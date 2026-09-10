from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .errors import StopError

PROJECT_START_SKILL_ID = "skills/project-start"
PROJECT_ROUTER_SKILL_ID = "skills/project-router"

REQUIRED_RULE_IDS = (
    "rules/git",
    "rules/ai-decision",
    "rules/human-confirmation",
    "rules/information-tracing",
)

# The stable IDs a Workline root must provide. This set detects *missing*
# required authority; it is deliberately not the list of Skills that exist.
# Additional ``skills/*`` entries are allowed and discovered dynamically, so
# adding a canonical Skill never requires touching a Project.
REQUIRED_SKILL_IDS = (
    "skills/project-start",
    "skills/project-router",
    "skills/roadmap",
    "skills/phase-create",
    "skills/create",
    "skills/start",
)

SKILL_ID_PREFIX = "skills/"

# Declared applicability of a canonical Skill, read from the registry rather
# than inferred from its name. ``project-router`` selects among ``PROJECT``
# Skills only, which is what keeps an established Project out of the
# pre-project initialization path and keeps the router from routing to itself
# — without any Skill ever being named in code.
CONTEXT_PRE_PROJECT = "pre-project"
CONTEXT_PROJECT = "project"
CONTEXT_ROUTER = "router"
SKILL_CONTEXTS = (CONTEXT_PRE_PROJECT, CONTEXT_PROJECT, CONTEXT_ROUTER)

_ID_LINE = re.compile(r"^\s*<!--\s*workline-id:\s*([^\s]+)\s*-->\s*$")
_TARGET_LINE = re.compile(r"^\s*<!--\s*workline-target:\s*([^\s]+)\s*-->\s*$")
_CONTEXT_LINE = re.compile(r"^\s*<!--\s*workline-context:\s*([^\s]+)\s*-->\s*$")


@dataclass(frozen=True)
class RegistryProblem:
    code: str
    message: str


