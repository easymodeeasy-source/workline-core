"""Batch A: reserved ownership and the bound ownership witness (``F3`` §7.8.4, IP-14 / IP-15 / IP-16).

What these tests hold, in the frozen order of §5.1 steps 5b-6:

* 5b is EXACTLY the landed ``mutation._safe_relative`` - reused, not re-grammared - and a
  non-canonical spelling is refused, never rewritten into another declaration;
* 5c reserves ``.workline/review`` (the root included) and ``.workline/events/events.jsonl``
  (exactly) by the ASCII fold as a pre-filter and filesystem OBJECT IDENTITY as the
  authority, refused as ``ReconcileRequired(reason="review_reserved_namespace")``, and an
  unanswerable identity is the OTHER refusal, ``review_candidate_unavailable``;
* 5d proves containment and captures a per-kind witness relative to the proven parent -
  file, executable, symlink, gitlink, absent - with a missing ancestor PROVING a deletion's
  absence and an existing indirect ancestor failing closed;
* the whole witness - kind, mode and identity - is what currentness compares, so a byte
  change, a mode-only change, a link-target change, a gitlink HEAD change, absent->present
  and present->absent are all visible;
* step 6 persists the already-bound witness without reading the filesystem, only in a
  review-v1 Work mutation, and a refusal at 5b/5c/5d leaves no ownership note at all;
* the legacy ``declare_own_content`` form is untouched, and the legacy digest reader refuses
  a witness rather than silently dropping it.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from helpers import WorklineTestCase
from workline import mutation as mutation_module
from workline.errors import ReconcileRequired, StopError
from workline.mutation import MutationController, WriteScope, declare_own_content
from workline.oplock import project_operation
from workline.review import fsafe, hermetic, ownership, work_invocation
from workline.store import ProjectStore

WINDOWS = sys.platform == "win32"


def git(where: Path, *args: str, check: bool = True, input: bytes | None = None) -> str:
    """Test-fixture Git only, with a clean environment and a fixed identity."""
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    environment.update({
        "GIT_AUTHOR_NAME": "Real Person", "GIT_AUTHOR_EMAIL": "real@proj",
        "GIT_COMMITTER_NAME": "Real Person", "GIT_COMMITTER_EMAIL": "real@proj",
    })
    found = subprocess.run(["git", "-C", str(where), *args], capture_output=True, env=environment, input=input)
    if check and found.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {where}: {found.stderr.decode('utf-8', 'replace')}")
    return found.stdout.decode("utf-8", "replace").strip()


def make_junction(link: Path, target: Path) -> bool:
    """A directory junction (Windows) or a directory symlink (POSIX); False when it cannot be made."""
    if WINDOWS:
        found = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
        return found.returncode == 0
    link.symlink_to(target, target_is_directory=True)
    return True


def blob_id(where: Path, data: bytes) -> str:
    return git(where, "hash-object", "--no-filters", "-t", "blob", "--stdin", input=data)


class OwnershipCase(WorklineTestCase):
    """A plain repository shaped like a Project's Git side: the event log committed, a real identity."""

    def setUp(self) -> None:
        super().setUp()
        self.root = self.new_dir("proj")
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "Real Person")
        git(self.root, "config", "user.email", "real@proj")
        git(self.root, "config", "core.fileMode", "false" if WINDOWS else "true")
        git(self.root, "config", "core.symlinks", "false" if WINDOWS else "true")
        (self.root / ".workline" / "events").mkdir(parents=True)
        (self.root / ".workline" / "events" / "events.jsonl").write_bytes(b'{"id":"e1"}\n')
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_bytes(b"print('base')\n")
        (self.root / "tmp").mkdir()
        (self.root / "tmp" / "old.txt").write_bytes(b"old\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "base", "--no-verify")
        self.store = ProjectStore(self.root)
        self.hermetic = hermetic.enter(self.store)
        self.base = git(self.root, "rev-parse", "HEAD")

    def commit_all(self, message: str = "more") -> str:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", message, "--no-verify")
        self.base = git(self.root, "rev-parse", "HEAD")
        return self.base

    def bind(self, results=(), deletions=()) -> tuple[ownership.OwnershipWitness, ...]:
        return ownership.bind_declarations(self.store, self.hermetic, results, deletions, self.base)

    def unavailable(self, results=(), deletions=()) -> StopError:
        with self.assertRaises(StopError) as caught:
            self.bind(results, deletions)
        self.assertNotIsInstance(caught.exception, ReconcileRequired)
        self.assertEqual(caught.exception.code, ownership.UNAVAILABLE_CODE)
        return caught.exception

    def reserved(self, results=(), deletions=()) -> ReconcileRequired:
        with self.assertRaises(ReconcileRequired) as caught:
            self.bind(results, deletions)
        self.assertEqual(caught.exception.code, "reconcile_required")
        self.assertEqual(caught.exception.reason, ownership.RESERVED_REASON)
        return caught.exception


# --------------------------------------------------------------------------- 5b


class SpellingTests(OwnershipCase):
    """§5.1 step 5b is EXACTLY the landed predicate, and nothing is rewritten."""

    def test_the_spelling_predicate_is_the_landed_one_not_a_copy(self) -> None:
        self.assertIs(ownership._safe_relative, mutation_module._safe_relative)

    def test_every_spelling_the_landed_predicate_refuses_is_unavailable(self) -> None:
        for path in ("", "/abs.txt", "C:/x.txt", "d/", "a//b.txt", "./src/main.py", "a/../b.txt", "a/./b.txt"):
            with self.subTest(path=path):
                self.assertFalse(mutation_module._safe_relative(path))
                self.unavailable(results=[path])

    def test_a_non_canonical_spelling_of_a_review_path_is_malformed_not_reserved(self) -> None:
        """§21.10 rows 1-2: refused at 5b, never normalized into the Review path and then refused as reserved."""
        for path in ("./.workline/review/gates/x.yaml", ".workline/runtime/../review/gates/x.yaml"):
            with self.subTest(path=path):
                raised = self.unavailable(results=[path])
                self.assertIn("canonical", raised.message)

    def test_no_grammar_beyond_the_landed_predicate_is_invented(self) -> None:
        """M-55: NFD and `.git/config` pass 5b today, so 5b must not refuse them."""
        nfd = "cafe\u0301/x.txt"
        self.assertTrue(mutation_module._safe_relative(nfd))
        (self.root / "cafe\u0301").mkdir()
        (self.root / nfd).write_bytes(b"nfd\n")
        witnesses = self.bind(results=[nfd])
        self.assertEqual([witness.path for witness in witnesses], [nfd])

    def test_a_nul_passes_spelling_and_is_refused_only_where_it_actually_fails(self) -> None:
        path = "d/a\0b.txt"
        self.assertTrue(mutation_module._safe_relative(path))
        raised = self.unavailable(results=[path])
        self.assertNotIn("canonical repository-relative spelling", raised.message)


# --------------------------------------------------------------------------- 5c


class ReservedNamespaceTests(OwnershipCase):
    """§5.1 step 5c: two reserved sets, one reason, component-wise, before any containment walk."""

    def setUp(self) -> None:
        super().setUp()
        (self.root / ".workline" / "review" / "gates").mkdir(parents=True)
        (self.root / ".workline" / "review" / "gates" / "x.yaml").write_bytes(b"x: 1\n")

    def test_a_result_inside_the_review_namespace_is_reserved(self) -> None:
        self.reserved(results=[".workline/review/gates/x.yaml"])

    def test_a_deletion_inside_the_review_namespace_is_reserved(self) -> None:
        self.reserved(deletions=[".workline/review/gates/x.yaml"])

    def test_the_review_root_itself_is_reserved_and_never_downgraded_to_malformed(self) -> None:
        """§7.8.6: it is a directory, so 5d would call it malformed - 5c refuses it first."""
        self.reserved(results=[".workline/review"])

    def test_the_event_log_is_reserved_as_a_result_and_as_a_deletion(self) -> None:
        self.reserved(results=[".workline/events/events.jsonl"])
        self.reserved(deletions=[".workline/events/events.jsonl"])

    def test_ascii_case_aliases_are_caught_by_the_fold(self) -> None:
        for path in (".WORKLINE/Review/gates/x.yaml", ".Workline/REVIEW", ".workline/EVENTS/Events.JSONL"):
            with self.subTest(path=path):
                self.reserved(results=[path])

    def test_the_fold_is_ascii_only(self) -> None:
        self.assertEqual(ownership.ascii_fold(".WoRkLiNe"), ".workline")
        self.assertEqual(ownership.ascii_fold(".WORKL\u0130NE"), ".workl\u0130ne")
        self.assertEqual(ownership.ascii_fold("\u00c9t\u00c9"), "\u00c9t\u00c9")
        self.assertIsNone(ownership.lexically_reserved(".workl\u0131ne/review/x.yaml"))

    def test_a_sibling_that_only_shares_a_prefix_is_not_reserved(self) -> None:
        """Component-wise, never a string prefix: `.workline/reviewX` is ordinary."""
        (self.root / ".workline" / "reviewX").mkdir()
        (self.root / ".workline" / "reviewX" / "notes.md").write_bytes(b"n\n")
        self.assertEqual([w.path for w in self.bind(results=[".workline/reviewX/notes.md"])],
                         [".workline/reviewX/notes.md"])

    def test_another_file_in_the_events_directory_is_not_reserved(self) -> None:
        """A-6 reserves exactly one path, never the directory."""
        (self.root / ".workline" / "events" / "other.txt").write_bytes(b"o\n")
        self.assertEqual([w.path for w in self.bind(results=[".workline/events/other.txt"])],
                         [".workline/events/other.txt"])

    def test_a_hard_link_to_the_event_log_is_reserved_by_object_identity(self) -> None:
        """The lexically innocent spelling reaches the canonical object: 2d compares OBJECTS, not names."""
        alias = self.root / "alias.txt"
        try:
            os.link(self.root / ".workline" / "events" / "events.jsonl", alias)
        except OSError as exc:
            self.skipTest(f"this filesystem cannot hard-link: {exc}")
        self.assertIsNone(ownership.lexically_reserved("alias.txt"))
        self.reserved(results=["alias.txt"])
        self.reserved(deletions=["alias.txt"])

    def test_an_ancestor_that_is_the_review_object_is_reserved_by_identity(self) -> None:
        """2c: an opened ancestor IS the Review root, whatever it is spelled (here: patched spelling equality away)."""
        with mock.patch.object(ownership, "lexically_reserved", return_value=None):
            self.reserved(results=[".workline/review/gates/x.yaml"])
            self.reserved(results=[".workline/review"])

    def test_an_indirect_ancestor_makes_the_identity_unanswerable_not_reserved(self) -> None:
        """2e: never a claim that the path IS reserved - the other refusal."""
        if not make_junction(self.root / "rv", self.root / ".workline" / "review"):
            self.skipTest("this account cannot create a junction or a directory symlink")
        raised = self.unavailable(results=["rv/gates/x.yaml"])
        self.assertNotEqual(getattr(raised, "reason", None), ownership.RESERVED_REASON)

    def test_precedence_spelling_before_reserved_before_containment(self) -> None:
        self.unavailable(results=["./x.txt", ".workline/review/gates/x.yaml"])
        self.reserved(results=[".workline/review/gates/x.yaml", "no/such/dir/file.txt"])

    def test_a_reserved_refusal_opens_nothing_for_containment(self) -> None:
        with mock.patch.object(ownership, "_capture_result") as capture, \
                mock.patch.object(ownership, "_capture_deletion") as delete:
            self.reserved(results=["src/main.py", ".workline/review"])
        capture.assert_not_called()
        delete.assert_not_called()

    def test_the_review_root_absent_leaves_the_fold_as_the_whole_test(self) -> None:
        """No Review object exists yet (it is created lazily): nothing to alias, so the lexical test decides."""
        for child in sorted((self.root / ".workline" / "review").rglob("*"), reverse=True):
            child.unlink() if child.is_file() else child.rmdir()
        (self.root / ".workline" / "review").rmdir()
        self.reserved(results=[".workline/review/gates/new.yaml"])
        self.assertEqual([w.path for w in self.bind(results=["src/main.py"])], ["src/main.py"])


# --------------------------------------------------------------------------- 5d


class WitnessKindTests(OwnershipCase):
    """§5.1 step 5d: the per-kind witness, captured relative to the proven parent."""

    def test_a_regular_file(self) -> None:
        data = b"print('result')\r\n"
        (self.root / "src" / "main.py").write_bytes(data)
        (witness,) = self.bind(results=["src/main.py"])
        self.assertEqual((witness.kind, witness.git_mode), ("file", "100644"))
        self.assertEqual(witness.material, data)
        self.assertEqual(witness.identity, blob_id(self.root, data))
        self.assertEqual(witness.content_sha256, hashlib.sha256(data).hexdigest())

    def test_a_new_file_has_the_regular_mode(self) -> None:
        (self.root / "new.txt").write_bytes(b"new\n")
        (witness,) = self.bind(results=["new.txt"])
        self.assertEqual((witness.kind, witness.git_mode), ("file", "100644"))

    def test_an_executable_file_keeps_the_mode_git_records(self) -> None:
        """The executable bit is Git's: the owner-execute bit where core.fileMode trusts it, the base entry otherwise."""
        git(self.root, "update-index", "--chmod=+x", "src/main.py")
        if not WINDOWS:
            os.chmod(self.root / "src" / "main.py", 0o755)
        self.commit_all("exec")
        (self.root / "src" / "main.py").write_bytes(b"#!/bin/sh\necho changed\n")
        (witness,) = self.bind(results=["src/main.py"])
        self.assertEqual((witness.kind, witness.git_mode), ("file", "100755"))

    @unittest.skipIf(WINDOWS, "NTFS carries no owner-execute bit; core.fileMode is false there")
    def test_a_chmod_alone_is_part_of_the_witness_on_posix(self) -> None:
        os.chmod(self.root / "src" / "main.py", 0o755)
        (witness,) = self.bind(results=["src/main.py"])
        self.assertEqual(witness.git_mode, "100755")

    @unittest.skipIf(WINDOWS, "this account cannot create a symlink; the Windows cases are separate below")
    def test_a_final_symlink_is_captured_as_its_link_and_never_followed(self) -> None:
        (self.root / "assets").mkdir()
        (self.root / "assets" / "real.txt").write_bytes(b"real bytes\n")
        os.symlink("real.txt", self.root / "assets" / "link")
        (witness,) = self.bind(results=["assets/link"])
        self.assertEqual((witness.kind, witness.git_mode, witness.material), ("symlink", "120000", b"real.txt"))
        self.assertEqual(witness.identity, blob_id(self.root, b"real.txt"))

    @unittest.skipUnless(WINDOWS, "core.symlinks=false is this platform's default")
    def test_a_plain_file_standing_for_a_base_link_is_that_link(self) -> None:
        """Where the filesystem holds no links, Git keeps the base's 120000 and the file IS the target."""
        target = blob_id(self.root, b"old-target")
        written = git(self.root, "hash-object", "-w", "--stdin", input=b"old-target")
        self.assertEqual(written, target)
        git(self.root, "update-index", "--add", "--cacheinfo", f"120000,{target},link")
        git(self.root, "commit", "-m", "link", "--no-verify")
        self.base = git(self.root, "rev-parse", "HEAD")
        (self.root / "link").write_bytes(b"new-target")
        (witness,) = self.bind(results=["link"])
        self.assertEqual((witness.kind, witness.git_mode, witness.material), ("symlink", "120000", b"new-target"))

    @unittest.skipUnless(WINDOWS, "the reparse-point final is the Windows shape of a final indirection")
    def test_a_final_reparse_point_whose_target_cannot_be_read_handle_bound_fails_closed(self) -> None:
        (self.root / "real").mkdir()
        if not make_junction(self.root / "jn", self.root / "real"):
            self.skipTest("this account cannot create a junction")
        raised = self.unavailable(results=["jn"])
        self.assertIn("reparse point", raised.message)

    def test_a_directory_result_that_is_not_a_submodule_is_unavailable(self) -> None:
        """F2 §6.5: a declared path that is a directory makes the Candidate unavailable."""
        (self.root / "adir").mkdir()
        self.unavailable(results=["adir"])

    def test_a_missing_result_is_unavailable(self) -> None:
        self.unavailable(results=["src/nope.py"])

    def test_a_result_under_a_missing_ancestor_is_unavailable(self) -> None:
        self.unavailable(results=["no/such/file.txt"])

    def test_a_result_under_an_indirect_ancestor_fails_closed(self) -> None:
        (self.root / "elsewhere").mkdir()
        (self.root / "elsewhere" / "out.so").write_bytes(b"foreign\n")
        if not make_junction(self.root / "build", self.root / "elsewhere"):
            self.skipTest("this account cannot create a junction or a directory symlink")
        self.unavailable(results=["build/out.so"])

    def test_a_deletion_with_its_parent_present(self) -> None:
        tracked = git(self.root, "rev-parse", "HEAD:tmp/old.txt")
        (self.root / "tmp" / "old.txt").unlink()
        (witness,) = self.bind(deletions=["tmp/old.txt"])
        self.assertEqual((witness.kind, witness.git_mode, witness.identity, witness.tracked_mode),
                         ("absent", "000000", tracked, "100644"))
        self.assertIsNone(witness.material)

    def test_a_deletion_whose_ancestor_is_gone_is_a_positive_absence(self) -> None:
        """§21.11 E: the last file removed and the directory with it - an ordinary correct deletion."""
        (self.root / "tmp" / "old.txt").unlink()
        (self.root / "tmp").rmdir()
        (witness,) = self.bind(deletions=["tmp/old.txt"])
        self.assertEqual(witness.kind, "absent")

    def test_a_deletion_under_an_existing_indirect_ancestor_fails_closed(self) -> None:
        """Missing is a proof; redirected is not."""
        (self.root / "tmp" / "old.txt").unlink()
        (self.root / "tmp").rmdir()
        (self.root / "other").mkdir()
        if not make_junction(self.root / "tmp", self.root / "other"):
            self.skipTest("this account cannot create a junction or a directory symlink")
        self.unavailable(deletions=["tmp/old.txt"])

    def test_a_deletion_of_an_untracked_path_is_unavailable(self) -> None:
        self.unavailable(deletions=["never/tracked.txt"])

    def test_a_deletion_that_still_exists_is_unavailable(self) -> None:
        self.unavailable(deletions=["tmp/old.txt"])

    def test_a_path_declared_as_both_result_and_deletion_cannot_be_witnessed(self) -> None:
        self.unavailable(results=["src/main.py"], deletions=["src/main.py"])

    def test_no_declared_path_is_vacuous_and_opens_nothing(self) -> None:
        with mock.patch.object(fsafe.SafeDirectory, "open_root", side_effect=AssertionError("opened")):
            self.assertEqual(self.bind(), ())

    def test_witnesses_are_ordered_by_path_utf8_bytes(self) -> None:
        for name in ("b.txt", "a.txt", "Z.txt"):
            (self.root / name).write_bytes(name.encode())
        paths = [w.path for w in self.bind(results=["b.txt", "a.txt", "Z.txt"])]
        self.assertEqual(paths, sorted(paths, key=lambda p: p.encode("utf-8")))

    def test_the_capture_resolves_nothing_from_the_project_root_by_pathname(self) -> None:
        """IP-15: no `ProjectStore.abs` (root / relative) and no `_content_digest` anywhere in 5b-5d."""
        (self.root / "src" / "main.py").write_bytes(b"x\n")
        (self.root / "tmp" / "old.txt").unlink()
        with mock.patch.object(ProjectStore, "abs", side_effect=AssertionError("root-relative resolution")), \
                mock.patch.object(mutation_module, "_content_digest", side_effect=AssertionError("digest reread")):
            witnesses = self.bind(results=["src/main.py"], deletions=["tmp/old.txt"])
        self.assertEqual([(w.path, w.kind) for w in witnesses], [("src/main.py", "file"), ("tmp/old.txt", "absent")])


class GitlinkTests(OwnershipCase):
    """160000: the commit the submodule's HEAD names, read through held handles (G-1 ... G-5)."""

    def setUp(self) -> None:
        super().setUp()
        self.subrepo = self.new_dir("subrepo")
        git(self.subrepo, "init", "-b", "main")
        (self.subrepo / "a.txt").write_bytes(b"a\n")
        git(self.subrepo, "add", "-A")
        git(self.subrepo, "commit", "-m", "sub base", "--no-verify")
        git(self.root, "-c", "protocol.file.allow=always", "submodule", "add", self.subrepo.as_uri(), "sub")
        self.commit_all("add sub")

    def advance(self) -> str:
        working = self.root / "sub"
        (working / "b.txt").write_bytes(b"b\n")
        git(working, "add", "-A")
        git(working, "commit", "-m", "sub advance", "--no-verify")
        return git(working, "rev-parse", "HEAD")

    def test_a_gitlink_witness_is_the_submodule_head_not_the_superproject_entry(self) -> None:
        staged = git(self.root, "ls-files", "--stage", "sub").split()[1]
        moved = self.advance()
        self.assertNotEqual(moved, staged)
        (witness,) = self.bind(results=["sub"])
        self.assertEqual((witness.kind, witness.git_mode, witness.identity), ("gitlink", "160000", moved))
        self.assertIsNone(witness.material)

    def test_a_gitlink_head_change_is_visible_to_currentness(self) -> None:
        (witness,) = self.bind(results=["sub"])
        self.assertIsNone(ownership.witness_problem(self.store, self.hermetic, witness, self.base))
        self.advance()
        problem = ownership.witness_problem(self.store, self.hermetic, witness, self.base)
        self.assertIsNotNone(problem)
        self.assertIn("identity", problem)


# --------------------------------------------------------------------------- currentness over the whole witness


class CurrentnessTests(OwnershipCase):
    """IP-16: the WHOLE witness is compared, so what a digest string could not see is seen."""

    def witness(self, path: str = "src/main.py") -> ownership.OwnershipWitness:
        (witness,) = self.bind(results=[path])
        self.assertIsNone(ownership.witness_problem(self.store, self.hermetic, witness, self.base))
        return witness

    def test_a_byte_change_is_visible(self) -> None:
        witness = self.witness()
        (self.root / "src" / "main.py").write_bytes(b"print('foreign')\n")
        self.assertIn("identity", ownership.witness_problem(self.store, self.hermetic, witness, self.base))

    def test_a_mode_only_change_is_visible(self) -> None:
        """M-33: the same bytes with another Git mode are another witness."""
        witness = self.witness()
        flipped = ownership.OwnershipWitness(witness.path, "file", "100755", witness.identity, witness.material)
        problem = ownership.witness_problem(self.store, self.hermetic, flipped, self.base)
        self.assertIsNotNone(problem)
        self.assertIn("git_mode", problem)
        self.assertNotIn("identity,", problem)

    @unittest.skipIf(WINDOWS, "a filesystem chmod is only Git's mode where core.fileMode trusts it")
    def test_a_real_chmod_is_visible_on_posix(self) -> None:
        witness = self.witness()
        os.chmod(self.root / "src" / "main.py", 0o755)
        self.assertIn("git_mode", ownership.witness_problem(self.store, self.hermetic, witness, self.base))

    @unittest.skipIf(WINDOWS, "this account cannot create a symlink")
    def test_a_link_target_change_is_visible(self) -> None:
        os.symlink("one", self.root / "ln")
        witness = self.witness("ln")
        os.unlink(self.root / "ln")
        os.symlink("two", self.root / "ln")
        self.assertIn("identity", ownership.witness_problem(self.store, self.hermetic, witness, self.base))

    @unittest.skipUnless(WINDOWS, "core.symlinks=false: the link is the plain file standing for it")
    def test_a_link_target_change_is_visible_where_links_are_plain_files(self) -> None:
        target = git(self.root, "hash-object", "-w", "--stdin", input=b"one")
        git(self.root, "update-index", "--add", "--cacheinfo", f"120000,{target},ln")
        git(self.root, "commit", "-m", "ln", "--no-verify")
        self.base = git(self.root, "rev-parse", "HEAD")
        (self.root / "ln").write_bytes(b"two")
        witness = self.witness("ln")
        (self.root / "ln").write_bytes(b"three")
        self.assertIn("identity", ownership.witness_problem(self.store, self.hermetic, witness, self.base))

    def test_absent_to_present_is_visible(self) -> None:
        (self.root / "tmp" / "old.txt").unlink()
        (witness,) = self.bind(deletions=["tmp/old.txt"])
        self.assertIsNone(ownership.witness_problem(self.store, self.hermetic, witness, self.base))
        (self.root / "tmp" / "old.txt").write_bytes(b"back again\n")
        self.assertIn("still exists", ownership.witness_problem(self.store, self.hermetic, witness, self.base))

    def test_present_to_absent_is_visible(self) -> None:
        witness = self.witness()
        (self.root / "src" / "main.py").unlink()
        self.assertIn("does not exist", ownership.witness_problem(self.store, self.hermetic, witness, self.base))

    def test_an_ancestor_swapped_to_an_indirection_is_refused_before_anything_is_compared(self) -> None:
        """The pre-stage check re-proves containment: a redirected ancestor never reaches a comparison."""
        (self.root / "pkg").mkdir()
        (self.root / "pkg" / "f.txt").write_bytes(b"mine\n")
        witness = self.witness("pkg/f.txt")
        (self.root / "pkg" / "f.txt").unlink()
        (self.root / "pkg").rmdir()
        (self.root / "foreign").mkdir()
        (self.root / "foreign" / "f.txt").write_bytes(b"mine\n")
        if not make_junction(self.root / "pkg", self.root / "foreign"):
            self.skipTest("this account cannot create a junction or a directory symlink")
        problem = ownership.witness_problem(self.store, self.hermetic, witness, self.base)
        self.assertIsNotNone(problem, "same bytes behind a redirected ancestor must not pass")
        with self.assertRaises(StopError) as caught:
            ownership.require_current(self.store, self.hermetic, [witness], self.base)
        self.assertEqual(caught.exception.code, ownership.UNAVAILABLE_CODE)

    def test_an_unchanged_set_passes(self) -> None:
        (self.root / "tmp" / "old.txt").unlink()
        witnesses = self.bind(results=["src/main.py"], deletions=["tmp/old.txt"])
        ownership.require_current(self.store, self.hermetic, witnesses, self.base)


# --------------------------------------------------------------------------- the durable form


class WitnessRecordTests(unittest.TestCase):
    """The explicit, closed durable form: every deviation fails closed."""

    OID = "1" * 40

    def file_witness(self) -> ownership.OwnershipWitness:
        data = b"bytes!\n"  # seven bytes: its canonical Base64 carries "==" padding
        return ownership.OwnershipWitness("a/b.txt", "file", "100644", ownership._blob_id(data, 40), data)

    def test_every_kind_round_trips_exactly(self) -> None:
        cases = [
            self.file_witness(),
            ownership.OwnershipWitness("x", "symlink", "120000", ownership._blob_id(b"t", 40), b"t"),
            ownership.OwnershipWitness("s", "gitlink", "160000", self.OID),
            ownership.OwnershipWitness("gone", "absent", "000000", self.OID, None, "100755"),
            ownership.OwnershipWitness("w", "file", "100644", ownership._blob_id(b"x", 64), b"x"),
        ]
        for witness in cases:
            with self.subTest(kind=witness.kind):
                record = witness.to_record()
                self.assertEqual(record["form"], ownership.WITNESS_FORM)
                self.assertEqual(ownership.OwnershipWitness.from_record(witness.path, record), witness)

    def test_every_deviation_is_refused(self) -> None:
        good = self.file_witness().to_record()
        self.assertTrue(good["material"].endswith("=="), "the fixture must exercise padding")
        self.assertEqual(good["material"], "Ynl0ZXMhCg==")
        mutations = {
            "unpadded base64": dict(good, material="Ynl0ZXMhCg"),
            "base64 with a line break": dict(good, material="Ynl0ZXMh\nCg=="),
            "base64 with non-zero pad bits": dict(good, material="Ynl0ZXMhCh=="),
            "unknown form": dict(good, form="review-v1-ownership-witness-v0"),
            "unknown kind": dict(good, kind="tree"),
            "mode for another kind": dict(good, git_mode="120000"),
            "no material": {key: value for key, value in good.items() if key != "material"},
            "extra field": dict(good, extra=1),
            "short id": dict(good, identity="abc"),
            "upper-case id": dict(good, identity=good["identity"].upper()),
            "non-canonical base64": dict(good, material=good["material"].rstrip("=")),
            "tampered material": dict(good, material="dGFtcGVyZWQK"),
            "gitlink with material": {"form": ownership.WITNESS_FORM, "kind": "gitlink", "git_mode": "160000",
                                      "identity": self.OID, "material": "eA=="},
            "absent without tracked mode": {"form": ownership.WITNESS_FORM, "kind": "absent", "git_mode": "000000",
                                            "identity": self.OID},
            "not a mapping": "sha256:" + "0" * 64,
        }
        for name, record in mutations.items():
            with self.subTest(name=name):
                with self.assertRaises(StopError) as caught:
                    ownership.OwnershipWitness.from_record("a/b.txt", record)
                self.assertEqual(caught.exception.code, "review_record_invalid")
        with self.assertRaises(StopError):
            ownership.OwnershipWitness.from_record("./a/b.txt", good)


# --------------------------------------------------------------------------- step 6 and durable compatibility


class AssertionTests(WorklineTestCase):
    """§5.1 step 6 in a real Project mutation, and the legacy form beside it."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        git(self.store.root, "config", "user.name", "Real Person")
        git(self.store.root, "config", "user.email", "real@proj")
        lock = project_operation(self.store, "start", {"work_id": "w_x", "mode": "single-work"})
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)
        self.hermetic = hermetic.enter(self.store)
        self.base = git(self.store.root, "rev-parse", "HEAD")
        (self.store.root / "result.txt").write_bytes(b"result\n")

    def open(self, *, review: bool = True):
        invocation = {"operation": "start", "work_id": "w_x", "mode": "single-work"}
        if review:
            invocation.update(work_invocation.markers())
        return MutationController(self.store).open("start", invocation, WriteScope(entities=("w_x",)))

    def bind(self, results=(), deletions=()):
        return ownership.bind_declarations(self.store, self.hermetic, results, deletions, self.base)

    def test_the_bound_witness_is_persisted_and_read_back_exactly(self) -> None:
        mutation = self.open()
        witnesses = self.bind(results=["result.txt"])
        ownership.assert_ownership(mutation, witnesses)
        self.assertEqual(ownership.own_witnesses(mutation), {"result.txt": witnesses[0]})
        reloaded = MutationController(self.store).load(mutation.id)
        self.assertEqual(ownership.own_witnesses(reloaded)["result.txt"], witnesses[0])

    def test_the_assertion_reads_nothing_from_the_filesystem(self) -> None:
        """R-6b: the object proven is the object asserted - step 6 re-resolves no pathname."""
        mutation = self.open()
        witnesses = self.bind(results=["result.txt"])
        (self.store.root / "result.txt").write_bytes(b"swapped after the proof\n")
        with mock.patch.object(fsafe.SafeDirectory, "open_root", side_effect=AssertionError("walked again")), \
                mock.patch.object(mutation_module, "_content_digest", side_effect=AssertionError("reread")):
            ownership.assert_ownership(mutation, witnesses)
        self.assertEqual(ownership.own_witnesses(mutation)["result.txt"].material, b"result\n")

    def test_asserting_the_same_witness_again_saves_nothing(self) -> None:
        mutation = self.open()
        witnesses = self.bind(results=["result.txt"])
        ownership.assert_ownership(mutation, witnesses)
        before = mutation.path.read_bytes()
        with mock.patch.object(type(mutation), "_save", side_effect=AssertionError("saved")):
            ownership.assert_ownership(mutation, witnesses)
        self.assertEqual(mutation.path.read_bytes(), before)

    def test_a_refusal_at_5b_5c_or_5d_leaves_no_ownership_note(self) -> None:
        """§5.4: the mutation stays pending, its markers unchanged, and no _OWN_CONTENT exists."""
        mutation = self.open()
        before = mutation.path.read_bytes()
        (self.store.root / ".workline" / "review").mkdir(parents=True, exist_ok=True)
        for results in (["./result.txt"], [".workline/review"], ["no/such.txt"]):
            with self.subTest(results=results):
                with self.assertRaises(StopError):
                    ownership.assert_ownership(mutation, self.bind(results=results))
                self.assertIsNone(mutation.note(mutation_module._OWN_CONTENT))
                self.assertEqual(mutation.path.read_bytes(), before)
                self.assertEqual(mutation.status, "pending")

    def test_a_legacy_mutation_never_holds_the_witness_form(self) -> None:
        mutation = self.open(review=False)
        with self.assertRaises(ReconcileRequired):
            ownership.assert_ownership(mutation, self.bind(results=["result.txt"]))
        self.assertIsNone(mutation.note(mutation_module._OWN_CONTENT))

    def test_an_unknown_or_contradictory_note_fails_closed(self) -> None:
        mutation = self.open()
        good = self.bind(results=["result.txt"])[0].to_record()
        for note in ({"result.txt": "sha256:" + "0" * 64}, {"result.txt": dict(good, kind="tree")}, ["result.txt"]):
            with self.subTest(note=note):
                mutation.record.setdefault("notes", {})[mutation_module._OWN_CONTENT] = note
                with self.assertRaises(ReconcileRequired):
                    ownership.own_witnesses(mutation)

    def test_the_legacy_digest_reader_refuses_a_witness_rather_than_dropping_it(self) -> None:
        mutation = self.open()
        ownership.assert_ownership(mutation, self.bind(results=["result.txt"]))
        with self.assertRaises(ReconcileRequired):
            mutation_module._own_content(mutation)

    def test_legacy_declare_own_content_is_unchanged(self) -> None:
        """The durable legacy form: the four digest strings, keyed by path, exactly as before."""
        mutation = self.open(review=False)
        declare_own_content(mutation, ["result.txt", "gone.txt"])
        note = mutation.note(mutation_module._OWN_CONTENT)
        self.assertEqual(note, {
            "gone.txt": "absent",
            "result.txt": "sha256:" + hashlib.sha256(b"result\n").hexdigest(),
        })
        self.assertEqual(mutation_module._own_content(mutation), note)


if __name__ == "__main__":
    unittest.main()
