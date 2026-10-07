"""P7 root meta-review semantics (``WORKLINE_COMPLETION_SPRINT`` §31.24-§31.29, §31.33-§31.37, §31.53; RB7C-1 / RB7C-2).

Unit level over the inert core :mod:`workline.review.global_policy`:

* identities: the root kind / target / stage / contract / non-history root family policy;
* reviewer floors ``max(2|3, pre-change slots)`` decided by the movement, never by the direction word, and never by
  the proposed after-state; distinct reviewer identity / version bindings and one separately bound adjudicator;
* the root requests are the common P4 requests under the root policy - no history contract, no prior history, no
  set-aside summary, no decision evidence, no Effective Policy (WAIT_PSW_IR_RB7_2 until PSW lands the root branch);
  the root policy is refused under every other contract and in a Work P4 Context; static effective policy hash;
* G4 from the validated Gate chain alone: a declined discovery and REPAIR_REQUIRED are terminal ``not_authorized``
  (no Repair Batch; the same verdict recovery gives),
  HUMAN_WAIT stays the same Run (R8), authorization-ready seals - and no P5 history surface is ever reached;
* the fixed mechanical meta-verifier has precedence over any reviewer approval and re-proves an exact-rollback
  exemption over the stored change / evaluation records (Amendment 7); the pre-change Global policy and the fixed
  root meta-rules are what the Context (pinned to this build), the requirement and the floors bind;
* the root recovery classification over the shared discovery core (no automatic set-aside, R8);
* the persistence records: the change record, the deterministic Patch Note, the Consumption v4 projection;
* the module is inert and its P7 codes are its own catalogue.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any
import unittest

from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.review import global_policy as gp
from workline.review import history, p4, policy, records, recovery, serialize
from workline.review.store import GateChain

from test_global_policy_promotion import (
    CHANGE_ID, EVALUATION_ID, PACKET_ID, PSW_P4, RECEIPT_ID, RUN_ID, SECRET_ROOT, V1, V2_SLOTS3, WAIT_PSW_IR_RB7_2,
    applied_change, candidate_for, change_request, digest_of, evaluate, ident, observed, root_policy_hash_stub,
    successor, three_independent, two_independent,
)

PSW_RECORDS = hasattr(records, "GLOBAL_POLICY_REVIEW_KIND")
WAIT_PSW_IR_RB7_1 = "WAIT_PSW_IR_RB7_1: records root contract / P7 kind constants / Global Policy Consumption v4"
SOURCE = Path(gp.__file__).read_text(encoding="utf-8")
LOADER = digest_of("loader identity")
GOOD_FACTS = {"current_before_global_digest": policy.global_policy_digest(V1), "sources_current": True,
              "source_problems": [], "publication_ready": True, "rollback_change": None, "rollback_evaluation": None}
#: The facts an exact-rollback Candidate's meta-verification is given (Amendment 7: six keys).
ROLLBACK_CHANGE_ID = "rgc_" + "2" * 26


def actor(*_: Any) -> None:
    return None


def discovery(*pairs: tuple[str, str]) -> tuple[p4.DiscoveryBinding, ...]:
    return tuple(p4.DiscoveryBinding(f"view-{index}", actor, identity, version)
                 for index, (identity, version) in enumerate(pairs, start=1))


ADJUDICATOR = p4.ActorBinding(actor, "adjudicator", "1")


# --------------------------------------------------------------------------- a root Gate chain

def _task(number: int, slot: str, kind: str) -> dict[str, Any]:
    return {"task_id": ident("rtk", number), "task_slot": slot, "task_kind": kind, "reviewer_identity": f"r{number}",
            "reviewer_version": "1", "candidate_hash": "0" * 64, "candidate_material_digest": "0" * 64,
            "reconstruction_mode": records.RECONSTRUCTION_SNAPSHOT, "request_digest": "0" * 64,
            "task_input_digest": "0" * 64, "review_context_hash": "0" * 64, "effective_policy_hash": "0" * 64}


def _settled(task: dict[str, Any], generation: int, status: str = records.TASK_SETTLED_OK) -> dict[str, Any]:
    return {"task_id": task["task_id"], "status": status, "result_digest": digest_of(task["task_id"]),
            "settled_generation": generation}


def root_chain(last: int, *, candidate: str = "c" * 64, shape: str = p4.SHAPE_SEAL, declined: bool = False,
               kind: str = gp.REVIEW_KIND, target: str = gp.TARGET_IDENTITY) -> GateChain:
    """A root Run's chain of the P4 shapes, through generation ``last``."""
    first, second = _task(1, "p4-discovery.view-1", p4.TASK_KIND_DISCOVERY), _task(2, "p4-discovery.view-2",
                                                                                  p4.TASK_KIND_DISCOVERY)
    adjudication = _task(3, p4.SLOT_ADJUDICATOR, p4.TASK_KIND_ADJUDICATION)
    repair = _task(4, p4.SLOT_REPAIR, p4.TASK_KIND_REPAIR)
    discovery_settled = [_settled(first, 2), _settled(second, 2, records.TASK_SETTLED_FAILED if declined
                                                      else records.TASK_SETTLED_OK)]
    steps = [
        ([first, second], [], records.GATE_STATUS_OPEN, None),
        ([first, second], discovery_settled, records.GATE_STATUS_OPEN, None),
        ([first, second, adjudication], discovery_settled, records.GATE_STATUS_OPEN, None),
        ([first, second, adjudication], discovery_settled + [_settled(adjudication, 4)], records.GATE_STATUS_OPEN, None),
    ]
    if shape == p4.SHAPE_SEAL:
        steps.append((steps[3][0], steps[3][1], records.GATE_STATUS_SEALED, RECEIPT_ID))
        steps.append((steps[3][0], steps[3][1], records.GATE_STATUS_OPEN, None))
    else:
        steps.append((steps[3][0] + [repair], steps[3][1], records.GATE_STATUS_OPEN, None))
    generations = []
    for number, (accepted, settled, status, receipt) in enumerate(steps[:last], start=1):
        generations.append(records.GateGeneration(
            review_run_id=RUN_ID, generation=number, previous_generation=None if number == 1 else number - 1,
            previous_digest=None if number == 1 else digest_of("gate", number - 1), review_kind=kind,
            target_identity=target, operation_identity=f"global-policy-change:{'1' * 64}", candidate_hash=candidate,
            review_context_hash="d" * 64, effective_policy_hash="e" * 64, evidence_digest="f" * 64,
            coverage_digest="f" * 64, raw_report_set_digest="f" * 64, adjudication_digest="f" * 64,
            obligation_digest="f" * 64, accepted_tasks=tuple(accepted), settled_tasks=tuple(settled), status=status,
            receipt_id=receipt, authorized_operation_stage=gp.AUTHORIZED_OPERATION_STAGE if receipt else None))
    return GateChain(RUN_ID, tuple(generations), tuple(digest_of("gate", n) for n in range(1, last + 1)))


