"""An applied effect a recorded commit finalizes is written again only on that commit's branch (BL-038).

An operation records a decided effect, applies it, records the commit that finalizes it and makes that commit
(``rules/git``: Multi-write mutation, Commit / push). A resume classifies every recorded effect again against the
working tree it meets. Interrupted after the commit was made - before its push, or after the push and before the
operation finished - and retried after a person checked out a branch whose history does not hold that commit, the
retry found the effects it had applied missing there and wrote them again into that branch's working tree: the
lifecycle events, the Work file and its Related edges. START also replayed the push of an earlier stage and
published the finalization commit. Only then did the retry reach the commit, whose classification asks for the
branch only of a commit not made yet: it stopped because its own writes had left the commit's paths changed - or,
with a commit carrying the same message on that branch, took the commit as made and reported success. Git then
refused to check the recorded branch out again over what had been written, and ``validate_project`` reported
nothing.

Before anything is replayed or saved, an effect the record holds as applied that the resume would write again is
now written only while HEAD is on the branch named by the commit recorded right after it. Anywhere else - another
branch, a detached HEAD, a branch Git cannot name - the retry stops with nothing replayed, recorded, committed or
pushed, and back on that branch the same retry goes on. A resume that writes nothing applied again is unchanged,
and so is what a commit recorded without a branch finalizes.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from helpers import completing_executor, git
from test_decision_branch_binding import DECIDED_ON, SIDE, DecisionCase
from test_recorded_commit_message import pushed_before_completion
from test_recorded_commit_resume import EVENT_LOG, MAIN
from workline import gitcmd, yamlish
from workline import start as st
from workline.errors import StopError
from workline.mutation import MutationController
from workline.state import ProjectView

#: What the refusal says about the effect it would have written again (``_require_finalized_branch``).
WRITTEN_AGAIN = "whose working tree does not hold that effect"
#: What the recorded commit's own classification says when it refuses (``Mutation.apply``).
COMMIT_REFUSED = "(git_commit) applied with unexpected result"


def unanswered_branch():
    """Git cannot say which branch HEAD is on; the entry's ``symbolic-ref --short`` still answers."""
    real = gitcmd.run_git

    def run_git(repo, *args, check=True):
        if args[:2] == ("symbolic-ref", "--quiet"):
            return gitcmd.GitResult(128, "", "fatal: cannot answer")
        return real(repo, *args, check=check)

    return mock.patch.object(gitcmd, "run_git", run_git)


class FinalizedCase(DecisionCase):
    """A Project with a remote, a ``side`` branch at the commit every operation starts from, and its windows."""

    def world(self, name: str, decision: str) -> None:
        super().world(name, decision)
        git(self.root, "branch", "side")  # holds none of what the operation is about to commit

    def commit_stage(self, decision: str) -> str:
        return rf"^{self.w1}:finalize:0$" if decision in ("start completion", "outer completion") else r"^finalize$"

    def committed(self, decision: str) -> tuple:
        """Interrupt ``decision`` with its commit made and recorded as applied, and its push not made (W4)."""
        call, _, _ = self.decision(decision)
        pattern = self.commit_stage(decision)
        pending = self.interrupt(call, pattern, "committed")
        (commit,) = [e for e in pending["effects"] if e["kind"] == "git_commit" and re.search(pattern, e["stage"])]
        self.assertTrue(commit["applied"])
        self.assertIn("commit_id", commit)  # BL-037: the commit this mutation made is recorded by its ID
        self.assertEqual(commit["payload"]["branch"], MAIN)
        return call, pending

    def pushed(self, decision: str) -> tuple:
        """Interrupt ``decision`` with its push made and the operation not completed (W5)."""
        call, _, _ = self.decision(decision)
        pending = self.stop_in(pushed_before_completion(), call)
        self.assertEqual(self.head(), self.remote_head())
        return call, pending

    def assertGoesOnBackOnMain(self, call, pending: dict) -> object:
        """Git lets the person go back - nothing was written over - and the same retry finishes there."""
        git(self.root, "checkout", "-q", "main")
        result = call()
        self.assertFinalizedHere(pending)
        self.assertEqual(self.on(), MAIN)
        return result

    def events_committed_on(self, ref: str) -> str:
        return git(self.root, "show", f"{ref}:{EVENT_LOG}")


