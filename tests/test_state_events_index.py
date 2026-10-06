"""RB2-H1 (Control Plane-frozen, §36.22 step 4): ``ProjectView.events_for`` reads one in-memory per-view index.

The index must be invisible: for every entity it returns exactly what the former full scan
``[e for e in view.events if e.entity == entity_id]`` returned - the same Event objects, in the same log order, a
new list per call, ``[]`` for an entity without Events - and it follows the view's Event list when that list is
replaced or grows (``with_effects`` appends to its copy; ``dataclasses.replace`` makes a new view). Over a real
generated Project (the RB2 benchmark generator at test scale), status JSON bytes, validate-project results and every
derived lifecycle state are identical whether ``events_for`` uses the index or the former scan.
"""

from __future__ import annotations

from dataclasses import replace
import unittest
from unittest import mock

from test_rb2_benchmark import FixtureCase
from workline import status
from workline.state import ProjectView
from workline.store import Event, ProjectStore
from workline.validate import validate_project

TYPES = ("work_started", "work_completed", "work_cancelled", "phase_entered", "phase_completed", "roadmap_created")


def scan(view: ProjectView, entity_id: object) -> list[Event]:
    """The former ``events_for``: a full scan of the view's Event list."""
    return [event for event in view.events if event.entity == entity_id]


def synthetic(entities: int = 40, per: int = 7) -> list[Event]:
    """Interleaved Events of many entities and types, in one log order."""
    found = []
    for step in range(per):
        for number in range(entities):
            found.append(Event(f"evt_{step:04d}{number:04d}", TYPES[(step + number) % len(TYPES)], f"ent_{number:03d}",
                               f"2026-01-01T00:{step:02d}:{number % 60:02d}Z"))
    return found


class IndexEqualityTests(unittest.TestCase):
    def view(self, events: list[Event]) -> ProjectView:
        return ProjectView(store=None, events=events)  # type: ignore[arg-type]

    def assertSameAsScan(self, view: ProjectView, entity_id: object) -> None:
        found, expected = view.events_for(entity_id), scan(view, entity_id)  # type: ignore[arg-type]
        self.assertEqual(expected, found)
        self.assertEqual([id(e) for e in expected], [id(e) for e in found], "the same Event objects, same order")

    def test_every_entity_many_types_and_interleaving(self) -> None:
        view = self.view(synthetic())
        for number in range(40):
            with self.subTest(entity=number):
                self.assertSameAsScan(view, f"ent_{number:03d}")
                self.assertEqual(7, len(view.events_for(f"ent_{number:03d}")))

    def test_zero_event_and_empty_log(self) -> None:
        self.assertSameAsScan(self.view(synthetic()), "w_without_events")
        self.assertEqual([], self.view(synthetic()).events_for("w_without_events"))
        self.assertEqual([], self.view([]).events_for("anything"))

    def test_repeated_calls_return_new_equal_lists(self) -> None:
        view = self.view(synthetic())
        first, second = view.events_for("ent_005"), view.events_for("ent_005")
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        first.clear()  # a caller changing its list changes nothing the view holds
        self.assertSameAsScan(view, "ent_005")
        self.assertEqual(7, len(view.events_for("ent_005")))

    def test_the_index_follows_a_replaced_or_grown_event_list(self) -> None:
        view = self.view(synthetic())
        view.events_for("ent_001")  # build the index
        with self.subTest("in-place append"):
            view.events.append(Event("evt_x1", "work_completed", "ent_001", "2026-01-02T00:00:00Z"))
            self.assertSameAsScan(view, "ent_001")
            self.assertEqual("evt_x1", view.events_for("ent_001")[-1].id)
        with self.subTest("a new entity appended"):
            view.events.append(Event("evt_x2", "work_started", "ent_new", "2026-01-02T00:00:01Z"))
            self.assertSameAsScan(view, "ent_new")
        with self.subTest("the list replaced"):
            view.events = [event for event in view.events if event.entity != "ent_001"]
            self.assertEqual([], view.events_for("ent_001"))
            self.assertSameAsScan(view, "ent_002")
        with self.subTest("dataclasses.replace makes an independent view"):
            other = replace(view, events=[Event("evt_y", "work_started", "ent_002", "2026-01-03T00:00:00Z")])
            self.assertEqual(["evt_y"], [e.id for e in other.events_for("ent_002")])
            self.assertSameAsScan(view, "ent_002")

    def test_with_effects_appends_are_seen(self) -> None:
        view = self.view(synthetic())
        view.events_for("ent_003")
        record = {"id": "evt_z", "type": "work_completed", "entity": "ent_003", "at": "2026-01-04T00:00:00Z"}
        projected = view.with_effects([{"kind": "append_event", "payload": {"record": record}}])
        self.assertEqual(scan(projected, "ent_003"), projected.events_for("ent_003"))
        self.assertEqual("evt_z", projected.events_for("ent_003")[-1].id)
        self.assertSameAsScan(view, "ent_003")  # the source view is unchanged
        self.assertNotIn("evt_z", [e.id for e in view.events_for("ent_003")])

    def test_an_argument_no_key_can_equal_compares_exactly_like_the_scan(self) -> None:
        view = self.view(synthetic())
        self.assertEqual([], view.events_for(["ent_001"]))  # type: ignore[arg-type]
        self.assertSameAsScan(view, None)


class GeneratedProjectEquivalenceTests(FixtureCase):
    def test_status_validation_and_derived_states_are_identical_to_the_full_scan(self) -> None:
        target, _ = self.fixture("T")
        root = target / "project"
        store = ProjectStore(root)
        indexed = ProjectView.load(store)
        ids = sorted(indexed.works) + sorted(indexed.phases) + sorted(indexed.roadmaps) + ["w_01ARZ3NDEKTSV4RRFFQ69G5FAV"]
        for entity_id in ids:
            self.assertEqual(scan(indexed, entity_id), indexed.events_for(entity_id), entity_id)
        derived = {
            "work": {w: (indexed.work_state(w), indexed.work_entered_execution(w)) for w in sorted(indexed.works)},
            "phase": {p: indexed.phase_lifecycle(p) for p in sorted(indexed.phases)},
        }
        status_json = status.render_json(status.build_status(root))
        problems = validate_project(store)
        with mock.patch.object(ProjectView, "events_for", scan):
            reference = ProjectView.load(store)
            self.assertEqual(derived, {
                "work": {w: (reference.work_state(w), reference.work_entered_execution(w)) for w in sorted(reference.works)},
                "phase": {p: reference.phase_lifecycle(p) for p in sorted(reference.phases)},
            })
            self.assertEqual(status_json, status.render_json(status.build_status(root)), "status JSON bytes")
            self.assertEqual(problems, validate_project(store))
        self.assertEqual([], problems, "the generated fixture validates")


if __name__ == "__main__":
    unittest.main()
