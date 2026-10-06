"""ORCH-RB6-1: a Policy Review whose owner runtime record is lost is recovered by canonical discovery, never bypassed.

Rows (the runtime directory deleted after each):

* after G1 / G2 / G3 / G4 / G5: the same request finds its one recoverable Run by canonical recovery discovery and
  resumes it with its canonical IDs (policy change id, Run, tasks, Receipt) - no substitute Run, one Receipt, one change
  record, one Consumption, and (remote) exactly Kp then Km published; a crash right after the recovered IDs were bound
  resumes that same binding (R7);
* stale (R1): another request's change moved the before-state - the same request is refused before any binding with
  nothing pending, and every later request still runs;
* after Kp (local and remote): the change record is stored without its Consumption, its Kp identity was never durably
  saved: nothing is inferred from Git history, nothing is published, and no Policy Change starts beside it
  (``review_p6_run_unrecovered``); after a revert of that Kp the same request is still refused and never re-adds the
  change record (R2), while other requests run and the barrier is never poisoned;
* after Km: the consumed Run is settled; nothing is duplicated;
* a settled not_authorized Run (a declined G2, a blocking G4) is set aside and the request is a new Run;
* G4 HUMAN_WAIT (CP ruling R8): the same canonical HUMAN_WAIT Run - after runtime loss, after the owner completed,
  after a crash before ``_finish``, after another request moved the before-state - is rediscovered with the same
  policy_change_id / review_run_id and returned as human_wait: no new Run, no set-aside, nothing written or published;
* malformed (R3 / R6 / R9): an uncommitted generation, a task whose provenance does not hold, a G1 with no TaskInput,
  an inconsistent twin only the reconstruction row refuses - ``review_recovery_incomplete`` from discovery itself,
  nothing pending; ambiguous (two recoverable Runs) likewise;
* owner intact (N5): a before-state that moved releases the effect-free owner mutation; N3: a Project with no policy
  history never reads its Consumptions' history.

The publication barrier (PK1-PK9): a proven Kp / Km passes for every push; each item refuses its forgery; a Km
anywhere in the pushed history is proven, even with its Consumption reverted out of the pushed tree (R5 case D); a
history with no policy change gets main's decision and reads plus the one policy change add-history read (R5 case A).
"""

from __future__ import annotations

from typing import Any
from unittest import mock

from helpers import rmtree
from planning_helpers import Crash, crash_at, move_branch, plan, plumb_commit
from project_policy_helpers import (
    GENERATION_SUBJECT, KM_SUBJECT, KP_SUBJECT, Adjudicator, Discovery, Interrupted, PolicyCase, after_effect,
    before_effect, change_request, claim, policy_review, two_reviewers,
)
from workline import gitcmd, project_policy
from workline import roadmap as rm
from workline.errors import ReconcileRequired, StopError
from workline.review import history, paths, policy, publication, records, recovery, serialize


class _RuntimeLoss(PolicyCase):
    def setUp(self) -> None:
        super().setUp()
        # The one request every crash and retry of a test uses: its evidence references are read once, so a Run
        # summary a crashed Run wrote (G2 not_authorized, G4 human_wait) never turns the retry into another request.
        self.first = self.request()

    def lose_runtime(self) -> None:
        rmtree(self.root / ".workline" / "runtime")

    def canonical(self) -> tuple[Any, ...]:
        review = self.review_store
        return (review.run_ids(), review.policy_change_ids(), tuple(self.policy_receipts()),
                tuple(found.consumption_id for found in self.policy_consumptions()), self.commit_of(),
                self.profile_bytes())

    def snapshot_candidate(self, run_id: str) -> dict[str, Any]:
        review = self.review_store
        return review.read_candidate_snapshot(review.gate_chain(run_id).generations[0].candidate_hash).material

    def assert_recovered(self, run_id: str, review: project_policy.PolicyReview | None = None
                         ) -> project_policy.PolicyChangeResult:
        candidate = self.snapshot_candidate(run_id)
        receipts = self.policy_receipts()
        result = self.applied(self.first, review)
        self.assertEqual((run_id, candidate["policy_change_id"]), (result.review_run_id, result.policy_change_id),
                         "the earlier Run is resumed with its canonical IDs, never replaced")
        self.assertEqual([run_id], self.policy_runs())
        self.assertEqual((candidate["policy_change_id"],), self.review_store.policy_change_ids())
        self.assertEqual(1, len(self.policy_receipts()))
        if receipts:
            self.assertEqual(receipts, self.policy_receipts(), "the sealed Receipt is the one consumed")
        self.assertEqual([result.consumption_id], [found.consumption_id for found in self.policy_consumptions()])
        self.assertEqual([], self.policy_pending())
        self.assertEqual([], self.problems())
        return result

    def assert_refused(self, reason: str, *requests: policy.PolicyChangeRequest) -> None:
        before = self.canonical()
        for request in requests:
            with self.subTest(request=request.after_setting), self.assertRaises(ReconcileRequired) as raised:
                self.change(request)
            self.assertEqual(reason, raised.exception.reason)
            self.assertEqual(before, self.canonical(), "nothing is reserved canonically, written or committed")
            self.assertEqual([], self.policy_pending(), "the refused call leaves no pending mutation")

    def crashed_at(self, step: str, review: project_policy.PolicyReview | None = None) -> str:
        with crash_at(project_policy, step), self.assertRaises(Crash):
            self.change(self.first, review)
        (run_id,) = self.policy_runs()
        return run_id

    def three_reviewers(self) -> project_policy.PolicyReview:
        return policy_review(Discovery(), Discovery(viewpoint="safety", identity="discovery-two"),
                             Discovery(viewpoint="scope", identity="discovery-three"))


