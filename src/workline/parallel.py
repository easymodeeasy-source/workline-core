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

from contextlib import contextmanager
from dataclasses import dataclass
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time
from typing import Any, Iterator

from . import gitcmd
from .durable import durable_write_text
from .errors import ProjectOperationBusy, StopError, ValidationError
from .ids import new_ulid
from .oplock import project_operation
from .store import ProjectStore

RUN_MARKER = "workline-parallel-run"
RUN_VERSION = 1
RUNS_DIR = ".workline/runtime/runs"
SAVED_REF_PREFIX = "refs/workline/runs/"
PARKED_REF_PREFIX = "refs/workline/parked/"
BRANCH_PREFIX = "workline/run/"

# run states ---------------------------------------------------------------
CLAIMING = "claiming"          # recorded before the claim is made: a claim interrupted at any point is found
CREATING = "creating"          # claim committed, workspace being made
RUNNING = "running"            # executor running (owner pid)
QUESTION_WAIT = "question_wait"
EXECUTED = "executed"          # Completed recorded, finish not yet done
FAILED = "failed"              # executor raised; workspace kept
CONFLICT = "conflict"          # parked: the result conflicts with the Project
PARKED = "parked"              # result kept on a saved ref for a later integration
RELEASING = "releasing"        # integrated; workspace being released
CLEANUP_FAILED = "cleanup_failed"
RELEASED = "released"

#: states in which the run owns its Work: no other START of that Work may run it
_HOLDING = {CLAIMING, CREATING, RUNNING, QUESTION_WAIT, EXECUTED, FAILED, CONFLICT}
#: states a live owner process is working in: a second START of the Work is refused while it lives
_LIVE = {CLAIMING, CREATING, RUNNING, EXECUTED}
#: states a later parallel START of the same Work picks up again
_RESUMABLE = {CREATING, RUNNING, QUESTION_WAIT, FAILED}

_tokens: dict[tuple[str, str], str] = {}


def _key(store: ProjectStore, work_id: str) -> tuple[str, str]:
    return (os.path.normcase(str(store.root.resolve())), work_id)


@contextmanager
def _token(store: ProjectStore, work_id: str, run_id: str) -> Iterator[None]:
    _tokens[_key(store, work_id)] = run_id
    try:
        yield
    finally:
        _tokens.pop(_key(store, work_id), None)


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


