"""P5 (``WORKLINE_COMPLETION_SPRINT`` §13 / §28): the inert common core of durable Review history.

Inert, exactly as :mod:`workline.review.p4` is: no Project lock, no mutation, no
filesystem write, no Git and no lifecycle transition. History is a validated
projection/reference layer over the immutable P1-P4 records plus genuinely new
later facts (§13.1); it is never lifecycle truth, never a scheduler, never a
queue and never a Work generator. The operation owners write every history
record, in the same recoverable transition that makes its source fact durable;
nothing here decides when.

```text
identity     the common durable history contract (§28.2) and the record schemas
vocabulary   Run dispositions (§13.4), causal statuses (§13.7), relation types (§13.8)
records      Run / Finding / Repair summaries, durable causal material, relations,
             Human Decision Evidence (§28.7-§28.14) - strict, exact-field, immutable
H-3          structured, bounded, single-line public-safe text only (§28.15)
builders     every summary recomputed from its immutable source records
validation   history_problems: the cross-source checks of §28.17, a pure function
readiness    the versioned history gates of §28.18, dispatched by an explicit contract
RB5          the narrow validated reference projection of §28.21
```

The Control Plane rulings GAP-A ... GAP-G bind what §13 / §28 left open. This
module carries the identity constants GAP-A fixes (a per-Run stored P5-capable
Effective Policy identity and the history contract, inside the existing
P4-capable owner family - no owner marker), and no dispatch: which Run is
P5-capable is read by the owners from that Run's own stored identity. Nothing
here calls an owner, and :func:`history_problems` is wired into no gating
validator (GAP-B): a broken history record never changes lifecycle truth
(§28.17), and only a P5 owner's explicit :func:`require_history_ready` at a P5
boundary whose stored contract requires the history may refuse.

The codes and reasons this module builds are the P5 catalogue. Owners raise
them through :func:`stop` and :func:`reconcile`, so neither the P2 catalogue of
the P2 modules nor the P4 catalogue of :mod:`workline.review.p4` moves.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Collection, Iterable, Mapping, Sequence

from ..errors import ReconcileRequired, StopError, ValidationError
from ..ids import is_valid_id
from . import paths, records, serialize

# --------------------------------------------------------------------------- identities (§28.2, P-1)

#: The common durable history contract every P5 history record binds, and every P5-capable request
#: envelope binds under :data:`HISTORY_CONTRACT_KEY`. Distinct from every v1, P3 and P4 identity.
HISTORY_CONTRACT = "review-v1-history-v1"
#: The request-envelope key under which a P5-capable Run binds :data:`HISTORY_CONTRACT`. Whether a Run
#: binds it is decided by the owner's contract dispatch; a Run whose envelopes bind none is pre-P5.
HISTORY_CONTRACT_KEY = "history_contract"
#: The P5-capable Effective Policy identity (§28.2, GAP-A option 3): a per-Run stored policy property inside
#: the existing P4-capable owner family, distinct from ``review-v1-p4-policy-v1`` and every v1 policy. A new
#: first Run binds it after P5 activation; a cycle keeps the policy of its first Run; an existing Run is read
#: only from its own stored identity - never from file presence, current code or shape. This module defines
#: the identity and dispatches nothing on it.
P5_POLICY_ID = "review-v1-p5-policy-v1"

SCHEMA_RUN = "review-history-run"
SCHEMA_FINDING = "review-history-finding"
SCHEMA_REPAIR = "review-history-repair"
SCHEMA_RELATION = "review-history-relation"
SCHEMA_HUMAN_DECISION = "review-history-human-decision"
SCHEMAS = (SCHEMA_RUN, SCHEMA_FINDING, SCHEMA_REPAIR, SCHEMA_RELATION, SCHEMA_HUMAN_DECISION)
RECORD_VERSION = 1

# --------------------------------------------------------------------------- vocabularies (§13.4, §13.7, §13.8)

#: The durable disposition of one Review Run (§13.4), each final for that Run when its summary is written.
DISPOSITION_AUTHORIZED = "authorized"
DISPOSITION_REPAIRED = "repaired_to_next_candidate"
DISPOSITION_HUMAN_WAIT = "human_wait"
DISPOSITION_NOT_AUTHORIZED = "not_authorized"
DISPOSITION_INVALIDATED = "invalidated"
DISPOSITION_SET_ASIDE = "set_aside"
DISPOSITION_CONSUMED = "consumed"
DISPOSITION_HISTORICAL_ESCAPE = "historical_escape"
RUN_DISPOSITIONS = (
    DISPOSITION_AUTHORIZED,
    DISPOSITION_REPAIRED,
    DISPOSITION_HUMAN_WAIT,
    DISPOSITION_NOT_AUTHORIZED,
    DISPOSITION_INVALIDATED,
    DISPOSITION_SET_ASIDE,
    DISPOSITION_CONSUMED,
    DISPOSITION_HISTORICAL_ESCAPE,
)

#: The reserved dispositions of the closed vocabulary that no canonical source transition can prove final
#: for a Run yet (§13.4 / §28.5, GAP-F option a). See :func:`disposition_admitted`, the one place that
#: decides what a stored summary carrying one means.
DISPOSITIONS_WITHOUT_TRANSITION = (DISPOSITION_AUTHORIZED, DISPOSITION_HISTORICAL_ESCAPE)


def disposition_admitted(disposition: object) -> bool:
    """Whether a canonical source transition can prove ``disposition`` final for a Run - the GAP-F seam.

    GAP-F (a) separates SCHEMA VOCABULARY from a VALIDATED PRODUCIBLE SOURCE FACT:

    ```text
    vocabulary   the strict reader recognizes all eight values, authorized and
                 historical_escape included (they stay reserved, §13.4)
    producer     none: the builders refuse to build either value
    source fact  none can prove either final, so a stored summary carrying one
                 is refused by source validation (history_problems, and so
                 require_history_ready) - never valid without a canonical
                 source transition
    ```

    A successfully authorized Run reaches its actual later final disposition
    (consumed, invalidated, set_aside, repaired_to_next_candidate); a downstream
    escape is a relation, never a rewritten Run summary. There is no
    authorized-final state and no historical-escape lifecycle.
    """
    return disposition in RUN_DISPOSITIONS and disposition not in DISPOSITIONS_WITHOUT_TRANSITION


#: The Finding vocabularies are P4's, copied exactly from the canonical adjudication (§28.8).
FINDING_CATEGORIES = records.P4_CATEGORIES
FINDING_SEVERITIES = records.P4_SEVERITIES
FINDING_DISPOSITIONS = records.P4_DISPOSITIONS
FINDING_RELATIONS = records.P4_RELATIONS

#: The durable result of one Repair summary (P-7). A P4 Repair Result is written only for a repair that
#: settled successfully and is eligible to start a successor Run, so there is exactly one value.
REPAIR_RESULT_SUCCESSOR_ELIGIBLE = "repaired_successor_eligible"
REPAIR_RESULTS = (REPAIR_RESULT_SUCCESSOR_ELIGIBLE,)

#: §13.7 / §28.10: causal / relationship status. Only ``supported`` is ever counted as confirmed.
CAUSAL_SUPPORTED = "supported"
CAUSAL_UNRESOLVED = "unresolved"
CAUSAL_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
CAUSAL_STATUSES = (CAUSAL_SUPPORTED, CAUSAL_UNRESOLVED, CAUSAL_INSUFFICIENT_EVIDENCE)

#: §13.8 / §28.11: the minimum later / cross-run relation types.
RELATION_CROSS_RUN_RECURRENCE = "cross_run_recurrence"
RELATION_REPAIR_INDUCED = "repair_induced"
RELATION_DOWNSTREAM_ESCAPE = "downstream_escape"
RELATION_FUTURE_WORK_LINK = "future_work_link"
RELATION_TYPES = (
    RELATION_CROSS_RUN_RECURRENCE, RELATION_REPAIR_INDUCED, RELATION_DOWNSTREAM_ESCAPE, RELATION_FUTURE_WORK_LINK,
)
#: The relation types whose status claims semantic responsibility, so they name the semantic surface.
SURFACE_RELATIONS = (RELATION_CROSS_RUN_RECURRENCE, RELATION_REPAIR_INDUCED)

#: What a relation endpoint names: a Review Run, a P4 Finding, a P4 Repair Batch, or a Work.
ENDPOINT_RUN = "review_run"
ENDPOINT_FINDING = "review_finding"
ENDPOINT_REPAIR = "review_repair_batch"
ENDPOINT_WORK = "work"
ENDPOINT_KINDS = (ENDPOINT_RUN, ENDPOINT_FINDING, ENDPOINT_REPAIR, ENDPOINT_WORK)
#: Which record an endpoint's digest is the canonical digest of: the endpoint's P5 history record, or
#: its immutable P1-P4 source record. A Work is a Project entity, bound by its ID alone.
BASIS_HISTORY = "history"
BASIS_SOURCE = "source"
BASIS_PROJECT = "project"
ENDPOINT_BASES = (BASIS_HISTORY, BASIS_SOURCE, BASIS_PROJECT)

#: The endpoint kinds each relation type joins (§13.8-§13.10): ``(source kinds, target kinds)``. Every
#: relation starts at the later Finding that made it knowable.
RELATION_ENDPOINT_KINDS: Mapping[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    RELATION_CROSS_RUN_RECURRENCE: ((ENDPOINT_FINDING,), (ENDPOINT_FINDING,)),
    RELATION_REPAIR_INDUCED: ((ENDPOINT_FINDING,), (ENDPOINT_REPAIR,)),
    RELATION_DOWNSTREAM_ESCAPE: ((ENDPOINT_FINDING,), (ENDPOINT_RUN, ENDPOINT_FINDING, ENDPOINT_REPAIR)),
    RELATION_FUTURE_WORK_LINK: ((ENDPOINT_FINDING,), (ENDPOINT_WORK,)),
}

#: The disposition of the Human decision itself (G-4), spelled exactly as
#: :data:`workline.review.p4.DECISION_DISPOSITIONS` spells it.
DECISION_REQUIREMENT_CONFIRMED = "requirement_confirmed"
DECISION_REQUIREMENT_CHANGED = "requirement_changed"
DECISION_DISPOSITIONS = (DECISION_REQUIREMENT_CONFIRMED, DECISION_REQUIREMENT_CHANGED)
#: The caller's stable decision identity (G-4), with exactly the shape :mod:`workline.review.p4` accepts.
DECISION_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")

#: The resulting action class of a Human decision (§13.11, GAP-G): what the owner's continuation does as a
#: result - set the affected HUMAN_WAIT Run aside as ``human_decision`` and resume Review under the
#: requirement authority the decision confirmed or changed. Each action belongs to exactly one disposition.
ACTION_RESUME_CONFIRMED = "resume_under_confirmed_requirement"
ACTION_RESUME_CHANGED = "resume_under_changed_requirement"
ACTION_CLASSES = (ACTION_RESUME_CONFIRMED, ACTION_RESUME_CHANGED)
DECISION_ACTIONS: Mapping[str, str] = {
    DECISION_REQUIREMENT_CONFIRMED: ACTION_RESUME_CONFIRMED,
    DECISION_REQUIREMENT_CHANGED: ACTION_RESUME_CHANGED,
}

#: §28.20: the history status of a Review Run.
HISTORY_NOT_REQUIRED = "not_required_by_contract"
HISTORY_COMPLETE = "complete"
HISTORY_INCOMPLETE = "incomplete"
HISTORY_STATUSES = (HISTORY_NOT_REQUIRED, HISTORY_COMPLETE, HISTORY_INCOMPLETE)

#: §28.18: the boundaries a P5-capable owner transition may not cross without the required history.
BOUNDARY_FINDINGS = "g4_findings"
BOUNDARY_HUMAN_WAIT = "human_wait"
BOUNDARY_REPAIRED = "repaired_g6"
BOUNDARY_SUCCESSOR_LAUNCH = "successor_launch"
BOUNDARY_CONSUMPTION = "consumption"
BOUNDARIES = (BOUNDARY_FINDINGS, BOUNDARY_HUMAN_WAIT, BOUNDARY_REPAIRED, BOUNDARY_SUCCESSOR_LAUNCH, BOUNDARY_CONSUMPTION)

# --------------------------------------------------------------------------- the P5 catalogue

#: P5 STOP codes. Each is raised through :func:`stop` (a builder refusal builds its ValidationError with
#: the constant); none is a P2 or P4 catalogue name and none uses the ``review_p4_`` prefix.
#:
#: ``review_p5_history_missing``          required history (or its source) is not canonical at a P5 boundary
#: ``review_p5_history_invalid``          required history does not validate against its immutable source
#: ``review_p5_disposition_unsupported``  a reserved disposition no canonical transition proves (GAP-F): the
#:                                        source-validation problem code, and the builders' refusal
#: ``review_p5_authority_mismatch``       the canonical authority does not reflect a Human decision that
#:                                        should have changed it (§28.14); raised by the owner's evidence proof
#: ``review_p5_decision_evidence_invalid`` a Human Decision Evidence input that names no valid affected
#:                                        HUMAN_WAIT Run this continuation sets aside, or that disagrees with
#:                                        its canonical sources (GAP-G); STOP before any effect
CODE_HISTORY_MISSING = "review_p5_history_missing"
CODE_HISTORY_INVALID = "review_p5_history_invalid"
CODE_DISPOSITION_UNSUPPORTED = "review_p5_disposition_unsupported"
CODE_AUTHORITY_MISMATCH = "review_p5_authority_mismatch"
CODE_DECISION_EVIDENCE_INVALID = "review_p5_decision_evidence_invalid"
STOP_CODES = (CODE_HISTORY_MISSING, CODE_HISTORY_INVALID, CODE_DISPOSITION_UNSUPPORTED, CODE_AUTHORITY_MISMATCH,
              CODE_DECISION_EVIDENCE_INVALID)

#: P5 ReconcileRequired reasons, raised through :func:`reconcile`.
REASON_HISTORY_CONFLICT = "review_p5_history_conflict"
RECONCILE_REASONS = (REASON_HISTORY_CONFLICT,)

#: The P1 problem codes the cross-source checks report with (the codes :mod:`workline.review.validate`
#: already reports a missing or contradicting Review record with).
PROBLEM_MISSING = "review_record_missing"
PROBLEM_CONFLICT = "review_record_conflict"
PROBLEM_INVALID = "review_record_invalid"


def stop(code: str, message: str) -> StopError:
    """A P5 STOP (built here so the owners raise P5 codes without restating them)."""
    if code not in STOP_CODES:
        raise ValueError(f"not a P5 STOP code: {code!r}")
    return StopError(message, code=code)


def reconcile(message: str, reason: str) -> ReconcileRequired:
    """A P5 reconcile-required refusal (built here, for the same reason as :func:`stop`)."""
    if reason not in RECONCILE_REASONS:
        raise ValueError(f"not a P5 reconcile reason: {reason!r}")
    return ReconcileRequired(f"{message}: reconcile required", reason=reason)


# --------------------------------------------------------------------------- reservation keys (§28.4, O-2)

#: The prefix of a ``review_relation`` reservation. Never ``review-run:``, which START counts as its Runs.
RELATION_KEY_PREFIX = "review-relation:"
#: The prefix of a ``review_decision`` reservation.
DECISION_KEY_PREFIX = "review-decision:"


def _require_key_part(value: object, described: str) -> None:
    if not isinstance(value, str) or not value or ":" in value or value != value.strip():
        raise ValidationError(
            f"a Review history reservation key part must be non-empty text without ':' - {described} is {value!r}",
            code=PROBLEM_INVALID,
        )


def review_relation_key(scope_id: str, ordinal: int) -> str:
    """``review-relation:<scope_id>:<ordinal>`` - one relation an owner makes knowable within one scope.

    ``scope_id`` is the stable Workline ID of what the owner records the relation
    for (the current Review Run, the source Finding of a future Work, ...) and
    ``ordinal`` the relation's 1-based position in that owner's deterministic
    order, never an external return order, a timestamp or a file listing. A
    replay therefore reserves the same relation ID (§28.4).
    """
    _require_key_part(scope_id, "scope_id")
    if not is_valid_id(scope_id):
        raise ValidationError(f"a relation reservation is scoped by a Workline ID, not {scope_id!r}", code=PROBLEM_INVALID)
    if type(ordinal) is not int or ordinal < 1:
        raise ValidationError(f"a relation reservation ordinal is a positive integer, not {ordinal!r}",
                              code=PROBLEM_INVALID)
    return f"{RELATION_KEY_PREFIX}{scope_id}:{ordinal}"


def review_decision_key(affected_review_run_id: str) -> str:
    """``review-decision:<affected_review_run_id>`` - the Human Decision Evidence of one affected Run.

    One Human decision is evidence about the Run whose HUMAN adjudication it
    answers, so a replay of the same resume reserves the same decision ID.
    """
    _require_key_part(affected_review_run_id, "affected_review_run_id")
    if not is_valid_id(affected_review_run_id, "review_run"):
        raise ValidationError(
            f"a decision reservation is keyed by a review_run id, not {affected_review_run_id!r}", code=PROBLEM_INVALID
        )
    return f"{DECISION_KEY_PREFIX}{affected_review_run_id}"


# --------------------------------------------------------------------------- H-3 sanitation (§13.12, §28.15)

#: P-9: what a NEW public-safe history input (a Human decision summary, a relation rationale) never
#: carries beyond the P4 H-3 rule - unnecessary personal information. Never applied to text copied
#: from an already-canonical P4 record, and never to P1-P4 records themselves.
_NEW_INPUT_UNSAFE = (
    ("an email address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")),
)


def summary_problem(value: object) -> str | None:
    """Why ``value`` is not a public-safe NEW history summary, or ``None`` when it is.

    The P4 H-3 rule (non-empty, bounded, single line, no control or bidi
    character, no path, URL credential, key or token shape), plus P-9. It
    refuses; it never redacts or rewrites a claim into a different one.
    """
    problem = records.public_safe_problem(value)
    if problem is not None:
        return problem
    for described, pattern in _NEW_INPUT_UNSAFE:
        if pattern.search(str(value)):
            return f"it carries {described}"
    return None


def _require_summary(record: dict[str, Any], key: str, described: str) -> str:
    problem = summary_problem(record.get(key))
    if problem is not None:
        raise ValidationError(f"{described} {key} is not public-safe history text: {problem}", code=PROBLEM_INVALID)
    return str(record[key])


def _require_copied_text(record: dict[str, Any], key: str, described: str) -> str:
    """Text copied from an already-canonical P4 record: exactly P4's own H-3 rule, never a stricter one."""
    return records._require_public_text(record, key, described)