class LocalRecoveryTests(_RuntimeLoss):
    template = "local"

    def test_after_g1_the_one_recoverable_run_resumes_with_its_ids(self) -> None:
        run_id = self.crashed_at("_launch_discovery")
        self.lose_runtime()
        self.assert_recovered(run_id)

    def test_after_g2(self) -> None:
        run_id = self.crashed_at("_accept_adjudication")
        self.assertEqual(2, self.review_store.gate_chain(run_id).latest.generation)
        self.lose_runtime()
        self.assert_recovered(run_id)

    def test_after_g3(self) -> None:
        run_id = self.crashed_at("_adjudicate")
        self.assertEqual(3, self.review_store.gate_chain(run_id).latest.generation)
        self.lose_runtime()
        self.assert_recovered(run_id)

    def test_after_g4(self) -> None:
        run_id = self.crashed_at("_seal")
        self.assertEqual(4, self.review_store.gate_chain(run_id).latest.generation)
        self.lose_runtime()
        self.assert_recovered(run_id)

    def test_after_the_receipt_the_sealed_receipt_is_the_one_consumed(self) -> None:
        run_id = self.crashed_at("_persist")
        self.assertEqual(1, len(self.policy_receipts()))
        self.lose_runtime()
        self.assert_recovered(run_id)

    def test_a_crash_right_after_the_binding_resumes_that_binding(self) -> None:
        """R7: the identical binding a crashed call saved is resumed, never a reservation conflict."""
        run_id = self.crashed_at("_launch_discovery")
        self.lose_runtime()
        with crash_at(project_policy, "bind_policy_recovery", after=True), self.assertRaises(Crash):
            self.change(self.first)
        (pending,) = self.policy_pending()
        self.assertIn(run_id, pending["reserved_ids"].values())
        self.assert_recovered(run_id)

    def test_after_km_the_consumed_run_is_settled_and_nothing_is_duplicated(self) -> None:
        with after_effect("git_commit", project_policy.STAGE_KM), self.assertRaises(Interrupted):
            self.change(self.first)
        self.assertEqual(1, len(self.policy_consumptions()))
        self.lose_runtime()
        before = self.canonical()
        # settled: the same request is a fresh freeze against the moved Profile (two reviewers now), changing nothing
        with self.assertRaises(StopError) as raised:
            self.change(self.first, two_reviewers())
        self.assertEqual(policy.CODE_DIRECTION_INVALID, raised.exception.code)
        self.assertEqual(before, self.canonical())
        self.assertEqual([], self.policy_pending())

    def test_a_not_authorized_run_is_set_aside_and_the_request_is_a_new_run(self) -> None:
        declined = self.crashed_at("_finish", policy_review(Discovery(status="declined")))
        self.assertEqual(2, self.review_store.gate_chain(declined).latest.generation)
        self.lose_runtime()
        result = self.applied(self.first)
        self.assertNotEqual(declined, result.review_run_id)
        self.assertEqual(sorted([declined, result.review_run_id]), sorted(self.policy_runs()))
        self.assertEqual([], self.problems())


class _HumanWait(_RuntimeLoss):
    """CP ruling R8: a Policy Review at canonical G4 HUMAN_WAIT stays the same canonical HUMAN_WAIT Run."""

    def waiting(self, *, crash: bool) -> str:
        """Item 1: a HUMAN adjudication reaches G4 HUMAN_WAIT with no Receipt - completed by its owner, or crashed in
        the window "G4 committed, before ``_finish``"."""
        review = policy_review(Discovery(claim("human", "MID")))
        if crash:
            run_id = self.crashed_at("_finish", review)
            self.assertEqual(1, len(self.policy_pending()), "the owner was lost before it finished")
        else:
            result = self.change(self.first, review)
            self.assertEqual(project_policy.STATUS_HUMAN_WAIT, result.status, result.detail)
            run_id = result.review_run_id
            self.assertEqual([], self.policy_pending(), "the owner completed its mutation at HUMAN_WAIT")
        chain = self.review_store.gate_chain(run_id)
        self.assertEqual(4, chain.latest.generation)
        self.assertEqual(records.HUMAN_WAIT, self.review_store.read_adjudication(run_id).outcome)
        self.assertEqual([None] * 4, [generation.receipt_id for generation in chain.generations])
        self.assertEqual([], self.policy_receipts(), "no Receipt")
        self.assertEqual(history.DISPOSITION_HUMAN_WAIT,
                         self.review_store.read_history(paths.HISTORY_RUNS, run_id).durable_disposition)
        return run_id

    def run_records(self, run_id: str) -> dict[str, bytes | None]:
        """Every record the Run's canonical chain names - gates, snapshot, TaskInputs, reports, adjudication, its P5
        Finding and Run summaries - byte for byte."""
        review = self.review_store
        found = recovery.p4_record_paths(review, run_id, review.gate_chain(run_id))
        return {relative: review.read_bytes(relative) for relative in sorted(set(found))}

    def named_aside(self) -> set[str]:
        """Every Run that a generation 1 of any Run names in the ``set_aside_runs`` of its TaskInputs."""
        review = self.review_store
        found: set[str] = set()
        for run_id in review.run_ids():
            for task in review.gate_chain(run_id).generations[0].accepted_tasks:
                envelope = review.read_task_input(str(task["task_id"])).request_envelope
                found |= {str(item["review_run_id"]) for item in envelope.get("set_aside_runs") or []}
        return found

    def assert_still_waiting(self, run_id: str, *, calls: int = 3) -> None:
        """Items 3-8: each call of the same request (repeated: stable) returns the same canonical HUMAN_WAIT Run."""
        candidate = self.snapshot_candidate(run_id)
        before = (self.canonical(), self.policy_runs(), self.run_records(run_id))
        for call in range(calls):
            actor, adjudicator = Discovery(), Adjudicator()
            with self.subTest(call=call):
                result = self.change(self.first, policy_review(actor, adjudicator=adjudicator))
                self.assertEqual(project_policy.STATUS_HUMAN_WAIT, result.status, result.detail)
                self.assertEqual((run_id, candidate["policy_change_id"]),
                                 (result.review_run_id, result.policy_change_id),
                                 "the same canonical Run, policy_change_id and review_run_id")
                self.assertEqual((None,) * 6, (result.receipt_id, result.consumption_id, result.profile_version,
                                               result.profile_digest, result.policy_commit, result.metadata_commit))
                self.assertEqual(([], []), (actor.tasks, adjudicator.tasks),
                                 "nothing is launched: no guessed Human answer, no new review")
                self.assertEqual(before, (self.canonical(), self.policy_runs(), self.run_records(run_id)),
                                 "no new Run, Receipt, change record, Profile, Consumption or commit; the waiting "
                                 "Run's records are unchanged byte for byte")
                self.assertNotIn(run_id, self.named_aside(), "no set-aside is written")
                self.assertEqual(([], []), (self.commits_with(KP_SUBJECT), self.commits_with(KM_SUBJECT)))
                self.assertEqual([], self.policy_pending(), "no pending mutation is left behind")
        self.assertEqual([], self.problems())


