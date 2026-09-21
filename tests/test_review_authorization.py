"""R3 §7 / R4: accepted vs settled, seal + Receipt in one stage, and Consumption uniqueness."""

from __future__ import annotations

import unittest

from helpers import WorklineTestCase
from workline.errors import ValidationError
from workline.mutation import MATCHING, UNAPPLIED, Effect, MutationController, WriteScope
from workline.oplock import project_operation
from workline.review import ReviewStore, gate, paths, records, serialize
from workline.validate import validate_project

from test_review_gate_generation import gate_record
from test_review_provenance import CANDIDATE, TASK_ID, snapshot_record, task_input_record

RUN_ID = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"
RECEIPT_ID = "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV"
OTHER_RECEIPT = "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAW"
CONSUMPTION_ID = "rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV"
OTHER_CONSUMPTION = "rcs_01ARZ3NDEKTSV4RRFFQ69G5FAW"
EVENT_ID = "evt_01ARZ3NDEKTSV4RRFFQ69G5FAV"
MUTATION_ID = "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV"


def accepted_task(**overrides: object) -> dict:
    record = {
        "task_id": TASK_ID,
        "task_slot": "primary",
        "task_kind": "formal_review",
        "reviewer_identity": "reviewer-a",
        "reviewer_version": "3.1",
        "candidate_hash": CANDIDATE,
        "candidate_material_digest": serialize.digest(snapshot_record()),
        "reconstruction_mode": records.RECONSTRUCTION_SNAPSHOT,
        "request_digest": "d" * 64,
        "task_input_digest": serialize.digest(task_input_record()),
        "review_context_hash": "f" * 64,
        "effective_policy_hash": "0" * 64,
    }
    record.update(overrides)
    return record


def settled_task(**overrides: object) -> dict:
    record = {
        "task_id": TASK_ID,
        "status": records.TASK_SETTLED_OK,
        "result_digest": "7" * 64,
        "settled_generation": 2,
    }
    record.update(overrides)
    return record


def receipt_record(**overrides: object) -> dict:
    record = {
        "schema": records.SCHEMA_RECEIPT,
        "version": records.VERSION,
        "receipt_id": RECEIPT_ID,
        "review_run_id": RUN_ID,
        "review_generation": 3,
        "review_kind": "work_formal",
        "target_identity": "w_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "operation_identity": "start",
        "authorized_candidate_hash": CANDIDATE,
        "review_context_hash": "b" * 64,
        "effective_policy_hash": "c" * 64,
        "coverage_hash": "d" * 64,
        "adjudication_hash": "e" * 64,
        "obligation_digest": "1" * 64,
        "unresolved_obligations": 0,
        "authorized_operation_stage": "work-terminal",
    }
    record.update(overrides)
    return record


def consumption_record(**overrides: object) -> dict:
    record = {
        "schema": records.SCHEMA_CONSUMPTION,
        "version": records.VERSION,
        "consumption_id": CONSUMPTION_ID,
        "receipt_id": RECEIPT_ID,
        "review_run_id": RUN_ID,
        "review_generation": 3,
        "review_kind": "work_formal",
        "authorized_candidate_hash": CANDIDATE,
        "operation_identity": "start",
        "operation_mutation_id": MUTATION_ID,
        "terminal_event_id": EVENT_ID,
        "terminal_event_type": "work_completed",
        "target_identity": "w_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "authorized_result_commit_sha": "a" * 40,
    }
    record.update(overrides)
    return record