# --------------------------------------------------------------------------- shared field checks

def _header(schema: str) -> dict[str, Any]:
    return {serialize.SCHEMA_KEY: schema, serialize.VERSION_KEY: RECORD_VERSION, "history_contract": HISTORY_CONTRACT}


def _require_header(record: dict[str, Any], schema: str, fields: tuple[str, ...], described: str) -> None:
    serialize.require_schema(record, schema, RECORD_VERSION, described)
    records._require_exact_fields(record, fields, described)
    records._require_choice(record, "history_contract", (HISTORY_CONTRACT,), described)


def _require_digests(record: dict[str, Any], key: str, described: str, *, non_empty: bool = False) -> list[str]:
    items = records._require_list(record, key, described)
    for item in items:
        if not isinstance(item, str) or records.DIGEST_RE.match(item) is None:
            raise ValidationError(f"{described} {key} holds {item!r}, not a lowercase hex SHA-256",
                                  code=PROBLEM_INVALID)
    records._require_sorted_unique(items, key, described)
    if non_empty and not items:
        raise ValidationError(f"{described} {key} is empty", code=PROBLEM_INVALID)
    return items


def _require_labels(record: dict[str, Any], key: str, described: str) -> list[str]:
    items = records._require_public_list(record, key, described, labels=True)
    records._require_sorted_unique(items, key, described)
    return items


def _optional_int(record: dict[str, Any], key: str, described: str) -> int | None:
    if record.get(key) is None:
        return None
    return records._require_int(record, key, described, minimum=records.FIRST_GENERATION)


def _optional_label(record: dict[str, Any], key: str, described: str) -> str | None:
    if record.get(key) is None:
        return None
    return records._require_label(record, key, described)


# --------------------------------------------------------------------------- Run summary (§13.4, §28.5-§28.7)

RUN_SUMMARY_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "history_contract",
    "review_run_id",
    "review_kind",
    "target_identity",
    "operation_identity",
    "candidate_hash",
    "candidate_generation",
    "review_context_hash",
    "effective_policy_hash",
    "evidence_digest",
    "coverage_digest",
    "gate_generation",
    "gate_digest",
    "adjudication_digest",
    "finding_ids",
    "repair_batch_id",
    "receipt_id",
    "consumption_id",
    "durable_disposition",
)


@dataclass(frozen=True)
class RunSummary:
    """The one immutable summary of one Review Run, written once, at its final durable disposition.

    Compact structured facts only - identities and digests copied or
    recomputed from the Run's immutable gate chain, adjudication, Receipt and
    Consumption - and no Candidate bytes, report prose or Gate record. It is
    never consulted to decide lifecycle progression (§28.7).
    """

    review_run_id: str
    review_kind: str
    target_identity: str
    operation_identity: str
    candidate_hash: str
    candidate_generation: int | None
    review_context_hash: str
    effective_policy_hash: str
    evidence_digest: str
    coverage_digest: str
    gate_generation: int
    gate_digest: str
    adjudication_digest: str | None
    finding_ids: tuple[str, ...]
    repair_batch_id: str | None
    receipt_id: str | None
    consumption_id: str | None
    durable_disposition: str

    def to_record(self) -> dict[str, Any]:
        record = _header(SCHEMA_RUN)
        record.update({
            "review_run_id": self.review_run_id,
            "review_kind": self.review_kind,
            "target_identity": self.target_identity,
            "operation_identity": self.operation_identity,
            "candidate_hash": self.candidate_hash,
            "candidate_generation": self.candidate_generation,
            "review_context_hash": self.review_context_hash,
            "effective_policy_hash": self.effective_policy_hash,
            "evidence_digest": self.evidence_digest,
            "coverage_digest": self.coverage_digest,
            "gate_generation": self.gate_generation,
            "gate_digest": self.gate_digest,
            "adjudication_digest": self.adjudication_digest,
            "finding_ids": list(self.finding_ids),
            "repair_batch_id": self.repair_batch_id,
            "receipt_id": self.receipt_id,
            "consumption_id": self.consumption_id,
            "durable_disposition": self.durable_disposition,
        })
        return record

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "RunSummary":
        _require_header(record, SCHEMA_RUN, RUN_SUMMARY_FIELDS, described)
        # The whole closed vocabulary is recognized here, the two reserved values included (GAP-F): whether
        # a canonical source transition proves the disposition is source validation's question.
        disposition = records._require_choice(record, "durable_disposition", RUN_DISPOSITIONS, described)
        finding_ids = records._require_id_list(record, "finding_ids", "review_finding", described)
        adjudication_digest = records._require_optional_digest(record, "adjudication_digest", described)
        repair_batch_id = records._require_optional_id(record, "repair_batch_id", "review_repair_batch", described)
        receipt_id = records._require_optional_id(record, "receipt_id", "review_receipt", described)
        consumption_id = records._require_optional_id(record, "consumption_id", "review_consumption", described)
        _require_disposition_shape(
            described, disposition, adjudication_digest=adjudication_digest, finding_ids=finding_ids,
            repair_batch_id=repair_batch_id, receipt_id=receipt_id, consumption_id=consumption_id,
        )
        return RunSummary(
            review_run_id=records._require_id(record, "review_run_id", "review_run", described),
            review_kind=records._require_text(record, "review_kind", described),
            target_identity=records._require_text(record, "target_identity", described),
            operation_identity=records._require_text(record, "operation_identity", described),
            candidate_hash=records._require_digest(record, "candidate_hash", described),
            candidate_generation=_optional_int(record, "candidate_generation", described),
            review_context_hash=records._require_digest(record, "review_context_hash", described),
            effective_policy_hash=records._require_digest(record, "effective_policy_hash", described),
            evidence_digest=records._require_digest(record, "evidence_digest", described),
            coverage_digest=records._require_digest(record, "coverage_digest", described),
            gate_generation=records._require_int(record, "gate_generation", described,
                                                 minimum=records.FIRST_GENERATION),
            gate_digest=records._require_digest(record, "gate_digest", described),
            adjudication_digest=adjudication_digest,
            finding_ids=tuple(finding_ids),
            repair_batch_id=repair_batch_id,
            receipt_id=receipt_id,
            consumption_id=consumption_id,
            durable_disposition=disposition,
        )


