"""P6 §30.36: the Policy Review (``project-policy-change-v1``) under the frozen §15.19 / §30.12-§30.14 contract.

Every flow runs through ``project_policy.change_project_policy`` on a real evidence Project with scripted,
terminating actors (``project_policy_helpers``). Covered (frozen bullets of §30.36):

* the PRE-CHANGE Effective Policy's ``required_slots`` controls the reviewer count (§30.13);
* a proposed lightening cannot reduce its own review, and an active holdout plan is part of the pre-change policy;
* G1-G5 topology (§30.14);
* the P4 discovery / adjudication helpers are reused (§30.12);
* the fixed mechanical meta-verifier catches a forbidden change whatever the reviewers said (§15.19, §30.14);
* blocking -> terminal at G4, no Receipt; HUMAN -> HUMAN_WAIT at G4, no Receipt;
* authorization -> G5 sealed + Receipt;
* there is no Repair Batch branch;
* P5 history boundaries (Finding summaries at G4, the Run summary at its final durable disposition).
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any
from unittest import mock

from project_policy_helpers import (
    GENERATION_SUBJECT, KM_SUBJECT, KP_SUBJECT, Adjudicator, Crash, Discovery, PolicyCase, claim, crash_at,
    policy_review, two_reviewers,
)
from workline import project_policy
from workline.errors import StopError
from workline.review import history, p4, paths, policy, records, serialize
from workline.review.store import ReviewStore


def first_envelope(review: ReviewStore, run_id: str) -> dict[str, Any]:
    chain = review.gate_chain(run_id)
    return review.read_task_input(str(chain.generations[0].accepted_tasks[0]["task_id"])).request_envelope


def discovery_envelopes(review: ReviewStore, run_id: str) -> list[dict[str, Any]]:
    chain = review.gate_chain(run_id)
    return [review.read_task_input(str(task["task_id"])).request_envelope
            for task in chain.generations[0].accepted_tasks if task["task_kind"] == p4.TASK_KIND_DISCOVERY]


class ReviewerCountTests(PolicyCase):
    """§30.13: discovery actors sufficient for the PRE-CHANGE Effective Policy ``required_slots``."""

    template = "profiled"  # Profile v1: required_slots 2

    def first_change(self) -> str:
        (change_id,) = self.review_store.policy_change_ids()
        return change_id

    def assert_nothing_written(self, runs: tuple[str, ...], head: str, profile: bytes | None) -> None:
        self.assertEqual(runs, self.review_store.run_ids(), "no Review Run was started")
        self.assertEqual(head, self.commit_of(), "nothing was committed")
        self.assertEqual(profile, self.profile_bytes(), "the Profile is untouched")
        self.assertEqual([], self.policy_pending(), "no policy change is left pending")

    def test_the_pre_change_required_slots_controls_the_reviewer_count(self) -> None:
        before = self.state()
        self.assertEqual(2, policy.setting(before.effective, policy.SURFACE_REQUIRED_SLOTS))
        request = self.request(after=3, supersedes=(self.first_change(),), overlap=policy.OVERLAP_KNOWN)
        runs, head, profile = self.review_store.run_ids(), self.commit_of(), self.profile_bytes()
        for name, review in (
            ("one reviewer", policy_review()),
            ("two slots on one reviewer identity/version pair",
             policy_review(Discovery(), Discovery(viewpoint="safety"))),
        ):
            with self.subTest(name), self.assertRaises(StopError) as raised:
                self.change(request, review)
            self.assertEqual(policy.CODE_DISCOVERY_SLOTS_UNMET, raised.exception.code)
            self.assert_nothing_written(runs, head, profile)
        result = self.applied(request, two_reviewers())
        review = self.review_store
        chain = review.gate_chain(result.review_run_id)
        discovery = [task for task in chain.generations[0].accepted_tasks if task["task_kind"] == p4.TASK_KIND_DISCOVERY]
        self.assertEqual(2, len(discovery), "exactly the two required discovery slots are accepted at G1")
        self.assertEqual(2, len({(task["reviewer_identity"], task["reviewer_version"]) for task in discovery}))
        for envelope in discovery_envelopes(review, result.review_run_id):
            self.assertEqual(before.effective, envelope[policy.EFFECTIVE_POLICY_KEY], "bound to the BEFORE policy")
            self.assertEqual(policy.ROLE_REQUIRED, envelope[policy.DISCOVERY_ROLE_KEY])
        self.assertEqual(before.effective_hash, chain.generations[0].effective_policy_hash)
        self.assertEqual(3, self.state().profile.setting_of(policy.SURFACE_REQUIRED_SLOTS))

    def test_a_resumed_review_still_binds_the_pre_change_reviewers(self) -> None:
        """§30.13 / §30.2 A: the reviewer count is the pre-change policy's on EVERY pass, a resume after the freeze too."""
        request = self.request(after=3, supersedes=(self.first_change(),), overlap=policy.OVERLAP_KNOWN)
        before = self.state()
        with crash_at(project_policy, "_accept"), self.assertRaises(Crash):
            self.change(request, two_reviewers())
        head, profile = self.commit_of(), self.profile_bytes()
        with self.assertRaises(StopError) as raised:
            self.change(request, policy_review())  # the same request resumed with one reviewer
        self.assertEqual(policy.CODE_DISCOVERY_SLOTS_UNMET, raised.exception.code)
        self.assertEqual([], self.policy_runs()[1:], "no Policy Review Run beyond the template's is started")
        self.assertEqual(head, self.commit_of())
        self.assertEqual(profile, self.profile_bytes())
        result = self.applied(request, two_reviewers())
        chain = self.review_store.gate_chain(result.review_run_id)
        self.assertEqual(2, len([t for t in chain.generations[0].accepted_tasks
                                 if t["task_kind"] == p4.TASK_KIND_DISCOVERY]))
        self.assertEqual(before.effective_hash, chain.generations[0].effective_policy_hash)

    def test_a_proposed_lightening_cannot_reduce_its_own_review(self) -> None:
        before = self.state()
        first = self.first_change()
        lighten = self.request(direction=policy.DIRECTION_LIGHTEN, after=1, supersedes=(first,),
                               overlap=policy.OVERLAP_KNOWN, expected_effect="one discovery reviewer suffices")
        runs, head, profile = self.review_store.run_ids(), self.commit_of(), self.profile_bytes()
        with self.assertRaises(StopError) as raised:
            self.change(lighten, policy_review())  # what the AFTER state would need
        self.assertEqual(policy.CODE_DISCOVERY_SLOTS_UNMET, raised.exception.code)
        self.assert_nothing_written(runs, head, profile)
        result = self.applied(lighten, two_reviewers())
        review = self.review_store
        chain = review.gate_chain(result.review_run_id)
        self.assertEqual(before.effective_hash, chain.generations[0].effective_policy_hash)
        receipt = review.read_receipt(str(result.receipt_id))
        self.assertEqual(before.effective_hash, receipt.effective_policy_hash, "never authorized under the after state")
        envelopes = discovery_envelopes(review, result.review_run_id)
        self.assertEqual(2, len(envelopes))
        self.assertEqual({2}, {policy.setting(env[policy.EFFECTIVE_POLICY_KEY], policy.SURFACE_REQUIRED_SLOTS)
                               for env in envelopes})
        change = review.read_policy_change(result.policy_change_id)
        self.assertEqual({"policy_surface_id": policy.SURFACE_REQUIRED_SLOTS, "holdout_setting": 2,
                          "selection": policy.HOLDOUT_SELECTION_ALL_RELEVANT}, change["holdout_plan"],
                         "the removed stronger behaviour stays an independent holdout")
        # the next Policy Review is reviewed under THIS pre-change policy: 1 required slot + the frozen holdout slot
        after = self.state()
        self.assertEqual(1, policy.setting(after.effective, policy.SURFACE_REQUIRED_SLOTS))
        self.assertEqual(1, policy.required_holdout_slots(after.effective))
        again = self.request(after=2, supersedes=(result.policy_change_id,), overlap=policy.OVERLAP_KNOWN)
        runs, head, profile = self.review_store.run_ids(), self.commit_of(), self.profile_bytes()
        for name, review_binding, code in (
            ("no holdout actor", policy_review(), policy.CODE_HOLDOUT_UNBOUND),
            ("holdout on a required reviewer's pair", policy_review(
                holdout=(Discovery(viewpoint="holdout"),)), policy.CODE_HOLDOUT_UNBOUND),
        ):
            with self.subTest(name), self.assertRaises(StopError) as raised:
                self.change(again, review_binding)
            self.assertEqual(code, raised.exception.code)
            self.assert_nothing_written(runs, head, profile)
        third = self.applied(again, policy_review(holdout=(Discovery(viewpoint="holdout", identity="holdout"),)))
        roles = sorted(env[policy.DISCOVERY_ROLE_KEY] for env in discovery_envelopes(self.review_store,
                                                                                    third.review_run_id))
        self.assertEqual([policy.ROLE_HOLDOUT, policy.ROLE_REQUIRED], roles)


