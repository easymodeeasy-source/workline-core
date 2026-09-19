"""Explicit git subprocess wrapper.

Every call names the repository with ``git -C <repo>``. Only the commands the
live specification allows are exposed: no ``add .``, no force push, no rebase,
no reset, no clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

from .errors import GitError

#: A commit named by its full object ID (SHA-1 or SHA-256), never by an expression Git would resolve.
_FULL_ID = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")


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


def head_paths(repo: Path, relpath: str) -> list[str] | None:
    """Paths under ``relpath`` that HEAD holds; None when undeterminable.

    The index and HEAD answer different questions. A file taken out of the index
    with ``git rm --cached`` is no longer tracked there while HEAD still holds
    it, so whoever has to know that removing a file would lose something
    committed asks both, and treats an unanswerable call as "held".
    """
    result = run_git(repo, "ls-tree", "-r", "-z", "--name-only", "HEAD", "--", relpath, check=False)
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


def current_branch_ref(repo: Path) -> str | None:
    """The full name (``refs/heads/<name>``) of the branch HEAD is on; None when detached or undeterminable.

    The full name identifies the branch exactly. The short name
    :func:`current_branch` reports is shortened only as far as it stays
    unambiguous, so it can change with the other refs around the branch.
    """
    result = run_git(repo, "symbolic-ref", "--quiet", "HEAD", check=False)
    ref = result.stdout.strip()
    if not result.ok or not ref.startswith("refs/heads/"):
        return None
    return ref


def head_detached(repo: Path) -> bool | None:
    """Whether HEAD is detached - it names a commit, not a branch; None when undeterminable.

    Git answers that HEAD is no symbolic ref at all only when it is detached; a
    branch that has no commit yet is still a branch. Any other failure answers
    neither way.
    """
    result = run_git(repo, "symbolic-ref", "--quiet", "HEAD", check=False)
    if result.returncode == 0:
        return False
    if result.returncode == 1:
        return True
    return None


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
    """What Git says ``git push <remote> <refspec>`` would do."""

    flag: str  # porcelain status: "=", "*", " ", "!", ...
    summary: str
    destination: str  # the ``To <...>`` line, for reporting only


def _exact_refspec(refspec: str) -> str:
    """The full branch ref ``refspec`` pushes to; GitError unless it is ``<commit ID>:refs/heads/<name>``.

    A recorded push publishes one commit, named by its full object ID, to one
    branch named in full, and it is never forced: no ``+``, no pattern, no other
    kind of source (the branch as it is when the push runs is exactly what it
    must not publish).
    """
    source, separator, destination = refspec.partition(":")
    if not separator or not _FULL_ID.fullmatch(source) or not destination.startswith("refs/heads/") or "*" in destination:
        raise GitError(f"not the exact refspec of a recorded push: {refspec!r}")
    return destination


def push_dry_run(repo: Path, remote: str, refspec: str) -> PushPreview:
    """Ask Git what the real push of ``refspec`` would do, over the real push path.

    The remote is named, never a resolved locator, and ``refspec`` is the exact
    refspec the real push (:func:`push`) is given, so Git applies its own URL
    rewriting once and answers about exactly that push to the repository it
    writes to. It writes nothing.
    """
    destination_ref = _exact_refspec(refspec)
    result = run_git(repo, "push", "--dry-run", "--porcelain", remote, refspec, check=False)
    destination = ""
    preview: PushPreview | None = None
    for line in result.stdout.splitlines():
        if line.startswith("To ") and not destination:
            destination = line[3:].strip()
            continue
        fields = line.split("\t")
        if len(fields) >= 3 and fields[1].endswith(f":{destination_ref}"):
            preview = PushPreview(fields[0], fields[2].strip(), destination)
    if preview is not None:
        return preview
    detail = result.stderr.strip() or result.stdout.strip()
    if not result.ok:
        raise GitError(f"cannot preview the push to {remote}: {detail}")
    raise GitError(f"git push --dry-run said nothing about {destination_ref}: {detail}")


def push(repo: Path, remote: str, refspec: str) -> GitResult:
    """Push exactly ``refspec`` - one commit by its ID to one full branch ref - to ``remote``, never forced."""
    _exact_refspec(refspec)
    return run_git(repo, "push", remote, refspec, check=False)


def reads_itself(repo: Path, locator: str) -> bool | None:
    """Whether a read of ``locator`` reaches ``locator`` itself; None when Git cannot say.

    A read (``ls-remote``, ``fetch``) of a URL passes it through
    ``url.<base>.insteadOf`` again, which can turn the very locator
    ``pushInsteadOf`` produced into another repository's. ``git ls-remote
    --get-url`` answers with the URL such a read would contact, without
    contacting anything; only when that is the locator unchanged does reading it
    read the repository the push writes to.
    """
    result = run_git(repo, "ls-remote", "--get-url", locator, check=False)
    if not result.ok:
        return None
    return result.stdout.strip() == locator


def _require_reads_itself(repo: Path, locator: str) -> None:
    if reads_itself(repo, locator) is not True:
        raise GitError(f"Git does not read {locator} as itself, so it is not read")


def destination_branch(repo: Path, locator: str, ref: str) -> str | None:
    """The commit branch ``ref`` points at in the repository at ``locator``; None when it has no such branch.

    A read-only network question (``ls-remote``), put only to a locator Git
    reads as itself (:func:`reads_itself`). Nothing local or remote is written.
    Any failure raises: a destination that cannot be read shows nothing.
    """
    if not ref.startswith("refs/heads/"):
        raise GitError(f"not a full branch ref: {ref!r}")
    _require_reads_itself(repo, locator)
    result = run_git(repo, "ls-remote", "--refs", locator, ref, check=False)
    if not result.ok:
        raise GitError(f"cannot read {ref} at {locator}: {result.stderr.strip() or result.stdout.strip()}")
    found = [line.split("\t", 1)[0] for line in result.stdout.splitlines() if line.split("\t", 1)[-1] == ref]
    if len(found) > 1 or found and not _FULL_ID.fullmatch(found[0]):
        raise GitError(f"cannot read {ref} at {locator}: {result.stdout.strip()!r}")
    return found[0] if found else None


def fetch_destination_branch(repo: Path, locator: str, ref: str) -> None:
    """Bring the history branch ``ref`` has at ``locator`` into this repository's object database, and nothing else.

    Put only to a locator Git reads as itself (:func:`reads_itself`), and to
    nothing else. No ref is created or moved (the refspec names no destination,
    and ``--refmap=`` keeps Git from mapping it through the fetch refspecs of a
    remote whose name the locator also is), no bundle is fetched from a
    ``fetch.bundleURI`` first (into ``refs/bundles``), ``FETCH_HEAD`` is not
    written, no tag is followed, no submodule is fetched and no automatic
    maintenance runs: the working tree, the index, HEAD and every branch stay as
    they are, and only objects nothing refers to are added.
    """
    if not ref.startswith("refs/heads/"):
        raise GitError(f"not a full branch ref: {ref!r}")
    _require_reads_itself(repo, locator)
    run_git(
        repo, "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-c", "fetch.writeCommitGraph=false",
        "-c", "fetch.bundleURI=", "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "--no-recurse-submodules",
        "--refmap=", locator, ref,
    )


def commit_touches(repo: Path, rev: str, paths: list[str]) -> set[str]:
    """Return the subset of ``paths`` changed by commit ``rev``."""
    if not paths:
        return set()
    result = run_git(repo, "show", "--name-only", "--format=", "-z", rev, "--", *paths)
    return {p.replace("\\", "/") for p in result.stdout.split("\0") if p}


def commit_changes(repo: Path, commit: str) -> list[str] | None:
    """The paths local commit ``commit`` changes against its first parent, without rename detection; None when undeterminable."""
    result = run_git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "--no-renames", commit, check=False)
    if not result.ok:
        return None
    return sorted(p.replace("\\", "/") for p in result.stdout.split("\0") if p)


def branch_commit(repo: Path, ref: str) -> str | None:
    """The commit local branch ``ref`` (full name) points at; None when there is none or Git cannot say."""
    result = run_git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    commit = result.stdout.strip()
    return commit if result.ok and _FULL_ID.fullmatch(commit) else None


def commit_parents(repo: Path, commit: str) -> list[str] | None:
    """The parents of local commit ``commit``, by object ID and in order; None when undeterminable.

    A root commit has none. ``commit`` is named by its full object ID, and the
    answer comes only when Git reports that very commit.
    """
    result = run_git(repo, "rev-list", "--parents", "-n", "1", commit, "--", check=False)
    listed = result.stdout.split()
    if not result.ok or not listed or listed[0] != commit:
        return None
    return listed[1:]


def descends_from(repo: Path, commit: str, ancestor: str) -> bool | None:
    """Whether local commit ``commit`` is ``ancestor`` itself or descends from it; None when undeterminable.

    Both are commits of this repository, named by object ID. It says nothing
    about what a remote holds by itself: that comes from the push path
    (:func:`push_dry_run`) and from what the destination itself reports
    (:func:`destination_branch`).
    """
    result = run_git(repo, "merge-base", "--is-ancestor", ancestor, commit, check=False)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def commits_touching(repo: Path, since: str, until: str, paths: list[str]) -> list[str] | None:
    """Commits in ``since..until`` that change any of ``paths``; None when undeterminable.

    A commit counts when it differs at those paths from any one of its parents,
    and every parent of a merge is followed (``--full-history``): a path a
    merged branch changed and changed back is still reported, although neither
    the merge nor the end result shows it. There is no rename detection, so a
    rename into or out of a path is a change of that path.
    """
    result = run_git(repo, "rev-list", "--full-history", f"{since}..{until}", "--", *paths, check=False)
    if not result.ok:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]
