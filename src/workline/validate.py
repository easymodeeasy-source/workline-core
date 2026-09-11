"""Structural validation of a Project's canonical Workline structure.

Checks reference integrity, affiliation, relation boundaries, event
sequences, and the integration invariant. Validation never repairs anything;
it only reports problems.
"""

from __future__ import annotations

from dataclasses import dataclass
import fnmatch
from pathlib import Path

from . import registry as registry_module
from . import self_hosting
from .errors import ValidationError
from .ids import is_valid_id
from .state import EXCLUDED_STATES, ProjectView
from .store import (
    CONDITION_KINDS,
    CONDITIONAL_RELATED_TYPES,
    PHASE_DESIRED_HEADING,
    PHASE_EVENTS,
    PHASE_TERMINAL_EVENTS,
    RELATED_TYPES,
    ROADMAP_DESIRED_HEADING,
    ROADMAP_EVENTS,
    ROADMAP_RELATION_TYPES,
    ROADMAP_TERMINAL_EVENTS,
    RULE_REFS,
    WORK_DESIRED_HEADING,
    WORK_EVENTS,
    WORK_KINDS,
    WORK_TERMINAL_EVENTS,
    ProjectStore,
)


@dataclass(frozen=True)
class Problem:
    code: str
    message: str


VAGUE_CONDITIONS = ("if relevant", "if needed", "if necessary", "必要なら", "関連する場合", "適宜")


def validate_condition(condition: object) -> str | None:
    """Return a problem message when ``condition`` is not machine-evaluable."""
    if not isinstance(condition, dict):
        return "condition must be a mapping with kind / pattern"
    kind = condition.get("kind")
    if kind not in CONDITION_KINDS:
        return f"unsupported condition kind: {kind!r}"
    pattern = condition.get("pattern")
    if not isinstance(pattern, str) or not pattern.strip():
        return "condition pattern must be a non-empty string"
    lowered = pattern.strip().lower()
    if any(vague in lowered for vague in VAGUE_CONDITIONS):
        return f"condition is not mechanically evaluable: {pattern!r}"
    return None


def condition_applies(condition: dict, paths: list[str]) -> bool:
    pattern = str(condition.get("pattern", ""))
    return any(fnmatch.fnmatch(path, pattern) for path in paths)


def validate_project_yaml(store: ProjectStore) -> list[Problem]:
    problems: list[Problem] = []
    try:
        data = store.load_project_yaml()
    except Exception as exc:  # ValidationError
        return [Problem("project_yaml_invalid", str(exc))]
    workline = data.get("workline")
    root = workline.get("root") if isinstance(workline, dict) else None
    if not isinstance(root, str) or not root:
        problems.append(Problem("project_yaml_invalid", "workline.root missing"))
    else:
        root_path = Path(root)
        if not root_path.is_dir():
            problems.append(Problem("workline_root_missing", f"Workline root is not a directory: {root}"))
        else:
            result = registry_module.validate_registry(root_path)
            for issue in result.problems:
                problems.append(Problem(issue.code, issue.message))
    try:
        # Shape only: the pin is compared against the live Git configuration by
        # the operation entry check, never by validation (which stays offline).
        store.read_push_pin()
    except Exception as exc:  # ValidationError
        problems.append(Problem("project_yaml_invalid", str(exc)))
    rules = data.get("rules")
    if not isinstance(rules, dict):
        problems.append(Problem("project_yaml_invalid", "rules missing"))
    else:
        for key, ref in RULE_REFS.items():
            entry = rules.get(key)
            if not isinstance(entry, dict) or entry.get("ref") != ref:
                problems.append(Problem("project_yaml_invalid", f"rules.{key}.ref must be {ref}"))
    return problems


