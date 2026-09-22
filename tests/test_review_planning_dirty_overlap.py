"""P2 §28 I: dirty overlap - a person's change to a planning-owned path is refused before any Review record."""

from __future__ import annotations

import contextlib
import unittest
from unittest import mock

from helpers import git
from planning_helpers import Crash, PlanningTestCase, Reviewer, crash_at, deterministic_ids, plan, rr, run_ids, state_entries
from workline import roadmap as rm
from workline.errors import StopError
from workline.review import checkout, gate, planning, records, serialize
from workline.review import paths as review_paths
from workline.store import ProjectStore

ROADMAP_YAML = ".workline/relations/roadmap.yaml"
PERSONS_BYTES = b"a person's change\n"


def rr_discovery_none():
    """Discovery finding no matching Run (a fixture that takes the namespace-readability step out of the way)."""
    from workline.review import recovery

    return recovery.Discovery(None, ())


class _FreezeCase(PlanningTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()
        self.reviewer = Reviewer()

    def run_plan(self):
        return self.reviewed_roadmap(self.store, self.reviewer)

    def crash_before_step_5(self) -> dict:
        """The freeze interrupted after every reservation (steps 1-4) and before step 5; the pending record."""
        with crash_at(gate, "require_committable", when=lambda n, store, relatives: len(relatives) > 3):
            with self.assertRaises(Crash):
                self.run_plan()
        (record,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-create"]
        return record

    def reserved_paths(self, record: dict) -> dict[str, str]:
        reserved = record["reserved_ids"]
        roadmap_id = reserved["roadmap"]
        run_id = reserved[gate.review_run_key(planning.KIND_ROADMAP, roadmap_id)]
        receipt_id = reserved[gate.review_receipt_key(run_id, planning.SEAL_GENERATION)]
        consumption_id = reserved[gate.review_consumption_key(receipt_id)]
        return {
            "run_id": run_id, "receipt_id": receipt_id, "consumption_id": consumption_id,
            "gate_4": review_paths.gate_rel(run_id, 4),
            "supersession": review_paths.supersession_rel(receipt_id),
            "consumption": review_paths.consumption_rel(consumption_id),
        }

    def assert_refused_before_anything(self, code: str, dirty: str, persons: bytes, mutation_id: str) -> None:
        with self.assertRaises(StopError) as raised:
            self.run_plan()
        self.assertEqual(code, raised.exception.code)
        self.assertEqual([], self.reviewer.tasks, "no reviewer launch")
        self.assertEqual((), run_ids(self.store), "no Review record")
        self.assertEqual([], [r for r in self.pending(self.store) if r["mutation_id"] == mutation_id], "abandoned")
        self.assertEqual(persons, (self.store.root / dirty).read_bytes(), "the person's bytes are untouched")


class FreezeTests(_FreezeCase):
    """A person's change present before the call: the freeze refuses it before any Review record or reviewer launch.

    Run record and Consumption paths exist only once their IDs are reserved, so a deterministic ID source predicts
    them: a scratch Project built alike reserves the same IDs.
    """

    def predicted(self) -> dict[str, str]:
        with deterministic_ids():
            scratch = self.planning_project("scratch")
            with crash_at(gate, "require_committable", when=lambda n, store, relatives: len(relatives) > 3):
                with self.assertRaises(Crash):
                    self.reviewed_roadmap(scratch)
            (record,) = [r for r in self.pending(scratch) if r["invocation"].get("operation") == "roadmap-create"]
        return self.reserved_paths(record)

    def refused_before_anything(self, relative: str, persons: bytes, code: str = "dirty_overlap", *, patches=()) -> None:
        self.projects = getattr(self, "projects", 0) + 1
        with deterministic_ids():
            store = self.planning_project(f"proj{self.projects + 1}")
            target = store.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(persons)
            before = {k: v for k, v in state_entries(store).items() if "/runtime/" not in k}
            reviewer = Reviewer()
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                with self.assertRaises(StopError) as raised:
                    self.reviewed_roadmap(store, reviewer)
        self.assertEqual(code, raised.exception.code)
        self.assertEqual([], reviewer.tasks, "no reviewer launch")
        after = {k: v for k, v in state_entries(store).items() if "/runtime/" not in k}
        self.assertEqual(before, after, "no Review record and no domain file: the person's bytes exactly as they were")
        self.assertEqual([], [r for r in self.pending(store) if r["invocation"].get("operation") == "roadmap-create"],
                         "the planning mutation is abandoned")

    def test_a_dirty_registration_path(self) -> None:
        persons = (self.store.root / ROADMAP_YAML).read_bytes() + b"\n"
        self.refused_before_anything(ROADMAP_YAML, persons)

    def test_a_dirty_supersession_path(self) -> None:
        found = self.predicted()
        persons = serialize.canonical_bytes(
            records.Supersession(found["receipt_id"], found["run_id"], 4, "a person's record").to_record())
        self.refused_before_anything(found["supersession"], persons)

    def test_a_dirty_consumption_path(self) -> None:
        found = self.predicted()
        consumption = records.Consumption(
            found["consumption_id"], "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV", "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV", 3, "custom-kind",
            "a" * 64, "custom-op", "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV", None, None, "a-target", None,
        )
        self.refused_before_anything(found["consumption"], serialize.canonical_bytes(consumption.to_record()))

    def test_a_dirty_gate_4_path(self) -> None:
        found = self.predicted()
        # a file there makes the Review namespace unreadable, which discovery checks first (§12.2 step 1)
        self.refused_before_anything(found["gate_4"], PERSONS_BYTES, "review_namespace_unreadable")
        # with that earlier check out of the way, the freeze's dirty overlap refuses the gate-4 path itself
        self.refused_before_anything(found["gate_4"], PERSONS_BYTES, patches=(
            mock.patch.object(checkout, "require_namespace_readable", lambda store: None),
            mock.patch.object(rr, "_discover", lambda op: rr_discovery_none()),
        ))

    def test_every_run_record_path_and_the_consumption_path_are_planning_owned(self) -> None:
        record = self.crash_before_step_5()
        found = self.reserved_paths(record)
        seen: list[list[str]] = []
        real = rr.gitops.ensure_separable_before_effects

        def watch(mutation, paths):
            seen.append(sorted(paths))
            return real(mutation, paths)

        with mock.patch.object(rr.gitops, "ensure_separable_before_effects", watch):
            with crash_at(rr, "_note_binding"):
                with self.assertRaises(Crash):
                    self.run_plan()
        (paths,) = seen
        for key in ("gate_4", "supersession", "consumption"):
            self.assertIn(found[key], paths)
        for number in (1, 2, 3):
            self.assertIn(review_paths.gate_rel(found["run_id"], number), paths)
        self.assertIn(review_paths.receipt_rel(found["receipt_id"]), paths)
        self.assertIn(ProjectStore.entity_rel_path("roadmap", record["reserved_ids"]["roadmap"]), paths)
        self.assertIn(ROADMAP_YAML, paths)


class AfterTheFreezeTests(_FreezeCase):
    def test_a_registration_path_changed_after_the_freeze_stops_the_use_check_and_stays_pending(self) -> None:
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.run_plan()
        (record,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-create"]
        persons = (self.store.root / ROADMAP_YAML).read_bytes() + b"\n"
        (self.store.root / ROADMAP_YAML).write_bytes(persons)
        with self.assertRaises(StopError) as raised:
            self.run_plan()
        self.assertEqual("dirty_overlap", raised.exception.code)
        (still,) = [r for r in self.pending(self.store) if r["mutation_id"] == record["mutation_id"]]
        self.assertEqual("pending", still["status"], "never abandoned after generation 1")
        self.assertEqual([], still["effects"], "nothing written")
        self.assertEqual(persons, (self.store.root / ROADMAP_YAML).read_bytes())
        git(self.store.root, "checkout", "--", ROADMAP_YAML)
        self.assertEqual("registered", self.run_plan().status)

    def test_a_resume_after_generation_1_never_abandons(self) -> None:
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.run_plan()
        (self.store.root / ROADMAP_YAML).write_bytes((self.store.root / ROADMAP_YAML).read_bytes() + b"\n")
        with self.assertRaises(StopError) as raised:
            self.run_plan()
        self.assertEqual("dirty_overlap", raised.exception.code)
        self.assertEqual(1, len([r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-create"]))


class LegacyTests(PlanningTestCase):
    def test_the_legacy_late_dirty_overlap_is_unchanged(self) -> None:
        """The baseline outcome (measured on de3681c): effects applied, the Git stage refused, the mutation pending."""
        store = self.planning_project()
        persons = (store.root / ROADMAP_YAML).read_bytes() + b"\n"
        (store.root / ROADMAP_YAML).write_bytes(persons)
        with self.assertRaises(StopError) as raised:
            rm.create_roadmap(store, plan())
        self.assertEqual("dirty_overlap", raised.exception.code)
        self.assertTrue(str(raised.exception).startswith(
            "pre-existing changes overlap operation-owned paths and cannot be separated safely"))
        (record,) = self.pending(store)
        self.assertNotIn("review_contract", record["invocation"])
        self.assertEqual(
            [("roadmap", "write_file", True), ("phases", "write_file", True), ("phases", "write_file", True),
             ("phases", "add_relation", True)],
            [(e["stage"], e["kind"], e["applied"]) for e in record["effects"]],
            "its domain effects applied and its Git stage never recorded, exactly as at the baseline",
        )
        self.assertEqual("attributes", self.subjects(store)[0], "nothing committed")


if __name__ == "__main__":
    unittest.main()