# =========================================================================== identities

class IdentityTests(unittest.TestCase):
    def test_the_frozen_root_identities(self) -> None:
        self.assertEqual(("global-policy-change-v1", "global-policy", "global-policy-change:persist-global-policy"),
                         (gp.REVIEW_KIND, gp.TARGET_IDENTITY, gp.AUTHORIZED_OPERATION_STAGE))
        self.assertEqual("review-v1-global-policy-change-p4-v1", gp.CONTRACT)
        self.assertEqual("review-v1-p7-root-policy-v1", gp.POLICY_ID)
        self.assertEqual("global-policy-adapter-v1", gp.PERSISTED_ADAPTER_IDENTITY)
        self.assertEqual(policy.COMPATIBILITY_TOTAL_ADAPTER_V1, gp.ADAPTER_V1_IDENTITY)
        self.assertEqual(("global-policy-change", "global-policy-evaluation"), (gp.OPERATION, gp.OPERATION_EVALUATION))

    def test_the_identities_are_exactly_the_shared_records_constants(self) -> None:
        if not PSW_RECORDS:
            self.skipTest(WAIT_PSW_IR_RB7_1)
        self.assertEqual(records.GLOBAL_POLICY_REVIEW_KIND, gp.REVIEW_KIND)
        self.assertEqual(records.GLOBAL_POLICY_TARGET_IDENTITY, gp.TARGET_IDENTITY)
        self.assertEqual(records.P7_GLOBAL_POLICY_CHANGE_CONTRACT, gp.CONTRACT)
        self.assertIn(gp.CONTRACT, records.P4_CONTRACTS)

    def test_the_root_policy_is_exactly_the_shared_p4_constant(self) -> None:
        if not PSW_P4:
            self.skipTest(WAIT_PSW_IR_RB7_2)
        self.assertEqual(p4.ROOT_POLICY_ID, gp.POLICY_ID)

    def test_the_p5_human_wait_disposition_this_core_reads(self) -> None:
        self.assertEqual(history.DISPOSITION_HUMAN_WAIT, gp._P5_HUMAN_WAIT)


# =========================================================================== reviewer floors (§31.26)

class ReviewerFloorTests(unittest.TestCase):
    def test_strengthen_adjust_and_exact_rollback_need_two_lighten_needs_three(self) -> None:
        v2 = successor(V1, slots=2)
        self.assertEqual(2, gp.required_discovery_slots(V1, v2, exact_rollback=False))
        self.assertEqual(3, gp.required_discovery_slots(V2_SLOTS3, successor(V2_SLOTS3, slots=1), exact_rollback=False))
        lowering = successor(v2, slots=1)
        self.assertEqual(3, gp.required_discovery_slots(v2, lowering, exact_rollback=False),
                         "decided by the movement, never by the direction word")
        self.assertEqual(2, gp.required_discovery_slots(v2, lowering, exact_rollback=True))

    def test_the_floor_is_the_pre_change_policy_never_the_proposed_after_state(self) -> None:
        self.assertEqual(2, gp.required_discovery_slots(V1, successor(V1, slots=4), exact_rollback=False),
                         "a proposed stronger after-state never selects the Review authorizing it")
        v4 = successor(V1, slots=4)
        self.assertEqual(4, gp.required_discovery_slots(v4, successor(v4, slots=1), exact_rollback=False),
                         "the proposed after-state never lowers the strength of the Review authorizing it")
        self.assertEqual(4, gp.required_discovery_slots(v4, successor(v4, slots=4, steps=3), exact_rollback=False))

    def test_every_counted_slot_binds_a_distinct_reviewer_and_one_adjudicator_is_bound(self) -> None:
        self.assertIsNone(gp.reviewer_floor_problem(discovery(("a", "1"), ("b", "1")), ADJUDICATOR, 2))
        self.assertIsNone(gp.reviewer_floor_problem(discovery(("a", "1"), ("a", "2")), ADJUDICATOR, 2),
                          "a distinct identity/version pair")
        cases = {
            "one identity twice": (discovery(("a", "1"), ("a", "1")), ADJUDICATOR, 2),
            "too few": (discovery(("a", "1"), ("b", "1")), ADJUDICATOR, 3),
            "no adjudicator": (discovery(("a", "1"), ("b", "1")), None, 2),
            "an extra slot repeating a counted reviewer": (discovery(("a", "1"), ("b", "1"), ("a", "1")), ADJUDICATOR, 2),
            "below the absolute root floor": (discovery(("a", "1")), ADJUDICATOR, 1),
            "a multi-line identity": (discovery(("a\nb", "1"), ("c", "1")), ADJUDICATOR, 2),
        }
        for name, (bindings, adjudicator, required) in cases.items():
            with self.subTest(case=name):
                self.assertIsNotNone(gp.reviewer_floor_problem(bindings, adjudicator, required))  # type: ignore
        with self.assertRaises(StopError) as raised:
            gp.require_reviewer_floor(discovery(("a", "1")), ADJUDICATOR, 2)
        self.assertEqual(gp.CODE_REVIEWER_FLOOR_UNMET, raised.exception.code)


