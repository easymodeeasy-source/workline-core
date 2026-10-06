"""BL-055 shadow-authority detector: read-only, advisory, evidence- and responsibility-based.

A Project-local artifact is *shadow authority* only when it claims, or is used,
to replace or duplicate a responsibility canonical Workline already owns
(Roadmap / Phase / Work planning, lifecycle, current/next progression, routing
and bootstrap ...). Filename and vocabulary alone never establish it.

This module answers one question about one Project and changes nothing:

```text
none       no shadow-authority evidence found
suspected  an artifact appears to overlap a Workline-owned responsibility,
           but actual authority substitution cannot be proven
confirmed  positive structural or observed evidence shows a noncanonical
           artifact being used as Workline authority
```

Evidence sources (deliberately narrow, v1)
------------------------------------------

1. The exact Project bootstrap path, :data:`workline.store.BOOTSTRAP_REL_PATH`,
   compared with :func:`workline.bootstrap.render_bootstrap` under the very
   matching rule :func:`workline.bootstrap.bootstrap_state` uses (strict UTF-8,
   universal newlines, the bootstrap's own normalization)::

       absent                                      -> no evidence
       canonical ordinary file                     -> none
       differing ordinary file                     -> suspected  bootstrap.differs
       a directory / special file at the path      -> suspected  bootstrap.not_regular_file
       a redirecting indirection - symlink,
       junction, any name-surrogate reparse point -
       at the path or at any of its ancestors      -> confirmed  bootstrap.indirection
       a reparse point positively shown NOT to
       redirect the name (cloud placeholder ...)   -> uninspected (not none, not confirmed)

   Indirection is identified without following it: each component is found in
   a listing of its already-proven parent and opened relative to that handle
   (:mod:`workline.review.fsafe`); a link's target is never opened, read or
   listed. The bootstrap path also matches ``.claude/skills/**/SKILL.md`` but is
   classified only by these rules, never by the Skill rules below.

2. Project-local executable Skills, ``.claude/skills/**/SKILL.md`` (the
   bootstrap path and its ancestors excluded). Static text yields at most
   ``suspected``; see :func:`skill_text_claims` for the documented triggers:

   * ``skill.canonical_copy`` - the Skill's front matter declares the name of a
     canonical Workline Skill (:data:`workline.registry.REQUIRED_SKILL_IDS`) and
     a description naming Workline: a copy of a canonical Skill (§15.4, §33.8);
   * ``skill.authority_override`` - a sentence displaces canonical Workline
     (``instead of / not / ignore / replaces / regardless of`` + ``.workline`` /
     ``Workline`` / ``canonical`` / ``project-router``), demotes it (``Workline
     state is advisory``), makes a local artifact *the* Workline object (``treat
     X as the Workline roadmap``) or claims to be the source of truth for a
     Workline object (``X is the source of truth for the next Workline Work``,
     ``正本``, ``正式な次タスク``);
   * ``skill.parallel_progression`` / ``skill.parallel_lifecycle_state`` - a
     sentence in which something other than Workline keeps, decides or marks
     the current / next Work or Work / Phase completion or state.

   A filename, a directory name or Workline words alone produce nothing. A
   Skill that only describes a distinct domain capability, or that only calls
   the canonical router / owner and keeps no parallel Workline state, is
   ``none`` - including when Workline is the actor (``Let Workline decide the
   next Work``) or Workline completion is only a trigger (``After the Workline
   Work is done, update the changelog``). The reading depends on the file's
   bytes and its path class only - never on an mtime, an enumeration order or a
   list of filenames - and every limit applies per Skill directory.

3. :class:`ObservedEvidence` handed in by canonical router / owner code: an
   observed noncanonical route, owner delegation or write used to decide a
   Workline-owned state. Each is positive evidence: ``confirmed``.

Nothing else is opened. Repository prose (README, BACKLOG, TODO, STATUS,
CLAUDE.md, design documents, domain configuration ...), the Workline root, and
any other file in a Skill directory are never read, and there is no
forbidden-filename list. :func:`source_paths` enumerates exactly the files
:func:`detect_shadow_authority` would read, without reading them.

Advisory only
-------------

:func:`detect_shadow_authority` never raises: a source that cannot be inspected
is reported in :attr:`ShadowDiagnostic.uninspected` and contributes no evidence,
and :attr:`ShadowDiagnostic.bootstrap_inspected` / ``complete`` say whether a
``none`` is a proven none. It is not a validation Problem and blocks nothing. It
never edits, deletes, migrates or backfills anything, never mutates the
bootstrap, never creates Work and never reruns BL-011 migration; it takes no
lock, opens no mutation, runs no Git and uses no network. A static or semantic
reading never promotes ``suspected`` to ``confirmed``.

Every evidence item is H-3 public-safe: Project-relative POSIX paths, stable
rule and responsibility IDs, canonical owner IDs, a line number and a SHA-256
digest - never the artifact's text and never an absolute path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import io
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterable

from .errors import ValidationError
from .registry import PROJECT_ROUTER_SKILL_ID, PROJECT_START_SKILL_ID, REQUIRED_SKILL_IDS, SKILL_ID_PREFIX
from .review import fsafe
from .store import BOOTSTRAP_REL_PATH, WORKLINE_DIR, ProjectStore

# --------------------------------------------------------------------------- vocabulary

NONE = "none"
SUSPECTED = "suspected"
CONFIRMED = "confirmed"
#: Weakest first: a diagnostic's status is the strongest level among its evidence.
LEVELS = (NONE, SUSPECTED, CONFIRMED)

#: Where an evidence item came from (§30.26's three v1 sources).
SOURCE_BOOTSTRAP = "bootstrap"
SOURCE_LOCAL_SKILL = "local_skill"
SOURCE_OBSERVED = "observed"
SOURCES = (SOURCE_BOOTSTRAP, SOURCE_LOCAL_SKILL, SOURCE_OBSERVED)

#: The Workline-owned responsibilities of §15.2, as stable IDs.
PLANNING_STATE = "planning_state"
LIFECYCLE_STATE = "lifecycle_state"
PROGRESSION = "progression"
RELATION_SEMANTICS = "relation_semantics"
OPERATION_SEMANTICS = "operation_semantics"
REVIEW_AUTHORIZATION = "review_authorization"
ROUTING_BOOTSTRAP = "routing_bootstrap"
GIT_MUTATION_OWNERSHIP = "git_mutation_ownership"
REVIEW_POLICY = "review_policy"

#: Each Workline-owned responsibility and the canonical owner(s) that own its meaning.
RESPONSIBILITY_OWNERS: dict[str, tuple[str, ...]] = {
    PLANNING_STATE: ("skills/roadmap", "skills/create"),
    LIFECYCLE_STATE: ("skills/start", "skills/roadmap"),
    PROGRESSION: ("skills/roadmap", "skills/start"),
    RELATION_SEMANTICS: ("skills/create", "skills/roadmap"),
    OPERATION_SEMANTICS: ("registry.md", PROJECT_ROUTER_SKILL_ID),
    REVIEW_AUTHORIZATION: ("skills/review",),
    ROUTING_BOOTSTRAP: (PROJECT_START_SKILL_ID, PROJECT_ROUTER_SKILL_ID),
    GIT_MUTATION_OWNERSHIP: ("rules/git",),
    REVIEW_POLICY: ("project-policy-change",),
}
RESPONSIBILITIES = tuple(RESPONSIBILITY_OWNERS)

#: Who may hand in an :class:`ObservedEvidence`: the canonical Workline Skills (router and owners)
#: and the canonical Review Policy owner (§30.15). Nothing else observes on Workline's behalf.
OBSERVERS: tuple[str, ...] = tuple(REQUIRED_SKILL_IDS) + ("project-policy-change",)

#: Rule IDs: every evidence item carries exactly one.
RULE_BOOTSTRAP_DIFFERS = "bootstrap.differs"
RULE_BOOTSTRAP_NOT_REGULAR_FILE = "bootstrap.not_regular_file"
RULE_BOOTSTRAP_INDIRECTION = "bootstrap.indirection"
RULE_SKILL_CANONICAL_COPY = "skill.canonical_copy"
RULE_SKILL_AUTHORITY_OVERRIDE = "skill.authority_override"
RULE_SKILL_PARALLEL_PROGRESSION = "skill.parallel_progression"
RULE_SKILL_PARALLEL_LIFECYCLE = "skill.parallel_lifecycle_state"
RULE_OBSERVED_ROUTE = "observed.route"
RULE_OBSERVED_DELEGATION = "observed.delegation"
RULE_OBSERVED_WRITE = "observed.write"
#: Each rule and the one level it yields: static Skill text never yields ``confirmed``.
RULE_LEVELS: dict[str, str] = {
    RULE_BOOTSTRAP_DIFFERS: SUSPECTED,
    RULE_BOOTSTRAP_NOT_REGULAR_FILE: SUSPECTED,
    RULE_BOOTSTRAP_INDIRECTION: CONFIRMED,
    RULE_SKILL_CANONICAL_COPY: SUSPECTED,
    RULE_SKILL_AUTHORITY_OVERRIDE: SUSPECTED,
    RULE_SKILL_PARALLEL_PROGRESSION: SUSPECTED,
    RULE_SKILL_PARALLEL_LIFECYCLE: SUSPECTED,
    RULE_OBSERVED_ROUTE: CONFIRMED,
    RULE_OBSERVED_DELEGATION: CONFIRMED,
    RULE_OBSERVED_WRITE: CONFIRMED,
}
RULES = tuple(RULE_LEVELS)

#: The kinds of positive observation canonical router / owner code can hand in.
OBSERVED_ROUTE = "route"
OBSERVED_DELEGATION = "delegation"
OBSERVED_WRITE = "write"
OBSERVED_KINDS = (OBSERVED_ROUTE, OBSERVED_DELEGATION, OBSERVED_WRITE)
_OBSERVED_RULES = {
    OBSERVED_ROUTE: RULE_OBSERVED_ROUTE,
    OBSERVED_DELEGATION: RULE_OBSERVED_DELEGATION,
    OBSERVED_WRITE: RULE_OBSERVED_WRITE,
}

#: How an indirection on the bootstrap path is named (never followed to find out more).
INDIRECTION_SYMLINK = "symlink"
INDIRECTION_JUNCTION = "junction"
INDIRECTION_REPARSE_POINT = "reparse_point"  # another name-surrogate (redirecting) reparse tag
INDIRECTION_NON_REDIRECTING = "non_redirecting_reparse_point"  # e.g. a cloud placeholder: data, not a name
INDIRECTION_UNKNOWN = "indirection"
INDIRECTION_KINDS = (
    INDIRECTION_SYMLINK, INDIRECTION_JUNCTION, INDIRECTION_REPARSE_POINT, INDIRECTION_NON_REDIRECTING,
    INDIRECTION_UNKNOWN,
)

#: Why a source contributed no evidence (:class:`Uninspected`).
UNINSPECTED_UNREADABLE = "unreadable"
UNINSPECTED_CHANGED = "changed_during_inspection"
UNINSPECTED_INDIRECTION = "indirection_not_followed"
UNINSPECTED_NON_REDIRECTING = "non_redirecting_reparse_point"
UNINSPECTED_TOO_LARGE = "too_large"
UNINSPECTED_UNDECODABLE = "undecodable"
UNINSPECTED_LIMIT = "limit_exceeded"
UNINSPECTED_FAILED = "inspection_failed"
UNINSPECTED_OBSERVATION_REJECTED = "observation_rejected"
UNINSPECTED_ROOT_REFUSED = "project_root_refused"
UNINSPECTED_REASONS = (
    UNINSPECTED_UNREADABLE, UNINSPECTED_CHANGED, UNINSPECTED_INDIRECTION, UNINSPECTED_NON_REDIRECTING,
    UNINSPECTED_TOO_LARGE, UNINSPECTED_UNDECODABLE, UNINSPECTED_LIMIT, UNINSPECTED_FAILED,
    UNINSPECTED_OBSERVATION_REJECTED, UNINSPECTED_ROOT_REFUSED,
)

#: The Project-local executable Skill surface (§30.26 source 2).
SKILLS_REL_DIR = ".claude/skills"
SKILL_FILENAME = "SKILL.md"

#: Bounds that keep one advisory read small. Every Skill directory directly under ``.claude/skills`` is
#: one unit with its own budget, so one unit's size never changes another's result; past
#: ``MAX_SKILL_UNITS`` the whole Skill source is reported as not inspected, never partly.
MAX_FILE_BYTES = 1 << 20
MAX_SKILL_UNITS = 512
MAX_UNIT_ENTRIES = 2_000
MAX_UNIT_SKILL_FILES = 64
MAX_SKILL_DEPTH = 8

_WINDOWS = os.name == "nt"
#: ``IsReparseTagNameSurrogate``: the tag names another file system object (a link, a mount point).
_NAME_SURROGATE_BIT = 0x20000000


# --------------------------------------------------------------------------- records


def _require_text(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{field_name} must be a str, not {type(value).__name__}")
    return value


def _require_relative_path(value: object, field_name: str) -> str:
    """A Project-relative POSIX path: H-3-safe, never absolute, never escaping or aliasing anything."""
    text = _require_text(value, field_name)
    if not text or len(text) > 512:
        raise ValueError(f"{field_name} must be a non-empty Project-relative path of at most 512 characters")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in text):
        raise ValueError(f"{field_name} must not carry control characters")
    if "\\" in text or ":" in text or text.startswith("/"):
        raise ValueError(f"{field_name} must be a Project-relative POSIX path, not {text!r}")
    for part in text.split("/"):
        if part in ("", ".", ".."):
            raise ValueError(f"{field_name} must not have empty, '.' or '..' components: {text!r}")
        if part.endswith((".", " ")):
            # Windows drops a trailing dot or space: ``.workline.`` IS ``.workline`` there.
            raise ValueError(f"{field_name} must not have a component ending in '.' or ' ': {text!r}")
    return text


def _bootstrap_reserved(text: str) -> bool:
    """``text`` is the bootstrap path or one of its ancestors, compared case-insensitively."""
    parts = BOOTSTRAP_REL_PATH.casefold().split("/")
    candidate = text.casefold().split("/")
    return len(candidate) <= len(parts) and candidate == parts[: len(candidate)]


@dataclass(frozen=True)
class ObservedEvidence:
    """One positive observation, handed in by canonical router / owner code (§30.26 source 3).

    ``kind`` says what was observed:

    * ``route`` - a Workline request was routed through ``artifact`` instead of
      through the canonical router / owner;
    * ``delegation`` - a Workline-owned responsibility was delegated to
      ``artifact`` as its owner;
    * ``write`` - ``artifact`` was read or written to decide a Workline-owned
      state transition.

    ``artifact`` is the noncanonical artifact's Project-relative POSIX path. The
    canonical ``.workline`` namespace and the canonical bootstrap path (and its
    ancestors) are never noncanonical here, so they are refused; so is any
    spelling Windows would alias to them (a trailing ``.`` or space).
    ``responsibility`` is one of :data:`RESPONSIBILITIES`, and ``observed_by``
    one of :data:`OBSERVERS`.

    The record has no free text: every field is a closed vocabulary or a
    validated path, so it is H-3-safe by construction. There is no kind for a
    guess - a suspicion is not an observation - and a malformed record is
    refused when it is built (``ValueError``), never coerced. The detector
    rebuilds every record it is handed, so one that skipped this check is
    refused there too.
    """

    kind: str
    artifact: str
    responsibility: str
    observed_by: str

    def __post_init__(self) -> None:
        if _require_text(self.kind, "kind") not in OBSERVED_KINDS:
            raise ValueError(f"kind must be one of {OBSERVED_KINDS}, not {self.kind!r}")
        artifact = _require_relative_path(self.artifact, "artifact")
        if artifact.split("/", 1)[0].casefold() == WORKLINE_DIR.casefold():
            raise ValueError(f"{artifact!r} is in the canonical {WORKLINE_DIR} namespace, which is never noncanonical")
        if _bootstrap_reserved(artifact):
            raise ValueError(f"{artifact!r} is the canonical bootstrap path, judged only by the bootstrap rule")
        if _require_text(self.responsibility, "responsibility") not in RESPONSIBILITIES:
            raise ValueError(f"responsibility must be one of {RESPONSIBILITIES}, not {self.responsibility!r}")
        if _require_text(self.observed_by, "observed_by") not in OBSERVERS:
            raise ValueError(f"observed_by must be one of {OBSERVERS}, not {self.observed_by!r}")


@dataclass(frozen=True)
class ShadowEvidence:
    """One concise, H-3-safe evidence item, classified on its own.

    ``level`` is this item's own classification (``suspected`` or
    ``confirmed``), ``path`` the artifact (Project-relative POSIX), ``rule`` one
    of :data:`RULES`, ``responsibility`` the Workline-owned responsibility it
    overlaps and ``canonical_owner`` the canonical owner(s) of that meaning. The
    optional fields carry only what the rule saw: the indirection ``component``
    and its kind, the ``line`` of a Skill claim, the SHA-256 ``digest`` of bytes
    that were read, or the owner that made an observation.
    """

    level: str
    source: str
    path: str
    rule: str
    responsibility: str
    canonical_owner: tuple[str, ...]
    component: str | None = None
    indirection: str | None = None
    line: int | None = None
    digest: str | None = None
    observed_by: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "source": self.source,
            "path": self.path,
            "rule": self.rule,
            "responsibility": self.responsibility,
            "canonical_owner": list(self.canonical_owner),
            "component": self.component,
            "indirection": self.indirection,
            "line": self.line,
            "digest": self.digest,
            "observed_by": self.observed_by,
        }


@dataclass(frozen=True)
class Uninspected:
    """A source the detector did not inspect, and why. It is not evidence and changes no level."""

    path: str
    reason: str

    def to_json(self) -> dict[str, str]:
        return {"path": self.path, "reason": self.reason}


@dataclass(frozen=True)
class ShadowDiagnostic:
    """The advisory result: ``status`` (none | suspected | confirmed), its evidence, and what went uninspected.

    ``status`` is the strongest :attr:`ShadowEvidence.level` among
    ``evidence``, and ``none`` when there is none. ``bootstrap_inspected`` is
    true only when the bootstrap rule reached a verdict (absent, canonical,
    suspected or confirmed): a ``none`` with it false is *not* a proven none.
    ``complete`` additionally requires that nothing at all went uninspected.
    ``advisory`` is always true: the diagnostic discloses, it never decides
    validity or blocks (§30.28).
    """

    status: str
    evidence: tuple[ShadowEvidence, ...] = ()
    uninspected: tuple[Uninspected, ...] = ()
    bootstrap_inspected: bool = False

    @property
    def advisory(self) -> bool:
        return True

    @property
    def complete(self) -> bool:
        """Every v1 source was inspected and every observation accepted: the status is a proven one."""
        return self.bootstrap_inspected and not self.uninspected

    @property
    def confirmed(self) -> tuple[ShadowEvidence, ...]:
        """The confirmed subset of :attr:`evidence`."""
        return tuple(item for item in self.evidence if item.level == CONFIRMED)

    @property
    def suspected(self) -> tuple[ShadowEvidence, ...]:
        """The suspected subset of :attr:`evidence`."""
        return tuple(item for item in self.evidence if item.level == SUSPECTED)

    def to_json(self) -> dict[str, Any]:
        """The JSON-ready, deterministic projection (for the RB1 status policy section)."""
        return {
            "status": self.status,
            "advisory": True,
            "bootstrap_inspected": self.bootstrap_inspected,
            "complete": self.complete,
            "confirmed_count": len(self.confirmed),
            "suspected_count": len(self.suspected),
            "evidence": [item.to_json() for item in self.evidence],
            "uninspected": [item.to_json() for item in self.uninspected],
        }

    def render_lines(self) -> list[str]:
        """Human lines for an advisory display; the first line always states the status."""
        lines = [f"shadow authority (advisory): {self.status}"]
        if not self.bootstrap_inspected:
            lines[0] += " (bootstrap not inspected)"
        for item in self.evidence:
            where = item.path if item.component is None else f"{item.path} via {item.component} ({item.indirection})"
            if item.line is not None:
                where = f"{where}:{item.line}"
            lines.append(
                f"  {item.level} {item.rule} {_printable(where)} -> {item.responsibility} "
                f"owned by {', '.join(item.canonical_owner)}"
            )
        for skipped in self.uninspected:
            lines.append(f"  uninspected {_printable(skipped.path)}: {skipped.reason}")
        return lines


def _printable(text: str) -> str:
    return "".join(char if char.isprintable() else f"\\x{ord(char):02x}" for char in text)


def _evidence(source: str, path: str, rule: str, responsibility: str, *,
              owner: tuple[str, ...] | None = None, **detail: Any) -> ShadowEvidence:
    return ShadowEvidence(
        RULE_LEVELS[rule], source, path, rule, responsibility,
        RESPONSIBILITY_OWNERS[responsibility] if owner is None else owner, **detail,
    )


def _sort_key(item: ShadowEvidence) -> tuple:
    """Every field: two items that differ anywhere never tie, so no order depends on a hash seed."""
    return (
        -LEVELS.index(item.level), item.source, item.path, item.rule, item.line or 0, item.responsibility,
        item.observed_by or "", item.component or "", item.indirection or "", item.digest or "", item.canonical_owner,
    )


# --------------------------------------------------------------------------- one inspection


@dataclass
class _Inspection:
    """One pass over the v1 sources. With ``read`` false it lists and opens directories, and opens no file."""

    root: Path
    read: bool
    evidence: list[ShadowEvidence] = field(default_factory=list)
    uninspected: list[Uninspected] = field(default_factory=list)
    #: Every file read (or, with ``read`` false, that would be read), Project-relative, in read order.
    reads: list[str] = field(default_factory=list)
    bootstrap_inspected: bool = False

    def skip(self, path: str, reason: str) -> None:
        self.uninspected.append(Uninspected(path, reason))

    def isolated(self, source: str, inspect) -> None:
        try:
            inspect()
        except Exception:  # advisory: a detector failure is reported, never raised into validation or status
            self.skip(source, UNINSPECTED_FAILED)


def _project_root(project_root: object) -> Path | None:
    """The Project root as :class:`~workline.store.ProjectStore` identifies it, or ``None`` for a non-root.

    A ``ProjectStore``, a non-blank ``str`` or an ``os.PathLike`` naming text is
    a root; anything else - an empty or blank string (which would silently mean
    the process's working directory), a string holding NUL (which the operating
    system would cut short to another path), bytes, ``None``, a number - is
    refused. Nothing is read or written.
    """
    if isinstance(project_root, ProjectStore):
        return project_root.root
    if isinstance(project_root, os.PathLike):
        project_root = os.fspath(project_root)
    if not isinstance(project_root, str) or not project_root.strip() or "\0" in project_root:
        return None
    return ProjectStore(Path(project_root)).root


# --------------------------------------------------------------------------- no-follow filesystem access


def _same_name(found: str, wanted: str) -> bool:
    return found == wanted or (_WINDOWS and found.casefold() == wanted.casefold())


def _find(entries: list[fsafe.Entry], wanted: str) -> fsafe.Entry | None:
    """The listed entry named ``wanted``: exact first, then (Windows only) the one case-insensitive match."""
    for entry in entries:
        if entry.name == wanted:
            return entry
    folded = [entry for entry in entries if _same_name(entry.name, wanted)]
    return folded[0] if len(folded) == 1 else None


def _entries(here: fsafe.SafeDirectory, path: Path) -> list[fsafe.Entry]:
    """``here``'s entries, described without following any of them.

    The handle-bound listing is used as it is. Windows can hold a name that is
    not valid UTF-16 (an unpaired surrogate), which that listing cannot decode;
    then - and only then - the same directory is listed through its path. That
    is still the proven directory: every directory held from the Project root
    down is pinned (no rename, no delete) while the walk holds it. Each entry is
    still described from the directory listing itself, never by following it.
    One odd name therefore never hides the rest of a directory.
    """
    try:
        return here.entries()
    except UnicodeError:
        if not _WINDOWS:
            raise
    found: list[fsafe.Entry] = []
    with os.scandir(path) as listing:
        for item in listing:
            info = item.stat(follow_symlinks=False)
            link = item.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
            found.append(fsafe.Entry(
                item.name,
                is_dir=not link and stat.S_ISDIR(info.st_mode),
                is_file=not link and stat.S_ISREG(info.st_mode),
                is_indirection=link,
            ))
    return sorted(found, key=lambda entry: entry.name)


def _describe_indirection(path: Path) -> tuple[str, bool]:
    """``(kind, redirects)`` for an entry a listing already reported as an indirection. Total: never raises.

    ``lstat`` describes the entry without following a link or a mount point.
    ``redirects`` is false only for a reparse point positively shown not to
    name another object (a cloud placeholder, a deduplicated or compressed
    file ...); whatever cannot be described stays a redirecting indirection,
    exactly as listed.
    """
    try:
        info = os.lstat(path)
        tag = getattr(info, "st_reparse_tag", 0) or 0
        attributes = getattr(info, "st_file_attributes", 0) or 0
        if tag == fsafe.IO_REPARSE_TAG_MOUNT_POINT:
            return INDIRECTION_JUNCTION, True
        if stat.S_ISLNK(info.st_mode) or tag == fsafe.IO_REPARSE_TAG_SYMLINK:
            return INDIRECTION_SYMLINK, True
        if tag & _NAME_SURROGATE_BIT:
            return INDIRECTION_REPARSE_POINT, True
        if attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            return INDIRECTION_NON_REDIRECTING, False
    except Exception:
        pass
    return INDIRECTION_UNKNOWN, True


def _too_large(path: Path) -> bool:
    try:
        return os.lstat(path).st_size > MAX_FILE_BYTES
    except (OSError, ValueError):
        return False  # the bound read reports what it finds


def _on_bootstrap_path(relative: str) -> bool:
    """``relative`` is the bootstrap path or one of its ancestors: only the bootstrap rules classify those."""
    parts = BOOTSTRAP_REL_PATH.split("/")
    candidate = relative.split("/")
    return len(candidate) <= len(parts) and all(_same_name(a, b) for a, b in zip(candidate, parts))


# --------------------------------------------------------------------------- source 1: the bootstrap


def _is_canonical_bootstrap(data: bytes) -> bool:
    """``data`` is the canonical bootstrap under :func:`workline.bootstrap.bootstrap_state`'s own rule.

    ``bootstrap_state`` reads with ``Path.read_text(encoding="utf-8")`` (strict
    UTF-8, universal newlines) and compares through the bootstrap's own
    normalization against :func:`workline.bootstrap.render_bootstrap`; the same
    decode and the same comparison are made here, on bytes read without
    following anything. Both are imported, not restated.
    """
    from . import bootstrap

    try:
        text = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8", newline=None).read()
    except UnicodeError:
        return False
    return bootstrap._normalize(text) == bootstrap._normalize(bootstrap.render_bootstrap())


def _inspect_bootstrap(run: _Inspection) -> None:
    parts = BOOTSTRAP_REL_PATH.split("/")
    try:
        directories = [fsafe.SafeDirectory.open_root(run.root)]
    except (ValidationError, OSError, ValueError):
        run.skip(".", UNINSPECTED_UNREADABLE)
        return
    walked: list[str] = []
    try:
        for index, wanted in enumerate(parts):
            here = directories[-1]
            entry = _find(_entries(here, run.root.joinpath(*walked)), wanted)
            if entry is None:
                run.bootstrap_inspected = True  # absent: no evidence
                return
            walked.append(entry.name)
            relative = "/".join(walked)
            if entry.is_indirection:
                kind, redirects = _describe_indirection(run.root.joinpath(*walked))
                if redirects:
                    run.evidence.append(_evidence(
                        SOURCE_BOOTSTRAP, BOOTSTRAP_REL_PATH, RULE_BOOTSTRAP_INDIRECTION, ROUTING_BOOTSTRAP,
                        component=relative, indirection=kind,
                    ))
                    run.bootstrap_inspected = True
                else:
                    run.skip(relative, UNINSPECTED_NON_REDIRECTING)  # neither none nor confirmed: not proven
                return
            if index < len(parts) - 1:
                if not entry.is_dir:
                    run.bootstrap_inspected = True  # a non-directory ancestor: the path cannot exist, so absent
                    return
                child = here.child(entry.name)
                if child is None:
                    run.skip(relative, UNINSPECTED_CHANGED)
                    return
                directories.append(child)
                continue
            if not entry.is_file:
                run.evidence.append(_evidence(
                    SOURCE_BOOTSTRAP, BOOTSTRAP_REL_PATH, RULE_BOOTSTRAP_NOT_REGULAR_FILE, ROUTING_BOOTSTRAP
                ))
                run.bootstrap_inspected = True
                return
            if _too_large(run.root.joinpath(*walked)):
                # Far larger than the canonical text can be: it differs, and it is not read.
                run.evidence.append(_evidence(
                    SOURCE_BOOTSTRAP, BOOTSTRAP_REL_PATH, RULE_BOOTSTRAP_DIFFERS, ROUTING_BOOTSTRAP
                ))
                run.bootstrap_inspected = True
                return
            run.reads.append(BOOTSTRAP_REL_PATH)
            if not run.read:
                run.bootstrap_inspected = True
                return
            bound = here.read_file_bound(entry.name)
            if bound is None:
                run.skip(relative, UNINSPECTED_CHANGED)
                return
            if not _is_canonical_bootstrap(bound.data):
                run.evidence.append(_evidence(
                    SOURCE_BOOTSTRAP, BOOTSTRAP_REL_PATH, RULE_BOOTSTRAP_DIFFERS, ROUTING_BOOTSTRAP,
                    digest=hashlib.sha256(bound.data).hexdigest(),
                ))
            run.bootstrap_inspected = True
            return
    except (ValidationError, OSError, ValueError):
        run.skip("/".join(walked) or ".", UNINSPECTED_UNREADABLE)
    finally:
        for directory in reversed(directories):
            directory.close()


# --------------------------------------------------------------------------- source 2: local Skill static text


def _words(*words: str) -> str:
    """English words bounded by non-letters (``\\b`` would not bound a word written next to Japanese text)."""
    return r"(?<![A-Za-z])(?:" + "|".join(words) + r")(?![A-Za-z])"


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


#: Canonical Workline, named: the state, the product, the canonical router / owners.
_CANON = (
    r"(?:\.workline(?![A-Za-z])|" + _words("workline", "canonical") + r"|project-router|skills/[a-z][a-z0-9-]*"
    r"|正式な(?:router|owner|ルーター|ルート|ルーティング|Skill|実装))"
)
#: A canonical Workline owner named as the one acting (case-sensitive: the owner names, not common words).
_OWNER_NAMES = r"(?:START|Roadmap|ROADMAP|CREATE|REVIEW|Review)"
_ANCHOR = _rx(r"workline")
_CANON_RX = _rx(_CANON)
#: A Workline object a sentence can be about without saying "Workline": the current / next Work, Phase or
#: task (§15.2 "current/next Workline progression"), or a mid-sentence capitalised Work / Phase that is not
#: a numbered domain step.
_PROGRESSION_OBJECT = (
    r"(?:(?<![A-Za-z])(?:next|current|upcoming)\s+(?:workline\s+)?(?:task|work|step|item|phase)s?(?![A-Za-z])"
    r"|what\s+to\s+do\s+next|(?<![A-Za-z])which\s+(?:workline\s+)?(?:work|phase|task)(?![A-Za-z])"
    r"(?!\s+(?:is|was|are)\s+(?:done|finished|complete|completed|closed))"
    r"|(?:次|現在)の?(?:workline\s*の?)?(?:タスク|作業|work|phase|フェーズ|ステップ)|現在地)"
)
_PROGRESSION_OBJECT_RX = _rx(_PROGRESSION_OBJECT)
_CAPITALISED_WORK = re.compile(
    r"(?<![A-Za-z])(?i:the|a|an|each|every|this|that|which|next|current|its|our|any|your)\s+(?:Works?|Phase)"
    r"(?![A-Za-z]|\s*\d|\s+[A-Z])"
    r"|(?<![A-Za-z])(?:Works?|Phase)\s+(?i:completion|state|status|items?|is\s+(?:done|finished|complete))(?![A-Za-z])"
)
_LIFECYCLE_NOUN = _rx(
    _words("completion", "complete", "completed", "done", "finished", "closed", "state", "status", "lifecycle",
           "progress")
    + r"|完了|状態|進捗|ステータス"
)
_ROUTING_WORDS = _rx(_words("router", "route", "routes", "routing", "routed", "bootstrap") + r"|project-router|ルーティング|ルーター")
_DERIVED = _rx(_words("derived", "read-only", "mirror", "mirrors", "snapshot", "copy of") + r"|派生|参照用|読み取り専用|写し")

#: A word that turns the verb after it into a denial.
_NEGATION_BEFORE = _rx(
    r"(?:" + _words("not", "never", "no", "nor", "cannot", "can't", "don't", "doesn't", "won't", "mustn't",
                    "shouldn't", "without", "neither") + r")(?:\W+\w+){0,2}\W*$"
)
_NEGATION_AFTER_EN = _rx(r"^\W*(?:" + _words("no", "nothing", "none", "never") + r")")
_NEGATION_AFTER_JA = re.compile(r"^.{0,3}?(?:ない|ません|せず|しな|禁止|不可)")

# displacing canonical Workline: "instead of .workline", "replaces the canonical router", "ignore .workline"
_DISPLACE = _rx(
    r"(?:instead\s+of|rather\s+than|in\s+place\s+of|regardless\s+of|in\s+preference\s+to|takes?\s+precedence\s+over"
    r"|wins?\s+over|prevails?\s+over|" + _words(
        "replace", "replaces", "replaced", "replacing", "override", "overrides", "overrode", "overriding",
        "overridden", "supersede", "supersedes", "superseded", "superseding", "bypass", "bypasses", "bypassed",
        "bypassing", "ignore", "ignores", "ignored", "ignoring", "disregard", "disregards", "disregarding")
    + r")\s+(?:the\s+|any\s+|all\s+|every\s+)?" + _CANON
)
_DISPLACE_JA = _rx(_CANON + r"\s*(?:の代わりに|の代わり|を置き換え|を置き換|を上書き|を無視|は無視|より優先|を代替)")
# not consulting canonical Workline: "never consult .workline", "TODO.md, not .workline, is ..."
_NOT_CONSULTED = _rx(
    _words("not", "never", "don't", "doesn't", "without", "no longer") + r"\s+(?:\w+\s+)?"
    + _words("use", "uses", "using", "consult", "consults", "consulting", "read", "reads", "reading", "follow",
             "follows", "following", "check", "checks", "checking", "rely on", "relies on", "trust", "trusts",
             "look at", "looks at")
    + r"\s+(?:the\s+|any\s+)?" + _CANON
)
_NOT_CONSULTED_CONTRAST = _rx(r",\s*not\s+(?:the\s+)?" + _CANON + r"[^,]*,")
_NOT_CONSULTED_JA = _rx(_CANON + r"\s*(?:は|を)?\s*(?:使わない|使用しない|参照しない|見ない|読まない|確認しない|使わず|参照せず)")
#: "do not read .workline directly" defers to the canonical tool rather than displacing the state.
_DIRECTLY = _rx(_words("directly", "by hand", "manually", "raw") + r"|直接|手で|手作業")
# demoting canonical Workline: "Workline state is advisory only"
_DEMOTED = _rx(
    _CANON + r"(?:\s+(?:state|records?|data))?\s+(?:is|are)\s+(?:only\s+|just\s+|merely\s+)?"
    + _words("advisory", "optional", "secondary", "informational", "non-binding", "not authoritative",
             "not binding", "ignored", "obsolete")
)
# a local artifact AS the Workline object: "Treat BACKLOG.md as the Workline roadmap"
_AS_WORKLINE = _rx(
    _words("treat", "treats", "treating", "use", "uses", "using", "consider", "considers", "regard", "regards",
           "keep", "keeps")
    + r"[^;。]{0,60}?" + _words("as") + r"\s+(?:the\s+|a\s+|an\s+|our\s+)?(?:\.workline|workline)(?![A-Za-z])"
)
# claiming to be the source of truth
_SOURCE_OF_TRUTH = _rx(
    r"(?:single\s+)?source\s+of\s+truth|system\s+of\s+record|canonical\s+(?:record|list|source|tracker|backlog)|"
    + _words("authoritative", "the authority on", "the authority for", "master list", "master copy",
             "master record")
    + r"|正本(?:である|だ|です|とする|として|になる)|唯一の情報源"
    r"|正式な(?!\s*(?:workline|canonical|router|owner|ルーター|ルート|ルーティング|skill|実装))"
)
_COPULA = _rx(_words("is", "are", "remains", "becomes", "serves as", "acts as") + r"|が|は")
#: "The source of truth for the next Work is Workline": the claimed authority is canonical Workline itself.
_CANONICAL_PREDICATE = _rx(r"^[^,;]{0,80}?" + _words("is", "are") + r"\s+(?:the\s+|still\s+|always\s+)?" + _CANON)
_CLAUSE_BREAK = re.compile(r"[,;:、，：]")

# keeping / deciding state
_KEEP_VERB_EN = _rx(_words(
    "mark", "marks", "marked", "set", "sets", "record", "records", "recorded", "log", "logs", "logged", "track",
    "tracks", "tracked", "write", "writes", "wrote", "store", "stores", "persist", "persists", "keep", "keeps",
    "maintain", "maintains", "update", "updates", "manage", "manages", "govern", "governs", "own", "owns",
    "decide", "decides", "determine", "determines", "choose", "chooses", "select", "selects", "pick", "picks",
    "move", "moves", "tick", "ticks", "close", "closes", "flag", "flags", "declare", "declares", "define",
    "defines"))
_KEEP_VERB_JA = re.compile(r"記録|管理|保存|保持|更新|判定|決定|決め|選|設定|扱い|にする|とする|マーク")
_LIFECYCLE_AFTER_EN = _rx(
    r"^[^;]{0,60}?(?:" + _words("completion", "status", "state", "lifecycle", "progress", "done", "complete",
                                  "completed", "finished", "closed") + r")"
)
_PROGRESSION_AFTER_EN = _rx(r"^[^;]{0,50}?" + _PROGRESSION_OBJECT)
_PROGRESSION_PASSIVE = _rx(
    _PROGRESSION_OBJECT + r"[^;]{0,30}?(?:is|are)\s+(?:decided|chosen|selected|picked|tracked|recorded|set|defined|"
    r"kept|managed|determined)(?![^;]{0,12}\bby\s+(?:the\s+)?(?:" + _CANON + r"|(?-i:" + _OWNER_NAMES + r")))"
)
_LIFECYCLE_BEFORE_JA = re.compile(r"(?:完了|状態|進捗|ステータス)(?:を|は|として|と|も)[^。]{0,15}$")
_LIFECYCLE_MARK_JA = re.compile(r"完了(?:扱い|にする|とする)|完了と(?:記録|マーク)")
_PROGRESSION_BEFORE_JA = _rx(_PROGRESSION_OBJECT + r"(?:を|は|として|と|が)?[^。]{0,15}$")
#: Workline (or a canonical owner) is the one doing it: "Let Workline decide", "Workline tracks",
#: "decided by Workline", "Worklineが決める" (the nearest が / は / によって before the verb).
_ACTOR = r"(?:" + _CANON + r"|(?-i:" + _OWNER_NAMES + r"))"
_ACTOR_BEFORE = _rx(_ACTOR + r"(?:'s)?(?:\s+\w+)?(?:\s+to)?\s+$")
_ACTOR_AFTER = _rx(r"^\s*(?:\w+\s+)?by\s+(?:the\s+)?" + _ACTOR)
_JA_SUBJECT = re.compile(r"(?:が|は|によって|では|側で)")
_JA_ACTOR = _rx(_ACTOR + r"\s*$")
#: A character of Japanese text: an English keep verb written inside it is a noun ("pendingのrecord").
_JA_CHAR = re.compile(r"[぀-ヿ㐀-鿿＀-￯]")

_SENTENCE_BREAK = re.compile(r"(?<=[。！？；;])|(?<=[.!?])\s+")
_TRIGGER_EN = _rx(r"^\s*(?:after|when|whenever|once|before|until|if|as\s+soon\s+as)\b[^,]*,")


def _w_object(sentence: str) -> bool:
    """The sentence is about a Workline object: it names Workline, or the current / next Work, Phase or task."""
    return bool(_ANCHOR.search(sentence) or _PROGRESSION_OBJECT_RX.search(sentence) or _CAPITALISED_WORK.search(sentence))


def _w_object_named(sentence: str) -> bool:
    """Stricter, for keeping-state claims: Workline itself, or a Workline Work / Phase - not a generic "task"."""
    return bool(_ANCHOR.search(sentence) or _CAPITALISED_WORK.search(sentence))


def _responsibility(sentence: str) -> str:
    if _ROUTING_WORDS.search(sentence):
        return ROUTING_BOOTSTRAP
    if _PROGRESSION_OBJECT_RX.search(sentence):
        return PROGRESSION
    if _LIFECYCLE_NOUN.search(sentence):
        return LIFECYCLE_STATE
    return PLANNING_STATE


def _negated(sentence: str, start: int, end: int) -> bool:
    return bool(
        _NEGATION_BEFORE.search(sentence[max(0, start - 40):start])
        or _NEGATION_AFTER_EN.search(sentence[end:end + 12])
        or _NEGATION_AFTER_JA.search(sentence[end:end + 6])
    )


def _workline_acts(sentence: str, start: int, end: int) -> bool:
    if _ACTOR_BEFORE.search(sentence[max(0, start - 32):start]) or _ACTOR_AFTER.search(sentence[end:end + 32]):
        return True
    particles = list(_JA_SUBJECT.finditer(sentence, 0, start))
    return bool(particles and _JA_ACTOR.search(sentence[:particles[-1].start()]))


def _overrides(sentence: str) -> bool:
    """A claim that displaces, demotes or replaces canonical Workline, or takes its place as the authority."""
    for match in _DISPLACE.finditer(sentence):
        if not _negated(sentence, match.start(), match.start()):
            return True
    if any(not _negated(sentence, m.start(), m.end()) for m in _DISPLACE_JA.finditer(sentence)):
        return True
    if not _DIRECTLY.search(sentence) and (
        _NOT_CONSULTED.search(sentence) or _NOT_CONSULTED_CONTRAST.search(sentence) or _NOT_CONSULTED_JA.search(sentence)
    ):
        return True
    if _DEMOTED.search(sentence):
        return True
    for match in _AS_WORKLINE.finditer(sentence):
        if not _negated(sentence, match.start(), match.start()):
            return True
    if _w_object(sentence):
        for match in _SOURCE_OF_TRUTH.finditer(sentence):
            if _negated(sentence, match.start(), match.start()) or _CANONICAL_PREDICATE.search(sentence[match.end():]):
                continue
            segment = _CLAUSE_BREAK.split(sentence[:match.start()])[-1]
            copula = _COPULA.search(segment)
            subject = segment[:copula.start()] if copula else segment
            if not _CANON_RX.search(subject):
                return True
    return False


def _keeps_state(sentence: str) -> tuple[str, str] | None:
    """A parallel progression / lifecycle claim: something other than Workline keeps, decides or marks it."""
    if not _w_object_named(sentence) or _DERIVED.search(sentence):
        return None
    main = _TRIGGER_EN.sub("", sentence, count=1)
    for match in _KEEP_VERB_EN.finditer(main):
        around = main[max(0, match.start() - 1):match.start()] + main[match.end():match.end() + 1]
        if _JA_CHAR.search(around):
            continue  # an English word inside Japanese text is a noun, not this sentence's verb
        if _negated(main, match.start(), match.end()) or _workline_acts(main, match.start(), match.end()):
            continue
        after = main[match.end():]
        if _PROGRESSION_AFTER_EN.search(after):
            return RULE_SKILL_PARALLEL_PROGRESSION, PROGRESSION
        if _LIFECYCLE_AFTER_EN.search(after):
            return RULE_SKILL_PARALLEL_LIFECYCLE, LIFECYCLE_STATE
    if _PROGRESSION_PASSIVE.search(main):
        return RULE_SKILL_PARALLEL_PROGRESSION, PROGRESSION
    for match in _KEEP_VERB_JA.finditer(sentence):
        if _negated(sentence, match.start(), match.end()) or _workline_acts(sentence, match.start(), match.end()):
            continue
        before = sentence[max(0, match.start() - 24):match.start()]
        if _PROGRESSION_BEFORE_JA.search(before):
            return RULE_SKILL_PARALLEL_PROGRESSION, PROGRESSION
        if _LIFECYCLE_BEFORE_JA.search(before) or _LIFECYCLE_MARK_JA.search(sentence[max(0, match.start() - 4):match.end()]):
            return RULE_SKILL_PARALLEL_LIFECYCLE, LIFECYCLE_STATE
    return None


def _sentence_claim(sentence: str) -> tuple[str, str] | None:
    """``(rule, responsibility)`` when one sentence claims Workline lifecycle / progression authority; else ``None``."""
    if _overrides(sentence):
        return RULE_SKILL_AUTHORITY_OVERRIDE, _responsibility(sentence)
    return _keeps_state(sentence)


def skill_text_claims(text: str) -> tuple[tuple[str, str, int], ...]:
    """Every ``(rule, responsibility, line)`` sentence claim in one Skill's text: the first line per rule.

    A deterministic heuristic for an advisory *suspicion* only: whatever it
    finds is ``suspected`` at most. A line is split into sentences at ``. ! ?
    ;`` (and full-width forms); one sentence is a claim when

    ``skill.authority_override``
        it displaces canonical Workline (``instead of`` / ``rather than`` /
        ``regardless of`` / ``replaces`` / ``overrides`` / ``ignores`` / ``の代わりに``
        / ``より優先`` ... + ``.workline`` / ``Workline`` / ``canonical`` /
        ``project-router`` / ``skills/<id>``), says not to consult it (``never
        consult .workline``, ``X, not .workline, is``, ``.workline は使わない`` -
        but not ``... directly``), demotes it (``Workline state is advisory``),
        makes a local artifact the Workline object (``treat X as the Workline
        roadmap``), or names a non-canonical subject the source of truth for a
        Workline object (``source of truth`` / ``authoritative`` / ``正本`` /
        ``正式な`` ...); the displacing verb must not itself be denied;
    ``skill.parallel_progression`` / ``skill.parallel_lifecycle_state``
        it is about a Workline object, is not derived / read-only, and a
        keeping verb (``decides``, ``records``, ``marks``, ``tracks``,
        ``governs``, ``moves`` / ``決める``, ``記録``, ``管理`` ...) that is
        neither denied nor done by Workline itself (``Let Workline decide``,
        ``Workline tracks``, ``Worklineが決める``, ``decided by Workline``) has the
        current / next Work or a completion / state as its object - a leading
        ``After / When ... ,`` clause is only a trigger.

    A Workline object is ``Workline`` / ``.workline``, the current / next Work,
    Phase or task, or a mid-sentence capitalised ``Work`` / ``Phase`` that is not
    a numbered step.
    """
    found: dict[str, tuple[str, str, int]] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        for sentence in _SENTENCE_BREAK.split(line):
            claim = _sentence_claim(sentence)
            if claim is not None and claim[0] not in found:
                found[claim[0]] = (claim[0], claim[1], number)
    return tuple(sorted(found.values(), key=lambda item: (item[2], item[0])))


#: The canonical Workline Skill names, from the registry's own required set.
_CANONICAL_SKILL_NAMES = {skill_id[len(SKILL_ID_PREFIX):]: skill_id for skill_id in REQUIRED_SKILL_IDS}
_FRONT_FIELD = re.compile(r"^([A-Za-z_-]+)\s*:\s*(.*)$")


def canonical_copy_of(text: str) -> str | None:
    """The canonical Skill ID this Skill's front matter declares itself to be, or ``None``.

    A copy of a canonical Workline Skill keeps its front matter: a ``name`` that
    is a canonical Workline Skill's (:data:`workline.registry.REQUIRED_SKILL_IDS`)
    and a ``description`` that names Workline. A Skill that merely shares a name
    (a code-review Skill called ``review``) does not name Workline and is not one.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fields: dict[str, str] = {}
    current = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        found = _FRONT_FIELD.match(line)
        if found:
            current = found.group(1).lower()
            fields[current] = found.group(2).strip()
        elif current is not None and line[:1].isspace():
            fields[current] += " " + line.strip()
    name = fields.get("name", "").strip("'\"")
    if name in _CANONICAL_SKILL_NAMES and _ANCHOR.search(fields.get("description", "")):
        return _CANONICAL_SKILL_NAMES[name]
    return None


