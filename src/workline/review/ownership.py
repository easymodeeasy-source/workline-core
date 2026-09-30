"""Reserved ownership and the bound ownership witness of a review-v1 Work completion (``F3`` §7.8.4).

IP-14 / IP-15 / IP-16. When a review-v1 Work's executor returns ``Completed``,
every declared result path and deletion path is judged BEFORE anything durably
records it as START's own, in one frozen order (``F3`` §5.1 steps 5b-6, R-6a):

```text
5b  CANONICAL SPELLING    exactly `mutation._safe_relative`; opens nothing
                          fail -> review_candidate_unavailable
5c  RESERVED OWNERSHIP    .workline/review (the root and every descendant, A-5)
                          and .workline/events/events.jsonl (exactly, A-6):
                          the ASCII-only fold as a PRE-FILTER, filesystem OBJECT
                          IDENTITY as the authority
                          match -> ReconcileRequired(reason=review_reserved_namespace)
                          identity unanswerable -> review_candidate_unavailable
5d  CONTAINMENT + WITNESS no-follow walk of the ancestors, and a per-kind witness
                          captured RELATIVE TO THE PROVEN PARENT
                          fail -> review_candidate_unavailable
6   OWNERSHIP ASSERTION   the ALREADY-BOUND witness is persisted; the declared
                          path is not resolved from the Project root again
```

A step never runs on a path an earlier step refused, and nothing is written by
any of them: on a refusal there is no ``_OWN_CONTENT`` note, no completion
precheck, no dirty-separability check, no Candidate and no Review.

**The witness is per kind** (IP-16), because a single content digest cannot
express a gitlink's referenced commit or an executable bit (M-32, M-33):

```text
file      100644 | 100755   the exact bytes and their raw Git blob id
symlink   120000            the exact link-target bytes, never followed, and their blob id
gitlink   160000            the commit the submodule's HEAD names, read through held handles
absent    000000            the tracked base identity, plus the positive absence
```

**The executable bit is Git's, not the filesystem's** (F2 §6.4). It is decided
the way Git decides it when it stages a path: from the owner-execute bit where
``core.fileMode`` says the filesystem carries one, and otherwise from the entry
the base holds at that path - ``100644`` for a path the base does not hold as a
regular file. Where ``core.symlinks`` says the filesystem cannot hold a link and
the base holds a link at the path, the plain file there is that link's target,
exactly as Git records it. The base is the persistence basis the caller names:
``PRE_S_C0_BASE`` at step 5d, which A-6 makes interchangeable with
``declared_base.base_commit`` at every declarable path (§7.8.5).

**The durable form is explicit and closed.** A witness is recorded in the
mutation's ``_OWN_CONTENT`` note as a mapping carrying
``form = "review-v1-ownership-witness-v1"``, and only in a mutation whose durable
invocation names the review-v1 Work contract. The legacy digest strings stay
the legacy form of legacy mutations and are never reinterpreted; a witness is
never read as a digest (:func:`workline.mutation._own_content` refuses one);
and any other shape, in either kind of mutation, fails closed.

This module decides nothing about Candidates, commits or Review records. It
proves what the executor left at each declared path and holds the proof.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
from typing import Any, Iterable, Mapping

from .. import gitcmd
from ..errors import ReconcileRequired, StopError, ValidationError
from ..mutation import _OWN_CONTENT, Mutation, _safe_relative, effect_path
from ..store import ProjectStore
from . import fsafe, work_invocation
from .hermetic import HermeticGit

#: The one new ReconcileRequired reason F3 introduces (IP-14), for both reserved sets alike.
RESERVED_REASON = "review_reserved_namespace"

#: F2 §6.5's projectability refusal, reused verbatim for every declaration whose identity
#: cannot be established - never merged with the ownership refusal above.
UNAVAILABLE_CODE = "review_candidate_unavailable"

#: The explicit durable form of a bound ownership witness (IP-16).
WITNESS_FORM = "review-v1-ownership-witness-v1"

KIND_FILE = "file"
KIND_SYMLINK = "symlink"
KIND_GITLINK = "gitlink"
KIND_ABSENT = "absent"

MODE_FILE = "100644"
MODE_EXECUTABLE = "100755"
MODE_SYMLINK = "120000"
MODE_GITLINK = "160000"
MODE_ABSENT = "000000"

#: Which Git modes each kind may carry; nothing else is a witness of that kind.
KIND_MODES = {
    KIND_FILE: (MODE_FILE, MODE_EXECUTABLE),
    KIND_SYMLINK: (MODE_SYMLINK,),
    KIND_GITLINK: (MODE_GITLINK,),
    KIND_ABSENT: (MODE_ABSENT,),
}

#: The modes a tracked path a deletion removes may have held in the base.
TRACKED_MODES = (MODE_FILE, MODE_EXECUTABLE, MODE_SYMLINK, MODE_GITLINK)

#: A-5: the canonical Review namespace, its ROOT included, compared component by component.
REVIEW_ROOT = (".workline", "review")
#: A-6: the lifecycle event log - exactly this one path, and nothing else in its directory.
EVENT_LOG = (".workline", "events", "events.jsonl")

_A5 = "the canonical Review namespace (.workline/review and everything under it)"
_A6 = "the lifecycle event log (.workline/events/events.jsonl)"


# --------------------------------------------------------------------------- refusals


def _unavailable(message: str) -> StopError:
    return StopError(
        f"the declared owned set cannot be projected exactly: {message}; no ownership is asserted and nothing of "
        "this completion is recorded: STOP",
        code=UNAVAILABLE_CODE,
    )


def _reserved(path: str, namespace: str) -> ReconcileRequired:
    return ReconcileRequired(
        f"the completion declares {path!r}, which lies in {namespace}; the review-v1 invocation contract reserved "
        "it before the executor ran, so START cannot own it as a result or as a deletion. No ownership is asserted "
        "and nothing of this completion is recorded; the working tree is left exactly as the executor left it: "
        "reconcile required",
        reason=RESERVED_REASON,
    )


def _malformed_note(mutation: Mutation, detail: str) -> ReconcileRequired:
    return ReconcileRequired(
        f"mutation {mutation.id}'s ownership note is not in a form this build reads ({detail}); an ownership record "
        "that cannot be read exactly is never guessed at, so nothing is committed or pushed: reconcile required"
    )


# --------------------------------------------------------------------------- lexical helpers


def ascii_fold(component: str) -> str:
    """``component`` with ASCII ``A``-``Z`` mapped to ``a``-``z`` and EVERY other code point unchanged.

    The frozen pre-filter of §7.8.4 layer 2 - not locale-aware, not the
    filesystem's comparison, not ``str.lower``/``casefold``, and never a mapping
    that can change a length or fold a non-ASCII code point. It is a
    deterministic pre-filter and never the proof: object identity is.
    """
    return "".join(chr(ord(character) + 32) if "A" <= character <= "Z" else character for character in component)


def lexically_reserved(path: str) -> str | None:
    """Which reserved set the component sequence of ``path`` names under the ASCII fold, or ``None``."""
    folded = tuple(ascii_fold(component) for component in path.split("/"))
    if folded[: len(REVIEW_ROOT)] == REVIEW_ROOT:
        return _A5
    if folded == EVENT_LOG:
        return _A6
    return None


def _utf8(path: str) -> bytes:
    return path.encode("utf-8", "surrogatepass")


def _blob_id(data: bytes, width: int) -> str:
    """The Git blob id of ``data`` in the object format a ``width``-character id names (40: SHA-1, 64: SHA-256)."""
    algorithm = "sha1" if width == 40 else "sha256"
    return hashlib.new(algorithm, b"blob %d\0" % len(data) + data).hexdigest()


def _encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _decode(text: object) -> bytes | None:
    """Strict canonical Base64 (RFC 4648 standard alphabet, padded, no whitespace), or ``None``."""
    if not isinstance(text, str):
        return None
    try:
        data = base64.b64decode(text.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError):
        return None
    return data if _encode(data) == text else None


# --------------------------------------------------------------------------- the witness


@dataclass(frozen=True)
class OwnershipWitness:
    """What a declared path held at the moment it was proven, per kind (IP-16).

    ``identity`` is a full object id: the blob id of ``material`` for a file or
    a symlink, the referenced commit for a gitlink, and for a deletion the id of
    the object the base tracks there (whose mode is ``tracked_mode``).
    ``material`` exists exactly for a file and a symlink.
    """

    path: str
    kind: str
    git_mode: str
    identity: str
    material: bytes | None = None
    tracked_mode: str | None = None

    @property
    def content_sha256(self) -> str | None:
        """SHA-256 of the material, for a kind that has material (F2 §6.3 ``content_sha256``)."""
        return None if self.material is None else hashlib.sha256(self.material).hexdigest()

    def to_record(self) -> dict[str, Any]:
        """The explicit durable form, keyed by path in the ``_OWN_CONTENT`` note."""
        record: dict[str, Any] = {
            "form": WITNESS_FORM,
            "kind": self.kind,
            "git_mode": self.git_mode,
            "identity": self.identity,
        }
        if self.material is not None:
            record["material"] = _encode(self.material)
        if self.tracked_mode is not None:
            record["tracked_mode"] = self.tracked_mode
        return record

    @staticmethod
    def from_record(path: object, record: object) -> "OwnershipWitness":
        """Read one durable witness, exactly; any deviation is a ``ValidationError`` (``review_record_invalid``).

        Every field is checked against its kind, and the material is checked
        against the identity it claims - so a record whose bytes no longer
        hash to its own id is refused rather than trusted.
        """
        def invalid(detail: str) -> ValidationError:
            return ValidationError(f"the ownership witness for {path!r} {detail}", code="review_record_invalid")

        if not isinstance(path, str) or not _safe_relative(path):
            raise invalid("is keyed by a path that is not a canonical repository-relative spelling")
        if not isinstance(record, Mapping):
            raise invalid("is not a mapping")
        if record.get("form") != WITNESS_FORM:
            raise invalid(f"names the form {record.get('form')!r}, not {WITNESS_FORM!r}")
        kind = record.get("kind")
        if kind not in KIND_MODES:
            raise invalid(f"names the kind {kind!r}")
        expected = {"form", "kind", "git_mode", "identity"}
        if kind in (KIND_FILE, KIND_SYMLINK):
            expected.add("material")
        if kind == KIND_ABSENT:
            expected.add("tracked_mode")
        if set(record) != expected:
            raise invalid(f"carries the fields {sorted(record)}, not exactly {sorted(expected)}")
        mode = record.get("git_mode")
        if mode not in KIND_MODES[kind]:
            raise invalid(f"names the mode {mode!r} for a {kind}")
        identity = record.get("identity")
        if not gitcmd.full_commit_id(identity):
            raise invalid(f"names {identity!r}, which is not a full object id")
        material = None
        if kind in (KIND_FILE, KIND_SYMLINK):
            material = _decode(record.get("material"))
            if material is None:
                raise invalid("carries material that is not canonical Base64")
            if _blob_id(material, len(identity)) != identity:
                raise invalid("carries material whose Git blob id is not its identity")
        tracked = record.get("tracked_mode")
        if kind == KIND_ABSENT and tracked not in TRACKED_MODES:
            raise invalid(f"names the tracked base mode {tracked!r}")
        return OwnershipWitness(path, kind, mode, identity, material, tracked if kind == KIND_ABSENT else None)


# --------------------------------------------------------------------------- 5c: reserved ownership (IP-14)


@dataclass(frozen=True)
class _CanonicalObjects:
    """The runtime identities of the two reserved objects, where they exist (§7.8.4 2b)."""

    review: tuple | None
    event_log: tuple | None


def _close(held: list[fsafe.SafeDirectory]) -> None:
    for directory in reversed(held):
        directory.close()


def _canonical_objects(store: ProjectStore) -> _CanonicalObjects:
    """2b: the identities of ``.workline/review`` and ``.workline/events/events.jsonl``, by no-follow metadata query.

    An indirection standing where a canonical object belongs is IDENTIFIED - its
    own identity is taken - rather than refused, so 2c/2d stay answerable. The
    one thing that cannot be answered without following anything is the event
    log beneath an ``events`` that is not a plain directory, and that is
    refused: not knowing which object the event log is, no declaration can be
    shown not to reach it.
    """
    held: list[fsafe.SafeDirectory] = []
    try:
        held.append(fsafe.SafeDirectory.open_root(store.root))
        workline = held[-1].child(".workline")
        if workline is None:
            return _CanonicalObjects(None, None)
        held.append(workline)
        review = workline.final_object("review")
        events = workline.final_object("events")
        event_log = None
        if events is not None:
            if events.is_indirection or not events.is_dir:
                raise _unavailable(
                    ".workline/events is not a plain directory, so which object the lifecycle event log is cannot "
                    "be established without following it"
                )
            events_directory = workline.child("events")
            if events_directory is not None:
                held.append(events_directory)
                log = events_directory.final_object("events.jsonl")
                event_log = None if log is None else log.identity
        return _CanonicalObjects(None if review is None else review.identity, event_log)
    except ValidationError as exc:
        raise _unavailable(f"the reserved namespaces cannot be identified without following anything ({exc})") from exc
    finally:
        _close(held)


def _physically_reserved(store: ProjectStore, path: str, canonical: _CanonicalObjects) -> str | None:
    """2a, 2c and 2d: whether ``path`` reaches a reserved OBJECT, whatever it is spelled.

    The ancestors are opened one at a time, no-follow, and each one's identity is
    taken from its own handle (2a) and compared to the Review root's (2c). The
    final component is never opened: its own identity is taken by a no-follow
    METADATA query and compared to both reserved objects (2d). A missing
    ancestor ends the walk - nothing can exist beneath it. An ancestor that is
    an indirection, or any identity that cannot be taken, is not a pass: it is
    ``review_candidate_unavailable`` (2e), never a claim that the path IS
    reserved.
    """
    parts = path.split("/")
    held: list[fsafe.SafeDirectory] = []
    try:
        held.append(fsafe.SafeDirectory.open_root(store.root))
        for name in parts[:-1]:
            child = held[-1].child(name)
            if child is None:
                return None
            held.append(child)
            if canonical.review is not None and child.identity() == canonical.review:
                return _A5
        final = held[-1].final_object(parts[-1])
        if final is not None:
            if canonical.review is not None and final.identity == canonical.review:
                return _A5
            if canonical.event_log is not None and final.identity == canonical.event_log:
                return _A6
        return None
    except ValidationError as exc:
        raise _unavailable(f"which object {path!r} reaches cannot be established without following anything ({exc})") from exc
    finally:
        _close(held)


# --------------------------------------------------------------------------- 5d: containment and the witness (IP-15)


def _base_entries(hermetic: HermeticGit, base: str, paths: list[str]) -> dict[str, gitcmd.TreeEntry]:
    """The entries ``base``'s tree holds at exactly ``paths`` (class B, literal pathspecs), parsed from bytes.

    A path holding a NUL can pass the spelling predicate (M-55) and can never be
    a tree entry - Git stores no such name - so it is not handed to Git at all:
    it simply has no base entry, and its capture refuses where it actually fails.
    """
    paths = [path for path in paths if "\0" not in path]
    if not paths:
        return {}
    listed = hermetic.run_bytes("ls-tree", "-z", "--full-tree", base, "--", *paths)
    if not listed.ok:
        raise _unavailable(f"Git cannot list what {base} holds at the declared paths")
    wanted = set(paths)
    found: dict[str, gitcmd.TreeEntry] = {}
    for item in listed.stdout.split(b"\0"):
        if not item:
            continue
        head, separator, raw_path = item.partition(b"\t")
        fields = head.split(b" ")
        if not separator or len(fields) != 3 or not raw_path:
            raise _unavailable(f"Git's listing of {base} holds a record this reader cannot classify")
        try:
            mode, kind, oid = (field.decode("ascii") for field in fields)
        except UnicodeDecodeError as exc:
            raise _unavailable(f"Git's listing of {base} holds a non-ASCII mode, type or object id") from exc
        entry_path = raw_path.decode("utf-8", "surrogateescape")
        if not gitcmd.full_commit_id(oid):
            raise _unavailable(f"Git's listing of {base} names {oid!r} where a full object id belongs")
        if entry_path in wanted:
            found[entry_path] = gitcmd.TreeEntry(mode, kind, oid, entry_path)
    return found


def _config_flag(hermetic: HermeticGit, key: str) -> bool:
    """A boolean Git setting as class B resolves it; unset is Git's default of ``true``."""
    found = hermetic.run("config", "--bool", "--get", key, check=False)
    if found.returncode == 1 and not found.stdout.strip():
        return True
    value = found.stdout.strip()
    if not found.ok or value not in ("true", "false"):
        raise _unavailable(f"Git cannot say how {key} is set, so the Git mode of a result cannot be decided")
    return value == "true"


