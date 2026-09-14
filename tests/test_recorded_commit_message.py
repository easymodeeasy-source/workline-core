"""A commit carrying the recorded message is not taken for the recorded commit unless the record holds it as applied (BL-033).

Every operation records its commit - the message, the paths it owns, the HEAD it was decided on and the
branch - before it makes it, and an operation interrupted in between, or whose commit failed, resumes from
that Git stage (``rules/git``: Multi-write mutation, Commit / push).

A recorded commit was classified applied and matching as soon as any commit since its base carried the
recorded message, whatever that commit held. When a person - or anything else - made such a commit while the
recorded one was still unmade (a commit the pre-commit hook refused, an interruption right after recording
it), the retry made no commit of its own, pushed what the branch held, returned success and closed its
mutation. The operation's own change stayed uncommitted in the working tree, the remote never received it,
``validate_project`` reported nothing, and every later operation writing the same files stopped on
``dirty_overlap``. START returned ``completed`` with the Work's lifecycle events uncommitted.

A message identifies no commit. Finding it now counts only for a commit the record already holds as applied
- one this mutation made, whose later stages may have changed its paths again. A commit not yet held as
applied goes through the checks every commit goes through: its paths holding nothing left to commit, HEAD
still at its base on its branch (BL-035), or a branch that only grew past it (BL-032) - and stops otherwise.
"""

from __future__ import annotations

import re
import unittest
from unittest import mock

from helpers import completing_executor, git
from test_recorded_commit_branch import BranchCase
from test_recorded_commit_resume import EVENT_LOG, MAIN, ROADMAP_RELATIONS, WINDOWS, Interrupted
from workline import roadmap as rm
from workline import start as st
from workline.errors import StopError
from workline.ids import new_id
from workline.mutation import Mutation, MutationController
from workline.state import ProjectView

RESULT_MESSAGE = "docs: record the W1 result"


# --------------------------------------------------------------------------- windows the BL-032 tests do not have
def before_recording(pattern: str):
    """Stop right before the commit stage matching ``pattern`` is recorded, its domain effects applied."""
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        if re.search(pattern, stage) and any(effect.kind == "git_commit" for effect in effects):
            raise Interrupted(f"before recording {stage}")
        return real(mutation, stage, effects)

    return mock.patch.object(Mutation, "add_effects", fire)


def committed_before_its_flag(pattern: str):
    """Stop with the commit of the stage matching ``pattern`` made and its ``applied`` flag not yet saved."""
    real = MutationController.apply_effect

    def fire(controller, record):
        result = real(controller, record)
        if record["kind"] == "git_commit" and re.search(pattern, record["stage"]):
            raise Interrupted("committed, applied flag not saved")
        return result

    return mock.patch.object(MutationController, "apply_effect", fire)


def pushed_before_completion():
    """Stop with the push made and the mutation not completed."""
    def fire(mutation):
        raise Interrupted("pushed, not completed")

    return mock.patch.object(Mutation, "complete", fire)