# --------------------------------------------------------------------------- the Skill walk


@dataclass
class _Unit:
    """One Skill directory directly under ``.claude/skills``, walked within its own budget."""

    entries: int = 0
    files: list[str] = field(default_factory=list)
    skipped: list[Uninspected] = field(default_factory=list)


def _collect(run: _Inspection, here: fsafe.SafeDirectory, relative: str, depth: int, unit: _Unit) -> bool:
    """List ``relative`` into ``unit``; ``False`` the moment the unit's budget is exceeded."""
    entries = _entries(here, run.root.joinpath(*relative.split("/")))
    unit.entries += len(entries)
    if unit.entries > MAX_UNIT_ENTRIES:
        return False
    for entry in entries:
        path = f"{relative}/{entry.name}"
        if entry.is_indirection:
            if not _on_bootstrap_path(path):
                unit.skipped.append(Uninspected(path, UNINSPECTED_INDIRECTION))
            continue
        if entry.is_dir:
            if depth + 1 > MAX_SKILL_DEPTH:
                return False
            child = here.child(entry.name)
            if child is None:
                unit.skipped.append(Uninspected(path, UNINSPECTED_CHANGED))
                continue
            with child:
                if not _collect(run, child, path, depth + 1, unit):
                    return False
            continue
        if entry.is_file and _same_name(entry.name, SKILL_FILENAME) and not _on_bootstrap_path(path):
            unit.files.append(path)
            if len(unit.files) > MAX_UNIT_SKILL_FILES:
                return False
    return True


