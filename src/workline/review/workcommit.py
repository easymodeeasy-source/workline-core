"""The review-v1 Work local persistence primitive, ``review-v1-work-local-v2`` (``F3`` §7.1).

Every commit a review-v1 Work operation makes - the entry-events commit S-c0,
each Work Review generation commit, every pre-completion Work stage, the result
commit K1 and the terminal commit K2 - commits a COMMIT TREE PLAN, and it is made
object by object, never by staging working-tree paths (§7.1.2):

```text
O-1  a fresh isolated GIT_INDEX_FILE under .workline/runtime/**
O-2  read-tree <plan.parent>                 never HEAD, never a branch name
O-2a every plan entry agrees with the parent tree the plan names
O-3  hash-object -w --stdin <- plan material, the id REQUIRED to equal plan.new_oid
O-4  update-index --cacheinfo / --force-remove   resolves nothing on the filesystem
O-5  write-tree, REQUIRED to be the tree the plan determines
O-6  commit-tree -p <plan.parent>, exact message, no hook, no signature
O-6a DURABLE prepared_commit_id (+ parent, tree, ref, contract) BEFORE any ref moves
O-7  update-ref <ref> <prepared> <plan.parent>     a compare-and-swap
O-7a the ref read back holding it -> commit_id + applied (C-1)
O-8  the isolated index discarded
```

``git add``, ``git commit`` and every other command that resolves a working-tree
pathname are not part of it. The one thing taken from outside Git's object store
is the plan's material, and its id is checked before anything else happens.

**Where a plan's bytes come from** (§7.1.1), and neither source is a reread of a
working-tree copy of a path the plan describes:

```text
recorded effects   the PARENT OBJECT's blob, then every recorded effect this
                   commit finalizes, applied in recorded order by the live
                   rendering rules - and the result REQUIRED to hash to the
                   digest the mutation durably recorded before it wrote (IP-22).
                   S-c0, the generation commits, the pre-completion stages, K2.
the witness        the bound ownership witness of each declared path (K1).
```

**Ownership is durable before the ref moves** (IP-18). A crash is decided from
this operation's own durable record by the matrix of §7.1.3, rows A-G, never
from the branch tip and never from "the paths no longer differ from HEAD".

**The real index is refreshed after C-1, never as a condition of it** (§7.1.4):
under an ``O_CREAT|O_EXCL`` ``index.lock`` held across the whole compare and
write, only this commit's own paths, only where the entry is still the one the
commit replaced, published by one same-directory rename. A person's staged
entry - on an unrelated path or on an own one - is never overwritten.

Every Git invocation here is class B (:class:`HermeticGit`), and every ancestry
question is answered by the RAW reader (:mod:`workline.review.ancestry`).
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil
import time
from typing import Any, Callable, Iterable, Sequence

from .. import gitcmd, yamlish
from ..errors import ReconcileRequired, StopError, ValidationError
from ..mutation import (
    FILE_EFFECT_KINDS,
    MATCHING,
    MISMATCH,
    UNAPPLIED,
    WORK_COMMIT_MODE,
    Effect,
    Mutation,
    _BYTES,
    _MADE_COMMIT,
    _last_wrote,
    appended_event_log,
    effect_path,
    rendered_ledger,
)
from ..store import Relation
from . import ancestry, hermetic as hermetic_module, ownership
from . import paths as review_paths
from .hermetic import HermeticGit

#: The one persistence contract this primitive implements (F2 §10.3 as amended by A-7).
CONTRACT = WORK_COMMIT_MODE

#: The commit classes of §7.1.1. The list is total over every commit a review-v1 Work operation makes.
CLASS_ENTRY = "entry"
CLASS_GENERATION = "generation"
CLASS_WORK_STAGE = "work-stage"
CLASS_RESULT = "result"
CLASS_TERMINAL = "terminal"
PLAN_CLASSES = (CLASS_ENTRY, CLASS_GENERATION, CLASS_WORK_STAGE, CLASS_RESULT, CLASS_TERMINAL)
#: The classes whose bytes come from recorded effects (every one but the result commit).
EFFECT_CLASSES = (CLASS_ENTRY, CLASS_GENERATION, CLASS_WORK_STAGE, CLASS_TERMINAL)

#: S-c0 commits exactly this and nothing else (§4.3, §7.1.11).
EVENT_LOG = ".workline/events/events.jsonl"

#: The prepared-commit ownership checkpoint (O-6a) - five keys, one save, before any ref moves.
PREPARED_COMMIT = "prepared_commit_id"
PREPARED_PARENT = "prepared_parent"
PREPARED_TREE = "prepared_tree"
PREPARED_REF = "prepared_ref"
PREPARED_CONTRACT = "prepared_contract"
PREPARED_KEYS = (PREPARED_COMMIT, PREPARED_PARENT, PREPARED_TREE, PREPARED_REF, PREPARED_CONTRACT)

#: Where the real-index refresh records its outcome on the commit record (IP-20).
INDEX_REFRESH = "index_refresh"

#: The two STOPs §7.1.4 R-IDX-8 names, each with its own exact identity.
LOCK_RECONCILIATION_CODE = "review_index_lock_reconciliation"
CLEANUP_CHECKPOINT_CODE = "review_local_cleanup_checkpoint"

#: How often an existing index.lock is asked for again before it is reported UNKNOWN (R-IDX-3).
LOCK_ATTEMPTS = 20
LOCK_WAIT_SECONDS = 0.1

_GIT_MODES = ("100644", "100755", "120000", "160000")
_ZERO_MODE = "000000"
_DATE = re.compile(r"[0-9]{1,15} [+-][0-9]{4}\Z")


# --------------------------------------------------------------------------- refusals


def _defect(message: str) -> StopError:
    """The plan and what it describes disagree: a defect or interference, and either way nothing to commit."""
    return StopError(f"the commit tree plan cannot be committed: {message}; nothing is committed: STOP",
                     code="review_commit_plan_invalid")


def _base_moved(message: str) -> ReconcileRequired:
    return ReconcileRequired(f"{message}: reconcile required", reason="review_registration_base_moved")


def _reconcile(message: str) -> ReconcileRequired:
    return ReconcileRequired(f"{message}: reconcile required")


# --------------------------------------------------------------------------- the plan (IP-19)


@dataclass(frozen=True)
class PlanEntry:
    """One path this commit changes: its entry in the parent and the entry it will carry.

    ``old_*`` are ``None`` where the parent holds no entry, ``new_*`` where the
    commit removes the path. ``material`` is the exact bytes, for a file or a
    symlink only; a gitlink's identity already is a commit id, and a deletion
    writes nothing.
    """

    path: str
    old_mode: str | None
    old_oid: str | None
    new_mode: str | None
    new_oid: str | None
    material: bytes | None = None

    @property
    def deleted(self) -> bool:
        return self.new_mode is None


@dataclass(frozen=True)
class CommitTreePlan:
    """What one commit commits, and nothing else (§7.1.1): exact parent, ref, message, contract, changed entries."""

    parent: str
    ref: str
    message: str
    contract: str
    plan_class: str
    entries: tuple[PlanEntry, ...]

    @property
    def paths(self) -> list[str]:
        return [entry.path for entry in self.entries]


def _utf8(path: str) -> bytes:
    return path.encode("utf-8", "surrogatepass")


def commit_date() -> str:
    """The one timestamp a commit is recorded with, in Git's own ``<seconds> <offset>`` form (§7.1.9 dates)."""
    return f"{int(time.time())} +0000"


