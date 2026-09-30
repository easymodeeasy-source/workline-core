"""START's review-v1 Work path: the entry, the Work Candidate and its Review Run (P3 F1 / F2 / F3 §5.1).

START stays the operation owner. Selecting review-v1 (``start(..., review=WorkReview(...))``)
makes Review a subordinate authorization gate inside START's own operation: START takes
the lock, opens and owns the mutation, runs the executor, decides every Git stage, and opens
the Run's generation mutations under its own lock. Review records what was reviewed and what
was authorized, and progresses nothing (F1 §6.3, F2 §8.3).

This module is START's, not Review's. The records it writes, and what they mean, are
:mod:`workline.review.work_review`'s; the object-driven commits are
:mod:`workline.review.workcommit`'s; ownership is :mod:`workline.review.ownership`'s.

What it implements, in the order F3 §5.1 freezes (steps 1 ... 16):

```text
 1 - 2b  the entry, before the lock: the selector, the platform's immutable create, the
         publication capability where there is a remote, the transform entry refusal
 3       under the lock, before the mutation opens: activation (the F1-D3 marker matrix is START's own)
 4       the mutation opened with both markers                      (START itself)
 5a - 6  normalization, spelling, reserved ownership, containment and the bound witness,
         then the ownership assertion - nothing durable before 6
 7 - 9   completion_precheck, dirty separability, the pinned persistence preflight
 9a      S-c0: the entry events, committed alone, only when uncommitted
10 - 12  the Work Candidate, its snapshot material, the resulting tree, Context v2, and the
         isolated verification of the exact Candidate
13 - 16  generation 1 (accept), the reviewer, generation 2 (settle), the checkout-capability
         decision, and only on "capable" generation 3 (seal, issuing the Receipt)
```

Every commit this path makes is ``review-v1-work-local-v2`` and commit-only: a review-v1
Work mutation pushes nothing before C-2 (F3 §4.3), which is Batch D's.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from typing import TYPE_CHECKING, Any

from . import gitcmd, gitops
from .errors import ReconcileRequired, StopError, ValidationError
from .mutation import Effect, Mutation, MutationController, WriteScope, abandon_on_stop
from .ops import stage_name
from .review import (
    attributes,
    checkout,
    closure,
    fsafe,
    gate,
    ownership,
    records,
    resulting_tree,
    serialize,
    work_checkout,
    work_context,
    work_invocation,
    work_review,
    work_verify,
    workcommit,
)
from .review import hermetic as hermetic_module
from .review import paths as review_paths
from .review.hermetic import HermeticGit
from .review.store import ReviewStore
from .state import ProjectView
from .store import Entity, Event, ProjectStore

if TYPE_CHECKING:  # pragma: no cover
    from .start import _Session

#: START is the owner of every mutation of this path, generation mutations included (F1 §6.3).
OWNER = "start"
#: What the execution lock's holder description says on the review-v1 path: the static marker, no caller value.
LOCK_DETAILS = {"review_contract": work_review.REVIEW_CONTRACT}
EVENT_LOG = workcommit.EVENT_LOG

#: The generation mutation's stages - the same names the P2 generation mutations use, so the
#: one dispatch that commits them (roadmap_review._finish_generation, C3-1) reads them unchanged.
STAGE_GENERATION = "review-generation"
STAGE_GENERATION_COMMIT = "review-generation-commit"
OPERATION_GENERATION = "review-generation"
TRANSITIONS = {1: "accept", 2: "settle", 3: "seal"}

#: The mutation runtime metadata a refused authorization is carried in (F3 §7.9.5): never a Review record.
NOTE_SEAL_REFUSAL = "review_seal_refusal"


# --------------------------------------------------------------------------- small readers


def _head(git: HermeticGit) -> tuple[str, str]:
    """HEAD's full branch ref and the commit it names, through class B. Detached HEAD never reaches here (§7.1.5)."""
    ref = workcommit._head_ref(git)
    if ref is None:
        raise StopError("repository is in detached HEAD state", code="detached_head")
    commit = workcommit.ref_value(git, ref)
    if commit is None:
        raise StopError(f"{ref} names no commit, so a review-v1 Work has no committed base: STOP",
                        code="review_base_uncommitted")
    return ref, commit


def _reconcile(message: str, reason: str | None = None) -> ReconcileRequired:
    return ReconcileRequired(f"{message}: reconcile required", reason=reason)


# --------------------------------------------------------------------------- 1 - 2b: the entry, before the lock


