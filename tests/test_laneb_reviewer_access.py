"""field-feedback item 6: a Review actor's read access is checked before the Review starts (core pre-check).

The actor owner builds the allowance; the core only asks it - ``read_access(argv) -> bool`` - for the exact command
forms the Project needs (``git -C <submodule> ...``, ``git ls-tree``, ``git submodule status``), classifies a
shortage, and refuses before any effect. Write-capable Git forms stay refused. Driven through a real submodule
project and the real START entry.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from test_review_p4_planning import Discovery
from test_review_p4_work import P4WorkCase, work_p4
from workline import reviewer_access as ra
from workline import start as st
from workline.errors import StopError


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "protocol.file.allow=always", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


READ_WORDS = {"rev-parse", "log", "ls-tree", "status", "show", "cat-file", "diff"}


def read_only_allowance(argv: tuple[str, ...]) -> bool:
    """An allowance that permits every read form, in either spelling (``git -C <dir> ...`` included)."""
    words = list(argv[1:])
    if words[:1] == ["-C"]:
        words = words[2:]
    if words[:2] == ["submodule", "status"]:
        return True
    return bool(words) and words[0] in READ_WORDS


def no_dash_c_allowance(argv: tuple[str, ...]) -> bool:
    """The field case: the plain forms are listed, ``git -C <submodule> ...`` is not."""
    return "-C" not in argv and read_only_allowance(argv)


def writing_allowance(argv: tuple[str, ...]) -> bool:
    return True


class AccessActor(Discovery):
    def __init__(self, allowance: Any, *script: Any) -> None:
        super().__init__(*script)
        self.read_access = allowance


class SubmoduleProjectCase(P4WorkCase):
    def setUp(self) -> None:
        super().setUp()
        root = Path(self.store.root)
        upstream = root.parent / (root.name + "-solver-upstream")
        upstream.mkdir()
        git(upstream, "init", "-q")
        (upstream / "solver.txt").write_text("solver\n", encoding="utf-8")
        git(upstream, "add", "solver.txt")
        git(upstream, "-c", "user.name=t", "-c", "user.email=t@example.test", "commit", "-q", "-m", "solver")
        git(root, "submodule", "add", "-q", str(upstream), "solver")
        git(root, "-c", "user.name=t", "-c", "user.email=t@example.test", "commit", "-q", "-m", "chore: add solver")
        self.root = root
        self.executor = self.completing(write={"out.txt": b"out\n"}, message="feat: out")


class ReviewerAccessCheckTests(SubmoduleProjectCase):
    def test_the_submodule_is_found(self) -> None:
        self.assertEqual(["solver"], ra.submodule_paths(self.root))

    def test_an_unreadable_submodule_list_is_unknown_and_never_taken_for_no_submodules(self) -> None:
        """H-X10: when the list of gitlinks cannot be read the status is ``unknown`` and it stops (AM-I)."""
        from unittest import mock

        failed = mock.Mock(ok=False, stdout="")
        with mock.patch.object(ra.gitcmd, "run_git", return_value=failed):
            with self.assertRaises(StopError) as raised:
                ra.submodule_paths(self.root)
        self.assertEqual(ra.CODE_REVIEWER_ACCESS, raised.exception.code)
        self.assertIn(ra.UNKNOWN, str(raised.exception))

    def test_an_allowance_that_lists_every_form_is_clean(self) -> None:
        self.assertEqual([], ra.findings_for(self.root, "reviewer 1", read_only_allowance))

    def test_the_field_case_missing_dash_c_forms_are_permission_denied_and_named(self) -> None:
        found = ra.findings_for(self.root, "reviewer 1", no_dash_c_allowance)
        self.assertTrue(found)
        self.assertEqual({ra.PERMISSION_DENIED}, {item.classification for item in found})
        self.assertIn(("git", "-C", "solver", "rev-parse", "HEAD"), {item.command for item in found})

    def test_an_allowance_that_would_write_is_not_read_only(self) -> None:
        found = ra.findings_for(self.root, "reviewer 1", writing_allowance)
        self.assertIn(ra.WRITE_PERMITTED, {item.classification for item in found})
        self.assertNotIn(ra.PERMISSION_DENIED, {item.classification for item in found})

    def test_an_allowance_that_cannot_answer_is_no_allowance(self) -> None:
        def broken(argv: tuple[str, ...]) -> bool:
            raise RuntimeError("no policy")

        self.assertEqual({ra.PERMISSION_DENIED}, {item.classification for item in
                                                   ra.findings_for(self.root, "reviewer 1", broken)})

    def test_a_submodule_that_is_not_checked_out_is_target_missing_not_a_permission_problem(self) -> None:
        found = ra.findings_for(self.root, "reviewer 1", read_only_allowance, paths=["not-a-submodule"])
        self.assertEqual([(ra.TARGET_MISSING, "not-a-submodule")], [(item.classification, item.target) for item in found])


class ReviewerAccessStartTests(SubmoduleProjectCase):
    def test_start_refuses_before_any_effect_and_a_sufficient_actor_runs_the_review(self) -> None:
        head = self.head()
        weak = AccessActor(no_dash_c_allowance)
        with self.assertRaises(StopError) as raised:
            st.start(self.store, self.work_id, "single-work", self.executor, review=work_p4(weak))
        self.assertEqual(ra.CODE_REVIEWER_ACCESS, raised.exception.code, raised.exception)
        self.assertIn(ra.PERMISSION_DENIED, str(raised.exception))
        self.assertEqual(head, self.head(), "nothing was committed")
        self.assertEqual([], self.pending(), "no mutation was begun")
        self.assertEqual([], self.runs(), "no Review Run was begun")
        self.assertEqual([], weak.tasks, "the actor was never launched")
        # the same Project with an actor whose allowance lists the forms the Reviewer runs there
        result, record = self.complete(self.executor, review=work_p4(AccessActor(read_only_allowance)))
        self.assertEqual([], self.problems())
        self.assertEqual(1, len(self.runs()))

    def test_start_with_an_unreadable_submodule_list_stops_before_anything_is_begun(self) -> None:
        from unittest import mock

        head = self.head()
        actor = AccessActor(read_only_allowance)
        real = ra.gitcmd.run_git

        def unreadable_list(root, *args, **kwargs):
            if args[:1] == ("ls-files",):
                return mock.Mock(ok=False, stdout="")
            return real(root, *args, **kwargs)

        with mock.patch.object(ra.gitcmd, "run_git", side_effect=unreadable_list):
            with self.assertRaises(StopError) as raised:
                st.start(self.store, self.work_id, "single-work", self.executor, review=work_p4(actor))
        self.assertEqual(ra.CODE_REVIEWER_ACCESS, raised.exception.code, raised.exception)
        self.assertIn(ra.UNKNOWN, str(raised.exception))
        self.assertEqual(head, self.head())
        self.assertEqual([], self.pending())
        self.assertEqual([], self.runs())
        self.assertEqual([], actor.tasks)

    def test_an_actor_that_exposes_no_allowance_is_not_checked(self) -> None:
        result, record = self.complete(self.executor, review=work_p4(Discovery()))
        self.assertEqual(1, len(self.runs()))
