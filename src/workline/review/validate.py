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
from . import paths
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
    return review_problems(review) + activation_problems(store, review)


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


def activation_problems(store: ProjectStore, review: ReviewStore) -> list[ReviewProblem]:
    """P3 F1 §10 over this Project's working tree: the activation boundary, and review-v1 totality after it.

    ```text
    no activation record      valid and not activated; no completion is classified
                              by its position, and a review-v1 marker contradicts it
    activation whose prefix   Events 0 .. N-1 are pre-activation legacy and need nothing;
    reproduces                a work_completed at index >= N is
                                without the marker        legacy - no Consumption
                                marked review-v1          bound by exactly one Work
                                                          Consumption that repeats it
                                any other marker          invalid
    activation whose prefix   fails closed: nothing after it is classified
    does not reproduce
    ```

    The prefix is read through the one digest implementation
    (:mod:`workline.review.activation`) over the event log this validation
    reads, so the indexes it classifies are the indexes the digest fixed.

    A one-sided review-v1 state - the event without its Consumption, or the
    Consumption without its event - is valid only while a pending review-v1
    Work START holds the one terminal stage both belong to, with the missing
    half still unapplied (:func:`workline.start_review.recorded_terminal`);
    never because of what the files themselves hold. A malformed record is the
    structural pass's to report, and classifies nothing either way.
    """
    try:
        activation = review.read_activation()
    except ValidationError:
        return []
    events = _event_log(store)
    if activation is None:
        return [] if events is None else _unactivated_markers(events)
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
    return [found for found in (recorded_terminal(record) for record in pending) if found is not None]


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
