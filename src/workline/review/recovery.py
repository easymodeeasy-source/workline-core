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

A valid committed explicit Human recovery disposition of a matching Run (RB10
N4, :mod:`workline.recovery_disposition`) is one more source of the same
set-aside relation the requests name: the Run is set aside with the stable
reason ``disposed_by_human`` and never selected again; a disposition that does
not hold its Run's exact witness stops the call (:func:`_human_dispositions`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .. import gitcmd
from ..errors import ReconcileRequired, StopError, ValidationError
from ..ids import is_valid_id
from ..store import ProjectStore
from . import checkout, committed, gate, p4, paths, planning, records, serialize, work_review
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
    #: The explicit contract the Run's generation-1 TaskInputs bind: a P4 contract, or ``None`` for v1.
    contract: str | None = None


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
    contract: str | None = None,
    human_decision: dict[str, Any] | None = None,
) -> Discovery:
    """Canonical recovery discovery (§12.2 steps 1-5) for one invocation; it begins nothing.

    ``currency`` evaluates a generation-1 or authorizing generation-2 Run's
    currency on HEAD, in the Roadmap-owned order; it answers ``current``,
    ``stale`` (with the reason) or ``mismatch``.

    Every matching Run is classified by the adapter of the contract its own
    generation-1 TaskInputs bind (§27.22): a v1 Run exactly as before, a P4
    Run by :func:`_classify_planning_p4`. ``contract`` is the invocation's
    (``None`` = v1): a Run of another contract is never recovered by it - a
    terminal one is set aside, any other refuses (``review_p4_contract_mismatch``).
    """
    if contract is None and human_decision is None:
        return _discover(store, review_kind, operation_identity, currency, PLANNING)
    adapter = RecoveryAdapter(
        shape=_shape_problem, named=_planning_named,
        classify=lambda store_, review, head, found, named_aside, currency_: _classify_versioned(
            store_, review, head, found, named_aside, currency_, contract, human_decision),
    )
    return _discover(store, review_kind, operation_identity, currency, adapter)


def discover_kind(store: ProjectStore, review_kind: str, operation_identity: str, adapter: RecoveryAdapter) -> Discovery:
    """The same canonical discovery for a kind whose owner supplies its own classification (P6, ORCH-RB6-1).

    Exactly :func:`_discover`: the matching Runs of ``review_kind`` and
    ``operation_identity`` from HEAD's history and the working tree, each proven
    whole under its own contract (P4-family Runs by :func:`_clean_p4_run`), the
    explicit Human dispositions, the adapter's classification, and
    ``review_recovery_ambiguous`` for more than one recoverable Run. No
    currency is evaluated: the owner's adapter needs none.
    """
    return _discover(store, review_kind, operation_identity, lambda found: None, adapter)


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
    disposed = _human_dispositions(store, review, matching, held)
    runs: dict[str, MatchingRun] = {}
    for review_run_id in sorted(matching - held):
        runs[review_run_id] = _clean_run(store, review, head, review_run_id, adapter.shape)
    named_aside: set[str] = set()
    for found in runs.values():
        named_aside.update(adapter.named(review, found))
    for review_run_id in sorted(matching & held):
        named_aside.update(_held_named(review, review_run_id, adapter))
    # RB10 N4 §35.15: an explicit Human disposition is one more source of the SAME set-aside relation.
    named_aside.update(disposed)
    recoverable: list[MatchingRun] = []
    set_aside: list[dict[str, str]] = []
    for review_run_id, found in runs.items():
        reason = adapter.classify(store, review, head, found, named_aside, currency)
        if reason == planning.SET_ASIDE_SET_ASIDE and review_run_id in disposed:
            reason = _DISPOSED_BY_HUMAN  # propagated by its stable code, never by the Human's free-form reason
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


#: The stable set-aside reason of a Run an explicit Human recovery disposition sets aside (RB10 N4 §35.15).
_DISPOSED_BY_HUMAN = "disposed_by_human"


