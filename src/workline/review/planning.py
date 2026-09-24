"""Planning Review (P2): the review-v1 identities, records and reviewer contract of RoadmapPlan and PhaseEntryDesign.

Review-owned, and inert: this module reads, validates and renders. It holds no
lock, opens no mutation, writes no file and decides nothing about whether a
planning operation proceeds - the Roadmap operation owns that
(``workline.roadmap_review``). What it fixes is the meaning of what a planning
Review Run records (``skills/review``):

```text
identities        the two planning kinds, their slots, stages, keys and contract strings
Candidate         review-planning-candidate: the reviewed artifact and its declared base
Context           review-planning-context: loader identity, authority digests, Git semantics
Policy            review-planning-policy: one static record for both kinds
request envelope  review-planning-request: what the reviewer is asked, set-aside Runs included
report            review-planning-report: what a reviewer returned, and its result digest
adjudication      mechanical: the reviewer's severity is final, HIGH and MID block
```

Every record is canonical data under the P1 serializer, so each digest is a
statement about the canonical bytes a reader reproduces.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from ..errors import StopError, ValidationError
from . import records, serialize

# --------------------------------------------------------------------------- static contract identifiers

PLANNING_CONTRACT = "review-v1-planning-v1"
PUBLICATION_CONTRACT = "review-v1-planning-publication-v1"
GIT_PERSISTENCE = "review-v1-planning-local-v1"
PERSISTED_RESULT_CONTRACT = "review-v1-planning-persisted-result-v1"
PROOF_CONTRACT = "review-v1-planning-proof-v1"
POLICY_ID = "review-v1-planning-policy-v1"
ADJUDICATION_RULE = "review-v1-planning-adjudication-v1"
INSTRUCTION = "review-v1-planning-instruction-v1"
CHECKOUT_CONTRACT = "review-v1-planning-checkout-v1"
COMMITTED_PROOF_CONTRACT = "review-v1-planning-committed-proof-v1"
TASK_KIND = "planning-review-v1"

KIND_ROADMAP = "roadmap-plan-v1"
KIND_PHASE_ENTRY = "phase-entry-design-v1"
PLANNING_KINDS = (KIND_ROADMAP, KIND_PHASE_ENTRY)

OPERATION_ROADMAP = "roadmap-create"
OPERATION_PHASE_ENTRY = "phase-entry"
OPERATION_GENERATION = "review-generation"

#: The invocation keys a planning mutation carries beside its live invocation (``skills/roadmap``).
MARKER_REVIEW = "review_contract"
MARKER_PUBLICATION = "publication_contract"
MARKER_RECOVERY = "recovery_of_review_run_id"

SCHEMA_REQUEST_IDENTITY = "review-planning-request-identity"
SCHEMA_CANDIDATE = "review-planning-candidate"
SCHEMA_CONTEXT = "review-planning-context"
SCHEMA_IMPLEMENTATION = "review-planning-implementation"
SCHEMA_POLICY = "review-planning-policy"
SCHEMA_REQUEST = "review-planning-request"
SCHEMA_REPORT = "review-planning-report"
SCHEMA_ADJUDICATION = "review-planning-adjudication"
SCHEMA_OBLIGATIONS = "review-planning-obligations"
SCHEMA_COVERAGE = "review-planning-coverage"
SCHEMA_REPORT_SET = "review-planning-report-set"
SCHEMA_EVIDENCE = "review-planning-evidence"
SCHEMA_INVALIDATION_EVIDENCE = "review-planning-invalidation-evidence"
SCHEMA_DELTA = "review-planning-delta"

RECORD_VERSION = 1

#: The generation of a planning Run that seals, and the only one that issues a Receipt.
SEAL_GENERATION = 3
#: The last generation a planning Run ever has: an invalidation, status ``open``.
INVALIDATION_GENERATION = 4

#: The stale reasons of the currency order (``skills/roadmap``): never exceptions, always a result's detail.
STALE_CONTEXT = "review_context_changed"
STALE_POLICY = "review_policy_changed"
STALE_DECLARED_BASE = "review_declared_base_changed"
STALE_REASONS = (STALE_CONTEXT, STALE_POLICY, STALE_DECLARED_BASE)

#: Why recovery discovery set a matching Run aside (the request envelope's ``set_aside_runs``).
SET_ASIDE_INVALIDATED = "invalidated"
SET_ASIDE_CONSUMED = "consumed"
SET_ASIDE_NOT_AUTHORIZED = "not_authorized"
SET_ASIDE_SET_ASIDE = "set_aside"
SET_ASIDE_REASONS = (
    SET_ASIDE_INVALIDATED, SET_ASIDE_CONSUMED, SET_ASIDE_NOT_AUTHORIZED, SET_ASIDE_SET_ASIDE,
) + STALE_REASONS


@dataclass(frozen=True)
class PlanningKind:
    """The identities one planning kind carries (``skills/review``: planning kinds)."""

    review_kind: str
    operation: str
    authorized_operation_stage: str
    task_slot: str
    projection_semantics_version: str
    adapter_identity: str


KINDS: dict[str, PlanningKind] = {
    KIND_ROADMAP: PlanningKind(
        KIND_ROADMAP, OPERATION_ROADMAP, "roadmap-create:registration", "roadmap-plan-reviewer",
        "roadmap-plan-projection-v1", "roadmap-plan-adapter-v1",
    ),
    KIND_PHASE_ENTRY: PlanningKind(
        KIND_PHASE_ENTRY, OPERATION_PHASE_ENTRY, "phase-entry:registration", "phase-entry-design-reviewer",
        "phase-entry-design-projection-v1", "phase-entry-design-adapter-v1",
    ),
}


def kind(review_kind: str) -> PlanningKind:
    found = KINDS.get(review_kind)
    if found is None:
        raise ValidationError(f"not a planning Review kind: {review_kind!r}", code="review_record_invalid")
    return found


def kind_of_operation(operation: str) -> PlanningKind:
    for found in KINDS.values():
        if found.operation == operation:
            return found
    raise ValidationError(f"not a planning operation: {operation!r}", code="review_record_invalid")


# --------------------------------------------------------------------------- the opt-in and the reviewer interface

@dataclass(frozen=True)
class PlanningReviewFinding:
    severity: str  # HIGH | MID | LOW
    code: str      # non-empty, stripped, no line break
    message: str


@dataclass(frozen=True)
class PlanningReviewReport:
    task_id: str
    reviewer_identity: str
    reviewer_version: str
    status: str  # completed | declined
    findings: tuple[PlanningReviewFinding, ...] = ()


@dataclass(frozen=True)
class PlanningReviewTask:
    task_id: str
    task_slot: str
    task_kind: str
    review_kind: str
    request_envelope: dict[str, Any]
    request_digest: str
    candidate_hash: str
    review_context_hash: str
    effective_policy_hash: str


@dataclass(frozen=True)
class PlanningReview:
    """The per-invocation opt-in: ``create_roadmap(..., review=PlanningReview(...))``.

    A versioned contract string, not a flag: it is recorded verbatim in the
    durable invocation, selects the publication contract, and a future
    planning contract is a new string this build refuses.
    """

    reviewer: Callable[[PlanningReviewTask], PlanningReviewReport]
    reviewer_identity: str
    reviewer_version: str
    contract: str = PLANNING_CONTRACT


def _single_line_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip() and value.splitlines() == [value]


def _persistable_reviewer_text(value: object) -> bool:
    """Whether ``value`` is reviewer identity or version text a Review record can carry.

    The single-line shape, and then representability, because these two values
    are not diagnostics: generation 1 makes them durable in the TaskInput and
    in the accepted descriptor, and ``task_input_digest`` is taken over their
    canonical bytes. Neither is in the request identity nor in the Candidate,
    so no canonical-input preflight reaches them, and without this rule the
    first encode would be :func:`accepted_descriptor` - after the lock, after
    the planning mutation and after its reservations.

    Both serializer calls are needed, and only together: ``canonical_bytes``
    says the value can be written at all, and ``canonical_roundtrips``, which
    compares parsed data and never encodes, says a reader gets it back. A
    representability failure is ``False`` here, so the refusal stays the one
    the caller's contract names and no serializer exception escapes.

    Only ``_single_line_text`` is shared with the finding code of a report
    (:func:`report_record`); this rule is not, because a report's own
    representability is already proven where the report is canonicalized.
    """
    if not _single_line_text(value):
        return False
    holder = {"reviewer_text": value}
    try:
        serialize.canonical_bytes(holder)
        return serialize.canonical_roundtrips(holder)
    except (ValidationError, ValueError, UnicodeError):
        return False


def validate_planning_review(review: object) -> PlanningReview:
    """The ``review`` argument, validated before the lock and before any Project state is read."""
    problems: list[str] = []
    if type(review) is not PlanningReview:
        raise ValidationError(
            f"review must be a PlanningReview, not {type(review).__name__}", code="review_contract_invalid"
        )
    if review.contract != PLANNING_CONTRACT:
        problems.append(f"contract {review.contract!r} is not {PLANNING_CONTRACT!r}")
    if not callable(review.reviewer):
        problems.append("reviewer is not callable")
    for name in ("reviewer_identity", "reviewer_version"):
        value = getattr(review, name)
        if _persistable_reviewer_text(value):
            continue
        problems.append(
            f"{name} must be non-empty single-line text without surrounding whitespace"
            if not _single_line_text(value)
            else f"{name} is text the canonical Review form cannot carry, so the accepted task could not record it"
        )
    if problems:
        raise ValidationError("invalid PlanningReview: " + "; ".join(problems), code="review_contract_invalid")
    return review


def invocation_markers() -> dict[str, str]:
    """The two keys a review-v1 planning invocation carries beside the live invocation."""
    return {MARKER_REVIEW: PLANNING_CONTRACT, MARKER_PUBLICATION: PUBLICATION_CONTRACT}


# --------------------------------------------------------------------------- operation identity

def request_identity_record(operation: str, request: dict[str, Any], phase_id: str | None = None) -> dict[str, Any]:
    if operation == OPERATION_ROADMAP:
        return {
            serialize.SCHEMA_KEY: SCHEMA_REQUEST_IDENTITY, serialize.VERSION_KEY: RECORD_VERSION,
            "operation": operation, "request": request,
        }
    return {
        serialize.SCHEMA_KEY: SCHEMA_REQUEST_IDENTITY, serialize.VERSION_KEY: RECORD_VERSION,
        "operation": operation, "phase_id": phase_id, "design": request,
    }


def request_digest(operation: str, request: dict[str, Any], phase_id: str | None = None) -> str:
    """``serialize.digest`` of the request identity record: the exact request or design semantics."""
    return serialize.digest(request_identity_record(operation, request, phase_id))


def operation_identity(operation: str, digest: str) -> str:
    return f"{operation}:{digest}"


def request_digest_of(operation_identity_value: str) -> str:
    """The digest part of an ``operation_identity``."""
    _, _, digest = operation_identity_value.partition(":")
    return digest


# --------------------------------------------------------------------------- Candidate

def candidate_record(review_kind: str, content: dict[str, Any], declared_base: dict[str, Any]) -> dict[str, Any]:
    """The canonical Candidate record: the reviewed artifact projection and the declared base."""
    found = kind(review_kind)
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_CANDIDATE,
        serialize.VERSION_KEY: RECORD_VERSION,
        "review_kind": review_kind,
        "projection": {
            "projection_kind": "reviewed_artifact",
            "semantics_version": found.projection_semantics_version,
            "content": content,
        },
        "declared_base": declared_base,
    })


def candidate_hash(candidate: dict[str, Any]) -> str:
    return serialize.digest(candidate)


def candidate_content(candidate: dict[str, Any]) -> dict[str, Any]:
    return candidate["projection"]["content"]


def snapshot_for(candidate: dict[str, Any]) -> records.CandidateSnapshot:
    """The P1 Candidate snapshot (snapshot mode) that carries ``candidate`` as its material."""
    return records.CandidateSnapshot(
        candidate_hash=candidate_hash(candidate),
        reconstruction_mode=records.RECONSTRUCTION_SNAPSHOT,
        projection_semantics_version=kind(candidate["review_kind"]).projection_semantics_version,
        material=candidate,
        builder=None,
    )


def require_planning_candidate(material: object, described: str) -> dict[str, Any]:
    """``material`` as a planning Candidate record of a planning kind, or a STOP naming ``described``."""
    if not isinstance(material, dict) or material.get(serialize.SCHEMA_KEY) != SCHEMA_CANDIDATE:
        raise ValidationError(f"{described} is not a planning Candidate", code="review_record_invalid")
    if material.get(serialize.VERSION_KEY) != RECORD_VERSION:
        raise ValidationError(f"{described} is not a version {RECORD_VERSION} planning Candidate", code="review_record_version")
    if set(material) != {serialize.SCHEMA_KEY, serialize.VERSION_KEY, "review_kind", "projection", "declared_base"}:
        raise ValidationError(f"{described} does not hold exactly the planning Candidate fields", code="review_record_invalid")
    review_kind = material.get("review_kind")
    if review_kind not in PLANNING_KINDS:
        raise ValidationError(f"{described} names no planning kind: {review_kind!r}", code="review_record_invalid")
    projection = material.get("projection")
    if (
        not isinstance(projection, dict)
        or set(projection) != {"projection_kind", "semantics_version", "content"}
        or projection.get("projection_kind") != "reviewed_artifact"
        or projection.get("semantics_version") != KINDS[review_kind].projection_semantics_version
        or not isinstance(projection.get("content"), dict)
        or not isinstance(material.get("declared_base"), dict)
    ):
        raise ValidationError(f"{described} does not carry a planning projection", code="review_record_invalid")
    return material


def is_planning_candidate(material: object) -> bool:
    """Whether a snapshot's material says it is a planning Candidate at all (``schema``)."""
    return isinstance(material, dict) and material.get(serialize.SCHEMA_KEY) == SCHEMA_CANDIDATE