def commit_effect(
    plan: CommitTreePlan, *, attr_basis: str, date: str | None = None, witness_basis: str | None = None
) -> Effect:
    """The recorded ``git_commit`` of a ``review-v1-work-local-v2`` commit: the plan's identity, durably.

    What the record carries is what a resume needs to rebuild the SAME plan
    from durable state alone: the exact parent, the full ref, the message, the
    class, the changed paths, the persistence basis the attribute pin names,
    the frozen timestamp and - for the result commit - the base its witnesses
    were measured against.
    """
    effect = Effect.git_commit(plan.message, plan.paths, plan.parent, plan.ref)
    effect.payload["mode"] = WORK_COMMIT_MODE
    effect.payload["plan_class"] = plan.plan_class
    effect.payload["attr_basis"] = attr_basis
    effect.payload["commit_date"] = date if date is not None else commit_date()
    if witness_basis is not None:
        effect.payload["witness_basis"] = witness_basis
    return effect


def validate_payload(payload: dict[str, Any]) -> None:
    """The closed shape of a Work-mode ``git_commit`` payload; any deviation is a ``ValidationError``."""
    expected = {"message", "paths", "base_head", "branch", "mode", "plan_class", "attr_basis", "commit_date"}
    if payload.get("plan_class") == CLASS_RESULT:
        expected.add("witness_basis")
    if set(payload) != expected:
        raise ValidationError(
            f"a {WORK_COMMIT_MODE} git_commit carries exactly {sorted(expected)}, not {sorted(payload)}"
        )
    if payload["plan_class"] not in PLAN_CLASSES:
        raise ValidationError(f"a {WORK_COMMIT_MODE} git_commit names the class {payload['plan_class']!r}")
    for key in ("base_head", "attr_basis") + (("witness_basis",) if "witness_basis" in expected else ()):
        if not gitcmd.full_commit_id(payload.get(key)):
            raise ValidationError(f"a {WORK_COMMIT_MODE} git_commit names its {key} by a full commit id")
    branch = payload.get("branch")
    if not isinstance(branch, str) or re.fullmatch(r"refs/heads/\S+", branch) is None:
        raise ValidationError(f"a {WORK_COMMIT_MODE} git_commit names its branch by its full ref name")
    if not isinstance(payload.get("commit_date"), str) or _DATE.fullmatch(payload["commit_date"]) is None:
        raise ValidationError(f"a {WORK_COMMIT_MODE} git_commit carries the timestamp it is recorded with")
    paths = payload.get("paths")
    if not isinstance(paths, list) or paths != sorted(set(paths), key=_utf8):
        raise ValidationError(f"a {WORK_COMMIT_MODE} git_commit names each changed path once, in path byte order")
    if payload["plan_class"] == CLASS_ENTRY and paths != [EVENT_LOG]:
        raise ValidationError(f"the entry-events commit commits {EVENT_LOG} and nothing else")


# --------------------------------------------------------------------------- reading the parent object


def _tree_entries(git: HermeticGit, commit: str, paths: Sequence[str]) -> dict[str, gitcmd.TreeEntry]:
    """What ``commit``'s tree holds at exactly ``paths`` (class B, literal pathspecs)."""
    wanted = [path for path in paths if "\0" not in path]
    if not wanted:
        return {}
    listed = git.run_bytes("ls-tree", "-z", "--full-tree", commit, "--", *wanted)
    if not listed.ok:
        raise _defect(f"Git cannot list what {commit} holds at the plan's paths")
    found: dict[str, gitcmd.TreeEntry] = {}
    for item in listed.stdout.split(b"\0"):
        if not item:
            continue
        head, separator, raw_path = item.partition(b"\t")
        fields = head.split(b" ")
        if not separator or len(fields) != 3 or not raw_path:
            raise _defect(f"Git's listing of {commit} holds a record this reader cannot classify")
        mode, kind, oid = (field.decode("ascii", "replace") for field in fields)
        if not gitcmd.full_commit_id(oid):
            raise _defect(f"Git's listing of {commit} names {oid!r} where a full object id belongs")
        path = raw_path.decode("utf-8", "surrogateescape")
        if path in wanted:
            found[path] = gitcmd.TreeEntry(mode, kind, oid, path)
    return found


def _read_blob(git: HermeticGit, oid: str) -> bytes:
    found = git.run_bytes("cat-file", "blob", oid)
    if not found.ok:
        raise _defect(f"Git cannot read the blob {oid} the parent holds")
    return found.stdout


def _blob_id(git: HermeticGit, data: bytes, width: int) -> str:
    """The raw blob id of ``data`` - no ``--path``, no filter - writing nothing."""
    found = git.run_bytes("hash-object", "--no-filters", "-t", "blob", "--stdin", input=data)
    oid = found.stdout.decode("ascii", "replace").strip() if found.ok else ""
    if not gitcmd.full_commit_id(oid) or len(oid) != width:
        raise _defect("Git cannot name the object id of the plan's material")
    return oid


# --------------------------------------------------------------------------- IP-22: parent-object-sourced rendering


def _universal(data: bytes, path: str) -> str:
    """The text the live reader makes of these bytes: strict UTF-8, CRLF and lone CR read as LF (``read_text``)."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _defect(f"the parent's {path} is not UTF-8 text ({exc})") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _ledger(data: bytes, path: str) -> list[Relation]:
    """A relation ledger parsed exactly as the live store reads one, from the accumulator's bytes."""
    try:
        parsed = yamlish.load(_universal(data, path))
    except yamlish.YamlishError as exc:
        raise _defect(f"{path} does not parse as a relation ledger ({exc})") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("relations"), list):
        raise _defect(f"{path} is not a relation ledger")
    relations: list[Relation] = []
    for record in parsed["relations"]:
        if not isinstance(record, dict) or not all(isinstance(record.get(k), str) for k in ("id", "type", "from", "to")):
            raise _defect(f"{path} holds a malformed relation record")
        relations.append(Relation.from_record(record))
    return relations


