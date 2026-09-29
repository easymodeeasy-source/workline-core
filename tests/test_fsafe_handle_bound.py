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
    """This unit lands readers. It wires them into nothing."""

    def setUp(self) -> None:
        from workline.implementation import package_directory

        self.package = package_directory(Path(__file__).resolve().parents[1])
        self.fsafe = self.package / "review" / "fsafe.py"
        self.assertTrue(self.fsafe.is_file(), f"fsafe.py must be where this test reads it: {self.fsafe}")

    def sources(self) -> dict[str, str]:
        return {path.name: path.read_text(encoding="utf-8")
                for path in self.package.rglob("*.py") if path != self.fsafe}

    def test_no_other_production_module_calls_the_new_readers(self) -> None:
        for name, text in self.sources().items():
            for api in ("final_object", "submodule_head", "FinalObjectInfo"):
                with self.subTest(module=name, api=api):
                    self.assertNotIn(api, text, f"{name} would make {api} live")

    def test_reserved_ownership_and_the_bound_witness_are_not_started(self) -> None:
        joined = "\n".join(self.sources().values()) + self.fsafe.read_text(encoding="utf-8")
        for absent in ("review_reserved_namespace", "OwnershipWitness", "ownership_witness",
                       "declare_own_content_witness", "CommitTreePlan", "prepared_commit_id",
                       "WORK_COMMIT_MODE"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, joined)

    def test_fsafe_still_decides_nothing_about_review_semantics(self) -> None:
        text = self.fsafe.read_text(encoding="utf-8")
        for leaked in ("review_candidate_unavailable", ".workline/review", "GateGeneration", "Receipt"):
            with self.subTest(leaked=leaked):
                self.assertNotIn(leaked, text)


if __name__ == "__main__":
    unittest.main()
