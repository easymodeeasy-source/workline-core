"""Roadmap (``skills/roadmap``).

Roadmap is the operation owner for Roadmap meaning, Phase meaning and
relations, startable Phase selection, Phase entry (Work structure, first
integration, structural human_confirmation), future-plan maintenance
(hold / resume / cancel / plan exclusion with replan), Phase addition to an
existing Roadmap, and the explicit Roadmap achievement judgement.
Registration goes through Phase CREATE / CREATE and the Mutation Controller;
Roadmap never executes Works and never lets START cross into the next Phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import gitcmd, gitops
from .create import RelatedSpec, RelationSpec, WorkSpec, register_works
from .errors import SpecViolation, StopError, ValidationError
from .mutation import Effect, Mutation, MutationController, WriteScope, abandon_on_stop
from .ops import (
    Replan,
    apply_replan,
    event_effects,
    owned_canonical_paths,
    plan_replan,
    problems_text,
    projected_view,
    validate_projection,
)
from .phase_create import PhaseRelationSpec, PhaseSpec, register_phases
from .state import ACHIEVED, ACTIVE, CANCELLED, COMPLETE, HELD, PLAN_EXCLUDED, UNSTARTED, ProjectView
from .store import (
    ROADMAP_BACKGROUND_HEADING,
    ROADMAP_DESIRED_HEADING,
    ROADMAP_OUT_OF_SCOPE_HEADING,
    ROADMAP_SCOPE_HEADING,
    WORKLINE_DIR,
    Entity,
    ProjectStore,
    render_body,
    render_entity,
)
from .validate import validate_structure

OWNER = "roadmap"
LEDGER_FILES = (
    f"{WORKLINE_DIR}/relations/roadmap.yaml",
    f"{WORKLINE_DIR}/relations/related.yaml",
    f"{WORKLINE_DIR}/events/events.jsonl",
)


# --------------------------------------------------------------------------- payloads

@dataclass(frozen=True)
class RoadmapPlan:
    name: str
    background: str
    desired_state: str
    phases: dict[str, PhaseSpec]
    relations: tuple[PhaseRelationSpec, ...] = ()
    scope: str | None = None
    out_of_scope: str | None = None


@dataclass(frozen=True)
class RoadmapResult:
    roadmap_id: str
    phase_ids: dict[str, str]
    mutation_id: str
    head: str | None
    resumed: bool


@dataclass(frozen=True)
class PhaseAdditionResult:
    roadmap_id: str
    phase_ids: dict[str, str]
    relation_ids: dict[int, str]
    mutation_id: str
    head: str | None
    resumed: bool


@dataclass(frozen=True)
class WorkDesign:
    name: str
    desired_state: str
    related: tuple[RelatedSpec, ...] = ()


@dataclass(frozen=True)
class PhaseEntryDesign:
    works: dict[str, WorkDesign]
    integration: WorkDesign
    human_confirmation: WorkDesign | None = None
    planned_next: tuple[tuple[str, str], ...] = ()
    requires_completion: tuple[tuple[str, str], ...] = ()
    entry: str | None = None


@dataclass(frozen=True)
class PhaseEntryResult:
    phase_id: str
    work_ids: dict[str, str]
    integration_id: str | None
    confirmation_id: str | None
    entry_work_id: str | None
    expanded: bool
    mutation_id: str | None
    head: str | None


@dataclass(frozen=True)
class OperationResult:
    status: str
    entity_id: str
    mutation_id: str | None
    head: str | None
    detail: str = ""


# --------------------------------------------------------------------------- helpers

def _stop_on_structure(store: ProjectStore, context: str) -> ProjectView:
    view = ProjectView.load(store)
    problems = validate_structure(view)
    if problems:
        raise ValidationError(f"{context}: {problems_text(problems)}", code="structure_invalid")
    return view


def _open(store: ProjectStore, operation: str, identity: dict[str, Any], entities: list[str] = ()) -> Mutation:
    controller = MutationController(store)
    invocation = {"operation": operation, **identity}
    mutation = controller.open(OWNER, invocation, WriteScope(entities=tuple(entities), files=LEDGER_FILES))
    gitops.ensure_git_ready(store.root)
    gitops.record_preexisting_dirty(mutation, store.root)
    mutation.apply()
    return mutation


def _finalize(mutation: Mutation, message: str, extra_paths: list[str] = ()) -> str | None:
    paths = sorted(set(owned_canonical_paths(mutation)) | set(extra_paths))
    gitops.finalize(mutation, "finalize", message, paths, push=True)
    _stop_on_structure(mutation.store, "postcheck")
    mutation.complete()
    return gitcmd.head_commit(mutation.store.root)


def _require_active_roadmap(view: ProjectView, roadmap_id: str) -> None:
    if roadmap_id not in view.roadmaps:
        raise ValidationError(f"Roadmap unresolvable: {roadmap_id}")
    lifecycle = view.roadmap_lifecycle(roadmap_id)
    if lifecycle in (CANCELLED, ACHIEVED):
        raise SpecViolation(f"Roadmap {roadmap_id} is {lifecycle}")
    if lifecycle == HELD:
        raise StopError(f"Roadmap {roadmap_id} is held; resume it first", code="roadmap_held")


# --------------------------------------------------------------------------- new Roadmap

def create_roadmap(store: ProjectStore, plan: RoadmapPlan) -> RoadmapResult:
    if not plan.name.strip() or not plan.background.strip() or not plan.desired_state.strip():
        raise ValidationError("Roadmap needs name, background and desired state")
    if not plan.phases:
        raise ValidationError("a new Roadmap registers all of its Phases; none were decided")
    _stop_on_structure(store, "precheck")
    mutation = _open(store, "roadmap-create", {"name": plan.name})
    with abandon_on_stop(mutation):
        return _create_roadmap(store, mutation, plan)


def _create_roadmap(store: ProjectStore, mutation: Mutation, plan: RoadmapPlan) -> RoadmapResult:
    roadmap_id = mutation.reserve_id("roadmap", "roadmap")
    mutation.extend_scope(entities=[roadmap_id])

    if not mutation.has_stage("roadmap"):
        sections = [(ROADMAP_BACKGROUND_HEADING, plan.background), (ROADMAP_DESIRED_HEADING, plan.desired_state)]
        if plan.scope:
            sections.append((ROADMAP_SCOPE_HEADING, plan.scope))
        if plan.out_of_scope:
            sections.append((ROADMAP_OUT_OF_SCOPE_HEADING, plan.out_of_scope))
        meta = {"id": roadmap_id, "display": f"R-{store.count_entities('roadmap') + 1:02d}", "type": "roadmap"}
        content = render_entity(meta, render_body(plan.name, sections))
        mutation.add_effects("roadmap", [Effect.write_file(ProjectStore.entity_rel_path("roadmap", roadmap_id), content)])
    mutation.apply()

    phases = register_phases(mutation, "phases", roadmap_id, plan.phases, list(plan.relations))
    head = _finalize(mutation, f"chore(workline): create roadmap {ProjectView.load(store).roadmaps[roadmap_id].display}")
    return RoadmapResult(roadmap_id, phases.phase_ids, mutation.id, head, mutation.resumed)


# --------------------------------------------------------------------------- Phase addition

def add_phases(
    store: ProjectStore,
    roadmap_id: str,
    phases: dict[str, PhaseSpec],
    relations: tuple[PhaseRelationSpec, ...] = (),
    *,
    future_plan_change: bool = False,
    invocation_key: str | None = None,
) -> PhaseAdditionResult:
    """Add already-decided Phases to an existing Roadmap (Roadmap operation).

    This is the formal recovery / replan path the achievement check requires
    (``not_achieved`` → add Phases / replan *without* changing the desired
    state). Roadmap owns the mutation, the structural check and the Git
    finalization; Phase CREATE participates as the child registration. The
    Roadmap body is never rewritten and existing Phases / relations are never
    touched: only new Phases and Roadmap-decided Phase relations are added.

    ``relations`` endpoints are spec keys of ``phases`` or existing Phase IDs.
    A cancelled / achieved Roadmap takes no normal Phase addition; a held
    Roadmap follows the existing lifecycle rule and needs a decided
    ``future_plan_change``.
    """
    if not phases:
        raise ValidationError("Phase addition needs at least one decided Phase")
    view = _stop_on_structure(store, "precheck")
    if roadmap_id not in view.roadmaps:
        raise ValidationError(f"Roadmap unresolvable: {roadmap_id}")
    lifecycle = view.roadmap_lifecycle(roadmap_id)
    if lifecycle in (CANCELLED, ACHIEVED):
        raise SpecViolation(f"Roadmap {roadmap_id} is {lifecycle}; no Phase addition")
    display = view.roadmaps[roadmap_id].display

    identity = {
        "roadmap_id": roadmap_id,
        "key": invocation_key or " | ".join(spec.name for spec in phases.values()),
    }
    mutation = _open(store, "roadmap-add-phases", identity, [roadmap_id])
    with abandon_on_stop(mutation):
        registered = register_phases(
            mutation, "phases", roadmap_id, phases, list(relations), future_plan_change=future_plan_change
        )
        head = _finalize(mutation, f"chore(workline): add phases to roadmap {display}")
    return PhaseAdditionResult(
        roadmap_id, registered.phase_ids, registered.relation_ids, mutation.id, head, mutation.resumed
    )


# --------------------------------------------------------------------------- startable Phase

def startable_phases(store: ProjectStore, roadmap_id: str) -> list[Entity]:
    view = _stop_on_structure(store, "precheck")
    _require_active_roadmap(view, roadmap_id)
    return view.startable_phases(roadmap_id)


def select_phase(store: ProjectStore, roadmap_id: str, explicit: str | None = None) -> Entity | None:
    """Select the Phase to enter.

    Returns None only when nothing was explicitly asked for and there is no
    startable candidate (the achievement-check / diagnosis path).
    """
    view = _stop_on_structure(store, "precheck")
    _require_active_roadmap(view, roadmap_id)
    candidates = view.startable_phases(roadmap_id)
    # An explicit Phase is validated first: an invalid explicit choice means the
    # same thing whether or not other candidates exist.
    if explicit is not None:
        for phase in candidates:
            if phase.id == explicit:
                return phase
        raise SpecViolation(f"{explicit} is not a startable Phase")
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    candidate_ids = {phase.id for phase in candidates}
    # planned_next from a completed Phase wins; then a candidate no other candidate plans before it.
    for relation in view.roadmap_relations:
        if relation.type == "planned_next" and relation.to in candidate_ids and view.phase_state(relation.from_id) == COMPLETE:
            return view.phases[relation.to]
    planned_after = {r.to for r in view.roadmap_relations if r.type == "planned_next" and r.from_id in candidate_ids}
    heads = [phase for phase in candidates if phase.id not in planned_after]
    return (heads or candidates)[0]


def diagnose_no_candidate(store: ProjectStore, roadmap_id: str) -> str:
    view = ProjectView.load(store)
    if view.all_active_phases_complete(roadmap_id):
        return "all active Phases complete: run the Roadmap achievement check"
    reasons = []
    for phase in view.active_phases(roadmap_id):
        state = view.phase_state(phase.id)
        if state == COMPLETE:
            continue
        if state == HELD:
            reasons.append(f"{phase.id} held")
        unsatisfied = view.unsatisfied_dependencies(phase.id)
        if unsatisfied:
            reasons.append(f"{phase.id} blocked by " + ", ".join(f"{r.from_id} ({label})" for r, label in unsatisfied))
    return "; ".join(reasons) or "no startable Phase"


# --------------------------------------------------------------------------- Phase entry

def enter_phase(store: ProjectStore, phase_id: str, design: PhaseEntryDesign) -> PhaseEntryResult:
    view = _stop_on_structure(store, "precheck")
    phase = view.phases.get(phase_id)
    if phase is None:
        raise ValidationError(f"Phase unresolvable: {phase_id}")
    roadmap_id = phase.roadmap_id or ""
    _require_active_roadmap(view, roadmap_id)
    state = view.phase_state(phase_id)
    if state == COMPLETE:
        raise SpecViolation(f"Phase {phase_id} is already complete")
    if state in (HELD, CANCELLED, PLAN_EXCLUDED):
        raise SpecViolation(f"Phase {phase_id} is {state}")
    unsatisfied = view.unsatisfied_dependencies(phase_id)
    if unsatisfied:
        raise StopError(
            f"Phase {phase_id} is blocked by " + ", ".join(f"{r.from_id} ({label})" for r, label in unsatisfied),
            code="phase_blocked",
        )

    if view.phase_works(phase_id):
        # Already expanded: do not expand again; inspect the current structure.
        startable = view.startable_works(phase_id)
        entry = startable[0].id if startable else None
        integration = next((w.id for w in view.integrations(phase_id)), None)
        confirmation = next((w.id for w in view.effective_works(phase_id) if w.work_kind == "human_confirmation"), None)
        return PhaseEntryResult(phase_id, {}, integration, confirmation, entry, False, None, gitcmd.head_commit(store.root))

    if not design.works:
        raise ValidationError("Phase entry needs at least one normal Work")
    for key in design.works:
        if key in ("integration", "confirmation"):
            raise ValidationError(f"reserved Work key: {key}")

    mutation = _open(store, "phase-entry", {"phase_id": phase_id}, [phase_id])
    with abandon_on_stop(mutation):
        return _expand_phase(store, mutation, phase, phase_id, roadmap_id, design)


def _expand_phase(store: ProjectStore, mutation: Mutation, phase: Entity, phase_id: str, roadmap_id: str, design: PhaseEntryDesign) -> PhaseEntryResult:
    normal_specs = {
        key: WorkSpec(w.name, w.desired_state, phase_id=phase_id, roadmap_id=roadmap_id, related=tuple(w.related))
        for key, w in design.works.items()
    }
    normal_relations = [RelationSpec("planned_next", a, b) for a, b in design.planned_next]
    normal_relations += [RelationSpec("requires_completion", a, b) for a, b in design.requires_completion]
    normal = register_works(mutation, "works", normal_specs, normal_relations)

    integration_spec = WorkSpec(
        design.integration.name,
        design.integration.desired_state,
        phase_id=phase_id,
        roadmap_id=roadmap_id,
        work_kind="phase_integration_check",
        related=tuple(design.integration.related),
    )
    integration = register_works(
        mutation,
        "integration",
        {"integration": integration_spec},
        [RelationSpec("requires_completion", work_id, "integration") for work_id in normal.work_ids.values()],
    )
    integration_id = integration.work_ids["integration"]

    confirmation_id: str | None = None
    paths = list(normal.paths) + list(integration.paths)
    if design.human_confirmation is not None:
        confirmation_spec = WorkSpec(
            design.human_confirmation.name,
            design.human_confirmation.desired_state,
            phase_id=phase_id,
            roadmap_id=roadmap_id,
            work_kind="human_confirmation",
            confirmation_target=integration_id,
            related=tuple(design.human_confirmation.related),
        )
        confirmation = register_works(
            mutation,
            "confirmation",
            {"confirmation": confirmation_spec},
            [RelationSpec("requires_completion", integration_id, "confirmation")],
        )
        confirmation_id = confirmation.work_ids["confirmation"]
        paths += list(confirmation.paths)

    after = _stop_on_structure(store, "phase structure check")
    head = _finalize(mutation, f"chore(workline): expand phase {phase.display}", paths)

    after = ProjectView.load(store)
    startable = after.startable_works(phase_id)
    if design.entry is not None:
        entry = normal.work_ids.get(design.entry)
        if entry is None or entry not in {w.id for w in startable}:
            raise SpecViolation(f"entry Work {design.entry} is not startable")
    else:
        entry = startable[0].id if startable else None
    return PhaseEntryResult(phase_id, normal.work_ids, integration_id, confirmation_id, entry, True, mutation.id, head)


# --------------------------------------------------------------------------- lifecycle

def _lifecycle(store: ProjectStore, operation: str, entity_id: str, event_type: str, precheck) -> OperationResult:
    view = _stop_on_structure(store, "precheck")
    precheck(view)
    mutation = _open(store, operation, {"entity": entity_id}, [entity_id])
    if not mutation.has_stage("event"):
        mutation.add_effects("event", event_effects(mutation, "event", entity_id, [event_type]))
    mutation.apply()
    head = _finalize(mutation, f"chore(workline): {event_type} {entity_id}")
    return OperationResult(event_type, entity_id, mutation.id, head)


def hold_phase(store: ProjectStore, phase_id: str) -> OperationResult:
    def precheck(view: ProjectView) -> None:
        if phase_id not in view.phases:
            raise ValidationError(f"Phase unresolvable: {phase_id}")
        if view.phase_lifecycle(phase_id) != ACTIVE:
            raise SpecViolation(f"Phase {phase_id} is {view.phase_lifecycle(phase_id)}")
    return _lifecycle(store, "phase-hold", phase_id, "phase_held", precheck)


def resume_phase(store: ProjectStore, phase_id: str) -> OperationResult:
    def precheck(view: ProjectView) -> None:
        if view.phase_lifecycle(phase_id) != HELD:
            raise SpecViolation(f"Phase {phase_id} is not held")
    return _lifecycle(store, "phase-resume", phase_id, "phase_resumed", precheck)


def cancel_phase(store: ProjectStore, phase_id: str) -> OperationResult:
    def precheck(view: ProjectView) -> None:
        if phase_id not in view.phases:
            raise ValidationError(f"Phase unresolvable: {phase_id}")
        if view.phase_lifecycle(phase_id) in (CANCELLED, PLAN_EXCLUDED):
            raise SpecViolation(f"Phase {phase_id} already terminal")
    return _lifecycle(store, "phase-cancel", phase_id, "phase_cancelled", precheck)


def hold_roadmap(store: ProjectStore, roadmap_id: str) -> OperationResult:
    def precheck(view: ProjectView) -> None:
        if view.roadmap_lifecycle(roadmap_id) != ACTIVE:
            raise SpecViolation(f"Roadmap {roadmap_id} is {view.roadmap_lifecycle(roadmap_id)}")
    return _lifecycle(store, "roadmap-hold", roadmap_id, "roadmap_held", precheck)


def resume_roadmap(store: ProjectStore, roadmap_id: str) -> OperationResult:
    def precheck(view: ProjectView) -> None:
        if view.roadmap_lifecycle(roadmap_id) != HELD:
            raise SpecViolation(f"Roadmap {roadmap_id} is not held")
    return _lifecycle(store, "roadmap-resume", roadmap_id, "roadmap_resumed", precheck)


def cancel_roadmap(store: ProjectStore, roadmap_id: str) -> OperationResult:
    def precheck(view: ProjectView) -> None:
        if view.roadmap_lifecycle(roadmap_id) in (CANCELLED, ACHIEVED):
            raise SpecViolation(f"Roadmap {roadmap_id} already terminal")
    return _lifecycle(store, "roadmap-cancel", roadmap_id, "roadmap_cancelled", precheck)


def _plan_exclude(store: ProjectStore, operation: str, entity_id: str, replan: Replan, precheck) -> OperationResult:
    view = _stop_on_structure(store, "precheck")
    precheck(view)
    mutation = _open(store, operation, {"entity": entity_id}, [entity_id])
    with abandon_on_stop(mutation):
        work_ids, removals, additions = plan_replan(mutation, "replan", view, replan)
        projection = projected_view(
            view,
            add_events=[(entity_id, "plan_excluded")],
            remove_relation_ids=tuple(r.id for r in removals),
            add_relations=additions,
            add_works={work_ids[k]: spec for k, spec in replan.new_works.items()},
        )
        validate_projection(projection, "plan exclusion replan")
    if not mutation.has_stage("event"):
        mutation.add_effects("event", event_effects(mutation, "event", entity_id, ["plan_excluded"]))
    mutation.apply()
    apply_replan(mutation, "replan", replan, removals, additions, work_ids)
    head = _finalize(mutation, f"chore(workline): plan_excluded {entity_id}")
    return OperationResult("plan_excluded", entity_id, mutation.id, head)


def plan_exclude_phase(store: ProjectStore, phase_id: str, replan: Replan = Replan()) -> OperationResult:
    def precheck(view: ProjectView) -> None:
        if phase_id not in view.phases:
            raise ValidationError(f"Phase unresolvable: {phase_id}")
        if view.phase_state(phase_id) != UNSTARTED:
            raise SpecViolation(f"plan_excluded is only for unstarted Phases; {phase_id} is {view.phase_state(phase_id)}")
    return _plan_exclude(store, "phase-plan-exclude", phase_id, replan, precheck)


def plan_exclude_work(store: ProjectStore, work_id: str, replan: Replan = Replan()) -> OperationResult:
    """Exclude an unstarted Phase Work from the future plan (Roadmap-owned)."""
    def precheck(view: ProjectView) -> None:
        work = view.works.get(work_id)
        if work is None:
            raise ValidationError(f"Work unresolvable: {work_id}")
        if work.phase_id is None:
            raise SpecViolation("standalone Work plan exclusion is owned by START (standalone scope)")
        if view.work_state(work_id).state != UNSTARTED:
            raise SpecViolation(f"plan_excluded is only for unstarted Works; {work_id} is {view.work_state(work_id).state}")
    return _plan_exclude(store, "work-plan-exclude", work_id, replan, precheck)


# --------------------------------------------------------------------------- achievement

@dataclass(frozen=True)
class AchievementResult:
    status: str  # not_ready | achieved | human_confirmation_required | not_achieved | desired_state_change_required
    roadmap_id: str
    mutation_id: str | None = None
    head: str | None = None
    detail: str = ""


JUDGEMENTS = ("achieved", "human_confirmation", "not_achieved", "desired_state_change")


def evaluate_achievement(store: ProjectStore, roadmap_id: str, judgement: str, detail: str = "") -> AchievementResult:
    """Explicit Roadmap achievement check.

    All active Phases complete is a precondition, never the conclusion. The
    ``judgement`` is the explicit evaluation of the Roadmap's desired state.
    Only ``achieved`` records ``roadmap_achieved``.
    """
    if judgement not in JUDGEMENTS:
        raise ValidationError(f"unknown judgement: {judgement}")
    view = _stop_on_structure(store, "precheck")
    _require_active_roadmap(view, roadmap_id)
    if not view.all_active_phases_complete(roadmap_id):
        return AchievementResult("not_ready", roadmap_id, detail=diagnose_no_candidate(store, roadmap_id))
    if judgement == "human_confirmation":
        return AchievementResult("human_confirmation_required", roadmap_id, detail=detail)
    if judgement == "not_achieved":
        return AchievementResult("not_achieved", roadmap_id, detail=detail or "add Phases / replan without changing the desired state")
    if judgement == "desired_state_change":
        return AchievementResult("desired_state_change_required", roadmap_id, detail=detail)
    result = _lifecycle(store, "roadmap-achievement", roadmap_id, "roadmap_achieved", lambda v: None)
    return AchievementResult("achieved", roadmap_id, result.mutation_id, result.head, detail)


# --------------------------------------------------------------------------- handoff

def handoff(store: ProjectStore, phase_id: str, executor, entry_work_id: str | None = None):
    """Hand a Phase to START (mode=outer). START returns at Phase completion or stop."""
    from .start import start

    if entry_work_id is None:
        view = _stop_on_structure(store, "handoff")
        startable = view.startable_works(phase_id)
        if not startable:
            raise StopError(f"Phase {phase_id} has no startable Work", code="no_startable_work")
        entry_work_id = startable[0].id
    return start(store, entry_work_id, "outer", executor)


__all__ = [
    "RoadmapPlan", "RoadmapResult", "WorkDesign", "PhaseEntryDesign", "PhaseEntryResult", "OperationResult",
    "PhaseAdditionResult", "AchievementResult", "Replan", "create_roadmap", "add_phases", "startable_phases",
    "select_phase", "diagnose_no_candidate",
    "enter_phase", "hold_phase", "resume_phase", "cancel_phase", "hold_roadmap", "resume_roadmap", "cancel_roadmap",
    "plan_exclude_phase", "plan_exclude_work", "evaluate_achievement", "handoff",
]
