"""Caller input the canonical writer and reader cannot carry is refused before anything is begun (RB10 N3).

A legacy registration or planning operation records what its caller decided in
the invocation of its mutation, renders the caller's text into the Project's
canonical files, and reads both back later - to resume, to validate, to show a
Project. Two questions are asked of fresh caller input, before the execution
lock is taken where the input reaches it, and in any case before the mutation is
opened, an ID is reserved or an effect is recorded:

* **durable** (N3(b)): every caller value the invocation records is written by
  the recovery record's own serializer and read back as the same value - the
  JSON normalization :meth:`MutationController.open` applies, ``yamlish`` dump
  and load, UTF-8 (:func:`require_durable`). A value Python can hold but the
  record cannot - text holding a lone surrogate, a float, a tuple, a mapping key
  that is not text, an empty mapping key, a sequence inside a sequence - used to
  escape as a raw ``UnicodeEncodeError`` / ``YamlishError`` / ``TypeError``:
  after the lock was taken (leaving it held for the rest of the process), after
  an ID was reserved, or with a pending mutation its own record could not
  resume.
* **semantic** (N3(a), Human decision HD-1): text the writer embeds as Markdown
  structure reads back as exactly what was given - the name as the entity's one
  H1 identity, each section as its own value, with no section added, split or
  reinterpreted (:func:`require_entity_text`). The proof is the live writer and
  reader themselves (``store.render_body`` / ``render_entity`` /
  ``as_read_back`` / ``entity_fields`` / ``Entity.name`` / ``body_section``);
  nothing is escaped, and no writer or reader changes.

What the reader folds is not a different value: a multiline section is read with
universal newlines, so a CRLF or a lone CR in it reads as LF (BL-056), and the
writer and the reader both strip a section. A name is different: it is one
identity, and the reader keeps one line of it and strips that, so a name holding
a line break, a line separator ``str.splitlines`` honours, or surrounding
whitespace reads back as another name, and is refused. A blank name or required
section is left to the owner's own rule (``name is required`` and the like),
which keeps its report.

The semantic question is asked of a request that begins a new mutation. A
request that continues its own unfinished mutation - the same request, recorded
before - is carried on under the record it already holds, whatever rules that
record was written under: refusing it then would leave what it applied
unfinished (``roadmap._require_new_request_input``, ``create``). A replan is
judged where it is decided, before its IDs are reserved (``ops.plan_replan``).

Every refusal is a :class:`ValidationError` with code ``input_unrepresentable``.
Review-v1 planning keeps its own canonical-input preflight and reader-loss
refusal (``roadmap_review``) with its own vocabulary; nothing here runs on it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any

from . import yamlish
from .errors import ValidationError
from .store import (
    _HEADING_RE,
    PHASE_DESIRED_HEADING,
    WORK_DESIRED_HEADING,
    Entity,
    as_read_back,
    body_section,
    entity_fields,
    render_body,
    render_entity,
)

__all__ = [
    "CODE",
    "refused",
    "require_durable",
    "require_entity_text",
    "require_hashable",
    "require_mapping",
    "require_optional_text",
    "require_pairs",
    "require_phase_addition",
    "require_phase_entry_design",
    "require_phase_entry_text",
    "require_phase_specs",
    "require_reference",
    "require_related",
    "require_related_maintenance",
    "require_relations",
    "require_replan",
    "require_roadmap_plan",
    "require_sequence",
    "require_spec_text",
    "require_text",
    "require_work_spec",
    "require_work_specs",
    "require_work_text",
    "require_works_text",
]

#: The code of every refusal made here.
CODE = "input_unrepresentable"

# An ID of each entity kind that no real entity has, for rendering an entity only to read it back.
_PROBE_IDS = {"roadmap": "r_" + "0" * 26, "phase": "p_" + "0" * 26, "work": "w_" + "0" * 26}


def refused(described: str, detail: str) -> ValidationError:
    return ValidationError(
        f"{described} cannot be stored and read back as the same value ({detail}); nothing was begun",
        code=CODE,
    )


# --------------------------------------------------------------------------- shapes

def require_text(value: object, described: str) -> None:
    """``value`` is text UTF-8 can write: a ``str`` holding no lone surrogate."""
    if not isinstance(value, str):
        raise refused(described, f"it is a {type(value).__name__}, not text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise refused(described, f"UTF-8 cannot write the character at position {exc.start}") from exc


def require_optional_text(value: object, described: str) -> None:
    if value is not None:
        require_text(value, described)


def require_mapping(value: object, described: str) -> None:
    if not isinstance(value, Mapping):
        raise refused(described, f"it is a {type(value).__name__}, not a mapping")


def require_sequence(value: object, described: str) -> None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        raise refused(described, f"it is a {type(value).__name__}, not a sequence")


def require_reference(value: object, keys: object, described: str) -> None:
    """A relation endpoint: a key the request itself declares, or text (an ID the registration resolves)."""
    if isinstance(value, str):
        require_text(value, described)
        return
    try:
        declared = isinstance(keys, Mapping) and value in keys
    except TypeError:  # an unhashable value names no key
        declared = False
    if not declared:
        raise refused(described, f"it is a {type(value).__name__} that names no key of this request")


def require_hashable(value: object, described: str) -> None:
    """A value a request looks up by (an ID to remove, an entry key): one that can be looked up at all."""
    try:
        hash(value)
    except TypeError as exc:
        raise refused(described, f"it is a {type(value).__name__}, which names nothing") from exc


def require_related(related: object, described: str) -> None:
    """Related edges as a registration reads them: a sequence of ``type`` / ``to`` / ``condition``, ``to`` text."""
    require_sequence(related, described)
    for index, spec in enumerate(related):
        where = f"{described}[{index}]"
        if not all(hasattr(spec, field) for field in ("type", "to", "condition")):
            raise refused(where, f"it is a {type(spec).__name__}, not a Related edge")
        require_text(spec.to, f"{where} target")
        if spec.condition is not None:
            require_durable(spec.condition, f"{where} condition")


def require_spec_text(spec: object, described: str) -> None:
    """A Phase or Work spec's name and desired state are text UTF-8 can write."""
    require_text(getattr(spec, "name", None), f"{described} name")
    require_text(getattr(spec, "desired_state", None), f"{described} desired state")


