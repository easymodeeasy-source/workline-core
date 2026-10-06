"""RB1 §29.30: the Review section reports what the canonical Review records show, and nothing they do not.

States are derived only where the validated chain shows them; an unreadable
chain or record is ``invalid`` with its exact reason, never absent; no raw
reviewer output appears; and Review status never changes lifecycle status.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from status_helpers import StatusCase
from workline import status
from workline.review import paths, records, serialize
from workline.review import status as review_status

from test_review_authorization import CONSUMPTION_ID, RECEIPT_ID, RUN_ID, consumption_record, receipt_record
from test_review_gate_generation import gate_record
from test_work_terminal_activation import ActivationCase

RAW_DIGEST = "f" * 64  # the fixture's raw_report_set_digest


class ReviewRunTests(StatusCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def put(self, relative: str, record: dict) -> None:
        target = self.store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(serialize.canonical_bytes(record))

    def run_entry(self) -> dict:
        review = self.data()["review"]
        self.assertEqual(review["status"], "available")
        entries = review["runs"]["entries"]
        self.assertEqual(len(entries), 1, entries)
        return entries[0]

    def open_run(self) -> dict:
        first = gate_record(1)
        self.put(paths.gate_rel(RUN_ID, 1), first)
        return first

    def sealed_run(self) -> dict:
        first = self.open_run()
        second = gate_record(2, previous_digest=serialize.digest(first), status=records.GATE_STATUS_SEALED,
                             receipt_id=RECEIPT_ID)
        self.put(paths.gate_rel(RUN_ID, 2), second)
        self.put(paths.receipt_rel(RECEIPT_ID), receipt_record(review_generation=2))
        return second

    def test_the_review_namespace_absent(self) -> None:
        review = self.data()["review"]
        self.assertEqual(review["namespace"], {"status": "absent", "reason": None})
        self.assertEqual(review["runs"]["entries"], [])
        self.assertEqual(review["activation"]["status"], "absent")

    def test_an_open_run(self) -> None:
        self.open_run()
        entry = self.run_entry()
        self.assertEqual(
            (entry["review_run_id"], entry["review_kind"], entry["target_identity"], entry["latest_generation"],
             entry["state"], entry["receipt"]["status"], entry["consumption"]["status"]),
            (RUN_ID, "work_formal", "w_01ARZ3NDEKTSV4RRFFQ69G5FAV", 1, "open", "none", "none"),
        )

    def test_a_sealed_run(self) -> None:
        self.sealed_run()
        entry = self.run_entry()
        self.assertEqual((entry["state"], entry["latest_generation"]), ("sealed", 2))
        self.assertEqual(entry["receipt"], {"status": "issued", "receipt_id": RECEIPT_ID, "reason": None})

    def test_a_consumed_run(self) -> None:
        self.sealed_run()
        self.put(paths.consumption_rel(CONSUMPTION_ID), consumption_record(review_generation=2))
        entry = self.run_entry()
        self.assertEqual(entry["state"], "consumed")
        self.assertEqual(entry["consumption"], {"status": "consumed", "consumption_id": CONSUMPTION_ID, "reason": None})

    def test_a_superseded_run_is_invalidated(self) -> None:
        second = self.sealed_run()
        self.put(paths.gate_rel(RUN_ID, 3), gate_record(3, previous_digest=serialize.digest(second)))
        self.put(paths.supersession_rel(RECEIPT_ID), {
            "schema": records.SCHEMA_SUPERSESSION, "version": records.VERSION, "superseded_receipt_id": RECEIPT_ID,
            "review_run_id": RUN_ID, "superseding_generation": 3, "reason": "invalidated",
        })
        entry = self.run_entry()
        self.assertEqual((entry["state"], entry["latest_generation"]), ("invalidated", 3))
        self.assertEqual((entry["receipt"]["status"], entry["receipt"]["receipt_id"]), ("superseded", RECEIPT_ID))

    def test_a_malformed_chain_is_invalid_with_its_reason(self) -> None:
        first = self.open_run()
        self.put(paths.gate_rel(RUN_ID, 3), gate_record(3, previous_digest=serialize.digest(first)))
        entry = self.run_entry()
        self.assertEqual(entry["state"], "invalid")
        self.assertEqual(entry["reason"]["code"], "review_gate_chain")
        self.assertIn("non-contiguous", entry["reason"]["message"])

    def test_a_broken_receipt_makes_the_run_invalid(self) -> None:
        self.sealed_run()
        (self.store.root / paths.receipt_rel(RECEIPT_ID)).write_bytes(b"schema: nonsense\n")
        entry = self.run_entry()
        self.assertEqual((entry["state"], entry["receipt"]["status"]), ("invalid", "invalid"))
        self.assertTrue(entry["reason"]["code"])

    def test_a_broken_namespace_does_not_hide_lifecycle(self) -> None:
        roadmap = self.simple_roadmap(self.store)
        (self.store.root / ".workline" / "review").mkdir(parents=True, exist_ok=True)
        (self.store.root / ".workline" / "review" / "gates").write_text("not a directory", encoding="utf-8")
        data = self.data()
        self.assertEqual(data["review"]["runs"]["status"], "unavailable")
        self.assertEqual(data["lifecycle"]["current"]["roadmap"]["id"], roadmap.roadmap_id)

    def test_obligations_wait_for_their_contract(self) -> None:
        self.sealed_run()
        entry = self.run_entry()
        self.assertEqual(entry["blocking_obligations"], {"status": "not_available_by_contract", "count": None})
        self.assertEqual(self.data()["review"]["pending_obligations"], {"status": "not_available_by_contract"})
        self.assertIn("set_aside", review_status.RUN_STATES, "set_aside is projected (test_status_set_aside)")

    def test_no_raw_report_text_or_digest_reaches_the_model(self) -> None:
        self.sealed_run()
        text = status.render_json(self.model()) + status.render_human(self.model())
        for leaked in (RAW_DIGEST, "raw_report", "accepted_tasks", "adjudication"):
            with self.subTest(leaked=leaked):
                self.assertNotIn(leaked, text)

    def test_review_records_never_change_lifecycle(self) -> None:
        roadmap = self.simple_roadmap(self.store)
        before = self.data()["lifecycle"]
        self.sealed_run()
        self.assertEqual(self.data()["lifecycle"], before)
        self.assertEqual(before["current"]["roadmap"]["id"], roadmap.roadmap_id)


class ActivationStatusTests(ActivationCase):
    def review(self) -> dict:
        return json.loads(status.render_json(status.build_status(self.root)))["review"]

    def test_activation_absent(self) -> None:
        self.assertEqual(self.review()["activation"]["status"], "absent")

    def test_activation_present(self) -> None:
        self.with_works()
        result = self.activate()
        activation = self.review()["activation"]
        self.assertEqual(activation["status"], "present", activation)
        self.assertEqual(activation["operation_contract"], "review-v1")
        self.assertEqual(activation["legacy_event_count"], result.legacy_event_count)
        authority = json.loads(status.render_json(status.build_status(self.root)))["authority"]
        self.assertEqual(authority["review_activation_contract"], "review-v1")

    def test_an_uncommitted_activation_is_invalid_never_absent(self) -> None:
        relative = Path(".workline/review/activation/work-terminal-v1.yaml")
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"schema: review-work-terminal-activation\nversion: 1\n")
        activation = self.review()["activation"]
        self.assertEqual(activation["status"], "invalid")
        self.assertEqual(activation["reason"]["code"], "review_record_conflict")

    def test_a_contradicting_event_log_makes_the_activation_invalid(self) -> None:
        self.with_events()
        self.activate()
        log = self.root / ".workline" / "events" / "events.jsonl"
        lines = log.read_bytes().split(b"\n")
        lines[0] = lines[0].replace(b'"at":"', b'"at":"1')
        log.write_bytes(b"\n".join(lines))
        activation = self.review()["activation"]
        self.assertEqual(activation["status"], "invalid")
        self.assertEqual(activation["reason"]["code"], "review_activation_prefix_mismatch")


if __name__ == "__main__":
    unittest.main()
