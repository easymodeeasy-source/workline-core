"""RB5 parallel core: the new modules stay inert and inside their owner boundaries (§14 / §32.1, §32.6, §32.9).

* the pure structural module and generated state load no Review code (checked on sys.modules);
* no new module directly imports anything that locks, mutates, reserves, writes or finalizes, nor the P5 history
  core (``review/integration.py`` and ``achievement.py`` reach it only transitively, through ``review/p4.py``);
* the shared Review dispatch names the Integration kind once - ``records.INTEGRATION_REVIEW_KIND``, registered by the
  shared-surface writer at I-4 - and its terminal stage nowhere; the ``rha`` ID prefix and the version 5 Consumption
  are claimed by the shared modules (I-1), never by the new ones;
* state.py stays free of Review and reaches the structural module only inside ``phase_completion`` (the reviewed
  predicate, post-RB6 integration I-2).
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys
import unittest

from workline import phase_integration as pi
from workline import ids, review as review_package, state
from workline.review import integration as ri, records

SRC = Path(pi.__file__).resolve().parent
NEW_MODULES = ("phase_integration.py", "achievement.py", "review/integration.py", "start_integration_review.py")


def _imported(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return {name.rsplit(".", 1)[-1] for name in names}


def _calls(path: Path) -> set[str]:
    return {node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(node, ast.Call)}


class InertTests(unittest.TestCase):
    def test_new_modules_import_nothing_that_locks_mutates_writes_or_finalizes(self) -> None:
        for name in NEW_MODULES:
            imported = _imported(SRC / name)
            for forbidden in ("mutation", "oplock", "gitops", "gitcmd", "durable", "fsafe", "hermetic", "subprocess",
                              "os", "shutil", "history", "gate", "publication", "roadmap", "roadmap_review",
                              "start_review", "status", "policy"):
                with self.subTest(module=name, forbidden=forbidden):
                    self.assertNotIn(forbidden, imported)

    def test_new_modules_call_no_writer(self) -> None:
        for name in NEW_MODULES:
            calls = _calls(SRC / name)
            for forbidden in ("open", "write_text", "write_bytes", "mkdir", "unlink", "rename", "rmdir", "create_file",
                              "add_effects", "apply", "reserve_id", "commit", "set_note", "extend_scope"):
                with self.subTest(module=name, call=forbidden):
                    self.assertNotIn(forbidden, calls)

    def test_the_structural_module_and_generated_state_load_no_review_code(self) -> None:
        code = ("import sys, workline.phase_integration, workline.state; "
                "print(sorted(m for m in sys.modules if m.startswith('workline.review')))")
        env = {**os.environ, "PYTHONPATH": str(SRC.parent)}
        found = subprocess.run([sys.executable, "-I", "-B", "-c", f"import sys; sys.path.insert(0, {str(SRC.parent)!r}); "
                                + code], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(0, found.returncode, found.stderr)
        self.assertEqual("[]", found.stdout.strip())


class OwnershipTests(unittest.TestCase):
    def test_state_py_reaches_phase_integration_only_inside_phase_completion(self) -> None:
        """Changed at the post-RB6 integration I-2 (row R05, playbook MC-4; was ``test_state_py_is_untouched_this_wave``).

        The bytes check is kept. The import assertion now admits exactly one function-local import of the
        structural module, inside ``ProjectView.phase_completion`` (§32.9) - never at module level, never elsewhere.
        """
        data = Path(state.__file__).read_bytes()
        self.assertNotIn(b"review", data.lower())
        tree = ast.parse(data.decode("utf-8"))
        module_level = {node.module for node in tree.body if isinstance(node, ast.ImportFrom)}
        self.assertNotIn("phase_integration", module_level)
        found = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for inner in ast.walk(node):
                    if isinstance(inner, ast.ImportFrom) and (inner.module or "").endswith("phase_integration") \
                            or isinstance(inner, ast.Import) and any(a.name.endswith("phase_integration")
                                                                     for a in inner.names):
                        found.append((node.name, [alias.name for alias in inner.names]))
        self.assertEqual([("phase_completion", ["completion_reasons"])], found)
        self.assertIn("phase_integration", _imported(Path(state.__file__)))

    def test_the_shared_review_dispatch_names_the_integration_kind_once(self) -> None:
        """Changed with the take of the shared-surface writer's I-4 (playbook §5 I-4 row, R13; PSW INTEGRATION REQUEST
        2; was ``test_nothing_is_registered_into_shared_review_dispatch``): the literal scan admits exactly the one
        ``records.INTEGRATION_REVIEW_KIND`` assignment, which equals ``review.integration.REVIEW_KIND``; the terminal
        stage literal stays out of every shared module, and nothing reaches ``review/__init__``."""
        self.assertNotIn("integration", review_package.__all__)
        self.assertNotIn("integration", _imported(SRC / "review" / "__init__.py"))
        self.assertNotIn("phase-integration-v1", records.PLANNING_REVIEW_KINDS)
        self.assertEqual(ri.REVIEW_KIND, records.INTEGRATION_REVIEW_KIND)
        admitted = {"review/records.py": ['INTEGRATION_REVIEW_KIND = "phase-integration-v1"']}
        for path in sorted(SRC.rglob("*.py")):
            name = path.relative_to(SRC).as_posix()
            if name in NEW_MODULES:
                continue
            with self.subTest(module=name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(admitted.get(name, []),
                                 [line.strip() for line in text.splitlines() if "phase-integration-v1" in line])
                self.assertNotIn("phase-integration:terminal", text)

    def test_the_id_prefix_and_consumption_version_are_claimed_outside_the_new_modules(self) -> None:
        """Changed with the take of the shared-surface writer's I-1 (R01, PSW INTEGRATION REQUEST 1; was
        ``test_no_id_prefix_and_no_consumption_version_is_claimed``): ``ids.py`` holds ``rha``; the module-text checks
        on the four new modules are kept."""
        self.assertEqual("rha", ids.PREFIXES["review_achievement"])
        for name in NEW_MODULES:
            text = (SRC / name).read_text(encoding="utf-8")
            with self.subTest(module=name):
                self.assertNotIn("PREFIXES", text)
                self.assertNotIn("CONSUMPTION_VERSION", text)
                self.assertNotIn("new_id(", text)

    def test_no_marker_accessor_outside_the_owners(self) -> None:
        """The marker is read only through the frozen ``Entity.phase_review_contract`` interface - never from meta.

        On the AST (RB5B-L11): no ``<x>.meta[...]`` subscript and no ``<x>.meta.get(...)`` call whose key is the
        marker key (as the literal or as ``PHASE_REVIEW_CONTRACT_KEY``), and no ``getattr`` fallback.
        """
        def is_marker_key(node: ast.AST) -> bool:
            return (isinstance(node, ast.Constant) and node.value == pi.PHASE_REVIEW_CONTRACT_KEY) or                 (isinstance(node, (ast.Name, ast.Attribute))
                 and getattr(node, "id", getattr(node, "attr", None)) == "PHASE_REVIEW_CONTRACT_KEY")

        def on_meta(node: ast.AST) -> bool:
            return isinstance(node, ast.Attribute) and node.attr == "meta"

        found = []
        for name in NEW_MODULES:
            for node in ast.walk(ast.parse((SRC / name).read_text(encoding="utf-8"))):
                if isinstance(node, ast.Subscript) and on_meta(node.value) and is_marker_key(node.slice):
                    found.append((name, node.lineno, "meta[...]"))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get"                         and on_meta(node.func.value) and node.args and is_marker_key(node.args[0]):
                    found.append((name, node.lineno, "meta.get(...)"))
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "getattr":
                    found.append((name, node.lineno, "getattr"))
        self.assertEqual([], found)


if __name__ == "__main__":
    unittest.main()
