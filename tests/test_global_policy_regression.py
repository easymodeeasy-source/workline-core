"""P7 compatibility regression (``WORKLINE_COMPLETION_SPRINT`` §31.59): what RB7 shares with Projects stays theirs.

RB7-F foundation rows:

* the OS lock primitive (§31.9) is extracted from the Project execution lock
  without changing it: the Project lock still runs every step it ran, in the same
  order, now through the public primitive the root maintenance lock uses too;
* the class B scratch (§31.8 / §31.30, RB7C-5): a Project's stays exactly where it
  was, and the root's class B entry uses root-runtime scratch and can never name
  ``.workline/`` - no root operation creates the Project namespace;
* the two read-only Git facts the opaque root repository identity is built from
  (§31.13): the common directory and the object format.

The §31.59 rows that need the root owner (Project Review / Mutation Controller
unchanged end to end, no ``.workline`` after every root operation) are added with
it.
"""

from __future__ import annotations

import ast
import inspect
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from unittest import mock

from helpers import SRC, WorklineTestCase, git
from workline import gitcmd, oplock
from workline.errors import StopError
from workline.review import hermetic, paths as review_paths

#: The root class B scratch of §31.8, as root maintenance names it.
ROOT_SCRATCH = hermetic.ScratchPaths(".workline-root-runtime/no-hooks", ".workline-root-runtime/no-config")
PRIMITIVE = ("open_lock_file", "try_exclusive_lock", "names_locked_file", "release_exclusive_lock")


def _function_source(module: object, name: str) -> str:
    tree = ast.parse(inspect.getsource(module))
    found = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(found) != 1:
        raise AssertionError(f"{name} is not one function of {module}")
    return ast.unparse(found[0])


