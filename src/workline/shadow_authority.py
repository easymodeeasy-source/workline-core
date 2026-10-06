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
       symlink / junction / other reparse point
       at the path or at any of its ancestors      -> confirmed  bootstrap.indirection

   Indirection is identified without following it: each component is found in
   a handle-bound listing of its already-proven parent and opened relative to
   that handle (:mod:`workline.review.fsafe`); a link's target is never opened,
   read or listed. The bootstrap path also matches ``.claude/skills/**/SKILL.md``
   but is classified only by these rules, never by the Skill text rule below.

2. Project-local executable Skills, ``.claude/skills/**/SKILL.md`` (the
   bootstrap path and its ancestors excluded). Static text produces at most
   ``suspected``. The trigger is one sentence (a line split at ``. ! ? ;`` and
   their full-width forms) that

   * names Workline (``Workline`` / ``.workline``) - or claims authority over
     the current / next Work, Phase or task, which in an established Workline
     Project names Workline progression by itself (§15.2),
   * neither denies (``not``, ``never``, ``ない``, ``禁止`` ...) nor defers to
     the canonical router / owner (``canonical``, ``正式``, ``project-router``,
     ``run-workline``, ``skills/<id>``), and
   * claims Workline lifecycle / progression authority:

     - ``skill.authority_override``: it claims to be the source of truth for,
       to override, supersede or replace Workline state (``source of truth``,
       ``authoritative``, ``overrides``, ``正本``, ``優先``, ``上書き`` ...);
       its responsibility is ``progression`` for the current / next Work,
       ``lifecycle_state`` for state / completion, else ``planning_state``;
     - ``skill.parallel_progression``: it keeps or decides the current / next
       Work / Phase / task (``next`` + ``task`` + ``decides`` / ``records`` ...);
     - ``skill.parallel_lifecycle_state``: it keeps, marks or decides Work /
       Phase / Roadmap completion or state (``marks`` + ``Work`` + ``done`` ...).

   A filename, a directory name or Workline words alone produce nothing; a
   Skill that only describes a distinct domain capability, or only calls the
   canonical router / owner and keeps no parallel Workline state, is ``none``.
   The reading depends on the file's bytes and its path class only - never on
   an mtime, an enumeration order or a list of filenames.

3. :class:`ObservedEvidence` handed in by canonical router / owner code: an
   observed noncanonical route, owner delegation or write used to decide a
   Workline-owned state. Each is positive evidence: ``confirmed``.

Nothing else is opened. Repository prose (README, BACKLOG, TODO, STATUS,
CLAUDE.md, design documents, domain configuration ...) and any other file in a
Skill directory are never read, and there is no forbidden-filename list.
:func:`source_paths` enumerates exactly the files :func:`detect_shadow_authority`
would read, without reading them.

Advisory only
-------------

:func:`detect_shadow_authority` never raises: a source that cannot be inspected
is reported in :attr:`ShadowDiagnostic.uninspected` and contributes no evidence.
It is not a validation Problem and blocks nothing. It never edits, deletes,
migrates or backfills anything, never mutates the bootstrap, never creates Work
and never reruns BL-011 migration; it takes no lock, opens no mutation, runs no
Git and uses no network. A static or semantic reading never promotes
``suspected`` to ``confirmed``.

Every evidence item is H-3 public-safe: Project-relative POSIX paths, stable
rule and responsibility IDs, canonical owner IDs, a line number and a SHA-256
digest - never the artifact's text and never an absolute path.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterable

from .errors import ValidationError
from .registry import PROJECT_ROUTER_SKILL_ID, PROJECT_START_SKILL_ID
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

#: Rule IDs: every evidence item carries exactly one.
RULE_BOOTSTRAP_DIFFERS = "bootstrap.differs"
RULE_BOOTSTRAP_NOT_REGULAR_FILE = "bootstrap.not_regular_file"
RULE_BOOTSTRAP_INDIRECTION = "bootstrap.indirection"
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
INDIRECTION_REPARSE_POINT = "reparse_point"
INDIRECTION_UNKNOWN = "indirection"

#: Why a source contributed no evidence (:class:`Uninspected`).
UNINSPECTED_UNREADABLE = "unreadable"
UNINSPECTED_CHANGED = "changed_during_inspection"
UNINSPECTED_INDIRECTION = "indirection_not_followed"
UNINSPECTED_TOO_LARGE = "too_large"
UNINSPECTED_UNDECODABLE = "undecodable"
UNINSPECTED_LIMIT = "limit_exceeded"
UNINSPECTED_FAILED = "inspection_failed"
UNINSPECTED_OBSERVATION_REJECTED = "observation_rejected"

