"""RB1 post-P4 carry (Control Plane §3, classes C and D): P4 set-aside read from records the real owners wrote.

Every Run here is written by the real P4 owner flow - ``start(..., review=WorkReviewP4(...))`` and
``create_roadmap(..., review=PlanningReviewP4(...))`` - with the scripted, terminating actors of the P4 tests.
Nothing is written by hand. ``status`` is then asked, inside the read-only boundary:

* a repaired predecessor (G6 repair settled) is ``set_aside`` once its successor's request names it as repaired
  and ``p4.proven_successor`` proves the replacement (G-2); the successor keeps its own state;
* a Run waiting at G4 HUMAN_WAIT stays ``open`` until a Human decision's successor names it; then it is
  ``set_aside`` (G-4), and a successor that waits in turn is ``open`` until its own successor names it;
* no valid P4 Run is ever ``invalid``, and no request, reviewer, repair or decision material reaches the output;
* (RB1-R10, planning flows) each Run's blocking obligations are the count of its own adjudication - also once it
  is set aside or consumed - and the pending summary counts only the Runs that are neither (§9.7, §29.18).
"""

from __future__ import annotations

import json
from typing import Any

from p5_helpers import p4_only_cycle
from status_helpers import ReadOnlyBoundary
from test_review_p4_planning import Discovery, P4PlanningCase, Repairer, p4_review
from test_review_p4_work import P4WorkCase, WorkRepairer, work_p4
from workline import roadmap_review as rr
from workline import start as st
from workline import status
from workline.errors import StopError
from workline.review import p4
from workline.review import status as review_status
from workline.review.store import ReviewStore

RAW_CLAIM = "RAW-P4-CLAIM-carry"
RAW_ACTOR = "raw-p4-actor-carry"
RAW_REPAIRER = "raw-p4-repairer-carry"
D1 = p4.HumanDecision("hd-raw-carry-d1", p4.DECISION_CONFIRMED)
D2 = p4.HumanDecision("hd-raw-carry-d2", p4.DECISION_CHANGED)
#: Reviewer, repair and request material the owner flows store; none may reach the status output.
MATERIAL = (
    RAW_CLAIM, RAW_ACTOR, RAW_REPAIRER, D1.decision_id, D2.decision_id, "rewrote the declared result",
    "restated the phase desired state", "set_aside_runs", "succession", "request_envelope", p4.DISCOVERY_INSTRUCTION,
)


def problem_raw() -> tuple[p4.P4Claim, ...]:
    return (p4.P4Claim("HIGH", "problem", RAW_CLAIM),)


def human_raw() -> tuple[p4.P4Claim, ...]:
    return (p4.P4Claim("HIGH", "human", RAW_CLAIM),)


def read_only_entries(case: Any, root: Any) -> tuple[dict[str, dict], str]:
    """The status Run entries, built and rendered inside the read-only boundary (test 11)."""
    with ReadOnlyBoundary(root) as boundary:
        model = status.build_status(root)
        text = status.render_json(model) + status.render_human(model)
    case.assertEqual(boundary.violations, [], boundary.violations)
    case.assertEqual(boundary.paths_written, [], boundary.paths_written)
    case.assertEqual(boundary.changed(), {}, "status changed bytes under the Project")
    case.assertNotIn("fetch", boundary.git_subcommands())
    review = json.loads(status.render_json(model))["review"]
    case.assertEqual(review["runs"]["status"], "available", review)
    entries = {entry["review_run_id"]: entry for entry in review["runs"]["entries"]}
    case.assertEqual([], [entry for entry in entries.values() if entry["state"] == "invalid"],
                     "no valid P4 Run is invalid")
    for leaked in MATERIAL:
        case.assertNotIn(leaked, text, f"{leaked} reached the status output")
    return entries, text


def states(entries: dict[str, dict], *run_ids: str) -> dict[str, tuple[str, int, Any]]:
    return {run_id: (entries[run_id]["state"], entries[run_id]["latest_generation"], entries[run_id]["reason"])
            for run_id in run_ids}


