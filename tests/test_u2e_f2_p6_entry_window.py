"""RB11 U2-E lane F2 (core): the Project-policy (P6) owner's ENTRY WINDOW.

``change_project_policy`` (and ``record_policy_evaluation``) open the owner mutation and only THEN ask Git whether the
repository is ready (``gitops.ensure_git_ready``: a detached HEAD is the STOP ``detached_head``) and record the changes
that were already there (``gitops.record_preexisting_dirty``). Before this repair neither call was inside any
``abandon_on_stop``, so a STOP there left a pending, effect-free, reservation-free owner mutation that holds the Profile
write scope: every other policy change or evaluation was refused ``reconcile required`` (and every push-pin change and
Work-terminal activation ``pending_operation``) until the ORIGINAL request was retried, and no Human recovery
disposition can set that record aside (the P6 owner has no read-only resume probe).

The repair is the rule the code already used for an effect-free owner (``rules/git``: a STOP before the first effect
abandons) and that START's Work run path, the Phase entry (``roadmap.enter_phase``: "only a Phase entry that this run
started may be abandoned before its first effect"), P7 (``global_policy._open_change``), direct CREATE, pin
maintenance, backfill and Work-terminal activation already follow: a mutation THIS call began is abandoned on a STOP in
its entry window; a mutation this call only RESUMED is never abandoned there, because it may hold what an earlier call
reserved or began (a frozen Candidate, a Review Run that only this record can resume) - the frozen T-B31 rule "kept
pending once a child began". A process that DIES (a ``Crash``, never a ``StopError``) in the window still leaves the
pending record, as every crash window does: the same request resumes it.

Real flows only (``change_project_policy`` / ``record_policy_evaluation`` on a restored evidence Project); the only
injected thing is the fault itself.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any
from unittest import mock

from helpers import git, run_python
from planning_helpers import Crash, crash_at
from project_policy_helpers import Discovery, PolicyCase, evaluation_request, policy_review, two_reviewers
from workline import gitops, project_policy
from workline.errors import ReconcileRequired, StopError
from workline.mutation import MutationController
from workline.review import policy

INJECTED = "u2e_f2_injected_stop"

#: The child process of the "process ended after the STOP" test: one policy change request, outcome on one line.
CHILD = """
import json, sys
from pathlib import Path
from project_policy_helpers import change_request, history_refs, policy_review
from workline import project_policy
from workline.errors import StopError
from workline.store import ProjectStore

store = ProjectStore(Path.cwd())
request = change_request(history_refs(store), after=int(sys.argv[1]))
try:
    result = project_policy.change_project_policy(store, request, review=policy_review())
except StopError as exc:
    print("RESULT " + json.dumps({"stopped": exc.code, "type": type(exc).__name__}))
else:
    print("RESULT " + json.dumps({"status": result.status, "mutation_id": result.mutation_id}))