# =========================================================================== the Candidate, the Context, the requirement (§31.24-§31.25)

class CandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        root_policy_hash_stub(self)
        self.material = candidate_for(V1, change_request(two_independent()), two_independent())

    def test_the_candidate_reconstructs_without_runtime_memory(self) -> None:
        material = self.material
        self.assertEqual(set(gp.CANDIDATE_FIELDS), set(material))
        self.assertEqual(V1, material["before_global_policy"])
        self.assertEqual(serialize.digest(material["promotion_packet"]), material["promotion_packet_digest"])
        self.assertEqual(sorted(["review-policy/global-policy.yaml", f"review-policy/changes/{CHANGE_ID}.yaml",
                                 f"review-policy/patch-notes/{CHANGE_ID}.md"]), material["expected_kp"]["paths"])
        self.assertEqual(serialize.digest(policy.global_policy_projection(material["after_global_policy"])),
                         material["normalized_projection_hash"])
        self.assertEqual(2, material["required_discovery_slots"])
        self.assertEqual(set(gp.EXPECTED_KP_FIELDS), set(material["expected_kp"]))
        self.assertEqual(set(gp.ROOT_META_POLICY_FIELDS), set(material["root_meta_policy"]))
        self.assertEqual(set(gp.COMPATIBILITY_PROOF_FIELDS), set(material["compatibility_proof"]))
        snapshot = gp.candidate_snapshot(material)
        self.assertEqual((records.RECONSTRUCTION_SNAPSHOT, gp.candidate_hash(material), material),
                         (snapshot.reconstruction_mode, snapshot.candidate_hash, snapshot.material))
        self.assertEqual(snapshot, records.CandidateSnapshot.from_record(snapshot.to_record(), "the snapshot"))
        self.assertNotIn(str(SECRET_ROOT), serialize.canonical_text(material))

    def test_a_tampered_candidate_does_not_reconstruct(self) -> None:
        for name, value in (("required_discovery_slots", 1), ("after_setting", 3),
                            ("before_global_policy", successor(V1, slots=2)),
                            ("expected_kp", {**self.material["expected_kp"], "paths": []})):
            with self.subTest(field=name):
                with self.assertRaises(ValidationError):
                    gp.parse_candidate_material({**self.material, name: value}, "the Candidate")

    def test_the_context_and_requirement_bind_the_pre_change_policy_and_fixed_meta_rules(self) -> None:
        context = gp.review_context(V1, loader_identity=LOADER)
        self.assertEqual(set(gp.CONTEXT_FIELDS), set(context))
        self.assertEqual((1, policy.global_policy_digest(V1)), (context["before_global_policy_version"],
                                                                context["before_global_policy_digest"]))
        self.assertEqual((policy.META_RULES_ID, policy.meta_rules_digest(), policy.LOADER_SEMANTICS_IDENTITY),
                         (context["meta_rules_id"], context["meta_rules_digest"], context["loader_semantics_identity"]))
        self.assertEqual("review-policy/review", context["namespace_root"])
        self.assertNotIn(self.material["after_global_policy_digest"], serialize.canonical_text(context))
        self.assertEqual(context, gp.parse_review_context(context, "the Context"))
        for name, value in (("root_policy_hash", digest_of("another root family policy")),
                            ("meta_rules_digest", digest_of("other meta-rules")),
                            ("before_global_policy_digest", "not a digest")):
            with self.subTest(foreign=name):
                with self.assertRaises(ValidationError):
                    gp.parse_review_context({**context, name: value}, "the Context")
        authority = gp.requirement(self.material)["authority"]
        self.assertEqual(policy.global_policy_digest(V1), authority["before_global_policy_digest"])
        self.assertEqual(policy.meta_rules_digest(), authority["meta_rules_digest"])
        evidence = gp.evidence_record(self.material)
        self.assertEqual(["alpha", "beta"], [item["source_id"] for item in evidence["source_snapshots"]])

    def test_the_root_runs_bind_the_static_root_family_policy_hash(self) -> None:
        if not PSW_P4:
            self.skipTest(WAIT_PSW_IR_RB7_2)
        expected = p4.family_policy_hash(gp.POLICY_ID)
        self.assertEqual(expected, gp.review_context(V1, loader_identity=LOADER)["root_policy_hash"])
        self.assertEqual(expected, self.material["root_meta_policy"]["root_policy_hash"])
        self.assertEqual(expected, p4.run_effective_policy_hash(gp.POLICY_ID, None))


