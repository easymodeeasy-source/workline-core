"""The resulting tree of a frozen Candidate: the exact tree identity that exists before K1 does.

``F3`` §7.9.2 defines it in one sentence, and the sentence is the whole design:

```text
resulting tree = the base tree with this Candidate's entries applied - every changing entry at
                 its new kind, mode and object id, every deletion absent. It is fully determined
                 by the Candidate and declared_base, so it is computable BEFORE K1 exists and
                 before the Review is even launched.
```

That "before K1 exists" is what this module is for. The seal's capability claim (§7.9.3) is about
a tree, not a commit, and the Work Review Context binds that tree's object id (§7.9.6) while the
Review is still being launched. So nothing here creates a commit, moves a ref, or touches the
Project's index or working tree. A tree identity is not an authorization and not an ownership
claim.

**Two bases, and they are not interchangeable** (§7.1.11):

```text
PRE_S_C0_BASE               the committed HEAD immediately BEFORE S-c0. Its ROOT TREE id is what
                            the Context's review_checkout_capability.base_tree names.
declared_base.base_commit   the committed HEAD AFTER S-c0. Its tree is what the Candidate's
                            entries were measured against, so it is what the result is composed
                            from.
```

§7.1.11 proves the two carry the same ATTRIBUTE-SOURCE state, because S-c0 changes only
`.workline/events/events.jsonl`. It does not make their tree identities equal, and composing
against PRE_S_C0_BASE would silently erase S-c0's event log from the result.

**How the tree is built, and why this way.** Measured, in a bare scratch repository borrowing the
Project's objects (M-21's containment):

```text
read-tree <declared base root tree>                loads the base exactly; write-tree round-trips
                                                   it back to the same id
hash-object -w in SCRATCH                          new blobs land in the scratch object store and
                                                   are NOT readable from the Project afterwards
update-index --index-info                          one uniform feed for every change:
                                                     <mode> <oid> 0<TAB><path>   to set
                                                     000000 <zero> 0<TAB><path>  to remove
write-tree                                         the exact root tree id
```

`--index-info` rather than `--cacheinfo`/`--force-remove`: measured, `--force-remove` fails with
"this operation must be run in a work tree" in a bare repository, while `--index-info` removes an
entry there without one. It is also one mechanism for both directions instead of two.

Measured and relied on: a `160000` entry is accepted and written even when the referenced commit
object is ABSENT, so a gitlink never needs a fetch; a deletion collapses a subtree that becomes
empty, exactly as Git does; and a nested addition creates the subtrees it needs.

Measured and deliberately NOT relied on: Git does not refuse an entry placed beneath an existing
file path. `update-index --index-info` accepted `k.txt/child` beside `k.txt` and `write-tree`
succeeded. So the conflict is refused HERE, before Git is asked.

Every Project-object question runs through Unit 1's class B authority, and none of it through the
generic cached helpers - the lesson Unit 3 was repaired for: those run with `env=None`, see Git's
ordinary refs/replace view, and memoize by (kind, repo, oid) with no environment in the key.

This is a foundation. No seal, no Receipt, no generation, no START dispatch calls it.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import stat
from typing import Any, Iterator, Mapping, Sequence

from .. import gitcmd
from ..errors import StopError
from ..store import ProjectStore
from . import paths as review_paths
from .hermetic import HermeticGit

#: The object kinds a Candidate entry may carry, and the modes each one may take (``F2`` §6.3, §6.4).
#: The Git TREE ENTRY is authoritative for kind, mode and oid - never a filesystem permission, a
#: submodule's checked-out worktree or a branch tip.
KIND_MODES: Mapping[str, tuple[str, ...]] = {
    "absent": ("000000",),
    "file": ("100644", "100755"),
    "symlink": ("120000",),
    "gitlink": ("160000",),
}

#: The kinds whose bytes live in this repository, so whose blob must exist before a tree names it.
BYTE_KINDS = ("file", "symlink")

#: The statuses of ``F2`` §6.3, derived from the two sides rather than trusted.
STATUS_ADDED, STATUS_MODIFIED, STATUS_DELETED = "A", "M", "D"

#: What an ``update-index --index-info`` record says to remove an entry.
REMOVE_MODE = "000000"

#: The entry fields a frozen Candidate carries (``F2`` §6.3), in the contract's order.
ENTRY_FIELDS = (
    "path", "status", "old_kind", "old_mode", "old_oid", "new_kind", "new_mode", "new_oid", "content_sha256",
)

_TREE_HEADER = "tree "


def _unavailable(message: str) -> StopError:
    """The resulting tree could not be determined. FC-5: a question Git cannot answer is a refusal."""
    return StopError(
        f"the resulting tree of the Candidate cannot be determined: {message}; nothing is committed: STOP",
        code="review_resulting_tree_unavailable",
    )


# --------------------------------------------------------------------------- the entries


@dataclass(frozen=True)
class Entry:
    """One frozen Candidate entry, as the tree composer needs it (``F2`` §6.3).

    A narrow typed VIEW of the record the Candidate already froze, never a second
    schema: :func:`entries_from_records` builds these from exactly the nine
    fields the contract names, so the composer and the Candidate cannot come to
    disagree about what was declared.
    """

    path: str
    status: str
    old_kind: str
    old_mode: str
    old_oid: str
    new_kind: str
    new_mode: str
    new_oid: str
    content_sha256: str | None

    @property
    def inert(self) -> bool:
        """Whether this entry declares a result that changed nothing (``F2`` §6.3).

        It stays in the Candidate - what the executor declared is part of what is
        reviewed - and applying it to the tree is a no-op. A Candidate whose
        entries are ALL inert composes to the base tree itself, which is lawful
        and is not a reason to invent a commit.
        """
        return (self.old_kind, self.old_mode, self.old_oid) == (self.new_kind, self.new_mode, self.new_oid)


def entries_from_records(records: Sequence[Mapping[str, Any]]) -> list[Entry]:
    """The frozen Candidate's entries as :class:`Entry`; anything not of the frozen shape is a refusal."""
    found: list[Entry] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise _unavailable(f"entry {index} is not a mapping")
        unknown = set(record) - set(ENTRY_FIELDS)
        missing = set(ENTRY_FIELDS) - set(record)
        if unknown or missing:
            raise _unavailable(
                f"entry {index} does not carry exactly the frozen Candidate entry fields"
                + (f"; unexpected {sorted(unknown)}" if unknown else "")
                + (f"; missing {sorted(missing)}" if missing else "")
            )
        found.append(Entry(**{field: record[field] for field in ENTRY_FIELDS}))
    return found