def _read_skill(run: _Inspection, path: str) -> None:
    parts = path.split("/")
    if _too_large(run.root.joinpath(*parts)):
        run.skip(path, UNINSPECTED_TOO_LARGE)
        return
    run.reads.append(path)
    if not run.read:
        return
    try:
        chain = fsafe.walk(run.root, parts[:-1])
        if chain is None:
            run.skip(path, UNINSPECTED_CHANGED)
            return
        with chain:
            bound = chain.last.read_file_bound(parts[-1])
    except (ValidationError, OSError, ValueError):
        run.skip(path, UNINSPECTED_UNREADABLE)
        return
    if bound is None:
        run.skip(path, UNINSPECTED_CHANGED)
        return
    try:
        text = bound.data.decode("utf-8-sig")
    except UnicodeError:
        run.skip(path, UNINSPECTED_UNDECODABLE)
        return
    digest = hashlib.sha256(bound.data).hexdigest()
    copied = canonical_copy_of(text)
    if copied is not None:
        run.evidence.append(_evidence(SOURCE_LOCAL_SKILL, path, RULE_SKILL_CANONICAL_COPY, OPERATION_SEMANTICS,
                                      owner=(copied,), line=1, digest=digest))
    for rule, responsibility, line in skill_text_claims(text):
        run.evidence.append(_evidence(SOURCE_LOCAL_SKILL, path, rule, responsibility, line=line, digest=digest))


