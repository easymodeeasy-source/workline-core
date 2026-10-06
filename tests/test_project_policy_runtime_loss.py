"""ORCH-RB6-1: a Policy Review whose owner runtime record is lost is recovered by canonical discovery, never bypassed.

Rows (the runtime directory deleted after each):

* after G1 and after the G5 Receipt: the same request finds its one recoverable Run by canonical recovery discovery
  and resumes it with its canonical IDs (policy change id, Run, tasks, Receipt) - no substitute Run, one Receipt,
  one change record, one Consumption, and (remote) exactly Kp then Km published;
* after Kp (local and remote): the change record is stored without its Consumption and the Kp identity was never
  durably saved: nothing infers it from Git history, nothing is published, and no Policy Change of any request
  starts beside it (``review_p6_run_unrecovered``);
* after Km: the consumed Run is settled; nothing is duplicated;
* ambiguous (two recoverable Runs of one request) and malformed earlier Runs fail closed; another request (another
  operation identity) is a new Run.

The publication barrier: another operation's push over a policy commit that holds up from committed objects passes;
over one that does not (the same tree, the change record and the Profile split across two commits) it is refused,
and the destination keeps what it had.
"""

from __future__ import annotations

from typing import Any

from helpers import git, rmtree
from planning_helpers import Crash, crash_at, move_branch, plan, plumb_commit
from project_policy_helpers import Interrupted, PolicyCase, after_effect, two_reviewers
from workline import gitcmd, project_policy
from workline import roadmap as rm
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.review import paths, policy, publication, serialize

KP_SUBJECT = "chore(workline): apply project policy change "


class _RuntimeLoss(PolicyCase):
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

    def assert_recovered(self, run_id: str) -> project_policy.PolicyChangeResult:
        candidate = self.snapshot_candidate(run_id)
        receipts = self.policy_receipts()
        result = self.applied()
        self.assertEqual((run_id, candidate["policy_change_id"]), (result.review_run_id, result.policy_change_id),
                         "the earlier Run is resumed with its canonical IDs, never replaced")
        self.assertEqual([run_id], self.policy_runs())
        self.assertEqual((candidate["policy_change_id"],), self.review_store.policy_change_ids())
        self.assertEqual(1, len(self.policy_receipts()))
        if receipts:
            self.assertEqual(receipts, self.policy_receipts(), "the sealed Receipt is the one consumed")
        self.assertEqual([result.consumption_id], [found.consumption_id for found in self.policy_consumptions()])
        self.assertEqual([], self.problems())
        return result

    def assert_refused(self, *requests: policy.PolicyChangeRequest) -> None:
        before = self.canonical()
        for request in requests:
            with self.subTest(request=request.after_setting), self.assertRaises(ReconcileRequired) as raised:
                self.change(request)
            self.assertEqual(policy.REASON_RUN_UNRECOVERED, raised.exception.reason)
            self.assertEqual(before, self.canonical(), "nothing is reserved canonically, written or committed")
            self.assertEqual([], self.policy_pending(), "the refused call leaves no pending mutation")

    def interrupted_at_g1(self) -> str:
        with crash_at(project_policy, "_launch_discovery"), self.assertRaises(Crash):
            self.change()
        (run_id,) = self.policy_runs()
        return run_id


