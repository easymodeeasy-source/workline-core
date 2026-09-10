"""Project開始 (``skills/project-start``).

Initialize a local folder as a new Workline Project:
preflight → Git boundary → registry validation → ``git init -b main`` when
needed → canonical ``.workline`` structure → ``project.yaml`` → Project-side
bootstrap Skill → initial commit (fixed message, no push) → postcheck.

The bootstrap Skill is what lets the Project be opened directly in Claude
Code afterwards; it is a thin router entry point, never a copy of a canonical
Skill (see :mod:`workline.bootstrap`). Projects initialized before it existed
are handled by ``bootstrap.backfill_bootstrap``, not by re-running this
pre-project operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import gitcmd, gitops
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
from .errors import StopError
from .mutation import Effect, MutationController, WriteScope, abandon_on_stop
from .registry import validate_registry
from .store import BOOTSTRAP_REL_PATH, ProjectStore, WORKLINE_DIR, render_project_yaml, render_relations
from .validate import validate_project_yaml

OWNER = "project-start"
INITIAL_COMMIT_MESSAGE = "chore(workline): initialize project"


@dataclass(frozen=True)
class ProjectStartResult:
    status: str  # "initialized" | "already_initialized"
    project_root: Path
    mutation_id: str | None
    head: str | None
    resumed: bool = False


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


def project_start(project_root: Path, workline_root: Path) -> ProjectStartResult:
    root = Path(project_root)
    workline = Path(workline_root)
    # Preflight ------------------------------------------------------------
    if not root.is_dir():
        raise StopError(f"Project root is not a directory: {root}", code="project_root_missing")
    if not workline.is_dir():
        raise StopError(f"Workline root is not a directory: {workline}", code="workline_root_missing")
    root = root.resolve()
    workline = workline.resolve()
    _registry_or_stop(workline)

    boundary = _git_boundary(root)

    store = ProjectStore(root)
    controller = MutationController(store)
    invocation = {"operation": OWNER, "project_root": str(root)}
    pending_match = [
        p for p in controller.list_pending() if p["owner"] == OWNER and p["invocation"] == invocation
    ]

    if store.workline.exists() and not pending_match:
        if boundary == "existing" and is_established_project(store):
            return ProjectStartResult("already_initialized", root, None, gitcmd.head_commit(root))
        raise StopError(
            "broken / partial .workline without a pending Project開始 mutation; not repairing by guess",
            code="partial_workline",
        )

    # A file already sitting at the bootstrap path with different content is
    # ownership-unknown: STOP before anything is written. Other Skills under
    # .claude/skills are never inspected or touched.
    state = bootstrap_state(store)
    if state == CONFLICT:
        raise bootstrap_conflict_error()

    declared = list(store.canonical_relative_paths) + [BOOTSTRAP_REL_PATH]
    mutation = controller.open(OWNER, invocation, WriteScope(files=tuple(declared)))

    # Git boundary --------------------------------------------------------
    with abandon_on_stop(mutation):
        if boundary == "init":
            gitcmd.init_main(root)
            if gitcmd.toplevel(root) != root:
                raise StopError("git init did not make Project root the Git top-level", code="git_init_failed")
        ensure_bootstrap_committable(store)
        # An untracked file byte-identical to the expected bootstrap is the
        # artifact this operation owns, not an unrelated user change.
        owned = list(store.canonical_relative_paths)
        if state == ABSENT or not bootstrap_tracked(store):
            owned.append(BOOTSTRAP_REL_PATH)
        preexisting = gitops.record_preexisting_dirty(
            mutation, root, exclude=(BOOTSTRAP_REL_PATH,) if state == MATCHING else ()
        )
        gitops.ensure_separable(preexisting, owned)

    # Create Project structure -----------------------------------------------
    if not mutation.has_stage("create"):
        effects = [
            Effect.write_file(f"{WORKLINE_DIR}/project.yaml", render_project_yaml(workline)),
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
    gitops.finalize(mutation, "commit", INITIAL_COMMIT_MESSAGE, owned, push=False)

    # Postcheck ---------------------------------------------------------------
    _postcheck(store, workline, owned, preexisting)
    mutation.complete()
    return ProjectStartResult("initialized", root, mutation.id, gitcmd.head_commit(root), resumed=mutation.resumed)


def _postcheck(store: ProjectStore, workline: Path, owned: list[str], preexisting: list[str]) -> None:
    root = store.root
    if gitcmd.toplevel(root) != root:
        raise StopError("postcheck: Git top-level != Project root", code="postcheck_failed")
    if store.workline_root() != workline:
        raise StopError("postcheck: project.yaml does not hold the given Workline root", code="postcheck_failed")
    problems = validate_project_yaml(store)
    if problems:
        raise StopError("postcheck: " + "; ".join(p.message for p in problems), code="postcheck_failed")
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
