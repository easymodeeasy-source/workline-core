"""Explicit git subprocess wrapper.

Every call names the repository with ``git -C <repo>``. Only the commands the
live specification allows are exposed: no ``add .``, no force push, no rebase,
no reset, no clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import re
import subprocess
from typing import Any

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


# --------------------------------------------------------------------------- review-v1 planning: versions
#
# ``rules/git`` owns both thresholds. They are independent and never merged:
# the first is what beginning or resuming an explicit review-v1 planning
# invocation needs (``git check-attr --source`` of the checkout capability),
# the second what the publication barrier's registered-Run discovery and the
# committed planning proof need (``git log --diff-merges=combined``).

#: The oldest Git that may begin or resume an explicit review-v1 planning invocation.
P2_REVIEW_GIT_MIN = (2, 40, 0)
#: The oldest Git that may classify a history holding planning Review material for publication.
P2_PUBLICATION_GIT_MIN = (2, 31, 0)

_VERSION_TEXT = re.compile(r"git version (\d+)\.(\d+)\.(\d+)(?!\d)")
_VERSION_READ: list[tuple[int, int, int] | None] = []


def parse_git_version(text: str) -> tuple[int, int, int] | None:
    """The first three numeric components of ``git --version`` output; None when they are not there.

    ``git version 2.54.0.windows.1`` is 2.54.0. A text that does not carry
    three numeric components where Git prints them is an unknown version,
    which meets no minimum.
    """
    if not isinstance(text, str):
        return None
    match = _VERSION_TEXT.match(text.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def running_git_version() -> tuple[int, int, int] | None:
    """The running Git's version, read once per process with ``git --version``; None when unknown."""
    if not _VERSION_READ:
        result = run_git(None, "--version", check=False)
        _VERSION_READ.append(parse_git_version(result.stdout) if result.ok else None)
    return _VERSION_READ[0]


def version_meets(version: tuple[int, int, int] | None, minimum: tuple[int, int, int]) -> bool:
    """Whether ``version`` is at or above ``minimum``; an unknown version meets none."""
    return version is not None and tuple(version) >= tuple(minimum)


def version_text(version: tuple[int, ...]) -> str:
    return ".".join(str(part) for part in version)


# --------------------------------------------------------------------------- review-v1 planning: raw committed objects
#
# Every read here is of Git objects as Git stores them: bytes, never text a
# checkout, a filter or a line-end conversion produced. Nothing here evaluates
# an attribute except :func:`check_attributes`, and nothing reads the working
# tree.


