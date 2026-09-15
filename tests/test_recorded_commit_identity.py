"""A commit a mutation made is recognized by the ID of that commit, not by the message Git stored (BL-037).

Every operation records its commit - message, paths, base and branch - before it makes it, and every later
apply classifies the recorded effects again: on a resume, and after each later stage of the same mutation.
A commit the record held as applied was recognized only by some commit since its base carrying the recorded
message. Git does not store that message as it was handed over: its cleanup drops trailing whitespace from
every line, turns CRLF into LF and folds runs of blank lines, and a ``commit-msg`` or ``prepare-commit-msg``
hook can add a trailer or a prefix. Once a later stage - the next Work of an outer START, the executor
before a question, a person - dirtied the commit's paths again, nothing recognized the commit as the
mutation's own: ``applied with unexpected result``, ``reconcile required`` on every retry, and every
operation sharing the ledger stopped behind the pending record, with nothing wrong in the Project.

The commit made is now recorded with its ID, in the same save that records it applied, and on the branch it
was recorded on that ID alone decides: HEAD's history holding it is a match, a history that no longer holds
it is not - never taken back to the message. Off that branch, and for a record without an ID (made just
before an interruption kept it from being saved, or recorded before IDs were), the commit is classified as
it always was. A commit someone else made never gets an ID: only the commit the Mutation Controller has just
made on top of the HEAD it started from does.
"""

from __future__ import annotations

import os
import re
import subprocess
import unittest
from unittest import mock

from helpers import git
from test_bootstrap_backfill_resume import BackfillCase
from test_recorded_commit_message import MessageCase, committed_before_its_flag, pushed_before_completion
from test_recorded_commit_resume import EVENT_LOG, MAIN, Interrupted, before_push
from workline import bootstrap as bs
from workline import gitcmd
from workline import start as st
from workline import yamlish
from workline.errors import StopError
from workline.mutation import Mutation, MutationController
from workline.store import BOOTSTRAP_REL_PATH
from workline.validate import validate_project

MADE = "commit_id"
WHITESPACE_MESSAGE = "docs: record the W1 result   \n\n\nwith a body line  \n"
CRLF_MESSAGE = "docs: record the W1 result\r\n\r\nwith a body line\r\n"
LONE_CR_MESSAGE = "docs: record\rthe W1 result"
CHANGE_ID_HOOK = r"""#!/bin/sh
# commit-msg: add a Change-Id trailer the way Gerrit's hook does
id="I$(git hash-object -t blob "$1")"
git interpret-trailers --in-place --if-exists doNothing --trailer "Change-Id: $id" "$1"
"""
BRANCH_PREFIX_HOOK = r"""#!/bin/sh
# prepare-commit-msg: prefix the subject with the branch it is committed on
branch=$(git symbolic-ref --short HEAD 2>/dev/null)
sed -i "1s|^|[$branch] |" "$1"
"""
EXTRA_COMMIT_FLAG = "workline-test-extra-commit"
EXTRA_COMMIT_HOOK = f"""#!/bin/sh
# post-commit: once, commit again right after the commit that ran the hook
flag="$(git rev-parse --git-dir)/{EXTRA_COMMIT_FLAG}"
if [ -f "$flag" ]; then
  rm -f "$flag"
  git commit -q --allow-empty -m "chore: made by a post-commit hook"
fi
exit 0
"""


