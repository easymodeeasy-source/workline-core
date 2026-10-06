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

Reading a link's target, which is not the same as following it
---------------------------------------------------------------

:meth:`SafeDirectory.read_link` returns the bytes Git stores as the blob of a
mode-120000 entry for a final link, together with the link's OWN identity:

```text
POSIX    fstatat(AT_SYMLINK_NOFOLLOW) + readlinkat(<held fd>, name)
Windows  NtCreateFile(RootDirectory=<held handle>, FILE_OPEN_REPARSE_POINT)
         + GetFileInformationByHandle + FSCTL_GET_REPARSE_POINT, all on ONE handle
```

On Windows the bytes are not the reparse data as it lies: Git for Windows
records a link through its own rule, and :func:`windows_link_target` is that
rule, taken from its source and measured against it. A reparse point Git does
not record as a link - a junction, which it treats as a directory and follows,
or any other tag - has no link target here and is refused, never followed.

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
import struct
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


@dataclass(frozen=True)
class BoundFile:
    """A plain file read through ONE handle opened relative to a held directory.

    ``data``, ``identity`` and ``executable`` all come from that same open
    handle, so they describe one object: nothing is looked up again by name
    between reading the bytes and saying which object they came from.
    ``identity`` compares with :attr:`FinalObjectInfo.identity` and with
    :meth:`SafeDirectory.identity`. ``executable`` is the owner-execute
    permission bit where the platform carries one, and ``None`` where it does
    not: a platform without that bit says nothing about it, which is not the
    same as saying "not executable".
    """

    data: bytes
    identity: tuple
    executable: bool | None


@dataclass(frozen=True)
class BoundLink:
    """A final link's target bytes and its OWN identity, read relative to a held directory without following it.

    ``target`` is what Git stores as the blob of a mode-120000 entry for this
    link on this platform. ``identity`` is the link object's - never its
    target's - and compares with :attr:`FinalObjectInfo.identity`. On Windows
    both come from ONE handle, so they describe one object; POSIX has no handle
    on a link itself, so there the identity is the no-follow query made
    immediately before ``readlinkat``, and a caller brackets the read with its
    own before/after identity comparison.
    """

    target: bytes
    identity: tuple


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


# --------------------------------------------------------------------------- Windows link targets, Git's rule
#
# Only reading the reparse data needs Windows; the rule over it is pure, so it is tested everywhere.
# It is Git for Windows 2.54.0.windows.1's own (compat/mingw.c and compat/win32/fscache.c at commit
# 2b8a3ab140826ac423c2845ef81d4c6ac4f7bf3c, the commit `git version --build-options` names here;
# git.exe imports msvcrt.dll):
#
#     mingw_lstat           reads a reparse point's data first; if read_reparse_point fails, lstat
#                           fails and Git cannot stage the path at all
#     read_reparse_point    the SUBSTITUTE name, NUL-terminated at SubstituteNameLength - and, as a C
#                           wide string, ending at its first NUL
#     normalize_ntpath      "\??\" or "\\?\" stripped, else "\DosDevices\" by wcsnicmp; then a leading
#                           "UNC\" (wcsnicmp) becomes "\\"; then every "\" becomes "/"
#     xwcstoutf             WideCharToMultiByte(CP_UTF8, 0, name, -1, buffer, MAX_PATH, NULL, NULL)
#     file_attr_to_st_mode  S_IFLNK only for IO_REPARSE_TAG_SYMLINK (a junction is S_IFDIR); and ONLY
#                           when is_inside_windows_container(), a link whose target starts with
#                           "/ContainerMappedDirectories/" is S_IFDIR too. fscache asks the same question
#     is_inside_windows_container  RegOpenKeyExA(HKLM, "SYSTEM\CurrentControlSet\Services\cexecsvc", 0,
#                           KEY_READ, ...) == ERROR_SUCCESS
#
# MEASURED, with no privilege:
#   the system link C:\Users\All Users (tag 0xA000000C, substitute name \??\C:\ProgramData) is staged
#     as 120000 e0316278a6be6fdf..., the 14 bytes "C:/ProgramData", core.symlinks false and true alike;
#     a junction (0xA0000003) is "a directory" to `git update-index --add`, and `git add` walks into it;
#   wcsnicmp: git.exe never sets LC_CTYPE (gettext sets LC_MESSAGES and LC_TIME only), and msvcrt's
#     _wcsnicmp, over every UTF-16 code unit against every letter of "\DosDevices\" and "UNC\", folds
#     exactly the ASCII letters - in the "C" locale, and in this user's Japanese_Japan.932 as well;
#   WideCharToMultiByte with Git's arguments: an unpaired surrogate becomes U+FFFD (EF BF BD), a NUL
#     ends the string, 259 bytes fit and 260 fail with ERROR_INSUFFICIENT_BUFFER;
#   FSCTL_SET_REPARSE_POINT validates a symbolic-link buffer BEFORE it checks the privilege: an empty
#     substitute or print name, an odd offset or length, a name outside the data and a header length
#     that disagrees are ERROR_INVALID_REPARSE_DATA - no such link can exist - while an embedded NUL,
#     a leading NUL, an unpaired surrogate, "\??\" alone and a container-mapped target all pass on to
#     the privilege check: links that can exist, and Git stages each of them.

