"""R1 §12 / R3 §3 / R3 §10: pre-project residue, the Git persistence boundary, and settlement."""

from __future__ import annotations

import unittest

from helpers import WorklineTestCase, git
from workline.errors import StopError, ValidationError
from workline.project_start import project_start
from workline.review import paths, records, serialize
from workline.review.gate import require_persisted, validate_settlement
from workline.store import WORKLINE_DIR

from test_review_authorization import accepted_task, settled_task
from test_review_gate_generation import RUN_ID, gate_record
from test_review_provenance import CANDIDATE, TASK_ID, snapshot_record, task_input_record

from helpers import WORKLINE_ROOT


class PreProjectResidueTests(WorklineTestCase):
    """``R1`` §12: a pre-existing Review namespace is not adopted by guess."""

    def test_a_pre_existing_review_namespace_is_not_adopted(self) -> None:
        root = self.new_dir()
        stray = root / paths.RECEIPTS_DIR
        stray.mkdir(parents=True)
        (stray / "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV.yaml").write_text("schema: x\n", encoding="utf-8")
        with self.assertRaises(StopError) as caught:
            project_start(root, WORKLINE_ROOT)
        # Refused as unrecognised pre-project state, not taken over.
        self.assertIn("review", str(caught.exception))
        self.assertEqual("schema: x\n", (stray / "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV.yaml").read_text(encoding="utf-8"))

    def test_project_start_still_works_with_no_review_namespace(self) -> None:
        root = self.new_dir("clean")
        project_start(root, WORKLINE_ROOT)
        self.assertFalse((root / paths.REVIEW_DIR).exists())


class PersistenceBoundaryTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()

    def _write(self, relative: str, record: dict) -> None:
        target = self.store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialize.canonical_text(record), encoding="utf-8", newline="")

    def _commit(self, relative: str) -> None:
        git(self.store.root, "add", "--", relative)
        git(self.store.root, "commit", "-m", f"add {relative}")

    def test_an_uncommitted_review_record_does_not_cross_the_boundary(self) -> None:
        relative = paths.task_input_rel(TASK_ID)
        self._write(relative, task_input_record())
        with self.assertRaises(StopError) as caught:
            require_persisted(self.store, [relative])
        self.assertEqual("review_not_persisted", caught.exception.code)

    def test_a_committed_review_record_crosses_the_boundary(self) -> None:
        relative = paths.task_input_rel(TASK_ID)
        self._write(relative, task_input_record())
        self._commit(relative)
        require_persisted(self.store, [relative])

    def test_a_committed_record_edited_since_does_not_cross(self) -> None:
        """HEAD holding the path is not enough: a clone would get the committed bytes."""
        relative = paths.task_input_rel(TASK_ID)
        self._write(relative, task_input_record())
        self._commit(relative)
        (self.store.root / relative).write_text("tampered: true\n", encoding="utf-8")
        with self.assertRaises(StopError) as caught:
            require_persisted(self.store, [relative])
        self.assertEqual("review_not_persisted", caught.exception.code)

    def test_an_undeterminable_answer_stops(self) -> None:
        from unittest import mock

        relative = paths.task_input_rel(TASK_ID)
        self._write(relative, task_input_record())
        with mock.patch("workline.review.gate.gitcmd.head_paths", return_value=None):
            with self.assertRaises(StopError) as caught:
                require_persisted(self.store, [relative])
        self.assertEqual("review_persistence_unknown", caught.exception.code)


class SettlementTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self._write(paths.candidate_snapshot_rel(CANDIDATE), snapshot_record())
        self._write(paths.task_input_rel(TASK_ID), task_input_record())

    def _write(self, relative: str, record: dict) -> None:
        target = self.store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialize.canonical_text(record), encoding="utf-8", newline="")

    def _accepting_chain(self) -> None:
        self._write(
            paths.gate_rel(RUN_ID, 1),
            gate_record(1, candidate_hash=CANDIDATE, accepted_tasks=[accepted_task()]),
        )

    def test_a_result_for_an_accepted_task_validates(self) -> None:
        self._accepting_chain()
        found = validate_settlement(self.store, RUN_ID, TASK_ID, "7" * 64, "reviewer-a")
        self.assertEqual(TASK_ID, found["task_id"])

    def test_a_result_for_an_unknown_run_is_refused(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            validate_settlement(self.store, RUN_ID, TASK_ID, "7" * 64, "reviewer-a")
        self.assertEqual("review_callback_unknown", caught.exception.code)

    def test_a_result_for_a_task_never_accepted_is_refused(self) -> None:
        self._write(paths.gate_rel(RUN_ID, 1), gate_record(1, candidate_hash=CANDIDATE))
        with self.assertRaises(ValidationError) as caught:
            validate_settlement(self.store, RUN_ID, TASK_ID, "7" * 64, "reviewer-a")
        self.assertEqual("review_callback_unknown", caught.exception.code)

    def test_an_exactly_duplicated_settlement_is_idempotent(self) -> None:
        first = gate_record(1, candidate_hash=CANDIDATE, accepted_tasks=[accepted_task()])
        self._write(paths.gate_rel(RUN_ID, 1), first)
        self._write(
            paths.gate_rel(RUN_ID, 2),
            gate_record(
                2,
                previous_digest=serialize.digest(first),
                candidate_hash=CANDIDATE,
                accepted_tasks=[accepted_task()],
                settled_tasks=[settled_task()],
            ),
        )
        found = validate_settlement(self.store, RUN_ID, TASK_ID, "7" * 64, "reviewer-a")
        self.assertEqual(TASK_ID, found["task_id"])

    def test_a_conflicting_second_result_is_refused(self) -> None:
        first = gate_record(1, candidate_hash=CANDIDATE, accepted_tasks=[accepted_task()])
        self._write(paths.gate_rel(RUN_ID, 1), first)
        self._write(
            paths.gate_rel(RUN_ID, 2),
            gate_record(
                2,
                previous_digest=serialize.digest(first),
                candidate_hash=CANDIDATE,
                accepted_tasks=[accepted_task()],
                settled_tasks=[settled_task()],
            ),
        )
        with self.assertRaises(ValidationError) as caught:
            validate_settlement(self.store, RUN_ID, TASK_ID, "9" * 64, "reviewer-a")
        self.assertEqual("review_callback_conflict", caught.exception.code)

    def test_a_missing_canonical_task_input_is_refused(self) -> None:
        self._accepting_chain()
        (self.store.root / paths.task_input_rel(TASK_ID)).unlink()
        with self.assertRaises(ValidationError) as caught:
            validate_settlement(self.store, RUN_ID, TASK_ID, "7" * 64, "reviewer-a")
        self.assertEqual("review_record_missing", caught.exception.code)

    def test_provenance_changed_since_acceptance_is_refused(self) -> None:
        self._accepting_chain()
        self._write(paths.task_input_rel(TASK_ID), task_input_record(task_slot="changed"))
        with self.assertRaises(ValidationError) as caught:
            validate_settlement(self.store, RUN_ID, TASK_ID, "7" * 64, "reviewer-a")
        self.assertEqual("review_provenance_conflict", caught.exception.code)

    def test_another_reviewer_answering_is_refused(self) -> None:
        self._accepting_chain()
        with self.assertRaises(ValidationError) as caught:
            validate_settlement(self.store, RUN_ID, TASK_ID, "7" * 64, "reviewer-b")
        self.assertEqual("review_callback_unknown", caught.exception.code)

    def test_a_runtime_job_handle_is_not_authority(self) -> None:
        """Only canonical material answers; a runtime handle cannot stand in for it."""
        self._accepting_chain()
        runtime = self.store.root / paths.RUNTIME_REVIEW_DIR
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "job.json").write_text('{"task": "%s"}' % TASK_ID, encoding="utf-8")
        (self.store.root / paths.task_input_rel(TASK_ID)).unlink()
        with self.assertRaises(ValidationError):
            validate_settlement(self.store, RUN_ID, TASK_ID, "7" * 64, "reviewer-a")


if __name__ == "__main__":
    unittest.main()