class IdentityCase(MessageCase):
    def hook(self, name: str, script: str) -> None:
        path = self.root / ".git" / "hooks" / name
        path.write_text(script, encoding="utf-8", newline="\n")
        os.chmod(path, 0o755)

    def stored_message(self, commit: str) -> str:
        """The message the commit object holds, byte for byte (no newline translation)."""
        raw = subprocess.run(["git", "-C", str(self.root), "cat-file", "commit", commit], capture_output=True, check=True).stdout
        return raw.split(b"\n\n", 1)[1].decode("utf-8")

    def recorded_effect(self, pending: dict, pattern: str = ".") -> dict:
        (effect,) = [e for e in pending["effects"] if e["kind"] == "git_commit" and re.search(pattern, e["stage"])]
        return effect

    def pending_record(self, mutation_id: str) -> dict:
        (record,) = [r for r in MutationController(self.store).list_pending() if r["mutation_id"] == mutation_id]
        return record

    def retry_until_pushing(self, call, pattern: str, mutation_id: str) -> dict:
        """Run the retry of a pending mutation until the push of the stage matching ``pattern``; return its record."""
        with before_push(pattern), self.assertRaises(Interrupted):
            call()
        return self.pending_record(mutation_id)

    def edit_record(self, pending: dict, change) -> None:
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        change(record)
        path.write_text(yamlish.dump(record), encoding="utf-8")

    def outer(self, w1_message: str, *, w2_edits_w1: bool, question: bool = False, move_second_to: str | None = None):
        """Outer START over W1, W2 and the integration; W1 finishes with its own result message."""
        asked: list[str] = []

        def execute(ctx):
            own = f"result_{ctx.work.display}.txt"
            if ctx.work.id == self.w2 and move_second_to and self.on() != f"refs/heads/{move_second_to}":
                git(self.root, "checkout", "-q", "-b", move_second_to)
            if ctx.work.id == self.w2 and question and not asked:
                asked.append(ctx.work.id)
                if w2_edits_w1:
                    self.append("result_W-01.txt", "W2 is reading and annotating this\n")
                return st.QuestionWait("which way?")
            (self.root / own).write_text(f"{ctx.work.name}\n", encoding="utf-8")
            if ctx.work.id == self.w1:
                return st.Completed((own,), w1_message)
            if ctx.work.id == self.w2 and w2_edits_w1:
                if not question:
                    self.append("result_W-01.txt", "W2 extends the W1 result\n")
                return st.Completed((own, "result_W-01.txt"), "docs: W2 extends the W1 result")
            return st.Completed((own,))

        return lambda: st.start(self.store, self.w1, "outer", execute)

    def results(self, message: str):
        """A single-work START whose Work finishes with one result file and ``message``."""
        def execute(ctx):
            (self.root / "result_W-01.txt").write_text(f"{ctx.work.name}\n", encoding="utf-8")
            return st.Completed(("result_W-01.txt",), message)

        return lambda: st.start(self.store, self.w1, "single-work", execute), rf"^{self.w1}:results:0$"

    def append(self, path: str, text: str) -> None:
        target = self.root / path
        target.write_text(target.read_text(encoding="utf-8") + text, encoding="utf-8", newline="\n")

    def assertOnlyLeftOver(self, dirty: list[str]) -> None:
        self.assertEqual(self.pending_ids(), [])
        self.assertEqual(self.dirty(), dirty)
        self.assertEqual(self.head(), self.remote_head())


