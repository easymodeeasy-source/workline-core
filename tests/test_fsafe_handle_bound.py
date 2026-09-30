"""The two handle-bound readers `fsafe` did not expose: final-object identity, submodule HEAD.

P3 F3 §7.8.4 layer 2 sub-steps 2a-2e and the 160000 gitlink section G-1 ... G-5,
IP-21 (the reader foundation only - nothing here is wired into a consumer).

Two properties are what these tests are actually about.

A FINAL indirection is IDENTIFIED, not refused. `read_file` and `child` answer
"may I use this?", and for a symlink the answer is no; `final_object` answers
"what IS this?", and a symlink is one of the answers. The distinction cost a
draft: an `O_NOFOLLOW` open of a final symlink fails with ELOOP instead of
identifying it, so every lawful F2 mode-120000 result would have been refused
before its own rules ever ran. An ANCESTOR indirection stays refused, and these
tests hold both halves at once.

A submodule's HEAD is read through HELD HANDLES. `git -C <path> rev-parse HEAD`
gives the right answer for the wrong reason - it hands a pathname to a second
process which resolves it from the root again - so the reader is proven here to
produce Git's own answer with every Git and subprocess route patched to raise.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from helpers import WorklineTestCase
from workline.errors import ValidationError
from workline.review import fsafe

WINDOWS = sys.platform == "win32"


def git(where: Path, *args: str, check: bool = True) -> str:
    """Test-fixture Git only. The production readers under test run none of this."""
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    environment.update({
        "GIT_AUTHOR_NAME": "Real Person", "GIT_AUTHOR_EMAIL": "real@proj",
        "GIT_COMMITTER_NAME": "Real Person", "GIT_COMMITTER_EMAIL": "real@proj",
    })
    found = subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True, env=environment)
    if check and found.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {where}: {found.stderr}")
    return found.stdout.strip()


def make_indirection(kind: str, link: Path, target: Path) -> bool:
    """A symlink or junction, or False when this account may not create one."""
    if WINDOWS:
        flag = {"file": [], "dir": ["/D"], "junction": ["/J"]}[kind]
        found = subprocess.run(["cmd", "/c", "mklink", *flag, str(link), str(target)],
                               capture_output=True, text=True)
        return found.returncode == 0
    link.symlink_to(target)
    return True


class FsafeCase(WorklineTestCase):
    def root(self, where: Path) -> fsafe.SafeDirectory:
        found = fsafe.SafeDirectory.open_root(where)
        self.addCleanup(found.close)
        return found

    def refusal(self, call) -> ValidationError:
        with self.assertRaises(ValidationError) as caught:
            call()
        self.assertEqual(caught.exception.code, fsafe.CODE)
        return caught.exception


# --------------------------------------------------------------------------- primitive A


class FinalObjectTests(FsafeCase):
    """§7.8.4 2d: what the name denotes, without following it."""

    def setUp(self) -> None:
        super().setUp()
        self.where = self.new_dir("objects")
        (self.where / "plain.txt").write_bytes(b"plain\n")
        (self.where / "other.txt").write_bytes(b"other\n")
        (self.where / "adir").mkdir()
        self.held = self.root(self.where)

    def test_a_missing_name_is_absent_and_not_an_exception(self) -> None:
        self.assertIsNone(self.held.final_object("nothing-here"))

    def test_a_plain_file_is_identified(self) -> None:
        found = self.held.final_object("plain.txt")
        self.assertIsNotNone(found)
        self.assertEqual((found.is_file, found.is_dir, found.is_indirection), (True, False, False))
        self.assertIsNotNone(found.identity)

    def test_a_plain_directory_is_identified(self) -> None:
        found = self.held.final_object("adir")
        self.assertEqual((found.is_file, found.is_dir, found.is_indirection), (False, True, False))

    def test_two_distinct_objects_have_distinct_identities(self) -> None:
        self.assertNotEqual(self.held.final_object("plain.txt").identity,
                            self.held.final_object("other.txt").identity)
        self.assertNotEqual(self.held.final_object("plain.txt").identity,
                            self.held.final_object("adir").identity)

    def test_the_same_object_gives_the_same_identity_every_time(self) -> None:
        self.assertEqual(self.held.final_object("plain.txt").identity,
                         self.held.final_object("plain.txt").identity)

    def test_two_names_for_one_physical_object_compare_equal(self) -> None:
        """A hard link is the cleanest statement of what the identity means."""
        link = self.where / "hard.txt"
        if WINDOWS:
            made = subprocess.run(["cmd", "/c", "mklink", "/H", str(link), str(self.where / "plain.txt")],
                                  capture_output=True, text=True).returncode == 0
        else:
            try:
                os.link(self.where / "plain.txt", link)
                made = True
            except OSError:
                made = False
        if not made:
            self.skipTest("this filesystem or account cannot create a hard link")
        self.assertEqual(self.held.final_object("hard.txt").identity,
                         self.held.final_object("plain.txt").identity)

    def test_a_final_symlink_is_identified_and_never_followed(self) -> None:
        """The central regression: the link's own identity, not its target's."""
        if not make_indirection("file", self.where / "flink", self.where / "plain.txt"):
            self.skipTest("file symlinks need a privilege this Windows account does not hold")
        found = self.held.final_object("flink")
        self.assertIsNotNone(found, "a final symlink must be identified, not reported absent")
        self.assertTrue(found.is_indirection)
        self.assertFalse(found.is_file, "the link is not the file it points at")
        self.assertNotEqual(found.identity, self.held.final_object("plain.txt").identity)

    def test_a_final_directory_symlink_is_identified_and_never_followed(self) -> None:
        if not make_indirection("dir", self.where / "dlink", self.where / "adir"):
            self.skipTest("directory symlinks need a privilege this Windows account does not hold")
        found = self.held.final_object("dlink")
        self.assertTrue(found.is_indirection)
        self.assertFalse(found.is_dir, "the link is not the directory it points at")
        self.assertNotEqual(found.identity, self.held.final_object("adir").identity)

    @unittest.skipUnless(WINDOWS, "a junction is a Windows reparse point")
    def test_a_final_junction_is_identified_and_never_followed(self) -> None:
        if not make_indirection("junction", self.where / "jdir", self.where / "adir"):
            self.skipTest("this account cannot create a junction")
        found = self.held.final_object("jdir")
        self.assertTrue(found.is_indirection, "a junction is a reparse point even though os.path calls it a directory")
        self.assertFalse(found.is_dir)
        self.assertNotEqual(found.identity, self.held.final_object("adir").identity)

    def test_the_query_takes_one_component_and_never_a_path(self) -> None:
        for name in ("", ".", "..", "a/b", "a\\b", "a\0b"):
            with self.subTest(name=name):
                self.refusal(lambda name=name: self.held.final_object(name))

    def test_identifying_an_indirection_does_not_make_the_walk_permissive(self) -> None:
        """The other half: an ANCESTOR indirection is still a containment failure."""
        kind = "junction" if WINDOWS else "dir"
        if not make_indirection(kind, self.where / "ancestor", self.where / "adir"):
            self.skipTest(f"this account cannot create a {kind} indirection")
        self.assertTrue(self.held.final_object("ancestor").is_indirection)
        self.refusal(lambda: self.held.child("ancestor"))
        # and the walk refuses rather than reporting it absent: an indirection present is not a gap
        self.refusal(lambda: fsafe.walk(self.where, ["ancestor"]))
        self.refusal(lambda: fsafe.walk(self.where, ["ancestor", "deeper"]))

    def test_repeated_queries_leak_no_handle(self) -> None:
        for _ in range(400):
            self.assertIsNotNone(self.held.final_object("plain.txt"))
            self.assertIsNone(self.held.final_object("nothing-here"))
        self.assertIsNotNone(self.held.final_object("adir"))

    def test_a_failed_query_still_closes_what_it_opened(self) -> None:
        for _ in range(200):
            self.refusal(lambda: self.held.final_object("a/b"))
        self.assertIsNotNone(self.held.final_object("plain.txt"))


# --------------------------------------------------------------------------- primitive B


class SubmoduleCase(FsafeCase):
    """A real LOCAL submodule. No network, no clone from anywhere but this temp directory."""

    def setUp(self) -> None:
        super().setUp()
        self.subrepo = self.new_dir("subrepo")
        git(self.subrepo, "init", "-b", "main")
        git(self.subrepo, "config", "user.name", "Real Person")
        git(self.subrepo, "config", "user.email", "real@proj")
        (self.subrepo / "a.txt").write_text("a\n", encoding="utf-8", newline="\n")
        git(self.subrepo, "add", "-A")
        git(self.subrepo, "commit", "-m", "sub base", "--no-verify")

        self.super = self.new_dir("super")
        git(self.super, "init", "-b", "main")
        git(self.super, "config", "user.name", "Real Person")
        git(self.super, "config", "user.email", "real@proj")
        git(self.super, "-c", "protocol.file.allow=always", "submodule", "add", self.subrepo.as_uri(), "sub")
        git(self.super, "commit", "-m", "add sub", "--no-verify")
        self.gitdir = self.super / ".git" / "modules" / "sub"

    def read(self) -> str:
        """The reader under test, over a chain walked to the submodule working tree."""
        chain = fsafe.walk(self.super, ["sub"])
        self.assertIsNotNone(chain, "the submodule working tree must be walkable")
        with chain:
            return fsafe.submodule_head(chain)

    def oracle(self) -> str:
        return git(self.super / "sub", "rev-parse", "HEAD")

    def staged(self) -> str:
        return git(self.super, "ls-files", "--stage", "sub").split()[1]

    def advance(self) -> str:
        """One more commit inside the submodule, deliberately NOT staged in the superproject."""
        (self.subrepo / "b.txt").write_text("b\n", encoding="utf-8", newline="\n")
        working = self.super / "sub"
        (working / "b.txt").write_text("b\n", encoding="utf-8", newline="\n")
        git(working, "add", "-A")
        git(working, "commit", "-m", "sub advance", "--no-verify")
        return git(working, "rev-parse", "HEAD")


class SubmoduleHeadTests(SubmoduleCase):
    """§7.8.4 G-1 ... G-5 over a real submodule."""

    def test_the_fixture_is_the_shape_the_contract_measured(self) -> None:
        """M-46: `.git` is a FILE holding a RELATIVE gitdir, which is why G-3 exists at all."""
        dotgit = self.super / "sub" / ".git"
        self.assertTrue(dotgit.is_file(), "a real submodule's .git is a gitfile, not a directory")
        raw = dotgit.read_bytes()
        self.assertTrue(raw.startswith(b"gitdir: "))
        value = raw.decode("utf-8").split(":", 1)[1].strip()
        self.assertFalse(value.startswith("/"), "and the gitdir it declares is relative")
        self.assertTrue(self.gitdir.is_dir())

    def test_the_reader_reproduces_gits_own_answer(self) -> None:
        found = self.read()
        self.assertEqual(found, self.oracle())
        self.assertEqual(found, self.staged())

    def test_the_answer_is_an_exact_full_lowercase_object_id(self) -> None:
        found = self.read()
        self.assertRegex(found, r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
        self.assertNotIn("\n", found)
        self.assertEqual(found, found.strip())

    def test_the_reader_runs_no_git_process(self) -> None:
        """Y: every route to a second process raises, and the reader still answers exactly."""
        expected = self.oracle()
        blocked = AssertionError("the handle-bound reader must not run a process")

        def refuse(*args, **kwargs):
            raise blocked

        with mock.patch.object(subprocess, "run", refuse), \
             mock.patch.object(subprocess, "Popen", refuse), \
             mock.patch.object(subprocess, "check_output", refuse), \
             mock.patch.object(os, "system", refuse), \
             mock.patch.object(os, "popen", refuse):
            found = self.read()
        self.assertEqual(found, expected)

    def test_the_superproject_index_is_not_the_answer(self) -> None:
        """W/X: the index still names the OLD commit, and reading it would witness the pre-executor value."""
        before = self.read()
        advanced = self.advance()
        self.assertNotEqual(advanced, before)
        self.assertEqual(self.staged(), before, "the fixture must leave the gitlink unstaged")
        self.assertEqual(self.read(), advanced)
        self.assertEqual(self.read(), self.oracle())

    def test_a_detached_head_is_supported(self) -> None:
        head = self.oracle()
        (self.gitdir / "HEAD").write_text(f"{head}\n", encoding="utf-8", newline="\n")
        self.assertEqual(self.read(), head)

    def test_a_symbolic_head_resolves_through_a_loose_ref(self) -> None:
        head = self.oracle()
        self.assertEqual((self.gitdir / "HEAD").read_bytes(), b"ref: refs/heads/main\n")
        self.assertTrue((self.gitdir / "refs" / "heads" / "main").is_file())
        self.assertEqual(self.read(), head)

    def test_a_symbolic_head_falls_back_to_packed_refs(self) -> None:
        head = self.oracle()
        loose = self.gitdir / "refs" / "heads" / "main"
        loose.unlink()
        (self.gitdir / "packed-refs").write_text(
            "# pack-refs with: peeled fully-peeled sorted \n"
            f"{'0' * 40} refs/heads/main2\n"
            f"{head} refs/heads/main\n"
            f"^{'1' * 40}\n"
            f"{'2' * 40} refs/tags/v1\n",
            encoding="utf-8", newline="\n",
        )
        self.assertEqual(self.read(), head)

    def test_a_packed_ref_is_matched_by_exact_name(self) -> None:
        """refs/heads/main must not be answered by refs/heads/main2."""
        head = self.oracle()
        (self.gitdir / "refs" / "heads" / "main").unlink()
        (self.gitdir / "packed-refs").write_text(
            f"{'3' * 40} refs/heads/main2\n{'4' * 40} refs/heads/mai\n{head} refs/heads/main\n",
            encoding="utf-8", newline="\n",
        )
        self.assertEqual(self.read(), head)
        (self.gitdir / "packed-refs").write_text(
            f"{'3' * 40} refs/heads/main2\n{'4' * 40} refs/heads/mainx\n", encoding="utf-8", newline="\n")
        self.refusal(self.read)

    def test_a_git_directory_instead_of_a_gitfile_is_supported(self) -> None:
        """G-2/G-3 collapse: `.git` as a plain directory needs no gitdir resolution."""
        head = self.oracle()
        working = self.super / "sub"
        (working / ".git").unlink()
        moved = working / ".git"
        moved.mkdir()
        for item in self.gitdir.iterdir():
            os.replace(item, moved / item.name)
        self.assertTrue((moved / "HEAD").is_file())
        self.assertEqual(self.read(), head)

    def test_repeated_reads_leak_no_handle(self) -> None:
        head = self.oracle()
        for _ in range(60):
            self.assertEqual(self.read(), head)


class SubmoduleAdversarialTests(SubmoduleCase):
    """Everything that must fail closed rather than be rescued by a broader parser."""

    def gitfile(self, text: str, *, raw: bytes | None = None) -> None:
        """Replace the submodule's gitfile. Git marks it hidden on Windows, so it is removed first."""
        where = self.super / "sub" / ".git"
        where.unlink()
        where.write_bytes(raw if raw is not None else text.encode("utf-8"))

    def head(self, text: str) -> None:
        (self.gitdir / "HEAD").write_text(text, encoding="utf-8", newline="\n")

    def loose(self, text: str) -> None:
        (self.gitdir / "refs" / "heads" / "main").write_text(text, encoding="utf-8", newline="\n")

    # ---- the gitfile
    def test_an_absolute_gitdir_is_refused(self) -> None:
        for value in (f"/{self.gitdir.as_posix().lstrip('/')}", "/etc/git", "C:/Windows/git",
                      "//server/share/git", "\\\\server\\share\\git", "c:git"):
            with self.subTest(value=value):
                self.gitfile(f"gitdir: {value}\n")
                self.refusal(self.read)

    def test_a_gitdir_climbing_above_the_project_root_is_refused(self) -> None:
        for value in ("../../..", "../../../.git/modules/sub", "../.././../elsewhere"):
            with self.subTest(value=value):
                self.gitfile(f"gitdir: {value}\n")
                self.refusal(self.read)

    def test_a_gitdir_component_that_is_an_indirection_is_refused(self) -> None:
        kind = "junction" if WINDOWS else "dir"
        decoy = self.new_dir("decoy-gitdir")
        if not make_indirection(kind, self.super / "linked", decoy):
            self.skipTest(f"this account cannot create a {kind} indirection")
        self.gitfile("gitdir: ../linked\n")
        self.refusal(self.read)

    def test_a_missing_gitdir_component_is_refused(self) -> None:
        self.gitfile("gitdir: ../.git/modules/nowhere\n")
        self.refusal(self.read)

    def test_a_malformed_gitfile_is_refused(self) -> None:
        for text in ("", "\n", "gitdir:\n", "gitdir: \n", "not a gitfile\n",
                     "gitdir: ../.git/modules/sub\ngitdir: ../elsewhere\n",
                     "gitdir: ../.git/modules/sub\nstray line\n",
                     "gitdir: ..//.git/modules/sub\n", "gitdir: ../.git/./modules/sub\n",
                     "gitdir: ..\\.git\\modules\\sub\n"):
            with self.subTest(text=text):
                self.gitfile(text)
                self.refusal(self.read)

    def test_a_gitfile_holding_a_nul_is_refused(self) -> None:
        self.gitfile("", raw=b"gitdir: ../.git/modules/\0sub\n")
        self.refusal(self.read)

    def test_a_dot_git_indirection_is_refused(self) -> None:
        kind = "junction" if WINDOWS else "dir"
        (self.super / "sub" / ".git").unlink()
        if not make_indirection(kind, self.super / "sub" / ".git", self.gitdir):
            self.skipTest(f"this account cannot create a {kind} indirection")
        self.refusal(self.read)

    # ---- HEAD
    def test_a_malformed_head_is_refused(self) -> None:
        head = self.oracle()
        for text in ("", "\n", "not an id\n", f"{head[:12]}\n", f"{head.upper()}\n",
                     f"{head} junk\n", f"{head}junk\n", f"{head}\nsecond line\n",
                     "ref:\n", "ref: \n", "ref: /refs/heads/main\n", "ref: C:/refs/heads/main\n",
                     "ref: ../../../etc/passwd\n", "ref: refs/../../escape\n",
                     "ref: refs//heads/main\n", "ref: refs/heads/./main\n",
                     "ref: refs\\heads\\main\n", f"{head}{head}\n", f"{head[:39]}\n",
                     f"{head[:63]}z\n", f"{head[:39]}z\n", f" {head}\n", f"{head} \n"):
            with self.subTest(text=text):
                self.head(text)
                self.refusal(self.read)

    def test_a_head_holding_a_nul_is_refused(self) -> None:
        (self.gitdir / "HEAD").write_bytes(self.oracle().encode("ascii") + b"\0\n")
        self.refusal(self.read)

    # ---- the refs
    def test_a_malformed_loose_ref_is_refused_and_never_falls_back(self) -> None:
        """§19: a present-but-malformed loose ref is a refusal, not a reason to read packed-refs."""
        head = self.oracle()
        (self.gitdir / "packed-refs").write_text(f"{head} refs/heads/main\n", encoding="utf-8", newline="\n")
        for text in ("", "\n", f"{head[:12]}\n", f"{head.upper()}\n", "not an id\n", f"{head} extra\n"):
            with self.subTest(text=text):
                self.loose(text)
                self.refusal(self.read)

    def test_a_malformed_packed_record_for_the_named_ref_is_refused(self) -> None:
        head = self.oracle()
        (self.gitdir / "refs" / "heads" / "main").unlink()
        for record in (f"{head[:12]} refs/heads/main", f"{head.upper()} refs/heads/main",
                       "notanid refs/heads/main"):
            with self.subTest(record=record):
                (self.gitdir / "packed-refs").write_text(record + "\n", encoding="utf-8", newline="\n")
                self.refusal(self.read)

    def test_a_ref_absent_from_both_loose_and_packed_is_refused(self) -> None:
        (self.gitdir / "refs" / "heads" / "main").unlink()
        self.refusal(self.read)
        (self.gitdir / "packed-refs").write_text(f"{'5' * 40} refs/heads/other\n",
                                                 encoding="utf-8", newline="\n")
        self.refusal(self.read)

    def test_a_directory_on_the_ref_path_that_is_missing_falls_back_rather_than_crashing(self) -> None:
        head = self.oracle()
        for item in (self.gitdir / "refs" / "heads").iterdir():
            item.unlink()
        (self.gitdir / "refs" / "heads").rmdir()
        (self.gitdir / "packed-refs").write_text(f"{head} refs/heads/main\n", encoding="utf-8", newline="\n")
        self.assertEqual(self.read(), head)

    def test_a_chain_holding_nothing_is_refused(self) -> None:
        self.refusal(lambda: fsafe.submodule_head(fsafe.Chain([])))


