"""Handle-bound, no-follow access to the canonical Review namespace.

Every Review read and every Review create goes through a :class:`SafeDirectory`:
an opened handle to a directory that has been *proven* to be a plain in-Project
directory, walked to from the Project root one component at a time without
following anything.

Why a handle, and not a path checked beforehand
-----------------------------------------------

Checking a path and then using the path is two operations, and anything can
happen between them: a component can be replaced with a symlink or a junction,
and the second operation - the one that actually reads or writes - follows it.
Adding a second check narrows that window without closing it. What closes it is
binding the operation to the directory object that was proven:

```text
POSIX    openat(parent_fd, name, O_NOFOLLOW ...)   - relative to the proven fd (reads only)
Windows  NtCreateFile(RootDirectory = parent handle, FILE_OPEN_REPARSE_POINT ...)
         NtSetInformationFile(FileRenameInformation,
                              RootDirectory = parent handle,
                              ReplaceIfExists = FALSE)   - exclusive: name collision
```

A component swapped after it was proven is not followed, because nothing is
resolved by name through it again: each step opens the next component
*relative to the handle already held*. A target that appears in the meantime is
never overwritten, because the final step is exclusive - it fails on an
existing name instead of replacing it.

Where a create is possible at all
---------------------------------

Binding to a handle keeps the operation on the proven directory *object*. A
create also needs that object to still be inside the Project when the name is
placed, and only a pinned object is:

```text
Windows  every held directory, from the Project root down, is opened without
         FILE_SHARE_DELETE, so while a create runs none of them can be renamed,
         deleted or replaced by anyone                    -> create supported
POSIX    an fd pins nothing: the directory it holds can be renamed anywhere
         while it is held - out of the Project included - and a create through
         the fd lands wherever it went                   -> create refused
```

No primitive available here makes a POSIX placement fail once the directory is
no longer under the Project root, and creating anyway, then noticing and taking
the record back out, still puts it outside for as long as that takes. So the
immutable create is refused on POSIX before anything is opened or written
(:func:`require_immutable_create`); reading, listing and validating stay
available there exactly as on Windows.

No-follow
---------

Every component, including the last, is opened so that an indirection is seen
as itself rather than as what it points to: ``O_NOFOLLOW`` on POSIX,
``FILE_OPEN_REPARSE_POINT`` on Windows. A Windows junction is the case that
matters most there: to ``os.path`` it is a directory and not a symlink, so a
check that asked only those two questions would follow it. Here any reparse
point - junction, symlink, anything carrying a reparse tag - is refused.

This module decides nothing about Review semantics. It opens, lists, reads and -
where the platform can keep a create inside the Project - creates, and it
refuses anything it cannot positively show to be a plain file or directory
inside the Project.

Identifying a final object, which is not the same as reading one
----------------------------------------------------------------

:meth:`SafeDirectory.read_file` and :meth:`SafeDirectory.child` answer "may I
use this?", and an indirection is a no. :meth:`SafeDirectory.final_object`
answers a different question - "what IS this name?" - and an indirection is one
of the answers rather than a refusal:

```text
POSIX    os.stat(name, dir_fd=<held fd>, follow_symlinks=False)   - fstatat(AT_SYMLINK_NOFOLLOW)
Windows  NtCreateFile(RootDirectory=<held handle>, FILE_OPEN_REPARSE_POINT)
         + GetFileInformationByHandle
```

The distinction is load-bearing and cost a draft: an ``O_NOFOLLOW`` *open* of a
final symlink fails with ``ELOOP`` instead of identifying it, so a caller built
on one cannot tell "this is a link" from "this is unreadable", and every lawful
symlink result is lost. A no-follow *metadata* query has no such failure - the
link's own identity comes back, distinct from its target's. An indirection in an
ANCESTOR is still a containment failure, unchanged: that is what ``child``
refuses, and nothing here relaxes it.

Reading a submodule's HEAD without handing out a pathname
---------------------------------------------------------

A gitlink's identity is the commit its submodule's HEAD names. Asking
``git -C <path> rev-parse HEAD`` hands a PATHNAME to a second process, which
resolves it from the root again - and on POSIX a held fd pins nothing, so the
directory proven a moment ago can be somewhere else by then, and the second
process would read whatever now answers to that name.
:func:`submodule_head` never does that: every step is a read relative to a
handle already held, and `..` steps back to a directory the chain is still
holding rather than asking the filesystem for a parent.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
import os
from pathlib import Path
import re
import secrets
import stat
import sys

from ..errors import ValidationError

#: What refusing an indirection or an unprovable component is reported as.
CODE = "review_containment"

#: What refusing a create on a platform that cannot keep its parent inside the Project is reported as.
UNSUPPORTED_CODE = "review_create_unsupported"


@dataclass(frozen=True)
class Entry:
    """One directory entry, described without following it."""

    name: str
    is_dir: bool
    is_file: bool
    is_indirection: bool


@dataclass(frozen=True)
class FinalObjectInfo:
    """What a name denotes, taken without following it.

    ``identity`` is the filesystem's own answer to "which object is this" -
    ``(st_dev, st_ino)`` on POSIX, the volume serial plus the file index on
    Windows - and is meaningful only by comparison: two names that yield equal
    identities are two names for one object, and that is a stronger statement
    than any comparison of the names could be. It is opaque, it is runtime-only,
    and it is never recorded: an inode number is not an identity across a
    remount, let alone across a machine.

    An indirection is DESCRIBED here rather than refused. ``is_indirection`` is
    the link or reparse point itself; ``is_dir`` and ``is_file`` describe the
    object this name denotes, so all three are false for a symlink - a symlink
    is not the directory it points at, and this query never asks what it points
    at.
    """

    identity: tuple
    is_dir: bool
    is_file: bool
    is_indirection: bool


def _refuse(message: str) -> ValidationError:
    return ValidationError(message, code=CODE)


def _unsupported() -> ValidationError:
    return ValidationError(
        "canonical Review records cannot be created on this platform: a directory held open here can still be "
        "renamed while it is held (POSIX pins nothing), so a create bound to its proven parent could land wherever "
        "that directory was moved, outside the Project included. The immutable Review create is refused before "
        "anything is written; Review records are still read and validated here",
        code=UNSUPPORTED_CODE,
    )


def _require_component(name: str) -> None:
    if not name or name in (".", "..") or "/" in name or "\\" in name or "\0" in name:
        raise _refuse(f"not a single path component: {name!r}")


def _tmp_name(name: str) -> str:
    return f".{name}.{os.getpid()}.{secrets.token_hex(6)}.tmp"


# --------------------------------------------------------------------------- POSIX

class _PosixDirectory:
    """A directory held open by fd, reached without following anything. Reads only: an fd pins nothing."""

    _DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)

    #: A held fd keeps nothing where it was proven: the directory can be renamed anywhere while it is held.
    PINS_HELD_DIRECTORIES = False

    def __init__(self, fd: int, described: str) -> None:
        self.fd = fd
        self.described = described

    @classmethod
    def open_root(cls, path: Path) -> "_PosixDirectory":
        try:
            fd = os.open(path, cls._DIR_FLAGS)
        except OSError as exc:
            raise _refuse(f"the Project root cannot be opened as a plain directory ({path}): {exc}") from exc
        return cls(fd, str(path))

    def child(self, name: str, *, create: bool) -> "_PosixDirectory | None":
        _require_component(name)
        if create:
            raise _unsupported()  # a directory made here is only as contained as the unpinned fd it is made in
        described = f"{self.described}/{name}"
        try:
            fd = os.open(name, self._DIR_FLAGS, dir_fd=self.fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            if exc.errno in (errno.ELOOP, errno.ENOTDIR, getattr(errno, "EMLINK", -1)):
                raise _refuse(
                    f"{described} is a symlink or not a directory, and a Review path is walked only "
                    "through plain in-Project directories"
                ) from exc
            raise _refuse(f"{described} cannot be opened: {exc}") from exc
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            os.close(fd)
            raise _refuse(f"{described} is not a plain directory")
        return _PosixDirectory(fd, described)

    def entries(self) -> list[Entry]:
        found: list[Entry] = []
        with os.scandir(self.fd) as listing:
            for entry in listing:
                link = entry.is_symlink()
                found.append(
                    Entry(
                        entry.name,
                        is_dir=not link and entry.is_dir(follow_symlinks=False),
                        is_file=not link and entry.is_file(follow_symlinks=False),
                        is_indirection=link,
                    )
                )
        return sorted(found, key=lambda item: item.name)

    def final_object(self, name: str) -> "FinalObjectInfo | None":
        """What ``name`` itself denotes, by ``fstatat(..., AT_SYMLINK_NOFOLLOW)``.

        Deliberately NOT an ``O_NOFOLLOW`` open: that refuses a symlink with
        ``ELOOP`` rather than identifying it, which is the one thing this query
        exists to do.
        """
        _require_component(name)
        described = f"{self.described}/{name}"
        try:
            info = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        except FileNotFoundError:
            return None  # positive absence, the one answer that is not a refusal
        except OSError as exc:
            raise _refuse(f"{described} cannot be identified: {exc}") from exc
        mode = info.st_mode
        return FinalObjectInfo(
            (info.st_dev, info.st_ino),
            is_dir=stat.S_ISDIR(mode),
            is_file=stat.S_ISREG(mode),
            is_indirection=stat.S_ISLNK(mode),
        )

    def read_file(self, name: str) -> bytes | None:
        _require_component(name)
        described = f"{self.described}/{name}"
        try:
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), dir_fd=self.fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise _refuse(f"{described} is a symlink, and a Review record is read only from a plain file") from exc
            raise _refuse(f"{described} cannot be opened: {exc}") from exc
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise _refuse(f"{described} is not a plain file")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1 << 16)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(fd)

    def create_file_exclusive(self, name: str, data: bytes, tmp: "_PosixDirectory") -> bool:
        """Refused before anything is written, not even a temporary file: see :func:`immutable_create_supported`."""
        raise _unsupported()

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


# --------------------------------------------------------------------------- Windows

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _ntdll = ctypes.WinDLL("ntdll")
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _UnicodeString(ctypes.Structure):
        _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT), ("Buffer", wintypes.LPWSTR)]

    class _ObjectAttributes(ctypes.Structure):
        _fields_ = [
            ("Length", wintypes.ULONG),
            ("RootDirectory", wintypes.HANDLE),
            ("ObjectName", ctypes.POINTER(_UnicodeString)),
            ("Attributes", wintypes.ULONG),
            ("SecurityDescriptor", wintypes.LPVOID),
            ("SecurityQualityOfService", wintypes.LPVOID),
        ]

    class _IoStatusBlock(ctypes.Structure):
        _fields_ = [("Status", ctypes.c_void_p), ("Information", ctypes.c_size_t)]

    class _ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    _NtCreateFile = _ntdll.NtCreateFile
    _NtCreateFile.restype = ctypes.c_long
    _NtCreateFile.argtypes = [
        ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, ctypes.POINTER(_ObjectAttributes),
        ctypes.POINTER(_IoStatusBlock), ctypes.c_void_p, wintypes.ULONG, wintypes.ULONG,
        wintypes.ULONG, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG,
    ]
    _NtSetInformationFile = _ntdll.NtSetInformationFile
    _NtSetInformationFile.restype = ctypes.c_long
    _NtSetInformationFile.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_IoStatusBlock), ctypes.c_void_p, wintypes.ULONG, ctypes.c_int,
    ]
    _CreateFileW = _kernel32.CreateFileW
    _CreateFileW.restype = wintypes.HANDLE
    _CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    _CloseHandle = _kernel32.CloseHandle
    _CloseHandle.argtypes = [wintypes.HANDLE]
    _GetFileInformationByHandle = _kernel32.GetFileInformationByHandle
    _GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ByHandleFileInformation)]
    _GetFileInformationByHandleEx = _kernel32.GetFileInformationByHandleEx
    _GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _ReadFile = _kernel32.ReadFile
    _ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    _WriteFile = _kernel32.WriteFile
    _WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    _FlushFileBuffers = _kernel32.FlushFileBuffers
    _FlushFileBuffers.argtypes = [wintypes.HANDLE]

    _INVALID_HANDLE = wintypes.HANDLE(-1).value

    # access
    _FILE_LIST_DIRECTORY = 0x0001
    _FILE_ADD_FILE = 0x0002
    _FILE_ADD_SUBDIRECTORY = 0x0004
    _FILE_TRAVERSE = 0x0020
    _FILE_READ_ATTRIBUTES = 0x0080
    _DELETE = 0x00010000
    _SYNCHRONIZE = 0x00100000
    _GENERIC_READ = 0x80000000
    _GENERIC_WRITE = 0x40000000
    _DIR_ACCESS = _FILE_LIST_DIRECTORY | _FILE_ADD_FILE | _FILE_ADD_SUBDIRECTORY | _FILE_TRAVERSE | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE
    # share: never FILE_SHARE_DELETE on a held directory, so it cannot be renamed, deleted or replaced
    _FILE_SHARE_READ = 0x1
    _FILE_SHARE_WRITE = 0x2
    _FILE_SHARE_DELETE = 0x4
    _PIN_SHARE = _FILE_SHARE_READ | _FILE_SHARE_WRITE
    #: A metadata query holds its handle only long enough to ask, and pins nothing on purpose:
    #: identifying an object must not depend on nobody else holding it, or on being able to pin it.
    _QUERY_SHARE = _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE
    # disposition / options
    _FILE_OPEN = 1
    _FILE_CREATE = 2
    _FILE_OPEN_IF = 3
    _FILE_DIRECTORY_FILE = 0x00000001
    _FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
    _FILE_NON_DIRECTORY_FILE = 0x00000040
    _FILE_OPEN_REPARSE_POINT = 0x00200000
    _OBJ_CASE_INSENSITIVE = 0x00000040
    # CreateFileW
    _OPEN_EXISTING = 3
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    # attributes
    _FILE_ATTRIBUTE_DIRECTORY = 0x10
    _FILE_ATTRIBUTE_REPARSE_POINT = 0x400
    # information classes
    _FileRenameInformation = 10
    _FileDispositionInformation = 13
    _FileFullDirectoryInfo = 14
    _FileFullDirectoryRestartInfo = 15
    # NTSTATUS
    _STATUS_OBJECT_NAME_NOT_FOUND = 0xC0000034
    _STATUS_OBJECT_PATH_NOT_FOUND = 0xC000003A
    _STATUS_OBJECT_NAME_COLLISION = 0xC0000035
    _STATUS_NOT_A_DIRECTORY = 0xC0000103
    _STATUS_FILE_IS_A_DIRECTORY = 0xC00000BA
    _ERROR_NO_MORE_FILES = 18

    def _status(value: int) -> int:
        return value & 0xFFFFFFFF

    def _nt_open(root: int, name: str, access: int, share: int, disposition: int, options: int) -> tuple[int, int]:
        """``(status, handle)`` of an ``NtCreateFile`` relative to ``root``. Nothing is resolved by name above ``root``."""
        buffer = ctypes.create_unicode_buffer(name)
        size = len(name) * ctypes.sizeof(ctypes.c_wchar)
        unicode = _UnicodeString(size, size + ctypes.sizeof(ctypes.c_wchar), ctypes.cast(buffer, wintypes.LPWSTR))
        attributes = _ObjectAttributes(
            ctypes.sizeof(_ObjectAttributes), wintypes.HANDLE(root), ctypes.pointer(unicode),
            _OBJ_CASE_INSENSITIVE, None, None,
        )
        handle = wintypes.HANDLE()
        io = _IoStatusBlock()
        status = _status(_NtCreateFile(
            ctypes.byref(handle), access, ctypes.byref(attributes), ctypes.byref(io),
            None, 0, share, disposition, options, None, 0,
        ))
        return status, (handle.value or 0)

    def _info(handle: int) -> "_ByHandleFileInformation":
        info = _ByHandleFileInformation()
        if not _GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise _refuse(f"cannot show what an opened Review path component is (error {ctypes.get_last_error()})")
        return info

    class _WindowsDirectory:
        """A directory held open by handle - pinned, reached without following anything."""

        #: Held without FILE_SHARE_DELETE: nobody can rename, delete or replace it while it is held.
        PINS_HELD_DIRECTORIES = True

        def __init__(self, handle: int, described: str) -> None:
            self.handle = handle
            self.described = described

        @classmethod
        def _checked(cls, handle: int, described: str) -> "_WindowsDirectory":
            info = _info(handle)
            if info.dwFileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                _CloseHandle(handle)
                raise _refuse(
                    f"{described} is a junction, symlink or other reparse point, and a Review path is walked "
                    "only through plain in-Project directories"
                )
            if not info.dwFileAttributes & _FILE_ATTRIBUTE_DIRECTORY:
                _CloseHandle(handle)
                raise _refuse(f"{described} is not a plain directory")
            return cls(handle, described)

        @classmethod
        def open_root(cls, path: Path) -> "_WindowsDirectory":
            handle = _CreateFileW(
                str(path), _DIR_ACCESS, _PIN_SHARE, None, _OPEN_EXISTING,
                _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT, None,
            )
            if handle in (None, 0, _INVALID_HANDLE):
                raise _refuse(f"the Project root cannot be opened as a plain directory ({path}): error {ctypes.get_last_error()}")
            return cls._checked(handle, str(path))

        def child(self, name: str, *, create: bool) -> "_WindowsDirectory | None":
            _require_component(name)
            described = f"{self.described}\\{name}"
            status, handle = _nt_open(
                self.handle, name, _DIR_ACCESS, _PIN_SHARE, _FILE_OPEN_IF if create else _FILE_OPEN,
                _FILE_DIRECTORY_FILE | _FILE_SYNCHRONOUS_IO_NONALERT | _FILE_OPEN_REPARSE_POINT,
            )
            if status in (_STATUS_OBJECT_NAME_NOT_FOUND, _STATUS_OBJECT_PATH_NOT_FOUND) and not create:
                return None
            if status == _STATUS_NOT_A_DIRECTORY:
                raise _refuse(f"{described} is not a directory")
            if status != 0:
                raise _refuse(f"{described} cannot be opened (NTSTATUS 0x{status:08X})")
            return self._checked(handle, described)

        def entries(self) -> list[Entry]:
            found: list[Entry] = []
            size = 64 * 1024
            buffer = ctypes.create_string_buffer(size)
            info_class = _FileFullDirectoryRestartInfo
            while True:
                if not _GetFileInformationByHandleEx(self.handle, info_class, buffer, size):
                    error = ctypes.get_last_error()
                    if error == _ERROR_NO_MORE_FILES:
                        break
                    raise _refuse(f"{self.described} cannot be listed (error {error})")
                info_class = _FileFullDirectoryInfo
                offset = 0
                while True:
                    next_offset = int.from_bytes(buffer.raw[offset:offset + 4], "little")
                    attributes = int.from_bytes(buffer.raw[offset + 56:offset + 60], "little")
                    name_length = int.from_bytes(buffer.raw[offset + 60:offset + 64], "little")
                    name = buffer.raw[offset + 68:offset + 68 + name_length].decode("utf-16-le")
                    if name not in (".", ".."):
                        reparse = bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)
                        directory = bool(attributes & _FILE_ATTRIBUTE_DIRECTORY)
                        found.append(Entry(name, is_dir=directory and not reparse,
                                           is_file=not directory and not reparse, is_indirection=reparse))
                    if next_offset == 0:
                        break
                    offset += next_offset
            return sorted(found, key=lambda item: item.name)

        def final_object(self, name: str) -> "FinalObjectInfo | None":
            """What ``name`` itself denotes, from a handle opened without reparse traversal.

            Neither ``FILE_DIRECTORY_FILE`` nor ``FILE_NON_DIRECTORY_FILE`` is
            asked for, so one query shape opens a file, a directory, a junction
            or any other reparse point. Measured on NTFS: a junction's own file
            index differs from its target's, and ``FILE_ATTRIBUTE_REPARSE_POINT``
            is set on it - identified, never traversed.
            """
            _require_component(name)
            described = f"{self.described}\\{name}"
            status, handle = _nt_open(
                self.handle, name, _FILE_READ_ATTRIBUTES | _SYNCHRONIZE, _QUERY_SHARE, _FILE_OPEN,
                _FILE_SYNCHRONOUS_IO_NONALERT | _FILE_OPEN_REPARSE_POINT,
            )
            if status in (_STATUS_OBJECT_NAME_NOT_FOUND, _STATUS_OBJECT_PATH_NOT_FOUND):
                return None  # positive absence, the one answer that is not a refusal
            if status != 0:
                raise _refuse(f"{described} cannot be identified (NTSTATUS 0x{status:08X})")
            try:
                info = _info(handle)
                attributes = info.dwFileAttributes
                reparse = bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)
                directory = bool(attributes & _FILE_ATTRIBUTE_DIRECTORY)
                return FinalObjectInfo(
                    (info.dwVolumeSerialNumber, (info.nFileIndexHigh << 32) | info.nFileIndexLow),
                    is_dir=directory and not reparse,
                    is_file=not directory and not reparse,
                    is_indirection=reparse,
                )
            finally:
                _CloseHandle(handle)

        def read_file(self, name: str) -> bytes | None:
            _require_component(name)
            described = f"{self.described}\\{name}"
            status, handle = _nt_open(
                self.handle, name, _GENERIC_READ | _SYNCHRONIZE, _FILE_SHARE_READ, _FILE_OPEN,
                _FILE_NON_DIRECTORY_FILE | _FILE_SYNCHRONOUS_IO_NONALERT | _FILE_OPEN_REPARSE_POINT,
            )
            if status in (_STATUS_OBJECT_NAME_NOT_FOUND, _STATUS_OBJECT_PATH_NOT_FOUND):
                return None
            if status == _STATUS_FILE_IS_A_DIRECTORY:
                raise _refuse(f"{described} is a directory, not a plain file")
            if status != 0:
                raise _refuse(f"{described} cannot be opened (NTSTATUS 0x{status:08X})")
            try:
                if _info(handle).dwFileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                    raise _refuse(f"{described} is a reparse point, and a Review record is read only from a plain file")
                chunks: list[bytes] = []
                chunk = ctypes.create_string_buffer(1 << 16)
                read = wintypes.DWORD()
                while True:
                    if not _ReadFile(handle, chunk, len(chunk), ctypes.byref(read), None):
                        raise _refuse(f"{described} cannot be read (error {ctypes.get_last_error()})")
                    if read.value == 0:
                        break
                    chunks.append(chunk.raw[: read.value])
                return b"".join(chunks)
            finally:
                _CloseHandle(handle)

        def _set_information(self, handle: int, data: ctypes.Array, info_class: int) -> int:
            io = _IoStatusBlock()
            return _status(_NtSetInformationFile(handle, ctypes.byref(io), data, len(data), info_class))

        def create_file_exclusive(self, name: str, data: bytes, tmp: "_WindowsDirectory") -> bool:
            """Create ``name`` holding ``data``; ``False``, with nothing changed, if the name already exists."""
            _require_component(name)
            status, handle = _nt_open(
                tmp.handle, _tmp_name(name), _GENERIC_WRITE | _DELETE | _SYNCHRONIZE, 0, _FILE_CREATE,
                _FILE_NON_DIRECTORY_FILE | _FILE_SYNCHRONOUS_IO_NONALERT,
            )
            if status != 0:
                raise _refuse(f"a temporary Review file cannot be created (NTSTATUS 0x{status:08X})")
            delete_on_close = ctypes.create_string_buffer(b"\x01", 1)
            try:
                view = memoryview(data)
                written = wintypes.DWORD()
                while view:
                    part = bytes(view[: 1 << 20])
                    if not _WriteFile(handle, part, len(part), ctypes.byref(written), None) or written.value == 0:
                        raise _refuse(f"a temporary Review file cannot be written (error {ctypes.get_last_error()})")
                    view = view[written.value:]
                if not _FlushFileBuffers(handle):
                    raise _refuse(f"a temporary Review file cannot be flushed (error {ctypes.get_last_error()})")
            except BaseException:
                self._set_information(handle, delete_on_close, _FileDispositionInformation)
                _CloseHandle(handle)
                raise
            try:
                # FILE_RENAME_INFORMATION (x64/x86): ReplaceIfExists at 0, RootDirectory
                # at the next pointer boundary, FileNameLength, then FileName.
                encoded = name.encode("utf-16-le")
                pointer = ctypes.sizeof(ctypes.c_void_p)
                name_at = pointer + pointer + 4
                rename = ctypes.create_string_buffer(name_at + len(encoded) + 2)
                rename[0] = 0  # ReplaceIfExists = FALSE: an existing name is a collision, never replaced
                ctypes.memmove(ctypes.addressof(rename) + pointer, ctypes.byref(wintypes.HANDLE(self.handle)), pointer)
                ctypes.memmove(ctypes.addressof(rename) + pointer + pointer, ctypes.byref(wintypes.ULONG(len(encoded))), 4)
                ctypes.memmove(ctypes.addressof(rename) + name_at, encoded, len(encoded))
                status = self._set_information(handle, rename, _FileRenameInformation)
                if status == _STATUS_OBJECT_NAME_COLLISION:
                    self._set_information(handle, ctypes.create_string_buffer(b"\x01", 1), _FileDispositionInformation)
                    return False
                if status != 0:
                    self._set_information(handle, ctypes.create_string_buffer(b"\x01", 1), _FileDispositionInformation)
                    raise _refuse(f"{self.described}\\{name} cannot be created (NTSTATUS 0x{status:08X})")
                return True
            finally:
                _CloseHandle(handle)

        def close(self) -> None:
            if self.handle:
                _CloseHandle(self.handle)
                self.handle = 0

    _Backend = _WindowsDirectory
else:
    _Backend = _PosixDirectory


# --------------------------------------------------------------------------- public surface

def immutable_create_supported() -> bool:
    """Whether a create here can keep its proven parent inside the Project until the name is placed.

    Only a backend that pins every directory it holds can: nothing it holds,
    from the Project root down, can be moved while the create runs. On Windows
    that is the share mode every directory is opened with; on POSIX an fd pins
    nothing, so there is no create there at all.
    """
    return _Backend.PINS_HELD_DIRECTORIES


def require_immutable_create() -> None:
    """Refuse, before anything is opened or written, a canonical Review create this platform cannot contain."""
    if not immutable_create_supported():
        raise _unsupported()


class SafeDirectory:
    """A proven, plain in-Project directory, held open. Use as a context manager."""

    def __init__(self, backend: object) -> None:
        self._backend = backend

    def __enter__(self) -> "SafeDirectory":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @classmethod
    def open_root(cls, path: Path) -> "SafeDirectory":
        return cls(_Backend.open_root(Path(path)))

    @property
    def described(self) -> str:
        return self._backend.described

    def child(self, name: str, *, create: bool = False) -> "SafeDirectory | None":
        found = self._backend.child(name, create=create)
        return None if found is None else SafeDirectory(found)

    def entries(self) -> list[Entry]:
        return self._backend.entries()

    def read_file(self, name: str) -> bytes | None:
        return self._backend.read_file(name)

    def final_object(self, name: str) -> "FinalObjectInfo | None":
        """What ``name`` itself denotes, without following it; ``None`` when it does not exist.

        One component, relative to this already-proven directory - the caller
        owns the walk that proved it. Unlike :meth:`read_file` and
        :meth:`child`, a final indirection is an ANSWER here, not a refusal;
        see the module docstring for why the two must differ.
        """
        return self._backend.final_object(name)

    def create_file_exclusive(self, name: str, data: bytes, tmp: "SafeDirectory") -> bool:
        """Create ``name`` holding ``data``; ``False``, with nothing changed, if the name already exists."""
        require_immutable_create()
        return self._backend.create_file_exclusive(name, data, tmp._backend)

    def close(self) -> None:
        self._backend.close()


class Chain:
    """Directories walked from the Project root, every one held open for as long as the chain lives."""

    def __init__(self, directories: list[SafeDirectory]) -> None:
        self.directories = directories

    @property
    def last(self) -> SafeDirectory:
        return self.directories[-1]

    def __enter__(self) -> "Chain":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        for directory in reversed(self.directories):
            directory.close()
        self.directories = []


def walk(root: Path, parts: list[str], *, create: bool = False) -> Chain | None:
    """Walk ``root`` -> ``parts`` without following anything, holding every directory.

    ``None`` when a component does not exist and ``create`` is false - the
    lazily created Review directories are simply not there yet. Anything present
    that is not a plain directory is refused, not skipped. Creating the missing
    ones is part of a create, so it is refused wherever a create is
    (:func:`require_immutable_create`).
    """
    if create:
        require_immutable_create()
    directories: list[SafeDirectory] = [SafeDirectory.open_root(root)]
    try:
        for part in parts:
            found = directories[-1].child(part, create=create)
            if found is None:
                for directory in reversed(directories):
                    directory.close()
                return None
            directories.append(found)
    except BaseException:
        for directory in reversed(directories):
            directory.close()
        raise
    return Chain(directories)


# --------------------------------------------------------------------------- the submodule HEAD

#: The name a submodule's git directory is reached through, as a directory or as a gitfile.
GIT_NAME = ".git"

#: What a gitfile declares, and the only declaration it may hold - the LITERAL eight bytes
#: Git writes and accepts, colon then exactly ONE space. Measured on Git 2.54.0.windows.1
#: against a real local submodule: `gitdir:X` and `gitdir:\tX` are "invalid gitfile format",
#: a blank line or a space BEFORE the declaration is too, and `gitdir:  X` / a trailing space
#: or tab leave Git looking for a path that is not there. So the spelling is not whitespace to
#: be tidied up - it is the grammar, and the value after it is taken VERBATIM.
GITDIR_DECLARATION = b"gitdir: "
GITDIR_PREFIX = "gitdir:"

#: What a symbolic HEAD or ref names another ref with.
SYMREF_PREFIX = "ref:"

#: A full object id, and nothing shorter, longer or upper-case. ``fullmatch`` is used
#: everywhere below: ``$`` alone would also match before a final newline, and a digest
#: with a newline after it is not a digest.
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


def _require_oid(value: str, described: str) -> str:
    if _OID.fullmatch(value) is None:
        raise _refuse(
            f"{described} is {value!r}, which is not a full lowercase object id "
            "(40 hex for SHA-1, 64 for SHA-256, and nothing else)"
        )
    return value


def _one_line(raw: bytes, described: str) -> str:
    """The single line ``raw`` holds, with at most one trailing newline and nothing after it."""
    if b"\0" in raw:
        raise _refuse(f"{described} holds a NUL byte")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _refuse(f"{described} is not UTF-8: {exc}") from exc
    if text.endswith("\n"):
        text = text[:-1]
    if "\n" in text or "\r" in text:
        raise _refuse(f"{described} holds more than one line")
    return text


def _gitdir_components(raw: bytes, described: str) -> list[str]:
    """The RELATIVE components a gitfile declares. Anything else fails closed.

    Absolute in every spelling is refused, because an absolute gitdir is exactly
    the pathname re-resolution this reader exists to avoid: it cannot be walked
    against the held chain, so there is no chain left to bind to.

    THE SPELLING IS THE GRAMMAR, AND THE VALUE IS TAKEN VERBATIM. An earlier
    draft matched the prefix ``gitdir:`` and then stripped spaces and tabs around
    what followed, which quietly turned six spellings Git REFUSES -
    ``gitdir:X``, ``gitdir:  X``, ``gitdir:\\tX``, a trailing space, a trailing
    tab, and a blank line before the declaration - into the canonical path, and
    so synthesised an authoritative gitlink identity for a submodule Git itself
    cannot open. Nothing is tidied up here now: the file must BEGIN with the
    exact eight bytes :data:`GITDIR_DECLARATION`, and the rest of that first line
    is the path as written. A stray space then survives into a component that
    does not exist, and the walk refuses it for the same reason Git does.
    """
    if b"\0" in raw:
        raise _refuse(f"{described} holds a NUL byte")
    if not raw.startswith(GITDIR_DECLARATION):
        raise _refuse(
            f"{described} does not begin with {GITDIR_DECLARATION.decode('ascii')!r}; that exact spelling - "
            "colon, one space, then the path - is the gitfile grammar, and this reader does not repair a "
            "declaration into it"
        )
    head, _, rest = raw.partition(b"\n")
    for line in rest.split(b"\n"):
        if line.strip():
            raise _refuse(f"{described} holds {line!r} after the declaration; a gitfile declares once and stops")
    try:
        value = head[len(GITDIR_DECLARATION):].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _refuse(f"{described} is not UTF-8: {exc}") from exc
    if not value:
        raise _refuse(f"{described} declares an empty gitdir")
    if "\\" in value:
        raise _refuse(
            f"{described} declares {value!r}; a gitfile separates components with '/' on every platform, "
            "and a backslash spelling is not walked against the held chain"
        )
    if value.startswith("/") or ":" in value.split("/")[0]:
        raise _refuse(
            f"{described} declares the absolute gitdir {value!r}; only a relative gitdir can be resolved "
            "against the handles already held, and an absolute one would be resolved by name from the root again"
        )
    components = value.split("/")
    if any(component == "" for component in components):
        raise _refuse(f"{described} declares {value!r}, which holds an empty component")
    return components


def _walk_held(chain: "Chain", components: list[str], opened: list[SafeDirectory], described: str) -> SafeDirectory:
    """Resolve ``components`` against the chain's own handles, never against a pathname.

    ``..`` steps back to a directory the walk ALREADY HOLDS - it is never asked
    of the filesystem, which would answer about wherever the directory is now.
    Stepping back past the Project root is refused: the chain holds nothing
    above it, so there is nothing there this reader is entitled to.
    """
    stack: list[SafeDirectory] = list(chain.directories)
    for component in components:
        if component == "..":
            if len(stack) <= 1:
                raise _refuse(
                    f"{described} steps above the Project root, which the held chain does not reach"
                )
            stack.pop()
            continue
        if component == ".":
            raise _refuse(f"{described} holds a '.' component")
        found = stack[-1].child(component)  # refuses an indirection and anything not a plain directory
        if found is None:
            raise _refuse(f"{described} names {component!r}, which does not exist in {stack[-1].described}")
        opened.append(found)
        stack.append(found)
    return stack[-1]


def _git_directory(chain: "Chain", opened: list[SafeDirectory]) -> SafeDirectory:
    """G-2 and G-3: the submodule's git directory, reached from the handle the chain already holds."""
    submodule = chain.last
    described = f"{submodule.described}/{GIT_NAME}"
    found = submodule.final_object(GIT_NAME)
    if found is None:
        raise _refuse(f"{described} does not exist, so this is not a submodule working tree")
    if found.is_indirection:
        raise _refuse(f"{described} is a symlink, junction or other reparse point, and is not followed")
    if found.is_dir:
        # G-2/G-3 collapse: the git directory IS this name, opened from the held handle
        directory = submodule.child(GIT_NAME)
        if directory is None:
            raise _refuse(f"{described} disappeared while it was opened")
        opened.append(directory)
        return directory
    if not found.is_file:
        raise _refuse(f"{described} is neither a plain directory nor a plain gitfile")
    raw = submodule.read_file(GIT_NAME)
    if raw is None:
        raise _refuse(f"{described} disappeared while it was read")
    return _walk_held(chain, _gitdir_components(raw, described), opened, f"the gitdir {described} declares")


