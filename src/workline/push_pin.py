"""Push destination pin maintenance (Workline infrastructure, not a Skill).

Adding or changing a Project's approved push destination is Project-specific
safety configuration, so it is neither a domain operation nor something an AI
may do on its own initiative:

* the destination is an **explicit human argument**; it is never read out of
  the Git configuration and turned into the approval of itself;
* only ``.workline/project.yaml`` is written — no ``.workline`` is
  re-initialized, no Roadmap / Phase / Work / relation / event is touched;
* the operation refuses to run while any other mutation is pending, so a
  pending operation recorded against the old destination is never silently
  re-aimed at the new one;
* it is not routed from ``skills/project-router``: no new domain Skill exists
  for it, exactly like the bootstrap backfill.

The legitimate A → B change is therefore: the human moves the Git remote, every
ordinary operation STOPs on the mismatch, and the human runs this operation
with the new destination to move the approval as well.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from . import gitcmd, gitops, pushurl
from .bootstrap import is_established_project
from .destination import DEFAULT_REMOTE, ensure_push_destination, resolve_active_push_url
from .errors import ReconcileRequired, StopError
from .mutation import Effect, Mutation, MutationController, WriteScope, abandon_on_stop
from .registry import validate_registry
from .store import PROJECT_YAML_REL, ProjectStore, PushPin
from .validate import validate_project_yaml

OWNER = "push-destination-pin"
PIN_COMMIT_MESSAGE = "chore(workline): pin push destination"


@dataclass(frozen=True)
class PinResult:
    status: str  # "pinned" | "already_pinned"
    project_root: Path
    remote: str
    url: str  # the active push destination Git resolves right now
    allowed_urls: tuple[str, ...]
    mutation_id: str | None = None
    head: str | None = None
    pushed: bool = False
    resumed: bool = False


def _approved(urls: Sequence[str]) -> tuple[str, ...]:
    """Normalize the human-supplied destinations, refusing credentials.

    Done before anything durable exists: a credential-bearing URL must never
    reach project.yaml *or* a recovery record, and the recovery record holds
    the invocation.
    """
    if not urls:
        raise StopError(
            "pin maintenance needs at least one approved push destination", code="push_destination_invalid"
        )
    accepted: list[str] = []
    for url in urls:
        normalized = pushurl.accept(url, "approved push destination")
        if normalized not in accepted:
            accepted.append(normalized)
    return tuple(accepted)


def pin_push_destination(project_root: Path, urls: Sequence[str], remote: str = DEFAULT_REMOTE) -> PinResult:
    """Approve ``urls`` as the push destinations of an established Project."""
    approved = _approved(urls)

    root = Path(project_root)
    if not root.is_dir():
        raise StopError(f"Project root is not a directory: {root}", code="project_root_missing")
    root = root.resolve()
    store = ProjectStore(root)
    if gitcmd.toplevel(root) != root:
        raise StopError(
            f"Project root is not the Git top-level; pin maintenance needs an established Project repository: {root}",
            code="not_a_project",
        )
    if not is_established_project(store):
        raise StopError(
            "not a valid established Workline Project (project.yaml missing, invalid or untracked); "
            "pin maintenance does not initialize a Project",
            code="not_a_project",
        )
    validation = validate_registry(store.workline_root())
    if not validation.ok:
        detail = "; ".join(f"{p.code}: {p.message}" for p in validation.problems)
        raise StopError(f"registry validation failed: {detail}", code="registry_invalid")

    # What the human approved must be what Git actually resolves right now.
    if remote not in gitcmd.remotes(root):
        raise StopError(f"this repository has no remote {remote}", code="push_destination_remote_missing")
    resolved = resolve_active_push_url(root, remote)
    if resolved not in approved:
        raise StopError(
            f"remote {remote} pushes to {resolved}, which is not among the destinations given "
            f"({', '.join(approved)}); STOP: state the destination you actually intend",
            code="push_destination_mismatch",
        )

    desired = PushPin(remote, approved)
    controller = MutationController(store)
    invocation = {"operation": OWNER, "project_root": str(root), "remote": remote, "urls": list(approved)}
    pending = controller.list_pending()
    matches = [p for p in pending if p["owner"] == OWNER and p["invocation"] == invocation]
    others = [p for p in pending if p not in matches]
    if others:
        detail = ", ".join(f"{p['mutation_id']} (owner {p['owner']})" for p in others)
        raise StopError(
            f"another Workline operation is still pending ({detail}); it may have been recorded against the "
            "current push destination, so the approved destination is not changed underneath it",
            code="pending_operation",
        )
    if len(matches) > 1:
        raise ReconcileRequired(f"{len(matches)} pending pin mutations match this request: reconcile required")

    current = store.read_push_pin()
    if current == desired and not matches:
        return PinResult("already_pinned", root, remote, resolved, approved)

    owned = [PROJECT_YAML_REL]
    mutation = controller.open(OWNER, invocation, WriteScope(files=tuple(owned)))
    with abandon_on_stop(mutation):
        gitops.ensure_git_ready(root)
        preexisting = gitops.record_preexisting_dirty(mutation, root)
        gitops.ensure_separable(preexisting, owned)

    if not mutation.has_stage("pin"):
        # project.yaml already exists: the update carries the content it was
        # decided against, so a resume can tell an unapplied write from someone
        # else's change.
        base = store.project_yaml.read_text(encoding="utf-8")
        mutation.add_effects(
            "pin", [Effect.write_file(PROJECT_YAML_REL, store.project_yaml_with_pin(desired), base)]
        )
    mutation.apply()

    # With the approval durable, the ordinary entry check must now pass — the
    # commit is pushed to the destination it just approved, so a clone gets it.
    destination = ensure_push_destination(store)
    gitops.finalize(mutation, "commit", PIN_COMMIT_MESSAGE, owned, destination=destination)

    _postcheck(store, desired, mutation, preexisting)
    mutation.complete()
    return PinResult(
        "pinned",
        root,
        remote,
        resolved,
        approved,
        mutation.id,
        gitcmd.head_commit(root),
        pushed=destination is not None,
        resumed=mutation.resumed,
    )


def _postcheck(store: ProjectStore, desired: PushPin, mutation: Mutation, preexisting: list[str]) -> None:
    root = store.root
    if store.read_push_pin() != desired:
        raise StopError("postcheck: project.yaml does not hold the approved destination", code="postcheck_failed")
    problems = validate_project_yaml(store)
    if problems:
        raise StopError("postcheck: " + "; ".join(p.message for p in problems), code="postcheck_failed")
    effects: list[dict[str, Any]] = mutation.effects
    written = {e["payload"]["path"] for e in effects if e["kind"] == "write_file"}
    if written != {PROJECT_YAML_REL}:
        raise StopError(
            f"postcheck: pin maintenance wrote more than project.yaml: {sorted(written)}", code="postcheck_failed"
        )
    if any(e["kind"] in ("add_relation", "remove_relation", "append_event") for e in effects):
        raise StopError("postcheck: pin maintenance touched domain state", code="postcheck_failed")
    head = gitcmd.head_commit(root)
    if head is None:
        raise StopError("postcheck: pin commit missing", code="postcheck_failed")
    if gitcmd.commit_touches(root, head, [PROJECT_YAML_REL]) != {PROJECT_YAML_REL}:
        raise StopError("postcheck: the pin commit does not hold project.yaml", code="postcheck_failed")
    if gitcmd.changed_against_head(root, [PROJECT_YAML_REL]):
        raise StopError("postcheck: project.yaml differs from HEAD", code="postcheck_failed")
    lost = sorted(set(preexisting) - set(gitops.capture_preexisting_dirty(root)))
    if lost:
        raise StopError("postcheck: unrelated changes were consumed: " + ", ".join(lost), code="postcheck_failed")
