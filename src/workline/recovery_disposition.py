"""Explicit Human-invoked recovery disposition (RB10 N4) - Workline recovery authority, not a Skill.

The canonical escape hatch for a pending mutation or a Review Run that is not
automatically resumable, that a Human has decided must no longer be considered
for automatic resume, and that no automatic replacement Run can set aside
(``WORKLINE_COMPLETION_SPRINT.md`` §18.5-§18.7, §35). It reuses the RB3-C1
meaning of set-aside exactly:

```text
the old state remains evidence
AND
automatic recovery selection must not choose it again
```

It deletes, completes, repairs or reinterprets nothing: the target mutation's
runtime record and every Review record stay byte for byte as they are.

One canonical immutable record per target, at
``.workline/recovery/dispositions/<target_id>.yaml`` (committed Project state,
never ``.workline/runtime``), whose identity is the target's own stable ID::

    schema: workline-recovery-disposition
    version: 1
    target_kind: mutation | review_run
    target_id: <mut_... | rr_...>
    target_state_contract: pending-mutation-v1 | review-run-recovery-v1
    target_state_digest: <lowercase sha256 of the exact target state witnessed>
    decision: set_aside
    decision_source: human
    reason: <the trimmed, one-line, public-safe Human reason>

There is no timestamp: the same target and reason are the same record, so a
repeat is idempotent by structure, never by chronology.

* :func:`dispose_recovery` (CLI ``dispose-recovery``) runs only on an explicit
  Human confirmation (``confirmed=True``, ``--confirm``), refused before any
  Project state, lock or mutation is read without it. It has its own owner,
  ``recovery-disposition``, its own mutation - opened only through
  :func:`open_disposition_mutation`, which exempts exactly the
  target pending mutation and nothing else - and owns exactly one canonical
  path, its record, which it creates once, commits alone and pushes to the
  approved destination when the Project has one;
* a pending mutation is disposable only while RB1's read-only classifier proves
  it ``pending_reconcile_required``; a Review Run only while its records are
  whole, no Receipt of it is current, it is not consumed or already set aside,
  and the generalized recovery classifier finds it non-resumable for the one
  owner-supported reason that no pending START holds it
  (:func:`workline.review.recovery.disposition_outcome`);
* the target's exact state is bound by a domain-separated digest
  (``pending-mutation-v1``: the runtime record bytes; ``review-run-recovery-v1``:
  every Review record of the Run, by path and content digest), witnessed again
  immediately before the record is written and on every later read;
* a valid committed disposition takes the target out of automatic selection:
  :meth:`workline.mutation.MutationController.list_pending` no longer returns a
  disposed mutation (an explicit load refuses it as ``disposed_by_human``), and
  Review recovery discovery sets a disposed Run aside with the stable reason
  ``disposed_by_human``. A record that does not hold fails closed everywhere.

Lifecycle derivation never reads this namespace.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
from typing import Any
import unicodedata

from . import gitcmd, yamlish
from .errors import GitError, ReconcileRequired, StopError, ValidationError
from .ids import is_valid_id, kind_of
from .review import serialize
from .store import (
    RECOVERY_DIR,
    RECOVERY_DISPOSITION_OWNERS,
    RECOVERY_DISPOSITIONS_DIR,
    WORKLINE_DIR,
    ProjectStore,
)

OWNER = RECOVERY_DISPOSITION_OWNERS[0]
SCHEMA = "workline-recovery-disposition"
VERSION = 1
DECISION_SET_ASIDE = "set_aside"
SOURCE_HUMAN = "human"
KIND_MUTATION = "mutation"
KIND_REVIEW_RUN = "review_run"
TARGET_KINDS = (KIND_MUTATION, KIND_REVIEW_RUN)
CONTRACT_MUTATION = "pending-mutation-v1"
CONTRACT_REVIEW_RUN = "review-run-recovery-v1"
CONTRACTS = {KIND_MUTATION: CONTRACT_MUTATION, KIND_REVIEW_RUN: CONTRACT_REVIEW_RUN}
#: The one stable code a Human disposition is propagated and reported by; the free-form reason never is.
REASON_DISPOSED_BY_HUMAN = "disposed_by_human"
#: Every field of a v1 record, and nothing else.
FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "target_kind", "target_id", "target_state_contract",
    "target_state_digest", "decision", "decision_source", "reason",
)
COMMIT_MESSAGE = "chore(workline): set aside recovery {target_id}"
#: The stage that records the one create, and the Git stage that commits (and, with a remote, pushes) it.
STAGE_DISPOSITION = "disposition"
STAGE_COMMIT = "commit"

#: What a target's disposition amounts to right now (:class:`TargetState`).
STATE_NONE = "none"
STATE_EFFECTIVE = "effective"
STATE_UNCOMMITTED = "uncommitted"
STATE_INVALID = "invalid"

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
#: The domain separators of the two target-state contracts.
_MUTATION_DOMAIN = b"workline-recovery-disposition\x00" + CONTRACT_MUTATION.encode("ascii") + b"\x00"
_REVIEW_DOMAIN = b"workline-recovery-disposition\x00" + CONTRACT_REVIEW_RUN.encode("ascii") + b"\x00"


def _invalid(message: str) -> ValidationError:
    return ValidationError(message, code="recovery_disposition_invalid")


# --------------------------------------------------------------------------- target, path, reason


def target_kind(target_id: object) -> str | None:
    """``mutation`` or ``review_run`` for a stable ID of one of those kinds; ``None`` for anything else."""
    if not isinstance(target_id, str):
        return None
    found = kind_of(target_id)
    return found if found in TARGET_KINDS else None


def disposition_rel(target_id: str) -> str:
    """The one canonical path of ``target_id``'s disposition."""
    if target_kind(target_id) is None:
        raise ValidationError(
            f"a recovery disposition targets exactly one mutation (mut_...) or Review Run (rr_...) stable ID, not "
            f"{target_id!r}",
            code="recovery_disposition_target_invalid",
        )
    return f"{RECOVERY_DISPOSITIONS_DIR}/{target_id}.yaml"


def _fold(component: str) -> str:
    """The frozen ASCII-only fold, then what a Windows name drops at its end: how two spellings reach one directory."""
    folded = "".join(chr(ord(character) + 32) if "A" <= character <= "Z" else character for character in component)
    return folded.rstrip(". ")