def _save(store: ProjectStore, record: dict[str, Any]) -> None:
    record["updated_at"] = _now()
    folder = _runs_dir(store)
    folder.mkdir(parents=True, exist_ok=True)
    store.tmp.mkdir(parents=True, exist_ok=True)
    durable_write_text(run_path(store, record["work_id"]),
                       json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", tmp_dir=store.tmp)


def _set(store: ProjectStore, record: dict[str, Any], state: str, **fields: Any) -> None:
    record["state"] = state
    record.update(fields)
    record.setdefault("history", []).append({"state": state, "at": _now(), "pid": os.getpid()})
    _save(store, record)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def pid_alive(pid: object) -> bool:
    """Whether process ``pid`` runs on this host; never signals it."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _owner_alive(record: dict[str, Any]) -> bool:
    return record.get("host") == socket.gethostname() and pid_alive(record.get("pid"))


def require_run_free(store: ProjectStore, work_id: str) -> None:
    """STOP unless no parallel run owns ``work_id`` - or this call is that run's own claim or finish.

    START asks this before it runs any Work, so neither an ordinary START, an
    outer continuation nor a second parallel START runs a Work another run
    holds (a double start).
    """
    record = read_run(store, work_id)
    if record is None or record.get("state") not in _HOLDING:
        return
    if _tokens.get(_key(store, work_id)) == record.get("run_id"):
        return
    raise StopError(
        f"Work {work_id} is held by parallel run {record.get('run_id')} ({record.get('state')}, pid "
        f"{record.get('pid')}); it is continued only by a parallel START of the same Work, nothing was begun",
        code="work_run_active",
    )


# --------------------------------------------------------------------------- the short locked sections

@contextmanager
def _short_lock(store: ProjectStore, details: dict[str, Any], wait: float) -> Iterator[None]:
    """The Project execution lock for one short canonical section, waiting up to ``wait`` seconds for it."""
    deadline = time.monotonic() + wait
    while True:
        try:
            with project_operation(store, "start", details):
                yield
            return
        except ProjectOperationBusy:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)


# --------------------------------------------------------------------------- workspace

@dataclass(frozen=True)
class WorkspaceSpec:
    """Where a parallel Work runs.

    ``kind`` "worktree" (default) makes a git worktree of ``repo`` (the Project
    itself when None) on a Work branch; "in_place" runs in the Project folder,
    for a Work that only reads and records. ``regenerable`` are glob patterns
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
        record["workspace"] = {"kind": "in_place", "path": str(store.root), "repo": str(store.root),
                               "base_commit": gitcmd.head_commit(store.root)}
        return
    if spec.kind != "worktree":
        raise ValidationError(f"workspace kind must be worktree or in_place: {spec.kind!r}", code="run_workspace_kind")
    repo = Path(spec.repo or store.root).resolve()
    base_root = Path(spec.root) if spec.root else store.root.parent / f"{store.root.name}.workline-runs"
    path = (base_root / record["run_id"]).resolve()
    branch = f"{spec.branch_prefix}{record['work_id'].lower()}-{record['run_id'][-8:].lower()}"
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
    staged = _git(ws, "diff", "--cached", "--name-only").stdout.split()
    if not staged:
        return _must(ws, "rev-parse", "HEAD")
    _must(ws, "commit", "--quiet", "-m", message)
    return _must(ws, "rev-parse", "HEAD")


def _conflicts(store: ProjectStore, record: dict[str, Any], paths: list[str], deleted: list[str]) -> list[str]:
    """Result paths the Project changed since the run's base in a way the run's result does not match."""
    ws = record["workspace"]
    base = ws["base_commit"]
    head = gitcmd.head_commit(store.root)
    found = []
    for p in sorted(set(paths) | set(deleted)):
        before = _blob(store.root, base, p)
        now = _blob(store.root, head, p)
        mine = None if p in deleted else _file_blob(store.root, p, workspace_path(record) / p)
        if now != before and mine != now:
            found.append(p)
        elif gitcmd.changed_against_head(store.root, [p]) and _file_blob(store.root, p, store.root / p) != mine:
            found.append(p)  # someone's uncommitted change in the Project folder
    return found


def _copy_results(store: ProjectStore, record: dict[str, Any], paths: list[str], deleted: list[str]) -> None:
    ws = workspace_path(record)
    for p in paths:
        target = store.root / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ws / p).read_bytes())
    for p in deleted:
        target = store.root / p
        if target.exists():
            target.unlink()


def _set_aside(store: ProjectStore, record: dict[str, Any], paths: list[str], deleted: list[str]) -> Path:
    stash = _runs_dir(store) / record["run_id"] / "results"
    head = gitcmd.head_commit(store.root)
    for p in paths:
        target = stash / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((store.root / p).read_bytes())
    for p in paths + deleted:
        before = gitcmd.run_git_bytes(store.root, "show", f"{head}:{p}")
        if before.returncode == 0:
            (store.root / p).write_bytes(before.stdout)
        elif (store.root / p).exists():
            (store.root / p).unlink()
    return stash


def _put_back(store: ProjectStore, stash: Path, paths: list[str], deleted: list[str]) -> None:
    for p in paths:
        (store.root / p).parent.mkdir(parents=True, exist_ok=True)
        (store.root / p).write_bytes((stash / p).read_bytes())
    for p in deleted:
        if (store.root / p).exists():
            (store.root / p).unlink()


# --------------------------------------------------------------------------- release

