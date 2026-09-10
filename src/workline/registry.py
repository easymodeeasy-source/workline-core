from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .errors import StopError

PROJECT_START_SKILL_ID = "skills/project-start"

REQUIRED_RULE_IDS = (
    "rules/git",
    "rules/ai-decision",
    "rules/human-confirmation",
    "rules/information-tracing",
)

REQUIRED_SKILL_IDS = (
    "skills/project-start",
    "skills/roadmap",
    "skills/phase-create",
    "skills/create",
    "skills/start",
)

_ID_LINE = re.compile(r"^\s*<!--\s*workline-id:\s*([^\s]+)\s*-->\s*$")
_TARGET_LINE = re.compile(r"^\s*<!--\s*workline-target:\s*([^\s]+)\s*-->\s*$")


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


def _extract_id_blocks(text: str) -> dict[str, list[str | None]]:
    blocks: dict[str, list[str | None]] = {}
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = _ID_LINE.match(line)
        if not match:
            continue
        item_id = match.group(1)
        target: str | None = None
        for candidate in lines[index + 1 : index + 6]:
            if _ID_LINE.match(candidate):
                break
            target_match = _TARGET_LINE.match(candidate)
            if target_match:
                target = target_match.group(1)
                break
        blocks.setdefault(item_id, []).append(target)
    return blocks


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
        entries = blocks.get(skill_id, ())
        if not entries:
            problems.append(RegistryProblem("required_skill_missing", f"missing required skill: {skill_id}"))
            continue
        if len(entries) > 1:
            problems.append(RegistryProblem("duplicate_skill", f"required skill is not unique: {skill_id}"))
            continue

        target = entries[0]
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

    target = _extract_id_blocks((root / "registry.md").read_text(encoding="utf-8"))[PROJECT_START_SKILL_ID][0]
    resolved = _safe_target(root, target) if target else None
    if resolved != skill:
        raise StopError(
            f"{root / 'registry.md'} routes workline://{PROJECT_START_SKILL_ID} to {resolved}, "
            f"not back to the executing Skill {skill}; configuration / routing error",
            code="routing_error",
        )
    return root
