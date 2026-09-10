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
import json
from typing import Any

from . import gitcmd, gitops
from .create import (
    RelatedSpec,
    RelationSpec,
    WorkSpec,
    register_works,
    related_edge_key,
    validate_related_specs,
)
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
    Relation,
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


# --------------------------------------------------------------------------- related maintenance

RELATED_FILE = "related"


@dataclass(frozen=True)
class RelatedMaintenanceResult:
    work_id: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    mutation_id: str | None
    head: str | None
    changed: bool
    resumed: bool = False


def _pending_for(store: ProjectStore, operation: str, identity: dict[str, Any]) -> list[dict[str, Any]]:
    invocation = json.loads(json.dumps({"operation": operation, **identity}, sort_keys=True))
    return [p for p in MutationController(store).list_pending() if p["owner"] == OWNER and p["invocation"] == invocation]


def _unstarted_roadmap_work(view: ProjectView, work_id: str) -> Entity:
    """The target of related maintenance, or STOP.

    Only an unstarted Work under an operable Roadmap is future plan; anything
    that already entered its lifecycle is not adjusted by this operation.
    """
    work = view.works.get(work_id)
    if work is None:
        raise ValidationError(f"Work unresolvable: {work_id}")
    origin = work.meta.get("origin")
    if not isinstance(origin, dict) or origin.get("type") != "roadmap":
        raise SpecViolation(
            f"{work_id} is not a Roadmap Work; standalone Work related maintenance is outside Roadmap scope"
        )
    if work.phase_id is None or work.phase_id not in view.phases:
        raise ValidationError(f"{work_id}: phase_id unresolvable")
    roadmap_id = origin.get("roadmap_id")
    if not isinstance(roadmap_id, str) or roadmap_id not in view.roadmaps:
        raise ValidationError(f"{work_id}: origin roadmap unresolvable")
    _require_active_roadmap(view, roadmap_id)
    state = view.work_state(work_id).state
    if state != UNSTARTED:
        raise SpecViolation(
            f"related maintenance is future planning and applies to unstarted Works only; {work_id} is {state}"
        )
    return work


def _related_snapshot(view: ProjectView, work_id: str) -> dict[str, Any]:
    work = view.works[work_id]
    return {
        "body": work.body,
        "meta": json.dumps(work.meta, sort_keys=True, ensure_ascii=False),
        "state": view.work_state(work_id).state,
        "events": [e.to_record() for e in view.events],
        "roadmap_relations": [r.to_record() for r in view.roadmap_relations],
        "related": {r.id: r.to_record() for r in view.related},
    }