@dataclass(frozen=True)
class _ModeRules:
    """How Git decides a staged regular file's mode here: ``core.fileMode`` and ``core.symlinks``."""

    trust_executable_bit: bool
    has_symlinks: bool


def _mode_rules(hermetic: HermeticGit) -> _ModeRules:
    return _ModeRules(_config_flag(hermetic, "core.fileMode"), _config_flag(hermetic, "core.symlinks"))


def _object_id(hermetic: HermeticGit, data: bytes, width: int) -> str:
    """The raw Git blob id of ``data`` - ``hash-object --no-filters --stdin``, writing nothing (M-40)."""
    found = hermetic.run_bytes("hash-object", "--no-filters", "-t", "blob", "--stdin", input=data)
    oid = found.stdout.decode("ascii", "replace").strip() if found.ok else ""
    if not gitcmd.full_commit_id(oid) or len(oid) != width:
        raise _unavailable("Git cannot name the object id of the bytes a declared path holds")
    return oid


def _file_witness(
    hermetic: HermeticGit, path: str, bound: fsafe.BoundFile, base_entry: gitcmd.TreeEntry | None,
    rules: _ModeRules, width: int,
) -> OwnershipWitness:
    """A regular file's witness, its kind and mode decided exactly as Git decides them when it stages the path."""
    base_mode = None if base_entry is None else base_entry.mode
    if not rules.has_symlinks and base_mode == MODE_SYMLINK:
        # Git keeps a link recorded as a link where the filesystem cannot hold one: the plain file
        # there IS the link target.
        return OwnershipWitness(path, KIND_SYMLINK, MODE_SYMLINK, _object_id(hermetic, bound.data, width), bound.data)
    if not rules.trust_executable_bit:
        mode = base_mode if base_mode in (MODE_FILE, MODE_EXECUTABLE) else MODE_FILE
    else:
        mode = MODE_EXECUTABLE if bound.executable else MODE_FILE
    return OwnershipWitness(path, KIND_FILE, mode, _object_id(hermetic, bound.data, width), bound.data)


