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
from . import committed, history, p4, paths, planning, records, serialize

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
    # P6 (ORCH-RB6-1): every policy commit (Kp) of the history is proven too. A Workline Kp always follows its
    # Policy Review Run's Candidate snapshot, so the unchanged snapshot fast path already reaches here; a legacy-only
    # push still pays exactly its one fast-path read. One history read lists every policy change and its adders.
    try:
        adders = policy_change_adders(Path(repo), commit)
    except (ValidationError, StopError, CommittedReadError) as exc:
        return f"the policy changes of {commit}'s history cannot be read ({exc})"
    for change_path in sorted(adders):
        failed = committed_policy_proof(Path(repo), commit, change_path, adders[change_path])
        if failed is not None:
            item, detail = failed
            return f"the policy commit adding {change_path} is not proven for {commit}: {item} fails ({detail})"
    return None


# --------------------------------------------------------------------------- P6 policy commits (ORCH-RB6-1)

def policy_change_adders(repo: Path, commit: str) -> dict[str, list[str]]:
    """Every policy change record path a commit of ``commit``'s history adds, with the commits that add it.

    One add-history read over the policy change directory (ORCH-RB6-1-R10);
    each change record is one policy commit (Kp).
    """
    directory = f"{paths.POLICY_DIR}/{paths.POLICY_CHANGES}"
    found: dict[str, list[str]] = {}
    for adding, names in committed.added_in_history(repo, commit, [directory]):
        for name in names:
            if name.startswith(directory + "/"):
                found.setdefault(name, []).append(adding)
    return found


def committed_policy_proof(repo: Path, commit: str, change_path: str,
                           adders: list[str] | None = None) -> tuple[str, str] | None:
    """The committed proof of one policy commit (Kp) at ``commit``, from committed objects alone; ``(item, detail)``
    of the first item that fails, ``None`` when every item holds.

    The C-2(Kp) / C-2(Km) facts a later push re-proves without the owner's
    runtime record (P6 §30.20 "no push before proof"; the P2 §18.8 committed
    proof's method):

    ```text
    PK1  one commit of the history adds the change record; it has one parent P
    PK2  its delta is exactly the change record (A) and the Profile (A / M), plain files
    PK3  the change record is exactly the change record of the Candidate the Run's snapshot at P holds, of its Run,
         Receipt and the baseline record it binds
    PK4  the committed Profile is exactly the reviewed after Profile and round-trips through the canonical loader
    PK5  P holds exactly the reviewed before Profile
    PK6  P holds the Policy Review Run whole and sealed: Policy Review kind / target / contract, discovery ->
         adjudication -> seal, every accepted task's provenance, generation 5 bound field by field to its Receipt
         and to the Policy Change stage, the G1 Candidate the snapshot's
    PK7  no invalidation or Supersession of the Receipt in the history, and no Consumption of it at Kp
    PK8  a Consumption of the Receipt the pushed commit holds is the one v3 Policy Consumption, bound to the Receipt,
         the Run, the change, Kp and P (absent: Kp alone is published, as its own owner publishes it, §30.20)
    PK9  its metadata commit Km: the one commit adding it, on Kp's clean descendant, exactly the consumed Run summary
         and the Consumption, the summary valid for that Consumption, Kp's change record and Profile unchanged
    ```

    Anything that cannot be read or answered is no proof: the item in progress fails (ORCH-RB6-1-R10).
    """
    progress = ["PK1"]
    try:
        _prove_policy(repo, commit, change_path, adders, progress)
    except _Fail as failed:
        return failed.item, failed.detail
    except Exception as exc:  # anything unanswerable is no proof: the item under evaluation fails
        return progress[-1], f"{type(exc).__name__}: {exc}"
    return None


