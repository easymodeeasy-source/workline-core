"""START's review-v1 Work path: the entry, the Work Candidate, its Review Run, and the terminal (P3 F1 / F2 / F3 §5.1).

START stays the operation owner. Selecting review-v1 (``start(..., review=WorkReview(...))``)
makes Review a subordinate authorization gate inside START's own operation: START takes
the lock, opens and owns the mutation, runs the executor, decides every Git stage, and opens
the Run's generation mutations under its own lock. Review records what was reviewed and what
was authorized, and progresses nothing (F1 §6.3, F2 §8.3).

This module is START's, not Review's. The records it writes, and what they mean, are
:mod:`workline.review.work_review`'s; the object-driven commits are
:mod:`workline.review.workcommit`'s; ownership is :mod:`workline.review.ownership`'s.

What it implements, in the order F3 §5.1 freezes (steps 1 ... 37):

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
17 - 24  the RAW lineage, the Consumption id, S-c1 and K1, C-2(K1), the result-proof note, and
         (with a remote) the push-only publication of exactly K1
25 - 35  the one terminal stage (two events, then the Consumption), S-c2 and K2, C-2(K2), the
         terminal-proof note, and (with a remote) the push-only publication of exactly K2
36 - 37  the recorded-completion proof; START returns "completed"
```

Every commit this path makes is ``review-v1-work-local-v2`` and commit-only; the only pushes
are the two push-only publication stages, each of exactly the commit its proof note names,
with its C-2 re-evaluated before it is recorded and again before it is applied (F3 §4.3, §11).
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
    ancestry,
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
from .review.committed import CommittedReviewStore
from .review.store import ReviewStore
from .state import ProjectView
from .store import WORK_TERMINAL_EVENTS, Entity, Event, ProjectStore

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

    @property
    def content(self) -> dict[str, Any]:
        return work_review.content_of(self.reconstruction.candidate)


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


# --------------------------------------------------------------------------- 17 ... 37: proof, publication, terminal
#
# After the seal, in the order F3 §5.1 freezes, and each step durable before the next:
#
#   17   lineage precondition (§8.2 L-1 ... L-5, RAW ancestry)
#   17a  the Consumption id reserved              17b  the pinned preflight over S-c1's paths
#   18   S-c1 recorded                            19   K1 made (C-1)
#   20   C-2(K1), W1 ... W12                      21   "review_work_result_proof"
#   22   barrier  23 S-p1 recorded  24 applied: exact K1, C-2 re-evaluated at apply (V-7)
#   25   terminal ids reserved  26 S-t recorded (two events, then the Consumption)  27 applied
#   28   preflight over the terminal paths  29 S-c2 recorded  30 K2 made (C-1)
#   31   C-2(K2), T1 ... T12                      32   "review_work_terminal_proof"
#   33   barrier  34 S-p2 recorded  35 applied: exact K2, C-2 re-evaluated at apply (V-7)
#   36   the recorded-completion proof, P-1 ... P-6
#   37   START returns "completed"; its caller completes the mutation
#
# An empty-artifact Candidate has no K1: 18 ... 24 are absent, and the lineage is measured to
# parent(K2) instead (§6.2, §6.3). With no remote, 22 ... 24 and 33 ... 35 are absent (§20).
# Every step reads what is already durable first, so a resume re-derives and never re-decides.

PROOF_CONTRACT = "review-v1-work-proof-v1"
LINEAGE_CONTRACT = "review-v1-work-lineage-v1"
TERMINAL_CONTRACT = "review-v1-work-terminal-v1"
PUBLICATION_VALIDATOR = "review-v1-work-publication-v1"
NOTE_RESULT_PROOF = "review_work_result_proof"
NOTE_TERMINAL_PROOF = "review_work_terminal_proof"
TERMINAL_EVENTS = ("work_target_removed", "work_completed")
ROLE_RESULT, ROLE_TERMINAL = "result", "terminal"
#: The operation-contract metadata the work_completed event carries (F1 Gate 1, R4 §5).
OPERATION_CONTRACT = work_context.OPERATION_CONTRACT


def _proof_failed(item: str, detail: str, reason: str | None = None) -> ReconcileRequired:
    return ReconcileRequired(f"{PROOF_CONTRACT} {item} fails: {detail}: reconcile required", reason=reason)


def _lineage_failed(item: str, detail: str) -> ReconcileRequired:
    return ReconcileRequired(
        f"{LINEAGE_CONTRACT} {item} fails: {detail}; the Candidate is not usable on this history and a new one would "
        "have to be frozen: reconcile required",
        reason="review_registration_base_moved",
    )


class CommittedRecords(CommittedReviewStore):
    """P1's strict Review reader over one exact commit, every Git read in class B (F3 §7.1.9).

    ``CommittedReviewStore`` lists and reads with no class B environment, so a
    replacement object could govern what a C-2 item reads. This keeps its whole
    inherited reader - the canonical parse, the record identities, the chain
    invariants - and replaces only its two byte sources with class B reads of
    the stored objects.
    """

    def __init__(self, store: ProjectStore, git: HermeticGit, commit: str) -> None:
        ReviewStore.__init__(self, store)
        self.repo = store.root
        self.commit = commit
        self._git = git
        listed = git.run_bytes("ls-tree", "-r", "-t", "-z", "--full-tree", commit, "--", review_paths.REVIEW_DIR)
        if not listed.ok:
            raise ValidationError(f"Git cannot list the Review records of {commit}", code="review_record_missing")
        tree: dict[str, gitcmd.TreeEntry] = {}
        for item in listed.stdout.split(b"\0"):
            if not item:
                continue
            head, separator, path = item.partition(b"\t")
            fields = head.split(b" ")
            if not separator or len(fields) != 3:
                raise ValidationError(f"Git's listing of {commit} holds a record this reader cannot classify",
                                      code="review_record_invalid")
            mode, kind, oid = (field.decode("ascii", "replace") for field in fields)
            text = path.decode("utf-8", "surrogateescape")
            tree[text] = gitcmd.TreeEntry(mode, kind, oid, text)
        self._tree = tree

    def read_bytes(self, relative: str) -> bytes | None:
        review_paths.require_review_record_path(relative)
        found = self._tree.get(relative)
        if found is None:
            return None
        if found.type != "blob" or found.mode != "100644":
            raise ValidationError(f"{self.commit} holds {relative} as {found.type} {found.mode}, not a record",
                                  code="review_record_invalid")
        blob = self._git.run_bytes("cat-file", "blob", found.oid)
        if not blob.ok:
            raise ValidationError(f"Git cannot read {found.oid} at {relative} in {self.commit}",
                                  code="review_record_missing")
        return blob.stdout


# --------------------------------------------------------------------------- the durable record, read as a Work START


@dataclass(frozen=True)
class WorkRecord:
    """A review-v1 Work START mutation as its durable record names it: the Work, the Run, the effects."""

    mutation_id: str
    run: WorkRun
    effects: list[dict[str, Any]]
    notes: dict[str, Any]
    reserved: dict[str, Any]

    @property
    def work_id(self) -> str:
        return self.run.work_id

    def stages(self) -> list[str]:
        found: list[str] = []
        for effect in self.effects:
            if effect.get("stage") not in found:
                found.append(effect.get("stage"))
        return found

    def stage_effects(self, stage: str) -> list[dict[str, Any]]:
        return [effect for effect in self.effects if effect.get("stage") == stage]

    def one_stage(self, prefix: str) -> str | None:
        """The one recorded stage ``<prefix>:<n>``; None when there is none, reconcile when there are several."""
        found = [stage for stage in self.stages()
                 if isinstance(stage, str) and stage.startswith(prefix + ":") and stage[len(prefix) + 1:].isdigit()]
        if len(found) > 1:
            raise _reconcile(f"START mutation {self.mutation_id} recorded {len(found)} stages {found}; a review-v1 Work "
                             "mutation records each of its Git stages once")
        return found[0] if found else None


def work_record(record: dict[str, Any]) -> WorkRecord:
    """The durable record of a review-v1 Work START mutation, with the one Work Review Run it reserved."""
    if not work_invocation.is_work(record.get("invocation")):
        raise _reconcile(f"mutation {record.get('mutation_id')} is not a review-v1 Work START by its durable invocation")
    reserved = dict(record.get("reserved_ids") or {})
    prefix = f"review-run:{work_review.REVIEW_KIND}:"
    keys = [key for key in reserved if str(key).startswith(prefix)]
    if len(keys) != 1:
        raise _reconcile(f"START mutation {record.get('mutation_id')} holds {len(keys)} Work Review Runs, not one")
    run_id = str(reserved[keys[0]])
    task_id = reserved.get(gate.review_task_key(run_id, work_review.TASK_SLOT))
    receipt_id = reserved.get(gate.review_receipt_key(run_id, work_review.SEAL_GENERATION))
    if not isinstance(task_id, str) or not isinstance(receipt_id, str):
        raise _reconcile(f"START mutation {record.get('mutation_id')} holds Run {run_id} without its task or Receipt id")
    effects = record.get("effects") if isinstance(record.get("effects"), list) else []
    notes = record.get("notes") if isinstance(record.get("notes"), dict) else {}
    return WorkRecord(str(record.get("mutation_id")), WorkRun(keys[0][len(prefix):], run_id, task_id, receipt_id),
                      effects, notes, reserved)


def _commit_effect(record: WorkRecord, stage: str | None) -> dict[str, Any] | None:
    if stage is None:
        return None
    found = record.stage_effects(stage)
    if [effect.get("kind") for effect in found] != ["git_commit"]:
        raise _reconcile(f"stage {stage} is not one git_commit")
    return found[0]


def _pre_s_c0_base(record: WorkRecord, base_commit: str) -> str:
    """PRE_S_C0_BASE, from the record: S-c0's exact parent when S-c0 made the declared base, else the base itself."""
    stage = record.one_stage(f"{record.work_id}:entry")
    effect = _commit_effect(record, stage)
    if effect is None:
        return base_commit
    if effect.get("applied") is not True or effect.get("commit_id") != base_commit:
        raise _reconcile("S-c0 did not make the declared base the Candidate names")
    return str(effect["payload"]["base_head"])


