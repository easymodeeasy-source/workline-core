"""Work-terminal Review activation maintenance (Workline infrastructure, not a Skill) - P3 F1 §8, Gate 3.

A Project may terminalize Works under the review-v1 operation contract only
once it has been activated for it, and the activation is one immutable canonical
Review record (``.workline/review/activation/work-terminal-v1.yaml``):

```text
operation_contract          review-v1
legacy_event_count          N - the parsed Events HEAD's committed event log holds
legacy_event_prefix_sha256  work-terminal-activation-digest-v1 over those N Events
activation_base_head        HEAD, the commit the activation is decided on
```

It changes a Project-specific Workline rule, so it is neither a domain
operation nor something an AI does on its own initiative:

* it runs only on an explicit positive human confirmation (``confirmed=True``,
  ``--confirm`` on the CLI), refused before the Project lock - and so before any
  mutation exists - without one. Nothing else stands in for it: not an absent
  record, not the caller, not the Project's state, not any Review file;
* it has its own top-level operation owner, ``work-terminal-activation``, and
  its own mutation, and the Mutation Controller lets no other owner create the
  record (:meth:`workline.mutation.MutationController._guard_activation_record`);
* it starts only while no other mutation of any owner is pending, so an
  unfinished START - legacy above all - is never surprised by a new contract,
  and the event-log prefix it binds stays as it was read; its own pending
  mutation claims the event log in its write scope, so no operation that
  appends a lifecycle event opens beside it until it is finished;
* N and the digest come from the event log HEAD has COMMITTED, read through
  the class B environment by the one digest implementation START's verifier
  uses (:mod:`workline.review.activation`); never from the working tree;
* the record is committed by this operation's own mutation with the ordinary
  infrastructure commit, and pushed - that commit only, never forced - to the
  approved destination when the Project has a remote. A missing or mismatched
  destination STOPs as it does for every operation; nothing here pins one;
* it is produced once per Project and never replaced: run again, it answers
  ``already_activated`` for a record that is committed and still proves, and it
  never recomputes, moves or rewrites one. Anything else at that path fails
  closed;
* it migrates nothing: no Event, Work, Consumption or other record is touched,
  and it selects nothing - review-v1 stays an explicit per-invocation opt-in of
  START, and legacy START stays exactly as it was.

It is not routed from ``skills/project-router``: no Skill exists for it, like
the push destination pin maintenance and the bootstrap backfill.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from . import gitcmd, gitops
from .bootstrap import is_established_project
from .destination import ensure_push_destination
from .errors import ReconcileRequired, StopError, ValidationError
from .mutation import Effect, Mutation, MutationController, WriteScope, abandon_on_stop
from .oplock import project_operation
from .registry import validate_registry
from .review import activation as work_activation
from .review import checkout, fsafe, gate, records, serialize, work_review
from .review import hermetic as hermetic_module
from .review import paths as review_paths
from .review.hermetic import HermeticGit
from .review.store import ReviewStore
from .review.validate import validate_review
from .review.workcommit import EVENT_LOG
from .store import Event, ProjectStore, render_event_line

OWNER = "work-terminal-activation"
ACTIVATION_COMMIT_MESSAGE = "chore(workline): activate review-v1 Work terminalization"
ACTIVATION_REL = review_paths.WORK_TERMINAL_ACTIVATION_REL
#: The stage that decides the record, and the Git stage that commits (and, with a remote, pushes) it.
STAGE_ACTIVATION = "activation"
STAGE_COMMIT = "commit"


@dataclass(frozen=True)
class ActivationResult:
    status: str  # "activated" | "already_activated"
    project_root: Path
    operation_contract: str
    legacy_event_count: int
    legacy_event_prefix_sha256: str
    activation_base_head: str
    mutation_id: str | None = None
    head: str | None = None  # the commit that holds the record
    pushed: bool = False
    resumed: bool = False


def activate_work_terminal_review(project_root: Path, *, confirmed: bool = False) -> ActivationResult:
    """Activate review-v1 Work terminalization for one established Project, on explicit human confirmation.

    ``confirmed`` must be exactly ``True``: it is the human's confirmation that
    this Project's Work-terminal contract may change (``rules/human-confirmation``).
    Without it nothing is read, locked or written.
    """
    if confirmed is not True:
        raise StopError(
            "activating review-v1 Work terminalization changes this Project's Workline rules and needs explicit human "
            "confirmation (confirmed=True; --confirm on the CLI); nothing was begun",
            code="work_terminal_activation_unconfirmed",
        )
    root = Path(project_root)
    if not root.is_dir():
        raise StopError(f"Project root is not a directory: {root}", code="project_root_missing")
    root = root.resolve()
    store = ProjectStore(root)
    if gitcmd.toplevel(root) != root:
        raise StopError(
            f"Project root is not the Git top-level; activation needs an established Project repository: {root}",
            code="not_a_project",
        )
    with project_operation(store, OWNER, {"operation_contract": records.OPERATION_CONTRACT_REVIEW_V1}):
        return _activate_locked(store, root)


def _activate_locked(store: ProjectStore, root: Path) -> ActivationResult:
    if not is_established_project(store):
        raise StopError(
            "not a valid established Workline Project (project.yaml missing, invalid or untracked); "
            "activation does not initialize a Project",
            code="not_a_project",
        )
    validation = validate_registry(store.workline_root())
    if not validation.ok:
        detail = "; ".join(f"{p.code}: {p.message}" for p in validation.problems)
        raise StopError(f"registry validation failed: {detail}", code="registry_invalid")
    require_prerequisite_gates()

    controller = MutationController(store)
    invocation = {"operation": OWNER, "project_root": str(root)}
    pending = controller.list_pending()
    own = [p for p in pending if p["owner"] == OWNER and p["invocation"] == invocation]
    others = [p for p in pending if p not in own]
    if len(own) > 1:
        raise ReconcileRequired(f"{len(own)} pending activation mutations match this request: reconcile required")
    if not own:
        existing = ReviewStore(store).read_activation()  # malformed or of an unknown contract: the reader's refusal
        if existing is not None:
            return _already_activated(store, root, existing)
    if others:
        detail = ", ".join(f"{p['mutation_id']} (owner {p['owner']})" for p in others)
        raise StopError(
            f"another Workline operation is still pending ({detail}); a pending operation is never surprised by a "
            "new Work-terminal contract, so nothing is activated until it is finished",
            code="pending_operation",
        )

    decision = None if own else _decide(store, root)
    destination = ensure_push_destination(store)
    if destination is not None and decision is not None:
        # The Git stage records a push only while the barrier is clear; refused here, nothing is created.
        from .review import publication

        publication.require_barrier_clear(root, decision.activation_base_head)
    # The event log is held in the write scope, never written: while this decision is pending, no operation
    # that appends a lifecycle event opens beside it (``rules/git`` Operation Owner).
    mutation = controller.open(OWNER, invocation, WriteScope(files=(ACTIVATION_REL, EVENT_LOG)))
    with abandon_on_stop(mutation):
        gitops.ensure_git_ready(root)
        preexisting = gitops.record_preexisting_dirty(mutation, root)
        gitops.ensure_separable(preexisting, [ACTIVATION_REL])
        if not mutation.has_stage(STAGE_ACTIVATION):
            # A resumed attempt that decided nothing decides now, under every precondition of a first one.
            if decision is None:
                if ReviewStore(store).read_activation() is not None:
                    raise ReconcileRequired(
                        f"{ACTIVATION_REL} exists, and the pending activation {mutation.id} never decided it; a record "
                        "it did not decide is never adopted: reconcile required"
                    )
                decision = _decide(store, root)
                if destination is not None:
                    from .review import publication

                    publication.require_barrier_clear(root, decision.activation_base_head)
            mutation.add_effects(STAGE_ACTIVATION, [Effect.create_file(ACTIVATION_REL, _content(decision))])
    decided = _recorded_decision(mutation)
    mutation.apply()
    gitops.finalize(mutation, STAGE_COMMIT, ACTIVATION_COMMIT_MESSAGE, [ACTIVATION_REL], destination=destination)
    head = _postcheck(store, mutation, decided, preexisting)
    mutation.complete()
    return ActivationResult(
        "activated",
        root,
        decided.operation_contract,
        decided.legacy_event_count,
        decided.legacy_event_prefix_sha256,
        decided.activation_base_head,
        mutation.id,
        head,
        pushed=destination is not None,
        resumed=mutation.resumed,
    )


# --------------------------------------------------------------------------- the prerequisite gates (F1 §12)

#: A review-v1 work_completed as P1 R4 §5 / F1 §12.1 frozen it: the lifecycle fields and the four keys of metadata.
_GATE_1_PROBE = {
    "id": "evt_00000000000000000000000001",
    "type": "work_completed",
    "entity": "w_00000000000000000000000001",
    "at": "2026-01-01T00:00:00Z",
    "operation_contract": records.OPERATION_CONTRACT_REVIEW_V1,
    "review_receipt_id": "rcp_00000000000000000000000001",
    "review_run_id": "rr_00000000000000000000000001",
    "review_generation": 3,
}


def require_prerequisite_gates() -> None:
    """F1 §12: the producer is unavailable unless Gate 1 and Gate 2 hold in the implementation that runs it.

    Gate 1 - the Event metadata carrier: a review-v1 ``work_completed`` and its
    metadata come back unchanged through the physical line, the canonical
    reader and the Event model's record form, and the digest reads them the
    same way. Gate 2 - the Consumption ``artifact_kind`` repair: a Work-kind
    Consumption is representable for a result-less Work, and a result-bearing
    one still binds its commit. Asked of the code itself, so a producer can
    never run on an implementation that lacks either.
    """
    problems: list[str] = []
    try:
        line = render_event_line(Event.from_record(dict(_GATE_1_PROBE)))
        parsed = work_activation.parse_event_log((line + "\n").encode("utf-8"))
        if Event.from_record(json.loads(line)).to_record() != _GATE_1_PROBE or parsed != [_GATE_1_PROBE]:
            problems.append("Gate 1: an Event's review-v1 metadata does not survive the carrier")
    except (ValidationError, ValueError, TypeError) as exc:
        problems.append(f"Gate 1: the Event metadata carrier refuses the review-v1 record ({exc})")
    if "artifact_kind" not in records.CONSUMPTION_FIELDS or records.CONSUMPTION_ARTIFACT_KINDS != ("result_commit", "empty"):
        problems.append("Gate 2: the Consumption record carries no artifact_kind")
    else:
        work_kind = {
            "schema": records.SCHEMA_CONSUMPTION, "version": records.VERSION,
            "consumption_id": "rcs_00000000000000000000000001", "receipt_id": _GATE_1_PROBE["review_receipt_id"],
            "review_run_id": _GATE_1_PROBE["review_run_id"], "review_generation": 3, "review_kind": work_review.REVIEW_KIND,
            "authorized_candidate_hash": "a" * 64,
            "operation_identity": work_review.operation_identity(str(_GATE_1_PROBE["entity"])),
            "operation_mutation_id": "mut_00000000000000000000000001", "terminal_event_id": _GATE_1_PROBE["id"],
            "terminal_event_type": "work_completed", "target_identity": _GATE_1_PROBE["entity"],
        }
        try:
            empty = records.Consumption.from_record({**work_kind, "authorized_result_commit_sha": None,
                                                     "artifact_kind": "empty"}, "Gate 2 probe")
            bound = records.Consumption.from_record({**work_kind, "authorized_result_commit_sha": "b" * 40,
                                                     "artifact_kind": "result_commit"}, "Gate 2 probe")
            if (empty.artifact_kind, bound.artifact_kind) != ("empty", "result_commit"):
                problems.append("Gate 2: the Consumption record does not keep artifact_kind")
        except ValidationError as exc:
            problems.append(f"Gate 2: a Work-kind Consumption is not representable ({exc})")
        else:
            try:
                records.Consumption.from_record({**work_kind, "authorized_result_commit_sha": None,
                                                 "artifact_kind": "result_commit"}, "Gate 2 probe")
                problems.append("Gate 2: a result_commit Consumption is accepted without its result commit")
            except ValidationError:
                pass
    if problems:
        raise StopError(
            "the Work-terminal activation producer is unavailable in this implementation (P3 F1 §12): "
            + "; ".join(problems) + "; nothing was begun",
            code="work_terminal_activation_unavailable",
        )


# --------------------------------------------------------------------------- the decision


@dataclass(frozen=True)
class _Decision:
    record: records.WorkTerminalActivation

    @property
    def activation_base_head(self) -> str:
        return self.record.activation_base_head


def _decide(store: ProjectStore, root: Path) -> _Decision:
    """The record this activation creates, decided from HEAD's committed state under every precondition of F1 §8.3.

    Everything here is read before any mutation exists, so a refusal leaves
    nothing behind.
    """
    if not fsafe.immutable_create_supported():
        raise StopError(
            "the activation record is an immutable Review record, which this platform cannot keep inside the Project; "
            "nothing was begun",
            code="review_create_unsupported",
        )
    if ACTIVATION_REL in gitops.capture_preexisting_dirty(root):
        raise StopError(gitops.OVERLAP_MESSAGE + ACTIVATION_REL, code="dirty_overlap")
    git = hermetic_module.enter(store)
    gitops.ensure_git_ready(root)  # detached HEAD: detached_head
    head = gitcmd.head_commit(root)
    if head is None or not gitcmd.full_commit_id(head):
        raise StopError(
            "HEAD names no commit, so there is no committed event log to activate on; nothing was begun",
            code="work_terminal_activation_base_invalid",
        )
    events = work_activation.committed_event_records(git, head)
    if events is None:
        raise StopError(
            f"{head}'s committed {EVENT_LOG} does not read as canonical Events, so which Events are pre-activation "
            "cannot be fixed; nothing was begun",
            code="work_terminal_activation_log_unreadable",
        )
    digest = work_activation.prefix_digest(events, len(events))
    if digest is None:
        raise StopError(
            f"{head}'s committed {EVENT_LOG} holds an Event the activation digest cannot render; nothing was begun",
            code="work_terminal_activation_log_unreadable",
        )
    record = records.WorkTerminalActivation(records.OPERATION_CONTRACT_REVIEW_V1, len(events), digest, head)
    try:
        records.WorkTerminalActivation.from_record(record.to_record(), "the decided activation record")
    except ValidationError as exc:
        # activation_base_head is frozen as a 40-hex commit id (F1 §7.1): a SHA-256 repository is not representable
        raise StopError(
            f"the activation record cannot hold this Project's HEAD ({exc}); the frozen review-work-terminal-activation "
            "record names a 40-hex commit, so this repository is not activated; nothing was begun",
            code="work_terminal_activation_base_invalid",
        ) from exc
    # The existing Review namespace reads canonically, and its activation classification has nothing to object to
    problems = validate_review(store)
    if problems:
        raise StopError(
            f"the existing Review namespace does not read canonically ({problems[0].code}: {problems[0].message}); "
            "nothing was begun",
            code="review_namespace_unreadable",
        )
    # The record has to reach every clone exactly as it is written: committable, and checked out as these bytes
    gate.require_committable(store, [ACTIVATION_REL])
    checkout.require_checkout_capability(store, [ACTIVATION_REL])
    return _Decision(record)


def _content(decision: _Decision) -> str:
    return serialize.canonical_text(decision.record.to_record())


def _recorded_decision(mutation: Mutation) -> records.WorkTerminalActivation:
    """The record this mutation decided, read back from its own durable stage - the only authority on resume."""
    found = [e for e in mutation.stage_effects(STAGE_ACTIVATION)]
    if [e.get("kind") for e in found] != ["create_file"] or found[0]["payload"].get("path") != ACTIVATION_REL:
        raise ReconcileRequired(
            f"mutation {mutation.id} holds an activation stage that is not one create of {ACTIVATION_REL}: reconcile required"
        )
    content = found[0]["payload"]["content"]
    try:
        data, _ = serialize.parse_canonical(content.encode("utf-8"), "the recorded activation record")
        decided = records.WorkTerminalActivation.from_record(data, "the recorded activation record")
    except ValidationError as exc:
        raise ReconcileRequired(f"mutation {mutation.id} recorded an activation record that does not read: {exc}") from exc
    if serialize.canonical_text(decided.to_record()) != content:
        raise ReconcileRequired(f"mutation {mutation.id} recorded an activation record in non-canonical form: reconcile required")
    return decided


# --------------------------------------------------------------------------- an activation that already exists


def _already_activated(
    store: ProjectStore, root: Path, existing: records.WorkTerminalActivation
) -> ActivationResult:
    """The idempotent answer: the record is committed, unchanged, and still proves on HEAD's history.

    Nothing is recomputed against the later HEAD, no boundary moves and nothing
    is written. A record HEAD does not hold, one the working tree holds
    differently, or one whose prefix no longer reproduces is never adopted,
    replaced or repaired: reconcile required.
    """
    git = hermetic_module.enter(store)
    head = gitcmd.head_commit(root)
    stored = ReviewStore(store).read_bytes(ACTIVATION_REL)
    committed = None if head is None else git.run_bytes("cat-file", "blob", f"{head}:{ACTIVATION_REL}")
    if committed is None or not committed.ok or committed.stdout != stored or gitcmd.changed_against_head(root, [ACTIVATION_REL]):
        raise ReconcileRequired(
            f"{ACTIVATION_REL} is present but is not the record HEAD has committed, and no pending activation of this "
            "Project decided it; an activation record is never adopted, recomputed or replaced: reconcile required"
        )
    digest = work_activation.committed_prefix_digest(git, head, existing.legacy_event_count)
    if digest is None or digest != existing.legacy_event_prefix_sha256:
        raise ReconcileRequired(
            f"this Project's activation fixes {existing.legacy_event_count} pre-activation Events, and {head}'s committed "
            "event log no longer reproduces their digest; the activation is never recomputed or replaced: reconcile required"
        )
    return ActivationResult(
        "already_activated",
        root,
        existing.operation_contract,
        existing.legacy_event_count,
        existing.legacy_event_prefix_sha256,
        existing.activation_base_head,
        head=head,
    )


# --------------------------------------------------------------------------- postcheck


def _postcheck(
    store: ProjectStore, mutation: Mutation, decided: records.WorkTerminalActivation, preexisting: list[str]
) -> str:
    """The committed activation is exactly the decided record, it proves on its own commit, and nothing else moved."""
    root = store.root
    content = serialize.canonical_text(decided.to_record())
    effects: list[dict[str, Any]] = mutation.effects
    written = {e["payload"]["path"] for e in effects if e["kind"] in ("write_file", "create_file")}
    if written != {ACTIVATION_REL}:
        raise StopError(f"postcheck: activation wrote more than its record: {sorted(written)}", code="postcheck_failed")
    if any(e["kind"] in ("add_relation", "remove_relation", "append_event") for e in effects):
        raise StopError("postcheck: activation touched domain state", code="postcheck_failed")
    head = gitcmd.head_commit(root)
    if head is None:
        raise StopError("postcheck: the activation commit is missing", code="postcheck_failed")
    git: HermeticGit = hermetic_module.enter(store)
    committed = git.run_bytes("cat-file", "blob", f"{head}:{ACTIVATION_REL}")
    if not committed.ok or committed.stdout != content.encode("utf-8"):
        raise StopError(f"postcheck: {head} does not hold the decided activation record", code="postcheck_failed")
    if gitcmd.changed_against_head(root, [ACTIVATION_REL]):
        raise StopError("postcheck: the activation record differs from HEAD", code="postcheck_failed")
    if gitcmd.descends_from(root, head, decided.activation_base_head) is not True:
        raise StopError(
            f"postcheck: {head} does not descend from the activation base {decided.activation_base_head}",
            code="postcheck_failed",
        )
    digest = work_activation.committed_prefix_digest(git, head, decided.legacy_event_count)
    if digest != decided.legacy_event_prefix_sha256:
        raise StopError(f"postcheck: the activation does not prove on {head}'s committed event log", code="postcheck_failed")
    if ReviewStore(store).read_activation() != decided:
        raise StopError("postcheck: the activation record does not read back as decided", code="postcheck_failed")
    lost = sorted(set(preexisting) - set(gitops.capture_preexisting_dirty(root)))
    if lost:
        raise StopError("postcheck: unrelated changes were consumed: " + ", ".join(lost), code="postcheck_failed")
    return head


__all__ = [
    "ACTIVATION_COMMIT_MESSAGE",
    "ACTIVATION_REL",
    "ActivationResult",
    "OWNER",
    "activate_work_terminal_review",
    "require_prerequisite_gates",
]