# --------------------------------------------------------------------------- Context

AUTHORITY_IDS = ("registry", "skills/roadmap", "skills/phase-create", "skills/create", "skills/review")


def _context_unavailable(message: str) -> StopError:
    return StopError(f"the review Context cannot be computed: {message}", code="review_context_unavailable")


def _read_authority(path: Path) -> bytes:
    """The bytes of one authority file. Separate so that what the Context reads is one call."""
    return Path(path).read_bytes()


def _lf_digest(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def authority_digests(workline_root: Path) -> list[dict[str, str]]:
    """``registry.md`` and the five planning Skills, each as the SHA-256 of its bytes with CRLF read as LF."""
    from ..registry import resolve_skill

    found: list[dict[str, str]] = []
    for authority_id in AUTHORITY_IDS:
        try:
            if authority_id == "registry":
                path = Path(workline_root) / "registry.md"
            else:
                path = resolve_skill(Path(workline_root), authority_id).path
            data = _read_authority(path)
        except (OSError, StopError) as exc:
            raise _context_unavailable(f"{authority_id} cannot be resolved or read: {exc}") from exc
        found.append({"id": authority_id, "digest": _lf_digest(data)})
    return found


def loader_identity(package_directory: Path) -> str:
    """The content identity of the running implementation: every ``*.py`` under the package, CRLF read as LF."""
    directory = Path(package_directory)
    if not directory.is_dir():
        raise _context_unavailable(f"the implementation package {directory} is not a directory")
    files: list[dict[str, str]] = []
    try:
        for path in directory.rglob("*.py"):
            relative = PurePosixPath(directory.name) / PurePosixPath(path.relative_to(directory).as_posix())
            files.append({"path": str(relative), "digest": _lf_digest(path.read_bytes())})
    except OSError as exc:
        raise _context_unavailable(f"the implementation package cannot be read: {exc}") from exc
    files.sort(key=lambda item: item["path"])
    return serialize.digest({
        serialize.SCHEMA_KEY: SCHEMA_IMPLEMENTATION, serialize.VERSION_KEY: RECORD_VERSION, "files": files,
    })


def context_record(workline_root: Path, review_kind: str) -> dict[str, Any]:
    """The review Context of ``review_kind``, recomputed now; ``review_context_unavailable`` when it cannot be."""
    from ..implementation import package_directory

    found = kind(review_kind)
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_CONTEXT,
        serialize.VERSION_KEY: RECORD_VERSION,
        "review_kind": review_kind,
        "contract": PLANNING_CONTRACT,
        "projection_semantics_version": found.projection_semantics_version,
        "adapter_identity": found.adapter_identity,
        "loader_identity": loader_identity(package_directory(workline_root)),
        "authority": authority_digests(workline_root),
        "git_persistence": GIT_PERSISTENCE,
        "checkout_capability": CHECKOUT_CONTRACT,
    })