# =========================================================================== the root requests over P4 (RB7C-1)

class RootRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        if not (PSW_P4 and PSW_RECORDS):
            self.skipTest(f"{WAIT_PSW_IR_RB7_1}; {WAIT_PSW_IR_RB7_2}")
        self.material = candidate_for(V1, change_request(two_independent()), two_independent())
        self.context = gp.review_context(V1, loader_identity=LOADER)

    def test_a_root_discovery_request_binds_no_history_and_no_effective_policy(self) -> None:
        found = gp.discovery_request(material=self.material, context=self.context, viewpoint="view-1")
        self.assertEqual((gp.CONTRACT, gp.REVIEW_KIND, gp.POLICY_ID, 1, None, [], None),
                         (found["review_contract"], found["review_kind"], found["policy_id"],
                          found["candidate_generation"], found["succession"], found["set_aside_runs"],
                          found["human_decision"]))
        for absent in (history.HISTORY_CONTRACT_KEY, "prior_history", "set_aside_summaries", "decision_evidence",
                       policy.EFFECTIVE_POLICY_KEY, policy.DISCOVERY_ROLE_KEY):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, found)
        self.assertEqual(gp.POLICY_ID, p4.policy_of_envelope(found))

    def test_a_root_adjudication_request_has_no_prior_cycle_and_no_history(self) -> None:
        found = gp.adjudication_request(review_run_id=RUN_ID, candidate_hash=gp.candidate_hash(self.material),
                                        review_context_hash=serialize.digest(self.context),
                                        requirement=gp.requirement(self.material), reports=[], evidence_ids=[])
        self.assertEqual(p4.NO_PRIOR, found["prior"])
        self.assertNotIn(history.HISTORY_CONTRACT_KEY, found)
        self.assertNotIn("prior_history", found)

    def test_the_root_policy_is_never_bound_under_another_contract_or_in_a_work_context(self) -> None:
        for contract in (records.P4_PLANNING_CONTRACT, records.P4_WORK_CONTRACT, records.P6_POLICY_CHANGE_CONTRACT):
            with self.subTest(contract=contract):
                self.assertIsNotNone(p4.contract_policy_problem(contract, gp.POLICY_ID))
        self.assertEqual((gp.POLICY_ID,), p4.CONTRACT_POLICIES[gp.CONTRACT])
        self.assertNotIn(gp.POLICY_ID, p4.POLICY_IDS)
        self.assertNotIn(gp.POLICY_ID, p4.FAMILY_POLICY_IDS, "a Work P4 Context never names the root policy")
        self.assertIsNone(p4.history_contract_of_policy(gp.POLICY_ID))
        self.assertNotIn(gp.REVIEW_KIND, history.G4_TERMINAL_REVIEW_KINDS)
        with self.assertRaises(ValidationError):
            p4.repair_request(review_contract=gp.CONTRACT, review_kind=gp.REVIEW_KIND, review_run_id=RUN_ID,
                              candidate_hash="0" * 64, candidate_generation=1, requirement={},
                              repair_batch_id=ident("rrb", 1), repair_batch_digest="0" * 64,
                              allowed_result_surface=[], strategy="ordinary", evidence_constraints=[],
                              policy_id=gp.POLICY_ID)


# =========================================================================== G4 without P5 history (§31.27, RB7C-1 (e))

class G4OutcomeTests(unittest.TestCase):
    def test_repair_required_is_terminal_not_authorized_with_no_repair_batch(self) -> None:
        self.assertEqual(gp.OUTCOME_NOT_AUTHORIZED, gp.g4_outcome(root_chain(4), records.REPAIR_REQUIRED))
        self.assertFalse(p4.repairs(gp.CONTRACT))
        self.assertNotIn(gp.CONTRACT, records.P4_REPAIR_CONTRACTS)

    def test_human_wait_stays_the_same_run(self) -> None:
        chain = root_chain(4)
        self.assertEqual(gp.OUTCOME_HUMAN_WAIT, gp.g4_outcome(chain, records.HUMAN_WAIT))
        self.assertIsNone(chain.latest.receipt_id)

    def test_authorization_ready_and_its_seal(self) -> None:
        self.assertEqual(gp.OUTCOME_AUTHORIZATION_READY, gp.g4_outcome(root_chain(4), records.AUTHORIZATION_READY))
        self.assertEqual(gp.OUTCOME_AUTHORIZATION_READY, gp.g4_outcome(root_chain(5), records.AUTHORIZATION_READY))

    def test_a_declined_discovery_never_authorizes_whatever_the_adjudication_says(self) -> None:
        chain = root_chain(4, declined=True)
        self.assertEqual([], p4.chain_problems(chain), "a declined settlement is shape-valid")
        for outcome in (records.AUTHORIZATION_READY, records.HUMAN_WAIT, records.REPAIR_REQUIRED):
            with self.subTest(outcome=outcome):
                self.assertEqual(gp.OUTCOME_NOT_AUTHORIZED, gp.g4_outcome(chain, outcome))
        self.assertEqual(gp.OUTCOME_NOT_AUTHORIZED, gp.g4_outcome(root_chain(5, declined=True),
                                                                  records.AUTHORIZATION_READY))

    def test_no_g4_outcome_before_g4_off_shape_or_for_another_kind(self) -> None:
        for name, chain, outcome in (("G3", root_chain(3), None), ("repair branch", root_chain(5, shape=p4.SHAPE_REPAIR),
                                                                    records.REPAIR_REQUIRED),
                                     ("invalidated", root_chain(6), records.AUTHORIZATION_READY),
                                     ("P6 kind", root_chain(4, kind=policy.REVIEW_KIND), records.HUMAN_WAIT),
                                     ("unknown outcome", root_chain(4), "MAYBE"),
                                     ("declined at G2", root_chain(2, declined=True), None)):
            with self.subTest(case=name):
                with self.assertRaises(ReconcileRequired) as raised:
                    gp.g4_outcome(chain, outcome)
                self.assertEqual(gp.REASON_CHAIN_INVALID, raised.exception.reason)

    def test_no_p5_history_surface_is_reached(self) -> None:
        for name in ("g4_history", "not_authorized_history", "prior_history_references", "prior_history_records",
                     "run_summary", "history_rel"):
            with self.subTest(name=name):
                self.assertNotIn(name, SOURCE)


