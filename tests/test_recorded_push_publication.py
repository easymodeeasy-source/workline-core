"""A recorded push publishes the commit its own Git stage made, never the branch as it is when the push runs (BL-050).

Every operation that pushes records its Git stage as one commit and, right after it, the push of it (``rules/git``:
Commit / push, Push destination). The push was recorded as ``{remote, branch, locator}`` and classified and made as
``git push <remote> <branch>:<branch>`` on every apply, whatever its ``applied`` flag said. A commit someone put on the
branch after the mutation's own - a person, another tool, another Workline operation, whatever paths it touched - was
therefore published by the mutation's push: by a push not made yet when the process died, by a push that had reached
the remote before its flag was saved, by a push recorded as applied in a mutation not yet completed, and, with no
interruption at all, by an outer START run again while its next Work waited for an answer. The operation reported
success and ``validate_project`` reported nothing.

A recorded push now publishes the commit its Git stage recorded making, by that ID, to the branch that commit names,
and is classified by where that commit stands at the destination. The branch is that commit, or has moved on past it:
published, nothing is pushed and the branch is left where it is. The branch is missing or behind it: that commit alone
is pushed. The branch holds another history: reconcile required, nothing is forced. Commits made on top of it are
never pushed by it; a later stage that makes its own commit on top of them publishes them as that commit's history,
as a commit made on top of independent commits always did (BL-032). A push whose commit cannot be named - a record
from before commits carried their ID, a commit whose ID was never saved, a record whose push no longer follows its
commit - is not made, and the branch as it is now never stands in for it.
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
from test_decision_branch_binding import after_recording
from test_recorded_commit_message import committed_before_its_flag, pushed_before_completion
from test_recorded_commit_resume import EVENT_LOG, CommitWindowCase, Interrupted, after_applying
from workline import gitcmd
from workline import roadmap as rm
from workline import start as st
from workline import yamlish
from workline.errors import StopError
from workline.mutation import MutationController
from workline.validate import validate_project

HOLD = r"^finalize$"
#: What a refused push says about the commit it cannot name (``_recorded_publication``).
UNNAMED = "cannot show which commit it publishes"
KILL_AFTER_RECEIVE = """#!/bin/sh
# post-receive hook of the scratch remote: the push has landed; the process that made it dies before it saves anything
flag="$(git rev-parse --git-dir)/workline-test-kill-receive"
while read old new ref; do
  if [ -f "$flag" ] && [ "$(git log -1 --format=%s "$new")" = "$(cat "$flag")" ]; then
    rm -f "$flag"
    "{python}" -c "import os, signal; os.kill(int(os.environ['WORKLINE_TEST_KILL_PID']), signal.SIGTERM)"
  fi
done
exit 0
"""
EXTRA_COMMIT_HOOK = """#!/bin/sh
# post-commit: once, commit again right after the commit that ran the hook
flag="$(git rev-parse --git-dir)/workline-test-extra-commit"
if [ -f "$flag" ]; then
  rm -f "$flag"
  git commit -q --allow-empty -m "chore: made by a post-commit hook"
