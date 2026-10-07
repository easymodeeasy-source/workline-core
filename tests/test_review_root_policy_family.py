"""P7 root meta-review on the shared records / p4 surfaces (§31.25 / §31.37; IR-RB7-1 / IR-RB7-2, shared-surface writer).

* records: the root contract is a P4-family contract with no Repair Batch branch; the Global Policy Consumption
  (version 4, allocation A-1) reads only its own strict shape, by version alone, and versions 1 - 3 read as before;
* p4 (addendum RB7C-1 (a)-(e)): the static root non-history family policy is in ``FAMILY_POLICY_RECORDS`` only; it
  is bound under the root contract alone and the root contract under it alone; a root request binds no history,
  Effective Policy or discovery role and is classified by its explicit identity; every root hash is the static
  family policy hash; there is no root repair request; the root kind is never G4-terminal P5 history;
  ``P6_POLICY_RECORD`` and every P4 / P5 / P6 request byte stay unchanged.
"""

from __future__ import annotations

import unittest

from workline.errors import ValidationError
from workline.review import history, p4, policy, records, serialize, work_review

ROOT = p4.ROOT_POLICY_ID
CONTRACT = records.P7_GLOBAL_POLICY_CHANGE_CONTRACT
COMMIT = "1" * 40


def persisted(**changes: object) -> dict:
    found = {
        "contract": records.PERSISTED_GLOBAL_POLICY_CONTRACT,
        "global_policy_change_id": "rgc_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "promotion_packet_id": "rpp_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "promotion_packet_digest": "2" * 64,
        "before_global_policy_version": 1,
        "before_global_policy_digest": "3" * 64,
        "after_global_policy_version": 2,
        "after_global_policy_digest": "4" * 64,
        "normalized_projection_hash": "5" * 64,
        "policy_commit": COMMIT,
        "policy_parent": "6" * 40,
        "branch": "refs/heads/main",
        "policy_delta_digest": "7" * 64,
        "compatibility_adapter_identity": policy.COMPATIBILITY_TOTAL_ADAPTER_V1,
        "compatibility_adapter_digest": "8" * 64,
        "loader_identity": "9" * 64,
    }
    found.update(changes)
    return found


def consumption(**changes: object) -> dict:
    found = {
        serialize.SCHEMA_KEY: records.SCHEMA_CONSUMPTION, serialize.VERSION_KEY: records.GLOBAL_POLICY_CONSUMPTION_VERSION,
        "consumption_id": "rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV", "receipt_id": "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "review_run_id": "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV", "review_generation": 5,
        "review_kind": records.GLOBAL_POLICY_REVIEW_KIND, "authorized_candidate_hash": "a" * 64,
        "operation_identity": "global-policy-change:" + "e" * 64,
        "root_policy_mutation_id": "rpm_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "target_identity": records.GLOBAL_POLICY_TARGET_IDENTITY, "persisted_global_policy": persisted(),
    }
    found.update(changes)
    return found


def discovery(policy_id: str = ROOT, contract: str = CONTRACT, **extra: object) -> dict:
    return p4.discovery_request(
        review_contract=contract, review_kind=records.GLOBAL_POLICY_REVIEW_KIND, viewpoint="correctness",
        candidate={"candidate_hash": "a" * 64}, context={"context": "root"}, requirement={"requirement": "r"},
        candidate_generation=1, succession=None, set_aside_runs=(), human_decision=None, policy_id=policy_id, **extra,
    )


def adjudication(policy_id: str = ROOT, contract: str = CONTRACT, **extra: object) -> dict:
    return p4.adjudication_request(
        review_contract=contract, review_kind=records.GLOBAL_POLICY_REVIEW_KIND,
        review_run_id="rr_01ARZ3NDEKTSV4RRFFQ69G5FAV", candidate_hash="a" * 64, candidate_generation=1,
        review_context_hash="b" * 64, requirement={"requirement": "r"}, reports=(), prior=dict(p4.NO_PRIOR),
        evidence_ids=(), policy_id=policy_id, **extra,
    )