def _terminal_stage(record: WorkRecord) -> str | None:
    """The one lifecycle stage of the review-v1 terminal shape (§13.3), or None when none is recorded."""
    found = [stage for stage in record.stages()
             if isinstance(stage, str) and stage.startswith(f"{record.work_id}:lifecycle:")
             and any(e.get("kind") == "create_file" for e in record.stage_effects(stage))]
    if len(found) > 1:
        raise _reconcile(f"START mutation {record.mutation_id} recorded more than one terminal stage")
    return found[0] if found else None


def is_terminal_stage(mutation: Mutation, stage: str, work_id: str) -> bool:
    """IP-3: whether ``stage`` is EXACTLY the review-v1 terminal stage of ``work_id`` (F3 §13.3).

    Two append_event effects in order under the reserved ids - work_target_removed,
    then work_completed carrying the review-v1 operation-contract metadata of
    this Run's Receipt - then exactly one create_file at this Run's Consumption
    path. Any other shape is not a review-v1 completion, and is never read as a
    legacy one either.
    """
    try:
        record = work_record(mutation.record)
    except ReconcileRequired:
        return False
    effects = record.stage_effects(stage)
    if [effect.get("kind") for effect in effects] != ["append_event", "append_event", "create_file"]:
        return False
    events = [effect["payload"].get("record") for effect in effects[:2]]
    if not all(isinstance(event, dict) for event in events):
        return False
    if [(event.get("type"), event.get("entity")) for event in events] != [(t, work_id) for t in TERMINAL_EVENTS]:
        return False
    if any(mutation.reserved(f"{stage}:event:{index}") != event.get("id") for index, event in enumerate(events)):
        return False
    if {key: value for key, value in events[1].items() if key not in ("id", "type", "entity", "at")} != _completion_metadata(record.run):
        return False
    consumption_id = mutation.reserved(gate.review_consumption_key(record.run.receipt_id))
    return consumption_id is not None and effects[2]["payload"].get("path") == review_paths.consumption_rel(consumption_id)


def _completion_metadata(run: WorkRun) -> dict[str, Any]:
    return {
        "operation_contract": OPERATION_CONTRACT,
        "review_receipt_id": run.receipt_id,
        "review_run_id": run.review_run_id,
        "review_generation": work_review.SEAL_GENERATION,
    }


# --------------------------------------------------------------------------- §8.2: lineage


def run_record_paths(run: WorkRun, chain: Any) -> list[str]:
    """This Run's own canonical Review record paths, DERIVED from its validated chain (L-2), never hardcoded."""
    first = chain.generations[0]
    found = {review_paths.candidate_snapshot_rel(first.candidate_hash)}
    for generation in chain.generations:
        found.add(review_paths.gate_rel(run.review_run_id, generation.generation))
        for task in generation.accepted_tasks:
            found.add(review_paths.task_input_rel(str(task["task_id"])))
        if generation.receipt_id:
            found.add(review_paths.receipt_rel(str(generation.receipt_id)))
    return sorted(found)


def _delta(git: HermeticGit, parent: str, commit: str) -> list[gitcmd.DeltaEntry]:
    """The complete delta of ``commit`` against ``parent``, from the stored objects (class B, no renames)."""
    try:
        return workcommit._tree_delta(git, workcommit._tree_of(git, parent), workcommit._tree_of(git, commit))
    except StopError as exc:
        raise _reconcile(f"the delta of {commit} against {parent} cannot be read: {exc}") from exc


def _parents(git: HermeticGit, commit: str) -> tuple[str, ...] | None:
    found = ancestry.raw_parents(git, commit)
    return None if isinstance(found, ancestry.Answer) else tuple(found)


