"""CREATE (``skills/create``): Work registration core and direct invocation.

The registration core registers Works whose meaning has already been decided
by the caller (Roadmap / START / a human for standalone Works). It assigns
stable identity, writes the Work body, registers ``origin`` / ``phase_id``,
caller-decided relations, Related data and derivation detail, and runs the
postcheck. It never decides whether a Work is needed, never creates
integration / human_confirmation Works on its own, never records lifecycle
events, and is not a Git finalizer.

Only the direct standalone invocation (``create_standalone_work``) creates a
Direct Work Operation context that owns postcheck / commit / push.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Sequence

from . import gitops
from .errors import SpecViolation, ValidationError
from .ids import is_valid_id
from .mutation import Effect, Mutation, MutationController, WriteScope, abandon_on_stop
from .state import COMPLETE, EXCLUDED_STATES, ProjectView
from .store import (
    CONDITIONAL_RELATED_TYPES,
    RELATED_TYPES,
    ROADMAP_RELATION_TYPES,
    WORK_DESIRED_HEADING,
    WORK_KINDS,
    WORKLINE_DIR,
    ProjectStore,
    Relation,
    render_body,
    render_entity,
)
from .validate import Problem, validate_condition, validate_structure

DIRECT_OWNER = "create-direct"


@dataclass(frozen=True)
class RelatedSpec:
    type: str
    to: str
    condition: dict[str, Any] | None = None


@dataclass(frozen=True)
class RelationSpec:
    """A caller-decided roadmap relation. Endpoints are stable IDs or spec keys."""

    type: str
    from_ref: str
    to_ref: str


@dataclass(frozen=True)
class WorkSpec:
    """Decided Work meaning handed to the registration core."""

    name: str
    desired_state: str
    phase_id: str | None = None
    roadmap_id: str | None = None
    work_kind: str | None = None
    confirmation_target: str | list[str] | None = None
    related: tuple[RelatedSpec, ...] = ()
    derivation_detail: str | None = None

    @property
    def standalone(self) -> bool:
        return self.phase_id is None


@dataclass(frozen=True)
class RegistrationResult:
    work_ids: dict[str, str]
    relation_ids: dict[int, str]
    paths: tuple[str, ...]


def _display(prefix: str, number: int) -> str:
    return f"{prefix}-{number:02d}"


def resolve_ref(ref: str, mapping: dict[str, str]) -> str:
    if ref in mapping:
        return mapping[ref]
    return ref


def validate_related_specs(related: "Sequence[RelatedSpec]", context: str) -> None:
    """Payload rules for related relations, shared by every owner that writes them.

    CREATE applies these when registering a new Work; Roadmap applies the same
    function when maintaining an unstarted Work's related relations. The rules
    live here once so the two paths can never drift apart.
    """
    for related_spec in related:
        if related_spec.type not in RELATED_TYPES:
            raise ValidationError(f"{context}: unknown related type {related_spec.type}")
        if not related_spec.to.strip():
            raise ValidationError(f"{context}: related target is empty")
        if related_spec.type in CONDITIONAL_RELATED_TYPES:
            message = validate_condition(related_spec.condition)
            if message:
                raise ValidationError(f"{context}: {message}")
        elif related_spec.condition is not None:
            raise ValidationError(f"{context}: condition is only for conditional relations")


def related_edge_key(relation_type: str, from_id: str, to: str, condition: dict[str, Any] | None) -> tuple:
    """Identity of a related edge for duplicate detection.

    Two edges are the same when type, from, to and condition agree; the
    relation ID is not part of it, so re-requesting an existing edge is a
    no-op instead of a second parallel relation.
    """
    return (relation_type, from_id, to, json.dumps(condition, sort_keys=True) if condition is not None else None)


def _stop_on_problems(problems: list[Problem], context: str) -> None:
    if problems:
        raise ValidationError(context + ": " + "; ".join(f"{p.code}: {p.message}" for p in problems), code="postcheck_failed")


def _validate_spec(spec: WorkSpec, key: str, view: ProjectView) -> None:
    if not spec.name.strip():
        raise ValidationError(f"work {key}: name is required")
    if not spec.desired_state.strip():
        raise ValidationError(f"work {key}: desired state is required")
    if spec.work_kind is not None and spec.work_kind not in WORK_KINDS:
        raise ValidationError(f"work {key}: unknown work_kind {spec.work_kind}")
    if spec.confirmation_target is not None and spec.work_kind != "human_confirmation":
        raise ValidationError(f"work {key}: confirmation_target is only for human_confirmation Works")
    if spec.phase_id is None:
        if spec.roadmap_id is not None:
            raise ValidationError(f"work {key}: standalone Work must not carry roadmap_id")
        if spec.work_kind is not None:
            raise ValidationError(f"work {key}: special Work kinds require a Phase")
    else:
        phase = view.phases.get(spec.phase_id)
        if phase is None:
            raise ValidationError(f"work {key}: phase_id unresolvable: {spec.phase_id}")
        if spec.roadmap_id is None or spec.roadmap_id != phase.roadmap_id:
            raise ValidationError(f"work {key}: roadmap_id must match the Phase's roadmap_id")
        phase_state = view.phase_state(spec.phase_id)
        if phase_state == COMPLETE:
            raise SpecViolation(f"work {key}: cannot add a Work to completed Phase {spec.phase_id}")
        if phase_state in EXCLUDED_STATES:
            raise SpecViolation(f"work {key}: Phase {spec.phase_id} is {phase_state}")
    validate_related_specs(spec.related, f"work {key}")


def register_works(
    mutation: Mutation,
    stage: str,
    specs: dict[str, WorkSpec],
    relations: list[RelationSpec] = (),
) -> RegistrationResult:
    """Registration core. Participates in the caller's mutation; no Git."""
    store = mutation.store
    if not specs:
        raise ValidationError("registration core needs at least one Work")
    view = ProjectView.load(store)
    for key, spec in specs.items():
        _validate_spec(spec, key, view)

    # stable IDs (reserved once per mutation; resumed unchanged) --------------
    work_ids = {key: mutation.reserve_id(f"{stage}:work:{key}", "work") for key in specs}
    relation_ids = {index: mutation.reserve_id(f"{stage}:rel:{index}", "relation") for index in range(len(relations))}
    related_ids: dict[tuple[str, int], str] = {}
    derivation_ids: dict[str, str] = {}
    for key, spec in specs.items():
        for index in range(len(spec.related)):
            related_ids[(key, index)] = mutation.reserve_id(f"{stage}:related:{key}:{index}", "relation")
        if spec.derivation_detail is not None:
            derivation_ids[key] = mutation.reserve_id(f"{stage}:der:{key}", "derivation")
    mutation.extend_scope(entities=list(work_ids.values()))

    # relation payload validation -----------------------------------------------
    resolved_relations: list[Relation] = []
    for index, rel in enumerate(relations):
        if rel.type not in ROADMAP_RELATION_TYPES:
            raise ValidationError(f"relation {index}: unknown type {rel.type}")
        from_id = resolve_ref(rel.from_ref, work_ids)
        to_id = resolve_ref(rel.to_ref, work_ids)
        for endpoint in (from_id, to_id):
            if not is_valid_id(endpoint, "work") or (endpoint not in view.works and endpoint not in work_ids.values()):
                raise ValidationError(f"relation {index}: endpoint unresolvable: {endpoint}")
        if from_id == to_id:
            raise ValidationError(f"relation {index}: self relation")
        resolved_relations.append(Relation(relation_ids[index], rel.type, from_id, to_id))

    # projected structure check (integration invariant, recursion, refs) ------
    _check_projection(view, specs, work_ids, resolved_relations)

    # effects -------------------------------------------------------------
    if not mutation.has_stage(stage):
        effects: list[Effect] = []
        base_number = store.count_entities("work")
        for offset, (key, spec) in enumerate(specs.items()):
            work_id = work_ids[key]
            meta: dict[str, Any] = {"id": work_id, "display": _display("W", base_number + offset + 1), "type": "work"}
            if spec.phase_id is not None:
                meta["phase_id"] = spec.phase_id
                meta["origin"] = {"type": "roadmap", "roadmap_id": spec.roadmap_id, "phase_id": spec.phase_id}
            else:
                meta["origin"] = {"type": "standalone"}
            if spec.work_kind is not None:
                meta["work_kind"] = spec.work_kind
            if spec.confirmation_target is not None:
                target = spec.confirmation_target
                if isinstance(target, list):
                    meta["confirmation_target"] = [resolve_ref(t, work_ids) for t in target]
                else:
                    meta["confirmation_target"] = resolve_ref(target, work_ids)
            body = render_body(spec.name, [(WORK_DESIRED_HEADING, spec.desired_state)])
            effects.append(Effect.write_file(ProjectStore.entity_rel_path("work", work_id), render_entity(meta, body)))
            if key in derivation_ids:
                detail = f"# Derivation detail\n\n{spec.derivation_detail.strip()}\n"
                effects.append(Effect.write_file(f"{WORKLINE_DIR}/derivations/{derivation_ids[key]}.md", detail))
        for relation in resolved_relations:
            effects.append(Effect.add_relation("roadmap", relation))
        for key, spec in specs.items():
            for index, related in enumerate(spec.related):
                extra = {"condition": related.condition} if related.condition is not None else {}
                effects.append(Effect.add_relation("related", Relation(related_ids[(key, index)], related.type, work_ids[key], related.to, extra)))
        mutation.add_effects(stage, effects)
    mutation.apply()

    # postcheck -----------------------------------------------------------
    after = ProjectView.load(store)
    for key, work_id in work_ids.items():
        entity = after.works.get(work_id)
        if entity is None or entity.section(WORK_DESIRED_HEADING) is None:
            raise ValidationError(f"postcheck: {work_id} not resolvable with desired state", code="postcheck_failed")
        if after.events_for(work_id):
            raise ValidationError(f"postcheck: {work_id} has lifecycle events after CREATE", code="postcheck_failed")
    registered = {r.id for r in after.roadmap_relations}
    for relation in resolved_relations:
        if relation.id not in registered:
            raise ValidationError(f"postcheck: relation {relation.id} missing", code="postcheck_failed")
    _stop_on_problems(validate_structure(after), "postcheck")
    paths = tuple(e["payload"]["path"] for e in mutation.stage_effects(stage) if e["kind"] == "write_file")
    touched = list(paths)
    if resolved_relations:
        touched.append(f"{WORKLINE_DIR}/relations/roadmap.yaml")
    if any(spec.related for spec in specs.values()):
        touched.append(f"{WORKLINE_DIR}/relations/related.yaml")
    return RegistrationResult(work_ids, relation_ids, tuple(touched))


