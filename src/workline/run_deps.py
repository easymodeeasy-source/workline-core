"""Versioned, read-only dependency trees shared by parallel Work runs.

A tree (for YGO: the patched OCGCore + Lua sources a Solver commit builds
against) is identified by its *identity* - the facts that decide its bytes,
e.g. the OCGCore and Lua commits, the fetch script's content hash, the patch
files' content hash and the build configuration. The key is the SHA-256 of
that identity as canonical JSON, so two Solver commits that differ in any of
them never share a tree, and two that agree do.

Each entry is ``<store>/<key>/``: ``tree/`` (made read-only), ``ENTRY.json``
(identity, manifest, origin) and ``users/<run_id>`` markers. A tree is adopted
only when its recursive manifest equals the manifest the caller expects, is
never rewritten, and is not removed while any run uses it. Nothing here
fetches or builds: making a tree is the caller's (e.g. the Solver's own fetch
script in a scratch folder), adopting it is this module's.

Adopt, acquire, release and remove of one key each run under that key's own OS
lock (``<store>/<key>.lock``), so a use being registered and a removal never
interleave: a removal either finishes before the use is checked (the use then
finds no entry) or sees the use and refuses.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import time
from typing import Any, Iterator

from .errors import StopError
from .ids import new_ulid
from .oplock import release_exclusive_lock, try_exclusive_lock

ENTRY = "ENTRY.json"
#: how long one adopt / acquire / release / remove waits for another one of the same key (each try non-blocking)
LOCK_SECONDS = 120.0


def key_of(identity: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def manifest(tree: Path, exclude: tuple[str, ...] = ()) -> tuple[str, int]:
    """SHA-256 over every file's relative path and content hash, recursively; and the file count."""
    tree = Path(tree)
    files = {p.relative_to(tree).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in tree.rglob("*") if p.is_file() and p.name not in exclude}
    return hashlib.sha256("".join(f"{k}\0{files[k]}\n" for k in sorted(files)).encode()).hexdigest(), len(files)


def _entry(store_dir: Path, identity: dict[str, Any]) -> Path:
    return Path(store_dir) / key_of(identity)


@contextmanager
def _locked(store_dir: Path, key: str) -> Iterator[None]:
    """The key's own OS lock (beside the entry, never inside it, so a removal does not take it away)."""
    store_dir = Path(store_dir)
    store_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(store_dir / f"{key}.lock", os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
    try:
        deadline = time.monotonic() + LOCK_SECONDS
        while not try_exclusive_lock(fd):
            if time.monotonic() >= deadline:
                raise StopError(f"deps entry {key[:12]} stayed locked for {LOCK_SECONDS:.0f} s", code="deps_busy")
            time.sleep(0.05)
        try:
            yield
        finally:
            release_exclusive_lock(fd)
    finally:
        os.close(fd)


def _read_only(tree: Path) -> None:
    for p in tree.rglob("*"):
        if p.is_file():
            os.chmod(p, stat.S_IREAD)


def adopt(store_dir: Path, identity: dict[str, Any], source: Path, expected_manifest: str,
          exclude: tuple[str, ...] = ()) -> Path:
    """Register ``source`` (copied) as the tree of ``identity``; returns the tree path. Idempotent.

    STOPs when the source's manifest is not ``expected_manifest``, or when an
    entry for the key already holds a different tree.
    """
    with _locked(store_dir, key_of(identity)):
        return _adopt(store_dir, identity, source, expected_manifest, exclude)


def _adopt(store_dir: Path, identity: dict[str, Any], source: Path, expected_manifest: str,
           exclude: tuple[str, ...]) -> Path:
    entry = _entry(store_dir, identity)
    tree = entry / "tree"
    if (entry / ENTRY).is_file():
        held = json.loads((entry / ENTRY).read_text(encoding="utf-8"))
        if held.get("manifest") != expected_manifest or manifest(tree, exclude)[0] != expected_manifest:
            raise StopError(f"deps entry {entry.name} holds another tree than {expected_manifest[:12]}",
                            code="deps_entry_mismatch")
        return tree
    found, count = manifest(source, exclude)
    if found != expected_manifest:
        raise StopError(f"deps source {source} has manifest {found[:12]}, not the expected {expected_manifest[:12]}",
                        code="deps_manifest_mismatch")
    staging = entry.with_name(entry.name + ".staging")
    if staging.exists():
        shutil.rmtree(staging, onerror=_writable_retry)
    shutil.copytree(source, staging / "tree")
    if manifest(staging / "tree", exclude)[0] != expected_manifest:
        raise StopError("deps copy does not hold the source's manifest", code="deps_copy_mismatch")
    _read_only(staging / "tree")
    (staging / "users").mkdir()
    (staging / ENTRY).write_text(json.dumps({"identity": identity, "key": entry.name, "manifest": found,
                                             "files": count, "adopted_from": str(source),
                                             "exclude": list(exclude)}, indent=2,
                                            sort_keys=True), encoding="utf-8")
    os.replace(staging, entry)
    return tree


def acquire(store_dir: Path, identity: dict[str, Any], run_id: str, exclude: tuple[str, ...] = ()) -> Path:
    """The read-only tree of ``identity`` for ``run_id``, its use recorded; STOPs when there is none or it changed.

    The check and the use's record are one step under the key's lock: a removal cannot come between them.
    """
    with _locked(store_dir, key_of(identity)):
        entry = _entry(store_dir, identity)
        if not (entry / ENTRY).is_file():
            raise StopError(f"no deps entry for identity {key_of(identity)[:12]}; make and adopt it first",
                            code="deps_missing")
        held = json.loads((entry / ENTRY).read_text(encoding="utf-8"))
        exclude = tuple(held.get("exclude", exclude))
        if manifest(entry / "tree", exclude)[0] != held["manifest"]:
            raise StopError(f"deps entry {entry.name} no longer holds its manifest", code="deps_entry_mismatch")
        (entry / "users").mkdir(exist_ok=True)
        (entry / "users" / run_id).write_text(str(os.getpid()), encoding="utf-8")
        return entry / "tree"


def release_user(store_dir: Path, key: str, run_id: str) -> None:
    with _locked(store_dir, key):
        marker = Path(store_dir) / key / "users" / run_id
        if marker.exists():
            marker.unlink()


def users(store_dir: Path, key: str) -> list[str]:
    folder = Path(store_dir) / key / "users"
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def remove(store_dir: Path, key: str) -> None:
    """Delete an entry; refused while any run uses it.

    Under the key's lock the entry is first moved aside (one rename), so no adopt or acquire ever sees it half
    deleted; a deletion that cannot finish leaves only the moved-aside folder.
    """
    with _locked(store_dir, key):
        held = users(store_dir, key)
        if held:
            raise StopError(f"deps entry {key[:12]} is used by {', '.join(held)}; not removed", code="deps_in_use")
        entry = Path(store_dir) / key
        if not entry.exists():
            return
        gone = entry.with_name(f"{key}.removing-{new_ulid()}")
        os.replace(entry, gone)
        shutil.rmtree(gone, onerror=_writable_retry)


def _writable_retry(function, path, _exc_info):
    os.chmod(path, stat.S_IWRITE)
    function(path)


__all__ = ["acquire", "adopt", "key_of", "manifest", "release_user", "remove", "users"]