def require_phase_specs(phases: object, described: str = "phase") -> None:
    """Phase specs, keyed as the request declares them, whose text the registration can read and write."""
    require_mapping(phases, f"the {described}s")
    for key, spec in phases.items():
        require_spec_text(spec, f"{described} {key!r}")


def require_work_spec(spec: object, described: str) -> None:
    """One Work spec (or design) whose text the registration can read and write: name, desired state, Related, detail."""
    require_spec_text(spec, described)
    require_related(getattr(spec, "related", ()), f"{described} related")
    require_optional_text(getattr(spec, "derivation_detail", None), f"{described} derivation detail")


def require_work_specs(specs: object, described: str = "work") -> None:
    """Work specs (or designs), keyed as the request declares them, whose text the registration can read and write."""
    require_mapping(specs, f"the {described}s")
    for key, spec in specs.items():
        require_work_spec(spec, f"{described} {key!r}")


def require_relations(relations: object, keys: object, described: str) -> None:
    """Relation specs (``type`` / ``from_ref`` / ``to_ref``) whose endpoints are keys of the request or text."""
    require_sequence(relations, described)
    for index, relation in enumerate(relations):
        where = f"{described}[{index}]"
        if not all(hasattr(relation, field) for field in ("type", "from_ref", "to_ref")):
            raise refused(where, f"it is a {type(relation).__name__}, not a relation")
        require_reference(relation.from_ref, keys, f"{where} from")
        require_reference(relation.to_ref, keys, f"{where} to")