fi
exit 0
"""


def pushed_not_saved(pattern: str):
    """Stop with the push of the stage matching ``pattern`` made and its ``applied`` flag not saved."""
    real = MutationController.apply_effect

    def fire(controller, record):
        result = real(controller, record)
        if record["kind"] == "git_push" and re.search(pattern, record["stage"]):
            raise Interrupted("pushed, applied flag not saved")
        return result

    return mock.patch.object(MutationController, "apply_effect", fire)


class PublicationCase(CommitWindowCase):
    """A Project with a scratch bare remote (``CommitWindowCase.build``): Phase hold, START and their push windows."""

    # running --------------------------------------------------------------------
    def hold(self):
        return lambda: rm.hold_phase(self.store, self.pb)

    def stop(self, window, call) -> dict:
        """Run ``call`` into ``window``; return the record it leaves pending."""
        known = set(self.pending_ids())
        with window, self.assertRaises(Interrupted):
            call()
        (pending,) = [p for p in MutationController(self.store).list_pending() if p["mutation_id"] not in known]
        return pending

    def made(self, pending: dict, pattern: str = HOLD) -> str:
        """The ID of the commit the stage matching ``pattern`` recorded making."""
        record = self.record_of(pending["mutation_id"])
        (effect,) = [e for e in record["effects"] if e["kind"] == "git_commit" and re.search(pattern, e["stage"])]
        return effect["commit_id"]

    def record_of(self, mutation_id: str) -> dict:
        (record,) = [r for r in MutationController(self.store).list_records() if r["mutation_id"] == mutation_id]
        return record

    def edit_record(self, pending: dict, change) -> None:
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        change(record)
        path.write_text(yamlish.dump(record), encoding="utf-8")

    def person(self, label: str, path: str = "notes.md") -> str:
        """A person's ordinary commit of one tracked path on the branch HEAD is on; its ID."""
        if path == EVENT_LOG:
            text = (self.root / path).read_text(encoding="utf-8") + "\n"
        else:
            text = f"notes\n{label} by a person\n"
        return self.human_commit({path: text}, f"docs: {label} by a person")

    # the scratch remote ----------------------------------------------------------
    @property
    def remote(self) -> Path:
        return self.remote_path(self.name)

    def remote_refs(self) -> str:
        return git(self.remote, "for-each-ref", "--format=%(refname) %(objectname)")

    def local_refs(self) -> str:
        return git(self.root, "for-each-ref", "--format=%(refname) %(objectname)")

    def published(self, commit: str) -> bool:
        """Whether the remote's main holds ``commit``."""
        return subprocess.run(["git", "-C", str(self.remote), "merge-base", "--is-ancestor", commit, "main"],
                              capture_output=True).returncode == 0

    def remote_moves_to_its_own(self, label: str, *, onto: str | None = None) -> str:
        """Point the remote's main at a commit made elsewhere - on ``onto`` or on a history of its own - without a push to main."""
        other = self.tmp / f"{self.name}-{label}"
        if onto is None:
            git(self.tmp, "init", "-q", "-b", "main", str(other))
        else:
            git(self.tmp, "clone", "-q", str(self.remote), str(other))
            git(other, "checkout", "-q", "--detach", onto)
        (other / f"{label}.md").write_text(f"{label}\n", encoding="utf-8")
        git(other, "add", f"{label}.md")
        git(other, "-c", "user.name=elsewhere", "-c", "user.email=elsewhere@example.invalid", "commit", "-q", "-m", f"docs: {label}")
        commit = git(other, "rev-parse", "HEAD").strip()
        git(other, "push", "-q", str(self.remote), f"{commit}:refs/heads/{label}")  # a new branch: nothing is forced
        git(self.remote, "update-ref", "refs/heads/main", commit)
        git(self.remote, "update-ref", "-d", f"refs/heads/{label}")
        return commit

    # assertions ------------------------------------------------------------------
    def assertPublishedExactly(self, made: str, *later: str) -> None:
        """The remote's main is the recorded commit, and holds none of the commits made on top of it."""
        self.assertEqual(self.remote_head(), made)
        for commit in later:
            self.assertFalse(self.published(commit), f"{commit} reached the remote")

    def assertFinished(self, pending: dict) -> None:
        self.assertEqual(self.record_of(pending["mutation_id"])["status"], "completed")
        self.assertEqual(self.pending_ids(), [])
        self.assertEqual(validate_project(self.store), [])

    def assertRefusedUntouched(self, call, fragment: str) -> StopError:
        """Refused before anything is pushed: nothing executed, the records, both repositories and the tree as they were."""
        before = self.untouched()
        executed: list[str] = []
        with self.assertRaises(StopError) as refused:
            self.counting(call, executed)
        self.assertEqual(refused.exception.code, "reconcile_required", refused.exception.message)
        self.assertIn(fragment, refused.exception.message)
        self.assertEqual(executed, [])
        self.assertEqual(self.untouched(), before)
        return refused.exception

    def untouched(self) -> dict:
        return {
            "records": {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))},
            "local refs": self.local_refs(), "remote refs": self.remote_refs(), "head": self.head(),
            "dirty": self.dirty(), "fetch head": (self.root / ".git" / "FETCH_HEAD").exists(),
        }