#: The one reparse tag Git for Windows stages as a mode-120000 link.
IO_REPARSE_TAG_SYMLINK = 0xA000000C
#: A junction: a DIRECTORY to Git for Windows, which follows it. Never a link target here.
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
#: The buffer Git converts a link target into: MAX_PATH bytes, the terminating NUL included.
GIT_LINK_TARGET_BUFFER = 260
#: The longest target Git for Windows can read, in UTF-8 bytes: MAX_PATH less the NUL.
GIT_LINK_TARGET_LIMIT = GIT_LINK_TARGET_BUFFER - 1
#: What Git for Windows takes, INSIDE a Windows container only, for a mapped volume - a directory.
CONTAINER_MAPPED_PREFIX = "/ContainerMappedDirectories/"
#: The key whose presence is Git for Windows' whole test for running inside a Windows container.
CONTAINER_SERVICE_KEY = "SYSTEM\\CurrentControlSet\\Services\\cexecsvc"

_REPARSE_HEADER = 8  # ReparseTag (4), ReparseDataLength (2), Reserved (2)
_SYMLINK_FIELDS = 12  # SubstituteNameOffset/Length, PrintNameOffset/Length (2 each), Flags (4)
_CP_UTF8 = 65001


def _ascii_fold(unit: str) -> str:
    return chr(ord(unit) + 32) if "A" <= unit <= "Z" else unit


def _device_prefix(text: str, literal: str) -> bool:
    """``wcsnicmp(text, literal, len(literal)) == 0`` as git.exe's runtime answers it: ASCII letters fold, nothing else.

    msvcrt's ``_wcsnicmp`` in the locale Git runs it in folds exactly the ASCII
    letters (measured over every UTF-16 code unit); a shorter name differs at
    its terminating NUL.
    """
    return len(text) >= len(literal) and all(_ascii_fold(a) == _ascii_fold(b) for a, b in zip(text, literal))


def _normalize_ntpath(target: str) -> str:
    """Git for Windows' ``normalize_ntpath``, exactly, over a NUL-free name."""
    if target.startswith("\\"):
        if target.startswith(("\\??\\", "\\\\?\\")):
            target = target[4:]
        elif _device_prefix(target, "\\DosDevices\\"):
            target = target[12:]
        if _device_prefix(target, "UNC\\"):
            target = "\\" + target[3:]  # wbuf += 2; *wbuf = '\\'
    return target.replace("\\", "/")


#: ``WideCharToMultiByte`` itself where it exists (assigned in the Windows backend below).
_native_wide_to_utf8 = None


def _wide_to_utf8_written_out(name: str) -> bytes | None:
    """What :func:`_utf8_as_git_converts` computes natively, written out for a platform without the call.

    Over the UTF-16 code units, as the call sees them: a high surrogate followed
    by a low one is one code point, every other surrogate code unit becomes
    U+FFFD - WideCharToMultiByte's own replacement with flags 0 - and a result
    that does not fit Git's buffer with its NUL is a failed read.
    """
    raw = name.encode("utf-16-le", "surrogatepass")
    units = [int.from_bytes(raw[index:index + 2], "little") for index in range(0, len(raw), 2)]
    out = bytearray()
    index = 0
    while index < len(units):
        unit = units[index]
        follower = units[index + 1] if index + 1 < len(units) else 0
        if 0xD800 <= unit <= 0xDBFF and 0xDC00 <= follower <= 0xDFFF:
            out += chr(0x10000 + ((unit - 0xD800) << 10) + (follower - 0xDC00)).encode("utf-8")
            index += 2
            continue
        out += ("\ufffd" if 0xD800 <= unit <= 0xDFFF else chr(unit)).encode("utf-8")
        index += 1
    return bytes(out) if len(out) < GIT_LINK_TARGET_BUFFER else None