class TopologyTests(PolicyCase):
    """§30.14 G1-G5 and §30.12: the dedicated kind, its identities, and the reused P1 / P4 primitives."""

    def test_g1_to_g5_seals_a_receipt_for_exactly_the_candidate(self) -> None:
        before = self.state()
        discovery = Discovery(claim("improve", "MID", "a clearer success criterion"))
        result = self.applied(review=policy_review(discovery))
        review = self.review_store
        chain = review.gate_chain(result.review_run_id)
        generations = chain.generations
        self.assertEqual([1, 2, 3, 4, 5], [g.generation for g in generations])
        self.assertEqual([], p4.chain_problems(chain))
        self.assertEqual(p4.SHAPE_SEAL, p4.shape_of(chain))
        for gate in generations:
            self.assertEqual(policy.REVIEW_KIND, gate.review_kind)
            self.assertEqual(policy.TARGET_IDENTITY, gate.target_identity)
            self.assertEqual(before.effective_hash, gate.effective_policy_hash)
        # G1: the CandidateSnapshot and the required discovery TaskInputs, the gate open
        first = generations[0]
        self.assertEqual(records.GATE_STATUS_OPEN, first.status)
        self.assertEqual([p4.TASK_KIND_DISCOVERY], [t["task_kind"] for t in first.accepted_tasks])
        snapshot = review.read_candidate_snapshot(first.candidate_hash)
        self.assertEqual(policy.candidate_hash(snapshot.material), first.candidate_hash)
        self.assertEqual(policy.SCHEMA_CANDIDATE, snapshot.material[serialize.SCHEMA_KEY])
        self.assertEqual(result.policy_change_id, snapshot.material["policy_change_id"])
        self.assertEqual(policy.TARGET_IDENTITY, snapshot.material["target_identity"])
        # G2: the sanitized discovery report settled, before any adjudication
        second = generations[1]
        self.assertEqual(1, len(second.settled_tasks))
        digest = second.settled_tasks[0]["result_digest"]
        self.assertEqual(digest, serialize.digest(review.read_report(digest).to_record()))
        self.assertEqual(records.TASK_SETTLED_OK, second.settled_tasks[0]["status"])
        # G3: one adjudication TaskInput accepted
        self.assertEqual(p4.TASK_KIND_ADJUDICATION, generations[2].accepted_tasks[-1]["task_kind"])
        self.assertEqual(len(first.accepted_tasks) + 1, len(generations[2].accepted_tasks))
        # G4: the adjudication settled and recorded
        adjudication = review.read_adjudication(result.review_run_id)
        self.assertEqual(p4.AUTHORIZATION_READY, adjudication.outcome)
        self.assertEqual(generations[3].adjudication_digest, serialize.digest(adjudication.to_record()))
        # G5: sealed with the Receipt; no Receipt before it
        self.assertEqual([None, None, None, None], [g.receipt_id for g in generations[:4]])
        self.assertTrue(generations[4].sealed)
        self.assertEqual(result.receipt_id, generations[4].receipt_id)
        self.assertEqual(policy.AUTHORIZED_OPERATION_STAGE, generations[4].authorized_operation_stage)
        receipt = review.read_receipt(str(result.receipt_id))
        self.assertEqual(p4.SEAL_GENERATION, receipt.review_generation)
        self.assertEqual(policy.REVIEW_KIND, receipt.review_kind)
        self.assertEqual(policy.TARGET_IDENTITY, receipt.target_identity)
        self.assertEqual(first.candidate_hash, receipt.authorized_candidate_hash)
        self.assertEqual("project-policy-change:persist-profile", receipt.authorized_operation_stage)
        self.assertEqual(before.effective_hash, receipt.effective_policy_hash)
        self.assertEqual(0, receipt.unresolved_obligations)
        self.assertEqual([str(result.receipt_id)], self.policy_receipts())
        # one generation commit each, then Kp and Km
        subjects = [self.subject(c) for c in self.git("rev-list", "-7", "HEAD").split()]
        self.assertEqual(f"{KM_SUBJECT}{result.consumption_id}", subjects[0])
        self.assertEqual(f"{KP_SUBJECT}{result.policy_change_id}", subjects[1])
        self.assertEqual([f"{GENERATION_SUBJECT}{n} of {result.review_run_id}" for n in (5, 4, 3, 2, 1)], subjects[2:7])
        self.assertEqual([], self.problems())

    def test_the_policy_review_kind_is_the_dedicated_one(self) -> None:
        self.assertEqual("project-policy-change-v1", policy.REVIEW_KIND)
        self.assertEqual("project-policy", policy.TARGET_IDENTITY)
        self.assertEqual("project-policy-change:persist-profile", policy.AUTHORIZED_OPERATION_STAGE)
        self.assertIn(policy.POLICY_CHANGE_CONTRACT, records.P4_CONTRACTS)
        self.assertNotIn(policy.POLICY_CHANGE_CONTRACT, records.P4_REPAIR_CONTRACTS)

    def test_the_p4_discovery_and_adjudication_helpers_are_reused(self) -> None:
        spied = {name: mock.patch.object(p4, name, wraps=getattr(p4, name)) for name in (
            "discovery_request", "task_input", "report_record", "adjudication_request", "normalize_adjudication",
            "adjudication", "g4_history", "convergence_from_records")}
        mocks = {name: patcher.start() for name, patcher in spied.items()}
        for patcher in spied.values():
            self.addCleanup(patcher.stop)
        adjudicator = Adjudicator()
        result = self.applied(review=policy_review(Discovery(claim("improve", "MID")), adjudicator=adjudicator))
        for name, found in mocks.items():
            self.assertTrue(found.called, f"the Policy Review reuses p4.{name}")
        for call in mocks["discovery_request"].call_args_list + mocks["adjudication_request"].call_args_list:
            self.assertEqual(policy.POLICY_CHANGE_CONTRACT, call.kwargs["review_contract"])
            self.assertEqual(policy.REVIEW_KIND, call.kwargs["review_kind"])
        (task,) = adjudicator.tasks
        self.assertIsInstance(task, p4.P4AdjudicationTask)
        self.assertEqual(1, len(task.reports), "the sanitized discovery report is what the adjudicator reads")
        adjudication = self.review_store.read_adjudication(result.review_run_id)
        self.assertIsInstance(adjudication, records.P4Adjudication)
        self.assertEqual(policy.POLICY_CHANGE_CONTRACT, adjudication.review_contract)
        self.assertEqual(p4.adjudication_instruction_of(p4.P6_POLICY_ID), adjudication.instruction)


