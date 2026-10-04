"""Canonical recovery discovery: which Review Run a review-v1 planning invocation continues after runtime loss.

Review-owned reads only (``skills/review``: the recovery classification of a
Run). It reads HEAD's committed objects and the working tree through the P1
reader; it records nothing, starts no mutation and decides no lifecycle. The
Roadmap operation runs it under its lock, only when the slot has no pending
review-v1 planning mutation, and acts on the answer (``skills/roadmap``).

```text
1 readability    every record of the namespace reads canonically (review_namespace_unreadable)
2 matching Runs  generation 1 added in HEAD's history or present in the working tree, of this kind
                 and this operation identity
3 clean          committed, unchanged, whole, one of the four shapes, no pending token holder
4 rows a-g       invalidated | consumed (CP proves it) | not_authorized | set_aside | reconstruction
                 | currency on HEAD (generations 1-2) | sealed (generation 3)
5 outcome        one recoverable -> recover it; none -> a new Run recording the set-aside Runs;
                 several -> ambiguous; anything incomplete -> incomplete
```

A Run that cannot be shown whole, or that holds a registration commit the
committed planning proof does not prove, is never excluded quietly and never
replaced by a new Run: the call stops.

The mechanics above - matching, committed-history discovery, whole-record
persistence, set-aside harvesting, no selection by age and the refusal of
several recoverable Runs - are Review-wide. What a Run's chain may look like,
how its request names Runs set aside, and the classification and
reconstruction tail are kind policy (F4 §26.5, §26.28 P4): planning keeps its
adapter exactly as it was, and the Work kind (``work-result-v1``) has its own
(:func:`discover_work`), which every review-v1 Work START invocation runs
(``skills/start``). A Work Run is resumed only through the START mutation that
reserved it, so the Work policy needs one more input than planning's: the Runs
the pending START mutations of the Work hold.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .. import gitcmd
from ..errors import ReconcileRequired, StopError, ValidationError
from ..ids import is_valid_id
from ..store import ProjectStore
from . import checkout, committed, gate, paths, planning, records, serialize, work_review
from .records import GateGeneration
from .store import GateChain, ReviewStore


def _incomplete(message: str) -> ReconcileRequired:
    return ReconcileRequired(
        f"{message}; a matching Review Run that cannot be shown whole is never replaced by a new Run: reconcile required",
        reason="review_recovery_incomplete",
    )


@dataclass(frozen=True)
class MatchingRun:
    review_run_id: str
    chain: GateChain
    material: dict[str, Any]
    task_id: str


@dataclass(frozen=True)
class Discovery:
    """The outcome: the one recoverable Run, or none and the matching Runs set aside with their reasons."""

    recoverable: MatchingRun | None
    set_aside: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class RecoveryAdapter:
    """The kind policy around the shared discovery core (F4 §26.5, §26.28 P4).

    ``shape``     the chain shapes a Run of this kind has (a problem, or None)
    ``named``     the Run ids a matching Run's stored request sets aside
    ``classify``  rows a-g: the set-aside reason of a matching Run, or None for a recoverable one
    """

    shape: Callable[[GateChain], "str | None"]
    named: Callable[[ReviewStore, MatchingRun], "list[str]"]
    classify: Callable[..., "str | None"]


def discover(
    store: ProjectStore,
    review_kind: str,
    operation_identity: str,
    *,
    currency: Callable[[MatchingRun], Any],
) -> Discovery:
    """Canonical recovery discovery (§12.2 steps 1-5) for one invocation; it begins nothing.

    ``currency`` evaluates a generation-1 or authorizing generation-2 Run's
    currency on HEAD, in the Roadmap-owned order; it answers ``current``,
    ``stale`` (with the reason) or ``mismatch``.
    """
    return _discover(store, review_kind, operation_identity, currency, PLANNING)


def discover_work(
    store: ProjectStore,
    operation_identity: str,
    *,
    currency: Callable[[MatchingRun], Any],
    owned: "frozenset[str] | set[str] | tuple[str, ...]",
    held: "frozenset[str] | set[str] | tuple[str, ...]" = (),
) -> Discovery:
    """The same canonical discovery over the Work kind's Runs of one operation identity (F4 §11.12).

    Every matching Run is proven whole and classified - ``invalidated`` (its
    generation 4), ``consumed``, ``not_authorized``, ``set_aside`` (named by a
    version 2 request), recoverable, stale (``currency``), or incomplete - and
    never chosen by age: one recoverable is the one to continue, several are
    ``review_recovery_ambiguous``, an incomplete one stops the call.

    ``owned`` are the Runs the pending START mutations of this Work reserved. A
    Work Run is resumed only from the record of the START mutation that
    reserved it and the canonical Review records (``skills/start``: resume), and
    what its remaining stages need is in that record alone (:func:`_require_owner`),
    so a Run of a recoverable shape that no owned set holds is incomplete, never
    recoverable. ``held`` (some of ``owned``) are the Runs the calling START
    mutation leaves to its own recovery selector
    (``start_review.select_in_flight``): they are neither proven nor classified
    here - an own Run with a pending generation mutation is the selector's to
    resume, never "incomplete" - and the Runs their requests set aside stay set
    aside. Every OTHER matching Run is classified exactly as above.
    """
    owned, held = frozenset(owned), frozenset(held)
    if not held <= owned:
        raise ValueError("a held Work Review Run is one a pending START mutation of the Work holds")
    adapter = RecoveryAdapter(
        shape=_work_shape_problem, named=_work_named,
        classify=lambda store_, review, head, found, named_aside, currency_: _classify_work(
            store_, review, head, found, named_aside, currency_, owned),
    )
    return _discover(store, work_review.REVIEW_KIND, operation_identity, currency, adapter, held)


def _discover(
    store: ProjectStore,
    review_kind: str,
    operation_identity: str,
    currency: Callable[[MatchingRun], Any],
    adapter: RecoveryAdapter,
    held: frozenset[str] = frozenset(),
) -> Discovery:
    checkout.require_namespace_readable(store)
    review = ReviewStore(store)
    head = gitcmd.head_commit(store.root)
    matching = _matching_runs(store, review, head, review_kind, operation_identity)
    runs: dict[str, MatchingRun] = {}
    for review_run_id in sorted(matching - held):
        runs[review_run_id] = _clean_run(store, review, head, review_run_id, adapter.shape)
    named_aside: set[str] = set()
    for found in runs.values():
        named_aside.update(adapter.named(review, found))
    for review_run_id in sorted(matching & held):
        named_aside.update(_held_named(review, review_run_id, adapter))
    recoverable: list[MatchingRun] = []
    set_aside: list[dict[str, str]] = []
    for review_run_id, found in runs.items():
        reason = adapter.classify(store, review, head, found, named_aside, currency)
        if reason is None:
            recoverable.append(found)
        else:
            set_aside.append({"review_run_id": review_run_id, "reason": reason})
    if len(recoverable) > 1:
        raise ReconcileRequired(
            "canonical recovery discovery finds "
            + ", ".join(found.review_run_id for found in recoverable)
            + " recoverable for this invocation; no Run is chosen by age, ID or position: reconcile required",
            reason="review_recovery_ambiguous",
        )
    return Discovery(recoverable[0] if recoverable else None, tuple(sorted(set_aside, key=lambda item: item["review_run_id"])))


def _held_named(review: ReviewStore, review_run_id: str, adapter: RecoveryAdapter) -> list[str]:
    """The Runs a held (own) Run's request sets aside, when its request reads; the held Run itself is not judged.

    Whether the caller's own Run is whole and valid is its own selector's to
    show, from its own record, so a held Run that does not read yet names
    nothing here rather than being reported as an incomplete matching Run.
    """
    try:
        chain = review.gate_chain(review_run_id)
    except ValidationError:
        return []
    if chain is None or not chain.generations[0].accepted_tasks:
        return []
    task_id = str(chain.generations[0].accepted_tasks[0]["task_id"])
    try:
        return adapter.named(review, MatchingRun(review_run_id, chain, {}, task_id))
    except ReconcileRequired:
        return []


# --------------------------------------------------------------------------- matching Runs

def _matching_runs(
    store: ProjectStore, review: ReviewStore, head: str | None, review_kind: str, operation_identity: str
) -> set[str]:
    found: set[str] = set()
    first_name = paths.generation_name(records.FIRST_GENERATION)
    if head is not None:
        for adding, names in committed.added_in_history(store.root, head, [paths.GATES_DIR]):
            for name in names:
                parts = name.split("/")
                if len(parts) != 5 or parts[4] != first_name or not is_valid_id(parts[3], "review_run"):
                    continue
                raw = gitcmd.blob_at(store.root, adding, name)
                if raw is None:
                    raise _incomplete(f"the generation 1 {name} added by {adding} cannot be read")
                try:
                    gate_one, _ = ReviewStore._parse(raw, f"{name} at {adding}", GateGeneration.from_record)
                except ValidationError as exc:
                    raise _incomplete(f"the generation 1 {name} added by {adding} does not read: {exc}") from exc
                if gate_one.review_kind == review_kind and gate_one.operation_identity == operation_identity:
                    found.add(parts[3])
    for review_run_id in review.run_ids():
        if review.read_bytes(paths.gate_rel(review_run_id, records.FIRST_GENERATION)) is None:
            continue
        gate_one = review.read_gate(review_run_id, records.FIRST_GENERATION)
        if gate_one.review_kind == review_kind and gate_one.operation_identity == operation_identity:
            found.add(review_run_id)
    return found


# --------------------------------------------------------------------------- clean persistence

def _run_record_paths(review: ReviewStore, head: str | None, review_run_id: str, chain: GateChain | None) -> list[str]:
    """Every path of the Run's records: its gates, snapshot, task input, Receipt, Supersession, Consumptions of it."""
    found: list[str] = []
    entries = review.entries(paths.run_dir(review_run_id)) or []
    found += [f"{paths.run_dir(review_run_id)}/{entry.name}" for entry in entries]
    if chain is None:
        return found
    first = chain.generations[0]
    found.append(paths.candidate_snapshot_rel(first.candidate_hash))
    if first.accepted_tasks:
        found.append(paths.task_input_rel(str(first.accepted_tasks[0]["task_id"])))
    receipts = [generation.receipt_id for generation in chain.generations if generation.receipt_id]
    for receipt_id in receipts:
        found.append(paths.receipt_rel(receipt_id))
        found.append(paths.supersession_rel(receipt_id))
    return found


