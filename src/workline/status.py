"""Read-only Project status: one versioned model of an established Workline Project, rendered two ways.

``run-workline.py status <project-root> [--json]`` (``rules/git``: Read-only
status). It reads one Project - from inside it or from anywhere else - and
reports, without deriving anything new, what its canonical records, its
recovery records, its Review records and its local Git repository say:

* who decides: the configured Workline root, whether this process runs that
  root's implementation, whether its registry validates, and the identities and
  digests of the authority it routes (never their prose);
* where it stands: Roadmap / Phase / Work state, and the current and next
  selections exactly as Roadmap and START compute them
  (:class:`~workline.state.ProjectView`, :mod:`workline.selection`) - or the
  ambiguity or blocker that keeps them from naming one;
* what is unfinished: every recovery record, each judged on its own, with how
  its owner's recovery would treat it - ``disposed_by_human`` where an explicit
  Human recovery disposition sets it aside, which stays visible as historical
  evidence after its runtime record is gone (RB10 N4);
* what the Review records, ``validate-project`` and local Git say.

It is a diagnostic. It never writes - no canonical file, no runtime record, no
lock or holder, no cache, no Git index, ref or config - it opens no mutation,
contacts no remote, launches no reviewer, and repairs, activates or cleans up
nothing. It progresses no Roadmap, Phase or Work, and what it reports is not
lifecycle truth apart from the canonical records it read.

A read made without the Project execution lock is not atomic, and it does not
pretend to be. Four witnesses - HEAD, the branch, the recovery-record set and a
fingerprint of the canonical ``.workline`` tree - are read before (B0) and after
(B1) the model is built. When they differ (once more after one immediate
rebuild), the model says ``changing`` and claims no current or next selection.

The human rendering and the JSON rendering are two presentations of one
:class:`StatusModel`; neither reads anything.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable, Mapping

from . import gitcmd, gitops, implementation, oplock, pushurl
from .errors import StopError
from .mutation import (
    RECORD_FILENAME_INVALID,
    RECORD_OWNERSHIP_UNCONFIRMED,
    RECORD_UNREADABLE,
    RECORD_VALID,
    REPLAY_CLEAR,
    REPLAY_RECONCILE,
    RecordInspection,
    inspect_records,
    read_only_git,
    replay_probe,
    same_request,
)
from .recovery_disposition import (
    KIND_MUTATION,
    STATE_EFFECTIVE,
    STATE_INVALID,
    STATE_NONE,
    TargetState,
    disposition_ids,
    mutation_target_state,
    namespace_present,
    target_kind,
)
from .registry import authority_inventory
from .selection import MULTIPLE_TARGETS, work_continuation
from .state import ACTIVE, AMBIGUOUS_CANDIDATES, HELD, IN_PROGRESS, UNSTARTED, ProjectView
from .store import PROJECT_YAML_REL, RUNTIME_DIR, WORKLINE_DIR, ProjectStore
from .validate import validate_project, validate_structure

SCHEMA = "workline-status"
VERSION = 1

STABLE_READ = "stable_read"
CHANGING = "changing"
PROJECT_CHANGED = "project_changed_during_status"

NOT_AVAILABLE_BY_CONTRACT = "not_available_by_contract"
REMOTE_NOT_CHECKED = "not_checked"

#: How a recovery record's owner would treat it (``none`` is the whole section with no record).
PENDING_NONE = "none"
PENDING_RESUMABLE = "pending_resumable"
PENDING_RECONCILE = "pending_reconcile_required"
DISPOSED_BY_HUMAN = "disposed_by_human"  # RB10 N4: a valid committed Human recovery disposition sets it aside
UNKNOWN_OR_INVALID = "unknown_or_invalid"
RESUME_CLASSIFICATIONS = (PENDING_RESUMABLE, PENDING_RECONCILE, DISPOSED_BY_HUMAN, UNKNOWN_OR_INVALID)

#: Why a selection the model would otherwise name is withheld, strongest first.
PENDING_UNRESOLVED = "pending_mutation_unresolved"
STRUCTURE_INVALID = "structure_invalid"

#: The order the human rendering presents the model in.
HUMAN_SECTIONS = (
    "Project",
    "Authority",
    "Current",
    "Next",
    "Blocked/Waiting",
    "Pending mutation",
    "Review",
    "Validation",
    "Git / push destination",
    "Achievement",
    "Policy",
)

# Invocation keys that identify an operation without carrying what it decided (no names, texts, URLs or requests).
_SAFE_INVOCATION_KEYS = (
    "operation", "work_id", "mode", "roadmap_id", "phase_id", "entity", "remote", "review_run_id", "generation",
    "planning_mutation_id", "review_kind", "review_contract", "publication_contract", "operation_contract",
    "recovery_of_review_run_id", "target_id",
)
_GENERATION_OPERATION = "review-generation"
# The canonical paths whose writes change what lifecycle derivation reads.
_PROGRESSION_PREFIXES = tuple(
    f"{WORKLINE_DIR}/{name}/" for name in ("events", "relations", "roadmaps", "phases", "works", "derivations")
)


# --------------------------------------------------------------------------- the model


@dataclass(frozen=True)
class StatusModel:
    """One read of one Project: the JSON-ready model both renderings present (``schema`` / ``version`` inside)."""

    data: Mapping[str, Any]

    def get(self, key: str) -> Any:
        return self.data[key]


def _reason(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _failure(exc: BaseException) -> dict[str, str]:
    return _reason(getattr(exc, "code", None) or type(exc).__name__, str(exc))


def _unavailable(exc: BaseException) -> dict[str, Any]:
    return {"status": "unavailable", "reason": _failure(exc)}


def _isolated(provider: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """One section, read on its own: a reader that fails reports why, and hides no other section."""
    try:
        return provider()
    except Exception as exc:  # every reader failure is a diagnostic, never a guess
        return _unavailable(exc)


# --------------------------------------------------------------------------- B0 / B1 witnesses


@dataclass(frozen=True)
class Witnesses:
    head: str | None
    branch: str
    pending: tuple[tuple[str, str | None, str], ...]
    fingerprint: str


def _git(root: Path, *args: str) -> gitcmd.GitResult | None:
    try:
        return gitcmd.run_git(root, *args, check=False)
    except StopError:
        return None


def _head(root: Path) -> str | None:
    found = _git(root, "rev-parse", "--verify", "--quiet", "HEAD")
    if found is None or not found.ok:
        return None
    return found.stdout.strip() or None


def _branch_witness(root: Path) -> str:
    found = _git(root, "symbolic-ref", "--quiet", "HEAD")
    if found is None:
        return "unknown"
    if found.returncode == 0:
        return found.stdout.strip()
    if found.returncode == 1:
        return "detached"
    return f"unknown:{found.returncode}"


def _pending_witness(store: ProjectStore) -> tuple[tuple[str, str | None, str], ...]:
    try:
        found = inspect_records(store)
    except OSError as exc:
        return (("", None, f"unlistable:{exc.errno}"),)
    return tuple(sorted((item.filename, item.sha256, item.parse_state) for item in found))


def _is_indirection(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _entry(path: Path, relative: str, info: os.stat_result) -> list[str]:
    if _is_indirection(info):
        try:
            target = os.readlink(path)
        except (OSError, ValueError):
            target = "?"
        return [relative, "indirection", f"{getattr(info, 'st_reparse_tag', 0)}:{target}"]
    if stat.S_ISREG(info.st_mode):
        try:
            with open(path, "rb") as handle:
                opened = os.fstat(handle.fileno())
                data = handle.read()
        except OSError as exc:
            return [relative, "other", f"unreadable:{exc.errno}"]
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            return [relative, "other", "replaced_during_read"]
        return [relative, "regular_file", hashlib.sha256(data).hexdigest()]
    return [relative, "other", f"mode:{stat.S_IFMT(info.st_mode)}"]


def canonical_inventory(root: Path) -> list[list[str]]:
    """The canonical ``.workline`` tree, entry by entry, without following anything; ``.workline/runtime`` excluded.

    Each entry binds its Project-relative path and its kind: a regular file by
    the SHA-256 of its exact bytes, a directory by being one, an indirection
    (symlink, junction, other reparse point) and anything else by a stable
    structural marker. No indirection is followed and no directory is entered
    through one.
    """
    entries: list[list[str]] = []
    runtime = os.path.normcase(RUNTIME_DIR)

    def visit(path: Path, relative: str) -> None:
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            entries.append([relative, "absent", ""])
            return
        except OSError as exc:
            entries.append([relative, "other", f"unreadable:{exc.errno}"])
            return
        if stat.S_ISDIR(info.st_mode) and not _is_indirection(info):
            entries.append([relative, "directory", ""])
            try:
                names = sorted(os.listdir(path))
            except OSError as exc:
                entries.append([relative + "/", "other", f"unlistable:{exc.errno}"])
                return
            for name in names:
                child = f"{relative}/{name}"
                if os.path.normcase(child) == runtime:
                    continue
                visit(path / name, child)
            return
        entries.append(_entry(path, relative, info))

    visit(root / WORKLINE_DIR, WORKLINE_DIR)
    return sorted(entries)


def canonical_fingerprint(root: Path) -> str:
    """SHA-256 over :func:`canonical_inventory`: the canonical status surface, as one witness."""
    text = json.dumps(canonical_inventory(root), ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def read_witnesses(root: Path) -> Witnesses:
    """B0 / B1: the four identities a stable read must find unchanged."""
    return Witnesses(_head(root), _branch_witness(root), _pending_witness(ProjectStore(root)), canonical_fingerprint(root))


# --------------------------------------------------------------------------- project


@dataclass
class _Context:
    """What one section reads that another needs, passed along rather than read twice."""

    root: Path
    store: ProjectStore
    established: bool = False
    configured_root: Path | None = None
    inspections: tuple[RecordInspection, ...] | None = None
    blocking_mutations: tuple[str, ...] = ()


def _root_kind(root: Path) -> str:
    try:
        info = os.stat(root)
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unreadable"
    return "directory" if stat.S_ISDIR(info.st_mode) else "not_directory"


def _project(context: _Context) -> dict[str, Any]:
    store = context.store
    kind = _root_kind(context.root)
    section: dict[str, Any] = {
        "root": str(context.root),
        "root_kind": kind,
        "established": False,
        "project_yaml": {"status": "absent", "reason": None},
        "configured_workline_root": {"status": "unavailable", "path": None, "exists": None, "reason": None},
    }
    if kind != "directory":
        section["configured_workline_root"]["reason"] = _reason("project_root_unavailable", f"{context.root} is {kind}")
        return section
    if not store.project_yaml.is_file():
        if store.project_yaml.exists():
            section["project_yaml"] = {
                "status": "unreadable",
                "reason": _reason("project_yaml_invalid", f"{PROJECT_YAML_REL} is not a regular file"),
            }
        section["configured_workline_root"]["reason"] = _reason(
            "not_an_established_project", f"{PROJECT_YAML_REL} is missing"
        )
        return section
    context.established = True
    section["established"] = True
    try:
        store.load_project_yaml()
        section["project_yaml"] = {"status": "readable", "reason": None}
    except StopError as exc:
        section["project_yaml"] = {"status": "unreadable", "reason": _failure(exc)}
    try:
        configured = store.workline_root()
    except StopError as exc:
        section["configured_workline_root"]["reason"] = _failure(exc)
        return section
    context.configured_root = configured
    section["configured_workline_root"] = {
        "status": "readable",
        "path": str(configured),
        "exists": configured.is_dir(),
        "reason": None,
    }
    return section


# --------------------------------------------------------------------------- authority

_IDENTITY_STATUS = {
    implementation.IMPLEMENTATION_MISMATCH: "mismatch",
    implementation.IMPLEMENTATION_UNVERIFIED: "unverified",
    implementation.PYTHON_UNSUPPORTED: "python_unsupported",
}


def _authority(context: _Context) -> dict[str, Any]:
    running = implementation.running_workline_root()
    section: dict[str, Any] = {
        "running_workline_root": {
            "status": "proven" if running is not None else "unverified",
            "path": None if running is None else str(running),
            "reason": None if running is not None else _reason(
                implementation.IMPLEMENTATION_UNVERIFIED,
                "the loaded workline implementation cannot be proven to be one Workline root's source package",
            ),
        },
        "implementation": {"status": "unavailable", "reason": None},
        "registry": {"status": "unavailable", "root": None, "sha256": None, "problems": [], "reason": None},
        "inventory": {"status": "unavailable", "entries": [], "reason": None},
        "review_activation_contract": None,
    }
    configured = context.configured_root
    if configured is None:
        missing = _reason("configured_workline_root_unavailable", "the Project's configured Workline root cannot be read")
        for name in ("implementation", "registry", "inventory"):
            section[name]["reason"] = missing
        return section
    problem = implementation.configured_implementation_problem(configured)
    section["implementation"] = (
        {"status": "match", "reason": None}
        if problem is None
        else {"status": _IDENTITY_STATUS.get(problem.code, "unverified"), "reason": _reason(problem.code, problem.message)}
    )
    if not configured.is_dir():
        missing = _reason("workline_root_missing", f"Workline root is not a directory: {configured}")
        section["registry"]["reason"] = missing
        section["inventory"]["reason"] = missing
        return section
    inventory = authority_inventory(configured)
    problems = sorted(([p.code, p.message] for p in inventory.validation.problems))
    section["registry"] = {
        "status": "valid" if inventory.validation.ok else "invalid",
        "root": str(configured.resolve()),
        "sha256": inventory.registry_sha256,
        "problems": [{"code": code, "message": message} for code, message in problems],
        "reason": None,
    }
    if inventory.validation.ok:
        section["inventory"] = {
            "status": "available",
            "entries": [
                {"id": e.authority_id, "target": e.target, "context": e.context, "sha256": e.sha256}
                for e in inventory.entries
            ],
            "reason": None,
        }
    else:
        section["inventory"]["reason"] = _reason(
            "registry_invalid", "the registry does not validate, so no routing inventory is reported"
        )
    return section


# --------------------------------------------------------------------------- git


def _dirty(root: Path) -> dict[str, Any]:
    found = _git(root, "status", "--porcelain=v1", "--untracked-files=all", "-z")
    if found is None or not found.ok:
        detail = "" if found is None else (found.stderr.strip() or found.stdout.strip())
        return {"status": "unavailable", "entries": [], "reason": _reason("git_status_unavailable", detail)}
    entries: list[dict[str, Any]] = []
    items = found.stdout.split("\0")
    index = 0
    while index < len(items):
        item = items[index]
        index += 1
        if not item:
            continue
        code, path = item[:2], item[3:].replace("\\", "/")
        origin = None
        if code[0] in "RC" and index < len(items):
            origin = items[index].replace("\\", "/")
            index += 1
        entries.append({"path": path, "index": code[0], "worktree": code[1], "orig_path": origin})
    entries.sort(key=lambda entry: (entry["path"], entry["index"], entry["worktree"], entry["orig_path"] or ""))
    return {"status": "available", "entries": entries, "reason": None}


def _push_destination(context: _Context) -> dict[str, Any]:
    root, store = context.root, context.store
    section: dict[str, Any] = {
        "approved_destination": {"status": "unavailable", "remote": None, "allowed_urls": [], "reason": None},
        "remotes": [],
        "active_local_push_locator": {"status": "not_applicable", "remote": None, "locator": None, "locators": [], "reason": None},
        "local_locator_matches_pin": None,
        "problem": None,
        "remote_publication_state": REMOTE_NOT_CHECKED,
    }
    pin = None
    if not context.established:
        section["approved_destination"]["reason"] = _reason("not_an_established_project", f"{PROJECT_YAML_REL} is missing")
    else:
        try:
            pin = store.read_push_pin()
            if pin is None:
                section["approved_destination"] = {"status": "unpinned", "remote": None, "allowed_urls": [], "reason": None}
            else:
                section["approved_destination"] = {
                    "status": "pinned",
                    "remote": pin.remote,
                    "allowed_urls": sorted(pushurl.redact(url) for url in pin.allowed_urls),
                    "reason": None,
                }
        except StopError as exc:
            section["approved_destination"] = {"status": "invalid", "remote": None, "allowed_urls": [], "reason": _failure(exc)}
    try:
        remotes = sorted(gitcmd.remotes(root))
    except StopError as exc:
        section["active_local_push_locator"].update(status="unavailable", reason=_failure(exc))
        return section
    section["remotes"] = remotes
    if pin is None:
        if remotes and section["approved_destination"]["status"] == "unpinned":
            section["problem"] = "push_destination_unpinned"
        return section
    locator = section["active_local_push_locator"]
    locator["remote"] = pin.remote
    if pin.remote not in remotes:
        locator["status"] = "remote_missing"
        section["problem"] = "push_destination_remote_missing"
        section["local_locator_matches_pin"] = False
        return section
    try:
        found = gitcmd.push_locators(root, pin.remote)
    except StopError as exc:
        locator.update(status="unavailable", reason=_failure(exc))
        section["problem"] = "push_destination_unresolved"
        return section
    locator["locators"] = sorted(pushurl.redact(item) for item in found)
    if not found:
        locator["status"] = "none"
        section["problem"] = "push_destination_unresolved"
        section["local_locator_matches_pin"] = False
    elif len(found) > 1:
        locator["status"] = "multiple"
        section["problem"] = "push_destination_multiple"
        section["local_locator_matches_pin"] = False
    elif pushurl.is_secret_bearing(found[0]):
        locator.update(status="secret_redacted", locator=pushurl.redact(found[0]))
        section["problem"] = pushurl.SECRET_CODE
        section["local_locator_matches_pin"] = False
    else:
        locator.update(status="resolved", locator=found[0])
        matches = found[0] in pin.allowed_urls
        section["local_locator_matches_pin"] = matches
        if not matches:
            section["problem"] = "push_destination_mismatch"
    return section


def _git_section(context: _Context) -> dict[str, Any]:
    root = context.root
    section: dict[str, Any] = {
        "status": "unavailable",
        "reason": None,
        "toplevel": None,
        "toplevel_is_project_root": None,
        "branch_ref": None,
        "branch": None,
        "detached": None,
        "head": None,
        "dirty": {"status": "unavailable", "entries": [], "reason": None},
        "push_destination": None,
    }
    if _root_kind(root) != "directory":
        section["reason"] = _reason("project_root_unavailable", f"{root} is {_root_kind(root)}")
        return section
    top = _git(root, "rev-parse", "--show-toplevel")
    if top is None or not top.ok or not top.stdout.strip():
        detail = "" if top is None else (top.stderr.strip() or top.stdout.strip())
        section["reason"] = _reason("not_a_git_repository", detail or f"{root} is in no Git repository")
        return section
    toplevel = Path(top.stdout.strip()).resolve()
    section.update(status="available", toplevel=str(toplevel))
    try:
        section["toplevel_is_project_root"] = os.path.samefile(toplevel, root)
    except OSError:
        section["toplevel_is_project_root"] = None
    branch = _git(root, "symbolic-ref", "--quiet", "HEAD")
    if branch is not None and branch.returncode == 0 and branch.stdout.strip().startswith("refs/heads/"):
        ref = branch.stdout.strip()
        section.update(branch_ref=ref, branch=ref[len("refs/heads/"):], detached=False)
    elif branch is not None and branch.returncode == 1:
        section["detached"] = True
    section["head"] = _head(root)
    section["dirty"] = _isolated(lambda: _dirty(root))
    section["push_destination"] = _isolated(lambda: _push_destination(context))
    return section


# --------------------------------------------------------------------------- pending mutations

_PARSE_CODES = {
    RECORD_FILENAME_INVALID: "mutation_filename_invalid",
    RECORD_UNREADABLE: "mutation_record_unreadable",
    RECORD_OWNERSHIP_UNCONFIRMED: "mutation_record_ownership_unconfirmed",
}


def _safe_invocation(invocation: Any) -> dict[str, Any]:
    if not isinstance(invocation, dict):
        return {}
    safe: dict[str, Any] = {}
    for key in _SAFE_INVOCATION_KEYS:
        value = invocation.get(key)
        if isinstance(value, (bool, int)) or (value is None and key in invocation):
            safe[key] = value
        elif isinstance(value, str):
            safe[key] = pushurl.redact(value) if pushurl.is_secret_bearing(value) else value
    return safe


def _scope(record: dict[str, Any]) -> dict[str, list[str]]:
    scope = record.get("write_scope")
    if not isinstance(scope, dict):
        return {"entities": [], "files": []}
    found: dict[str, list[str]] = {}
    for name in ("entities", "files"):
        items = scope.get(name)
        found[name] = sorted(item for item in items if isinstance(item, str)) if isinstance(items, list) else []
    return found


def _affects_progression(record: dict[str, Any] | None) -> bool:
    """Whether an unfinished mutation may change what lifecycle derivation reads; an unreadable one may."""
    if record is None:
        return True
    scope = record.get("write_scope")
    if not isinstance(scope, dict) or not isinstance(scope.get("entities") or [], list) or not isinstance(scope.get("files") or [], list):
        return True
    if scope.get("entities"):
        return True
    return any(isinstance(path, str) and path.startswith(_PROGRESSION_PREFIXES) for path in scope.get("files") or [])


def _effects_summary(record: dict[str, Any]) -> dict[str, Any]:
    effects = record.get("effects")
    if not isinstance(effects, list):
        return {"stages": [], "effect_count": None, "applied_count": None, "kinds": []}
    stages: list[str] = []
    kinds: dict[str, int] = {}
    applied = 0
    for effect in effects:
        if not isinstance(effect, dict):
            continue
        stage = effect.get("stage")
        if isinstance(stage, str) and stage not in stages:
            stages.append(stage)  # recorded order is meaningful
        kind = str(effect.get("kind"))
        kinds[kind] = kinds.get(kind, 0) + 1
        applied += 1 if effect.get("applied") is True else 0
    return {
        "stages": stages,
        "effect_count": len(effects),
        "applied_count": applied,
        "kinds": [{"kind": kind, "count": count} for kind, count in sorted(kinds.items())],
    }


def _generation_binding(record: dict[str, Any]) -> dict[str, Any] | None:
    invocation = record.get("invocation")
    if not isinstance(invocation, dict) or invocation.get("operation") != _GENERATION_OPERATION:
        return None
    keys = ("review_run_id", "generation", "planning_mutation_id", "review_kind")
    return {key: invocation.get(key) for key in keys if isinstance(invocation.get(key), (str, int)) and not isinstance(invocation.get(key), bool)}


def _probe_push_destination_pin(
    store: ProjectStore, record: dict[str, Any], pending: list[dict[str, Any]]
) -> tuple[str, dict[str, str]]:
    """Push destination pin maintenance's recovery, asked read-only: what ``pin_push_destination`` checks, in its order.

    Each refusal it would make before resuming this record is reported with
    the code it would stop with; the replay itself is asked of the Mutation
    Controller (:func:`workline.mutation.replay_probe`). Only when every one of
    them passes is the record ``pending_resumable``.
    """
    from . import push_pin
    from .bootstrap import is_established_project
    from .destination import resolve_active_push_locator
    from .registry import validate_registry

    root = store.root
    invocation = record["invocation"]
    urls = invocation.get("urls")
    remote = invocation.get("remote")
    if (
        set(invocation) != {"operation", "project_root", "remote", "urls"}
        or invocation.get("operation") != push_pin.OWNER
        or invocation.get("project_root") != str(root)
        or not isinstance(remote, str)
        or not isinstance(urls, list)
        or not urls
        or not all(isinstance(url, str) and url and url == url.strip() for url in urls)
        or len(set(urls)) != len(urls)
        or any(pushurl.is_secret_bearing(url) for url in urls)
    ):
        # the invocation a run of pin maintenance on this root builds can never be this one
        return UNKNOWN_OR_INVALID, _reason(
            "invocation_not_reproducible",
            "pin maintenance of this Project root cannot be invoked again with exactly the recorded invocation",
        )
    if gitcmd.toplevel(root) != root or not is_established_project(store):
        return UNKNOWN_OR_INVALID, _reason("not_a_project", "pin maintenance refuses a Project that is not established")
    if not validate_registry(store.workline_root()).ok:
        return UNKNOWN_OR_INVALID, _reason("registry_invalid", "pin maintenance refuses an invalid registry")
    if remote not in gitcmd.remotes(root):
        return UNKNOWN_OR_INVALID, _reason("push_destination_remote_missing", f"this repository has no remote {remote}")
    try:
        resolved = resolve_active_push_locator(root, remote)
    except StopError as exc:
        return UNKNOWN_OR_INVALID, _failure(exc)
    if resolved not in urls:
        return UNKNOWN_OR_INVALID, _reason(
            "push_destination_mismatch", f"remote {remote} resolves to a destination the recorded request did not approve"
        )
    matches = [other for other in pending if other["owner"] == push_pin.OWNER and other["invocation"] == invocation]
    others = [other for other in pending if other not in matches]
    if others:
        names = ", ".join(sorted(str(other["mutation_id"]) for other in others))
        return UNKNOWN_OR_INVALID, _reason(
            "pending_operation", f"pin maintenance does not run while another operation is pending ({names})"
        )
    if len(matches) > 1:
        return PENDING_RECONCILE, _reason("duplicate_pending_invocation", f"{len(matches)} pending pin mutations match")
    if gitcmd.current_branch(root) is None:
        return UNKNOWN_OR_INVALID, _reason("detached_head", "repository is in detached HEAD state")
    notes = record.get("notes") if isinstance(record.get("notes"), dict) else {}
    noted = notes.get("preexisting_dirty")
    preexisting = noted if isinstance(noted, list) else gitops.preexisting_dirty_snapshot(root)
    if PROJECT_YAML_REL in preexisting:
        return UNKNOWN_OR_INVALID, _reason("dirty_overlap", gitops.OVERLAP_MESSAGE + PROJECT_YAML_REL)
    replay = replay_probe(store, record)
    if replay.outcome == REPLAY_CLEAR:
        return PENDING_RESUMABLE, _reason("resume_proven", "pin maintenance would resume this record and replay it")
    if replay.outcome == REPLAY_RECONCILE:
        return PENDING_RECONCILE, _reason(replay.code, replay.message)
    return UNKNOWN_OR_INVALID, _reason(replay.code, replay.message)


#: Owners whose recovery status can ask read-only, by the predicates that recovery itself evaluates.
_OWNER_PROBES: dict[str, Callable[[ProjectStore, dict[str, Any], list[dict[str, Any]]], tuple[str, dict[str, str]]]] = {
    "push-destination-pin": _probe_push_destination_pin,
}


def _classify(
    store: ProjectStore, record: dict[str, Any], pending: list[dict[str, Any]], unreadable: list[RecordInspection]
) -> tuple[str, dict[str, str]]:
    if unreadable:
        names = ", ".join(sorted(item.filename for item in unreadable))
        return PENDING_RECONCILE, _reason(
            "mutation_area_unreadable",
            f"every operation owner reads the runtime mutation area strictly before it resumes a record, and {names} "
            "stop that read: reconcile required",
        )
    duplicates = [
        other for other in pending
        if other is not record and other["owner"] == record["owner"] and same_request(other["invocation"], record["invocation"])
    ]
    if duplicates:
        return PENDING_RECONCILE, _reason(
            "duplicate_pending_invocation",
            f"{len(duplicates) + 1} pending mutations of {record['owner']} record the same invocation; none of them "
            "is resumed: reconcile required",
        )
    probe = _OWNER_PROBES.get(record["owner"])
    if probe is None:
        return UNKNOWN_OR_INVALID, _reason(
            "no_read_only_resume_probe",
            f"no read-only proof of how {record['owner']} would resume this record exists; status does not assume one",
        )
    return probe(store, record, pending)


# --------------------------------------------------------------------------- Human recovery dispositions (RB10 N4)


def _pending_dispositions(store: ProjectStore, pending: list[dict[str, Any]]) -> dict[str, TargetState]:
    """What the disposition of each pending record amounts to, for the records that have one (§35.16)."""
    if not pending or not namespace_present(store):
        return {}
    found: dict[str, TargetState] = {}
    for record in pending:
        state = mutation_target_state(store, str(record["mutation_id"]))
        if state.state != STATE_NONE:
            found[str(record["mutation_id"])] = state
    return found


def _classify_pending(
    store: ProjectStore,
    record: dict[str, Any],
    active: list[dict[str, Any]],
    unreadable: list[RecordInspection],
    dispositions: dict[str, TargetState],
) -> tuple[str, dict[str, str]]:
    """RB1's classification, with what a Human disposition changes in it and nothing else.

    A record a valid committed disposition sets aside is ``disposed_by_human``
    (never completed, abandoned or absent), and is not among the pending
    records another owner's probe meets - as :meth:`MutationController.list_pending`
    passes it over. A disposition that does not hold stops every owner's
    pending read, so every other record is ``pending_reconcile_required``.
    """
    own = dispositions.get(str(record["mutation_id"]))
    if own is not None and own.state == STATE_EFFECTIVE:
        return DISPOSED_BY_HUMAN, _reason(
            DISPOSED_BY_HUMAN,
            "an explicit Human recovery disposition sets this record aside: no owner resumes it automatically, and it "
            "stays as diagnostic evidence",
        )
    broken = sorted(mutation_id for mutation_id, state in dispositions.items() if state.state == STATE_INVALID)
    if broken and not unreadable:
        return PENDING_RECONCILE, _reason(
            "recovery_disposition_invalid",
            f"every operation owner reads the pending records through their recovery dispositions, and the "
            f"disposition of {', '.join(broken)} does not hold: reconcile required",
        )
    return _classify(store, record, active, unreadable)


def _disposition_detail(target_id: str, state: TargetState | None) -> dict[str, Any] | None:
    """The additive disposition detail (§35.16): identities, the bound digest, the public-safe reason, the runtime record."""
    if state is None:
        return None
    found = state.disposition
    return {
        "state": state.state,
        "target_id": target_id,
        "path": None if found is None else found.path,
        "target_state_digest": None if found is None else found.target_state_digest,
        "reason": None if found is None else found.reason,
        "runtime_record": state.runtime_record,
        "problem": None if state.problem is None else _reason("recovery_disposition_invalid", state.problem),
    }


def _mutation_dispositions(store: ProjectStore) -> list[dict[str, Any]]:
    """Every disposition of a mutation, the runtime record present or not: historical recovery evidence (§35.19)."""
    if not namespace_present(store):
        return []
    return [
        _disposition_detail(target_id, mutation_target_state(store, target_id))
        for target_id in disposition_ids(store)
        if target_kind(target_id) == KIND_MUTATION
    ]


def pending_classification(
    store: ProjectStore, mutation_id: str, *, excluding: tuple[str, ...] = ()
) -> tuple[str, dict[str, str]]:
    """The read-only classification status reports for one pending record; ``excluding`` leaves records out of the set.

    The one reader RB10 N4's eligibility asks (§35.5): a pending mutation is
    disposable only while this proves ``pending_reconcile_required``. A
    disposition resuming its own unfinished attempt leaves its own record out,
    as nothing it would compete with.
    """
    inspections = inspect_records(store)
    unreadable = [item for item in inspections if item.parse_state != RECORD_VALID]
    pending = [
        item.record for item in inspections
        if item.record is not None and item.record.get("status") == "pending" and item.mutation_id not in excluding
    ]
    dispositions = _pending_dispositions(store, pending)
    active = [record for record in pending if dispositions.get(str(record["mutation_id"]), TargetState(STATE_NONE)).state != STATE_EFFECTIVE]
    for record in pending:
        if record["mutation_id"] == mutation_id:
            return _classify_pending(store, record, active, unreadable, dispositions)
    return UNKNOWN_OR_INVALID, _reason("mutation_not_pending", f"{mutation_id} is not a pending recovery record")


def _pending(context: _Context) -> dict[str, Any]:
    store = context.store
    lock = _lock_hint(store)
    try:
        inspections = inspect_records(store)
    except OSError as exc:
        context.blocking_mutations = ("<unlistable>",)
        return {"status": "unavailable", "reason": _failure(exc), "records": [], "closed": [], "lock": lock}
    context.inspections = inspections
    unreadable = [item for item in inspections if item.parse_state != RECORD_VALID]
    pending = [item.record for item in inspections if item.record is not None and item.record.get("status") == "pending"]
    dispositions = _pending_dispositions(store, pending)
    active = [record for record in pending if dispositions.get(str(record["mutation_id"]), TargetState(STATE_NONE)).state != STATE_EFFECTIVE]
    records: list[dict[str, Any]] = []
    closed: list[dict[str, Any]] = []
    for item in sorted(inspections, key=lambda found: found.filename):
        if item.record is None:
            records.append({
                "filename": item.filename,
                "mutation_id": item.mutation_id,
                "parse_state": item.parse_state,
                "owner": None,
                "record_status": None,
                "operation": {},
                "write_scope": {"entities": [], "files": []},
                "stages": [],
                "effect_count": None,
                "applied_count": None,
                "kinds": [],
                "review_generation": None,
                "affects_progression": True,
                "classification": UNKNOWN_OR_INVALID,
                "reason": _reason(_PARSE_CODES.get(item.parse_state, "mutation_record_invalid"), item.reason or ""),
            })
            continue
        record = item.record
        if record.get("status") != "pending":
            closed.append({"mutation_id": item.mutation_id, "owner": record.get("owner"), "status": record.get("status")})
            continue
        try:
            classification, reason = _classify_pending(store, record, active, unreadable, dispositions)
        except Exception as exc:  # a probe that cannot finish proves nothing
            classification, reason = UNKNOWN_OR_INVALID, _failure(exc)
        records.append({
            "filename": item.filename,
            "mutation_id": item.mutation_id,
            "parse_state": item.parse_state,
            "owner": record.get("owner"),
            "record_status": record.get("status"),
            "operation": _safe_invocation(record.get("invocation")),
            "write_scope": _scope(record),
            **_effects_summary(record),
            "review_generation": _generation_binding(record),
            "affects_progression": _affects_progression(record),
            "classification": classification,
            "reason": reason,
        })
        # RB10 N4 §35.16: the additive detail, present only for a record that has a Human disposition
        detail = _disposition_detail(str(item.mutation_id), dispositions.get(str(item.mutation_id)))
        if detail is not None:
            records[-1]["disposition"] = detail
    # A record a Human disposition sets aside is resumed by no owner, so it holds no selection back.
    context.blocking_mutations = tuple(sorted(
        entry["mutation_id"] or entry["filename"] for entry in records
        if entry["affects_progression"] and entry["classification"] != DISPOSED_BY_HUMAN
    ))
    return {
        "status": "present" if records else PENDING_NONE,
        "reason": None,
        "records": records,
        "closed": sorted(closed, key=lambda entry: str(entry["mutation_id"])),
        "lock": lock,
        "dispositions": _isolated_list(lambda: _mutation_dispositions(store)),
    }


def _isolated_list(reader: Callable[[], list[dict[str, Any]]]) -> list[dict[str, Any]] | dict[str, Any]:
    try:
        return reader()
    except Exception as exc:  # a reader that cannot finish is reported, never taken for "none"
        return _unavailable(exc)


def _lock_hint(store: ProjectStore) -> dict[str, Any]:
    """The execution lock is never taken or tested here; ``holder.json`` is reported as the hint it is."""
    hint: dict[str, Any] = {"state": "not_checked", "holder_hint": "absent", "holder_operation": None, "holder_mutation_id": None}
    try:
        present = store.lock_holder.exists()
    except OSError:
        present = True
    if not present:
        return hint
    holder = oplock.read_holder(store)
    if holder is None:
        hint["holder_hint"] = "unreadable"
        return hint
    hint["holder_hint"] = "present"
    if isinstance(holder.get("operation"), str):
        hint["holder_operation"] = holder["operation"]
    if isinstance(holder.get("mutation_id"), str):
        hint["holder_mutation_id"] = holder["mutation_id"]
    return hint


# --------------------------------------------------------------------------- lifecycle


def _selected(identifier: str | None, reason: str | None, candidates: list[str] | None = None) -> dict[str, Any]:
    return {"id": identifier, "reason": reason, "candidates": sorted(candidates or [])}


def _next(identifier: str | None, reason: str | None, candidates: list[str], preferred: list[str], basis: str | None) -> dict[str, Any]:
    return {
        "id": identifier,
        "reason": reason,
        "basis": basis,
        "candidates": sorted(candidates),
        "preferred": sorted(preferred),
    }


def _entity(view: ProjectView, entity: Any, **extra: Any) -> dict[str, Any]:
    return {"id": entity.id, "display": entity.display, "name": entity.name, **extra}


def _dependency_blockers(view: ProjectView, entities: list[Any]) -> list[dict[str, Any]]:
    blockers = []
    for entity in entities:
        unsatisfied = view.unsatisfied_dependencies(entity.id)
        if unsatisfied:
            blockers.append({
                "code": "dependency_unsatisfied",
                "ids": [entity.id],
                "predecessors": sorted(
                    ({"id": relation.from_id, "state": label} for relation, label in unsatisfied),
                    key=lambda item: (item["id"], item["state"]),
                ),
            })
    return blockers


def _lifecycle(context: _Context) -> dict[str, Any]:
    if not context.established:
        return {"status": "unavailable", "reason": _reason("not_an_established_project", f"{PROJECT_YAML_REL} is missing")}
    view = ProjectView.load(context.store)
    structure = validate_structure(view)
    blockers: list[dict[str, Any]] = []

    roadmaps = [_entity(view, r, lifecycle=view.roadmap_lifecycle(r.id)) for r in view.roadmaps.values()]
    active = [r["id"] for r in roadmaps if r["lifecycle"] == ACTIVE]
    held_roadmaps = [r["id"] for r in roadmaps if r["lifecycle"] == HELD]
    if held_roadmaps:
        blockers.append({"code": "roadmap_held", "ids": held_roadmaps})
    phases = [
        _entity(view, p, roadmap_id=p.roadmap_id, lifecycle=view.phase_lifecycle(p.id), state=view.phase_state(p.id))
        for p in view.phases.values()
    ]
    current_roadmap = (
        _selected(active[0], None, active) if len(active) == 1
        else _selected(None, "multiple_active_roadmaps" if active else "no_active_roadmap", active)
    )
    if len(active) > 1:
        blockers.append({"code": "multiple_active_roadmaps", "ids": active})

    current_phase = _selected(None, "no_unique_roadmap")
    next_phase = _next(None, "no_unique_roadmap", [], [], None)
    current_work = _selected(None, "no_unique_phase")
    next_work = _next(None, "no_unique_phase", [], [], None)
    works: list[dict[str, Any]] = []
    roadmap_id = current_roadmap["id"]
    if roadmap_id is not None:
        members = view.roadmap_phases(roadmap_id)
        started = [p.id for p in members if view.phase_state(p.id) == IN_PROGRESS]
        held_phases = [p.id for p in members if view.phase_lifecycle(p.id) == HELD]
        if held_phases:
            blockers.append({"code": "phase_held", "ids": held_phases})
        if len(started) == 1:
            current_phase = _selected(started[0], None, started)
        else:
            current_phase = _selected(None, "multiple_started_phases" if started else "no_started_phase", started)
            if started:
                blockers.append({"code": "multiple_started_phases", "ids": started})
        # Roadmap's Phase selection (``roadmap.select_phase``): the startable Phases, narrowed by planned_next.
        candidates = view.startable_phases(roadmap_id)
        preferred = view.planned_next_preference(candidates) if candidates else []
        if len(preferred) == 1:
            next_phase = _next(preferred[0].id, None, [p.id for p in candidates], [p.id for p in preferred], "planned")
        elif preferred:
            next_phase = _next(None, AMBIGUOUS_CANDIDATES, [p.id for p in candidates], [p.id for p in preferred], None)
            blockers.append({"code": AMBIGUOUS_CANDIDATES, "kind": "phase", "ids": sorted(p.id for p in preferred)})
        else:
            reason = "all_active_phases_complete" if view.all_active_phases_complete(roadmap_id) else "no_startable_phase"
            next_phase = _next(None, reason, [], [], None)
            if reason == "no_startable_phase":
                blockers.extend(
                    _dependency_blockers(view, [p for p in members if view.phase_state(p.id) in (UNSTARTED, IN_PROGRESS)])
                )
        phase_id = current_phase["id"]
        if phase_id is None:
            reason = current_phase["reason"]
            current_work = _selected(None, reason)
            next_work = _next(None, reason, [], [], None)
        else:
            scope = view.effective_works(phase_id)
            continuation = work_continuation(view, phase_id, scope)
            in_flight = [w.id for w in continuation.in_flight]
            works = [
                _entity(
                    view, w, state=view.work_state(w.id).state, has_target=view.work_state(w.id).has_target,
                    work_kind=w.work_kind,
                )
                for w in view.phase_works(phase_id)
            ]
            held_works = [w["id"] for w in works if w["state"] == HELD]
            if held_works:
                blockers.append({"code": "work_held", "ids": held_works})
            confirming = [w.id for w in continuation.in_flight if w.work_kind == "human_confirmation"]
            if confirming:
                blockers.append({"code": "human_confirmation_in_flight", "ids": confirming})
            candidate_ids = [w.id for w in continuation.candidates]
            preferred_ids = [w.id for w in continuation.preferred]
            if len(in_flight) == 1:
                current_work = _selected(in_flight[0], None, in_flight)
                next_work = _next(in_flight[0], None, candidate_ids, preferred_ids, "in_flight")
            elif in_flight:
                current_work = _selected(None, MULTIPLE_TARGETS, in_flight)
                next_work = _next(None, MULTIPLE_TARGETS, candidate_ids, preferred_ids, None)
                blockers.append({"code": MULTIPLE_TARGETS, "ids": in_flight})
            else:
                current_work = _selected(None, "no_work_in_flight")
                selected = continuation.selected
                if selected is not None:
                    next_work = _next(selected.id, None, candidate_ids, preferred_ids, "planned")
                elif preferred_ids:
                    next_work = _next(None, AMBIGUOUS_CANDIDATES, candidate_ids, preferred_ids, None)
                    blockers.append({"code": AMBIGUOUS_CANDIDATES, "kind": "work", "ids": sorted(preferred_ids)})
                else:
                    next_work = _next(None, "no_startable_work", [], [], None)
                    blockers.extend(
                        _dependency_blockers(view, [w for w in scope if view.work_state(w.id).state == UNSTARTED])
                    )

    standalone = [w for w in view.works.values() if w.phase_id is None]
    standalone_section = {
        "in_flight": sorted(
            w.id for w in standalone if view.work_state(w.id).state == IN_PROGRESS and view.work_state(w.id).has_target
        ),
        "startable": sorted(w.id for w in view.startable_works(None, standalone)),
        "selected": None,
        "reason": "standalone_requires_explicit_entry",
    }
    section = {
        "status": "available",
        "reason": None,
        "structure": {
            "status": "failed" if structure else "pass",
            "problems": sorted(({"code": p.code, "message": p.message} for p in structure), key=lambda p: (p["code"], p["message"])),
        },
        "roadmaps": roadmaps,
        "phases": phases,
        "works": works,
        "current": {"roadmap": current_roadmap, "phase": current_phase, "work": current_work},
        "next": {"phase": next_phase, "work": next_work},
        "standalone": standalone_section,
        "blockers": blockers,
    }
    if structure:
        # Roadmap and START refuse to select over an invalid structure; status claims no selection either.
        _withhold(section, STRUCTURE_INVALID)
        section["blockers"].append({"code": STRUCTURE_INVALID, "ids": []})
    return section


def _withhold(lifecycle: dict[str, Any], reason: str) -> None:
    """Null every selected current / next value, keeping the observed candidate sets."""
    for group in ("current", "next"):
        for name, selected in lifecycle[group].items():
            selected["id"] = None
            selected["reason"] = reason
            if "basis" in selected:
                selected["basis"] = None


# --------------------------------------------------------------------------- validation / review


def _validation(context: _Context) -> dict[str, Any]:
    if not context.established:
        return {
            "status": "unavailable",
            "reason": _reason("not_an_established_project", f"{PROJECT_YAML_REL} is missing"),
            "problems": [],
            "implementation_verified": None,
        }
    problems = sorted(([p.code, p.message] for p in validate_project(context.store)))
    configured = context.configured_root
    identity = None if configured is None else implementation.configured_implementation_problem(configured)
    verified = configured is not None and identity is None
    if problems:
        status, reason = "failed", None
    elif verified:
        status, reason = "pass", None
    else:
        # A Project's canonical validation never PASSes under another implementation (``rules/git``).
        status = "unavailable"
        reason = _reason(identity.code, identity.message) if identity is not None else _reason(
            "configured_workline_root_unavailable", "the configured Workline root cannot be read"
        )
    return {
        "status": status,
        "reason": reason,
        "problems": [{"code": code, "message": message} for code, message in problems],
        "implementation_verified": verified,
    }


def _review(context: _Context) -> dict[str, Any]:
    if _root_kind(context.root) != "directory":
        return {"status": "unavailable", "reason": _reason("project_root_unavailable", f"{context.root} is not a directory")}
    from .review.status import review_status

    return {"status": "available", "reason": None, **review_status(context.store)}


# --------------------------------------------------------------------------- build


def _collect(root: Path) -> dict[str, Any]:
    """Every section from one pass over the Project; each reader isolated from the others."""
    context = _Context(root, ProjectStore(root))
    body: dict[str, Any] = {}
    body["project"] = _isolated(lambda: _project(context))
    body["authority"] = _isolated(lambda: _authority(context))
    body["git"] = _isolated(lambda: _git_section(context))
    body["pending"] = _isolated(lambda: _pending(context))
    body["lifecycle"] = _isolated(lambda: _lifecycle(context))
    body["validation"] = _isolated(lambda: _validation(context))
    body["review"] = _isolated(lambda: _review(context))
    body["_blocking_mutations"] = list(context.blocking_mutations)
    return body


_URL_USERINFO = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)([^/\s@]+)@")
_SCP_USERINFO = re.compile(r"(?<![\w/\\])([\w.+-]+:[^\s@/:]+)@([\w.-]+):")


def _scrub(value: Any) -> Any:
    """``value`` with every credential-bearing locator text masked, wherever a message carried one.

    The rule is ``pushurl``'s: a password component under any scheme, and over
    http(s) any user name at all, is never emitted - not in a field, not inside
    a reason a reader quoted.
    """
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if not isinstance(value, str):
        return value

    def url(match: re.Match[str]) -> str:
        scheme, userinfo = match.group(1), match.group(2)
        if ":" in userinfo or scheme[:-3].lower() in ("http", "https"):
            return scheme + "***@"
        return match.group(0)

    return _SCP_USERINFO.sub(lambda match: f"***@{match.group(2)}:", _URL_USERINFO.sub(url, value))


def _assemble(body: dict[str, Any], consistency: str) -> StatusModel:
    blocking = body.pop("_blocking_mutations")
    lifecycle = body["lifecycle"]
    if lifecycle.get("status") == "available":
        if consistency == CHANGING:
            _withhold(lifecycle, PROJECT_CHANGED)
        elif blocking:
            _withhold(lifecycle, PENDING_UNRESOLVED)
        if blocking:
            lifecycle["blockers"].append({"code": PENDING_UNRESOLVED, "ids": blocking})
        if consistency == CHANGING:
            lifecycle["blockers"].append({"code": PROJECT_CHANGED, "ids": []})
        lifecycle["blockers"].sort(key=lambda blocker: json.dumps(blocker, sort_keys=True))
    review = body["review"]
    activation = review.get("activation") if isinstance(review, dict) else None
    if isinstance(activation, dict) and activation.get("status") == "present" and isinstance(body["authority"], dict):
        body["authority"]["review_activation_contract"] = activation.get("operation_contract")
    data = {
        "schema": SCHEMA,
        "version": VERSION,
        "snapshot_consistency": consistency,
        "snapshot_reason": PROJECT_CHANGED if consistency == CHANGING else None,
        **body,
        "completion": {"status": NOT_AVAILABLE_BY_CONTRACT},
        "policy": {"status": NOT_AVAILABLE_BY_CONTRACT},
    }
    return StatusModel(_scrub(data))


def build_status(project_root: str | os.PathLike[str]) -> StatusModel:
    """Read the Project at ``project_root`` once, between two witness reads, and return its status model.

    Never changes the working directory and never resolves the caller's Project
    context: the target is the path given. One immediate rebuild is made when
    the witnesses differ; there is no other retry and no wait.
    """
    root = Path(os.path.abspath(project_root))
    try:
        root = root.resolve()
    except OSError:
        pass
    with read_only_git():
        for _attempt in range(2):
            before = read_witnesses(root)
            body = _collect(root)
            after = read_witnesses(root)
            if before == after:
                return _assemble(body, STABLE_READ)
        return _assemble(body, CHANGING)


# --------------------------------------------------------------------------- renderings


def render_json(model: StatusModel) -> str:
    """The versioned machine-readable rendering: deterministic bytes, ASCII only, one trailing newline."""
    return json.dumps(model.data, ensure_ascii=True, sort_keys=True, indent=2) + "\n"


def _label(index: dict[str, str], identifier: str | None) -> str:
    if identifier is None:
        return "none"
    shown = index.get(identifier)
    return f"{identifier} ({shown})" if shown else identifier


def _reason_text(reason: Any) -> str:
    if isinstance(reason, dict):
        return f"{reason.get('code')}: {reason.get('message')}"
    return str(reason)


def _section_status(section: Any) -> str | None:
    if isinstance(section, dict) and section.get("status") == "unavailable":
        return f"  unavailable - {_reason_text(section.get('reason'))}"
    return None


def _counted(found: Mapping[str, Any]) -> str:
    """An obligation status, with its count when it has one."""
    return str(found["status"]) + ("" if found.get("count") is None else f" {found['count']}")


def render_human(model: StatusModel) -> str:
    """The recovery-first human rendering of ``model``: presentation only - nothing is read or recomputed."""
    data = model.data
    out: list[str] = [
        f"Workline status ({data['schema']} v{data['version']}) - snapshot: {data['snapshot_consistency']}"
        + (f" ({data['snapshot_reason']})" if data.get("snapshot_reason") else "")
    ]

    def heading(name: str) -> None:
        out.append("")
        out.append(name)

    lifecycle = data.get("lifecycle") or {}
    index: dict[str, str] = {}
    for group in ("roadmaps", "phases", "works"):
        for entity in lifecycle.get(group) or []:
            index[entity["id"]] = " ".join(part for part in (entity.get("display"), entity.get("name")) if part)

    project = data["project"]
    heading("Project")
    out.append(_section_status(project) or f"  root: {project.get('root')} ({project.get('root_kind')})")
    if isinstance(project, dict) and "established" in project:
        out.append(f"  established: {'yes' if project['established'] else 'no'}")
        yaml = project["project_yaml"]
        out.append(f"  project.yaml: {yaml['status']}" + (f" - {_reason_text(yaml['reason'])}" if yaml.get("reason") else ""))
        configured = project["configured_workline_root"]
        out.append(
            f"  configured Workline root: {configured['path'] or 'unavailable'}"
            + (f" - {_reason_text(configured['reason'])}" if configured.get("reason") else "")
        )

    authority = data["authority"]
    heading("Authority")
    unavailable = _section_status(authority)
    if unavailable:
        out.append(unavailable)
    else:
        running = authority["running_workline_root"]
        out.append(f"  running Workline root: {running['path'] or running['status']}")
        identity = authority["implementation"]
        out.append(f"  implementation: {identity['status']}" + (f" - {_reason_text(identity['reason'])}" if identity.get("reason") else ""))
        registry = authority["registry"]
        out.append(
            f"  registry: {registry['status']}" + (f" (sha256 {registry['sha256']})" if registry.get("sha256") else "")
            + (f" - {_reason_text(registry['reason'])}" if registry.get("reason") else "")
        )
        for problem in registry.get("problems") or []:
            out.append(f"    - {problem['code']}: {problem['message']}")
        inventory = authority["inventory"]
        out.append(f"  authority inventory: {inventory['status']}" + (f" - {_reason_text(inventory['reason'])}" if inventory.get("reason") else ""))
        for entry in inventory.get("entries") or []:
            target = entry["target"] or "registry.md"
            out.append(f"    {entry['id']}  {target}" + (f"  sha256 {entry['sha256']}" if entry.get("sha256") else ""))
        if authority.get("review_activation_contract"):
            out.append(f"  review activation contract: {authority['review_activation_contract']}")

    def selected_line(name: str, selected: dict[str, Any]) -> str:
        text = f"  {name}: {_label(index, selected.get('id'))}"
        if selected.get("basis"):
            text += f" [{selected['basis']}]"
        if selected.get("reason"):
            text += f" - {selected['reason']}"
        candidates = selected.get("preferred") or selected.get("candidates") or []
        if selected.get("id") is None and candidates:
            text += " (candidates: " + ", ".join(_label(index, c) for c in candidates) + ")"
        return text

    heading("Current")
    lifecycle_unavailable = _section_status(lifecycle)
    if lifecycle_unavailable:
        out.append(lifecycle_unavailable)
    else:
        for name in ("roadmap", "phase", "work"):
            out.append(selected_line(name.capitalize(), lifecycle["current"][name]))
        standalone = lifecycle["standalone"]
        if standalone["in_flight"]:
            out.append("  standalone in flight: " + ", ".join(_label(index, w) for w in standalone["in_flight"]))

    heading("Next")
    if lifecycle_unavailable:
        out.append(lifecycle_unavailable)
    else:
        for name in ("phase", "work"):
            out.append(selected_line(name.capitalize(), lifecycle["next"][name]))
        standalone = lifecycle["standalone"]
        if standalone["startable"]:
            out.append(
                "  standalone startable (no implicit entry): " + ", ".join(_label(index, w) for w in standalone["startable"])
            )

    heading("Blocked/Waiting")
    blocked: list[str] = []
    if data.get("snapshot_consistency") == CHANGING:
        blocked.append(f"  - {PROJECT_CHANGED}: the Project changed while it was read; no current / next is claimed")
    for blocker in [] if lifecycle_unavailable else lifecycle.get("blockers") or []:
        if blocker["code"] == PROJECT_CHANGED:
            continue
        detail = ", ".join(_label(index, i) for i in blocker.get("ids") or [])
        extra = ""
        if blocker.get("predecessors"):
            extra = " waits for " + ", ".join(f"{p['id']} ({p['state']})" for p in blocker["predecessors"])
        blocked.append(f"  - {blocker['code']}" + (f": {detail}" if detail else "") + extra)
    validation = data["validation"]
    if isinstance(validation, dict) and validation.get("status") == "failed":
        blocked.append(f"  - validation failed ({len(validation.get('problems') or [])} problem(s))")
    out.extend(blocked or ["  none"])

    pending = data["pending"]
    heading("Pending mutation")
    unavailable_pending = _section_status(pending)
    if unavailable_pending:
        out.append(unavailable_pending)
    elif pending.get("status") == PENDING_NONE:
        out.append("  none")
    else:
        for record in pending.get("records") or []:
            out.append(
                f"  {record['mutation_id'] or record['filename']}  owner={record['owner'] or 'unknown'}  "
                f"{record['classification']} - {_reason_text(record['reason'])}"
            )
            if record.get("stages"):
                out.append(f"    stages: {', '.join(record['stages'])} ({record['applied_count']}/{record['effect_count']} applied)")
            scope = record.get("write_scope") or {}
            if scope.get("entities") or scope.get("files"):
                out.append(f"    write scope: {', '.join((scope.get('entities') or []) + (scope.get('files') or []))}")
    found = pending.get("dispositions") if isinstance(pending, dict) else None
    if isinstance(found, list):
        for disposition in found:
            out.append(
                f"  Human disposition {disposition['target_id']}: {disposition['state']} (runtime record "
                f"{disposition['runtime_record'] or 'unknown'})"
                + (f" - {_reason_text(disposition['problem'])}" if disposition.get("problem") else "")
            )
    if isinstance(pending, dict) and isinstance(pending.get("lock"), dict):
        lock = pending["lock"]
        out.append(
            f"  execution lock: {lock['state']} (holder hint: {lock['holder_hint']}"
            + (f", {lock['holder_operation']}" if lock.get("holder_operation") else "") + ")"
        )

    review = data["review"]
    heading("Review")
    unavailable = _section_status(review)
    if unavailable:
        out.append(unavailable)
    else:
        namespace = review["namespace"]
        out.append(f"  namespace: {namespace['status']}" + (f" - {_reason_text(namespace['reason'])}" if namespace.get("reason") else ""))
        activation = review["activation"]
        out.append(
            f"  Work-terminal activation: {activation['status']}"
            + (f" ({activation['operation_contract']})" if activation.get("operation_contract") else "")
            + (f" - {_reason_text(activation['reason'])}" if activation.get("reason") else "")
        )
        runs = review["runs"]
        if runs.get("reason"):
            out.append(f"  runs: unavailable - {_reason_text(runs['reason'])}")
        for run in runs.get("entries") or []:
            obligations = run["blocking_obligations"]
            out.append(
                f"  {run['review_run_id']}  {run['review_kind'] or '?'} -> {run['target_identity'] or '?'}  "
                f"generation {run['latest_generation']}  {run['state']}  receipt {run['receipt']['status']}  "
                f"consumption {run['consumption']['status']}"
                + ("" if obligations["status"] == NOT_AVAILABLE_BY_CONTRACT
                   else f"  obligations {_counted(obligations)}")
                + (f" - {_reason_text(run['reason'])}" if run.get("reason") else "")
            )
        out.append(f"  pending obligations: {_counted(review['pending_obligations'])}")

    heading("Validation")
    out.append(
        f"  {validation.get('status')}"
        + (f" - {_reason_text(validation['reason'])}" if validation.get("reason") else "")
    )
    for problem in validation.get("problems") or []:
        out.append(f"  - {problem['code']}: {problem['message']}")

    git = data["git"]
    heading("Git / push destination")
    if git.get("status") == "unavailable":
        out.append(f"  unavailable - {_reason_text(git.get('reason'))}")
    else:
        out.append(f"  toplevel: {git['toplevel']}" + ("" if git.get("toplevel_is_project_root") else " (not the Project root)"))
        if git.get("detached"):
            out.append("  branch: detached HEAD")
        else:
            out.append(f"  branch: {git.get('branch_ref') or 'unknown'}")
        out.append(f"  HEAD: {git.get('head') or 'none (no commit yet)'}")
        dirty = git["dirty"]
        if dirty.get("status") != "available":
            out.append(f"  dirty: unavailable - {_reason_text(dirty.get('reason'))}")
        else:
            out.append(f"  dirty: {len(dirty['entries'])} path(s)")
            for entry in dirty["entries"]:
                out.append(f"    {entry['index']}{entry['worktree']} {entry['path']}")
        push = git.get("push_destination") or {}
        if push.get("status") == "unavailable":
            out.append(f"  push destination: unavailable - {_reason_text(push.get('reason'))}")
        else:
            approved = push["approved_destination"]
            out.append(
                f"  approved destination: {approved['status']}"
                + (f" ({approved['remote']}: {', '.join(approved['allowed_urls'])})" if approved.get("remote") else "")
                + (f" - {_reason_text(approved['reason'])}" if approved.get("reason") else "")
            )
            out.append(f"  remotes: {', '.join(push['remotes']) or 'none'}")
            active = push["active_local_push_locator"]
            out.append(
                f"  active local push locator: {active['status']}"
                + (f" ({active['locator']})" if active.get("locator") else "")
                + (f" [{', '.join(active['locators'])}]" if active.get("status") == "multiple" else "")
            )
            out.append(f"  local locator matches pin: {push['local_locator_matches_pin']}")
            if push.get("problem"):
                out.append(f"  problem: {push['problem']}")
            out.append(f"  remote publication: {push['remote_publication_state']}")

    heading("Achievement")
    out.append(f"  {data['completion']['status']}")
    heading("Policy")
    out.append(f"  {data['policy']['status']}")
    return "\n".join(out) + "\n"


__all__ = [
    "CHANGING",
    "DISPOSED_BY_HUMAN",
    "HUMAN_SECTIONS",
    "NOT_AVAILABLE_BY_CONTRACT",
    "PENDING_NONE",
    "PENDING_RECONCILE",
    "PENDING_RESUMABLE",
    "PROJECT_CHANGED",
    "RESUME_CLASSIFICATIONS",
    "SCHEMA",
    "STABLE_READ",
    "StatusModel",
    "UNKNOWN_OR_INVALID",
    "VERSION",
    "Witnesses",
    "build_status",
    "canonical_fingerprint",
    "canonical_inventory",
    "read_witnesses",
    "render_human",
    "render_json",
]