def _inspect_skills(run: _Inspection) -> None:
    try:
        directories = [fsafe.SafeDirectory.open_root(run.root)]
    except (ValidationError, OSError, ValueError):
        run.skip(".", UNINSPECTED_UNREADABLE)
        return
    walked: list[str] = []
    try:
        for wanted in SKILLS_REL_DIR.split("/"):
            entry = _find(_entries(directories[-1], run.root.joinpath(*walked)), wanted)
            if entry is None or not (entry.is_dir or entry.is_indirection):
                return  # no Skill surface at all
            walked.append(entry.name)
            if entry.is_indirection:
                run.skip("/".join(walked), UNINSPECTED_INDIRECTION)  # the bootstrap rule judges it; nothing is followed
                return
            child = directories[-1].child(entry.name)
            if child is None:
                run.skip("/".join(walked), UNINSPECTED_CHANGED)
                return
            directories.append(child)
        skills = directories[-1]
        top = _entries(skills, run.root.joinpath(*walked))
        if len(top) > MAX_SKILL_UNITS:
            run.skip(SKILLS_REL_DIR, UNINSPECTED_LIMIT)  # never a partial reading of the Skill source
            return
        files: list[str] = []
        for entry in top:  # each unit on its own: no unit's size, name or order changes another's result
            path = f"{SKILLS_REL_DIR}/{entry.name}"
            if entry.is_indirection:
                if not _on_bootstrap_path(path):
                    run.skip(path, UNINSPECTED_INDIRECTION)
                continue
            if entry.is_file:
                if _same_name(entry.name, SKILL_FILENAME):
                    files.append(path)
                continue
            if not entry.is_dir:
                continue
            unit = _Unit()
            try:
                child = skills.child(entry.name)
                if child is None:
                    run.skip(path, UNINSPECTED_CHANGED)
                    continue
                with child:
                    within = _collect(run, child, path, 0, unit)
            except (ValidationError, OSError, ValueError):
                run.skip(path, UNINSPECTED_UNREADABLE)
                continue
            if not within:
                run.skip(path, UNINSPECTED_LIMIT)
                continue
            run.uninspected.extend(unit.skipped)
            files.extend(unit.files)
    except (ValidationError, OSError, ValueError):
        run.skip("/".join(walked) or ".", UNINSPECTED_UNREADABLE)
        return
    finally:
        for directory in reversed(directories):
            directory.close()
    for path in files:
        _read_skill(run, path)


