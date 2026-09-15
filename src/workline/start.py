"""START (``skills/start``): execute a registered Work to the requested boundary.

START is the operation owner for Work execution: dependency checks,
target / lifecycle events, derived / fix Work creation through CREATE,
integration and human_confirmation handling, cancel with replan, Git
persistence and terminal finalization, and same-Phase continuation in
``outer`` mode. START never crosses into the next Phase.

The actual domain work (and every domain judgement: what to derive, whether
the result is acceptable, ...) is supplied by an ``executor`` callable that
receives an ``ExecutionContext`` and returns an outcome object. START owns
the mechanics: it does not invent Works, relations or integrations beyond
the structural rules the live specification assigns to it.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import stat
from typing import Any, Callable

from . import gitcmd, gitops, yamlish
from .create import RelatedSpec, RelationSpec, WorkSpec, _registration_effects, register_works, resolve_ref
from .errors import ReconcileRequired, SpecViolation, StopError, ValidationError
from .ids import is_valid_id
from .mutation import FILE_EFFECT_KINDS, Effect, Mutation, MutationController, WriteScope, abandon_on_stop
from .oplock import project_operation
from .ops import (
    Replan,
    _as_recorded,
    _own_effects_free_view,
    _owned_paths,
    _plan_exclusion_request,
    _ProvenRecord,
    _recorded_progress,
    _recorded_stages,
    _refuse_before_replay,
    _resume_plan_exclusion,
    apply_replan,
    event_effects,
    owned_canonical_paths,
    plan_replan,
    problems_text,
    projected_view,
    stage_name,
    validate_projection,
)
from .registry import validate_registry
from .state import (
    ACTIVE,
    AMBIGUOUS_CANDIDATES,
    COMPLETED,
    HELD,
    IN_PROGRESS,
    UNSTARTED,
    ProjectView,
    WorkState,
)
from .store import WORK_TERMINAL_EVENTS, WORKLINE_DIR, Entity, ProjectStore, Relation
from .validate import condition_applies, validate_structure

OWNER = "start"
MODES = ("single-work", "outer")
LEDGER_FILES = (
    f"{WORKLINE_DIR}/relations/roadmap.yaml",
    f"{WORKLINE_DIR}/relations/related.yaml",
    f"{WORKLINE_DIR}/events/events.jsonl",
)


# --------------------------------------------------------------------------- outcomes

@dataclass(frozen=True)
class Completed:
    """A finished Work and the changes it owns.

    ``result_paths`` are the files the Work created or modified; they must
    exist when it completes. ``deleted_paths`` are tracked files the Work
    deliberately removed; they must be absent and must have been tracked.
    The two are declared separately on purpose — a result path that has gone
    missing is a failed Work, never an inferred deletion.

    ``deleted_paths`` is last so the existing positional form
    ``Completed(paths, message)`` keeps working.
    """

    result_paths: tuple[str, ...] = ()
    message: str | None = None
    deleted_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuestionWait:
    question: str = ""


@dataclass(frozen=True)
class Hold:
    reason: str = ""


@dataclass(frozen=True)
class Cancel:
    replan: Replan = Replan()
    reason: str = ""


@dataclass(frozen=True)
class DerivedWork:
    name: str
    desired_state: str
    related: tuple[RelatedSpec, ...] = ()
    before_integration: bool = True
    work_kind: str | None = None
    confirmation_target: str | list[str] | None = None
    derivation_detail: str | None = None
    return_to: bool = False


@dataclass(frozen=True)
class Derive:
    """START decided new Works (and optionally a re-integration) while executing."""

    works: dict[str, DerivedWork]
    integration: DerivedWork | None = None
    relations: tuple[RelationSpec, ...] = ()
    move: bool = False


@dataclass(frozen=True)
class HumanNG:
    """human_confirmation judged NG: fix Works + new integration, then return to the same confirmation."""

    fix_works: dict[str, DerivedWork]
    integration: DerivedWork
    relations: tuple[RelationSpec, ...] = ()


Outcome = Completed | QuestionWait | Hold | Cancel | Derive | HumanNG


@dataclass
class ExecutionContext:
    store: ProjectStore
    view: ProjectView
    work: Entity
    state: WorkState
    phase: Entity | None
    roadmap: Entity | None
    reading_plan: list[str]
    mutation_id: str
    mode: str
    attempt: int


Executor = Callable[[ExecutionContext], Outcome]


@dataclass(frozen=True)
class StartResult:
    status: str  # completed | phase_complete | question_wait | held | cancelled | moved | stopped
    work_id: str
    mutation_id: str
    completed_work_ids: tuple[str, ...] = ()
    phase_id: str | None = None
    detail: str = ""
    head: str | None = None


# --------------------------------------------------------------------------- helpers

def _structure_or_stop(store: ProjectStore, context: str) -> ProjectView:
    view = ProjectView.load(store)
    problems = validate_structure(view)
    if problems:
        raise ValidationError(f"{context}: {problems_text(problems)}", code="structure_invalid")
    return view


def _tracked_files(store: ProjectStore) -> list[str]:
    result = gitcmd.run_git(store.root, "ls-files", "-z", check=False)
    return [p.replace("\\", "/") for p in result.stdout.split("\0") if p] if result.ok else []


def read_obligations(
    store: ProjectStore, view: ProjectView, work_id: str, *, tracked: list[str] | None = None
) -> list[Relation]:
    """The Related edges a Work has to read, in the canonical reading order.

    ``must_read``, every ``conditional_must_read`` whose condition currently
    applies, then the ``obey`` chain (``rules/information-tracing``). They are
    *current* obligations only while the Work can still run: the same edges on
    a terminal Work are historical evidence of what that Work had to read when
    it ran, and are never revived as a present duty.
    """
    obligations = list(view.related_from(work_id, "must_read"))
    conditional = view.related_from(work_id, "conditional_must_read")
    if conditional:
        if tracked is None:
            tracked = _tracked_files(store)
        obligations += [r for r in conditional if condition_applies(r.extra.get("condition") or {}, tracked)]
    obligations += view.related_from(work_id, "obey")
    return obligations


def require_read_targets(store: ProjectStore, view: ProjectView, work: Entity) -> None:
    """STOP unless every current read obligation of ``work`` resolves.

    A Work about to run must be able to read what it was told to read. A
    target that is gone is never worked around: no filename, directory, mtime
    or similarity fallback, and no assumption that an old target no longer
    matters (``rules/information-tracing``).
    """
    missing = [r for r in read_obligations(store, view, work.id) if not _ref_resolves(store, r.to)]
    if missing:
        detail = ", ".join(f"{r.type} {r.to} (relation {r.id})" for r in missing)
        raise StopError(f"Work {work.id} cannot resolve what it must read: {detail}", code="related_target_missing")


def reading_plan(store: ProjectStore, view: ProjectView, work: Entity) -> list[str]:
    """Work → Phase → Roadmap → must_read → applicable conditional_must_read → obey chain."""
    plan = [work.path]
    phase = view.phases.get(work.phase_id) if work.phase_id else None
    if phase is not None:
        plan.append(phase.path)
        roadmap = view.roadmaps.get(phase.roadmap_id or "")
        if roadmap is not None:
            plan.append(roadmap.path)
    return plan + [relation.to for relation in read_obligations(store, view, work.id)]


def _ref_resolves(store: ProjectStore, target: str) -> bool:
    if target.startswith("workline://"):
        root = store.workline_root()
        return validate_registry(root).ok and target[len("workline://"):] in _registry_ids(root)
    return (store.root / target).exists()


def _registry_ids(root) -> set[str]:
    from .registry import _extract_id_blocks

    try:
        return set(_extract_id_blocks((root / "registry.md").read_text(encoding="utf-8")))
    except OSError:
        return set()


def _result_message(message: str | None, work: Entity) -> str:
    """The message a Work's result commit carries.

    An executor that has something to say says it, and that string is committed
    exactly as given - not stripped, prefixed, retyped or checked against any
    commit convention. Saying nothing is the same however it is spelled: no
    message, an empty one, or only whitespace all fall back to the neutral
    default, because none of them tells a reader anything the default does not.
    The emptiness test is the only thing that strips; it never reaches the
    message that gets committed.

    Blank strings are the only thing this adds to the truthiness test it
    replaces, and nothing else changes meaning. A falsy value still falls back
    to the default as it always did. A truthy value that is not a string is
    still handed on unchanged, so the commit effect's own validation refuses it
    exactly as before - it is neither promoted to a valid message here nor
    refused by a new check of its own.
    """
    if not message:
        return f"chore(workline): {work.display} {work.name}"
    if isinstance(message, str) and not message.strip():
        return f"chore(workline): {work.display} {work.name}"
    return message


def completion_precheck(
    store: ProjectStore,
    view: ProjectView,
    work: Entity,
    result_paths: tuple[str, ...],
    deleted_paths: tuple[str, ...] = (),
) -> None:
    """Work completion precheck (mechanically checkable part of the spec list).

    The Work's changed set is ``result_paths | deleted_paths``, so deleting a
    ``must_update`` target counts as having updated it. ``realizes`` keeps its
    meaning untouched: it asks whether the target exists, so a deletion can
    never satisfy it.
    """
    problems: list[str] = []
    paths = set(result_paths) | set(deleted_paths)
    for relation in view.related_from(work.id, "must_update"):
        if relation.to not in paths:
            problems.append(f"must_update not satisfied: {relation.to}")
    for relation in view.related_from(work.id, "conditional_must_update"):
        condition = relation.extra.get("condition") or {}
        if condition_applies(condition, sorted(paths)) and relation.to not in paths:
            problems.append(f"conditional_must_update not satisfied: {relation.to}")
    for relation in view.related_from(work.id, "realizes"):
        if not _ref_resolves(store, relation.to):
            problems.append(f"realizes target does not exist: {relation.to}")
    unsatisfied = view.unsatisfied_dependencies(work.id)
    if unsatisfied:
        problems.append("unresolved required dependency: " + ", ".join(r.from_id for r, _ in unsatisfied))
    for path in result_paths:
        if not (store.root / path).exists():
            problems.append(f"result path missing: {path}")
    overlap = sorted(set(result_paths) & set(deleted_paths))
    if overlap:
        problems.append("declared both as a result and as a deletion: " + ", ".join(overlap))
    for path in deleted_paths:
        if (store.root / path).exists():
            problems.append(f"deleted path still exists: {path}")
        if not gitcmd.tracked_file(store.root, path):
            # never tracked, or a directory standing in for the files under it
            problems.append(f"deleted path is not a tracked file: {path}")
    # The session refuses such a removal right after the executor returns, where it can
    # still put the file back; this keeps the condition true for a direct caller too.
    problems.extend(_deletion_blocked_by_readers(store, view, work.id, deleted_paths))
    structural = validate_structure(view)
    if structural:
        problems.append("structure invalid: " + problems_text(structural))
    if problems:
        raise StopError("completion precheck failed: " + "; ".join(problems), code="completion_precheck_failed")


def _deletion_blocked_by_readers(
    store: ProjectStore, view: ProjectView, work_id: str, deleted_paths: tuple[str, ...]
) -> list[str]:
    """Started Works, other than this one, that currently must read a path this Work deletes.

    Workline does not create the state its own rule then refuses to run in: a
    Work that entered execution and has not finished still needs what it was
    told to read. The deleting Work itself is not one of them, since it started
    while the target was there. Unstarted Works are future plan, maintained
    through the Roadmap route, and a terminal Work's edges are historical
    evidence, which a later deletion never invalidates.
    """
    if not deleted_paths:
        return []
    targets = set(deleted_paths)
    tracked = _tracked_files(store)
    problems: list[str] = []
    for other_id in sorted(view.works):
        if other_id == work_id:
            continue
        state = view.work_state(other_id)
        if state.terminal or state.state == UNSTARTED:
            continue
        for relation in read_obligations(store, view, other_id, tracked=tracked):
            if relation.to in targets:
                problems.append(
                    f"deleted path {relation.to} is a current read target of {other_id} "
                    f"({relation.type}, relation {relation.id})"
                )
    return problems


def standalone_scope(view: ProjectView, work_id: str) -> list[Entity]:
    """Standalone Works connected to ``work_id`` through roadmap relations."""
    seen = {work_id}
    queue = [work_id]
    while queue:
        current = queue.pop()
        for relation in view.roadmap_relations:
            for other in (relation.from_id, relation.to):
                if other in seen or other not in view.works or view.works[other].phase_id is not None:
                    continue
                if current in (relation.from_id, relation.to):
                    seen.add(other)
                    queue.append(other)
    return [view.works[w] for w in sorted(seen)]


# --------------------------------------------------------------------------- START

class _Session:
    def __init__(
        self,
        store: ProjectStore,
        mutation: Mutation,
        destination: gitops.PushDestination | None,
        mode: str,
        executor: Executor,
    ) -> None:
        self.store = store
        self.mutation = mutation
        # The push destination START verified at its entry; every commit this
        # session finalizes pushes there or nowhere.
        self.destination = destination
        self.mode = mode
        self.executor = executor
        self.completed: list[str] = []

    # git ---------------------------------------------------------------
    def _commit(self, prefix: str, message: str, paths: list[str], *, include_canonical: bool = True) -> None:
        stage = stage_name(self.mutation, prefix)
        owned = sorted(set(paths) | (set(owned_canonical_paths(self.mutation)) if include_canonical else set()))
        dirty = gitcmd.changed_against_head(self.store.root, owned)
        to_commit = sorted(p for p in owned if p in dirty)
        if not to_commit:
            return
        gitops.finalize(self.mutation, stage, message, to_commit, destination=self.destination)

    def _lifecycle(self, work: Entity, types: list[str]) -> None:
        if not types:
            return
        stage = stage_name(self.mutation, f"{work.id}:lifecycle")
        self.mutation.add_effects(stage, event_effects(self.mutation, stage, work.id, types))
        self.mutation.apply()

    # single Work cycle -------------------------------------------------------
    def run_work(self, work_id: str) -> StartResult:
        view = _structure_or_stop(self.store, "start precheck")
        work = view.works.get(work_id)
        if work is None:
            raise ValidationError(f"Work unresolvable: {work_id}", code="entity_unresolvable")
        state = view.work_state(work_id)
        if state.state == COMPLETED:
            # Only a resumed START gets here, once replaying its recorded finalization has
            # committed and pushed the completion; one whose finalization was never
            # recorded is finished before any Work is run (:func:`_completion_to_finish`).
            return StartResult("completed", work_id, self.mutation.id, phase_id=work.phase_id)
        if state.terminal:
            raise SpecViolation(f"Work {work_id} is {state.state}; terminal Works are not started")
        phase = view.phases.get(work.phase_id) if work.phase_id else None
        if phase is not None:
            if view.phase_lifecycle(phase.id) != ACTIVE:
                raise StopError(f"Phase {phase.id} is {view.phase_lifecycle(phase.id)}", code="phase_inactive")
            if view.roadmap_lifecycle(phase.roadmap_id or "") != ACTIVE:
                raise StopError(f"Roadmap {phase.roadmap_id} is {view.roadmap_lifecycle(phase.roadmap_id or '')}", code="roadmap_inactive")
        unsatisfied = view.unsatisfied_dependencies(work_id)
        if unsatisfied:
            raise StopError(
                f"Work {work_id} has unresolved requires_completion: " + ", ".join(f"{r.from_id} ({label})" for r, label in unsatisfied),
                code="dependency_unsatisfied",
            )
        require_read_targets(self.store, view, work)
        # Refuse here, before this Work writes anything, when a target another started
        # Work must read could not be put back if this execution removed it.
        self._protected_read_targets(view, work_id)
        plan = reading_plan(self.store, view, work)
        self.mutation.extend_scope(entities=[work_id])

        # target / lifecycle ---------------------------------------------------
        if state.state == UNSTARTED:
            self._lifecycle(work, ["work_started", "work_target_added"])
        elif state.state == HELD:
            self._lifecycle(work, ["work_resumed", "work_target_added"])
        elif state.state == IN_PROGRESS and not state.has_target:
            self._lifecycle(work, ["work_target_added"])

        attempt = 0
        while True:
            attempt += 1
            view = ProjectView.load(self.store)
            work = view.works[work_id]
            roadmap = view.roadmaps.get(phase.roadmap_id or "") if phase else None
            context = ExecutionContext(self.store, view, work, view.work_state(work_id), phase, roadmap, plan, self.mutation.id, self.mode, attempt)
            protected = self._protected_read_targets(view, work_id)
            try:
                outcome = self.executor(context)
            except BaseException as failure:
                self._put_back_after_failure(protected, failure)
                raise
            self._keep_protected_read_targets(view, work_id, protected)
            if isinstance(outcome, Completed):
                return self._complete(view, work, outcome)
            if isinstance(outcome, QuestionWait):
                return StartResult("question_wait", work_id, self.mutation.id, phase_id=work.phase_id, detail=outcome.question)
            if isinstance(outcome, Hold):
                self._lifecycle(work, ["work_target_removed", "work_held"])
                self._commit("commit", f"chore(workline): hold {work.display}", [])
                return StartResult("held", work_id, self.mutation.id, phase_id=work.phase_id, detail=outcome.reason, head=gitcmd.head_commit(self.store.root))
            if isinstance(outcome, Cancel):
                return self._cancel(view, work, outcome)
            if isinstance(outcome, Derive):
                self._derive(view, work, outcome)
                if outcome.move:
                    self._lifecycle(work, ["work_target_removed"])
                    self._commit("commit", f"chore(workline): branch from {work.display}", [])
                    return StartResult("moved", work_id, self.mutation.id, phase_id=work.phase_id, head=gitcmd.head_commit(self.store.root))
                self._commit("commit", f"chore(workline): derive from {work.display}", [])
                continue
            if isinstance(outcome, HumanNG):
                self._human_ng(view, work, outcome)
                self._lifecycle(work, ["work_target_removed"])
                self._commit("commit", f"chore(workline): {work.display} NG; fix planned", [])
                return StartResult("moved", work_id, self.mutation.id, phase_id=work.phase_id, head=gitcmd.head_commit(self.store.root))
            raise ValidationError(f"executor returned an unknown outcome: {outcome!r}")

    # protected read targets -------------------------------------------------
    def _protected_read_targets(self, view: ProjectView, work_id: str) -> dict[str, tuple[bytes, int]]:
        """What other started Works must currently read, as it stands before the executor runs.

        Only what this rule protects: the current read obligations of Works that
        entered execution and have not finished. The content comes from the
        working tree, not from Git, so uncommitted local content is what would
        be put back. A ``workline://`` target is not a file this execution can
        delete, and a target that is already gone is the reader's own STOP
        rather than this Work's doing; neither is carried here.

        A target that exists but could not be put back the same way — a
        directory, a link, a file that cannot be read — STOPs the Work here,
        before it writes or runs anything, instead of after an executor has
        destroyed it.
        """
        snapshot: dict[str, tuple[bytes, int]] = {}
        tracked = _tracked_files(self.store)
        for other_id in sorted(view.works):
            if other_id == work_id:
                continue
            state = view.work_state(other_id)
            if state.terminal or state.state == UNSTARTED:
                continue
            for relation in read_obligations(self.store, view, other_id, tracked=tracked):
                if relation.to in snapshot or relation.to.startswith("workline://"):
                    continue
                target = self.store.root / relation.to
                if not target.exists():
                    continue
                if target.is_symlink():
                    reason = "it is a link"
                elif target.is_dir():
                    reason = "it is a directory"
                else:
                    try:
                        snapshot[relation.to] = (target.read_bytes(), target.stat().st_mode)
                        continue
                    except OSError as exc:
                        reason = f"it cannot be read ({exc.strerror or exc})"
                raise StopError(
                    f"Work {work_id} cannot run while {other_id} must read {relation.to} "
                    f"(relation {relation.id}): {reason}, so Workline could not put it back "
                    "if this execution removed it",
                    code="related_target_unprotectable",
                )
        return snapshot

    def _put_back_protected(self, snapshot: dict[str, tuple[bytes, int]]) -> tuple[list[str], list[str]]:
        """Write back the protected targets that are gone; return what was and was not put back.

        Exactly the protected paths that disappeared are written, byte for byte
        as they stood when the executor started. Nothing else in the working
        tree is read, restored or reverted, and Git is not asked to check
        anything out.
        """
        restored: list[str] = []
        unrestored: list[str] = []
        for path in sorted(snapshot):
            target = self.store.root / path
            if target.exists():
                continue
            content, mode = snapshot[path]
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                os.chmod(target, stat.S_IMODE(mode))
                restored.append(path)
            except OSError:
                unrestored.append(path)
        return restored, unrestored

    def _keep_protected_read_targets(
        self, view: ProjectView, work_id: str, snapshot: dict[str, tuple[bytes, int]]
    ) -> None:
        """Put back what this execution removed from another started Work, then STOP.

        Refusing the Work is not enough: the Project must not be left without a
        file another started Work still has to read.
        """
        restored, unrestored = self._put_back_protected(snapshot)
        lost = sorted(restored + unrestored)
        if not lost:
            return
        detail = "; ".join(_deletion_blocked_by_readers(self.store, view, work_id, tuple(lost)))
        message = f"Work {work_id} removed what another started Work must read: {detail}"
        if restored:
            message += "; put back as it stood before this execution: " + ", ".join(restored)
        if unrestored:
            message += "; could not be put back: " + ", ".join(unrestored)
        raise StopError(message, code="related_target_removed")

    def _put_back_after_failure(self, snapshot: dict[str, tuple[bytes, int]], failure: BaseException) -> None:
        """Put back what a failed execution removed, without taking over its failure.

        The executor failing is its own outcome and keeps its own meaning, so a
        successful put-back says nothing and lets that failure travel on. Only
        when the Project cannot be put back does it become a STOP of its own,
        raised from the original failure so that neither is hidden.
        """
        _, unrestored = self._put_back_protected(snapshot)
        if unrestored:
            raise StopError(
                "the Work failed and Workline could not put back what another started Work must read: "
                + ", ".join(unrestored),
                code="related_target_unrestored",
            ) from failure

    # completion ------------------------------------------------------------
    def _complete(self, view: ProjectView, work: Entity, outcome: Completed) -> StartResult:
        result_paths = tuple(p.replace("\\", "/") for p in outcome.result_paths)
        deleted_paths = tuple(p.replace("\\", "/") for p in outcome.deleted_paths)
        completion_precheck(self.store, view, work, result_paths, deleted_paths)
        # Created, modified and deleted results are one owned set: they are
        # protected from pre-existing changes together and finalized in the
        # same commit, by exact path.
        owned = sorted(set(result_paths) | set(deleted_paths))
        if owned:
            preexisting = gitops.record_preexisting_dirty(self.mutation, self.store.root)
            gitops.ensure_separable(preexisting, owned)
            # Without an executor-supplied message the default stays neutral:
            # whether a result is a feature, a fix or documentation is the
            # executor's product judgement, and Workline never infers it from
            # the Work name or kind. A blank message says nothing, so it means
            # the same as supplying none - whitespace alone is not a message a
            # commit could carry, and refusing it would strand the finished Work
            # rather than describe it. Only that emptiness test strips: a
            # message with anything in it is committed exactly as given.
            self._commit(f"{work.id}:results", _result_message(outcome.message, work), owned, include_canonical=False)
        self._lifecycle(work, ["work_target_removed", "work_completed"])
        return self._finalize_completion(work)

    def _finalize_completion(self, work: Entity) -> StartResult:
        """The Git stage of a completion: the commit carrying its events, the push, the postcheck."""
        self._commit(f"{work.id}:finalize", f"chore(workline): complete {work.display}", [])
        after = ProjectView.load(self.store)
        if after.work_state(work.id).state != COMPLETED:
            raise StopError(f"{work.id} is not completed after finalization", code="postcheck_failed")
        self.completed.append(work.id)
        return StartResult("completed", work.id, self.mutation.id, tuple(self.completed), work.phase_id, head=gitcmd.head_commit(self.store.root))

    def finish_completion(self, work_id: str) -> StartResult:
        """Finalize a completion this mutation recorded and applied, doing none of it again.

        The Work's result is committed and its ``work_target_removed`` /
        ``work_completed`` events are in the event log, but the commit that
        carries them was never recorded. What is left is exactly the Git stage
        (``skills/start``: Terminal finalization): the executor is not asked
        again, no event is added, and nothing else is chosen or run first.
        """
        work = ProjectView.load(self.store).works.get(work_id)
        if work is None:
            raise ValidationError(f"Work unresolvable: {work_id}", code="entity_unresolvable")
        return self._finalize_completion(work)

    # cancel ----------------------------------------------------------------
    def _cancel(self, view: ProjectView, work: Entity, outcome: Cancel) -> StartResult:
        state = view.work_state(work.id)
        prefix = stage_name(self.mutation, f"{work.id}:cancel")
        work_ids, removals, additions = plan_replan(self.mutation, prefix, view, outcome.replan)
        events = [(work.id, "work_target_removed")] if state.has_target else []
        events.append((work.id, "work_cancelled"))
        projection = projected_view(
            view,
            add_events=events,
            remove_relation_ids=tuple(r.id for r in removals),
            add_relations=additions,
            add_works={work_ids[k]: spec for k, spec in outcome.replan.new_works.items()},
        )
        validate_projection(projection, "cancel replan")
        decision = _cancel_decision(work.id, prefix, outcome, removals)
        self._record_cancel(work, [t for _, t in events], decision)
        return self._carry_cancel(work, prefix, outcome.replan, removals, additions, work_ids, outcome.reason)

    def _record_cancel(self, work: Entity, types: list[str], decision: dict[str, Any]) -> None:
        """Record the cancel's lifecycle events together with the decision that made them, then apply them.

        The decision rides on the ``work_cancelled`` effect, so it is durable in
        exactly the save that records the terminal events - the save in which the
        Mutation Controller also records the branch they are decided on
        (``rules/git``: Commit / push). No record holds the events without their
        decision, and once they exist nothing a resume needs is left with the
        executor.
        """
        stage = stage_name(self.mutation, f"{work.id}:lifecycle")
        effects = event_effects(self.mutation, stage, work.id, types)
        effects[-1] = Effect(effects[-1].kind, {**effects[-1].payload, _CANCEL_DECISION: decision})
        self.mutation.add_effects(stage, effects)
        self.mutation.apply()

    def _carry_cancel(
        self,
        work: Entity,
        prefix: str,
        replan: Replan,
        removals: list[Relation],
        additions: list[Relation],
        work_ids: dict[str, str],
        reason: object,
    ) -> StartResult:
        """Everything of a cancel after its lifecycle events: the replan, the structural validation, the commit."""
        apply_replan(self.mutation, prefix, replan, removals, additions, work_ids)
        _structure_or_stop(self.store, "cancel structural validation")
        self._commit("commit", f"chore(workline): cancel {work.display}", [])
        return StartResult("cancelled", work.id, self.mutation.id, tuple(self.completed), work.phase_id, reason, gitcmd.head_commit(self.store.root))

    def finish_cancel(self, cancel: "_ProvenCancel") -> StartResult:
        """Carry a cancel this mutation recorded through what is left of it, deciding none of it again.

        The record was shown to hold the cancel's decision and only effects that
        decision makes, and replaying it applied every effect already recorded
        (:func:`_cancel_to_finish`). The executor is not asked; the prefix, the
        IDs, the removals and a recorded registration come from the record; and
        the rest is recorded from the decision exactly as the uninterrupted cancel
        records it. A commit recorded already is done once replayed. The outcome
        is the cancel's own: ``cancelled``, with the reason it was decided for,
        and nothing is chosen or run after it.
        """
        work = ProjectView.load(self.store).works[cancel.work_id]
        if cancel.committed:
            return StartResult(
                "cancelled", work.id, self.mutation.id, tuple(self.completed), work.phase_id, cancel.reason,
                gitcmd.head_commit(self.store.root),
            )
        return self._carry_cancel(
            work, cancel.prefix, cancel.replan, cancel.removals, cancel.additions, cancel.work_ids, cancel.reason
        )

    # derived / fix Works -----------------------------------------------------
    def _derive(self, view: ProjectView, work: Entity, outcome: Derive) -> dict[str, str]:
        if not outcome.works and outcome.integration is None:
            raise ValidationError("Derive without Works")
        for key in outcome.works:
            if key == "integration":
                raise ValidationError("reserved Work key: integration")
        phase_id = work.phase_id
        roadmap_id = view.phases[phase_id].roadmap_id if phase_id else None
        specs: dict[str, WorkSpec] = {}
        relations: list[RelationSpec] = []
        for key, derived in outcome.works.items():
            specs[key] = WorkSpec(
                derived.name,
                derived.desired_state,
                phase_id=phase_id,
                roadmap_id=roadmap_id,
                work_kind=derived.work_kind,
                confirmation_target=derived.confirmation_target,
                related=tuple(derived.related),
                derivation_detail=derived.derivation_detail,
            )
            relations.append(RelationSpec("derived", work.id, key))
            if derived.return_to:
                relations.append(RelationSpec("return_to", key, work.id))
        normal_keys = [k for k, d in outcome.works.items() if d.work_kind is None]
        if phase_id is not None:
            unfinished = view.unfinished_integrations(phase_id)
            if len(unfinished) >= 2:
                raise SpecViolation(f"Phase {phase_id} has {len(unfinished)} unfinished integrations: structural anomaly, STOP")
            if outcome.integration is not None:
                if unfinished:
                    raise SpecViolation("an unfinished integration already exists; START must not create another")
                specs["integration"] = WorkSpec(
                    outcome.integration.name,
                    outcome.integration.desired_state,
                    phase_id=phase_id,
                    roadmap_id=roadmap_id,
                    work_kind="phase_integration_check",
                    related=tuple(outcome.integration.related),
                    derivation_detail=outcome.integration.derivation_detail,
                )
                relations.append(RelationSpec("derived", work.id, "integration"))
                for key in normal_keys:
                    if outcome.works[key].before_integration:
                        relations.append(RelationSpec("requires_completion", key, "integration"))
            elif normal_keys:
                if len(unfinished) == 1:
                    for key in normal_keys:
                        if outcome.works[key].before_integration:
                            relations.append(RelationSpec("requires_completion", key, unfinished[0].id))
                else:
                    raise StopError(
                        f"Phase {phase_id} has no unfinished integration; START must design a re-integration for the new Work(s)",
                        code="reintegration_required",
                    )
        elif outcome.integration is not None:
            raise SpecViolation("standalone Works have no phase integration")
        relations += list(outcome.relations)
        stage = stage_name(self.mutation, f"{work.id}:derive")
        result = register_works(self.mutation, stage, specs, relations)
        return result.work_ids

    def _human_ng(self, view: ProjectView, work: Entity, outcome: HumanNG) -> dict[str, str]:
        if work.work_kind != "human_confirmation":
            raise SpecViolation("HumanNG applies to human_confirmation Works only")
        if not outcome.fix_works:
            raise ValidationError("HumanNG needs at least one fix Work")
        relations = [RelationSpec("requires_completion", "integration", work.id)]
        relations += list(outcome.relations)
        derive = Derive(dict(outcome.fix_works), outcome.integration, tuple(relations), move=True)
        return self._derive(view, work, derive)

    # continuation ------------------------------------------------------------
    def next_work(self, view: ProjectView, phase_id: str | None, entry: Entity, just_completed: str | None) -> Entity | None:
        works = view.effective_works(phase_id) if phase_id else standalone_scope(view, entry.id)
        inflight = [w for w in works if view.work_state(w.id).state == IN_PROGRESS and view.work_state(w.id).has_target]
        if len(inflight) > 1:
            raise StopError("multiple Works carry a target: " + ", ".join(w.id for w in inflight), code="multiple_targets")
        if inflight:
            return inflight[0]
        startable = view.startable_works(phase_id, works if phase_id is None else None)
        # a Work that a still-active branch plans to return to waits for that branch
        pending_returns = {
            r.to for r in view.roadmap_relations
            if r.type == "return_to" and r.from_id in view.works and not view.work_state(r.from_id).terminal
        }
        startable = [w for w in startable if w.id not in pending_returns] or startable
        # The plan decides which Work comes next. When it leaves several equally
        # planned, the continuation STOPs instead of separating them by the order
        # they were read in.
        return view.choose_startable(startable, "Work")


def _next_or_ambiguous(
    session: "_Session", view: ProjectView, phase_id: str | None, entry: Entity, just_completed: str | None
) -> tuple[Entity | None, str | None]:
    """The next Work, or the reason the continuation cannot choose one.

    An ambiguous continuation is a STOP, but the Work that just finished was
    committed legitimately and its finalization mutation still has to close. So
    the ambiguity comes back as a stop reason to return, not as an exception
    that would leave the mutation pending behind a decision nobody made.
    """
    try:
        return session.next_work(view, phase_id, entry, just_completed), None
    except StopError as exc:
        if exc.code != AMBIGUOUS_CANDIDATES:
            raise
        return None, exc.message


_EVENT_LOG = f"{WORKLINE_DIR}/events/events.jsonl"
_COMPLETION_EVENTS = ("work_target_removed", "work_completed")


def _completion_to_finish(mutation: Mutation, work_id: str, mode: str) -> str | None:
    """The Work whose recorded completion a resumed START finalizes before anything else, or ``None``.

    A terminal lifecycle stage this START records is finalized by the Git stage
    recorded after it: ``<Work>:finalize:<n>`` for a completion, ``commit:<n>``
    for a cancel. While that stage is missing, the terminal events are in the
    event log, or about to be replayed into it, with nothing committed or
    pushed. Current state already shows the Work completed or cancelled, so a
    retry that read only the state would report success, choose the next Work
    or fold those events into another Work's commit - and close the mutation
    that was the only way left to finalize them.

    So the record is read first, before anything is replayed:

    * no terminal stage without its Git stage - ``None``, and START goes on as
      it always did (a recorded Git stage is replayed like any other effect);
    * an unfinished completion that is provably this START's own - its stage
      holds exactly the two events a completion records for that Work, under
      the IDs reserved for them, it is the last stage recorded, in single-work
      mode it is the invoked Work, and HEAD's event log does not hold those
      events yet - that Work: only its Git stage is left, and it is done
      before anything else;
    * anything else unfinished - more than one unfinished terminal Work, a
      completion recorded in a form this START does not write, or completion
      events HEAD's event log already holds through a commit this mutation did
      not record, which leaves its own finalization commit and push unshown -
      STOP, with the record left exactly as it is.

    A cancel is never finished here. A record holding one is read before the
    mutation is even opened (:func:`_cancel_to_finish`): the cancel is carried on
    from its recorded decision, or START stops there. An unfinished cancel that
    reaches this point was not seen there, and is not taken on trust.
    """
    stages: list[str] = []
    for effect in mutation.effects:
        if effect.get("stage") not in stages:
            stages.append(effect.get("stage"))
    unfinished: list[tuple[int, str, dict]] = []
    for position, stage in enumerate(stages):
        terminal = [
            event for event in _stage_events(mutation, stage)
            if event.get("type") in WORK_TERMINAL_EVENTS and isinstance(event.get("entity"), str)
        ]
        if not terminal:
            continue
        subject, event_type = terminal[0]["entity"], terminal[0]["type"]
        closing = f"{subject}:finalize:" if event_type == "work_completed" else "commit:"
        if not any(str(later).startswith(closing) for later in stages[position + 1:]):
            unfinished.append((position, stage, terminal[0]))
    if not unfinished:
        return None
    if len(unfinished) > 1:
        raise ReconcileRequired(
            f"START mutation {mutation.id} recorded terminal lifecycle events for "
            + ", ".join(sorted({event["entity"] for _, _, event in unfinished}))
            + " that no commit finalizes; START finalizes one Work before it runs another, so this is not a "
            "record it can continue, and it is left pending, exactly as it is: reconcile required"
        )
    position, stage, event = unfinished[0]
    subject, event_type = event["entity"], event["type"]
    if event_type == "work_completed":
        if not (position == len(stages) - 1 and (mode == "outer" or subject == work_id) and _recorded_completion(mutation, stage, subject)):
            raise ReconcileRequired(
                f"START mutation {mutation.id} recorded work_completed for {subject} without the commit that finalizes "
                "it, but not as this START records a completion of that Work, so it cannot show that finalizing it "
                "is its own to do; it is left pending, exactly as it is: reconcile required"
            )
        if _in_head_event_log(mutation.store, [recorded.get("id") for recorded in _stage_events(mutation, stage)]):
            raise ReconcileRequired(
                f"START mutation {mutation.id} recorded the completion of {subject}, but a commit it did not record "
                "already holds those events, so its own finalization commit and push cannot be shown; it is left "
                "pending, exactly as it is: reconcile required"
            )
        return subject
    raise ReconcileRequired(
        f"START mutation {mutation.id} recorded {event_type} for {subject} without the commit that finalizes it, "
        "and not as a cancel this START has shown from its record, so it can neither finish it nor go on past it "
        "to report another outcome; it is left pending, exactly as it is: reconcile required"
    )


def _stage_events(mutation: Mutation, stage: str) -> list[dict]:
    """The event records of ``stage``'s ``append_event`` effects, in recorded order."""
    events: list[dict] = []
    for effect in mutation.stage_effects(stage):
        payload = effect.get("payload")
        record = payload.get("record") if effect.get("kind") == "append_event" and isinstance(payload, dict) else None
        if isinstance(record, dict):
            events.append(record)
    return events


