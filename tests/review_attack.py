"""An attacker for Review containment tests: turn an existing empty directory into a junction in place.

Not a test module. It exists so a test can reproduce the one Windows race a
share-mode pin does not stop - another actor setting a mount-point reparse
point on an empty directory Workline already holds open - and show that the
handle-relative create is refused by the kernel instead of following it.
"""

from __future__ import annotations

import sys
from pathlib import Path

_IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
_FSCTL_SET_REPARSE_POINT = 0x000900A4


def set_mount_point(directory: Path, target: Path) -> str:
    """Convert ``directory`` (empty, existing) into a junction to ``target``; ``"converted"`` on success."""
    if sys.platform != "win32":
        raise RuntimeError("mount-point reparse points are a Windows mechanism")
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.DeviceIoControl.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
    ]
    generic_write, share_all, open_existing = 0x40000000, 0x7, 3
    backup_semantics, open_reparse_point = 0x02000000, 0x00200000
    handle = kernel32.CreateFileW(
        str(directory), generic_write, share_all, None, open_existing, backup_semantics | open_reparse_point, None
    )
    if handle in (None, 0, wintypes.HANDLE(-1).value):
        return f"open refused: error {ctypes.get_last_error()}"
    substitute = ("\\??\\" + str(target)).encode("utf-16-le")
    printed = str(target).encode("utf-16-le")
    path_buffer = substitute + b"\0\0" + printed + b"\0\0"
    header = (
        _IO_REPARSE_TAG_MOUNT_POINT.to_bytes(4, "little")
        + (8 + len(path_buffer)).to_bytes(2, "little")
        + (0).to_bytes(2, "little")
    )
    offsets = (
        (0).to_bytes(2, "little")
        + len(substitute).to_bytes(2, "little")
        + (len(substitute) + 2).to_bytes(2, "little")
        + len(printed).to_bytes(2, "little")
    )
    raw = header + offsets + path_buffer
    buffer = ctypes.create_string_buffer(raw, len(raw))
    returned = wintypes.DWORD()
    ok = kernel32.DeviceIoControl(
        handle, _FSCTL_SET_REPARSE_POINT, buffer, len(raw), None, 0, ctypes.byref(returned), None
    )
    error = ctypes.get_last_error()
    kernel32.CloseHandle(handle)
    return "converted" if ok else f"conversion refused: error {error}"