def _capture_result(
    store: ProjectStore, hermetic: HermeticGit, path: str, base_entry: gitcmd.TreeEntry | None,
    rules: _ModeRules, width: int,
) -> OwnershipWitness:
    """5d for a RESULT: every ancestor must exist and be proven plain; the final entry is read relative to its parent.

    The chain stays held across the whole capture, and the final entry is
    identified, read or readlink'd relative to the proven parent handle - never
    reopened as ``root / path``. What is captured is bound to the object that
    was identified: an entry that changes between being identified and being
    read is refused, not witnessed.
    """
    parts = path.split("/")
    name = parts[-1]
    try:
        chain = fsafe.walk(store.root, parts[:-1])
    except ValidationError as exc:
        raise _unavailable(f"an ancestor of {path!r} is not a plain in-Project directory ({exc})") from exc
    if chain is None:
        raise _unavailable(f"an ancestor of {path!r} does not exist, so the result cannot exist")
    with chain:
        parent = chain.last
        try:
            final = parent.final_object(name)
            if final is None:
                raise _unavailable(f"{path!r} does not exist")
            if final.is_indirection:
                # the link's own identity, from the read itself, and again after it: an object swapped in
                # between identifying the name and reading it - or back again before the second look - is
                # refused, not witnessed
                link = parent.read_link(name)
                after = parent.final_object(name)
                if (link is None or link.identity != final.identity or after is None
                        or after.identity != final.identity or not after.is_indirection):
                    raise _unavailable(f"{path!r} changed while its link target was read")
                return OwnershipWitness(
                    path, KIND_SYMLINK, MODE_SYMLINK, _object_id(hermetic, link.target, width), link.target
                )
            if final.is_file:
                bound = parent.read_file_bound(name)
                if bound is None or bound.identity != final.identity:
                    raise _unavailable(f"{path!r} changed between being identified and being read")
                return _file_witness(hermetic, path, bound, base_entry, rules, width)
            if final.is_dir:
                submodule = parent.child(name)
                if submodule is None:
                    raise _unavailable(f"{path!r} disappeared while it was opened")
                try:
                    if submodule.identity() != final.identity:
                        raise _unavailable(f"{path!r} changed between being identified and being opened")
                    head = fsafe.submodule_head(fsafe.Chain(list(chain.directories) + [submodule]))
                finally:
                    submodule.close()
                if len(head) != width:
                    raise _unavailable(f"{path!r} names {head}, which is not an id of this repository's object format")
                return OwnershipWitness(path, KIND_GITLINK, MODE_GITLINK, head)
        except ValidationError as exc:
            raise _unavailable(f"{path!r} holds nothing whose Git identity can be established ({exc})") from exc
        raise _unavailable(f"{path!r} is neither a plain file, a link nor a submodule directory")