def _prove_policy(repo: Path, commit: str, change_path: str, adders: list[str] | None, progress: list[str]) -> None:
    from . import policy
    from .validate import GATE_RECEIPT_BINDING, RECEIPT_CONSUMPTION_BINDING

    # PK1 - the policy commit and its one parent
    kps = adders if adders is not None else _guard("PK1", lambda: committed.adding_commits(repo, commit, change_path))
    _require(len(kps) == 1, "PK1", f"{change_path} is added by {len(kps)} commits of the history, not exactly one")
    kp = kps[0]
    parents = gitcmd.commit_parents(repo, kp) or []
    _require(len(parents) == 1, "PK1", f"the policy commit {kp} has {len(parents)} parents")
    parent = parents[0]

    progress.append("PK2")
    at_kp = _guard("PK2", lambda: committed.CommittedReviewStore(repo, kp))
    change_id = change_path.rsplit("/", 1)[-1][: -len(".yaml")]
    change = _guard("PK2", lambda: at_kp.read_policy_change(change_id))
    delta = gitcmd.commit_delta(repo, parent, kp)
    _require(delta is not None, "PK2", f"Git cannot show the delta of {kp}")
    wanted = {change_path: "A", paths.POLICY_PROFILE_REL: "A" if change["before_profile_digest"] is None else "M"}
    _require({item.path: item.status for item in delta} == wanted and all(item.new_mode == "100644" for item in delta),
             "PK2", f"{kp} is not exactly the change record and the Profile")

    progress.append("PK3")
    at_parent = _guard("PK3", lambda: committed.CommittedReviewStore(repo, parent))
    snapshot = _guard("PK3", lambda: at_parent.read_candidate_snapshot(str(change["candidate_hash"])))
    candidate = dict(snapshot.material or {})
    rebuilt = _guard("PK3", lambda: policy.change_record(
        candidate, review_run_id=str(change["review_run_id"]), receipt_id=str(change["receipt_id"]),
        baseline_record=change["global_baseline"]))
    _require(serialize.canonical_bytes(rebuilt) == gitcmd.blob_at(repo, kp, change_path), "PK3",
             f"{change_path} is not exactly the change record of the Candidate it names")

    progress.append("PK4")
    problem = _guard("PK4", lambda: policy.persisted_projection_problem(
        candidate["after_profile"], gitcmd.blob_at(repo, kp, paths.POLICY_PROFILE_REL),
        policy.bound_global_settings(change["global_baseline"])))
    _require(problem is None, "PK4", problem or "")

    progress.append("PK5")
    before = gitcmd.blob_at(repo, parent, paths.POLICY_PROFILE_REL)
    before_digest = None if before is None else serialize.digest_of_text(before.decode("utf-8"))
    _require(before_digest == candidate["before_profile"]["digest"], "PK5",
             f"the parent of {kp} does not hold the exact reviewed before Profile")

    progress.append("PK6")
    review_run_id, receipt_id = str(change["review_run_id"]), str(change["receipt_id"])
    chain = _guard("PK6", lambda: at_parent.gate_chain(review_run_id))
    _require(chain is not None, "PK6", f"the parent of {kp} holds no generation of {review_run_id}")
    first, sealed = chain.generations[0], chain.latest
    _require(len(chain.generations) == p4.SEAL_GENERATION and not p4.chain_problems(chain)
             and p4.shape_of(chain) == p4.SHAPE_SEAL and sealed.sealed and sealed.receipt_id == receipt_id,
             "PK6", f"the Run's chain at {parent} is not discovery -> adjudication -> seal with {receipt_id}")
    contracts = _guard("PK6", lambda: p4.run_contracts(at_parent, chain))
    _require(contracts == {policy.POLICY_CHANGE_CONTRACT} and first.review_kind == policy.REVIEW_KIND
             and first.target_identity == policy.TARGET_IDENTITY
             and sealed.authorized_operation_stage == policy.AUTHORIZED_OPERATION_STAGE
             and first.candidate_hash == change["candidate_hash"] == policy.candidate_hash(candidate),
             "PK6", "the Run is not the Policy Review of the change's Candidate under the Policy Change stage")
    for task in sealed.accepted_tasks:
        accepted = int(chain.accepted_at(str(task["task_id"])) or 0)
        problems = _guard("PK6", lambda: at_parent.provenance_problems(task, accepted))
        _require(not problems, "PK6", "; ".join(message for _, message in problems))
    receipt = _guard("PK6", lambda: at_parent.read_receipt(receipt_id))
    for gate_field, receipt_field in GATE_RECEIPT_BINDING:
        _require(getattr(sealed, gate_field) == getattr(receipt, receipt_field), "PK6",
                 f"the Receipt's {receipt_field} is not generation 5's {gate_field}")

    progress.append("PK7")
    invalidations = _guard("PK7", lambda: committed.added_in_history(
        repo, commit, [paths.gate_rel(review_run_id, p4.INVALIDATION_GENERATION), paths.supersession_rel(receipt_id)]))
    _require(not invalidations, "PK7", f"{commit}'s history adds a generation 6 or a Supersession of the Receipt")
    _require(not any(found.receipt_id == receipt_id for found in _guard("PK7", at_kp.consumptions)), "PK7",
             f"{kp} holds a Consumption of its own Receipt")

    progress.append("PK8")
    at_commit = _guard("PK8", lambda: committed.CommittedReviewStore(repo, commit))
    naming = [found for found in _guard("PK8", at_commit.consumptions) if found.receipt_id == receipt_id]
    if not naming:
        return  # Kp alone, proven: what its own owner publishes before its Consumption (§30.20)
    _require(len(naming) == 1, "PK8", f"{commit} holds {len(naming)} Consumptions of the Receipt")
    consumption = naming[0]
    _require(isinstance(consumption, records.PolicyConsumption), "PK8", "the Consumption is not a Policy Consumption")
    for name in RECEIPT_CONSUMPTION_BINDING:
        _require(getattr(receipt, name) == getattr(consumption, name), "PK8",
                 f"the Consumption's {name} is not the Receipt's")
    persisted = consumption.persisted_policy
    _require(
        persisted.get("policy_change_id") == change_id and persisted.get("policy_commit") == kp
        and persisted.get("policy_parent") == parent
        and persisted.get("after_profile_digest") == change["after_profile_digest"]
        and persisted.get("before_profile_digest") == change["before_profile_digest"]
        and persisted.get("global_baseline_digest") == change["global_baseline_digest"]
        and isinstance(persisted.get("branch"), str) and persisted["branch"].startswith("refs/heads/"),
        "PK8", "the Consumption's persisted policy does not bind the change, its policy commit and its parent")

    progress.append("PK9")
    consumption_path = paths.consumption_rel(consumption.consumption_id)
    summary_path = paths.history_run_rel(review_run_id)
    metadata = [listed for listed, names in _guard("PK9", lambda: committed.added_in_history(repo, commit, [consumption_path]))
                if consumption_path in names]
    _require(len(metadata) == 1, "PK9", f"{len(metadata)} commits add the Consumption")
    km = metadata[0]
    km_parents = gitcmd.commit_parents(repo, km) or []
    _require(len(km_parents) == 1, "PK9", f"{km} does not have exactly one parent")
    q = km_parents[0]
    _require((q == kp or gitcmd.descends_from(repo, q, kp) is True)
             and (q == kp or gitcmd.commits_touching(repo, kp, q, [change_path, paths.POLICY_PROFILE_REL]) == []),
             "PK9", f"{km}'s parent is not the policy commit or its clean descendant")
    km_delta = gitcmd.commit_delta(repo, q, km)
    _require(km_delta is not None and sorted(item.path for item in km_delta) == sorted([consumption_path, summary_path])
             and all(item.status == "A" and item.new_mode == "100644" for item in km_delta),
             "PK9", "the metadata commit is not exactly the added Run summary and Consumption")
    at_km = _guard("PK9", lambda: committed.CommittedReviewStore(repo, km))
    _require(at_km.blob_id(consumption_path) == at_commit.blob_id(consumption_path), "PK9",
             "the Consumption the metadata commit added is not the one the published commit holds")
    summary = _guard("PK9", lambda: at_km.read_history(paths.HISTORY_RUNS, review_run_id))
    problems = _guard("PK9", lambda: history.run_summary_problems(at_km, summary))
    _require(not problems and summary.durable_disposition == history.DISPOSITION_CONSUMED
             and summary.consumption_id == consumption.consumption_id,
             "PK9", "the Run summary does not validate against the exact Consumption")
    for path in (change_path, paths.POLICY_PROFILE_REL):
        _require(gitcmd.blob_at(repo, km, path) == gitcmd.blob_at(repo, kp, path), "PK9",
                 f"{km} does not hold the policy commit's {path}")


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
        if _replaced_by_successor(repo, commit, candidate_hash):
            continue  # G-2: a P4 predecessor positively replaced, with no registration of its own
        runs.append(RegisteredRun(candidate_hash, material, wanted, registering))
    return runs


