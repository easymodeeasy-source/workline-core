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
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
import os
from pathlib import Path
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
    _PIN_SHARE = _FILE_SHARE_READ | _FILE_SHARE_WRITE
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