class HumanWaitRecoveryTests(_HumanWait):
    template = "local"

    def test_after_runtime_loss_the_same_request_rediscovers_the_same_human_wait_run(self) -> None:
        """Items 1-8: the owner completed at HUMAN_WAIT, then its runtime state is deleted."""
        waiting = self.waiting(crash=False)
        self.lose_runtime()
        self.assert_still_waiting(waiting)

    def test_an_owner_intact_retry_after_a_completed_human_wait_is_the_same_run(self) -> None:
        """Item 9: no runtime loss - the owner's completed mutation never turns the retry into a new Run."""
        waiting = self.waiting(crash=False)
        self.assert_still_waiting(waiting)

    def test_a_crash_between_g4_and_finish_recovers_the_same_human_wait_run(self) -> None:
        """Item 10: G4 committed and the owner lost before ``_finish`` completed it."""
        waiting = self.waiting(crash=True)
        self.lose_runtime()
        self.assert_still_waiting(waiting)

    def test_a_blocking_g4_run_keeps_its_terminal_semantics(self) -> None:
        """Item 11: a G4 that settles REPAIR_REQUIRED is terminal ``not_authorized``, never a recoverable wait: the
        same request is a new Run with new IDs, and the old Run's records are unchanged."""
        blocked = self.crashed_at("_finish", policy_review(Discovery(claim("problem"))))
        self.assertEqual(records.REPAIR_REQUIRED, self.review_store.read_adjudication(blocked).outcome)
        old_change = self.snapshot_candidate(blocked)["policy_change_id"]
        old = self.run_records(blocked)
        self.lose_runtime()
        result = self.applied(self.first)
        self.assertNotEqual(blocked, result.review_run_id)
        self.assertNotEqual(old_change, result.policy_change_id)
        self.assertEqual(sorted([blocked, result.review_run_id]), sorted(self.policy_runs()))
        self.assertEqual(old, self.run_records(blocked), "the terminal Run's chain is unchanged byte for byte")
        self.assertEqual([], self.problems())

    def test_a_different_request_is_its_own_run_and_never_names_the_waiting_one(self) -> None:
        """Item 12: a changed proposal is its own operation identity, Candidate and Run; it neither names nor sets
        aside the HUMAN_WAIT Run, which stays canonical HUMAN_WAIT for its own request."""
        waiting = self.waiting(crash=False)
        kept = self.run_records(waiting)
        other = self.applied(change_request(self.first.evidence, after=3))
        self.assertNotEqual(waiting, other.review_run_id)
        self.assertNotEqual(self.snapshot_candidate(waiting)["policy_change_id"], other.policy_change_id)
        self.assertNotIn(waiting, self.named_aside())
        self.assertEqual(kept, self.run_records(waiting))
        self.assertEqual(sorted([waiting, other.review_run_id]), sorted(self.policy_runs()))

    def test_a_moved_before_state_still_returns_the_same_human_wait_run(self) -> None:
        """Item 13 (CANDIDATE §6d: HUMAN_WAIT for the unchanged canonical Run): another request applied and moved the
        Profile since the waiting Run froze. Row f (currency / before-state) does not apply to a G4 HUMAN_WAIT Run -
        as in P4 planning and Work recovery - since it authorizes, launches and writes nothing: the same request gets
        the same human_wait, with nothing written, set aside or pending."""
        waiting = self.waiting(crash=False)
        moved = self.applied(change_request(self.first.evidence, after=3))
        self.assertNotEqual(self.snapshot_candidate(waiting)["before_profile"]["digest"], self.state().profile_digest)
        self.lose_runtime()
        self.assert_still_waiting(waiting)
        self.assertEqual(moved.profile_digest, self.state().profile_digest, "the other change stands")


class RemoteHumanWaitTests(_HumanWait):
    template = "remote"

    def test_human_wait_recovery_publishes_nothing(self) -> None:
        """Items 1-8 and 10 with a remote: nothing is pushed."""
        waiting = self.waiting(crash=True)
        pushes, published = self.pushes(), self.remote_main()
        self.lose_runtime()
        self.assert_still_waiting(waiting, calls=2)
        self.assertEqual(pushes, self.pushes(), "no push")
        self.assertEqual(published, self.remote_main())


class StaleRecoveryTests(_RuntimeLoss):
    """R1: a recovered Run whose before-state moved never strands a pending mutation."""

    template = "local"

    def stale_then_others_run(self, step: str) -> None:
        stale = self.crashed_at(step)
        self.lose_runtime()
        other = self.applied(self.request(after=3))  # another request moves the Profile
        before = self.canonical()
        with self.assertRaises(StopError) as raised:
            self.change(self.first)  # the stale request, with its usual reviewers
        self.assertEqual(policy.CODE_BEFORE_STATE_CONFLICT, raised.exception.code)
        self.assertEqual(before, self.canonical())
        self.assertEqual([], self.policy_pending(), "no pending mutation holds the Profile scope")
        self.assertIn(stale, self.policy_runs(), "the stale Run stays canonical evidence")
        # every later Policy Change still runs (reviewed under the pre-change policy: required_slots 3)
        third = self.applied(self.request(after=4, supersedes=(other.policy_change_id,), overlap=policy.OVERLAP_KNOWN),
                             self.three_reviewers())
        self.assertEqual(2, self.review_store.read_profile().profile_version, "the stale request never applied")
        self.assertNotEqual(stale, third.review_run_id)

    def test_stale_at_g1(self) -> None:
        self.stale_then_others_run("_launch_discovery")

    def test_stale_at_g5(self) -> None:
        self.stale_then_others_run("_persist")


