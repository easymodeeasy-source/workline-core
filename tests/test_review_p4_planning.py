"""P4 §27.31 (planning): the G1-G6 owner flow of RoadmapPlan under the P4 contract, end to end.

Every flow runs through ``create_roadmap(..., review=PlanningReviewP4(...))`` with scripted, terminating actors:
the discovery actors return a fixed script of claims, the adjudicator a deterministic disposition per claim
code, and the repair actor a complete repaired Candidate content. Nothing here shortcuts production code.
"""

from __future__ import annotations

from typing import Any, Callable

from planning_helpers import PlanningTestCase, plan
from workline import gitcmd
from workline import roadmap as rm
from workline import roadmap_review as rr
from workline.errors import ReconcileRequired, StopError
from workline.review import p4, planning, publication, records, serialize
from workline.review.store import ReviewStore
from workline.review.validate import validate_review

COVERAGE = p4.P4Coverage(("the plan",), ("phase structure",), (), ())


class Discovery:
    """A scripted discovery actor: each call returns the next scripted claims (none once the script is spent)."""

    def __init__(self, *script: tuple[p4.P4Claim, ...], viewpoint: str = "correctness", identity: str = "discovery",
                 version: str = "1", status: str = "completed", coverage: p4.P4Coverage = COVERAGE) -> None:
        self.script = list(script)
        self.viewpoint = viewpoint
        self.identity = identity
        self.version = version
        self.status = status
        self.coverage = coverage
        self.tasks: list[Any] = []

    def __call__(self, task: Any) -> p4.P4DiscoveryReport:
        self.tasks.append(task)
        claims = self.script.pop(0) if self.script else ()
        return p4.P4DiscoveryReport(task.task_id, self.identity, self.version, self.status,
                                    tuple(claims) if self.status == "completed" else (), self.coverage)

    def binding(self) -> p4.DiscoveryBinding:
        return p4.DiscoveryBinding(self.viewpoint, self, self.identity, self.version)


def problem(code: str = "problem", severity: str = "HIGH") -> p4.P4Claim:
    return p4.P4Claim(severity, code, f"the plan has a {code}")


class Adjudicator:
    """A deterministic adjudicator: a claim's code decides its §12.4 outcome.

    ``problem*`` -> Problem HIGH (blocking); ``low`` -> Problem LOW retained; ``improve`` -> Improvement;
    ``human`` -> HUMAN; ``false`` -> unsupported; anything else -> dismissed.
    """

    def __init__(self, identity: str = "adjudicator", version: str = "1",
                 relation: Callable[[Any, dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self.identity = identity
        self.version = version
        self.relation = relation
        self.tasks: list[Any] = []

    def __call__(self, task: Any) -> p4.P4AdjudicationReturn:
        self.tasks.append(task)
        dispositions = []
        repairing = False
        for report in task.reports:
            for index, claim in enumerate(report["claims"]):
                code = claim["code"]
                base = dict(task_id=report["task_id"], claim_index=index, reason="adjudicated by script")
                if code.startswith("problem"):
                    extra = self.relation(task, claim) if self.relation else {}
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=True, requirement_decision_required=False, fails_requirement=True,
                        better_alternative=False, outcome=p4.OUTCOME_PROBLEM, severity="HIGH",
                        statement=claim["message"], semantic_surface="phase-plan", repair_identity=code,
                        disposition=p4.DISPOSITION_REPAIR_REQUIRED, **base, **extra))
                    repairing = True
                elif code == "low":
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=True, requirement_decision_required=False, fails_requirement=True,
                        better_alternative=False, outcome=p4.OUTCOME_PROBLEM, severity="LOW",
                        statement=claim["message"], semantic_surface="phase-plan", repair_identity="low",
                        disposition=p4.DISPOSITION_RETAINED_HISTORY_ONLY, **base))
                elif code == "improve":
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=True, requirement_decision_required=False, fails_requirement=False,
                        better_alternative=True, outcome=p4.OUTCOME_IMPROVEMENT, severity="MID",
                        statement=claim["message"], semantic_surface="phase-plan", repair_identity="improve",
                        disposition=p4.DISPOSITION_FUTURE_WORK_CANDIDATE, **base))
                elif code == "human":
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=True, requirement_decision_required=True, fails_requirement=False,
                        better_alternative=False, outcome=p4.OUTCOME_HUMAN, **base))
                elif code == "false":
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=False, requirement_decision_required=False, fails_requirement=False,
                        better_alternative=False, outcome=p4.OUTCOME_UNSUPPORTED, **base))
                else:
                    dispositions.append(p4.P4ClaimDisposition(
                        supported=True, requirement_decision_required=False, fails_requirement=False,
                        better_alternative=False, outcome=p4.OUTCOME_DISMISSED, **base))
        return p4.P4AdjudicationReturn(
            task.task_id, self.identity, self.version, True, tuple(dispositions),
            repair_purpose="repair the blocking plan problems" if repairing else None,
        )

    def binding(self) -> p4.ActorBinding:
        return p4.ActorBinding(self, self.identity, self.version)


