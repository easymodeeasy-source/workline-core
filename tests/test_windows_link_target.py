"""A final link's target, read the way Git records it - on Windows through the link's own handle.

P3 F3 cumulative repair B-1 (F2 §6.4, F3 §7.8.4 2d / IP-15 / IP-21). A FINAL symlink is
identified, never followed, and its artifact is the exact target bytes Git stores as the
blob of its mode-120000 entry; an ANCESTOR indirection stays a containment failure.

Three layers are held here, so the production backend is exercised even where this
account cannot create a symlink:

* Git's rule (:func:`fsafe.windows_link_target`), pure and platform-independent, over
  reparse buffers built from the documented REPARSE_DATA_BUFFER layout - including the one
  shape measured against the installed Git with a real link;
* the native read (``fsafe._reparse_point`` / ``read_link``) against REAL reparse points
  this account can make - junctions, a broken junction - and against the real system link
  ``C:\\Users\\All Users``, compared byte for byte with what Git itself stages for it;
* a real symlink made where the platform permits, compared with ``git add``.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import struct
import subprocess
import sys
import unittest
from unittest import mock

from helpers import WorklineTestCase
from workline.errors import ReconcileRequired, ValidationError
from workline.review import fsafe, work_verify

WINDOWS = sys.platform == "win32"
SYMLINK = fsafe.IO_REPARSE_TAG_SYMLINK
MOUNT_POINT = fsafe.IO_REPARSE_TAG_MOUNT_POINT
BACKSLASH = chr(92)


def wide(text: str) -> bytes:
    """UTF-16-LE exactly as NTFS holds a name, lone surrogates included."""
    return text.encode("utf-16-le", "surrogatepass")


def reparse(tag: int, substitute: bytes, printed: bytes | None = None, *, flags: int = 1,
            print_first: bool = False) -> bytes:
    """A symbolic-link REPARSE_DATA_BUFFER: header, the four name fields, Flags, then PathBuffer."""
    printed = substitute if printed is None else printed
    if print_first:
        names, substitute_at, print_at = printed + substitute, len(printed), 0
    else:
        names, substitute_at, print_at = substitute + printed, 0, len(substitute)
    data = struct.pack("<HHHHI", substitute_at, len(substitute), print_at, len(printed), flags) + names
    return struct.pack("<IHH", tag, len(data), 0) + data


def link(target: str, printed: str | None = None, **options) -> bytes:
    return reparse(SYMLINK, wide(target), None if printed is None else wide(printed), **options)


def fields(substitute_at: int, substitute_length: int, print_at: int, print_length: int, names: bytes) -> bytes:
    """A symbolic-link buffer whose header length is right and whose name fields are exactly as given."""
    data = struct.pack("<HHHHI", substitute_at, substitute_length, print_at, print_length, 0) + names
    return struct.pack("<IHH", SYMLINK, len(data), 0) + data


def clean_git(*args: str, input: bytes | None = None) -> subprocess.CompletedProcess:
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    return subprocess.run(["git", *args], capture_output=True, env=environment, input=input)


def staged_link(repository: Path, work_tree: Path, name: str) -> tuple[str, bytes]:
    """``(mode, blob)`` Git itself stages for ``work_tree/name`` - the oracle, never the reader under test."""
    common = ["-C", str(work_tree), f"--git-dir={repository / '.git'}", f"--work-tree={work_tree}",
              "-c", "safe.directory=*"]
    staged = clean_git(*common, "update-index", "--add", "--", name)
    if staged.returncode != 0:
        raise AssertionError(f"git could not stage {name}: {staged.stderr.decode('utf-8', 'replace')}")
    listed = clean_git(*common, "ls-files", "-s", "--", name).stdout.decode("utf-8").split()
    blob = clean_git(f"--git-dir={repository / '.git'}", "cat-file", "blob", listed[1]).stdout
    return listed[0], blob


class ReaderCase(WorklineTestCase):
    def refusal(self, call) -> ValidationError:
        with self.assertRaises(ValidationError) as caught:
            call()
        self.assertEqual(caught.exception.code, fsafe.CODE)
        return caught.exception


# --------------------------------------------------------------------------- Git's rule, pure


class GitRuleTests(ReaderCase):
    """``windows_link_target``: Git for Windows' read_reparse_point + normalize_ntpath + xwcstoutf."""

    def target(self, raw: bytes) -> bytes:
        return fsafe.windows_link_target(raw, "link")

    def test_the_shape_measured_against_the_installed_git(self) -> None:
        """C:\\Users\\All Users: substitute \\??\\C:\\ProgramData -> Git's blob is the 14 bytes C:/ProgramData."""
        self.assertEqual(self.target(link("\\??\\C:\\ProgramData", "C:\\ProgramData", flags=0)), b"C:/ProgramData")

    def test_a_relative_target_keeps_its_components_with_slashes(self) -> None:
        for raw, expected in (("..\\lib\\a.so", b"../lib/a.so"), ("a", b"a"), ("a/b", b"a/b"), (".\\x", b"./x")):
            with self.subTest(raw=raw):
                self.assertEqual(self.target(link(raw)), expected)

    def test_every_prefix_git_strips_and_every_one_it_leaves(self) -> None:
        cases = {
            "\\??\\C:\\x": b"C:/x",
            "\\\\?\\C:\\x": b"C:/x",
            "\\DosDevices\\C:\\x": b"C:/x",
            "\\dosdevices\\C:\\x": b"C:/x",
            "\\DOSDEVICES\\C:\\x": b"C:/x",
            "\\??\\UNC\\srv\\share\\x": b"//srv/share/x",
            "\\??\\unc\\srv\\x": b"//srv/x",
            "\\\\?\\UNC\\srv\\x": b"//srv/x",
            "\\DosDevices\\UNC\\srv\\x": b"//srv/x",
            "\\x\\y": b"/x/y",
            "\\??x": b"/??x",
            "\\Device\\HarddiskVolume3\\x": b"/Device/HarddiskVolume3/x",
            "UNC\\srv": b"UNC/srv",
            "\\UNC\\srv": b"/UNC/srv",
            "\\??\\UN": b"UN",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(self.target(link(raw)), expected)

    def test_the_substitute_name_is_read_and_the_print_name_is_not(self) -> None:
        self.assertEqual(self.target(link("\\??\\C:\\real", "C:\\decoy")), b"C:/real")
        self.assertEqual(self.target(link("\\??\\C:\\real", "C:\\decoy", print_first=True)), b"C:/real")

    def test_the_flags_never_change_the_bytes(self) -> None:
        for flags in (0, 1, 0xFFFFFFFF):
            with self.subTest(flags=flags):
                self.assertEqual(self.target(link("..\\x", flags=flags)), b"../x")

    def test_a_non_ascii_target_is_utf8_exactly(self) -> None:
        for raw in ("\u30c7\u30fc\u30bf\\\u30d5\u30a1\u30a4\u30eb.txt", "\U0001d11e\\x", "caf\u00e9"):
            with self.subTest(raw=raw):
                self.assertEqual(self.target(link(raw)), raw.replace(BACKSLASH, "/").encode("utf-8"))

    def test_a_broken_link_is_read_like_any_other(self) -> None:
        """The rule never looks at the target: a link to nothing is still exactly its bytes (F2 §6.4)."""
        self.assertEqual(self.target(link("..\\does\\not\\exist")), b"../does/not/exist")

    def test_every_other_reparse_tag_is_refused(self) -> None:
        tags = {
            "junction": MOUNT_POINT, "WSL symlink": 0xA000001D, "app execution alias": 0x8000001B,
            "deduplicated file": 0x80000013, "cloud placeholder": 0x9000001A, "third-party tag": 0x00000001,
        }
        for label, tag in tags.items():
            with self.subTest(tag=label):
                refused = self.refusal(lambda tag=tag: self.target(reparse(tag, wide("..\\x"))))
                self.assertIn(f"0x{tag:08X}", refused.message)
        self.assertIn("junction", self.refusal(lambda: self.target(reparse(MOUNT_POINT, wide("x")))).message)

    def test_a_malformed_buffer_is_refused(self) -> None:
        good = link("..\\x")
        names = wide("ab")
        self.assertEqual(self.target(fields(0, 4, 0, 4, names)), b"ab", "the builder itself is well formed")
        cases = {
            "empty": b"",
            "no length": struct.pack("<I", SYMLINK),
            "trailing byte": good + b"\0",
            "missing byte": good[:-1],
            "no name fields": struct.pack("<IHH", SYMLINK, 4, 0) + b"\0" * 4,
            "odd substitute offset": fields(1, 2, 0, 4, names),
            "odd substitute length": fields(0, 3, 0, 4, names),
            "substitute outside": fields(2, 4, 0, 4, names),
            "odd print offset": fields(0, 4, 1, 2, names),
            "print name outside": fields(0, 4, 2, 4, names),
        }
        for label, raw in cases.items():
            with self.subTest(case=label):
                self.refusal(lambda raw=raw: self.target(raw))

    def test_a_target_git_would_rewrite_or_cut_short_is_refused(self) -> None:
        cases = {
            "lone high surrogate": link("a\ud800b"),
            "lone low surrogate": link("a\udc00b"),
            "empty": link(""),
            "a NUL inside": link("a\0b"),
            "a prefix and nothing else": link("\\??\\"),
        }
        for label, raw in cases.items():
            with self.subTest(case=label):
                self.refusal(lambda raw=raw: self.target(raw))

    def test_a_locale_dependent_prefix_comparison_is_refused(self) -> None:
        """wcsnicmp over a non-ASCII character depends on the C runtime's locale: not decided here."""
        self.refusal(lambda: self.target(link("\\DosDev\u0130ces\\x")))
        self.refusal(lambda: self.target(link("\\??\\UN\u0106\\srv")))
        # a comparison decided before it reaches a non-ASCII character is not refused
        self.assertEqual(self.target(link("\\??\\C:\\\u30c7\u30fc\u30bf")), "C:/\u30c7\u30fc\u30bf".encode("utf-8"))

    def test_the_container_mapping_git_reads_as_a_directory_is_refused(self) -> None:
        self.refusal(lambda: self.target(link("\\ContainerMappedDirectories\\0A1B")))

    def test_the_limit_is_what_git_can_read_after_normalization(self) -> None:
        self.assertEqual(len(self.target(link("a" * 259))), 259)
        self.refusal(lambda: self.target(link("a" * 260)))
        self.assertEqual(len(self.target(link("\u3042" * 86))), 258)
        self.refusal(lambda: self.target(link("\u3042" * 87)))
        # the substitute name is longer than the limit; what Git reads, after the prefix goes, is not
        self.assertEqual(len(self.target(link("\\??\\C:\\" + "a" * 256))), 259)

    def test_the_named_constants_are_the_measured_ones(self) -> None:
        self.assertEqual((fsafe.IO_REPARSE_TAG_SYMLINK, fsafe.IO_REPARSE_TAG_MOUNT_POINT), (0xA000000C, 0xA0000003))
        self.assertEqual(fsafe.GIT_LINK_TARGET_LIMIT, 259)
        self.assertEqual(fsafe.CONTAINER_MAPPED_PREFIX, "/ContainerMappedDirectories/")


# --------------------------------------------------------------------------- the native read, on real reparse points


@unittest.skipUnless(WINDOWS, "the handle-bound reparse read is the Windows backend")
class NativeReaderTests(ReaderCase):
    """No privilege is needed for any of this: a junction is a real reparse point this account can make."""

    def setUp(self) -> None:
        super().setUp()
        import _winapi

        self.where = self.new_dir("links")
        (self.where / "real").mkdir()
        (self.where / "real" / "inside.txt").write_bytes(b"never read\n")
        (self.where / "plain.txt").write_bytes(b"plain\n")
        _winapi.CreateJunction(str(self.where / "real"), str(self.where / "jn"))
        self.held = fsafe.SafeDirectory.open_root(self.where)
        self.addCleanup(self.held.close)

    def read_raw(self, name: str) -> tuple[tuple, bytes]:
        found = fsafe._reparse_point(self.held._backend.handle, name, name)
        self.assertIsNotNone(found)
        return found

    def test_the_identity_and_the_data_come_from_the_reparse_point_itself(self) -> None:
        identity, raw = self.read_raw("jn")
        self.assertEqual(identity, self.held.final_object("jn").identity)
        self.assertNotEqual(identity, self.held.final_object("real").identity, "never the target's identity")
        tag, length = struct.unpack_from("<IH", raw, 0)
        self.assertEqual(tag, MOUNT_POINT)
        self.assertEqual(len(raw), 8 + length, "exactly the header plus the reparse data length")
        offset, size = struct.unpack_from("<HH", raw, 8)
        substitute = raw[16 + offset:16 + offset + size].decode("utf-16-le")
        self.assertEqual(substitute, "\\??\\" + str(self.where / "real"))

    def test_a_broken_reparse_point_is_read_without_its_target(self) -> None:
        import _winapi

        (self.where / "gone").mkdir()
        _winapi.CreateJunction(str(self.where / "gone"), str(self.where / "broken"))
        (self.where / "gone").rmdir()
        identity, raw = self.read_raw("broken")
        self.assertEqual(identity, self.held.final_object("broken").identity)
        self.assertEqual(struct.unpack_from("<I", raw, 0)[0], MOUNT_POINT)

    def test_a_junction_is_not_a_link_and_is_refused(self) -> None:
        refused = self.refusal(lambda: self.held.read_link("jn"))
        self.assertIn("0xA0000003", refused.message)
        self.assertIn("junction", refused.message)

    def test_a_name_that_is_not_a_reparse_point_is_refused(self) -> None:
        for name in ("plain.txt", "real"):
            with self.subTest(name=name):
                self.assertIn("not a reparse point", self.refusal(lambda name=name: self.held.read_link(name)).message)

    def test_a_missing_name_is_absent(self) -> None:
        self.assertIsNone(self.held.read_link("nothing-here"))

    def test_the_read_takes_one_component_and_never_a_path(self) -> None:
        for name in ("", ".", "..", "a/b", "a\\b", "a\0b", "jn/inside.txt"):
            with self.subTest(name=name):
                self.refusal(lambda name=name: self.held.read_link(name))

    def test_repeated_reads_leak_no_handle(self) -> None:
        for _ in range(300):
            self.assertIsNone(self.held.read_link("nothing-here"))
            self.refusal(lambda: self.held.read_link("plain.txt"))
            self.refusal(lambda: self.held.read_link("jn"))
        os.rmdir(self.where / "jn")  # nothing of ours still holds it
        self.assertIsNone(self.held.final_object("jn"))

    def test_the_system_link_is_read_exactly_as_git_stages_it(self) -> None:
        """A REAL symlink this account did not have to create, measured against the installed Git."""
        users = Path("C:/Users")
        try:
            is_link = os.lstat(users / "All Users").st_reparse_tag == SYMLINK
        except OSError:
            is_link = False
        if not is_link:
            self.skipTest("this Windows installation has no C:\\Users\\All Users symbolic link")
        repository = self.new_dir("oracle")
        self.assertEqual(clean_git("init", "-q", str(repository)).returncode, 0)
        mode, blob = staged_link(repository, users, "All Users")
        with read_only_directory("C:/Users") as parent, read_only_directory("C:/") as drive:
            found = parent.read_link("All Users")
            self.assertEqual(mode, "120000")
            self.assertEqual(found.target, blob, "the bytes Git itself staged for this link")
            self.assertEqual(found.identity, parent.final_object("All Users").identity)
            self.assertNotEqual(found.identity, drive.final_object("ProgramData").identity)


class read_only_directory:
    """A directory opened for listing only, wrapped as a held directory - C:\\Users refuses the pinning open."""

    def __init__(self, path: str) -> None:
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                         wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        access = 0x0001 | 0x0020 | 0x0080 | 0x00100000  # LIST_DIRECTORY | TRAVERSE | READ_ATTRIBUTES | SYNCHRONIZE
        handle = kernel32.CreateFileW(path, access, 0x7, None, 3, 0x02000000 | 0x00200000, None)
        if handle in (None, 0, wintypes.HANDLE(-1).value):
            raise unittest.SkipTest(f"{path} cannot be opened for listing here")
        self.directory = fsafe.SafeDirectory(fsafe._WindowsDirectory(handle, path))

    def __enter__(self) -> fsafe.SafeDirectory:
        return self.directory

    def __exit__(self, *exc: object) -> None:
        self.directory.close()


# --------------------------------------------------------------------------- a real symlink, where it can be made


class RealLinkTests(ReaderCase):
    """Privilege-dependent: skipped where this account cannot create a symlink, and never the only coverage."""

    def setUp(self) -> None:
        super().setUp()
        self.repository = self.new_dir("repo")
        self.assertEqual(clean_git("init", "-q", str(self.repository)).returncode, 0)
        (self.repository / "dir").mkdir()
        (self.repository / "dir" / "file.txt").write_bytes(b"file\n")

    def make(self, name: str, target: str, *, directory: bool = False) -> None:
        try:
            os.symlink(target, self.repository / name, target_is_directory=directory)
        except OSError as exc:
            self.skipTest(f"this account cannot create a symlink: {exc}")

    def assert_as_git_stages(self, name: str) -> None:
        mode, blob = staged_link(self.repository, self.repository, name)
        with fsafe.SafeDirectory.open_root(self.repository) as held:
            found = held.read_link(name)
            self.assertEqual((mode, found.target), ("120000", blob))
            self.assertEqual(found.identity, held.final_object(name).identity)

    def test_a_relative_file_link(self) -> None:
        self.make("to-file", "dir/file.txt")
        self.assert_as_git_stages("to-file")

    def test_a_directory_link(self) -> None:
        self.make("to-dir", "dir", directory=True)
        self.assert_as_git_stages("to-dir")

    def test_a_broken_link(self) -> None:
        self.make("broken", "does/not/exist")
        self.assert_as_git_stages("broken")

    def test_an_absolute_link(self) -> None:
        self.make("absolute", str(self.repository / "dir" / "file.txt"))
        self.assert_as_git_stages("absolute")


# --------------------------------------------------------------------------- the isolated verification's read-back


@unittest.skipUnless(WINDOWS, "os.readlink renders a Windows link differently from Git; POSIX needs no bridge")
class VerificationReadBackTests(ReaderCase):
    """IP-6 V-2 compares a link with Git's bytes, so it reads the link as Git does - not with os.readlink."""

    def setUp(self) -> None:
        super().setUp()
        import _winapi

        self.workspace = self.new_dir("workspace")
        (self.workspace / "sub").mkdir()
        (self.workspace / "target").mkdir()
        _winapi.CreateJunction(str(self.workspace / "target"), str(self.workspace / "sub" / "ln"))

    def test_a_link_is_read_back_by_gits_rule_and_never_by_os_readlink(self) -> None:
        real = fsafe._reparse_point

        def as_link(parent, name, described):
            identity, _ = real(parent, name, described)
            return identity, link("..\\x\\y")

        with mock.patch.object(fsafe, "_reparse_point", side_effect=as_link), \
                mock.patch.object(os, "readlink", side_effect=AssertionError("os.readlink renders links its own way")):
            self.assertEqual(work_verify._link_target(self.workspace, "sub/ln"), b"../x/y")

    def test_a_reparse_point_git_does_not_read_as_a_link_fails_the_verification(self) -> None:
        with self.assertRaises(ReconcileRequired):
            work_verify._link_target(self.workspace, "sub/ln")

    def test_a_missing_link_fails_the_verification(self) -> None:
        with self.assertRaises(ReconcileRequired):
            work_verify._link_target(self.workspace, "sub/nothing")
        with self.assertRaises(ReconcileRequired):
            work_verify._link_target(self.workspace, "nowhere/ln")


if __name__ == "__main__":
    unittest.main()