def maintain_work_related(
    store: ProjectStore,
    work_id: str,
    *,
    add: tuple[RelatedSpec, ...] = (),
    remove_relation_ids: tuple[str, ...] = (),
    invocation_key: str | None = None,
) -> RelatedMaintenanceResult:
    """Maintain the related relations of an existing, unstarted Roadmap Work.

    Roadmap already owns the meaning of ``WorkDesign.related`` at Phase entry,
    so it also owns later corrections to that plan. CREATE stays the
    registration core and never becomes the owner of an existing Work's
    meaning. ``roadmap.yaml`` future-plan relations already had a maintenance
    path; this closes the same gap for ``related.yaml``, which previously could
    only be corrected by editing the file by hand or by discarding and
    recreating the Work.

    Adds reuse the CREATE payload type and validation. Removals accept
    relation IDs that actually exist and belong to this Work; anything else
    STOPs rather than being guessed. Requesting an edge that already exists is
    a no-op, and an operation with no effective change makes no commit, no
    push and no relation ID. The Work body, ``origin``, ``phase_id``,
    lifecycle state, events and ``roadmap.yaml`` are never touched: this is a
    plan correction, not a lifecycle event.
    """
    if not add and not remove_relation_ids:
        raise ValidationError("related maintenance needs at least one add or remove")

    view = _stop_on_structure(store, "precheck")
    work = _unstarted_roadmap_work(view, work_id)
    validate_related_specs(add, f"related maintenance {work_id}")

    existing = {r.id: r for r in view.related}
    removals: list[Relation] = []
    seen_removals: set[str] = set()
    for relation_id in remove_relation_ids:
        relation = existing.get(relation_id)
        if relation is None:
            raise ValidationError(
                f"related maintenance: relation {relation_id} unresolvable; "
                "no name / target / similarity fallback is attempted"
            )
        if relation.from_id != work_id:
            raise SpecViolation(
                f"related maintenance: relation {relation_id} belongs to {relation.from_id}, not {work_id}"
            )
        if relation_id not in seen_removals:
            seen_removals.add(relation_id)
            removals.append(relation)

    # An edge that already exists (after the requested removals) is not added
    # a second time; duplicates inside one request collapse the same way.
    remaining = {
        related_edge_key(r.type, r.from_id, r.to, r.extra.get("condition"))
        for r in view.related
        if r.id not in seen_removals
    }
    effective_adds: list[tuple[int, RelatedSpec]] = []
    for index, spec in enumerate(add):
        key = related_edge_key(spec.type, work_id, spec.to, spec.condition)
        if key in remaining:
            continue
        remaining.add(key)
        effective_adds.append((index, spec))

    identity = {
        "work_id": work_id,
        "key": invocation_key
        or " | ".join([f"+{s.type}:{s.to}" for s in add] + [f"-{r}" for r in remove_relation_ids]),
    }
    operation = "work-related-maintenance"
    if not effective_adds and not removals and not _pending_for(store, operation, identity):
        return RelatedMaintenanceResult(work_id, (), (), None, gitcmd.head_commit(store.root), changed=False)

    before = _related_snapshot(view, work_id)
    mutation = _open(store, operation, identity, [work_id])
    with abandon_on_stop(mutation):
        additions = [
            Relation(
                mutation.reserve_id(f"related:add:{index}", "relation"),
                spec.type,
                work_id,
                spec.to,
                {"condition": spec.condition} if spec.condition is not None else {},
            )
            for index, spec in effective_adds
        ]
        validate_projection(
            projected_view(
                view,
                remove_related_ids=tuple(r.id for r in removals),
                add_related=additions,
            ),
            "related maintenance",
        )

    if not mutation.has_stage("related"):
        mutation.add_effects(
            "related",
            [Effect.remove_relation(RELATED_FILE, relation) for relation in removals]
            + [Effect.add_relation(RELATED_FILE, relation) for relation in additions],
        )
    mutation.apply()

    recorded = mutation.stage_effects("related")
    added_ids = tuple(e["payload"]["record"]["id"] for e in recorded if e["kind"] == "add_relation")
    removed_ids = tuple(e["payload"]["record"]["id"] for e in recorded if e["kind"] == "remove_relation")
    _related_postcheck(store, work_id, before, added_ids, removed_ids)

    head = _finalize(mutation, f"chore(workline): update related refs {work.display}")
    return RelatedMaintenanceResult(
        work_id, added_ids, removed_ids, mutation.id, head, changed=True, resumed=mutation.resumed
    )


def _related_postcheck(
    store: ProjectStore,
    work_id: str,
    before: dict[str, Any],
    added_ids: tuple[str, ...],
    removed_ids: tuple[str, ...],
) -> None:
    after_view = _stop_on_structure(store, "postcheck")
    after = _related_snapshot(after_view, work_id)

    for field_name in ("body", "meta", "state", "events", "roadmap_relations"):
        if after[field_name] != before[field_name]:
            raise StopError(
                f"postcheck: related maintenance changed {field_name} of {work_id}", code="postcheck_failed"
            )

    expected = {rid: rec for rid, rec in before["related"].items() if rid not in removed_ids}
    for relation_id in added_ids:
        relation = next((r for r in after_view.related if r.id == relation_id), None)
        if relation is None:
            raise StopError(f"postcheck: added relation {relation_id} missing", code="postcheck_failed")
        if relation.from_id != work_id:
            raise StopError(f"postcheck: added relation {relation_id} is not from {work_id}", code="postcheck_failed")
        expected[relation_id] = relation.to_record()
    if after["related"] != expected:
        raise StopError(
            "postcheck: related.yaml holds changes beyond the requested add / remove", code="postcheck_failed"
        )


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