def _recorded_completion(mutation: Mutation, stage: str, work_id: str) -> bool:
    """Whether ``stage`` is exactly the lifecycle stage a completion of ``work_id`` records."""
    effects = mutation.stage_effects(stage)
    events = _stage_events(mutation, stage)
    return (
        isinstance(stage, str)
        and stage.rsplit(":", 1)[0] == f"{work_id}:lifecycle"
        and [effect.get("kind") for effect in effects] == ["append_event"] * len(_COMPLETION_EVENTS)
        and [(event.get("type"), event.get("entity")) for event in events] == [(t, work_id) for t in _COMPLETION_EVENTS]
        and all(mutation.reserved(f"{stage}:event:{index}") == event.get("id") for index, event in enumerate(events))
    )


def _in_head_event_log(store: ProjectStore, event_ids: list[str]) -> bool:
    """Whether the event log committed in HEAD holds any of ``event_ids``; a question Git cannot answer counts as yes."""
    patterns = [arg for event_id in event_ids for arg in ("-e", str(event_id))]
    found = gitcmd.run_git(store.root, "grep", "-q", "-F", *patterns, "HEAD", "--", _EVENT_LOG, check=False)
    return found.returncode != 1


# --------------------------------------------------------------------------- cancel decision
#
# A cancel is decided by the executor, not by START's caller: which new Works
# replace the cancelled one, which relations are added and removed, and why, all
# come back as its outcome. START records that decision on the ``work_cancelled``
# effect, in the save that records the cancel's lifecycle events, and a retry of
# the same START carries the cancel on from the record alone - never by asking
# the executor again, and never by reading the decision back out of the Project.
# Where the retry may replay and record is not decided here: the Mutation
# Controller allows it only on the branch the cancel was decided on, and the
# recorded commit's own branch rules from its Git stage on (``rules/git``:
# Commit / push).

