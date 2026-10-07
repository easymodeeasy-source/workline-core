"""P7 compatibility regression (``WORKLINE_COMPLETION_SPRINT`` §31.59): what RB7 shares with Projects stays theirs.

RB7-F foundation rows:

* the OS lock primitive (§31.9) is extracted from the Project execution lock
  without changing it: the Project lock still runs every step it ran, in the same
  order, now through the public primitive the root maintenance lock uses too;
* the class B scratch (§31.8 / §31.30, RB7C-5): a Project's stays exactly where it
  was, and the root's class B entry uses root-runtime scratch and can never name
  ``.workline/`` - no root operation creates the Project namespace;
* the two read-only Git facts the opaque root repository identity is built from
  (§31.13): the common directory and the object format;
* rules/git "Root policy maintenance" (§31.47, AO-1) and no new routing ID;
* the two root CLI commands (§31.12, RB7C-6): bound like every command but
  ``status``, targeting the launcher's own root, the mutation-capable one refused
  inside a Project before the lock.

The §31.59 rows that need the root owner (Project Review / Mutation Controller
unchanged end to end, no ``.workline`` after every root operation) are added with
it.
"""

from __future__ import annotations

import ast
import inspect
import json
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


class RootCliBindingTests(WorklineTestCase):
    """RB7C-6 / §31.12: the two root commands bind to the launcher's own root; the binding exception stays ``status``."""

    STATUS_KEYS = {"status", "global_policy", "current_change_id", "evaluation_ids", "authorization",
                   "pending_mutation", "next_boundary_adapter_identity"}

    def p7_root(self, name: str = "workline-root") -> Path:
        """A git-initialized copy of this root carrying its tracked Global policy and root ignore rule."""
        from helpers import WORKLINE_ROOT, copy_workline_root
        from workline.review import policy

        root = copy_workline_root(self.tmp / name)
        for relative in (".gitignore", policy.GLOBAL_POLICY_REL):
            target = root.joinpath(*relative.split("/"))
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(WORKLINE_ROOT.joinpath(*relative.split("/")).read_bytes().replace(b"\r\n", b"\n"))
        git(root, "init", "-q", "-b", "main")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "base")
        return root

    def run_root(self, root: Path, *args: str, cwd: Path) -> "subprocess.CompletedProcess":
        from helpers import launcher_command, run_python

        return run_python(launcher_command(root, *args), cwd=cwd)

    def test_the_binding_exception_is_still_status_alone(self) -> None:
        from workline import cli

        self.assertEqual("status", cli.READ_ONLY_STATUS_COMMAND)
        for command in (cli.ROOT_STATUS_COMMAND, cli.ROOT_AUTHORIZE_COMMAND):
            with self.subTest(command=command):
                self.assertTrue(cli.binds_invocation_project([command]))
                self.assertTrue(cli.binds_invocation_project([command, "--json"]))

    def test_status_from_the_root_reports_and_creates_nothing(self) -> None:
        root = self.p7_root()
        done = self.run_root(root, "root-policy-maintenance-status", "--json", cwd=root)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        report = json.loads(done.stdout)
        self.assertEqual(self.STATUS_KEYS, set(report))
        self.assertEqual(("materialized-global-policy", 1),
                         (report["global_policy"]["source_mode"], report["global_policy"]["version"]))
        self.assertEqual("not_required", report["authorization"]["status"])
        human = self.run_root(root, "root-policy-maintenance-status", cwd=root)
        self.assertEqual(0, human.returncode, human.stdout + human.stderr)
        self.assertIn("global policy: materialized-global-policy v1", human.stdout)
        self.assertFalse((root / ".workline-root-runtime").exists(), "status writes no runtime")
        self.assertFalse((root / ".workline").exists())
        self.assertEqual("", git(root, "status", "--porcelain"))

    def test_authorize_from_the_root_writes_only_its_authorization(self) -> None:
        root = self.p7_root()
        bare = self.tmp / "root-remote.git"
        git(self.tmp, "init", "--bare", "-q", "-b", "main", str(bare))
        git(root, "remote", "add", "origin", str(bare))
        done = self.run_root(root, "root-policy-maintenance-authorize", "--remote", "origin", "--branch",
                             "refs/heads/main", "--locator", str(bare), cwd=root)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("remote=origin branch=refs/heads/main", done.stdout)
        self.assertTrue((root / ".workline-root-runtime" / "maintenance-authorization.yaml").is_file())
        self.assertEqual("", git(root, "status", "--porcelain"), "the root runtime is ignored; nothing else changed")
        report = json.loads(self.run_root(root, "root-policy-maintenance-status", "--json", cwd=root).stdout)
        self.assertEqual({"status": "valid", "remote": "origin", "branch": "refs/heads/main"}, report["authorization"])
        self.assertNotIn(str(bare), json.dumps(report))
        self.assertNotIn(str(bare).replace("\\", "\\\\"), json.dumps(report))
        self.assertFalse((root / ".workline").exists())

    def test_authorize_inside_a_project_is_refused_before_the_lock(self) -> None:
        root = self.p7_root()
        project = self.new_dir("project")
        git(project, "init", "-q", "-b", "main")
        started = self.run_root(root, "project-start", str(project), "--workline-root", str(root), cwd=root)
        self.assertEqual(0, started.returncode, started.stdout + started.stderr)
        done = self.run_root(root, "root-policy-maintenance-authorize", "--remote", "origin", "--branch",
                             "refs/heads/main", "--locator", "unused", cwd=project)
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertIn("review_p7_root_project_context", done.stdout)
        self.assertFalse((root / ".workline-root-runtime").exists(), "refused before the lock: nothing created")

    def test_root_commands_inside_a_project_of_another_root_are_bound(self) -> None:
        root = self.p7_root()
        store = self.new_project("other-root-project")  # configured to this checkout's root, not to the copy
        for args in (("root-policy-maintenance-status", "--json"),
                     ("root-policy-maintenance-authorize", "--remote", "origin", "--branch", "refs/heads/main",
                      "--locator", "unused")):
            with self.subTest(command=args[0]):
                done = self.run_root(root, *args, cwd=store.root)
                self.assertEqual(1, done.returncode, done.stdout + done.stderr)
                self.assertIn("workline_implementation_mismatch", done.stdout)
        self.assertFalse((root / ".workline-root-runtime").exists())


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
