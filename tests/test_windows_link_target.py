"""A final link's target, read the way Git records it - on Windows through the link's own handle.

P3 F3 cumulative repair B-1 (F2 §6.4, F3 §7.8.4 2d / IP-15 / IP-21). A FINAL symlink is
identified, never followed, and its artifact is the exact target bytes Git stores as the
blob of its mode-120000 entry; an ANCESTOR indirection stays a containment failure.

Several layers are held here, so the production backend is exercised even where this
account cannot create a symlink:

* Git's rule (:func:`fsafe.windows_link_target`) over reparse buffers built from the
  documented REPARSE_DATA_BUFFER layout. Wherever Git stages a 120000 blob, the reader returns
  Git's bytes - a name ended at its first NUL, an unpaired surrogate as U+FFFD, an empty name,
  a prefix compared the way git.exe's runtime compares it, a container-mapped target outside a
  container - and it refuses only what Git does not stage as a link or cannot read (cumulative
  repair B-1, then the link-semantics repair after the external re-review);
* the kernel's own admission rule (FSCTL_SET_REPARSE_POINT validates before the privilege
  check), which is what makes a malformed buffer CLASS 4 rather than a preference;
* Git's container test, ``is_inside_windows_container()``, reproduced exactly;
* the native read (``fsafe._reparse_point`` / ``read_link``) against REAL reparse points
  this account can make - junctions, a broken junction - and against the real system link
  ``C:\\Users\\All Users``, compared byte for byte with what Git itself stages for it;
* real links made where the platform permits - with ``os.symlink`` and, for the exact names
  above, with FSCTL_SET_REPARSE_POINT - compared with ``git update-index --add``.
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


def set_reparse_point(path: Path, buffer: bytes) -> int:
    """FSCTL_SET_REPARSE_POINT on ``path`` (a file of the test's own): 0, or the Windows error it was refused with.

    The kernel validates a symbolic-link buffer before it checks the privilege, so without the
    privilege a well-formed buffer is ERROR_PRIVILEGE_NOT_HELD (1314) and a malformed one
    ERROR_INVALID_REPARSE_DATA (4392); with it, a well-formed buffer turns the file into that link.
    """
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                     wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                         wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                         wintypes.LPVOID]
    handle = kernel32.CreateFileW(str(path), 0x40000000, 0x7, None, 3, 0x02000000 | 0x00200000, None)
    if handle in (None, 0, wintypes.HANDLE(-1).value):
        raise AssertionError(f"{path} cannot be opened for writing its reparse data: {ctypes.get_last_error()}")
    try:
        returned = wintypes.DWORD()
        data = ctypes.create_string_buffer(buffer, len(buffer))
        done = kernel32.DeviceIoControl(handle, 0x000900A4, data, len(buffer), None, 0, ctypes.byref(returned), None)
        return 0 if done else ctypes.get_last_error()
    finally:
        kernel32.CloseHandle(handle)


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
            # wcsnicmp in git.exe's runtime folds ASCII letters only, so these prefixes do not match
            "\\DosDev\u0130ces\\x": "/DosDev\u0130ces/x".encode("utf-8"),
            "\\??\\UN\u0106\\srv": "UN\u0106/srv".encode("utf-8"),
            "\\??\\\u212aUNC\\srv": "\u212aUNC/srv".encode("utf-8"),
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

    def test_reparse_data_the_kernel_admits_for_no_link_is_refused(self) -> None:
        """CLASS 4 - measured: FSCTL_SET_REPARSE_POINT rejects each of these before any privilege check."""
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
            "empty substitute name": fields(0, 0, 0, 4, names),
            "empty print name": fields(0, 4, 0, 0, names),
        }
        for label, raw in cases.items():
            with self.subTest(case=label):
                self.refusal(lambda raw=raw: self.target(raw))

    def test_a_name_git_ends_rewrites_or_empties_is_read_exactly_as_git_reads_it(self) -> None:
        """CLASS 1 - the kernel admits each of these links, and Git stages each as a 120000 blob of these bytes.

        read_reparse_point reads the name as a C wide string, so it ends at its first NUL;
        WideCharToMultiByte(CP_UTF8, 0) replaces an unpaired surrogate with U+FFFD; an empty name is
        an empty blob. These are Git's bytes, not shapes to refuse.
        """
        cases = {
            "a NUL inside": (link("ab\0cd", "ab"), b"ab"),
            "a NUL first": (link("\0cd", "x"), b""),
            "a NUL after a prefix": (link("\\??\\C:\\x\0y", "x"), b"C:/x"),
            "a prefix and nothing else": (link("\\??\\", "x"), b""),
            "a lone high surrogate": (link("a\ud800b"), b"a\xef\xbf\xbdb"),
            "a lone low surrogate": (link("a\udc00b"), b"a\xef\xbf\xbdb"),
            "a high surrogate at the end": (link("ab\ud83d"), b"ab\xef\xbf\xbd"),
            "two highs then a low": (link("\ud800\ud800\udc00"), b"\xef\xbf\xbd\xf0\x90\x80\x80"),
            "a low then a high": (link("\udc00\ud800"), b"\xef\xbf\xbd\xef\xbf\xbd"),
            "a surrogate after a prefix": (link("\\??\\C:\\\udc00"), b"C:/\xef\xbf\xbd"),
        }
        for label, (raw, expected) in cases.items():
            with self.subTest(case=label):
                self.assertEqual(self.target(raw), expected)

    def test_the_prefix_comparison_folds_ascii_only_as_gits_runtime_does(self) -> None:
        """CLASS 1 - git.exe runs msvcrt's _wcsnicmp in the "C" locale: ASCII letters fold, nothing else does."""
        cases = {
            ("\\DosDevices\\", "\\DosDevices\\"): True,
            ("\\DOSDEVICES\\", "\\DosDevices\\"): True,
            ("\\dosdevices\\", "\\DosDevices\\"): True,
            ("\\DosDevices", "\\DosDevices\\"): False,  # shorter: it ends at its NUL
            ("\\DosDev\u0130ces\\", "\\DosDevices\\"): False,  # U+0130 is not the ASCII letter i
            ("\\Do\u017fDevices\\", "\\DosDevices\\"): False,  # U+017F LONG S is not s
            ("UNC\\", "UNC\\"): True,
            ("unc\\", "UNC\\"): True,
            ("UN\u0106\\", "UNC\\"): False,
            ("\u212aUNC\\", "UNC\\"): False,
            ("UNC", "UNC\\"): False,
        }
        for (text, literal), matches in cases.items():
            with self.subTest(literal=literal, text=text):
                self.assertEqual(fsafe._device_prefix(text, literal), matches)
        self.assertEqual(self.target(link("\\??\\C:\\\u30c7\u30fc\u30bf")), "C:/\u30c7\u30fc\u30bf".encode("utf-8"))

    def test_a_container_mapped_target_is_a_link_outside_a_container(self) -> None:
        """CLASS 1 - Git's container rule applies only when is_inside_windows_container(); outside, it is a link."""
        with mock.patch.object(fsafe, "inside_windows_container", return_value=False):
            for raw, expected in (("\\ContainerMappedDirectories\\0A1B", b"/ContainerMappedDirectories/0A1B"),
                                  ("/ContainerMappedDirectories/0A1B", b"/ContainerMappedDirectories/0A1B"),
                                  ("\\ContainerMappedDirectories\\", b"/ContainerMappedDirectories/")):
                with self.subTest(raw=raw):
                    self.assertEqual(self.target(link(raw)), expected)

    def test_inside_a_container_git_takes_the_mapped_target_for_a_directory(self) -> None:
        """CLASS 2 - the same link inside a container is a directory to Git, decided by Git's own test."""
        with mock.patch.object(fsafe, "inside_windows_container", return_value=True):
            refused = self.refusal(lambda: self.target(link("\\ContainerMappedDirectories\\0A1B")))
            self.assertIn("inside a Windows container", refused.message)
            # starts_with is exact bytes: anything else stays a link even inside a container
            for raw, expected in (("\\containermappeddirectories\\0A1B", b"/containermappeddirectories/0A1B"),
                                  ("\\ContainerMappedDirectories", b"/ContainerMappedDirectories"),
                                  ("..\\ContainerMappedDirectories\\0A1B", b"../ContainerMappedDirectories/0A1B")):
                with self.subTest(raw=raw):
                    self.assertEqual(self.target(link(raw)), expected)

    def test_the_limit_is_what_git_can_read_after_normalization(self) -> None:
        """CLASS 3 - past 259 UTF-8 bytes Git's read fails, its lstat fails, and Git stages nothing."""
        self.assertEqual(len(self.target(link("a" * 259))), 259)
        self.refusal(lambda: self.target(link("a" * 260)))
        self.assertEqual(len(self.target(link("\u3042" * 86))), 258)
        self.refusal(lambda: self.target(link("\u3042" * 87)))
        # an unpaired surrogate counts as the three bytes of U+FFFD it becomes
        self.assertEqual(len(self.target(link("\ud800" * 86))), 258)
        self.refusal(lambda: self.target(link("\ud800" * 87)))
        # the substitute name is longer than the limit; what Git reads, after the prefix goes, is not
        self.assertEqual(len(self.target(link("\\??\\C:\\" + "a" * 256))), 259)

    def test_the_written_out_conversion_is_the_native_one(self) -> None:
        """Off Windows the conversion is written out; it must be WideCharToMultiByte's own answer, unit for unit."""
        if fsafe._native_wide_to_utf8 is None:
            self.skipTest("WideCharToMultiByte exists only on Windows; the written-out form is all there is here")
        samples = ["", "a/b", "a\ud800b", "\ud800\ud800\udc00", "\udc00\ud800", "ab\ud83d", "\U0001d11e",
                   "\ud800\udc00", "\udbff\udfff", "\ufffd\uffff", "x" * 259, "x" * 260, "\u3042" * 86, "\u3042" * 87]
        units = [0x0041, 0x00E9, 0x3042, 0xD800, 0xDBFF, 0xDC00, 0xDFFF, 0xFFFD, 0x002F]
        samples += ["".join(chr(units[(seed * 7 + step * 3) % len(units)]) for step in range(seed % 9 + 1))
                    for seed in range(400)]
        for sample in samples:
            with self.subTest(sample=sample.encode("utf-16-le", "surrogatepass").hex()):
                self.assertEqual(fsafe._wide_to_utf8_written_out(sample), fsafe._native_wide_to_utf8(sample))

    def test_the_named_constants_are_the_measured_ones(self) -> None:
        self.assertEqual((fsafe.IO_REPARSE_TAG_SYMLINK, fsafe.IO_REPARSE_TAG_MOUNT_POINT), (0xA000000C, 0xA0000003))
        self.assertEqual((fsafe.GIT_LINK_TARGET_BUFFER, fsafe.GIT_LINK_TARGET_LIMIT), (260, 259))
        self.assertEqual(fsafe.CONTAINER_MAPPED_PREFIX, "/ContainerMappedDirectories/")
        self.assertEqual(fsafe.CONTAINER_SERVICE_KEY, "SYSTEM\\CurrentControlSet\\Services\\cexecsvc")


class ContainerPredicateTests(ReaderCase):
    """Git's is_inside_windows_container(), exactly: RegOpenKeyExA(HKLM, ...cexecsvc, 0, KEY_READ) succeeds."""

    @unittest.skipUnless(WINDOWS, "the registry exists only on Windows")
    def test_the_predicate_is_gits_registry_test_and_nothing_else(self) -> None:
        import winreg

        class Opened:
            def Close(self) -> None:
                pass

        with mock.patch.object(winreg, "OpenKey", return_value=Opened()) as opened:
            self.assertTrue(fsafe.inside_windows_container())
        opened.assert_called_once_with(winreg.HKEY_LOCAL_MACHINE, "SYSTEM\\CurrentControlSet\\Services\\cexecsvc", 0,
                                       winreg.KEY_READ)
        for failure in (FileNotFoundError(2, "absent"), PermissionError(5, "denied"), OSError(1, "other")):
            with self.subTest(failure=type(failure).__name__), mock.patch.object(winreg, "OpenKey", side_effect=failure):
                self.assertFalse(fsafe.inside_windows_container(), "Git: any failure to open is not a container")
        with mock.patch.dict(os.environ, {"CONTAINER": "1", "DOCKER_HOST": "x"}), \
                mock.patch.object(winreg, "OpenKey", side_effect=FileNotFoundError(2, "absent")):
            self.assertFalse(fsafe.inside_windows_container(), "no environment variable is consulted")

    def test_off_windows_there_is_no_container(self) -> None:
        with mock.patch.object(fsafe.sys, "platform", "linux"):
            self.assertFalse(fsafe.inside_windows_container())

    @unittest.skipUnless(WINDOWS, "the registry exists only on Windows")
    def test_on_this_host_the_mapped_target_is_whatever_gits_own_test_makes_it(self) -> None:
        """The real predicate on this host, and the reader's answer that follows from it."""
        raw = link("\\ContainerMappedDirectories\\0A1B")
        if fsafe.inside_windows_container():
            self.refusal(lambda: fsafe.windows_link_target(raw, "link"))
        else:
            self.assertEqual(fsafe.windows_link_target(raw, "link"), b"/ContainerMappedDirectories/0A1B")


@unittest.skipUnless(WINDOWS, "FSCTL_SET_REPARSE_POINT is the Windows kernel's own admission check")
class KernelAdmissionTests(ReaderCase):
    """CLASS 4 is the kernel's: it validates symbolic-link reparse data BEFORE it checks the privilege.

    So without the privilege, a buffer the kernel would admit is refused with ERROR_PRIVILEGE_NOT_HELD
    and one it never admits with ERROR_INVALID_REPARSE_DATA - and the reader must refuse exactly the
    second kind and read every one of the first. Where this account does hold the privilege the set
    simply succeeds, on a scratch file, which is the same answer: admitted.
    """

    ADMITTED, REJECTED = (0, 1314), (4392,)

    def set_reparse(self, buffer: bytes) -> int:
        path = self.new_dir(f"probe-{os.urandom(4).hex()}") / "file"
        path.write_bytes(b"x")
        return set_reparse_point(path, buffer)

    def test_the_reader_refuses_exactly_what_the_kernel_never_admits(self) -> None:
        names = wide("ab")
        admitted = {
            "well formed": link("..\\x"),
            "a NUL inside": link("ab\0cd", "ab"),
            "a NUL first": link("\0cd", "x"),
            "a lone surrogate": link("a\ud800b"),
            "a prefix and nothing else": link("\\??\\", "x"),
            "a container-mapped target": link("\\ContainerMappedDirectories\\0A1B", "x"),
        }
        rejected = {
            "empty substitute name": fields(0, 0, 0, 4, names),
            "empty print name": fields(0, 4, 0, 0, names),
            "odd substitute length": fields(0, 3, 0, 4, names),
            "odd substitute offset": fields(1, 2, 0, 4, names),
            "substitute outside": fields(2, 4, 0, 4, names),
            "print name outside": fields(0, 4, 2, 4, names),
            "no name fields": struct.pack("<IHH", SYMLINK, 4, 0) + b"\0" * 4,
        }
        with mock.patch.object(fsafe, "inside_windows_container", return_value=False):
            for label, buffer in admitted.items():
                with self.subTest(admitted=label):
                    self.assertIn(self.set_reparse(buffer), self.ADMITTED)
                    fsafe.windows_link_target(buffer, label)  # read, not refused
            for label, buffer in rejected.items():
                with self.subTest(rejected=label):
                    self.assertIn(self.set_reparse(buffer), self.REJECTED)
                    self.refusal(lambda buffer=buffer, label=label: fsafe.windows_link_target(buffer, label))


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

    def craft(self, name: str, substitute: str, printed: str = "x") -> None:
        """A link whose substitute name is EXACTLY ``substitute``, set through FSCTL_SET_REPARSE_POINT."""
        if not WINDOWS:
            self.skipTest("a reparse buffer is a Windows object")
        path = self.repository / name
        path.write_bytes(b"x")
        status = set_reparse_point(path, link(substitute, printed))
        if status == 1314:
            self.skipTest("this account cannot create a symlink (ERROR_PRIVILEGE_NOT_HELD)")
        self.assertEqual(status, 0, "the kernel admits every one of these links")

    def test_links_whose_names_git_ends_rewrites_or_empties_are_read_as_git_stages_them(self) -> None:
        """The CLASS 1 shapes, as real links, against Git itself - wherever this account may make them."""
        shapes = {
            "cut": "ab\0cd",
            "lone": "a\ud800b",
            "bare": "\\??\\",
            "device": "\\DosDev\u0130ces\\x",
            "mapped": "\\ContainerMappedDirectories\\0A1B",
        }
        self.craft("probe", "..\\x")  # skips the whole test, once, where this account may not make links
        for name, substitute in shapes.items():
            with self.subTest(shape=name):
                if name == "mapped" and fsafe.inside_windows_container():
                    continue  # a directory to Git here: ContainerPredicateTests covers it
                self.craft(name, substitute)
                self.assert_as_git_stages(name)

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
