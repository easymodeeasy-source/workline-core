"""Isolated verification of a frozen Work Candidate: the IP-6 materialization primitive (``F2`` §13.4).

F2 assigns isolated verification to P3 and freezes its minimum semantics, V-1 to
V-5; F3 §21.1 IP-6 names the gap: no live primitive exports a Work result tree.
This module is that primitive, and nothing more:

```text
V-1  target          the EXACT frozen Candidate, identified by candidate_hash - and nothing else
V-2  reconstruction  a workspace materialized from declared_base.base_commit PLUS the exact
                     CandidateSnapshot.material, and from nothing else:
                         file      the exact decoded payload bytes, at the entry's mode
                         symlink   the exact link object from the target bytes; never dereferenced
                         gitlink   the exact 160000 entry naming new_oid; no clone, no checkout
                         absent    that exact path removed from the base materialization
                         empty     the base materialization, with no owned result delta
V-3  no substitution the primary working tree is NEVER used in its place
```

**Where the material comes from.** The payloads are the snapshot's, already
proven against the Candidate by :func:`workline.review.work_review.read_material`
(canonical Base64, SHA-256, Git blob identity); the base is the committed tree of
``declared_base.base_commit``, read through class B. The Project's working tree,
its index, a future K1 and ``.workline/runtime/**`` state are never read.

**How.** Measured, the same containment the resulting-tree composition uses: a
bare scratch repository under ``.workline/runtime/review/work-verify/`` borrows
the Project's object store through ``alternates``, so new blobs land only in the
scratch store and the Project is never written. The index is loaded from the
base tree and every entry is applied through ``update-index --index-info``;
``write-tree`` must reproduce the Context's ``resulting_tree`` exactly. The
workspace is then checked out with ``checkout-index`` under ``attr.tree`` set to
the empty tree - measured, without it an in-tree ``text eol=crlf`` rewrote the
bytes on checkout - so no attribute of the Candidate itself can transform what is
materialized, and each entry is read back from the workspace, no-follow.

A verification failure is ``reconcile_required``: the frozen Candidate could not
be reproduced from its clone-safe material, and nothing is substituted for it.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import stat
import sys
from typing import Any

from .. import gitcmd
from ..errors import ReconcileRequired, StopError, ValidationError
from ..store import ProjectStore
from . import fsafe, paths as review_paths, resulting_tree, work_review
from .hermetic import HermeticGit


def _failed(message: str) -> ReconcileRequired:
    return ReconcileRequired(
        f"isolated verification could not reproduce the frozen Work Candidate: {message}; nothing is substituted: "
        "reconcile required"
    )


def _unavailable(message: str) -> StopError:
    return StopError(f"the isolated verification workspace cannot be built: {message}: STOP",
                     code="review_candidate_unavailable")


@dataclass(frozen=True)
class Verified:
    """What the isolated verification reproduced: the exact tree and every entry, from clone-safe material."""

    base_commit: str
    resulting_tree: str
    verified_entries: int


def _can_symlink(directory: Path) -> bool:
    probe = directory / "symlink-probe"
    try:
        os.symlink("target", probe)
    except (OSError, NotImplementedError):
        return False
    try:
        return os.path.islink(probe)
    finally:
        try:
            os.unlink(probe)
        except OSError:
            pass


def verify(
    store: ProjectStore,
    hermetic: HermeticGit,
    reconstruction: work_review.Reconstruction,
    *,
    resulting_tree_id: str,
) -> Verified:
    """V-1 ... V-3: materialize the exact Candidate in an isolated workspace and read every entry back.

    ``reconstruction`` is the snapshot proven against its Candidate; nothing
    else supplies a byte. ``resulting_tree_id`` is the tree the Context binds,
    and the workspace's index must write exactly it.
    """
    candidate = reconstruction.candidate
    base_commit = candidate["declared_base"]["base_commit"]
    if not gitcmd.full_commit_id(base_commit):
        raise _failed(f"the declared base {base_commit!r} is not an exact commit id")
    width = len(base_commit)
    zero = "0" * width
    entries = work_review.entries_of(candidate)
    base_tree = resulting_tree.root_tree_id(hermetic, base_commit)
    objects = resulting_tree._objects_directory(hermetic, store)
    object_format = resulting_tree._object_format(hermetic)
    scratch = store.root / review_paths.RUNTIME_WORK_VERIFY_DIR / secrets.token_hex(8)
    try:
        try:
            scratch.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise _unavailable(f"the verification directory {scratch} cannot be created: {exc}") from exc
        bare = scratch / "verify.git"
        created = gitcmd.run_git(
            None, "init", "--bare", "--quiet", "--template=", f"--object-format={object_format}", str(bare),
            check=False, env=hermetic.environment(),
        )
        if not created.ok:
            raise _unavailable(f"the verification repository could not be created: {created.stderr.strip()}")
        alternates = bare / "objects" / "info" / "alternates"
        alternates.parent.mkdir(parents=True, exist_ok=True)
        alternates.write_text(objects.as_posix() + "\n", encoding="utf-8", newline="\n")
        index_file = str(scratch / "verify-index")
        workspace = scratch / "workspace"
        workspace.mkdir()
        symlinks = _can_symlink(scratch)

        def run(*args: str, feed: bytes | None = None, extra: tuple[str, ...] = ()) -> gitcmd.GitBytes:
            return gitcmd.run_git_bytes(
                bare, *hermetic.configuration_arguments(), *extra, *args,
                input=feed, env=hermetic.environment(index_file=index_file),
            )

        if not run("read-tree", base_tree).ok:
            raise _failed(f"the base tree {base_tree} of {base_commit} could not be loaded")
        feed: list[str] = []
        for entry in entries:
            path = entry["path"]
            if entry["new_kind"] == "absent":
                feed.append(f"000000 {zero} 0\t{path}")
                continue
            if entry["new_kind"] in work_review.BYTE_KINDS:
                data = reconstruction.payloads.get(path)
                if data is None:
                    raise _failed(f"no payload carries {path!r}")
                written = run("hash-object", "-w", "-t", "blob", "--stdin", feed=data)
                if not written.ok or written.stdout.decode("ascii", "replace").strip() != entry["new_oid"]:
                    raise _failed(f"the payload of {path!r} is not the object {entry['new_oid']} the Candidate froze")
            feed.append(f"{entry['new_mode']} {entry['new_oid']} 0\t{path}")
        if feed:
            applied = run("update-index", "--index-info", feed=("\n".join(feed) + "\n").encode("utf-8", "surrogateescape"))
            if not applied.ok:
                raise _failed("the Candidate's entries could not be applied: "
                              + applied.stderr.decode("utf-8", "replace").strip())
        tree = run("write-tree")
        found = tree.stdout.decode("ascii", "replace").strip() if tree.ok else ""
        if found != resulting_tree_id:
            raise _failed(f"the reconstructed tree is {found or 'unwritable'}, not the {resulting_tree_id} the Context binds")
        _require_index_entries(run, entries)
        # the empty tree, written into the SCRATCH store, is the attribute source: nothing applies
        empty = run("mktree", feed=b"")
        empty_tree = empty.stdout.decode("ascii", "replace").strip() if empty.ok else ""
        if not gitcmd.full_commit_id(empty_tree):
            raise _unavailable("the empty attribute source could not be written")
        checkout = run(
            f"--work-tree={workspace}", "checkout-index", "-a", "-f",
            extra=("-c", f"attr.tree={empty_tree}", "-c", f"core.symlinks={'true' if symlinks else 'false'}",
                   "-c", "core.fileMode=true"),
        )
        if not checkout.ok:
            raise _failed("the workspace could not be materialized: " + checkout.stderr.decode("utf-8", "replace").strip())
        for entry in entries:
            _require_materialized(workspace, entry, reconstruction.payloads.get(entry["path"]), symlinks)
        verified = Verified(base_commit=base_commit, resulting_tree=found, verified_entries=len(entries))
    finally:
        # Git writes loose objects read-only; the composition's own removal makes them writable first
        removed = resulting_tree._remove_scratch(scratch)
    if not removed:
        raise _unavailable(f"the verification directory {scratch} could not be removed")
    return verified


def _require_index_entries(run: Any, entries: list[dict[str, Any]]) -> None:
    """Every Candidate entry is exactly in the reconstructed index: its mode and id, or its absence."""
    if not entries:
        return
    listed = run("ls-files", "-s", "-z", "--", *[entry["path"] for entry in entries])
    if not listed.ok:
        raise _failed("the reconstructed index cannot be listed")
    held: dict[str, tuple[str, str]] = {}
    for item in listed.stdout.split(b"\0"):
        if not item:
            continue
        head, _, path = item.partition(b"\t")
        fields = head.decode("ascii", "replace").split(" ")
        if len(fields) != 3:
            raise _failed("the reconstructed index holds a record this reader cannot classify")
        held[path.decode("utf-8", "surrogateescape")] = (fields[0], fields[1])
    for entry in entries:
        found = held.get(entry["path"])
        if entry["new_kind"] == "absent":
            if found is not None:
                raise _failed(f"{entry['path']!r} is still in the reconstructed index")
        elif found != (entry["new_mode"], entry["new_oid"]):
            raise _failed(f"{entry['path']!r} is {found} in the reconstructed index, not {entry['new_mode']} {entry['new_oid']}")


def _link_target(workspace: Path, path: str) -> bytes:
    """The link at ``path`` in the workspace, read the way Git reads it - ``fsafe``'s reader, never ``os.readlink``.

    Git for Windows checks a link out with backslashes and reads one back through
    its own normalization, while ``os.readlink`` renders the same reparse data its
    own way (a ``\\\\?\\`` prefix, backslashes kept): compared with Git's bytes, that
    rendering would refuse every link holding a separator or an absolute target.
    On POSIX both are the raw target bytes.
    """
    parts = path.split("/")
    try:
        chain = fsafe.walk(workspace, parts[:-1])
        if chain is None:
            raise _failed(f"{path!r} is missing from the workspace")
        with chain:
            link = chain.last.read_link(parts[-1])
    except ValidationError as exc:
        raise _failed(f"{path!r} cannot be read back as a link: {exc.message}") from exc
    if link is None:
        raise _failed(f"{path!r} is missing from the workspace")
    return link.target


def _require_materialized(workspace: Path, entry: dict[str, Any], payload: bytes | None, symlinks: bool) -> None:
    """One entry, read back from the workspace no-follow: its kind and exact bytes as V-2 freezes them."""
    target = workspace.joinpath(*entry["path"].split("/"))
    try:
        info = os.lstat(target)
    except FileNotFoundError:
        info = None
    except OSError as exc:
        raise _failed(f"{entry['path']!r} cannot be read back from the workspace: {exc}") from exc
    kind = entry["new_kind"]
    if kind == "absent":
        if info is not None:
            raise _failed(f"{entry['path']!r} is present in the workspace, and the Candidate removes it")
        return
    if info is None:
        raise _failed(f"{entry['path']!r} is missing from the workspace")
    if kind == "gitlink":
        if not stat.S_ISDIR(info.st_mode):
            raise _failed(f"{entry['path']!r} is not the directory a gitlink checks out as")
        return
    if kind == "symlink" and symlinks:
        if not stat.S_ISLNK(info.st_mode):
            raise _failed(f"{entry['path']!r} is not a symbolic link in the workspace")
        if _link_target(workspace, entry["path"]) != payload:
            raise _failed(f"{entry['path']!r} links to something other than the frozen target bytes")
        return
    if not stat.S_ISREG(info.st_mode):
        raise _failed(f"{entry['path']!r} is not a regular file in the workspace")
    if target.read_bytes() != payload:
        raise _failed(f"{entry['path']!r} does not hold the frozen bytes in the workspace")
    if sys.platform != "win32" and kind == "file":
        executable = bool(info.st_mode & stat.S_IXUSR)
        if executable != (entry["new_mode"] == "100755"):
            raise _failed(f"{entry['path']!r} does not carry the executable bit of mode {entry['new_mode']}")