def require_pairs(pairs: object, keys: object, described: str) -> None:
    """``(from, to)`` pairs whose endpoints are keys of the request or text."""
    require_sequence(pairs, described)
    for index, pair in enumerate(pairs):
        where = f"{described}[{index}]"
        if isinstance(pair, (str, bytes, Mapping)) or not isinstance(pair, Sequence) or len(pair) != 2:
            raise refused(where, f"it is not one (from, to) pair: {pair!r}")
        require_reference(pair[0], keys, f"{where} from")
        require_reference(pair[1], keys, f"{where} to")


# --------------------------------------------------------------------------- the shapes of each legacy request

def require_roadmap_plan(plan: object) -> None:
    """A RoadmapPlan whose every value a Roadmap creation can read, record and write."""
    require_text(getattr(plan, "name", None), "the Roadmap name")
    require_text(getattr(plan, "background", None), "the Roadmap background")
    require_text(getattr(plan, "desired_state", None), "the Roadmap desired state")
    require_optional_text(getattr(plan, "scope", None), "the Roadmap scope")
    require_optional_text(getattr(plan, "out_of_scope", None), "the Roadmap out-of-scope")
    phases = getattr(plan, "phases", None)
    require_phase_specs(phases)
    require_relations(getattr(plan, "relations", None), phases, "Phase relation")


def require_phase_addition(phases: object, relations: object) -> None:
    """Phases and Phase relations a Phase addition can read, record and write."""
    require_phase_specs(phases)
    require_relations(relations, phases, "Phase relation")


def require_phase_entry_design(design: object) -> None:
    """A PhaseEntryDesign whose every value a Phase entry can read, record and write."""
    works = getattr(design, "works", None)
    require_work_specs(works)
    require_work_spec(getattr(design, "integration", None), "the integration Work")
    confirmation = getattr(design, "human_confirmation", None)
    if confirmation is not None:
        require_work_spec(confirmation, "the confirmation Work")
    require_pairs(getattr(design, "planned_next", None), works, "planned_next")
    require_pairs(getattr(design, "requires_completion", None), works, "requires_completion")
    require_hashable(getattr(design, "entry", None), "the entry Work")


def require_phase_entry_text(design: object) -> None:
    """N3(a) for every Work a Phase entry design registers: its normal Works, integration and confirmation."""
    require_works_text(getattr(design, "works", None))
    require_work_text("work", getattr(design, "integration", None), "the integration Work")
    confirmation = getattr(design, "human_confirmation", None)
    if confirmation is not None:
        require_work_text("work", confirmation, "the confirmation Work")


def require_replan(replan: object) -> None:
    """A Replan whose every value a plan exclusion can read, record and write."""
    removals = getattr(replan, "remove_relation_ids", None)
    require_sequence(removals, "the relations to remove")
    for index, relation_id in enumerate(removals):
        require_hashable(relation_id, f"the relation to remove [{index}]")
    new_works = getattr(replan, "new_works", None)
    require_work_specs(new_works, "replan work")
    require_relations(getattr(replan, "add_relations", None), new_works, "replan relation")


def require_related_maintenance(add: object, remove_relation_ids: object) -> None:
    """Related edges to add and relation IDs to remove that a Related maintenance can read, record and write."""
    require_related(add, "the Related to add")
    require_sequence(remove_relation_ids, "the relations to remove")
    for index, relation_id in enumerate(remove_relation_ids):
        require_hashable(relation_id, f"the relation to remove [{index}]")


# --------------------------------------------------------------------------- durable