def _consumption_paths_of(store: ProjectStore, review: ReviewStore, head: str | None, receipt_ids: set[str]) -> list[str]:
    """The Consumption paths naming one of ``receipt_ids``: in the working tree, and added anywhere in HEAD's history."""
    found: set[str] = set()
    for consumption_id in review.consumption_ids():
        if review.read_consumption(consumption_id).receipt_id in receipt_ids:
            found.add(paths.consumption_rel(consumption_id))
    if head is not None:
        for adding, names in committed.added_in_history(store.root, head, [paths.CONSUMPTIONS_DIR]):
            for name in names:
                raw = gitcmd.blob_at(store.root, adding, name)
                if raw is None:
                    raise _incomplete(f"the Consumption {name} added by {adding} cannot be read")
                try:
                    consumption, _ = ReviewStore._parse(raw, f"{name} at {adding}", records.consumption_from_record)
                except ValidationError as exc:
                    raise _incomplete(f"the Consumption {name} added by {adding} does not read: {exc}") from exc
                if consumption.receipt_id in receipt_ids:
                    found.add(name)
    return sorted(found)


def _clean_run(
    store: ProjectStore, review: ReviewStore, head: str | None, review_run_id: str,
    shape_of: Callable[[GateChain], "str | None"],
) -> MatchingRun:
    """The matching Run, proven cleanly persisted; ``review_recovery_incomplete`` otherwise."""
    repo = store.root
    try:
        chain = review.gate_chain(review_run_id)
    except ValidationError as exc:
        raise _incomplete(f"Review Run {review_run_id}'s chain does not validate: {exc}") from exc
    if chain is None:
        raise _incomplete(f"Review Run {review_run_id} has no generation in the working tree")
    if head is None:
        raise _incomplete(f"Review Run {review_run_id} is not committed: HEAD names no commit")
    shape = shape_of(chain)
    if shape:
        raise _incomplete(f"Review Run {review_run_id} {shape}")
    receipt_ids = {generation.receipt_id for generation in chain.generations if generation.receipt_id}
    try:
        record_paths = _run_record_paths(review, head, review_run_id, chain) + _consumption_paths_of(
            store, review, head, receipt_ids
        )
    except ValidationError as exc:
        raise _incomplete(f"the records of Review Run {review_run_id} do not read: {exc}") from exc
    # everything HEAD's history ever added is still in HEAD's tree, with the same blob
    run_prefix = paths.run_dir(review_run_id) + "/"
    targets = sorted({paths.run_dir(review_run_id)} | {relative for relative in record_paths if not relative.startswith(run_prefix)})
    added = committed.added_in_history(repo, head, targets)
    at_head = {entry.path: entry for entry in (gitcmd.tree_entries(repo, head, record_paths) or [])}
    for adding, names in added:
        for name in names:
            if name not in record_paths and not name.startswith(run_prefix):
                continue
            then = {entry.path: entry for entry in (gitcmd.tree_entries(repo, adding, [name]) or [])}
            if name not in at_head or name not in then or at_head[name].oid != then[name].oid:
                raise _incomplete(f"{name} of Review Run {review_run_id} was committed and is no longer in HEAD's tree as committed")
    # every record the working tree holds is committed and unchanged
    present = [relative for relative in record_paths if review.read_bytes(relative) is not None]
    try:
        gate.require_persisted(store, present)
    except StopError as exc:
        raise _incomplete(f"a record of Review Run {review_run_id} exists only in the working tree or differs from HEAD: {exc}") from exc
    for relative in present:
        entry = at_head.get(relative)
        if entry is None or entry.mode != "100644" or gitcmd.read_blob(repo, entry.oid) != review.read_bytes(relative):
            raise _incomplete(f"{relative} of Review Run {review_run_id} is not committed as its working-tree bytes")
    # every stage is whole
    first = chain.generations[0]
    task_id = str(first.accepted_tasks[0]["task_id"])
    if review.read_bytes(paths.candidate_snapshot_rel(first.candidate_hash)) is None or review.read_bytes(
        paths.task_input_rel(task_id)
    ) is None:
        raise _incomplete(f"generation 1 of Review Run {review_run_id} is not whole (snapshot and task input)")
    for generation in chain.generations:
        if generation.sealed and review.read_bytes(paths.receipt_rel(str(generation.receipt_id))) is None:
            raise _incomplete(f"the seal of Review Run {review_run_id} has no Receipt")
    if len(chain.generations) == planning.INVALIDATION_GENERATION:
        receipt_id = chain.generation(planning.SEAL_GENERATION).receipt_id
        if not review.supersession_exists(str(receipt_id)):
            raise _incomplete(f"generation 4 of Review Run {review_run_id} has no Supersession")
    # no pending mutation holds the Run's token
    if gate.pending_generation_mutations(store, review_run_id):
        raise _incomplete(f"a generation mutation of Review Run {review_run_id} is pending without its planning mutation")
    try:
        material = review.read_candidate_snapshot(first.candidate_hash).material or {}
    except ValidationError as exc:
        raise _incomplete(f"the snapshot of Review Run {review_run_id} does not read: {exc}") from exc
    return MatchingRun(review_run_id, chain, material, task_id)


