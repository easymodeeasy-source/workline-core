"""The publication barrier and the committed planning proof (``rules/git`` Push destination; ``skills/review``).

No Workline push - of any operation, legacy ones included - publishes a commit
whose history holds a review-v1 planning registration commit unless the
committed planning proof proves that registration's Run for exactly the commit
being published. Both read committed Git objects only: no commit message,
branch position, runtime note, mutation record, remote state or working-tree
file takes part, and no attribute is evaluated.

```text
fast path   git rev-list --full-history -n 1 <C> -- .workline/review/candidate-snapshots/
            empty -> clear, on any Git; a read Git cannot answer -> held
Git         listed, and the running Git below P2_PUBLICATION_GIT_MIN (2.31.0) or of unknown
            version -> refused as a capability failure that names no Run
Runs        every planning Candidate snapshot added in C's history -> its reserved entity paths
            -> the commits that add them; a Run with none is not registered and begins nothing
proof       CP1-CP5, CP7, CP6, CP8-CP13 for every registered Run, from committed objects alone
```

A Candidate snapshot alone never begins the barrier; a Supersession, a
Consumption, a metadata commit or the destination's state never clears it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import gitcmd
from ..committed_view import CommittedReadError
from ..errors import StopError, ValidationError
from ..store import ProjectStore
from . import committed, paths, planning, records, serialize

#: The directory whose history the fast path reads.
FAST_PATH_DIRECTORY = f"{paths.CANDIDATE_SNAPSHOTS_DIR}/"

UNAVAILABLE_BELOW = "publication proof unavailable: the running Git is below P2_PUBLICATION_GIT_MIN (2.31.0)"
UNAVAILABLE_UNKNOWN = "publication proof unavailable: the running Git's version is unknown"


def _barrier(detail: str) -> StopError:
    return StopError(f"publication barrier: {detail}; nothing is published", code="review_publication_barrier")


def require_barrier_clear(repo: Path, commit: str | None) -> None:
    """``review_publication_barrier`` unless the barrier is clear for ``commit``."""
    problem = barrier_problem(repo, commit)
    if problem is not None:
        raise _barrier(problem)


def barrier_problem(repo: Path, commit: str | None) -> str | None:
    """Why a push of ``commit`` may not publish its history; None when the barrier is clear."""
    if commit is None:
        return None  # no history, so no registration commit to publish
    touched = gitcmd.history_touches(Path(repo), commit, FAST_PATH_DIRECTORY)
    if touched is None:
        return f"the fast-path read of {commit}'s history could not be answered, and an unanswered read is no clear barrier"
    if not touched:
        return None
    version = gitcmd.running_git_version()
    if version is None:
        return UNAVAILABLE_UNKNOWN
    if not gitcmd.version_meets(version, gitcmd.P2_PUBLICATION_GIT_MIN):
        return UNAVAILABLE_BELOW
    try:
        runs = registered_runs(Path(repo), commit)
    except (ValidationError, StopError, CommittedReadError) as exc:
        return f"the planning Runs of {commit}'s history cannot be read ({exc})"
    for run in runs:
        failed = committed_planning_proof(Path(repo), commit, run)
        if failed is not None:
            item, detail = failed
            return (
                f"the review-v1 registration commit {run.registration_commit or '(not unique)'} of the Run with "
                f"candidate {run.candidate_hash} is not proven for {commit}: {item} fails ({detail})"
            )
    return None


# --------------------------------------------------------------------------- registered Runs

@dataclass(frozen=True)
class RegisteredRun:
    candidate_hash: str
    material: dict[str, Any]
    entity_paths: tuple[str, ...]
    registration_commits: tuple[str, ...]

    @property
    def registration_commit(self) -> str | None:
        return self.registration_commits[0] if len(self.registration_commits) == 1 else None


def registered_runs(repo: Path, commit: str) -> list[RegisteredRun]:
    """Every planning Run of ``commit``'s history whose reserved entity paths some commit of that history adds."""
    from ..roadmap_review import entity_paths

    added = committed.added_in_history(repo, commit, [paths.CANDIDATE_SNAPSHOTS_DIR])
    adders: dict[str, list[str]] = {}
    for listed, names in added:
        for name in names:
            if name.startswith(paths.CANDIDATE_SNAPSHOTS_DIR + "/"):
                adders.setdefault(name, []).append(listed)
    runs: list[RegisteredRun] = []
    for path in sorted(adders):
        materials = []
        for adding in adders[path]:
            snapshot = committed.read_candidate_snapshot_blob(repo, adding, path)
            if snapshot.material not in materials:
                materials.append(snapshot.material)
        if len(materials) != 1:
            raise ValidationError(f"{path} was added with different contents in the history", code="review_record_invalid")
        material = materials[0]
        if not planning.is_planning_candidate(material) or (material or {}).get("review_kind") not in planning.PLANNING_KINDS:
            continue  # not a planning Candidate: it concerns no planning registration
        planning.require_planning_candidate(material, f"the Candidate snapshot {path}")
        try:
            wanted = tuple(entity_paths(material))
        except (KeyError, TypeError, IndexError) as exc:
            raise ValidationError(
                f"the planning Candidate {path} does not yield its registration paths ({exc})", code="review_record_invalid"
            ) from exc
        registering = tuple(
            listed for listed, names in committed.added_in_history(repo, commit, list(wanted)) if set(names) & set(wanted)
        )
        if not registering:
            continue  # a Candidate snapshot alone begins no barrier
        candidate_hash = path.rsplit("/", 1)[-1][: -len(".yaml")]
        runs.append(RegisteredRun(candidate_hash, material, wanted, registering))
    return runs


