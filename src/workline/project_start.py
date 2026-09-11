"""Project開始 (``skills/project-start``).

Initialize a local folder as a new Workline Project:
preflight → registry validation → Git boundary → pre-effect checks
(``git init -b main`` when needed, bootstrap committability, separable
pre-existing changes) → recovery intent → canonical ``.workline`` structure →
``project.yaml`` → Project-side bootstrap Skill → initial commit (fixed
message, no push) → postcheck.

A new Project開始 settles its predictable pre-effect STOPs before its recovery
intent exists, so they leave no ``.workline`` behind. A pending Project開始
resumes as the same mutation. A ``.workline`` proven to hold nothing but
Project開始 intents for this folder, each abandoned before its first effect, is
started again as a new mutation with those records left as they are; any other
partial ``.workline`` is not repaired by guess.

The bootstrap Skill is what lets the Project be opened directly in Claude
Code afterwards; it is a thin router entry point, never a copy of a canonical
Skill (see :mod:`workline.bootstrap`). Projects initialized before it existed
are handled by ``bootstrap.backfill_bootstrap``, not by re-running this
pre-project operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import stat
from typing import Callable

from . import gitcmd, gitops, pushurl
from .bootstrap import (
    ABSENT,
    CONFLICT,
    MATCHING,
    bootstrap_conflict_error,
    bootstrap_state,
    bootstrap_tracked,
    ensure_bootstrap_committable,
    is_established_project,
    render_bootstrap,
)
from .context import _pre_project_authorization, require_pre_project_context
from .destination import DEFAULT_REMOTE, resolve_active_push_locator
from .errors import StopError
from .ids import is_valid_id
from .implementation import require_configured_implementation
from .mutation import Effect, Mutation, MutationController, WriteScope, abandon_on_stop
from .registry import validate_registry
from .self_hosting import refuse_self_hosting
from .store import (
    BOOTSTRAP_REL_PATH,
    MUTATIONS_DIR,
    RUNTIME_DIR,
    TMP_DIR,
    ProjectStore,
    PushPin,
    WORKLINE_DIR,
    render_project_yaml,
    render_relations,
)
from .validate import validate_project_yaml

# Initial Project開始 is outside the Project execution lock (rules/git): the
# Project does not exist yet, and starting the same Project twice at once is
# not supported. Its mutation is written only inside the pre-project
# authorization project_start() grants for its own target root
# (store.PRE_PROJECT_OWNERS names the owner; the name alone authorizes nothing).
OWNER = "project-start"
INITIAL_COMMIT_MESSAGE = "chore(workline): initialize project"


@dataclass(frozen=True)
class ProjectStartResult:
    status: str  # "initialized" | "already_initialized"
    project_root: Path
    mutation_id: str | None
    head: str | None
    resumed: bool = False
    pinned_url: str | None = None
    unpinned_remotes: tuple[str, ...] = ()  # remotes present with no approved destination


def _pin_or_stop(root: Path, expected_push_url: str, remote: str) -> PushPin:
    """Approve ``expected_push_url`` as this Project's push destination.

    The human states the destination; Git states what it currently resolves.
    A pin is written only when the two agree character for character — a remote
    is never blessed just because it happens to be configured, and two
    spellings are never assumed to name the same repository.
    """
    approved = expected_push_url.strip()
    pushurl.ensure_no_secret(approved, "expected push destination")
    if remote not in gitcmd.remotes(root):
        raise StopError(
            f"expected push destination was given for remote {remote}, which this repository does not have",
            code="push_destination_remote_missing",
        )
    resolved = resolve_active_push_locator(root, remote)
    if resolved != approved:
        raise StopError(
            f"remote {remote} pushes to {resolved}, not to the expected destination {approved}; STOP",
            code="push_destination_mismatch",
        )
    return PushPin(remote, (approved,))


def _registry_or_stop(workline_root: Path) -> None:
    result = validate_registry(workline_root)
    if not result.ok:
        detail = "; ".join(f"{p.code}: {p.message}" for p in result.problems)
        raise StopError(f"registry validation failed: {detail}", code="registry_invalid")


def _relative_to_parent(root: Path, parent: Path) -> str:
    try:
        return root.relative_to(parent).as_posix()
    except ValueError:
        raise StopError(
            f"Project root {root} is not expressible relative to the enclosing Git repository {parent}",
            code="git_boundary_unclear",
        ) from None


def _git_boundary(root: Path) -> str:
    """How ``root`` relates to Git — "existing" | "init" — from Git alone.

    ``Project root == Git top-level`` keeps the existing repository, and no
    enclosing repository means a fresh one. Inside an enclosing repository a
    fresh repository is created only when Git itself proves the two cannot
    claim the same files: the whole Project root is ignored by the nearest
    parent repository *and* that repository tracks nothing beneath it. Any
    other state — including one Git cannot decide — STOPs. Path shape is never
    evidence; only what Git reports is.
    """
    top = gitcmd.toplevel(root)
    if top == root:
        return "existing"
    if top is None:
        return "init"

    relative = _relative_to_parent(root, top)
    ignored = gitcmd.is_ignored(top, relative)
    if ignored is None:
        raise StopError(
            f"cannot determine whether {relative} is ignored by the enclosing Git repository ({top}); STOP",
            code="git_boundary_unclear",
        )
    if not ignored:
        raise StopError(
            f"Project root is inside another Git repository ({top}) and is not ignored by it; STOP",
            code="parent_repo",
        )
    tracked = gitcmd.tracked_under(top, relative)
    if tracked is None:
        raise StopError(
            f"cannot determine what the enclosing Git repository ({top}) tracks under {relative}; STOP",
            code="git_boundary_unclear",
        )
    if tracked:
        raise StopError(
            f"the enclosing Git repository ({top}) tracks {len(tracked)} path(s) under the Project root "
            f"(first: {tracked[0]}); STOP",
            code="parent_repo_tracked",
        )
    return "init"


# Abandoned pre-effect residue ---------------------------------------------------

# Every field of a recovery intent Project開始 opened (MutationController.begin)
# and then closed (Mutation.abandon). A record with any other set of fields is
# not proven to be one this operation left behind.
_CLOSED_INTENT_FIELDS = frozenset({
    "workline", "version", "mutation_id", "owner", "status", "created_at", "updated_at",
    "invocation", "write_scope", "reserved_ids", "notes", "effects", "completed_at",
})


def _plain_entry(path: Path, is_kind: Callable[[int], bool]) -> bool:
    """Whether ``path`` itself is of that kind: not a symlink, junction or other reparse point."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        return False
    return is_kind(info.st_mode)


