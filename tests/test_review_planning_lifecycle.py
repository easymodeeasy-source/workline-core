"""P2 §28 H: lifecycle separation - Review metadata never alters lifecycle, and P3 stays inactive."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from helpers import completing_executor, git
from planning_helpers import Crash, PlanningTestCase, Reviewer, crash_at, design, plan, rr, run_ids
from workline import roadmap as rm
from workline import start as st
from workline import state
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.review import paths as review_paths
from workline.review.store import ReviewStore
from workline.state import ProjectView
from workline.validate import validate_structure

#: SHA-256 of ``src/workline/state.py`` at the implementation baseline de3681c (LF line ends).
STATE_PY_BASELINE_SHA256 = "6f86107ceee1536b55ff0c85b2f1bd3fca17ee0b83e4ef38885d184be1d0e6da"
EVENT_LOG = ".workline/events/events.jsonl"


def lifecycle_facts(view: ProjectView) -> dict:
    """Everything lifecycle and progression derive, keyed by display so two Projects built alike compare equal."""
    display = {entity.id: entity.display for kind in (view.roadmaps, view.phases, view.works) for entity in kind.values()}
    return {
        "roadmaps": {r.display: (r.name, view.roadmap_lifecycle(r.id)) for r in view.roadmaps.values()},
        "phases": {p.display: (p.name, view.phase_state(p.id), view.phase_lifecycle(p.id)) for p in view.phases.values()},
        "works": {w.display: (w.name, w.work_kind, view.work_state(w.id).state) for w in view.works.values()},
        "startable": {p.display: [display[w.id] for w in view.startable_works(p.id)] for p in view.phases.values()},
        "relations": sorted((r.type, display.get(r.from_id), display.get(r.to)) for r in view.roadmap_relations),
        "related": sorted((r.type, display.get(r.from_id), r.to) for r in view.related),
        "events": [(e.type, display.get(e.entity)) for e in view.events],
    }


class EndStateTests(PlanningTestCase):
    def test_gated_and_legacy_end_states_are_equal(self) -> None:
        legacy = self.planning_project("legacy")
        created = rm.create_roadmap(legacy, plan())
        rm.enter_phase(legacy, created.phase_ids["a"], design())
        legacy_facts = lifecycle_facts(ProjectView.load(legacy))
        gated = self.planning_project("gated")
        result = self.reviewed_roadmap(gated)
        self.reviewed_entry(gated, result.registration.phase_ids["a"])
        self.assertEqual(legacy_facts, lifecycle_facts(ProjectView.load(gated)))
        self.assertEqual(
            (legacy.root / EVENT_LOG).read_bytes() if (legacy.root / EVENT_LOG).exists() else b"",
            (gated.root / EVENT_LOG).read_bytes() if (gated.root / EVENT_LOG).exists() else b"",
            "a review-v1 Roadmap creation or Phase entry writes no event",
        )

    def test_generation_4_and_the_supersession_change_no_lifecycle_fact(self) -> None:
        store = self.planning_project()
        before = lifecycle_facts(ProjectView.load(store))
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store)
        real = rr.planning._read_authority
        from unittest import mock

        with mock.patch.object(rr.planning, "_read_authority",
                               lambda path: real(path) + (b"\nchanged\n" if str(path).endswith("registry.md") else b"")):
            result = self.reviewed_roadmap(store)
        self.assertEqual("stale", result.status)
        self.assertTrue(ReviewStore(store).supersession_exists(result.receipt_id))
        self.assertEqual(before, lifecycle_facts(ProjectView.load(store)))


class TamperedRecordTests(PlanningTestCase):
    def test_a_tampered_record_stops_only_the_gated_operation_relying_on_it(self) -> None:
        store = self.planning_project()
        other = rm.create_roadmap(store, plan("Other Roadmap")).roadmap_id
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store)
        before = lifecycle_facts(ProjectView.load(store))
        (run_id,) = run_ids(store)
        receipt = store.root / review_paths.receipt_rel(self.chain(store, run_id).latest.receipt_id)
        receipt.write_bytes(receipt.read_bytes().replace(b"\n", b"\r\n"))  # no longer canonical
        self.assertEqual(before, lifecycle_facts(ProjectView.load(store)), "lifecycle is not reinterpreted")
        self.assertEqual([], validate_structure(ProjectView.load(store)))
        rm.hold_roadmap(store, other)  # an operation that relies on no Review record proceeds
        with self.assertRaises((ReconcileRequired, StopError, ValidationError)) as raised:
            self.reviewed_roadmap(store)  # the gated operation relying on the record stops
        self.assertEqual(("ReconcileRequired", "review_receipt_invalid"),
                         (type(raised.exception).__name__, getattr(raised.exception, "reason", None)))


class StatePyTests(unittest.TestCase):
    def test_state_py_is_byte_identical_to_the_baseline(self) -> None:
        data = Path(state.__file__).read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(STATE_PY_BASELINE_SHA256, hashlib.sha256(data).hexdigest())
        self.assertNotIn(b"review", data.lower())


class P3InactiveTests(PlanningTestCase):
    def _completed_first_work(self, store, *, reviewed: bool):
        if reviewed:
            result = self.reviewed_roadmap(store)
            entry = self.reviewed_entry(store, result.registration.phase_ids["a"]).registration
        else:
            created = rm.create_roadmap(store, plan())
            entry = rm.enter_phase(store, created.phase_ids["a"], design())
        started = st.start(store, entry.work_ids["w1"], "single-work", completing_executor(store))
        view = ProjectView.load(store)
        events = [e.type for e in view.events_for(entry.work_ids["w1"])]
        subjects = git(store.root, "log", "-2", "--format=%s").splitlines()
        return started.status, events, subjects

    def test_start_completion_is_unchanged_and_nothing_activates_p3(self) -> None:
        legacy = self._completed_first_work(self.planning_project("legacy"), reviewed=False)
        gated_store = self.planning_project("gated")
        gated = self._completed_first_work(gated_store, reviewed=True)
        self.assertEqual(legacy, gated)
        review = ReviewStore(gated_store)
        self.assertIsNone(review.read_activation())
        self.assertFalse((gated_store.root / review_paths.WORK_TERMINAL_ACTIVATION_REL).exists())
        self.assertEqual(2, len(review.consumption_ids()), "the two planning Consumptions only: no Work-terminal one")


class NoCrossOperationPreconditionTests(PlanningTestCase):
    def test_a_legacy_phase_entry_on_a_review_v1_roadmap_proceeds(self) -> None:
        store = self.planning_project()
        result = self.reviewed_roadmap(store)
        entry = rm.enter_phase(store, result.registration.phase_ids["a"], design())
        self.assertTrue(entry.work_ids)

    def test_a_review_v1_phase_entry_on_a_legacy_roadmap_proceeds(self) -> None:
        store = self.planning_project()
        created = rm.create_roadmap(store, plan())
        result = self.reviewed_entry(store, created.phase_ids["a"])
        self.assertEqual("registered", result.status)


class HeldBackOperationTests(PlanningTestCase):
    def test_a_legacy_operation_held_back_by_the_barrier_applied_exactly_its_usual_effects(self) -> None:
        store = self.planning_project(remote=True)
        other = rm.create_roadmap(store, plan("Other Roadmap")).roadmap_id
        with crash_at(rr, "_c2_kp"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store)
        committed_log = git(store.root, "show", f"HEAD:{EVENT_LOG}", check=False)
        with self.assertRaises(StopError) as raised:
            rm.hold_roadmap(store, other)
        self.assertEqual("review_publication_barrier", raised.exception.code)
        changed = [line[3:] for line in git(store.root, "status", "--porcelain", "--untracked-files=all").splitlines()
                   if not line[3:].startswith(".workline/runtime/")]
        self.assertEqual([EVENT_LOG], changed, "its only effect is its event")
        applied = (store.root / EVENT_LOG).read_text(encoding="utf-8")
        self.assertTrue(applied.startswith(committed_log))
        (line,) = applied[len(committed_log):].splitlines()
        self.assertIn('"roadmap_held"', line)
        self.assertIn(other, line)
        self.assertEqual("held", ProjectView.load(store).roadmap_lifecycle(other))
        self.reviewed_roadmap(store)  # the planning retry proves Kp and publishes Km
        held = rm.hold_roadmap(store, other)  # only its commit and push waited
        self.assertEqual([EVENT_LOG], git(store.root, "show", "--name-only", "--format=", held.head).split())
        self.assertEqual(applied, git(store.root, "show", f"{held.head}:{EVENT_LOG}"))
        self.assertEqual(held.head, self.remote_head())


if __name__ == "__main__":
    unittest.main()
