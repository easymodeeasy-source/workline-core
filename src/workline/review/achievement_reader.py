"""The achievement evidence reader (``WORKLINE_COMPLETION_SPRINT`` §32.39 - §32.41, §14.5): RB5's I/O seam.

The decisions are the pure RB5 core's (:mod:`workline.achievement`); this module
only supplies them with what they decide over - a ``ProjectView`` and the
validated phase_completion evidence a Review reader holds - so ``achievement.py``
stays free of any Review history read (its documented contract).

```text
phase_progression_ready(store, phase_id)   §32.40: generated state + exactly one valid current-basis record
phase_progression(view, reader, phase_id)  the same over any view / reader pair - a committed view and a
                                           CommittedReviewStore for the §32.39 postcommit proof
progression_narrowing(view, reader, ...)   §32.41 / RB8-FC-08: the one startable-Phase narrowing Roadmap and
                                           status both call (achievement.progression_ready_candidates)
candidate_achievement_refs(view, reader,   §14.5 / RB5FB-3: the available achievement evidence refs a Phase
                           phase_id)       Integration Candidate binds at freeze
```

Read-only: no lock, no mutation, no reservation, no write, no Git and no
network. ``state.py`` never calls anything here, and nothing here derives a
Phase or Roadmap lifecycle state: progression-ready is not lifecycle state
(§32.40). A record that cannot be read raises (fail closed); it is never left
out of a decision as if it did not exist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

from ..errors import ValidationError
from ..store import ProjectStore
from .store import ReviewStore

if TYPE_CHECKING:  # pragma: no cover
    from ..achievement import ProgressionNarrowing, ProgressionReadiness
    from ..state import ProjectView
    from ..store import Entity


def phase_progression(view: "ProjectView", reader: Any, phase_id: str) -> "ProgressionReadiness":
    """§32.40 over ``view`` and the validated phase_completion evidence ``reader`` holds."""
    from .. import achievement

    return achievement.phase_progression_decision(view, phase_id, reader.phase_completion_evidence())


def phase_progression_ready(store: ProjectStore, phase_id: str) -> "ProgressionReadiness":
    """§32.40 ``phase_progression_ready(store, phase_id)``: the working Project's state and Review history.

    Legacy Phase complete -> ready under legacy rules; reviewed Phase complete
    -> ready only with exactly one valid current-basis phase_completion record;
    incomplete -> not ready. Generated Phase state itself never reads this.
    """
    from ..state import ProjectView

    return phase_progression(ProjectView.load(store), ReviewStore(store), phase_id)


def progression_narrowing(view: "ProjectView", reader: Any, candidates: Iterable["Entity"]) -> "ProgressionNarrowing":
    """§32.41 / RB8-FC-08: ``candidates`` (``ProjectView.startable_phases``) narrowed by progression-readiness."""
    from .. import achievement

    return achievement.progression_ready_candidates(view, candidates, reader.phase_completion_evidence())


def candidate_achievement_refs(view: "ProjectView", reader: Any, phase_id: str) -> tuple[tuple[str, str, str], ...]:
    """§14.5 / RB5FB-3: the available achievement evidence refs a Phase Integration Candidate of ``phase_id`` binds.

    Scope (the writer decision RB5-FR-bc64c32 left open; no refusal is added
    by it): the one current-basis phase_completion record of every reviewed
    Phase that is a direct ``requires_completion`` predecessor of ``phase_id``
    - the completed Phases whose evidence this Phase's progression relied on
    (§32.41). A legacy predecessor has no evidence and none is invented; a
    reviewed predecessor whose evidence is not ready contributes nothing here
    (its progression gate, not the Candidate, is what refuses). Entries are
    ``(phase_id, achievement_evidence_id, evidence_digest)`` - the body digest,
    the shape of ``achievement.RoadmapBasis.phase_evidence_refs`` - in
    ``(phase_id, achievement_evidence_id)`` order.
    """
    from .. import achievement

    if phase_id not in view.phases:
        raise ValidationError(f"Phase {phase_id} does not exist", code="review_record_invalid")
    evidence = reader.phase_completion_evidence()
    validation = achievement.structural_validation(view)
    found: list[tuple[str, str, str]] = []
    predecessors = sorted({relation.from_id for relation in view.relations_to(phase_id, "requires_completion")
                           if relation.from_id in view.phases})
    for predecessor in predecessors:
        basis = achievement.phase_basis(view, predecessor, validation=validation)
        if not basis.reviewed or not basis.generated_complete:
            continue
        match = achievement.match_current_phase_evidence(basis, evidence)
        if match.status == achievement.EVIDENCE_READY and match.current is not None:
            found.append((predecessor, match.current.achievement_evidence_id, match.current.digest))
    return tuple(sorted(found))


__all__ = ["phase_progression", "phase_progression_ready", "progression_narrowing", "candidate_achievement_refs"]