class OwnerIntactStaleTests(_RuntimeLoss):
    """N5: with the owner record intact, a before-state that moved releases the effect-free owner mutation."""

    template = "local"

    def commit_foreign_profile(self) -> None:
        from test_project_policy_change import foreign_profile

        target = self.root / paths.POLICY_PROFILE_REL
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(foreign_profile(3).text().encode("utf-8"))
        self.git("add", "--", paths.POLICY_PROFILE_REL)
        self.git("commit", "-q", "-m", "docs: a person edits the Project Profile")

    def test_before_generation_1_the_release_leaves_nothing_pending(self) -> None:
        """No Run is canonical yet: the release leaves nothing pending and nothing names the released IDs."""
        with crash_at(project_policy, "_accept"), self.assertRaises(Crash):
            self.change(self.first)
        self.assertEqual(1, len(self.policy_pending()))
        self.commit_foreign_profile()
        with self.assertRaises(StopError) as raised:
            self.change(self.first)
        self.assertEqual(policy.CODE_BEFORE_STATE_CONFLICT, raised.exception.code)
        self.assertEqual([], self.policy_pending(), "the effect-free owner mutation is released")
        self.assertEqual([], self.policy_runs())

    def test_at_generation_1_the_release_leaves_nothing_pending_and_the_run_stays_refused(self) -> None:
        """The Run is canonical: the owner's own step releases, then canonical discovery's re-proof refuses."""
        run_id = self.crashed_at("_launch_discovery")
        self.commit_foreign_profile()
        for call in range(2):
            with self.subTest(call=call), self.assertRaises(StopError) as raised:
                self.change(self.first)
            self.assertEqual(policy.CODE_BEFORE_STATE_CONFLICT, raised.exception.code)
            self.assertEqual([], self.policy_pending())
            self.assertEqual([run_id], self.policy_runs())


class StrandedKpTests(_RuntimeLoss):
    template = "local"

    def stranded(self) -> str:
        with after_effect("git_commit", project_policy.STAGE_KP), self.assertRaises(Interrupted):
            self.change(self.first)
        (kp,) = self.commits_with(KP_SUBJECT)
        self.lose_runtime()
        return kp

    def test_after_kp_nothing_is_inferred_from_git_history(self) -> None:
        kp = self.stranded()
        self.assert_refused(policy.REASON_RUN_UNRECOVERED, self.request(), self.request(after=3))
        self.assertEqual([kp], self.commits_with(KP_SUBJECT), "the Kp is never re-made or adopted")
        self.assertEqual([], self.policy_consumptions())

    def test_a_reverted_stranded_kp_is_never_re_applied(self) -> None:
        """R2: the revert removes the record from the tree, not from HEAD's history: the Run stays unrecoverable."""
        kp = self.stranded()
        (change_id,) = self.review_store.policy_change_ids()
        change_path = paths.policy_change_rel(change_id)
        self.git("revert", "--no-edit", kp)
        self.assertIsNone(self.profile_bytes())
        self.assert_refused(policy.REASON_RUN_UNRECOVERED, self.first)
        self.assertEqual({change_path: [kp]}, {path: found for path, found in
                                               publication.policy_change_adders(self.root, self.commit_of()).items()},
                         "the change record is never added twice")
        # the revert reconciled it for every other request, and nothing poisons the barrier
        other = self.applied(self.request(after=3))
        self.assertNotEqual(change_id, other.policy_change_id)
        self.assertIsNone(publication.barrier_problem(self.root, self.commit_of()))

    def test_a_consumption_naming_the_change_under_another_receipt_does_not_consume_it(self) -> None:
        """N4: only the Policy Consumption of the change's own Receipt consumes it. A hand-made one naming the change
        id under another Receipt clears neither the Project-wide stranded check nor row b (at a596fad it cleared
        both, keyed on the change id alone)."""
        kp = self.stranded()
        (change_id,) = self.review_store.policy_change_ids()
        change = self.review_store.read_policy_change(change_id)
        forged = records.PolicyConsumption(
            consumption_id="rcs_01ARZ3NDEKTSV4RRFFQ69G5FTV", receipt_id="rcp_01ARZ3NDEKTSV4RRFFQ69G5FTV",
            review_run_id=str(change["review_run_id"]), review_generation=5, review_kind=policy.REVIEW_KIND,
            authorized_candidate_hash=str(change["candidate_hash"]),
            operation_identity=policy.operation_identity(policy.request_digest(policy.request_record(self.first))),
            operation_mutation_id="mut_01ARZ3NDEKTSV4RRFFQ69G5FTV", target_identity=policy.TARGET_IDENTITY,
            persisted_policy={
                "contract": records.PERSISTED_POLICY_CONTRACT, "policy_change_id": change_id,
                "before_profile_version": None, "before_profile_digest": None, "after_profile_version": 1,
                "after_profile_digest": change["after_profile_digest"],
                "global_baseline_digest": change["global_baseline_digest"], "normalized_projection_hash": "0" * 64,
                "policy_commit": kp, "policy_parent": self.parents(kp)[0], "branch": "refs/heads/main",
                "policy_delta_digest": "0" * 64, "adapter_identity": records.POLICY_ADAPTER_IDENTITY,
                "loader_identity": "0" * 64,
            },
        )
        relative = paths.consumption_rel(forged.consumption_id)
        (self.root / relative).write_bytes(serialize.canonical_bytes(forged.to_record()))
        self.git("add", "--", relative)
        self.git("commit", "-q", "-m", "docs: a hand-made Consumption naming the change under another Receipt")
        self.assert_refused(policy.REASON_RUN_UNRECOVERED, self.first, self.request(after=3))
        self.assertEqual([kp], self.commits_with(KP_SUBJECT))