@dataclass(frozen=True)
class RegistryValidation:
    problems: tuple[RegistryProblem, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass(frozen=True)
class RegistryBlock:
    """One ``workline-id`` block: its routing target and declared context."""

    target: str | None
    context: str | None


@dataclass(frozen=True)
class SkillEntry:
    """A registry-routed canonical Skill, resolved from stable ID alone."""

    skill_id: str
    target: str
    context: str
    path: Path

    @property
    def selectable_in_project(self) -> bool:
        return self.context == CONTEXT_PROJECT


def _extract_id_blocks(text: str) -> dict[str, list[RegistryBlock]]:
    blocks: dict[str, list[RegistryBlock]] = {}
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = _ID_LINE.match(line)
        if not match:
            continue
        item_id = match.group(1)
        target: str | None = None
        context: str | None = None
        for candidate in lines[index + 1 : index + 6]:
            if _ID_LINE.match(candidate):
                break
            target_match = _TARGET_LINE.match(candidate)
            if target_match:
                target = target_match.group(1)
                continue
            context_match = _CONTEXT_LINE.match(candidate)
            if context_match:
                context = context_match.group(1)
        blocks.setdefault(item_id, []).append(RegistryBlock(target, context))
    return blocks


def _target_of(blocks: dict[str, list[RegistryBlock]], item_id: str) -> str | None:
    entries = blocks.get(item_id, ())
    return entries[0].target if len(entries) == 1 else None


def _safe_target(root: Path, target: str) -> Path | None:
    candidate = (root / target).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def validate_registry(root: Path) -> RegistryValidation:
    root = root.resolve()
    registry = root / "registry.md"
    problems: list[RegistryProblem] = []

    if not registry.is_file():
        return RegistryValidation((RegistryProblem("registry_missing", "registry.md is missing"),))

    try:
        text = registry.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return RegistryValidation((RegistryProblem("registry_unreadable", "registry.md is not readable UTF-8"),))

    blocks = _extract_id_blocks(text)

    for rule_id in REQUIRED_RULE_IDS:
        count = len(blocks.get(rule_id, ()))
        if count == 0:
            problems.append(RegistryProblem("required_rule_missing", f"missing required rule: {rule_id}"))
        elif count > 1:
            problems.append(RegistryProblem("duplicate_rule", f"required rule is not unique: {rule_id}"))

    for skill_id in REQUIRED_SKILL_IDS:
        if not blocks.get(skill_id):
            problems.append(RegistryProblem("required_skill_missing", f"missing required skill: {skill_id}"))

    # Every registered Skill is validated, not just the required ones: a broken
    # or duplicated optional Skill must STOP routing too, never degrade into a
    # similar-looking candidate.
    for skill_id in sorted(k for k in blocks if k.startswith(SKILL_ID_PREFIX)):
        entries = blocks[skill_id]
        if len(entries) > 1:
            problems.append(RegistryProblem("duplicate_skill", f"skill is not unique: {skill_id}"))
            continue

        context = entries[0].context
        if context is None:
            problems.append(RegistryProblem("skill_context_missing", f"missing context for skill: {skill_id}"))
        elif context not in SKILL_CONTEXTS:
            problems.append(
                RegistryProblem("skill_context_invalid", f"unknown context for skill {skill_id}: {context}")
            )

        target = entries[0].target
        if target is None:
            problems.append(RegistryProblem("skill_target_missing", f"missing target for skill: {skill_id}"))
            continue
        resolved = _safe_target(root, target)
        if resolved is None:
            problems.append(RegistryProblem("skill_target_outside_root", f"target escapes Workline root: {skill_id}"))
            continue
        if not resolved.is_file():
            problems.append(RegistryProblem("skill_target_unreadable", f"target is not a file: {skill_id} -> {target}"))
            continue
        try:
            content = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            problems.append(RegistryProblem("skill_target_unreadable", f"target is not readable UTF-8: {skill_id} -> {target}"))
            continue
        if not content.strip():
            problems.append(RegistryProblem("skill_target_empty", f"target is empty: {skill_id} -> {target}"))

    return RegistryValidation(tuple(problems))


def owning_workline_root(skill_file: Path) -> Path:
    """The Workline root that owns a concrete ``skills/project-start`` SKILL.md.

    Used when no Workline root was given explicitly: the root is read off the
    Skill that is actually executing, never searched for. Only the nearest
    ancestor holding a ``registry.md`` is considered, and routing must close
    the loop — that registry's ``workline://skills/project-start`` target has
    to resolve back to this very file. No sibling directory, no second
    registry, no filename / mtime / Git-recency / similarity comparison enters
    the decision. A root that fails this is a configuration / routing error,
    not an invitation to look somewhere else.
    """
    skill = Path(skill_file).resolve()
    if not skill.is_file():
        raise StopError(
            f"concrete ProjectSTART SKILL.md is not a readable file: {skill}",
            code="routing_error",
        )

    root = next((parent for parent in skill.parents if (parent / "registry.md").is_file()), None)
    if root is None:
        raise StopError(
            f"no registry.md owns {skill}; configuration / routing error",
            code="routing_error",
        )

    validation = validate_registry(root)
    if not validation.ok:
        detail = "; ".join(f"{p.code}: {p.message}" for p in validation.problems)
        raise StopError(
            f"registry of the owning Workline root ({root}) is invalid: {detail}",
            code="routing_error",
        )

    blocks = _extract_id_blocks((root / "registry.md").read_text(encoding="utf-8"))
    target = _target_of(blocks, PROJECT_START_SKILL_ID)
    resolved = _safe_target(root, target) if target else None
    if resolved != skill:
        raise StopError(
            f"{root / 'registry.md'} routes workline://{PROJECT_START_SKILL_ID} to {resolved}, "
            f"not back to the executing Skill {skill}; configuration / routing error",
            code="routing_error",
        )
    return root


def _validated_blocks(root: Path) -> dict[str, list[RegistryBlock]]:
    """Registry blocks of a root whose registry validates, or STOP.

    A broken registry never degrades into a partial inventory: routing stops.
    """
    validation = validate_registry(root)
    if not validation.ok:
        detail = "; ".join(f"{p.code}: {p.message}" for p in validation.problems)
        raise StopError(f"registry validation failed for {root}: {detail}", code="registry_invalid")
    return _extract_id_blocks((root / "registry.md").read_text(encoding="utf-8"))


def skill_inventory(root: Path) -> dict[str, SkillEntry]:
    """Every canonical Skill the registry currently routes, by stable ID.

    Read from the registry at call time, so a Skill added to the Workline root
    becomes available to every Project without changing anything inside those
    Projects. No hard-coded Skill list exists on either side of the boundary.
    """
    root = Path(root).resolve()
    blocks = _validated_blocks(root)
    inventory: dict[str, SkillEntry] = {}
    for skill_id in sorted(k for k in blocks if k.startswith(SKILL_ID_PREFIX)):
        entry = blocks[skill_id][0]
        resolved = _safe_target(root, entry.target) if entry.target else None
        if resolved is None or entry.context is None:
            # validate_registry already accepted this root, so this is
            # unreachable in practice; stopping keeps the invariant explicit.
            raise StopError(f"unroutable skill survived validation: {skill_id}", code="registry_invalid")
        inventory[skill_id] = SkillEntry(skill_id, entry.target, entry.context, resolved)
    return inventory


def router_candidates(root: Path) -> dict[str, SkillEntry]:
    """Skills the project-router may delegate to from inside a Project.

    Selection is by each Skill's declared ``workline-context``: only
    ``project`` Skills qualify. ``pre-project`` (initialization) and ``router``
    (the router itself) are excluded structurally, so an established Project
    can neither be re-initialized nor routed into the router recursively, and
    no Skill is ever excluded by name.
    """
    return {
        skill_id: entry
        for skill_id, entry in skill_inventory(root).items()
        if entry.selectable_in_project
    }


def resolve_skill(root: Path, skill_id: str) -> SkillEntry:
    """Resolve one stable Skill ID, or STOP.

    Never falls back to a similar ID, a filename, an mtime or a Git-recency
    comparison: an unresolvable ID is a routing error.
    """
    inventory = skill_inventory(root)
    entry = inventory.get(skill_id)
    if entry is None:
        raise StopError(
            f"workline://{skill_id} is not registered in {root / 'registry.md'}; "
            "no name / path / similarity fallback is attempted",
            code="routing_error",
        )
    return entry