#: The key of the ``work_cancelled`` effect's payload under which a cancel's decision is recorded.
_CANCEL_DECISION = "cancel"
_CANCEL_DECISION_VERSION = 1
_DECISION_FIELDS = frozenset({"version", "work_id", "prefix", "reason", "new_works", "add_relations", "remove_relations"})
_NEW_WORK_FIELDS = frozenset({
    "key", "name", "desired_state", "phase_id", "roadmap_id", "work_kind", "confirmation_target", "related",
    "derivation_detail",
})
_RELATED_FIELDS = frozenset({"type", "to", "condition"})
_ADDITION_FIELDS = frozenset({"type", "from", "to"})
_EVENT_FIELDS = frozenset({"id", "type", "entity", "at"})
#: The lifecycle events a cancel records, in the order it records them.
_CANCEL_EVENTS = (["work_cancelled"], ["work_target_removed", "work_cancelled"])


def _cancel_decision(work_id: str, prefix: str, outcome: Cancel, removals: list[Relation]) -> dict[str, Any]:
    """What a START cancel decided, exactly as its recovery record reads it back - or the refusal.

    Everything a resume needs that no effect recorded with the cancel's events
    holds: the Work, the prefix its replan stages are recorded under, the reason,
    the new Works and the relations to add exactly as the executor gave them
    (declared order, endpoints as written - a key and the ID it is reserved as
    are different decisions), and every relation to remove as the Project held
    it when the cancel was decided. The lifecycle events are not repeated - the
    decision rides on them - and neither are the IDs reserved for the replan,
    which the record keeps under keys this decision determines.

    Nothing is normalised or translated, because a resume rebuilds from it the
    replan the uninterrupted cancel carries on with. The decision is therefore
    recorded only when the record reads every part of it back as the same value
    of the same kind. A part it cannot keep - a float, a tuple, an object, a
    nested list, text holding a lone surrogate UTF-8 cannot write -
    refuses the cancel here, before anything of it is recorded, rather than
    leaving a cancel that could be finished only if nothing interrupted it. So
    does a decision a resume would not read as one (:func:`_decision_problem`),
    such as a new Work whose name is not text, which the registration would
    refuse only after the cancel's events were applied.
    """
    replan = outcome.replan
    try:
        decision = {
            "version": _CANCEL_DECISION_VERSION,
            "work_id": work_id,
            "prefix": prefix,
            "reason": outcome.reason,
            "new_works": [
                {
                    "key": key,
                    "name": spec.name,
                    "desired_state": spec.desired_state,
                    "phase_id": spec.phase_id,
                    "roadmap_id": spec.roadmap_id,
                    "work_kind": spec.work_kind,
                    "confirmation_target": spec.confirmation_target,
                    "related": [{"type": r.type, "to": r.to, "condition": r.condition} for r in spec.related],
                    "derivation_detail": spec.derivation_detail,
                }
                for key, spec in replan.new_works.items()
            ],
            "add_relations": [{"type": r.type, "from": r.from_ref, "to": r.to_ref} for r in replan.add_relations],
            "remove_relations": [relation.to_record() for relation in removals],
        }
    except (AttributeError, TypeError) as exc:
        raise ValidationError(
            f"cancel decision: the replan is not one a cancel decision can record ({exc}); a cancel is recorded only "
            "together with everything it decided, so nothing of it is recorded"
        ) from exc
    kept = _read_back(decision)
    if kept is _UNKEPT:
        where, value = _unkept_part(decision, "cancel")
        raise ValidationError(
            f"cancel decision: {where} ({type(value).__name__}) cannot be kept exactly by the recovery record; a "
            "cancel is recorded only together with everything it decided, so nothing of it is recorded"
        )
    # Only a decision a resume can read back as one is recorded: what the registration would refuse anyway is refused
    # here, before the cancel's events, instead of after them.
    problem = _decision_problem(kept)
    if problem is not None:
        raise ValidationError(
            f"cancel decision: {problem}; a cancel is recorded only together with everything it decided, so nothing "
            "of it is recorded"
        )
    return kept


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