# =========================================================================== the mechanical meta-verifier (§31.28)

class MetaVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        root_policy_hash_stub(self)
        self.material = candidate_for(V1, change_request(two_independent()), two_independent())

    def test_a_current_candidate_passes_every_item(self) -> None:
        self.assertEqual([], gp.meta_verifier_problems(self.material, GOOD_FACTS))
        self.assertEqual([], gp.meta_verifier_problems(self.material, {**GOOD_FACTS, "publication_ready": None}),
                         "a remote-less root needs no publication")
        gp.require_meta_verifier(self.material, GOOD_FACTS)

    def test_a_failed_mechanical_item_refuses_whatever_any_reviewer_said(self) -> None:
        cases = {
            "before moved": {**GOOD_FACTS, "current_before_global_digest": digest_of("another Global")},
            "sources stale": {**GOOD_FACTS, "sources_current": False},
            "source problem": {**GOOD_FACTS, "source_problems": ["alpha: the bound evidence changed"]},
            "publication not ready": {**GOOD_FACTS, "publication_ready": False},
            "facts shape": {key: value for key, value in GOOD_FACTS.items() if key != "publication_ready"},
        }
        for name, facts in cases.items():
            with self.subTest(case=name):
                self.assertTrue(gp.meta_verifier_problems(self.material, facts))
                with self.assertRaises(StopError) as raised:
                    gp.require_meta_verifier(self.material, facts)
                self.assertEqual(gp.CODE_META_VERIFIER_FAILED, raised.exception.code)

    def test_a_tampered_or_foreign_meta_policy_is_refused(self) -> None:
        foreign = {**self.material, "root_meta_policy": {**self.material["root_meta_policy"],
                                                         "root_policy_hash": digest_of("another root policy")}}
        codes = [code for code, _ in gp.meta_verifier_problems(foreign, GOOD_FACTS)]
        self.assertEqual([gp.CODE_META_VERIFIER_FAILED], codes)
        tampered = {**self.material, "promotion_packet": {**self.material["promotion_packet"], "summary": "other"}}
        self.assertTrue(gp.meta_verifier_problems(tampered, GOOD_FACTS))

    def test_rollback_facts_are_none_when_the_exception_is_unused(self) -> None:
        change = applied_change(self)
        facts = {**GOOD_FACTS, "rollback_change": change}
        self.assertEqual([gp.CODE_META_VERIFIER_FAILED], [code for code, _ in gp.meta_verifier_problems(
            self.material, facts)])

    def test_the_lighten_floor_is_rechecked_by_the_movement(self) -> None:
        snapshots = three_independent()
        material = candidate_for(V2_SLOTS3, change_request(snapshots, direction="adjust", after=2), snapshots)
        facts = {**GOOD_FACTS, "current_before_global_digest": policy.global_policy_digest(V2_SLOTS3)}
        self.assertEqual([], gp.meta_verifier_problems(material, facts))
        self.assertEqual(3, material["required_discovery_slots"])
        self.assertEqual(gp.FLOOR_LIGHTEN, material["promotion_packet"]["eligibility"]["floor"])