def entry_gate(store: ProjectStore, review: object) -> work_review.WorkReview:
    """F3 §5.1 steps 1, 2a and 2b: everything a review-v1 START refuses before the lock, with nothing written.

    ``review_contract_invalid``  the selector (F1-D1)
    ``review_create_unsupported`` the platform cannot keep an immutable Review create inside the Project
    ``review_git_unsupported``   a Project with a remote on a Git below P2_PUBLICATION_GIT_MIN (§12.4), or
                                 a Git that cannot be shown to honour the attribute pin (§7.7)
    ``review_git_transform``     the attribute source of HEAD - PRE_S_C0_BASE's source - fails the
                                 universal predicate (§7.4, §7.8)
    """
    checked = work_review.validate_work_review(review)
    if not fsafe.immutable_create_supported():
        raise StopError(
            "review-v1 Work writes immutable Review records, which this platform cannot keep inside the Project; "
            "nothing was begun (legacy START is unaffected)",
            code="review_create_unsupported",
        )
    version = gitcmd.running_git_version()
    if not gitcmd.version_meets(version, gitcmd.P2_PUBLICATION_GIT_MIN) and _has_remote(store):
        found = "of unknown version" if version is None else gitcmd.version_text(version)
        raise StopError(
            f"the running Git is {found}; a review-v1 Work START in a Project with a remote needs "
            f"P2_PUBLICATION_GIT_MIN ({gitcmd.version_text(gitcmd.P2_PUBLICATION_GIT_MIN)}) or newer; nothing was begun",
            code="review_git_unsupported",
        )
    git = hermetic_module.enter(store)
    _, head = _head(git)
    attributes.require_work_attribute_source(store, git, head)
    attributes.require_attribute_pin_capability(store, git)
    return checked


def _has_remote(store: ProjectStore) -> bool:
    from .destination import ensure_push_destination

    return ensure_push_destination(store) is not None


# --------------------------------------------------------------------------- 3: activation and the marker matrix


@dataclass(frozen=True)
class Activation:
    """The Project's Work-terminal activation, read and proven at entry (F1 §6.4, §10.1)."""

    record: records.WorkTerminalActivation
    record_digest: str

    def binding(self) -> dict[str, str]:
        return work_context.activation_binding(self.record_digest, self.record.activation_base_head)


def activation_prefix_digest(git: HermeticGit, commit: str, count: int) -> str | None:
    """``work-terminal-activation-digest-v1`` over the first ``count`` Events of ``commit``'s event log (F1 §9.1).

    Read from the committed blob through class B, parsed exactly as the live
    Event reader parses (blank physical lines ignored, CRLF and CR read as LF),
    each record rendered as canonical JSON - keys sorted by code point, ``,``
    and ``:`` separators, UTF-8 without ASCII escaping, one LF after each. None
    when the log cannot be read, a line is not an Event, or fewer than
    ``count`` Events exist: the prefix is then unprovable, never legacy.
    """
    found = git.run_bytes("cat-file", "blob", f"{commit}:{EVENT_LOG}")
    if not found.ok:
        return None
    try:
        text = found.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None
    parsed: list[dict[str, Any]] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(record, dict) or not all(isinstance(record.get(key), str) for key in ("id", "type", "entity", "at")):
            return None
        try:
            parsed.append(Event.from_record(record).to_record())
        except ValidationError:
            return None
    if len(parsed) < count:
        return None
    try:
        canonical = b"".join(
            json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
            + b"\n"
            for record in parsed[:count]
        )
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(canonical).hexdigest()


def require_activation(store: ProjectStore) -> Activation:
    """F1 §6.4: under the lock, before the mutation is opened.

    Absent is ``review_not_activated``; a malformed record or an unknown
    operation contract is the reader's own ``ValidationError``; a prefix digest
    that does not reproduce from HEAD's committed event log fails closed, and
    is never a legacy fallback.
    """
    record = ReviewStore(store).read_activation()
    if record is None:
        raise StopError(
            "this Project has not activated review-v1 Work terminalization, so a review-v1 START is refused; nothing "
            "was begun (legacy START is unaffected)",
            code="review_not_activated",
        )
    git = hermetic_module.enter(store)
    _, head = _head(git)
    digest = activation_prefix_digest(git, head, record.legacy_event_count)
    if digest is None or digest != record.legacy_event_prefix_sha256:
        raise _reconcile(
            f"the activation record's legacy event prefix ({record.legacy_event_count} Events) does not reproduce from "
            f"{head}'s committed event log, so which Events are pre-activation cannot be shown; nothing was begun"
        )
    return Activation(record, serialize.digest(record.to_record()))


def invocation(work_id: str, mode: str) -> dict[str, Any]:
    """F1-D2: the live invocation plus exactly the two markers, written at the intent's first durable write."""
    return {"operation": "start", "work_id": work_id, "mode": mode, **work_invocation.markers()}


# --------------------------------------------------------------------------- commit-only stages (F3 §4.3)


def commit_stage(session: "_Session", prefix: str, message: str, *, plan_class: str = workcommit.CLASS_WORK_STAGE) -> None:
    """A review-v1 Work Git stage: exactly one ``review-v1-work-local-v2`` commit, never a push (F3 §4.3, §11.3).

    What it commits is decided by the plan - the parent object plus the
    effects this mutation recorded since its last commit - never by what the
    working tree holds, and nothing is recorded when the plan changes nothing.
    """
    mutation = session.mutation
    stage = stage_name(mutation, prefix)
    if not mutation.has_stage(stage):
        effect = workcommit.stage_commit_effect(mutation, message, plan_class=plan_class)
        if effect is None:
            return
        gitops.ensure_separable(gitops.record_preexisting_dirty(mutation, session.store.root), list(effect.payload["paths"]))
        mutation.add_effects(stage, [effect])
    mutation.apply()