def _human_dispositions(
    store: ProjectStore, review: ReviewStore, matching: set[str], held: frozenset[str]
) -> frozenset[str]:
    """The matching Runs a valid committed Human recovery disposition sets aside (RB10 N4 §35.15, §35.18).

    Read from recovery authority's own records (:mod:`workline.recovery_disposition`),
    each held to its Run's exact recovery witness. A disposition written and
    not committed yet sets nothing aside. One that does not hold - a record
    that does not read, a Run whose records changed, a Run holding a current
    Receipt - and one naming a Run a pending START mutation holds, stop the
    call: broken disposition authority fails closed.
    """
    from .. import recovery_disposition as disposition

    if not matching or not disposition.namespace_present(store):
        return frozenset()
    found: set[str] = set()
    for review_run_id in sorted(matching):
        state = disposition.review_run_target_state(store, review_run_id, review)
        if state.state == disposition.STATE_INVALID:
            raise _incomplete(f"the recovery disposition of Review Run {review_run_id} does not hold ({state.problem})")
        if state.state != disposition.STATE_EFFECTIVE:
            continue
        if review_run_id in held:
            raise _incomplete(
                f"Review Run {review_run_id} is set aside by an explicit Human recovery disposition, and a pending START "
                "mutation of this Work holds it"
            )
        found.add(review_run_id)
    return frozenset(found)


#: What :func:`disposition_outcome` finds for one Run (RB10 N4 §35.10).
OUTCOME_RECOVERABLE = "recoverable"
OUTCOME_SET_ASIDE = "set_aside"
OUTCOME_UNOWNED = "unowned"
OUTCOME_UNRESOLVED = "unresolved"


def disposition_outcome(
    store: ProjectStore, review_run_id: str, *, currency: Callable[[MatchingRun], Any]
) -> tuple[str, str]:
    """How the generalized recovery classifier treats one Work Review Run, for a Human disposition; it writes nothing.

    The read-only, per-Run form of :func:`discover_work` for the case the
    disposition operation allows (no pending mutation at all, so nothing is
    owned or held): every Run matching the target's Work is proven whole and
    the Runs their requests and valid Human dispositions set aside are
    harvested exactly as discovery does, and the target is classified by the
    unchanged Work policy (:func:`_classify_work`, :func:`_require_owner`
    untouched):

    ```text
    a set-aside reason                       set_aside     (already resolved)
    recoverable                              recoverable
    review_recovery_incomplete, and the very
    same classification with the Run owned
    makes it recoverable                     unowned       (the one owner-supported non-resumable case)
    anything else                            unresolved    (a malformed or ambiguous namespace)
    ```

    A planning Run is ``unresolved``: its recovery classification is made
    against the planning request that would resume it, which no Human
    disposition has.
    """
    review = ReviewStore(store)
    try:
        chain = review.gate_chain(review_run_id)
    except ValidationError as exc:
        return OUTCOME_UNRESOLVED, str(exc)
    if chain is None:
        return OUTCOME_UNRESOLVED, f"Review Run {review_run_id} holds no gate generation"
    first = chain.generations[0]
    if first.review_kind != work_review.REVIEW_KIND:
        return OUTCOME_UNRESOLVED, (
            f"Review Run {review_run_id} is a {first.review_kind} Run, classified only against the planning request "
            "that would resume it"
        )
    try:
        checkout.require_namespace_readable(store)
        head = gitcmd.head_commit(store.root)
        matching = _matching_runs(store, review, head, first.review_kind, first.operation_identity)
        if review_run_id not in matching:
            return OUTCOME_UNRESOLVED, f"Review Run {review_run_id} is not a matching Run of its own Work"
        disposed = _human_dispositions(store, review, matching, frozenset())
        runs = {found: _clean_run(store, review, head, found, _work_shape_problem) for found in sorted(matching)}
        named_aside: set[str] = set(disposed)
        for found in runs.values():
            named_aside.update(_work_named(review, found))
    except StopError as exc:
        return OUTCOME_UNRESOLVED, str(exc)
    target = runs[review_run_id]
    try:
        reason = _classify_work(store, review, head, target, named_aside, currency, frozenset())
    except ReconcileRequired as exc:
        if exc.reason != "review_recovery_incomplete":
            return OUTCOME_UNRESOLVED, str(exc)
        try:
            owned = _classify_work(store, review, head, target, named_aside, currency, frozenset({review_run_id}))
        except StopError:
            return OUTCOME_UNRESOLVED, str(exc)
        return (OUTCOME_UNOWNED if owned is None else OUTCOME_UNRESOLVED), str(exc)
    except StopError as exc:
        return OUTCOME_UNRESOLVED, str(exc)
    if reason is None:
        return OUTCOME_RECOVERABLE, f"Review Run {review_run_id} is the one recoverable Run of its Work"
    return OUTCOME_SET_ASIDE, reason


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
    contract = run_contract(review, chain)
    if contract is not None:
        return _clean_p4_run(store, review, head, review_run_id, chain, contract)
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
    _require_clean_paths(store, review, head, review_run_id, record_paths)
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