class RootContractTests(unittest.TestCase):
    def test_the_root_contract_is_a_p4_family_contract_with_no_repair_batch_branch(self) -> None:
        self.assertEqual("review-v1-global-policy-change-p4-v1", CONTRACT)
        self.assertIn(CONTRACT, records.P4_CONTRACTS)
        self.assertNotIn(CONTRACT, records.P4_REPAIR_CONTRACTS)
        self.assertFalse(p4.repairs(CONTRACT))
        self.assertEqual(("global-policy-change-v1", "global-policy"),
                         (records.GLOBAL_POLICY_REVIEW_KIND, records.GLOBAL_POLICY_TARGET_IDENTITY))
        self.assertEqual((policy.COMPATIBILITY_TOTAL_ADAPTER_V1,), records.GLOBAL_POLICY_COMPATIBILITY_ADAPTERS)


class GlobalPolicyConsumptionTests(unittest.TestCase):
    def test_version_4_reads_only_its_own_strict_shape(self) -> None:
        record = consumption()
        found = records.consumption_from_record(record, "v4")
        self.assertIsInstance(found, records.GlobalPolicyConsumption)
        self.assertEqual(record, found.to_record())
        self.assertEqual((False, None, None, None, None, COMMIT),
                         (found.work_kind, found.work_id, found.terminal_event_id, found.terminal_event_type,
                          found.authorized_result_commit_sha, found.policy_commit))
        for name, change in {
            "another kind": {"review_kind": "project-policy-change-v1"},
            "another target": {"target_identity": "project-policy"},
            "a Project mutation": {"root_policy_mutation_id": "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV"},
            "an operation_mutation_id": {"operation_mutation_id": "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV"},
            "a terminal event": {"terminal_event_id": "evt_01ARZ3NDEKTSV4RRFFQ69G5FAV"},
            "a skipped version": {"persisted_global_policy": persisted(after_global_policy_version=3)},
            "version 0 before": {"persisted_global_policy": persisted(before_global_policy_version=0,
                                                                      after_global_policy_version=1)},
            "an unknown adapter": {"persisted_global_policy": persisted(compatibility_adapter_identity="x-v9")},
            "a short commit": {"persisted_global_policy": persisted(policy_commit="1234567")},
            "a branch name": {"persisted_global_policy": persisted(branch="main")},
            "a Project change id": {"persisted_global_policy": persisted(
                global_policy_change_id="rpc_01ARZ3NDEKTSV4RRFFQ69G5FAV")},
            "another contract": {"persisted_global_policy": persisted(contract="review-v1-p6-persisted-policy-v1")},
            "an extra persisted field": {"persisted_global_policy": {**persisted(), "notes": "x"}},
        }.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                records.consumption_from_record(consumption(**change), name)

    def test_dispatch_is_by_version_only_and_versions_1_to_3_are_unchanged(self) -> None:
        record = consumption()
        for version in (1, 2, 3, 5):
            with self.subTest(version=version), self.assertRaises(ValidationError):
                records.consumption_from_record({**record, serialize.VERSION_KEY: version}, "a v4 shape elsewhere")
        v1 = records.Consumption(
            "rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV", "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV", "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV", 5,
            "work-result-v1", "a" * 64, "start:" + "e" * 64, "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV", None, None,
            "w_01ARZ3NDEKTSV4RRFFQ69G5FAV", None).to_record()
        self.assertIs(type(records.consumption_from_record(v1, "v1")), records.Consumption)
        with self.assertRaises(ValidationError):
            records.consumption_from_record({**v1, serialize.VERSION_KEY: 4}, "a v1 shape at version 4")