def _entry_names(directory: Path) -> set[str]:
    return {entry.name for entry in directory.iterdir()}


def _residue_layout_problem(store: ProjectStore) -> str | None:
    """Why ``.workline`` is not laid out as recovery records alone; None when it is.

    Allowed: ``runtime/mutations/`` holding one or more ``<mutation_id>.yaml``
    regular files, and an empty ``runtime/tmp/``. Nothing else — no canonical
    file or directory, not even an empty one, no lock area, no indirection.
    """
    if not _plain_entry(store.workline, stat.S_ISDIR):
        return f"{WORKLINE_DIR} is not a plain directory"
    names = _entry_names(store.workline)
    if names != {"runtime"}:
        extra = sorted(names - {"runtime"})
        return f"{WORKLINE_DIR} holds {extra[0]}" if extra else f"{WORKLINE_DIR} holds no recovery record"
    if not _plain_entry(store.runtime, stat.S_ISDIR):
        return f"{RUNTIME_DIR} is not a plain directory"
    names = _entry_names(store.runtime)
    extra = sorted(names - {"mutations", "tmp"})
    if extra:
        return f"{RUNTIME_DIR} holds {extra[0]}"
    if "tmp" in names:
        if not _plain_entry(store.tmp, stat.S_ISDIR):
            return f"{TMP_DIR} is not a plain directory"
        if _entry_names(store.tmp):
            return f"{TMP_DIR} is not empty"
    if "mutations" not in names:
        return f"{RUNTIME_DIR} holds no recovery record"
    if not _plain_entry(store.mutations, stat.S_ISDIR):
        return f"{MUTATIONS_DIR} is not a plain directory"
    names = _entry_names(store.mutations)
    if not names:
        return f"{MUTATIONS_DIR} holds no recovery record"
    for name in sorted(names):
        stem = name[: -len(".yaml")] if name.endswith(".yaml") else ""
        if not is_valid_id(stem, "mutation") or not _plain_entry(store.mutations / name, stat.S_ISREG):
            return f"{MUTATIONS_DIR} holds {name}, which is not a plain recovery record"
    return None