# --------------------------------------------------------------------------- the reproduction: its own commit
class OwnCommitTests(IdentityCase):
    def test_an_outer_start_goes_on_over_the_message_git_stored_for_its_result(self) -> None:
        """The next Work edits the result file; the result commit is recognized whatever message Git stored."""
        for index, message in enumerate((WHITESPACE_MESSAGE, CRLF_MESSAGE, LONE_CR_MESSAGE)):
            with self.subTest(message=message):
                self.build(f"outer-{index}")

                result = self.outer(message, w2_edits_w1=True)()

                self.assertEqual((result.status, result.completed_work_ids), ("phase_complete", (self.w1, self.w2, self.integration)))
                (made,) = git(self.root, "rev-list", "HEAD", "--", "result_W-01.txt").split()[-1:]
                # what used to stop it: the message as Workline reads it back is not the one it recorded (a lone CR
                # is stored as given and only read back as a line break)
                read_back = gitcmd.run_git(self.root, "log", "-1", "--format=%B", made).stdout
                self.assertNotEqual(read_back.strip(), message.strip())
                self.assertEqual(self.head(), self.remote_head())
                self.assertNothingLeftOver()

    def test_a_hook_that_rewrites_every_message(self) -> None:
        """Workline's own messages change too, so the next Work's lifecycle events alone used to stop it."""
        hooks = {"commit-msg trailer": ("commit-msg", CHANGE_ID_HOOK, "\n\nChange-Id: I"),
                 "prepare-commit-msg prefix": ("prepare-commit-msg", BRANCH_PREFIX_HOOK, "[main] ")}
        for index, (label, (name, script, mark)) in enumerate(hooks.items()):
            with self.subTest(hook=label, flow="outer, no shared file"):
                self.build(f"hook-outer-{index}")
                self.hook(name, script)

                result = self.outer("docs: record the W1 result", w2_edits_w1=False)()

                self.assertEqual(result.status, "phase_complete")
                self.assertIn(mark, self.stored_message(self.head()))
                self.assertNothingLeftOver()
        with self.subTest(hook="commit-msg trailer", flow="single-work, derived and continued"):
            self.build("hook-derive")
            self.hook("commit-msg", CHANGE_ID_HOOK)
            ran: list[str] = []

            def execute(ctx):
                ran.append(ctx.work.id)
                if len(ran) == 1:
                    return st.Derive({"d": st.DerivedWork("Derived D", "d is done")})
                (self.root / "result_W-01.txt").write_text("W1\n", encoding="utf-8")
                return st.Completed(("result_W-01.txt",))

            self.assertEqual(st.start(self.store, self.w1, "single-work", execute).status, "completed")
            self.assertNothingLeftOver()

    def test_an_outer_question_wait_resumes_over_the_message_git_stored(self) -> None:
        self.build("question")
        call = self.outer(CRLF_MESSAGE, w2_edits_w1=True, question=True)
        self.assertEqual(call().status, "question_wait")

        result = call()

        self.assertEqual(result.status, "phase_complete")
        self.assertNothingLeftOver()

    def test_a_committed_commit_resumes_over_a_rewritten_message(self) -> None:
        """Committed and not pushed, or pushed and not completed, and the committed paths edited again by a person."""
        cases = {
            ("phase hold", "committed"): ["git_push"],
            ("phase hold", "pushed"): [],
            ("start finalization", "committed"): ["git_push"],
            ("start finalization", "pushed"): [],
        }
        for index, ((operation, window), expected) in enumerate(cases.items()):
            with self.subTest(operation=operation, window=window):
                self.build(f"committed-{index}")
                self.hook("commit-msg", CHANGE_ID_HOOK)
                call, pattern = self.operation(operation)
                pending = (self.interrupt(call, pattern, "committed") if window == "committed"
                           else self.interrupt_with(call, pushed_before_completion()))
                effect = self.recorded_effect(pending, pattern)
                self.assertIn("Change-Id: I", self.stored_message(effect[MADE]))
                self.append(EVENT_LOG, "\n")
                executed: list[str] = []

                self.counting(call, executed)

                self.assertEqual(executed, expected)
                self.assertOnlyLeftOver([f" M {EVENT_LOG}"])


# --------------------------------------------------------------------------- what is recorded, and when
class RecordTests(IdentityCase):
    def test_the_commit_made_is_recorded_with_its_applied_flag(self) -> None:
        self.build("record")
        call, pattern = self.operation("phase hold")

        pending = self.interrupt(call, pattern, "committed")

        effect = self.recorded_effect(pending, pattern)
        self.assertEqual((effect["applied"], effect[MADE]), (True, self.head()))
        self.assertEqual(self.parent(effect[MADE]), effect["payload"]["base_head"])
        self.assertNotIn(MADE, effect["payload"])
        self.assertEqual([MADE in e for e in pending["effects"]], [e is effect for e in pending["effects"]])
        text = MutationController(self.store).intent_path(pending["mutation_id"]).read_text(encoding="utf-8")
        self.assertIn(f"{MADE}: {self.head()}", text)

    def test_a_commit_made_before_its_flag_was_saved_gets_no_id(self) -> None:
        """Saved neither with the flag nor after it: the retry did not make that commit, so it cannot name it."""
        self.build("w2")
        call, pattern = self.operation("phase hold")
        pending = self.interrupt_with(call, committed_before_its_flag(pattern))
        effect = self.recorded_effect(pending, pattern)
        self.assertEqual((effect["applied"], MADE in effect), (False, False))

        again = self.retry_until_pushing(call, pattern, pending["mutation_id"])

        effect = self.recorded_effect(again, pattern)
        self.assertEqual((effect["applied"], MADE in effect), (True, False))
        self.assertEqual(call().status, "phase_held")
        self.assertNothingLeftOver()

    def test_a_commit_git_does_not_show_as_the_one_made_gets_no_id(self) -> None:
        cases = {
            "a post-commit hook commits again": lambda: (self.root / ".git" / EXTRA_COMMIT_FLAG).write_text("once\n", encoding="utf-8"),
            "Git cannot name the parents": None,
        }
        for index, (label, arm) in enumerate(cases.items()):
            with self.subTest(case=label):
                self.build(f"unshown-{index}")
                call, pattern = self.operation("phase hold")
                if arm is not None:
                    self.hook("post-commit", EXTRA_COMMIT_HOOK)
                    arm()
                    pending = self.interrupt(call, pattern, "committed")
                else:
                    with mock.patch.object(gitcmd, "commit_parents", return_value=None):
                        pending = self.interrupt(call, pattern, "committed")

                effect = self.recorded_effect(pending, pattern)
                self.assertEqual((effect["applied"], MADE in effect), (True, False))
                self.assertEqual(call().status, "phase_held")


