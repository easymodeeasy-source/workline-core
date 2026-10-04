"""A message Workline accepted is committed with Workline's own cleanup, not the repository's (RB10 N6-4).

Workline's own commits go through ``gitcmd.commit_only`` (``git commit --only -m``). Git cleans a message up before
storing it, and how is configuration: ``commit.cleanup=strip`` - in the Project's repository or the user's global
configuration - reads every line starting with ``#`` as commentary and drops it. A caller message such as
``# heading`` then lost its first line, and one that was only ``# only`` became empty: Git refused the commit, and
the operation stopped at its Git stage with everything else applied.

The cleanup is pinned now: ``--cleanup=whitespace``, the cleanup ``-m`` gets when nothing is configured - trailing
whitespace, leading / trailing / repeated blank lines go, every line stays. The stored message is the same whatever
the configuration says. A ``#``-prefixed message is never refused for being one. A hook may still rewrite a message;
the made commit's ID, not its message, stays what recognizes it (BL-037).
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from helpers import WorklineTestCase, git
from workline import gitcmd
from workline import start as st
from workline.create import WorkSpec, create_standalone_work
from workline.mutation import MutationController

#: The executor's message, and what is stored for it whatever ``commit.cleanup`` says.
MESSAGES = {
    "only a comment-like line": ("# only", "# only\n"),
    "a comment-like heading and a body": ("# heading\nbody", "# heading\nbody\n"),
    "ordinary text": ("feat: export the report", "feat: export the report\n"),
    "trailing whitespace and repeated blank lines": ("subject   \n\n\nbody  \n", "subject\n\nbody\n"),
    "leading blank lines": ("\n\n# first\n", "# first\n"),
    "CRLF": ("subject\r\n\r\nbody\r\n", "subject\n\nbody\n"),
}


def stored_message(root: Path, commit: str) -> str:
    raw = subprocess.run(["git", "-C", str(root), "cat-file", "commit", commit], capture_output=True, check=True).stdout
    return raw.split(b"\n\n", 1)[1].decode("utf-8")


class CleanupCase(WorklineTestCase):
    def complete_with(self, store, message: str) -> str:
        """A standalone Work completed by an executor committing one result file with ``message``; the result commit."""
        self.enter(store.root)
        work_id = create_standalone_work(store, WorkSpec("Report", "the report exists")).work_id

        def execute(ctx):
            (store.root / "report.txt").write_text("report\n", encoding="utf-8")
            return st.Completed(("report.txt",), message)

        result = st.start(store, work_id, "single-work", execute)
        self.assertEqual(result.status, "completed")
        self.assertEqual(MutationController(store).list_pending(), [])
        commit = git(store.root, "log", "-1", "--format=%H", "--", "report.txt").strip()
        self.assertTrue(commit)
        return commit


class PinnedCleanupTests(CleanupCase):
    def test_commit_only_pins_the_cleanup(self) -> None:
        seen: list[tuple] = []

        def run(repo, *args, **kwargs):
            seen.append(args)

        with mock.patch.object(gitcmd, "run_git", run), mock.patch.object(gitcmd, "head_commit", lambda repo: "0" * 40):
            gitcmd.commit_only(Path("."), "# only", ["a.txt"])
        (args,) = seen
        self.assertEqual(args[:2], ("commit", "--only"))
        self.assertIn("--cleanup=whitespace", args)
        self.assertLess(args.index("--cleanup=whitespace"), args.index("-m"))

    def test_a_hostile_repository_cleanup_changes_nothing(self) -> None:
        for label, (message, expected) in MESSAGES.items():
            with self.subTest(label):
                case = type(self)(self._testMethodName)
                case.setUp()
                try:
                    hostile = case.new_project("hostile")
                    git(hostile.root, "config", "commit.cleanup", "strip")
                    git(hostile.root, "config", "core.commentChar", "#")
                    plain = case.new_project("plain")
                    hostile_commit = case.complete_with(hostile, message)
                    plain_commit = case.complete_with(plain, message)
                    case.assertEqual(stored_message(hostile.root, hostile_commit), expected)
                    case.assertEqual(stored_message(plain.root, plain_commit), expected, "the same as with no configuration")
                finally:
                    case.doCleanups()

    def test_a_hostile_global_cleanup_changes_nothing(self) -> None:
        config = self.tmp / "global.gitconfig"
        config.write_text("[commit]\n\tcleanup = strip\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(config)}):
            store = self.new_project()
            commit = self.complete_with(store, "# heading\nbody")
        self.assertEqual(stored_message(store.root, commit), "# heading\nbody\n")

    def test_without_the_pin_git_would_have_dropped_or_refused_the_message(self) -> None:
        """What the configuration does to an unpinned ``git commit -m``: the reason the cleanup is pinned."""
        store = self.new_project()
        git(store.root, "config", "commit.cleanup", "strip")
        (store.root / "a.txt").write_text("a\n", encoding="utf-8")
        git(store.root, "add", "a.txt")
        refused = subprocess.run(["git", "-C", str(store.root), "commit", "-m", "# only"], capture_output=True, text=True)
        self.assertNotEqual(refused.returncode, 0, "an empty message after strip")
        git(store.root, "commit", "-q", "-m", "# heading\nbody")
        self.assertEqual(stored_message(store.root, git(store.root, "rev-parse", "HEAD").strip()), "body\n")


if __name__ == "__main__":
    unittest.main()