# --------------------------------------------------------------------------- Policy

#: The one static Effective Policy of P2, identical for both kinds. ``skills/review`` declares it verbatim.
POLICY_RECORD: dict[str, Any] = {
    serialize.SCHEMA_KEY: SCHEMA_POLICY,
    serialize.VERSION_KEY: RECORD_VERSION,
    "policy_id": POLICY_ID,
    "slots": [
        {"review_kind": KIND_ROADMAP, "task_slot": "roadmap-plan-reviewer", "task_kind": TASK_KIND, "required": True},
        {"review_kind": KIND_PHASE_ENTRY, "task_slot": "phase-entry-design-reviewer", "task_kind": TASK_KIND, "required": True},
    ],
    "reviewer_identity_rule": "caller-declared identity and version, bound at acceptance; a settlement is accepted only from them",
    "report_statuses": ["completed", "declined"],
    "severities": ["HIGH", "MID", "LOW"],
    "blocking_severities": ["HIGH", "MID"],
    "low_disposition": "recorded in the report digest, returned to the caller, non-blocking",
    "declined_disposition": "the task settles failed; the planning attempt is not authorized",
    "error_disposition": "no settlement; the same task is launched again by the next run",
    "timeout_disposition": "none imposed by Workline; a reviewer that gives up returns declined",
    "adjudication_rule": ADJUDICATION_RULE,
    "obligation_rule": "every HIGH or MID finding and every failed task is an unresolved obligation; P2 resolves none",
    "seal_rule": "every required task settled completed and zero unresolved obligations",
    "repair": "none; a not-authorized planning attempt is terminal",
    "instruction": INSTRUCTION,
}