# --------------------------------------------------------------------------- the ID is the identity: no way back to the message
class UnreachableTests(IdentityCase):
    def test_a_history_that_no_longer_holds_the_commit_made_stops(self) -> None:
        """A refusal the message rule did not make: each of these used to be taken for the recorded commit."""
        rewrites = {
            "amended with another message": lambda m: git(self.root, "commit", "-q", "--amend", "--only", "-m", "chore: reworded"),
            "amended keeping its message": lambda m: git(self.root, "commit", "-q", "--amend", "--only", "--no-edit",
                                                         "--date", "2001-01-01T00:00:00"),
            "reset, and committed again with its message": lambda m: (git(self.root, "reset", "-q", "--soft", "HEAD~1"),
                                                                        git(self.root, "commit", "-q", "-m", m)),
            "reset, the change left staged": lambda m: git(self.root, "reset", "-q", "--soft", "HEAD~1"),
        }
        for index, (label, rewrite) in enumerate(rewrites.items()):
            with self.subTest(rewrite=label):
                self.build(f"rewrite-{index}")
                call, pattern = self.operation("phase hold")
                pending = self.interrupt(call, pattern, "committed")
                effect = self.recorded_effect(pending, pattern)
                rewrite(effect["payload"]["message"])
                self.assertNotIn(effect[MADE], git(self.root, "rev-list", "HEAD").split())

                self.assertStopsUntouched(call)

                git(self.root, "reset", "-q", "--hard", effect[MADE])
                self.assertEqual(call().status, "phase_held")  # back on the commit it made, the same retry goes on
                self.assertNothingLeftOver()

    def test_a_question_git_cannot_answer_stops(self) -> None:
        self.build("unanswered")
        call, pattern = self.operation("phase hold")
        self.interrupt(call, pattern, "committed")

        with mock.patch.object(gitcmd, "descends_from", return_value=None):
            self.assertStopsUntouched(call)


# --------------------------------------------------------------------------- the ID proves nothing off the branch it was recorded on
class BranchTests(IdentityCase):
    def test_on_another_branch_the_commit_made_is_classified_as_a_commit_without_its_id(self) -> None:
        self.build("side")
        call, pattern = self.results(WHITESPACE_MESSAGE)
        pending = self.interrupt(call, pattern, "committed")
        effect = self.recorded_effect(pending, pattern)
        git(self.root, "checkout", "-q", "-b", "side")  # it holds the commit made, and HEAD reaches it
        self.append("result_W-01.txt", "a person's follow-up\n")

        self.assertStopsUntouched(call)

        git(self.root, "checkout", "-q", "main")
        self.assertEqual(call().status, "completed")
        self.assertEqual(self.on(), MAIN)
        self.assertIn(effect[MADE], git(self.root, "rev-list", "HEAD").split())
        self.assertNothingLeftOver()


