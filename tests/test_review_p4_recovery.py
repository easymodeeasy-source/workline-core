"""P4 §27.22 / §27.32: current-cycle recovery after runtime cleanup, and fail-closed linkage.

Planning: the planning mutation's runtime record is lost (``.workline/runtime`` removed) at a P4 state; the
same invocation's canonical recovery discovery classifies every matching Run by its own contract - a repaired
predecessor is set aside only on positive successor proof (G-2) - binds the recovered Run's canonical
reservations, and continues to ``registered``. Work: a P4 Work Run is resumed only through the START mutation
that holds it, so after runtime loss it is ``review_recovery_incomplete`` (fail closed), exactly as v1.
"""

from __future__ import annotations

from planning_helpers import Crash, crash_at, plan
from test_review_p4_interruptions_planning import ByGeneration, review
from test_review_p4_planning import Adjudicator, P4PlanningCase, Repairer
from test_review_p4_work import P4WorkCase, WorkRepairer
from test_work_terminal import Crash as WorkCrash
from workline import roadmap as rm
from workline import roadmap_review as rr
from workline import start as st
from workline import start_review as sr
from workline.errors import ReconcileRequired
from workline.review import p4, work_review
from workline.review.store import ReviewStore
from unittest import mock


class PlanningRuntimeCleanupTests(P4PlanningCase):
    def lose_runtime_at(self, name: str, *, after: bool = True, call: int | None = None):
        store = self.planning_project()
        when = None if call is None else (lambda calls, *a, **k: calls == call)
        with crash_at(rr, name, after=after, when=when):
            with self.assertRaises(Crash):
                rm.create_roadmap(store, plan(), review=review())
        self.runtime_gone(store)
        return store

    def finish(self, store) -> rr.ReviewedPlanningResult:
        result = rm.create_roadmap(store, plan(), review=review())
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        self.assertIn("recovered Run", result.detail)
        self.assertEqual([], self.problems(store))
        return result

    def test_g2_discovery_settled_recovers_and_completes_the_cycle(self) -> None:
        store = self.lose_runtime_at("_finish_generation", call=2)
        result = self.finish(store)
        self.assertEqual(2, len(ReviewStore(store).run_ids()))
        self.assertEqual(1, len(ReviewStore(store).receipt_ids()))
        self.assertTrue(result.review_run_id)

    def test_g6_repair_settled_recovers_to_the_successor(self) -> None:
        store = self.lose_runtime_at("_finish_generation", call=6)
        self.finish(store)
        review_store = ReviewStore(store)
        self.assertEqual(2, len(review_store.run_ids()))
        self.assertEqual(1, len(review_store.repair_result_ids()))

    def test_successor_active_recovers_the_successor_and_sets_the_predecessor_aside(self) -> None:
        store = self.lose_runtime_at("_finish_generation", call=7)  # the successor's G1 committed
        result = self.finish(store)
        review_store = ReviewStore(store)
        runs = list(review_store.run_ids())
        self.assertEqual(2, len(runs))
        predecessor = [run for run in runs if run != result.review_run_id][0]
        self.assertEqual(6, len(review_store.gate_chain(predecessor).generations), "never resumed, never mutated")

    def test_g5_sealed_recovers_to_registration(self) -> None:
        store = self.lose_runtime_at("_p4_seal")
        self.finish(store)
        self.assertEqual(1, len(ReviewStore(store).consumption_ids()))

    def test_a_v1_invocation_never_recovers_a_p4_run(self) -> None:
        from planning_helpers import Reviewer

        store = self.lose_runtime_at("_finish_generation", call=2)
        with self.assertRaises(ReconcileRequired) as raised:
            rm.create_roadmap(store, plan(), review=Reviewer().review())
        self.assertEqual(p4.REASON_CONTRACT_MISMATCH, raised.exception.reason)

    def test_contradictory_successor_linkage_fails_closed(self) -> None:
        store = self.lose_runtime_at("_finish_generation", call=7)
        review_store = ReviewStore(store)
        (batch_id,) = review_store.repair_batch_ids()
        path = store.root / ".workline" / "review" / "repair-results" / f"{batch_id}.yaml"
        path.write_bytes(path.read_bytes().replace(b"successor_eligible: true", b"successor_eligible: false"))
        self.commit_all(store, "tamper with the Repair Result", str(path.relative_to(store.root)))
        with self.assertRaises(ReconcileRequired) as raised:
            rm.create_roadmap(store, plan(), review=review())
        self.assertIn(raised.exception.reason, ("review_recovery_incomplete", p4.REASON_LINKAGE_INVALID))


class WorkRuntimeCleanupTests(P4WorkCase):
    def test_a_p4_work_run_without_its_start_mutation_is_incomplete(self) -> None:
        executor = self.completing(write={"out.txt": b"broken\n"}, message="feat: out")
        selector = work_review.WorkReviewP4((ByGeneration().binding(),), Adjudicator().binding(),
                                            WorkRepairer({"out.txt": b"repaired\n"}).binding())
        original = sr._finish_generation

        def crash_after_g2(*args, **kwargs):
            commit = original(*args, **kwargs)
            if (args[1].invocation or {}).get("generation") == 2:
                raise WorkCrash("after G2")
            return commit

        with mock.patch.object(sr, "_finish_generation", side_effect=crash_after_g2):
            with self.assertRaises(WorkCrash):
                st.start(self.store, self.work_id, "single-work", executor, review=selector)
        import shutil

        shutil.rmtree(self.store.root / ".workline" / "runtime")
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work", executor, review=selector)
        self.assertEqual("review_recovery_incomplete", raised.exception.reason)
