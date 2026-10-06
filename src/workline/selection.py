"""Which Work a Phase or a standalone scope continues with - one pure calculation for every reader.

START's same-Phase continuation and the read-only status projection ask the
same question of the same :class:`~workline.state.ProjectView`, and must not
be able to answer it differently. The answer is computed here, from canonical
state alone, and nothing here reads a file, writes anything, or decides more
than the existing semantics already do:

* a Work in flight is one ``in_progress`` that carries its target, within the
  scope; one of them is what continues, and more than one is a blocker, never
  a winner;
* with none in flight, the startable Works (:meth:`ProjectView.startable_works`)
  are the candidates, less every Work a still-active branch plans to
  ``return_to`` (unless that would leave nothing);
* among the candidates the plan decides through ``planned_next``
  (:meth:`ProjectView.planned_next_preference`); several equally planned are
  an ambiguity, never separated by the order they were read in.

:meth:`WorkContinuation.choose` is that answer in START's terms: the Work, or
the STOP START gives. :attr:`WorkContinuation.selected` is the same answer
without the STOP, for a reader that reports instead of acting.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import StopError
from .state import IN_PROGRESS, ProjectView
from .store import Entity

MULTIPLE_TARGETS = "multiple_targets"


@dataclass(frozen=True)
class WorkContinuation:
    """The continuation of one scope, as computed from one snapshot."""

    view: ProjectView
    in_flight: tuple[Entity, ...]
    #: Startable Works with the ``return_to`` waits taken out - the candidate set the plan chooses from.
    candidates: tuple[Entity, ...]
    #: The candidates the plan recommends equally (:meth:`ProjectView.planned_next_preference`).
    preferred: tuple[Entity, ...]

    @property
    def selected(self) -> Entity | None:
        """The one Work START would continue with, or ``None`` when canonical state names none."""
        if self.in_flight:
            return self.in_flight[0] if len(self.in_flight) == 1 else None
        return self.preferred[0] if len(self.preferred) == 1 else None

    def choose(self) -> Entity | None:
        """The Work START continues with, or the STOP it gives: what START's continuation returns."""
        if len(self.in_flight) > 1:
            raise StopError(
                "multiple Works carry a target: " + ", ".join(w.id for w in self.in_flight), code=MULTIPLE_TARGETS
            )
        if self.in_flight:
            return self.in_flight[0]
        # The plan decides which Work comes next. When it leaves several equally
        # planned, the continuation STOPs instead of separating them by the order
        # they were read in.
        return self.view.choose_startable(list(self.candidates), "Work")


def work_continuation(view: ProjectView, phase_id: str | None, works: list[Entity]) -> WorkContinuation:
    """The continuation of ``works`` - a Phase's effective Works (``phase_id``) or a standalone scope (``None``).

    Exactly the calculation START's continuation makes: the same in-flight
    definition, the same startable rule, the same ``return_to`` filtering and
    the same ``planned_next`` preference.
    """
    in_flight = [
        work for work in works if view.work_state(work.id).state == IN_PROGRESS and view.work_state(work.id).has_target
    ]
    startable = view.startable_works(phase_id, works if phase_id is None else None)
    # a Work that a still-active branch plans to return to waits for that branch
    pending_returns = {
        relation.to
        for relation in view.roadmap_relations
        if relation.type == "return_to"
        and relation.from_id in view.works
        and not view.work_state(relation.from_id).terminal
    }
    candidates = [work for work in startable if work.id not in pending_returns] or startable
    preferred = view.planned_next_preference(candidates) if candidates else []
    return WorkContinuation(view, tuple(in_flight), tuple(candidates), tuple(preferred))


__all__ = ["MULTIPLE_TARGETS", "WorkContinuation", "work_continuation"]