def require_lineage(git: HermeticGit, run: WorkRun, chain: Any, base: dict[str, Any], parent: str) -> None:
    """``review-v1-work-lineage-v1``, L-1 ... L-5, measured to ``parent`` (§8.2; §6.3 for the empty case).

    Every question is answered by the RAW reader (§7.1.8): a graft, a shallow
    boundary or a replacement object changes nothing it reads, and an
    unanswerable question fails closed.
    """
    branch, base_commit = base["branch"], base["base_commit"]
    if workcommit._head_ref(git) != branch:
        raise _lineage_failed("L-3", f"HEAD is not on {branch}, the branch the Candidate declared")
    tip = workcommit.ref_value(git, branch)
    if tip is None or (tip != parent and ancestry.raw_descends_from(git, tip, parent) is not True):
        raise _lineage_failed("L-3", f"{branch} does not hold {parent}")
    if parent != base_commit and ancestry.raw_descends_from(git, parent, base_commit) is not True:
        raise _lineage_failed("L-1", f"{base_commit} is not shown to be an ancestor of {parent}")
    commits = ancestry.raw_range(git, base_commit, parent)
    if isinstance(commits, ancestry.Answer):
        raise _lineage_failed("L-2", f"the range ({base_commit}, {parent}] is {commits.value}")
    own = set(run_record_paths(run, chain))
    for commit in commits:
        parents = _parents(git, commit)
        if parents is None or len(parents) != 1:
            raise _lineage_failed("L-2", f"{commit} does not have exactly one parent")
        delta = _delta(git, parents[0], commit)
        foreign = [entry.path for entry in delta
                   if entry.status != "A" or entry.new_mode != "100644" or entry.path not in own]
        if not delta or foreign:
            raise _lineage_failed(
                "L-2", f"{commit} is not an own-Review commit of Run {run.review_run_id}"
                + (f" ({', '.join(foreign)})" if foreign else " (empty delta)")
            )


# --------------------------------------------------------------------------- the Run as a commit holds it


@dataclass(frozen=True)
class ProofMaterial:
    """The Run's records exactly as one commit holds them, cross-checked the way the launch checks them."""

    chain: Any
    snapshot: records.CandidateSnapshot
    reconstruction: work_review.Reconstruction
    task_input: records.TaskInput
    context: dict[str, Any]
    receipt: records.Receipt

    @property
    def candidate(self) -> dict[str, Any]:
        return self.reconstruction.candidate

    @property
    def base(self) -> dict[str, Any]:
        return self.reconstruction.candidate["declared_base"]

    @property
    def content(self) -> dict[str, Any]:
        return work_review.content_of(self.reconstruction.candidate)


def _material_at(at: "CommittedRecords", record: WorkRecord, item: str) -> ProofMaterial:
    run = record.run
    try:
        chain = at.gate_chain(run.review_run_id)
        if chain is None or len(chain.generations) != work_review.SEAL_GENERATION:
            raise _proof_failed(item, f"{at.commit} does not hold Run {run.review_run_id} as accepted, settled and sealed")
        third = chain.latest
        if not third.sealed or third.receipt_id != run.receipt_id:
            raise _proof_failed(item, f"{at.commit} does not hold the seal issuing Receipt {run.receipt_id}")
        first = chain.generations[0]
        snapshot = at.read_candidate_snapshot(first.candidate_hash)
        candidate = (snapshot.material or {}).get("candidate") or {}
        width = len(str(candidate.get("declared_base", {}).get("base_commit", "")))
        reconstruction = work_review.read_material(snapshot, first.candidate_hash, width)
        task_input = at.read_task_input(run.task_id)
        problems = work_review.task_input_problems(
            task_input, snapshot.material or {}, first.candidate_hash, first.review_context_hash,
            first.effective_policy_hash,
        )
        if problems:
            raise _proof_failed(item, "; ".join(problems))
        receipt = at.read_receipt(run.receipt_id)
    except ValidationError as exc:
        raise _proof_failed(item, f"the Run's records at {at.commit} do not read: {exc}") from exc
    return ProofMaterial(chain, snapshot, reconstruction, task_input, dict(task_input.request_envelope["context"]), receipt)


def _record_bytes(at: "CommittedRecords", paths: list[str]) -> dict[str, bytes | None]:
    return {relative: at.read_bytes(relative) for relative in paths}


def _namespace_clean(at: "CommittedRecords", run: WorkRun, item: str) -> None:
    """The whole namespace reads canonically at this commit, and nothing invalidates or supersedes the Run."""
    from .review import validate

    problems = validate.review_problems(at)
    if problems:
        raise _proof_failed(item, f"the Review namespace at {at.commit} does not read canonically: {problems[0].message}")
    if at.entry(review_paths.gate_rel(run.review_run_id, 4)) is not None or at.supersession_exists(run.receipt_id):
        raise _proof_failed(item, f"{at.commit} holds an invalidation of Run {run.review_run_id} or a Supersession")


def _require_receipt_current(material: ProofMaterial, record: WorkRecord, item: str) -> None:
    """W8 / T11: the Receipt is this Run's latest valid authorization for exactly this Candidate and stage."""
    from .review import validate

    receipt, third = material.receipt, material.chain.latest
    problems = [problem.message for problem in validate._gate_receipt_binding(third, receipt)]
    expected = {
        "authorized_candidate_hash": material.chain.generations[0].candidate_hash,
        "authorized_operation_stage": work_review.AUTHORIZED_OPERATION_STAGE,
        "target_identity": record.work_id,
        "operation_identity": work_review.operation_identity(record.work_id),
        "review_kind": work_review.REVIEW_KIND,
    }
    problems += [f"{name} is {getattr(receipt, name)!r}" for name, value in expected.items()
                 if getattr(receipt, name) != value]
    if not work_review.authorizes(material.chain.generations[1]):
        problems.append("the settlement does not authorize")
    if problems:
        raise _proof_failed(item, "the Receipt is not this Run's authorization of exactly this Candidate for "
                                  "start:work-terminal: " + "; ".join(problems))


def _require_identities(store: ProjectStore, git: HermeticGit, material: ProofMaterial, activation: Activation,
                        item: str) -> None:
    """W10 / T11: the Context recomputes to the bound hash, the Policy is the bound one, the Evidence re-derives."""
    from .implementation import package_directory

    first = material.chain.generations[0]
    capability = material.context["review_checkout_capability"]
    try:
        recomputed = work_context.context_record(
            store.workline_root(), package_directory(store.workline_root()), activation.binding(),
            capability["base_tree"], capability["resulting_tree"],
        )
    except StopError as exc:
        raise _proof_failed(item, f"the Work Review Context cannot be recomputed: {exc}") from exc
    if work_context.context_hash(recomputed) != first.review_context_hash:
        raise _proof_failed(item, "the Work Review Context no longer recomputes to the bound review_context_hash")
    if work_review.policy_hash() != first.effective_policy_hash:
        raise _proof_failed(item, "the Effective Policy is not the bound one")
    entries = work_review.entries_of(material.candidate)
    verified = work_verify.Verified(material.base["base_commit"], capability["resulting_tree"], len(entries))
    evidence = _evidence(git, material.candidate, material.snapshot, material.task_input, material.context,
                         first.review_context_hash, first.effective_policy_hash, activation, verified,
                         declared=bool(entries))
    if serialize.digest(evidence) != first.evidence_digest:
        raise _proof_failed(item, "the Evidence, and the closure digest inside it, does not re-derive to the bound "
                                  "evidence_digest")