# --------------------------------------------------------------------------- the committed planning proof

class _Fail(Exception):
    def __init__(self, item: str, detail: str) -> None:
        super().__init__(f"{item}: {detail}")
        self.item = item
        self.detail = detail


def committed_planning_proof(repo: Path, commit: str, run: RegisteredRun) -> tuple[str, str] | None:
    """``(item, detail)`` of the first CP item that fails for ``run`` at ``commit``; None when every item passes.

    Contract ``review-v1-planning-committed-proof-v1``. The items run in the
    order CP1-CP5, CP7, CP6, CP8-CP13: a declared-base difference is reported
    as CP7 and never as an R9 mismatch.
    """
    progress = ["CP1"]
    try:
        _prove(repo, commit, run, progress)
    except _Fail as failed:
        return failed.item, failed.detail
    except Exception as exc:  # anything unanswerable is no proof: the item under evaluation fails
        return progress[-1], f"{type(exc).__name__}: {exc}"
    return None


def _require(condition: bool, item: str, detail: str) -> None:
    if not condition:
        raise _Fail(item, detail)


def _guard(item: str, action):
    try:
        return action()
    except _Fail:
        raise
    except Exception as exc:  # an object, record or question that cannot be read or answered is no proof
        raise _Fail(item, f"{type(exc).__name__}: {exc}") from exc