def in_recovery_namespace(relative: object) -> bool:
    """Whether a Project path lands in the recovery namespace, spelled in any way a filesystem may fold onto it."""
    if not isinstance(relative, str):
        return False
    parts = relative.split("/")
    return len(parts) >= 2 and parts[0] == WORKLINE_DIR and _fold(parts[1]) == _fold(RECOVERY_DIR.split("/")[1])


def require_disposition_path(relative: object) -> str:
    """The target ID of an exact canonical disposition path, or ``recovery_disposition_path``."""
    parts = relative.split("/") if isinstance(relative, str) else []
    name = parts[-1] if parts else ""
    target_id = name[: -len(".yaml")] if name.endswith(".yaml") else ""
    if len(parts) != 4 or "/".join(parts[:3]) != RECOVERY_DISPOSITIONS_DIR or target_kind(target_id) is None:
        raise ValidationError(
            f"not a canonical recovery disposition path: {relative!r}; the namespace holds "
            f"{RECOVERY_DISPOSITIONS_DIR}/<mut_...|rr_...>.yaml and nothing else",
            code="recovery_disposition_path",
        )
    return target_id


#: What a reason may not hold: it is one line of text, stored and read back exactly.
_REFUSED_CATEGORIES = ("Cc", "Cs", "Zl", "Zp")


def normalize_reason(reason: object) -> str:
    """The canonical Human reason: trimmed, non-empty, one line of text; ``recovery_disposition_reason_invalid`` else.

    It is committed canonical Project data, so it holds no control character,
    line or paragraph separator, or lone surrogate. Whether it is public-safe is
    the Human's to say (no secret, no private raw material); nothing here can.
    """
    if not isinstance(reason, str):
        raise StopError("a recovery disposition needs a reason, as text", code="recovery_disposition_reason_invalid")
    text = reason.strip()
    if not text:
        raise StopError(
            "a recovery disposition needs a non-empty, public-safe Human reason; nothing was begun",
            code="recovery_disposition_reason_invalid",
        )
    if any(unicodedata.category(character) in _REFUSED_CATEGORIES for character in text):
        raise StopError(
            "a recovery disposition reason is one line of text: no control character, line or paragraph separator "
            "or lone surrogate; nothing was begun",
            code="recovery_disposition_reason_invalid",
        )
    return text


# --------------------------------------------------------------------------- the record


@dataclass(frozen=True)
class Disposition:
    """One Human recovery disposition, v1 (§35.3)."""

    target_kind: str
    target_id: str
    target_state_digest: str
    reason: str
    target_state_contract: str = ""
    decision: str = DECISION_SET_ASIDE
    decision_source: str = SOURCE_HUMAN

    def __post_init__(self) -> None:
        if not self.target_state_contract:
            object.__setattr__(self, "target_state_contract", CONTRACTS.get(self.target_kind, ""))

    @property
    def path(self) -> str:
        return disposition_rel(self.target_id)

    def to_record(self) -> dict[str, Any]:
        return {
            serialize.SCHEMA_KEY: SCHEMA,
            serialize.VERSION_KEY: VERSION,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "target_state_contract": self.target_state_contract,
            "target_state_digest": self.target_state_digest,
            "decision": self.decision,
            "decision_source": self.decision_source,
            "reason": self.reason,
        }

    @staticmethod
    def from_record(data: object, described: str) -> "Disposition":
        """Strict v1: unknown or missing fields, any other value or kind of value fail closed."""
        if not isinstance(data, dict) or set(data) != set(FIELDS):
            found = sorted(str(key) for key in data) if isinstance(data, dict) else type(data).__name__
            raise _invalid(f"{described} carries exactly {sorted(FIELDS)}, not {found}")
        if data[serialize.SCHEMA_KEY] != SCHEMA or type(data[serialize.VERSION_KEY]) is not int \
                or data[serialize.VERSION_KEY] != VERSION:
            raise _invalid(f"{described} is not a {SCHEMA} record of version {VERSION}")
        kind, target_id = data["target_kind"], data["target_id"]
        if kind not in TARGET_KINDS:
            raise _invalid(f"{described} has no known target_kind")
        if target_kind(target_id) != kind:
            raise _invalid(f"{described}: target_id is not a {kind} stable ID")
        if data["target_state_contract"] != CONTRACTS[kind]:
            raise _invalid(f"{described}: target_state_contract is not {CONTRACTS[kind]}")
        digest = data["target_state_digest"]
        if not isinstance(digest, str) or _DIGEST.match(digest) is None:
            raise _invalid(f"{described}: target_state_digest is not a lowercase SHA-256")
        if data["decision"] != DECISION_SET_ASIDE or data["decision_source"] != SOURCE_HUMAN:
            raise _invalid(f"{described}: decision is exactly {DECISION_SET_ASIDE}, by {SOURCE_HUMAN}")
        reason = data["reason"]
        try:
            canonical = normalize_reason(reason)
        except StopError as exc:
            raise _invalid(f"{described}: its reason is not a canonical Human reason ({exc.message})") from exc
        if canonical != reason:
            raise _invalid(f"{described}: its reason is not stored trimmed")
        return Disposition(kind, target_id, digest, reason)


def render(disposition: Disposition) -> str:
    """The one canonical text of a record: what the file holds."""
    return serialize.canonical_text(disposition.to_record())


def parse(raw: bytes, target_id: str) -> Disposition:
    """The record ``raw`` holds at ``target_id``'s path - only if it is that record's canonical text.

    Line ends are read as a checkout may have written them (CRLF for the LF the
    record is committed with); anything else that is not exactly the canonical
    rendering is refused.
    """
    described = f"the recovery disposition {disposition_rel(target_id)}"
    try:
        text = raw.decode("utf-8", errors="strict").replace("\r\n", "\n")
        data = yamlish.load(text)
    except (UnicodeDecodeError, yamlish.YamlishError) as exc:
        raise _invalid(f"{described} does not read: {exc}") from exc
    found = Disposition.from_record(data, described)
    if found.target_id != target_id:
        raise _invalid(f"{described} names another target, {found.target_id}, than its own path")
    if render(found) != text:
        raise _invalid(f"{described} is not stored in its canonical form")
    return found


def _dispositions_chain(store: ProjectStore):
    from .review import fsafe

    return fsafe.walk(store.root, RECOVERY_DISPOSITIONS_DIR.split("/"))