def _activation_at(store: ProjectStore, git: HermeticGit, at: "CommittedRecords", material: ProofMaterial,
                   item: str) -> Activation:
    """W11: the activation record at this commit, well-formed, its prefix reproducing, bound in both records."""
    try:
        found = at.read_activation()
    except ValidationError as exc:
        raise _proof_failed(item, f"the activation record at {at.commit} does not read: {exc}") from exc
    if found is None:
        raise _proof_failed(item, f"{at.commit} holds no activation record")
    digest = activation_prefix_digest(git, at.commit, found.legacy_event_count)
    if digest is None or digest != found.legacy_event_prefix_sha256:
        raise _proof_failed(item, f"the activation prefix does not reproduce at {at.commit}")
    activation = Activation(found, serialize.digest(found.to_record()))
    binding = activation.binding()
    if material.candidate.get("activation") != binding or material.context.get("activation") != binding:
        raise _proof_failed(item, "the activation record is not the one the Candidate and the Context bind")
    return activation


def _events_at(git: HermeticGit, commit: str) -> bytes:
    found = git.run_bytes("cat-file", "blob", f"{commit}:{EVENT_LOG}")
    if not found.ok:
        raise _reconcile(f"the event log of {commit} cannot be read")
    return found.stdout


def _tree_identity(git: HermeticGit, commit: str, paths: list[str]) -> dict[str, tuple[str, str, str]]:
    try:
        held = workcommit._tree_entries(git, commit, paths)
    except StopError as exc:
        raise _reconcile(f"the tree of {commit} cannot be read: {exc}") from exc
    return {path: (entry.type, entry.mode, entry.oid) for path, entry in held.items()}


_KIND_TYPE = {"file": "blob", "symlink": "blob", "gitlink": "commit"}


def _require_contained(git: HermeticGit, commit: str, entries: list[dict[str, Any]], item: str) -> None:
    """W5 / T12: every entry resolves in ``commit``'s tree to exactly its new identity; a deletion is absent."""
    held = _tree_identity(git, commit, [entry["path"] for entry in entries])
    for entry in entries:
        found = held.get(entry["path"])
        if entry["new_kind"] == "absent":
            if found is not None:
                raise _proof_failed(item, f"{commit} still holds {entry['path']}, which the Candidate deletes")
        elif found != (_KIND_TYPE[entry["new_kind"]], entry["new_mode"], entry["new_oid"]):
            raise _proof_failed(item, f"{commit} holds {entry['path']} as {found}, not the Candidate's identity")


#: Git's raw status letters and the Candidate's (§9 W4): a type change has both sides present, so it is M.
_STATUS = {"A": "A", "D": "D", "M": "M", "T": "M"}


def _stage_position(record: WorkRecord, stage: str | None) -> int:
    for index, effect in enumerate(record.effects):
        if effect.get("stage") == stage:
            return index
    return len(record.effects)


def prove_result(store: ProjectStore, git: HermeticGit, mutation_record: dict[str, Any], k1: str) -> dict[str, Any]:
    """C-2(K1), ``review-v1-work-proof-v1`` W1 ... W12 (F3 §9), for exactly ``k1``; the result-proof note's content.

    Re-executed from the durable record and the committed objects alone
    (Option A, §10), so it can run again at any time - before the note, before
    the push is recorded and immediately before it is applied - and it never
    reads its own earlier outcome.
    """
    record = work_record(mutation_record)
    work_id = record.work_id
    stage = record.one_stage(f"{work_id}:results")
    effect = _commit_effect(record, stage)
    # W1 - ownership: the S-c1 effect promoted by O-7a, and nothing else confers it
    if effect is None or effect.get("applied") is not True or effect.get("commit_id") != k1:
        raise _proof_failed("W1", f"{k1} is not the commit the S-c1 stage of this mutation made", "review_commit_unowned")
    payload = effect["payload"]
    stored = workcommit._stored_commit(git, k1)
    if stored is None or len(stored.parents) != 1:
        raise _proof_failed("W3", f"{k1} is not one commit with exactly one parent")
    parent = stored.parents[0]
    at_parent, at_k1 = CommittedRecords(store, git, parent), CommittedRecords(store, git, k1)
    material = _material_at(at_k1, record, "W7")
    base = material.base
    # W2 - the Work persistence semantics, pinned to the declared base, re-proven now
    if (payload.get("mode") != workcommit.CONTRACT or payload.get("plan_class") != workcommit.CLASS_RESULT
            or payload.get("attr_basis") != base["base_commit"]):
        raise _proof_failed("W2", "S-c1 is not a review-v1-work-local-v2 result commit pinned to the declared base")
    attributes.require_pinned_path_evaluation(store, git, base["base_commit"], list(payload["paths"]))
    # W3 - lineage
    if parent != payload.get("base_head") or payload.get("branch") != base["branch"]:
        raise _proof_failed("W3", f"parent({k1}) is not the recorded base_head on the declared branch")
    require_lineage(git, record.run, material.chain, base, parent)
    tip = workcommit.ref_value(git, base["branch"])
    if tip is None or ancestry.raw_descends_from(git, tip, k1) is not True:
        raise _proof_failed("W3", f"{base['branch']} does not hold {k1}")
    # W4 - the artifact delta is the Candidate's CHANGING entries exactly
    entries = work_review.entries_of(material.candidate)
    changing = [entry for entry in entries if work_review.changing(entry)]
    if material.content["artifact_kind"] != work_review.ARTIFACT_RESULT or not changing:
        raise _proof_failed("W4", "the Candidate is not a result-bearing one")
    expected = {entry["path"]: (entry["old_mode"], entry["new_mode"], entry["old_oid"], entry["new_oid"], entry["status"])
                for entry in changing}
    found: dict[str, tuple[str, ...]] = {}
    for item in _delta(git, parent, k1):
        status = _STATUS.get(item.status)
        if status is None or item.path in found:
            raise _proof_failed("W4", f"{k1}'s delta holds {item.status} at {item.path}")
        found[item.path] = (item.old_mode, item.new_mode, item.old_blob, item.new_blob, status)
    if found != expected:
        raise _proof_failed("W4", f"{k1}'s delta is not exactly the Candidate's changing entries")
    # W5 - every declared entry, inert ones included, by exact tree containment
    _require_contained(git, k1, entries, "W5")
    # W6 - the message, byte for byte
    if stored.message != material.content["message"].encode("utf-8"):
        raise _proof_failed("W6", f"{k1}'s message is not the Candidate's message exactly")
    # W7 - the Run's records present and unchanged at parent(K1) and K1; the namespace canonical at both
    paths = run_record_paths(record.run, material.chain)
    before, after = _record_bytes(at_parent, paths), _record_bytes(at_k1, paths)
    if before != after or any(data is None for data in after.values()):
        raise _proof_failed("W7", "this Run's records are not held unchanged at parent(K1) and K1")
    _material_at(at_parent, record, "W7")
    _namespace_clean(at_parent, record.run, "W7")
    _namespace_clean(at_k1, record.run, "W7")
    # W8 - the authorization is current
    _require_receipt_current(material, record, "W8")
    # W9 - the Candidate is current: declared_base re-derives at its base, and at parent(K1)
    if declared_base(store, git, base["base_commit"], base["branch"], work_id) != base:
        raise _proof_failed("W9a", "declared_base does not re-derive at declared_base.base_commit")
    again = declared_base(store, git, parent, base["branch"], work_id)
    if {**again, "base_commit": base["base_commit"]} != base:
        raise _proof_failed("W9b", f"declared_base does not re-derive identically at {parent}")
    # W11 before W10: the activation the Context is recomputed with is the one proven here
    activation = _activation_at(store, git, at_parent, material, "W11")
    _require_identities(store, git, material, activation, "W10")
    # W12 - neither the transition nor the consumption has happened
    state = committed_view_at(store, git, k1).work_state(work_id)
    if state.state != "in_progress" or not state.has_target:
        raise _proof_failed("W12", f"{work_id} does not hold its target in progress at {k1}")
    for earlier in record.effects[:_stage_position(record, stage)]:
        event = (earlier.get("payload") or {}).get("record") if earlier.get("kind") == "append_event" else None
        if earlier.get("kind") == "git_push" or (isinstance(event, dict) and event.get("type") in WORK_TERMINAL_EVENTS):
            raise _proof_failed("W12", "a push or a Work terminal event is recorded before S-c1")
    consumed = [c for c in (*at_k1.consumptions(), *ReviewStore(store).consumptions())
                if c.receipt_id == record.run.receipt_id]
    if consumed:
        raise _proof_failed("W12", f"a Consumption of Receipt {record.run.receipt_id} already exists")
    return {
        "contract": PROOF_CONTRACT, "candidate_hash": material.chain.generations[0].candidate_hash,
        "receipt_id": record.run.receipt_id, "result_commit": k1, "base_commit": parent, "branch": base["branch"],
    }


