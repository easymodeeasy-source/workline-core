"""The canonical Review records, and what each one must say to be read at all.

Seven immutable record kinds live under ``.workline/review/`` (``R1``). Each
declares its own schema and version inside its canonical bytes, and each is
validated on the way in and on the way out: a record this module will not build
is a record :mod:`workline.review.store` will not read, so a Project cannot come
to hold a Review record that only one side of the boundary understands.

```text
gate generation     the immutable snapshot of one Review Run's gate state
receipt             the authorization a sealed generation issues
consumption         the one use of one authorization
supersession        the fact that a Receipt was invalidated
candidate snapshot  clone-safe material to rebuild the reviewed artifact
task input          clone-safe material to rebuild an accepted task's request
activation          the P3 boundary between legacy and review-v1 terminals
```

None of them is lifecycle truth. ``ProjectView`` / ``state.py`` never reads any
of them, and nothing here derives Work, Phase or Roadmap state.

Validation is deliberately total rather than tolerant. An unknown field is a
STOP, not something to drop: a field this build does not know is a field whose
meaning it cannot honour, and silently ignoring it would let a record written
under a contract this build does not implement look acceptable.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from ..errors import ValidationError
from ..ids import is_valid_id
from . import serialize

#: A lowercase hex SHA-256, the shape every Review digest identity has.
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

#: A Review Run's gate generations are numbered from here, upward by exactly one.
FIRST_GENERATION = 1

#: The terminal states a stored generation may declare. ``superseded`` is not
#: among them by design (``R1`` §4): supersession is derived from the existence
#: of a later valid generation in the validated chain, never by rewriting an
#: immutable file.
GATE_STATUS_OPEN = "open"
GATE_STATUS_SEALED = "sealed_authorized"
GATE_STATUSES = (GATE_STATUS_OPEN, GATE_STATUS_SEALED)

#: How an accepted task's Candidate material is reconstructed after runtime loss.
RECONSTRUCTION_SNAPSHOT = "snapshot"
RECONSTRUCTION_BUILDER = "builder_v1"
RECONSTRUCTION_MODES = (RECONSTRUCTION_SNAPSHOT, RECONSTRUCTION_BUILDER)

#: A settled task's terminal status. ``accepted`` is not a status here: being
#: accepted is being present in ``accepted_tasks``, and being settled is being
#: present in ``settled_tasks``. The two are different facts and are never
#: collapsed into one field (``R3``).
TASK_SETTLED_OK = "completed"
TASK_SETTLED_FAILED = "failed"
TASK_SETTLED_STATUSES = (TASK_SETTLED_OK, TASK_SETTLED_FAILED)

SCHEMA_GATE = "review-gate-generation"
SCHEMA_RECEIPT = "review-authorization-receipt"
SCHEMA_CONSUMPTION = "review-consumption"
SCHEMA_SUPERSESSION = "review-supersession"
SCHEMA_CANDIDATE_SNAPSHOT = "review-candidate-snapshot"
SCHEMA_TASK_INPUT = "review-task-input"
SCHEMA_ACTIVATION = "review-work-terminal-activation"

VERSION = 1

#: The terminal event a Work-kind Consumption binds (``R4`` section 2).
WORK_TERMINAL_EVENT = "work_completed"

#: The operation contract a review-v1 Work terminal event declares (``R4`` §5).
#: P1 defines the constant; P3 activates the behaviour.
OPERATION_CONTRACT_REVIEW_V1 = "review-v1"


# --------------------------------------------------------------------------- field checks
#
# One place decides what "present and well formed" means, so that every record
# kind refuses the same shapes for the same reasons.

def _require_text(record: dict[str, Any], key: str, described: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{described} needs text {key}", code="review_record_invalid")
    return value


def _require_digest(record: dict[str, Any], key: str, described: str) -> str:
    value = _require_text(record, key, described)
    if DIGEST_RE.match(value) is None:
        raise ValidationError(
            f"{described} {key} is not a lowercase hex SHA-256: {value!r}", code="review_record_invalid"
        )
    return value


def _require_id(record: dict[str, Any], key: str, kind: str, described: str) -> str:
    value = _require_text(record, key, described)
    if not is_valid_id(value, kind):
        raise ValidationError(f"{described} {key} is not a {kind} id: {value!r}", code="review_record_invalid")
    return value


def _require_int(record: dict[str, Any], key: str, described: str, *, minimum: int) -> int:
    value = record.get(key)
    # ``bool`` is an ``int`` in Python; a flag is never a count here.
    if type(value) is not int or value < minimum:
        raise ValidationError(
            f"{described} needs integer {key} >= {minimum}, not {value!r}", code="review_record_invalid"
        )
    return value


def _require_choice(record: dict[str, Any], key: str, allowed: tuple[str, ...], described: str) -> str:
    value = _require_text(record, key, described)
    if value not in allowed:
        raise ValidationError(
            f"{described} {key} is {value!r}, not one of {', '.join(allowed)}", code="review_record_invalid"
        )
    return value


def _require_list(record: dict[str, Any], key: str, described: str) -> list[Any]:
    value = record.get(key)
    if not isinstance(value, list):
        raise ValidationError(f"{described} needs list {key}", code="review_record_invalid")
    return value


def _require_mapping(value: object, described: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{described} must be a mapping", code="review_record_invalid")
    return value


def _require_exact_fields(record: dict[str, Any], expected: tuple[str, ...], described: str) -> None:
    """Refuse a record that carries a field this build does not know, or lacks one it needs.

    Total rather than tolerant on purpose: a field this build cannot interpret
    is a field whose contract it cannot honour, and dropping it silently would
    let a record written under a contract this build does not implement pass
    for one it does.
    """
    found = set(record)
    unknown = sorted(found - set(expected))
    if unknown:
        raise ValidationError(
            f"{described} holds unknown field(s): {', '.join(unknown)}", code="review_record_invalid"
        )
    missing = sorted(set(expected) - found)
    if missing:
        raise ValidationError(
            f"{described} is missing field(s): {', '.join(missing)}", code="review_record_invalid"
        )


def _header(schema: str) -> dict[str, Any]:
    return {serialize.SCHEMA_KEY: schema, serialize.VERSION_KEY: VERSION}


# --------------------------------------------------------------------------- accepted / settled task descriptors

#: What an accepted task descriptor binds. ``candidate_material_digest`` and
#: ``task_input_digest`` are here because R3 §5 makes *how* a task and Candidate
#: are reconstructed material, not only the artifact and request they come out
#: as: a well-formed replacement of the provenance that happens to reproduce the
#: same ``candidate_hash`` or ``request_digest`` is still a change.
ACCEPTED_TASK_FIELDS = (
    "task_id",
    "task_slot",
    "task_kind",
    "reviewer_identity",
    "reviewer_version",
    "candidate_hash",
    "candidate_material_digest",
    "reconstruction_mode",
    "request_digest",
    "task_input_digest",
    "review_context_hash",
    "effective_policy_hash",
)

SETTLED_TASK_FIELDS = ("task_id", "status", "result_digest", "settled_generation")


def validate_accepted_task(value: object, described: str) -> dict[str, Any]:
    record = _require_mapping(value, f"{described} accepted task")
    _require_exact_fields(record, ACCEPTED_TASK_FIELDS, f"{described} accepted task")
    _require_id(record, "task_id", "review_task", described)
    _require_text(record, "task_slot", described)
    _require_text(record, "task_kind", described)
    _require_text(record, "reviewer_identity", described)
    _require_text(record, "reviewer_version", described)
    for key in (
        "candidate_hash",
        "candidate_material_digest",
        "request_digest",
        "task_input_digest",
        "review_context_hash",
        "effective_policy_hash",
    ):
        _require_digest(record, key, described)
    _require_choice(record, "reconstruction_mode", RECONSTRUCTION_MODES, described)
    return record


def validate_settled_task(value: object, described: str) -> dict[str, Any]:
    record = _require_mapping(value, f"{described} settled task")
    _require_exact_fields(record, SETTLED_TASK_FIELDS, f"{described} settled task")
    _require_id(record, "task_id", "review_task", described)
    _require_choice(record, "status", TASK_SETTLED_STATUSES, described)
    _require_digest(record, "result_digest", described)
    _require_int(record, "settled_generation", described, minimum=FIRST_GENERATION)
    return record


# --------------------------------------------------------------------------- gate generation

GATE_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "review_run_id",
    "generation",
    "previous_generation",
    "previous_digest",
    "review_kind",
    "target_identity",
    "operation_identity",
    "candidate_hash",
    "review_context_hash",
    "effective_policy_hash",
    "evidence_digest",
    "coverage_digest",
    "raw_report_set_digest",
    "adjudication_digest",
    "obligation_digest",
    "accepted_tasks",
    "settled_tasks",
    "status",
    "receipt_id",
    "authorized_operation_stage",
)


@dataclass(frozen=True)
class GateGeneration:
    """One immutable snapshot of a Review Run's gate state.

    A generation is never edited. What changes gate state is the next
    generation, which names this one and its digest, so the chain is what a
    reader validates rather than the newest file alone.
    """

    review_run_id: str
    generation: int
    previous_generation: int | None
    previous_digest: str | None
    review_kind: str
    target_identity: str
    operation_identity: str
    candidate_hash: str
    review_context_hash: str
    effective_policy_hash: str
    evidence_digest: str
    coverage_digest: str
    raw_report_set_digest: str
    adjudication_digest: str
    obligation_digest: str
    accepted_tasks: tuple[dict[str, Any], ...]
    settled_tasks: tuple[dict[str, Any], ...]
    status: str
    receipt_id: str | None
    #: The operation stage a sealed generation authorizes. The Receipt it issues
    #: carries the same value, and binding the two is only possible if the seal
    #: itself records it: a Receipt's stage checked against nothing is not bound.
    authorized_operation_stage: str | None = None

    @property
    def sealed(self) -> bool:
        return self.status == GATE_STATUS_SEALED

    def accepted_task_ids(self) -> tuple[str, ...]:
        return tuple(str(task["task_id"]) for task in self.accepted_tasks)

    def settled_task_ids(self) -> tuple[str, ...]:
        return tuple(str(task["task_id"]) for task in self.settled_tasks)

    def unsettled_task_ids(self) -> tuple[str, ...]:
        """Accepted tasks with no settlement yet - what a seal may not step over (``R3`` §7)."""
        settled = set(self.settled_task_ids())
        return tuple(task_id for task_id in self.accepted_task_ids() if task_id not in settled)

    def to_record(self) -> dict[str, Any]:
        record = _header(SCHEMA_GATE)
        record.update(
            {
                "review_run_id": self.review_run_id,
                "generation": self.generation,
                "previous_generation": self.previous_generation,
                "previous_digest": self.previous_digest,
                "review_kind": self.review_kind,
                "target_identity": self.target_identity,
                "operation_identity": self.operation_identity,
                "candidate_hash": self.candidate_hash,
                "review_context_hash": self.review_context_hash,
                "effective_policy_hash": self.effective_policy_hash,
                "evidence_digest": self.evidence_digest,
                "coverage_digest": self.coverage_digest,
                "raw_report_set_digest": self.raw_report_set_digest,
                "adjudication_digest": self.adjudication_digest,
                "obligation_digest": self.obligation_digest,
                "accepted_tasks": [dict(task) for task in self.accepted_tasks],
                "settled_tasks": [dict(task) for task in self.settled_tasks],
                "status": self.status,
                "receipt_id": self.receipt_id,
                "authorized_operation_stage": self.authorized_operation_stage,
            }
        )
        return record

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "GateGeneration":
        serialize.require_schema(record, SCHEMA_GATE, VERSION, described)
        _require_exact_fields(record, GATE_FIELDS, described)
        generation = _require_int(record, "generation", described, minimum=FIRST_GENERATION)
        previous_generation = record.get("previous_generation")
        previous_digest = record.get("previous_digest")
        if generation == FIRST_GENERATION:
            if previous_generation is not None or previous_digest is not None:
                raise ValidationError(
                    f"{described} is generation {FIRST_GENERATION} and names a predecessor",
                    code="review_gate_chain",
                )
        else:
            if previous_generation != generation - 1:
                raise ValidationError(
                    f"{described} names predecessor {previous_generation!r}, not {generation - 1}",
                    code="review_gate_chain",
                )
            _require_digest(record, "previous_digest", described)
        status = _require_choice(record, "status", GATE_STATUSES, described)
        receipt_id = record.get("receipt_id")
        if receipt_id is not None and not is_valid_id(str(receipt_id), "review_receipt"):
            raise ValidationError(
                f"{described} receipt_id is not a review_receipt id: {receipt_id!r}", code="review_record_invalid"
            )
        if status == GATE_STATUS_OPEN and receipt_id is not None:
            raise ValidationError(
                f"{described} is {GATE_STATUS_OPEN} and carries a receipt_id; only a sealed generation issues one",
                code="review_record_invalid",
            )
        stage = record.get("authorized_operation_stage")
        if status == GATE_STATUS_SEALED:
            # A seal is what issues the Receipt (R3 section 7), and it records the
            # stage it authorizes so that the Receipt's stage is bound to something.
            if receipt_id is None:
                raise ValidationError(f"{described} is sealed and issues no receipt", code="review_record_invalid")
            if not isinstance(stage, str) or not stage:
                raise ValidationError(
                    f"{described} is sealed and names no authorized_operation_stage", code="review_record_invalid"
                )
        elif stage is not None:
            raise ValidationError(
                f"{described} is {GATE_STATUS_OPEN} and names an authorized_operation_stage; only a seal authorizes one",
                code="review_record_invalid",
            )
        accepted = tuple(validate_accepted_task(item, described) for item in _require_list(record, "accepted_tasks", described))
        settled = tuple(validate_settled_task(item, described) for item in _require_list(record, "settled_tasks", described))
        accepted_ids = [str(task["task_id"]) for task in accepted]
        if len(set(accepted_ids)) != len(accepted_ids):
            raise ValidationError(f"{described} accepts the same task twice", code="review_record_invalid")
        settled_ids = [str(task["task_id"]) for task in settled]
        if len(set(settled_ids)) != len(settled_ids):
            raise ValidationError(f"{described} settles the same task twice", code="review_record_invalid")
        unknown_settled = sorted(set(settled_ids) - set(accepted_ids))
        if unknown_settled:
            raise ValidationError(
                f"{described} settles task(s) it never accepted: {', '.join(unknown_settled)}",
                code="review_record_invalid",
            )
        future = sorted(str(task["task_id"]) for task in settled if task["settled_generation"] > generation)
        if future:
            raise ValidationError(
                f"{described} is generation {generation} and holds settlement(s) from a later generation: "
                f"{', '.join(future)}",
                code="review_gate_chain",
            )
        return GateGeneration(
            review_run_id=_require_id(record, "review_run_id", "review_run", described),
            generation=generation,
            previous_generation=None if generation == FIRST_GENERATION else generation - 1,
            previous_digest=None if generation == FIRST_GENERATION else str(previous_digest),
            review_kind=_require_text(record, "review_kind", described),
            target_identity=_require_text(record, "target_identity", described),
            operation_identity=_require_text(record, "operation_identity", described),
            candidate_hash=_require_digest(record, "candidate_hash", described),
            review_context_hash=_require_digest(record, "review_context_hash", described),
            effective_policy_hash=_require_digest(record, "effective_policy_hash", described),
            evidence_digest=_require_digest(record, "evidence_digest", described),
            coverage_digest=_require_digest(record, "coverage_digest", described),
            raw_report_set_digest=_require_digest(record, "raw_report_set_digest", described),
            adjudication_digest=_require_digest(record, "adjudication_digest", described),
            obligation_digest=_require_digest(record, "obligation_digest", described),
            accepted_tasks=accepted,
            settled_tasks=settled,
            status=status,
            receipt_id=None if receipt_id is None else str(receipt_id),
            authorized_operation_stage=None if stage is None else str(stage),
        )


# --------------------------------------------------------------------------- authorization receipt

RECEIPT_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "receipt_id",
    "review_run_id",
    "review_generation",
    "review_kind",
    "target_identity",
    "operation_identity",
    "authorized_candidate_hash",
    "review_context_hash",
    "effective_policy_hash",
    "coverage_hash",
    "adjudication_hash",
    "obligation_digest",
    "unresolved_obligations",
    "authorized_operation_stage",
)


@dataclass(frozen=True)
class Receipt:
    """What a sealed generation authorizes - and nothing about whether it was used.

    A Receipt is not completion and not Consumption. It says an exact Candidate
    was authorized under an exact Context and Policy; whether that authorization
    has been spent is a :class:`Consumption` question, answered separately
    (``R4``).

    It deliberately carries no commit SHA of its own storage: a Receipt cannot
    contain the identity of the commit that stores it.
    """

    receipt_id: str
    review_run_id: str
    review_generation: int
    review_kind: str
    target_identity: str
    operation_identity: str
    authorized_candidate_hash: str
    review_context_hash: str
    effective_policy_hash: str
    coverage_hash: str
    adjudication_hash: str
    obligation_digest: str
    unresolved_obligations: int
    authorized_operation_stage: str

    def to_record(self) -> dict[str, Any]:
        record = _header(SCHEMA_RECEIPT)
        record.update(
            {
                "receipt_id": self.receipt_id,
                "review_run_id": self.review_run_id,
                "review_generation": self.review_generation,
                "review_kind": self.review_kind,
                "target_identity": self.target_identity,
                "operation_identity": self.operation_identity,
                "authorized_candidate_hash": self.authorized_candidate_hash,
                "review_context_hash": self.review_context_hash,
                "effective_policy_hash": self.effective_policy_hash,
                "coverage_hash": self.coverage_hash,
                "adjudication_hash": self.adjudication_hash,
                "obligation_digest": self.obligation_digest,
                "unresolved_obligations": self.unresolved_obligations,
                "authorized_operation_stage": self.authorized_operation_stage,
            }
        )
        return record

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "Receipt":
        serialize.require_schema(record, SCHEMA_RECEIPT, VERSION, described)
        _require_exact_fields(record, RECEIPT_FIELDS, described)
        unresolved = _require_int(record, "unresolved_obligations", described, minimum=0)
        if unresolved != 0:
            raise ValidationError(
                f"{described} carries {unresolved} unresolved obligation(s); a Receipt issues only at zero",
                code="review_record_invalid",
            )
        return Receipt(
            receipt_id=_require_id(record, "receipt_id", "review_receipt", described),
            review_run_id=_require_id(record, "review_run_id", "review_run", described),
            review_generation=_require_int(record, "review_generation", described, minimum=FIRST_GENERATION),
            review_kind=_require_text(record, "review_kind", described),
            target_identity=_require_text(record, "target_identity", described),
            operation_identity=_require_text(record, "operation_identity", described),
            authorized_candidate_hash=_require_digest(record, "authorized_candidate_hash", described),
            review_context_hash=_require_digest(record, "review_context_hash", described),
            effective_policy_hash=_require_digest(record, "effective_policy_hash", described),
            coverage_hash=_require_digest(record, "coverage_hash", described),
            adjudication_hash=_require_digest(record, "adjudication_hash", described),
            obligation_digest=_require_digest(record, "obligation_digest", described),
            unresolved_obligations=unresolved,
            authorized_operation_stage=_require_text(record, "authorized_operation_stage", described),
        )


# --------------------------------------------------------------------------- consumption

CONSUMPTION_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "consumption_id",
    "receipt_id",
    "review_run_id",
    "review_generation",
    "review_kind",
    "authorized_candidate_hash",
    "operation_identity",
    "operation_mutation_id",
    "terminal_event_id",
    "terminal_event_type",
    "target_identity",
    "authorized_result_commit_sha",
)


@dataclass(frozen=True)
class Consumption:
    """The one use of one authorization.

    ``terminal_event_id`` and ``authorized_result_commit_sha`` are the Work-kind
    bindings; a planning or policy Consumption leaves them null and is unique by
    Receipt alone, because those kinds never invent a Work terminal event
    (``R4`` §7).

    P1 builds the identity and cardinality foundation only. The P3 totality rule
    - that a review-v1 ``work_completed`` has exactly one Consumption - is not
    applied to the current START path by anything here.
    """

    consumption_id: str
    receipt_id: str
    review_run_id: str
    review_generation: int
    review_kind: str
    authorized_candidate_hash: str
    operation_identity: str
    operation_mutation_id: str
    terminal_event_id: str | None
    terminal_event_type: str | None
    target_identity: str
    authorized_result_commit_sha: str | None

    @property
    def work_kind(self) -> bool:
        """Whether this Consumption binds a Work terminal event (``R4`` section 2)."""
        return self.terminal_event_id is not None

    @property
    def work_id(self) -> str | None:
        """The Work a Work-kind Consumption terminates - its target - and ``None`` for any other kind."""
        return self.target_identity if self.work_kind else None

    def to_record(self) -> dict[str, Any]:
        record = _header(SCHEMA_CONSUMPTION)
        record.update(
            {
                "consumption_id": self.consumption_id,
                "receipt_id": self.receipt_id,
                "review_run_id": self.review_run_id,
                "review_generation": self.review_generation,
                "review_kind": self.review_kind,
                "authorized_candidate_hash": self.authorized_candidate_hash,
                "operation_identity": self.operation_identity,
                "operation_mutation_id": self.operation_mutation_id,
                "terminal_event_id": self.terminal_event_id,
                "terminal_event_type": self.terminal_event_type,
                "target_identity": self.target_identity,
                "authorized_result_commit_sha": self.authorized_result_commit_sha,
            }
        )
        return record

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "Consumption":
        serialize.require_schema(record, SCHEMA_CONSUMPTION, VERSION, described)
        _require_exact_fields(record, CONSUMPTION_FIELDS, described)
        event_id = record.get("terminal_event_id")
        event_type = record.get("terminal_event_type")
        commit = record.get("authorized_result_commit_sha")
        # A Work-kind Consumption binds one terminal event of one Work to one
        # authorized result commit (R4 section 2). The three are a single binding:
        # either all are there, or - for a planning or policy Consumption, which
        # never invents a Work terminal event (R4 section 7) - none is.
        present = [value is not None for value in (event_id, event_type, commit)]
        if any(present) and not all(present):
            raise ValidationError(
                f"{described} carries part of a Work terminal binding (terminal_event_id, terminal_event_type, "
                "authorized_result_commit_sha); a Work-kind Consumption carries all three and any other kind none",
                code="review_record_invalid",
            )
        if event_id is not None:
            if not is_valid_id(str(event_id), "event"):
                raise ValidationError(
                    f"{described} terminal_event_id is not an event id: {event_id!r}", code="review_record_invalid"
                )
            if event_type != WORK_TERMINAL_EVENT:
                raise ValidationError(
                    f"{described} terminal_event_type is {event_type!r}; a Work terminal Consumption binds "
                    f"{WORK_TERMINAL_EVENT}",
                    code="review_record_invalid",
                )
            if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", commit) is None:
                raise ValidationError(
                    f"{described} authorized_result_commit_sha is not a full commit id: {commit!r}",
                    code="review_record_invalid",
                )
            target = record.get("target_identity")
            if not isinstance(target, str) or not is_valid_id(target, "work"):
                raise ValidationError(
                    f"{described} binds a Work terminal event but its target_identity is not a work id: {target!r}",
                    code="review_record_invalid",
                )
        return Consumption(
            consumption_id=_require_id(record, "consumption_id", "review_consumption", described),
            receipt_id=_require_id(record, "receipt_id", "review_receipt", described),
            review_run_id=_require_id(record, "review_run_id", "review_run", described),
            review_generation=_require_int(record, "review_generation", described, minimum=FIRST_GENERATION),
            review_kind=_require_text(record, "review_kind", described),
            authorized_candidate_hash=_require_digest(record, "authorized_candidate_hash", described),
            operation_identity=_require_text(record, "operation_identity", described),
            operation_mutation_id=_require_id(record, "operation_mutation_id", "mutation", described),
            terminal_event_id=None if event_id is None else str(event_id),
            terminal_event_type=None if event_type is None else str(event_type),
            target_identity=_require_text(record, "target_identity", described),
            authorized_result_commit_sha=None if commit is None else str(commit),
        )


# --------------------------------------------------------------------------- supersession

SUPERSESSION_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "superseded_receipt_id",
    "review_run_id",
    "superseding_generation",
    "reason",
)


@dataclass(frozen=True)
class Supersession:
    """The immutable fact that a Receipt was invalidated before it was consumed."""

    superseded_receipt_id: str
    review_run_id: str
    superseding_generation: int
    reason: str

    def to_record(self) -> dict[str, Any]:
        record = _header(SCHEMA_SUPERSESSION)
        record.update(
            {
                "superseded_receipt_id": self.superseded_receipt_id,
                "review_run_id": self.review_run_id,
                "superseding_generation": self.superseding_generation,
                "reason": self.reason,
            }
        )
        return record

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "Supersession":
        serialize.require_schema(record, SCHEMA_SUPERSESSION, VERSION, described)
        _require_exact_fields(record, SUPERSESSION_FIELDS, described)
        return Supersession(
            superseded_receipt_id=_require_id(record, "superseded_receipt_id", "review_receipt", described),
            review_run_id=_require_id(record, "review_run_id", "review_run", described),
            superseding_generation=_require_int(record, "superseding_generation", described, minimum=FIRST_GENERATION),
            reason=_require_text(record, "reason", described),
        )


# --------------------------------------------------------------------------- candidate snapshot

CANDIDATE_SNAPSHOT_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "candidate_hash",
    "reconstruction_mode",
    "projection_semantics_version",
    "material",
    "builder",
)


@dataclass(frozen=True)
class CandidateSnapshot:
    """Clone-safe material to rebuild the exact reviewed artifact.

    A digest is never reconstruction material (``R1`` §6). In ``snapshot`` mode
    the record carries the material itself; in ``builder_v1`` mode it carries a
    deterministic builder's identity, version and the complete ordered identities
    of its clone-safe inputs, which is what lets a fresh clone regenerate the
    identical projection instead of guessing at one.
    """

    candidate_hash: str
    reconstruction_mode: str
    projection_semantics_version: str
    material: dict[str, Any] | None
    builder: dict[str, Any] | None

    def to_record(self) -> dict[str, Any]:
        record = _header(SCHEMA_CANDIDATE_SNAPSHOT)
        record.update(
            {
                "candidate_hash": self.candidate_hash,
                "reconstruction_mode": self.reconstruction_mode,
                "projection_semantics_version": self.projection_semantics_version,
                "material": self.material,
                "builder": self.builder,
            }
        )
        return record

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "CandidateSnapshot":
        serialize.require_schema(record, SCHEMA_CANDIDATE_SNAPSHOT, VERSION, described)
        _require_exact_fields(record, CANDIDATE_SNAPSHOT_FIELDS, described)
        mode = _require_choice(record, "reconstruction_mode", RECONSTRUCTION_MODES, described)
        material = record.get("material")
        builder = record.get("builder")
        if mode == RECONSTRUCTION_SNAPSHOT:
            if builder is not None:
                raise ValidationError(f"{described} is snapshot mode and carries builder data", code="review_record_invalid")
            _require_mapping(material, f"{described} material")
            if not material:
                raise ValidationError(
                    f"{described} is snapshot mode with no material; a digest is not reconstruction material",
                    code="review_record_invalid",
                )
        else:
            if material is not None:
                raise ValidationError(f"{described} is builder mode and carries snapshot material", code="review_record_invalid")
            envelope = _require_mapping(builder, f"{described} builder")
            _require_exact_fields(envelope, BUILDER_ENVELOPE_FIELDS, f"{described} builder")
            _require_text(envelope, "builder_identity", f"{described} builder")
            _require_text(envelope, "builder_version", f"{described} builder")
            inputs = _require_list(envelope, "inputs", f"{described} builder")
            if not inputs:
                raise ValidationError(
                    f"{described} builder names no inputs; a clone could not rebuild the projection",
                    code="review_record_invalid",
                )
            for item in inputs:
                entry = _require_mapping(item, f"{described} builder input")
                _require_exact_fields(entry, BUILDER_INPUT_FIELDS, f"{described} builder input")
                _require_text(entry, "name", f"{described} builder input")
                _require_text(entry, "identity", f"{described} builder input")
        return CandidateSnapshot(
            candidate_hash=_require_digest(record, "candidate_hash", described),
            reconstruction_mode=mode,
            projection_semantics_version=_require_text(record, "projection_semantics_version", described),
            material=None if material is None else dict(material),
            builder=None if builder is None else dict(builder),
        )


BUILDER_ENVELOPE_FIELDS = ("builder_identity", "builder_version", "inputs")
BUILDER_INPUT_FIELDS = ("name", "identity")


# --------------------------------------------------------------------------- task input

TASK_INPUT_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "task_id",
    "task_slot",
    "task_kind",
    "reviewer_identity",
    "reviewer_version",
    "request_envelope",
    "request_digest",
    "candidate_hash",
    "reconstruction_mode",
    "candidate_material_digest",
    "review_context_hash",
    "effective_policy_hash",
    "accepted_generation",
)


@dataclass(frozen=True)
class TaskInput:
    """Clone-safe material to rebuild an accepted task's exact request.

    A provider job handle is runtime only and is deliberately not here: after
    ``.workline/runtime/**`` is gone, this record plus the Candidate snapshot is
    what a clone rebuilds the same logical task from, and if it cannot, the
    answer is to fail closed rather than to allocate a replacement task ID.
    """

    task_id: str
    task_slot: str
    task_kind: str
    reviewer_identity: str
    reviewer_version: str
    request_envelope: dict[str, Any]
    request_digest: str
    candidate_hash: str
    reconstruction_mode: str
    candidate_material_digest: str
    review_context_hash: str
    effective_policy_hash: str
    accepted_generation: int

    def to_record(self) -> dict[str, Any]:
        record = _header(SCHEMA_TASK_INPUT)
        record.update(
            {
                "task_id": self.task_id,
                "task_slot": self.task_slot,
                "task_kind": self.task_kind,
                "reviewer_identity": self.reviewer_identity,
                "reviewer_version": self.reviewer_version,
                "request_envelope": dict(self.request_envelope),
                "request_digest": self.request_digest,
                "candidate_hash": self.candidate_hash,
                "reconstruction_mode": self.reconstruction_mode,
                "candidate_material_digest": self.candidate_material_digest,
                "review_context_hash": self.review_context_hash,
                "effective_policy_hash": self.effective_policy_hash,
                "accepted_generation": self.accepted_generation,
            }
        )
        return record

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "TaskInput":
        serialize.require_schema(record, SCHEMA_TASK_INPUT, VERSION, described)
        _require_exact_fields(record, TASK_INPUT_FIELDS, described)
        envelope = _require_mapping(record.get("request_envelope"), f"{described} request_envelope")
        if not envelope:
            raise ValidationError(f"{described} carries an empty request envelope", code="review_record_invalid")
        return TaskInput(
            task_id=_require_id(record, "task_id", "review_task", described),
            task_slot=_require_text(record, "task_slot", described),
            task_kind=_require_text(record, "task_kind", described),
            reviewer_identity=_require_text(record, "reviewer_identity", described),
            reviewer_version=_require_text(record, "reviewer_version", described),
            request_envelope=dict(envelope),
            request_digest=_require_digest(record, "request_digest", described),
            candidate_hash=_require_digest(record, "candidate_hash", described),
            reconstruction_mode=_require_choice(record, "reconstruction_mode", RECONSTRUCTION_MODES, described),
            candidate_material_digest=_require_digest(record, "candidate_material_digest", described),
            review_context_hash=_require_digest(record, "review_context_hash", described),
            effective_policy_hash=_require_digest(record, "effective_policy_hash", described),
            accepted_generation=_require_int(record, "accepted_generation", described, minimum=FIRST_GENERATION),
        )


# --------------------------------------------------------------------------- work-terminal activation

ACTIVATION_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "operation_contract",
    "legacy_event_count",
    "legacy_event_prefix_sha256",
    "activation_base_head",
)


@dataclass(frozen=True)
class WorkTerminalActivation:
    """The P3 boundary between legacy Work terminals and review-v1 ones.

    P1 defines the path, the schema and the reader so that the shape is frozen
    and validated, and creates no such record and activates nothing. An absent
    activation record means review-v1 Work terminalization has not been
    activated - which is exactly the state P1 leaves the Project in.
    """

    operation_contract: str
    legacy_event_count: int
    legacy_event_prefix_sha256: str
    activation_base_head: str

    def to_record(self) -> dict[str, Any]:
        record = _header(SCHEMA_ACTIVATION)
        record.update(
            {
                "operation_contract": self.operation_contract,
                "legacy_event_count": self.legacy_event_count,
                "legacy_event_prefix_sha256": self.legacy_event_prefix_sha256,
                "activation_base_head": self.activation_base_head,
            }
        )
        return record

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "WorkTerminalActivation":
        serialize.require_schema(record, SCHEMA_ACTIVATION, VERSION, described)
        _require_exact_fields(record, ACTIVATION_FIELDS, described)
        contract = _require_choice(record, "operation_contract", (OPERATION_CONTRACT_REVIEW_V1,), described)
        head = _require_text(record, "activation_base_head", described)
        if re.fullmatch(r"[0-9a-f]{40}", head) is None:
            raise ValidationError(
                f"{described} activation_base_head is not a full commit id: {head!r}", code="review_record_invalid"
            )
        return WorkTerminalActivation(
            operation_contract=contract,
            legacy_event_count=_require_int(record, "legacy_event_count", described, minimum=0),
            legacy_event_prefix_sha256=_require_digest(record, "legacy_event_prefix_sha256", described),
            activation_base_head=head,
        )
