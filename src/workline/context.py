"""Invocation Project context (``rules/git``: Project context).

A state-changing operation on an established Workline Project runs only when
the Project the process works in is that very Project. The invocation context
is resolved once, when the top-level operation starts, from the process working
directory — never from a session identity, an argument, an environment
variable or anything a prompt says:

* the working directory is resolved to its real path and walked upward;
* the first directory holding ``.workline/project.yaml`` is the context
  Project (a directory holding both that and ``.git`` is a Project);
* a ``.git`` file or directory met first is a Git repository that is not a
  Project: the walk stops there and never reaches a Project above it;
* nothing up to the filesystem root means there is no Project context.

A mismatch STOPs as ``foreign_project_mutation`` before the Project execution
lock is taken, so a foreign caller creates nothing in the target. Reading
another Project is never checked.

Initial Project開始 is the one pre-project exception. It never runs from inside
an established Project other than its target and never creates a Workline
Project inside an established one; project_start() then grants its own
mutation a private authorization bound to its exact target root, and the
Mutation Controller accepts a Project開始 mutation only inside it. The owner
name alone authorizes nothing.

This guards against passing another Project's path by mistake. It is not a
security sandbox: deliberately changing the working directory, or writing files
without Workline, is outside what it guarantees.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Iterator

from .errors import ForeignProjectMutation, StopError
from .store import PROJECT_YAML_REL

PROJECT = "project"
GIT_REPOSITORY = "git_repository"
NO_CONTEXT = "none"


@dataclass(frozen=True)
class InvocationContext:
    """Where a top-level operation was started from."""

    kind: str  # project | git_repository | none
    root: Path | None  # the Project root or the Git repository boundary
    cwd: Path  # the resolved working directory it was resolved from

    def describe(self) -> str:
        if self.kind == PROJECT:
            return f"inside the Workline Project {self.root}"
        if self.kind == GIT_REPOSITORY:
            return f"inside the Git repository {self.root}, which is not a Workline Project"
        return f"from {self.cwd}, which is inside no Git repository or Workline Project"


def resolve_invocation_context() -> InvocationContext:
    """The invocation context of the current working directory."""
    try:
        here = Path.cwd().resolve()
    except OSError as exc:
        raise StopError(
            f"cannot resolve the working directory this operation was started from: {exc}",
            code="invocation_context_unavailable",
        ) from exc
    for directory in (here, *here.parents):
        if os.path.isfile(directory / PROJECT_YAML_REL):
            return InvocationContext(PROJECT, directory, here)
        git = directory / ".git"
        if os.path.isdir(git) or os.path.isfile(git):
            return InvocationContext(GIT_REPOSITORY, directory, here)
    return InvocationContext(NO_CONTEXT, None, here)


def same_directory(first: Path, second: Path) -> bool:
    """Whether two paths name one directory: the same real path and file identity.

    Resolving removes differences of spelling (case on Windows, separators,
    junctions and symlinks); the file identity check keeps two distinct
    directories from ever comparing equal.
    """
    try:
        real_first, real_second = Path(first).resolve(), Path(second).resolve()
        if os.path.normcase(real_first) != os.path.normcase(real_second):
            return False
        return os.path.samefile(real_first, real_second)
    except OSError:
        return False


def authorize_project_mutation(target_root: Path) -> InvocationContext:
    """STOP unless this process works inside the established Project it is about to change."""
    context = resolve_invocation_context()
    if context.kind == PROJECT and context.root is not None and same_directory(context.root, target_root):
        return context
    raise ForeignProjectMutation(
        f"this operation would change the Workline Project {target_root}, but it was started "
        f"{context.describe()}; an established Project is changed only from its own context, so open "
        "that Project directly and run the operation there. Nothing was written.",
        context_root=context.root,
        target_root=Path(target_root),
    )


def require_pre_project_context(target_root: Path) -> InvocationContext:
    """STOP unless Project開始 of ``target_root`` may run from here.

    It never runs from inside an established Project other than the target, and
    it never makes a Workline Project inside an established one. Only the
    target's ancestors are examined, never its contents.
    """
    target = Path(target_root).resolve()
    context = resolve_invocation_context()
    if context.kind == PROJECT and context.root is not None and not same_directory(context.root, target):
        raise ForeignProjectMutation(
            f"Project開始 of {target} was started {context.describe()}; a folder is initialized from the "
            "Workline root or from a directory that is not another established Project. Nothing was written.",
            context_root=context.root,
            target_root=target,
        )
    for ancestor in target.parents:
        if os.path.isfile(ancestor / PROJECT_YAML_REL):
            raise StopError(
                f"{target} is inside the established Workline Project {ancestor}; a Workline Project is not "
                "created inside another one. Nothing was written.",
                code="nested_workline_project",
            )
    return context


@dataclass(frozen=True)
class _PreProjectGrant:
    root: Path


_pre_project_grant: ContextVar[_PreProjectGrant | None] = ContextVar("workline_pre_project_grant", default=None)


@contextmanager
def _pre_project_authorization(target_root: Path) -> Iterator[None]:
    """Authorize Project開始's own mutation for exactly ``target_root``.

    Private to :func:`workline.project_start.project_start`, which enters it only
    after its pre-project checks have passed. It takes no token or flag, and it
    is withdrawn however the block exits.
    """
    token = _pre_project_grant.set(_PreProjectGrant(Path(target_root).resolve()))
    try:
        yield
    finally:
        _pre_project_grant.reset(token)


def pre_project_authorized(root: Path) -> bool:
    """Whether a running Project開始 has authorized mutations of ``root``."""
    grant = _pre_project_grant.get()
    return grant is not None and same_directory(grant.root, root)


__all__ = [
    "GIT_REPOSITORY",
    "NO_CONTEXT",
    "PROJECT",
    "InvocationContext",
    "authorize_project_mutation",
    "pre_project_authorized",
    "require_pre_project_context",
    "resolve_invocation_context",
    "same_directory",
]