class MessageCase(BranchCase):
    def two_result_files(self):
        """A single-work START whose Work finishes with two result files and its own result message."""
        def execute(ctx):
            names = ("result_a.txt", "result_b.txt")
            for name in names:
                (self.root / name).write_text(f"{ctx.work.name} {name}\n", encoding="utf-8")
            return st.Completed(names, RESULT_MESSAGE)

        return lambda: st.start(self.store, self.w1, "single-work", execute), rf"^{self.w1}:results:0$"

    def interrupt_with(self, call, window):
        """Run ``call`` into a window made by ``window``; return the record it leaves pending."""
        known = set(self.pending_ids())
        with window, self.assertRaises(Interrupted):
            call()
        (pending,) = [p for p in MutationController(self.store).list_pending() if p["mutation_id"] not in known]
        return pending

    def same_message_commit(self, message: str, text: str = "notes\nnothing to do with the recorded commit\n") -> str:
        return self.human_commit({"notes.md": text}, message)

    def stage_of(self, pending: dict, pattern: str) -> str:
        (stage,) = {e["stage"] for e in pending["effects"] if e["kind"] == "git_commit" and re.search(pattern, e["stage"])}
        return stage

    def carrying(self, message: str, since: str) -> list[str]:
        """Every commit since ``since`` that carries ``message``, oldest first."""
        return [sha for sha in git(self.root, "rev-list", "--reverse", f"{since}..HEAD").split()
                if git(self.root, "log", "-1", "--format=%B", sha).strip() == message.strip()]

    def introduced_by(self, event_id: str) -> str:
        """The subject of the commit that brought ``event_id`` into the committed event log."""
        commits = git(self.root, "log", "--reverse", "--format=%s", f"-S{event_id}", "--", EVENT_LOG).splitlines()
        self.assertTrue(commits, f"{event_id} is in no commit")
        return commits[0]

    def assertMadeOverSameMessage(self, call, pattern: str, pending: dict, moved_to: str, decided: dict) -> object:
        """The retry makes the recorded commit itself, once, on top of the commit that only shared its message."""
        stage = self.stage_of(pending, pattern)
        recorded = self.recorded_commit(pending, pattern)
        executed: list[str] = []
        stages: list[str] = []

        result = self.counting(call, executed, stages)

        self.assertEqual(result.mutation_id, pending["mutation_id"])
        self.assertEqual(list(zip(stages, executed)).count((stage, "git_commit")), 1)
        (made,) = self.carrying(recorded["message"], moved_to)
        self.assertEqual(self.parent(made), moved_to)
        changed = git(self.root, "diff-tree", "--no-commit-id", "--name-only", "-r", "--no-renames", made).split()
        self.assertTrue(changed and set(changed) <= set(recorded["paths"]), changed)
        self.assertEqual(self.blobs(recorded["paths"], made), decided)
        self.assertEqual(self.head(), self.remote_head())
        self.assertNothingLeftOver()
        return result


# --------------------------------------------------------------------------- the reproduction, for every kind of owner
class SameMessageTests(MessageCase):
    def test_a_commit_that_only_shares_the_message_does_not_stand_in_for_the_recorded_commit(self) -> None:
        """Unrelated paths under the recorded message: the operation makes its own commit after it (BL-032),
        exactly as it would after a commit with any other message - never success with its change uncommitted."""
        cases = [("phase hold", window) for window in WINDOWS] + [
            (operation, "commit refused")
            for operation in ("related maintenance", "roadmap creation", "direct creation", "start finalization")
        ]
        for index, (operation, window) in enumerate(cases):
            with self.subTest(operation=operation, window=window):
                self.build(f"same-{index}")
                call, pattern = self.operation(operation)
                pending = self.interrupt(call, pattern, window)
                recorded = self.recorded_commit(pending, pattern)
                decided = self.blobs(recorded["paths"])
                moved_to = self.same_message_commit(recorded["message"])

                self.assertMadeOverSameMessage(call, pattern, pending, moved_to, decided)

    def test_several_commits_sharing_the_message(self) -> None:
        self.build()
        call, pattern = self.operation("phase hold")
        pending = self.interrupt(call, pattern, "commit refused")
        recorded = self.recorded_commit(pending)
        decided = self.blobs(recorded["paths"])
        self.same_message_commit(recorded["message"], "notes\nfirst\n")
        moved_to = self.same_message_commit(recorded["message"], "notes\nsecond\n")

        self.assertMadeOverSameMessage(call, pattern, pending, moved_to, decided)

    def test_a_merged_branch_that_carries_the_message(self) -> None:
        self.build()
        call, pattern = self.operation("phase hold")
        pending = self.interrupt(call, pattern, "commit recorded")
        recorded = self.recorded_commit(pending)
        decided = self.blobs(recorded["paths"])
        git(self.root, "checkout", "-q", "-b", "side")
        self.same_message_commit(recorded["message"])
        git(self.root, "checkout", "-q", "main")
        git(self.root, "merge", "-q", "--no-ff", "-m", "Merge branch 'side'", "side")

        self.assertMadeOverSameMessage(call, pattern, pending, self.head(), decided)

    def test_part_of_the_recorded_paths_under_the_recorded_message_stops(self) -> None:
        for index, window in enumerate(WINDOWS):
            with self.subTest(window=window):
                self.build(f"partial-{index}")
                call, pattern = self.operation("phase entry")
                pending = self.interrupt(call, pattern, window)
                recorded = self.recorded_commit(pending)
                self.assertGreater(len(recorded["paths"]), 1)
                git(self.root, "add", "--", ROADMAP_RELATIONS)
                git(self.root, "commit", "-q", "-m", recorded["message"], "--", ROADMAP_RELATIONS)

                self.assertStopsUntouched(call)

                self.assertEqual(self.pending_ids(), [pending["mutation_id"]])

    def test_the_recorded_paths_with_other_content_under_the_recorded_message_stop(self) -> None:
        for index, window in enumerate(WINDOWS):
            with self.subTest(window=window):
                self.build(f"other-content-{index}")
                call, pattern = self.operation("phase hold")
                pending = self.interrupt(call, pattern, window)
                decided = self.store.events_jsonl.read_text(encoding="utf-8")
                committed = git(self.root, "show", f"HEAD:{EVENT_LOG}")
                other = '{"id":"%s","type":"phase_held","entity":"%s","at":"2026-01-01T00:00:00+00:00"}\n' % (new_id("event"), self.pc)
                self.human_commit({EVENT_LOG: committed + other}, self.recorded_commit(pending)["message"])
                (self.root / EVENT_LOG).write_text(decided, encoding="utf-8", newline="\n")

                self.assertStopsUntouched(call)

    def test_a_commit_carrying_the_message_on_a_branch_that_was_left_again(self) -> None:
        """Not in HEAD's history: the recorded commit is made on its base, as if nothing had happened."""
        self.build()
        call, pattern = self.operation("phase hold")
        pending = self.interrupt(call, pattern, "commit refused")
        recorded = self.recorded_commit(pending)
        git(self.root, "checkout", "-q", "-b", "side")
        self.same_message_commit(recorded["message"])
        git(self.root, "checkout", "-q", "main")

        self.assertEqual(call().status, "phase_held")

        self.assertMadeOnBranch(recorded["message"], recorded["base_head"], MAIN)


