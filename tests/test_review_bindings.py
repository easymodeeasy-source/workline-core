"""P1-REV-004 / P1-REV-005: authorization and provenance records bind their shared identities exactly.

Each negative test starts from one valid, exact chain - accepted, settled, sealed,
Receipt issued, Consumption recorded - and changes exactly one shared identity in
exactly one record. A match on the Candidate alone, or on a digest alone, is
never enough.
"""

from __future__ import annotations

import unittest

from helpers import WorklineTestCase
from workline.errors import ValidationError
from workline.review import ReviewStore, paths, records, serialize
from workline.review.gate import validate_settlement
from workline.validate import validate_project

from test_review_authorization import (
    CONSUMPTION_ID,
    RECEIPT_ID,
    accepted_task,
    consumption_record,
    receipt_record,
    settled_task,
)
from test_review_gate_generation import RUN_ID, gate_record
from test_review_provenance import CANDIDATE, TASK_ID, snapshot_record, task_input_record

OTHER_RUN = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAW"
OTHER_RECEIPT = "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAW"
OTHER_WORK = "w_01ARZ3NDEKTSV4RRFFQ69G5FAZ"


class BindingCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.review = ReviewStore(self.store)

    def _put(self, relative: str, record: dict) -> None:
        target = self.store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(serialize.canonical_bytes(record))

    def _g(self, number: int, **fields: object) -> dict:
        fields.setdefault("accepted_tasks", [accepted_task()])
        if number >= 2:
            fields.setdefault("settled_tasks", [settled_task(settled_generation=2)])
        return gate_record(number, candidate_hash=CANDIDATE, **fields)

    def _chain(self, *generations: dict, run: str = RUN_ID) -> list[str]:
        digests: list[str] = []
        previous = None
        for number, record in enumerate(generations, start=1):
            record = dict(record, previous_digest=previous, review_run_id=run)
            self._put(paths.gate_rel(run, number), record)
            previous = serialize.digest(record)
            digests.append(previous)
        return digests

    def valid(
        self,
        *,
        gate3: dict | None = None,
        receipt: dict | None = None,
        consumption: dict | None | bool = None,
        task_input: dict | None = None,
        accepted: dict | None = None,
        snapshot: dict | None = None,
    ) -> None:
        """One exact chain; each keyword replaces one record's fields."""
        snap = snapshot_record(**(snapshot or {}))
        self._put(paths.candidate_snapshot_rel(CANDIDATE), snap)
        ti = task_input_record(**(task_input or {}))
        self._put(paths.task_input_rel(TASK_ID), ti)
        descriptor = accepted_task(**(accepted or {}))
        self._chain(
            self._g(1, accepted_tasks=[descriptor]),
            self._g(2, accepted_tasks=[descriptor]),
            self._g(3, accepted_tasks=[descriptor], status=records.GATE_STATUS_SEALED, receipt_id=RECEIPT_ID, **(gate3 or {})),
        )
        self._put(paths.receipt_rel(RECEIPT_ID), receipt_record(review_generation=3, **(receipt or {})))
        if consumption is not False:
            self._put(paths.consumption_rel(CONSUMPTION_ID), consumption_record(**(consumption or {})))

    def codes(self) -> list[str]:
        return [p.code for p in validate_project(self.store)]

    def messages(self) -> str:
        return "\n".join(p.message for p in validate_project(self.store))


class GateReceiptBindingTests(BindingCase):
    """8.1: a sealed generation and its Receipt say the same thing, field for field."""

    def test_the_valid_exact_chain_passes(self) -> None:
        self.valid()
        self.assertEqual([], self.codes())

    def _mismatch(self, receipt_fields: dict, expected_field: str) -> None:
        self.valid(receipt=receipt_fields)
        self.assertIn("review_record_conflict", self.codes())
        self.assertIn(expected_field, self.messages())

    def test_target_mismatch_fails(self) -> None:
        self._mismatch({"target_identity": OTHER_WORK}, "target_identity")

    def test_context_mismatch_fails(self) -> None:
        self._mismatch({"review_context_hash": "9" * 64}, "review_context_hash")

    def test_policy_mismatch_fails(self) -> None:
        self._mismatch({"effective_policy_hash": "9" * 64}, "effective_policy_hash")

    def test_coverage_mismatch_fails(self) -> None:
        self._mismatch({"coverage_hash": "9" * 64}, "coverage_hash")

    def test_adjudication_mismatch_fails(self) -> None:
        self._mismatch({"adjudication_hash": "9" * 64}, "adjudication_hash")

    def test_obligation_mismatch_fails(self) -> None:
        self._mismatch({"obligation_digest": "9" * 64}, "obligation_digest")

    def test_kind_mismatch_fails(self) -> None:
        self._mismatch({"review_kind": "roadmap_planning"}, "review_kind")

    def test_operation_mismatch_fails(self) -> None:
        self._mismatch({"operation_identity": "roadmap"}, "operation_identity")

    def test_authorized_stage_mismatch_fails(self) -> None:
        self._mismatch({"authorized_operation_stage": "another-stage"}, "authorized_operation_stage")

    def test_candidate_mismatch_fails(self) -> None:
        self._mismatch({"authorized_candidate_hash": "9" * 64}, "authorized_candidate_hash")

    def test_a_receipt_claiming_a_generation_that_did_not_issue_it_fails(self) -> None:
        self.valid()
        self._put(paths.receipt_rel(RECEIPT_ID), receipt_record(review_generation=2))
        self.assertIn("review_record_conflict", self.codes())

    def test_a_seal_whose_receipt_is_not_stored_fails(self) -> None:
        self.valid(consumption=False)
        (self.store.root / paths.receipt_rel(RECEIPT_ID)).unlink()
        self.assertIn("review_record_missing", self.codes())


