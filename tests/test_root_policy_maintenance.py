"""Workline-root policy maintenance runtime (P7 §31.54, §31.8-§31.13, §31.46; addendum RB7C-4/5/6/7/9).

Lock exclusivity (cross-process) and no Project lock / state; the runtime layout
and its ignore rule; remote-less mode; explicit authorization, copied
authorization rejected (other clone / other worktree), locator / branch mismatch,
multiple / unreadable / secret-bearing locator; the read-only status report
(creates nothing, no forbidden key, no locator); an identity-unconfigured root
STOPs at entry; non-empty scratch STOPs; a mutation-capable entry inside a
Project is refused before the lock; never ``<root>/.workline``; reservation
replay-stability; the closed effect set; the committability preflight.

Every root here is a temporary Git repository. The running implementation's
root is patched to it where an entry check needs that (the one fact a temporary
root cannot be); one row proves the real binding without any patch, from a copied
Workline root's own implementation.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
import unittest
from unittest import mock

from helpers import SRC, WORKLINE_ROOT, WorklineTestCase, copy_workline_root, cwd, git, run_python
from workline import gitcmd, ids, implementation, oplock
from workline import root_maintenance as rm
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.review import fsafe, hermetic, serialize
from workline.review import policy
from workline.review.namespace import ROOT_POLICY_LAYOUT, ROOT_POLICY_REVIEW_NAMESPACE

IGNORE_RULE = ".workline-root-runtime/\n"
FORBIDDEN_KEYS = {"cwd", "pid", "host", "hostname", "time", "timestamp", "at", "created_at", "updated_at",
                  "acquired_at", "generated_at"}
DATE = "1700000000 +0000"
CAN_CREATE = fsafe.immutable_create_supported()


def make_junction(link: Path, target: Path) -> bool:
    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
    return made.returncode == 0


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def keys_at_any_depth(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            found |= keys_at_any_depth(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            found |= keys_at_any_depth(item)
    return found


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """Every path under ``root`` (``.git`` included) with its size and modification time."""
    found: dict[str, tuple[int, int]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            info = os.lstat(path)
            found[path.relative_to(root).as_posix()] = (info.st_size if not path.is_dir() else 0, info.st_mtime_ns)
    return found


def v1_global_policy() -> dict:
    return policy.global_policy_record(1, None, {s.policy_surface_id: s.global_setting for s in policy.SURFACES})


def v2_global_policy() -> dict:
    before = v1_global_policy()
    return policy.global_policy_record(2, policy.global_policy_digest(before),
                                       {policy.SURFACE_REQUIRED_SLOTS: 2, policy.SURFACE_EXTRA_SCOPE_STEPS: 0})


class RootCase(WorklineTestCase):
    """A git-initialized Workline root (the runtime ignore rule committed) that the running implementation binds to."""

    def setUp(self) -> None:
        super().setUp()
        self.root = self.make_root("workline-root")
        self.bind(self.root)
        self.enter(self.root)

    def make_root(self, name: str, *, ignore: bool = True, source: Path | None = None) -> Path:
        root = source if source is not None else self.new_dir(name)
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.name", "Root Maintainer")
        git(root, "config", "user.email", "root@maintainer.invalid")
        (root / ".gitignore").write_bytes(IGNORE_RULE.encode("utf-8") if ignore else b"")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "base")
        return root.resolve()

    def bind(self, root: Path | None) -> None:
        patcher = mock.patch.object(implementation, "running_workline_root", return_value=root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def head(self, root: Path | None = None) -> str:
        return git(root or self.root, "rev-parse", "HEAD").strip()

    def assertNoWorkline(self, root: Path | None = None) -> None:
        self.assertFalse(os.path.lexists((root or self.root) / ".workline"), "the Workline root never gets .workline")

    def assertStop(self, code: str, call, *args, **kwargs) -> StopError:
        with self.assertRaises(StopError) as caught:
            call(*args, **kwargs)
        self.assertEqual(code, caught.exception.code, str(caught.exception))
        return caught.exception

    def assertReconcile(self, reason: str, call, *args, **kwargs) -> ReconcileRequired:
        with self.assertRaises(ReconcileRequired) as caught:
            call(*args, **kwargs)
        self.assertEqual(reason, caught.exception.reason, str(caught.exception))
        return caught.exception

    def fake_project(self) -> Path:
        project = self.new_dir("some-project")
        (project / ".workline").mkdir()
        (project / ".workline" / "project.yaml").write_text("schema: fake\n", encoding="utf-8")
        return project

    def add_remote(self, root: Path | None = None, name: str = "root-remote") -> Path:
        bare = self.tmp / f"{name}.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(bare))
        git(root or self.root, "remote", "add", "origin", str(bare))
        return bare

    def git_clean(self, root: Path | None = None) -> str:
        return git(root or self.root, "status", "--porcelain", "--untracked-files=all")


# --------------------------------------------------------------------------- layout and catalogue


class LayoutTests(WorklineTestCase):
    def test_the_frozen_runtime_layout(self) -> None:
        self.assertEqual(".workline-root-runtime", rm.RUNTIME_DIR)
        self.assertEqual(".workline-root-runtime/global-policy.lock", rm.LOCK_REL)
        self.assertEqual(".workline-root-runtime/holder.json", rm.HOLDER_REL)
        self.assertEqual(".workline-root-runtime/mutations", rm.MUTATIONS_DIR)
        self.assertEqual(".workline-root-runtime/maintenance-authorization.yaml", rm.AUTHORIZATION_REL)
        self.assertEqual(".workline-root-runtime/tmp", rm.TMP_DIR)
        self.assertEqual(tuple(rm.TMP_DIR.split("/")), rm.TMP_PARTS)
        self.assertEqual(hermetic.ScratchPaths(".workline-root-runtime/no-hooks", ".workline-root-runtime/no-config"),
                         rm.ROOT_GIT_SCRATCH)
        for relative in (rm.LOCK_REL, rm.HOLDER_REL, rm.MUTATIONS_DIR, rm.AUTHORIZATION_REL, rm.TMP_DIR,
                         rm.ROOT_GIT_SCRATCH.no_hooks, rm.ROOT_GIT_SCRATCH.no_config):
            with self.subTest(relative=relative):
                self.assertTrue(relative.startswith(rm.RUNTIME_DIR + "/"))
                self.assertFalse(relative.startswith(".workline/"))
        self.assertEqual(("global-policy-change", "global-policy-evaluation"), rm.OPERATIONS)
        self.assertEqual("workline-root-policy-mutation", rm.MUTATION_SCHEMA)
        self.assertEqual(1, rm.MUTATION_VERSION)
        self.assertEqual("workline-root-maintenance-authorization", rm.AUTHORIZATION_SCHEMA)
        self.assertEqual("workline-root-maintenance-authorization-v1", rm.AUTHORIZATION_CONTRACT)
        self.assertEqual(("pending", "completed", "abandoned"),
                         (rm.STATUS_PENDING, rm.STATUS_COMPLETED, rm.STATUS_ABANDONED))
        self.assertEqual("root_maintenance", rm.STATUS_KEY)

    def test_the_closed_effect_set(self) -> None:
        self.assertEqual(
            ("root-review-create", "promotion-packet-create", "global-change-create", "patch-note-create",
             "global-policy-replace", "global-consumption-create", "global-evaluation-create", "root-commit",
             "root-push"),
            rm.ROOT_EFFECT_KINDS)
        self.assertEqual(tuple(kind for kind in rm.ROOT_EFFECT_KINDS if kind != rm.EFFECT_EVALUATION_CREATE),
                         rm.OPERATION_EFFECTS[rm.OPERATION_CHANGE])
        self.assertEqual((rm.EFFECT_EVALUATION_CREATE, rm.EFFECT_COMMIT, rm.EFFECT_PUSH),
                         rm.OPERATION_EFFECTS[rm.OPERATION_EVALUATION])
        self.assertNotIn(rm.EFFECT_GLOBAL_POLICY_REPLACE, rm.OPERATION_EFFECTS[rm.OPERATION_EVALUATION],
                         "the evaluation sub-operation never writes the Global policy (§31.42)")
        self.assertEqual(("review_run", "review_task", "review_receipt", "review_consumption",
                          "review_promotion_packet", "review_global_policy_change",
                          "review_global_policy_evaluation"), rm.RESERVATION_KINDS)
        for kind in rm.RESERVATION_KINDS + ("root_policy_mutation",):
            with self.subTest(kind=kind):
                self.assertTrue(ids.is_valid_id(ids.new_id(kind), kind))

    def test_the_frozen_api(self) -> None:
        import dataclasses
        import inspect

        def shape(function) -> list[tuple[str, str]]:
            return [(name, parameter.kind.name) for name, parameter in inspect.signature(function).parameters.items()]

        positional, keyword = "POSITIONAL_OR_KEYWORD", "KEYWORD_ONLY"
        self.assertEqual([("workline_root", positional)], shape(rm.require_root_target))
        self.assertEqual([], shape(rm.require_root_invocation))
        self.assertEqual([("workline_root", positional), ("operation", positional), ("details", positional)],
                         shape(rm.root_operation))
        self.assertEqual([("lock", positional)], shape(rm.enter_git))
        self.assertEqual([("lock", positional), ("invocation", positional), ("branch", keyword), ("base", keyword),
                          ("global_policy_version", keyword), ("global_policy_digest", keyword),
                          ("write_scope", keyword), ("publication", keyword), ("rebind", keyword),
                          ("reserved", keyword)],
                         shape(rm.open_mutation))
        self.assertIsNone(inspect.signature(rm.open_mutation).parameters["rebind"].default)
        self.assertIsNone(inspect.signature(rm.open_mutation).parameters["reserved"].default)
        for function in (rm.pending_mutations, rm.repository_identity, rm.read_authorization, rm.publication_binding,
                         rm.status_report):
            with self.subTest(function=function.__name__):
                self.assertEqual([("workline_root", positional)], shape(function))
        self.assertEqual([("workline_root", positional), ("review_run_id", positional)], shape(rm.pending_for_run))
        self.assertEqual([("workline_root", positional), ("relatives", positional)], shape(rm.require_committable))
        self.assertEqual([("workline_root", positional), ("remote", keyword), ("branch", keyword),
                          ("locator", keyword)], shape(rm.authorize))
        self.assertEqual(["root", "operation", "details"], [field.name for field in dataclasses.fields(rm.RootLock)])
        self.assertEqual(["remote", "branch", "locator", "repository_identity"],
                         [field.name for field in dataclasses.fields(rm.Authorization)])
        self.assertEqual(["remote", "branch", "locator"],
                         [field.name for field in dataclasses.fields(rm.PublicationBinding)])
        for name, parameters in (("reserve_id", ["key", "kind"]), ("reserved", ["key"]), ("note", ["key"]),
                                 ("set_note", ["key", "value"]), ("add_effect", ["kind", "payload"]),
                                 ("apply_effect", ["index"]), ("mark_effect", ["index", "facts"]), ("effects", []),
                                 ("complete", []), ("abandon", [])):
            with self.subTest(method=name):
                self.assertEqual(["self", *parameters],
                                 list(inspect.signature(getattr(rm.RootMutation, name)).parameters))
        for name in ("mutation_id", "operation", "record"):
            self.assertIsInstance(getattr(rm.RootMutation, name), property)

    def test_the_catalogue(self) -> None:
        frozen_stop = {
            "review_p7_root_binding_mismatch", "review_p7_root_is_project", "review_p7_root_project_context",
            "review_p7_root_not_repository", "review_p7_root_runtime_invalid", "review_p7_root_runtime_unignored",
            "review_p7_root_busy", "review_p7_root_nested", "review_p7_root_lock_unavailable",
            "review_p7_authorization_required", "review_p7_authorization_mismatch",
            "review_p7_authorization_invalid", "review_p7_repository_identity_unavailable",
            "review_p7_root_effect_refused",
        }
        frozen_reasons = {"review_p7_root_mutation_conflict", "review_p7_root_mutation_unreadable",
                          "review_p7_root_effect_conflict"}
        self.assertTrue(frozen_stop <= set(rm.STOP_CODES))
        self.assertTrue(frozen_reasons <= set(rm.RECONCILE_REASONS))
        self.assertEqual({"review_p7_root_lock_not_held"}, set(rm.STOP_CODES) - frozen_stop)
        self.assertEqual({"review_p7_root_abandon_refused"}, set(rm.RECONCILE_REASONS) - frozen_reasons)
        every = rm.STOP_CODES + rm.RECONCILE_REASONS
        self.assertEqual(len(every), len(set(every)))
        self.assertTrue(all(code.startswith("review_p7_") for code in every))
        with self.assertRaises(ValueError):
            rm.stop("review_p7_not_declared", "x")
        with self.assertRaises(ValueError):
            rm.reconcile("x", "review_p7_root_busy")
        self.assertEqual("review_p7_root_busy", rm.stop("review_p7_root_busy", "x").code)
        self.assertEqual("review_p7_root_effect_conflict", rm.reconcile("x", "review_p7_root_effect_conflict").reason)

    def test_the_module_holds_no_project_machinery(self) -> None:
        import ast
        import re

        source = (SRC / "workline" / "root_maintenance.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                imported.setdefault("." * node.level + (node.module or ""), set()).update(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertFalse(alias.name.startswith("workline"), alias.name)
        # the import DAG of the foundation interfaces (section 0): nothing of the Project machinery
        self.assertEqual({".", ".durable", ".errors", ".review", ".review.namespace"}, set(imported))
        self.assertEqual({"context", "destination", "gitcmd", "ids", "implementation", "oplock", "pushurl"},
                         imported["."])
        self.assertEqual({"fsafe", "hermetic", "serialize", "policy"}, imported[".review"])
        self.assertEqual({"ROOT_POLICY_LAYOUT", "ROOT_POLICY_REVIEW_NAMESPACE"}, imported[".review.namespace"])
        used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        for absent in ("ProjectStore", "project_operation", "MutationController", "contained_add",
                       "contained_commit", "g4_history", "next_generation_scope", "pending_generation_mutations",
                       "record_preexisting_dirty", "finalize"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, used)
        self.assertNotIn("review_p6_", source)
        # every review_p7_ literal is declared exactly once, in the catalogue constants
        literals = re.findall(r'"(review_p7_[a-z_]+)"', source)
        self.assertEqual(sorted(set(rm.STOP_CODES + rm.RECONCILE_REASONS)), sorted(literals))
        # the only .workline name the module spells is the one it refuses
        self.assertEqual(['".workline"'], re.findall(r'"\.workline(?:/[^"]*)?"', source))

    def test_the_real_workline_root_ignores_the_runtime(self) -> None:
        self.assertIn(".workline-root-runtime/", (WORKLINE_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())
        self.assertIs(True, gitcmd.is_ignored(WORKLINE_ROOT, rm.RUNTIME_DIR + "/"))


# --------------------------------------------------------------------------- entry checks (RB7C-6)


class EntryTests(RootCase):
    def test_the_bound_root_passes_and_writes_nothing(self) -> None:
        before = snapshot(self.root)
        self.assertEqual(self.root, rm.require_root_target(self.root))
        rm.require_root_invocation()
        self.assertEqual(before, snapshot(self.root))

    def test_another_running_root_is_a_binding_mismatch(self) -> None:
        other = self.make_root("other-root")
        for running in (other, None):
            with self.subTest(running=running):
                with mock.patch.object(implementation, "running_workline_root", return_value=running):
                    self.assertStop("review_p7_root_binding_mismatch", rm.require_root_target, self.root)
                    with self.assertRaises(StopError) as caught, rm.root_operation(self.root, rm.OPERATION_CHANGE):
                        pass
                    self.assertEqual("review_p7_root_binding_mismatch", caught.exception.code)
        self.assertFalse(os.path.lexists(self.root / rm.RUNTIME_DIR))

    def test_a_root_holding_any_workline_entry_is_refused(self) -> None:
        for make in (lambda path: path.mkdir(), lambda path: path.write_text("", encoding="utf-8"),
                     lambda path: (path.mkdir(), (path / "project.yaml").write_text("x: 1\n", encoding="utf-8"))):
            with self.subTest(make=make):
                target = self.root / ".workline"
                make(target)
                try:
                    self.assertStop("review_p7_root_is_project", rm.require_root_target, self.root)
                    with self.assertRaises(StopError) as caught, rm.root_operation(self.root, rm.OPERATION_CHANGE):
                        pass
                    self.assertEqual("review_p7_root_is_project", caught.exception.code)
                    self.assertFalse(os.path.lexists(self.root / rm.RUNTIME_DIR))
                finally:
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()

    def test_a_root_that_is_not_its_own_repository_top_level_is_refused(self) -> None:
        inner = self.root / "nested"
        inner.mkdir()
        with mock.patch.object(implementation, "running_workline_root", return_value=inner.resolve()):
            self.assertStop("review_p7_root_not_repository", rm.require_root_target, inner)
        outside = self.new_dir("no-repository")
        with mock.patch.object(implementation, "running_workline_root", return_value=outside.resolve()), \
                mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(self.tmp)}):
            self.assertStop("review_p7_root_not_repository", rm.require_root_target, outside)

    def test_a_mutation_capable_entry_inside_a_project_is_refused_before_the_lock(self) -> None:
        project = self.fake_project()
        self.add_remote()
        with cwd(project):
            self.assertStop("review_p7_root_project_context", rm.require_root_invocation)
            for operation in rm.LOCK_OPERATIONS:
                with self.subTest(operation=operation):
                    with self.assertRaises(StopError) as caught, rm.root_operation(self.root, operation):
                        pass
                    self.assertEqual("review_p7_root_project_context", caught.exception.code)
            self.assertStop("review_p7_root_project_context", rm.authorize, self.root, remote="origin",
                            branch="refs/heads/main", locator=str(self.tmp / "root-remote.git"))
        self.assertFalse(os.path.lexists(self.root / rm.RUNTIME_DIR), "refused before the lock: nothing created")
        self.assertNoWorkline()
        # from a directory that is neither a Project nor the root, the binding is the root's own
        with cwd(self.new_dir("elsewhere")):
            rm.require_root_invocation()
            with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
                self.assertEqual(self.root, lock.root)

    def test_the_real_binding_from_a_copied_roots_own_implementation(self) -> None:
        copy = copy_workline_root(self.tmp / "copied-root")
        self.make_root("unused", source=copy)
        script = textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(copy / 'src')!r})
            from pathlib import Path
            from workline import root_maintenance as rm
            from workline.errors import StopError
            print(rm.require_root_target(Path({str(copy)!r})))
            try:
                rm.require_root_target(Path({str(self.root)!r}))
            except StopError as exc:
                print(exc.code)
        """)
        env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        done = run_python([sys.executable, "-B", "-c", script], cwd=copy, env=env)
        self.assertEqual(0, done.returncode, done.stderr)
        lines = done.stdout.strip().splitlines()
        self.assertEqual(str(copy), lines[0])
        self.assertEqual("review_p7_root_binding_mismatch", lines[1])
        self.assertNoWorkline(copy)