# --------------------------------------------------------------------------- what does count
class ProvenCommitTests(MessageCase):
    def test_the_recorded_content_committed_by_someone_else(self) -> None:
        """Nothing is left to commit at the recorded paths: that is what shows the commit, whatever its message."""
        for index, message in enumerate(("the recorded message", "another message")):
            with self.subTest(message=message):
                self.build(f"content-{index}")
                call, pattern = self.operation("phase entry")
                pending = self.interrupt(call, pattern, "commit refused")
                recorded = self.recorded_commit(pending)
                git(self.root, "add", "--", *recorded["paths"])
                text = recorded["message"] if message == "the recorded message" else "chore: a person committed it"
                git(self.root, "commit", "-q", "-m", text, "--", *recorded["paths"])
                executed: list[str] = []

                result = self.counting(call, executed)

                self.assertEqual((result.mutation_id, executed), (pending["mutation_id"], ["git_push"]))
                self.assertEqual(self.head(), self.remote_head())
                self.assertNothingLeftOver()

    def test_a_commit_made_just_before_its_flag_was_saved(self) -> None:
        """The commit exists but the record does not hold it as applied, so only its committed paths can show it."""
        with self.subTest(after="nothing"):
            self.build("flag-plain")
            call, pattern = self.operation("phase hold")
            pending = self.interrupt_with(call, committed_before_its_flag(pattern))
            self.assertEqual([e["applied"] for e in pending["effects"] if e["kind"] == "git_commit"], [False])
            executed: list[str] = []

            self.assertEqual(self.counting(call, executed).status, "phase_held")

            self.assertEqual(executed, ["git_push"])
            self.assertEqual(len(self.carrying(self.recorded_commit(pending)["message"], self.recorded_commit(pending)["base_head"])), 1)
            self.assertNothingLeftOver()
        with self.subTest(after="a commit sharing the message"):
            self.build("flag-same")
            call, pattern = self.operation("phase hold")
            pending = self.interrupt_with(call, committed_before_its_flag(pattern))
            recorded = self.recorded_commit(pending)
            (made,) = self.carrying(recorded["message"], recorded["base_head"])
            self.same_message_commit(recorded["message"])
            executed = []

            self.assertEqual(self.counting(call, executed).status, "phase_held")

            self.assertEqual(executed, ["git_push"])
            self.assertEqual(self.carrying(recorded["message"], recorded["base_head"])[0], made)
            self.assertNothingLeftOver()
        with self.subTest(after="its paths changed again by someone else"):
            # D-1, accepted: the commit is there, but nothing durable shows it is this mutation's own
            self.build("flag-dirty")
            call, pattern = self.operation("phase hold")
            pending = self.interrupt_with(call, committed_before_its_flag(pattern))
            (self.root / EVENT_LOG).write_text(self.store.events_jsonl.read_text(encoding="utf-8") + "\n",
                                               encoding="utf-8", newline="\n")

            self.assertStopsUntouched(call)

            self.assertEqual(self.pending_ids(), [pending["mutation_id"]])

    def test_a_commit_the_record_holds_as_applied_is_recognized_by_its_message(self) -> None:
        """Once applied, its paths may be changed again - by a person, or by the mutation's own later stages."""
        with self.subTest(window="committed, not pushed"):
            self.build("applied-push")
            call, pattern = self.operation("phase hold")
            pending = self.interrupt(call, pattern, "committed")
            recorded = self.recorded_commit(pending)
            (self.root / EVENT_LOG).write_text(self.store.events_jsonl.read_text(encoding="utf-8") + "\n",
                                               encoding="utf-8", newline="\n")
            executed: list[str] = []

            self.assertEqual(self.counting(call, executed).status, "phase_held")

            self.assertEqual(executed, ["git_push"])
            self.assertEqual(len(self.carrying(recorded["message"], recorded["base_head"])), 1)
            self.assertEqual((self.head(), self.pending_ids(), self.dirty()), (self.remote_head(), [], [f" M {EVENT_LOG}"]))
        with self.subTest(window="pushed, not completed"):
            self.build("applied-complete")
            call, pattern = self.operation("phase hold")
            pending = self.interrupt_with(call, pushed_before_completion())
            recorded = self.recorded_commit(pending)
            moved_to = self.same_message_commit(recorded["message"])
            executed = []

            self.assertEqual(self.counting(call, executed).status, "phase_held")

            self.assertEqual(executed, ["git_push"])
            self.assertEqual(len(self.carrying(recorded["message"], recorded["base_head"])), 2)
            self.assertEqual(self.head(), moved_to)
            self.assertEqual(self.head(), self.remote_head())
            self.assertNothingLeftOver()
        with self.subTest(window="a question the next Work asks, in outer mode"):
            # the second Work's events make the first Work's finalization paths dirty again before it asks
            self.build("applied-outer")
            asked: list[str] = []
            done = completing_executor(self.store)

            def execute(ctx):
                if ctx.work.id == self.w2 and not asked:
                    asked.append(ctx.work.id)
                    return st.QuestionWait("which way?")
                return done(ctx)

            call = lambda: st.start(self.store, self.w1, "outer", execute)  # noqa: E731
            self.assertEqual(call().status, "question_wait")

            self.assertEqual(call().status, "phase_complete")

            works = ProjectView.load(self.store).works
            first = git(self.root, "rev-list", "--max-parents=0", "HEAD").strip()
            for work in (self.w1, self.w2, self.integration):
                self.assertEqual(len(self.carrying(f"chore(workline): complete {works[work].display}", first)), 1)
            self.assertEqual(self.head(), self.remote_head())
            self.assertNothingLeftOver()