def repaired_desired_state(content: dict[str, Any]) -> dict[str, Any]:
    changed = serialize.canonical_data(content)
    changed["phases"][0]["desired_state"] = changed["phases"][0]["desired_state"] + " (repaired)"
    return changed


class Repairer:
    """A scripted repair actor returning the complete repaired content, never touching the working tree."""

    def __init__(self, change: Callable[[dict[str, Any]], Any] = repaired_desired_state, *, status: str = "completed",
                 identity: str = "repairer", version: str = "1", impact: str = p4.IMPACT_LOCAL,
                 coverage: p4.P4CoverageCheck | None = None, verification: tuple[str, ...] = ("direct_consumers", "focused_tests")) -> None:
        self.change = change
        self.status = status
        self.identity = identity
        self.version = version
        self.impact = impact
        self.coverage = coverage or p4.P4CoverageCheck(
            "the phase desired state is stated precisely", "phase-plan", (), False, True, ("phase a",), True, "local",
        )
        self.verification = verification
        self.tasks: list[Any] = []

    def __call__(self, task: Any) -> p4.P4RepairReturn:
        self.tasks.append(task)
        if self.status != "completed":
            return p4.P4RepairReturn(task.task_id, self.identity, self.version, self.status)
        return p4.P4RepairReturn(
            task.task_id, self.identity, self.version, "completed",
            proposal=self.change(planning.candidate_content(task.source_candidate)),
            repaired_surface=("phase a desired state",), impact_class=self.impact, coverage_check=self.coverage,
            verification=tuple(p4.P4Verification(name, "pass") for name in self.verification),
            causal_summary="restated the phase desired state",
        )

    def binding(self) -> p4.ActorBinding:
        return p4.ActorBinding(self, self.identity, self.version)


def p4_review(discovery: Discovery | tuple[Discovery, ...] | None = None, adjudicator: Adjudicator | None = None,
              repairer: Repairer | None = None, decision: p4.HumanDecision | None = None) -> planning.PlanningReviewP4:
    found = discovery if isinstance(discovery, tuple) else ((discovery or Discovery()),)
    return planning.PlanningReviewP4(
        tuple(item.binding() for item in found), (adjudicator or Adjudicator()).binding(),
        (repairer or Repairer()).binding(), decision,
    )


class P4PlanningCase(PlanningTestCase):
    def reviewed_p4(self, store, review: planning.PlanningReviewP4, the_plan=None):
        return rm.create_roadmap(store, the_plan or plan(), review=review)

    def runs(self, store) -> list[str]:
        return list(ReviewStore(store).run_ids())

    def problems(self, store) -> list[str]:
        return [f"{problem.code}: {problem.message}" for problem in validate_review(store)]