def _require_disposition_shape(
    described: str, disposition: str, *, adjudication_digest: str | None, finding_ids: Sequence[str],
    repair_batch_id: str | None, receipt_id: str | None, consumption_id: str | None,
) -> None:
    """What each disposition says about the Run on its own, before any source is read.

    ```text
    consumed                   a Receipt and its Consumption; no Repair Batch
    repaired_to_next_candidate a Repair Batch after an adjudication; no Receipt, no Consumption
    human_wait                 an adjudication; no Receipt, no Repair Batch, no Consumption
    invalidated                the superseded Receipt; no Consumption, no Repair Batch
    not_authorized             written in the G2 settlement (GAP-E): no adjudication, no Finding,
                               no Receipt, no Consumption, no Repair Batch
    set_aside                  no Consumption
    authorized / historical_   recognized vocabulary only; no shape is defined, because no
    escape                     transition proves either (GAP-F, refused by source validation)
    ```

    A Consumption is named by a ``consumed`` summary and by nothing else, and a
    Finding is named only by a summary that binds the adjudication holding it.
    """
    def refuse(message: str) -> ValidationError:
        return ValidationError(f"{described} is {disposition} and {message}", code=PROBLEM_INVALID)

    if finding_ids and adjudication_digest is None:
        raise ValidationError(f"{described} names Findings and binds no adjudication", code=PROBLEM_INVALID)
    if (consumption_id is not None) != (disposition == DISPOSITION_CONSUMED):
        raise ValidationError(f"{described} names a Consumption exactly when it is {DISPOSITION_CONSUMED}",
                              code=PROBLEM_INVALID)
    if disposition == DISPOSITION_CONSUMED:
        if receipt_id is None:
            raise refuse("names no Receipt")
        if repair_batch_id is not None:
            raise refuse("names a Repair Batch")
    elif disposition == DISPOSITION_REPAIRED:
        if repair_batch_id is None or adjudication_digest is None:
            raise refuse("does not name both its adjudication and its Repair Batch")
        if receipt_id is not None:
            raise refuse("names a Receipt")
    elif disposition == DISPOSITION_HUMAN_WAIT:
        if adjudication_digest is None:
            raise refuse("binds no adjudication")
        if receipt_id is not None or repair_batch_id is not None:
            raise refuse("names a Receipt or a Repair Batch")
    elif disposition == DISPOSITION_INVALIDATED:
        if receipt_id is None:
            raise refuse("names no superseded Receipt")
        if repair_batch_id is not None:
            raise refuse("names a Repair Batch")
    elif disposition == DISPOSITION_NOT_AUTHORIZED:
        if receipt_id is not None or repair_batch_id is not None:
            raise refuse("names a Receipt or a Repair Batch")
        if adjudication_digest is not None:
            raise refuse("binds an adjudication; non-authorization is final at the discovery settlement (GAP-E)")


# --------------------------------------------------------------------------- Finding summary (§13.5, §28.8)

FINDING_SUMMARY_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "history_contract",
    "finding_id",
    "review_run_id",
    "candidate_hash",
    "adjudication_digest",
    "source_report_digests",
    "category",
    "severity",
    "semantic_surface",
    "summary",
    "disposition",
    "relation",
    "linked_finding_ids",
    "linked_repair_batch_ids",
    "causal_evidence_digest",
    "relation_ids",
)


@dataclass(frozen=True)
class FindingSummary:
    """The immutable summary of one canonical normalized P4 Finding (§28.8).

    Problem or Improvement only: an unsupported, HUMAN or dismissed claim never
    becomes one. Category, severity, semantic surface, disposition and the A/B/C
    relationship are P4's exactly; ``summary`` is P4's canonical public-safe
    statement, never raw external output. The related Repair Batches are only
    those canonical P4 linkage already fixed (``linked_repair_batch_ids``); the
    forward link to the Run's own repair is the Repair summary's
    ``finding_ids``. ``relation_ids`` are the cross-run relations the SAME G4
    made knowable starting at this Finding (GAP-C) - the canonical record the
    owner derives that G4's relation paths from (P-5). Later relations are
    separate records that point here; this file is never backpatched with them.
    """

    finding_id: str
    review_run_id: str
    candidate_hash: str
    adjudication_digest: str
    source_report_digests: tuple[str, ...]
    category: str
    severity: str
    semantic_surface: str
    summary: str
    disposition: str
    relation: str
    linked_finding_ids: tuple[str, ...]
    linked_repair_batch_ids: tuple[str, ...]
    causal_evidence_digest: str | None
    relation_ids: tuple[str, ...] = ()

    def to_record(self) -> dict[str, Any]:
        record = _header(SCHEMA_FINDING)
        record.update({
            "finding_id": self.finding_id,
            "review_run_id": self.review_run_id,
            "candidate_hash": self.candidate_hash,
            "adjudication_digest": self.adjudication_digest,
            "source_report_digests": list(self.source_report_digests),
            "category": self.category,
            "severity": self.severity,
            "semantic_surface": self.semantic_surface,
            "summary": self.summary,
            "disposition": self.disposition,
            "relation": self.relation,
            "linked_finding_ids": list(self.linked_finding_ids),
            "linked_repair_batch_ids": list(self.linked_repair_batch_ids),
            "causal_evidence_digest": self.causal_evidence_digest,
            "relation_ids": list(self.relation_ids),
        })
        return record

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "FindingSummary":
        _require_header(record, SCHEMA_FINDING, FINDING_SUMMARY_FIELDS, described)
        return FindingSummary(
            finding_id=records._require_id(record, "finding_id", "review_finding", described),
            review_run_id=records._require_id(record, "review_run_id", "review_run", described),
            candidate_hash=records._require_digest(record, "candidate_hash", described),
            adjudication_digest=records._require_digest(record, "adjudication_digest", described),
            source_report_digests=tuple(_require_digests(record, "source_report_digests", described, non_empty=True)),
            category=records._require_choice(record, "category", FINDING_CATEGORIES, described),
            severity=records._require_choice(record, "severity", FINDING_SEVERITIES, described),
            semantic_surface=records._require_label(record, "semantic_surface", described),
            summary=_require_copied_text(record, "summary", described),
            disposition=records._require_choice(record, "disposition", FINDING_DISPOSITIONS, described),
            relation=records._require_choice(record, "relation", FINDING_RELATIONS, described),
            linked_finding_ids=tuple(records._require_id_list(record, "linked_finding_ids", "review_finding", described)),
            linked_repair_batch_ids=tuple(
                records._require_id_list(record, "linked_repair_batch_ids", "review_repair_batch", described)
            ),
            causal_evidence_digest=records._require_optional_digest(record, "causal_evidence_digest", described),
            relation_ids=tuple(_require_relation_ids(record, described)),
        )


def _require_relation_ids(record: dict[str, Any], described: str) -> list[str]:
    found = records._require_id_list(record, "relation_ids", "review_relation", described)
    records._require_sorted_unique(found, "relation_ids", described)
    return found


# --------------------------------------------------------------------------- durable causal material (§13.7, §28.10)

CAUSAL_MATERIAL_FIELDS = (
    "source_candidate_material_digest",
    "result_candidate_material_digest",
    "repaired_surface",
    "affected_surfaces",
    "reverification_digest",
    "review_context_hash",
    "effective_policy_hash",
)


@dataclass(frozen=True)
class CausalMaterial:
    """References sufficient to re-open the exact repair-relevant material, never the material itself.

    The complete source and result Candidates are named by their stored
    snapshots' material digests (which carry the whole operation-owned delta),
    alongside the surface the repair touched, the impact-analysis affected set,
    the reverification and the Context / Policy identities. No Candidate byte or
    owned delta is duplicated here (§28.10).
    """

    source_candidate_material_digest: str
    result_candidate_material_digest: str
    repaired_surface: tuple[str, ...]
    affected_surfaces: tuple[str, ...]
    reverification_digest: str
    review_context_hash: str
    effective_policy_hash: str

    def to_record(self) -> dict[str, Any]:
        return {
            "source_candidate_material_digest": self.source_candidate_material_digest,
            "result_candidate_material_digest": self.result_candidate_material_digest,
            "repaired_surface": list(self.repaired_surface),
            "affected_surfaces": list(self.affected_surfaces),
            "reverification_digest": self.reverification_digest,
            "review_context_hash": self.review_context_hash,
            "effective_policy_hash": self.effective_policy_hash,
        }

    @staticmethod
    def from_record(value: object, described: str) -> "CausalMaterial":
        where = f"{described} causal_material"
        record = records._require_mapping(value, where)
        records._require_exact_fields(record, CAUSAL_MATERIAL_FIELDS, where)
        repaired = records._require_public_list(record, "repaired_surface", where)
        records._require_sorted_unique(repaired, "repaired_surface", where)
        if not repaired:
            raise ValidationError(f"{where} names no repaired surface", code=PROBLEM_INVALID)
        return CausalMaterial(
            source_candidate_material_digest=records._require_digest(record, "source_candidate_material_digest", where),
            result_candidate_material_digest=records._require_digest(record, "result_candidate_material_digest", where),
            repaired_surface=tuple(repaired),
            affected_surfaces=tuple(records._require_public_list(record, "affected_surfaces", where)),
            reverification_digest=records._require_digest(record, "reverification_digest", where),
            review_context_hash=records._require_digest(record, "review_context_hash", where),
            effective_policy_hash=records._require_digest(record, "effective_policy_hash", where),
        )


# --------------------------------------------------------------------------- Repair summary (§13.6, §28.9)

REPAIR_SUMMARY_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "history_contract",
    "repair_batch_id",
    "source_review_run_id",
    "source_candidate_hash",
    "result_candidate_hash",
    "finding_ids",
    "semantic_surfaces",
    "strategy",
    "strategy_change_class",
    "impact_class",
    "coverage_check_digest",
    "coverage_covers_affected_set",
    "coverage_repair_scope",
    "evidence_reusable_ids",
    "evidence_unknown_ids",
    "evidence_invalidated_ids",
    "repair_identity",
    "repair_version",
    "durable_result",
    "batch_digest",
    "result_digest",
    "causal_material",
)


@dataclass(frozen=True)
class RepairSummary:
    """The immutable summary of one P4 Repair Batch and its Repair Result (§28.9).

    It never claims causality: a later Finding adjacent in time to this repair
    is not thereby caused by it. Causality is a separate relation record with
    its own evidence and status.
    """

    repair_batch_id: str
    source_review_run_id: str
    source_candidate_hash: str
    result_candidate_hash: str
    finding_ids: tuple[str, ...]
    semantic_surfaces: tuple[str, ...]
    strategy: str
    strategy_change_class: str | None
    impact_class: str
    coverage_check_digest: str
    coverage_covers_affected_set: bool
    coverage_repair_scope: str
    evidence_reusable_ids: tuple[str, ...]
    evidence_unknown_ids: tuple[str, ...]
    evidence_invalidated_ids: tuple[str, ...]
    repair_identity: str
    repair_version: str
    durable_result: str
    batch_digest: str
    result_digest: str
    causal_material: CausalMaterial

    def to_record(self) -> dict[str, Any]:
        record = _header(SCHEMA_REPAIR)
        record.update({
            "repair_batch_id": self.repair_batch_id,
            "source_review_run_id": self.source_review_run_id,
            "source_candidate_hash": self.source_candidate_hash,
            "result_candidate_hash": self.result_candidate_hash,
            "finding_ids": list(self.finding_ids),
            "semantic_surfaces": list(self.semantic_surfaces),
            "strategy": self.strategy,
            "strategy_change_class": self.strategy_change_class,
            "impact_class": self.impact_class,
            "coverage_check_digest": self.coverage_check_digest,
            "coverage_covers_affected_set": self.coverage_covers_affected_set,
            "coverage_repair_scope": self.coverage_repair_scope,
            "evidence_reusable_ids": list(self.evidence_reusable_ids),
            "evidence_unknown_ids": list(self.evidence_unknown_ids),
            "evidence_invalidated_ids": list(self.evidence_invalidated_ids),
            "repair_identity": self.repair_identity,
            "repair_version": self.repair_version,
            "durable_result": self.durable_result,
            "batch_digest": self.batch_digest,
            "result_digest": self.result_digest,
            "causal_material": self.causal_material.to_record(),
        })
        return record

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "RepairSummary":
        _require_header(record, SCHEMA_REPAIR, REPAIR_SUMMARY_FIELDS, described)
        finding_ids = records._require_id_list(record, "finding_ids", "review_finding", described)
        if not finding_ids:
            raise ValidationError(f"{described} names no repaired Finding", code=PROBLEM_INVALID)
        surfaces = _require_labels(record, "semantic_surfaces", described)
        if not surfaces:
            raise ValidationError(f"{described} names no semantic surface", code=PROBLEM_INVALID)
        strategy = records._require_choice(record, "strategy", records.P4_STRATEGIES, described)
        change_class = record.get("strategy_change_class")
        if strategy == records.STRATEGY_CHANGE:
            records._require_choice(record, "strategy_change_class", records.P4_STRATEGY_CHANGE_CLASSES, described)
        elif change_class is not None:
            raise ValidationError(f"{described} is an ordinary strategy and names a strategy-change class",
                                  code=PROBLEM_INVALID)
        evidence = {
            name: _require_labels(record, name, described)
            for name in ("evidence_reusable_ids", "evidence_unknown_ids", "evidence_invalidated_ids")
        }
        seen: set[str] = set()
        for items in evidence.values():
            if seen & set(items):
                raise ValidationError(f"{described} decides one Evidence two ways", code=PROBLEM_INVALID)
            seen |= set(items)
        source_hash = records._require_digest(record, "source_candidate_hash", described)
        result_hash = records._require_digest(record, "result_candidate_hash", described)
        if source_hash == result_hash:
            raise ValidationError(f"{described} names the source Candidate as its result", code=PROBLEM_INVALID)
        return RepairSummary(
            repair_batch_id=records._require_id(record, "repair_batch_id", "review_repair_batch", described),
            source_review_run_id=records._require_id(record, "source_review_run_id", "review_run", described),
            source_candidate_hash=source_hash,
            result_candidate_hash=result_hash,
            finding_ids=tuple(finding_ids),
            semantic_surfaces=tuple(surfaces),
            strategy=strategy,
            strategy_change_class=None if change_class is None else str(change_class),
            impact_class=records._require_choice(record, "impact_class", records.P4_IMPACT_CLASSES, described),
            coverage_check_digest=records._require_digest(record, "coverage_check_digest", described),
            coverage_covers_affected_set=records._require_bool(record, "coverage_covers_affected_set", described),
            coverage_repair_scope=records._require_choice(record, "coverage_repair_scope", records.P4_REPAIR_SCOPES,
                                                          described),
            evidence_reusable_ids=tuple(evidence["evidence_reusable_ids"]),
            evidence_unknown_ids=tuple(evidence["evidence_unknown_ids"]),
            evidence_invalidated_ids=tuple(evidence["evidence_invalidated_ids"]),
            repair_identity=records._require_text(record, "repair_identity", described),
            repair_version=records._require_text(record, "repair_version", described),
            durable_result=records._require_choice(record, "durable_result", REPAIR_RESULTS, described),
            batch_digest=records._require_digest(record, "batch_digest", described),
            result_digest=records._require_digest(record, "result_digest", described),
            causal_material=CausalMaterial.from_record(record.get("causal_material"), described),
        )