def render_effect(effect: dict[str, Any], accumulator: bytes, path: str) -> bytes:
    """One recorded effect applied to the ACCUMULATOR by that kind's own live rule (§7.1.1, IP-22).

    The rules are the writer's own (:func:`workline.mutation.rendered_ledger`,
    :func:`workline.mutation.appended_event_log` - what ``planned_write`` applies
    to the working tree), applied here to the parent object's bytes instead.
    Nothing under ``review/`` renders a ledger or an entity of its own.
    """
    kind, payload = effect["kind"], effect["payload"]
    if kind in ("write_file", "create_file"):
        return payload["content"].encode("utf-8")
    if kind in ("add_relation", "remove_relation"):
        return rendered_ledger(effect, _ledger(accumulator, path)).encode("utf-8")
    if kind == "append_event":
        return appended_event_log(effect, _universal(accumulator, path)).encode("utf-8")
    raise _defect(f"a {kind} effect writes no file and contributes no material")


def render(effects: Sequence[dict[str, Any]], parent_blob: Callable[[str], bytes | None]) -> dict[str, bytes]:
    """MATERIAL(path) for every path ``effects`` write: the parent object's blob, then each effect in recorded order."""
    accumulators: dict[str, bytes] = {}
    for effect in effects:
        path = effect_path(effect)
        if path is None:
            continue
        if path not in accumulators:
            held = parent_blob(path)
            accumulators[path] = b"" if held is None else held
        accumulators[path] = render_effect(effect, accumulators[path], path)
    return accumulators


def finalized_effects(effects: Sequence[dict[str, Any]], position: int) -> list[dict[str, Any]]:
    """The file effects the commit recorded at ``position`` finalizes: every one since the git_commit before it."""
    start = 0
    for index in range(position - 1, -1, -1):
        if effects[index].get("kind") == "git_commit":
            start = index + 1
            break
    return [effect for effect in effects[start:position] if effect.get("kind") in FILE_EFFECT_KINDS]


def effect_plan(
    git: HermeticGit,
    *,
    parent: str,
    ref: str,
    message: str,
    plan_class: str,
    effects: Sequence[dict[str, Any]],
) -> CommitTreePlan:
    """The plan of a commit whose bytes come from recorded effects (S-c0, generation, pre-completion stage, K2).

    MATERIAL(path) starts from the PARENT OBJECT and applies, in recorded order,
    every effect ``effects`` hold for that path - never the working-tree copy,
    which anything may have touched and which, for an append, already holds
    the event being appended. The result is then REQUIRED to hash to the
    digest the mutation durably recorded before the last of those writes: the
    two independent derivations must agree, or nothing is committed.

    Only paths whose material differs from the parent's entry are entries; a
    path the effects left exactly as the parent holds it changes nothing.
    """
    if plan_class not in EFFECT_CLASSES:
        raise _defect(f"{plan_class!r} is not a commit class whose bytes come from recorded effects")
    written = sorted({path for effect in effects if (path := effect_path(effect)) is not None}, key=_utf8)
    parent_entries = _tree_entries(git, parent, written)
    for path, entry in parent_entries.items():
        if entry.type != "blob" or entry.mode != "100644":
            raise _defect(f"{parent} holds {path} as {entry.type} {entry.mode}, not the regular file Workline writes")

    def parent_blob(path: str) -> bytes | None:
        entry = parent_entries.get(path)
        return None if entry is None else _read_blob(git, entry.oid)

    materials = render(effects, parent_blob)
    entries: list[PlanEntry] = []
    for path in written:
        material = materials[path]
        recorded = _last_wrote(list(effects), path)
        if recorded != _BYTES + hashlib.sha256(material).hexdigest():
            raise _defect(
                f"{path}: what the recorded effects render from {parent} is not what this mutation recorded writing "
                "there"
            )
        old = parent_entries.get(path)
        new_oid = _blob_id(git, material, len(parent))
        if old is not None and old.oid == new_oid:
            continue
        entries.append(PlanEntry(path, None if old is None else old.mode, None if old is None else old.oid,
                                 "100644", new_oid, material))
    if plan_class == CLASS_ENTRY:
        if [entry.path for entry in entries] != [EVENT_LOG]:
            raise _defect(f"the entry-events commit would change {[entry.path for entry in entries]}, not {EVENT_LOG}")
        held = parent_blob(EVENT_LOG) or b""
        if not entries[0].material.startswith(held):
            raise _defect("the entry-events commit is not an append to the parent's event log")
    return CommitTreePlan(parent, ref, message, CONTRACT, plan_class, tuple(entries))


# --------------------------------------------------------------------------- the result commit's plan (K1)


def result_plan(
    git: HermeticGit,
    *,
    parent: str,
    ref: str,
    message: str,
    witnesses: Sequence[ownership.OwnershipWitness],
    candidate_entries: Sequence[dict[str, Any]] | None = None,
) -> CommitTreePlan:
    """K1's plan: the bound witnesses, their CHANGING entries exactly, against ``parent``'s tree (§7.1.1 S-c1).

    An entry is changing when the parent's kind, mode or object id at that path
    differs from the witnessed one; an inert entry changes nothing and is never
    an entry of the delta (it is proven by tree containment instead, W5). The
    material is the WITNESSED bytes and nothing else.

    ``candidate_entries``, when given, are the frozen Candidate's changing
    entries in F2 §6.3's shape, and the plan must equal them field for field:
    WITNESS == CANDIDATE == PLAN.
    """
    by_path = {witness.path: witness for witness in witnesses}
    parent_entries = _tree_entries(git, parent, sorted(by_path, key=_utf8))
    entries: list[PlanEntry] = []
    for path in sorted(by_path, key=_utf8):
        witness = by_path[path]
        old = parent_entries.get(path)
        old_mode, old_oid = (None, None) if old is None else (old.mode, old.oid)
        if old is not None and (old.mode not in _GIT_MODES or old.type not in ("blob", "commit")):
            raise _defect(f"{parent} holds {path} as {old.type} {old.mode}")
        if witness.kind == ownership.KIND_ABSENT:
            if old is None:
                continue
            entries.append(PlanEntry(path, old_mode, old_oid, None, None))
            continue
        if (old_mode, old_oid) == (witness.git_mode, witness.identity):
            continue
        entries.append(PlanEntry(path, old_mode, old_oid, witness.git_mode, witness.identity, witness.material))
    plan = CommitTreePlan(parent, ref, message, CONTRACT, CLASS_RESULT, tuple(entries))
    if candidate_entries is not None:
        _require_candidate_agreement(plan, candidate_entries, len(parent))
    return plan