# --------------------------------------------------------------------------- the defect: a later commit on the branch
class LaterCommitTests(PublicationCase):
    def test_a_push_not_made_yet_publishes_only_its_commit(self) -> None:
        """Committed, the push not made (P1): the resume pushes the commit alone, not the person's commit on top."""
        self.build("delayed")
        pending = self.interrupt(self.hold(), HOLD, "committed")
        made = self.made(pending)
        self.assertEqual(self.remote_head(), pending["effects"][1]["payload"]["base_head"])
        later = self.person("H1")
        executed: list[str] = []

        self.assertEqual(self.counting(self.hold(), executed).status, "phase_held")

        self.assertEqual(executed, ["git_push"])
        self.assertPublishedExactly(made, later)
        self.assertEqual(self.head(), later)  # the person's commit stays where they made it
        self.assertFinished(pending)

    def test_a_push_that_landed_is_not_made_again(self) -> None:
        """Pushed, its flag not saved (P3), or recorded applied and not completed (P4): nothing is pushed again."""
        windows = {"pushed, flag not saved": lambda: pushed_not_saved(HOLD), "pushed, not completed": pushed_before_completion}
        for index, (label, window) in enumerate(windows.items()):
            with self.subTest(window=label):
                self.build(f"landed-{index}")
                pending = self.stop(window(), self.hold())
                made = self.made(pending)
                self.assertEqual(self.remote_head(), made)
                (push,) = [e for e in self.record_of(pending["mutation_id"])["effects"] if e["kind"] == "git_push"]
                self.assertEqual(push["applied"], label == "pushed, not completed")
                later = [self.person("H1"), self.person("H2")]
                executed: list[str] = []

                self.assertEqual(self.counting(self.hold(), executed).status, "phase_held")

                self.assertEqual(executed, [])
                self.assertPublishedExactly(made, *later)
                self.assertFinished(pending)

    def test_a_real_process_death_after_the_push_landed(self) -> None:
        """No patching: the process dies in the remote's post-receive, the push landed and its flag unsaved (P3)."""
        self.build("killed")
        hook = self.remote / "hooks" / "post-receive"
        hook.write_text(KILL_AFTER_RECEIVE.replace("{python}", Path(sys.executable).as_posix()), encoding="utf-8", newline="\n")
        os.chmod(hook, 0o755)
        (self.remote / "workline-test-kill-receive").write_text(f"chore(workline): phase_held {self.pb}", encoding="utf-8", newline="")
        code = (
            "import os, sys\n"
            f"sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n"
            "import helpers\n"
            "from pathlib import Path\n"
            "from workline import roadmap as rm\n"
            "from workline.store import ProjectStore\n"
            "os.environ['WORKLINE_TEST_KILL_PID'] = str(os.getpid())\n"
            f"rm.hold_phase(ProjectStore(Path({str(self.root)!r})), {self.pb!r})\n"
            "print('not killed')\n"
        )
        try:
            died = subprocess.run([sys.executable, "-B", "-c", code], cwd=str(self.root), capture_output=True, text=True,
                                  env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
        finally:
            hook.unlink()
        self.assertNotEqual(died.returncode, 0, died.stdout + died.stderr)
        self.assertNotIn("not killed", died.stdout)
        self.assertFalse((self.remote / "workline-test-kill-receive").exists())
        (pending,) = MutationController(self.store).list_pending()
        self.assertEqual([(e["kind"], e["applied"]) for e in pending["effects"]],
                         [("append_event", True), ("git_commit", True), ("git_push", False)])
        made = self.made(pending)
        self.assertEqual(self.remote_head(), made)  # it landed
        later = self.person("H1")
        executed: list[str] = []

        self.assertEqual(self.counting(self.hold(), executed).status, "phase_held")

        self.assertEqual(executed, [])
        self.assertPublishedExactly(made, later)
        self.assertFinished(pending)

    def test_every_retry_keeps_to_the_same_commit(self) -> None:
        """However long the mutation stays pending, and however often it is retried, its push publishes nothing more."""
        self.build("retries")
        pending = self.interrupt(self.hold(), HOLD, "committed")
        made = self.made(pending)
        first = self.person("H1")
        with pushed_not_saved(HOLD), self.assertRaises(Interrupted):  # the retry pushes, and dies before saving that it did
            self.hold()()
        self.assertEqual(self.pending_ids(), [pending["mutation_id"]])
        self.assertPublishedExactly(made, first)
        second = self.person("H2")
        executed: list[str] = []

        self.assertEqual(self.counting(self.hold(), executed).status, "phase_held")

        self.assertEqual(executed, [])
        self.assertPublishedExactly(made, first, second)
        self.assertFinished(pending)
        third = self.person("H3")
        with self.assertRaises(StopError):  # closed: the same request is a new one, and the Phase is held already
            self.hold()()
        self.assertPublishedExactly(made, first, second, third)

    def test_another_operations_commit_is_left_to_that_operation(self) -> None:
        """A commit another Workline operation made on top is published by that operation's own push, not this one."""
        self.build("another")
        held = self.interrupt(self.hold(), HOLD, "committed")
        maintain, pattern = self.operation("related maintenance")
        maintained = self.interrupt(maintain, pattern, "committed")
        own, others = self.made(held), self.made(maintained, pattern)
        self.assertEqual(self.parent(others), own)
        executed: list[str] = []

        self.counting(self.hold(), executed)

        self.assertEqual(executed, ["git_push"])
        self.assertPublishedExactly(own, others)
        self.assertEqual(self.record_of(held["mutation_id"])["status"], "completed")
        self.assertEqual(self.pending_ids(), [maintained["mutation_id"]])
        maintain()
        self.assertPublishedExactly(others)
        self.assertFinished(maintained)

    def test_a_start_publishes_only_its_own_commits(self) -> None:
        """START, its finalization committed and not pushed, a person's commit on top: the results push is published
        already, the finalization push publishes the finalization commit, and nothing of the person's."""
        self.build("start")
        call, pattern = self.operation("start finalization")
        pending = self.interrupt(call, pattern, "committed")
        results, final = self.made(pending, rf"^{self.w1}:results:0$"), self.made(pending, pattern)
        self.assertEqual((self.remote_head(), self.parent(final)), (results, results))
        later = self.person("H1")
        executed: list[str] = []
        stages: list[str] = []

        self.assertEqual(self.counting(call, executed, stages).status, "completed")

        self.assertEqual(list(zip(stages, executed)), [(f"{self.w1}:finalize:0", "git_push")])
        self.assertPublishedExactly(final, later)
        self.assertFinished(pending)

    def test_an_outer_start_waiting_for_an_answer_does_not_publish_a_later_commit(self) -> None:
        """No interruption at all: W2 waits for an answer, a person commits meanwhile, and START is run again."""
        self.build("question")
        answered: list[bool] = [False]
        done = completing_executor(self.store)

        def execute(ctx):
            if ctx.work.id == self.w2 and not answered[0]:
                return st.QuestionWait("which way?")
            return done(ctx)

        call = lambda: st.start(self.store, self.w1, "outer", execute)  # noqa: E731
        self.assertEqual(call().status, "question_wait")
        (pending,) = MutationController(self.store).list_pending()  # pending while it waits, as designed
        first = self.head()
        self.assertEqual(self.remote_head(), first)  # W1 committed and published before W2 asked
        later = self.person("H1")
        executed: list[str] = []

        self.assertEqual(self.counting(call, executed).status, "question_wait")

        self.assertEqual(executed, [])
        self.assertPublishedExactly(first, later)
        answered[0] = True
        self.assertEqual(call().status, "phase_complete")
        # W2's own commits were decided after the person's commit and made on top of it; theirs is the push that
        # publishes it, as the history of a commit this mutation made (BL-032)
        w2_result = git(self.root, "rev-list", "--reverse", f"{later}..HEAD").split()[0]
        self.assertEqual(self.parent(w2_result), later)
        self.assertEqual(self.remote_head(), self.head())
        self.assertFinished(pending)


# --------------------------------------------------------------------------- controls: nothing else changes
class ControlTests(PublicationCase):
    def test_without_a_later_commit(self) -> None:
        for index, (label, window) in enumerate({"committed": None, "pushed": lambda: pushed_not_saved(HOLD)}.items()):
            with self.subTest(window=label):
                self.build(f"plain-{index}")
                pending = (self.interrupt(self.hold(), HOLD, "committed") if window is None
                           else self.stop(window(), self.hold()))
                executed: list[str] = []

                self.counting(self.hold(), executed)

                self.assertEqual(executed, ["git_push"] if window is None else [])
                self.assertPublishedExactly(self.made(pending))
                self.assertEqual(self.head(), self.remote_head())
                self.assertFinished(pending)

    def test_a_later_commit_that_is_not_on_the_recorded_branch(self) -> None:
        moves = {
            "on another branch, HEAD back on main": ("side", True),
            "on the recorded branch, HEAD on another branch holding the commit": ("main", False),
        }
        for index, (label, (onto, back)) in enumerate(moves.items()):
            with self.subTest(case=label):
                self.build(f"branch-{index}")
                pending = self.interrupt(self.hold(), HOLD, "committed")
                made = self.made(pending)
                git(self.root, "branch", "side")
                if onto == "side":
                    git(self.root, "checkout", "-q", "side")
                later = self.person("H1")
                git(self.root, "checkout", "-q", "main" if back else "side")

                self.assertEqual(self.hold()().status, "phase_held")

                self.assertPublishedExactly(made, later)
                self.assertNotIn("refs/heads/side", self.remote_refs())
                self.assertFinished(pending)

    def test_an_uncommitted_change_and_a_change_to_the_owned_path(self) -> None:
        with self.subTest(case="an uncommitted change only"):
            self.build("dirty")
            pending = self.interrupt(self.hold(), HOLD, "committed")
            (self.root / "notes.md").write_text("notes\nnot committed\n", encoding="utf-8")

            self.hold()()

            self.assertPublishedExactly(self.made(pending))
            self.assertEqual(self.dirty(), [" M notes.md"])
        with self.subTest(case="a later commit of the event log the operation committed"):
            self.build("owned")
            pending = self.interrupt(self.hold(), HOLD, "committed")
            later = self.person("H1", EVENT_LOG)

            self.hold()()

            self.assertPublishedExactly(self.made(pending), later)
            self.assertFinished(pending)


# --------------------------------------------------------------------------- where the commit stands at the destination
class DestinationTests(PublicationCase):
    def test_a_destination_that_has_moved_on_past_the_commit_is_published_already(self) -> None:
        cases = {"a person pushed their own commit on top": "person", "another clone pushed on top": "clone"}
        for index, (label, who) in enumerate(cases.items()):
            with self.subTest(case=label):
                self.build(f"past-{index}")
                pending = self.interrupt(self.hold(), HOLD, "committed")
                made = self.made(pending)
                if who == "person":
                    tip = self.person("H1")
                    git(self.root, "push", "-q", "origin", "main:main")  # the person publishes it, not Workline
                else:
                    git(self.root, "push", "-q", "origin", f"{made}:refs/heads/main")
                    self.push_from_another_clone()
                    tip = git(self.remote, "rev-parse", "main").strip()
                    self.assertNotEqual(git(self.root, "cat-file", "-t", tip, check=False).strip(), "commit")
                local_refs, head = self.local_refs(), self.head()
                executed: list[str] = []

                self.assertEqual(self.counting(self.hold(), executed).status, "phase_held")

                self.assertEqual(executed, [])
                self.assertEqual(self.remote_head(), tip)  # left where it is, nothing rewound
                self.assertTrue(self.published(made))
                # the destination was only read: no ref, no FETCH_HEAD, the branch and the tree as they were
                self.assertEqual((self.local_refs(), self.head()), (local_refs, head))
                self.assertFalse((self.root / ".git" / "FETCH_HEAD").exists())
                self.assertFinished(pending)

    def test_a_destination_holding_another_history_stops(self) -> None:
        for index, onto in enumerate(("base", None)):
            with self.subTest(history="diverged from the base" if onto else "unrelated"):
                self.build(f"diverged-{index}")
                pending = self.interrupt(self.hold(), HOLD, "committed")
                base = pending["effects"][1]["payload"]["base_head"]
                elsewhere = self.remote_moves_to_its_own("elsewhere", onto=base if onto else None)

                self.assertRefusedUntouched(self.hold(), "a history that does not hold")

                self.assertEqual(self.remote_head(), elsewhere)
                self.assertFalse(self.published(self.made(pending)))

    def test_a_destination_without_the_branch_gets_it_at_the_commit(self) -> None:
        self.build("absent")
        pending = self.interrupt(self.hold(), HOLD, "committed")
        made = self.made(pending)
        later = self.person("H1")
        git(self.remote, "update-ref", "-d", "refs/heads/main")

        self.assertEqual(self.hold()().status, "phase_held")

        self.assertPublishedExactly(made, later)
        self.assertFinished(pending)

    def test_reading_the_destination_brings_its_history_and_nothing_else(self) -> None:
        """Whatever the repository configures a fetch to do besides: Git takes a locator that is also one of its remote
        names for that remote, whose fetch refspecs would move a remote-tracking ref, and ``fetch.bundleURI`` would
        first fetch a bundle from elsewhere into refs/bundles."""
        repo, other = self.tmp / "named", self.tmp / "named-other"
        git(self.tmp, "init", "-q", "-b", "main", str(repo))
        (repo / "a.md").write_text("a\n", encoding="utf-8")
        git(repo, "add", "a.md")
        git(repo, "commit", "-q", "-m", "docs: a")
        git(repo, "init", "-q", "--bare", "-b", "main", "dest")  # the locator "dest", read from the repository's root
        git(repo, "remote", "add", "dest", "dest")  # and a remote of that name, fetching into refs/remotes/dest/*
        git(repo, "push", "-q", "dest", "main:refs/heads/main")
        git(self.tmp, "clone", "-q", str(repo / "dest"), str(other))
        (other / "b.md").write_text("b\n", encoding="utf-8")
        git(other, "add", "b.md")
        git(other, "commit", "-q", "-m", "docs: b, pushed from another clone")
        git(other, "push", "-q", "origin", "main:main")
        bundle = self.tmp / "named.bundle"
        git(repo / "dest", "bundle", "create", bundle.as_posix(), "main")
        git(repo, "config", "fetch.bundleURI", bundle.as_posix())
        state = lambda: (git(repo, "for-each-ref", "--format=%(refname) %(objectname)"),  # noqa: E731
                         git(repo, "config", "--local", "--list"), (repo / ".git" / "FETCH_HEAD").exists())
        before = state()
        self.assertIn("refs/remotes/dest/main", before[0])
        self.assertTrue(gitcmd.reads_itself(repo, "dest"))

        tip = gitcmd.destination_branch(repo, "dest", "refs/heads/main")
        gitcmd.fetch_destination_branch(repo, "dest", "refs/heads/main")

        self.assertEqual(tip, git(other, "rev-parse", "HEAD").strip())
        self.assertIs(gitcmd.descends_from(repo, tip, git(repo, "rev-parse", "main").strip()), True)
        self.assertEqual(state(), before)


# --------------------------------------------------------------------------- the recoveries around it are unchanged
class RecoveryTests(PublicationCase):
    def test_a_commit_made_on_top_of_a_later_commit_publishes_it_as_its_history(self) -> None:
        """BL-032: the commit not made yet is made on top of the person's commit, and publishing it publishes both."""
        for index, window in enumerate(("commit recorded", "before the Git stage")):
            with self.subTest(window=window):
                self.build(f"ancestor-{index}")
                pending = (self.interrupt(self.hold(), HOLD, "commit recorded") if window == "commit recorded"
                           else self.stop(after_applying(r"^event$"), self.hold()))
                earlier = self.person("H1")

                self.assertEqual(self.hold()().status, "phase_held")

                made = self.made(pending)
                self.assertEqual(self.parent(made), earlier)
                self.assertEqual(self.remote_head(), made)
                self.assertTrue(self.published(earlier))
                self.assertFinished(pending)

    def test_the_branch_checks_still_stop_first(self) -> None:
        """BL-036 (decided, commit not recorded) and BL-038 (committed) on a branch that does not hold them."""
        cases = {"decided": (lambda: self.stop(after_applying(r"^event$"), self.hold()), "no recorded commit finalizes"),
                 "committed": (lambda: self.interrupt(self.hold(), HOLD, "committed"), "whose working tree does not hold")}
        for index, (label, (stop, fragment)) in enumerate(cases.items()):
            with self.subTest(window=label):
                self.build(f"branch-{index}")
                base = self.head()
                pending = stop()
                git(self.root, "checkout", "-q", "-b", "side", base)
                self.person("H1")

                self.assertRefusedUntouched(self.hold(), fragment)

                git(self.root, "checkout", "-q", "main")
                later = self.person("H2")
                self.assertEqual(self.hold()().status, "phase_held")
                made = self.made(pending)
                if label == "committed":
                    self.assertPublishedExactly(made, later)
                else:  # decided before H2, committed after it, on top of it (BL-036 / BL-032)
                    self.assertEqual((self.parent(made), self.remote_head()), (later, made))
                self.assertFinished(pending)

    def test_a_commit_no_longer_held_stops_before_its_push(self) -> None:
        """BL-037: an amended commit is not the one recorded; nothing is pushed, back on it the push is made."""
        self.build("amended")
        pending = self.interrupt(self.hold(), HOLD, "committed")
        made = self.made(pending)
        git(self.root, "commit", "-q", "--amend", "--only", "-m", "chore: reworded")

        self.assertRefusedUntouched(self.hold(), "applied with unexpected result")

        git(self.root, "reset", "-q", "--hard", made)
        self.assertEqual(self.hold()().status, "phase_held")
        self.assertPublishedExactly(made)

    def test_a_foreign_change_refused_after_an_earlier_push_publishes_nothing(self) -> None:
        """BL-043 refuses the completion; the results push before it has nothing more to publish, retry after retry."""
        self.build("foreign")
        call = lambda: st.start(self.store, self.w1, "single-work", completing_executor(self.store))  # noqa: E731
        pending = self.stop(after_recording(rf"^{self.w1}:lifecycle:1$"), call)
        results = self.made(pending, rf"^{self.w1}:results:0$")
        self.assertEqual(self.remote_head(), results)
        first = self.person("H1")
        held = (self.root / EVENT_LOG).read_bytes()
        (self.root / EVENT_LOG).write_bytes(held + b"\n")  # a byte another subject wrote into the event log

        refused = self.assertRefusedUntouched(call, "no longer holds what this operation left there")

        self.assertIn("nothing is written, committed or pushed", refused.message)
        second = self.person("H2")
        self.assertRefusedUntouched(call, "no longer holds what this operation left there")
        self.assertPublishedExactly(results, first, second)
        (self.root / EVENT_LOG).write_bytes(held)
        self.assertEqual(call().status, "completed")
        self.assertEqual(self.remote_head(), self.head())  # the finalization, decided on main and made on top of H2
        self.assertFinished(pending)


# --------------------------------------------------------------------------- a push that cannot name its commit is not made
class UnnamedCommitTests(PublicationCase):
    def test_a_record_that_does_not_name_the_commit_stops(self) -> None:
        def commit_id(value):
            return lambda record: record["effects"][1].update(commit_id=value) if value is not None else record["effects"][1].pop("commit_id")

        def later_commit(record):
            record["effects"][1]["commit_id"] = self.head()

        def base_commit(record):
            record["effects"][1]["commit_id"] = record["effects"][1]["payload"]["base_head"]

        # an ID Git cannot even take for a commit ID is refused where BL-037 refuses it, at the commit; every other
        # record reaches the push, which names no commit for it
        at_the_commit = "applied with unexpected result"
        changes = {
            "no commit_id (recorded before IDs)": (commit_id(None), UNNAMED),
            "abbreviated": (lambda record: record["effects"][1].update(commit_id=record["effects"][1]["commit_id"][:12]),
                            at_the_commit),
            "upper case": (lambda record: record["effects"][1].update(commit_id=record["effects"][1]["commit_id"].upper()),
                           at_the_commit),
            "not hex": (commit_id("z" * 40), at_the_commit),
            "not text": (commit_id(5), at_the_commit),
            "a later commit on the branch": (later_commit, UNNAMED),
            "its base": (base_commit, UNNAMED),
            "the push names another branch": (lambda record: record["effects"][2]["payload"].update(branch="side"), UNNAMED),
            "the push recorded in another stage": (lambda record: record["effects"][2].update(stage="push"), UNNAMED),
            "the push not next to its commit": (lambda record: record["effects"][2].update(seq=5), UNNAMED),
            "the commit without its branch": (lambda record: record["effects"][1]["payload"].pop("branch"), UNNAMED),
        }
        for index, (label, (change, fragment)) in enumerate(changes.items()):
            with self.subTest(record=label):
                self.build(f"unnamed-{index}")
                pending = self.interrupt(self.hold(), HOLD, "committed")
                base = self.remote_head()
                self.person("H1")
                self.edit_record(pending, change)

                self.assertRefusedUntouched(self.hold(), fragment)

                self.assertEqual(self.remote_head(), base)

    def test_a_push_recorded_for_another_destination_stops_before_anything_is_read(self) -> None:
        """The destination is confirmed before the commit is looked for at all, as it always was."""
        changes = {
            "another remote": (lambda record: record["effects"][2]["payload"].update(remote="upstream"),
                               "is not the Project's pinned remote"),
            "another locator": (lambda record: record["effects"][2]["payload"].update(locator=str(self.tmp / "elsewhere.git")),
                                "is no longer an approved destination"),
        }
        for index, (label, (change, fragment)) in enumerate(changes.items()):
            with self.subTest(payload=label):
                self.build(f"destination-{index}")
                pending = self.interrupt(self.hold(), HOLD, "committed")
                base = self.remote_head()
                self.person("H1")
                self.edit_record(pending, change)

                self.assertRefusedUntouched(self.hold(), fragment)

                self.assertEqual(self.remote_head(), base)

    def test_a_commit_whose_id_was_never_saved_stops_before_its_push(self) -> None:
        """L1: made just before the process died, or followed by a commit a hook made; nothing names it, nothing is pushed."""
        with self.subTest(case="made, its flag and ID not saved"):
            self.build("never-saved")
            pending = self.stop(committed_before_its_flag(HOLD), self.hold())
            base = self.remote_head()

            with self.assertRaises(StopError) as refused:
                self.hold()()

            self.assertEqual(refused.exception.code, "reconcile_required")
            self.assertIn(UNNAMED, refused.exception.message)
            self.assertEqual(self.remote_head(), base)
            self.assertEqual(self.pending_ids(), [pending["mutation_id"]])
        with self.subTest(case="a post-commit hook commits again"):
            self.build("hooked")
            hook = self.root / ".git" / "hooks" / "post-commit"
            hook.write_text(EXTRA_COMMIT_HOOK, encoding="utf-8", newline="\n")
            os.chmod(hook, 0o755)
            (self.root / ".git" / "workline-test-extra-commit").write_text("once\n", encoding="utf-8")
            base = self.remote_head()

            with self.assertRaises(StopError) as refused:
                self.hold()()

            self.assertEqual(refused.exception.code, "reconcile_required")
            self.assertIn(UNNAMED, refused.exception.message)
            self.assertEqual(self.remote_head(), base)


if __name__ == "__main__":
    unittest.main()