# --------------------------------------------------------------------------- relation record (§13.8, §28.11, §28.13)

ENDPOINT_FIELDS = ("kind", "id", "basis", "digest")


@dataclass(frozen=True)
class Endpoint:
    """One end of a relation: what it names, and the digest of the exact record that names it.

    A Review endpoint binds the canonical digest of either its P5 history record
    (``basis = history``) or its immutable P1-P4 source record (``basis =
    source``); a Work is a Project entity and binds its ID alone.
    """

    kind: str
    id: str
    basis: str
    digest: str | None

    def to_record(self) -> dict[str, Any]:
        return {"kind": self.kind, "id": self.id, "basis": self.basis, "digest": self.digest}

    @property
    def identity(self) -> tuple[str, str]:
        return (self.kind, self.id)

    @staticmethod
    def from_record(value: object, described: str) -> "Endpoint":
        record = records._require_mapping(value, described)
        records._require_exact_fields(record, ENDPOINT_FIELDS, described)
        kind = records._require_choice(record, "kind", ENDPOINT_KINDS, described)
        identifier = records._require_id(record, "id", kind, described)
        basis = records._require_choice(record, "basis", ENDPOINT_BASES, described)
        if kind == ENDPOINT_WORK:
            if basis != BASIS_PROJECT or record.get("digest") is not None:
                raise ValidationError(f"{described} names a Work, which is bound by its ID alone",
                                      code=PROBLEM_INVALID)
            return Endpoint(kind, identifier, basis, None)
        if basis == BASIS_PROJECT:
            raise ValidationError(f"{described} names a Review record on a Project basis", code=PROBLEM_INVALID)
        return Endpoint(kind, identifier, basis, records._require_digest(record, "digest", described))


RELATION_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "history_contract",
    "relation_id",
    "relation_type",
    "source",
    "target",
    "semantic_surface",
    "status",
    "supporting_evidence_digests",
    "rationale",
)


@dataclass(frozen=True)
class Relation:
    """One append-only later / cross-run relation (§28.11). It never edits either endpoint.

    Code or message equality is never the evidence: a ``supported`` status
    carries at least one supporting Evidence digest, and an unresolved or
    insufficient one stays exactly that - only ``supported`` is ever counted as
    a confirmed recurrence or causality.
    """

    relation_id: str
    relation_type: str
    source: Endpoint
    target: Endpoint
    semantic_surface: str | None
    status: str
    supporting_evidence_digests: tuple[str, ...]
    rationale: str

    @property
    def logical_identity(self) -> tuple[str, tuple[str, str], tuple[str, str]]:
        """What two records may not both say: one type between one source and one target."""
        return (self.relation_type, self.source.identity, self.target.identity)

    @property
    def confirmed(self) -> bool:
        """Whether this relation may feed confirmed recurrence / causality / learning (§28.10)."""
        return self.status == CAUSAL_SUPPORTED

    def to_record(self) -> dict[str, Any]:
        record = _header(SCHEMA_RELATION)
        record.update({
            "relation_id": self.relation_id,
            "relation_type": self.relation_type,
            "source": self.source.to_record(),
            "target": self.target.to_record(),
            "semantic_surface": self.semantic_surface,
            "status": self.status,
            "supporting_evidence_digests": list(self.supporting_evidence_digests),
            "rationale": self.rationale,
        })
        return record

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "Relation":
        _require_header(record, SCHEMA_RELATION, RELATION_FIELDS, described)
        relation_type = records._require_choice(record, "relation_type", RELATION_TYPES, described)
        source = Endpoint.from_record(record.get("source"), f"{described} source")
        target = Endpoint.from_record(record.get("target"), f"{described} target")
        source_kinds, target_kinds = RELATION_ENDPOINT_KINDS[relation_type]
        if source.kind not in source_kinds or target.kind not in target_kinds:
            raise ValidationError(
                f"{described} is a {relation_type} from a {source.kind} to a {target.kind}; it joins a "
                f"{' / '.join(source_kinds)} to a {' / '.join(target_kinds)}",
                code=PROBLEM_INVALID,
            )
        if source.identity == target.identity:
            raise ValidationError(f"{described} relates {source.id} to itself", code=PROBLEM_INVALID)
        surface = _optional_label(record, "semantic_surface", described)
        if relation_type in SURFACE_RELATIONS and surface is None:
            raise ValidationError(
                f"{described} is a {relation_type}, which claims a semantic responsibility and names no surface",
                code=PROBLEM_INVALID,
            )
        status = records._require_choice(record, "status", CAUSAL_STATUSES, described)
        evidence = _require_digests(record, "supporting_evidence_digests", described)
        if status == CAUSAL_SUPPORTED and not evidence:
            raise ValidationError(f"{described} is supported and carries no supporting evidence",
                                  code=PROBLEM_INVALID)
        return Relation(
            relation_id=records._require_id(record, "relation_id", "review_relation", described),
            relation_type=relation_type,
            source=source,
            target=target,
            semantic_surface=surface,
            status=status,
            supporting_evidence_digests=tuple(evidence),
            rationale=_require_summary(record, "rationale", described),
        )


# --------------------------------------------------------------------------- Human Decision Evidence (§13.11, §28.14)

HUMAN_DECISION_FIELDS = (
    serialize.SCHEMA_KEY,
    serialize.VERSION_KEY,
    "history_contract",
    "review_decision_id",
    "decision_id",
    "decision_disposition",
    "affected_review_run_id",
    "affected_candidate_hash",
    "affected_adjudication_digest",
    "affected_entries",
    "affected_coverage_gaps",
    "question_summary",
    "decision_summary",
    "authority_identity",
    "action_class",
    "source_digests",
    "effect_digests",
)
#: An adjudication entry is identified by the raw claim it adjudicates.
AFFECTED_ENTRY_FIELDS = records.SOURCE_FIELDS
#: A coverage gap is identified by its discovery task and its surface.
AFFECTED_GAP_FIELDS = ("task_id", "surface")
#: The coverage-gap resolutions that are HUMAN obligations (:func:`workline.review.p4._human_count`).
HUMAN_GAP_RESOLUTIONS = (records.GAP_HUMAN, records.GAP_TARGETED_CHECK)


@dataclass(frozen=True)
class HumanDecisionEvidence:
    """Evidence that a Human actually made the decision a concrete HUMAN adjudication needed (§13.11, GAP-G).

    One record per affected Run. Its filename identity is the replay-stable
    reserved ``review_decision`` ID (``review_decision_id``); the caller's G-4
    ``decision_id`` and its disposition are fields, never the record identity.
    It names the exact affected HUMAN_WAIT Run, Candidate and HUMAN
    adjudication references, the canonical requirement / authority identity the
    decision is about, the resulting action class and the source / effect
    digests that prove what changed.

    It is evidence that the decision occurred - never the canonical requirement,
    specification or authority the Human changed or confirmed, which the owner
    reads and proves separately. No transcript, deliberation or free-form
    metadata has a field here.
    """

    review_decision_id: str
    decision_id: str
    decision_disposition: str
    affected_review_run_id: str
    affected_candidate_hash: str
    affected_adjudication_digest: str
    affected_entries: tuple[dict[str, Any], ...]
    affected_coverage_gaps: tuple[dict[str, Any], ...]
    question_summary: str
    decision_summary: str
    authority_identity: str
    action_class: str
    source_digests: tuple[str, ...]
    effect_digests: tuple[str, ...]

    def to_record(self) -> dict[str, Any]:
        record = _header(SCHEMA_HUMAN_DECISION)
        record.update({
            "review_decision_id": self.review_decision_id,
            "decision_id": self.decision_id,
            "decision_disposition": self.decision_disposition,
            "affected_review_run_id": self.affected_review_run_id,
            "affected_candidate_hash": self.affected_candidate_hash,
            "affected_adjudication_digest": self.affected_adjudication_digest,
            "affected_entries": [dict(item) for item in self.affected_entries],
            "affected_coverage_gaps": [dict(item) for item in self.affected_coverage_gaps],
            "question_summary": self.question_summary,
            "decision_summary": self.decision_summary,
            "authority_identity": self.authority_identity,
            "action_class": self.action_class,
            "source_digests": list(self.source_digests),
            "effect_digests": list(self.effect_digests),
        })
        return record

    @staticmethod
    def from_record(record: dict[str, Any], described: str) -> "HumanDecisionEvidence":
        _require_header(record, SCHEMA_HUMAN_DECISION, HUMAN_DECISION_FIELDS, described)
        entries: list[dict[str, Any]] = []
        for item in records._require_list(record, "affected_entries", described):
            entries.append(records._validate_source(item, f"{described} affected entry"))
        keys = [records._source_key(entry) for entry in entries]
        if keys != sorted(set(keys)):
            raise ValidationError(f"{described} affected_entries are not sorted and duplicate-free",
                                  code=PROBLEM_INVALID)
        gaps: list[dict[str, Any]] = []
        for item in records._require_list(record, "affected_coverage_gaps", described):
            where = f"{described} affected coverage gap"
            gap = records._require_mapping(item, where)
            records._require_exact_fields(gap, AFFECTED_GAP_FIELDS, where)
            records._require_id(gap, "task_id", "review_task", where)
            _require_copied_text(gap, "surface", where)
            gaps.append(gap)
        gap_keys = [(gap["task_id"], gap["surface"]) for gap in gaps]
        if gap_keys != sorted(set(gap_keys)):
            raise ValidationError(f"{described} affected_coverage_gaps are not sorted and duplicate-free",
                                  code=PROBLEM_INVALID)
        if not entries and not gaps:
            raise ValidationError(f"{described} points at no HUMAN adjudication entry or coverage gap",
                                  code=PROBLEM_INVALID)
        decision_id = records._require_text(record, "decision_id", described)
        if DECISION_ID_PATTERN.match(decision_id) is None:
            raise ValidationError(f"{described} decision_id {decision_id!r} is not a stable decision identity",
                                  code=PROBLEM_INVALID)
        disposition = records._require_choice(record, "decision_disposition", DECISION_DISPOSITIONS, described)
        action = records._require_choice(record, "action_class", ACTION_CLASSES, described)
        if action != DECISION_ACTIONS[disposition]:
            raise ValidationError(
                f"{described} is {disposition} and names action class {action!r}, not "
                f"{DECISION_ACTIONS[disposition]!r}",
                code=PROBLEM_INVALID,
            )
        source_digests = _require_digests(record, "source_digests", described, non_empty=True)
        effect_digests = _require_digests(record, "effect_digests", described)
        if disposition == DECISION_REQUIREMENT_CHANGED and not effect_digests:
            raise ValidationError(
                f"{described} changes the requirement and binds no effect digest proving the change",
                code=PROBLEM_INVALID,
            )
        return HumanDecisionEvidence(
            review_decision_id=records._require_id(record, "review_decision_id", "review_decision", described),
            decision_id=decision_id,
            decision_disposition=disposition,
            affected_review_run_id=records._require_id(record, "affected_review_run_id", "review_run", described),
            affected_candidate_hash=records._require_digest(record, "affected_candidate_hash", described),
            affected_adjudication_digest=records._require_digest(record, "affected_adjudication_digest", described),
            affected_entries=tuple(entries),
            affected_coverage_gaps=tuple(gaps),
            question_summary=_require_summary(record, "question_summary", described),
            decision_summary=_require_summary(record, "decision_summary", described),
            authority_identity=records._require_label(record, "authority_identity", described),
            action_class=action,
            source_digests=tuple(source_digests),
            effect_digests=tuple(effect_digests),
        )


