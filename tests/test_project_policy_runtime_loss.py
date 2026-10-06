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
* settled Runs (not_authorized, human_wait) are set aside and the request is a new Run;
* malformed (R3 / R6 / R9): an uncommitted generation, a task whose provenance does not hold, a G1 with no TaskInput -
  ``review_recovery_incomplete`` from discovery itself, nothing pending; ambiguous (two recoverable Runs) likewise.

The publication barrier (PK1-PK9): a proven Kp / Km passes for every push; each item refuses its forgery.
"""

from __future__ import annotations

from typing import Any

from helpers import rmtree
from planning_helpers import Crash, crash_at, move_branch, plan, plumb_commit
from project_policy_helpers import (
    GENERATION_SUBJECT, KM_SUBJECT, KP_SUBJECT, Discovery, Interrupted, PolicyCase, after_effect, before_effect, claim,
    policy_review, two_reviewers,
)
from workline import gitcmd, project_policy
from workline import roadmap as rm
from workline.errors import ReconcileRequired, StopError
from workline.review import paths, policy, publication, serialize


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


class HumanWaitSetAsideTests(_RuntimeLoss):
    template = "local"

    def test_a_human_wait_run_is_set_aside(self) -> None:
        waiting = self.crashed_at("_finish", policy_review(Discovery(claim("human", "MID"))))
        self.assertEqual(4, self.review_store.gate_chain(waiting).latest.generation)
        self.lose_runtime()
        result = self.applied(self.first)
        self.assertNotEqual(waiting, result.review_run_id)


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
        kp, other = self.stranded_kp()
        self.assertIsNone(publication.barrier_problem(self.root, kp))
        held = rm.hold_roadmap(self.store, other)
        self.assertEqual(held.head, self.remote_main())
        self.assertTrue(gitcmd.descends_from(self.root, held.head, kp))

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

    def test_pk9_a_metadata_commit_with_an_extra_path(self) -> None:
        (consumption,) = self.policy_consumptions()
        consumption_path = paths.consumption_rel(consumption.consumption_id)
        summary_path = paths.history_run_rel(str(self.record["review_run_id"]))
        forged = plumb_commit(self.store, self.kp, {
            consumption_path: self.blob(self.km, consumption_path), summary_path: self.blob(self.km, summary_path),
            ".workline/extra.txt": b"x\n"}, "a metadata commit with an extra path")
        self.assertEqual("PK9", self.item(forged))
