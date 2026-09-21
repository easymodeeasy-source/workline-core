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

P3 activation semantics are not applied. An absent activation record means
review-v1 Work terminalization is not activated, which is the state P1 leaves
every Project in, and no terminal event is classified by anything here.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import ValidationError
from ..store import ProjectStore
from . import paths
from .records import Consumption, GateGeneration, Receipt
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


def validate_review(store: ProjectStore) -> list[ReviewProblem]:
    """Structural problems in this Project's Review namespace; empty when there are none."""
    review = ReviewStore(store)
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
    problems.extend(_provenance(review, chains))
    problems.extend(_activation(review))
    return problems


def _problem(exc: ValidationError) -> ReviewProblem:
    return ReviewProblem(getattr(exc, "code", None) or "review_invalid", str(exc))


def _namespace_shape(review: ReviewStore) -> list[ReviewProblem]:
    """Only the seven known directories, each a plain directory, and nothing else - read without following."""
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


def _receipt_consumption_binding(receipt: Receipt, consumption: Consumption) -> list[ReviewProblem]:
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


def _activation(review: ReviewStore) -> list[ReviewProblem]:
    """The activation record, if present, must parse. P1 creates none and activates nothing."""
    try:
        review.read_activation()
    except ValidationError as exc:
        return [_problem(exc)]
    return []