def _utf8_as_git_converts(name: str) -> bytes | None:
    """Git's ``xwcstoutf(buffer, name, MAX_PATH)``: the UTF-8 bytes, or ``None`` where Git's read fails.

    ``name`` holds the link's UTF-16 code units - a valid pair as one code point,
    an unpaired surrogate as itself. On Windows this is the very call Git makes,
    with Git's arguments, so the replacement of an unpaired surrogate and the
    length at which the read fails are the platform's own answer, not a copy of it.
    """
    if _native_wide_to_utf8 is not None:
        return _native_wide_to_utf8(name)
    return _wide_to_utf8_written_out(name)


def inside_windows_container() -> bool:
    """Git for Windows' ``is_inside_windows_container()``: ``HKLM\\`` :data:`CONTAINER_SERVICE_KEY` opens for KEY_READ.

    Exactly the condition Git asks, and the only one: no environment variable or
    other sign of a container is consulted, because Git consults none.
    """
    if sys.platform != "win32":
        return False
    import winreg

    try:
        winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CONTAINER_SERVICE_KEY, 0, winreg.KEY_READ).Close()
    except OSError:
        return False
    return True


def windows_link_target(raw: bytes, described: str) -> bytes:
    """The blob Git for Windows stores for a link whose ``FSCTL_GET_REPARSE_POINT`` data is ``raw``.

    Wherever Git stages the reparse point as a mode-120000 link, these are the
    bytes it stores - however its rule ended, rewrote, case-compared or
    normalized the name on the way: a name ending at its first NUL, an unpaired
    surrogate as U+FFFD, an empty name as empty bytes. Refused is only what Git
    itself does not stage as a link or cannot read: a tag that is not a link to
    Git (a junction is a directory to it, and it follows one), a target too long
    for Git's read, and - inside a Windows container, decided by Git's own test -
    a container-mapped volume, which Git takes for a directory. Reparse data the
    kernel never admits for a link (measured) is refused as malformed. The link
    is never followed and its target never has to exist, so a broken link is
    read like any other.
    """
    if len(raw) < _REPARSE_HEADER:
        raise _refuse(f"{described} returned reparse data too short to hold a reparse tag")
    tag, data_length = struct.unpack_from("<IH", raw, 0)
    if tag != IO_REPARSE_TAG_SYMLINK:
        what = ("a junction, which Git for Windows treats as a directory and follows"
                if tag == IO_REPARSE_TAG_MOUNT_POINT else "not a symbolic link to Git for Windows")
        raise _refuse(
            f"{described} is a reparse point of tag 0x{tag:08X} - {what}; it is never followed, and it has no "
            "link target here"
        )
    # the kernel's own admission rule for symbolic-link reparse data (measured): no other shape exists
    if data_length < _SYMLINK_FIELDS or _REPARSE_HEADER + data_length != len(raw):
        raise _refuse(f"{described} holds symbolic-link reparse data whose length disagrees with its own header")
    substitute_offset, substitute_length, print_offset, print_length = struct.unpack_from("<HHHH", raw, _REPARSE_HEADER)
    names = raw[_REPARSE_HEADER + _SYMLINK_FIELDS:]
    for offset, length in ((substitute_offset, substitute_length), (print_offset, print_length)):
        if not length or offset % 2 or length % 2 or offset + length > len(names):
            raise _refuse(
                f"{described} holds symbolic-link reparse data the kernel admits for no link (an empty, odd or "
                "out-of-range name)"
            )
    # read_reparse_point: the substitute name as a C wide string, so it ends at its first NUL
    name = names[substitute_offset:substitute_offset + substitute_length].decode("utf-16-le", "surrogatepass")
    data = _utf8_as_git_converts(_normalize_ntpath(name.split("\0", 1)[0]))
    if data is None:
        raise _refuse(
            f"{described} links to a target longer than Git for Windows can read ({GIT_LINK_TARGET_LIMIT} UTF-8 "
            "bytes): its lstat fails and Git stages nothing for it"
        )
    # file_attr_to_st_mode: inside a Windows container - and only there - Git takes this for a directory
    if data.startswith(CONTAINER_MAPPED_PREFIX.encode("ascii")) and inside_windows_container():
        raise _refuse(
            f"{described} links to {data!r} inside a Windows container, where Git for Windows takes it for a "
            "container-mapped directory and not for a link"
        )
    return data


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

    def replace_file(self, name: str, data: bytes, tmp: "_PosixDirectory") -> None:
        """Refused before anything is written: a replace is held to the same containment capability as a create."""
        raise _unsupported()

    def identity(self) -> tuple:
        """This held directory's own identity, from its fd: ``(st_dev, st_ino)``."""
        info = os.fstat(self.fd)
        return (info.st_dev, info.st_ino)

    def read_file_bound(self, name: str) -> "BoundFile | None":
        """``name``'s bytes, identity and owner-execute bit, all from one ``O_NOFOLLOW`` fd."""
        _require_component(name)
        described = f"{self.described}/{name}"
        try:
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), dir_fd=self.fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise _refuse(f"{described} is a symlink, and a plain file is read only from a plain file") from exc
            raise _refuse(f"{described} cannot be opened: {exc}") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise _refuse(f"{described} is not a plain file")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1 << 16)
                if not chunk:
                    break
                chunks.append(chunk)
            return BoundFile(b"".join(chunks), (info.st_dev, info.st_ino), bool(info.st_mode & stat.S_IXUSR))
        finally:
            os.close(fd)

    def read_link(self, name: str) -> "BoundLink | None":
        """The link ``name``: its exact target bytes by ``readlinkat`` relative to the held fd, never followed.

        Its identity is the ``fstatat(AT_SYMLINK_NOFOLLOW)`` query made just before
        the read - POSIX offers no handle on a link itself - so the caller's own
        before/after identity comparison is what brackets the read.
        """
        _require_component(name)
        described = f"{self.described}/{name}"
        try:
            info = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise _refuse(f"{described} cannot be identified without following it: {exc}") from exc
        if not stat.S_ISLNK(info.st_mode):
            raise _refuse(f"{described} is not a symbolic link")
        try:
            target = os.readlink(os.fsencode(name), dir_fd=self.fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise _refuse(f"{described} is not a link whose target can be read without following it: {exc}") from exc
        return BoundLink(target, (info.st_dev, info.st_ino))

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
    _DeviceIoControl = _kernel32.DeviceIoControl
    _DeviceIoControl.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
    ]
    _WideCharToMultiByte = _kernel32.WideCharToMultiByte
    _WideCharToMultiByte.restype = ctypes.c_int
    _WideCharToMultiByte.argtypes = [
        wintypes.UINT, wintypes.DWORD, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
        ctypes.c_void_p, ctypes.c_void_p,
    ]

    def _wide_to_utf8_native(name: str) -> bytes | None:
        """``WideCharToMultiByte(CP_UTF8, 0, name, -1, buffer, MAX_PATH, NULL, NULL)``: Git's ``xwcstoutf`` call, as it is."""
        wide = ctypes.create_string_buffer(name.encode("utf-16-le", "surrogatepass") + b"\0\0")
        out = ctypes.create_string_buffer(GIT_LINK_TARGET_BUFFER)
        written = _WideCharToMultiByte(_CP_UTF8, 0, wide, -1, out, GIT_LINK_TARGET_BUFFER, None, None)
        return out.raw[: written - 1] if written > 0 else None

    _native_wide_to_utf8 = _wide_to_utf8_native

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
    # FSCTL_GET_REPARSE_POINT: CTL_CODE(FILE_DEVICE_FILE_SYSTEM, 42, METHOD_BUFFERED, FILE_ANY_ACCESS)
    _FSCTL_GET_REPARSE_POINT = 0x000900A8
    _MAXIMUM_REPARSE_DATA_BUFFER_SIZE = 16 * 1024
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

    def _reparse_point(parent: int, name: str, described: str) -> "tuple[tuple, bytes] | None":
        """``(identity, reparse data)`` of the reparse point ``name``, both asked of ONE handle; ``None`` if absent.

        The handle is opened relative to ``parent`` with ``FILE_OPEN_REPARSE_POINT``
        and neither ``FILE_DIRECTORY_FILE`` nor ``FILE_NON_DIRECTORY_FILE``: the
        reparse point itself is opened, a file link and a directory link alike, and
        nothing is resolved through it - its target need not exist. That is the
        open :meth:`_WindowsDirectory.final_object` identifies with, so the identity
        here is the link's own, and the data is the data of that same object.
        """
        status, handle = _nt_open(
            parent, name, _FILE_READ_ATTRIBUTES | _SYNCHRONIZE, _QUERY_SHARE, _FILE_OPEN,
            _FILE_SYNCHRONOUS_IO_NONALERT | _FILE_OPEN_REPARSE_POINT,
        )
        if status in (_STATUS_OBJECT_NAME_NOT_FOUND, _STATUS_OBJECT_PATH_NOT_FOUND):
            return None
        if status != 0:
            raise _refuse(f"{described} cannot be opened as itself (NTSTATUS 0x{status:08X})")
        try:
            info = _info(handle)
            if not info.dwFileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                raise _refuse(f"{described} is not a reparse point, so it is not a link")
            buffer = ctypes.create_string_buffer(_MAXIMUM_REPARSE_DATA_BUFFER_SIZE)
            returned = wintypes.DWORD()
            if not _DeviceIoControl(handle, _FSCTL_GET_REPARSE_POINT, None, 0, buffer, len(buffer),
                                    ctypes.byref(returned), None):
                raise _refuse(f"the reparse data of {described} cannot be read (error {ctypes.get_last_error()})")
            identity = (info.dwVolumeSerialNumber, (info.nFileIndexHigh << 32) | info.nFileIndexLow)
            return identity, buffer.raw[: returned.value]
        finally:
            _CloseHandle(handle)

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

        def replace_file(self, name: str, data: bytes, tmp: "_WindowsDirectory") -> None:
            """Place ``data`` at ``name`` in this held directory, replacing the plain file that is there (P6 §30.18).

            The bytes are written to a temporary file in the held runtime area and
            placed by ONE rename relative to this pinned parent handle with
            ``ReplaceIfExists = TRUE``: the name is replaced as a directory entry,
            never resolved, so nothing at it is followed, and the parent cannot
            have moved out of the Project while it is held. Which bytes may be
            replaced is the caller's compare (:func:`compare_and_replace`), made
            through this same held parent immediately before.
            """
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
                encoded = name.encode("utf-16-le")
                pointer = ctypes.sizeof(ctypes.c_void_p)
                name_at = pointer + pointer + 4
                rename = ctypes.create_string_buffer(name_at + len(encoded) + 2)
                rename[0] = 1  # ReplaceIfExists = TRUE: the entry at the name is replaced, never followed
                ctypes.memmove(ctypes.addressof(rename) + pointer, ctypes.byref(wintypes.HANDLE(self.handle)), pointer)
                ctypes.memmove(ctypes.addressof(rename) + pointer + pointer, ctypes.byref(wintypes.ULONG(len(encoded))), 4)
                ctypes.memmove(ctypes.addressof(rename) + name_at, encoded, len(encoded))
                status = self._set_information(handle, rename, _FileRenameInformation)
                if status != 0:
                    self._set_information(handle, ctypes.create_string_buffer(b"\x01", 1), _FileDispositionInformation)
                    raise _refuse(f"{self.described}\\{name} cannot be replaced (NTSTATUS 0x{status:08X})")
            finally:
                _CloseHandle(handle)

        def identity(self) -> tuple:
            """This held directory's own identity, from its handle: volume serial plus file index."""
            info = _info(self.handle)
            return (info.dwVolumeSerialNumber, (info.nFileIndexHigh << 32) | info.nFileIndexLow)

        def read_file_bound(self, name: str) -> "BoundFile | None":
            """``name``'s bytes and identity from ONE handle opened relative to this held one.

            NTFS carries no owner-execute bit, so ``executable`` is ``None``: the
            platform says nothing about it, and nothing here guesses.
            """
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
                info = _info(handle)
                if info.dwFileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                    raise _refuse(f"{described} is a reparse point, and a plain file is read only from a plain file")
                chunks: list[bytes] = []
                chunk = ctypes.create_string_buffer(1 << 16)
                read = wintypes.DWORD()
                while True:
                    if not _ReadFile(handle, chunk, len(chunk), ctypes.byref(read), None):
                        raise _refuse(f"{described} cannot be read (error {ctypes.get_last_error()})")
                    if read.value == 0:
                        break
                    chunks.append(chunk.raw[: read.value])
                identity = (info.dwVolumeSerialNumber, (info.nFileIndexHigh << 32) | info.nFileIndexLow)
                return BoundFile(b"".join(chunks), identity, None)
            finally:
                _CloseHandle(handle)

        def read_link(self, name: str) -> "BoundLink | None":
            """The symbolic link ``name``: Git's blob for it and its own identity, from ONE handle.

            The reparse data is read through the handle opened relative to this
            held directory (:func:`_reparse_point`) and turned into bytes only by
            Git for Windows' own rule (:func:`windows_link_target`): a junction or
            any other reparse point that Git does not record as a link is refused
            there, and nothing is ever followed.
            """
            _require_component(name)
            described = f"{self.described}\\{name}"
            found = _reparse_point(self.handle, name, described)
            if found is None:
                return None
            identity, raw = found
            return BoundLink(windows_link_target(raw, described), identity)

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

    def replace_file(self, name: str, data: bytes, tmp: "SafeDirectory") -> None:
        """Place ``data`` at ``name``, replacing what is there: only where a create could be contained."""
        require_immutable_create()
        self._backend.replace_file(name, data, tmp._backend)

    def identity(self) -> tuple:
        """Which directory object this handle holds, asked of the handle itself - never of a name.

        Comparable with :attr:`FinalObjectInfo.identity`: equal values are one
        object. Opaque and runtime-only, exactly like that identity.
        """
        return self._backend.identity()

    def read_file_bound(self, name: str) -> "BoundFile | None":
        """The plain file ``name`` - its bytes, identity and execute bit - read through one handle.

        One component, relative to this already-proven directory, opened
        without following anything: an indirection or anything that is not a
        plain file is refused exactly as :meth:`read_file` refuses it. ``None``
        when the name does not exist.
        """
        return self._backend.read_file_bound(name)

    def read_link(self, name: str) -> "BoundLink | None":
        """The final link ``name`` - the bytes Git stores for it, and its own identity - never followed.

        One component, relative to this already-proven directory. ``None`` when
        the name does not exist; anything that is not a link Git records as one
        is refused rather than read some other way. See :class:`BoundLink`.
        """
        return self._backend.read_link(name)

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


