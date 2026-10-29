"""Parallel Work execution: START split into a short claim, an unlocked run, and a short finish.

The ordinary START holds the Project execution lock and one pending mutation
whose write scope names the shared ledgers for as long as its executor runs,
so a second Work cannot begin until the first one has finished or been
reconciled. A parallel START (``start(..., parallel=True)``) keeps every
canonical write exactly where it was - under the lock, through the ordinary
START mutation - and moves only the executor out of it:

1. claim (locked, short): the ordinary START of the Work records its
   lifecycle (``work_started`` / ``work_target_added``) and commits it; the
   mutation completes, so no pending record holds the ledgers afterwards.
   Workline then creates the Work's own workspace (a git worktree on a Work
   branch, by default) and records the run.
2. run (unlocked): the executor works in the workspace. Other Works can be
   claimed, run and finished meanwhile. A question wait ends here with no lock
   and no pending mutation; the next parallel START of the same Work resumes
   the same workspace.
3. finish (locked, short): the result is checked against what the Project
   changed since the run's base commit (a path both changed differently is a
   conflict and the run is parked, nothing written), copied into the Project,
   and completed by the ordinary START completion - its commit, push and
   lifecycle events.
4. release: the workspace is checked (uncommitted, untracked, ignored files,
   unintegrated commits) and removed only when nothing would be lost; a run
   whose cleanup cannot finish says so and can be resumed. It never stops
   another Work.

The run record (``.workline/runtime/runs/<work_id>.json``) is runtime state,
not canonical: the Work's canonical state stays in the Project's one event log.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import sys
import threading
import time
from typing import Any, Callable, Iterator

from . import gitcmd
from .durable import durable_write_text
from .errors import ProjectOperationBusy, StopError, ValidationError
from .ids import new_ulid
from .oplock import project_operation, release_exclusive_lock, try_exclusive_lock
from .store import ProjectStore

RUN_MARKER = "workline-parallel-run"
RUN_VERSION = 1
RUNS_DIR = ".workline/runtime/runs"
#: which Workline mutation made which Project commit, noted while a parallel run holds a Work (:func:`note_commit`)
JOURNAL_DIR = ".workline/runtime/commit-journal"
SAVED_REF_PREFIX = "refs/workline/runs/"
PARKED_REF_PREFIX = "refs/workline/parked/"
BRANCH_PREFIX = "workline/run/"

#: The one wait a parallel START adds: each of its short locked sections (claim, finish) retries the
#: Project execution lock - every try non-blocking, a refused try writing nothing - for at most this long,
#: then STOPs ``project_operation_busy`` like every other operation. Nothing else waits for the lock.
LOCK_RETRY_SECONDS = 120.0
#: A run record is read and written under its own small OS lock (compare-and-write); never held long.
RECORD_LOCK_SECONDS = 10.0
#: What a parking release keeps of a held / cancelled / stopped run: tracked changes, and untracked files of
#: the run's own worktree up to these sizes. Anything larger is listed and the release stops (nothing deleted).
WIP_FILE_LIMIT = 10 * 1024 * 1024
WIP_TOTAL_LIMIT = 50 * 1024 * 1024

# run states ---------------------------------------------------------------
CLAIMING = "claiming"          # recorded before the claim is made: a claim interrupted at any point is found
CREATING = "creating"          # claim committed, workspace being made
RUNNING = "running"            # executor running (owner pid)
QUESTION_WAIT = "question_wait"
RETURNED = "returned"          # the executor returned; what it returned is recorded, its result not yet committed
EXECUTED = "executed"          # Completed recorded, finish not yet done
FAILED = "failed"              # executor raised; workspace kept
INTERRUPTED = "interrupted"    # the owner died while the executor ran: not run again until acknowledged
OUTCOME_UNKNOWN = "outcome_unknown"  # the executor returned but what it left cannot be proven: a Human decides
CONFLICT = "conflict"          # parked: the result conflicts with the Project
PARKED = "parked"              # result kept on a saved ref for a later integration
RELEASING = "releasing"        # integrated; workspace being released
CLEANUP_FAILED = "cleanup_failed"
RELEASED = "released"

#: states in which the run owns its Work: no other START of that Work may run it
_HOLDING = {CLAIMING, CREATING, RUNNING, QUESTION_WAIT, RETURNED, EXECUTED, FAILED, INTERRUPTED, OUTCOME_UNKNOWN,
            CONFLICT}
#: states a live owner process is working in: a second START of the Work is refused while it lives
_LIVE = {CLAIMING, CREATING, RUNNING, RETURNED, EXECUTED}

# owner liveness -------------------------------------------------------------
ALIVE, DEAD, UNKNOWN = "alive", "dead", "unknown"

#: (Project, Work) -> (run_id, thread) of the claim / finish being made by that thread
_tokens: dict[tuple[str, str], tuple[str, int]] = {}
#: (Project, Work) -> the one invocation of this process that holds it: {"nonce", "thread"}
_active: dict[tuple[str, str], dict[str, Any]] = {}
_guard = threading.Lock()
_owner_cache: dict[str, Any] = {}


def _key(store: ProjectStore, work_id: str) -> tuple[str, str]:
    return (os.path.normcase(str(store.root.resolve())), work_id)


@contextmanager
def _token(store: ProjectStore, work_id: str, run_id: str) -> Iterator[None]:
    key = _key(store, work_id)
    with _guard:
        _tokens[key] = (run_id, threading.get_ident())
    try:
        yield
    finally:
        with _guard:
            _tokens.pop(key, None)


def _token_here(store: ProjectStore, work_id: str) -> str | None:
    """The run whose claim / finish this thread is making for ``work_id``; None in every other thread."""
    with _guard:
        held = _tokens.get(_key(store, work_id))
    return held[0] if held is not None and held[1] == threading.get_ident() else None


@contextmanager
def _invocation(store: ProjectStore, work_id: str, *, join: bool = False) -> Iterator[str]:
    """One parallel START (or release) of ``work_id`` by this process: the identity its run record is owned by.

    The owner is the invocation, not the process: two threads, or a run entered again from inside its own executor,
    are two invocations, and a second one of a Work while the first lasts is refused here, before anything is read
    or written. ``join``: a release the holding invocation makes itself (same thread) continues under it. When the
    invocation ends, its record says so (``owner.ended_at``), so the next START - of this process or another - does
    not wait for the process to exit.
    """
    key = _key(store, work_id)
    thread = threading.get_ident()
    with _guard:
        held = _active.get(key)
        joined = held is not None and join and held["thread"] == thread
        if held is not None and not joined:
            where = ("entered again from inside its own run (the same thread)" if held["thread"] == thread
                     else "being run by another thread of this process")
            raise StopError(f"Work {work_id} is already {where} (invocation {held['nonce']}); nothing was begun",
                            code="work_run_active")
        if held is None:
            held = {"nonce": new_ulid(), "thread": thread}
            _active[key] = held
    try:
        yield held["nonce"]
    finally:
        if not joined:
            try:
                _end_turn(store, work_id, held["nonce"])
            finally:
                with _guard:
                    _active.pop(key, None)


def _current(store: ProjectStore, work_id: str) -> str | None:
    """The invocation this thread is running for ``work_id``, if any."""
    with _guard:
        held = _active.get(_key(store, work_id))
    return held["nonce"] if held is not None and held["thread"] == threading.get_ident() else None


def _invocation_live(nonce: object) -> bool:
    with _guard:
        return bool(nonce) and any(held["nonce"] == nonce for held in _active.values())


def _end_turn(store: ProjectStore, work_id: str, nonce: str) -> None:
    """The invocation ``nonce`` has ended: its record (still its own) says so. Never raised past the caller's own
    outcome - a record that cannot say it keeps its owner, who then counts as alive while its process lives."""
    if not run_path(store, work_id).is_file():
        return  # nothing was written for it: nothing to say
    try:
        with _record_lock(store, work_id):
            on_disk = read_run(store, work_id)
            owner = (on_disk or {}).get("owner") or {}
            if on_disk is not None and owner.get("nonce") == nonce and not owner.get("ended_at"):
                owner["ended_at"] = _now()
                _write(store, on_disk)
    except (StopError, OSError):
        pass


# --------------------------------------------------------------------------- run records

def _runs_dir(store: ProjectStore) -> Path:
    return store.root / RUNS_DIR


def run_path(store: ProjectStore, work_id: str) -> Path:
    return _runs_dir(store) / f"{work_id}.json"


def read_run(store: ProjectStore, work_id: str) -> dict[str, Any] | None:
    path = run_path(store, work_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StopError(f"run record {path.name} is unreadable: {exc}", code="run_record_unreadable") from exc
    if not isinstance(data, dict) or data.get("workline") != RUN_MARKER or data.get("work_id") != work_id:
        raise StopError(f"run record {path.name} is not a Workline run record for {work_id}", code="run_record_unreadable")
    return data


def list_runs(store: ProjectStore) -> list[dict[str, Any]]:
    folder = _runs_dir(store)
    if not folder.is_dir():
        return []
    return [r for p in sorted(folder.glob("*.json")) if (r := read_run(store, p.stem)) is not None]


@contextmanager
def _record_lock(store: ProjectStore, work_id: str) -> Iterator[None]:
    """The run record's own OS lock: a read-compare-write of the record is one step for every process."""
    folder = _runs_dir(store)
    folder.mkdir(parents=True, exist_ok=True)
    fd = os.open(folder / f"{work_id}.lock", os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
    try:
        deadline = time.monotonic() + RECORD_LOCK_SECONDS
        while not try_exclusive_lock(fd):
            if time.monotonic() >= deadline:
                raise StopError(f"the run record of {work_id} stayed locked for {RECORD_LOCK_SECONDS:.0f} s",
                                code="run_record_busy")
            time.sleep(0.02)
        try:
            yield
        finally:
            release_exclusive_lock(fd)
    finally:
        os.close(fd)


def _write(store: ProjectStore, record: dict[str, Any]) -> None:
    record["updated_at"] = _now()
    store.tmp.mkdir(parents=True, exist_ok=True)
    durable_write_text(run_path(store, record["work_id"]),
                       json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", tmp_dir=store.tmp)


def _save(store: ProjectStore, record: dict[str, Any], *, take: bool = False) -> None:
    """Write ``record`` - only while it is still this run's and this owner's (compare-and-write).

    A record another process has since taken over (a new run, or the same run under a new owner) is never
    overwritten: the write STOPs ``run_owner_changed``. ``take`` is the takeover itself, made only where the
    caller has established that the previous owner is gone (under the Project execution lock, or by
    :func:`release` / :func:`acknowledge_interrupted`, which check it first).
    """
    with _record_lock(store, record["work_id"]):
        if not take:
            on_disk = read_run(store, record["work_id"])
            if on_disk is not None and (on_disk.get("run_id") != record.get("run_id")
                                        or (on_disk.get("owner") or {}).get("nonce")
                                        != (record.get("owner") or {}).get("nonce")):
                raise StopError(f"run {record.get('run_id')} of {record['work_id']} is no longer owned by this process "
                                f"(now {on_disk.get('run_id')}, owner {(on_disk.get('owner') or {}).get('pid')}); "
                                "nothing was written", code="run_owner_changed")
        _write(store, record)


def _set(store: ProjectStore, record: dict[str, Any], state: str, *, take: bool = False, **fields: Any) -> None:
    record["state"] = state
    record.update(fields)
    record.setdefault("history", []).append({"state": state, "at": _now(), "pid": os.getpid()})
    _save(store, record, take=take)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _process_started(pid: int) -> str | None:
    """When process ``pid`` was created, as an opaque token (Windows creation time, Linux start ticks); None when
    it cannot be read. Two processes that reuse one pid never share it."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return None
            try:
                times = [wintypes.FILETIME() for _ in range(4)]
                if not kernel32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                    return None
                return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
            finally:
                kernel32.CloseHandle(handle)
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii", errors="replace")
        return stat.rsplit(")", 1)[1].split()[19]  # field 22: starttime
    except (OSError, IndexError, AttributeError, ValueError):
        return None


def pid_state(pid: object, started: str | None = None) -> str:
    """Whether process ``pid`` runs on this host: ``alive``, ``dead`` or ``unknown``; never signals it.

    Only an answer the operating system gives is ``dead``: no such process, or a process that has exited, or
    one created at another time than ``started`` (the pid was reused). A refused or failed query is
    ``unknown``, and an unknown owner is never taken for gone.
    """
    if not isinstance(pid, int) or pid <= 0:
        return DEAD
    if pid == os.getpid():
        alive = True
    elif sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            # ERROR_INVALID_PARAMETER: no process has this id. Anything else (access denied, ...) proves nothing.
            return DEAD if ctypes.get_last_error() == 87 else UNKNOWN
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return UNKNOWN
            alive = code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
            alive = True
        except ProcessLookupError:
            alive = False
        except PermissionError:
            alive = True
        except OSError:
            return UNKNOWN
    if not alive:
        return DEAD
    if started is not None:
        now = _process_started(pid)
        if now is not None and now != started:
            return DEAD  # the pid now names another process: the owner is gone
    return ALIVE


def pid_alive(pid: object) -> bool:
    """Whether process ``pid`` is known to run on this host (``unknown`` is not alive here; see :func:`pid_state`)."""
    return pid_state(pid) == ALIVE


def _me() -> dict[str, Any]:
    """This process: pid, host, creation time and a nonce of its own (an owner adds its invocation's nonce)."""
    if _owner_cache.get("pid") != os.getpid():
        _owner_cache.clear()
        _owner_cache.update(pid=os.getpid(), host=socket.gethostname(), started=_process_started(os.getpid()),
                            process=new_ulid())
    return dict(_owner_cache)


def owner_state(record: dict[str, Any]) -> str:
    """The run's owner: ``alive``, ``dead`` or ``unknown``. Another host's owner cannot be checked from here.

    The owner is one invocation (:func:`_invocation`). One that recorded its own end is gone; one of this process is
    alive exactly while that invocation lasts (another thread's, or this thread's); one of another process on this
    host is as alive as that process.
    """
    owner = record.get("owner") or {"pid": record.get("pid"), "host": record.get("host")}
    if owner.get("ended_at"):
        return DEAD  # the invocation itself recorded that it ended
    if owner.get("process") and owner["process"] == _me()["process"]:
        return ALIVE if _invocation_live(owner.get("nonce")) else DEAD
    if record.get("owner_cleared", {}).get("nonce") == owner.get("nonce") and owner.get("nonce"):
        return DEAD  # a Human confirmed this owner is gone (declare_owner_gone)
    if owner.get("host") != socket.gethostname():
        return UNKNOWN
    return pid_state(owner.get("pid"), owner.get("started"))


def _owned_by_me(store: ProjectStore, record: dict[str, Any]) -> bool:
    """Whether ``record`` is owned by the invocation this thread is running for its Work - not merely this process."""
    nonce = _current(store, record.get("work_id", ""))
    owner = record.get("owner") or {}
    return bool(nonce) and owner.get("nonce") == nonce and not owner.get("ended_at")


def _become_owner(store: ProjectStore, record: dict[str, Any]) -> None:
    nonce = _current(store, record["work_id"])
    if nonce is None:
        raise StopError(f"no invocation of this thread runs {record['work_id']}; the run is not taken",
                        code="run_owner_changed")
    me = _me()
    record["owner"] = {**me, "nonce": nonce}
    record["pid"], record["host"] = me["pid"], me["host"]


def require_run_free(store: ProjectStore, work_id: str) -> None:
    """STOP unless no parallel run owns ``work_id`` - or this call is that run's own claim or finish.

    START asks this before it runs any Work, so neither an ordinary START, an
    outer continuation nor a second parallel START runs a Work another run
    holds (a double start). The claim / finish is recognized by its thread, so
    another thread of the same process is never taken for it.
    """
    record = read_run(store, work_id)
    if record is None or record.get("state") not in _HOLDING:
        return
    if _token_here(store, work_id) == record.get("run_id"):
        return
    waiting = f"; it waits for a Human: {record.get('question')}" if record.get("state") == QUESTION_WAIT else ""
    raise StopError(
        f"Work {work_id} is held by parallel run {record.get('run_id')} ({record.get('state')}, pid "
        f"{record.get('pid')}){waiting}; it is continued only by a parallel START of the same Work, nothing was begun",
        code="work_run_active",
    )


def detach_allowed(store: ProjectStore, work_id: str) -> bool:
    """Whether ``start.Detach`` may end this START: only inside the claim or finish of the parallel run that owns
    ``work_id``, made by its owner. Anywhere else a returned Detach is an unknown outcome."""
    run_id = _token_here(store, work_id)
    if run_id is None:
        return False
    record = read_run(store, work_id)
    return (record is not None and record.get("run_id") == run_id and _owned_by_me(store, record)
            and record.get("state") in (CLAIMING, RUNNING, EXECUTED))


# --------------------------------------------------------------------------- the short locked sections

@contextmanager
def _short_lock(store: ProjectStore, details: dict[str, Any], wait: float, waited: dict[str, float] | None = None,
                key: str = "") -> Iterator[None]:
    """The Project execution lock for one short canonical section, its acquisition retried for up to ``wait`` s.

    Only the acquisition is retried: each try is the ordinary non-blocking one, and a refused try writes nothing.
    Once held, the section runs exactly once; whatever it raises propagates and is never retried here.
    """
    t0 = time.monotonic()
    deadline = t0 + wait
    stack = ExitStack()
    while True:
        try:
            stack.enter_context(project_operation(store, "start", details))
            break
        except ProjectOperationBusy:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)
    if waited is not None:
        waited[key] = round(time.monotonic() - t0, 3)
    with stack:
        yield


# --------------------------------------------------------------------------- workspace

@dataclass(frozen=True)
class WorkspaceSpec:
    """Where a parallel Work runs.

    ``kind`` "worktree" (default) makes a git worktree of ``repo`` (the Project
    itself when None) on a Work branch; "in_place" runs in the Project folder,
    which every Work shares, so only for a Work that reads: it returns no
    result paths and writes nothing there. ``regenerable`` are glob patterns
    (relative to the worktree) of ignored outputs the release may delete.
    """

    kind: str = "worktree"
    repo: Path | None = None
    root: Path | None = None
    regenerable: tuple[str, ...] = ()
    #: the Work branch's name prefix (the YGO Solver fork's commit guard accepts only ``feature/...``)
    branch_prefix: str = BRANCH_PREFIX
    #: another repository's result is integrated by the finish (see :class:`IntegrateSpec`); None parks it
    integrate: "IntegrateSpec | None" = None
    #: the read-only deps store (:mod:`workline.run_deps`) runs of this kind take their trees from
    deps_store: Path | None = None
    #: The Project's own preparation of a new worktree, called as ``prepare(worktree, record)`` after it is made and
    #: before the executor runs (e.g. YGO naming the Work for its fork guard in the worktree's git dir). Workline
    #: knows nothing of what it does; a failure stops the run before its executor, and it is called again on resume.
    prepare: Callable[[Path, dict], None] | None = None


@dataclass(frozen=True)
class IntegrateSpec:
    """How the finish integrates a result commit of another repository (a Solver fork) the Project holds as a gitlink.

    In order, each step recorded before the next, and none begun before every check passed:
    1. the result must descend from the Project's gitlink (at HEAD) and from ``target_branch`` of the repository;
    2. the repository's ``target_branch`` is fast-forwarded to it (never forced) - and, with ``push_remote``, the
       Work branch and then ``target_branch`` are pushed there, fast-forward only, before the Project commits a
       pointer to the commit (so the Project never publishes a pointer its remote cannot resolve);
    3. the gitlink checkout is moved to it (only when clean and detached or on ``target_branch``), and the Work's
       completion commits the gitlink ``gitlink`` in the Project.
    A failure after step 2 leaves the repository ahead of the Project's pointer, which the record names and the next
    parallel START of the Work continues from.
    """

    gitlink: str
    target_branch: str = "main"
    push_remote: str | None = None
    #: the environment the push runs with (e.g. the fork guard's FORK_INTEGRATE_VERIFIED=<sha>), ``{sha}`` filled in
    push_env: tuple[tuple[str, str], ...] = ()


def _git(repo: Path, *args: str) -> gitcmd.GitResult:
    return gitcmd.run_git(repo, *args, check=False)


def _must(repo: Path, *args: str) -> str:
    result = _git(repo, *args)
    if not result.ok:
        raise StopError(f"git {' '.join(args)} failed in {repo}: {result.stderr.strip()}", code="run_git_failed")
    return result.stdout.strip()


def _create_workspace(store: ProjectStore, record: dict[str, Any], spec: WorkspaceSpec,
                      start_at: str | None = None, base: str | None = None) -> None:
    if spec.kind == "in_place":
        # F-01 (r6 review): a reading Work never gets the Project folder itself. It runs on a snapshot - a detached
        # worktree of the Project's HEAD with the Human's uncommitted files copied in - whose files are made
        # read-only; the Project folder, the Human's uncommitted work included, is not where it writes. It still
        # returns no result paths (:func:`_execute`), and the finish still refuses when the Project folder changed
        # under it (:func:`_project_written`).
        base_root = Path(spec.root) if spec.root else store.root.parent / f"{store.root.name}.workline-runs"
        path = (base_root / record["run_id"]).resolve()
        head = gitcmd.head_commit(store.root)
        record["workspace"] = {"kind": "in_place", "snapshot": True, "path": str(path), "repo": str(store.root),
                               "base_commit": head, "folder": _folder_state(store)}
        _save(store, record)  # where it will be, before it exists
        base_root.mkdir(parents=True, exist_ok=True)
        _must(store.root, "worktree", "add", "--detach", str(path), head)
        _snapshot_overlay(store.root, path)
        return
    if spec.kind != "worktree":
        raise ValidationError(f"workspace kind must be worktree or in_place: {spec.kind!r}", code="run_workspace_kind")
    repo = Path(spec.repo or store.root).resolve()
    base_root = Path(spec.root) if spec.root else store.root.parent / f"{store.root.name}.workline-runs"
    path = (base_root / record["run_id"]).resolve()
    branch = f"{spec.branch_prefix}{record['work_id'].lower()}-{record['run_id'][-8:].lower()}"
    if base is None and spec.integrate is not None:
        # an integrated Work starts from what the Project names (its gitlink at HEAD), never from whatever the
        # checkout has out: a checkout left on other commits must not carry them into the integration
        base = _project_pointer(store, spec.integrate.gitlink)
        if base is None:
            raise StopError(f"{spec.integrate.gitlink} is not a gitlink (a mode 160000 entry) at the Project's HEAD",
                            code="run_gitlink_missing")
    base = base or _must(repo, "rev-parse", "HEAD")
    record["workspace"] = {"kind": "worktree", "repo": str(repo), "path": str(path), "branch": branch,
                           "base_commit": base, "project_repo": os.path.normcase(str(repo)) == os.path.normcase(str(store.root.resolve())),
                           "regenerable": list(spec.regenerable),
                           "integrate": None if spec.integrate is None else {
                               "gitlink": spec.integrate.gitlink, "target_branch": spec.integrate.target_branch,
                               "push_remote": spec.integrate.push_remote, "push_env": [list(e) for e in spec.integrate.push_env]},
                           "deps_store": None if spec.deps_store is None else str(spec.deps_store)}
    _save(store, record)  # where it will be, before it exists: an interrupted creation is found and cleaned
    base_root.mkdir(parents=True, exist_ok=True)
    _must(repo, "worktree", "add", "-b", branch, str(path), start_at or base)
    _prepare(store, record, spec)


def _prepare(store: ProjectStore, record: dict[str, Any], spec: WorkspaceSpec) -> None:
    ws = record.get("workspace") or {}
    if spec.prepare is None or ws.get("kind") != "worktree" or ws.get("prepared"):
        return
    spec.prepare(Path(ws["path"]), json.loads(json.dumps(record)))
    ws["prepared"] = True
    _save(store, record)


def _z(output: str) -> list[str]:
    """Git's NUL-separated output, as it names the paths (spaces, non-ASCII and quotes kept exactly)."""
    return [p for p in output.split("\0") if p]


def _project_pointer(store: ProjectStore, gitlink: str) -> str | None:
    """The commit the Project's HEAD names for ``gitlink`` - only for a mode-160000 entry, else None."""
    for entry in _z(_git(store.root, "ls-tree", "-z", "HEAD", "--", gitlink).stdout):
        meta, _, name = entry.partition("\t")
        fields = meta.split(" ")
        if name == gitlink and len(fields) == 3 and fields[0] == "160000" and fields[1] == "commit":
            return fields[2]
    return None


def _staged(store: ProjectStore) -> list[str]:
    return sorted(_z(_git(store.root, "diff", "--cached", "--name-only", "-z").stdout))


def _index_state(store: ProjectStore) -> dict[str, str]:
    """What the Project's index holds against HEAD, entry by entry: path -> ``<modes> <objects> <status>``."""
    items = _z(_git(store.root, "diff", "--cached", "--raw", "-z", "--no-renames", "--full-index").stdout)
    return {items[i + 1]: items[i] for i in range(0, len(items) - 1, 2)}


def _snapshot_overlay(project: Path, snapshot: Path) -> None:
    """Copy the Project folder's uncommitted state (tracked changes, deletions, untracked files; runtime aside) onto
    ``snapshot`` and make every file there read-only. Only the snapshot is written; the Project is only read."""
    import shutil

    out = _git(project, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames", "--", ".",
               ":(exclude).workline/runtime").stdout
    for entry in _z(out):
        if len(entry) <= 3:
            continue
        rel = entry[3:]
        source, target = project / rel, snapshot / rel
        if os.path.lexists(source) and source.is_file() and not source.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif not os.path.lexists(source) and os.path.lexists(target):
            target.unlink()
    for item in snapshot.rglob("*"):
        if item.is_file() and not item.is_symlink() and item.name != ".git":
            os.chmod(item, stat.S_IREAD)


def _remove_snapshot(record: dict[str, Any]) -> list[str]:
    """Remove an in-place run's own snapshot (Workline's copy, never the Project); what the run added there is listed."""
    import shutil

    ws = record.get("workspace") or {}
    path, repo = Path(ws["path"]), Path(ws["repo"])
    added = []
    if path.is_dir():
        out = _git(path, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames").stdout
        added = [entry[3:] for entry in _z(out) if len(entry) > 3]

        def writable(function, target, _info):
            os.chmod(target, stat.S_IWRITE)
            function(target)

        shutil.rmtree(path, onerror=writable)
    _git(repo, "worktree", "prune")
    return added


def _folder_state(store: ProjectStore) -> dict[str, str]:
    """What the Project folder holds apart from HEAD (runtime aside): path -> its exact content identity."""
    out = _git(store.root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames", "--", ".",
               ":(exclude).workline/runtime").stdout
    return {entry[3:]: _identity(store.root / entry[3:]) or "absent" for entry in _z(out) if len(entry) > 3}


def _journal(store: ProjectStore, commit: str) -> dict[str, Any] | None:
    try:
        noted = json.loads((store.root / JOURNAL_DIR / f"{commit}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return noted if isinstance(noted, dict) and noted.get("commit") == commit else None


def note_commit(store: ProjectStore, commit: str, mutation_id: str, paths: list[str], parent: str | None) -> None:
    """The Mutation Controller, right after it made ``commit``: which mutation made it, from which parent, for which
    paths - noted (runtime, never canonical) only while a parallel run holds a Work of the Project, so a Project
    without one is unchanged. A parallel finish proves with it that every commit since its claim is a Workline
    mutation's own (:func:`_unproven_commits`)."""
    if not _runs_dir(store).is_dir():
        return
    try:
        holding = any(r.get("state") in _HOLDING for r in list_runs(store))
    except StopError:
        holding = True  # a record that cannot be read may hold a Work: noting costs nothing
    if not holding:
        return
    store.tmp.mkdir(parents=True, exist_ok=True)
    durable_write_text(store.root / JOURNAL_DIR / f"{commit}.json",
                       json.dumps({"commit": commit, "mutation_id": mutation_id, "parent": parent,
                                   "paths": sorted(paths), "at": _now(), "pid": os.getpid()}, sort_keys=True) + "\n",
                       tmp_dir=store.tmp)


def _within(path: str, declared: list[str]) -> bool:
    return any(path == d or path.startswith(d.rstrip("/") + "/") for d in declared)


def _unproven_commits(store: ProjectStore, record: dict[str, Any]) -> list[str]:
    """Commits on the Project's branch since the claim that no Workline mutation is shown to have made.

    Each one must be noted by the Mutation Controller (:func:`note_commit`) with exactly its parent, and change only
    paths that mutation's commit names; the claim's commit must still be in HEAD's history, on the same branch. A
    clean ``git status`` proves none of this: an executor that committed leaves the folder clean. Commits a Human
    accepted for this run (:func:`accept_project_writes`) are not asked again.
    """
    claim = record.get("claim") or {}
    since = claim.get("head")
    if not since:
        return []
    found = []
    branch = gitcmd.current_branch_ref(store.root)
    if claim.get("branch") and branch != claim["branch"]:
        found.append(f"branch:{branch} (the claim was made on {claim['branch']})")
    head = gitcmd.head_commit(store.root)
    if head is None or _git(store.root, "merge-base", "--is-ancestor", since, head).returncode != 0:
        return found + [f"history:{since[:12]} (the claim's commit) is no longer in HEAD's history"]
    accepted = set((record.get("accepted_writes") or {}).get("commits", []))
    for commit in _git(store.root, "rev-list", "--reverse", f"{since}..{head}").stdout.split():
        if commit in accepted:
            continue
        noted = _journal(store, commit)
        parents = gitcmd.commit_parents(store.root, commit)
        if noted is None:
            found.append(f"commit:{commit} (no Workline mutation is noted as its maker)")
        elif parents != [noted.get("parent")]:
            found.append(f"commit:{commit} (its parents {parents} are not mutation {noted.get('mutation_id')}'s "
                         f"{noted.get('parent')})")
        else:
            changed = _z(_git(store.root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", commit).stdout)
            outside = [p for p in changed if not _within(p, noted.get("paths") or [])]
            if outside:
                found.append(f"commit:{commit} (changes {', '.join(outside[:5])}, which mutation "
                             f"{noted.get('mutation_id')} did not commit)")
    return found


def _project_written(store: ProjectStore, record: dict[str, Any]) -> list[str]:
    """What a lock-free executor may never have changed in the Project, read under the finish's lock before anything
    is written: uncommitted canonical ``.workline/`` files (runtime aside), the index against what it held at the
    claim, commits since the claim no Workline mutation made (:func:`_unproven_commits`), and - for a read-only
    in-place run - the Project folder against what it held at the claim. Whatever it finds stops the finish (a
    reconcile, not a guess)."""
    status = _git(store.root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames", "--",
                  ".workline", ":(exclude).workline/runtime").stdout
    canonical = sorted({entry[3:] for entry in _z(status) if len(entry) > 3})
    claim = record.get("claim", {})
    if "index" in claim:
        now = _index_state(store)
        index = sorted(p for p in set(now) | set(claim["index"]) if now.get(p) != claim["index"].get(p))
    else:
        index = sorted(set(_staged(store)) - set(claim.get("staged", [])))
    found = canonical + [f"index:{p}" for p in index] + _unproven_commits(store, record)
    ws = record.get("workspace") or {}
    if ws.get("kind") == "in_place" and "folder" in ws:
        now = _folder_state(store)
        found += [f"folder:{p}" for p in sorted(set(now) | set(ws["folder"])) if now.get(p) != ws["folder"].get(p)]
    return found


def workspace_path(record: dict[str, Any]) -> Path:
    return Path(record["workspace"]["path"])


# --------------------------------------------------------------------------- results in the workspace

def _blob(repo: Path, commit: str, path: str) -> str | None:
    result = _git(repo, "rev-parse", "--verify", "--quiet", f"{commit}:{path}")
    return result.stdout.strip() if result.ok else None


def _file_blob(repo: Path, rel: str, path: Path) -> str | None:
    if not path.is_file():
        return None
    return _must(repo, "hash-object", "--path", rel, "--", str(path))


def _identity(path: Path) -> str | None:
    """The exact content identity of ``path`` as it is now: a file's bytes, a link's target, or every file below a
    directory with its own identity (``.git`` aside); None when nothing is there."""
    if path.is_symlink():
        return "link:" + os.readlink(path)
    if path.is_file():
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                digest.update(block)
        return "file:" + digest.hexdigest()
    if path.is_dir():
        digest = hashlib.sha256()
        for inner in sorted(p for p in path.rglob("*") if not p.is_dir() or p.is_symlink()):
            rel = inner.relative_to(path).as_posix()
            if rel.split("/")[0] != ".git":
                digest.update(f"{rel}\0{_identity(inner)}\n".encode("utf-8"))
        return "tree:" + digest.hexdigest()
    return "other" if os.path.lexists(path) else None


def _returned_identity(root: Path, paths: list[str]) -> dict[str, str | None]:
    return {p: _identity(root / p) for p in paths}


def _unproven_result(record: dict[str, Any], root: Path) -> list[str]:
    """How what ``root`` holds now differs from what the executor returned (its recorded content identity): a result
    changed, replaced or missing, or a deletion undone. Presence alone never proves a result."""
    outcome = record.get("outcome") or {}
    recorded = outcome.get("identity")
    if not isinstance(recorded, dict):
        return ["no content identity was recorded when the executor returned"]
    problems = []
    for p in outcome.get("result_paths", []):
        now = _identity(root / p)
        if now is None:
            problems.append(f"{p} is missing")
        elif recorded.get(p) != now:
            problems.append(f"{p} is not what the executor returned ({str(recorded.get(p))[:20]} -> {now[:20]})")
    problems += [f"{p} was to be deleted but exists" for p in outcome.get("deleted_paths", [])
                 if os.path.lexists(root / p)]
    return problems


def _check_result_paths(paths: list[str]) -> None:
    for p in paths:
        parts = Path(p).parts
        if Path(p).is_absolute() or ".." in parts or not parts or parts[0] in (".workline", ".git"):
            raise ValidationError(f"a parallel Work result must be a Project path outside .workline: {p!r}",
                                  code="run_result_path")


def _commit_in_workspace(record: dict[str, Any], paths: list[str], deleted: list[str], message: str) -> str | None:
    ws = workspace_path(record)
    if paths:
        _must(ws, "add", "--", *paths)
    for p in deleted:
        _must(ws, "rm", "--quiet", "--cached", "--ignore-unmatch", "--", p)
    staged = _z(_git(ws, "diff", "--cached", "--name-only", "-z").stdout)
    if not staged:
        return _must(ws, "rev-parse", "HEAD")
    _must(ws, "commit", "--quiet", "-m", message)
    return _must(ws, "rev-parse", "HEAD")


def _conflicts(store: ProjectStore, record: dict[str, Any], paths: list[str], deleted: list[str],
               snapshot: dict[str, bytes] | None = None) -> list[str]:
    """Result paths the Project changed since the run's base in a way the run's result does not match."""
    ws = record["workspace"]
    base = ws["base_commit"]
    head = gitcmd.head_commit(store.root)
    found = []
    for p in sorted(set(paths) | set(deleted)):
        before = _blob(store.root, base, p)
        now = _blob(store.root, head, p)
        if p in deleted:
            mine = None
        elif snapshot is not None:
            hashed = gitcmd.run_git_bytes(store.root, "hash-object", "--path", p, "--stdin", input=snapshot[p])
            mine = hashed.stdout.decode("ascii").strip() if hashed.returncode == 0 else None
        else:
            mine = _file_blob(store.root, p, workspace_path(record) / p)
        if now != before and mine != now:
            found.append(p)
        elif gitcmd.changed_against_head(store.root, [p]) and _file_blob(store.root, p, store.root / p) != mine:
            found.append(p)  # someone's uncommitted change in the Project folder
    return found


def _verified_snapshot(record: dict[str, Any]) -> tuple[dict[str, bytes], list[str]]:
    """F-03 (r6 review): the result files read ONCE into memory, each proven against the content identity recorded
    when the executor returned and against the Work branch's result commit (as Git writes it out); what is copied
    into the Project is these bytes, never a second read of the mutable workspace."""
    ws = workspace_path(record)
    outcome = record.get("outcome") or {}
    recorded = outcome.get("identity") or {}
    snapshot, problems = {}, []
    for p in outcome.get("result_paths", []):
        path = ws / p
        if path.is_symlink() or not path.is_file():
            problems.append(f"{p} is not a regular file")
            continue
        data = path.read_bytes()
        if "file:" + hashlib.sha256(data).hexdigest() != recorded.get(p):
            problems.append(f"{p} is not what the executor returned")
            continue
        commit = record.get("result_commit")
        if commit:
            written = gitcmd.run_git_bytes(Path(record["workspace"]["repo"]), "cat-file", "--filters", f"{commit}:{p}",
                                           cwd=ws)
            if written.returncode != 0 or hashlib.sha256(written.stdout).hexdigest() != hashlib.sha256(data).hexdigest():
                problems.append(f"{p} differs from the result commit {commit[:12]}")
                continue
        snapshot[p] = data
    return snapshot, problems


def _copy_results(store: ProjectStore, record: dict[str, Any], paths: list[str], deleted: list[str],
                  snapshot: dict[str, bytes] | None = None) -> None:
    ws = workspace_path(record)
    for p in paths:
        target = store.root / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(snapshot[p] if snapshot is not None else (ws / p).read_bytes())
    for p in deleted:
        target = store.root / p
        if target.exists():
            target.unlink()


# --------------------------------------------------------------------------- release

def _ignored_and_dirty(ws: Path) -> tuple[list[str], list[str]]:
    out = _git(ws, "status", "--porcelain=v1", "--ignored", "--untracked-files=all", "--no-renames", "-z").stdout
    dirty, ignored = [], []
    for entry in (e for e in out.split("\0") if e):
        code, path = entry[:2], entry[3:]
        (ignored if code == "!!" else dirty).append(path)
    return dirty, ignored


def release(store: ProjectStore, work_id: str) -> dict[str, Any]:
    """Release (or resume releasing) the workspace of ``work_id``'s run; returns the record as it ends.

    Never deletes what is not integrated or regenerable. A failure is recorded
    as ``cleanup_failed`` with what blocked it and returned, not raised: it
    belongs to this run alone.
    """
    with _invocation(store, work_id, join=True):
        return _release(store, work_id)


def _release(store: ProjectStore, work_id: str) -> dict[str, Any]:
    record = read_run(store, work_id)
    if record is None:
        raise StopError(f"no parallel run for {work_id}", code="run_missing")
    if record["state"] == RELEASED:
        return record
    if record["state"] not in (RELEASING, CLEANUP_FAILED, PARKED):
        raise StopError(f"run {record['run_id']} is {record['state']}; only a finished run is released",
                        code="run_not_finished")
    if not _owned_by_me(store, record):
        # a release is resumed by whoever comes next; one still being made (releasing) only once its owner is gone -
        # a cleanup_failed / parked run's owner has ended its turn
        state = owner_state(record) if record["state"] == RELEASING else DEAD
        if state != DEAD:
            raise StopError(f"run {record['run_id']} of {work_id} is being released by its owner "
                            f"(pid {record.get('pid')}, {state}); nothing was done",
                            code="work_run_active" if state == ALIVE else "run_owner_unknown")
        _become_owner(store, record)
        _save(store, record, take=True)
    ws = record.get("workspace") or {}
    if ws.get("kind") != "worktree":
        import shutil

        stash = _runs_dir(store) / record["run_id"]
        removed = []
        if stash.is_dir():
            shutil.rmtree(stash)  # the set-aside copies of results the completion has committed
            removed.append(f"{RUNS_DIR}/{record['run_id']}")
        written = _remove_snapshot(record) if ws.get("snapshot") else []
        _set(store, record, RELEASED, cleanup={"state": "released", "removed": removed,
                                               "snapshot_writes_discarded": written})
        return record
    path, repo = Path(ws["path"]), Path(ws["repo"])
    try:
        blocked = []
        removed: list[str] = []
        integrated_now = record.get("integration", {}).get("state") == "integrated"
        if path.exists() and not integrated_now:
            # what a held / cancelled / stopped run leaves uncommitted is its work in progress: kept as a commit
            # on the Work branch (and so on the parked ref below), never discarded with the worktree. The worktree
            # is this run's alone; what it keeps is its tracked changes and its untracked (not ignored) files up
            # to WIP_FILE_LIMIT / WIP_TOTAL_LIMIT - anything larger is listed and blocks the release instead.
            untracked = [p for p in _git(path, "ls-files", "--others", "--exclude-standard", "-z").stdout.split("\0") if p]
            sizes = {p: (path / p).stat().st_size for p in untracked if (path / p).is_file()}
            too_big = sorted(p for p, n in sizes.items() if n > WIP_FILE_LIMIT)
            if too_big or sum(sizes.values()) > WIP_TOTAL_LIMIT:
                blocked.append(f"untracked files too large to keep as work in progress: "
                               f"{', '.join(too_big[:10]) or f'{sum(sizes.values())} bytes in total'}")
            else:
                _must(path, "add", "-u")
                if untracked:
                    _must(path, "add", "--", *untracked)
                if _git(path, "diff", "--cached", "--quiet").returncode != 0:
                    _must(path, "commit", "--quiet", "-m", f"workline: work in progress of {record['work_id']} "
                                                            f"(run {record['run_id']}, parked)")
                    record["wip_commit"] = _must(path, "rev-parse", "HEAD")
                    record["wip_untracked"] = sorted(untracked)
        if path.exists():
            dirty, ignored = _ignored_and_dirty(path)
            if dirty:
                blocked.append(f"uncommitted or untracked: {', '.join(sorted(dirty)[:10])}")
            patterns = ws.get("regenerable") or []
            keep = [p for p in ignored if not any(fnmatch.fnmatch(p.rstrip('/'), pat) or fnmatch.fnmatch(p, pat) for pat in patterns)]
            if keep:
                blocked.append(f"ignored files not declared regenerable: {', '.join(sorted(keep)[:10])}")
        tip = _git(repo, "rev-parse", "--verify", "--quiet", ws["branch"]).stdout.strip()
        if tip:
            # the run's own commits are always kept on a saved ref before the branch can go
            saved = SAVED_REF_PREFIX + record["run_id"]
            _must(repo, "update-ref", saved, tip)
            record.setdefault("refs", {})["saved"] = saved
        integrated = record.get("integration", {}).get("state") == "integrated"
        if not integrated and tip and tip != ws["base_commit"]:
            parked = PARKED_REF_PREFIX + record["run_id"]
            _must(repo, "update-ref", parked, tip)
            record["refs"]["parked"] = parked
        if blocked:
            _set(store, record, CLEANUP_FAILED, cleanup={"state": "blocked", "blocked": blocked}, next_actor="human")
            return record
        _set(store, record, RELEASING, cleanup={"state": "removing"})
        if path.exists():
            for p in ignored:
                target = path / p
                if target.is_dir():
                    import shutil

                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
                removed.append(p)
            result = _git(repo, "worktree", "remove", str(path))
            if not result.ok:
                _set(store, record, CLEANUP_FAILED, cleanup={"state": "remove_failed", "blocked": [result.stderr.strip()]},
                     next_actor="human")
                return record
            if path.exists():
                _set(store, record, CLEANUP_FAILED,
                     cleanup={"state": "directory_left", "blocked": [f"{path} still exists (in use?)"]}, next_actor="human")
                return record
        _git(repo, "worktree", "prune")
        _drop_deps_users(record)
        if tip and (integrated or tip == ws["base_commit"]):
            _must(repo, "branch", "-D", ws["branch"])  # its commit stays on the saved ref
        final = RELEASED if integrated or not tip or tip == ws["base_commit"] else PARKED
        _set(store, record, final, cleanup={"state": "released", "removed_files": len(removed),
                                            "removed_top": sorted({r.split("/")[0] for r in removed})},
             next_actor=None if final == RELEASED else "integration")
        return record
    except (StopError, OSError) as exc:
        _set(store, record, CLEANUP_FAILED, cleanup={"state": "error", "blocked": [str(exc)]}, next_actor="human")
        return record


# --------------------------------------------------------------------------- the parallel START

def run(store: ProjectStore, work_id: str, executor, spec: WorkspaceSpec | None = None, *, mode: str = "single-work",
        selectors: tuple = (None, None), lock_wait: float = LOCK_RETRY_SECONDS):
    """One parallel START of ``work_id`` (see the module docstring); returns a ``start.StartResult``."""
    from . import start as st

    if mode != "single-work" or any(selector is not None for selector in selectors):
        raise ValidationError("a parallel START runs one named Work (mode single-work) without a Review selector",
                              code="parallel_start_shape")
    # one invocation per Work in this process: another thread's START of the Work, or one made from inside its own
    # executor, is refused before anything is read or written (the run record is owned by this invocation)
    with _invocation(store, work_id):
        return _run(store, work_id, executor, spec, lock_wait)


def _run(store: ProjectStore, work_id: str, executor, spec: WorkspaceSpec | None, lock_wait: float):
    from . import start as st

    spec = spec or WorkspaceSpec()
    timings: dict[str, float] = {}
    try:
        return _run_timed(store, work_id, executor, spec, lock_wait, timings)
    finally:
        _keep_timings(store, work_id, timings)


def _keep_timings(store: ProjectStore, work_id: str, timings: dict[str, float]) -> None:
    """F-06: this invocation's timings (lock waits and stage times, kept apart) on its run, whatever the way out."""
    if not timings:
        return
    try:
        latest = read_run(store, work_id)
        if latest is None or not _owned_by_me(store, latest):
            return
        kept = {k: round(v, 3) for k, v in timings.items()}
        latest["timings"] = kept
        latest.setdefault("timings_history", []).append({"at": _now(), "state": latest.get("state"), **kept})
        _save(store, latest)
    except StopError:
        pass  # a record another owner holds now, or none: nothing of it is overwritten


def _run_timed(store: ProjectStore, work_id: str, executor, spec: WorkspaceSpec, lock_wait: float,
               timings: dict[str, float]):
    from . import start as st

    details = {"work_id": work_id, "mode": "single-work", "parallel": True}

    # 1. claim ------------------------------------------------------------
    t0 = time.perf_counter()
    with _short_lock(store, details, lock_wait, timings, "claim_lock_wait_s"):
        record = _claim(store, work_id, spec)
    if not isinstance(record, dict):
        return record  # the claim did not leave the Work running (refused, held, ...): its own result
    timings["claim_s"] = time.perf_counter() - t0

    while True:
        # 2. run (no lock) -----------------------------------------------------
        t1 = time.perf_counter()
        if record.get("outcome", {}).get("kind") == "completed" and record["state"] == EXECUTED:
            outcome = st.Completed(tuple(record["outcome"]["result_paths"]), record["outcome"].get("message"),
                                   tuple(record["outcome"].get("deleted_paths", ())))
        else:
            outcome = _execute(store, record, executor)
        timings["run_s"] = time.perf_counter() - t1
        if isinstance(outcome, st.QuestionWait):
            _set(store, record, QUESTION_WAIT, question=outcome.question, next_actor="human")
            return st.StartResult("question_wait", work_id, record["claim"]["mutation_id"], detail=outcome.question)

        # 3. finish (locked) ---------------------------------------------------
        t2 = time.perf_counter()
        try:
            with _short_lock(store, details, lock_wait, timings, "finish_lock_wait_s"):
                result = _finish(store, record, outcome)
        except BaseException as exc:
            # the finish stopped: what the run recorded (its result, the integration stages) stays; the next
            # parallel START of the Work continues the finish from there
            latest = read_run(store, work_id) or record
            if latest.get("run_id") == record.get("run_id") and _owned_by_me(store, latest):
                latest["finish_error"] = f"{type(exc).__name__}: {exc}"[:1000]
                if latest.get("next_actor") != "human":
                    latest["next_actor"] = "start"
                _save(store, latest)
            raise
        timings["finish_s"] = time.perf_counter() - t2
        if result.status != "running":
            break
        record = read_run(store, work_id)  # a non-moving derivation: the Work runs again in its workspace
        _set(store, record, RUNNING, pid=os.getpid())

    # 4. release -----------------------------------------------------------
    t3 = time.perf_counter()
    if read_run(store, work_id)["state"] in (RELEASING,):
        released = release(store, work_id)
        if released["state"] != RELEASED:
            result = st.StartResult(result.status, result.work_id, result.mutation_id, result.completed_work_ids,
                                    result.phase_id, "; ".join(x for x in (
                                        result.detail, f"cleanup {released['state']}: {released.get('cleanup')}") if x),
                                    result.head, code="run_cleanup_incomplete")
    timings["release_s"] = time.perf_counter() - t3
    return result


def _claim(store: ProjectStore, work_id: str, spec: WorkspaceSpec):
    """The claim, under the Project execution lock: the run record (an existing one taken over only from a gone or
    finished owner), the Work's START lifecycle committed, the workspace. A ``StartResult`` when the Work is not left
    running; raises a STOP when another owner holds it or when what happened before cannot be established."""
    from . import start as st

    record = read_run(store, work_id)
    if record is not None and record["state"] in (RELEASING, CLEANUP_FAILED):
        release(store, work_id)
        record = read_run(store, work_id)
    resume_parked = None
    if record is not None and record["state"] == PARKED and record.get("integration", {}).get("state") == "held" \
            and record.get("refs", {}).get("parked"):
        resume_parked = record  # a held run's kept work is where the resumed Work continues
    if record is not None and record["state"] in (RELEASED, PARKED):
        record = None  # a finished run: a new START of the Work (if it is still startable) is a new run
    if record is not None:
        state = record["state"]
        if state in _LIVE and not _owned_by_me(store, record):
            owner = owner_state(record)
            if owner == ALIVE:
                raise StopError(f"Work {work_id} is already running in parallel run {record['run_id']} "
                                f"(pid {record.get('pid')}); nothing was begun", code="work_run_active")
            if owner == UNKNOWN:
                raise StopError(f"run {record['run_id']} of {work_id} is {state} and its owner (pid {record.get('pid')} on "
                                f"{record.get('host')}) cannot be proven gone; nothing was begun. A Human who knows it "
                                "is gone says so with parallel.declare_owner_gone", code="run_owner_unknown")
            if state == RUNNING:
                # the owner died while its executor ran: what that executor already did is not known, so it is not
                # simply run again
                _set(store, record, INTERRUPTED, take=True, next_actor="human", resume_acknowledged=None,
                     interrupted={"at": _now(), "attempt": record.get("attempts"), "owner": record.get("owner")})
                raise StopError(f"run {record['run_id']} of {work_id} was interrupted while its executor ran (attempt "
                                f"{record.get('attempts')}); its effects are unknown. It is run again only after "
                                "parallel.acknowledge_interrupted", code="run_interrupted")
        if state == RETURNED:
            # the executor returned (its owner gone, or this process stopped after it): finished from the record
            if not _owned_by_me(store, record):
                _become_owner(store, record)
                _save(store, record, take=True)
            _recover_returned(store, record)  # EXECUTED, or a STOP when the result cannot be proven
            state = record["state"]
        if state == CLAIMING:
            # no claim is in progress while this one holds the lock: that claim was interrupted, and is made again
            # below (the START mutation resumes; the lifecycle is not recorded twice)
            record = None
        elif state == INTERRUPTED and not record.get("resume_acknowledged"):
            raise StopError(f"run {record['run_id']} of {work_id} was interrupted while its executor ran; it is run "
                            "again only after parallel.acknowledge_interrupted", code="run_interrupted")
        elif state == OUTCOME_UNKNOWN:
            raise StopError(f"run {record['run_id']} of {work_id}: its executor returned but what it left cannot be "
                            f"proven ({record.get('unknown')}); a Human decides", code="run_outcome_unknown")
        elif state == CONFLICT:
            raise StopError(f"run {record['run_id']} of {work_id} is parked on a conflict "
                            f"({', '.join(record.get('conflicts', []))}); integrate it first", code="run_conflict_parked")
    if record is not None:
        if not _owned_by_me(store, record):
            _become_owner(store, record)
            _save(store, record, take=True)
        recorded = (record.get("workspace") or {}).get("integrate")
        if recorded and spec.integrate is not None and spec.integrate.gitlink == recorded["gitlink"] \
                and spec.integrate.target_branch == recorded["target_branch"] \
                and [list(e) for e in spec.integrate.push_env] != recorded.get("push_env"):
            # the push environment is the caller's attestation (e.g. FORK_INTEGRATE_VERIFIED, which the repository's
            # own guard checks): the invocation that resumes the run states it again, and the change is kept
            record.setdefault("push_env_history", []).append({"was": recorded.get("push_env"), "at": _now()})
            recorded["push_env"] = [list(e) for e in spec.integrate.push_env]
            _save(store, record)
        if record["state"] == CREATING:
            with _token(store, work_id, record["run_id"]):
                if not Path(record.get("workspace", {}).get("path", "")).exists():
                    _create_workspace(store, record, spec)
                else:
                    _prepare(store, record, spec)
        if record["state"] == INTERRUPTED:
            # one acknowledgement, one re-run: it is used up here, and a later interruption needs a new one
            record.setdefault("resumed_after_interruption", []).append(record.pop("resume_acknowledged"))
    else:
        if spec.integrate is not None and _project_pointer(store, spec.integrate.gitlink) is None:
            # checked before anything is written: no claim is made for an integration the Project cannot name
            raise StopError(f"{spec.integrate.gitlink} is not a gitlink (a mode 160000 entry) at the Project's HEAD; "
                            "nothing was begun", code="run_gitlink_missing")
        record = {"workline": RUN_MARKER, "version": RUN_VERSION, "run_id": f"run_{new_ulid()}",
                  "work_id": work_id, "created_at": _now()}
        _become_owner(store, record)
        if resume_parked is not None:
            record["resumed_from"] = {"run_id": resume_parked["run_id"], "ref": resume_parked["refs"]["parked"]}
        previous = read_run(store, work_id)
        if previous is not None:
            record["previous_runs"] = previous.get("previous_runs", []) + [
                {k: previous.get(k) for k in ("run_id", "state", "result_commit", "refs", "integration")}]
        before = _claim_trace(store, work_id)
        _set(store, record, CLAIMING, take=True)  # before the claim: a claim interrupted after its commit is still found
        try:
            with _token(store, work_id, record["run_id"]):
                claimed = st._start_locked(store, work_id, "single-work", lambda ctx: st.Detach())
        except BaseException as exc:
            # forgotten only when the claim provably wrote nothing: its commit may have been made (and its push
            # refused), and a Work left in progress always keeps the run record that holds it
            _keep_or_forget(store, record, previous, before, f"{type(exc).__name__}: {exc}")
            raise
        if claimed.status != "running":
            _keep_or_forget(store, record, previous, before, f"the claim ended {claimed.status}: {claimed.detail}")
            return claimed
        _set(store, record, CREATING, claim={"mutation_id": claimed.mutation_id, "head": claimed.head,
                                             "branch": gitcmd.current_branch_ref(store.root),
                                             "staged": _staged(store), "index": _index_state(store)})
        with _token(store, work_id, record["run_id"]):
            if resume_parked is not None:
                old = resume_parked["workspace"]
                kept = _must(Path(old["repo"]), "rev-parse", resume_parked["refs"]["parked"])
                _create_workspace(store, record, spec, start_at=kept, base=old["base_commit"])
            else:
                _create_workspace(store, record, spec)
    _set(store, record, EXECUTED if record["state"] == EXECUTED else RUNNING, pid=os.getpid(), host=socket.gethostname())
    return record


def _execute(store: ProjectStore, record: dict[str, Any], executor):
    from . import start as st
    from .state import ProjectView

    view = ProjectView.load(store)
    work = view.works[record["work_id"]]
    phase = view.phases.get(work.phase_id) if work.phase_id else None
    roadmap = view.roadmaps.get(phase.roadmap_id or "") if phase else None
    attempt = int(record.get("attempts", 0)) + 1
    record["attempts"] = attempt
    _save(store, record)
    context = st.ExecutionContext(store, view, work, view.work_state(work.id), phase, roadmap,
                                  st.reading_plan(store, view, work), record["claim"]["mutation_id"], "single-work",
                                  attempt, workspace=workspace_path(record), run_id=record["run_id"])
    here = os.getcwd()
    try:
        outcome = executor(context)
    except BaseException as exc:
        _set(store, record, FAILED, error=f"{type(exc).__name__}: {exc}", next_actor="start")
        raise
    finally:
        os.chdir(here)
    record["deps"] = (read_run(store, record["work_id"]) or {}).get("deps", record.get("deps", []))
    if isinstance(outcome, st.Detach):
        # Detach is Workline's own, never an executor's: refused like any unknown outcome
        _set(store, record, FAILED, error="the executor returned Detach", next_actor="start")
        raise ValidationError("an executor returned start.Detach, which only Workline's parallel claim / finish may use",
                              code="parallel_detach_refused")
    if isinstance(outcome, st.Completed):
        paths = [p.replace("\\", "/") for p in outcome.result_paths]
        deleted = [p.replace("\\", "/") for p in outcome.deleted_paths]
        try:
            _check_result_paths(paths + deleted)
            if record["workspace"]["kind"] == "in_place" and (paths or deleted):
                # the Project folder is every Work's: a Work that writes results gets a workspace of its own
                raise ValidationError(f"an in-place parallel Work is read-only, and returned results "
                                      f"({', '.join((paths + deleted)[:5])}); run it in a worktree workspace",
                                      code="parallel_in_place_read_only")
        except ValidationError as exc:
            _set(store, record, FAILED, error=f"{type(exc).__name__}: {exc}", next_actor="start")
            raise
        # what the executor returned is recorded before anything else is done with it - with the exact content
        # identity of each result: an interruption from here on is resumed from the record, never by running the
        # executor again, and only while the workspace still holds exactly that
        _set(store, record, RETURNED, result_commit=None,
             outcome={"kind": "completed", "result_paths": paths, "deleted_paths": deleted, "message": outcome.message,
                      "commit_message": (outcome.message or f"work({work.display}): result").strip(),
                      "identity": _returned_identity(workspace_path(record), paths)})
        _commit_returned(store, record)
    return outcome


def _commit_returned(store: ProjectStore, record: dict[str, Any]) -> None:
    """RETURNED -> EXECUTED: the recorded result committed on the Work branch (worktree runs)."""
    outcome = record["outcome"]
    commit = None
    if record["workspace"]["kind"] == "worktree":
        try:
            commit = _commit_in_workspace(record, outcome["result_paths"], outcome["deleted_paths"],
                                          outcome["commit_message"])
        except StopError as exc:
            # e.g. the repository's own commit hook refused: nothing is bypassed, the result stays recorded
            _set(store, record, RETURNED, commit_error=str(exc)[:1000], next_actor="human")
            raise
    _set(store, record, EXECUTED, result_commit=commit)


def _recover_returned(store: ProjectStore, record: dict[str, Any]) -> None:
    """A run whose owner died after its executor returned: resumed from the record when the workspace still holds
    exactly what was returned - each result's content identity as recorded, each deletion still absent - else
    OUTCOME_UNKNOWN (STOP). The executor is never run again for it."""
    outcome = record.get("outcome") or {}
    ws = record.get("workspace") or {}
    root = Path(ws.get("path", "")) if ws.get("kind") == "worktree" else store.root
    problems = []
    if outcome.get("kind") != "completed":
        problems.append("no recorded result")
    elif not root.is_dir():
        problems.append(f"the workspace {root} is gone")
    else:
        problems += _unproven_result(record, root)
    if problems:
        _set(store, record, OUTCOME_UNKNOWN, next_actor="human", unknown=problems)
        raise StopError(f"run {record['run_id']} of {record['work_id']}: its executor returned, but the result cannot be "
                        f"proven ({'; '.join(problems)}); nothing was run again", code="run_outcome_unknown")
    record["recovered_from"] = RETURNED
    _commit_returned(store, record)


def acknowledge_interrupted(store: ProjectStore, work_id: str, note: str) -> dict[str, Any]:
    """A Human (or the CP) accepts that an interrupted run's executor is run again, in the same workspace, by the next
    parallel START of the Work - knowing its first run may have had effects Workline cannot see."""
    if not isinstance(note, str) or not note.strip():
        raise ValidationError("acknowledging an interrupted run needs a note saying who decided and why",
                              code="run_ack_note")
    with _short_lock(store, {"work_id": work_id, "parallel": True, "acknowledge": True}, 30.0):
        record = read_run(store, work_id)
        if record is None or record["state"] != INTERRUPTED:
            raise StopError(f"no interrupted run of {work_id}", code="run_not_interrupted")
        _set(store, record, INTERRUPTED, take=True, next_actor="start", resume_acknowledged={"at": _now(), "note": note})
        return record


def declare_owner_gone(store: ProjectStore, work_id: str, run_id: str, note: str) -> dict[str, Any]:
    """A Human states that a run's owner Workline cannot check (another host, a refused query) is gone. Only for an
    owner whose state is ``unknown``: a live owner is never declared gone, a dead one needs no declaration."""
    if not isinstance(note, str) or not note.strip():
        raise ValidationError("declaring an owner gone needs a note saying who checked and how", code="run_owner_note")
    with _short_lock(store, {"work_id": work_id, "parallel": True, "owner_gone": True}, 30.0):
        record = read_run(store, work_id)
        if record is None or record.get("run_id") != run_id:
            raise StopError(f"no parallel run {run_id} of {work_id}", code="run_missing")
        state = owner_state(record)
        if state == ALIVE:
            raise StopError(f"the owner of {run_id} (pid {record.get('pid')}) is alive", code="work_run_active")
        if state == DEAD:
            return record
        owner = record.get("owner") or {}
        _set(store, record, record["state"], take=True,
             owner_cleared={"nonce": owner.get("nonce"), "pid": owner.get("pid"), "host": owner.get("host"),
                            "at": _now(), "note": note})
        return record


def _finish(store: ProjectStore, record: dict[str, Any], outcome):
    from . import mutation
    from . import start as st

    work_id = record["work_id"]
    with _token(store, work_id, record["run_id"]):
        if not _owned_by_me(store, read_run(store, work_id) or {"work_id": work_id}):
            raise StopError(f"run {record['run_id']} of {work_id} is no longer owned by this process; its finish is "
                            "not made here", code="run_owner_changed")
        touched = _project_written(store, record)
        if touched:
            # the executor ran without the lock: it may write its own workspace, never the Project's canonical files
            # or its index. Nothing is finished; the Project needs a reconcile, not a guess
            _set(store, record, record["state"], next_actor="human", project_written=touched)
            raise StopError("the Project's canonical files, Git index, history or folder changed in ways no Workline "
                            f"operation is shown to have made while this run worked ({', '.join(touched[:8])}); "
                            "nothing is finished: reconcile required", code="run_project_written")
        ws = record["workspace"]
        drift = _base_drift(store, record)  # what the Project changed since the base, before this finish commits
        result_paths = list(record.get("outcome", {}).get("result_paths") or [])
        allowed_gitlink = None
        if isinstance(outcome, st.Completed) and ws["kind"] == "worktree" and not ws.get("project_repo"):
            # another repository (a Solver worktree, approach S): its result is the commit on the Work branch
            if not ws.get("integrate"):
                # no integration declared: the Work completes and the commit waits on its saved and parked refs
                outcome = st.Completed((), outcome.message)
                record["integration_pending"] = {"repo": ws["repo"], "branch": ws["branch"],
                                                 "commit": record["result_commit"]}
            else:
                refused = _integrate_repository(store, record)
                if refused is not None:
                    return refused
                result_paths = [ws["integrate"]["gitlink"]]
                # the one gitlink this finish integrates is the only directory its completion may carry as a commit
                allowed_gitlink = (store.root, ws["integrate"]["gitlink"], record["result_commit"])
                outcome = st.Completed((ws["integrate"]["gitlink"],), outcome.message)
        assessment = _drift_assessment(drift, result_paths)
        if isinstance(outcome, st.Completed) and outcome.result_paths and drift:
            outcome = st.Completed(outcome.result_paths, _with_drift_trailer(store, work_id, outcome.message, assessment),
                                   outcome.deleted_paths)
        calls = {"n": 0}
        if isinstance(outcome, st.Completed) and ws["kind"] == "worktree" and ws.get("integrate") \
                and not ws.get("project_repo"):
            completed = outcome

            def finishing(ctx):
                calls["n"] += 1
                if calls["n"] > 1:
                    return st.Detach()
                _move_checkout(store, record)
                return completed
        elif isinstance(outcome, st.Completed) and ws["kind"] == "worktree" and ws.get("project_repo"):
            paths = list(record["outcome"]["result_paths"])
            deleted = list(record["outcome"]["deleted_paths"])
            changed = _unproven_result(record, workspace_path(record))
            snapshot, unproven = _verified_snapshot(record)
            changed += [u for u in unproven if u not in changed]
            if changed:
                # what is copied into the Project is exactly what the executor returned, or nothing
                _set(store, record, OUTCOME_UNKNOWN, next_actor="human", unknown=changed)
                raise StopError(f"run {record['run_id']} of {work_id}: the workspace no longer holds what the executor "
                                f"returned ({'; '.join(changed)}); nothing was integrated", code="run_outcome_unknown")
            conflicts = _conflicts(store, record, paths, deleted, snapshot)
            if conflicts:
                parked = PARKED_REF_PREFIX + record["run_id"]
                _must(Path(record["workspace"]["repo"]), "update-ref", parked, record["result_commit"])
                _set(store, record, CONFLICT, conflicts=conflicts, refs={"parked": parked}, next_actor="human",
                     integration={"state": "conflict", "target": gitcmd.current_branch_ref(store.root)})
                return st.StartResult("conflict", work_id, record["claim"]["mutation_id"],
                                      detail=f"result conflicts with the Project at {', '.join(conflicts)}; "
                                             f"kept on {parked}", code="run_conflict")
            completed = outcome

            def finishing(ctx):
                calls["n"] += 1
                if calls["n"] > 1:
                    return st.Detach()
                _copy_results(store, record, paths, deleted, snapshot)
                return completed
        else:
            def finishing(ctx):
                calls["n"] += 1
                return outcome if calls["n"] == 1 else st.Detach()

        _set(store, record, record["state"], finishing_at=_now())
        with ExitStack() as allow:
            if allowed_gitlink is not None:
                allow.enter_context(mutation.allow_gitlink(*allowed_gitlink))
            result = st._start_locked(store, work_id, "single-work", finishing)
        if result.status == "running":
            _set(store, record, RUNNING, outcome={})
            return result
        if result.status == "completed" and record.get("integration_pending"):
            _set(store, record, RELEASING, integration={"state": "pending", **record["integration_pending"],
                                                        "work_commit": gitcmd.head_commit(store.root),
                                                        "base_drift": drift, "drift": assessment},
                 next_actor="integration")
        elif result.status == "completed":
            _set(store, record, RELEASING, integration={**record.get("integration", {}), "state": "integrated",
                                                        "target": gitcmd.current_branch_ref(store.root),
                                                        "commit": gitcmd.head_commit(store.root),
                                                        "finish_mutation_id": result.mutation_id,
                                                        "base_drift": drift, "drift": assessment},
                 next_actor="workline")
        else:
            # held, cancelled, moved, stopped: the Work's own outcome ends this run; what the workspace holds is
            # kept on a parked ref by the release when it is not integrated
            _set(store, record, RELEASING, integration={**record.get("integration", {}), "state": result.status},
                 next_actor="workline")
        if result.status == "completed" and drift:
            # integrated by path, never verified together with what the Project changed meanwhile: the caller is told
            result = st.StartResult(result.status, result.work_id, result.mutation_id, result.completed_work_ids,
                                    result.phase_id, f"base drift ({assessment['eligibility']}): "
                                    f"{', '.join(drift[:20])}{' ...' if len(drift) > 20 else ''}",
                                    result.head, code="integrated_with_base_drift")
        return result


def _drift_assessment(drift: list[str], result_paths: list[str]) -> dict[str, Any]:
    """What the drift means for the result: never a pass or a fail by itself.

    ``near_result`` are drift paths in a directory the result also changed (or the result path itself): the
    combination is the first thing a re-run or a Review checks. A drift elsewhere can still interact (a header, a
    configuration); it is listed, not dismissed.
    """
    def parent(p: str) -> str:
        return p.rsplit("/", 1)[0] if "/" in p else ""

    dirs = {parent(p) for p in result_paths} | set(result_paths)
    near = sorted(d for d in drift if d in dirs or parent(d) in dirs
                  or any(d.startswith(r + "/") or r.startswith(d + "/") for r in result_paths))
    return {"paths": list(drift), "near_result": near, "verified_together": False, "integration": "mechanical",
            "eligibility": "reverify_near_result" if near else ("review_listed_drift" if drift else "no_drift")}


def _with_drift_trailer(store: ProjectStore, work_id: str, message: str | None, assessment: dict[str, Any]) -> str:
    from . import start as st
    from .state import ProjectView

    base = st._result_message(message, ProjectView.load(store).works[work_id])
    paths = assessment["paths"]
    listed = ", ".join(paths[:20]) + (f" (+{len(paths) - 20} more)" if len(paths) > 20 else "")
    return (f"{base.rstrip()}\n\n"
            f"Workline-Base-Drift: {listed}\n"
            f"Workline-Base-Drift-Near-Result: {', '.join(assessment['near_result']) or 'none'}\n"
            f"Workline-Integration: mechanical; not verified together with the drift ({assessment['eligibility']})\n")


def _work_events(store: ProjectStore, work_id: str) -> int:
    """How many events the Project folder's event log holds for ``work_id`` (committed or not)."""
    count = 0
    for log in sorted((store.root / ".workline" / "events").glob("*.jsonl")):
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                count += json.loads(line).get("entity") == work_id
            except (ValueError, AttributeError):
                count += 1  # a line that cannot be read is counted as a change, never as nothing
    return count


def _pending_mutations(store: ProjectStore) -> list[str]:
    from .mutation import MutationController

    try:
        return sorted(str(r.get("mutation_id")) for r in MutationController(store).list_pending())
    except (StopError, OSError) as exc:
        return [f"unreadable ({exc})"]  # never read as "nothing pending"


def _claim_trace(store: ProjectStore, work_id: str) -> dict[str, Any]:
    """What a claim can leave behind, read before it and after it fails: HEAD, the pending mutations (a START left to
    resume, e.g. its push refused), the Work's lifecycle events."""
    return {"head": gitcmd.head_commit(store.root), "events": _work_events(store, work_id),
            "mutations": _pending_mutations(store)}


def _keep_or_forget(store: ProjectStore, record: dict[str, Any], previous: dict[str, Any] | None,
                    before: dict[str, Any], why: str) -> None:
    """A claim that did not leave the Work running: its CLAIMING record is forgotten only when HEAD, the pending
    mutations and the Work's lifecycle are exactly as before it. Anything else - a commit made and its push refused, a
    START mutation left pending, a lifecycle event recorded - keeps the record (CLAIMING), so the Work is never in
    progress without the run that holds it, and the next parallel START of the Work claims it again (the START
    mutation resumes; nothing is recorded twice)."""
    after = _claim_trace(store, record["work_id"])
    left = []
    if after["head"] != before["head"]:
        left.append(f"HEAD moved from {str(before['head'])[:12]} to {str(after['head'])[:12]}")
    if set(after["mutations"]) - set(before["mutations"]):
        left.append(f"pending mutation(s) {', '.join(sorted(set(after['mutations']) - set(before['mutations'])))}")
    if after["events"] != before["events"]:
        left.append(f"{after['events'] - before['events']} lifecycle event(s) of {record['work_id']}")
    if not left:
        _forget(store, record, previous)
        return
    record["claim_error"] = {"error": why[:1000], "left": left, "at": _now()}
    record["next_actor"] = "start"
    _save(store, record)


def accept_project_writes(store: ProjectStore, work_id: str, commits: list[str], note: str) -> dict[str, Any]:
    """A Human (or the CP) accepts, by exact ID, commits a parallel finish stopped on as made by no Workline mutation
    (``run_project_written``), after checking them: the run's next finish does not ask about those commits again.
    Only commits the finish currently finds unproven can be accepted; nothing else of the check is relaxed."""
    if not isinstance(note, str) or not note.strip():
        raise ValidationError("accepting writes needs a note saying who checked them and how", code="run_accept_note")
    with _short_lock(store, {"work_id": work_id, "parallel": True, "accept_writes": True}, 30.0):
        record = read_run(store, work_id)
        if record is None or record.get("state") not in _HOLDING:
            raise StopError(f"no parallel run holds {work_id}", code="run_missing")
        unproven = {item.split(" ", 1)[0][len("commit:"):] for item in _unproven_commits(store, record)
                    if item.startswith("commit:")}
        asked = list(dict.fromkeys(commits))
        if not asked or any(c not in unproven for c in asked):
            raise StopError(f"only commits the finish finds unproven can be accepted: {sorted(unproven) or 'none'}",
                            code="run_accept_unknown_commit")
        accepted = record.setdefault("accepted_writes", {"commits": [], "notes": []})
        accepted["commits"] = sorted(set(accepted["commits"]) | set(asked))
        accepted["notes"].append({"commits": asked, "note": note, "at": _now()})
        _set(store, record, record["state"], take=True)
        return record


def _forget(store: ProjectStore, record: dict[str, Any], previous: dict[str, Any] | None) -> None:
    """Undo the CLAIMING record of a claim that wrote nothing (refused or not running): the previous record returns."""
    if previous is not None:
        _save(store, previous, take=True)
    else:
        with _record_lock(store, record["work_id"]):
            on_disk = read_run(store, record["work_id"])
            if on_disk is not None and on_disk.get("run_id") == record.get("run_id"):
                run_path(store, record["work_id"]).unlink(missing_ok=True)


def _base_drift(store: ProjectStore, record: dict[str, Any]) -> list[str]:
    """Paths the Project changed between the run's base and its integration (``.workline`` aside).

    The finish refuses only a path both changed; a change elsewhere - a header, a
    configuration, a caller - can still interact with the Work's result in ways a
    path comparison cannot see. These paths are what the integrated combination
    was never run against, recorded so a Review or a re-run can look at them.
    """
    ws = record["workspace"]
    base = ws["base_commit"] if ws.get("project_repo") or ws["kind"] == "in_place" else record.get("claim", {}).get("head")
    if not base:
        return []
    out = _git(store.root, "diff", "--name-only", "-z", "--no-renames", base, "HEAD", "--", ".",
               ":(exclude).workline").stdout
    return sorted(set(_z(out)) - set(record.get("outcome", {}).get("result_paths", [])))


def _remote_tip(repo: Path, remote: str, ref: str) -> str | None:
    """What ``remote`` itself says ``refs/heads/<ref>`` is (asked, never taken from a remote-tracking ref)."""
    found = _git(repo, "ls-remote", "--exit-code", remote, f"refs/heads/{ref}")
    if not found.ok:
        return None
    lines = [line.split() for line in found.stdout.splitlines() if line.strip()]
    tips = {fields[0] for fields in lines if len(fields) == 2 and fields[1] == f"refs/heads/{ref}"}
    return tips.pop() if len(tips) == 1 else None


def _integrate_repository(store: ProjectStore, record: dict[str, Any]):
    """Steps 1-5 of :class:`IntegrateSpec` up to the Project commit; a StartResult when refused, else None.

    1. the result descends from the Project's gitlink (a mode-160000 entry at HEAD) and from the target branch;
    2. every check passes before anything is written;
    3. the target branch is fast-forwarded (``update-ref`` with the old value, never forced);
    4. with a remote: the Work branch, then the target branch, are pushed from the run's own worktree - so the
       repository's hooks (a fork guard) see the worktree that made the commit - fast-forward only;
    5. the remote is asked what each ref now is: only the result commit itself counts as reached.
    The Project's pointer moves only after 5 (in the completion, :func:`_move_checkout`).
    """
    from . import start as st

    ws = record["workspace"]
    spec = ws["integrate"]
    repo, result, target = Path(ws["repo"]), record["result_commit"], spec["target_branch"]
    gitlink = spec["gitlink"]
    done = record.setdefault("integration", {}).setdefault("stages", {})
    _recover_checkout_move(store, record)  # F-02: an interrupted move of the checkout is undone before any check

    def refuse(why: str):
        parked = PARKED_REF_PREFIX + record["run_id"]
        _must(repo, "update-ref", parked, result)
        _set(store, record, CONFLICT, conflicts=[why], refs={**record.get("refs", {}), "parked": parked},
             next_actor="human", integration={**record["integration"], "state": "conflict"})
        return st.StartResult("conflict", record["work_id"], record["claim"]["mutation_id"],
                              detail=f"{why}; the result is kept on {parked}", code="run_conflict")

    def ancestor(a: str, b: str) -> bool:
        return _git(repo, "merge-base", "--is-ancestor", a, b).returncode == 0

    pointer = _project_pointer(store, gitlink)
    if pointer is None:
        return refuse(f"{gitlink} is not a gitlink (a mode 160000 entry) at the Project's HEAD")
    checkout = store.root / gitlink
    if not ancestor(pointer, result):
        return refuse(f"the result {result[:12]} does not descend from the Project's pointer {pointer[:12]}")
    old = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{target}").stdout.strip()
    if not old and spec.get("push_remote"):
        # no local branch yet (a fresh clone): the remote's branch, as last fetched, is where it stands
        old = _git(repo, "rev-parse", "--verify", "--quiet",
                   f"refs/remotes/{spec['push_remote']}/{target}").stdout.strip()
    if not old:
        return refuse(f"{target} is not known in {repo.name} (neither a local nor a remote-tracking branch)")
    if not done.get("repository") and not ancestor(old, result):
        return refuse(f"{target} ({old[:12]}) has moved where the result does not follow")
    on = _git(checkout, "symbolic-ref", "--quiet", "HEAD").stdout.strip()
    if on and on != f"refs/heads/{target}":
        return refuse(f"the checkout {gitlink} is on {on}, not detached or on {target}; it is not moved under it")
    if _git(checkout, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        return refuse(f"the checkout {gitlink} has uncommitted changes")
    at = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    # F-02: the identity the decision below rests on; the move re-checks exactly this, under nothing else
    record["integration"]["checkout_seen"] = {"symbolic": on or None, "head": at, "at": _now()}
    if at not in (pointer, result):
        # a checkout holding a commit the Project does not name is someone's state: nothing is written under it
        return refuse(f"the checkout {gitlink} has {at[:12]} out, which the Project does not name ({pointer[:12]}); "
                      "it is not moved under it")
    if gitcmd.changed_against_head(store.root, [p for p in _git(store.root, "ls-files", "--", ".gitmodules").stdout.split()]):
        return refuse(".gitmodules has uncommitted changes")
    if not done.get("repository"):
        # a branch another worktree has out is never moved under it (that worktree would be left behind its branch)
        mine, current, holders = os.path.normcase(str(checkout.resolve())), None, []
        for line in _git(repo, "worktree", "list", "--porcelain").stdout.splitlines():
            if line.startswith("worktree "):
                current = line[len("worktree "):]
            elif line == f"branch refs/heads/{target}" and current is not None \
                    and os.path.normcase(str(Path(current).resolve())) != mine:
                holders.append(current)
        if holders:
            return refuse(f"{target} is checked out in another worktree of {repo.name} ({', '.join(holders)}); "
                          "it is not moved under it")
    if not done.get("repository"):
        # 3. the repository's own branch, fast-forward only; then the remote, before the Project names the commit.
        # A branch the gitlink checkout has out moves with that checkout, inside the completion.
        if on != f"refs/heads/{target}":
            _must(repo, "update-ref", f"refs/heads/{target}", result,
                  *(([old]) if _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{target}").ok else ["0" * 40]))
            # F-02 (r5): a worktree that took the target branch out between the check above and this move holds it at
            # the old commit (its index still is that tree): the move is undone under it and nothing goes further.
            # A worktree that took it out after the move holds the new commit and is consistent; it is left alone.
            stale = [w for w in _target_holders(repo, target, checkout)
                     if _git(Path(w), "--no-optional-locks", "diff", "--cached", "--quiet", "HEAD").returncode != 0]
            if stale:
                _git(repo, "update-ref", f"refs/heads/{target}", old, result)
                record["integration"]["target_taken"] = {"worktrees": stale, "undone": [result, old], "at": _now()}
                _save(store, record)
                raise StopError(f"{target} was taken out by another worktree ({', '.join(stale)}) while it was moved; "
                                "the move is undone and the result kept, the next START checks again",
                                code="run_checkout_changed")
        done["repository"] = {"branch": target, "from": old, "to": result, "at": _now(),
                              "with_checkout": on == f"refs/heads/{target}"}
        _set(store, record, record["state"], integration=record["integration"])
    if spec.get("push_remote") and not done.get("reached"):
        remote = spec["push_remote"]
        here = workspace_path(record) if workspace_path(record).is_dir() else repo
        env = dict(os.environ, **{k: v.format(sha=result) for k, v in spec.get("push_env", [])})
        for ref in (ws["branch"], target):
            if _remote_tip(here, remote, ref) == result:
                continue  # an earlier finish already pushed it
            pushed = gitcmd.run_git(here, "push", remote, f"{result}:refs/heads/{ref}", check=False, env=env)
            if not pushed.ok:
                _set(store, record, EXECUTED, next_actor="human",
                     integration={**record["integration"], "state": "repository_ahead",
                                  "push_error": pushed.stderr.strip()[-400:]})
                raise StopError(f"push of {ref} to {remote} failed; {target} is integrated locally and the "
                                f"Project's pointer is not moved: {pushed.stderr.strip()[-200:]}", code="run_push_failed")
        # 5. reached means: the remote itself names the result commit, for both refs
        seen = {ref: _remote_tip(here, remote, ref) for ref in (ws["branch"], target)}
        if any(tip != result for tip in seen.values()):
            _set(store, record, EXECUTED, next_actor="human",
                 integration={**record["integration"], "state": "repository_unreached", "remote_seen": seen})
            raise StopError(f"{remote} does not name {result[:12]} for {', '.join(r for r, t in seen.items() if t != result)}"
                            f" (it says {seen}); the Project's pointer is not moved", code="run_remote_unreached")
        done["pushed"] = {"remote": remote, "refs": [ws["branch"], target], "at": _now(), "from": str(here)}
        done["reached"] = {"remote": remote, "refs": seen, "at": _now()}
        _set(store, record, record["state"], integration=record["integration"])
    _set(store, record, record["state"], integration={**record["integration"], "state": "repository_integrated"})
    return None


@contextmanager
def _index_lock(gitdir: Path, record: dict[str, Any] | None = None) -> Iterator[Path]:
    """Hold the checkout's own ``index.lock`` the way Git does (exclusive create), released by removing it.

    Every Git command that changes the index - ``checkout`` / ``switch`` of a branch, ``add``, ``commit``, ``reset``,
    ``merge``, ``read-tree`` - takes this same lock first and refuses while it exists ("index.lock: File exists"), so
    while Workline holds it no such command, from a terminal or a GUI, can change the checkout's branch, HEAD or
    index. The holder commits a new index by writing it into the lock file and renaming that over ``index``.

    The lock carries a nonce (run, pid, host, a unique id), recorded in the run's checkout journal (``record``) before
    anything is written, and it keeps that nonce until it is released: the new index is never written into the lock
    (R7-F02-01) but completed as a private index file beside it and renamed over ``index`` while the lock still
    stands. A lock found existing is taken over only when it holds exactly the journal's nonce and the process that
    wrote it is not alive - a lock of any other Git process, or of a Workline process still running, STOPs.
    """
    lock = gitdir / "index.lock"
    journal = (record or {}).get("integration", {}).get("checkout_move") or {}
    nonce = (f"workline-run {(record or {}).get('run_id')} pid {os.getpid()} host {socket.gethostname()} "
             f"id {new_ulid()}")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        try:
            held = lock.read_bytes().decode("utf-8", "replace")
        except OSError:
            held = ""
        if not journal.get("lock_nonce") or held != journal["lock_nonce"]:
            raise StopError(f"{lock} exists: another Git operation is running in the checkout; nothing is moved",
                            code="run_checkout_busy") from exc
        words = held.split()
        owner_pid = int(words[3]) if len(words) > 5 and words[2] == "pid" and words[3].isdigit() else None
        owner_host = words[5] if len(words) > 5 and words[4] == "host" else None
        if owner_host == socket.gethostname() and owner_pid not in (None, os.getpid()) and pid_alive(owner_pid):
            raise StopError(f"{lock} is held by Workline process {owner_pid}, which is still running; nothing is moved",
                            code="run_checkout_busy") from exc
        fd = None  # the lock a dead Workline run of this record left: taken over
        nonce = held
    if fd is not None:
        os.write(fd, nonce.encode("utf-8"))
        os.close(fd)
    try:
        yield lock
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass  # committed: renamed over the index


def _target_holders(repo: Path, target: str, checkout: Path) -> list[str]:
    """The worktrees of ``repo`` other than ``checkout`` that have ``target`` out."""
    mine, current, found = os.path.normcase(str(Path(checkout).resolve())), None, []
    for line in _git(repo, "worktree", "list", "--porcelain").stdout.splitlines():
        if line.startswith("worktree "):
            current = line[len("worktree "):]
        elif line == f"branch refs/heads/{target}" and current is not None \
                and os.path.normcase(str(Path(current).resolve())) != mine:
            found.append(current)
    return found


def _path_blob(checkout: Path, rel: str) -> str | None:
    """The blob ``rel`` would be in ``checkout`` as it is now (Git's own filters applied); None when absent, "?" when
    it is something Workline never writes (a link, a directory)."""
    path = checkout / rel
    if not os.path.lexists(path):
        return None
    if path.is_symlink() or not path.is_file():
        return "?"
    return _must(checkout, "hash-object", "--path", rel, "--", str(path))


def _restore_paths(checkout: Path, paths: list[str], frm: str, to: str) -> list[str]:
    """Put each of ``paths`` from commit ``frm``'s content back to commit ``to``'s, file by file, only where the file
    holds exactly ``frm``'s (Workline's own write) - a file already at ``to`` is left, and a file holding anything
    else (the Human's) is never touched and is returned."""
    untouched = []
    for rel in paths:
        now, before, after = _path_blob(checkout, rel), _blob(checkout, to, rel), _blob(checkout, frm, rel)
        if now == before:
            continue
        if now != after:
            untouched.append(rel)
            continue
        target = checkout / rel
        if before is None:
            target.unlink()
        else:
            data = gitcmd.run_git_bytes(checkout, "cat-file", "--filters", f"{to}:{rel}")
            if data.returncode != 0:
                untouched.append(rel)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data.stdout)
    return untouched


def _move_ref(checkout: Path, symbolic: str | None, new: str, old: str) -> gitcmd.GitResult:
    return gitcmd.run_git(checkout, *(["update-ref", symbolic, new, old] if symbolic is not None
                                      else ["update-ref", "--no-deref", "HEAD", new, old]), check=False)


def _ref_now(checkout: Path, symbolic: str | None) -> str:
    return _git(checkout, "rev-parse", "--verify", "--quiet", symbolic or "HEAD").stdout.strip()


def _undo_move(store: ProjectStore, record: dict[str, Any]) -> None:
    """F-02 (r6 review): put the gitlink checkout back to where the recorded move (``checkout_move``) started.

    Runs under the checkout's index.lock - after an exception in the same process, or by the next START after the
    process died. Git cannot change a ref and the index in one transaction, so the move is recorded durably before
    its first write and undone from that record: the index was never committed (it is the last write), the ref goes
    back by compare-and-swap if it is still the move's, and each file the move wrote goes back only if it still holds
    exactly the move's content. A file holding anything else is the Human's and STOPs the undo with nothing touched;
    the record stays for the next attempt.
    """
    integ = record["integration"]
    move = integ["checkout_move"]
    spec = record["workspace"]["integrate"]
    checkout = store.root / spec["gitlink"]
    old, new, symbolic = move["old"], move["new"], move["symbolic"]
    if move.get("phase") == "index":
        # the index was committed: the move completed; only its end was not recorded
        if _ref_now(checkout, symbolic) == new:
            integ.pop("checkout_move", None)
            integ["stages"]["checkout"] = {"path": spec["gitlink"], "head": new, "at": _now(), "recovered": "completed"}
            _save(store, record)
            return
    index_at_old = _git(checkout, "--no-optional-locks", "diff-index", "--cached", "--quiet", old, "--").returncode == 0
    index_at_new = _git(checkout, "--no-optional-locks", "diff-index", "--cached", "--quiet", new, "--").returncode == 0
    if index_at_new and not index_at_old and _ref_now(checkout, symbolic) == new:
        # the process died after its last write (the index) and before recording it: the move is complete
        integ.pop("checkout_move", None)
        integ["stages"]["checkout"] = {"path": spec["gitlink"], "head": new, "at": _now(), "recovered": "completed"}
        _save(store, record)
        return
    if not index_at_old:
        raise StopError(f"the checkout {spec['gitlink']}'s index is neither where the interrupted move started nor where "
                        "it ended; nothing is changed, the record stays: reconcile required", code="run_checkout_unrecovered")
    ref = _ref_now(checkout, symbolic)
    if ref == new:
        back = _move_ref(checkout, symbolic, old, new)
        if not back.ok:
            raise StopError(f"the move's ref cannot be put back ({back.stderr.strip()[-200:]}); the record stays",
                            code="run_checkout_unrecovered")
    elif ref != old:
        raise StopError(f"{symbolic or 'HEAD'} is at {ref[:12]}, neither the move's start nor its end; nothing is "
                        "changed, the record stays: reconcile required", code="run_checkout_unrecovered")
    untouched = _restore_paths(checkout, list(move["paths"]), new, old)
    if untouched:
        integ["checkout_unrecovered_paths"] = untouched
        _save(store, record)
        raise StopError(f"files changed by someone else since the move began are left as they are ({', '.join(untouched)}); "
                        "the record stays: reconcile required", code="run_checkout_unrecovered")
    integ.pop("checkout_move", None)
    integ.setdefault("checkout_undone", []).append({"old": old, "new": new, "at": _now()})
    _save(store, record)


def _recover_checkout_move(store: ProjectStore, record: dict[str, Any]) -> None:
    """Before anything is checked again: an interrupted move of the gitlink checkout is undone first (F-02)."""
    if not (record.get("integration") or {}).get("checkout_move"):
        return
    checkout = store.root / record["workspace"]["integrate"]["gitlink"]
    gitdir = Path(_must(checkout, "rev-parse", "--absolute-git-dir"))
    with _index_lock(gitdir, record):
        _undo_move(store, record)


def _move_checkout(store: ProjectStore, record: dict[str, Any]) -> None:
    """The completion's own write: the gitlink checkout takes the result (after the remote was reached).

    Under the checkout's index.lock (:func:`_index_lock`), in this order: check (branch HEAD names - the target or
    none - commit, clean, no other worktree on the target); record the move durably (``checkout_move``: start, end,
    branch, the paths it writes, the lock's nonce); working tree by ``read-tree -m -u`` on a private index (it refuses
    before writing anything that would lose local work); ref by compare-and-swap; check again; index committed through
    the lock (the last write). Any exception before the index is committed undoes the move (:func:`_undo_move`); a
    process that dies leaves the record and its lock, and the next START undoes the move before it checks anything.
    The run stays ``executed`` with its result commit throughout; the executor is never run again for this.
    """
    ws = record["workspace"]
    spec = ws["integrate"]
    checkout, result, target = store.root / spec["gitlink"], record["result_commit"], spec["target_branch"]
    seen = record["integration"].get("checkout_seen") or {}
    gitdir = Path(_must(checkout, "rev-parse", "--absolute-git-dir"))
    integ = record["integration"]

    def changed(detail: str, now: dict[str, Any] | None = None) -> StopError:
        integ["checkout_changed"] = {"seen": seen, "now": now, "detail": detail, "at": _now()}
        _save(store, record)
        return StopError(f"the checkout {spec['gitlink']} {detail}; nothing is moved under it",
                         code="run_checkout_changed")

    def head_state() -> tuple[str | None, str]:
        return (_git(checkout, "symbolic-ref", "--quiet", "HEAD").stdout.strip() or None,
                _must(checkout, "rev-parse", "HEAD"))

    with _index_lock(gitdir, record) as lock:
        if integ.get("checkout_move"):
            _undo_move(store, record)
        now_symbolic, now_head = head_state()
        now = {"symbolic": now_symbolic, "head": now_head}
        if now_head == result and now_symbolic == seen.get("symbolic"):
            integ["stages"]["checkout"] = {"path": spec["gitlink"], "head": result, "at": _now()}
            _save(store, record)
            return
        if (now_symbolic, now_head) != (seen.get("symbolic"), seen.get("head")) \
                or now_symbolic not in (None, f"refs/heads/{target}"):
            raise changed(f"changed after the integration check (it was {seen.get('symbolic') or 'detached'} at "
                          f"{str(seen.get('head'))[:12]}, it is {now_symbolic or 'detached'} at {now_head[:12]})", now)
        if _git(checkout, "--no-optional-locks", "status", "--porcelain", "--untracked-files=no").stdout.strip():
            raise changed("has uncommitted changes", now)
        taken = _target_holders(checkout, target, checkout) if now_symbolic is not None else []
        if taken:
            raise changed(f"has {target} out in another worktree ({', '.join(taken)})", now)
        paths = _z(_git(checkout, "diff", "--name-only", "-z", "--no-renames", now_head, result).stdout)
        integ["checkout_move"] = {"old": now_head, "new": result, "symbolic": now_symbolic, "paths": paths,
                                  "phase": "begun", "lock_nonce": lock.read_bytes().decode("utf-8", "replace"),
                                  "at": _now()}
        _save(store, record)  # durable before the first write: a death from here on is undone from it
        private = gitdir / f"workline-index-{record['run_id']}"
        private.write_bytes((gitdir / "index").read_bytes())
        env = dict(os.environ, GIT_INDEX_FILE=str(private))
        try:
            moved = gitcmd.run_git(checkout, "read-tree", "-m", "-u", now_head, result, check=False, env=env)
            if not moved.ok:
                raise changed(f"cannot take the result without overwriting local work ({moved.stderr.strip()[-300:]})",
                              now)
            integ["checkout_move"]["phase"] = "worktree"
            _save(store, record)
            swapped = _move_ref(checkout, now_symbolic, result, now_head)
            if not swapped.ok:
                raise changed(f"ref refused the move ({swapped.stderr.strip()[-200:]})", now)
            integ["checkout_move"]["phase"] = "ref"
            _save(store, record)
            after_symbolic, after_head = head_state()
            moved_away = _target_holders(checkout, target, checkout) if now_symbolic is not None else []
            if (after_symbolic, after_head) != (now_symbolic, result) or moved_away:
                raise changed(f"changed while it was being moved (now {after_symbolic or 'detached'} at {after_head[:12]}"
                              f"{'; ' + target + ' taken by ' + ', '.join(moved_away) if moved_away else ''})",
                              {"symbolic": after_symbolic, "head": after_head})
            # the last write: the completed private index is renamed over ``index`` while the nonce-bearing lock
            # still keeps every Git writer out; the lock is released only after the journal records it (R7-F02-01)
            os.replace(private, gitdir / "index")
            integ["checkout_move"]["phase"] = "index"
            _save(store, record)
        except BaseException:
            if integ.get("checkout_move") and integ["checkout_move"].get("phase") != "index":
                try:
                    _undo_move(store, record)
                except StopError:
                    pass  # the record stays; the next START undoes the move before anything else
            raise
        finally:
            private.unlink(missing_ok=True)
    # the lock is released (above); the completed move is closed in the journal last - a death before this leaves
    # phase "index", which the next START reads as complete
    integ.pop("checkout_move", None)
    integ["stages"]["checkout"] = {"path": spec["gitlink"], "head": result, "at": _now(),
                                   "branch": now_symbolic, "under": "index.lock"}
    _save(store, record)


def use_deps(ctx, identity: dict[str, Any], exclude: tuple[str, ...] = ()) -> Path:
    """For an executor: the read-only deps tree of ``identity`` from its run's deps store, recorded on the run."""
    from . import run_deps

    record = read_run(ctx.store, ctx.work.id)
    store_dir = (record.get("workspace") or {}).get("deps_store")
    if not store_dir:
        raise StopError("this run's WorkspaceSpec names no deps_store", code="deps_store_missing")
    tree = run_deps.acquire(Path(store_dir), identity, record["run_id"], exclude)
    record.setdefault("deps", []).append({"store": store_dir, "key": run_deps.key_of(identity), "identity": identity})
    _save(ctx.store, record)
    return tree


def _drop_deps_users(record: dict[str, Any]) -> None:
    from . import run_deps

    for used in record.get("deps", []):
        run_deps.release_user(Path(used["store"]), used["key"], record["run_id"])


def reopen(store: ProjectStore, work_id: str) -> dict[str, Any]:
    """A conflict-parked run is reopened, explicitly: its workspace is kept and its base becomes the Project's HEAD, so
    the next parallel START runs the executor there again to reconcile, and the finish checks against that base."""
    with _short_lock(store, {"work_id": work_id, "parallel": True, "reopen": True}, 30.0):
        record = read_run(store, work_id)
        if record is None or record["state"] != CONFLICT:
            raise StopError(f"no conflict-parked run of {work_id} to reopen", code="run_not_conflicted")
        ws = record["workspace"]
        record.setdefault("reopened", []).append({"old_base": ws["base_commit"], "conflicts": record.get("conflicts")})
        if ws.get("project_repo"):
            ws["base_commit"] = gitcmd.head_commit(store.root)
        record.pop("integration", None)
        _set(store, record, QUESTION_WAIT, question=f"reconcile {', '.join(record.get('conflicts') or [])} with the "
                                                    "Project's current state in this workspace", next_actor="start",
             outcome={})
        return record


__all__ = ["IntegrateSpec", "LOCK_RETRY_SECONDS", "WorkspaceSpec", "accept_project_writes", "acknowledge_interrupted",
           "declare_owner_gone", "detach_allowed", "list_runs", "note_commit", "owner_state", "pid_alive", "pid_state",
           "read_run", "release", "reopen", "require_run_free", "run", "run_path", "status_projection", "use_deps"]


def status_projection(store: ProjectStore) -> list[dict[str, Any]]:
    """What ``workline status`` shows of the parallel runs: read only, nothing written, no lock taken.

    A run record is runtime state, not the canonical pending mutation: this is a projection of it - which Work a
    run holds, its state and next actor, a Human question it waits on, its owner as far as this host can tell,
    and what an integration recorded (drift, refs, cleanup).
    """
    shown = []
    for record in list_runs(store):
        integration = record.get("integration") or {}
        shown.append({
            "work_id": record.get("work_id"), "run_id": record.get("run_id"), "state": record.get("state"),
            "holds_work": record.get("state") in _HOLDING, "next_actor": record.get("next_actor"),
            "question": record.get("question") if record.get("state") == QUESTION_WAIT else None,
            "owner": {"pid": record.get("pid"), "host": record.get("host"),
                      "state": owner_state(record) if record.get("state") in _LIVE else None},
            "integration": {"state": integration.get("state"), "base_drift": integration.get("base_drift"),
                            "near_result": (integration.get("drift") or {}).get("near_result")},
            "conflicts": record.get("conflicts"), "unknown": record.get("unknown"),
            "refs": record.get("refs"), "cleanup": (record.get("cleanup") or {}).get("state"),
        })
    return shown