# --------------------------------------------------------------------------- the declared base (F2 §5.3)


def committed_view_at(store: ProjectStore, git: HermeticGit, commit: str) -> ProjectView:
    """``ProjectView`` as of ``commit``, read from raw blobs through class B by the production loader.

    The same materialization :mod:`workline.committed_view` performs, with every
    Git read in the hermetic class B environment, so a replacement object or an
    inherited ``GIT_*`` variable cannot stand in for the base the Candidate
    declares (F3 §7.1.9).
    """
    import secrets
    import shutil

    from .committed_view import is_materialized_path

    tree = resulting_tree.root_tree_id(git, commit)
    entries = resulting_tree.tree_entries(git, tree)
    directory = store.root / review_paths.RUNTIME_PROOFS_DIR / secrets.token_hex(8)
    directory.mkdir(parents=True, exist_ok=False)
    try:
        for path, entry in entries.items():
            if not is_materialized_path(path):
                continue
            if entry.type != "blob" or entry.mode != "100644":
                raise StopError(f"{commit} holds {path} as {entry.type} {entry.mode}, not a regular file blob",
                                code="review_base_uncommitted")
            blob = git.run_bytes("cat-file", "blob", entry.oid)
            if not blob.ok:
                raise StopError(f"Git cannot read the blob {entry.oid} {commit} holds at {path}",
                                code="review_base_uncommitted")
            target = directory.joinpath(*path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob.stdout)
        return ProjectView.load(ProjectStore(directory))
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def declared_base(store: ProjectStore, git: HermeticGit, base_commit: str, branch: str, work_id: str) -> dict[str, Any]:
    """F2 §5.3, read from the committed state of ``base_commit`` through the canonical loader, never the working tree."""
    from .start import read_obligations

    view = committed_view_at(store, git, base_commit)
    work = view.works.get(work_id)
    if work is None:
        raise StopError(f"{work_id} is not in {base_commit}'s committed state, so the Candidate has no declared base",
                        code="review_base_uncommitted")
    tracked = sorted(path for path, entry in resulting_tree.tree_entries(git, resulting_tree.root_tree_id(git, base_commit)).items()
                     if entry.type == "blob")
    dependencies = sorted(view.relations_to(work_id, "requires_completion"), key=lambda relation: relation.id)
    obligations = sorted(read_obligations(store, view, work_id, tracked=tracked), key=lambda relation: relation.id)
    return {
        "base_commit": base_commit,
        "branch": branch,
        "work": {
            "work_id": work_id,
            "display": work.display,
            "name": work.name,
            "desired_state": work.meta.get("desired_state"),
            "phase_id": work.phase_id,
            "state": view.work_state(work_id).state,
        },
        "dependencies": [
            {"relation_id": relation.id, "from": relation.from_id, "from_state": view.entity_state_label(relation.from_id)}
            for relation in dependencies
        ],
        "read_obligations": [{"relation_id": relation.id, "type": relation.type, "to": relation.to} for relation in obligations],
    }


# --------------------------------------------------------------------------- the Run's identity and state


@dataclass
class WorkRun:
    """The Work Review Run of this START's one completion, and the identifiers it reserved."""

    work_id: str
    review_run_id: str
    task_id: str
    receipt_id: str
    #: The freeze's material, present only between a new Run's freeze and its generation 1.
    frozen: dict[str, Any] | None = None


def run_key(work_id: str) -> str:
    return gate.review_run_key(work_review.REVIEW_KIND, work_id)


def reserve_run(mutation: Mutation, work_id: str) -> WorkRun:
    run_id = mutation.reserve_id(run_key(work_id), "review_run")
    task_id = mutation.reserve_id(gate.review_task_key(run_id, work_review.TASK_SLOT), "review_task")
    receipt_id = mutation.reserve_id(gate.review_receipt_key(run_id, work_review.SEAL_GENERATION), "review_receipt")
    return WorkRun(work_id, run_id, task_id, receipt_id)


def run_in_flight(mutation: Mutation) -> WorkRun | None:
    """The Run this START already began, once anything of it is durable; None before generation 1 exists.

    Read from the mutation's own reservations and the canonical chain: a Run
    whose generation 1 is committed (or whose generation mutation is pending)
    is continued from its records and never frozen again. A mutation holds at
    most one Work Run - one completion per review-v1 mutation (F3 §4.5, §11.3.1).
    """
    prefix = f"review-run:{work_review.REVIEW_KIND}:"
    keys = [key for key in (mutation.record.get("reserved_ids") or {}) if str(key).startswith(prefix)]
    if not keys:
        return None
    if len(keys) > 1:
        raise _reconcile(f"START mutation {mutation.id} reserved more than one Work Review Run ({sorted(keys)})")
    work_id = keys[0][len(prefix):]
    run_id = mutation.reserved(keys[0])
    if not isinstance(run_id, str):
        return None
    begun = gate.pending_generation_mutations(mutation.store, run_id) or ReviewStore(mutation.store).next_generation(run_id) > 1
    if not begun:
        return None
    task_id = mutation.reserved(gate.review_task_key(run_id, work_review.TASK_SLOT))
    receipt_id = mutation.reserved(gate.review_receipt_key(run_id, work_review.SEAL_GENERATION))
    if not isinstance(task_id, str) or not isinstance(receipt_id, str):
        raise _reconcile(f"START mutation {mutation.id} holds Work Review Run {run_id} without its task or Receipt id")
    return WorkRun(work_id, run_id, task_id, receipt_id)


