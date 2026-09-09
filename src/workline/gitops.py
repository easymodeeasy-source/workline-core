"""Git safety helpers shared by operation owners.

* pre-existing dirty state is captured at operation entry and never staged;
* only paths the current operation owns are committed;
* commit / push are recorded as mutation effects so a failure resumes from the
  Git stage without re-running domain writes.
"""

from __future__ import annotations

from pathlib import Path

from . import gitcmd
from .errors import StopError
from .mutation import Effect, Mutation
from .store import RUNTIME_DIR, ProjectStore

DEFAULT_REMOTE = "origin"


def is_runtime_path(path: str) -> bool:
    return path == RUNTIME_DIR or path.startswith(RUNTIME_DIR + "/")


def capture_preexisting_dirty(repo: Path) -> list[str]:
    """Dirty paths that are not Workline runtime metadata."""
    return sorted(p for p in gitcmd.dirty_paths(repo) if not is_runtime_path(p))


def record_preexisting_dirty(mutation: Mutation, repo: Path) -> list[str]:
    """Capture pre-existing dirty paths once per mutation (stable across resume)."""
    noted = mutation.note("preexisting_dirty")
    if noted is None:
        noted = capture_preexisting_dirty(repo)
        mutation.set_note("preexisting_dirty", noted)
    return list(noted)


def ensure_separable(preexisting: list[str], owned: list[str]) -> None:
    overlap = sorted(set(preexisting) & set(owned))
    if overlap:
        raise StopError(
            "pre-existing changes overlap operation-owned paths and cannot be separated safely: " + ", ".join(overlap),
            code="dirty_overlap",
        )


def ensure_git_ready(repo: Path) -> str:
    """Return the current branch; STOP on detached HEAD."""
    branch = gitcmd.current_branch(repo)
    if branch is None:
        raise StopError("repository is in detached HEAD state", code="detached_head")
    return branch


def finalize_effects(store: ProjectStore, message: str, paths: list[str], *, push: bool) -> list[Effect]:
    """Build commit (+ push when a remote exists and ``push`` is requested) effects."""
    repo = store.root
    effects = [Effect.git_commit(message, sorted(set(paths)), gitcmd.head_commit(repo))]
    if push and gitcmd.has_remote(repo, DEFAULT_REMOTE):
        effects.append(Effect.git_push(DEFAULT_REMOTE, ensure_git_ready(repo)))
    return effects


def finalize(mutation: Mutation, stage: str, message: str, paths: list[str], *, push: bool) -> None:
    """Record and apply the Git stage of ``mutation`` (idempotent on resume)."""
    store = mutation.store
    if not mutation.has_stage(stage):
        preexisting = record_preexisting_dirty(mutation, store.root)
        ensure_separable(preexisting, paths)
        mutation.add_effects(stage, finalize_effects(store, message, paths, push=push))
    mutation.apply()


def canonical_dirty_paths(store: ProjectStore) -> list[str]:
    """Dirty paths under ``.workline/`` excluding the runtime area."""
    return sorted(
        p for p in gitcmd.dirty_paths(store.root, [".workline"]) if not is_runtime_path(p)
    )