def _require_candidate_agreement(plan: CommitTreePlan, candidate_entries: Sequence[dict[str, Any]], width: int) -> None:
    zero = "0" * width

    def shape(entry: PlanEntry) -> tuple:
        return (entry.path, entry.old_mode or _ZERO_MODE, entry.old_oid or zero, entry.new_mode or _ZERO_MODE,
                entry.new_oid or zero)

    expected = sorted(
        ((item["path"], item["old_mode"], item["old_oid"], item["new_mode"], item["new_oid"]) for item in candidate_entries),
        key=lambda row: _utf8(row[0]),
    )
    if [shape(entry) for entry in plan.entries] != expected:
        raise _defect("the result commit's plan is not the Candidate's changing entries exactly")


# --------------------------------------------------------------------------- O-1 ... O-6: building the prepared commit (IP-17)


def isolated_index_path(root: Path, mutation_id: str, seq: int) -> Path:
    return Path(root) / review_paths.RUNTIME_WORK_INDEX_DIR / f"{mutation_id}-{seq}.index"


def _remove(path: Path) -> None:
    for candidate in (path, Path(str(path) + ".lock")):
        try:
            if os.path.lexists(candidate):
                os.chmod(candidate, 0o600)
                os.unlink(candidate)
        except OSError as exc:
            raise _defect(f"the isolated index {candidate} cannot be discarded ({exc})") from exc


def _index_entries(git: HermeticGit, index: str, paths: Sequence[str]) -> dict[str, list[tuple[str, str, str]]]:
    """``ls-files --stage`` of ``paths`` in ``index``: ``path -> [(mode, oid, stage) ...]``."""
    wanted = [path for path in paths if "\0" not in path]
    if not wanted:
        return {}
    listed = git.execute("ls-files", "--stage", "-z", "--", *wanted, index_file=index)
    if not listed.ok:
        raise _defect("Git cannot list the entries of an index this operation owns")
    found: dict[str, list[tuple[str, str, str]]] = {}
    for item in listed.stdout.split(b"\0"):
        if not item:
            continue
        head, separator, raw_path = item.partition(b"\t")
        fields = head.split(b" ")
        if not separator or len(fields) != 3:
            raise _defect("an index listing holds a record this reader cannot classify")
        mode, oid, stage = (field.decode("ascii", "replace") for field in fields)
        found.setdefault(raw_path.decode("utf-8", "surrogateescape"), []).append((mode, oid, stage))
    return found


def _tree_of(git: HermeticGit, commit: str) -> str:
    """The tree a commit object names, from the stored object itself (no replace view)."""
    found = git.run_bytes("cat-file", "commit", commit)
    if not found.ok:
        raise _defect(f"Git cannot read the commit object {commit}")
    header = found.stdout.split(b"\n", 1)[0]
    if not header.startswith(b"tree "):
        raise _defect(f"the commit object {commit} does not begin with its tree")
    tree = header[5:].decode("ascii", "replace")
    if not gitcmd.full_commit_id(tree):
        raise _defect(f"the commit object {commit} names {tree!r} as its tree")
    return tree


@dataclass(frozen=True)
class Prepared:
    commit: str
    tree: str


def _tree_delta(git: HermeticGit, old_tree: str, new_tree: str) -> list[gitcmd.DeltaEntry]:
    found = git.run_bytes("diff-tree", "-r", "-z", "--no-renames", "--no-abbrev", "--raw", old_tree, new_tree)
    if not found.ok:
        raise _defect(f"Git cannot compare {old_tree} with {new_tree}")
    items = found.stdout.split(b"\0")
    entries: list[gitcmd.DeltaEntry] = []
    index = 0
    while index < len(items):
        header = items[index]
        index += 1
        if not header:
            continue
        fields = header[1:].split(b" ")
        if not header.startswith(b":") or len(fields) != 5 or index >= len(items):
            raise _defect("a tree comparison holds a record this reader cannot classify")
        old_mode, new_mode, old_oid, new_oid, status = (field.decode("ascii", "replace") for field in fields)
        path = items[index].decode("utf-8", "surrogateescape")
        index += 1
        entries.append(gitcmd.DeltaEntry(old_mode, new_mode, old_oid, new_oid, status, path))
    return entries


def _require_planned_tree(git: HermeticGit, plan: CommitTreePlan, parent_tree: str, tree: str) -> None:
    """O-5: the tree written IS the one the plan determines - the parent's tree with exactly the plan's changes.

    A tree is determined by its parent and its delta, so the written tree is the
    planned one exactly when their complete difference is the plan's entries,
    field for field, and nothing else.
    """
    if tree == parent_tree:
        raise _defect("the tree written equals the parent's tree; an empty delta is never committed")
    zero = "0" * len(plan.parent)
    delta = {
        entry.path: (entry.old_mode, entry.old_blob, entry.new_mode, entry.new_blob)
        for entry in _tree_delta(git, parent_tree, tree)
    }
    planned = {
        entry.path: (entry.old_mode or _ZERO_MODE, entry.old_oid or zero, entry.new_mode or _ZERO_MODE,
                     entry.new_oid or zero)
        for entry in plan.entries
    }
    if delta != planned:
        raise _defect("the tree written is not the tree the plan determines")


def build(git: HermeticGit, plan: CommitTreePlan, *, index: Path, date: str) -> Prepared:
    """O-1 ... O-6: the prepared commit object, and no ref moved. The caller owns O-6a onward and O-8.

    Every step either succeeds exactly as planned or STOPs; nothing here reads a
    working-tree path. A STOP can leave unreachable blobs, trees or commits in
    the object database (§7.1.6): they move no ref, are never adopted, and are
    no evidence of anything.
    """
    if not plan.entries:
        raise _defect("the plan changes nothing; O-5/O-6 never run on an empty delta (§6.1)")
    _remove(index)  # a partially built index from an earlier attempt of this same effect has no standing
    index.parent.mkdir(parents=True, exist_ok=True)
    try:
        return _build(git, plan, str(index), date)
    except BaseException:
        _remove(index)  # a refused attempt leaves no partially built index behind
        raise