def _replaced_by_successor(repo: Path, commit: str, candidate_hash: str) -> bool:
    """G-2: whether the one Run of ``candidate_hash`` at ``commit`` is a P4 predecessor positively replaced.

    Only the committed objects of ``commit`` are read. The five conditions are
    :func:`workline.review.p4.proven_successor`'s; anything short of them -
    including anything unreadable - is no proof, and the snapshot stays a
    registration Run the committed planning proof must prove (fail closed).
    """
    try:
        at_commit = committed.CommittedReviewStore(repo, commit)
        runs = at_commit.runs_with_candidate(candidate_hash)
        if len(runs) != 1:
            return False
        chain = at_commit.gate_chain(runs[0])
        return chain is not None and p4.proven_successor(at_commit, runs[0], chain) is not None
    except (ValidationError, StopError, CommittedReadError):
        return False


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
    contracts = _guard("CP2", lambda: p4.run_contracts(at_parent, chain)) if chain is not None else {None}
    # the Run's contract is the one its generation-1 TaskInputs bind, never its shape (§27.3)
    p4_run = contracts == {planning.P4_CONTRACT}
    if p4_run:
        seal_generation, invalidation_generation = p4.SEAL_GENERATION, p4.INVALIDATION_GENERATION
        _require(
            chain is not None and len(chain.generations) == p4.SEAL_GENERATION and not p4.chain_problems(chain)
            and p4.shape_of(chain) == p4.SHAPE_SEAL,
            "CP2", f"the P4 Run's chain at {parent} is not discovery -> adjudication -> seal (generations 1-5)",
        )
        first, third = chain.generations[0], chain.generations[p4.SEAL_GENERATION - 1]
    else:
        seal_generation, invalidation_generation = planning.SEAL_GENERATION, planning.INVALIDATION_GENERATION
        _require(chain is not None and contracts <= {None} and len(chain.generations) == planning.SEAL_GENERATION, "CP2",
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
    if p4_run:
        for task in third.accepted_tasks:
            accepted = int(chain.accepted_at(str(task["task_id"])) or 0)
            problems = _guard("CP3", lambda: at_parent.provenance_problems(task, accepted))
            _require(not problems, "CP3", "; ".join(message for _, message in problems))
    else:
        problems = _guard("CP3", lambda: at_parent.provenance_problems(descriptor, 1))
        _require(not problems, "CP3", "; ".join(message for _, message in problems))
    _require(snapshot.material == material, "CP3", "the snapshot at the parent is not the Run's Candidate")
    if p4_run:
        problems3 = []
        for task in p4.discovery_tasks(chain):
            problems3 += planning.task_input_problems_p4(
                _guard("CP3", lambda: at_parent.read_task_input(str(task["task_id"]))), material, first.candidate_hash,
                first.review_context_hash,
            )
    else:
        problems3 = planning.task_input_problems(
            task_input, material, first.candidate_hash, first.review_context_hash, first.effective_policy_hash
        )
    _require(not problems3, "CP3", "; ".join(problems3))
    _require(first.review_kind == material["review_kind"], "CP3", "the Run's kind is not the Candidate's")
    _require(first.target_identity == rr.candidate_target(material), "CP3", "the Run's target is not the Candidate's")
    context = task_input.request_envelope.get("context")

    progress.append("CP4")
    # CP4 - the same Run records at C, and no invalidation anywhere in C's history
    if p4_run:
        record_paths = _guard("CP4", lambda: rr.p4_run_record_paths(at_parent, review_run_id, chain))
    else:
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
        repo, commit, [paths.gate_rel(review_run_id, invalidation_generation), paths.supersession_rel(receipt_id)]
    ))
    _require(not invalidations, "CP4",
             f"{commit}'s history adds a generation {invalidation_generation} or a Supersession of the Receipt")

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
    failed = rr.semantic_problem(material, view_parent, view_registration)
    _require(failed is None, "CP6", failed[1] if failed else "")
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
        consumption.review_run_id == review_run_id and consumption.review_generation == seal_generation
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
    if p4_run:
        owned = rr.p4_planning_owned_paths(
            rr._Run(review_run_id, task_id, receipt_id, consumption.consumption_id), chain, material, at_parent
        )
    else:
        owned = rr.planning_owned_paths(review_run_id, material, task_id, receipt_id, consumption.consumption_id)
    touching = gitcmd.commits_touching(repo, registration, q, owned)
    _require(touching == [], "CP11", "a commit between the registration and the metadata commit touches a planning-owned path")
    at_km = _guard("CP11", lambda: committed.CommittedReviewStore(repo, km))
    _require(at_km.blob_id(consumption_path) is not None and at_km.blob_id(consumption_path) == at_commit.blob_id(consumption_path),
             "CP11", "the Consumption the metadata commit added is not the one the published commit holds")

    progress.append("CP12")
    # CP12 - the metadata commit carries the Consumption alone (v1 / P4-only, byte for byte as frozen); a P5 Run -
    # by the policy its own committed TaskInputs store (GAP-A, §28.6) - carries its Run summary and the Consumption
    delta = gitcmd.commit_delta(repo, q, km)
    history_contract = _guard("CP12", lambda: p4.run_history_contract(at_parent, chain)) if p4_run else None
    if history_contract is None:
        _require(
            delta is not None and len(delta) == 1 and delta[0].path == consumption_path and delta[0].status == "A"
            and delta[0].new_mode == "100644",
            "CP12", "the metadata commit is not exactly the added Consumption",
        )
    else:
        summary_path = paths.history_run_rel(review_run_id)
        _require(
            delta is not None and sorted(item.path for item in delta) == sorted([consumption_path, summary_path])
            and all(item.status == "A" and item.new_mode == "100644" for item in delta),
            "CP12", "the metadata commit is not exactly the added Run summary and Consumption",
        )
        summary = _guard("CP12", lambda: at_km.read_history(paths.HISTORY_RUNS, review_run_id))
        problems = _guard("CP12", lambda: history.run_summary_problems(at_km, summary))
        _require(not problems and summary.durable_disposition == history.DISPOSITION_CONSUMED
                 and summary.consumption_id == consumption.consumption_id,
                 "CP12", "the Run summary does not validate against the exact Consumption")

    progress.append("CP13")
    # CP13 - the metadata commit's tree still holds the Run and the registration as proven
    for relative in record_paths:
        _require(at_km.blob_id(relative) == at_parent.blob_id(relative), "CP13", f"{km} does not hold {relative} as the parent holds it")
    _require(at_km.entry(paths.gate_rel(review_run_id, invalidation_generation)) is None
             and not at_km.supersession_exists(receipt_id), "CP13", f"{km} holds an invalidation of the Receipt")
    registration_blobs = gitcmd.tree_entries(repo, registration, list(rr.registration_paths(material)))
    km_blobs = gitcmd.tree_entries(repo, km, list(rr.registration_paths(material)))
    _require(
        registration_blobs is not None and km_blobs is not None
        and {e.path: e.oid for e in registration_blobs} == {e.path: e.oid for e in km_blobs},
        "CP13", "the metadata commit's registration paths are not the registration commit's",
    )