def _ignored_and_dirty(ws: Path) -> tuple[list[str], list[str]]:
    out = _git(ws, "status", "--porcelain=v1", "--ignored", "--untracked-files=all", "-z").stdout
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
    record = read_run(store, work_id)
    if record is None:
        raise StopError(f"no parallel run for {work_id}", code="run_missing")
    if record["state"] == RELEASED:
        return record
    if record["state"] not in (RELEASING, CLEANUP_FAILED, PARKED):
        raise StopError(f"run {record['run_id']} is {record['state']}; only a finished run is released",
                        code="run_not_finished")
    ws = record.get("workspace") or {}
    if ws.get("kind") != "worktree":
        import shutil

        stash = _runs_dir(store) / record["run_id"]
        removed = []
        if stash.is_dir():
            shutil.rmtree(stash)  # the set-aside copies of results the completion has committed
            removed.append(f"{RUNS_DIR}/{record['run_id']}")
        _set(store, record, RELEASED, cleanup={"state": "released", "removed": removed})
        return record
    path, repo = Path(ws["path"]), Path(ws["repo"])
    try:
        blocked = []
        removed: list[str] = []
        integrated_now = record.get("integration", {}).get("state") == "integrated"
        if path.exists() and not integrated_now:
            # what a held / cancelled / stopped run leaves uncommitted is its work in progress: kept as a commit
            # on the Work branch (and so on the parked ref below), never discarded with the worktree
            _git(path, "add", "-A")
            if _git(path, "diff", "--cached", "--quiet").returncode != 0:
                _must(path, "commit", "--quiet", "-m", f"workline: work in progress of {record['work_id']} "
                                                        f"(run {record['run_id']}, parked)")
                record["wip_commit"] = _must(path, "rev-parse", "HEAD")
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
        selectors: tuple = (None, None), lock_wait: float = 120.0):
    """One parallel START of ``work_id`` (see the module docstring); returns a ``start.StartResult``."""
    from . import start as st

    if mode != "single-work" or any(selector is not None for selector in selectors):
        raise ValidationError("a parallel START runs one named Work (mode single-work) without a Review selector",
                              code="parallel_start_shape")

    spec = spec or WorkspaceSpec()
    details = {"work_id": work_id, "mode": "single-work", "parallel": True}
    timings: dict[str, float] = {}

    # 1. claim ------------------------------------------------------------
    t0 = time.perf_counter()
    with _short_lock(store, details, lock_wait):
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
        if record is not None and record["state"] == CLAIMING and not _owner_alive(record):
            record = None  # its claim was interrupted: the claim below is made again (the START mutation resumes)
        if record is not None:
            if record["state"] in _LIVE and _owner_alive(record):
                raise StopError(f"Work {work_id} is already running in parallel run {record['run_id']} "
                                f"(pid {record.get('pid')}); nothing was begun", code="work_run_active")
            if record["state"] == CONFLICT:
                raise StopError(f"run {record['run_id']} of {work_id} is parked on a conflict "
                                f"({', '.join(record.get('conflicts', []))}); integrate it first", code="run_conflict_parked")
            if record["state"] == CREATING and not Path(record.get("workspace", {}).get("path", "")).exists():
                with _token(store, work_id, record["run_id"]):
                    _create_workspace(store, record, spec)
        else:
            record = {"workline": RUN_MARKER, "version": RUN_VERSION, "run_id": f"run_{new_ulid()}",
                      "work_id": work_id, "created_at": _now(), "host": socket.gethostname(), "pid": os.getpid()}
            if resume_parked is not None:
                record["resumed_from"] = {"run_id": resume_parked["run_id"], "ref": resume_parked["refs"]["parked"]}
            previous = read_run(store, work_id)
            if previous is not None:
                record["previous_runs"] = previous.get("previous_runs", []) + [
                    {k: previous.get(k) for k in ("run_id", "state", "result_commit", "refs", "integration")}]
            _set(store, record, CLAIMING)  # before the claim: a claim interrupted after its commit is still found
            try:
                with _token(store, work_id, record["run_id"]):
                    claimed = st._start_locked(store, work_id, "single-work", lambda ctx: st.Detach())
            except BaseException:
                _forget(store, record, previous)
                raise
            if claimed.status != "running":
                _forget(store, record, previous)
                return claimed
            _set(store, record, CREATING, claim={"mutation_id": claimed.mutation_id, "head": claimed.head})
            if resume_parked is not None:
                old = resume_parked["workspace"]
                kept = _must(Path(old["repo"]), "rev-parse", resume_parked["refs"]["parked"])
                _create_workspace(store, record, spec, start_at=kept, base=old["base_commit"])
            else:
                _create_workspace(store, record, spec)
        if record["state"] == EXECUTED:
            _set(store, record, EXECUTED, pid=os.getpid(), host=socket.gethostname())
        else:
            _set(store, record, RUNNING, pid=os.getpid(), host=socket.gethostname())
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
            with _short_lock(store, details, lock_wait):
                result = _finish(store, record, outcome)
        except BaseException as exc:
            # the finish stopped: what the run recorded (its result, the integration stages) stays; the next
            # parallel START of the Work continues the finish from there
            latest = read_run(store, work_id) or record
            latest["finish_error"] = f"{type(exc).__name__}: {exc}"[:1000]
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
                                    result.phase_id, f"cleanup {released['state']}: {released.get('cleanup')}",
                                    result.head, code="run_cleanup_incomplete")
    timings["release_s"] = time.perf_counter() - t3
    final = read_run(store, work_id)
    final["timings"] = timings
    _save(store, final)
    return result


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
    if isinstance(outcome, st.Completed):
        paths = [p.replace("\\", "/") for p in outcome.result_paths]
        deleted = [p.replace("\\", "/") for p in outcome.deleted_paths]
        _check_result_paths(paths + deleted)
        commit = None
        if record["workspace"]["kind"] == "worktree":
            message = (outcome.message or f"work({work.display}): result").strip()
            commit = _commit_in_workspace(record, paths, deleted, message)
        _set(store, record, EXECUTED, result_commit=commit,
             outcome={"kind": "completed", "result_paths": paths, "deleted_paths": deleted, "message": outcome.message})
    return outcome