def _require_clean_paths(
    store: ProjectStore, review: ReviewStore, head: str, review_run_id: str, record_paths: list[str]
) -> None:
    """A Run's records are committed as HEAD's history added them, and the working tree holds them unchanged."""
    repo = store.root
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


#: Planning's policy, exactly as it was before the core was shared, for every v1 Run; a P4 Run is classified by its
#: own contract (:func:`_classify_versioned`), and a v1 invocation never recovers it.
PLANNING = RecoveryAdapter(
    shape=_shape_problem, named=_planning_named,
    classify=lambda store, review, head, found, named_aside, currency: _classify_versioned(
        store, review, head, found, named_aside, currency, None, None),
)


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
    if found.contract is not None:
        return _classify_work_p4(store, review, head, found, named_aside, currency, owned)
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


# --------------------------------------------------------------------------- P4: versioned per-Run dispatch (§27.22)


def run_contract(review: ReviewStore, chain: GateChain) -> str | None:
    """The explicit P4 contract a Run's generation-1 TaskInputs bind, or ``None`` (a v1 Run, or unreadable)."""
    first = chain.generations[0]
    try:
        found = {p4.contract_of_task_input(review.read_task_input(str(task["task_id"]))) for task in first.accepted_tasks}
    except ValidationError:
        return None
    return found.pop() if len(found) == 1 and None not in found else None


def p4_record_paths(review: ReviewStore, review_run_id: str, chain: GateChain) -> list[str]:
    """Every record path a P4 Run's chain names: gates, snapshots, every TaskInput, reports, adjudication,
    Repair Batch / Result (and Candidate N+1), Receipt and Supersession."""
    found: list[str] = [f"{paths.run_dir(review_run_id)}/{entry.name}" for entry in (review.entries(paths.run_dir(review_run_id)) or [])]
    first = chain.generations[0]
    found.append(paths.candidate_snapshot_rel(first.candidate_hash))
    found += [paths.task_input_rel(str(task["task_id"])) for task in chain.latest.accepted_tasks]
    discovery = {str(task["task_id"]) for task in p4.discovery_tasks(chain)}
    found += [paths.report_rel(str(task["result_digest"])) for task in chain.latest.settled_tasks
              if str(task["task_id"]) in discovery]
    if len(chain.generations) >= p4.ADJUDICATION_SETTLE_GENERATION:
        found.append(paths.adjudication_rel(review_run_id))
    repair = p4.repair_task(chain)
    if repair is not None:
        batch_id = str(review.read_task_input(str(repair["task_id"])).request_envelope.get("repair_batch_id"))
        found.append(paths.repair_batch_rel(batch_id))
        if len(chain.generations) == p4.REPAIR_SETTLE_GENERATION:
            found.append(paths.repair_result_rel(batch_id))
            found.append(paths.candidate_snapshot_rel(review.read_repair_result(batch_id).result_candidate_hash))
    for generation in chain.generations:
        if generation.receipt_id:
            found += [paths.receipt_rel(generation.receipt_id), paths.supersession_rel(generation.receipt_id)]
    # P5 (P-5): the history the Run's own generations wrote, derived from its canonical records, never from file
    # presence - generation 1's set-aside summaries and Human Decision Evidence, its own G2 / G4 / G6 Run summary,
    # G4's Finding summaries and relations, G6's Repair summary. None for a P4-only Run.
    found += p4.run_history_paths(review, review_run_id, chain)
    return found