class MetaVerifierTests(PolicyCase):
    """§15.19 / §30.14: the fixed mechanical meta-verifier, whatever any external reviewer said."""

    def candidate(self, request: policy.PolicyChangeRequest | None = None) -> tuple[dict[str, Any], policy.PolicyState]:
        state = self.state()
        record = policy.request_record(request or self.request())
        return policy.build_candidate(record, "rpc_01ARZ3NDEKTSV4RRFFQ69G5FAV", state, self.review_store), state

    def codes(self, candidate: dict[str, Any], state: policy.PolicyState) -> list[str]:
        return [code for code, _ in policy.candidate_problems(candidate, state, self.review_store)]

    def test_a_valid_candidate_passes_and_every_forbidden_change_is_caught(self) -> None:
        candidate, state = self.candidate()
        self.assertEqual([], self.codes(candidate, state))
        steps = policy.SURFACE_BY_ID[policy.SURFACE_EXTRA_SCOPE_STEPS]

        def other_surface(c: dict[str, Any]) -> None:
            c["after_profile"]["overrides"].append({
                "policy_surface_id": steps.policy_surface_id, "strength_class": steps.strength_class, "setting": 2,
                "direction": "strengthen", "supporting_policy_change_id": c["policy_change_id"]})

        def free_form(c: dict[str, Any]) -> None:
            c["after_profile"]["script"] = "lower every severity"

        def reclassified(c: dict[str, Any]) -> None:
            c["strength_class"] = policy.CLASS_ADAPTIVE

        def non_adaptive(c: dict[str, Any]) -> None:
            c["affected_policy_surface"] = "review.severity.blocking"

        def unmeasured(c: dict[str, Any]) -> None:
            c["holdout_plan"] = {"policy_surface_id": policy.SURFACE_REQUIRED_SLOTS, "holdout_setting": 1,
                                 "selection": policy.HOLDOUT_SELECTION_ALL_RELEVANT}

        def single_event(c: dict[str, Any]) -> None:
            c["evidence"] = c["evidence"][:1]
            c["relevant_opportunity"]["opportunities"] = c["relevant_opportunity"]["opportunities"][:1]

        def duplicate(c: dict[str, Any]) -> None:
            c["evidence"] = [c["evidence"][0], dict(c["evidence"][0])]

        def wrong_digest(c: dict[str, Any]) -> None:
            c["evidence"][0]["digest"] = "0" * 64

        def unattributed(c: dict[str, Any]) -> None:
            c["environment_identity"]["global_baseline_digest"] = "0" * 64

        def wrong_rollback_unit(c: dict[str, Any]) -> None:
            c["rollback_unit"]["restore_setting"] = 3

        def stale_before(c: dict[str, Any]) -> None:
            c["before_profile"] = {"profile_version": 1, "digest": "0" * 64}

        for name, change, code in (
            ("another surface's override changes", other_surface, policy.CODE_FORBIDDEN_CHANGE),
            ("a free-form field in the after Profile", free_form, policy.CODE_FORBIDDEN_CHANGE),
            ("a reclassified surface", reclassified, policy.CODE_RECLASSIFIED),
            ("the absolute non-adaptive surface", non_adaptive, policy.CODE_SURFACE_NON_ADAPTIVE),
            ("an upward change carrying a holdout", unmeasured, policy.CODE_LIGHTENING_UNMEASURED),
            ("one opportunity for a permanent change", single_event, policy.CODE_SINGLE_EVENT),
            ("one source twice", duplicate, policy.CODE_DUPLICATE_EVIDENCE),
            ("evidence digest mismatch", wrong_digest, policy.CODE_EVIDENCE_INVALID),
            ("environment not attributed", unattributed, policy.CODE_ENVIRONMENT_UNATTRIBUTED),
            ("rollback unit not the pre-change setting", wrong_rollback_unit, policy.CODE_CANDIDATE_INVALID),
            ("a stale before Profile", stale_before, policy.CODE_BEFORE_STATE_CONFLICT),
        ):
            tampered = serialize.canonical_data(candidate)
            change(tampered)
            with self.subTest(name):
                self.assertIn(code, self.codes(tampered, state))

    def test_a_non_adaptive_surface_is_refused_before_any_review_or_write(self) -> None:
        runs, head = self.review_store.run_ids(), self.commit_of()
        for surface in ("review.severity.blocking", "review.authorization.consumption", "lifecycle.completion",
                        "review.discovery.unknown_surface"):
            with self.subTest(surface), self.assertRaises(StopError) as raised:
                self.change(self.request(surface=surface))
            self.assertIn(raised.exception.code, (policy.CODE_SURFACE_NON_ADAPTIVE, policy.CODE_SURFACE_UNKNOWN))
        self.assertEqual(runs, self.review_store.run_ids())
        self.assertEqual(head, self.commit_of())
        self.assertIsNone(self.profile_bytes())

    def forbidden_candidates(self):
        """``policy.build_candidate`` returning the real Candidate plus another surface's override (a forbidden change)."""
        real = policy.build_candidate

        def build(request, policy_change_id, state, reader):
            found = serialize.canonical_data(real(request, policy_change_id, state, reader))
            steps = policy.SURFACE_BY_ID[policy.SURFACE_EXTRA_SCOPE_STEPS]
            found["after_profile"]["overrides"].append({
                "policy_surface_id": steps.policy_surface_id, "strength_class": steps.strength_class, "setting": 2,
                "direction": "strengthen", "supporting_policy_change_id": policy_change_id})
            return serialize.canonical_data(found)

        return mock.patch.object(policy, "build_candidate", build)

    def test_a_forbidden_candidate_is_refused_although_every_reviewer_passes_it(self) -> None:
        discovery, adjudicator = Discovery(), Adjudicator()
        with self.forbidden_candidates(), self.assertRaises(StopError) as raised:
            self.change(review=policy_review(discovery, adjudicator=adjudicator))
        self.assertEqual(policy.CODE_FORBIDDEN_CHANGE, raised.exception.code)
        self.assertEqual([], self.policy_receipts())
        self.assertEqual([], self.policy_runs(), "refused before G1")
        self.assertIsNone(self.profile_bytes())
        self.assertEqual((), self.review_store.policy_change_ids())

    def test_the_g4_meta_verification_refuses_what_the_adjudicator_authorized(self) -> None:
        """§30.14: G4 = adjudication + the fixed mechanical meta-policy verification - even after the reviewers pass."""
        real = policy.candidate_problems
        calls = {"n": 0}

        def first_passes(candidate, state, reader):
            calls["n"] += 1
            return [] if calls["n"] == 1 else real(candidate, state, reader)

        adjudicator = Adjudicator()
        with self.forbidden_candidates(), mock.patch.object(policy, "candidate_problems", first_passes), \
                self.assertRaises(StopError) as raised:
            self.change(review=policy_review(Discovery(), adjudicator=adjudicator))
        self.assertEqual(policy.CODE_FORBIDDEN_CHANGE, raised.exception.code)
        self.assertEqual(1, len(adjudicator.tasks), "the adjudicator was asked and passed it")
        (run_id,) = self.policy_runs()
        chain = self.review_store.gate_chain(run_id)
        self.assertLess(len(chain.generations), p4.SEAL_GENERATION, "no seal")
        self.assertEqual([], self.policy_receipts(), "no Receipt")
        self.assertIsNone(self.profile_bytes())
        self.assertEqual((), self.review_store.policy_change_ids())