# --------------------------------------------------------------------------- the families

#: The record class of each history family, by the family directory its records live in.
FAMILY_RECORDS: Mapping[str, Any] = {
    paths.HISTORY_RUNS: RunSummary,
    paths.HISTORY_FINDINGS: FindingSummary,
    paths.HISTORY_REPAIRS: RepairSummary,
    paths.HISTORY_RELATIONS: Relation,
    paths.HISTORY_HUMAN_DECISIONS: HumanDecisionEvidence,
}
#: The field of each family's record that must equal the identity its filename names.
FAMILY_IDENTITY_FIELDS: Mapping[str, str] = {
    paths.HISTORY_RUNS: "review_run_id",
    paths.HISTORY_FINDINGS: "finding_id",
    paths.HISTORY_REPAIRS: "repair_batch_id",
    paths.HISTORY_RELATIONS: "relation_id",
    paths.HISTORY_HUMAN_DECISIONS: "review_decision_id",
}


def parse_history(family: str, record: dict[str, Any], described: str) -> Any:
    """The typed history record ``record`` is, read by its family's strict parser."""
    if family not in FAMILY_RECORDS:
        raise ValidationError(f"not a Review history family: {family!r}", code=PROBLEM_INVALID)
    return FAMILY_RECORDS[family].from_record(record, described)


def record_identity(family: str, found: Any) -> str:
    """The stable identity a history record of ``family`` declares inside its bytes."""
    return str(getattr(found, FAMILY_IDENTITY_FIELDS[family]))


def history_contract_of_envelope(envelope: object) -> str | None:
    """The history contract a request envelope explicitly binds, or ``None`` when it binds none.

    Explicit persisted identity only (§28.2): never inferred from a history
    directory, a record shape or a generation count. A bound value this build
    does not implement is refused rather than read as "none".
    """
    if not isinstance(envelope, dict) or HISTORY_CONTRACT_KEY not in envelope:
        return None
    found = envelope[HISTORY_CONTRACT_KEY]
    if found != HISTORY_CONTRACT:
        raise ValidationError(
            f"a request envelope binds history contract {found!r}, which this build does not implement",
            code="review_record_version",
        )
    return HISTORY_CONTRACT


# --------------------------------------------------------------------------- builders (owners call these; nothing here does)

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message, code=PROBLEM_INVALID)


def _built(family: str, found: Any) -> Any:
    """``found`` exactly as its family's strict reader would read it back - or a refusal before persistence.

    The canonical rendering must read back as the same data, and the strict
    reader must return exactly what was built: a value the schema would
    normalize, or text a reader would take for something else, is refused here
    rather than persisted and read back as a different record.
    """
    record = serialize.canonical_data(found.to_record())
    described = f"the {family} history record"
    if not serialize.canonical_roundtrips(record):
        raise ValidationError(f"{described} does not read back as the record it renders", code=PROBLEM_INVALID)
    parsed = parse_history(family, record, described)
    if serialize.canonical_data(parsed.to_record()) != record:
        raise ValidationError(f"{described} does not round-trip through its schema unchanged", code=PROBLEM_INVALID)
    return parsed


def run_summary(
    terminal: records.GateGeneration,
    *,
    durable_disposition: str,
    candidate_generation: int | None,
    adjudication: records.P4Adjudication | None = None,
    repair_batch_id: str | None = None,
    receipt_id: str | None = None,
    consumption_id: str | None = None,
) -> RunSummary:
    """The Run summary of the Run whose final generation is ``terminal`` (§28.5-§28.7).

    ``terminal`` is the generation the final transition fixes - written by that
    same transition, or already stored - and its digest is recomputed from it
    here, as the adjudication's is. Every other identity is copied from those
    two records, so the summary cannot say something its sources do not.

    Nothing produces ``authorized`` or ``historical_escape`` (GAP-F): no
    canonical transition proves either final, so this builder refuses both.
    """
    if not disposition_admitted(durable_disposition):
        raise ValidationError(
            f"no canonical transition proves durable disposition {durable_disposition!r} final for a Run; P5 "
            "writes no summary carrying it (GAP-F)",
            code=CODE_DISPOSITION_UNSUPPORTED,
        )
    _require(adjudication is None or adjudication.review_run_id == terminal.review_run_id,
             "the adjudication is not of the Run the summary is of")
    _require(adjudication is None or adjudication.candidate_hash == terminal.candidate_hash,
             "the adjudication is not of the Run's Candidate")
    _require(adjudication is None or candidate_generation == adjudication.candidate_generation,
             "the candidate generation is not the adjudication's")
    found = RunSummary(
        review_run_id=terminal.review_run_id,
        review_kind=terminal.review_kind,
        target_identity=terminal.target_identity,
        operation_identity=terminal.operation_identity,
        candidate_hash=terminal.candidate_hash,
        candidate_generation=candidate_generation,
        review_context_hash=terminal.review_context_hash,
        effective_policy_hash=terminal.effective_policy_hash,
        evidence_digest=terminal.evidence_digest,
        coverage_digest=terminal.coverage_digest,
        gate_generation=terminal.generation,
        gate_digest=serialize.digest(terminal.to_record()),
        adjudication_digest=None if adjudication is None else serialize.digest(adjudication.to_record()),
        finding_ids=() if adjudication is None else tuple(str(item["finding_id"]) for item in adjudication.findings),
        repair_batch_id=repair_batch_id,
        receipt_id=receipt_id,
        consumption_id=consumption_id,
        durable_disposition=durable_disposition,
    )
    return _built(paths.HISTORY_RUNS, found)


def consumed_run_summary(
    sealed: records.GateGeneration,
    receipt: records.Receipt,
    consumption_id: str,
    *,
    candidate_generation: int | None,
    adjudication: records.P4Adjudication | None = None,
) -> RunSummary:
    """The Consumption-bound Run summary (§28.6): built before the Consumption, in its owner transition.

    ``consumption_id`` is the exact reserved Consumption ID; both records are
    first made canonical by the same transition. The Receipt must be the one
    ``sealed`` issued, for this Run, this generation and this Candidate.
    """
    _require(sealed.sealed and sealed.receipt_id == receipt.receipt_id,
             f"generation {sealed.generation} of {sealed.review_run_id} does not issue Receipt {receipt.receipt_id}")
    _require(
        (receipt.review_run_id, receipt.review_generation, receipt.authorized_candidate_hash)
        == (sealed.review_run_id, sealed.generation, sealed.candidate_hash),
        f"Receipt {receipt.receipt_id} is not the authorization of this Run's sealed Candidate",
    )
    _require(is_valid_id(consumption_id, "review_consumption"), f"not a review_consumption id: {consumption_id!r}")
    return run_summary(
        sealed, durable_disposition=DISPOSITION_CONSUMED, candidate_generation=candidate_generation,
        adjudication=adjudication, receipt_id=receipt.receipt_id, consumption_id=consumption_id,
    )


def set_aside_run_summary(
    latest: records.GateGeneration,
    *,
    candidate_generation: int | None,
    adjudication: records.P4Adjudication | None = None,
    repair_batch_id: str | None = None,
    receipt_id: str | None = None,
) -> RunSummary:
    """The ``set_aside`` Run summary of a predecessor whose chain ends at ``latest`` (§28.5).

    Only for a Run that has no final summary yet; the replacement transition
    that makes the set-aside canonical is the owner's to identify.
    """
    return run_summary(
        latest, durable_disposition=DISPOSITION_SET_ASIDE, candidate_generation=candidate_generation,
        adjudication=adjudication, repair_batch_id=repair_batch_id, receipt_id=receipt_id,
    )


def finding_summary(adjudication: records.P4Adjudication, finding_id: str,
                    relation_ids: Iterable[str] = ()) -> FindingSummary:
    """The summary of one normalized Finding of ``adjudication``, copied exactly from it (§28.8).

    ``relation_ids`` are the relations the same G4 accepted starting at this Finding (GAP-C), if any.
    """
    finding = adjudication.finding(finding_id)
    _require(finding is not None,
             f"the adjudication of {adjudication.review_run_id} holds no Finding {finding_id}; an unsupported, "
             "HUMAN or dismissed claim never becomes a Finding summary")
    assert finding is not None
    found = FindingSummary(
        finding_id=str(finding["finding_id"]),
        review_run_id=adjudication.review_run_id,
        candidate_hash=adjudication.candidate_hash,
        adjudication_digest=serialize.digest(adjudication.to_record()),
        source_report_digests=tuple(sorted({str(source["result_digest"]) for source in finding["sources"]})),
        category=str(finding["category"]),
        severity=str(finding["severity"]),
        semantic_surface=str(finding["semantic_surface"]),
        summary=str(finding["statement"]),
        disposition=str(finding["disposition"]),
        relation=str(finding["relation"]),
        linked_finding_ids=tuple(str(item) for item in finding["linked_finding_ids"]),
        linked_repair_batch_ids=tuple(str(item) for item in finding["linked_repair_batch_ids"]),
        causal_evidence_digest=finding["causal_evidence_digest"],
        relation_ids=tuple(sorted(set(relation_ids))),
    )
    return _built(paths.HISTORY_FINDINGS, found)


def finding_summaries(adjudication: records.P4Adjudication) -> tuple[FindingSummary, ...]:
    """One summary per normalized Finding of ``adjudication``, in its canonical Finding order (§28.8)."""
    return tuple(finding_summary(adjudication, str(item["finding_id"])) for item in adjudication.findings)


def repair_summary(
    adjudication: records.P4Adjudication,
    batch: records.P4RepairBatch,
    result: records.P4RepairResult,
    *,
    source_candidate_material_digest: str,
) -> RepairSummary:
    """The summary of one successful repair: its Repair Batch, its Repair Result and its source (§28.9).

    The three records must be one linkage - the batch of this adjudication's
    Run and Candidate, the result of this batch - or nothing is built.
    """
    _require(batch.repair_batch_id == result.repair_batch_id,
             f"Repair Result {result.repair_batch_id} is not of Repair Batch {batch.repair_batch_id}")
    _require(batch.source_review_run_id == result.source_review_run_id == adjudication.review_run_id,
             "the Repair Batch, its Result and the adjudication name different source Runs")
    _require(batch.source_candidate_hash == result.source_candidate_hash == adjudication.candidate_hash,
             "the Repair Batch, its Result and the adjudication name different source Candidates")
    _require(batch.adjudication_digest == serialize.digest(adjudication.to_record()),
             f"Repair Batch {batch.repair_batch_id} does not bind this adjudication")
    _require(result.successor_eligible is True,
             f"Repair Result {result.repair_batch_id} is not eligible to start a successor Run")
    decided: dict[str, list[str]] = {state: [] for state in records.P4_REUSE_STATES}
    for decision in result.evidence_decisions:
        decided[str(decision["state"])].append(str(decision["evidence_id"]))
    found = RepairSummary(
        repair_batch_id=batch.repair_batch_id,
        source_review_run_id=batch.source_review_run_id,
        source_candidate_hash=batch.source_candidate_hash,
        result_candidate_hash=result.result_candidate_hash,
        finding_ids=tuple(batch.finding_ids),
        semantic_surfaces=tuple(batch.semantic_surfaces),
        strategy=batch.strategy,
        strategy_change_class=batch.strategy_change_class,
        impact_class=result.impact_class,
        coverage_check_digest=result.coverage_check_digest,
        coverage_covers_affected_set=bool(result.coverage_check["covers_affected_set"]),
        coverage_repair_scope=str(result.coverage_check["repair_scope"]),
        evidence_reusable_ids=tuple(sorted(decided["reusable"])),
        evidence_unknown_ids=tuple(sorted(decided["unknown"])),
        evidence_invalidated_ids=tuple(sorted(decided["invalidated"])),
        repair_identity=result.repair_identity,
        repair_version=result.repair_version,
        durable_result=REPAIR_RESULT_SUCCESSOR_ELIGIBLE,
        batch_digest=serialize.digest(batch.to_record()),
        result_digest=serialize.digest(result.to_record()),
        causal_material=CausalMaterial(
            source_candidate_material_digest=source_candidate_material_digest,
            result_candidate_material_digest=result.result_candidate_material_digest,
            repaired_surface=tuple(result.repaired_surface),
            affected_surfaces=tuple(str(item) for item in result.coverage_check["affected_set"]),
            reverification_digest=result.reverification_digest,
            review_context_hash=adjudication.review_context_hash,
            effective_policy_hash=adjudication.effective_policy_hash,
        ),
    )
    return _built(paths.HISTORY_REPAIRS, found)