# --------------------------------------------------------------------------- generation mutations (R3, C3-1)


def _generation_invocation(mutation: Mutation, run: WorkRun, generation: int, gate_record: records.GateGeneration,
                           receipt_id: str | None, basis: str, branch: str) -> dict[str, Any]:
    return {
        "operation": OPERATION_GENERATION,
        "review_contract": work_review.REVIEW_CONTRACT,
        "start_mutation_id": mutation.id,
        "review_kind": work_review.REVIEW_KIND,
        "review_run_id": run.review_run_id,
        "generation": generation,
        "transition": TRANSITIONS[generation],
        "candidate_hash": gate_record.candidate_hash,
        "review_context_hash": gate_record.review_context_hash,
        "effective_policy_hash": gate_record.effective_policy_hash,
        "obligation_digest": gate_record.obligation_digest,
        "receipt_id": receipt_id,
        "persistence_basis": basis,
        "persistence_branch": branch,
    }


def _finish_generation(store: ProjectStore, gen: Mutation) -> None:
    """The one generation dispatch (``F3`` §7.1.7, C3-1): its durable ``review_kind`` selects the Work primitive."""
    from .roadmap_review import _finish_generation as finish

    finish(store, gen)


def _start_generation(
    session: "_Session", run: WorkRun, generation: int, gate_record: records.GateGeneration,
    extra: list[tuple[str, dict[str, Any]]], base: dict[str, Any], *, receipt_id: str | None = None,
) -> None:
    """Open, record, commit and prove persisted the generation mutation writing ``gate_record`` (and ``extra``)."""
    store, mutation = session.store, session.mutation
    scope = gate.next_generation_scope(store, run.review_run_id)
    if scope.generation != generation:
        raise _reconcile(
            f"Work Review Run {run.review_run_id}'s next generation is {scope.generation}, and START is at generation "
            f"{generation}",
            "review_chain_invalid",
        )
    writes = [(scope.gate_path, gate_record.to_record())] + list(extra)
    if generation == records.FIRST_GENERATION:
        writes = list(extra) + [(scope.gate_path, gate_record.to_record())]
    invocation_record = _generation_invocation(mutation, run, generation, gate_record, receipt_id, base["base_commit"],
                                               base["branch"])
    record_paths = [path for path, _ in writes]
    gen = MutationController(store).open(OWNER, invocation_record,
                                         WriteScope(files=tuple(scope.files) + tuple(path for path, _ in extra)))
    with abandon_on_stop(gen):
        gitops.record_preexisting_dirty(gen, store.root)
        gitops.ensure_separable_before_effects(gen, record_paths)
        if not gen.has_stage(STAGE_GENERATION):
            gate.require_committable(store, record_paths)
            gen.add_effects(STAGE_GENERATION, [
                Effect.create_file(path, serialize.canonical_text(record)) for path, record in writes
            ])
    _finish_generation(store, gen)


def resolve_pending_generation(session: "_Session", run: WorkRun) -> None:
    """R2 §4: a pending generation mutation of this Run is resumed first, and nothing else is."""
    store, mutation = session.store, session.mutation
    pending = gate.pending_generation_mutations(store, run.review_run_id)
    if not pending:
        return
    if len(pending) > 1:
        raise _reconcile(f"Work Review Run {run.review_run_id} has {len(pending)} pending generation mutations",
                         "review_generation_owner_conflict")
    record = pending[0]
    found = record.get("invocation") or {}
    if (
        record.get("owner") != OWNER
        or found.get("operation") != OPERATION_GENERATION
        or found.get("review_kind") != work_review.REVIEW_KIND
        or found.get("start_mutation_id") != mutation.id
        or found.get("review_run_id") != run.review_run_id
    ):
        raise _reconcile(
            f"the pending generation mutation {record.get('mutation_id')} of Work Review Run {run.review_run_id} is not "
            f"this START mutation's ({mutation.id})",
            "review_generation_owner_conflict",
        )
    gen = MutationController(store).open(OWNER, found, WriteScope.from_record(record.get("write_scope") or {}))
    if not gen.effects:
        gen.abandon()
        return
    generation = found.get("generation")
    try:
        chain = ReviewStore(store).gate_chain(run.review_run_id)
    except ValidationError as exc:
        raise _reconcile(f"Work Review Run {run.review_run_id}'s chain does not validate: {exc}", "review_chain_invalid") from exc
    recorded = {effect["payload"]["path"]: effect["payload"]["content"] for effect in gen.stage_effects(STAGE_GENERATION)}
    next_number = records.FIRST_GENERATION if chain is None else chain.next_generation
    fits = generation == next_number
    if not fits and chain is not None and generation == chain.latest.generation:
        gate_path = review_paths.gate_rel(run.review_run_id, int(generation))
        stored = ReviewStore(store).read_bytes(gate_path)
        fits = stored is not None and gate_path in recorded and stored == recorded[gate_path].encode("utf-8")
    if not fits or found.get("transition") != TRANSITIONS.get(generation):
        raise _reconcile(
            f"the pending generation mutation {gen.id} writes generation {generation} ({found.get('transition')}) of "
            f"Work Review Run {run.review_run_id}, which is not the chain's next transition",
            "review_chain_invalid",
        )
    _finish_generation(store, gen)


