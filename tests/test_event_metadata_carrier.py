"""Non-lifecycle Event metadata survives the whole carrier path (P3 F1 Gate 1 / P3 F3 IP-4).

P3's review-v1 terminal event has to carry Review consistency metadata -
``operation_contract``, ``review_receipt_id``, ``review_run_id``,
``review_generation``. At the landed baseline that metadata reached the physical
event log intact, because an ``append_event`` effect's record is written
verbatim, but the canonical Event model dropped every key it did not know. Effect
classification then compared the reduced record it read back against the record
the effect holds, found them different, and answered ``applied_mismatch`` - after
which the next apply of the same mutation raised ``reconcile_required``. Every
review-v1 terminal event would have poisoned its own mutation.

The carrier now keeps what it is given:

```text
effect record
  -> physical event log
    -> canonical Event reader
      -> Event model and its record form
        -> Mutation effect classification
```

It carries; it does not interpret. Nothing here reads a metadata key, gives one a
meaning or requires one to be present, and state derivation still reads the four
lifecycle fields and only those. An event that carries no metadata is the event it
was before, down to its bytes.

This is Gate 1 alone. Gate 2 (the Consumption ``artifact_kind`` repair) has since landed in its
own ordered unit, and the tests below pin that it did not arrive through this one; Gate 3 (the
activation producer) is not implemented, and they pin that it is still absent.
"""

from __future__ import annotations

import json
import unittest

from helpers import WorklineTestCase
from workline.errors import ValidationError
from workline.mutation import MATCHING, MISMATCH, UNAPPLIED, Effect, MutationController, _text_digest, planned_write
from workline.state import derive_work_state
from workline.store import EVENT_LIFECYCLE_FIELDS, Event, ProjectStore, render_event_line

#: The frozen minimum carrier content for a review-v1 ``work_completed``
#: (P3 F1 §12.1, inherited from P1 R4 §5).
REVIEW_METADATA = {
    "operation_contract": "review-v1",
    "review_receipt_id": "rcp_00000000000000000000000001",
    "review_run_id": "run_00000000000000000000000001",
    "review_generation": 3,
}

LIFECYCLE = {
    "id": "evt_00000000000000000000000001",
    "type": "work_completed",
    "entity": "wrk_00000000000000000000000001",
    "at": "2026-09-27T00:00:00Z",
}


def carrying(**extra: object) -> dict[str, object]:
    """A review-v1 terminal event record: the lifecycle fields, then its metadata."""
    return {**LIFECYCLE, **REVIEW_METADATA, **extra}


class EventModelTests(unittest.TestCase):
    """The model keeps every non-lifecycle key, and identifies itself by the lifecycle ones."""

    def test_from_record_keeps_every_non_lifecycle_key(self) -> None:
        event = Event.from_record(carrying())
        self.assertEqual(dict(event.metadata), REVIEW_METADATA)

    def test_record_round_trips_unchanged(self) -> None:
        record = carrying()
        self.assertEqual(Event.from_record(record).to_record(), record)

    def test_lifecycle_fields_are_read_as_before(self) -> None:
        event = Event.from_record(carrying())
        self.assertEqual(
            (event.id, event.type, event.entity, event.at),
            (LIFECYCLE["id"], LIFECYCLE["type"], LIFECYCLE["entity"], LIFECYCLE["at"]),
        )

    def test_metadata_is_not_writable_through_the_event(self) -> None:
        event = Event.from_record(carrying())
        with self.assertRaises(TypeError):
            event.metadata["operation_contract"] = "forged"  # type: ignore[index]

    def test_mutating_the_source_record_afterwards_changes_nothing(self) -> None:
        record = carrying()
        event = Event.from_record(record)
        record["review_generation"] = 99
        self.assertEqual(event.metadata["review_generation"], 3)

    def test_metadata_may_not_hold_a_lifecycle_field(self) -> None:
        for field in EVENT_LIFECYCLE_FIELDS:
            with self.subTest(field=field):
                with self.assertRaises(ValidationError) as caught:
                    Event("evt_x", "work_completed", "wrk_x", "2026-09-27T00:00:00Z", {field: "forged"})
                self.assertEqual(caught.exception.code, "events_invalid")

    def test_metadata_is_carried_not_interpreted(self) -> None:
        """An unknown key is kept as it is: this layer neither rejects nor understands it."""
        record = carrying(some_future_f4_key={"nested": [1, 2]})
        event = Event.from_record(record)
        self.assertEqual(event.metadata["some_future_f4_key"], {"nested": [1, 2]})
        self.assertEqual(event.to_record(), record)

    def test_contradictory_metadata_is_not_stripped_into_lifecycle_semantics(self) -> None:
        """An unknown operation_contract is carried through, not silently made legacy."""
        record = carrying(operation_contract="review-v99")
        event = Event.from_record(record)
        self.assertEqual(event.metadata["operation_contract"], "review-v99")
        self.assertEqual(event.to_record()["operation_contract"], "review-v99")


