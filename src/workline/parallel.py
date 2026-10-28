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
_HOLDING = {CREATING, RUNNING, QUESTION_WAIT, EXECUTED, FAILED, CONFLICT}
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


def _git(repo: Path, *args: str) -> gitcmd.GitResult:
    return gitcmd.run_git(repo, *args, check=False)


def _must(repo: Path, *args: str) -> str:
    result = _git(repo, *args)
    if not result.ok:
        raise StopError(f"git {' '.join(args)} failed in {repo}: {result.stderr.strip()}", code="run_git_failed")
    return result.stdout.strip()


def _create_workspace(store: ProjectStore, record: dict[str, Any], spec: WorkspaceSpec) -> None:
    if spec.kind == "in_place":
        record["workspace"] = {"kind": "in_place", "path": str(store.root), "repo": str(store.root),
                               "base_commit": gitcmd.head_commit(store.root)}
        return
    if spec.kind != "worktree":
        raise ValidationError(f"workspace kind must be worktree or in_place: {spec.kind!r}", code="run_workspace_kind")
    repo = Path(spec.repo or store.root).resolve()
    base_root = Path(spec.root) if spec.root else store.root.parent / f"{store.root.name}.workline-runs"
    path = (base_root / record["run_id"]).resolve()
    branch = f"{BRANCH_PREFIX}{record['work_id'].lower()}-{record['run_id'][-8:].lower()}"
    base = _must(repo, "rev-parse", "HEAD")
    record["workspace"] = {"kind": "worktree", "repo": str(repo), "path": str(path), "branch": branch,
                           "base_commit": base, "project_repo": os.path.normcase(str(repo)) == os.path.normcase(str(store.root.resolve())),
                           "regenerable": list(spec.regenerable)}
    _save(store, record)  # where it will be, before it exists: an interrupted creation is found and cleaned
    base_root.mkdir(parents=True, exist_ok=True)
    _must(repo, "worktree", "add", "-b", branch, str(path), base)


def workspace_path(record: dict[str, Any]) -> Path:
    return Path(record["workspace"]["path"])


# --------------------------------------------------------------------------- results in the workspace

def _blob(repo: Path, commit: str, path: str) -> str | None:
    result = _git(repo, "rev-parse", "--verify", "--quiet", f"{commit}:{path}")
    return result.stdout.strip() if result.ok else None


def _file_blob(path: Path) -> str | None:
    if not path.is_file():
        return None
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


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
    _must(ws, "commit", "--quiet", "--no-verify", "-m", message)
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
        mine = None if p in deleted else _file_blob(workspace_path(record) / p)
        if now != before and mine != now:
            found.append(p)
        elif gitcmd.changed_against_head(store.root, [p]):
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
        if tip and (integrated or tip == ws["base_commit"]):
            _must(repo, "branch", "-D", ws["branch"])  # its commit stays on the saved ref
        final = RELEASED if integrated or not tip or tip == ws["base_commit"] else PARKED
        _set(store, record, final, cleanup={"state": "released", "removed": removed},
             next_actor=None if final == RELEASED else "integration")
        return record
    except (StopError, OSError) as exc:
        _set(store, record, CLEANUP_FAILED, cleanup={"state": "error", "blocked": [str(exc)]}, next_actor="human")
        return record


# --------------------------------------------------------------------------- the parallel START

def run(store: ProjectStore, work_id: str, executor, spec: WorkspaceSpec | None = None, *, lock_wait: float = 120.0):
    """One parallel START of ``work_id`` (see the module docstring); returns a ``start.StartResult``."""
    from . import start as st

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
        if record is not None and record["state"] in (RELEASED, PARKED):
            record = None  # a finished run: a new START of the Work (if it is still startable) is a new run
        if record is not None:
            if record["state"] in (RUNNING, CREATING) and _owner_alive(record):
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
            with _token(store, work_id, record["run_id"]):
                claimed = st._start_locked(store, work_id, "single-work", lambda ctx: st.Detach())
            if claimed.status != "running":
                return claimed
            _set(store, record, CREATING, claim={"mutation_id": claimed.mutation_id, "head": claimed.head})
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
        with _short_lock(store, details, lock_wait):
            result = _finish(store, record, outcome)
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
            # another repository (a Solver worktree, approach S): its result is the commit on the Work branch. The
            # Work completes in the Project with that commit named; the commit itself waits, on its saved and parked
            # refs, for the integration into that repository's own branch - Workline does not merge it.
            note = (f"run {record['run_id']}: result commit {record['result_commit']} on {ws['branch']} "
                    f"in {Path(ws['repo']).name} (integration pending)")
            message = ((outcome.message or "").strip() + "\n\n" + note).strip()
            outcome = st.Completed((), message)
            record["integration_pending"] = {"repo": ws["repo"], "branch": ws["branch"], "commit": record["result_commit"]}
        if isinstance(outcome, st.Completed) and ws["kind"] == "in_place":
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
            _set(store, record, RELEASING, integration={"state": "integrated",
                                                        "target": gitcmd.current_branch_ref(store.root),
                                                        "commit": gitcmd.head_commit(store.root),
                                                        "finish_mutation_id": result.mutation_id},
                 next_actor="workline")
        else:
            # held, cancelled, moved, stopped: the Work's own outcome ends this run; what the workspace holds is
            # kept on a parked ref by the release when it is not integrated
            _set(store, record, RELEASING, integration={"state": result.status}, next_actor="workline")
        return result


__all__ = ["WorkspaceSpec", "list_runs", "pid_alive", "read_run", "release", "require_run_free", "run", "run_path"]