def _capture_deletion(
    store: ProjectStore, path: str, base: str, base_entry: gitcmd.TreeEntry | None
) -> OwnershipWitness:
    """5d for a DELETION: the tracked base identity, plus a POSITIVE absence.

    A missing ancestor positively proves absence - a path cannot exist beneath a
    component that does not exist - and is accepted. An EXISTING ancestor that
    is an indirection, or whose identity cannot be taken, is not: absence below
    an indirection proves nothing about the declared path. Missing is a proof;
    redirected is not.
    """
    if base_entry is None:
        raise _unavailable(f"{path!r} is declared deleted and is not a tracked path of {base}")
    if base_entry.mode not in TRACKED_MODES or base_entry.type not in ("blob", "commit"):
        raise _unavailable(f"{path!r} is declared deleted, and {base} holds it as {base_entry.type} {base_entry.mode}")
    parts = path.split("/")
    held: list[fsafe.SafeDirectory] = []
    try:
        held.append(fsafe.SafeDirectory.open_root(store.root))
        for name in parts[:-1]:
            child = held[-1].child(name)
            if child is None:
                return OwnershipWitness(path, KIND_ABSENT, MODE_ABSENT, base_entry.oid, None, base_entry.mode)
            held.append(child)
        if held[-1].final_object(parts[-1]) is not None:
            raise _unavailable(f"{path!r} is declared deleted and still exists")
    except ValidationError as exc:
        raise _unavailable(f"the absence of {path!r} cannot be proven without following anything ({exc})") from exc
    finally:
        _close(held)
    return OwnershipWitness(path, KIND_ABSENT, MODE_ABSENT, base_entry.oid, None, base_entry.mode)


