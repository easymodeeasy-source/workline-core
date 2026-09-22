"""Shared fixtures for the review-v1 planning (P2) tests: fixture Projects, scripted reviewers, crash points.

Every Project here is a real Workline Project (``helpers.WorklineTestCase``)
whose root ``.gitattributes`` carries the canonical Review-attribute rule as
its last attribute rule, committed by the test itself - Workline never writes
it. Nothing here shortcuts production code: the flows run through
``create_roadmap`` / ``enter_phase`` with ``review=PlanningReview(...)``.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import itertools
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Iterator
from unittest import mock

from helpers import WorklineTestCase, git
from workline import gitcmd, ids
from workline import roadmap as rm
from workline import roadmap_review as rr
from workline.mutation import MutationController
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.review import paths as review_paths
from workline.review import planning, publication, records, serialize
from workline.review.planning import PlanningReview, PlanningReviewFinding, PlanningReviewReport
from workline.review.store import ReviewStore
from workline.store import ProjectStore

CANONICAL_RULE = ".workline/review/** !text eol=lf -filter -ident -working-tree-encoding"


class Crash(Exception):
    """A simulated process death: not a StopError, so nothing is abandoned on its way out."""


class Reviewer:
    """A scripted synchronous reviewer that records every task it receives."""

    def __init__(
        self,
        status: str = "completed",
        findings: tuple[PlanningReviewFinding, ...] = (),
        *,
        identity: str = "test-reviewer",
        version: str = "1",
        raises: BaseException | None = None,
        returns: Any = None,
    ) -> None:
        self.status = status
        self.findings = findings
        self.identity = identity
        self.version = version
        self.raises = raises
        self.returns = returns
        self.tasks: list[Any] = []

    def __call__(self, task: Any) -> Any:
        self.tasks.append(task)
        if self.raises is not None:
            raise self.raises
        if self.returns is not None:
            return self.returns(task) if callable(self.returns) else self.returns
        return PlanningReviewReport(task.task_id, self.identity, self.version, self.status, tuple(self.findings))

    def review(self) -> PlanningReview:
        return PlanningReview(self, self.identity, self.version)


def plan(name: str = "Planned Roadmap", *, relations: bool = True, scope: str | None = None) -> rm.RoadmapPlan:
    return rm.RoadmapPlan(
        name,
        "計画の背景",
        "達成したい状態",
        {"a": PhaseSpec("Phase A", "A が成立する"), "b": PhaseSpec("Phase B", "B が成立する")},
        (PhaseRelationSpec("planned_next", "a", "b"),) if relations else (),
        scope=scope,
    )


def design(
    *,
    works: dict[str, str] | None = None,
    related: dict[str, tuple] | None = None,
    confirmation: bool = True,
    planned_next: tuple = (("w1", "w2"),),
    requires_completion: tuple = (),
    entry: str | None = None,
    integration_related: tuple = (),
) -> rm.PhaseEntryDesign:
    works = works if works is not None else {"w1": "W1 が成立する", "w2": "W2 が成立する"}
    related = related or {}
    return rm.PhaseEntryDesign(
        {key: rm.WorkDesign(key.upper(), desired, tuple(related.get(key, ()))) for key, desired in works.items()},
        rm.WorkDesign("Integration", "全Workの統合確認が取れている", tuple(integration_related)),
        rm.WorkDesign("Confirmation", "人間が成果を確認した") if confirmation else None,
        planned_next=planned_next,
        requires_completion=requires_completion,
        entry=entry,
    )


def condition(first: str = "pattern") -> dict[str, Any]:
    """A path_glob condition built in either key insertion order."""
    if first == "pattern":
        return {"pattern": "src/*.py", "kind": "path_glob"}
    return {"kind": "path_glob", "pattern": "src/*.py"}


class PlanningTestCase(WorklineTestCase):
    """A Workline test case with review-v1 planning fixtures."""

    def setUp(self) -> None:
        super().setUp()
        gitcmd.forget_object_answers()

    # projects --------------------------------------------------------------
    def planning_project(
        self, name: str = "proj", *, remote: bool = False, attributes: str | None = None
    ) -> ProjectStore:
        """A Project whose root ``.gitattributes`` ends with the canonical rule, committed (and pushed)."""
        store = self.new_project(name, remote=remote)
        text = attributes if attributes is not None else "* text=auto\n" + CANONICAL_RULE + "\n"
        self.commit_attributes(store, text)
        if remote:
            git(store.root, "push", "origin", "main")
        return store

    def commit_attributes(self, store: ProjectStore, text: str | bytes, *, message: str = "attributes") -> None:
        target = store.root / ".gitattributes"
        if isinstance(text, bytes):
            target.write_bytes(text)
        else:
            target.write_text(text, encoding="utf-8", newline="\n")
        git(store.root, "add", ".gitattributes")
        git(store.root, "commit", "-m", message)

    def commit_all(self, store: ProjectStore, message: str, *paths: str) -> str:
        git(store.root, "add", "--", *(paths or (".",)))
        git(store.root, "commit", "-m", message)
        return self.head(store)

    # flows -----------------------------------------------------------------
    def reviewed_roadmap(self, store: ProjectStore, reviewer: Reviewer | None = None, the_plan: rm.RoadmapPlan | None = None):
        return rm.create_roadmap(store, the_plan or plan(), review=(reviewer or Reviewer()).review())

    def reviewed_entry(self, store: ProjectStore, phase_id: str, reviewer: Reviewer | None = None, the_design=None):
        return rm.enter_phase(store, phase_id, the_design or design(), review=(reviewer or Reviewer()).review())

    def roadmap_and_phase(self, store: ProjectStore, *, reviewed: bool = False) -> tuple[str, str]:
        """A Roadmap with Phases a -> b; returns (roadmap_id, phase a)."""
        if reviewed:
            result = self.reviewed_roadmap(store)
            return result.registration.roadmap_id, result.registration.phase_ids["a"]
        result = rm.create_roadmap(store, plan())
        return result.roadmap_id, result.phase_ids["a"]

    # reading -----------------------------------------------------------------
    def head(self, store: ProjectStore) -> str:
        return gitcmd.head_commit(store.root) or ""

    def subjects(self, store: ProjectStore, count: int = 30) -> list[str]:
        return git(store.root, "log", f"-{count}", "--format=%s").splitlines()

    def pending(self, store: ProjectStore) -> list[dict[str, Any]]:
        return MutationController(store).list_pending()

    def chain(self, store: ProjectStore, run_id: str):
        return ReviewStore(store).gate_chain(run_id)

    def runtime_gone(self, store: ProjectStore) -> None:
        """Runtime loss: ``.workline/runtime/**`` removed."""
        shutil.rmtree(store.root / ".workline" / "runtime")

    def remote_head(self, name: str = "proj") -> str | None:
        found = git(self.tmp, "--git-dir", str(self.remote_path(name)), "rev-parse", "--verify", "--quiet", "refs/heads/main", check=False)
        return found.strip() or None

    def fresh_clone(self, source: Path, name: str, *config: str) -> ProjectStore:
        """A normal new clone of ``source`` (its committed attributes as the only in-tree source)."""
        target = self.tmp / name
        args = []
        for item in config:
            args += ["-c", item]
        git(self.tmp, *args, "clone", "-q", str(source), str(target))
        return ProjectStore(target)

    def snapshot_state(self, store: ProjectStore) -> dict[str, bytes]:
        """Every file under ``.workline`` (runtime included), for byte-for-byte before/after comparisons."""
        found: dict[str, bytes] = {}
        base = store.root / ".workline"
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(store.root).as_posix()
            if path.is_file() and "/locks/" not in relative:
                found[relative] = path.read_bytes()
        return found


@contextmanager
def crash_at(target: Any, name: str, *, after: bool = False, when: Any = None) -> Iterator[mock.MagicMock]:
    """Raise :class:`Crash` when ``target.name`` is called (before it runs, or right after it returns)."""
    original = getattr(target, name)
    calls = {"n": 0}

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if when is not None and not when(calls["n"], *args, **kwargs):
            return original(*args, **kwargs)
        if not after:
            raise Crash(f"crash before {name}")
        original(*args, **kwargs)
        raise Crash(f"crash after {name}")

    with mock.patch.object(target, name, wrapper) as patched:
        yield patched


@contextmanager
def executable_registration() -> Iterator[None]:
    """A fixture Kp whose Roadmap file is committed with mode ``100755`` (every other byte is the writer's).

    The planning commit primitive commits the working tree with ``--only``, which
    takes each mode from the filesystem; the fixture re-commits the same parent
    with the index mode changed, so the commit recorded as made is the changed one.
    """
    real = gitcmd.contained_commit

    def commit(repo: Path, message: str, paths: list[str], hooks: str) -> None:
        real(repo, message, paths, hooks)
        roadmaps = [path for path in paths if "/roadmaps/" in path]
        if roadmaps:
            git(repo, "update-index", "--chmod=+x", roadmaps[0])
            git(repo, "-c", f"core.hooksPath={hooks}", "commit", "-q", "--amend", "--no-edit", "--no-verify")

    with mock.patch.object(gitcmd, "contained_commit", commit):
        yield


@contextmanager
def noncanonical_registration() -> Iterator[None]:
    """A fixture Kp whose Roadmap file ends with one extra blank line: the same meaning (§31), other bytes.

    The bytes change inside the planning commit primitive's staging, after
    every own-bytes check, as a concurrent foreign change would; the proof over
    Kp then fails at P3 while the committed view still loads.
    """
    real = gitcmd.contained_add

    def add(repo: Path, paths: list[str], hooks: str) -> None:
        roadmaps = [path for path in paths if "/roadmaps/" in path]
        if roadmaps:
            target = Path(repo) / roadmaps[0]
            target.write_bytes(target.read_bytes() + b"\n")
        real(repo, paths, hooks)

    with mock.patch.object(gitcmd, "contained_add", add):
        yield


def raw_git(repo: Path, *args: str, env: dict[str, str] | None = None, data: bytes | None = None) -> str:
    """``git`` with an optional environment overlay and raw stdin bytes (fixture plumbing only)."""
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], input=data, capture_output=True, env={**os.environ, **(env or {})},
    )
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {completed.stderr.decode('utf-8', 'replace')}")
    return completed.stdout.decode("utf-8")


def plumb_commit(
    store: ProjectStore,
    parents: str | list[str],
    changes: dict[str, bytes | str | None],
    message: str = "a fixture commit",
    *,
    modes: dict[str, str] | None = None,
    base: str | None = None,
) -> str:
    """A commit made with plumbing only: ``base``'s tree (default: the first parent's) with ``changes`` applied.

    A ``str`` is written as UTF-8 bytes exactly as given, ``None`` removes the
    path. Nothing in the working tree, the index or any ref moves.
    """
    repo = store.root
    parents = [parents] if isinstance(parents, str) else list(parents)
    index = repo / ".git" / f"fixture-index-{os.getpid()}"
    env = {"GIT_INDEX_FILE": str(index)}
    try:
        raw_git(repo, "read-tree", base or parents[0], env=env)
        for path, content in changes.items():
            if content is None:
                raw_git(repo, "update-index", "--force-remove", "--", path, env=env)
                continue
            data = content.encode("utf-8") if isinstance(content, str) else content
            oid = raw_git(repo, "hash-object", "-w", "--stdin", data=data).strip()
            mode = (modes or {}).get(path, "100644")
            raw_git(repo, "update-index", "--add", "--cacheinfo", f"{mode},{oid},{path}", env=env)
        tree = raw_git(repo, "write-tree", env=env).strip()
    finally:
        if index.exists():
            index.unlink()
    args = ["commit-tree", tree, "-m", message]
    for parent in parents:
        args += ["-p", parent]
    return raw_git(repo, *args).strip()


def blob_at(store: ProjectStore, commit: str, path: str) -> bytes:
    completed = subprocess.run(["git", "-C", str(store.root), "cat-file", "blob", f"{commit}:{path}"], capture_output=True)
    if completed.returncode != 0:
        raise AssertionError(f"{commit}:{path} is not a blob")
    return completed.stdout


def move_branch(store: ProjectStore, commit: str) -> None:
    """Put the current branch, index and working tree at ``commit`` (a fixture history only; untracked files stay)."""
    git(store.root, "reset", "-q", "--hard", commit)


@contextmanager
def deterministic_ids(start: int = 1) -> Iterator[None]:
    """Every new ID from one deterministic sequence, so two Projects built alike get the same IDs."""
    counter = itertools.count(start)

    def next_ulid(now_ms: int | None = None) -> str:
        value = next(counter)
        chars = []
        for _ in range(26):
            chars.append("0123456789ABCDEFGHJKMNPQRSTVWXYZ"[value & 31])
            value >>= 5
        return "".join(reversed(chars))

    with mock.patch.object(ids, "new_ulid", next_ulid):
        yield


def state_entries(store: ProjectStore) -> dict[str, bytes | None]:
    """Every entry under ``.workline`` - directories as ``None``, files as their bytes - except the execution lock.

    The lock's own directories are left out too: taking it writes its holder durably, which recreates
    ``.workline/runtime`` and ``.workline/runtime/tmp`` when they are gone (after runtime loss, and for a legacy
    refusal exactly the same way). Whatever a run leaves *inside* them is still listed, entry for entry.
    """
    lock_directories = {".workline/runtime", store.tmp.relative_to(store.root).as_posix()}
    found: dict[str, bytes | None] = {}
    base = store.root / ".workline"
    for path in sorted(base.rglob("*")):
        relative = path.relative_to(store.root).as_posix()
        if "/locks" in relative or (relative in lock_directories and path.is_dir()):
            continue
        found[relative] = path.read_bytes() if path.is_file() else None
    return found


@dataclass(frozen=True)
class Registered:
    """What a completed review-v1 registration left: Kp, its parent P, Km, the Candidate and its Consumption."""

    kp: str
    parent: str
    km: str
    material: dict[str, Any]
    consumption: Any
    consumption_path: str

    def run(self, repo: Path, commit: str | None = None) -> Any:
        (found,) = [r for r in publication.registered_runs(repo, commit or self.km)
                    if r.candidate_hash == planning.candidate_hash(self.material)]
        return found

    def registration_blobs(self, store: ProjectStore) -> dict[str, bytes]:
        return {path: blob_at(store, self.kp, path) for path in rr.registration_paths(self.material)}


def registered(store: ProjectStore, result: Any) -> Registered:
    """Read a completed ``ReviewedPlanningResult`` back from its Consumption."""
    review = ReviewStore(store)
    consumption = review.read_consumption(result.consumption_id)
    material = review.read_candidate_snapshot(consumption.authorized_candidate_hash).material
    kp = consumption.persisted_result["registration_commit"]
    relative = review_paths.consumption_rel(result.consumption_id)
    km = git(store.root, "log", "--format=%H", "--diff-filter=A", "-n", "1", "--", relative).strip()
    return Registered(kp, consumption.persisted_result["registration_parent"], km, material, consumption, relative)


def run_ids(store: ProjectStore) -> tuple[str, ...]:
    return ReviewStore(store).run_ids()


def snapshot_material(store: ProjectStore, run_id: str) -> dict[str, Any]:
    chain = ReviewStore(store).gate_chain(run_id)
    return ReviewStore(store).read_candidate_snapshot(chain.generations[0].candidate_hash).material


__all__ = [
    "CANONICAL_RULE", "Crash", "PlanningTestCase", "Registered", "Reviewer", "blob_at", "condition", "crash_at", "design",
    "deterministic_ids", "executable_registration", "move_branch", "noncanonical_registration", "plan", "planning",
    "plumb_commit", "raw_git",
    "registered", "review_paths", "rr", "run_ids", "serialize", "snapshot_material", "state_entries",
]
