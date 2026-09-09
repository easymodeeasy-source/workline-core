"""Helpers shared by operation owners (Roadmap / START / CREATE direct).

* event effect construction with mutation-stable IDs;
* replan payloads (relation removal / addition / new Works) with projected
  structural validation before any physical write;
* owned canonical path computation from recorded effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .create import RelationSpec, WorkSpec, register_works, resolve_ref
from .errors import SpecViolation, ValidationError
from .mutation import Effect, Mutation, utc_now
from .state import ProjectView
from .store import WORK_DESIRED_HEADING, WORKLINE_DIR, Entity, Event, ProjectStore, Relation, render_body
from .validate import Problem, validate_structure


def new_event(mutation: Mutation, key: str, event_type: str, entity_id: str) -> Event:
    return Event(mutation.reserve_id(key, "event"), event_type, entity_id, utc_now())


def event_effects(mutation: Mutation, stage: str, entity_id: str, types: list[str]) -> list[Effect]:
    return [Effect.append_event(new_event(mutation, f"{stage}:event:{index}", t, entity_id)) for index, t in enumerate(types)]


def stage_name(mutation: Mutation, prefix: str) -> str:
    """Unique stage name ``<prefix>:<n>`` based on stages already recorded."""
    count = len({e["stage"] for e in mutation.effects if str(e["stage"]).startswith(prefix + ":")})
    return f"{prefix}:{count}"


def owned_canonical_paths(mutation: Mutation) -> list[str]:
    """Canonical paths touched by the mutation's recorded effects."""
    paths: set[str] = set()
    for effect in mutation.effects:
        kind = effect["kind"]
        payload = effect["payload"]
        if kind == "write_file":
            paths.add(payload["path"])
        elif kind in ("add_relation", "remove_relation"):
            paths.add(f"{WORKLINE_DIR}/relations/{payload['file']}.yaml")
        elif kind == "append_event":
            paths.add(f"{WORKLINE_DIR}/events/events.jsonl")
    return sorted(paths)


# --------------------------------------------------------------------------- replan

@dataclass(frozen=True)
class Replan:
    """Operation-owner decided future-plan changes accompanying cancel / plan exclusion."""

    remove_relation_ids: tuple[str, ...] = ()
    add_relations: tuple[RelationSpec, ...] = ()
    new_works: dict[str, WorkSpec] = field(default_factory=dict)


def projected_view(
    view: ProjectView,
    *,
    add_events: list[tuple[str, str]] = (),
    remove_relation_ids: tuple[str, ...] = (),
    add_relations: list[Relation] = (),
    add_works: dict[str, WorkSpec] | None = None,
) -> ProjectView:
    """In-memory projection of ``view`` after the planned changes."""
    projected = ProjectView(view.store)
    projected.works = dict(view.works)
    projected.phases = dict(view.phases)
    projected.roadmaps = dict(view.roadmaps)
    projected.related = list(view.related)
    projected.roadmap_relations = [r for r in view.roadmap_relations if r.id not in remove_relation_ids] + list(add_relations)
    projected.events = list(view.events) + [Event(f"evt_{'0' * 26}", t, e, utc_now()) for e, t in add_events]
    for work_id, spec in (add_works or {}).items():
        meta: dict[str, Any] = {"id": work_id, "display": "W-??", "type": "work"}
        if spec.phase_id is not None:
            meta["phase_id"] = spec.phase_id
            meta["origin"] = {"type": "roadmap", "roadmap_id": spec.roadmap_id, "phase_id": spec.phase_id}
        else:
            meta["origin"] = {"type": "standalone"}
        if spec.work_kind is not None:
            meta["work_kind"] = spec.work_kind
        body = render_body(spec.name, [(WORK_DESIRED_HEADING, spec.desired_state)])
        projected.works[work_id] = Entity(work_id, "work", meta, body, ProjectStore.entity_rel_path("work", work_id))
    return projected


def validate_projection(view: ProjectView, context: str, *, ignore_placeholder_events: bool = True) -> None:
    problems = [
        p for p in validate_structure(view)
        if not (ignore_placeholder_events and p.code == "event_invalid" and "duplicate event id: evt_0" in p.message)
    ]
    if problems:
        raise SpecViolation(f"{context}: structure would be invalid: " + "; ".join(p.message for p in problems))


def plan_replan(
    mutation: Mutation,
    prefix: str,
    view: ProjectView,
    replan: Replan,
) -> tuple[dict[str, str], list[Relation], list[Relation]]:
    """Reserve IDs and resolve a replan into (new work ids, removals, additions)."""
    removals: list[Relation] = []
    existing = {r.id: r for r in view.roadmap_relations}
    for relation_id in replan.remove_relation_ids:
        relation = existing.get(relation_id)
        if relation is None:
            raise ValidationError(f"replan: relation {relation_id} unresolvable")
        if relation.type == "derived":
            raise SpecViolation("replan: derived relations are historical facts and cannot be removed")
        removals.append(relation)
    work_ids = {key: mutation.reserve_id(f"{prefix}:works:work:{key}", "work") for key in replan.new_works}
    additions: list[Relation] = []
    relation_stage = f"{prefix}:works" if replan.new_works else f"{prefix}:relations"
    for index, spec in enumerate(replan.add_relations):
        relation_id = mutation.reserve_id(f"{relation_stage}:rel:{index}", "relation")
        additions.append(Relation(relation_id, spec.type, resolve_ref(spec.from_ref, work_ids), resolve_ref(spec.to_ref, work_ids)))
    return work_ids, removals, additions


def apply_replan(
    mutation: Mutation,
    prefix: str,
    replan: Replan,
    removals: list[Relation],
    additions: list[Relation],
    work_ids: dict[str, str],
) -> list[str]:
    """Record and apply replan effects. Returns touched canonical paths."""
    touched: list[str] = []
    if replan.new_works:
        result = register_works(
            mutation,
            f"{prefix}:works",
            replan.new_works,
            list(replan.add_relations),
        )
        touched.extend(result.paths)
        if result.work_ids != work_ids:
            raise ValidationError("replan: reserved Work IDs diverged")
    elif additions:
        stage = f"{prefix}:relations"
        if not mutation.has_stage(stage):
            mutation.add_effects(stage, [Effect.add_relation("roadmap", r) for r in additions])
        mutation.apply()
        touched.append(f"{WORKLINE_DIR}/relations/roadmap.yaml")
    if removals:
        stage = f"{prefix}:remove"
        if not mutation.has_stage(stage):
            mutation.add_effects(stage, [Effect.remove_relation("roadmap", r) for r in removals])
        mutation.apply()
        touched.append(f"{WORKLINE_DIR}/relations/roadmap.yaml")
    return touched


def problems_text(problems: list[Problem]) -> str:
    return "; ".join(f"{p.code}: {p.message}" for p in problems)
