"""RB4 / P5 §28.27 (planning): history written by the planning owner at each exact transition boundary.

Every flow runs ``create_roadmap(..., review=PlanningReviewP4(...))`` with the scripted, terminating actors of
:mod:`test_review_p4_planning`. A fresh Run binds the P5-capable policy (GAP-A option 3) and its owner writes:

* G4: one Finding summary per normalized Finding, beside the adjudication (§28.8);
* G6 repair: the Repair summary and the repaired Run summary, beside the Repair Result (§28.9);
* G2: the ``not_authorized`` Run summary in the settlement that makes discovery non-authorizing (GAP-E);
* the Consumption stage: the consumed Run summary first, then the Consumption, and Km carries both (§28.6);
* G4 of a later Run: accepted cross-run relation claims as immutable new facts (GAP-C).

A P4-only cycle (the test-only seam ``p4_only_cycle``) writes no history and Km is the Consumption alone.
"""

from __future__ import annotations

from typing import Any

from p5_helpers import at_head, committed_paths, first_envelope, p4_only_cycle
from test_review_p4_planning import Adjudicator, Discovery, P4PlanningCase, Repairer, p4_review, problem
from workline import roadmap_review as rr
from workline.review import history, p4, paths, serialize
from workline.review.store import ReviewStore

LOW = p4.P4Claim("LOW", "low", "a minor wording note")
IMPROVE = p4.P4Claim("MID", "improve", "a clearer phase name")


class P5PlanningTests(P4PlanningCase):
    def history_clean(self, store: Any) -> None:
        self.assertEqual([], history.history_problems(ReviewStore(store), work_ids=None))
        self.assertEqual([], self.problems(store))

    def test_a_fresh_run_is_p5_and_its_g4_and_consumption_write_its_history(self) -> None:
        store = self.planning_project()
        result = self.reviewed_p4(store, p4_review(Discovery((LOW, IMPROVE))))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        review = ReviewStore(store)
        run = str(result.review_run_id)
        envelope = first_envelope(review, run)
        self.assertEqual(p4.P5_POLICY_ID, envelope["policy_id"])
        self.assertEqual(history.HISTORY_CONTRACT, envelope["history_contract"])
        chain = review.gate_chain(run)
        self.assertEqual(p4.policy_hash(p4.P5_POLICY_ID), chain.generations[0].effective_policy_hash)
        # G4: one Finding summary per normalized Finding, exactly the adjudication's
        adjudication = review.read_adjudication(run)
        self.assertEqual(2, len(adjudication.findings))
        for finding in adjudication.findings:
            summary = review.read_history(paths.HISTORY_FINDINGS, str(finding["finding_id"]))
            self.assertEqual((finding["category"], finding["severity"], finding["disposition"]),
                             (summary.category, summary.severity, summary.disposition))
            self.assertTrue(at_head(store.root, paths.history_finding_rel(summary.finding_id)))
        # the Consumption stage: the consumed Run summary bound to the exact Consumption, Km carries both
        summary = review.read_history(paths.HISTORY_RUNS, run)
        self.assertEqual((history.DISPOSITION_CONSUMED, result.consumption_id, result.receipt_id),
                         (summary.durable_disposition, summary.consumption_id, summary.receipt_id))
        self.assertEqual(sorted([paths.history_run_rel(run), paths.consumption_rel(str(result.consumption_id))]),
                         committed_paths(store.root))
        self.assertEqual(history.HISTORY_COMPLETE,
                         history.rb5_reference(review, run, history_contract=history.HISTORY_CONTRACT).history_status)
        self.history_clean(store)

    def test_a_p4_only_km_of_the_consumption_alone_is_published_to_the_destination(self) -> None:
        """OD2-T2 end to end: a P4-only Run's Km is the Consumption alone and publishes exactly as before."""
        store = self.planning_project(remote=True)
        with p4_only_cycle():
            result = self.reviewed_p4(store, p4_review(Discovery((LOW,))))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        self.assertEqual([paths.consumption_rel(str(result.consumption_id))], committed_paths(store.root))
        self.assertEqual(self.head(store), self.remote_head(), "exactly Km is published")
        self.assertEqual([], self.problems(store))

    def test_a_p5_km_of_summary_and_consumption_is_published_to_the_destination(self) -> None:
        """OD2-T3 end to end: the planning push validator publishes the P5 Km (Run summary + Consumption) only after
        it proves the Run P5-capable from the Run's canonical stored identity in Km (OD-2)."""
        store = self.planning_project(remote=True)
        result = self.reviewed_p4(store, p4_review(Discovery((LOW,))))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        self.assertEqual(sorted([paths.history_run_rel(str(result.review_run_id)),
                                 paths.consumption_rel(str(result.consumption_id))]), committed_paths(store.root))
        self.assertEqual(self.head(store), self.remote_head(), "exactly Km is published")
        self.history_clean(store)

    def test_a_repair_writes_the_repair_and_repaired_summaries_in_its_g6(self) -> None:
        store = self.planning_project()
        result = self.reviewed_p4(store, p4_review(Discovery((problem(),), ()), repairer=Repairer()))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        review = ReviewStore(store)
        predecessor = [run for run in review.run_ids() if run != result.review_run_id][0]
        batch_id = review.repair_batch_ids()[0]
        repaired = review.read_history(paths.HISTORY_RUNS, predecessor)
        self.assertEqual((history.DISPOSITION_REPAIRED, batch_id), (repaired.durable_disposition, repaired.repair_batch_id))
        repair = review.read_history(paths.HISTORY_REPAIRS, batch_id)
        self.assertEqual(review.repair_result_digest(batch_id), repair.result_digest)
        # the successor keeps its cycle's stored family (GAP-A item 5)
        self.assertEqual(p4.P5_POLICY_ID, first_envelope(review, str(result.review_run_id))["policy_id"])
        self.assertEqual(p4.P5_POLICY_ID, first_envelope(review, predecessor)["policy_id"])
        self.history_clean(store)

    def test_a_declined_discovery_writes_not_authorized_in_the_same_g2(self) -> None:
        store = self.planning_project()
        result = self.reviewed_p4(store, p4_review(Discovery(status="declined")))
        self.assertEqual(rr.STATUS_NOT_AUTHORIZED, result.status, result.detail)
        review = ReviewStore(store)
        summary = review.read_history(paths.HISTORY_RUNS, str(result.review_run_id))
        self.assertEqual((history.DISPOSITION_NOT_AUTHORIZED, 2), (summary.durable_disposition, summary.gate_generation))
        self.assertIn(paths.history_run_rel(str(result.review_run_id)), committed_paths(store.root),
                      "the summary is committed by the G2 generation commit itself")
        self.history_clean(store)

    def test_a_p4_only_cycle_writes_no_history_and_km_is_the_consumption_alone(self) -> None:
        store = self.planning_project()
        with p4_only_cycle():
            result = self.reviewed_p4(store, p4_review(Discovery((LOW,))))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        review = ReviewStore(store)
        envelope = first_envelope(review, str(result.review_run_id))
        self.assertEqual(p4.POLICY_ID, envelope["policy_id"])
        self.assertNotIn("history_contract", envelope, "a P4-only request is byte for byte the pre-P5 one")
        self.assertFalse((store.root / paths.HISTORY_DIR).exists())
        self.assertEqual([paths.consumption_rel(str(result.consumption_id))], committed_paths(store.root))
        self.assertEqual(history.HISTORY_NOT_REQUIRED,
                         history.rb5_reference(review, str(result.review_run_id), history_contract=None).history_status)
        self.assertEqual([], self.problems(store))


