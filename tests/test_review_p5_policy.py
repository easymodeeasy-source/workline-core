"""RB4 / P5 GAP-A option 3 at unit level: explicit policy-family dispatch, P4-only bytes unchanged, P5 inputs.

* the P4 request builders, called with the P4 policy explicitly, return exactly what they returned with none;
* a P5 request binds the P5 policy, the history contract and its P5-only fields, and is recognized only with the
  history contract this build implements - never inferred;
* a TaskInput binds the policy its request names; a new first Run binds the current default, and the test seam
  ``p4_only_cycle`` is the only way a test creates P4-only Runs;
* GAP-C relation claims: refused on a P4-only Run, validated against the adjudication and the bound references,
  ordered by the owner, never by the return;
* GAP-G evidence inputs: refused before the lock when they disagree with the Human decision or are not public-safe.
"""

from __future__ import annotations

from dataclasses import replace
import unittest

from p5_helpers import p4_only_cycle, p5_only_cycle
from workline.errors import StopError, ValidationError
from workline.review import history, p4, paths, serialize
from test_review_p4_adjudication import adjudicate, bound, disposition, report, returned

TASK_A = "rtk_01ARZ3NDEKTSV4RRFFQ69G5FA1"


def discovery(**overrides: object) -> dict:
    arguments = dict(review_contract=p4.WORK_CONTRACT, review_kind="work-result-v1", viewpoint="correctness",
                     candidate={"c": 1}, context={"x": 1}, requirement={"r": 1}, candidate_generation=1,
                     succession=None, set_aside_runs=[], human_decision=None)
    arguments.update(overrides)
    return p4.discovery_request(**arguments)


class PolicyFamilyTests(unittest.TestCase):
    def test_p4_requests_are_byte_identical_with_the_policy_named_explicitly(self) -> None:
        self.assertEqual(discovery(), discovery(policy_id=p4.POLICY_ID))
        adjudication = dict(review_contract=p4.WORK_CONTRACT, review_kind="work-result-v1",
                            review_run_id="rr_01ARZ3NDEKTSV4RRFFQ69G5FAV", candidate_hash="a" * 64,
                            candidate_generation=1, review_context_hash="b" * 64, requirement={"r": 1}, reports=[],
                            prior=p4.NO_PRIOR, evidence_ids=[])
        self.assertEqual(p4.adjudication_request(**adjudication),
                         p4.adjudication_request(**adjudication, policy_id=p4.POLICY_ID))
        self.assertNotIn(history.HISTORY_CONTRACT_KEY, discovery())
        self.assertEqual(p4.policy_hash(), p4.policy_hash(p4.POLICY_ID))
        self.assertEqual(p4.policy_record(), p4.policy_named(p4.POLICY_ID))

    def test_a_p5_request_binds_the_policy_and_the_history_contract_and_is_recognized_only_with_it(self) -> None:
        found = discovery(policy_id=p4.P5_POLICY_ID)
        self.assertEqual(set(discovery()) | {"history_contract", "set_aside_summaries", "decision_evidence"}, set(found))
        self.assertEqual((p4.P5_POLICY_ID, history.HISTORY_CONTRACT), (found["policy_id"], found["history_contract"]))
        self.assertEqual(p4.WORK_CONTRACT, p4.contract_of_envelope(found))
        self.assertEqual(p4.P5_POLICY_ID, p4.policy_of_envelope(found))
        without = {key: value for key, value in found.items() if key != "history_contract"}
        self.assertIsNone(p4.contract_of_envelope(without), "never P5 without the explicit history contract")
        self.assertIsNone(p4.contract_of_envelope({**found, "history_contract": "review-v1-history-v9"}))
        # a P4 request is read exactly as before, whatever else it carries
        self.assertEqual(p4.POLICY_ID, p4.policy_of_envelope({**discovery(), "history_contract": "x"}))

    def test_the_policies_are_distinct_and_only_p5_binds_history(self) -> None:
        self.assertNotEqual(p4.policy_hash(p4.POLICY_ID), p4.policy_hash(p4.P5_POLICY_ID))
        self.assertIsNone(p4.history_contract_of_policy(p4.POLICY_ID))
        self.assertEqual(history.HISTORY_CONTRACT, p4.history_contract_of_policy(p4.P5_POLICY_ID))
        self.assertIsNone(p4.policy_named("review-v1-p4-policy-v9"))
        with self.assertRaises(ValidationError):
            p4.policy_hash("review-v1-p4-policy-v9")

    def test_a_p4_only_request_binds_no_history_writes(self) -> None:
        with self.assertRaises(ValidationError):
            discovery(set_aside_summaries=[{"review_run_id": "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV", "digest": "a" * 64}])

    def test_a_task_input_binds_the_policy_its_request_names(self) -> None:
        arguments = dict(task_id=TASK_A, task_slot="p4-discovery.correctness", task_kind=p4.TASK_KIND_DISCOVERY,
                         actor_identity="a", actor_version="1", candidate_hash="a" * 64,
                         candidate_material_digest="b" * 64, review_context_hash="e" * 64, accepted_generation=1)
        found = p4.task_input(envelope=discovery(policy_id=p4.P5_POLICY_ID), policy_id=p4.P5_POLICY_ID, **arguments)
        self.assertEqual(p4.policy_hash(p4.P5_POLICY_ID), found.effective_policy_hash)
        self.assertEqual(p4.P5_POLICY_ID, p4.policy_of_task_input(found))
        with self.assertRaises(ValidationError):
            p4.task_input(envelope=discovery(policy_id=p4.P5_POLICY_ID), **arguments)

    def test_a_new_first_run_binds_the_current_default_and_the_test_seam_is_the_only_way_back(self) -> None:
        # R6-1: the current default is the P6-capable family policy; the test-only seams are the only way back
        self.assertEqual(p4.P6_POLICY_ID, p4.new_run_policy())
        with p4_only_cycle():
            self.assertEqual(p4.POLICY_ID, p4.new_run_policy())
        with p5_only_cycle():
            self.assertEqual(p4.P5_POLICY_ID, p4.new_run_policy())
        self.assertEqual(p4.P6_POLICY_ID, p4.new_run_policy())


class RelationClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.found = adjudicate(bound(report(TASK_A, "correctness", [("LOW", "a", "c"), ("LOW", "b", "d")])),
                                returned(disposition(TASK_A, 0, p4.OUTCOME_IMPROVEMENT, severity="LOW",
                                                     repair_identity="one"),
                                         disposition(TASK_A, 1, p4.OUTCOME_IMPROVEMENT, severity="LOW",
                                                     repair_identity="two")))
        self.references = [{"family": paths.HISTORY_FINDINGS, "id": "rfd_01ARZ3NDEKTSV4RRFFQ69G5F99", "digest": "c" * 64},
                           {"family": paths.HISTORY_RUNS, "id": "rr_01ARZ3NDEKTSV4RRFFQ69G5F99", "digest": "d" * 64}]

    def claim(self, index: int = 0, **overrides: object) -> p4.P5RelationClaim:
        base = dict(relation_type=history.RELATION_CROSS_RUN_RECURRENCE, source_task_id=TASK_A, source_claim_index=index,
                    target_family=paths.HISTORY_FINDINGS, target_id="rfd_01ARZ3NDEKTSV4RRFFQ69G5F99",
                    status=history.CAUSAL_UNRESOLVED, rationale="the same wording issue as before",
                    semantic_surface="wording")
        base.update(overrides)
        return p4.P5RelationClaim(**base)

    def drafts(self, *claims: p4.P5RelationClaim, policy: str = p4.P5_POLICY_ID):
        answer = p4.P4AdjudicationReturn(TASK_A, "adjudicator", "1", True, relation_claims=claims)
        return p4.relation_drafts(answer, self.found, self.references, policy_id=policy)

    def test_a_p4_only_adjudication_returns_no_relation_claim(self) -> None:
        self.assertEqual((), self.drafts(policy=p4.POLICY_ID))
        with self.assertRaises(StopError) as raised:
            self.drafts(self.claim(), policy=p4.POLICY_ID)
        self.assertEqual(p4.CODE_ADJUDICATION_INVALID, raised.exception.code)

    def test_claims_are_validated_against_the_findings_and_the_bound_references(self) -> None:
        for bad in (self.claim(source_claim_index=7), self.claim(target_id="rfd_01ARZ3NDEKTSV4RRFFQ69G5F98")):
            with self.subTest(bad=bad), self.assertRaises(StopError):
                self.drafts(bad)
        with self.assertRaises(StopError):
            self.drafts(self.claim(), self.claim())

    def test_the_order_is_the_owners_never_the_returns(self) -> None:
        first = self.claim(0)
        second = self.claim(1, relation_type=history.RELATION_DOWNSTREAM_ESCAPE, target_family=paths.HISTORY_RUNS,
                            target_id="rr_01ARZ3NDEKTSV4RRFFQ69G5F99")
        self.assertEqual([d.order_key for d in self.drafts(first, second)],
                         [d.order_key for d in self.drafts(second, first)])


class DecisionEvidenceInputTests(unittest.TestCase):
    def evidence(self, **overrides: object) -> p4.DecisionEvidence:
        base = dict(affected_review_run_id="rr_01ARZ3NDEKTSV4RRFFQ69G5FAV", affected_candidate_hash="a" * 64,
                    decision_id="hd-1", decision_disposition=p4.DECISION_CONFIRMED, affected_entries=(),
                    question_summary="which scope", decision_summary="confirmed as written",
                    authority_identity="work:w_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                    action_class=history.ACTION_RESUME_CONFIRMED, source_digests=("b" * 64,))
        base.update(overrides)
        return p4.DecisionEvidence(**base)

    def test_a_well_formed_input_agreeing_with_the_decision_has_no_problem(self) -> None:
        decision = p4.HumanDecision("hd-1", p4.DECISION_CONFIRMED)
        self.assertEqual([], p4.decision_evidence_problems((self.evidence(),), decision))
        self.assertEqual([], p4.decision_evidence_problems((), None), "no evidence is the P4-only default")

    def test_inputs_that_disagree_or_are_unsafe_are_refused_before_the_lock(self) -> None:
        decision = p4.HumanDecision("hd-1", p4.DECISION_CONFIRMED)
        for name, items, given in (
            ("no decision", (self.evidence(),), None),
            ("another decision", (self.evidence(decision_id="hd-2"),), decision),
            ("email", (self.evidence(decision_summary="ask ops@example.org"),), decision),
            ("twice", (self.evidence(), self.evidence()), decision),
            ("action", (self.evidence(action_class=history.ACTION_RESUME_CHANGED),), decision),
            ("not a tuple", [self.evidence()], decision),
        ):
            with self.subTest(name):
                self.assertTrue(p4.decision_evidence_problems(items, given))

    def test_the_authority_identity_names_the_canonical_requirement(self) -> None:
        self.assertEqual("work:w_1", p4.requirement_authority_identity({"authority": {"work_id": "w_1"}}))
        self.assertEqual("phase:p_1", p4.requirement_authority_identity({"authority": {"phase_id": "p_1"}}))
        self.assertEqual("roadmap-plan-v1:request",
                         p4.requirement_authority_identity({"review_kind": "roadmap-plan-v1", "authority": {}}))
        self.assertTrue(serialize.digest({"x": 1}))


if __name__ == "__main__":
    unittest.main()
