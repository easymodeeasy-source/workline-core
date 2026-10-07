"""RB5 test doubles: in-memory Projects for the pure Phase integration / achievement functions.

The views are built from plain ``store.Entity`` objects: the marker is read through
the read-only ``Entity.phase_review_contract`` property (§32.2), the raw frontmatter
value when present, ``None`` when absent. (The test-only ``MarkedEntity`` that stood
in for that property before the post-RB6 integration is gone - integration I-2,
row R03.) Nothing here is production code.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from workline.state import ProjectView  # noqa: E402
from workline.store import (  # noqa: E402
    PHASE_DESIRED_HEADING,
    ROADMAP_BACKGROUND_HEADING,
    ROADMAP_DESIRED_HEADING,
    WORK_DESIRED_HEADING,
    Entity,
    Event,
    Relation,
    render_body,
)

INTEGRATION = "phase_integration_check"
CONFIRMATION = "human_confirmation"
V1 = "phase-integration-review-v1"


def ident(prefix: str, number: int) -> str:
    """A valid Workline ID of ``prefix`` whose ULID part is ``number`` in decimal digits."""
    return f"{prefix}_{number:026d}"


class ViewBuilder:
    """Builds a structurally valid in-memory Project, one Roadmap by default."""

    def __init__(self) -> None:
        self.counter = 0
        self.roadmaps: dict[str, Entity] = {}
        self.phases: dict[str, Entity] = {}
        self.works: dict[str, Entity] = {}
        self.relations: list[Relation] = []
        self.related: list[Relation] = []
        self.events: list[Event] = []
        self.roadmap_id = self.roadmap()

    def _next(self, prefix: str, number: int | None = None) -> str:
        if number is None:
            self.counter += 1
            number = self.counter
        return ident(prefix, number)

    def roadmap(self, name: str = "Roadmap", desired: str = "The Roadmap goal holds") -> str:
        roadmap_id = self._next("r")
        body = render_body(name, [(ROADMAP_BACKGROUND_HEADING, "background"), (ROADMAP_DESIRED_HEADING, desired)])
        meta = {"id": roadmap_id, "display": f"R-{len(self.roadmaps) + 1:02d}", "type": "roadmap"}
        self.roadmaps[roadmap_id] = Entity(roadmap_id, "roadmap", meta, body, f".workline/roadmaps/{roadmap_id}.md")
        return roadmap_id

    def phase(self, name: str = "Phase", desired: str = "The Phase goal holds", *, roadmap_id: str | None = None,
              display: str | None = None) -> str:
        phase_id = self._next("p")
        meta = {"id": phase_id, "display": display or f"P-{len(self.phases) + 1:02d}", "type": "phase",
                "roadmap_id": roadmap_id or self.roadmap_id}
        body = render_body(name, [(PHASE_DESIRED_HEADING, desired)])
        self.phases[phase_id] = Entity(phase_id, "phase", meta, body, f".workline/phases/{phase_id}.md")
        return phase_id

    def work(self, phase_id: str, name: str = "Work", *, kind: str | None = None, marker: Any = None,
             target: Any = None, desired: str | None = None, number: int | None = None) -> str:
        work_id = self._next("w", number)
        roadmap_id = self.phases[phase_id].meta["roadmap_id"]
        meta: dict[str, Any] = {
            "id": work_id, "display": f"W-{len(self.works) + 1:02d}", "type": "work", "phase_id": phase_id,
            "origin": {"type": "roadmap", "roadmap_id": roadmap_id, "phase_id": phase_id},
        }
        if kind is not None:
            meta["work_kind"] = kind
        if marker is not None:
            meta["phase_review_contract"] = marker
        if target is not None:
            meta["confirmation_target"] = target
        body = render_body(name, [(WORK_DESIRED_HEADING, desired or f"{name} done")])
        self.works[work_id] = Entity(work_id, "work", meta, body, f".workline/works/{work_id}.md")
        return work_id

    def integration(self, phase_id: str, *, marker: Any = V1, number: int | None = None, name: str = "Integration") -> str:
        return self.work(phase_id, name, kind=INTEGRATION, marker=marker, number=number)

    def confirmation(self, phase_id: str, target: str, *, edge: bool = True) -> str:
        work_id = self.work(phase_id, "Confirmation", kind=CONFIRMATION, target=target)
        if edge:
            self.requires(target, work_id)
        return work_id

    def requires(self, from_id: str, to: str) -> str:
        relation = Relation(self._next("rel"), "requires_completion", from_id, to)
        self.relations.append(relation)
        return relation.id

    def must_read(self, work_id: str, to: str = "README.md") -> str:
        relation = Relation(self._next("rel"), "must_read", work_id, to)
        self.related.append(relation)
        return relation.id

    def event(self, entity: str, kind: str) -> str:
        event = Event(self._next("evt"), kind, entity, "2026-10-06T00:00:00Z")
        self.events.append(event)
        return event.id

    def start(self, work_id: str) -> None:
        self.event(work_id, "work_started")

    def complete(self, *work_ids: str) -> None:
        for work_id in work_ids:
            self.event(work_id, "work_started")
            self.event(work_id, "work_completed")

    def cancel(self, work_id: str) -> None:
        self.event(work_id, "work_cancelled")

    def exclude(self, work_id: str) -> None:
        self.event(work_id, "plan_excluded")

    def view(self) -> ProjectView:
        return ProjectView(
            None,  # type: ignore[arg-type]
            works=dict(sorted(self.works.items())),
            phases=dict(sorted(self.phases.items())),
            roadmaps=dict(sorted(self.roadmaps.items())),
            roadmap_relations=list(self.relations),
            related=list(self.related),
            events=list(self.events),
        )


def reviewed_phase(builder: ViewBuilder, *, works: int = 2, complete: bool = True,
                   confirmation: bool = False) -> tuple[str, list[str], str, str | None]:
    """A Phase entered with ``works`` normal Works -> one reviewed integration (and optionally a confirmation)."""
    phase_id = builder.phase()
    normal = [builder.work(phase_id, f"W{index + 1}") for index in range(works)]
    integration_id = builder.integration(phase_id)
    for work_id in normal:
        builder.requires(work_id, integration_id)
    confirmation_id = builder.confirmation(phase_id, integration_id) if confirmation else None
    if complete:
        builder.complete(*normal, integration_id)
        if confirmation_id:
            builder.complete(confirmation_id)
    return phase_id, normal, integration_id, confirmation_id