def _parse_events(data: bytes) -> list[dict[str, Any]] | None:
    """Every Event record ``data`` holds, as the live reader parses it; None when one is not an Event."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    found: list[dict[str, Any]] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(event, dict) or not all(isinstance(event.get(k), str) for k in ("id", "type", "entity", "at")):
            return None
        found.append(event)
    return found


def prove_terminal(store: ProjectStore, git: HermeticGit, mutation_record: dict[str, Any], k2: str) -> dict[str, Any]:
    """C-2(K2), ``review-v1-work-proof-v1`` T1 ... T12 (F3 §16), for exactly ``k2``; the terminal-proof note's content."""
    record = work_record(mutation_record)
    work_id, run = record.work_id, record.run
    stage = record.one_stage(f"{work_id}:finalize")
    effect = _commit_effect(record, stage)
    # T1 - ownership
    if effect is None or effect.get("applied") is not True or effect.get("commit_id") != k2:
        raise _proof_failed("T1", f"{k2} is not the commit the S-c2 stage of this mutation made", "review_commit_unowned")
    payload = effect["payload"]
    stored = workcommit._stored_commit(git, k2)
    if stored is None or len(stored.parents) != 1:
        raise _proof_failed("T3", f"{k2} is not one commit with exactly one parent")
    parent = stored.parents[0]
    at_parent, at_k2 = CommittedRecords(store, git, parent), CommittedRecords(store, git, k2)
    material = _material_at(at_k2, record, "T11")
    base = material.base
    result = material.content["artifact_kind"] == work_review.ARTIFACT_RESULT
    k1_effect = _commit_effect(record, record.one_stage(f"{work_id}:results"))
    k1 = None if k1_effect is None else k1_effect.get("commit_id")
    # T2 - the Work persistence semantics, pinned to the declared base, re-proven now
    if (payload.get("mode") != workcommit.CONTRACT or payload.get("plan_class") != workcommit.CLASS_TERMINAL
            or payload.get("attr_basis") != base["base_commit"]):
        raise _proof_failed("T2", "S-c2 is not a review-v1-work-local-v2 terminal commit pinned to the declared base")
    attributes.require_pinned_path_evaluation(store, git, base["base_commit"], list(payload["paths"]))
    # T3 - lineage: parent(K2) is K1 exactly, or the own-Review lineage with no K1
    if parent != payload.get("base_head") or payload.get("branch") != base["branch"]:
        raise _proof_failed("T3", f"parent({k2}) is not the recorded base_head on the declared branch")
    if result:
        if not isinstance(k1, str) or parent != k1:
            raise _proof_failed("T3", f"parent({k2}) is not K1 exactly")
    else:
        if k1 is not None:
            raise _proof_failed("T3", "an empty-artifact operation holds a result commit")
        require_lineage(git, run, material.chain, base, parent)
    if workcommit._head_ref(git) != base["branch"]:
        raise _proof_failed("T3", f"HEAD is not on {base['branch']}")
    tip = workcommit.ref_value(git, base["branch"])
    if tip is None or ancestry.raw_descends_from(git, tip, k2) is not True:
        raise _proof_failed("T3", f"{base['branch']} does not hold {k2}")
    # T4 - the delta is exactly the terminal projection
    terminal = _terminal_stage(record)
    consumption_id = record.reserved.get(gate.review_consumption_key(run.receipt_id))
    if terminal is None or not isinstance(consumption_id, str):
        raise _proof_failed("T4", "the terminal stage or its Consumption id is not recorded")
    consumption_path = review_paths.consumption_rel(consumption_id)
    delta = sorted((item.path, item.status, item.old_mode, item.new_mode) for item in _delta(git, parent, k2))
    if delta != sorted([(EVENT_LOG, "M", "100644", "100644"), (consumption_path, "A", "000000", "100644")]):
        raise _proof_failed("T4", f"{k2}'s delta is not exactly the event log and the Consumption")
    # T5 - no new reviewed-artifact delta
    entries = work_review.entries_of(material.candidate)
    paths = [entry["path"] for entry in entries]
    if result and _tree_identity(git, k2, paths) != _tree_identity(git, str(k1), paths):
        raise _proof_failed("T5", f"{k2} changes the reviewed artifact K1 carries")
    # T6 / T7 - exactly the authorized transition, appended, and nothing else
    before, after = _events_at(git, parent), _events_at(git, k2)
    old, new = _parse_events(before), _parse_events(after)
    if old is None or new is None or not after.startswith(before) or new[: len(old)] != old:
        raise _proof_failed("T6", f"the event log at {k2} is not the one at {parent} with records appended")
    appended = new[len(old):]
    reserved = [record.reserved.get(f"{terminal}:event:{index}") for index in range(2)]
    shape = [(event.get("type"), event.get("entity"), event.get("id")) for event in appended]
    if shape != [(TERMINAL_EVENTS[0], work_id, reserved[0]), (TERMINAL_EVENTS[1], work_id, reserved[1])]:
        raise _proof_failed("T6", f"{k2} appends {shape}, not exactly the two authorized events")
    if {k: v for k, v in appended[1].items() if k not in ("id", "type", "entity", "at")} != _completion_metadata(run):
        raise _proof_failed("T7", "work_completed does not carry exactly the review-v1 operation-contract metadata")
    if {k: v for k, v in appended[0].items() if k not in ("id", "type", "entity", "at")}:
        raise _proof_failed("T7", "work_target_removed carries metadata")
    # T8 - the Consumption's content, and the artifact_kind agreement read from committed state
    recorded = [e for e in record.stage_effects(terminal) if e.get("kind") == "create_file"]
    committed = at_k2.read_bytes(consumption_path)
    if len(recorded) != 1 or committed is None or committed != recorded[0]["payload"]["content"].encode("utf-8"):
        raise _proof_failed("T8", "the Consumption K2 adds is not byte for byte the recorded one")
    try:
        consumption = at_k2.read_consumption(consumption_id)
    except ValidationError as exc:
        raise _proof_failed("T8", f"the Consumption does not read back: {exc}") from exc
    require_artifact_kind_agreement(material.candidate, consumption, k1, "T8")
    # T9 - the Consumption binds exactly this Receipt, this mutation and this terminal event
    receipt = material.receipt
    binding = ("receipt_id", "review_run_id", "review_generation", "review_kind", "target_identity",
               "operation_identity", "authorized_candidate_hash")
    wrong = [name for name in binding if getattr(consumption, name) != getattr(receipt, name)]
    if (wrong or consumption.operation_mutation_id != record.mutation_id or consumption.terminal_event_id != reserved[1]
            or consumption.terminal_event_type != "work_completed" or consumption.target_identity != work_id):
        raise _proof_failed("T9", "the Consumption does not bind exactly this Receipt, mutation and terminal event")
    # T10 - uniqueness and totality at K2
    try:
        by_receipt = at_k2.consumption_by_receipt()
        by_event = at_k2.consumption_by_terminal_event()
    except ValidationError as exc:
        raise _proof_failed("T10", f"the Consumption indexes do not build at {k2}: {exc}") from exc
    if (getattr(by_receipt.get(run.receipt_id), "consumption_id", None) != consumption_id
            or getattr(by_event.get(str(reserved[1])), "consumption_id", None) != consumption_id):
        raise _proof_failed("T10", "the Consumption is not the one Consumption of its Receipt and terminal event")
    _namespace_clean(at_k2, run, "T10")
    # T11 - the authorization still current, and every bound identity unchanged
    run_paths = run_record_paths(run, material.chain)
    if _record_bytes(at_parent, run_paths) != _record_bytes(at_k2, run_paths):
        raise _proof_failed("T11", "this Run's records changed between parent(K2) and K2")
    _require_receipt_current(material, record, "T11")
    activation = _activation_at(store, git, at_parent, material, "T11")
    _require_identities(store, git, material, activation, "T11")
    # T12 - the result binding
    if result:
        if ancestry.raw_descends_from(git, k2, str(k1)) is not True or consumption.authorized_result_commit_sha != k1:
            raise _proof_failed("T12", "K1 is not in K2's history, or the Consumption names another result commit")
    else:
        if consumption.authorized_result_commit_sha is not None:
            raise _proof_failed("T12", "an empty-artifact Consumption names a result commit")
        if any(e.get("kind") == "git_commit" and (e.get("payload") or {}).get("plan_class") == workcommit.CLASS_RESULT
               for e in record.effects):
            raise _proof_failed("T12", "a commit of this mutation carries a reviewed-artifact delta")
        _require_contained(git, k2, entries, "T12")
        declared = set(paths)
        if any(item.path in declared for item in _delta(git, base["base_commit"], k2)):
            raise _proof_failed("T12", "the delta from the declared base to K2 holds a declared path")
    return {
        "contract": PROOF_CONTRACT, "candidate_hash": material.chain.generations[0].candidate_hash,
        "receipt_id": run.receipt_id, "artifact_kind": material.content["artifact_kind"],
        "result_commit": k1 if result else None, "terminal_commit": k2, "terminal_event_ids": list(reserved),
        "consumption_id": consumption_id, "base_commit": parent, "branch": base["branch"],
    }


