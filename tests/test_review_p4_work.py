"""P4 §27.31 (Work): the G1-G6 START owner flow under the Work P4 contract, through terminalization.

The flows run through ``start(..., review=WorkReviewP4(...))`` with scripted, terminating actors (the
discovery and adjudication actors of :mod:`test_review_p4_planning`; a Work repair actor here that only
returns complete bytes and never writes the working tree). The terminal path is the real one: K1, the
generation-5 Receipt's Consumption, K2 and both pushes.
"""

from __future__ import annotations

from typing import Any

from test_review_p4_planning import Adjudicator, Discovery, problem
from test_work_terminal import TerminalCase
from workline import start as st
from workline.errors import ReconcileRequired, StopError
from workline.review import p4, work_review
from workline.review.store import ReviewStore
from workline.review.validate import validate_review

from test_work_review_runtime import git


class WorkRepairer:
    """A scripted Work repair actor: the complete new bytes of declared result paths, nothing written."""

    def __init__(self, files: dict[str, bytes], *, identity: str = "repairer", version: str = "1",
                 status: str = "completed") -> None:
        self.files = files
        self.identity = identity
        self.version = version
        self.status = status
        self.tasks: list[Any] = []

    def __call__(self, task: Any) -> p4.P4RepairReturn:
        self.tasks.append(task)
        if self.status != "completed":
            return p4.P4RepairReturn(task.task_id, self.identity, self.version, self.status)
        return p4.P4RepairReturn(
            task.task_id, self.identity, self.version, "completed", proposal={"files": dict(self.files), "message": None},
            repaired_surface=tuple(sorted(self.files)), impact_class=p4.IMPACT_LOCAL,
            coverage_check=p4.P4CoverageCheck("the result bytes are corrected", "work-result", (), False, True,
                                              tuple(sorted(self.files)), True, "local"),
            verification=(p4.P4Verification("direct_consumers", "pass"), p4.P4Verification("focused_tests", "pass")),
            causal_summary="rewrote the declared result",
        )

    def binding(self) -> p4.ActorBinding:
        return p4.ActorBinding(self, self.identity, self.version)


def work_p4(discovery: Discovery | None = None, adjudicator: Adjudicator | None = None,
            repairer: WorkRepairer | None = None, decision: p4.HumanDecision | None = None) -> work_review.WorkReviewP4:
    return work_review.WorkReviewP4(
        ((discovery or Discovery()).binding(),), (adjudicator or Adjudicator()).binding(),
        (repairer or WorkRepairer({"out.txt": b"repaired\n"})).binding(), decision,
    )


class P4WorkCase(TerminalCase):
    def runs(self) -> list[str]:
        return list(ReviewStore(self.store).run_ids())

    def problems(self) -> list[str]:
        return [f"{problem.code}: {problem.message}" for problem in validate_review(self.store)]


class WorkAuthorizationTests(P4WorkCase):
    def test_authorization_ready_seals_at_5_and_terminalizes_through_k1_and_k2(self) -> None:
        discovery = Discovery((p4.P4Claim("LOW", "low", "a minor note"),))
        result, record = self.complete(self.completing(write={"out.txt": b"out\n"}, message="feat: out"),
                                       review=work_p4(discovery))
        self.assertEqual(work_review.P4_CONTRACT, record["invocation"]["review_contract"])
        review = ReviewStore(self.store)
        (run_id,) = self.runs()
        chain = review.gate_chain(run_id)
        self.assertEqual(5, len(chain.generations))
        self.assertTrue(chain.latest.sealed)
        k2 = self.head()
        k1 = git(self.root, "rev-parse", "HEAD~1")
        self.assertEqual(self.delta(k1), [("A", "out.txt")])
        consumption = self.consumption(k2, record)
        self.assertEqual(p4.SEAL_GENERATION, consumption.review_generation)
        self.assertEqual(run_id, consumption.review_run_id)
        self.assertEqual(k1, consumption.authorized_result_commit_sha)
        completed = [event for event in self.events_for(k2) if event["type"] == "work_completed"]
        self.assertEqual(p4.SEAL_GENERATION, completed[-1]["review_generation"])
        self.assertEqual([], self.problems())
        self.assertEqual(k2, self.remote_main())
        self.assertEqual(p4.AUTHORIZATION_READY, review.read_adjudication(run_id).outcome)