@dataclass(frozen=True)
class GitBytes:
    returncode: int
    stdout: bytes
    stderr: bytes

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_git_bytes(
    repo: Path | None,
    *args: str,
    input: bytes | None = None,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> GitBytes:
    """Run git and keep its output as bytes: nothing is decoded, replaced or translated."""
    command = ["git"]
    if repo is not None:
        command += ["-C", str(repo)]
    command += list(args)
    feed = {"input": input} if input is not None else {"stdin": subprocess.DEVNULL}
    try:
        completed = subprocess.run(
            command, capture_output=True, env=env, cwd=None if cwd is None else str(cwd), **feed
        )
    except FileNotFoundError as exc:
        raise GitError("git executable not found") from exc
    return GitBytes(completed.returncode, completed.stdout, completed.stderr)


def full_commit_id(value: object) -> bool:
    """Whether ``value`` names a commit by its full lowercase hexadecimal object ID (SHA-1 or SHA-256)."""
    return isinstance(value, str) and _FULL_ID.fullmatch(value) is not None


def zero_object_id(like: str) -> str:
    """The all-zero object ID in the object format of ``like``: as many ``0`` as ``like`` has characters."""
    return "0" * len(like)


def _path_text(raw: bytes) -> str:
    # Git writes a path's bytes as they are; surrogateescape keeps any byte that is not UTF-8 exactly.
    return raw.decode("utf-8", "surrogateescape")


# Within one process, what Git answers about an object named by its full ID is reused for that same ID:
# the objects behind a commit or blob ID cannot change. Only answers are kept - a question Git could not
# answer is asked again - nothing is shared across processes, and nothing named by a ref (HEAD, a branch)
# is kept, since what a ref names can move.
_OBJECT_ANSWERS: dict[tuple, Any] = {}
_OBJECT_ANSWERS_LIMIT = 50000


def _remembered(key: tuple, compute):
    if key in _OBJECT_ANSWERS:
        return _OBJECT_ANSWERS[key]
    answer = compute()
    if answer is not None:
        if len(_OBJECT_ANSWERS) >= _OBJECT_ANSWERS_LIMIT:
            _OBJECT_ANSWERS.clear()
        _OBJECT_ANSWERS[key] = answer
    return answer


def forget_object_answers() -> None:
    """Drop every in-process answer about immutable objects (tests that patch Git's answers call this)."""
    _OBJECT_ANSWERS.clear()


def _immutable(name: str) -> bool:
    return _FULL_ID.fullmatch(name) is not None


@dataclass(frozen=True)
class TreeEntry:
    """One ``git ls-tree`` entry: the mode as Git prints it, the object type and ID, the full path."""

    mode: str
    type: str
    oid: str
    path: str


def tree_entries(
    repo: Path, commit: str, paths: "list[str] | tuple[str, ...]" = (), *, recursive: bool = True, trees: bool = False
) -> list[TreeEntry] | None:
    """The entries of ``commit``'s tree (``git ls-tree -z --full-tree``); None when undeterminable."""
    if _immutable(commit):
        return _remembered(
            ("tree", str(repo), commit, tuple(paths), recursive, trees),
            lambda: _tree_entries(repo, commit, paths, recursive, trees),
        )
    return _tree_entries(repo, commit, paths, recursive, trees)


def _tree_entries(repo: Path, commit: str, paths: "list[str] | tuple[str, ...]", recursive: bool, trees: bool) -> list[TreeEntry] | None:
    args = ["ls-tree", "-z", "--full-tree"]
    if recursive:
        args.append("-r")
    if trees:
        args.append("-t")
    args.append(commit)
    if paths:
        args += ["--", *paths]
    result = run_git_bytes(repo, *args)
    if not result.ok:
        return None
    entries: list[TreeEntry] = []
    for item in result.stdout.split(b"\0"):
        if not item:
            continue
        head, separator, path = item.partition(b"\t")
        fields = head.split(b" ")
        if not separator or len(fields) != 3 or not path:
            return None
        try:
            mode, kind, oid = (field.decode("ascii") for field in fields)
        except UnicodeDecodeError:
            return None
        entries.append(TreeEntry(mode, kind, oid, _path_text(path)))
    return entries


def read_blob(repo: Path, oid: str) -> bytes | None:
    """The raw bytes of blob ``oid`` (``git cat-file blob``); None when it cannot be read."""
    def read() -> bytes | None:
        result = run_git_bytes(repo, "cat-file", "blob", oid)
        return result.stdout if result.ok else None

    return _remembered(("blob", str(repo), oid), read) if _immutable(oid) else read()


def blob_at(repo: Path, commit: str, path: str) -> bytes | None:
    """The raw bytes ``commit`` holds at ``path`` (``git cat-file blob <commit>:<path>``); None when it holds none."""
    def read() -> bytes | None:
        result = run_git_bytes(repo, "cat-file", "blob", f"{commit}:{path}")
        return result.stdout if result.ok else None

    return _remembered(("blob_at", str(repo), commit, path), read) if _immutable(commit) else read()


def hash_blob(repo: Path, data: bytes) -> str | None:
    """The object ID ``data`` has as a blob (``git hash-object --no-filters -t blob --stdin``); nothing is written."""
    def compute() -> str | None:
        result = run_git_bytes(repo, "hash-object", "--no-filters", "-t", "blob", "--stdin", input=data)
        if not result.ok:
            return None
        oid = result.stdout.decode("ascii", "replace").strip()
        return oid if _FULL_ID.fullmatch(oid) else None

    return _remembered(("hash", str(repo), hashlib.sha256(data).hexdigest(), len(data)), compute)


@dataclass(frozen=True)
class DeltaEntry:
    """One entry of ``git diff-tree -r -z --no-renames --no-abbrev --raw``."""

    old_mode: str
    new_mode: str
    old_blob: str
    new_blob: str
    status: str
    path: str


def commit_delta(repo: Path, parent: str, commit: str) -> list[DeltaEntry] | None:
    """Every path ``commit`` changes against ``parent``, with modes, blobs and status; None when undeterminable."""
    if _immutable(parent) and _immutable(commit):
        return _remembered(("delta", str(repo), parent, commit), lambda: _commit_delta(repo, parent, commit))
    return _commit_delta(repo, parent, commit)


def _commit_delta(repo: Path, parent: str, commit: str) -> list[DeltaEntry] | None:
    result = run_git_bytes(repo, "diff-tree", "-r", "-z", "--no-renames", "--no-abbrev", "--raw", parent, commit)
    if not result.ok:
        return None
    items = result.stdout.split(b"\0")
    entries: list[DeltaEntry] = []
    index = 0
    while index < len(items):
        header = items[index]
        index += 1
        if not header:
            continue
        if not header.startswith(b":") or index >= len(items):
            return None
        fields = header[1:].split(b" ")
        if len(fields) != 5:
            return None
        try:
            old_mode, new_mode, old_blob, new_blob, status = (field.decode("ascii") for field in fields)
        except UnicodeDecodeError:
            return None
        path = items[index]
        index += 1
        if not path:
            return None
        entries.append(DeltaEntry(old_mode, new_mode, old_blob, new_blob, status, _path_text(path)))
    return entries


def added_paths(repo: Path, commit: str, paths: "list[str] | tuple[str, ...]") -> list[tuple[str, list[str]]] | None:
    """The commits in ``commit``'s history that add any of ``paths``, each with the paths it adds; None when undeterminable.

    A commit adds a path when its tree holds the path and none of its parents'
    trees does, every parent of a merge followed:
    ``git log --full-history --no-renames --diff-merges=combined --diff-filter=A --name-only -z``.
    This is the one spelling the add-history read has; no other is ever run.
    """
    if _immutable(commit):
        return _remembered(("added", str(repo), commit, tuple(paths)), lambda: _added_paths(repo, commit, paths))
    return _added_paths(repo, commit, paths)


def _added_paths(repo: Path, commit: str, paths: "list[str] | tuple[str, ...]") -> list[tuple[str, list[str]]] | None:
    result = run_git_bytes(
        repo, "log", "--full-history", "--no-renames", "--diff-merges=combined", "--diff-filter=A", "--name-only",
        "-z", "--format=%x01%H%x02", commit, "--", *paths,
    )
    if not result.ok:
        return None
    found: list[tuple[str, list[str]]] = []
    for chunk in result.stdout.split(b"\x01"):
        if not chunk:
            continue
        head, separator, rest = chunk.partition(b"\x02")
        try:
            listed = head.decode("ascii")
        except UnicodeDecodeError:
            return None
        if not separator or not _FULL_ID.fullmatch(listed):
            return None
        names = [_path_text(name.lstrip(b"\n")) for name in rest.split(b"\0") if name.lstrip(b"\n")]
        if names:
            found.append((listed, names))
    return found


def history_touches(repo: Path, commit: str, directory: str) -> bool | None:
    """Whether any commit in ``commit``'s history changed anything under ``directory``; None when Git cannot answer.

    ``git rev-list --full-history -n 1 <commit> -- <directory>``: empty exactly
    when no commit in the history changed anything there.
    """
    def read() -> bool | None:
        result = run_git(repo, "rev-list", "--full-history", "-n", "1", commit, "--", directory, check=False)
        if not result.ok:
            return None
        return bool(result.stdout.strip())

    return _remembered(("touches", str(repo), commit, directory), read) if _immutable(commit) else read()


def check_attributes(
    repo: Path | None,
    paths: "list[str] | tuple[str, ...]",
    attributes: "list[str] | tuple[str, ...]",
    *,
    before: "tuple[str, ...]" = (),
    options: "tuple[str, ...]" = (),
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> dict[str, dict[str, str]] | None:
    """What ``git check-attr`` prints for each path and attribute; None when Git cannot answer.

    ``before`` are global options (``--git-dir``, ``-c``), ``options`` those of
    ``check-attr`` itself (``--source``). Paths go on standard input, NUL
    separated. The printed word is what is returned; it is never, by itself,
    the state of the attribute.
    """
    if not paths:
        return {}
    feed = b"".join(path.encode("utf-8", "surrogateescape") + b"\0" for path in paths)
    result = run_git_bytes(
        repo, *before, "check-attr", *options, "--stdin", "-z", *attributes, input=feed, env=env, cwd=cwd
    )
    if not result.ok:
        return None
    items = result.stdout.split(b"\0")
    if items and items[-1] == b"":
        items = items[:-1]
    if len(items) % 3 != 0:
        return None
    printed: dict[str, dict[str, str]] = {}
    for index in range(0, len(items), 3):
        path = _path_text(items[index])
        try:
            name, value = items[index + 1].decode("utf-8"), items[index + 2].decode("utf-8")
        except UnicodeDecodeError:
            return None
        printed.setdefault(path, {})[name] = value
    for path in paths:
        if set(printed.get(path, {})) != set(attributes):
            return None
    return printed


def config_names_matching(repo: Path, pattern: str) -> list[str] | None:
    """The effective configuration's variable names matching ``pattern``; None when Git cannot answer."""
    result = run_git_bytes(repo, "config", "-z", "--name-only", "--get-regexp", pattern)
    if result.returncode == 1:
        return []  # no variable matches
    if not result.ok:
        return None
    return [_path_text(name) for name in result.stdout.split(b"\0") if name]


def contained_add(repo: Path, paths: list[str], hooks_path: str) -> None:
    """``git add`` with no hook, no filesystem monitor: the planning commit primitive's staging."""
    if not paths:
        return
    run_git(repo, "-c", f"core.hooksPath={hooks_path}", "-c", "core.fsmonitor=false", "add", "--", *paths)


def contained_commit(repo: Path, message: str, paths: list[str], hooks_path: str) -> None:
    """``git commit --only`` with no hook, no signing and no background maintenance (``review-v1-planning-local-v1``)."""
    if not paths:
        raise GitError("nothing to commit: empty path list")
    run_git(
        repo,
        "-c", f"core.hooksPath={hooks_path}",
        "-c", "commit.gpgSign=false",
        "-c", "core.fsmonitor=false",
        "-c", "gc.auto=0",
        "-c", "maintenance.auto=false",
        "commit", "--only", "--no-verify", "--no-gpg-sign", "-m", message, "--", *paths,
    )