def read_disposition(store: ProjectStore, target_id: str) -> Disposition | None:
    """The disposition of ``target_id`` read through a held no-follow chain; ``None`` when there is none.

    An indirection anywhere on the way, a file that does not read, or one that
    is not exactly a valid record is ``recovery_disposition_invalid``.
    """
    name = disposition_rel(target_id).rsplit("/", 1)[1]
    try:
        chain = _dispositions_chain(store)
        if chain is None:
            return None
        with chain:
            raw = chain.last.read_file(name)
    except ValidationError as exc:
        raise _invalid(f"the recovery disposition of {target_id} cannot be read safely: {exc}") from exc
    except OSError as exc:
        raise _invalid(f"the recovery disposition of {target_id} cannot be read: {exc}") from exc
    return None if raw is None else parse(raw, target_id)


def namespace_present(store: ProjectStore) -> bool:
    """Whether anything is at the recovery namespace path (a cheap check before any record is read)."""
    return os.path.lexists(store.root / RECOVERY_DIR)


def committed(store: ProjectStore, relative: str) -> bool | None:
    """Whether HEAD holds ``relative`` and neither the index nor the working tree differs from it; ``None``: unknown."""
    held = gitcmd.head_paths(store.root, relative)
    if held is None:
        return None
    if relative not in held:
        return False
    try:
        return not gitcmd.changed_against_head(store.root, [relative])
    except GitError:
        return None


# --------------------------------------------------------------------------- the target-state witnesses


def mutation_state_digest(raw: bytes) -> str:
    """``pending-mutation-v1``: SHA-256 over the domain separator and the exact runtime record bytes."""
    return hashlib.sha256(_MUTATION_DOMAIN + raw).hexdigest()


def runtime_record_bytes(store: ProjectStore, mutation_id: str) -> bytes | None:
    """The exact bytes of ``mutation_id``'s runtime record; ``None`` when it is not there (runtime loss, a clone)."""
    path = store.mutations / f"{mutation_id}.yaml"
    if not os.path.lexists(path):
        return None
    return path.read_bytes()


def review_run_closure(review: Any, review_run_id: str) -> list[str]:
    """Every canonical Review record of one Run (``review-run-recovery-v1``), sorted by path.

    Every gate generation file of the Run's directory; the CandidateSnapshot of
    every Candidate a generation binds; every accepted TaskInput; the P4 report
    of a settled task, the adjudication, and the Repair Batch / Result a
    TaskInput names, when present; every Receipt a generation issues and its
    Supersession, when present; and every Consumption of one of those Receipts.
    Anything the Run's own records name that does not read is a refusal.
    """
    from .review import paths

    chain = review.gate_chain(review_run_id)
    if chain is None:
        raise ValidationError(f"Review Run {review_run_id} holds no gate generation", code="recovery_disposition_witness")
    run_dir = paths.run_dir(review_run_id)
    members: set[str] = set()
    for entry in review.entries(run_dir) or []:
        if not entry.is_file or entry.is_indirection:
            raise ValidationError(
                f"{run_dir}/{entry.name} is not a plain gate generation file", code="recovery_disposition_witness"
            )
        members.add(f"{run_dir}/{entry.name}")
    receipts: set[str] = set()
    task_ids: set[str] = set()
    for generation in chain.generations:
        members.add(paths.candidate_snapshot_rel(generation.candidate_hash))
        task_ids.update(str(task["task_id"]) for task in generation.accepted_tasks)
        for task in generation.settled_tasks:
            digest = task.get("result_digest")
            if isinstance(digest, str) and _DIGEST.match(digest) and review.report_exists(digest):
                members.add(paths.report_rel(digest))
        if generation.receipt_id:
            receipts.add(str(generation.receipt_id))
    for task_id in task_ids:
        members.add(paths.task_input_rel(task_id))
        envelope = review.read_task_input(task_id).request_envelope
        batch = envelope.get("repair_batch_id") if isinstance(envelope, dict) else None
        if isinstance(batch, str) and is_valid_id(batch, "review_repair_batch"):
            if review.repair_batch_exists(batch):
                members.add(paths.repair_batch_rel(batch))
            if review.repair_result_exists(batch):
                members.add(paths.repair_result_rel(batch))
                members.add(paths.candidate_snapshot_rel(review.read_repair_result(batch).result_candidate_hash))
    for receipt_id in receipts:
        members.add(paths.receipt_rel(receipt_id))
        if review.supersession_exists(receipt_id):
            members.add(paths.supersession_rel(receipt_id))
    for consumption_id in review.consumption_ids():
        if review.read_consumption(consumption_id).receipt_id in receipts:
            members.add(paths.consumption_rel(consumption_id))
    if review.adjudication_exists(review_run_id):
        members.add(paths.adjudication_rel(review_run_id))
    return sorted(members)


def review_run_state_digest(review: Any, review_run_id: str) -> str:
    """``review-run-recovery-v1``: SHA-256 over the domain separator and each closure member's path and content digest."""
    found = hashlib.sha256(_REVIEW_DOMAIN)
    for relative in review_run_closure(review, review_run_id):
        data = review.read_bytes(relative)
        if data is None:
            raise ValidationError(
                f"{relative}, named by the records of Review Run {review_run_id}, is not there",
                code="recovery_disposition_witness",
            )
        found.update(relative.encode("utf-8") + b"\x00" + hashlib.sha256(data).hexdigest().encode("ascii") + b"\n")
    return found.hexdigest()


def current_receipt(review: Any, chain: Any) -> str | None:
    """The Run's sealed Receipt no Supersession invalidates yet, or ``None``."""
    latest = chain.latest
    if latest.sealed and latest.receipt_id and not review.supersession_exists(str(latest.receipt_id)):
        return str(latest.receipt_id)
    return None


# --------------------------------------------------------------------------- what a disposition amounts to now


@dataclass(frozen=True)
class TargetState:
    """A target's disposition as the readers take it: none, effective, written but not committed, or invalid."""

    state: str
    disposition: Disposition | None = None
    problem: str | None = None
    #: mutation targets only: whether the runtime record is still there (``present`` / ``absent``)
    runtime_record: str | None = None