def policy_record() -> dict[str, Any]:
    return serialize.canonical_data(POLICY_RECORD)


def policy_hash() -> str:
    return serialize.digest(policy_record())


def policy_named(policy_id: object) -> dict[str, Any] | None:
    """The static policy the running implementation provides under ``policy_id``; None when it provides none."""
    record = policy_record()
    return record if policy_id == record["policy_id"] else None


# --------------------------------------------------------------------------- request envelope, task input, descriptor

def request_envelope(
    review_kind: str, candidate: dict[str, Any], context: dict[str, Any], set_aside_runs: list[dict[str, str]]
) -> dict[str, Any]:
    kind(review_kind)
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_REQUEST,
        serialize.VERSION_KEY: RECORD_VERSION,
        "review_kind": review_kind,
        "policy_id": POLICY_ID,
        "instruction": INSTRUCTION,
        "candidate": candidate,
        "context": context,
        "set_aside_runs": sorted(
            ({"review_run_id": str(item["review_run_id"]), "reason": str(item["reason"])} for item in set_aside_runs),
            key=lambda item: item["review_run_id"],
        ),
    })


def task_input_for(
    *,
    task_id: str,
    review_kind: str,
    reviewer_identity: str,
    reviewer_version: str,
    envelope: dict[str, Any],
    candidate: dict[str, Any],
    review_context_hash: str,
    effective_policy_hash: str,
) -> records.TaskInput:
    snapshot = snapshot_for(candidate)
    return records.TaskInput(
        task_id=task_id,
        task_slot=kind(review_kind).task_slot,
        task_kind=TASK_KIND,
        reviewer_identity=reviewer_identity,
        reviewer_version=reviewer_version,
        request_envelope=envelope,
        request_digest=serialize.digest(envelope),
        candidate_hash=snapshot.candidate_hash,
        reconstruction_mode=records.RECONSTRUCTION_SNAPSHOT,
        candidate_material_digest=serialize.digest(snapshot.to_record()),
        review_context_hash=review_context_hash,
        effective_policy_hash=effective_policy_hash,
        accepted_generation=records.FIRST_GENERATION,
    )


