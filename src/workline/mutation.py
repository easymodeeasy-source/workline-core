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
import json
from pathlib import Path
from typing import Any

from . import gitcmd, oplock, pushurl, yamlish
from .context import pre_project_authorized, same_directory
from .destination import resolve_active_push_locator, verify_recorded_destination
from .durable import DurableWriteError, durable_write_text
from .errors import GitError, ReconcileRequired, StopError, ValidationError
from .ids import is_valid_id, kind_of, new_id
from .store import (
    ENTITY_DIRS,
    INFRA_WRITE_PATHS,
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

UNAPPLIED = "unapplied"
MATCHING = "applied_matching"
MISMATCH = "applied_mismatch"

EFFECT_KINDS = ("write_file", "add_relation", "remove_relation", "append_event", "git_commit", "git_push")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n")


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
    def git_commit(message: str, paths: list[str], base_head: str | None) -> "Effect":
        return Effect("git_commit", {"message": message, "paths": list(paths), "base_head": base_head})

    @staticmethod
    def git_push(remote: str, branch: str, locator: str) -> "Effect":
        """A push to one named destination.

        ``locator`` is the exact push destination Git resolved at record time,
        stored verbatim. It is part of the durable payload so a resume verifies
        the destination instead of following the remote name to wherever it
        points by then — and, because it is compared as text, a differently
        spelled locator is a change, not a match.
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
        self.record.setdefault("notes", {})[key] = value
        self._save()

    def extend_scope(self, entities: list[str] = (), files: list[str] = ()) -> None:
        self._writable()
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
        """Validate ``effects`` and append them durably to the intent (before any run)."""
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
            pending_records.append(record)
        self.record["effects"] = recorded + pending_records
        self._save()

    def apply(self) -> list[tuple[int, str]]:
        """Classify every recorded effect in order and apply the unapplied ones."""
        self._writable()
        if self.status != "pending":
            raise StopError(f"mutation {self.id} is {self.status}", code="mutation_not_pending")
        outcomes: list[tuple[int, str]] = []
        for record in self.record.get("effects") or []:
            classification = self.controller.classify(record)
            if classification == MISMATCH:
                raise ReconcileRequired(
                    f"mutation {self.id} effect {record['seq']} ({record['kind']}) applied with unexpected result: reconcile required"
                )
            if classification == UNAPPLIED:
                self.controller.apply_effect(record)
            if not record.get("applied"):
                record["applied"] = True
                self._save()
            outcomes.append((int(record["seq"]), classification))
        return outcomes

    def complete(self) -> None:
        self._writable()
        self.record["status"] = "completed"
        self.record["completed_at"] = utc_now()
        self._save()

    def abandon(self) -> None:
        """Close an intent that never recorded an effect (nothing to resume)."""
        self._writable()
        if self.effects:
            raise StopError(f"mutation {self.id} has recorded effects and cannot be abandoned", code="mutation_has_effects")
        self.record["status"] = "abandoned"
        self.record["completed_at"] = utc_now()
        self._save()


@contextmanager
def abandon_on_stop(mutation: Mutation):
    """Abandon ``mutation`` when a STOP happens before any effect was recorded."""
    try:
        yield mutation
    except StopError:
        if mutation.status == "pending" and not mutation.effects:
            mutation.abandon()
        raise


class MutationController:
    """Physical writer for a Project's canonical files."""

    def __init__(self, store: ProjectStore) -> None:
        self.store = store

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

    def list_pending(self) -> list[dict[str, Any]]:
        if not self.store.mutations.is_dir():
            return []
        pending: list[dict[str, Any]] = []
        for path in sorted(self.store.mutations.glob("*.yaml")):
            if not is_valid_id(path.stem, "mutation"):
                raise ReconcileRequired(f"unexpected file in runtime mutation area: {path.name}")
            data = self._load_intent(path)
            if data["status"] == "pending":
                pending.append(data)
        return pending

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
            return self._classify_commit(payload)
        if kind == "git_push":
            return self._classify_push(payload)
        raise ValidationError(f"unknown effect kind: {kind}")

    def _classify_commit(self, payload: dict[str, Any]) -> str:
        repo = self.store.root
        head = gitcmd.head_commit(repo)
        base = payload.get("base_head")
        if head is not None:
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
        if head == base:
            return UNAPPLIED
        return MISMATCH

    def _classify_push(self, payload: dict[str, Any]) -> str:
        """Classify a recorded push — destination first, network second.

        The destination the effect was recorded against is confirmed against
        the Project pin and the current Git configuration *before* anything is
        contacted, so a mutation never follows a remote name to a destination
        it was not recorded for.

        The evidence then comes from the push itself: ``git push --dry-run``
        over the same remote name and the same refspec the real push uses, so
        Git applies its own rewriting once and answers about the repository the
        push would write to. A resolved locator is never handed back to another
        Git command — ``url.<base>.insteadOf`` can rewrite the very locator
        ``pushInsteadOf`` produced, which would inspect a different repository
        — and a remote-tracking ref is never consulted, since it survives a
        failed fetch and would make a stale answer look confirmed.
        """
        repo = self.store.root
        remote, branch, locator = payload["remote"], payload["branch"], payload["locator"]
        verify_recorded_destination(self.store, remote, locator)
        if gitcmd.head_commit(repo) is None:
            return MISMATCH
        preview = gitcmd.push_dry_run(repo, remote, branch)
        if preview.flag == "=":
            return MATCHING  # up to date
        if preview.flag in ("*", " "):
            return UNAPPLIED  # new branch / fast-forward update
        if preview.flag == "!":
            raise ReconcileRequired(
                f"the destination would reject this push ({preview.summary}); the branch at "
                f"{preview.destination or locator} is not what this mutation left behind: reconcile required"
            )
        raise StopError(
            f"git push --dry-run reported {preview.flag!r} ({preview.summary}), which Workline does not "
            "act on; STOP rather than guess",
            code="push_preview_unknown",
        )

    # application ---------------------------------------------------------------
    def apply_effect(self, record: dict[str, Any]) -> None:
        kind = record["kind"]
        payload = record["payload"]
        if kind == "write_file":
            durable_write_text(self.store.abs(payload["path"]), payload["content"], tmp_dir=self.store.tmp)
            return
        if kind == "add_relation":
            path = self.store.relation_file(payload["file"])
            relations = self.store.read_relation_file(payload["file"])
            relations.append(Relation.from_record(payload["record"]))
            durable_write_text(path, render_relations(relations), tmp_dir=self.store.tmp)
            return
        if kind == "remove_relation":
            path = self.store.relation_file(payload["file"])
            relations = [r for r in self.store.read_relation_file(payload["file"]) if r.id != payload["record"]["id"]]
            durable_write_text(path, render_relations(relations), tmp_dir=self.store.tmp)
            return
        if kind == "append_event":
            text = _normalize(self.store.events_text())
            if text and not text.endswith("\n"):
                text += "\n"
            text += json.dumps(payload["record"], ensure_ascii=False, separators=(",", ":")) + "\n"
            durable_write_text(self.store.events_jsonl, text, tmp_dir=self.store.tmp)
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
            result = gitcmd.push(repo, remote, payload["branch"])
            if not result.ok:
                raise GitError(f"push to {locator} failed: {result.stderr.strip() or result.stdout.strip()}")
            return
        raise ValidationError(f"unknown effect kind: {kind}")
