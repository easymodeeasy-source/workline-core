"""Durable local file writes.

A write counts as durable only after the bytes reach the file, the file is
flushed and fsynced, and the temporary file is atomically moved into place
(``os.replace``). On POSIX the parent directory is fsynced as well; Windows
cannot open directories for fsync, so ``os.replace`` (MoveFileEx with
replace) is the durability boundary there.

Temporary files live in ``tmp_dir`` (a Workline runtime area) so that an
interrupted write never leaves stray files inside canonical directories.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path


class DurableWriteError(OSError):
    """A durable write could not be completed."""


def _fsync_dir(directory: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable_write_text(path: Path, content: str, *, tmp_dir: Path | None = None) -> None:
    """Write ``content`` to ``path`` durably and atomically.

    ``tmp_dir`` must be on the same volume as ``path``; it defaults to the
    parent directory of ``path``.
    """
    path = Path(path)
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    if tmp_dir is None:
        tmp_dir = directory
    else:
        tmp_dir = Path(tmp_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_dir(directory)
    except OSError as exc:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise DurableWriteError(f"durable write failed for {path}: {exc}") from exc


def read_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")
