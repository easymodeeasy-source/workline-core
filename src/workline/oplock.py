"""Project execution lock (``rules/git``: Project execution lock).

One active writer per established Workline Project. A top-level
state-changing operation takes the lock at its entry, before it reads any
Project state that decides a write, and holds it through mutation open /
resume, effects, validation, commit and push until it returns. A START that
returns a question wait lets go as well: its mutation stays pending, and the
invocation that later resumes it takes the lock afresh.

Before the lock the operation passes the Project context check
(:mod:`workline.context`): it must have been started from inside the very
Project it changes. A foreign caller STOPs as ``foreign_project_mutation``
before the lock directory or file exists, so it creates nothing in the target.

The lock is an OS-managed, non-blocking, exclusive lock on
``.workline/runtime/locks/project.lock`` (``msvcrt.locking`` on Windows,
``fcntl.flock`` elsewhere). Holding it is the only proof of ownership. The OS
releases it when the holding process ends, so there is no lease, no TTL, no
forced unlock and no stale-lock cleanup: after a crash the next operation
takes the lock and follows the ordinary pending-mutation recovery.
``holder.json`` beside the lock only describes the holder for a busy report;
nothing reads it to decide ownership.

A pending mutation and this lock are different things. The pending mutation
is durable recovery state; the lock says only that a process is executing on
the Project right now. Contention is therefore ``project_operation_busy``,
never ``reconcile required``, and the busy side writes nothing.

Only top-level operations take the lock. Phase CREATE / CREATE registration
cores join the operation that already holds it; starting another top-level
operation on the same Project from inside a running one is
``project_operation_nested``. Initial Project開始 runs before a Project is
established and is outside this lock.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import socket
import threading
from typing import Any, Iterator

from .context import authorize_project_mutation
from .durable import durable_write_text
from .errors import ProjectOperationBusy, ProjectOperationNested, StopError
from .store import PROJECT_YAML_REL, ProjectStore

HOLDER_MARKER = "workline-operation-holder"
HOLDER_VERSION = 1

if os.name == "nt":
    import msvcrt

    # A byte range locked through another handle is reported as EACCES; the
    # deadlock codes belong to the retrying modes, which are never used here.
    _CONTENDED = {errno.EACCES, errno.EDEADLK, getattr(errno, "EDEADLOCK", errno.EDEADLK)}

    def _try_lock(fd: int) -> bool:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in _CONTENDED:
                return False
            raise
        return True

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

    def _names_locked_file(fd: int, path: Path) -> bool:
        # A file open here cannot be deleted or renamed on Windows, so the path
        # still names the file this descriptor locked.
        return True

else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)

    def _names_locked_file(fd: int, path: Path) -> bool:
        # flock follows the open file, not the name: had the lock file been
        # unlinked and recreated meanwhile, another process could lock a
        # different file under the same path.
        try:
            return os.path.samestat(os.fstat(fd), os.stat(path))
        except OSError:
            return False


@dataclass
class ProjectLock:
    """The execution lock this process holds on one Project."""

    store: ProjectStore
    operation: str
    details: dict[str, Any]
    acquired_at: str
    context_root: Path  # the Project the operation was started from: always this lock's Project
    fd: int = field(repr=False)
    mutation_id: str | None = None


_held: dict[str, ProjectLock] = {}
_held_guard = threading.Lock()


def _key(store: ProjectStore) -> str:
    return os.path.normcase(str(store.lock_file))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def held_lock(store: ProjectStore) -> ProjectLock | None:
    """The execution lock this process currently holds on ``store``'s Project."""
    with _held_guard:
        return _held.get(_key(store))