def accepted_descriptor(task_input: records.TaskInput) -> dict[str, Any]:
    """The accepted task descriptor generation 1 carries: every P1 field, from the same sources as the task input."""
    return {
        "task_id": task_input.task_id,
        "task_slot": task_input.task_slot,
        "task_kind": task_input.task_kind,
        "reviewer_identity": task_input.reviewer_identity,
        "reviewer_version": task_input.reviewer_version,
        "candidate_hash": task_input.candidate_hash,
        "candidate_material_digest": task_input.candidate_material_digest,
        "reconstruction_mode": task_input.reconstruction_mode,
        "request_digest": task_input.request_digest,
        "task_input_digest": serialize.digest(task_input.to_record()),
        "review_context_hash": task_input.review_context_hash,
        "effective_policy_hash": task_input.effective_policy_hash,
    }


def task_from_input(task_input: records.TaskInput, review_kind: str) -> PlanningReviewTask:
    """The task object the reviewer receives, rebuilt from the stored TaskInput and never from memory."""
    return PlanningReviewTask(
        task_id=task_input.task_id,
        task_slot=task_input.task_slot,
        task_kind=task_input.task_kind,
        review_kind=review_kind,
        request_envelope=serialize.canonical_data(task_input.request_envelope),
        request_digest=task_input.request_digest,
        candidate_hash=task_input.candidate_hash,
        review_context_hash=task_input.review_context_hash,
        effective_policy_hash=task_input.effective_policy_hash,
    )