_UNKEPT = object()


def _read_back(value: object) -> object:
    """``value`` as a recovery record reads it back once written, or :data:`_UNKEPT` when that is not exactly ``value``.

    Written and read the way the record itself is (``yamlish``, UTF-8), and
    compared with the kind of every part, keys included (:func:`_typed`).
    """
    try:
        text = yamlish.dump({"value": value})
        text.encode("utf-8")
        kept = yamlish.load(text)["value"]
        if _typed(kept) == _typed(value):
            return kept
    except (yamlish.YamlishError, TypeError, ValueError, KeyError, RecursionError):
        pass
    return _UNKEPT


def _typed(value: object) -> object:
    """``value`` spelled out with the kind of each part, so that ``True`` is not ``1``, nor ``1`` the key ``"1"``."""
    if value is None or isinstance(value, bool):
        return [type(value).__name__, value]
    if isinstance(value, int):
        return ["int", int(value)]
    if isinstance(value, str):
        return ["str", str(value)]
    if isinstance(value, dict):
        return ["dict", [[_typed(key), _typed(item)] for key, item in value.items()]]
    if isinstance(value, list):
        return ["list", [_typed(item) for item in value]]
    raise TypeError(f"{type(value).__name__} is not a value a recovery record keeps")


def _unkept_part(value: object, where: str) -> tuple[str, object]:
    """The innermost part of ``value`` a recovery record does not keep exactly, and where it is."""
    if isinstance(value, dict):
        parts = [(f"{where}.{key}", item) for key, item in value.items()]
    elif isinstance(value, list):
        parts = [(f"{where}[{index}]", item) for index, item in enumerate(value)]
    else:
        parts = []
    for part, item in parts:
        if _read_back(item) is _UNKEPT:
            return _unkept_part(item, part)
    return where, value