# --------------------------------------------------------------------------- someone else's commit never gets the ID (BL-033)
class SameMessageTests(IdentityCase):
    def test_a_commit_sharing_the_recorded_message_gets_no_id_and_stands_in_for_nothing(self) -> None:
        with self.subTest(case="unrelated paths under the recorded message"):
            self.build("same-unrelated")
            call, pattern = self.results(WHITESPACE_MESSAGE)
            pending = self.interrupt(call, pattern, "commit refused")
            foreign = self.same_message_commit(WHITESPACE_MESSAGE)

            again = self.retry_until_pushing(call, pattern, pending["mutation_id"])

            made = self.recorded_effect(again, pattern)[MADE]
            self.assertNotEqual(made, foreign)
            self.assertEqual(self.parent(made), foreign)  # its own commit, made on top (BL-032)
            self.assertEqual(call().status, "completed")
            self.assertNothingLeftOver()
        with self.subTest(case="the recorded paths with other content under the recorded message"):
            self.build("same-other-content")
            call, pattern = self.results(WHITESPACE_MESSAGE)
            self.interrupt(call, pattern, "commit recorded")
            (self.root / "result_W-01.txt").write_text("someone else's result\n", encoding="utf-8")
            git(self.root, "add", "--", "result_W-01.txt")
            git(self.root, "commit", "-q", "-m", WHITESPACE_MESSAGE, "--", "result_W-01.txt")
            (self.root / "result_W-01.txt").write_text("W1\n", encoding="utf-8")

            self.assertStopsUntouched(call)
        with self.subTest(case="its commit made before its flag, a same-message commit after it, its paths edited"):
            self.build("same-before-flag")
            call, pattern = self.operation("phase hold")
            pending = self.interrupt_with(call, committed_before_its_flag(pattern))
            self.same_message_commit(self.recorded_commit(pending)["message"])
            self.append(EVENT_LOG, "\n")

            self.assertStopsUntouched(call)  # BL-033 D-1: nothing durable shows it is this mutation's own


# --------------------------------------------------------------------------- records without an ID keep today's contract
class LegacyTests(IdentityCase):
    def test_a_record_without_an_id_is_classified_as_before(self) -> None:
        drop = lambda record: [effect.pop(MADE, None) for effect in record["effects"]]  # noqa: E731
        with self.subTest(case="its message, its paths edited again"):
            self.build("legacy-message")
            call, pattern = self.operation("phase hold")
            pending = self.interrupt(call, pattern, "committed")
            self.edit_record(pending, drop)
            self.append(EVENT_LOG, "\n")

            self.assertEqual(call().status, "phase_held")
            self.assertOnlyLeftOver([f" M {EVENT_LOG}"])
        with self.subTest(case="a message a hook rewrote, its paths edited again"):
            self.build("legacy-hook")
            self.hook("commit-msg", CHANGE_ID_HOOK)
            call, pattern = self.operation("phase hold")
            pending = self.interrupt(call, pattern, "committed")
            self.edit_record(pending, drop)
            self.append(EVENT_LOG, "\n")

            self.assertStopsUntouched(call)  # no message is taken for it because it looks alike
        with self.subTest(case="amended keeping its message"):
            self.build("legacy-amend")
            call, pattern = self.operation("phase hold")
            pending = self.interrupt(call, pattern, "committed")
            self.edit_record(pending, drop)
            git(self.root, "commit", "-q", "--amend", "--only", "--no-edit", "--date", "2001-01-01T00:00:00")

            self.assertEqual(call().status, "phase_held")
            self.assertNothingLeftOver()


# --------------------------------------------------------------------------- the windows before the commit is made
class EarlierWindowTests(IdentityCase):
    def test_a_commit_made_over_an_independent_commit_records_that_commit(self) -> None:
        """BL-032: the recorded commit is made on top of an independent commit, and that commit is the one named."""
        self.build("independent")
        call, pattern = self.operation("phase hold")
        pending = self.interrupt(call, pattern, "commit recorded")
        self.assertNotIn(MADE, self.recorded_effect(pending, pattern))
        independent = self.human_commit({"notes.md": "notes\nby a person\n"}, "docs: a note")

        again = self.retry_until_pushing(call, pattern, pending["mutation_id"])

        made = self.recorded_effect(again, pattern)[MADE]
        self.assertEqual((made, self.parent(made)), (self.head(), independent))
        self.assertEqual(call().status, "phase_held")
        self.assertNothingLeftOver()

    def test_another_branch_at_the_base_still_stops_before_the_commit(self) -> None:
        """BL-035: nothing is made, so nothing is named; back on its branch the commit made is named."""
        self.build("base-side")
        call, pattern = self.operation("phase hold")
        pending = self.interrupt(call, pattern, "commit recorded")
        git(self.root, "checkout", "-q", "-b", "side")

        self.assertStopsUntouched(call)
        self.assertNotIn(MADE, self.recorded_effect(self.pending_record(pending["mutation_id"]), pattern))

        git(self.root, "checkout", "-q", "main")
        again = self.retry_until_pushing(call, pattern, pending["mutation_id"])
        self.assertEqual(self.recorded_effect(again, pattern)[MADE], self.head())
        self.assertEqual(call().status, "phase_held")