def mutation_target_state(store: ProjectStore, mutation_id: str) -> TargetState:
    """What ``mutation_id``'s disposition amounts to (§35.8, §35.19).

    ```text
    no record                                          none
    record that does not read                          invalid
    runtime record present, its exact bytes bound      effective when committed, uncommitted otherwise
    runtime record present, other bytes                invalid: never resumed, never hidden
    runtime record absent (runtime loss, a clone)      historical evidence: effective when committed
    committedness Git cannot answer                    invalid
    ```
    """
    try:
        found = read_disposition(store, mutation_id)
    except ValidationError as exc:
        return TargetState(STATE_INVALID, problem=str(exc))
    if found is None:
        return TargetState(STATE_NONE)
    if found.target_kind != KIND_MUTATION:
        return TargetState(STATE_INVALID, found, f"{found.path} does not target a mutation")
    try:
        raw = runtime_record_bytes(store, mutation_id)
    except OSError as exc:
        return TargetState(STATE_INVALID, found, f"the runtime record of {mutation_id} cannot be read: {exc}", "present")
    runtime = "absent" if raw is None else "present"
    if raw is not None and mutation_state_digest(raw) != found.target_state_digest:
        return TargetState(
            STATE_INVALID, found,
            f"the runtime record of {mutation_id} no longer holds the exact state {found.path} binds", runtime,
        )
    return _committed_state(store, found, runtime)


def review_run_target_state(store: ProjectStore, review_run_id: str, review: Any = None) -> TargetState:
    """What ``review_run_id``'s disposition amounts to: its record, its Run's witness and its Receipt (§35.9, §35.11)."""
    from .review.store import ReviewStore

    try:
        found = read_disposition(store, review_run_id)
    except ValidationError as exc:
        return TargetState(STATE_INVALID, problem=str(exc))
    if found is None:
        return TargetState(STATE_NONE)
    review = review or ReviewStore(store)
    problem = review_run_problem(review, found)
    if problem is not None:
        return TargetState(STATE_INVALID, found, problem)
    return _committed_state(store, found, None)


