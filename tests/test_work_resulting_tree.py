"""The resulting tree of a frozen Candidate: the exact tree identity that exists before K1.

P3 F3 §7.9.2, §7.1.11, IP-13.

The tree is "the base tree with this Candidate's entries applied", and every word
of that is tested against real Git: applied to WHICH base, at which kind and mode
and object id, with deletions absent, and with everything the Candidate does not
mention left exactly as the base holds it.

Two things these tests are especially about. The base is
``declared_base.base_commit`` - the committed HEAD AFTER S-c0 - because composing
against ``PRE_S_C0_BASE`` would erase S-c0's event log from the result; §7.1.11
proves the two carry the same ATTRIBUTE state, not the same tree identity. And
every Project-object question runs through Unit 1's class B authority, because a
replacement ref or an inherited ``GIT_OBJECT_DIRECTORY`` would otherwise decide
what the base "holds" - the defect Unit 3 was repaired for.

Nothing here creates a commit. A tree identity is not an authorization.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from helpers import WorklineTestCase, git
from workline import gitcmd
from workline.errors import StopError
from workline.review import hermetic, paths as review_paths, resulting_tree as rt
from workline.store import ProjectStore

ZERO_40 = "0" * 40
CODE = "review_resulting_tree_unavailable"


def clean_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}


class TreeCase(WorklineTestCase):
    """A Project with a base commit, and helpers to declare Candidate entries against it."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        git(self.store.root, "config", "user.name", "Real Person")
        git(self.store.root, "config", "user.email", "real@proj")
        self.hermetic = hermetic.enter(self.store)
        self.write("keep.txt", "keep\n")
        self.write("sub/old.txt", "old\n")
        self.base = self.commit("base")
        self.base_tree = rt.root_tree_id(self.hermetic, self.base)
        self.held = rt.tree_entries(self.hermetic, self.base_tree)

    def write(self, relative: str, text: str) -> None:
        path = self.store.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def commit(self, message: str) -> str:
        git(self.store.root, "add", "-A")
        git(self.store.root, "commit", "-m", message, "--no-verify")
        return git(self.store.root, "rev-parse", "HEAD").strip()

    def blob(self, data: bytes) -> tuple[str, str]:
        return gitcmd.hash_blob(self.store.root, data), hashlib.sha256(data).hexdigest()

    def added(self, path: str, data: bytes, mode: str = "100644", kind: str = "file") -> rt.Entry:
        oid, digest = self.blob(data)
        return rt.Entry(path, "A", "absent", "000000", ZERO_40, kind, mode, oid,
                        digest if kind in rt.BYTE_KINDS else None)

    def modified(self, path: str, data: bytes, mode: str = "100644") -> rt.Entry:
        old = self.held[path]
        oid, digest = self.blob(data)
        return rt.Entry(path, "M", "file", old.mode, old.oid, "file", mode, oid, digest)

    def deleted(self, path: str) -> rt.Entry:
        old = self.held[path]
        kind = "symlink" if old.mode == "120000" else "gitlink" if old.mode == "160000" else "file"
        return rt.Entry(path, "D", kind, old.mode, old.oid, "absent", "000000", ZERO_40, None)

    def compose(self, entries, payloads=None) -> str:
        return rt.resulting_tree_id(self.store, self.hermetic, self.base, entries, payloads or {})

    def refusal(self, call, code: str = CODE) -> StopError:
        with self.assertRaises(StopError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        return caught.exception


# --------------------------------------------------------------------------- the object authority


class RootTreeTests(TreeCase):
    """§7.9.2 needs exact tree identities, and the revision view is what a replacement ref changes."""

    def test_the_root_tree_comes_from_the_stored_commit_object(self) -> None:
        self.assertEqual(self.base_tree, git(self.store.root, "rev-parse", "HEAD^{tree}").strip())
        self.assertEqual(len(self.base_tree), len(self.base))

    def test_only_an_exact_full_object_id_names_a_commit(self) -> None:
        branch = git(self.store.root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        for commit in ("HEAD", branch, self.base[:12], self.base.upper(), f"{self.base}^{{tree}}", ""):
            with self.subTest(commit=commit):
                self.refusal(lambda commit=commit: rt.root_tree_id(self.hermetic, commit))

    def test_a_replacement_cannot_change_the_root_tree(self) -> None:
        """M-49 / M-58: an oid means the object it names, never a refs/replace view."""
        self.write("other.txt", "other\n")
        other = self.commit("other")
        subprocess.run(["git", "-C", str(self.store.root), "replace", "-f", self.base, other],
                       capture_output=True, env=clean_env())
        gitcmd.forget_object_answers()
        self.assertEqual(rt.root_tree_id(self.hermetic, self.base), self.base_tree)
        self.assertNotEqual(rt.root_tree_id(self.hermetic, other), self.base_tree)

    def test_a_replacement_cannot_change_the_composition_base(self) -> None:
        self.write("other.txt", "other\n")
        other = self.commit("other")
        subprocess.run(["git", "-C", str(self.store.root), "replace", "-f", self.base, other],
                       capture_output=True, env=clean_env())
        gitcmd.forget_object_answers()
        composed = rt.resulting_tree_id(self.store, self.hermetic, self.base, [], {})
        self.assertEqual(composed, self.base_tree)

    def test_an_inherited_object_directory_is_stripped(self) -> None:
        """M-61: an exported GIT_OBJECT_DIRECTORY hides the repository's own objects."""
        hostile = self.new_dir("hostile-objects")
        control = subprocess.run(
            ["git", "-C", str(self.store.root), "cat-file", "commit", self.base],
            capture_output=True, env={**clean_env(), "GIT_OBJECT_DIRECTORY": str(hostile)},
        )
        self.assertNotEqual(control.returncode, 0, "the hostile directory should really hide the objects")
        with mock.patch.dict(os.environ, {"GIT_OBJECT_DIRECTORY": str(hostile)}):
            gitcmd.forget_object_answers()
            self.assertEqual(rt.root_tree_id(self.hermetic, self.base), self.base_tree)
            self.assertEqual(self.compose([]), self.base_tree)

    def test_an_inherited_index_file_is_stripped(self) -> None:
        hostile = self.new_dir("hostile-index") / "index"
        with mock.patch.dict(os.environ, {"GIT_INDEX_FILE": str(hostile)}):
            self.assertEqual(self.compose([]), self.base_tree)
        self.assertFalse(hostile.exists(), "the Project's composition never wrote the inherited index")

    def test_hostile_inline_configuration_is_stripped(self) -> None:
        hostile = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.autocrlf", "GIT_CONFIG_VALUE_0": "true"}
        with mock.patch.dict(os.environ, hostile):
            self.assertEqual(self.compose([]), self.base_tree)

    def test_the_generic_object_cache_is_not_the_authority(self) -> None:
        with mock.patch.object(gitcmd, "tree_entries", side_effect=AssertionError("tree_entries used")):
            with mock.patch.object(gitcmd, "read_blob", side_effect=AssertionError("read_blob used")):
                self.assertEqual(self.compose([]), self.base_tree)

    def test_every_object_read_is_a_class_b_invocation(self) -> None:
        # the entry is built BEFORE the recorder is installed, so what is captured is the
        # composer's own invocations and not the fixture's
        entry = self.added("a.txt", b"a\n")
        seen: list[tuple[tuple[str, ...], dict]] = []
        real = gitcmd.run_git_bytes

        def recording(repo, *args, **kwargs):
            seen.append((args, dict(kwargs)))
            return real(repo, *args, **kwargs)

        with mock.patch.object(gitcmd, "run_git_bytes", recording):
            self.compose([entry], {"a.txt": b"a\n"})
        self.assertTrue(seen)
        for args, kwargs in seen:
            with self.subTest(verb=args[:8]):
                names = {name for name in kwargs["env"] if name.upper().startswith("GIT_")}
                self.assertEqual(names - {"GIT_INDEX_FILE"}, set(hermetic.CLASS_B_ALLOWLIST))
                self.assertEqual(kwargs["env"]["GIT_NO_REPLACE_OBJECTS"], "1")
                self.assertEqual(kwargs["env"]["GIT_NO_LAZY_FETCH"], "1")
                for name in hermetic.CLASS_B_IDENTITY_VARIABLES:
                    self.assertNotIn(name, kwargs["env"])
                settings = dict(
                    argument.split("=", 1)
                    for position, argument in enumerate(args)
                    if position > 0 and args[position - 1] == "-c"
                )
                for key, value in hermetic.CLASS_B_CONFIGURATION:
                    self.assertEqual(settings.get(key), value)

    def test_the_index_file_is_the_scratch_one_never_the_project(self) -> None:
        seen: list[str] = []
        real = gitcmd.run_git_bytes

        def recording(repo, *args, **kwargs):
            named = (kwargs.get("env") or {}).get("GIT_INDEX_FILE")
            if named:
                seen.append(named)
            return real(repo, *args, **kwargs)

        with mock.patch.object(gitcmd, "run_git_bytes", recording):
            self.compose([])
        self.assertTrue(seen)
        for named in seen:
            with self.subTest(index=named):
                self.assertIn(review_paths.RUNTIME_RESULTING_TREE_DIR.replace("/", os.sep), named)
                self.assertNotEqual(Path(named), self.store.root / ".git" / "index")


# --------------------------------------------------------------------------- composition


class CompositionTests(TreeCase):
    """Every kind, every direction, and everything the Candidate does not mention left alone."""

    def entries_of(self, tree: str) -> dict[str, gitcmd.TreeEntry]:
        with rt.composed(self.store, self.hermetic, self.base, [], {}) as composition:
            self.assertEqual(composition.tree, self.base_tree)
        return {}

    def test_no_entries_composes_to_the_declared_base_tree(self) -> None:
        self.assertEqual(self.compose([]), self.base_tree)

    def test_an_all_inert_candidate_composes_to_the_base_tree(self) -> None:
        """An entry that changed nothing stays in the Candidate and is a tree no-op (F2 §6.3)."""
        old = self.held["keep.txt"]
        inert = rt.Entry("keep.txt", "M", "file", old.mode, old.oid, "file", old.mode, old.oid,
                         hashlib.sha256(b"keep\n").hexdigest())
        self.assertTrue(inert.inert)
        self.assertEqual(self.compose([inert]), self.base_tree)

    def test_an_added_file_appears_at_its_exact_identity(self) -> None:
        data = b"brand new\n"
        entry = self.added("added.txt", data)
        with rt.composed(self.store, self.hermetic, self.base, [entry], {"added.txt": data}) as composition:
            found = composition.entries()["added.txt"]
            self.assertEqual((found.mode, found.type, found.oid), ("100644", "blob", entry.new_oid))
            self.assertNotEqual(composition.tree, self.base_tree)

    def test_a_modified_file_takes_its_new_identity(self) -> None:
        data = b"changed\n"
        entry = self.modified("keep.txt", data)
        with rt.composed(self.store, self.hermetic, self.base, [entry], {"keep.txt": data}) as composition:
            self.assertEqual(composition.entries()["keep.txt"].oid, entry.new_oid)

    def test_the_executable_bit_is_gits_not_the_filesystems(self) -> None:
        data = b"#!/bin/sh\n"
        entry = self.added("run.sh", data, mode="100755")
        with rt.composed(self.store, self.hermetic, self.base, [entry], {"run.sh": data}) as composition:
            self.assertEqual(composition.entries()["run.sh"].mode, "100755")

    def test_an_executable_mode_change_alone_changes_the_tree(self) -> None:
        old = self.held["keep.txt"]
        entry = rt.Entry("keep.txt", "M", "file", old.mode, old.oid, "file", "100755", old.oid,
                         hashlib.sha256(b"keep\n").hexdigest())
        with rt.composed(self.store, self.hermetic, self.base, [entry], {}) as composition:
            self.assertEqual(composition.entries()["keep.txt"].mode, "100755")
            self.assertNotEqual(composition.tree, self.base_tree)

    def test_a_symlink_is_its_link_object_and_is_never_dereferenced(self) -> None:
        """F2 §6.4: the artifact is the link object, identified by the target bytes."""
        target = b"sub/old.txt"
        entry = self.added("link", target, mode="120000", kind="symlink")
        with rt.composed(self.store, self.hermetic, self.base, [entry], {"link": target}) as composition:
            found = composition.entries()["link"]
            self.assertEqual((found.mode, found.type), ("120000", "blob"))
            self.assertEqual(composition.read_blob(found.oid), target)

    def test_a_gitlink_needs_no_fetch_and_no_checkout(self) -> None:
        absent = "1" * 40
        entry = rt.Entry("submod", "A", "absent", "000000", ZERO_40, "gitlink", "160000", absent, None)
        with rt.composed(self.store, self.hermetic, self.base, [entry], {}) as composition:
            found = composition.entries()["submod"]
            self.assertEqual((found.mode, found.type, found.oid), ("160000", "commit", absent))

    def test_a_deletion_is_an_absent_path_and_nothing_else(self) -> None:
        with rt.composed(self.store, self.hermetic, self.base, [self.deleted("sub/old.txt")], {}) as composition:
            listing = composition.entries()
            self.assertNotIn("sub/old.txt", listing)
            self.assertNotIn("sub", composition.entries(trees=True))

    def test_a_nested_addition_creates_the_subtrees_it_needs(self) -> None:
        data = b"deep\n"
        entry = self.added("a/b/c/deep.txt", data)
        with rt.composed(self.store, self.hermetic, self.base, [entry], {"a/b/c/deep.txt": data}) as composition:
            self.assertIn("a/b/c/deep.txt", composition.entries())
            self.assertIn("a", composition.entries(trees=True))

    def test_everything_the_candidate_does_not_mention_is_preserved_exactly(self) -> None:
        data = b"added\n"
        entry = self.added("added.txt", data)
        with rt.composed(self.store, self.hermetic, self.base, [entry], {"added.txt": data}) as composition:
            listing = composition.entries()
        for path, held in self.held.items():
            with self.subTest(path=path):
                self.assertEqual((listing[path].mode, listing[path].oid), (held.mode, held.oid))

    def test_a_mixed_candidate_applies_every_entry(self) -> None:
        added, changed = b"added\n", b"changed\n"
        old = self.held["keep.txt"]
        entries = [
            self.added("added.txt", added),
            self.modified("keep.txt", changed),
            self.deleted("sub/old.txt"),
            rt.Entry("keep.txt.inert", "A", "absent", "000000", ZERO_40, "gitlink", "160000", "2" * 40, None),
        ]
        payloads = {"added.txt": added, "keep.txt": changed}
        with rt.composed(self.store, self.hermetic, self.base, entries, payloads) as composition:
            listing = composition.entries()
        self.assertEqual(listing["added.txt"].oid, entries[0].new_oid)
        self.assertEqual(listing["keep.txt"].oid, entries[1].new_oid)
        self.assertNotIn("sub/old.txt", listing)
        self.assertEqual(listing["keep.txt.inert"].mode, "160000")
        self.assertNotEqual(old.oid, listing["keep.txt"].oid)

    def test_the_order_entries_are_given_in_does_not_change_the_tree(self) -> None:
        added, changed = b"added\n", b"changed\n"
        entries = [self.added("added.txt", added), self.modified("keep.txt", changed), self.deleted("sub/old.txt")]
        payloads = {"added.txt": added, "keep.txt": changed}
        first = self.compose(entries, payloads)
        second = self.compose(list(reversed(entries)), payloads)
        self.assertEqual(first, second)

    def test_bytes_already_in_the_project_need_no_payload(self) -> None:
        old = self.held["sub/old.txt"]
        entry = rt.Entry("copy.txt", "A", "absent", "000000", ZERO_40, "file", "100644", old.oid,
                         hashlib.sha256(b"old\n").hexdigest())
        with rt.composed(self.store, self.hermetic, self.base, [entry], {}) as composition:
            self.assertEqual(composition.entries()["copy.txt"].oid, old.oid)


# --------------------------------------------------------------------------- containment


class ContainmentTests(TreeCase):
    """The Project is read-only, and the composition takes its scratch away with it."""

    def test_new_blobs_are_written_only_into_the_scratch_store(self) -> None:
        data = b"never in the project\n"
        entry = self.added("added.txt", data)
        self.compose([entry], {"added.txt": data})
        present = subprocess.run(["git", "-C", str(self.store.root), "cat-file", "-e", entry.new_oid],
                                 capture_output=True, env=clean_env())
        self.assertNotEqual(present.returncode, 0, "the Candidate's blob must not enter the Project store")

    def test_the_resulting_tree_object_is_not_in_the_project_store(self) -> None:
        data = b"added\n"
        tree = self.compose([self.added("added.txt", data)], {"added.txt": data})
        present = subprocess.run(["git", "-C", str(self.store.root), "cat-file", "-e", tree],
                                 capture_output=True, env=clean_env())
        self.assertNotEqual(present.returncode, 0)

    def test_the_project_index_refs_head_and_worktree_are_untouched(self) -> None:
        index = self.store.root / ".git" / "index"
        before = index.read_bytes() if index.exists() else None
        head = git(self.store.root, "rev-parse", "HEAD").strip()
        refs = git(self.store.root, "show-ref")
        status = git(self.store.root, "status", "--porcelain")
        data = b"added\n"
        self.compose([self.added("added.txt", data)], {"added.txt": data})
        self.assertEqual(index.read_bytes() if index.exists() else None, before)
        self.assertEqual(git(self.store.root, "rev-parse", "HEAD").strip(), head)
        self.assertEqual(git(self.store.root, "show-ref"), refs)
        self.assertEqual(git(self.store.root, "status", "--porcelain"), status)

    def test_the_scratch_directory_is_removed(self) -> None:
        self.compose([])
        root = self.store.root / review_paths.RUNTIME_RESULTING_TREE_DIR
        self.assertTrue(not root.exists() or not list(root.iterdir()))

    def test_the_scratch_lives_under_the_runtime_area(self) -> None:
        self.assertTrue(review_paths.RUNTIME_RESULTING_TREE_DIR.startswith(".workline/runtime/"))

    def test_a_colliding_scratch_name_is_refused(self) -> None:
        with mock.patch.object(rt.secrets, "token_hex", return_value="fixed"):
            (self.store.root / review_paths.RUNTIME_RESULTING_TREE_DIR / "fixed").mkdir(parents=True)
            self.refusal(lambda: self.compose([]))

    def test_a_failed_composition_still_removes_its_scratch(self) -> None:
        with mock.patch.object(rt, "_materialize", side_effect=OSError("no")):
            with self.assertRaises(OSError):
                data = b"added\n"
                self.compose([self.added("added.txt", data)], {"added.txt": data})
        root = self.store.root / review_paths.RUNTIME_RESULTING_TREE_DIR
        self.assertTrue(not root.exists() or not list(root.iterdir()))


# --------------------------------------------------------------------------- contradictory input


class ContradictoryEntryTests(TreeCase):
    """The composer never manufactures a tree from entry data that disagrees with the base."""

    def test_a_duplicate_path_is_refused(self) -> None:
        data = b"added\n"
        entry = self.added("added.txt", data)
        self.refusal(lambda: self.compose([entry, entry], {"added.txt": data}))

    def test_an_old_side_that_disagrees_with_the_base_is_refused(self) -> None:
        old = self.held["keep.txt"]
        for label, entry in (
            ("wrong oid", rt.Entry("keep.txt", "M", "file", old.mode, "9" * 40, "file", "100644", old.oid, "a" * 64)),
            ("wrong mode", rt.Entry("keep.txt", "M", "file", "100755", old.oid, "file", "100644", old.oid, "a" * 64)),
            ("absent but present", rt.Entry("keep.txt", "A", "absent", "000000", ZERO_40, "file", "100644", old.oid, "a" * 64)),
            ("present but absent", rt.Entry("nope.txt", "M", "file", "100644", old.oid, "file", "100644", old.oid, "a" * 64)),
        ):
            with self.subTest(case=label):
                self.refusal(lambda entry=entry: self.compose([entry], {}))

    def test_an_invalid_kind_and_mode_pair_is_refused(self) -> None:
        oid, digest = self.blob(b"x\n")
        for kind, mode in (("file", "120000"), ("symlink", "100644"), ("gitlink", "100644"),
                           ("file", "160000"), ("absent", "100644"), ("directory", "040000")):
            with self.subTest(kind=kind, mode=mode):
                entry = rt.Entry("x", "A", "absent", "000000", ZERO_40, kind, mode, oid, digest)
                self.refusal(lambda entry=entry: self.compose([entry], {"x": b"x\n"}))

    def test_an_object_id_of_the_wrong_shape_is_refused(self) -> None:
        digest = hashlib.sha256(b"x\n").hexdigest()
        oid, _ = self.blob(b"x\n")
        for label, value in (("uppercase", oid.upper()), ("abbreviated", oid[:12]), ("too long", oid + "0"),
                             ("sha256 width in a sha1 repository", "a" * 64), ("not hex", "z" * 40)):
            with self.subTest(case=label):
                entry = rt.Entry("x", "A", "absent", "000000", ZERO_40, "file", "100644", value, digest)
                self.refusal(lambda entry=entry: self.compose([entry], {"x": b"x\n"}))

    def test_a_zero_id_on_a_present_side_and_a_non_zero_id_on_an_absent_side_are_refused(self) -> None:
        digest = hashlib.sha256(b"x\n").hexdigest()
        oid, _ = self.blob(b"x\n")
        self.refusal(lambda: self.compose(
            [rt.Entry("x", "A", "absent", "000000", ZERO_40, "file", "100644", ZERO_40, digest)], {}))
        self.refusal(lambda: self.compose(
            [rt.Entry("x", "A", "absent", "000000", oid, "file", "100644", oid, digest)], {}))

    def test_a_status_that_disagrees_with_the_two_sides_is_refused(self) -> None:
        data = b"added\n"
        oid, digest = self.blob(data)
        for status in ("M", "D", "X", ""):
            with self.subTest(status=status):
                entry = rt.Entry("added.txt", status, "absent", "000000", ZERO_40, "file", "100644", oid, digest)
                self.refusal(lambda entry=entry: self.compose([entry], {"added.txt": data}))

    def test_an_entry_absent_on_both_sides_declares_nothing(self) -> None:
        entry = rt.Entry("x", "D", "absent", "000000", ZERO_40, "absent", "000000", ZERO_40, None)
        self.refusal(lambda: self.compose([entry], {}))

    def test_bytes_that_are_not_the_ones_the_candidate_froze_are_never_substituted(self) -> None:
        data = b"declared\n"
        entry = self.added("added.txt", data)
        self.refusal(lambda: self.compose([entry], {"added.txt": b"different\n"}))

    def test_a_content_digest_that_disagrees_is_refused(self) -> None:
        data = b"added\n"
        oid, _ = self.blob(data)
        entry = rt.Entry("added.txt", "A", "absent", "000000", ZERO_40, "file", "100644", oid, "0" * 64)
        self.refusal(lambda: self.compose([entry], {"added.txt": data}))

    def test_a_content_digest_where_there_are_no_bytes_is_refused(self) -> None:
        entry = rt.Entry("submod", "A", "absent", "000000", ZERO_40, "gitlink", "160000", "1" * 40, "a" * 64)
        self.refusal(lambda: self.compose([entry], {}))

    def test_a_file_with_no_digest_is_refused(self) -> None:
        oid, _ = self.blob(b"x\n")
        entry = rt.Entry("x", "A", "absent", "000000", ZERO_40, "file", "100644", oid, None)
        self.refusal(lambda: self.compose([entry], {"x": b"x\n"}))

    def test_missing_bytes_this_repository_does_not_hold_are_refused(self) -> None:
        entry = rt.Entry("x", "A", "absent", "000000", ZERO_40, "file", "100644", "3" * 40,
                         hashlib.sha256(b"x\n").hexdigest())
        self.refusal(lambda: self.compose([entry], {}))

    def test_a_child_beneath_an_existing_object_is_refused(self) -> None:
        """Measured: Git accepts this and writes a tree, so the conflict is refused here."""
        data = b"child\n"
        entry = self.added("keep.txt/child", data)
        self.refusal(lambda: self.compose([entry], {"keep.txt/child": data}))

    def test_a_child_beneath_a_path_the_candidate_itself_adds_is_refused(self) -> None:
        one, two = b"one\n", b"two\n"
        entries = [self.added("new", one), self.added("new/child", two)]
        self.refusal(lambda: self.compose(entries, {"new": one, "new/child": two}))

    def test_a_path_that_is_not_a_canonical_relative_spelling_is_refused(self) -> None:
        data = b"x\n"
        oid, digest = self.blob(data)
        for path in ("/abs.txt", "a\\b.txt", "./a.txt", "a/../b.txt", "a//b.txt", "C:/x.txt", "", "a/./b"):
            with self.subTest(path=path):
                entry = rt.Entry(path, "A", "absent", "000000", ZERO_40, "file", "100644", oid, digest)
                self.refusal(lambda entry=entry: self.compose([entry], {path: data}))

    def test_a_declared_base_that_is_not_an_exact_object_id_is_refused(self) -> None:
        for basis in ("HEAD", "main", self.base[:12], self.base.upper(), ""):
            with self.subTest(basis=basis):
                self.refusal(lambda basis=basis: rt.resulting_tree_id(self.store, self.hermetic, basis, [], {}))

    def test_an_entry_record_of_the_wrong_shape_is_refused(self) -> None:
        good = {field: "x" for field in rt.ENTRY_FIELDS}
        self.refusal(lambda: rt.entries_from_records([{**good, "extra": 1}]))
        self.refusal(lambda: rt.entries_from_records([{k: v for k, v in good.items() if k != "path"}]))
        self.refusal(lambda: rt.entries_from_records(["not a mapping"]))

    def test_the_frozen_candidate_entry_fields_are_the_contracts_nine(self) -> None:
        self.assertEqual(rt.ENTRY_FIELDS, (
            "path", "status", "old_kind", "old_mode", "old_oid",
            "new_kind", "new_mode", "new_oid", "content_sha256",
        ))
        records = [{
            "path": "added.txt", "status": "A", "old_kind": "absent", "old_mode": "000000",
            "old_oid": ZERO_40, "new_kind": "file", "new_mode": "100644",
            "new_oid": self.blob(b"a\n")[0], "content_sha256": self.blob(b"a\n")[1],
        }]
        built = rt.entries_from_records(records)
        self.assertEqual(built[0].path, "added.txt")
        self.assertFalse(built[0].inert)


# --------------------------------------------------------------------------- both object formats


class ObjectFormatTests(WorklineTestCase):
    """A basis is whatever identity its repository stores; no width is assumed."""

    def project_with_format(self, object_format: str) -> ProjectStore:
        root = self.new_dir(f"fmt-{object_format}")
        made = subprocess.run(
            ["git", "init", "-q", "-b", "main", f"--object-format={object_format}", str(root)],
            capture_output=True, text=True,
        )
        if made.returncode != 0:
            self.skipTest(f"this Git cannot create a {object_format} repository: {made.stderr.strip()[:80]}")
        git(root, "config", "user.name", "A")
        git(root, "config", "user.email", "a@x")
        (root / ".workline").mkdir(exist_ok=True)
        (root / "keep.txt").write_text("keep\n", encoding="utf-8", newline="\n")
        git(root, "add", "-A")
        git(root, "commit", "-m", "base")
        return ProjectStore(root)

    def check(self, object_format: str, width: int) -> None:
        store = self.project_with_format(object_format)
        built = hermetic.enter(store)
        base = git(store.root, "rev-parse", "HEAD").strip()
        self.assertEqual(len(base), width)
        base_tree = rt.root_tree_id(built, base)
        self.assertEqual(len(base_tree), width)
        self.assertEqual(base_tree, git(store.root, "rev-parse", "HEAD^{tree}").strip())
        self.assertEqual(rt.resulting_tree_id(store, built, base, [], {}), base_tree)

        data = b"added\n"
        oid = gitcmd.hash_blob(store.root, data)
        self.assertEqual(len(oid), width)
        entry = rt.Entry("added.txt", "A", "absent", "000000", gitcmd.zero_object_id(base),
                         "file", "100644", oid, hashlib.sha256(data).hexdigest())
        with rt.composed(store, built, base, [entry], {"added.txt": data}) as composition:
            self.assertEqual(len(composition.tree), width)
            self.assertNotEqual(composition.tree, base_tree)
            self.assertEqual(composition.entries()["added.txt"].oid, oid)

    def test_sha1_forty_hex(self) -> None:
        self.check("sha1", 40)

    def test_sha256_sixty_four_hex(self) -> None:
        self.check("sha256", 64)


# --------------------------------------------------------------------------- the unit boundary


class UnitBoundaryTests(unittest.TestCase):
    """Unit 4 is a foundation: it composes a tree identity and dispatches nothing."""

    def test_no_commit_primitive_is_reachable_from_the_composer(self) -> None:
        import inspect

        source = inspect.getsource(rt)
        for forbidden in ("commit-tree", "update-ref", "\"commit\"", "'commit'"):
            with self.subTest(token=forbidden):
                self.assertNotIn(f'run("{forbidden}', source)
                self.assertNotIn(f'run_bytes("{forbidden}', source)

    def test_later_unit_machinery_is_still_absent(self) -> None:
        from workline import mutation
        from workline.review.store import ReviewStore

        self.assertFalse(hasattr(mutation, "WORK_COMMIT_MODE"))
        self.assertEqual(mutation.PLANNING_COMMIT_MODE, "review-v1-planning-local-v1")
        for name in ("CommitTreePlan", "prepared_commit_id", "compose_commit"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(rt, name))
        for writer in ("write_activation", "create_activation", "activate", "produce_activation"):
            with self.subTest(writer=writer):
                self.assertFalse(hasattr(ReviewStore, writer))

    def test_nothing_in_production_dispatches_into_the_composer(self) -> None:
        from workline import gitops, mutation, roadmap_review, start
        from workline.review import checkout, planning, publication

        for module in (gitops, mutation, roadmap_review, start, checkout, planning, publication):
            with self.subTest(module=module.__name__):
                self.assertFalse(hasattr(module, "resulting_tree"))

    def test_the_planning_checkout_capability_is_untouched(self) -> None:
        from workline.review import checkout

        self.assertEqual(checkout.CHECKOUT_CONTRACT, "review-v1-planning-checkout-v1")


if __name__ == "__main__":
    unittest.main()