class NonAuthorizingTests(PolicyCase):
    """§30.14: blocking -> terminal at G4, no Receipt; HUMAN -> HUMAN_WAIT at G4, no Receipt; no Repair Batch."""

    def assert_no_authorization(self, result: project_policy.PolicyChangeResult, generations: int,
                                disposition: str) -> None:
        review = self.review_store
        chain = review.gate_chain(result.review_run_id)
        self.assertEqual(generations, len(chain.generations))
        self.assertEqual([None] * generations, [g.receipt_id for g in chain.generations])
        self.assertIsNone(result.receipt_id)
        self.assertIsNone(result.consumption_id)
        self.assertEqual([], self.policy_receipts())
        self.assertEqual([], self.policy_consumptions(), "no Policy Consumption")
        self.assertEqual((), review.repair_batch_ids(), "a Policy Review has no Repair Batch branch")
        self.assertIsNone(self.profile_bytes(), "nothing is written to the Profile")
        self.assertEqual((), review.policy_change_ids())
        self.assertEqual([], self.commits_with(KP_SUBJECT))
        self.assertEqual([], self.policy_pending())
        summary = review.read_history(paths.HISTORY_RUNS, result.review_run_id)
        self.assertEqual(disposition, summary.durable_disposition)
        self.assertIsNone(summary.receipt_id)
        self.assertEqual([], self.problems())

    def test_a_blocking_problem_is_terminal_at_g4_with_no_receipt(self) -> None:
        result = self.change(review=policy_review(Discovery(claim("problem"))))
        self.assertEqual(project_policy.STATUS_NOT_AUTHORIZED, result.status)
        self.assertEqual(records.REPAIR_REQUIRED, self.review_store.read_adjudication(result.review_run_id).outcome)
        self.assert_no_authorization(result, 4, history.DISPOSITION_NOT_AUTHORIZED)
        (finding,) = result.findings
        self.assertTrue(finding["blocking"])
        self.assertIn(finding["finding_id"], self.review_store.finding_history_ids())

    def test_human_is_human_wait_at_g4_with_no_receipt(self) -> None:
        result = self.change(review=policy_review(Discovery(claim("human"))))
        self.assertEqual(project_policy.STATUS_HUMAN_WAIT, result.status)
        self.assertEqual(records.HUMAN_WAIT, self.review_store.read_adjudication(result.review_run_id).outcome)
        self.assert_no_authorization(result, 4, history.DISPOSITION_HUMAN_WAIT)

    def test_a_declined_discovery_task_is_not_authorizing_at_g2(self) -> None:
        result = self.change(review=policy_review(Discovery(status="declined")))
        self.assertEqual(project_policy.STATUS_NOT_AUTHORIZED, result.status)
        self.assert_no_authorization(result, 2, history.DISPOSITION_NOT_AUTHORIZED)

    def test_there_is_no_repair_batch_branch(self) -> None:
        self.assertEqual(["discovery", "adjudicator", "holdout_discovery"],
                         [item.name for item in fields(project_policy.PolicyReview)], "no repair actor")
        with self.assertRaises(TypeError):
            project_policy.PolicyReview((Discovery().binding(),), Adjudicator().binding(), (),  # type: ignore[call-arg]
                                        Adjudicator().binding())
        self.assertFalse(p4.repairs(policy.POLICY_CHANGE_CONTRACT))
        blocked = self.change(review=policy_review(Discovery(claim("problem"))))
        self.assertEqual(project_policy.STATUS_NOT_AUTHORIZED, blocked.status)
        old = self.review_store.gate_chain(blocked.review_run_id)
        # the same proposal again is a later new Candidate and Run; the blocked Run is never repaired or continued
        again = self.change(review=policy_review(Discovery()))
        self.assertEqual(project_policy.STATUS_APPLIED, again.status, again.detail)
        self.assertNotEqual(blocked.review_run_id, again.review_run_id)
        self.assertNotEqual(blocked.policy_change_id, again.policy_change_id)
        self.assertEqual(old.generations, self.review_store.gate_chain(blocked.review_run_id).generations)
        self.assertEqual((), self.review_store.repair_batch_ids())
        self.assertEqual((), self.review_store.repair_result_ids())
        self.assertEqual([], self.problems())


