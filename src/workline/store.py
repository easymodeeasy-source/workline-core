"""Project layout and canonical file access.

The canonical structure (``skills/project-start``)::

    .workline/
    ├─ project.yaml
    ├─ roadmaps/    <id>.md
    ├─ phases/      <id>.md
    ├─ works/       <id>.md
    ├─ relations/roadmap.yaml, related.yaml
    ├─ events/events.jsonl
    └─ derivations/ <id>.md

``.workline/runtime/`` is the Workline-owned non-domain runtime area.

Entities are resolved only by stable ID: ``<kind>/<id>.md`` must exist and
its frontmatter ``id`` must equal the requested ID. No filename / mtime /
similarity fallback is ever attempted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

from . import pushurl, yamlish
from .errors import ValidationError
from .ids import is_valid_id

WORKLINE_DIR = ".workline"
RUNTIME_DIR = ".workline/runtime"
MUTATIONS_DIR = ".workline/runtime/mutations"
TMP_DIR = ".workline/runtime/tmp"

# The Project-side bootstrap Skill: the single thin entry point Claude Code
# discovers when a Workline Project is opened directly. It is Project
# infrastructure, not a domain 正本 and not a copy of any canonical Skill, so
# it is the one non-``.workline`` path an operation owner may write.
BOOTSTRAP_REL_PATH = ".claude/skills/workline/SKILL.md"
INFRA_WRITE_PATHS = (BOOTSTRAP_REL_PATH,)

PROJECT_YAML_REL = f"{WORKLINE_DIR}/project.yaml"

# Only these operation owners may write the ``git.push`` pin. The Mutation
# Controller enforces it; it is not left to Skill prose.
PIN_OWNERS = ("project-start", "push-destination-pin")

ENTITY_DIRS = {"roadmap": "roadmaps", "phase": "phases", "work": "works"}

ROADMAP_RELATION_TYPES = ("planned_next", "requires_completion", "derived", "return_to")
FUTURE_PLAN_RELATION_TYPES = ("planned_next", "requires_completion", "return_to")
RELATED_TYPES = ("must_read", "conditional_must_read", "obey", "realizes", "must_update", "conditional_must_update")
CONDITIONAL_RELATED_TYPES = ("conditional_must_read", "conditional_must_update")
CONDITION_KINDS = ("path_glob",)

WORK_KINDS = ("phase_integration_check", "human_confirmation")

WORK_EVENTS = (
    "work_started", "work_target_added", "work_target_removed",
    "work_held", "work_resumed", "work_completed", "work_cancelled", "plan_excluded",
)
PHASE_EVENTS = ("phase_held", "phase_resumed", "phase_cancelled", "plan_excluded")
ROADMAP_EVENTS = ("roadmap_held", "roadmap_resumed", "roadmap_cancelled", "roadmap_achieved")
WORK_TERMINAL_EVENTS = ("work_completed", "work_cancelled", "plan_excluded")
PHASE_TERMINAL_EVENTS = ("phase_cancelled", "plan_excluded")
ROADMAP_TERMINAL_EVENTS = ("roadmap_cancelled", "roadmap_achieved")

WORK_DESIRED_HEADING = "このWorkで成立させる状態"
PHASE_DESIRED_HEADING = "成立させたい状態"
ROADMAP_BACKGROUND_HEADING = "背景"
ROADMAP_DESIRED_HEADING = "達成したい状態"
ROADMAP_SCOPE_HEADING = "対象範囲"
ROADMAP_OUT_OF_SCOPE_HEADING = "対象外"

RULE_REFS = {
    "git": "workline://rules/git",
    "ai-decision": "workline://rules/ai-decision",
    "human-confirmation": "workline://rules/human-confirmation",
    "information-tracing": "workline://rules/information-tracing",
}

_HEADING_RE = re.compile(r"^## (.+?)\s*$", re.MULTILINE)


def to_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


# --------------------------------------------------------------------------- records

@dataclass(frozen=True)
class Entity:
    id: str
    type: str
    meta: dict[str, Any]
    body: str
    path: str

    @property
    def display(self) -> str:
        return str(self.meta.get("display", ""))

    @property
    def name(self) -> str:
        for line in self.body.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return ""

    def section(self, heading: str) -> str | None:
        return body_section(self.body, heading)

    @property
    def phase_id(self) -> str | None:
        value = self.meta.get("phase_id")
        return str(value) if value else None

    @property
    def roadmap_id(self) -> str | None:
        value = self.meta.get("roadmap_id")
        return str(value) if value else None

    @property
    def work_kind(self) -> str | None:
        value = self.meta.get("work_kind")
        return str(value) if value else None


@dataclass(frozen=True)
class Relation:
    id: str
    type: str
    from_id: str
    to: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {"id": self.id, "type": self.type, "from": self.from_id, "to": self.to}
        record.update(self.extra)
        return record

    @staticmethod
    def from_record(record: dict[str, Any]) -> "Relation":
        extra = {k: v for k, v in record.items() if k not in ("id", "type", "from", "to")}
        return Relation(str(record["id"]), str(record["type"]), str(record["from"]), str(record["to"]), extra)


@dataclass(frozen=True)
class PushPin:
    """The Project's approved push destination — a safety pin, not a cache.

    ``allowed_urls`` holds the destinations a human explicitly approved (an
    https and an ssh form of the same repository, say). It is never derived
    from the current Git configuration and never auto-refreshed: exactly one
    of these URLs must be what Git actually resolves as the active push
    destination, or the operation STOPs.
    """

    remote: str
    allowed_urls: tuple[str, ...]

    def to_record(self) -> dict[str, Any]:
        return {"remote": self.remote, "allowed_urls": list(self.allowed_urls)}


def parse_push_pin(data: dict[str, Any]) -> PushPin | None:
    """Read the ``git.push`` pin out of project.yaml data; None when unpinned."""
    git_block = data.get("git")
    if git_block is None:
        return None
    if not isinstance(git_block, dict):
        raise ValidationError("project.yaml git must be a mapping", code="project_yaml_invalid")
    push = git_block.get("push")
    if push is None:
        return None
    if not isinstance(push, dict):
        raise ValidationError("project.yaml git.push must be a mapping", code="project_yaml_invalid")
    remote = push.get("remote")
    if not isinstance(remote, str) or not remote.strip():
        raise ValidationError("project.yaml git.push.remote missing", code="project_yaml_invalid")
    urls = push.get("allowed_urls")
    if not isinstance(urls, list) or not urls:
        raise ValidationError("project.yaml git.push.allowed_urls must be a non-empty list", code="project_yaml_invalid")
    accepted: list[str] = []
    for url in urls:
        if not isinstance(url, str) or not url.strip():
            raise ValidationError("project.yaml git.push.allowed_urls holds an empty entry", code="project_yaml_invalid")
        if pushurl.is_secret_bearing(url):
            raise ValidationError(
                f"project.yaml git.push.allowed_urls holds a credential-bearing URL ({pushurl.redact(url)})",
                code="project_yaml_invalid",
            )
        canonical = pushurl.normalize(url)
        if canonical != url:
            raise ValidationError(
                f"project.yaml git.push.allowed_urls is not in canonical form: {url} (expected {canonical})",
                code="project_yaml_invalid",
            )
        accepted.append(url)
    if len(set(accepted)) != len(accepted):
        raise ValidationError("project.yaml git.push.allowed_urls holds duplicates", code="project_yaml_invalid")
    return PushPin(remote.strip(), tuple(accepted))


@dataclass(frozen=True)
class Event:
    id: str
    type: str
    entity: str
    at: str

    def to_record(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "entity": self.entity, "at": self.at}

    @staticmethod
    def from_record(record: dict[str, Any]) -> "Event":
        return Event(str(record["id"]), str(record["type"]), str(record["entity"]), str(record["at"]))


# --------------------------------------------------------------------------- rendering

def body_section(body: str, heading: str) -> str | None:
    matches = list(_HEADING_RE.finditer(body))
    for index, match in enumerate(matches):
        if match.group(1).strip() == heading:
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            return body[start:end].strip()
    return None


def render_body(name: str, sections: list[tuple[str, str]]) -> str:
    parts = [f"# {name}", ""]
    for heading, text in sections:
        parts.append(f"## {heading}")
        parts.append(text.strip())
        parts.append("")
    return "\n".join(parts).rstrip("\n") + "\n"


def render_entity(meta: dict[str, Any], body: str) -> str:
    return yamlish.dump_frontmatter(meta, body)


def render_relations(relations: list[Relation]) -> str:
    return yamlish.dump({"relations": [relation.to_record() for relation in relations]})


def render_event_line(event: Event) -> str:
    return json.dumps(event.to_record(), ensure_ascii=False, separators=(",", ":"))


def project_yaml_text(data: dict[str, Any], pin: PushPin | None) -> str:
    """Render project.yaml data with ``pin`` as its ``git.push`` block.

    Every key the file already holds is preserved; only ``git.push`` is
    replaced, so pinning a destination never rewrites the rest of the file.
    """
    ordered: dict[str, Any] = {}
    if "workline" in data:
        ordered["workline"] = data["workline"]
    git_block = {k: v for k, v in (data.get("git") or {}).items() if k != "push"}
    if pin is not None:
        git_block["push"] = pin.to_record()
    if git_block:
        ordered["git"] = git_block
    for key, value in data.items():
        if key not in ("workline", "git"):
            ordered[key] = value
    return yamlish.dump(ordered)


def render_project_yaml(workline_root: Path, pin: PushPin | None = None) -> str:
    return project_yaml_text(
        {
            "workline": {"root": str(workline_root)},
            "rules": {key: {"ref": ref} for key, ref in RULE_REFS.items()},
        },
        pin,
    )


# --------------------------------------------------------------------------- store

class ProjectStore:
    """Read access to a Project's canonical files and runtime area."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.workline = self.root / WORKLINE_DIR
        self.project_yaml = self.workline / "project.yaml"
        self.relations_dir = self.workline / "relations"
        self.roadmap_yaml = self.relations_dir / "roadmap.yaml"
        self.related_yaml = self.relations_dir / "related.yaml"
        self.events_jsonl = self.workline / "events" / "events.jsonl"
        self.derivations = self.workline / "derivations"
        self.runtime = self.root / RUNTIME_DIR
        self.mutations = self.root / MUTATIONS_DIR
        self.tmp = self.root / TMP_DIR

    # paths ---------------------------------------------------------------
    def entity_dir(self, kind: str) -> Path:
        return self.workline / ENTITY_DIRS[kind]

    def entity_path(self, kind: str, entity_id: str) -> Path:
        return self.entity_dir(kind) / f"{entity_id}.md"

    def rel(self, path: Path) -> str:
        return to_posix(path, self.root)

    def abs(self, relative: str) -> Path:
        return self.root / relative

    @staticmethod
    def entity_rel_path(kind: str, entity_id: str) -> str:
        return f"{WORKLINE_DIR}/{ENTITY_DIRS[kind]}/{entity_id}.md"

    @property
    def canonical_relative_paths(self) -> tuple[str, ...]:
        return (
            f"{WORKLINE_DIR}/project.yaml",
            f"{WORKLINE_DIR}/relations/roadmap.yaml",
            f"{WORKLINE_DIR}/relations/related.yaml",
            f"{WORKLINE_DIR}/events/events.jsonl",
        )

    # project.yaml ---------------------------------------------------------
    def load_project_yaml(self) -> dict[str, Any]:
        try:
            data = yamlish.load(self.project_yaml.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yamlish.YamlishError) as exc:
            raise ValidationError(f"project.yaml unreadable: {exc}", code="project_yaml_invalid") from exc
        if not isinstance(data, dict):
            raise ValidationError("project.yaml is not a mapping", code="project_yaml_invalid")
        return data

    def read_push_pin(self) -> PushPin | None:
        """The Project's approved push destination, or None when unpinned."""
        return parse_push_pin(self.load_project_yaml())

    def project_yaml_with_pin(self, pin: PushPin | None) -> str:
        """Current project.yaml re-rendered with ``pin`` as its ``git.push``."""
        return project_yaml_text(self.load_project_yaml(), pin)

    def workline_root(self) -> Path:
        data = self.load_project_yaml()
        workline = data.get("workline")
        if not isinstance(workline, dict) or not isinstance(workline.get("root"), str):
            raise ValidationError("project.yaml lacks workline.root", code="project_yaml_invalid")
        return Path(workline["root"])

    def exists(self) -> bool:
        return self.workline.is_dir()

    # entities ---------------------------------------------------------------
    def _parse_entity(self, kind: str, path: Path, expected_id: str | None) -> Entity:
        try:
            meta, body = yamlish.load_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yamlish.YamlishError) as exc:
            raise ValidationError(f"{kind} file unreadable: {path.name}: {exc}", code="entity_invalid") from exc
        entity_id = meta.get("id")
        if not isinstance(entity_id, str) or not is_valid_id(entity_id, kind):
            raise ValidationError(f"{kind} file has invalid id: {path.name}", code="entity_invalid")
        if expected_id is not None and entity_id != expected_id:
            raise ValidationError(f"{kind} id mismatch: file {path.name} declares {entity_id}", code="entity_invalid")
        if path.stem != entity_id:
            raise ValidationError(f"{kind} file name does not match id: {path.name}", code="entity_invalid")
        if meta.get("type") != kind:
            raise ValidationError(f"{kind} file has type {meta.get('type')!r}: {path.name}", code="entity_invalid")
        return Entity(entity_id, kind, meta, body, self.rel(path))

    def read_entity(self, kind: str, entity_id: str) -> Entity:
        if not is_valid_id(entity_id, kind):
            raise ValidationError(f"invalid {kind} id: {entity_id!r}", code="entity_unresolvable")
        path = self.entity_path(kind, entity_id)
        if not path.is_file():
            raise ValidationError(f"{kind} not found: {entity_id}", code="entity_unresolvable")
        return self._parse_entity(kind, path, entity_id)

    def entity_exists(self, kind: str, entity_id: str) -> bool:
        return is_valid_id(entity_id, kind) and self.entity_path(kind, entity_id).is_file()

    def list_entities(self, kind: str) -> list[Entity]:
        directory = self.entity_dir(kind)
        if not directory.is_dir():
            return []
        entities = [self._parse_entity(kind, path, None) for path in sorted(directory.glob("*.md"))]
        return sorted(entities, key=lambda entity: entity.id)

    def count_entities(self, kind: str) -> int:
        directory = self.entity_dir(kind)
        if not directory.is_dir():
            return 0
        return sum(1 for _ in directory.glob("*.md"))

    def resolve_any(self, entity_id: str) -> Entity:
        for kind in ENTITY_DIRS:
            if is_valid_id(entity_id, kind):
                return self.read_entity(kind, entity_id)
        raise ValidationError(f"invalid entity id: {entity_id!r}", code="entity_unresolvable")

    # relations ---------------------------------------------------------------
    def _read_relation_file(self, path: Path) -> list[Relation]:
        if not path.is_file():
            raise ValidationError(f"missing relation file: {self.rel(path)}", code="relations_invalid")
        try:
            data = yamlish.load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yamlish.YamlishError) as exc:
            raise ValidationError(f"relation file unreadable: {self.rel(path)}: {exc}", code="relations_invalid") from exc
        if not isinstance(data, dict) or not isinstance(data.get("relations"), list):
            raise ValidationError(f"relation file malformed: {self.rel(path)}", code="relations_invalid")
        relations: list[Relation] = []
        for record in data["relations"]:
            if not isinstance(record, dict) or not all(isinstance(record.get(k), str) for k in ("id", "type", "from", "to")):
                raise ValidationError(f"relation record malformed in {self.rel(path)}", code="relations_invalid")
            relations.append(Relation.from_record(record))
        return relations

    def read_roadmap_relations(self) -> list[Relation]:
        return self._read_relation_file(self.roadmap_yaml)

    def read_related(self) -> list[Relation]:
        return self._read_relation_file(self.related_yaml)

    def relation_file(self, which: str) -> Path:
        if which == "roadmap":
            return self.roadmap_yaml
        if which == "related":
            return self.related_yaml
        raise ValidationError(f"unknown relation file: {which}", code="relations_invalid")

    def read_relation_file(self, which: str) -> list[Relation]:
        return self._read_relation_file(self.relation_file(which))

    # events ---------------------------------------------------------------
    def read_events(self) -> list[Event]:
        if not self.events_jsonl.is_file():
            raise ValidationError("missing events/events.jsonl", code="events_invalid")
        events: list[Event] = []
        try:
            text = self.events_jsonl.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValidationError(f"events unreadable: {exc}", code="events_invalid") from exc
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"events line {number} malformed", code="events_invalid") from exc
            if not isinstance(record, dict) or not all(isinstance(record.get(k), str) for k in ("id", "type", "entity", "at")):
                raise ValidationError(f"events line {number} malformed", code="events_invalid")
            events.append(Event.from_record(record))
        return events

    def events_text(self) -> str:
        if not self.events_jsonl.is_file():
            return ""
        return self.events_jsonl.read_text(encoding="utf-8")