def _finish(store: ProjectStore, record: dict[str, Any], outcome):
    from . import start as st

    work_id = record["work_id"]
    with _token(store, work_id, record["run_id"]):
        ws = record["workspace"]
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
                pointer = st.Completed((ws["integrate"]["gitlink"],), outcome.message)
                calls = {"n": 0}

                def finishing(ctx):
                    calls["n"] += 1
                    if calls["n"] > 1:
                        return st.Detach()
                    _move_checkout(store, record)
                    return pointer
        if isinstance(outcome, st.Completed) and ws["kind"] == "worktree" and ws.get("integrate") \
                and not ws.get("project_repo"):
            pass  # finishing is set above
        elif isinstance(outcome, st.Completed) and ws["kind"] == "in_place":
            # in place: the executor wrote straight into the Project folder. Its results are set aside and the paths
            # put back to HEAD under this lock, so the ordinary completion sees them written by its own cycle
            paths = list(record["outcome"]["result_paths"])
            deleted = list(record["outcome"]["deleted_paths"])
            stash = _set_aside(store, record, paths, deleted)
            calls = {"n": 0}

            def finishing(ctx):
                calls["n"] += 1
                if calls["n"] > 1:
                    return st.Detach()
                _put_back(store, stash, paths, deleted)
                return outcome
        elif isinstance(outcome, st.Completed) and ws["kind"] == "worktree" and ws.get("project_repo"):
            paths = list(record["outcome"]["result_paths"])
            deleted = list(record["outcome"]["deleted_paths"])
            conflicts = _conflicts(store, record, paths, deleted)
            if conflicts:
                parked = PARKED_REF_PREFIX + record["run_id"]
                _must(Path(record["workspace"]["repo"]), "update-ref", parked, record["result_commit"])
                _set(store, record, CONFLICT, conflicts=conflicts, refs={"parked": parked}, next_actor="human",
                     integration={"state": "conflict", "target": gitcmd.current_branch_ref(store.root)})
                return st.StartResult("conflict", work_id, record["claim"]["mutation_id"],
                                      detail=f"result conflicts with the Project at {', '.join(conflicts)}; "
                                             f"kept on {parked}", code="run_conflict")
            calls = {"n": 0}

            def finishing(ctx):
                calls["n"] += 1
                if calls["n"] > 1:
                    return st.Detach()
                _copy_results(store, record, paths, deleted)
                return outcome
        else:
            calls = {"n": 0}

            def finishing(ctx):
                calls["n"] += 1
                return outcome if calls["n"] == 1 else st.Detach()

        drift = _base_drift(store, record)  # what the Project changed since the base, before this finish commits
        _set(store, record, record["state"], finishing_at=_now())
        result = st._start_locked(store, work_id, "single-work", finishing)
        if result.status == "running":
            _set(store, record, RUNNING, outcome={})
            return result
        if result.status == "completed" and record.get("integration_pending"):
            _set(store, record, RELEASING, integration={"state": "pending", **record["integration_pending"],
                                                        "work_commit": gitcmd.head_commit(store.root)},
                 next_actor="integration")
        elif result.status == "completed":
            _set(store, record, RELEASING, integration={**record.get("integration", {}), "state": "integrated",
                                                        "target": gitcmd.current_branch_ref(store.root),
                                                        "commit": gitcmd.head_commit(store.root),
                                                        "finish_mutation_id": result.mutation_id,
                                                        "base_drift": drift},
                 next_actor="workline")
        else:
            # held, cancelled, moved, stopped: the Work's own outcome ends this run; what the workspace holds is
            # kept on a parked ref by the release when it is not integrated
            _set(store, record, RELEASING, integration={**record.get("integration", {}), "state": result.status},
                 next_actor="workline")
        return result