class ExactRollbackMetaVerifierTests(unittest.TestCase):
    """Amendment 7 / §31.28: "rollback exception exactness when used" is re-proven over the stored records."""

    def setUp(self) -> None:
        root_policy_hash_stub(self)
        self.change = applied_change(self)
        self.before = successor(V1, slots=2)
        self.evaluation = evaluate(self.change, gp.RESULT_ROLLBACK, observed(CHANGE_ID))
        request = change_request([], direction="rollback", after=1, rollback_of=CHANGE_ID,
                                 rollback_evaluation_id=EVALUATION_ID)
        self.material = candidate_for(self.before, request, [], change_id=ROLLBACK_CHANGE_ID)
        self.facts = {**GOOD_FACTS, "current_before_global_digest": policy.global_policy_digest(self.before),
                      "rollback_change": self.change, "rollback_evaluation": self.evaluation}

    def test_an_exact_rollback_with_its_stored_records_passes(self) -> None:
        self.assertEqual(gp.BASIS_EXACT_ROLLBACK, self.material["promotion_packet"]["eligibility"]["basis"])
        self.assertEqual([], gp.meta_verifier_problems(self.material, self.facts))
        gp.require_meta_verifier(self.material, self.facts)

    def test_an_unproven_exemption_never_seals(self) -> None:
        retained = evaluate(self.change, gp.RESULT_RETAIN, observed(CHANGE_ID))
        other_change = dict(self.change, global_policy_change_id="rgc_" + "3" * 26)
        cases = {
            "records missing": {"rollback_change": None, "rollback_evaluation": None},
            "evaluation missing": {"rollback_evaluation": None},
            "another change": {"rollback_change": other_change},
            "the threshold did not fire": {"rollback_evaluation": retained},
            "not a mapping": {"rollback_change": "rgc"},
        }
        for name, changes in cases.items():
            with self.subTest(case=name):
                problems = gp.meta_verifier_problems(self.material, {**self.facts, **changes})
                self.assertEqual([gp.CODE_ROLLBACK_INEXACT], [code for code, _ in problems])
                with self.assertRaises(StopError) as raised:
                    gp.require_meta_verifier(self.material, {**self.facts, **changes})
                self.assertEqual(gp.CODE_META_VERIFIER_FAILED, raised.exception.code)
                self.assertIn(gp.CODE_ROLLBACK_INEXACT, str(raised.exception))

    def test_the_change_must_still_be_the_one_in_force(self) -> None:
        moved = successor(self.before, steps=1)
        facts = {**self.facts, "current_before_global_digest": policy.global_policy_digest(moved)}
        self.assertIn(gp.CODE_META_VERIFIER_FAILED, [code for code, _ in gp.meta_verifier_problems(self.material,
                                                                                                    facts)])


# =========================================================================== root recovery classification (§31.29, RB7C-2, R8)

class RecoveryAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        root_policy_hash_stub(self)
        self.material = candidate_for(V1, change_request(two_independent()), two_independent())
        self.hash = gp.candidate_hash(self.material)
        self.consumed: set[str] = set()
        self.outcome = records.AUTHORIZATION_READY

    def classify(self, chain: GateChain, *, bound: bool = True, contract: str = gp.CONTRACT,
                 material: dict[str, Any] | None = None) -> str | None:
        adapter = gp.recovery_adapter(promotion_packet_id=PACKET_ID if bound else None,
                                      candidate_hash=self.hash if bound else None,
                                      consumed=lambda receipt_id: receipt_id in self.consumed)
        found = recovery.MatchingRun(RUN_ID, chain, self.material if material is None else material,
                                     ident("rtk", 1), contract)
        review = SimpleNamespace(read_adjudication=lambda run_id: SimpleNamespace(outcome=self.outcome))
        return adapter.classify(SECRET_ROOT, review, "a" * 40, found, set(), None)

    def test_the_adapter_is_the_shared_core_shape_with_no_automatic_set_aside(self) -> None:
        adapter = gp.recovery_adapter(promotion_packet_id=PACKET_ID, candidate_hash=self.hash, consumed=lambda _: False)
        self.assertIsInstance(adapter, recovery.RecoveryAdapter)
        self.assertIsNone(adapter.shape(root_chain(5, candidate=self.hash)))
        self.assertIsNotNone(adapter.shape(root_chain(5, candidate=self.hash, shape=p4.SHAPE_REPAIR)))
        self.assertEqual([], adapter.named(None, None))

    def test_settled_runs(self) -> None:
        self.consumed.add(RECEIPT_ID)
        self.assertEqual(gp.SETTLED_CONSUMED, self.classify(root_chain(5, candidate=self.hash)))
        self.consumed.clear()
        self.assertEqual(gp.SETTLED_INVALIDATED, self.classify(root_chain(6, candidate=self.hash)))
        self.assertEqual(gp.SETTLED_NOT_AUTHORIZED, self.classify(root_chain(2, candidate=self.hash, declined=True)))
        self.outcome = records.REPAIR_REQUIRED
        self.assertEqual(gp.SETTLED_NOT_AUTHORIZED, self.classify(root_chain(4, candidate=self.hash)))
        self.outcome = records.AUTHORIZATION_READY
        declined = root_chain(4, candidate=self.hash, declined=True)
        self.assertEqual(gp.SETTLED_NOT_AUTHORIZED, self.classify(declined))
        self.assertEqual(gp.OUTCOME_NOT_AUTHORIZED, gp.g4_outcome(declined, self.outcome), "one Run, one verdict")

    def test_a_human_wait_run_is_recovered_as_the_same_waiting_run(self) -> None:
        self.outcome = records.HUMAN_WAIT
        self.assertIsNone(self.classify(root_chain(4, candidate=self.hash)), "R8: never set aside by runtime loss")
        self.assertIsNone(self.classify(root_chain(4, candidate=self.hash), bound=False))

    def test_open_and_sealed_runs_are_recoverable(self) -> None:
        for last in (1, 2, 3, 5):
            with self.subTest(generation=last):
                self.assertIsNone(self.classify(root_chain(last, candidate=self.hash)))

    def test_identity_contract_and_kind_are_proven(self) -> None:
        with self.assertRaises(ReconcileRequired) as raised:
            self.classify(root_chain(3, candidate=self.hash), contract=records.P6_POLICY_CHANGE_CONTRACT)
        self.assertEqual(gp.REASON_CHAIN_INVALID, raised.exception.reason)
        with self.assertRaises(ReconcileRequired) as raised:
            self.classify(root_chain(3, candidate="9" * 64))
        self.assertEqual(gp.REASON_CANDIDATE_MISMATCH, raised.exception.reason)
        with self.assertRaises(ReconcileRequired) as raised:
            self.classify(root_chain(3, candidate=self.hash), material={**self.material, "after_setting": 3})
        self.assertEqual(gp.REASON_CANDIDATE_MISMATCH, raised.exception.reason)

    def test_another_in_flight_candidate_of_the_same_request_is_never_chosen(self) -> None:
        snapshots = three_independent()
        other = candidate_for(V1, change_request(snapshots), snapshots)
        chain = root_chain(3, candidate=gp.candidate_hash(other))
        with self.assertRaises(ReconcileRequired) as raised:
            self.classify(chain, material=other)
        self.assertEqual(gp.REASON_CANDIDATE_MISMATCH, raised.exception.reason)
        self.assertIsNone(self.classify(chain, material=other, bound=False), "after runtime loss nothing is bound")
        self.consumed.add(RECEIPT_ID)
        self.assertEqual(gp.SETTLED_CONSUMED, self.classify(root_chain(5, candidate=gp.candidate_hash(other)),
                                                            material=other), "a settled Run is settled whoever's")

    def test_the_bound_identity_is_named_together(self) -> None:
        # Amendment 6: both None (nothing bound yet) or both given; exactly one is review_record_invalid
        for packet_id, candidate in ((PACKET_ID, None), (None, self.hash), ("rpp_bad", self.hash), (PACKET_ID, "x")):
            with self.subTest(packet_id=packet_id, candidate=candidate):
                with self.assertRaises(ValidationError) as raised:
                    gp.recovery_adapter(promotion_packet_id=packet_id, candidate_hash=candidate,
                                        consumed=lambda _: False)
                self.assertEqual("review_record_invalid", raised.exception.code)
        gp.recovery_adapter(promotion_packet_id=None, candidate_hash=None, consumed=lambda _: False)