def _clean_p4_run(
    store: ProjectStore, review: ReviewStore, head: str, review_run_id: str, chain: GateChain, contract: str
) -> MatchingRun:
    """A matching P4 Run, proven cleanly persisted and whole under its own shape; incomplete otherwise."""
    problems = p4.chain_problems(chain)
    if problems:
        raise _incomplete(f"P4 Review Run {review_run_id} is not a P4 shape: " + "; ".join(problems))
    receipt_ids = {generation.receipt_id for generation in chain.generations if generation.receipt_id}
    try:
        consumptions = _consumption_paths_of(store, review, head, {str(item) for item in receipt_ids})
        record_paths = p4_record_paths(review, review_run_id, chain) + consumptions
        if consumptions and p4.is_history_policy(p4.run_policy(review, chain)):
            # §28.6: a consumed P5 (or P6, R6-1) Run's summary is made canonical by the same transition as its
            # Consumption
            record_paths.append(paths.history_run_rel(review_run_id))
    except (ValidationError, ReconcileRequired) as exc:
        raise _incomplete(f"the records of P4 Review Run {review_run_id} do not read: {exc}") from exc
    _require_clean_paths(store, review, head, review_run_id, record_paths)
    wanted = [relative for relative in record_paths if not relative.startswith(paths.run_dir(review_run_id) + "/")
              and not relative.startswith(paths.SUPERSESSIONS_DIR + "/") and not relative.startswith(paths.CONSUMPTIONS_DIR + "/")]
    missing = [relative for relative in wanted if review.read_bytes(relative) is None]
    if missing:
        raise _incomplete(f"P4 Review Run {review_run_id} is not whole: {', '.join(missing)} missing")
    if p4.shape_of(chain) == p4.SHAPE_SEAL and len(chain.generations) == p4.INVALIDATION_GENERATION:
        if not review.supersession_exists(str(chain.generation(p4.SEAL_GENERATION).receipt_id)):
            raise _incomplete(f"generation 6 of P4 Review Run {review_run_id} invalidates with no Supersession")
    if gate.pending_generation_mutations(store, review_run_id):
        raise _incomplete(f"a generation mutation of P4 Review Run {review_run_id} is pending without its owner")
    first = chain.generations[0]
    try:
        material = review.read_candidate_snapshot(first.candidate_hash).material or {}
    except ValidationError as exc:
        raise _incomplete(f"the snapshot of P4 Review Run {review_run_id} does not read: {exc}") from exc
    return MatchingRun(review_run_id, chain, material, str(first.accepted_tasks[0]["task_id"]), contract)


def _classify_versioned(
    store: ProjectStore,
    review: ReviewStore,
    head: str | None,
    found: MatchingRun,
    named_aside: set[str],
    currency: Callable[[MatchingRun], Any],
    contract: str | None,
    human_decision: dict[str, Any] | None,
) -> str | None:
    """Each matching Run by its own contract's classifier; a Run of another contract is never recovered."""
    if found.contract is None:
        reason = _classify(store, review, head, found, named_aside, currency)
    else:
        reason = _classify_planning_p4(store, review, head, found, named_aside, currency, human_decision)
    if reason is None and found.contract != contract:
        raise p4.reconcile(
            f"Review Run {found.review_run_id} is recoverable under contract {found.contract or planning.PLANNING_CONTRACT}, "
            f"and this invocation runs under {contract or planning.PLANNING_CONTRACT}; it is resumed only under its own "
            "contract, never upgraded or downgraded",
            p4.REASON_CONTRACT_MISMATCH,
        )
    return reason


