"""Mutation Controller: durable write-ahead recovery intent and effect application.

Contract (``rules/git`` / Mutation Controller, Multi-write mutation):

* every state-changing operation has one owner and a stable ``mutation_id``
  (``mut_<ULID>``);
* the recovery intent (owner, invocation, write scope, reserved IDs, decided
  effects with expectations) is written durably to
  ``.workline/runtime/mutations/<mutation_id>.yaml`` **before** the first
  domain effect, and every later effect is appended durably before it runs;
* on resume every recorded effect is classified against reality as
  unapplied / applied-matching / applied-mismatch, and a mismatch stops the
  operation as ``reconcile required``;
* a relation the mutation added and a later stage of its own removed exactly is
  applied while its file does not hold it, and never written again only to be
  removed again (:func:`_classify_recorded`);
* an effect that decides Project content is recorded with the branch it was
  decided on, and until the commit that finalizes it is recorded - which then
  names that same branch - nothing of the mutation is replayed or recorded on
  any other (:func:`_open_decision`);
* a commit the mutation makes is recorded with the ID of the commit it made, in
  the same durable save that records it applied, and on the branch it was
  recorded on it is recognized by that ID alone, never by its message
  (:func:`_made_commit_held`);
* a recorded push publishes the commit its own Git stage made, by that ID, and
  nothing a later commit put on the branch: it is classified by where that
  commit stands at the destination and pushed as that commit alone, and a push
  whose commit cannot be shown that way is not made
  (:func:`_recorded_publication`);
* every write to a Project file records what the path held before it and what it
  wrote there, and a path is written again, and committed, only while it still
  holds exactly that: owning the path is not owning the bytes, so a change
  another subject made to it after the operation began is never written over,
  taken into the mutation's own state, or committed as its own
  (:func:`_require_own_bytes_before_write`, :func:`_require_own_bytes_committed`);
* an effect the mutation applied and a recorded commit finalizes is written
  again only on the branch that commit names: a resume that would write it
  anywhere else stops before anything is replayed or recorded
  (:func:`_require_finalized_branch`);
* a mutation of an established Project is opened, resumed and written only
  while its operation holds the Project execution lock
  (:mod:`workline.oplock`), which an operation receives only after passing the
  Project context check (:mod:`workline.context`); initial Project開始 is
  outside the lock, and its mutation is written only inside the authorization
  a running Project開始 grants for its own target root;
* the controller validates and physically writes decided payloads. It never
  decides domain meaning.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterable

from . import gitcmd, oplock, pushurl, yamlish
from .context import pre_project_authorized, same_directory
from .destination import resolve_active_push_locator, verify_recorded_destination
from .durable import DurableWriteError, durable_write_text
from .errors import GitError, ReconcileRequired, StopError, ValidationError
from .ids import is_valid_id, kind_of, new_id
from .store import (
    ENTITY_DIRS,
    INFRA_WRITE_PATHS,
    MUTATIONS_DIR,
    PRE_PROJECT_OWNERS,
    PHASE_EVENTS,
    PHASE_TERMINAL_EVENTS,
    PIN_OWNERS,
    PROJECT_YAML_REL,
    RELATED_TYPES,
    ROADMAP_EVENTS,
    ROADMAP_RELATION_TYPES,
    ROADMAP_TERMINAL_EVENTS,
    RUNTIME_DIR,
    WORK_EVENTS,
    WORK_TERMINAL_EVENTS,
    WORKLINE_DIR,
    Event,
    ProjectStore,
    Relation,
    parse_push_pin,
    render_relations,
)

INTENT_MARKER = "workline-mutation-intent"
INTENT_VERSION = 1

# Every top-level field of a recovery record this controller opened
# (:meth:`MutationController.begin`) and then closed (:meth:`Mutation.complete`
# or :meth:`Mutation.abandon`). A record holding any other set of fields is not
# one this run can show it wrote by itself, so it is never removed.
CLOSED_RECORD_FIELDS = frozenset({
    "workline", "version", "mutation_id", "owner", "status", "created_at", "updated_at",
    "invocation", "write_scope", "reserved_ids", "notes", "effects", "completed_at",
})

UNAPPLIED = "unapplied"
MATCHING = "applied_matching"
MISMATCH = "applied_mismatch"

EFFECT_KINDS = ("write_file", "add_relation", "remove_relation", "append_event", "git_commit", "git_push")
#: The effects that write a Project's files rather than Git.
FILE_EFFECT_KINDS = ("write_file", "add_relation", "remove_relation", "append_event")

# A recorded commit names its base by the full object ID and its branch by the full ref name, never by an
# expression Git would resolve.
_COMMIT_ID = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
_BRANCH_REF = re.compile(r"refs/heads/\S+")

#: The key of a recorded effect that holds where the stage deciding it was decided (:func:`_open_decision`).
_DECIDED_ON = "decided_on"

#: The key of a recorded git_commit that holds the ID of the commit this mutation made for it (:func:`_make_commit`).
_MADE_COMMIT = "commit_id"
_NO_MADE_COMMIT = object()

#: Work lifecycle events that open a Work's execution rather than decide what it produced. START records
#: them before its executor runs, and a stage made only of them fixes no branch (``skills/start``).
_OPENING_EVENTS = frozenset({"work_started", "work_resumed", "work_target_added"})

#: The key of a recorded file effect that holds what its path held before it wrote (:meth:`Mutation.add_effects`).
_HELD_BEFORE = "held_before"
#: The key of a recorded file effect that holds what it wrote there (:meth:`Mutation.apply`).
_WROTE = "wrote"
#: The note holding what an owner showed is its own at a path no effect of its writes (:func:`declare_own_content`).
_OWN_CONTENT = "own_content"

#: What :func:`_content_digest` answers with: the bytes at a path, the target of a link, or no path at all.
_BYTES = "sha256:"
_LINK = "link:"
_ABSENT = "absent"
#: What :func:`declare_own_content` records for a path it could not read, so that no later state matches it.
_UNREADABLE = "unreadable"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n")


# --------------------------------------------------------------------------- what a path holds

def effect_path(effect: "dict[str, Any] | Effect") -> str | None:
    """The canonical Project path this effect writes; ``None`` for one that writes no file.

    The one place that mapping lives, so what an operation says it owns
    (:func:`workline.ops._owned_paths`) and what the Mutation Controller proves
    it wrote are the same path.
    """
    kind, payload = (effect["kind"], effect["payload"]) if isinstance(effect, dict) else (effect.kind, effect.payload)
    if kind == "write_file":
        return payload["path"]
    if kind in ("add_relation", "remove_relation"):
        return f"{WORKLINE_DIR}/relations/{payload['file']}.yaml"
    if kind == "append_event":
        return f"{WORKLINE_DIR}/events/events.jsonl"
    return None


def _text_digest(text: str) -> str:
    """What :func:`_content_digest` answers for a path holding exactly ``text``.

    :func:`durable_write_text` writes the text as UTF-8 and translates no line
    ending, so these are the bytes the file comes to hold, and a write and a
    later reading of it are compared as the same bytes.
    """
    return _BYTES + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _content_digest(path: Path) -> str | None:
    """What the Project holds at ``path`` right now, as one comparable value; ``None`` when it cannot be read.

    The bytes as they are on disk - not the text a reader makes of them, which
    turns CRLF into LF and would take a rewritten file for an unchanged one, and
    not anything Git stores, whose own content filters (``core.autocrlf``,
    ``.gitattributes``, smudge / clean) answer about another sequence of bytes
    than the one a write put there. A link is compared by what it points at,
    which is what Git would carry, and is never followed to the bytes at the
    other end.
    """
    try:
        if path.is_symlink():
            return _LINK + hashlib.sha256(os.readlink(path).encode("utf-8", "surrogatepass")).hexdigest()
        if not path.exists():
            return _ABSENT
        return _BYTES + hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return None


@dataclass(frozen=True)
class Effect:
    """A decided physical effect with enough expectation to classify on resume."""

    kind: str
    payload: dict[str, Any]

    @staticmethod
    def write_file(path: str, content: str, base: str | None = None) -> "Effect":
        """Write ``content`` to ``path``.

        ``base`` is the content the file is expected to hold *before* the write
        (``None`` = the file is expected not to exist yet). It is what lets a
        resume tell "my write has not happened yet" from "someone else changed
        this file", the same way ``git_commit`` carries ``base_head``.
        """
        payload: dict[str, Any] = {"path": path, "content": content}
        if base is not None:
            payload["base"] = base
        return Effect("write_file", payload)

    @staticmethod
    def add_relation(file: str, relation: Relation) -> "Effect":
        return Effect("add_relation", {"file": file, "record": relation.to_record()})

    @staticmethod
    def remove_relation(file: str, relation: Relation) -> "Effect":
        return Effect("remove_relation", {"file": file, "record": relation.to_record()})

    @staticmethod
    def append_event(event: Event) -> "Effect":
        return Effect("append_event", {"record": event.to_record()})

    @staticmethod
    def git_commit(message: str, paths: list[str], base_head: str | None, branch: str | None = None) -> "Effect":
        """Commit exactly ``paths`` with ``message``.

        ``base_head`` is the commit HEAD was when the commit was decided (``None``:
        there was none yet), and ``branch`` the full name of the branch HEAD was on
        then, left out when HEAD was on no branch. Together they let a resume tell
        a commit not made yet - on the branch it was decided on
        (:func:`_on_recorded_branch`), which may have only grown past it
        (:func:`_head_advanced_independently`) - from a history that went
        elsewhere. A record without a branch - as every record written before the
        branch was recorded is - does not show one.

        A commit that finalizes a decision the mutation recorded earlier is
        recorded only while HEAD is still where that decision was made, so its
        ``branch`` is the decision's branch (:func:`_bind_decision`).

        Which commit it becomes is known only once it is made: the Mutation
        Controller then records its ID next to the payload (:func:`_make_commit`).
        """
        payload: dict[str, Any] = {"message": message, "paths": list(paths), "base_head": base_head}
        if branch is not None:
            payload["branch"] = branch
        return Effect("git_commit", payload)

    @staticmethod
    def git_push(remote: str, branch: str, locator: str) -> "Effect":
        """A push to one named destination.

        ``locator`` is the exact push destination Git resolved at record time,
        stored verbatim. It is part of the durable payload so a resume verifies
        the destination instead of following the remote name to wherever it
        points by then — and, because it is compared as text, a differently
        spelled locator is a change, not a match.

        What it publishes is not in the payload: it is the commit recorded right
        before it in the same Git stage, by the ID the Mutation Controller
        recorded making it (:func:`_recorded_publication`) - never ``branch`` as
        it is when the push runs.
        """
        return Effect("git_push", {"remote": remote, "branch": branch, "locator": locator})


@dataclass(frozen=True)
class WriteScope:
    entities: tuple[str, ...] = ()
    files: tuple[str, ...] = ()

    def overlaps(self, other: "WriteScope") -> bool:
        return bool(set(self.entities) & set(other.entities)) or bool(set(self.files) & set(other.files))

    def to_record(self) -> dict[str, Any]:
        return {"entities": sorted(set(self.entities)), "files": sorted(set(self.files))}

    @staticmethod
    def from_record(record: dict[str, Any]) -> "WriteScope":
        return WriteScope(tuple(record.get("entities") or ()), tuple(record.get("files") or ()))


def _safe_relative(path: str) -> bool:
    if not isinstance(path, str) or not path or path.startswith("/") or ":" in path.split("/")[0]:
        return False
    parts = path.split("/")
    return all(part not in ("", ".", "..") for part in parts)


class Mutation:
    """One resumable multi-write mutation backed by a durable intent record."""

    def __init__(self, controller: "MutationController", record: dict[str, Any], resumed: bool) -> None:
        self.controller = controller
        self.store = controller.store
        self.record = record
        self.resumed = resumed
        self.path = controller.intent_path(record["mutation_id"])

    # basic accessors ---------------------------------------------------------
    @property
    def id(self) -> str:
        return str(self.record["mutation_id"])

    @property
    def owner(self) -> str:
        return str(self.record["owner"])

    @property
    def invocation(self) -> dict[str, Any]:
        return dict(self.record["invocation"])

    @property
    def scope(self) -> WriteScope:
        return WriteScope.from_record(self.record["write_scope"])

    @property
    def status(self) -> str:
        return str(self.record["status"])

    @property
    def effects(self) -> list[dict[str, Any]]:
        return list(self.record.get("effects") or [])

    # durable intent -------------------------------------------------------
    def _writable(self) -> None:
        """Checked before any in-memory change a later save would persist."""
        self.controller.require_execution_lock(self.owner)

    def _save(self) -> None:
        self._writable()
        self.record["updated_at"] = utc_now()
        try:
            durable_write_text(self.path, yamlish.dump(self.record), tmp_dir=self.store.tmp)
        except DurableWriteError as exc:
            raise StopError(f"recovery intent durable write failed: {exc}", code="recovery_write_failed") from exc

    # reserved IDs -----------------------------------------------------------
    def reserve_id(self, key: str, kind: str) -> str:
        self._writable()
        reserved = self.record.setdefault("reserved_ids", {})
        if key in reserved:
            existing = str(reserved[key])
            if kind_of(existing) != kind:
                raise ReconcileRequired(f"reserved id {key} has kind {kind_of(existing)} not {kind}")
            return existing
        _require_decided_branch(self, f"reserving {key}")
        _require_finalized_branch(self, f"reserving {key}")
        identifier = new_id(kind)
        reserved[key] = identifier
        self._save()
        return identifier

    def reserved(self, key: str) -> str | None:
        value = (self.record.get("reserved_ids") or {}).get(key)
        return str(value) if value else None

    # notes (operation bookkeeping such as pre-existing dirty paths) ----------
    def note(self, key: str) -> Any:
        return (self.record.get("notes") or {}).get(key)

    def set_note(self, key: str, value: Any) -> None:
        self._writable()
        _require_decided_branch(self, f"noting {key}")
        _require_finalized_branch(self, f"noting {key}")
        self.record.setdefault("notes", {})[key] = value
        self._save()

    def extend_scope(self, entities: list[str] = (), files: list[str] = ()) -> None:
        self._writable()
        _require_decided_branch(self, "extending its write scope")
        _require_finalized_branch(self, "extending its write scope")
        scope = self.scope
        merged = WriteScope(tuple(scope.entities) + tuple(entities), tuple(scope.files) + tuple(files))
        self.record["write_scope"] = merged.to_record()
        self._save()

    # stages / effects --------------------------------------------------------
    def has_stage(self, stage: str) -> bool:
        return any(effect.get("stage") == stage for effect in self.effects)

    def stage_effects(self, stage: str) -> list[dict[str, Any]]:
        return [effect for effect in self.effects if effect.get("stage") == stage]

    def add_effects(self, stage: str, effects: list[Effect]) -> None:
        """Validate ``effects`` and append them durably to the intent (before any run).

        A stage that decides Project content carries the branch it is decided on
        in the same durable write, and nothing is recorded off the branch an
        unfinalized decision was made on (:func:`_bind_decision`), nor where an
        applied effect a recorded commit finalizes would have to be written
        again off that commit's branch (:func:`_require_finalized_branch`).

        A stage that writes a Project file carries, in that same write, what
        each of those files holds now, so that the first write of this mutation
        to a path can tell the state it decided against from one another
        subject changed in between (:func:`_require_own_bytes_before_write`).
        A path this mutation has written before is held to what it wrote there
        instead, so a snapshot taken after such a change can never stand in for
        it. A file that cannot be read now carries nothing: a write that then
        happens anyway is classified as it always was.
        """
        self._writable()
        if self.status != "pending":
            raise StopError(f"mutation {self.id} is {self.status}", code="mutation_not_pending")
        if self.has_stage(stage):
            raise StopError(f"stage {stage!r} already recorded in {self.id}", code="stage_duplicate")
        recorded = self.effects
        pending_records: list[dict[str, Any]] = []
        seq = len(recorded)
        for effect in effects:
            seq += 1
            record = {"seq": seq, "stage": stage, "kind": effect.kind, "payload": effect.payload, "applied": False}
            self.controller.validate_effect(record, recorded + pending_records, self.owner)
            path = effect_path(record)
            if path is not None:
                held = _content_digest(self.store.abs(path))
                if held is not None:
                    record[_HELD_BEFORE] = held
            pending_records.append(record)
        _bind_decision(self, stage, pending_records)
        _require_finalized_branch(self, f"recording stage {stage!r}")
        self.record["effects"] = recorded + pending_records
        self._save()

    def apply(self) -> list[tuple[int, str]]:
        """Classify every recorded effect in order and apply the unapplied ones.

        Before anything is classified or applied, a decision no recorded commit
        finalizes yet must still be where it was made (:func:`_require_decided_branch`),
        and an effect already applied that a recorded commit finalizes is not
        written again off that commit's branch (:func:`_require_finalized_branch`).
        A commit made here is recorded with its ID in the same save that records
        it applied (:func:`_make_commit`). A push made here publishes exactly the
        commit its Git stage made, whatever the branch holds by then
        (:func:`_publish`).

        A write happens only while its file still holds what this mutation left
        there, or what it recorded finding there before its first write
        (:func:`_require_own_bytes_before_write`), and the bytes it is about to
        write are recorded durably before it writes them, so that what it wrote
        is known however the write ends. A commit is made only while every path
        it would carry holds exactly what this mutation put there
        (:func:`_require_own_bytes_committed`).
        """
        self._writable()
        if self.status != "pending":
            raise StopError(f"mutation {self.id} is {self.status}", code="mutation_not_pending")
        _require_decided_branch(self, "replaying what it recorded")
        _require_finalized_branch(self, "replaying what it recorded")
        outcomes: list[tuple[int, str]] = []
        effects = self.record.get("effects") or []
        for position, record in enumerate(effects):
            classification = _classify_recorded(self.controller, effects, position)
            if classification == MISMATCH:
                raise ReconcileRequired(
                    f"mutation {self.id} effect {record['seq']} ({record['kind']}) applied with unexpected result: reconcile required"
                )
            identified = False
            if classification == UNAPPLIED:
                if record["kind"] == "git_commit":
                    _require_own_bytes_committed(self, effects, position, record)
                    identified = _make_commit(self, record)
                elif record["kind"] == "git_push":
                    _publish(self, effects, position, record)
                else:
                    _require_own_bytes_before_write(self, effects, position, record)
                    planned = self.controller._planned_write(record)
                    if planned is not None:
                        wrote = _text_digest(planned[1])
                        if record.get(_WROTE) != wrote:
                            record[_WROTE] = wrote
                            self._save()
                    self.controller.apply_effect(record)
            if not record.get("applied") or identified:
                # also what lets a later classification recognize a commit as this mutation's own
                record["applied"] = True
                self._save()
            outcomes.append((int(record["seq"]), classification))
        return outcomes

    def complete(self) -> None:
        self._writable()
        self.record["status"] = "completed"
        self.record["completed_at"] = utc_now()
        self._save()
        self._drop_own_record()

    def _drop_own_record(self) -> None:
        """Take away this mutation's own recovery record, now that nothing can need it.

        A closed record has no reader: a resume looks only at pending records,
        and the Project開始 residue proof accepts only abandoned ones. Keeping
        every one of them for the life of the Project is what makes each
        operation's startup read the whole history back, and what lets a later
        change of record format stop a Project over a record nothing needs.

        Removing it is the cleanup ``rules/git`` allows - an artifact this same
        mutation created, uncommitted, unreferenced and exactly as written - so
        every part of that has to be shown, not assumed
        (:meth:`_own_record_removable`), and whatever cannot be shown keeps the
        record. The record is this operation's own leftover and never its
        result: failing to remove it is not a failure of the operation, and
        nothing is retried because of it.
        """
        try:
            if self._own_record_removable():
                self.path.unlink()
        except (OSError, GitError):
            return

    def _own_record_removable(self) -> bool:
        """Whether this mutation can show that removing its own record loses nothing.

        All of it is required, and an answer that cannot be reached counts as a
        reason to keep the record:

        * this run wrote the record from the beginning and never resumed one it
          found on disk. A record that lay on disk while its operation waited
          can carry someone else's edit - :meth:`MutationController._load_intent`
          accepts unknown fields and :meth:`_save` writes them back - so the
          bytes such a record ends up holding say nothing about who wrote them;
        * its top-level fields are exactly a closed record's;
        * the file is a plain regular file, not a link or other indirection;
        * neither the Git index nor HEAD holds it, so taking it away cannot
          delete anything someone committed. They are separate questions, and a
          git call that cannot answer either one counts as holding it;
        * its bytes are exactly what this mutation last wrote.
        """
        if self.resumed:
            return False
        if set(self.record) != CLOSED_RECORD_FIELDS or type(self.record["version"]) is not int:
            return False
        info = os.lstat(self.path)
        if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            return False
        if not stat.S_ISREG(info.st_mode):
            return False
        relative = f"{MUTATIONS_DIR}/{self.path.name}"
        if gitcmd.tracked_under(self.store.root, relative) != []:
            return False
        if gitcmd.head_paths(self.store.root, relative) != []:
            return False
        return self.path.read_bytes() == yamlish.dump(self.record).encode("utf-8")

    def abandon(self) -> None:
        """Close an intent that never recorded an effect (nothing to resume)."""
        self._writable()
        if self.effects:
            raise StopError(f"mutation {self.id} has recorded effects and cannot be abandoned", code="mutation_has_effects")
        self.record["status"] = "abandoned"
        self.record["completed_at"] = utc_now()
        self._save()


def _classify_recorded(controller: "MutationController", effects: list[dict[str, Any]], position: int) -> str:
    """Classify the effect at ``position`` of a mutation's recorded ``effects``, as replaying that record classifies it.

    ``effects`` are in the order they were recorded - all of the record's, or
    only its file effects. Each is classified against the Project on its own
    (:meth:`MutationController.classify`), which takes an added relation its file
    does not hold for one not added yet. The record itself can show otherwise:
    the add is recorded as applied, and a stage recorded after the add's stage
    removes exactly that relation - the same file, and the same record with its
    ID and every field. A removal is recorded only while the file holds the
    relation exactly as it names it, so the add had been written by then, and
    the relation is missing because the mutation removed it itself - whether or
    not an interruption right after that removal kept its own ``applied`` flag
    from being saved. Such an add is applied, matching, and is not written again.
    Classified on its own it was added again on every replay after its removal
    and removed once more after that, and a replay stopped in between - by an
    interruption, or a push preview that failed - left the relation back in its
    file, where the record's own order no longer explains it.

    Nothing else stands in for that removal. A relation under another ID, of the
    same type and endpoints included, a removal recorded with another snapshot,
    an add the record does not hold as applied, and a removal recorded before the
    add or in the add's own stage leave the add classified as it always was.

    A push is classified by where the commit its own Git stage made stands at
    its destination, and only the record can name that commit
    (:func:`_recorded_publication`).
    """
    record = effects[position]
    if record.get("kind") == "git_push":
        return controller._classify_push(record["payload"], _recorded_publication(controller.store.root, effects, position))
    classification = controller.classify(record)
    if classification != UNAPPLIED or record["kind"] != "add_relation" or record.get("applied") is not True:
        return classification
    stage, payload = record.get("stage"), record["payload"]
    for later in effects[position + 1:]:
        if later.get("kind") == "remove_relation" and later.get("stage") != stage and later.get("payload") == payload:
            return MATCHING
    return classification


def unapplied_effects(mutation: Mutation) -> list[dict[str, Any]]:
    """The recorded file effects :meth:`Mutation.apply` has still to write, in the order it writes them.

    Each is classified the way :meth:`Mutation.apply` classifies it, and the
    list ends where that would stop: at the first effect applied with an
    unexpected result, which it refuses before writing anything after it. Git
    effects write none of the Project's files, and classifying a push contacts
    its destination, so they are passed over. Nothing is written or saved.
    """
    unapplied: list[dict[str, Any]] = []
    effects = mutation.effects
    for position, record in enumerate(effects):
        if record["kind"] not in FILE_EFFECT_KINDS:
            continue
        classification = _classify_recorded(mutation.controller, effects, position)
        if classification == MISMATCH:
            break
        if classification == UNAPPLIED:
            unapplied.append(record)
    return unapplied


def same_request(recorded: object, request: dict[str, Any]) -> bool:
    """Whether a record was opened for this very request, compared as it is written.

    Compared on the canonical encoding rather than as Python objects, because
    Python reads ``True`` and ``1`` as the same value while the record - and any
    payload built from it - keeps them apart. A recorded request that cannot be
    encoded at all is not one this run can claim to match.
    """
    try:
        return json.dumps(recorded, sort_keys=True) == json.dumps(request, sort_keys=True)
    except (TypeError, ValueError):
        return False


def pending_for_slot(store: ProjectStore, owner: str, slot: dict[str, Any]) -> list[dict[str, Any]]:
    """This owner's unfinished mutations whose invocation matches ``slot``.

    ``slot`` is the part of an invocation that says *which* thing is being
    worked on - a name, a key, an entity - without saying what was decided about
    it. Discovery is deliberately by slot alone, so a request that differs in
    content still finds the record it would otherwise have resumed, and can be
    refused instead of quietly taking it over.
    """
    return [
        record
        for record in MutationController(store).list_pending()
        if record["owner"] == owner and all(record["invocation"].get(key) == value for key, value in slot.items())
    ]


def require_same_request(pending: list[dict[str, Any]], request: dict[str, Any], described: str) -> None:
    """STOP unless an unfinished mutation in this slot is this very request.

    An operation that decides what its caller asked for must be resumable only
    by the same request. Resuming one request's record for another would report
    success while the Project keeps what the first one decided - or, where the
    first had not finished deciding, mix the two. Where that cannot be ruled out
    the record is left exactly as it is, for a human to reconcile: nothing is
    abandoned, removed, replaced or rolled back, and no new mutation is started.
    """
    if not pending:
        return
    legacy = [record for record in pending if "request" not in record["invocation"]]
    if legacy:
        raise ReconcileRequired(
            "unfinished " + described + " "
            + ", ".join(sorted(record["mutation_id"] for record in legacy))
            + ": the record is still pending but was written before this operation recorded what it "
            "had decided, so there is no way to show that this request continues that same one; it "
            "is left untouched: reconcile required"
        )
    if len(pending) > 1:
        raise ReconcileRequired(
            f"{len(pending)} unfinished {described} "
            + ", ".join(sorted(record["mutation_id"] for record in pending))
            + ": reconcile required"
        )
    record = pending[0]
    if not same_request(record["invocation"].get("request"), request):
        raise ReconcileRequired(
            "the unfinished " + described + f" {record['mutation_id']} was opened for a different "
            "request than the one now given; an interrupted operation is never continued with "
            "another request, and it is left untouched: reconcile required"
        )


def unsettled_lifecycle(store: ProjectStore, entities: "Iterable[str]") -> list[dict[str, str]]:
    """Lifecycle events an unfinished mutation decided and the Project cannot see yet.

    A lifecycle fact - held, resumed, cancelled, achieved, started, completed,
    plan_excluded - is derived from the event log, so an operation that reads one
    as a precondition reads the log. Between the moment another mutation records
    its event and the moment that event is applied, the log does not hold it: the
    decision is durable but invisible. An operation that only looked at current
    state would act on a fact that has already been decided away.

    The effect is compared against the log by event ID rather than by its own
    ``applied`` flag, so a crash between applying an event and saving that flag
    reports the event as settled - which it is, because the log holds it and the
    reader can see it.

    Owner-agnostic: a Work's lifecycle decision is as invisible when START made
    it as when Roadmap did.
    """
    wanted = {entity for entity in entities if entity}
    if not wanted:
        return []
    logged = {event.id for event in store.read_events()} if store.events_jsonl.is_file() else set()
    decided: list[dict[str, str]] = []
    for record in MutationController(store).list_pending():
        for effect in record["effects"]:
            if effect["kind"] != "append_event":
                continue
            event = effect["payload"]["record"]
            if event["entity"] in wanted and event["id"] not in logged:
                decided.append({
                    "mutation_id": record["mutation_id"],
                    "owner": record["owner"],
                    "entity": event["entity"],
                    "type": event["type"],
                })
    return decided


@contextmanager
def abandon_on_stop(mutation: Mutation):
    """Abandon ``mutation`` when a STOP happens before any effect was recorded."""
    try:
        yield mutation
    except StopError:
        if mutation.status == "pending" and not mutation.effects:
            mutation.abandon()
        raise


# --------------------------------------------------------------------------- the branch a decision is made on

_UNBOUND = object()


def _opens_execution(effect: dict[str, Any]) -> bool:
    payload = effect.get("payload")
    event = payload.get("record") if effect.get("kind") == "append_event" and isinstance(payload, dict) else None
    return isinstance(event, dict) and event.get("type") in _OPENING_EVENTS


def _decides(effects: list[dict[str, Any]]) -> bool:
    """Whether a stage's effects decide Project content that its commit must finalize where they were decided.

    Only an effect that writes the Project's files decides anything; a Git stage
    finalizes what was decided. A stage made only of the lifecycle events that
    open a Work's execution decides nothing either: START records it before its
    executor runs, and what the Work produces - and so the branch that is
    finalized on - is decided only once the executor has returned. An effect
    that cannot be read as such an event counts as deciding.
    """
    return any(not _opens_execution(effect) for effect in effects if effect.get("kind") in FILE_EFFECT_KINDS)


def _open_decision(mutation: Mutation) -> tuple[list[str], dict[str, Any] | None]:
    """The stages whose decision no recorded commit finalizes yet, and the binding they carry.

    A stage that decides Project content (:func:`_decides`) is recorded with a
    binding under :data:`_DECIDED_ON`: the full name of the branch HEAD was on
    when it was decided (``None`` on a detached HEAD) and the commit HEAD was
    at (``None`` while the branch had none). The Git stage recorded after it
    finalizes it; from then on the recorded commit names its branch itself - the
    branch a commit not made yet is made on (:func:`_on_recorded_branch`) and
    the only one what it finalizes is written again on
    (:func:`_require_finalized_branch`) - and the binding has nothing left to say.
    Until then it is the only thing that says where the decision was made.

    ``([], None)`` when nothing decided waits for its commit. Whatever cannot
    be shown STOPs, and nothing stands in for it:

    * a decision recorded without a binding - as every decision recorded before
      decisions carried their branch was - shows no branch, and the branch HEAD
      is on now is not taken for it, even when it is the same;
    * a binding in another form than this module records, or decisions waiting
      for the same commit that carry different bindings, show no single place.
    """
    effects = mutation.effects
    last_commit = max((index for index, effect in enumerate(effects) if effect.get("kind") == "git_commit"), default=-1)
    stages: dict[str, list[dict[str, Any]]] = {}
    for effect in effects[last_commit + 1:]:
        stages.setdefault(str(effect.get("stage")), []).append(effect)
    decided = [stage for stage, stage_effects in stages.items() if _decides(stage_effects)]
    if not decided:
        return [], None
    bindings = [
        effect.get(_DECIDED_ON, _UNBOUND)
        for stage in decided
        for effect in stages[stage]
        if effect.get("kind") in FILE_EFFECT_KINDS
    ]
    named = ", ".join(decided)
    if any(binding is _UNBOUND for binding in bindings):
        raise ReconcileRequired(
            f"mutation {mutation.id} recorded {named}, which decide Project content no recorded commit finalizes "
            "yet, without the branch they were decided on, as a record written before decisions carried their "
            "branch is; nothing in the record shows that branch and the branch HEAD is on now is not taken for it, "
            "so nothing is replayed or recorded: reconcile required"
        )
    if not all(_binding_readable(binding) for binding in bindings) or any(binding != bindings[0] for binding in bindings):
        raise ReconcileRequired(
            f"mutation {mutation.id}: the decisions no recorded commit finalizes yet ({named}) do not carry one "
            "branch binding in the form Workline records, so where they were decided cannot be shown: reconcile required"
        )
    return decided, dict(bindings[0])


def _binding_readable(binding: object) -> bool:
    return (
        isinstance(binding, dict)
        and set(binding) == {"branch", "head"}
        and (binding["branch"] is None or isinstance(binding["branch"], str) and _BRANCH_REF.fullmatch(binding["branch"]) is not None)
        and (binding["head"] is None or isinstance(binding["head"], str) and _COMMIT_ID.fullmatch(binding["head"]) is not None)
    )


def _where_head_is(repo: Path) -> dict[str, Any] | None:
    """The binding a decision made now carries; ``None`` when Git cannot say which branch, if any, HEAD is on."""
    branch = gitcmd.current_branch_ref(repo)
    if branch is None and gitcmd.head_detached(repo) is not True:
        return None
    return {"branch": branch, "head": gitcmd.head_commit(repo)}


def _still_where_decided(repo: Path, binding: dict[str, Any]) -> bool:
    """Whether HEAD is on the branch a decision was made on, over a history that still holds the commit it was made at.

    The branch is compared by its full name, and a detached HEAD matches only a
    decision made on one. A branch that only grew past that commit - an
    independent commit, a fast-forward - still holds it; an amended, reset or
    rebased one does not. Every question is put to Git, and one it cannot
    answer shows nothing.
    """
    here = _where_head_is(repo)
    if here is None or here["branch"] != binding["branch"]:
        return False
    if binding["head"] is None or here["head"] == binding["head"]:
        return True
    return here["head"] is not None and gitcmd.descends_from(repo, here["head"], binding["head"]) is True


def _off_decided_branch(mutation: Mutation, decided: list[str], binding: dict[str, Any], doing: str) -> ReconcileRequired:
    def place(where: dict[str, Any] | None) -> str:
        if where is None:
            return "a branch Git cannot name"
        return (where["branch"] or "a detached HEAD") + (f" at {where['head']}" if where["head"] else "")

    return ReconcileRequired(
        f"mutation {mutation.id} decided {', '.join(decided)} on {place(binding)}, and no recorded commit finalizes "
        f"that yet; HEAD is now on {place(_where_head_is(mutation.store.root))}, which is not that branch or no longer "
        "holds that commit. Finalizing the decision here would commit it where it was not decided, so nothing is "
        f"replayed, recorded, committed or pushed ({doing}); check out the branch it was decided on to continue: "
        "reconcile required"
    )


def _require_decided_branch(mutation: Mutation, doing: str) -> None:
    """STOP unless every decision no recorded commit finalizes yet is still where it was made (:func:`_open_decision`)."""
    decided, binding = _open_decision(mutation)
    if binding is not None and not _still_where_decided(mutation.store.root, binding):
        raise _off_decided_branch(mutation, decided, binding, doing)


def _bind_decision(mutation: Mutation, stage: str, records: list[dict[str, Any]]) -> None:
    """Give the effects of a stage about to be recorded the binding they must carry, or STOP before it is recorded.

    * While a decision waits for its commit, nothing is recorded unless HEAD is
      still where that decision was made, and a commit recorded then must name
      that same branch: this is where the decision's binding passes to the
      commit's ``branch`` (:func:`_on_recorded_branch`,
      :func:`_require_finalized_branch`), which guards it from then on.
    * A stage that decides Project content carries the binding of the decision
      it joins, or - when none waits - the place HEAD is now, written in the
      same durable save as the stage itself. When Git cannot say which branch
      HEAD is on, nothing is recorded.
    * Anything else carries no binding.
    """
    decided, binding = _open_decision(mutation)
    repo = mutation.store.root
    if binding is not None:
        if not _still_where_decided(repo, binding):
            raise _off_decided_branch(mutation, decided, binding, f"recording stage {stage!r}")
        for record in records:
            if record["kind"] == "git_commit" and record["payload"].get("branch") != binding["branch"]:
                raise ReconcileRequired(
                    f"mutation {mutation.id} decided {', '.join(decided)} on {binding['branch'] or 'a detached HEAD'}, "
                    f"but the commit recorded to finalize it in stage {stage!r} names "
                    f"{record['payload'].get('branch') or 'no branch'}; it is not recorded: reconcile required"
                )
    if not _decides(records):
        return
    if binding is None:
        binding = _where_head_is(repo)
        if binding is None:
            raise GitError(
                f"Git cannot say which branch HEAD is on, so the branch stage {stage!r} of mutation {mutation.id} "
                "would be decided on is unknown; nothing is recorded"
            )
    for record in records:
        if record["kind"] in FILE_EFFECT_KINDS:
            record[_DECIDED_ON] = dict(binding)


# --------------------------------------------------------------------------- the branch a finalized effect is written on
def _require_finalized_branch(mutation: Mutation, doing: str) -> None:
    """STOP before an applied effect a recorded commit finalizes is written again anywhere but on that commit's branch.

    Once the commit finalizing a stage is recorded, it names the branch the
    stage was decided on (:func:`_bind_decision`), and a resume classifies every
    recorded effect again against the working tree it meets. A tree whose
    history does not hold that commit - another branch checked out after the
    commit was made, before its push or before the operation finished - does
    not hold what the commit carried, so every effect the mutation applied looks
    unapplied there. Replaying them wrote the decision into a branch that never
    made it and replayed the pushes recorded before it, and only then reached
    the commit: its own classification asks for the branch only of a commit not
    made yet (:func:`_on_recorded_branch`), so it refused merely because those
    writes had left its paths changed - or, with a same-message commit on that
    branch, took the commit as made and reported success. Git then refused to
    check the recorded branch out again over what had been written.

    So an effect the record holds as applied, which :meth:`Mutation.apply` would
    write again now (:func:`unapplied_effects`), is written again only while
    HEAD is on the branch named by the commit recorded right after it - the
    commit that finalizes it, recorded only where its decision was made -
    compared by its full name. On any other branch, on a detached HEAD, or where
    Git cannot name the branch HEAD is on, nothing is replayed, recorded,
    committed or pushed.

    Nothing is asked of a resume that writes nothing applied again: on that
    branch, on another branch whose history holds the commit, and wherever the
    effects are still in place, a question Git cannot answer included, it goes
    on exactly as before. A commit recorded without a branch - as every commit
    recorded before commits carried their branch is - names none, and nothing
    stands in for it: what it finalizes is left to the rules that always
    classified it.
    """
    effects = mutation.effects
    finalized_on: dict[int, object] = {}
    following: object = _UNBOUND
    for position in range(len(effects) - 1, -1, -1):
        effect = effects[position]
        if effect.get("kind") == "git_commit":
            payload = effect.get("payload")
            following = payload["branch"] if isinstance(payload, dict) and "branch" in payload else _UNBOUND
        elif following is not _UNBOUND and effect.get("kind") in FILE_EFFECT_KINDS and effect.get("applied") is True:
            finalized_on[position] = following
    if not finalized_on:
        return
    repo = mutation.store.root
    here = gitcmd.current_branch_ref(repo)
    if all(branch == here for branch in finalized_on.values()):
        return
    positions = {id(effect): position for position, effect in enumerate(effects)}
    for record in unapplied_effects(mutation):
        branch = finalized_on.get(positions.get(id(record), -1), _UNBOUND)
        if branch is not _UNBOUND and branch != here:
            raise _off_finalized_branch(mutation, record, branch, here, doing)


def _off_finalized_branch(
    mutation: Mutation, record: dict[str, Any], branch: object, here: str | None, doing: str
) -> ReconcileRequired:
    if here is not None:
        place = here
    elif gitcmd.head_detached(mutation.store.root) is True:
        place = "a detached HEAD"
    else:
        place = "a branch Git cannot name"
    return ReconcileRequired(
        f"mutation {mutation.id} applied effect {record['seq']} ({record['kind']}, stage {record.get('stage')!r}), "
        f"and the commit recorded to finalize it names {branch}; HEAD is now on {place}, whose working tree does not "
        "hold that effect. Writing it again here would put it on a branch that commit was not made on, so nothing is "
        f"replayed, recorded, committed or pushed ({doing}); check out {branch} to continue: reconcile required"
    )


def _on_recorded_branch(repo: Path, payload: dict[str, Any]) -> bool:
    """Whether HEAD is where a recorded commit that was never made was decided to go.

    HEAD still being the recorded ``base_head`` says only that no commit has been
    made on top of it. Another branch can point at the same commit: a person who
    checks one out, or renames the branch, leaves HEAD where it was, and making
    the commit then puts it on that other branch while the branch it was decided
    on - and every push the record names for it - never receives it.

    So the branch has to be shown as well:

    * a record that names a branch shows it only when HEAD is on exactly that
      branch, compared by its full name;
    * a record without a branch was written on a detached HEAD - or before the
      branch was recorded at all - and names none; nothing stands in for it,
      least of all the branch HEAD happens to be on now. It goes on only while
      HEAD is on no branch either, which is where a commit decided on a detached
      HEAD is made (and where an operation that refuses a detached HEAD at its
      entry never gets to). On a branch it stops;
    * Git answers every question asked; one it cannot answer shows nothing.
    """
    if "branch" not in payload:
        return gitcmd.head_detached(repo) is True
    branch = payload["branch"]
    return isinstance(branch, str) and gitcmd.current_branch_ref(repo) == branch


def _head_advanced_independently(repo: Path, payload: dict[str, Any], head: str) -> bool:
    """Whether a recorded commit that was never made can still be made now that HEAD has moved on.

    A commit is recorded, with the HEAD it was decided on, before it is made.
    Between the two - an interruption, or the commit itself failing - an
    operation independent of this one, or a person, can commit, and HEAD is no
    longer ``base_head``. That alone does not make the recorded commit wrong: if
    the branch only grew by commits that leave this commit's paths alone, it is
    still exactly the commit that was decided, made on top of them as it would
    have been had it been decided after them.

    Only what can be shown counts, and all of it is required:

    * the record names its base by a full commit ID, and that commit is an
      ancestor of HEAD. An amended, reset or rebased history did not grow;
    * no commit since the base changes a recorded path, with every parent of a
      merge followed. That is stricter than the paths still holding what the
      base held: a path someone changed and changed back - or committed with
      this commit's own content and then reverted - was still changed by
      someone else while this commit waited, and making it now would go over
      that. A path committed on its own, or with other content, was changed
      too;
    * HEAD is on the branch the record names. A record that names none - as
      every record written before the branch was recorded does - shows none,
      and nothing stands in for it: a push of the same stage names only where
      it pushes, not where the commit was decided;
    * Git answers every question asked; one it cannot answer shows nothing.

    Short of that, the commit stays applied with an unexpected result.
    """
    base, branch = payload.get("base_head"), payload.get("branch")
    if not isinstance(base, str) or not _COMMIT_ID.fullmatch(base):
        return False
    if not isinstance(branch, str) or gitcmd.current_branch_ref(repo) != branch:
        return False
    return (
        gitcmd.descends_from(repo, head, base) is True
        and gitcmd.commits_touching(repo, base, head, list(payload["paths"])) == []
    )


# --------------------------------------------------------------------------- the bytes a mutation owns

def declare_own_content(mutation: Mutation, paths: "Iterable[str]") -> None:
    """Record what the Project holds at ``paths`` right now as this mutation's own.

    For the paths an operation commits that none of its effects writes: what
    START's executor produced and what it deleted, and a file an owner showed
    already holds exactly what it would have written. The owner has just
    established their content, so what they hold at this moment is what the
    operation is responsible for, and the Git stage commits them only while they
    still hold it (:func:`_require_own_bytes_committed`).

    A path this cannot read is recorded as unreadable rather than left out, so
    the commit refuses it instead of taking it for a path nothing owns. A path
    an effect of this mutation writes is passed over: what that write recorded
    putting there says more than this does, and is what decides for it.

    Nothing is saved when this says exactly what the record already holds: an
    owner that establishes the same content again on a retry leaves the record
    byte for byte as it was, so a run that goes on to stop changes nothing.
    """
    written = {effect_path(effect) for effect in mutation.effects}
    held = mutation.note(_OWN_CONTENT)
    before = dict(held) if isinstance(held, dict) else {}
    declared = dict(before)
    for path in sorted(set(paths) - written):
        digest = _content_digest(mutation.store.abs(path))
        declared[path] = digest if digest is not None else _UNREADABLE
    if declared != before:
        mutation.set_note(_OWN_CONTENT, declared)


def _own_content(mutation: Mutation) -> dict[str, str]:
    declared = mutation.note(_OWN_CONTENT)
    if not isinstance(declared, dict):
        return {}
    return {path: value for path, value in declared.items() if isinstance(path, str) and isinstance(value, str)}


def _last_wrote(effects: list[dict[str, Any]], path: str) -> str | None:
    """What the last effect of ``effects`` that wrote ``path`` recorded writing there."""
    wrote = None
    for effect in effects:
        if effect_path(effect) == path and isinstance(effect.get(_WROTE), str):
            wrote = effect[_WROTE]
    return wrote


def _witnessless(effects: list[dict[str, Any]], path: str) -> bool:
    """Whether some effect of ``effects`` writes ``path`` while recording nothing about its content.

    Such an effect was recorded before a mutation recorded what it writes, so
    what its path holds now cannot be shown either way, and it is treated as it
    was then.
    """
    return any(
        effect_path(effect) == path and _HELD_BEFORE not in effect and _WROTE not in effect
        for effect in effects
    )


def _proves_own_content(effects: list[dict[str, Any]], declared: dict[str, str]) -> bool:
    """Whether this record holds any account at all of the content it owns."""
    return bool(declared) or any(_HELD_BEFORE in effect or _WROTE in effect for effect in effects)


def _require_own_bytes_before_write(
    mutation: Mutation, effects: list[dict[str, Any]], position: int, record: dict[str, Any]
) -> None:
    """STOP unless the file this effect writes still holds what this mutation left there.

    Writing a Project file is not writing the whole file: an appended event
    keeps every line already in the log, and a relation added or removed
    re-renders the ledger out of what it reads there. So a change another
    subject made to that file after this operation began is carried into what
    the write produces - taken over as this mutation's own state where it parses
    (a relation record it then reads back as one of its own), and destroyed
    where it does not (a line the renderer cannot reproduce). Neither is this
    operation's to do (``rules/git`` 基本原則), and the check the commit makes
    cannot catch either, because by then the write has already made the file
    hold exactly what the mutation expected.

    So the file is held to what this mutation last wrote there, and, before its
    first write, to what its stage recorded finding there
    (:meth:`Mutation.add_effects`). What it wrote outranks what it found: a
    snapshot taken after another subject's change must never stand in for the
    mutation's own bytes. A mismatch stops before anything is written, replayed
    or recorded, and leaves that change exactly where it is - nothing is staged,
    committed, pushed, put back or taken away. The person commits or discards
    it, and the operation runs again (``rules/git``: ownership競合はreconcile
    required).

    An effect recorded before a mutation recorded any of this is applied as it
    always was.
    """
    path = effect_path(record)
    if path is None:
        return
    expected = _last_wrote(effects[:position], path) or record.get(_HELD_BEFORE)
    if not isinstance(expected, str):
        return
    if _content_digest(mutation.store.abs(path)) != expected:
        raise ReconcileRequired(
            f"mutation {mutation.id} effect {record['seq']} ({record['kind']}) would write {path}, which no longer "
            "holds what this operation left there; a change it does not own would be taken into its own state or "
            "written over, so nothing is written, committed or pushed and the change is left exactly as it is: "
            "reconcile required"
        )


def _require_own_bytes_committed(
    mutation: Mutation, effects: list[dict[str, Any]], position: int, record: dict[str, Any]
) -> None:
    """STOP unless every path this commit would carry holds exactly what this mutation put there.

    Owning a path is not owning the bytes at it. ``git add`` and
    ``git commit --only`` carry whatever the working tree holds at the paths
    they are given, and the operation knows only that it wrote *somewhere* in
    each of them; a change another subject made to one after the operation began
    is as much "different from HEAD" as its own writes, and is committed, pushed
    and reported as the operation's own result. So each path is compared, right
    before it is staged, against what this mutation recorded putting there: what
    its last write to that path wrote (:meth:`Mutation.apply`), or, for a path
    no effect of its writes, what its owner showed is its own
    (:func:`declare_own_content`).

    Only the paths that would actually carry something are compared: a path
    identical to HEAD adds nothing to the commit, whatever the record says about
    it. A path that would carry something this mutation cannot account for is
    refused exactly as a changed one is - it is a change the operation did not
    make. Nothing is staged, committed or pushed, and the change is left where
    it is.

    Every committed path was clean when the operation began (BL-041,
    :func:`workline.gitops.ensure_separable`), which is what makes the
    comparison sound: a difference from HEAD that is not this mutation's own was
    made after it began. A record from before a mutation recorded any of this,
    and a path whose writer was recorded then, keep the behaviour they had.
    """
    paths = [path for path in record["payload"]["paths"] if isinstance(path, str)]
    changed = gitcmd.changed_against_head(mutation.store.root, paths)
    if not changed:
        return
    earlier = effects[:position]
    declared = _own_content(mutation)
    proves = _proves_own_content(earlier, declared)
    foreign: list[str] = []
    unaccounted: list[str] = []
    for path in sorted(changed):
        expected = _last_wrote(earlier, path) or declared.get(path)
        if expected is None:
            if _witnessless(earlier, path) or not proves:
                continue  # recorded before a mutation recorded what it writes
            unaccounted.append(path)
            continue
        if _content_digest(mutation.store.abs(path)) != expected:
            foreign.append(path)
    if not foreign and not unaccounted:
        return
    detail = []
    if foreign:
        detail.append("no longer holds what this operation wrote there: " + ", ".join(foreign))
    if unaccounted:
        detail.append("differs from HEAD through no write of this operation: " + ", ".join(unaccounted))
    raise ReconcileRequired(
        f"mutation {mutation.id} cannot show the change it would commit is its own - "
        + "; ".join(detail)
        + "; nothing is staged, committed or pushed and the change is left exactly as it is: reconcile required"
    )


# --------------------------------------------------------------------------- the commit a mutation made

def _make_commit(mutation: Mutation, record: dict[str, Any]) -> bool:
    """Make the recorded commit and note on its record the ID of the commit made; whether that note changed.

    The ID is only noted here, in memory: :meth:`Mutation.apply` writes it in
    the same save that records the commit applied, so a record never holds one
    without the other. An interruption after the commit succeeded and before
    that save leaves neither, as it always did.

    The commit made is the one HEAD names right after ``git commit`` succeeded
    (:func:`_commit_just_made`). Nothing is looked up afterwards, and a commit
    Git does not show to be exactly that one is noted as no ID at all.
    """
    repo = mutation.store.root
    before = gitcmd.head_commit(repo)
    mutation.controller.apply_effect(record)
    made = _commit_just_made(repo, before)
    noted = record.get(_MADE_COMMIT, _NO_MADE_COMMIT)
    if made is None:
        record.pop(_MADE_COMMIT, None)
    else:
        record[_MADE_COMMIT] = made
    return record.get(_MADE_COMMIT, _NO_MADE_COMMIT) != noted


def _commit_just_made(repo: Path, before: str | None) -> str | None:
    """The ID of the commit ``git commit`` just made on top of ``before``; ``None`` when Git does not show exactly that.

    It is the commit HEAD names right after the commit succeeded, and it counts
    only as a new commit whose one parent is the commit HEAD was at before -
    or, on a branch without commits yet, a commit with none. A hook that made
    another commit after it, took it away again or moved HEAD elsewhere, and a
    question Git cannot answer, leave the commit without an ID: it is then
    recognized as a commit recorded before IDs were.
    """
    after = gitcmd.head_commit(repo)
    if after is None or after == before or not _COMMIT_ID.fullmatch(after):
        return None
    if gitcmd.commit_parents(repo, after) != ([] if before is None else [before]):
        return None
    return after


def _made_commit_held(repo: Path, made: object, head: str | None) -> bool:
    """Whether HEAD's history still holds the commit a mutation recorded it made.

    ``made`` must be a full commit ID, and Git must show HEAD is that commit or
    descends from it. An amended, reset or rebased history does not hold it, and
    a question Git cannot answer shows nothing.
    """
    return (
        isinstance(made, str)
        and _COMMIT_ID.fullmatch(made) is not None
        and head is not None
        and gitcmd.descends_from(repo, head, made) is True
    )


# --------------------------------------------------------------------------- what a recorded push publishes

@dataclass(frozen=True)
class _Publication:
    """The one commit a recorded push publishes, and the full name of the branch it publishes it to."""

    commit: str
    ref: str

    @property
    def refspec(self) -> str:
        return f"{self.commit}:{self.ref}"


def _recorded_publication(repo: Path, effects: list[dict[str, Any]], position: int) -> "_Publication | str":
    """What the push recorded at ``position`` of ``effects`` publishes; why that cannot be shown, when it cannot.

    A Git stage is recorded as one commit and, with a remote, the push of it
    right after (:func:`workline.gitops.finalize_effects`). The push publishes
    that commit - the one this mutation made, by the ID it recorded making it
    (:func:`_make_commit`) - and the history it was made on, never the branch as
    it is when the push runs: a person, another tool or another operation can
    have committed on top of that commit since, whatever paths they touched, and
    nothing this mutation decided approved publishing it. The approved
    destination says where the push may write, not what it may publish.

    All of the following must be shown, and anything short of it names no commit:

    * the push is the second and last effect of its stage, recorded right after
      that stage's only other effect, a git_commit - next to it in the record and
      by ``seq``;
    * the record holds that commit as applied with the full ID of the commit this
      mutation made. A commit recorded before IDs were, one made just before an
      interruption kept its ID from being saved, one someone else made and one
      Git could not show to be the commit made name none, and nothing stands in
      for the ID - the branch tip least of all;
    * the commit names its branch in full, and the push names that same branch;
    * Git shows the ID is a commit with exactly one parent, a parent descending
      from the recorded base, a change to nothing but the recorded paths - the
      commit ``git commit --only`` makes of them - and that the recorded branch
      still holds it.
    """
    push = effects[position]
    stage = push.get("stage")
    commit = effects[position - 1] if position > 0 else {}
    if (
        [index for index, effect in enumerate(effects) if effect.get("stage") == stage] != [position - 1, position]
        or commit.get("kind") != "git_commit"
        or type(commit.get("seq")) is not int
        or type(push.get("seq")) is not int
        or commit["seq"] + 1 != push["seq"]
    ):
        return "it is not recorded right after the one commit of its Git stage"
    made = commit.get(_MADE_COMMIT)
    if commit.get("applied") is not True or not isinstance(made, str) or _COMMIT_ID.fullmatch(made) is None:
        return "the commit of its Git stage is not recorded with the ID of a commit this mutation made"
    payload, pushed = commit.get("payload"), push.get("payload")
    ref = payload.get("branch") if isinstance(payload, dict) else None
    if (
        not isinstance(ref, str)
        or _BRANCH_REF.fullmatch(ref) is None
        or not isinstance(pushed, dict)
        or pushed.get("branch") != ref.removeprefix("refs/heads/")
    ):
        return "the commit of its Git stage and the push do not name the same branch in full"
    base, paths = payload.get("base_head"), payload.get("paths")
    parents = gitcmd.commit_parents(repo, made)
    if (
        parents is None
        or len(parents) != 1
        or not isinstance(base, str)
        or _COMMIT_ID.fullmatch(base) is None
        or gitcmd.descends_from(repo, parents[0], base) is not True
    ):
        return f"Git does not show {made} as the commit made on top of the recorded base"
    changed = gitcmd.commit_changes(repo, made)
    if changed is None or not isinstance(paths, list) or not set(changed) <= set(paths):
        return f"Git does not show {made} as a commit of the recorded paths alone"
    tip = gitcmd.branch_commit(repo, ref)
    if tip is None or gitcmd.descends_from(repo, tip, made) is not True:
        return f"{ref} does not hold {made}"
    return _Publication(made, ref)


def _published_under(repo: Path, locator: str, publication: _Publication, preview: gitcmd.PushPreview) -> str:
    """Whether a destination branch Git will not fast-forward to the recorded commit already holds it.

    Git refuses (``!``) when the branch at the destination is not an ancestor of
    the commit. That branch has either moved on past it - the push of a later
    stage of this mutation, a person, another clone - and the commit is already
    published, or it holds another history. The push path cannot tell which, so
    the destination is read: where its branch points
    (:func:`workline.gitcmd.destination_branch`) and, when this repository does
    not have that commit yet, the history behind it
    (:func:`workline.gitcmd.fetch_destination_branch` - objects only, no ref,
    no ``FETCH_HEAD``). Only a locator Git reads as itself is read: one
    ``url.<base>.insteadOf`` would turn into another repository's is not.

    Holding the commit is applied, matching: nothing is pushed and the branch is
    left where it is. Not holding it is reconcile required, and nothing is
    forced. What cannot be read or shown is a STOP, never taken for published.
    """
    readable = gitcmd.reads_itself(repo, locator)
    if readable is False:
        raise ReconcileRequired(
            f"the destination would reject this push of {publication.commit} to {publication.ref} ({preview.summary}), "
            f"and whether it already holds that commit could only be read through the URL Git rewrites {locator} to - "
            "another repository - so it is not read and nothing is pushed: reconcile required"
        )
    if readable is None:
        raise GitError(f"cannot tell what a read of {locator} would reach; nothing is pushed")
    tip = gitcmd.destination_branch(repo, locator, publication.ref)
    if tip == publication.commit:
        return MATCHING
    held = None if tip is None else gitcmd.descends_from(repo, tip, publication.commit)
    if tip is not None and held is None:
        gitcmd.fetch_destination_branch(repo, locator, publication.ref)
        held = gitcmd.descends_from(repo, tip, publication.commit)
    if held is True:
        return MATCHING  # the destination's branch has moved on past the commit: it is published, and stays as it is
    if held is False:
        raise ReconcileRequired(
            f"the destination would reject this push ({preview.summary}): its {publication.ref} is at {tip}, a history "
            f"that does not hold {publication.commit}; nothing is pushed or forced: reconcile required"
        )
    raise GitError(
        f"cannot show whether {publication.ref} at {locator} holds {publication.commit} (it changed while it was read, "
        "or could not be read); nothing is pushed"
    )


def _publish(mutation: Mutation, effects: list[dict[str, Any]], position: int, record: dict[str, Any]) -> None:
    """Make the recorded push at ``position`` publish exactly the commit its Git stage made.

    The commit is shown again right before the push (:func:`_recorded_publication`)
    and handed to :meth:`MutationController.apply_effect` for this one call, which
    pushes that commit alone to its branch - whatever the branch holds by then.
    """
    publication = _recorded_publication(mutation.store.root, effects, position)
    if isinstance(publication, str):
        raise ReconcileRequired(
            f"mutation {mutation.id} effect {record['seq']} (git_push) cannot show which commit it publishes: "
            f"{publication}; the branch as it is now is never pushed in its place, so nothing is pushed: reconcile required"
        )
    controller = mutation.controller
    controller._publishing = (record, publication)
    try:
        controller.apply_effect(record)
    finally:
        controller._publishing = None


class MutationController:
    """Physical writer for a Project's canonical files."""

    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        # the recorded push being made and the one commit it publishes (:func:`_publish`), for one apply_effect call
        self._publishing: tuple[dict[str, Any], _Publication] | None = None

    # intent files -----------------------------------------------------------
    def intent_path(self, mutation_id: str) -> Path:
        return self.store.mutations / f"{mutation_id}.yaml"

    def _load_intent(self, path: Path) -> dict[str, Any]:
        try:
            data = yamlish.load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yamlish.YamlishError) as exc:
            raise ReconcileRequired(f"cannot read recovery record {path.name}: {exc}") from exc
        if (
            not isinstance(data, dict)
            or data.get("workline") != INTENT_MARKER
            or data.get("version") != INTENT_VERSION
            or data.get("mutation_id") != path.stem
            or not isinstance(data.get("owner"), str)
            or not isinstance(data.get("invocation"), dict)
            or not isinstance(data.get("write_scope"), dict)
            or data.get("status") not in ("pending", "completed", "abandoned")
        ):
            raise ReconcileRequired(f"cannot confirm Workline ownership of recovery record {path.name}")
        return data

    def list_records(self) -> list[dict[str, Any]]:
        """Every recovery record in the runtime mutation area, whatever its status.

        Each record passes the same ownership and version checks as pending
        discovery. Read-only: nothing is repaired, closed or removed.
        """
        if not self.store.mutations.is_dir():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(self.store.mutations.glob("*.yaml")):
            if not is_valid_id(path.stem, "mutation"):
                raise ReconcileRequired(f"unexpected file in runtime mutation area: {path.name}")
            records.append(self._load_intent(path))
        return records

    def list_pending(self) -> list[dict[str, Any]]:
        return [record for record in self.list_records() if record["status"] == "pending"]

    def load(self, mutation_id: str) -> Mutation:
        path = self.intent_path(mutation_id)
        if not path.is_file():
            raise ReconcileRequired(f"mutation record missing: {mutation_id}")
        return Mutation(self, self._load_intent(path), resumed=True)

    # operation authorization ---------------------------------------------------
    def require_execution_lock(self, owner: str) -> None:
        """STOP unless this mutation runs inside its operation's authorization.

        Initial Project開始 is outside the execution lock, but its mutation is
        opened, resumed and written only inside the authorization a running
        project_start() grants for exactly this root; the owner name alone
        authorizes nothing (``rules/git``: Project context). Every other owner
        works only while its top-level operation holds this Project's execution
        lock, which an operation receives only after passing the Project context
        check: no other context writes these records, and no two processes work
        on them at once.
        """
        if owner in PRE_PROJECT_OWNERS:
            if not pre_project_authorized(self.store.root):
                raise StopError(
                    f"{owner} cannot open or write a mutation outside Project開始 of this folder; only a running "
                    "project_start() authorizes it, for its own target root",
                    code="pre_project_authorization_required",
                )
            return
        lock = oplock.held_lock(self.store)
        if lock is None or not same_directory(lock.context_root, self.store.root):
            raise StopError(
                f"{owner} cannot open or write a mutation without this Project's execution lock; "
                "the top-level Workline operation takes it at its entry",
                code="operation_lock_required",
            )

    # discovery ----------------------------------------------------------------
    def open(self, owner: str, invocation: dict[str, Any], scope: WriteScope) -> Mutation:
        """Resume the unique matching pending mutation or begin a new one.

        * exactly one pending mutation with the same owner and invocation → resume
        * none → begin a new mutation
        * several matches, or any other pending mutation whose write scope is
          not provably independent → ``reconcile required``

        The caller holds the Project execution lock, so the pending records
        read here cannot change before the chosen mutation is resumed or begun.
        """
        self.require_execution_lock(owner)
        pending = self.list_pending()
        invocation = json.loads(json.dumps(invocation, sort_keys=True))
        matches = [p for p in pending if p["owner"] == owner and p["invocation"] == invocation]
        others = [p for p in pending if p not in matches]
        if len(matches) > 1:
            raise ReconcileRequired(f"{len(matches)} pending mutations match {owner} {invocation}: reconcile required")
        planned = scope
        if matches:
            planned = WriteScope(
                tuple(scope.entities) + tuple(WriteScope.from_record(matches[0]["write_scope"]).entities),
                tuple(scope.files) + tuple(WriteScope.from_record(matches[0]["write_scope"]).files),
            )
        for other in others:
            other_scope = WriteScope.from_record(other["write_scope"])
            if other_scope.overlaps(planned) or not other_scope.entities and not other_scope.files:
                raise ReconcileRequired(
                    f"pending mutation {other['mutation_id']} (owner {other['owner']}) overlaps the planned write scope: reconcile required"
                )
        if matches:
            mutation = Mutation(self, matches[0], resumed=True)
        else:
            mutation = self.begin(owner, invocation, scope)
        if owner not in PRE_PROJECT_OWNERS:
            oplock.note_mutation(self.store, mutation.id)
        return mutation

    def begin(self, owner: str, invocation: dict[str, Any], scope: WriteScope) -> Mutation:
        mutation_id = new_id("mutation")
        record: dict[str, Any] = {
            "workline": INTENT_MARKER,
            "version": INTENT_VERSION,
            "mutation_id": mutation_id,
            "owner": owner,
            "status": "pending",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "invocation": json.loads(json.dumps(invocation, sort_keys=True)),
            "write_scope": scope.to_record(),
            "reserved_ids": {},
            "notes": {},
            "effects": [],
        }
        mutation = Mutation(self, record, resumed=False)
        mutation._save()
        return mutation

    # validation ----------------------------------------------------------------
    def _entity_known(self, entity_id: str, previous: list[dict[str, Any]]) -> bool:
        kind = kind_of(entity_id)
        if kind not in ENTITY_DIRS:
            return False
        if self.store.entity_exists(kind, entity_id):
            return True
        expected_path = ProjectStore.entity_rel_path(kind, entity_id)
        return any(e["kind"] == "write_file" and e["payload"]["path"] == expected_path for e in previous)

    def _previous_relation_ids(self, file: str, previous: list[dict[str, Any]]) -> set[str]:
        return {
            e["payload"]["record"]["id"]
            for e in previous
            if e["kind"] == "add_relation" and e["payload"]["file"] == file
        }

    def _guard_push_pin(self, content: str, owner: str) -> None:
        """Only the pin owners may change ``git.push`` in project.yaml.

        The push destination is Project-specific safety configuration, so the
        controller refuses the write mechanically instead of leaving the rule
        to Skill prose: a domain operation cannot make the Project follow a
        remote it happens to find.
        """
        try:
            data = yamlish.load(content)
        except yamlish.YamlishError as exc:
            raise ValidationError(f"project.yaml payload is not readable: {exc}", code="project_yaml_invalid") from exc
        if not isinstance(data, dict):
            raise ValidationError("project.yaml payload is not a mapping", code="project_yaml_invalid")
        proposed = parse_push_pin(data)
        current = self.store.read_push_pin() if self.store.project_yaml.is_file() else None
        if proposed == current or owner in PIN_OWNERS:
            return
        raise ValidationError(
            f"operation owner {owner} may not change the Project's push destination pin; "
            "it is changed only by the pin maintenance operation, with human confirmation",
            code="push_pin_owner",
        )

    def validate_effect(self, record: dict[str, Any], previous: list[dict[str, Any]], owner: str) -> None:
        kind = record["kind"]
        payload = record["payload"]
        if kind not in EFFECT_KINDS:
            raise ValidationError(f"unknown effect kind: {kind}")
        if kind == "write_file":
            path = payload.get("path")
            canonical = (
                _safe_relative(path)
                and path.startswith(WORKLINE_DIR + "/")
                and not path.startswith(RUNTIME_DIR + "/")
            )
            # ``INFRA_WRITE_PATHS`` is a closed allowlist of Project
            # infrastructure files (the bootstrap Skill), not a general escape
            # from the .workline boundary.
            if not canonical and path not in INFRA_WRITE_PATHS:
                raise ValidationError(f"write_file path must be a canonical .workline path: {path!r}")
            if not isinstance(payload.get("content"), str):
                raise ValidationError("write_file content must be text")
            if "base" in payload and not isinstance(payload["base"], str):
                raise ValidationError("write_file base must be text")
            if any(e["kind"] == "write_file" and e["payload"]["path"] == path for e in previous):
                raise ValidationError(f"write_file path written twice in one mutation: {path}")
            if path == PROJECT_YAML_REL:
                self._guard_push_pin(payload["content"], owner)
            return
        if kind in ("add_relation", "remove_relation"):
            file = payload.get("file")
            rec = payload.get("record")
            if file not in ("roadmap", "related") or not isinstance(rec, dict):
                raise ValidationError("relation effect needs file roadmap|related and a record")
            for key in ("id", "type", "from", "to"):
                if not isinstance(rec.get(key), str) or not rec[key]:
                    raise ValidationError(f"relation record missing {key}")
            if not is_valid_id(rec["id"], "relation"):
                raise ValidationError(f"relation id invalid: {rec['id']}")
            allowed = ROADMAP_RELATION_TYPES if file == "roadmap" else RELATED_TYPES
            if rec["type"] not in allowed:
                raise ValidationError(f"relation type {rec['type']} not allowed in {file}.yaml")
            if kind == "remove_relation":
                if rec["type"] == "derived":
                    raise ValidationError("derived relations are historical facts and cannot be removed")
                existing = {r.id: r for r in self.store.read_relation_file(file)}
                if rec["id"] not in existing or existing[rec["id"]].to_record() != rec:
                    raise ValidationError(f"remove_relation snapshot does not match {rec['id']}")
                return
            if not self._entity_known(rec["from"], previous):
                raise ValidationError(f"relation from unresolvable: {rec['from']}")
            if file == "roadmap":
                if not self._entity_known(rec["to"], previous):
                    raise ValidationError(f"relation to unresolvable: {rec['to']}")
                if kind_of(rec["from"]) != kind_of(rec["to"]):
                    raise ValidationError("mixed Phase↔Work relation is not allowed")
                if rec["from"] == rec["to"]:
                    raise ValidationError("self relation is not allowed")
                if kind_of(rec["from"]) not in ("work", "phase"):
                    raise ValidationError("roadmap relations connect Works or Phases only")
            else:
                if kind_of(rec["from"]) != "work":
                    raise ValidationError("related relations start from a Work")
                if rec["type"].startswith("conditional_"):
                    from .validate import validate_condition

                    message = validate_condition(rec.get("condition"))
                    if message:
                        raise ValidationError(message)
            existing_ids = {r.id for r in self.store.read_relation_file(file)} if self.store.relation_file(file).is_file() else set()
            if rec["id"] in existing_ids or rec["id"] in self._previous_relation_ids(file, previous):
                raise ValidationError(f"relation id already registered: {rec['id']}")
            return
        if kind == "append_event":
            rec = payload.get("record")
            if not isinstance(rec, dict) or not all(isinstance(rec.get(k), str) and rec[k] for k in ("id", "type", "entity", "at")):
                raise ValidationError("event record needs id / type / entity / at")
            if not is_valid_id(rec["id"], "event"):
                raise ValidationError(f"event id invalid: {rec['id']}")
            entity = rec["entity"]
            entity_kind = kind_of(entity)
            if not self._entity_known(entity, previous):
                raise ValidationError(f"event entity unresolvable: {entity}")
            allowed, terminal = {
                "work": (WORK_EVENTS, WORK_TERMINAL_EVENTS),
                "phase": (PHASE_EVENTS, PHASE_TERMINAL_EVENTS),
                "roadmap": (ROADMAP_EVENTS, ROADMAP_TERMINAL_EVENTS),
            }[entity_kind]
            if rec["type"] not in allowed:
                raise ValidationError(f"event {rec['type']} not allowed for {entity_kind}")
            history = [e.type for e in self.store.read_events() if e.entity == entity] if self.store.events_jsonl.is_file() else []
            history += [
                e["payload"]["record"]["type"]
                for e in previous
                if e["kind"] == "append_event" and e["payload"]["record"]["entity"] == entity
            ]
            if any(t in terminal for t in history):
                raise ValidationError(f"{entity} already has a terminal event; no further lifecycle events allowed")
            return
        if kind == "git_commit":
            if not isinstance(payload.get("message"), str) or not payload["message"].strip():
                raise ValidationError("git_commit needs a message")
            paths = payload.get("paths")
            if not isinstance(paths, list) or not paths or not all(_safe_relative(p) for p in paths):
                raise ValidationError("git_commit needs relative paths")
            if any(p.startswith(RUNTIME_DIR + "/") for p in paths):
                raise ValidationError("runtime metadata is never committed")
            if "branch" in payload and not (isinstance(payload["branch"], str) and _BRANCH_REF.fullmatch(payload["branch"])):
                raise ValidationError("git_commit branch must be the full name of a branch")
            return
        if kind == "git_push":
            remote, branch, locator = payload.get("remote"), payload.get("branch"), payload.get("locator")
            if not remote or not branch or not locator:
                raise ValidationError("git_push needs remote, branch and the resolved push locator")
            if pushurl.is_secret_bearing(locator):
                raise ValidationError(
                    f"git_push destination carries credentials ({pushurl.redact(locator)})",
                    code="push_destination_secret",
                )
            pin = self.store.read_push_pin()
            if pin is None:
                raise ValidationError(
                    "git_push cannot be recorded: this Project has no approved push destination",
                    code="push_destination_unpinned",
                )
            if remote != pin.remote or locator not in pin.allowed_urls:
                raise ValidationError(
                    f"git_push {remote} -> {locator} is not the Project's approved destination "
                    f"({pin.remote} -> {', '.join(pin.allowed_urls)})",
                    code="push_destination_mismatch",
                )

    # classification ------------------------------------------------------------
    def classify(self, record: dict[str, Any]) -> str:
        kind = record["kind"]
        payload = record["payload"]
        if kind == "write_file":
            path = self.store.abs(payload["path"])
            if not path.exists():
                return UNAPPLIED
            try:
                current = _normalize(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError):
                return MISMATCH
            if current == _normalize(payload["content"]):
                return MATCHING
            base = payload.get("base")
            if base is not None and current == _normalize(base):
                return UNAPPLIED  # the decided update has not been applied yet
            return MISMATCH
        if kind == "add_relation":
            rec = payload["record"]
            existing = {r.id: r for r in self.store.read_relation_file(payload["file"])}
            if rec["id"] not in existing:
                return UNAPPLIED
            return MATCHING if existing[rec["id"]].to_record() == rec else MISMATCH
        if kind == "remove_relation":
            rec = payload["record"]
            existing = {r.id: r for r in self.store.read_relation_file(payload["file"])}
            if rec["id"] not in existing:
                return MATCHING
            return UNAPPLIED if existing[rec["id"]].to_record() == rec else MISMATCH
        if kind == "append_event":
            rec = payload["record"]
            for event in self.store.read_events():
                if event.id == rec["id"]:
                    return MATCHING if event.to_record() == rec else MISMATCH
            return UNAPPLIED
        if kind == "git_commit":
            return self._classify_commit(payload, record.get("applied") is True, record.get(_MADE_COMMIT, _NO_MADE_COMMIT))
        if kind == "git_push":
            # what a push publishes is named only by the record it was recorded in (:func:`_classify_recorded`)
            return self._classify_push(payload, "it is classified without the record of the mutation that recorded it")
        raise ValidationError(f"unknown effect kind: {kind}")

    def _classify_commit(self, payload: dict[str, Any], applied: bool, made: object = _NO_MADE_COMMIT) -> str:
        """Classify a recorded commit, in this order:

        * the record holds the commit as ``applied`` with the ID of the commit
          this mutation made (``made``), and HEAD is on the branch the commit was
          recorded on (:func:`_on_recorded_branch`) - applied, matching while
          HEAD's history holds that commit (:func:`_made_commit_held`), applied
          with an unexpected result otherwise;
        * the record already holds the commit as ``applied``, and a commit since
          ``base_head`` still carries the recorded message - applied, matching;
        * nothing is left to commit at the recorded paths - applied, matching;
        * HEAD is still ``base_head``, on the branch the commit was decided on
          (:func:`_on_recorded_branch`) - unapplied;
        * HEAD has only moved on past commits independent of this one
          (:func:`_head_advanced_independently`) - unapplied, and the commit is
          made on top of them;
        * anything else - applied with an unexpected result.

        A message does not identify a commit: anyone can write the same one, for
        any content and on any branch. Finding it says something only about a
        commit this mutation already knows it made. ``applied`` is saved right
        after the commit succeeded, or after an earlier classification found its
        paths committed, and every later apply classifies the commit again -
        often after a later stage of the same mutation changed those paths once
        more, when the message is all that is left to recognize it by.

        A commit the record does not hold as applied - recorded and never made,
        refused by a hook, or made just before an interruption kept its flag from
        being saved - is never taken for made because some commit carries its
        message. Only its paths holding nothing left to commit show that; short of
        it, the base, branch and history checks decide as for any other commit.

        Nor is the message what shows a commit this mutation made: Git stores it
        after its own cleanup - trailing whitespace, line endings, runs of blank
        lines - and after whatever a ``commit-msg`` or ``prepare-commit-msg`` hook
        wrote, so the commit it made may carry another message than the one
        recorded. Such a commit is recorded with its ID, and on its branch that ID
        alone decides: a history that no longer holds it (amended, reset,
        rebased) is not taken back to the message, which cannot tell the commit
        made from one written in its place. Off that branch the ID says nothing
        about where the rest of the mutation goes on, so the commit is classified
        as a commit without one. A commit recorded without an ID - made just
        before an interruption kept its ID from being saved, or recorded before
        IDs were - is classified as it always was.
        """
        repo = self.store.root
        head = gitcmd.head_commit(repo)
        base = payload.get("base_head")
        if applied and made is not _NO_MADE_COMMIT and _on_recorded_branch(repo, payload):
            return MATCHING if _made_commit_held(repo, made, head) else MISMATCH
        if head is not None and applied:
            rev_range = f"{base}..HEAD" if base else "HEAD"
            log = gitcmd.run_git(repo, "log", "--format=%H%x00%B%x01", rev_range, check=False)
            if log.ok:
                for chunk in log.stdout.split("\x01"):
                    if "\x00" not in chunk:
                        continue
                    _, message = chunk.strip().split("\x00", 1)
                    if message.strip() == payload["message"].strip():
                        return MATCHING
        changed = gitcmd.changed_against_head(repo, list(payload["paths"]))
        if head is not None and not changed:
            return MATCHING  # nothing left to commit for these paths
        if head == base and _on_recorded_branch(repo, payload):
            return UNAPPLIED
        if head is not None and _head_advanced_independently(repo, payload, head):
            return UNAPPLIED
        return MISMATCH

    def _classify_push(self, payload: dict[str, Any], publication: "_Publication | str") -> str:
        """Classify a recorded push by where the commit it publishes stands at its destination.

        Destination first: the destination the effect was recorded against is
        confirmed against the Project pin and the current Git configuration
        *before* anything is contacted, so a mutation never follows a remote name
        to a destination it was not recorded for. Then the commit it publishes -
        ``publication``, the commit its Git stage made (:func:`_recorded_publication`)
        - must have been shown; a push that cannot name it is not classified at
        all, and the branch as it is now never stands in for it.

        The evidence comes from the push itself: ``git push --dry-run`` of the
        exact refspec the real push uses - that commit to that branch - so Git
        applies its own rewriting once and answers about the repository the push
        would write to. ``=``: the branch is that commit, published. ``*`` /
        `` ``: the branch is missing or behind it, unapplied, and only that
        commit is pushed. ``!``: the branch has moved on past it or away from it,
        which the destination itself is asked (:func:`_published_under`). A
        remote-tracking ref is never consulted, since it survives a failed fetch
        and would make a stale answer look confirmed.
        """
        repo = self.store.root
        remote, branch, locator = payload["remote"], payload["branch"], payload["locator"]
        verify_recorded_destination(self.store, remote, locator)
        if isinstance(publication, str):
            raise ReconcileRequired(
                f"the recorded push to {branch} cannot show which commit it publishes: {publication}; the branch as it "
                "is now is never pushed in its place, so nothing is pushed: reconcile required"
            )
        preview = gitcmd.push_dry_run(repo, remote, publication.refspec)
        if preview.flag == "=":
            return MATCHING  # the branch is that commit
        if preview.flag in ("*", " "):
            return UNAPPLIED  # new branch / fast-forward to that commit, and no further
        if preview.flag == "!":
            return _published_under(repo, locator, publication, preview)
        raise StopError(
            f"git push --dry-run reported {preview.flag!r} ({preview.summary}), which Workline does not "
            "act on; STOP rather than guess",
            code="push_preview_unknown",
        )

    # application ---------------------------------------------------------------
    def _planned_write(self, record: dict[str, Any]) -> tuple[Path, str] | None:
        """The file this effect writes and the exact text it puts there; ``None`` for one that writes no file.

        The same computation :meth:`apply_effect` performs, so that what a
        mutation records having written (:meth:`Mutation.apply`) is what the
        write puts on disk, and never a second, separately written rendering of
        it that could come to differ.
        """
        kind = record["kind"]
        payload = record["payload"]
        if kind == "write_file":
            return self.store.abs(payload["path"]), payload["content"]
        if kind == "add_relation":
            relations = self.store.read_relation_file(payload["file"])
            relations.append(Relation.from_record(payload["record"]))
            return self.store.relation_file(payload["file"]), render_relations(relations)
        if kind == "remove_relation":
            relations = [r for r in self.store.read_relation_file(payload["file"]) if r.id != payload["record"]["id"]]
            return self.store.relation_file(payload["file"]), render_relations(relations)
        if kind == "append_event":
            text = _normalize(self.store.events_text())
            if text and not text.endswith("\n"):
                text += "\n"
            text += yamlish.escape_line_separators(json.dumps(payload["record"], ensure_ascii=False, separators=(",", ":"))) + "\n"
            return self.store.events_jsonl, text
        if kind in ("git_commit", "git_push"):
            return None
        raise ValidationError(f"unknown effect kind: {kind}")

    def apply_effect(self, record: dict[str, Any]) -> None:
        kind = record["kind"]
        payload = record["payload"]
        planned = self._planned_write(record)
        if planned is not None:
            path, text = planned
            durable_write_text(path, text, tmp_dir=self.store.tmp)
            return
        if kind == "git_commit":
            repo = self.store.root
            paths = list(payload["paths"])
            gitcmd.add_paths(repo, paths)
            gitcmd.commit_only(repo, payload["message"], paths)
            return
        if kind == "git_push":
            repo = self.store.root
            remote, locator = payload["remote"], payload["locator"]
            # The one commit this push publishes, shown by its record right before this call (:func:`_publish`);
            # without it nothing is pushed - the branch as it is now never stands in for it.
            staged = self._publishing
            if staged is None or staged[0] is not record:
                raise ReconcileRequired(
                    f"a recorded push to {payload['branch']} is made only for the commit its Git stage made, and none "
                    "was shown for this one; nothing is pushed: reconcile required"
                )
            # Re-resolved immediately before the push: the window between the
            # check and the push cannot be closed entirely (Git reads its own
            # configuration when it runs), but it is narrowed to this call.
            current = resolve_active_push_locator(repo, remote)
            if current != locator:
                raise StopError(
                    f"push destination changed just before pushing (expected {locator}, remote {remote} "
                    f"now resolves to {current}): STOP",
                    code="push_destination_changed",
                )
            result = gitcmd.push(repo, remote, staged[1].refspec)
            if not result.ok:
                raise GitError(f"push to {locator} failed: {result.stderr.strip() or result.stdout.strip()}")
            return
        raise ValidationError(f"unknown effect kind: {kind}")
