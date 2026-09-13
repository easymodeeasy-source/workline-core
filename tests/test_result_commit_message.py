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
from unittest import mock

from helpers import WorklineTestCase, git
from workline import gitcmd
from workline import start as st
from workline.create import WorkSpec, create_standalone_work
from workline.errors import ValidationError
from workline.mutation import MutationController


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


class BlankMessageTests(WorklineTestCase):
    """A message that says nothing means the same however it is spelled.

    None, empty and whitespace-only all fall back to the neutral default. A
    blank one is never refused: whitespace alone is not a message a commit could
    carry, and stopping the Work over it would strand a result that is already
    finished - the commit effect is recorded after the executor has run, so the
    refusal used to leave a pending mutation that blocked the next operation.
    """

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def _run_with(self, message: str | None, name: str = "Blank case"):
        work_id = create_standalone_work(self.store, WorkSpec(name, "成立する")).work_id

        def execute(ctx):
            (self.store.root / "result.txt").write_text("x\n", encoding="utf-8")
            return st.Completed(("result.txt",), message)

        result = st.start(self.store, work_id, "single-work", execute)
        self.assertEqual(result.status, "completed")
        return git(self.store.root, "log", "--format=%s").splitlines()

    def assertFellBackToDefault(self, message: str | None) -> None:
        messages = self._run_with(message)

        self.assertEqual(messages[1], "chore(workline): W-01 Blank case")
        self.assertEqual(messages[0], "chore(workline): complete W-01")
        self.assertEqual(MutationController(self.store).list_pending(), [])

    def test_no_message_uses_the_default(self) -> None:
        self.assertFellBackToDefault(None)

    def test_an_empty_message_uses_the_default(self) -> None:
        self.assertFellBackToDefault("")

    def test_a_spaces_only_message_uses_the_default_instead_of_stopping(self) -> None:
        self.assertFellBackToDefault("   ")

    def test_a_tab_and_newline_message_uses_the_default(self) -> None:
        self.assertFellBackToDefault("\t\r\n")

    def test_a_falsy_value_that_is_not_a_string_still_uses_the_default(self) -> None:
        """Falsy values fell back to the default before, and still do."""
        for index, value in enumerate((0, False, [])):
            with self.subTest(value=value):
                work_id = create_standalone_work(self.store, WorkSpec(f"Odd {index}", "成立する")).work_id

                def execute(ctx, value=value, index=index):
                    (self.store.root / f"odd{index}.txt").write_text("x\n", encoding="utf-8")
                    return st.Completed((f"odd{index}.txt",), value)

                result = st.start(self.store, work_id, "single-work", execute)

                self.assertEqual(result.status, "completed")
                self.assertEqual(
                    git(self.store.root, "log", "-2", "--format=%s").splitlines()[1],
                    f"chore(workline): W-{index + 1:02d} Odd {index}",
                )
                self.assertEqual(MutationController(self.store).list_pending(), [])

    def test_a_truthy_value_that_is_not_a_string_is_still_refused(self) -> None:
        """Not promoted to a valid message: the commit effect refuses it, as it always did.

        Only blank strings were added to what falls back to the default. A truthy
        non-string is handed on unchanged and meets the same refusal it met
        before; there is no new check of its own and no quiet default.
        """
        for index, value in enumerate((5, [1])):
            with self.subTest(value=value):
                store = self.new_project(f"truthy{index}")
                work_id = create_standalone_work(store, WorkSpec("Truthy", "成立する")).work_id

                def execute(ctx, value=value, store=store):
                    (store.root / "result.txt").write_text("x\n", encoding="utf-8")
                    return st.Completed(("result.txt",), value)

                with self.assertRaises(ValidationError) as refused:
                    st.start(store, work_id, "single-work", execute)

                self.assertEqual(refused.exception.code, "validation_failed")
                self.assertEqual(refused.exception.message, "git_commit needs a message")
                # nothing was committed under the default in its place
                self.assertNotIn("chore(workline): W-01 Truthy", git(store.root, "log", "--format=%s").splitlines())

    def test_only_blank_strings_changed_from_the_truthiness_test(self) -> None:
        """The whole boundary, against the rule it replaced: ``message or default``.

        Every input gives exactly what that rule gave, with one exception - a
        string of only whitespace, which now falls back to the default instead of
        reaching a validation that refuses it. The object handed on is the same
        object, so a refusal further down is the same refusal.
        """

        class Work:
            display = "W-07"
            name = "Boundary"

        default = "chore(workline): W-07 Boundary"
        blank_strings = ("   ", "\t\r\n", " ", "\n")
        unchanged = (None, "", 0, False, [], 0.0, 5, [1], "docs(project): exact", " x ", "\n real \n", "まとめた")
        marker = object()

        for value in unchanged + (marker,):
            with self.subTest(value=value):
                got = st._result_message(value, Work)
                if value:
                    self.assertIs(got, value)  # the very object: not copied, stripped or replaced
                else:
                    self.assertEqual(got, default)
        for value in blank_strings:
            with self.subTest(value=value):
                self.assertEqual(st._result_message(value, Work), default)

    def test_a_blank_message_leaves_the_project_usable(self) -> None:
        """The Work finishes, so the next operation is not blocked behind it."""
        self._run_with("   ", "First")

        later = create_standalone_work(self.store, WorkSpec("Later", "成立する"))

        self.assertIsNotNone(later.work_id)
        self.assertEqual(MutationController(self.store).list_pending(), [])


