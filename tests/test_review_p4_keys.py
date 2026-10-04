"""P4 (§27.7 / §27.14): Finding and Repair Batch ID kinds and their deterministic reservation keys."""

from __future__ import annotations

import unittest

from workline.errors import ValidationError
from workline.ids import is_valid_id, kind_of, new_id
from workline.review import gate

RUN_ID = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"


class P4IdKindTests(unittest.TestCase):
    def test_the_p4_kinds_exist_with_their_prefixes(self) -> None:
        for kind, prefix in (("review_finding", "rfd"), ("review_repair_batch", "rrb")):
            identifier = new_id(kind)
            self.assertTrue(identifier.startswith(prefix + "_"), identifier)
            self.assertEqual(kind, kind_of(identifier))
            self.assertTrue(is_valid_id(identifier, kind))

    def test_p4_prefixes_never_read_as_a_shorter_prefix(self) -> None:
        self.assertEqual("review_repair_batch", kind_of("rrb_01ARZ3NDEKTSV4RRFFQ69G5FAV"))
        self.assertEqual("review_finding", kind_of("rfd_01ARZ3NDEKTSV4RRFFQ69G5FAV"))
        self.assertEqual("review_run", kind_of(RUN_ID))
        self.assertEqual("roadmap", kind_of("r_01ARZ3NDEKTSV4RRFFQ69G5FAV"))

    def test_the_existing_kinds_are_unchanged(self) -> None:
        for kind, prefix in (
            ("review_run", "rr"), ("review_receipt", "rcp"), ("review_consumption", "rcs"), ("review_task", "rtk"),
            ("mutation", "mut"), ("roadmap", "r"), ("phase", "p"), ("work", "w"), ("relation", "rel"),
            ("event", "evt"), ("derivation", "der"),
        ):
            self.assertEqual(kind, kind_of(new_id(kind)))
            self.assertTrue(new_id(kind).startswith(prefix + "_"))


class P4ReservationKeyTests(unittest.TestCase):
    def test_finding_key_shape(self) -> None:
        self.assertEqual(f"review-finding:{RUN_ID}:1", gate.review_finding_key(RUN_ID, 1))
        self.assertEqual(f"review-finding:{RUN_ID}:12", gate.review_finding_key(RUN_ID, 12))
        self.assertTrue(gate.review_finding_key(RUN_ID, 3).startswith(gate.FINDING_KEY_PREFIX))

    def test_finding_key_refuses_a_non_positive_or_non_int_ordinal(self) -> None:
        for bad in (0, -1, True, "1", 1.0, None):
            with self.assertRaises(ValidationError, msg=repr(bad)):
                gate.review_finding_key(RUN_ID, bad)  # type: ignore[arg-type]

    def test_finding_key_refuses_anything_but_a_review_run_id(self) -> None:
        for bad in ("w_01ARZ3NDEKTSV4RRFFQ69G5FAV", "", "rr_x", f"{RUN_ID}:1", f" {RUN_ID}"):
            with self.assertRaises(ValidationError, msg=repr(bad)):
                gate.review_finding_key(bad, 1)

    def test_repair_batch_key_shape(self) -> None:
        self.assertEqual(f"review-repair-batch:{RUN_ID}", gate.review_repair_batch_key(RUN_ID))
        self.assertTrue(gate.review_repair_batch_key(RUN_ID).startswith(gate.REPAIR_BATCH_KEY_PREFIX))

    def test_repair_batch_key_refuses_anything_but_a_review_run_id(self) -> None:
        for bad in ("w_01ARZ3NDEKTSV4RRFFQ69G5FAV", "", "rrb_01ARZ3NDEKTSV4RRFFQ69G5FAV", f"{RUN_ID}:x"):
            with self.assertRaises(ValidationError, msg=repr(bad)):
                gate.review_repair_batch_key(bad)

    def test_p4_keys_never_collide_with_existing_key_families(self) -> None:
        keys = {
            gate.review_run_key("work-result-v1", "w_01ARZ3NDEKTSV4RRFFQ69G5FAV"),
            gate.review_successor_run_key(RUN_ID),
            gate.review_receipt_key(RUN_ID, 5),
            gate.review_task_key(RUN_ID, "primary"),
            gate.review_finding_key(RUN_ID, 1),
            gate.review_repair_batch_key(RUN_ID),
        }
        self.assertEqual(6, len(keys))
        prefixes = {key.split(":", 1)[0] for key in keys}
        self.assertEqual(6, len(prefixes))


if __name__ == "__main__":
    unittest.main()
