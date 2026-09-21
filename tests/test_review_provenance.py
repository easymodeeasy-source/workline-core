"""R1 §6 / R3 §4-5: clone-safe Candidate and task provenance, and the digests that identify it."""

from __future__ import annotations

import unittest

from helpers import WorklineTestCase
from workline.errors import ValidationError
from workline.mutation import Effect, MutationController, WriteScope
from workline.oplock import project_operation
from workline.review import ReviewStore, fsafe, paths, records, serialize
from workline.validate import validate_project

CREATE_SUPPORTED = fsafe.immutable_create_supported()

RUN_ID = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"
TASK_ID = "rtk_01ARZ3NDEKTSV4RRFFQ69G5FAV"
CANDIDATE = "a" * 64


def snapshot_record(**overrides: object) -> dict:
    record = {
        "schema": records.SCHEMA_CANDIDATE_SNAPSHOT,
        "version": records.VERSION,
        "candidate_hash": CANDIDATE,
        "reconstruction_mode": records.RECONSTRUCTION_SNAPSHOT,
        "projection_semantics_version": "reviewed-artifact-v1",
        "material": {"paths": [{"path": "src/a.py", "mode": "100644", "object": "b" * 40}]},
        "builder": None,
    }
    record.update(overrides)
    return record


def builder_record(**overrides: object) -> dict:
    record = snapshot_record(
        reconstruction_mode=records.RECONSTRUCTION_BUILDER,
        material=None,
        builder={
            "builder_identity": "roadmap-projection",
            "builder_version": "1.2.0",
            "inputs": [{"name": "plan", "identity": "c" * 64}],
        },
    )
    record.update(overrides)
    return record


def task_input_record(**overrides: object) -> dict:
    record = {
        "schema": records.SCHEMA_TASK_INPUT,
        "version": records.VERSION,
        "task_id": TASK_ID,
        "task_slot": "primary",
        "task_kind": "formal_review",
        "reviewer_identity": "reviewer-a",
        "reviewer_version": "3.1",
        "request_envelope": {"instruction": "review this", "candidate": CANDIDATE},
        "request_digest": "d" * 64,
        "candidate_hash": CANDIDATE,
        "reconstruction_mode": records.RECONSTRUCTION_SNAPSHOT,
        # The digest of the snapshot this task reconstructs from - the same
        # identity the accepted descriptor binds (P1-REV-005).
        "candidate_material_digest": serialize.digest(snapshot_record()),
        "review_context_hash": "f" * 64,
        "effective_policy_hash": "0" * 64,
        "accepted_generation": 1,
    }
    record.update(overrides)
    return record


class ProvenanceRecordTests(unittest.TestCase):
    def test_snapshot_round_trips_canonically(self) -> None:
        record = snapshot_record()
        parsed = records.CandidateSnapshot.from_record(record, "snapshot")
        self.assertEqual(record, parsed.to_record())
        self.assertTrue(serialize.canonical_roundtrips(record))

    def test_task_input_round_trips_canonically(self) -> None:
        record = task_input_record()
        parsed = records.TaskInput.from_record(record, "task input")
        self.assertEqual(record, parsed.to_record())
        self.assertTrue(serialize.canonical_roundtrips(record))

    def test_canonical_bytes_do_not_depend_on_key_order(self) -> None:
        record = snapshot_record()
        shuffled = {key: record[key] for key in reversed(list(record))}
        self.assertEqual(serialize.canonical_text(record), serialize.canonical_text(shuffled))
        self.assertEqual(serialize.digest(record), serialize.digest(shuffled))

    def test_a_snapshot_with_no_material_is_refused(self) -> None:
        """A digest is never reconstruction material."""
        with self.assertRaises(ValidationError) as caught:
            records.CandidateSnapshot.from_record(snapshot_record(material={}), "snapshot")
        self.assertIn("not reconstruction material", str(caught.exception))

    def test_builder_mode_needs_identity_version_and_inputs(self) -> None:
        records.CandidateSnapshot.from_record(builder_record(), "snapshot")
        for broken in (
            {"builder_identity": "b", "builder_version": "1", "inputs": []},
            {"builder_identity": "b", "builder_version": "1"},
        ):
            with self.assertRaises(ValidationError):
                records.CandidateSnapshot.from_record(builder_record(builder=broken), "snapshot")

    def test_builder_mode_may_not_also_carry_snapshot_material(self) -> None:
        with self.assertRaises(ValidationError):
            records.CandidateSnapshot.from_record(builder_record(material={"x": "y"}), "snapshot")

    def test_task_input_needs_a_request_envelope(self) -> None:
        with self.assertRaises(ValidationError):
            records.TaskInput.from_record(task_input_record(request_envelope={}), "task input")

    def test_unknown_field_is_not_dropped(self) -> None:
        record = task_input_record()
        record["provider_job_handle"] = "runtime-only"
        with self.assertRaises(ValidationError) as caught:
            records.TaskInput.from_record(record, "task input")
        self.assertIn("unknown field", str(caught.exception))


class ProvenanceDigestTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.review = ReviewStore(self.store)
        self.controller = MutationController(self.store)
        lock = project_operation(self.store, "review-provenance-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)

    def _create(self, relative: str, record: dict) -> None:
        """Lay a Review record down. Through the immutable create where the platform supports it; where the create is
        fail-closed (POSIX), place the same canonical bytes directly, so these provenance-digest tests still exercise
        the reader on POSIX. The create boundary itself is covered by test_review_safe_create."""
        text = serialize.canonical_text(record)
        if CREATE_SUPPORTED:
            mutation = self.controller.open(
                "start", {"operation": "review-provenance", "path": relative}, WriteScope(files=(relative,))
            )
            mutation.add_effects("review", [Effect.create_file(relative, text)])
            mutation.apply()
            mutation.complete()
        else:
            target = self.store.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="")

    def test_material_digest_is_over_the_stored_snapshot_bytes(self) -> None:
        record = snapshot_record()
        self._create(paths.candidate_snapshot_rel(CANDIDATE), record)
        self.assertEqual(serialize.digest(record), self.review.candidate_material_digest(CANDIDATE))

    def test_task_input_digest_is_over_the_stored_task_input_bytes(self) -> None:
        record = task_input_record()
        self._create(paths.task_input_rel(TASK_ID), record)
        self.assertEqual(serialize.digest(record), self.review.task_input_digest(TASK_ID))

    def test_same_candidate_hash_with_different_snapshot_bytes_is_different_provenance(self) -> None:
        """``R3`` §5: equal results do not make equal reconstruction."""
        first = snapshot_record()
        second = snapshot_record(material={"paths": [{"path": "src/a.py", "mode": "100755", "object": "b" * 40}]})
        self.assertEqual(first["candidate_hash"], second["candidate_hash"])
        self.assertNotEqual(serialize.digest(first), serialize.digest(second))

    def test_builder_version_change_is_material(self) -> None:
        first = builder_record()
        second = builder_record(
            builder={"builder_identity": "roadmap-projection", "builder_version": "1.3.0", "inputs": [{"name": "plan", "identity": "c" * 64}]}
        )
        self.assertNotEqual(serialize.digest(first), serialize.digest(second))

    def test_builder_input_identity_change_is_material(self) -> None:
        first = builder_record()
        second = builder_record(
            builder={"builder_identity": "roadmap-projection", "builder_version": "1.2.0", "inputs": [{"name": "plan", "identity": "9" * 64}]}
        )
        self.assertNotEqual(serialize.digest(first), serialize.digest(second))

    def test_provenance_survives_runtime_loss(self) -> None:
        """Canonical provenance is what a clone rebuilds from; runtime is not."""
        self._create(paths.candidate_snapshot_rel(CANDIDATE), snapshot_record())
        self._create(paths.task_input_rel(TASK_ID), task_input_record())
        runtime = self.store.root / paths.RUNTIME_REVIEW_DIR
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "job-handle.json").write_text('{"provider":"x"}', encoding="utf-8")
        import shutil

        # What a clone or a runtime cleanup takes away: the ephemeral Review
        # area, provider job handle and all.
        shutil.rmtree(runtime)
        self.assertFalse(runtime.exists())
        self.assertEqual(CANDIDATE, self.review.read_candidate_snapshot(CANDIDATE).candidate_hash)
        self.assertEqual(TASK_ID, self.review.read_task_input(TASK_ID).task_id)

    def test_missing_canonical_provenance_fails_closed(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            self.review.read_task_input(TASK_ID)
        self.assertEqual("review_record_missing", caught.exception.code)

    def test_filename_must_match_the_identity_inside(self) -> None:
        other = "rtk_01ARZ3NDEKTSV4RRFFQ69G5FAW"
        self._create(paths.task_input_rel(other), task_input_record())
        with self.assertRaises(ValidationError) as caught:
            self.review.read_task_input(other)
        self.assertIn("not the one its filename names", str(caught.exception))

    def test_accepted_task_provenance_mismatch_fails_validation(self) -> None:
        """A gate that bound one provenance digest and stores another is reported."""
        from test_review_gate_generation import gate_record

        snapshot = snapshot_record()
        task_input = task_input_record()
        self._create(paths.candidate_snapshot_rel(CANDIDATE), snapshot)
        self._create(paths.task_input_rel(TASK_ID), task_input)
        accepted = {
            "task_id": TASK_ID,
            "task_slot": "primary",
            "task_kind": "formal_review",
            "reviewer_identity": "reviewer-a",
            "reviewer_version": "3.1",
            "candidate_hash": CANDIDATE,
            "candidate_material_digest": "9" * 64,  # not what the stored snapshot digests to
            "reconstruction_mode": records.RECONSTRUCTION_SNAPSHOT,
            "request_digest": task_input["request_digest"],
            "task_input_digest": serialize.digest(task_input),
            "review_context_hash": task_input["review_context_hash"],
            "effective_policy_hash": task_input["effective_policy_hash"],
        }
        record = gate_record(1, candidate_hash=CANDIDATE, accepted_tasks=[accepted])
        self._create(paths.gate_rel(RUN_ID, 1), record)
        codes = [p.code for p in validate_project(self.store)]
        self.assertIn("review_provenance_conflict", codes)


if __name__ == "__main__":
    unittest.main()