# --------------------------------------------------------------------------- the one compare-and-replace (P6 §30.18)

#: What :func:`compare_and_replace` found and did. ``replaced``: the target held exactly the expected prior state
#: and now holds the new bytes; ``matching``: it already held the new bytes, and nothing was written; ``mismatch``:
#: it held anything else, and nothing was written.
CAS_REPLACED = "replaced"
CAS_MATCHING = "matching"
CAS_MISMATCH = "mismatch"


def compare_and_replace(root: Path, parts: list[str], expected: bytes | None, data: bytes, tmp_parts: list[str]) -> str:
    """Replace the plain file at ``root`` / ``parts`` with ``data`` only while it holds exactly ``expected``.

    The narrow primitive the P6 Profile CAS effect applies (§30.18), held to the
    containment standard of the canonical Review create: refused before anything
    is opened or written where a create could not be contained
    (:func:`require_immutable_create`); the parent walked from ``root`` without
    following anything and held - pinned - until the bytes are placed; the
    current target read through that held parent with no-follow semantics, so
    an indirection at the target or anywhere above it is a mismatch, never
    followed; and the new bytes placed by one rename relative to the held
    parent. ``expected`` ``None`` means the target must be absent, and the
    placement is then exclusive: a name that appears in the meantime is never
    replaced.

    Returns :data:`CAS_REPLACED`, :data:`CAS_MATCHING` or :data:`CAS_MISMATCH`;
    nothing is written for the last two.

    RB6B-L8: compare, then rename. The window between the no-follow read and
    the rename is guarded by the Project operation lock every Workline writer
    holds, not by this primitive: a subject writing the Profile outside that
    lock inside the window is overwritten, never classified MISMATCH. Every
    later reader still proves the bytes (the PersistedProjectionAdapter, the
    lineage gate of a new Run and validation), so such a write never becomes
    policy silently.
    """
    require_immutable_create()
    name = parts[-1]
    _require_component(name)
    with walk(root, parts[:-1], create=True) as parent, walk(root, tmp_parts, create=True) as tmp:
        try:
            stored = parent.last.read_file(name)
        except ValidationError:
            return CAS_MISMATCH
        if stored is not None and stored == data:
            return CAS_MATCHING
        if expected is None:
            if stored is not None:
                return CAS_MISMATCH
            if parent.last.create_file_exclusive(name, data, tmp.last):
                return CAS_REPLACED
            try:
                raced = parent.last.read_file(name)
            except ValidationError:
                return CAS_MISMATCH
            return CAS_MATCHING if raced == data else CAS_MISMATCH
        if stored != expected:
            return CAS_MISMATCH
        parent.last.replace_file(name, data, tmp.last)
        return CAS_REPLACED


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