def _snapshot_path(path: object) -> bool:
    """Whether ``path`` is a Git worktree-relative path as a recorded snapshot holds it.

    Slash-separated and relative: no backslash, no drive, and no empty, ``.``
    or ``..`` component. A single trailing slash is the one exception, since
    Git reports an untracked nested repository as its directory (``sub/``).
    """
    if not isinstance(path, str) or not path or "\\" in path or path[1:2] == ":":
        return False
    body = path[:-1] if path.endswith("/") else path
    return all(part not in ("", ".", "..") for part in body.split("/")) and not gitops.is_runtime_path(path)


def _snapshot_shaped(value: object) -> bool:
    """Whether ``value`` is shaped like a recorded snapshot of pre-existing changes: sorted, unique Git paths outside runtime."""
    return isinstance(value, list) and all(_snapshot_path(path) for path in value) and value == sorted(set(value))


def _recorded_time(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _abandoned_before_effect_problem(record: dict, invocation: dict, scope: dict) -> str | None:
    """Why ``record`` is not proven to be a Project開始 intent for this folder closed before its first effect.

    ``Mutation.abandon`` refuses a mutation that recorded an effect, so an
    abandoned intent without effects never got as far as one.
    """
    name = f"recovery record {record['mutation_id']}"
    if set(record) != _CLOSED_INTENT_FIELDS or type(record["version"]) is not int:
        return f"{name} does not have the fields of a closed Project開始 intent"
    if record["owner"] != OWNER:
        return f"{name} belongs to {record['owner']}"
    if record["status"] != "abandoned":
        return f"{name} is {record['status']}"
    if record["invocation"] != invocation:
        return f"{name} was not recorded for Project開始 of this folder"
    if record["write_scope"] != scope:
        return f"{name} does not declare the Project開始 write scope"
    if record["effects"] != []:
        return f"{name} recorded effects"
    if record["reserved_ids"] != {}:
        return f"{name} reserved IDs"
    notes = record["notes"]
    if not isinstance(notes, dict) or not set(notes) <= {"preexisting_dirty"}:
        return f"{name} holds notes other than a snapshot of pre-existing changes"
    if "preexisting_dirty" in notes and not _snapshot_shaped(notes["preexisting_dirty"]):
        return f"{name} holds a snapshot of pre-existing changes Workline does not record"
    if not all(_recorded_time(record[key]) for key in ("created_at", "updated_at", "completed_at")):
        return f"{name} does not hold valid timestamps"
    return None


def _residue_tracked_problem(root: Path) -> str | None:
    """Why Git does not prove the Project repository holds nothing under ``.workline``; None when it does."""
    tracked = gitcmd.tracked_under(root, WORKLINE_DIR)
    if tracked is None:
        return f"cannot determine what the Project repository tracks under {WORKLINE_DIR}"
    if tracked:
        return f"the Project repository tracks {tracked[0]}"
    if gitcmd.head_commit(root) is None:
        return None
    held = gitcmd.run_git(root, "ls-tree", "-r", "-z", "--name-only", "HEAD", "--", WORKLINE_DIR, check=False)
    if not held.ok:
        return f"cannot determine what HEAD holds under {WORKLINE_DIR}"
    paths = sorted(path for path in held.stdout.split("\0") if path)
    return f"HEAD holds {paths[0]}" if paths else None


def _abandoned_start_residue_problem(
    store: ProjectStore, controller: MutationController, invocation: dict, declared: list[str], boundary: str
) -> str | None:
    """Why this ``.workline`` is not proven to be abandoned pre-effect Project開始 residue; None when it is.

    Proven residue is recovery records alone (:func:`_residue_layout_problem`),
    each confirmed by the Mutation Controller and each a Project開始 intent for
    exactly this folder and write scope, abandoned with no reserved ID and no
    effect (:func:`_abandoned_before_effect_problem`), in a Project repository —
    when there is one — that holds nothing under ``.workline``. A record the
    Mutation Controller cannot confirm has already stopped discovery as
    ``reconcile required``.
    """
    try:
        layout = _residue_layout_problem(store)
    except OSError as exc:
        return f"cannot inspect {WORKLINE_DIR}: {exc}"
    if layout is not None:
        return layout
    records = controller.list_records()
    if not records:
        return f"{MUTATIONS_DIR} holds no recovery record"
    scope = WriteScope(files=tuple(declared)).to_record()
    for record in records:
        problem = _abandoned_before_effect_problem(record, invocation, scope)
        if problem is not None:
            return problem
    if boundary == "existing":
        return _residue_tracked_problem(store.root)
    return None


def project_start(
    project_root: Path,
    workline_root: Path,
    *,
    expected_push_url: str | None = None,
    push_remote: str = DEFAULT_REMOTE,
) -> ProjectStartResult:
    root = Path(project_root)
    workline = Path(workline_root)
    # Preflight ------------------------------------------------------------
    if not root.is_dir():
        raise StopError(f"Project root is not a directory: {root}", code="project_root_missing")
    if not workline.is_dir():
        raise StopError(f"Workline root is not a directory: {workline}", code="workline_root_missing")
    root = root.resolve()
    workline = workline.resolve()
    # Project context (rules/git): never from inside another established Project
    # and never a Workline Project inside an established one, decided before
    # anything is written.
    require_pre_project_context(root)
    # Unsupported self-hosting (rules/git): a Workline root is never initialized
    # as a Project of its own, nor is a folder not proven to be a different
    # directory — decided before Git, .workline or the bootstrap are touched.
    refuse_self_hosting(root, workline)
    # Workline implementation (rules/git): the implementation that writes this
    # Workline root into project.yaml must be that root's own.
    require_configured_implementation(workline)
    _registry_or_stop(workline)

    boundary = _git_boundary(root)

    # Push destination: decided before anything is written, never derived from
    # whatever remote happens to be configured. Project開始 itself does not
    # push, so a Project with a remote and no approved destination is still a
    # valid Project — its first push-performing operation is what STOPs.
    pin: PushPin | None = None
    if expected_push_url is not None:
        if boundary != "existing":
            raise StopError(
                "an expected push destination was given, but this Project root has no Git repository yet",
                code="push_destination_remote_missing",
            )
        pin = _pin_or_stop(root, expected_push_url, push_remote)

    store = ProjectStore(root)
    controller = MutationController(store)
    invocation = {"operation": OWNER, "project_root": str(root)}
    declared = list(store.canonical_relative_paths) + [BOOTSTRAP_REL_PATH]
    pending_match = [
        p for p in controller.list_pending() if p["owner"] == OWNER and p["invocation"] == invocation
    ]

    if store.workline.exists() and not pending_match:
        if boundary == "existing" and is_established_project(store):
            if expected_push_url is not None:
                raise StopError(
                    "this is already an established Workline Project; a push destination is pinned there "
                    "by the pin maintenance operation, not by re-running Project開始",
                    code="already_initialized",
                )
            existing = store.read_push_pin()
            return ProjectStartResult(
                "already_initialized",
                root,
                None,
                gitcmd.head_commit(root),
                pinned_url=existing.allowed_urls[0] if existing else None,
                unpinned_remotes=() if existing else tuple(gitcmd.remotes(root)),
            )
        # The one partial .workline started again: Project開始 intents for this
        # folder alone, each proven abandoned before its first effect. They are
        # left as they are, and a new mutation is opened below.
        residue = _abandoned_start_residue_problem(store, controller, invocation, declared, boundary)
        if residue is not None:
            raise StopError(
                f"broken / partial .workline without a pending Project開始 mutation ({residue}); "
                "not repairing by guess",
                code="partial_workline",
            )

    # A file already sitting at the bootstrap path with different content is
    # ownership-unknown: STOP before anything is written. Other Skills under
    # .claude/skills are never inspected or touched.
    state = bootstrap_state(store)
    if state == CONFLICT:
        raise bootstrap_conflict_error()

    # The pre-project checks have passed: only this call may now open, resume
    # and write the Project開始 mutation, and only for this root.
    with _pre_project_authorization(root):
        mutation, owned, preexisting = _open_mutation(
            store, controller, invocation, declared, boundary, state, resume=bool(pending_match)
        )
        return _initialize(store, mutation, owned, preexisting, state, pin, root, workline)


def _prepare_repository(store: ProjectStore, boundary: str) -> None:
    """Give the Project root its own repository when its Git boundary calls for one; prove the bootstrap committable."""
    root = store.root
    if boundary == "init":
        gitcmd.init_main(root)
        if gitcmd.toplevel(root) != root:
            raise StopError("git init did not make Project root the Git top-level", code="git_init_failed")
    ensure_bootstrap_committable(store)


def _owned_paths(store: ProjectStore, state: str) -> list[str]:
    # An untracked file byte-identical to the expected bootstrap is the
    # artifact this operation owns, not an unrelated user change.
    owned = list(store.canonical_relative_paths)
    if state == ABSENT or not bootstrap_tracked(store):
        owned.append(BOOTSTRAP_REL_PATH)
    return owned


def _open_mutation(
    store: ProjectStore,
    controller: MutationController,
    invocation: dict,
    declared: list[str],
    boundary: str,
    state: str,
    *,
    resume: bool,
) -> tuple[Mutation, list[str], list[str]]:
    """Open the Project開始 mutation with its pre-effect checks settled.

    A pending Project開始 resumes as the same mutation and runs the checks inside
    it; the snapshot of pre-existing changes it already recorded stays the
    authority.

    A new one settles every predictable pre-effect STOP before its recovery
    intent exists — ``git init`` is not a domain effect — and records the very
    snapshot it checked before any effect. Such a STOP leaves no ``.workline``;
    a repository it initialized stays and is the existing one next time.
    """
    root = store.root
    scope = WriteScope(files=tuple(declared))
    exclude = (BOOTSTRAP_REL_PATH,) if state == MATCHING else ()
    if resume:
        mutation = controller.open(OWNER, invocation, scope)
        with abandon_on_stop(mutation):
            _prepare_repository(store, boundary)
            owned = _owned_paths(store, state)
            preexisting = gitops.record_preexisting_dirty(mutation, root, exclude=exclude)
            gitops.ensure_separable(preexisting, owned)
        return mutation, owned, preexisting

    _prepare_repository(store, boundary)
    owned = _owned_paths(store, state)
    preexisting = gitops.preexisting_dirty_snapshot(root, exclude=exclude)
    gitops.ensure_separable(preexisting, owned)
    mutation = controller.open(OWNER, invocation, scope)
    with abandon_on_stop(mutation):
        mutation.set_note("preexisting_dirty", preexisting)
    return mutation, owned, preexisting


def _initialize(
    store: ProjectStore,
    mutation: Mutation,
    owned: list[str],
    preexisting: list[str],
    state: str,
    pin: PushPin | None,
    root: Path,
    workline: Path,
) -> ProjectStartResult:
    # Create Project structure -----------------------------------------------
    if not mutation.has_stage("create"):
        effects = [
            Effect.write_file(f"{WORKLINE_DIR}/project.yaml", render_project_yaml(workline, pin)),
            Effect.write_file(f"{WORKLINE_DIR}/relations/roadmap.yaml", render_relations([])),
            Effect.write_file(f"{WORKLINE_DIR}/relations/related.yaml", render_relations([])),
            Effect.write_file(f"{WORKLINE_DIR}/events/events.jsonl", ""),
        ]
        if state == ABSENT:
            effects.append(Effect.write_file(BOOTSTRAP_REL_PATH, render_bootstrap()))
        mutation.add_effects("create", effects)
    mutation.apply()
    for name in ("roadmaps", "phases", "works", "derivations"):
        (store.workline / name).mkdir(parents=True, exist_ok=True)

    # Initial commit ----------------------------------------------------------
    _registry_or_stop(workline)
    # Project開始 is the documented exception: initial commit required, no push.
    gitops.finalize(mutation, "commit", INITIAL_COMMIT_MESSAGE, owned, destination=None)

    # Postcheck ---------------------------------------------------------------
    _postcheck(store, workline, owned, preexisting, pin)
    mutation.complete()
    return ProjectStartResult(
        "initialized",
        root,
        mutation.id,
        gitcmd.head_commit(root),
        resumed=mutation.resumed,
        pinned_url=pin.allowed_urls[0] if pin else None,
        unpinned_remotes=() if pin else tuple(gitcmd.remotes(root)),
    )


def _postcheck(
    store: ProjectStore, workline: Path, owned: list[str], preexisting: list[str], pin: PushPin | None
) -> None:
    root = store.root
    if gitcmd.toplevel(root) != root:
        raise StopError("postcheck: Git top-level != Project root", code="postcheck_failed")
    if store.workline_root() != workline:
        raise StopError("postcheck: project.yaml does not hold the given Workline root", code="postcheck_failed")
    problems = validate_project_yaml(store)
    if problems:
        raise StopError("postcheck: " + "; ".join(p.message for p in problems), code="postcheck_failed")
    if store.read_push_pin() != pin:
        raise StopError("postcheck: project.yaml does not hold the approved push destination", code="postcheck_failed")
    if store.read_roadmap_relations() != [] or store.read_related() != [] or store.read_events() != []:
        raise StopError("postcheck: central stores are not in initial state", code="postcheck_failed")
    if bootstrap_state(store) != MATCHING:
        raise StopError("postcheck: Project bootstrap Skill is missing or not the expected bootstrap", code="postcheck_failed")
    if not bootstrap_tracked(store):
        raise StopError("postcheck: Project bootstrap Skill is not tracked", code="postcheck_failed")
    if gitcmd.head_commit(root) is None:
        raise StopError("postcheck: initial commit missing", code="postcheck_failed")
    tracked = gitcmd.run_git(root, "ls-files", "-z", "--", *owned).stdout.split("\0")
    if set(p for p in tracked if p) != set(owned):
        raise StopError("postcheck: canonical files are not all tracked", code="postcheck_failed")
    if gitcmd.changed_against_head(root, owned):
        raise StopError("postcheck: canonical files differ from HEAD", code="postcheck_failed")
    still_dirty = set(gitops.capture_preexisting_dirty(root))
    lost = sorted(set(preexisting) - still_dirty)
    if lost:
        raise StopError("postcheck: unrelated changes were consumed: " + ", ".join(lost), code="postcheck_failed")