class OsLockPrimitiveTests(WorklineTestCase):
    def lock_path(self) -> Path:
        return self.new_dir("locks") / "maintenance.lock"

    def test_the_primitive_is_public_and_the_project_lock_runs_through_it(self) -> None:
        for name in PRIMITIVE:
            with self.subTest(name=name):
                self.assertIn(name, oplock.__all__)
                self.assertTrue(callable(getattr(oplock, name)))
        self.assertEqual(["store", "operation", "details"], list(inspect.signature(oplock.project_operation).parameters))
        body = _function_source(oplock, "project_operation")
        for name in PRIMITIVE:
            with self.subTest(uses=name):
                self.assertIn(f"{name}(", body)
        self.assertNotIn("os.open(", body, "the Project lock opens its file through the primitive")
        # the order of the Project lock is unchanged: open, lock, prove the name, ... release
        order = [body.index(f"{name}(") for name in PRIMITIVE]
        self.assertEqual(sorted(order), order)
        for retired in ("_try_lock", "_unlock", "_names_locked_file"):
            self.assertFalse(hasattr(oplock, retired), retired)

    def test_one_holder_at_a_time_on_one_file_and_release_frees_it(self) -> None:
        path = self.lock_path()
        first = oplock.open_lock_file(path)
        self.addCleanup(os.close, first)
        second = oplock.open_lock_file(path)
        self.addCleanup(os.close, second)
        self.assertTrue(path.is_file())
        self.assertTrue(oplock.try_exclusive_lock(first))
        self.assertTrue(oplock.names_locked_file(first, path))
        self.assertFalse(oplock.try_exclusive_lock(second), "a second holder never takes a held lock")
        oplock.release_exclusive_lock(first)
        self.assertTrue(oplock.try_exclusive_lock(second))
        oplock.release_exclusive_lock(second)

    def test_another_process_is_refused_without_waiting_while_one_holds_it(self) -> None:
        path = self.lock_path()
        child = subprocess.Popen(
            [sys.executable, "-B", "-c", textwrap.dedent(f"""
                import os, sys
                sys.path.insert(0, {str(SRC)!r})
                from workline import oplock
                fd = oplock.open_lock_file({str(path)!r})
                print("held" if oplock.try_exclusive_lock(fd) else "busy", flush=True)
                sys.stdin.readline()
                oplock.release_exclusive_lock(fd)
                os.close(fd)
            """)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        try:
            self.assertEqual("held", child.stdout.readline().strip())
            fd = oplock.open_lock_file(path)
            try:
                self.assertFalse(oplock.try_exclusive_lock(fd))
            finally:
                os.close(fd)
        finally:
            child.communicate("release\n", timeout=60)
        fd = oplock.open_lock_file(path)
        try:
            self.assertTrue(oplock.try_exclusive_lock(fd), "the OS let go when its holder did")
            oplock.release_exclusive_lock(fd)
        finally:
            os.close(fd)

    @unittest.skipIf(os.name == "nt", "an open file cannot be replaced on Windows")
    def test_a_replaced_lock_file_is_not_the_locked_one(self) -> None:
        path = self.lock_path()
        fd = oplock.open_lock_file(path)
        self.addCleanup(os.close, fd)
        self.assertTrue(oplock.try_exclusive_lock(fd))
        path.unlink()
        path.write_bytes(b"")
        self.assertFalse(oplock.names_locked_file(fd, path))
        oplock.release_exclusive_lock(fd)


class ProjectScratchTests(WorklineTestCase):
    def test_a_projects_class_b_scratch_is_where_it_always_was(self) -> None:
        self.assertEqual(".workline/runtime/review/no-hooks", hermetic.PROJECT_SCRATCH.no_hooks)
        self.assertEqual(".workline/runtime/review/no-config", hermetic.PROJECT_SCRATCH.no_config)
        self.assertEqual((review_paths.RUNTIME_NO_HOOKS_DIR, review_paths.RUNTIME_NO_CONFIG_FILE),
                         (hermetic.PROJECT_SCRATCH.no_hooks, hermetic.PROJECT_SCRATCH.no_config))
        store = self.new_project()
        git(store.root, "config", "user.name", "Real Person")
        git(store.root, "config", "user.email", "real@proj")
        hooks = os.path.abspath(store.root / review_paths.RUNTIME_NO_HOOKS_DIR)
        config = os.path.abspath(store.root / review_paths.RUNTIME_NO_CONFIG_FILE)
        self.assertEqual(hooks, hermetic.no_hooks_directory(store))
        self.assertEqual(config, hermetic.no_config_file(store))
        built = hermetic.enter(store)
        self.assertEqual(config, built.environment()["GIT_CONFIG_GLOBAL"])
        self.assertIn(f"core.hooksPath={hooks}", built.configuration_arguments())
        self.assertIn(f"core.attributesFile={config}", built.attribute_configuration_arguments("0" * 40))
        self.assertEqual(["store"], list(inspect.signature(hermetic.enter).parameters))

    def test_a_scratch_path_is_repository_relative(self) -> None:
        for value in ("/abs/no-hooks", "C:/no-hooks", "a/../no-hooks", "", "a\\no-hooks", "./no-hooks", "a//b", "a/"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                hermetic.ScratchPaths(value, ".workline-root-runtime/no-config")
            with self.subTest(config=value), self.assertRaises(ValueError):
                hermetic.ScratchPaths(".workline-root-runtime/no-hooks", value)


class RootClassBEntryTests(WorklineTestCase):
    """RB7C-5 / N-3: every root commit is class B, entered for the root with root-runtime scratch."""

    def setUp(self) -> None:
        super().setUp()
        self.root = self.new_dir("workline-root")
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "Root Maintainer")
        git(self.root, "config", "user.email", "root@maintainer")

    def test_the_root_entry_uses_root_runtime_scratch_and_never_creates_workline(self) -> None:
        built = hermetic.enter_root(self.root, ROOT_SCRATCH)
        hooks = os.path.abspath(self.root / ".workline-root-runtime" / "no-hooks")
        config = os.path.abspath(self.root / ".workline-root-runtime" / "no-config")
        self.assertEqual(config, built.environment()["GIT_CONFIG_GLOBAL"])
        self.assertIn(f"core.hooksPath={hooks}", built.configuration_arguments())
        self.assertEqual(("Root Maintainer", "root@maintainer"), (built.identity.name, built.identity.email))
        self.assertEqual("false", built.run("config", "--get", "core.autocrlf").stdout.strip())
        self.assertTrue(Path(hooks).is_dir() and Path(config).is_file())
        self.assertFalse((self.root / ".workline").exists())

    def test_the_global_configuration_takes_no_part(self) -> None:
        home = self.new_dir("hostile-home")
        (home / ".gitconfig").write_text("[core]\n\tautocrlf = true\n[filter \"lfs\"]\n\tclean = false\n",
                                         encoding="utf-8")
        with mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
            built = hermetic.enter_root(self.root, ROOT_SCRATCH)
            self.assertEqual("false", built.run("config", "--get", "core.autocrlf").stdout.strip())
            self.assertFalse(built.run("config", "--get", "filter.lfs.clean", check=False).ok)

    def test_a_project_scratch_is_refused_for_the_root_before_anything_is_created(self) -> None:
        for scratch in (hermetic.PROJECT_SCRATCH,
                        hermetic.ScratchPaths(".workline/no-hooks", ".workline-root-runtime/no-config"),
                        hermetic.ScratchPaths(".workline-root-runtime/no-hooks", ".workline/no-config")):
            with self.subTest(scratch=scratch), self.assertRaises(ValueError):
                hermetic.enter_root(self.root, scratch)
        self.assertFalse((self.root / ".workline").exists())
        self.assertFalse((self.root / ".workline-root-runtime").exists())

    def test_an_unconfigured_root_identity_stops_at_entry_and_writes_nothing(self) -> None:
        git(self.root, "config", "--unset", "user.name")
        home = self.new_dir("empty-home")
        with mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
            with self.assertRaises(StopError) as caught:
                hermetic.enter_root(self.root, ROOT_SCRATCH)
        self.assertEqual("review_identity_unavailable", caught.exception.code)
        self.assertFalse((self.root / ".workline-root-runtime").exists())
        self.assertFalse((self.root / ".workline").exists())

    def test_a_non_empty_root_scratch_stops_before_any_commit(self) -> None:
        built = hermetic.enter_root(self.root, ROOT_SCRATCH)
        (self.root / ".workline-root-runtime" / "no-hooks" / "pre-commit").write_text("exit 1\n", encoding="utf-8")
        with self.assertRaises(StopError) as caught:
            built.configuration_arguments()
        self.assertEqual("review_hooks_path_invalid", caught.exception.code)
        (self.root / ".workline-root-runtime" / "no-hooks" / "pre-commit").unlink()
        (self.root / ".workline-root-runtime" / "no-config").write_text("[user]\n\tname = x\n", encoding="utf-8")
        with self.assertRaises(StopError) as caught:
            hermetic.enter_root(self.root, ROOT_SCRATCH)
        self.assertEqual("review_no_config_file_invalid", caught.exception.code)


class RulesGitRootMaintenanceTests(unittest.TestCase):
    """§31.47 / AO-1: rules/git states root policy maintenance; rules/human-confirmation is untouched; no new route."""

    def registry(self) -> str:
        from helpers import WORKLINE_ROOT

        return WORKLINE_ROOT.joinpath("registry.md").read_text(encoding="utf-8").replace("\r\n", "\n")

    def test_the_section_is_inside_rules_git_and_states_the_rules(self) -> None:
        text = self.registry()
        rules_git = text[text.index("<!-- workline-id: rules/git -->"):text.index("## AI Decision")]
        self.assertLess(text.index("### Root policy maintenance"), text.index("<!-- workline-id: rules/ai-decision -->"))
        section = rules_git[rules_git.index("### Root policy maintenance"):]
        for phrase in ("`global-policy-change`", "`global-policy-evaluation`", "`review-policy/global-policy.yaml`",
                       "`.workline-root-runtime/`", "`global-policy.lock`", "`root-policy-maintenance-status`",
                       "`root-policy-maintenance-authorize`", "`base_exact`", "Kp", "Km", "`reconcile required`",
                       "`.workline/`", "force", "rebase", "reset", "amend", "`<exact commit>:<full ref>`",
                       "`rules/human-confirmation`"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, section)
        self.assertNotRegex(section, r"BL-\d{3}")
        self.assertEqual(1, text.count("### Root policy maintenance"))

    def test_no_new_routing_id(self) -> None:
        import re

        ids = re.findall(r"<!-- workline-id: ([^ ]+) -->", self.registry())
        self.assertNotIn("skills/global-policy", ids)
        self.assertFalse([found for found in ids if "root" in found or "global-policy" in found])


class RootRepositoryFactsTests(WorklineTestCase):
    """§31.13: the read-only Git facts root maintenance binds into its opaque local repository identity."""

    def test_the_common_directory_and_object_format_are_read_without_writing(self) -> None:
        root = self.new_dir("workline-root")
        git(root, "init", "-b", "main")
        git(root, "commit", "-q", "--allow-empty", "-m", "base")
        before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
        self.assertEqual((root / ".git").resolve(), gitcmd.git_common_dir(root))
        self.assertEqual("sha1", gitcmd.object_format(root))
        self.assertEqual(before, sorted(str(path.relative_to(root)) for path in root.rglob("*")))

    def test_every_worktree_shares_the_common_directory(self) -> None:
        root = self.new_dir("workline-root")
        git(root, "init", "-b", "main")
        git(root, "commit", "-q", "--allow-empty", "-m", "base")
        other = self.tmp / "other-worktree"
        git(root, "worktree", "add", "-q", "-b", "other", str(other))
        self.assertEqual(gitcmd.git_common_dir(root), gitcmd.git_common_dir(other))
        self.assertNotEqual(root.resolve(), other.resolve())

    def test_outside_a_repository_there_is_no_answer(self) -> None:
        outside = self.new_dir("not-a-repository")
        with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(self.tmp)}):
            self.assertIsNone(gitcmd.git_common_dir(outside))
            self.assertIsNone(gitcmd.object_format(outside))


if __name__ == "__main__":
    unittest.main()
