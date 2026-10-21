"""field-feedback item 6: a Reviewer's read access is checked before the Review starts, not discovered as a HUMAN_WAIT afterwards.

The field case: a Project whose solver lives in a submodule, and a Review actor whose read-only Git allowance did
not list the commands it actually runs there (``git -C <submodule> ...``, ``git ls-tree``,
``git submodule status``). The Reviewer could not read what it had to judge, reported the surface as uninspected,
and the Run waited for a Human to decide a requirement that was never in question.

This is the core side only: a pre-check, before any lock-bound effect, of whether each Review actor *would be
allowed* the read commands this Project needs. An actor opts in by exposing ``read_access(argv) -> bool`` (the
actor's own allowance, asked - never executed). An actor that exposes none is not checked and nothing changes for
it; building the allowance itself is the actor owner's. Read-only is kept two ways: a write-capable command
(commit, checkout, push, ...) that an actor would allow is itself a refusal, and no command is ever run here
except the read-only Git queries that decide whether a target exists.

A shortage is classified, never folded into a requirement question:

``permission_denied``  the actor's allowance refuses a read command this Project needs
``target_missing``     the target (a submodule) is not checked out here, so nothing could be read
``write_permitted``    the actor's allowance would run a write command - read-only is not kept
``unknown``            the Project's list of submodules could not be read, so what the actor would have to read is
                       not known: never treated as "no submodules", it stops the START like the other shortages
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from . import gitcmd
from .errors import GitError, StopError

CODE_REVIEWER_ACCESS = "review_reviewer_access_insufficient"

PERMISSION_DENIED = "permission_denied"
TARGET_MISSING = "target_missing"
WRITE_PERMITTED = "write_permitted"
UNKNOWN = "unknown"
CLASSIFICATIONS = (PERMISSION_DENIED, TARGET_MISSING, WRITE_PERMITTED, UNKNOWN)

#: The attribute an actor exposes to be checked: ``read_access(argv: tuple[str, ...]) -> bool``.
READ_ACCESS_ATTR = "read_access"

GITLINK_MODE = "160000"


@dataclass(frozen=True)
class AccessFinding:
    actor: str
    classification: str
    target: str
    command: tuple[str, ...]

    def describe(self) -> str:
        return f"{self.actor}: {self.classification} for {self.target} ({' '.join(self.command)})"


def submodule_paths(root: Any) -> list[str]:
    """The submodule (gitlink) paths of the Project's index, sorted; none when it has none.

    A list that cannot be read is NOT "no submodules": the access status is then ``unknown`` and the START stops
    (``review_reviewer_access_insufficient``) before anything is begun, reserved or written.
    """
    try:
        result = gitcmd.run_git(root, "ls-files", "-s", check=False)
        readable = result.ok
    except GitError:
        readable = False
    if not readable:
        raise StopError(
            f"a Review actor's read access is {UNKNOWN}: the Project's list of submodules could not be read, so what "
            "a Reviewer would have to read here is not known; the Review is not started (nothing is begun, reserved "
            "or written; this is an access check that could not be completed, never a requirement question for a Human)",
            code=CODE_REVIEWER_ACCESS,
        )
    found: set[str] = set()
    for line in result.stdout.splitlines():
        head, _, path = line.partition("\t")
        if head.split(" ", 1)[0] == GITLINK_MODE and path:
            found.add(path)
    return sorted(found)


def read_commands(path: str) -> list[tuple[str, ...]]:
    """The read-only Git forms a Reviewer runs against the submodule at ``path``, exactly as it spells them."""
    return [
        ("git", "-C", path, "rev-parse", "HEAD"),
        ("git", "-C", path, "log", "-1", "--format=%H"),
        ("git", "-C", path, "ls-tree", "-r", "--name-only", "HEAD"),
        ("git", "ls-tree", "HEAD", path),
        ("git", "submodule", "status"),
    ]


def write_commands(path: str) -> list[tuple[str, ...]]:
    """Git forms that change state: an actor that would allow one is not read-only."""
    return [
        ("git", "-C", path, "commit", "--allow-empty", "-m", "x"),
        ("git", "-C", path, "checkout", "--detach"),
        ("git", "-C", path, "push"),
        ("git", "-C", path, "reset", "--hard"),
        ("git", "submodule", "update", "--init", path),
    ]


def _allowed(check: Any, argv: tuple[str, ...]) -> bool:
    try:
        return check(argv) is True
    except Exception:  # an allowance that cannot answer is not an allowance
        return False


def checked_out(root: Any, path: str) -> bool:
    """Whether the submodule at ``path`` is itself checked out: the repository found there is its own, not the Project's.

    ``git -C <path> rev-parse HEAD`` is no proof: an uninitialized or deinitialized gitlink leaves an empty directory,
    and Git then finds the superproject above it and answers with the superproject's HEAD. The top level of the
    repository found at ``path`` must be ``path`` itself.
    """
    target = Path(str(root)) / path
    try:
        top = gitcmd.toplevel(target)
    except GitError:
        return False
    if top is None:
        return False
    try:
        expected = target.resolve()
    except OSError:
        return False
    return os.path.normcase(str(top)) == os.path.normcase(str(expected))


def findings_for(root: Any, actor: str, check: Any, paths: Iterable[str] | None = None) -> list[AccessFinding]:
    """The access shortages of one actor's ``check`` over the Project's submodules (nothing to check without any)."""
    found: list[AccessFinding] = []
    for path in sorted(submodule_paths(root) if paths is None else paths):
        if not checked_out(root, path):
            found.append(AccessFinding(actor, TARGET_MISSING, path, ("git", "-C", path, "rev-parse", "HEAD")))
            continue
        for argv in read_commands(path):
            if not _allowed(check, argv):
                found.append(AccessFinding(actor, PERMISSION_DENIED, path, argv))
        for argv in write_commands(path):
            if _allowed(check, argv):
                found.append(AccessFinding(actor, WRITE_PERMITTED, path, argv))
    return found


def _bindings(*selectors: Any) -> list[tuple[Any, str]]:
    """The ``(actor, label)`` of every Review actor the selectors name: P4 bindings and the review-v1 reviewer."""
    found: list[tuple[Any, str]] = []
    for selector in selectors:
        if selector is None:
            continue
        bindings: list[Any] = []
        for name in ("discovery", "holdout_discovery"):
            bindings.extend(getattr(selector, name, ()) or ())
        for name in ("adjudicator", "repair"):
            binding = getattr(selector, name, None)
            if binding is not None:
                bindings.append(binding)
        for binding in bindings:
            found.append((getattr(binding, "actor", None), f"{binding.identity} {binding.version}"))
        reviewer = getattr(selector, "reviewer", None)
        if reviewer is not None:
            label = f"{getattr(selector, 'reviewer_identity', 'reviewer')} {getattr(selector, 'reviewer_version', '')}"
            found.append((reviewer, label.strip()))
    return found


def require_reviewer_access(root: Any, *selectors: Any) -> None:
    """STOP before any effect when a checkable Review actor cannot read what this Project needs, or is not read-only.

    ``selectors`` are the START's ``review`` / ``phase_review`` selectors (``None`` ones are skipped). Only an
    actor exposing :data:`READ_ACCESS_ATTR` is checked.
    """
    seen: set[int] = set()
    problems: list[AccessFinding] = []
    paths: list[str] | None = None
    for actor, label in _bindings(*selectors):
        check = getattr(actor, READ_ACCESS_ATTR, None)
        if not callable(check) or id(actor) in seen:
            continue
        seen.add(id(actor))
        if paths is None:
            paths = submodule_paths(root)
        problems += findings_for(root, label, check, paths)
    if problems:
        raise StopError(
            "a Review actor cannot be relied on to read this Project, and the Review is not started (nothing is "
            "begun, reserved or written; this is an actor access shortage, never a requirement question for a "
            "Human): " + "; ".join(item.describe() for item in problems),
            code=CODE_REVIEWER_ACCESS,
        )