class VerbatimMessageTests(WorklineTestCase):
    """What an executor actually says is committed exactly as given."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def committed_message(self, message: str) -> str:
        """The message START hands to Git, before Git does anything of its own."""
        seen: list[str] = []
        real = gitcmd.commit_only

        def watch(repo, msg, paths):
            seen.append(msg)
            return real(repo, msg, paths)

        work_id = create_standalone_work(self.store, WorkSpec("Verbatim", "成立する")).work_id

        def execute(ctx):
            (self.store.root / "result.txt").write_text("x\n", encoding="utf-8")
            return st.Completed(("result.txt",), message)

        with mock.patch.object(gitcmd, "commit_only", watch):
            st.start(self.store, work_id, "single-work", execute)
        return seen[0]

    def test_a_conventional_message_is_passed_through_unchanged(self) -> None:
        self.assertEqual(self.committed_message("docs(project): rewrite the guide"), "docs(project): rewrite the guide")

    def test_a_free_form_message_is_passed_through_unchanged(self) -> None:
        self.assertEqual(self.committed_message("まとめて書き直した"), "まとめて書き直した")

    def test_surrounding_whitespace_is_not_stripped_by_workline(self) -> None:
        """The blank test strips; the message that gets committed never does.

        Git trims trailing whitespace when it stores a commit subject, so the
        check is what Workline hands over, not what Git kept afterwards.
        """
        given = " docs(project): exact text "

        self.assertEqual(self.committed_message(given), given)

    def test_a_message_that_only_looks_blank_at_the_edges_is_kept(self) -> None:
        self.assertEqual(self.committed_message("\n  real content  \n"), "\n  real content  \n")


class ResultCommitShapeTests(WorklineTestCase):
    """How many result commits a completion makes, and in what order."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def test_several_result_paths_stay_one_result_commit(self) -> None:
        work_id = create_standalone_work(self.store, WorkSpec("Many", "成立する")).work_id

        def execute(ctx):
            for name in ("one.txt", "two.txt", "three.txt"):
                (self.store.root / name).write_text("x\n", encoding="utf-8")
            return st.Completed(("one.txt", "two.txt", "three.txt"))

        st.start(self.store, work_id, "single-work", execute)

        messages = git(self.store.root, "log", "--format=%s").splitlines()
        self.assertEqual(messages[:2], ["chore(workline): complete W-01", "chore(workline): W-01 Many"])
        self.assertEqual(
            set(git(self.store.root, "show", "--name-only", "--format=", "HEAD~1").split()),
            {"one.txt", "two.txt", "three.txt"},
        )

    def test_a_blank_message_does_not_change_the_commit_shape(self) -> None:
        """Same two commits, same order, as a completion with no message at all."""
        work_id = create_standalone_work(self.store, WorkSpec("Shape", "成立する")).work_id

        def execute(ctx):
            (self.store.root / "a.txt").write_text("x\n", encoding="utf-8")
            (self.store.root / "b.txt").write_text("x\n", encoding="utf-8")
            return st.Completed(("a.txt", "b.txt"), "   ")

        st.start(self.store, work_id, "single-work", execute)

        messages = git(self.store.root, "log", "--format=%s").splitlines()
        self.assertEqual(messages[:2], ["chore(workline): complete W-01", "chore(workline): W-01 Shape"])
        self.assertEqual(
            set(git(self.store.root, "show", "--name-only", "--format=", "HEAD~1").split()),
            {"a.txt", "b.txt"},
        )


if __name__ == "__main__":
    unittest.main()