def require_artifact_kind_agreement(candidate: dict[str, Any], consumption: Any, k1: str | None, item: str) -> None:
    """F3 §14.2: both statements read on their own and compared; neither is derived from the other."""
    reviewed = work_review.content_of(candidate).get("artifact_kind")
    consumed = getattr(consumption, "artifact_kind", None)
    if reviewed not in (work_review.ARTIFACT_RESULT, work_review.ARTIFACT_EMPTY) or consumed != reviewed:
        raise _proof_failed(item, f"the Candidate says {reviewed!r} and the Consumption {consumed!r}")
    if reviewed == work_review.ARTIFACT_RESULT and (k1 is None or consumption.authorized_result_commit_sha != k1):
        raise _proof_failed(item, "a result-bearing Consumption does not name K1")
    if reviewed == work_review.ARTIFACT_EMPTY and consumption.authorized_result_commit_sha is not None:
        raise _proof_failed(item, "an empty Consumption names a result commit")


# --------------------------------------------------------------------------- IP-2: the Work publication validator


def work_publication(store: ProjectStore, effects: list[dict[str, Any]], position: int,
                     mutation_record: dict[str, Any]) -> tuple[str, str]:
    """``review-v1-work-publication-v1`` V-2 ... V-7 (F3 §11.2) for the push at ``position``; ``(K, full ref)``.

    V-1 (a push-only stage) is the caller's, in the Mutation Controller, and V-8
    (the exact refspec) is the one the Controller already pushes. Every refusal
    here is ``reconcile_required``: the push names no commit and publishes
    nothing.
    """
    push = effects[position]
    payload = push.get("payload") if isinstance(push.get("payload"), dict) else {}
    commit = payload.get("commit")
    if not gitcmd.full_commit_id(commit):
        raise _reconcile("V-2: the Work push does not name a full commit id", "review_publication_invalid")
    record = work_record({**mutation_record, "effects": effects})
    # V-3: exactly one proof note names K, and that says which publication this is
    roles = []
    for key, field, role in ((NOTE_RESULT_PROOF, "result_commit", ROLE_RESULT),
                             (NOTE_TERMINAL_PROOF, "terminal_commit", ROLE_TERMINAL)):
        note = record.notes.get(key)
        if isinstance(note, dict) and note.get("contract") == PROOF_CONTRACT and note.get(field) == commit:
            roles.append(role)
    if len(roles) != 1:
        raise _reconcile(f"V-3: {len(roles)} proof notes name {commit}, not exactly one", "review_publication_invalid")
    role = roles[0]
    # V-4: the one commit effect that made K
    makers = [index for index, effect in enumerate(effects)
              if effect.get("kind") == "git_commit" and effect.get("applied") is True and effect.get("commit_id") == commit]
    maker = effects[makers[0]] if len(makers) == 1 else {}
    stage_members = [index for index, effect in enumerate(effects) if effect.get("stage") == maker.get("stage")]
    ref = (maker.get("payload") or {}).get("branch")
    if (len(makers) != 1 or stage_members != makers or makers[0] >= position
            or (maker.get("payload") or {}).get("mode") != workcommit.CONTRACT
            or ref != f"refs/heads/{payload.get('branch')}"):
        raise _reconcile("V-4: the commit the push names is not exactly one applied Work commit of its own stage, "
                         "recorded earlier on the pushed branch", "review_publication_invalid")
    # V-5: Git agrees - one parent, the recorded base_head, and the branch still holds K
    git = hermetic_module.enter(store)
    if _parents(git, commit) != (maker["payload"]["base_head"],):
        raise _reconcile(f"V-5: {commit} is not one commit on its recorded base_head", "review_publication_invalid")
    tip = workcommit.ref_value(git, str(ref))
    if tip is None or ancestry.raw_descends_from(git, tip, commit) is not True:
        raise _reconcile(f"V-5: {ref} does not hold {commit}", "review_publication_invalid")
    # V-6a: the exact cardinality, from the destination pin and the Candidate's artifact_kind
    from .destination import ensure_push_destination

    if ensure_push_destination(store) is None:
        raise _reconcile("V-6a: a Work mutation with no destination publishes nothing", "review_publication_invalid")
    at = CommittedRecords(store, git, commit)
    kind = _material_at(at, record, "V-6a").content["artifact_kind"]
    allowed = 2 if kind == work_review.ARTIFACT_RESULT else 1
    pushes = [index for index, effect in enumerate(effects) if effect.get("kind") == "git_push"]
    if len(pushes) > allowed:
        raise _reconcile(f"V-6a: {len(pushes)} pushes are recorded and this case allows {allowed}",
                         "review_publication_invalid")
    # V-6: the role's shape
    if role == ROLE_RESULT:
        if kind != work_review.ARTIFACT_RESULT or pushes[0] != position:
            raise _reconcile("V-6: a result publication in an operation that has no K1, or not the first push",
                             "review_publication_invalid")
    else:
        if len(pushes) != allowed or pushes[-1] != position:
            raise _reconcile("V-6a: the terminal publication is not the last of exactly the pushes this case allows",
                             "review_publication_invalid")
        terminal = _terminal_stage(record)
        if terminal is None or any(effect.get("applied") is not True for effect in record.stage_effects(terminal)):
            raise _reconcile("V-6: the terminal stage is not recorded and applied", "review_publication_invalid")
    # V-7: the full C-2 of exactly K, re-evaluated immediately before a push not yet applied is made. A push
    # already applied has published; its C-2 was re-evaluated before it was, and C-2(K1)'s W12 ("not yet
    # applied") is false by construction once the terminal stage exists, so it is never asked again then.
    if push.get("applied") is not True:
        whole = {**mutation_record, "effects": effects}
        proven = (prove_result if role == ROLE_RESULT else prove_terminal)(store, git, whole, commit)
        note = record.notes[NOTE_RESULT_PROOF if role == ROLE_RESULT else NOTE_TERMINAL_PROOF]
        if note != proven:
            raise _reconcile("V-7: the proof re-evaluated now is not the one its note names", "review_publication_invalid")
    return commit, str(ref)


