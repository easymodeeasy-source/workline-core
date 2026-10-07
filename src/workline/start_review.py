"""START's review-v1 Work path: the entry, the Work Candidate, its Review Run, and the terminal (P3 F1 / F2 / F3 §5.1).

START stays the operation owner. Selecting review-v1 (``start(..., review=WorkReview(...))``)
makes Review a subordinate authorization gate inside START's own operation: START takes
the lock, opens and owns the mutation, runs the executor, decides every Git stage, and opens
the Run's generation mutations under its own lock. Review records what was reviewed and what
was authorized, and progresses nothing (F1 §6.3, F2 §8.3).

This module is START's, not Review's. The records it writes, and what they mean, are
:mod:`workline.review.work_review`'s; the object-driven commits are
:mod:`workline.review.workcommit`'s; ownership is :mod:`workline.review.ownership`'s.

What it implements, in the order F3 §5.1 freezes (steps 1 ... 37):

```text
 1 - 2b  the entry, before the lock: the selector, the platform's immutable create, the
         publication capability where there is a remote, the transform entry refusal
 3       under the lock, before the mutation opens: activation (the F1-D3 marker matrix is START's own)
 4       the mutation opened with both markers                      (START itself)
 5a - 6  normalization, spelling, reserved ownership, containment and the bound witness,
         then the ownership assertion - nothing durable before 6
 7 - 9   completion_precheck, dirty separability, the pinned persistence preflight
 9a      S-c0: the entry events, committed alone, only when uncommitted
10 - 12  the Work Candidate, its snapshot material, the resulting tree, Context v2, and the
         isolated verification of the exact Candidate
13 - 16  generation 1 (accept), the reviewer, generation 2 (settle), the checkout-capability
         decision, and only on "capable" generation 3 (seal, issuing the Receipt)
17 - 24  the RAW lineage, the Consumption id, S-c1 and K1, C-2(K1), the result-proof note, and
         (with a remote) the push-only publication of exactly K1
25 - 35  the one terminal stage (two events, then the Consumption), S-c2 and K2, C-2(K2), the
         terminal-proof note, and (with a remote) the push-only publication of exactly K2
36 - 37  the recorded-completion proof; START returns "completed"
```

Every commit this path makes is ``review-v1-work-local-v2`` and commit-only; the only pushes
are the two push-only publication stages, each of exactly the commit its proof note names,
with its C-2 re-evaluated before it is recorded and again before it is applied (F3 §4.3, §11).
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
import json
from typing import TYPE_CHECKING, Any

from . import gitcmd, gitops
from .errors import ReconcileRequired, StopError, ValidationError, WorklineError
from .mutation import _HELD_BEFORE, _WROTE, Effect, Mutation, MutationController, WriteScope, _last_wrote, abandon_on_stop
from .ops import stage_name
from .review import (
    ancestry,
    attributes,
    checkout,
    closure,
    fsafe,
    gate,
    ownership,
    p4,
    records,
    resulting_tree,
    serialize,
    work_checkout,
    work_context,
    work_invocation,
    work_review,
    work_verify,
    workcommit,
)
from .review import activation as work_activation
from .review import hermetic as hermetic_module
from .review import history
from .review import paths as review_paths
from .review.hermetic import HermeticGit
from .review.committed import CommittedReviewStore
from .review.store import ReviewStore
from .state import ACTIVE, HELD, IN_PROGRESS, UNSTARTED, ProjectView
from .store import WORK_DESIRED_HEADING, WORK_TERMINAL_EVENTS, Entity, Event, ProjectStore

if TYPE_CHECKING:  # pragma: no cover
    from .start import _Session

#: START is the owner of every mutation of this path, generation mutations included (F1 §6.3).
OWNER = "start"
#: What the execution lock's holder description says on the review-v1 path: the static marker, no caller value.
LOCK_DETAILS = {"review_contract": work_review.REVIEW_CONTRACT}
EVENT_LOG = workcommit.EVENT_LOG

#: The generation mutation's stages - the same names the P2 generation mutations use, so the
#: one dispatch that commits them (roadmap_review._finish_generation, C3-1) reads them unchanged.
STAGE_GENERATION = "review-generation"
STAGE_GENERATION_COMMIT = "review-generation-commit"
OPERATION_GENERATION = "review-generation"
#: Generation 4 is the one same-Run invalidation of a sealed Work Run (F4 §11.18.1, §11.18.4); there is no 5.
TRANSITIONS = {1: "accept", 2: "settle", 3: "seal", 4: "invalidate"}
INVALIDATION_GENERATION = 4

#: The mutation runtime metadata a refused authorization is carried in (F3 §7.9.5): never a Review record.
NOTE_SEAL_REFUSAL = "review_seal_refusal"

# --------------------------------------------------------------------------- F4 (RB3-C1): post-commit recovery
#
# Class A replaces the authorization of an exact operation-owned K1 whose normal C-2(K1) no longer holds:
#
#   K1 -> old Run G4 + Supersession(R1) -> successor G1 -> G2 -> G3 + R2 (= K_adopt)
#      -> exact K_adopt published -> terminal stage consuming R2 (result commit K1) -> K_terminal -> published
#
# Class B (unexpected / non-owned content) and Class C (ownership, ref, lineage, complete delta or remote state
# unprovable) are reconcile required. The checkpoint and the adopted-result proof are START mutation runtime
# material: never a canonical Review record, never lifecycle truth (F4 §11.18.3).

#: The durable Class-A checkpoint, recorded before old G4 and validated against committed state on every resume.
NOTE_CLASS_A = "review_work_class_a_checkpoint"
CLASS_A_CONTRACT = "review-v1-work-class-a-checkpoint-v1"
CLASS_A_VERSION = 1
#: The adopted-result proof note: names exact K_adopt, the commit the adopted-result publication publishes.
NOTE_ADOPTED_PROOF = "review_work_adopted_result_proof"
ADOPTED_PROOF_CONTRACT = "review-v1-work-adopted-result-proof-v1"
#: The two Class-A entry causes (F4 §11.3) and the two classes that are always reconcile.
CLASS_A1, CLASS_A2, CLASS_B, CLASS_C = "A1", "A2", "B", "C"
#: What is not Class A for a reason of its own: an incompatible durable effect, an already published K1.
NOT_ELIGIBLE, ESCAPED = "not-eligible", "historical-escape"
#: The reconcile reasons of a post-commit refusal.
REASON_CLASS_A_INELIGIBLE = "review_class_a_ineligible"
REASON_CLASS_B = "review_class_b_unowned_content"
REASON_CLASS_C = "review_class_c_unprovable"
REASON_ALREADY_PUBLISHED = "review_result_already_published"
REASON_DESTINATION_DIVERGENT = "review_destination_divergent"
#: The Supersession / invalidation-evidence / set-aside reason of a Class-A replacement.
CLASS_A_REASON = work_review.INVALIDATION_CLASS_A


# --------------------------------------------------------------------------- small readers


def _head(git: HermeticGit) -> tuple[str, str]:
    """HEAD's full branch ref and the commit it names, through class B. Detached HEAD never reaches here (§7.1.5)."""
    ref = workcommit._head_ref(git)
    if ref is None:
        raise StopError("repository is in detached HEAD state", code="detached_head")
    commit = workcommit.ref_value(git, ref)
    if commit is None:
        raise StopError(f"{ref} names no commit, so a review-v1 Work has no committed base: STOP",
                        code="review_base_uncommitted")
    return ref, commit


def _reconcile(message: str, reason: str | None = None) -> ReconcileRequired:
    return ReconcileRequired(f"{message}: reconcile required", reason=reason)


# --------------------------------------------------------------------------- 1 - 2b: the entry, before the lock


def entry_gate(store: ProjectStore, review: object) -> work_review.WorkReview:
    """F3 §5.1 steps 1, 2a and 2b: everything a review-v1 START refuses before the lock, with nothing written.

    ``review_contract_invalid``  the selector (F1-D1)
    ``review_create_unsupported`` the platform cannot keep an immutable Review create inside the Project
    ``review_git_unsupported``   a Project with a remote on a Git below P2_PUBLICATION_GIT_MIN (§12.4), or
                                 a Git that cannot be shown to honour the attribute pin (§7.7)
    ``review_git_transform``     the attribute source of HEAD - PRE_S_C0_BASE's source - fails the
                                 universal predicate (§7.4, §7.8)
    """
    if work_review.is_p4(review):
        checked: Any = work_review.validate_work_review_p4(review)
    else:
        checked = work_review.validate_work_review(review)
    if not fsafe.immutable_create_supported():
        raise StopError(
            "review-v1 Work writes immutable Review records, which this platform cannot keep inside the Project; "
            "nothing was begun (legacy START is unaffected)",
            code="review_create_unsupported",
        )
    version = gitcmd.running_git_version()
    if not gitcmd.version_meets(version, gitcmd.P2_PUBLICATION_GIT_MIN) and _has_remote(store):
        found = "of unknown version" if version is None else gitcmd.version_text(version)
        raise StopError(
            f"the running Git is {found}; a review-v1 Work START in a Project with a remote needs "
            f"P2_PUBLICATION_GIT_MIN ({gitcmd.version_text(gitcmd.P2_PUBLICATION_GIT_MIN)}) or newer; nothing was begun",
            code="review_git_unsupported",
        )
    git = hermetic_module.enter(store)
    _, head = _head(git)
    attributes.require_work_attribute_source(store, git, head)
    attributes.require_attribute_pin_capability(store, git)
    return checked


def validate_selector(review: object) -> Any:
    """The ``review=`` argument validated as a selector only (F1-D1) - nothing about the Project is asked.

    RB5 (§32.14): what START checks of a Work Formal Review selector that applies
    to no Work of its operation - a single-work START naming a marked
    integration with the Phase Integration Review selector too.
    """
    if work_review.is_p4(review):
        return work_review.validate_work_review_p4(review)
    return work_review.validate_work_review(review)


def _has_remote(store: ProjectStore) -> bool:
    from .destination import ensure_push_destination

    return ensure_push_destination(store) is not None


# --------------------------------------------------------------------------- 3: activation and the marker matrix


@dataclass(frozen=True)
class Activation:
    """The Project's Work-terminal activation, read and proven at entry (F1 §6.4, §10.1)."""

    record: records.WorkTerminalActivation
    record_digest: str

    def binding(self) -> dict[str, str]:
        return work_context.activation_binding(self.record_digest, self.record.activation_base_head)


def require_activation(store: ProjectStore) -> Activation:
    """F1 §6.4: under the lock, before the mutation is opened.

    The activation is the record current HEAD commits, held unchanged by the
    working tree (:func:`workline.review.activation.current_activation`).
    Neither holding one is ``review_not_activated``. One holding a record the
    other does not, or the two holding different bytes, is reconcile required:
    neither "not activated" nor activation. A malformed record or an unknown
    operation contract is the reader's own ``ValidationError``; a prefix digest
    that does not reproduce from HEAD's committed event log fails closed, and
    is never a legacy fallback.
    """
    git = hermetic_module.enter(store)
    _, head = _head(git)
    found = work_activation.current_activation(ReviewStore(store), git, head)
    if found.state == work_activation.NOT_ACTIVATED:
        raise StopError(
            "this Project has not activated review-v1 Work terminalization, so a review-v1 START is refused; nothing "
            "was begun (legacy START is unaffected)",
            code="review_not_activated",
        )
    record = found.record
    if record is None:
        raise _reconcile(f"{found.conflict()}; nothing was begun")
    digest = work_activation.committed_prefix_digest(git, head, record.legacy_event_count)
    if digest is None or digest != record.legacy_event_prefix_sha256:
        raise _reconcile(
            f"the activation record's legacy event prefix ({record.legacy_event_count} Events) does not reproduce from "
            f"{head}'s committed event log, so which Events are pre-activation cannot be shown; nothing was begun"
        )
    return Activation(record, serialize.digest(record.to_record()))


def invocation(work_id: str, mode: str) -> dict[str, Any]:
    """F1-D2: the live invocation plus exactly the two markers, written at the intent's first durable write."""
    return {"operation": "start", "work_id": work_id, "mode": mode, **work_invocation.markers()}


# --------------------------------------------------------------------------- commit-only stages (F3 §4.3)


def commit_stage(session: "_Session", prefix: str, message: str, *, plan_class: str = workcommit.CLASS_WORK_STAGE) -> None:
    """A review-v1 Work Git stage: exactly one ``review-v1-work-local-v2`` commit, never a push (F3 §4.3, §11.3).

    What it commits is decided by the plan - the parent object plus the
    effects this mutation recorded since its last commit - never by what the
    working tree holds, and nothing is recorded when the plan changes nothing.
    """
    mutation = session.mutation
    stage = stage_name(mutation, prefix)
    if not mutation.has_stage(stage):
        effect = workcommit.stage_commit_effect(mutation, message, plan_class=plan_class)
        if effect is None:
            return
        gitops.ensure_separable(gitops.record_preexisting_dirty(mutation, session.store.root), list(effect.payload["paths"]))
        mutation.add_effects(stage, [effect])
    mutation.apply()


# --------------------------------------------------------------------------- the declared base (F2 §5.3)


def committed_view_at(store: ProjectStore, git: HermeticGit, commit: str) -> ProjectView:
    """``ProjectView`` as of ``commit``, read from raw blobs through class B by the production loader.

    The same materialization :mod:`workline.committed_view` performs, with every
    Git read in the hermetic class B environment, so a replacement object or an
    inherited ``GIT_*`` variable cannot stand in for the base the Candidate
    declares (F3 §7.1.9).
    """
    import secrets
    import shutil

    from .committed_view import is_materialized_path

    tree = resulting_tree.root_tree_id(git, commit)
    entries = resulting_tree.tree_entries(git, tree)
    directory = store.root / review_paths.RUNTIME_PROOFS_DIR / secrets.token_hex(8)
    directory.mkdir(parents=True, exist_ok=False)
    try:
        for path, entry in entries.items():
            if not is_materialized_path(path):
                continue
            if entry.type != "blob" or entry.mode != "100644":
                raise StopError(f"{commit} holds {path} as {entry.type} {entry.mode}, not a regular file blob",
                                code="review_base_uncommitted")
            blob = git.run_bytes("cat-file", "blob", entry.oid)
            if not blob.ok:
                raise StopError(f"Git cannot read the blob {entry.oid} {commit} holds at {path}",
                                code="review_base_uncommitted")
            target = directory.joinpath(*path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob.stdout)
        return ProjectView.load(ProjectStore(directory))
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def declared_base(store: ProjectStore, git: HermeticGit, base_commit: str, branch: str, work_id: str) -> dict[str, Any]:
    """F2 §5.3, read from the committed state of ``base_commit`` through the canonical loader, never the working tree.

    The Work's desired state is its canonical body section (``WORK_DESIRED_HEADING``), read as
    planning reads it: a Work's frontmatter has no desired-state key.
    """
    from .start import read_obligations

    view = committed_view_at(store, git, base_commit)
    work = view.works.get(work_id)
    if work is None:
        raise StopError(f"{work_id} is not in {base_commit}'s committed state, so the Candidate has no declared base",
                        code="review_base_uncommitted")
    tracked = sorted(path for path, entry in resulting_tree.tree_entries(git, resulting_tree.root_tree_id(git, base_commit)).items()
                     if entry.type == "blob")
    dependencies = sorted(view.relations_to(work_id, "requires_completion"), key=lambda relation: relation.id)
    obligations = sorted(read_obligations(store, view, work_id, tracked=tracked), key=lambda relation: relation.id)
    return {
        "base_commit": base_commit,
        "branch": branch,
        "work": {
            "work_id": work_id,
            "display": work.display,
            "name": work.name,
            "desired_state": work.section(WORK_DESIRED_HEADING),
            "phase_id": work.phase_id,
            "state": view.work_state(work_id).state,
        },
        "dependencies": [
            {"relation_id": relation.id, "from": relation.from_id, "from_state": view.entity_state_label(relation.from_id)}
            for relation in dependencies
        ],
        "read_obligations": [{"relation_id": relation.id, "type": relation.type, "to": relation.to} for relation in obligations],
    }


# --------------------------------------------------------------------------- the Run's identity and state


@dataclass
class WorkRun:
    """The Work Review Run of this START's one completion, and the identifiers it reserved."""

    work_id: str
    review_run_id: str
    task_id: str
    receipt_id: str
    #: The freeze's material, present only between a new Run's freeze and its generation 1.
    frozen: dict[str, Any] | None = None
    #: The Run it replaces, for the one F4 Class-A successor (F4 §11.18.5); None for a first Run.
    predecessor_review_run_id: str | None = None
    #: generation -> the exact commit its generation mutation made, as C-1 owned it (this process only).
    generation_commits: dict[int, str] = field(default_factory=dict)
    #: The explicit Review contract of the Run: ``None`` for v1 (F3 / F4), the Work P4 contract for P4.
    contract: str | None = None
    #: P4 only: every record path of this START's P4 cycle - the own-Review set of L-2 (filled where a store is read).
    own_paths: tuple[str, ...] = ()


def run_key(work_id: str) -> str:
    return gate.review_run_key(work_review.REVIEW_KIND, work_id)


def reserve_run(mutation: Mutation, work_id: str) -> WorkRun:
    run_id = mutation.reserve_id(run_key(work_id), "review_run")
    task_id = mutation.reserve_id(gate.review_task_key(run_id, work_review.TASK_SLOT), "review_task")
    receipt_id = mutation.reserve_id(gate.review_receipt_key(run_id, work_review.SEAL_GENERATION), "review_receipt")
    return WorkRun(work_id, run_id, task_id, receipt_id)


def reserve_successor(mutation: Mutation, predecessor: WorkRun) -> WorkRun:
    """The one direct successor of ``predecessor`` (F4 §11.18.5): reserved once, read back by every replay.

    Keyed by the exact predecessor Run (:func:`workline.review.gate.review_successor_run_key`); the
    successor's task and Receipt use the ordinary per-Run keys, so a replay that stopped half way reserves
    exactly the identifiers that are missing and changes none that exist. The first-Run key is untouched.
    """
    run_id = mutation.reserve_id(gate.review_successor_run_key(predecessor.review_run_id), "review_run")
    if run_id == predecessor.review_run_id:
        raise _reconcile(f"START mutation {mutation.id} holds Work Review Run {run_id} as its own successor")
    task_id = mutation.reserve_id(gate.review_task_key(run_id, work_review.TASK_SLOT), "review_task")
    receipt_id = mutation.reserve_id(gate.review_receipt_key(run_id, work_review.SEAL_GENERATION), "review_receipt")
    return WorkRun(predecessor.work_id, run_id, task_id, receipt_id,
                   predecessor_review_run_id=predecessor.review_run_id)


#: The states the recovery selector tells apart (F4 §26.4).
STATE_INITIAL = "initial"                      # the first Run, no Class-A checkpoint
STATE_CHECKPOINTED = "class_a_checkpointed"    # checkpoint durable; old G4 not yet committed
STATE_OLD_INVALIDATED = "old_invalidated"      # old G4 + Supersession committed; no successor reserved
STATE_SUCCESSOR_RESERVED = "successor_reserved"  # successor reserved, its generation 1 not yet begun
STATE_SUCCESSOR_REVIEWING = "successor_reviewing"  # successor generation 1 or 2 (or one pending)
STATE_SUCCESSOR_SEALED = "successor_sealed"    # successor generation 3 + R2: ready for adopted-result publication


@dataclass(frozen=True)
class InFlight:
    """What a resumed review-v1 START continues, read from its own reservations, notes and the canonical chains."""

    state: str
    initial: WorkRun
    successor_review_run_id: str | None = None


@dataclass(frozen=True)
class Adoption:
    """A Class-A replacement in progress, continued from its durable checkpoint (F4).

    Deliberately not a :class:`Sealed`: once the checkpoint exists, the first
    Run's Receipt is on its way to supersession and is never offered as a
    current authorization again.
    """

    initial: WorkRun


def _reserved_run(mutation: Mutation, work_id: str, run_id: str) -> WorkRun:
    task_id = mutation.reserved(gate.review_task_key(run_id, work_review.TASK_SLOT))
    receipt_id = mutation.reserved(gate.review_receipt_key(run_id, work_review.SEAL_GENERATION))
    if not isinstance(task_id, str) or not isinstance(receipt_id, str):
        raise _reconcile(f"START mutation {mutation.id} holds Work Review Run {run_id} without its task or Receipt id")
    return WorkRun(work_id, run_id, task_id, receipt_id)


def _successor_keys(reserved: dict[str, Any]) -> list[str]:
    return sorted(str(key) for key in reserved if str(key).startswith(gate.SUCCESSOR_RUN_KEY_PREFIX))


def select_in_flight(mutation: Mutation) -> InFlight | None:
    """The one recovery selector of a resumed review-v1 START (F4 §26.4); None before generation 1 exists.

    Read from the mutation's own reservations, its Class-A checkpoint and the
    canonical chains - never from recency, HEAD or a commit message:

    ```text
    no checkpoint, no successor          the first Run, as F3 continues it (initial)
    checkpoint, first Run sealed / G4    class_a_checkpointed (G4 not committed) | old_invalidated
    pending
    checkpoint + the one successor       successor_reserved | successor_reviewing | successor_sealed
    reserved
    ```

    A successor without the checkpoint that alone selects one, a successor
    keyed by another Run, a successor of the successor (no recursive Class A),
    a successor reserved before the first Run's generation 4 is committed, or a
    successor chain past generation 3, is reconcile required.
    """
    if is_p4_mutation(mutation):
        return select_in_flight_p4(mutation)
    reserved = mutation.record.get("reserved_ids") or {}
    prefix = f"review-run:{work_review.REVIEW_KIND}:"
    keys = [key for key in reserved if str(key).startswith(prefix)]
    if not keys:
        return None
    if len(keys) > 1:
        raise _reconcile(f"START mutation {mutation.id} reserved more than one Work Review Run ({sorted(keys)})")
    work_id = keys[0][len(prefix):]
    run_id = mutation.reserved(keys[0])
    if not isinstance(run_id, str):
        return None
    checkpoint = mutation.note(NOTE_CLASS_A)
    successors = _successor_keys(reserved)
    store = mutation.store
    if checkpoint is None:
        if successors:
            raise _reconcile(f"START mutation {mutation.id} reserves a successor Work Review Run ({successors}) without "
                             "the Class-A checkpoint that alone selects one")
        if not _begun(store, run_id):
            return None
        return InFlight(STATE_INITIAL, _reserved_run(mutation, work_id, run_id))
    initial = _reserved_run(mutation, work_id, run_id)
    if not isinstance(checkpoint, dict) or checkpoint.get("old_review_run_id") != run_id:
        raise _reconcile(f"START mutation {mutation.id}'s Class-A checkpoint does not name its first Work Review Run "
                         f"{run_id}")
    old_chain = _chain(store, initial)
    old_pending = gate.pending_generation_mutations(store, run_id)
    if old_chain is None or old_chain.latest.generation not in (work_review.SEAL_GENERATION, INVALIDATION_GENERATION):
        raise _reconcile(f"Work Review Run {run_id} is neither sealed nor invalidated under a Class-A checkpoint")
    if not successors:
        if old_chain.latest.generation == INVALIDATION_GENERATION and not old_pending:
            return InFlight(STATE_OLD_INVALIDATED, initial)
        return InFlight(STATE_CHECKPOINTED, initial)
    if successors != [gate.review_successor_run_key(run_id)]:
        raise _reconcile(f"START mutation {mutation.id} reserves {successors}, not exactly the one successor of "
                         f"{run_id}; a predecessor has at most one successor and a successor has none",
                         REASON_CLASS_A_INELIGIBLE)
    successor_id = mutation.reserved(successors[0])
    if not isinstance(successor_id, str) or successor_id == run_id:
        raise _reconcile(f"START mutation {mutation.id} holds no usable successor of {run_id}")
    if old_chain.latest.generation != INVALIDATION_GENERATION or old_pending:
        raise _reconcile(f"successor {successor_id} is reserved while {run_id}'s generation 4 is not committed")
    successor_chain = _chain(store, WorkRun(work_id, successor_id, "", ""))
    if gate.pending_generation_mutations(store, successor_id):
        return InFlight(STATE_SUCCESSOR_REVIEWING, initial, successor_id)
    if successor_chain is None:
        return InFlight(STATE_SUCCESSOR_RESERVED, initial, successor_id)
    latest = successor_chain.latest.generation
    if latest in (1, 2):
        return InFlight(STATE_SUCCESSOR_REVIEWING, initial, successor_id)
    if latest == work_review.SEAL_GENERATION:
        return InFlight(STATE_SUCCESSOR_SEALED, initial, successor_id)
    raise _reconcile(f"successor Work Review Run {successor_id} has generation {latest}; a successor is never invalidated "
                     "or replaced again (no recursive Class A)", REASON_CLASS_A_INELIGIBLE)


def _begun(store: ProjectStore, run_id: str) -> bool:
    """Whether a reserved Work Review Run has begun: its generation 1 exists, or a generation mutation of it is pending."""
    return bool(gate.pending_generation_mutations(store, run_id)) or ReviewStore(store).next_generation(run_id) > 1


@contextmanager
def abandon_unbegun_on_stop(mutation: Mutation):
    """A review-v1 START's STOP guard: abandon the mutation only when it recorded no effect AND began no Run.

    ``mutation.abandon_on_stop`` abandons on "no effect" alone. A START on a
    Work already in progress with its target records no lifecycle effect
    before its review, so a STOP after its Work Review Run began - a reviewer
    error at generation 1, a settlement that does not authorize - would abandon
    the one record that can resume that Run, and every later START would find
    the Run held by no pending START: incomplete (``recovery.discover_work``).
    The Work Review Policy's ``error_disposition`` ("no settlement; the same
    task is launched again by the next run") and F4 §11.16 (an interruption at
    reviewer launch or settlement resumes, with no new Candidate) keep it
    pending instead: the next START opens it again and :func:`select_in_flight`
    continues the same Run. A STOP before any Run began abandons exactly as
    before. Whether a Run began is read as :func:`select_in_flight` reads it,
    and a record whose Runs cannot be read is kept, never abandoned.
    """
    try:
        yield mutation
    except StopError:
        if mutation.status == "pending" and not mutation.effects and not _holds_begun_run(mutation):
            mutation.abandon()
        raise


def _holds_begun_run(mutation: Mutation) -> bool:
    try:
        return any(_begun(mutation.store, run_id)
                   for run_id in sorted(own_run_ids(mutation.record.get("reserved_ids") or {})))
    except (WorklineError, OSError):
        return True


def run_in_flight(mutation: Mutation) -> WorkRun | None:
    """The first Run this START already began, when that is what it continues (F3 §5.4); None otherwise.

    The F3 reading, kept for readers that only ask about the first Run: a Run
    whose generation 1 is committed (or whose generation mutation is pending)
    is continued from its records and never frozen again. Which state a
    resumed START is in - including every F4 Class-A state - is
    :func:`select_in_flight`'s.
    """
    selected = select_in_flight(mutation)
    return None if selected is None or selected.state != STATE_INITIAL else selected.initial


def continue_selected(session: "_Session", selected: InFlight) -> "Sealed | Adoption":
    """Continue what :func:`select_in_flight` selected: the first Run as F3 does, or the Class-A replacement."""
    if selected.state == STATE_P4:
        return _continue_p4(session, selected.initial)
    if selected.state == STATE_INITIAL:
        return _continue(session, selected.initial)
    return Adoption(selected.initial)


# --------------------------------------------------------------------------- §11.12: every invocation, every matching Run


def own_run_ids(reserved: dict[str, Any]) -> set[str]:
    """The Work Review Runs one START record reserved: its first Run and its Class-A successor."""
    prefix = f"review-run:{work_review.REVIEW_KIND}:"
    return {
        str(value) for key, value in reserved.items()
        if value and (str(key).startswith(prefix) or str(key).startswith(gate.SUCCESSOR_RUN_KEY_PREFIX))
    }


def recovery_discovery(store: ProjectStore, work_id: str, held: set[str]) -> Any:
    """Canonical recovery discovery for one review-v1 Work Review invocation (F4 §11.12); it writes nothing.

    Every Run with this Work's review kind and operation identity - which has
    no mutation id, time or mode in it, so a Run another START of the same Work
    began is one of them - is proven and classified, never chosen by recency.
    ``held`` are the Runs the pending START mutations of this Work reserved
    (once this invocation's mutation is open, exactly its own: opening refuses
    any other pending START of the Work). A Work Run is resumed only through
    the START mutation that reserved it, so the held Runs are their selectors'
    (:func:`select_in_flight`) and are not classified here, and every OTHER
    matching Run must be one this invocation does not resume - consumed,
    invalidated, not_authorized, set_aside or stale:

    ```text
    another Run of a recoverable shape (generation 1 or an       review_recovery_incomplete: no pending
    authorizing generation 2 with a current Context, or sealed)  START holds what its resumption needs
    another Run incomplete / contradictory                       review_recovery_incomplete
    ```

    No other Run can be recoverable here (``recovery.discover_work``: a Run is
    recoverable only while one of ``held`` holds it), so the selection is the
    selector's own Run when there is one and a new Run otherwise. The Discovery
    returned names, in ``set_aside``, every other matching Run and the reason
    it is not resumed - what a new Run's request names (§11.6).
    """
    from .review import recovery

    return recovery.discover_work(store, work_review.operation_identity(work_id), currency=_recovery_currency(store),
                                  owned=held, held=held)


def entry_recovery(store: ProjectStore, work_id: str) -> None:
    """§11.12 at a review-v1 START's entry: after activation, before the mutation is opened, writing nothing.

    The Runs held by pending START mutations of this Work are excluded: the one
    whose invocation is this one is resumed by opening it, and its selector
    continues its own Run (§11.12: the one recoverable Run is resumed); any
    other - another mode - is reported when the mutation is opened, as the
    existing write-scope conflict, before anything is reserved, so no Run
    begins beside a Run another START holds. Every other matching Run is
    classified by :func:`recovery_discovery`, so a refusing invocation
    reserves, records and writes nothing and never runs the executor. An
    unreadable recovery area is reported where it always was, when the
    mutation is opened.
    """
    try:
        pending = MutationController(store).list_pending()
    except ReconcileRequired:
        return
    held: set[str] = set()
    for record in pending:
        found = record.get("invocation")
        if (record.get("owner") == OWNER and isinstance(found, dict) and found.get("operation") == "start"
                and found.get("work_id") == work_id):
            held |= own_run_ids(record.get("reserved_ids") or {})
    recovery_discovery(store, work_id, held)


# --------------------------------------------------------------------------- generation mutations (R3, C3-1)


def _generation_invocation(mutation: Mutation, run: WorkRun, generation: int, gate_record: records.GateGeneration,
                           receipt_id: str | None, basis: str, branch: str, transition: str | None = None) -> dict[str, Any]:
    return {
        "operation": OPERATION_GENERATION,
        "review_contract": work_review.REVIEW_CONTRACT if run.contract is None else run.contract,
        "start_mutation_id": mutation.id,
        "review_kind": work_review.REVIEW_KIND,
        "review_run_id": run.review_run_id,
        "generation": generation,
        "transition": TRANSITIONS[generation] if transition is None else transition,
        "candidate_hash": gate_record.candidate_hash,
        "review_context_hash": gate_record.review_context_hash,
        "effective_policy_hash": gate_record.effective_policy_hash,
        "obligation_digest": gate_record.obligation_digest,
        "receipt_id": receipt_id,
        "persistence_basis": basis,
        "persistence_branch": branch,
    }


def _finish_generation(store: ProjectStore, gen: Mutation) -> str:
    """The one generation dispatch (``F3`` §7.1.7, C3-1): its durable ``review_kind`` selects the Work primitive.

    Returns the exact commit the generation mutation made, as C-1 owns it - the
    commit :func:`workline.review.workcommit.require_generation_persisted` has
    just proven (F4 §26.28 P3) - read from the mutation's own record.
    """
    from .roadmap_review import _finish_generation as finish

    finish(store, gen)
    return workcommit.generation_commit_of(gen)[0]


def _start_generation(
    session: "_Session", run: WorkRun, generation: int, gate_record: records.GateGeneration,
    extra: list[tuple[str, dict[str, Any]]], base: dict[str, Any], *, receipt_id: str | None = None,
    transition: str | None = None,
) -> str:
    """Open, record, commit and prove persisted the generation mutation writing ``gate_record`` (and ``extra``).

    ``transition`` is given by the P4 flow only (its generations 5 and 6 each have two shapes); an accept writes
    its TaskInput(s) before the gate that names them. A v1 generation keeps its exact invocation.
    """
    store, mutation = session.store, session.mutation
    scope = gate.next_generation_scope(store, run.review_run_id)
    if scope.generation != generation:
        raise _reconcile(
            f"Work Review Run {run.review_run_id}'s next generation is {scope.generation}, and START is at generation "
            f"{generation}",
            "review_chain_invalid",
        )
    writes = [(scope.gate_path, gate_record.to_record())] + list(extra)
    if generation == records.FIRST_GENERATION or transition == p4.TRANSITION_ACCEPT:
        writes = list(extra) + [(scope.gate_path, gate_record.to_record())]
    invocation_record = _generation_invocation(mutation, run, generation, gate_record, receipt_id, base["base_commit"],
                                               base["branch"], transition)
    record_paths = [path for path, _ in writes]
    gen = MutationController(store).open(OWNER, invocation_record,
                                         WriteScope(files=tuple(scope.files) + tuple(path for path, _ in extra)))
    with abandon_on_stop(gen):
        gitops.record_preexisting_dirty(gen, store.root)
        gitops.ensure_separable_before_effects(gen, record_paths)
        if not gen.has_stage(STAGE_GENERATION):
            gate.require_committable(store, record_paths)
            gen.add_effects(STAGE_GENERATION, [
                Effect.create_file(path, serialize.canonical_text(record)) for path, record in writes
            ])
    commit = _finish_generation(store, gen)
    run.generation_commits[generation] = commit
    return commit


def resolve_pending_generation(session: "_Session", run: WorkRun) -> None:
    """R2 §4: a pending generation mutation of this Run is resumed first, and nothing else is."""
    store, mutation = session.store, session.mutation
    pending = gate.pending_generation_mutations(store, run.review_run_id)
    if not pending:
        return
    if len(pending) > 1:
        raise _reconcile(f"Work Review Run {run.review_run_id} has {len(pending)} pending generation mutations",
                         "review_generation_owner_conflict")
    record = pending[0]
    found = record.get("invocation") or {}
    if (
        record.get("owner") != OWNER
        or found.get("operation") != OPERATION_GENERATION
        or found.get("review_kind") != work_review.REVIEW_KIND
        or found.get("start_mutation_id") != mutation.id
        or found.get("review_run_id") != run.review_run_id
    ):
        raise _reconcile(
            f"the pending generation mutation {record.get('mutation_id')} of Work Review Run {run.review_run_id} is not "
            f"this START mutation's ({mutation.id})",
            "review_generation_owner_conflict",
        )
    gen = MutationController(store).open(OWNER, found, WriteScope.from_record(record.get("write_scope") or {}))
    if not gen.effects:
        gen.abandon()
        return
    generation = found.get("generation")
    try:
        chain = ReviewStore(store).gate_chain(run.review_run_id)
    except ValidationError as exc:
        raise _reconcile(f"Work Review Run {run.review_run_id}'s chain does not validate: {exc}", "review_chain_invalid") from exc
    recorded = {effect["payload"]["path"]: effect["payload"]["content"] for effect in gen.stage_effects(STAGE_GENERATION)}
    next_number = records.FIRST_GENERATION if chain is None else chain.next_generation
    fits = generation == next_number
    if not fits and chain is not None and generation == chain.latest.generation:
        gate_path = review_paths.gate_rel(run.review_run_id, int(generation))
        stored = ReviewStore(store).read_bytes(gate_path)
        fits = stored is not None and gate_path in recorded and stored == recorded[gate_path].encode("utf-8")
    if found.get("review_contract") == work_review.P4_CONTRACT:
        allowed = p4.TRANSITIONS.get(int(generation), ()) if type(generation) is int else ()
    else:
        allowed = (TRANSITIONS.get(generation),)
    if not fits or found.get("transition") not in allowed:
        raise _reconcile(
            f"the pending generation mutation {gen.id} writes generation {generation} ({found.get('transition')}) of "
            f"Work Review Run {run.review_run_id}, which is not the chain's next transition",
            "review_chain_invalid",
        )
    run.generation_commits[int(generation)] = _finish_generation(store, gen)


def _chain(store: ProjectStore, run: WorkRun):
    try:
        return ReviewStore(store).gate_chain(run.review_run_id)
    except ValidationError as exc:
        raise _reconcile(f"Work Review Run {run.review_run_id}'s chain does not validate: {exc}", "review_chain_invalid") from exc


def _require_shape(run: WorkRun, chain: Any) -> None:
    """The chain is one of the shapes a Work Run has: accepted, settled, sealed - or invalidated at generation 4.

    Generation 4 is exactly the F4 same-Run invalidation of the seal (open, no
    Receipt, no authorized stage, every accepted and settled task carried
    forward); it is the last generation a Work Run ever has, so a fifth one is
    refused (F4 §11.18.4, §26.12).
    """
    generations = chain.generations
    problems: list[str] = []
    if len(generations) > INVALIDATION_GENERATION:
        problems.append("more than four generations (a Work Run has no generation 5)")
    first = generations[0]
    if first.review_kind != work_review.REVIEW_KIND or first.target_identity != run.work_id:
        problems.append("generation 1 is not a Work Review of this Work")
    if first.status != records.GATE_STATUS_OPEN or len(first.accepted_tasks) != 1 or first.settled_tasks:
        problems.append("generation 1 is not one accepted, unsettled task")
    if first.accepted_tasks and str(first.accepted_tasks[0]["task_id"]) != run.task_id:
        problems.append("generation 1 accepts another task than the reserved one")
    if len(generations) >= 2 and (generations[1].status != records.GATE_STATUS_OPEN or len(generations[1].settled_tasks) != 1):
        problems.append("generation 2 is not an open settlement")
    if len(generations) >= 3 and (not generations[2].sealed or generations[2].receipt_id != run.receipt_id
                                  or generations[2].authorized_operation_stage != work_review.AUTHORIZED_OPERATION_STAGE):
        problems.append("generation 3 is not the seal issuing the reserved Receipt for start:work-terminal")
    if len(generations) >= 4:
        third, fourth = generations[2], generations[3]
        if (fourth.status != records.GATE_STATUS_OPEN or fourth.receipt_id is not None
                or fourth.authorized_operation_stage is not None or fourth.accepted_tasks != third.accepted_tasks
                or fourth.settled_tasks != third.settled_tasks):
            problems.append("generation 4 is not the open invalidation of the seal")
    if problems:
        raise _reconcile(f"Work Review Run {run.review_run_id}: " + "; ".join(problems), "review_chain_invalid")


# --------------------------------------------------------------------------- the Run's durable material


@dataclass(frozen=True)
class RunMaterial:
    """What generation 1 made durable, read back from the canonical records and never from memory (F3 §5.3)."""

    task_input: records.TaskInput
    reconstruction: work_review.Reconstruction
    context: dict[str, Any]

    @property
    def candidate(self) -> dict[str, Any]:
        return self.reconstruction.candidate

    @property
    def base(self) -> dict[str, Any]:
        return self.reconstruction.candidate["declared_base"]

    @property
    def content(self) -> dict[str, Any]:
        return work_review.content_of(self.reconstruction.candidate)


def run_material(store: ProjectStore, run: WorkRun, chain: Any) -> RunMaterial:
    """The accepted task, the exact Candidate with its payloads, and the bound Context - every cross-check applied."""
    review = ReviewStore(store)
    first = chain.generations[0]
    descriptor = first.accepted_tasks[0]
    problems = review.provenance_problems(descriptor, 1)
    if problems:
        raise _reconcile("the accepted task's provenance: " + "; ".join(message for _, message in problems),
                         "review_task_invalid")
    task_input = review.read_task_input(run.task_id)
    snapshot = review.read_candidate_snapshot(first.candidate_hash)
    material = snapshot.material or {}
    width = len(str((material.get("candidate") or {}).get("declared_base", {}).get("base_commit", "")))
    if width not in (40, 64):
        raise _reconcile("the stored Candidate names no declared base of a known object width")
    reconstruction = work_review.read_material(snapshot, first.candidate_hash, width)
    envelope_problems = work_review.task_input_problems(
        task_input, material, first.candidate_hash, first.review_context_hash, first.effective_policy_hash,
        review_run_id=run.review_run_id,
    )
    if envelope_problems:
        raise _reconcile("the accepted task's request: " + "; ".join(envelope_problems), "review_task_invalid")
    return RunMaterial(task_input, reconstruction, dict(task_input.request_envelope["context"]))


# --------------------------------------------------------------------------- 5a ... 16: the completion under review


@dataclass(frozen=True)
class Sealed:
    """A sealed Work Review Run: the Receipt authorizes this exact Candidate for start:work-terminal."""

    run: WorkRun
    material: RunMaterial
    chain: Any


def freeze_and_review(session: "_Session", view: ProjectView, work: Entity, outcome: Any) -> Sealed:
    """F3 §5.1 steps 5a ... 16 for a Completed outcome; the sealed Run, or a STOP."""
    from .start import _result_message, completion_precheck

    if work_review.is_p4(session.review):
        return freeze_and_review_p4(session, view, work, outcome)
    store, mutation = session.store, session.mutation
    # F4 §11.12 / §11.6: every other matching Run classified (it is never resumed here), read before anything of this
    # Run is durable; the new Run's request names each one with the reason it is set aside - none, in the ordinary case
    recovered = recovery_discovery(store, work.id, own_run_ids(mutation.record.get("reserved_ids") or {}))
    set_aside = [dict(item) for item in recovered.set_aside]
    result_paths = tuple(p.replace("\\", "/") for p in outcome.result_paths)  # 5a, unchanged
    deleted_paths = tuple(p.replace("\\", "/") for p in outcome.deleted_paths)
    git = hermetic_module.enter(store)
    branch, pre_base = _head(git)
    # 5b - 5d, over every declared path in their precedence; nothing durable yet
    witnesses = ownership.bind_declarations(store, git, result_paths, deleted_paths, pre_base)
    ownership.assert_ownership(mutation, witnesses)  # 6
    completion_precheck(store, view, work, result_paths, deleted_paths)  # 7
    owned = sorted(set(result_paths) | set(deleted_paths))
    if owned:
        preexisting = gitops.record_preexisting_dirty(mutation, store.root)  # 8
        overlap = sorted(set(preexisting) & set(owned))
        if overlap:
            session._refuse_overlapping_result(work, outcome, overlap, overlap)
        attributes.require_pinned_path_evaluation(store, git, pre_base, owned)  # 9
    commit_stage(session, f"{work.id}:entry", f"chore(workline): enter {work.display}",
                 plan_class=workcommit.CLASS_ENTRY)  # 9a, S-c0 only when the entry events are uncommitted
    branch_after, base_commit = _head(git)
    if branch_after != branch:
        raise _reconcile(f"HEAD left {branch} while the completion of {work.id} was being frozen")
    width = len(base_commit)
    base = declared_base(store, git, base_commit, branch, work.id)
    # 10: the Candidate, from the bound witnesses and base_commit's tree - no pathname is read again
    held = workcommit._tree_entries(git, base_commit, [witness.path for witness in witnesses])
    entries: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    for witness in witnesses:
        old = held.get(witness.path)
        entries.append(work_review.candidate_entry(
            witness.path,
            None if old is None else (old.mode, old.oid),
            witness.kind,
            witness.git_mode,
            None if witness.kind == ownership.KIND_ABSENT else witness.identity,
            witness.material,
            width,
        ))
        if witness.material is not None:
            payloads[witness.path] = witness.material
    content = work_review.content_for(
        entries, message=_result_message(outcome.message, work), base_commit=base_commit,
        declared_result=result_paths, declared_deleted=deleted_paths,
    )
    activation = session.activation
    if activation is None:
        raise _reconcile("a review-v1 START session holds no activation proven at its entry")
    candidate = work_review.candidate_record(content, base, activation.binding())
    material = work_review.snapshot_material(candidate, payloads)  # 11
    snapshot = work_review.snapshot_for(material)
    # 11a, 11b: the resulting tree and the Context v2 - the proof TARGET, never a verdict
    resulting = resulting_tree.resulting_tree_id(
        store, git, base_commit, resulting_tree.entries_from_records(work_review.entries_of(candidate)), payloads
    )
    from .implementation import package_directory

    context = work_context.context_record(
        store.workline_root(), package_directory(store.workline_root()), activation.binding(),
        resulting_tree.root_tree_id(git, pre_base), resulting,
    )
    run = reserve_run(mutation, work.id)
    # 12: the Evidence checks F2 §13.2 names are executed, not assumed: the owned paths still hold
    # exactly what was witnessed (own-bytes), and every existing Review record reads canonically
    # (review-namespace) - then the isolated verification of the exact Candidate, from its
    # clone-safe material alone
    ownership.require_current(store, git, witnesses, pre_base)
    checkout.require_namespace_readable(store)
    reconstruction = work_review.read_material(snapshot, work_review.candidate_hash(candidate), width)
    verified = work_verify.verify(store, git, reconstruction, resulting_tree_id=resulting)
    context_hash = work_context.context_hash(context)
    policy_hash = work_review.policy_hash()
    # F4 §11.18.6: a new Run's request is version 2, naming the older matching Runs it does not resume ([] when none)
    envelope = work_review.request_envelope(candidate, context, set_aside, review_run_id=run.review_run_id)
    task_input = work_review.task_input_for(
        task_id=run.task_id, reviewer_identity=session.review.reviewer_identity,
        reviewer_version=session.review.reviewer_version, envelope=envelope, snapshot=snapshot,
        review_context_hash=context_hash, effective_policy_hash=policy_hash,
    )
    evidence = _evidence(git, candidate, snapshot, task_input, context, context_hash, policy_hash, activation, verified,
                         declared=bool(owned))
    run.frozen = {"snapshot": snapshot, "task_input": task_input, "evidence": evidence, "context": context}
    _accept(session, run, base)  # 13
    session._drop_refused_result(work.id)
    return _continue(session, run)


def _evidence(
    git: HermeticGit, candidate: dict[str, Any], snapshot: records.CandidateSnapshot, task_input: records.TaskInput,
    context: dict[str, Any], context_hash: str, policy_hash: str, activation: Activation, verified: work_verify.Verified,
    *, declared: bool,
) -> dict[str, Any]:
    """F2 §13.2 - §14.3: the checks, the isolated verification and the closure digest, in one Evidence record."""
    base = candidate["declared_base"]
    material_digest = work_review.material_digest(snapshot)
    git_version = gitcmd.version_text(gitcmd.running_git_version() or (0, 0, 0))
    provenance = closure.ReviewProvenance(
        candidate_hash=snapshot.candidate_hash,
        candidate_material_digest=material_digest,
        task_input_digest=serialize.digest(task_input.to_record()),
        request_digest=task_input.request_digest,
        reviewer_identity=task_input.reviewer_identity,
        reviewer_version=task_input.reviewer_version,
        review_context_hash=context_hash,
        effective_policy_hash=policy_hash,
    )
    base_tree = resulting_tree.root_tree_id(git, base["base_commit"])
    declaration = work_review.dependency_declaration(
        entry_identities=work_review.entry_identities(candidate) + work_review.base_identities(candidate),
        base_commit=base["base_commit"],
        branch=base["branch"],
        object_identities=(base_tree, verified.resulting_tree),
        provenance=(
            provenance.candidate_hash, provenance.candidate_material_digest, provenance.task_input_digest,
            provenance.request_digest, provenance.reviewer_identity, provenance.reviewer_version,
            provenance.review_context_hash, provenance.effective_policy_hash,
        ),
        loader_identity=context["loader_identity"],
        git_version=git_version,
    )
    verification = work_review.verification_record(
        candidate_hash_value=snapshot.candidate_hash, candidate_material_digest=material_digest,
        review_context_hash=context_hash, effective_policy_hash=policy_hash,
        dependency_declaration=declaration.identity(), base_commit=base["base_commit"],
        resulting_tree=verified.resulting_tree, verified_entries=verified.verified_entries,
    )
    checks = work_review.check_results(declared)
    validity = work_review.validity_closure(
        base_commit=base["base_commit"], branch=base["branch"], provenance=provenance,
        entry_identities=work_review.entry_identities(candidate), activation_record_digest=activation.record_digest,
        evidence_payload_digest=serialize.digest(work_review.evidence_payload(checks, verification)),
        loader_identity=context["loader_identity"], git_version=git_version, declaration=declaration,
    )
    return work_review.evidence_record(checks, verification, validity.digest())


def _accept(session: "_Session", run: WorkRun, base: dict[str, Any]) -> None:
    """Generation 1: the snapshot, the TaskInput and the accepting gate, in one generation mutation (F3 §5.1 step 13)."""
    frozen = run.frozen or {}
    task_input: records.TaskInput = frozen["task_input"]
    snapshot: records.CandidateSnapshot = frozen["snapshot"]
    descriptor = work_review.accepted_descriptor(task_input)
    gate_one = records.GateGeneration(
        review_run_id=run.review_run_id, generation=1, previous_generation=None, previous_digest=None,
        review_kind=work_review.REVIEW_KIND, target_identity=run.work_id,
        operation_identity=work_review.operation_identity(run.work_id),
        candidate_hash=snapshot.candidate_hash, review_context_hash=work_context.context_hash(frozen["context"]),
        effective_policy_hash=work_review.policy_hash(), evidence_digest=serialize.digest(frozen["evidence"]),
        coverage_digest=serialize.digest(work_review.coverage_record(task_input.task_id, [])),
        raw_report_set_digest=serialize.digest(work_review.report_set_record([])),
        adjudication_digest=serialize.digest(work_review.adjudication_record([])),
        obligation_digest=serialize.digest(work_review.obligations_record([])),
        accepted_tasks=(descriptor,), settled_tasks=(), status=records.GATE_STATUS_OPEN, receipt_id=None,
        authorized_operation_stage=None,
    )
    _start_generation(session, run, 1, gate_one, [
        (review_paths.candidate_snapshot_rel(snapshot.candidate_hash), snapshot.to_record()),
        (review_paths.task_input_rel(task_input.task_id), task_input.to_record()),
    ], base)
    run.frozen = None


def continue_run(session: "_Session", run: WorkRun) -> Sealed:
    """Continue a Run this START already began, from its canonical records (F3 §5.4)."""
    return _continue(session, run)


def _continue(session: "_Session", run: WorkRun) -> Sealed:
    store = session.store
    while True:
        resolve_pending_generation(session, run)
        chain = _chain(store, run)
        if chain is None:
            raise _reconcile(f"Work Review Run {run.review_run_id} has no chain to continue", "review_chain_invalid")
        _require_shape(run, chain)
        latest = chain.latest.generation
        if latest == INVALIDATION_GENERATION:
            raise _reconcile(
                f"Work Review Run {run.review_run_id} is invalidated at generation 4 and its Receipt is superseded; an "
                "invalidated Run is never continued as a current authorization (F4 §11.18.4)",
                "review_chain_invalid",
            )
        material = run_material(store, run, chain)
        if latest == 1:
            _launch_and_settle(session, run, chain, material)
            continue
        if latest == 2:
            if not work_review.authorizes(chain.latest):
                _refuse_seal(session.mutation, run, "not_authorized", None)
                raise _reconcile(
                    f"Work Review Run {run.review_run_id} settled without authorizing the completion of {run.work_id} "
                    "(a declined task or an unresolved HIGH or MID finding); START does not terminalize an unauthorized "
                    "completion, and nothing further is recorded"
                )
            require_capability(session, run, material)  # 15a
            _seal(session, run, chain, material.base)  # 16
            continue
        return Sealed(run, material, chain)


def _launch_and_settle(session: "_Session", run: WorkRun, chain: Any, material: RunMaterial) -> None:
    """Steps 14 - 15: the launch checks, the reviewer, the report, and generation 2."""
    store = session.store
    first = chain.latest
    descriptor = first.accepted_tasks[0]
    task_id = str(descriptor["task_id"])
    gate.require_persisted(store, [
        review_paths.candidate_snapshot_rel(first.candidate_hash),
        review_paths.task_input_rel(task_id),
        review_paths.gate_rel(run.review_run_id, 1),
    ])
    selector = session.review
    if (selector.reviewer_identity, selector.reviewer_version) != (descriptor["reviewer_identity"], descriptor["reviewer_version"]):
        raise StopError(
            f"task {task_id} was accepted for reviewer {descriptor['reviewer_identity']} {descriptor['reviewer_version']}, "
            f"and this invocation names {selector.reviewer_identity} {selector.reviewer_version}; the reviewer is not called",
            code="review_reviewer_mismatch",
        )
    task = work_review.task_from_input(material.task_input)
    try:
        returned = selector.reviewer(task)
    except Exception as exc:
        raise StopError(f"the reviewer raised for task {task_id}: {exc}; nothing is settled", code="review_reviewer_failed") from exc
    report = work_review.report_record(returned, descriptor)
    result_digest = serialize.digest(report)
    from .durable import durable_write_text

    durable_write_text(store.root / review_paths.runtime_report_rel(task_id), serialize.canonical_text(report), tmp_dir=store.tmp)
    gate.validate_settlement(store, run.review_run_id, task_id, result_digest, str(returned.reviewer_identity))
    settled = {"task_id": task_id, "status": work_review.settled_status(report), "result_digest": result_digest,
               "settled_generation": 2}
    pairs = [(settled, report)]
    gate_two = replace(
        first,
        generation=2,
        previous_generation=1,
        previous_digest=chain.latest_digest,
        coverage_digest=serialize.digest(work_review.coverage_record(task_id, [settled])),
        raw_report_set_digest=serialize.digest(work_review.report_set_record([settled])),
        adjudication_digest=serialize.digest(work_review.adjudication_record(pairs)),
        obligation_digest=serialize.digest(work_review.obligations_record(pairs)),
        settled_tasks=(settled,),
    )
    _start_generation(session, run, 2, gate_two, [], material.base)


def require_capability(session: "_Session", run: WorkRun, material: RunMaterial) -> work_checkout.Capability:
    """Step 15a (F3 §7.9.3 - §7.9.5): the capability of EXACTLY ``Context.resulting_tree``, before any generation-3 effect.

    Recomposed from the committed Candidate and its payloads; the Context's
    bound tree is what must be proven. ``unsafe`` or ``unknown`` is the STOP of
    this operation: no generation 3, no Receipt, and generation 2 stays the
    latest, open generation. The refusal is carried in the mutation's runtime
    metadata, never in a Review record.
    """
    store = session.store
    git = hermetic_module.enter(store)
    expected = material.context["review_checkout_capability"]["resulting_tree"]
    entries = resulting_tree.entries_from_records(work_review.entries_of(material.candidate))
    try:
        with resulting_tree.composed(store, git, material.base["base_commit"], entries,
                                     material.reconstruction.payloads) as composition:
            return work_checkout.require_resulting_tree_capability(store, git, composition, expect=expected)
    except StopError as exc:
        if exc.code in ("review_checkout_unsafe", "review_checkout_unknown"):
            _refuse_seal(session.mutation, run, exc.code, expected)
        raise


def _refuse_seal(mutation: Mutation, run: WorkRun, code: str, resulting: str | None) -> None:
    mutation.set_note(NOTE_SEAL_REFUSAL, {
        "review_run_id": run.review_run_id, "generation": 2, "code": code, "resulting_tree": resulting,
    })


def _seal(session: "_Session", run: WorkRun, chain: Any, base: dict[str, Any]) -> None:
    """Step 16: generation 3 and the Receipt, in one generation mutation - reached only on ``capable``."""
    second = chain.latest
    gate_three = replace(
        second, generation=3, previous_generation=2, previous_digest=chain.latest_digest,
        status=records.GATE_STATUS_SEALED, receipt_id=run.receipt_id,
        authorized_operation_stage=work_review.AUTHORIZED_OPERATION_STAGE,
    )
    receipt = records.Receipt(
        receipt_id=run.receipt_id, review_run_id=run.review_run_id, review_generation=3,
        review_kind=second.review_kind, target_identity=second.target_identity,
        operation_identity=second.operation_identity, authorized_candidate_hash=second.candidate_hash,
        review_context_hash=second.review_context_hash, effective_policy_hash=second.effective_policy_hash,
        coverage_hash=second.coverage_digest, adjudication_hash=second.adjudication_digest,
        obligation_digest=second.obligation_digest, unresolved_obligations=0,
        authorized_operation_stage=work_review.AUTHORIZED_OPERATION_STAGE,
    )
    if session.mutation.note(NOTE_SEAL_REFUSAL) is not None:
        session.mutation.set_note(NOTE_SEAL_REFUSAL, None)  # a retry that passes leaves no stale refusal behind
    _start_generation(session, run, 3, gate_three, [(review_paths.receipt_rel(run.receipt_id), receipt.to_record())], base,
                      receipt_id=run.receipt_id)  # a Class-A successor's generation 3 commit is K_adopt (F4 §11.18.2)


# --------------------------------------------------------------------------- 17 ... 37: proof, publication, terminal
#
# After the seal, in the order F3 §5.1 freezes, and each step durable before the next:
#
#   17   lineage precondition (§8.2 L-1 ... L-5, RAW ancestry)
#   17a  the Consumption id reserved              17b  the pinned preflight over S-c1's paths
#   18   S-c1 recorded                            19   K1 made (C-1)
#   20   C-2(K1), W1 ... W12                      21   "review_work_result_proof"
#   22   barrier  23 S-p1 recorded  24 applied: exact K1, C-2 re-evaluated at apply (V-7)
#   25   terminal ids reserved  26 S-t recorded (two events, then the Consumption)  27 applied
#   28   preflight over the terminal paths  29 S-c2 recorded  30 K2 made (C-1)
#   31   C-2(K2), T1 ... T12                      32   "review_work_terminal_proof"
#   33   barrier  34 S-p2 recorded  35 applied: exact K2, C-2 re-evaluated at apply (V-7)
#   36   the recorded-completion proof, P-1 ... P-6
#   37   START returns "completed"; its caller completes the mutation
#
# An empty-artifact Candidate has no K1: 18 ... 24 are absent, and the lineage is measured to
# parent(K2) instead (§6.2, §6.3). With no remote, 22 ... 24 and 33 ... 35 are absent (§20).
# Every step reads what is already durable first, so a resume re-derives and never re-decides.

PROOF_CONTRACT = "review-v1-work-proof-v1"
LINEAGE_CONTRACT = "review-v1-work-lineage-v1"
TERMINAL_CONTRACT = "review-v1-work-terminal-v1"
PUBLICATION_VALIDATOR = "review-v1-work-publication-v1"
NOTE_RESULT_PROOF = "review_work_result_proof"
NOTE_TERMINAL_PROOF = "review_work_terminal_proof"
TERMINAL_EVENTS = ("work_target_removed", "work_completed")
ROLE_RESULT, ROLE_ADOPTED, ROLE_TERMINAL = "result", "adopted-result", "terminal"
#: The operation-contract metadata the work_completed event carries (F1 Gate 1, R4 §5).
OPERATION_CONTRACT = work_context.OPERATION_CONTRACT


def _proof_failed(item: str, detail: str, reason: str | None = None) -> ReconcileRequired:
    return ReconcileRequired(f"{PROOF_CONTRACT} {item} fails: {detail}: reconcile required", reason=reason)


def _lineage_failed(item: str, detail: str) -> ReconcileRequired:
    return ReconcileRequired(
        f"{LINEAGE_CONTRACT} {item} fails: {detail}; the Candidate is not usable on this history and a new one would "
        "have to be frozen: reconcile required",
        reason="review_registration_base_moved",
    )


class CommittedRecords(CommittedReviewStore):
    """P1's strict Review reader over one exact commit, every Git read in class B (F3 §7.1.9).

    ``CommittedReviewStore`` lists and reads with no class B environment, so a
    replacement object could govern what a C-2 item reads. This keeps its whole
    inherited reader - the canonical parse, the record identities, the chain
    invariants - and replaces only its two byte sources with class B reads of
    the stored objects.
    """

    def __init__(self, store: ProjectStore, git: HermeticGit, commit: str) -> None:
        ReviewStore.__init__(self, store)
        self.repo = store.root
        self.commit = commit
        self._git = git
        listed = git.run_bytes("ls-tree", "-r", "-t", "-z", "--full-tree", commit, "--", review_paths.REVIEW_DIR)
        if not listed.ok:
            raise ValidationError(f"Git cannot list the Review records of {commit}", code="review_record_missing")
        tree: dict[str, gitcmd.TreeEntry] = {}
        for item in listed.stdout.split(b"\0"):
            if not item:
                continue
            head, separator, path = item.partition(b"\t")
            fields = head.split(b" ")
            if not separator or len(fields) != 3:
                raise ValidationError(f"Git's listing of {commit} holds a record this reader cannot classify",
                                      code="review_record_invalid")
            mode, kind, oid = (field.decode("ascii", "replace") for field in fields)
            text = path.decode("utf-8", "surrogateescape")
            tree[text] = gitcmd.TreeEntry(mode, kind, oid, text)
        self._tree = tree

    def read_bytes(self, relative: str) -> bytes | None:
        review_paths.require_review_readable_path(relative)
        found = self._tree.get(relative)
        if found is None:
            return None
        if found.type != "blob" or found.mode != "100644":
            raise ValidationError(f"{self.commit} holds {relative} as {found.type} {found.mode}, not a record",
                                  code="review_record_invalid")
        blob = self._git.run_bytes("cat-file", "blob", found.oid)
        if not blob.ok:
            raise ValidationError(f"Git cannot read {found.oid} at {relative} in {self.commit}",
                                  code="review_record_missing")
        return blob.stdout


# --------------------------------------------------------------------------- the durable record, read as a Work START


@dataclass(frozen=True)
class WorkRecord:
    """A review-v1 Work START mutation as its durable record names it: the Work, the Run, the effects.

    ``run`` is the Run whose Receipt the completion consumes: the first Run,
    or - once the Class-A checkpoint and the one successor reservation are both
    durable - that successor, with the first Run as ``initial`` (F4).
    """

    mutation_id: str
    run: WorkRun
    effects: list[dict[str, Any]]
    notes: dict[str, Any]
    reserved: dict[str, Any]
    initial: WorkRun | None = None

    @property
    def work_id(self) -> str:
        return self.run.work_id

    @property
    def adopted(self) -> bool:
        """Whether this completion is a Class-A adoption: its authorizing Run is the successor."""
        return self.initial is not None

    def stages(self) -> list[str]:
        found: list[str] = []
        for effect in self.effects:
            if effect.get("stage") not in found:
                found.append(effect.get("stage"))
        return found

    def stage_effects(self, stage: str) -> list[dict[str, Any]]:
        return [effect for effect in self.effects if effect.get("stage") == stage]

    def one_stage(self, prefix: str) -> str | None:
        """The one recorded stage ``<prefix>:<n>``; None when there is none, reconcile when there are several."""
        found = [stage for stage in self.stages()
                 if isinstance(stage, str) and stage.startswith(prefix + ":") and stage[len(prefix) + 1:].isdigit()]
        if len(found) > 1:
            raise _reconcile(f"START mutation {self.mutation_id} recorded {len(found)} stages {found}; a review-v1 Work "
                             "mutation records each of its Git stages once")
        return found[0] if found else None


def work_record(record: dict[str, Any]) -> WorkRecord:
    """The durable record of a review-v1 Work START mutation, with the Work Review Run that authorizes it.

    The first Run is reserved under the unchanged first-Run key. A Class-A
    successor is the authorizing Run only when the record holds both the
    Class-A checkpoint naming the first Run and exactly the one successor
    reservation keyed by it (F4 §11.18.5): a reservation alone never changes
    which Receipt a completion consumes, and anything else is reconcile.
    """
    if not work_invocation.is_work(record.get("invocation")):
        raise _reconcile(f"mutation {record.get('mutation_id')} is not a review-v1 Work START by its durable invocation")
    reserved = dict(record.get("reserved_ids") or {})
    prefix = f"review-run:{work_review.REVIEW_KIND}:"
    keys = [key for key in reserved if str(key).startswith(prefix)]
    if len(keys) != 1:
        raise _reconcile(f"START mutation {record.get('mutation_id')} holds {len(keys)} Work Review Runs, not one")
    if work_invocation.contract_of(record.get("invocation")) == work_review.P4_CONTRACT:
        # P4: the Run whose Receipt is consumed is the current Run of the cycle; never a Class-A adoption
        p4_work_id = keys[0][len(prefix):]
        runs = _p4_reserved_runs(reserved, p4_work_id)
        current = _p4_work_run(reserved, p4_work_id, runs[-1])
        if not current.task_id or not current.receipt_id:
            raise _reconcile(f"START mutation {record.get('mutation_id')} holds P4 Run {current.review_run_id} without "
                             "its task or Receipt id")
        return WorkRecord(str(record.get("mutation_id")), current,
                          record.get("effects") if isinstance(record.get("effects"), list) else [],
                          record.get("notes") if isinstance(record.get("notes"), dict) else {}, reserved)
    run_id = str(reserved[keys[0]])
    task_id = reserved.get(gate.review_task_key(run_id, work_review.TASK_SLOT))
    receipt_id = reserved.get(gate.review_receipt_key(run_id, work_review.SEAL_GENERATION))
    if not isinstance(task_id, str) or not isinstance(receipt_id, str):
        raise _reconcile(f"START mutation {record.get('mutation_id')} holds Run {run_id} without its task or Receipt id")
    effects = record.get("effects") if isinstance(record.get("effects"), list) else []
    notes = record.get("notes") if isinstance(record.get("notes"), dict) else {}
    work_id = keys[0][len(prefix):]
    first = WorkRun(work_id, run_id, task_id, receipt_id)
    successors = _successor_keys(reserved)
    if not successors:
        return WorkRecord(str(record.get("mutation_id")), first, effects, notes, reserved)
    checkpoint = notes.get(NOTE_CLASS_A)
    if successors != [gate.review_successor_run_key(run_id)] or not isinstance(checkpoint, dict) \
            or checkpoint.get("old_review_run_id") != run_id:
        raise _reconcile(f"START mutation {record.get('mutation_id')} reserves {successors} without exactly the "
                         f"Class-A checkpoint and the one successor of {run_id}")
    successor_id = str(reserved[successors[0]])
    successor_task = reserved.get(gate.review_task_key(successor_id, work_review.TASK_SLOT))
    successor_receipt = reserved.get(gate.review_receipt_key(successor_id, work_review.SEAL_GENERATION))
    if successor_id == run_id or not isinstance(successor_task, str) or not isinstance(successor_receipt, str):
        raise _reconcile(f"START mutation {record.get('mutation_id')} holds successor Run {successor_id} without its "
                         "task or Receipt id")
    successor = WorkRun(work_id, successor_id, successor_task, successor_receipt, predecessor_review_run_id=run_id)
    return WorkRecord(str(record.get("mutation_id")), successor, effects, notes, reserved, initial=first)


def _commit_effect(record: WorkRecord, stage: str | None) -> dict[str, Any] | None:
    if stage is None:
        return None
    found = record.stage_effects(stage)
    if [effect.get("kind") for effect in found] != ["git_commit"]:
        raise _reconcile(f"stage {stage} is not one git_commit")
    return found[0]


def _pre_s_c0_base(record: WorkRecord, base_commit: str) -> str:
    """PRE_S_C0_BASE, from the record: S-c0's exact parent when S-c0 made the declared base, else the base itself."""
    stage = record.one_stage(f"{record.work_id}:entry")
    effect = _commit_effect(record, stage)
    if effect is None:
        return base_commit
    if effect.get("applied") is not True or effect.get("commit_id") != base_commit:
        raise _reconcile("S-c0 did not make the declared base the Candidate names")
    return str(effect["payload"]["base_head"])


def _terminal_stage(record: WorkRecord) -> str | None:
    """The one lifecycle stage of the review-v1 terminal shape (§13.3), or None when none is recorded."""
    found = [stage for stage in record.stages()
             if isinstance(stage, str) and stage.startswith(f"{record.work_id}:lifecycle:")
             and any(e.get("kind") == "create_file" for e in record.stage_effects(stage))]
    if len(found) > 1:
        raise _reconcile(f"START mutation {record.mutation_id} recorded more than one terminal stage")
    return found[0] if found else None


def is_terminal_stage(mutation: Mutation, stage: str, work_id: str) -> bool:
    """IP-3: whether ``stage`` is EXACTLY the review-v1 terminal stage of ``work_id`` (F3 §13.3).

    Two append_event effects in order under the reserved ids - work_target_removed,
    then work_completed carrying the review-v1 operation-contract metadata of
    this Run's Receipt - then exactly one create_file at this Run's Consumption
    path. Any other shape is not a review-v1 completion, and is never read as a
    legacy one either.

    A P5 Run - by the history contract its own stored TaskInputs bind, never by
    the stage's shape (GAP-A) - records the same stage with its Consumption-bound
    Run summary first (§28.6, P-2): one durable unit of four effects.
    """
    return _terminal_shape(mutation.record, stage, work_id, _stored_history_contract(mutation.store, mutation.record))


def _stored_history_contract(store: ProjectStore | None, mutation_record: dict[str, Any]) -> str | None:
    """The history contract the record's authorizing Run stores (GAP-A); ``None`` for v1 / P4-only, or when unread.

    Read from the Run's canonical generation-1 TaskInputs. When they cannot be
    read, nothing P5 is assumed: only the frozen three-effect shape is a
    terminal stage then, so an unproven summary half excuses nothing.
    """
    if store is None:
        return None
    try:
        run = work_record(mutation_record).run
        if run.contract is None:
            return None
        review = ReviewStore(store)
        chain = review.gate_chain(run.review_run_id)
        return None if chain is None else p4.run_history_contract(review, chain)
    except (ReconcileRequired, ValidationError, StopError):
        return None


def _terminal_shape(mutation_record: dict[str, Any], stage: str, work_id: str,
                    history_contract: str | None = None) -> bool:
    """:func:`is_terminal_stage` over a durable mutation record alone, pending or loaded.

    ``history_contract`` is the authorizing Run's stored one: ``None`` is the
    frozen v1 / P4-only shape byte for byte; the P5 shape is that same stage
    preceded by exactly one create at the Run's own summary path.
    """
    try:
        record = work_record(mutation_record)
    except ReconcileRequired:
        return False

    def reserved(key: str) -> str | None:  # exactly ``Mutation.reserved``
        value = (mutation_record.get("reserved_ids") or {}).get(key)
        return str(value) if value else None

    effects = record.stage_effects(stage)
    if history_contract is not None:
        if not effects or effects[0].get("kind") != "create_file" \
                or effects[0]["payload"].get("path") != review_paths.history_run_rel(record.run.review_run_id):
            return False
        effects = effects[1:]
    if [effect.get("kind") for effect in effects] != ["append_event", "append_event", "create_file"]:
        return False
    events = [effect["payload"].get("record") for effect in effects[:2]]
    if not all(isinstance(event, dict) for event in events):
        return False
    if [(event.get("type"), event.get("entity")) for event in events] != [(t, work_id) for t in TERMINAL_EVENTS]:
        return False
    if any(reserved(f"{stage}:event:{index}") != event.get("id") for index, event in enumerate(events)):
        return False
    if {key: value for key, value in events[1].items() if key not in ("id", "type", "entity", "at")} != _completion_metadata(record.run):
        return False
    consumption_id = reserved(gate.review_consumption_key(record.run.receipt_id))
    return consumption_id is not None and effects[2]["payload"].get("path") == review_paths.consumption_rel(consumption_id)


@dataclass(frozen=True)
class RecordedTerminal:
    """The one review-v1 terminal stage a pending Work START mutation recorded, as its durable record holds it.

    What the activation totality allowance (P3 F1 §10.2, FC-12) may lean on: the
    stage is one durable unit - both terminal events, then the Consumption create -
    so an event without its Consumption, or a Consumption without its event, is
    a half of a stage this record holds. Whether that half is one its own replay
    can finish is answered from the same record, by what the replay itself
    requires: ``consumption_written`` is what this mutation recorded writing at
    the Consumption path (``None`` when it never wrote there); ``log_before`` is
    what the event log held, by this mutation's own record, right before the
    stage's first event, and ``log_after`` what it recorded writing there with
    the stage's second - the state its replay must find before it appends the
    events again, or after which only the Consumption is left to create.
    """

    mutation_id: str
    work_id: str
    stage: str
    completed: dict[str, Any]
    consumption_path: str
    consumption_content: str
    consumption_written: str | None
    log_before: str | None
    log_after: str | None


def recorded_terminal(mutation_record: dict[str, Any], store: ProjectStore | None = None) -> RecordedTerminal | None:
    """The terminal stage of exactly the frozen shape (F3 §13.3) a pending review-v1 Work START recorded; else None.

    Read from the durable record alone, never from what files hold: a record
    that is not a review-v1 Work START, holds no terminal stage, holds more than
    one, or holds one of any other shape excuses nothing. With ``store``, a P5
    Run's stage - its summary create, then the same three effects (P-2) - is read
    by the history contract the Run's own TaskInputs store; the halves are the
    events' and the Consumption's exactly as before.
    """
    if mutation_record.get("status") != "pending":
        return None
    try:
        record = work_record(mutation_record)
        stage = _terminal_stage(record)
    except ReconcileRequired:
        return None
    history_contract = _stored_history_contract(store, mutation_record)
    if stage is None or not _terminal_shape(mutation_record, stage, record.work_id, history_contract):
        return None
    effects = record.stage_effects(stage)
    if history_contract is not None:
        effects = effects[1:]  # the summary create the P5 stage records first; the halves are the events' and Consumption's
    everything = list(record.effects)
    first = next(index for index, effect in enumerate(everything) if effect is effects[0])
    before = _last_wrote(everything[:first], EVENT_LOG) or effects[0].get(_HELD_BEFORE)
    after = _last_wrote(everything[:first + 2], EVENT_LOG)
    written = effects[2].get(_WROTE)
    return RecordedTerminal(
        record.mutation_id, record.work_id, stage, dict(effects[1]["payload"]["record"]),
        str(effects[2]["payload"]["path"]), str(effects[2]["payload"]["content"]),
        written if isinstance(written, str) else None, before if isinstance(before, str) else None,
        after if isinstance(after, str) else None,
    )


def _completion_metadata(run: WorkRun) -> dict[str, Any]:
    return {
        "operation_contract": OPERATION_CONTRACT,
        "review_receipt_id": run.receipt_id,
        "review_run_id": run.review_run_id,
        "review_generation": work_review.SEAL_GENERATION if run.contract is None else p4.SEAL_GENERATION,
    }


# --------------------------------------------------------------------------- §8.2: lineage


def run_record_paths(run: WorkRun, chain: Any) -> list[str]:
    """This Run's own canonical Review record paths, DERIVED from its validated chain (L-2), never hardcoded.

    A P4 Run's own set is its whole current cycle's records (every Run, report, adjudication, Repair Batch and
    Result of this START), read where a store is held (:func:`p4_cycle_paths`); without it nothing extra is owned.
    """
    if run.contract is not None and run.own_paths:
        return sorted(run.own_paths)
    first = chain.generations[0]
    found = {review_paths.candidate_snapshot_rel(first.candidate_hash)}
    for generation in chain.generations:
        found.add(review_paths.gate_rel(run.review_run_id, generation.generation))
        for task in generation.accepted_tasks:
            found.add(review_paths.task_input_rel(str(task["task_id"])))
        if generation.receipt_id:
            found.add(review_paths.receipt_rel(str(generation.receipt_id)))
    return sorted(found)


def _delta(git: HermeticGit, parent: str, commit: str) -> list[gitcmd.DeltaEntry]:
    """The complete delta of ``commit`` against ``parent``, from the stored objects (class B, no renames)."""
    try:
        return workcommit._tree_delta(git, workcommit._tree_of(git, parent), workcommit._tree_of(git, commit))
    except StopError as exc:
        raise _reconcile(f"the delta of {commit} against {parent} cannot be read: {exc}") from exc


def _parents(git: HermeticGit, commit: str) -> tuple[str, ...] | None:
    found = ancestry.raw_parents(git, commit)
    return None if isinstance(found, ancestry.Answer) else tuple(found)


def require_lineage(git: HermeticGit, run: WorkRun, chain: Any, base: dict[str, Any], parent: str) -> None:
    """``review-v1-work-lineage-v1``, L-1 ... L-5, measured to ``parent`` (§8.2; §6.3 for the empty case).

    Every question is answered by the RAW reader (§7.1.8): a graft, a shallow
    boundary or a replacement object changes nothing it reads, and an
    unanswerable question fails closed.
    """
    branch, base_commit = base["branch"], base["base_commit"]
    if workcommit._head_ref(git) != branch:
        raise _lineage_failed("L-3", f"HEAD is not on {branch}, the branch the Candidate declared")
    tip = workcommit.ref_value(git, branch)
    if tip is None or (tip != parent and ancestry.raw_descends_from(git, tip, parent) is not True):
        raise _lineage_failed("L-3", f"{branch} does not hold {parent}")
    if parent != base_commit and ancestry.raw_descends_from(git, parent, base_commit) is not True:
        raise _lineage_failed("L-1", f"{base_commit} is not shown to be an ancestor of {parent}")
    commits = ancestry.raw_range(git, base_commit, parent)
    if isinstance(commits, ancestry.Answer):
        raise _lineage_failed("L-2", f"the range ({base_commit}, {parent}] is {commits.value}")
    own = set(run_record_paths(run, chain))
    for commit in commits:
        parents = _parents(git, commit)
        if parents is None or len(parents) != 1:
            raise _lineage_failed("L-2", f"{commit} does not have exactly one parent")
        delta = _delta(git, parents[0], commit)
        foreign = [entry.path for entry in delta
                   if entry.status != "A" or entry.new_mode != "100644" or entry.path not in own]
        if not delta or foreign:
            raise _lineage_failed(
                "L-2", f"{commit} is not an own-Review commit of Run {run.review_run_id}"
                + (f" ({', '.join(foreign)})" if foreign else " (empty delta)")
            )


# --------------------------------------------------------------------------- the Run as a commit holds it


@dataclass(frozen=True)
class ProofMaterial:
    """The Run's records exactly as one commit holds them, cross-checked the way the launch checks them."""

    chain: Any
    snapshot: records.CandidateSnapshot
    reconstruction: work_review.Reconstruction
    task_input: records.TaskInput
    context: dict[str, Any]
    receipt: records.Receipt
    #: P4 only: the Run's canonical adjudication, which is what authorizes it (never generation 2).
    adjudication: Any = None

    @property
    def candidate(self) -> dict[str, Any]:
        return self.reconstruction.candidate

    @property
    def base(self) -> dict[str, Any]:
        return self.reconstruction.candidate["declared_base"]

    @property
    def content(self) -> dict[str, Any]:
        return work_review.content_of(self.reconstruction.candidate)


def _material_at(at: "CommittedRecords", record: WorkRecord, item: str) -> ProofMaterial:
    run = record.run
    if run.contract is not None:
        return _p4_material_at(at, record, item)
    try:
        chain = at.gate_chain(run.review_run_id)
        if chain is None or len(chain.generations) != work_review.SEAL_GENERATION:
            raise _proof_failed(item, f"{at.commit} does not hold Run {run.review_run_id} as accepted, settled and sealed")
        third = chain.latest
        if not third.sealed or third.receipt_id != run.receipt_id:
            raise _proof_failed(item, f"{at.commit} does not hold the seal issuing Receipt {run.receipt_id}")
        first = chain.generations[0]
        snapshot = at.read_candidate_snapshot(first.candidate_hash)
        candidate = (snapshot.material or {}).get("candidate") or {}
        width = len(str(candidate.get("declared_base", {}).get("base_commit", "")))
        reconstruction = work_review.read_material(snapshot, first.candidate_hash, width)
        task_input = at.read_task_input(run.task_id)
        problems = work_review.task_input_problems(
            task_input, snapshot.material or {}, first.candidate_hash, first.review_context_hash,
            first.effective_policy_hash, review_run_id=run.review_run_id,
        )
        if problems:
            raise _proof_failed(item, "; ".join(problems))
        receipt = at.read_receipt(run.receipt_id)
    except ValidationError as exc:
        raise _proof_failed(item, f"the Run's records at {at.commit} do not read: {exc}") from exc
    return ProofMaterial(chain, snapshot, reconstruction, task_input, dict(task_input.request_envelope["context"]), receipt)


def _record_bytes(at: "CommittedRecords", paths: list[str]) -> dict[str, bytes | None]:
    return {relative: at.read_bytes(relative) for relative in paths}


def _namespace_clean(at: "CommittedRecords", run: WorkRun, item: str) -> None:
    """The whole namespace reads canonically at this commit, and nothing invalidates or supersedes the Run."""
    from .review import validate

    problems = validate.review_problems(at)
    if problems:
        raise _proof_failed(item, f"the Review namespace at {at.commit} does not read canonically: {problems[0].message}")
    invalidation = INVALIDATION_GENERATION if run.contract is None else p4.INVALIDATION_GENERATION
    if at.entry(review_paths.gate_rel(run.review_run_id, invalidation)) is not None or at.supersession_exists(run.receipt_id):
        raise _proof_failed(item, f"{at.commit} holds an invalidation of Run {run.review_run_id} or a Supersession")


def _require_receipt_current(material: ProofMaterial, record: WorkRecord, item: str) -> None:
    """W8 / T11: the Receipt is this Run's latest valid authorization for exactly this Candidate and stage."""
    from .review import validate

    receipt, third = material.receipt, material.chain.latest
    problems = [problem.message for problem in validate._gate_receipt_binding(third, receipt)]
    expected = {
        "authorized_candidate_hash": material.chain.generations[0].candidate_hash,
        "authorized_operation_stage": work_review.AUTHORIZED_OPERATION_STAGE,
        "target_identity": record.work_id,
        "operation_identity": work_review.operation_identity(record.work_id),
        "review_kind": work_review.REVIEW_KIND,
    }
    problems += [f"{name} is {getattr(receipt, name)!r}" for name, value in expected.items()
                 if getattr(receipt, name) != value]
    if record.run.contract is not None:
        found = material.adjudication
        if found is None or found.outcome != p4.AUTHORIZATION_READY or found.obligations["problem_high"] \
                or found.obligations["problem_mid"] or found.obligations["human"]:
            problems.append("the P4 adjudication does not authorize")
    elif not work_review.authorizes(material.chain.generations[1]):
        problems.append("the settlement does not authorize")
    if problems:
        raise _proof_failed(item, "the Receipt is not this Run's authorization of exactly this Candidate for "
                                  "start:work-terminal: " + "; ".join(problems))


def _require_identities(store: ProjectStore, git: HermeticGit, material: ProofMaterial, activation: Activation,
                        item: str) -> None:
    """W10 / T11: the Context recomputes to the bound hash, the Policy is the bound one, the Evidence re-derives."""
    from .implementation import package_directory

    first = material.chain.generations[0]
    capability = material.context["review_checkout_capability"]
    try:
        recomputed = work_context.context_record(
            store.workline_root(), package_directory(store.workline_root()), activation.binding(),
            capability["base_tree"], capability["resulting_tree"],
        )
    except StopError as exc:
        raise _proof_failed(item, f"the Work Review Context cannot be recomputed: {exc}") from exc
    p4_run = p4.contract_of_task_input(material.task_input) is not None
    policy = _p4_task_policy(material.task_input)  # the Run's own stored family policy (GAP-A)
    bound = serialize.digest(work_review.context_record_p4(recomputed, policy)) if p4_run \
        else work_context.context_hash(recomputed)
    if bound != first.review_context_hash:
        raise _proof_failed(item, "the Work Review Context no longer recomputes to the bound review_context_hash")
    stored = p4.envelope_policy_hash(material.task_input.request_envelope) if p4_run else work_review.policy_hash()
    if stored != first.effective_policy_hash:
        raise _proof_failed(item, "the Effective Policy is not the bound one")
    entries = work_review.entries_of(material.candidate)
    verified = work_verify.Verified(material.base["base_commit"], capability["resulting_tree"], len(entries))
    evidence = _evidence(git, material.candidate, material.snapshot, material.task_input, material.context,
                         first.review_context_hash, first.effective_policy_hash, activation, verified,
                         declared=bool(entries))
    if serialize.digest(evidence) != first.evidence_digest:
        raise _proof_failed(item, "the Evidence, and the closure digest inside it, does not re-derive to the bound "
                                  "evidence_digest")


def _activation_at(store: ProjectStore, git: HermeticGit, at: "CommittedRecords", material: ProofMaterial,
                   item: str) -> Activation:
    """W11: the activation record at this commit, well-formed, its prefix reproducing, bound in both records."""
    try:
        found = at.read_activation()
    except ValidationError as exc:
        raise _proof_failed(item, f"the activation record at {at.commit} does not read: {exc}") from exc
    if found is None:
        raise _proof_failed(item, f"{at.commit} holds no activation record")
    digest = work_activation.committed_prefix_digest(git, at.commit, found.legacy_event_count)
    if digest is None or digest != found.legacy_event_prefix_sha256:
        raise _proof_failed(item, f"the activation prefix does not reproduce at {at.commit}")
    activation = Activation(found, serialize.digest(found.to_record()))
    binding = activation.binding()
    if material.candidate.get("activation") != binding or material.context.get("activation") != binding:
        raise _proof_failed(item, "the activation record is not the one the Candidate and the Context bind")
    return activation


def _events_at(git: HermeticGit, commit: str) -> bytes:
    found = git.run_bytes("cat-file", "blob", f"{commit}:{EVENT_LOG}")
    if not found.ok:
        raise _reconcile(f"the event log of {commit} cannot be read")
    return found.stdout


def _tree_identity(git: HermeticGit, commit: str, paths: list[str]) -> dict[str, tuple[str, str, str]]:
    try:
        held = workcommit._tree_entries(git, commit, paths)
    except StopError as exc:
        raise _reconcile(f"the tree of {commit} cannot be read: {exc}") from exc
    return {path: (entry.type, entry.mode, entry.oid) for path, entry in held.items()}


_KIND_TYPE = {"file": "blob", "symlink": "blob", "gitlink": "commit"}


def _require_contained(git: HermeticGit, commit: str, entries: list[dict[str, Any]], item: str) -> None:
    """W5 / T12: every entry resolves in ``commit``'s tree to exactly its new identity; a deletion is absent."""
    held = _tree_identity(git, commit, [entry["path"] for entry in entries])
    for entry in entries:
        found = held.get(entry["path"])
        if entry["new_kind"] == "absent":
            if found is not None:
                raise _proof_failed(item, f"{commit} still holds {entry['path']}, which the Candidate deletes")
        elif found != (_KIND_TYPE[entry["new_kind"]], entry["new_mode"], entry["new_oid"]):
            raise _proof_failed(item, f"{commit} holds {entry['path']} as {found}, not the Candidate's identity")


#: Git's raw status letters and the Candidate's (§9 W4): a type change has both sides present, so it is M.
_STATUS = {"A": "A", "D": "D", "M": "M", "T": "M"}


def _stage_position(record: WorkRecord, stage: str | None) -> int:
    for index, effect in enumerate(record.effects):
        if effect.get("stage") == stage:
            return index
    return len(record.effects)


def prove_result(store: ProjectStore, git: HermeticGit, mutation_record: dict[str, Any], k1: str) -> dict[str, Any]:
    """C-2(K1), ``review-v1-work-proof-v1`` W1 ... W12 (F3 §9), for exactly ``k1``; the result-proof note's content.

    Re-executed from the durable record and the committed objects alone
    (Option A, §10), so it can run again at any time - before the note, before
    the push is recorded and immediately before it is applied - and it never
    reads its own earlier outcome.
    """
    record = work_record(mutation_record)
    work_id = record.work_id
    if record.run.contract is not None:
        record.run.own_paths = p4_cycle_paths(store, record.reserved, work_id)
    stage = record.one_stage(f"{work_id}:results")
    effect = _commit_effect(record, stage)
    # W1 - ownership: the S-c1 effect promoted by O-7a, and nothing else confers it
    if effect is None or effect.get("applied") is not True or effect.get("commit_id") != k1:
        raise _proof_failed("W1", f"{k1} is not the commit the S-c1 stage of this mutation made", "review_commit_unowned")
    payload = effect["payload"]
    stored = workcommit._stored_commit(git, k1)
    if stored is None or len(stored.parents) != 1:
        raise _proof_failed("W3", f"{k1} is not one commit with exactly one parent")
    parent = stored.parents[0]
    at_parent, at_k1 = CommittedRecords(store, git, parent), CommittedRecords(store, git, k1)
    material = _material_at(at_k1, record, "W7")
    base = material.base
    # W2 - the Work persistence semantics, pinned to the declared base, re-proven now
    if (payload.get("mode") != workcommit.CONTRACT or payload.get("plan_class") != workcommit.CLASS_RESULT
            or payload.get("attr_basis") != base["base_commit"]):
        raise _proof_failed("W2", "S-c1 is not a review-v1-work-local-v2 result commit pinned to the declared base")
    attributes.require_pinned_path_evaluation(store, git, base["base_commit"], list(payload["paths"]))
    # W3 - lineage
    if parent != payload.get("base_head") or payload.get("branch") != base["branch"]:
        raise _proof_failed("W3", f"parent({k1}) is not the recorded base_head on the declared branch")
    require_lineage(git, record.run, material.chain, base, parent)
    tip = workcommit.ref_value(git, base["branch"])
    if tip is None or ancestry.raw_descends_from(git, tip, k1) is not True:
        raise _proof_failed("W3", f"{base['branch']} does not hold {k1}")
    # W4 - the artifact delta is the Candidate's CHANGING entries exactly
    entries = work_review.entries_of(material.candidate)
    changing = [entry for entry in entries if work_review.changing(entry)]
    if material.content["artifact_kind"] != work_review.ARTIFACT_RESULT or not changing:
        raise _proof_failed("W4", "the Candidate is not a result-bearing one")
    expected = {entry["path"]: (entry["old_mode"], entry["new_mode"], entry["old_oid"], entry["new_oid"], entry["status"])
                for entry in changing}
    found: dict[str, tuple[str, ...]] = {}
    for item in _delta(git, parent, k1):
        status = _STATUS.get(item.status)
        if status is None or item.path in found:
            raise _proof_failed("W4", f"{k1}'s delta holds {item.status} at {item.path}")
        found[item.path] = (item.old_mode, item.new_mode, item.old_blob, item.new_blob, status)
    if found != expected:
        raise _proof_failed("W4", f"{k1}'s delta is not exactly the Candidate's changing entries")
    # W5 - every declared entry, inert ones included, by exact tree containment
    _require_contained(git, k1, entries, "W5")
    # W6 - the message, byte for byte
    if stored.message != material.content["message"].encode("utf-8"):
        raise _proof_failed("W6", f"{k1}'s message is not the Candidate's message exactly")
    # W7 - the Run's records present and unchanged at parent(K1) and K1; the namespace canonical at both
    paths = run_record_paths(record.run, material.chain)
    before, after = _record_bytes(at_parent, paths), _record_bytes(at_k1, paths)
    if before != after or any(data is None for data in after.values()):
        raise _proof_failed("W7", "this Run's records are not held unchanged at parent(K1) and K1")
    _material_at(at_parent, record, "W7")
    _namespace_clean(at_parent, record.run, "W7")
    _namespace_clean(at_k1, record.run, "W7")
    # W8 - the authorization is current
    _require_receipt_current(material, record, "W8")
    # W9 - the Candidate is current: declared_base re-derives at its base, and at parent(K1)
    if declared_base(store, git, base["base_commit"], base["branch"], work_id) != base:
        raise _proof_failed("W9a", "declared_base does not re-derive at declared_base.base_commit")
    again = declared_base(store, git, parent, base["branch"], work_id)
    if {**again, "base_commit": base["base_commit"]} != base:
        raise _proof_failed("W9b", f"declared_base does not re-derive identically at {parent}")
    # W11 before W10: the activation the Context is recomputed with is the one proven here
    activation = _activation_at(store, git, at_parent, material, "W11")
    _require_identities(store, git, material, activation, "W10")
    # W12 - neither the transition nor the consumption has happened
    state = committed_view_at(store, git, k1).work_state(work_id)
    if state.state != "in_progress" or not state.has_target:
        raise _proof_failed("W12", f"{work_id} does not hold its target in progress at {k1}")
    for earlier in record.effects[:_stage_position(record, stage)]:
        event = (earlier.get("payload") or {}).get("record") if earlier.get("kind") == "append_event" else None
        if earlier.get("kind") == "git_push" or (isinstance(event, dict) and event.get("type") in WORK_TERMINAL_EVENTS):
            raise _proof_failed("W12", "a push or a Work terminal event is recorded before S-c1")
    consumed = [c for c in (*at_k1.consumptions(), *ReviewStore(store).consumptions())
                if c.receipt_id == record.run.receipt_id]
    if consumed:
        raise _proof_failed("W12", f"a Consumption of Receipt {record.run.receipt_id} already exists")
    return {
        "contract": PROOF_CONTRACT, "candidate_hash": material.chain.generations[0].candidate_hash,
        "receipt_id": record.run.receipt_id, "result_commit": k1, "base_commit": parent, "branch": base["branch"],
    }


def _parse_events(data: bytes) -> list[dict[str, Any]] | None:
    """Every Event record ``data`` holds, as the live reader parses it; None when one is not an Event."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    found: list[dict[str, Any]] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(event, dict) or not all(isinstance(event.get(k), str) for k in ("id", "type", "entity", "at")):
            return None
        found.append(event)
    return found


def prove_terminal(store: ProjectStore, git: HermeticGit, mutation_record: dict[str, Any], k2: str) -> dict[str, Any]:
    """C-2(K2), ``review-v1-work-proof-v1`` T1 ... T12 (F3 §16), for exactly ``k2``; the terminal-proof note's content."""
    record = work_record(mutation_record)
    work_id, run = record.work_id, record.run
    if run.contract is not None:
        run.own_paths = p4_cycle_paths(store, record.reserved, work_id)
    stage = record.one_stage(f"{work_id}:finalize")
    effect = _commit_effect(record, stage)
    # T1 - ownership
    if effect is None or effect.get("applied") is not True or effect.get("commit_id") != k2:
        raise _proof_failed("T1", f"{k2} is not the commit the S-c2 stage of this mutation made", "review_commit_unowned")
    payload = effect["payload"]
    stored = workcommit._stored_commit(git, k2)
    if stored is None or len(stored.parents) != 1:
        raise _proof_failed("T3", f"{k2} is not one commit with exactly one parent")
    parent = stored.parents[0]
    at_parent, at_k2 = CommittedRecords(store, git, parent), CommittedRecords(store, git, k2)
    material = _material_at(at_k2, record, "T11")
    base = material.base
    result = material.content["artifact_kind"] == work_review.ARTIFACT_RESULT
    k1_effect = _commit_effect(record, record.one_stage(f"{work_id}:results"))
    k1 = None if k1_effect is None else k1_effect.get("commit_id")
    # T2 - the Work persistence semantics, pinned to the declared base, re-proven now
    if (payload.get("mode") != workcommit.CONTRACT or payload.get("plan_class") != workcommit.CLASS_TERMINAL
            or payload.get("attr_basis") != base["base_commit"]):
        raise _proof_failed("T2", "S-c2 is not a review-v1-work-local-v2 terminal commit pinned to the declared base")
    attributes.require_pinned_path_evaluation(store, git, base["base_commit"], list(payload["paths"]))
    # T3 - lineage: parent(K2) is K1 exactly, or the own-Review lineage with no K1. A Class-A completion -
    # selected only by its durable checkpoint and the successor it reserved, never by the parent's shape - has
    # parent(K_terminal) = K_adopt exactly, over the proven adoption range K1 -> old G4 -> G1 -> G2 -> G3 (F4 §11.18.10)
    if parent != payload.get("base_head") or payload.get("branch") != base["branch"]:
        raise _proof_failed("T3", f"parent({k2}) is not the recorded base_head on the declared branch")
    adopted: str | None = None
    if result and record.adopted:
        adopted = _adopted_parent(store, git, record, k1, parent, "T3")
        if parent != adopted:
            raise _proof_failed("T3", f"parent({k2}) is not K_adopt exactly")
    elif result:
        if not isinstance(k1, str) or parent != k1:
            raise _proof_failed("T3", f"parent({k2}) is not K1 exactly")
    else:
        if k1 is not None:
            raise _proof_failed("T3", "an empty-artifact operation holds a result commit")
        require_lineage(git, run, material.chain, base, parent)
    if workcommit._head_ref(git) != base["branch"]:
        raise _proof_failed("T3", f"HEAD is not on {base['branch']}")
    tip = workcommit.ref_value(git, base["branch"])
    if tip is None or ancestry.raw_descends_from(git, tip, k2) is not True:
        raise _proof_failed("T3", f"{base['branch']} does not hold {k2}")
    # T4 - the delta is exactly the terminal projection
    terminal = _terminal_stage(record)
    consumption_id = record.reserved.get(gate.review_consumption_key(run.receipt_id))
    if terminal is None or not isinstance(consumption_id, str):
        raise _proof_failed("T4", "the terminal stage or its Consumption id is not recorded")
    consumption_path = review_paths.consumption_rel(consumption_id)
    delta = sorted((item.path, item.status, item.old_mode, item.new_mode) for item in _delta(git, parent, k2))
    # P5 (§28.6), by the history contract the Run's own committed TaskInputs bind - never by K2's shape (GAP-A)
    summary_path = _committed_summary_path(at_k2, run, material.chain, "T4")
    expected_delta = [(EVENT_LOG, "M", "100644", "100644"), (consumption_path, "A", "000000", "100644")]
    if summary_path is not None:
        expected_delta.append((summary_path, "A", "000000", "100644"))
    if delta != sorted(expected_delta):
        raise _proof_failed("T4", f"{k2}'s delta is not exactly the event log and the Consumption"
                            + ("" if summary_path is None else " and the Run summary"))
    # T5 - no new reviewed-artifact delta
    entries = work_review.entries_of(material.candidate)
    paths = [entry["path"] for entry in entries]
    if result and _tree_identity(git, k2, paths) != _tree_identity(git, str(k1), paths):
        raise _proof_failed("T5", f"{k2} changes the reviewed artifact K1 carries")
    # T6 / T7 - exactly the authorized transition, appended, and nothing else
    before, after = _events_at(git, parent), _events_at(git, k2)
    old, new = _parse_events(before), _parse_events(after)
    if old is None or new is None or not after.startswith(before) or new[: len(old)] != old:
        raise _proof_failed("T6", f"the event log at {k2} is not the one at {parent} with records appended")
    appended = new[len(old):]
    reserved = [record.reserved.get(f"{terminal}:event:{index}") for index in range(2)]
    shape = [(event.get("type"), event.get("entity"), event.get("id")) for event in appended]
    if shape != [(TERMINAL_EVENTS[0], work_id, reserved[0]), (TERMINAL_EVENTS[1], work_id, reserved[1])]:
        raise _proof_failed("T6", f"{k2} appends {shape}, not exactly the two authorized events")
    if {k: v for k, v in appended[1].items() if k not in ("id", "type", "entity", "at")} != _completion_metadata(run):
        raise _proof_failed("T7", "work_completed does not carry exactly the review-v1 operation-contract metadata")
    if {k: v for k, v in appended[0].items() if k not in ("id", "type", "entity", "at")}:
        raise _proof_failed("T7", "work_target_removed carries metadata")
    # T8 - the Consumption's content, and the artifact_kind agreement read from committed state
    recorded = [e for e in record.stage_effects(terminal) if e.get("kind") == "create_file"]
    if summary_path is not None:
        # P5: the stage records the summary create and the Consumption create; each is picked by its path
        summaries = [e for e in recorded if e["payload"].get("path") == summary_path]
        recorded = [e for e in recorded if e["payload"].get("path") == consumption_path]
        held = at_k2.read_bytes(summary_path)
        if len(summaries) != 1 or held is None or held != summaries[0]["payload"]["content"].encode("utf-8"):
            raise _proof_failed("T8", "the Run summary K2 adds is not byte for byte the recorded one")
    committed = at_k2.read_bytes(consumption_path)
    if len(recorded) != 1 or committed is None or committed != recorded[0]["payload"]["content"].encode("utf-8"):
        raise _proof_failed("T8", "the Consumption K2 adds is not byte for byte the recorded one")
    try:
        consumption = at_k2.read_consumption(consumption_id)
    except ValidationError as exc:
        raise _proof_failed("T8", f"the Consumption does not read back: {exc}") from exc
    require_artifact_kind_agreement(material.candidate, consumption, k1, "T8")
    if summary_path is not None:
        # §28.6: the post-commit proof of the summary against the exact Consumption, read from K2 itself
        try:
            summary = at_k2.read_history(review_paths.HISTORY_RUNS, run.review_run_id)
            problems = history.run_summary_problems(at_k2, summary)
        except ValidationError as exc:
            raise _proof_failed("T8", f"the Run summary does not read back: {exc}") from exc
        if problems or summary.durable_disposition != history.DISPOSITION_CONSUMED \
                or summary.consumption_id != consumption_id:
            raise _proof_failed("T8", "the Run summary does not validate against the exact Consumption: "
                                + "; ".join(message for _, message in problems))
    # T9 - the Consumption binds exactly this Receipt, this mutation and this terminal event
    receipt = material.receipt
    binding = ("receipt_id", "review_run_id", "review_generation", "review_kind", "target_identity",
               "operation_identity", "authorized_candidate_hash")
    wrong = [name for name in binding if getattr(consumption, name) != getattr(receipt, name)]
    if (wrong or consumption.operation_mutation_id != record.mutation_id or consumption.terminal_event_id != reserved[1]
            or consumption.terminal_event_type != "work_completed" or consumption.target_identity != work_id):
        raise _proof_failed("T9", "the Consumption does not bind exactly this Receipt, mutation and terminal event")
    # T10 - uniqueness and totality at K2
    try:
        by_receipt = at_k2.consumption_by_receipt()
        by_event = at_k2.consumption_by_terminal_event()
    except ValidationError as exc:
        raise _proof_failed("T10", f"the Consumption indexes do not build at {k2}: {exc}") from exc
    if (getattr(by_receipt.get(run.receipt_id), "consumption_id", None) != consumption_id
            or getattr(by_event.get(str(reserved[1])), "consumption_id", None) != consumption_id):
        raise _proof_failed("T10", "the Consumption is not the one Consumption of its Receipt and terminal event")
    _namespace_clean(at_k2, run, "T10")
    # T11 - the authorization still current, and every bound identity unchanged
    run_paths = run_record_paths(run, material.chain)
    if _record_bytes(at_parent, run_paths) != _record_bytes(at_k2, run_paths):
        raise _proof_failed("T11", "this Run's records changed between parent(K2) and K2")
    _require_receipt_current(material, record, "T11")
    activation = _activation_at(store, git, at_parent, material, "T11")
    _require_identities(store, git, material, activation, "T11")
    # T12 - the result binding
    if result:
        if ancestry.raw_descends_from(git, k2, str(k1)) is not True or consumption.authorized_result_commit_sha != k1:
            raise _proof_failed("T12", "K1 is not in K2's history, or the Consumption names another result commit")
    else:
        if consumption.authorized_result_commit_sha is not None:
            raise _proof_failed("T12", "an empty-artifact Consumption names a result commit")
        if any(e.get("kind") == "git_commit" and (e.get("payload") or {}).get("plan_class") == workcommit.CLASS_RESULT
               for e in record.effects):
            raise _proof_failed("T12", "a commit of this mutation carries a reviewed-artifact delta")
        _require_contained(git, k2, entries, "T12")
        declared = set(paths)
        if any(item.path in declared for item in _delta(git, base["base_commit"], k2)):
            raise _proof_failed("T12", "the delta from the declared base to K2 holds a declared path")
    proven = {
        "contract": PROOF_CONTRACT, "candidate_hash": material.chain.generations[0].candidate_hash,
        "receipt_id": run.receipt_id, "artifact_kind": material.content["artifact_kind"],
        "result_commit": k1 if result else None, "terminal_commit": k2, "terminal_event_ids": list(reserved),
        "consumption_id": consumption_id, "base_commit": parent, "branch": base["branch"],
    }
    if adopted is not None:
        proven["adopted_commit"] = adopted  # a Class-A terminal names its K_adopt; a normal one is unchanged
    return proven


def _committed_summary_path(at: "CommittedRecords", run: WorkRun, chain: Any, item: str) -> str | None:
    """The Run summary path K2 carries for a P5 Run, by the policy its committed TaskInputs store; None otherwise."""
    if run.contract is None:
        return None
    try:
        contract = p4.run_history_contract(at, chain)
    except (ReconcileRequired, ValidationError) as exc:
        raise _proof_failed(item, f"the Run's stored policy does not read at {at.commit}: {exc}") from exc
    return None if contract is None else review_paths.history_run_rel(run.review_run_id)


def require_artifact_kind_agreement(candidate: dict[str, Any], consumption: Any, k1: str | None, item: str) -> None:
    """F3 §14.2: both statements read on their own and compared; neither is derived from the other."""
    reviewed = work_review.content_of(candidate).get("artifact_kind")
    consumed = getattr(consumption, "artifact_kind", None)
    if reviewed not in (work_review.ARTIFACT_RESULT, work_review.ARTIFACT_EMPTY) or consumed != reviewed:
        raise _proof_failed(item, f"the Candidate says {reviewed!r} and the Consumption {consumed!r}")
    if reviewed == work_review.ARTIFACT_RESULT and (k1 is None or consumption.authorized_result_commit_sha != k1):
        raise _proof_failed(item, "a result-bearing Consumption does not name K1")
    if reviewed == work_review.ARTIFACT_EMPTY and consumption.authorized_result_commit_sha is not None:
        raise _proof_failed(item, "an empty Consumption names a result commit")


# --------------------------------------------------------------------------- IP-2: the Work publication validator


def work_publication(store: ProjectStore, effects: list[dict[str, Any]], position: int,
                     mutation_record: dict[str, Any]) -> tuple[str, str]:
    """``review-v1-work-publication-v1`` V-2 ... V-7 (F3 §11.2) for the push at ``position``; ``(K, full ref)``.

    V-1 (a push-only stage) is the caller's, in the Mutation Controller, and V-8
    (the exact refspec) is the one the Controller already pushes. Every refusal
    here is ``reconcile_required``: the push names no commit and publishes
    nothing.
    """
    push = effects[position]
    payload = push.get("payload") if isinstance(push.get("payload"), dict) else {}
    commit = payload.get("commit")
    if not gitcmd.full_commit_id(commit):
        raise _reconcile("V-2: the Work push does not name a full commit id", "review_publication_invalid")
    record = work_record({**mutation_record, "effects": effects})
    # V-3: exactly one proof note names K, and that says which publication this is. The adopted-result role
    # (F4 §11.18.9) is its own role, recognized only from its own note: never inferred from the stage's shape
    roles = []
    for key, named, role, contract in ((NOTE_RESULT_PROOF, "result_commit", ROLE_RESULT, PROOF_CONTRACT),
                                       (NOTE_ADOPTED_PROOF, "k_adopt", ROLE_ADOPTED, ADOPTED_PROOF_CONTRACT),
                                       (NOTE_TERMINAL_PROOF, "terminal_commit", ROLE_TERMINAL, PROOF_CONTRACT)):
        note = record.notes.get(key)
        if isinstance(note, dict) and note.get("contract") == contract and note.get(named) == commit:
            roles.append(role)
    if len(roles) != 1:
        raise _reconcile(f"V-3: {len(roles)} proof notes name {commit}, not exactly one", "review_publication_invalid")
    role = roles[0]
    # the normal-result and the adopted-result roles never both belong to one completion
    class_a = record.adopted or record.notes.get(NOTE_CLASS_A) is not None
    if (role == ROLE_RESULT and class_a) or (role == ROLE_ADOPTED and not record.adopted):
        raise _reconcile(f"V-3: a {'Class-A' if class_a else 'normal'} completion does not publish {commit} as "
                         f"its {role}", "review_publication_invalid")
    git = hermetic_module.enter(store)
    makers = [index for index, effect in enumerate(effects)
              if effect.get("kind") == "git_commit" and effect.get("applied") is True and effect.get("commit_id") == commit]
    if role == ROLE_ADOPTED:
        # V-4 / V-5: K_adopt is the successor's generation 3 commit - made by its generation mutation, never by
        # this START mutation - on the branch its proof binds, one commit on the successor's generation 2
        adopted = record.notes[NOTE_ADOPTED_PROOF]
        ref = adopted.get("branch")
        successors = adopted.get("successor_generation_commits")
        if makers or ref != f"refs/heads/{payload.get('branch')}" or not isinstance(successors, list) \
                or len(successors) != 3 or successors[-1] != commit:
            raise _reconcile("V-4: the adopted-result push does not name the successor's exact generation 3 commit on "
                             "the branch its proof binds", "review_publication_invalid")
        if _parents(git, commit) != (successors[1],):
            raise _reconcile(f"V-5: {commit} is not one commit on the successor's generation 2", "review_publication_invalid")
    else:
        # V-4: the one commit effect that made K
        maker = effects[makers[0]] if len(makers) == 1 else {}
        stage_members = [index for index, effect in enumerate(effects) if effect.get("stage") == maker.get("stage")]
        ref = (maker.get("payload") or {}).get("branch")
        if (len(makers) != 1 or stage_members != makers or makers[0] >= position
                or (maker.get("payload") or {}).get("mode") != workcommit.CONTRACT
                or ref != f"refs/heads/{payload.get('branch')}"):
            raise _reconcile("V-4: the commit the push names is not exactly one applied Work commit of its own stage, "
                             "recorded earlier on the pushed branch", "review_publication_invalid")
        # V-5: Git agrees - one parent, the recorded base_head, and the branch still holds K
        if _parents(git, commit) != (maker["payload"]["base_head"],):
            raise _reconcile(f"V-5: {commit} is not one commit on its recorded base_head", "review_publication_invalid")
    tip = workcommit.ref_value(git, str(ref))
    if tip is None or ancestry.raw_descends_from(git, tip, commit) is not True:
        raise _reconcile(f"V-5: {ref} does not hold {commit}", "review_publication_invalid")
    # V-6a: the exact cardinality, from the destination pin and the Candidate's artifact_kind
    from .destination import ensure_push_destination

    if ensure_push_destination(store) is None:
        raise _reconcile("V-6a: a Work mutation with no destination publishes nothing", "review_publication_invalid")
    at = CommittedRecords(store, git, commit)
    kind = _material_at(at, record, "V-6a").content["artifact_kind"]
    allowed = 2 if kind == work_review.ARTIFACT_RESULT else 1
    pushes = [index for index, effect in enumerate(effects) if effect.get("kind") == "git_push"]
    if len(pushes) > allowed:
        raise _reconcile(f"V-6a: {len(pushes)} pushes are recorded and this case allows {allowed}",
                         "review_publication_invalid")
    # V-6: the role's shape
    if role == ROLE_RESULT:
        if kind != work_review.ARTIFACT_RESULT or pushes[0] != position:
            raise _reconcile("V-6: a result publication in an operation that has no K1, or not the first push",
                             "review_publication_invalid")
    elif role == ROLE_ADOPTED:
        # the first of the two pushes a result-bearing Class A has; never K1 alone, never beside a result push
        k1 = record.notes[NOTE_ADOPTED_PROOF].get("k1")
        if (kind != work_review.ARTIFACT_RESULT or pushes[0] != position
                or any((effects[index].get("payload") or {}).get("commit") == k1 for index in pushes)):
            raise _reconcile("V-6: an adopted-result publication that is not the first push of a result-bearing "
                             "Class A, or one beside a push of K1", "review_publication_invalid")
    else:
        if len(pushes) != allowed or pushes[-1] != position:
            raise _reconcile("V-6a: the terminal publication is not the last of exactly the pushes this case allows",
                             "review_publication_invalid")
        terminal = _terminal_stage(record)
        if terminal is None or any(effect.get("applied") is not True for effect in record.stage_effects(terminal)):
            raise _reconcile("V-6: the terminal stage is not recorded and applied", "review_publication_invalid")
    # V-7: the full C-2 of exactly K, re-evaluated immediately before a push not yet applied is made. A push
    # already applied has published; its C-2 was re-evaluated before it was, and C-2(K1)'s W12 ("not yet
    # applied") is false by construction once the terminal stage exists, so it is never asked again then.
    if push.get("applied") is not True:
        whole = {**mutation_record, "effects": effects}
        prover, key = {
            ROLE_RESULT: (prove_result, NOTE_RESULT_PROOF),
            ROLE_ADOPTED: (prove_adopted_result, NOTE_ADOPTED_PROOF),
            ROLE_TERMINAL: (prove_terminal, NOTE_TERMINAL_PROOF),
        }[role]
        proven = prover(store, git, whole, commit)
        if record.notes[key] != proven:
            raise _reconcile("V-7: the proof re-evaluated now is not the one its note names", "review_publication_invalid")
    return commit, str(ref)


# --------------------------------------------------------------------------- 17 ... 37, in order


def _write_note(mutation: Mutation, key: str, value: dict[str, Any]) -> None:
    """A proof note is written once and names exactly one commit; a different one already there is reconcile."""
    found = mutation.note(key)
    if found is None:
        mutation.set_note(key, value)
        return
    if found != value:
        raise _reconcile(f"the {key} note already names another proof than the one re-evaluated now")


def _publish_stage(session: "_Session", prefix: str, commit: str, branch: str) -> None:
    """S-p1 / S-p2: a push-only stage publishing exactly ``commit`` to the declared ``branch`` (F3 §11, §12)."""
    from .review import publication

    mutation = session.mutation
    if work_record(mutation.record).one_stage(prefix) is None:
        # 22 / 33: the barrier, after the proof and its note, before the stage is recorded (§12.2)
        publication.require_barrier_clear(session.store.root, commit)
        mutation.add_effects(stage_name(mutation, prefix), [
            gitops.review_publication_effect(session.destination, branch.removeprefix("refs/heads/"), commit)
        ])
    # 24 / 35: the Controller re-resolves the destination, re-checks the barrier and - through the Work
    # validator - re-evaluates the full C-2 of exactly this commit before it pushes it (V-7)
    mutation.apply()


def _stage_commit(mutation: Mutation, stage: str | None) -> str:
    effect = _commit_effect(work_record(mutation.record), stage)
    if effect is None or effect.get("applied") is not True or not gitcmd.full_commit_id(effect.get("commit_id")):
        raise _reconcile(f"stage {stage} does not hold a commit C-1 owns", "review_commit_unowned")
    return str(effect["commit_id"])


def terminalize(session: "_Session", sealed: "Sealed | Adoption") -> Any:
    """F3 §5.1 steps 17 ... 37 for a sealed Work Review Run; the ``completed`` StartResult, or a STOP.

    A Class-A replacement in progress - an :class:`Adoption`, or any record
    that already holds the durable Class-A checkpoint - continues on the F4
    topology from that checkpoint (:func:`_adopt`) and never on the normal one.
    """
    from .start import StartResult

    if isinstance(sealed, Adoption):
        return _adopt(session, sealed.initial)
    if session.mutation.note(NOTE_CLASS_A) is not None:
        return _adopt(session, sealed.run)
    store, mutation = session.store, session.mutation
    run, material = sealed.run, sealed.material
    candidate, base = material.candidate, material.base
    work_id = run.work_id
    if run.contract is not None:
        run.own_paths = p4_cycle_paths(store, mutation.record.get("reserved_ids") or {}, work_id)
    result = work_review.artifact_kind(candidate) == work_review.ARTIFACT_RESULT
    git = hermetic_module.enter(store)
    remote = session.destination is not None
    chain = _chain(store, run)
    recorded = work_record(mutation.record)
    terminal_recorded = _terminal_stage(recorded) is not None
    # 17 - the lineage (§8.2), proven BEFORE anything of the terminal phase is made durable: the first
    # reservation of the Consumption id and the scope that names its path follow a successful proof and
    # never precede it (§5.1). Measured to K1's parent, or to K2's with no K1 (§6.2); each is proven
    # again immediately before the base-exact commit it guards (_result_commit, _terminal).
    if result:
        if recorded.one_stage(f"{work_id}:results") is None:
            require_lineage(git, run, chain, base, _head(git)[1])
    elif recorded.one_stage(f"{work_id}:finalize") is None and not terminal_recorded:
        require_lineage(git, run, chain, base, _head(git)[1])
    # 17a - the Consumption id, reserved at or after the seal and before S-c1 (§13.2)
    consumption_id = mutation.reserve_id(gate.review_consumption_key(run.receipt_id), "review_consumption")
    consumption_path = review_paths.consumption_rel(consumption_id)
    if consumption_path not in mutation.scope.files:
        mutation.extend_scope(files=[consumption_path])
    k1: str | None = None
    if result:
        k1 = _result_commit(session, sealed, git, chain)  # 17 again, 17b, 18, 19
        if not terminal_recorded:
            # 20, 21: C-2(K1) re-evaluated until the terminal stage exists. From then on its W12 ("the
            # consumption has not happened") is false by construction, and the stage was recorded only
            # once this proof was complete and its note durable (§13.4) - so it is never asked again.
            try:
                proven = prove_result(store, git, mutation.record, k1)
            except ReconcileRequired as failure:
                if run.contract is not None:
                    _p4_post_commit(session, sealed, git, failure)
                # F4: K1 exists and its normal proof no longer holds. Only an explicit, fail-closed post-commit
                # classification decides whether this is Class A; B, C and everything unproven stay reconcile.
                return _post_commit(session, sealed, git, k1, failure)
            _write_note(mutation, NOTE_RESULT_PROOF, proven)
        elif not isinstance(mutation.note(NOTE_RESULT_PROOF), dict):
            raise _reconcile("the terminal stage is recorded without the result proof note it requires")
        if remote:
            _publish_stage(session, f"{work_id}:results-publication", k1, base["branch"])  # 22 - 24
    k2 = _terminal(session, sealed, git, chain, consumption_id, k1)  # 25 - 30
    _write_note(mutation, NOTE_TERMINAL_PROOF, prove_terminal(store, git, mutation.record, k2))  # 31, 32
    if remote:
        _publish_stage(session, f"{work_id}:finalize-publication", k2, base["branch"])  # 33 - 35
    require_recorded_completion(session, sealed, git, k2, consumption_path)  # 36
    session.completed.append(work_id)
    view = ProjectView.load(store)
    return StartResult("completed", work_id, mutation.id, tuple(session.completed), view.works[work_id].phase_id,
                       head=k2)


def _result_commit(session: "_Session", sealed: Sealed, git: HermeticGit, chain: Any) -> str:
    """Steps 17 - 19: lineage, the preflight again, S-c1 recorded from the bound witnesses, K1 made (C-1)."""
    store, mutation = session.store, session.mutation
    run, material = sealed.run, sealed.material
    base = material.base
    prefix = f"{run.work_id}:results"
    if work_record(mutation.record).one_stage(prefix) is None:
        branch, tip = _head(git)
        require_lineage(git, run, chain, base, tip)  # 17, again: immediately before the base-exact S-c1
        changing = [entry for entry in work_review.entries_of(material.candidate) if work_review.changing(entry)]
        paths = [entry["path"] for entry in changing]
        pre_base = _pre_s_c0_base(work_record(mutation.record), base["base_commit"])
        owned = ownership.own_witnesses(mutation)
        missing = [path for path in paths if path not in owned]
        if missing:
            raise _reconcile(f"no bound ownership witness is recorded for {missing}")
        chosen = [owned[path] for path in paths]
        # the pre-stage re-proof of §7.8.4: the chain re-walked and the whole witness compared
        ownership.require_current(store, git, chosen, pre_base)
        attributes.require_pinned_path_evaluation(store, git, base["base_commit"], paths)  # 17b
        plan = workcommit.result_plan(git, parent=tip, ref=branch, message=material.content["message"],
                                      witnesses=chosen, candidate_entries=changing)
        effect = workcommit.commit_effect(plan, attr_basis=base["base_commit"], witness_basis=pre_base)
        mutation.add_effects(stage_name(mutation, prefix), [effect])  # 18
    mutation.apply()  # 19
    return _stage_commit(mutation, work_record(mutation.record).one_stage(prefix))


def _terminal_summary_path(store: ProjectStore, run: WorkRun, chain: Any) -> str | None:
    """The Run summary path the terminal stage of a P5 Run writes (§28.6); None for v1 and P4-only Runs."""
    if run.contract is None or chain is None or _p4_history(store, chain) is None:
        return None
    return review_paths.history_run_rel(run.review_run_id)


def _terminal(session: "_Session", sealed: Sealed, git: HermeticGit, chain: Any, consumption_id: str,
              k1: str | None, *, k_adopt: str | None = None) -> str:
    """Steps 25 - 30: the terminal stage (two events, then the Consumption), applied; then S-c2 and K2.

    With ``k_adopt`` (a Class-A adoption, F4 §11.18.10) the Consumption still
    binds K1, the stage follows the adopted-result proof instead of C-2(K1), and
    the terminal commit's exact parent is K_adopt instead of K1.
    """
    from .ops import new_event

    store, mutation = session.store, session.mutation
    run, material = sealed.run, sealed.material
    work_id, base = run.work_id, material.base
    consumption_path = review_paths.consumption_rel(consumption_id)
    summary_path = _terminal_summary_path(store, run, chain)
    if _terminal_stage(work_record(mutation.record)) is None:
        # §13.4 - before the stage is recorded
        gate.require_committable(store, [consumption_path] if summary_path is None else [summary_path, consumption_path])
        if summary_path is not None and summary_path not in mutation.scope.files:
            # P5 (§28.6): the Run summary path joins the scope only now - no generation of the Run follows - since a
            # G6 invalidation of this Run would write that path itself
            mutation.extend_scope(files=[summary_path])
        if material.content["artifact_kind"] == work_review.ARTIFACT_RESULT and k_adopt is not None:
            note = mutation.note(NOTE_ADOPTED_PROOF)
            if (not isinstance(note, dict) or note.get("contract") != ADOPTED_PROOF_CONTRACT or note.get("k1") != k1
                    or note.get("k_adopt") != k_adopt):
                raise _reconcile("the Class-A terminal stage is recorded only after the adopted-result proof of exact "
                                 "K_adopt and its note")
        elif material.content["artifact_kind"] == work_review.ARTIFACT_RESULT:
            note = mutation.note(NOTE_RESULT_PROOF)
            if not isinstance(note, dict) or note.get("result_commit") != k1:
                raise _reconcile("the terminal stage is recorded only after C-2(K1) and its note")
        review = ReviewStore(store)
        if run.contract is not None:
            authorizing = review.adjudication_exists(run.review_run_id) and \
                review.read_adjudication(run.review_run_id).outcome == p4.AUTHORIZATION_READY
            invalidation = p4.INVALIDATION_GENERATION
        else:
            authorizing = work_review.authorizes(chain.generations[1])
            invalidation = INVALIDATION_GENERATION
        if not chain.latest.sealed or not authorizing:
            raise _reconcile(f"Work Review Run {run.review_run_id} is not sealed with an authorizing settlement")
        if (any(c.receipt_id == run.receipt_id for c in review.consumptions()) or review.supersession_exists(run.receipt_id)
                or review.read_bytes(review_paths.gate_rel(run.review_run_id, invalidation)) is not None):
            raise _reconcile(f"Receipt {run.receipt_id} is consumed, superseded or invalidated")
        stage = stage_name(mutation, f"{work_id}:lifecycle")  # 25: every identifier durable before apply
        removed = new_event(mutation, f"{stage}:event:0", TERMINAL_EVENTS[0], work_id)
        reserved = new_event(mutation, f"{stage}:event:1", TERMINAL_EVENTS[1], work_id)
        completed = Event(reserved.id, reserved.type, reserved.entity, reserved.at, _completion_metadata(run))
        receipt = ReviewStore(store).read_receipt(run.receipt_id)
        consumption = records.Consumption(
            consumption_id=consumption_id, receipt_id=receipt.receipt_id, review_run_id=receipt.review_run_id,
            review_generation=receipt.review_generation, review_kind=receipt.review_kind,
            authorized_candidate_hash=receipt.authorized_candidate_hash, operation_identity=receipt.operation_identity,
            operation_mutation_id=mutation.id, terminal_event_id=completed.id, terminal_event_type=completed.type,
            target_identity=work_id, authorized_result_commit_sha=k1,
            artifact_kind=work_review.ARTIFACT_RESULT if k1 is not None else work_review.ARTIFACT_EMPTY,
        )
        # §14.3: the Consumption's own statement, then compared with the Candidate's before anything is recorded
        require_artifact_kind_agreement(material.candidate, consumption, k1, "§14")
        effects = [  # 26: two events, then the Consumption - exactly three, in that order
            Effect.append_event(removed),
            Effect.append_event(completed),
            Effect.create_file(consumption_path, serialize.canonical_text(consumption.to_record())),
        ]
        if summary_path is not None:
            # P5 (§28.6, P-2): the Run summary first, in the SAME stage - one durable unit with the events and the
            # Consumption it binds - so the record binds every write before apply, and K2 carries all of them
            summary = history.consumed_run_summary(
                chain.generation(p4.SEAL_GENERATION), receipt, consumption_id,
                candidate_generation=p4.run_candidate_generation(review, chain),
                adjudication=p4.bound_adjudication(review, chain),
            )
            effects.insert(0, Effect.create_file(summary_path, serialize.canonical_text(summary.to_record())))
        mutation.add_effects(stage, effects)
    mutation.apply()  # 27
    # §28.18: a P5 Consumption completes only with its final Run summary in the same transition
    history.require_history_ready(ReviewStore(store), run.review_run_id, history.BOUNDARY_CONSUMPTION,
                                  history_contract=None if summary_path is None else history.HISTORY_CONTRACT,
                                  consumption_id=consumption_id)
    prefix = f"{work_id}:finalize"
    if work_record(mutation.record).one_stage(prefix) is None:
        branch, tip = _head(git)
        if k_adopt is not None and tip != k_adopt:
            raise _reconcile(f"{branch} is {tip}, not K_adopt {k_adopt}; parent(K_terminal) is K_adopt exactly "
                             "(F4 §11.18.10)", "review_registration_base_moved")
        if k_adopt is None and k1 is not None and tip != k1:
            raise _reconcile(f"{branch} is {tip}, not K1 {k1}; parent(K2) is K1 exactly (§15.1)",
                             "review_registration_base_moved")
        if k1 is None:
            require_lineage(git, run, chain, base, tip)
        # 28 - 29: the per-commit preflight runs when the stage is recorded, under the declared base's pin
        view = ProjectView.load(store)
        effect = workcommit.terminal_commit_effect(
            mutation, f"chore(workline): complete {view.works[work_id].display}", attr_basis=base["base_commit"]
        )
        mutation.add_effects(stage_name(mutation, prefix), [effect])
    mutation.apply()  # 30
    return _stage_commit(mutation, work_record(mutation.record).one_stage(prefix))


def require_recorded_completion(session: "_Session", sealed: Sealed, git: HermeticGit, k2: str,
                                consumption_path: str) -> None:
    """Step 36, P-1 ... P-6 (F3 §19): only then does START return ``completed``."""
    store, mutation = session.store, session.mutation
    run, material = sealed.run, sealed.material
    record = work_record(mutation.record)
    terminal = _terminal_stage(record)
    # P-1 - the terminal stage recorded and applied
    if terminal is None or any(effect.get("applied") is not True for effect in record.stage_effects(terminal)):
        raise _reconcile("P-1: the terminal stage is not recorded and applied")
    # P-2 - C-2(K2), re-evaluated here
    prove_terminal(store, git, mutation.record, k2)
    # P-3 - with a remote, the exact K2 published (and, for a Class-A adoption, the exact K_adopt before it)
    if session.destination is not None:
        stage = record.one_stage(f"{run.work_id}:finalize-publication")
        if stage is None or any(effect.get("applied") is not True for effect in record.stage_effects(stage)):
            raise _reconcile("P-3: K2 is not published")
        if record.adopted:
            adopted = record.one_stage(f"{run.work_id}:adopted-publication")
            if adopted is None or any(effect.get("applied") is not True for effect in record.stage_effects(adopted)):
                raise _reconcile("P-3: K_adopt is not published")
    # P-4 - the live lifecycle postcheck, reading no Review record
    if ProjectView.load(store).work_state(run.work_id).state != "completed":
        raise StopError(f"{run.work_id} is not completed after its terminal stage", code="postcheck_failed")
    # P-5 - the Review consistency postcheck, from committed state at K2 (T8 - T11 re-read it in P-2)
    # P-6 - nothing this operation owns is left uncommitted (a P5 Run also owns its Consumption-bound Run summary)
    owned = [entry["path"] for entry in work_review.entries_of(material.candidate)] + [EVENT_LOG, consumption_path]
    summary_path = _terminal_summary_path(store, run, sealed.chain)
    if summary_path is not None:
        owned.append(summary_path)
    left = gitcmd.changed_against_head(store.root, owned)
    if left:
        raise _reconcile(f"P-6: {', '.join(sorted(left))} is not committed as this operation left it")


# =========================================================================== F4 (RB3-C1): post-commit recovery
#
# Where Class A is attempted: only once K1 - the result commit this mutation's own S-c1 made (C-1) - exists,
# its normal C-2(K1) fails, and no publication, terminal lifecycle, Consumption or terminal commit stage is
# durable yet. Pre-commit drift never reaches here: a mismatch known before K1 exists is not committed (F4
# §11.2). The classification is explicit and fail-closed - the hard safety facts are established on their own,
# and only then is the failure classified as A1 or A2; everything else is B, C, not eligible, or an escape.


@dataclass(frozen=True)
class PostCommit:
    """The explicit post-commit classification of an exact K1 whose normal proof failed (F4 §11.3, §26.8).

    ``kind``    A1 | A2 (adoptable), B, C, not-eligible, historical-escape (each reconcile)
    ``reason``  for an adoptable K1 its classification reason ("a1:<surfaces>" / "a2:<surfaces>"); for a
                refusal the reconcile reason it stops with
    """

    kind: str
    reason: str
    detail: str
    parent: str | None = None
    destination: str | None = None

    @property
    def adoptable(self) -> bool:
        return self.kind in (CLASS_A1, CLASS_A2)


def _stripped(failure: ReconcileRequired) -> str:
    text = str(failure)
    return text[: -len(": reconcile required")] if text.endswith(": reconcile required") else text


def _destination_state(session: "_Session", commit: str, branch: str) -> str:
    """Where the approved destination's ``branch`` stands to ``commit``; read-only (F4 §11.4, §26.28 P2).

    ```text
    no-remote   a remote-less Project: nothing is published, ever
    absent      the destination has no such branch
    holds       its branch is ``commit`` or a descendant of it: ``commit`` is published
    behind      its branch is an ancestor of ``commit``: ``commit`` is not published
    divergent   another history
    ```

    The existing exact-publication primitives, in their existing roles: the
    recorded destination confirmed against the Project pin before anything is
    contacted, only a locator Git reads as itself is read, the destination's own
    branch (never a remote-tracking ref), its history fetched as objects only,
    and the RAW ancestry reader. What cannot be read or shown is a STOP, never
    "not published".
    """
    destination = session.destination
    if destination is None:
        return "no-remote"
    from .destination import verify_recorded_destination

    store = session.store
    verify_recorded_destination(store, destination.remote, destination.locator)
    readable = gitcmd.reads_itself(store.root, destination.locator)
    if readable is False:
        raise _reconcile(f"whether the approved destination holds {commit} could only be read through the URL Git "
                         f"rewrites {destination.locator} to - another repository - so it is not read")
    if readable is None:
        raise StopError(f"cannot tell what a read of {destination.locator} would reach: STOP",
                        code="review_destination_unknown")
    tip = gitcmd.destination_branch(store.root, destination.locator, branch)
    if tip is None:
        return "absent"
    if tip == commit:
        return "holds"
    git = hermetic_module.enter(store)
    held = ancestry.raw_descends_from(git, tip, commit)
    if held is ancestry.UNKNOWN:
        gitcmd.fetch_destination_branch(store.root, destination.locator, branch)
        held = ancestry.raw_descends_from(git, tip, commit)
    if held is True:
        return "holds"
    if held is not False:
        raise StopError(f"cannot show whether {branch} at {destination.locator} holds {commit}: STOP",
                        code="review_destination_unknown")
    behind = ancestry.raw_descends_from(git, commit, tip)
    if behind is True:
        return "behind"
    if behind is False:
        return "divergent"
    raise StopError(f"cannot show how {branch} at {destination.locator} stands to {commit}: STOP",
                    code="review_destination_unknown")


def _currency_surfaces(store: ProjectStore, git: HermeticGit, material: Any, activation: Activation) -> list[str]:
    """Which bound authorization surfaces no longer re-derive now: Context, Effective Policy, Evidence (A2)."""
    from .implementation import package_directory

    first = material.chain.generations[0]
    capability = material.context["review_checkout_capability"]
    recomputed = work_context.context_record(
        store.workline_root(), package_directory(store.workline_root()), activation.binding(),
        capability["base_tree"], capability["resulting_tree"],
    )
    stale: list[str] = []
    if work_context.context_hash(recomputed) != first.review_context_hash:
        stale.append("review_context_changed")
    if work_review.policy_hash() != first.effective_policy_hash:
        stale.append("review_policy_changed")
    entries = work_review.entries_of(material.candidate)
    verified = work_verify.Verified(material.base["base_commit"], capability["resulting_tree"], len(entries))
    evidence = _evidence(git, material.candidate, material.snapshot, material.task_input, material.context,
                         first.review_context_hash, first.effective_policy_hash, activation, verified,
                         declared=bool(entries))
    if serialize.digest(evidence) != first.evidence_digest:
        stale.append("review_evidence_changed")
    return stale


def _artifact_differences(git: HermeticGit, material: Any, parent: str, k1: str, stored: Any) -> list[str]:
    """Where the persisted K1 is not the Candidate's artifact: its complete delta, its containment, its message."""
    differences: list[str] = []
    entries = work_review.entries_of(material.candidate)
    expected = {entry["path"]: (entry["old_mode"], entry["new_mode"], entry["old_oid"], entry["new_oid"], entry["status"])
                for entry in entries if work_review.changing(entry)}
    found: dict[str, tuple[str, ...]] = {}
    for item in _delta(git, parent, k1):
        found[item.path] = (item.old_mode, item.new_mode, item.old_blob, item.new_blob, _STATUS.get(item.status, "?"))
    if found != expected:
        differences.append("entries")
    try:
        _require_contained(git, k1, entries, "A1")
    except ReconcileRequired:
        if "entries" not in differences:
            differences.append("entries")
    if stored.message != material.content["message"].encode("utf-8"):
        differences.append("message")
    return differences


@dataclass(frozen=True)
class Replacement:
    """The replacement Candidate C2, frozen from committed objects alone (F4 §11.18.8, §26.11)."""

    candidate: dict[str, Any]
    payloads: dict[str, bytes]
    snapshot: records.CandidateSnapshot
    context: dict[str, Any]
    parent: str
    tree: str


def _replacement(store: ProjectStore, git: HermeticGit, predecessor: dict[str, Any], k1: str,
                 activation: Activation) -> Replacement:
    """C2: the predecessor's declared path set read at parent(K1) (old side) and at exact K1 (new side).

    The predecessor Candidate's declared artifact paths are the closed
    declaration set; the complete parent(K1) -> K1 delta holds no path outside
    it (else Class B). Every declared entry is rebuilt - inert ones included -
    with its old identity from parent(K1) and its new identity (and, for a file
    or a symlink, its bytes) from the stored K1; a gitlink and an absence carry
    no payload. The message is K1's persisted message, and the resulting tree is
    exactly K1's tree. No working-tree byte is read. The Context, Policy and
    activation are the current ones.
    """
    from .implementation import package_directory

    stored = workcommit._stored_commit(git, k1)
    if stored is None or len(stored.parents) != 1:
        raise _reconcile(f"{k1} is not a readable stored commit with exactly one parent", REASON_CLASS_C)
    parent = stored.parents[0]
    declared = [entry["path"] for entry in work_review.entries_of(predecessor)]
    foreign = sorted({item.path for item in _delta(git, parent, k1)} - set(declared))
    if foreign:
        raise _reconcile(f"Class B: K1 {k1} changes {foreign}, outside the operation-owned declaration", REASON_CLASS_B)
    width = len(k1)
    try:
        before = workcommit._tree_entries(git, parent, declared)
        after = workcommit._tree_entries(git, k1, declared)
    except StopError as exc:
        raise _reconcile(f"the trees of {parent} and {k1} cannot be read: {exc}", REASON_CLASS_C) from exc
    kinds = {"100644": ("file", "blob"), "100755": ("file", "blob"), "120000": ("symlink", "blob"),
             "160000": ("gitlink", "commit")}
    entries: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    for path in declared:
        old, new = before.get(path), after.get(path)
        if new is None:
            kind, mode, oid, data = "absent", "000000", None, None
        else:
            if new.mode not in kinds or kinds[new.mode][1] != new.type:
                raise _reconcile(f"{k1} holds {path} as {new.type} {new.mode}, which no Candidate kind names",
                                 REASON_CLASS_C)
            kind, mode, oid = kinds[new.mode][0], new.mode, new.oid
            data = workcommit._read_blob(git, new.oid) if kind in work_review.BYTE_KINDS else None
            if data is not None:
                payloads[path] = data
        entries.append(work_review.candidate_entry(path, None if old is None else (old.mode, old.oid), kind, mode, oid,
                                                   data, width))
    try:
        message = stored.message.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _reconcile(f"K1 {k1}'s persisted message is not UTF-8 text a Candidate can bind", REASON_CLASS_C) from exc
    content = work_review.content_for(
        entries, message=message, base_commit=parent,
        declared_result=[entry["path"] for entry in entries if entry["new_kind"] != "absent"],
        declared_deleted=[entry["path"] for entry in entries if entry["new_kind"] == "absent"],
    )
    if content["artifact_kind"] != work_review.ARTIFACT_RESULT:
        raise _reconcile(f"K1 {k1} carries no changing declared entry; Class A never synthesizes an empty adoption",
                         REASON_CLASS_C)
    base = declared_base(store, git, parent, predecessor["declared_base"]["branch"],
                         predecessor["declared_base"]["work"]["work_id"])
    candidate = work_review.candidate_record(content, base, activation.binding())
    snapshot = work_review.snapshot_for(work_review.snapshot_material(candidate, payloads))
    resulting = resulting_tree.resulting_tree_id(
        store, git, parent, resulting_tree.entries_from_records(work_review.entries_of(candidate)), payloads
    )
    if resulting != stored.tree:
        raise _reconcile(f"C2 composes {resulting}, not K1's exact tree {stored.tree}", REASON_CLASS_C)
    context = work_context.context_record(
        store.workline_root(), package_directory(store.workline_root()), activation.binding(),
        resulting_tree.root_tree_id(git, parent), stored.tree,
    )
    return Replacement(candidate, payloads, snapshot, context, parent, stored.tree)


def _incompatible_effect(record: WorkRecord) -> str | None:
    """A durable effect automatic Class A never reinterprets (F4 §11.18.7, §26.18), or None."""
    if any(effect.get("kind") == "git_push" for effect in record.effects):
        return "a publication effect is already durable"
    if (_terminal_stage(record) is not None or record.one_stage(f"{record.work_id}:finalize") is not None
            or record.notes.get(NOTE_TERMINAL_PROOF) is not None):
        return "a terminal lifecycle, Consumption or terminal commit stage is already durable"
    for effect in record.effects:
        event = (effect.get("payload") or {}).get("record") if effect.get("kind") == "append_event" else None
        if isinstance(event, dict) and event.get("type") in WORK_TERMINAL_EVENTS:
            return "a Work terminal event is already durable"
    return None


def classify_post_commit(session: "_Session", sealed: Sealed, git: HermeticGit, k1: str,
                         failure: ReconcileRequired | None = None) -> PostCommit:
    """Class A1 / A2 / B / C of an exact K1 whose normal C-2(K1) failed (F4 §11.3, §26.8); it writes nothing.

    The hard safety facts first, each on its own: the exact operation-owned K1
    (C-1 of this mutation's S-c1), no incompatible durable publication or
    terminal effect, its one raw parent, the declared branch holding exactly K1,
    the complete delta closed over the operation-owned declaration (else B), the
    first Run sealed and its Receipt current, unsuperseded and unconsumed, the
    Review namespace canonical and the Run's records unchanged at parent(K1) and
    K1, the RAW lineage, the activation, the declared base, and C2 reconstructible
    from committed objects. Only then:

    ```text
    A1  K1's delta, containment or message is not the Candidate's - every byte still operation-owned
    A2  K1 is exactly the Candidate, and its Context, Effective Policy or Evidence no longer re-derives
    ```

    and only an A whose approved destination does not already hold K1 is
    adoptable. A malformed namespace, missing records, a contradictory
    activation, an existing Consumption, unknown destination state or foreign
    lineage is never downgraded into A.
    """
    store, mutation = session.store, session.mutation
    defaults = {CLASS_B: REASON_CLASS_B, NOT_ELIGIBLE: REASON_CLASS_A_INELIGIBLE, ESCAPED: REASON_ALREADY_PUBLISHED}

    def refuse(kind: str, detail: str, reason: str | None = None) -> PostCommit:
        fallback = failure.reason if failure is not None and failure.reason else REASON_CLASS_C
        return PostCommit(kind, reason or defaults.get(kind) or fallback, detail)

    try:
        record = work_record(mutation.record)
    except ReconcileRequired as exc:
        return refuse(CLASS_C, f"the START record does not read as one Work completion ({_stripped(exc)})")
    run, base = record.run, sealed.material.base
    work_id, branch = run.work_id, base["branch"]
    if record.adopted or record.notes.get(NOTE_CLASS_A) is not None or run.review_run_id != sealed.run.review_run_id:
        return refuse(CLASS_C, "the record already holds a Class-A replacement, or names another Run")
    # the exact operation-owned K1 (C-1)
    try:
        effect = _commit_effect(record, record.one_stage(f"{work_id}:results"))
    except ReconcileRequired as exc:
        return refuse(CLASS_C, _stripped(exc))
    payload = (effect or {}).get("payload") or {}
    if (effect is None or effect.get("applied") is not True or effect.get("commit_id") != k1
            or effect.get(workcommit.PREPARED_COMMIT) != k1 or payload.get("mode") != workcommit.CONTRACT
            or payload.get("plan_class") != workcommit.CLASS_RESULT or payload.get("branch") != branch):
        return refuse(CLASS_C, f"{k1} is not shown to be the result commit this mutation's own S-c1 made (C-1)")
    # no incompatible durable effect: automatic Class A is unavailable behind one
    incompatible = _incompatible_effect(record)
    if incompatible is not None:
        return refuse(NOT_ELIGIBLE, f"{incompatible}; it is never rewritten, deleted or followed by a replacement")
    # the stored K1, exactly one raw parent, the one S-c1 recorded and prepared on
    stored = workcommit._stored_commit(git, k1)
    if (stored is None or len(stored.parents) != 1 or stored.parents[0] != payload.get("base_head")
            or stored.parents[0] != effect.get(workcommit.PREPARED_PARENT)):
        return refuse(CLASS_C, f"{k1} is not one stored commit on the parent its S-c1 recorded")
    parent = stored.parents[0]
    # the expected branch holds exactly K1: the adoption range begins at K1
    try:
        head_ref, tip = workcommit._head_ref(git), workcommit.ref_value(git, branch)
    except ReconcileRequired as exc:
        return refuse(CLASS_C, _stripped(exc))
    if head_ref != branch or tip != k1:
        return refuse(CLASS_C, f"HEAD is on {head_ref} and {branch} is {tip}, not exactly K1 {k1}")
    # the complete delta, closed over the operation-owned declaration
    try:
        delta = _delta(git, parent, k1)
    except ReconcileRequired as exc:
        return refuse(CLASS_C, _stripped(exc))
    changed = [item.path for item in delta]
    if any(item.status not in _STATUS for item in delta) or len(set(changed)) != len(changed):
        return refuse(CLASS_C, "K1's complete delta holds an entry no Candidate status names")
    declared = {entry["path"] for entry in work_review.entries_of(sealed.material.candidate)}
    foreign = sorted(set(changed) - declared)
    if foreign:
        return refuse(CLASS_B, f"K1 changes {foreign}, outside the operation-owned declaration")
    if sorted(changed, key=workcommit._utf8) != list(payload.get("paths") or []):
        return refuse(CLASS_C, "K1's complete delta is not the path set its S-c1 recorded")
    # the first Run, its Receipt, the Review namespace and the committed state at parent(K1) and K1
    try:
        chain = _chain(store, run)
        if chain is None:
            raise _reconcile(f"Work Review Run {run.review_run_id} has no chain")
        _require_shape(run, chain)
        if len(chain.generations) != work_review.SEAL_GENERATION:
            raise _reconcile(f"Work Review Run {run.review_run_id} is not exactly accepted, settled and sealed")
        checkout.require_namespace_readable(store)
        review = ReviewStore(store)
        if review.supersession_exists(run.receipt_id) or review.read_bytes(review_paths.gate_rel(run.review_run_id, 4)):
            raise _reconcile(f"Receipt {run.receipt_id} is already superseded or its Run invalidated")
        if run.receipt_id in review.consumption_by_receipt():
            raise _reconcile(f"Receipt {run.receipt_id} is already consumed")
        at_parent, at_k1 = CommittedRecords(store, git, parent), CommittedRecords(store, git, k1)
        material = _material_at(at_k1, record, "A")
        _material_at(at_parent, record, "A")
        paths = run_record_paths(run, material.chain)
        if _record_bytes(at_parent, paths) != _record_bytes(at_k1, paths):
            raise _reconcile("the Run's records are not held unchanged at parent(K1) and K1")
        _namespace_clean(at_parent, run, "A")
        _namespace_clean(at_k1, run, "A")
        if any(consumption.receipt_id == run.receipt_id for consumption in at_k1.consumptions()):
            raise _reconcile(f"K1 holds a Consumption of Receipt {run.receipt_id}")
        _require_receipt_current(material, record, "A")
        require_lineage(git, run, material.chain, base, parent)
        activation = _activation_at(store, git, at_parent, material, "A")
        if session.activation is None or session.activation.binding() != activation.binding():
            raise _reconcile("the activation proven at entry is not the one the Run binds")
        if declared_base(store, git, base["base_commit"], branch, work_id) != base:
            raise _reconcile("declared_base does not re-derive at declared_base.base_commit")
        if {**declared_base(store, git, parent, branch, work_id), "base_commit": base["base_commit"]} != base:
            raise _reconcile(f"declared_base does not re-derive identically at {parent}")
        state = committed_view_at(store, git, k1).work_state(work_id)
        if state.state != "in_progress" or not state.has_target:
            raise _reconcile(f"{work_id} does not hold its target in progress at {k1}")
    except StopError as exc:
        return refuse(CLASS_C, _stripped(exc) if isinstance(exc, ReconcileRequired) else str(exc))
    # C2 can be frozen exactly from committed objects
    try:
        _replacement(store, git, sealed.material.candidate, k1, activation)
        differences = _artifact_differences(git, material, parent, k1, stored)
        surfaces = _currency_surfaces(store, git, material, activation)
    except ReconcileRequired as exc:
        return refuse(CLASS_B if exc.reason == REASON_CLASS_B else CLASS_C, _stripped(exc))
    except StopError as exc:
        return refuse(CLASS_C, f"the replacement Candidate cannot be frozen from K1: {exc}")
    if differences:
        kind, reason = CLASS_A1, "a1:" + ",".join(differences)
    elif surfaces:
        kind, reason = CLASS_A2, "a2:" + ",".join(surfaces)
    else:
        return refuse(CLASS_C, "K1 is exactly the reviewed artifact and its authorization re-derives, so the normal "
                               "proof failed for a reason Class A never covers")
    # the remote-publication precondition: never adopt a K1 the approved destination already holds
    where = _destination_state(session, k1, branch)
    if where == "holds":
        return refuse(ESCAPED, f"the approved destination already holds K1 {k1}: an unauthorized / historical "
                               "publication escape - no history rewrite, no retroactive authorization, no adoption")
    if where == "divergent":
        return refuse(CLASS_C, f"the approved destination's {branch} holds another history than K1 {k1}",
                      REASON_DESTINATION_DIVERGENT)
    return PostCommit(kind, reason, f"{kind}: {reason}", parent, where)


CHECKPOINT_FIELDS = (
    "contract", "version", "classification", "reason", "k1", "parent_k1", "branch", "old_review_run_id",
    "old_receipt_id", "old_candidate_hash", "predecessor_review_run_id", "result_stage", "result_effect_seq",
    "durable_effects", "publication_effects", "terminal_effects", "destination",
)


def _post_commit(session: "_Session", sealed: Sealed, git: HermeticGit, k1: str, failure: ReconcileRequired) -> Any:
    """K1 exists and C-2(K1) failed: classify; reconcile anything not adoptable; else checkpoint and adopt."""
    found = classify_post_commit(session, sealed, git, k1, failure)
    if not found.adoptable:
        raise ReconcileRequired(
            f"{_stripped(failure)}; the post-commit classification is {found.kind}: {found.detail}: reconcile required",
            reason=found.reason,
        )
    mutation, run = session.mutation, sealed.run
    record = work_record(mutation.record)
    stage = record.one_stage(f"{run.work_id}:results")
    effect = _commit_effect(record, stage) or {}
    # F4 §11.18.3: the durable checkpoint, after strict eligibility and the remote precondition, before old G4
    _write_note(mutation, NOTE_CLASS_A, {
        "contract": CLASS_A_CONTRACT, "version": CLASS_A_VERSION,
        "classification": found.kind, "reason": found.reason,
        "k1": k1, "parent_k1": found.parent, "branch": sealed.material.base["branch"],
        "old_review_run_id": run.review_run_id, "old_receipt_id": run.receipt_id,
        "old_candidate_hash": sealed.chain.generations[0].candidate_hash,
        "predecessor_review_run_id": run.review_run_id,
        "result_stage": stage, "result_effect_seq": effect.get("seq"),
        "durable_effects": len(mutation.effects), "publication_effects": 0, "terminal_effects": 0,
        "destination": found.destination,
    })
    return _adopt(session, run)


def _checkpoint_facts(record: WorkRecord, notes: dict[str, Any]) -> dict[str, Any]:
    """The Class-A checkpoint, held against the durable record it names; reconcile on any contradiction."""
    note = notes.get(NOTE_CLASS_A)
    initial = record.initial or record.run
    if (not isinstance(note, dict) or set(note) != set(CHECKPOINT_FIELDS) or note["contract"] != CLASS_A_CONTRACT
            or note["version"] != CLASS_A_VERSION or note["classification"] not in (CLASS_A1, CLASS_A2)):
        raise _reconcile(f"START mutation {record.mutation_id}'s Class-A checkpoint is not of the "
                         f"{CLASS_A_CONTRACT} shape", REASON_CLASS_C)
    if (note["old_review_run_id"] != initial.review_run_id or note["predecessor_review_run_id"] != initial.review_run_id
            or note["old_receipt_id"] != initial.receipt_id):
        raise _reconcile("the Class-A checkpoint names another first Run or Receipt than the record holds",
                         REASON_CLASS_C)
    found = [effect for effect in record.effects if effect.get("stage") == note["result_stage"]]
    if (len(found) != 1 or found[0].get("kind") != "git_commit" or found[0].get("seq") != note["result_effect_seq"]
            or found[0].get("applied") is not True or found[0].get("commit_id") != note["k1"]
            or found[0].get(workcommit.PREPARED_COMMIT) != note["k1"]
            or (found[0].get("payload") or {}).get("base_head") != note["parent_k1"]
            or (found[0].get("payload") or {}).get("branch") != note["branch"]
            or (found[0].get("payload") or {}).get("plan_class") != workcommit.CLASS_RESULT):
        raise _reconcile("the Class-A checkpoint's K1 is not the result commit the record's S-c1 made",
                         REASON_CLASS_C)
    earlier = record.effects[: int(note["durable_effects"]) if isinstance(note["durable_effects"], int) else 0]
    if any(effect.get("kind") == "git_push" for effect in earlier) or note["publication_effects"] != 0 \
            or note["terminal_effects"] != 0:
        raise _reconcile("the Class-A checkpoint was not recorded before every publication and terminal effect",
                         REASON_CLASS_C)
    return note


def _require_checkpoint(mutation: Mutation, initial: WorkRun, chain: Any, material: RunMaterial,
                        git: HermeticGit) -> dict[str, Any]:
    """The checkpoint, validated against immutable committed state before any invalidation or replacement.

    Read against the first Run alone, so a successor reservation an interruption
    left half made (its task or Receipt id not yet reserved) never keeps the
    replacement from being continued.
    """
    notes = dict(mutation.record.get("notes") or {})
    record = WorkRecord(mutation.id, initial, mutation.effects, notes, dict(mutation.record.get("reserved_ids") or {}))
    note = _checkpoint_facts(record, notes)
    if chain.generations[0].candidate_hash != note["old_candidate_hash"] or material.base["branch"] != note["branch"]:
        raise _reconcile("the Class-A checkpoint names another Candidate or branch than the first Run binds",
                         REASON_CLASS_C)
    stored = workcommit._stored_commit(git, note["k1"])
    if stored is None or stored.parents != (note["parent_k1"],):
        raise _reconcile(f"the immutable K1 {note['k1']} the checkpoint names is missing or not on its parent",
                         REASON_CLASS_C)
    return note


def _expected_invalidation(run: WorkRun, chain: Any) -> tuple[records.GateGeneration, records.Supersession]:
    """The exact generation 4 and Supersession(R1) a Class-A replacement writes (F4 §11.18.4)."""
    third = chain.generation(work_review.SEAL_GENERATION)
    if not third.sealed or third.receipt_id != run.receipt_id:
        raise _reconcile(f"Work Review Run {run.review_run_id} is not sealed issuing Receipt {run.receipt_id}",
                         "review_chain_invalid")
    gate_four = replace(
        third, generation=INVALIDATION_GENERATION, previous_generation=work_review.SEAL_GENERATION,
        previous_digest=chain.digests[work_review.SEAL_GENERATION - 1],
        evidence_digest=serialize.digest(work_review.invalidation_evidence_record(run.receipt_id, CLASS_A_REASON)),
        status=records.GATE_STATUS_OPEN, receipt_id=None, authorized_operation_stage=None,
    )
    return gate_four, records.Supersession(run.receipt_id, run.review_run_id, INVALIDATION_GENERATION, CLASS_A_REASON)


def _invalidate_predecessor(session: "_Session", run: WorkRun, material: RunMaterial, checkpoint: dict[str, Any],
                            git: HermeticGit) -> None:
    """Old G4 + Supersession(R1), one generation mutation, exactly once (F4 §11.18.1, §11.18.4, §26.12).

    A pending G4 generation mutation is finished first. A committed G4 must be
    exactly the one this replacement writes. Before it is written, every
    precondition is derived again now: the old chain exactly sealed, R1 current
    and unsuperseded and unconsumed, no incompatible durable effect, the branch
    still exactly K1, and K1 not published.
    """
    store, mutation = session.store, session.mutation
    resolve_pending_generation(session, run)
    chain = _chain(store, run)
    if chain is None:
        raise _reconcile(f"Work Review Run {run.review_run_id} has no chain", "review_chain_invalid")
    _require_shape(run, chain)
    gate_four, supersession = _expected_invalidation(run, chain)
    review = ReviewStore(store)
    if chain.latest.generation == INVALIDATION_GENERATION:
        try:
            held = review.read_supersession(run.receipt_id)
        except ValidationError as exc:
            raise _reconcile(f"generation 4 of {run.review_run_id} has no Supersession that reads: {exc}") from exc
        if chain.latest.to_record() != gate_four.to_record() or held.to_record() != supersession.to_record():
            raise _reconcile(f"Work Review Run {run.review_run_id}'s generation 4 or Supersession is not the Class-A "
                             "invalidation this replacement writes", "review_chain_invalid")
        return
    if chain.latest.generation != work_review.SEAL_GENERATION:
        raise _reconcile(f"Work Review Run {run.review_run_id} is not sealed under its Class-A checkpoint",
                         "review_chain_invalid")
    incompatible = _incompatible_effect(work_record(mutation.record))
    if incompatible is not None:
        raise _reconcile(f"{incompatible}; old G4 is not written behind it", REASON_CLASS_A_INELIGIBLE)
    if review.supersession_exists(run.receipt_id) or run.receipt_id in review.consumption_by_receipt():
        raise _reconcile(f"Receipt {run.receipt_id} is already superseded or consumed", REASON_CLASS_C)
    k1, branch = checkpoint["k1"], checkpoint["branch"]
    if workcommit._head_ref(git) != branch or workcommit.ref_value(git, branch) != k1:
        raise _reconcile(f"{branch} no longer holds exactly K1 {k1}, the Class-A checkpoint's lineage", REASON_CLASS_C)
    where = _destination_state(session, k1, branch)
    if where == "holds":
        raise _reconcile(f"the approved destination already holds K1 {k1}: an unauthorized / historical publication "
                         "escape; nothing is invalidated or adopted", REASON_ALREADY_PUBLISHED)
    if where == "divergent":
        raise _reconcile(f"the approved destination's {branch} holds another history than K1 {k1}",
                         REASON_DESTINATION_DIVERGENT)
    _start_generation(session, run, INVALIDATION_GENERATION, gate_four,
                      [(review_paths.supersession_rel(run.receipt_id), supersession.to_record())], material.base,
                      receipt_id=run.receipt_id)


@dataclass(frozen=True)
class AdoptionLineage:
    """The adoption range above K1: the generation commits matched in order, and what follows them."""

    commits: tuple[str, ...]  # old G4, then the successor's G1, G2, G3 (= K_adopt), as far as they exist
    rest: tuple[str, ...]


def _is_generation_commit(store: ProjectStore, git: HermeticGit, parent: str, commit: str, run: WorkRun,
                          generation: int) -> bool:
    """Whether ``commit`` is exactly ``run``'s generation ``generation`` commit, one commit on ``parent``.

    Its complete delta must be exactly the Review records that generation adds
    - all added, mode 100644 - as the generation's own committed chain names
    them, and nothing else (F4 §11.18.2, §26.15).
    """
    if _parents(git, commit) != (parent,):
        return False
    try:
        chain = CommittedRecords(store, git, commit).gate_chain(run.review_run_id)
    except ValidationError:
        return False
    if chain is None or chain.latest.generation != generation:
        return False
    latest = chain.latest
    wanted = {review_paths.gate_rel(run.review_run_id, generation)}
    if generation == records.FIRST_GENERATION:
        tasks = [str(task["task_id"]) for task in latest.accepted_tasks]
        if tasks != [run.task_id]:
            return False
        wanted |= {review_paths.candidate_snapshot_rel(latest.candidate_hash), review_paths.task_input_rel(run.task_id)}
    if generation == work_review.SEAL_GENERATION:
        if latest.receipt_id != run.receipt_id:
            return False
        wanted.add(review_paths.receipt_rel(run.receipt_id))
    if generation == INVALIDATION_GENERATION:
        wanted.add(review_paths.supersession_rel(run.receipt_id))
    try:
        delta = _delta(git, parent, commit)
    except ReconcileRequired:
        return False
    return (sorted(item.path for item in delta) == sorted(wanted)
            and all(item.status == "A" and item.new_mode == "100644" for item in delta))


def _adoption_lineage(store: ProjectStore, git: HermeticGit, record: WorkRecord, k1: str, head: str) -> AdoptionLineage:
    """The RAW single-parent range (K1, head], matched against K1 -> old G4 -> successor G1 -> G2 -> G3.

    Identity is positive proof from the stored objects - each commit exactly one
    commit on the one before, each delta exactly its generation's records - and
    never HEAD, a message, recency or path similarity (F4 §11.18.9, §26.14).
    """
    walked = ancestry.raw_range(git, k1, head)
    if isinstance(walked, ancestry.Answer):
        raise _reconcile(f"the range ({k1}, {head}] is {walked.value}", REASON_CLASS_C)
    ordered = list(reversed(walked))
    initial = record.initial or record.run
    expected = [(initial, INVALIDATION_GENERATION)]
    if record.adopted:
        expected += [(record.run, generation) for generation in (1, 2, work_review.SEAL_GENERATION)]
    matched: list[str] = []
    previous = k1
    for commit in ordered:
        if len(matched) == len(expected):
            break
        run, generation = expected[len(matched)]
        if not _is_generation_commit(store, git, previous, commit, run, generation):
            break
        matched.append(commit)
        previous = commit
    return AdoptionLineage(tuple(matched), tuple(ordered[len(matched):]))


def _adopted_parent(store: ProjectStore, git: HermeticGit, record: WorkRecord, k1: str | None, parent: str,
                    item: str) -> str:
    """K_adopt, proven again for a Class-A terminal: exactly K1 -> old G4 -> G1 -> G2 -> G3 up to ``parent``."""
    adopted = record.notes.get(NOTE_ADOPTED_PROOF)
    try:
        checkpoint = _checkpoint_facts(record, record.notes)
    except ReconcileRequired as exc:
        raise _proof_failed(item, _stripped(exc)) from exc
    if (not isinstance(k1, str) or checkpoint["k1"] != k1 or not isinstance(adopted, dict)
            or adopted.get("contract") != ADOPTED_PROOF_CONTRACT or adopted.get("k1") != k1):
        raise _proof_failed(item, "the Class-A checkpoint and the adopted-result proof do not both name exact K1")
    lineage = _adoption_lineage(store, git, record, k1, parent)
    if len(lineage.commits) != 4 or lineage.rest:
        raise _proof_failed(item, f"the range (K1, {parent}] is not exactly old G4 and the successor's G1, G2 and G3")
    if adopted.get("k_adopt") != lineage.commits[-1]:
        raise _proof_failed(item, "the adopted-result proof names another K_adopt than the adoption range proves")
    return lineage.commits[-1]


def prove_adopted_result(store: ProjectStore, git: HermeticGit, mutation_record: dict[str, Any],
                         k_adopt: str) -> dict[str, Any]:
    """``review_work_adopted_result_proof``: the adopted-result proof of exact ``k_adopt`` (F4 §26.15).

    Re-executed from the durable record and the committed objects alone, so it
    runs again before the publication is recorded and immediately before it is
    applied; its note is a binding, never timeless truth. It proves:

    ```text
    AP-1  the Class-A checkpoint and the exact operation-owned K1 (C-1 of the record's S-c1), one parent
    AP-2  the RAW range (K1, K_adopt] is exactly old G4, successor G1, G2, G3; the branch holds K_adopt
    AP-3  the successor at K_adopt: sealed, R2 for start:work-terminal, its v2 request setting aside the
          first Run with the Class-A reason
    AP-4  the first Run invalidated at K_adopt by exactly its generation 4 and Supersession(R1)
    AP-5  C2 binds exact K1: base parent(K1), delta / containment / message exactly K1's, resulting tree K1's
    AP-6  R2 current for C2: Receipt, settlement, activation, Context, Policy, Evidence, declared base
    AP-7  the namespace canonical, no Consumption of R1 or R2, no terminal stage, the Work still in progress
    AP-8  the approved destination identity
    ```
    """
    from .destination import ensure_push_destination

    record = work_record(mutation_record)
    if not record.adopted or record.initial is None:
        raise _proof_failed("AP-1", "the record holds no Class-A successor")
    try:
        checkpoint = _checkpoint_facts(record, record.notes)
    except ReconcileRequired as exc:
        raise _proof_failed("AP-1", _stripped(exc)) from exc
    k1, branch, work_id, old = checkpoint["k1"], checkpoint["branch"], record.work_id, record.initial
    stored = workcommit._stored_commit(git, k1)
    if stored is None or stored.parents != (checkpoint["parent_k1"],):
        raise _proof_failed("AP-1", f"K1 {k1} is not the stored commit on the parent the checkpoint names")
    parent = stored.parents[0]
    # AP-2
    lineage = _adoption_lineage(store, git, record, k1, k_adopt)
    if len(lineage.commits) != 4 or lineage.rest or lineage.commits[-1] != k_adopt:
        raise _proof_failed("AP-2", f"(K1, {k_adopt}] is not exactly old G4 and the successor's G1, G2 and G3")
    if workcommit._head_ref(git) != branch:
        raise _proof_failed("AP-2", f"HEAD is not on {branch}")
    tip = workcommit.ref_value(git, branch)
    if tip is None or ancestry.raw_descends_from(git, tip, k_adopt) is not True:
        raise _proof_failed("AP-2", f"{branch} does not hold {k_adopt}")
    # AP-3
    at = CommittedRecords(store, git, k_adopt)
    material = _material_at(at, record, "AP-3")
    try:
        set_aside = work_review.request_set_aside(material.task_input.request_envelope,
                                                  review_run_id=record.run.review_run_id)
    except ValidationError as exc:
        raise _proof_failed("AP-3", str(exc)) from exc
    if [item for item in set_aside if item["review_run_id"] == old.review_run_id] != [
            {"review_run_id": old.review_run_id, "reason": CLASS_A_REASON}]:
        raise _proof_failed("AP-3", "the successor's request does not set aside the first Run, exactly once, as its "
                                    "Class-A replacement")
    own = own_run_ids(record.reserved)
    for item in set_aside:
        if item["review_run_id"] == old.review_run_id:
            continue
        # any other entry names another matching Run of this Work - never this START's own Run or the successor;
        # the reason it was set aside is recovery's classification and is not derived again here
        try:
            other = at.read_gate(item["review_run_id"], records.FIRST_GENERATION)
        except ValidationError as exc:
            raise _proof_failed("AP-3", f"the successor sets aside {item['review_run_id']}, which {k_adopt} does not "
                                        f"hold as a Review Run: {exc}") from exc
        if (item["review_run_id"] in own or other.review_kind != work_review.REVIEW_KIND
                or other.operation_identity != work_review.operation_identity(work_id)):
            raise _proof_failed("AP-3", f"the successor sets aside {item['review_run_id']}, which is not another "
                                        "matching Run of this Work")
    # AP-4
    try:
        old_chain = at.gate_chain(old.review_run_id)
        held = at.read_supersession(old.receipt_id)
    except ValidationError as exc:
        raise _proof_failed("AP-4", f"the first Run's records at {k_adopt} do not read: {exc}") from exc
    if old_chain is None or len(old_chain.generations) != INVALIDATION_GENERATION:
        raise _proof_failed("AP-4", f"{k_adopt} does not hold the first Run invalidated at generation 4")
    gate_four, supersession = _expected_invalidation(old, old_chain)
    if old_chain.latest.to_record() != gate_four.to_record() or held.to_record() != supersession.to_record():
        raise _proof_failed("AP-4", "the first Run's generation 4 or Supersession is not the Class-A invalidation")
    # AP-5
    base = material.base
    if (material.content["artifact_kind"] != work_review.ARTIFACT_RESULT or base["base_commit"] != parent
            or base["branch"] != branch or base["work"]["work_id"] != work_id):
        raise _proof_failed("AP-5", "C2 is not a result-bearing Candidate declared on parent(K1)")
    capability = material.context["review_checkout_capability"]
    if capability["resulting_tree"] != stored.tree or capability["base_tree"] != resulting_tree.root_tree_id(git, parent):
        raise _proof_failed("AP-5", "C2's Context does not bind K1's exact tree over parent(K1)'s")
    differences = _artifact_differences(git, material, parent, k1, stored)
    if differences:
        raise _proof_failed("AP-5", f"C2 is not exactly K1 ({', '.join(differences)})")
    # AP-6
    _require_receipt_current(material, record, "AP-6")
    activation = _activation_at(store, git, at, material, "AP-6")
    _require_identities(store, git, material, activation, "AP-6")
    if declared_base(store, git, parent, branch, work_id) != base:
        raise _proof_failed("AP-6", f"declared_base does not re-derive at {parent}")
    # AP-7
    _namespace_clean(at, record.run, "AP-7")
    receipts = {old.receipt_id, record.run.receipt_id}
    if any(consumption.receipt_id in receipts for consumption in (*at.consumptions(), *ReviewStore(store).consumptions())):
        raise _proof_failed("AP-7", "a Consumption of the first or the successor Receipt already exists")
    if _terminal_stage(record) is not None:
        raise _proof_failed("AP-7", "a terminal stage is recorded before the adopted-result publication")
    state = committed_view_at(store, git, k_adopt).work_state(work_id)
    if state.state != "in_progress" or not state.has_target:
        raise _proof_failed("AP-7", f"{work_id} does not hold its target in progress at {k_adopt}")
    # AP-8
    destination = ensure_push_destination(store)
    first = material.chain.generations[0]
    return {
        "contract": ADOPTED_PROOF_CONTRACT, "candidate_hash": first.candidate_hash,
        "k1": k1, "parent_k1": parent, "branch": branch,
        "old_review_run_id": old.review_run_id, "old_receipt_id": old.receipt_id,
        "old_generation_4_commit": lineage.commits[0],
        "successor_review_run_id": record.run.review_run_id, "successor_receipt_id": record.run.receipt_id,
        "successor_generation_commits": list(lineage.commits[1:]),
        "k_adopt": k_adopt,
        "review_context_hash": first.review_context_hash, "effective_policy_hash": first.effective_policy_hash,
        "evidence_digest": first.evidence_digest, "activation": activation.binding(),
        "destination": None if destination is None else {"remote": destination.remote, "locator": destination.locator},
    }


@dataclass(frozen=True)
class _Currency:
    current: bool
    stale: bool
    detail: str


def _recovery_currency(store: ProjectStore):
    """The Work currency a generation-1 / authorizing generation-2 Run is classified by: Context and Policy now."""
    from .implementation import package_directory

    def currency(found: Any) -> _Currency:
        first = found.chain.generations[0]
        p4_run = getattr(found, "contract", None) is not None
        try:
            task_input = ReviewStore(store).read_task_input(found.task_id)
            context = task_input.request_envelope["context"]
            if p4_run:
                context = work_review.inner_context(context)
            capability = context["review_checkout_capability"]
            recomputed = work_context.context_record(
                store.workline_root(), package_directory(store.workline_root()), context["activation"],
                capability["base_tree"], capability["resulting_tree"],
            )
        except (StopError, KeyError, TypeError, ValidationError) as exc:
            return _Currency(False, False, f"the Context cannot be recomputed ({exc})")
        policy = _p4_task_policy(task_input)  # the Run's own stored family policy, never the default (GAP-A)
        bound = serialize.digest(work_review.context_record_p4(recomputed, policy)) if p4_run \
            else work_context.context_hash(recomputed)
        if bound != first.review_context_hash:
            return _Currency(False, True, "review_context_changed")
        stored = p4.envelope_policy_hash(task_input.request_envelope) if p4_run else work_review.policy_hash()
        if stored != first.effective_policy_hash:
            return _Currency(False, True, "review_policy_changed")
        return _Currency(True, False, "current")

    return currency


def _require_recovery_selection(session: "_Session", initial: WorkRun, successor: WorkRun) -> Any:
    """Canonical recovery selection over every matching Work Run (F4 §11.12): exactly the successor, or none yet.

    The first Run must classify as invalidated; the successor, once it has a
    generation, as the one recoverable Run; and no other matching Run may be
    recoverable. Nothing is chosen by recency. The Discovery is returned: the
    successor's request names, besides its predecessor, every other matching
    Run it sets aside (§11.6).
    """
    from .review import planning, recovery

    store = session.store
    found = recovery.discover_work(store, work_review.operation_identity(initial.work_id),
                                   currency=_recovery_currency(store),
                                   owned=own_run_ids(session.mutation.record.get("reserved_ids") or {}))
    aside = {item["review_run_id"]: item["reason"] for item in found.set_aside}
    if aside.get(initial.review_run_id) != planning.SET_ASIDE_INVALIDATED:
        raise _reconcile(f"recovery selection does not classify {initial.review_run_id} invalidated "
                         f"({aside.get(initial.review_run_id)})", "review_recovery_ambiguous")
    expected = successor.review_run_id if _chain(store, successor) is not None else None
    selected = None if found.recoverable is None else found.recoverable.review_run_id
    if expected is not None and selected is None and successor.review_run_id in aside:
        raise _reconcile(
            f"the successor Work Review Run {successor.review_run_id} is {aside[successor.review_run_id]}; START does not "
            "terminalize an unauthorized completion and begins no further replacement (no repair loop)",
            "review_chain_invalid",
        )
    if selected != expected:
        raise _reconcile(f"recovery selection finds {selected} recoverable, and this START continues "
                         f"{expected or 'a successor not yet begun'}", "review_recovery_ambiguous")
    return found


def _freeze_replacement(session: "_Session", initial: WorkRun, material: RunMaterial, successor: WorkRun,
                        k1: str, git: HermeticGit, recovered: Any) -> None:
    """Successor generation 1: C2 from K1, the v2 request naming the first Run, Evidence, accept (F4 §26.13).

    The request names the predecessor with the Class-A reason, and every other
    matching Run recovery selection set aside with its own reason (§11.6).
    """
    store = session.store
    activation = session.activation
    if activation is None:
        raise _reconcile("a review-v1 START session holds no activation proven at its entry")
    replacement = _replacement(store, git, material.candidate, k1, activation)
    checkout.require_namespace_readable(store)
    candidate_hash = work_review.candidate_hash(replacement.candidate)
    reconstruction = work_review.read_material(replacement.snapshot, candidate_hash, len(k1))
    verified = work_verify.verify(store, git, reconstruction, resulting_tree_id=replacement.tree)
    context_hash = work_context.context_hash(replacement.context)
    policy_hash = work_review.policy_hash()
    envelope = work_review.request_envelope(
        replacement.candidate, replacement.context,
        [{"review_run_id": initial.review_run_id, "reason": CLASS_A_REASON}]
        + [dict(item) for item in recovered.set_aside
           if item["review_run_id"] not in (initial.review_run_id, successor.review_run_id)],
        review_run_id=successor.review_run_id,
    )
    task_input = work_review.task_input_for(
        task_id=successor.task_id, reviewer_identity=session.review.reviewer_identity,
        reviewer_version=session.review.reviewer_version, envelope=envelope, snapshot=replacement.snapshot,
        review_context_hash=context_hash, effective_policy_hash=policy_hash,
    )
    evidence = _evidence(git, replacement.candidate, replacement.snapshot, task_input, replacement.context,
                         context_hash, policy_hash, activation, verified, declared=True)
    successor.frozen = {"snapshot": replacement.snapshot, "task_input": task_input, "evidence": evidence,
                        "context": replacement.context}
    _accept(session, successor, replacement.candidate["declared_base"])


def _adopt(session: "_Session", initial: WorkRun) -> Any:
    """The F4 Class-A topology from the durable checkpoint to ``completed`` (F4 §11.18, §26.12 - §26.17).

    ```text
    checkpoint (validated)  -> old G4 + Supersession(R1)   -> successor reserved
    -> recovery selection   -> successor G1 (C2) / reviewer / G2 / capability / G3 + R2 (= K_adopt)
    -> adopted-result proof note -> (remote) exact K_adopt published
    -> terminal stage consuming R2 (result commit K1) -> K_terminal on K_adopt -> terminal proof
    -> (remote) exact K_terminal published -> recorded-completion proof -> completed
    ```

    Every step reads what is already durable first, so a resume continues at
    the earliest unsatisfied checkpoint and never decides anything again. A
    non-authorizing successor stops, exactly as a first Run does (no P4 repair).
    """
    from .start import StartResult

    store, mutation = session.store, session.mutation
    git = hermetic_module.enter(store)
    remote = session.destination is not None
    old_chain = _chain(store, initial)
    if old_chain is None:
        raise _reconcile(f"Work Review Run {initial.review_run_id} has no chain", "review_chain_invalid")
    old_material = run_material(store, initial, old_chain)
    checkpoint = _require_checkpoint(mutation, initial, old_chain, old_material, git)
    k1, branch, work_id = checkpoint["k1"], checkpoint["branch"], initial.work_id
    _invalidate_predecessor(session, initial, old_material, checkpoint, git)
    successor = reserve_successor(mutation, initial)
    record = work_record(mutation.record)
    if not record.adopted or record.run.review_run_id != successor.review_run_id:
        raise _reconcile("the START record does not select the reserved successor", REASON_CLASS_C)
    terminal_recorded = _terminal_stage(record) is not None
    if not terminal_recorded:
        resolve_pending_generation(session, successor)
        recovered = _require_recovery_selection(session, initial, successor)
        # the adoption range so far is exactly K1 -> old G4 [-> the successor's generations], up to the tip
        reached = _chain(store, successor)
        tip = workcommit.ref_value(git, branch)
        so_far = _adoption_lineage(store, git, record, k1, tip) if tip is not None else None
        expected = 1 + (0 if reached is None else reached.latest.generation)
        if so_far is None or len(so_far.commits) != expected or (so_far.rest and expected < 4):
            raise _reconcile(f"{branch} is not exactly the adoption range K1 -> old G4 -> successor generations so far",
                             REASON_CLASS_C)
        if reached is None:
            _freeze_replacement(session, initial, old_material, successor, k1, git, recovered)
    sealed = _continue(session, successor)
    tip = workcommit.ref_value(git, branch)
    if tip is None:
        raise _reconcile(f"{branch} names no commit", REASON_CLASS_C)
    lineage = _adoption_lineage(store, git, record, k1, tip)
    if len(lineage.commits) != 4:
        raise _reconcile(f"{branch} does not hold K1 -> old G4 -> successor G1 -> G2 -> G3 exactly", REASON_CLASS_C)
    k_adopt = lineage.commits[-1]
    made = successor.generation_commits.get(work_review.SEAL_GENERATION)
    if made is not None and made != k_adopt:
        raise _reconcile(f"the successor's generation 3 commit {made} is not the K_adopt the lineage proves {k_adopt}",
                         REASON_CLASS_C)
    if not terminal_recorded:
        prefix = f"{work_id}:adopted-publication"
        if work_record(mutation.record).one_stage(prefix) is None and lineage.rest:
            raise _reconcile(f"{branch} moved past K_adopt {k_adopt} before its publication", REASON_CLASS_C)
        # the adopted-result proof, re-derived until the terminal stage exists; its note binds exact K_adopt
        _write_note(mutation, NOTE_ADOPTED_PROOF, prove_adopted_result(store, git, mutation.record, k_adopt))
        if remote:
            if work_record(mutation.record).one_stage(prefix) is None and \
                    _destination_state(session, k_adopt, branch) != "holds":
                where = _destination_state(session, k1, branch)
                if where == "holds":
                    raise _reconcile(f"the approved destination holds K1 {k1} without its replacement authorization: an "
                                     "unauthorized / historical publication escape", REASON_ALREADY_PUBLISHED)
                if where == "divergent":
                    raise _reconcile(f"the approved destination's {branch} holds another history than K1 {k1}",
                                     REASON_DESTINATION_DIVERGENT)
            _publish_stage(session, prefix, k_adopt, branch)  # exact K_adopt, never K1 alone, never the tip
    else:
        note = mutation.note(NOTE_ADOPTED_PROOF)
        if not isinstance(note, dict) or note.get("k_adopt") != k_adopt:
            raise _reconcile("the terminal stage is recorded without the adopted-result proof note of exact K_adopt")
    consumption_id = mutation.reserve_id(gate.review_consumption_key(successor.receipt_id), "review_consumption")
    consumption_path = review_paths.consumption_rel(consumption_id)
    if consumption_path not in mutation.scope.files:
        mutation.extend_scope(files=[consumption_path])
    k_terminal = _terminal(session, sealed, git, sealed.chain, consumption_id, k1, k_adopt=k_adopt)
    _write_note(mutation, NOTE_TERMINAL_PROOF, prove_terminal(store, git, mutation.record, k_terminal))
    if remote:
        _publish_stage(session, f"{work_id}:finalize-publication", k_terminal, branch)
    require_recorded_completion(session, sealed, git, k_terminal, consumption_path)
    session.completed.append(work_id)
    view = ProjectView.load(store)
    return StartResult("completed", work_id, mutation.id, tuple(session.completed), view.works[work_id].phase_id,
                       head=k_terminal)


# =========================================================================== P4 Work (§12 / §27)
#
# The P4 START flow: the same START mutation, generation mutations and terminal
# path as v1 (S-c1 / K1, Consumption, S-c2 / K2, publication), with the P4 Run
# shape between the freeze and the seal. Dispatch is by the START mutation's
# durable marker (G-6 Option M, ``work_invocation.contract_of``); a Run's own
# contract is the one its generation-1 TaskInputs bind. A P4 Run never enters the
# F4 Class-A path (G-3): a stale P4 seal is invalidated by its own G6.
#
# ```text
# freeze (unchanged steps 5a-12) -> G1 discovery -> G2 + raw reports -> G3 adjudication -> G4 + adjudication
#   AUTHORIZATION_READY -> capability (15a) -> G5 seal + Receipt (generation 5) -> terminal path
#   REPAIR_REQUIRED     -> G5 Repair Batch + repair accept -> G6 Repair Result + Candidate N+1
#                          -> START adopts N+1 onto the declared result paths (G-5) -> successor Run
#   HUMAN_WAIT          -> STOP, the START stays pending; a Human decision sets the Run aside (G-4)
# ```

STATE_P4 = "p4_cycle"
#: The START mutation's durable G-4 bindings: waiting Review Run ID -> the Human decision that exits its wait
#: (P4-R7). One binding per waiting Run, never one per mutation: a pending START may wait more than once.
NOTE_P4_DECISIONS = "p4_human_decisions"


# =========================================================================== Phase Integration Review (RB5 §32.14 -)

@dataclass(frozen=True)
class PhaseIntegrationReview:
    """The Phase Integration Review selector: ``start(..., phase_review=PhaseIntegrationReview(...))`` (§32.14).

    A separate selector, never an overload of the Work Formal Review ``review=``
    (whose semantics and activation are unchanged). It carries the P4 / P6
    discovery and adjudicator actor identities and versions of the
    ``review-v1-phase-integration-p4-v1`` contract, and - as RB6's Policy Review -
    no repair actor: a Phase Integration Run has no Repair Batch branch (domain
    repair is START's normal fix Work, §14.14). ``human_decision`` /
    ``decision_evidence`` are the G4 HUMAN_WAIT continuation inputs (R8);
    ``holdout_discovery`` the P6 holdout slots (R6-1). None of it is START slot
    identity: the START invocation is the same with or without it.
    """

    discovery: tuple[p4.DiscoveryBinding, ...]
    adjudicator: p4.ActorBinding
    human_decision: p4.HumanDecision | None = None
    contract: str = records.P4_PHASE_INTEGRATION_CONTRACT
    decision_evidence: tuple[p4.DecisionEvidence, ...] = ()
    holdout_discovery: tuple[p4.DiscoveryBinding, ...] = ()


def validate_phase_integration_review(phase_review: object) -> PhaseIntegrationReview:
    """The ``phase_review`` argument, validated before the lock and before any Project state is read (§32.14)."""
    if type(phase_review) is not PhaseIntegrationReview:
        raise ValidationError(f"phase_review must be a PhaseIntegrationReview, not {type(phase_review).__name__}",
                              code="review_contract_invalid")
    problems: list[str] = []
    if phase_review.contract != records.P4_PHASE_INTEGRATION_CONTRACT:
        problems.append(f"contract {phase_review.contract!r} is not {records.P4_PHASE_INTEGRATION_CONTRACT!r}")
    # No repair actor: as RB6's Policy Review selector, the adjudicator stands in the shared check's repair slot.
    problems.extend(p4.binding_problems(phase_review.discovery, phase_review.adjudicator, phase_review.adjudicator,
                                        phase_review.human_decision))
    problems.extend(p4.decision_evidence_problems(phase_review.decision_evidence, phase_review.human_decision))
    problems.extend(p4.holdout_binding_problems(phase_review.holdout_discovery, phase_review.discovery))
    if problems:
        raise ValidationError("invalid PhaseIntegrationReview: " + "; ".join(problems), code="review_contract_invalid")
    return phase_review


# --------------------------------------------------------------------------- the Run flow (I-5: §32.16 - §32.22, §32.29 - §32.31)
#
# START's own driver of the one Phase Integration Review Run of a marked integration it runs, under the registered
# contract review-v1-phase-integration-p4-v1, modelled on the P6 Policy Review owner - discovery -> adjudication ->
# seal, never a Repair Batch branch:
#
#   precheck (ordinary) -> R22 discovery (a fresh Run only) -> freeze (the Candidate over committed HEAD, its Context
#   and Effective Policy, durable in the START record) -> the integration's own opening lifecycle -> G1 accepted ->
#   G2 settled -> G3 adjudication accepted -> G4 settled with the one §32.22 disposition -> G5 sealed (Receipt),
#   AUTHORIZATION_READY only -> the terminal gate -> ONE terminal stage -> START's ordinary <Work>:finalize
#
# A G4 HUMAN_WAIT keeps the Run and the START pending (R8). A G4-terminal disposition (ruling OQ-C) ends the Run at
# G4 - final not_authorized, its P5 summary written in that G4, no Receipt - and START stops before any further
# effect; what START does next (domain repair planning, the confirmation structure) is I-6's.

#: The frozen material of each Integration Run this START mutation holds, keyed by Run (durable before its G1).
NOTE_INTEGRATION_FREEZE = "phase_integration_freeze"
#: The owner-measured Project-state digests around each actor launch of a Run (§14.10, §32.29), keyed by Run and
#: settling generation: the positive proof that the verification left persistent state untouched.
NOTE_INTEGRATION_MEASURED = "phase_integration_measured"
#: This START's durable Human-decision bindings, waiting Integration Run -> decision record (P4-R7, R8): bound
#: before the successor Run is reserved, one decision per waiting Run.
NOTE_INTEGRATION_DECISIONS = "phase_integration_human_decisions"
#: §32.19: the operation identity of an Integration Run is its integration Work's, whatever START mode runs it.
INTEGRATION_OPERATION = "start-phase-integration"
INTEGRATION_PROJECTION = "phase-integration-candidate-v1"
SCHEMA_INTEGRATION_CONTEXT = "review-phase-integration-context"
#: The verification adapter's identity and its declared side-effect contract (§32.29): verification-only, nothing
#: persistent allowed anywhere. The before / after proof is START's own measurement, never the adapter's report.
INTEGRATION_ADAPTER = "phase-integration-review-v1-p4"
#: What START does after each G4-terminal Integration Run, keyed by Run (R26, §32.23 / §32.25): decided once, kept
#: before its first effect, and finished from the record on resume - never decided again.
NOTE_INTEGRATION_FOLLOWUPS = "phase_integration_followups"
FOLLOWUP_REPAIR = "domain_repair"
FOLLOWUP_STRUCTURE = "confirmation_structure"
#: An ordinary completion makes a reviewed Phase generated-complete and no covering integration's consumed Review
#: can be cited (§32.35): no evidence is fabricated, nothing is recorded.
CODE_PHASE_EVIDENCE_UNAVAILABLE = "phase_evidence_unavailable"
#: The reconcile reason of phase_completion evidence a completion recorded that is not HEAD's committed basis (§32.39).
REASON_ACHIEVEMENT_BASIS_MISMATCH = "review_achievement_basis_mismatch"
#: The executor's answer to a domain repair context is not an IntegrationRepairPlan START accepts (§32.25).
CODE_INTEGRATION_REPAIR_PLAN_INVALID = "phase_integration_repair_plan_invalid"
#: The public-safe rationale of every future_work_link START's integration repair records (§32.26 / §32.50).
FIX_LINK_RATIONALE = "START's integration repair plan registered this fix Work for the Finding; provenance only."
#: A verification actor changed persistent Project state across its launch: nothing is settled.
CODE_INTEGRATION_SIDE_EFFECT = "phase_integration_verification_side_effect"


@dataclass(frozen=True)
class IntegrationAdjudicationReturn:
    """What the Phase Integration adjudicator returns (§32.21): the P4 adjudication and the ONE Phase outcome.

    The P4 part is normalized exactly as every P4 adjudication is; the Phase
    outcome (a ``review.integration.PhaseOutcome``, or its record) names the
    canonical Phase objective by its desired-state digest and never restates
    it. Both are judged together (``review.integration.integration_branch``)
    before anything is settled.
    """

    adjudication: p4.P4AdjudicationReturn
    phase_outcome: Any


@dataclass
class IntegrationRun:
    """One Integration Review Run this START holds, with the material it froze for it."""

    work_id: str
    review_run_id: str
    candidate: dict[str, Any]
    context: dict[str, Any]
    effective: dict[str, Any] | None
    policy: str
    set_aside: tuple[dict[str, str], ...] = ()
    receipt_id: str | None = None


def integration_operation_identity(work_id: str) -> str:
    """``start-phase-integration:`` + the digest of the integration's request identity (§32.19)."""
    from .review import integration as ri

    return f"{INTEGRATION_OPERATION}:{serialize.digest({'review_kind': ri.REVIEW_KIND, 'target_identity': work_id})}"


def integration_context(store: ProjectStore) -> dict[str, Any]:
    """The Phase Integration Review Context: the contract, the adapter, the running loader and the Global policy
    baseline it reviews under - recomputed at freeze, then bound by digest."""
    from .implementation import package_directory
    from .review import integration as ri
    from .review import planning
    from .review import policy as review_policy

    root = store.workline_root()
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_INTEGRATION_CONTEXT, serialize.VERSION_KEY: 1,
        "review_kind": ri.REVIEW_KIND, "contract": records.P4_PHASE_INTEGRATION_CONTRACT,
        "adapter_identity": INTEGRATION_ADAPTER, "projection_semantics_version": INTEGRATION_PROJECTION,
        "loader_identity": planning.loader_identity(package_directory(root)),
        "global_baseline_digest": review_policy.load_global_baseline(root).digest,
    })


def integration_requirement(candidate: dict[str, Any]) -> dict[str, Any]:
    """The decided requirement an Integration Run is adjudicated against: the canonical Phase and integration
    objectives, by digest only - reviewer prose never restates them (§32.21)."""
    from .review import integration as ri

    return p4.requirement_record(ri.REVIEW_KIND, {
        "phase_id": candidate["phase_id"], "phase_desired_state_digest": candidate["phase_desired_state_digest"],
        "integration_id": candidate["integration"]["work_id"],
        "integration_desired_state_digest": candidate["integration"]["desired_state_digest"],
    })


def current_integration_requirement(store: ProjectStore, work_id: str) -> dict[str, Any]:
    """The integration's decided requirement as HEAD's committed objects hold it now - what a Human decision about
    a waiting Run is proven against (GAP-G), and what a Candidate frozen at HEAD binds."""
    from .review import integration as ri
    from .store import PHASE_DESIRED_HEADING

    git = hermetic_module.enter(store)
    view = committed_view_at(store, git, _head(git)[1])
    work = view.works.get(work_id)
    phase = None if work is None else view.phases.get(str(work.phase_id))
    if work is None or phase is None:
        raise _integration_reconcile(f"HEAD's committed view holds no integration {work_id} in a Phase")

    def digest(text: str | None) -> str | None:
        return None if text is None else serialize.digest_of_text(text)

    return p4.requirement_record(ri.REVIEW_KIND, {
        "phase_id": phase.id, "phase_desired_state_digest": digest(phase.section(PHASE_DESIRED_HEADING)),
        "integration_id": work_id, "integration_desired_state_digest": digest(work.section(WORK_DESIRED_HEADING)),
    })


def _integration_snapshot(candidate: dict[str, Any]) -> records.CandidateSnapshot:
    from .review import integration as ri

    return records.CandidateSnapshot(candidate_hash=ri.candidate_hash(candidate),
                                     reconstruction_mode=records.RECONSTRUCTION_SNAPSHOT,
                                     projection_semantics_version=INTEGRATION_PROJECTION, material=dict(candidate),
                                     builder=None)


def _integration_bindings(session: "_Session") -> list[p4.DiscoveryBinding]:
    """The discovery actors: the required slots, then the holdout slots, each by viewpoint (as P6, §30.11)."""
    selector = session.phase_review
    return (sorted(selector.discovery, key=lambda binding: binding.viewpoint)
            + sorted(selector.holdout_discovery, key=lambda binding: binding.viewpoint))


def _integration_reconcile(message: str, reason: str = p4.REASON_CHAIN_INVALID) -> ReconcileRequired:
    return _reconcile(message, reason)


# --------------------------------------------------------------------------- R22: earlier Runs of the integration

def _integration_waiting(review: ReviewStore, chain: Any) -> bool:
    """Whether the Run stands at canonical G4 HUMAN_WAIT (R8: the same canonical Run, never settled)."""
    return chain.latest.generation == p4.ADJUDICATION_SETTLE_GENERATION and review.adjudication_exists(
        chain.review_run_id) and review.read_adjudication(chain.review_run_id).outcome == records.HUMAN_WAIT


def _integration_settled(review: ReviewStore, chain: Any) -> str | None:
    """How an earlier Integration Run ended for good: ``consumed`` or ``not_authorized`` (a declining G2, or a
    G4-terminal disposition - ruling OQ-C); ``None`` otherwise. A G4 HUMAN_WAIT is never settled (R8)."""
    found = p4.final_disposition(review, chain)
    return None if found == history.DISPOSITION_HUMAN_WAIT else found


def integration_recovery(store: ProjectStore, work_id: str) -> Any:
    """R22: canonical recovery discovery of the earlier Integration Runs of ``work_id``, before a fresh Run begins.

    The shared core (``recovery.discover_kind``) with this kind's adapter; it
    writes nothing. Called only by a START that holds no Integration Run of
    the Work yet, so every matching Run is another START's:

    ```text
    not the Phase Integration contract                  reconcile (review_chain_invalid)
    consumed / not_authorized (G2 declined, G4-terminal) set aside - settled; never authorizable again (OQ-C)
                                                          and never named by the new Run (MC-7)
    named by another matching Run                        set aside
    G4 HUMAN_WAIT                                        recoverable: the same canonical waiting Run (R8),
                                                          returned - never replaced, never set aside unasked
    any other (open G1 - G3, an authorizing G4, a seal   review_recovery_incomplete: an Integration Run is
      not consumed)                                       resumed only from the START record that holds it
    ```
    """
    from .review import integration as ri
    from .review import recovery

    def classify(store_: ProjectStore, review: ReviewStore, head: str | None, found: Any, named_aside: set[str],
                 currency: Any) -> str | None:
        if found.contract != records.P4_PHASE_INTEGRATION_CONTRACT:
            raise _integration_reconcile(f"Review Run {found.review_run_id} of the Phase Integration kind binds "
                                         f"contract {found.contract}")
        first = found.chain.generations[0]
        if first.target_identity != work_id or p4.shape_of(found.chain) == p4.SHAPE_REPAIR \
                or found.chain.latest.generation > p4.SEAL_GENERATION:
            raise _integration_reconcile(f"Integration Review Run {found.review_run_id} is not a discovery -> "
                                         f"adjudication -> seal Run of {work_id}")
        try:
            settled = _integration_settled(review, found.chain)
            waiting = _integration_waiting(review, found.chain)
        except ValidationError as exc:
            raise _reconcile(f"Integration Review Run {found.review_run_id} does not reconstruct: {exc}",
                             "review_recovery_incomplete") from exc
        if settled is not None:
            return settled
        if found.review_run_id in named_aside:
            return "set_aside"
        problem = recovery.p4_reconstruction_problem(review, found)
        if problem:
            raise _reconcile(f"Integration Review Run {found.review_run_id} does not reconstruct: {problem}",
                             "review_recovery_incomplete")
        if waiting:
            return None
        raise _reconcile(
            f"Integration Review Run {found.review_run_id} of {work_id} is open and no START this invocation holds "
            "holds it; it is never replaced by a new Run and never recovered as authorizable here",
            "review_recovery_incomplete",
        )

    adapter = recovery.RecoveryAdapter(
        shape=lambda chain: "binds no Phase Integration contract in its generation-1 TaskInputs",
        named=lambda review, found: [str(item["review_run_id"]) for item in (
            review.read_task_input(found.task_id).request_envelope.get("set_aside_runs") or [])],
        classify=classify,
    )
    return recovery.discover_kind(store, ri.REVIEW_KIND, integration_operation_identity(work_id), adapter)


# --------------------------------------------------------------------------- precheck, freeze and the opening

def _integration_precheck(session: "_Session", view: ProjectView, work: Entity) -> None:
    """START's ordinary entry checks of the Work, before anything of it is recorded (the executor is never asked)."""
    phase = view.phases.get(work.phase_id) if work.phase_id else None
    if phase is None:
        raise StopError(f"integration {work.id} belongs to no Phase", code="phase_inactive")
    if view.phase_lifecycle(phase.id) != ACTIVE:
        raise StopError(f"Phase {phase.id} is {view.phase_lifecycle(phase.id)}", code="phase_inactive")
    if view.roadmap_lifecycle(phase.roadmap_id or "") != ACTIVE:
        raise StopError(f"Roadmap {phase.roadmap_id} is {view.roadmap_lifecycle(phase.roadmap_id or '')}",
                        code="roadmap_inactive")
    unsatisfied = view.unsatisfied_dependencies(work.id)
    if unsatisfied:
        raise StopError(f"Work {work.id} has unresolved requires_completion: "
                        + ", ".join(f"{relation.from_id} ({label})" for relation, label in unsatisfied),
                        code="dependency_unsatisfied")


def _integration_runs(mutation: Mutation, work_id: str) -> list[str]:
    """The Integration Runs this START mutation holds for ``work_id``, first to current: its first Run, then each
    Human-decision successor by its exact successor reservation (R8, P4-R7)."""
    from .review import integration as ri

    first = mutation.reserved(gate.review_run_key(ri.REVIEW_KIND, work_id))
    if first is None:
        return []
    found = [first]
    while True:
        successor = mutation.reserved(gate.review_successor_run_key(found[-1]))
        if successor is None:
            return found
        if successor in found:
            raise _integration_reconcile(f"the successor reservations of Integration Review Run {found[-1]} are not "
                                         "one chain", p4.REASON_SUCCESSOR_CONFLICT)
        found.append(successor)


# --------------------------------------------------------------------------- R8 / P4-R7: the Human decision

def _integration_decision_bindings(mutation: Mutation) -> dict[str, dict[str, Any]]:
    found = mutation.note(NOTE_INTEGRATION_DECISIONS)
    if found is None:
        return {}
    if not isinstance(found, dict) or not all(isinstance(key, str) and isinstance(value, dict)
                                              for key, value in found.items()):
        raise _integration_reconcile(f"START mutation {mutation.id}'s Human-decision bindings are not a waiting-Run "
                                     "mapping", p4.REASON_LINKAGE_INVALID)
    return dict(found)


def _integration_decision_exits(session: "_Session", waiting_run_id: str, chain: Any) -> bool:
    """Whether the invocation's Human decision exits ``waiting_run_id``'s wait - read only, nothing bound."""
    decision = session.phase_review.human_decision
    if decision is None:
        return False
    record = decision.to_record()
    bindings = _integration_decision_bindings(session.mutation)
    if waiting_run_id in bindings:
        return bindings[waiting_run_id] == record
    if any(found.get("decision_id") == decision.decision_id for found in bindings.values()):
        return False
    return _integration_envelope(ReviewStore(session.store), chain).get("human_decision") != record


def _integration_require_evidence(session: "_Session", waiting_run_id: str, chain: Any, work_id: str) -> None:
    """GAP-G, before any binding, reservation or other effect: the Human Decision Evidence of the wait this decision
    exits - exactly that Run, proven against canonical records and the current requirement; nothing detached."""
    from .review import integration as ri

    evidence = session.phase_review.decision_evidence
    exits = _integration_decision_exits(session, waiting_run_id, chain)
    resumed = [{"review_run_id": waiting_run_id, "reason": p4.SET_ASIDE_HUMAN_DECISION}] if exits else []
    review = ReviewStore(session.store)
    p4.require_decision_evidence_cover(review, resumed, evidence)
    if exits:
        requirement = current_integration_requirement(session.store, work_id)
        for item in evidence:
            p4.prove_decision_evidence(review, item, review_kind=ri.REVIEW_KIND, target_identity=work_id,
                                       current_requirement=requirement)


def _integration_bind_decision(session: "_Session", waiting_run_id: str, chain: Any) -> p4.HumanDecision | None:
    """P4-R7 for an Integration Run: the decision that exits ``waiting_run_id``'s HUMAN_WAIT, bound durably before
    the successor is reserved; the same decision again is idempotent, another one for a bound wait is refused, and a
    decision that already exits another wait, or that the waiting Run's own request carried, exits nothing."""
    decision = session.phase_review.human_decision
    if decision is None:
        return None
    record = decision.to_record()
    bindings = _integration_decision_bindings(session.mutation)
    bound = bindings.get(waiting_run_id)
    if bound is not None:
        if bound != record:
            raise p4.stop(p4.CODE_HUMAN_DECISION_INVALID,
                          f"START mutation {session.mutation.id} already binds Human decision "
                          f"{bound.get('decision_id')!r} to the wait of Integration Review Run {waiting_run_id}, and "
                          f"this invocation carries {decision.decision_id!r} for it; the binding is left unchanged")
        return decision
    for other, found in sorted(bindings.items()):
        if found.get("decision_id") != decision.decision_id:
            continue
        if found != record:
            raise p4.stop(p4.CODE_HUMAN_DECISION_INVALID,
                          f"Human decision {decision.decision_id!r} is bound to the wait of Integration Review Run "
                          f"{other} with another disposition; one decision identity is one decision")
        return None
    if _integration_envelope(ReviewStore(session.store), chain).get("human_decision") == record:
        return None
    session.mutation.set_note(NOTE_INTEGRATION_DECISIONS, {**bindings, waiting_run_id: record})
    return decision


def _unfrozen_set_aside(store: ProjectStore, mutation: Mutation, runs: list[str]) -> tuple[dict[str, str], ...]:
    """What the current Run of ``runs`` sets aside, when it is reserved and not frozen yet.

    A successor of a waiting Run names it (``human_decision``); a successor of a
    G4-terminal Run - after the confirmation structure or a domain repair -
    names nothing (MC-7: a final Run is never set aside). A first Run names the
    waiting Run of another (lost) START whose wait this START's bound decision
    exits - the bindings are durable before any reservation (P4-R7).
    """
    if len(runs) > 1:
        predecessor = ReviewStore(store).gate_chain(runs[-2])
        if predecessor is not None and _integration_waiting(ReviewStore(store), predecessor):
            return ({"review_run_id": runs[-2], "reason": p4.SET_ASIDE_HUMAN_DECISION},)
        return ()
    bound = sorted(set(_integration_decision_bindings(mutation)) - set(runs))
    return tuple({"review_run_id": run_id, "reason": p4.SET_ASIDE_HUMAN_DECISION} for run_id in bound)


def _integration_exit_wait(session: "_Session", waiting_run_id: str, chain: Any, work_id: str) -> tuple[dict[str, str], ...]:
    """R8: a G4 HUMAN_WAIT Run stays the same canonical Run until an explicit Human decision exits it - proven,
    then bound, before anything is reserved for its successor. Without one, START stays pending at that wait."""
    history.require_history_ready(ReviewStore(session.store), waiting_run_id, history.BOUNDARY_HUMAN_WAIT,
                                  history_contract=history.HISTORY_CONTRACT)
    _integration_require_evidence(session, waiting_run_id, chain, work_id)
    if _integration_bind_decision(session, waiting_run_id, chain) is None:
        raise p4.stop(p4.CODE_HUMAN_WAIT,
                      f"Integration Review Run {waiting_run_id} of {work_id} waits on a Human requirement decision at "
                      "generation 4; it stays the same canonical Run, nothing guesses the decision, and no other Run "
                      "of the integration begins beside it (R8)")
    return ({"review_run_id": waiting_run_id, "reason": p4.SET_ASIDE_HUMAN_DECISION},)


def _integration_own_opening(mutation: Mutation, work_id: str) -> list[dict[str, Any]]:
    """The integration's own opening lifecycle effects this START recorded (§32.17), in recorded order."""
    from .review import integration as ri

    found = []
    for effect in mutation.effects:
        record = (effect.get("payload") or {}).get("record") if effect.get("kind") == "append_event" else None
        if isinstance(record, dict) and record.get("entity") == work_id and record.get("type") in ri.OPENING_EVENTS \
                and str(effect.get("stage", "")).rsplit(":", 1)[0] == f"{work_id}:lifecycle":
            found.append(effect)
    return found


def _projected_opening(mutation: Mutation, candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """The recorded opening effects the Candidate binds as START's own uncommitted lifecycle projection, by event ID."""
    ids = [entry["event_id"] for entry in candidate["owning_operation"]["lifecycle_projection"]]
    found = {}
    for effect in mutation.effects:
        record = (effect.get("payload") or {}).get("record") if effect.get("kind") == "append_event" else None
        if isinstance(record, dict) and record.get("id") in ids:
            found[record["id"]] = effect
    return [found[event_id] for event_id in ids if event_id in found]


def _opening_types(view: ProjectView, work_id: str) -> list[str]:
    """What START's ordinary path opens for the Work in its state (``run_work``'s target / lifecycle step)."""
    state = view.work_state(work_id)
    if state.state == UNSTARTED:
        return ["work_started", "work_target_added"]
    if state.state == HELD:
        return ["work_resumed", "work_target_added"]
    if state.state == IN_PROGRESS and not state.has_target:
        return ["work_target_added"]
    return []


def _integration_freeze(session: "_Session", view: ProjectView, work: Entity, run_id: str,
                        set_aside: tuple[dict[str, str], ...]) -> dict[str, Any]:
    """§32.17 - §32.18: the Candidate over committed HEAD, its Context and frozen Effective Policy - once per Run.

    Decided before the Run's first effect and kept in the START record, so a
    resume continues the same Candidate. START's own opening of the integration
    is bound as the lifecycle projection (the event IDs are reserved first),
    never as basis; any other structural difference between the working state
    and HEAD refuses the freeze (``review_base_uncommitted``) before anything of
    the integration is recorded.
    """
    from . import start_integration_review as sir
    from .ops import _own_effects_free_view, new_event
    from .review import achievement_reader
    from .review import policy as review_policy

    store, mutation = session.store, session.mutation
    frozen = (mutation.note(NOTE_INTEGRATION_FREEZE) or {}).get(run_id)
    if frozen is not None:
        return frozen
    git = hermetic_module.enter(store)
    branch, base = _head(git)
    committed = committed_view_at(store, git, base)
    # START's own opening of the integration that HEAD does not hold yet - an opening an earlier cycle of this
    # mutation committed (a repair's move) is basis, never projection
    held = {event.id for event in committed.events}
    opening = [effect for effect in _integration_own_opening(mutation, work.id)
               if effect["payload"]["record"]["id"] not in held]
    recorded = int(stage_name(mutation, f"{work.id}:lifecycle").rsplit(":", 1)[1])
    if opening:
        projection = [(str(effect["payload"]["record"]["id"]), str(effect["payload"]["record"]["type"]))
                      for effect in opening]
        terminal_stage = f"{work.id}:lifecycle:{recorded}"
    else:
        stage = f"{work.id}:lifecycle:{recorded}"
        projection = [(new_event(mutation, f"{stage}:event:{index}", kind, work.id).id, kind)
                      for index, kind in enumerate(_opening_types(view, work.id))]
        terminal_stage = f"{work.id}:lifecycle:{recorded + 1}"
    working = _own_effects_free_view(ProjectView.load(store), opening)
    differences = sir.unowned_structural_difference(committed, working, str(work.phase_id), work.id)
    if differences:
        raise StopError("the Phase Integration Candidate is frozen over committed canonical state only, and the "
                        "working structure differs from HEAD's: " + "; ".join(differences) + "; nothing of the "
                        "integration was begun", code="review_base_uncommitted")
    policy_id = p4.new_run_policy()
    review = ReviewStore(store)
    selector = session.phase_review
    # R6-1 / R19: resolved ONCE, before any reservation, with the selector's discovery and holdout actors
    effective = review_policy.new_run_effective_policy(review, store.workline_root(), policy_id, selector.discovery,
                                                       selector.holdout_discovery)
    context = integration_context(store)
    phase_id = str(work.phase_id)
    try:
        candidate = sir.build_candidate(
            committed, phase_id, work.id, base_commit=base, branch=branch, owning_mutation_id=mutation.id,
            terminal_stage=terminal_stage, lifecycle_projection=projection,
            work_review_refs=_integration_work_review_refs(review, committed, phase_id),
            review_context_digest=serialize.digest(context),
            effective_policy_hash=p4.run_effective_policy_hash(policy_id, effective), candidate_generation=1,
            achievement_evidence_refs=achievement_reader.candidate_achievement_refs(committed, review, phase_id),
        )
    except ValidationError as exc:
        raise StopError(f"no Phase Integration Candidate of {work.id} is frozen: {exc}; nothing of the integration "
                        "was begun", code=exc.code or "review_candidate_unrepresentable") from exc
    record = {"candidate": candidate, "context": context, "effective": effective, "policy": policy_id,
              "set_aside": [dict(item) for item in set_aside]}
    mutation.set_note(NOTE_INTEGRATION_FREEZE, {**(mutation.note(NOTE_INTEGRATION_FREEZE) or {}), run_id: record})
    return record


def _integration_work_review_refs(review: ReviewStore, committed: ProjectView, phase_id: str
                                  ) -> list[tuple[str, str, str]]:
    """§14.5 / §32.18: the validated P5 Work Review references of the Phase's effective Works - each consumed Work
    Review Run of one of them whose stored consumed P5 Run summary validates against its own chain, adjudication,
    Receipt and Consumption, by that summary's digest. A pre-P5 Run has none; nothing is backfilled."""
    effective = {found.id for found in committed.effective_works(phase_id)}
    refs: list[tuple[str, str, str]] = []
    for consumption in review.consumptions():
        if getattr(consumption, "review_kind", None) != work_review.REVIEW_KIND \
                or consumption.target_identity not in effective:
            continue
        run_id = consumption.review_run_id
        chain = review.gate_chain(run_id)
        if chain is None or not p4.run_contracts(review, chain) - {None} \
                or p4.history_contract_of_policy(p4.run_policy(review, chain)) is None \
                or not review.history_exists(review_paths.HISTORY_RUNS, run_id):
            continue  # a v1 or P4-only Work Review Run binds no P5 history
        summary = review.read_history(review_paths.HISTORY_RUNS, run_id)
        if summary.durable_disposition == history.DISPOSITION_CONSUMED \
                and not history.run_summary_problems(review, summary):
            refs.append((consumption.target_identity, run_id, review.history_digest(review_paths.HISTORY_RUNS, run_id)))
    return sorted(refs)


def _integration_open(session: "_Session", view: ProjectView, work: Entity, run_id: str,
                      frozen: dict[str, Any]) -> None:
    """Record the integration's own opening lifecycle exactly as the frozen Candidate projects it (idempotent)."""
    mutation = session.mutation
    projection = frozen["candidate"]["owning_operation"]["lifecycle_projection"]
    opening = _projected_opening(mutation, frozen["candidate"])
    if opening:
        found = [(effect["payload"]["record"]["id"], effect["payload"]["record"]["type"]) for effect in opening]
        if found != [(entry["event_id"], entry["type"]) for entry in projection]:
            raise _integration_reconcile(f"the opening lifecycle START recorded for {work.id} is not the one the "
                                         f"Candidate of Integration Review Run {run_id} binds")
        return
    from .mutation import utc_now

    stage = stage_name(mutation, f"{work.id}:lifecycle")
    effects = []
    for index, entry in enumerate(projection):
        if mutation.reserved(f"{stage}:event:{index}") != entry["event_id"]:
            raise _integration_reconcile(f"the opening event {entry['event_id']} of {work.id} is not the one "
                                         f"reserved for {stage}")
        effects.append(Effect.append_event(Event(entry["event_id"], entry["type"], work.id, utc_now())))
    mutation.extend_scope(entities=[work.id])
    mutation.add_effects(stage, effects)
    mutation.apply()


def _integration_successor(session: "_Session", view: ProjectView, work: Entity, waiting_run_id: str,
                           set_aside: tuple[dict[str, str], ...]) -> IntegrationRun:
    """The Human-decision successor of this START's own waiting Run: reserved after the decision is bound, then a
    new Candidate frozen over committed HEAD (the opening START already recorded is its lifecycle projection)."""
    mutation = session.mutation
    run_id = mutation.reserve_id(gate.review_successor_run_key(waiting_run_id), "review_run")
    frozen = _integration_freeze(session, view, work, run_id, set_aside)
    for binding in _integration_bindings(session):
        mutation.reserve_id(gate.review_task_key(run_id, binding.task_slot), "review_task")
    return _integration_held(mutation, work.id, run_id, frozen)


def _integration_held(mutation: Mutation, work_id: str, run_id: str, frozen: dict[str, Any]) -> IntegrationRun:
    return IntegrationRun(work_id, run_id, frozen["candidate"], frozen["context"], frozen["effective"],
                          str(frozen["policy"]), tuple(dict(item) for item in frozen.get("set_aside") or ()),
                          mutation.reserved(gate.review_receipt_key(run_id, p4.SEAL_GENERATION)))


def _integration_run(session: "_Session", view: ProjectView, work: Entity) -> IntegrationRun:
    """The Run this START holds for ``work``: reserved, frozen and opened on first use (§32.15 - §32.17)."""
    from .review import integration as ri

    store, mutation = session.store, session.mutation
    if not fsafe.immutable_create_supported():
        raise StopError("a Phase Integration Review writes immutable Review records, which this platform cannot keep "
                        "inside the Project; nothing of the integration was begun", code="review_create_unsupported")
    held = _integration_runs(mutation, work.id)
    set_aside: tuple[dict[str, str], ...] = ()
    if not held:
        # R22, before anything of the integration is reserved or recorded: an earlier Run is settled (never named),
        # waiting at G4 HUMAN_WAIT (the same canonical Run: returned, R8), or open elsewhere (incomplete)
        discovered = integration_recovery(store, work.id)
        if discovered.recoverable is not None:
            set_aside = _integration_exit_wait(session, discovered.recoverable.review_run_id,
                                               discovered.recoverable.chain, work.id)
        _integration_precheck(session, view, work)
        gitops.ensure_separable_before_effects(mutation, [EVENT_LOG])
        gitops.narrow_preexisting_dirty(mutation, store.root)
    if held and _repair_moved(mutation, held[-1]):
        # the repaired Run's cycle ended with its move; the integration is entered again after its fix Works: a new
        # Run of the same integration over a new Candidate, never naming the final one (§32.27, MC-7)
        _integration_precheck(session, view, work)
        held = held + [mutation.reserve_id(gate.review_successor_run_key(held[-1]), "review_run")]
    if held:
        set_aside = _unfrozen_set_aside(store, mutation, held)
    run_id = held[-1] if held else mutation.reserve_id(gate.review_run_key(ri.REVIEW_KIND, work.id), "review_run")
    frozen = _integration_freeze(session, view, work, run_id, set_aside)
    for binding in _integration_bindings(session):
        mutation.reserve_id(gate.review_task_key(run_id, binding.task_slot), "review_task")
    _integration_open(session, view, work, run_id, frozen)
    return _integration_held(mutation, work.id, run_id, frozen)


# --------------------------------------------------------------------------- generation mutations

def _integration_generation(session: "_Session", run: IntegrationRun, generation: int, transition: str,
                            gate_record: records.GateGeneration, extra: list[tuple[str, dict[str, Any]]],
                            receipt_id: str | None = None) -> None:
    """Open, record, commit and prove persisted the generation mutation writing ``gate_record`` (and ``extra``).

    Its durable ``review_kind`` is the Phase Integration kind, so the one
    generation dispatch (``roadmap_review._finish_generation``) commits only its
    Review record paths with the review-v1 planning commit primitive - never the
    Work one - while START's own uncommitted lifecycle stays out of it.
    """
    from .review import integration as ri
    from .roadmap_review import _finish_generation as finish

    store, mutation = session.store, session.mutation
    scope = gate.next_generation_scope(store, run.review_run_id)
    if scope.generation != generation:
        raise _integration_reconcile(f"Integration Review Run {run.review_run_id}'s next generation is "
                                     f"{scope.generation}, not {generation}")
    if transition == p4.TRANSITION_ACCEPT:
        writes = list(extra) + [(scope.gate_path, gate_record.to_record())]
    else:
        writes = [(scope.gate_path, gate_record.to_record())] + list(extra)
    invocation = {
        "operation": OPERATION_GENERATION, "review_contract": records.P4_PHASE_INTEGRATION_CONTRACT,
        "start_mutation_id": mutation.id, "review_kind": ri.REVIEW_KIND, "review_run_id": run.review_run_id,
        "generation": generation, "transition": transition, "candidate_hash": gate_record.candidate_hash,
        "review_context_hash": gate_record.review_context_hash,
        "effective_policy_hash": gate_record.effective_policy_hash,
        "obligation_digest": gate_record.obligation_digest, "receipt_id": receipt_id,
    }
    record_paths = [path for path, _ in writes]
    gen = MutationController(store).open(OWNER, invocation,
                                         WriteScope(files=tuple(scope.files) + tuple(path for path, _ in extra)))
    with abandon_on_stop(gen):
        gitops.record_preexisting_dirty(gen, store.root)
        gitops.ensure_separable_before_effects(gen, record_paths)
        if not gen.has_stage(STAGE_GENERATION):
            gate.require_committable(store, record_paths)
            gitops.require_no_planning_transform(store.root, record_paths)
            checkout.require_checkout_capability(store, record_paths)
            gen.add_effects(STAGE_GENERATION, [Effect.create_file(path, serialize.canonical_text(record))
                                               for path, record in writes])
    finish(store, gen)


def _integration_resolve_pending(session: "_Session", run: IntegrationRun) -> None:
    """A pending generation mutation of this Run is resumed first, and nothing else is (§11.8 step 3)."""
    from .review import integration as ri
    from .roadmap_review import _finish_generation as finish

    store, mutation = session.store, session.mutation
    pending = gate.pending_generation_mutations(store, run.review_run_id)
    if not pending:
        return
    if len(pending) > 1:
        raise _integration_reconcile(f"Integration Review Run {run.review_run_id} has {len(pending)} pending "
                                     "generation mutations", "review_generation_owner_conflict")
    record = pending[0]
    found = record.get("invocation") or {}
    if (record.get("owner") != OWNER or found.get("operation") != OPERATION_GENERATION
            or found.get("review_kind") != ri.REVIEW_KIND or found.get("start_mutation_id") != mutation.id
            or found.get("review_run_id") != run.review_run_id
            or found.get("review_contract") != records.P4_PHASE_INTEGRATION_CONTRACT):
        raise _integration_reconcile(f"the pending generation mutation {record.get('mutation_id')} of Integration "
                                     f"Review Run {run.review_run_id} is not this START mutation's ({mutation.id})",
                                     "review_generation_owner_conflict")
    gen = MutationController(store).open(OWNER, found, WriteScope.from_record(record.get("write_scope") or {}))
    if not gen.effects:
        gen.abandon()
        return
    generation = found.get("generation")
    chain = _integration_chain(store, run)
    next_number = records.FIRST_GENERATION if chain is None else chain.next_generation
    recorded = {effect["payload"]["path"]: effect["payload"]["content"] for effect in gen.stage_effects(STAGE_GENERATION)}
    fits = generation == next_number
    if not fits and chain is not None and generation == chain.latest.generation:
        gate_path = review_paths.gate_rel(run.review_run_id, int(generation))
        stored = ReviewStore(store).read_bytes(gate_path)
        fits = stored is not None and gate_path in recorded and stored == recorded[gate_path].encode("utf-8")
    allowed = p4.TRANSITIONS.get(int(generation), ()) if type(generation) is int else ()
    if not fits or found.get("transition") not in allowed or (type(generation) is int and generation > p4.SEAL_GENERATION):
        raise _integration_reconcile(f"the pending generation mutation {gen.id} writes generation {generation} of "
                                     f"Integration Review Run {run.review_run_id}, which is not its next transition")
    finish(store, gen)


def _integration_chain(store: ProjectStore, run: IntegrationRun) -> Any:
    try:
        return ReviewStore(store).gate_chain(run.review_run_id)
    except ValidationError as exc:
        raise _integration_reconcile(f"Integration Review Run {run.review_run_id}'s chain does not validate: "
                                     f"{exc}") from exc


# --------------------------------------------------------------------------- currency and side effects

def _integration_current_problems(session: "_Session", run: IntegrationRun) -> list[str]:
    """Why the frozen Candidate is no longer current (§32.30); empty when it is.

    HEAD is on the Candidate's branch and descends from its base, every commit
    since changed Review records only, the committed structure at HEAD and the
    working structure (less START's own opening) are still the Candidate's,
    and the integration still carries its marker.
    """
    from . import phase_integration as pi
    from . import start_integration_review as sir
    from .ops import _own_effects_free_view

    store, mutation = session.store, session.mutation
    base = run.candidate["base"]
    git = hermetic_module.enter(store)
    branch, head = _head(git)
    if branch != base["branch"]:
        return [f"HEAD is on {branch}, not the Candidate's {base['branch']}"]
    problems: list[str] = []
    if head != base["commit"]:
        descends = ancestry.raw_descends_from(git, head, base["commit"])
        if descends is not True:
            return [f"HEAD {head} is not shown to descend from the Candidate's base {base['commit']}"]
        outside = sorted(entry.path for entry in _delta(git, base["commit"], head)
                         if not entry.path.startswith(f"{review_paths.REVIEW_DIR}/"))
        if outside:
            problems.append("commits since the Candidate's base changed " + ", ".join(outside))
    phase_id = str(run.candidate["phase_id"])
    committed = committed_view_at(store, git, head)
    working = _own_effects_free_view(ProjectView.load(store), _projected_opening(mutation, run.candidate))
    problems += sir.unowned_structural_difference(committed, working, phase_id, run.work_id)
    work = working.works.get(run.work_id)
    if work is None or not pi.is_reviewed_integration(work) \
            or work.phase_review_contract != run.candidate["integration"]["phase_review_contract"]:
        problems.append(f"{run.work_id} no longer carries the marker its Candidate binds")
    return problems


def _project_state_digest(store: ProjectStore) -> str:
    """START's own measurement of persistent Project state (§14.10 owner-measured proof): HEAD, and every path Git
    sees changed or untracked with the exact bytes it holds (the Mutation Controller's own content digest: bytes as on
    disk, a link by its target, absence as absence) - runtime records excluded."""
    from .mutation import _content_digest
    from .store import RUNTIME_DIR

    repo = store.root
    entries = []
    for entry in sorted(gitcmd.status_entries(repo), key=lambda found: found.path):
        if entry.path.startswith(RUNTIME_DIR + "/"):
            continue
        held = _content_digest(repo.joinpath(*entry.path.split("/")))
        entries.append({"path": entry.path, "status": entry.index + entry.worktree,
                        "content": "unreadable" if held is None else held})
    return serialize.digest({"head": gitcmd.head_commit(repo), "entries": entries})


def _measured(session: "_Session", run: IntegrationRun, generation: int, before: str) -> None:
    """Record the before / after measurement of the launches settled at ``generation``; refuse any change."""
    after = _project_state_digest(session.store)
    if after != before:
        raise StopError(f"a verification actor of Integration Review Run {run.review_run_id} changed persistent "
                        "Project state across its launch (a verification-only Review mutates nothing); nothing is "
                        "settled", code=CODE_INTEGRATION_SIDE_EFFECT)
    notes = dict(session.mutation.note(NOTE_INTEGRATION_MEASURED) or {})
    measured = dict(notes.get(run.review_run_id) or {})
    measured[str(generation)] = {"before": before, "after": after}
    notes[run.review_run_id] = measured
    session.mutation.set_note(NOTE_INTEGRATION_MEASURED, notes)


def _side_effect_problems(session: "_Session", run: IntegrationRun) -> tuple[str, ...] | None:
    """§32.29: the verification-only proof of every launch the Run settled, or ``None`` when one is not measured."""
    from .review import integration as ri

    measured = (session.mutation.note(NOTE_INTEGRATION_MEASURED) or {}).get(run.review_run_id) or {}
    git = hermetic_module.enter(session.store)
    tree = resulting_tree.root_tree_id(git, run.candidate["base"]["commit"])
    declaration = p4.IntegrationDeclaration(INTEGRATION_ADAPTER, (), (), (), None, False)
    problems: list[str] = []
    for generation in (p4.DISCOVERY_SETTLE_GENERATION, p4.ADJUDICATION_SETTLE_GENERATION):
        found = measured.get(str(generation))
        if not isinstance(found, dict):
            return None
        proof = ri.OwnerMeasuredProof(OWNER, str(found.get("before")), str(found.get("after")), (), ())
        problems += ri.verification_only_problems(declaration, p4.IntegrationObservation(), proof,
                                                  candidate_base_tree=tree)
    return tuple(problems)


# --------------------------------------------------------------------------- G1 .. G5

def _integration_accept(session: "_Session", run: IntegrationRun) -> None:
    """G1: the Candidate snapshot, every discovery TaskInput (required + holdout) and the open gate, together."""
    from .review import integration as ri
    from .review import policy as review_policy

    store, mutation = session.store, session.mutation
    candidate, context = run.candidate, run.context
    snapshot = _integration_snapshot(candidate)
    requirement = integration_requirement(candidate)
    review = ReviewStore(store)
    decision = None
    writes = p4.HistoryWrites(p4.set_aside_summaries(review, run.set_aside))
    if any(item["reason"] == p4.SET_ASIDE_HUMAN_DECISION for item in run.set_aside):
        # §28.14 / GAP-G: the Human decision this Run continues under, and its Human Decision Evidence, persisted
        # in this G1 - before any external launch
        decision = session.phase_review.human_decision
        writes = p4.HistoryWrites(writes.summaries, tuple(
            p4.decision_evidence_record(
                review, item, mutation.reserve_id(history.review_decision_key(item.affected_review_run_id),
                                                  "review_decision"),
                review_kind=ri.REVIEW_KIND, target_identity=run.work_id, current_requirement=requirement,
            )
            for item in session.phase_review.decision_evidence
        ))
    evidence = serialize.canonical_data({"candidate_hash": snapshot.candidate_hash,
                                         "review_context_hash": serialize.digest(context)})
    holdout = {binding.task_slot for binding in session.phase_review.holdout_discovery}
    task_inputs: list[records.TaskInput] = []
    for binding in _integration_bindings(session):
        task_id = mutation.reserved(gate.review_task_key(run.review_run_id, binding.task_slot))
        if task_id is None:
            raise _integration_reconcile(f"discovery slot {binding.task_slot} has no reserved task")
        envelope = p4.discovery_request(
            review_contract=records.P4_PHASE_INTEGRATION_CONTRACT, review_kind=ri.REVIEW_KIND,
            viewpoint=binding.viewpoint, candidate=candidate, context=context, requirement=requirement,
            candidate_generation=1, succession=None, set_aside_runs=run.set_aside, human_decision=decision,
            evidence_ids=[f"phase-integration-candidate:{snapshot.candidate_hash}"], policy_id=run.policy,
            set_aside_summaries=writes.summary_bindings(), decision_evidence=writes.decision_bindings(),
            effective_policy=run.effective,
            discovery_role=review_policy.ROLE_HOLDOUT if binding.task_slot in holdout else review_policy.ROLE_REQUIRED,
        )
        task_inputs.append(p4.task_input(
            task_id=task_id, task_slot=binding.task_slot, task_kind=p4.TASK_KIND_DISCOVERY,
            actor_identity=binding.identity, actor_version=binding.version, envelope=envelope,
            candidate_hash=snapshot.candidate_hash, candidate_material_digest=serialize.digest(snapshot.to_record()),
            review_context_hash=serialize.digest(context), accepted_generation=p4.DISCOVERY_ACCEPT_GENERATION,
            policy_id=run.policy,
        ))
    required = [(found.task_slot, found.task_id) for found in task_inputs]
    gate_one = records.GateGeneration(
        review_run_id=run.review_run_id, generation=1, previous_generation=None, previous_digest=None,
        review_kind=ri.REVIEW_KIND, target_identity=run.work_id,
        operation_identity=integration_operation_identity(run.work_id), candidate_hash=snapshot.candidate_hash,
        review_context_hash=serialize.digest(context),
        effective_policy_hash=p4.run_effective_policy_hash(run.policy, run.effective),
        evidence_digest=serialize.digest(evidence), coverage_digest=serialize.digest(p4.coverage_record(required, [])),
        raw_report_set_digest=serialize.digest(p4.report_set_record([])),
        adjudication_digest=serialize.digest(p4.pending_adjudication_record()),
        obligation_digest=serialize.digest(p4.obligations_record(None)),
        accepted_tasks=tuple(p4.accepted_descriptor(found) for found in task_inputs), settled_tasks=(),
        status=records.GATE_STATUS_OPEN, receipt_id=None, authorized_operation_stage=None,
    )
    extra: list[tuple[str, dict[str, Any]]] = []
    if not ReviewStore(store).candidate_snapshot_exists(snapshot.candidate_hash):
        extra.append((review_paths.candidate_snapshot_rel(snapshot.candidate_hash), snapshot.to_record()))
    extra += [(review_paths.task_input_rel(found.task_id), found.to_record()) for found in task_inputs]
    extra += writes.extra()
    _integration_generation(session, run, 1, p4.TRANSITION_ACCEPT, gate_one, extra)


def _integration_launch(session: "_Session", run: IntegrationRun, chain: Any) -> None:
    """G1 -> G2: every accepted discovery task launched to its bound actor (state measured around), then G2."""
    store = session.store
    review = ReviewStore(store)
    first = chain.latest
    tasks = list(first.accepted_tasks)
    envelope = _integration_envelope(review, chain)
    gate.require_persisted(store, [review_paths.candidate_snapshot_rel(first.candidate_hash),
                                   review_paths.gate_rel(run.review_run_id, 1)]
                           + [review_paths.task_input_rel(str(task["task_id"])) for task in tasks]
                           + p4.first_generation_history_paths(envelope))
    # §28.18 successor_launch: no external launch under a Human decision before its evidence is canonical
    p4.require_first_generation_history(review, run.review_run_id, envelope)
    for task in tasks:
        problems = [message for _, message in review.provenance_problems(task, 1)]
        if problems:
            raise _integration_reconcile("the accepted discovery task's provenance: " + "; ".join(problems),
                                         "review_task_invalid")
    current = _integration_current_problems(session, run)
    if current:
        raise _integration_reconcile("the Phase Integration Candidate is no longer current: " + "; ".join(current)
                                     + "; nothing is launched", "review_candidate_mismatch")
    bindings = {binding.task_slot: binding for binding in _integration_bindings(session)}
    settled: list[dict[str, Any]] = []
    reports: dict[str, dict[str, Any]] = {}
    before = _project_state_digest(store)
    for task in tasks:
        task_id = str(task["task_id"])
        binding = bindings.get(str(task["task_slot"]))
        if binding is None or (binding.identity, binding.version) != (task["reviewer_identity"], task["reviewer_version"]):
            raise StopError(f"discovery task {task_id} ({task['task_slot']}) was accepted for {task['reviewer_identity']} "
                            f"{task['reviewer_version']}, and this invocation binds no such actor; nothing is launched",
                            code="review_reviewer_mismatch")
        task_input = review.read_task_input(task_id)
        launched = p4.P4DiscoveryTask(
            task_id=task_id, task_slot=task_input.task_slot, task_kind=task_input.task_kind,
            review_kind=first.review_kind, viewpoint=binding.viewpoint,
            request_envelope=serialize.canonical_data(task_input.request_envelope),
            request_digest=task_input.request_digest, candidate_hash=task_input.candidate_hash,
            review_context_hash=task_input.review_context_hash, effective_policy_hash=task_input.effective_policy_hash,
        )
        try:
            returned = binding.actor(launched)
        except Exception as exc:
            raise StopError(f"the discovery actor raised for task {task_id}: {exc}; nothing is settled",
                            code="review_reviewer_failed") from exc
        report = p4.report_record(returned, task, review_kind=first.review_kind,
                                  review_contract=records.P4_PHASE_INTEGRATION_CONTRACT)
        result_digest = serialize.digest(report)
        gate.validate_settlement(store, run.review_run_id, task_id, result_digest, str(returned.reviewer_identity))
        settled.append({"task_id": task_id, "status": p4.settled_status(report), "result_digest": result_digest,
                        "settled_generation": 2})
        reports[task_id] = report
    _measured(session, run, p4.DISCOVERY_SETTLE_GENERATION, before)
    required = [(str(task["task_slot"]), str(task["task_id"])) for task in tasks]
    gate_two = replace(
        first, generation=2, previous_generation=1, previous_digest=chain.latest_digest,
        coverage_digest=serialize.digest(p4.coverage_record(required, settled, reports)),
        raw_report_set_digest=serialize.digest(p4.report_set_record(settled)), settled_tasks=tuple(settled),
    )
    extra = [(review_paths.report_rel(task["result_digest"]), reports[task["task_id"]]) for task in settled]
    # GAP-E: a declined discovery task makes the Run non-authorizing and final in this same G2
    extra += p4.not_authorized_history(gate_two, 1)
    _integration_generation(session, run, 2, p4.TRANSITION_SETTLE, gate_two, extra)


def _integration_reports(review: ReviewStore, chain: Any) -> list[tuple[str, str, dict[str, Any]]]:
    discovery_ids = {str(task["task_id"]) for task in p4.discovery_tasks(chain)}
    found = []
    for task in chain.generation(2).settled_tasks:
        if str(task["task_id"]) in discovery_ids:
            digest = str(task["result_digest"])
            found.append((str(task["task_id"]), digest, serialize.canonical_data(review.read_report(digest).to_record())))
    return found


def _integration_envelope(review: ReviewStore, chain: Any) -> dict[str, Any]:
    return review.read_task_input(str(chain.generations[0].accepted_tasks[0]["task_id"])).request_envelope


def _integration_accept_adjudication(session: "_Session", run: IntegrationRun, chain: Any) -> None:
    """G3: one adjudication TaskInput built from canonical material only, accepted before any launch."""
    store, mutation = session.store, session.mutation
    review = ReviewStore(store)
    second = chain.latest
    envelope = _integration_envelope(review, chain)
    reports = _integration_reports(review, chain)
    request = p4.adjudication_request(
        review_contract=records.P4_PHASE_INTEGRATION_CONTRACT, review_kind=second.review_kind,
        review_run_id=run.review_run_id, candidate_hash=second.candidate_hash, candidate_generation=1,
        review_context_hash=second.review_context_hash, requirement=envelope["requirement"],
        reports=[{"task_id": t, "result_digest": d} for t, d, _ in reports], prior=p4.NO_PRIOR,
        evidence_ids=[eid for _, _, report in reports for eid in report["coverage"]["evidence_ids"]],
        policy_id=run.policy,
        prior_history=p4.prior_history_references(review, second.review_kind, second.target_identity,
                                                  run.review_run_id),
        effective_policy=run.effective,
    )
    task_id = mutation.reserve_id(gate.review_task_key(run.review_run_id, p4.SLOT_ADJUDICATOR), "review_task")
    adjudicator = session.phase_review.adjudicator
    task_input = p4.task_input(
        task_id=task_id, task_slot=p4.SLOT_ADJUDICATOR, task_kind=p4.TASK_KIND_ADJUDICATION,
        actor_identity=adjudicator.identity, actor_version=adjudicator.version, envelope=request,
        candidate_hash=second.candidate_hash,
        candidate_material_digest=review.candidate_material_digest(second.candidate_hash),
        review_context_hash=second.review_context_hash, accepted_generation=p4.ADJUDICATION_ACCEPT_GENERATION,
        policy_id=run.policy,
    )
    gate_three = replace(second, generation=3, previous_generation=2, previous_digest=chain.latest_digest,
                         accepted_tasks=second.accepted_tasks + (p4.accepted_descriptor(task_input),))
    _integration_generation(session, run, 3, p4.TRANSITION_ACCEPT, gate_three,
                            [(review_paths.task_input_rel(task_id), task_input.to_record())])


def _integration_disposition(run: IntegrationRun, normalized: Any, outcome: Any, current: list[str]) -> str:
    """§32.22 in the frozen order (rulings CPQ-04 / OQ-C): HUMAN_WAIT, DOMAIN_REPAIR_REQUIRED,
    CONFIRMATION_STRUCTURE_REQUIRED, AUTHORIZATION_READY - or the step-4 refusal code, which is the Run's terminal
    G4 disposition (never a corrupt record). An inconsistent adjudication derives nothing (ValidationError)."""
    from .review import integration as ri

    try:
        return ri.integration_branch(
            p4_outcome=p4.derive_outcome(normalized), phase_outcome=outcome,
            candidate_desired_state_digest=str(run.candidate["phase_desired_state_digest"]),
            blocking_problems=sum(1 for draft in normalized.drafts if draft.blocking),
            human_obligations=int(p4.obligations(normalized)["human"]),
            valid_downstream_confirmation=bool(ri.downstream_confirmation_ids_of(run.candidate)),
            invalid_uncovered=ri.invalid_uncovered_of(run.candidate), evidence_current=not current,
        )
    except ValidationError as exc:
        if exc.code in (ri.CODE_UNCOVERED, ri.CODE_NOT_AUTHORIZABLE):
            return str(exc.code)
        raise


def _integration_adjudicate(session: "_Session", run: IntegrationRun, chain: Any) -> None:
    """G3 -> G4: the adjudicator, launched only to its bound identity (state measured around); the P4 adjudication
    normalized, the Phase outcome judged with it, the one G4 disposition derived; G4 with its P5 history."""
    from .review import integration as ri

    store, mutation = session.store, session.mutation
    review = ReviewStore(store)
    third = chain.latest
    descriptor = p4.adjudication_task(chain)
    if descriptor is None:
        raise _integration_reconcile(f"Integration Review Run {run.review_run_id} accepted no adjudication")
    task_id = str(descriptor["task_id"])
    reports = _integration_reports(review, chain)
    gate.require_persisted(store, [review_paths.task_input_rel(task_id), review_paths.gate_rel(run.review_run_id, 3)]
                           + [review_paths.report_rel(digest) for _, digest, _ in reports])
    problems = review.provenance_problems(descriptor, 3)
    if problems:
        raise _integration_reconcile("the accepted adjudication task's provenance: "
                                     + "; ".join(message for _, message in problems), "review_task_invalid")
    binding = session.phase_review.adjudicator
    if (binding.identity, binding.version) != (descriptor["reviewer_identity"], descriptor["reviewer_version"]):
        raise StopError(f"adjudication task {task_id} was accepted for {descriptor['reviewer_identity']} "
                        f"{descriptor['reviewer_version']}, and this invocation binds {binding.identity} "
                        f"{binding.version}; the adjudicator is not launched", code="review_reviewer_mismatch")
    task_input = review.read_task_input(task_id)
    references = list(task_input.request_envelope.get("prior_history") or [])
    launched = p4.P4AdjudicationTask(
        task_id=task_id, task_slot=task_input.task_slot, task_kind=task_input.task_kind, review_kind=third.review_kind,
        request_envelope=serialize.canonical_data(task_input.request_envelope), request_digest=task_input.request_digest,
        candidate_hash=third.candidate_hash, review_context_hash=third.review_context_hash,
        effective_policy_hash=third.effective_policy_hash, candidate=dict(run.candidate),
        reports=tuple(report for _, _, report in reports), prior_findings=(), prior_repair_batch=None,
        prior_repair_result=None, prior_history=p4.prior_history_records(review, references),
    )
    before = _project_state_digest(store)
    try:
        returned = binding.actor(launched)
    except Exception as exc:
        raise p4.stop(p4.CODE_ADJUDICATOR_FAILED,
                      f"the adjudicator raised for task {task_id}: {exc}; nothing is settled") from exc
    if type(returned) is not IntegrationAdjudicationReturn:
        raise p4.stop(p4.CODE_ADJUDICATION_INVALID,
                      f"the Phase Integration adjudicator returned {type(returned).__name__}, not an "
                      "IntegrationAdjudicationReturn (the P4 adjudication and its one Phase outcome); nothing is settled")
    normalized = p4.normalize_adjudication(returned.adjudication, descriptor, reports, None)
    try:
        outcome = returned.phase_outcome if type(returned.phase_outcome) is ri.PhaseOutcome \
            else ri.PhaseOutcome.from_record(returned.phase_outcome)
        disposition = _integration_disposition(run, normalized, outcome, _integration_current_problems(session, run))
    except ValidationError as exc:
        raise p4.stop(p4.CODE_ADJUDICATION_INVALID,
                      f"the Phase Integration adjudication is not valid: {exc}; nothing is settled") from exc
    _measured(session, run, p4.ADJUDICATION_SETTLE_GENERATION, before)
    finding_ids = [mutation.reserve_id(gate.review_finding_key(run.review_run_id, ordinal), "review_finding")
                   for ordinal in range(1, len(normalized.drafts) + 1)]

    def build(strategy_change_required: bool | None) -> Any:
        return p4.adjudication(
            normalized, finding_ids, review_run_id=run.review_run_id, gate_record=third, candidate_generation=1,
            review_contract=records.P4_PHASE_INTEGRATION_CONTRACT, descriptor=descriptor, reports=reports, prior=None,
            policy_id=run.policy, phase_outcome=outcome, integration_disposition=disposition,
            strategy_change_required=strategy_change_required,
        )

    # CP RB5 Q-C2 / Q-C3 (§32.26 / §32.28): a repair_induced claim may name only a fix Work an earlier repair of this
    # integration registered (its one validated version 2 future_work_link); STRATEGY_CHANGE is the supported B/C
    # relation chain over this G4's drafts - both pure, so the adjudication is built once to read its drafts and
    # once more with the answer recorded. No Run order, timestamp or newest record decides anything here.
    view = ProjectView.load(store)
    fix_works = _integration_fix_works(review, view, str(chain.generations[0].target_identity))
    drafts = p4.relation_drafts(returned.adjudication, build(None), references, policy_id=run.policy,
                                fix_works=fix_works)
    required = p4.integration_strategy_change_required(review, drafts, fix_works=fix_works, work_ids=set(view.works))
    adjudication = build(required)
    drafts = p4.relation_drafts(returned.adjudication, adjudication, references, policy_id=run.policy,
                                fix_works=fix_works)
    relation_ids = [mutation.reserve_id(history.review_relation_key(run.review_run_id, ordinal), "review_relation")
                    for ordinal in range(1, len(drafts) + 1)]
    record = adjudication.to_record()
    digest = serialize.digest(record)
    gate.validate_settlement(store, run.review_run_id, task_id, digest, str(returned.adjudication.adjudicator_identity))
    settled = {"task_id": task_id, "status": records.TASK_SETTLED_OK, "result_digest": digest, "settled_generation": 4}
    gate_four = replace(
        third, generation=4, previous_generation=3, previous_digest=chain.latest_digest, adjudication_digest=digest,
        obligation_digest=serialize.digest(p4.obligations_record(adjudication)),
        settled_tasks=third.settled_tasks + (settled,),
    )
    extra = [(review_paths.adjudication_rel(run.review_run_id), record)]
    # §28.8 / §28.12 / §28.5, ruling OQ-C: the Finding summaries, the relations and - for HUMAN_WAIT and every
    # G4-terminal disposition - the Run summary, in this same G4
    extra += p4.g4_history(adjudication, gate_four, drafts, relation_ids, references, fix_works=fix_works).extra()
    _integration_generation(session, run, 4, p4.TRANSITION_SETTLE, gate_four, extra)
    history.require_history_ready(ReviewStore(store), run.review_run_id, history.BOUNDARY_FINDINGS,
                                  history_contract=history.HISTORY_CONTRACT)


def _integration_seal(session: "_Session", run: IntegrationRun, chain: Any) -> None:
    """G5: the Receipt - only for an AUTHORIZATION_READY disposition, the full convergence and a current Candidate."""
    from .review import integration as ri

    review = ReviewStore(session.store)
    found = review.read_adjudication(run.review_run_id)
    if found.integration_disposition != ri.BRANCH_AUTHORIZATION_READY:
        raise _integration_reconcile(f"Integration Review Run {run.review_run_id} is "
                                     f"{found.integration_disposition}; only AUTHORIZATION_READY seals")
    unmet = p4.convergence_from_records(review, run.review_run_id, chain, _integration_envelope(review, chain),
                                        evidence_current=True)
    if unmet:
        raise _integration_reconcile(f"Integration Review Run {run.review_run_id} is not converged: " + "; ".join(unmet))
    current = _integration_current_problems(session, run)
    if current:
        raise _integration_reconcile("the Phase Integration Candidate is no longer current: " + "; ".join(current)
                                     + "; no Receipt issues", "review_candidate_mismatch")
    fourth = chain.latest
    receipt_id = session.mutation.reserve_id(gate.review_receipt_key(run.review_run_id, p4.SEAL_GENERATION),
                                             "review_receipt")
    run.receipt_id = receipt_id
    gate_five = replace(fourth, generation=5, previous_generation=4, previous_digest=chain.latest_digest,
                        status=records.GATE_STATUS_SEALED, receipt_id=receipt_id,
                        authorized_operation_stage=ri.AUTHORIZED_OPERATION_STAGE)
    receipt = records.Receipt(
        receipt_id=receipt_id, review_run_id=run.review_run_id, review_generation=p4.SEAL_GENERATION,
        review_kind=fourth.review_kind, target_identity=fourth.target_identity,
        operation_identity=fourth.operation_identity, authorized_candidate_hash=fourth.candidate_hash,
        review_context_hash=fourth.review_context_hash, effective_policy_hash=fourth.effective_policy_hash,
        coverage_hash=fourth.coverage_digest, adjudication_hash=fourth.adjudication_digest,
        obligation_digest=fourth.obligation_digest, unresolved_obligations=0,
        authorized_operation_stage=ri.AUTHORIZED_OPERATION_STAGE,
    )
    _integration_generation(session, run, 5, p4.TRANSITION_SEAL, gate_five,
                            [(review_paths.receipt_rel(receipt_id), receipt.to_record())], receipt_id=receipt_id)


# --------------------------------------------------------------------------- the terminal stage (§32.30 - §32.31)

def _frozen_terminal(mutation: Mutation, work_id: str) -> tuple[str, dict[str, Any]] | None:
    """The terminal stage the frozen Candidate of this START's current Run of ``work_id`` names, with its record."""
    runs = _integration_runs(mutation, work_id)
    frozen = (mutation.note(NOTE_INTEGRATION_FREEZE) or {}).get(runs[-1]) if runs else None
    if not isinstance(frozen, dict):
        return None
    stage = ((frozen.get("candidate") or {}).get("owning_operation") or {}).get("terminal_stage")
    return (stage, frozen) if isinstance(stage, str) else None


def is_integration_terminal_stage(mutation: Mutation, stage: str, work_id: str) -> bool:
    """Whether ``stage`` is exactly the terminal stage this START records for its reviewed integration ``work_id``
    (``start._recorded_completion``): the stage its frozen Candidate names, holding the P5 Run summary, the ordinary
    ``work_target_removed`` / ``work_completed`` under the IDs reserved for them, the version 5 Consumption and,
    when owed, the Phase completion evidence - in that order, and nothing else."""
    found = _frozen_terminal(mutation, work_id)
    if found is None or found[0] != stage:
        return False
    effects = mutation.stage_effects(stage)
    kinds = [effect.get("kind") for effect in effects]
    if kinds not in (["create_file", "append_event", "append_event", "create_file"],
                     ["create_file", "append_event", "append_event", "create_file", "create_file"]):
        return False
    events = [effect["payload"]["record"] for effect in effects if effect.get("kind") == "append_event"]
    return [(event.get("type"), event.get("entity")) for event in events] == [
        ("work_target_removed", work_id), ("work_completed", work_id)] and all(
        mutation.reserved(f"{stage}:event:{index}") == event.get("id") for index, event in enumerate(events))


def _integration_terminal_gate(session: "_Session", work: Entity, run: IntegrationRun, chain: Any,
                               receipt: records.Receipt) -> list[str]:
    """§14.16 + §32.30, every fact established under the START lock (none has a passing default)."""
    from . import phase_integration as pi
    from . import start_integration_review as sir
    from .review import integration as ri
    from .validate import validate_structure

    store = session.store
    review = ReviewStore(store)
    view = ProjectView.load(store)
    current = _integration_current_problems(session, run)
    adjudication = review.read_adjudication(run.review_run_id)
    latest = chain.latest
    chains = {}
    for found_id in sorted(review.run_ids()):
        other = review.gate_chain(found_id)
        first = None if other is None else other.generations[0]
        if first is not None and (first.review_kind, first.target_identity) == (ri.REVIEW_KIND, work.id):
            chains[found_id] = other
    # a Run set aside by an Integration Run's own request (a decided HUMAN_WAIT) is no longer pending beside it
    named = {str(item["review_run_id"]) for other in chains.values()
             for item in _integration_envelope(review, other).get("set_aside_runs") or []}
    others = [found_id for found_id, other in chains.items() if found_id != run.review_run_id
              and found_id not in named and _integration_settled(review, other) is None]
    readiness = history.readiness_problems(review, run.review_run_id, history.BOUNDARY_FINDINGS,
                                           history_contract=history.HISTORY_CONTRACT)
    current_work = view.works.get(work.id)
    facts = sir.TerminalGateFacts(
        ordinary_precheck_passed=not view.unsatisfied_dependencies(work.id),
        marker_matches=current_work is not None and pi.is_reviewed_integration(current_work)
        and current_work.phase_review_contract == run.candidate["integration"]["phase_review_contract"],
        candidate_current=not current, structural_validation_passed=not validate_structure(view),
        structural_coverage_current=not current, phase_basis_invalidated=bool(current),
        review_complete=latest.sealed and latest.generation == p4.SEAL_GENERATION,
        review_evidence_current=not current, branch=str(adjudication.integration_disposition),
        phase_outcome=str((adjudication.phase_outcome or {}).get("outcome")),
        downstream_confirmation_modeled=bool(ri.downstream_confirmation_ids_of(run.candidate)),
        blocking_problems=sum(1 for finding in adjudication.findings if finding["blocking"]),
        dispositions_valid=not p4.convergence_from_records(review, run.review_run_id, chain,
                                                           _integration_envelope(review, chain), evidence_current=True),
        receipt_authorizes_candidate=(
            latest.receipt_id == receipt.receipt_id and receipt.review_run_id == run.review_run_id
            and receipt.authorized_candidate_hash == ri.candidate_hash(run.candidate)
            and receipt.review_kind == ri.REVIEW_KIND and receipt.target_identity == work.id
            and receipt.authorized_operation_stage == ri.AUTHORIZED_OPERATION_STAGE),
        history_obligations_valid=not readiness, incompatible_pending_successor=bool(others),
        side_effect_problems=_side_effect_problems(session, run),
        conflicts=tuple(
            ([f"Receipt {receipt.receipt_id} is already consumed"]
             if review.consumption_by_receipt().get(receipt.receipt_id) is not None else [])
            + ([f"Receipt {receipt.receipt_id} is superseded"] if review.supersession_exists(receipt.receipt_id) else [])
            + [f"Integration Review Run {other} of {work.id} is pending beside it" for other in others]),
        unclosed_obligations=tuple(f"{count} open HUMAN obligation(s)" for count in
                                   [int((adjudication.obligations or {}).get("human") or 0)] if count),
    )
    return sir.terminal_gate_problems(facts)


def _integration_terminal(session: "_Session", work: Entity, run: IntegrationRun, chain: Any) -> Any:
    """§32.30 - §32.31: the terminal gate, then ONE recorded stage, then START's ordinary completion finalization.

    The stage holds, in order: the consumed P5 Run summary, the integration's
    ordinary ``work_target_removed`` and unmarked ``work_completed`` (the
    Receipt authorizes this stage only), the version 5 Integration Consumption
    bound to exactly that ``work_completed`` event ID - every ID reserved before
    the stage is recorded, so a resume binds the same pair - and, when this
    terminal transition makes the reviewed Phase generated-complete, the Phase
    completion evidence (§32.35 - §32.37). Its finalization is START's ordinary
    ``<Work>:finalize`` commit and push; a resume that finds the stage recorded
    and unfinalized finishes it from the record (``start._completion_to_finish``).
    """
    from . import achievement as ach
    from .ops import new_event
    from .review import integration as ri

    store, mutation = session.store, session.mutation
    review = ReviewStore(store)
    stage = str(run.candidate["owning_operation"]["terminal_stage"])
    if not mutation.has_stage(stage):
        if stage_name(mutation, f"{work.id}:lifecycle") != stage:
            raise _integration_reconcile(f"the next lifecycle stage of {work.id} is no longer the terminal stage its "
                                         f"Candidate names ({stage})", "review_candidate_mismatch")
        receipt = review.read_receipt(str(run.receipt_id))
        refused = _integration_terminal_gate(session, work, run, chain, receipt)
        if refused:
            raise StopError(f"integration {work.id} may not record its terminal stage (§32.30): " + "; ".join(refused),
                            code=ri.CODE_NOT_AUTHORIZABLE)
        consumption_id = mutation.reserve_id(gate.review_consumption_key(receipt.receipt_id), "review_consumption")
        removed = new_event(mutation, f"{stage}:event:0", "work_target_removed", work.id)
        completed = new_event(mutation, f"{stage}:event:1", "work_completed", work.id)
        consumption = records.IntegrationConsumption(
            consumption_id, receipt.receipt_id, receipt.review_run_id, receipt.review_generation, receipt.review_kind,
            receipt.authorized_candidate_hash, receipt.operation_identity, mutation.id, completed.id, completed.type,
            work.id,
        )
        sealed = chain.generation(p4.SEAL_GENERATION)
        summary = history.consumed_run_summary(sealed, receipt, consumption_id,
                                               candidate_generation=p4.run_candidate_generation(review, chain),
                                               adjudication=p4.bound_adjudication(review, chain))
        summary_path = review_paths.history_run_rel(run.review_run_id)
        consumption_path = review_paths.consumption_rel(consumption_id)
        effects = [
            Effect.create_file(summary_path, serialize.canonical_text(summary.to_record())),
            Effect.append_event(removed),
            Effect.append_event(completed),
            Effect.create_file(consumption_path, serialize.canonical_text(consumption.to_record())),
        ]
        paths = [summary_path, consumption_path]
        view = ProjectView.load(store)
        # the projection carries the very events the stage records, so the basis it binds is HEAD's after finalization
        projected = replace(view, events=list(view.events) + [removed, completed])
        phase_id = str(run.candidate["phase_id"])
        existing = review.phase_completion_evidence()
        if ach.phase_evidence_obligation(projected, phase_id, existing).required:
            adjudication = review.read_adjudication(run.review_run_id)
            outcome = ri.PhaseOutcome.from_record(adjudication.phase_outcome)
            evidence_id = mutation.reserve_id(f"{stage}:achievement", "review_achievement")
            # CPQ-05A: four distinct digests, each of its own record - the TERMINAL gate generation (never the Run
            # summary), the Receipt, the Consumption - and the separate consumed P5 summary reference
            ref = ach.IntegrationRunRef(
                work.id, run.review_run_id, receipt.authorized_candidate_hash, chain.latest_digest, receipt.receipt_id,
                review.receipt_digest(receipt.receipt_id), consumption_id, serialize.digest(consumption.to_record()),
                serialize.digest(summary.to_record()),
            )
            sources = [message for _, message in history.integration_run_ref_problems(
                review, ref, outcome, consumption=consumption, run_summary=summary)]
            evidence = ach.phase_completion_evidence_for(
                projected, phase_id, existing, achievement_evidence_id=evidence_id, covering_integration_id=work.id,
                integration_review=ref, phase_outcome=outcome, source_ref_problems=sources,
                evaluators=[(str(task["task_slot"]), str(task["reviewer_identity"]), str(task["reviewer_version"]))
                            for task in sealed.accepted_tasks],
                rationale=outcome.rationale, causing_mutation_id=mutation.id, causing_operation=OWNER,
                causing_event_ids=[completed.id],
                work_review_refs=[(item["work_id"], item["review_run_id"], item["run_summary_digest"])
                                  for item in run.candidate["work_review_refs"]],
            )
            if evidence is not None:
                evidence_path = review_paths.history_achievement_rel(evidence_id)
                effects.append(Effect.create_file(
                    evidence_path, serialize.canonical_text(history.achievement_record(evidence).to_record())))
                paths.append(evidence_path)
        gate.require_committable(store, paths)
        gitops.require_no_planning_transform(store.root, paths)
        checkout.require_checkout_capability(store, paths)
        missing = [path for path in paths if path not in mutation.scope.files]
        if missing:
            mutation.extend_scope(files=missing)
        mutation.add_effects(stage, effects)
    mutation.apply()
    history.require_history_ready(review, run.review_run_id, history.BOUNDARY_CONSUMPTION,
                                  history_contract=history.HISTORY_CONTRACT,
                                  consumption_id=mutation.reserved(gate.review_consumption_key(str(run.receipt_id))))
    return session.finish_completion(work.id)


# --------------------------------------------------------------------------- R26: after a G4-terminal Run

def _followups(mutation: Mutation) -> dict[str, dict[str, Any]]:
    found = mutation.note(NOTE_INTEGRATION_FOLLOWUPS)
    if found is None:
        return {}
    if not isinstance(found, dict) or not all(isinstance(key, str) and isinstance(value, dict)
                                              for key, value in found.items()):
        raise _integration_reconcile(f"START mutation {mutation.id}'s Integration follow-ups are not a Run mapping")
    return dict(found)


def _set_followup(mutation: Mutation, run_id: str, entry: dict[str, Any] | None) -> None:
    found = _followups(mutation)
    if entry is None:
        found.pop(run_id, None)
    else:
        found[run_id] = entry
    mutation.set_note(NOTE_INTEGRATION_FOLLOWUPS, found)


def _recorded_stages(mutation: Mutation) -> list[str]:
    stages: list[str] = []
    for effect in mutation.effects:
        if effect["stage"] not in stages:
            stages.append(effect["stage"])
    return stages


def _repair_move(mutation: Mutation, run_id: str) -> tuple[str, str] | None:
    """The removal and the commit that ended the repaired cycle of ``run_id``, when both are recorded."""
    entry = _followups(mutation).get(run_id)
    if not entry or entry.get("kind") != FOLLOWUP_REPAIR or not mutation.has_stage(str(entry.get("stage"))):
        return None
    stages = _recorded_stages(mutation)
    after = stages[stages.index(str(entry["stage"])) + 1:]
    work_id = str(entry.get("work_id"))
    removal = next((name for name in after if name.startswith(f"{work_id}:lifecycle:") and any(
        (effect["payload"].get("record") or {}).get("type") == "work_target_removed"
        for effect in mutation.stage_effects(name) if effect["kind"] == "append_event")), None)
    if removal is None:
        return None
    commit = next((name for name in after[after.index(removal) + 1:] if name.startswith("commit:")), None)
    return None if commit is None else (removal, commit)


def _repair_moved(mutation: Mutation, run_id: str) -> bool:
    return _repair_move(mutation, run_id) is not None


def _prior_repair_links(review: ReviewStore, view: ProjectView, work_id: str) -> tuple[Any, ...]:
    """§32.26: the prior supported repair links of this integration, from validated P5 future_work_link provenance."""
    from .review import integration as ri

    links = []
    for relation_id in review.history_ids(review_paths.HISTORY_RELATIONS):
        found = review.read_history(review_paths.HISTORY_RELATIONS, relation_id)
        provenance = found.integration_provenance
        if found.relation_type != history.RELATION_FUTURE_WORK_LINK or provenance is None:
            continue
        chain = review.gate_chain(str(provenance["source_review_run_id"]))
        if chain is None or chain.generations[0].target_identity != work_id \
                or history.relation_problems(review, found, work_ids=set(view.works)):
            continue
        finding = review.read_history(review_paths.HISTORY_FINDINGS, found.source.id)
        links.append(ri.PriorRepairLink(finding.semantic_surface, str(provenance["strategy_id"]), finding.finding_id,
                                        str(provenance["source_review_run_id"]), found.target.id))
    return tuple(sorted(links, key=lambda link: (link.source_review_run_id, link.source_finding_id,
                                                 link.target_work_id)))


def _integration_fix_works(review: ReviewStore, view: ProjectView, work_id: str) -> dict[str, Any]:
    """CP RB5 Q-C2: each fix Work an earlier domain repair of integration ``work_id`` registered, mapped to its one
    validated version 2 ``future_work_link`` (``history.integration_fix_link``) - the only Works a ``repair_induced``
    claim of this integration's adjudication may name. Two links for one Work are a conflict, never a choice."""
    found: dict[str, Any] = {}
    for link in _prior_repair_links(review, view, work_id):
        try:
            relation = history.integration_fix_link(review, link.target_work_id)
        except ValidationError as exc:
            raise _integration_reconcile(f"fix Work {link.target_work_id} of integration {work_id}: {exc}",
                                         "review_record_invalid") from exc
        if relation is not None:
            found[link.target_work_id] = relation
    return found


def integration_repair_context(store: ProjectStore, work_id: str, review_run_id: str) -> Any:
    """§32.25 - §32.26: the canonical blocking obligation set of a DOMAIN_REPAIR_REQUIRED Run, from its G4 records only:
    its blocking Findings with their semantic surfaces, the unmet objective obligations of its Phase outcome, the
    validated prior repair links of the integration and whether STRATEGY_CHANGE is required."""
    from .review import integration as ri

    review = ReviewStore(store)
    adjudication = review.read_adjudication(review_run_id)
    if adjudication.integration_disposition != ri.BRANCH_DOMAIN_REPAIR_REQUIRED:
        raise _integration_reconcile(f"Integration Review Run {review_run_id} is {adjudication.integration_disposition}, "
                                     "not DOMAIN_REPAIR_REQUIRED")
    blocking = tuple(sorted((str(finding["finding_id"]), str(finding["semantic_surface"]))
                            for finding in adjudication.findings if finding["blocking"]))
    outcome = adjudication.phase_outcome or {}
    context = ri.IntegrationRepairContext(
        work_id, review_run_id, blocking, tuple(outcome.get("unmet_objective_obligations") or ()),
        _prior_repair_links(review, ProjectView.load(store), work_id),
        bool((adjudication.obligations or {}).get("strategy_change_required")),
    )
    problems = context.problems()
    if problems:
        raise _integration_reconcile(f"the canonical records of Integration Review Run {review_run_id} make no domain "
                                     "repair context: " + "; ".join(problems), "review_record_invalid")
    return context


def _ask_repair(session: "_Session", work: Entity, context: Any) -> Any:
    """START's executor in the dedicated integration-repair planning context - only after G4 (§32.25)."""
    from . import start as st

    store = session.store
    view = ProjectView.load(store)
    work = view.works[work.id]
    phase = view.phases.get(str(work.phase_id))
    roadmap = view.roadmaps.get(phase.roadmap_id or "") if phase is not None else None
    found = st.ExecutionContext(store, view, work, view.work_state(work.id), phase, roadmap,
                                st.reading_plan(store, view, work), session.mutation.id, session.mode, 1,
                                integration_repair=context)
    return session.executor(found)


def _integration_domain_repair(session: "_Session", view: ProjectView, work: Entity, run: IntegrationRun) -> Any:
    """R26 / §32.25 - §32.27: a DOMAIN_REPAIR_REQUIRED Run is repaired through START's normal fix Works.

    START hands its executor the canonical blocking obligation set and accepts
    only an IntegrationRepairPlan over its own ``Derive`` (moving the target off,
    no second integration, normal fix Works before the integration) - or the
    existing question / hold behaviour; nothing completes past the blocking
    Findings. The plan is kept before its registration, then registered through
    START's derivation (CREATE), the target removed and the move committed;
    the integration stays in progress and is entered again after its fixes,
    with a new Candidate and Run (:func:`_integration_run`). A resume finishes
    the kept plan from the record and never asks again.
    """
    from . import input_validation
    from . import start as st
    from . import start_integration_review as sir

    store, mutation = session.store, session.mutation
    entry = _followups(mutation).get(run.review_run_id)
    if entry is None:
        context = integration_repair_context(store, work.id, run.review_run_id)
        outcome = _ask_repair(session, work, context)
        if isinstance(outcome, st.QuestionWait):
            return st.StartResult("question_wait", work.id, mutation.id, phase_id=work.phase_id, detail=outcome.question)
        if isinstance(outcome, st.Hold):
            session._record_hold(work, outcome)
            session._commit("commit", st.finalization_message(st._HELD, work.display), [])
            return st.StartResult("held", work.id, mutation.id, phase_id=work.phase_id, detail=outcome.reason,
                                  head=gitcmd.head_commit(store.root))
        refused = sir.repair_outcome_problems(outcome, context)
        if refused:
            raise StopError(f"the repair plan for integration {work.id} is refused: " + "; ".join(refused)
                            + "; nothing of it was recorded", code=CODE_INTEGRATION_REPAIR_PLAN_INVALID)
        kept = st._recorded_outcome(outcome.derive)
        if kept is None or st._outcome_from_record(kept) != outcome.derive:
            raise StopError(f"the repair plan for integration {work.id} cannot be kept in the record exactly; nothing "
                            "of it was recorded", code="input_unrepresentable")
        current = ProjectView.load(store)
        specs, relations = st._derivation_registration(current, current, current.works[work.id], outcome.derive,
                                                       semantics=session.semantics)
        input_validation.require_work_specs(specs, "integration fix work")
        input_validation.require_relations(relations, specs, "integration fix relation")
        input_validation.require_works_text(specs, "integration fix work")
        entry = {"kind": FOLLOWUP_REPAIR, "work_id": work.id, "strategy_id": outcome.strategy_id, "derive": kept,
                 "stage": stage_name(mutation, f"{work.id}:derive"), "display": work.display,
                 "blocking_finding_ids": list(context.blocking_finding_ids),
                 "provenance": stage_name(mutation, f"{work.id}:repair-provenance")}
        _set_followup(mutation, run.review_run_id, entry)
    stage = str(entry["stage"])
    derive = st._outcome_from_record(entry["derive"])
    replay = st._ProvenDerivation(work.id, stage, derive, "derive", mutation.has_stage(stage), entry.get("display"))
    current = ProjectView.load(store)
    try:
        work_ids = session._derive(current, current.works[work.id], derive, replay)
    except BaseException:
        if not mutation.has_stage(stage):
            _set_followup(mutation, run.review_run_id, None)  # nothing of the plan was carried out: asked again
        raise
    _record_fix_links(session, run.review_run_id, entry, work_ids)
    if ProjectView.load(store).work_state(work.id).has_target:
        session._lifecycle(current.works[work.id], ["work_target_removed"])
    session._commit("commit", st._move_message(str(entry.get("display") or work.display), "derive"), [])
    state = ProjectView.load(store).work_state(work.id)
    if state.terminal or state.has_target:
        raise StopError(f"{work.id} is {state.state} and still carries its target after the repair move",
                        code="postcheck_failed")
    return st.StartResult("moved", work.id, mutation.id, tuple(session.completed), work.phase_id,
                          head=gitcmd.head_commit(store.root))


def _record_fix_links(session: "_Session", run_id: str, entry: dict[str, Any], work_ids: dict[str, str]) -> None:
    """§32.26 / §32.50 (R16): the version 2 ``future_work_link`` of each (blocking Finding, fix Work) START's repair
    plan registered - the source Integration Run and the strategy identity as provenance - in their own stage between
    the registration and the move, so the move commit carries them. Provenance only: they put no Work in a
    completion set and make Review no Work owner. A plan resting only on unmet objective obligations (no blocking
    Finding) links nothing. Recorded once; a resume replays the recorded stage."""
    from .review import integration as ri

    store, mutation = session.store, session.mutation
    stage = entry.get("provenance")
    findings = sorted(str(finding_id) for finding_id in entry.get("blocking_finding_ids") or [])
    if not isinstance(stage, str) or not findings or mutation.has_stage(stage):
        return
    review = ReviewStore(store)
    strategy = str(entry["strategy_id"])
    effects, paths = [], []
    for finding_id in findings:
        source = review.read_history(review_paths.HISTORY_FINDINGS, finding_id)
        for ordinal, key in enumerate(sorted(work_ids), start=1):
            problems = ri.IntegrationFixProvenance(run_id, finding_id, strategy, work_ids[key]).problems()
            if problems:
                raise _integration_reconcile(f"the fix provenance of {work_ids[key]} is invalid: " + "; ".join(problems),
                                             "review_record_invalid")
            relation_id = mutation.reserve_id(history.review_relation_key(finding_id, ordinal), "review_relation")
            relation = history.future_work_link(
                relation_id, source, work_ids[key], status=history.CAUSAL_SUPPORTED, rationale=FIX_LINK_RATIONALE,
                supporting_evidence_digests=[source.adjudication_digest],
                integration_provenance={"source_review_run_id": run_id, "strategy_id": strategy},
            )
            path = review_paths.history_relation_rel(relation_id)
            effects.append(Effect.create_file(path, serialize.canonical_text(relation.to_record())))
            paths.append(path)
    gate.require_committable(store, paths)
    gitops.require_no_planning_transform(store.root, paths)
    checkout.require_checkout_capability(store, paths)
    missing = [path for path in paths if path not in mutation.scope.files]
    if missing:
        mutation.extend_scope(files=missing)
    mutation.add_effects(stage, effects)
    mutation.apply()


def _integration_confirmation_structure(session: "_Session", view: ProjectView, work: Entity,
                                        run: IntegrationRun) -> IntegrationRun:
    """§32.23: CONFIRMATION_STRUCTURE_REQUIRED - exactly one deterministic confirmation through CREATE, committed,
    then a successor Run of the same integration over a new Candidate that binds it.

    Reviewer text never reaches the structure (``confirmation_structure``); one
    valid downstream confirmation already there means none is created; several
    generated duplicates are a reconcile failure. The structure commit carries
    only the registration's own paths, so START's opening of the integration
    stays its uncommitted lifecycle projection. The successor never names the
    final Run (MC-7). Decided once and finished from the record on resume.
    """
    from . import start_integration_review as sir
    from .create import register_works
    from .ops import _owned_paths

    store, mutation = session.store, session.mutation
    phase_id = str(run.candidate["phase_id"])
    entry = _followups(mutation).get(run.review_run_id)
    if entry is None:
        decision, _ = sir.confirmation_decision(ProjectView.load(store), phase_id, work.id)
        entry = {"kind": FOLLOWUP_STRUCTURE, "work_id": work.id, "stage": stage_name(
            mutation, f"{work.id}:structure") if decision == sir.CONFIRMATION_CREATE else None}
        _set_followup(mutation, run.review_run_id, entry)
    stage = entry.get("stage")
    if isinstance(stage, str):
        if not mutation.has_stage(stage):
            specs, relations = sir.confirmation_registration(ProjectView.load(store), phase_id, work.id)
            ledger = f"{review_paths.WORKLINE_DIR}/relations/roadmap.yaml"
            if ledger in gitops.record_preexisting_dirty(mutation, store.root):
                raise StopError(f"the confirmation structure of {work.id} writes {ledger}, which held a change from "
                                "before this operation; nothing of it was recorded", code="dirty_overlap")
            register_works(mutation, stage, specs, relations)
        paths = _owned_paths(mutation.stage_effects(stage))
        session._commit(f"{work.id}:structure-commit", f"chore(workline): add the Phase confirmation of {work.display}",
                        paths, include_canonical=False)
    return _integration_successor(session, view, work, run.review_run_id, ())


# --------------------------------------------------------------------------- R27: evidence at an ordinary completion

def _covering_reference(store: ProjectStore, mutation: Mutation, review: ReviewStore, view: ProjectView,
                        projected: ProjectView, phase_id: str) -> Any:
    """The covering integration of the projected basis and the references of its consumed Integration Run - found by
    the Consumption of the integration's own ``work_completed`` - or ``None`` when none can be cited (a Run with no
    gate chain included, RB5K-2).

    The records are read through the working Project's Review store, and the
    evidence built from them is immutable and committed by this operation: so
    every record a reference is read from (the Consumption, the consumed Run
    summary, the Receipt, the adjudication, every gate generation, the Candidate
    snapshot) must hold no change from before this operation - one that does is
    refused ``dirty_overlap`` and never bound (RB5K-1), so the evidence binds
    only bytes HEAD holds.
    """
    from . import achievement as ach
    from .review import integration as ri

    basis = ach.phase_basis(projected, phase_id)
    for integration_id in sorted(basis.covering_integration_ids):
        completed = [event.id for event in view.events_for(integration_id) if event.type == "work_completed"]
        consumption = next((found for found in review.consumptions()
                            if isinstance(found, records.IntegrationConsumption)
                            and found.target_identity == integration_id and found.terminal_event_id in completed), None)
        if consumption is None:
            continue
        run_id = consumption.review_run_id
        chain = review.gate_chain(run_id)
        if chain is None:
            continue
        sources = [review_paths.consumption_rel(consumption.consumption_id), review_paths.history_run_rel(run_id),
                   review_paths.receipt_rel(consumption.receipt_id), review_paths.adjudication_rel(run_id),
                   review_paths.candidate_snapshot_rel(chain.generations[0].candidate_hash)]
        sources += [review_paths.gate_rel(run_id, generation.generation) for generation in chain.generations]
        dirty = sorted(set(gitops.record_preexisting_dirty(mutation, store.root)) & set(sources))
        if dirty:
            raise StopError(f"the Review records the Phase completion evidence of {phase_id} would cite held a change "
                            "from before this operation (" + ", ".join(dirty) + "); the evidence binds only what HEAD "
                            "holds, so nothing was recorded", code="dirty_overlap")
        receipt = review.read_receipt(consumption.receipt_id)
        adjudication = review.read_adjudication(run_id)
        outcome = ri.PhaseOutcome.from_record(adjudication.phase_outcome)
        ref = ach.IntegrationRunRef(
            integration_id, run_id, receipt.authorized_candidate_hash, chain.latest_digest, receipt.receipt_id,
            review.receipt_digest(receipt.receipt_id), consumption.consumption_id,
            review.consumption_digest(consumption.consumption_id), review.history_digest(review_paths.HISTORY_RUNS, run_id),
        )
        candidate = review.read_candidate_snapshot(chain.generations[0].candidate_hash).material or {}
        evaluators = [(str(task["task_slot"]), str(task["reviewer_identity"]), str(task["reviewer_version"]))
                      for task in chain.latest.accepted_tasks]
        refs = [(item["work_id"], item["review_run_id"], item["run_summary_digest"])
                for item in candidate.get("work_review_refs") or []]
        return integration_id, ref, outcome, evaluators, refs
    return None


def completion_evidence_effects(store: ProjectStore, mutation: Mutation, work: Entity, stage: str,
                                events: list[Effect]) -> list[Effect]:
    """§32.36 - §32.37 for an ordinary START completion (a downstream confirmation, or any Work whose completion
    closes the current reviewed basis): the phase_completion evidence, reserved and built before the completion is
    recorded, for its SAME lifecycle stage - or nothing. A legacy Phase pays nothing: its completion mode is read
    before any basis is computed."""
    from . import achievement as ach
    from . import phase_integration as pi

    view = ProjectView.load(store)
    phase_id = str(work.phase_id)
    if work.phase_id is None or phase_id not in view.phases or pi.completion_mode(view, phase_id) != pi.MODE_REVIEWED:
        return []
    added = [Event.from_record(effect.payload["record"]) for effect in events]
    projected = replace(view, events=list(view.events) + added)
    review = ReviewStore(store)
    existing = review.phase_completion_evidence()
    if not ach.phase_evidence_obligation(projected, phase_id, existing).required:
        return []
    found = _covering_reference(store, mutation, review, view, projected, phase_id)
    if found is None:
        raise StopError(f"completing {work.id} makes reviewed Phase {phase_id} generated-complete, and no covering "
                        "integration's consumed Review can be cited: no evidence is fabricated, nothing was recorded",
                        code=CODE_PHASE_EVIDENCE_UNAVAILABLE)
    integration_id, ref, outcome, evaluators, refs = found
    sources = [message for _, message in history.integration_run_ref_problems(review, ref, outcome)]
    evidence_id = mutation.reserve_id(f"{stage}:achievement", "review_achievement")
    evidence = ach.phase_completion_evidence_for(
        projected, phase_id, existing, achievement_evidence_id=evidence_id, covering_integration_id=integration_id,
        integration_review=ref, phase_outcome=outcome, source_ref_problems=sources, evaluators=evaluators,
        rationale=outcome.rationale, causing_mutation_id=mutation.id, causing_operation=OWNER,
        causing_event_ids=[added[-1].id], work_review_refs=refs,
    )
    if evidence is None:
        return []
    path = review_paths.history_achievement_rel(evidence_id)
    fsafe.require_immutable_create()
    gate.require_committable(store, [path])
    gitops.require_no_planning_transform(store.root, [path])
    checkout.require_checkout_capability(store, [path])
    if path not in mutation.scope.files:
        mutation.extend_scope(files=[path])
    return [Effect.create_file(path, serialize.canonical_text(history.achievement_record(evidence).to_record()))]


def replan_evidence_effects(store: ProjectStore, mutation: Mutation, work_id: str, stage: str,
                            causing_event_ids: list[str], *, causing_operation: str = OWNER) -> list[Effect]:
    """§32.36 - §32.37 for START's cancel (its replan applied): the phase_completion evidence over the Project as the
    cancel's applied effects leave it, reserved and built before the final commit - or nothing. A legacy Phase pays
    nothing. A basis whose evidence cannot be valid (no covering integration's consumed Review can be cited, or the
    body does not hold - e.g. its required Human confirmation was cancelled) is not written over: no evidence is
    fabricated, the obligation stays open and progression stays blocked, and the cancel itself is never refused."""
    from . import achievement as ach
    from . import phase_integration as pi

    view = ProjectView.load(store)
    work = view.works.get(work_id)
    phase_id = None if work is None else work.phase_id
    if phase_id is None or phase_id not in view.phases or pi.completion_mode(view, phase_id) != pi.MODE_REVIEWED:
        return []
    review = ReviewStore(store)
    existing = review.phase_completion_evidence()
    if not ach.phase_evidence_obligation(view, phase_id, existing).required:
        return []
    try:
        found = _covering_reference(store, mutation, review, view, view, phase_id)
    except StopError as refused:
        if refused.code != "dirty_overlap":
            raise
        return []  # RB5K-1 for a cancel / exclusion: nothing is bound from changed records, and the owner is not refused
    if found is None:
        return []
    integration_id, ref, outcome, evaluators, refs = found
    sources = [message for _, message in history.integration_run_ref_problems(review, ref, outcome)]
    try:
        evidence = ach.phase_completion_evidence_for(
            view, phase_id, existing, achievement_evidence_id=mutation.reserve_id(stage, "review_achievement"),
            covering_integration_id=integration_id, integration_review=ref, phase_outcome=outcome,
            source_ref_problems=sources, evaluators=evaluators, rationale=outcome.rationale,
            causing_mutation_id=mutation.id, causing_operation=causing_operation, causing_event_ids=causing_event_ids,
            work_review_refs=refs,
        )
    except ValidationError:
        return []
    if evidence is None:
        return []
    path = review_paths.history_achievement_rel(evidence.achievement_evidence_id)
    fsafe.require_immutable_create()
    gate.require_committable(store, [path])
    gitops.require_no_planning_transform(store.root, [path])
    checkout.require_checkout_capability(store, [path])
    if path not in mutation.scope.files:
        mutation.extend_scope(files=[path])
    return [Effect.create_file(path, serialize.canonical_text(history.achievement_record(evidence).to_record()))]


def stage_evidence_postcommit(store: ProjectStore, mutation: Mutation, stage: str) -> None:
    """§32.39 for an owner that records phase_completion evidence in a stage of its own (a Roadmap work-plan
    exclusion): when ``stage`` is recorded, HEAD holds its record byte for byte and the evidence is HEAD's committed
    Phase basis; a mismatch is reconcile required, never replaced. An owner that recorded none pays nothing."""
    from . import achievement as ach

    if not mutation.has_stage(stage):
        return
    expected = {effect["payload"]["path"]: effect["payload"]["content"].encode("utf-8")
                for effect in mutation.stage_effects(stage) if effect.get("kind") == "create_file"}
    git = hermetic_module.enter(store)
    _, head = _head(git)
    held = {entry.path: entry for entry in gitcmd.tree_entries(store.root, head, sorted(expected)) or []}
    for path, data in sorted(expected.items()):
        entry = held.get(path)
        if entry is None or entry.type != "blob" or entry.mode != "100644" \
                or gitcmd.read_blob(store.root, entry.oid) != data:
            raise _reconcile(f"{path} is not committed at HEAD as a 100644 blob of the canonical bytes stage {stage} "
                             "recorded", "review_not_persisted")
    evidence_id = mutation.reserved(stage)
    if evidence_id is None or review_paths.history_achievement_rel(evidence_id) not in expected:
        return
    evidence = ReviewStore(store).read_achievement(evidence_id).evidence
    problems = ach.postcommit_basis_problems(
        evidence, ach.phase_basis(committed_view_at(store, git, head), evidence.phase_id))
    if problems:
        raise _reconcile("the Phase completion evidence stage " + stage + " recorded is not HEAD's committed Phase "
                         "basis (§32.39): " + "; ".join(problems) + "; no replacement evidence is made",
                         REASON_ACHIEVEMENT_BASIS_MISMATCH)


def roadmap_achievement_postcommit(store: ProjectStore, mutation: Mutation, roadmap_id: str, head: str,
                                   stage: str) -> None:
    """§32.46 step 11 for the Roadmap owner's achieved path: the roadmap_achieved event, its roadmap_achievement
    evidence and the Roadmap basis read back from commit ``head`` itself as one decision. Nothing is repaired or
    replaced: a mismatch is reconcile required, with the achievement reason stage_evidence_postcommit uses."""
    from . import achievement as ach
    from .committed_view import committed_view

    evidence_id = mutation.reserved(f"{stage}:achievement")
    event_id = mutation.reserved(f"{stage}:event:0")
    committed = committed_view(store, head)
    evidence = ReviewStore(store).read_achievement(str(evidence_id)).evidence
    (event,) = [found for found in committed.events if found.id == event_id]
    basis = ach.roadmap_basis(committed, roadmap_id, ReviewStore(store).phase_completion_evidence(),
                              review_refs=evidence.review_refs, human_decision_ref=evidence.human_decision_ref)
    problems = ach.readback_problems(evidence, basis, event)
    if problems:
        raise _reconcile(f"the committed roadmap_achieved of {roadmap_id} and its evidence do not read back as one "
                         "decision: " + "; ".join(problems), REASON_ACHIEVEMENT_BASIS_MISMATCH)


def completion_postcommit(store: ProjectStore, mutation: Mutation, work_id: str) -> None:
    """After a completion's finalization (§32.31, §32.39): the Review records its lifecycle stage wrote - an
    integration terminal stage's, or an ordinary completion's evidence - are committed at HEAD byte for byte, and
    phase_completion evidence is HEAD's committed Phase basis. Nothing is repaired or replaced: a mismatch is
    reconcile required. A completion that wrote no Review record (every legacy one) is not this check's."""
    from . import achievement as ach

    stages = [name for name in _recorded_stages(mutation) if name.startswith(f"{work_id}:lifecycle:") and any(
        (effect["payload"].get("record") or {}).get("type") in ("work_completed", "work_cancelled")
        for effect in mutation.stage_effects(name) if effect["kind"] == "append_event")]
    if not stages:
        return
    stage = stages[-1]
    expected = {effect["payload"]["path"]: effect["payload"]["content"].encode("utf-8")
                for effect in mutation.stage_effects(stage) if effect.get("kind") == "create_file"}
    cancelled = [name for name in _recorded_stages(mutation) if name.startswith(f"{work_id}:cancel:")
                 and name.endswith(":achievement")]
    for name in cancelled[-1:]:
        expected.update({effect["payload"]["path"]: effect["payload"]["content"].encode("utf-8")
                         for effect in mutation.stage_effects(name) if effect.get("kind") == "create_file"})
    if not expected:
        return
    git = hermetic_module.enter(store)
    _, head = _head(git)
    entries = gitcmd.tree_entries(store.root, head, sorted(expected))
    held = {entry.path: entry for entry in entries or []}
    for path, data in sorted(expected.items()):
        entry = held.get(path)
        if entry is None or entry.type != "blob" or entry.mode != "100644" \
                or gitcmd.read_blob(store.root, entry.oid) != data:
            raise _reconcile(f"{path} is not committed at HEAD as a 100644 blob of the canonical bytes the completion "
                             f"stage of {work_id} recorded", "review_not_persisted")
    for evidence_id in [mutation.reserved(f"{stage}:achievement")] + [mutation.reserved(name) for name in cancelled[-1:]]:
        if evidence_id is None or review_paths.history_achievement_rel(evidence_id) not in expected:
            continue
        evidence = ReviewStore(store).read_achievement(evidence_id).evidence
        basis = ach.phase_basis(committed_view_at(store, git, head), evidence.phase_id)
        problems = ach.postcommit_basis_problems(evidence, basis)
        if problems:
            raise _reconcile("the Phase completion evidence the completion of " + work_id + " recorded is not HEAD's "
                             "committed Phase basis (§32.39): " + "; ".join(problems) + "; no replacement evidence is "
                             "made", REASON_ACHIEVEMENT_BASIS_MISMATCH)


# --------------------------------------------------------------------------- the owner loop

def review_phase_integration(session: "_Session", view: ProjectView, work: Entity) -> Any:
    """START's Phase Integration Review of one marked integration (§32.16): its lifecycle opens, no executor runs.

    The Run's chain decides the next step, so a resume continues at the
    earliest unfinished generation and decides nothing again:

    ```text
    (none)  G1 accept           1  launch -> G2         2  declined: final not_authorized (STOP)
                                                           otherwise G3 accept
    3  adjudicate -> G4         4  HUMAN_WAIT: pending (R8), a Human decision exits it into a successor Run
                                   DOMAIN_REPAIR_REQUIRED: final not_authorized; START's repair plan, fix
                                     Works, the move (R26) - a new Run when the integration is entered again
                                   CONFIRMATION_STRUCTURE_REQUIRED: final not_authorized; the confirmation
                                     through CREATE, committed, then a successor Run (§32.23)
                                   a step-4 refusal: final not_authorized (STOP)
                                   AUTHORIZATION_READY: G5 seal
    5  sealed: the terminal gate, the terminal stage, START's ordinary finalization
    ```
    """
    from . import start as st
    from .review import integration as ri

    store, mutation = session.store, session.mutation
    held = _integration_runs(mutation, work.id)
    moved = _repair_move(mutation, held[-1]) if held else None
    if moved is not None and _recorded_stages(mutation)[-1] == moved[1]:
        # resumed right after the repair move: that cycle ended there, exactly as uninterrupted
        return st.StartResult("moved", work.id, mutation.id, tuple(session.completed), work.phase_id,
                              head=gitcmd.head_commit(store.root))
    run = _integration_run(session, view, work)
    while True:
        _integration_resolve_pending(session, run)
        review = ReviewStore(store)
        chain = _integration_chain(store, run)
        latest = 0 if chain is None else chain.latest.generation
        if chain is not None:
            problems = p4.chain_problems(chain)
            first = chain.generations[0]
            if first.review_kind != ri.REVIEW_KIND or first.target_identity != work.id \
                    or first.operation_identity != integration_operation_identity(work.id):
                problems.append("generation 1 is not the Phase Integration Review of this integration")
            if problems or p4.shape_of(chain) == p4.SHAPE_REPAIR or latest > p4.SEAL_GENERATION:
                raise _integration_reconcile(f"Integration Review Run {run.review_run_id}: "
                                             + "; ".join(problems or ["not discovery -> adjudication -> seal"]))
        if latest == 0:
            _integration_accept(session, run)
        elif latest == 1:
            _integration_launch(session, run, chain)
        elif latest == p4.DISCOVERY_SETTLE_GENERATION:
            if any(task["status"] != records.TASK_SETTLED_OK for task in chain.latest.settled_tasks):
                raise StopError(f"a discovery task of Integration Review Run {run.review_run_id} declined: the Run is "
                                "final not_authorized and no Receipt issues", code=ri.CODE_NOT_AUTHORIZABLE)
            _integration_accept_adjudication(session, run, chain)
        elif latest == 3:
            _integration_adjudicate(session, run, chain)
        elif latest == p4.ADJUDICATION_SETTLE_GENERATION:
            history.require_history_ready(review, run.review_run_id, history.BOUNDARY_FINDINGS,
                                          history_contract=history.HISTORY_CONTRACT)
            disposition = review.read_adjudication(run.review_run_id).integration_disposition
            if disposition == records.HUMAN_WAIT:
                # R8: the same canonical Run, pending, until an explicit Human decision exits it into a successor
                run = _integration_successor(session, view, work, run.review_run_id,
                                             _integration_exit_wait(session, run.review_run_id, chain, work.id))
                continue
            if disposition == ri.BRANCH_CONFIRMATION_STRUCTURE_REQUIRED:
                run = _integration_confirmation_structure(session, view, work, run)
                continue
            if disposition == ri.BRANCH_DOMAIN_REPAIR_REQUIRED:
                return _integration_domain_repair(session, view, work, run)
            if disposition in records.INTEGRATION_G4_TERMINAL_DISPOSITIONS:
                raise StopError(f"Integration Review Run {run.review_run_id} ended at generation 4 with "
                                f"{disposition}: it is final not_authorized, no Receipt issues, and it is never "
                                "recovered as authorizable; a repaired structure is a new Candidate and a new Run",
                                code=str(disposition))
            _integration_seal(session, run, chain)
        elif chain.latest.sealed:
            run.receipt_id = str(chain.latest.receipt_id)
            return _integration_terminal(session, work, run, chain)
        else:
            raise _integration_reconcile(f"Integration Review Run {run.review_run_id} is at generation {latest}, "
                                         "which this owner never writes")


def is_p4_mutation(mutation: Mutation) -> bool:
    return work_invocation.contract_of(mutation.invocation) == work_review.P4_CONTRACT


def lock_details(review: object) -> dict[str, Any]:
    """The execution lock's holder description: the static contract marker of this invocation, never a caller value."""
    if work_review.is_p4(review):
        return {"review_contract": work_review.P4_CONTRACT}
    return dict(LOCK_DETAILS)


def invocation_for(work_id: str, mode: str, review: object) -> dict[str, Any]:
    """The live invocation plus exactly the two markers of this selector's contract (G-6 Option M)."""
    if work_review.is_p4(review):
        return {"operation": "start", "work_id": work_id, "mode": mode,
                **work_invocation.markers(work_review.P4_CONTRACT)}
    return invocation(work_id, mode)


def _p4_reserved_runs(reserved: dict[str, Any], work_id: str) -> list[str]:
    """The P4 Runs one START mutation holds, first to current, by its exact successor reservations (§27.21)."""
    first = reserved.get(run_key(work_id))
    if not isinstance(first, str):
        return []
    found = [first]
    while True:
        successor = reserved.get(gate.review_successor_run_key(found[-1]))
        if successor is None:
            return found
        if not isinstance(successor, str) or successor in found:
            raise p4.reconcile(f"the successor reservations of Work Review Run {found[-1]} are not one chain",
                               p4.REASON_SUCCESSOR_CONFLICT)
        found.append(successor)


def _p4_work_run(reserved: dict[str, Any], work_id: str, run_id: str) -> WorkRun:
    prefix = f"review-task:{run_id}:{records.P4_DISCOVERY_SLOT_PREFIX}"
    tasks = sorted(str(value) for key, value in reserved.items() if str(key).startswith(prefix))
    receipt = reserved.get(gate.review_receipt_key(run_id, p4.SEAL_GENERATION))
    return WorkRun(work_id, run_id, tasks[0] if tasks else "", str(receipt) if receipt else "",
                   contract=work_review.P4_CONTRACT)


def select_in_flight_p4(mutation: Mutation) -> InFlight | None:
    """The P4 recovery selector: the current Run of this START's cycle, or None before generation 1 exists."""
    reserved = mutation.record.get("reserved_ids") or {}
    prefix = f"review-run:{work_review.REVIEW_KIND}:"
    keys = [key for key in reserved if str(key).startswith(prefix)]
    if not keys:
        return None
    if len(keys) > 1:
        raise _reconcile(f"START mutation {mutation.id} reserved more than one Work Review Run ({sorted(keys)})")
    work_id = keys[0][len(prefix):]
    runs = _p4_reserved_runs(reserved, work_id)
    if not runs or (len(runs) == 1 and not _begun(mutation.store, runs[0])):
        return None
    return InFlight(STATE_P4, _p4_work_run(reserved, work_id, runs[-1]))


def _p4_envelope(store: ProjectStore, chain: Any) -> dict[str, Any]:
    first = chain.generations[0]
    return ReviewStore(store).read_task_input(str(first.accepted_tasks[0]["task_id"])).request_envelope


def _p4_task_policy(task_input: records.TaskInput) -> str:
    """The family policy a P4-capable TaskInput's request names (GAP-A); a request naming none reads as P4, as before."""
    return p4.policy_of_task_input(task_input) or p4.POLICY_ID


def _p4_policy(store: ProjectStore, chain: Any) -> str:
    """The family policy the Run's own generation-1 TaskInputs store (GAP-A): what its currency and history dispatch on."""
    return p4.run_policy(ReviewStore(store), chain)


def _p4_history(store: ProjectStore, chain: Any) -> str | None:
    """The durable history contract the Run stores: ``None`` for a P4-only Run (``not_required_by_contract``)."""
    return p4.history_contract_of_policy(_p4_policy(store, chain))


def _p4_require_shape(store: ProjectStore, run: WorkRun, chain: Any) -> None:
    review = ReviewStore(store)
    try:
        contracts = p4.run_contracts(review, chain)
    except ValidationError as exc:
        raise _reconcile(f"Work Review Run {run.review_run_id}'s task inputs do not read: {exc}", "review_chain_invalid") from exc
    if contracts != {work_review.P4_CONTRACT}:
        raise p4.reconcile(f"Work Review Run {run.review_run_id} binds {sorted(str(c) for c in contracts)}, not the Work "
                           "P4 contract this START runs under; it is neither upgraded nor downgraded",
                           p4.REASON_CONTRACT_MISMATCH)
    first = chain.generations[0]
    problems = p4.chain_problems(chain)
    if first.review_kind != work_review.REVIEW_KIND or first.target_identity != run.work_id \
            or first.operation_identity != work_review.operation_identity(run.work_id):
        problems.append("generation 1 is not a Work Review of this Work under its operation identity")
    if problems:
        raise p4.reconcile(f"Work Review Run {run.review_run_id}: " + "; ".join(problems), p4.REASON_CHAIN_INVALID)


def _p4_requirement(store: ProjectStore, git: HermeticGit, work_id: str) -> dict[str, Any]:
    """The Work's decided requirement, read from HEAD's committed Work body (G-1 item 6 / G-4)."""
    view = committed_view_at(store, git, _head(git)[1])
    work = view.works.get(work_id)
    if work is None:
        raise _reconcile(f"HEAD's committed view holds no Work {work_id}")
    return work_review.requirement_authority(work_id, work.body)


def _p4_decision_bindings(mutation: Mutation) -> dict[str, dict[str, Any]]:
    """This START's durable G-4 bindings, waiting Review Run ID -> Human-decision record (P4-R7)."""
    found = mutation.note(NOTE_P4_DECISIONS)
    if found is None:
        return {}
    if not isinstance(found, dict) or not all(
        isinstance(run_id, str) and isinstance(record, dict) for run_id, record in found.items()
    ):
        raise p4.reconcile(f"START mutation {mutation.id}'s Human-decision bindings are not a waiting-Run mapping",
                           p4.REASON_LINKAGE_INVALID)
    return dict(found)


def _p4_bind_decision(session: "_Session", waiting_run_id: str, chain: Any) -> p4.HumanDecision | None:
    """G-4 (P4-R7): the decision that exits ``waiting_run_id``'s HUMAN_WAIT, bound durably before any reservation.

    The binding is per waiting Run, never per mutation, because a pending START can wait more than once:
    the same decision for the same Run is idempotent; a different decision for a Run that is already bound is
    refused (``review_p4_human_decision_invalid``) and the binding stays as it was; a later waiting Run of the
    same pending START binds its own, later decision. A decision that already exits another Run's wait, or that
    the waiting Run's own request already carried (it was supplied before the wait existed), exits nothing and
    returns None. A decision identity reused with another disposition is refused.
    """
    decision = getattr(session.review, "human_decision", None)
    if decision is None:
        return None
    record = decision.to_record()
    bindings = _p4_decision_bindings(session.mutation)
    bound = bindings.get(waiting_run_id)
    if bound is not None:
        if bound != record:
            raise p4.stop(p4.CODE_HUMAN_DECISION_INVALID,
                          f"START mutation {session.mutation.id} already binds Human decision "
                          f"{bound.get('decision_id')!r} to the wait of Work Review Run {waiting_run_id}, and this "
                          f"invocation carries {decision.decision_id!r} for it; the binding is left unchanged")
        return decision
    for other, found in sorted(bindings.items()):
        if found.get("decision_id") != decision.decision_id:
            continue
        if found != record:
            raise p4.stop(p4.CODE_HUMAN_DECISION_INVALID,
                          f"Human decision {decision.decision_id!r} is bound to the wait of Work Review Run {other} "
                          "with another disposition; one decision identity is one decision")
        return None
    if _p4_envelope(session.store, chain).get("human_decision") == record:
        return None
    session.mutation.set_note(NOTE_P4_DECISIONS, {**bindings, waiting_run_id: record})
    return decision


def _p4_reserve(mutation: Mutation, run_id: str, work_id: str, bindings: list[p4.DiscoveryBinding],
                *, predecessor: str | None = None) -> WorkRun:
    task_ids = [mutation.reserve_id(gate.review_task_key(run_id, binding.task_slot), "review_task")
                for binding in bindings]
    receipt = mutation.reserve_id(gate.review_receipt_key(run_id, p4.SEAL_GENERATION), "review_receipt")
    return WorkRun(work_id, run_id, task_ids[0], receipt, predecessor_review_run_id=predecessor,
                   contract=work_review.P4_CONTRACT)


def _p4_bindings(session: "_Session") -> list[p4.DiscoveryBinding]:
    """The discovery actors of the Run: the required slots, then (P6, §30.11) the holdout slots, each by viewpoint."""
    return (sorted(session.review.discovery, key=lambda binding: binding.viewpoint)
            + sorted(getattr(session.review, "holdout_discovery", ()), key=lambda binding: binding.viewpoint))


def _p4_new_run_effective(session: "_Session", policy_id: str) -> dict[str, Any] | None:
    """R6-1: the Effective Policy a NEW Work Review Run of family ``policy_id`` freezes (None for P4 / P5)."""
    from .review import policy as review_policy

    return review_policy.new_run_effective_policy(
        ReviewStore(session.store), session.store.workline_root(), policy_id, session.review.discovery,
        getattr(session.review, "holdout_discovery", ()),
    )


@dataclass(frozen=True)
class _P4Frozen:
    candidate: dict[str, Any]
    snapshot: records.CandidateSnapshot
    context: dict[str, Any]
    task_inputs: list[records.TaskInput]
    evidence: dict[str, Any]
    write_snapshot: bool
    #: The Run's family policy (GAP-A) and, for P5, what its G1 writes besides its own records (§28.5, §28.14).
    policy: str = p4.POLICY_ID
    history: p4.HistoryWrites = field(default_factory=p4.HistoryWrites)
    #: P6 (R6-1): the Effective Policy a P6-capable Run froze; None for a P4 / P5 Run.
    effective: dict[str, Any] | None = None


def _p4_freeze_material(
    session: "_Session", run: WorkRun, git: HermeticGit, candidate: dict[str, Any], snapshot: records.CandidateSnapshot,
    resulting: str, pre_base: str, *, generation: int, succession: dict[str, Any] | None,
    set_aside: list[dict[str, Any]], declared: bool, write_snapshot: bool, human_decision: p4.HumanDecision | None,
    policy: str, history_writes: p4.HistoryWrites | None = None, effective: dict[str, Any] | None = None,
) -> _P4Frozen:
    """Context, isolated verification, discovery requests and Evidence of one P4 Run's Candidate (§27.8).

    ``policy`` is the Run's explicit family policy (GAP-A); a P5 Run's requests also bind ``history_writes``; a
    P6 Run's (R6-1) also bind the Effective Policy it froze (``effective``) and each discovery task's role.
    """
    from .review import policy as review_policy

    from .implementation import package_directory

    store = session.store
    activation = session.activation
    if activation is None:
        raise _reconcile("a review-v1 START session holds no activation proven at its entry")
    writes = history_writes or p4.HistoryWrites()
    inner = work_context.context_record(
        store.workline_root(), package_directory(store.workline_root()), activation.binding(),
        resulting_tree.root_tree_id(git, pre_base), resulting,
    )
    context = work_review.context_record_p4(inner, policy)
    width = len(candidate["declared_base"]["base_commit"])
    reconstruction = work_review.read_material(snapshot, work_review.candidate_hash(candidate), width)
    verified = work_verify.verify(store, git, reconstruction, resulting_tree_id=resulting)
    requirement = _p4_requirement(store, git, run.work_id)
    task_ids = [str(session.mutation.reserved(gate.review_task_key(run.review_run_id, binding.task_slot)))
                for binding in _p4_bindings(session)]
    task_inputs = []
    holdout = {binding.task_slot for binding in getattr(session.review, "holdout_discovery", ())}
    for task_id, binding in zip(task_ids, _p4_bindings(session)):
        role = None
        if effective is not None:
            role = review_policy.ROLE_HOLDOUT if binding.task_slot in holdout else review_policy.ROLE_REQUIRED
        envelope = p4.discovery_request(
            review_contract=work_review.P4_CONTRACT, review_kind=work_review.REVIEW_KIND, viewpoint=binding.viewpoint,
            candidate=candidate, context=context, requirement=requirement, candidate_generation=generation,
            succession=succession, set_aside_runs=set_aside, human_decision=human_decision,
            evidence_ids=[f"work-isolated-verification:{verified.resulting_tree}"], policy_id=policy,
            set_aside_summaries=writes.summary_bindings(), decision_evidence=writes.decision_bindings(),
            effective_policy=effective, discovery_role=role,
        )
        task_inputs.append(p4.task_input(
            task_id=task_id, task_slot=binding.task_slot, task_kind=p4.TASK_KIND_DISCOVERY,
            actor_identity=binding.identity, actor_version=binding.version, envelope=envelope,
            candidate_hash=snapshot.candidate_hash, candidate_material_digest=work_review.material_digest(snapshot),
            review_context_hash=serialize.digest(context), accepted_generation=p4.DISCOVERY_ACCEPT_GENERATION,
            policy_id=policy,
        ))
    evidence = _evidence(git, candidate, snapshot, task_inputs[0], inner, serialize.digest(context),
                         p4.run_effective_policy_hash(policy, effective), activation, verified, declared=declared)
    return _P4Frozen(candidate, snapshot, context, task_inputs, evidence, write_snapshot, policy, writes, effective)


def freeze_and_review_p4(session: "_Session", view: ProjectView, work: Entity, outcome: Any) -> Sealed:
    """F3 §5.1 steps 5a ... 12 exactly as v1, then the P4 Run of the frozen Candidate (§27.8)."""
    from .start import _result_message, completion_precheck

    store, mutation = session.store, session.mutation
    recovered = recovery_discovery(store, work.id, own_run_ids(mutation.record.get("reserved_ids") or {}))
    set_aside = [dict(item) for item in recovered.set_aside]
    # GAP-G: a first Run resumes no HUMAN_WAIT Run, so evidence here would be detached - refused before any effect
    p4.require_decision_evidence_cover(ReviewStore(store), set_aside, getattr(session.review, "decision_evidence", ()))
    # R6-1, before the entry commit and any reservation: a NEW first Run is P6-capable; it resolves its Effective
    # Policy (fail closed on an incompatible Profile) with its discovery actors held to required_slots / holdout
    policy = p4.new_run_policy()
    effective = _p4_new_run_effective(session, policy)
    result_paths = tuple(p.replace("\\", "/") for p in outcome.result_paths)
    deleted_paths = tuple(p.replace("\\", "/") for p in outcome.deleted_paths)
    git = hermetic_module.enter(store)
    branch, pre_base = _head(git)
    witnesses = ownership.bind_declarations(store, git, result_paths, deleted_paths, pre_base)
    ownership.assert_ownership(mutation, witnesses)
    completion_precheck(store, view, work, result_paths, deleted_paths)
    owned = sorted(set(result_paths) | set(deleted_paths))
    if owned:
        preexisting = gitops.record_preexisting_dirty(mutation, store.root)
        overlap = sorted(set(preexisting) & set(owned))
        if overlap:
            session._refuse_overlapping_result(work, outcome, overlap, overlap)
        attributes.require_pinned_path_evaluation(store, git, pre_base, owned)
    commit_stage(session, f"{work.id}:entry", f"chore(workline): enter {work.display}",
                 plan_class=workcommit.CLASS_ENTRY)
    branch_after, base_commit = _head(git)
    if branch_after != branch:
        raise _reconcile(f"HEAD left {branch} while the completion of {work.id} was being frozen")
    candidate, payloads = _p4_candidate_from_witnesses(
        session, git, witnesses, base_commit, branch, work.id, _result_message(outcome.message, work),
        result_paths, deleted_paths,
    )
    snapshot = work_review.snapshot_for(work_review.snapshot_material(candidate, payloads))
    resulting = resulting_tree.resulting_tree_id(
        store, git, base_commit, resulting_tree.entries_from_records(work_review.entries_of(candidate)), payloads
    )
    run = _p4_reserve(mutation, mutation.reserve_id(run_key(work.id), "review_run"), work.id, _p4_bindings(session))
    ownership.require_current(store, git, witnesses, pre_base)
    checkout.require_namespace_readable(store)
    # GAP-A item 7 / R6-1: a first Run of a START with no Run yet binds the current default (P6-capable), resolved
    # above before any effect
    writes = p4.HistoryWrites()
    if p4.history_contract_of_policy(policy) is not None:
        writes = p4.HistoryWrites(p4.set_aside_summaries(ReviewStore(store), set_aside))  # §28.5 set-aside summaries
    frozen = _p4_freeze_material(session, run, git, candidate, snapshot, resulting, pre_base, generation=1,
                                 succession=None, set_aside=set_aside, declared=bool(owned), write_snapshot=True,
                                 human_decision=getattr(session.review, "human_decision", None), policy=policy,
                                 history_writes=writes, effective=effective)
    _p4_accept(session, run, frozen)
    session._drop_refused_result(work.id)
    return _continue_p4(session, run)


def _p4_candidate_from_witnesses(
    session: "_Session", git: HermeticGit, witnesses: Any, base_commit: str, branch: str, work_id: str, message: str,
    result_paths: Any, deleted_paths: Any,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Step 10 exactly: the Candidate from the bound witnesses and ``base_commit``'s tree, no pathname read again."""
    width = len(base_commit)
    base = declared_base(session.store, git, base_commit, branch, work_id)
    held = workcommit._tree_entries(git, base_commit, [witness.path for witness in witnesses])
    entries: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    for witness in witnesses:
        old = held.get(witness.path)
        entries.append(work_review.candidate_entry(
            witness.path, None if old is None else (old.mode, old.oid), witness.kind, witness.git_mode,
            None if witness.kind == ownership.KIND_ABSENT else witness.identity, witness.material, width,
        ))
        if witness.material is not None:
            payloads[witness.path] = witness.material
    content = work_review.content_for(entries, message=message, base_commit=base_commit,
                                      declared_result=result_paths, declared_deleted=deleted_paths)
    activation = session.activation
    if activation is None:
        raise _reconcile("a review-v1 START session holds no activation proven at its entry")
    return work_review.candidate_record(content, base, activation.binding()), payloads


def _p4_accept(session: "_Session", run: WorkRun, frozen: _P4Frozen) -> None:
    """G1: the snapshot (when new), every discovery TaskInput and the open gate, in one generation mutation."""
    required = [(found.task_slot, found.task_id) for found in frozen.task_inputs]
    gate_one = records.GateGeneration(
        review_run_id=run.review_run_id, generation=1, previous_generation=None, previous_digest=None,
        review_kind=work_review.REVIEW_KIND, target_identity=run.work_id,
        operation_identity=work_review.operation_identity(run.work_id),
        candidate_hash=frozen.snapshot.candidate_hash, review_context_hash=serialize.digest(frozen.context),
        effective_policy_hash=p4.run_effective_policy_hash(frozen.policy, frozen.effective),
        evidence_digest=serialize.digest(frozen.evidence),
        coverage_digest=serialize.digest(p4.coverage_record(required, [])),
        raw_report_set_digest=serialize.digest(p4.report_set_record([])),
        adjudication_digest=serialize.digest(p4.pending_adjudication_record()),
        obligation_digest=serialize.digest(p4.obligations_record(None)),
        accepted_tasks=tuple(p4.accepted_descriptor(found) for found in frozen.task_inputs), settled_tasks=(),
        status=records.GATE_STATUS_OPEN, receipt_id=None, authorized_operation_stage=None,
    )
    extra: list[tuple[str, dict[str, Any]]] = []
    if frozen.write_snapshot and not ReviewStore(session.store).candidate_snapshot_exists(frozen.snapshot.candidate_hash):
        extra.append((review_paths.candidate_snapshot_rel(frozen.snapshot.candidate_hash), frozen.snapshot.to_record()))
    extra += [(review_paths.task_input_rel(found.task_id), found.to_record()) for found in frozen.task_inputs]
    # P5 (§28.5, §28.14): the set-aside summaries and Human Decision Evidence the requests bind, in this same G1 -
    # committed before any external reviewer launch
    extra += frozen.history.extra()
    _start_generation(session, run, 1, gate_one, extra, frozen.candidate["declared_base"],
                      transition=p4.TRANSITION_ACCEPT)


def _p4_base(store: ProjectStore, chain: Any) -> dict[str, Any]:
    snapshot = ReviewStore(store).read_candidate_snapshot(chain.generations[0].candidate_hash)
    return ((snapshot.material or {}).get("candidate") or {})["declared_base"]


def p4_run_material(store: ProjectStore, run: WorkRun, chain: Any) -> RunMaterial:
    """The first discovery task, the exact Candidate with its payloads, and the bound Work Context v2."""
    review = ReviewStore(store)
    first = chain.generations[0]
    descriptor = first.accepted_tasks[0]
    problems = review.provenance_problems(descriptor, 1)
    if problems:
        raise _reconcile("the accepted task's provenance: " + "; ".join(message for _, message in problems),
                         "review_task_invalid")
    task_input = review.read_task_input(str(descriptor["task_id"]))
    snapshot = review.read_candidate_snapshot(first.candidate_hash)
    material = snapshot.material or {}
    width = len(str((material.get("candidate") or {}).get("declared_base", {}).get("base_commit", "")))
    if width not in (40, 64):
        raise _reconcile("the stored Candidate names no declared base of a known object width")
    reconstruction = work_review.read_material(snapshot, first.candidate_hash, width)
    problems_p4 = work_review.task_input_problems_p4(task_input, material, first.candidate_hash, first.review_context_hash)
    if problems_p4:
        raise _reconcile("the accepted task's request: " + "; ".join(problems_p4), "review_task_invalid")
    return RunMaterial(task_input, reconstruction, work_review.inner_context(task_input.request_envelope["context"]))


def _continue_p4(session: "_Session", run: WorkRun) -> Sealed:
    """The P4 owner loop over the validated chain of the current Run of this START's cycle (§27.1)."""
    store, mutation = session.store, session.mutation
    review = ReviewStore(store)
    while True:
        runs = _p4_reserved_runs(mutation.record.get("reserved_ids") or {}, run.work_id)
        if runs and runs[-1] != run.review_run_id:
            run = _p4_work_run(mutation.record.get("reserved_ids") or {}, run.work_id, runs[-1])
        resolve_pending_generation(session, run)
        chain = _chain(store, run)
        if chain is None:
            if len(runs) < 2:
                raise _reconcile(f"Work Review Run {run.review_run_id} has no chain to continue", "review_chain_invalid")
            _p4_begin_successor(session, run, runs[-2])
            continue
        _p4_require_shape(store, run, chain)
        latest = chain.latest.generation
        shape = p4.shape_of(chain)
        if latest == 1:
            _p4_launch_discovery(session, run, chain)
        elif latest == 2:
            if any(task["status"] != records.TASK_SETTLED_OK for task in chain.latest.settled_tasks):
                _refuse_seal(mutation, run, "not_authorized", None)
                raise _reconcile(f"Work Review Run {run.review_run_id}'s discovery was declined; START does not "
                                 f"terminalize an unauthorized completion of {run.work_id}")
            _p4_accept_adjudication(session, run, chain)
        elif latest == 3:
            _p4_adjudicate(session, run, chain)
        elif latest == 4:
            outcome = review.read_adjudication(run.review_run_id).outcome
            # §28.18: a P5 G4 is history-complete only with every Finding summary its adjudication requires
            history.require_history_ready(review, run.review_run_id, history.BOUNDARY_FINDINGS,
                                          history_contract=_p4_history(store, chain))
            if outcome == p4.HUMAN_WAIT:
                _p4_human_wait(session, run, chain)
            elif outcome == p4.REPAIR_REQUIRED:
                _p4_accept_repair(session, run, chain)
            else:
                material = p4_run_material(store, run, chain)
                require_capability(session, run, material)
                _p4_seal(session, run, chain)
        elif latest == 5 and shape == p4.SHAPE_SEAL:
            run.receipt_id = str(chain.latest.receipt_id)
            return Sealed(run, p4_run_material(store, run, chain), chain)
        elif latest == 5:
            _p4_repair(session, run, chain)
        elif shape == p4.SHAPE_SEAL:
            raise p4.stop(p4.CODE_RECEIPT_INVALIDATED,
                          f"Work Review Run {run.review_run_id}'s Receipt is invalidated at generation 6; a P4 Run is "
                          "never continued as a current authorization and never enters Class A: reconcile under the "
                          "START owner")
        else:
            # §28.18 repaired_g6: a P5 repair's Repair summary and repaired Run summary are canonical first
            history.require_history_ready(review, run.review_run_id, history.BOUNDARY_REPAIRED,
                                          history_contract=_p4_history(store, chain))
            _p4_adopt(session, run, chain)
            successor = mutation.reserve_id(gate.review_successor_run_key(run.review_run_id), "review_run")
            _p4_reserve(mutation, successor, run.work_id, _p4_bindings(session), predecessor=run.review_run_id)


def _p4_launch_discovery(session: "_Session", run: WorkRun, chain: Any) -> None:
    """G1 -> G2: every accepted discovery task launched to its bound actor, then the raw reports and G2 (§27.9)."""
    store = session.store
    review = ReviewStore(store)
    first = chain.latest
    tasks = list(first.accepted_tasks)
    envelope = _p4_envelope(store, chain)
    gate.require_persisted(store, [review_paths.candidate_snapshot_rel(first.candidate_hash),
                                   review_paths.gate_rel(run.review_run_id, 1)]
                           + [review_paths.task_input_rel(str(task["task_id"])) for task in tasks]
                           + p4.first_generation_history_paths(envelope))  # P5: what G1 bound, before any launch
    # §28.18 successor_launch: no external launch under a Human decision before its evidence is canonical
    p4.require_first_generation_history(review, run.review_run_id, envelope)
    material = p4_run_material(store, run, chain)
    for task in tasks:
        problems = [message for _, message in review.provenance_problems(task, 1)]
        problems += work_review.task_input_problems_p4(review.read_task_input(str(task["task_id"])),
                                                       review.read_candidate_snapshot(first.candidate_hash).material or {},
                                                       first.candidate_hash, first.review_context_hash)
        if problems:
            raise _reconcile("the accepted discovery task: " + "; ".join(problems), "review_task_invalid")
    bindings = {binding.task_slot: binding for binding in _p4_bindings(session)}
    settled: list[dict[str, Any]] = []
    reports: dict[str, dict[str, Any]] = {}
    for task in tasks:
        task_id = str(task["task_id"])
        binding = bindings.get(str(task["task_slot"]))
        if binding is None or (binding.identity, binding.version) != (task["reviewer_identity"], task["reviewer_version"]):
            raise StopError(
                f"discovery task {task_id} ({task['task_slot']}) was accepted for {task['reviewer_identity']} "
                f"{task['reviewer_version']}, and this invocation binds no such actor to that viewpoint; nothing is launched",
                code="review_reviewer_mismatch",
            )
        task_input = review.read_task_input(task_id)
        launched = p4.P4DiscoveryTask(
            task_id=task_id, task_slot=task_input.task_slot, task_kind=task_input.task_kind,
            review_kind=work_review.REVIEW_KIND, viewpoint=binding.viewpoint,
            request_envelope=serialize.canonical_data(task_input.request_envelope),
            request_digest=task_input.request_digest, candidate_hash=task_input.candidate_hash,
            review_context_hash=task_input.review_context_hash, effective_policy_hash=task_input.effective_policy_hash,
        )
        try:
            returned = binding.actor(launched)
        except Exception as exc:
            raise StopError(f"the discovery actor raised for task {task_id}: {exc}; nothing is settled",
                            code="review_reviewer_failed") from exc
        report = p4.report_record(returned, task, review_kind=work_review.REVIEW_KIND,
                                  review_contract=work_review.P4_CONTRACT)
        result_digest = serialize.digest(report)
        gate.validate_settlement(store, run.review_run_id, task_id, result_digest, str(returned.reviewer_identity))
        settled.append({"task_id": task_id, "status": p4.settled_status(report), "result_digest": result_digest,
                        "settled_generation": 2})
        reports[task_id] = report
    required = [(str(task["task_slot"]), str(task["task_id"])) for task in tasks]
    gate_two = replace(
        first, generation=2, previous_generation=1, previous_digest=chain.latest_digest,
        coverage_digest=serialize.digest(p4.coverage_record(required, settled, reports)),
        raw_report_set_digest=serialize.digest(p4.report_set_record(settled)), settled_tasks=tuple(settled),
    )
    extra = [(review_paths.report_rel(task["result_digest"]), reports[task["task_id"]]) for task in settled]
    if p4.is_history_policy(p4.policy_of_envelope(envelope)):
        # GAP-E: a G2 that settles a discovery task failed makes discovery non-authorizing and final for the Run;
        # its immutable not_authorized Run summary is written in this same G2 settlement
        extra += p4.not_authorized_history(gate_two, int(envelope["candidate_generation"]))
    _start_generation(session, run, 2, gate_two, extra, material.base, transition=p4.TRANSITION_SETTLE)


def _p4_reports(review: ReviewStore, chain: Any) -> list[tuple[str, str, dict[str, Any]]]:
    discovery = {str(task["task_id"]) for task in p4.discovery_tasks(chain)}
    return [
        (str(task["task_id"]), str(task["result_digest"]),
         serialize.canonical_data(review.read_report(str(task["result_digest"])).to_record()))
        for task in chain.generation(2).settled_tasks if str(task["task_id"]) in discovery
    ]


def _p4_prior(store: ProjectStore, chain: Any) -> p4.PriorCycle | None:
    """The current-cycle predecessor of a repaired Candidate's Run, from explicit linkage only (§12.11)."""
    review = ReviewStore(store)
    succession = _p4_envelope(store, chain).get("succession")
    if succession is None:
        return None
    try:
        predecessor_id = str(succession["predecessor_review_run_id"])
        predecessor = review.gate_chain(predecessor_id)
        adjudication = review.read_adjudication(predecessor_id)
        batch = review.read_repair_batch(str(succession["repair_batch_id"]))
        result = review.read_repair_result(batch.repair_batch_id)
        prior = p4.PriorCycle(predecessor_id, adjudication, review.adjudication_digest(predecessor_id), batch, result,
                              review.repair_result_digest(batch.repair_batch_id))
    except (ValidationError, KeyError, TypeError) as exc:
        raise p4.reconcile(f"the predecessor of Work Review Run {chain.review_run_id} does not read: {exc}",
                           p4.REASON_LINKAGE_INVALID) from exc
    if predecessor is None:
        raise p4.reconcile(f"the predecessor {predecessor_id} has no chain", p4.REASON_LINKAGE_INVALID)
    earlier = _p4_prior(store, predecessor)
    history = (() if earlier is None else earlier.bc_history) + (p4.bc_surfaces(adjudication),)
    return replace(prior, bc_history=history)


def _p4_accept_adjudication(session: "_Session", run: WorkRun, chain: Any) -> None:
    """G3: one adjudication TaskInput built from canonical material only, accepted before any launch (§27.10)."""
    store, mutation = session.store, session.mutation
    review = ReviewStore(store)
    second = chain.latest
    envelope = _p4_envelope(store, chain)
    reports = _p4_reports(review, chain)
    prior = _p4_prior(store, chain)
    policy = _p4_policy(store, chain)
    references = [] if p4.history_contract_of_policy(policy) is None else p4.prior_history_references(
        review, second.review_kind, second.target_identity, run.review_run_id)  # GAP-C, P5 only
    request = p4.adjudication_request(
        review_contract=work_review.P4_CONTRACT, review_kind=work_review.REVIEW_KIND, review_run_id=run.review_run_id,
        candidate_hash=second.candidate_hash, candidate_generation=int(envelope["candidate_generation"]),
        review_context_hash=second.review_context_hash, requirement=envelope["requirement"],
        reports=[{"task_id": t, "result_digest": d} for t, d, _ in reports],
        prior=p4.NO_PRIOR if prior is None else prior.prior_record(),
        evidence_ids=[eid for _, _, report in reports for eid in report["coverage"]["evidence_ids"]],
        policy_id=policy, prior_history=references, effective_policy=p4.effective_policy_of_envelope(envelope),
    )
    task_id = mutation.reserve_id(gate.review_task_key(run.review_run_id, p4.SLOT_ADJUDICATOR), "review_task")
    adjudicator = session.review.adjudicator
    task_input = p4.task_input(
        task_id=task_id, task_slot=p4.SLOT_ADJUDICATOR, task_kind=p4.TASK_KIND_ADJUDICATION,
        actor_identity=adjudicator.identity, actor_version=adjudicator.version, envelope=request,
        candidate_hash=second.candidate_hash,
        candidate_material_digest=review.candidate_material_digest(second.candidate_hash),
        review_context_hash=second.review_context_hash, accepted_generation=p4.ADJUDICATION_ACCEPT_GENERATION,
        policy_id=policy,
    )
    gate_three = replace(second, generation=3, previous_generation=2, previous_digest=chain.latest_digest,
                         accepted_tasks=second.accepted_tasks + (p4.accepted_descriptor(task_input),))
    _start_generation(session, run, 3, gate_three, [(review_paths.task_input_rel(task_id), task_input.to_record())],
                      _p4_base(store, chain), transition=p4.TRANSITION_ACCEPT)


def _p4_adjudicate(session: "_Session", run: WorkRun, chain: Any) -> None:
    """G3 -> G4: the adjudicator, launched only to its bound identity; its return validated and normalized (§27.11)."""
    store, mutation = session.store, session.mutation
    review = ReviewStore(store)
    third = chain.latest
    descriptor = p4.adjudication_task(chain)
    assert descriptor is not None
    task_id = str(descriptor["task_id"])
    reports = _p4_reports(review, chain)
    gate.require_persisted(store, [review_paths.task_input_rel(task_id), review_paths.gate_rel(run.review_run_id, 3)]
                           + [review_paths.report_rel(digest) for _, digest, _ in reports])
    problems = review.provenance_problems(descriptor, 3)
    if problems:
        raise _reconcile("the accepted adjudication task: " + "; ".join(m for _, m in problems), "review_task_invalid")
    binding = session.review.adjudicator
    if (binding.identity, binding.version) != (descriptor["reviewer_identity"], descriptor["reviewer_version"]):
        raise StopError(
            f"adjudication task {task_id} was accepted for {descriptor['reviewer_identity']} "
            f"{descriptor['reviewer_version']}, and this invocation binds {binding.identity} {binding.version}; the "
            "adjudicator is not launched",
            code="review_reviewer_mismatch",
        )
    task_input = review.read_task_input(task_id)
    prior = _p4_prior(store, chain)
    snapshot = review.read_candidate_snapshot(third.candidate_hash)
    policy = _p4_policy(store, chain)
    references = list(task_input.request_envelope.get("prior_history") or [])
    launched = p4.P4AdjudicationTask(
        task_id=task_id, task_slot=task_input.task_slot, task_kind=task_input.task_kind,
        review_kind=work_review.REVIEW_KIND, request_envelope=serialize.canonical_data(task_input.request_envelope),
        request_digest=task_input.request_digest, candidate_hash=third.candidate_hash,
        review_context_hash=third.review_context_hash, effective_policy_hash=third.effective_policy_hash,
        candidate=(snapshot.material or {}).get("candidate") or {}, reports=tuple(r for _, _, r in reports),
        prior_findings=() if prior is None else tuple(prior.adjudication.findings),
        prior_repair_batch=None if prior is None else prior.repair_batch.to_record(),
        prior_repair_result=None if prior is None else prior.repair_result.to_record(),
        prior_history=p4.prior_history_records(review, references),
    )
    try:
        returned = binding.actor(launched)
    except Exception as exc:
        raise p4.stop(p4.CODE_ADJUDICATOR_FAILED,
                      f"the adjudicator raised for task {task_id}: {exc}; nothing is settled") from exc
    normalized = p4.normalize_adjudication(returned, descriptor, reports, prior)
    finding_ids = [mutation.reserve_id(gate.review_finding_key(run.review_run_id, ordinal), "review_finding")
                   for ordinal in range(1, len(normalized.drafts) + 1)]
    adjudication = p4.adjudication(
        normalized, finding_ids, review_run_id=run.review_run_id, gate_record=third,
        candidate_generation=int(_p4_envelope(store, chain)["candidate_generation"]),
        review_contract=work_review.P4_CONTRACT, descriptor=descriptor, reports=reports, prior=prior,
        policy_id=policy,
    )
    # GAP-C: structured cross-run relation claims, validated before anything is reserved for them
    drafts = p4.relation_drafts(returned, adjudication, references, policy_id=policy)
    relation_ids = [mutation.reserve_id(history.review_relation_key(run.review_run_id, ordinal), "review_relation")
                    for ordinal in range(1, len(drafts) + 1)]
    record = adjudication.to_record()
    digest = serialize.digest(record)
    gate.validate_settlement(store, run.review_run_id, task_id, digest, str(returned.adjudicator_identity))
    settled = {"task_id": task_id, "status": records.TASK_SETTLED_OK, "result_digest": digest, "settled_generation": 4}
    gate_four = replace(third, generation=4, previous_generation=3, previous_digest=chain.latest_digest,
                        adjudication_digest=digest, obligation_digest=serialize.digest(p4.obligations_record(adjudication)),
                        settled_tasks=third.settled_tasks + (settled,))
    extra = [(review_paths.adjudication_rel(run.review_run_id), record)]
    if p4.history_contract_of_policy(policy) is not None:
        # §28.8 / §28.12 / §28.5: the Finding summaries, the accepted relations and a HUMAN_WAIT Run summary, in
        # this same G4 that persists the adjudication
        extra += p4.g4_history(adjudication, gate_four, drafts, relation_ids, references).extra()
    _start_generation(session, run, 4, gate_four, extra, _p4_base(store, chain), transition=p4.TRANSITION_SETTLE)


def _p4_seal(session: "_Session", run: WorkRun, chain: Any) -> None:
    """G5 seal: the Receipt at generation 5 (§27.12), reached only on ``capable`` and the convergence predicate."""
    unmet = p4.convergence_from_records(ReviewStore(session.store), run.review_run_id, chain,
                                        _p4_envelope(session.store, chain), evidence_current=True)
    if unmet:
        raise p4.reconcile(f"Work Review Run {run.review_run_id} is not converged: " + "; ".join(unmet),
                           p4.REASON_CHAIN_INVALID)
    fourth = chain.latest
    receipt_id = session.mutation.reserve_id(gate.review_receipt_key(run.review_run_id, p4.SEAL_GENERATION),
                                             "review_receipt")
    run.receipt_id = receipt_id
    gate_five = replace(fourth, generation=5, previous_generation=4, previous_digest=chain.latest_digest,
                        status=records.GATE_STATUS_SEALED, receipt_id=receipt_id,
                        authorized_operation_stage=work_review.AUTHORIZED_OPERATION_STAGE)
    receipt = records.Receipt(
        receipt_id=receipt_id, review_run_id=run.review_run_id, review_generation=p4.SEAL_GENERATION,
        review_kind=fourth.review_kind, target_identity=fourth.target_identity,
        operation_identity=fourth.operation_identity, authorized_candidate_hash=fourth.candidate_hash,
        review_context_hash=fourth.review_context_hash, effective_policy_hash=fourth.effective_policy_hash,
        coverage_hash=fourth.coverage_digest, adjudication_hash=fourth.adjudication_digest,
        obligation_digest=fourth.obligation_digest, unresolved_obligations=0,
        authorized_operation_stage=work_review.AUTHORIZED_OPERATION_STAGE,
    )
    if session.mutation.note(NOTE_SEAL_REFUSAL) is not None:
        session.mutation.set_note(NOTE_SEAL_REFUSAL, None)
    _start_generation(session, run, 5, gate_five, [(review_paths.receipt_rel(receipt_id), receipt.to_record())],
                      _p4_base(session.store, chain), receipt_id=receipt_id, transition=p4.TRANSITION_SEAL)


def p4_invalidate(session: "_Session", run: WorkRun, chain: Any) -> None:
    """G-3: a stale P4 G5 Receipt is superseded by the P4 G6 invalidation, atomically; never F4 Class A."""
    fifth = chain.latest
    receipt_id = str(fifth.receipt_id)
    gate_six = replace(
        fifth, generation=6, previous_generation=5, previous_digest=chain.latest_digest,
        evidence_digest=serialize.digest(p4.invalidation_evidence_record(receipt_id, p4.INVALIDATION_STALE_RECEIPT)),
        status=records.GATE_STATUS_OPEN, receipt_id=None, authorized_operation_stage=None,
    )
    supersession = records.Supersession(receipt_id, run.review_run_id, 6, p4.INVALIDATION_STALE_RECEIPT)
    extra = [(review_paths.supersession_rel(receipt_id), supersession.to_record())]
    if _p4_history(session.store, chain) is not None:
        # §28.5: the invalidated Run summary, in the same G6 that persists the invalidation and Supersession
        extra += p4.invalidated_history(ReviewStore(session.store), chain, gate_six, receipt_id)
    _start_generation(session, run, 6, gate_six, extra, _p4_base(session.store, chain), receipt_id=receipt_id,
                      transition=p4.TRANSITION_INVALIDATE)


def _p4_decision_exits(session: "_Session", waiting_run_id: str, chain: Any) -> bool:
    """Whether :func:`_p4_bind_decision` would let the invocation's decision exit this wait - read only, nothing bound."""
    decision = getattr(session.review, "human_decision", None)
    if decision is None:
        return False
    record = decision.to_record()
    bindings = _p4_decision_bindings(session.mutation)
    if waiting_run_id in bindings:
        return bindings[waiting_run_id] == record
    if any(found.get("decision_id") == decision.decision_id for found in bindings.values()):
        return False
    return _p4_envelope(session.store, chain).get("human_decision") != record


def _p4_require_evidence(session: "_Session", waiting_run_id: str, chain: Any) -> None:
    """GAP-G (Work), before ANY binding, reservation or other effect: the evidence of a P5 wait this decision exits.

    ``affected_review_run_id`` must be exactly the P4-R7 waiting Run; a P5 wait resumed without its evidence is
    ``review_p5_history_missing``; evidence for any other Run is detached and refused. A P4-only wait resumes as
    it always did, with the decision alone.
    """
    evidence = getattr(session.review, "decision_evidence", ())
    exits = _p4_decision_exits(session, waiting_run_id, chain)
    resumed = [{"review_run_id": waiting_run_id, "reason": p4.SET_ASIDE_HUMAN_DECISION}] if exits else []
    review = ReviewStore(session.store)
    p4.require_decision_evidence_cover(review, resumed, evidence)
    if exits and _p4_history(session.store, chain) is not None:
        work_id = chain.generations[0].target_identity
        requirement = _p4_requirement(session.store, hermetic_module.enter(session.store), work_id)
        for item in evidence:
            p4.prove_decision_evidence(review, item, review_kind=work_review.REVIEW_KIND, target_identity=work_id,
                                       current_requirement=requirement)


def _p4_human_wait(session: "_Session", run: WorkRun, chain: Any) -> None:
    """G-4: HUMAN_WAIT stays at G4 and the START stays pending; a Human decision sets the Run aside for a new Run.

    A P5 wait is history-complete only with its Run summary (§28.18), and is resumed only with its Human Decision
    Evidence input, proven before the decision is bound or anything reserved (GAP-G).
    """
    history.require_history_ready(ReviewStore(session.store), run.review_run_id, history.BOUNDARY_HUMAN_WAIT,
                                  history_contract=_p4_history(session.store, chain))
    _p4_require_evidence(session, run.review_run_id, chain)
    if _p4_bind_decision(session, run.review_run_id, chain) is None:
        raise p4.stop(p4.CODE_HUMAN_WAIT,
                      f"Work Review Run {run.review_run_id} waits on a Human requirement decision at generation 4; "
                      "no repair guesses it, and this START stays pending until an invocation carries the decision")
    # bound durably above, before the successor's reservation (P4-R7 invariant 4)
    successor = session.mutation.reserve_id(gate.review_successor_run_key(run.review_run_id), "review_run")
    _p4_reserve(session.mutation, successor, run.work_id, _p4_bindings(session), predecessor=run.review_run_id)


def _p4_accept_repair(session: "_Session", run: WorkRun, chain: Any) -> None:
    """G5 repair branch: the one Repair Batch and its repair TaskInput, accepted together, no Receipt (§27.15)."""
    store, mutation = session.store, session.mutation
    review = ReviewStore(store)
    fourth = chain.latest
    adjudication = review.read_adjudication(run.review_run_id)
    candidate = (review.read_candidate_snapshot(fourth.candidate_hash).material or {}).get("candidate") or {}
    batch_id = mutation.reserve_id(gate.review_repair_batch_key(run.review_run_id), "review_repair_batch")
    batch = p4.repair_batch(adjudication, review.adjudication_digest(run.review_run_id), repair_batch_id=batch_id,
                            allowed_result_surface=work_review.allowed_result_surface(candidate) or ["(no result path)"])
    envelope = _p4_envelope(store, chain)
    policy = _p4_policy(store, chain)
    request = p4.repair_request(
        review_contract=work_review.P4_CONTRACT, review_kind=work_review.REVIEW_KIND, review_run_id=run.review_run_id,
        candidate_hash=fourth.candidate_hash, candidate_generation=int(envelope["candidate_generation"]),
        requirement=envelope["requirement"], repair_batch_id=batch_id, repair_batch_digest=serialize.digest(batch.to_record()),
        allowed_result_surface=batch.allowed_result_surface, strategy=batch.strategy, evidence_constraints=(),
        policy_id=policy, effective_policy=p4.effective_policy_of_envelope(envelope),
    )
    task_id = mutation.reserve_id(gate.review_task_key(run.review_run_id, p4.SLOT_REPAIR), "review_task")
    repair = session.review.repair
    task_input = p4.task_input(
        task_id=task_id, task_slot=p4.SLOT_REPAIR, task_kind=p4.TASK_KIND_REPAIR, actor_identity=repair.identity,
        actor_version=repair.version, envelope=request, candidate_hash=fourth.candidate_hash,
        candidate_material_digest=review.candidate_material_digest(fourth.candidate_hash),
        review_context_hash=fourth.review_context_hash, accepted_generation=p4.REPAIR_ACCEPT_GENERATION,
        policy_id=policy,
    )
    gate_five = replace(fourth, generation=5, previous_generation=4, previous_digest=chain.latest_digest,
                        accepted_tasks=fourth.accepted_tasks + (p4.accepted_descriptor(task_input),))
    _start_generation(session, run, 5, gate_five, [
        (review_paths.repair_batch_rel(batch_id), batch.to_record()),
        (review_paths.task_input_rel(task_id), task_input.to_record()),
    ], _p4_base(store, chain), transition=p4.TRANSITION_ACCEPT)


def _p4_repair(session: "_Session", run: WorkRun, chain: Any) -> None:
    """G5 -> G6: the repair actor's proposal turned into a complete Candidate N+1, never written to the tree (G-5)."""
    store = session.store
    review = ReviewStore(store)
    fifth = chain.latest
    descriptor = p4.repair_task(chain)
    assert descriptor is not None
    task_id = str(descriptor["task_id"])
    task_input = review.read_task_input(task_id)
    batch_id = str(task_input.request_envelope.get("repair_batch_id"))
    gate.require_persisted(store, [review_paths.task_input_rel(task_id), review_paths.gate_rel(run.review_run_id, 5),
                                   review_paths.repair_batch_rel(batch_id)])
    problems = review.provenance_problems(descriptor, 5)
    if problems:
        raise _reconcile("the accepted repair task: " + "; ".join(m for _, m in problems), "review_task_invalid")
    batch = review.read_repair_batch(batch_id)
    if review.repair_batch_digest(batch_id) != task_input.request_envelope.get("repair_batch_digest") \
            or batch.source_review_run_id != run.review_run_id:
        raise p4.reconcile(f"the repair task of {run.review_run_id} does not bind its Repair Batch", p4.REASON_LINKAGE_INVALID)
    binding = session.review.repair
    if (binding.identity, binding.version) != (descriptor["reviewer_identity"], descriptor["reviewer_version"]):
        raise StopError(
            f"repair task {task_id} was accepted for {descriptor['reviewer_identity']} {descriptor['reviewer_version']}, "
            f"and this invocation binds {binding.identity} {binding.version}; the repair actor is not launched",
            code="review_reviewer_mismatch",
        )
    material = p4_run_material(store, run, chain)
    adjudication = review.read_adjudication(run.review_run_id)
    launched = p4.P4RepairTask(
        task_id=task_id, task_slot=task_input.task_slot, task_kind=task_input.task_kind,
        review_kind=work_review.REVIEW_KIND, request_envelope=serialize.canonical_data(task_input.request_envelope),
        request_digest=task_input.request_digest, candidate_hash=fifth.candidate_hash,
        source_candidate={"candidate": material.candidate, "payloads": dict(material.reconstruction.payloads)},
        repair_batch=batch.to_record(),
        findings=tuple(adjudication.finding(finding_id) for finding_id in batch.finding_ids),
    )
    try:
        returned = binding.actor(launched)
    except Exception as exc:
        raise p4.stop(p4.CODE_REPAIR_INVALID, f"the repair actor raised for task {task_id}: {exc}; nothing is settled") from exc
    refused = p4.repair_return_problems(returned, descriptor)
    if refused:
        code, message = refused[0]
        if code == "review_reviewer_mismatch":
            raise StopError(f"{message}; nothing is settled", code="review_reviewer_mismatch")
        raise p4.stop(code, f"{message}; nothing is settled")
    width = len(material.base["base_commit"])
    try:
        candidate, payloads = work_review.repaired_candidate(material.reconstruction, returned.proposal, width)
    except (ValueError, StopError, ValidationError) as exc:
        raise p4.stop(p4.CODE_REPAIR_INVALID, f"the repair proposal is not a complete Work Candidate: {exc}; nothing "
                      "is settled") from exc
    snapshot = work_review.snapshot_for(work_review.snapshot_material(candidate, payloads))
    git = hermetic_module.enter(store)
    resulting = resulting_tree.resulting_tree_id(
        store, git, material.base["base_commit"], resulting_tree.entries_from_records(work_review.entries_of(candidate)),
        payloads,
    )
    verified = work_verify.verify(store, git, work_review.read_material(snapshot, snapshot.candidate_hash, width),
                                  resulting_tree_id=resulting)
    envelope = _p4_envelope(store, chain)
    result = p4.repair_result(
        batch=batch, source_candidate_generation=int(envelope["candidate_generation"]),
        result_candidate_hash=snapshot.candidate_hash, result_candidate_material_digest=work_review.material_digest(snapshot),
        repair_task_id=task_id, returned=returned,
        evidence=(p4.evidence_reuse("work-isolated-verification", None, None, prior_identities=(),
                                    new_identities=(verified.resulting_tree,), assumption_invalidated=True),),
        kind_checks=(p4.P4Verification(work_review.P4_KIND_CHECK, "pass"),),
        effective_policy=p4.effective_policy_of_envelope(envelope),
    )
    record = result.to_record()
    digest = serialize.digest(record)
    gate.validate_settlement(store, run.review_run_id, task_id, digest, str(returned.repair_identity))
    settled = {"task_id": task_id, "status": records.TASK_SETTLED_OK, "result_digest": digest, "settled_generation": 6}
    gate_six = replace(fifth, generation=6, previous_generation=5, previous_digest=chain.latest_digest,
                       settled_tasks=fifth.settled_tasks + (settled,))
    extra = [
        (review_paths.repair_result_rel(batch_id), record),
        (review_paths.candidate_snapshot_rel(snapshot.candidate_hash), snapshot.to_record()),
    ]
    if _p4_history(store, chain) is not None:
        # §28.9: the Repair summary and the repaired Run summary, in the same G6 as the Repair Result and N+1
        extra += p4.g6_history(adjudication, batch, result, gate_six,
                               source_candidate_material_digest=review.candidate_material_digest(fifth.candidate_hash))
    _start_generation(session, run, 6, gate_six, extra, material.base, transition=p4.TRANSITION_SETTLE)


def _p4_settled_result(store: ProjectStore, chain: Any) -> tuple[records.P4RepairBatch, records.P4RepairResult, str]:
    review = ReviewStore(store)
    repair = p4.repair_task(chain)
    batch_id = str(review.read_task_input(str(repair["task_id"])).request_envelope.get("repair_batch_id"))
    return review.read_repair_batch(batch_id), review.read_repair_result(batch_id), review.repair_result_digest(batch_id)


def _p4_adopt(session: "_Session", run: WorkRun, chain: Any) -> None:
    """G-5: START alone adopts the exact Candidate N+1 onto the declared result paths, before any successor Review.

    1 the exact persisted N+1 material is read; 2 only the source's declared
    result paths may change; 3 START writes the bytes; 4 the ownership,
    containment, reserved-path and pre-existing-dirty checks run again through
    the existing machinery; 5 fresh witnesses are bound; 6 they hold the
    adopted bytes; 7 the Candidate is rebuilt from them exactly as step 10
    builds one; 8 its hash must be the persisted N+1 hash; 9 the isolated
    verification runs. Any difference fails closed. A replay finds the bytes
    already adopted and only re-proves them.
    """
    import os

    store, mutation = session.store, session.mutation
    review = ReviewStore(store)
    batch, result, _ = _p4_settled_result(store, chain)
    source = p4_run_material(store, run, chain)
    snapshot = review.read_candidate_snapshot(result.result_candidate_hash)
    width = len(source.base["base_commit"])
    target = work_review.read_material(snapshot, result.result_candidate_hash, width)
    base = target.candidate["declared_base"]
    if base != source.base or target.candidate.get("activation") != source.candidate.get("activation"):
        raise p4.reconcile("Candidate N+1 does not keep the source's declared base and activation",
                           p4.REASON_ADOPTION_MISMATCH)
    result_paths, deleted_paths = work_review.declared_paths(source.candidate)
    if work_review.declared_paths(target.candidate) != (result_paths, deleted_paths):
        raise p4.reconcile("Candidate N+1 changes the declared paths", p4.REASON_ADOPTION_MISMATCH)
    allowed = set(batch.allowed_result_surface)
    changed = {path: data for path, data in target.payloads.items() if source.reconstruction.payloads.get(path) != data}
    if not set(changed) <= allowed:
        raise p4.reconcile("Candidate N+1 changes a path outside the Repair Batch's allowed result surface",
                           p4.REASON_ADOPTION_MISMATCH)
    git = hermetic_module.enter(store)
    pre_base = _pre_s_c0_base(work_record(mutation.record), base["base_commit"])
    owned = ownership.own_witnesses(mutation)
    preexisting = set(gitops.record_preexisting_dirty(mutation, store.root))
    if preexisting & set(changed):
        raise p4.reconcile(f"{sorted(preexisting & set(changed))} held changes before this START began",
                           p4.REASON_ADOPTION_MISMATCH)
    for path, data in sorted(changed.items()):
        current = ownership.capture(store, git, path, deletion=False, base=pre_base)
        if current.material == data:
            continue  # already adopted by an earlier attempt: only re-proven below
        witness = owned.get(path)
        if witness is None or ownership.witness_problem(store, git, witness, pre_base) is not None:
            raise p4.reconcile(f"{path} does not hold the bytes this START witnessed, so N+1 is not adopted over it",
                               p4.REASON_ADOPTION_MISMATCH)
        destination = store.root / path
        temporary = destination.with_name(f".{destination.name}.workline-p4-adopt")
        temporary.write_bytes(data)
        os.replace(temporary, destination)
    witnesses = ownership.bind_declarations(store, git, result_paths, deleted_paths, pre_base)
    ownership.assert_ownership(mutation, witnesses)
    for witness in witnesses:
        expected = target.payloads.get(witness.path)
        if expected is not None and witness.material != expected:
            raise p4.reconcile(f"{witness.path} does not hold Candidate N+1's bytes after adoption",
                               p4.REASON_ADOPTION_MISMATCH)
    content = work_review.content_of(target.candidate)
    rebuilt, payloads = _p4_candidate_from_witnesses(
        session, git, witnesses, base["base_commit"], base["branch"], run.work_id, str(content.get("message") or ""),
        result_paths, deleted_paths,
    )
    if work_review.candidate_hash(rebuilt) != result.result_candidate_hash:
        raise p4.reconcile("the Candidate rebuilt from the adopted working tree is not the persisted Candidate N+1",
                           p4.REASON_ADOPTION_MISMATCH)
    ownership.require_current(store, git, witnesses, pre_base)
    resulting = resulting_tree.resulting_tree_id(
        store, git, base["base_commit"], resulting_tree.entries_from_records(work_review.entries_of(rebuilt)), payloads,
    )
    work_verify.verify(store, git, target, resulting_tree_id=resulting)


def _p4_begin_successor(session: "_Session", run: WorkRun, predecessor_id: str) -> None:
    """The successor's G1: Candidate N+1 (after adoption) or, on a Human decision, the re-witnessed Candidate."""
    store = session.store
    review = ReviewStore(store)
    predecessor = review.gate_chain(predecessor_id)
    if predecessor is None:
        raise p4.reconcile(f"the predecessor {predecessor_id} has no chain", p4.REASON_LINKAGE_INVALID)
    git = hermetic_module.enter(store)
    predecessor_material = p4_run_material(store, WorkRun(run.work_id, predecessor_id, "", ""), predecessor)
    base = predecessor_material.base
    pre_base = _pre_s_c0_base(work_record(session.mutation.record), base["base_commit"])
    predecessor_envelope = _p4_envelope(store, predecessor)
    # a repair or Human-decision successor stays in its cycle's stored family (GAP-A item 5)
    policy = _p4_policy(store, predecessor)
    writes = p4.HistoryWrites()
    if p4.shape_of(predecessor) == p4.SHAPE_REPAIR and len(predecessor.generations) == p4.REPAIR_SETTLE_GENERATION:
        _p4_adopt(session, WorkRun(run.work_id, predecessor_id, "", "", contract=work_review.P4_CONTRACT), predecessor)
        batch, result, result_digest = _p4_settled_result(store, predecessor)
        snapshot = review.read_candidate_snapshot(result.result_candidate_hash)
        generation = int(predecessor_envelope["candidate_generation"]) + 1
        succession = p4.succession_record(predecessor_id, predecessor.generations[0].candidate_hash,
                                          batch.repair_batch_id, result_digest)
        set_aside = [{"review_run_id": predecessor_id, "reason": p4.SET_ASIDE_REPAIRED}]
        write_snapshot = False
        decision = getattr(session.review, "human_decision", None)
    elif len(predecessor.generations) == p4.ADJUDICATION_SETTLE_GENERATION \
            and review.read_adjudication(predecessor_id).outcome == p4.HUMAN_WAIT \
            and predecessor_id in _p4_decision_bindings(session.mutation) \
            and getattr(session.review, "human_decision", None) is not None:
        set_aside = [{"review_run_id": predecessor_id, "reason": p4.SET_ASIDE_HUMAN_DECISION}]
        evidence = getattr(session.review, "decision_evidence", ())
        p4.require_decision_evidence_cover(review, set_aside, evidence)  # GAP-G, before anything else
        if p4.history_contract_of_policy(policy) is not None:
            # §28.14 / GAP-G: the one Human Decision Evidence of the P4-R7 waiting Run, persisted in this G1
            requirement = _p4_requirement(store, git, run.work_id)
            writes = p4.HistoryWrites(decisions=tuple(
                p4.decision_evidence_record(
                    review, item,
                    session.mutation.reserve_id(history.review_decision_key(item.affected_review_run_id),
                                                "review_decision"),
                    review_kind=work_review.REVIEW_KIND, target_identity=run.work_id, current_requirement=requirement,
                )
                for item in evidence
            ))
        # the decision bound to this predecessor's wait before the reservation: the same one again, or a refusal
        decision = _p4_bind_decision(session, predecessor_id, predecessor)
        result_paths, deleted_paths = work_review.declared_paths(predecessor_material.candidate)
        witnesses = ownership.bind_declarations(store, git, result_paths, deleted_paths, pre_base)
        ownership.assert_ownership(session.mutation, witnesses)
        candidate, payloads = _p4_candidate_from_witnesses(
            session, git, witnesses, base["base_commit"], base["branch"], run.work_id,
            str(work_review.content_of(predecessor_material.candidate).get("message") or ""), result_paths, deleted_paths,
        )
        snapshot = work_review.snapshot_for(work_review.snapshot_material(candidate, payloads))
        generation, succession, write_snapshot = 1, None, True
    else:
        raise p4.reconcile(f"{run.review_run_id} is reserved as the successor of {predecessor_id}, which neither "
                           "settled a repair nor waits on a Human decision this START binds and this invocation carries",
                           p4.REASON_LINKAGE_INVALID)
    width = len(base["base_commit"])
    reconstruction = work_review.read_material(snapshot, snapshot.candidate_hash, width)
    resulting = resulting_tree.resulting_tree_id(
        store, git, base["base_commit"],
        resulting_tree.entries_from_records(work_review.entries_of(reconstruction.candidate)), reconstruction.payloads,
    )
    run.contract = work_review.P4_CONTRACT
    # a P6 successor is a new Run: it freezes the Effective Policy current at its start (R6-1, §30.6)
    effective = _p4_new_run_effective(session, policy)
    frozen = _p4_freeze_material(
        session, run, git, reconstruction.candidate, snapshot, resulting, pre_base, generation=generation,
        succession=succession, set_aside=set_aside, declared=bool(work_review.entries_of(reconstruction.candidate)),
        write_snapshot=write_snapshot, human_decision=decision, policy=policy, history_writes=writes,
        effective=effective,
    )
    if succession is not None:
        problems = p4.linkage_problems(
            batch, result, source_run_id=predecessor_id, source_candidate_hash=predecessor.generations[0].candidate_hash,
            source_candidate_generation=int(predecessor_envelope["candidate_generation"]),
            snapshot_hash=snapshot.candidate_hash, successor_envelope=frozen.task_inputs[0].request_envelope,
            repair_result_digest=result_digest,
        )
        if problems:
            raise p4.reconcile("the repaired Candidate's linkage: " + "; ".join(problems), p4.REASON_LINKAGE_INVALID)
    _p4_accept(session, run, frozen)


def p4_cycle_paths(store: ProjectStore, reserved: dict[str, Any], work_id: str) -> tuple[str, ...]:
    """Every canonical record path of every Run this START's P4 cycle holds (the L-2 own-Review set)."""
    from .review import recovery

    review = ReviewStore(store)
    found: set[str] = set()
    for run_id in _p4_reserved_runs(reserved, work_id):
        chain = review.gate_chain(run_id)
        if chain is None:
            continue
        found |= set(recovery.p4_record_paths(review, run_id, chain))
    return tuple(sorted(path for path in found if not path.startswith(review_paths.SUPERSESSIONS_DIR + "/")))


def _p4_material_at(at: "CommittedRecords", record: WorkRecord, item: str) -> ProofMaterial:
    """The P4 Run's records exactly as one commit holds them: discovered, adjudicated and sealed at generation 5."""
    run = record.run
    try:
        chain = at.gate_chain(run.review_run_id)
        if chain is None or len(chain.generations) != p4.SEAL_GENERATION or p4.chain_problems(chain) \
                or p4.shape_of(chain) != p4.SHAPE_SEAL:
            raise _proof_failed(item, f"{at.commit} does not hold P4 Run {run.review_run_id} as discovered, adjudicated "
                                      "and sealed")
        fifth = chain.latest
        if not fifth.sealed or fifth.receipt_id != run.receipt_id:
            raise _proof_failed(item, f"{at.commit} does not hold the seal issuing Receipt {run.receipt_id}")
        first = chain.generations[0]
        snapshot = at.read_candidate_snapshot(first.candidate_hash)
        candidate = (snapshot.material or {}).get("candidate") or {}
        width = len(str(candidate.get("declared_base", {}).get("base_commit", "")))
        reconstruction = work_review.read_material(snapshot, first.candidate_hash, width)
        task_input = at.read_task_input(str(first.accepted_tasks[0]["task_id"]))
        problems = work_review.task_input_problems_p4(task_input, snapshot.material or {}, first.candidate_hash,
                                                      first.review_context_hash)
        if problems:
            raise _proof_failed(item, "; ".join(problems))
        receipt = at.read_receipt(run.receipt_id)
        adjudication = at.read_adjudication(run.review_run_id)
        if serialize.digest(adjudication.to_record()) != chain.generation(p4.ADJUDICATION_SETTLE_GENERATION).adjudication_digest:
            raise _proof_failed(item, f"the adjudication at {at.commit} is not the one generation 4 binds")
        context = work_review.inner_context(task_input.request_envelope["context"])
    except ValidationError as exc:
        raise _proof_failed(item, f"the Run's records at {at.commit} do not read: {exc}") from exc
    return ProofMaterial(chain, snapshot, reconstruction, task_input, context, receipt, adjudication)


def _p4_post_commit(session: "_Session", sealed: Sealed, git: HermeticGit, failure: ReconcileRequired) -> None:
    """K1 exists and C-2(K1) fails for a P4 Run: never F4 Class A (G-3).

    When the failure is staleness of the authorization - the bound Context or
    Policy no longer re-derives - the G5 Receipt is superseded by the P4 G6
    invalidation at once, so no live Receipt survives known staleness, and the
    START stops for reconciliation. Anything else is reconcile as it stands.
    """
    from .implementation import package_directory

    store, run = session.store, sealed.run
    chain = _chain(store, run)
    stale = False
    activation = session.activation
    if activation is not None and chain is not None:
        capability = sealed.material.context["review_checkout_capability"]
        try:
            recomputed = work_context.context_record(
                store.workline_root(), package_directory(store.workline_root()), activation.binding(),
                capability["base_tree"], capability["resulting_tree"],
            )
            first = chain.generations[0]
            policy = _p4_task_policy(sealed.material.task_input)  # the Run's own stored family policy (GAP-A)
            stale = serialize.digest(work_review.context_record_p4(recomputed, policy)) != first.review_context_hash \
                or p4.envelope_policy_hash(sealed.material.task_input.request_envelope) != first.effective_policy_hash
        except StopError:
            stale = False
    review = ReviewStore(store)
    if stale and chain is not None and chain.latest.generation == p4.SEAL_GENERATION and chain.latest.sealed \
            and not review.supersession_exists(str(chain.latest.receipt_id)):
        p4_invalidate(session, run, chain)
        raise p4.stop(p4.CODE_RECEIPT_INVALIDATED,
                      f"the authorization of Work Review Run {run.review_run_id} is stale ({failure.message}); its "
                      "generation-5 Receipt is superseded by the P4 generation-6 invalidation, and the START stops for "
                      "reconciliation (never F4 Class A)")
    raise failure