@dataclass(frozen=True)
class _ProvenCancel:
    """An interrupted cancel of exactly this START, shown from its record, and what carrying it on still needs."""

    mutation_id: str
    work_id: str
    prefix: str
    reason: object
    replan: Replan
    work_ids: dict[str, str]
    additions: list[Relation]
    removals: list[Relation]
    committed: bool  # the commit carrying the cancel is recorded: replaying the record finishes it
    view: ProjectView  # the Project without the cancel's own applied effects: what the decision was made on


@dataclass(frozen=True)
class _CancelRecord:
    """The stages of a START record and its one cancel, read with nothing assumed."""

    effects: list[dict[str, Any]]
    stages: list[str]
    by_stage: dict[str, list[dict[str, Any]]]
    stage: str
    position: int
    work_id: str
    events: list[dict[str, Any]]
    reserved: dict[str, Any]
    decision: object

    @property
    def types(self) -> list[str]:
        return [event["type"] for event in self.events]


def _cancel_to_finish(store: ProjectStore, entry: Entity, mode: str) -> _ProvenCancel | None:
    """The cancel an interrupted run of exactly this START recorded and a retry carries on, or ``None``.

    Read before anything is judged on the current Project, before the mutation
    is opened and before any recorded effect is replayed, because a cancel that
    stopped part-way leaves a Project this START would otherwise refuse or
    misread: its own ``work_cancelled`` makes the Work terminal, a relation its
    replan was about to remove can still point at the cancelled Work, and a
    commit already recorded would be replayed before anything else. Every step
    reads only, and whatever refuses leaves the record, the Project and Git
    exactly as they are:

    * no unfinished START of this Work and mode holds a cancel - ``None``, and
      START goes on as it always did (a recovery area that cannot be read proves
      nothing here and is reported where it always was, when the mutation is
      opened);
    * several unfinished STARTs of this Work and mode - ``reconcile required``;
    * a cancel recorded without its decision, as every cancel was before START
      recorded one - ``reconcile required``, whether or not its commit is
      recorded too: what it decided is never read back out of the Project, the
      events, the commit or the reservations;
    * :func:`_prove_cancel` - the decision is in the form START records it, it
      cancels this START's Work under its own prefix and reservations, every
      stage recorded after it is exactly what it makes, and what was applied is
      consistent with the order it was recorded in;
    * :func:`_decide_cancel` - the decision judged again, as START judged it, on
      the Project without the cancel's own applied effects;
    * ``ops._refuse_before_replay`` - what is still to come refused the way
      recording and applying it would refuse, before any of it runs.
    """
    invocation = {"operation": OWNER, "work_id": entry.id, "mode": mode}
    try:
        records = [
            record for record in MutationController(store).list_pending()
            if record["owner"] == OWNER and record["invocation"] == invocation
        ]
    except ReconcileRequired:
        return None
    if not any(_cancel_event(effect) is not None for record in records for effect in _effects_of(record)):
        return None
    if len(records) > 1:
        raise ReconcileRequired(
            f"{len(records)} unfinished START mutations of {entry.id} ({mode}) "
            + ", ".join(sorted(record["mutation_id"] for record in records))
            + ", and one of them recorded a cancel; START carries on exactly one, and they are left as they are: "
            "reconcile required"
        )
    (record,) = records
    refuse = _cancel_refusal(record)
    read = _read_cancel_record(record, refuse)
    proven, cancel = _prove_cancel(store, record, read, entry, mode, refuse)
    view = _decide_cancel(proven, read, cancel, refuse)
    own = {read.stage, *_replan_stages(cancel.prefix, cancel.replan)}
    _refuse_before_replay(
        store, OWNER, record, proven, cancel.replan, cancel.removals,
        prefix=cancel.prefix,
        context="cancel replan",
        committing=[effect for effect in proven.file_effects if effect["stage"] in own],
    )
    return _ProvenCancel(
        record["mutation_id"], read.work_id, cancel.prefix, read.decision["reason"], cancel.replan, cancel.work_ids,
        cancel.additions, cancel.removals, cancel.committed, view,
    )