# --------------------------------------------------------------------------- source 3: observations


def _inspect_observed(run: _Inspection, observed: Iterable[object]) -> None:
    for index, item in enumerate(observed):
        try:
            if type(item) is not ObservedEvidence:
                raise ValueError("not an ObservedEvidence")
            # Rebuilt, so validated again: a record that skipped construction is refused here as well.
            accepted = ObservedEvidence(
                object.__getattribute__(item, "kind"), object.__getattribute__(item, "artifact"),
                object.__getattribute__(item, "responsibility"), object.__getattribute__(item, "observed_by"),
            )
        except Exception:
            run.skip(f"observed[{index}]", UNINSPECTED_OBSERVATION_REJECTED)
            continue
        run.evidence.append(_evidence(
            SOURCE_OBSERVED, accepted.artifact, _OBSERVED_RULES[accepted.kind], accepted.responsibility,
            observed_by=accepted.observed_by,
        ))


# --------------------------------------------------------------------------- public entry points


def detect_shadow_authority(project_root: object, observed: Iterable[ObservedEvidence] = ()) -> ShadowDiagnostic:
    """Classify one Project's shadow-authority evidence: read-only, advisory, never raising.

    ``project_root`` is the Project root: a :class:`ProjectStore`, or a
    non-blank path (``str`` / ``os.PathLike``); anything else is refused and
    reported, never read as the working directory. Reads exactly
    :func:`source_paths` - the bootstrap path and ``.claude/skills/**/SKILL.md``
    - without following any link, and takes ``observed`` (canonical router /
    owner observations) as given, each one validated again. Each source is
    isolated: one that cannot be read is reported in ``uninspected`` and the
    others still run. Writes nothing, takes no lock, runs no Git, uses no network.
    """
    try:
        root = _project_root(project_root)
    except Exception:
        root = None
    if root is None:
        return ShadowDiagnostic(NONE, (), (Uninspected(".", UNINSPECTED_ROOT_REFUSED),))
    run = _Inspection(root, read=True)
    run.isolated(BOOTSTRAP_REL_PATH, lambda: _inspect_bootstrap(run))
    run.isolated(SKILLS_REL_DIR, lambda: _inspect_skills(run))
    run.isolated("observed", lambda: _inspect_observed(run, observed))
    unique = sorted(set(run.evidence), key=_sort_key)
    status = max((item.level for item in unique), key=LEVELS.index, default=NONE)
    return ShadowDiagnostic(
        status,
        tuple(unique),
        tuple(sorted(set(run.uninspected), key=lambda item: (item.path, item.reason))),
        run.bootstrap_inspected,
    )