class LocalRuntimeLossTests(_RuntimeLoss):
    template = "local"

    def test_after_g1_the_one_recoverable_run_resumes_with_its_ids(self) -> None:
        run_id = self.interrupted_at_g1()
        self.lose_runtime()
        self.assert_recovered(run_id)

    def test_after_the_receipt_the_sealed_receipt_is_the_one_consumed(self) -> None:
        with crash_at(project_policy, "_persist"), self.assertRaises(Crash):
            self.change()
        (run_id,) = self.policy_runs()
        self.assertEqual(1, len(self.policy_receipts()))
        self.lose_runtime()
        self.assert_recovered(run_id)

    def test_after_kp_nothing_is_inferred_from_git_history(self) -> None:
        with after_effect("git_commit", project_policy.STAGE_KP), self.assertRaises(Interrupted):
            self.change()
        (kp,) = self.commits_with(KP_SUBJECT)
        self.lose_runtime()
        self.assert_refused(self.request(), self.request(after=3))
        self.assertEqual([kp], self.commits_with(KP_SUBJECT), "the Kp is never re-made or adopted")
        self.assertEqual([], self.policy_consumptions())

    def test_after_km_the_consumed_run_is_settled_and_nothing_is_duplicated(self) -> None:
        with after_effect("git_commit", project_policy.STAGE_KM), self.assertRaises(Interrupted):
            self.change()
        self.assertEqual(1, len(self.policy_consumptions()))
        self.lose_runtime()
        before = self.canonical()
        # settled: the same request is a fresh freeze against the moved Profile (two reviewers now), changing nothing
        with self.assertRaises(StopError) as raised:
            self.change(review=two_reviewers())
        self.assertEqual(policy.CODE_DIRECTION_INVALID, raised.exception.code)
        self.assertEqual(before, self.canonical())
        self.assertEqual([], self.policy_pending())

    def test_two_recoverable_runs_of_one_request_are_ambiguous(self) -> None:
        run_id = self.interrupted_at_g1()
        self.lose_runtime()
        # a second, identical-request Run at generation 1 (only a hand-made history holds one)
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
            self.change()
        self.assertEqual("review_recovery_ambiguous", raised.exception.reason)
        self.assertEqual(before, self.canonical(), "no Run is chosen by age, ID or position, and nothing is written")
        self.assertEqual([], self.policy_pending())

    def test_a_malformed_earlier_run_fails_closed_and_another_request_is_a_new_run(self) -> None:
        run_id = self.interrupted_at_g1()
        self.lose_runtime()
        before = self.canonical()
        gate_one = self.root / paths.gate_rel(run_id, 1)
        original = gate_one.read_bytes()
        gate_one.write_bytes(original + b"# tampered\n")
        # a Run that cannot be shown whole is never replaced by a new Run: the call fails closed, nothing written
        with self.assertRaises((StopError, ValidationError)):
            self.change()
        gate_one.write_bytes(original)
        self.assertEqual(before, self.canonical())
        self.assertEqual([], self.policy_pending())
        # another request has another operation identity: no earlier Run of ITS identity, so it is a new Run
        result = self.applied(self.request(after=3))
        self.assertNotEqual(run_id, result.review_run_id)


class RemoteRuntimeLossTests(_RuntimeLoss):
    template = "remote"

    def test_after_the_receipt_recovery_publishes_exactly_kp_and_km(self) -> None:
        with crash_at(project_policy, "_persist"), self.assertRaises(Crash):
            self.change()
        (run_id,) = self.policy_runs()
        pushes = self.pushes()
        self.lose_runtime()
        result = self.assert_recovered(run_id)
        published = self.pushes()[len(pushes):]
        self.assertEqual([str(result.policy_commit), str(result.metadata_commit)], [item[1] for item in published])
        self.assert_fast_forward_pushes()

    def test_after_kp_nothing_is_published_by_the_refused_retry(self) -> None:
        with after_effect("git_commit", project_policy.STAGE_KP), self.assertRaises(Interrupted):
            self.change()
        pushes = self.pushes()
        self.lose_runtime()
        self.assert_refused(self.request())
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
        self.assertEqual(git(self.root, "rev-parse", f"{kp}^{{tree}}").strip(),
                         git(self.root, "rev-parse", f"{second}^{{tree}}").strip())
        move_branch(self.store, second)
        problem = publication.barrier_problem(self.root, second)
        self.assertIn("PK2 fails", problem)
        with self.assertRaises(StopError) as raised:
            rm.hold_roadmap(self.store, other)
        self.assertEqual("review_publication_barrier", raised.exception.code)
        self.assertEqual(published, self.remote_main(), "the destination keeps what it had")