class MalformedTests(_RuntimeLoss):
    """R3 / R6 / R9: discovery itself refuses a Run it cannot show whole - before any binding, nothing pending."""

    template = "local"

    def assert_incomplete(self) -> None:
        before = self.canonical()
        with self.assertRaises(ReconcileRequired) as raised:
            self.change(self.first)
        self.assertEqual("review_recovery_incomplete", raised.exception.reason)
        self.assertEqual(before, self.canonical())
        self.assertEqual([], self.policy_pending())

    def test_an_uncommitted_generation_is_incomplete(self) -> None:
        with before_effect("git_commit", project_policy.STAGE_GENERATION_COMMIT), self.assertRaises(Interrupted):
            self.change(self.first)
        (run_id,) = self.policy_runs()
        self.assertIn(paths.gate_rel(run_id, 1), "\n".join(self.dirty()))
        self.lose_runtime()
        self.assert_incomplete()

    def test_a_sealed_run_whose_task_provenance_fails_is_incomplete(self) -> None:
        run_id = self.crashed_at("_persist")
        self.lose_runtime()
        task_id = str(self.review_store.gate_chain(run_id).generations[0].accepted_tasks[0]["task_id"])
        relative = paths.task_input_rel(task_id)
        record = serialize.parse((self.root / relative).read_text(encoding="utf-8"), "task input")
        record["reviewer_version"] = "9"
        (self.root / relative).write_bytes(serialize.canonical_bytes(record))
        self.git("add", "--", relative)
        self.git("commit", "-q", "-m", "docs: a person edits a task input")
        self.assert_incomplete()
        self.assertEqual((), self.review_store.policy_change_ids(), "an inconsistent Run never authorizes a change")

    def test_a_once_committed_inconsistent_twin_does_not_reconstruct(self) -> None:
        """N1 (row e): a matching Run whose records are whole, committed once and unchanged - so clean persistence
        holds - and whose accepted descriptor names another reviewer version than its untouched TaskInput: only the
        reconstruction row refuses it (without row e both twins would be recoverable: ambiguous)."""
        run_id = self.crashed_at("_launch_discovery")
        self.lose_runtime()
        record = serialize.parse((self.root / paths.gate_rel(run_id, 1)).read_text(encoding="utf-8"), "gate")
        twin = "rr_01ARZ3NDEKTSV4RRFFQ69G5FTV"
        record["review_run_id"] = twin
        record["accepted_tasks"][0]["reviewer_version"] = "9"
        target = self.root / paths.gate_rel(twin, 1)
        target.parent.mkdir(parents=True)
        target.write_bytes(serialize.canonical_bytes(record))
        self.git("add", "--", paths.gate_rel(twin, 1))
        self.git("commit", "-q", "-m", "docs: a hand-made Policy Review twin whose descriptor is not its TaskInput's")
        before = self.canonical()
        with self.assertRaises(ReconcileRequired) as raised:
            self.change(self.first)
        self.assertEqual("review_recovery_incomplete", raised.exception.reason)
        self.assertIn(f"Policy Review Run {twin} does not reconstruct", str(raised.exception))
        self.assertIn("reviewer_version", str(raised.exception))
        self.assertEqual(before, self.canonical())
        self.assertEqual([], self.policy_pending())

    def test_a_policy_kind_g1_with_no_task_is_incomplete(self) -> None:
        run_id = self.crashed_at("_launch_discovery")
        self.lose_runtime()
        record = serialize.parse((self.root / paths.gate_rel(run_id, 1)).read_text(encoding="utf-8"), "gate")
        twin = "rr_01ARZ3NDEKTSV4RRFFQ69G5FTX"
        record.update(review_run_id=twin, accepted_tasks=[])
        target = self.root / paths.gate_rel(twin, 1)
        target.parent.mkdir(parents=True)
        target.write_bytes(serialize.canonical_bytes(record))
        self.git("add", "--", paths.gate_rel(twin, 1))
        self.git("commit", "-q", "-m", "docs: a hand-made Policy Review generation 1 with no task")
        self.assert_incomplete()

    def test_two_recoverable_runs_of_one_request_are_ambiguous(self) -> None:
        run_id = self.crashed_at("_launch_discovery")
        self.lose_runtime()
        twin = "rr_01ARZ3NDEKTSV4RRFFQ69G5FTW"
        record = serialize.parse((self.root / paths.gate_rel(run_id, 1)).read_text(encoding="utf-8"), "gate")
        record["review_run_id"] = twin
        target = self.root / paths.gate_rel(twin, 1)
        target.parent.mkdir(parents=True)
        target.write_bytes(serialize.canonical_bytes(record))
        self.git("add", "--", paths.gate_rel(twin, 1))
        self.git("commit", "-q", "-m", "docs: a hand-made twin Run")
        before = self.canonical()
        with self.assertRaises(ReconcileRequired) as raised:
            self.change(self.first)
        self.assertEqual("review_recovery_ambiguous", raised.exception.reason)
        self.assertEqual(before, self.canonical(), "no Run is chosen by age, ID or position, and nothing is written")
        self.assertEqual([], self.policy_pending())


class NoPolicyHistoryTests(_RuntimeLoss):
    """N3: a Project with no policy history never reads its Consumptions' history for a Policy Change."""

    template = "local"

    def test_an_unreadable_unrelated_consumption_in_history_refuses_no_policy_change(self) -> None:
        relative = paths.consumption_rel("rcs_01ARZ3NDEKTSV4RRFFQ69G5FTV")
        (self.root / relative).write_bytes(b"not: a consumption\n")
        self.git("add", "--", relative)
        self.git("commit", "-q", "-m", "docs: a person commits a malformed Consumption")
        self.git("rm", "-q", "--", relative)
        self.git("commit", "-q", "-m", "docs: and removes it again")
        result = self.applied(self.first)
        self.assertEqual([result.review_run_id], self.policy_runs())
        self.assertEqual([], self.policy_pending())