"""


class EntryCase(PolicyCase):
    """A restored evidence Project and the helpers to read EVERY owner mutation record, whatever its status."""

    template = "local"

    def setUp(self) -> None:
        super().setUp()
        #: the one request every attempt of a test uses (its evidence references are read once)
        self.first = self.request()

    def detach(self) -> str:
        """Detach HEAD at the current commit; returns the branch to come back to."""
        branch = self.git("symbolic-ref", "--short", "HEAD").strip()
        self.git("checkout", "-q", "--detach", self.commit_of())
        return branch

    def reattach(self, branch: str) -> None:
        self.git("checkout", "-q", branch)

    def records_of(self, operation: str) -> list[dict[str, Any]]:
        """EVERY owner mutation record of ``operation``, whatever its status (pending, abandoned, completed)."""
        return [record for record in MutationController(self.store).list_records()
                if record["owner"] == project_policy.OWNER
                and (record.get("invocation") or {}).get("operation") == operation]

    def assert_closed_empty(self, record: dict[str, Any]) -> None:
        """Abandoned (closed, not deleted), nothing recorded, nothing reserved: it names nothing a retry needs."""
        self.assertEqual(("abandoned", [], {}), (record["status"], record["effects"], record["reserved_ids"]))

    def child(self, after: int) -> dict[str, Any]:
        """One policy change request in a fresh interpreter of THIS tree, from inside the Project."""
        src = Path(project_policy.__file__).resolve().parent.parent
        env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(src), str(Path(__file__).resolve().parent))),
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
        completed = run_python([sys.executable, "-B", "-", str(after)], cwd=self.root, stdin=CHILD, env=env)
        lines = [line for line in completed.stdout.splitlines() if line.startswith("RESULT ")]
        self.assertEqual(1, len(lines), f"stdout={completed.stdout!r} stderr={completed.stderr!r}")
        return json.loads(lines[0][len("RESULT "):])


# =========================================================================== P6 policy change: the repaired window

class PolicyChangeEntryWindowTests(EntryCase):
    """A STOP in the entry window of a NEW owner mutation leaves nothing pending."""

    def test_a_detached_head_leaves_no_pending_owner(self) -> None:
        profile, head, runs = self.profile_bytes(), self.commit_of(), self.policy_runs()
        self.detach()
        with self.assertRaises(StopError) as raised:
            self.change(self.first)
        self.assertEqual("detached_head", raised.exception.code)
        self.assertEqual([], self.policy_pending(), "no pending owner: it was opened for nothing, so nothing needs it")
        (record,) = self.records_of(project_policy.OPERATION)
        self.assert_closed_empty(record)
        self.assertEqual((profile, head, runs), (self.profile_bytes(), self.commit_of(), self.policy_runs()),
                         "nothing was written, committed or begun")
        self.assertEqual([], self.owner_pending())

    def test_a_different_request_is_not_refused_after_the_stop(self) -> None:
        """The stranded record held the Profile scope: ANOTHER request used to be refused ``reconcile required``."""
        branch = self.detach()
        with self.assertRaises(StopError):
            self.change(self.first)
        self.reattach(branch)
        result = self.applied(self.request(after=3))
        self.assertEqual([], self.policy_pending())
        self.assertEqual(1, len(self.policy_runs()))
        self.assertEqual([], self.problems())
        self.assertEqual("applied", result.status)

    def test_the_same_request_retried_is_a_fresh_owner_and_applies_once(self) -> None:
        branch = self.detach()
        with self.assertRaises(StopError):
            self.change(self.first)
        (stopped,) = self.records_of(project_policy.OPERATION)
        self.reattach(branch)
        result = self.applied(self.first)
        self.assertNotEqual(stopped["mutation_id"], result.mutation_id, "a new owner record: the stopped one named nothing")
        self.assertEqual([], self.policy_pending())
        self.assertEqual(1, len(self.policy_runs()), "one Run")
        self.assertEqual(1, len(self.policy_receipts()), "one Receipt")
        self.assertEqual(1, len(self.policy_consumptions()), "one Consumption")
        self.assertEqual([], self.problems())
        self.assertEqual([], self.dirty())
        statuses = {record["mutation_id"]: record["status"] for record in self.records_of(project_policy.OPERATION)}
        self.assertEqual("abandoned", statuses[stopped["mutation_id"]], "closed, never reopened")

    def test_a_stop_other_than_detached_head_in_the_window_is_not_swallowed_and_closes_nothing(self) -> None:
        """AM-A covers the ``detached_head`` STOP of the Git-readiness check only: any other StopError - here one
        injected into the second call of the window - propagates and leaves the record exactly as it was."""
        with mock.patch.object(gitops, "record_preexisting_dirty", side_effect=StopError("injected", code=INJECTED)):
            with self.assertRaises(StopError) as raised:
                self.change(self.first)
        self.assertEqual(INJECTED, raised.exception.code)
        (kept,) = self.policy_pending()
        self.assertEqual([], kept["effects"])
        self.assertEqual("pending", kept["status"])

    def test_a_process_that_ended_after_the_stop_leaves_nothing_for_the_next_process(self) -> None:
        """(iii) process death and restart, with real processes: the first ends on the STOP, the second asks for
        ANOTHER policy change (the case that used to be refused ``reconcile required``)."""
        branch = self.detach()
        first = self.child(2)
        self.assertEqual({"stopped": "detached_head", "type": "StopError"}, first)
        self.assertEqual([], self.policy_pending())
        self.reattach(branch)
        second = self.child(3)
        self.assertEqual("applied", second.get("status"), second)
        self.assertEqual([], self.policy_pending())
        self.assertEqual([], self.problems())


# =========================================================================== what the repair must NOT widen

class ResumedOwnerKeptPendingTests(EntryCase):
    """T-B31: a mutation this call only RESUMED is never abandoned in the entry window."""

    def stop_before(self, step: str) -> None:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            raise StopError(f"injected STOP before {step}", code=INJECTED)

        with mock.patch.object(project_policy, step, wrapper), self.assertRaises(StopError) as raised:
            self.change(self.first)
        self.assertEqual(INJECTED, raised.exception.code)

    def assert_kept_then_resumed(self, pending: dict[str, Any]) -> None:
        """The same record, with the same IDs, survives a detached-HEAD retry and finishes on a branch."""
        reserved, notes = dict(pending["reserved_ids"]), pending["notes"]
        branch = self.detach()
        with self.assertRaises(StopError) as raised:
            self.change(self.first)
        self.assertEqual("detached_head", raised.exception.code)
        (after,) = self.policy_pending()
        self.assertEqual((pending["mutation_id"], "pending", reserved, notes["policy_candidate"]),
                         (after["mutation_id"], after["status"], after["reserved_ids"],
                          after["notes"]["policy_candidate"]), "the very record, untouched")
        self.assertEqual([pending["mutation_id"]],
                         [r["mutation_id"] for r in self.records_of(project_policy.OPERATION)], "no second record")
        self.reattach(branch)
        result = self.applied(self.first)
        self.assertEqual(pending["mutation_id"], result.mutation_id, "the same owner record finished")
        self.assertEqual([], self.policy_pending())

    def test_a_frozen_owner_before_g1_is_kept_when_the_retry_meets_a_detached_head(self) -> None:
        self.stop_before("_accept")
        (pending,) = self.policy_pending()
        self.assertTrue(any(key.startswith("review-run:") for key in pending["reserved_ids"]), "IDs are reserved")
        self.assertEqual([], self.policy_runs(), "no child yet")
        self.assert_kept_then_resumed(pending)

    def test_an_owner_whose_run_began_is_kept_when_the_retry_meets_a_detached_head(self) -> None:
        """After G1 the owner record is the ONLY way to resume the Run (T-B31)."""

        class Failing(Discovery):
            def __call__(self, task: Any) -> Any:
                self.tasks.append(task)
                raise RuntimeError("the reviewer process died")

        with self.assertRaises(StopError) as raised:
            self.change(self.first, policy_review(Failing()))
        self.assertEqual("review_reviewer_failed", raised.exception.code)
        (pending,) = self.policy_pending()
        (run_id,) = self.policy_runs()
        self.assertIn(run_id, pending["reserved_ids"].values())
        self.assert_kept_then_resumed(pending)
        self.assertEqual([run_id], self.policy_runs(), "one Run: the child that began is the child that finished")


class CrashWindowUnchangedTests(EntryCase):
    """A process that DIES in the window (never a StopError) leaves the pending record, as before the repair."""

    def test_a_crash_in_the_window_leaves_the_record_and_the_same_request_resumes_it(self) -> None:
        with crash_at(gitops, "ensure_git_ready"), self.assertRaises(Crash):
            self.change(self.first)
        (pending,) = self.policy_pending()
        self.assertEqual(("pending", [], {}), (pending["status"], pending["effects"], pending["reserved_ids"]))
        with self.assertRaises(ReconcileRequired):
            self.change(self.request(after=3))  # another request still meets the pending record
        result = self.applied(self.first)
        self.assertEqual(pending["mutation_id"], result.mutation_id, "the same request resumed the very record")
        self.assertEqual([], self.policy_pending())


# =========================================================================== P6 evaluation: the same window

class PolicyEvaluationEntryWindowTests(EntryCase):
    """``record_policy_evaluation`` opens its owner mutation before the same Git readiness check."""

    template = "profiled"  # one applied change to evaluate

    def evaluation(self) -> project_policy.PolicyEvaluationResult:
        (change_id,) = self.review_store.policy_change_ids()
        request = evaluation_request(change_id, self.refs(), result=policy.RESULT_INCONCLUSIVE,
                                     next_action=policy.NEXT_CONTINUE_OBSERVATION)
        return project_policy.record_policy_evaluation(self.store, request)

    def test_a_detached_head_leaves_no_pending_evaluation_owner(self) -> None:
        head = self.commit_of()
        self.detach()
        with self.assertRaises(StopError) as raised:
            self.evaluation()
        self.assertEqual("detached_head", raised.exception.code)
        self.assertEqual([], self.owner_pending())
        (record,) = self.records_of(project_policy.OPERATION_EVALUATION)
        self.assert_closed_empty(record)
        self.assertEqual(head, self.commit_of())

    def test_nothing_is_refused_afterwards_and_the_evaluation_is_recorded_once(self) -> None:
        branch = self.detach()
        with self.assertRaises(StopError):
            self.evaluation()
        self.reattach(branch)
        # a policy change request meets no stranded evaluation owner (it used to be refused ``reconcile required``)
        (first_change,) = self.review_store.policy_change_ids()
        request = self.request(after=3, supersedes=(first_change,), overlap=policy.OVERLAP_KNOWN)
        self.applied(request, two_reviewers())
        self.assertEqual([], self.owner_pending())

    def test_the_evaluation_retried_on_a_branch_records_once(self) -> None:
        branch = self.detach()
        with self.assertRaises(StopError):
            self.evaluation()
        self.reattach(branch)
        result = self.evaluation()
        self.assertEqual([], self.owner_pending())
        self.assertEqual((result.evaluation_id,), self.review_store.policy_evaluation_ids())
        self.assertEqual([], self.problems())
        self.assertEqual([], self.dirty())
