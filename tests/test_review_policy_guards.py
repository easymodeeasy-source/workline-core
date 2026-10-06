"""P6 guards the independent model review (RB6-B) found open: each one positive and negative (RB6B-M10).

* M3: a Profile no Policy Change produced never becomes a new Run's Effective Policy (lineage gate);
* M4: the Policy Review contract binds only the P6-capable family policy - builders, readers and validation;
* M5: a stored P6 request is classified by its stored identity; an unreadable frozen record fails closed;
* L2: the Profile read boundary is byte-exact; L9: another loader's Profile is incompatible, never malformed;
* L5: a non-v3 Consumption of a Policy Receipt is named by its Receipt;
* L6 / L7: the Profile CAS records only a canonical Profile; write_file never reaches the policy namespace in any
  letter case.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
import unittest

from helpers import WORKLINE_ROOT, WorklineTestCase
from workline import mutation
from workline.errors import StopError, ValidationError
from workline.review import p4, paths, policy, serialize, validate
from workline.review.store import ReviewStore

RPC = "rpc_01ARZ3NDEKTSV4RRFFQ69G5FAV"


def a_profile(*, loader: str = policy.LOADER_SEMANTICS_IDENTITY) -> policy.ProjectProfile:
    surface = policy.SURFACE_BY_ID[policy.SURFACE_REQUIRED_SLOTS]
    return policy.ProjectProfile(
        profile_version=1, parent_profile_digest=None,
        global_baseline_digest=policy.load_global_baseline(WORKLINE_ROOT).digest, global_baseline_version=1,
        loader_semantics_identity=loader,
        overrides=({"policy_surface_id": surface.policy_surface_id, "strength_class": surface.strength_class,
                    "setting": 2, "direction": "strengthen", "supporting_policy_change_id": RPC},),
        active_experiment_refs=(RPC,),
    )


def effective() -> dict[str, Any]:
    return policy.effective_policy_record(policy.load_global_baseline(WORKLINE_ROOT), None, ())


def discovery(policy_id: str, *, contract: str = p4.PLANNING_CONTRACT, frozen: Any = None,
              role: str | None = policy.ROLE_REQUIRED) -> dict[str, Any]:
    return p4.discovery_request(
        review_contract=contract, review_kind="planning", viewpoint="correctness", candidate={}, context={},
        requirement={}, candidate_generation=1, succession=None, set_aside_runs=(), human_decision=None,
        policy_id=policy_id, effective_policy=frozen, discovery_role=role if policy_id == p4.P6_POLICY_ID else None)


class LineageGateTests(WorklineTestCase):
    """RB6B-M3: new-Run resolution proves Profile lineage exactly as validation does."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.review = ReviewStore(self.store)

    def test_a_profile_no_change_produced_never_becomes_an_effective_policy(self) -> None:
        target = self.store.root / paths.POLICY_PROFILE_REL
        target.parent.mkdir(parents=True)
        target.write_bytes(a_profile().text().encode("utf-8"))
        with self.assertRaises(StopError) as raised:
            policy.resolve_policy_state(self.review, self.store.workline_root())
        self.assertEqual(policy.CODE_LINEAGE_INVALID, raised.exception.code)
        with self.assertRaises(StopError) as raised:
            policy.current_effective_policy_hash(self.review, self.store.workline_root())
        self.assertEqual(policy.CODE_LINEAGE_INVALID, raised.exception.code)

    def test_absence_with_no_change_record_stays_valid(self) -> None:
        state = policy.resolve_policy_state(self.review, self.store.workline_root())
        self.assertIsNone(state.profile)