def _classify_planning_p4(
    store: ProjectStore,
    review: ReviewStore,
    head: str | None,
    found: MatchingRun,
    named_aside: set[str],
    currency: Callable[[MatchingRun], Any],
    human_decision: dict[str, Any] | None,
) -> str | None:
    """The P4 planning classification (§27.22, G-2, G-3, G-4): the set-aside reason, or None for the recoverable one.

    ```text
    G6 invalidation of a G5 seal                         invalidated          (G-3: terminal)
    G6 repair settled, positively replaced by a successor p4_repaired         (G-2: before any registration reading)
    registration / Consumption, proven                   consumed
    G2 with a declined discovery                         not_authorized
    named by another matching Run                        set_aside
    G4 HUMAN_WAIT, and this invocation decides           human_decision       (G-4)
    does not reconstruct                                 review_recovery_incomplete
    G1-G4 (not HUMAN_WAIT)                               currency
    G4 HUMAN_WAIT, G5 seal, G5 repair, G6 settled        recoverable
    ```
    """
    from . import publication
    from ..roadmap_review import entity_paths

    chain = found.chain
    latest = chain.latest.generation
    shape = p4.shape_of(chain)
    if shape == p4.SHAPE_SEAL and latest == p4.INVALIDATION_GENERATION:
        return planning.SET_ASIDE_INVALIDATED
    if shape == p4.SHAPE_REPAIR and latest == p4.REPAIR_SETTLE_GENERATION:
        if p4.proven_successor(review, found.review_run_id, chain) is not None:
            return p4.SET_ASIDE_REPAIRED
        if p4.named_by_successor(review, found.review_run_id):
            raise _incomplete(
                f"P4 Review Run {found.review_run_id} is named by a successor whose replacement cannot be positively proven"
            )
    wanted = entity_paths(found.material)
    at_head = {entry.path for entry in (gitcmd.tree_entries(store.root, head or "", wanted) or [])}
    registering = [
        listed for listed, names in committed.added_in_history(store.root, head or "", wanted) if set(names) & set(wanted)
    ]
    receipt_ids = {generation.receipt_id for generation in chain.generations if generation.receipt_id}
    consumptions = _consumption_paths_of(store, review, head, {str(r) for r in receipt_ids}) if receipt_ids else []
    if registering or at_head or consumptions:
        if shape != p4.SHAPE_SEAL:
            raise _incomplete(
                f"P4 Review Run {found.review_run_id} is not sealed and its reserved paths are registered by a Run not "
                "proven to replace it"
            )
        run = publication.RegisteredRun(
            planning.candidate_hash(found.material), found.material, tuple(wanted), tuple(registering)
        )
        failed = publication.committed_planning_proof(store.root, head or "", run)
        if failed is None:
            return planning.SET_ASIDE_CONSUMED
        raise _incomplete(
            f"P4 Review Run {found.review_run_id} holds a registration or a Consumption the committed planning proof "
            f"does not prove for HEAD ({failed[0]}: {failed[1]})"
        )
    if latest == p4.DISCOVERY_SETTLE_GENERATION and any(
        task["status"] != records.TASK_SETTLED_OK for task in chain.latest.settled_tasks
    ):
        return planning.SET_ASIDE_NOT_AUTHORIZED
    if found.review_run_id in named_aside:
        return planning.SET_ASIDE_SET_ASIDE
    waiting = latest == p4.ADJUDICATION_SETTLE_GENERATION and review.read_adjudication(found.review_run_id).outcome == p4.HUMAN_WAIT
    if waiting and human_decision is not None:
        bound = review.read_task_input(found.task_id).request_envelope.get("human_decision")
        if bound != human_decision:
            return p4.SET_ASIDE_HUMAN_DECISION
    problem = _p4_reconstruction_problem(review, found)
    if problem:
        raise _incomplete(f"P4 Review Run {found.review_run_id} does not reconstruct: {problem}")
    if latest <= p4.ADJUDICATION_SETTLE_GENERATION and not waiting:
        outcome = currency(found)
        if outcome.current:
            return None
        if outcome.stale:
            return outcome.detail
        raise _incomplete(f"P4 Review Run {found.review_run_id}'s Candidate does not reproduce on HEAD: {outcome.detail}")
    return None


