"""BL-008: Workline runs on a supported interpreter with the configured Workline root's implementation.

The canonical entry is ``<R>/run-workline.py``, started as ``py -3 -I -B`` on
Windows or ``python3 -I -B`` on POSIX. It runs ``<R>/src/workline`` with nothing
installed and proves by origin verification — not by a successful import and not
by ``-I`` — that every loaded ``workline`` module comes from there (Layer 1).
Inside the implementation, state-changing operations, Project開始 and
``validate-project`` check the loaded implementation against the configured root
however ``workline`` was imported (Layer 2): after the Project context and before
the execution lock, so a mismatch writes nothing.

Most checks start separate processes, because the interpreter, its import path
and its loaded modules are exactly what is under test. Copies of this Workline
root stand in for other clones, and a throwaway virtual environment stands in
for an interpreter with Workline in its site-packages. These run on Windows;
nothing here claims that POSIX was exercised.
"""

from __future__ import annotations

import base64
import contextlib
from importlib.machinery import ModuleSpec
from importlib.util import spec_from_file_location
import hashlib
import io
import json
import locale
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import textwrap
import tomllib
import types
import unittest
from unittest import mock

from helpers import (
    LAUNCHER_NAME,
    WORKLINE_ROOT,
    WorklineTestCase,
    completing_executor,
    copy_workline_root,
    cwd,
    git,
    launcher_command,
    rmtree,
    run_python,
)

from workline import bootstrap as bs
from workline import implementation, oplock, yamlish
from workline import project_start as ps
from workline import roadmap as rm
from workline import start as st
from workline.bootstrap import render_bootstrap
from workline.cli import main as cli_main
from workline.create import WorkSpec, create_standalone_work
from workline.errors import (
    ForeignProjectMutation,
    ImplementationMismatch,
    ImplementationUnverified,
    PythonUnsupported,
    implementation_error,
)
from workline.implementation import (
    IMPLEMENTATION_MISMATCH,
    IMPLEMENTATION_UNVERIFIED,
    PYTHON_UNSUPPORTED,
    IdentityProblem,
    loaded_implementation_problem,
)
from workline.mutation import INTENT_VERSION
from workline.push_pin import pin_push_destination
from workline.state import ProjectView
from workline.store import RULE_REFS, ProjectStore, PushPin, render_project_yaml

REGISTRY = WORKLINE_ROOT / "registry.md"
README = WORKLINE_ROOT / "README.md"
BOOTSTRAP_SHA256 = "e33cdc421138f002ed086315fbcd4d712ae8df5b7efaae63aa91d18d33579786"
POWERSHELL_EXAMPLE_MARKER = "'@ | py -3 -I -B -"
POSIX_EXAMPLE_MARKER = "python3 -I -B - <<'PY'"

REPORT_ORIGINS = textwrap.dedent(
    """\
    import json as _json, sys as _sys
    print("ORIGINS " + _json.dumps(sorted({
        _module.__file__ for _name, _module in _sys.modules.items() if _name == "workline" or _name.startswith("workline.")
    })))
    """
)


# --------------------------------------------------------------------------- helpers

def activation(root: Path) -> str:
    """The canonical start of an API driver: activate ``root`` in this process, then import."""
    return (
        "import runpy\n\n"
        f'activate = runpy.run_path(r"{Path(root) / LAUNCHER_NAME}")["activate"]\n'
        "activate()\n\n"
        "# only after activation:\n"
    )


def driver_command(python: object = sys.executable, flags: tuple[str, ...] = ("-I", "-B")) -> list[str]:
    """An API driver process reading its source from stdin."""
    return [str(python), *flags, "-"]


def origins_of(output: str) -> list[Path]:
    reports = [line for line in output.splitlines() if line.startswith("ORIGINS ")]
    if len(reports) != 1:
        raise AssertionError(f"no origin report in: {output}")
    return [Path(path) for path in json.loads(reports[0][len("ORIGINS "):])]


def same_directory(first: object, second: object) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def fake_workline(parent: Path) -> Path:
    """A package named ``workline`` that leaves a marker file behind when anything imports it."""
    marker = parent / "fake-workline-was-imported"
    package = parent / "workline"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(f"open({str(marker)!r}, 'w').close()\n", encoding="utf-8")
    return marker


def preload_line(root: Path) -> str:
    """A ``.pth`` line that imports ``root``'s workline package while the interpreter starts."""
    source = str(root / "src")
    return f"import sys; sys.path.insert(0, {source!r}); import workline; sys.path.remove({source!r})\n"