class P4WorkFlowTests(P4WorkCase):
    """Class C: P4 Work successor / set-aside."""

    def test_c_a_repaired_predecessor_is_set_aside_by_its_proven_successor(self) -> None:
        discovery = Discovery(problem_raw(), (), identity=RAW_ACTOR)
        repairer = WorkRepairer({"out.txt": b"repaired\n"}, identity=RAW_REPAIRER)
        result, record = self.complete(self.completing(write={"out.txt": b"broken\n"}, message="feat: out"),
                                       review=work_p4(discovery, repairer=repairer))
        review = ReviewStore(self.store)
        successor = self.consumption(self.head(), record).review_run_id
        (predecessor,) = [run for run in self.runs() if run != successor]
        self.assertEqual(successor, p4.proven_successor(review, predecessor, review.gate_chain(predecessor)))
        entries, _ = read_only_entries(self, self.store.root)
        self.assertEqual(states(entries, predecessor, successor),
                         {predecessor: ("set_aside", 6, None), successor: ("consumed", 5, None)})
        self.assertEqual([], self.problems())

    # Post-RB4 carry: a P4-ONLY cycle (the test-only seam), so a resume with only p4.HumanDecision is the P4 flow
    # this class covers; a P5 HUMAN_WAIT resume needs Human Decision Evidence (§28.18, test_review_p5_human_decisions)
    @p4_only_cycle()
    def test_c_human_decision_successors_set_their_waiting_predecessors_aside(self) -> None:
        discovery = Discovery(human_raw(), human_raw(), (), identity=RAW_ACTOR)
        executor = self.completing(write={"out.txt": b"out\n"}, message="feat: out")
        # A waits at G4: a wait alone sets nothing aside
        with self.assertRaises(StopError) as raised:
            st.start(self.store, self.work_id, "single-work", executor, review=work_p4(discovery))
        self.assertEqual(p4.CODE_HUMAN_WAIT, raised.exception.code)
        (a,) = self.runs()
        entries, _ = read_only_entries(self, self.store.root)
        self.assertEqual(states(entries, a), {a: ("open", 4, None)})
        # D1 exits A's wait; B is born from it and waits in turn: B keeps its own state
        with self.assertRaises(StopError) as raised:
            st.start(self.store, self.work_id, "single-work", executor, review=work_p4(discovery, decision=D1))
        self.assertEqual(p4.CODE_HUMAN_WAIT, raised.exception.code)
        (b,) = [run for run in self.runs() if run != a]
        entries, _ = read_only_entries(self, self.store.root)
        self.assertEqual(states(entries, a, b), {a: ("set_aside", 4, None), b: ("open", 4, None)})
        # D2 exits B's wait; C authorizes and the START completes
        result, record = self.complete(executor, review=work_p4(discovery, decision=D2))
        c = self.consumption(self.head(), record).review_run_id
        entries, _ = read_only_entries(self, self.store.root)
        self.assertEqual(states(entries, a, b, c),
                         {a: ("set_aside", 4, None), b: ("set_aside", 4, None), c: ("consumed", 5, None)})
        self.assertEqual([], self.problems())


class P4PlanningFlowTests(P4PlanningCase):
    """Class D: P4 planning successor / set-aside."""

    def test_d_a_repaired_predecessor_is_set_aside_by_its_proven_successor(self) -> None:
        store = self.planning_project()
        result = self.reviewed_p4(store, p4_review(Discovery(problem_raw(), (), identity=RAW_ACTOR),
                                                   repairer=Repairer(identity=RAW_REPAIRER)))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        successor = result.review_run_id
        (predecessor,) = [run for run in self.runs(store) if run != successor]
        review = ReviewStore(store)
        self.assertEqual(successor, p4.proven_successor(review, predecessor, review.gate_chain(predecessor)))
        entries, _ = read_only_entries(self, store.root)
        self.assertEqual(states(entries, predecessor, successor),
                         {predecessor: ("set_aside", 6, None), successor: ("consumed", 5, None)})
        # RB1-R10: the repaired predecessor's one blocking Problem is history; the consumed successor has none
        self.assertEqual({run: entries[run]["blocking_obligations"] for run in (predecessor, successor)},
                         {predecessor: {"status": "available", "count": 1},
                          successor: {"status": "available", "count": 0}})
        self.assertEqual(review_status.review_status(store)["pending_obligations"],
                         {"status": "available", "count": 0, "review_run_ids": []})
        self.assertEqual([], self.problems(store))

    # Post-RB4 carry: a P4-ONLY cycle, as in test_c_human_decision_successors_set_their_waiting_predecessors_aside
    @p4_only_cycle()
    def test_d_a_human_decision_sets_the_waiting_run_aside(self) -> None:
        store = self.planning_project()
        waited = self.reviewed_p4(store, p4_review(Discovery(human_raw(), identity=RAW_ACTOR)))
        self.assertEqual(rr.STATUS_HUMAN_WAIT, waited.status, waited.detail)
        waiting = waited.review_run_id
        entries, _ = read_only_entries(self, store.root)
        self.assertEqual(states(entries, waiting), {waiting: ("open", 4, None)})
        # RB1-R10: the one unresolved HUMAN decision of the waiting Run is the one current blocking obligation
        self.assertEqual(entries[waiting]["blocking_obligations"], {"status": "available", "count": 1})
        self.assertEqual(review_status.review_status(store)["pending_obligations"],
                         {"status": "available", "count": 1, "review_run_ids": [waiting]})
        decided = self.reviewed_p4(store, p4_review(Discovery(identity=RAW_ACTOR), decision=D1))
        self.assertEqual(rr.STATUS_REGISTERED, decided.status, decided.detail)
        entries, _ = read_only_entries(self, store.root)
        self.assertEqual(states(entries, waiting, decided.review_run_id),
                         {waiting: ("set_aside", 4, None), decided.review_run_id: ("consumed", 5, None)})
        self.assertEqual({run: entries[run]["blocking_obligations"] for run in (waiting, decided.review_run_id)},
                         {waiting: {"status": "available", "count": 1},
                          decided.review_run_id: {"status": "available", "count": 0}})
        self.assertEqual(review_status.review_status(store)["pending_obligations"],
                         {"status": "available", "count": 0, "review_run_ids": []})
        self.assertEqual([], self.problems(store))


if __name__ == "__main__":
    import unittest

    unittest.main()