# --------------------------------------------------------------------------- a branch that does not hold the commit
class OtherBranchTests(FinalizedCase):
    OWNERS = ("phase hold", "start completion", "outer completion", "direct creation")

    def test_nothing_applied_is_written_again_on_a_branch_without_the_commit(self) -> None:
        for index, owner in enumerate(self.OWNERS):
            with self.subTest(owner=owner, window="committed, not pushed"):
                self.world(f"committed-{index}", owner)
                call, pending = self.committed(owner)
                ran = list(self.ran)
                git(self.root, "checkout", "-q", "side")

                stopped = self.assertStopsUntouched(call, fragment=WRITTEN_AGAIN)

                self.assertIn(f"names {MAIN}; HEAD is now on {SIDE}", stopped.message)
                self.assertEqual(self.remote_head(), git(self.root, "rev-parse", "main~1").strip())  # nothing pushed
                result = self.assertGoesOnBackOnMain(call, pending)
                self.assertEqual(self.ran[:len(ran)], ran)
                if owner == "start completion":
                    self.assertEqual((result.status, self.ran.count(self.w1)), ("completed", 1))  # the executor was not asked again
                if owner == "outer completion":
                    self.assertEqual((result.status, self.ran), ("phase_complete", [self.w1, self.w2, self.integration]))

    def test_nothing_applied_is_written_again_after_the_push_either(self) -> None:
        for index, owner in enumerate(("phase hold", "start completion")):
            with self.subTest(owner=owner, window="pushed, not completed"):
                self.world(f"pushed-{index}", owner)
                call, pending = self.pushed(owner)
                git(self.root, "checkout", "-q", "side")

                self.assertStopsUntouched(call, fragment=WRITTEN_AGAIN)

                self.assertGoesOnBackOnMain(call, pending)

    def test_direct_creation_stops_before_its_write_scope_is_saved_again(self) -> None:
        """The first thing a resumed registration saves is its write scope; the record keeps every byte."""
        self.world("create-scope", "direct creation")
        call, pending = self.committed("direct creation")
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        recorded = path.read_bytes()
        (work_file,) = [e["payload"]["path"] for e in pending["effects"] if e["kind"] == "write_file"]
        git(self.root, "checkout", "-q", "side")

        self.assertStopsUntouched(call, fragment="(extending its write scope)")

        self.assertEqual(path.read_bytes(), recorded)
        self.assertFalse((self.root / work_file).exists())
        self.assertGoesOnBackOnMain(call, pending)
        self.assertTrue((self.root / work_file).exists())

    def test_a_same_message_commit_on_that_branch_is_no_success(self) -> None:
        for index, owner in enumerate(("phase hold", "start completion")):
            with self.subTest(owner=owner):
                self.world(f"same-message-{index}", owner)
                call, pending = self.committed(owner)
                recorded = self.recorded_commit(pending, self.commit_stage(owner))
                git(self.root, "checkout", "-q", "side")
                self.human_commit({"notes.md": "notes\nthe same message\n"}, recorded["message"])

                self.assertStopsUntouched(call, fragment=WRITTEN_AGAIN)

                self.assertGoesOnBackOnMain(call, pending)  # the recorded commit itself reaches main and its remote

    def test_an_earlier_push_is_not_replayed_before_stopping(self) -> None:
        """Outer START interrupted in its second Work's push window, on a branch holding only the first Work."""
        self.world("outer-second", "outer completion")
        call = lambda: st.start(self.store, self.w1, "outer", completing_executor(self.store, self.ran))  # noqa: E731
        pending = self.interrupt(call, rf"^{self.w2}:finalize:0$", "committed")
        first = git(self.root, "rev-parse", "main~2").strip()  # the first Work's finalization, under the second's two commits
        display = ProjectView.load(self.store).works[self.w1].display
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", first).strip(), f"chore(workline): complete {display}")
        git(self.root, "branch", "-f", "side", first)
        remote = self.remote_head()
        git(self.root, "checkout", "-q", "side")

        self.assertStopsUntouched(call, fragment=WRITTEN_AGAIN)

        self.assertEqual(self.remote_head(), remote)  # the first Work's recorded push published nothing more
        result = self.assertGoesOnBackOnMain(call, pending)
        self.assertEqual(result.status, "phase_complete")

    def test_a_decision_made_on_side_is_not_written_again_on_main(self) -> None:
        self.world("from-side", "start completion")
        git(self.root, "checkout", "-q", "side")
        git(self.root, "push", "-q", "origin", "side")
        call, _, _ = self.decision("start completion")
        pending = self.interrupt(call, self.commit_stage("start completion"), "committed")
        git(self.root, "checkout", "-q", "main")

        stopped = self.assertStopsUntouched(call, fragment=WRITTEN_AGAIN)

        self.assertIn(f"names {SIDE}; HEAD is now on {MAIN}", stopped.message)
        git(self.root, "checkout", "-q", "side")
        call()
        self.assertFinalizedHere(pending)
        self.assertEqual(self.on(), SIDE)

    def test_a_commit_recorded_but_not_made_stops_before_writing_again_too(self) -> None:
        """The commit refused, and the person stashed what the operation had applied before leaving (W3)."""
        self.world("stashed", "phase hold")
        call, _, _ = self.decision("phase hold")
        pending = self.interrupt(call, r"^finalize$", "commit refused")
        git(self.root, "stash", "push", "-q", "--", EVENT_LOG)
        git(self.root, "checkout", "-q", "side")

        self.assertStopsUntouched(call, fragment=WRITTEN_AGAIN)

        git(self.root, "checkout", "-q", "main")
        self.assertEqual(call().status, "phase_held")  # on its own branch the stashed event is written again and committed
        self.assertFinalizedHere(pending)