def _check_projection(
    view: ProjectView,
    specs: dict[str, WorkSpec],
    work_ids: dict[str, str],
    relations: list[Relation],
) -> None:
    """Integration invariant and special Work recursion on the projected structure."""
    per_phase_new_integrations: dict[str, int] = {}
    for key, spec in specs.items():
        if spec.work_kind == "phase_integration_check" and spec.phase_id is not None:
            per_phase_new_integrations[spec.phase_id] = per_phase_new_integrations.get(spec.phase_id, 0) + 1
        if spec.work_kind == "human_confirmation" and spec.confirmation_target is not None:
            targets = spec.confirmation_target if isinstance(spec.confirmation_target, list) else [spec.confirmation_target]
            for target in targets:
                resolved = resolve_ref(target, work_ids)
                if resolved == work_ids[key]:
                    raise ValidationError(f"work {key}: confirmation_target refers to itself")
                target_spec = next((s for k, s in specs.items() if work_ids[k] == resolved), None)
                if target_spec is not None and target_spec.work_kind == "human_confirmation":
                    raise ValidationError(f"work {key}: human_confirmation confirming a human_confirmation (recursion)")
                existing = view.works.get(resolved)
                if existing is not None and existing.work_kind == "human_confirmation":
                    raise ValidationError(f"work {key}: human_confirmation confirming a human_confirmation (recursion)")
                if existing is None and target_spec is None:
                    raise ValidationError(f"work {key}: confirmation_target unresolvable: {target}")
    for phase_id, count in per_phase_new_integrations.items():
        unfinished = len(view.unfinished_integrations(phase_id)) + count
        if unfinished > 1:
            raise SpecViolation(
                f"integration invariant: Phase {phase_id} would have {unfinished} unfinished integrations"
            )
    graph: dict[str, list[str]] = {}
    for relation in view.roadmap_relations + relations:
        if relation.type == "requires_completion":
            graph.setdefault(relation.from_id, []).append(relation.to)
    from .validate import _has_cycle

    if _has_cycle(graph):
        raise ValidationError("requires_completion would form a cycle")