# --------------------------------------------------------------------------- bootstrap backfill (BL-034)
class BackfillIdentityTests(BackfillCase):
    def hook(self, name: str, script: str) -> None:
        path = self.root / ".git" / "hooks" / name
        path.write_text(script, encoding="utf-8", newline="\n")
        os.chmod(path, 0o755)

    def assertCreatedOnce(self, pending: dict, result, executed: list[str], expected: list[str]) -> None:
        self.assertEqual((result.status, result.mutation_id, result.resumed), ("created", pending["mutation_id"], True))
        self.assertEqual(executed, expected)
        self.assertEqual(MutationController(self.store).list_pending(), [])
        commits = git(self.root, "rev-list", f"{self.legacy}..HEAD", "--", BOOTSTRAP_REL_PATH).split()
        self.assertEqual(len(commits), 1, commits)
        self.assertEqual(git(self.root, "show", "--name-only", "--format=", commits[0]).split(), [BOOTSTRAP_REL_PATH])
        self.assertEqual((self.remote_head(), self.dirty(), validate_project(self.store)), (self.head(), [], []))

    def test_a_backfill_recognizes_the_commit_it_made_under_a_rewriting_hook(self) -> None:
        for index, (window, expected) in enumerate((("push refused", ["git_push"]), ("pushed", []), ("not completed", []))):
            with self.subTest(window=window):
                self.build(f"backfill-hook-{index}")
                self.hook("commit-msg", CHANGE_ID_HOOK)
                pending = self.interrupt(window)
                (commit,) = [e for e in pending["effects"] if e["kind"] == "git_commit"]
                self.assertIn("Change-Id: I", git(self.root, "log", "-1", "--format=%B", commit[MADE]))
                executed: list[str] = []

                result = self.retry(executed)

                self.assertCreatedOnce(pending, result, executed, expected)

    def test_a_backfill_commit_the_history_no_longer_holds_stops(self) -> None:
        self.build("backfill-amended")
        self.interrupt("push refused")
        git(self.root, "commit", "-q", "--amend", "--only", "--no-edit", "--date", "2001-01-01T00:00:00")
        self.assertEqual(git(self.root, "log", "-1", "--format=%B").strip(), bs.BACKFILL_COMMIT_MESSAGE)

        self.assertStopsUntouched("not changed by that one commit alone")

    def test_a_commit_id_in_another_form_stops(self) -> None:
        def set_id(value, applied=None):
            def change(record):
                (commit,) = [e for e in record["effects"] if e["kind"] == "git_commit"]
                commit[MADE] = value
                if applied is not None:
                    commit["applied"] = applied
            return change

        cases = {
            "not a commit ID": ("push refused", set_id("HEAD")),
            "on a commit it has not made": ("commit refused", set_id("0" * 40)),
        }
        for index, (label, (window, change)) in enumerate(cases.items()):
            with self.subTest(case=label):
                self.build(f"backfill-form-{index}")
                pending = self.interrupt(window)
                self.edit_record(pending, change)

                self.assertStopsUntouched("records the commit it made in another form")


# --------------------------------------------------------------------------- residual pinned, not fixed here
class KnownResidualTests(IdentityCase):
    def test_an_executor_that_moves_branch_under_a_rewriting_hook_still_stops(self) -> None:
        """Off the branch a commit was recorded on its ID is not used, so this is classified as before BL-037."""
        self.build("moves")
        self.hook("commit-msg", CHANGE_ID_HOOK)
        call = self.outer("docs: record the W1 result", w2_edits_w1=False, move_second_to="feature")

        with self.assertRaises(StopError) as stopped:
            call()

        self.assertEqual(stopped.exception.code, "reconcile_required")
        self.assertIn("(git_commit) applied with unexpected result", stopped.exception.message)
        self.assertEqual(self.on(), "refs/heads/feature")


if __name__ == "__main__":
    unittest.main()