def _forget(store: ProjectStore, record: dict[str, Any], previous: dict[str, Any] | None) -> None:
    """Undo the CLAIMING record of a claim that wrote nothing (refused or not running): the previous record returns."""
    if previous is not None:
        _save(store, previous)
    else:
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
    out = _git(store.root, "diff", "--name-only", base, "HEAD", "--", ".", ":(exclude).workline").stdout
    return sorted(set(out.split()) - set(record.get("outcome", {}).get("result_paths", [])))


def _integrate_repository(store: ProjectStore, record: dict[str, Any]):
    """Steps 1-3 of :class:`IntegrateSpec` up to the Project commit; a StartResult when refused, else None."""
    from . import start as st

    ws = record["workspace"]
    spec = ws["integrate"]
    repo, result, target = Path(ws["repo"]), record["result_commit"], spec["target_branch"]
    gitlink = spec["gitlink"]
    done = record.setdefault("integration", {}).setdefault("stages", {})

    def refuse(why: str):
        parked = PARKED_REF_PREFIX + record["run_id"]
        _must(repo, "update-ref", parked, result)
        _set(store, record, CONFLICT, conflicts=[why], refs={**record.get("refs", {}), "parked": parked},
             next_actor="human", integration={**record["integration"], "state": "conflict"})
        return st.StartResult("conflict", record["work_id"], record["claim"]["mutation_id"],
                              detail=f"{why}; the result is kept on {parked}", code="run_conflict")

    def ancestor(a: str, b: str) -> bool:
        return _git(repo, "merge-base", "--is-ancestor", a, b).returncode == 0

    pointer = _blob(store.root, "HEAD", gitlink)
    checkout = store.root / gitlink
    if pointer is None:
        return refuse(f"{gitlink} is not a gitlink at the Project's HEAD")
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
    if gitcmd.changed_against_head(store.root, [p for p in _git(store.root, "ls-files", "--", ".gitmodules").stdout.split()]):
        return refuse(".gitmodules has uncommitted changes")
    if not done.get("repository"):
        # 2. the repository's own branch, fast-forward only; then the remote, before the Project names the commit.
        # A branch the gitlink checkout has out moves with that checkout, inside the completion (step 3).
        if on != f"refs/heads/{target}":
            _must(repo, "update-ref", f"refs/heads/{target}", result,
                  *(([old]) if _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{target}").ok else ["0" * 40]))
        done["repository"] = {"branch": target, "from": old, "to": result, "at": _now(),
                              "with_checkout": on == f"refs/heads/{target}"}
        _set(store, record, record["state"], integration=record["integration"])
    if spec.get("push_remote") and not done.get("pushed"):
        env = dict(os.environ, **{k: v.format(sha=result) for k, v in spec.get("push_env", [])})
        for ref in (ws["branch"], target):
            pushed = gitcmd.run_git(repo, "push", spec["push_remote"], f"{result}:refs/heads/{ref}", check=False, env=env)
            if not pushed.ok:
                _set(store, record, EXECUTED, next_actor="human",
                     integration={**record["integration"], "state": "repository_ahead",
                                  "push_error": pushed.stderr.strip()[-400:]})
                raise StopError(f"push of {ref} to {spec['push_remote']} failed; {target} is integrated locally and the "
                                f"Project's pointer is not moved: {pushed.stderr.strip()[-200:]}", code="run_push_failed")
        done["pushed"] = {"remote": spec["push_remote"], "refs": [ws["branch"], target], "at": _now()}
        _set(store, record, record["state"], integration=record["integration"])
    _set(store, record, record["state"], integration={**record["integration"], "state": "repository_integrated"})
    return None


def _move_checkout(store: ProjectStore, record: dict[str, Any]) -> None:
    """Step 3 of :class:`IntegrateSpec`, run as the completion's own write: the gitlink checkout takes the result."""
    ws = record["workspace"]
    checkout, result = store.root / ws["integrate"]["gitlink"], record["result_commit"]
    if _must(checkout, "rev-parse", "HEAD") != result:
        if _git(checkout, "symbolic-ref", "--quiet", "HEAD").stdout.strip():
            _must(checkout, "merge", "--ff-only", "--quiet", result)
        else:
            _must(checkout, "checkout", "--quiet", "--detach", result)
    record["integration"]["stages"]["checkout"] = {"path": ws["integrate"]["gitlink"], "head": result, "at": _now()}
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


__all__ = ["IntegrateSpec", "WorkspaceSpec", "list_runs", "pid_alive", "read_run", "release", "reopen",
           "require_run_free", "run", "run_path", "use_deps"]