class AuthorizationBranchTests(P4PlanningCase):
    def test_authorization_ready_seals_at_generation_5_and_registers(self) -> None:
        store = self.planning_project()
        discovery = Discovery((problem("note", "LOW"), p4.P4Claim("MID", "improve", "a clearer phase name")))
        result = self.reviewed_p4(store, p4_review(discovery))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        review = ReviewStore(store)
        chain = review.gate_chain(result.review_run_id)
        self.assertEqual(5, len(chain.generations))
        self.assertTrue(chain.latest.sealed)
        receipt = review.read_receipt(str(result.receipt_id))
        self.assertEqual(p4.SEAL_GENERATION, receipt.review_generation)
        consumption = review.read_consumption(str(result.consumption_id))
        self.assertEqual(p4.SEAL_GENERATION, consumption.review_generation)
        # G1 discovery, G2 settle, G3 adjudication accept, G4 settle
        self.assertEqual([p4.TASK_KIND_DISCOVERY], [t["task_kind"] for t in chain.generations[0].accepted_tasks])
        self.assertEqual(p4.TASK_KIND_ADJUDICATION, chain.generations[2].accepted_tasks[-1]["task_kind"])
        report_digest = chain.generations[1].settled_tasks[0]["result_digest"]
        self.assertEqual(report_digest, serialize.digest(review.read_report(report_digest).to_record()))
        adjudication = review.read_adjudication(result.review_run_id)
        self.assertEqual(p4.AUTHORIZATION_READY, adjudication.outcome)
        self.assertEqual(chain.generations[3].adjudication_digest, review.adjudication_digest(result.review_run_id))
        self.assertEqual([p4.OUTCOME_IMPROVEMENT, p4.OUTCOME_DISMISSED],
                         sorted(entry["outcome"] for entry in adjudication.entries))
        self.assertEqual([], self.problems(store))
        self.assertIsNone(publication.barrier_problem(store.root, gitcmd.head_commit(store.root)))
        self.assertEqual([], self.pending(store))
        # the marker is the distinct P4 contract, recorded at the first owner write
        self.assertEqual(1, len(discovery.tasks))
        self.assertEqual(p4.PLANNING_CONTRACT, discovery.tasks[0].request_envelope["review_contract"])

    def test_no_receipt_until_generation_5_and_no_generation_7(self) -> None:
        store = self.planning_project()
        result = self.reviewed_p4(store, p4_review())
        chain = ReviewStore(store).gate_chain(result.review_run_id)
        self.assertEqual([None, None, None, None], [g.receipt_id for g in chain.generations[:4]])
        self.assertEqual([], p4.chain_problems(chain))
        self.assertEqual(p4.SHAPE_SEAL, p4.shape_of(chain))


class RepairBranchTests(P4PlanningCase):
    def test_repair_settles_candidate_n_plus_1_and_a_successor_registers_it(self) -> None:
        store = self.planning_project()
        discovery = Discovery((problem(),), ())
        repairer = Repairer()
        result = self.reviewed_p4(store, p4_review(discovery, repairer=repairer))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        review = ReviewStore(store)
        runs = self.runs(store)
        self.assertEqual(2, len(runs))
        predecessor = [run for run in runs if run != result.review_run_id][0]
        old = review.gate_chain(predecessor)
        self.assertEqual(6, len(old.generations))
        self.assertEqual(p4.SHAPE_REPAIR, p4.shape_of(old))
        self.assertEqual([None] * 6, [g.receipt_id for g in old.generations], "no Receipt on the repair branch")
        batch_id = review.repair_batch_ids()[0]
        batch = review.read_repair_batch(batch_id)
        repair_result = review.read_repair_result(batch_id)
        self.assertEqual(predecessor, batch.source_review_run_id)
        self.assertEqual(old.generations[0].candidate_hash, batch.source_candidate_hash)
        self.assertEqual(2, repair_result.result_candidate_generation)
        new = review.gate_chain(result.review_run_id)
        self.assertEqual(repair_result.result_candidate_hash, new.generations[0].candidate_hash)
        self.assertNotEqual(old.generations[0].candidate_hash, new.generations[0].candidate_hash)
        self.assertEqual({old.generations[0].candidate_hash},
                         {g.candidate_hash for g in old.generations}, "the old Run's Candidate never changes")
        envelope = review.read_task_input(str(new.generations[0].accepted_tasks[0]["task_id"])).request_envelope
        self.assertEqual(2, envelope["candidate_generation"])
        self.assertEqual([{"review_run_id": predecessor, "reason": p4.SET_ASIDE_REPAIRED}], envelope["set_aside_runs"])
        self.assertEqual(predecessor, envelope["succession"]["predecessor_review_run_id"])
        # the registered Roadmap holds the repaired Candidate, never the repair actor's own write
        roadmap_id = result.registration.roadmap_id
        self.assertIn("(repaired)", "\n".join(e.body for e in store.list_entities("phase")))
        self.assertEqual(1, len(repairer.tasks))
        self.assertEqual([], self.problems(store))
        self.assertIsNone(publication.barrier_problem(store.root, gitcmd.head_commit(store.root)))
        self.assertTrue(roadmap_id)

    def test_explicit_repair_failure_never_authorizes_the_old_candidate(self) -> None:
        store = self.planning_project()
        with self.assertRaises(StopError) as raised:
            self.reviewed_p4(store, p4_review(Discovery((problem(),)), repairer=Repairer(status="declined")))
        self.assertEqual(p4.CODE_REPAIR_FAILED, raised.exception.code)
        review = ReviewStore(store)
        run = self.runs(store)[0]
        self.assertEqual(5, len(review.gate_chain(run).generations))
        self.assertEqual((), review.repair_result_ids())
        self.assertEqual((), review.receipt_ids())
        self.assertEqual(1, len(self.pending(store)), "the planning mutation stays pending at the accepted repair")

    def test_unknown_repair_coverage_does_not_settle(self) -> None:
        store = self.planning_project()
        unknown = p4.P4CoverageCheck("x changed", "phase-plan", (), False, False, (), False, "local")
        with self.assertRaises(StopError) as raised:
            self.reviewed_p4(store, p4_review(Discovery((problem(),)), repairer=Repairer(coverage=unknown)))
        self.assertEqual(p4.CODE_REPAIR_COVERAGE_UNKNOWN, raised.exception.code)
        self.assertEqual((), ReviewStore(store).repair_result_ids())