# =========================================================================== persistence records (§31.33-§31.37)

class PersistenceRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        root_policy_hash_stub(self)
        self.material = candidate_for(V1, change_request(two_independent()), two_independent())
        self.change = gp.change_record(self.material, review_run_id=RUN_ID, receipt_id=RECEIPT_ID)

    def test_the_change_record_binds_the_authorized_candidate_and_never_its_commit(self) -> None:
        change = self.change
        self.assertEqual(set(gp.CHANGE_FIELDS), set(change))
        self.assertEqual((CHANGE_ID, PACKET_ID, gp.candidate_hash(self.material), RUN_ID, RECEIPT_ID),
                         (change["global_policy_change_id"], change["promotion_packet_id"], change["candidate_hash"],
                          change["review_run_id"], change["receipt_id"]))
        self.assertEqual((1, 2, 1, 2), (change["before_global_policy_version"], change["after_global_policy_version"],
                                        change["before_setting"], change["after_setting"]))
        self.assertFalse({"policy_commit", "commit", "commit_sha"} & set(change))
        self.assertEqual(change, gp.parse_change_record(change, "the change"))
        for name, value in (("after_global_policy_version", 3), ("summary", "C:\\Users\\dev\\notes"),
                            ("compatibility_adapter_identity", "another adapter")):
            with self.subTest(field=name):
                with self.assertRaises(ValidationError):
                    gp.parse_change_record({**change, name: value}, "the change")

    def test_the_patch_note_is_deterministic_explanation_only(self) -> None:
        note = gp.patch_note_bytes(self.change)
        self.assertEqual(note, gp.patch_note_bytes(dict(self.change)))
        self.assertNotIn(b"\r", note)
        self.assertTrue(note.endswith(b"\n"))
        text = note.decode("utf-8")
        for fact in (CHANGE_ID, policy.SURFACE_REQUIRED_SLOTS, "1 -> 2", self.change["generalized_mechanism_id"],
                     self.change["expected_effect"], self.change["rollback_contract"]["threshold"], PACKET_ID,
                     "explanation only"):
            with self.subTest(fact=fact):
                self.assertIn(str(fact), text)
        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]|/home/|/Users/", text))
        self.assertNotIn(str(SECRET_ROOT), text)

    def test_the_persisted_projection_consumption_v4_binds(self) -> None:
        if not PSW_RECORDS:
            self.skipTest(WAIT_PSW_IR_RB7_1)
        found = gp.persisted_global_policy(self.material, global_policy_change_id=CHANGE_ID, policy_commit="b" * 40,
                                           policy_parent="a" * 40, branch="refs/heads/main",
                                           policy_delta_digest=digest_of("delta"), loader_identity=LOADER)
        self.assertEqual(set(records.PERSISTED_GLOBAL_POLICY_FIELDS), set(found))
        self.assertEqual(records.PERSISTED_GLOBAL_POLICY_CONTRACT, found["contract"])
        self.assertEqual(self.material["compatibility_proof_digest"], found["compatibility_adapter_digest"])
        self.assertIn(found["compatibility_adapter_identity"], records.GLOBAL_POLICY_COMPATIBILITY_ADAPTERS)
        consumption = {
            serialize.SCHEMA_KEY: records.SCHEMA_CONSUMPTION, serialize.VERSION_KEY: 4,
            "consumption_id": ident("rcs", 1), "receipt_id": RECEIPT_ID, "review_run_id": RUN_ID,
            "review_generation": p4.SEAL_GENERATION, "review_kind": gp.REVIEW_KIND,
            "authorized_candidate_hash": gp.candidate_hash(self.material),
            "operation_identity": f"global-policy-change:{'1' * 64}", "root_policy_mutation_id": ident("rpm", 1),
            "target_identity": gp.TARGET_IDENTITY, "persisted_global_policy": found,
        }
        parsed = records.consumption_from_record(consumption, "the Consumption")
        self.assertEqual("b" * 40, parsed.policy_commit)

    def test_the_persisted_projection_refuses_what_is_not_kp(self) -> None:
        good = dict(global_policy_change_id=CHANGE_ID, policy_commit="b" * 40, policy_parent="a" * 40,
                    branch="refs/heads/main", policy_delta_digest=digest_of("delta"), loader_identity=LOADER)
        for name, value in (("policy_commit", "main"), ("policy_parent", "b" * 40), ("branch", "main"),
                            ("loader_identity", "loader")):
            with self.subTest(field=name):
                with self.assertRaises(ValidationError):
                    gp.persisted_global_policy(self.material, **{**good, name: value})
        with self.assertRaises(ReconcileRequired):
            gp.persisted_global_policy(self.material, **{**good, "global_policy_change_id": "rgc_" + "2" * 26})