def _chain(store: ProjectStore, run: WorkRun):
    try:
        return ReviewStore(store).gate_chain(run.review_run_id)
    except ValidationError as exc:
        raise _reconcile(f"Work Review Run {run.review_run_id}'s chain does not validate: {exc}", "review_chain_invalid") from exc


def _require_shape(run: WorkRun, chain: Any) -> None:
    """The chain is one of the three shapes a Work Run has before its terminal: accepted, settled, sealed."""
    generations = chain.generations
    problems: list[str] = []
    if len(generations) > work_review.SEAL_GENERATION:
        problems.append("more than three generations")
    first = generations[0]
    if first.review_kind != work_review.REVIEW_KIND or first.target_identity != run.work_id:
        problems.append("generation 1 is not a Work Review of this Work")
    if first.status != records.GATE_STATUS_OPEN or len(first.accepted_tasks) != 1 or first.settled_tasks:
        problems.append("generation 1 is not one accepted, unsettled task")
    if first.accepted_tasks and str(first.accepted_tasks[0]["task_id"]) != run.task_id:
        problems.append("generation 1 accepts another task than the reserved one")
    if len(generations) >= 2 and (generations[1].status != records.GATE_STATUS_OPEN or len(generations[1].settled_tasks) != 1):
        problems.append("generation 2 is not an open settlement")
    if len(generations) >= 3 and (not generations[2].sealed or generations[2].receipt_id != run.receipt_id
                                  or generations[2].authorized_operation_stage != work_review.AUTHORIZED_OPERATION_STAGE):
        problems.append("generation 3 is not the seal issuing the reserved Receipt for start:work-terminal")
    if problems:
        raise _reconcile(f"Work Review Run {run.review_run_id}: " + "; ".join(problems), "review_chain_invalid")


# --------------------------------------------------------------------------- the Run's durable material


@dataclass(frozen=True)
class RunMaterial:
    """What generation 1 made durable, read back from the canonical records and never from memory (F3 §5.3)."""

    task_input: records.TaskInput
    reconstruction: work_review.Reconstruction
    context: dict[str, Any]

    @property
    def candidate(self) -> dict[str, Any]:
        return self.reconstruction.candidate

    @property
    def base(self) -> dict[str, Any]:
        return self.reconstruction.candidate["declared_base"]


def run_material(store: ProjectStore, run: WorkRun, chain: Any) -> RunMaterial:
    """The accepted task, the exact Candidate with its payloads, and the bound Context - every cross-check applied."""
    review = ReviewStore(store)
    first = chain.generations[0]
    descriptor = first.accepted_tasks[0]
    problems = review.provenance_problems(descriptor, 1)
    if problems:
        raise _reconcile("the accepted task's provenance: " + "; ".join(message for _, message in problems),
                         "review_task_invalid")
    task_input = review.read_task_input(run.task_id)
    snapshot = review.read_candidate_snapshot(first.candidate_hash)
    material = snapshot.material or {}
    width = len(str((material.get("candidate") or {}).get("declared_base", {}).get("base_commit", "")))
    if width not in (40, 64):
        raise _reconcile("the stored Candidate names no declared base of a known object width")
    reconstruction = work_review.read_material(snapshot, first.candidate_hash, width)
    envelope_problems = work_review.task_input_problems(
        task_input, material, first.candidate_hash, first.review_context_hash, first.effective_policy_hash
    )
    if envelope_problems:
        raise _reconcile("the accepted task's request: " + "; ".join(envelope_problems), "review_task_invalid")
    return RunMaterial(task_input, reconstruction, dict(task_input.request_envelope["context"]))


# --------------------------------------------------------------------------- 5a ... 16: the completion under review


@dataclass(frozen=True)
class Sealed:
    """A sealed Work Review Run: the Receipt authorizes this exact Candidate for start:work-terminal."""

    run: WorkRun
    material: RunMaterial
    chain: Any