def _shape_problem(chain: GateChain) -> str | None:
    generations = chain.generations
    if len(generations) > planning.INVALIDATION_GENERATION:
        return "has more than four generations"
    first = generations[0]
    if first.status != records.GATE_STATUS_OPEN or len(first.accepted_tasks) != 1 or first.settled_tasks:
        return "does not begin with one accepted, unsettled task"
    if len(generations) >= 2 and (generations[1].status != records.GATE_STATUS_OPEN or len(generations[1].settled_tasks) != 1):
        return "does not settle its task at generation 2"
    if len(generations) >= 3 and not generations[2].sealed:
        return "is not sealed at generation 3"
    if len(generations) == 4 and generations[3].status != records.GATE_STATUS_OPEN:
        return "does not invalidate at generation 4"
    return None


# --------------------------------------------------------------------------- classification (rows a-g)

def _classify(
    store: ProjectStore,
    review: ReviewStore,
    head: str | None,
    found: MatchingRun,
    named_aside: set[str],
    currency: Callable[[MatchingRun], Any],
) -> str | None:
    """The set-aside reason of a matching Run, or None for a recoverable one."""
    from . import publication
    from ..roadmap_review import entity_paths

    chain = found.chain
    latest = chain.latest.generation
    # a - invalidated
    if latest == planning.INVALIDATION_GENERATION:
        return planning.SET_ASIDE_INVALIDATED
    # b - a registration commit or a Consumption exists
    wanted = entity_paths(found.material)
    at_head = {entry.path for entry in (gitcmd.tree_entries(store.root, head or "", wanted) or [])}
    registering = [
        listed for listed, names in committed.added_in_history(store.root, head or "", wanted) if set(names) & set(wanted)
    ]
    receipt_ids = {generation.receipt_id for generation in chain.generations if generation.receipt_id}
    consumptions = _consumption_paths_of(store, review, head, receipt_ids) if receipt_ids else []
    if registering or at_head or consumptions:
        run = publication.RegisteredRun(
            planning.candidate_hash(found.material), found.material, tuple(wanted), tuple(registering)
        )
        failed = publication.committed_planning_proof(store.root, head or "", run)
        if failed is None:
            return planning.SET_ASIDE_CONSUMED
        raise _incomplete(
            f"Review Run {found.review_run_id} holds a registration or a Consumption that the committed planning "
            f"proof does not prove for HEAD ({failed[0]}: {failed[1]})"
        )
    # c - not authorized
    if latest == 2 and not planning.authorizes(chain.latest):
        return planning.SET_ASIDE_NOT_AUTHORIZED
    # d - set aside by another matching Run
    if found.review_run_id in named_aside:
        return planning.SET_ASIDE_SET_ASIDE
    # e - reconstruction
    problem = _reconstruction_problem(review, found)
    if problem:
        raise _incomplete(f"Review Run {found.review_run_id} does not reconstruct: {problem}")
    # f - generation 1, or an authorizing generation 2: currency on HEAD
    if latest in (1, 2):
        outcome = currency(found)
        if outcome.current:
            return None
        if outcome.stale:
            return outcome.detail
        raise _incomplete(f"Review Run {found.review_run_id}'s Candidate does not reproduce on HEAD: {outcome.detail}")
    # g - sealed, with no registration commit
    return None