def _require_base(base: object) -> str:
    if not gitcmd.full_commit_id(base):
        raise _unavailable(f"the base the witnesses are measured against must be an exact full commit id, not {base!r}")
    assert isinstance(base, str)
    return base


# --------------------------------------------------------------------------- 5b-5d, in the frozen order


def bind_declarations(
    store: ProjectStore,
    hermetic: HermeticGit,
    result_paths: Iterable[str],
    deleted_paths: Iterable[str],
    base: str,
) -> tuple[OwnershipWitness, ...]:
    """§5.1 steps 5b, 5c and 5d over every declared path, in precedence order; the bound witnesses, or a refusal.

    ``result_paths`` and ``deleted_paths`` are the declaration exactly as START's
    existing normalization leaves it (``p.replace("\\\\", "/")`` and nothing
    more, step 5a). ``base`` is the exact persistence basis - ``PRE_S_C0_BASE``
    - the deletions' tracked identities and the Git modes are measured against.

    The steps run over the whole declared set in their precedence, so the
    refusal a declaration gets is the one its earliest failing step gives:
    spelling, then reserved ownership, then containment and the witness. A
    reserved path is refused as reserved and is never downgraded to malformed
    because its final object happens to be a directory (§7.8.6). Nothing is
    written by any of it: the caller asserts ownership only with what this
    returns (:func:`assert_ownership`).

    No declared path at all is VACUOUS: nothing is opened and ``()`` is returned.
    """
    declared = [(path, False) for path in sorted(set(result_paths), key=_utf8)]
    declared += [(path, True) for path in sorted(set(deleted_paths), key=_utf8)]
    if not declared:
        return ()
    base = _require_base(base)
    for path, _ in declared:  # 5b
        if not _safe_relative(path):
            raise _unavailable(
                f"{path!r} is not a canonical repository-relative spelling; a declared path is refused, never "
                "rewritten into another one"
            )
    for path, _ in declared:  # 5c, the lexical pre-filter
        namespace = lexically_reserved(path)
        if namespace is not None:
            raise _reserved(path, namespace)
    canonical = _canonical_objects(store)  # 5c, the authority: object identity
    for path, _ in declared:
        namespace = _physically_reserved(store, path, canonical)
        if namespace is not None:
            raise _reserved(path, namespace)
    entries = _base_entries(hermetic, base, [path for path, _ in declared])  # 5d
    rules = _mode_rules(hermetic) if any(not deletion for _, deletion in declared) else None
    witnesses: list[OwnershipWitness] = []
    for path, deletion in declared:
        if deletion:
            witnesses.append(_capture_deletion(store, path, base, entries.get(path)))
        else:
            assert rules is not None
            witnesses.append(_capture_result(store, hermetic, path, entries.get(path), rules, len(base)))
    return tuple(sorted(witnesses, key=lambda witness: _utf8(witness.path)))


