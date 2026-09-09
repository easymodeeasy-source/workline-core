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


def has_remote(repo: Path, name: str = "origin") -> bool:
    return name in remotes(repo)


def fetch(repo: Path, remote: str, branch: str) -> GitResult:
    return run_git(repo, "fetch", remote, branch, check=False)


def remote_ref(repo: Path, remote: str, branch: str) -> str | None:
    result = run_git(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}/{branch}", check=False)
    if not result.ok:
        return None
    return result.stdout.strip() or None


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = run_git(repo, "merge-base", "--is-ancestor", ancestor, descendant, check=False)
    return result.returncode == 0


def push(repo: Path, remote: str, branch: str) -> GitResult:
    return run_git(repo, "push", remote, f"{branch}:{branch}", check=False)


def commit_touches(repo: Path, rev: str, paths: list[str]) -> set[str]:
    """Return the subset of ``paths`` changed by commit ``rev``."""
    if not paths:
        return set()
    result = run_git(repo, "show", "--name-only", "--format=", "-z", rev, "--", *paths)
    return {p.replace("\\", "/") for p in result.stdout.split("\0") if p}