class ContractPolicyTests(unittest.TestCase):
    """RB6B-M4: a Policy Review is reviewed under the pre-change Effective Policy only a P6 Run freezes."""

    def test_the_builders_refuse_the_policy_contract_under_a_static_policy(self) -> None:
        for policy_id in (p4.POLICY_ID, p4.P5_POLICY_ID):
            with self.subTest(policy_id), self.assertRaises(ValidationError) as raised:
                discovery(policy_id, contract=policy.POLICY_CHANGE_CONTRACT)
            self.assertEqual("review_contract_invalid", raised.exception.code)
            with self.subTest(policy_id, request="adjudication"), self.assertRaises(ValidationError):
                p4.adjudication_request(
                    review_contract=policy.POLICY_CHANGE_CONTRACT, review_kind=policy.REVIEW_KIND,
                    review_run_id="rr_" + "0" * 26, candidate_hash="a" * 64, candidate_generation=1,
                    review_context_hash="b" * 64, requirement={}, reports=(), prior={}, evidence_ids=(),
                    policy_id=policy_id)
        found = discovery(p4.P6_POLICY_ID, contract=policy.POLICY_CHANGE_CONTRACT, frozen=effective())
        self.assertEqual(policy.POLICY_CHANGE_CONTRACT, p4.contract_of_envelope(found))

    def test_a_forged_static_policy_envelope_is_never_a_policy_review(self) -> None:
        forged = discovery(p4.P5_POLICY_ID)
        forged["review_contract"] = policy.POLICY_CHANGE_CONTRACT
        self.assertEqual(p4.P5_POLICY_ID, p4.policy_of_envelope(forged))
        self.assertIsNone(p4.contract_of_envelope(forged))
        self.assertIsNotNone(p4.contract_policy_problem(policy.POLICY_CHANGE_CONTRACT, p4.P5_POLICY_ID))
        self.assertIsNone(p4.contract_policy_problem(p4.PLANNING_CONTRACT, p4.P5_POLICY_ID),
                          "an unrestricted contract keeps every policy it had")


class FrozenPolicyClassificationTests(unittest.TestCase):
    """RB6B-M5: identity is the stored policy_id; an unreadable frozen record fails closed, never reads as v1."""

    def test_a_drifted_frozen_policy_stays_p6_and_fails_closed(self) -> None:
        envelope = discovery(p4.P6_POLICY_ID, frozen=effective())
        self.assertEqual(p4.P6_POLICY_ID, p4.policy_of_envelope(envelope))
        self.assertEqual(p4.PLANNING_CONTRACT, p4.contract_of_envelope(envelope))
        self.assertIsNotNone(p4.envelope_policy_hash(envelope))
        drifted = serialize.canonical_data(envelope)
        drifted[policy.EFFECTIVE_POLICY_KEY]["meta_rules_digest"] = "0" * 64  # what a later build would not read
        self.assertEqual(p4.P6_POLICY_ID, p4.policy_of_envelope(drifted), "never reclassified")
        self.assertEqual(p4.PLANNING_CONTRACT, p4.contract_of_envelope(drifted), "never read as a v1 request")
        with self.assertRaises(ValidationError) as raised:
            p4.effective_policy_of_envelope(drifted)
        self.assertEqual(policy.CODE_EFFECTIVE_POLICY_UNREADABLE, raised.exception.code)
        self.assertIsNone(p4.envelope_policy_hash(drifted), "no hash is proven, so every comparison fails closed")
        no_role = serialize.canonical_data(envelope)
        no_role.pop(policy.DISCOVERY_ROLE_KEY)
        with self.assertRaises(ValidationError):
            p4.effective_policy_of_envelope(no_role)
        self.assertIsNone(p4.effective_policy_of_envelope(discovery(p4.P5_POLICY_ID)))


