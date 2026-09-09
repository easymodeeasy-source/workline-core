"""Phase CREATE (``skills/phase-create``): register already-decided Phases.

Internal registration path called by Roadmap. Validates input, issues stable
Phase IDs / display, writes the Phase body with ``roadmap_id``, registers
Roadmap-decided Phase relation payloads through the Mutation Controller, and
runs the postcheck. It never decides Phase meaning, never splits Phases,
never creates Works / integration / human_confirmation, never starts
anything and is not a Git finalizer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import SpecViolation, ValidationError
from .ids import is_valid_id
from .mutation import Effect, Mutation
from .state import ACHIEVED, CANCELLED, HELD, ProjectView
from .store import PHASE_DESIRED_HEADING, ROADMAP_RELATION_TYPES, ProjectStore, Relation, render_body, render_entity
from .validate import validate_structure


@dataclass(frozen=True)
class PhaseSpec:
    name: str
    desired_state: str


@dataclass(frozen=True)
class PhaseRelationSpec:
    """Roadmap-decided Phase↔Phase relation; endpoints are Phase IDs or spec keys."""

    type: str
    from_ref: str
    to_ref: str


@dataclass(frozen=True)
class PhaseRegistrationResult:
    phase_ids: dict[str, str]
    relation_ids: dict[int, str]
    paths: tuple[str, ...]


def register_phases(
    mutation: Mutation,
    stage: str,
    roadmap_id: str,
    specs: dict[str, PhaseSpec],
    relations: list[PhaseRelationSpec] = (),
    *,
    future_plan_change: bool = False,
) -> PhaseRegistrationResult:
    store = mutation.store
    if not specs:
        raise ValidationError("Phase CREATE needs at least one Phase")
    view = ProjectView.load(store)

    # Precheck ---------------------------------------------------------------
    if roadmap_id not in view.roadmaps:
        raise ValidationError(f"Roadmap unresolvable: {roadmap_id}")
    lifecycle = view.roadmap_lifecycle(roadmap_id)
    if lifecycle in (CANCELLED, ACHIEVED):
        raise SpecViolation(f"Roadmap {roadmap_id} is {lifecycle}; no Phase registration")
    if lifecycle == HELD and not future_plan_change:
        raise SpecViolation(f"Roadmap {roadmap_id} is held; Phase addition needs a decided future-plan change")
    for key, spec in specs.items():
        if not spec.name.strip():
            raise ValidationError(f"phase {key}: name is required")
        if not spec.desired_state.strip():
            raise ValidationError(f"phase {key}: desired state is required")

    phase_ids = {key: mutation.reserve_id(f"{stage}:phase:{key}", "phase") for key in specs}
    relation_ids = {index: mutation.reserve_id(f"{stage}:rel:{index}", "relation") for index in range(len(relations))}
    mutation.extend_scope(entities=list(phase_ids.values()))

    resolved: list[Relation] = []
    for index, rel in enumerate(relations):
        if rel.type not in ROADMAP_RELATION_TYPES:
            raise ValidationError(f"phase relation {index}: unknown type {rel.type}")
        from_id = phase_ids.get(rel.from_ref, rel.from_ref)
        to_id = phase_ids.get(rel.to_ref, rel.to_ref)
        for endpoint in (from_id, to_id):
            if not is_valid_id(endpoint, "phase"):
                raise ValidationError(f"phase relation {index}: mixed or invalid endpoint {endpoint}")
            if endpoint not in view.phases and endpoint not in phase_ids.values():
                raise ValidationError(f"phase relation {index}: endpoint unresolvable: {endpoint}")
        if from_id == to_id:
            raise ValidationError(f"phase relation {index}: self relation")
        resolved.append(Relation(relation_ids[index], rel.type, from_id, to_id))

    # Effects ---------------------------------------------------------------
    if not mutation.has_stage(stage):
        effects: list[Effect] = []
        base_number = store.count_entities("phase")
        for offset, (key, spec) in enumerate(specs.items()):
            phase_id = phase_ids[key]
            meta: dict[str, Any] = {
                "id": phase_id,
                "display": f"P-{base_number + offset + 1:02d}",
                "type": "phase",
                "roadmap_id": roadmap_id,
            }
            body = render_body(spec.name, [(PHASE_DESIRED_HEADING, spec.desired_state)])
            effects.append(Effect.write_file(ProjectStore.entity_rel_path("phase", phase_id), render_entity(meta, body)))
        for relation in resolved:
            effects.append(Effect.add_relation("roadmap", relation))
        mutation.add_effects(stage, effects)
    mutation.apply()

    # Postcheck ---------------------------------------------------------------
    after = ProjectView.load(store)
    for key, phase_id in phase_ids.items():
        entity = after.phases.get(phase_id)
        if entity is None or entity.roadmap_id != roadmap_id or entity.section(PHASE_DESIRED_HEADING) is None:
            raise ValidationError(f"postcheck: Phase {phase_id} invalid", code="postcheck_failed")
        if "state" in entity.meta or "origin" in entity.meta:
            raise ValidationError(f"postcheck: Phase {phase_id} carries state / origin", code="postcheck_failed")
        if after.events_for(phase_id) or after.phase_works(phase_id):
            raise ValidationError(f"postcheck: Phase CREATE produced Works or events for {phase_id}", code="postcheck_failed")
    registered = {r.id: r for r in after.roadmap_relations}
    for relation in resolved:
        if registered.get(relation.id) != relation:
            raise ValidationError(f"postcheck: relation {relation.id} does not match decided payload", code="postcheck_failed")
    problems = validate_structure(after)
    if problems:
        raise ValidationError("postcheck: " + "; ".join(p.message for p in problems), code="postcheck_failed")
    paths = [e["payload"]["path"] for e in mutation.stage_effects(stage) if e["kind"] == "write_file"]
    if resolved:
        paths.append(".workline/relations/roadmap.yaml")
    return PhaseRegistrationResult(phase_ids, relation_ids, tuple(paths))