def _effects_of(record: dict[str, Any]) -> list[Any]:
    effects = record.get("effects")
    return effects if isinstance(effects, list) else []


def _cancel_event(effect: object) -> dict[str, Any] | None:
    """The ``work_cancelled`` event an effect records, or ``None``."""
    payload = effect.get("payload") if isinstance(effect, dict) and effect.get("kind") == "append_event" else None
    event = payload.get("record") if isinstance(payload, dict) else None
    return event if isinstance(event, dict) and event.get("type") == "work_cancelled" else None


def _cancel_refusal(record: dict[str, Any]) -> Callable[[str], ReconcileRequired]:
    def refuse(reason: str) -> ReconcileRequired:
        return ReconcileRequired(
            f"START mutation {record['mutation_id']} recorded a cancel, but its record holds {reason}; nothing shows "
            "that carrying it on does what that cancel decided, and it is left pending, exactly as it is: "
            "reconcile required"
        )

    return refuse


def _read_cancel_record(record: dict[str, Any], refuse) -> _CancelRecord:
    """The record's stages and its one cancel stage with the decision on it, when both are in the form START records them."""
    effects = record.get("effects")
    if not isinstance(effects, list) or not all(
        isinstance(effect, dict)
        and isinstance(effect.get("stage"), str)
        and isinstance(effect.get("kind"), str)
        and isinstance(effect.get("payload"), dict)
        for effect in effects
    ):
        raise refuse("effects that cannot be read")
    stages = _recorded_stages(effects, refuse)
    cancelled = [effect for effect in effects if _cancel_event(effect) is not None]
    if len(cancelled) != 1:
        raise refuse("more than one work_cancelled event; START cancels one Work and then stops")
    (cancel_effect,) = cancelled
    stage = cancel_effect["stage"]
    if _CANCEL_DECISION not in cancel_effect["payload"]:
        raise ReconcileRequired(
            f"START mutation {record['mutation_id']} recorded the cancel of {_cancel_event(cancel_effect).get('entity')} "
            "without the decision that cancel made: it was written before START recorded what a cancel decides, so "
            "neither its replan nor its outcome can be shown, and nothing stands in for them - not the Project, the "
            "events, a recorded commit or the IDs it reserved; it is left pending, exactly as it is: reconcile required"
        )
    by_stage = {name: [effect for effect in effects if effect["stage"] == name] for name in stages}
    lifecycle = by_stage[stage]
    events = [effect["payload"].get("record") for effect in lifecycle]
    if not all(
        effect["kind"] == "append_event"
        and isinstance(event, dict)
        and set(event) == _EVENT_FIELDS
        and all(isinstance(event[field], str) and event[field] for field in _EVENT_FIELDS)
        for effect, event in zip(lifecycle, events)
    ):
        raise refuse(f"a cancel stage {stage!r} holding something other than lifecycle events")
    work_id = events[-1]["entity"]
    if (
        [event["type"] for event in events] not in _CANCEL_EVENTS
        or any(event["entity"] != work_id for event in events)
        or not is_valid_id(work_id, "work")
    ):
        raise refuse(f"a cancel stage {stage!r} holding other events than the cancel of one Work records")
    position = stages.index(stage)
    number = len({name for name in stages[:position] if name.startswith(f"{work_id}:lifecycle:")})
    if stage != f"{work_id}:lifecycle:{number}":
        raise refuse(f"a cancel stage named {stage!r}, where the cancel of {work_id} records it as its next lifecycle stage")
    reserved = record.get("reserved_ids")
    if not isinstance(reserved, dict):
        raise refuse("reservations that are not a mapping")
    if any(reserved.get(f"{stage}:event:{index}") != event["id"] for index, event in enumerate(events)):
        raise refuse("cancel events under IDs the cancel did not reserve for them")
    if any(set(effect["payload"]) != {"record"} for effect in lifecycle[:-1]) or set(lifecycle[-1]["payload"]) != {
        "record", _CANCEL_DECISION
    }:
        raise refuse("cancel events carrying something other than the decision on the work_cancelled event")
    return _CancelRecord(
        effects, stages, by_stage, stage, position, work_id, events, reserved, lifecycle[-1]["payload"][_CANCEL_DECISION]
    )


def _decision_problem(decision: object) -> str | None:
    """What makes ``decision`` other than a cancel decision START records, or ``None``.

    The form is the one :func:`_cancel_decision` records, and it refuses to
    record any other: text where registering a Work or a relation needs text,
    and any value the record keeps where the executor may hand one - a reason,
    and a new Work's key and the endpoints and confirmation targets that name
    one.
    """
    if not isinstance(decision, dict) or set(decision) != _DECISION_FIELDS:
        return "fields other than a cancel decision's"
    if type(decision["version"]) is not int or decision["version"] != _CANCEL_DECISION_VERSION:
        return f"version {decision['version']!r}, which this START does not read"
    if not isinstance(decision["work_id"], str) or not isinstance(decision["prefix"], str):
        return "a Work or a prefix that is not text"
    new_works, additions, removals = decision["new_works"], decision["add_relations"], decision["remove_relations"]
    if not isinstance(new_works, list) or not all(_decided_work(work) for work in new_works):
        return "new Works in another form than a cancel decision records them"
    keys = [work["key"] for work in new_works]
    if len(set(keys)) != len(keys) or len({_canonical(key) for key in keys}) != len(keys):
        return "one new Work key decided twice"
    if not isinstance(additions, list) or not all(
        isinstance(addition, dict)
        and set(addition) == _ADDITION_FIELDS
        and isinstance(addition["type"], str)
        and _names_one(addition["from"])
        and _names_one(addition["to"])
        for addition in additions
    ):
        return "relations to add in another form than a cancel decision records them"
    if not isinstance(removals, list) or not all(_decided_removal(removal) for removal in removals):
        return "relations to remove in another form than a cancel decision records them"
    return None


def _names_one(value: object) -> bool:
    """Whether ``value`` can name a Work - by its ID or by a new Work's key - as a record keeps it."""
    return value is None or isinstance(value, (str, int))


def _decided_work(work: object) -> bool:
    if not isinstance(work, dict) or set(work) != _NEW_WORK_FIELDS:
        return False
    target = work["confirmation_target"]
    return (
        _names_one(work["key"])
        and isinstance(work["name"], str)
        and isinstance(work["desired_state"], str)
        and all(work[field] is None or isinstance(work[field], str) for field in ("phase_id", "roadmap_id", "work_kind", "derivation_detail"))
        and (_names_one(target) or isinstance(target, list) and all(_names_one(item) for item in target))
        and isinstance(work["related"], list)
        and all(
            isinstance(related, dict)
            and set(related) == _RELATED_FIELDS
            and isinstance(related["type"], str)
            and isinstance(related["to"], str)
            and (related["condition"] is None or isinstance(related["condition"], dict))
            for related in work["related"]
        )
    )