def _reconstruction_problem(review: ReviewStore, found: MatchingRun) -> str | None:
    first = found.chain.generations[0]
    descriptor = first.accepted_tasks[0]
    problems = review.provenance_problems(descriptor, records.FIRST_GENERATION)
    if problems:
        return "; ".join(message for _, message in problems)
    try:
        task_input = review.read_task_input(found.task_id)
        planning.require_planning_candidate(found.material, "the snapshot's material")
    except ValidationError as exc:
        return str(exc)
    envelope_problems = planning.task_input_problems(
        task_input, found.material, first.candidate_hash, first.review_context_hash, first.effective_policy_hash
    )
    if envelope_problems:
        return "; ".join(envelope_problems)
    content = planning.candidate_content(found.material)
    target = content["roadmap"]["id"] if found.material["review_kind"] == planning.KIND_ROADMAP else content.get("phase_id")
    if first.target_identity != target or first.review_kind != found.material["review_kind"]:
        return "the Run's target or kind is not the Candidate's"
    context = task_input.request_envelope.get("context")
    provided = planning.KINDS.get(first.review_kind)
    if (
        provided is None or not isinstance(context, dict)
        or context.get("adapter_identity") != provided.adapter_identity
        or context.get("projection_semantics_version") != provided.projection_semantics_version
    ):
        return "the running implementation does not provide the adapter the Context names"
    return None


