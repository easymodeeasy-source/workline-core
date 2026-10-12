"""RB11 RT-2 (rev-11 BRIEF §41.6, TFI §A.2 T-A21..T-A24): the status lock hint shows holder fields as hints only.

``lock.state`` stays ``not_checked``; the fields are what ``ProjectOperationBusy``
already reports, read from ``holder.json`` as the diagnostic it is (it may be
stale and is never authority); nothing is written to it; a field UTF-8 cannot
carry is left out. Added here: ``holder_acquired_at``. The holder's ``pid`` and
``host`` are not shown: ``test_status_read_only`` pins that they never appear in
status, a pin RT-2 may not change beyond ADM §F (reported as an RB11 stop).
"""

from __future__ import annotations

import json
import unittest

from status_helpers import StatusCase
from workline import oplock, status
from workline.oplock import project_operation


class LockHintTests(StatusCase):
    def hint(self) -> dict:
        return self.data()["pending"]["lock"]

    def write_holder(self, **fields) -> None:
        self.store.locks.mkdir(parents=True, exist_ok=True)
        record = {"workline": oplock.HOLDER_MARKER, "version": 1, "operation": "start", "pid": 4242,
                  "host": "elsewhere-host", "acquired_at": "2026-10-12T01:02:03+00:00", "mutation_id": None, **fields}
        self.store.lock_holder.write_text(json.dumps(record), encoding="utf-8")

    def test_t_a21_the_hint_shows_the_holder_fields_busy_reports_and_stays_not_checked(self) -> None:
        self.store = self.new_project()
        with project_operation(self.store, "start", {"work_id": "w_x"}) as lock:
            oplock.note_mutation(self.store, "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV")
            holder_bytes = self.store.lock_holder.read_bytes()
            found = self.hint()
            self.assertEqual(self.store.lock_holder.read_bytes(), holder_bytes, "nothing written to holder.json")
        self.assertEqual(found, {
            "state": "not_checked", "holder_hint": "present", "holder_operation": "start",
            "holder_mutation_id": "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV", "holder_acquired_at": lock.acquired_at,
        })

    def test_t_a23_a_ghost_holder_is_a_hint_only(self) -> None:
        self.store = self.new_project()
        self.write_holder()
        found = self.hint()
        self.assertEqual((found["state"], found["holder_hint"], found["holder_acquired_at"]),
                         ("not_checked", "present", "2026-10-12T01:02:03+00:00"))
        text = json.dumps(self.data())
        self.assertNotIn("4242", text, "the holder's pid is not shown (test_status_read_only pin)")
        self.assertNotIn("elsewhere-host", text, "the holder's host is not shown (test_status_read_only pin)")

    def test_t_a24_a_field_utf8_cannot_carry_is_left_out(self) -> None:
        self.store = self.new_project()
        self.store.locks.mkdir(parents=True, exist_ok=True)
        self.store.lock_holder.write_text(
            '{"workline": "%s", "version": 1, "operation": "start", "acquired_at": "2026-10-12\\ud800", '
            '"mutation_id": null}' % oplock.HOLDER_MARKER, encoding="utf-8")
        found = self.hint()
        self.assertEqual((found["holder_hint"], found["holder_acquired_at"]), ("present", None))
        status.render_json(self.model())  # the model renders

    def test_t_a24_operation_and_mutation_id_utf8_cannot_carry_are_left_out_too(self) -> None:
        """RB11 repair RTR-8: the guard covers every holder field the hint shows, not only the one RT-2 added."""
        self.store = self.new_project()
        self.store.locks.mkdir(parents=True, exist_ok=True)
        self.store.lock_holder.write_text(
            '{"workline": "%s", "version": 1, "operation": "start\\ud800", "acquired_at": "2026-10-12T01:02:03+00:00", '
            '"mutation_id": "mut_\\udfff"}' % oplock.HOLDER_MARKER, encoding="utf-8")
        found = self.hint()
        self.assertEqual((found["holder_hint"], found["holder_operation"], found["holder_mutation_id"],
                          found["holder_acquired_at"]), ("present", None, None, "2026-10-12T01:02:03+00:00"))
        status.render_human(self.model())  # the human rendering takes the model as it is

    def test_a_value_that_is_not_text_is_left_out_and_an_absent_holder_shows_nothing(self) -> None:
        self.store = self.new_project()
        self.assertEqual(self.hint()["holder_acquired_at"], None)
        self.write_holder(acquired_at=12345)
        self.assertIsNone(self.hint()["holder_acquired_at"])


if __name__ == "__main__":
    unittest.main()
