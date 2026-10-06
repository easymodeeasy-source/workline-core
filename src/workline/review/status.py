"""Review status: a read-only diagnostic projection of the canonical Review records.

The Review part of ``run-workline.py status`` (``rules/git``: Read-only status).
It reads the canonical Review records through their existing public readers -
:class:`~workline.review.store.ReviewStore` and the activation reader of
:mod:`workline.review.activation` - and says, by stable codes, what they hold:

* whether the Review namespace exists, and whether it can be read at all;
* the Work-terminal activation: ``absent``, ``present`` (the record HEAD
  commits, held unchanged by the working tree, whose prefix digest the event
  log reproduces) or ``invalid`` with the exact reason - never ``absent`` for a
  record that is there but broken;
* each Review Run: its kind, target, latest generation, and a state derived
  only where the canonical records show it mechanically - ``open``,
  ``sealed``, ``invalidated``, ``consumed``, ``set_aside`` or ``invalid`` - and
  its blocking obligations where its Review contract (P4) gives them;
* the pending Review obligation summary over the current P4 Runs.

``set_aside`` is projected only from positive successor evidence (F4 §11.6,
§11.18.6; P4 §27.13, §27.21, G-2, G-4): the stored request of another Work or
planning Run names this exact Run, read by the one fail-closed reader its
Review contract owns, and this Run is another Run of the same Review kind and
operation identity. The contract is the one generation 1's TaskInputs bind
explicitly (:func:`workline.review.p4.contract_of_task_input`); each kind and
contract has its reader, never a parser here:

```text
Work, v1 contract        work_review.request_set_aside   the request generation 1's one task input
                                                         carries, bound by its digest: version 1 names
                                                         no Run, version 2 its exact validated list
planning, v1 contract    planning.request_set_aside      the same, for the planning request
Work / planning, P4      p4.set_aside_named              every discovery request generation 1 accepted,
                                                         bound by digest, one validated list; a Run named
                                                         as repaired only with its proven successor
                                                         (p4.proven_successor), one named by a Human
                                                         decision only while it waits at G4 HUMAN_WAIT
```

Never age, ID or filename order, generation count, a successor reservation, or
an ID that appears anywhere else. Precedence: a Run whose own records do not
read stays ``invalid``; an ``invalidated`` or ``consumed`` Run stays so; only
an ``open`` Run, or a ``sealed`` one whose Receipt is known to be unconsumed,
becomes ``set_aside``. The Run that names it keeps its own state. A request
that does not read or is refused, a linkage the canonical records do not
prove, a name that is not another matching Run of this namespace, or a naming
cycle sets nothing aside: the naming Run is ``invalid`` with the exact code and
the identities involved. A P4 Run's request schema is never read as a v1 one.

Each Run's ``blocking_obligations`` follow the same explicit contract (§9.7,
§29.18): a v1 Run's are ``not_available_by_contract``; a P4 Run's are what the
one P4 reader of them, :func:`workline.review.p4.blocking_obligations`, says -
``pending`` before the canonical adjudication (never 0), ``available`` with its
count after it. P4 obligation records that do not read make the Run
``invalid`` with the reader's code, as a Receipt that does not read does; an
``invalid`` Run never shows a count. ``pending_obligations`` sums the counts of
the Runs that are neither v1 nor terminal (``consumed``, ``invalidated``,
``set_aside``), and is ``pending`` or ``invalid`` - never a number - while one of
them has no adjudication yet or does not read.

It is not lifecycle truth and never overrides it: nothing here reads or
derives Work, Phase or Roadmap state. It writes nothing, takes no lock, opens
no mutation and launches no reviewer, and it carries no raw reviewer output or
request payload - only identities, states and the codes of what could not be
read.
"""

from __future__ import annotations

from typing import Any

from ..errors import StopError, ValidationError
from ..store import ProjectStore
from . import activation as work_activation
from . import p4, planning, work_review
from .records import GateGeneration
from .store import GateChain, ReviewStore
from .validate import ACTIVATION_PREFIX_MISMATCH

NAMESPACE_ABSENT = "absent"
NAMESPACE_PRESENT = "present"
NAMESPACE_INVALID = "invalid"

ACTIVATION_ABSENT = "absent"
ACTIVATION_PRESENT = "present"
ACTIVATION_INVALID = "invalid"