# --------------------------------------------------------------------------- validation


def _require_relative_path(path: object, described: str) -> str:
    """A canonical repository-relative POSIX spelling, or the entry is not placeable in a tree."""
    if not isinstance(path, str) or not path:
        raise _unavailable(f"{described} names {path!r}, which is not a path")
    if path.startswith("/") or "\\" in path or ":" in path.split("/")[0]:
        raise _unavailable(f"{described} names {path!r}, which is absolute, drive-qualified or holds a backslash")
    if any(part in ("", ".", "..") for part in path.split("/")):
        raise _unavailable(f"{described} names {path!r}, which holds an empty, `.` or `..` component")
    if "\0" in path or "\n" in path or "\t" in path:
        raise _unavailable(f"{described} names a path holding NUL, newline or tab")
    return path


def _require_side(kind: object, mode: object, oid: object, zero: str, width: int, described: str) -> None:
    """One side of an entry: the kind, its mode and its object id must be a valid triple."""
    if kind not in KIND_MODES:
        raise _unavailable(f"{described} names the kind {kind!r}, which is not one of {sorted(KIND_MODES)}")
    if mode not in KIND_MODES[kind]:
        raise _unavailable(f"{described} names {kind} with mode {mode!r}; {kind} takes {KIND_MODES[kind]}")
    if not isinstance(oid, str) or len(oid) != width or not gitcmd.full_commit_id(oid):
        raise _unavailable(
            f"{described} names the object id {oid!r}, which is not a full lowercase {width}-character id"
        )
    if kind == "absent" and oid != zero:
        raise _unavailable(f"{described} is absent but names {oid}; an absent side names the all-zero id")
    if kind != "absent" and oid == zero:
        raise _unavailable(f"{described} is {kind} but names the all-zero id")