def _planning_named(review: ReviewStore, found: MatchingRun) -> list[str]:
    try:
        envelope = review.read_task_input(found.task_id).request_envelope
    except ValidationError as exc:
        raise _incomplete(f"the task input of Review Run {found.review_run_id} does not read: {exc}") from exc
    return [
        item["review_run_id"] for item in envelope.get("set_aside_runs") or []
        if isinstance(item, dict) and isinstance(item.get("review_run_id"), str)
    ]


#: Planning's policy, exactly as it was before the core was shared.
PLANNING = RecoveryAdapter(shape=_shape_problem, named=_planning_named, classify=_classify)


# --------------------------------------------------------------------------- the Work adapter (F4 §11.12, §26.5)


def _work_shape_problem(chain: GateChain) -> str | None:
    """The shapes a Work Run has: accepted, settled, sealed - and the one same-Run invalidation, its last generation."""
    problem = _shape_problem(chain)
    if problem:
        return problem
    generations = chain.generations
    if len(generations) >= 3 and generations[2].authorized_operation_stage != work_review.AUTHORIZED_OPERATION_STAGE:
        return "is not sealed for start:work-terminal at generation 3"
    if len(generations) == 4 and (
        generations[3].receipt_id is not None or generations[3].authorized_operation_stage is not None
        or generations[3].settled_tasks != generations[2].settled_tasks
    ):
        return "does not invalidate its seal at generation 4"
    return None