class ReceiptConsumptionBindingTests(BindingCase):
    """8.2: a Consumption repeats its Receipt's identities exactly."""

    def _mismatch(self, fields: dict, expected_field: str) -> None:
        self.valid(consumption=fields)
        self.assertIn("review_record_conflict", self.codes())
        self.assertIn(expected_field, self.messages())

    def test_generation_mismatch_fails(self) -> None:
        self._mismatch({"review_generation": 2}, "review_generation")

    def test_target_mismatch_fails(self) -> None:
        self._mismatch({"target_identity": OTHER_WORK}, "target_identity")

    def test_operation_mismatch_fails(self) -> None:
        self._mismatch({"operation_identity": "roadmap"}, "operation_identity")

    def test_kind_mismatch_fails(self) -> None:
        self._mismatch({"review_kind": "roadmap_planning"}, "review_kind")

    def test_candidate_mismatch_fails(self) -> None:
        self._mismatch({"authorized_candidate_hash": "9" * 64}, "authorized_candidate_hash")

    def test_run_mismatch_fails(self) -> None:
        self._mismatch({"review_run_id": OTHER_RUN}, "review_run_id")

    def test_a_partial_work_binding_is_refused(self) -> None:
        for dropped in ("terminal_event_id", "terminal_event_type", "authorized_result_commit_sha"):
            with self.assertRaises(ValidationError, msg=dropped):
                records.Consumption.from_record(consumption_record(**{dropped: None}), "consumption")

    def test_a_work_binding_to_another_event_type_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            records.Consumption.from_record(consumption_record(terminal_event_type="work_cancelled"), "consumption")

    def test_a_work_binding_whose_target_is_not_a_work_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            records.Consumption.from_record(consumption_record(target_identity="r_01ARZ3NDEKTSV4RRFFQ69G5FAV"), "consumption")

    def test_a_work_binding_exposes_its_work(self) -> None:
        found = records.Consumption.from_record(consumption_record(), "consumption")
        self.assertTrue(found.work_kind)
        self.assertEqual(found.target_identity, found.work_id)
        planning = records.Consumption.from_record(
            consumption_record(terminal_event_id=None, terminal_event_type=None, authorized_result_commit_sha=None),
            "consumption",
        )
        self.assertIsNone(planning.work_id)