def freeze_and_review(session: "_Session", view: ProjectView, work: Entity, outcome: Any) -> Sealed:
    """F3 §5.1 steps 5a ... 16 for a Completed outcome; the sealed Run, or a STOP."""
    from .start import _result_message, completion_precheck

    store, mutation = session.store, session.mutation
    result_paths = tuple(p.replace("\\", "/") for p in outcome.result_paths)  # 5a, unchanged
    deleted_paths = tuple(p.replace("\\", "/") for p in outcome.deleted_paths)
    git = hermetic_module.enter(store)
    branch, pre_base = _head(git)
    # 5b - 5d, over every declared path in their precedence; nothing durable yet
    witnesses = ownership.bind_declarations(store, git, result_paths, deleted_paths, pre_base)
    ownership.assert_ownership(mutation, witnesses)  # 6
    completion_precheck(store, view, work, result_paths, deleted_paths)  # 7
    owned = sorted(set(result_paths) | set(deleted_paths))
    if owned:
        preexisting = gitops.record_preexisting_dirty(mutation, store.root)  # 8
        overlap = sorted(set(preexisting) & set(owned))
        if overlap:
            session._refuse_overlapping_result(work, outcome, overlap, overlap)
        attributes.require_pinned_path_evaluation(store, git, pre_base, owned)  # 9
    commit_stage(session, f"{work.id}:entry", f"chore(workline): enter {work.display}",
                 plan_class=workcommit.CLASS_ENTRY)  # 9a, S-c0 only when the entry events are uncommitted
    branch_after, base_commit = _head(git)
    if branch_after != branch:
        raise _reconcile(f"HEAD left {branch} while the completion of {work.id} was being frozen")
    width = len(base_commit)
    base = declared_base(store, git, base_commit, branch, work.id)
    # 10: the Candidate, from the bound witnesses and base_commit's tree - no pathname is read again
    held = workcommit._tree_entries(git, base_commit, [witness.path for witness in witnesses])
    entries: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    for witness in witnesses:
        old = held.get(witness.path)
        entries.append(work_review.candidate_entry(
            witness.path,
            None if old is None else (old.mode, old.oid),
            witness.kind,
            witness.git_mode,
            None if witness.kind == ownership.KIND_ABSENT else witness.identity,
            witness.material,
            width,
        ))
        if witness.material is not None:
            payloads[witness.path] = witness.material
    content = work_review.content_for(
        entries, message=_result_message(outcome.message, work), base_commit=base_commit,
        declared_result=result_paths, declared_deleted=deleted_paths,
    )
    activation = session.activation
    if activation is None:
        raise _reconcile("a review-v1 START session holds no activation proven at its entry")
    candidate = work_review.candidate_record(content, base, activation.binding())
    material = work_review.snapshot_material(candidate, payloads)  # 11
    snapshot = work_review.snapshot_for(material)
    # 11a, 11b: the resulting tree and the Context v2 - the proof TARGET, never a verdict
    resulting = resulting_tree.resulting_tree_id(
        store, git, base_commit, resulting_tree.entries_from_records(work_review.entries_of(candidate)), payloads
    )
    from .implementation import package_directory

    context = work_context.context_record(
        store.workline_root(), package_directory(store.workline_root()), activation.binding(),
        resulting_tree.root_tree_id(git, pre_base), resulting,
    )
    run = reserve_run(mutation, work.id)
    # 12: the Evidence checks F2 §13.2 names are executed, not assumed: the owned paths still hold
    # exactly what was witnessed (own-bytes), and every existing Review record reads canonically
    # (review-namespace) - then the isolated verification of the exact Candidate, from its
    # clone-safe material alone
    ownership.require_current(store, git, witnesses, pre_base)
    checkout.require_namespace_readable(store)
    reconstruction = work_review.read_material(snapshot, work_review.candidate_hash(candidate), width)
    verified = work_verify.verify(store, git, reconstruction, resulting_tree_id=resulting)
    context_hash = work_context.context_hash(context)
    policy_hash = work_review.policy_hash()
    envelope = work_review.request_envelope(candidate, context)
    task_input = work_review.task_input_for(
        task_id=run.task_id, reviewer_identity=session.review.reviewer_identity,
        reviewer_version=session.review.reviewer_version, envelope=envelope, snapshot=snapshot,
        review_context_hash=context_hash, effective_policy_hash=policy_hash,
    )
    evidence = _evidence(git, candidate, snapshot, task_input, context, context_hash, policy_hash, activation, verified,
                         declared=bool(owned))
    run.frozen = {"snapshot": snapshot, "task_input": task_input, "evidence": evidence, "context": context}
    _accept(session, run, base)  # 13
    session._drop_refused_result(work.id)
    return _continue(session, run)