#: The Project-local executable Skill surface (§30.26 source 2).
SKILLS_REL_DIR = ".claude/skills"
SKILL_FILENAME = "SKILL.md"

#: Bounds that keep one advisory read small: a larger artifact is reported, not read.
MAX_FILE_BYTES = 1 << 20
MAX_SKILL_DEPTH = 8
MAX_SKILL_FILES = 256
MAX_LISTED_ENTRIES = 10_000

_WINDOWS = os.name == "nt"


# --------------------------------------------------------------------------- records


def _require_text(value: object, field: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{field} must be a str, not {type(value).__name__}")
    return value


_OWNER_ID = re.compile(r"[a-z][a-z0-9-]{0,62}(?:/[a-z][a-z0-9-]{0,62})?")


def _require_relative_path(value: object, field: str) -> str:
    """A Project-relative POSIX path: H-3-safe, never absolute, never escaping the Project."""
    text = _require_text(value, field)
    if not text or len(text) > 512:
        raise ValueError(f"{field} must be a non-empty Project-relative path of at most 512 characters")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in text):
        raise ValueError(f"{field} must not carry control characters")
    if "\\" in text or ":" in text or text.startswith("/"):
        raise ValueError(f"{field} must be a Project-relative POSIX path, not {text!r}")
    if any(part in ("", ".", "..") for part in text.split("/")):
        raise ValueError(f"{field} must not have empty, '.' or '..' components: {text!r}")
    return text


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

    ``artifact`` is the noncanonical artifact's Project-relative POSIX path; the
    canonical ``.workline`` namespace is never noncanonical, so it is refused.
    ``responsibility`` is one of :data:`RESPONSIBILITIES`, and ``observed_by`` the
    canonical owner that observed it (a registry ID such as
    ``skills/project-router``, or an owner name such as ``start``).

    The record has no free text: every field is a closed vocabulary or a
    validated identifier, so it is H-3-safe by construction. There is no kind
    for a guess - a suspicion is not an observation - and a malformed record is
    refused when it is built (``ValueError``), never coerced.
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
        if _require_text(self.responsibility, "responsibility") not in RESPONSIBILITIES:
            raise ValueError(f"responsibility must be one of {RESPONSIBILITIES}, not {self.responsibility!r}")
        if not _OWNER_ID.fullmatch(_require_text(self.observed_by, "observed_by")):
            raise ValueError(f"observed_by must be a canonical owner identifier, not {self.observed_by!r}")


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
    ``evidence``, and ``none`` when there is none. ``advisory`` is always true:
    the diagnostic discloses, it never decides validity or blocks (§30.28).
    """

    status: str
    evidence: tuple[ShadowEvidence, ...] = ()
    uninspected: tuple[Uninspected, ...] = ()

    @property
    def advisory(self) -> bool:
        return True

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
            "confirmed_count": len(self.confirmed),
            "suspected_count": len(self.suspected),
            "evidence": [item.to_json() for item in self.evidence],
            "uninspected": [item.to_json() for item in self.uninspected],
        }

    def render_lines(self) -> list[str]:
        """Human lines for an advisory display; the first line always states the status."""
        lines = [f"shadow authority (advisory): {self.status}"]
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


def _evidence(source: str, path: str, rule: str, responsibility: str, **detail: Any) -> ShadowEvidence:
    return ShadowEvidence(
        RULE_LEVELS[rule], source, path, rule, responsibility, RESPONSIBILITY_OWNERS[responsibility], **detail
    )


def _sort_key(item: ShadowEvidence) -> tuple:
    return (-LEVELS.index(item.level), item.source, item.path, item.rule, item.line or 0, item.observed_by or "")


# --------------------------------------------------------------------------- one inspection


class _Inspection:
    """One pass over the v1 sources. With ``read`` false it lists and opens directories, and opens no file."""

    def __init__(self, root: Path, *, read: bool) -> None:
        self.root = root
        self.read = read
        self.evidence: list[ShadowEvidence] = []
        self.uninspected: list[Uninspected] = []
        #: Every file read (or, with ``read`` false, that would be read), Project-relative, in read order.
        self.reads: list[str] = []
        self.skill_files = 0
        self.listed = 0

    def skip(self, path: str, reason: str) -> None:
        self.uninspected.append(Uninspected(path, reason))

    def isolated(self, source: str, inspect) -> None:
        try:
            inspect()
        except Exception:  # advisory: a detector failure is reported, never raised into validation or status
            self.skip(source, UNINSPECTED_FAILED)


def _project_root(project_root: str | os.PathLike[str] | ProjectStore) -> Path:
    """The Project root as :class:`~workline.store.ProjectStore` identifies it; nothing is read or written."""
    return project_root.root if isinstance(project_root, ProjectStore) else ProjectStore(Path(project_root)).root


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


def _indirection_kind(path: Path) -> str:
    """Name an indirection a handle-bound listing already found; ``lstat`` describes it without following it."""
    try:
        info = os.lstat(path)
    except (OSError, ValueError):
        return INDIRECTION_UNKNOWN
    tag = getattr(info, "st_reparse_tag", 0)
    if tag == stat.IO_REPARSE_TAG_MOUNT_POINT:
        return INDIRECTION_JUNCTION
    if stat.S_ISLNK(info.st_mode) or tag == stat.IO_REPARSE_TAG_SYMLINK:
        return INDIRECTION_SYMLINK
    if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        return INDIRECTION_REPARSE_POINT
    return INDIRECTION_UNKNOWN


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
    except (ValidationError, OSError):
        run.skip(".", UNINSPECTED_UNREADABLE)
        return
    walked: list[str] = []
    try:
        for index, wanted in enumerate(parts):
            here = directories[-1]
            entry = _find(here.entries(), wanted)
            if entry is None:
                return  # absent: no evidence
            walked.append(entry.name)
            relative = "/".join(walked)
            if entry.is_indirection:
                run.evidence.append(_evidence(
                    SOURCE_BOOTSTRAP, BOOTSTRAP_REL_PATH, RULE_BOOTSTRAP_INDIRECTION, ROUTING_BOOTSTRAP,
                    component=relative, indirection=_indirection_kind(run.root.joinpath(*walked)),
                ))
                return
            if index < len(parts) - 1:
                if not entry.is_dir:
                    return  # a non-directory ancestor: the bootstrap path cannot exist, so it is absent
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
                return
            if _too_large(run.root.joinpath(*walked)):
                # Far larger than the canonical text can be: it differs, and it is not read.
                run.evidence.append(_evidence(
                    SOURCE_BOOTSTRAP, BOOTSTRAP_REL_PATH, RULE_BOOTSTRAP_DIFFERS, ROUTING_BOOTSTRAP
                ))
                return
            run.reads.append(BOOTSTRAP_REL_PATH)
            if not run.read:
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
            return
    except (ValidationError, OSError):
        run.skip("/".join(walked) or ".", UNINSPECTED_UNREADABLE)
    finally:
        for directory in reversed(directories):
            directory.close()


# --------------------------------------------------------------------------- source 2: local Skill static text


def _words(*words: str) -> str:
    """English words bounded by non-letters (``\\b`` would not bound a word written next to Japanese text)."""
    return r"(?<![A-Za-z])(?:" + "|".join(words) + r")(?![A-Za-z])"


#: The sentence names Workline (``Workline`` / ``.workline``): without it nothing is a Workline claim.
_ANCHOR = re.compile(r"workline", re.IGNORECASE)
#: The sentence denies or forbids rather than claims.
_NEGATION = re.compile(
    _words("not", "never", "no", "nor", "none", "without", "cannot", "can't", "don't", "doesn't", "won't",
           "mustn't", "shouldn't", "isn't", "aren't")
    + r"|ない|ません|禁止|不可|せず",
    re.IGNORECASE,
)
#: The sentence defers to the canonical router / owner: it calls canonical Workline, it does not replace it.
_DEFERENCE = re.compile(_words("canonical") + r"|正式|project-router|run-workline|skills/[a-z]", re.IGNORECASE)
#: A Workline lifecycle subject.
_SUBJECT = re.compile(
    _words("work", "works", "phase", "phases", "roadmap", "roadmaps", "task", "tasks")
    + r"|作業|タスク|フェーズ|ロードマップ",
    re.IGNORECASE,
)
#: Current / next progression.
_PROGRESSION = re.compile(_words("current", "next", "upcoming") + r"|次|現在", re.IGNORECASE)
#: Lifecycle / completion state.
_LIFECYCLE = re.compile(
    _words("complete", "completed", "completion", "done", "finished", "closed", "achieved", "achievement",
           "lifecycle", "status", "state")
    + r"|完了|達成|状態|ステータス|ライフサイクル",
    re.IGNORECASE,
)
#: Deciding / keeping state.
_KEEPS = re.compile(
    _words("mark", "marks", "marked", "set", "sets", "record", "records", "recorded", "track", "tracks", "tracked",
           "persist", "persists", "persisted", "store", "stores", "stored", "keep", "keeps", "maintain", "maintains",
           "decide", "decides", "decided", "determine", "determines", "choose", "chooses", "select", "selects",
           "pick", "picks", "declare", "declares", "update", "updates", "own", "owns", "manage", "manages")
    + r"|記録|管理|保存|保持|更新|判定|決定|決め|選|設定|扱い|にする|とする",
    re.IGNORECASE,
)
#: Claiming authority over, or replacing, Workline state.
_OVERRIDES = re.compile(
    r"source of truth|takes? precedence|instead of|in place of|"
    + _words("authoritative", "override", "overrides", "overriding", "supersede", "supersedes")
    + r"|正本|優先|上書き|代わりに|置き換",
    re.IGNORECASE,
)
_SENTENCE_BREAK = re.compile(r"(?<=[。！？；;])|(?<=[.!?])\s+")


def _sentence_claim(sentence: str) -> tuple[str, str] | None:
    """``(rule, responsibility)`` when one sentence claims Workline lifecycle / progression authority; else ``None``."""
    if _NEGATION.search(sentence) or _DEFERENCE.search(sentence):
        return None
    subject = bool(_SUBJECT.search(sentence))
    progression = subject and bool(_PROGRESSION.search(sentence))
    overrides = bool(_OVERRIDES.search(sentence))
    # In an established Workline Project, claiming authority over the current / next Work, Phase or task
    # names Workline progression itself (§15.2) - with or without the word.
    if not (_ANCHOR.search(sentence) or (overrides and progression)):
        return None
    if overrides:
        if progression:
            return RULE_SKILL_AUTHORITY_OVERRIDE, PROGRESSION
        return RULE_SKILL_AUTHORITY_OVERRIDE, LIFECYCLE_STATE if _LIFECYCLE.search(sentence) else PLANNING_STATE
    if progression and _KEEPS.search(sentence):
        return RULE_SKILL_PARALLEL_PROGRESSION, PROGRESSION
    if subject and _LIFECYCLE.search(sentence) and _KEEPS.search(sentence):
        return RULE_SKILL_PARALLEL_LIFECYCLE, LIFECYCLE_STATE
    return None


def skill_text_claims(text: str) -> tuple[tuple[str, str, int], ...]:
    """Every ``(rule, responsibility, line)`` claim in one Skill's text: the first line per rule, in line order.

    A deterministic heuristic for an advisory *suspicion* only (the trigger is
    documented in the module docstring): whatever it finds is ``suspected`` at
    most. A sentence counts only when it names Workline (or claims authority
    over the current / next Work, Phase or task), claims to keep, decide or
    override Workline lifecycle / progression state, and neither denies it nor
    defers to the canonical router / owner.
    """
    found: dict[str, tuple[str, str, int]] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        for sentence in _SENTENCE_BREAK.split(line):
            claim = _sentence_claim(sentence)
            if claim is not None and claim[0] not in found:
                found[claim[0]] = (claim[0], claim[1], number)
    return tuple(sorted(found.values(), key=lambda item: (item[2], item[0])))


def _inspect_skills(run: _Inspection) -> None:
    try:
        chain = fsafe.walk(run.root, SKILLS_REL_DIR.split("/"))
    except (ValidationError, OSError):
        return  # an indirection or non-directory on the bootstrap path: the bootstrap rules report it
    if chain is None:
        return
    with chain:
        _skill_directory(run, chain.last, SKILLS_REL_DIR, 0)


def _skill_directory(run: _Inspection, here: fsafe.SafeDirectory, relative: str, depth: int) -> None:
    try:
        entries = here.entries()
    except (ValidationError, OSError):
        run.skip(relative, UNINSPECTED_UNREADABLE)
        return
    run.listed += len(entries)
    if run.listed > MAX_LISTED_ENTRIES:
        run.skip(relative, UNINSPECTED_LIMIT)
        return
    for entry in entries:  # fsafe lists by name: the order is the names', never the filesystem's
        path = f"{relative}/{entry.name}"
        if entry.is_indirection:
            if not _on_bootstrap_path(path):
                run.skip(path, UNINSPECTED_INDIRECTION)
            continue
        if entry.is_dir:
            if depth + 1 > MAX_SKILL_DEPTH:
                run.skip(path, UNINSPECTED_LIMIT)
                continue
            try:
                child = here.child(entry.name)
            except (ValidationError, OSError):
                run.skip(path, UNINSPECTED_UNREADABLE)
                continue
            if child is None:
                run.skip(path, UNINSPECTED_CHANGED)
                continue
            with child:
                _skill_directory(run, child, path, depth + 1)
            continue
        if entry.is_file and _same_name(entry.name, SKILL_FILENAME) and not _on_bootstrap_path(path):
            _skill_file(run, here, entry.name, path)


def _skill_file(run: _Inspection, here: fsafe.SafeDirectory, name: str, path: str) -> None:
    run.skill_files += 1
    if run.skill_files > MAX_SKILL_FILES:
        run.skip(path, UNINSPECTED_LIMIT)
        return
    if _too_large(run.root.joinpath(*path.split("/"))):
        run.skip(path, UNINSPECTED_TOO_LARGE)
        return
    run.reads.append(path)
    if not run.read:
        return
    try:
        bound = here.read_file_bound(name)
    except (ValidationError, OSError):
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
    for rule, responsibility, line in skill_text_claims(text):
        run.evidence.append(_evidence(SOURCE_LOCAL_SKILL, path, rule, responsibility, line=line, digest=digest))


# --------------------------------------------------------------------------- source 3: observations


def _inspect_observed(run: _Inspection, observed: Iterable[object]) -> None:
    for index, item in enumerate(observed):
        if type(item) is not ObservedEvidence:
            run.skip(f"observed[{index}]", UNINSPECTED_OBSERVATION_REJECTED)
            continue
        run.evidence.append(_evidence(
            SOURCE_OBSERVED, item.artifact, _OBSERVED_RULES[item.kind], item.responsibility,
            observed_by=item.observed_by,
        ))


# --------------------------------------------------------------------------- public entry points


def detect_shadow_authority(
    project_root: str | os.PathLike[str] | ProjectStore, observed: Iterable[ObservedEvidence] = ()
) -> ShadowDiagnostic:
    """Classify one Project's shadow-authority evidence: read-only, advisory, never raising.

    ``project_root`` is the Project root (a path, or a :class:`ProjectStore`).
    Reads exactly :func:`source_paths` - the bootstrap path and
    ``.claude/skills/**/SKILL.md`` - without following any link, and takes
    ``observed`` (canonical router / owner observations) as given. Each source
    is isolated: one that cannot be read is reported in ``uninspected`` and the
    others still run. Writes nothing, takes no lock, runs no Git, uses no network.
    """
    try:
        root = _project_root(project_root)
    except Exception:
        return ShadowDiagnostic(NONE, (), (Uninspected(".", UNINSPECTED_UNREADABLE),))
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
    )


def source_paths(project_root: str | os.PathLike[str] | ProjectStore) -> tuple[str, ...]:
    """The Project-relative files :func:`detect_shadow_authority` would read, in read order; none is opened here.

    The same no-follow walk, stopped before any file is opened: the bootstrap
    path when it is a plain file reached without indirection, then every plain
    ``SKILL.md`` under ``.claude/skills`` the Skill rule would read. Nothing
    else is ever read. Never raises: what cannot be listed is simply not here.
    """
    try:
        root = _project_root(project_root)
    except Exception:
        return ()
    run = _Inspection(root, read=False)
    run.isolated(BOOTSTRAP_REL_PATH, lambda: _inspect_bootstrap(run))
    run.isolated(SKILLS_REL_DIR, lambda: _inspect_skills(run))
    return tuple(run.reads)


__all__ = [
    "CONFIRMED",
    "LEVELS",
    "NONE",
    "OBSERVED_DELEGATION",
    "OBSERVED_KINDS",
    "OBSERVED_ROUTE",
    "OBSERVED_WRITE",
    "RESPONSIBILITIES",
    "RESPONSIBILITY_OWNERS",
    "RULES",
    "RULE_BOOTSTRAP_DIFFERS",
    "RULE_BOOTSTRAP_INDIRECTION",
    "RULE_BOOTSTRAP_NOT_REGULAR_FILE",
    "RULE_LEVELS",
    "RULE_OBSERVED_DELEGATION",
    "RULE_OBSERVED_ROUTE",
    "RULE_OBSERVED_WRITE",
    "RULE_SKILL_AUTHORITY_OVERRIDE",
    "RULE_SKILL_PARALLEL_LIFECYCLE",
    "RULE_SKILL_PARALLEL_PROGRESSION",
    "SUSPECTED",
    "ObservedEvidence",
    "ShadowDiagnostic",
    "ShadowEvidence",
    "Uninspected",
    "detect_shadow_authority",
    "skill_text_claims",
    "source_paths",
]