def _require_status(entry: Entry) -> None:
    """``F2`` §6.3 derives status from the two sides; a record that disagrees is not repaired here."""
    expected = (
        STATUS_ADDED if entry.old_kind == "absent"
        else STATUS_DELETED if entry.new_kind == "absent"
        else STATUS_MODIFIED
    )
    if entry.status != expected:
        raise _unavailable(
            f"the entry for {entry.path!r} says status {entry.status!r} while its sides say {expected!r}"
        )
    if entry.old_kind == "absent" and entry.new_kind == "absent":
        raise _unavailable(f"the entry for {entry.path!r} is absent on both sides, so it declares nothing")


def _require_content_digest(entry: Entry, payload: bytes | None) -> None:
    """``content_sha256`` is null except for a file or symlink, and it must match the bytes supplied."""
    if entry.new_kind in BYTE_KINDS:
        if not isinstance(entry.content_sha256, str) or len(entry.content_sha256) != 64:
            raise _unavailable(f"the entry for {entry.path!r} is a {entry.new_kind} with no content_sha256")
        if payload is not None:
            found = hashlib.sha256(payload).hexdigest()
            if found != entry.content_sha256:
                raise _unavailable(
                    f"the bytes supplied for {entry.path!r} digest to {found}, not the "
                    f"{entry.content_sha256} the Candidate froze"
                )
    elif entry.content_sha256 is not None:
        raise _unavailable(
            f"the entry for {entry.path!r} is {entry.new_kind} and carries a content_sha256; only a file "
            "or a symlink has bytes in this repository"
        )


def _require_no_path_conflicts(entries: Sequence[Entry], base: Mapping[str, gitcmd.TreeEntry]) -> None:
    """No duplicate path, and nothing placed beneath a path that holds an object rather than a tree.

    Measured: Git accepts `a/b` beside a file `a` in `update-index --index-info`
    and `write-tree` succeeds, so this conflict is refused here rather than left
    to produce a tree nobody declared.
    """
    seen: set[str] = set()
    for entry in entries:
        if entry.path in seen:
            raise _unavailable(f"the Candidate declares {entry.path!r} more than once")
        seen.add(entry.path)
    present = {
        path for path, found in base.items() if found.type == "blob" or found.type == "commit"
    }
    remaining = (present | {e.path for e in entries if e.new_kind != "absent"}) - {
        e.path for e in entries if e.new_kind == "absent"
    }
    for entry in entries:
        if entry.new_kind == "absent":
            continue
        prefixes = entry.path.split("/")[:-1]
        for depth in range(1, len(prefixes) + 1):
            ancestor = "/".join(prefixes[:depth])
            if ancestor in remaining:
                raise _unavailable(
                    f"{entry.path!r} would be placed beneath {ancestor!r}, which holds an object rather "
                    "than a directory"
                )


def _require_old_side_agrees(entry: Entry, base: Mapping[str, gitcmd.TreeEntry], described: str) -> None:
    """The entry's old side must be exactly what the declared base's tree holds at that path."""
    found = base.get(entry.path)
    if entry.old_kind == "absent":
        if found is not None:
            raise _unavailable(
                f"{described} says the base holds nothing at {entry.path!r}, but it holds "
                f"{found.type} {found.mode} {found.oid}"
            )
        return
    if found is None:
        raise _unavailable(f"{described} names an old {entry.old_kind} at {entry.path!r}, which the base does not hold")
    if found.mode != entry.old_mode or found.oid != entry.old_oid:
        raise _unavailable(
            f"{described} names {entry.old_mode} {entry.old_oid} at {entry.path!r}, but the base holds "
            f"{found.mode} {found.oid}"
        )


# --------------------------------------------------------------------------- the class B object authority


def root_tree_id(hermetic: HermeticGit, commit: str) -> str:
    """The ROOT TREE object id of ``commit``, read from the stored commit object under class B.

    ```text
    GIT_NO_REPLACE_OBJECTS=1  GIT_NO_LAZY_FETCH=1  git cat-file commit <oid>
    ```

    and the literal ``tree <oid>`` header of the pre-blank-line block, exactly
    one of them, at the repository's own width. Never ``<rev>^{tree}`` and never
    a branch or ``HEAD``: a revision expression is not an identity, and the
    revision view is what a replacement ref changes (M-49, M-58).
    """
    if not gitcmd.full_commit_id(commit):
        raise _unavailable(f"{commit!r} is not an exact full object id, so its tree cannot be named")
    found = hermetic.run_bytes("cat-file", "commit", commit)
    if not found.ok:
        raise _unavailable(f"Git cannot read the commit object {commit}")
    block, terminator, _message = found.stdout.partition(b"\n\n")
    if not terminator:
        raise _unavailable(f"the commit object {commit} has no header block")
    headers = [line for line in block.split(b"\n") if line.startswith(_TREE_HEADER.encode())]
    if len(headers) != 1:
        raise _unavailable(f"the commit object {commit} holds {len(headers)} tree headers")
    try:
        named = headers[0][len(_TREE_HEADER):].decode("ascii")
    except UnicodeDecodeError as exc:
        raise _unavailable(f"the commit object {commit} holds a non-ASCII tree header") from exc
    if not gitcmd.full_commit_id(named) or len(named) != len(commit):
        raise _unavailable(f"the commit object {commit} names {named!r} where a full tree id belongs")
    return named


