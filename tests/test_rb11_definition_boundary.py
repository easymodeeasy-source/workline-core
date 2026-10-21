"""The finite exceptions of Sprint 41.31 (AM-J): only the listed definitions of the listed files differ from production main.

Tables J1 and J2 of 41.31 name the definitions, per file, that the RB11 amendment units may change; every other definition
and all other module-level text of every ``src`` file stays byte-identical to production main (41d27c00). A definition's
digest is that of its source text; a class is guarded by its header and class-level statements (each method is its own
definition); ``<module>`` is the text outside every definition. A change outside the tables fails this test.
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASE = "41d27c0048f3cfc19e2c9b3ebcf90f005c097b16"

#: file -> the definitions that Table J1 / J2 allow to differ (a new definition counts as a difference too).
ALLOWED = {
    "roadmap.py": {
        "<module>", "_open", "RoadmapPlan", "WorkDependency", "RegisteredRoadmapResult", "entry_order", "with_work_dependencies",
        "_require_phase_entries", "_require_plan_shapes", "_planned_entry_paths", "create_roadmap", "_create_roadmap", "_register_roadmap",
        "_register_phase_expansion", "roadmap_request_identity", "enter_phase", "_enter_registered_phase", "_enter_phase_locked",
        "independent_candidates", "IndependentCandidates", "__all__",
    },
    "mutation.py": {"abandon_new_on_stop", "MutationController.open"},
    "project_policy.py": {"<module>", "change_project_policy", "record_policy_evaluation"},
    "start.py": {"<module>", "_plan_exclude_standalone_locked", "_start_locked"},
    "start_review.py": {"_integration_adjudicate", "_integration_exit_wait", "_p4_human_wait"},
    "review/p4.py": {"normalize_adjudication", "wait_breakdown", "wait_breakdown_text"},
    "state.py": {"ProjectView.unsatisfied_dependencies", "ProjectView.phase_completion"},
    "store.py": {"Entity.roadmap_registration"},
    "create.py": {"<module>", "WorkSpec", "_validate_spec", "_registration_effects"},
    "phase_create.py": {"register_phases"},
}
#: files that exist only in the candidate (Table J2: the whole file).
ADDED_FILES = {"reviewer_access.py"}
#: module-level text that may differ, by file: exactly the named import changes of J1 / J2.
IMPORT_LINES = {
    "roadmap.py": {"    abandon_new_on_stop,"},
    "project_policy.py": {"from .mutation import (", "    Effect, Mutation, MutationController, WriteScope, abandon_new_on_stop, abandon_on_stop, bind_policy_recovery,", ")", "from .mutation import Effect, Mutation, MutationController, WriteScope, abandon_on_stop, bind_policy_recovery"},
    "start.py": {"    abandon_new_on_stop,"},
    "create.py": {"from dataclasses import dataclass, field, replace", "from dataclasses import dataclass, replace"},
}


def _git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, check=True).stdout


def definition_digests(text: str) -> dict[str, str]:
    tree = ast.parse(text)
    lines = text.split("\n")
    digests: dict[str, str] = {}
    covered: set[int] = set()

    def span(node: ast.AST) -> tuple[int, int]:
        start = (node.decorator_list[0].lineno if getattr(node, "decorator_list", None) else node.lineno) - 1
        return start, node.end_lineno

    def walk(body: list[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a, b = span(node)
                digests[prefix + node.name] = hashlib.sha256("\n".join(lines[a:b]).encode()).hexdigest()
                covered.update(range(a, b))
            elif isinstance(node, ast.ClassDef):
                a, b = span(node)
                nested: set[int] = set()
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        c, d = span(child)
                        nested.update(range(c, d))
                own = [lines[i] for i in range(a, b) if i not in nested and lines[i].strip()]
                digests[prefix + node.name] = hashlib.sha256("\n".join(own).encode()).hexdigest()
                covered.update(range(a, b))
                walk(node.body, prefix + node.name + ".")
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and prefix == "":
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        a, b = span(node)
                        digests["__all__"] = hashlib.sha256("\n".join(lines[a:b]).encode()).hexdigest()
                        covered.update(range(a, b))

    walk(tree.body, "")
    rest = [lines[i] for i in range(len(lines)) if i not in covered and lines[i].strip()]
    digests["<module>"] = hashlib.sha256("\n".join(rest).encode()).hexdigest()
    return digests


def module_text_outside_definitions(text: str) -> list[str]:
    tree = ast.parse(text)
    lines = text.split("\n")
    covered: set[int] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) or (
            isinstance(node, (ast.Assign, ast.AnnAssign))
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in (node.targets if isinstance(node, ast.Assign) else [node.target]))
        ):
            start = (node.decorator_list[0].lineno if getattr(node, "decorator_list", None) else node.lineno) - 1
            covered.update(range(start, node.end_lineno))
    return [lines[i] for i in range(len(lines)) if i not in covered and lines[i].strip()]


class DefinitionBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            _git("cat-file", "-e", BASE + "^{commit}")
        except subprocess.CalledProcessError as exc:  # the guard compares with production main: it must be reachable
            raise AssertionError(f"production main {BASE} is not reachable from this checkout") from exc
        cls.base_files = {
            line[len("src/workline/"):]
            for line in _git("ls-tree", "-r", "--name-only", BASE, "--", "src/workline").decode().splitlines()
            if line.endswith(".py")
        }
        cls.now_files = {p.relative_to(REPO / "src" / "workline").as_posix() for p in (REPO / "src" / "workline").rglob("*.py")}

    def test_no_source_file_is_added_or_removed_except_the_listed_ones(self) -> None:
        self.assertEqual(set(), self.base_files - self.now_files, "no source file is removed")
        self.assertEqual(ADDED_FILES, self.now_files - self.base_files)

    def test_every_other_file_is_byte_identical_to_production_main(self) -> None:
        for name in sorted(self.base_files & self.now_files):
            if name in ALLOWED:
                continue
            with self.subTest(file=name):
                base = _git("show", f"{BASE}:src/workline/{name}")
                now = (REPO / "src" / "workline" / name).read_bytes()
                self.assertEqual(hashlib.sha256(base).hexdigest(), hashlib.sha256(now).hexdigest(), name)

    def test_only_the_listed_definitions_of_the_listed_files_differ(self) -> None:
        for name, allowed in sorted(ALLOWED.items()):
            with self.subTest(file=name):
                base = definition_digests(_git("show", f"{BASE}:src/workline/{name}").decode("utf-8").replace("\r\n", "\n"))
                now = definition_digests((REPO / "src" / "workline" / name).read_bytes().decode("utf-8").replace("\r\n", "\n"))
                changed = {k for k in set(base) | set(now) if base.get(k) != now.get(k)}
                self.assertEqual(set(), changed - allowed, f"{name}: definitions changed outside Table J1/J2")

    def test_the_only_module_level_text_that_differs_is_the_named_import_changes(self) -> None:
        for name, lines in sorted(IMPORT_LINES.items()):
            with self.subTest(file=name):
                base = module_text_outside_definitions(_git("show", f"{BASE}:src/workline/{name}").decode("utf-8").replace("\r\n", "\n"))
                now = module_text_outside_definitions((REPO / "src" / "workline" / name).read_bytes().decode("utf-8").replace("\r\n", "\n"))
                added = [line for line in now if line not in base]
                removed = [line for line in base if line not in now]
                self.assertEqual([], [line for line in added + removed if line not in lines], name)
        for name in ("mutation.py", "start_review.py", "review/p4.py", "state.py", "store.py", "phase_create.py"):
            with self.subTest(file=name):
                base = _git("show", f"{BASE}:src/workline/{name}").decode("utf-8").replace("\r\n", "\n")
                now = (REPO / "src" / "workline" / name).read_bytes().decode("utf-8").replace("\r\n", "\n")
                self.assertEqual(module_text_outside_definitions(base), module_text_outside_definitions(now), name)

    def test_the_guard_notices_a_change_outside_the_tables(self) -> None:
        text = (REPO / "src" / "workline" / "start.py").read_bytes().decode("utf-8").replace("\r\n", "\n")
        self.assertNotEqual(definition_digests(text), definition_digests(text + "\n\ndef extra() -> None:\n    pass\n"))
        self.assertNotEqual(definition_digests(text), definition_digests("# changed\n" + text))
        self.assertIn("completion_precheck", definition_digests(text))


if __name__ == "__main__":
    unittest.main()
