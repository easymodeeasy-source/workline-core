"""Git safety helpers shared by operation owners.

* pre-existing dirty state is captured at operation entry and never staged;
* only paths the current operation owns are committed;
* commit / push are recorded as mutation effects so a failure resumes from the
  Git stage without re-running domain writes;
* a push is only ever recorded for a destination the operation owner verified
  at its entry (:mod:`workline.destination`), never for whatever ``origin``
  happens to be.
"""

from __future__ import annotations

from pathlib import Path

from . import gitcmd
from .destination import DEFAULT_REMOTE, PushDestination, ensure_push_destination
from .errors import StopError
from .mutation import Effect, Mutation
from .store import RUNTIME_DIR, ProjectStore

__all__ = [
    "DEFAULT_REMOTE",
    "PushDestination",
    "canonical_dirty_paths",
    "capture_preexisting_dirty",
    "ensure_git_ready",
    "ensure_push_destination",
    "ensure_separable",
    "finalize",
    "finalize_effects",
    "is_runtime_path",
    "record_preexisting_dirty",
]


def is_runtime_path(path: str) -> bool:
    return path == RUNTIME_DIR or path.startswith(RUNTIME_DIR + "/")


def capture_preexisting_dirty(repo: Path) -> list[str]:
    """Dirty paths that are not Workline runtime metadata."""
    return sorted(p for p in gitcmd.dirty_paths(repo) if not is_runtime_path(p))


def record_preexisting_dirty(mutation: Mutation, repo: Path, *, exclude: tuple[str, ...] = ()) -> list[str]:
    """Capture pre-existing dirty paths once per mutation (stable across resume).

    ``exclude`` drops paths the operation has already proven it owns — an
    untracked file byte-identical to an artifact this operation would write is
    not an unrelated user change, so it may be committed instead of blocking
    the operation. The exclusion is applied when the note is first recorded, so
    every later reader (including the Git stage) sees the same list on resume.
    """
    noted = mutation.note("preexisting_dirty")
    if noted is None:
        noted = [p for p in capture_preexisting_dirty(repo) if p not in exclude]
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


def finalize_effects(
    store: ProjectStore, message: str, paths: list[str], *, destination: PushDestination | None
) -> list[Effect]:
    """Build the commit effect, plus a push effect when ``destination`` is set.

    ``destination`` is the verified :class:`PushDestination` the owner obtained
    at its entry; ``None`` means this finalization does not push (a remote-less
    Project, or Project開始, whose initial commit deliberately needs no push).
    """
    repo = store.root
    effects = [Effect.git_commit(message, sorted(set(paths)), gitcmd.head_commit(repo))]
    if destination is not None:
        effects.append(Effect.git_push(destination.remote, ensure_git_ready(repo), destination.locator))
    return effects


def finalize(
    mutation: Mutation, stage: str, message: str, paths: list[str], *, destination: PushDestination | None
) -> None:
    """Record and apply the Git stage of ``mutation`` (idempotent on resume)."""
    store = mutation.store
    if not mutation.has_stage(stage):
        preexisting = record_preexisting_dirty(mutation, store.root)
        ensure_separable(preexisting, paths)
        mutation.add_effects(stage, finalize_effects(store, message, paths, destination=destination))
    mutation.apply()


def canonical_dirty_paths(store: ProjectStore) -> list[str]:
    """Dirty paths under ``.workline/`` excluding the runtime area."""
    return sorted(
        p for p in gitcmd.dirty_paths(store.root, [".workline"]) if not is_runtime_path(p)
    )