# --------------------------------------------------------------------------- windows
class WindowTests(MessageCase):
    def test_a_commit_sharing_the_message_in_each_window(self) -> None:
        """Before the commit is recorded, recorded and unmade, refused, made before its flag, flagged, pushed."""
        with self.subTest(window="before the commit is recorded"):
            self.build("w0")
            call, pattern = self.operation("phase hold")
            self.interrupt_with(call, before_recording(pattern))
            message = f"chore(workline): phase_held {self.pb}"
            moved_to = self.same_message_commit(message)
            executed: list[str] = []

            self.assertEqual(self.counting(call, executed).status, "phase_held")

            self.assertEqual(executed, ["git_commit", "git_push"])
            (made,) = self.carrying(message, moved_to)
            self.assertEqual(self.parent(made), moved_to)
            self.assertNothingLeftOver()
        for window in WINDOWS:
            with self.subTest(window=window):
                self.build(f"w1-{window.replace(' ', '-')}")
                call, pattern = self.operation("phase hold")
                pending = self.interrupt(call, pattern, window)
                recorded = self.recorded_commit(pending)
                decided = self.blobs(recorded["paths"])
                moved_to = self.same_message_commit(recorded["message"])

                self.assertMadeOverSameMessage(call, pattern, pending, moved_to, decided)
        with self.subTest(window="committed, applied flag not saved"):
            self.build("w2")
            call, pattern = self.operation("phase hold")
            pending = self.interrupt_with(call, committed_before_its_flag(pattern))
            self.same_message_commit(self.recorded_commit(pending)["message"])
            executed = []

            self.assertEqual(self.counting(call, executed).status, "phase_held")

            self.assertEqual(executed, ["git_push"])
            self.assertNothingLeftOver()
        for label, window in (("committed, not pushed", "committed"), ("pushed, not completed", None)):
            with self.subTest(window=label):
                self.build(f"w-{label.split(',')[0]}")
                call, pattern = self.operation("phase hold")
                pending = (self.interrupt(call, pattern, window) if window
                           else self.interrupt_with(call, pushed_before_completion()))
                recorded = self.recorded_commit(pending)
                self.same_message_commit(recorded["message"])
                executed = []

                self.assertEqual(self.counting(call, executed).status, "phase_held")

                self.assertEqual(executed, ["git_push"])
                self.assertEqual(len(self.carrying(recorded["message"], recorded["base_head"])), 2)
                self.assertNothingLeftOver()