def _build(git: HermeticGit, plan: CommitTreePlan, where: str, date: str) -> Prepared:
    """O-2 ... O-6 against the fresh isolated index at ``where``."""
    # O-2 - seed from the exact parent, never HEAD or a branch
    if not git.execute("read-tree", plan.parent, index_file=where).ok:
        raise _defect(f"Git cannot read the parent {plan.parent} into the isolated index")
    # O-2a - parent agreement
    seeded = _index_entries(git, where, plan.paths)
    for entry in plan.entries:
        held = seeded.get(entry.path, [])
        expected = [] if entry.old_mode is None else [(entry.old_mode, entry.old_oid, "0")]
        if held != expected:
            raise _defect(f"the parent's entry at {entry.path} is not the one the plan was computed against")
    width = len(plan.parent)
    # O-3 - materialize from the plan only
    for entry in plan.entries:
        if entry.deleted or entry.new_mode == "160000":
            if entry.material is not None:
                raise _defect(f"{entry.path} carries material its kind does not have")
            continue
        if entry.material is None:
            raise _defect(f"{entry.path} has no material to write")
        written = git.execute("hash-object", "-w", "--no-filters", "-t", "blob", "--stdin", input=entry.material)
        oid = written.stdout.decode("ascii", "replace").strip() if written.ok else ""
        if oid != entry.new_oid or len(oid) != width:
            raise _defect(f"the object written for {entry.path} is {oid or 'nothing'}, not the planned {entry.new_oid}")
    # O-4 - place by identity, not by path resolution
    for entry in plan.entries:
        if entry.deleted:
            placed = git.execute("update-index", "--force-remove", "--", entry.path, index_file=where)
        else:
            placed = git.execute("update-index", "--add", "--cacheinfo",
                                 f"{entry.new_mode},{entry.new_oid},{entry.path}", index_file=where)
        if not placed.ok:
            raise _defect(f"Git refuses to place {entry.path} in the isolated index "
                          f"({placed.stderr.decode('utf-8', 'replace').strip()})")
    # O-5 - write the tree, exactly the planned one
    tree_found = git.execute("write-tree", index_file=where)
    tree = tree_found.stdout.decode("ascii", "replace").strip() if tree_found.ok else ""
    if not gitcmd.full_commit_id(tree):
        raise _defect("Git cannot write the planned tree")
    _require_planned_tree(git, plan, _tree_of(git, plan.parent), tree)
    # O-6 - the commit object: exact parent, exact message bytes, no hook, no signature
    made = git.execute("commit-tree", tree, "-p", plan.parent, "--no-gpg-sign", "-F", "-",
                       input=plan.message.encode("utf-8"), date=date)
    commit = made.stdout.decode("ascii", "replace").strip() if made.ok else ""
    if not gitcmd.full_commit_id(commit) or len(commit) != width:
        raise _defect(f"Git cannot write the commit object ({made.stderr.decode('utf-8', 'replace').strip()})")
    return Prepared(commit, tree)


# --------------------------------------------------------------------------- the prepared object and the ref


def ref_value(git: HermeticGit, ref: str) -> str | None:
    """What the full ref ``ref`` names now, matched by its exact name; ``None`` when it does not exist.

    A question Git cannot answer is a STOP, never "absent": a ref this operation
    advances is read only to ask whether it holds an id recorded beforehand.
    """
    found = git.run("for-each-ref", "--format=%(refname)%00%(objectname)", ref, check=False)
    if not found.ok:
        raise _reconcile(f"Git cannot say what {ref} names")
    values = []
    for line in found.stdout.splitlines():
        name, separator, value = line.partition("\0")
        if separator and name == ref:
            values.append(value.strip())
    if len(values) > 1 or (values and not gitcmd.full_commit_id(values[0])):
        raise _reconcile(f"Git does not give one full object id for {ref}")
    return values[0] if values else None


def _head_ref(git: HermeticGit) -> str | None:
    found = git.run("symbolic-ref", "-q", "HEAD", check=False)
    return found.stdout.strip() if found.ok and found.stdout.strip() else None


@dataclass(frozen=True)
class _StoredCommit:
    tree: str
    parents: tuple[str, ...]
    message: bytes


def _stored_commit(git: HermeticGit, commit: str) -> _StoredCommit | None:
    """The commit object ``commit`` exactly as stored, or ``None`` when it is missing, not a commit, or malformed."""
    kind = git.run_bytes("cat-file", "-t", commit)
    if not kind.ok or kind.stdout.strip() != b"commit":
        return None
    found = git.run_bytes("cat-file", "commit", commit)
    if not found.ok:
        return None
    header, terminator, message = found.stdout.partition(b"\n\n")
    if not terminator:
        return None
    lines = header.split(b"\n")
    if not lines or not lines[0].startswith(b"tree "):
        return None
    parents = ancestry.raw_parents(git, commit)
    if isinstance(parents, ancestry.Answer):
        return None
    return _StoredCommit(lines[0][5:].decode("ascii", "replace"), tuple(parents), message)


def _require_prepared_object(git: HermeticGit, record: dict[str, Any]) -> None:
    """§7.1.3 row B: THAT object, exactly - exists, is a commit, tree, parent and message as recorded. Else row E."""
    payload = record["payload"]
    stored = _stored_commit(git, record[PREPARED_COMMIT])
    if stored is None:
        raise _reconcile(
            f"this mutation durably recorded preparing the commit {record[PREPARED_COMMIT]}, and the repository no "
            "longer holds it as a readable commit; it is never rebuilt or replaced by another"
        )
    if (
        stored.tree != record[PREPARED_TREE]
        or stored.parents != (record[PREPARED_PARENT],)
        or stored.message != payload["message"].encode("utf-8")
    ):
        raise _reconcile(
            f"the object {record[PREPARED_COMMIT]} is not the commit this mutation prepared (tree, parent or "
            "message differ); it is never adopted"
        )


def _cas(git: HermeticGit, ref: str, commit: str, parent: str) -> None:
    """O-7: advance ``ref`` to ``commit`` only while it still names ``parent``. A wrong old value refuses."""
    moved = git.run("update-ref", ref, commit, parent, check=False)
    if not moved.ok:
        raise _base_moved(
            f"{ref} is no longer {parent}, the exact parent this commit was built on ({moved.stderr.strip()}); the "
            "prepared commit is never moved onto another tip, rebuilt against it or published"
        )


def _promote(mutation: Mutation, git: HermeticGit, record: dict[str, Any]) -> None:
    """O-7a: C-1, once the ref is read back holding exactly the prepared id."""
    ref, prepared = record[PREPARED_REF], record[PREPARED_COMMIT]
    if ref_value(git, ref) != prepared:
        raise _reconcile(f"{ref} was not read back holding the prepared commit {prepared}; C-1 is not recorded")
    record[_MADE_COMMIT] = prepared
    record["applied"] = True
    mutation._save()