class RemoteRuntimeLossTests(_RuntimeLoss):
    template = "remote"

    def test_after_the_receipt_recovery_publishes_exactly_kp_and_km(self) -> None:
        run_id = self.crashed_at("_persist")
        pushes = self.pushes()
        self.lose_runtime()
        result = self.assert_recovered(run_id)
        published = self.pushes()[len(pushes):]
        self.assertEqual([str(result.policy_commit), str(result.metadata_commit)], [item[1] for item in published])
        self.assert_fast_forward_pushes()

    def test_after_kp_nothing_is_published_by_the_refused_retry(self) -> None:
        with after_effect("git_commit", project_policy.STAGE_KP), self.assertRaises(Interrupted):
            self.change(self.first)
        pushes = self.pushes()
        self.lose_runtime()
        self.assert_refused(policy.REASON_RUN_UNRECOVERED, self.first)
        self.assertEqual(pushes, self.pushes(), "no publication beside the unrecovered policy commit")


class BarrierTests(_RuntimeLoss):
    """Another operation's push over a policy commit (Kp) left by a lost owner record."""

    template = "remote"

    def stranded_kp(self) -> tuple[str, str]:
        other = rm.create_roadmap(self.store, plan("Other Roadmap")).roadmap_id
        with after_effect("git_commit", project_policy.STAGE_KP), self.assertRaises(Interrupted):
            self.change()
        (kp,) = self.commits_with(KP_SUBJECT)
        self.lose_runtime()
        return kp, other

    def test_a_push_over_a_proven_policy_commit_passes(self) -> None:
        """R5 items 2-3 (case C): the owner's runtime record is lost right after Kp, no Consumption or Km of it exists
        anywhere, and an unrelated operation's push publishes the proven Kp."""
        kp, other = self.stranded_kp()
        self.assertFalse((self.root / ".workline" / "runtime").exists(), "the owner's runtime state is lost")
        self.assertEqual([], self.policy_consumptions(), "no Policy Consumption")
        self.assertEqual([], self.commits_with(KM_SUBJECT), "no Km")
        self.assertIsNone(publication.barrier_problem(self.root, kp))
        held = rm.hold_roadmap(self.store, other)
        self.assertEqual(held.head, self.remote_main())
        self.assertTrue(gitcmd.descends_from(self.root, held.head, kp))
        self.assertEqual([], self.commits_with(KM_SUBJECT, held.head), "the published history holds no Km")
        self.assertEqual([], self.policy_consumptions())

    def test_a_push_over_an_unproven_km_is_refused(self) -> None:
        """R5 item 5 (case D): a Km needs its own proof - another operation's push over a forged metadata commit is
        refused, and the real Km beside it is proven."""
        other = rm.create_roadmap(self.store, plan("Other Roadmap")).roadmap_id
        with after_effect("git_commit", project_policy.STAGE_KM), self.assertRaises(Interrupted):
            self.change()
        (kp,) = self.commits_with(KP_SUBJECT)
        (km,) = self.commits_with(KM_SUBJECT)
        self.lose_runtime()
        self.assertIsNone(publication.barrier_problem(self.root, km), "the real Km is proven")
        published = self.remote_main()
        self.assertEqual(kp, published, "the owner published exactly Kp before it was lost")
        (consumption,) = self.policy_consumptions()
        consumption_path = paths.consumption_rel(consumption.consumption_id)
        summary_path = paths.history_run_rel(consumption.review_run_id)
        record = consumption.to_record()
        record["persisted_policy"] = dict(record["persisted_policy"], policy_parent=kp)
        forged = plumb_commit(self.store, kp, {consumption_path: serialize.canonical_bytes(record),
                                               summary_path: self.blob(km, summary_path)}, "a forged metadata commit")
        move_branch(self.store, forged)
        self.assertIn("PK8 fails", publication.barrier_problem(self.root, forged))
        with self.assertRaises(StopError) as raised:
            rm.hold_roadmap(self.store, other)
        self.assertEqual("review_publication_barrier", raised.exception.code)
        self.assertEqual(published, self.remote_main(), "the destination keeps what it had")

    def test_a_push_over_an_unproven_policy_commit_is_refused(self) -> None:
        kp, other = self.stranded_kp()
        published = self.remote_main()
        parent = self.parents(kp)[0]
        change_path = next(path for path in self.delta(kp) if path.startswith(paths.POLICY_DIR + "/changes/"))
        # the same final tree, the change record and the Profile split across two commits: PK2 cannot hold
        first = plumb_commit(self.store, parent, {change_path: self.blob(kp, change_path)}, "a split change record")
        second = plumb_commit(self.store, first, {paths.POLICY_PROFILE_REL: self.blob(kp, paths.POLICY_PROFILE_REL)},
                              "a split Profile")
        move_branch(self.store, second)
        self.assertIn("PK2 fails", publication.barrier_problem(self.root, second))
        with self.assertRaises(StopError) as raised:
            rm.hold_roadmap(self.store, other)
        self.assertEqual("review_publication_barrier", raised.exception.code)
        self.assertEqual(published, self.remote_main(), "the destination keeps what it had")