class GateTaskTests(unittest.TestCase):
    def test_accepted_and_settled_are_different_facts(self) -> None:
        generation = records.GateGeneration.from_record(
            gate_record(1, accepted_tasks=[accepted_task()]), "gate"
        )
        self.assertEqual((TASK_ID,), generation.accepted_task_ids())
        self.assertEqual((), generation.settled_task_ids())
        self.assertEqual((TASK_ID,), generation.unsettled_task_ids())

    def test_settling_a_task_clears_it_from_unsettled(self) -> None:
        generation = records.GateGeneration.from_record(
            gate_record(2, previous_digest="a" * 64, accepted_tasks=[accepted_task()], settled_tasks=[settled_task()]),
            "gate",
        )
        self.assertEqual((), generation.unsettled_task_ids())

    def test_settling_a_task_never_accepted_is_refused(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            records.GateGeneration.from_record(gate_record(1, settled_tasks=[settled_task()]), "gate")
        self.assertIn("never accepted", str(caught.exception))

    def test_a_duplicate_accepted_task_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            records.GateGeneration.from_record(
                gate_record(1, accepted_tasks=[accepted_task(), accepted_task()]), "gate"
            )

    def test_a_conflicting_duplicate_settlement_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            records.GateGeneration.from_record(
                gate_record(
                    1,
                    accepted_tasks=[accepted_task()],
                    settled_tasks=[settled_task(), settled_task(status=records.TASK_SETTLED_FAILED)],
                ),
                "gate",
            )

    def test_an_accepted_task_must_bind_both_provenance_digests(self) -> None:
        for missing in ("candidate_material_digest", "task_input_digest"):
            task = accepted_task()
            del task[missing]
            with self.assertRaises(ValidationError):
                records.validate_accepted_task(task, "gate")

    def test_an_open_generation_issues_no_receipt(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            records.GateGeneration.from_record(
                gate_record(1, status=records.GATE_STATUS_OPEN, receipt_id=RECEIPT_ID), "gate"
            )
        self.assertIn("only a sealed generation", str(caught.exception))


class ReceiptTests(unittest.TestCase):
    def test_a_receipt_issues_only_at_zero_unresolved_obligations(self) -> None:
        records.Receipt.from_record(receipt_record(), "receipt")
        with self.assertRaises(ValidationError):
            records.Receipt.from_record(receipt_record(unresolved_obligations=1), "receipt")

    def test_a_receipt_carries_no_commit_of_its_own_storage(self) -> None:
        self.assertNotIn("commit", " ".join(records.RECEIPT_FIELDS))

    def test_receipt_round_trips_canonically(self) -> None:
        record = receipt_record()
        self.assertEqual(record, records.Receipt.from_record(record, "receipt").to_record())


class SealAndConsumptionTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.review = ReviewStore(self.store)
        self.controller = MutationController(self.store)
        lock = project_operation(self.store, "review-authorization-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)

    def _put(self, relative: str, record: dict) -> None:
        target = self.store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialize.canonical_text(record), encoding="utf-8", newline="")

    def _chain_to_seal(self) -> None:
        """A Run whose generation 3 seals and issues ``RECEIPT_ID``."""
        first = gate_record(1, candidate_hash=CANDIDATE, accepted_tasks=[accepted_task()])
        self._put(paths.gate_rel(RUN_ID, 1), first)
        second = gate_record(
            2,
            previous_digest=serialize.digest(first),
            candidate_hash=CANDIDATE,
            accepted_tasks=[accepted_task()],
            settled_tasks=[settled_task()],
        )
        self._put(paths.gate_rel(RUN_ID, 2), second)
        third = gate_record(
            3,
            previous_digest=serialize.digest(second),
            candidate_hash=CANDIDATE,
            accepted_tasks=[accepted_task()],
            settled_tasks=[settled_task()],
            status=records.GATE_STATUS_SEALED,
            receipt_id=RECEIPT_ID,
        )
        self._put(paths.gate_rel(RUN_ID, 3), third)
        self._put(paths.receipt_rel(RECEIPT_ID), receipt_record())
        self._put(paths.candidate_snapshot_rel(CANDIDATE), snapshot_record())
        self._put(paths.task_input_rel(TASK_ID), task_input_record())

    # seal -------------------------------------------------------------------
    def test_sealing_with_an_unsettled_accepted_task_fails_validation(self) -> None:
        record = gate_record(
            1,
            candidate_hash=CANDIDATE,
            accepted_tasks=[accepted_task()],
            status=records.GATE_STATUS_SEALED,
            receipt_id=RECEIPT_ID,
        )
        self._put(paths.gate_rel(RUN_ID, 1), record)
        self._put(paths.receipt_rel(RECEIPT_ID), receipt_record(review_generation=1))
        self._put(paths.candidate_snapshot_rel(CANDIDATE), snapshot_record())
        self._put(paths.task_input_rel(TASK_ID), task_input_record())
        codes = [p.code for p in validate_project(self.store)]
        self.assertIn("review_gate_chain", codes)

    def test_seal_and_receipt_are_one_stage_and_resume_together(self) -> None:
        """A partial stage resumes the remaining effect; nothing is consumable before both exist."""
        first = gate_record(1, candidate_hash=CANDIDATE)
        self._put(paths.gate_rel(RUN_ID, 1), first)
        seal = gate_record(
            2,
            previous_digest=serialize.digest(first),
            candidate_hash=CANDIDATE,
            status=records.GATE_STATUS_SEALED,
            receipt_id=RECEIPT_ID,
        )
        gate_path = paths.gate_rel(RUN_ID, 2)
        receipt_path = paths.receipt_rel(RECEIPT_ID)
        mutation = self.controller.open(
            "start",
            {"operation": "review-seal", "review_run_id": RUN_ID, "generation": 2},
            WriteScope(files=(gate_path, receipt_path, paths.serialization_token_rel(RUN_ID))),
        )
        mutation.add_effects(
            "seal",
            [
                Effect.create_file(gate_path, serialize.canonical_text(seal)),
                Effect.create_file(receipt_path, serialize.canonical_text(receipt_record(review_generation=2))),
            ],
        )
        # Crash after the generation and before the Receipt.
        self.controller.apply_effect(mutation.effects[0])
        self.assertTrue((self.store.root / gate_path).is_file())
        self.assertFalse((self.store.root / receipt_path).is_file())
        # The seal is not usable: the Receipt it names is not stored.
        self.assertIn("review_record_missing", [p.code for p in validate_project(self.store)])
        # Resume writes exactly the remaining effect: the generation was already
        # there, the Receipt was not, and ``apply`` reports what it found before
        # writing it.
        outcomes = self.controller.load(mutation.id).apply()
        self.assertEqual([MATCHING, UNAPPLIED], [classification for _, classification in outcomes])
        self.assertTrue((self.store.root / receipt_path).is_file())
        # And a further replay writes nothing at all.
        self.assertEqual(
            [MATCHING, MATCHING], [c for _, c in self.controller.load(mutation.id).apply()]
        )
        self.assertEqual([], [p.code for p in validate_project(self.store)])

    def test_a_receipt_issued_by_an_open_generation_fails_validation(self) -> None:
        self._put(paths.gate_rel(RUN_ID, 1), gate_record(1, candidate_hash=CANDIDATE))
        self._put(paths.receipt_rel(RECEIPT_ID), receipt_record(review_generation=1))
        codes = [p.code for p in validate_project(self.store)]
        self.assertIn("review_record_conflict", codes)

    def test_a_receipt_authorizing_another_candidate_fails_validation(self) -> None:
        self._chain_to_seal()
        self._put(paths.receipt_rel(RECEIPT_ID), receipt_record(authorized_candidate_hash="9" * 64))
        codes = [p.code for p in validate_project(self.store)]
        self.assertIn("review_record_conflict", codes)

    def test_a_sealed_chain_validates(self) -> None:
        self._chain_to_seal()
        self.assertEqual([], [p.code for p in validate_project(self.store)])

    # consumption ------------------------------------------------------------
    def test_one_receipt_has_at_most_one_consumption(self) -> None:
        self._chain_to_seal()
        self._put(paths.consumption_rel(CONSUMPTION_ID), consumption_record())
        self.assertEqual(RECEIPT_ID, next(iter(self.review.consumption_by_receipt())))
        self._put(
            paths.consumption_rel(OTHER_CONSUMPTION),
            consumption_record(consumption_id=OTHER_CONSUMPTION, terminal_event_id="evt_01ARZ3NDEKTSV4RRFFQ69G5FAW"),
        )
        with self.assertRaises(ValidationError) as caught:
            self.review.consumption_by_receipt()
        self.assertEqual("review_consumption_conflict", caught.exception.code)

    def test_one_terminal_event_has_at_most_one_consumption(self) -> None:
        self._chain_to_seal()
        self._put(paths.receipt_rel(OTHER_RECEIPT), receipt_record(receipt_id=OTHER_RECEIPT))
        self._put(paths.consumption_rel(CONSUMPTION_ID), consumption_record())
        self._put(
            paths.consumption_rel(OTHER_CONSUMPTION),
            consumption_record(consumption_id=OTHER_CONSUMPTION, receipt_id=OTHER_RECEIPT),
        )
        with self.assertRaises(ValidationError) as caught:
            self.review.consumption_by_terminal_event()
        self.assertEqual("review_consumption_conflict", caught.exception.code)

    def test_exact_replay_of_one_consumption_is_idempotent(self) -> None:
        self._chain_to_seal()
        relative = paths.consumption_rel(CONSUMPTION_ID)
        text = serialize.canonical_text(consumption_record())
        mutation = self.controller.open(
            "start", {"operation": "review-consume", "receipt_id": RECEIPT_ID}, WriteScope(files=(relative,))
        )
        mutation.add_effects("consume", [Effect.create_file(relative, text)])
        self.assertEqual([UNAPPLIED], [c for _, c in [(0, self.controller.classify(mutation.effects[0]))]])
        mutation.apply()
        self.assertEqual([MATCHING], [c for _, c in mutation.apply()])

    def test_a_planning_consumption_names_no_terminal_event(self) -> None:
        record = consumption_record(
            terminal_event_id=None, terminal_event_type=None, authorized_result_commit_sha=None, review_kind="roadmap_planning"
        )
        parsed = records.Consumption.from_record(record, "consumption")
        self.assertIsNone(parsed.terminal_event_id)

    def test_a_half_named_terminal_event_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            records.Consumption.from_record(consumption_record(terminal_event_type=None), "consumption")

    def test_a_consumption_of_an_unstored_receipt_fails_validation(self) -> None:
        self._put(paths.consumption_rel(CONSUMPTION_ID), consumption_record())
        codes = [p.code for p in validate_project(self.store)]
        self.assertIn("review_record_missing", codes)

    def test_a_consumption_naming_another_candidate_fails_validation(self) -> None:
        self._chain_to_seal()
        self._put(paths.consumption_rel(CONSUMPTION_ID), consumption_record(authorized_candidate_hash="9" * 64))
        codes = [p.code for p in validate_project(self.store)]
        self.assertIn("review_record_conflict", codes)

    def test_receipt_existence_is_not_consumption(self) -> None:
        self._chain_to_seal()
        self.assertTrue(self.review.receipt_exists(RECEIPT_ID))
        self.assertEqual({}, self.review.consumption_by_receipt())

    def test_the_consumption_reservation_key_is_the_receipt(self) -> None:
        self.assertEqual(f"review-consumption:{RECEIPT_ID}", gate.review_consumption_key(RECEIPT_ID))

    # supersession -----------------------------------------------------------
    def test_a_supersession_of_an_unstored_receipt_fails_validation(self) -> None:
        self._put(
            paths.supersession_rel(RECEIPT_ID),
            {
                "schema": records.SCHEMA_SUPERSESSION,
                "version": records.VERSION,
                "superseded_receipt_id": RECEIPT_ID,
                "review_run_id": RUN_ID,
                "superseding_generation": 4,
                "reason": "a newly supported invalidating fact",
            },
        )
        codes = [p.code for p in validate_project(self.store)]
        self.assertIn("review_record_missing", codes)

    def test_a_supersession_alongside_its_receipt_validates(self) -> None:
        self._chain_to_seal()
        self._put(
            paths.supersession_rel(RECEIPT_ID),
            {
                "schema": records.SCHEMA_SUPERSESSION,
                "version": records.VERSION,
                "superseded_receipt_id": RECEIPT_ID,
                "review_run_id": RUN_ID,
                "superseding_generation": 4,
                "reason": "a newly supported invalidating fact",
            },
        )
        self.assertEqual([], [p.code for p in validate_project(self.store)])


if __name__ == "__main__":
    unittest.main()