# --------------------------------------------------------------------------- the whole sequence, and its resume


def is_work_commit(record: dict[str, Any]) -> bool:
    payload = record.get("payload")
    return record.get("kind") == "git_commit" and isinstance(payload, dict) and payload.get("mode") == WORK_COMMIT_MODE


def plan_for(mutation: Mutation, git: HermeticGit, effects: Sequence[dict[str, Any]], position: int,
             record: dict[str, Any], *, candidate_entries: Sequence[dict[str, Any]] | None = None) -> CommitTreePlan:
    """The plan of the recorded commit at ``position``, rebuilt from durable state alone."""
    payload = record["payload"]
    common = {"parent": payload["base_head"], "ref": payload["branch"], "message": payload["message"]}
    if payload["plan_class"] == CLASS_RESULT:
        if finalized_effects(effects, position):
            raise _defect("file effects this mutation recorded wait uncommitted before the result commit")
        witnesses = ownership.own_witnesses(mutation)
        missing = [path for path in payload["paths"] if path not in witnesses]
        if missing:
            raise _defect(f"no bound ownership witness is recorded for {missing}")
        chosen = [witnesses[path] for path in payload["paths"]]
        ownership.require_current(mutation.store, git, chosen, payload["witness_basis"])
        plan = result_plan(git, witnesses=chosen, candidate_entries=candidate_entries, **common)
    else:
        plan = effect_plan(git, plan_class=payload["plan_class"], effects=finalized_effects(effects, position), **common)
    if plan.paths != list(payload["paths"]):
        raise _defect(f"the plan changes {plan.paths}, and the recorded commit names {payload['paths']}")
    return plan


def preflight(mutation: Mutation, git: HermeticGit, record: dict[str, Any]) -> None:
    """§7.3: the Git persistence preflight for exactly this commit's path set, under the pin it commits with.

    Evaluated against the recorded persistence basis (``attr.tree`` and
    ``--source`` the same exact id), never the working tree, and never carried
    from another commit: a pass proven for paths A says nothing about paths B.
    """
    from . import attributes

    payload = record["payload"]
    attributes.require_pinned_path_evaluation(mutation.store, git, payload["attr_basis"], list(payload["paths"]))


def require_recordable(mutation: Mutation, effects: Sequence[dict[str, Any]], position: int, record: dict[str, Any]) -> None:
    """Before a Work-mode commit is written into the record: its plan can be built exactly, from durable state.

    The same proof the commit is held to when it is made, made first so that a
    commit that cannot be shown to be exactly this mutation's own leaves no Git
    stage behind (BL-053's discipline, for the object-driven primitive) - and
    the §7.3 preflight over exactly its path set, under its pin, which "FAILS
    CLOSED before that commit is recorded".
    """
    git = hermetic_module.enter(mutation.store)
    if ref_value(git, record["payload"]["branch"]) != record["payload"]["base_head"]:
        raise _base_moved(
            f"{record['payload']['branch']} is not {record['payload']['base_head']}, the exact parent this commit is "
            "recorded to be built on"
        )
    plan_for(mutation, git, effects, position, record)
    preflight(mutation, git, record)


def _make(mutation: Mutation, git: HermeticGit, record: dict[str, Any], plan: CommitTreePlan) -> None:
    """O-1 ... O-8 for a commit nothing of which is owned yet (§7.1.3 row A)."""
    index = isolated_index_path(mutation.store.root, mutation.id, int(record["seq"]))
    try:
        prepared = build(git, plan, index=index, date=record["payload"]["commit_date"])
        # O-6a - one durable save, before any ref moves
        record.update({
            PREPARED_COMMIT: prepared.commit,
            PREPARED_PARENT: plan.parent,
            PREPARED_TREE: prepared.tree,
            PREPARED_REF: plan.ref,
            PREPARED_CONTRACT: plan.contract,
        })
        mutation._save()
        _cas(git, plan.ref, prepared.commit, plan.parent)  # O-7
        _promote(mutation, git, record)  # O-7a
    finally:
        _remove(index)  # O-8


def _require_prepared_consistent(record: dict[str, Any]) -> None:
    payload = record["payload"]
    if (
        not gitcmd.full_commit_id(record.get(PREPARED_COMMIT))
        or record.get(PREPARED_PARENT) != payload.get("base_head")
        or record.get(PREPARED_REF) != payload.get("branch")
        or record.get(PREPARED_CONTRACT) != WORK_COMMIT_MODE
        or not gitcmd.full_commit_id(record.get(PREPARED_TREE))
    ):
        raise _reconcile("the prepared-commit checkpoint does not agree with the commit it was recorded for")


def replay(mutation: Mutation, effects: list[dict[str, Any]], position: int, record: dict[str, Any]) -> str:
    """Classify and make the Work-mode commit at ``position``, by §7.1.3's matrix; the classification it had.

    Decided from this operation's own durable record, never from the branch tip:

    ```text
    A  no prepared id, ref == parent            build it from the start (O-1 ... O-8)
    B  prepared id,    ref == parent            re-verify THAT object, retry the CAS of THAT id
    C  prepared id,    ref == prepared id       C-1 recovered positively from the own record
    D  prepared id,    ref elsewhere            reconcile, review_registration_base_moved
    E  prepared id,    object missing/corrupt   fail closed
    F  prepared id,    ref descends from it     reconcile (RAW ancestry, never merge-base)
    G  C-1 complete                             C-1 stands; only the index refresh may be owed
    ```

    HEAD must be on the recorded branch throughout: a commit this mutation
    records is made only on the branch it was recorded on.
    """
    payload = record["payload"]
    git = hermetic_module.enter(mutation.store)
    ref, parent = payload["branch"], payload["base_head"]
    if _head_ref(git) != ref:
        raise _reconcile(
            f"HEAD is not on {ref}, the branch mutation {mutation.id} recorded its commit (effect {record['seq']}) "
            "on; nothing is committed on another branch"
        )
    made = record.get(_MADE_COMMIT)
    if record.get("applied") is True and gitcmd.full_commit_id(made):
        tip = ref_value(git, ref)
        if tip is None or ancestry.raw_descends_from(git, tip, made) is not True:
            raise _reconcile(f"{ref} no longer holds {made}, the commit mutation {mutation.id} made (effect {record['seq']})")
        _finish_index(mutation, git, record)  # row G
        return MATCHING
    if record.get("applied") is True:
        raise _reconcile(f"effect {record['seq']} is recorded applied without the commit it made; C-1 is never inferred")
    tip = ref_value(git, ref)
    if PREPARED_COMMIT not in record:
        if tip != parent:  # row A needs the ref still at the exact parent; L-5: no independent-advance allowance
            raise _base_moved(f"{ref} is {tip}, not {parent}, the exact parent the commit of effect {record['seq']} "
                              "is built on")
        plan = plan_for(mutation, git, effects, position, record)
        preflight(mutation, git, record)  # immediately before the commit, once more: a pass does not carry
        _make(mutation, git, record, plan)
        _finish_index(mutation, git, record)
        return UNAPPLIED
    _require_prepared_consistent(record)
    prepared = record[PREPARED_COMMIT]
    if tip == parent:  # row B
        _require_prepared_object(git, record)
        _cas(git, ref, prepared, parent)
        _promote(mutation, git, record)
        _finish_index(mutation, git, record)
        return UNAPPLIED
    if tip == prepared:  # row C
        _require_prepared_object(git, record)
        _promote(mutation, git, record)
        _finish_index(mutation, git, record)
        return UNAPPLIED
    _require_prepared_object(git, record)  # row E before D/F
    if tip is not None and ancestry.raw_descends_from(git, tip, prepared) is True:  # row F
        raise _reconcile(
            f"{ref} has moved on past {prepared}, the commit this mutation prepared; the later branch state is never "
            "taken for this stage's result"
        )
    raise _base_moved(f"{ref} is {tip}, neither {parent} nor the prepared {prepared}")  # row D