class BarrierEquivalenceTests(PolicyCase):
    """R5 item 4 (case A): a history with no policy change is decided exactly as main decides it.

    The reference is the barrier with its P6 block neutralized (``policy_change_adders`` answering ``{}`` without a
    read): ``publication.py`` adds to main's barrier only that block, after the unchanged fast path and planning
    proofs. Against it the real barrier gives the byte-equal answer, makes every one of the reference's Git reads in
    the same order, and adds at most one: the policy change directory's add-history read, which lists nothing. No
    committed policy proof runs. (Legacy-only histories: ``test_review_planning_publication.LegacyOnlyTests`` and
    ``test_review_planning_committed_proof.LegacyOnlyPushTests`` pin main's one fast-path read, unchanged.)
    """

    template = "local"

    def recorded(self, commit: str, *, neutral: bool) -> tuple[str | None, list[tuple[str, ...]], list[Any]]:
        calls: list[tuple[str, ...]] = []
        listed: list[Any] = []
        real_run, real_bytes, real_adders = gitcmd.run_git, gitcmd.run_git_bytes, publication.policy_change_adders

        def run(repo: Any, *args: str, **kwargs: Any) -> Any:
            calls.append(tuple(args))
            return real_run(repo, *args, **kwargs)

        def run_bytes(repo: Any, *args: str, **kwargs: Any) -> Any:
            calls.append(tuple(args))
            return real_bytes(repo, *args, **kwargs)

        def adders(repo: Any, at: str) -> dict[str, list[str]]:
            found = {} if neutral else real_adders(repo, at)
            listed.append(found)
            return found

        gitcmd.forget_object_answers()
        with mock.patch.object(gitcmd, "run_git", run), mock.patch.object(gitcmd, "run_git_bytes", run_bytes), \
                mock.patch.object(publication, "policy_change_adders", adders), \
                mock.patch.object(publication, "committed_policy_proof", side_effect=AssertionError("a policy proof ran")):
            problem = publication.barrier_problem(self.root, commit)
        return problem, calls, listed

    def extra_reads(self, commit: str) -> tuple[str | None, list[tuple[str, ...]], list[Any]]:
        publication.barrier_problem(self.root, commit)  # the once-per-process Git version read, outside the records
        reference, reference_calls, _ = self.recorded(commit, neutral=True)
        found, calls, listed = self.recorded(commit, neutral=False)
        self.assertEqual(reference, found, "main's decision, byte for byte")
        self.assertEqual(reference_calls, calls[:len(reference_calls)], "main's reads, in main's order")
        return found, calls[len(reference_calls):], listed

    def test_a_proven_planning_only_history_adds_one_empty_policy_read(self) -> None:
        head = self.commit_of()
        self.assertEqual({}, publication.policy_change_adders(self.root, head))
        found, extra, listed = self.extra_reads(head)
        self.assertIsNone(found)
        directory = f"{paths.POLICY_DIR}/{paths.POLICY_CHANGES}"
        self.assertEqual([("log", "--full-history", "--no-renames", "--diff-merges=combined", "--diff-filter=A",
                           "--name-only", "-z", "--format=%x01%H%x02", head, "--", directory)], extra)
        self.assertEqual([{}], listed)

    def test_a_refused_planning_only_history_adds_no_read(self) -> None:
        (consumption, *_) = [found for found in self.review_store.consumptions()
                             if isinstance(found, records.PlanningConsumption)]
        broken = plumb_commit(self.store, self.commit_of(), {paths.consumption_rel(consumption.consumption_id): None},
                              "a person removes a planning Consumption")
        found, extra, listed = self.extra_reads(broken)
        self.assertRegex(str(found), r"CP\d+ fails")
        self.assertEqual(([], []), (extra, listed), "the planning refusal comes before the P6 block")