def tree_entries(hermetic: HermeticGit, tree: str, *, trees: bool = False) -> dict[str, gitcmd.TreeEntry]:
    """Every entry of ``tree``, recursively, as a CLASS B invocation parsed from bytes.

    Not ``gitcmd.tree_entries``: that runs with no class B environment and
    memoizes by an environment-blind key, which is exactly what Unit 3 was
    repaired for.
    """
    arguments = ["ls-tree", "-z", "--full-tree", "-r"] + (["-t"] if trees else []) + [tree]
    listed = hermetic.run_bytes(*arguments)
    if not listed.ok:
        raise _unavailable(f"Git cannot enumerate the tree {tree}")
    found: dict[str, gitcmd.TreeEntry] = {}
    for item in listed.stdout.split(b"\0"):
        if not item:
            continue
        head, separator, path = item.partition(b"\t")
        fields = head.split(b" ")
        if not separator or len(fields) != 3 or not path:
            raise _unavailable(f"Git's listing of {tree} holds a record this parser cannot classify")
        try:
            mode, kind, oid = (field.decode("ascii") for field in fields)
        except UnicodeDecodeError as exc:
            raise _unavailable(f"Git's listing of {tree} holds a non-ASCII mode, type or object id") from exc
        if not gitcmd.full_commit_id(oid):
            raise _unavailable(f"Git's listing of {tree} names {oid!r} where a full object id belongs")
        # surrogateescape keeps any byte that is not UTF-8 exactly, as the repository's other raw readers do
        found[path.decode("utf-8", "surrogateescape")] = gitcmd.TreeEntry(mode, kind, oid, path.decode("utf-8", "surrogateescape"))
    return found


# --------------------------------------------------------------------------- the contained composition


def _remove_scratch(path: Path) -> bool:
    """Remove the scratch directory completely; whether nothing of it is left.

    Git stores loose objects READ-ONLY, and a plain recursive delete leaves them
    behind on Windows, so every entry is made writable first and the answer is
    read from the filesystem rather than from the delete's silence.
    """
    for parent, directories, files in os.walk(path):
        for name in (*directories, *files):
            try:
                os.chmod(os.path.join(parent, name), stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)
    return not os.path.lexists(path)


@dataclass(frozen=True)
class Composition:
    """A composed resulting tree, live inside its contained scratch repository.

    ``tree`` is the exact root tree object id. The objects behind it live only in
    the scratch store, so every question about them is asked through
    :meth:`run_bytes` while this composition is open.
    """

    tree: str
    base_tree: str
    repository: Path
    _hermetic: HermeticGit

    def run_bytes(self, *args: str) -> gitcmd.GitBytes:
        """One class B Git command inside the scratch repository."""
        return gitcmd.run_git_bytes(
            self.repository, *self._hermetic.configuration_arguments(), *args, env=self._hermetic.environment()
        )

    def entries(self, *, trees: bool = False) -> dict[str, gitcmd.TreeEntry]:
        """Every entry of the resulting tree, read inside the scratch repository."""
        arguments = ["ls-tree", "-z", "--full-tree", "-r"] + (["-t"] if trees else []) + [self.tree]
        listed = self.run_bytes(*arguments)
        if not listed.ok:
            raise _unavailable(f"Git cannot enumerate the resulting tree {self.tree}")
        found: dict[str, gitcmd.TreeEntry] = {}
        for item in listed.stdout.split(b"\0"):
            if not item:
                continue
            head, separator, path = item.partition(b"\t")
            fields = head.split(b" ")
            if not separator or len(fields) != 3 or not path:
                raise _unavailable(f"Git's listing of {self.tree} holds a record this parser cannot classify")
            try:
                mode, kind, oid = (field.decode("ascii") for field in fields)
            except UnicodeDecodeError as exc:
                raise _unavailable(f"Git's listing of {self.tree} holds a non-ASCII field") from exc
            if not gitcmd.full_commit_id(oid):
                raise _unavailable(f"Git's listing of {self.tree} names {oid!r} where a full object id belongs")
            text = path.decode("utf-8", "surrogateescape")
            found[text] = gitcmd.TreeEntry(mode, kind, oid, text)
        return found

    def read_blob(self, oid: str) -> bytes:
        """The bytes of one blob of the resulting tree; unreadable is a refusal, never a fallback."""
        found = self.run_bytes("cat-file", "blob", oid)
        if not found.ok:
            raise _unavailable(f"Git cannot read the object {oid} of the resulting tree")
        return found.stdout


