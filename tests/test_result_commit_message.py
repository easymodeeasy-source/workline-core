"""The default message of a Work result commit (BL-016).

Whether a result is a feature, a fix, documentation or a refactor is a product
judgement about what the work means. Only the executor that produced the result
holds it, so START never infers one from the Work name, its desired state, its
``work_kind`` or the files it touched: the default it writes is neutral and the
same for every Work.

An executor that does hold that judgement passes it as an explicit message, and
that string is committed verbatim - START adds no prefix, converts no type and
validates no format.
"""

from __future__ import annotations

import unittest

from helpers import WorklineTestCase, git
from workline import start as st
from workline.create import WorkSpec, create_standalone_work


class ResultCommitMessageTests(WorklineTestCase):
    """One standalone Work per case, run to completion, read back from Git."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def _run(self, name: str, executor) -> list[str]:
        work_id = create_standalone_work(self.store, WorkSpec(name, f"{name} が成立する")).work_id
        result = st.start(self.store, work_id, "single-work", executor)
        self.assertEqual(result.status, "completed")
        return git(self.store.root, "log", "--format=%s").splitlines()

    def _writes(self, filename: str, message: str | None = None):
        def execute(ctx):
            (self.store.root / filename).write_text(f"{ctx.work.name}\n", encoding="utf-8")
            return st.Completed((filename,), message)

        return execute

    def _seed_tracked(self, filename: str) -> None:
        (self.store.root / filename).write_text("bye\n", encoding="utf-8")
        git(self.store.root, "add", filename)
        git(self.store.root, "commit", "-m", "chore(workline): seed a tracked file")

    # default ---------------------------------------------------------------
    def test_a_normal_work_gets_the_neutral_default(self) -> None:
        messages = self._run("Add export button", self._writes("feature.txt"))

        self.assertEqual(
            messages[:2],
            ["chore(workline): complete W-01", "chore(workline): W-01 Add export button"],
        )

    def test_a_bugfix_shaped_name_is_not_read_as_a_fix(self) -> None:
        """The name says "Fix"; the type stays neutral because START does not read names."""
        messages = self._run("Fix crash on empty input", self._writes("bugfix.txt"))

        self.assertEqual(messages[1], "chore(workline): W-01 Fix crash on empty input")

    def test_a_documentation_shaped_name_is_not_read_as_docs(self) -> None:
        messages = self._run("Update README", self._writes("README-note.md"))

        self.assertEqual(messages[1], "chore(workline): W-01 Update README")

    def test_a_deletion_only_result_gets_the_same_default(self) -> None:
        """Created, modified and deleted results are one owned set and one commit."""
        self._seed_tracked("obsolete.txt")

        def execute(ctx):
            (self.store.root / "obsolete.txt").unlink()
            return st.Completed((), None, ("obsolete.txt",))

        messages = self._run("Remove obsolete file", execute)

        self.assertEqual(messages[1], "chore(workline): W-01 Remove obsolete file")
        self.assertEqual(
            set(git(self.store.root, "show", "--name-only", "--format=", "HEAD~1").split()),
            {"obsolete.txt"},
        )

    # explicit override -----------------------------------------------------
    def test_an_explicit_message_is_committed_verbatim(self) -> None:
        """No prefix is added and no type is converted: the executor's string stands."""
        messages = self._run(
            "Documented work", self._writes("docs.md", "docs(project): rewrite the guide")
        )

        self.assertEqual(messages[1], "docs(project): rewrite the guide")
        self.assertEqual(messages[0], "chore(workline): complete W-01")

    def test_an_explicit_message_needs_no_conventional_form(self) -> None:
        messages = self._run("Free form", self._writes("free.txt", "まとめて書き直した"))

        self.assertEqual(messages[1], "まとめて書き直した")

    # no owned result -------------------------------------------------------
    def test_a_work_owning_no_file_makes_no_result_commit(self) -> None:
        messages = self._run("Analysis only", lambda ctx: st.Completed())

        self.assertEqual(messages[0], "chore(workline): complete W-01")
        self.assertEqual(messages[1], "chore(workline): create W-01")

    # the type START never writes -------------------------------------------
    def test_no_workline_written_message_claims_a_feature(self) -> None:
        """A guard against a semantic default returning by any path."""
        self._seed_tracked("gone.txt")

        def deletes(ctx):
            (self.store.root / "gone.txt").unlink()
            return st.Completed((), None, ("gone.txt",))

        self._run("Fix the feature docs", self._writes("a.txt"))
        self._run("Add a feature", self._writes("b.txt"))
        self._run("Drop the feature", deletes)

        written = git(self.store.root, "log", "--format=%s").splitlines()
        self.assertEqual([m for m in written if m.startswith("feat(")], [])


if __name__ == "__main__":
    unittest.main()