def _decided_removal(removal: object) -> bool:
    return (
        isinstance(removal, dict)
        and all(isinstance(removal.get(part), str) and removal[part] for part in ("id", "type", "from", "to"))
        and is_valid_id(removal["id"], "relation")
        and removal["type"] != "derived"
        and Relation.from_record(removal).to_record() == removal
    )


def _decided_replan(decision: dict[str, Any]) -> Replan:
    """The replan a proven decision records, rebuilt as the executor gave it."""
    return Replan(
        remove_relation_ids=tuple(removal["id"] for removal in decision["remove_relations"]),
        add_relations=tuple(RelationSpec(addition["type"], addition["from"], addition["to"]) for addition in decision["add_relations"]),
        new_works={
            work["key"]: WorkSpec(
                work["name"],
                work["desired_state"],
                phase_id=work["phase_id"],
                roadmap_id=work["roadmap_id"],
                work_kind=work["work_kind"],
                confirmation_target=work["confirmation_target"],
                related=tuple(RelatedSpec(related["type"], related["to"], related["condition"]) for related in work["related"]),
                derivation_detail=work["derivation_detail"],
            )
            for work in decision["new_works"]
        },
    )


def _replan_stages(prefix: str, replan: Replan) -> list[str]:
    """The stages a cancel's replan records after its lifecycle stage, in the order it records them (``ops.apply_replan``)."""
    stages = [f"{prefix}:works"] if replan.new_works else [f"{prefix}:relations"] if replan.add_relations else []
    if replan.remove_relation_ids:
        stages.append(f"{prefix}:remove")
    return stages


@dataclass(frozen=True)
class _DecidedCancel:
    prefix: str
    replan: Replan
    work_ids: dict[str, str]
    additions: list[Relation]
    removals: list[Relation]
    committed: bool


def _prove_cancel(
    store: ProjectStore, record: dict[str, Any], read: _CancelRecord, entry: Entity, mode: str, refuse
) -> tuple[_ProvenRecord, _DecidedCancel]:
    """Show the decision, and every effect recorded with and after it, are what that decision makes for this START."""
    decision = read.decision
    problem = _decision_problem(decision)
    if problem is not None:
        raise refuse(f"a cancel decision with {problem}")
    work_id, stages, reserved, position = read.work_id, read.stages, read.reserved, read.position
    if decision["work_id"] != work_id:
        raise refuse(f"a decision to cancel {decision['work_id']} on the events cancelling {work_id}")
    current = ProjectView.load(store)
    work = current.works.get(work_id)
    if work is None:
        raise refuse(f"the cancel of {work_id}, which does not resolve")
    if mode == "single-work" and work_id != entry.id:
        raise refuse(f"the cancel of {work_id}, where this single-work START runs {entry.id} alone")
    if work.phase_id != entry.phase_id:
        raise refuse(f"the cancel of {work_id}, outside the scope this START runs from {entry.id}")

    # stages: the prefix is the one the cancel recorded its replan under, and only what the decision records follows
    prefix = decision["prefix"]
    expected_prefix = f"{work_id}:cancel:{len({name for name in stages[:position] if name.startswith(f'{work_id}:cancel:')})}"
    if prefix != expected_prefix:
        raise refuse(f"the replan prefix {prefix!r}, where the cancel records its replan under {expected_prefix!r}")
    replan = _decided_replan(decision)
    works_stage, relations_stage, remove_stage = f"{prefix}:works", f"{prefix}:relations", f"{prefix}:remove"
    replanned = _replan_stages(prefix, replan)
    after = stages[position + 1:]
    if after[: len(replanned)] != replanned[: len(after)]:
        raise refuse(f"the stages {after} after the cancel stage, where its decision records {replanned} in that order")
    committed = len(after) > len(replanned)
    commit_stage: str | None = None
    if committed:
        commit_stage = f"commit:{len({name for name in stages[: position + 1 + len(replanned)] if name.startswith('commit:')})}"
        if after[len(replanned):] != [commit_stage]:
            raise refuse(f"the stages {after} after the cancel stage, where its decision records {replanned} and then its commit")
    for index, name in enumerate(stages[:position]):
        for effect in read.by_stage[name]:
            event = effect["payload"].get("record") if effect["kind"] == "append_event" else None
            if not isinstance(event, dict) or event.get("type") not in WORK_TERMINAL_EVENTS:
                continue
            if event.get("type") != "work_completed" or not any(
                later.startswith(f"{event.get('entity')}:finalize:") for later in stages[index + 1: position]
            ):
                raise refuse(f"a terminal lifecycle stage {name!r} no commit finalized before the cancel")

    # reservations: the decision's keys name them, and the IDs are never decided again
    def reserved_id(key: str, kind: str) -> str:
        value = reserved.get(key)
        if not isinstance(value, str) or not is_valid_id(value, kind):
            raise refuse(f"no {kind} ID reserved under {key!r}")
        return value

    work_ids = {key: reserved_id(f"{works_stage}:work:{key}", "work") for key in replan.new_works}
    relation_stage = works_stage if replan.new_works else relations_stage
    relation_ids = [reserved_id(f"{relation_stage}:rel:{index}", "relation") for index in range(len(replan.add_relations))]
    used = list(work_ids.values()) + relation_ids + [event["id"] for event in read.events]
    if len(set(used)) != len(used):
        raise refuse("one reserved ID used for two things the decision makes")
    additions = [
        Relation(relation_ids[index], spec.type, resolve_ref(spec.from_ref, work_ids), resolve_ref(spec.to_ref, work_ids))
        for index, spec in enumerate(replan.add_relations)
    ]
    removals = [Relation.from_record(removal) for removal in decision["remove_relations"]]

    # recorded replan stages: exactly what the decision records, under its reservations
    if works_stage in read.by_stage:
        related_ids = {
            (key, index): reserved_id(f"{works_stage}:related:{key}:{index}", "relation")
            for key, spec in replan.new_works.items()
            for index in range(len(spec.related))
        }
        derivation_ids = {
            key: reserved_id(f"{works_stage}:der:{key}", "derivation")
            for key, spec in replan.new_works.items()
            if spec.derivation_detail is not None
        }
        # The Works the Project held when the stage was recorded: while this mutation is pending, its new Works are the
        # only ones registered since.
        base_number = len(current.works) - sum(1 for identifier in work_ids.values() if identifier in current.works)
        try:
            expected = _registration_effects(replan.new_works, work_ids, additions, related_ids, derivation_ids, base_number)
        except (AttributeError, TypeError, ValueError) as exc:
            raise refuse(f"new Works the registration cannot write ({exc})") from exc
        if _as_recorded(read.by_stage[works_stage]) != _as_recorded(expected):
            raise refuse(f"a {works_stage} stage other than the registration its decision makes")
    if relations_stage in read.by_stage:
        if _as_recorded(read.by_stage[relations_stage]) != _as_recorded(Effect.add_relation("roadmap", r) for r in additions):
            raise refuse(f"a {relations_stage} stage other than the relations its decision adds")
    if remove_stage in read.by_stage:
        if _as_recorded(read.by_stage[remove_stage]) != _as_recorded(Effect.remove_relation("roadmap", r) for r in removals):
            raise refuse(f"a {remove_stage} stage other than the removals its decision makes")
    file_effects = [effect for effect in read.effects if effect["kind"] in FILE_EFFECT_KINDS]
    finalize = read.by_stage[commit_stage] if committed else None
    if finalize is not None:
        try:
            owned = set(_owned_paths(file_effects))
        except (KeyError, TypeError) as exc:
            raise refuse(f"file effects that cannot be read ({exc})") from exc
        commit = finalize[0]["payload"]
        paths = commit.get("paths")
        if (
            [effect["kind"] for effect in finalize] not in (["git_commit"], ["git_commit", "git_push"])
            or commit.get("message") != f"chore(workline): cancel {work.display}"
            or not isinstance(paths, list)
            or not paths
            or not all(isinstance(path, str) for path in paths)
            or not set(paths) <= owned
        ):
            raise refuse(f"a {commit_stage} stage other than the commit carrying the cancel")

    # progress: what was applied is what the record says was done first, and only its last stage can be part-way
    applied, unapplied = _recorded_progress(store, file_effects, stages[-1], committed, refuse)
    if not committed and _in_head_event_log(store, [event["id"] for event in read.events]):
        raise ReconcileRequired(
            f"START mutation {record['mutation_id']} recorded the cancel of {work_id}, but a commit it did not record "
            "already holds those events, so its own commit and push cannot be shown; it is left pending, exactly as "
            "it is: reconcile required"
        )
    proven = _ProvenRecord(
        dict(reserved), read.effects, read.by_stage, current, work_ids, additions,
        removals if remove_stage in read.by_stage else None, finalize, file_effects, applied, unapplied,
    )
    return proven, _DecidedCancel(prefix, replan, work_ids, additions, removals, committed)


