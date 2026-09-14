"""A recorded commit is made only on the branch it was decided on, also while HEAD is still its base (BL-035).

Every operation records its commit - the message, the paths it owns, the HEAD it was decided on and the
full name of the branch HEAD was on - before it makes it, and an operation interrupted in between, or whose
commit failed, resumes from that Git stage (``rules/git``: Multi-write mutation, Commit / push).

A recorded commit that had not been made was taken as unapplied whenever HEAD was still the recorded base,
whichever branch HEAD was on. Checking out another branch at the same commit, or renaming the branch, leaves
HEAD where it was, so the retry made the commit on that other branch. The push the record names for the
branch the commit was decided on then found that branch and its remote already equal (``git push --dry-run``
reports ``=``), took itself for done, and the operation returned success and closed its mutation: neither
the branch the commit was decided on nor its remote ever received the commit, and ``validate_project``
reported nothing.

HEAD being the base now counts only on the branch the commit was decided on. Another branch at the same
commit, a renamed branch, a detached HEAD, a record naming its branch in any other way and a question Git
cannot answer all stop the retry before the commit is made, with nothing changed; back on that branch the
same retry goes on. A record without a branch - written on a detached HEAD, or before the branch was
recorded - is made only while HEAD is on no branch.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from helpers import WORKLINE_ROOT, completing_executor, cwd, git
from test_recorded_commit_resume import HOOK, MAIN, WINDOWS, CommitWindowCase
from workline import gitcmd
from workline import start as st
from workline import yamlish
from workline.create import WorkSpec, create_standalone_work
from workline.errors import StopError
from workline.project_start import INITIAL_COMMIT_MESSAGE, project_start
from workline.store import ProjectStore

SIDE = "refs/heads/side"


class BranchCase(CommitWindowCase):
    def operation(self, name: str):
        if name == "direct creation":
            return lambda: create_standalone_work(self.store, WorkSpec("Solo", "solo")), r"^finalize$"
        return super().operation(name)

    def repository(self, name: str, *, committed: bool = True, detached: bool = False) -> None:
        """A folder with a repository on main, holding one commit or none yet, for Project開始 to initialize (no remote)."""
        self.name = name
        self.root = self.new_dir(name)
        git(self.root, "init", "-q", "-b", "main")
        if committed:
            (self.root / "notes.md").write_text("notes\n", encoding="utf-8")
            git(self.root, "add", "notes.md")
            git(self.root, "commit", "-q", "-m", "docs: notes")
        hooks = self.root / ".git" / "hooks"
        hooks.mkdir(exist_ok=True)
        (hooks / "pre-commit").write_text(HOOK, encoding="utf-8", newline="\n")
        os.chmod(hooks / "pre-commit", 0o755)
        git(self.root, "config", "core.hooksPath", hooks.as_posix())
        if detached:
            git(self.root, "checkout", "-q", "--detach")
        self.store = ProjectStore(self.root)

    def initialize(self):
        with cwd(WORKLINE_ROOT):
            return project_start(self.root, WORKLINE_ROOT)

    def on(self) -> str | None:
        return git(self.root, "symbolic-ref", "--quiet", "HEAD", check=False).strip() or None

    def records(self) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))}

    def snapshot(self) -> dict:
        """Everything a refused retry must leave exactly as it was, on a branch or on none.

        A record is compared by everything it holds but the time it was last saved: direct CREATE saves its
        unchanged write scope again on every resume, before its Git stage is reached (not new here).
        """
        remote = self.remote_path(self.name)
        return {
            "records": {name: {k: v for k, v in yamlish.load(data.decode("utf-8")).items() if k != "updated_at"}
                        for name, data in self.records().items()},
            "events": self.store.events_jsonl.read_bytes(),
            "head": git(self.root, "rev-parse", "--verify", "--quiet", "HEAD", check=False).strip(),
            "on": self.on(),
            "refs": git(self.root, "for-each-ref", "--format=%(refname) %(objectname)"),
            "remote refs": git(remote, "for-each-ref", "--format=%(refname) %(objectname)") if remote.exists() else None,
            "index": git(self.root, "diff", "--cached", "--name-status"),
            "dirty": self.dirty(),
        }

    def assertNeverCommitted(self, message: str) -> None:
        """No commit on any branch, here or at the remote, carries ``message``."""
        repositories = [self.root] + [r for r in (self.remote_path(self.name),) if r.exists()]
        for repository in repositories:
            carried = git(repository, "log", "--all", "--format=%B").split("\n")
            self.assertNotIn(message, [line.strip() for line in carried], repository)

    def assertMadeOnBranch(self, message: str, base: str, branch: str) -> None:
        """The commit is made once, on ``branch``, directly on the base, and the remote holds the same branch."""
        self.assertEqual(self.on(), branch)
        self.assertEqual(self.parent(self.made_with(message, base)), base)
        name = branch.removeprefix("refs/heads/")
        self.assertEqual(git(self.remote_path(self.name), "rev-parse", name).strip(), self.head())
        self.assertNothingLeftOver()


# --------------------------------------------------------------------------- the same commit, another branch
class SameCommitOtherBranchTests(BranchCase):
    def test_another_branch_at_the_recorded_base_stops_every_owner_before_its_commit(self) -> None:
        cases = [("phase hold", window) for window in WINDOWS] + [
            (operation, "commit refused") for operation in ("related maintenance", "direct creation", "start finalization")
        ]
        for index, (operation, window) in enumerate(cases):
            with self.subTest(operation=operation, window=window):
                self.build(f"other-{index}")
                call, pattern = self.operation(operation)
                pending = self.interrupt(call, pattern, window)
                recorded = self.recorded_commit(pending, pattern)
                self.assertEqual((recorded["base_head"], recorded["branch"]), (self.head(), MAIN))
                git(self.root, "checkout", "-q", "-b", "side")
                records = self.records()

                self.assertStopsUntouched(call)

                if operation != "direct creation":
                    self.assertEqual(self.records(), records)  # not a byte of the record is written
                self.assertNeverCommitted(recorded["message"])
                self.assertEqual(self.pending_ids(), [pending["mutation_id"]])
                # back on the branch it was decided on, the same retry goes on from its Git stage
                git(self.root, "checkout", "-q", "main")
                self.assertEqual(call().mutation_id, pending["mutation_id"])
                self.assertMadeOnBranch(recorded["message"], recorded["base_head"], MAIN)

    def test_a_renamed_branch_stops(self) -> None:
        self.build()
        call, pattern = self.operation("phase hold")
        pending = self.interrupt(call, pattern, "commit refused")
        git(self.root, "branch", "-m", "main", "trunk")

        self.assertStopsUntouched(call)

        self.assertNeverCommitted(self.recorded_commit(pending)["message"])

    def test_a_record_made_on_another_branch_is_not_made_on_main(self) -> None:
        moves = {
            "main checked out at the same commit": lambda: git(self.root, "checkout", "-q", "main"),
            "its branch deleted": lambda: (git(self.root, "checkout", "-q", "main"), git(self.root, "branch", "-q", "-D", "side")),
        }
        for index, move in enumerate(moves):
            with self.subTest(move=move):
                self.build(f"side-{index}")
                git(self.root, "checkout", "-q", "-b", "side")
                git(self.root, "push", "-q", "origin", "side")
                call, pattern = self.operation("phase hold")
                pending = self.interrupt(call, pattern, "commit refused")
                recorded = self.recorded_commit(pending)
                self.assertEqual(recorded["branch"], SIDE)
                moves[move]()

                self.assertStopsUntouched(call)

                self.assertNeverCommitted(recorded["message"])
                self.assertEqual(self.head(), self.remote_head())

    def test_a_detached_head_at_the_recorded_base_stops(self) -> None:
        with self.subTest(owner="Project開始"):
            self.repository("start-detached-later")
            base = self.head()
            pending = self.interrupt(self.initialize, r"^commit$", "commit refused")
            self.assertEqual(self.recorded_commit(pending)["branch"], MAIN)
            git(self.root, "checkout", "-q", "--detach")

            self.assertStopsUntouched(self.initialize)

            self.assertNeverCommitted(INITIAL_COMMIT_MESSAGE)
            git(self.root, "checkout", "-q", "main")
            result = self.initialize()
            self.assertEqual((result.status, result.mutation_id, result.resumed), ("initialized", pending["mutation_id"], True))
            self.assertEqual(self.parent(self.made_with(INITIAL_COMMIT_MESSAGE, base)), base)
            self.assertEqual(self.on(), MAIN)
        with self.subTest(owner="a Roadmap operation"):
            # unchanged: an operation that needs a branch refuses a detached HEAD at its entry, before any record is read
            self.build()
            call, pattern = self.operation("phase hold")
            self.interrupt(call, pattern, "commit refused")
            git(self.root, "checkout", "-q", "--detach")
            before = self.snapshot()
            with self.assertRaises(StopError) as stopped:
                call()
            self.assertEqual(stopped.exception.code, "detached_head")
            self.assertEqual(self.snapshot(), before)


# --------------------------------------------------------------------------- the branch it was decided on
class DecidedBranchTests(BranchCase):
    def test_the_branch_the_commit_was_decided_on_still_goes_on(self) -> None:
        moves = {
            "nothing moved": lambda: None,
            "another branch checked out and left again": lambda: (git(self.root, "checkout", "-q", "-b", "side"),
                                                                  git(self.root, "checkout", "-q", "main")),
        }
        for index, move in enumerate(moves):
            with self.subTest(move=move):
                self.build(f"same-{index}")
                call, pattern = self.operation("phase hold")
                pending = self.interrupt(call, pattern, "commit refused")
                recorded = self.recorded_commit(pending)
                moves[move]()

                self.assertEqual(call().status, "phase_held")

                self.assertMadeOnBranch(recorded["message"], recorded["base_head"], MAIN)

    def test_a_commit_decided_on_another_branch_goes_on_there(self) -> None:
        self.build()
        git(self.root, "checkout", "-q", "-b", "side")
        git(self.root, "push", "-q", "origin", "side")
        call, pattern = self.operation("phase hold")
        pending = self.interrupt(call, pattern, "commit refused")
        recorded = self.recorded_commit(pending)

        self.assertEqual(call().status, "phase_held")

        self.assertMadeOnBranch(recorded["message"], recorded["base_head"], SIDE)
        self.assertEqual(self.remote_head(), recorded["base_head"])  # main is left as it was

    def test_a_branch_with_no_commit_yet(self) -> None:
        for index, (move, resumes) in enumerate({"the same branch": True, "another branch": False}.items()):
            with self.subTest(move=move):
                self.repository(f"unborn-{index}", committed=False)
                pending = self.interrupt(self.initialize, r"^commit$", "commit refused")
                self.assertEqual((self.recorded_commit(pending)["base_head"], self.recorded_commit(pending)["branch"]), (None, MAIN))
                if not resumes:
                    git(self.root, "symbolic-ref", "HEAD", SIDE)
                    self.assertStopsUntouched(self.initialize)
                    continue
                self.assertEqual(self.initialize().mutation_id, pending["mutation_id"])
                self.assertEqual(git(self.root, "log", "-1", "--format=%s", "main").strip(), INITIAL_COMMIT_MESSAGE)


# --------------------------------------------------------------------------- what the record shows
class RecordedBranchIdentityTests(BranchCase):
    def test_a_record_naming_its_branch_in_another_way_stops(self) -> None:
        self.build()
        call, pattern = self.operation("phase hold")
        pending = self.interrupt(call, pattern, "commit refused")
        branches = {
            "the short name": "main",
            "null": None,
            "empty": "",
            "not text": 5,
            "a branch that does not exist": "refs/heads/other",
            "a tag of the same name": "refs/tags/main",
        }
        for label, branch in branches.items():
            with self.subTest(branch=label):
                self.edit_recorded_commit(pending, lambda payload, branch=branch: payload.update(branch=branch))

                self.assertStopsUntouched(call)

    def test_a_record_without_a_branch(self) -> None:
        with self.subTest(record="written before the branch was recorded", on="the branch"):
            self.build("legacy-main")
            call, pattern = self.operation("phase hold")
            pending = self.interrupt(call, pattern, "commit refused")
            self.edit_recorded_commit(pending, lambda payload: payload.pop("branch"))

            self.assertStopsUntouched(call)
        with self.subTest(record="written before the branch was recorded", on="another branch"):
            self.build("legacy-side")
            call, pattern = self.operation("phase hold")
            pending = self.interrupt(call, pattern, "commit refused")
            self.edit_recorded_commit(pending, lambda payload: payload.pop("branch"))
            git(self.root, "checkout", "-q", "-b", "side")

            self.assertStopsUntouched(call)

            self.assertNeverCommitted(self.recorded_commit(pending)["message"])
        with self.subTest(record="written on a detached HEAD", on="no branch, uninterrupted"):
            self.repository("detached-whole", detached=True)
            base = self.head()
            self.assertEqual(self.initialize().status, "initialized")
            self.assertEqual((self.on(), self.parent(self.head())), (None, base))
        for window in WINDOWS:
            with self.subTest(record="written on a detached HEAD", on="no branch", window=window):
                self.repository(f"detached-{window.replace(' ', '-')}", detached=True)
                base = self.head()
                pending = self.interrupt(self.initialize, r"^commit$", window)
                self.assertNotIn("branch", self.recorded_commit(pending))

                result = self.initialize()

                self.assertEqual((result.status, result.mutation_id, result.resumed), ("initialized", pending["mutation_id"], True))
                self.assertEqual((self.on(), self.parent(self.head())), (None, base))
                self.assertEqual(git(self.root, "rev-parse", "main").strip(), base)
        with self.subTest(record="written on a detached HEAD", on="a branch at the same commit"):
            self.repository("detached-then-main", detached=True)
            pending = self.interrupt(self.initialize, r"^commit$", "commit refused")
            git(self.root, "checkout", "-q", "main")

            self.assertStopsUntouched(self.initialize)

            self.assertNeverCommitted(INITIAL_COMMIT_MESSAGE)
            git(self.root, "checkout", "-q", "--detach")
            self.assertEqual(self.initialize().mutation_id, pending["mutation_id"])

    def test_a_question_git_cannot_answer_at_the_recorded_base(self) -> None:
        real = gitcmd.run_git

        def unanswered(repo, *args, check=True):
            if args[:2] == ("symbolic-ref", "--quiet"):
                return gitcmd.GitResult(128, "", "fatal: cannot answer")
            return real(repo, *args, check=check)

        with self.subTest(record="naming its branch"):
            self.build()
            call, pattern = self.operation("phase hold")
            self.interrupt(call, pattern, "commit refused")
            with mock.patch.object(gitcmd, "run_git", unanswered):
                self.assertStopsUntouched(call)
        with self.subTest(record="without a branch"):
            self.repository("unanswered-detached", detached=True)
            self.interrupt(self.initialize, r"^commit$", "commit refused")
            with mock.patch.object(gitcmd, "run_git", unanswered):
                self.assertStopsUntouched(self.initialize)


# --------------------------------------------------------------------------- START finalization (BL-031)
class StartFinalizationTests(BranchCase):
    def test_a_finalization_is_not_committed_on_another_branch(self) -> None:
        for index, mode in enumerate(("single-work", "outer")):
            with self.subTest(mode=mode):
                self.build(f"finalize-{index}")
                call = lambda: st.start(self.store, self.w1, mode, completing_executor(self.store))  # noqa: E731
                pattern = rf"^{self.w1}:finalize:0$"
                pending = self.interrupt(call, pattern, "commit refused")
                recorded = self.recorded_commit(pending, pattern)
                git(self.root, "checkout", "-q", "-b", "side")

                self.assertStopsUntouched(call)

                self.assertNeverCommitted(recorded["message"])
                git(self.root, "checkout", "-q", "main")
                result = call()
                self.assertEqual((result.status, result.mutation_id),
                                 ("completed" if mode == "single-work" else "phase_complete", pending["mutation_id"]))
                self.assertEqual(self.parent(self.made_with(recorded["message"], recorded["base_head"])), recorded["base_head"])
                self.assertEqual((self.on(), self.head()), (MAIN, self.remote_head()))
                self.assertNothingLeftOver()


# --------------------------------------------------------------------------- unchanged
class KnownResidualTests(BranchCase):
    def test_a_commit_carrying_the_recorded_message_on_another_branch_is_still_taken_for_it(self) -> None:
        """BL-033, unchanged: the recorded message is looked for before the branch is considered."""
        self.build()
        call, pattern = self.operation("phase hold")
        pending = self.interrupt(call, pattern, "commit recorded")
        base = self.head()
        git(self.root, "checkout", "-q", "-b", "side")
        self.human_commit({"notes.md": "notes\nsame message\n"}, self.recorded_commit(pending)["message"])
        executed: list[str] = []

        result = self.counting(call, executed)

        self.assertEqual((result.status, result.mutation_id), ("phase_held", pending["mutation_id"]))
        self.assertEqual(executed, [])  # the recorded commit is never made, and main:main is already up to date
        self.assertEqual(self.dirty(), [" M .workline/events/events.jsonl"])
        self.assertEqual((git(self.root, "rev-parse", "main").strip(), self.remote_head()), (base, base))


if __name__ == "__main__":
    unittest.main()