# --------------------------------------------------------------------------- the root lock (§31.9)


class LockTests(RootCase):
    def test_the_lock_lifecycle_and_layout(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE, {"request": "x"}) as lock:
            self.assertEqual((self.root, rm.OPERATION_CHANGE, {"request": "x"}), (lock.root, lock.operation,
                                                                                  lock.details))
            runtime = self.root / rm.RUNTIME_DIR
            self.assertTrue(runtime.is_dir() and not runtime.is_symlink())
            self.assertTrue((self.root / rm.LOCK_REL).is_file())
            self.assertTrue((self.root / rm.TMP_DIR).is_dir())
            holder = json.loads((self.root / rm.HOLDER_REL).read_text(encoding="utf-8"))
            self.assertEqual(rm.OPERATION_CHANGE, holder["operation"])
            self.assertEqual("", self.git_clean(), "the runtime is ignored: nothing of it is dirt")
        self.assertFalse((self.root / rm.HOLDER_REL).exists(), "the holder description goes with the lock")
        self.assertTrue((self.root / rm.LOCK_REL).is_file(), "no lock cleanup either")
        with rm.root_operation(self.root, rm.OPERATION_EVALUATION):
            pass
        self.assertNoWorkline()
        self.assertEqual("", self.git_clean())

    def test_a_nested_root_operation_is_refused(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE):
            for operation in rm.LOCK_OPERATIONS:
                with self.subTest(operation=operation):
                    with self.assertRaises(StopError) as caught, rm.root_operation(self.root, operation):
                        pass
                    self.assertEqual("review_p7_root_nested", caught.exception.code)
            self.assertTrue((self.root / rm.HOLDER_REL).exists(), "the refused nested entry touched nothing")

    def test_the_lock_is_released_however_the_block_exits(self) -> None:
        with self.assertRaises(RuntimeError), rm.root_operation(self.root, rm.OPERATION_CHANGE):
            raise RuntimeError("boom")
        with rm.root_operation(self.root, rm.OPERATION_CHANGE):
            pass

    def test_another_process_is_refused_busy_and_nothing_is_written(self) -> None:
        child = subprocess.Popen(
            [sys.executable, "-B", "-c", textwrap.dedent(f"""
                import os, sys
                sys.path.insert(0, {str(SRC)!r})
                from pathlib import Path
                from unittest import mock
                from workline import implementation
                from workline import root_maintenance as rm
                root = Path({str(self.root)!r})
                os.chdir(root)
                with mock.patch.object(implementation, "running_workline_root", return_value=root):
                    with rm.root_operation(root, rm.OPERATION_CHANGE):
                        print("held", flush=True)
                        sys.stdin.readline()
                print("released", flush=True)
            """)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            self.assertEqual("held", child.stdout.readline().strip(), child.stderr.read() if child.poll() else "")
            before = snapshot(self.root)
            for operation in rm.LOCK_OPERATIONS:
                with self.subTest(operation=operation):
                    with self.assertRaises(StopError) as caught, rm.root_operation(self.root, operation):
                        pass
                    self.assertEqual("review_p7_root_busy", caught.exception.code)
                    self.assertIn(rm.OPERATION_CHANGE, str(caught.exception))
            self.assertStop("review_p7_root_busy", rm.authorize, self.root, remote="origin",
                            branch="refs/heads/main", locator="x")
            self.assertEqual(before, snapshot(self.root), "the busy side writes nothing")
        finally:
            out, _ = child.communicate("release\n", timeout=60)
        self.assertEqual("released", out.strip())
        with rm.root_operation(self.root, rm.OPERATION_CHANGE):
            pass

    def test_the_holder_description_never_decides(self) -> None:
        (self.root / rm.RUNTIME_DIR).mkdir()
        (self.root / rm.HOLDER_REL).write_text(json.dumps({"workline": rm.HOLDER_MARKER, "operation":
                                                           rm.OPERATION_CHANGE, "pid": 1}), encoding="utf-8")
        with rm.root_operation(self.root, rm.OPERATION_EVALUATION):
            self.assertEqual(rm.OPERATION_EVALUATION,
                             json.loads((self.root / rm.HOLDER_REL).read_text(encoding="utf-8"))["operation"])
        (self.root / rm.HOLDER_REL).write_text("not json", encoding="utf-8")
        with rm.root_operation(self.root, rm.OPERATION_CHANGE):
            pass

    def test_no_project_lock_and_no_project_state(self) -> None:
        with mock.patch.object(oplock, "project_operation", side_effect=AssertionError("a Project lock")) as project:
            with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
                mutation = rm.open_mutation(lock, {"op": 1}, branch="refs/heads/main", base=self.head(),
                                            global_policy_version=1, global_policy_digest="a" * 64,
                                            write_scope=[ROOT_POLICY_LAYOUT.review_dir + "/"], publication=None)
                mutation.reserve_id("run", "review_run")
                rm.enter_git(lock)
        project.assert_not_called()
        self.assertNoWorkline()
        self.assertEqual("", self.git_clean())

    def test_an_unignored_runtime_is_refused_before_anything_is_created(self) -> None:
        with mock.patch.object(gitcmd, "is_ignored", return_value=None):
            with self.assertRaises(StopError) as caught, rm.root_operation(self.root, rm.OPERATION_CHANGE):
                pass
        self.assertEqual("review_committability_unknown", caught.exception.code)
        self.assertFalse(os.path.lexists(self.root / rm.RUNTIME_DIR))
        unignored = self.make_root("unignored-root", ignore=False)
        with mock.patch.object(implementation, "running_workline_root", return_value=unignored):
            with self.assertRaises(StopError) as caught, rm.root_operation(unignored, rm.OPERATION_CHANGE):
                pass
            self.assertEqual("review_p7_root_runtime_unignored", caught.exception.code)
            self.assertStop("review_p7_root_runtime_unignored", rm.authorize, unignored, remote="origin",
                            branch="refs/heads/main", locator="x")
        self.assertFalse(os.path.lexists(unignored / rm.RUNTIME_DIR), "an unignored root gets nothing")
        self.assertEqual("", self.git_clean(unignored))

    def test_an_indirected_or_odd_runtime_is_refused(self) -> None:
        runtime = self.root / rm.RUNTIME_DIR
        runtime.write_text("", encoding="utf-8")
        with self.assertRaises(StopError) as caught, rm.root_operation(self.root, rm.OPERATION_CHANGE):
            pass
        self.assertEqual("review_p7_root_runtime_invalid", caught.exception.code)
        runtime.unlink()
        runtime.mkdir()
        (self.root / rm.LOCK_REL).mkdir()
        with self.assertRaises(StopError) as caught, rm.root_operation(self.root, rm.OPERATION_CHANGE):
            pass
        self.assertEqual("review_p7_root_runtime_invalid", caught.exception.code)
        (self.root / rm.LOCK_REL).rmdir()
        runtime.rmdir()
        if os.name != "nt":
            return
        target = self.new_dir("elsewhere-runtime")
        if not make_junction(runtime, target):
            self.skipTest("cannot create a junction here")
        with self.assertRaises(StopError) as caught, rm.root_operation(self.root, rm.OPERATION_CHANGE):
            pass
        self.assertEqual("review_p7_root_runtime_invalid", caught.exception.code)
        self.assertEqual([], list(target.iterdir()), "a junctioned runtime is never followed")
        os.rmdir(runtime)
        runtime.mkdir()
        if not make_junction(self.root / rm.TMP_DIR, target):
            self.skipTest("cannot create a junction here")
        with self.assertRaises(StopError) as caught, rm.root_operation(self.root, rm.OPERATION_CHANGE):
            pass
        self.assertEqual("review_p7_root_runtime_invalid", caught.exception.code)
        self.assertEqual([], list(target.iterdir()))
        os.rmdir(self.root / rm.TMP_DIR)
        with rm.root_operation(self.root, rm.OPERATION_CHANGE):
            pass  # the refusal released the lock

    def test_an_unopenable_or_replaced_lock_is_unavailable(self) -> None:
        with mock.patch.object(oplock, "open_lock_file", side_effect=OSError("denied")):
            with self.assertRaises(StopError) as caught, rm.root_operation(self.root, rm.OPERATION_CHANGE):
                pass
        self.assertEqual("review_p7_root_lock_unavailable", caught.exception.code)
        with mock.patch.object(oplock, "names_locked_file", return_value=False):
            with self.assertRaises(StopError) as caught, rm.root_operation(self.root, rm.OPERATION_CHANGE):
                pass
        self.assertEqual("review_p7_root_lock_unavailable", caught.exception.code)
        with rm.root_operation(self.root, rm.OPERATION_CHANGE):
            pass

    def test_only_the_root_operations_take_the_lock(self) -> None:
        for operation in ("project-policy-change", "start", ""):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                with rm.root_operation(self.root, operation):
                    pass
        self.assertFalse(os.path.lexists(self.root / rm.RUNTIME_DIR))


# --------------------------------------------------------------------------- class B root Git entry (RB7C-5)


class GitEntryTests(RootCase):
    def test_the_root_git_uses_root_runtime_scratch(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            built = rm.enter_git(lock)
            hooks = os.path.abspath(self.root / rm.ROOT_GIT_SCRATCH.no_hooks)
            config = os.path.abspath(self.root / rm.ROOT_GIT_SCRATCH.no_config)
            self.assertEqual(config, built.environment()["GIT_CONFIG_GLOBAL"])
            self.assertIn(f"core.hooksPath={hooks}", built.configuration_arguments())
            self.assertEqual(("Root Maintainer", "root@maintainer.invalid"), (built.identity.name,
                                                                              built.identity.email))
            self.assertTrue(rm.tmp_directory(lock).is_dir())
        self.assertNoWorkline()
        self.assertEqual("", self.git_clean())

    def test_an_identity_unconfigured_root_stops_at_entry_and_writes_nothing(self) -> None:
        git(self.root, "config", "--unset", "user.name")
        home = self.new_dir("empty-home")
        with mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
            with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
                self.assertStop("review_identity_unavailable", rm.enter_git, lock)
                self.assertFalse(os.path.lexists(self.root / rm.ROOT_GIT_SCRATCH.no_config))
                self.assertFalse(os.path.lexists(self.root / rm.ROOT_GIT_SCRATCH.no_hooks))
                self.assertFalse(os.path.lexists(self.root / rm.MUTATIONS_DIR))
        self.assertNoWorkline()
        self.assertEqual("", self.git_clean())

    def test_a_non_empty_scratch_stops_before_any_commit(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            built = rm.enter_git(lock)
            hook = self.root / rm.ROOT_GIT_SCRATCH.no_hooks / "pre-commit"
            hook.write_text("exit 1\n", encoding="utf-8")
            self.assertStop("review_hooks_path_invalid", built.configuration_arguments)
            hook.unlink()
            (self.root / rm.ROOT_GIT_SCRATCH.no_config).write_text("[user]\n\tname = x\n", encoding="utf-8")
            self.assertStop("review_no_config_file_invalid", rm.enter_git, lock)

    def test_the_root_git_needs_the_held_lock(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            pass
        self.assertStop("review_p7_root_lock_not_held", rm.enter_git, lock)
        self.assertStop("review_p7_root_lock_not_held", rm.tmp_directory, lock)
        self.assertStop("review_p7_root_lock_not_held", rm.enter_git,
                        rm.RootLock(self.root, rm.OPERATION_CHANGE, {}))


# --------------------------------------------------------------------------- the root mutation (§31.10, §31.11)


class MutationCase(RootCase):
    def setUp(self) -> None:
        super().setUp()
        self.run_id = ids.new_id("review_run")
        self.packet_id = ids.new_id("review_promotion_packet")
        self.change_id = ids.new_id("review_global_policy_change")
        self.gate = ROOT_POLICY_REVIEW_NAMESPACE.gate_rel(self.run_id, 1)
        self.consumption = ROOT_POLICY_REVIEW_NAMESPACE.consumption_rel(ids.new_id("review_consumption"))
        self.packet = ROOT_POLICY_LAYOUT.promotion_packet_rel(self.packet_id)
        self.change = ROOT_POLICY_LAYOUT.global_change_rel(self.change_id)
        self.note = ROOT_POLICY_LAYOUT.patch_note_rel(self.change_id)
        self.scope = [ROOT_POLICY_LAYOUT.review_dir + "/", self.packet, self.change, self.note,
                      ROOT_POLICY_LAYOUT.global_policy_rel]

    def open(self, lock: rm.RootLock, invocation: dict | None = None, **overrides) -> rm.RootMutation:
        arguments = dict(branch="refs/heads/main", base=self.head(), global_policy_version=1,
                         global_policy_digest=policy.global_policy_digest(v1_global_policy()),
                         write_scope=self.scope, publication=None)
        arguments.update(overrides)
        return rm.open_mutation(lock, invocation or {"request_digest": "d" * 64}, **arguments)

    def create(self, path: str, content: str) -> dict:
        return {"path": path, "content": content, "sha256": sha(content)}

    def stored(self, mutation_id: str) -> dict:
        raw = (self.root / rm.MUTATIONS_DIR / f"{mutation_id}.yaml").read_bytes()
        return serialize.parse_canonical(raw, "record")[0]

    def commit_object(self, parent: str, message: str = "root commit") -> tuple[str, str]:
        tree = git(self.root, "rev-parse", f"{parent}^{{tree}}").strip()
        commit = git(self.root, "commit-tree", tree, "-p", parent, "-m", message).strip()
        return commit, tree


class MutationRecordTests(MutationCase):
    def test_a_new_mutation_is_one_durable_canonical_record(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            mutation = self.open(lock, write_scope=list(reversed(self.scope)))
            self.assertTrue(ids.is_valid_id(mutation.mutation_id, "root_policy_mutation"))
            self.assertEqual(rm.OPERATION_CHANGE, mutation.operation)
            record = self.stored(mutation.mutation_id)
            self.assertEqual(set(rm.MUTATION_FIELDS), set(record))
            self.assertEqual(
                {"schema": rm.MUTATION_SCHEMA, "version": 1, "mutation_id": mutation.mutation_id,
                 "operation": rm.OPERATION_CHANGE, "status": "pending", "invocation": {"request_digest": "d" * 64},
                 "branch": "refs/heads/main", "base": self.head(),
                 "global_policy": {"version": 1, "digest": policy.global_policy_digest(v1_global_policy())},
                 "reserved_ids": {}, "write_scope": sorted(self.scope), "effects": [], "notes": {},
                 "publication": None},
                record)
            self.assertEqual(record, dict(mutation.record))
            with self.assertRaises(TypeError):
                mutation.record["status"] = "completed"  # type: ignore[index]
            self.assertEqual([record], rm.pending_mutations(self.root))
        self.assertEqual([record], rm.pending_mutations(self.root), "read without the lock")
        self.assertNoWorkline()
        self.assertEqual("", self.git_clean())

    def test_the_same_invocation_resumes_and_another_is_a_conflict(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            first = self.open(lock)
            run = first.reserve_id("run", "review_run")
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            # RB7BL-2: a resume re-freezes nothing, and a differing frozen value is never silently replaced
            for overrides, named in (({"branch": "refs/heads/other"}, "branch"), ({"base": "0" * 40}, "base"),
                                     ({"global_policy_version": 2}, "global_policy"),
                                     ({"global_policy_version": True}, "global_policy"),
                                     ({"global_policy_digest": "b" * 64}, "global_policy"),
                                     ({"publication": {"remote": "origin", "branch": "refs/heads/main"}},
                                      "publication")):
                with self.subTest(resume=overrides):
                    error = self.assertReconcile("review_p7_root_mutation_conflict", self.open, lock, **overrides)
                    self.assertIn(named, str(error))
            self.assertEqual(dict(first.record), self.stored(first.mutation_id), "a refused resume changes nothing")
            # the write scope is the record's: its exact paths name IDs the mutation itself reserved
            again = self.open(lock, write_scope=[ROOT_POLICY_LAYOUT.global_policy_rel])
            self.assertEqual(first.mutation_id, again.mutation_id)
            self.assertEqual(sorted(self.scope), again.record["write_scope"])
            self.assertEqual(self.head(), again.record["base"])
            self.assertEqual(run, again.reserve_id("run", "review_run"))
            self.assertReconcile("review_p7_root_mutation_conflict", self.open, lock, {"request_digest": "e" * 64})
            self.assertReconcile("review_p7_root_mutation_conflict", self.open, lock, rebind={"run": run})
        with rm.root_operation(self.root, rm.OPERATION_EVALUATION) as lock:
            self.assertReconcile("review_p7_root_mutation_conflict", rm.open_mutation, lock,
                                 {"request_digest": "d" * 64}, branch="refs/heads/main", base=self.head(),
                                 global_policy_version=1, global_policy_digest="a" * 64,
                                 write_scope=[ROOT_POLICY_LAYOUT.global_evaluation_rel(
                                     ids.new_id("review_global_policy_evaluation"))], publication=None)
        self.assertEqual(1, len(list((self.root / rm.MUTATIONS_DIR).iterdir())))

    def test_reservations_are_replay_stable(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            mutation = self.open(lock)
            reserved = {kind: mutation.reserve_id(f"key-{kind}", kind) for kind in rm.RESERVATION_KINDS}
            for kind, value in reserved.items():
                with self.subTest(kind=kind):
                    self.assertTrue(ids.is_valid_id(value, kind))
                    self.assertEqual(value, mutation.reserve_id(f"key-{kind}", kind))
                    self.assertEqual(value, mutation.reserved(f"key-{kind}"))
            self.assertReconcile("review_p7_root_mutation_conflict", mutation.reserve_id, "key-review_run",
                                 "review_task")
            for kind in ("root_policy_mutation", "work", "review_policy_change", "nonsense"):
                with self.subTest(refused=kind):
                    self.assertStop("review_p7_root_effect_refused", mutation.reserve_id, "other", kind)
            self.assertIsNone(mutation.reserved("never"))
        self.assertEqual(reserved, {kind: self.stored(mutation.mutation_id)["reserved_ids"][f"key-{kind}"]
                                    for kind in rm.RESERVATION_KINDS})
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            resumed = self.open(lock)
            for kind, value in reserved.items():
                self.assertEqual(value, resumed.reserve_id(f"key-{kind}", kind))

    def test_a_rebind_pre_seeds_reconstructed_ids_and_allocates_nothing_for_them(self) -> None:
        run, receipt = ids.new_id("review_run"), ids.new_id("review_receipt")
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            for bad in ({"run": "rr_bad"}, {"run": ids.new_id("work")}, {"": run}, {"run": 5}):
                with self.subTest(rebind=bad):
                    self.assertStop("review_p7_root_effect_refused", self.open, lock, rebind=bad)
            # Amendment 4: a recovery open's ID-naming scope paths name rebound IDs (here the Packet / change ones
            # are not rebound, so the scope is refused; the rebind itself is otherwise taken exactly as before)
            self.assertStop("review_p7_root_effect_refused", self.open, lock, rebind={"run": run, "receipt": receipt})
            mutation = self.open(lock, rebind={"run": run, "receipt": receipt, "packet": self.packet_id,
                                               "change": self.change_id})
            self.assertEqual(self.packet_id, mutation.reserve_id("packet", "review_promotion_packet"))
            self.assertEqual(run, mutation.reserve_id("run", "review_run"))
            self.assertEqual(receipt, mutation.reserve_id("receipt", "review_receipt"))
            self.assertReconcile("review_p7_root_mutation_conflict", mutation.reserve_id, "run", "review_receipt")

    def test_notes_are_durable_canonical_data(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            mutation = self.open(lock)
            mutation.set_note("dirty", {"paths": ["a.txt"], "count": 1, "ok": True, "none": None})
            self.assertEqual({"paths": ["a.txt"], "count": 1, "ok": True, "none": None}, mutation.note("dirty"))
            mutation.note("dirty")["paths"].append("b")
            self.assertEqual(["a.txt"], mutation.note("dirty")["paths"], "a note is read as a copy")
            for bad in (1.5, {1: "x"}, object()):
                with self.subTest(value=bad):
                    self.assertStop("review_p7_root_effect_refused", mutation.set_note, "bad", bad)
            self.assertIsNone(mutation.note("bad"))
        self.assertEqual({"paths": ["a.txt"], "count": 1, "ok": True, "none": None},
                         self.stored(mutation.mutation_id)["notes"]["dirty"])

    def test_the_mutation_needs_its_held_lock_and_a_mutation_operation(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_AUTHORIZE) as lock:
            self.assertStop("review_p7_root_effect_refused", self.open, lock)
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            mutation = self.open(lock)
        self.assertStop("review_p7_root_lock_not_held", self.open, lock)
        self.assertStop("review_p7_root_lock_not_held", mutation.reserve_id, "run", "review_run")
        self.assertStop("review_p7_root_lock_not_held", mutation.set_note, "n", 1)
        self.assertStop("review_p7_root_lock_not_held", mutation.add_effect, rm.EFFECT_REVIEW_CREATE,
                        self.create(self.gate, "x: 1\n"))
        with rm.root_operation(self.root, rm.OPERATION_CHANGE):
            self.assertStop("review_p7_root_lock_not_held", mutation.reserve_id, "run", "review_run")

    def test_the_frozen_values_and_the_write_scope_are_closed(self) -> None:
        evaluation = ROOT_POLICY_LAYOUT.global_evaluation_rel(ids.new_id("review_global_policy_evaluation"))
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            for scope in (["README.md"], [".workline/project.yaml"], ["review-policy/../README.md"],
                          ["review-policy/review/gates/x"], ["review-policy/other.yaml"], [evaluation],
                          ["review-policy/changes/"], [".workline-root-runtime/x"], [], "review-policy/review/",
                          [self.change + "\n"], ["/" + self.change], [self.change.replace("/", "\\")]):
                with self.subTest(scope=scope):
                    self.assertStop("review_p7_root_effect_refused", self.open, lock, write_scope=scope)
            for overrides in ({"branch": "main"}, {"branch": "refs/tags/x"}, {"base": "HEAD"},
                              {"base": self.head()[:12]}, {"global_policy_version": 0},
                              {"global_policy_version": True}, {"global_policy_digest": "A" * 64},
                              {"publication": {"remote": "origin", "branch": "refs/heads/main", "locator": "x"}},
                              {"publication": {"remote": "origin", "branch": "refs/heads/other"}},
                              {"publication": {"remote": "", "branch": "refs/heads/main"}}):
                with self.subTest(overrides=overrides):
                    self.assertStop("review_p7_root_effect_refused", self.open, lock, **overrides)
            for invocation in ({}, ["x"], {"x": 1.5}):
                with self.subTest(invocation=invocation):
                    self.assertStop("review_p7_root_effect_refused", rm.open_mutation, lock, invocation,
                                    branch="refs/heads/main", base=self.head(), global_policy_version=1,
                                    global_policy_digest="a" * 64, write_scope=self.scope, publication=None)
        self.assertFalse(os.path.lexists(self.root / rm.MUTATIONS_DIR), "a refused open records nothing")
        with rm.root_operation(self.root, rm.OPERATION_EVALUATION) as lock:
            self.assertStop("review_p7_root_effect_refused", self.open, lock,
                            write_scope=[ROOT_POLICY_LAYOUT.review_dir + "/"])
            self.assertStop("review_p7_root_effect_refused", self.open, lock, write_scope=[self.change])
            self.assertEqual([evaluation], self.open(lock, write_scope=[evaluation]).record["write_scope"])

    def test_an_unreadable_runtime_record_fails_closed(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            mutation = self.open(lock)
        path = self.root / rm.MUTATIONS_DIR / f"{mutation.mutation_id}.yaml"
        good = path.read_bytes()
        for bad in (b"not: [a, record\n", good.replace(b"\n", b"\r\n"), good.replace(b"pending", b"waiting")):
            with self.subTest(bad=bad[:20]):
                path.write_bytes(bad)
                self.assertReconcile("review_p7_root_mutation_unreadable", rm.pending_mutations, self.root)
                with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
                    self.assertReconcile("review_p7_root_mutation_unreadable", self.open, lock)
        path.write_bytes(good)
        stray = self.root / rm.MUTATIONS_DIR / "notes.txt"
        stray.write_text("", encoding="utf-8")
        self.assertReconcile("review_p7_root_mutation_unreadable", rm.pending_mutations, self.root)
        stray.unlink()
        renamed = self.root / rm.MUTATIONS_DIR / f"{ids.new_id('root_policy_mutation')}.yaml"
        path.rename(renamed)
        self.assertReconcile("review_p7_root_mutation_unreadable", rm.pending_mutations, self.root)
        renamed.rename(path)
        self.assertEqual(1, len(rm.pending_mutations(self.root)))

    def test_a_corrupted_canonical_record_is_unreadable_and_never_a_crash(self) -> None:
        """RB7BL-4: values are checked, not key sets alone; a corruption is a reconcile, never a raw error."""
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            mutation = self.open(lock)
        path = self.root / rm.MUTATIONS_DIR / f"{mutation.mutation_id}.yaml"
        good = self.stored(mutation.mutation_id)
        commit = {"stage": "kg1", "parent": self.head(), "ref": "refs/heads/main", "message": "kg1",
                  "paths": [self.gate], "date": DATE}
        facts = {"prepared_commit": self.head(), "prepared_tree": "1" * 40, "ref_moved": False}

        def effect(kind, payload, state="intended", effect_facts=None):
            return {"kind": kind, "payload": payload, "state": state, "facts": effect_facts}

        def create(kind, path_value, content, digest=None):
            return effect(kind, {"path": path_value, "content": content,
                                 "sha256": digest or (sha(content) if isinstance(content, str) else "0" * 64)})

        corruptions = {
            "scope holds a number": {"write_scope": [1, self.change]},
            "scope holds a mapping": {"write_scope": [{"x": 1}, self.change]},
            "scope is unsorted": {"write_scope": [self.packet, self.change]},
            "scope is empty": {"write_scope": []},
            "invocation is empty": {"invocation": {}},
            "publication of another branch": {"publication": {"remote": "origin", "branch": "refs/heads/x"}},
            "reserved ID of another kind": {"reserved_ids": {"run": ids.new_id("work")}},
            "file path is a number": {"effects": [create(rm.EFFECT_REVIEW_CREATE, 1, "x\n")]},
            "file content is a number": {"effects": [create(rm.EFFECT_REVIEW_CREATE, self.gate, 1)]},
            "file content and sha disagree": {"effects": [create(rm.EFFECT_CHANGE_CREATE, self.change, "x\n",
                                                                 sha("y\n"))]},
            "file outside the scope": {"effects": [create(rm.EFFECT_REVIEW_CREATE, "README.md", "x\n")]},
            "file effect with facts": {"effects": [{**create(rm.EFFECT_CHANGE_CREATE, self.change, "x\n"),
                                                    "state": "marked", "facts": {"pushed": True}}]},
            "commit paths are numbers": {"effects": [effect(rm.EFFECT_COMMIT, {**commit, "paths": [1, 2]})]},
            "commit facts of the wrong types": {"effects": [effect(rm.EFFECT_COMMIT, commit, "marked",
                                                                   {**facts, "ref_moved": "no"})]},
            "commit marked without facts": {"effects": [effect(rm.EFFECT_COMMIT, commit, "marked")]},
            "commit facts while intended": {"effects": [effect(rm.EFFECT_COMMIT, commit, "intended", facts)]},
            "commit applied": {"effects": [effect(rm.EFFECT_COMMIT, commit, "applied")]},
            "push of a remote-less root": {"effects": [effect(rm.EFFECT_PUSH, {
                "stage": "kp", "remote": "origin", "ref": "refs/heads/main", "commit": self.head()})]},
            "effect kind is a list": {"effects": [effect(["root-commit"], commit)]},
            "two effects for one path": {"effects": [create(rm.EFFECT_CHANGE_CREATE, self.change, "x\n"),
                                                     create(rm.EFFECT_CHANGE_CREATE, self.change, "y\n")]},
        }
        for name, change in corruptions.items():
            with self.subTest(corruption=name):
                path.write_text(serialize.canonical_text({**good, **change}), encoding="utf-8", newline="\n")
                self.assertReconcile("review_p7_root_mutation_unreadable", rm.pending_mutations, self.root)
                self.assertReconcile("review_p7_root_mutation_unreadable", rm.pending_for_run, self.root,
                                     self.run_id)
                self.assertEqual({"mutation_id": None, "operation": None, "status": "reconcile_required",
                                  "stage": None}, rm._pending_summary(self.root))
                with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
                    self.assertReconcile("review_p7_root_mutation_unreadable", self.open, lock)
        path.write_text(serialize.canonical_text(good), encoding="utf-8", newline="\n")
        self.assertEqual([good], rm.pending_mutations(self.root))


class FirstOpenReservationTests(MutationCase):
    """Amendment 4: the IDs an exact write-scope path names are reserved by the record's first durable write."""

    PACKET_KEY = "review-promotion-packet"
    CHANGE_KEY = "review-global-policy-change"
    EVALUATION_KEY = "review-global-policy-evaluation"

    def reservations(self) -> dict[str, str]:
        return {self.PACKET_KEY: self.packet_id, self.CHANGE_KEY: self.change_id}

    def test_the_first_durable_write_stores_them_and_reserve_id_returns_them(self) -> None:
        writes: list[tuple[str, str]] = []
        real = rm._write_runtime

        def recording(root, relative, text):
            writes.append((relative, text))
            return real(root, relative, text)

        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            with mock.patch.object(rm, "_write_runtime", side_effect=recording):
                mutation = self.open(lock, reserved=self.reservations())
            records = [text for relative, text in writes if relative.startswith(rm.MUTATIONS_DIR + "/")]
            self.assertEqual(1, len(records), "the open is one durable write")
            first = serialize.parse_canonical(records[0].encode("utf-8"), "first write")[0]
            self.assertEqual(self.reservations(), first["reserved_ids"])
            self.assertEqual(sorted(self.scope), first["write_scope"])
            stored = self.stored(mutation.mutation_id)
            self.assertEqual(self.packet_id, mutation.reserve_id(self.PACKET_KEY, "review_promotion_packet"))
            self.assertEqual(self.change_id, mutation.reserve_id(self.CHANGE_KEY, "review_global_policy_change"))
            self.assertEqual(stored, self.stored(mutation.mutation_id), "returning a reservation writes nothing")
            self.assertReconcile("review_p7_root_mutation_conflict", mutation.reserve_id, self.CHANGE_KEY,
                                 "review_promotion_packet")
            run = mutation.reserve_id("run", "review_run")
            self.assertTrue(ids.is_valid_id(run, "review_run"), "any other key allocates as before")
            self.assertEqual(self.reservations(),
                             {key: value for key, value in self.stored(mutation.mutation_id)["reserved_ids"].items()
                              if key != "run"})

    def test_never_with_a_rebind_and_never_on_a_resume(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            self.assertStop("review_p7_root_effect_refused", self.open, lock, reserved=self.reservations(),
                            rebind=self.reservations())
            self.assertFalse(os.path.lexists(self.root / rm.MUTATIONS_DIR), "refused before anything is written")
            first = self.open(lock, reserved=self.reservations())
            for reserved in (self.reservations(), {}, {self.PACKET_KEY: self.packet_id}):
                with self.subTest(resume_with=reserved):
                    self.assertReconcile("review_p7_root_mutation_conflict", self.open, lock, reserved=reserved)
            self.assertStop("review_p7_root_effect_refused", self.open, lock, reserved=self.reservations(),
                            rebind={})
            again = self.open(lock)
            self.assertEqual(first.mutation_id, again.mutation_id)
            self.assertEqual(self.reservations(), again.record["reserved_ids"])
        self.assertEqual(1, len(list((self.root / rm.MUTATIONS_DIR).iterdir())))

    def test_each_reservation_is_an_id_of_a_reservation_kind(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            for reserved in ({self.PACKET_KEY: "rpp_bad"}, {self.PACKET_KEY: ids.new_id("work")},
                             {self.PACKET_KEY: ids.new_id("root_policy_mutation")},
                             {self.PACKET_KEY: self.packet_id + "\n"}, {self.PACKET_KEY: 5}, {"": self.packet_id},
                             {5: self.packet_id}, [(self.PACKET_KEY, self.packet_id)]):
                with self.subTest(reserved=reserved):
                    self.assertStop("review_p7_root_effect_refused", self.open, lock, reserved=reserved,
                                    write_scope=[ROOT_POLICY_LAYOUT.review_dir + "/"])
        self.assertFalse(os.path.lexists(self.root / rm.MUTATIONS_DIR), "a refused open records nothing")

    def test_every_id_naming_scope_path_names_a_reserved_id(self) -> None:
        foreign_packet = ROOT_POLICY_LAYOUT.promotion_packet_rel(ids.new_id("review_promotion_packet"))
        foreign_change_id = ids.new_id("review_global_policy_change")
        evaluation_id = ids.new_id("review_global_policy_evaluation")
        evaluation = ROOT_POLICY_LAYOUT.global_evaluation_rel(evaluation_id)
        foreign_evaluation = ROOT_POLICY_LAYOUT.global_evaluation_rel(ids.new_id("review_global_policy_evaluation"))
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            for name, scope, reserved in (
                ("the change is not reserved", self.scope, {self.PACKET_KEY: self.packet_id}),
                ("the packet is not reserved", self.scope, {self.CHANGE_KEY: self.change_id}),
                ("a foreign packet", self.scope + [foreign_packet], self.reservations()),
                ("a foreign change", [ROOT_POLICY_LAYOUT.global_change_rel(foreign_change_id)], self.reservations()),
                ("a foreign Patch Note", [ROOT_POLICY_LAYOUT.patch_note_rel(foreign_change_id)], self.reservations()),
                ("nothing reserved", [self.change], {}),
            ):
                with self.subTest(name):
                    self.assertStop("review_p7_root_effect_refused", self.open, lock, write_scope=scope,
                                    reserved=reserved)
            # a runtime-loss recovery open is held to its rebound IDs the same way
            self.assertStop("review_p7_root_effect_refused", self.open, lock, write_scope=self.scope,
                            rebind={self.PACKET_KEY: self.packet_id})
            self.assertFalse(os.path.lexists(self.root / rm.MUTATIONS_DIR), "a refused open records nothing")
            # the Review prefix and the Global policy path name no reserved kind
            only = self.open(lock, write_scope=[ROOT_POLICY_LAYOUT.review_dir + "/",
                                                ROOT_POLICY_LAYOUT.global_policy_rel], reserved={})
            self.assertEqual({}, only.record["reserved_ids"])
            only.abandon()
            recovered = self.open(lock, {"recovered": 1}, write_scope=self.scope, rebind=self.reservations())
            self.assertEqual(self.reservations(), recovered.record["reserved_ids"])
            recovered.abandon()
            owned = self.open(lock, {"owned": 1}, reserved=self.reservations())
            self.assertEqual(sorted(self.scope), owned.record["write_scope"])
            owned.abandon()
            # a call with neither behaves exactly as before: a scope naming any ID is taken as given
            plain = self.open(lock, {"plain": 1}, write_scope=self.scope + [foreign_packet])
            self.assertEqual({}, plain.record["reserved_ids"])
            plain.abandon()
        with rm.root_operation(self.root, rm.OPERATION_EVALUATION) as lock:
            self.assertStop("review_p7_root_effect_refused", self.open, lock, write_scope=[foreign_evaluation],
                            reserved={self.EVALUATION_KEY: evaluation_id})
            mutation = self.open(lock, write_scope=[evaluation], reserved={self.EVALUATION_KEY: evaluation_id})
            self.assertEqual(evaluation_id, mutation.reserve_id(self.EVALUATION_KEY,
                                                                "review_global_policy_evaluation"))

    def test_the_reservations_survive_a_crash_right_after_the_first_write(self) -> None:
        arguments = dict(branch="refs/heads/main", base=self.head(), global_policy_version=1,
                         global_policy_digest=policy.global_policy_digest(v1_global_policy()),
                         write_scope=self.scope, publication=None)
        child = subprocess.run(
            [sys.executable, "-B", "-c", textwrap.dedent(f"""
                import os, sys
                sys.path.insert(0, {str(SRC)!r})
                from pathlib import Path
                from unittest import mock
                from workline import implementation
                from workline import root_maintenance as rm
                root = Path({str(self.root)!r})
                os.chdir(root)
                with mock.patch.object(implementation, "running_workline_root", return_value=root):
                    with rm.root_operation(root, rm.OPERATION_CHANGE) as lock:
                        mutation = rm.open_mutation(lock, {{"request_digest": "d" * 64}}, reserved={self.reservations()!r},
                                                    **{arguments!r})
                        print(mutation.mutation_id, flush=True)
                        os._exit(9)  # the process dies right after the first durable write, holding the lock
            """)],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(9, child.returncode, child.stderr)
        mutation_id = child.stdout.strip()
        self.assertTrue(ids.is_valid_id(mutation_id, "root_policy_mutation"))
        self.assertEqual(self.reservations(), self.stored(mutation_id)["reserved_ids"])
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            resumed = rm.open_mutation(lock, {"request_digest": "d" * 64}, reserved=None, **arguments)
            self.assertEqual(mutation_id, resumed.mutation_id)
            self.assertEqual(self.packet_id, resumed.reserve_id(self.PACKET_KEY, "review_promotion_packet"))
            self.assertEqual(self.change_id, resumed.reserve_id(self.CHANGE_KEY, "review_global_policy_change"))
            self.assertEqual(sorted(self.scope), resumed.record["write_scope"])
        self.assertNoWorkline()
        self.assertEqual("", self.git_clean())


class EffectTests(MutationCase):
    def test_every_effect_outside_the_closed_set_is_refused(self) -> None:
        content = "schema: x\n"
        evaluation = ROOT_POLICY_LAYOUT.global_evaluation_rel(ids.new_id("review_global_policy_evaluation"))
        foreign_change = ROOT_POLICY_LAYOUT.global_change_rel(ids.new_id("review_global_policy_change"))
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            mutation = self.open(lock)
            refused = [
                (rm.EFFECT_EVALUATION_CREATE, self.create(evaluation, content)),  # not an effect of a change
                ("write_file", self.create(self.change, content)),  # a Project effect kind
                (rm.EFFECT_PACKET_CREATE, self.create(self.change, content)),  # family mismatch
                (rm.EFFECT_CHANGE_CREATE, self.create(self.note, content)),
                (rm.EFFECT_PATCH_NOTE_CREATE, self.create(self.change, content)),
                (rm.EFFECT_REVIEW_CREATE, self.create(self.consumption, content)),  # a Consumption is its own kind
                (rm.EFFECT_CONSUMPTION_CREATE, self.create(self.gate, content)),
                (rm.EFFECT_CHANGE_CREATE, self.create(foreign_change, content)),  # outside the write scope
                (rm.EFFECT_REVIEW_CREATE, self.create("README.md", content)),
                (rm.EFFECT_REVIEW_CREATE, self.create(".workline/project.yaml", content)),
                (rm.EFFECT_REVIEW_CREATE, self.create("review-policy/review/gates/../../../README.md", content)),
                (rm.EFFECT_REVIEW_CREATE, self.create(".workline-root-runtime/holder.json", content)),
                (rm.EFFECT_REVIEW_CREATE, {**self.create(self.gate, content), "extra": 1}),
                (rm.EFFECT_REVIEW_CREATE, {**self.create(self.gate, content), "sha256": "0" * 64}),
                (rm.EFFECT_REVIEW_CREATE, {"path": self.gate, "content": 1, "sha256": "0" * 64}),
                (rm.EFFECT_GLOBAL_POLICY_REPLACE, self.create(ROOT_POLICY_LAYOUT.global_policy_rel, content)),
                (rm.EFFECT_GLOBAL_POLICY_REPLACE, {**self.create(ROOT_POLICY_LAYOUT.global_policy_rel, content),
                                                   "expected_content": content, "expected_sha256": sha(content)}),
                (rm.EFFECT_GLOBAL_POLICY_REPLACE, {**self.create(ROOT_POLICY_LAYOUT.global_policy_rel, content),
                                                   "expected_content": "old\n", "expected_sha256": None}),
                (rm.EFFECT_PUSH, {"stage": "kp", "remote": "origin", "ref": "refs/heads/main",
                                  "commit": self.head()}),  # a remote-less root publishes nothing
                (rm.EFFECT_COMMIT, {"stage": "kp", "parent": self.head(), "ref": "refs/heads/other",
                                    "message": "kp", "paths": [self.change], "date": DATE}),
                (rm.EFFECT_COMMIT, {"stage": "evaluation", "parent": self.head(), "ref": "refs/heads/main",
                                    "message": "x", "paths": [self.change], "date": DATE}),
                (rm.EFFECT_COMMIT, {"stage": "kp", "parent": "HEAD", "ref": "refs/heads/main",
                                    "message": "kp", "paths": [self.change], "date": DATE}),
                (rm.EFFECT_COMMIT, {"stage": "kp", "parent": self.head(), "ref": "refs/heads/main",
                                    "message": "kp", "paths": ["README.md"], "date": DATE}),
                (rm.EFFECT_COMMIT, {"stage": "kp", "parent": self.head(), "ref": "refs/heads/main",
                                    "message": "kp", "paths": [self.note, self.change], "date": DATE}),
                (rm.EFFECT_COMMIT, {"stage": "kp", "parent": self.head(), "ref": "refs/heads/main",
                                    "message": "kp", "paths": [self.change], "date": "yesterday"}),
                (rm.EFFECT_COMMIT, {"stage": "kp", "parent": self.head(), "ref": "refs/heads/main",
                                    "message": " ", "paths": [self.change], "date": DATE}),
            ]
            for kind, payload in refused:
                with self.subTest(kind=kind, payload=payload):
                    self.assertStop("review_p7_root_effect_refused", mutation.add_effect, kind, payload)
            self.assertEqual((), mutation.effects())
            mutation.abandon()
        with rm.root_operation(self.root, rm.OPERATION_EVALUATION) as lock:
            mutation = rm.open_mutation(lock, {"evaluation": 1}, branch="refs/heads/main", base=self.head(),
                                        global_policy_version=1, global_policy_digest="a" * 64,
                                        write_scope=[evaluation], publication=None)
            for kind, payload in ((rm.EFFECT_GLOBAL_POLICY_REPLACE,
                                   {**self.create(ROOT_POLICY_LAYOUT.global_policy_rel, content),
                                    "expected_content": None, "expected_sha256": None}),
                                  (rm.EFFECT_CHANGE_CREATE, self.create(self.change, content)),
                                  (rm.EFFECT_REVIEW_CREATE, self.create(self.gate, content)),
                                  (rm.EFFECT_COMMIT, {"stage": "kp", "parent": self.head(), "ref": "refs/heads/main",
                                                      "message": "x", "paths": [evaluation], "date": DATE})):
                with self.subTest(evaluation_refuses=kind):
                    self.assertStop("review_p7_root_effect_refused", mutation.add_effect, kind, payload)
            self.assertEqual(0, mutation.add_effect(rm.EFFECT_COMMIT, {
                "stage": "evaluation", "parent": self.head(), "ref": "refs/heads/main", "message": "evaluation",
                "paths": [evaluation], "date": DATE}))
        self.assertNoWorkline()

    @unittest.skipUnless(CAN_CREATE, "the immutable create is refused on this platform")
    def test_an_effect_is_recorded_once_and_its_replay_is_the_same(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            mutation = self.open(lock)
            index = mutation.add_effect(rm.EFFECT_REVIEW_CREATE, self.create(self.gate, "gate: 1\n"))
            self.assertEqual(index, mutation.add_effect(rm.EFFECT_REVIEW_CREATE, self.create(self.gate, "gate: 1\n")))
            self.assertReconcile("review_p7_root_effect_conflict", mutation.add_effect, rm.EFFECT_REVIEW_CREATE,
                                 self.create(self.gate, "gate: 2\n"))
            commit = {"stage": "kg1", "parent": self.head(), "ref": "refs/heads/main", "message": "kg1",
                      "paths": [self.gate], "date": DATE}
            second = mutation.add_effect(rm.EFFECT_COMMIT, commit)
            self.assertEqual(second, mutation.add_effect(rm.EFFECT_COMMIT, dict(commit)))
            self.assertReconcile("review_p7_root_effect_conflict", mutation.add_effect, rm.EFFECT_COMMIT,
                                 {**commit, "message": "another"})
            self.assertEqual(2, len(mutation.effects()))
            self.assertEqual({"kind": rm.EFFECT_REVIEW_CREATE, "payload": self.create(self.gate, "gate: 1\n"),
                              "state": "intended", "facts": None}, mutation.effects()[0])
        self.assertEqual(2, len(self.stored(mutation.mutation_id)["effects"]))
        self.assertFalse((self.root / self.gate).exists(), "intent is recorded first; nothing is applied by it")

    @unittest.skipUnless(CAN_CREATE, "the immutable create is refused on this platform")
    def test_immutable_creates_apply_exactly_and_never_overwrite(self) -> None:
        records = [(rm.EFFECT_REVIEW_CREATE, self.gate, "gate: 1\n"),
                   (rm.EFFECT_CONSUMPTION_CREATE, self.consumption, "consumption: 1\n"),
                   (rm.EFFECT_PACKET_CREATE, self.packet, "packet: 1\n"),
                   (rm.EFFECT_CHANGE_CREATE, self.change, "change: 1\r\nkept: exactly\n"),
                   (rm.EFFECT_PATCH_NOTE_CREATE, self.note, "# Patch note\n\nNo path here.\n")]
        scope = self.scope + [self.consumption]
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            mutation = self.open(lock, write_scope=scope)
            for kind, path, content in records:
                with self.subTest(kind=kind):
                    index = mutation.add_effect(kind, self.create(path, content))
                    self.assertEqual(rm.APPLIED, mutation.apply_effect(index))
                    self.assertEqual(content.encode("utf-8"), (self.root / path).read_bytes())
                    self.assertEqual(rm.MATCHED, mutation.apply_effect(index))
                    self.assertEqual("applied", mutation.effects()[index]["state"])
            self.assertStop("review_p7_root_effect_refused", mutation.apply_effect, 99)
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            resumed = self.open(lock, write_scope=scope)
            conflict = ROOT_POLICY_REVIEW_NAMESPACE.gate_rel(self.run_id, 2)
            (self.root / conflict).write_text("foreign: 1\n", encoding="utf-8")
            index = resumed.add_effect(rm.EFFECT_REVIEW_CREATE, self.create(conflict, "gate: 2\n"))
            self.assertReconcile("review_p7_root_effect_conflict", resumed.apply_effect, index)
            self.assertEqual("foreign: 1\n", (self.root / conflict).read_text(encoding="utf-8"))
        self.assertNoWorkline()

    @unittest.skipUnless(CAN_CREATE, "the immutable create is refused on this platform")
    def test_the_global_policy_replace_is_an_exact_compare_and_swap(self) -> None:
        v1 = policy.global_policy_bytes(v1_global_policy()).decode("utf-8")
        v2 = policy.global_policy_bytes(v2_global_policy()).decode("utf-8")
        target = self.root / ROOT_POLICY_LAYOUT.global_policy_rel
        target.parent.mkdir(parents=True)
        target.write_bytes(v1.encode("utf-8"))
        replace = {**self.create(ROOT_POLICY_LAYOUT.global_policy_rel, v2), "expected_content": v1,
                   "expected_sha256": sha(v1)}
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            mutation = self.open(lock)
            index = mutation.add_effect(rm.EFFECT_GLOBAL_POLICY_REPLACE, replace)
            self.assertEqual(rm.APPLIED, mutation.apply_effect(index))
            self.assertEqual(v2.encode("utf-8"), target.read_bytes())
            self.assertEqual(rm.MATCHED, mutation.apply_effect(index))
        # a before-state mismatch is never overwritten
        other = self.make_root("cas-root")
        self.bind(other)
        tampered = v1.replace("parent_global_policy_digest: null", "parent_global_policy_digest: null\n")
        (other / "review-policy").mkdir()
        (other / ROOT_POLICY_LAYOUT.global_policy_rel).write_bytes(tampered.encode("utf-8"))
        with cwd(other), rm.root_operation(other, rm.OPERATION_CHANGE) as lock:
            mutation = rm.open_mutation(lock, {"x": 1}, branch="refs/heads/main", base=self.head(other),
                                        global_policy_version=1, global_policy_digest="a" * 64,
                                        write_scope=[ROOT_POLICY_LAYOUT.global_policy_rel], publication=None)
            index = mutation.add_effect(rm.EFFECT_GLOBAL_POLICY_REPLACE, replace)
            self.assertReconcile("review_p7_root_effect_conflict", mutation.apply_effect, index)
        self.assertEqual(tampered.encode("utf-8"), (other / ROOT_POLICY_LAYOUT.global_policy_rel).read_bytes())

    @unittest.skipIf(CAN_CREATE, "this platform can contain an immutable create")
    def test_no_file_effect_is_recorded_where_no_create_can_be_contained(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            mutation = self.open(lock)
            with self.assertRaises(ValidationError) as caught:
                mutation.add_effect(rm.EFFECT_REVIEW_CREATE, self.create(self.gate, "gate: 1\n"))
            self.assertEqual("review_create_unsupported", caught.exception.code)
            self.assertEqual((), mutation.effects())

    def test_commit_and_push_facts_are_recorded_and_never_contradicted(self) -> None:
        base = self.head()
        bare = self.add_remote()
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            mutation = self.open(lock, publication={"remote": "origin", "branch": "refs/heads/main"})
            kg1 = mutation.add_effect(rm.EFFECT_COMMIT, {"stage": "kg1", "parent": base, "ref": "refs/heads/main",
                                                          "message": "kg1", "paths": [self.gate], "date": DATE})
            self.assertStop("review_p7_root_effect_refused", mutation.apply_effect, kg1)
            commit, tree = self.commit_object(base)
            self.assertStop("review_p7_root_effect_refused", mutation.mark_effect, kg1, {"prepared_commit": commit})
            mutation.mark_effect(kg1, {"prepared_commit": commit, "prepared_tree": tree, "ref_moved": False})
            self.assertEqual("marked", mutation.effects()[kg1]["state"])
            self.assertReconcile("review_p7_root_effect_conflict", mutation.mark_effect, kg1,
                                 {"prepared_commit": base, "prepared_tree": tree, "ref_moved": False})
            # the ref has not moved: recording it as moved is refused
            self.assertReconcile("review_p7_root_effect_conflict", mutation.mark_effect, kg1,
                                 {"prepared_commit": commit, "prepared_tree": tree, "ref_moved": True})
            # a Review generation commit is never published on its own, and nothing unmoved is published
            self.assertStop("review_p7_root_effect_refused", mutation.add_effect, rm.EFFECT_PUSH,
                            {"stage": "kg1", "remote": "origin", "ref": "refs/heads/main", "commit": commit})
            git(self.root, "update-ref", "refs/heads/main", commit, base)
            mutation.mark_effect(kg1, {"prepared_commit": commit, "prepared_tree": tree, "ref_moved": True})
            self.assertReconcile("review_p7_root_effect_conflict", mutation.mark_effect, kg1,
                                 {"prepared_commit": commit, "prepared_tree": tree, "ref_moved": False})
            kp_commit, kp_tree = self.commit_object(commit, "kp")
            kp = mutation.add_effect(rm.EFFECT_COMMIT, {"stage": "kp", "parent": commit, "ref": "refs/heads/main",
                                                         "message": "kp", "paths": [self.change], "date": DATE})
            self.assertStop("review_p7_root_effect_refused", mutation.add_effect, rm.EFFECT_PUSH,
                            {"stage": "kp", "remote": "origin", "ref": "refs/heads/main", "commit": kp_commit})
            self.assertStop("review_p7_root_effect_refused", mutation.mark_effect, kp,
                            {"prepared_commit": kp_commit, "prepared_tree": kp_tree, "ref_moved": True})
            self.assertIsNone(mutation.effects()[kp]["facts"], "a commit is never first recorded as moved")
            mutation.mark_effect(kp, {"prepared_commit": kp_commit, "prepared_tree": kp_tree, "ref_moved": False})
            git(self.root, "update-ref", "refs/heads/main", kp_commit, commit)
            mutation.mark_effect(kp, {"prepared_commit": kp_commit, "prepared_tree": kp_tree, "ref_moved": True})
            for payload in ({"stage": "kp", "remote": "upstream", "ref": "refs/heads/main", "commit": kp_commit},
                            {"stage": "kp", "remote": "origin", "ref": "refs/heads/other", "commit": kp_commit},
                            {"stage": "kp", "remote": "origin", "ref": "refs/heads/main", "commit": commit}):
                with self.subTest(push=payload):
                    self.assertStop("review_p7_root_effect_refused", mutation.add_effect, rm.EFFECT_PUSH, payload)
            push = mutation.add_effect(rm.EFFECT_PUSH, {"stage": "kp", "remote": "origin", "ref": "refs/heads/main",
                                                         "commit": kp_commit})
            self.assertStop("review_p7_root_effect_refused", mutation.mark_effect, push, {"pushed": "yes"})
            mutation.mark_effect(push, {"pushed": True})
            self.assertReconcile("review_p7_root_effect_conflict", mutation.mark_effect, push, {"pushed": False})
            self.assertEqual({"stage", "remote", "ref", "commit"}, set(mutation.effects()[push]["payload"]))
            text = (self.root / rm.MUTATIONS_DIR / f"{mutation.mutation_id}.yaml").read_text(encoding="utf-8")
            self.assertNotIn(str(bare), text, "the mutation record never carries the locator")
            self.assertNotIn(str(bare).replace("\\", "/"), text)
            mutation.complete()
        self.assertEqual("completed", self.stored(mutation.mutation_id)["status"])
        self.assertEqual([], rm.pending_mutations(self.root))

    def test_completion_needs_every_effect_done_and_closes_the_record(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            mutation = self.open(lock)
            index = mutation.add_effect(rm.EFFECT_COMMIT, {"stage": "kg1", "parent": self.head(),
                                                            "ref": "refs/heads/main", "message": "kg1",
                                                            "paths": [self.gate], "date": DATE})
            self.assertStop("review_p7_root_effect_refused", mutation.complete)
            parent = self.head()
            commit, tree = self.commit_object(parent)
            mutation.mark_effect(index, {"prepared_commit": commit, "prepared_tree": tree, "ref_moved": False})
            self.assertStop("review_p7_root_effect_refused", mutation.complete)
            git(self.root, "update-ref", "refs/heads/main", commit, parent)
            mutation.mark_effect(index, {"prepared_commit": commit, "prepared_tree": tree, "ref_moved": True})
            mutation.complete()
            for call, args in ((mutation.reserve_id, ("k", "review_run")), (mutation.set_note, ("k", 1)),
                               (mutation.complete, ()), (mutation.abandon, ())):
                with self.subTest(call=call.__name__):
                    self.assertStop("review_p7_root_effect_refused", call, *args)
            fresh = self.open(lock, {"next": 1})
            self.assertNotEqual(mutation.mutation_id, fresh.mutation_id, "a completed mutation is never resumed")

    def test_a_commit_is_recorded_prepared_before_its_ref_moves(self) -> None:
        """RB7BL-1: facts absent means the ref never moved through this mutation, and that order is enforced."""
        parent = self.head()
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            mutation = self.open(lock)
            index = mutation.add_effect(rm.EFFECT_COMMIT, {"stage": "kg1", "parent": parent,
                                                            "ref": "refs/heads/main", "message": "kg1",
                                                            "paths": [self.gate], "date": DATE})
            commit, tree = self.commit_object(parent)
            # a factless commit intent whose branch is still at its recorded parent is provably unapplied
            self.assertFalse(rm._effect_may_be_applied(self.root, mutation.effects()[index]))
            # the forbidden order: the ref moved before the prepared commit was durable
            git(self.root, "update-ref", "refs/heads/main", commit, parent)
            self.assertTrue(rm._effect_may_be_applied(self.root, mutation.effects()[index]),
                            "a factless commit whose branch moved is not provably unapplied")
            self.assertStop("review_p7_root_effect_refused", mutation.mark_effect, index,
                            {"prepared_commit": commit, "prepared_tree": tree, "ref_moved": True})
            self.assertReconcile("review_p7_root_effect_conflict", mutation.mark_effect, index,
                                 {"prepared_commit": commit, "prepared_tree": tree, "ref_moved": False})
            self.assertIsNone(mutation.effects()[index]["facts"])
            self.assertReconcile("review_p7_root_abandon_refused", mutation.abandon)
            # an unreadable branch is not provably unapplied either, nor provably unmoved
            with mock.patch.object(gitcmd, "branch_commit", return_value=None):
                self.assertReconcile("review_p7_root_abandon_refused", mutation.abandon)
                self.assertReconcile("review_p7_root_effect_conflict", mutation.mark_effect, index,
                                     {"prepared_commit": commit, "prepared_tree": tree, "ref_moved": False})
            # back at its parent, nothing of it is applied: it may be abandoned
            git(self.root, "update-ref", "refs/heads/main", parent, commit)
            mutation.abandon()
        self.assertEqual("abandoned", self.stored(mutation.mutation_id)["status"])

    def test_abandon_only_while_nothing_canonical_is_applied(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            mutation = self.open(lock)
            mutation.reserve_id("run", "review_run")
            if CAN_CREATE:
                mutation.add_effect(rm.EFFECT_REVIEW_CREATE, self.create(self.gate, "gate: 1\n"))
            mutation.abandon()
            self.assertEqual("abandoned", self.stored(mutation.mutation_id)["status"])
            self.assertEqual([], rm.pending_mutations(self.root))
        if not CAN_CREATE:
            return
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            applied = self.open(lock, {"second": 1})
            index = applied.add_effect(rm.EFFECT_REVIEW_CREATE, self.create(self.gate, "gate: 1\n"))
            applied.apply_effect(index)
            self.assertReconcile("review_p7_root_abandon_refused", applied.abandon)
        # an applied effect whose application was never recorded (a crash in between) also blocks it
        record = self.stored(applied.mutation_id)
        record["effects"][index]["state"] = "intended"
        (self.root / rm.MUTATIONS_DIR / f"{applied.mutation_id}.yaml").write_text(
            serialize.canonical_text(record), encoding="utf-8", newline="\n")
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            resumed = self.open(lock, {"second": 1})
            self.assertReconcile("review_p7_root_abandon_refused", resumed.abandon)
            # a commit whose prepared commit the branch already names blocks it as well
            commit, tree = self.commit_object(self.head())
            other = ROOT_POLICY_REVIEW_NAMESPACE.gate_rel(self.run_id, 2)
            kg = resumed.add_effect(rm.EFFECT_COMMIT, {"stage": "kg2", "parent": self.head(), "ref": "refs/heads/main",
                                                        "message": "kg2", "paths": [other], "date": DATE})
            resumed.mark_effect(kg, {"prepared_commit": commit, "prepared_tree": tree, "ref_moved": False})
            git(self.root, "update-ref", "refs/heads/main", commit, self.head())
            (self.root / self.gate).unlink()
            self.assertReconcile("review_p7_root_abandon_refused", resumed.abandon)

    def test_pending_for_run_finds_the_root_generation_mutation(self) -> None:
        with rm.root_operation(self.root, rm.OPERATION_CHANGE) as lock:
            mutation = self.open(lock)
            if CAN_CREATE:
                mutation.add_effect(rm.EFFECT_REVIEW_CREATE, self.create(self.gate, "gate: 1\n"))
        if CAN_CREATE:
            self.assertEqual([mutation.mutation_id],
                             [record["mutation_id"] for record in rm.pending_for_run(self.root, self.run_id)])
        self.assertEqual([], rm.pending_for_run(self.root, ids.new_id("review_run")))
        with self.assertRaises(ValidationError):
            rm.pending_for_run(self.root, "not-a-run")


# --------------------------------------------------------------------------- authorization and repository identity (§31.12, §31.13)


class AuthorizationTests(RootCase):
    def test_a_remote_less_root_needs_no_authorization(self) -> None:
        self.assertIsNone(rm.publication_binding(self.root))
        self.assertStop("review_p7_authorization_invalid", rm.authorize, self.root, remote="origin",
                        branch="refs/heads/main", locator="anything")
        self.assertFalse(os.path.lexists(self.root / rm.AUTHORIZATION_REL))

    def test_with_a_remote_nothing_publishes_until_a_human_authorizes_and_origin_is_never_inferred(self) -> None:
        bare = self.add_remote()
        self.assertStop("review_p7_authorization_required", rm.publication_binding, self.root)
        found = rm.authorize(self.root, remote="origin", branch="refs/heads/main", locator=str(bare))
        self.assertEqual(("origin", "refs/heads/main", str(bare)), (found.remote, found.branch, found.locator))
        self.assertEqual(rm.repository_identity(self.root), found.repository_identity)
        self.assertEqual(found, rm.read_authorization(self.root))
        raw = (self.root / rm.AUTHORIZATION_REL).read_bytes()
        record, _ = serialize.parse_canonical(raw, "authorization")
        self.assertEqual({"schema": rm.AUTHORIZATION_SCHEMA, "version": 1, "contract": rm.AUTHORIZATION_CONTRACT,
                          "repository_identity": found.repository_identity, "remote": "origin",
                          "branch": "refs/heads/main", "locator": str(bare)}, record)
        binding = rm.publication_binding(self.root)
        self.assertEqual(rm.PublicationBinding("origin", "refs/heads/main", str(bare)), binding)
        self.assertEqual("", self.git_clean(), "the authorization is local and ignored")
        self.assertNoWorkline()
        self.assertFalse((self.root / rm.HOLDER_REL).exists())

    def test_an_unreadable_authorization_is_none_and_required(self) -> None:
        bare = self.add_remote()
        rm.authorize(self.root, remote="origin", branch="refs/heads/main", locator=str(bare))
        path = self.root / rm.AUTHORIZATION_REL
        good = path.read_bytes()
        for bad in (b"garbage", good.replace(b"\n", b"\r\n"), good.replace(b"workline-root-maintenance-authorization-v1",
                                                                             b"workline-root-maintenance-authorization-v2")):
            with self.subTest(bad=bad[:16]):
                path.write_bytes(bad)
                self.assertIsNone(rm.read_authorization(self.root))
                self.assertStop("review_p7_authorization_required", rm.publication_binding, self.root)

    def test_authorize_compares_every_input_with_git_now(self) -> None:
        bare = self.add_remote()
        cases = [
            dict(remote="upstream", branch="refs/heads/main", locator=str(bare)),
            dict(remote="origin", branch="refs/heads/main", locator=str(bare) + "/"),
            dict(remote="origin", branch="refs/heads/main", locator=str(self.tmp / "other.git")),
            dict(remote="origin", branch="main", locator=str(bare)),
            dict(remote="origin", branch="refs/heads/other", locator=str(bare)),
            dict(remote="origin", branch="refs/heads/main", locator=""),
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assertStop("review_p7_authorization_invalid", rm.authorize, self.root, **case)
        git(self.root, "checkout", "-q", "--detach")
        self.assertStop("review_p7_authorization_invalid", rm.authorize, self.root, remote="origin",
                        branch="refs/heads/main", locator=str(bare))
        self.assertFalse(os.path.lexists(self.root / rm.AUTHORIZATION_REL), "a refused authorization writes nothing")

    def test_a_locator_or_branch_change_is_a_mismatch(self) -> None:
        bare = self.add_remote()
        rm.authorize(self.root, remote="origin", branch="refs/heads/main", locator=str(bare))
        other = self.tmp / "other-remote.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(other))
        git(self.root, "remote", "set-url", "--push", "origin", str(other))
        self.assertStop("review_p7_authorization_mismatch", rm.publication_binding, self.root)
        git(self.root, "config", "--unset", "remote.origin.pushurl")
        self.assertIsNotNone(rm.publication_binding(self.root))
        git(self.root, "checkout", "-q", "-b", "other")
        self.assertStop("review_p7_authorization_mismatch", rm.publication_binding, self.root)
        git(self.root, "checkout", "-q", "main")
        git(self.root, "remote", "rename", "origin", "upstream")
        self.assertStop("review_p7_authorization_mismatch", rm.publication_binding, self.root)

    def test_multiple_or_unreadable_locators_are_refused(self) -> None:
        bare = self.add_remote()
        rm.authorize(self.root, remote="origin", branch="refs/heads/main", locator=str(bare))
        second = self.tmp / "second.git"
        git(self.root, "remote", "set-url", "--add", "--push", "origin", str(bare))
        git(self.root, "remote", "set-url", "--add", "--push", "origin", str(second))
        self.assertStop("push_destination_multiple", rm.publication_binding, self.root)
        self.assertStop("push_destination_multiple", rm.authorize, self.root, remote="origin",
                        branch="refs/heads/main", locator=str(bare))
        git(self.root, "config", "--unset-all", "remote.origin.pushurl")
        with mock.patch.object(gitcmd, "push_locators", side_effect=gitcmd.GitError("unreadable")):
            self.assertStop("push_destination_unresolved", rm.publication_binding, self.root)
            self.assertStop("push_destination_unresolved", rm.authorize, self.root, remote="origin",
                            branch="refs/heads/main", locator=str(bare))
        with mock.patch.object(gitcmd, "push_locators", return_value=[]):
            self.assertStop("push_destination_unresolved", rm.authorize, self.root, remote="origin",
                            branch="refs/heads/main", locator=str(bare))
        self.assertEqual(rm.PublicationBinding("origin", "refs/heads/main", str(bare)),
                         rm.publication_binding(self.root))

    def test_a_secret_bearing_locator_is_refused_and_never_echoed(self) -> None:
        secret = "https://maintainer:s3cr3t-token@example.invalid/root.git"
        git(self.root, "remote", "add", "origin", secret)
        error = self.assertStop("push_destination_secret", rm.authorize, self.root, remote="origin",
                                branch="refs/heads/main", locator=secret)
        self.assertNotIn("s3cr3t-token", str(error))
        self.assertFalse(os.path.lexists(self.root / rm.AUTHORIZATION_REL))
        clean = "https://example.invalid/root.git"
        git(self.root, "remote", "set-url", "origin", clean)
        error = self.assertStop("push_destination_secret", rm.authorize, self.root, remote="origin",
                                branch="refs/heads/main", locator=secret)
        self.assertNotIn("s3cr3t-token", str(error))
        rm.authorize(self.root, remote="origin", branch="refs/heads/main", locator=clean)
        git(self.root, "remote", "set-url", "--push", "origin", secret)
        error = self.assertStop("push_destination_secret", rm.publication_binding, self.root)
        self.assertNotIn("s3cr3t-token", str(error))

    def test_a_copied_authorization_authorizes_no_other_clone_or_worktree(self) -> None:
        bare = self.add_remote()
        rm.authorize(self.root, remote="origin", branch="refs/heads/main", locator=str(bare))
        authorization = (self.root / rm.AUTHORIZATION_REL).read_bytes()
        clone = self.tmp / "clone"
        git(self.tmp, "clone", "-q", str(self.root), str(clone))
        git(clone, "remote", "set-url", "origin", str(bare))
        worktree = self.tmp / "worktree"
        git(self.root, "worktree", "add", "-q", "--detach", str(worktree))
        for copy in (clone, worktree):
            with self.subTest(copy=copy.name):
                (copy / rm.RUNTIME_DIR).mkdir()
                (copy / rm.AUTHORIZATION_REL).write_bytes(authorization)
                self.assertNotEqual(rm.repository_identity(self.root), rm.repository_identity(copy))
                error = self.assertStop("review_p7_authorization_mismatch", rm.publication_binding, copy)
                self.assertIn("another repository instance", str(error))
        self.assertEqual(gitcmd.git_common_dir(self.root), gitcmd.git_common_dir(worktree))

    def test_the_repository_identity_is_opaque_stable_and_positive(self) -> None:
        identity = rm.repository_identity(self.root)
        self.assertRegex(identity, r"\A[0-9a-f]{64}\Z")
        self.assertEqual(identity, rm.repository_identity(self.root))
        self.assertNotIn(self.root.name, identity)
        outside = self.new_dir("not-a-repository")
        with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(self.tmp)}):
            self.assertStop("review_p7_repository_identity_unavailable", rm.repository_identity, outside)
        with mock.patch.object(gitcmd, "object_format", return_value=None):
            self.assertStop("review_p7_repository_identity_unavailable", rm.repository_identity, self.root)

    def test_an_indirected_authorization_is_never_read_or_written_through(self) -> None:
        if os.name != "nt":
            self.skipTest("junctions are a Windows construct")
        bare = self.add_remote()
        decoy = self.new_dir("decoy")
        (decoy / "maintenance-authorization.yaml").write_text("x", encoding="utf-8")
        if not make_junction(self.root / rm.RUNTIME_DIR, decoy):
            self.skipTest("cannot create a junction here")
        self.assertIsNone(rm.read_authorization(self.root))
        self.assertStop("review_p7_root_runtime_invalid", rm.authorize, self.root, remote="origin",
                        branch="refs/heads/main", locator=str(bare))
        self.assertEqual("x", (decoy / "maintenance-authorization.yaml").read_text(encoding="utf-8"))
        self.assertEqual(["maintenance-authorization.yaml"], [path.name for path in decoy.iterdir()])


# --------------------------------------------------------------------------- committability (RB7C-9)


class CommittabilityTests(RootCase):
    def effect_set(self) -> list[str]:
        change = ids.new_id("review_global_policy_change")
        return [ROOT_POLICY_LAYOUT.review_dir + "/", ROOT_POLICY_LAYOUT.global_policy_rel,
                ROOT_POLICY_LAYOUT.promotion_packet_rel(ids.new_id("review_promotion_packet")),
                ROOT_POLICY_LAYOUT.global_change_rel(change), ROOT_POLICY_LAYOUT.patch_note_rel(change),
                ROOT_POLICY_LAYOUT.global_evaluation_rel(ids.new_id("review_global_policy_evaluation"))]

    def ignore(self, rule: str) -> None:
        # LF only: Git for Windows reads a CRLF blank ignore line as a pattern matching every directory
        (self.root / ".gitignore").write_bytes((IGNORE_RULE + (rule + "\n" if rule else "")).encode("utf-8"))

    def test_a_committable_effect_set_passes_and_nothing_is_written(self) -> None:
        before = snapshot(self.root)
        rm.require_committable(self.root, self.effect_set())
        rm.require_committable(self.root, [])
        self.assertEqual(before, snapshot(self.root))

    def test_an_ignore_rule_on_any_root_family_stops_before_the_first_effect(self) -> None:
        effects = self.effect_set()
        for rule in ("review-policy/review/", "review-policy/review/gates/", "review-policy/review/consumptions/",
                     "review-policy/review/**/*.yaml", "review-policy/changes/", "review-policy/patch-notes/*.md",
                     "*.md", "global-policy.yaml", "review-policy/evaluations", "review-policy/promotion-packets/"):
            with self.subTest(rule=rule):
                self.ignore(rule)
                self.assertStop("review_path_ignored", rm.require_committable, self.root, effects)
        self.ignore("")
        rm.require_committable(self.root, effects)

    def test_a_path_outside_the_root_policy_layout_is_refused(self) -> None:
        for relative in ("README.md", ".workline/project.yaml", ".workline-root-runtime/holder.json",
                         "review-policy/other.yaml", "review-policy/../README.md", "/review-policy/review/",
                         "review-policy", 5):
            with self.subTest(relative=relative):
                self.assertStop("review_p7_root_effect_refused", rm.require_committable, self.root, [relative])
        self.assertStop("review_p7_root_effect_refused", rm.require_committable, self.root,
                        ROOT_POLICY_LAYOUT.global_policy_rel)

    def test_undeterminable_is_a_stop(self) -> None:
        with mock.patch.object(gitcmd, "is_ignored", return_value=None):
            self.assertStop("review_committability_unknown", rm.require_committable, self.root, self.effect_set())


# --------------------------------------------------------------------------- read-only status (§31.46, RB7C-4)


class StatusTests(RootCase):
    def setUp(self) -> None:
        super().setUp()
        # the real root's own baseline: the materialized Global policy v1 once P7 tracks it (RB7 step 4b)
        self.current = policy.load_global_baseline(WORKLINE_ROOT)
        patcher = mock.patch.object(policy, "load_global_baseline", return_value=self.current)
        self.loader = patcher.start()
        self.addCleanup(patcher.stop)

    def assertPrivate(self, report: dict, *secrets: str) -> None:
        self.assertEqual(set(), keys_at_any_depth(report) & FORBIDDEN_KEYS)
        text = json.dumps(report)
        for secret in secrets:
            self.assertNotIn(secret, text)
            self.assertNotIn(secret.replace("\\", "\\\\"), text)

    def test_the_exact_shape_of_a_fresh_root_in_either_source_mode(self) -> None:
        # Global policy version 1 has ONE digest in both modes: the derived baseline restated is exactly the
        # materialized v1 record, so the status names the same Global policy before and after the transition.
        derived = policy.derived_global_baseline(WORKLINE_ROOT)
        self.assertEqual((policy.SOURCE_MODE_DERIVED, policy.SOURCE_MODE_MATERIALIZED),
                         (derived.source_mode, self.current.source_mode))
        self.assertEqual(policy.global_policy_digest(v1_global_policy()), self.current.global_policy_identity)
        for baseline in (derived, self.current):
            with self.subTest(source_mode=baseline.source_mode):
                self.loader.return_value = baseline
                before = snapshot(self.root)
                report = rm.status_report(self.root)
                self.assertEqual(before, snapshot(self.root), "a status call creates nothing")
                self.assertEqual(
                    {"status": "available",
                     "global_policy": {"source_mode": baseline.source_mode, "version": 1,
                                       "digest": policy.global_policy_digest(v1_global_policy())},
                     "current_change_id": None, "evaluation_ids": [],
                     "authorization": {"status": "not_required", "remote": None, "branch": None},
                     "pending_mutation": None,
                     "next_boundary_adapter_identity": policy.COMPATIBILITY_EXACT_DERIVED_SEMANTIC},
                    report)
                self.assertFalse(os.path.lexists(self.root / rm.RUNTIME_DIR))
                self.assertNoWorkline()
                self.assertPrivate(report)

    def test_with_a_held_lock_a_pending_mutation_and_an_authorization(self) -> None:
        bare = self.add_remote()
        self.assertEqual("absent", rm.status_report(self.root)["authorization"]["status"])
        rm.authorize(self.root, remote="origin", branch="refs/heads/main", locator=str(bare))
        calls: list[tuple[str, ...]] = []
        real = gitcmd.run_git

        def recording(repo, *args, **kwargs):
            calls.append(args)
            return real(repo, *args, **kwargs)

        run_id = ids.new_id("review_run")
        with rm.root_operation(self.root, rm.OPERATION_CHANGE, {"pid": 1}) as lock:
            mutation = rm.open_mutation(lock, {"x": 1}, branch="refs/heads/main", base=self.head(),
                                        global_policy_version=1, global_policy_digest="a" * 64,
                                        write_scope=[ROOT_POLICY_LAYOUT.review_dir + "/"],
                                        publication={"remote": "origin", "branch": "refs/heads/main"})
            mutation.add_effect(rm.EFFECT_COMMIT, {"stage": "kg1", "parent": self.head(), "ref": "refs/heads/main",
                                                   "message": "kg1",
                                                   "paths": [ROOT_POLICY_REVIEW_NAMESPACE.gate_rel(run_id, 1)],
                                                   "date": DATE})
            before = snapshot(self.root)
            with mock.patch.object(gitcmd, "run_git", side_effect=recording), \
                    mock.patch.object(oplock, "open_lock_file", side_effect=AssertionError("a lock")):
                report = rm.status_report(self.root)
            self.assertEqual(before, snapshot(self.root), "a status call writes no runtime state")
        self.assertEqual({"mutation_id": mutation.mutation_id, "operation": rm.OPERATION_CHANGE,
                          "status": "pending", "stage": "kg1"}, report["pending_mutation"])
        self.assertEqual({"status": "valid", "remote": "origin", "branch": "refs/heads/main"}, report["authorization"])
        self.assertPrivate(report, str(bare), socket_name())
        for args in calls:
            self.assertFalse({"push", "fetch", "ls-remote", "pull"} & set(args), f"a remote contact: {args}")

    def test_authorization_states(self) -> None:
        bare = self.add_remote()
        rm.authorize(self.root, remote="origin", branch="refs/heads/main", locator=str(bare))
        git(self.root, "checkout", "-q", "-b", "other")
        self.assertEqual({"status": "mismatch", "remote": "origin", "branch": "refs/heads/main"},
                         rm.status_report(self.root)["authorization"])
        git(self.root, "checkout", "-q", "main")
        git(self.root, "remote", "set-url", "--add", "--push", "origin", str(bare))
        git(self.root, "remote", "set-url", "--add", "--push", "origin", str(self.tmp / "b.git"))
        self.assertEqual("mismatch", rm.status_report(self.root)["authorization"]["status"])
        git(self.root, "config", "--unset-all", "remote.origin.pushurl")
        (self.root / rm.AUTHORIZATION_REL).write_text("garbage", encoding="utf-8")
        self.assertEqual({"status": "unreadable", "remote": None, "branch": None},
                         rm.status_report(self.root)["authorization"])
        git(self.root, "remote", "remove", "origin")
        self.assertEqual("not_required", rm.status_report(self.root)["authorization"]["status"])

    def test_an_unreadable_pending_mutation_is_reported_never_repaired(self) -> None:
        (self.root / rm.MUTATIONS_DIR).mkdir(parents=True)
        stray = self.root / rm.MUTATIONS_DIR / f"{ids.new_id('root_policy_mutation')}.yaml"
        stray.write_text("garbage\n", encoding="utf-8")
        report = rm.status_report(self.root)
        self.assertEqual({"mutation_id": None, "operation": None, "status": "reconcile_required", "stage": None},
                         report["pending_mutation"])
        self.assertEqual("garbage\n", stray.read_text(encoding="utf-8"))

    def test_an_indirected_runtime_is_reported_and_never_followed(self) -> None:
        if os.name != "nt":
            self.skipTest("junctions are a Windows construct")
        self.add_remote()
        decoy = self.new_dir("decoy")
        (decoy / "mutations").mkdir()
        if not make_junction(self.root / rm.RUNTIME_DIR, decoy):
            self.skipTest("cannot create a junction here")
        before = snapshot(decoy)
        report = rm.status_report(self.root)
        self.assertEqual({"status": "unreadable", "remote": None, "branch": None}, report["authorization"])
        self.assertEqual("reconcile_required", report["pending_mutation"]["status"])
        self.assertEqual(before, snapshot(decoy))

    def test_the_current_change_and_its_evaluations_under_a_materialized_version_2(self) -> None:
        v2 = v2_global_policy()
        materialized = policy.GlobalPolicyBaseline(policy.materialized_baseline_record(v2, (), ()))
        self.loader.return_value = materialized
        current, older = ids.new_id("review_global_policy_change"), ids.new_id("review_global_policy_change")
        evaluations = sorted(ids.new_id("review_global_policy_evaluation") for _ in range(2))
        foreign = ids.new_id("review_global_policy_evaluation")
        self.write_record(ROOT_POLICY_LAYOUT.global_change_rel(current),
                          {"global_policy_change_id": current, "after_global_policy_digest": policy.global_policy_digest(v2)})
        self.write_record(ROOT_POLICY_LAYOUT.global_change_rel(older),
                          {"global_policy_change_id": older, "after_global_policy_digest": "b" * 64})
        for evaluation in evaluations:
            self.write_record(ROOT_POLICY_LAYOUT.global_evaluation_rel(evaluation),
                              {"evaluation_id": evaluation, "global_policy_change_id": current})
        self.write_record(ROOT_POLICY_LAYOUT.global_evaluation_rel(foreign),
                          {"evaluation_id": foreign, "global_policy_change_id": older})
        (self.root / ROOT_POLICY_LAYOUT.patch_notes_dir).mkdir(parents=True)
        (self.root / ROOT_POLICY_LAYOUT.patch_note_rel(current)).write_text("# note\n", encoding="utf-8")
        report = rm.status_report(self.root)
        self.assertEqual({"source_mode": policy.SOURCE_MODE_MATERIALIZED, "version": 2,
                          "digest": policy.global_policy_digest(v2)}, report["global_policy"])
        self.assertEqual(current, report["current_change_id"])
        self.assertEqual(evaluations, report["evaluation_ids"])
        self.assertEqual(policy.COMPATIBILITY_TOTAL_ADAPTER_V1, report["next_boundary_adapter_identity"])
        self.assertPrivate(report)
        # RB7BL-3: a stored record that is not canonical is never read past: the call raises its StopError, and
        # the RB1 caller's isolation (IR-RB7-5) renders the key unavailable with that code
        (self.root / ROOT_POLICY_LAYOUT.global_change_rel(older)).write_bytes(b"global_policy_change_id: x\r\n")
        with self.assertRaises(StopError) as caught:
            rm.status_report(self.root)
        self.assertEqual("review_record_noncanonical", caught.exception.code)
        from workline import status as rb1_status

        rendered = rb1_status._isolated(lambda: rm.status_report(self.root))
        self.assertEqual("unavailable", rendered["status"])
        self.assertEqual("review_record_noncanonical", rendered["reason"]["code"])
        self.assertPrivate(rendered)

    def test_an_indirected_root_record_family_is_never_followed(self) -> None:
        if os.name != "nt":
            self.skipTest("junctions are a Windows construct")
        decoy = self.new_dir("decoy-changes")
        change = ids.new_id("review_global_policy_change")
        (decoy / f"{change}.yaml").write_bytes(serialize.canonical_bytes(
            {"schema": "x", "version": 1, "global_policy_change_id": change,
             "after_global_policy_digest": self.current.global_policy_identity}))
        (self.root / "review-policy").mkdir()
        if not make_junction(self.root / ROOT_POLICY_LAYOUT.changes_dir, decoy):
            self.skipTest("cannot create a junction here")
        with self.assertRaises(StopError) as caught:
            rm.status_report(self.root)
        self.assertEqual("review_containment", caught.exception.code)
        from workline import status as rb1_status

        self.assertEqual("review_containment",
                         rb1_status._isolated(lambda: rm.status_report(self.root))["reason"]["code"])

    def write_record(self, relative: str, record: dict) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(serialize.canonical_bytes({"schema": "x", "version": 1, **record}))


def p7_root_copy(dest: Path) -> Path:
    """A copied Workline root carrying its tracked Global policy (P7 §31.2, RB7C-7): the loader requires the file.

    ``copy_workline_root`` gains the file itself with RB7's shared helper change (IR-RB7-6); until then the copy is
    completed here, and afterwards this adds nothing.
    """
    root = copy_workline_root(dest)
    target = root.joinpath(*policy.GLOBAL_POLICY_REL.split("/"))
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(WORKLINE_ROOT.joinpath(*policy.GLOBAL_POLICY_REL.split("/")).read_bytes())
    return root


class RealRootStatusTests(WorklineTestCase):
    def test_a_copied_workline_root_reports_from_its_own_loader_and_creates_nothing(self) -> None:
        root = p7_root_copy(self.tmp / "copied-root")
        git(root, "init", "-q", "-b", "main")
        (root / ".gitignore").write_bytes(IGNORE_RULE.encode("utf-8"))
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "base")
        before = snapshot(root)
        report = rm.status_report(root)
        self.assertEqual(before, snapshot(root))
        baseline = policy.load_global_baseline(root)
        self.assertEqual(policy.SOURCE_MODE_MATERIALIZED, baseline.source_mode)
        self.assertEqual({"source_mode": baseline.source_mode, "version": baseline.version,
                          "digest": baseline.global_policy_identity}, report["global_policy"])
        if baseline.version == 1:
            self.assertEqual(policy.global_policy_digest(v1_global_policy()), report["global_policy"]["digest"])
            self.assertEqual(policy.COMPATIBILITY_EXACT_DERIVED_SEMANTIC, report["next_boundary_adapter_identity"])
        self.assertEqual({"status", "global_policy", "current_change_id", "evaluation_ids", "authorization",
                          "pending_mutation", "next_boundary_adapter_identity"}, set(report))
        self.assertFalse(os.path.lexists(root / ".workline"))
        self.assertEqual(set(), keys_at_any_depth(report) & FORBIDDEN_KEYS)


def socket_name() -> str:
    import socket

    return socket.gethostname()


if __name__ == "__main__":
    unittest.main()
