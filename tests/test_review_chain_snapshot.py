"""P1-REV-003: every gate generation is a full snapshot, so durable task facts cannot vanish by omission."""

from __future__ import annotations

import unittest

from helpers import WorklineTestCase
from workline.errors import ValidationError
from workline.review import ReviewStore, paths, records, serialize
from workline.validate import validate_project

from test_review_authorization import RECEIPT_ID, accepted_task, receipt_record, settled_task
from test_review_gate_generation import RUN_ID, gate_record
from test_review_provenance import CANDIDATE, TASK_ID, snapshot_record, task_input_record

OTHER_TASK = "rtk_01ARZ3NDEKTSV4RRFFQ69G5FAW"


class ChainSnapshotTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.review = ReviewStore(self.store)
        self._put(paths.candidate_snapshot_rel(CANDIDATE), snapshot_record())
        self._put(paths.task_input_rel(TASK_ID), task_input_record())

    def _put(self, relative: str, record: dict) -> None:
        target = self.store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(serialize.canonical_bytes(record))

    def _chain(self, *generations: dict) -> None:
        previous = None
        for number, record in enumerate(generations, start=1):
            record = dict(record, previous_digest=previous)
            self._put(paths.gate_rel(RUN_ID, number), record)
            previous = serialize.digest(record)

    def _refused(self, *generations: dict) -> str:
        self._chain(*generations)
        with self.assertRaises(ValidationError) as caught:
            self.review.gate_chain(RUN_ID)
        self.assertIn("review_gate_chain", [p.code for p in validate_project(self.store)])
        return str(caught.exception)

    def _g(self, number: int, **fields: object) -> dict:
        return gate_record(number, candidate_hash=CANDIDATE, **fields)

    # omission cannot erase a fact ---------------------------------------------
    def test_an_accepted_task_dropped_in_the_next_generation_is_refused(self) -> None:
        message = self._refused(self._g(1, accepted_tasks=[accepted_task()]), self._g(2))
        self.assertIn("drops accepted task", message)

    def test_the_reviewer_scenario_drop_then_seal_is_refused(self) -> None:
        """G1 accepts T; G2 omits T and seals. Must not be a valid authorization."""
        self._put(paths.receipt_rel(RECEIPT_ID), receipt_record(review_generation=2))
        message = self._refused(
            self._g(1, accepted_tasks=[accepted_task()]),
            self._g(2, status=records.GATE_STATUS_SEALED, receipt_id=RECEIPT_ID),
        )
        self.assertIn("drops accepted task", message)

    def test_a_settled_task_dropped_later_is_refused(self) -> None:
        message = self._refused(
            self._g(1, accepted_tasks=[accepted_task()]),
            self._g(2, accepted_tasks=[accepted_task()], settled_tasks=[settled_task()]),
            self._g(3, accepted_tasks=[accepted_task()]),
        )
        self.assertIn("drops the settlement", message)

    def test_an_accepted_descriptor_mutated_while_carried_forward_is_refused(self) -> None:
        message = self._refused(
            self._g(1, accepted_tasks=[accepted_task()]),
            self._g(2, accepted_tasks=[accepted_task(reviewer_version="9.9")]),
        )
        self.assertIn("different descriptor", message)

    # settled_generation -------------------------------------------------------
    def test_a_settlement_for_a_task_never_accepted_is_refused(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            records.GateGeneration.from_record(self._g(2, previous_digest="a" * 64, settled_tasks=[settled_task()]), "gate")
        self.assertIn("never accepted", str(caught.exception))

    def test_a_settlement_from_a_future_generation_is_refused(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            records.GateGeneration.from_record(
                self._g(2, previous_digest="a" * 64, accepted_tasks=[accepted_task()],
                        settled_tasks=[settled_task(settled_generation=7)]),
                "gate",
            )
        self.assertIn("later generation", str(caught.exception))

    def test_a_settlement_naming_a_generation_other_than_where_it_first_appears_is_refused(self) -> None:
        message = self._refused(
            self._g(1, accepted_tasks=[accepted_task()]),
            self._g(2, accepted_tasks=[accepted_task()]),
            self._g(3, accepted_tasks=[accepted_task()], settled_tasks=[settled_task(settled_generation=2)]),
        )
        self.assertIn("names settled_generation 2", message)

    def test_settled_generation_changed_in_a_later_snapshot_is_refused(self) -> None:
        message = self._refused(
            self._g(1, accepted_tasks=[accepted_task()]),
            self._g(2, accepted_tasks=[accepted_task()], settled_tasks=[settled_task(settled_generation=2)]),
            self._g(3, accepted_tasks=[accepted_task()], settled_tasks=[settled_task(settled_generation=3)]),
        )
        self.assertIn("forward changed", message)

    def test_a_settlement_in_the_generation_that_accepted_the_task_is_refused(self) -> None:
        """R3 section 3: the settlement is written as a later generation, after the accepted task persisted."""
        message = self._refused(
            self._g(1, accepted_tasks=[accepted_task()], settled_tasks=[settled_task(settled_generation=1)]),
        )
        self.assertIn("generation that accepted it", message)

    # seal ---------------------------------------------------------------------
    def test_a_seal_over_an_unsettled_task_is_refused(self) -> None:
        message = self._refused(
            self._g(1, accepted_tasks=[accepted_task()]),
            self._g(2, accepted_tasks=[accepted_task()], status=records.GATE_STATUS_SEALED, receipt_id=RECEIPT_ID),
        )
        self.assertIn("unsettled", message)

    def test_a_seal_followed_directly_by_another_seal_is_refused(self) -> None:
        other = "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAW"
        message = self._refused(
            self._g(1, status=records.GATE_STATUS_SEALED, receipt_id=RECEIPT_ID),
            self._g(2, status=records.GATE_STATUS_SEALED, receipt_id=other),
        )
        self.assertIn("another seal", message)

    def test_a_seal_names_the_stage_it_authorizes(self) -> None:
        with self.assertRaises(ValidationError):
            records.GateGeneration.from_record(
                self._g(1, status=records.GATE_STATUS_SEALED, receipt_id=RECEIPT_ID, authorized_operation_stage=None),
                "gate",
            )

    def test_a_seal_issues_a_receipt(self) -> None:
        with self.assertRaises(ValidationError):
            records.GateGeneration.from_record(self._g(1, status=records.GATE_STATUS_SEALED, receipt_id=None), "gate")

    # the valid shape ----------------------------------------------------------
    def test_valid_carry_forward_settlement_and_seal_pass(self) -> None:
        self._put(paths.receipt_rel(RECEIPT_ID), receipt_record(review_generation=3))
        self._chain(
            self._g(1, accepted_tasks=[accepted_task()]),
            self._g(2, accepted_tasks=[accepted_task()], settled_tasks=[settled_task(settled_generation=2)]),
            self._g(3, accepted_tasks=[accepted_task()], settled_tasks=[settled_task(settled_generation=2)],
                    status=records.GATE_STATUS_SEALED, receipt_id=RECEIPT_ID),
        )
        chain = self.review.gate_chain(RUN_ID)
        self.assertEqual((), chain.latest.unsettled_task_ids())
        self.assertEqual(1, chain.accepted_at(TASK_ID))
        self.assertEqual([], [p.code for p in validate_project(self.store)])

    def test_a_task_accepted_later_is_carried_alongside_earlier_ones(self) -> None:
        second = accepted_task(task_id=OTHER_TASK, task_slot="secondary")
        self._chain(
            self._g(1, accepted_tasks=[accepted_task()]),
            self._g(2, accepted_tasks=[accepted_task(), second]),
        )
        chain = self.review.gate_chain(RUN_ID)
        self.assertEqual(2, chain.accepted_at(OTHER_TASK))
        self.assertEqual((TASK_ID, OTHER_TASK), chain.latest.accepted_task_ids())


if __name__ == "__main__":
    unittest.main()
