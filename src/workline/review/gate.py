"""Opening a gate generation safely: reservation keys, same-run serialization, committability.

Three things stand between "a Review Run needs its next generation" and a
mutation that may write one.

**Reservation keys** (``R2`` §2) are deterministic, so a replay reserves the
same identity rather than allocating a second one. They go through
``Mutation.reserve_id`` like every other kind; Review has no generator of its
own.

**Same-run serialization** (``R2`` §4 / ``R3`` §2) closes the window the Project
lock cannot: the lock serializes live processes, and a crash releases it. A
generation file can therefore exist on disk before the ``applied`` flag that
records making it was saved, and a fresh invocation reading the chain would see
N+1 present and compute N+2 - forking the run. The fix is that every generation
mutation carries a stable scope-only token for its Review Run, so an unfinished
N+1 and a hypothetical N+2 mechanically overlap, and the owner looks for a
pending same-run mutation *before* computing anything.

**Committability** (``R1`` §13) is checked before the first canonical Review
effect is recorded: a Review path the Project's own ignore rules exclude would
be written and then silently not committed, so the operation stops instead.
Workline never edits ignore configuration to make a Review path committable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .. import gitcmd
from ..errors import StopError, ValidationError
from ..store import ProjectStore
from . import paths, records
from .store import ReviewStore


# --------------------------------------------------------------------------- reservation keys

def review_run_key(review_kind: str, target_identity: str) -> str:
    """``review-run:<review_kind>:<target_identity>``."""
    _require_key_part(review_kind, "review_kind")
    _require_key_part(target_identity, "target_identity")
    return f"review-run:{review_kind}:{target_identity}"


def review_receipt_key(review_run_id: str, generation: int) -> str:
    """``review-receipt:<review_run_id>:<generation>``."""
    _require_key_part(review_run_id, "review_run_id")
    if type(generation) is not int or generation < records.FIRST_GENERATION:
        raise ValidationError(f"a Review generation is a positive integer, not {generation!r}", code="review_gate_chain")
    return f"review-receipt:{review_run_id}:{generation}"


def review_consumption_key(receipt_id: str) -> str:
    """``review-consumption:<receipt_id>``.

    Keyed by the Receipt alone, which is what makes "one Receipt, at most one
    Consumption" (``R4`` §1) hold by construction on replay: a second attempt
    to consume the same authorization reserves the identity that already exists.
    """
    _require_key_part(receipt_id, "receipt_id")
    return f"review-consumption:{receipt_id}"


def review_task_key(review_run_id: str, task_slot: str) -> str:
    """``review-task:<review_run_id>:<task-slot>``."""
    _require_key_part(review_run_id, "review_run_id")
    _require_key_part(task_slot, "task_slot")
    return f"review-task:{review_run_id}:{task_slot}"


def _require_key_part(value: object, described: str) -> None:
    if not isinstance(value, str) or not value or ":" in value or value != value.strip():
        raise ValidationError(
            f"a Review reservation key part must be non-empty text without ':' - {described} is {value!r}",
            code="review_record_invalid",
        )


# --------------------------------------------------------------------------- same-run serialization

@dataclass(frozen=True)
class GenerationScope:
    """The exact initial write scope a new generation mutation opens with.

    Both paths, always. The generation file is what the mutation writes; the
    token is what makes any *other* unfinished generation mutation for this run
    collide with it.
    """

    review_run_id: str
    generation: int
    gate_path: str
    token_path: str

    @property
    def files(self) -> list[str]:
        return [self.gate_path, self.token_path]


def pending_generation_mutations(store: ProjectStore, review_run_id: str) -> list[dict[str, Any]]:
    """Pending mutation records that hold this Review Run's serialization token in scope.

    The token is how a generation mutation announces which run it belongs to,
    so this finds them without Review having to know which owners exist or what
    they called their stages.
    """
    from ..mutation import MutationController, WriteScope

    token = paths.serialization_token_rel(review_run_id)
    found: list[dict[str, Any]] = []
    for record in MutationController(store).list_pending():
        scope = WriteScope.from_record(record.get("write_scope") or {})
        if token in scope.files:
            found.append(record)
    return found


def next_generation_scope(store: ProjectStore, review_run_id: str) -> GenerationScope:
    """The scope for this Review Run's next generation, once it is safe to compute one.

    Order is the contract (``R3`` §2), and it is this order because any other
    one reintroduces the fork:

    1. a pending same-run generation mutation must be resumed or reconciled
       first - never stepped over, because its generation may already exist
       physically while its record does not yet say so;
    2. more than one pending same-run mutation is a conflict nobody can resolve
       by choosing, so it is ``reconcile_required``;
    3. only with none pending is the immutable chain validated and N+1 computed.

    The caller opens its mutation with :attr:`GenerationScope.files` as the
    initial ``WriteScope.files`` - both paths - before reserving any ID or
    recording any effect.
    """
    pending = pending_generation_mutations(store, review_run_id)
    if len(pending) > 1:
        ids = ", ".join(sorted(str(record.get("id")) for record in pending))
        raise ValidationError(
            f"Review Run {review_run_id} has {len(pending)} pending generation mutations ({ids}); "
            "which one owns the next generation cannot be decided here: reconcile required",
            code="review_generation_conflict",
        )
    if pending:
        raise ValidationError(
            f"Review Run {review_run_id} has a pending generation mutation ({pending[0].get('id')}); "
            "it is resumed or reconciled before any new generation is calculated",
            code="review_generation_pending",
        )
    generation = ReviewStore(store).next_generation(review_run_id)
    return GenerationScope(
        review_run_id=review_run_id,
        generation=generation,
        gate_path=paths.gate_rel(review_run_id, generation),
        token_path=paths.serialization_token_rel(review_run_id),
    )


# --------------------------------------------------------------------------- git committability preflight

def require_committable(store: ProjectStore, relatives: list[str]) -> None:
    """Refuse to record a Review effect for a path this Project would not commit.

    Asked with Git's own ignore evaluation, before the first canonical Review
    effect of the mutation is recorded. An ignored path would be written and
    then quietly left out of the commit, so the record would exist locally and
    not in the clone-safe state every later proof reads. Undeterminable is a
    STOP for the same reason it is everywhere else: not knowing is not a yes.

    Workline never edits ``.gitignore``, ``.git/info/exclude`` or any other
    ignore configuration to make a Review path committable. That is a decision
    about the Project's own configuration, and it belongs to whoever made it.
    """
    for relative in relatives:
        if not paths.is_review_path(relative):
            continue
        ignored = gitcmd.is_ignored(store.root, relative)
        if ignored is None:
            raise StopError(
                f"git cannot say whether {relative} is ignored, so whether this Review record would reach "
                "the Project's committed state cannot be shown: STOP",
                code="review_committability_unknown",
            )
        if ignored:
            raise StopError(
                f"{relative} is excluded by this Project's ignore rules, so the Review record written there "
                "would never be committed; Workline does not change ignore configuration to make it "
                "committable: STOP",
                code="review_path_ignored",
            )


# --------------------------------------------------------------------------- git persistence boundary

def require_persisted(store: ProjectStore, relatives: list[str]) -> None:
    """Refuse to cross an external-launch boundary until these Review records are committed.

    ``R3`` §10: a gate or provenance fact that will be relied on after clone or
    process loss must have reached canonical tracked local Git state first.
    Writing the file is not enough - a record that exists only in the working
    tree is gone from a fresh clone, and an accepted task whose provenance is
    gone cannot be rerun or retrieved, which is the one thing the canonical
    records exist to make possible.

    Committed means both halves, and neither implies the other: HEAD holds the
    path, *and* the working tree and index do not differ from HEAD there. A file
    HEAD holds but that has since been edited is not the material the clone
    would get.

    Remote-less Projects are valid; this is a *local* Git boundary and asks
    nothing about a remote.
    """
    for relative in relatives:
        held = gitcmd.head_paths(store.root, relative)
        if held is None:
            raise StopError(
                f"git cannot say whether {relative} is committed, so whether this Review record would survive "
                "a clone cannot be shown: STOP",
                code="review_persistence_unknown",
            )
        if relative not in held:
            raise StopError(
                f"{relative} has not reached committed state, so a clone would not have it; the external launch "
                "or terminal boundary that depends on it does not proceed: STOP",
                code="review_not_persisted",
            )
    dirty = gitcmd.changed_against_head(store.root, list(relatives))
    if dirty:
        raise StopError(
            f"{', '.join(sorted(dirty))} differs from what is committed, so the committed Review record is not "
            "the material a clone would reconstruct from: STOP",
            code="review_not_persisted",
        )


# --------------------------------------------------------------------------- settlement

def validate_settlement(
    store: ProjectStore, review_run_id: str, task_id: str, result_digest: str, reviewer_identity: str
) -> dict[str, Any]:
    """Check an arriving reviewer result against what the gate actually accepted.

    ``R3`` §3: a result turning up is not a settlement. Before anything is
    written, the arrival is matched to canonical state - the task must have been
    accepted by this Run, its canonical task input must still be stored and
    still digest to what the acceptance bound, and the reviewer answering must
    be the one the acceptance named. Only then may the owning operation record
    the settlement as the next generation.

    Returns the accepted descriptor the result settles, so the caller writes a
    settlement for a task it has been shown exists rather than one it believes
    in. Every failure is closed:

    ```text
    no chain / task never accepted        -> unknown callback
    already settled with another result   -> conflict
    canonical task input missing          -> cannot be reconstructed
    task input digest moved               -> provenance changed since acceptance
    another reviewer answering            -> identity mismatch
    ```

    An exactly duplicated settlement - same task, same result - is not an error:
    it is the same fact arriving twice, and it returns the same descriptor.
    """
    review = ReviewStore(store)
    chain = review.gate_chain(review_run_id)
    if chain is None:
        raise ValidationError(
            f"a result arrived for Review Run {review_run_id}, which has no gate chain: unknown callback",
            code="review_callback_unknown",
        )
    accepted = chain.accepted_descriptor(task_id)
    accepted_generation = chain.accepted_at(task_id)
    if accepted is None or accepted_generation is None:
        raise ValidationError(
            f"a result arrived for task {task_id}, which Review Run {review_run_id} never accepted: "
            "unknown callback",
            code="review_callback_unknown",
        )
    # Every arrival is matched to canonical provenance first - a duplicate
    # included. The same cross-binding structural validation applies: every
    # identity the accepted descriptor, the stored task input and the stored
    # Candidate snapshot share must agree, not only the task-input digest. A
    # repeat of an earlier result is only "the same fact" if the material it
    # answers is still the material that was accepted.
    problems = review.provenance_problems(accepted, accepted_generation)
    if problems:
        code, message = problems[0]
        raise ValidationError(
            f"the result for task {task_id} cannot be matched to canonical provenance: {message}",
            code=code,
        )
    if reviewer_identity != accepted["reviewer_identity"]:
        raise ValidationError(
            f"task {task_id} was accepted for reviewer {accepted['reviewer_identity']}, and a result arrived from "
            f"{reviewer_identity}",
            code="review_callback_unknown",
        )
    # The chain is a full snapshot, so the latest generation holds every
    # settlement ever recorded for this Run.
    for settled in chain.latest.settled_tasks:
        if str(settled["task_id"]) != task_id:
            continue
        if str(settled["result_digest"]) == result_digest:
            return accepted  # the same fact arriving twice
        raise ValidationError(
            f"task {task_id} is already settled with result {settled['result_digest']}, and a different "
            f"result {result_digest} arrived: reconcile required",
            code="review_callback_conflict",
        )
    return accepted
