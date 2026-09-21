"""R1: canonical Review layout, the immutable create-only writer, and write-time containment."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest import mock

from helpers import WorklineTestCase, git
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.mutation import MATCHING, MISMATCH, UNAPPLIED, Effect, MutationController, WriteScope
from workline.oplock import project_operation
from workline.review import ReviewStore, paths, records, serialize
from workline.review.gate import require_committable
from workline.store import WORKLINE_DIR
from workline.validate import validate_project

RUN_ID = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"
RECEIPT_ID = "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV"


def receipt_record(receipt_id: str = RECEIPT_ID, **overrides: object) -> dict:
    record = {
        "schema": records.SCHEMA_RECEIPT,
        "version": records.VERSION,
        "receipt_id": receipt_id,
        "review_run_id": RUN_ID,
        "review_generation": 1,
        "review_kind": "work_formal",
        "target_identity": "w_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "operation_identity": "start",
        "authorized_candidate_hash": "a" * 64,
        "review_context_hash": "b" * 64,
        "effective_policy_hash": "c" * 64,
        "coverage_hash": "d" * 64,
        "adjudication_hash": "e" * 64,
        "obligation_digest": "f" * 64,
        "unresolved_obligations": 0,
        "authorized_operation_stage": "work-terminal",
    }
    record.update(overrides)
    return record


class ReviewLayoutTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.review = ReviewStore(self.store)
        self.controller = MutationController(self.store)
        lock = project_operation(self.store, "review-layout-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)

    def _mutation(self, relative: str):
        return self.controller.open(
            "start", {"operation": "review-test", "path": relative}, WriteScope(files=(relative,))
        )

    def _create(self, relative: str, record: dict):
        mutation = self._mutation(relative)
        mutation.add_effects("review", [Effect.create_file(relative, serialize.canonical_text(record))])
        mutation.apply()
        return mutation

    # lazy namespace ---------------------------------------------------------
    def test_project_with_no_review_namespace_is_valid(self) -> None:
        self.assertFalse(self.review.exists())
        self.assertEqual([], [p.code for p in validate_project(self.store)])

    def test_project_start_creates_no_review_directories(self) -> None:
        """Empty canonical directories are not clone-safe state, so none is bootstrapped."""
        self.assertFalse((self.store.root / paths.REVIEW_DIR).exists())
        for name in paths.REVIEW_SUBDIRS:
            self.assertFalse((self.store.root / paths.REVIEW_DIR / name).exists())

    def test_first_review_write_creates_parents_lazily(self) -> None:
        relative = paths.receipt_rel(RECEIPT_ID)
        self._create(relative, receipt_record())
        self.assertTrue((self.store.root / relative).is_file())
        self.assertTrue(self.review.exists())
        self.assertEqual(RECEIPT_ID, self.review.read_receipt(RECEIPT_ID).receipt_id)

    def test_review_record_holds_exactly_the_canonical_bytes(self) -> None:
        relative = paths.receipt_rel(RECEIPT_ID)
        record = receipt_record()
        self._create(relative, record)
        stored = (self.store.root / relative).read_bytes()
        self.assertEqual(serialize.canonical_bytes(record), stored)
        self.assertNotIn(b"\r\n", stored)

    # immutable create-only --------------------------------------------------
    def test_exact_replay_is_matching_and_writes_nothing_again(self) -> None:
        relative = paths.receipt_rel(RECEIPT_ID)
        text = serialize.canonical_text(receipt_record())
        mutation = self._mutation(relative)
        mutation.add_effects("review", [Effect.create_file(relative, text)])
        mutation.apply()
        outcomes = mutation.apply()
        self.assertEqual([MATCHING], [classification for _, classification in outcomes])

    def test_absent_target_is_unapplied(self) -> None:
        relative = paths.receipt_rel(RECEIPT_ID)
        record = {"kind": "create_file", "payload": {"path": relative, "content": "a: 1\n"}}
        self.assertEqual(UNAPPLIED, self.controller.classify(record))

    def test_different_bytes_at_the_target_reconcile(self) -> None:
        relative = paths.receipt_rel(RECEIPT_ID)
        mutation = self._mutation(relative)
        mutation.add_effects("review", [Effect.create_file(relative, serialize.canonical_text(receipt_record()))])
        target = self.store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("someone: else\n", encoding="utf-8")
        with self.assertRaises(ReconcileRequired):
            mutation.apply()
        self.assertEqual("someone: else\n", target.read_text(encoding="utf-8"))

    def test_a_directory_where_the_record_belongs_is_a_mismatch(self) -> None:
        relative = paths.receipt_rel(RECEIPT_ID)
        (self.store.root / relative).mkdir(parents=True)
        record = {"kind": "create_file", "payload": {"path": relative, "content": "a: 1\n"}}
        self.assertEqual(MISMATCH, self.controller.classify(record))

    def test_create_file_takes_no_base(self) -> None:
        mutation = self._mutation(paths.receipt_rel(RECEIPT_ID))
        effect = Effect("create_file", {"path": paths.receipt_rel(RECEIPT_ID), "content": "a: 1\n", "base": "x"})
        with self.assertRaises(ValidationError) as caught:
            mutation.add_effects("review", [effect])
        self.assertIn("immutable", str(caught.exception))

    def test_write_file_cannot_touch_a_canonical_review_path(self) -> None:
        """The generic update primitive is mechanically kept away from immutable records."""
        relative = paths.receipt_rel(RECEIPT_ID)
        mutation = self._mutation(relative)
        with self.assertRaises(ValidationError) as caught:
            mutation.add_effects("review", [Effect.write_file(relative, "a: 1\n")])
        self.assertIn("create_file", str(caught.exception))

    def test_create_file_only_writes_review_paths(self) -> None:
        relative = f"{WORKLINE_DIR}/works/w_01ARZ3NDEKTSV4RRFFQ69G5FAV.md"
        mutation = self._mutation(relative)
        with self.assertRaises(ValidationError) as caught:
            mutation.add_effects("review", [Effect.create_file(relative, "x")])
        self.assertIn("canonical Review records", str(caught.exception))

    def test_runtime_review_is_not_canonical(self) -> None:
        """``.workline/runtime/review`` is outside the canonical namespace entirely."""
        self.assertFalse(paths.is_review_path(f"{paths.RUNTIME_REVIEW_DIR}/scratch.yaml"))
        mutation = self._mutation(f"{paths.RUNTIME_REVIEW_DIR}/scratch.yaml")
        with self.assertRaises(ValidationError):
            mutation.add_effects("review", [Effect.create_file(f"{paths.RUNTIME_REVIEW_DIR}/scratch.yaml", "x")])

    # containment / no-follow ------------------------------------------------
    @unittest.skipUnless(hasattr(os, "symlink"), "no symlink support")
    def test_symlinked_parent_is_refused(self) -> None:
        outside = self.tmp / "outside"
        outside.mkdir()
        review = self.store.root / paths.REVIEW_DIR
        review.mkdir(parents=True)
        try:
            (review / "receipts").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:  # Windows without developer mode
            self.skipTest(f"cannot create a directory symlink here: {exc}")
        relative = paths.receipt_rel(RECEIPT_ID)
        mutation = self._mutation(relative)
        mutation.add_effects("review", [Effect.create_file(relative, "a: 1\n")])
        with self.assertRaises(ValidationError) as caught:
            mutation.apply()
        self.assertEqual("review_containment", caught.exception.code)
        self.assertFalse((outside / f"{RECEIPT_ID}.yaml").exists())

    @unittest.skipUnless(sys.platform == "win32", "junctions are a Windows reparse point")
    def test_a_junctioned_parent_is_refused(self) -> None:
        """A junction is ``is_dir()`` and not ``is_symlink()`` - only its reparse tag gives it away.

        Needs no developer mode, unlike a directory symlink, so this is the
        Windows reparse branch actually exercised on an ordinary machine. A
        check that asked only "is it a directory and not a symlink?" would
        follow this and write the record outside the Project.
        """
        import subprocess

        outside = self.tmp / "outside"
        outside.mkdir()
        review = self.store.root / paths.REVIEW_DIR
        review.mkdir(parents=True)
        link = review / "receipts"
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True, text=True)
        if made.returncode != 0:
            self.skipTest(f"cannot create a junction here: {made.stderr.strip() or made.stdout.strip()}")
        self.addCleanup(lambda: os.rmdir(link) if os.path.lexists(link) else None)  # the junction, never its target
        self.assertTrue(link.is_dir())
        self.assertFalse(link.is_symlink())
        relative = paths.receipt_rel(RECEIPT_ID)
        mutation = self._mutation(relative)
        mutation.add_effects("review", [Effect.create_file(relative, "a: 1\n")])
        with self.assertRaises(ValidationError) as caught:
            mutation.apply()
        self.assertEqual("review_containment", caught.exception.code)
        self.assertEqual([], list(outside.iterdir()))

    def test_a_file_where_a_review_directory_belongs_is_refused(self) -> None:
        review = self.store.root / paths.REVIEW_DIR
        review.mkdir(parents=True)
        (review / "receipts").write_text("not a directory\n", encoding="utf-8")
        relative = paths.receipt_rel(RECEIPT_ID)
        mutation = self._mutation(relative)
        mutation.add_effects("review", [Effect.create_file(relative, "a: 1\n")])
        with self.assertRaises(ValidationError) as caught:
            mutation.apply()
        self.assertEqual("review_containment", caught.exception.code)

    def test_parent_replaced_between_proof_and_write_is_refused(self) -> None:
        """TOCTOU: the identity proven by the walk is taken again at the create boundary."""
        relative = paths.receipt_rel(RECEIPT_ID)
        parent = self.store.root / paths.RECEIPTS_DIR
        parent.mkdir(parents=True)
        mutation = self._mutation(relative)
        mutation.add_effects("review", [Effect.create_file(relative, "a: 1\n")])

        real = paths.prove_containment

        def swap(root, rel):
            identity = real(root, rel)
            # Between the proof and the write, the proven directory is replaced
            # by a different one.
            parent.rmdir()
            parent.mkdir()
            return identity

        with mock.patch.object(paths, "prove_containment", swap):
            with self.assertRaises(ValidationError) as caught:
                mutation.apply()
        self.assertEqual("review_containment", caught.exception.code)
        self.assertFalse((self.store.root / relative).exists())

    def test_containment_refuses_a_path_outside_the_review_namespace(self) -> None:
        with self.assertRaises(ValidationError):
            paths.prove_containment(self.store.root, f"{WORKLINE_DIR}/project.yaml")

    def test_containment_refuses_traversal(self) -> None:
        with self.assertRaises(ValidationError):
            paths.prove_containment(self.store.root, f"{paths.REVIEW_DIR}/../escape.yaml")

    # git committability preflight -------------------------------------------
    def test_ignored_review_path_stops_before_any_effect(self) -> None:
        (self.store.root / ".gitignore").write_text(f"{paths.REVIEW_DIR}/\n", encoding="utf-8")
        with self.assertRaises(StopError) as caught:
            require_committable(self.store, [paths.receipt_rel(RECEIPT_ID)])
        self.assertEqual("review_path_ignored", caught.exception.code)

    def test_committable_review_path_passes(self) -> None:
        require_committable(self.store, [paths.receipt_rel(RECEIPT_ID)])

    def test_undeterminable_committability_stops(self) -> None:
        with mock.patch("workline.review.gate.gitcmd.is_ignored", return_value=None):
            with self.assertRaises(StopError) as caught:
                require_committable(self.store, [paths.receipt_rel(RECEIPT_ID)])
        self.assertEqual("review_committability_unknown", caught.exception.code)

    # namespace validation ---------------------------------------------------
    def test_unknown_entry_in_the_namespace_fails_validation(self) -> None:
        (self.store.root / paths.REVIEW_DIR).mkdir(parents=True)
        (self.store.root / paths.REVIEW_DIR / "stray.yaml").write_text("x: 1\n", encoding="utf-8")
        codes = [p.code for p in validate_project(self.store)]
        self.assertIn("review_namespace_invalid", codes)

    def test_malformed_record_fails_validation(self) -> None:
        relative = paths.receipt_rel(RECEIPT_ID)
        target = self.store.root / relative
        target.parent.mkdir(parents=True)
        target.write_text("schema: review-authorization-receipt\nversion: 1\n", encoding="utf-8")
        codes = [p.code for p in validate_project(self.store)]
        self.assertIn("review_record_invalid", codes)

    def test_filename_that_is_not_an_id_fails_validation(self) -> None:
        directory = self.store.root / paths.RECEIPTS_DIR
        directory.mkdir(parents=True)
        (directory / "not-an-id.yaml").write_text("x: 1\n", encoding="utf-8")
        codes = [p.code for p in validate_project(self.store)]
        self.assertIn("review_namespace_invalid", codes)

    def test_review_records_do_not_make_the_project_invalid(self) -> None:
        self._create(paths.receipt_rel(RECEIPT_ID), receipt_record())
        # The Receipt names a Review Run with no gate chain, which Review
        # validation reports - and nothing about the Project's own structure.
        codes = {p.code for p in validate_project(self.store)}
        self.assertTrue(codes <= {"review_record_missing"}, codes)


if __name__ == "__main__":
    unittest.main()