# =========================================================================== an inert core with its own catalogue

class InertCoreTests(unittest.TestCase):
    def test_the_core_imports_nothing_that_locks_reads_files_mutates_or_reaches_history(self) -> None:
        tree = ast.parse(SOURCE)
        allowed = {"errors", "ids", "namespace", "p4", "policy", "records", "serialize", "recovery"}
        standard = {"__future__", "dataclasses", "itertools", "pathlib", "re", "typing"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                names = {node.module} if node.module else {alias.name for alias in node.names}
                with self.subTest(line=node.lineno):
                    self.assertLessEqual(names - {None}, allowed)
            elif isinstance(node, ast.ImportFrom):
                with self.subTest(line=node.lineno):
                    self.assertIn(node.module, standard, "an absolute import reaches only the standard library")
            elif isinstance(node, ast.Import):
                with self.subTest(line=node.lineno):
                    self.assertLessEqual({alias.name for alias in node.names}, standard)
        self.assertIsNone(re.search(r"\bimport history\b|from \.history import|from \. import .*\bhistory\b", SOURCE))
        calls = {node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                 for node in ast.walk(tree) if isinstance(node, ast.Call)}
        for forbidden in ("open", "write_text", "write_bytes", "read_text", "read_bytes", "mkdir", "unlink", "rename",
                          "run", "Popen"):
            with self.subTest(call=forbidden):
                self.assertNotIn(forbidden, calls)

    def test_recovery_is_imported_lazily_inside_the_adapter_only(self) -> None:
        tree = ast.parse(SOURCE)
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and any(alias.name == "recovery" for alias in node.names):
                self.fail("review.recovery is imported at module level")
        adapter = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                       and node.name == "recovery_adapter")
        self.assertTrue(any(isinstance(node, ast.ImportFrom) and any(alias.name == "recovery" for alias in node.names)
                            for node in ast.walk(adapter)))

    def test_every_p7_code_literal_is_declared_once_in_this_catalogue(self) -> None:
        occurrences = [node.value for node in ast.walk(ast.parse(SOURCE))
                       if isinstance(node, ast.Constant) and isinstance(node.value, str)
                       and re.fullmatch(r"review_p7_[a-z_]+", node.value)]
        declared = set(gp.STOP_CODES) | set(gp.RECONCILE_REASONS)
        self.assertEqual(declared, set(occurrences))
        self.assertEqual(len(gp.STOP_CODES) + len(gp.RECONCILE_REASONS), len(declared))
        self.assertEqual(len(declared), len(occurrences), "each P7 code is spelled exactly once, in the catalogue")
        self.assertFalse(re.search(r"review_p6_[a-z_]+", SOURCE), "no P6 code is raised by the P7 core")
        others = set(p4.STOP_CODES) | set(p4.RECONCILE_REASONS) | set(policy.STOP_CODES) | set(policy.RECONCILE_REASONS) \
            | set(history.STOP_CODES) | set(history.RECONCILE_REASONS)
        self.assertEqual(set(), declared & others)
        with self.assertRaises(ValueError):
            gp.stop("review_p7_not_a_code", "x")
        with self.assertRaises(ValueError):
            gp.reconcile("x", gp.CODE_REQUEST_INVALID)

    def test_the_frozen_catalogue(self) -> None:
        self.assertEqual({
            "review_p7_request_invalid", "review_p7_surface_refused", "review_p7_source_unavailable",
            "review_p7_source_invalid", "review_p7_not_eligible", "review_p7_rollback_inexact",
            "review_p7_compatibility_unproven", "review_p7_reviewer_floor_unmet", "review_p7_meta_verifier_failed",
            "review_p7_evaluation_invalid"}, set(gp.STOP_CODES))
        self.assertEqual({"review_p7_candidate_mismatch", "review_p7_chain_invalid"}, set(gp.RECONCILE_REASONS))


if __name__ == "__main__":
    unittest.main()