def _work_named(review: ReviewStore, found: MatchingRun) -> list[str]:
    """The Runs a version 2 Work request sets aside; a version 1 request names none (F4 §11.18.6)."""
    try:
        envelope = review.read_task_input(found.task_id).request_envelope
        named = work_review.request_set_aside(envelope, review_run_id=found.review_run_id)
    except ValidationError as exc:
        raise _incomplete(f"the task input of Review Run {found.review_run_id} does not read: {exc}") from exc
    return [item["review_run_id"] for item in named]


def _classify_work(
    store: ProjectStore,
    review: ReviewStore,
    head: str | None,
    found: MatchingRun,
    named_aside: set[str],
    currency: Callable[[MatchingRun], Any],
    owned: frozenset[str],
) -> str | None:
    """Rows a-g for a Work Run: the set-aside reason, or None for the recoverable one.

    ```text
    a  generation 4 (the same-Run invalidation)       invalidated   never resumed
    b  a Consumption of one of its Receipts exists     consumed      never resumed
    c  generation 2 does not authorize                 not_authorized
    d  named by another matching Run's request         set_aside
    e  does not reconstruct                            review_recovery_incomplete
    f  generation 1, or an authorizing generation 2    currency: current -> recoverable, stale -> its reason
    g  sealed at generation 3, unconsumed              recoverable
    ```

    Recoverable (f current, g) means resumable by the START mutation that
    reserved the Run; one no pending START mutation of this Work holds lacks
    what its resumption needs and is ``review_recovery_incomplete`` (e).
    """
    chain = found.chain
    latest = chain.latest.generation
    if latest == planning.INVALIDATION_GENERATION:
        return planning.SET_ASIDE_INVALIDATED
    receipt_ids = {generation.receipt_id for generation in chain.generations if generation.receipt_id}
    if receipt_ids and _consumption_paths_of(store, review, head, {str(item) for item in receipt_ids}):
        return planning.SET_ASIDE_CONSUMED
    if latest == 2 and not work_review.authorizes(chain.latest):
        return planning.SET_ASIDE_NOT_AUTHORIZED
    if found.review_run_id in named_aside:
        return planning.SET_ASIDE_SET_ASIDE
    problem = _work_reconstruction_problem(review, found)
    if problem:
        raise _incomplete(f"Work Review Run {found.review_run_id} does not reconstruct: {problem}")
    if latest in (1, 2):
        outcome = currency(found)
        if outcome.current:
            _require_owner(found, owned)
            return None
        if outcome.stale:
            return outcome.detail
        raise _incomplete(f"Work Review Run {found.review_run_id}'s Candidate is indeterminate: {outcome.detail}")
    _require_owner(found, owned)
    return None