@contextmanager
def composed(
    store: ProjectStore,
    hermetic: HermeticGit,
    declared_base: str,
    entries: Sequence[Entry],
    payloads: Mapping[str, bytes] | None = None,
) -> Iterator[Composition]:
    """Compose the resulting tree in a contained scratch repository, and keep it open for proofs.

    ``declared_base`` is ``declared_base.base_commit`` - the committed HEAD AFTER
    S-c0 - because that is the tree the Candidate's entries were measured
    against. Composing from ``PRE_S_C0_BASE`` instead would erase S-c0's event
    log from the result (§7.1.11).

    ``payloads`` supplies the exact bytes of every file and symlink the result
    names, keyed by path. Before K1 those blobs need not exist in the Project, so
    they are written into the SCRATCH store - and only after the bytes are proven
    to be the ones the Candidate froze: the blob id Git computes must equal
    ``new_oid`` and the SHA-256 of the bytes must equal ``content_sha256``. Bytes
    that disagree are never substituted.

    The Project is read-only throughout: its object store is borrowed through the
    scratch repository's alternates, its index, refs, HEAD and working tree are
    never touched, and nothing this composes is written into it.
    """
    payloads = dict(payloads or {})
    if not gitcmd.full_commit_id(declared_base):
        raise _unavailable(f"the declared base {declared_base!r} is not an exact full object id")
    base_tree = root_tree_id(hermetic, declared_base)
    width = len(declared_base)
    zero = gitcmd.zero_object_id(declared_base)

    base = tree_entries(hermetic, base_tree)
    for index, entry in enumerate(entries):
        described = f"the entry for {entry.path!r}"
        _require_relative_path(entry.path, f"entry {index}")
        _require_side(entry.old_kind, entry.old_mode, entry.old_oid, zero, width, f"{described} old side")
        _require_side(entry.new_kind, entry.new_mode, entry.new_oid, zero, width, f"{described} new side")
        _require_status(entry)
        _require_content_digest(entry, payloads.get(entry.path))
        _require_old_side_agrees(entry, base, described)
    _require_no_path_conflicts(entries, base)

    objects = _objects_directory(hermetic, store)
    object_format = _object_format(hermetic)
    root = store.root / review_paths.RUNTIME_RESULTING_TREE_DIR
    scratch = root / secrets.token_hex(8)
    try:
        try:
            scratch.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise _unavailable(f"the composition directory {scratch} already exists") from exc
        bare = scratch / "compose.git"
        created = gitcmd.run_git(
            None, "init", "--bare", "--quiet", "--template=", f"--object-format={object_format}", str(bare),
            check=False, env=hermetic.environment(),
        )
        if not created.ok:
            raise _unavailable(f"the composition repository could not be created: {created.stderr.strip()}")
        alternates = bare / "objects" / "info" / "alternates"
        alternates.parent.mkdir(parents=True, exist_ok=True)
        alternates.write_text(objects.as_posix() + "\n", encoding="utf-8", newline="\n")
        index_file = str(scratch / "compose-index")

        def run(*args: str, feed: bytes | None = None) -> gitcmd.GitBytes:
            return gitcmd.run_git_bytes(
                bare, *hermetic.configuration_arguments(), *args,
                input=feed, env=hermetic.environment(index_file=index_file),
            )

        loaded = run("read-tree", base_tree)
        if not loaded.ok:
            raise _unavailable(f"the base tree {base_tree} could not be loaded into the composition index")
        roundtrip = run("write-tree")
        if not roundtrip.ok or roundtrip.stdout.decode("ascii", "replace").strip() != base_tree:
            raise _unavailable(f"the composition index does not reproduce the base tree {base_tree}")

        records: list[str] = []
        for entry in entries:
            if entry.new_kind == "absent":
                records.append(f"{REMOVE_MODE} {zero} 0\t{entry.path}")
                continue
            if entry.new_kind in BYTE_KINDS:
                _materialize(run, entry, payloads)
            records.append(f"{entry.new_mode} {entry.new_oid} 0\t{entry.path}")
        if records:
            feed = ("\n".join(records) + "\n").encode("utf-8", "surrogateescape")
            applied = run("update-index", "--index-info", feed=feed)
            if not applied.ok:
                raise _unavailable(
                    "the Candidate's entries could not be applied to the composition index: "
                    + applied.stderr.decode("utf-8", "replace").strip()
                )
        written = run("write-tree")
        if not written.ok:
            raise _unavailable("the resulting tree could not be written: "
                               + written.stderr.decode("utf-8", "replace").strip())
        tree = written.stdout.decode("ascii", "replace").strip()
        if not gitcmd.full_commit_id(tree) or len(tree) != width:
            raise _unavailable(f"the resulting tree id {tree!r} is not a full object id of this repository's width")
        yield Composition(tree=tree, base_tree=base_tree, repository=bare, _hermetic=hermetic)
    finally:
        removed = _remove_scratch(scratch)
    if not removed:
        raise _unavailable(f"the composition directory {scratch} could not be removed")