def _decide_cancel(proven: _ProvenRecord, read: _CancelRecord, cancel: _DecidedCancel, refuse) -> ProjectView:
    """The decision judged again as START judged it, on the Project without the cancel's own applied effects.

    START's precheck, the Work the cancel found, the relations it removes and
    the owner projection of the whole replan read that Project - the one the
    decision was made on - so the cancel's own events, Works, additions and
    removals are neither held against it nor counted twice. What other stages of
    the same START applied before the cancel stays: the cancel was decided on it.
    """
    own = {read.stage, *_replan_stages(cancel.prefix, cancel.replan)}
    view = _own_effects_free_view(proven.current, [effect for effect in proven.applied if effect["stage"] in own])
    work_id, types = read.work_id, read.types
    state = view.work_state(work_id)
    if state.state != IN_PROGRESS or state.has_target != ("work_target_removed" in types):
        raise refuse(
            f"a cancel of {work_id} as it never stood: without the cancel it is {state.state} "
            f"{'with' if state.has_target else 'without'} a target"
        )
    problems = validate_structure(view)
    if problems:
        raise ValidationError(f"start precheck: {problems_text(problems)}", code="structure_invalid")
    standing = {relation.id: relation for relation in view.roadmap_relations}
    for removal in cancel.removals:
        if removal.id not in standing or standing[removal.id].to_record() != removal.to_record():
            raise refuse(f"relation {removal.id} to remove, which the Project no longer holds as the cancel found it")
    validate_projection(
        projected_view(
            view,
            add_events=[(work_id, event_type) for event_type in types],
            remove_relation_ids=tuple(relation.id for relation in cancel.removals),
            add_relations=cancel.additions,
            add_works={cancel.work_ids[key]: spec for key, spec in cancel.replan.new_works.items()},
        ),
        "cancel replan",
    )
    return view


def start(store: ProjectStore, work_id: str, mode: str, executor: Executor) -> StartResult:
    if mode not in MODES:
        raise ValidationError(f"mode must be one of {MODES}: {mode!r}")
    # Project execution lock (rules/git): everything that decides a write is read
    # under it, the executor runs inside it, and it is released when START
    # returns. A question wait releases it too; the mutation stays pending for
    # the invocation that resumes it under a fresh lock.
    with project_operation(store, OWNER, {"work_id": work_id, "mode": mode}):
        return _start_locked(store, work_id, mode, executor)


def _start_locked(store: ProjectStore, work_id: str, mode: str, executor: Executor) -> StartResult:
    work = store.read_entity("work", work_id)  # stable resolve; no fallback
    # A cancel an interrupted run of this START recorded is answered from its record first: the current Project
    # shows that cancel part-way, and is judged as it stood when the cancel was decided.
    cancel = _cancel_to_finish(store, work, mode)
    view = cancel.view if cancel is not None else _structure_or_stop(store, "start precheck")
    gitops.ensure_git_ready(store.root)
    # Before the mutation exists: an unpinned or drifted push destination STOPs
    # here, with no intent record, no domain write and no network contact.
    destination = gitops.ensure_push_destination(store)

    controller = MutationController(store)
    # invocation identity = the required START inputs (stable Work ID and mode);
    # a pending START mutation on the same Work with another mode is a conflict → reconcile required
    invocation = {"operation": OWNER, "work_id": work_id, "mode": mode}
    mutation = controller.open(OWNER, invocation, WriteScope(entities=(work_id,), files=LEDGER_FILES))
    with abandon_on_stop(mutation):
        if cancel is not None and mutation.id != cancel.mutation_id:
            raise ReconcileRequired(
                f"START resumed mutation {mutation.id}, not {cancel.mutation_id} whose cancel it had shown; both are "
                "left as they are: reconcile required"
            )
        # A terminal lifecycle this mutation recorded without its finalization is
        # answered from the record before anything is replayed or chosen.
        finishing = _completion_to_finish(mutation, work_id, mode) if mutation.resumed and cancel is None else None
        gitops.record_preexisting_dirty(mutation, store.root)
        mutation.apply()  # resume: replay every recorded effect before continuing
        state = view.work_state(work_id)
        if state.terminal and not mutation.resumed:
            raise SpecViolation(f"Work {work_id} is {state.state}")

        session = _Session(store, mutation, destination, mode, executor)
        phase_id = work.phase_id
        current: Entity | None = work
        result: StartResult
        just_completed: str | None = None
        if cancel is not None:
            # The cancel ends this START as it would have uninterrupted: no other Work is chosen or run after it.
            result = session.finish_cancel(cancel)
        elif finishing is not None:
            result = session.finish_completion(finishing)
        elif mutation.resumed:
            ambiguous: str | None = None
            if mode == "outer":
                current, ambiguous = _next_or_ambiguous(session, ProjectView.load(store), phase_id, work, None)
            if ambiguous is not None:
                result = StartResult("stopped", work_id, mutation.id, phase_id=phase_id, detail=ambiguous)
            elif current is None:
                result = StartResult("completed", work_id, mutation.id, phase_id=phase_id)
            else:
                result = session.run_work(current.id)
        else:
            result = session.run_work(work.id)

    while mode == "outer" and result.status in ("completed", "moved"):
        just_completed = result.work_id if result.status == "completed" else None
        view = ProjectView.load(store)
        if phase_id is not None:
            completion = view.phase_completion(phase_id)
            if completion.complete:
                result = StartResult("phase_complete", work_id, mutation.id, tuple(session.completed), phase_id, head=gitcmd.head_commit(store.root))
                break
        nxt, ambiguous = _next_or_ambiguous(session, view, phase_id, work, just_completed)
        if ambiguous is not None:
            result = StartResult("stopped", work_id, mutation.id, tuple(session.completed), phase_id, ambiguous, gitcmd.head_commit(store.root))
            break
        if nxt is None:
            detail = "; ".join(view.phase_completion(phase_id).reasons) if phase_id else "no startable Work in standalone scope"
            result = StartResult("stopped", work_id, mutation.id, tuple(session.completed), phase_id, detail, gitcmd.head_commit(store.root))
            break
        if result.status == "moved" and nxt.id == result.work_id:
            raise StopError(f"outer continuation makes no progress: {nxt.id} was re-selected right after branching", code="no_progress")
        result = session.run_work(nxt.id)

    if result.status != "question_wait":
        _structure_or_stop(store, "postcheck")
        mutation.complete()
    return StartResult(result.status, result.work_id, mutation.id, tuple(session.completed), phase_id, result.detail, result.head)


# --------------------------------------------------------------------------- standalone plan exclusion

def plan_exclude_standalone_work(store: ProjectStore, work_id: str, replan: Replan = Replan()):
    """START-owned plan exclusion of an unstarted standalone Work."""
    with project_operation(store, "start-plan-exclude", {"work_id": work_id}):
        return _plan_exclude_standalone_locked(store, work_id, replan)


def _plan_exclude_standalone_locked(store: ProjectStore, work_id: str, replan: Replan):
    def precheck(view: ProjectView) -> None:
        work = view.works.get(work_id)
        if work is None:
            raise ValidationError(f"Work unresolvable: {work_id}")
        if work.phase_id is not None:
            raise SpecViolation("Phase Work plan exclusion is owned by Roadmap")
        if view.work_state(work_id).state != UNSTARTED:
            raise SpecViolation(f"plan_excluded is only for unstarted Works; {work_id} is {view.work_state(work_id).state}")

    def message(view: ProjectView) -> str:
        return f"chore(workline): plan_excluded {view.works[work_id].display}"

    # Resumed exactly as Roadmap's plan exclusion is (``roadmap._plan_exclude_locked``). The slot names this
    # operation, not START's own invocation: a START record of the same Work is never taken for one of these, and
    # START's own resume (:func:`_completion_to_finish`) reads only the mutation ``_start_locked`` opens.
    slot = {"operation": "start-plan-exclude", "work_id": work_id}
    request = _plan_exclusion_request(work_id, replan)
    resumed = _resume_plan_exclusion(store, OWNER, slot, work_id, replan, request, precheck, message)
    if resumed is not None:
        view = resumed.view
    else:
        view = _structure_or_stop(store, "precheck")
        precheck(view)
    destination = gitops.ensure_push_destination(store)
    controller = MutationController(store)
    mutation = controller.open(OWNER, {**slot, "request": request}, WriteScope(entities=(work_id,), files=LEDGER_FILES))
    gitops.ensure_git_ready(store.root)
    gitops.record_preexisting_dirty(mutation, store.root)
    mutation.apply()
    if resumed is not None:
        work_ids, removals, additions = resumed.work_ids, resumed.removals, resumed.additions
    else:
        with abandon_on_stop(mutation):
            work_ids, removals, additions = plan_replan(mutation, "replan", view, replan)
            projection = projected_view(
                view,
                add_events=[(work_id, "plan_excluded")],
                remove_relation_ids=tuple(r.id for r in removals),
                add_relations=additions,
                add_works={work_ids[k]: spec for k, spec in replan.new_works.items()},
            )
            validate_projection(projection, "plan exclusion replan")
    if not mutation.has_stage("event"):
        mutation.add_effects("event", event_effects(mutation, "event", work_id, ["plan_excluded"]))
    mutation.apply()
    apply_replan(mutation, "replan", replan, removals, additions, work_ids)
    gitops.finalize(
        mutation,
        "finalize",
        message(view),
        owned_canonical_paths(mutation),
        destination=destination,
    )
    _structure_or_stop(store, "postcheck")
    mutation.complete()
    return StartResult("plan_excluded", work_id, mutation.id, head=gitcmd.head_commit(store.root))


__all__ = [
    "Completed", "QuestionWait", "Hold", "Cancel", "DerivedWork", "Derive", "HumanNG", "ExecutionContext",
    "StartResult", "start", "plan_exclude_standalone_work", "reading_plan", "read_obligations",
    "require_read_targets", "completion_precheck", "standalone_scope",
]
