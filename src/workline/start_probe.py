"""RB1's read-only probe of a pending START record (RB11 RT-1a: the START owner probe, stage 1a).

``run-workline.py status`` asks every pending recovery record how its owner's
recovery would treat it (``rules/git``: Read-only status; WORKLINE_COMPLETION_SPRINT
§29.16). For a record of owner ``start`` this module answers, by walking START's
own control flow with its guards - read only, offline, writing nothing - and
calling START's own predicates wherever they read only (rev-11 BRIEF §41.3,
ADMISSION MATRIX §A.0 - §A.3, unchanged by Sprint §41.3):

```text
S1.1  domain: owner "start" and invocation.operation == "start"; every other START-owned
      operation is unknown_or_invalid with a fixed reason and no record value echoed
S1.2  the exact legacy invocation key set {operation, work_id, mode} (stage 1a); a review-v1
      or any other key set, and any Phase integration semantics note, is unknown_or_invalid
S2.0  mode in MODES
S3.x  the Work resolves; marker compatibility over the passed pending set; the recorded
      cancel (_cancel_to_finish); structure; the Phase integration entry gate; Git ready;
      the push destination
S4.x  the recovery-disposition barrier and the open checks over the passed pending set
S5.x  the post-open readers, with START's guards: completion, hold only without a
      finishing completion, derivations only without either, move only on derivations
S6.1  replay_probe, unchanged: anything but clear is unknown_or_invalid
S6.2  the replay writes nothing: every recorded effect classifies applied (PO-52, method (b))
S7.x  the post-replay dispatch: each finish path's local refusals, or run_work's gate list
S8    everything evaluated and passed: pending_resumable (the narrowed claim)
```

The first refusal decides. It is ``pending_reconcile_required`` only when the
raising call carries a check ID (``errors.with_check``) on the ALLOW list of the
step START was at - the class-R calls of ADM §A.2, which read only the record's
own bytes and its own invocation - and the refusal is a ``ReconcileRequired``.
The message text, ``code`` and ``reason`` are never read to decide. Every other
refusal, and every step that cannot be evaluated read-only, is
``unknown_or_invalid``.

What this never does: write anything (no runtime file, no scratch, no index
refresh, no lock, no Git object - Git runs with its optional locks off), call
``hermetic.enter``, call a START path that opens, closes or mutates, list the
pending records itself (it uses the set status passes, which honours a recovery
disposition's ``excluding``), or apply START-run predicates to a START-owned
operation other than ``start``.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import json
from typing import Any, Callable

from . import gitops
from .errors import ReconcileRequired
from .mutation import (
    MATCHING,
    REPLAY_CLEAR,
    Mutation,
    MutationController,
    WriteScope,
    _classify_recorded,
    _require_decided_branch,
    _require_finalized_branch,
    read_only_git,
    replay_probe,
)
from .store import ProjectStore

#: The classifications this probe yields (the RB1 vocabulary, §29.16).
PENDING_RESUMABLE = "pending_resumable"
PENDING_RECONCILE = "pending_reconcile_required"
UNKNOWN_OR_INVALID = "unknown_or_invalid"

#: The reason codes of ``unknown_or_invalid`` (ADM §A.1 S1.1, S6.1, S6.2).
NO_PROBE = "no_read_only_resume_probe"
NOT_PROBED_GENERATION = "start_operation_not_probed_review_generation"
NOT_PROBED_PLAN_EXCLUSION = "start_operation_not_probed_plan_exclusion"
POST_REPLAY_NOT_READ_ONLY = "post_replay_not_read_only"

#: The START-owned operations other than ``start`` that get a fixed reason (PO-50; no record value is echoed).
_OTHER_OPERATIONS = {"review-generation": NOT_PROBED_GENERATION, "start-plan-exclude": NOT_PROBED_PLAN_EXCLUSION}

#: Stage 1a: the exact key set of a legacy START invocation (start.py ``invocation`` at the open).
LEGACY_KEYS = frozenset({"operation", "work_id", "mode"})

# The ALLOW list (ADM §A.2), per step of START's control flow: the check IDs of the raising calls whose
# predicate reads only the record's own bytes and its own invocation (class R). A check ID is admitted only at
# the step named here, and only as the record's FIRST refusal. ``ops.832`` is ``ops._recorded_stages``, which the
# cancel (2275), hold (2759), derivations (3022) and move (3234) readers each pass their own ``refuse`` to.
ALLOW: dict[str, frozenset[str]] = {
    # S3.4 the recorded cancel (_read_cancel_record, _prove_cancel)
    "S3.4": frozenset({
        "start.2274", "ops.832", "start.2278", "start.2282", "start.2298", "start.2305", "start.2309",
        "start.2312", "start.2314", "start.2318", "start.2454", "start.2457", "start.2463", "start.2471",
        "start.2477", "start.2488", "start.2495", "start.2504", "start.2510", "start.2518", "start.2542",
        "start.2544", "start.2547", "start.2550", "start.2557", "start.2568",
    }),
    # S5.1 the unfinished completion (_completion_to_finish), operation "start" only
    "S5.1": frozenset({"start.1530", "start.1540", "start.1552"}),
    # S5.2 the recorded hold (_hold_to_finish), reached only when no completion is finishing
    "S5.2": frozenset({
        "start.2750", "start.2758", "ops.832", "start.2767", "start.2769", "start.2774", "start.2784",
        "start.2786", "start.2788", "start.2793", "start.2800", "start.2811", "start.2817",
    }),
    # S5.3 the recorded derivations (_derivations_to_reuse); 3053 only on its record-only branch
    "S5.3": frozenset({
        "start.3002", "start.3010", "start.3021", "ops.832", "start.3027", "start.3030", "start.3033",
        "start.3038", "start.3053.between",
    }),
    # S5.4 the recorded move (_derive_move_to_finish); 3274 raises the refusal 2945 builds
    "S5.4": frozenset({"ops.832", "start.3260", "start.3274", "start.3281"}),
    # S7.3 the refused-result note (900), only under every condition of S7.3
    "S7.3": frozenset({"start.900"}),
}


@dataclass(frozen=True)
class StartProbe:
    """What the probe found: the classification, its reason, and where START's walk ended (internal)."""

    classification: str
    code: str
    message: str
    step: str
    check_id: str | None = None

    def reason(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class _ProbeWouldWrite(Exception):
    """START would write here (never a StopError: no START handler takes it for a refusal)."""


class _ProbeMutation(Mutation):
    """A pending START record as START's readers see it once the mutation is resumed - with no way to write.

    A copy of the record, held in memory. Every write path of :class:`Mutation`
    (reserve, record, apply, save, complete, abandon) is refused before it does
    anything. A note or a write scope START would save before its next domain step
    is kept in this copy only, after the same branch checks :meth:`Mutation.set_note`
    and :meth:`Mutation.extend_scope` make - so a later reader meets what START's own
    later reader meets, and nothing reaches the disk.
    """

    def _writable(self) -> None:
        raise _ProbeWouldWrite(f"START would write mutation {self.id} here")

    def set_note(self, key: str, value: Any) -> None:
        _require_decided_branch(self, f"noting {key}")
        _require_finalized_branch(self, f"noting {key}")
        self.record.setdefault("notes", {})[key] = value

    def extend_scope(self, entities: list[str] = (), files: list[str] = ()) -> None:
        _require_decided_branch(self, "extending its write scope")
        _require_finalized_branch(self, "extending its write scope")
        scope = self.scope
        merged = WriteScope(tuple(scope.entities) + tuple(entities), tuple(scope.files) + tuple(files))
        self.record["write_scope"] = merged.to_record()


class _Ended(Exception):
    """The walk reached its answer (internal control flow only)."""

    def __init__(self, found: StartProbe) -> None:
        super().__init__(found.code)
        self.found = found


def probe(store: ProjectStore, record: dict[str, Any], pending: list[dict[str, Any]]) -> tuple[str, dict[str, str]]:
    """RB1's owner probe for owner ``start``: ``(classification, reason)`` for ``record`` among ``pending``."""
    found = inspect(store, record, pending)
    return found.classification, found.reason()


def inspect(store: ProjectStore, record: dict[str, Any], pending: list[dict[str, Any]]) -> StartProbe:
    """The probe, with where START's walk ended and the check ID of its first refusal (for tests and diagnosis).

    Never raises: a walk that cannot finish proves nothing, and is ``unknown_or_invalid``.
    """
    try:
        with read_only_git():
            _Walk(store, record, pending).run()
    except _Ended as ended:
        return ended.found
    except Exception as exc:  # a probe that cannot finish proves nothing
        return StartProbe(
            UNKNOWN_OR_INVALID, NO_PROBE,
            f"START's read-only probe could not finish ({type(exc).__name__}); status does not assume a resume",
            "probe",
        )
    return StartProbe(  # unreachable: every walk ends with _Ended
        UNKNOWN_OR_INVALID, NO_PROBE, "START's read-only probe reached no answer", "probe",
    )


class _Walk:
    """START's control flow for one pending record, step by step, read only (ADM §A.1)."""

    def __init__(self, store: ProjectStore, record: dict[str, Any], pending: list[dict[str, Any]]) -> None:
        from . import start

        self.start = start
        self.store = store
        self.record = record
        self.pending = pending
        self.root = store.root

    # ---------------------------------------------------------------- answers
    def unknown(self, step: str, message: str, code: str = NO_PROBE, check_id: str | None = None) -> _Ended:
        return _Ended(StartProbe(UNKNOWN_OR_INVALID, code, message, step, check_id))

    def resumable(self, step: str, message: str) -> _Ended:
        return _Ended(StartProbe(PENDING_RESUMABLE, "resume_proven", message, step))

    def refused(self, step: str, exc: BaseException) -> _Ended:
        """The record's first refusal, raised by START's own predicate at ``step``: admitted only by check ID."""
        check = getattr(exc, "check_id", None)
        if isinstance(exc, ReconcileRequired) and isinstance(check, str) and check in ALLOW.get(step, frozenset()):
            return _Ended(StartProbe(PENDING_RECONCILE, exc.reason or exc.code, str(exc), step, check))
        if isinstance(exc, _ProbeWouldWrite):
            return self.unknown(step, f"at {step} START would write before it could be shown to resume this record")
        code = getattr(exc, "code", None) or type(exc).__name__
        return self.unknown(
            step,
            f"START's first refusal of this record ({code}, at {step}, check {check or 'none'}) is not a refusal "
            "that reads only the record itself, so status does not claim a reconcile or a resume",
            check_id=check if isinstance(check, str) else None,
        )

    def ask(self, step: str, predicate: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """START's own predicate at ``step``; its refusal ends the walk there."""
        try:
            return predicate(*args, **kwargs)
        except Exception as exc:
            raise self.refused(step, exc) from None

    # ---------------------------------------------------------------- the walk
    def run(self) -> None:
        start = self.start
        record = self.record
        invocation = record["invocation"]

        # S1.1 the probe's domain (RB11FP-1; fixed reasons, RB11RR-7): checked here, since status selects by owner
        operation = invocation.get("operation")
        if operation != start.OWNER:
            fixed = _OTHER_OPERATIONS.get(operation) if isinstance(operation, str) else None
            if fixed is not None:
                raise self.unknown("S1.1", "this START-owned operation has no read-only resume probe; status does "
                                           "not apply START's own predicates to it", fixed)
            raise self.unknown("S1.1", "no read-only proof of how START would resume a record of this operation "
                                       "exists; status does not assume one")

        # S1.2 stage 1a: exactly the legacy key set; a review-v1 record (stage 1b, PO-05 not shown) and any other
        # key set (X-M, X-P) are not probed, nor is a record carrying a Phase integration semantics note (X-I)
        if set(invocation) != LEGACY_KEYS:
            raise self.unknown("S1.2", "START's read-only probe proves only records of a legacy START invocation "
                                       "(exactly operation, work_id and mode)")
        work_id, mode = invocation["work_id"], invocation["mode"]
        if not isinstance(work_id, str) or not isinstance(mode, str):
            raise self.unknown("S1.2", "the record's invocation names its Work or mode in a form a START "
                                       "invocation never takes")
        mutation = _ProbeMutation(MutationController(self.store), copy.deepcopy(record), resumed=True)
        semantics = self.ask("S1.2", start._semantics_of, mutation)
        from .phase_integration import MODE_LEGACY

        if semantics != MODE_LEGACY:
            raise self.unknown("S1.2", "the record runs reviewed Phase integration semantics and may hold a "
                                       "Phase Integration Run; it is never probed")

        # S2.0 the mode gate START makes before the lock (start.py:3629-3630)
        if mode not in start.MODES:
            raise self.unknown("S2.0", "START refuses this record's mode before anything else (validation_failed)")

        # S3.1 the named Work (start.py:3723)
        work = self.ask("S3.1", self.store.read_entity, "work", work_id)
        # S3.3 marker compatibility, over the passed pending set (start.py:3738)
        self.ask("S3.3", start._require_marker_compatible_in, self.pending, work_id, mode, review_contract=None)
        # S3.4 a cancel this START recorded, over the passed pending set (start.py:3746)
        live_invocation = {"operation": start.OWNER, "work_id": work_id, "mode": mode}
        cancel = self.ask("S3.4", start._cancel_to_finish_in, self.store, work, mode, live_invocation, self.pending)
        # S3.5 structure (skipped when a cancel was proven: START judges on the cancel's own view)
        view = cancel.view if cancel is not None else self.ask(
            "S3.5", start._structure_or_stop, self.store, "start precheck")
        # S3.6 the Phase integration entry gate (no selector)
        self.ask("S3.6", start._phase_integration_gate, view.works.get(work_id, work), None, None)
        # S3.7 the RB5PR2-1 fresh check is review-v1 only; S3.8 Git ready and the push destination
        self.ask("S3.8", gitops.ensure_git_ready, self.root)
        destination = self.ask("S3.8", gitops.ensure_push_destination, self.store)

        # S4.1 the recovery-disposition barrier and S4.2 the open checks, over the passed pending set
        from .recovery_disposition import require_no_pending_disposition

        self.ask("S4.1", require_no_pending_disposition, self.pending)
        self.open_checks(work_id, live_invocation)

        # S5 the post-open readers, with START's guards (start.py:3795-3802)
        finishing = holding = None
        derivations: tuple = ()
        moving = None
        if cancel is None:
            finishing = self.ask("S5.1", start._completion_to_finish, mutation, work_id, mode)
            if finishing is None:
                holding = self.ask("S5.2", start._hold_to_finish, mutation, work_id, mode)
            if finishing is None and holding is None:
                derivations = self.ask("S5.3", start._derivations_to_reuse, mutation, work_id, mode)
            if derivations:
                moving = self.ask("S5.4", start._derive_move_to_finish, mutation, derivations)
        # what START notes before its replay (start.py:3803), kept in the probe's copy only
        self.ask("S5.5", gitops.record_preexisting_dirty, mutation, self.root)

        # S6.1 the replay, asked of the Mutation Controller unchanged
        replay = replay_probe(self.store, record)
        if replay.outcome != REPLAY_CLEAR:
            raise self.unknown("S6.1", replay.message, replay.code)
        # S6.2 the replay writes nothing: every recorded effect classifies applied (PO-52, method (b))
        self.replay_writes_nothing(mutation)

        session = start._Session(self.store, mutation, destination, mode, _no_executor, derivations,
                                 semantics=semantics)
        # S7.1 the post-replay dispatch (start.py:3818-3847)
        if cancel is not None:
            self.finish_cancel(session, cancel)
        if finishing is not None:
            self.finish_completion(session, finishing, mode)
        if holding is not None:
            self.finish_hold(session, holding)
        if moving is not None:
            self.finish_move(session, moving, mode)
        current = work
        if mode == "outer":
            latest = self.ask("S7.1", start.ProjectView.load, self.store)
            current, ambiguous = self.ask("S7.1", start._next_or_ambiguous, session, latest, work.phase_id, work, None)
            if ambiguous is not None or current is None:
                raise self.unknown("S7.1", "the outer continuation would stop or finish here instead of running a "
                                           "Work; status does not follow it")
            if session.unreviewable_integration(current) is not None:
                raise self.unknown("S7.1", "the outer continuation would stop before a marked integration here")
        self.run_work(session, mutation, current.id, mode)

    # ---------------------------------------------------------------- S4.2
    def open_checks(self, work_id: str, invocation: dict[str, Any]) -> None:
        """What ``MutationController.open`` refuses for START's open of this invocation, over the passed set."""
        start = self.start
        wanted = json.loads(json.dumps(invocation, sort_keys=True))  # as MutationController.open matches it
        matches = [p for p in self.pending if p["owner"] == start.OWNER and p["invocation"] == wanted]
        others = [p for p in self.pending if p not in matches]
        if len(matches) != 1 or matches[0].get("mutation_id") != self.record.get("mutation_id"):
            raise self.unknown("S4.2", "START's open of this invocation would not resume exactly this record")
        planned = WriteScope(entities=(work_id,), files=start.LEDGER_FILES)
        recorded = WriteScope.from_record(matches[0]["write_scope"])
        planned = WriteScope(tuple(planned.entities) + tuple(recorded.entities),
                             tuple(planned.files) + tuple(recorded.files))
        for other in others:
            other_scope = WriteScope.from_record(other["write_scope"])
            if other_scope.overlaps(planned) or not other_scope.entities and not other_scope.files:
                raise self.unknown("S4.2", "another pending mutation overlaps the write scope START would resume "
                                           "this record with (reconcile_required at open)")

    # ---------------------------------------------------------------- S6.2
    def replay_writes_nothing(self, mutation: _ProbeMutation) -> None:
        """PO-52 method (b): every recorded effect classifies applied, so the replay writes nothing to the Project.

        Each effect is classified exactly as the replay classifies it (``_classify_recorded``, the predicate
        ``Mutation.apply`` and ``replay_probe`` use), against the Project as it is: an UNAPPLIED one is a write
        the replay would make, after which no read of the Project as it is now shows what START reads. The
        ``applied`` flags alone prove nothing; once every effect is shown applied, the probe's copy holds them
        all applied, as the replay's own save leaves the record.
        """
        effects = list(self.record.get("effects") or [])
        controller = MutationController(self.store)
        for position in range(len(effects)):
            try:
                classification = _classify_recorded(controller, effects, position, self.record)
            except Exception as exc:
                raise self.unknown("S6.2", f"a recorded effect cannot be classified here ({type(exc).__name__})",
                                   POST_REPLAY_NOT_READ_ONLY) from None
            if classification != MATCHING:
                raise self.unknown("S6.2", "replaying this record would write to the Project before START goes on, "
                                           "so nothing after the replay is evaluated", POST_REPLAY_NOT_READ_ONLY)
        for effect in mutation.record.get("effects") or []:
            effect["applied"] = True

    # ---------------------------------------------------------------- S7.1 finish paths
    def would_commit(self, session: Any, mutation: _ProbeMutation, prefix: str) -> bool:
        """The local refusals of ``_Session._commit`` and ``gitops.finalize`` before the stage is recorded.

        True when the commit would be recorded - the next domain step; False when there is nothing to commit
        (START records no stage and goes on). The publication barrier is not evaluated: it is a publication
        precondition, excluded from the claim (ADM §A.1 S7.1 (i)).
        """
        stage, to_commit = self.ask("S7.1", self.start._commit_plan, self.store, mutation, prefix, [])
        if not to_commit:
            return False
        if mutation.has_stage(stage):
            raise self.unknown("S7.1", "the finish path's Git stage is recorded already; status does not follow it")
        preexisting = self.ask("S7.1", gitops.record_preexisting_dirty, mutation, self.root)
        self.ask("S7.1", gitops.ensure_separable, preexisting, to_commit)
        return True

    def postcommit(self, session: Any, work_id: str) -> None:
        """``_Session._completion_postcommit``, asked only where it is I/O-free: a record with no Review record."""
        if any(effect.get("kind") == "create_file" for effect in session.mutation.effects):
            raise self.unknown("S7.1", "the completion's postcommit proof reads Review records through Git's class B "
                                       "environment, which status never enters")
        self.ask("S7.1", session._completion_postcommit, work_id)

    def closing(self, step: str) -> _Ended:
        """START's postcheck before it closes the record (start.py:3878-3880): the next domain step."""
        self.ask(step, self.start._structure_or_stop, self.store, "postcheck")
        return self.resumable(step, "START would resume this record and finish it with no refusal before it "
                                    "closes the record")

    def finish_cancel(self, session: Any, cancel: Any) -> None:
        latest = self.ask("S7.1", self.start.ProjectView.load, self.store)
        if cancel.work_id not in latest.works:
            raise self.unknown("S7.1", "the cancelled Work does not resolve where START finishes the cancel")
        if not cancel.committed:
            raise self.unknown("S7.1", "carrying the cancel's replan on is not evaluated read-only here")
        self.postcommit(session, cancel.work_id)
        raise self.closing("S7.1")

    def finish_completion(self, session: Any, work_id: str, mode: str) -> None:
        start = self.start
        latest = self.ask("S7.1", start.ProjectView.load, self.store)
        work = latest.works.get(work_id)
        if work is None:
            raise self.unknown("S7.1", "the completed Work does not resolve where START finalizes it (entity_unresolvable)")
        if self.would_commit(session, session.mutation, f"{work.id}:finalize"):
            raise self.resumable("S7.1", "START would resume this record and record the commit finalizing the "
                                         "completion next, with no refusal before it")
        if latest.work_state(work.id).state != start.COMPLETED:
            raise self.unknown("S7.1", "the Work is not completed after its finalization (postcheck_failed)")
        self.postcommit(session, work.id)
        if mode == "outer":
            raise self.unknown("S7.1", "the outer continuation after the completion is not followed")
        raise self.closing("S7.1")

    def finish_hold(self, session: Any, hold: Any) -> None:
        start = self.start
        latest = self.ask("S7.1", start.ProjectView.load, self.store)
        work = latest.works.get(hold.work_id)
        if work is None:
            raise self.unknown("S7.1", "the held Work does not resolve where START finishes the hold (entity_unresolvable)")
        if not hold.committed and self.would_commit(session, session.mutation, "commit"):
            raise self.resumable("S7.1", "START would resume this record and record the commit carrying the hold "
                                         "next, with no refusal before it")
        if latest.work_state(work.id).state != start.HELD:
            raise self.unknown("S7.1", "the Work is not held after its finalization (postcheck_failed)")
        raise self.closing("S7.1")

    def finish_move(self, session: Any, move: Any, mode: str) -> None:
        latest = self.ask("S7.1", self.start.ProjectView.load, self.store)
        work = latest.works.get(move.work_id)
        if work is None:
            raise self.unknown("S7.1", "the moved Work does not resolve where START finishes the move (entity_unresolvable)")
        if not move.committed and self.would_commit(session, session.mutation, "commit"):
            raise self.resumable("S7.1", "START would resume this record and record the commit carrying the move "
                                         "next, with no refusal before it")
        state = latest.work_state(work.id)
        if state.terminal or state.has_target:
            raise self.unknown("S7.1", "the Work still carries its target after the move (postcheck_failed)")
        if mode == "outer":
            raise self.unknown("S7.1", "the outer continuation after the move is not followed")
        raise self.closing("S7.1")

    # ---------------------------------------------------------------- S7.2 / S7.3 run_work
    def run_work(self, session: Any, mutation: _ProbeMutation, work_id: str, mode: str) -> None:
        """``_Session.run_work``'s complete gate list, in its order (start.py:535-623), up to its next domain step."""
        start = self.start
        view = self.ask("S7.2", start._structure_or_stop, self.store, "start precheck")
        work = view.works.get(work_id)
        if work is None:
            raise self.unknown("S7.2", "the Work does not resolve where START runs it (entity_unresolvable)")
        state = view.work_state(work_id)
        if state.state == start.COMPLETED:
            self.postcommit(session, work_id)
            if mode == "outer":
                raise self.unknown("S7.2", "the outer continuation after the completion is not followed")
            raise self.closing("S7.2")
        if state.terminal:
            raise self.unknown("S7.2", "START does not run a terminal Work (spec_violation)")
        if self.ask("S7.2", start._phase_integration_gate, work, None, None, session.semantics):
            raise self.unknown("S7.2", "START would run the Work's Phase Integration Review here")
        self.ask("S7.2", start._require_work_review_not_closing, view, work, None, mutation)
        opening = not (state.state == start.IN_PROGRESS and state.has_target)
        cycle = () if opening else session._cycle_derivations(work_id)
        phase = view.phases.get(work.phase_id) if work.phase_id else None
        if phase is not None:
            if view.phase_lifecycle(phase.id) != start.ACTIVE:
                raise self.unknown("S7.2", "the Work's Phase is not active (phase_inactive)")
            if view.roadmap_lifecycle(phase.roadmap_id or "") != start.ACTIVE:
                raise self.unknown("S7.2", "the Work's Roadmap is not active (roadmap_inactive)")
        own = self.ask("S7.2", start._own_cycle_dependencies, mutation, view, work, cycle)
        if [(relation, label) for relation, label in view.unsatisfied_dependencies(work_id)
                if own.get(relation.id) != relation.to_record()]:
            raise self.unknown("S7.2", "the Work has unsatisfied dependencies (dependency_unsatisfied)")
        self.ask("S7.2", start.require_read_targets, self.store, view, work)
        self.ask("S7.2", session._protected_read_targets, view, work_id)
        self.ask("S7.2", start.reading_plan, self.store, view, work)
        self.ask("S7.2", gitops.ensure_separable_before_effects, mutation, [start._EVENT_LOG])
        self.ask("S7.2", gitops.narrow_preexisting_dirty, mutation, self.root)
        self.ask("S7.2", mutation.extend_scope, entities=[work_id])
        # START writes _lifecycle next unless the Work is IN_PROGRESS with its target (start.py:601-606)
        if opening:
            raise self.unknown("S7.2", "START would write the Work's lifecycle first; status does not claim past it")
        # S7.3 the first attempt: a recorded derivation of this cycle is replayed (it writes and commits)
        if cycle:
            raise self.unknown("S7.3", "START would replay a recorded derivation of this cycle first; status does "
                                       "not claim past it")
        latest = self.ask("S7.3", start.ProjectView.load, self.store)
        self.ask("S7.3", session._protected_read_targets, latest, work_id)
        kept = self.ask("S7.3", session._refused_result, work_id)
        if kept is not None:
            raise self.unknown("S7.3", "START would finish the Work from the result its refusal kept; status does "
                                       "not follow that path")
        raise self.resumable("S8", "every step START takes before it asks its executor again passes read-only "
                                   "(the executor's result and network publication are not part of this claim)")


def _no_executor(context: Any) -> Any:
    raise _ProbeWouldWrite("the probe never runs an executor")


__all__ = [
    "ALLOW", "LEGACY_KEYS", "NO_PROBE", "NOT_PROBED_GENERATION", "NOT_PROBED_PLAN_EXCLUSION", "PENDING_RECONCILE",
    "PENDING_RESUMABLE", "POST_REPLAY_NOT_READ_ONLY", "StartProbe", "UNKNOWN_OR_INVALID", "inspect", "probe",
]