class RelatingAdjudicator(Adjudicator):
    """The script adjudicator, which - given prior history - claims one unresolved repair-induced relation."""

    def __init__(self) -> None:
        super().__init__()
        self.claims: list[Any] = []

    def __call__(self, task: Any) -> p4.P4AdjudicationReturn:
        returned = super().__call__(task)
        repairs = [item for item in task.prior_history if item["family"] == paths.HISTORY_REPAIRS]
        lows = [(report["task_id"], index) for report in task.reports
                for index, claim in enumerate(report["claims"]) if claim["code"] == "low"]
        if not repairs or not lows:
            return returned
        claim = p4.P5RelationClaim(
            relation_type=history.RELATION_REPAIR_INDUCED, source_task_id=lows[0][0], source_claim_index=lows[0][1],
            target_family=paths.HISTORY_REPAIRS, target_id=repairs[0]["id"], status=history.CAUSAL_UNRESOLVED,
            rationale="the wording note may follow the earlier repair", semantic_surface="phase-plan",
        )
        self.claims.append(claim)
        return p4.P4AdjudicationReturn(returned.task_id, returned.adjudicator_identity, returned.adjudicator_version,
                                       returned.objective_holds, returned.dispositions, returned.coverage_gaps,
                                       returned.repair_purpose, returned.strategy_change_class, (claim,))


class P5RelationTests(P4PlanningCase):
    def test_a_cross_run_relation_claim_is_an_immutable_new_g4_fact(self) -> None:
        store = self.planning_project()
        adjudicator = RelatingAdjudicator()
        result = self.reviewed_p4(store, p4_review(Discovery((problem(),), (LOW,)), adjudicator=adjudicator,
                                                   repairer=Repairer()))
        self.assertEqual(rr.STATUS_REGISTERED, result.status, result.detail)
        self.assertEqual(1, len(adjudicator.claims))
        review = ReviewStore(store)
        successor = str(result.review_run_id)
        # GAP-C: the adjudicator got the deterministic validated reference set, bound by digest in its request
        adjudication_task = review.gate_chain(successor).generations[2].accepted_tasks[-1]
        request = review.read_task_input(str(adjudication_task["task_id"])).request_envelope
        families = sorted(item["family"] for item in request["prior_history"])
        self.assertEqual([paths.HISTORY_FINDINGS, paths.HISTORY_REPAIRS, paths.HISTORY_RUNS], families)
        self.assertEqual(p4.P5_ADJUDICATION_INSTRUCTION, request["instruction"])
        (relation_id,) = review.history_ids(paths.HISTORY_RELATIONS)
        relation = review.read_history(paths.HISTORY_RELATIONS, relation_id)
        self.assertEqual((history.RELATION_REPAIR_INDUCED, history.CAUSAL_UNRESOLVED),
                         (relation.relation_type, relation.status))
        self.assertFalse(relation.confirmed, "only supported relations are confirmed")
        finding = review.read_history(paths.HISTORY_FINDINGS, relation.source.id)
        self.assertEqual((relation_id,), finding.relation_ids)
        self.assertEqual(successor, finding.review_run_id)
        # the endpoint it points at is never rewritten: the predecessor's Repair summary is still its G6 bytes
        repair = review.read_history(paths.HISTORY_REPAIRS, relation.target.id)
        self.assertEqual(relation.target.digest, serialize.digest(repair.to_record()))
        self.assertEqual([], history.history_problems(review, work_ids=None))
