"""P1-REV-001: the immutable Review create is race-safe at the physical create boundary itself.

The create is bound to the proven parent handle (no pathname is re-resolved
after the proof), every component is opened without following it, and the final
placement is exclusive - it fails on an existing name instead of replacing it.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from helpers import WorklineTestCase
from workline.errors import ReconcileRequired, ValidationError
from workline.mutation import MATCHING, MISMATCH, UNAPPLIED, Effect, MutationController, WriteScope
from workline.oplock import project_operation
from workline.review import fsafe, paths, serialize

from test_review_authorization import RECEIPT_ID, receipt_record

WINDOWS = sys.platform == "win32"


def make_junction(link: Path, target: Path) -> bool:
    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
    return made.returncode == 0


def try_symlink(link: Path, target: Path, directory: bool) -> bool:
    try:
        link.symlink_to(target, target_is_directory=directory)
        return True
    except (OSError, NotImplementedError):
        return False


class SafeCreateTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.controller = MutationController(self.store)
        lock = project_operation(self.store, "review-safe-create-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)
        self.outside = self.tmp / "outside"
        self.outside.mkdir()
        self.relative = paths.receipt_rel(RECEIPT_ID)
        self.target = self.store.root / self.relative
        self.text = serialize.canonical_text(receipt_record())

    def _mutation(self):
        mutation = self.controller.open(
            "start", {"operation": "review-safe-create", "path": self.relative}, WriteScope(files=(self.relative,))
        )
        mutation.add_effects("review", [Effect.create_file(self.relative, self.text)])
        return mutation

    @staticmethod
    def _remove_link(link: Path) -> None:
        """Remove the indirection itself, never what it points at: unlink a symlink, rmdir a junction."""
        if os.path.islink(link):
            os.unlink(link)
        elif getattr(os.path, "isjunction", lambda _: False)(link):
            os.rmdir(link)

    def _outside_is_empty(self) -> None:
        self.assertEqual([], sorted(p.name for p in self.outside.rglob("*")), "nothing may land outside the Project")

    # the three immutable outcomes -------------------------------------------
    def test_absent_target_is_created_with_exact_canonical_bytes(self) -> None:
        self._mutation().apply()
        self.assertEqual(self.text.encode("utf-8"), self.target.read_bytes())

    def test_same_bytes_replay_is_matching(self) -> None:
        mutation = self._mutation()
        mutation.apply()
        self.assertEqual([MATCHING], [c for _, c in mutation.apply()])

    def test_different_bytes_reconcile_and_are_not_replaced(self) -> None:
        mutation = self._mutation()
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b"someone: else\n")
        with self.assertRaises(ReconcileRequired):
            mutation.apply()
        self.assertEqual(b"someone: else\n", self.target.read_bytes())

    def test_a_directory_at_the_target_reconciles(self) -> None:
        mutation = self._mutation()
        self.target.mkdir(parents=True)
        self.assertEqual(MISMATCH, self.controller.classify(mutation.effects[0]))
        with self.assertRaises(ReconcileRequired):
            mutation.apply()
        self.assertTrue(self.target.is_dir())

    def test_a_crlf_copy_of_the_record_is_not_the_record(self) -> None:
        """Replay compares stored bytes, not text a reader normalised."""
        mutation = self._mutation()
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(self.text.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(MISMATCH, self.controller.classify(mutation.effects[0]))

    # races at the create boundary -------------------------------------------
    def test_target_created_by_another_actor_after_classification_is_never_overwritten(self) -> None:
        mutation = self._mutation()
        self.assertEqual(UNAPPLIED, self.controller.classify(mutation.effects[0]))
        real = fsafe.SafeDirectory.create_file_exclusive

        def racing(directory, name, data, tmp):
            # Between classification and the physical create, someone else
            # creates the target inside the proven directory.
            (self.store.root / self.relative).write_bytes(b"foreign: 1\n")
            return real(directory, name, data, tmp)

        with mock.patch.object(fsafe.SafeDirectory, "create_file_exclusive", racing):
            with self.assertRaises(ReconcileRequired):
                mutation.apply()
        self.assertEqual(b"foreign: 1\n", self.target.read_bytes())

    def test_identical_record_created_concurrently_is_an_exact_replay(self) -> None:
        mutation = self._mutation()
        real = fsafe.SafeDirectory.create_file_exclusive

        def racing(directory, name, data, tmp):
            (self.store.root / self.relative).write_bytes(data)
            return real(directory, name, data, tmp)

        with mock.patch.object(fsafe.SafeDirectory, "create_file_exclusive", racing):
            mutation.apply()
        self.assertEqual(self.text.encode("utf-8"), self.target.read_bytes())
        self.assertEqual([MATCHING], [c for _, c in mutation.apply()])

    def test_parent_swapped_after_the_proof_writes_nothing_outside(self) -> None:
        """A swap between the no-follow walk and the physical create is refused or harmless - never a redirect.

        Windows: every held directory is opened without FILE_SHARE_DELETE, so
        the swap itself is refused and the record lands in the proven
        directory. POSIX: the rename succeeds, but the create is bound to the
        proven fd, and the post-create walk sees the substitute and fails
        closed, taking the record back out of the moved directory.
        """
        parent = self.target.parent
        parent.mkdir(parents=True)
        mutation = self._mutation()
        real = fsafe.SafeDirectory.create_file_exclusive
        outcome: dict[str, object] = {}

        def swapping(directory, name, data, tmp):
            moved = parent.with_name("receipts.moved")
            try:
                os.rename(parent, moved)
            except OSError:
                outcome["pinned"] = True
            else:
                outcome["moved"] = moved
                linked = make_junction(parent, self.outside) if WINDOWS else try_symlink(parent, self.outside, True)
                if not linked:
                    parent.mkdir()  # still a substitute: another directory at the proven path
            return real(directory, name, data, tmp)

        with mock.patch.object(fsafe.SafeDirectory, "create_file_exclusive", swapping):
            try:
                mutation.apply()
                outcome["applied"] = True
            except ReconcileRequired:
                outcome["refused"] = True
        self.addCleanup(self._remove_link, parent)
        self._outside_is_empty()
        if outcome.get("pinned"):
            self.assertTrue(outcome.get("applied"), "with the swap refused, the create proceeds in the proven directory")
            self.assertEqual(self.text.encode("utf-8"), self.target.read_bytes())
        else:
            self.assertTrue(outcome.get("refused"), "a substituted parent must fail closed")
            self.assertEqual([], list(outcome["moved"].iterdir()), "the record is taken back out of the moved directory")

    @unittest.skipIf(WINDOWS, "on Windows a held directory cannot be relocated at all")
    def test_posix_proven_directory_relocated_outside_is_taken_back_out(self) -> None:
        """The POSIX-inherent case: the proven directory object itself is moved out of the Project.

        The fd follows the object, so the create lands in it wherever it went.
        The post-create walk no longer reaches it from the root, so the record
        is removed through the held fd and the create is refused.
        """
        parent = self.target.parent
        parent.mkdir(parents=True)
        mutation = self._mutation()
        real = fsafe.SafeDirectory.create_file_exclusive
        relocated = self.outside / "receipts"

        def relocating(directory, name, data, tmp):
            os.rename(parent, relocated)
            return real(directory, name, data, tmp)

        with mock.patch.object(fsafe.SafeDirectory, "create_file_exclusive", relocating):
            with self.assertRaises(ReconcileRequired):
                mutation.apply()
        self.assertEqual([], list(relocated.iterdir()), "the record does not stay outside the Project")

    @unittest.skipUnless(WINDOWS, "the share-mode pin is a Windows mechanism")
    def test_windows_held_directories_cannot_be_renamed_during_the_create(self) -> None:
        with fsafe.walk(self.store.root, self.relative.split("/")[:-1], create=True) as chain:
            for victim in (self.target.parent, self.target.parent.parent, self.store.root / ".workline"):
                with self.assertRaises(OSError):
                    os.rename(victim, str(victim) + ".moved")

    # indirection at the target or on the way --------------------------------
    @unittest.skipUnless(WINDOWS, "junctions are a Windows reparse point")
    def test_a_junctioned_parent_is_refused_by_the_classifier_and_by_the_writer(self) -> None:
        review = self.store.root / paths.REVIEW_DIR
        review.mkdir(parents=True)
        link = review / "receipts"
        if not make_junction(link, self.outside):
            self.skipTest("cannot create a junction here")
        self.addCleanup(lambda: os.rmdir(link) if os.path.lexists(link) else None)
        self.assertTrue(link.is_dir() and not link.is_symlink(), "a junction passes naive directory checks")
        mutation = self._mutation()
        self.assertEqual(MISMATCH, self.controller.classify(mutation.effects[0]))
        with self.assertRaises(ReconcileRequired):
            mutation.apply()
        # The writer refuses on its own too, independently of classification.
        with self.assertRaises(ValidationError) as caught:
            self.controller.apply_effect(mutation.effects[0])
        self.assertEqual("review_containment", caught.exception.code)
        self._outside_is_empty()

    @unittest.skipUnless(WINDOWS, "in-place reparse conversion is a Windows attack")
    def test_parent_converted_into_a_junction_in_place_while_held_is_refused_by_the_kernel(self) -> None:
        """The empty held parent is turned into a junction after the walk; the handle-relative create is refused.

        A path-based create would follow it. Binding the create to the held
        handle is what makes the kernel refuse instead of redirecting.
        """
        from review_attack import set_mount_point

        parent = self.target.parent
        parent.mkdir(parents=True)
        mutation = self._mutation()
        real = fsafe.SafeDirectory.create_file_exclusive
        converted: list[str] = []

        def converting(directory, name, data, tmp):
            converted.append(set_mount_point(parent, self.outside))
            return real(directory, name, data, tmp)

        with mock.patch.object(fsafe.SafeDirectory, "create_file_exclusive", converting):
            with self.assertRaises((ValidationError, ReconcileRequired)):
                mutation.apply()
        self.addCleanup(lambda: os.rmdir(parent) if os.path.lexists(parent) else None)
        self.assertEqual(["converted"], converted, "the attacker's conversion must actually have happened")
        self._outside_is_empty()

    @unittest.skipIf(WINDOWS, "file symlinks need a privilege this Windows account does not hold")
    def test_a_symlink_at_the_target_is_refused(self) -> None:
        self.target.parent.mkdir(parents=True)
        victim = self.outside / "victim.yaml"
        victim.write_bytes(b"outside: 1\n")
        self.assertTrue(try_symlink(self.target, victim, False))
        mutation = self._mutation()
        self.assertEqual(MISMATCH, self.controller.classify(mutation.effects[0]))
        with self.assertRaises(ReconcileRequired):
            mutation.apply()
        self.assertEqual(b"outside: 1\n", victim.read_bytes())

    @unittest.skipIf(WINDOWS, "directory symlinks need a privilege this Windows account does not hold")
    def test_a_symlinked_parent_is_refused(self) -> None:
        review = self.store.root / paths.REVIEW_DIR
        review.mkdir(parents=True)
        self.assertTrue(try_symlink(review / "receipts", self.outside, True))
        mutation = self._mutation()
        self.assertEqual(MISMATCH, self.controller.classify(mutation.effects[0]))
        with self.assertRaises(ReconcileRequired):
            mutation.apply()
        with self.assertRaises(ValidationError):
            self.controller.apply_effect(mutation.effects[0])
        self._outside_is_empty()

    # the generic primitive stays away ----------------------------------------
    def test_generic_write_file_is_refused_on_a_review_path(self) -> None:
        mutation = self.controller.open(
            "start", {"operation": "review-generic"}, WriteScope(files=(self.relative,))
        )
        with self.assertRaises(ValidationError):
            mutation.add_effects("review", [Effect.write_file(self.relative, self.text)])

    def test_a_failed_temporary_write_leaves_no_debris_and_no_record(self) -> None:
        """A write failure partway through (disk full, I/O error) removes the temporary file and places nothing."""
        mutation = self._mutation()
        if WINDOWS:
            failing = mock.patch.object(fsafe, "_WriteFile", lambda *args: 0)
        else:
            real_write = os.write

            def fail_on_temporary(fd, data):
                raise OSError(28, "No space left on device")

            failing = mock.patch.object(fsafe.os, "write", fail_on_temporary)
        with failing:
            with self.assertRaises((ValidationError, OSError)):
                mutation.apply()
        self.assertFalse(self.target.exists(), "a failed write places no record")
        leftovers = [p.name for p in self.store.tmp.iterdir()] if self.store.tmp.is_dir() else []
        self.assertEqual([], leftovers, "a failed write leaves no temporary file")
        # And the same mutation, retried, creates the record normally.
        self.controller.load(mutation.id).apply()
        self.assertEqual(self.text.encode("utf-8"), self.target.read_bytes())

    def test_no_temporary_file_is_left_behind(self) -> None:
        self._mutation().apply()
        self.assertEqual([], [p.name for p in self.store.tmp.iterdir()] if self.store.tmp.is_dir() else [])
        self.assertEqual([self.target.name], [p.name for p in self.target.parent.iterdir()])


if __name__ == "__main__":
    unittest.main()