def _materialize(run: Any, entry: Entry, payloads: Mapping[str, bytes]) -> None:
    """Write one file or symlink blob into the SCRATCH store, only if its identity is already proven."""
    payload = payloads.get(entry.path)
    if payload is None:
        # the blob may already be in the Project's store - a modification whose bytes were committed
        # before, or an entry the executor did not change - and the borrowed alternates make it readable
        present = run("cat-file", "-e", entry.new_oid)
        if present.ok:
            return
        raise _unavailable(
            f"the resulting tree needs the bytes of {entry.path!r} ({entry.new_oid}), which this "
            "repository does not hold and which were not supplied"
        )
    computed = run("hash-object", "-t", "blob", "--stdin", feed=payload)
    if not computed.ok:
        raise _unavailable(f"Git cannot compute the object id of the bytes supplied for {entry.path!r}")
    found = computed.stdout.decode("ascii", "replace").strip()
    if found != entry.new_oid:
        raise _unavailable(
            f"the bytes supplied for {entry.path!r} are the object {found}, not the {entry.new_oid} the "
            "Candidate froze"
        )
    written = run("hash-object", "-w", "-t", "blob", "--stdin", feed=payload)
    if not written.ok or written.stdout.decode("ascii", "replace").strip() != entry.new_oid:
        raise _unavailable(f"the bytes of {entry.path!r} could not be written into the composition store")


def _objects_directory(hermetic: HermeticGit, store: ProjectStore) -> Path:
    found = hermetic.run("rev-parse", "--git-path", "objects", check=False)
    text = found.stdout.strip()
    if not found.ok or not text:
        raise _unavailable("Git cannot name this repository's object directory")
    path = Path(text)
    if not path.is_absolute():
        path = Path(store.root) / path
    if not path.is_dir():
        raise _unavailable(f"this repository's object directory {path} is not a directory")
    return path.resolve()


def _object_format(hermetic: HermeticGit) -> str:
    found = hermetic.run("rev-parse", "--show-object-format", check=False)
    text = found.stdout.strip()
    if not found.ok or not text:
        raise _unavailable("Git cannot name this repository's object format")
    return text


def resulting_tree_id(
    store: ProjectStore,
    hermetic: HermeticGit,
    declared_base: str,
    entries: Sequence[Entry],
    payloads: Mapping[str, bytes] | None = None,
) -> str:
    """The exact root TREE object id the Candidate would produce over ``declared_base``.

    A tree id, never a commit id. It may equal the declared base's tree - an
    all-inert Candidate, or one with no entries at all - and that equality is
    lawful: no synthetic commit follows from it, because the resulting tree is a
    tree identity and nothing else.
    """
    with composed(store, hermetic, declared_base, entries, payloads) as composition:
        return composition.tree
