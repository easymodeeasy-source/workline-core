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

P4 (``WORKLINE_COMPLETION_SPRINT`` §12.22 / §27.5) adds four more, each its own
versioned schema, so no record above changes meaning:

```text
P4 report           one unadjudicated discovery report, named by its own digest
P4 adjudication     the one normalized adjudication of one P4 Review Run
P4 repair batch     the one Repair Batch of one Candidate generation
P4 repair result    the immutable result of one successful repair
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
    "artifact_kind",
)

#: What a Work-kind Consumption says it consumed: a result commit, or an
#: empty-artifact Candidate that has none (F1 §11.3). Any other kind says null.
CONSUMPTION_ARTIFACT_KINDS = ("result_commit", "empty")


@dataclass(frozen=True)
class Consumption:
    """The one use of one authorization.

    ``terminal_event_id`` is the Work-kind discriminator; a planning or policy
    Consumption leaves it null and is unique by Receipt alone, because those
    kinds never invent a Work terminal event (``R4`` §7).

    ``artifact_kind`` says which of the two authorized Work shapes this is
    (F1 §11.3, Gate 2). A Work can complete correctly with no result-path change
    and no deleted path, and START then makes no result commit at all - ordinary
    and correct, not a degenerate case (F1 §11.1, §11.2). Such a Consumption
    binds ``artifact_kind = "empty"`` with no ``authorized_result_commit_sha``,
    and no empty commit is ever synthesized to stand in for one. A result-bearing
    Consumption binds ``artifact_kind = "result_commit"`` with K1. The field is
    what states the absence explicitly instead of leaving a null to be guessed
    at, so the two cases are never told apart by the commit field alone.

    P1 builds the identity and cardinality foundation only. The P3 totality rule
    - that a review-v1 ``work_completed`` has exactly one Consumption - is not
    applied to the current START path by anything here, and neither is the
    Candidate/Consumption ``artifact_kind`` agreement of F3 §14, which is read
    and compared by the F3 terminal-stage and C-2(K2) proofs, not here.
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
    # Declared last, and null for every kind that is not Work-kind, so the
    # existing positional constructions of a non-Work Consumption still build
    # the record they always did (F1 §11.3, implementation note).
    artifact_kind: str | None = None

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
                # Always emitted, present-as-null for a non-Work kind, never
                # omitted: a reader must never have to tell "no artifact_kind"
                # apart from "artifact_kind is null" (F1 §11.3).
                "artifact_kind": self.artifact_kind,
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
        kind = record.get("artifact_kind")
        # The binding rule of F1 §11.3, which replaces the all-or-none rule this
        # record used to apply over the Work-terminal triple. That rule made an
        # empty-artifact Work Consumption unrepresentable - it demanded a result
        # commit from a Work that correctly has none - so the discriminator is
        # now the terminal event, and artifact_kind says which Work shape it is.
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
            target = record.get("target_identity")
            if not isinstance(target, str) or not is_valid_id(target, "work"):
                raise ValidationError(
                    f"{described} binds a Work terminal event but its target_identity is not a work id: {target!r}",
                    code="review_record_invalid",
                )
            if kind not in CONSUMPTION_ARTIFACT_KINDS:
                raise ValidationError(
                    f"{described} artifact_kind is {kind!r}; a Work-kind Consumption is one of "
                    f"{' or '.join(CONSUMPTION_ARTIFACT_KINDS)}",
                    code="review_record_invalid",
                )
            # The commit and the kind say the same thing or the record is not
            # one: a result commit exactly when the artifact is one, and none at
            # all when it is empty. Neither is ever derived from the other.
            if kind == "result_commit":
                if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", commit) is None:
                    raise ValidationError(
                        f"{described} authorized_result_commit_sha is not a full commit id: {commit!r}",
                        code="review_record_invalid",
                    )
            elif commit is not None:
                raise ValidationError(
                    f"{described} artifact_kind is empty and authorized_result_commit_sha is {commit!r}; "
                    "an empty-artifact Consumption binds no result commit",
                    code="review_record_invalid",
                )
        else:
            carried = sorted(
                name
                for name, value in (
                    ("terminal_event_type", event_type),
                    ("authorized_result_commit_sha", commit),
                    ("artifact_kind", kind),
                )
                if value is not None
            )
            if carried:
                raise ValidationError(
                    f"{described} carries {', '.join(carried)} without a terminal_event_id; a Consumption that "
                    "is not Work-kind carries none of terminal_event_id, terminal_event_type, "
                    "authorized_result_commit_sha, artifact_kind",
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
            artifact_kind=None if kind is None else str(kind),
        )


# --------------------------------------------------------------------------- planning consumption (version 2)
#
# The Planning Consumption (P2, ``skills/review``): the P1 Consumption schema at
# version 2, for the two planning kinds only, with a ``persisted_result`` that
# binds the registration commit it consumed the Receipt for. Version 1 keeps
# every record it ever read, with exactly its P1 meaning; a planning kind is
# valid only in version 2, and version 2 only for a planning kind.

PLANNING_CONSUMPTION_VERSION = 2

#: The planning kinds (``skills/review``); a Consumption of either is a Planning Consumption, version 2.
PLANNING_REVIEW_KINDS = ("roadmap-plan-v1", "phase-entry-design-v1")

PLANNING_ADAPTER_IDENTITY = {
    "roadmap-plan-v1": "roadmap-plan-adapter-v1",
    "phase-entry-design-v1": "phase-entry-design-adapter-v1",
}

PERSISTED_RESULT_CONTRACT = "review-v1-planning-persisted-result-v1"

PLANNING_CONSUMPTION_FIELDS = (
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
    "target_identity",
    "persisted_result",
)

PERSISTED_RESULT_COMMON_FIELDS = (
    "contract",
    "request_digest",
    "registration_commit",
    "registration_parent",
    "branch",
    "registration_delta_digest",
    "semantic_projection_digest",
    "adapter_identity",
    "loader_identity",
)

PERSISTED_RESULT_KIND_FIELDS = {
    "roadmap-plan-v1": ("roadmap_id", "phase_ids", "relation_ids"),
    "phase-entry-design-v1": (
        "phase_id",
        "roadmap_id",
        "work_ids",
        "integration_work_id",
        "confirmation_work_id",
        "roadmap_relation_ids",
        "related_relation_ids",
        "canonical_first_work_id",
    ),
}

_FULL_COMMIT = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
_FULL_BRANCH = re.compile(r"refs/heads/\S+")


def _require_full_commit(record: dict[str, Any], key: str, described: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or _FULL_COMMIT.fullmatch(value) is None:
        raise ValidationError(f"{described} {key} is not a full commit id: {value!r}", code="review_record_invalid")
    return value


def _require_keyed_ids(record: dict[str, Any], key: str, kind: str, described: str) -> list[dict[str, str]]:
    items = _require_list(record, key, described)
    seen_keys: set[str] = set()
    seen_ids: set[str] = set()
    for item in items:
        entry = _require_mapping(item, f"{described} {key} entry")
        _require_exact_fields(entry, ("key", "id"), f"{described} {key} entry")
        entry_key = _require_text(entry, "key", f"{described} {key} entry")
        entry_id = _require_id(entry, "id", kind, f"{described} {key} entry")
        if entry_key in seen_keys or entry_id in seen_ids:
            raise ValidationError(f"{described} {key} holds a duplicate", code="review_record_invalid")
        seen_keys.add(entry_key)
        seen_ids.add(entry_id)
    return items


def _require_id_list(record: dict[str, Any], key: str, kind: str, described: str) -> list[str]:
    items = _require_list(record, key, described)
    for item in items:
        if not isinstance(item, str) or not is_valid_id(item, kind):
            raise ValidationError(f"{described} {key} holds {item!r}, not a {kind} id", code="review_record_invalid")
    if len(set(items)) != len(items):
        raise ValidationError(f"{described} {key} holds a duplicate", code="review_record_invalid")
    return items


def _require_optional_id(record: dict[str, Any], key: str, kind: str, described: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    return _require_id(record, key, kind, described)


def _validate_persisted_result(value: object, review_kind: str, target_identity: str, described: str) -> dict[str, Any]:
    where = f"{described} persisted_result"
    result = _require_mapping(value, where)
    _require_exact_fields(result, PERSISTED_RESULT_COMMON_FIELDS + PERSISTED_RESULT_KIND_FIELDS[review_kind], where)
    _require_choice(result, "contract", (PERSISTED_RESULT_CONTRACT,), where)
    _require_digest(result, "request_digest", where)
    _require_full_commit(result, "registration_commit", where)
    _require_full_commit(result, "registration_parent", where)
    branch = result.get("branch")
    if not isinstance(branch, str) or _FULL_BRANCH.fullmatch(branch) is None:
        raise ValidationError(f"{where} branch is not a full branch ref: {branch!r}", code="review_record_invalid")
    _require_digest(result, "registration_delta_digest", where)
    _require_digest(result, "semantic_projection_digest", where)
    _require_choice(result, "adapter_identity", (PLANNING_ADAPTER_IDENTITY[review_kind],), where)
    _require_digest(result, "loader_identity", where)
    if review_kind == "roadmap-plan-v1":
        roadmap_id = _require_id(result, "roadmap_id", "roadmap", where)
        _require_keyed_ids(result, "phase_ids", "phase", where)
        _require_id_list(result, "relation_ids", "relation", where)
        if target_identity != roadmap_id:
            raise ValidationError(
                f"{described} target_identity {target_identity!r} is not its roadmap_id {roadmap_id!r}",
                code="review_record_invalid",
            )
    else:
        phase_id = _require_id(result, "phase_id", "phase", where)
        _require_id(result, "roadmap_id", "roadmap", where)
        _require_keyed_ids(result, "work_ids", "work", where)
        _require_id(result, "integration_work_id", "work", where)
        _require_optional_id(result, "confirmation_work_id", "work", where)
        _require_id_list(result, "roadmap_relation_ids", "relation", where)
        _require_id_list(result, "related_relation_ids", "relation", where)
        _require_optional_id(result, "canonical_first_work_id", "work", where)
        if target_identity != phase_id:
            raise ValidationError(
                f"{described} target_identity {target_identity!r} is not its phase_id {phase_id!r}",
                code="review_record_invalid",
            )
    return result


@dataclass(frozen=True)
class PlanningConsumption:
    """The one use of one planning Receipt, bound to the registration commit it authorized (version 2).

    Reading proves form and bindings only. What it claims - the registration
    commit and parent, the delta and semantic projection digests, the IDs, the
    adapter and loader identities - is never trusted for publication: the
    committed planning proof recomputes or cross-checks every claim from
    committed objects. It carries no Work terminal binding and never invents
    one (``R4`` §7).
    """

    consumption_id: str
    receipt_id: str
    review_run_id: str
    review_generation: int
    review_kind: str
    authorized_candidate_hash: str
    operation_identity: str
    operation_mutation_id: str
    target_identity: str
    persisted_result: dict[str, Any]

    #: A planning Consumption binds no Work terminal event.
    terminal_event_id = None
    terminal_event_type = None
    authorized_result_commit_sha = None

    @property
    def work_kind(self) -> bool:
        return False

    @property
    def work_id(self) -> str | None:
        return None

    @property
    def registration_commit(self) -> str:
        return str(self.persisted_result["registration_commit"])

    def to_record(self) -> dict[str, Any]:
        return {
            serialize.SCHEMA_KEY: SCHEMA_CONSUMPTION,
            serialize.VERSION_KEY: PLANNING_CONSUMPTION_VERSION,
            "consumption_id": self.consumption_id,
            "receipt_id": self.receipt_id,
            "review_run_id": self.review_run_id,
            "review_generation": self.review_generation,
            "review_kind": self.review_kind,
            "authorized_candidate_hash": self.authorized_candidate_hash,
            "operation_identity": self.operation_identity,
            "operation_mutation_id": self.operation_mutation_id,
            "target_identity": self.target_identity,
            "persisted_result": dict(self.persisted_result),
        }

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "PlanningConsumption":
        serialize.require_schema(record, SCHEMA_CONSUMPTION, PLANNING_CONSUMPTION_VERSION, described)
        _require_exact_fields(record, PLANNING_CONSUMPTION_FIELDS, described)
        review_kind = _require_choice(record, "review_kind", PLANNING_REVIEW_KINDS, described)
        target = _require_text(record, "target_identity", described)
        persisted = _validate_persisted_result(record.get("persisted_result"), review_kind, target, described)
        return PlanningConsumption(
            consumption_id=_require_id(record, "consumption_id", "review_consumption", described),
            receipt_id=_require_id(record, "receipt_id", "review_receipt", described),
            review_run_id=_require_id(record, "review_run_id", "review_run", described),
            review_generation=_require_int(record, "review_generation", described, minimum=FIRST_GENERATION),
            review_kind=review_kind,
            authorized_candidate_hash=_require_digest(record, "authorized_candidate_hash", described),
            operation_identity=_require_text(record, "operation_identity", described),
            operation_mutation_id=_require_id(record, "operation_mutation_id", "mutation", described),
            target_identity=target,
            persisted_result=dict(persisted),
        )


# --------------------------------------------------------------------------- policy consumption (version 3)
#
# The Policy Consumption (P6, ``WORKLINE_COMPLETION_SPRINT`` §30.21): the P1 Consumption schema at version 3,
# for the ``project-policy-change-v1`` kind only, with a ``persisted_policy`` that binds the exact local policy
# commit Kp and the persisted Profile projection it consumed the Receipt for. Versions 1 and 2 keep every record
# they ever read with exactly their meaning; the policy kind is valid only in version 3, and version 3 only for
# the policy kind. One Receipt still has at most one Consumption (keyed by the Receipt alone).

POLICY_CONSUMPTION_VERSION = 3

#: The Policy Review kind, and the only kind a version 3 Consumption may name.
POLICY_REVIEW_KIND = "project-policy-change-v1"
POLICY_TARGET_IDENTITY = "project-policy"
PERSISTED_POLICY_CONTRACT = "review-v1-p6-persisted-policy-v1"
POLICY_ADAPTER_IDENTITY = "project-policy-adapter-v1"

POLICY_CONSUMPTION_FIELDS = (
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
    "target_identity",
    "persisted_policy",
)

PERSISTED_POLICY_FIELDS = (
    "contract",
    "policy_change_id",
    "before_profile_version",
    "before_profile_digest",
    "after_profile_version",
    "after_profile_digest",
    "global_baseline_digest",
    "normalized_projection_hash",
    "policy_commit",
    "policy_parent",
    "branch",
    "policy_delta_digest",
    "adapter_identity",
    "loader_identity",
)


def _validate_persisted_policy(value: object, described: str) -> dict[str, Any]:
    where = f"{described} persisted_policy"
    result = _require_mapping(value, where)
    _require_exact_fields(result, PERSISTED_POLICY_FIELDS, where)
    _require_choice(result, "contract", (PERSISTED_POLICY_CONTRACT,), where)
    _require_id(result, "policy_change_id", "review_policy_change", where)
    before_version, before_digest = result.get("before_profile_version"), result.get("before_profile_digest")
    if (before_version is None) != (before_digest is None):
        raise ValidationError(f"{where} names a before Profile version without its digest, or the reverse",
                              code="review_record_invalid")
    if before_version is not None:
        _require_int(result, "before_profile_version", where, minimum=1)
        _require_digest(result, "before_profile_digest", where)
    after_version = _require_int(result, "after_profile_version", where, minimum=1)
    if after_version != (1 if before_version is None else before_version + 1):
        raise ValidationError(f"{where} skips a Profile version", code="review_record_invalid")
    _require_digest(result, "after_profile_digest", where)
    _require_digest(result, "global_baseline_digest", where)
    _require_digest(result, "normalized_projection_hash", where)
    _require_full_commit(result, "policy_commit", where)
    _require_full_commit(result, "policy_parent", where)
    branch = result.get("branch")
    if not isinstance(branch, str) or _FULL_BRANCH.fullmatch(branch) is None:
        raise ValidationError(f"{where} branch is not a full branch ref: {branch!r}", code="review_record_invalid")
    _require_digest(result, "policy_delta_digest", where)
    _require_choice(result, "adapter_identity", (POLICY_ADAPTER_IDENTITY,), where)
    _require_digest(result, "loader_identity", where)
    return result


@dataclass(frozen=True)
class PolicyConsumption:
    """The one use of one Policy Change Receipt, bound to the exact policy commit it authorized (version 3).

    Reading proves form and bindings only; the committed policy proof
    recomputes what it claims from committed objects. It binds no Work terminal
    event and never invents one, and it is not Project lifecycle truth.
    """

    consumption_id: str
    receipt_id: str
    review_run_id: str
    review_generation: int
    review_kind: str
    authorized_candidate_hash: str
    operation_identity: str
    operation_mutation_id: str
    target_identity: str
    persisted_policy: dict[str, Any]

    #: A Policy Consumption binds no Work terminal event.
    terminal_event_id = None
    terminal_event_type = None
    authorized_result_commit_sha = None

    @property
    def work_kind(self) -> bool:
        return False

    @property
    def work_id(self) -> str | None:
        return None

    @property
    def policy_commit(self) -> str:
        return str(self.persisted_policy["policy_commit"])

    def to_record(self) -> dict[str, Any]:
        return {
            serialize.SCHEMA_KEY: SCHEMA_CONSUMPTION,
            serialize.VERSION_KEY: POLICY_CONSUMPTION_VERSION,
            "consumption_id": self.consumption_id,
            "receipt_id": self.receipt_id,
            "review_run_id": self.review_run_id,
            "review_generation": self.review_generation,
            "review_kind": self.review_kind,
            "authorized_candidate_hash": self.authorized_candidate_hash,
            "operation_identity": self.operation_identity,
            "operation_mutation_id": self.operation_mutation_id,
            "target_identity": self.target_identity,
            "persisted_policy": dict(self.persisted_policy),
        }

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "PolicyConsumption":
        serialize.require_schema(record, SCHEMA_CONSUMPTION, POLICY_CONSUMPTION_VERSION, described)
        _require_exact_fields(record, POLICY_CONSUMPTION_FIELDS, described)
        review_kind = _require_choice(record, "review_kind", (POLICY_REVIEW_KIND,), described)
        target = _require_choice(record, "target_identity", (POLICY_TARGET_IDENTITY,), described)
        persisted = _validate_persisted_policy(record.get("persisted_policy"), described)
        return PolicyConsumption(
            consumption_id=_require_id(record, "consumption_id", "review_consumption", described),
            receipt_id=_require_id(record, "receipt_id", "review_receipt", described),
            review_run_id=_require_id(record, "review_run_id", "review_run", described),
            review_generation=_require_int(record, "review_generation", described, minimum=FIRST_GENERATION),
            review_kind=review_kind,
            authorized_candidate_hash=_require_digest(record, "authorized_candidate_hash", described),
            operation_identity=_require_text(record, "operation_identity", described),
            operation_mutation_id=_require_id(record, "operation_mutation_id", "mutation", described),
            target_identity=target,
            persisted_policy=dict(persisted),
        )


# --------------------------------------------------------------------------- global policy consumption (version 4)
#
# The Global Policy Consumption (P7, ``WORKLINE_COMPLETION_SPRINT`` §31.25 / §31.37, allocation A-1): the P1
# Consumption schema at version 4, for the ``global-policy-change-v1`` root meta-review kind only, stored in the root
# policy Review namespace. Its ``persisted_global_policy`` binds the exact root policy commit Kp and the persisted
# Global policy it consumed the Receipt for. It names the single-purpose root policy mutation (``rpm``), never a
# Project mutation, and no Work terminal event. Versions 1 - 3 keep every record they ever read with exactly their
# meaning; the root kind is valid only in version 4, and version 4 only for the root kind. One Receipt still has at
# most one Consumption (keyed by the Receipt alone).

GLOBAL_POLICY_CONSUMPTION_VERSION = 4

#: The root meta-review kind (§31.25), the only kind a version 4 Consumption may name, and its target.
GLOBAL_POLICY_REVIEW_KIND = "global-policy-change-v1"
GLOBAL_POLICY_TARGET_IDENTITY = "global-policy"
PERSISTED_GLOBAL_POLICY_CONTRACT = "review-v1-p7-persisted-global-policy-v1"
#: The total Profile compatibility adapters a Global change persists under - ``policy.COMPATIBILITY_TOTAL_ADAPTER_V1``,
#: restated because this module imports no policy code, and pinned equal.
GLOBAL_POLICY_COMPATIBILITY_ADAPTERS = ("review-v1-p7-total-adapter-v1",)

GLOBAL_POLICY_CONSUMPTION_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "consumption_id",
    "receipt_id",
    "review_run_id",
    "review_generation",
    "review_kind",
    "authorized_candidate_hash",
    "operation_identity",
    "root_policy_mutation_id",
    "target_identity",
    "persisted_global_policy",
)

PERSISTED_GLOBAL_POLICY_FIELDS = (
    "contract",
    "global_policy_change_id",
    "promotion_packet_id",
    "promotion_packet_digest",
    "before_global_policy_version",
    "before_global_policy_digest",
    "after_global_policy_version",
    "after_global_policy_digest",
    "normalized_projection_hash",
    "policy_commit",
    "policy_parent",
    "branch",
    "policy_delta_digest",
    "compatibility_adapter_identity",
    "compatibility_adapter_digest",
    "loader_identity",
)


def _validate_persisted_global_policy(value: object, described: str) -> dict[str, Any]:
    where = f"{described} persisted_global_policy"
    result = _require_mapping(value, where)
    _require_exact_fields(result, PERSISTED_GLOBAL_POLICY_FIELDS, where)
    _require_choice(result, "contract", (PERSISTED_GLOBAL_POLICY_CONTRACT,), where)
    _require_id(result, "global_policy_change_id", "review_global_policy_change", where)
    _require_id(result, "promotion_packet_id", "review_promotion_packet", where)
    _require_digest(result, "promotion_packet_digest", where)
    before = _require_int(result, "before_global_policy_version", where, minimum=1)
    _require_digest(result, "before_global_policy_digest", where)
    after = _require_int(result, "after_global_policy_version", where, minimum=2)
    if after != before + 1:
        raise ValidationError(f"{where} does not persist exactly the next Global policy version", code="review_record_invalid")
    _require_digest(result, "after_global_policy_digest", where)
    _require_digest(result, "normalized_projection_hash", where)
    _require_full_commit(result, "policy_commit", where)
    _require_full_commit(result, "policy_parent", where)
    branch = result.get("branch")
    if not isinstance(branch, str) or _FULL_BRANCH.fullmatch(branch) is None:
        raise ValidationError(f"{where} branch is not a full branch ref: {branch!r}", code="review_record_invalid")
    _require_digest(result, "policy_delta_digest", where)
    _require_choice(result, "compatibility_adapter_identity", GLOBAL_POLICY_COMPATIBILITY_ADAPTERS, where)
    _require_digest(result, "compatibility_adapter_digest", where)
    _require_digest(result, "loader_identity", where)
    return result


@dataclass(frozen=True)
class GlobalPolicyConsumption:
    """The one use of one Global Policy Change Receipt, bound to the exact root policy commit it authorized (v4).

    Reading proves form and bindings only; the root owner's committed proof
    recomputes what it claims from committed objects. It binds no Work terminal
    event and never invents one, and it is neither Project lifecycle truth nor
    a Project record.
    """

    consumption_id: str
    receipt_id: str
    review_run_id: str
    review_generation: int
    review_kind: str
    authorized_candidate_hash: str
    operation_identity: str
    root_policy_mutation_id: str
    target_identity: str
    persisted_global_policy: dict[str, Any]

    #: A Global Policy Consumption binds no Work terminal event.
    terminal_event_id = None
    terminal_event_type = None
    authorized_result_commit_sha = None

    @property
    def work_kind(self) -> bool:
        return False

    @property
    def work_id(self) -> str | None:
        return None

    @property
    def policy_commit(self) -> str:
        return str(self.persisted_global_policy["policy_commit"])

    def to_record(self) -> dict[str, Any]:
        return {
            serialize.SCHEMA_KEY: SCHEMA_CONSUMPTION,
            serialize.VERSION_KEY: GLOBAL_POLICY_CONSUMPTION_VERSION,
            "consumption_id": self.consumption_id,
            "receipt_id": self.receipt_id,
            "review_run_id": self.review_run_id,
            "review_generation": self.review_generation,
            "review_kind": self.review_kind,
            "authorized_candidate_hash": self.authorized_candidate_hash,
            "operation_identity": self.operation_identity,
            "root_policy_mutation_id": self.root_policy_mutation_id,
            "target_identity": self.target_identity,
            "persisted_global_policy": dict(self.persisted_global_policy),
        }

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "GlobalPolicyConsumption":
        serialize.require_schema(record, SCHEMA_CONSUMPTION, GLOBAL_POLICY_CONSUMPTION_VERSION, described)
        _require_exact_fields(record, GLOBAL_POLICY_CONSUMPTION_FIELDS, described)
        review_kind = _require_choice(record, "review_kind", (GLOBAL_POLICY_REVIEW_KIND,), described)
        target = _require_choice(record, "target_identity", (GLOBAL_POLICY_TARGET_IDENTITY,), described)
        persisted = _validate_persisted_global_policy(record.get("persisted_global_policy"), described)
        return GlobalPolicyConsumption(
            consumption_id=_require_id(record, "consumption_id", "review_consumption", described),
            receipt_id=_require_id(record, "receipt_id", "review_receipt", described),
            review_run_id=_require_id(record, "review_run_id", "review_run", described),
            review_generation=_require_int(record, "review_generation", described, minimum=FIRST_GENERATION),
            review_kind=review_kind,
            authorized_candidate_hash=_require_digest(record, "authorized_candidate_hash", described),
            operation_identity=_require_text(record, "operation_identity", described),
            root_policy_mutation_id=_require_id(record, "root_policy_mutation_id", "root_policy_mutation", described),
            target_identity=target,
            persisted_global_policy=dict(persisted),
        )


def consumption_from_record(
    record: dict[str, Any], described: str
) -> "Consumption | PlanningConsumption | PolicyConsumption | GlobalPolicyConsumption":
    """A stored Consumption of any version, read by its own reader.

    Version 1 is the P1 reader, unchanged, and a planning kind is refused
    there; version 2 is the Planning Consumption; version 3 is the Policy
    Consumption (P6); version 4 is the Global Policy Consumption (P7,
    allocation A-1). Any other version is not read. Version 1 reads exactly
    what it always read: that a Policy Receipt is consumed only by a version 3
    Consumption is the P6 validation's, made where a Policy Receipt exists.
    """
    version = record.get(serialize.VERSION_KEY)
    if version == PLANNING_CONSUMPTION_VERSION:
        return PlanningConsumption.from_record(record, described)
    if version == POLICY_CONSUMPTION_VERSION:
        return PolicyConsumption.from_record(record, described)
    if version == GLOBAL_POLICY_CONSUMPTION_VERSION:
        return GlobalPolicyConsumption.from_record(record, described)
    found = Consumption.from_record(record, described)
    if found.review_kind in PLANNING_REVIEW_KINDS:
        raise ValidationError(
            f"{described} is a version {VERSION} Consumption of planning kind {found.review_kind}; a planning "
            f"Consumption is version {PLANNING_CONSUMPTION_VERSION}",
            code="review_record_invalid",
        )
    return found


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


# --------------------------------------------------------------------------- P4 vocabulary (§12 / §27)
#
# The closed vocabularies the four P4 record kinds are validated against. The
# common P4 semantic core (:mod:`workline.review.p4`) uses exactly these, so a
# record this module reads and a decision that module makes cannot disagree
# about what a word means.

SCHEMA_P4_REPORT = "review-p4-report"
SCHEMA_P4_ADJUDICATION = "review-p4-adjudication"
SCHEMA_P4_REPAIR_BATCH = "review-p4-repair-batch"
SCHEMA_P4_REPAIR_RESULT = "review-p4-repair-result"

#: The two P4 Review contracts (§12.21 / G-6): distinct durable identities, never a v1 string.
P4_PLANNING_CONTRACT = "review-v1-planning-p4-v1"
P4_WORK_CONTRACT = "review-v1-work-p4-v1"
#: P6 (§30.12): the Policy Review contract of the ``project-policy-change-v1`` kind. A member of the P4-capable
#: contract family - P4 discovery reports and the P4 adjudication, G1-G5 - with no Repair Batch branch, so a
#: Repair Batch or Repair Result never names it (:data:`P4_REPAIR_CONTRACTS`).
P6_POLICY_CHANGE_CONTRACT = "review-v1-policy-change-p6-v1"
#: P7 (§31.25, addendum RB7C-1 (d)): the root meta-review contract of the ``global-policy-change-v1`` kind - P4
#: discovery reports and the P4 adjudication, G1-G5 in the root policy Review namespace, no Repair Batch branch (so
#: never in :data:`P4_REPAIR_CONTRACTS`), bound under the root non-history family policy only (``p4.CONTRACT_POLICIES``).
P7_GLOBAL_POLICY_CHANGE_CONTRACT = "review-v1-global-policy-change-p4-v1"
P4_CONTRACTS = (P4_PLANNING_CONTRACT, P4_WORK_CONTRACT, P6_POLICY_CHANGE_CONTRACT, P7_GLOBAL_POLICY_CHANGE_CONTRACT)
#: The contracts whose Runs may repair: exactly the two P4 owner contracts, unchanged.
P4_REPAIR_CONTRACTS = (P4_PLANNING_CONTRACT, P4_WORK_CONTRACT)

#: The P4 discovery task slot prefix; the rest of the slot is the viewpoint.
P4_DISCOVERY_SLOT_PREFIX = "p4-discovery."

P4_REPORT_STATUSES = ("completed", "declined")
P4_SEVERITIES = ("HIGH", "MID", "LOW")
P4_SEVERITY_RANK = {"HIGH": 3, "MID": 2, "LOW": 1}

#: §12.4: the one outcome each raw claim is adjudicated to. Only Problem and Improvement are content
#: categories; unsupported and HUMAN are adjudication outcomes, never categories.
OUTCOME_UNSUPPORTED = "unsupported"
OUTCOME_HUMAN = "HUMAN"
OUTCOME_PROBLEM = "Problem"
OUTCOME_IMPROVEMENT = "Improvement"
OUTCOME_DISMISSED = "dismissed_non_actionable"
P4_OUTCOMES = (OUTCOME_UNSUPPORTED, OUTCOME_HUMAN, OUTCOME_PROBLEM, OUTCOME_IMPROVEMENT, OUTCOME_DISMISSED)
P4_CATEGORIES = (OUTCOME_PROBLEM, OUTCOME_IMPROVEMENT)

#: §12.19 / §27.24: the non-blocking current-cycle dispositions, and the one blocking one.
DISPOSITION_REPAIR_REQUIRED = "repair_required"
DISPOSITION_REPAIRED_CURRENT_CYCLE = "repaired_current_cycle"
DISPOSITION_RETAINED_HISTORY_ONLY = "retained_history_only"
DISPOSITION_FUTURE_WORK_CANDIDATE = "future_work_candidate"
DISPOSITION_NO_ACTION = "no_action_after_adjudication"
P4_NONBLOCKING_DISPOSITIONS = (
    DISPOSITION_REPAIRED_CURRENT_CYCLE, DISPOSITION_RETAINED_HISTORY_ONLY, DISPOSITION_FUTURE_WORK_CANDIDATE,
    DISPOSITION_NO_ACTION,
)
P4_DISPOSITIONS = (DISPOSITION_REPAIR_REQUIRED,) + P4_NONBLOCKING_DISPOSITIONS

#: §12.16: the A/B/C relationship of a Finding after a repair.
RELATION_A_NEW = "A_NEW"
RELATION_B_RECURRENCE = "B_RECURRENCE"
RELATION_C_REPAIR_INDUCED = "C_REPAIR_INDUCED"
P4_RELATIONS = (RELATION_A_NEW, RELATION_B_RECURRENCE, RELATION_C_REPAIR_INDUCED)

#: §12.12: how an adjudication resolves a declared discovery coverage gap.
GAP_NOT_APPLICABLE = "not_applicable"
GAP_COVERED = "covered"
GAP_TARGETED_CHECK = "targeted_check_required"
GAP_HUMAN = "HUMAN"
P4_GAP_RESOLUTIONS = (GAP_NOT_APPLICABLE, GAP_COVERED, GAP_TARGETED_CHECK, GAP_HUMAN)

#: §27.11: the one owner branch a settled adjudication derives.
AUTHORIZATION_READY = "AUTHORIZATION_READY"
REPAIR_REQUIRED = "REPAIR_REQUIRED"
HUMAN_WAIT = "HUMAN_WAIT"
P4_ADJUDICATION_OUTCOMES = (AUTHORIZATION_READY, REPAIR_REQUIRED, HUMAN_WAIT)

#: §12.17: the repair strategy a Repair Batch selects.
STRATEGY_ORDINARY = "ordinary"
STRATEGY_CHANGE = "strategy_change"
P4_STRATEGIES = (STRATEGY_ORDINARY, STRATEGY_CHANGE)
P4_STRATEGY_CHANGE_CLASSES = (
    "repair_shared_responsibility",
    "widen_scope",
    "reconsider_state_lifecycle_authority",
    "replace_or_rollback_prior_repair",
    "restructure_around_simpler_invariant",
)

#: §12.14: the one change-impact class every successful repair records.
IMPACT_LOCAL = "LOCAL"
IMPACT_SHARED = "SHARED"
IMPACT_CONTRACT = "CONTRACT"
IMPACT_FOUNDATION = "FOUNDATION"
P4_IMPACT_CLASSES = (IMPACT_LOCAL, IMPACT_SHARED, IMPACT_CONTRACT, IMPACT_FOUNDATION)

P4_REPAIR_SCOPES = ("local", "widened")
P4_REUSE_STATES = ("reusable", "unknown", "invalidated")
P4_VERIFICATION_RESULTS = ("pass", "fail")

#: The longest public-safe P4 text (H-3, P-4) and the longest P4 label.
P4_MAX_TEXT = 2000
P4_MAX_LABEL = 200

#: H-3 (§12.3): shapes a canonical P4 text never carries. Deterministic and deliberately narrow: the
#: reviewer instruction requires public-safe structured output, and this refuses what is recognisably
#: not, before anything is persisted. A refusal never settles the task.
_H3_UNSAFE = (
    ("an absolute Windows drive path", re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")),
    ("a UNC path", re.compile(r"\\\\[^\\\s]")),
    ("a file URL", re.compile(r"(?i)\bfile://")),
    ("a home-relative path", re.compile(r"(?<![A-Za-z0-9._-])~[\\/]")),
    ("an absolute local path", re.compile(r"(?:^|[\s\"'(=,;])/(?:home|Users|root|tmp|var|etc|mnt|opt|private|proc|srv)/")),
    ("a URL credential", re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@")),
    ("a private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY")),
    ("an API-token-like value", re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}")),
    ("a GitHub-token-like value", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("an AWS-key-like value", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("a Slack-token-like value", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("a JWT-like value", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.")),
    ("a credential assignment", re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|token)\s*[:=]\s*\S+")),
)

#: Characters that are never part of public-safe single-line text: line breaks of every kind, other
#: control characters, and the bidirectional overrides that make text read differently than it is.
_H3_FORBIDDEN_CHARS = re.compile(
    "[" + "".join(
        re.escape(chr(code))
        for code in (
            *range(0x00, 0x20), *range(0x7F, 0xA0), 0x2028, 0x2029, 0x200E, 0x200F,
            *range(0x202A, 0x202F), *range(0x2066, 0x206A), 0xFEFF,
        )
    ) + "]"
)


def public_safe_problem(value: object, *, limit: int = P4_MAX_TEXT) -> str | None:
    """Why ``value`` is not H-3 public-safe single-line P4 text, or ``None`` when it is (§12.3, P-4)."""
    if not isinstance(value, str) or not value:
        return "it is not non-empty text"
    if value != value.strip():
        return "it carries surrounding whitespace"
    if len(value) > limit:
        return f"it is longer than {limit} characters"
    if _H3_FORBIDDEN_CHARS.search(value):
        return "it carries a line break or control character"
    for described, pattern in _H3_UNSAFE:
        if pattern.search(value):
            return f"it carries {described}"
    return None


def _require_public_text(record: dict[str, Any], key: str, described: str, *, limit: int = P4_MAX_TEXT) -> str:
    value = record.get(key)
    problem = public_safe_problem(value, limit=limit)
    if problem is not None:
        raise ValidationError(f"{described} {key} is not public-safe P4 text: {problem}", code="review_record_invalid")
    return str(value)


def _require_label(record: dict[str, Any], key: str, described: str) -> str:
    return _require_public_text(record, key, described, limit=P4_MAX_LABEL)


def _require_bool(record: dict[str, Any], key: str, described: str) -> bool:
    value = record.get(key)
    if type(value) is not bool:
        raise ValidationError(f"{described} needs boolean {key}, not {value!r}", code="review_record_invalid")
    return value


def _require_public_list(record: dict[str, Any], key: str, described: str, *, labels: bool = False) -> list[str]:
    items = _require_list(record, key, described)
    for item in items:
        problem = public_safe_problem(item, limit=P4_MAX_LABEL if labels else P4_MAX_TEXT)
        if problem is not None:
            raise ValidationError(
                f"{described} {key} holds text that is not public-safe: {problem}", code="review_record_invalid"
            )
    return items


def _require_sorted_unique(items: list[Any], key: str, described: str) -> None:
    if items != sorted(set(items)):
        raise ValidationError(f"{described} {key} is not sorted and duplicate-free", code="review_record_invalid")


def _require_optional_digest(record: dict[str, Any], key: str, described: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    return _require_digest(record, key, described)


def _require_ids(record: dict[str, Any], key: str, kind: str, described: str) -> list[str]:
    """An ordered, duplicate-free list of ids of one kind (empty allowed)."""
    return _require_id_list(record, key, kind, described)


def _source_key(source: dict[str, Any]) -> tuple[str, str, int]:
    return (str(source["task_id"]), str(source["result_digest"]), int(source["claim_index"]))


SOURCE_FIELDS = ("task_id", "result_digest", "claim_index")


def _validate_source(value: object, described: str, *, exact: bool = True) -> dict[str, Any]:
    source = _require_mapping(value, f"{described} source")
    if exact:
        _require_exact_fields(source, SOURCE_FIELDS, f"{described} source")
    _require_id(source, "task_id", "review_task", described)
    _require_digest(source, "result_digest", described)
    _require_int(source, "claim_index", described, minimum=0)
    return source


# --------------------------------------------------------------------------- P4 report

P4_REPORT_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "review_kind",
    "review_contract",
    "task_id",
    "task_slot",
    "reviewer_identity",
    "reviewer_version",
    "status",
    "claims",
    "coverage",
)
P4_CLAIM_FIELDS = ("severity", "code", "message")
P4_COVERAGE_FIELDS = ("viewpoint", "inspected", "checked", "evidence_ids", "not_inspected")


@dataclass(frozen=True)
class P4Report:
    """One unadjudicated P4 discovery report (§12.3 / §27.4), stored at ``reports/<its own digest>.yaml``.

    "Raw" means unadjudicated, never unsanitized: every text field is already
    H-3 public-safe, and the reviewer's severity is input to adjudication, not
    authority. It is never rewritten to reflect a later adjudication.
    """

    review_kind: str
    review_contract: str
    task_id: str
    task_slot: str
    reviewer_identity: str
    reviewer_version: str
    status: str
    claims: tuple[dict[str, Any], ...]
    coverage: dict[str, Any]

    @property
    def viewpoint(self) -> str:
        return str(self.coverage["viewpoint"])

    def to_record(self) -> dict[str, Any]:
        record = _header(SCHEMA_P4_REPORT)
        record.update(
            {
                "review_kind": self.review_kind,
                "review_contract": self.review_contract,
                "task_id": self.task_id,
                "task_slot": self.task_slot,
                "reviewer_identity": self.reviewer_identity,
                "reviewer_version": self.reviewer_version,
                "status": self.status,
                "claims": [dict(claim) for claim in self.claims],
                "coverage": {
                    "viewpoint": self.coverage["viewpoint"],
                    "inspected": list(self.coverage["inspected"]),
                    "checked": list(self.coverage["checked"]),
                    "evidence_ids": list(self.coverage["evidence_ids"]),
                    "not_inspected": list(self.coverage["not_inspected"]),
                },
            }
        )
        return record

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "P4Report":
        serialize.require_schema(record, SCHEMA_P4_REPORT, VERSION, described)
        _require_exact_fields(record, P4_REPORT_FIELDS, described)
        slot = _require_text(record, "task_slot", described)
        if not slot.startswith(P4_DISCOVERY_SLOT_PREFIX) or len(slot) == len(P4_DISCOVERY_SLOT_PREFIX):
            raise ValidationError(f"{described} task_slot {slot!r} is not a P4 discovery slot", code="review_record_invalid")
        claims: list[dict[str, Any]] = []
        for item in _require_list(record, "claims", described):
            claim = _require_mapping(item, f"{described} claim")
            _require_exact_fields(claim, P4_CLAIM_FIELDS, f"{described} claim")
            _require_choice(claim, "severity", P4_SEVERITIES, f"{described} claim")
            _require_label(claim, "code", f"{described} claim")
            _require_public_text(claim, "message", f"{described} claim")
            claims.append(claim)
        coverage = _require_mapping(record.get("coverage"), f"{described} coverage")
        _require_exact_fields(coverage, P4_COVERAGE_FIELDS, f"{described} coverage")
        viewpoint = _require_label(coverage, "viewpoint", f"{described} coverage")
        if slot != P4_DISCOVERY_SLOT_PREFIX + viewpoint:
            raise ValidationError(
                f"{described} coverage viewpoint {viewpoint!r} is not its task slot's", code="review_record_invalid"
            )
        for key in ("inspected", "checked", "not_inspected"):
            _require_public_list(coverage, key, f"{described} coverage")
        _require_public_list(coverage, "evidence_ids", f"{described} coverage", labels=True)
        status = _require_choice(record, "status", P4_REPORT_STATUSES, described)
        if status == "declined" and claims:
            raise ValidationError(f"{described} is declined and carries claims", code="review_record_invalid")
        return P4Report(
            review_kind=_require_text(record, "review_kind", described),
            review_contract=_require_choice(record, "review_contract", P4_CONTRACTS, described),
            task_id=_require_id(record, "task_id", "review_task", described),
            task_slot=slot,
            reviewer_identity=_require_text(record, "reviewer_identity", described),
            reviewer_version=_require_text(record, "reviewer_version", described),
            status=status,
            claims=tuple(claims),
            coverage=dict(coverage),
        )


# --------------------------------------------------------------------------- P4 adjudication

P4_ADJUDICATION_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "review_run_id",
    "review_kind",
    "target_identity",
    "operation_identity",
    "candidate_hash",
    "candidate_generation",
    "review_context_hash",
    "effective_policy_hash",
    "review_contract",
    "adjudication_contract",
    "instruction",
    "task_id",
    "adjudicator_identity",
    "adjudicator_version",
    "reports",
    "objective_holds",
    "entries",
    "findings",
    "coverage_gaps",
    "prior",
    "outcome",
    "obligations",
    "repair_purpose",
    "strategy_change_class",
)
P4_ENTRY_FIELDS = SOURCE_FIELDS + (
    "outcome",
    "supported",
    "requirement_decision_required",
    "fails_requirement",
    "better_alternative",
    "finding_id",
    "reason",
)
P4_FINDING_FIELDS = (
    "finding_id",
    "category",
    "severity",
    "statement",
    "semantic_surface",
    "repair_identity",
    "sources",
    "disposition",
    "blocking",
    "relation",
    "linked_finding_ids",
    "linked_repair_batch_ids",
    "causal_evidence_digest",
)
P4_GAP_FIELDS = ("task_id", "surface", "resolution", "evidence_ids")
P4_PRIOR_FIELDS = (
    "predecessor_review_run_id",
    "predecessor_adjudication_digest",
    "repair_batch_id",
    "repair_result_digest",
)
P4_OBLIGATION_FIELDS = (
    "unadjudicated",
    "problem_high",
    "problem_mid",
    "problem_low",
    "improvement",
    "human",
    "coverage_unresolved",
    "strategy_change_required",
)


@dataclass(frozen=True)
class P4Adjudication:
    """The one canonical normalized adjudication of one P4 Review Run (§12.5 / §27.6).

    Every raw claim of every bound report has exactly one entry; only Problem
    and Improvement entries name a Finding, and only Findings carry a reserved
    ``finding_id``. The record is structurally total here; the §12.4 decision
    order, merging and causal-linkage rules are checked by
    :func:`workline.review.p4.adjudication_problems`.
    """

    review_run_id: str
    review_kind: str
    target_identity: str
    operation_identity: str
    candidate_hash: str
    candidate_generation: int
    review_context_hash: str
    effective_policy_hash: str
    review_contract: str
    adjudication_contract: str
    instruction: str
    task_id: str
    adjudicator_identity: str
    adjudicator_version: str
    reports: tuple[dict[str, Any], ...]
    objective_holds: bool
    entries: tuple[dict[str, Any], ...]
    findings: tuple[dict[str, Any], ...]
    coverage_gaps: tuple[dict[str, Any], ...]
    prior: dict[str, Any]
    outcome: str
    obligations: dict[str, Any]
    #: What a following repair is for, and - when STRATEGY_CHANGE is required - its class. Present exactly
    #: when the outcome is REPAIR_REQUIRED, so the Repair Batch is rebuilt from this record alone.
    repair_purpose: str | None = None
    strategy_change_class: str | None = None

    def finding(self, finding_id: str) -> dict[str, Any] | None:
        for found in self.findings:
            if found["finding_id"] == finding_id:
                return found
        return None

    def to_record(self) -> dict[str, Any]:
        record = _header(SCHEMA_P4_ADJUDICATION)
        record.update(
            {
                "review_run_id": self.review_run_id,
                "review_kind": self.review_kind,
                "target_identity": self.target_identity,
                "operation_identity": self.operation_identity,
                "candidate_hash": self.candidate_hash,
                "candidate_generation": self.candidate_generation,
                "review_context_hash": self.review_context_hash,
                "effective_policy_hash": self.effective_policy_hash,
                "review_contract": self.review_contract,
                "adjudication_contract": self.adjudication_contract,
                "instruction": self.instruction,
                "task_id": self.task_id,
                "adjudicator_identity": self.adjudicator_identity,
                "adjudicator_version": self.adjudicator_version,
                "reports": [dict(item) for item in self.reports],
                "objective_holds": self.objective_holds,
                "entries": [dict(item) for item in self.entries],
                "findings": [
                    {**dict(item), "sources": [dict(source) for source in item["sources"]]} for item in self.findings
                ],
                "coverage_gaps": [dict(item) for item in self.coverage_gaps],
                "prior": dict(self.prior),
                "outcome": self.outcome,
                "obligations": dict(self.obligations),
                "repair_purpose": self.repair_purpose,
                "strategy_change_class": self.strategy_change_class,
            }
        )
        return record

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "P4Adjudication":
        serialize.require_schema(record, SCHEMA_P4_ADJUDICATION, VERSION, described)
        _require_exact_fields(record, P4_ADJUDICATION_FIELDS, described)
        reports: list[dict[str, Any]] = []
        for item in _require_list(record, "reports", described):
            entry = _require_mapping(item, f"{described} report")
            _require_exact_fields(entry, ("task_id", "result_digest"), f"{described} report")
            _require_id(entry, "task_id", "review_task", described)
            _require_digest(entry, "result_digest", described)
            reports.append(entry)
        if not reports:
            raise ValidationError(f"{described} binds no report", code="review_record_invalid")
        if len({item["result_digest"] for item in reports}) != len(reports):
            raise ValidationError(f"{described} binds one report twice", code="review_record_invalid")
        entries: list[dict[str, Any]] = []
        seen_sources: set[tuple[str, str, int]] = set()
        for item in _require_list(record, "entries", described):
            entry = _require_mapping(item, f"{described} entry")
            _require_exact_fields(entry, P4_ENTRY_FIELDS, f"{described} entry")
            _validate_source(entry, f"{described} entry", exact=False)
            _require_choice(entry, "outcome", P4_OUTCOMES, f"{described} entry")
            for key in ("supported", "requirement_decision_required", "fails_requirement", "better_alternative"):
                _require_bool(entry, key, f"{described} entry")
            _require_optional_id(entry, "finding_id", "review_finding", f"{described} entry")
            _require_public_text(entry, "reason", f"{described} entry")
            key = _source_key(entry)
            if key in seen_sources:
                raise ValidationError(f"{described} adjudicates one claim twice", code="review_record_invalid")
            seen_sources.add(key)
            entries.append(entry)
        findings: list[dict[str, Any]] = []
        finding_ids: set[str] = set()
        for item in _require_list(record, "findings", described):
            finding = _require_mapping(item, f"{described} finding")
            where = f"{described} finding"
            _require_exact_fields(finding, P4_FINDING_FIELDS, where)
            finding_id = _require_id(finding, "finding_id", "review_finding", where)
            if finding_id in finding_ids:
                raise ValidationError(f"{described} holds Finding {finding_id} twice", code="review_record_invalid")
            finding_ids.add(finding_id)
            _require_choice(finding, "category", P4_CATEGORIES, where)
            _require_choice(finding, "severity", P4_SEVERITIES, where)
            _require_public_text(finding, "statement", where)
            _require_label(finding, "semantic_surface", where)
            _require_label(finding, "repair_identity", where)
            sources = [_validate_source(source, where) for source in _require_list(finding, "sources", where)]
            if not sources:
                raise ValidationError(f"{where} {finding_id} names no source claim", code="review_record_invalid")
            if [_source_key(source) for source in sources] != sorted({_source_key(source) for source in sources}):
                raise ValidationError(f"{where} {finding_id} sources are not canonically ordered", code="review_record_invalid")
            _require_choice(finding, "disposition", P4_DISPOSITIONS, where)
            _require_bool(finding, "blocking", where)
            _require_choice(finding, "relation", P4_RELATIONS, where)
            _require_ids(finding, "linked_finding_ids", "review_finding", where)
            _require_ids(finding, "linked_repair_batch_ids", "review_repair_batch", where)
            _require_optional_digest(finding, "causal_evidence_digest", where)
            findings.append(finding)
        gaps: list[dict[str, Any]] = []
        for item in _require_list(record, "coverage_gaps", described):
            gap = _require_mapping(item, f"{described} coverage gap")
            _require_exact_fields(gap, P4_GAP_FIELDS, f"{described} coverage gap")
            _require_id(gap, "task_id", "review_task", f"{described} coverage gap")
            _require_public_text(gap, "surface", f"{described} coverage gap")
            _require_choice(gap, "resolution", P4_GAP_RESOLUTIONS, f"{described} coverage gap")
            _require_public_list(gap, "evidence_ids", f"{described} coverage gap", labels=True)
            gaps.append(gap)
        prior = _require_mapping(record.get("prior"), f"{described} prior")
        _require_exact_fields(prior, P4_PRIOR_FIELDS, f"{described} prior")
        _require_optional_id(prior, "predecessor_review_run_id", "review_run", f"{described} prior")
        _require_optional_digest(prior, "predecessor_adjudication_digest", f"{described} prior")
        _require_optional_id(prior, "repair_batch_id", "review_repair_batch", f"{described} prior")
        _require_optional_digest(prior, "repair_result_digest", f"{described} prior")
        linked = [prior[key] is None for key in P4_PRIOR_FIELDS]
        if any(linked) and not all(linked):
            raise ValidationError(
                f"{described} prior names some predecessor linkage and not all of it", code="review_record_invalid"
            )
        obligations = _require_mapping(record.get("obligations"), f"{described} obligations")
        _require_exact_fields(obligations, P4_OBLIGATION_FIELDS, f"{described} obligations")
        for key in P4_OBLIGATION_FIELDS[:-1]:
            _require_int(obligations, key, f"{described} obligations", minimum=0)
        _require_bool(obligations, "strategy_change_required", f"{described} obligations")
        outcome = _require_choice(record, "outcome", P4_ADJUDICATION_OUTCOMES, described)
        purpose = record.get("repair_purpose")
        change_class = record.get("strategy_change_class")
        if outcome == REPAIR_REQUIRED:
            _require_public_text(record, "repair_purpose", described)
        elif purpose is not None:
            raise ValidationError(f"{described} names a repair purpose and no repair follows", code="review_record_invalid")
        if change_class is not None:
            _require_choice(record, "strategy_change_class", P4_STRATEGY_CHANGE_CLASSES, described)
            if outcome != REPAIR_REQUIRED:
                raise ValidationError(f"{described} names a strategy-change class and no repair follows",
                                      code="review_record_invalid")
        generation = _require_int(record, "candidate_generation", described, minimum=1)
        if generation == 1 and not all(linked):
            raise ValidationError(
                f"{described} is candidate generation 1 and names a predecessor", code="review_record_invalid"
            )
        if generation > 1 and any(linked):
            raise ValidationError(
                f"{described} is candidate generation {generation} and names no predecessor", code="review_record_invalid"
            )
        return P4Adjudication(
            review_run_id=_require_id(record, "review_run_id", "review_run", described),
            review_kind=_require_text(record, "review_kind", described),
            target_identity=_require_text(record, "target_identity", described),
            operation_identity=_require_text(record, "operation_identity", described),
            candidate_hash=_require_digest(record, "candidate_hash", described),
            candidate_generation=generation,
            review_context_hash=_require_digest(record, "review_context_hash", described),
            effective_policy_hash=_require_digest(record, "effective_policy_hash", described),
            review_contract=_require_choice(record, "review_contract", P4_CONTRACTS, described),
            adjudication_contract=_require_text(record, "adjudication_contract", described),
            instruction=_require_text(record, "instruction", described),
            task_id=_require_id(record, "task_id", "review_task", described),
            adjudicator_identity=_require_text(record, "adjudicator_identity", described),
            adjudicator_version=_require_text(record, "adjudicator_version", described),
            reports=tuple(reports),
            objective_holds=_require_bool(record, "objective_holds", described),
            entries=tuple(entries),
            findings=tuple(findings),
            coverage_gaps=tuple(gaps),
            prior=dict(prior),
            outcome=outcome,
            obligations=dict(obligations),
            repair_purpose=None if purpose is None else str(purpose),
            strategy_change_class=None if change_class is None else str(change_class),
        )


# --------------------------------------------------------------------------- P4 repair batch

P4_REPAIR_BATCH_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "repair_batch_id",
    "review_kind",
    "target_identity",
    "operation_identity",
    "review_contract",
    "source_review_run_id",
    "source_candidate_hash",
    "candidate_generation",
    "adjudication_digest",
    "finding_ids",
    "deliberate_low_finding_ids",
    "semantic_surfaces",
    "repair_purpose",
    "strategy",
    "strategy_change_required",
    "strategy_change_class",
    "allowed_result_surface",
    "prior_relations",
)
P4_PRIOR_RELATION_FIELDS = ("finding_id", "relation", "linked_finding_ids", "linked_repair_batch_ids")


@dataclass(frozen=True)
class P4RepairBatch:
    """The one immutable Repair Batch of one Candidate generation (§12.8 / §27.14)."""

    repair_batch_id: str
    review_kind: str
    target_identity: str
    operation_identity: str
    review_contract: str
    source_review_run_id: str
    source_candidate_hash: str
    candidate_generation: int
    adjudication_digest: str
    finding_ids: tuple[str, ...]
    deliberate_low_finding_ids: tuple[str, ...]
    semantic_surfaces: tuple[str, ...]
    repair_purpose: str
    strategy: str
    strategy_change_required: bool
    strategy_change_class: str | None
    allowed_result_surface: tuple[str, ...]
    prior_relations: tuple[dict[str, Any], ...]

    def to_record(self) -> dict[str, Any]:
        record = _header(SCHEMA_P4_REPAIR_BATCH)
        record.update(
            {
                "repair_batch_id": self.repair_batch_id,
                "review_kind": self.review_kind,
                "target_identity": self.target_identity,
                "operation_identity": self.operation_identity,
                "review_contract": self.review_contract,
                "source_review_run_id": self.source_review_run_id,
                "source_candidate_hash": self.source_candidate_hash,
                "candidate_generation": self.candidate_generation,
                "adjudication_digest": self.adjudication_digest,
                "finding_ids": list(self.finding_ids),
                "deliberate_low_finding_ids": list(self.deliberate_low_finding_ids),
                "semantic_surfaces": list(self.semantic_surfaces),
                "repair_purpose": self.repair_purpose,
                "strategy": self.strategy,
                "strategy_change_required": self.strategy_change_required,
                "strategy_change_class": self.strategy_change_class,
                "allowed_result_surface": list(self.allowed_result_surface),
                "prior_relations": [dict(item) for item in self.prior_relations],
            }
        )
        return record

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "P4RepairBatch":
        serialize.require_schema(record, SCHEMA_P4_REPAIR_BATCH, VERSION, described)
        _require_exact_fields(record, P4_REPAIR_BATCH_FIELDS, described)
        finding_ids = _require_ids(record, "finding_ids", "review_finding", described)
        if not finding_ids:
            raise ValidationError(f"{described} names no Finding to repair", code="review_record_invalid")
        deliberate = _require_ids(record, "deliberate_low_finding_ids", "review_finding", described)
        if not set(deliberate) <= set(finding_ids):
            raise ValidationError(
                f"{described} names a deliberate LOW Finding it does not repair", code="review_record_invalid"
            )
        surfaces = _require_public_list(record, "semantic_surfaces", described, labels=True)
        _require_sorted_unique(surfaces, "semantic_surfaces", described)
        if not surfaces:
            raise ValidationError(f"{described} names no semantic surface", code="review_record_invalid")
        allowed = _require_public_list(record, "allowed_result_surface", described)
        _require_sorted_unique(allowed, "allowed_result_surface", described)
        if not allowed:
            raise ValidationError(f"{described} allows no result surface", code="review_record_invalid")
        strategy = _require_choice(record, "strategy", P4_STRATEGIES, described)
        required = _require_bool(record, "strategy_change_required", described)
        change_class = record.get("strategy_change_class")
        if strategy == STRATEGY_CHANGE:
            _require_choice(record, "strategy_change_class", P4_STRATEGY_CHANGE_CLASSES, described)
        elif change_class is not None:
            raise ValidationError(
                f"{described} is an ordinary strategy and names a strategy-change class", code="review_record_invalid"
            )
        if required and strategy != STRATEGY_CHANGE:
            raise ValidationError(
                f"{described} requires STRATEGY_CHANGE and selects an ordinary unchanged strategy",
                code="review_record_invalid",
            )
        relations: list[dict[str, Any]] = []
        for item in _require_list(record, "prior_relations", described):
            relation = _require_mapping(item, f"{described} prior relation")
            _require_exact_fields(relation, P4_PRIOR_RELATION_FIELDS, f"{described} prior relation")
            _require_id(relation, "finding_id", "review_finding", f"{described} prior relation")
            _require_choice(relation, "relation", P4_RELATIONS, f"{described} prior relation")
            _require_ids(relation, "linked_finding_ids", "review_finding", f"{described} prior relation")
            _require_ids(relation, "linked_repair_batch_ids", "review_repair_batch", f"{described} prior relation")
            relations.append(relation)
        if [item["finding_id"] for item in relations] != finding_ids:
            raise ValidationError(
                f"{described} prior relations do not name exactly its Findings, in order", code="review_record_invalid"
            )
        return P4RepairBatch(
            repair_batch_id=_require_id(record, "repair_batch_id", "review_repair_batch", described),
            review_kind=_require_text(record, "review_kind", described),
            target_identity=_require_text(record, "target_identity", described),
            operation_identity=_require_text(record, "operation_identity", described),
            review_contract=_require_choice(record, "review_contract", P4_REPAIR_CONTRACTS, described),
            source_review_run_id=_require_id(record, "source_review_run_id", "review_run", described),
            source_candidate_hash=_require_digest(record, "source_candidate_hash", described),
            candidate_generation=_require_int(record, "candidate_generation", described, minimum=1),
            adjudication_digest=_require_digest(record, "adjudication_digest", described),
            finding_ids=tuple(finding_ids),
            deliberate_low_finding_ids=tuple(deliberate),
            semantic_surfaces=tuple(surfaces),
            repair_purpose=_require_public_text(record, "repair_purpose", described),
            strategy=strategy,
            strategy_change_required=required,
            strategy_change_class=None if change_class is None else str(change_class),
            allowed_result_surface=tuple(allowed),
            prior_relations=tuple(relations),
        )


# --------------------------------------------------------------------------- P4 repair result

P4_REPAIR_RESULT_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "repair_batch_id",
    "review_kind",
    "target_identity",
    "operation_identity",
    "review_contract",
    "source_review_run_id",
    "source_candidate_hash",
    "source_candidate_generation",
    "result_candidate_hash",
    "result_candidate_generation",
    "result_candidate_material_digest",
    "repair_task_id",
    "repair_identity",
    "repair_version",
    "repaired_surface",
    "impact_class",
    "coverage_check",
    "coverage_check_digest",
    "evidence_decisions",
    "reverification",
    "reverification_digest",
    "causal_summary",
    "successor_eligible",
)
P4_COVERAGE_CHECK_FIELDS = (
    "semantic_behavior_changed",
    "semantic_responsibility",
    "other_sites",
    "shared_responsibility",
    "enumerable",
    "affected_set",
    "covers_affected_set",
    "repair_scope",
    "unresolved_gap",
)
P4_EVIDENCE_DECISION_FIELDS = ("evidence_id", "reusable", "state", "reasons")
P4_REVERIFICATION_FIELDS = ("required", "completed", "residual")


@dataclass(frozen=True)
class P4RepairResult:
    """The immutable result of one successful repair (§12.10 / §27.20), named by its Repair Batch.

    Candidate N+1 is a complete Candidate stored as its own Candidate
    snapshot; this record links it to the source Candidate, Run and batch and
    carries the coverage, Evidence and reverification decisions the successor
    Run's convergence reads. It is written only for a repair that settled
    successfully and is eligible to start a successor Run.
    """

    repair_batch_id: str
    review_kind: str
    target_identity: str
    operation_identity: str
    review_contract: str
    source_review_run_id: str
    source_candidate_hash: str
    source_candidate_generation: int
    result_candidate_hash: str
    result_candidate_generation: int
    result_candidate_material_digest: str
    repair_task_id: str
    repair_identity: str
    repair_version: str
    repaired_surface: tuple[str, ...]
    impact_class: str
    coverage_check: dict[str, Any]
    coverage_check_digest: str
    evidence_decisions: tuple[dict[str, Any], ...]
    reverification: dict[str, Any]
    reverification_digest: str
    causal_summary: str
    successor_eligible: bool

    def to_record(self) -> dict[str, Any]:
        record = _header(SCHEMA_P4_REPAIR_RESULT)
        record.update(
            {
                "repair_batch_id": self.repair_batch_id,
                "review_kind": self.review_kind,
                "target_identity": self.target_identity,
                "operation_identity": self.operation_identity,
                "review_contract": self.review_contract,
                "source_review_run_id": self.source_review_run_id,
                "source_candidate_hash": self.source_candidate_hash,
                "source_candidate_generation": self.source_candidate_generation,
                "result_candidate_hash": self.result_candidate_hash,
                "result_candidate_generation": self.result_candidate_generation,
                "result_candidate_material_digest": self.result_candidate_material_digest,
                "repair_task_id": self.repair_task_id,
                "repair_identity": self.repair_identity,
                "repair_version": self.repair_version,
                "repaired_surface": list(self.repaired_surface),
                "impact_class": self.impact_class,
                "coverage_check": {
                    **dict(self.coverage_check),
                    "other_sites": list(self.coverage_check["other_sites"]),
                    "affected_set": list(self.coverage_check["affected_set"]),
                },
                "coverage_check_digest": self.coverage_check_digest,
                "evidence_decisions": [
                    {**dict(item), "reasons": list(item["reasons"])} for item in self.evidence_decisions
                ],
                "reverification": {
                    "required": list(self.reverification["required"]),
                    "completed": [dict(item) for item in self.reverification["completed"]],
                    "residual": self.reverification["residual"],
                },
                "reverification_digest": self.reverification_digest,
                "causal_summary": self.causal_summary,
                "successor_eligible": self.successor_eligible,
            }
        )
        return record

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "P4RepairResult":
        serialize.require_schema(record, SCHEMA_P4_REPAIR_RESULT, VERSION, described)
        _require_exact_fields(record, P4_REPAIR_RESULT_FIELDS, described)
        source_generation = _require_int(record, "source_candidate_generation", described, minimum=1)
        result_generation = _require_int(record, "result_candidate_generation", described, minimum=2)
        if result_generation != source_generation + 1:
            raise ValidationError(
                f"{described} result_candidate_generation {result_generation} is not source generation "
                f"{source_generation} + 1",
                code="review_record_invalid",
            )
        source_hash = _require_digest(record, "source_candidate_hash", described)
        result_hash = _require_digest(record, "result_candidate_hash", described)
        if source_hash == result_hash:
            raise ValidationError(
                f"{described} names the source Candidate as its result; a repaired Candidate is a new one",
                code="review_record_invalid",
            )
        repaired = _require_public_list(record, "repaired_surface", described)
        _require_sorted_unique(repaired, "repaired_surface", described)
        if not repaired:
            raise ValidationError(f"{described} names no repaired surface", code="review_record_invalid")
        check = _require_mapping(record.get("coverage_check"), f"{described} coverage_check")
        where = f"{described} coverage_check"
        _require_exact_fields(check, P4_COVERAGE_CHECK_FIELDS, where)
        _require_public_text(check, "semantic_behavior_changed", where)
        _require_label(check, "semantic_responsibility", where)
        _require_public_list(check, "other_sites", where)
        for key in ("shared_responsibility", "enumerable", "covers_affected_set"):
            _require_bool(check, key, where)
        _require_public_list(check, "affected_set", where)
        _require_choice(check, "repair_scope", P4_REPAIR_SCOPES, where)
        if check.get("unresolved_gap") is not None:
            _require_public_text(check, "unresolved_gap", where)
        check_digest = _require_digest(record, "coverage_check_digest", described)
        if serialize.digest(dict(check)) != check_digest:
            raise ValidationError(f"{described} coverage_check_digest is not its check's digest", code="review_record_invalid")
        decisions: list[dict[str, Any]] = []
        for item in _require_list(record, "evidence_decisions", described):
            decision = _require_mapping(item, f"{described} evidence decision")
            _require_exact_fields(decision, P4_EVIDENCE_DECISION_FIELDS, f"{described} evidence decision")
            _require_label(decision, "evidence_id", f"{described} evidence decision")
            reusable = _require_bool(decision, "reusable", f"{described} evidence decision")
            state = _require_choice(decision, "state", P4_REUSE_STATES, f"{described} evidence decision")
            if reusable != (state == "reusable"):
                raise ValidationError(
                    f"{described} evidence decision says reusable {reusable} with state {state}",
                    code="review_record_invalid",
                )
            _require_public_list(decision, "reasons", f"{described} evidence decision")
            decisions.append(decision)
        if len({item["evidence_id"] for item in decisions}) != len(decisions):
            raise ValidationError(f"{described} decides one Evidence twice", code="review_record_invalid")
        reverification = _require_mapping(record.get("reverification"), f"{described} reverification")
        where = f"{described} reverification"
        _require_exact_fields(reverification, P4_REVERIFICATION_FIELDS, where)
        required = _require_public_list(reverification, "required", where, labels=True)
        _require_sorted_unique(required, "required", where)
        completed = []
        for item in _require_list(reverification, "completed", where):
            done = _require_mapping(item, f"{where} completed")
            _require_exact_fields(done, ("id", "result"), f"{where} completed")
            _require_label(done, "id", f"{where} completed")
            _require_choice(done, "result", P4_VERIFICATION_RESULTS, f"{where} completed")
            completed.append(done)
        if [item["id"] for item in completed] != sorted({item["id"] for item in completed}):
            raise ValidationError(f"{where} completed is not sorted and duplicate-free", code="review_record_invalid")
        residual = _require_int(reverification, "residual", where, minimum=0)
        passed = {item["id"] for item in completed if item["result"] == "pass"}
        if residual != len(set(required) - passed):
            raise ValidationError(
                f"{where} residual {residual} is not the count of required verification not passed",
                code="review_record_invalid",
            )
        reverification_digest = _require_digest(record, "reverification_digest", described)
        if serialize.digest(dict(reverification)) != reverification_digest:
            raise ValidationError(
                f"{described} reverification_digest is not its reverification's digest", code="review_record_invalid"
            )
        return P4RepairResult(
            repair_batch_id=_require_id(record, "repair_batch_id", "review_repair_batch", described),
            review_kind=_require_text(record, "review_kind", described),
            target_identity=_require_text(record, "target_identity", described),
            operation_identity=_require_text(record, "operation_identity", described),
            review_contract=_require_choice(record, "review_contract", P4_REPAIR_CONTRACTS, described),
            source_review_run_id=_require_id(record, "source_review_run_id", "review_run", described),
            source_candidate_hash=source_hash,
            source_candidate_generation=source_generation,
            result_candidate_hash=result_hash,
            result_candidate_generation=result_generation,
            result_candidate_material_digest=_require_digest(record, "result_candidate_material_digest", described),
            repair_task_id=_require_id(record, "repair_task_id", "review_task", described),
            repair_identity=_require_text(record, "repair_identity", described),
            repair_version=_require_text(record, "repair_version", described),
            repaired_surface=tuple(repaired),
            impact_class=_require_choice(record, "impact_class", P4_IMPACT_CLASSES, described),
            coverage_check=dict(check),
            coverage_check_digest=check_digest,
            evidence_decisions=tuple(decisions),
            reverification=dict(reverification),
            reverification_digest=reverification_digest,
            causal_summary=_require_public_text(record, "causal_summary", described),
            successor_eligible=_require_bool(record, "successor_eligible", described),
        )