def source_paths(project_root: object) -> tuple[str, ...]:
    """The Project-relative files :func:`detect_shadow_authority` would read, in read order; none is opened here.

    The same no-follow walk, stopped before any file is opened: the bootstrap
    path when it is a plain file reached without indirection, then every plain
    ``SKILL.md`` under ``.claude/skills`` the Skill rules would read. Nothing
    else is ever read. Never raises: what cannot be listed is simply not here.
    """
    try:
        root = _project_root(project_root)
    except Exception:
        root = None
    if root is None:
        return ()
    run = _Inspection(root, read=False)
    run.isolated(BOOTSTRAP_REL_PATH, lambda: _inspect_bootstrap(run))
    run.isolated(SKILLS_REL_DIR, lambda: _inspect_skills(run))
    return tuple(run.reads)


__all__ = [
    "CONFIRMED",
    "GIT_MUTATION_OWNERSHIP",
    "INDIRECTION_JUNCTION",
    "INDIRECTION_KINDS",
    "INDIRECTION_NON_REDIRECTING",
    "INDIRECTION_REPARSE_POINT",
    "INDIRECTION_SYMLINK",
    "INDIRECTION_UNKNOWN",
    "LEVELS",
    "LIFECYCLE_STATE",
    "MAX_FILE_BYTES",
    "MAX_SKILL_DEPTH",
    "MAX_SKILL_UNITS",
    "MAX_UNIT_ENTRIES",
    "MAX_UNIT_SKILL_FILES",
    "NONE",
    "OBSERVED_DELEGATION",
    "OBSERVED_KINDS",
    "OBSERVED_ROUTE",
    "OBSERVED_WRITE",
    "OBSERVERS",
    "OPERATION_SEMANTICS",
    "PLANNING_STATE",
    "PROGRESSION",
    "RELATION_SEMANTICS",
    "RESPONSIBILITIES",
    "RESPONSIBILITY_OWNERS",
    "REVIEW_AUTHORIZATION",
    "REVIEW_POLICY",
    "ROUTING_BOOTSTRAP",
    "RULES",
    "RULE_BOOTSTRAP_DIFFERS",
    "RULE_BOOTSTRAP_INDIRECTION",
    "RULE_BOOTSTRAP_NOT_REGULAR_FILE",
    "RULE_LEVELS",
    "RULE_OBSERVED_DELEGATION",
    "RULE_OBSERVED_ROUTE",
    "RULE_OBSERVED_WRITE",
    "RULE_SKILL_AUTHORITY_OVERRIDE",
    "RULE_SKILL_CANONICAL_COPY",
    "RULE_SKILL_PARALLEL_LIFECYCLE",
    "RULE_SKILL_PARALLEL_PROGRESSION",
    "SKILLS_REL_DIR",
    "SKILL_FILENAME",
    "SOURCES",
    "SOURCE_BOOTSTRAP",
    "SOURCE_LOCAL_SKILL",
    "SOURCE_OBSERVED",
    "SUSPECTED",
    "UNINSPECTED_CHANGED",
    "UNINSPECTED_FAILED",
    "UNINSPECTED_INDIRECTION",
    "UNINSPECTED_LIMIT",
    "UNINSPECTED_NON_REDIRECTING",
    "UNINSPECTED_OBSERVATION_REJECTED",
    "UNINSPECTED_REASONS",
    "UNINSPECTED_ROOT_REFUSED",
    "UNINSPECTED_TOO_LARGE",
    "UNINSPECTED_UNDECODABLE",
    "UNINSPECTED_UNREADABLE",
    "ObservedEvidence",
    "ShadowDiagnostic",
    "ShadowEvidence",
    "Uninspected",
    "canonical_copy_of",
    "detect_shadow_authority",
    "skill_text_claims",
    "source_paths",
]