# --------------------------------------------------------------------------- 6: the ownership assertion (IP-16)


def _require_work_mutation(mutation: Mutation, doing: str) -> None:
    if not work_invocation.is_work(mutation.invocation):
        raise ReconcileRequired(
            f"mutation {mutation.id} is not a review-v1 Work mutation by its durable invocation, and a bound "
            f"ownership witness is that contract's form alone; nothing is {doing}: reconcile required"
        )


def own_witnesses(mutation: Mutation) -> dict[str, OwnershipWitness]:
    """The bound witnesses a review-v1 Work mutation durably holds, read exactly; any other shape fails closed.

    A legacy digest string, a malformed witness, an unknown form or a witness
    in a mutation that is not a review-v1 Work mutation is never adapted: it is
    ``reconcile_required``.
    """
    held = mutation.note(_OWN_CONTENT)
    if held is None:
        return {}
    _require_work_mutation(mutation, "read as its own")
    if not isinstance(held, dict):
        raise _malformed_note(mutation, "the note is not a mapping")
    found: dict[str, OwnershipWitness] = {}
    for path, record in held.items():
        try:
            found[path] = OwnershipWitness.from_record(path, record)
        except ValidationError as exc:
            raise _malformed_note(mutation, str(exc)) from exc
    return found


def assert_ownership(mutation: Mutation, witnesses: Iterable[OwnershipWitness]) -> None:
    """§5.1 step 6: persist the ALREADY-BOUND witnesses as this mutation's own, in one save.

    Nothing is read from the filesystem here: what is recorded is exactly what
    step 5d captured, so the object proven is the object asserted (R-6b). A
    path an effect of this mutation writes is passed over, as the legacy
    assertion passes it over - what that write recorded decides for it. A
    witness already recorded for a path is replaced by the newer capture of
    the same declaration, exactly as the legacy assertion replaces a digest;
    nothing is saved when the note would not change, so a retry that binds the
    same artifact again leaves the record byte for byte as it was.
    """
    _require_work_mutation(mutation, "asserted")
    before = own_witnesses(mutation)
    written = {effect_path(effect) for effect in mutation.effects}
    declared = {path: witness.to_record() for path, witness in before.items()}
    for witness in witnesses:
        if witness.path in written:
            continue
        declared[witness.path] = witness.to_record()
    if declared != {path: witness.to_record() for path, witness in before.items()}:
        mutation.set_note(_OWN_CONTENT, declared)


