"""P4 §27.36 (planning): the interruption / recovery matrix, rows 1-21, over the repair-then-authorize cycle.

Each row kills the process (``Crash``, never a StopError, so nothing is abandoned on its way out) at one
instant of a RoadmapPlan P4 cycle - Run N discovers a blocking Problem, is repaired, and its successor N+1
authorizes and registers - and then runs the same invocation again. Every retry must end ``registered`` with:
the same Runs, task, Finding, Repair Batch and successor IDs the interrupted attempt reserved; no duplicate raw
report, adjudication, Repair Batch / Result, Receipt or Consumption; no v1 fallback; no newest/timestamp choice.

The actors are deterministic per Candidate generation (read from the canonical request), so a retry asks the
same question and gets the same answer.
"""

from __future__ import annotations

from typing import Any

from planning_helpers import Crash, crash_at, plan
from test_review_p4_planning import Adjudicator, P4PlanningCase, Repairer, problem
from workline import roadmap as rm
from workline import roadmap_review as rr
from workline.review import p4, planning
from workline.review.store import ReviewStore

COVERAGE = p4.P4Coverage(("the plan",), ("phase structure",), (), ())


class ByGeneration:
    """A discovery actor answering by the Candidate generation its canonical request binds: N has a Problem."""

    def __init__(self, identity: str = "discovery", version: str = "1") -> None:
        self.identity = identity
        self.version = version
        self.tasks: list[Any] = []

    def __call__(self, task: Any) -> p4.P4DiscoveryReport:
        self.tasks.append(task)
        claims = (problem(),) if task.request_envelope["candidate_generation"] == 1 else ()
        return p4.P4DiscoveryReport(task.task_id, self.identity, self.version, "completed", claims, COVERAGE)

    def binding(self) -> p4.DiscoveryBinding:
        return p4.DiscoveryBinding("correctness", self, self.identity, self.version)


def review() -> planning.PlanningReviewP4:
    return planning.PlanningReviewP4((ByGeneration().binding(),), Adjudicator().binding(), Repairer().binding())


def at_call(n: int):
    return lambda calls, *args, **kwargs: calls == n


#: (row, target module, function, after?, which call) - the 21 instants of §27.36.
ROWS = (
    (1, rr, "_p4_reserve_run_ids", True, None),            # P4 Run reservation
    (2, rr, "_p4_accept", False, None),                    # G1 before effect
    (3, rr, "_finish_generation", True, 1),                # G1 commit
    (4, p4, "report_record", True, 1),                     # one discovery return before G2
    (5, rr, "_finish_generation", False, 2),               # raw report creation before G2 completes
    (6, rr, "_finish_generation", True, 2),                # G2 commit
    (7, rr, "_p4_accept_adjudication", True, None),        # G3 adjudication TaskInput accepted
    (8, p4, "normalize_adjudication", True, 1),            # adjudicator return before G4
    (9, rr, "_finish_generation", False, 4),               # G4 adjudication record creation
    (10, rr, "_finish_generation", True, 4),               # G4 commit
    (11, p4, "repair_batch", True, 1),                     # Repair Batch ID reservation
    (12, rr, "_finish_generation", False, 5),              # G5 Repair Batch / TaskInput partial apply
    (13, rr, "_finish_generation", True, 5),               # G5 commit
    (14, p4, "repair_return_problems", True, 1),           # repair external return before G6
    (15, rr, "_finish_generation", False, 6),              # Candidate N+1 / Repair Result partial apply
    (16, rr, "_finish_generation", True, 6),               # G6 commit
    (17, rr, "_p4_reserve_successor", True, None),         # successor reservation
    (18, rr, "_p4_begin_successor", False, None),          # successor before G1
    (19, p4, "report_record", True, 2),                    # successor discovery cycle
    (20, rr, "_p4_seal", True, None),                      # P4 G5 seal
    (21, rr, "_c2_kp", False, None),                       # existing owner persistence / Consumption
)


class InterruptionCase(P4PlanningCase):
    def interrupted(self, target: Any, name: str, after: bool, call: int | None) -> None:
        store = self.planning_project()
        with crash_at(target, name, after=after, when=None if call is None else at_call(call)):
            with self.assertRaises(Crash):
                rm.create_roadmap(store, plan(), review=review())
        pending = [record for record in self.pending(store) if (record.get("invocation") or {}).get("operation") == "roadmap-create"]
        self.assertEqual(1, len(pending), "the planning mutation is kept for the retry")
        reserved = dict(pending[0].get("reserved_ids") or {})
        result = rm.create_roadmap(store, plan(), review=review())
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        self.assertEqual([], self.pending(store))
        self.assert_cycle(store, reserved, result)

    def assert_cycle(self, store, reserved: dict[str, str], result) -> None:
        review = ReviewStore(store)
        runs = list(review.run_ids())
        self.assertEqual(2, len(runs), "Run N and its one successor, never a third")
        self.assertEqual(2, len(review.report_digests()), "one raw report per Run, no duplicate")
        self.assertEqual(sorted(runs), sorted(review.adjudication_run_ids()))
        self.assertEqual(1, len(review.repair_batch_ids()))
        self.assertEqual(1, len(review.repair_result_ids()))
        self.assertEqual(1, len(review.receipt_ids()))
        self.assertEqual(1, len(review.consumption_ids()))
        for key, identifier in reserved.items():
            if key.startswith(("review-run:", "review-successor-run:")):
                self.assertIn(identifier, runs, f"the retry kept {key}")
            elif key.startswith("review-repair-batch:"):
                self.assertEqual([identifier], list(review.repair_batch_ids()))
            elif key.startswith("review-finding:"):
                run_id = key.split(":")[1]
                self.assertIn(identifier, [f["finding_id"] for f in review.read_adjudication(run_id).findings])
        successor = [run for run in runs if review.gate_chain(run).latest.sealed]
        self.assertEqual([result.review_run_id], successor)
        envelope = review.read_task_input(
            str(review.gate_chain(result.review_run_id).generations[0].accepted_tasks[0]["task_id"])
        ).request_envelope
        self.assertEqual(2, envelope["candidate_generation"], "no v1 fallback, no fresh generation-1 Candidate")


def _make(row: int, target: Any, name: str, after: bool, call: int | None):
    def test(self: InterruptionCase) -> None:
        self.interrupted(target, name, after, call)

    test.__name__ = f"test_row_{row:02d}_{name.strip('_')}{'_after' if after else ''}"
    return test


class InterruptionRows01To11(InterruptionCase):
    pass


class InterruptionRows12To21(InterruptionCase):
    pass


for _row, _target, _name, _after, _call in ROWS:
    _holder = InterruptionRows01To11 if _row <= 11 else InterruptionRows12To21
    _test = _make(_row, _target, _name, _after, _call)
    setattr(_holder, _test.__name__, _test)
# A module-level name left bound to a TestCase class is collected again under that name: unbind every loop name.
del _holder, _test, _row, _target, _name, _after, _call