def _evidence(
    git: HermeticGit, candidate: dict[str, Any], snapshot: records.CandidateSnapshot, task_input: records.TaskInput,
    context: dict[str, Any], context_hash: str, policy_hash: str, activation: Activation, verified: work_verify.Verified,
    *, declared: bool,
) -> dict[str, Any]:
    """F2 §13.2 - §14.3: the checks, the isolated verification and the closure digest, in one Evidence record."""
    base = candidate["declared_base"]
    material_digest = work_review.material_digest(snapshot)
    git_version = gitcmd.version_text(gitcmd.running_git_version() or (0, 0, 0))
    provenance = closure.ReviewProvenance(
        candidate_hash=snapshot.candidate_hash,
        candidate_material_digest=material_digest,
        task_input_digest=serialize.digest(task_input.to_record()),
        request_digest=task_input.request_digest,
        reviewer_identity=task_input.reviewer_identity,
        reviewer_version=task_input.reviewer_version,
        review_context_hash=context_hash,
        effective_policy_hash=policy_hash,
    )
    base_tree = resulting_tree.root_tree_id(git, base["base_commit"])
    declaration = work_review.dependency_declaration(
        entry_identities=work_review.entry_identities(candidate) + work_review.base_identities(candidate),
        base_commit=base["base_commit"],
        branch=base["branch"],
        object_identities=(base_tree, verified.resulting_tree),
        provenance=(
            provenance.candidate_hash, provenance.candidate_material_digest, provenance.task_input_digest,
            provenance.request_digest, provenance.reviewer_identity, provenance.reviewer_version,
            provenance.review_context_hash, provenance.effective_policy_hash,
        ),
        loader_identity=context["loader_identity"],
        git_version=git_version,
    )
    verification = work_review.verification_record(
        candidate_hash_value=snapshot.candidate_hash, candidate_material_digest=material_digest,
        review_context_hash=context_hash, effective_policy_hash=policy_hash,
        dependency_declaration=declaration.identity(), base_commit=base["base_commit"],
        resulting_tree=verified.resulting_tree, verified_entries=verified.verified_entries,
    )
    checks = work_review.check_results(declared)
    validity = work_review.validity_closure(
        base_commit=base["base_commit"], branch=base["branch"], provenance=provenance,
        entry_identities=work_review.entry_identities(candidate), activation_record_digest=activation.record_digest,
        evidence_payload_digest=serialize.digest(work_review.evidence_payload(checks, verification)),
        loader_identity=context["loader_identity"], git_version=git_version, declaration=declaration,
    )
    return work_review.evidence_record(checks, verification, validity.digest())


def _accept(session: "_Session", run: WorkRun, base: dict[str, Any]) -> None:
    """Generation 1: the snapshot, the TaskInput and the accepting gate, in one generation mutation (F3 §5.1 step 13)."""
    frozen = run.frozen or {}
    task_input: records.TaskInput = frozen["task_input"]
    snapshot: records.CandidateSnapshot = frozen["snapshot"]
    descriptor = work_review.accepted_descriptor(task_input)
    gate_one = records.GateGeneration(
        review_run_id=run.review_run_id, generation=1, previous_generation=None, previous_digest=None,
        review_kind=work_review.REVIEW_KIND, target_identity=run.work_id,
        operation_identity=work_review.operation_identity(run.work_id),
        candidate_hash=snapshot.candidate_hash, review_context_hash=work_context.context_hash(frozen["context"]),
        effective_policy_hash=work_review.policy_hash(), evidence_digest=serialize.digest(frozen["evidence"]),
        coverage_digest=serialize.digest(work_review.coverage_record(task_input.task_id, [])),
        raw_report_set_digest=serialize.digest(work_review.report_set_record([])),
        adjudication_digest=serialize.digest(work_review.adjudication_record([])),
        obligation_digest=serialize.digest(work_review.obligations_record([])),
        accepted_tasks=(descriptor,), settled_tasks=(), status=records.GATE_STATUS_OPEN, receipt_id=None,
        authorized_operation_stage=None,
    )
    _start_generation(session, run, 1, gate_one, [
        (review_paths.candidate_snapshot_rel(snapshot.candidate_hash), snapshot.to_record()),
        (review_paths.task_input_rel(task_input.task_id), task_input.to_record()),
    ], base)
    run.frozen = None


def continue_run(session: "_Session", run: WorkRun) -> Sealed:
    """Continue a Run this START already began, from its canonical records (F3 §5.4)."""
    return _continue(session, run)


def _continue(session: "_Session", run: WorkRun) -> Sealed:
    store = session.store
    while True:
        resolve_pending_generation(session, run)
        chain = _chain(store, run)
        if chain is None:
            raise _reconcile(f"Work Review Run {run.review_run_id} has no chain to continue", "review_chain_invalid")
        _require_shape(run, chain)
        material = run_material(store, run, chain)
        latest = chain.latest.generation
        if latest == 1:
            _launch_and_settle(session, run, chain, material)
            continue
        if latest == 2:
            if not work_review.authorizes(chain.latest):
                _refuse_seal(session.mutation, run, "not_authorized", None)
                raise _reconcile(
                    f"Work Review Run {run.review_run_id} settled without authorizing the completion of {run.work_id} "
                    "(a declined task or an unresolved HIGH or MID finding); START does not terminalize an unauthorized "
                    "completion, and nothing further is recorded"
                )
            require_capability(session, run, material)  # 15a
            _seal(session, run, chain, material.base)  # 16
            continue
        return Sealed(run, material, chain)