class NoMetadataIsUnchangedTests(unittest.TestCase):
    """An event carrying no metadata behaves exactly as it did at the baseline."""

    def setUp(self) -> None:
        self.plain = Event(LIFECYCLE["id"], LIFECYCLE["type"], LIFECYCLE["entity"], LIFECYCLE["at"])

    def test_record_is_the_four_lifecycle_keys_in_order(self) -> None:
        self.assertEqual(list(self.plain.to_record()), list(EVENT_LIFECYCLE_FIELDS))
        self.assertEqual(self.plain.to_record(), LIFECYCLE)

    def test_rendering_is_byte_identical_to_the_baseline_form(self) -> None:
        expected = json.dumps(LIFECYCLE, ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(render_event_line(self.plain), expected)

    def test_hash_is_the_lifecycle_identity(self) -> None:
        self.assertEqual(hash(self.plain), hash((LIFECYCLE["id"], LIFECYCLE["type"], LIFECYCLE["entity"], LIFECYCLE["at"])))

    def test_a_carrying_event_hashes_as_its_lifecycle_identity(self) -> None:
        self.assertEqual(hash(Event.from_record(carrying())), hash(self.plain))

    def test_metadata_still_distinguishes_two_events_by_equality(self) -> None:
        self.assertNotEqual(Event.from_record(carrying()), self.plain)


class CarrierPathTests(WorklineTestCase):
    """The whole path of P3 F1 §12.1, through a real Project's physical log."""

    def setUp(self) -> None:
        super().setUp()
        self.store: ProjectStore = self.new_project()

    def append_line(self, record: dict[str, object]) -> None:
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with self.store.events_jsonl.open("a", encoding="utf-8", newline="") as handle:
            handle.write(line + "\n")

    def test_metadata_survives_the_physical_log(self) -> None:
        record = carrying()
        self.append_line(record)
        read = [event for event in self.store.read_events() if event.id == record["id"]]
        self.assertEqual(len(read), 1)
        self.assertEqual(read[0].to_record(), record)

    def test_a_legacy_line_without_metadata_reads_back_as_before(self) -> None:
        self.append_line(LIFECYCLE)
        read = [event for event in self.store.read_events() if event.id == LIFECYCLE["id"]]
        self.assertEqual(read[0].to_record(), LIFECYCLE)
        self.assertEqual(dict(read[0].metadata), {})

    def test_a_line_missing_a_lifecycle_field_still_fails_closed(self) -> None:
        """The reader's existing refusal is unchanged: metadata does not stand in for a lifecycle field."""
        self.append_line({"id": "evt_x", "type": "work_completed", "entity": "wrk_x", **REVIEW_METADATA})
        with self.assertRaises(ValidationError) as caught:
            self.store.read_events()
        self.assertEqual(caught.exception.code, "events_invalid")

    def test_state_derivation_ignores_metadata_entirely(self) -> None:
        """Lifecycle derivation reads the lifecycle fields and only those."""
        started = {**LIFECYCLE, "id": "evt_00000000000000000000000000", "type": "work_started"}
        plain = [Event.from_record(started), Event.from_record(LIFECYCLE)]
        carried = [Event.from_record(started), Event.from_record(carrying())]
        self.assertEqual(derive_work_state(plain), derive_work_state(carried))

    def test_derivation_is_unchanged_for_every_lifecycle_shape(self) -> None:
        """Adding metadata to any event of a history changes no derived state."""
        history = [
            {**LIFECYCLE, "id": "evt_00000000000000000000000010", "type": "work_started"},
            {**LIFECYCLE, "id": "evt_00000000000000000000000011", "type": "work_completed"},
        ]
        plain = [Event.from_record(record) for record in history]
        carried = [Event.from_record({**record, **REVIEW_METADATA}) for record in history]
        self.assertEqual(derive_work_state(plain), derive_work_state(carried))


class ClassificationTests(WorklineTestCase):
    """The measured defect itself: a carried event classifies as applied, not as a mismatch."""

    def setUp(self) -> None:
        super().setUp()
        self.store: ProjectStore = self.new_project()
        self.controller = MutationController(self.store)

    def record_for(self, event_record: dict[str, object]) -> dict[str, object]:
        return {"kind": "append_event", "payload": {"record": event_record}}

    def append_line(self, record: dict[str, object]) -> None:
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with self.store.events_jsonl.open("a", encoding="utf-8", newline="") as handle:
            handle.write(line + "\n")

    def test_a_carried_event_in_the_log_classifies_matching(self) -> None:
        record = carrying()
        self.append_line(record)
        self.assertEqual(self.controller.classify(self.record_for(record)), MATCHING)

    def test_an_absent_event_is_still_unapplied(self) -> None:
        self.assertEqual(self.controller.classify(self.record_for(carrying())), UNAPPLIED)

    def test_metadata_that_differs_is_still_a_mismatch(self) -> None:
        """Carrying the metadata does not stop classification from comparing it."""
        self.append_line(carrying(review_generation=3))
        self.assertEqual(self.controller.classify(self.record_for(carrying(review_generation=4))), MISMATCH)

    def test_a_log_line_carrying_metadata_the_effect_does_not_is_a_mismatch(self) -> None:
        self.append_line(carrying())
        self.assertEqual(self.controller.classify(self.record_for(dict(LIFECYCLE))), MISMATCH)

    def test_a_plain_event_classifies_exactly_as_before(self) -> None:
        self.append_line(LIFECYCLE)
        self.assertEqual(self.controller.classify(self.record_for(dict(LIFECYCLE))), MATCHING)

    def test_effect_append_event_carries_the_metadata_into_the_effect(self) -> None:
        effect = Effect.append_event(Event.from_record(carrying()))
        self.assertEqual(effect.payload["record"], carrying())


class PhysicalWriteTests(WorklineTestCase):
    """What an append_event effect puts on disk, and what the writer digests of it."""

    def setUp(self) -> None:
        super().setUp()
        self.store: ProjectStore = self.new_project()

    def planned(self, event: Event) -> str:
        effect = Effect.append_event(event)
        written = planned_write(self.store, {"kind": effect.kind, "payload": effect.payload})
        assert written is not None
        return written[1]

    def test_a_no_metadata_event_writes_and_digests_exactly_as_at_baseline(self) -> None:
        """P3 F1 §12.1: an Event carrying no metadata renders, parses, classifies and digests as before."""
        plain = Event(LIFECYCLE["id"], LIFECYCLE["type"], LIFECYCLE["entity"], LIFECYCLE["at"])
        baseline = json.dumps(LIFECYCLE, ensure_ascii=False, separators=(",", ":")) + "\n"
        self.assertEqual(self.planned(plain), baseline)
        self.assertEqual(_text_digest(self.planned(plain)), _text_digest(baseline))

    def test_the_carried_metadata_reaches_the_planned_bytes(self) -> None:
        record = carrying()
        expected = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        self.assertEqual(self.planned(Event.from_record(record)), expected)


class GateBoundaryTests(unittest.TestCase):
    """Gate 1 is a carrier prerequisite. It carries no Gate 2 work, and it does not activate Gate 3."""

    def test_gate_2_did_not_arrive_through_the_carrier(self) -> None:
        """P3 F1 §12.2 / IP-5: Gate 2 is the Consumption record's own repair, not the Event's.

        This pinned Gate 2's absence while Gate 1 was the unit being built. Gate 2 has since landed
        in the ordered unit that owns it, so what still has to hold is the separation: the
        ``artifact_kind`` repair lives on the Consumption record, and nothing about it reached the
        Event carrier, whose metadata stays uninterpreted (F1 §12.1).
        """
        from workline.review import records
        from workline.store import EVENT_LIFECYCLE_FIELDS, Event

        self.assertIn("artifact_kind", records.Consumption.__dataclass_fields__)
        self.assertNotIn("artifact_kind", Event.__dataclass_fields__)
        self.assertEqual(EVENT_LIFECYCLE_FIELDS, ("id", "type", "entity", "at"))
        carried = Event.from_record({**LIFECYCLE, "artifact_kind": "empty"})
        self.assertEqual(dict(carried.metadata), {"artifact_kind": "empty"})

    def test_gate_3_activation_is_not_produced(self) -> None:
        """P3 F1 §12.3 / IP-7: the activation record exists as a type, and nothing writes one."""
        from workline.review import records

        from workline.review.store import ReviewStore

        # P1 already froze the record type and a reader for it. Gate 3 is the PRODUCER, and that is
        # what must still be absent: the store can say whether a Project is activated, and cannot
        # make one activated.
        self.assertTrue(hasattr(records, "WorkTerminalActivation"))
        self.assertTrue(hasattr(ReviewStore, "read_activation"))
        self.assertTrue(hasattr(ReviewStore, "activation_exists"))
        for writer in ("write_activation", "create_activation", "activate", "produce_activation"):
            with self.subTest(writer=writer):
                self.assertFalse(
                    hasattr(ReviewStore, writer), f"ReviewStore.{writer} exists; Gate 3 must stay unproduced"
                )

    def test_the_review_v1_work_persistence_identity_is_not_dispatchable(self) -> None:
        """P3 F3 IP-1: git_commit still accepts the planning mode alone; the Work mode is not live."""
        from workline import mutation

        self.assertEqual(mutation.PLANNING_COMMIT_MODE, "review-v1-planning-local-v1")
        self.assertFalse(hasattr(mutation, "WORK_COMMIT_MODE"))
        with self.assertRaises(ValidationError):
            mutation._validate_planning_commit({"mode": "review-v1-work-local-v2", "paths": [], "message": "m"})


if __name__ == "__main__":
    unittest.main()
