"""RB10-N4 repair (Control Plane: N4_POSITIVE_ADMISSION_MISSING_FOR_REVIEW_RUN_DISPOSITION).

A Human recovery disposition is admissible only for a Work Review Run, and that is enforced at the shared Review
Run disposition validity boundary (``recovery_disposition.review_run_problem``), not only by the operation. The
operation never creates a record for a Planning Run - ``recovery.disposition_outcome`` leaves it ``unresolved`` and
``dispose_recovery`` refuses ``recovery_disposition_target_ineligible``. A structurally canonical record for one,
written by hand and committed, must therefore hold nothing for every reader:

* ``review_run_target_state`` is ``invalid`` (the Run's own generation-1 ``review_kind`` decides, never the record);
* validation reports ``recovery_disposition_conflict``;
* the real Planning recovery path (``recovery.discover``, exactly as the planning owner calls it, and the planning
  operation end to end) fails closed (``review_recovery_incomplete``) - the Run is never set aside and never
  propagated as ``disposed_by_human``;
* Review status never reports it ``set_aside`` by ``human_disposition``.

The Planning Run is a real P4 planning Run left at G4 without a Receipt (its owner died before the seal and the
runtime area was lost), with an exact reproducible ``review-run-recovery-v1`` witness. Work Review dispositions and
the Receipt / witness refusals are unchanged (``test_recovery_disposition_review``).
"""

from __future__ import annotations

from typing import Any

from planning_helpers import Crash, crash_at
from test_review_p4_planning import Discovery, P4PlanningCase, p4_review
from workline import recovery_disposition as rd
from workline import roadmap_review as rr
from workline.errors import ReconcileRequired, StopError
from workline.review import p4, planning, recovery, work_review
from workline.review.status import SET_ASIDE_SOURCE_HUMAN, review_status
from workline.review.store import ReviewStore

LOW = p4.P4Claim("LOW", "low", "a minor wording note")
REASON = "the Human abandons this planning attempt"


def never_classified(found: Any) -> Any:
    raise AssertionError(f"Run {found.review_run_id} reached classification; discovery must fail closed before it")


class PlanningRunDispositionTests(P4PlanningCase):
    def left_behind_planning_run(self, store: Any) -> str:
        """A real P4 planning Run at G4 with no Receipt, its owner mutation lost (runtime loss)."""
        with crash_at(rr, "_p4_seal"), self.assertRaises(Crash):
            self.reviewed_p4(store, p4_review(Discovery((LOW,))))
        (run,) = self.runs(store)
        review = ReviewStore(store)
        chain = review.gate_chain(run)
        self.assertEqual(planning.KIND_ROADMAP, chain.generations[0].review_kind)
        self.assertNotEqual(work_review.REVIEW_KIND, chain.generations[0].review_kind)
        self.assertEqual(4, chain.latest.generation)
        self.assertIsNone(rd.current_receipt(review, chain), "no current unsuperseded Receipt")
        self.runtime_gone(store)
        return run

    def hand_written(self, store: Any, run: str) -> rd.Disposition:
        """The canonical v1 record the operation would write - but written by hand and committed, never through it."""
        review = ReviewStore(store)
        found = rd.Disposition(rd.KIND_REVIEW_RUN, run, rd.review_run_state_digest(review, run), REASON)
        rel = rd.disposition_rel(run)
        (store.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (store.root / rel).write_bytes(rd.render(found).encode("utf-8"))
        self.commit_all(store, "a hand-written Human recovery disposition", rel)
        self.assertEqual(found, rd.read_disposition(store, run), "structurally canonical v1 bytes")
        self.assertEqual(found.target_state_digest, rd.review_run_state_digest(ReviewStore(store), run),
                         "the exact review-run-recovery-v1 witness reproduces")
        self.assertIs(True, rd.committed(store, rel))
        return found

    def test_the_operation_never_disposes_a_planning_run(self) -> None:
        store = self.planning_project()
        run = self.left_behind_planning_run(store)
        head = self.head(store)
        with self.assertRaises(StopError) as refused:
            rd.dispose_recovery(store.root, run, REASON, confirmed=True)
        self.assertEqual("recovery_disposition_target_ineligible", refused.exception.code, refused.exception.message)
        self.assertFalse((store.root / rd.disposition_rel(run)).exists(), "nothing is written")
        self.assertEqual(head, self.head(store), "nothing is committed")

    def test_a_hand_written_planning_run_disposition_holds_nothing_for_any_reader(self) -> None:
        store = self.planning_project()
        run = self.left_behind_planning_run(store)
        self.hand_written(store, run)
        with self.subTest("the shared validity boundary: invalid, by the Run's own review kind"):
            state = rd.review_run_target_state(store, run)
            self.assertEqual(rd.STATE_INVALID, state.state, state)
            self.assertIn(f"admissible only for a {work_review.REVIEW_KIND} Run", state.problem)
        with self.subTest("validation: recovery_disposition_conflict"):
            problems = rd.namespace_problems(store)
            self.assertIn("recovery_disposition_conflict", [code for code, _ in problems], problems)
        with self.subTest("Review status: never set aside by a Human disposition"):
            entry = {item["review_run_id"]: item for item in review_status(store)["runs"]["entries"]}[run]
            self.assertNotEqual(SET_ASIDE_SOURCE_HUMAN, entry["set_aside_source"], entry)
            self.assertNotEqual("set_aside", entry["state"], entry)
        with self.subTest("the real Planning recovery discovery fails closed before any classification"):
            first = ReviewStore(store).gate_chain(run).generations[0]
            with self.assertRaises(ReconcileRequired) as raised:
                recovery.discover(store, first.review_kind, first.operation_identity, currency=never_classified,
                                  contract=planning.P4_CONTRACT)
            self.assertEqual("review_recovery_incomplete", raised.exception.reason, raised.exception)
            self.assertIn(run, str(raised.exception))
            self.assertIn("does not hold", str(raised.exception))
            self.assertNotIn("disposed_by_human", str(raised.exception))
        with self.subTest("the planning operation end to end: refused, nothing begins, the Run is not set aside"):
            head, runs = self.head(store), self.runs(store)
            with self.assertRaises(StopError) as refused:
                self.reviewed_p4(store, p4_review(Discovery((LOW,))))
            self.assertIn(refused.exception.code, ("reconcile_required",), refused.exception)
            self.assertEqual((head, runs), (self.head(store), self.runs(store)), "no commit and no new Run")
            entry = {item["review_run_id"]: item for item in review_status(store)["runs"]["entries"]}[run]
            self.assertNotEqual(SET_ASIDE_SOURCE_HUMAN, entry["set_aside_source"], entry)