class RootFamilyPolicyTests(unittest.TestCase):
    def test_the_record_is_static_in_the_family_table_only(self) -> None:
        self.assertEqual("review-v1-p7-root-policy-v1", ROOT)
        self.assertIs(p4.ROOT_POLICY_RECORD, p4.FAMILY_POLICY_RECORDS[ROOT])
        for table in (p4.POLICY_RECORDS, p4.POLICY_IDS, p4.FAMILY_POLICY_IDS, p4.HISTORY_POLICY_IDS):
            with self.subTest(table=table):
                self.assertNotIn(ROOT, table)
        found = p4.ROOT_POLICY_RECORD
        self.assertEqual((p4.SCHEMA_ROOT_POLICY, ROOT, [CONTRACT]),
                         (found["schema"], found["policy_id"], found["review_contracts"]))
        self.assertEqual("review-p7-root-policy", p4.SCHEMA_ROOT_POLICY)
        for key in ("repair", "history", "adaptive"):
            self.assertNotIn(key, found)
        self.assertEqual(p4.POLICY_RECORD["discovery"], found["discovery"])
        self.assertEqual(p4.ADJUDICATION_INSTRUCTION, found["adjudication"]["instruction"])
        self.assertEqual(p4.ADJUDICATION_INSTRUCTION, p4.adjudication_instruction_of(ROOT))
        self.assertIn("root", found)
        self.assertIsNone(p4.history_contract_of_policy(ROOT))
        self.assertFalse(p4.is_history_policy(ROOT))
        self.assertEqual(serialize.digest(serialize.canonical_data(found)), p4.family_policy_hash(ROOT))
        self.assertNotIn(CONTRACT, p4.P6_POLICY_RECORD["review_contracts"], "P6_POLICY_RECORD untouched")
        self.assertNotIn(records.GLOBAL_POLICY_REVIEW_KIND, history.G4_TERMINAL_REVIEW_KINDS)

    def test_the_contract_and_the_root_policy_bind_each_other_only(self) -> None:
        self.assertIsNone(p4.contract_policy_problem(CONTRACT, ROOT))
        for other in (p4.POLICY_ID, p4.P5_POLICY_ID, p4.P6_POLICY_ID):
            with self.subTest(policy=other):
                self.assertIn("root non-history family policy", str(p4.contract_policy_problem(CONTRACT, other)))
        for contract in (p4.PLANNING_CONTRACT, p4.WORK_CONTRACT, records.P6_POLICY_CHANGE_CONTRACT, "x"):
            with self.subTest(contract=contract):
                self.assertIsNotNone(p4.contract_policy_problem(contract, ROOT))
        self.assertEqual(
            f"{records.P6_POLICY_CHANGE_CONTRACT} Runs bind the {p4.P6_POLICY_ID} family policy, never "
            f"{p4.P5_POLICY_ID!r}: a Policy Review is reviewed under the pre-change Effective Policy only a P6-capable "
            "Run freezes", p4.contract_policy_problem(records.P6_POLICY_CHANGE_CONTRACT, p4.P5_POLICY_ID),
            "RB6's refusal text byte for byte")
        # RB5PSW-3 (the RB5 side pins the same parity): every restricted contract states its own refusal reason, so
        # a CONTRACT_POLICIES key without its reason fails here, never as a KeyError at a Run open
        self.assertEqual(set(p4.CONTRACT_POLICIES), set(p4._CONTRACT_POLICY_REASONS))
        for contract in (p4.WORK_CONTRACT, p4.PLANNING_CONTRACT):
            with self.subTest(request=contract), self.assertRaises(ValidationError):
                discovery(contract=contract)
        with self.assertRaises(ValidationError):
            discovery(policy_id=p4.P6_POLICY_ID)

    def test_a_root_request_binds_no_history_effective_policy_or_role(self) -> None:
        found = discovery()
        self.assertEqual(ROOT, found["policy_id"])
        for key in (history.HISTORY_CONTRACT_KEY, "set_aside_summaries", "decision_evidence", "prior_history",
                    policy.EFFECTIVE_POLICY_KEY, policy.DISCOVERY_ROLE_KEY):
            with self.subTest(key=key):
                self.assertNotIn(key, found)
                self.assertNotIn(key, adjudication())
        self.assertEqual(p4.ADJUDICATION_INSTRUCTION, adjudication()["instruction"])
        for name, call in {
            "set-aside summaries": lambda: discovery(set_aside_summaries=[{"review_run_id": "rr_01ARZ3NDEKTSV4RRFFQ69G5FAW",
                                                                          "digest": "1" * 64}]),
            "decision evidence": lambda: discovery(decision_evidence=[{
                "review_decision_id": "rhd_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "affected_review_run_id": "rr_01ARZ3NDEKTSV4RRFFQ69G5FAW", "digest": "1" * 64}]),
            "an Effective Policy": lambda: discovery(effective_policy={"x": 1}),
            "a discovery role": lambda: discovery(discovery_role=policy.ROLE_REQUIRED),
            "prior history": lambda: adjudication(prior_history=[{"family": "runs", "id": "rr_01ARZ3NDEKTSV4RRFFQ69G5FAW",
                                                                 "digest": "1" * 64}]),
            "an adjudication Effective Policy": lambda: adjudication(effective_policy={"x": 1}),
        }.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                call()
        with self.assertRaises(ValidationError) as raised:
            p4.repair_request(review_contract=CONTRACT, review_kind=records.GLOBAL_POLICY_REVIEW_KIND,
                              review_run_id="rr_01ARZ3NDEKTSV4RRFFQ69G5FAV", candidate_hash="a" * 64,
                              candidate_generation=1, requirement={}, repair_batch_id="rrb_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                              repair_batch_digest="1" * 64, allowed_result_surface=(), strategy="s",
                              evidence_constraints=(), policy_id=ROOT)
        self.assertEqual("review_contract_invalid", raised.exception.code)

    def test_the_envelope_is_classified_by_its_explicit_identity_and_hashed_statically(self) -> None:
        envelope = discovery()
        static = p4.family_policy_hash(ROOT)
        self.assertEqual((ROOT, CONTRACT, static), (p4.policy_of_envelope(envelope), p4.contract_of_envelope(envelope),
                                                    p4.envelope_policy_hash(envelope)))
        self.assertIsNone(p4.effective_policy_of_envelope(envelope))
        for name, changed in {
            "with a history contract": {**envelope, history.HISTORY_CONTRACT_KEY: history.HISTORY_CONTRACT},
            "with an Effective Policy": {**envelope, policy.EFFECTIVE_POLICY_KEY: {}},
        }.items():
            with self.subTest(name):
                self.assertIsNone(p4.policy_of_envelope(changed))
                self.assertIsNone(p4.contract_of_envelope(changed))
        self.assertIsNone(p4.contract_of_envelope({**envelope, "review_contract": p4.WORK_CONTRACT}))
        self.assertEqual(static, p4.run_effective_policy_hash(ROOT, None))
        with self.assertRaises(ValidationError):
            p4.run_effective_policy_hash(ROOT, {"x": 1})
        found = p4.task_input(
            task_id="rtk_01ARZ3NDEKTSV4RRFFQ69G5FAV", task_slot=p4.discovery_slot("correctness"),
            task_kind=p4.TASK_KIND_DISCOVERY, actor_identity="reviewer-a", actor_version="1", envelope=envelope,
            candidate_hash="a" * 64, candidate_material_digest="c" * 64, review_context_hash="b" * 64,
            accepted_generation=1, policy_id=ROOT)
        self.assertEqual(static, found.effective_policy_hash)
        self.assertEqual(ROOT, p4.policy_of_task_input(found))

    def test_a_work_p4_context_never_names_the_root_policy(self) -> None:
        """RB7C-1 (c): the Work P4 Context admits ``FAMILY_POLICY_IDS``, which never gains the root policy."""
        self.assertNotIn(ROOT, p4.FAMILY_POLICY_IDS)
        self.assertEqual((p4.POLICY_ID, p4.P5_POLICY_ID, p4.P6_POLICY_ID), p4.FAMILY_POLICY_IDS)
        with self.assertRaises(ValidationError):
            work_review.inner_context({"schema": work_review.SCHEMA_P4_CONTEXT, "version": work_review.RECORD_VERSION,
                                       "review_contract": work_review.P4_CONTRACT, "policy_id": ROOT,
                                       "work_context": {}})


if __name__ == "__main__":
    unittest.main()