def read_holder(store: ProjectStore) -> dict[str, Any] | None:
    """The holder description last recorded beside the lock.

    Diagnostic only: it may be stale (a crashed holder leaves it behind) and it
    is never read to decide who owns the lock.
    """
    try:
        data = json.loads(store.lock_holder.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("workline") != HOLDER_MARKER:
        return None
    return data


def note_mutation(store: ProjectStore, mutation_id: str) -> None:
    """Add the opened mutation to the holder description (diagnostic only)."""
    lock = held_lock(store)
    if lock is None or lock.mutation_id == mutation_id:
        return
    lock.mutation_id = mutation_id
    _write_holder(lock)


def _write_holder(lock: ProjectLock) -> None:
    record = {
        "workline": HOLDER_MARKER,
        "version": HOLDER_VERSION,
        "operation": lock.operation,
        "details": lock.details,
        "mutation_id": lock.mutation_id,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "acquired_at": lock.acquired_at,
    }
    try:
        durable_write_text(
            lock.store.lock_holder,
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            tmp_dir=lock.store.tmp,
        )
    except OSError:
        pass  # a description that cannot be written never fails the operation


def _clear_holder(store: ProjectStore) -> None:
    try:
        store.lock_holder.unlink()
    except OSError:
        pass


def _busy_message(store: ProjectStore, holder: dict[str, Any] | None) -> str:
    message = f"another process is running a Workline operation on this Project ({store.root})"
    if holder is not None:
        described = (
            f"{holder.get('operation')} (pid {holder.get('pid')} on {holder.get('host')}, "
            f"since {holder.get('acquired_at')}"
        )
        if holder.get("mutation_id"):
            described += f", mutation {holder['mutation_id']}"
        message += f"; recorded holder: {described})"
    return message + "; nothing was written, run the operation again once it has finished"


@contextmanager
def project_operation(
    store: ProjectStore, operation: str, details: dict[str, Any] | None = None
) -> Iterator[ProjectLock]:
    """Hold the Project execution lock for one top-level operation, or STOP.

    Every established-Project mutation entry comes through here, so this is
    where its Project context is decided: once, from the working directory at
    this moment. An operation started anywhere but inside this Project STOPs
    as ``foreign_project_mutation`` before the lock area exists.

    The lock is taken without waiting. When another process holds it, the
    operation STOPs as ``project_operation_busy`` having written nothing; when
    this process already runs an operation on the Project, it STOPs as
    ``project_operation_nested``. The lock is released however the block
    exits: completion, a question wait, a STOP or an unexpected error.

    Only an established Project (one with ``.workline/project.yaml``) has an
    execution lock, and nothing is created in a folder that is not one.
    """
    if not store.project_yaml.is_file():
        raise StopError(
            f"not an established Workline Project ({PROJECT_YAML_REL} is missing): {store.root}",
            code="not_a_project",
        )
    context = authorize_project_mutation(store.root)
    key = _key(store)
    with _held_guard:
        running = _held.get(key)
    if running is not None:
        raise ProjectOperationNested(
            f"this process is already running {running.operation} on this Project; a top-level Workline "
            "operation cannot start inside another one (child registration joins the running operation instead)"
        )
    try:
        store.locks.mkdir(parents=True, exist_ok=True)
        fd = os.open(store.lock_file, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
    except OSError as exc:
        raise StopError(
            f"cannot open the Project execution lock {store.lock_file}: {exc}", code="project_lock_unavailable"
        ) from exc
    try:
        locked = _try_lock(fd)
    except OSError as exc:
        os.close(fd)
        raise StopError(
            f"cannot take the Project execution lock {store.lock_file}: {exc}", code="project_lock_unavailable"
        ) from exc
    if not locked:
        os.close(fd)
        holder = read_holder(store)
        raise ProjectOperationBusy(_busy_message(store, holder), holder)
    if not _names_locked_file(fd, store.lock_file):
        os.close(fd)
        raise StopError(
            f"the Project execution lock {store.lock_file} was replaced while it was being taken; STOP",
            code="project_lock_unavailable",
        )

    lock = ProjectLock(store, operation, dict(details or {}), _utc_now(), context.root, fd)
    with _held_guard:
        _held[key] = lock
    _write_holder(lock)
    try:
        yield lock
    finally:
        with _held_guard:
            _held.pop(key, None)
        # The description goes first, while the lock is still held, so it can
        # never erase the description the next holder writes.
        _clear_holder(store)
        try:
            _unlock(fd)
        except OSError:
            pass
        os.close(fd)


__all__ = ["ProjectLock", "held_lock", "note_mutation", "project_operation", "read_holder"]