# --------------------------------------------------------------------------- where nothing applied is written again
class UnchangedTests(FinalizedCase):
    def test_the_recorded_branch_goes_on_as_before(self) -> None:
        moves = {
            "stayed": lambda: None,
            "left and came back": lambda: (git(self.root, "checkout", "-q", "side"), git(self.root, "checkout", "-q", "main")),
            "grew by an independent commit": lambda: self.human_commit({"notes.md": "notes\nby a person\n"}, "docs: a note"),
        }
        for index, ((label, move), owner) in enumerate((m, o) for m in moves.items() for o in ("phase hold", "start completion")):
            with self.subTest(move=label, owner=owner):
                self.world(f"same-{index}", owner)
                call, pending = self.committed(owner)
                made = self.head()
                move()
                executed: list[str] = []

                self.counting(call, executed)

                self.assertEqual(executed, ["git_push"])
                if label == "grew by an independent commit":
                    # the push publishes the commit this mutation made, not the person's commit on top of it (BL-050)
                    self.assertEqual(git(self.remote_path(self.name), "rev-parse", "main").strip(), made)
                    self.assertEqual(self.parent(self.head()), made)
                    git(self.root, "push", "-q", "origin", "main:main")  # the person publishes their own commit
                self.assertFinalizedHere(pending)

    def test_a_branch_that_holds_the_commit_goes_on_as_before(self) -> None:
        for index, owner in enumerate(("phase hold", "start completion", "outer completion")):
            with self.subTest(owner=owner):
                self.world(f"holds-{index}", owner)
                call, pending = self.committed(owner)
                made = self.head()
                git(self.root, "checkout", "-q", "-b", "holding")

                result = call()

                self.assertEqual(git(self.remote_path(self.name), "rev-parse", "main").strip(), made)  # the recorded branch
                if owner == "outer completion":  # the next Works are decided where HEAD is now (BL-036)
                    self.assertEqual((result.status, self.on()), ("phase_complete", "refs/heads/holding"))
                else:
                    self.assertEqual((self.head(), self.dirty()), (made, []))
                records = {r["mutation_id"]: r for r in MutationController(self.store).list_records()}
                self.assertEqual(records[pending["mutation_id"]]["status"], "completed")

    def test_an_executor_that_moves_to_another_branch_goes_on_as_before(self) -> None:
        """Uninterrupted outer START whose second Work moves to a new branch, with and without result files."""
        for index, with_files in enumerate((True, False)):
            with self.subTest(result_files=with_files):
                self.world(f"executor-moves-{index}", "outer completion")
                done = completing_executor(self.store, self.ran, with_files=with_files)

                def moving(ctx, done=done):
                    if ctx.work.id == self.w2:
                        git(self.root, "checkout", "-q", "-b", "feature")
                    return done(ctx)

                result = st.start(self.store, self.w1, "outer", moving)

                self.assertEqual((result.status, self.on()), ("phase_complete", "refs/heads/feature"))
                self.assertEqual(self.ran, [self.w1, self.w2, self.integration])