def endpoint(kind: str, identifier: str, *, basis: str, digest: str | None = None) -> Endpoint:
    """One relation endpoint, refused unless it is a well-formed one."""
    return Endpoint.from_record({"kind": kind, "id": identifier, "basis": basis, "digest": digest}, "the endpoint")


def relation(
    relation_id: str,
    relation_type: str,
    source: Endpoint,
    target: Endpoint,
    *,
    status: str,
    rationale: str,
    semantic_surface: str | None = None,
    supporting_evidence_digests: Iterable[str] = (),
) -> Relation:
    """One relation record under a reserved ``review_relation`` ID, refused unless it is a valid one."""
    found = Relation(
        relation_id=relation_id,
        relation_type=relation_type,
        source=source,
        target=target,
        semantic_surface=semantic_surface,
        status=status,
        supporting_evidence_digests=tuple(sorted(set(supporting_evidence_digests))),
        rationale=rationale,
    )
    return _built(paths.HISTORY_RELATIONS, found)


def future_work_link(
    relation_id: str,
    source_finding: FindingSummary,
    work_id: str,
    *,
    status: str,
    rationale: str,
    supporting_evidence_digests: Iterable[str] = (),
) -> Relation:
    """The shape of a ``future_work_link`` (§28.13): ``finding_id -> work_id``, provenance only.

    Bound to the exact P5 Finding summary it starts at. It adds the Work to no
    completion set, creates no reverse dependency and changes no selection; the
    Work itself is created only by the normal Work-creation owner.
    """
    return relation(
        relation_id, RELATION_FUTURE_WORK_LINK,
        endpoint(ENDPOINT_FINDING, source_finding.finding_id, basis=BASIS_HISTORY,
                 digest=serialize.digest(source_finding.to_record())),
        endpoint(ENDPOINT_WORK, work_id, basis=BASIS_PROJECT),
        status=status, rationale=rationale, supporting_evidence_digests=supporting_evidence_digests,
    )


def human_decision_evidence(
    review_decision_id: str,
    adjudication: records.P4Adjudication,
    *,
    decision_id: str,
    decision_disposition: str,
    affected_entries: Iterable[Mapping[str, Any]],
    affected_coverage_gaps: Iterable[Mapping[str, Any]] = (),
    question_summary: str,
    decision_summary: str,
    authority_identity: str,
    action_class: str,
    source_digests: Iterable[str],
    effect_digests: Iterable[str] = (),
) -> HumanDecisionEvidence:
    """The one Human Decision Evidence record of the HUMAN_WAIT Run ``adjudication`` settled (§28.14, GAP-G).

    ``review_decision_id`` is the replay-stable reservation under
    :func:`review_decision_key` of the affected Run; ``decision_id`` and
    ``decision_disposition`` are the caller's G-4 Human-decision input. Every
    reference must name a HUMAN entry or a HUMAN coverage gap of that
    adjudication, and the adjudication must have reached HUMAN_WAIT; anything
    else is refused before persistence - a detached evidence record is never
    built. The owner's own proofs (the Run's chain settled this adjudication,
    review kind / target compatibility, the decision input agreeing, the
    canonical authority reflecting a change, the set-aside of exactly this Run)
    are the owner's to make before any effect.
    """
    entries = sorted(
        ({name: item[name] for name in AFFECTED_ENTRY_FIELDS} for item in affected_entries),
        key=records._source_key,
    )
    gaps = sorted(({name: item[name] for name in AFFECTED_GAP_FIELDS} for item in affected_coverage_gaps),
                  key=lambda gap: (str(gap["task_id"]), str(gap["surface"])))
    problems = _human_reference_problems(adjudication, entries, gaps)
    _require(not problems, "; ".join(problems))
    found = HumanDecisionEvidence(
        review_decision_id=review_decision_id,
        decision_id=decision_id,
        decision_disposition=decision_disposition,
        affected_review_run_id=adjudication.review_run_id,
        affected_candidate_hash=adjudication.candidate_hash,
        affected_adjudication_digest=serialize.digest(adjudication.to_record()),
        affected_entries=tuple(entries),
        affected_coverage_gaps=tuple(gaps),
        question_summary=question_summary,
        decision_summary=decision_summary,
        authority_identity=authority_identity,
        action_class=action_class,
        source_digests=tuple(sorted(set(source_digests))),
        effect_digests=tuple(sorted(set(effect_digests))),
    )
    return _built(paths.HISTORY_HUMAN_DECISIONS, found)


