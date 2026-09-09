"""Generated state.

No state is stored in canonical files. Work / Phase / Roadmap state, targets,
effective current-plan Work sets, unfinished integrations, startable Works and
Phases, and Phase completion are all generated here from events, affiliation
(``phase_id`` / ``roadmap_id``) and relations.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .store import Entity, Event, ProjectStore, Relation

UNSTARTED = "unstarted"
IN_PROGRESS = "in_progress"
HELD = "held"
COMPLETED = "completed"
CANCELLED = "cancelled"
PLAN_EXCLUDED = "plan_excluded"
ACTIVE = "active"
ACHIEVED = "achieved"
COMPLETE = "complete"

EXCLUDED_STATES = (CANCELLED, PLAN_EXCLUDED)


@dataclass(frozen=True)
class WorkState:
    state: str
    has_target: bool

    @property
    def terminal(self) -> bool:
        return self.state in (COMPLETED, CANCELLED, PLAN_EXCLUDED)

    @property
    def excluded(self) -> bool:
        return self.state in EXCLUDED_STATES


def derive_work_state(events: list[Event]) -> WorkState:
    state = UNSTARTED
    has_target = False
    for event in events:
        kind = event.type
        if kind == "work_started":
            state = IN_PROGRESS
        elif kind == "work_target_added":
            has_target = True
        elif kind == "work_target_removed":
            has_target = False
        elif kind == "work_held":
            state = HELD
        elif kind == "work_resumed":
            state = IN_PROGRESS
        elif kind == "work_completed":
            state = COMPLETED
            has_target = False
        elif kind == "work_cancelled":
            state = CANCELLED
            has_target = False
        elif kind == "plan_excluded":
            state = PLAN_EXCLUDED
            has_target = False
    return WorkState(state, has_target)


def derive_phase_lifecycle(events: list[Event]) -> str:
    state = ACTIVE
    for event in events:
        if event.type == "phase_held":
            state = HELD
        elif event.type == "phase_resumed":
            state = ACTIVE
        elif event.type == "phase_cancelled":
            state = CANCELLED
        elif event.type == "plan_excluded":
            state = PLAN_EXCLUDED
    return state


def derive_roadmap_lifecycle(events: list[Event]) -> str:
    state = ACTIVE
    for event in events:
        if event.type == "roadmap_held":
            state = HELD
        elif event.type == "roadmap_resumed":
            state = ACTIVE
        elif event.type == "roadmap_cancelled":
            state = CANCELLED
        elif event.type == "roadmap_achieved":
            state = ACHIEVED
    return state


@dataclass(frozen=True)
class PhaseCompletion:
    complete: bool
    reasons: tuple[str, ...] = ()


@dataclass
class ProjectView:
    """A consistent in-memory snapshot of a Project's canonical files."""

    store: ProjectStore
    works: dict[str, Entity] = field(default_factory=dict)
    phases: dict[str, Entity] = field(default_factory=dict)
    roadmaps: dict[str, Entity] = field(default_factory=dict)
    roadmap_relations: list[Relation] = field(default_factory=list)
    related: list[Relation] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)

    @classmethod
    def load(cls, store: ProjectStore) -> "ProjectView":
        view = cls(store)
        view.works = {entity.id: entity for entity in store.list_entities("work")}
        view.phases = {entity.id: entity for entity in store.list_entities("phase")}
        view.roadmaps = {entity.id: entity for entity in store.list_entities("roadmap")}
        view.roadmap_relations = store.read_roadmap_relations()
        view.related = store.read_related()
        view.events = store.read_events()
        return view

    # events ---------------------------------------------------------------
    def events_for(self, entity_id: str) -> list[Event]:
        return [event for event in self.events if event.entity == entity_id]

    # work -----------------------------------------------------------------
    def work_state(self, work_id: str) -> WorkState:
        return derive_work_state(self.events_for(work_id))

    def phase_lifecycle(self, phase_id: str) -> str:
        return derive_phase_lifecycle(self.events_for(phase_id))

    def roadmap_lifecycle(self, roadmap_id: str) -> str:
        return derive_roadmap_lifecycle(self.events_for(roadmap_id))

    def phase_works(self, phase_id: str) -> list[Entity]:
        return [work for work in self.works.values() if work.phase_id == phase_id]

    def effective_works(self, phase_id: str) -> list[Entity]:
        """Effective current-plan Work set: phase members minus cancelled / plan_excluded."""
        return [work for work in self.phase_works(phase_id) if not self.work_state(work.id).excluded]

    def unfinished_integrations(self, phase_id: str) -> list[Entity]:
        return [
            work
            for work in self.effective_works(phase_id)
            if work.work_kind == "phase_integration_check" and self.work_state(work.id).state != COMPLETED
        ]

    def integrations(self, phase_id: str) -> list[Entity]:
        return [work for work in self.effective_works(phase_id) if work.work_kind == "phase_integration_check"]

    # relations -----------------------------------------------------------
    def relations_from(self, entity_id: str, rel_type: str | None = None) -> list[Relation]:
        return [r for r in self.roadmap_relations if r.from_id == entity_id and (rel_type is None or r.type == rel_type)]

    def relations_to(self, entity_id: str, rel_type: str | None = None) -> list[Relation]:
        return [r for r in self.roadmap_relations if r.to == entity_id and (rel_type is None or r.type == rel_type)]

    def related_from(self, work_id: str, rel_type: str | None = None) -> list[Relation]:
        return [r for r in self.related if r.from_id == work_id and (rel_type is None or r.type == rel_type)]

    def entity_state_label(self, entity_id: str) -> str:
        if entity_id in self.works:
            return self.work_state(entity_id).state
        if entity_id in self.phases:
            return self.phase_state(entity_id)
        if entity_id in self.roadmaps:
            return self.roadmap_lifecycle(entity_id)
        return "unresolvable"

    def unsatisfied_dependencies(self, entity_id: str) -> list[tuple[Relation, str]]:
        """Incoming ``requires_completion`` whose predecessor is not completed.

        A cancelled / plan_excluded predecessor never satisfies the dependency.
        """
        result: list[tuple[Relation, str]] = []
        for relation in self.relations_to(entity_id, "requires_completion"):
            label = self.entity_state_label(relation.from_id)
            if label not in (COMPLETED, COMPLETE):
                result.append((relation, label))
        return result

    def dependencies_satisfied(self, entity_id: str) -> bool:
        return not self.unsatisfied_dependencies(entity_id)

    # phase ----------------------------------------------------------------
    def phase_completion(self, phase_id: str) -> PhaseCompletion:
        reasons: list[str] = []
        lifecycle = self.phase_lifecycle(phase_id)
        if lifecycle in EXCLUDED_STATES:
            reasons.append(f"phase is {lifecycle}")
        effective = self.effective_works(phase_id)
        if not effective:
            reasons.append("no effective current-plan Work")
        for work in effective:
            state = self.work_state(work.id).state
            if state != COMPLETED:
                reasons.append(f"{work.id} is {state}")
        if not self.integrations(phase_id):
            reasons.append("no phase_integration_check in effective current-plan")
        if self.unfinished_integrations(phase_id):
            reasons.append("unfinished integration remains")
        for work in effective:
            for relation, label in self.unsatisfied_dependencies(work.id):
                if label in EXCLUDED_STATES:
                    reasons.append(f"{relation.id}: predecessor {relation.from_id} is {label} (replan required)")
        return PhaseCompletion(not reasons, tuple(reasons))

    def phase_state(self, phase_id: str) -> str:
        lifecycle = self.phase_lifecycle(phase_id)
        if lifecycle in EXCLUDED_STATES or lifecycle == HELD:
            return lifecycle
        if self.phase_completion(phase_id).complete:
            return COMPLETE
        works = self.phase_works(phase_id)
        if any(self.work_state(work.id).state != UNSTARTED for work in works):
            return IN_PROGRESS
        return UNSTARTED

    def startable_works(self, phase_id: str | None, works: list[Entity] | None = None) -> list[Entity]:
        """Works that can be started now within one Phase (or a standalone set).

        Startable: in the effective current-plan set, generated state
        ``unstarted`` or ``in_progress`` without target, and every incoming
        ``requires_completion`` predecessor completed. Held Works need an
        explicit resume and are not auto-selected.
        """
        candidates = works if works is not None else self.effective_works(phase_id or "")
        if phase_id is not None and self.phase_lifecycle(phase_id) != ACTIVE:
            return []
        result: list[Entity] = []
        for work in candidates:
            state = self.work_state(work.id)
            if state.state == UNSTARTED or (state.state == IN_PROGRESS and not state.has_target):
                if self.dependencies_satisfied(work.id):
                    result.append(work)
        return result

    # roadmap --------------------------------------------------------------
    def roadmap_phases(self, roadmap_id: str) -> list[Entity]:
        return [phase for phase in self.phases.values() if phase.roadmap_id == roadmap_id]

    def active_phases(self, roadmap_id: str) -> list[Entity]:
        return [phase for phase in self.roadmap_phases(roadmap_id) if self.phase_lifecycle(phase.id) not in EXCLUDED_STATES]

    def startable_phases(self, roadmap_id: str) -> list[Entity]:
        if self.roadmap_lifecycle(roadmap_id) != ACTIVE:
            return []
        result: list[Entity] = []
        for phase in self.roadmap_phases(roadmap_id):
            state = self.phase_state(phase.id)
            if state in (COMPLETE, HELD, CANCELLED, PLAN_EXCLUDED):
                continue
            if self.dependencies_satisfied(phase.id):
                result.append(phase)
        return result

    def all_active_phases_complete(self, roadmap_id: str) -> bool:
        active = self.active_phases(roadmap_id)
        return bool(active) and all(self.phase_state(phase.id) == COMPLETE for phase in active)