class GitOracleGrammarTests(SubmoduleCase):
    """The gitfile grammar is Git's, measured against Git, not a grammar of our own.

    The reader exists to reproduce the commit Git names for a submodule. A
    spelling Git refuses as a gitfile therefore has no commit to reproduce, and
    synthesising one by tidying whitespace would report an identity for a
    working tree Git itself cannot open.
    """

    def git_says(self, *args: str) -> str:
        found = subprocess.run(
            ["git", "-C", str(self.super / "sub"), *args], capture_output=True, text=True,
            env={**{k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")},
                 "GIT_AUTHOR_NAME": "R", "GIT_AUTHOR_EMAIL": "r@p",
                 "GIT_COMMITTER_NAME": "R", "GIT_COMMITTER_EMAIL": "r@p"},
        )
        return found.stdout.strip() if found.returncode == 0 else "REFUSE"

    def reader_says(self) -> str:
        try:
            return self.read()
        except ValidationError:
            return "REFUSE"

    def gitfile(self, raw: bytes) -> None:
        where = self.super / "sub" / ".git"
        where.unlink()                       # Git marks it hidden on Windows
        where.write_bytes(raw)

    #: (label, bytes, does Git accept it)
    def spellings(self) -> list:
        p = b"../.git/modules/sub"
        return [
            ("canonical 'gitdir: X'", b"gitdir: " + p + b"\n", True),
            ("blank line AFTER", b"gitdir: " + p + b"\n\n", True),
            ("no final newline", b"gitdir: " + p, True),
            ("no space 'gitdir:X'", b"gitdir:" + p + b"\n", False),
            ("two spaces 'gitdir:  X'", b"gitdir:  " + p + b"\n", False),
            ("tab after the colon", b"gitdir:\t" + p + b"\n", False),
            ("trailing space", b"gitdir: " + p + b" \n", False),
            ("trailing tab", b"gitdir: " + p + b"\t\n", False),
            ("blank line BEFORE", b"\ngitdir: " + p + b"\n", False),
            ("space before 'gitdir'", b" gitdir: " + p + b"\n", False),
            ("upper-case GITDIR:", b"GITDIR: " + p + b"\n", False),
            ("declaration with no path", b"gitdir: \n", False),
            ("stray line after", b"gitdir: " + p + b"\nstray\n", False),
            ("second declaration", b"gitdir: " + p + b"\ngitdir: ../elsewhere\n", False),
        ]

    def test_the_reader_agrees_with_git_on_every_measured_spelling(self) -> None:
        head = self.oracle()
        for label, raw, git_accepts in self.spellings():
            with self.subTest(case=label):
                self.gitfile(raw)
                said = self.git_says("rev-parse", "HEAD")
                self.assertEqual(said, head if git_accepts else "REFUSE",
                                 f"the Git oracle changed for {label}; re-measure before trusting this test")
                self.assertEqual(self.reader_says(), said,
                                 f"the reader must not differ from Git for {label}")

    def test_no_malformed_spelling_is_normalized_into_an_object_id(self) -> None:
        """The decisive half: not one Git-refused spelling yields an OID."""
        for label, raw, git_accepts in self.spellings():
            if git_accepts:
                continue
            with self.subTest(case=label):
                self.gitfile(raw)
                self.refusal(self.read)

    def test_the_declaration_is_matched_as_exact_bytes_not_a_stripped_prefix(self) -> None:
        import inspect

        source = inspect.getsource(fsafe._gitdir_components)
        self.assertIn("GITDIR_DECLARATION", source)
        self.assertIn("raw.startswith(GITDIR_DECLARATION)", source)
        self.assertEqual(fsafe.GITDIR_DECLARATION, b"gitdir: ")
        # the declared VALUE is never tidied; the only strip left detects a non-empty leftover line
        value_line = [line for line in source.splitlines() if "value =" in line]
        self.assertTrue(value_line, "the value assignment must be findable")
        for line in value_line:
            self.assertNotIn("strip", line, f"the value is taken verbatim: {line.strip()}")

    def test_a_lawful_path_holding_a_space_is_still_accepted(self) -> None:
        """Verbatim must not become 'no spaces anywhere': a directory may legitimately hold one."""
        head = self.oracle()
        modules = self.super / ".git" / "modules"
        os.replace(modules / "sub", modules / "with space")
        try:
            self.gitfile(b"gitdir: ../.git/modules/with space\n")
            self.assertEqual(self.git_says("rev-parse", "HEAD"), head)
            self.assertEqual(self.read(), head)
        finally:
            os.replace(modules / "with space", modules / "sub")

    def test_crlf_stays_refused_and_is_the_deferred_finding(self) -> None:
        """Git accepts a CRLF gitfile and HEAD; this reader refuses. Fail-closed, and left alone."""
        self.gitfile(b"gitdir: ../.git/modules/sub\r\n")
        self.assertEqual(self.git_says("rev-parse", "HEAD"), self.oracle())
        self.refusal(self.read)
        self.gitfile(b"gitdir: ../.git/modules/sub\n")
        (self.gitdir / "HEAD").write_bytes(b"ref: refs/heads/main\r\n")
        self.assertEqual(self.git_says("rev-parse", "HEAD"), self.oracle())
        self.refusal(self.read)


class AlternateDataStreamTests(SubmoduleCase):
    """A colon is not part of a ref name, and on NTFS it addresses a hidden stream."""

    def test_the_bounded_audit_of_git_invalid_spellings(self) -> None:
        """Only the colon reaches a hidden alternate of the real object; the rest are ordinary files."""
        where = self.new_dir("vectors")
        (where / "main").write_bytes(b"REAL\n")
        with fsafe.SafeDirectory.open_root(where) as root:
            for name in ("main[x]", "main~1", "main^", "main.lock"):
                with self.subTest(name=name):
                    (where / name).write_bytes(b"OTHER\n")
                    self.assertIn(name, [entry.name for entry in root.entries()],
                                  "an ordinary file, visible in a listing")
                    self.assertEqual(root.read_file("main"), b"REAL\n", "and the real ref is untouched")

    @unittest.skipUnless(WINDOWS, "an alternate data stream is an NTFS feature")
    def test_a_stream_beside_a_ref_is_invisible_and_reads_back_differently(self) -> None:
        """The fact that makes the refusal necessary - kept, not deleted."""
        where = self.new_dir("ads")
        (where / "main").write_bytes(b"REAL\n")
        try:
            with open(str(where / "main") + ":evil", "w", encoding="utf-8", newline="\n") as handle:
                handle.write("ADS\n")
        except OSError:
            self.skipTest("this filesystem does not support alternate data streams")
        with fsafe.SafeDirectory.open_root(where) as root:
            self.assertEqual([entry.name for entry in root.entries()], ["main"],
                             "no listing of the namespace shows the stream")
            self.assertEqual(root.read_file("main"), b"REAL\n")
            self.assertEqual(root.read_file("main:evil"), b"ADS\n",
                             "read_file can open it, which is exactly why the refname must refuse first")

    @unittest.skipUnless(WINDOWS, "an alternate data stream is an NTFS feature")
    def test_a_stream_can_never_become_the_submodule_identity(self) -> None:
        real = self.oracle()
        evil = "1" * 40
        main = self.gitdir / "refs" / "heads" / "main"
        try:
            with open(str(main) + ":evil", "w", encoding="utf-8", newline="\n") as handle:
                handle.write(evil + "\n")
        except OSError:
            self.skipTest("this filesystem does not support alternate data streams")
        self.assertEqual(main.read_text().strip(), real)
        # Git refuses the name and refuses the HEAD that points at it
        environment = {**{k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}}
        refused = subprocess.run(["git", "-C", str(self.super / "sub"), "check-ref-format",
                                  "refs/heads/main:evil"], capture_output=True, text=True, env=environment)
        self.assertNotEqual(refused.returncode, 0, "git check-ref-format must reject the name")

        (self.gitdir / "HEAD").write_bytes(b"ref: refs/heads/main:evil\n")
        found = subprocess.run(["git", "-C", str(self.super / "sub"), "rev-parse", "HEAD"],
                               capture_output=True, text=True, env=environment)
        self.assertNotEqual(found.returncode, 0, "git rev-parse must refuse such a HEAD")
        error = self.refusal(self.read)
        self.assertIn("colon", str(error))
        self.assertNotIn(evil, str(error), "the stream's content never reaches the answer")

    def test_a_colon_is_refused_in_every_component_position(self) -> None:
        for refname in ("refs/heads/main:evil", "refs/he:ads/main", "refs/heads/ma:in/x",
                        "refs/heads/main::x", "C:/refs/heads/main", ":refs/heads/main"):
            with self.subTest(refname=refname):
                (self.gitdir / "HEAD").write_text(f"ref: {refname}\n", encoding="utf-8", newline="\n")
                self.refusal(self.read)

    def test_the_refusal_happens_before_any_filesystem_lookup(self) -> None:
        """Instrumented: read_file is never reached for a colon-bearing ref name."""
        (self.gitdir / "HEAD").write_bytes(b"ref: refs/heads/main:evil\n")
        looked_up: list = []
        original = fsafe.SafeDirectory.read_file

        def spy(self, name):
            looked_up.append(name)
            return original(self, name)

        with mock.patch.object(fsafe.SafeDirectory, "read_file", spy):
            self.refusal(self.read)
        self.assertNotIn("main:evil", looked_up, "the colon must be refused before the lookup")
        self.assertTrue(any(name == "HEAD" for name in looked_up), "HEAD itself was still read")

    def test_the_shared_component_predicate_was_not_changed(self) -> None:
        """The refusal belongs to Unit 5's refname rule, not to fsafe's general component rule."""
        where = self.new_dir("predicate")
        (where / "a:b").write_bytes(b"x\n") if False else None
        with fsafe.SafeDirectory.open_root(where) as root:
            self.assertIsNone(root.read_file("nothing:here"),
                              "read_file still treats a colon name as an ordinary absent name")


class PackedRefUniquenessTests(SubmoduleCase):
    """One exact referenced object id, or a refusal - never whichever record was scanned first."""

    def setUp(self) -> None:
        super().setUp()
        self.head = self.oracle()                           # while the loose ref still answers
        (self.gitdir / "refs" / "heads" / "main").unlink()   # then force the packed path
        self.other = "2" * 40

    def packed(self, text: str) -> None:
        (self.gitdir / "packed-refs").write_text(text, encoding="utf-8", newline="\n")

    def test_a_single_valid_record_still_answers(self) -> None:
        self.packed(f"{self.head} refs/heads/main\n")
        self.assertEqual(self.read(), self.head)

    def test_headers_and_peeled_lines_are_still_tolerated(self) -> None:
        self.packed(f"# pack-refs with: peeled fully-peeled sorted \n"
                    f"{self.head} refs/heads/main\n^{self.other}\n"
                    f"{'3' * 40} refs/tags/v1\n^{'4' * 40}\n")
        self.assertEqual(self.read(), self.head)

    def test_duplicate_records_binding_the_same_oid_are_one_identity(self) -> None:
        self.packed(f"{self.head} refs/heads/main\n{self.head} refs/heads/main\n")
        self.assertEqual(self.read(), self.head)

    def test_duplicate_records_binding_different_oids_are_refused(self) -> None:
        for label, text in (
            ("head then other", f"{self.head} refs/heads/main\n{self.other} refs/heads/main\n"),
            ("other then head", f"{self.other} refs/heads/main\n{self.head} refs/heads/main\n"),
            ("three, two distinct", f"{self.head} refs/heads/main\n{self.head} refs/heads/main\n"
                                    f"{self.other} refs/heads/main\n"),
        ):
            with self.subTest(case=label):
                self.packed(text)
                error = self.refusal(self.read)
                self.assertIn("different object ids", str(error))

    def test_a_malformed_record_for_the_target_is_refused_in_either_order(self) -> None:
        for label, bad in (("not an id", "notanoid"), ("abbreviated", self.head[:12]),
                           ("uppercase", self.head.upper()), ("too long", self.head + "0")):
            for order, text in (
                ("bad first", f"{bad} refs/heads/main\n{self.head} refs/heads/main\n"),
                ("bad last", f"{self.head} refs/heads/main\n{bad} refs/heads/main\n"),
            ):
                with self.subTest(case=f"{label} / {order}"):
                    self.packed(text)
                    self.refusal(self.read)

    def test_an_unrelated_record_git_tolerates_is_still_not_validated(self) -> None:
        """The parser stays narrow about IDENTITY: an unrelated record's id is never hex-checked.

        Superseding this class's earlier claim that unrelated malformed lines are
        never validated AT ALL. That was measured wrong: Git refuses the whole
        file for a line it cannot parse, so a SHAPE it rejects now refuses here
        too (see :class:`PackedWholeFileTests`). What remains unvalidated is the
        id of a record that is not the one being asked about - Git resolves the
        target past forty non-hex characters, and so does this.
        """
        self.packed(f"{'z' * 40} refs/heads/elsewhere\n{self.head} refs/heads/main\n")
        self.assertEqual(self.read(), self.head)
        self.packed(f"{self.head.upper()} refs/heads/elsewhere\n{self.head} refs/heads/main\n")
        self.assertEqual(self.read(), self.head)
        # but a line whose SHAPE Git refuses now refuses here as well
        self.packed(f"garbage-without-a-space\n{self.head} refs/heads/main\n")
        self.refusal(self.read)

    def test_near_names_are_never_the_target(self) -> None:
        self.packed(f"{self.other} refs/heads/main2\n{self.other} refs/heads/mainx\n"
                    f"{self.other} refs/heads/mai\n{self.other} refs/heads/MAIN\n")
        self.refusal(self.read)
        self.packed(f"{self.other} refs/heads/main2\n{self.head} refs/heads/main\n"
                    f"{self.other} refs/heads/mainx\n")
        self.assertEqual(self.read(), self.head)

    def test_no_target_record_is_refused(self) -> None:
        self.packed(f"# only a header\n{self.other} refs/tags/v1\n")
        self.refusal(self.read)

    def test_the_parser_no_longer_returns_on_the_first_match(self) -> None:
        import inspect

        source = inspect.getsource(fsafe._packed_ref)
        self.assertIn("bindings", source)
        self.assertIn("different object ids", source)


class RefnameGrammarTests(SubmoduleCase):
    """A ref spelling Git rejects must not become a gitlink identity.

    The first repair closed the colon because it reached a hidden stream. That
    reasoning was too narrow: the invariant is not "cannot reach a hidden
    object", it is "a ref Git does not recognise has no commit to report". An
    ordinary visible file with a Git-invalid name is just as wrong an answer.
    """

    def git_ok(self, *args: str) -> bool:
        return subprocess.run(
            ["git", "-C", str(self.super / "sub"), *args], capture_output=True, text=True,
            env={k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")},
        ).returncode == 0

    def refname(self, refname: str) -> None:
        (self.gitdir / "HEAD").write_text(f"ref: {refname}\n", encoding="utf-8", newline="\n")

    #: Every class Git rejects, with a representative that needs no filesystem fixture.
    INVALID = (
        ("component begins with '.'", "refs/heads/.hidden"),
        ("nested component begins with '.'", "refs/heads/sub/.hidden"),
        ("component ends with '.lock'", "refs/heads/name.lock"),
        ("nested component ends with '.lock'", "refs/heads/sub/name.lock"),
        ("holds '..'", "refs/heads/a..b"),
        ("'..' component", "refs/heads/../escape"),
        ("'.' component", "refs/heads/./x"),
        ("tilde", "refs/heads/bad~name"),
        ("caret", "refs/heads/bad^name"),
        ("colon", "refs/heads/bad:name"),
        ("question mark", "refs/heads/bad?name"),
        ("asterisk", "refs/heads/bad*name"),
        ("open bracket", "refs/heads/bad[name"),
        ("space", "refs/heads/bad name"),
        ("tab", "refs/heads/bad\tname"),
        ("control character", "refs/heads/bad\x01name"),
        ("DEL", "refs/heads/bad\x7fname"),
        ("'@{'", "refs/heads/@{bad"),
        ("'@{' inside", "refs/heads/a@{b"),
        ("backslash", "refs/heads/bad\\name"),
        ("ends with '.'", "refs/heads/trailing."),
        ("trailing slash", "refs/heads/trailing/"),
        ("double slash", "refs/heads//double"),
        ("leading slash", "/refs/heads/main"),
        ("empty", ""),
        ("not under refs/", "heads/main"),
        ("single component", "refs"),
        ("NUL", "refs/heads/bad\0name"),
    )

    #: Names Git ACCEPTS. Refusing any of these would refuse a submodule HEAD Git resolves.
    VALID = (
        "refs/heads/main", "refs/heads/feature/x", "refs/heads/a-b_c.d", "refs/heads/@",
        "refs/heads/a.b", "refs/heads/bad]name", "refs/heads/bad@bad", "refs/heads/-dash",
        "refs/heads/dash-", "refs/heads/{brace", "refs/heads/}brace", "refs/heads/per%cent",
        "refs/heads/semi;colon", "refs/heads/pipe|x", "refs/heads/amp&x", "refs/heads/dollar$x",
        "refs/heads/hash#x", "refs/heads/plus+x", "refs/heads/eq=x", "refs/heads/bang!x",
        "refs/heads/paren(x", "refs/heads/comma,x", "refs/heads/a./b", "refs/tags/v1",
    )

    # ---- the predicate on its own
    def test_every_invalid_class_is_refused_by_the_predicate(self) -> None:
        for label, refname in self.INVALID:
            with self.subTest(case=label):
                with self.assertRaises(ValidationError) as caught:
                    fsafe._require_refname(refname, "HEAD")
                self.assertEqual(caught.exception.code, fsafe.CODE)

    def test_every_name_git_accepts_passes_the_predicate(self) -> None:
        """The other half: the predicate must not invent a namespace narrower than Git's."""
        for refname in self.VALID:
            with self.subTest(refname=refname):
                self.assertEqual(fsafe._require_refname(refname, "HEAD"), refname.split("/"))

    def test_the_predicate_agrees_with_git_check_ref_format(self) -> None:
        """Measured, not assumed - except the one place HEAD is stricter than the command."""
        for label, refname in self.INVALID:
            if refname in ("", "heads/main", "refs") or "\0" in refname:
                continue  # empty / not-under-refs / NUL are not things to hand a command
            with self.subTest(invalid=label):
                self.assertFalse(self.git_ok("check-ref-format", refname),
                                 f"the Git oracle changed for {refname!r}")
        for refname in self.VALID:
            with self.subTest(valid=refname):
                self.assertTrue(self.git_ok("check-ref-format", refname),
                                f"the Git oracle changed for {refname!r}")

    def test_a_name_git_accepts_but_head_cannot_resolve_is_still_refused(self) -> None:
        """MEASURED: `check-ref-format` accepts 'heads/mainx', but HEAD naming it does not resolve."""
        self.assertTrue(self.git_ok("check-ref-format", "heads/mainx"))
        with self.assertRaises(ValidationError):
            fsafe._require_refname("heads/mainx", "HEAD")

    # ---- planted through a real submodule
    def test_a_planted_invalid_ref_is_refused_where_git_refuses(self) -> None:
        for leaf in ("bad~name", "bad^name", "bad[name", "name.lock", "a..b", "@{bad",
                     "bad name", ".hidden", "trailing."):
            with self.subTest(leaf=leaf):
                where = self.gitdir / "refs" / "heads" / leaf
                try:
                    where.parent.mkdir(parents=True, exist_ok=True)
                    where.write_text("7" * 40 + "\n", encoding="utf-8", newline="\n")
                    created = where.is_file()
                except OSError:
                    created = False
                if not created:
                    self.skipTest(f"this filesystem cannot hold a file named {leaf!r}")
                try:
                    # the oracle runs AFTER HEAD points at the planted ref, or it proves nothing
                    self.assertFalse(self.git_ok("check-ref-format", f"refs/heads/{leaf}"),
                                     f"git check-ref-format must reject refs/heads/{leaf!r}")
                    self.refname(f"refs/heads/{leaf}")
                    self.assertFalse(self.git_ok("rev-parse", "HEAD"),
                                     f"git rev-parse HEAD must refuse a HEAD naming refs/heads/{leaf!r}")
                    error = self.refusal(self.read)
                    self.assertNotIn("7" * 40, str(error), "the planted id never reaches the answer")
                finally:
                    where.unlink()
                    self.refname("refs/heads/main")

    def test_a_valid_symbolic_ref_still_resolves_after_the_tightening(self) -> None:
        head = self.oracle()
        self.refname("refs/heads/main")
        self.assertEqual(self.read(), head)
        # and an unusual but Git-valid name resolves too
        unusual = self.gitdir / "refs" / "heads" / "dash-"
        unusual.write_text(head + "\n", encoding="utf-8", newline="\n")
        self.refname("refs/heads/dash-")
        self.assertEqual(self.read(), head)


class PackedSeparatorTests(SubmoduleCase):
    """Every record syntax Git honours for the target takes part in the identity decision.

    A space-only parser lost a TAB-separated record entirely, so Git and this
    reader answered with different commits from the same bytes - the defect the
    uniqueness repair was supposed to close, surviving in another separator.
    """

    def setUp(self) -> None:
        super().setUp()
        self.head = self.oracle()
        (self.gitdir / "refs" / "heads" / "main").unlink()
        self.other = "2" * 40

    def packed(self, text: str) -> None:
        (self.gitdir / "packed-refs").write_text(text, encoding="utf-8", newline="\n")

    def git_head(self) -> str:
        found = subprocess.run(
            ["git", "-C", str(self.super / "sub"), "rev-parse", "HEAD"], capture_output=True, text=True,
            env={k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")},
        )
        return found.stdout.strip() if found.returncode == 0 else "REFUSE"

    def test_the_separator_set_is_the_one_git_accepts(self) -> None:
        self.assertEqual(fsafe.PACKED_SEPARATORS, " \t\v\f")
        for name, separator in (("space", " "), ("tab", "\t"), ("vertical tab", "\v"), ("form feed", "\f")):
            with self.subTest(separator=name):
                self.packed(f"{self.head}{separator}refs/heads/main\n")
                self.assertEqual(self.git_head(), self.head, "the Git oracle changed for this separator")
                self.assertEqual(self.read(), self.head)

    def test_a_tab_record_is_no_longer_invisible(self) -> None:
        """The decisive case: Git honoured it, the old parser did not see it at all."""
        self.packed(f"{self.head}\trefs/heads/main\n")
        self.assertEqual(self.read(), self.head)

    def test_a_tab_record_contradicting_a_space_record_fails_closed(self) -> None:
        for label, text in (
            ("space then tab", f"{self.head} refs/heads/main\n{self.other}\trefs/heads/main\n"),
            ("tab then space", f"{self.other}\trefs/heads/main\n{self.head} refs/heads/main\n"),
        ):
            with self.subTest(case=label):
                self.packed(text)
                self.assertNotEqual(self.git_head(), "REFUSE", "Git honours both records here")
                error = self.refusal(self.read)
                self.assertIn("different object ids", str(error))

    def test_a_tab_record_agreeing_with_a_space_record_is_one_identity(self) -> None:
        self.packed(f"{self.head} refs/heads/main\n{self.head}\trefs/heads/main\n")
        self.assertEqual(self.read(), self.head)

    def test_a_doubled_separator_is_refused_as_git_refuses_it(self) -> None:
        for separator in ("  ", " \t", "\t "):
            with self.subTest(separator=repr(separator)):
                self.packed(f"{self.head}{separator}refs/heads/main\n")
                self.assertEqual(self.git_head(), "REFUSE")
                self.refusal(self.read)


class PackedWholeFileTests(SubmoduleCase):
    """Git reads packed-refs as a whole: a line it cannot parse refuses every ref in it."""

    def setUp(self) -> None:
        super().setUp()
        self.head = self.oracle()
        (self.gitdir / "refs" / "heads" / "main").unlink()
        self.other = "2" * 40
        self.target = "refs/heads/main"
        self.elsewhere = "refs/heads/elsewhere"

    def packed(self, text: str) -> None:
        (self.gitdir / "packed-refs").write_text(text, encoding="utf-8", newline="\n")

    def git_head(self) -> str:
        found = subprocess.run(
            ["git", "-C", str(self.super / "sub"), "rev-parse", "HEAD"], capture_output=True, text=True,
            env={k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")},
        )
        return found.stdout.strip() if found.returncode == 0 else "REFUSE"

    def both(self, label: str, text: str) -> None:
        """Git refuses -> reader must refuse. Git answers -> reader answers the same, or fails closed."""
        self.packed(text)
        said = self.git_head()
        got = self.read_or_refuse()
        if said == "REFUSE":
            self.assertEqual(got, "REFUSE", f"{label}: Git refuses the file, so the reader must not answer")
        else:
            self.assertIn(got, (said, "REFUSE"), f"{label}: the reader must agree with Git or fail closed")

    def read_or_refuse(self) -> str:
        try:
            return self.read()
        except ValidationError:
            return "REFUSE"

    def test_a_packed_state_git_refuses_never_yields_a_target_id(self) -> None:
        for label, unrelated in (
            ("garbage, no separator", "garbage-without-a-space"),
            ("garbage with a space", "garbage line here"),
            ("abbreviated id", f"{self.head[:12]} {self.elsewhere}"),
            ("id with no ref", self.head),
            ("id and separator, no ref", f"{self.head} "),
            ("ref with no id", self.elsewhere),
            ("stray # comment", "# a comment"),
            ("empty line", ""),
        ):
            for order, text in (("before the target", f"{unrelated}\n{self.head} {self.target}\n"),
                                ("after the target", f"{self.head} {self.target}\n{unrelated}\n")):
                with self.subTest(case=f"{label} / {order}"):
                    self.packed(text)
                    self.assertEqual(self.git_head(), "REFUSE", f"the Git oracle changed for {label}")
                    self.refusal(self.read)

    def test_a_peeled_line_before_any_record_is_refused(self) -> None:
        self.packed(f"^{self.other}\n{self.head} {self.target}\n")
        self.assertEqual(self.git_head(), "REFUSE")
        self.refusal(self.read)

    def test_lawful_unrelated_records_are_still_accepted(self) -> None:
        """Measured: Git resolves the target past these, so refusing them would refuse a state Git answers."""
        for label, unrelated in (
            ("forty non-hex characters", f"{'z' * 40} {self.elsewhere}"),
            ("an upper-case full id", f"{self.head.upper()} {self.elsewhere}"),
            ("a tab-separated other ref", f"{self.other}\t{self.elsewhere}"),
            ("a Git-invalid ref name", f"{self.other} refs/heads/bad~name"),
            ("trailing junk after the ref", f"{self.other} {self.elsewhere} junk"),
        ):
            with self.subTest(case=label):
                self.packed(f"{unrelated}\n{self.head} {self.target}\n")
                self.assertEqual(self.git_head(), self.head, f"the Git oracle changed for {label}")
                self.assertEqual(self.read(), self.head)

    def test_the_header_is_accepted_only_as_the_first_line(self) -> None:
        """MEASURED, and the reason `rev-parse HEAD` alone is not a whole-file oracle.

        A header anywhere but the top is a malformed file. In a submodule git
        directory `git rev-parse HEAD` refuses it outright; in a plain repository
        `rev-parse` resolves the target early and `git show-ref` refuses. This
        reader takes the answer both commands agree on and refuses.
        """
        self.packed(f"# pack-refs with: peeled \n{self.head} {self.target}\n")
        self.assertEqual(self.git_head(), self.head)
        self.assertEqual(self.read(), self.head)

        self.packed(f"{self.head} {self.target}\n# pack-refs with: peeled \n")
        self.assertEqual(self.git_head(), "REFUSE", "in a submodule gitdir Git refuses a trailing header")
        self.refusal(self.read)

    def test_an_id_token_of_the_wrong_length_is_refused_and_disclosed(self) -> None:
        """DISCLOSED: Git resolves past a 39- or 41-character unrelated token; this reader does not.

        Those are object ids in no spelling, the reason Git tolerates them is not
        documented behaviour to reproduce, and guessing at it would be worse than
        failing closed. Recorded here so the difference is deliberate, not lost.
        """
        for length in (39, 41):
            with self.subTest(length=length):
                token = (self.head * 2)[:length]
                self.packed(f"{token} {self.elsewhere}\n{self.head} {self.target}\n")
                self.assertEqual(self.git_head(), self.head, "Git still resolves the target")
                self.refusal(self.read)

    def test_the_header_prefix_includes_the_space_after_the_colon(self) -> None:
        """MEASURED: the trailing space is part of the spelling, and the trait list is not validated.

        `# pack-refs with: ` with no traits at all resolves, and so does an
        unknown trait - Git allows traits it does not know. But
        `# pack-refs with:`, `# pack-refs with:peeled` and `# pack-refs with:X`
        are each refused before the ref resolves, so a prefix without the space
        accepted three states Git rejects.
        """
        self.assertEqual(fsafe.PACKED_HEADER, "# pack-refs with: ")
        for label, header, accepted in (
            ("canonical, several traits", "# pack-refs with: peeled fully-peeled sorted ", True),
            ("required space, no traits", "# pack-refs with: ", True),
            ("unknown trait", "# pack-refs with: unknown", True),
            ("doubled space", "# pack-refs with:  peeled ", True),
            ("no space after the colon", "# pack-refs with:", False),
            ("trait with no space", "# pack-refs with:peeled", False),
            ("junk with no space", "# pack-refs with:X", False),
            ("wrong case", "# pack-refs WITH: peeled ", False),
        ):
            with self.subTest(case=label):
                self.packed(f"{header}\n{self.head} {self.target}\n")
                said = self.git_head()
                self.assertEqual(said, self.head if accepted else "REFUSE",
                                 f"the Git oracle changed for {header!r}")
                if accepted:
                    self.assertEqual(self.read(), self.head)
                else:
                    self.refusal(self.read)

    def test_an_unterminated_final_record_is_refused(self) -> None:
        """MEASURED: Git refuses a packed-refs file whose last line carries no LF."""
        for label, text in (
            ("bare record", f"{self.head} {self.target}"),
            ("after a header", f"# pack-refs with: peeled \n{self.head} {self.target}"),
            ("after another record", f"{self.other} {self.elsewhere}\n{self.head} {self.target}"),
            ("after a peeled line", f"{self.head} {self.target}\n^{self.other}"),
        ):
            with self.subTest(case=label):
                self.packed(text)
                self.assertEqual(self.git_head(), "REFUSE", f"the Git oracle changed for {label}")
                error = self.refusal(self.read)
                self.assertIn("newline", str(error))
        # and the terminated form still works
        self.packed(f"{self.head} {self.target}\n")
        self.assertEqual(self.read(), self.head)

    def test_a_carriage_return_is_not_normalized_away(self) -> None:
        """MEASURED: Git reads `<id> refs/heads/main\\r` as a binding for a DIFFERENT ref.

        So it resolves `refs/heads/main` from the LF record beside it, and refuses
        when the CRLF record is the only one. Stripping the `\\r` invented a
        binding Git does not have.
        """
        for label, text, expected in (
            ("target CRLF alone", f"{self.head} {self.target}\r\n", "REFUSE"),
            ("header LF + target CRLF", f"# pack-refs with: peeled \n{self.head} {self.target}\r\n", "REFUSE"),
            ("header CRLF + target CRLF", f"# pack-refs with: peeled \r\n{self.head} {self.target}\r\n", "REFUSE"),
            ("header CRLF + target LF", f"# pack-refs with: peeled \r\n{self.head} {self.target}\n", "HEAD"),
            ("LF record then CRLF record, same ref",
             f"{self.head} {self.target}\n{self.other} {self.target}\r\n", "HEAD"),
            ("CRLF record then LF record, same ref",
             f"{self.other} {self.target}\r\n{self.head} {self.target}\n", "HEAD"),
        ):
            with self.subTest(case=label):
                self.packed(text)
                want = self.head if expected == "HEAD" else "REFUSE"
                self.assertEqual(self.git_head(), want, f"the Git oracle changed for {label}")
                if want == "REFUSE":
                    self.refusal(self.read)
                else:
                    self.assertEqual(self.read(), self.head,
                                     "a CRLF record names another ref; it must not shadow the LF one")

    def test_a_carriage_return_separator_is_refused_and_disclosed(self) -> None:
        """DISCLOSED: Git accepts CR as the one record separator; this reader does not.

        Adding it to the separator set is the wrong trade: `\\r` would then have to
        be both a separator and a legal tail of a ref name, and a CRLF record
        beside a valid one would become invisible again - the exact defect the
        separator repair closed. Refusing is fail-closed and recorded here.
        """
        self.assertNotIn("\r", fsafe.PACKED_SEPARATORS)
        self.packed(f"{self.head}\r{self.target}\n")
        self.assertEqual(self.git_head(), self.head, "Git accepts a CR separator")
        self.refusal(self.read)

    def test_a_peeled_line_follows_the_f3_oracle_not_whole_repository_validity(self) -> None:
        """§8A: for every peeled shape, `git rev-parse HEAD` answers and so does this reader.

        `git show-ref` refuses several of them, and that difference is recorded
        rather than adopted: the frozen standard is the commit the submodule's
        HEAD names, not whole-repository validity.
        """
        for label, peeled in (
            ("valid id", f"^{self.other}"),
            ("garbage", "^garbage"),
            ("abbreviated", f"^{self.head[:12]}"),
            ("over-long", f"^{(self.head * 2)[:41]}"),
            ("valid id plus junk", f"^{self.other}junk"),
        ):
            with self.subTest(case=label):
                self.packed(f"{self.head} {self.target}\n{peeled}\n")
                self.assertEqual(self.git_head(), self.head, f"the Git oracle changed for {label}")
                self.assertEqual(self.read(), self.head)

    def test_the_whole_file_grammar_is_a_named_boundary(self) -> None:
        import inspect

        self.assertIn("_packed_records", inspect.getsource(fsafe._packed_ref))
        # the header's exact spelling is pinned by test_the_header_prefix_includes_the_space_after_the_colon
        self.assertTrue(fsafe.PACKED_HEADER.startswith("# pack-refs with:"))


class SubmoduleSha256Tests(FsafeCase):
    """G-5 accepts a 64-hex object id, parsed the same way as a 40-hex one."""

    def test_a_sixty_four_hex_head_is_accepted(self) -> None:
        where = self.new_dir("sha256")
        gitdir = where / "sub" / ".git"
        gitdir.mkdir(parents=True)
        oid = "9" * 64
        (gitdir / "HEAD").write_text(f"{oid}\n", encoding="utf-8", newline="\n")
        chain = fsafe.walk(where, ["sub"])
        with chain:
            self.assertEqual(fsafe.submodule_head(chain), oid)

    def test_a_sixty_four_hex_loose_ref_is_accepted(self) -> None:
        where = self.new_dir("sha256-ref")
        gitdir = where / "sub" / ".git"
        (gitdir / "refs" / "heads").mkdir(parents=True)
        oid = "ab" * 32
        (gitdir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8", newline="\n")
        (gitdir / "refs" / "heads" / "main").write_text(f"{oid}\n", encoding="utf-8", newline="\n")
        chain = fsafe.walk(where, ["sub"])
        with chain:
            self.assertEqual(fsafe.submodule_head(chain), oid)

    def test_a_sixty_three_or_sixty_five_hex_head_is_refused(self) -> None:
        where = self.new_dir("sha256-bad")
        gitdir = where / "sub" / ".git"
        gitdir.mkdir(parents=True)
        for oid in ("9" * 63, "9" * 65, "9" * 41, "9" * 39):
            with self.subTest(length=len(oid)):
                (gitdir / "HEAD").write_text(f"{oid}\n", encoding="utf-8", newline="\n")
                chain = fsafe.walk(where, ["sub"])
                with chain:
                    self.refusal(lambda chain=chain: fsafe.submodule_head(chain))


class HeldHandleTests(SubmoduleCase):
    """§30: once the chain is held, a replacement at the pathname must not redirect the reader."""

    def test_the_reader_answers_through_the_held_chain_not_a_replacement(self) -> None:
        head = self.oracle()
        decoy = self.new_dir("decoy")
        git(decoy, "init", "-b", "main")
        git(decoy, "config", "user.name", "Real Person")
        git(decoy, "config", "user.email", "real@proj")
        (decoy / "z.txt").write_text("z\n", encoding="utf-8", newline="\n")
        git(decoy, "add", "-A")
        git(decoy, "commit", "-m", "decoy", "--no-verify")
        decoy_head = git(decoy, "rev-parse", "HEAD")
        self.assertNotEqual(decoy_head, head)

        chain = fsafe.walk(self.super, ["sub"])
        self.assertIsNotNone(chain)
        with chain:
            working = self.super / "sub"
            try:
                os.replace(working, self.super / "sub-moved")
                os.replace(decoy, working)
                swapped = True
            except OSError as exc:
                swapped = False
                reason = exc
            if not swapped:
                # Windows: every held directory is opened without FILE_SHARE_DELETE, so the
                # pathname cannot be renamed or replaced while the chain lives. The redirection
                # this test probes for is prevented rather than survived, which is the stronger
                # outcome - recorded as measured, not assumed.
                self.assertTrue(WINDOWS, f"a POSIX rename should have succeeded: {reason}")
                self.assertEqual(fsafe.submodule_head(chain), head)
                return
            self.assertEqual(fsafe.submodule_head(chain), head,
                             "the reader must answer through the held chain, not the decoy at that name")


# --------------------------------------------------------------------------- what must NOT change


class PreservedSemanticsTests(FsafeCase):
    """§33: identifying an indirection must not make any existing reader permissive."""

    def setUp(self) -> None:
        super().setUp()
        self.where = self.new_dir("preserved")
        (self.where / "plain.txt").write_bytes(b"plain\n")
        (self.where / "adir").mkdir()
        self.held = self.root(self.where)

    def test_read_file_still_accepts_only_a_plain_file(self) -> None:
        self.assertEqual(self.held.read_file("plain.txt"), b"plain\n")
        self.assertIsNone(self.held.read_file("nothing-here"))
        self.refusal(lambda: self.held.read_file("adir"))

    def test_read_file_still_refuses_a_final_indirection(self) -> None:
        if not make_indirection("file", self.where / "flink", self.where / "plain.txt"):
            self.skipTest("file symlinks need a privilege this Windows account does not hold")
        self.assertTrue(self.held.final_object("flink").is_indirection, "identified here")
        self.refusal(lambda: self.held.read_file("flink"))  # and still refused there

    def test_child_still_accepts_only_a_plain_directory(self) -> None:
        with self.held.child("adir") as found:
            self.assertIsNotNone(found)
        self.assertIsNone(self.held.child("nothing-here"))
        self.refusal(lambda: self.held.child("plain.txt"))

    def test_immutable_create_support_is_unchanged(self) -> None:
        self.assertEqual(fsafe.immutable_create_supported(), WINDOWS)
        if WINDOWS:
            fsafe.require_immutable_create()
        else:
            with self.assertRaises(ValidationError) as caught:
                fsafe.require_immutable_create()
            self.assertEqual(caught.exception.code, fsafe.UNSUPPORTED_CODE)

    def test_the_refusal_code_surface_is_unchanged(self) -> None:
        self.assertEqual(fsafe.CODE, "review_containment")
        self.assertEqual(fsafe.UNSUPPORTED_CODE, "review_create_unsupported")


# --------------------------------------------------------------------------- the unit boundary


class UnitBoundaryTests(unittest.TestCase):
    """This unit landed readers; the one consumer they have is the ownership boundary built on them.

    The two pins that held the readers unconsumed and the ownership boundary unstarted were
    ordered-gate pins, and they failed by design when P3 F3 Batch A (IP-14 / IP-15 / IP-16)
    landed. They are retired into SEPARATION pins rather than deleted: the readers have exactly
    one consumer, the reserved-ownership and witness names live in exactly that module, and the
    persistence engine that comes after it (Batch B) has still not arrived through it.
    """

    def setUp(self) -> None:
        from workline.implementation import package_directory

        self.package = package_directory(Path(__file__).resolve().parents[1])
        self.fsafe = self.package / "review" / "fsafe.py"
        self.assertTrue(self.fsafe.is_file(), f"fsafe.py must be where this test reads it: {self.fsafe}")

    def sources(self) -> dict[str, str]:
        return {path.relative_to(self.package).as_posix(): path.read_text(encoding="utf-8")
                for path in self.package.rglob("*.py") if path != self.fsafe}

    def test_the_new_readers_have_exactly_the_ownership_boundary_as_their_consumer(self) -> None:
        for name, text in self.sources().items():
            for api in ("final_object", "submodule_head", "FinalObjectInfo"):
                if name == "review/ownership.py" and api != "FinalObjectInfo":
                    self.assertIn(api, text, f"the ownership boundary is built on {api}")
                    continue
                with self.subTest(module=name, api=api):
                    self.assertNotIn(api, text, f"{name} would make {api} live outside the ownership boundary")

    def test_reserved_ownership_and_the_bound_witness_live_in_their_own_module(self) -> None:
        for name, text in self.sources().items():
            for owned in ("review_reserved_namespace", "OwnershipWitness", "ownership_witness",
                          "declare_own_content_witness"):
                if name == "review/ownership.py":
                    continue
                with self.subTest(module=name, owned=owned):
                    self.assertNotIn(owned, text, f"{name} names {owned}, which the ownership boundary owns")
        self.assertIn("review_reserved_namespace", self.sources()["review/ownership.py"])
        self.assertIn("OwnershipWitness", self.sources()["review/ownership.py"])

    def test_the_persistence_engine_has_not_arrived_through_the_ownership_boundary(self) -> None:
        joined = "\n".join(self.sources().values()) + self.fsafe.read_text(encoding="utf-8")
        for absent in ("CommitTreePlan", "prepared_commit_id", "WORK_COMMIT_MODE"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, joined)

    def test_fsafe_still_decides_nothing_about_review_semantics(self) -> None:
        text = self.fsafe.read_text(encoding="utf-8")
        for leaked in ("review_candidate_unavailable", ".workline/review", "GateGeneration", "Receipt"):
            with self.subTest(leaked=leaked):
                self.assertNotIn(leaked, text)


if __name__ == "__main__":
    unittest.main()