# --------------------------------------------------------------------------- 17 ... 37, in order


def _write_note(mutation: Mutation, key: str, value: dict[str, Any]) -> None:
    """A proof note is written once and names exactly one commit; a different one already there is reconcile."""
    found = mutation.note(key)
    if found is None:
        mutation.set_note(key, value)
        return
    if found != value:
        raise _reconcile(f"the {key} note already names another proof than the one re-evaluated now")


def _publish_stage(session: "_Session", prefix: str, commit: str, branch: str) -> None:
    """S-p1 / S-p2: a push-only stage publishing exactly ``commit`` to the declared ``branch`` (F3 §11, §12)."""
    from .review import publication

    mutation = session.mutation
    if work_record(mutation.record).one_stage(prefix) is None:
        # 22 / 33: the barrier, after the proof and its note, before the stage is recorded (§12.2)
        publication.require_barrier_clear(session.store.root, commit)
        mutation.add_effects(stage_name(mutation, prefix), [
            gitops.review_publication_effect(session.destination, branch.removeprefix("refs/heads/"), commit)
        ])
    # 24 / 35: the Controller re-resolves the destination, re-checks the barrier and - through the Work
    # validator - re-evaluates the full C-2 of exactly this commit before it pushes it (V-7)
    mutation.apply()


def _stage_commit(mutation: Mutation, stage: str | None) -> str:
    effect = _commit_effect(work_record(mutation.record), stage)
    if effect is None or effect.get("applied") is not True or not gitcmd.full_commit_id(effect.get("commit_id")):
        raise _reconcile(f"stage {stage} does not hold a commit C-1 owns", "review_commit_unowned")
    return str(effect["commit_id"])


def terminalize(session: "_Session", sealed: Sealed) -> Any:
    """F3 §5.1 steps 17 ... 37 for a sealed Work Review Run; the ``completed`` StartResult, or a STOP."""
    from .start import StartResult

    store, mutation = session.store, session.mutation
    run, material = sealed.run, sealed.material
    candidate, base = material.candidate, material.base
    work_id = run.work_id
    result = work_review.artifact_kind(candidate) == work_review.ARTIFACT_RESULT
    git = hermetic_module.enter(store)
    remote = session.destination is not None
    chain = _chain(store, run)
    # 17a - the Consumption id, reserved at or after the seal and before S-c1 (§13.2)
    consumption_id = mutation.reserve_id(gate.review_consumption_key(run.receipt_id), "review_consumption")
    consumption_path = review_paths.consumption_rel(consumption_id)
    if consumption_path not in mutation.scope.files:
        mutation.extend_scope(files=[consumption_path])
    k1: str | None = None
    terminal_recorded = _terminal_stage(work_record(mutation.record)) is not None
    if result:
        k1 = _result_commit(session, sealed, git, chain)  # 17, 17b, 18, 19
        if not terminal_recorded:
            # 20, 21: C-2(K1) re-evaluated until the terminal stage exists. From then on its W12 ("the
            # consumption has not happened") is false by construction, and the stage was recorded only
            # once this proof was complete and its note durable (§13.4) - so it is never asked again.
            _write_note(mutation, NOTE_RESULT_PROOF, prove_result(store, git, mutation.record, k1))
        elif not isinstance(mutation.note(NOTE_RESULT_PROOF), dict):
            raise _reconcile("the terminal stage is recorded without the result proof note it requires")
        if remote:
            _publish_stage(session, f"{work_id}:results-publication", k1, base["branch"])  # 22 - 24
    elif work_record(mutation.record).one_stage(f"{work_id}:finalize") is None and not terminal_recorded:
        branch, tip = _head(git)
        require_lineage(git, run, chain, base, tip)  # 17, measured to K2's parent (§6.2)
    k2 = _terminal(session, sealed, git, chain, consumption_id, k1)  # 25 - 30
    _write_note(mutation, NOTE_TERMINAL_PROOF, prove_terminal(store, git, mutation.record, k2))  # 31, 32
    if remote:
        _publish_stage(session, f"{work_id}:finalize-publication", k2, base["branch"])  # 33 - 35
    require_recorded_completion(session, sealed, git, k2, consumption_path)  # 36
    session.completed.append(work_id)
    view = ProjectView.load(store)
    return StartResult("completed", work_id, mutation.id, tuple(session.completed), view.works[work_id].phase_id,
                       head=k2)


