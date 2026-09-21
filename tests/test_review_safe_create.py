"""P1-REV-001: the immutable Review create is safe at the physical create boundary itself.

Where the platform can keep the create inside the Project (Windows: every held
directory is opened without ``FILE_SHARE_DELETE``, so nothing from the root down
can be renamed, deleted or replaced while a create runs), the create is bound to
the proven parent handle - no pathname is re-resolved after the proof, every
component is opened without following it, and the final placement is exclusive,
failing on an existing name instead of replacing it.

Where it cannot (POSIX: an fd pins nothing, so a held directory can be renamed
out of the Project and the create through the fd would land wherever it went),
the immutable Review create is refused before anything is opened or written -
no record is ever created outside the Project and then taken back out.
"""

from __future__ import annotations

import os
from pathlib import Path
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
CREATE_SUPPORTED = fsafe.immutable_create_supported()
FAIL_CLOSED = "the immutable Review create is fail-closed on this platform (POSIX pins no held directory)"
CREATE_ONLY = unittest.skipUnless(CREATE_SUPPORTED, FAIL_CLOSED)
POSIX_FAIL_CLOSED = unittest.skipIf(CREATE_SUPPORTED, "this platform supports the immutable create; fail-closed is POSIX-only")


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

    def _open(self):
        return self.controller.open(
            "start", {"operation": "review-safe-create", "path": self.relative}, WriteScope(files=(self.relative,))
        )

    def _mutation(self):
        mutation = self._open()
        mutation.add_effects("review", [Effect.create_file(self.relative, self.text)])
        return mutation

    def _no_temp_debris(self) -> None:
        leftovers = [p.name for p in self.store.tmp.iterdir()] if self.store.tmp.is_dir() else []
        self.assertEqual([], leftovers, "a fail-closed create leaves no temporary file")

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
    @CREATE_ONLY
    def test_absent_target_is_created_with_exact_canonical_bytes(self) -> None:
        self._mutation().apply()
        self.assertEqual(self.text.encode("utf-8"), self.target.read_bytes())

    @CREATE_ONLY
    def test_same_bytes_replay_is_matching(self) -> None:
        mutation = self._mutation()
        mutation.apply()
        self.assertEqual([MATCHING], [c for _, c in mutation.apply()])

    @CREATE_ONLY
    def test_different_bytes_reconcile_and_are_not_replaced(self) -> None:
        mutation = self._mutation()
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b"someone: else\n")
        with self.assertRaises(ReconcileRequired):
            mutation.apply()
        self.assertEqual(b"someone: else\n", self.target.read_bytes())

    @CREATE_ONLY
    def test_a_directory_at_the_target_reconciles(self) -> None:
        mutation = self._mutation()
        self.target.mkdir(parents=True)
        self.assertEqual(MISMATCH, self.controller.classify(mutation.effects[0]))
        with self.assertRaises(ReconcileRequired):
            mutation.apply()
        self.assertTrue(self.target.is_dir())

    @CREATE_ONLY
    def test_a_crlf_copy_of_the_record_is_not_the_record(self) -> None:
        """Replay compares stored bytes, not text a reader normalised."""
        mutation = self._mutation()
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(self.text.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(MISMATCH, self.controller.classify(mutation.effects[0]))

    # races at the create boundary -------------------------------------------
    @CREATE_ONLY
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

    @CREATE_ONLY
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

    @CREATE_ONLY
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

    # POSIX: the immutable create is fail-closed, before anything is written ---
    #
    # An fd pins no directory, so a held parent can be renamed out of the
    # Project while it is held and the create through the fd would land wherever
    # it went. No POSIX primitive makes that placement fail once the parent has
    # left the Project, and creating anyway, then noticing and removing the
    # record, would still have put it outside. So the create is refused before
    # any directory, temporary file or record is opened or written.

    def _expect_create_refused(self):
        """Open the mutation and record the create; assert it is refused fail-closed. Returns the raised error."""
        mutation = self._open()
        with self.assertRaises(ValidationError) as caught:
            mutation.add_effects("review", [Effect.create_file(self.relative, self.text)])
        self.assertEqual(fsafe.UNSUPPORTED_CODE, caught.exception.code)
        return caught.exception

    @POSIX_FAIL_CLOSED
    def test_the_immutable_create_is_fail_closed_before_any_write(self) -> None:
        self.assertFalse(fsafe.immutable_create_supported())
        with self.assertRaises(ValidationError) as caught:
            fsafe.require_immutable_create()
        self.assertEqual(fsafe.UNSUPPORTED_CODE, caught.exception.code)
        self._expect_create_refused()
        self.assertFalse(self.target.exists(), "nothing is written")
        self._no_temp_debris()
        self._outside_is_empty()

    @POSIX_FAIL_CLOSED
    def test_a_relocation_attempt_puts_no_record_outside_and_fails_closed(self) -> None:
        """The required proof: under a relocation attempt, no final record appears anywhere, and the create fails closed."""
        parent = self.target.parent
        parent.mkdir(parents=True)
        relocated = self.outside / "receipts"
        os.rename(parent, relocated)  # the parent is now outside the Project, exactly the case that cannot be contained
        self._expect_create_refused()
        self.assertFalse(self.target.exists())
        self.assertEqual([], list(relocated.iterdir()), "no record is created in the relocated directory")
        self._no_temp_debris()

    @POSIX_FAIL_CLOSED
    def test_even_a_direct_apply_of_a_create_effect_is_fail_closed(self) -> None:
        """Defence in depth: were a create effect recorded elsewhere, applying it here still writes nothing."""
        record = {"kind": "create_file", "payload": {"path": self.relative, "content": self.text}}
        with self.assertRaises(ValidationError) as caught:
            self.controller.apply_effect(record)
        self.assertEqual(fsafe.UNSUPPORTED_CODE, caught.exception.code)
        self.assertFalse(self.target.exists())
        self._no_temp_debris()

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

    @POSIX_FAIL_CLOSED
    def test_a_symlink_at_the_target_is_fail_closed_and_its_victim_is_untouched(self) -> None:
        """The record-target-symlink case: refused before any write, and what the symlink points at is never touched."""
        self.target.parent.mkdir(parents=True)
        victim = self.outside / "victim.yaml"
        victim.write_bytes(b"outside: 1\n")
        if not try_symlink(self.target, victim, False):
            self.skipTest("cannot create a file symlink here")
        self._expect_create_refused()
        self.assertEqual(b"outside: 1\n", victim.read_bytes(), "the symlink's target is never written through")

    @POSIX_FAIL_CLOSED
    def test_a_symlinked_parent_is_fail_closed_and_nothing_lands_outside(self) -> None:
        review = self.store.root / paths.REVIEW_DIR
        review.mkdir(parents=True)
        if not try_symlink(review / "receipts", self.outside, True):
            self.skipTest("cannot create a directory symlink here")
        self._expect_create_refused()
        self._outside_is_empty()

    # the generic primitive stays away ----------------------------------------
    def test_generic_write_file_is_refused_on_a_review_path(self) -> None:
        mutation = self.controller.open(
            "start", {"operation": "review-generic"}, WriteScope(files=(self.relative,))
        )
        with self.assertRaises(ValidationError):
            mutation.add_effects("review", [Effect.write_file(self.relative, self.text)])

    @CREATE_ONLY
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

    @CREATE_ONLY
    def test_no_temporary_file_is_left_behind(self) -> None:
        self._mutation().apply()
        self.assertEqual([], [p.name for p in self.store.tmp.iterdir()] if self.store.tmp.is_dir() else [])
        self.assertEqual([self.target.name], [p.name for p in self.target.parent.iterdir()])


if __name__ == "__main__":
    unittest.main()