class WorkRepairTests(P4WorkCase):
    def test_repair_adopts_candidate_n_plus_1_and_the_successor_terminalizes_it(self) -> None:
        discovery = Discovery((problem(),), ())
        repairer = WorkRepairer({"out.txt": b"repaired\n"})
        result, record = self.complete(self.completing(write={"out.txt": b"broken\n"}, message="feat: out"),
                                       review=work_p4(discovery, repairer=repairer))
        self.assertEqual(1, len(repairer.tasks))
        review = ReviewStore(self.store)
        runs = self.runs()
        self.assertEqual(2, len(runs))
        k2 = self.head()
        consumption = self.consumption(k2, record)
        predecessor = [run for run in runs if run != consumption.review_run_id][0]
        old = review.gate_chain(predecessor)
        self.assertEqual(6, len(old.generations))
        self.assertEqual(p4.SHAPE_REPAIR, p4.shape_of(old))
        new = review.gate_chain(consumption.review_run_id)
        self.assertEqual(5, len(new.generations))
        k1 = git(self.root, "rev-parse", "HEAD~1")
        self.assertEqual(b"repaired\n", (self.root / "out.txt").read_bytes())
        self.assertEqual("repaired", git(self.root, "show", f"{k1}:out.txt"))
        self.assertEqual({old.generations[0].candidate_hash}, {g.candidate_hash for g in old.generations})
        envelope = review.read_task_input(str(new.generations[0].accepted_tasks[0]["task_id"])).request_envelope
        self.assertEqual([{"review_run_id": predecessor, "reason": p4.SET_ASIDE_REPAIRED}], envelope["set_aside_runs"])
        self.assertEqual(2, envelope["candidate_generation"])
        self.assertEqual(old.generations[0].operation_identity, new.generations[0].operation_identity, "G-7")
        self.assertEqual([], self.problems())

    def test_a_proposal_outside_the_declared_result_surface_never_settles(self) -> None:
        repairer = WorkRepairer({"elsewhere.txt": b"x\n"})
        with self.assertRaises(StopError) as raised:
            st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"broken\n"}),
                     review=work_p4(Discovery((problem(),)), repairer=repairer))
        self.assertEqual(p4.CODE_REPAIR_INVALID, raised.exception.code)
        self.assertEqual((), ReviewStore(self.store).repair_result_ids())
        self.assertEqual(b"broken\n", (self.root / "out.txt").read_bytes(), "the repair actor never writes the tree")


class WorkHumanWaitTests(P4WorkCase):
    def setUp(self) -> None:
        # RB4 (Orchestrator decision on the P5-default STOP): these assertions are about a P4-ONLY cycle, which a
        # fresh Run no longer is (GAP-A option 3); the test-only seam makes its first Run P4-only exactly as pre-P5
        # code wrote it. The P5 twin, which needs the evidence input, is tests/test_review_p5_human_decisions.py.
        super().setUp()
        from p5_helpers import p4_only_cycle

        seam = p4_only_cycle()
        seam.__enter__()
        self.addCleanup(seam.__exit__, None, None, None)

    def test_human_wait_keeps_the_start_pending_and_a_decision_resumes_it(self) -> None:
        human = Discovery((p4.P4Claim("HIGH", "human", "which format?"),), ())
        executor = self.completing(write={"out.txt": b"out\n"}, message="feat: out")
        with self.assertRaises(StopError) as raised:
            st.start(self.store, self.work_id, "single-work", executor, review=work_p4(human))
        self.assertEqual(p4.CODE_HUMAN_WAIT, raised.exception.code)
        self.assertEqual(1, len(self.pending()), "the START stays pending at HUMAN_WAIT")
        (waiting,) = self.runs()
        decision = p4.HumanDecision("hd-7", p4.DECISION_CONFIRMED)
        result, record = self.complete(executor, review=work_p4(human, decision=decision))
        consumption = self.consumption(self.head(), record)
        self.assertNotEqual(waiting, consumption.review_run_id)
        review = ReviewStore(self.store)
        envelope = review.read_task_input(
            str(review.gate_chain(consumption.review_run_id).generations[0].accepted_tasks[0]["task_id"])
        ).request_envelope
        self.assertEqual([{"review_run_id": waiting, "reason": p4.SET_ASIDE_HUMAN_DECISION}], envelope["set_aside_runs"])
        self.assertEqual(decision.to_record(), envelope["human_decision"])
        self.assertEqual(4, len(review.gate_chain(waiting).generations))


class WorkDispatchTests(P4WorkCase):
    def test_a_v1_selector_never_continues_a_p4_start_and_the_lock_names_p4(self) -> None:
        human = Discovery((p4.P4Claim("HIGH", "human", "which format?"),))
        with self.assertRaises(StopError):
            st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                     review=work_p4(human))
        record = self.pending()[0]
        with self.assertRaises(ReconcileRequired) as raised:
            st.start(self.store, self.work_id, "single-work", self.completing(write={"out.txt": b"out\n"}),
                     review=self.review())
        self.assertEqual("review_marker_mismatch", raised.exception.reason)
        self.assertEqual(record, self.pending()[0], "the P4 record is left untouched")
        from workline import start_review

        self.assertEqual({"review_contract": work_review.P4_CONTRACT}, start_review.lock_details(work_p4()))
        self.assertEqual({"review_contract": "review-v1-work-v1"}, start_review.lock_details(self.review()))
