"""RB1 §29.25: ``status`` reads and never writes - checked mechanically, not by prose.

Every scenario runs inside :class:`status_helpers.ReadOnlyBoundary`: the
callables that open a mutation, take the execution lock, write durably, commit,
push or reach a remote fail if they are reached; every process launched must be
a read-only local ``git``; and the whole Project tree, ``.git`` included, must
hold the same bytes afterwards. The status code itself is also read as source:
nothing in it names a write.
"""

from __future__ import annotations

import ast
import contextlib
import inspect
import io
import json
import os
from pathlib import Path
import textwrap
import time
import unittest

from helpers import git
from status_helpers import ReadOnlyBoundary, StatusCase, append_events
from workline import cli, mutation, selection, status
from workline.mutation import MutationController, WriteScope
from workline.oplock import project_operation
from workline.review import status as review_status

from test_work_terminal_activation import ActivationCase

LEDGERS = (".workline/events/events.jsonl", ".workline/relations/roadmap.yaml", ".workline/relations/related.yaml")


class ReadOnlyScenarios(StatusCase):
    def run_status(self, root: Path) -> dict:
        """Build, render both ways, and run the CLI in this process - all inside the boundary."""

        def call():
            model = status.build_status(root)
            text = status.render_json(model)
            status.render_human(model)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = cli.main(["status", str(root), "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(output.getvalue(), text)
            return json.loads(text)

        data, boundary = self.assertReadOnly(call, root)
        subcommands = boundary.git_subcommands()
        self.assertTrue(subcommands, "status reads local Git")
        self.assertNotIn("fetch", subcommands)
        return data

    def test_a_valid_project_is_read_without_a_single_write(self) -> None:
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        self.simple_entry(store, roadmap.phase_ids["a"], {"w1": "W1 done", "w2": "W2 done"})
        locks_existed = store.locks.exists()

        data = self.run_status(store.root)

        self.assertEqual(data["validation"]["status"], "pass")
        self.assertEqual(data["snapshot_consistency"], "stable_read")
        self.assertEqual(store.locks.exists(), locks_existed, "no lock directory appears")
        self.assertFalse(store.lock_holder.exists(), "no holder description appears")

    def test_an_invalid_project_is_read_without_a_single_write(self) -> None:
        store = self.new_project()
        store.related_yaml.write_text("relations: [not a list\n", encoding="utf-8")

        data = self.run_status(store.root)

        self.assertEqual(data["validation"]["status"], "failed")
        self.assertEqual(data["lifecycle"]["status"], "unavailable")

    def test_a_project_with_pending_and_unreadable_records_is_read_without_a_single_write(self) -> None:
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        entry = self.simple_entry(store, roadmap.phase_ids["a"])
        work = entry.work_ids["w1"]
        with project_operation(store, "start", {}):
            MutationController(store).open(
                "start", {"operation": "start", "work_id": work, "mode": "single-work"},
                WriteScope(entities=(work,), files=LEDGERS),
            )
        (store.mutations / "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV.yaml").write_bytes(b"\xff\xfe not yaml")
        (store.mutations / "stray.yaml").write_text("x: 1\n", encoding="utf-8")

        data = self.run_status(store.root)

        self.assertEqual(data["pending"]["status"], "present")
        self.assertEqual(len(data["pending"]["records"]), 3)

    def test_a_stale_holder_description_is_a_hint_and_never_an_active_lock(self) -> None:
        store = self.new_project()
        store.locks.mkdir(parents=True, exist_ok=True)
        store.lock_holder.write_text(
            json.dumps({"workline": "workline-operation-holder", "version": 1, "operation": "start", "pid": 999999,
                        "host": "elsewhere", "acquired_at": "2026-01-01T00:00:00+00:00", "mutation_id": None}),
            encoding="utf-8",
        )

        data = self.run_status(store.root)

        lock = data["pending"]["lock"]
        self.assertEqual((lock["state"], lock["holder_hint"], lock["holder_operation"]), ("not_checked", "present", "start"))
        self.assertNotIn("999999", json.dumps(data))
        self.assertNotIn("elsewhere", json.dumps(data))

    def test_a_stat_dirty_index_is_never_refreshed(self) -> None:
        """``git status`` writes the index back when it can; status runs Git with its optional locks off."""
        store = self.new_project()
        tracked = store.project_yaml
        later = time.time() + 120
        os.utime(tracked, (later, later))
        index = store.root / ".git" / "index"
        before = index.read_bytes()

        self.run_status(store.root)

        self.assertEqual(index.read_bytes(), before, "status refreshed the index")
        git(store.root, "status", "--porcelain")
        self.assertNotEqual(index.read_bytes(), before, "the fixture tempts an index refresh (discriminating)")


class ReviewEnabledReadOnlyTests(ActivationCase):
    def test_a_review_activated_project_is_read_without_a_single_write(self) -> None:
        self.with_works()
        self.activate()
        with ReadOnlyBoundary(self.root) as boundary:
            model = status.build_status(self.root)
            status.render_human(model)
            data = json.loads(status.render_json(model))
        self.assertEqual(boundary.violations, [])
        self.assertEqual(boundary.paths_written, [])
        self.assertEqual(boundary.changed(), {})
        self.assertEqual(data["review"]["activation"]["status"], "present")


class StaticCallGraphTests(unittest.TestCase):
    """The status code names no write, lock, mutation, commit, push or remote read."""

    FORBIDDEN_ATTRIBUTES = frozenset({
        "open", "begin", "reserve_id", "add_effects", "apply", "complete", "abandon", "set_note",
        "extend_scope", "_save", "apply_effect", "project_operation", "note_mutation", "durable_write_text",
        "write_text", "write_bytes", "mkdir", "makedirs", "unlink", "rmdir", "rename", "touch", "symlink_to",
        "remove", "rmtree", "add_paths", "commit_only", "push", "push_dry_run", "fetch_destination_branch",
        "destination_branch", "reads_itself", "init_main", "contained_add", "contained_commit", "enter",
        "pin_push_destination", "backfill_bootstrap", "activate_work_terminal_review", "chdir",
    })
    FORBIDDEN_NAMES = frozenset({
        "project_operation", "durable_write_text", "pin_push_destination", "backfill_bootstrap",
        "activate_work_terminal_review", "chdir", "MutationController",
    })

    def check(self, source: str, where: str, *, allowed_names: frozenset[str] = frozenset()) -> None:
        tree = ast.parse(textwrap.dedent(source))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                with self.subTest(where=where, call=func.attr, line=node.lineno):
                    self.assertNotIn(func.attr, self.FORBIDDEN_ATTRIBUTES)
                    if func.attr == "load":  # a parser or a snapshot reader; never MutationController.load
                        self.assertTrue(isinstance(func.value, ast.Name) and func.value.id in ("yamlish", "ProjectView", "json"))
            elif isinstance(func, ast.Name):
                if func.id in allowed_names:
                    continue
                with self.subTest(where=where, call=func.id, line=node.lineno):
                    self.assertNotIn(func.id, self.FORBIDDEN_NAMES)
                    if func.id == "open":
                        mode = node.args[1] if len(node.args) > 1 else None
                        self.assertTrue(isinstance(mode, ast.Constant) and mode.value == "rb", "open() only to read bytes")

    def test_the_status_modules_name_no_write(self) -> None:
        for module in (status, review_status, selection):
            self.check(inspect.getsource(module), module.__name__)

    def test_the_tolerant_mutation_readers_name_no_write(self) -> None:
        for function in (mutation.inspect_records, mutation._inspect_record, mutation.replay_probe,
                         mutation._replay_probe, mutation._replay_key):
            self.check(inspect.getsource(function), function.__name__, allowed_names=frozenset({"MutationController"}))
        # The inspected record exposes what the replay predicates read, and nothing a write goes through.
        names = {name for name in vars(mutation._InspectedRecord) if not name.startswith("__")}
        self.assertEqual(names, {"store", "controller", "record", "id", "effects", "note"})
        self.assertFalse(hasattr(mutation._InspectedRecord, "_save"))
        self.assertFalse(hasattr(mutation._InspectedRecord, "_writable"))

    def test_status_never_resolves_the_caller_context(self) -> None:
        source = inspect.getsource(status)
        for needle in ("resolve_invocation_context", "getcwd", "Path.cwd", "authorize_project_mutation"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, source)


if __name__ == "__main__":
    unittest.main()
