"""P1-REV-008: every physical entry in the Review namespace is enumerated and structurally validated.

The structural validator already reads ``gates/``, ``receipts/``,
``consumptions/`` and ``supersessions/`` in full. This covers the three that
were only ever read by reference before - ``candidate-snapshots/``,
``task-inputs/`` and ``activation/`` - so an unreferenced record that is
malformed, non-canonical, misnamed or an indirection fails closed instead of
being missed because nothing happened to point at it.

A valid but unreferenced record is a legal orphan (crash/recovery, immutable
write ordering) and is simply validated, never condemned: no reachability or
garbage-collection policy is introduced here.

Written directly to disk (not through the immutable create), so these run
identically on Windows and on POSIX, where the create itself is fail-closed.
Indirection is exercised with a real junction on Windows and a real symlink on
POSIX.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest

from helpers import WorklineTestCase
from workline.review import ReviewStore, paths, records, serialize
from workline.validate import validate_project

from test_review_provenance import CANDIDATE, TASK_ID, snapshot_record, task_input_record

WINDOWS = sys.platform == "win32"
OTHER_CANDIDATE = "b" * 64
OTHER_TASK = "rtk_01ARZ3NDEKTSV4RRFFQ69G5FAW"


def activation_record(**overrides: object) -> dict:
    record = {
        "schema": records.SCHEMA_ACTIVATION,
        "version": records.VERSION,
        "operation_contract": records.OPERATION_CONTRACT_REVIEW_V1,
        "legacy_event_count": 0,
        "legacy_event_prefix_sha256": "0" * 64,
        "activation_base_head": "a" * 40,
    }
    record.update(overrides)
    return record


def make_junction(link: Path, target: Path) -> bool:
    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
    return made.returncode == 0


def make_indirection(link: Path, target: Path, *, directory: bool) -> bool:
    """A real reparse point at ``link``: a junction on Windows, a symlink on POSIX. False if the OS refuses."""
    if WINDOWS:
        return directory and make_junction(link, target)  # file reparse points need a privilege this account lacks
    try:
        link.symlink_to(target, target_is_directory=directory)
        return True
    except (OSError, NotImplementedError):
        return False


class NamespaceEnumerationTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.review = ReviewStore(self.store)
        self.outside = self.tmp / "outside"
        self.outside.mkdir()

    def _put_bytes(self, relative: str, data: bytes) -> Path:
        target = self.store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def _put(self, relative: str, record: dict) -> Path:
        return self._put_bytes(relative, serialize.canonical_bytes(record))

    def _codes(self) -> list[str]:
        return [problem.code for problem in validate_project(self.store)]

    # candidate-snapshots ----------------------------------------------------
    def test_valid_unreferenced_candidate_snapshot_passes(self) -> None:
        self._put(paths.candidate_snapshot_rel(CANDIDATE), snapshot_record())
        self.assertEqual([], self._codes(), "a structurally valid orphan snapshot is not a problem")

    def test_malformed_unreferenced_candidate_snapshot_fails(self) -> None:
        # Canonical bytes of an incomplete record: what is refused is the schema, not the line endings.
        self._put(paths.candidate_snapshot_rel(CANDIDATE),
                  {"schema": records.SCHEMA_CANDIDATE_SNAPSHOT, "version": records.VERSION})
        self.assertIn("review_record_invalid", self._codes())

    def test_noncanonical_unreferenced_candidate_snapshot_fails(self) -> None:
        canonical = serialize.canonical_text(snapshot_record())
        self._put_bytes(paths.candidate_snapshot_rel(CANDIDATE), canonical.replace("\n", "\r\n").encode("utf-8"))
        self.assertIn("review_record_noncanonical", self._codes())

    def test_candidate_snapshot_filename_content_mismatch_fails(self) -> None:
        # Filename names OTHER_CANDIDATE; the record inside declares CANDIDATE.
        self._put(paths.candidate_snapshot_rel(OTHER_CANDIDATE), snapshot_record())
        self.assertIn("review_record_invalid", self._codes())

    def test_candidate_snapshot_filename_that_is_not_a_hash_fails(self) -> None:
        (self.store.root / paths.CANDIDATE_SNAPSHOTS_DIR).mkdir(parents=True)
        self._put_bytes(f"{paths.CANDIDATE_SNAPSHOTS_DIR}/not-a-hash.yaml", b"x: 1\n")
        self.assertIn("review_namespace_invalid", self._codes())

    def test_candidate_snapshot_indirection_fails(self) -> None:
        (self.store.root / paths.CANDIDATE_SNAPSHOTS_DIR).mkdir(parents=True)
        link = self.store.root / paths.candidate_snapshot_rel(CANDIDATE)
        if not make_indirection(link, self.outside, directory=True):
            self.skipTest("cannot create a reparse point here")
        self.addCleanup(self._remove_indirection, link)
        self.assertIn("review_containment", self._codes())

    # task-inputs ------------------------------------------------------------
    def test_valid_unreferenced_task_input_passes(self) -> None:
        self._put(paths.task_input_rel(TASK_ID), task_input_record())
        self.assertEqual([], self._codes())

    def test_malformed_unreferenced_task_input_fails(self) -> None:
        self._put(paths.task_input_rel(TASK_ID),
                  {"schema": records.SCHEMA_TASK_INPUT, "version": records.VERSION})
        self.assertIn("review_record_invalid", self._codes())

    def test_noncanonical_unreferenced_task_input_fails(self) -> None:
        canonical = serialize.canonical_text(task_input_record())
        self._put_bytes(paths.task_input_rel(TASK_ID), canonical.replace("\n", "\r\n").encode("utf-8"))
        self.assertIn("review_record_noncanonical", self._codes())

    def test_task_input_filename_content_mismatch_fails(self) -> None:
        self._put(paths.task_input_rel(OTHER_TASK), task_input_record())
        self.assertIn("review_record_invalid", self._codes())

    def test_task_input_filename_that_is_not_an_id_fails(self) -> None:
        (self.store.root / paths.TASK_INPUTS_DIR).mkdir(parents=True)
        self._put_bytes(f"{paths.TASK_INPUTS_DIR}/not-an-id.yaml", b"x: 1\n")
        self.assertIn("review_namespace_invalid", self._codes())

    def test_task_input_indirection_fails(self) -> None:
        (self.store.root / paths.TASK_INPUTS_DIR).mkdir(parents=True)
        link = self.store.root / paths.task_input_rel(TASK_ID)
        if not make_indirection(link, self.outside, directory=True):
            self.skipTest("cannot create a reparse point here")
        self.addCleanup(self._remove_indirection, link)
        self.assertIn("review_containment", self._codes())

    def test_a_nested_directory_in_task_inputs_fails(self) -> None:
        (self.store.root / paths.TASK_INPUTS_DIR / "nested").mkdir(parents=True)
        self.assertIn("review_namespace_invalid", self._codes())

    # activation -------------------------------------------------------------
    def test_empty_activation_directory_passes(self) -> None:
        (self.store.root / paths.ACTIVATION_DIR).mkdir(parents=True)
        self.assertEqual([], self._codes())
        self.assertIsNone(self.review.read_activation(), "an absent record means Work-terminal review is not activated")

    def test_valid_activation_record_is_structurally_valid_but_does_not_activate(self) -> None:
        self._put(paths.WORK_TERMINAL_ACTIVATION_REL, activation_record())
        self.assertEqual([], self._codes(), "a well-formed activation record is structurally valid")
        # It is read and validated, but nothing here consumes it: P1 activates no
        # START, Roadmap or P3 behavior from its presence.
        self.assertIsNotNone(self.review.read_activation())

    def test_malformed_activation_record_fails(self) -> None:
        self._put(paths.WORK_TERMINAL_ACTIVATION_REL,
                  {"schema": records.SCHEMA_ACTIVATION, "version": records.VERSION})
        self.assertIn("review_record_invalid", self._codes())

    def test_noncanonical_activation_record_fails(self) -> None:
        canonical = serialize.canonical_text(activation_record())
        self._put_bytes(paths.WORK_TERMINAL_ACTIVATION_REL, canonical.replace("\n", "\r\n").encode("utf-8"))
        self.assertIn("review_record_noncanonical", self._codes())

    def test_unknown_entry_in_activation_fails(self) -> None:
        self._put_bytes(f"{paths.ACTIVATION_DIR}/unknown.yaml", b"x: 1\n")
        self.assertIn("review_namespace_invalid", self._codes())

    def test_a_nested_directory_in_activation_fails(self) -> None:
        (self.store.root / paths.ACTIVATION_DIR / "nested").mkdir(parents=True)
        self.assertIn("review_namespace_invalid", self._codes())

    def test_the_activation_name_as_a_directory_fails(self) -> None:
        (self.store.root / paths.WORK_TERMINAL_ACTIVATION_REL).mkdir(parents=True)
        self.assertIn("review_namespace_invalid", self._codes())

    def test_activation_record_as_an_indirection_fails(self) -> None:
        (self.store.root / paths.ACTIVATION_DIR).mkdir(parents=True)
        victim = self.outside / "work-terminal-v1.yaml"
        victim.write_bytes(serialize.canonical_bytes(activation_record()))
        link = self.store.root / paths.WORK_TERMINAL_ACTIVATION_REL
        # a junction is a directory reparse point, so point it at a directory on Windows
        if WINDOWS:
            if not make_junction(link, self.outside):
                self.skipTest("cannot create a junction here")
        elif not make_indirection(link, victim, directory=False):
            self.skipTest("cannot create a symlink here")
        self.addCleanup(self._remove_indirection, link)
        self.assertIn("review_containment", self._codes())

    @staticmethod
    def _remove_indirection(link: Path) -> None:
        if os.path.islink(link):
            os.unlink(link)
        elif getattr(os.path, "isjunction", lambda _: False)(link):
            os.rmdir(link)


if __name__ == "__main__":
    unittest.main()