# --------------------------------------------------------------------------- when Git cannot name the branch
class UnnamedBranchTests(FinalizedCase):
    def test_a_branch_git_cannot_name_stops_only_what_would_be_written_again(self) -> None:
        with self.subTest(case="an applied effect would be written again"):
            self.world("unnamed-other", "phase hold")
            call, pending = self.committed("phase hold")
            git(self.root, "checkout", "-q", "side")
            with unanswered_branch():
                stopped = self.assertStopsUntouched(call, fragment=WRITTEN_AGAIN)
            self.assertIn("HEAD is now on a branch Git cannot name", stopped.message)
            self.assertGoesOnBackOnMain(call, pending)
        with self.subTest(case="everything applied is in place"):
            self.world("unnamed-same", "phase hold")
            call, pending = self.committed("phase hold")
            executed: list[str] = []
            with unanswered_branch():
                self.assertEqual(self.counting(call, executed).status, "phase_held")
            self.assertEqual(executed, ["git_push"])
            self.assertFinalizedHere(pending)


# --------------------------------------------------------------------------- what this does not decide
class KnownResidualTests(FinalizedCase):
    def strip_commit_branch(self, pending: dict) -> None:
        """Rewrite the record as an implementation before commits carried their branch wrote it."""
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        for effect in record["effects"]:
            effect.pop(DECIDED_ON, None)
            effect.pop("commit_id", None)
            if effect["kind"] == "git_commit":
                effect["payload"].pop("branch", None)
        path.write_text(yamlish.dump(record), encoding="utf-8")

    def test_a_commit_recorded_without_a_branch_is_left_to_the_rules_it_always_had(self) -> None:
        """L-1: no branch is inferred; on another branch the old write-then-stop remains. On its own branch the commit is
        recognized as it always was, and its push, which cannot name that commit, stops before pushing (BL-050)."""
        with self.subTest(retried_on="another branch"):
            self.world("legacy-other", "phase hold")
            call, pending = self.committed("phase hold")
            self.strip_commit_branch(pending)
            git(self.root, "checkout", "-q", "side")
            with self.assertRaises(StopError) as stopped:
                call()
            self.assertEqual(stopped.exception.code, "reconcile_required")
            self.assertIn(COMMIT_REFUSED, stopped.exception.message)
            self.assertNotIn(WRITTEN_AGAIN, stopped.exception.message)
            self.assertEqual(self.dirty(), [f" M {EVENT_LOG}"])
        with self.subTest(retried_on="its own branch"):
            # the commit is still recognized as it always was; its push cannot name it, and pushes nothing (BL-050 L1)
            self.world("legacy-same", "phase hold")
            call, pending = self.committed("phase hold")
            self.strip_commit_branch(pending)
            remote = git(self.remote_path(self.name), "rev-parse", "main").strip()
            with self.assertRaises(StopError) as stopped:
                call()
            self.assertEqual(stopped.exception.code, "reconcile_required")
            self.assertIn("cannot show which commit it publishes", stopped.exception.message)
            self.assertEqual(git(self.remote_path(self.name), "rev-parse", "main").strip(), remote)
            self.assertEqual([p["mutation_id"] for p in MutationController(self.store).list_pending()], [pending["mutation_id"]])

    def test_a_rewritten_recorded_branch_is_left_to_the_commit_id(self) -> None:
        """The recorded branch itself no longer holds the commit: BL-037's unreachable ID decides, not this rule."""
        self.world("rewound", "phase hold")
        call, _ = self.committed("phase hold")
        git(self.root, "reset", "-q", "--keep", "HEAD~1")
        with self.assertRaises(StopError) as stopped:
            call()
        self.assertIn(COMMIT_REFUSED, stopped.exception.message)
        self.assertNotIn(WRITTEN_AGAIN, stopped.exception.message)