def _human_reference_problems(
    adjudication: records.P4Adjudication, entries: Sequence[Mapping[str, Any]], gaps: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Every reference that does not name a real HUMAN part of ``adjudication``."""
    problems: list[str] = []
    if adjudication.outcome != records.HUMAN_WAIT:
        problems.append(f"the adjudication of {adjudication.review_run_id} is {adjudication.outcome}, not HUMAN_WAIT")
    by_source = {records._source_key(entry): entry for entry in adjudication.entries}
    for reference in entries:
        found = by_source.get(records._source_key(dict(reference)))
        if found is None or found["outcome"] != records.OUTCOME_HUMAN:
            problems.append(f"claim {reference['claim_index']} of {reference['task_id']} is not a HUMAN entry of "
                            f"the adjudication of {adjudication.review_run_id}")
    human_gaps = {(gap["task_id"], gap["surface"]) for gap in adjudication.coverage_gaps
                  if gap["resolution"] in HUMAN_GAP_RESOLUTIONS}
    for reference in gaps:
        if (reference["task_id"], reference["surface"]) not in human_gaps:
            problems.append(f"coverage gap {reference['surface']!r} of {reference['task_id']} is not a HUMAN coverage "
                            f"gap of the adjudication of {adjudication.review_run_id}")
    return problems


# --------------------------------------------------------------------------- cross-source validation (§28.17)
#
# Pure functions over any P1 reader that also reads history (``ReviewStore`` or one of its committed /
# resulting-tree readers). They report; they never repair, never write and never decide lifecycle.
# Nothing in the live gating validators calls them (GAP-B).

Problem = tuple[str, str]


def _code(exc: ValidationError) -> str:
    return getattr(exc, "code", None) or PROBLEM_INVALID


def _differences(found: Mapping[str, Any], expected: Mapping[str, Any]) -> list[str]:
    return sorted(key for key in set(found) | set(expected) if found.get(key) != expected.get(key))


def _bound_by_chain(reader: Any, review_run_id: str, adjudication_digest: str) -> bool | None:
    """Whether ``review_run_id``'s chain settled exactly that adjudication; ``None`` when no chain reads."""
    try:
        chain = reader.gate_chain(review_run_id)
    except ValidationError:
        return None
    if chain is None:
        return None
    return any(found.adjudication_digest == adjudication_digest for found in chain.generations)


def _discovery_generation(reader: Any, chain: Any) -> int | None:
    """The candidate generation the Run's generation-1 request binds, or ``None`` when it binds none."""
    for task in chain.generations[0].accepted_tasks:
        try:
            envelope = reader.read_task_input(str(task["task_id"])).request_envelope
        except ValidationError:
            return None
        found = envelope.get("candidate_generation")
        if type(found) is int:
            return found
    return None


def run_summary_problems(reader: Any, summary: RunSummary) -> list[Problem]:
    """Every way a Run summary disagrees with the Run's immutable gate chain, adjudication, Receipt and Consumption.

    Never "latest value wins": the summary must bind exactly where the chain
    ends, exactly what that generation says, exactly the adjudication and
    Findings the chain settled, the Receipt the chain issued, and the
    Consumption that consumed it - and its disposition must be one those
    sources positively show. A reserved disposition no canonical transition
    proves (``authorized``, ``historical_escape``) is refused here, never in the
    reader (GAP-F).
    """
    run = summary.review_run_id
    where = f"Run summary {run}"
    unproven: list[Problem] = []
    if not disposition_admitted(summary.durable_disposition):
        unproven.append((CODE_DISPOSITION_UNSUPPORTED,
                         f"{where} claims durable disposition {summary.durable_disposition!r}, and no canonical source "
                         "transition proves it final for a Run (GAP-F)"))
    return unproven + _run_source_problems(reader, summary, where)


def _run_source_problems(reader: Any, summary: RunSummary, where: str) -> list[Problem]:
    run = summary.review_run_id
    try:
        chain = reader.gate_chain(run)
    except ValidationError as exc:
        return [(_code(exc), f"{where}: the Run's gate chain does not read: {exc}")]
    if chain is None:
        return [(PROBLEM_MISSING, f"{where}: Review Run {run} has no gate chain")]
    problems: list[Problem] = []
    latest = chain.latest
    if (summary.gate_generation, summary.gate_digest) != (latest.generation, chain.latest_digest):
        problems.append((PROBLEM_CONFLICT,
                         f"{where} binds generation {summary.gate_generation} ({summary.gate_digest}), and the chain "
                         f"ends at generation {latest.generation} ({chain.latest_digest})"))
    for name in ("review_kind", "target_identity", "operation_identity", "candidate_hash", "review_context_hash",
                 "effective_policy_hash", "evidence_digest", "coverage_digest"):
        if getattr(summary, name) != getattr(latest, name):
            problems.append((PROBLEM_CONFLICT, f"{where} says {name} {getattr(summary, name)!r}, and the Run's "
                                               f"generation {latest.generation} says {getattr(latest, name)!r}"))
    adjudication = None
    try:
        if reader.adjudication_exists(run):
            adjudication = reader.read_adjudication(run)
            stored_digest = reader.adjudication_digest(run)
    except ValidationError as exc:
        return problems + [(_code(exc), f"{where}: the Run's adjudication does not read: {exc}")]
    bound = None
    if summary.adjudication_digest is not None:
        if adjudication is None:
            problems.append((PROBLEM_MISSING, f"{where} binds an adjudication, and none is stored for {run}"))
        elif stored_digest != summary.adjudication_digest:
            problems.append((PROBLEM_CONFLICT, f"{where} binds adjudication {summary.adjudication_digest}, and the "
                                               f"stored one digests to {stored_digest}"))
        elif not any(found.adjudication_digest == stored_digest for found in chain.generations):
            problems.append((PROBLEM_MISSING, f"{where} binds an adjudication the Run's chain never settled"))
        else:
            bound = adjudication
    elif adjudication is not None and any(found.adjudication_digest == stored_digest for found in chain.generations):
        problems.append((PROBLEM_CONFLICT, f"{where} binds no adjudication, and the Run's chain settled one"))
    expected_findings = () if bound is None else tuple(str(item["finding_id"]) for item in bound.findings)
    if summary.finding_ids != expected_findings:
        problems.append((PROBLEM_CONFLICT, f"{where} names Findings {list(summary.finding_ids)}, and the adjudication "
                                           f"it binds holds {list(expected_findings)}"))
    expected_generation = bound.candidate_generation if bound is not None else _discovery_generation(reader, chain)
    if summary.candidate_generation != expected_generation:
        problems.append((PROBLEM_CONFLICT, f"{where} says candidate generation {summary.candidate_generation}, and "
                                           f"its sources say {expected_generation}"))
    if summary.durable_disposition == DISPOSITION_HUMAN_WAIT and bound is not None \
            and bound.outcome != records.HUMAN_WAIT:
        problems.append((PROBLEM_CONFLICT, f"{where} is human_wait, and its adjudication is {bound.outcome}"))
    if summary.durable_disposition == DISPOSITION_NOT_AUTHORIZED and not any(
        task["status"] == records.TASK_SETTLED_FAILED for task in latest.settled_tasks
    ):
        # GAP-E: the canonical discovery settlement itself establishes the terminal non-authorizing fact.
        problems.append((PROBLEM_CONFLICT, f"{where} is not_authorized, and generation {latest.generation} settles no "
                                           "task as failed"))
    problems.extend(_run_authorization_problems(reader, summary, chain, where))
    problems.extend(_run_repair_problems(reader, summary, where))
    return problems


def _run_authorization_problems(reader: Any, summary: RunSummary, chain: Any, where: str) -> list[Problem]:
    """The Receipt the chain issued, its Consumption, and its Supersession, against what the summary says."""
    problems: list[Problem] = []
    issued = [found.receipt_id for found in chain.generations if found.receipt_id is not None]
    expected_receipt = issued[-1] if issued else None
    if summary.receipt_id != expected_receipt:
        problems.append((PROBLEM_CONFLICT, f"{where} names Receipt {summary.receipt_id}, and the chain's last issued "
                                           f"Receipt is {expected_receipt}"))
    if summary.receipt_id is not None:
        try:
            receipt = reader.read_receipt(summary.receipt_id)
        except ValidationError as exc:
            return problems + [(_code(exc), f"{where}: Receipt {summary.receipt_id} does not read: {exc}")]
        if (receipt.review_run_id, receipt.authorized_candidate_hash) != (summary.review_run_id, summary.candidate_hash):
            problems.append((PROBLEM_CONFLICT, f"{where}: Receipt {summary.receipt_id} authorizes another Run or "
                                               "Candidate"))
    try:
        consumed = None if summary.receipt_id is None else reader.consumption_by_receipt().get(summary.receipt_id)
    except ValidationError as exc:
        return problems + [(_code(exc), f"{where}: the Consumptions do not read: {exc}")]
    if consumed is not None and consumed.consumption_id != summary.consumption_id:
        problems.append((PROBLEM_CONFLICT, f"{where} is {summary.durable_disposition}, and its Receipt "
                                           f"{summary.receipt_id} is consumed by {consumed.consumption_id}"))
    if summary.consumption_id is not None:
        try:
            consumption = reader.read_consumption(summary.consumption_id)
        except ValidationError as exc:
            return problems + [(_code(exc), f"{where}: Consumption {summary.consumption_id} does not read: {exc}")]
        if (consumption.receipt_id, consumption.review_run_id, consumption.authorized_candidate_hash) != (
            summary.receipt_id, summary.review_run_id, summary.candidate_hash
        ):
            problems.append((PROBLEM_CONFLICT, f"{where}: Consumption {summary.consumption_id} does not consume its "
                                               "Receipt for its Run and Candidate"))
    if summary.durable_disposition == DISPOSITION_INVALIDATED and summary.receipt_id is not None:
        try:
            superseded = reader.supersession_exists(summary.receipt_id)
        except ValidationError as exc:
            return problems + [(_code(exc), f"{where}: the Supersession does not read: {exc}")]
        if not superseded:
            problems.append((PROBLEM_MISSING, f"{where} is invalidated, and no Supersession of Receipt "
                                              f"{summary.receipt_id} is stored"))
    return problems


def _run_repair_problems(reader: Any, summary: RunSummary, where: str) -> list[Problem]:
    if summary.repair_batch_id is None:
        return []
    batch_id = summary.repair_batch_id
    try:
        if not reader.repair_batch_exists(batch_id):
            return [(PROBLEM_MISSING, f"{where} names Repair Batch {batch_id}, which is not stored")]
        batch = reader.read_repair_batch(batch_id)
        has_result = reader.repair_result_exists(batch_id)
    except ValidationError as exc:
        return [(_code(exc), f"{where}: Repair Batch {batch_id} does not read: {exc}")]
    problems: list[Problem] = []
    if (batch.source_review_run_id, batch.source_candidate_hash) != (summary.review_run_id, summary.candidate_hash):
        problems.append((PROBLEM_CONFLICT, f"{where}: Repair Batch {batch_id} is not of this Run's Candidate"))
    if summary.durable_disposition == DISPOSITION_REPAIRED and not has_result:
        problems.append((PROBLEM_MISSING, f"{where} is {DISPOSITION_REPAIRED}, and Repair Batch {batch_id} has no "
                                          "stored Repair Result"))
    return problems


def finding_summary_problems(reader: Any, summary: FindingSummary) -> list[Problem]:
    """Every way a Finding summary disagrees with the canonical P4 adjudication Finding it summarizes."""
    run = summary.review_run_id
    where = f"Finding summary {summary.finding_id}"
    try:
        if not reader.adjudication_exists(run):
            return [(PROBLEM_MISSING, f"{where}: Review Run {run} has no stored adjudication")]
        adjudication = reader.read_adjudication(run)
        stored_digest = reader.adjudication_digest(run)
    except ValidationError as exc:
        return [(_code(exc), f"{where}: the adjudication of {run} does not read: {exc}")]
    if stored_digest != summary.adjudication_digest:
        return [(PROBLEM_CONFLICT, f"{where} binds adjudication {summary.adjudication_digest}, and the stored one "
                                   f"digests to {stored_digest}")]
    if _bound_by_chain(reader, run, stored_digest) is not True:
        return [(PROBLEM_MISSING, f"{where}: the chain of {run} never settled the adjudication it summarizes")]
    try:
        expected = finding_summary(adjudication, summary.finding_id, summary.relation_ids)
    except ValidationError as exc:
        return [(PROBLEM_CONFLICT, f"{where}: {exc}")]
    problems: list[Problem] = []
    differ = _differences(summary.to_record(), expected.to_record())
    if differ:
        problems.append((PROBLEM_CONFLICT, f"{where} disagrees with its adjudication Finding in {', '.join(differ)}"))
    for digest in summary.source_report_digests:
        try:
            if not reader.report_exists(digest):
                problems.append((PROBLEM_MISSING, f"{where}: source report {digest} is not stored"))
        except ValidationError as exc:
            problems.append((_code(exc), f"{where}: source report {digest} does not read: {exc}"))
    for relation_id in summary.relation_ids:
        found, missing = _read_family(reader, paths.HISTORY_RELATIONS, relation_id, where)
        problems.extend(missing)
        if found is not None and found.source.identity != (ENDPOINT_FINDING, summary.finding_id):
            problems.append((PROBLEM_CONFLICT, f"{where} names relation {relation_id}, which does not start at it"))
    return problems


def repair_summary_problems(reader: Any, summary: RepairSummary) -> list[Problem]:
    """Every way a Repair summary disagrees with its Repair Batch, Repair Result and source records."""
    batch_id = summary.repair_batch_id
    where = f"Repair summary {batch_id}"
    try:
        if not reader.repair_batch_exists(batch_id):
            return [(PROBLEM_MISSING, f"{where}: Repair Batch {batch_id} is not stored")]
        if not reader.repair_result_exists(batch_id):
            return [(PROBLEM_MISSING, f"{where}: Repair Batch {batch_id} has no stored Repair Result")]
        batch = reader.read_repair_batch(batch_id)
        result = reader.read_repair_result(batch_id)
        source_run = batch.source_review_run_id
        if not reader.adjudication_exists(source_run):
            return [(PROBLEM_MISSING, f"{where}: source Run {source_run} has no stored adjudication")]
        adjudication = reader.read_adjudication(source_run)
        if not reader.candidate_snapshot_exists(batch.source_candidate_hash):
            return [(PROBLEM_MISSING, f"{where}: source Candidate {batch.source_candidate_hash} is not stored")]
        material = reader.candidate_material_digest(batch.source_candidate_hash)
        stored = (reader.repair_batch_digest(batch_id), reader.repair_result_digest(batch_id))
    except ValidationError as exc:
        return [(_code(exc), f"{where}: its source records do not read: {exc}")]
    problems: list[Problem] = []
    if (summary.batch_digest, summary.result_digest) != stored:
        problems.append((PROBLEM_CONFLICT, f"{where} binds batch / result digests that are not the stored records'"))
    try:
        expected = repair_summary(adjudication, batch, result, source_candidate_material_digest=material)
    except ValidationError as exc:
        return problems + [(PROBLEM_CONFLICT, f"{where}: {exc}")]
    differ = _differences(summary.to_record(), expected.to_record())
    if differ:
        problems.append((PROBLEM_CONFLICT, f"{where} disagrees with its Repair Batch / Result in {', '.join(differ)}"))
    return problems


def _endpoint_problems(reader: Any, found: Endpoint, where: str, work_ids: Collection[str] | None) -> list[Problem]:
    """Whether the record an endpoint names exists, and is the exact record its digest names."""
    if found.kind == ENDPOINT_WORK:
        if work_ids is not None and found.id not in work_ids:
            return [(PROBLEM_MISSING, f"{where} names Work {found.id}, which this Project does not hold")]
        return []
    family = {ENDPOINT_RUN: paths.HISTORY_RUNS, ENDPOINT_FINDING: paths.HISTORY_FINDINGS,
              ENDPOINT_REPAIR: paths.HISTORY_REPAIRS}[found.kind]
    try:
        if found.basis == BASIS_HISTORY:
            if not reader.history_exists(family, found.id):
                return [(PROBLEM_MISSING, f"{where} names the {family} history record {found.id}, which is not stored")]
            digests = {reader.history_digest(family, found.id)}
        elif found.kind == ENDPOINT_RUN:
            chain = reader.gate_chain(found.id)
            if chain is None:
                return [(PROBLEM_MISSING, f"{where} names Review Run {found.id}, which has no gate chain")]
            digests = set(chain.digests)
        elif found.kind == ENDPOINT_REPAIR:
            if not reader.repair_batch_exists(found.id):
                return [(PROBLEM_MISSING, f"{where} names Repair Batch {found.id}, which is not stored")]
            digests = {reader.repair_batch_digest(found.id)}
        else:
            digests = {
                reader.adjudication_digest(run) for run in reader.adjudication_run_ids()
                if reader.read_adjudication(run).finding(found.id) is not None
            }
            if not digests:
                return [(PROBLEM_MISSING, f"{where} names Finding {found.id}, which no stored adjudication holds")]
    except ValidationError as exc:
        return [(_code(exc), f"{where}: the record it names does not read: {exc}")]
    if found.digest not in digests:
        return [(PROBLEM_CONFLICT, f"{where} binds digest {found.digest}, which is not the {found.basis} record of "
                                   f"{found.kind} {found.id}")]
    return []


def relation_problems(reader: Any, found: Relation, *, work_ids: Collection[str] | None) -> list[Problem]:
    """Whether both endpoints of a relation exist as the exact records it binds (§28.17).

    ``work_ids`` is the Work set of the Project the reader belongs to, or
    ``None`` from a reader that has no Project view, which then leaves a Work
    endpoint unchecked rather than guessing.
    """
    where = f"relation {found.relation_id}"
    return (_endpoint_problems(reader, found.source, f"{where} source", work_ids)
            + _endpoint_problems(reader, found.target, f"{where} target", work_ids))


def duplicate_relation_problems(found: Iterable[Relation]) -> list[Problem]:
    """Two relation records that say the same thing - one type between one source and one target."""
    seen: dict[Any, str] = {}
    problems: list[Problem] = []
    for item in sorted(found, key=lambda relation_record: relation_record.relation_id):
        first = seen.setdefault(item.logical_identity, item.relation_id)
        if first != item.relation_id:
            problems.append((PROBLEM_CONFLICT, f"relations {first} and {item.relation_id} are one logical relation "
                                               f"({item.relation_type} {item.source.id} -> {item.target.id})"))
    return problems


def human_decision_problems(reader: Any, evidence: HumanDecisionEvidence) -> list[Problem]:
    """Whether Human Decision Evidence points at a real HUMAN part of the G4 HUMAN_WAIT its Run's chain settled."""
    run = evidence.affected_review_run_id
    where = f"Human Decision Evidence {evidence.review_decision_id}"
    try:
        if not reader.adjudication_exists(run):
            return [(PROBLEM_MISSING, f"{where}: affected Run {run} has no stored adjudication")]
        adjudication = reader.read_adjudication(run)
        stored_digest = reader.adjudication_digest(run)
    except ValidationError as exc:
        return [(_code(exc), f"{where}: the adjudication of {run} does not read: {exc}")]
    if stored_digest != evidence.affected_adjudication_digest:
        return [(PROBLEM_CONFLICT, f"{where} binds adjudication {evidence.affected_adjudication_digest}, and the "
                                   f"stored one digests to {stored_digest}")]
    if _bound_by_chain(reader, run, stored_digest) is not True:
        return [(PROBLEM_MISSING, f"{where}: the chain of {run} never settled the adjudication it points at")]
    problems: list[Problem] = []
    if adjudication.candidate_hash != evidence.affected_candidate_hash:
        problems.append((PROBLEM_CONFLICT, f"{where} names Candidate {evidence.affected_candidate_hash}, and the "
                                           f"adjudication is of {adjudication.candidate_hash}"))
    for message in _human_reference_problems(adjudication, evidence.affected_entries, evidence.affected_coverage_gaps):
        problems.append((PROBLEM_CONFLICT, f"{where}: {message}"))
    return problems


def duplicate_decision_problems(found: Iterable[HumanDecisionEvidence]) -> list[Problem]:
    """Two Human Decision Evidence records for one affected Run: there is exactly one per affected Run (GAP-G)."""
    seen: dict[str, str] = {}
    problems: list[Problem] = []
    for item in sorted(found, key=lambda evidence: evidence.review_decision_id):
        first = seen.setdefault(item.affected_review_run_id, item.review_decision_id)
        if first != item.review_decision_id:
            problems.append((PROBLEM_CONFLICT, f"Human Decision Evidence {first} and {item.review_decision_id} both "
                                               f"name affected Run {item.affected_review_run_id}"))
    return problems


@dataclass(frozen=True)
class LoadedHistory:
    """Every history record one reader holds, by family and identity, and the problems reading them."""

    records: Mapping[str, Mapping[str, Any]]
    problems: tuple[Problem, ...]


def load_history(reader: Any) -> LoadedHistory:
    """Read every history record through the reader's strict per-family readers; structural only."""
    found: dict[str, dict[str, Any]] = {family: {} for family in paths.HISTORY_FAMILIES}
    problems: list[Problem] = []
    for family in paths.HISTORY_FAMILIES:
        try:
            identifiers = reader.history_ids(family)
        except ValidationError as exc:
            problems.append((_code(exc), str(exc)))
            continue
        for identifier in identifiers:
            try:
                found[family][identifier] = reader.read_history(family, identifier)
            except ValidationError as exc:
                problems.append((_code(exc), str(exc)))
    return LoadedHistory(found, tuple(problems))


def history_problems(reader: Any, *, work_ids: Collection[str] | None) -> list[Problem]:
    """§28.17 over every history record ``reader`` holds: each on its own, and against its immutable source.

    A pure function. It is not part of :func:`workline.review.validate.review_problems`,
    of any closed-namespace reader, of any readiness gate or of any operation:
    a broken history record never changes lifecycle truth, and where it is
    reported is an owner decision (GAP-B). An absent history namespace is
    valid, with no problem (pre-P5).
    """
    loaded = load_history(reader)
    problems = list(loaded.problems)
    for summary in loaded.records[paths.HISTORY_RUNS].values():
        problems.extend(run_summary_problems(reader, summary))
    for summary in loaded.records[paths.HISTORY_FINDINGS].values():
        problems.extend(finding_summary_problems(reader, summary))
    for summary in loaded.records[paths.HISTORY_REPAIRS].values():
        problems.extend(repair_summary_problems(reader, summary))
    relations = list(loaded.records[paths.HISTORY_RELATIONS].values())
    for found in relations:
        problems.extend(relation_problems(reader, found, work_ids=work_ids))
    problems.extend(duplicate_relation_problems(relations))
    decisions = list(loaded.records[paths.HISTORY_HUMAN_DECISIONS].values())
    for evidence in decisions:
        problems.extend(human_decision_problems(reader, evidence))
    problems.extend(duplicate_decision_problems(decisions))
    return problems


def confirmed_relations(found: Iterable[Relation]) -> tuple[Relation, ...]:
    """The relations that may feed confirmed recurrence / causality metrics: ``supported`` only (§28.22)."""
    return tuple(item for item in found if item.confirmed)


# --------------------------------------------------------------------------- readiness (§28.18, §28.20)

def _read_family(reader: Any, family: str, identifier: str, where: str) -> tuple[Any, list[Problem]]:
    try:
        if not reader.history_exists(family, identifier):
            return None, [(PROBLEM_MISSING, f"{where}: the {family} history record {identifier} is not canonical")]
        return reader.read_history(family, identifier), []
    except ValidationError as exc:
        return None, [(_code(exc), f"{where}: the {family} history record {identifier} does not read: {exc}")]


def readiness_problems(
    reader: Any,
    review_run_id: str,
    boundary: str,
    *,
    history_contract: str | None,
    review_decision_ids: Sequence[str] = (),
    consumption_id: str | None = None,
) -> list[Problem]:
    """What keeps ``review_run_id`` from crossing ``boundary`` with its required history (§28.18).

    ``history_contract`` is the history contract the Run's own stored request
    binds, as the owner's contract dispatch read it. ``None`` is a pre-P5 Run:
    history is ``not_required_by_contract``, and nothing is required - never
    because a history directory happens to exist or not (§28.2, §28.20).

    ```text
    g4_findings       every normalized Finding of the Run's adjudication has its summary
    human_wait        the Run's human_wait summary
    repaired_g6       the Run's repaired summary and the Repair summary of its batch
    successor_launch  the Human Decision Evidence ``review_decision_ids`` names
    consumption       the Run's consumed summary, naming ``consumption_id`` when given
    ```
    """
    if boundary not in BOUNDARIES:
        raise ValueError(f"not a P5 history boundary: {boundary!r}")
    if history_contract is None:
        return []
    where = f"Review Run {review_run_id} at {boundary}"
    if history_contract != HISTORY_CONTRACT:
        return [("review_record_version",
                 f"{where} binds history contract {history_contract!r}, which this build does not implement")]
    if boundary == BOUNDARY_FINDINGS:
        try:
            adjudication = reader.read_adjudication(review_run_id)
        except ValidationError as exc:
            return [(_code(exc), f"{where}: the Run's adjudication does not read: {exc}")]
        problems: list[Problem] = []
        for item in adjudication.findings:
            summary, missing = _read_family(reader, paths.HISTORY_FINDINGS, str(item["finding_id"]), where)
            problems.extend(missing)
            if summary is not None:
                problems.extend(finding_summary_problems(reader, summary))
                for relation_id in summary.relation_ids:
                    # GAP-C: the relations this G4 accepted are validated end to end before the G4 is history-complete
                    found, _ = _read_family(reader, paths.HISTORY_RELATIONS, relation_id, where)
                    if found is not None:
                        problems.extend(relation_problems(reader, found, work_ids=None))
        return problems
    if boundary == BOUNDARY_SUCCESSOR_LAUNCH:
        if not review_decision_ids:
            return [(PROBLEM_MISSING, f"{where}: no Human Decision Evidence is named for the decision it resumes under")]
        problems = []
        for review_decision_id in review_decision_ids:
            evidence, missing = _read_family(reader, paths.HISTORY_HUMAN_DECISIONS, review_decision_id, where)
            problems.extend(missing)
            if evidence is not None:
                problems.extend(human_decision_problems(reader, evidence))
        return problems
    expected = {
        BOUNDARY_HUMAN_WAIT: DISPOSITION_HUMAN_WAIT,
        BOUNDARY_REPAIRED: DISPOSITION_REPAIRED,
        BOUNDARY_CONSUMPTION: DISPOSITION_CONSUMED,
    }[boundary]
    summary, missing = _read_family(reader, paths.HISTORY_RUNS, review_run_id, where)
    if summary is None:
        return missing
    problems = list(run_summary_problems(reader, summary))
    if summary.durable_disposition != expected:
        problems.append((PROBLEM_CONFLICT, f"{where}: the Run summary is {summary.durable_disposition}, not {expected}"))
    if boundary == BOUNDARY_CONSUMPTION and consumption_id is not None and summary.consumption_id != consumption_id:
        problems.append((PROBLEM_CONFLICT, f"{where}: the Run summary names Consumption {summary.consumption_id}, not "
                                           f"{consumption_id}"))
    if boundary == BOUNDARY_REPAIRED and summary.repair_batch_id is not None:
        repair, missing = _read_family(reader, paths.HISTORY_REPAIRS, summary.repair_batch_id, where)
        problems.extend(missing)
        if repair is not None:
            problems.extend(repair_summary_problems(reader, repair))
    return problems


def history_status(problems: Sequence[Problem], *, history_contract: str | None) -> str:
    """``not_required_by_contract`` for a pre-P5 Run; otherwise ``complete`` exactly when nothing is missing or wrong."""
    if history_contract is None:
        return HISTORY_NOT_REQUIRED
    return HISTORY_INCOMPLETE if problems else HISTORY_COMPLETE


def require_history_ready(
    reader: Any,
    review_run_id: str,
    boundary: str,
    *,
    history_contract: str | None,
    review_decision_ids: Sequence[str] = (),
    consumption_id: str | None = None,
) -> None:
    """Refuse to let a P5-capable Run cross ``boundary`` over missing or invalid required history (§28.17).

    The narrow check an owner makes before such a transition; a pre-P5 Run
    passes by its explicit contract. Nothing is written, retried or repaired.
    """
    problems = readiness_problems(reader, review_run_id, boundary, history_contract=history_contract,
                                  review_decision_ids=review_decision_ids, consumption_id=consumption_id)
    if not problems:
        return
    detail = "; ".join(message for _, message in problems)
    if any(code == PROBLEM_MISSING for code, _ in problems):
        raise stop(CODE_HISTORY_MISSING, f"required P5 history is not canonical: {detail}; nothing proceeds")
    raise stop(CODE_HISTORY_INVALID, f"required P5 history does not validate against its source: {detail}; "
                                     "nothing proceeds")


# --------------------------------------------------------------------------- RB5 handoff (§13.14, §28.21, P-13)

@dataclass(frozen=True)
class RB5Reference:
    """The narrow, validated reference projection of one Review Run that RB5 may cite (§28.21).

    References only. It decides no achievement, and for a pre-P5 Run it carries
    the P1 references with no history (no backfill).
    """

    review_run_id: str
    history_status: str
    run_summary_digest: str | None
    durable_disposition: str | None
    receipt_id: str | None
    consumption_id: str | None
    unresolved_obligations: int | None
    evidence_digest: str
    coverage_digest: str
    finding_dispositions: tuple[tuple[str, str], ...]
    human_decision_evidence_ids: tuple[str, ...]

    def to_record(self) -> dict[str, Any]:
        return {
            "review_run_id": self.review_run_id,
            "history_status": self.history_status,
            "run_summary_digest": self.run_summary_digest,
            "durable_disposition": self.durable_disposition,
            "receipt_id": self.receipt_id,
            "consumption_id": self.consumption_id,
            "unresolved_obligations": self.unresolved_obligations,
            "evidence_digest": self.evidence_digest,
            "coverage_digest": self.coverage_digest,
            "finding_dispositions": [
                {"finding_id": finding_id, "disposition": disposition}
                for finding_id, disposition in self.finding_dispositions
            ],
            "human_decision_evidence_ids": list(self.human_decision_evidence_ids),
        }


def rb5_reference(reader: Any, review_run_id: str, *, history_contract: str | None) -> RB5Reference:
    """The RB5 reference of ``review_run_id``: P1 references always, history references only once validated.

    Pure: it reads and validates, and decides nothing. The Receipt and
    Consumption are the chain's own (the authority); the Run summary, Finding
    dispositions and Human Decision Evidence are exposed only when the Run's
    history is ``complete``.
    """
    chain = reader.gate_chain(review_run_id)
    if chain is None:
        raise ValidationError(f"Review Run {review_run_id} has no gate chain", code=PROBLEM_MISSING)
    issued = [found.receipt_id for found in chain.generations if found.receipt_id is not None]
    receipt_id = issued[-1] if issued else None
    receipt = None if receipt_id is None else reader.read_receipt(receipt_id)
    consumed = None if receipt_id is None else reader.consumption_by_receipt().get(receipt_id)
    problems: list[Problem] = []
    summary = None
    findings: tuple[tuple[str, str], ...] = ()
    decisions: tuple[str, ...] = ()
    if history_contract is not None:
        if history_contract != HISTORY_CONTRACT:
            problems.append(("review_record_version", f"history contract {history_contract!r} is not implemented"))
        else:
            summary, problems = _read_family(reader, paths.HISTORY_RUNS, review_run_id, f"Review Run {review_run_id}")
            if summary is not None:
                problems.extend(run_summary_problems(reader, summary))
                found_findings = []
                for finding_id in summary.finding_ids:
                    finding, missing = _read_family(reader, paths.HISTORY_FINDINGS, finding_id, "the RB5 reference")
                    problems.extend(missing)
                    if finding is not None:
                        problems.extend(finding_summary_problems(reader, finding))
                        found_findings.append((finding.finding_id, finding.disposition))
                findings = tuple(found_findings)
                loaded = load_history(reader)
                problems.extend(loaded.problems)
                affected = sorted(
                    review_decision_id
                    for review_decision_id, evidence in loaded.records[paths.HISTORY_HUMAN_DECISIONS].items()
                    if evidence.affected_review_run_id == review_run_id
                )
                for review_decision_id in affected:
                    problems.extend(human_decision_problems(
                        reader, loaded.records[paths.HISTORY_HUMAN_DECISIONS][review_decision_id]
                    ))
                decisions = tuple(affected)
    status = history_status(problems, history_contract=history_contract)
    complete = status == HISTORY_COMPLETE
    return RB5Reference(
        review_run_id=review_run_id,
        history_status=status,
        run_summary_digest=reader.history_digest(paths.HISTORY_RUNS, review_run_id) if complete else None,
        durable_disposition=summary.durable_disposition if complete and summary is not None else None,
        receipt_id=receipt_id,
        consumption_id=None if consumed is None else consumed.consumption_id,
        unresolved_obligations=None if receipt is None else receipt.unresolved_obligations,
        evidence_digest=chain.latest.evidence_digest,
        coverage_digest=chain.latest.coverage_digest,
        finding_dispositions=findings if complete else (),
        human_decision_evidence_ids=decisions if complete else (),
    )