class HumanWaitTests(P4PlanningCase):
    def setUp(self) -> None:
        # RB4 (Orchestrator decision on the P5-default STOP): these assertions are about a P4-ONLY cycle, which a
        # fresh Run no longer is (GAP-A option 3); the test-only seam makes its first Run P4-only exactly as pre-P5
        # code wrote it. The P5 twin, which needs the evidence input, is tests/test_review_p5_human_decisions.py.
        super().setUp()
        from p5_helpers import p4_only_cycle

        seam = p4_only_cycle()
        seam.__enter__()
        self.addCleanup(seam.__exit__, None, None, None)

    def test_human_wait_stops_at_g4_and_a_decision_starts_a_new_run(self) -> None:
        store = self.planning_project()
        result = self.reviewed_p4(store, p4_review(Discovery((p4.P4Claim("HIGH", "human", "which scope?"),))))
        self.assertEqual(rr.STATUS_HUMAN_WAIT, result.status)
        review = ReviewStore(store)
        waiting = result.review_run_id
        self.assertEqual(4, len(review.gate_chain(waiting).generations))
        self.assertEqual((), review.repair_batch_ids(), "no guessed repair")
        self.assertEqual((), review.receipt_ids())
        again = self.reviewed_p4(store, p4_review(Discovery((p4.P4Claim("HIGH", "human", "which scope?"),))))
        self.assertEqual(rr.STATUS_HUMAN_WAIT, again.status, "no decision: still waiting")
        decision = p4.HumanDecision("hd-1", p4.DECISION_CONFIRMED)
        decided = self.reviewed_p4(store, p4_review(decision=decision))
        self.assertEqual(rr.STATUS_REGISTERED, decided.status, decided.detail)
        self.assertNotEqual(waiting, decided.review_run_id)
        envelope = review.read_task_input(
            str(review.gate_chain(decided.review_run_id).generations[0].accepted_tasks[0]["task_id"])
        ).request_envelope
        self.assertIn({"review_run_id": waiting, "reason": p4.SET_ASIDE_HUMAN_DECISION}, envelope["set_aside_runs"])
        self.assertEqual(decision.to_record(), envelope["human_decision"])
        self.assertEqual(4, len(review.gate_chain(waiting).generations), "the old Run is never mutated")


class DispatchTests(P4PlanningCase):
    def test_a_v1_selector_never_continues_a_p4_record(self) -> None:
        store = self.planning_project()
        with self.assertRaises(StopError):
            self.reviewed_p4(store, p4_review(Discovery((problem(),)), repairer=Repairer(status="failed")))
        from planning_helpers import Reviewer

        with self.assertRaises(ReconcileRequired) as raised:
            rm.create_roadmap(store, plan(), review=Reviewer().review())
        self.assertEqual("review_marker_mismatch", raised.exception.reason)