def _require_refname(refname: str, described: str) -> list[str]:
    """The components of a ref name, or a refusal. A ref name is a path inside the git directory.

    A COLON IS REFUSED WHEREVER IT APPEARS, not only in the first component.
    Measured on NTFS: ``refs/heads/main:evil`` names an ALTERNATE DATA STREAM of
    the real ``main`` ref - it reads back different bytes, it is attached to the
    legitimate file, and a directory listing shows only ``main``, so nothing that
    enumerates the namespace can see it. ``git check-ref-format`` rejects that
    name and ``git rev-parse`` refuses such a HEAD, so a spelling Git will not
    accept as a ref must not become a commit identity here merely because the
    filesystem can address it. The refusal belongs at this boundary: the shared
    component predicate and :meth:`SafeDirectory.read_file` both predate this
    unit and mean something else by a name.

    The same bounded audit found no other equivalent vector among the spellings
    ``git check-ref-format`` rejects: ``main[x]``, ``main~1``, ``main^`` and
    ``main.lock`` are ordinary separate files, visible in a listing and no more
    reachable than any other name, and ``main*`` / ``main?`` cannot be created on
    NTFS at all. Only the colon addresses a hidden alternate of the real object.
    """
    if not refname:
        raise _refuse(f"{described} names an empty ref")
    if ":" in refname:
        raise _refuse(
            f"{described} names {refname!r}; a colon is not part of a Git ref name, and on NTFS it addresses "
            "an alternate data stream of the ref beside it - a hidden object no listing of the namespace shows"
        )
    if "\\" in refname or "\0" in refname:
        raise _refuse(f"{described} names {refname!r}, which holds a backslash or a NUL")
    if refname.startswith("/") or ":" in refname.split("/")[0]:
        raise _refuse(f"{described} names the absolute ref {refname!r}")
    components = refname.split("/")
    for component in components:
        if component in ("", ".", ".."):
            raise _refuse(f"{described} names {refname!r}, which would leave the git directory")
        _require_component(component)
    return components