# --------------------------------------------------------------------------- direct invocation

@dataclass(frozen=True)
class CreateResult:
    work_id: str
    mutation_id: str
    head: str | None
    resumed: bool


def create_standalone_work(store: ProjectStore, spec: WorkSpec, *, invocation_key: str | None = None) -> CreateResult:
    """CREATE entrypoint for direct standalone invocation (Direct Work Operation context)."""
    if not spec.standalone or spec.roadmap_id is not None:
        raise SpecViolation("direct CREATE only creates standalone Works (origin.type = standalone)")
    if spec.work_kind is not None:
        raise SpecViolation("direct CREATE does not create special Phase Works")
    controller = MutationController(store)
    invocation = {"operation": DIRECT_OWNER, "name": spec.name, "key": invocation_key or spec.name}
    scope = WriteScope(files=(
        f"{WORKLINE_DIR}/relations/roadmap.yaml",
        f"{WORKLINE_DIR}/relations/related.yaml",
        f"{WORKLINE_DIR}/events/events.jsonl",
    ))
    mutation = controller.open(DIRECT_OWNER, invocation, scope)
    with abandon_on_stop(mutation):
        gitops.ensure_git_ready(store.root)
        gitops.record_preexisting_dirty(mutation, store.root)
        result = register_works(mutation, "register", {"work": spec})
    work_id = result.work_ids["work"]
    message = f"chore(workline): create {ProjectView.load(store).works[work_id].display}"
    gitops.finalize(mutation, "finalize", message, list(result.paths), push=True)
    _stop_on_problems(validate_structure(ProjectView.load(store)), "postcheck")
    mutation.complete()
    from . import gitcmd

    return CreateResult(work_id, mutation.id, gitcmd.head_commit(store.root), mutation.resumed)