def task_input_problems(task_input: records.TaskInput, snapshot_material: dict[str, Any], run_candidate_hash: str,
                        run_context_hash: str, run_policy_hash: str) -> list[str]:
    """What the P1 provenance comparison does not cover and every planning launch and reconstruction checks."""
    problems: list[str] = []
    envelope = task_input.request_envelope
    if serialize.digest(envelope) != task_input.request_digest:
        problems.append("the task input's request_digest is not the digest of its request envelope")
    if envelope.get("candidate") != snapshot_material:
        problems.append("the request envelope's candidate is not the stored snapshot's material")
    if serialize.digest(snapshot_material) != run_candidate_hash:
        problems.append("the stored snapshot's material does not digest to the Run's candidate_hash")
    context = envelope.get("context")
    if not isinstance(context, dict) or serialize.digest(context) != run_context_hash:
        problems.append("the request envelope's context does not digest to the Run's review_context_hash")
    named = policy_named(envelope.get("policy_id"))
    if named is None or serialize.digest(named) != run_policy_hash:
        problems.append("the request envelope names no policy whose digest is the Run's effective_policy_hash")
    return problems


# --------------------------------------------------------------------------- reports

SEVERITIES = ("HIGH", "MID", "LOW")
BLOCKING = ("HIGH", "MID")
REPORT_STATUSES = ("completed", "declined")


def _report_invalid(message: str) -> StopError:
    return StopError(f"the reviewer's report is not valid: {message}; nothing is settled", code="review_report_invalid")