def _loose_ref(gitdir: SafeDirectory, components: list[str], opened: list[SafeDirectory]) -> bytes | None:
    """The bytes of the loose ref, or ``None`` when it is positively absent."""
    directory = gitdir
    for component in components[:-1]:
        found = directory.child(component)  # an indirection here fails closed; it is never a fallback
        if found is None:
            return None
        opened.append(found)
        directory = found
    return directory.read_file(components[-1])


def _packed_ref(gitdir: SafeDirectory, refname: str) -> str:
    """The OID ``packed-refs`` binds to ``refname``, by exact name, or a refusal.

    Narrow on purpose: an ordinary ``<oid> <refname>`` record, with ``#`` headers
    and ``^`` peeled lines skipped because a lawful file holds them. An unrelated
    line is never allowed to answer for the ref that was asked about, and an
    unrelated MALFORMED line is not validated either - this reader is not a
    checker of the whole ref graph.

    EVERY record for the requested ref is read before any answer is given. An
    earlier draft returned on the first exact name match, which does not
    establish an identity at all: measured against Git, two records binding the
    same ref to different commits made this reader answer with the FIRST and Git
    with the LAST - opposite commits from the same bytes, decided by scan order -
    and a valid record followed by a malformed one for that ref made Git refuse
    while this reader answered. So the whole file is scanned, every binding for
    the requested ref must parse, and the answer is given only when those
    bindings agree on ONE commit.

    Contradictory duplicates FAIL CLOSED here rather than reproducing Git's
    last-record rule. G-5 requires one exact referenced object id or a refusal,
    and "whichever record came last" is not an identity a Candidate should be
    frozen against.
    """
    raw = gitdir.read_file("packed-refs")
    if raw is None:
        raise _refuse(
            f"{gitdir.described} binds HEAD to {refname!r}, which has neither a loose ref nor a packed-refs file"
        )
    if b"\0" in raw:
        raise _refuse(f"{gitdir.described}/packed-refs holds a NUL byte")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _refuse(f"{gitdir.described}/packed-refs is not UTF-8: {exc}") from exc
    bindings: list[str] = []
    for line in text.split("\n"):
        line = line.rstrip("\r")
        if not line or line.startswith("#") or line.startswith("^"):
            continue
        oid, separator, name = line.partition(" ")
        if not separator or name != refname:
            continue
        # a malformed binding for the ref being asked about is a refusal, never a record to skip
        bindings.append(_require_oid(oid, f"the packed-refs record for {refname}"))
    if not bindings:
        raise _refuse(f"{gitdir.described}/packed-refs does not bind {refname!r}")
    unique = set(bindings)
    if len(unique) != 1:
        raise _refuse(
            f"{gitdir.described}/packed-refs binds {refname!r} to {len(unique)} different object ids "
            f"({', '.join(sorted(unique))}); that is not one identity, and this reader will not pick one"
        )
    return bindings[0]