def p4_reconstruction_problem(review: ReviewStore, found: MatchingRun) -> str | None:
    """The shared P4 reconstruction row (e) for a kind adapter (P6 ORCH-RB6-1-R3): exactly
    :func:`_p4_reconstruction_problem` - every accepted task's provenance at its accepting generation."""
    return _p4_reconstruction_problem(review, found)


def _p4_reconstruction_problem(review: ReviewStore, found: MatchingRun) -> str | None:
    """Every accepted task's provenance at its accepting generation, and the discovery requests' bindings."""
    chain = found.chain
    first = chain.generations[0]
    for task in chain.latest.accepted_tasks:
        accepted_at = chain.accepted_at(str(task["task_id"]))
        problems = review.provenance_problems(task, int(accepted_at or 0))
        if problems:
            return "; ".join(message for _, message in problems)
    if planning.is_planning_candidate(found.material):
        try:
            planning.require_planning_candidate(found.material, "the snapshot's material")
        except ValidationError as exc:
            return str(exc)
        for task in p4.discovery_tasks(chain):
            problems = planning.task_input_problems_p4(
                review.read_task_input(str(task["task_id"])), found.material, first.candidate_hash,
                first.review_context_hash,
            )
            if problems:
                return "; ".join(problems)
        content = planning.candidate_content(found.material)
        target = content["roadmap"]["id"] if found.material["review_kind"] == planning.KIND_ROADMAP else content.get("phase_id")
        if first.target_identity != target or first.review_kind != found.material["review_kind"]:
            return "the Run's target or kind is not the Candidate's"
    return None


def _classify_work_p4(
    store: ProjectStore,
    review: ReviewStore,
    head: str | None,
    found: MatchingRun,
    named_aside: set[str],
    currency: Callable[[MatchingRun], Any],
    owned: frozenset[str],
) -> str | None:
    """The P4 Work classification (§27.22, G-3, G-4): terminal states are set aside; anything else is
    recoverable only through the START mutation that holds it (a Work Run is resumed only by its owner)."""
    chain = found.chain
    latest = chain.latest.generation
    shape = p4.shape_of(chain)
    if shape == p4.SHAPE_SEAL and latest == p4.INVALIDATION_GENERATION:
        return planning.SET_ASIDE_INVALIDATED
    if shape == p4.SHAPE_REPAIR and latest == p4.REPAIR_SETTLE_GENERATION \
            and p4.proven_successor(review, found.review_run_id, chain) is not None:
        return p4.SET_ASIDE_REPAIRED
    receipt_ids = {generation.receipt_id for generation in chain.generations if generation.receipt_id}
    if receipt_ids and _consumption_paths_of(store, review, head, {str(item) for item in receipt_ids}):
        return planning.SET_ASIDE_CONSUMED
    if latest == p4.DISCOVERY_SETTLE_GENERATION and any(
        task["status"] != records.TASK_SETTLED_OK for task in chain.latest.settled_tasks
    ):
        return planning.SET_ASIDE_NOT_AUTHORIZED
    if found.review_run_id in named_aside:
        return planning.SET_ASIDE_SET_ASIDE
    problem = _p4_reconstruction_problem(review, found)
    if problem:
        raise _incomplete(f"P4 Work Review Run {found.review_run_id} does not reconstruct: {problem}")
    waiting = latest == p4.ADJUDICATION_SETTLE_GENERATION and review.read_adjudication(found.review_run_id).outcome == p4.HUMAN_WAIT
    if latest <= p4.ADJUDICATION_SETTLE_GENERATION and not waiting:
        outcome = currency(found)
        if outcome.stale:
            return outcome.detail
        if not outcome.current:
            raise _incomplete(f"P4 Work Review Run {found.review_run_id}'s Candidate is indeterminate: {outcome.detail}")
    _require_owner(found, owned)
    return None
