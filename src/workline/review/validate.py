"""Structural validation of a Project's Review namespace.

A separate pass from ``ProjectView`` validation, and deliberately so (``R1``
§11). Review records are not lifecycle truth, so they are not loaded by the
thing that derives lifecycle; they are checked here, where a problem with them
can be reported without any of them ever reaching ``state.py``.

The baseline is that a Project with no ``.workline/review/`` is valid. Review
capability arrives lazily with the first Review write, and a Project that never
uses it keeps exactly the shape it has today.

Everything else fails closed, and is read the way the writer writes - through
the handle-bound, no-follow walk (:mod:`workline.review.fsafe`) and the
canonical read boundary (:func:`workline.review.serialize.parse_canonical`):
an unknown entry, a file where a directory belongs, a symlink, junction or
other reparse point anywhere in the namespace, a malformed or non-canonical
record, a name that does not match the identity inside the file, a broken or
non-full-snapshot generation chain, a duplicate logical ID, an authorization
record whose shared identities do not match what issued it, malformed or
inconsistent provenance, or a contradictory activation state.

P3's activation semantics are applied to the working tree (P3 F1 §10,
:func:`activation_problems`). An absent activation record means review-v1 Work
terminalization is not activated - a valid, ordinary state - and no completion
is classified by its position. A present record fixes the pre-activation Events
by its prefix digest; when that prefix reproduces, every ``work_completed``
after it is legacy without the review-v1 marker and bound by exactly one Work
Consumption with it, and when it does not, nothing after it is classified at
all. Lifecycle derivation never reads any of it.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing import Any

from ..errors import StopError, ValidationError
from ..ids import is_valid_id
from ..store import EVENT_LIFECYCLE_FIELDS, ProjectStore
from . import activation as work_activation
from . import paths, serialize
from .records import OPERATION_CONTRACT_REVIEW_V1, Consumption, GateGeneration, PlanningConsumption, Receipt
from .store import GateChain, ReviewStore


@dataclass(frozen=True)
class ReviewProblem:
    code: str
    message: str


#: What a sealed generation and the Receipt it issues must both say, field by
#: field. Where the two records name the same identity differently the pair
#: says so explicitly - the gate's ``coverage_digest`` *is* the Receipt's
#: ``coverage_hash`` - so no shared identity is left unbound because its name
#: differs (``R3`` §6-7, Candidate 7 §5).
GATE_RECEIPT_BINDING = (
    ("receipt_id", "receipt_id"),
    ("review_run_id", "review_run_id"),
    ("generation", "review_generation"),
    ("review_kind", "review_kind"),
    ("target_identity", "target_identity"),
    ("operation_identity", "operation_identity"),
    ("candidate_hash", "authorized_candidate_hash"),
    ("review_context_hash", "review_context_hash"),
    ("effective_policy_hash", "effective_policy_hash"),
    ("coverage_digest", "coverage_hash"),
    ("adjudication_digest", "adjudication_hash"),
    ("obligation_digest", "obligation_digest"),
    ("authorized_operation_stage", "authorized_operation_stage"),
)

#: What a Consumption repeats from the Receipt it consumes, and must repeat
#: exactly (``R4`` §2).
RECEIPT_CONSUMPTION_BINDING = (
    "receipt_id",
    "review_run_id",
    "review_generation",
    "review_kind",
    "target_identity",
    "operation_identity",
    "authorized_candidate_hash",
)


#: F1 §10's problems. Each refuses this Project's review-v1 use; none is ever a fallback to legacy.
ACTIVATION_PREFIX_MISMATCH = "review_activation_prefix_mismatch"
COMPLETION_MARKER_INVALID = "review_completion_marker_invalid"
COMPLETION_MARKER_CONTRADICTION = "review_completion_marker_contradiction"
COMPLETION_UNCONSUMED = "review_completion_unconsumed"
CONSUMPTION_UNBOUND = "review_consumption_unbound"

#: The Review consistency metadata a review-v1 ``work_completed`` carries, and nothing else (P1 R4 §5,
#: F1 §12.1): the operation-contract marker first, then what binds the Consumption of it.
COMPLETION_METADATA = ("operation_contract", "review_receipt_id", "review_run_id", "review_generation")


def validate_review(store: ProjectStore) -> list[ReviewProblem]:
    """Problems in this Project's Review namespace and in its activation classification; empty when there are none.

    The structural pass reads any P1 reader (:func:`review_problems`). The
    activation pass (:func:`activation_problems`) reads this Project's working
    tree - its event log and its pending recovery records - so it is made here,
    for the Project, and never by a reader of one commit's records.
    """
    review = ReviewStore(store)
    return review_problems(review) + activation_problems(store, review) + _policy_compatibility(store, review)


def review_problems(review: ReviewStore) -> list[ReviewProblem]:
    """:func:`validate_review` over any P1 reader - the working tree's, or one commit's committed records."""
    try:
        if not review.exists():
            return []  # a Project that has never used Review is a valid Project
    except ValidationError as exc:
        return [_problem(exc)]
    problems = _namespace_shape(review)
    if problems:
        # A namespace whose shape is wrong cannot be read record by record
        # without reporting the same broken thing repeatedly.
        return problems
    chains, chain_problems = _chains(review)
    problems.extend(chain_problems)
    receipts, receipt_problems = _receipts(review, chains)
    problems.extend(receipt_problems)
    problems.extend(_supersessions(review, chains, receipts))
    problems.extend(_consumptions(review, chains, receipts))
    problems.extend(_candidate_snapshots(review))
    problems.extend(_task_inputs(review))
    problems.extend(_provenance(review, chains))
    problems.extend(_p4_records(review, chains))
    problems.extend(_history_records(review))
    problems.extend(_activation(review))
    problems.extend(_policy_records(review, chains))
    return problems


def _problem(exc: ValidationError) -> ReviewProblem:
    return ReviewProblem(getattr(exc, "code", None) or "review_invalid", str(exc))


def _namespace_shape(review: ReviewStore) -> list[ReviewProblem]:
    """Only the known directories (P1's seven, P4's four, P5's history), each a plain directory - read without following.

    ``history/`` is the one area two levels deep (§28.3): it holds exactly the
    five history family directories, each plain, and nothing else.
    """
    try:
        found = review.entries(paths.REVIEW_DIR) or []
    except ValidationError as exc:
        return [_problem(exc)]
    problems: list[ReviewProblem] = []
    for entry in found:
        if entry.name not in paths.REVIEW_SUBDIRS:
            problems.append(ReviewProblem("review_namespace_invalid", f"{paths.REVIEW_DIR} holds unknown entry {entry.name}"))
        elif entry.is_indirection:
            problems.append(
                ReviewProblem("review_containment", f"{paths.REVIEW_DIR}/{entry.name} is a symlink, junction or other reparse point")
            )
        elif not entry.is_dir:
            problems.append(
                ReviewProblem("review_namespace_invalid", f"{paths.REVIEW_DIR}/{entry.name} is a file where a directory belongs")
            )
        elif entry.name == "history":
            problems.extend(_history_shape(review))
        elif entry.name == "policy":
            problems.extend(_policy_shape(review))
    return problems


def _policy_shape(review: ReviewStore) -> list[ReviewProblem]:
    """``policy/`` holds the one Profile file and the two evidence family directories, and nothing else (§30.17).

    Read without following: an indirection where the Profile or a family
    belongs is refused, and a Profile that is a directory, or a family that is
    a file, is a namespace problem. Absence of any of them is valid.
    """
    try:
        found = review.entries(paths.POLICY_DIR) or []
    except ValidationError as exc:
        return [_problem(exc)]
    problems: list[ReviewProblem] = []
    for entry in found:
        where = f"{paths.POLICY_DIR}/{entry.name}"
        if entry.name != paths.POLICY_PROFILE_NAME and entry.name not in paths.POLICY_FAMILIES:
            problems.append(ReviewProblem("review_namespace_invalid", f"{paths.POLICY_DIR} holds unknown entry {entry.name}"))
        elif entry.is_indirection:
            problems.append(ReviewProblem("review_containment", f"{where} is a symlink, junction or other reparse point"))
        elif entry.name == paths.POLICY_PROFILE_NAME and not entry.is_file:
            problems.append(ReviewProblem("review_namespace_invalid", f"{where} is not a plain Profile file"))
        elif entry.name in paths.POLICY_FAMILIES and not entry.is_dir:
            problems.append(ReviewProblem("review_namespace_invalid", f"{where} is a file where a directory belongs"))
    return problems


def _history_shape(review: ReviewStore) -> list[ReviewProblem]:
    """``history/`` holds only the five family directories, each a plain directory - read without following."""
    try:
        found = review.entries(paths.HISTORY_DIR) or []
    except ValidationError as exc:
        return [_problem(exc)]
    problems: list[ReviewProblem] = []
    for entry in found:
        if entry.name not in paths.HISTORY_FAMILIES:
            problems.append(ReviewProblem("review_namespace_invalid", f"{paths.HISTORY_DIR} holds unknown entry {entry.name}"))
        elif entry.is_indirection:
            problems.append(
                ReviewProblem("review_containment", f"{paths.HISTORY_DIR}/{entry.name} is a symlink, junction or other reparse point")
            )
        elif not entry.is_dir:
            problems.append(
                ReviewProblem("review_namespace_invalid", f"{paths.HISTORY_DIR}/{entry.name} is a file where a directory belongs")
            )
    return problems


def _chains(review: ReviewStore) -> tuple[dict[str, GateChain], list[ReviewProblem]]:
    chains: dict[str, GateChain] = {}
    problems: list[ReviewProblem] = []
    try:
        run_ids = review.run_ids()
    except ValidationError as exc:
        return chains, [_problem(exc)]
    for review_run_id in run_ids:
        try:
            chain = review.gate_chain(review_run_id)
        except ValidationError as exc:
            problems.append(_problem(exc))
            continue
        if chain is None:
            problems.append(
                ReviewProblem(
                    "review_namespace_invalid",
                    f"{paths.run_dir(review_run_id)} holds no gate generation; an empty Review Run directory "
                    "is not a state a Review Run reaches",
                )
            )
            continue
        chains[review_run_id] = chain
    return chains, problems


def _receipts(review: ReviewStore, chains: dict[str, GateChain]) -> tuple[dict[str, Receipt], list[ReviewProblem]]:
    """Every Receipt, bound exactly to the sealed generation that issued it - and every seal to its Receipt."""
    receipts: dict[str, Receipt] = {}
    problems: list[ReviewProblem] = []
    try:
        receipt_ids = review.receipt_ids()
    except ValidationError as exc:
        return receipts, [_problem(exc)]
    for receipt_id in receipt_ids:
        try:
            receipt = review.read_receipt(receipt_id)
        except ValidationError as exc:
            problems.append(_problem(exc))
            continue
        receipts[receipt_id] = receipt
        chain = chains.get(receipt.review_run_id)
        if chain is None:
            problems.append(
                ReviewProblem(
                    "review_record_missing",
                    f"receipt {receipt_id} names Review Run {receipt.review_run_id}, which has no valid gate chain",
                )
            )
            continue
        if not chain.has_generation(receipt.review_generation):
            problems.append(
                ReviewProblem(
                    "review_record_conflict",
                    f"receipt {receipt_id} says it was issued by generation {receipt.review_generation}, which "
                    f"Review Run {receipt.review_run_id} does not have",
                )
            )
            continue
        problems.extend(_gate_receipt_binding(chain.generation(receipt.review_generation), receipt))
    for chain in chains.values():
        for generation in chain.generations:
            if generation.receipt_id is not None and generation.receipt_id not in receipts:
                problems.append(
                    ReviewProblem(
                        "review_record_missing",
                        f"Review Run {chain.review_run_id} generation {generation.generation} issues receipt "
                        f"{generation.receipt_id}, which is not stored",
                    )
                )
    issued: dict[str, str] = {}
    for chain in chains.values():
        for generation in chain.generations:
            if generation.receipt_id is None:
                continue
            where = f"{chain.review_run_id} generation {generation.generation}"
            if generation.receipt_id in issued:
                problems.append(
                    ReviewProblem(
                        "review_gate_chain",
                        f"receipt {generation.receipt_id} is issued by both {issued[generation.receipt_id]} and {where}",
                    )
                )
            issued[generation.receipt_id] = where
    return receipts, problems


def _gate_receipt_binding(generation: GateGeneration, receipt: Receipt) -> list[ReviewProblem]:
    problems: list[ReviewProblem] = []
    if not generation.sealed:
        problems.append(
            ReviewProblem(
                "review_record_conflict",
                f"receipt {receipt.receipt_id} was issued by generation {generation.generation}, which is "
                f"{generation.status}; only a sealed generation issues a Receipt",
            )
        )
    for gate_field, receipt_field in GATE_RECEIPT_BINDING:
        gate_value = getattr(generation, gate_field)
        receipt_value = getattr(receipt, receipt_field)
        if gate_value != receipt_value:
            problems.append(
                ReviewProblem(
                    "review_record_conflict",
                    f"receipt {receipt.receipt_id} says {receipt_field} {receipt_value!r}, but the generation that "
                    f"issued it says {gate_field} {gate_value!r}",
                )
            )
    return problems


def _superseded(chains: dict[str, GateChain], review: ReviewStore) -> tuple[set[str], list[ReviewProblem]]:
    """Receipts that are superseded, and whether the record and the chain agree about it.

    ``R3`` §8: invalidation creates a later open generation *and* a
    supersession record. A Receipt the chain has moved past without a
    supersession record, or a supersession record for a Receipt the chain has
    not moved past, is a half-written invalidation.
    """
    problems: list[ReviewProblem] = []
    try:
        recorded = set(review.superseded_receipt_ids())
    except ValidationError as exc:
        return set(), [_problem(exc)]
    derived: set[str] = set()
    for chain in chains.values():
        derived.update(chain.superseded_receipts())
    for receipt_id in sorted(derived - recorded):
        problems.append(
            ReviewProblem(
                "review_record_missing",
                f"receipt {receipt_id} was moved past by a later generation, but no supersession record says so",
            )
        )
    return recorded | derived, problems


def _supersessions(
    review: ReviewStore, chains: dict[str, GateChain], receipts: dict[str, Receipt]
) -> list[ReviewProblem]:
    """Each supersession names a stored Receipt of the same Run and a real, later, open generation."""
    problems: list[ReviewProblem] = []
    _, derived_problems = _superseded(chains, review)
    problems.extend(derived_problems)
    try:
        superseded_ids = review.superseded_receipt_ids()
    except ValidationError as exc:
        return [_problem(exc)]
    for receipt_id in superseded_ids:
        try:
            supersession = review.read_supersession(receipt_id)
        except ValidationError as exc:
            problems.append(_problem(exc))
            continue
        receipt = receipts.get(receipt_id)
        if receipt is None:
            problems.append(
                ReviewProblem("review_record_missing", f"supersession names receipt {receipt_id}, which is not stored")
            )
            continue
        if receipt.review_run_id != supersession.review_run_id:
            problems.append(
                ReviewProblem(
                    "review_record_conflict",
                    f"supersession of {receipt_id} names Review Run {supersession.review_run_id}, "
                    f"but the receipt names {receipt.review_run_id}",
                )
            )
            continue
        chain = chains.get(supersession.review_run_id)
        if chain is None or not chain.has_generation(supersession.superseding_generation):
            problems.append(
                ReviewProblem(
                    "review_record_conflict",
                    f"supersession of {receipt_id} names superseding generation {supersession.superseding_generation}, "
                    f"which Review Run {supersession.review_run_id} does not have",
                )
            )
            continue
        if supersession.superseding_generation <= receipt.review_generation:
            problems.append(
                ReviewProblem(
                    "review_record_conflict",
                    f"supersession of {receipt_id} names generation {supersession.superseding_generation}, which is "
                    f"not later than the generation {receipt.review_generation} that issued the receipt",
                )
            )
            continue
        if chain.generation(supersession.superseding_generation).sealed:
            problems.append(
                ReviewProblem(
                    "review_record_conflict",
                    f"supersession of {receipt_id} names generation {supersession.superseding_generation}, which is "
                    "sealed; an invalidation creates an open generation",
                )
            )
    return problems


def _consumptions(
    review: ReviewStore, chains: dict[str, GateChain], receipts: dict[str, Receipt]
) -> list[ReviewProblem]:
    problems: list[ReviewProblem] = []
    try:
        by_receipt = review.consumption_by_receipt()
        review.consumption_by_terminal_event()
        # Planning Consumptions (version 2) are unique by Receipt as every
        # Consumption is, and by their kind-specific persisted-result binding:
        # one per registration commit, one per (review_kind, target_identity).
        review.planning_consumption_by_commit()
        review.planning_consumption_by_target()
    except ValidationError as exc:
        return [_problem(exc)]
    superseded, _ = _superseded(chains, review)
    for receipt_id, consumption in by_receipt.items():
        receipt = receipts.get(receipt_id)
        if receipt is None:
            problems.append(
                ReviewProblem(
                    "review_record_missing",
                    f"consumption {consumption.consumption_id} consumes receipt {receipt_id}, which is not stored",
                )
            )
            continue
        if receipt_id in superseded:
            problems.append(
                ReviewProblem(
                    "review_record_conflict",
                    f"consumption {consumption.consumption_id} consumes receipt {receipt_id}, which is superseded; "
                    "a superseded authorization is never consumed",
                )
            )
        problems.extend(_receipt_consumption_binding(receipt, consumption))
    return problems


def _receipt_consumption_binding(receipt: Receipt, consumption: "Consumption | PlanningConsumption") -> list[ReviewProblem]:
    problems: list[ReviewProblem] = []
    for name in RECEIPT_CONSUMPTION_BINDING:
        if getattr(receipt, name) != getattr(consumption, name):
            problems.append(
                ReviewProblem(
                    "review_record_conflict",
                    f"consumption {consumption.consumption_id} says {name} {getattr(consumption, name)!r}, but the "
                    f"receipt it consumes says {getattr(receipt, name)!r}",
                )
            )
    return problems


def _provenance(review: ReviewStore, chains: dict[str, GateChain]) -> list[ReviewProblem]:
    """Every accepted task's reconstruction material is stored and agrees with it exactly.

    An accepted task whose snapshot or task input is missing, or whose stored
    provenance disagrees with it in any shared identity, cannot be rerun or
    retrieved after runtime loss - which is the whole point of the records being
    canonical rather than runtime (``R3`` §4). Each task is checked once, at the
    generation that first accepted it: later generations carry the identical
    descriptor forward, which the chain has already proven.
    """
    problems: list[ReviewProblem] = []
    for review_run_id, chain in sorted(chains.items()):
        seen: set[str] = set()
        for generation in chain.generations:
            for task in generation.accepted_tasks:
                task_id = str(task["task_id"])
                if task_id in seen:
                    continue
                seen.add(task_id)
                where = f"Review Run {review_run_id} generation {generation.generation}"
                for code, message in review.provenance_problems(task, generation.generation):
                    problems.append(ReviewProblem(code, f"{where}: {message}"))
    return problems


def _candidate_snapshots(review: ReviewStore) -> list[ReviewProblem]:
    """Every stored Candidate snapshot, referenced or not, is structurally valid (``R1`` §11, P1-REV-008).

    A snapshot is read only when an accepted task points at it (:func:`_provenance`),
    so a structurally broken snapshot that nothing references - malformed,
    non-canonical, an indirection, or a filename that is not the candidate hash
    inside it - would otherwise never be looked at. Enumerating them here reads
    each one the way every Review record is read (no-follow, canonical bytes,
    schema round-trip, filename == identity inside), so its shape is checked
    whether or not it is reachable. A valid but unreferenced snapshot is a legal
    orphan (crash/recovery, immutable write ordering) and is simply validated,
    not condemned - no reachability or garbage-collection policy is introduced.
    """
    try:
        hashes = review.candidate_snapshot_hashes()
    except ValidationError as exc:
        return [_problem(exc)]
    problems: list[ReviewProblem] = []
    for candidate_hash in hashes:
        try:
            review.read_candidate_snapshot(candidate_hash)
        except ValidationError as exc:
            problems.append(_problem(exc))
    return problems


def _task_inputs(review: ReviewStore) -> list[ReviewProblem]:
    """Every stored task input, referenced or not, is structurally valid (``R1`` §11, P1-REV-008).

    The same blind spot as Candidate snapshots: a task input is read only when
    an accepted task names it, so an unreferenced one is enumerated and read
    here - canonical bytes, schema round-trip, and a filename that is the
    ``review_task`` id inside it. A valid unreferenced task input is a legal
    orphan and only validated.
    """
    try:
        task_ids = review.task_input_ids()
    except ValidationError as exc:
        return [_problem(exc)]
    problems: list[ReviewProblem] = []
    for task_id in task_ids:
        try:
            review.read_task_input(task_id)
        except ValidationError as exc:
            problems.append(_problem(exc))
    return problems


def _p4_records(review: ReviewStore, chains: dict[str, GateChain]) -> list[ReviewProblem]:
    """The four P4 record kinds, referenced or orphaned, and every P4 Run's chain against them (§12.22, §27.5).

    Each stored record is read through its strict reader whether or not anything
    references it - a valid orphan (a crash between a record's create and its
    generation's commit) is only validated, never condemned. A P4 Run is known
    by the explicit contract its stored TaskInput binds, never by its shape;
    its chain must be a P4 shape, and every record its generations reference
    must be stored and agree with what the generation binds.
    """
    from . import p4

    problems: list[ReviewProblem] = []
    stored: dict[str, dict[str, Any]] = {"report": {}, "adjudication": {}, "batch": {}, "result": {}}
    for kind, list_ids, read in (
        ("report", review.report_digests, review.read_report),
        ("adjudication", review.adjudication_run_ids, review.read_adjudication),
        ("batch", review.repair_batch_ids, review.read_repair_batch),
        ("result", review.repair_result_ids, review.read_repair_result),
    ):
        try:
            identifiers = list_ids()
        except ValidationError as exc:
            problems.append(_problem(exc))
            continue
        for identifier in identifiers:
            try:
                stored[kind][identifier] = read(identifier)
            except ValidationError as exc:
                problems.append(_problem(exc))
    for run_id, found in sorted(stored["adjudication"].items()):
        for message in p4.adjudication_problems(found):
            problems.append(ReviewProblem("review_record_invalid", f"P4 adjudication of {run_id}: {message}"))
    for batch_id, batch in sorted(stored["batch"].items()):
        source = stored["adjudication"].get(batch.source_review_run_id)
        if source is None:
            continue
        try:
            source_digest = review.adjudication_digest(batch.source_review_run_id)
        except ValidationError as exc:
            problems.append(_problem(exc))
            continue
        if batch.adjudication_digest != source_digest or batch.source_candidate_hash != source.candidate_hash:
            problems.append(ReviewProblem(
                "review_record_conflict",
                f"Repair Batch {batch_id} does not bind the adjudication of its source Run {batch.source_review_run_id}",
            ))
        expected, deliberate = p4.repair_finding_ids(source)
        if list(batch.finding_ids) != expected or list(batch.deliberate_low_finding_ids) != deliberate:
            problems.append(ReviewProblem(
                "review_record_conflict",
                f"Repair Batch {batch_id} does not hold exactly the blocking and deliberately repaired Findings of "
                f"{batch.source_review_run_id}",
            ))
    for batch_id, result in sorted(stored["result"].items()):
        batch = stored["batch"].get(batch_id)
        if batch is None:
            continue
        for message in p4.linkage_problems(
            batch, result, source_run_id=batch.source_review_run_id, source_candidate_hash=batch.source_candidate_hash,
            source_candidate_generation=batch.candidate_generation, snapshot_hash=result.result_candidate_hash,
        ):
            problems.append(ReviewProblem("review_record_conflict", f"Repair Result {batch_id}: {message}"))
        if not review.candidate_snapshot_exists(result.result_candidate_hash):
            continue  # an orphan Result (its generation never committed) is only validated
        try:
            material = review.candidate_material_digest(result.result_candidate_hash)
        except ValidationError as exc:
            problems.append(_problem(exc))
            continue
        if material != result.result_candidate_material_digest:
            problems.append(ReviewProblem(
                "review_record_conflict",
                f"Repair Result {batch_id} binds Candidate material {result.result_candidate_material_digest}, and the "
                f"stored snapshot digests to {material}",
            ))
    for run_id, chain in sorted(chains.items()):
        problems.extend(_p4_chain(review, run_id, chain, stored))
    return problems


def _p4_chain(
    review: ReviewStore, run_id: str, chain: GateChain, stored: dict[str, dict[str, Any]]
) -> list[ReviewProblem]:
    from . import p4

    first = chain.generations[0]
    try:
        task_inputs = [review.read_task_input(str(task["task_id"])) for task in first.accepted_tasks]
    except ValidationError:
        return []  # a missing or malformed task input is the provenance pass's to report
    contracts = {p4.contract_of_task_input(found) for found in task_inputs}
    if contracts <= {None}:  # no TaskInput, or only v1 ones: not a P4 Run, the v1 passes own it
        if run_id in stored["adjudication"]:
            return [ReviewProblem(
                "review_record_conflict",
                f"a P4 adjudication names Review Run {run_id}, whose generation 1 binds no P4 contract",
            )]
        return []
    where = f"P4 Review Run {run_id}"
    if len(contracts) != 1:
        return [ReviewProblem("review_record_conflict", f"{where} binds more than one contract at generation 1")]
    problems = [ReviewProblem("review_gate_chain", f"{where}: {message}") for message in p4.chain_problems(chain)]
    if problems:
        return problems
    contract = next(iter(contracts))
    if not p4.repairs(contract) and p4.shape_of(chain) == p4.SHAPE_REPAIR:
        # a G4-terminal contract (P6 Policy Review) has no Repair Batch branch
        return [ReviewProblem("review_gate_chain", f"{where} accepts a repair under {contract}, which has no Repair "
                                                   "Batch branch")]
    for task in p4.discovery_tasks(chain):
        settled = p4.settled_of(chain, str(task["task_id"]))
        if settled is None:
            continue
        report = stored["report"].get(str(settled["result_digest"]))
        if report is None:
            problems.append(ReviewProblem(
                "review_record_missing",
                f"{where} settles discovery task {task['task_id']} with report {settled['result_digest']}, which is "
                "not stored canonically",
            ))
        elif report.task_id != str(task["task_id"]) or report.task_slot != str(task["task_slot"]):
            problems.append(ReviewProblem(
                "review_record_conflict", f"{where}: report {settled['result_digest']} is not of the task it settles",
            ))
    if len(chain.generations) >= p4.ADJUDICATION_SETTLE_GENERATION:
        fourth = chain.generation(p4.ADJUDICATION_SETTLE_GENERATION)
        found = stored["adjudication"].get(run_id)
        if found is None:
            problems.append(ReviewProblem("review_record_missing", f"{where} settles its adjudication, which is not stored"))
        else:
            if fourth.adjudication_digest != review.adjudication_digest(run_id) \
                    or found.candidate_hash != first.candidate_hash:
                problems.append(ReviewProblem(
                    "review_record_conflict", f"{where}: generation 4 does not bind its stored adjudication",
                ))
            if fourth.obligation_digest != serialize.digest(p4.obligations_record(found)):
                problems.append(ReviewProblem(
                    "review_record_conflict", f"{where}: generation 4 does not bind its adjudication's obligations",
                ))
    if p4.shape_of(chain) == p4.SHAPE_REPAIR:
        repair = p4.repair_task(chain)
        try:
            envelope = review.read_task_input(str(repair["task_id"])).request_envelope if repair else {}
        except ValidationError:
            envelope = {}
        batch_id = str(envelope.get("repair_batch_id"))
        batch = stored["batch"].get(batch_id)
        if batch is None or batch.source_review_run_id != run_id:
            problems.append(ReviewProblem(
                "review_record_missing",
                f"{where} accepts a repair of Repair Batch {batch_id}, which is not stored as its own",
            ))
            return problems
        if review.repair_batch_digest(batch_id) != envelope.get("repair_batch_digest"):
            problems.append(ReviewProblem("review_record_conflict", f"{where}: the repair request binds another batch"))
        if len(chain.generations) >= p4.REPAIR_SETTLE_GENERATION and repair is not None:
            settled = p4.settled_of(chain, str(repair["task_id"]))
            result = stored["result"].get(batch_id)
            if settled is None or result is None:
                problems.append(ReviewProblem("review_record_missing", f"{where} settles a repair whose Result is not stored"))
            elif review.repair_result_digest(batch_id) != settled["result_digest"]:
                problems.append(ReviewProblem(
                    "review_record_conflict", f"{where}: generation 6 does not settle its stored Repair Result",
                ))
            elif not review.candidate_snapshot_exists(result.result_candidate_hash):
                problems.append(ReviewProblem(
                    "review_record_missing", f"{where}: Candidate N+1 {result.result_candidate_hash} is not stored",
                ))
    return problems


def _policy_records(review: ReviewStore, chains: dict[str, GateChain]) -> list[ReviewProblem]:
    """P6 normative Review validation (§30.30): the Profile, change and evaluation records, read strictly.

    Absence is valid. A malformed Profile, a broken lineage, an unreadable or
    orphaned evidence record, a Policy Receipt consumed by anything but a
    version 3 Policy Consumption, and a Policy Review Run with a repair branch
    are Problems. Whether the Profile is compatible with the current Global
    baseline needs the configured Workline root, so it is checked for the
    Project (:func:`validate_review`), never for one commit's records.
    """
    from . import p4, policy
    from .records import PolicyConsumption

    problems = [ReviewProblem(code, message) for code, message in policy.policy_problems(review, None)]
    try:
        consumptions = review.consumptions()
    except ValidationError:
        consumptions = ()  # the Consumption pass reports it
    try:
        policy_receipts = {str(review.read_policy_change(change_id)["receipt_id"])
                           for change_id in review.policy_change_ids()}
    except ValidationError:
        policy_receipts = set()  # the record pass reports it
    for found in consumptions:
        if isinstance(found, PolicyConsumption):
            try:
                receipt = review.read_receipt(found.receipt_id)
            except ValidationError:
                continue  # the Consumption pass reports a missing Receipt
            if receipt.review_kind != policy.REVIEW_KIND \
                    or receipt.authorized_operation_stage != policy.AUTHORIZED_OPERATION_STAGE:
                problems.append(ReviewProblem("review_record_conflict",
                                              f"Policy Consumption {found.consumption_id} consumes a Receipt that is not a "
                                              "Policy Change authorization"))
            change_id = str(found.persisted_policy["policy_change_id"])
            try:
                change = review.read_policy_change(change_id) if review.policy_change_exists(change_id) else None
            except ValidationError:
                change = None
            if change is None or change["receipt_id"] != found.receipt_id \
                    or change["after_profile_digest"] != found.persisted_policy["after_profile_digest"] \
                    or change["candidate_hash"] != found.authorized_candidate_hash:
                problems.append(ReviewProblem("review_record_conflict",
                                              f"Policy Consumption {found.consumption_id} does not bind the stored change "
                                              f"record of {change_id}"))
        elif found.receipt_id in policy_receipts:
            problems.append(ReviewProblem("review_record_conflict",
                                          f"consumption {found.consumption_id} consumes the Policy Change Receipt "
                                          f"{found.receipt_id} and is not a version 3 Policy Consumption"))
    for run_id, chain in sorted(chains.items()):
        first = chain.generations[0]
        try:
            contracts = {p4.contract_of_task_input(review.read_task_input(str(task["task_id"])))
                         for task in first.accepted_tasks}
        except ValidationError:
            continue  # the provenance pass reports it
        if policy.POLICY_CHANGE_CONTRACT not in contracts:
            continue
        where = f"Policy Review Run {run_id}"
        if contracts != {policy.POLICY_CHANGE_CONTRACT} or first.target_identity != policy.TARGET_IDENTITY \
                or first.review_kind != policy.REVIEW_KIND:
            problems.append(ReviewProblem("review_record_conflict",
                                          f"{where} does not bind exactly the Policy Review contract, kind and target"))
    return problems


def _policy_compatibility(store: ProjectStore, review: ReviewStore) -> list[ReviewProblem]:
    """§30.7 / §30.30: an incompatible canonical Profile is a validation Problem; an absent one never is."""
    from . import policy

    try:
        if review.read_profile_bytes() is None:
            return []
        profile = review.read_profile()
    except ValidationError:
        return []  # a malformed Profile is the record pass's
    try:
        workline_root = store.workline_root()
        baseline = policy.load_global_baseline(workline_root)
    except (ValidationError, StopError) as exc:
        return [ReviewProblem(policy.CODE_BASELINE_UNAVAILABLE, "the Global policy baseline cannot be derived to "
                                                                f"check the Project Profile: {exc}")]
    problem = policy.compatibility_problem(profile, baseline, review)
    if problem is None:
        return []
    return [ReviewProblem(policy.CODE_PROFILE_INCOMPATIBLE, f"the canonical Project Profile is incompatible: {problem} "
                                                            "(policy maintenance / reconcile)")]


def _history_records(review: ReviewStore) -> list[ReviewProblem]:
    """Every P5 history record, referenced or not, is structurally valid (§28.17 shape, schema, identity).

    Structural only: each family directory is enumerated (no indirection, no
    nested directory, no non-record entry, a filename that is the family's
    identity kind) and each record is read through its strict reader
    (canonical bytes, exact schema and version, filename == identity inside).
    Whether a summary agrees with its immutable source is
    :func:`workline.review.history.history_problems`, which is deliberately
    not part of this pass: a broken history record never changes lifecycle
    truth (§28.17). A Project with no history namespace has nothing here.
    """
    from . import history

    return [ReviewProblem(code, message) for code, message in history.load_history(review).problems]


def activation_problems(store: ProjectStore, review: ReviewStore) -> list[ReviewProblem]:
    """P3 F1 §10 over this Project's working tree: the activation boundary, and review-v1 totality after it.

    ```text
    no activation record      valid and not activated; no completion is classified
                              by its position, and a review-v1 marker contradicts it
    a record HEAD does not    review_record_conflict: an uncommitted, deleted or
    hold as the working tree  changed record is never activation, and nothing is
    holds it                  classified by it
    activation whose prefix   Events 0 .. N-1 are pre-activation legacy and need nothing;
    reproduces                a work_completed at index >= N is
                                without the marker        legacy - no Consumption
                                marked review-v1          bound by exactly one Work
                                                          Consumption that repeats it
                                any other marker          invalid
    activation whose prefix   fails closed: nothing after it is classified
    does not reproduce
    ```

    The activation is the record current HEAD commits, held unchanged by the
    working tree - the one check START's entry makes too
    (:func:`workline.review.activation.current_activation`). The prefix is read
    through the one digest implementation over the event log this validation
    reads, so the indexes it classifies are the indexes the digest fixed.

    A one-sided review-v1 state - the event without its Consumption, or the
    Consumption without its event - is valid only while a pending review-v1
    Work START holds the one terminal stage both belong to, with the missing
    half still unapplied (:func:`workline.start_review.recorded_terminal`);
    never because of what the files themselves hold. A malformed record is the
    structural pass's to report, and classifies nothing either way.
    """
    found = _committed_activation(store, review)
    if isinstance(found, list):
        return found
    events = _event_log(store)
    if found.state == work_activation.NOT_ACTIVATED:
        return [] if events is None else _unactivated_markers(events)
    activation = found.record
    if activation is None:
        return [ReviewProblem("review_record_conflict", f"{found.conflict()}; no completion is classified by it")]
    count = activation.legacy_event_count
    if events is None or work_activation.prefix_digest(events, count) != activation.legacy_event_prefix_sha256:
        return [
            ReviewProblem(
                ACTIVATION_PREFIX_MISMATCH,
                f"the activation fixes {count} pre-activation Events by their digest, and this event log does not "
                "reproduce it; no completion after them is classified",
            )
        ]
    try:
        consumptions = {
            event_id: found
            for event_id, found in review.consumption_by_terminal_event().items()
            if isinstance(found, Consumption) and found.work_kind
        }
    except ValidationError:
        return []  # a conflict between Consumptions is the structural pass's to report
    terminals = _recorded_terminals(store)
    problems: list[ReviewProblem] = []
    bound: set[str] = set()
    for index, event in enumerate(events):
        if event.get("type") != "work_completed":
            continue
        reviewed, malformed = _marker(event)
        where = f"work_completed {event['id']} (Event {index}) of {event['entity']}"
        if malformed is not None:
            problems.append(ReviewProblem(COMPLETION_MARKER_INVALID, f"{where} {malformed}"))
            continue
        if not reviewed:
            continue  # legacy, before the boundary or after it
        if index < count:
            problems.append(ReviewProblem(
                COMPLETION_MARKER_CONTRADICTION,
                f"{where} carries the review-v1 marker, and the activation fixes it as one of the {count} "
                "pre-activation Events, which are never review-v1",
            ))
            continue
        consumption = consumptions.get(event["id"])
        if consumption is None:
            if not _event_awaits_consumption(store, review, terminals, event):
                problems.append(ReviewProblem(
                    COMPLETION_UNCONSUMED,
                    f"{where} is a review-v1 completion and no Work Consumption binds it, and no pending terminal "
                    "stage of a review-v1 START holds them together",
                ))
            continue
        bound.add(consumption.consumption_id)
        contradicted = _binding_contradictions(event, consumption)
        if contradicted:
            problems.append(ReviewProblem(
                COMPLETION_MARKER_CONTRADICTION,
                f"{where} and consumption {consumption.consumption_id} that binds it disagree: " + "; ".join(contradicted),
            ))
    positions: dict[str, int] = {}
    for index, event in enumerate(events):
        positions.setdefault(event["id"], index)
    for event_id, consumption in sorted(consumptions.items()):
        if consumption.consumption_id in bound:
            continue
        index = positions.get(event_id)
        if index is None:
            if _consumption_awaits_event(store, review, terminals, consumption):
                continue
            detail = "names a terminal event this event log does not hold"
        else:
            detail = f"binds Event {index}, which is not a review-v1 completion after the activation"
        problems.append(ReviewProblem(
            CONSUMPTION_UNBOUND,
            f"Work consumption {consumption.consumption_id} {detail}, and no pending terminal stage of a review-v1 "
            "START holds them together",
        ))
    return problems


def _committed_activation(
    store: ProjectStore, review: ReviewStore
) -> work_activation.Currentness | list[ReviewProblem]:
    """This Project's activation as its current HEAD commits it; or the problems that keep it from being shown.

    HEAD is read through a read-only class B context, which captures no
    identity and writes nothing into the Project: validating a Project leaves
    it exactly as it was. A working record the Review store cannot read, or a
    current record that is malformed or of an unknown contract, is the
    structural pass's to report and classifies nothing. Whatever keeps HEAD's
    record from being read is a problem of its own, never an absence.
    """
    from . import hermetic

    try:
        with hermetic.read_only(store.root) as git:
            return work_activation.current_activation(review, git, work_activation.head_commit(git))
    except work_activation.CommittedRecordUnreadable as exc:
        return [ReviewProblem(exc.code, f"{exc}; no completion is classified by it")]
    except ValidationError:
        return []
    except StopError as exc:
        return _unprovable(review, exc)


def _unprovable(review: ReviewStore, exc: StopError) -> work_activation.Currentness | list[ReviewProblem]:
    """Where HEAD's record cannot be read at all, no working record is ever taken for one.

    That is the case only when the read-only class B context itself cannot be
    prepared, or its scratch outside the Project fails its proof before a read.
    A working record is then a problem. With none, nothing claims an
    activation, and the Project reads as it always did.
    """
    try:
        claimed = review.read_bytes(paths.WORK_TERMINAL_ACTIVATION_REL) is not None
    except ValidationError:
        return []
    if not claimed:
        return work_activation.Currentness(None, work_activation.NOT_ACTIVATED)
    return [ReviewProblem(exc.code, f"the activation record cannot be shown to be the one HEAD commits ({exc}); "
                                    "no completion is classified by it")]


def _event_log(store: ProjectStore) -> list[dict[str, Any]] | None:
    """The working tree's event log, parsed by the activation digest's own reader; None when it does not read."""
    try:
        data = store.events_jsonl.read_bytes()
    except OSError:
        return None
    return work_activation.parse_event_log(data)


def _marker(event: dict[str, Any]) -> tuple[bool, str | None]:
    """``(review-v1, problem)`` for one ``work_completed``: only true absence of the marker is legacy.

    Review metadata without the marker, an unknown marker, and a review-v1
    marker whose metadata is not exactly the frozen set of well-formed values
    are all invalid; none of them is read as legacy (F1 §10.3).
    """
    carried = [key for key in COMPLETION_METADATA if key in event]
    if not carried:
        return False, None
    if "operation_contract" not in event:
        return False, f"carries Review metadata ({', '.join(carried)}) without the operation-contract marker"
    if event["operation_contract"] != OPERATION_CONTRACT_REVIEW_V1:
        return False, f"carries the unknown operation-contract marker {event['operation_contract']!r}"
    metadata = sorted(key for key in event if key not in EVENT_LIFECYCLE_FIELDS)
    if metadata != sorted(COMPLETION_METADATA):
        return False, f"carries the review-v1 marker with the metadata {metadata}, not exactly {list(COMPLETION_METADATA)}"
    generation = event["review_generation"]
    if (
        not isinstance(event["review_receipt_id"], str) or not is_valid_id(event["review_receipt_id"], "review_receipt")
        or not isinstance(event["review_run_id"], str) or not is_valid_id(event["review_run_id"], "review_run")
        or type(generation) is not int or generation < 1
    ):
        return False, "carries the review-v1 marker with malformed receipt, run or generation metadata"
    return True, None


def _unactivated_markers(events: list[dict[str, Any]]) -> list[ReviewProblem]:
    """With no activation, no completion is review-v1: its marker contradicts the Project, and a malformed one is invalid."""
    problems: list[ReviewProblem] = []
    for index, event in enumerate(events):
        if event.get("type") != "work_completed":
            continue
        reviewed, malformed = _marker(event)
        where = f"work_completed {event['id']} (Event {index}) of {event['entity']}"
        if malformed is not None:
            problems.append(ReviewProblem(COMPLETION_MARKER_INVALID, f"{where} {malformed}"))
        elif reviewed:
            problems.append(ReviewProblem(
                COMPLETION_MARKER_CONTRADICTION,
                f"{where} carries the review-v1 marker, and this Project has not activated review-v1 Work "
                "terminalization",
            ))
    return problems


def _binding_contradictions(event: dict[str, Any], consumption: Consumption) -> list[str]:
    """What the Consumption that binds a review-v1 completion says differently from the completion itself."""
    expected = {
        "target_identity": event["entity"],
        "receipt_id": event["review_receipt_id"],
        "review_run_id": event["review_run_id"],
        "review_generation": event["review_generation"],
    }
    return [
        f"the consumption says {name} {getattr(consumption, name)!r}, the completion {value!r}"
        for name, value in expected.items()
        if getattr(consumption, name) != value
    ]


def _recorded_terminals(store: ProjectStore) -> list[Any]:
    """The terminal stages pending review-v1 Work STARTs recorded; an unreadable recovery area excuses nothing."""
    from ..mutation import MutationController
    from ..start_review import recorded_terminal

    try:
        pending = MutationController(store).list_pending()
    except StopError:
        return []
    return [found for found in (recorded_terminal(record, store) for record in pending) if found is not None]


def _stored(review: ReviewStore, relative: str) -> bytes | None | bool:
    """The bytes at ``relative``; None when absent; False when what is there cannot be read as a record."""
    try:
        return review.read_bytes(relative)
    except ValidationError:
        return False


def _event_awaits_consumption(
    store: ProjectStore, review: ReviewStore, terminals: list[Any], event: dict[str, Any]
) -> bool:
    """A pending terminal stage wrote exactly this completion, the log is as it left it, and its create is unapplied."""
    from ..mutation import _content_digest

    return any(
        terminal.completed == event
        and _stored(review, terminal.consumption_path) is None
        and terminal.log_after is not None
        and terminal.log_after == _content_digest(store.events_jsonl)
        for terminal in terminals
    )


def _consumption_awaits_event(
    store: ProjectStore, review: ReviewStore, terminals: list[Any], consumption: Consumption
) -> bool:
    """A pending terminal stage wrote exactly this Consumption itself, and its replay can still append the events.

    The replay appends an event only to the log its own record says it found
    there, and commits the Consumption only as the bytes it recorded writing;
    a Consumption someone else placed, or a log someone else changed, is no
    half of this stage that the replay could finish, however exact the bytes.
    """
    from ..mutation import _content_digest, _text_digest

    relative = paths.consumption_rel(consumption.consumption_id)
    return any(
        terminal.consumption_path == relative
        and terminal.completed.get("id") == consumption.terminal_event_id
        and _stored(review, relative) == terminal.consumption_content.encode("utf-8")
        and terminal.consumption_written == _text_digest(terminal.consumption_content)
        and terminal.log_before is not None
        and terminal.log_before == _content_digest(store.events_jsonl)
        for terminal in terminals
    )


def _activation(review: ReviewStore) -> list[ReviewProblem]:
    """The activation directory holds only the one activation record P1 defines, and it parses if present.

    Fully enumerated, not read by exact path alone (P1-REV-008): the only
    physical entry ``activation/`` may hold is ``work-terminal-v1.yaml`` as a
    plain file. An unknown entry, a nested directory, or a symlink/junction/
    reparse point anywhere in it fails closed. An *absent* record stays valid
    and means review-v1 Work terminalization is not activated - the state P1
    leaves every Project in - and even a present, valid record activates no
    START, Roadmap or P3 behavior here; it is only structurally validated.
    """
    problems: list[ReviewProblem] = []
    try:
        found = review.entries(paths.ACTIVATION_DIR)
    except ValidationError as exc:
        return [_problem(exc)]
    allowed = paths.WORK_TERMINAL_ACTIVATION_REL.rsplit("/", 1)[-1]
    for entry in found or []:
        if entry.name == allowed and entry.is_file and not entry.is_indirection:
            continue
        if entry.is_indirection:
            problems.append(
                ReviewProblem("review_containment", f"{paths.ACTIVATION_DIR}/{entry.name} is a symlink, junction or other reparse point")
            )
        elif entry.name != allowed:
            problems.append(
                ReviewProblem(
                    "review_namespace_invalid",
                    f"{paths.ACTIVATION_DIR} holds {entry.name}; the only activation record P1 defines is {allowed}",
                )
            )
        else:  # the expected name, but a directory rather than a plain file
            problems.append(
                ReviewProblem("review_namespace_invalid", f"{paths.ACTIVATION_DIR}/{entry.name} is not a plain file")
            )
    # The record parses (if it is present as a plain file). When the activation
    # file itself is the broken entry, the enumeration above already said so.
    if not any(entry.name == allowed and (entry.is_indirection or not entry.is_file) for entry in found or []):
        try:
            review.read_activation()
        except ValidationError as exc:
            problems.append(_problem(exc))
    return problems