def report_record(report: object, descriptor: dict[str, Any]) -> dict[str, Any]:
    """The canonical report record of a reviewer's return, validated before anything is settled.

    ``review_report_invalid`` for anything that is not exactly a report for
    this task; ``review_reviewer_mismatch`` for a report from another reviewer
    identity or version than the one the task was accepted for.
    """
    if type(report) is not PlanningReviewReport:
        raise _report_invalid(f"the reviewer returned {type(report).__name__}, not a PlanningReviewReport")
    if report.task_id != descriptor["task_id"]:
        raise _report_invalid(f"it answers task {report.task_id!r}, not {descriptor['task_id']}")
    if report.status not in REPORT_STATUSES:
        raise _report_invalid(f"status {report.status!r} is not one of {', '.join(REPORT_STATUSES)}")
    if not isinstance(report.findings, tuple):
        raise _report_invalid("findings is not a tuple of PlanningReviewFinding")
    findings: list[dict[str, Any]] = []
    for finding in report.findings:
        if type(finding) is not PlanningReviewFinding:
            raise _report_invalid(f"a finding is {type(finding).__name__}, not a PlanningReviewFinding")
        if finding.severity not in SEVERITIES:
            raise _report_invalid(f"a finding has severity {finding.severity!r}")
        if not _single_line_text(finding.code):
            raise _report_invalid(f"a finding has code {finding.code!r}")
        if not isinstance(finding.message, str):
            raise _report_invalid("a finding's message is not text")
        findings.append({"severity": finding.severity, "code": finding.code, "message": finding.message})
    if not isinstance(report.reviewer_identity, str) or not isinstance(report.reviewer_version, str):
        raise _report_invalid("the reviewer identity and version are not text")
    if report.reviewer_identity != descriptor["reviewer_identity"] or report.reviewer_version != descriptor["reviewer_version"]:
        raise StopError(
            f"task {descriptor['task_id']} was accepted for reviewer {descriptor['reviewer_identity']} "
            f"{descriptor['reviewer_version']}, and the report comes from {report.reviewer_identity} "
            f"{report.reviewer_version}; nothing is settled",
            code="review_reviewer_mismatch",
        )
    record = {
        serialize.SCHEMA_KEY: SCHEMA_REPORT,
        serialize.VERSION_KEY: RECORD_VERSION,
        "task_id": report.task_id,
        "reviewer_identity": report.reviewer_identity,
        "reviewer_version": report.reviewer_version,
        "status": report.status,
        "findings": findings,
    }
    try:
        serialize.canonical_bytes(record)
        representable = serialize.canonical_roundtrips(record)
    except (ValidationError, ValueError, UnicodeError) as exc:
        raise _report_invalid(f"it cannot be recorded canonically: {exc}") from exc
    if not representable:
        raise _report_invalid("it does not read back as itself in canonical form")
    return serialize.canonical_data(record)


def findings_of(record: dict[str, Any]) -> tuple[PlanningReviewFinding, ...]:
    return tuple(
        PlanningReviewFinding(str(item["severity"]), str(item["code"]), str(item["message"]))
        for item in record.get("findings") or []
    )


def settled_status(record: dict[str, Any]) -> str:
    """How a report settles its task: ``declined`` settles ``failed``."""
    return records.TASK_SETTLED_OK if record["status"] == "completed" else records.TASK_SETTLED_FAILED


# --------------------------------------------------------------------------- adjudication and gate digests