def _same(a: object, b: object) -> bool:
    """Equal and of the same type throughout: ``True`` is not ``1``, a tuple is not a list."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same(a[key], b[key]) for key in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _first_unkept(value: Any, where: str) -> str | None:
    """Where in ``value`` the record would refuse or change something, for the refusal's detail."""
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                return f"{where} has the mapping key {key!r}"
            found = _first_unkept(item, f"{where}.{key}")
            if found:
                return found
        return None
    if isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, list):
                return f"{where}[{index}] is a sequence inside a sequence"
            found = _first_unkept(item, f"{where}[{index}]")
            if found:
                return found
        return None
    if value is None or type(value) in (bool, int):
        return None
    if type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return f"{where} holds a lone surrogate"
        return None
    return f"{where} is a {type(value).__name__}"


def require_durable(value: object, described: str) -> None:
    """``value`` survives the recovery record as itself, or a refusal.

    The record is the invocation as :meth:`MutationController.open` normalizes
    it (a JSON round trip), dumped by ``yamlish`` and written as UTF-8; resume
    reads it back with ``yamlish``. Both readings must give back ``value``
    exactly - same types throughout - and the text must encode.
    """
    holder = {"value": value}
    try:
        normalized = json.loads(json.dumps(holder, sort_keys=True))
        text = yamlish.dump(holder)
        text.encode("utf-8")
        loaded = yamlish.load(text)
    except (TypeError, ValueError, RecursionError) as exc:  # YamlishError and UnicodeError are ValueErrors
        raise refused(described, _first_unkept(value, "the value") or f"{type(exc).__name__}: {exc}") from exc
    if not (_same(normalized, holder) and _same(loaded, holder)):
        raise refused(described, _first_unkept(value, "the value") or "it reads back as another value")


# --------------------------------------------------------------------------- semantic (Markdown structure)

def require_entity_text(kind: str, name: str, sections: Sequence[tuple[str, str]], described: str) -> None:
    """The entity file the writer makes of ``name`` and ``sections`` reads back as them, or a refusal.

    Rendered by the canonical writer and read back by the canonical reader: the
    name must come back as the one H1 identity it was given, the sections as
    exactly the headings written, in order, and each section as its text with
    its line ends read the way the reader reads them and stripped, as both the
    writer and the reader strip it. A blank name is the owner's to refuse.
    """
    if not name.strip():
        return
    entity_id = _PROBE_IDS[kind]
    content = render_entity({"id": entity_id, "display": "X-00", "type": kind}, render_body(name, list(sections)))
    try:
        _, _, body = entity_fields(kind, as_read_back(content), f"{entity_id}.md", entity_id)
    except ValidationError as exc:
        raise refused(described, f"the entity file it makes does not read back: {exc.message}") from exc
    read_name = Entity(entity_id, kind, {}, body, "").name
    if read_name != name:
        raise refused(f"{described} name", f"it reads back as the name {read_name!r}")
    written = [heading for heading, _ in sections]
    read = [match.group(1).strip() for match in _HEADING_RE.finditer(body)]
    if read != written:
        extra = [heading for heading in read if heading not in written] or read
        raise refused(described, f"its text adds or splits a section heading: {extra!r}")
    for heading, text in sections:
        if body_section(body, heading) != as_read_back(text.strip()):
            raise refused(f"{described} section {heading!r}", "it reads back as other text")


def require_work_text(kind: str, spec: object, described: str) -> None:
    """N3(a) for one Work / Phase-like spec (``name`` and ``desired_state``), judging only what is text.

    Anything that is not text is left to the owner's own shape rules, so a shared
    helper never takes over an owner's refusal of a value it reads differently.
    """
    name, desired = getattr(spec, "name", None), getattr(spec, "desired_state", None)
    if not isinstance(name, str) or not isinstance(desired, str):
        return
    heading = WORK_DESIRED_HEADING if kind == "work" else PHASE_DESIRED_HEADING
    require_entity_text(kind, name, [(heading, desired)], described)


def require_works_text(specs: object, described: str = "work", kind: str = "work") -> None:
    """N3(a) for every spec of a mapping of Work (or Phase) specs, in declared order."""
    if not isinstance(specs, Mapping):
        return
    for key, spec in specs.items():
        require_work_text(kind, spec, f"{described} {key!r}")