class SupersessionTests(BindingCase):
    """8.3 / 8.4: supersession names a real, later, open generation, and a superseded Receipt is never consumed."""

    def _invalidate(self, *, record: bool = True, superseding: int = 4, run: str = RUN_ID) -> None:
        self.valid(consumption=False)
        chain = self.review.gate_chain(RUN_ID)
        self._put(
            paths.gate_rel(RUN_ID, 4),
            gate_record(4, previous_digest=chain.latest_digest, candidate_hash=CANDIDATE,
                        accepted_tasks=[accepted_task()], settled_tasks=[settled_task(settled_generation=2)]),
        )
        if record:
            self._put(
                paths.supersession_rel(RECEIPT_ID),
                {
                    "schema": records.SCHEMA_SUPERSESSION,
                    "version": records.VERSION,
                    "superseded_receipt_id": RECEIPT_ID,
                    "review_run_id": run,
                    "superseding_generation": superseding,
                    "reason": "a newly supported invalidating fact",
                },
            )

    def test_a_valid_invalidation_passes(self) -> None:
        self._invalidate()
        self.assertEqual([], self.codes())

    def test_a_consumption_of_a_superseded_receipt_fails(self) -> None:
        self._invalidate()
        self._put(paths.consumption_rel(CONSUMPTION_ID), consumption_record())
        self.assertIn("review_record_conflict", self.codes())
        self.assertIn("superseded", self.messages())

    def test_a_superseding_generation_that_does_not_exist_fails(self) -> None:
        self._invalidate(superseding=999)
        self.assertIn("review_record_conflict", self.codes())

    def test_a_superseding_generation_not_later_than_the_receipt_fails(self) -> None:
        for superseding in (3, 2):
            with self.subTest(superseding=superseding):
                self._invalidate(superseding=superseding)
                self.assertIn("review_record_conflict", self.codes())

    def test_a_supersession_naming_another_run_fails(self) -> None:
        self._invalidate(run=OTHER_RUN)
        self.assertIn("review_record_conflict", self.codes())

    def test_a_chain_moved_past_a_seal_without_a_supersession_record_fails(self) -> None:
        self._invalidate(record=False)
        self.assertIn("review_record_missing", self.codes())

    def test_a_supersession_pointing_at_a_sealed_generation_fails(self) -> None:
        self._invalidate(superseding=5)
        chain = self.review.gate_chain(RUN_ID)
        self._put(
            paths.gate_rel(RUN_ID, 5),
            gate_record(5, previous_digest=chain.latest_digest, candidate_hash=CANDIDATE,
                        accepted_tasks=[accepted_task()], settled_tasks=[settled_task(settled_generation=2)],
                        status=records.GATE_STATUS_SEALED, receipt_id=OTHER_RECEIPT),
        )
        self._put(paths.receipt_rel(OTHER_RECEIPT), receipt_record(receipt_id=OTHER_RECEIPT, review_generation=5))
        self.assertIn("sealed", self.messages())


class ProvenanceBindingTests(BindingCase):
    """P1-REV-005: accepted descriptor, stored task input and stored snapshot agree in every shared identity."""

    def test_the_exact_triple_passes(self) -> None:
        self.valid(consumption=False)
        self.assertEqual([], self.codes())
        self.assertEqual(TASK_ID, validate_settlement(self.store, RUN_ID, TASK_ID, "7" * 64, "reviewer-a")["task_id"])

    def test_the_reviewer_attack_is_refused(self) -> None:
        """Task input names reviewer-B v9 and material X; the descriptor names reviewer-A v3 and material Y,
        and binds the task input's exact digest. A digest match must not carry the rest."""
        attacked = task_input_record(reviewer_identity="reviewer-B", reviewer_version="9", candidate_material_digest="9" * 64)
        self.valid(consumption=False, accepted={"task_input_digest": serialize.digest(attacked)})
        self._put(paths.task_input_rel(TASK_ID), attacked)
        codes = self.codes()
        self.assertIn("review_provenance_conflict", codes)
        for field in ("reviewer_identity", "reviewer_version", "candidate_material_digest"):
            self.assertIn(field, self.messages())

    def _task_input_mismatch(self, field: str, value: object) -> None:
        changed = task_input_record(**{field: value})
        self.valid(consumption=False, accepted={"task_input_digest": serialize.digest(changed)})
        self._put(paths.task_input_rel(TASK_ID), changed)
        self.assertIn("review_provenance_conflict", self.codes())
        self.assertIn(field, self.messages())
        with self.assertRaises(ValidationError):
            validate_settlement(self.store, RUN_ID, TASK_ID, "7" * 64, "reviewer-a")

    def test_reviewer_mismatch_fails(self) -> None:
        self._task_input_mismatch("reviewer_identity", "reviewer-B")

    def test_reviewer_version_mismatch_fails(self) -> None:
        self._task_input_mismatch("reviewer_version", "9")

    def test_task_slot_mismatch_fails(self) -> None:
        self._task_input_mismatch("task_slot", "other-slot")

    def test_task_kind_mismatch_fails(self) -> None:
        self._task_input_mismatch("task_kind", "other-kind")

    def test_reconstruction_mode_mismatch_fails(self) -> None:
        self._task_input_mismatch("reconstruction_mode", records.RECONSTRUCTION_BUILDER)

    def test_candidate_material_digest_mismatch_fails(self) -> None:
        self._task_input_mismatch("candidate_material_digest", "9" * 64)

    def test_accepted_generation_mismatch_fails(self) -> None:
        self._task_input_mismatch("accepted_generation", 2)

    def test_a_changed_candidate_snapshot_fails(self) -> None:
        """The snapshot's bytes move; both the descriptor and the task input still bind the old digest."""
        self.valid(consumption=False, snapshot={"projection_semantics_version": "reviewed-artifact-v2"})
        self.assertIn("review_provenance_conflict", self.codes())
        self.assertIn("candidate_material_digest", self.messages())


if __name__ == "__main__":
    unittest.main()