def review_run_problem(review: Any, found: Disposition) -> str | None:
    """Why a Review Run disposition does not hold against the Run as its records are now; ``None`` when it does.

    Positive admission first: only a Work Review Run is a disposition target -
    the one kind :func:`_review_run_eligibility` lets the operation dispose
    (``recovery.disposition_outcome`` leaves every other kind ``unresolved``).
    Proven from the Run's own canonical generation-1 ``review_kind``, never from
    the record, its file name or a caller; a structurally canonical record for a
    Planning (or any other) Run, which the operation never creates, holds
    nothing (``invalid``) for every reader.
    """
    from .review import work_review

    if found.target_kind != KIND_REVIEW_RUN:
        return f"{found.path} does not target a Review Run"
    try:
        chain = review.gate_chain(found.target_id)
        if chain is None:
            return f"{found.path} targets Review Run {found.target_id}, which this Project does not hold"
        kind = chain.generations[0].review_kind
        if kind != work_review.REVIEW_KIND:
            return (
                f"{found.path} targets Review Run {found.target_id}, a {kind} Run; a Human recovery disposition is "
                f"admissible only for a {work_review.REVIEW_KIND} Run, so it holds nothing"
            )
        receipt = current_receipt(review, chain)
        if receipt is not None:
            return (
                f"Review Run {found.target_id} holds the current, unsuperseded Receipt {receipt}, which a Human "
                "disposition never sets aside (its invalidation is Supersession's)"
            )
        digest = review_run_state_digest(review, found.target_id)
    except (ValidationError, KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        return f"the records of Review Run {found.target_id} cannot be witnessed: {exc}"
    if digest != found.target_state_digest:
        return f"the records of Review Run {found.target_id} are no longer the exact state {found.path} binds"
    return None


def _committed_state(store: ProjectStore, found: Disposition, runtime: str | None) -> TargetState:
    held = committed(store, found.path)
    if held is None:
        return TargetState(STATE_INVALID, found, f"Git cannot say whether {found.path} is committed", runtime)
    return TargetState(STATE_EFFECTIVE if held else STATE_UNCOMMITTED, found, None, runtime)


def disposition_ids(store: ProjectStore) -> list[str]:
    """Every name in the dispositions directory that is a canonical record name, sorted; ``[]`` when there is none.

    Anything else there is the validator's to report (:func:`namespace_problems`).
    """
    try:
        chain = _dispositions_chain(store)
    except (ValidationError, OSError):
        return []
    if chain is None:
        return []
    with chain:
        entries = chain.last.entries()
    found = []
    for entry in entries:
        if entry.name.endswith(".yaml") and target_kind(entry.name[: -len(".yaml")]) is not None:
            found.append(entry.name[: -len(".yaml")])
    return sorted(found)


# --------------------------------------------------------------------------- the Mutation Controller's admission (§35.7, §35.8)
#
# What the controller calls: its active pending set, an explicit load, the
# global barrier in its pending admission, and the one narrow opening path of
# the disposition owner. Owned here, beside the record they read.


def active_pending(store: ProjectStore, pending: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``pending`` without the records a valid committed Human recovery disposition sets aside (§35.8).

    A record leaves the active set only when the disposition at its own stable
    ID reads as a valid ``pending-mutation-v1`` record, HEAD commits it, and the
    runtime record still holds the exact bytes it binds. A disposition written
    and not committed yet leaves the record active. One that does not hold - a
    record that does not read, a runtime record whose bytes changed, a
    committedness Git cannot answer - neither resumes nor hides anything: every
    owner stops at ``reconcile required``.
    """
    if not pending or not namespace_present(store):
        return pending
    active: list[dict[str, Any]] = []
    for record in pending:
        found = mutation_target_state(store, str(record["mutation_id"]))
        if found.state == STATE_INVALID:
            raise ReconcileRequired(
                f"the recovery disposition of pending mutation {record['mutation_id']} does not hold ({found.problem}); "
                "the mutation is neither resumed nor hidden: reconcile required",
                reason="recovery_disposition_invalid",
            )
        if found.state != STATE_EFFECTIVE:
            active.append(record)
    return active


def refuse_disposed(store: ProjectStore, record: dict[str, Any]) -> None:
    """An explicit load of a pending mutation a valid disposition sets aside refuses as ``disposed_by_human``."""
    if not namespace_present(store):
        return
    found = mutation_target_state(store, str(record["mutation_id"]))
    if found.state == STATE_INVALID:
        raise ReconcileRequired(
            f"the recovery disposition of mutation {record['mutation_id']} does not hold ({found.problem}): reconcile required",
            reason="recovery_disposition_invalid",
        )
    if found.state == STATE_EFFECTIVE:
        raise ReconcileRequired(
            f"mutation {record['mutation_id']} is set aside by an explicit Human recovery disposition; it stays as "
            "diagnostic evidence and is never resumed: reconcile required",
            reason=REASON_DISPOSED_BY_HUMAN,
        )


def require_no_pending_disposition(pending: list[dict[str, Any]]) -> None:
    """The global recovery barrier (§35.7): a pending recovery disposition holds back every other owner."""
    held = sorted(str(record["mutation_id"]) for record in pending if record["owner"] in RECOVERY_DISPOSITION_OWNERS)
    if held:
        raise ReconcileRequired(
            f"a recovery disposition is pending ({', '.join(held)}); it changes what recovery selects, so no other "
            "Workline operation begins or resumes until that same disposition is run again and completes: reconcile "
            "required",
            reason="recovery_disposition_pending",
        )


def open_disposition_mutation(
    store: ProjectStore, invocation: dict[str, Any], scope: Any, *, target_mutation_id: str | None = None
) -> Any:
    """The one narrow opening path of a recovery disposition (§35.7); the ordinary ``MutationController.open`` refuses it.

    * under the Project execution lock, for the ``recovery-disposition`` owner only;
    * its scope is exactly the one disposition path it creates: no entity, no
      other file;
    * it resumes only the pending disposition of exactly this request (target
      and reason); a second matching one refuses;
    * besides that record, exactly the target pending mutation may be pending
      (``target_mutation_id``) and nothing else - not a second pending mutation,
      not another disposition. The target is never loaded or written: it is only
      not refused.
    """
    import json

    from . import oplock
    from .mutation import Mutation, MutationController, WriteScope

    controller = MutationController(store)
    controller.require_execution_lock(OWNER)
    if scope.entities or len(set(scope.files)) != 1:
        raise ValidationError("a recovery disposition owns exactly its one disposition path", code="recovery_disposition_owner")
    require_disposition_path(scope.files[0])
    pending = controller.list_pending()
    invocation = json.loads(json.dumps(invocation, sort_keys=True))
    matches = [p for p in pending if p["owner"] == OWNER and p["invocation"] == invocation]
    if len(matches) > 1:
        raise ReconcileRequired(f"{len(matches)} pending recovery dispositions match {invocation}: reconcile required")
    for other in pending:
        if other in matches:
            continue
        if target_mutation_id is not None and other["mutation_id"] == target_mutation_id \
                and other["owner"] not in RECOVERY_DISPOSITION_OWNERS:
            continue  # exactly the target pending mutation, and only it, is not refused
        raise ReconcileRequired(
            f"pending mutation {other['mutation_id']} (owner {other['owner']}) is not the one this recovery disposition "
            "disposes; a disposition begins or resumes beside nothing else: reconcile required",
            reason="recovery_disposition_pending_operation",
        )
    if matches:
        if WriteScope.from_record(matches[0]["write_scope"]).to_record() != scope.to_record():
            raise ReconcileRequired(
                f"the pending recovery disposition {matches[0]['mutation_id']} owns another path than this request: "
                "reconcile required"
            )
        mutation = Mutation(controller, matches[0], resumed=True)
    else:
        mutation = controller.begin(OWNER, invocation, scope)
    oplock.note_mutation(store, mutation.id)
    return mutation


# --------------------------------------------------------------------------- validation (§35.18)


def namespace_problems(store: ProjectStore) -> list[tuple[str, str]]:
    """``(code, message)`` for every way the recovery namespace and its records do not hold; empty when they do.

    Read-only, and without ``state.py``: path shape, the strict v1 schema, the
    target ID / kind / contract agreement, one record per target, a Review
    target that exists and still matches its witness and holds no current
    Receipt, a mutation target that - when its runtime record is there - is the
    exact pending record the digest binds (absent after runtime loss or in a
    clone is historical evidence and valid).
    """
    from .review import fsafe

    if not namespace_present(store):
        return []
    problems: list[tuple[str, str]] = []
    shape = "recovery_disposition_invalid"
    try:
        chain = fsafe.walk(store.root, RECOVERY_DIR.split("/"))
    except (ValidationError, OSError) as exc:
        return [(shape, f"{RECOVERY_DIR} cannot be read safely: {exc}")]
    if chain is None:
        return [(shape, f"{RECOVERY_DIR} is not a plain directory")]
    with chain:
        top = chain.last.entries()
    for entry in top:
        if entry.name != RECOVERY_DISPOSITIONS_DIR.rsplit("/", 1)[1] or not entry.is_dir or entry.is_indirection:
            problems.append((shape, f"{RECOVERY_DIR}/{entry.name} is not part of the recovery namespace"))
    try:
        chain = _dispositions_chain(store)
    except (ValidationError, OSError) as exc:
        return problems + [(shape, f"{RECOVERY_DISPOSITIONS_DIR} cannot be read safely: {exc}")]
    if chain is None:
        return problems
    with chain:
        entries = chain.last.entries()
    targets: list[str] = []
    for entry in entries:
        relative = f"{RECOVERY_DISPOSITIONS_DIR}/{entry.name}"
        if not entry.is_file or entry.is_indirection:
            problems.append((shape, f"{relative} is not a plain record file"))
            continue
        try:
            targets.append(require_disposition_path(relative))
        except ValidationError as exc:
            problems.append((shape, exc.message))
    from .review.store import ReviewStore

    review = ReviewStore(store)
    for target_id in sorted(targets):
        try:
            found = read_disposition(store, target_id)
        except ValidationError as exc:
            problems.append((shape, exc.message))
            continue
        if found is None:
            continue
        problem = _mutation_problem(store, found) if found.target_kind == KIND_MUTATION else review_run_problem(review, found)
        if problem is not None:
            problems.append(("recovery_disposition_conflict", problem))
    return problems


def _mutation_problem(store: ProjectStore, found: Disposition) -> str | None:
    from .mutation import _ownership_confirmed

    try:
        raw = runtime_record_bytes(store, found.target_id)
    except OSError as exc:
        return f"the runtime record of {found.target_id} cannot be read: {exc}"
    if raw is None:
        return None  # historical evidence after runtime loss or in a clone
    try:
        data = yamlish.load(raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n"))
    except (UnicodeError, yamlish.YamlishError):
        data = None
    if not _ownership_confirmed(data, found.target_id) or data.get("status") != "pending":
        return f"the runtime record of {found.target_id} is not the pending Workline mutation {found.path} disposes"
    if mutation_state_digest(raw) != found.target_state_digest:
        return f"the runtime record of {found.target_id} no longer holds the exact state {found.path} binds"
    return None


# --------------------------------------------------------------------------- the operation (§35.13)


@dataclass(frozen=True)
class DispositionResult:
    status: str  # "disposed" | "already_disposed"
    project_root: Path
    target_kind: str
    target_id: str
    target_state_digest: str
    path: str
    mutation_id: str | None = None
    head: str | None = None
    pushed: bool = False
    resumed: bool = False


def dispose_recovery(project_root: Path, target_id: str, reason: str, *, confirmed: bool = False) -> DispositionResult:
    """Set one pending mutation or Review Run aside by explicit Human disposition (§35.4).

    ``confirmed`` must be exactly ``True``: it is the Human's confirmation, and
    no caller identity, prompt text, broken record or supplied reason stands in
    for it. Without it nothing is read, locked or written. The reason is
    committed canonical Project data: one line of public-safe text, never a
    secret or private raw material.
    """
    if confirmed is not True:
        raise StopError(
            "a recovery disposition is explicit Human-confirmed maintenance and needs that confirmation "
            "(confirmed=True; --confirm on the CLI); nothing was read or begun",
            code="recovery_disposition_unconfirmed",
        )
    normalized = normalize_reason(reason)
    kind = target_kind(target_id)
    if kind is None:
        disposition_rel(target_id)  # raises recovery_disposition_target_invalid
    from .oplock import project_operation

    root = Path(project_root)
    if not root.is_dir():
        raise StopError(f"Project root is not a directory: {root}", code="project_root_missing")
    root = root.resolve()
    store = ProjectStore(root)
    if gitcmd.toplevel(root) != root:
        raise StopError(
            f"Project root is not the Git top-level; a recovery disposition needs an established Project repository: {root}",
            code="not_a_project",
        )
    with project_operation(store, OWNER, {"target_id": target_id}):
        return _dispose_locked(store, root, str(kind), target_id, normalized)


def _dispose_locked(store: ProjectStore, root: Path, kind: str, target_id: str, reason: str) -> DispositionResult:
    from . import gitops
    from .bootstrap import is_established_project
    from .destination import ensure_push_destination
    from .mutation import Effect, MutationController, WriteScope, abandon_on_stop, same_request
    from .registry import validate_registry

    if not is_established_project(store):
        raise StopError(
            "not a valid established Workline Project (project.yaml missing, invalid or untracked)", code="not_a_project"
        )
    validation = validate_registry(store.workline_root())
    if not validation.ok:
        detail = "; ".join(f"{p.code}: {p.message}" for p in validation.problems)
        raise StopError(f"registry validation failed: {detail}", code="registry_invalid")

    rel = disposition_rel(target_id)
    invocation = {"operation": OWNER, "project_root": str(root), "target_id": target_id, "reason": reason}
    pending = MutationController(store).list_pending()  # strict; the active set
    own = [p for p in pending if p["owner"] == OWNER and same_request(p["invocation"], invocation)]
    foreign = [p for p in pending if p["owner"] == OWNER and p not in own]
    if foreign:
        detail = ", ".join(sorted(str(p["mutation_id"]) for p in foreign))
        raise ReconcileRequired(
            f"an unfinished recovery disposition for another request is pending ({detail}); a disposition is never "
            "continued with another target or reason, and it is left untouched: reconcile required",
            reason="recovery_disposition_conflict",
        )
    if len(own) > 1:
        raise ReconcileRequired(f"{len(own)} pending recovery dispositions match this request: reconcile required")
    if not own:
        existing = _read_or_refuse(store, target_id)
        if existing is not None:
            return _already_disposed(store, root, existing, reason)
    _require_alone(pending, own, kind, target_id)

    decision = None if own else _decide(store, root, kind, target_id, reason, None)
    destination = ensure_push_destination(store)
    if destination is not None and decision is not None:
        _require_barrier_clear(root)
    mutation = open_disposition_mutation(
        store, invocation, WriteScope(files=(rel,)), target_mutation_id=target_id if kind == KIND_MUTATION else None,
    )
    with abandon_on_stop(mutation):
        gitops.ensure_git_ready(root)
        preexisting = gitops.record_preexisting_dirty(mutation, root)
        gitops.ensure_separable(preexisting, [rel])
        if not mutation.has_stage(STAGE_DISPOSITION):
            # A resumed attempt that decided nothing decides now, under every precondition of a first one.
            if decision is None:
                if _read_or_refuse(store, target_id) is not None:
                    raise ReconcileRequired(
                        f"{rel} exists, and the pending recovery disposition {mutation.id} never decided it; a record "
                        "it did not decide is never adopted: reconcile required",
                        reason="recovery_disposition_conflict",
                    )
                decision = _decide(store, root, kind, target_id, reason, mutation.id)
                if destination is not None:
                    _require_barrier_clear(root)
            # The exact target state is witnessed again immediately before the decision is recorded (§35.5, §35.9).
            if _witness(store, kind, target_id) != decision.target_state_digest:
                raise ReconcileRequired(
                    f"{target_id} changed after it was witnessed for this disposition; nothing is recorded: "
                    "reconcile required",
                    reason="recovery_disposition_target_changed",
                )
            mutation.add_effects(STAGE_DISPOSITION, [Effect.create_file(rel, render(decision))])
    decided = _recorded_decision(mutation, target_id, reason)
    mutation.apply()
    gitops.finalize(mutation, STAGE_COMMIT, COMMIT_MESSAGE.format(target_id=target_id), [rel], destination=destination)
    head = _postcheck(store, mutation, decided, preexisting)
    mutation.complete()
    return DispositionResult(
        "disposed", root, decided.target_kind, decided.target_id, decided.target_state_digest, rel, mutation.id, head,
        pushed=destination is not None, resumed=mutation.resumed,
    )


def _read_or_refuse(store: ProjectStore, target_id: str) -> Disposition | None:
    try:
        return read_disposition(store, target_id)
    except ValidationError as exc:
        raise ReconcileRequired(
            f"{exc.message}; a broken disposition is never replaced or repaired: reconcile required",
            reason="recovery_disposition_invalid",
        ) from exc


def _require_alone(pending: list[dict[str, Any]], own: list[dict[str, Any]], kind: str, target_id: str) -> None:
    """§35.6: beside this request's own record, at most the target pending mutation itself; nothing else."""
    others = [
        p for p in pending
        if p not in own and not (kind == KIND_MUTATION and p["mutation_id"] == target_id and p["owner"] != OWNER)
    ]
    if others:
        detail = ", ".join(f"{p['mutation_id']} (owner {p['owner']})" for p in sorted(others, key=lambda p: str(p["mutation_id"])))
        raise StopError(
            f"another Workline operation is pending ({detail}); a recovery disposition changes what recovery selects "
            "and never surprises an operation in flight, so nothing is disposed until it is finished",
            code="recovery_disposition_pending_operation",
        )


def _require_barrier_clear(root: Path) -> None:
    from .review import publication

    publication.require_barrier_clear(root, gitcmd.head_commit(root))


def _witness(store: ProjectStore, kind: str, target_id: str) -> str | None:
    """The target's state digest as it is now; ``None`` when it cannot be witnessed."""
    if kind == KIND_MUTATION:
        try:
            raw = runtime_record_bytes(store, target_id)
        except OSError:
            return None
        return None if raw is None else mutation_state_digest(raw)
    from .review.store import ReviewStore

    try:
        return review_run_state_digest(ReviewStore(store), target_id)
    except (ValidationError, KeyError, TypeError, ValueError, AttributeError):
        return None


def _ineligible(message: str) -> StopError:
    return StopError(f"{message}; nothing is disposed", code="recovery_disposition_target_ineligible")


def _unnecessary(message: str) -> StopError:
    return StopError(
        f"{message}; a Human disposition would only write the same meaning twice, so nothing is disposed",
        code="recovery_disposition_unnecessary",
    )


def _decide(
    store: ProjectStore, root: Path, kind: str, target_id: str, reason: str, own_mutation_id: str | None
) -> Disposition:
    """The record this disposition creates, decided under every precondition of §35.5 / §35.10 / §35.12 / §35.20.

    Everything here is read before any effect exists, so a refusal records nothing.
    """
    from . import gitops
    from .review import fsafe

    rel = disposition_rel(target_id)
    if not fsafe.immutable_create_supported():
        raise StopError(
            "a recovery disposition is an immutable create this platform cannot keep inside the Project; it never "
            "falls back to overwrite or replace, so nothing is disposed",
            code="recovery_disposition_create_unsupported",
        )
    if rel in gitops.capture_preexisting_dirty(root):
        raise StopError(gitops.OVERLAP_MESSAGE + rel, code="dirty_overlap")
    gitops.ensure_git_ready(root)
    ignored = gitcmd.is_ignored(root, rel)
    if ignored is None:
        raise StopError(
            f"git cannot say whether {rel} is ignored, so whether the disposition would reach the Project's committed "
            "state cannot be shown: STOP",
            code="recovery_disposition_committability_unknown",
        )
    if ignored:
        raise StopError(
            f"{rel} is excluded by this Project's ignore rules, so the disposition would never be committed; Workline "
            "does not change ignore configuration: STOP",
            code="recovery_disposition_path_ignored",
        )
    if kind == KIND_MUTATION:
        digest = _mutation_eligibility(store, target_id, own_mutation_id)
    else:
        digest = _review_run_eligibility(store, target_id)
    return Disposition(kind, target_id, digest, reason)


def _mutation_eligibility(store: ProjectStore, target_id: str, own_mutation_id: str | None) -> str:
    """§35.5: the target is the exact pending record RB1's read-only classifier proves ``pending_reconcile_required``."""
    from . import status
    from .mutation import RECORD_VALID, inspect_records

    try:
        raw = runtime_record_bytes(store, target_id)
    except OSError as exc:
        raise _ineligible(f"the runtime record of mutation {target_id} cannot be read ({exc})") from exc
    if raw is None:
        raise _ineligible(f"mutation {target_id} has no runtime record here (missing)")
    found = [item for item in inspect_records(store) if item.mutation_id == target_id]
    if len(found) != 1 or found[0].parse_state != RECORD_VALID or found[0].record is None:
        raise _ineligible(f"mutation {target_id}'s record cannot be attributed to Workline and its owner")
    record = found[0].record
    if record.get("status") != "pending":
        raise _ineligible(f"mutation {target_id} is {record.get('status')}, not pending")
    if record.get("owner") == OWNER:
        raise _ineligible(f"mutation {target_id} is a recovery disposition itself; it is resumed, never disposed")
    excluding = () if own_mutation_id is None else (own_mutation_id,)
    classification, why = status.pending_classification(store, target_id, excluding=excluding)
    if classification != status.PENDING_RECONCILE:
        raise _ineligible(
            f"mutation {target_id} is {classification} ({why.get('code')}), and only a pending mutation the read-only "
            f"classifier proves {status.PENDING_RECONCILE} is disposed"
        )
    return mutation_state_digest(raw)


def _review_run_eligibility(store: ProjectStore, review_run_id: str) -> str:
    """§35.10 / §35.11: a whole, unconsumed, unauthorized Run the generalized classifier finds owner-less."""
    from . import start_review
    from .review import recovery
    from .review.store import ReviewStore

    review = ReviewStore(store)
    try:
        chain = review.gate_chain(review_run_id)
    except ValidationError as exc:
        raise _ineligible(f"Review Run {review_run_id}'s records do not read ({exc.message})") from exc
    if chain is None:
        raise _ineligible(f"Review Run {review_run_id} does not exist in this Project (missing)")
    receipts = {str(generation.receipt_id) for generation in chain.generations if generation.receipt_id}
    try:
        consumed = sorted(
            consumption_id for consumption_id in review.consumption_ids()
            if review.read_consumption(consumption_id).receipt_id in receipts
        )
    except ValidationError as exc:
        raise _ineligible(f"the Consumptions of this Project do not read ({exc.message})") from exc
    if consumed:
        raise _unnecessary(f"Review Run {review_run_id} is consumed ({', '.join(consumed)})")
    receipt = current_receipt(review, chain)
    if receipt is not None:
        raise StopError(
            f"Review Run {review_run_id} holds the current, unsuperseded sealed Receipt {receipt}; a Human disposition "
            "never invalidates an authorization - the existing Review invalidation (Supersession) resolves it; nothing "
            "is disposed",
            code="recovery_disposition_receipt_current",
        )
    if any(review.supersession_exists(receipt_id) for receipt_id in receipts):
        raise _unnecessary(f"Review Run {review_run_id}'s Receipt is already superseded")
    outcome, detail = recovery.disposition_outcome(store, review_run_id, currency=start_review._recovery_currency(store))
    if outcome == recovery.OUTCOME_SET_ASIDE:
        raise _unnecessary(f"Review Run {review_run_id} is already set aside by its own recovery ({detail})")
    if outcome == recovery.OUTCOME_RECOVERABLE:
        raise _ineligible(f"Review Run {review_run_id} is safely recoverable ({detail}); it is resumed, never disposed")
    if outcome != recovery.OUTCOME_UNOWNED:
        raise _ineligible(
            f"Review Run {review_run_id}'s non-resumability is not one its owner's recovery supports ({detail}); a "
            "Run whose records or ownership cannot be shown exactly is never made disposable"
        )
    try:
        return review_run_state_digest(review, review_run_id)
    except (ValidationError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise _ineligible(f"the exact recovery witness of Review Run {review_run_id} cannot be built ({exc})") from exc


def _recorded_decision(mutation: Any, target_id: str, reason: str) -> Disposition:
    """The record this mutation decided, read back from its own durable stage - the only authority on resume."""
    rel = disposition_rel(target_id)
    found = mutation.stage_effects(STAGE_DISPOSITION)
    if [e.get("kind") for e in found] != ["create_file"] or found[0]["payload"].get("path") != rel:
        raise ReconcileRequired(
            f"mutation {mutation.id} holds a disposition stage that is not one create of {rel}: reconcile required"
        )
    content = found[0]["payload"]["content"]
    try:
        decided = parse(str(content).encode("utf-8"), target_id)
    except ValidationError as exc:
        raise ReconcileRequired(f"mutation {mutation.id} recorded a disposition that does not read: {exc}") from exc
    if render(decided) != content or decided.reason != reason:
        raise ReconcileRequired(
            f"mutation {mutation.id} recorded a disposition other than this request's: reconcile required",
            reason="recovery_disposition_conflict",
        )
    return decided


def _already_disposed(store: ProjectStore, root: Path, existing: Disposition, reason: str) -> DispositionResult:
    """§35.14: the committed record of this very target, digest, decision and reason is answered, never written again."""
    held = committed(store, existing.path)
    if held is not True:
        raise ReconcileRequired(
            f"{existing.path} is present but is not the record HEAD has committed, and no pending disposition of this "
            "request decided it; a disposition is never adopted or rewritten: reconcile required",
            reason="recovery_disposition_conflict",
        )
    if existing.reason != reason:
        raise ReconcileRequired(
            f"{existing.target_id} is already disposed with another reason; a second, conflicting disposition is never "
            "written, chosen by time or appended: reconcile required",
            reason="recovery_disposition_conflict",
        )
    if existing.target_kind == KIND_MUTATION:
        state = mutation_target_state(store, existing.target_id)
    else:
        state = review_run_target_state(store, existing.target_id)
    if state.state != STATE_EFFECTIVE:
        raise ReconcileRequired(
            f"{existing.target_id} is already disposed, and its state is no longer the one the disposition binds "
            f"({state.problem}): reconcile required",
            reason="recovery_disposition_conflict",
        )
    return DispositionResult(
        "already_disposed", root, existing.target_kind, existing.target_id, existing.target_state_digest,
        existing.path, head=gitcmd.head_commit(root),
    )


def _postcheck(store: ProjectStore, mutation: Any, decided: Disposition, preexisting: list[str]) -> str:
    """The committed record is exactly the decided one, recovery takes the target out, and nothing else moved."""
    from . import gitops
    from .mutation import MutationController

    root = store.root
    rel = decided.path
    effects: list[dict[str, Any]] = mutation.effects
    written = {e["payload"]["path"] for e in effects if e["kind"] in ("write_file", "create_file")}
    if written != {rel} or any(e["kind"] in ("add_relation", "remove_relation", "append_event") for e in effects):
        raise StopError(f"postcheck: the disposition wrote more than its record: {sorted(written)}", code="postcheck_failed")
    commits = [e for e in effects if e["kind"] == "git_commit"]
    if len(commits) != 1 or commits[0].get("applied") is not True:
        raise StopError("postcheck: the disposition has not one applied commit", code="postcheck_failed")
    head = gitcmd.head_commit(root)
    # A commit made right before an interruption kept its ID from being saved carries none; HEAD's own bytes
    # below still prove the record is committed as decided.
    made = commits[0].get("commit_id")
    if made is not None and (
        not isinstance(made, str) or gitcmd.commit_changes(root, made) != [rel]
        or head is None or gitcmd.descends_from(root, head, made) is not True
    ):
        raise StopError("postcheck: HEAD does not hold the commit of the record alone", code="postcheck_failed")
    if gitcmd.blob_at(root, head, rel) != render(decided).encode("utf-8") or gitcmd.changed_against_head(root, [rel]):
        raise StopError(f"postcheck: {head} does not hold the decided disposition as written", code="postcheck_failed")
    if read_disposition(store, decided.target_id) != decided:
        raise StopError("postcheck: the disposition does not read back as decided", code="postcheck_failed")
    if decided.target_kind == KIND_MUTATION:
        state = mutation_target_state(store, decided.target_id)
        active = {record["mutation_id"] for record in MutationController(store).list_pending()}
        if state.state != STATE_EFFECTIVE or decided.target_id in active:
            raise StopError("postcheck: recovery still selects the disposed mutation", code="postcheck_failed")
    elif review_run_target_state(store, decided.target_id).state != STATE_EFFECTIVE:
        raise StopError("postcheck: recovery does not take the disposed Review Run aside", code="postcheck_failed")
    lost = sorted(set(preexisting) - set(gitops.capture_preexisting_dirty(root)))
    if lost:
        raise StopError("postcheck: unrelated changes were consumed: " + ", ".join(lost), code="postcheck_failed")
    return head


__all__ = [
    "COMMIT_MESSAGE",
    "active_pending",
    "open_disposition_mutation",
    "refuse_disposed",
    "require_no_pending_disposition",
    "CONTRACTS",
    "Disposition",
    "DispositionResult",
    "OWNER",
    "REASON_DISPOSED_BY_HUMAN",
    "SCHEMA",
    "STATE_EFFECTIVE",
    "STATE_INVALID",
    "STATE_NONE",
    "STATE_UNCOMMITTED",
    "TargetState",
    "VERSION",
    "dispose_recovery",
    "disposition_ids",
    "disposition_rel",
    "in_recovery_namespace",
    "mutation_state_digest",
    "mutation_target_state",
    "namespace_problems",
    "normalize_reason",
    "parse",
    "read_disposition",
    "render",
    "require_disposition_path",
    "review_run_closure",
    "review_run_state_digest",
    "review_run_target_state",
    "target_kind",
]
