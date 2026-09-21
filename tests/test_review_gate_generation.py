"""R2/R3: Review IDs, reservation keys, the generation chain and same-run serialization."""

from __future__ import annotations

import unittest

from helpers import WorklineTestCase
from workline.errors import ReconcileRequired, ValidationError
from workline.ids import is_valid_id, kind_of, new_id
from workline.mutation import Effect, MutationController, WriteScope
from workline.oplock import project_operation
from workline.review import ReviewStore, gate, paths, records, serialize

RUN_ID = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"
OTHER_RUN = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAW"


def gate_record(generation: int, *, previous_digest: str | None = None, **overrides: object) -> dict:
    record = {
        "schema": records.SCHEMA_GATE,
        "version": records.VERSION,
        "review_run_id": RUN_ID,
        "generation": generation,
        "previous_generation": None if generation == 1 else generation - 1,
        "previous_digest": previous_digest,
        "review_kind": "work_formal",
        "target_identity": "w_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "operation_identity": "start",
        "candidate_hash": "a" * 64,
        "review_context_hash": "b" * 64,
        "effective_policy_hash": "c" * 64,
        "evidence_digest": "d" * 64,
        "coverage_digest": "e" * 64,
        "raw_report_set_digest": "f" * 64,
        "adjudication_digest": "0" * 64,
        "obligation_digest": "1" * 64,
        "accepted_tasks": [],
        "settled_tasks": [],
        "status": records.GATE_STATUS_OPEN,
        "receipt_id": None,
        "authorized_operation_stage": None,
    }
    record.update(overrides)
    # A seal records the operation stage it authorizes (it is what the Receipt's
    # own stage is bound to). Tests that seal get the same stage the Receipt
    # fixtures name, unless they say otherwise.
    if record["status"] == records.GATE_STATUS_SEALED and "authorized_operation_stage" not in overrides:
        record["authorized_operation_stage"] = "work-terminal"
    return record


class ReviewIdTests(unittest.TestCase):
    def test_the_four_review_kinds_exist_with_their_prefixes(self) -> None:
        for kind, prefix in (
            ("review_run", "rr"),
            ("review_receipt", "rcp"),
            ("review_consumption", "rcs"),
            ("review_task", "rtk"),
        ):
            identifier = new_id(kind)
            self.assertTrue(identifier.startswith(prefix + "_"), identifier)
            self.assertEqual(kind, kind_of(identifier))
            self.assertTrue(is_valid_id(identifier, kind))

    def test_review_prefixes_do_not_collide_with_roadmap(self) -> None:
        """``rr_``/``rcp_`` are read as themselves, not as the Roadmap prefix ``r``."""
        self.assertEqual("review_run", kind_of(RUN_ID))
        self.assertEqual("roadmap", kind_of("r_01ARZ3NDEKTSV4RRFFQ69G5FAV"))

    def test_reservation_keys_are_the_frozen_shapes(self) -> None:
        self.assertEqual("review-run:work_formal:w_1", gate.review_run_key("work_formal", "w_1"))
        self.assertEqual(f"review-receipt:{RUN_ID}:3", gate.review_receipt_key(RUN_ID, 3))
        self.assertEqual("review-consumption:rcp_x", gate.review_consumption_key("rcp_x"))
        self.assertEqual(f"review-task:{RUN_ID}:primary", gate.review_task_key(RUN_ID, "primary"))

    def test_reservation_key_parts_may_not_hide_a_separator(self) -> None:
        with self.assertRaises(ValidationError):
            gate.review_run_key("work:formal", "w_1")

    def test_generation_filenames_are_exact(self) -> None:
        self.assertEqual("000001.yaml", paths.generation_name(1))
        self.assertEqual("000042.yaml", paths.generation_name(42))
        self.assertEqual(1, paths.generation_of_name("000001.yaml"))
        for bad in ("1.yaml", "0000001.yaml", "000000.yaml", "00000a.yaml", "000001.yml", "x.yaml"):
            self.assertIsNone(paths.generation_of_name(bad), bad)

    def test_a_generation_is_not_an_allocated_identifier(self) -> None:
        with self.assertRaises(ValidationError):
            paths.generation_name(0)
        with self.assertRaises(ValidationError):
            paths.generation_name(-1)


class GateChainTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.review = ReviewStore(self.store)
        self.controller = MutationController(self.store)
        lock = project_operation(self.store, "review-gate-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)

    def _put(self, generation: int, record: dict) -> str:
        relative = paths.gate_rel(RUN_ID, generation)
        target = self.store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        text = serialize.canonical_text(record)
        target.write_text(text, encoding="utf-8", newline="")
        return serialize.digest_of_text(text)

    def _chain(self, length: int) -> list[str]:
        digests: list[str] = []
        previous: str | None = None
        for generation in range(1, length + 1):
            previous = self._put(generation, gate_record(generation, previous_digest=previous))
            digests.append(previous)
        return digests

    # chain validity ---------------------------------------------------------
    def test_no_chain_yields_generation_one(self) -> None:
        self.assertIsNone(self.review.gate_chain(RUN_ID))
        self.assertEqual(1, self.review.next_generation(RUN_ID))

    def test_contiguous_chain_validates_and_names_its_latest(self) -> None:
        self._chain(3)
        chain = self.review.gate_chain(RUN_ID)
        self.assertEqual(3, chain.latest.generation)
        self.assertEqual(4, chain.next_generation)
        self.assertEqual(4, self.review.next_generation(RUN_ID))

    def test_a_gap_fails_closed(self) -> None:
        self._put(1, gate_record(1))
        self._put(3, gate_record(3, previous_digest="a" * 64))
        with self.assertRaises(ValidationError) as caught:
            self.review.gate_chain(RUN_ID)
        self.assertEqual("review_gate_chain", caught.exception.code)

    def test_a_chain_that_does_not_start_at_one_fails_closed(self) -> None:
        self._put(2, gate_record(2, previous_digest="a" * 64))
        with self.assertRaises(ValidationError) as caught:
            self.review.gate_chain(RUN_ID)
        self.assertEqual("review_gate_chain", caught.exception.code)

    def test_a_wrong_predecessor_digest_fails_closed(self) -> None:
        self._put(1, gate_record(1))
        self._put(2, gate_record(2, previous_digest="9" * 64))
        with self.assertRaises(ValidationError) as caught:
            self.review.gate_chain(RUN_ID)
        self.assertEqual("review_gate_chain", caught.exception.code)

    def test_a_predecessor_that_is_not_the_generation_before_fails_closed(self) -> None:
        record = gate_record(2, previous_digest="a" * 64)
        record["previous_generation"] = 0
        with self.assertRaises(ValidationError):
            records.GateGeneration.from_record(record, "gate")

    def test_generation_one_may_not_name_a_predecessor(self) -> None:
        record = gate_record(1)
        record["previous_generation"] = 0
        record["previous_digest"] = "a" * 64
        with self.assertRaises(ValidationError):
            records.GateGeneration.from_record(record, "gate")

    def test_filename_must_equal_the_generation_inside(self) -> None:
        self._put(1, gate_record(2, previous_digest="a" * 64))
        with self.assertRaises(ValidationError) as caught:
            self.review.gate_chain(RUN_ID)
        self.assertEqual("review_gate_chain", caught.exception.code)

    def test_a_foreign_file_in_the_run_directory_fails_closed(self) -> None:
        self._chain(1)
        (self.store.root / paths.run_dir(RUN_ID) / "notes.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(ValidationError) as caught:
            self.review.gate_chain(RUN_ID)
        self.assertEqual("review_namespace_invalid", caught.exception.code)

    def test_a_physical_serialization_token_fails_closed(self) -> None:
        """The token is scope-only; a file at that path is never something Workline wrote."""
        self._chain(1)
        (self.store.root / paths.serialization_token_rel(RUN_ID)).write_text("x", encoding="utf-8")
        with self.assertRaises(ValidationError) as caught:
            self.review.gate_chain(RUN_ID)
        self.assertEqual("review_namespace_invalid", caught.exception.code)

    def test_unknown_schema_version_fails_closed(self) -> None:
        self._put(1, gate_record(1, version=2))
        with self.assertRaises(ValidationError) as caught:
            self.review.gate_chain(RUN_ID)
        self.assertEqual("review_record_version", caught.exception.code)

    def test_unknown_field_fails_closed_rather_than_being_dropped(self) -> None:
        record = gate_record(1)
        record["invented_later"] = "x"
        with self.assertRaises(ValidationError) as caught:
            records.GateGeneration.from_record(record, "gate")
        self.assertIn("unknown field", str(caught.exception))

    def test_supersession_is_derived_from_the_chain_not_stored(self) -> None:
        """``superseded`` is not a stored status: a later generation is what supersedes."""
        self.assertNotIn("superseded", records.GATE_STATUSES)
        receipt = "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV"
        previous = self._put(
            1, gate_record(1, status=records.GATE_STATUS_SEALED, receipt_id=receipt)
        )
        self._put(2, gate_record(2, previous_digest=previous))
        chain = self.review.gate_chain(RUN_ID)
        self.assertEqual((receipt,), chain.superseded_receipts())

    # same-run serialization -------------------------------------------------
    def _open_generation_mutation(self, review_run_id: str = RUN_ID):
        scope = gate.next_generation_scope(self.store, review_run_id)
        return self.controller.open(
            "start",
            {"operation": "review-gate", "review_run_id": review_run_id, "generation": scope.generation},
            WriteScope(files=tuple(scope.files)),
        ), scope

    def test_the_initial_scope_carries_both_paths(self) -> None:
        scope = gate.next_generation_scope(self.store, RUN_ID)
        self.assertEqual(
            [paths.gate_rel(RUN_ID, 1), paths.serialization_token_rel(RUN_ID)], scope.files
        )

    def test_the_token_is_never_created_on_disk(self) -> None:
        mutation, scope = self._open_generation_mutation()
        mutation.add_effects("gate", [Effect.create_file(scope.gate_path, serialize.canonical_text(gate_record(1)))])
        mutation.apply()
        self.assertTrue((self.store.root / scope.gate_path).is_file())
        self.assertFalse((self.store.root / scope.token_path).exists())

    def test_a_pending_same_run_mutation_blocks_a_new_generation(self) -> None:
        """The crash window: the physical generation exists, its applied flag does not."""
        mutation, scope = self._open_generation_mutation()
        mutation.add_effects("gate", [Effect.create_file(scope.gate_path, serialize.canonical_text(gate_record(1)))])
        # The file appears, and the mutation stays pending - exactly the state a
        # crash between the write and the applied save leaves behind.
        self.controller.apply_effect(mutation.effects[0])
        self.assertTrue((self.store.root / scope.gate_path).is_file())
        with self.assertRaises(ValidationError) as caught:
            gate.next_generation_scope(self.store, RUN_ID)
        self.assertEqual("review_generation_pending", caught.exception.code)

    def test_no_n_plus_two_fork_after_that_crash(self) -> None:
        mutation, scope = self._open_generation_mutation()
        mutation.add_effects("gate", [Effect.create_file(scope.gate_path, serialize.canonical_text(gate_record(1)))])
        self.controller.apply_effect(mutation.effects[0])
        # The chain now reads generation 1, so an unguarded owner would compute 2.
        self.assertEqual(2, self.review.next_generation(RUN_ID))
        # The guard refuses instead of opening generation 2 beside a pending 1.
        with self.assertRaises(ValidationError):
            gate.next_generation_scope(self.store, RUN_ID)

    def test_resuming_the_pending_mutation_lets_the_next_generation_proceed(self) -> None:
        mutation, scope = self._open_generation_mutation()
        mutation.add_effects("gate", [Effect.create_file(scope.gate_path, serialize.canonical_text(gate_record(1)))])
        self.controller.apply_effect(mutation.effects[0])
        resumed = self.controller.load(mutation.id)
        resumed.apply()
        resumed.complete()
        scope = gate.next_generation_scope(self.store, RUN_ID)
        self.assertEqual(2, scope.generation)

    def test_the_token_stops_a_second_same_run_mutation_at_open(self) -> None:
        """First layer: the shared token makes the second attempt's scope overlap the first."""
        self._open_generation_mutation()
        with self.assertRaises(ReconcileRequired):
            self.controller.open(
                "start",
                {"operation": "review-gate", "review_run_id": RUN_ID, "generation": 1, "attempt": 2},
                WriteScope(files=(paths.serialization_token_rel(RUN_ID),)),
            )

    def test_two_pending_same_run_records_reconcile(self) -> None:
        """Second layer: a record set that already holds two is refused rather than chosen between.

        ``open`` will not produce this state - the token makes the second
        attempt overlap the first - so it is built directly, as an older build
        or a hand-edited record set could leave it.
        """
        first, _ = self._open_generation_mutation()
        text = first.path.read_text(encoding="utf-8")
        twin = self.store.mutations / "mut_01ARZ3NDEKTSV4RRFFQ69G5FAW.yaml"
        twin.write_text(
            text.replace(first.id, "mut_01ARZ3NDEKTSV4RRFFQ69G5FAW"), encoding="utf-8", newline=""
        )
        with self.assertRaises(ValidationError) as caught:
            gate.next_generation_scope(self.store, RUN_ID)
        self.assertEqual("review_generation_conflict", caught.exception.code)

    def test_a_pending_mutation_for_another_run_does_not_block(self) -> None:
        self.controller.open(
            "start",
            {"operation": "review-gate", "review_run_id": OTHER_RUN, "generation": 1},
            WriteScope(files=(paths.serialization_token_rel(OTHER_RUN),)),
        )
        scope = gate.next_generation_scope(self.store, RUN_ID)
        self.assertEqual(1, scope.generation)

    def test_the_token_makes_two_generation_mutations_overlap(self) -> None:
        """Scope overlap is what the token exists for, independent of the guard."""
        first = WriteScope(files=tuple(gate.GenerationScope(RUN_ID, 1, paths.gate_rel(RUN_ID, 1), paths.serialization_token_rel(RUN_ID)).files))
        second = WriteScope(files=tuple(gate.GenerationScope(RUN_ID, 2, paths.gate_rel(RUN_ID, 2), paths.serialization_token_rel(RUN_ID)).files))
        self.assertTrue(first.overlaps(second))


if __name__ == "__main__":
    unittest.main()