class CommittedPolicyProofTests(PolicyCase):
    """PK1-PK9 each refuse their forgery; the proven Kp / Km pass (read from committed objects only)."""

    template = "profiled"

    def setUp(self) -> None:
        super().setUp()
        (self.change_id,) = self.review_store.policy_change_ids()
        self.change_path = paths.policy_change_rel(self.change_id)
        (self.kp,) = self.commits_with(KP_SUBJECT)
        (self.km,) = self.commits_with(KM_SUBJECT)
        self.parent = self.parents(self.kp)[0]
        self.record = self.review_store.read_policy_change(self.change_id)

    def item(self, commit: str) -> str | None:
        failed = publication.committed_policy_proof(self.root, commit, self.change_path)
        return None if failed is None else failed[0]

    def test_the_proven_kp_and_km_pass(self) -> None:
        self.assertIsNone(self.item(self.kp))
        self.assertIsNone(self.item(self.km))
        self.assertIsNone(publication.barrier_problem(self.root, self.km))

    def test_pk1_a_change_record_added_twice(self) -> None:
        removed = plumb_commit(self.store, self.km, {self.change_path: None}, "a revert of the change record")
        again = plumb_commit(self.store, removed, {self.change_path: self.blob(self.kp, self.change_path)}, "re-added")
        self.assertEqual("PK1", self.item(again))
        self.assertIn("PK1 fails", publication.barrier_problem(self.root, again))

    def test_pk3_a_change_record_that_is_not_its_candidates(self) -> None:
        record = dict(self.record, success_criteria="a different success criterion than the reviewed one")
        forged = plumb_commit(self.store, self.parent, {
            self.change_path: serialize.canonical_bytes(record),
            paths.POLICY_PROFILE_REL: self.blob(self.kp, paths.POLICY_PROFILE_REL)}, "a forged change record")
        self.assertEqual("PK3", self.item(forged))

    def test_pk4_a_profile_that_is_not_the_reviewed_after_profile(self) -> None:
        after = self.review_store.read_profile().to_record()
        after["active_experiment_refs"] = []
        forged = plumb_commit(self.store, self.parent, {
            self.change_path: self.blob(self.kp, self.change_path),
            paths.POLICY_PROFILE_REL: serialize.canonical_bytes(after)}, "a forged Profile")
        self.assertEqual("PK4", self.item(forged))

    def test_pk5_a_parent_without_the_reviewed_before_profile(self) -> None:
        second = self.applied(self.request(after=3, supersedes=(self.change_id,), overlap=policy.OVERLAP_KNOWN),
                              two_reviewers())
        change_path = paths.policy_change_rel(second.policy_change_id)
        kp = str(second.policy_commit)
        moved = self.review_store.read_profile().to_record()
        moved["active_experiment_refs"] = []
        before = plumb_commit(self.store, self.parents(kp)[0],
                              {paths.POLICY_PROFILE_REL: serialize.canonical_bytes(moved)}, "a moved before Profile")
        forged = plumb_commit(self.store, before, {
            change_path: self.blob(kp, change_path),
            paths.POLICY_PROFILE_REL: self.blob(kp, paths.POLICY_PROFILE_REL)}, "a Kp on another before Profile")
        self.assertIsNone(publication.committed_policy_proof(self.root, kp, change_path))
        self.assertEqual("PK5", publication.committed_policy_proof(self.root, forged, change_path)[0])

    def test_pk6_a_parent_without_the_sealed_run(self) -> None:
        run_id = self.record["review_run_id"]
        (fifth,) = [commit for commit in self.commits_with(GENERATION_SUBJECT)
                    if self.subject(commit) == f"{GENERATION_SUBJECT}5 of {run_id}"]
        forged = plumb_commit(self.store, self.parents(fifth)[0], {
            self.change_path: self.blob(self.kp, self.change_path),
            paths.POLICY_PROFILE_REL: self.blob(self.kp, paths.POLICY_PROFILE_REL)}, "a Kp before the seal")
        self.assertEqual("PK6", self.item(forged))

    def test_pk6_a_receipt_that_is_not_its_seals(self) -> None:
        """N1: the parent's Receipt differs from generation 5 in one bound field; only PK6's Receipt binding refuses
        the Kp on it (round 1's PK6 proved the Run sealed with that Receipt ID, and the Kp alone passed)."""
        receipt_id = str(self.record["receipt_id"])
        receipt = self.review_store.read_receipt(receipt_id).to_record()
        receipt["coverage_hash"] = "f" * 64
        edited = plumb_commit(self.store, self.parent, {paths.receipt_rel(receipt_id): serialize.canonical_bytes(receipt)},
                              "a person edits the Receipt")
        forged = plumb_commit(self.store, edited, {
            self.change_path: self.blob(self.kp, self.change_path),
            paths.POLICY_PROFILE_REL: self.blob(self.kp, paths.POLICY_PROFILE_REL)}, "a Kp over the edited Receipt")
        item, detail = publication.committed_policy_proof(self.root, forged, self.change_path)
        self.assertEqual("PK6", item)
        self.assertIn("coverage_hash", detail)

    def test_pk7_a_supersession_of_the_receipt(self) -> None:
        forged = plumb_commit(self.store, self.km, {paths.supersession_rel(str(self.record["receipt_id"])): b"x: 1\n"},
                              "a Supersession")
        self.assertEqual("PK7", self.item(forged))

    def test_pk8_two_consumptions_of_the_receipt(self) -> None:
        (consumption,) = self.policy_consumptions()
        record = consumption.to_record()
        record["consumption_id"] = "rcs_01ARZ3NDEKTSV4RRFFQ69G5FTY"
        forged = plumb_commit(self.store, self.km, {
            paths.consumption_rel("rcs_01ARZ3NDEKTSV4RRFFQ69G5FTY"): serialize.canonical_bytes(record)},
            "a second Consumption")
        self.assertEqual("PK8", self.item(forged))

    def metadata_paths(self) -> tuple[str, str]:
        (consumption,) = self.policy_consumptions()
        return paths.consumption_rel(consumption.consumption_id), paths.history_run_rel(str(self.record["review_run_id"]))

    def forged_consumption(self, **persisted: Any) -> bytes:
        """The real Policy Consumption with ``persisted`` claims changed (each still valid in form)."""
        (consumption,) = self.policy_consumptions()
        record = consumption.to_record()
        record["persisted_policy"] = dict(record["persisted_policy"], **persisted)
        return serialize.canonical_bytes(record)

    def test_pk8_recomputes_the_persisted_claims_from_kp_and_its_parent(self) -> None:
        """N4: a Consumption whose derived claims Kp and P do not prove is refused at PK8 (a596fad cross-checked seven
        of the fourteen persisted fields, and these two passed)."""
        consumption_path, summary_path = self.metadata_paths()
        for name in ("policy_delta_digest", "normalized_projection_hash"):
            with self.subTest(name=name):
                forged = plumb_commit(self.store, self.kp, {
                    consumption_path: self.forged_consumption(**{name: "0" * 64}),
                    summary_path: self.blob(self.km, summary_path)}, f"a metadata commit with a false {name}")
                self.assertEqual("PK8", self.item(forged))

    def test_pk8_another_policy_consumption_naming_the_change(self) -> None:
        """N4: another Policy Consumption (under another Receipt) naming the same change and Kp is refused."""
        (consumption,) = self.policy_consumptions()
        record = consumption.to_record()
        record.update(consumption_id="rcs_01ARZ3NDEKTSV4RRFFQ69G5FTV", receipt_id="rcp_01ARZ3NDEKTSV4RRFFQ69G5FTV")
        forged = plumb_commit(self.store, self.km, {
            paths.consumption_rel(record["consumption_id"]): serialize.canonical_bytes(record)},
            "a second Policy Consumption of the change")
        self.assertEqual("PK8", self.item(forged))

    def test_case_d_a_forged_km_whose_consumption_was_reverted_is_still_proven(self) -> None:
        """R5 case D (round-2 N4): a Km anywhere in the pushed history must be proven, even when a later commit took
        its Consumption back out of the pushed tree. At a596fad PK8 read only the pushed tree and published the
        forged Km as 'Kp alone'."""
        consumption_path, summary_path = self.metadata_paths()
        forged = plumb_commit(self.store, self.kp, {
            consumption_path: self.forged_consumption(policy_parent=self.kp),
            summary_path: self.blob(self.km, summary_path)}, "a forged metadata commit")
        reverted = plumb_commit(self.store, forged, {consumption_path: None, summary_path: None}, "a revert of it")
        self.assertEqual("PK8", self.item(reverted))
        self.assertIn("PK8 fails", publication.barrier_problem(self.root, reverted))

    def test_case_d_a_proven_km_whose_consumption_was_reverted_stays_proven(self) -> None:
        """The real Km is proven at Km whatever a later commit did to its Consumption; absent everywhere (Kp itself)
        is Kp alone (case C)."""
        consumption_path, summary_path = self.metadata_paths()
        reverted = plumb_commit(self.store, self.km, {consumption_path: None, summary_path: None}, "a revert of Km")
        self.assertIsNone(self.item(reverted))
        self.assertIsNone(publication.barrier_problem(self.root, reverted))
        self.assertIsNone(self.item(self.kp))

    def test_pk9_a_metadata_commit_with_an_extra_path(self) -> None:
        (consumption,) = self.policy_consumptions()
        consumption_path = paths.consumption_rel(consumption.consumption_id)
        summary_path = paths.history_run_rel(str(self.record["review_run_id"]))
        forged = plumb_commit(self.store, self.kp, {
            consumption_path: self.blob(self.km, consumption_path), summary_path: self.blob(self.km, summary_path),
            ".workline/extra.txt": b"x\n"}, "a metadata commit with an extra path")
        self.assertEqual("PK9", self.item(forged))