def classify(mutation_store, record: dict[str, Any]) -> str:
    """A side-effect-free classification of a Work-mode commit, for readers that only ask.

    MATCHING only for a commit C-1 owns that the recorded branch still holds;
    UNAPPLIED while §7.1.3 says the commit can still be made or promoted (rows
    A, B and C); MISMATCH for everything else. Never "nothing left to commit",
    never a message, never the tip.
    """
    payload = record["payload"]
    git = hermetic_module.enter(mutation_store)
    ref = payload["branch"]
    if _head_ref(git) != ref:
        return MISMATCH
    tip = ref_value(git, ref)
    made = record.get(_MADE_COMMIT)
    if record.get("applied") is True:
        if not gitcmd.full_commit_id(made) or tip is None:
            return MISMATCH
        return MATCHING if ancestry.raw_descends_from(git, tip, made) is True else MISMATCH
    if tip == payload.get("base_head") or (PREPARED_COMMIT in record and tip == record[PREPARED_COMMIT]):
        return UNAPPLIED
    return MISMATCH


# --------------------------------------------------------------------------- §7.1.4: the real index (IP-24 / IP-20)


def _git_dir(git: HermeticGit) -> Path:
    found = git.run("rev-parse", "--absolute-git-dir", check=False)
    text = found.stdout.strip()
    if not found.ok or not text:
        raise _cleanup("Git cannot name this repository's directory")
    return Path(text)


def _cleanup(message: str) -> StopError:
    return StopError(
        f"LOCAL CLEANUP CHECKPOINT: {message}. The commit this operation made stays owned and on its branch; only "
        "the refresh of the real index is outstanding, and the same pending operation finishes it when run again: "
        "STOP",
        code=CLEANUP_CHECKPOINT_CODE,
    )


def _acquire(lock: Path) -> int:
    """R-IDX-3: create ``index.lock`` O_CREAT|O_EXCL, retrying briefly; a lock that stays is UNKNOWN."""
    for attempt in range(LOCK_ATTEMPTS):
        try:
            return os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o644)
        except FileExistsError:
            time.sleep(LOCK_WAIT_SECONDS)
        except OSError as exc:
            raise StopError(
                f"INDEX LOCK RECONCILIATION: {lock} cannot be created ({exc}); nothing about the index is changed: STOP",
                code=LOCK_RECONCILIATION_CODE,
            ) from exc
    raise StopError(
        f"INDEX LOCK RECONCILIATION: {lock} exists and stays; a lockfile carries no owner, so whose it is is "
        "UNKNOWN and it is never deleted here. The commit this operation made stays owned and on its branch; once "
        "the stale Git lock is resolved, the same pending operation finishes the index refresh: STOP",
        code=LOCK_RECONCILIATION_CODE,
    )


def _publish_snapshot(snapshot: Path, index: Path) -> None:
    """R-IDX-6: publish the snapshot over the real index in one same-directory rename, as Git's own protocol does."""
    os.replace(snapshot, index)


def refresh_real_index(git: HermeticGit, parent: str, commit: str) -> dict[str, list[str]]:
    """§7.1.4: bring the real index's entries for this commit's OWN paths to what it committed, where safe.

    Under ``<git-dir>/index.lock`` held from the first read to the final
    rename: the index is snapshotted, each own path's entry is compared with
    the entry this commit replaced, and only an entry still exactly that is
    rewritten - in the snapshot. A person's entry is never overwritten, on an
    unrelated path or on an own one. The snapshot is renamed over the index in
    one step; any failure before that leaves the index exactly as it was.
    """
    delta = _tree_delta(git, _tree_of(git, parent), _tree_of(git, commit))
    git_dir = _git_dir(git)
    lock_path = git_dir / "index.lock"
    index_path = git_dir / "index"
    snapshot = git_dir / f"wl-index-{secrets.token_hex(8)}.tmp"
    handle = _acquire(lock_path)
    refreshed: list[str] = []
    foreign: list[str] = []
    try:
        try:
            if index_path.exists():
                shutil.copyfile(index_path, snapshot)
            current = _index_entries(git, str(snapshot), [entry.path for entry in delta])
            for entry in delta:
                old = [] if entry.old_mode == _ZERO_MODE else [(entry.old_mode, entry.old_blob, "0")]
                new = [] if entry.new_mode == _ZERO_MODE else [(entry.new_mode, entry.new_blob, "0")]
                held = current.get(entry.path, [])
                if held == new:
                    continue
                if held != old:
                    foreign.append(entry.path)
                    continue
                if entry.new_mode == _ZERO_MODE:
                    written = git.execute("update-index", "--force-remove", "--", entry.path, index_file=str(snapshot))
                else:
                    written = git.execute("update-index", "--add", "--cacheinfo",
                                          f"{entry.new_mode},{entry.new_blob},{entry.path}", index_file=str(snapshot))
                if not written.ok:
                    raise _cleanup(f"the index entry for {entry.path} cannot be written")
                refreshed.append(entry.path)
            if refreshed:
                _publish_snapshot(snapshot, index_path)
        except StopError:
            raise
        except OSError as exc:
            raise _cleanup(f"the real index cannot be replaced ({exc})") from exc
    finally:
        try:
            if snapshot.exists():
                snapshot.unlink()
        except OSError:
            pass
        os.close(handle)
        os.unlink(lock_path)
    return {"refreshed": sorted(refreshed, key=_utf8), "foreign": sorted(foreign, key=_utf8)}