def validate_structure(view: ProjectView) -> list[Problem]:
    problems: list[Problem] = []
    works, phases, roadmaps = view.works, view.phases, view.roadmaps

    # entities -----------------------------------------------------------
    for roadmap in roadmaps.values():
        if not roadmap.display:
            problems.append(Problem("roadmap_invalid", f"{roadmap.id}: display missing"))
        if roadmap.section(ROADMAP_DESIRED_HEADING) is None:
            problems.append(Problem("roadmap_invalid", f"{roadmap.id}: desired state section missing"))
        for forbidden in ("state", "phases", "progress", "current_target", "next_work"):
            if forbidden in roadmap.meta:
                problems.append(Problem("roadmap_invalid", f"{roadmap.id}: forbidden field {forbidden}"))

    for phase in phases.values():
        if not phase.display:
            problems.append(Problem("phase_invalid", f"{phase.id}: display missing"))
        if phase.roadmap_id is None or phase.roadmap_id not in roadmaps:
            problems.append(Problem("phase_invalid", f"{phase.id}: roadmap_id unresolvable"))
        if phase.section(PHASE_DESIRED_HEADING) is None:
            problems.append(Problem("phase_invalid", f"{phase.id}: desired state section missing"))
        for forbidden in ("state", "origin", "works", "progress"):
            if forbidden in phase.meta:
                problems.append(Problem("phase_invalid", f"{phase.id}: forbidden field {forbidden}"))

    for work in works.values():
        if not work.display:
            problems.append(Problem("work_invalid", f"{work.id}: display missing"))
        if work.section(WORK_DESIRED_HEADING) is None:
            problems.append(Problem("work_invalid", f"{work.id}: desired state section missing"))
        if "state" in work.meta or "target" in work.meta:
            problems.append(Problem("work_invalid", f"{work.id}: forbidden state/target field"))
        origin = work.meta.get("origin")
        if not isinstance(origin, dict) or origin.get("type") not in ("roadmap", "standalone"):
            problems.append(Problem("work_invalid", f"{work.id}: origin invalid"))
        else:
            if origin["type"] == "roadmap":
                if origin.get("roadmap_id") not in roadmaps or origin.get("phase_id") not in phases:
                    problems.append(Problem("work_invalid", f"{work.id}: origin refs unresolvable"))
                if work.phase_id is None:
                    problems.append(Problem("work_invalid", f"{work.id}: roadmap Work lacks phase_id"))
            elif work.phase_id is not None:
                problems.append(Problem("work_invalid", f"{work.id}: standalone Work must not have phase_id"))
        if work.phase_id is not None and work.phase_id not in phases:
            problems.append(Problem("work_invalid", f"{work.id}: phase_id unresolvable"))
        kind = work.work_kind
        if kind is not None and kind not in WORK_KINDS:
            problems.append(Problem("work_invalid", f"{work.id}: unknown work_kind {kind}"))
        if kind == "phase_integration_check" and work.phase_id is None:
            problems.append(Problem("work_invalid", f"{work.id}: integration must belong to a Phase"))
        target = work.meta.get("confirmation_target")
        if target is not None:
            if kind != "human_confirmation":
                problems.append(Problem("work_invalid", f"{work.id}: confirmation_target on non human_confirmation Work"))
            targets = target if isinstance(target, list) else [target]
            for item in targets:
                if item == work.id:
                    problems.append(Problem("work_invalid", f"{work.id}: confirmation_target refers to itself"))
                elif item not in works and item not in phases:
                    problems.append(Problem("work_invalid", f"{work.id}: confirmation_target unresolvable: {item}"))

    # roadmap relations ----------------------------------------------------
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()
    for relation in view.roadmap_relations:
        if not is_valid_id(relation.id, "relation"):
            problems.append(Problem("relation_invalid", f"relation id invalid: {relation.id}"))
        if relation.id in seen_ids:
            problems.append(Problem("relation_invalid", f"duplicate relation id: {relation.id}"))
        seen_ids.add(relation.id)
        if relation.type not in ROADMAP_RELATION_TYPES:
            problems.append(Problem("relation_invalid", f"{relation.id}: unknown type {relation.type}"))
            continue
        edge = (relation.type, relation.from_id, relation.to)
        if edge in seen_edges:
            problems.append(Problem("relation_invalid", f"{relation.id}: duplicate edge {edge}"))
        seen_edges.add(edge)
        from_kind = "work" if relation.from_id in works else "phase" if relation.from_id in phases else None
        to_kind = "work" if relation.to in works else "phase" if relation.to in phases else None
        if from_kind is None or to_kind is None:
            problems.append(Problem("relation_invalid", f"{relation.id}: endpoint unresolvable"))
            continue
        if from_kind != to_kind:
            problems.append(Problem("relation_invalid", f"{relation.id}: mixed Phase↔Work relation"))
            continue
        if relation.from_id == relation.to:
            problems.append(Problem("relation_invalid", f"{relation.id}: self relation"))
            continue
        if relation.type == "requires_completion":
            successor_state = view.entity_state_label(relation.to)
            predecessor_state = view.entity_state_label(relation.from_id)
            if successor_state not in EXCLUDED_STATES and predecessor_state in EXCLUDED_STATES:
                problems.append(Problem(
                    "dependency_unreplanned",
                    f"{relation.id}: requires_completion predecessor {relation.from_id} is {predecessor_state}",
                ))
        if relation.type == "return_to":
            from_state = view.entity_state_label(relation.from_id)
            to_state = view.entity_state_label(relation.to)
            if from_state not in EXCLUDED_STATES and to_state in EXCLUDED_STATES:
                problems.append(Problem("return_to_unreplanned", f"{relation.id}: return_to target {relation.to} is {to_state}"))

    # requires_completion cycles ---------------------------------------------
    graph: dict[str, list[str]] = {}
    for relation in view.roadmap_relations:
        if relation.type == "requires_completion":
            graph.setdefault(relation.from_id, []).append(relation.to)
    if _has_cycle(graph):
        problems.append(Problem("dependency_cycle", "requires_completion graph contains a cycle"))

    # related -------------------------------------------------------------
    related_ids: set[str] = set()
    for relation in view.related:
        if relation.id in related_ids or relation.id in seen_ids:
            problems.append(Problem("related_invalid", f"duplicate related id: {relation.id}"))
        related_ids.add(relation.id)
        if relation.type not in RELATED_TYPES:
            problems.append(Problem("related_invalid", f"{relation.id}: unknown type {relation.type}"))
            continue
        if relation.from_id not in works:
            problems.append(Problem("related_invalid", f"{relation.id}: from is not a Work"))
        if not relation.to.strip():
            problems.append(Problem("related_invalid", f"{relation.id}: empty target"))
        if relation.type in CONDITIONAL_RELATED_TYPES:
            message = validate_condition(relation.extra.get("condition"))
            if message:
                problems.append(Problem("related_invalid", f"{relation.id}: {message}"))

    # events -------------------------------------------------------------
    event_ids: set[str] = set()
    terminal_seen: dict[str, str] = {}
    for event in view.events:
        if event.id in event_ids:
            problems.append(Problem("event_invalid", f"duplicate event id: {event.id}"))
        event_ids.add(event.id)
        entity = event.entity
        if entity in works:
            allowed, terminal = WORK_EVENTS, WORK_TERMINAL_EVENTS
        elif entity in phases:
            allowed, terminal = PHASE_EVENTS, PHASE_TERMINAL_EVENTS
        elif entity in roadmaps:
            allowed, terminal = ROADMAP_EVENTS, ROADMAP_TERMINAL_EVENTS
        else:
            problems.append(Problem("event_invalid", f"{event.id}: entity unresolvable: {entity}"))
            continue
        if event.type not in allowed:
            problems.append(Problem("event_invalid", f"{event.id}: {event.type} not allowed for {entity}"))
            continue
        if entity in terminal_seen:
            problems.append(Problem("event_invalid", f"{event.id}: event after terminal {terminal_seen[entity]} on {entity}"))
            continue
        if event.type in terminal:
            terminal_seen[entity] = event.type

    # integration invariant -------------------------------------------------
    for phase in phases.values():
        unfinished = view.unfinished_integrations(phase.id)
        if len(unfinished) > 1:
            problems.append(Problem("integration_invariant", f"{phase.id}: {len(unfinished)} unfinished integrations"))

    return problems