class ProfileBoundaryTests(unittest.TestCase):
    def test_the_profile_read_boundary_is_byte_exact(self) -> None:
        """RB6B-L2: ``true`` for an integer is one Python value and two byte shapes - refused."""
        text = a_profile().text()
        self.assertIn("\nversion: 1\n", text)
        for raw in (text.replace("\nversion: 1\n", "\nversion: true\n").encode("utf-8"),
                    text.replace("profile_version: 1\n", "profile_version: true\n").encode("utf-8")):
            with self.subTest(raw=raw[:40]), self.assertRaises(ValidationError) as raised:
                policy.parse_profile_bytes(raw, "p")
            self.assertEqual(policy.CODE_PROFILE_INVALID, raised.exception.code)

    def test_another_loader_is_incompatible_never_malformed(self) -> None:
        """RB6B-L9: the structural reader reads it; the compatibility decision refuses it."""
        foreign = a_profile(loader="review-v1-p6-policy-loader-v9")
        found, _ = policy.parse_profile_bytes(foreign.text().encode("utf-8"), "p")
        self.assertEqual("review-v1-p6-policy-loader-v9", found.loader_semantics_identity)
        reader = SimpleNamespace(policy_change_ids=lambda: (), read_policy_change=None, policy_change_exists=None)
        self.assertIn("loader", policy.compatibility_problem(found, policy.load_global_baseline(WORKLINE_ROOT), reader))
        record = foreign.to_record()
        record["loader_semantics_identity"] = ["not", "a", "label"]
        self.assertIn(policy.CODE_PROFILE_INVALID, [code for code, _ in policy.profile_problems(record, "p")])


class PolicyReceiptConsumptionTests(unittest.TestCase):
    """RB6B-L5: keyed on the Receipt, so no change record is needed to name a non-v3 Consumption of it."""

    def reader(self, kind: str) -> Any:
        consumption = SimpleNamespace(consumption_id="rcs_" + "1" * 26, receipt_id="rcp_" + "1" * 26)
        return SimpleNamespace(
            policy_change_ids=lambda: (), policy_evaluation_ids=lambda: (), read_profile=lambda: None,
            consumptions=lambda: (consumption,), read_receipt=lambda receipt_id: SimpleNamespace(review_kind=kind),
        )

    def test_a_v1_consumption_of_a_policy_receipt_is_a_problem(self) -> None:
        found = validate._policy_records(self.reader(policy.REVIEW_KIND), {})
        self.assertEqual(["review_record_conflict"], [problem.code for problem in found])
        self.assertEqual([], validate._policy_records(self.reader("planning"), {}))


class ProfileEffectTests(unittest.TestCase):
    def test_the_profile_cas_records_only_a_canonical_profile(self) -> None:
        """RB6B-L6: refused when recorded, before anything is written."""
        for content in ("x: 1\n", a_profile().text() + "\n", a_profile().text().replace("\n", "\r\n")):
            with self.subTest(content=content[:20]), self.assertRaises(ValidationError) as raised:
                mutation._validate_profile_replacement(
                    {"path": paths.POLICY_PROFILE_REL, "content": content, "expected_digest": None}, [],
                    policy.OWNER)
            self.assertEqual("review_policy_owner", raised.exception.code)

    def test_write_file_never_reaches_the_policy_namespace_in_any_letter_case(self) -> None:
        """RB6B-L7 (the other Review records keep their pre-existing behaviour, disclosed)."""
        controller = mutation.MutationController.__new__(mutation.MutationController)
        # a spelling whose Review prefix is not the exact-case one: the case-folded policy guard refuses it
        for path in (".workline/Review/policy/project-profile.yaml",
                     ".workline/REVIEW/Policy/changes/" + RPC + ".yaml"):
            with self.subTest(path), self.assertRaises(ValidationError) as raised:
                controller.validate_effect({"kind": "write_file", "payload": {"path": path, "content": "x"}}, [],
                                           "start")
            self.assertEqual("review_policy_owner", raised.exception.code)
        # the exact-case Review prefix keeps its pre-existing refusal (the generic immutable Review record rule)
        for path in (".workline/review/POLICY/project-profile.yaml", paths.POLICY_PROFILE_REL):
            with self.subTest(path), self.assertRaises(ValidationError):
                controller.validate_effect({"kind": "write_file", "payload": {"path": path, "content": "x"}}, [],
                                           "start")


if __name__ == "__main__":
    unittest.main()