def adjudication_record(settled: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    """``settled`` is ``[(settled task, report record)]``; empty before any settlement."""
    tasks = []
    for task, report in settled:
        severities = [finding["severity"] for finding in report.get("findings") or []]
        tasks.append({
            "task_id": task["task_id"], "status": task["status"], "result_digest": task["result_digest"],
            "high": severities.count("HIGH"), "mid": severities.count("MID"), "low": severities.count("LOW"),
        })
    return {
        serialize.SCHEMA_KEY: SCHEMA_ADJUDICATION, serialize.VERSION_KEY: RECORD_VERSION,
        "rule": ADJUDICATION_RULE, "tasks": tasks,
    }


def obligations_record(settled: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    """Every HIGH or MID finding, in report order, and every failed task: P2 resolves none."""
    obligations: list[dict[str, Any]] = []
    for task, report in settled:
        for finding in report.get("findings") or []:
            if finding["severity"] in BLOCKING:
                obligations.append({
                    "task_id": task["task_id"], "kind": "finding", "severity": finding["severity"],
                    "code": finding["code"], "message": finding["message"],
                })
        if task["status"] == records.TASK_SETTLED_FAILED:
            obligations.append({
                "task_id": task["task_id"], "kind": "task_failed", "severity": "FAILED",
                "code": "task_failed", "message": "",
            })
    return {serialize.SCHEMA_KEY: SCHEMA_OBLIGATIONS, serialize.VERSION_KEY: RECORD_VERSION, "obligations": obligations}


def coverage_record(required: list[tuple[str, str]], settled: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        serialize.SCHEMA_KEY: SCHEMA_COVERAGE, serialize.VERSION_KEY: RECORD_VERSION,
        "required": [{"task_slot": slot, "task_id": task_id} for slot, task_id in required],
        "settled": [{"task_id": task["task_id"], "status": task["status"]} for task in settled],
    }


def report_set_record(settled: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        serialize.SCHEMA_KEY: SCHEMA_REPORT_SET, serialize.VERSION_KEY: RECORD_VERSION,
        "reports": [{"task_id": task["task_id"], "result_digest": task["result_digest"]} for task in settled],
    }


EVIDENCE_CHECKS = (
    "structure-projection", "representability", "self-selection", "git-persistence-preflight",
    "checkout-capability", "review-namespace", "dirty-separability", "publication-barrier",
)


def evidence_record(canonical_first_work: str | None, *, phase_entry: bool, remote: bool) -> dict[str, Any]:
    """The freeze's evidence: every pre-Review check passed; self-selection and the barrier as they applied."""
    checks: list[dict[str, Any]] = []
    for check in EVIDENCE_CHECKS:
        if check == "self-selection":
            checks.append({
                "check": check, "result": "pass" if phase_entry else "not-applicable",
                "canonical_first_work": canonical_first_work if phase_entry else None,
            })
        elif check == "publication-barrier":
            checks.append({"check": check, "result": "pass" if remote else "not-applicable"})
        else:
            checks.append({"check": check, "result": "pass"})
    return {serialize.SCHEMA_KEY: SCHEMA_EVIDENCE, serialize.VERSION_KEY: RECORD_VERSION, "checks": checks}


def invalidation_evidence_record(superseded_receipt_id: str, reason: str) -> dict[str, Any]:
    return {
        serialize.SCHEMA_KEY: SCHEMA_INVALIDATION_EVIDENCE, serialize.VERSION_KEY: RECORD_VERSION,
        "superseded_receipt_id": superseded_receipt_id, "reason": reason,
    }


def empty_obligation_digest() -> str:
    return serialize.digest(obligations_record([]))


def authorizes(generation: records.GateGeneration) -> bool:
    """Whether a settled generation authorizes: every required task completed, and no unresolved obligation."""
    if not generation.settled_tasks or generation.unsettled_task_ids():
        return False
    if any(task["status"] != records.TASK_SETTLED_OK for task in generation.settled_tasks):
        return False
    return generation.obligation_digest == empty_obligation_digest()


# --------------------------------------------------------------------------- the registration delta record

def delta_record(parent: str, commit: str, entries: list[dict[str, str]]) -> dict[str, Any]:
    """The ``review-planning-delta`` record: E's entries, every scalar in its exact text form."""
    return {
        serialize.SCHEMA_KEY: SCHEMA_DELTA,
        serialize.VERSION_KEY: RECORD_VERSION,
        "parent": parent,
        "commit": commit,
        "entries": [
            {
                "path": entry["path"], "status": entry["status"],
                "old_mode": entry["old_mode"], "new_mode": entry["new_mode"],
                "old_blob": entry["old_blob"], "new_blob": entry["new_blob"],
            }
            for entry in sorted(entries, key=lambda item: item["path"].encode("utf-8", "surrogateescape"))
        ],
    }