def _finish_index(mutation: Mutation, git: HermeticGit, record: dict[str, Any]) -> None:
    """Row G: C-1 stands; the refresh runs once, and its outcome is recorded on the commit's record."""
    if isinstance(record.get(INDEX_REFRESH), dict):
        return
    outcome = refresh_real_index(git, record["payload"]["base_head"], record[_MADE_COMMIT])
    record[INDEX_REFRESH] = outcome
    mutation._save()


# --------------------------------------------------------------------------- IP-23: a Work Review Run's own generation commits


def generation_commit_effect(mutation: Mutation, message: str) -> Effect:
    """The commit a Work Review Run's generation mutation records (``F3`` §7.1.7, C3-1).

    Work mode, and its plan built from the recorded immutable creates - the
    exact bytes P1's serializer produced, never a reread of the files they
    wrote. The discriminator that brings a generation here is its durable
    ``review_kind`` (:func:`workline.roadmap_review._finish_generation`), never
    the calling code path; every planning kind keeps the planning primitive
    exactly as it is.
    """
    basis = mutation.invocation.get("persistence_basis")
    branch = mutation.invocation.get("persistence_branch")
    if not gitcmd.full_commit_id(basis) or not isinstance(branch, str) or not branch.startswith("refs/heads/"):
        raise _defect(
            "a Work Review generation mutation names the exact persistence basis its commits pin to and the "
            "declared branch they advance, and this one does not"
        )
    git = hermetic_module.enter(mutation.store)
    ref = _head_ref(git)
    parent = None if ref is None else ref_value(git, ref)
    if ref is None or parent is None:
        raise _defect("HEAD is not on a branch holding a commit, so the generation commit has no exact parent")
    if ref != branch:
        raise _reconcile(
            f"HEAD is on {ref}, and the Work Review's generation commits advance {branch}, the branch its Candidate "
            "declared (F3 §7.1.5); nothing is committed on another branch"
        )
    effects = mutation.effects
    plan = effect_plan(git, parent=parent, ref=ref, message=message, plan_class=CLASS_GENERATION,
                       effects=finalized_effects(effects, len(effects)))
    return commit_effect(plan, attr_basis=basis)


def stage_commit_effect(mutation: Mutation, message: str, *, plan_class: str) -> Effect | None:
    """A review-v1 Work mutation's own Git stage: S-c0 (``entry``) or a pre-completion stage (``work-stage``).

    Its plan is the parent object plus the file effects this mutation recorded
    since its last commit - never the working tree - and ``None`` when that plan
    changes nothing, so no stage is recorded (§4.3: "only when there is something
    to commit"). The pin is the commit's own exact parent, the ``base_head`` its
    payload records. For S-c0 that parent IS ``PRE_S_C0_BASE`` (§7.1.11); a
    pre-completion stage is made before any declared base exists, so it is
    pinned to its own parent too (C3-2), and no START-owned write ever touches
    an attribute source.
    """
    if plan_class not in (CLASS_ENTRY, CLASS_WORK_STAGE):
        raise _defect(f"{plan_class!r} is not a class a review-v1 Work mutation's own Git stage is made in")
    git = hermetic_module.enter(mutation.store)
    ref = _head_ref(git)
    parent = None if ref is None else ref_value(git, ref)
    if ref is None or parent is None:
        raise _defect("HEAD is not on a branch holding a commit, so the stage commit has no exact parent")
    effects = finalized_effects(mutation.effects, len(mutation.effects))
    changed = effect_plan(git, parent=parent, ref=ref, message=message, plan_class=CLASS_WORK_STAGE, effects=effects)
    if not changed.entries:
        return None
    plan = changed if plan_class == CLASS_WORK_STAGE else effect_plan(
        git, parent=parent, ref=ref, message=message, plan_class=plan_class, effects=effects
    )
    return commit_effect(plan, attr_basis=parent)


def terminal_commit_effect(mutation: Mutation, message: str, *, attr_basis: str) -> Effect:
    """S-c2's commit (``F3`` §7.1.1, the K2 class): the terminal stage's recorded effects over the exact parent.

    Its bytes are the parent object plus the effects the terminal stage
    recorded - the two appended events and the Consumption's immutable create -
    and never a reread of either file. It is pinned to ``declared_base.base_commit``
    (§7.1.11).
    """
    git = hermetic_module.enter(mutation.store)
    ref = _head_ref(git)
    parent = None if ref is None else ref_value(git, ref)
    if ref is None or parent is None:
        raise _defect("HEAD is not on a branch holding a commit, so the terminal commit has no exact parent")
    effects = finalized_effects(mutation.effects, len(mutation.effects))
    plan = effect_plan(git, parent=parent, ref=ref, message=message, plan_class=CLASS_TERMINAL, effects=effects)
    return commit_effect(plan, attr_basis=attr_basis)


def require_generation_persisted(mutation: Mutation, expected: dict[str, bytes]) -> None:
    """``R3`` §10 for a Work Review generation: the commit C-1 owns holds every record's exact bytes, on its branch.

    Read from the owned commit's own tree, through class B, and then the live
    persistence gate over the working tree and index, which is what a later
    external launch relies on.
    """
    from . import gate

    git = hermetic_module.enter(mutation.store)
    commits = [effect for effect in mutation.effects if is_work_commit(effect)]
    if len(commits) != 1 or commits[0].get("applied") is not True or not gitcmd.full_commit_id(commits[0].get(_MADE_COMMIT)):
        raise _defect("the generation mutation does not hold exactly one Work-mode commit that C-1 owns")
    commit, ref = commits[0][_MADE_COMMIT], commits[0]["payload"]["branch"]
    tip = ref_value(git, ref)
    if tip is None or ancestry.raw_descends_from(git, tip, commit) is not True:
        raise _defect(f"{ref} does not hold {commit}, the generation commit this mutation made")
    held = _tree_entries(git, commit, sorted(expected, key=_utf8))
    for path, data in sorted(expected.items()):
        entry = held.get(path)
        if entry is None or entry.type != "blob" or entry.mode != "100644" or _read_blob(git, entry.oid) != data:
            raise StopError(
                f"{path} is not committed at {commit} as a 100644 blob of its canonical bytes, so the committed "
                "Review record is not the material a clone would reconstruct from: STOP",
                code="review_not_persisted",
            )
    gate.require_persisted(mutation.store, sorted(expected))