def _has_cycle(graph: dict[str, list[str]]) -> bool:
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(node: str) -> bool:
        if node in done:
            return False
        if node in visiting:
            return True
        visiting.add(node)
        for nxt in graph.get(node, []):
            if visit(nxt):
                return True
        visiting.discard(node)
        done.add(node)
        return False

    return any(visit(node) for node in list(graph))


def _self_hosting_problems(store: ProjectStore) -> list[Problem]:
    """Unsupported self-hosting (rules/git), reported so that full validation never passes it.

    Only full validation reports it. project.yaml validation, which also decides
    whether a Project is established and serves as an operation postcheck,
    stays about the file itself.
    """
    try:
        workline_root = store.workline_root()
    except ValidationError:
        return []  # an unreadable project.yaml is already reported by project.yaml validation
    problem = self_hosting.self_hosting_problem(store.root, workline_root)
    return [Problem(self_hosting.CODE, problem)] if problem else []


def validate_project(store: ProjectStore) -> list[Problem]:
    """Full validation: project.yaml + registry routing + supported topology + structure."""
    problems = validate_project_yaml(store)
    problems.extend(_self_hosting_problems(store))
    try:
        view = ProjectView.load(store)
    except Exception as exc:  # ValidationError from store
        problems.append(Problem("structure_unreadable", str(exc)))
        return problems
    problems.extend(validate_structure(view))
    return problems