# --------------------------------------------------------------------------- currentness over the whole witness


def capture(store: ProjectStore, hermetic: HermeticGit, path: str, *, deletion: bool, base: str) -> OwnershipWitness:
    """One declared path's witness as it stands now, by the same layer-3 walk and the same rules as 5d."""
    base = _require_base(base)
    entries = _base_entries(hermetic, base, [path])
    if deletion:
        return _capture_deletion(store, path, base, entries.get(path))
    return _capture_result(store, hermetic, path, entries.get(path), _mode_rules(hermetic), len(base))


def witness_problem(store: ProjectStore, hermetic: HermeticGit, witness: OwnershipWitness, base: str) -> str | None:
    """Whether ``witness`` still describes what its path holds - kind, mode AND identity - or what differs.

    The pre-stage check of §7.8.4: the containment of the path is proven again
    by the layer-3 walk, and the WHOLE witness is compared, so a chmod (M-33), a
    changed gitlink (M-32), a changed link target or a deletion undone is seen
    where a single content digest could not see it. ``None`` when it holds.
    """
    try:
        current = capture(store, hermetic, witness.path, deletion=witness.kind == KIND_ABSENT, base=base)
    except StopError as exc:
        if exc.code != UNAVAILABLE_CODE:
            raise
        return f"{witness.path}: {exc.message}"
    if current == witness:
        return None
    changed = [
        name for name in ("kind", "git_mode", "identity", "tracked_mode")
        if getattr(current, name) != getattr(witness, name)
    ]
    return (
        f"{witness.path} now holds {current.kind} {current.git_mode} {current.identity}, not the witnessed "
        f"{witness.kind} {witness.git_mode} {witness.identity} (changed: {', '.join(changed) or 'material'})"
    )


def require_current(
    store: ProjectStore, hermetic: HermeticGit, witnesses: Iterable[OwnershipWitness], base: str
) -> None:
    """``review_candidate_unavailable`` unless every witness still holds in full (the pre-stage check)."""
    problems = [problem for witness in witnesses if (problem := witness_problem(store, hermetic, witness, base))]
    if problems:
        raise _unavailable(
            "the working tree no longer holds exactly what was witnessed when the executor returned - "
            + "; ".join(problems)
        )