#: Every character Git refuses anywhere in a ref name, measured against
#: ``git check-ref-format`` on Git 2.54: the ASCII control range and DEL, a
#: space, and the six characters it reserves for revision syntax. Characters it
#: ACCEPTS are deliberately not listed - ``]``, ``{``, ``}``, ``%``, ``;``,
#: ``|``, ``<``, ``>``, quotes, ``&``, ``$``, ``#``, ``+``, ``=``, ``!``, ``(``,
#: ``,`` and ``@`` all appear in names Git takes, and refusing them would refuse
#: a submodule HEAD Git resolves.
_REFNAME_FORBIDDEN = frozenset(" ~^:?*[\\" + "".join(chr(code) for code in range(0x20)) + "\x7f")

#: The single character Git accepts between a packed record's id and its ref name.
#: Measured: exactly ONE of these. Two spaces, space+TAB, TAB+space and no
#: separator at all each make Git refuse the file, and TAB, vertical tab and form
#: feed each work exactly as a space does - which is why a space-only parser
#: silently loses a binding Git honours.
PACKED_SEPARATORS = " \t\v\f"

#: The only ``#`` line Git tolerates, and only as the FIRST line. The TRAILING
#: SPACE is part of the spelling, measured: ``# pack-refs with: `` with no traits
#: at all is accepted and so is ``# pack-refs with: unknown``, while
#: ``# pack-refs with:``, ``# pack-refs with:peeled`` and ``# pack-refs with:X``
#: are each refused before the ref resolves. So the trait vocabulary is NOT
#: validated - Git allows traits it does not know - but the prefix is exact.
#:
#: An arbitrary ``# comment`` makes Git refuse the whole file even at the top, so
#: ``#`` is not a comment introducer here; and a header anywhere but the first
#: line is a malformed file - in a submodule git directory ``git rev-parse HEAD``
#: refuses it outright, while in a plain repository ``rev-parse`` resolves the
#: target early and ``git show-ref`` refuses. ``rev-parse HEAD`` alone is
#: therefore not a stable oracle for whole-file validity, and this reader takes
#: the answer both commands agree on.
PACKED_HEADER = "# pack-refs with: "

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
    for character in refname:
        if character in _REFNAME_FORBIDDEN:
            raise _refuse(
                f"{described} names {refname!r}, which holds {character!r}; Git refuses that character in a "
                "ref name, so no ref of that name exists for this reader to report"
            )
    if not refname.startswith("refs/"):
        # MEASURED, and the one place this reader must be stricter than
        # `check-ref-format`: that command accepts `heads/mainx`, but a symbolic
        # HEAD naming it does NOT resolve - `git rev-parse HEAD` refuses. The
        # question here is only ever what HEAD names.
        raise _refuse(f"{described} names {refname!r}, which is not under 'refs/', so a symbolic HEAD cannot name it")
    if refname.endswith("."):
        raise _refuse(f"{described} names {refname!r}, which ends with '.'")
    if ".." in refname:
        raise _refuse(f"{described} names {refname!r}, which holds '..'")
    if "@{" in refname:
        raise _refuse(f"{described} names {refname!r}, which holds '@{{'")
    components = refname.split("/")
    if len(components) < 2:
        raise _refuse(f"{described} names {refname!r}, which is not a two-component ref name")
    for component in components:
        if component == "":
            raise _refuse(f"{described} names {refname!r}, which holds an empty component")
        if component.startswith("."):
            raise _refuse(f"{described} names {refname!r}, whose component {component!r} begins with '.'")
        if component.endswith(".lock"):
            raise _refuse(f"{described} names {refname!r}, whose component {component!r} ends with '.lock'")
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


