"""P5 §28.1 / §28.17 / §28.33: the history core is inert, its catalogue is its own, and nothing is wired yet.

* ``review/history.py`` imports and calls nothing that locks, mutates, writes, finalizes or derives lifecycle;
* the P5 catalogue: ``review_p5_*`` names, declared once, disjoint from the P2 and P4 catalogues, raised
  only through :func:`history.stop` / :func:`history.reconcile`; every ``review_p5_*`` literal is declared;
* RB4-CORE scope: no owner builds or writes history, and ``history_problems`` / readiness / the RB5
  projection are called from nowhere (GAP-A / GAP-B / owner integration wait for their rulings);
* the GAP-F seam is one named predicate, and ``history`` is not part of the package's public exports (P-14).
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest

from workline import review as review_package
from workline.errors import ReconcileRequired, StopError
from workline.review import history, p4

SRC = Path(history.__file__).resolve().parents[1]
HISTORY = Path(history.__file__)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _sources() -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in sorted(SRC.rglob("*.py"))}


class InertCoreTests(unittest.TestCase):
    def test_history_imports_nothing_that_locks_mutates_writes_or_finalizes(self) -> None:
        imported: set[str] = set()
        for node in ast.walk(_tree(HISTORY)):
            if isinstance(node, ast.ImportFrom):
                imported.add(("." * node.level) + (node.module or ""))
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        names = {name.rsplit(".", 1)[-1] for name in imported}
        for forbidden in ("mutation", "oplock", "gitops", "gitcmd", "durable", "state", "store", "fsafe", "hermetic",
                          "subprocess", "os", "shutil", "pathlib", "roadmap_review", "start_review", "roadmap",
                          "start", "create", "gate", "validate", "recovery", "publication", "status", "p4"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, names)

    def test_history_calls_no_filesystem_writer(self) -> None:
        calls = {node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                 for node in ast.walk(_tree(HISTORY)) if isinstance(node, ast.Call)}
        for forbidden in ("open", "write_text", "write_bytes", "mkdir", "unlink", "replace", "rename", "rmdir",
                          "create_file", "add_effects", "apply", "reserve_id", "commit"):
            with self.subTest(call=forbidden):
                self.assertNotIn(forbidden, calls)

    def test_history_never_names_the_activation_path(self) -> None:
        self.assertNotIn("WORK_TERMINAL_ACTIVATION_REL", HISTORY.read_text(encoding="utf-8"))


class CatalogueTests(unittest.TestCase):
    def test_p5_names_are_its_own(self) -> None:
        from test_review_planning_fold_ins import CATALOGUE_CODES, CATALOGUE_REASONS

        names = set(history.STOP_CODES) | set(history.RECONCILE_REASONS)
        self.assertEqual(len(names), len(history.STOP_CODES) + len(history.RECONCILE_REASONS))
        self.assertTrue(all(name.startswith("review_p5_") for name in names))
        self.assertEqual(set(), names & (CATALOGUE_CODES | CATALOGUE_REASONS))
        self.assertEqual(set(), names & (set(p4.STOP_CODES) | set(p4.RECONCILE_REASONS)))

    def test_every_review_p5_literal_in_the_implementation_is_declared(self) -> None:
        declared = set(history.STOP_CODES) | set(history.RECONCILE_REASONS)
        found: set[str] = set()
        for path, text in _sources().items():
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                        and re.fullmatch(r"review_p5_[a-z_]+", node.value):
                    found.add(node.value)
                    with self.subTest(module=path.name):
                        self.assertEqual("history.py", path.name, "P5 codes are declared in history.py alone")
        self.assertEqual(declared, found)

    def test_history_spells_no_p4_code(self) -> None:
        for node in ast.walk(_tree(HISTORY)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertIsNone(re.fullmatch(r"review_p4_[a-z_]+", node.value), node.value)

    def test_stop_and_reconcile_build_only_catalogue_names(self) -> None:
        for code in history.STOP_CODES:
            built = history.stop(code, "x")
            self.assertEqual((StopError, code), (type(built), built.code))
        for reason in history.RECONCILE_REASONS:
            built = history.reconcile("x", reason)
            self.assertIsInstance(built, ReconcileRequired)
            self.assertEqual(("reconcile_required", reason), (built.code, built.reason))
        with self.assertRaises(ValueError):
            history.stop(p4.CODE_HUMAN_WAIT, "x")
        with self.assertRaises(ValueError):
            history.reconcile("x", "review_commit_unowned")


class ScopeTests(unittest.TestCase):
    """RB4-OWNER: the owners write history at their transitions; what stays unwired stays unwired.

    * GAP-B: ``history_problems`` (cross-source semantics) is wired into no gating validator, reader or
      operation - only P5 owners' explicit ``require_history_ready`` at P5 boundaries may refuse;
    * GAP-D (a): ``future_work_link`` is called by the direct standalone CREATE alone (explicit
      ``source_finding_id``), and by nothing in Review: P5 never creates or schedules a Work;
    * RB5 owns achievement: nothing calls ``rb5_reference`` or ``confirmed_relations`` yet (§28.21 / §28.22).
    """

    UNWIRED = ("history_problems", "rb5_reference", "confirmed_relations",
               "duplicate_relation_problems", "duplicate_decision_problems")
    #: The modules that may reach the history core: the reader, the structural validator, the inert P4/P5 core,
    #: the two operation owners, the committed planning proof, and CREATE's explicit future-Work provenance (GAP-D).
    REACHING = {"store.py", "validate.py", "p4.py", "roadmap_review.py", "start_review.py", "publication.py",
                "create.py"}

    def test_what_stays_unwired_is_called_from_nowhere(self) -> None:
        for path, text in _sources().items():
            if path == HISTORY:
                continue
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "history":
                    with self.subTest(module=path.name, name=node.attr):
                        self.assertNotIn(node.attr, self.UNWIRED)

    def test_gap_d_future_work_link_is_built_by_the_direct_create_alone(self) -> None:
        callers = set()
        for path, text in _sources().items():
            if path == HISTORY:
                continue
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "history"                         and node.attr == "future_work_link":
                    callers.add(path.name)
        self.assertEqual({"create.py"}, callers)

    def test_only_the_reader_validator_core_owners_and_planning_proof_reach_history(self) -> None:
        reaching = set()
        for path, text in _sources().items():
            if path != HISTORY and re.search(r"\bimport history\b|from \.history import|from \. import .*\bhistory\b"
                                             r"|from \.review import .*\bhistory\b", text):
                reaching.add(path.name)
        self.assertLessEqual(reaching, self.REACHING)
        self.assertLessEqual({"store.py", "validate.py", "p4.py"}, reaching)

    def test_the_gap_f_seam_is_one_named_predicate_used_by_the_builder_and_source_validation_only(self) -> None:
        text = HISTORY.read_text(encoding="utf-8")
        self.assertEqual(2, text.count("DISPOSITIONS_WITHOUT_TRANSITION"), "declared once and read once")
        tree = _tree(HISTORY)
        callers = sorted(
            scope.name for scope in ast.walk(tree) if isinstance(scope, ast.FunctionDef)
            for node in ast.walk(scope)
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "disposition_admitted"
        )
        # GAP-F (a): the reader (RunSummary.from_record) recognizes the vocabulary and never asks the predicate.
        self.assertEqual(["run_summary", "run_summary_problems"], callers)
        for path, source in _sources().items():
            if path != HISTORY:
                with self.subTest(module=path.name):
                    self.assertNotIn("historical_escape", source)

    def test_gap_a_the_p5_identities_are_declared_once_and_dispatched_by_name(self) -> None:
        """The literals live in history.py alone; the family dispatch names them, never spells or infers them."""
        for path, source in _sources().items():
            if path != HISTORY:
                with self.subTest(module=path.name):
                    self.assertNotIn(history.P5_POLICY_ID, source)
                    self.assertNotIn(history.HISTORY_CONTRACT, source)
        self.assertIs(history.P5_POLICY_ID, p4.P5_POLICY_ID)
        self.assertEqual((p4.POLICY_ID, history.P5_POLICY_ID), p4.POLICY_IDS)

    def test_history_is_not_a_public_export_of_the_review_package(self) -> None:
        self.assertNotIn("history", review_package.__all__)


if __name__ == "__main__":
    unittest.main()
