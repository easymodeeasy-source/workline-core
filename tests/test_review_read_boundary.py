"""P1-REV-002 / P1-REV-007: readers refuse indirection, and accept only the canonical physical bytes.

The reader is held to the writer's rules. It walks the namespace with the same
handle-bound, no-follow opens - so a junction or symlink is refused, never
followed to records outside the Project - and it accepts a record only when the
stored bytes are exactly the canonical rendering of what they parse to.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest

from helpers import WorklineTestCase
from workline.errors import ValidationError
from workline.review import ReviewStore, paths, serialize
from workline.validate import validate_project

from test_review_authorization import RECEIPT_ID, receipt_record
from test_review_gate_generation import RUN_ID, gate_record

WINDOWS = sys.platform == "win32"


def make_junction(link: Path, target: Path) -> bool:
    return subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True).returncode == 0


def try_symlink(link: Path, target: Path, directory: bool) -> bool:
    try:
        link.symlink_to(target, target_is_directory=directory)
        return True
    except (OSError, NotImplementedError):
        return False


class ReaderNoFollowTests(WorklineTestCase):
    """P1-REV-002: nothing in the namespace is followed to somewhere else."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.review = ReviewStore(self.store)
        # A well-formed Review Run *outside* the Project - what an indirection
        # would lead a following reader to.
        self.outside = self.tmp / "outside"
        run = self.outside / RUN_ID
        run.mkdir(parents=True)
        (run / "000001.yaml").write_bytes(serialize.canonical_bytes(gate_record(1)))
        self.links: list[Path] = []
        self.addCleanup(self._unlink)

    def _unlink(self) -> None:
        for link in reversed(self.links):
            if os.path.lexists(link):
                os.rmdir(link) if WINDOWS else os.unlink(link)

    def _link_dir(self, link: Path, target: Path) -> None:
        made = make_junction(link, target) if WINDOWS else try_symlink(link, target, True)
        if not made:
            self.skipTest("cannot create a directory indirection here")
        self.links.append(link)

    def test_gates_directory_as_indirection_fails_validation(self) -> None:
        (self.store.root / paths.REVIEW_DIR).mkdir(parents=True)
        self._link_dir(self.store.root / paths.GATES_DIR, self.outside)
        codes = [p.code for p in validate_project(self.store)]
        self.assertIn("review_containment", codes)
        with self.assertRaises(ValidationError):
            self.review.run_ids()

    def test_a_run_directory_as_indirection_is_refused_by_gate_chain(self) -> None:
        (self.store.root / paths.GATES_DIR).mkdir(parents=True)
        self._link_dir(self.store.root / paths.GATES_DIR / RUN_ID, self.outside / RUN_ID)
        with self.assertRaises(ValidationError) as caught:
            self.review.gate_chain(RUN_ID)
        self.assertEqual("review_containment", caught.exception.code)
        self.assertIn("review_containment", [p.code for p in validate_project(self.store)])

    def test_the_review_namespace_itself_as_indirection_fails_validation(self) -> None:
        other = self.tmp / "other-review"
        (other / "gates" / RUN_ID).mkdir(parents=True)
        (other / "gates" / RUN_ID / "000001.yaml").write_bytes(serialize.canonical_bytes(gate_record(1)))
        self._link_dir(self.store.root / paths.REVIEW_DIR, other)
        self.assertIn("review_containment", [p.code for p in validate_project(self.store)])
        with self.assertRaises(ValidationError):
            self.review.exists()

    def test_a_record_parent_as_indirection_is_refused_when_reading_a_record(self) -> None:
        other = self.tmp / "other-receipts"
        other.mkdir()
        (other / f"{RECEIPT_ID}.yaml").write_bytes(serialize.canonical_bytes(receipt_record()))
        (self.store.root / paths.REVIEW_DIR).mkdir(parents=True)
        self._link_dir(self.store.root / paths.RECEIPTS_DIR, other)
        with self.assertRaises(ValidationError) as caught:
            self.review.read_receipt(RECEIPT_ID)
        self.assertEqual("review_containment", caught.exception.code)
        with self.assertRaises(ValidationError):
            self.review.receipt_exists(RECEIPT_ID)

    def test_the_activation_parent_as_indirection_is_refused(self) -> None:
        other = self.tmp / "other-activation"
        other.mkdir()
        (self.store.root / paths.REVIEW_DIR).mkdir(parents=True)
        self._link_dir(self.store.root / paths.ACTIVATION_DIR, other)
        with self.assertRaises(ValidationError):
            self.review.read_activation()

    @unittest.skipIf(WINDOWS, "file symlinks need a privilege this Windows account does not hold")
    def test_a_record_file_as_symlink_is_refused(self) -> None:
        victim = self.tmp / "victim.yaml"
        victim.write_bytes(serialize.canonical_bytes(receipt_record()))
        (self.store.root / paths.RECEIPTS_DIR).mkdir(parents=True)
        self.assertTrue(try_symlink(self.store.root / paths.receipt_rel(RECEIPT_ID), victim, False))
        with self.assertRaises(ValidationError) as caught:
            self.review.read_receipt(RECEIPT_ID)
        self.assertEqual("review_containment", caught.exception.code)
        self.assertIn("review_containment", [p.code for p in validate_project(self.store)])

    def test_a_directory_where_a_record_belongs_is_refused(self) -> None:
        (self.store.root / paths.receipt_rel(RECEIPT_ID)).mkdir(parents=True)
        with self.assertRaises(ValidationError):
            self.review.read_receipt(RECEIPT_ID)
        self.assertTrue([p for p in validate_project(self.store)])