class HistoryBoundaryTests(PolicyCase):
    """§30.12 / §30.31: P5 Finding / Run history at its frozen boundaries, references never copies."""

    template = "profiled"

    def test_findings_at_g4_and_the_run_summary_only_at_its_final_disposition(self) -> None:
        (first_change,) = self.review_store.policy_change_ids()
        first_run = self.review_store.read_policy_change(first_change)["review_run_id"]
        request = self.request(after=3, supersedes=(first_change,), overlap=policy.OVERLAP_KNOWN)
        result = self.applied(request, policy_review(
            Discovery(claim("improve", "MID", "a clearer measurement window")),
            Discovery(viewpoint="safety", identity="discovery-two")))
        review = self.review_store
        run_id = result.review_run_id
        envelope = first_envelope(review, run_id)
        self.assertEqual(p4.P6_POLICY_ID, envelope["policy_id"])
        self.assertEqual(history.HISTORY_CONTRACT, envelope[history.HISTORY_CONTRACT_KEY])
        generation_commits = {int(self.subject(c).split()[5]): c for c in self.commits_with(GENERATION_SUBJECT)
                              if self.subject(c).endswith(run_id)}
        (finding,) = result.findings
        finding_path = paths.history_finding_rel(finding["finding_id"])
        summary_path = paths.history_run_rel(run_id)
        self.assertFalse(self.has_path(generation_commits[3], finding_path))
        self.assertTrue(self.has_path(generation_commits[4], finding_path), "the Finding summary is G4's")
        for generation in (1, 2, 3, 4, 5):
            self.assertFalse(self.has_path(generation_commits[generation], summary_path))
        (kp,) = [c for c in self.commits_with(KP_SUBJECT) if self.subject(c).endswith(result.policy_change_id)]
        self.assertFalse(self.has_path(kp, summary_path), "no Run summary before the Consumption")
        self.assertTrue(self.has_path(str(result.metadata_commit), summary_path))
        summary = review.read_history(paths.HISTORY_RUNS, run_id)
        self.assertEqual(history.DISPOSITION_CONSUMED, summary.durable_disposition)
        self.assertEqual(result.consumption_id, summary.consumption_id)
        self.assertEqual(result.receipt_id, summary.receipt_id)
        # the adjudication is offered the earlier Policy Review Run's validated history, by reference
        adjudication_task = [t for t in review.gate_chain(run_id).generations[2].accepted_tasks
                             if t["task_kind"] == p4.TASK_KIND_ADJUDICATION][0]
        prior = review.read_task_input(str(adjudication_task["task_id"])).request_envelope["prior_history"]
        self.assertIn({"family": paths.HISTORY_RUNS, "id": first_run,
                       "digest": review.history_digest(paths.HISTORY_RUNS, first_run)},
                      [dict(item) for item in prior])
        # the change record references P5 sources by identity and digest, never copies them
        change = review.read_policy_change(result.policy_change_id)
        self.assertEqual([ref.to_record() for ref in request.evidence], change["evidence"])
        self.assertEqual([], self.problems())

    def test_a_non_authorizing_review_writes_its_run_summary_at_g4(self) -> None:
        (first_change,) = self.review_store.policy_change_ids()
        request = self.request(after=3, supersedes=(first_change,), overlap=policy.OVERLAP_KNOWN)
        result = self.change(request, policy_review(Discovery(claim("problem")),
                                                    Discovery(viewpoint="safety", identity="discovery-two")))
        self.assertEqual(project_policy.STATUS_NOT_AUTHORIZED, result.status)
        (g4,) = [c for c in self.commits_with(GENERATION_SUBJECT)
                 if self.subject(c) == f"{GENERATION_SUBJECT}4 of {result.review_run_id}"]
        self.assertEqual(self.commit_of(), g4, "nothing after G4")
        self.assertTrue(self.has_path(g4, paths.history_run_rel(result.review_run_id)))
        for finding in result.findings:
            self.assertTrue(self.has_path(g4, paths.history_finding_rel(finding["finding_id"])))
        self.assertEqual([], self.problems())


if __name__ == "__main__":
    import unittest

    unittest.main()