# --------------------------------------------------------------------------- START (BL-031)
class StartTests(MessageCase):
    def test_a_finalization_is_committed_by_the_work_itself(self) -> None:
        """The completion events reach the remote in the Work's own finalization commit, in both modes."""
        for index, mode in enumerate(("single-work", "outer")):
            with self.subTest(mode=mode):
                self.build(f"finalize-{index}")
                call = lambda: st.start(self.store, self.w1, mode, completing_executor(self.store))  # noqa: E731
                pattern = rf"^{self.w1}:finalize:0$"
                pending = self.interrupt(call, pattern, "commit refused")
                recorded = self.recorded_commit(pending, pattern)
                completion = [e["payload"]["record"]["id"] for e in pending["effects"]
                              if e["kind"] == "append_event" and e["payload"]["record"]["type"] == "work_completed"]
                moved_to = self.same_message_commit(recorded["message"])

                result = call()

                self.assertEqual((result.status, result.mutation_id),
                                 ("completed" if mode == "single-work" else "phase_complete", pending["mutation_id"]))
                (made,) = self.carrying(recorded["message"], moved_to)
                self.assertEqual(self.parent(made), moved_to)
                self.assertEqual(self.introduced_by(completion[0]), recorded["message"])
                self.assertEqual(self.head(), self.remote_head())
                self.assertNothingLeftOver()

    def test_results_a_person_committed_in_part_under_the_result_message_stop(self) -> None:
        """D-5, accepted: START does not run the Work again over results only part of which are committed."""
        for index, window in enumerate(WINDOWS):
            with self.subTest(window=window):
                self.build(f"results-{index}")
                call, pattern = self.two_result_files()
                pending = self.interrupt(call, pattern, window)
                self.assertEqual(self.recorded_commit(pending, pattern)["paths"], ["result_a.txt", "result_b.txt"])
                git(self.root, "add", "--", "result_a.txt")
                git(self.root, "commit", "-q", "-m", RESULT_MESSAGE, "--", "result_a.txt")

                self.assertStopsUntouched(call)


if __name__ == "__main__":
    unittest.main()
