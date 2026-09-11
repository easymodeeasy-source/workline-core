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
from typing import Callable

from . import gitcmd, gitops
from .create import RelatedSpec, RelationSpec, WorkSpec, register_works
from .errors import SpecViolation, StopError, ValidationError
from .mutation import Mutation, MutationController, WriteScope, abandon_on_stop
from .oplock import project_operation
from .ops import (
    Replan,
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
from .state import ACTIVE, COMPLETED, HELD, IN_PROGRESS, UNSTARTED, ProjectView, WorkState
from .store import WORKLINE_DIR, Entity, ProjectStore
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


def reading_plan(store: ProjectStore, view: ProjectView, work: Entity) -> list[str]:
    """Work → Phase → Roadmap → must_read → applicable conditional_must_read → obey chain."""
    plan = [work.path]
    phase = view.phases.get(work.phase_id) if work.phase_id else None
    if phase is not None:
        plan.append(phase.path)
        roadmap = view.roadmaps.get(phase.roadmap_id or "")
        if roadmap is not None:
            plan.append(roadmap.path)
    plan += [r.to for r in view.related_from(work.id, "must_read")]
    tracked = _tracked_files(store)
    for relation in view.related_from(work.id, "conditional_must_read"):
        condition = relation.extra.get("condition") or {}
        if condition_applies(condition, tracked):
            plan.append(relation.to)
    plan += [r.to for r in view.related_from(work.id, "obey")]
    return plan


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
    structural = validate_structure(view)
    if structural:
        problems.append("structure invalid: " + problems_text(structural))
    if problems:
        raise StopError("completion precheck failed: " + "; ".join(problems), code="completion_precheck_failed")


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
            outcome = self.executor(context)
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
            self._commit(f"{work.id}:results", outcome.message or f"feat(workline): {work.display} {work.name}", owned, include_canonical=False)
        self._lifecycle(work, ["work_target_removed", "work_completed"])
        self._commit(f"{work.id}:finalize", f"chore(workline): complete {work.display}", [])
        after = ProjectView.load(self.store)
        if after.work_state(work.id).state != COMPLETED:
            raise StopError(f"{work.id} is not completed after finalization", code="postcheck_failed")
        self.completed.append(work.id)
        return StartResult("completed", work.id, self.mutation.id, tuple(self.completed), work.phase_id, head=gitcmd.head_commit(self.store.root))

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
        self._lifecycle(work, [t for _, t in events])
        apply_replan(self.mutation, prefix, outcome.replan, removals, additions, work_ids)
        _structure_or_stop(self.store, "cancel structural validation")
        self._commit("commit", f"chore(workline): cancel {work.display}", [])
        return StartResult("cancelled", work.id, self.mutation.id, tuple(self.completed), work.phase_id, outcome.reason, gitcmd.head_commit(self.store.root))

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
        if not startable:
            return None
        if just_completed:
            planned = {r.to for r in view.relations_from(just_completed, "planned_next")}
            for work in startable:
                if work.id in planned:
                    return work
        return startable[0]


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
    view = _structure_or_stop(store, "start precheck")
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
        if mutation.resumed:
            current = session.next_work(ProjectView.load(store), phase_id, work, None) if mode == "outer" else work
            if current is None:
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
        nxt = session.next_work(view, phase_id, work, just_completed)
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
    view = _structure_or_stop(store, "precheck")
    work = view.works.get(work_id)
    if work is None:
        raise ValidationError(f"Work unresolvable: {work_id}")
    if work.phase_id is not None:
        raise SpecViolation("Phase Work plan exclusion is owned by Roadmap")
    if view.work_state(work_id).state != UNSTARTED:
        raise SpecViolation(f"plan_excluded is only for unstarted Works; {work_id} is {view.work_state(work_id).state}")
    destination = gitops.ensure_push_destination(store)
    controller = MutationController(store)
    mutation = controller.open(OWNER, {"operation": "start-plan-exclude", "work_id": work_id}, WriteScope(entities=(work_id,), files=LEDGER_FILES))
    gitops.ensure_git_ready(store.root)
    gitops.record_preexisting_dirty(mutation, store.root)
    mutation.apply()
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
        f"chore(workline): plan_excluded {work.display}",
        owned_canonical_paths(mutation),
        destination=destination,
    )
    _structure_or_stop(store, "postcheck")
    mutation.complete()
    return StartResult("plan_excluded", work_id, mutation.id, head=gitcmd.head_commit(store.root))


__all__ = [
    "Completed", "QuestionWait", "Hold", "Cancel", "DerivedWork", "Derive", "HumanNG", "ExecutionContext",
    "StartResult", "start", "plan_exclude_standalone_work", "reading_plan", "completion_precheck", "standalone_scope",
]