def _result_commit(session: "_Session", sealed: Sealed, git: HermeticGit, chain: Any) -> str:
    """Steps 17 - 19: lineage, the preflight again, S-c1 recorded from the bound witnesses, K1 made (C-1)."""
    store, mutation = session.store, session.mutation
    run, material = sealed.run, sealed.material
    base = material.base
    prefix = f"{run.work_id}:results"
    if work_record(mutation.record).one_stage(prefix) is None:
        branch, tip = _head(git)
        require_lineage(git, run, chain, base, tip)  # 17
        changing = [entry for entry in work_review.entries_of(material.candidate) if work_review.changing(entry)]
        paths = [entry["path"] for entry in changing]
        pre_base = _pre_s_c0_base(work_record(mutation.record), base["base_commit"])
        owned = ownership.own_witnesses(mutation)
        missing = [path for path in paths if path not in owned]
        if missing:
            raise _reconcile(f"no bound ownership witness is recorded for {missing}")
        chosen = [owned[path] for path in paths]
        # the pre-stage re-proof of §7.8.4: the chain re-walked and the whole witness compared
        ownership.require_current(store, git, chosen, pre_base)
        attributes.require_pinned_path_evaluation(store, git, base["base_commit"], paths)  # 17b
        plan = workcommit.result_plan(git, parent=tip, ref=branch, message=material.content["message"],
                                      witnesses=chosen, candidate_entries=changing)
        effect = workcommit.commit_effect(plan, attr_basis=base["base_commit"], witness_basis=pre_base)
        mutation.add_effects(stage_name(mutation, prefix), [effect])  # 18
    mutation.apply()  # 19
    return _stage_commit(mutation, work_record(mutation.record).one_stage(prefix))


def _terminal(session: "_Session", sealed: Sealed, git: HermeticGit, chain: Any, consumption_id: str,
              k1: str | None) -> str:
    """Steps 25 - 30: the terminal stage (two events, then the Consumption), applied; then S-c2 and K2."""
    from .ops import new_event

    store, mutation = session.store, session.mutation
    run, material = sealed.run, sealed.material
    work_id, base = run.work_id, material.base
    consumption_path = review_paths.consumption_rel(consumption_id)
    if _terminal_stage(work_record(mutation.record)) is None:
        # §13.4 - before the stage is recorded
        gate.require_committable(store, [consumption_path])
        if material.content["artifact_kind"] == work_review.ARTIFACT_RESULT:
            note = mutation.note(NOTE_RESULT_PROOF)
            if not isinstance(note, dict) or note.get("result_commit") != k1:
                raise _reconcile("the terminal stage is recorded only after C-2(K1) and its note")
        if not chain.latest.sealed or not work_review.authorizes(chain.generations[1]):
            raise _reconcile(f"Work Review Run {run.review_run_id} is not sealed with an authorizing settlement")
        review = ReviewStore(store)
        if (any(c.receipt_id == run.receipt_id for c in review.consumptions()) or review.supersession_exists(run.receipt_id)
                or review.read_bytes(review_paths.gate_rel(run.review_run_id, 4)) is not None):
            raise _reconcile(f"Receipt {run.receipt_id} is consumed, superseded or invalidated")
        stage = stage_name(mutation, f"{work_id}:lifecycle")  # 25: every identifier durable before apply
        removed = new_event(mutation, f"{stage}:event:0", TERMINAL_EVENTS[0], work_id)
        reserved = new_event(mutation, f"{stage}:event:1", TERMINAL_EVENTS[1], work_id)
        completed = Event(reserved.id, reserved.type, reserved.entity, reserved.at, _completion_metadata(run))
        receipt = ReviewStore(store).read_receipt(run.receipt_id)
        consumption = records.Consumption(
            consumption_id=consumption_id, receipt_id=receipt.receipt_id, review_run_id=receipt.review_run_id,
            review_generation=receipt.review_generation, review_kind=receipt.review_kind,
            authorized_candidate_hash=receipt.authorized_candidate_hash, operation_identity=receipt.operation_identity,
            operation_mutation_id=mutation.id, terminal_event_id=completed.id, terminal_event_type=completed.type,
            target_identity=work_id, authorized_result_commit_sha=k1,
            artifact_kind=work_review.ARTIFACT_RESULT if k1 is not None else work_review.ARTIFACT_EMPTY,
        )
        # §14.3: the Consumption's own statement, then compared with the Candidate's before anything is recorded
        require_artifact_kind_agreement(material.candidate, consumption, k1, "§14")
        mutation.add_effects(stage, [  # 26: two events, then the Consumption - exactly three, in that order
            Effect.append_event(removed),
            Effect.append_event(completed),
            Effect.create_file(consumption_path, serialize.canonical_text(consumption.to_record())),
        ])
    mutation.apply()  # 27
    prefix = f"{work_id}:finalize"
    if work_record(mutation.record).one_stage(prefix) is None:
        branch, tip = _head(git)
        if k1 is not None and tip != k1:
            raise _reconcile(f"{branch} is {tip}, not K1 {k1}; parent(K2) is K1 exactly (§15.1)",
                             "review_registration_base_moved")
        if k1 is None:
            require_lineage(git, run, chain, base, tip)
        # 28 - 29: the per-commit preflight runs when the stage is recorded, under the declared base's pin
        view = ProjectView.load(store)
        effect = workcommit.terminal_commit_effect(
            mutation, f"chore(workline): complete {view.works[work_id].display}", attr_basis=base["base_commit"]
        )
        mutation.add_effects(stage_name(mutation, prefix), [effect])
    mutation.apply()  # 30
    return _stage_commit(mutation, work_record(mutation.record).one_stage(prefix))


def require_recorded_completion(session: "_Session", sealed: Sealed, git: HermeticGit, k2: str,
                                consumption_path: str) -> None:
    """Step 36, P-1 ... P-6 (F3 §19): only then does START return ``completed``."""
    store, mutation = session.store, session.mutation
    run, material = sealed.run, sealed.material
    record = work_record(mutation.record)
    terminal = _terminal_stage(record)
    # P-1 - the terminal stage recorded and applied
    if terminal is None or any(effect.get("applied") is not True for effect in record.stage_effects(terminal)):
        raise _reconcile("P-1: the terminal stage is not recorded and applied")
    # P-2 - C-2(K2), re-evaluated here
    prove_terminal(store, git, mutation.record, k2)
    # P-3 - with a remote, the exact K2 published
    if session.destination is not None:
        stage = record.one_stage(f"{run.work_id}:finalize-publication")
        if stage is None or any(effect.get("applied") is not True for effect in record.stage_effects(stage)):
            raise _reconcile("P-3: K2 is not published")
    # P-4 - the live lifecycle postcheck, reading no Review record
    if ProjectView.load(store).work_state(run.work_id).state != "completed":
        raise StopError(f"{run.work_id} is not completed after its terminal stage", code="postcheck_failed")
    # P-5 - the Review consistency postcheck, from committed state at K2 (T8 - T11 re-read it in P-2)
    # P-6 - nothing this operation owns is left uncommitted
    owned = [entry["path"] for entry in work_review.entries_of(material.candidate)] + [EVENT_LOG, consumption_path]
    left = gitcmd.changed_against_head(store.root, owned)
    if left:
        raise _reconcile(f"P-6: {', '.join(sorted(left))} is not committed as this operation left it")