def _launch_and_settle(session: "_Session", run: WorkRun, chain: Any, material: RunMaterial) -> None:
    """Steps 14 - 15: the launch checks, the reviewer, the report, and generation 2."""
    store = session.store
    first = chain.latest
    descriptor = first.accepted_tasks[0]
    task_id = str(descriptor["task_id"])
    gate.require_persisted(store, [
        review_paths.candidate_snapshot_rel(first.candidate_hash),
        review_paths.task_input_rel(task_id),
        review_paths.gate_rel(run.review_run_id, 1),
    ])
    selector = session.review
    if (selector.reviewer_identity, selector.reviewer_version) != (descriptor["reviewer_identity"], descriptor["reviewer_version"]):
        raise StopError(
            f"task {task_id} was accepted for reviewer {descriptor['reviewer_identity']} {descriptor['reviewer_version']}, "
            f"and this invocation names {selector.reviewer_identity} {selector.reviewer_version}; the reviewer is not called",
            code="review_reviewer_mismatch",
        )
    task = work_review.task_from_input(material.task_input)
    try:
        returned = selector.reviewer(task)
    except Exception as exc:
        raise StopError(f"the reviewer raised for task {task_id}: {exc}; nothing is settled", code="review_reviewer_failed") from exc
    report = work_review.report_record(returned, descriptor)
    result_digest = serialize.digest(report)
    from .durable import durable_write_text

    durable_write_text(store.root / review_paths.runtime_report_rel(task_id), serialize.canonical_text(report), tmp_dir=store.tmp)
    gate.validate_settlement(store, run.review_run_id, task_id, result_digest, str(returned.reviewer_identity))
    settled = {"task_id": task_id, "status": work_review.settled_status(report), "result_digest": result_digest,
               "settled_generation": 2}
    pairs = [(settled, report)]
    gate_two = replace(
        first,
        generation=2,
        previous_generation=1,
        previous_digest=chain.latest_digest,
        coverage_digest=serialize.digest(work_review.coverage_record(task_id, [settled])),
        raw_report_set_digest=serialize.digest(work_review.report_set_record([settled])),
        adjudication_digest=serialize.digest(work_review.adjudication_record(pairs)),
        obligation_digest=serialize.digest(work_review.obligations_record(pairs)),
        settled_tasks=(settled,),
    )
    _start_generation(session, run, 2, gate_two, [], material.base)


def require_capability(session: "_Session", run: WorkRun, material: RunMaterial) -> work_checkout.Capability:
    """Step 15a (F3 §7.9.3 - §7.9.5): the capability of EXACTLY ``Context.resulting_tree``, before any generation-3 effect.

    Recomposed from the committed Candidate and its payloads; the Context's
    bound tree is what must be proven. ``unsafe`` or ``unknown`` is the STOP of
    this operation: no generation 3, no Receipt, and generation 2 stays the
    latest, open generation. The refusal is carried in the mutation's runtime
    metadata, never in a Review record.
    """
    store = session.store
    git = hermetic_module.enter(store)
    expected = material.context["review_checkout_capability"]["resulting_tree"]
    entries = resulting_tree.entries_from_records(work_review.entries_of(material.candidate))
    try:
        with resulting_tree.composed(store, git, material.base["base_commit"], entries,
                                     material.reconstruction.payloads) as composition:
            return work_checkout.require_resulting_tree_capability(store, git, composition, expect=expected)
    except StopError as exc:
        if exc.code in ("review_checkout_unsafe", "review_checkout_unknown"):
            _refuse_seal(session.mutation, run, exc.code, expected)
        raise


def _refuse_seal(mutation: Mutation, run: WorkRun, code: str, resulting: str | None) -> None:
    mutation.set_note(NOTE_SEAL_REFUSAL, {
        "review_run_id": run.review_run_id, "generation": 2, "code": code, "resulting_tree": resulting,
    })


def _seal(session: "_Session", run: WorkRun, chain: Any, base: dict[str, Any]) -> None:
    """Step 16: generation 3 and the Receipt, in one generation mutation - reached only on ``capable``."""
    second = chain.latest
    gate_three = replace(
        second, generation=3, previous_generation=2, previous_digest=chain.latest_digest,
        status=records.GATE_STATUS_SEALED, receipt_id=run.receipt_id,
        authorized_operation_stage=work_review.AUTHORIZED_OPERATION_STAGE,
    )
    receipt = records.Receipt(
        receipt_id=run.receipt_id, review_run_id=run.review_run_id, review_generation=3,
        review_kind=second.review_kind, target_identity=second.target_identity,
        operation_identity=second.operation_identity, authorized_candidate_hash=second.candidate_hash,
        review_context_hash=second.review_context_hash, effective_policy_hash=second.effective_policy_hash,
        coverage_hash=second.coverage_digest, adjudication_hash=second.adjudication_digest,
        obligation_digest=second.obligation_digest, unresolved_obligations=0,
        authorized_operation_stage=work_review.AUTHORIZED_OPERATION_STAGE,
    )
    if session.mutation.note(NOTE_SEAL_REFUSAL) is not None:
        session.mutation.set_note(NOTE_SEAL_REFUSAL, None)  # a retry that passes leaves no stale refusal behind
    _start_generation(session, run, 3, gate_three, [(review_paths.receipt_rel(run.receipt_id), receipt.to_record())], base,
                      receipt_id=run.receipt_id)