# --------------------------------------------------------------------------- the process really dies
KILL_BEFORE_PUSH = """#!/bin/sh
# pre-push hook: runs for the push classification's dry-run, after the commit is made and recorded as applied.
flag="$(git rev-parse --git-dir)/workline-test-kill-push"
while read local_ref local_sha remote_ref remote_sha; do
  if [ -f "$flag" ] && [ "$(git log -1 --format=%s "$local_sha")" = "$(cat "$flag")" ]; then
    rm -f "$flag"
    "{python}" -c "import os, signal; os.kill(int(os.environ['WORKLINE_TEST_KILL_PID']), signal.SIGTERM)"
    exit 1
  fi
done
exit 0
"""


class ProcessKillTests(FinalizedCase):
    def test_a_start_killed_before_its_push_does_not_write_its_completion_on_another_branch(self) -> None:
        """No patching: the process running START dies while its finalization push is classified (W4)."""
        self.world("killed", "start completion")
        display = ProjectView.load(self.store).works[self.w1].display
        hooks = self.root / ".git" / "hooks"
        (hooks / "pre-push").write_text(KILL_BEFORE_PUSH.replace("{python}", Path(sys.executable).as_posix()),
                                        encoding="utf-8", newline="\n")
        os.chmod(hooks / "pre-push", 0o755)
        (self.root / ".git" / "workline-test-kill-push").write_text(f"chore(workline): complete {display}",
                                                                   encoding="utf-8", newline="")
        code = (
            "import os, sys\n"
            f"sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n"
            "import helpers\n"
            "from pathlib import Path\n"
            "from workline import start as st\n"
            "from workline.store import ProjectStore\n"
            "os.environ['WORKLINE_TEST_KILL_PID'] = str(os.getpid())\n"
            f"store = ProjectStore(Path({str(self.root)!r}))\n"
            f"st.start(store, {self.w1!r}, 'single-work', helpers.completing_executor(store))\n"
            "print('not killed')\n"
        )
        env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
        try:
            died = subprocess.run([sys.executable, "-B", "-c", code], cwd=str(self.root), capture_output=True, text=True, env=env)
        finally:
            (hooks / "pre-push").unlink()
        self.assertNotEqual(died.returncode, 0, died.stdout + died.stderr)
        self.assertNotIn("not killed", died.stdout)
        (pending,) = MutationController(self.store).list_pending()
        finalize = [e for e in pending["effects"] if e["stage"] == f"{self.w1}:finalize:0"]
        self.assertEqual([(e["kind"], e["applied"], "commit_id" in e) for e in finalize],
                         [("git_commit", True, True), ("git_push", False, False)])
        git(self.root, "checkout", "-q", "side")
        call = lambda: st.start(self.store, self.w1, "single-work", completing_executor(self.store, self.ran))  # noqa: E731

        self.assertStopsUntouched(call, fragment=WRITTEN_AGAIN)

        self.assertEqual(self.assertGoesOnBackOnMain(call, pending).status, "completed")
        self.assertEqual(self.ran, [])  # the executor was not asked again


if __name__ == "__main__":
    unittest.main()