def _require_owner(found: MatchingRun, owned: frozenset[str]) -> None:
    """A Run of a recoverable shape is recoverable only while a pending START mutation of its Work holds it.

    What its remaining stages consume is runtime material of the START
    mutation that reserved it, never a Review record: the reserved Run, task,
    Receipt and Consumption IDs (``start_review.select_in_flight`` reads the
    Run from them), the owner of its generation mutations
    (``start_review.resolve_pending_generation``), the bound ownership
    witnesses S-c1 requires (``start_review._result_commit``) and the
    pre-existing-dirty snapshot its commits are separated against, its S-c0 /
    S-c1 commits as C-1 owns them (W1), and its terminal stage. Another
    mutation cannot hold them: it reserves new IDs, binds recovered ones only
    as a recovery planning mutation, snapshots the bytes the lost START's
    executor wrote as changes from before it, and never adopts a commit it did
    not make. So the Run cannot be resumed and is incomplete.
    """
    if found.review_run_id not in owned:
        raise _incomplete(
            f"Work Review Run {found.review_run_id} has the shape of a recoverable Run, and no pending START mutation "
            "of this Work holds it: its reservations, its generation mutations' owner, the ownership witnesses and "
            "pre-existing-dirty snapshot its Candidate was frozen under, its S-c0 / S-c1 commits and its terminal "
            "stage are runtime material of the START mutation that began it, which no other mutation can hold"
        )


def _work_reconstruction_problem(review: ReviewStore, found: MatchingRun) -> str | None:
    first = found.chain.generations[0]
    descriptor = first.accepted_tasks[0]
    problems = review.provenance_problems(descriptor, records.FIRST_GENERATION)
    if problems:
        return "; ".join(message for _, message in problems)
    try:
        task_input = review.read_task_input(found.task_id)
        snapshot = review.read_candidate_snapshot(first.candidate_hash)
        candidate = (snapshot.material or {}).get("candidate") or {}
        width = len(str((candidate.get("declared_base") or {}).get("base_commit", "")))
        reconstruction = work_review.read_material(snapshot, first.candidate_hash, width)
    except (ValidationError, ReconcileRequired) as exc:
        return str(exc)
    envelope_problems = work_review.task_input_problems(
        task_input, found.material, first.candidate_hash, first.review_context_hash, first.effective_policy_hash,
        review_run_id=found.review_run_id,
    )
    if envelope_problems:
        return "; ".join(envelope_problems)
    work_id = reconstruction.candidate["declared_base"]["work"]["work_id"]
    if (
        first.review_kind != work_review.REVIEW_KIND or first.target_identity != work_id
        or first.operation_identity != work_review.operation_identity(work_id)
    ):
        return "the Run's kind, target or operation identity is not the Candidate's Work"
    return None