def _packed_records(text: str, described: str) -> list[tuple[str, str]]:
    """Every ``(id token, ref name)`` the file declares, or a refusal for the WHOLE file.

    Git reads ``packed-refs`` as a whole: a line it cannot parse makes it refuse
    every ref in the file, not only the malformed one. Measured, and this is why
    "unrelated lines are never validated" could not stand - with a garbage line,
    an abbreviated id, an id with no ref, a ref with no id, an empty line, a
    stray ``#`` comment or a peeled line before any record, ``git rev-parse
    HEAD`` refuses outright while a target-only parser still produced an id.

    The grammar is deliberately the narrow shape Git's accepted cases share, and
    an id TOKEN is not validated as hexadecimal here: measured, Git resolves a
    ref from a file whose OTHER record holds forty non-hex characters or an
    upper-case id, so refusing those would refuse a state Git answers. The
    token of the ref actually being asked about is validated by the caller, as
    an identity rather than a shape.

    Known and deliberate: a 39- or 41-character unrelated token is refused here
    although Git resolves past it. Those are not object ids in any spelling, the
    reason Git tolerates them is not documented behaviour to reproduce, and
    guessing at it would be worse than failing closed.
    """
    if text and not text.endswith("\n"):
        # MEASURED: Git refuses a packed-refs file whose last line is not
        # LF-terminated, however lawful the record itself looks - with a bare
        # record, after a header, after another record and after a peeled line.
        # This is packed-refs only; a GITFILE with no final newline is lawful and
        # stays accepted.
        raise _refuse(f"{described} does not end with a newline, so its last record is unterminated")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]  # the final newline terminates the last record; it is not an empty line
    records: list[tuple[str, str]] = []
    after_record = False
    for number, line in enumerate(lines, start=1):
        where = f"{described} line {number}"
        # A carriage return is NOT stripped. Measured: Git reads `<id> refs/heads/main\r`
        # as a binding for the ref named `refs/heads/main\r`, which is a different ref -
        # so it resolves `refs/heads/main` from the LF record beside it, and refuses when
        # the CRLF record is the only one. Stripping it invented a binding Git does not
        # have. Left in place, the name simply does not match what was asked for.
        if line.startswith("#"):
            if number != 1 or not line.startswith(PACKED_HEADER):
                raise _refuse(
                    f"{where} is {line!r}; the only '#' line Git accepts is its own {PACKED_HEADER!r} header, "
                    "and only as the first line"
                )
            continue
        if line.startswith("^"):
            if not after_record:
                raise _refuse(f"{where} is a peeled line with no record before it")
            after_record = False
            continue
        if not line:
            raise _refuse(f"{where} is empty; Git refuses the whole file for an empty line")
        cut = min((line.find(character) for character in PACKED_SEPARATORS if character in line), default=-1)
        if cut <= 0:
            raise _refuse(f"{where} is {line!r}, which is not an id followed by a ref name")
        token, name = line[:cut], line[cut + 1:]
        if len(token) not in (40, 64):
            raise _refuse(
                f"{where} names the id {token!r}, which is {len(token)} characters; a packed record's id is 40 or 64"
            )
        if not name or name[0] in PACKED_SEPARATORS:
            raise _refuse(f"{where} is {line!r}, whose ref name is empty or begins with a separator")
        records.append((token, name))
        after_record = True
    return records


def _packed_ref(gitdir: SafeDirectory, refname: str) -> str:
    """The OID ``packed-refs`` binds to ``refname``, by exact name, or a refusal.

    Narrow about IDENTITY, total about SHAPE. An unrelated line is never allowed
    to answer for the ref that was asked about, and an unrelated record's id is
    never checked for being hexadecimal - Git resolves the target past forty
    non-hex characters and past an upper-case id. But the FILE's shape is
    validated as a whole by :func:`_packed_records`, because Git reads it as a
    whole: one line it cannot parse and it refuses every ref in the file. An
    earlier draft of this reader said unrelated malformed lines are never
    validated at all; that was measured wrong and is withdrawn.

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
    bindings = [
        _require_oid(token, f"the packed-refs record for {refname}")
        for token, name in _packed_records(text, f"{gitdir.described}/packed-refs")
        if name == refname
    ]
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