def workline_state(store: ProjectStore) -> dict:
    """What a stopped operation must leave exactly as it was: everything under .workline, and Git."""
    files = {
        path.relative_to(store.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "<dir>"
        for path in sorted(store.workline.rglob("*"))
    }
    return {
        "workline": files,
        "head": git(store.root, "rev-parse", "HEAD").strip(),
        "index": git(store.root, "ls-files", "-s"),
        "status": git(store.root, "status", "--porcelain", "--untracked-files=all"),
    }


def workline_modules() -> dict[str, object]:
    return {name: module for name, module in sys.modules.items() if name == "workline" or name.startswith("workline.")}


def module_at(name: str, origin: Path, *, package_directory: Path | None = None) -> types.ModuleType:
    """A module object whose spec says it was loaded from ``origin`` (it is never executed)."""
    if package_directory is None:
        spec = ModuleSpec(name, None, origin=str(origin))
        spec.has_location = True
    else:
        spec = spec_from_file_location(name, origin, submodule_search_locations=[str(package_directory)])
    module = types.ModuleType(name)
    module.__spec__ = spec
    if package_directory is not None:
        module.__path__ = [str(package_directory)]
    return module


def older_python() -> list[str] | None:
    """A command running an installed Python older than Workline requires, when there is one."""
    candidates: list[list[str]] = []
    if shutil.which("py"):
        candidates += [["py", f"-3.{minor}"] for minor in (10, 9, 8)]
    for minor in (10, 9, 8):
        found = shutil.which(f"python3.{minor}")
        if found:
            candidates.append([found])
    for command in candidates:
        try:
            probe = subprocess.run(
                [*command, "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
                capture_output=True, text=True, timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        parts = probe.stdout.split()
        if probe.returncode == 0 and len(parts) == 2 and (int(parts[0]), int(parts[1])) < implementation.MINIMUM_PYTHON:
            return command
    return None


def fenced_block(text: str, marker: str) -> str:
    """The one fenced code block in ``text`` that contains ``marker``."""
    blocks = [block for block in re.findall(r"^```[^\n]*\n(.*?)^```", text, re.S | re.M) if marker in block]
    if len(blocks) != 1:
        raise AssertionError(f"expected exactly one code block containing {marker!r}, found {len(blocks)}")
    return blocks[0]


class IdentityTestCase(WorklineTestCase):
    def configure_root(self, store: ProjectStore, root: Path) -> None:
        """Point the Project's configured Workline root at ``root``, as a committed project.yaml change."""
        store.project_yaml.write_text(render_project_yaml(root, store.read_push_pin()), encoding="utf-8")
        git(store.root, "add", ".workline/project.yaml")
        git(store.root, "commit", "-q", "-m", "configure another Workline root")

    def assertPassed(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assertStopped(self, result: subprocess.CompletedProcess, code: str) -> None:
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(f"STOP [{code}]", result.stdout, result.stdout + result.stderr)

    def assertRunsFrom(self, origins: list[Path], root: Path) -> None:
        package = root / "src" / "workline"
        self.assertTrue(origins)
        for origin in origins:
            self.assertTrue(same_directory(origin.parent, package), f"{origin} is not in {package}")


# --------------------------------------------------------------------------- the launcher

class CanonicalLauncherTests(IdentityTestCase):
    def test_the_launcher_runs_the_configured_implementation(self) -> None:
        store = self.new_project()
        checked = run_python(launcher_command(WORKLINE_ROOT, "validate-project", "."), cwd=store.root)
        self.assertPassed(checked)
        self.assertIn("project validation: PASS", checked.stdout)

        created = run_python(
            launcher_command(WORKLINE_ROOT, "create-work", ".", "--name", "Doc", "--desired-state", "docs exist"),
            cwd=store.root,
        )
        self.assertPassed(created)
        work_id = re.search(r"create-work: (w_\S+)", created.stdout).group(1)
        self.assertIn(work_id, ProjectView.load(store).works)

    def test_an_unsupported_python_stops_before_anything_is_written(self) -> None:
        old = older_python()
        if old is None:
            self.skipTest("no Python older than 3.11 is installed")
        root = copy_workline_root(self.tmp / "root")
        target = self.new_dir("target")

        started = run_python(
            [*old, "-I", "-B", str(root / LAUNCHER_NAME), "project-start", str(target), "--workline-root", str(root)],
            cwd=root,
        )
        self.assertStopped(started, "workline_python_unsupported")
        self.assertIn("3.11", started.stdout)
        self.assertEqual(list(target.iterdir()), [])

        activated = run_python(driver_command(old[0], (*old[1:], "-I", "-B")), cwd=self.tmp, stdin=activation(root) + "print('API imported')\n")
        self.assertStopped(activated, "workline_python_unsupported")
        self.assertNotIn("API imported", activated.stdout)
        self.assertEqual(sorted(root.rglob("__pycache__")), [])

    def test_layer_2_refuses_an_unsupported_python_before_the_lock(self) -> None:
        store = self.new_project()
        before = workline_state(store)
        with mock.patch.object(sys, "version_info", (3, 10, 11, "final", 0)):
            with self.assertRaises(PythonUnsupported) as ctx:
                create_standalone_work(store, WorkSpec("Unsupported", "never registered"))
        self.assertIn("3.10.11", ctx.exception.message)
        self.assertFalse(store.locks.exists())
        self.assertEqual(workline_state(store), before)

    def test_the_launcher_requires_isolated_mode(self) -> None:
        root = copy_workline_root(self.tmp / "root")
        cli = run_python(launcher_command(root, "validate-registry", root, flags=("-B",)), cwd=self.tmp)
        self.assertStopped(cli, "workline_invocation_not_isolated")
        api = run_python(driver_command(flags=("-B",)), cwd=self.tmp, stdin=activation(root) + "print('API imported')\n")
        self.assertStopped(api, "workline_invocation_not_isolated")
        self.assertNotIn("API imported", api.stdout)

    def test_the_canonical_runtime_writes_no_bytecode(self) -> None:
        root = copy_workline_root(self.tmp / "root")
        # -B is part of the canonical form, and the launcher turns bytecode off by itself as well
        for flags in (("-I", "-B"), ("-I",)):
            with self.subTest(flags=flags):
                self.assertPassed(run_python(launcher_command(root, "validate-registry", root, flags=flags), cwd=self.tmp))
                driver = activation(root) + "from workline import roadmap, start\n"
                self.assertPassed(run_python(driver_command(flags=flags), cwd=self.tmp, stdin=driver))
        self.assertEqual(sorted(root.rglob("__pycache__")), [])
        self.assertEqual(sorted(root.rglob("*.pyc")), [])

    def test_a_workline_on_pythonpath_is_not_adopted(self) -> None:
        root = copy_workline_root(self.tmp / "root")
        parent = self.new_dir("pythonpath")
        marker = fake_workline(parent)
        environment = {**os.environ, "PYTHONPATH": str(parent)}

        self.assertPassed(run_python(launcher_command(root, "validate-registry", root), cwd=self.tmp, env=environment))
        driven = run_python(driver_command(), cwd=self.tmp, env=environment, stdin=activation(root) + REPORT_ORIGINS)
        self.assertPassed(driven)
        self.assertRunsFrom(origins_of(driven.stdout), root)
        self.assertFalse(marker.exists())

        # the same PYTHONPATH does reach a process that is not isolated
        ambient = run_python([sys.executable, "-B", "-c", "import workline"], cwd=self.tmp, env=environment)
        self.assertTrue(marker.exists(), ambient.stdout + ambient.stderr)

    def test_a_workline_in_the_working_directory_is_not_adopted(self) -> None:
        root = copy_workline_root(self.tmp / "root")
        here = self.new_dir("here")
        marker = fake_workline(here)

        self.assertPassed(run_python(launcher_command(root, "validate-registry", root), cwd=here))
        driven = run_python(driver_command(), cwd=here, stdin=activation(root) + REPORT_ORIGINS)
        self.assertPassed(driven)
        self.assertRunsFrom(origins_of(driven.stdout), root)
        self.assertFalse(marker.exists())

        # the working directory does reach a process that is not isolated
        ambient = run_python([sys.executable, "-B", "-c", "import workline"], cwd=here)
        self.assertTrue(marker.exists(), ambient.stdout + ambient.stderr)

    def test_the_launcher_only_dispatches_existing_cli_commands(self) -> None:
        root = copy_workline_root(self.tmp / "root")
        marker = self.tmp / "driver-ran"
        for args in (("bogus-command",), ("-c", f"open({str(marker)!r}, 'w').close()"), ("run", "driver.py")):
            with self.subTest(args=args):
                result = run_python(launcher_command(root, *args), cwd=self.tmp)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("invalid choice", result.stderr)
        self.assertFalse(marker.exists())

    def test_an_identity_stop_reports_roots_and_interpreter_but_no_environment(self) -> None:
        store = self.new_project()
        other = copy_workline_root(self.tmp / "other")
        secret = "wl-test-secret-4f2c9e"
        hidden = self.new_dir(f"hidden-{secret}")
        environment = {**os.environ, "WORKLINE_TEST_SECRET": secret, "PYTHONPATH": str(hidden)}

        result = run_python(launcher_command(other, "validate-project", "."), cwd=store.root, env=environment)

        self.assertStopped(result, "workline_implementation_mismatch")
        self.assertIn(str(store.workline_root()), result.stdout)
        self.assertIn(str(other / "src" / "workline"), result.stdout)
        self.assertIn(sys.executable, result.stdout)
        self.assertIn(".".join(str(part) for part in sys.version_info[:3]), result.stdout)
        self.assertNotIn(secret, result.stdout + result.stderr)

        # Layer 2 in this process reports no import path either
        self.configure_root(store, other)
        marker_entry = str(self.tmp / f"sys-path-{secret}")
        sys.path.append(marker_entry)
        self.addCleanup(sys.path.remove, marker_entry)
        with self.assertRaises(ImplementationMismatch) as ctx:
            create_standalone_work(store, WorkSpec("Mismatch", "never registered"))
        self.assertNotIn(secret, ctx.exception.message)


# --------------------------------------------------------------------------- classification of loaded modules

class LoadedModuleClassificationTests(IdentityTestCase):
    def test_this_process_runs_the_repository_implementation(self) -> None:
        self.assertIsNone(loaded_implementation_problem(WORKLINE_ROOT))

    def test_nothing_loaded_is_accepted_only_before_loading(self) -> None:
        self.assertIsNone(loaded_implementation_problem(WORKLINE_ROOT, allow_unloaded=True, modules={}))
        self.assertEqual(loaded_implementation_problem(WORKLINE_ROOT, modules={}).code, IMPLEMENTATION_UNVERIFIED)

    def test_a_single_package_elsewhere_is_a_mismatch(self) -> None:
        other = copy_workline_root(self.tmp / "other")
        directory = other / "src" / "workline"
        package = module_at("workline", directory / "__init__.py", package_directory=directory)
        self.assertEqual(loaded_implementation_problem(WORKLINE_ROOT, modules={"workline": package}).code, IMPLEMENTATION_MISMATCH)
        self.assertIsNone(loaded_implementation_problem(other, modules={"workline": package}))

        plain = self.tmp / "plain" / "workline.py"
        plain.parent.mkdir()
        plain.write_text("", encoding="utf-8")
        self.assertEqual(
            loaded_implementation_problem(WORKLINE_ROOT, modules={"workline": module_at("workline", plain)}).code,
            IMPLEMENTATION_MISMATCH,
        )

    def test_modules_from_more_than_one_place_are_unverified(self) -> None:
        other = copy_workline_root(self.tmp / "other")
        stray = module_at("workline.stray", other / "src" / "workline" / "errors.py")
        modules = {**workline_modules(), "workline.stray": stray}
        self.assertEqual(loaded_implementation_problem(WORKLINE_ROOT, modules=modules).code, IMPLEMENTATION_UNVERIFIED)

        # the package from this root with its __path__ widened to another one
        widened = types.ModuleType("workline")
        widened.__spec__ = sys.modules["workline"].__spec__
        widened.__path__ = [str(WORKLINE_ROOT / "src" / "workline"), str(other / "src" / "workline")]
        self.assertEqual(loaded_implementation_problem(WORKLINE_ROOT, modules={"workline": widened}).code, IMPLEMENTATION_UNVERIFIED)

    def test_origins_that_are_not_source_files_are_unverified(self) -> None:
        bytecode = self.tmp / "stray.pyc"
        bytecode.write_bytes(b"")
        extension = self.tmp / "stray.pyd"
        extension.write_bytes(b"")
        namespace = types.ModuleType("workline")
        namespace.__spec__ = ModuleSpec("workline", None, is_package=True)
        namespace.__path__ = [str(WORKLINE_ROOT / "src" / "workline")]
        cases = {
            "no spec and no file": {"workline.stray": types.ModuleType("workline.stray")},
            "built-in": {"workline.stray": self._with_spec(ModuleSpec("workline.stray", None, origin="built-in"))},
            "frozen": {"workline.stray": self._with_spec(ModuleSpec("workline.stray", None, origin="frozen"))},
            "sourceless bytecode": {"workline.stray": module_at("workline.stray", bytecode)},
            "extension module": {"workline.stray": module_at("workline.stray", extension)},
            "source file that is gone": {"workline.stray": module_at("workline.stray", WORKLINE_ROOT / "src" / "workline" / "gone.py")},
            "import blocker": {"workline.stray": None},
        }
        for label, extra in cases.items():
            with self.subTest(case=label):
                modules = {**workline_modules(), **extra}
                self.assertEqual(loaded_implementation_problem(WORKLINE_ROOT, modules=modules).code, IMPLEMENTATION_UNVERIFIED)
        with self.subTest(case="namespace package"):
            self.assertEqual(loaded_implementation_problem(WORKLINE_ROOT, modules={"workline": namespace}).code, IMPLEMENTATION_UNVERIFIED)

    def test_each_layer_2_problem_is_a_stop_with_its_own_code(self) -> None:
        for code, error_class in (
            (PYTHON_UNSUPPORTED, PythonUnsupported),
            (IMPLEMENTATION_UNVERIFIED, ImplementationUnverified),
            (IMPLEMENTATION_MISMATCH, ImplementationMismatch),
        ):
            with self.subTest(code=code):
                error = implementation_error(IdentityProblem(code, "why"))
                self.assertIsInstance(error, error_class)
                self.assertEqual((error.code, error.message), (code, "why"))

    @staticmethod
    def _with_spec(spec: ModuleSpec) -> types.ModuleType:
        module = types.ModuleType(spec.name)
        module.__spec__ = spec
        return module


# --------------------------------------------------------------------------- Workline installed in site-packages

class InstalledWorklineTests(IdentityTestCase):
    """A Workline that site-packages makes importable is never what the canonical launcher runs.

    ``-I`` does not keep system site-packages out, so a throwaway virtual
    environment stands in for an interpreter with Workline installed.
    """

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.environment_parent = Path(tempfile.mkdtemp(prefix="workline-venv-"))
        venv = cls.environment_parent / "venv"
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True, capture_output=True, timeout=600)
        cls.python = venv / "Scripts" / "python.exe" if os.name == "nt" else venv / "bin" / "python"
        purelib = subprocess.run(
            [str(cls.python), "-I", "-B", "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
            check=True, capture_output=True, text=True, timeout=300,
        )
        cls.site_packages = Path(purelib.stdout.strip())

    @classmethod
    def tearDownClass(cls) -> None:
        rmtree(cls.environment_parent)
        super().tearDownClass()

    def in_site_packages(self, name: str, *, text: str | None = None, tree: Path | None = None) -> None:
        path = self.site_packages / name
        if tree is not None:
            shutil.copytree(tree, path)
            self.addCleanup(rmtree, path)
        else:
            path.write_text(text or "", encoding="utf-8")
            self.addCleanup(path.unlink)

    def ambient_workline(self) -> Path | None:
        """Where a plain ``import workline`` would come from in the environment's isolated interpreter."""
        probe = run_python(
            [str(self.python), "-I", "-B", "-c", "import importlib.util as u; s = u.find_spec('workline'); print(s.origin if s else '')"],
            cwd=self.tmp,
        )
        found = probe.stdout.strip()
        return Path(found) if found else None

    def test_a_fresh_root_runs_with_no_workline_installed(self) -> None:
        self.assertIsNone(self.ambient_workline())
        root = copy_workline_root(self.tmp / "fresh")
        result = run_python(launcher_command(root, "validate-registry", root, python=self.python), cwd=self.tmp)
        self.assertPassed(result)
        self.assertIn("registry validation: PASS", result.stdout)

    def test_an_editable_install_of_another_clone_is_not_what_runs(self) -> None:
        root, other = copy_workline_root(self.tmp / "root"), copy_workline_root(self.tmp / "other")
        self.in_site_packages("__editable__.workline_core-0.1.0.pth", text=f"{other / 'src'}\n")
        self.assertTrue(same_directory(self.ambient_workline().parent, other / "src" / "workline"))

        self.assertPassed(run_python(launcher_command(root, "validate-registry", root, python=self.python), cwd=self.tmp))
        driven = run_python(driver_command(self.python), cwd=self.tmp, stdin=activation(root) + REPORT_ORIGINS)
        self.assertPassed(driven)
        self.assertRunsFrom(origins_of(driven.stdout), root)

    def test_a_workline_package_in_site_packages_is_not_what_runs(self) -> None:
        root, other = copy_workline_root(self.tmp / "root"), copy_workline_root(self.tmp / "other")
        self.in_site_packages("workline", tree=other / "src" / "workline")
        self.assertTrue(same_directory(self.ambient_workline().parent, self.site_packages / "workline"))

        self.assertPassed(run_python(launcher_command(root, "validate-registry", root, python=self.python), cwd=self.tmp))
        driven = run_python(driver_command(self.python), cwd=self.tmp, stdin=activation(root) + REPORT_ORIGINS)
        self.assertPassed(driven)
        self.assertRunsFrom(origins_of(driven.stdout), root)

    def test_another_root_loaded_while_the_interpreter_starts_stops(self) -> None:
        root, other = copy_workline_root(self.tmp / "root"), copy_workline_root(self.tmp / "other")
        self.in_site_packages("zz-preload-workline.pth", text=preload_line(other))

        result = run_python(launcher_command(root, "validate-registry", root, python=self.python), cwd=self.tmp)
        self.assertStopped(result, "workline_implementation_mismatch")
        self.assertIn(str(other / "src" / "workline"), result.stdout)

        driven = run_python(driver_command(self.python), cwd=self.tmp, stdin=activation(root) + "print('API imported')\n")
        self.assertStopped(driven, "workline_implementation_mismatch")
        self.assertNotIn("API imported", driven.stdout)

    def test_the_same_root_loaded_while_the_interpreter_starts_is_accepted(self) -> None:
        root = copy_workline_root(self.tmp / "root")
        self.in_site_packages("zz-preload-workline.pth", text=preload_line(root))
        self.assertPassed(run_python(launcher_command(root, "validate-registry", root, python=self.python), cwd=self.tmp))


# --------------------------------------------------------------------------- established Projects and Layer 2

class ProjectImplementationTests(IdentityTestCase):
    def test_another_roots_launcher_cannot_run_inside_a_project(self) -> None:
        store = self.new_project()
        other = copy_workline_root(self.tmp / "other")
        before = workline_state(store)
        commands = (
            ("validate-project", "."),
            ("create-work", ".", "--name", "Other", "--desired-state", "never registered"),
            ("backfill-bootstrap", "."),
            ("pin-push-destination", ".", "--url", str(self.tmp / "nowhere.git")),
            ("validate-registry", other),
        )
        for args in commands:
            with self.subTest(command=args[0]):
                result = run_python(launcher_command(other, *args), cwd=store.root)
                self.assertStopped(result, "workline_implementation_mismatch")
        self.assertFalse(store.locks.exists())
        self.assertEqual(workline_state(store), before)

    def test_validate_project_never_passes_under_another_implementation(self) -> None:
        store = self.new_project()
        other = copy_workline_root(self.tmp / "other")
        outside = self.new_dir("outside")

        self.assertStopped(
            run_python(launcher_command(other, "validate-project", store.root), cwd=outside), "workline_implementation_mismatch"
        )
        self.assertPassed(run_python(launcher_command(WORKLINE_ROOT, "validate-project", store.root), cwd=outside))

        # in this process too, however workline was imported
        self.configure_root(store, other)
        output = io.StringIO()
        with cwd(outside), contextlib.redirect_stdout(output):
            self.assertEqual(cli_main(["validate-project", str(store.root)]), 1)
        self.assertIn("STOP [workline_implementation_mismatch]", output.getvalue())

    def test_only_the_newly_configured_root_runs_after_the_root_changes(self) -> None:
        store = self.new_project()
        other = copy_workline_root(self.tmp / "other")
        self.configure_root(store, other)

        self.assertStopped(
            run_python(launcher_command(WORKLINE_ROOT, "validate-project", "."), cwd=store.root), "workline_implementation_mismatch"
        )
        self.assertPassed(run_python(launcher_command(other, "validate-project", "."), cwd=store.root))
        created = run_python(
            launcher_command(other, "create-work", ".", "--name", "Moved", "--desired-state", "done"), cwd=store.root
        )
        self.assertPassed(created)
        self.assertIn(re.search(r"create-work: (w_\S+)", created.stdout).group(1), ProjectView.load(store).works)

        # this test process runs the repository implementation, which the Project no longer accepts
        with self.assertRaises(ImplementationMismatch):
            create_standalone_work(store, WorkSpec("In process", "never registered"))

    def test_a_foreign_project_is_reported_before_an_implementation_mismatch(self) -> None:
        target = self.new_project("target")
        self.configure_root(target, copy_workline_root(self.tmp / "other"))
        before = workline_state(target)
        self.new_project("here")  # working inside another Project from now on

        with self.assertRaises(ForeignProjectMutation):
            create_standalone_work(ProjectStore(target.root), WorkSpec("Foreign", "never registered"))
        with cwd(target.root), self.assertRaises(ImplementationMismatch):
            create_standalone_work(ProjectStore(target.root), WorkSpec("Mismatch", "never registered"))

        self.assertFalse(target.locks.exists())
        self.assertEqual(workline_state(target), before)

    def test_an_implementation_mismatch_takes_no_lock_and_writes_nothing(self) -> None:
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        existing = create_standalone_work(store, WorkSpec("Existing", "done"))
        self.configure_root(store, copy_workline_root(self.tmp / "other"))
        shutil.rmtree(store.locks)  # left by the operations above; nothing below may bring it back
        before = workline_state(store)

        def hold_the_lock() -> None:
            with oplock.project_operation(store, "probe"):
                self.fail("a mismatched implementation must never hold the lock")

        attempts = {
            "project operation": hold_the_lock,
            "standalone CREATE": lambda: create_standalone_work(store, WorkSpec("Mismatch", "never registered")),
            "Roadmap hold": lambda: rm.hold_roadmap(store, roadmap.roadmap_id),
            "START": lambda: st.start(store, existing.work_id, "single-work", completing_executor(store)),
            "bootstrap backfill": lambda: bs.backfill_bootstrap(store.root),
            "push destination pin": lambda: pin_push_destination(store.root, [str(self.tmp / "nowhere.git")]),
        }
        for label, attempt in attempts.items():
            with self.subTest(operation=label):
                with self.assertRaises(ImplementationMismatch):
                    attempt()
                self.assertFalse(store.locks.exists())
                self.assertIsNone(oplock.held_lock(store))
        self.assertEqual(workline_state(store), before)


class ProjectStartImplementationTests(IdentityTestCase):
    def test_project_start_through_the_launcher_of_the_root_it_configures(self) -> None:
        root = copy_workline_root(self.tmp / "root")
        target = self.new_dir("target")

        started = run_python(launcher_command(root, "project-start", target, "--workline-root", root), cwd=root)

        self.assertPassed(started)
        self.assertIn("project-start: initialized", started.stdout)
        store = ProjectStore(target)
        self.assertTrue(same_directory(store.workline_root(), root))
        self.assertEqual(set(store.load_project_yaml()), {"workline", "rules"})  # no runtime information in the Project
        self.assertPassed(run_python(launcher_command(root, "validate-project", "."), cwd=target))

    def test_project_start_for_another_workline_root_writes_nothing(self) -> None:
        root = copy_workline_root(self.tmp / "root")
        target = self.new_dir("target")

        result = run_python(launcher_command(root, "project-start", target, "--workline-root", WORKLINE_ROOT), cwd=root)

        self.assertStopped(result, "workline_implementation_mismatch")
        self.assertEqual(list(target.iterdir()), [])

    def test_project_start_in_process_refuses_a_root_that_is_not_the_running_implementation(self) -> None:
        target = self.new_dir("target")
        other = copy_workline_root(self.tmp / "other")
        with cwd(self.tmp), self.assertRaises(ImplementationMismatch):
            ps.project_start(target, other)
        self.assertEqual(list(target.iterdir()), [])


# --------------------------------------------------------------------------- the Python API

class ApiActivationTests(IdentityTestCase):
    def test_activate_then_import_then_operate(self) -> None:
        store = self.new_project()
        operation = textwrap.dedent(
            """\
            from pathlib import Path
            from workline import roadmap as rm
            from workline.phase_create import PhaseSpec
            from workline.store import ProjectStore

            plan = rm.RoadmapPlan("日本語のRoadmap", "背景", "達成したい状態です", {"a": PhaseSpec("フェーズA", "Aが成立する")})
            print("ROADMAP", rm.create_roadmap(ProjectStore(Path.cwd()), plan).roadmap_id)
            """
        )
        result = run_python(driver_command(), cwd=store.root, stdin=activation(WORKLINE_ROOT) + operation)
        self.assertPassed(result)
        roadmap = ProjectView.load(store).roadmaps[re.search(r"ROADMAP (r_\S+)", result.stdout).group(1)]
        self.assertEqual(roadmap.name, "日本語のRoadmap")

    def test_a_workline_imported_from_another_root_before_activation_stops(self) -> None:
        root, other = copy_workline_root(self.tmp / "root"), copy_workline_root(self.tmp / "other")
        driver = f'import sys\nsys.path.insert(0, r"{other / "src"}")\nimport workline\n' + activation(root) + "print('API imported')\n"
        result = run_python(driver_command(), cwd=self.tmp, stdin=driver)
        self.assertStopped(result, "workline_implementation_mismatch")
        self.assertNotIn("API imported", result.stdout)

    def test_activating_the_same_root_again_passes(self) -> None:
        root = copy_workline_root(self.tmp / "root")
        result = run_python(driver_command(), cwd=self.tmp, stdin=activation(root) + "activate()\nactivate()\n" + REPORT_ORIGINS)
        self.assertPassed(result)
        self.assertRunsFrom(origins_of(result.stdout), root)

    def test_activating_a_second_root_in_the_same_process_stops(self) -> None:
        first, second = copy_workline_root(self.tmp / "first"), copy_workline_root(self.tmp / "second")
        driver = activation(first) + f'runpy.run_path(r"{second / LAUNCHER_NAME}")["activate"]()\nprint("second activation passed")\n'
        result = run_python(driver_command(), cwd=self.tmp, stdin=driver)
        self.assertStopped(result, "workline_implementation_mismatch")
        self.assertNotIn("second activation passed", result.stdout)

    def test_modules_from_two_roots_in_one_process_stop_as_unverified(self) -> None:
        root, other = copy_workline_root(self.tmp / "root"), copy_workline_root(self.tmp / "other")
        driver = activation(root) + textwrap.dedent(
            f"""\
            import importlib.util, sys
            spec = importlib.util.spec_from_file_location("workline.stray", r"{other / 'src' / 'workline' / 'errors.py'}")
            stray = importlib.util.module_from_spec(spec)
            sys.modules["workline.stray"] = stray
            spec.loader.exec_module(stray)
            activate()
            print("activation passed")
            """
        )
        result = run_python(driver_command(), cwd=self.tmp, stdin=driver)
        self.assertStopped(result, "workline_implementation_unverified")
        self.assertNotIn("activation passed", result.stdout)

    def test_a_module_without_a_source_origin_stops_as_unverified(self) -> None:
        root = copy_workline_root(self.tmp / "root")
        driver = activation(root) + (
            "import sys, types\n"
            "sys.modules['workline.stray'] = types.ModuleType('workline.stray')\n"
            "activate()\n"
            "print('activation passed')\n"
        )
        result = run_python(driver_command(), cwd=self.tmp, stdin=driver)
        self.assertStopped(result, "workline_implementation_unverified")
        self.assertNotIn("activation passed", result.stdout)

    def test_activation_is_not_inherited_by_another_process(self) -> None:
        root = copy_workline_root(self.tmp / "root")
        child_code = (
            "import json, os, sys; print(json.dumps({"
            "'isolated': sys.flags.isolated, "
            f"'root_source_on_path': any(os.path.normcase(os.path.abspath(p)) == os.path.normcase({str(root / 'src')!r}) for p in sys.path if p), "
            "'workline_loaded': any(n == 'workline' or n.startswith('workline.') for n in sys.modules)}))"
        )
        driver = (
            "import os, subprocess, sys\n"
            "environment_before = dict(os.environ)\n"
            + activation(root)
            + "assert dict(os.environ) == environment_before, 'activate() changed the environment'\n"
            + f"child = subprocess.run([sys.executable, '-c', {child_code!r}], capture_output=True, text=True)\n"
            + "print('CHILD ' + child.stdout.strip() + child.stderr.strip())\n"
        )
        result = run_python(driver_command(), cwd=self.tmp, stdin=driver)
        self.assertPassed(result)
        child = json.loads(result.stdout.split("CHILD ", 1)[1].splitlines()[0])
        self.assertEqual(child, {"isolated": 0, "root_source_on_path": False, "workline_loaded": False})
        self.assertEqual(sorted(root.rglob("__pycache__")), [])

    def test_a_child_process_with_another_implementation_is_stopped_by_layer_2(self) -> None:
        store = self.new_project()
        other = copy_workline_root(self.tmp / "other")
        child_code = textwrap.dedent(
            """\
            import json
            from pathlib import Path
            import workline
            from workline.create import WorkSpec, create_standalone_work
            from workline.errors import StopError
            from workline.store import ProjectStore
            try:
                create_standalone_work(ProjectStore(Path.cwd()), WorkSpec("From the child", "never registered"))
                outcome = "created"
            except StopError as exc:
                outcome = exc.code
            print(json.dumps({"outcome": outcome, "implementation": workline.__file__}))
            """
        )
        driver = (
            activation(WORKLINE_ROOT)
            + "import os, subprocess, sys\n"
            + f"environment = dict(os.environ, PYTHONPATH={str(other / 'src')!r})\n"
            + f"child = subprocess.run([sys.executable, '-B', '-c', {child_code!r}], capture_output=True, text=True, env=environment)\n"
            + "print('CHILD ' + child.stdout.strip() + child.stderr.strip())\n"
        )
        before = workline_state(store)

        result = run_python(driver_command(), cwd=store.root, stdin=driver)

        self.assertPassed(result)
        child = json.loads(result.stdout.split("CHILD ", 1)[1].splitlines()[0])
        self.assertEqual(child["outcome"], "workline_implementation_mismatch")
        self.assertTrue(same_directory(Path(child["implementation"]).parent, other / "src" / "workline"))
        self.assertFalse(store.locks.exists())
        self.assertEqual(workline_state(store), before)


# --------------------------------------------------------------------------- the documented invocations

class DocumentedInvocationTests(unittest.TestCase):
    def test_rules_state_the_canonical_cli_invocations(self) -> None:
        text = REGISTRY.read_text(encoding="utf-8")
        self.assertIn('py -3 -I -B "<R>\\run-workline.py" <command> ...', text)
        self.assertIn('python3 -I -B "<R>/run-workline.py" <command> ...', text)

    def test_rules_and_readme_show_the_same_api_examples(self) -> None:
        registry, readme = REGISTRY.read_text(encoding="utf-8"), README.read_text(encoding="utf-8")
        for marker in (POWERSHELL_EXAMPLE_MARKER, POSIX_EXAMPLE_MARKER):
            with self.subTest(example=marker):
                self.assertEqual(fenced_block(readme, marker), fenced_block(registry, marker))

    def test_the_api_examples_activate_before_any_workline_import(self) -> None:
        registry = REGISTRY.read_text(encoding="utf-8")
        for marker in (POWERSHELL_EXAMPLE_MARKER, POSIX_EXAMPLE_MARKER):
            with self.subTest(example=marker):
                block = fenced_block(registry, marker)
                activated = block.index("activate()\n")
                self.assertLess(activated, block.index("from workline import"))
                self.assertNotIn("workline import", block[:activated])
                self.assertIn("-I -B -", block)
        powershell = fenced_block(registry, POWERSHELL_EXAMPLE_MARKER)
        self.assertTrue(powershell.startswith("& {\n"))
        self.assertIn("$OutputEncoding = [System.Text.UTF8Encoding]::new($false)", powershell)


class PowerShellApiExampleTests(IdentityTestCase):
    """The PowerShell API example exactly as documented, run by Windows PowerShell 5.1 and PowerShell 7."""

    NON_ASCII_OPERATION = textwrap.dedent(
        """\
        from pathlib import Path
        from workline.phase_create import PhaseSpec
        from workline.store import ProjectStore

        plan = rm.RoadmapPlan("日本語のRoadmap", "背景です", "達成したい状態です", {"a": PhaseSpec("フェーズA", "Aが成立する")})
        print("ROADMAP", rm.create_roadmap(ProjectStore(Path.cwd()), plan).roadmap_id)
        """
    )

    def setUp(self) -> None:
        super().setUp()
        if os.name != "nt":
            self.skipTest("the PowerShell example is the Windows form")
        if shutil.which("py") is None:
            self.skipTest("the Python launcher py is not installed")
        probe = subprocess.run(
            ["py", "-3", "-c", "import sys; print(int(sys.version_info >= (3, 11)))"], capture_output=True, text=True, timeout=120
        )
        if probe.stdout.strip() != "1":
            self.skipTest("py -3 does not select Python 3.11 or newer")

    def shell(self, name: str) -> str:
        found = shutil.which(name)
        if found is None:
            self.skipTest(f"{name} is not installed")
        return found

    def run_example(self, shell: str, root: Path, operation: str, where: Path, *, example: str | None = None) -> str:
        example = example or fenced_block(REGISTRY.read_text(encoding="utf-8"), POWERSHELL_EXAMPLE_MARKER)
        self.assertEqual((example.count("<R>"), example.count("# operation...")), (1, 1))
        script = example.replace("<R>", str(root)).replace("# operation...", operation.rstrip("\n"))
        wrapper = "\n".join(
            [
                "$ProgressPreference = 'SilentlyContinue'",
                '"PSMAJOR=" + $PSVersionTable.PSVersion.Major',
                '"BEFORE=" + $OutputEncoding.WebName',
                script,
                '"EXIT=" + $LASTEXITCODE',
                '"AFTER=" + $OutputEncoding.WebName',
            ]
        )
        encoded = base64.b64encode(wrapper.encode("utf-16-le")).decode("ascii")
        completed = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], cwd=str(where), capture_output=True, timeout=600
        )
        encoding = locale.getpreferredencoding(False)
        return completed.stdout.decode(encoding, "replace") + completed.stderr.decode(encoding, "replace")

    @staticmethod
    def value(output: str, name: str) -> str:
        found = re.search(rf"^{name}=(.*?)\s*$", output, re.M)
        if found is None:
            raise AssertionError(f"{name} not reported: {output}")
        return found.group(1)

    def check_documented_example(self, shell_name: str) -> str:
        store = self.new_project()
        output = self.run_example(self.shell(shell_name), WORKLINE_ROOT, self.NON_ASCII_OPERATION, store.root)
        self.assertEqual(self.value(output, "EXIT"), "0", output)
        roadmap = ProjectView.load(store).roadmaps[re.search(r"ROADMAP (r_\S+)", output).group(1)]
        self.assertEqual(roadmap.name, "日本語のRoadmap")
        self.assertEqual(roadmap.section("達成したい状態"), "達成したい状態です")
        self.assertEqual(self.value(output, "BEFORE"), self.value(output, "AFTER"))  # the caller's $OutputEncoding is untouched
        return output

    def test_windows_powershell_5_1_delivers_non_ascii_driver_text(self) -> None:
        output = self.check_documented_example("powershell")
        self.assertEqual(self.value(output, "PSMAJOR"), "5")

        # why the example sets $OutputEncoding: without it Windows PowerShell 5.1 turns the text into "?"
        example = fenced_block(REGISTRY.read_text(encoding="utf-8"), POWERSHELL_EXAMPLE_MARKER)
        without = "\n".join(line for line in example.splitlines() if "$OutputEncoding" not in line) + "\n"
        probe = self.run_example(
            self.shell("powershell"), WORKLINE_ROOT, 'print("HEX", "日本語".encode("utf-8").hex())', self.tmp, example=without
        )
        self.assertIn("HEX 3f3f3f", probe)

    def test_powershell_7_delivers_non_ascii_driver_text(self) -> None:
        output = self.check_documented_example("pwsh")
        self.assertGreaterEqual(int(self.value(output, "PSMAJOR")), 7)

    def test_a_stop_reaches_lastexitcode(self) -> None:
        store = self.new_project()
        other = copy_workline_root(self.tmp / "other")
        shells = [name for name in ("powershell", "pwsh") if shutil.which(name)]
        if not shells:
            self.skipTest("no PowerShell is installed")
        for name in shells:
            with self.subTest(shell=name):
                output = self.run_example(shutil.which(name), other, "print('API imported')", store.root)
                self.assertIn("STOP [workline_implementation_mismatch]", output)
                self.assertEqual(self.value(output, "EXIT"), "1", output)
                self.assertNotIn("API imported", output)


# --------------------------------------------------------------------------- what BL-008 does not change

class CompatibilityTests(unittest.TestCase):
    def test_the_project_bootstrap_is_byte_identical(self) -> None:
        self.assertEqual(hashlib.sha256(render_bootstrap().encode("utf-8")).hexdigest(), BOOTSTRAP_SHA256)

    def test_project_yaml_keeps_its_schema(self) -> None:
        data = yamlish.load(render_project_yaml(Path("workline-root")))
        self.assertEqual(set(data), {"workline", "rules"})
        self.assertEqual(set(data["workline"]), {"root"})
        pinned = yamlish.load(render_project_yaml(Path("workline-root"), PushPin("origin", ("https://example.invalid/r.git",))))
        self.assertEqual(set(pinned), {"workline", "git", "rules"})
        self.assertEqual(
            RULE_REFS,
            {
                "git": "workline://rules/git",
                "ai-decision": "workline://rules/ai-decision",
                "human-confirmation": "workline://rules/human-confirmation",
                "information-tracing": "workline://rules/information-tracing",
            },
        )

    def test_the_recovery_intent_format_is_unchanged(self) -> None:
        self.assertEqual(INTENT_VERSION, 1)

    def test_workline_has_no_runtime_dependencies(self) -> None:
        project = tomllib.loads((WORKLINE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual(project.get("dependencies", []), [])
        self.assertEqual(project["requires-python"], ">=3.11")
        self.assertEqual(implementation.MINIMUM_PYTHON, (3, 11))
        self.assertEqual(runpy.run_path(str(WORKLINE_ROOT / LAUNCHER_NAME))["MINIMUM_PYTHON"], implementation.MINIMUM_PYTHON)


if __name__ == "__main__":
    unittest.main()