class CanonicalBytesTests(WorklineTestCase):
    """P1-REV-007: a record is read only in the one representation the writer produces."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.review = ReviewStore(self.store)
        self.record = receipt_record()
        self.canonical = serialize.canonical_text(self.record)
        self.target = self.store.root / paths.receipt_rel(RECEIPT_ID)
        self.target.parent.mkdir(parents=True)

    def _store(self, raw: bytes) -> None:
        self.target.write_bytes(raw)

    def _refused(self, raw: bytes) -> ValidationError:
        self._store(raw)
        with self.assertRaises(ValidationError) as caught:
            self.review.read_receipt(RECEIPT_ID)
        return caught.exception

    def test_canonical_bytes_are_read(self) -> None:
        self._store(self.canonical.encode("utf-8"))
        self.assertEqual(RECEIPT_ID, self.review.read_receipt(RECEIPT_ID).receipt_id)

    def test_the_same_record_with_keys_reordered_is_refused(self) -> None:
        lines = self.canonical.splitlines()
        self.assertEqual("review_record_noncanonical", self._refused(("\n".join(reversed(lines)) + "\n").encode()).code)

    def test_a_comment_is_refused(self) -> None:
        self.assertEqual("review_record_noncanonical", self._refused(("# note\n" + self.canonical).encode()).code)

    def test_crlf_line_ends_are_refused(self) -> None:
        self.assertEqual("review_record_noncanonical", self._refused(self.canonical.replace("\n", "\r\n").encode()).code)

    def test_a_missing_final_lf_is_refused(self) -> None:
        self.assertEqual("review_record_noncanonical", self._refused(self.canonical.rstrip("\n").encode()).code)

    def test_extra_whitespace_is_refused(self) -> None:
        padded = self.canonical.replace("review_kind: work_formal", "review_kind:  work_formal")
        self.assertNotEqual(padded, self.canonical)
        self.assertEqual("review_record_noncanonical", self._refused(padded.encode()).code)

    def test_an_alternate_scalar_spelling_is_refused(self) -> None:
        quoted = self.canonical.replace("review_kind: work_formal", 'review_kind: "work_formal"')
        self.assertNotEqual(quoted, self.canonical)
        self.assertEqual("review_record_noncanonical", self._refused(quoted.encode()).code)

    def test_a_duplicated_key_is_refused(self) -> None:
        duplicated = self.canonical + "review_kind: work_formal\n"
        self.assertTrue(self._refused(duplicated.encode()).code.startswith("review_record"))

    def test_invalid_utf8_is_refused(self) -> None:
        self.assertEqual("review_record_noncanonical", self._refused(self.canonical.encode() + b"\xff\n").code)

    def test_a_byte_order_mark_is_refused(self) -> None:
        self.assertEqual("review_record_noncanonical", self._refused(b"\xef\xbb\xbf" + self.canonical.encode()).code)

    def test_noncanonical_bytes_fail_validation(self) -> None:
        self._store(self.canonical.replace("\n", "\r\n").encode())
        self.assertIn("review_record_noncanonical", [p.code for p in validate_project(self.store)])


class CanonicalChainTests(WorklineTestCase):
    """The predecessor digest is taken only over bytes the canonical boundary accepted."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.review = ReviewStore(self.store)
        self.run = self.store.root / paths.run_dir(RUN_ID)
        self.run.mkdir(parents=True)

    def test_a_canonical_predecessor_chain_is_read(self) -> None:
        first = gate_record(1)
        (self.run / "000001.yaml").write_bytes(serialize.canonical_bytes(first))
        (self.run / "000002.yaml").write_bytes(serialize.canonical_bytes(gate_record(2, previous_digest=serialize.digest(first))))
        self.assertEqual(2, self.review.gate_chain(RUN_ID).latest.generation)

    def test_a_noncanonical_predecessor_is_refused_even_with_a_matching_digest(self) -> None:
        """G1 stored reordered; G2 names the digest of exactly those noncanonical bytes. Still refused."""
        import hashlib

        lines = serialize.canonical_text(gate_record(1)).splitlines()
        noncanonical = ("\n".join(reversed(lines)) + "\n").encode("utf-8")
        (self.run / "000001.yaml").write_bytes(noncanonical)
        forged = hashlib.sha256(noncanonical).hexdigest()
        (self.run / "000002.yaml").write_bytes(serialize.canonical_bytes(gate_record(2, previous_digest=forged)))
        with self.assertRaises(ValidationError) as caught:
            self.review.gate_chain(RUN_ID)
        self.assertEqual("review_record_noncanonical", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