RUN_OPEN = "open"
RUN_SEALED = "sealed"
RUN_INVALIDATED = "invalidated"
RUN_SET_ASIDE = "set_aside"
RUN_CONSUMED = "consumed"
RUN_INVALID = "invalid"
RUN_STATES = (RUN_OPEN, RUN_SEALED, RUN_INVALIDATED, RUN_SET_ASIDE, RUN_CONSUMED, RUN_INVALID)

#: A count or summary the Run's Review contract does not give: a v1 Run has no obligation count.
NOT_AVAILABLE_BY_CONTRACT = "not_available_by_contract"

#: Blocking-obligation states (§9.7, §29.18): a P4 Run with no canonical adjudication yet, one whose count its
#: adjudication gives, a Run whose own records do not read (never a count); the summary when no Run can be listed.
OBLIGATIONS_PENDING = "pending"
OBLIGATIONS_AVAILABLE = "available"
OBLIGATIONS_INVALID = "invalid"
OBLIGATIONS_UNAVAILABLE = "unavailable"
#: The Run states whose obligations are history: they never add to the current summary.
_TERMINAL = (RUN_CONSUMED, RUN_INVALIDATED, RUN_SET_ASIDE)


def _reason(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _failure(exc: Exception) -> dict[str, str]:
    return _reason(getattr(exc, "code", None) or type(exc).__name__, str(exc))


def activation_status(store: ProjectStore, review: ReviewStore | None = None) -> dict[str, Any]:
    """The Work-terminal activation as the current HEAD commits it and the working tree holds it."""
    from . import hermetic

    review = review or ReviewStore(store)
    try:
        with hermetic.read_only(store.root) as git:
            found = work_activation.current_activation(review, git, work_activation.head_commit(git))
    except work_activation.CommittedRecordUnreadable as exc:
        return _activation(ACTIVATION_INVALID, reason=_failure(exc))
    except ValidationError as exc:
        return _activation(ACTIVATION_INVALID, reason=_failure(exc))
    except StopError as exc:
        # HEAD's record cannot be read at all. As validation does, a working record is then never taken for
        # the committed one - and with none, nothing claims an activation.
        try:
            claimed = review.activation_exists()
        except ValidationError as inner:
            return _activation(ACTIVATION_INVALID, reason=_failure(inner))
        if claimed:
            return _activation(
                ACTIVATION_INVALID,
                reason=_reason(exc.code, f"the activation record cannot be shown to be the one HEAD commits ({exc})"),
            )
        return _activation(ACTIVATION_ABSENT, reason=_failure(exc))
    if found.state == work_activation.NOT_ACTIVATED:
        return _activation(ACTIVATION_ABSENT)
    if found.record is None:
        return _activation(ACTIVATION_INVALID, reason=_reason("review_record_conflict", found.conflict() or found.state))
    record = found.record
    try:
        data = store.events_jsonl.read_bytes()
    except OSError:
        data = None
    events = None if data is None else work_activation.parse_event_log(data)
    if events is None or work_activation.prefix_digest(events, record.legacy_event_count) != record.legacy_event_prefix_sha256:
        return _activation(
            ACTIVATION_INVALID,
            record,
            reason=_reason(
                ACTIVATION_PREFIX_MISMATCH,
                f"the activation fixes {record.legacy_event_count} pre-activation Events by their digest, and this "
                "event log does not reproduce it",
            ),
        )
    return _activation(ACTIVATION_PRESENT, record)


def _activation(state: str, record: Any = None, *, reason: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "status": state,
        "operation_contract": None if record is None else record.operation_contract,
        "legacy_event_count": None if record is None else record.legacy_event_count,
        "activation_base_head": None if record is None else record.activation_base_head,
        "reason": reason,
    }


def _run_entry(review_run_id: str) -> dict[str, Any]:
    return {
        "review_run_id": review_run_id,
        "review_kind": None,
        "target_identity": None,
        "latest_generation": None,
        "state": RUN_INVALID,
        "receipt": {"status": "none", "receipt_id": None, "reason": None},
        "consumption": {"status": "none", "consumption_id": None, "reason": None},
        "blocking_obligations": {"status": NOT_AVAILABLE_BY_CONTRACT, "count": None},
        "reason": None,
    }


def _runs(review: ReviewStore) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    try:
        run_ids = sorted(review.run_ids())
    except ValidationError as exc:
        return [], _failure(exc)
    try:
        by_receipt: dict[str, Any] | None = review.consumption_by_receipt()
        consumptions_reason = None
    except ValidationError as exc:
        by_receipt, consumptions_reason = None, _failure(exc)
    runs: list[dict[str, Any]] = []
    firsts: dict[str, GateGeneration] = {}
    whole: dict[str, GateChain] = {}
    obligations: dict[str, dict[str, Any]] = {}
    for review_run_id in run_ids:
        entry = _run_entry(review_run_id)
        runs.append(entry)
        try:
            chain = review.gate_chain(review_run_id)
        except ValidationError as exc:
            entry["reason"] = _failure(exc)
            continue
        if chain is None:
            entry["reason"] = _reason(
                "review_namespace_invalid", f"Review Run {review_run_id} holds no gate generation"
            )
            continue
        firsts[review_run_id] = chain.generations[0]
        latest = chain.latest
        entry.update(
            review_kind=latest.review_kind, target_identity=latest.target_identity, latest_generation=latest.generation
        )
        superseded = chain.superseded_receipts()
        receipt_id = latest.receipt_id if latest.sealed else (superseded[-1] if superseded else None)
        if receipt_id is not None:
            entry["receipt"]["receipt_id"] = receipt_id
            if latest.sealed:
                try:
                    review.read_receipt(receipt_id)
                    entry["receipt"]["status"] = "issued"
                except ValidationError as exc:
                    entry["receipt"].update(status="invalid", reason=_failure(exc))
                    entry["reason"] = _failure(exc)
                    continue
            else:
                entry["receipt"]["status"] = "superseded"
        if by_receipt is None:
            entry["consumption"].update(status="unavailable", reason=consumptions_reason)
        elif receipt_id is not None and receipt_id in by_receipt:
            entry["consumption"].update(status="consumed", consumption_id=by_receipt[receipt_id].consumption_id)
        if latest.sealed:
            entry["state"] = RUN_CONSUMED if entry["consumption"]["status"] == "consumed" else RUN_SEALED
        else:
            entry["state"] = RUN_INVALIDATED if superseded else RUN_OPEN
        try:
            obligations[review_run_id] = _run_obligations(review, review_run_id, chain.generations[0], chain)
        except ValidationError as exc:
            # its own P4 obligation records do not read: as for a Receipt, it is invalid, sets nothing aside,
            # and is never set aside
            _invalid(entry, _failure(exc))
            continue
        whole[review_run_id] = chain
    _project_set_aside(review, runs, firsts, whole)
    _project_obligations(review, runs, firsts, obligations)
    return runs, None


# --------------------------------------------------------------------------- set-aside linkage (F4 §11.6, §11.18.6)


class _LinkageInvalid(Exception):
    """A naming Run's set-aside linkage cannot be shown: the reason, by code and identities only."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.reason = _reason(code, message)


#: The v1 request reader of each Review kind whose requests name set-aside Runs: the kind's label, its one
#: fail-closed reader, and how that reader is described when it refuses (its own text may quote the payload).
_WORK_V1 = (
    "Work", work_review.request_set_aside,
    "the Work request version reader (version 1 names no Run; version 2 names exactly its validated list, in "
    "canonical order)",
)
_PLANNING_V1 = (
    "planning", planning.request_set_aside,
    "the planning request reader (exactly its validated list of set-aside Runs, in canonical order)",
)
_V1_READERS: dict[str, tuple[str, Any, str]] = {
    work_review.REVIEW_KIND: _WORK_V1, **{kind: _PLANNING_V1 for kind in planning.PLANNING_KINDS},
}
#: The P4 contract each such kind's P4 Runs bind (G-6 Option M); the P4 linkage reader is one for both.
_P4_CONTRACTS = {
    work_review.REVIEW_KIND: work_review.P4_CONTRACT,
    **{kind: planning.P4_CONTRACT for kind in planning.PLANNING_KINDS},
}
_P4_READER = (
    "the P4 linkage reader (every discovery request bound by digest, naming one validated list of set-aside Runs "
    "in canonical order; a Run named as repaired only with its proven successor, one named by a Human decision "
    "only while it waits at G4 HUMAN_WAIT)"
)


def _label(first: GateGeneration) -> str:
    return _V1_READERS[first.review_kind][0]


def _contracts(review: ReviewStore, chain: GateChain) -> set[str | None]:
    """The Review contracts generation 1's readable TaskInputs bind explicitly (``None`` = v1).

    A TaskInput that does not read is left to the request reader of the Run's
    contract, which reports it with its own code.
    """
    found: set[str | None] = set()
    for task in chain.generations[0].accepted_tasks:
        try:
            found.add(p4.contract_of_task_input(review.read_task_input(str(task["task_id"]))))
        except ValidationError:
            continue
    return found


def _v1_request_names(
    review: ReviewStore, review_run_id: str, chain: GateChain, label: str, reader: Any, described: str,
) -> list[str]:
    """The Runs the stored v1 request of Run ``review_run_id`` sets aside, by its kind's one request reader.

    The request is the one in the task input generation 1 accepted, and only
    while that task input's digest is the one the accepted task binds. The
    reader (:func:`work_review.request_set_aside`, :func:`planning.request_set_aside`)
    reads it fail-closed and refuses anything its writer never writes. The
    reader's text is not carried: it may quote the stored payload.
    """
    first = chain.generations[0]
    if len(first.accepted_tasks) != 1:
        raise _LinkageInvalid(
            "review_record_invalid",
            f"generation 1 of {label} Review Run {review_run_id} does not accept exactly one task, so no one request of "
            "it can be read",
        )
    descriptor = first.accepted_tasks[0]
    task_id = str(descriptor["task_id"])
    try:
        envelope = review.read_task_input(task_id).request_envelope
        bound = review.task_input_digest(task_id) == descriptor["task_input_digest"]
    except ValidationError as exc:
        raise _LinkageInvalid(
            getattr(exc, "code", None) or "review_record_invalid",
            f"the task input {task_id} of {label} Review Run {review_run_id} does not read",
        ) from exc
    if not bound:
        raise _LinkageInvalid(
            "review_provenance_conflict",
            f"the stored task input {task_id} is not the one generation 1 of {label} Review Run {review_run_id} accepted",
        )
    try:
        named = reader(envelope, review_run_id=review_run_id)
    except ValidationError as exc:
        raise _LinkageInvalid(
            getattr(exc, "code", None) or "review_record_invalid",
            f"the request of {label} Review Run {review_run_id} is refused by {described}",
        ) from exc
    return [item["review_run_id"] for item in named]


def _request_names(review: ReviewStore, review_run_id: str, chain: GateChain) -> list[str]:
    """The Runs the stored request of Run ``review_run_id`` sets aside, by the reader of its explicit contract.

    A v1 Run by its kind's v1 reader; a P4 Run by :func:`p4.set_aside_named`,
    never by a v1 reader; a Run whose generation 1 binds more than one
    contract, or the P4 contract of another kind, names nothing and is refused.
    """
    first = chain.generations[0]
    label, reader, described = _V1_READERS[first.review_kind]
    contracts = _contracts(review, chain)
    if len(contracts) > 1:
        raise _LinkageInvalid(
            "review_record_conflict",
            f"generation 1 of {label} Review Run {review_run_id} binds more than one Review contract",
        )
    contract = next(iter(contracts), None)
    if contract is None:
        return _v1_request_names(review, review_run_id, chain, label, reader, described)
    if contract != _P4_CONTRACTS[first.review_kind]:
        raise _LinkageInvalid(
            "review_record_conflict",
            f"generation 1 of {label} Review Run {review_run_id} binds the P4 contract of another Review kind",
        )
    try:
        named = p4.set_aside_named(review, review_run_id, chain)
    except ValidationError as exc:
        raise _LinkageInvalid(
            getattr(exc, "code", None) or "review_record_invalid",
            f"the request of P4 {label} Review Run {review_run_id} is refused by {_P4_READER}",
        ) from exc
    return [item["review_run_id"] for item in named]


def _require_matching(
    label: str, namer: str, first: GateGeneration, named: str, entries: dict[str, dict[str, Any]],
    firsts: dict[str, GateGeneration],
) -> None:
    """``named`` is another Run of the namer's Review kind and operation identity in this namespace.

    The shape of the recovery harvest (only matching Runs are set aside) and of
    the adoption proof's check of a successor's other set-aside entries. A
    named Run whose chain does not read is not judged: it stays ``invalid``.
    """
    if named not in entries:
        raise _LinkageInvalid(
            "review_record_conflict",
            f"the request of {label} Review Run {namer} sets aside Review Run {named}, which this Review namespace "
            "does not hold",
        )
    other = firsts.get(named)
    if other is not None and (other.review_kind, other.operation_identity) != (first.review_kind, first.operation_identity):
        raise _LinkageInvalid(
            "review_record_conflict",
            f"the request of {label} Review Run {namer} sets aside Review Run {named}, which is not a Run of the same "
            "Review kind and operation identity",
        )


def _on_cycle(names: dict[str, list[str]]) -> set[str]:
    """The naming Runs a chain of set-aside names leads back to: no Run can set aside a Run that sets it aside."""
    found: set[str] = set()
    for start in names:
        seen: set[str] = set()
        frontier = list(names[start])
        while frontier:
            current = frontier.pop()
            if current == start:
                found.add(start)
                break
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(names.get(current, ()))
    return found


def _invalid(entry: dict[str, Any], reason: dict[str, str]) -> None:
    entry["state"] = RUN_INVALID
    entry["reason"] = reason


def _project_set_aside(
    review: ReviewStore, runs: list[dict[str, Any]], firsts: dict[str, GateGeneration], whole: dict[str, GateChain],
) -> None:
    """Project ``set_aside`` from positive, validated successor evidence only (see the module docstring)."""
    entries = {entry["review_run_id"]: entry for entry in runs}
    names: dict[str, list[str]] = {}
    for review_run_id, chain in whole.items():
        first = chain.generations[0]
        if first.review_kind not in _V1_READERS:
            continue
        try:
            named = _request_names(review, review_run_id, chain)
            for other in named:
                _require_matching(_label(first), review_run_id, first, other, entries, firsts)
        except _LinkageInvalid as exc:
            _invalid(entries[review_run_id], exc.reason)
            continue
        if named:
            names[review_run_id] = named
    for review_run_id in sorted(_on_cycle(names)):
        _invalid(entries[review_run_id], _reason(
            "review_record_conflict",
            f"the request of {_label(firsts[review_run_id])} Review Run {review_run_id} sets aside a Run whose own "
            f"set-aside names lead back to {review_run_id}; no Run sets aside a Run that sets it aside",
        ))
    for namer, named in names.items():
        if entries[namer]["state"] == RUN_INVALID:
            continue
        for other in named:
            entry = entries[other]
            if entry["state"] == RUN_OPEN or (entry["state"] == RUN_SEALED and entry["consumption"]["status"] == "none"):
                entry["state"] = RUN_SET_ASIDE


# --------------------------------------------------------------------------- blocking obligations (§9.7, §29.18)


def _obligations(status: str, count: int | None = None) -> dict[str, Any]:
    return {"status": status, "count": count}


def _first_contracts(review: ReviewStore, first: GateGeneration) -> set[str | None] | None:
    """The Review contracts generation 1's TaskInputs bind explicitly (``None`` = v1); ``None`` if one does not read."""
    found: set[str | None] = set()
    for task in first.accepted_tasks:
        try:
            found.add(p4.contract_of_task_input(review.read_task_input(str(task["task_id"]))))
        except ValidationError:
            return None
    return found


def _run_obligations(
    review: ReviewStore, review_run_id: str, first: GateGeneration | None, chain: GateChain | None,
) -> dict[str, Any]:
    """A Run's blocking obligations, by the Review contract its generation 1 binds explicitly.

    ```text
    a kind no P4 contract covers, or no P4 contract    not_available_by_contract (v1 gives no count)
    the kind's P4 contract, its chain read             p4.blocking_obligations: pending before the
                                                       canonical adjudication, available with its count
                                                       after; a refusal is raised to the caller
    anything else (no generation 1 read, a TaskInput   invalid, never a count; the Run's own reader
    that does not read, several or another contract)   says why (set-aside dispatch, chain, Receipt)
    ```

    P4's meaning is never re-derived here: the count is the P4 reader's.
    """
    if first is None:
        return _obligations(OBLIGATIONS_INVALID)
    contract = _P4_CONTRACTS.get(first.review_kind)
    contracts = _first_contracts(review, first)
    if contract is None or (contracts is not None and contracts <= {None}):
        return _obligations(NOT_AVAILABLE_BY_CONTRACT)
    if chain is None or contracts != {contract}:
        return _obligations(OBLIGATIONS_INVALID)
    count = p4.blocking_obligations(review, review_run_id, chain)
    return _obligations(OBLIGATIONS_PENDING) if count is None else _obligations(OBLIGATIONS_AVAILABLE, count)


def _project_obligations(
    review: ReviewStore, runs: list[dict[str, Any]], firsts: dict[str, GateGeneration],
    obligations: dict[str, dict[str, Any]],
) -> None:
    """Each Run's ``blocking_obligations``, once its state is final: an ``invalid`` Run never shows a count."""
    for entry in runs:
        review_run_id = entry["review_run_id"]
        found = obligations.get(review_run_id)
        if found is None:  # its own records stopped the read first; generation 1 alone still shows its contract
            first = firsts.get(review_run_id)
            if first is None:
                try:
                    first = review.read_gate(review_run_id, 1)
                except ValidationError:
                    first = None
            found = _run_obligations(review, review_run_id, first, None)
        if entry["state"] == RUN_INVALID and found["status"] != NOT_AVAILABLE_BY_CONTRACT:
            found = _obligations(OBLIGATIONS_INVALID)
        entry["blocking_obligations"] = found


def _pending_obligations(
    namespace: dict[str, Any], runs: list[dict[str, Any]], runs_reason: dict[str, str] | None,
) -> dict[str, Any]:
    """The pending Review obligation summary (§9.4): the blocking obligations of every current P4 Run.

    Filled once any Run is not a v1 Run. A deterministic aggregate over every
    Run that is neither v1 nor terminal (``consumed``, ``invalidated``,
    ``set_aside``), in Run ID order only for the listing - never a Run chosen
    by age, ID, file or time: ``invalid`` when one of them does not read,
    ``pending`` when one has no adjudication yet, else ``available`` with the
    sum of their counts (a sealed Run adds 0). A namespace whose Runs cannot be
    listed is ``unavailable``. A projection, never lifecycle truth.
    """
    if namespace["status"] == NAMESPACE_INVALID or runs_reason is not None:
        return {"status": OBLIGATIONS_UNAVAILABLE, "count": None, "review_run_ids": []}
    if all(entry["blocking_obligations"]["status"] == NOT_AVAILABLE_BY_CONTRACT for entry in runs):
        return {"status": NOT_AVAILABLE_BY_CONTRACT}
    current = [
        entry for entry in runs
        if entry["state"] not in _TERMINAL and entry["blocking_obligations"]["status"] != NOT_AVAILABLE_BY_CONTRACT
    ]
    statuses = {entry["blocking_obligations"]["status"] for entry in current}
    review_run_ids = sorted(entry["review_run_id"] for entry in current)
    for status in (OBLIGATIONS_INVALID, OBLIGATIONS_PENDING):
        if status in statuses:
            return {"status": status, "count": None, "review_run_ids": review_run_ids}
    count = sum(int(entry["blocking_obligations"]["count"]) for entry in current)
    return {"status": OBLIGATIONS_AVAILABLE, "count": count, "review_run_ids": review_run_ids}


def review_status(store: ProjectStore) -> dict[str, Any]:
    """The Review section of the status model; every part read on its own, none hiding another."""
    review = ReviewStore(store)
    try:
        present = review.exists()
        namespace = {"status": NAMESPACE_PRESENT if present else NAMESPACE_ABSENT, "reason": None}
    except ValidationError as exc:
        present = False
        namespace = {"status": NAMESPACE_INVALID, "reason": _failure(exc)}
    try:
        activation = activation_status(store, review)
    except Exception as exc:  # a reader defect is reported, never taken for absence
        activation = _activation(ACTIVATION_INVALID, reason=_failure(exc))
    runs: list[dict[str, Any]] = []
    runs_reason = None
    if present:
        runs, runs_reason = _runs(review)
    return {
        "namespace": namespace,
        "activation": activation,
        "runs": {"status": "unavailable" if runs_reason else "available", "reason": runs_reason, "entries": runs},
        "pending_obligations": _pending_obligations(namespace, runs, runs_reason),
    }


__all__ = [
    "ACTIVATION_ABSENT",
    "ACTIVATION_INVALID",
    "ACTIVATION_PRESENT",
    "NAMESPACE_ABSENT",
    "NAMESPACE_INVALID",
    "NAMESPACE_PRESENT",
    "NOT_AVAILABLE_BY_CONTRACT",
    "OBLIGATIONS_AVAILABLE",
    "OBLIGATIONS_INVALID",
    "OBLIGATIONS_PENDING",
    "OBLIGATIONS_UNAVAILABLE",
    "RUN_STATES",
    "activation_status",
    "review_status",
]