def _prove(repo: Path, commit: str, run: RegisteredRun, progress: list[str]) -> None:
    from .. import roadmap_review as rr
    from ..committed_view import committed_view
    from ..validate import validate_structure
    from .validate import GATE_RECEIPT_BINDING, RECEIPT_CONSUMPTION_BINDING

    store = ProjectStore(repo)
    material = run.material
    content = planning.candidate_content(material)

    # CP1 - the registration commit and its one parent
    _require(len(run.registration_commits) == 1, "CP1", f"{len(run.registration_commits)} commits add the Run's paths")
    registration = run.registration_commits[0]
    added = _guard("CP1", lambda: committed.added_in_history(repo, commit, list(run.entity_paths)))
    adds_all = [names for listed, names in added if listed == registration]
    _require(bool(adds_all) and set(run.entity_paths) <= set(adds_all[0]), "CP1", f"{registration} does not add every reserved entity path")
    parents = gitcmd.commit_parents(repo, registration)
    _require(parents is not None and len(parents) == 1, "CP1", f"{registration} does not have exactly one parent")
    parent = parents[0]

    progress.append("CP2")
    # CP2 - the Run's records at the parent, and its chain
    at_parent = _guard("CP2", lambda: committed.CommittedReviewStore(repo, parent))
    candidate_hash = planning.candidate_hash(material)
    runs = _guard("CP2", lambda: at_parent.runs_with_candidate(candidate_hash))
    _require(len(runs) == 1, "CP2", f"{parent} holds {len(runs)} Runs of the Candidate")
    review_run_id = runs[0]
    chain = _guard("CP2", lambda: at_parent.gate_chain(review_run_id))
    _require(chain is not None and len(chain.generations) == planning.SEAL_GENERATION, "CP2",
             f"the Run's chain at {parent} is not generations 1-3")
    first, second, third = chain.generations
    _require(
        first.status == records.GATE_STATUS_OPEN and len(first.accepted_tasks) == 1 and not first.settled_tasks
        and second.status == records.GATE_STATUS_OPEN and len(second.settled_tasks) == 1
        and third.sealed and third.receipt_id is not None,
        "CP2", "the chain is not accept -> settle -> seal",
    )
    receipt_id = str(third.receipt_id)
    receipt = _guard("CP2", lambda: at_parent.read_receipt(receipt_id))
    for gate_field, receipt_field in GATE_RECEIPT_BINDING:
        _require(getattr(third, gate_field) == getattr(receipt, receipt_field), "CP2",
                 f"the Receipt's {receipt_field} is not generation 3's {gate_field}")
    snapshot = _guard("CP2", lambda: at_parent.read_candidate_snapshot(candidate_hash))
    descriptor = first.accepted_tasks[0]
    task_id = str(descriptor["task_id"])
    task_input = _guard("CP2", lambda: at_parent.read_task_input(task_id))
    _require(not _guard("CP2", lambda: at_parent.supersession_exists(receipt_id)), "CP2",
             f"{parent} holds a Supersession of the Receipt")

    progress.append("CP3")
    # CP3 - provenance
    problems = _guard("CP3", lambda: at_parent.provenance_problems(descriptor, 1))
    _require(not problems, "CP3", "; ".join(message for _, message in problems))
    _require(snapshot.material == material, "CP3", "the snapshot at the parent is not the Run's Candidate")
    problems3 = planning.task_input_problems(
        task_input, material, first.candidate_hash, first.review_context_hash, first.effective_policy_hash
    )
    _require(not problems3, "CP3", "; ".join(problems3))
    _require(first.review_kind == material["review_kind"], "CP3", "the Run's kind is not the Candidate's")
    _require(first.target_identity == rr.candidate_target(material), "CP3", "the Run's target is not the Candidate's")
    context = task_input.request_envelope.get("context")

    progress.append("CP4")
    # CP4 - the same Run records at C, and no invalidation anywhere in C's history
    record_paths = [
        paths.candidate_snapshot_rel(candidate_hash), paths.task_input_rel(task_id),
        paths.gate_rel(review_run_id, 1), paths.gate_rel(review_run_id, 2), paths.gate_rel(review_run_id, 3),
        paths.receipt_rel(receipt_id),
    ]
    at_commit = _guard("CP4", lambda: committed.CommittedReviewStore(repo, commit))
    for relative in record_paths:
        _require(at_commit.blob_id(relative) == at_parent.blob_id(relative) and at_parent.blob_id(relative) is not None,
                 "CP4", f"{commit} does not hold {relative} as the parent holds it")
    invalidations = _guard("CP4", lambda: committed.added_in_history(
        repo, commit, [paths.gate_rel(review_run_id, planning.INVALIDATION_GENERATION), paths.supersession_rel(receipt_id)]
    ))
    _require(not invalidations, "CP4", f"{commit}'s history adds a generation 4 or a Supersession of the Receipt")

    progress.append("CP5")
    # CP5 - physical: K's delta is exactly E
    try:
        expected = rr.expected_projection(store, material, context, parent)
    except rr.ExpectedUnavailable as exc:
        raise _Fail("CP5", f"the expected physical projection is unavailable: {exc}") from exc
    problem = rr.delta_problem(repo, expected, registration)
    _require(problem is None, "CP5", problem or "")

    progress.append("CP7")
    # CP7 - the authorized pre-state, before any R9 comparison
    view_parent = _guard("CP7", lambda: committed_view(store, parent))
    found_base = _guard("CP7", lambda: rr.declared_base(view_parent, content))
    _require(serialize.canonical_data(found_base) == material["declared_base"], "CP7",
             f"the declared base on {parent} is not the Candidate's")

    progress.append("CP6")
    # CP6 - semantic, on the committed views of P and K
    view_registration = _guard("CP6", lambda: committed_view(store, registration))
    problem = rr.semantic_problem(material, view_parent, view_registration)
    _require(problem is None, "CP6", problem or "")
    _require(not validate_structure(view_registration), "CP6", "the registration commit's structure does not validate")
    selection_id = rr.selected_first_work_id(material, view_registration)

    progress.append("CP8")
    # CP8 - exactly one Planning Consumption of the Receipt, bound to it and to the Run
    consumptions = _guard("CP8", lambda: at_commit.consumptions())
    naming = [found for found in consumptions if found.receipt_id == receipt_id]
    _require(len(naming) == 1, "CP8", f"{commit} holds {len(naming)} Consumptions of the Receipt")
    consumption = naming[0]
    _require(isinstance(consumption, records.PlanningConsumption), "CP8", "the Consumption is not a Planning Consumption")
    for name in RECEIPT_CONSUMPTION_BINDING:
        _require(getattr(receipt, name) == getattr(consumption, name), "CP8", f"the Consumption's {name} is not the Receipt's")
    _require(
        consumption.review_run_id == review_run_id and consumption.review_generation == planning.SEAL_GENERATION
        and consumption.review_kind == first.review_kind and consumption.authorized_candidate_hash == candidate_hash
        and consumption.operation_identity == first.operation_identity
        and consumption.target_identity == first.target_identity,
        "CP8", "the Consumption does not name the Run",
    )

    progress.append("CP9")
    # CP9 - every persisted_result claim re-proven
    result = consumption.persisted_result
    claims = rr.persisted_result_claims(
        material, first.operation_identity, registration, parent, expected, selection_id,
        context if isinstance(context, dict) else {},
    )
    for key, value in claims.items():
        _require(result.get(key) == value, "CP9", f"persisted_result {key} is not what the committed objects prove")
    _require(isinstance(result.get("branch"), str) and result["branch"].startswith("refs/heads/"), "CP9",
             "persisted_result branch is not a full branch ref")

    progress.append("CP10")
    # CP10 - uniqueness in C's tree
    planning_ones = [found for found in consumptions if isinstance(found, records.PlanningConsumption)]
    _require(sum(1 for found in planning_ones if found.registration_commit == registration) == 1, "CP10",
             "another Planning Consumption names the registration commit")
    _require(
        sum(1 for found in planning_ones if (found.review_kind, found.target_identity) == (first.review_kind, first.target_identity)) == 1,
        "CP10", "another Planning Consumption has the Run's kind and target",
    )

    progress.append("CP11")
    # CP11 - the metadata commit
    consumption_path = paths.consumption_rel(consumption.consumption_id)
    metadata = [listed for listed, names in _guard("CP11", lambda: committed.added_in_history(repo, commit, [consumption_path]))
                if consumption_path in names]
    _require(len(metadata) == 1, "CP11", f"{len(metadata)} commits add the Consumption")
    km = metadata[0]
    km_parents = gitcmd.commit_parents(repo, km)
    _require(km_parents is not None and len(km_parents) == 1, "CP11", f"{km} does not have exactly one parent")
    q = km_parents[0]
    _require(q == registration or gitcmd.descends_from(repo, q, registration) is True, "CP11",
             f"{km}'s parent does not descend from the registration commit")
    owned = rr.planning_owned_paths(review_run_id, material, task_id, receipt_id, consumption.consumption_id)
    touching = gitcmd.commits_touching(repo, registration, q, owned)
    _require(touching == [], "CP11", "a commit between the registration and the metadata commit touches a planning-owned path")
    at_km = _guard("CP11", lambda: committed.CommittedReviewStore(repo, km))
    _require(at_km.blob_id(consumption_path) is not None and at_km.blob_id(consumption_path) == at_commit.blob_id(consumption_path),
             "CP11", "the Consumption the metadata commit added is not the one the published commit holds")

    progress.append("CP12")
    # CP12 - the metadata commit carries the Consumption alone
    delta = gitcmd.commit_delta(repo, q, km)
    _require(
        delta is not None and len(delta) == 1 and delta[0].path == consumption_path and delta[0].status == "A"
        and delta[0].new_mode == "100644",
        "CP12", "the metadata commit is not exactly the added Consumption",
    )

    progress.append("CP13")
    # CP13 - the metadata commit's tree still holds the Run and the registration as proven
    for relative in record_paths:
        _require(at_km.blob_id(relative) == at_parent.blob_id(relative), "CP13", f"{km} does not hold {relative} as the parent holds it")
    _require(at_km.entry(paths.gate_rel(review_run_id, planning.INVALIDATION_GENERATION)) is None
             and not at_km.supersession_exists(receipt_id), "CP13", f"{km} holds an invalidation of the Receipt")
    registration_blobs = gitcmd.tree_entries(repo, registration, list(rr.registration_paths(material)))
    km_blobs = gitcmd.tree_entries(repo, km, list(rr.registration_paths(material)))
    _require(
        registration_blobs is not None and km_blobs is not None
        and {e.path: e.oid for e in registration_blobs} == {e.path: e.oid for e in km_blobs},
        "CP13", "the metadata commit's registration paths are not the registration commit's",
    )