def submodule_head(chain: "Chain") -> str:
    """The exact commit id a submodule's HEAD names, read only through held handles (G-1 ... G-5).

    ``chain``'s last directory IS the submodule working tree, proven by whoever
    walked it (G-1). Nothing here re-opens it, re-resolves its pathname, runs
    Git, or consults the superproject's index - the index still holds the commit
    from before the executor ran, which is the value this reader exists NOT to
    return.

    The answer is one full lowercase object id and nothing else: never a branch
    name, never a symbolic ref, never an abbreviation (G-5).
    """
    if not chain.directories:
        raise _refuse("a submodule HEAD is read from a held chain, and this chain holds nothing")
    opened: list[SafeDirectory] = []
    try:
        gitdir = _git_directory(chain, opened)
        described = f"{gitdir.described}/HEAD"
        raw = gitdir.read_file("HEAD")
        if raw is None:
            raise _refuse(f"{described} does not exist")
        text = _one_line(raw, described)
        if not text.startswith(SYMREF_PREFIX):
            return _require_oid(text, described)  # a detached HEAD IS the identity
        refname = text[len(SYMREF_PREFIX):].strip(" \t")
        components = _require_refname(refname, described)
        loose = _loose_ref(gitdir, components, opened)
        if loose is not None:
            # present but malformed is a refusal, never a reason to go looking somewhere else
            return _require_oid(_one_line(loose, f"{gitdir.described}/{refname}"), f"{gitdir.described}/{refname}")
        return _packed_ref(gitdir, refname)
    finally:
        for directory in reversed(opened):
            directory.close()
