"""The authority boundary: Review authorizes, and never progresses or derives lifecycle."""

from __future__ import annotations

import inspect
from pathlib import Path
import unittest

from helpers import WorklineTestCase, copy_workline_root
from workline import review as review_package
from workline import state as state_module
from workline.registry import REQUIRED_SKILL_IDS, resolve_skill, skill_inventory, validate_registry
from workline.review import ReviewStore, paths, records, serialize
from workline.state import ProjectView
from workline.validate import validate_project

from test_review_authorization import RECEIPT_ID, RUN_ID, receipt_record
from test_review_gate_generation import gate_record

WORKLINE_ROOT = Path(__file__).resolve().parents[1]


class LifecycleIndependenceTests(WorklineTestCase):
    """``state.py`` derives lifecycle from entities, relations and events - and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def _put(self, relative: str, record: dict) -> None:
        target = self.store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialize.canonical_text(record), encoding="utf-8", newline="")

    def test_state_module_does_not_import_review(self) -> None:
        source = inspect.getsource(state_module)
        self.assertNotIn("review", source.lower().replace("reviewed", ""), "state.py must not reach into Review")

    def test_project_view_does_not_read_review_records(self) -> None:
        before = ProjectView.load(self.store)
        self._put(paths.gate_rel(RUN_ID, 1), gate_record(1))
        self._put(paths.receipt_rel(RECEIPT_ID), receipt_record(review_generation=1))
        after = ProjectView.load(self.store)
        self.assertEqual(
            (sorted(before.works), sorted(before.phases), sorted(before.roadmaps),
             len(before.roadmap_relations), len(before.related), len(before.events)),
            (sorted(after.works), sorted(after.phases), sorted(after.roadmaps),
             len(after.roadmap_relations), len(after.related), len(after.events)),
        )

    def test_review_records_do_not_change_work_state(self) -> None:
        roadmap = self.simple_roadmap(self.store)
        entry = self.simple_entry(self.store, next(iter(roadmap.phase_ids.values())))
        work = next(iter(entry.work_ids.values()))
        before = ProjectView.load(self.store).work_state(work)
        self._put(paths.gate_rel(RUN_ID, 1), gate_record(1, target_identity=work))
        self._put(paths.receipt_rel(RECEIPT_ID), receipt_record(review_generation=1, target_identity=work))
        self.assertEqual(before, ProjectView.load(self.store).work_state(work))

    def test_the_review_package_is_not_imported_by_state_or_project_view(self) -> None:
        for module in (state_module,):
            for name, value in vars(module).items():
                self.assertIsNot(value, review_package, f"{module.__name__} holds the Review package as {name}")

    def test_review_store_is_not_an_operation_owner(self) -> None:
        """It reads, validates and renders. It never writes, locks or opens a mutation."""
        source = inspect.getsource(ReviewStore)
        for forbidden in ("durable_write_text", "write_text(", "MutationController", "project_operation", "mkdir"):
            self.assertNotIn(forbidden, source, f"ReviewStore must not {forbidden}")


class RegistryRoutingTests(unittest.TestCase):
    def test_the_canonical_review_skill_is_routed(self) -> None:
        entry = resolve_skill(WORKLINE_ROOT, "skills/review")
        self.assertEqual(".claude/skills/review/SKILL.md", entry.target)
        self.assertEqual("project", entry.context)

    def test_review_is_required_authority(self) -> None:
        self.assertIn("skills/review", REQUIRED_SKILL_IDS)

    def test_registry_validation_passes_with_review_routed(self) -> None:
        result = validate_registry(WORKLINE_ROOT)
        self.assertTrue(result.ok, [f"{p.code}: {p.message}" for p in result.problems])

    def test_the_skill_file_exists_and_declares_its_boundary(self) -> None:
        text = (WORKLINE_ROOT / ".claude" / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: review", text)
        self.assertIn("subordinate", text)
        self.assertIn("NOT ACTIVATED", text)

    def test_review_appears_in_the_skill_inventory(self) -> None:
        self.assertIn("skills/review", skill_inventory(WORKLINE_ROOT))


class BrokenRoutingTests(WorklineTestCase):
    def test_missing_review_routing_is_detected(self) -> None:
        root = copy_workline_root(self.tmp / "no-review")
        registry = (root / "registry.md").read_text(encoding="utf-8")
        registry = registry.replace("<!-- workline-id: skills/review -->", "<!-- workline-id: skills/removed -->")
        (root / "registry.md").write_text(registry, encoding="utf-8")
        result = validate_registry(root)
        self.assertFalse(result.ok)
        self.assertIn("required_skill_missing", [p.code for p in result.problems])

    def test_review_routing_to_a_missing_file_is_detected(self) -> None:
        root = copy_workline_root(self.tmp / "broken-review")
        (root / ".claude" / "skills" / "review" / "SKILL.md").unlink()
        result = validate_registry(root)
        self.assertFalse(result.ok)
        self.assertTrue(
            any("review" in p.message for p in result.problems), [p.message for p in result.problems]
        )


class ActivationBoundaryTests(WorklineTestCase):
    """P1 defines the activation shape and activates nothing."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.review = ReviewStore(self.store)

    def test_p1_leaves_work_terminal_review_unactivated(self) -> None:
        self.assertFalse(self.review.activation_exists())
        self.assertIsNone(self.review.read_activation())

    def test_the_activation_record_shape_is_frozen_and_validated(self) -> None:
        from workline.errors import ValidationError

        good = {
            "schema": records.SCHEMA_ACTIVATION,
            "version": records.VERSION,
            "operation_contract": records.OPERATION_CONTRACT_REVIEW_V1,
            "legacy_event_count": 7,
            "legacy_event_prefix_sha256": "a" * 64,
            "activation_base_head": "b" * 40,
        }
        parsed = records.WorkTerminalActivation.from_record(good, "activation")
        self.assertEqual(good, parsed.to_record())
        with self.assertRaises(ValidationError):
            records.WorkTerminalActivation.from_record({**good, "operation_contract": "legacy"}, "activation")
        with self.assertRaises(ValidationError):
            records.WorkTerminalActivation.from_record({**good, "activation_base_head": "short"}, "activation")

    def test_a_project_with_review_records_but_no_activation_is_valid(self) -> None:
        target = self.store.root / paths.gate_rel(RUN_ID, 1)
        target.parent.mkdir(parents=True)
        target.write_text(serialize.canonical_text(gate_record(1)), encoding="utf-8", newline="")
        self.assertEqual([], [p.code for p in validate_project(self.store)])
        self.assertFalse(self.review.activation_exists())


if __name__ == "__main__":
    unittest.main()
