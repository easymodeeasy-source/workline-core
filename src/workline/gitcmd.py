"""Explicit git subprocess wrapper.

Every call names the repository with ``git -C <repo>``. Only the commands the
live specification allows are exposed: no ``add .``, no force push, no rebase,
no reset, no clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from .errors import GitError


@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_git(repo: Path | None, *args: str, check: bool = True) -> GitResult:
    command = ["git"]
    if repo is not None:
        command += ["-C", str(repo)]
    command += list(args)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise GitError("git executable not found") from exc
    result = GitResult(completed.returncode, completed.stdout, completed.stderr)
    if check and not result.ok:
        detail = result.stderr.strip() or result.stdout.strip()
        raise GitError(f"git {' '.join(args)} failed ({result.returncode}): {detail}")
    return result


def toplevel(path: Path) -> Path | None:
    """Return the git top-level for ``path`` or None when not inside a repo."""
    result = run_git(path, "rev-parse", "--show-toplevel", check=False)
    if not result.ok:
        return None
    text = result.stdout.strip()
    if not text:
        return None
    return Path(text).resolve()


def init_main(path: Path) -> None:
    run_git(path, "init", "-b", "main")


def is_ignored(repo: Path, relpath: str) -> bool | None:
    """Whether ``relpath`` is ignored by ``repo``'s ignore rules.

    ``--no-index`` asks about the ignore rules alone, so the answer stays
    independent of what the index happens to track; tracking is a separate
    observation (:func:`tracked_under`). None means git could not decide and
    the caller must STOP rather than assume either answer.
    """
    result = run_git(repo, "check-ignore", "-q", "--no-index", "--", relpath, check=False)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def tracked_under(repo: Path, relpath: str) -> list[str] | None:
    """Paths tracked by ``repo`` under ``relpath``; None when undeterminable."""
    result = run_git(repo, "ls-files", "-z", "--", relpath, check=False)
    if not result.ok:
        return None
    return sorted(p.replace("\\", "/") for p in result.stdout.split("\0") if p)


def tracked_file(repo: Path, relpath: str) -> bool:
    """Whether ``relpath`` is tracked as exactly this file.

    The index is the authority, not the worktree: a tracked file the executor
    unlinked still has its index entry until the deletion is staged, which is
    what lets a completed Work declare it as a deletion result. A directory
    lists its children instead of itself and is therefore never accepted in
    place of the files it holds.
    """
    tracked = tracked_under(repo, relpath)
    return tracked == [relpath.replace("\\", "/")]


def current_branch(repo: Path) -> str | None:
    result = run_git(repo, "symbolic-ref", "--short", "HEAD", check=False)
    if not result.ok:
        return None
    return result.stdout.strip() or None


def head_commit(repo: Path) -> str | None:
    result = run_git(repo, "rev-parse", "--verify", "--quiet", "HEAD", check=False)
    if not result.ok:
        return None
    return result.stdout.strip() or None


def commit_message(repo: Path, rev: str) -> str:
    return run_git(repo, "log", "-1", "--format=%B", rev).stdout.strip()


@dataclass(frozen=True)
class StatusEntry:
    index: str
    worktree: str
    path: str

    @property
    def untracked(self) -> bool:
        return self.index == "?" and self.worktree == "?"


def status_entries(repo: Path, paths: list[str] | None = None) -> list[StatusEntry]:
    """Porcelain v1 status with every untracked file listed individually."""
    args = ["status", "--porcelain=v1", "--untracked-files=all", "-z"]
    if paths:
        args += ["--", *paths]
    result = run_git(repo, *args)
    entries: list[StatusEntry] = []
    items = result.stdout.split("\0")
    index = 0
    while index < len(items):
        item = items[index]
        index += 1
        if not item:
            continue
        code = item[:2]
        path = item[3:]
        if code[0] in "RC":
            index += 1  # the rename / copy source follows as its own item
        entries.append(StatusEntry(code[0], code[1], path.replace("\\", "/")))
    return entries


def dirty_paths(repo: Path, paths: list[str] | None = None) -> set[str]:
    return {entry.path for entry in status_entries(repo, paths)}


def changed_against_head(repo: Path, paths: list[str]) -> set[str]:
    """Paths (among ``paths``) that differ from HEAD in worktree or index."""
    if not paths:
        return set()
    if head_commit(repo) is None:
        return set(paths)
    return dirty_paths(repo, paths)


def staged_paths(repo: Path) -> set[str]:
    result = run_git(repo, "diff", "--cached", "--name-only", "-z")
    return {p.replace("\\", "/") for p in result.stdout.split("\0") if p}


def add_paths(repo: Path, paths: list[str]) -> None:
    if not paths:
        return
    run_git(repo, "add", "--", *paths)


def commit_only(repo: Path, message: str, paths: list[str]) -> str:
    """Commit exactly ``paths`` (``git commit --only``) and return the new HEAD."""
    if not paths:
        raise GitError("nothing to commit: empty path list")
    run_git(repo, "commit", "--only", "-m", message, "--", *paths)
    head = head_commit(repo)
    if head is None:
        raise GitError("commit did not produce a HEAD")
    return head


def remotes(repo: Path) -> list[str]:
    result = run_git(repo, "remote")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def push_locators(repo: Path, remote: str) -> list[str]:
    """Every locator ``git push <remote>`` would actually write to.

    ``get-url --push --all`` is what Git itself resolves: it applies
    ``remote.<name>.pushurl`` and ``url.<base>.pushInsteadOf`` rewriting, so it
    reports the real destination rather than the URL the config happens to
    show. It is a configuration read — no network is touched.
    """
    result = run_git(repo, "remote", "get-url", "--push", "--all", remote, check=False)
    if not result.ok:
        raise GitError(
            f"cannot resolve the push locator of remote {remote}: {result.stderr.strip() or result.stdout.strip()}"
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


@dataclass(frozen=True)
class PushPreview:
    """What Git says ``git push <remote> <branch>:<branch>`` would do."""

    flag: str  # porcelain status: "=", "*", " ", "!", ...
    summary: str
    destination: str  # the ``To <...>`` line, for reporting only


def push_dry_run(repo: Path, remote: str, branch: str) -> PushPreview:
    """Ask Git what the real push would do, over the real push path.

    The remote is named, never a resolved locator: handing a locator back to
    another Git command re-enters URL rewriting (``url.<base>.insteadOf`` can
    rewrite the very locator ``pushInsteadOf`` produced), which would inspect a
    different repository from the one the push writes to. The refspec is
    identical to the real push, so the answer describes exactly that push.
    """
    result = run_git(repo, "push", "--dry-run", "--porcelain", remote, f"{branch}:{branch}", check=False)
    destination = ""
    preview: PushPreview | None = None
    for line in result.stdout.splitlines():
        if line.startswith("To ") and not destination:
            destination = line[3:].strip()
            continue
        fields = line.split("\t")
        if len(fields) >= 3 and fields[1].endswith(f":refs/heads/{branch}"):
            preview = PushPreview(fields[0], fields[2].strip(), destination)
    if preview is not None:
        return preview
    detail = result.stderr.strip() or result.stdout.strip()
    if not result.ok:
        raise GitError(f"cannot preview the push to {remote}: {detail}")
    raise GitError(f"git push --dry-run said nothing about {branch}: {detail}")


def push(repo: Path, remote: str, branch: str) -> GitResult:
    return run_git(repo, "push", remote, f"{branch}:{branch}", check=False)


def commit_touches(repo: Path, rev: str, paths: list[str]) -> set[str]:
    """Return the subset of ``paths`` changed by commit ``rev``."""
    if not paths:
        return set()
    result = run_git(repo, "show", "--name-only", "--format=", "-z", rev, "--", *paths)
    return {p.replace("\\", "/") for p in result.stdout.split("\0") if p}
