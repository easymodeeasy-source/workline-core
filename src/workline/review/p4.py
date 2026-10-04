"""P4 (``WORKLINE_COMPLETION_SPRINT`` §12 / §27): the common semantic core of the current-cycle Repair Loop.

Inert, exactly as :mod:`workline.review.closure` is: no Project lock, no
mutation, no filesystem write, no Git finalization and no lifecycle
transition. The operation owners (:mod:`workline.roadmap_review`,
:mod:`workline.start_review`) open every mutation and write every record; the
kind modules (:mod:`workline.review.planning`, :mod:`workline.review.work_review`)
own the kind-specific Candidate material. What this module fixes is the meaning
that is common to both kinds:

```text
identities     the P4 contracts, policy, instructions, task kinds and slots (§27.3)
selector       actor bindings: discovery actor(s), one adjudicator, one repair actor (§27.3)
shape          G1 discovery accept .. G6 repair settle / invalidate, no G7 (§12.6, §27.1, G-3)
reports        H-3 public-safe discovery reports (§12.3, §27.4, §27.9)
adjudication   the §12.4 order, normalized Findings, merge by repair identity (§12.5, §27.6-§27.11)
outcome        AUTHORIZATION_READY | REPAIR_REQUIRED | HUMAN_WAIT by obligations (§12.18, §27.11)
repair         one Repair Batch per Candidate generation, coverage, impact, reverification (§12.8-§12.15)
relations      A_NEW / B_RECURRENCE / C_REPAIR_INDUCED and STRATEGY_CHANGE (§12.16-§12.17)
Evidence       positive-proof reuse over the closure vocabulary, never closure.may_reuse (§12.13, §27.18)
Integration    the verification-only side-effect contract (§12.20, §27.25)
linkage        Repair Result <-> Candidate N+1 <-> successor request (§12.10-§12.11, §27.20-§27.21, G-1, G-2)
```

The codes and reasons this module builds are the P4 catalogue: they are raised
by the owners through :func:`stop` and :func:`reconcile`, so the P2 catalogue of
the P2 modules is left exactly as P2 drew it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..errors import ReconcileRequired, StopError, ValidationError
from ..ids import is_valid_id
from . import closure, records, serialize
from .records import (
    AUTHORIZATION_READY,
    DISPOSITION_FUTURE_WORK_CANDIDATE,
    DISPOSITION_NO_ACTION,
    DISPOSITION_REPAIR_REQUIRED,
    DISPOSITION_REPAIRED_CURRENT_CYCLE,
    DISPOSITION_RETAINED_HISTORY_ONLY,
    GAP_COVERED,
    GAP_HUMAN,
    GAP_NOT_APPLICABLE,
    GAP_TARGETED_CHECK,
    HUMAN_WAIT,
    IMPACT_CONTRACT,
    IMPACT_FOUNDATION,
    IMPACT_LOCAL,
    IMPACT_SHARED,
    OUTCOME_DISMISSED,
    OUTCOME_HUMAN,
    OUTCOME_IMPROVEMENT,
    OUTCOME_PROBLEM,
    OUTCOME_UNSUPPORTED,
    P4_CATEGORIES,
    P4_CONTRACTS,
    P4_DISCOVERY_SLOT_PREFIX,
    P4_DISPOSITIONS,
    P4_GAP_RESOLUTIONS,
    P4_IMPACT_CLASSES,
    P4_NONBLOCKING_DISPOSITIONS,
    P4_OUTCOMES,
    P4_PLANNING_CONTRACT,
    P4_RELATIONS,
    P4_REPAIR_SCOPES,
    P4_SEVERITIES,
    P4_SEVERITY_RANK,
    P4_STRATEGY_CHANGE_CLASSES,
    P4_WORK_CONTRACT,
    RELATION_A_NEW,
    RELATION_B_RECURRENCE,
    RELATION_C_REPAIR_INDUCED,
    REPAIR_REQUIRED,
    STRATEGY_CHANGE,
    STRATEGY_ORDINARY,
    public_safe_problem,
)

# --------------------------------------------------------------------------- identities (§27.3, G-6, G-7)

#: The planning P4 Review contract: distinct from ``review-v1-planning-v1`` and recorded as the planning
#: owner's durable marker from the first owner write (G-6 Option M).
PLANNING_CONTRACT = P4_PLANNING_CONTRACT
#: The Work P4 Review contract: distinct from ``review-v1-work-v1`` (P3 / F4) and recorded as the START
#: owner's durable marker from the first owner write (G-6 Option M).
WORK_CONTRACT = P4_WORK_CONTRACT
CONTRACTS = P4_CONTRACTS

#: The one P4 Effective Policy (§12.21): distinct from both v1 policies, and the same for every P4 kind.
POLICY_ID = "review-v1-p4-policy-v1"
DISCOVERY_INSTRUCTION = "review-v1-p4-discovery-instruction-v1"
ADJUDICATION_INSTRUCTION = "review-v1-p4-adjudication-instruction-v1"
REPAIR_INSTRUCTION = "review-v1-p4-repair-instruction-v1"
ADJUDICATION_CONTRACT = "review-v1-p4-adjudication-v1"

TASK_KIND_DISCOVERY = "p4-discovery-v1"
TASK_KIND_ADJUDICATION = "p4-adjudication-v1"
TASK_KIND_REPAIR = "p4-repair-v1"
SLOT_ADJUDICATOR = "p4-adjudicator"
SLOT_REPAIR = "p4-repair"

SCHEMA_POLICY = "review-p4-policy"
SCHEMA_DISCOVERY_REQUEST = "review-p4-discovery-request"
SCHEMA_ADJUDICATION_REQUEST = "review-p4-adjudication-request"
SCHEMA_REPAIR_REQUEST = "review-p4-repair-request"
SCHEMA_COVERAGE = "review-p4-coverage"
SCHEMA_REPORT_SET = "review-p4-report-set"
SCHEMA_ADJUDICATION_PENDING = "review-p4-adjudication-pending"
SCHEMA_OBLIGATIONS = "review-p4-obligations"
SCHEMA_INVALIDATION_EVIDENCE = "review-p4-invalidation-evidence"
SCHEMA_REQUIREMENT = "review-p4-requirement"
SCHEMA_HUMAN_DECISION = "review-p4-human-decision"
RECORD_VERSION = 1
REQUEST_SCHEMAS = (SCHEMA_DISCOVERY_REQUEST, SCHEMA_ADJUDICATION_REQUEST, SCHEMA_REPAIR_REQUEST)

# --------------------------------------------------------------------------- generations (§12.6, §27.1, G-3)

DISCOVERY_ACCEPT_GENERATION = 1
DISCOVERY_SETTLE_GENERATION = 2
ADJUDICATION_ACCEPT_GENERATION = 3
ADJUDICATION_SETTLE_GENERATION = 4
#: The generation of a P4 Run that seals, and the only one that issues a Receipt (§27.12).
SEAL_GENERATION = 5
REPAIR_ACCEPT_GENERATION = 5
REPAIR_SETTLE_GENERATION = 6
#: The invalidation of a stale sealed P4 Run (G-3): open, superseding the generation-5 Receipt.
INVALIDATION_GENERATION = 6
#: No G7 exists within one Candidate-specific P4 Run (§27.31).
LAST_GENERATION = 6

TRANSITION_ACCEPT = "accept"
TRANSITION_SETTLE = "settle"
TRANSITION_SEAL = "seal"
TRANSITION_INVALIDATE = "invalidate"
#: The P4 transition map, kept apart from the pinned v1 maps. Generation 5 and 6 each have two shapes;
#: which one a stored generation is, is read from its canonical records (§27.31, G-3), never from its
#: number alone.
TRANSITIONS: Mapping[int, tuple[str, ...]] = {
    1: (TRANSITION_ACCEPT,),
    2: (TRANSITION_SETTLE,),
    3: (TRANSITION_ACCEPT,),
    4: (TRANSITION_SETTLE,),
    5: (TRANSITION_SEAL, TRANSITION_ACCEPT),
    6: (TRANSITION_SETTLE, TRANSITION_INVALIDATE),
}

#: Why a P4 owner names an older Run in its successor request's ``set_aside_runs``.
SET_ASIDE_REPAIRED = "p4_repaired"
SET_ASIDE_HUMAN_DECISION = "human_decision"
SET_ASIDE_INVALIDATED = "p4_invalidated"
SET_ASIDE_REASONS = (SET_ASIDE_REPAIRED, SET_ASIDE_HUMAN_DECISION, SET_ASIDE_INVALIDATED)

#: The stable reason a P4 G6 invalidation records on its Supersession (G-3).
INVALIDATION_STALE_RECEIPT = "p4_receipt_stale"

#: The G-4 Human-decision dispositions.
DECISION_CONFIRMED = "requirement_confirmed"
DECISION_CHANGED = "requirement_changed"
DECISION_DISPOSITIONS = (DECISION_CONFIRMED, DECISION_CHANGED)

# --------------------------------------------------------------------------- the P4 catalogue (P-5)

#: P4 STOP codes. Each is raised through :func:`stop`, named in the review / roadmap / start Skills, and
#: pinned by the P4 catalogue test; none is a P2 catalogue name.
CODE_HUMAN_WAIT = "review_p4_human_wait"
CODE_ADJUDICATION_INVALID = "review_p4_adjudication_invalid"
CODE_ADJUDICATOR_FAILED = "review_p4_adjudicator_failed"
CODE_REPAIR_FAILED = "review_p4_repair_failed"
CODE_REPAIR_INVALID = "review_p4_repair_invalid"
CODE_REPAIR_COVERAGE_UNKNOWN = "review_p4_repair_coverage_unknown"
CODE_REPAIR_WIDEN_REQUIRED = "review_p4_repair_widen_required"
CODE_REVERIFICATION_INCOMPLETE = "review_p4_reverification_incomplete"
CODE_STRATEGY_CHANGE_REQUIRED = "review_p4_strategy_change_required"
CODE_HUMAN_DECISION_INVALID = "review_p4_human_decision_invalid"
CODE_RECEIPT_INVALIDATED = "review_p4_receipt_invalidated"
STOP_CODES = (
    CODE_HUMAN_WAIT,
    CODE_ADJUDICATION_INVALID,
    CODE_ADJUDICATOR_FAILED,
    CODE_REPAIR_FAILED,
    CODE_REPAIR_INVALID,
    CODE_REPAIR_COVERAGE_UNKNOWN,
    CODE_REPAIR_WIDEN_REQUIRED,
    CODE_REVERIFICATION_INCOMPLETE,
    CODE_STRATEGY_CHANGE_REQUIRED,
    CODE_HUMAN_DECISION_INVALID,
    CODE_RECEIPT_INVALIDATED,
)

#: P4 ReconcileRequired reasons, raised through :func:`reconcile`.
REASON_CONTRACT_MISMATCH = "review_p4_contract_mismatch"
REASON_LINKAGE_INVALID = "review_p4_linkage_invalid"
REASON_SUCCESSOR_CONFLICT = "review_p4_successor_conflict"
REASON_ADOPTION_MISMATCH = "review_p4_adoption_mismatch"
REASON_CHAIN_INVALID = "review_p4_chain_invalid"
RECONCILE_REASONS = (
    REASON_CONTRACT_MISMATCH,
    REASON_LINKAGE_INVALID,
    REASON_SUCCESSOR_CONFLICT,
    REASON_ADOPTION_MISMATCH,
    REASON_CHAIN_INVALID,
)


def stop(code: str, message: str) -> StopError:
    """A P4 STOP (built here so the owners raise P4 codes without restating them)."""
    if code not in STOP_CODES:
        raise ValueError(f"not a P4 STOP code: {code!r}")
    return StopError(message, code=code)


def reconcile(message: str, reason: str) -> ReconcileRequired:
    """A P4 reconcile-required refusal (built here, for the same reason as :func:`stop`)."""
    if reason not in RECONCILE_REASONS:
        raise ValueError(f"not a P4 reconcile reason: {reason!r}")
    return ReconcileRequired(f"{message}: reconcile required", reason=reason)


# --------------------------------------------------------------------------- the selector building blocks (§27.3)

_VIEWPOINT = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_DECISION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


@dataclass(frozen=True)
class ActorBinding:
    """One P4 actor: the callable, and the durable identity and version a task binds before launch."""

    actor: Callable[..., Any]
    identity: str
    version: str


@dataclass(frozen=True)
class DiscoveryBinding:
    """One required discovery actor and the viewpoint (task slot) it is assigned (§12.12)."""

    viewpoint: str
    actor: Callable[..., Any]
    identity: str
    version: str

    @property
    def task_slot(self) -> str:
        return discovery_slot(self.viewpoint)


@dataclass(frozen=True)
class HumanDecision:
    """The explicit Human-decision input of G-4: a stable decision identity and its disposition.

    Never a requirement store: a changed requirement already lives in its own
    normal authority, and a confirmation may leave its bytes unchanged - the
    decision identity is what tells "decided" apart from "no decision".
    """

    decision_id: str
    disposition: str

    def to_record(self) -> dict[str, Any]:
        return {
            serialize.SCHEMA_KEY: SCHEMA_HUMAN_DECISION, serialize.VERSION_KEY: RECORD_VERSION,
            "decision_id": self.decision_id, "disposition": self.disposition,
        }


def discovery_slot(viewpoint: str) -> str:
    if not isinstance(viewpoint, str) or _VIEWPOINT.match(viewpoint) is None:
        raise ValidationError(f"a P4 discovery viewpoint is a lowercase machine name, not {viewpoint!r}",
                              code="review_contract_invalid")
    return P4_DISCOVERY_SLOT_PREFIX + viewpoint


def _persistable_text(value: object) -> bool:
    if not isinstance(value, str) or not value or value != value.strip() or value.splitlines() != [value]:
        return False
    holder = {"text": value}
    try:
        serialize.canonical_bytes(holder)
        return serialize.canonical_roundtrips(holder)
    except (ValidationError, ValueError, UnicodeError):
        return False


def binding_problems(
    discovery: object, adjudicator: object, repair: object, human_decision: object
) -> list[str]:
    """What makes a P4 selector's actor bindings invalid, before the lock (§27.3)."""
    problems: list[str] = []
    if not isinstance(discovery, tuple) or not discovery:
        problems.append("discovery must be a non-empty tuple of DiscoveryBinding")
        discovery = ()
    viewpoints: list[str] = []
    for item in discovery:  # type: ignore[union-attr]
        if type(item) is not DiscoveryBinding:
            problems.append(f"a discovery actor is {type(item).__name__}, not a DiscoveryBinding")
            continue
        if not isinstance(item.viewpoint, str) or _VIEWPOINT.match(item.viewpoint) is None:
            problems.append(f"discovery viewpoint {item.viewpoint!r} is not a lowercase machine name")
        viewpoints.append(str(item.viewpoint))
        problems.extend(_actor_problems(item, f"discovery actor {item.viewpoint!r}"))
    if len(set(viewpoints)) != len(viewpoints):
        problems.append("two discovery actors share one viewpoint")
    for name, binding in (("adjudicator", adjudicator), ("repair", repair)):
        if type(binding) is not ActorBinding:
            problems.append(f"{name} must be an ActorBinding, not {type(binding).__name__}")
            continue
        problems.extend(_actor_problems(binding, name))
    if human_decision is not None:
        problems.extend(human_decision_problems(human_decision))
    return problems


def _actor_problems(binding: Any, described: str) -> list[str]:
    problems: list[str] = []
    if not callable(binding.actor):
        problems.append(f"{described} is not callable")
    for name in ("identity", "version"):
        if not _persistable_text(getattr(binding, name)):
            problems.append(f"{described} {name} must be non-empty single-line text the canonical form carries")
    return problems


def human_decision_problems(decision: object) -> list[str]:
    if type(decision) is not HumanDecision:
        return [f"human_decision must be a HumanDecision, not {type(decision).__name__}"]
    problems: list[str] = []
    if not isinstance(decision.decision_id, str) or _DECISION_ID.match(decision.decision_id) is None:
        problems.append(f"decision_id {decision.decision_id!r} is not a stable decision identity")
    if decision.disposition not in DECISION_DISPOSITIONS:
        problems.append(f"disposition {decision.disposition!r} is not one of {', '.join(DECISION_DISPOSITIONS)}")
    return problems


# --------------------------------------------------------------------------- the actor interfaces

@dataclass(frozen=True)
class P4Claim:
    severity: str  # HIGH | MID | LOW - reviewer-claimed, never authority
    code: str
    message: str


@dataclass(frozen=True)
class P4Coverage:
    """§12.12: what a discovery actor actually looked at, and what it did not."""

    inspected: tuple[str, ...] = ()
    checked: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    not_inspected: tuple[str, ...] = ()


@dataclass(frozen=True)
class P4DiscoveryReport:
    task_id: str
    reviewer_identity: str
    reviewer_version: str
    status: str  # completed | declined
    claims: tuple[P4Claim, ...] = ()
    coverage: P4Coverage = field(default_factory=P4Coverage)


@dataclass(frozen=True)
class P4DiscoveryTask:
    task_id: str
    task_slot: str
    task_kind: str
    review_kind: str
    viewpoint: str
    request_envelope: dict[str, Any]
    request_digest: str
    candidate_hash: str
    review_context_hash: str
    effective_policy_hash: str


@dataclass(frozen=True)
class P4ClaimDisposition:
    """The adjudicator's answer for one raw claim, in the §12.4 order.

    The four decision flags are the adjudicator's answers to §12.4 steps 1-4;
    ``outcome`` must be what that order yields from them, which is what lets a
    return that turns HUMAN uncertainty into a Problem be refused mechanically.
    The Finding fields are given exactly for Problem and Improvement.
    """

    task_id: str
    claim_index: int
    supported: bool
    requirement_decision_required: bool
    fails_requirement: bool
    better_alternative: bool
    outcome: str
    reason: str
    severity: str | None = None
    statement: str | None = None
    semantic_surface: str | None = None
    repair_identity: str | None = None
    disposition: str | None = None
    relation: str = RELATION_A_NEW
    linked_finding_ids: tuple[str, ...] = ()
    linked_repair_batch_ids: tuple[str, ...] = ()
    causal_evidence_digest: str | None = None


@dataclass(frozen=True)
class P4CoverageGap:
    """How the adjudication resolves one declared ``not_inspected`` surface (§12.12)."""

    task_id: str
    surface: str
    resolution: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class P4AdjudicationReturn:
    task_id: str
    adjudicator_identity: str
    adjudicator_version: str
    objective_holds: bool
    dispositions: tuple[P4ClaimDisposition, ...] = ()
    coverage_gaps: tuple[P4CoverageGap, ...] = ()
    #: Present when a repair follows: what it is for, and - when STRATEGY_CHANGE is required - which class.
    repair_purpose: str | None = None
    strategy_change_class: str | None = None


@dataclass(frozen=True)
class P4AdjudicationTask:
    task_id: str
    task_slot: str
    task_kind: str
    review_kind: str
    request_envelope: dict[str, Any]
    request_digest: str
    candidate_hash: str
    review_context_hash: str
    effective_policy_hash: str
    candidate: dict[str, Any]
    reports: tuple[dict[str, Any], ...]
    prior_findings: tuple[dict[str, Any], ...]
    prior_repair_batch: dict[str, Any] | None
    prior_repair_result: dict[str, Any] | None


@dataclass(frozen=True)
class P4CoverageCheck:
    semantic_behavior_changed: str
    semantic_responsibility: str
    other_sites: tuple[str, ...]
    shared_responsibility: bool
    enumerable: bool
    affected_set: tuple[str, ...]
    covers_affected_set: bool
    repair_scope: str  # local | widened
    unresolved_gap: str | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "semantic_behavior_changed": self.semantic_behavior_changed,
            "semantic_responsibility": self.semantic_responsibility,
            "other_sites": list(self.other_sites),
            "shared_responsibility": self.shared_responsibility,
            "enumerable": self.enumerable,
            "affected_set": list(self.affected_set),
            "covers_affected_set": self.covers_affected_set,
            "repair_scope": self.repair_scope,
            "unresolved_gap": self.unresolved_gap,
        }


@dataclass(frozen=True)
class P4Verification:
    verification_id: str
    result: str  # pass | fail


@dataclass(frozen=True)
class P4RepairReturn:
    """A repair actor's return: a proposal for a complete repaired Candidate, never an adopted one.

    ``proposal`` is kind-specific and complete (§27.16): planning returns the
    complete Candidate content; Work returns the complete result bytes of every
    declared path. The actor never writes the canonical working tree (G-5).
    """

    task_id: str
    repair_identity: str
    repair_version: str
    status: str  # completed | failed | declined
    proposal: Any = None
    repaired_surface: tuple[str, ...] = ()
    impact_class: str | None = None
    coverage_check: P4CoverageCheck | None = None
    verification: tuple[P4Verification, ...] = ()
    causal_summary: str | None = None


@dataclass(frozen=True)
class P4RepairTask:
    task_id: str
    task_slot: str
    task_kind: str
    review_kind: str
    request_envelope: dict[str, Any]
    request_digest: str
    candidate_hash: str
    source_candidate: dict[str, Any]
    repair_batch: dict[str, Any]
    findings: tuple[dict[str, Any], ...]


# --------------------------------------------------------------------------- policy (§12.21)

#: The one static P4 Effective Policy. ``skills/review`` declares it verbatim under its own heading.
POLICY_RECORD: dict[str, Any] = {
    serialize.SCHEMA_KEY: SCHEMA_POLICY,
    serialize.VERSION_KEY: RECORD_VERSION,
    "policy_id": POLICY_ID,
    "review_contracts": [PLANNING_CONTRACT, WORK_CONTRACT],
    "discovery": {
        "task_kind": TASK_KIND_DISCOVERY,
        "slot_rule": "one required task per viewpoint the P4 selector binds; at least one",
        "instruction": DISCOVERY_INSTRUCTION,
        "history": "fresh: no prior Finding or Repair history",
        "report_rule": "H-3 public-safe structured claims plus an explicit coverage declaration",
    },
    "adjudication": {
        "task_kind": TASK_KIND_ADJUDICATION,
        "slot": SLOT_ADJUDICATOR,
        "instruction": ADJUDICATION_INSTRUCTION,
        "contract": ADJUDICATION_CONTRACT,
        "order": ["unsupported", "HUMAN", "Problem", "Improvement", "dismissed_non_actionable"],
        "merge_rule": "same substantive issue, same semantic responsibility, one repair closes all; uncertain stays separate",
        "severity_rule": "the strongest severity the adjudication supports; the reviewer's severity is input only",
    },
    "repair": {
        "task_kind": TASK_KIND_REPAIR,
        "slot": SLOT_REPAIR,
        "instruction": REPAIR_INSTRUCTION,
        "batch_rule": "one Repair Batch per Candidate generation holding every decidable blocking Problem",
        "proposal_rule": "a complete repaired Candidate proposal; the owner alone adopts it",
    },
    "severities": list(P4_SEVERITIES),
    "categories": list(P4_CATEGORIES),
    "outcomes": list(P4_OUTCOMES),
    "blocking_rule": "Problem HIGH or MID, and every C_REPAIR_INDUCED Problem, is a blocking current-cycle obligation",
    "low_rule": "Problem LOW is non-blocking only while the current completion objective still holds",
    "improvement_rule": "Improvement of any severity is non-blocking",
    "human_rule": "a required requirement decision is HUMAN_WAIT at generation 4; no repair guesses it",
    "work_creation_rule": "LOW and Improvement never create Work automatically",
    "dispositions": list(P4_DISPOSITIONS),
    "relations": list(P4_RELATIONS),
    "strategy_rule": "two consecutive supported B/C failures on one semantic surface require STRATEGY_CHANGE",
    "impact_classes": list(P4_IMPACT_CLASSES),
    "reverification_minimums": {
        IMPACT_LOCAL: ["direct_consumers", "focused_tests"],
        IMPACT_SHARED: ["focused_tests", "integration_checks", "representative_callers"],
        IMPACT_CONTRACT: ["adjacent_eligibility", "contract_roundtrip", "failure_interruption_resume", "writers_readers"],
        IMPACT_FOUNDATION: ["broad_integration", "full_suite"],
    },
    "convergence_rule": "unresolved blocking review obligations = 0 and required coverage and Evidence are current",
    "evidence_reuse_rule": "positive proof under the dependency vocabulary only; a report, adjudication or Receipt is never reused",
    "seal_generation": SEAL_GENERATION,
    "last_generation": LAST_GENERATION,
}


def policy_record() -> dict[str, Any]:
    return serialize.canonical_data(POLICY_RECORD)


def policy_hash() -> str:
    return serialize.digest(policy_record())


def policy_named(policy_id: object) -> dict[str, Any] | None:
    record = policy_record()
    return record if policy_id == record["policy_id"] else None


#: The verification identities each impact class requires at least (§12.14 / §27.19).
REVERIFICATION_MINIMUMS: Mapping[str, tuple[str, ...]] = {
    key: tuple(value) for key, value in POLICY_RECORD["reverification_minimums"].items()
}


def reverification_plan(impact_class: str, kind_checks: Sequence[str] = ()) -> tuple[str, ...]:
    """The required verification identities of a repair: the semantic minimum of its impact plus the kind's own.

    The plan follows semantic impact, never file count, and never shrinks below
    the minimum (§12.14).
    """
    if impact_class not in P4_IMPACT_CLASSES:
        raise ValidationError(f"not an impact class: {impact_class!r}", code="review_record_invalid")
    return tuple(sorted(set(REVERIFICATION_MINIMUMS[impact_class]) | set(kind_checks)))


# --------------------------------------------------------------------------- request envelopes and dispatch (§27.3)

def requirement_record(review_kind: str, authority: Mapping[str, Any]) -> dict[str, Any]:
    """The current decided requirement / desired-state material an owner supplies, as one canonical record."""
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_REQUIREMENT, serialize.VERSION_KEY: RECORD_VERSION,
        "review_kind": review_kind, "authority": dict(authority),
    })


def _set_aside(items: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    found = [{"review_run_id": str(item["review_run_id"]), "reason": str(item["reason"])} for item in items]
    return sorted(found, key=lambda item: item["review_run_id"])


def succession_record(
    predecessor_review_run_id: str, predecessor_candidate_hash: str, repair_batch_id: str, repair_result_digest: str
) -> dict[str, Any]:
    """The successor linkage of a Candidate N+1 Run (§27.21, G-1 item 4)."""
    return {
        "predecessor_review_run_id": predecessor_review_run_id,
        "predecessor_candidate_hash": predecessor_candidate_hash,
        "repair_batch_id": repair_batch_id,
        "repair_result_digest": repair_result_digest,
    }


def discovery_request(
    *,
    review_contract: str,
    review_kind: str,
    viewpoint: str,
    candidate: dict[str, Any],
    context: dict[str, Any],
    requirement: dict[str, Any],
    candidate_generation: int,
    succession: dict[str, Any] | None,
    set_aside_runs: Iterable[Mapping[str, Any]],
    human_decision: HumanDecision | None,
    kind_material: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The P4 discovery request: what one discovery actor is asked, with the P4 contract bound explicitly.

    Discovery is fresh: it carries the successor linkage identities a recovery
    needs, never prior Finding or Repair content (§12.2).
    """
    if review_contract not in CONTRACTS:
        raise ValidationError(f"not a P4 contract: {review_contract!r}", code="review_contract_invalid")
    if (candidate_generation == 1) != (succession is None):
        raise ValidationError("candidate generation 1 has no succession, and every later one has exactly one",
                              code="review_record_invalid")
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_DISCOVERY_REQUEST,
        serialize.VERSION_KEY: RECORD_VERSION,
        "review_contract": review_contract,
        "review_kind": review_kind,
        "policy_id": POLICY_ID,
        "instruction": DISCOVERY_INSTRUCTION,
        "viewpoint": viewpoint,
        "candidate": candidate,
        "context": context,
        "requirement": requirement,
        "candidate_generation": candidate_generation,
        "succession": succession,
        "set_aside_runs": _set_aside(set_aside_runs),
        "human_decision": None if human_decision is None else human_decision.to_record(),
        "kind_material": kind_material,
    })


def adjudication_request(
    *,
    review_contract: str,
    review_kind: str,
    review_run_id: str,
    candidate_hash: str,
    candidate_generation: int,
    review_context_hash: str,
    requirement: dict[str, Any],
    reports: Sequence[Mapping[str, Any]],
    prior: Mapping[str, Any],
    evidence_ids: Sequence[str],
) -> dict[str, Any]:
    """The adjudication request, built from canonical material only (§12.7 / §27.10)."""
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_ADJUDICATION_REQUEST,
        serialize.VERSION_KEY: RECORD_VERSION,
        "review_contract": review_contract,
        "review_kind": review_kind,
        "policy_id": POLICY_ID,
        "instruction": ADJUDICATION_INSTRUCTION,
        "adjudication_contract": ADJUDICATION_CONTRACT,
        "review_run_id": review_run_id,
        "candidate_hash": candidate_hash,
        "candidate_generation": candidate_generation,
        "review_context_hash": review_context_hash,
        "requirement": requirement,
        "reports": [{"task_id": str(item["task_id"]), "result_digest": str(item["result_digest"])} for item in reports],
        "prior": dict(prior),
        "evidence_ids": sorted(set(evidence_ids)),
    })


def repair_request(
    *,
    review_contract: str,
    review_kind: str,
    review_run_id: str,
    candidate_hash: str,
    candidate_generation: int,
    requirement: dict[str, Any],
    repair_batch_id: str,
    repair_batch_digest: str,
    allowed_result_surface: Sequence[str],
    strategy: str,
    evidence_constraints: Sequence[str],
) -> dict[str, Any]:
    """The ReviewRepairRequest, built from canonical material only (§12.9 / §27.15)."""
    return serialize.canonical_data({
        serialize.SCHEMA_KEY: SCHEMA_REPAIR_REQUEST,
        serialize.VERSION_KEY: RECORD_VERSION,
        "review_contract": review_contract,
        "review_kind": review_kind,
        "policy_id": POLICY_ID,
        "instruction": REPAIR_INSTRUCTION,
        "review_run_id": review_run_id,
        "candidate_hash": candidate_hash,
        "candidate_generation": candidate_generation,
        "requirement": requirement,
        "repair_batch_id": repair_batch_id,
        "repair_batch_digest": repair_batch_digest,
        "allowed_result_surface": sorted(set(allowed_result_surface)),
        "strategy": strategy,
        "evidence_constraints": sorted(set(evidence_constraints)),
    })


def contract_of_envelope(envelope: object) -> str | None:
    """The P4 contract a request envelope explicitly binds, or ``None`` when it is not a P4 request.

    Explicit persisted identity only (§27.3): never inferred from a generation
    count or a record shape. A v1 envelope names no ``review_contract`` and is
    never read as P4.
    """
    if not isinstance(envelope, dict) or envelope.get(serialize.SCHEMA_KEY) not in REQUEST_SCHEMAS:
        return None
    if envelope.get(serialize.VERSION_KEY) != RECORD_VERSION or envelope.get("policy_id") != POLICY_ID:
        return None
    contract = envelope.get("review_contract")
    return contract if contract in CONTRACTS else None


def contract_of_task_input(task_input: records.TaskInput) -> str | None:
    """The P4 contract of a stored TaskInput (its request envelope and task kind agree), or ``None``."""
    contract = contract_of_envelope(task_input.request_envelope)
    if contract is None:
        return None
    expected = {
        SCHEMA_DISCOVERY_REQUEST: TASK_KIND_DISCOVERY,
        SCHEMA_ADJUDICATION_REQUEST: TASK_KIND_ADJUDICATION,
        SCHEMA_REPAIR_REQUEST: TASK_KIND_REPAIR,
    }[task_input.request_envelope[serialize.SCHEMA_KEY]]
    return contract if task_input.task_kind == expected else None


def task_input(
    *,
    task_id: str,
    task_slot: str,
    task_kind: str,
    actor_identity: str,
    actor_version: str,
    envelope: dict[str, Any],
    candidate_hash: str,
    candidate_material_digest: str,
    review_context_hash: str,
    accepted_generation: int,
) -> records.TaskInput:
    """The P1 TaskInput of one P4 task (snapshot reconstruction; the Candidate snapshot is the material)."""
    return records.TaskInput(
        task_id=task_id,
        task_slot=task_slot,
        task_kind=task_kind,
        reviewer_identity=actor_identity,
        reviewer_version=actor_version,
        request_envelope=envelope,
        request_digest=serialize.digest(envelope),
        candidate_hash=candidate_hash,
        reconstruction_mode=records.RECONSTRUCTION_SNAPSHOT,
        candidate_material_digest=candidate_material_digest,
        review_context_hash=review_context_hash,
        effective_policy_hash=policy_hash(),
        accepted_generation=accepted_generation,
    )


def accepted_descriptor(found: records.TaskInput) -> dict[str, Any]:
    """The accepted task descriptor a generation carries, from the same sources as the TaskInput."""
    return {
        "task_id": found.task_id,
        "task_slot": found.task_slot,
        "task_kind": found.task_kind,
        "reviewer_identity": found.reviewer_identity,
        "reviewer_version": found.reviewer_version,
        "candidate_hash": found.candidate_hash,
        "candidate_material_digest": found.candidate_material_digest,
        "reconstruction_mode": found.reconstruction_mode,
        "request_digest": found.request_digest,
        "task_input_digest": serialize.digest(found.to_record()),
        "review_context_hash": found.review_context_hash,
        "effective_policy_hash": found.effective_policy_hash,
    }


# --------------------------------------------------------------------------- gate digest records

def coverage_record(required: Sequence[tuple[str, str]], settled: Sequence[Mapping[str, Any]],
                    reports: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """The discovery coverage a generation binds: the required slots, what settled, and each report's declaration."""
    reports = reports or {}
    return {
        serialize.SCHEMA_KEY: SCHEMA_COVERAGE, serialize.VERSION_KEY: RECORD_VERSION,
        "required": [{"task_slot": slot, "task_id": task_id} for slot, task_id in required],
        "settled": [
            {
                "task_id": str(task["task_id"]), "status": str(task["status"]),
                "coverage": None if str(task["task_id"]) not in reports
                else serialize.canonical_data(reports[str(task["task_id"])]["coverage"]),
            }
            for task in settled
        ],
    }


def report_set_record(settled: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        serialize.SCHEMA_KEY: SCHEMA_REPORT_SET, serialize.VERSION_KEY: RECORD_VERSION,
        "reports": [{"task_id": str(task["task_id"]), "result_digest": str(task["result_digest"])} for task in settled],
    }


def pending_adjudication_record() -> dict[str, Any]:
    """The adjudication digest a generation binds before the adjudication settles."""
    return {serialize.SCHEMA_KEY: SCHEMA_ADJUDICATION_PENDING, serialize.VERSION_KEY: RECORD_VERSION}


def obligations_record(adjudication: records.P4Adjudication | None) -> dict[str, Any]:
    """The obligation digest a generation binds: pending before G4, the adjudication's summary after."""
    if adjudication is None:
        return {
            serialize.SCHEMA_KEY: SCHEMA_OBLIGATIONS, serialize.VERSION_KEY: RECORD_VERSION,
            "outcome": None, "obligations": None, "blocking_finding_ids": [],
        }
    return {
        serialize.SCHEMA_KEY: SCHEMA_OBLIGATIONS, serialize.VERSION_KEY: RECORD_VERSION,
        "outcome": adjudication.outcome,
        "obligations": dict(adjudication.obligations),
        "blocking_finding_ids": [str(item["finding_id"]) for item in adjudication.findings if item["blocking"]],
    }


def invalidation_evidence_record(superseded_receipt_id: str, reason: str) -> dict[str, Any]:
    """The evidence a P4 G6 invalidation binds by digest (G-3)."""
    if not is_valid_id(str(superseded_receipt_id), "review_receipt") or reason != INVALIDATION_STALE_RECEIPT:
        raise ValidationError("the P4 invalidation evidence names no Receipt or no stable reason",
                              code="review_record_invalid")
    return {
        serialize.SCHEMA_KEY: SCHEMA_INVALIDATION_EVIDENCE, serialize.VERSION_KEY: RECORD_VERSION,
        "superseded_receipt_id": superseded_receipt_id, "reason": reason,
    }


# --------------------------------------------------------------------------- reports (§12.3, §27.4, §27.9)

def _report_invalid(message: str) -> StopError:
    # The P1/P2 code: a report that is not exactly a valid report for this task does not settle.
    return StopError(f"the discovery report is not valid: {message}; nothing is settled", code="review_report_invalid")


def report_record(returned: object, descriptor: Mapping[str, Any], *, review_kind: str, review_contract: str) -> dict[str, Any]:
    """The canonical P4 report record of a discovery return, validated and H-3 checked before anything settles.

    An unsafe or malformed return is refused here and never persisted: the
    accepted task stays the authority, and the same task is launched again.
    """
    if type(returned) is not P4DiscoveryReport:
        raise _report_invalid(f"the discovery actor returned {type(returned).__name__}, not a P4DiscoveryReport")
    if returned.task_id != descriptor["task_id"]:
        raise _report_invalid(f"it answers task {returned.task_id!r}, not {descriptor['task_id']}")
    if returned.reviewer_identity != descriptor["reviewer_identity"] or returned.reviewer_version != descriptor["reviewer_version"]:
        raise StopError(
            f"task {descriptor['task_id']} was accepted for reviewer {descriptor['reviewer_identity']} "
            f"{descriptor['reviewer_version']}, and the report comes from {returned.reviewer_identity!r} "
            f"{returned.reviewer_version!r}; nothing is settled",
            code="review_reviewer_mismatch",
        )
    if not isinstance(returned.claims, tuple) or type(returned.coverage) is not P4Coverage:
        raise _report_invalid("claims is not a tuple of P4Claim or coverage is not a P4Coverage")
    slot = str(descriptor["task_slot"])
    claims: list[dict[str, Any]] = []
    for claim in returned.claims:
        if type(claim) is not P4Claim:
            raise _report_invalid(f"a claim is {type(claim).__name__}, not a P4Claim")
        claims.append({"severity": claim.severity, "code": claim.code, "message": claim.message})
    coverage = returned.coverage
    for name in ("inspected", "checked", "evidence_ids", "not_inspected"):
        if not isinstance(getattr(coverage, name), tuple):
            raise _report_invalid(f"coverage {name} is not a tuple of text")
    record = {
        serialize.SCHEMA_KEY: records.SCHEMA_P4_REPORT,
        serialize.VERSION_KEY: records.VERSION,
        "review_kind": review_kind,
        "review_contract": review_contract,
        "task_id": returned.task_id,
        "task_slot": slot,
        "reviewer_identity": returned.reviewer_identity,
        "reviewer_version": returned.reviewer_version,
        "status": returned.status,
        "claims": claims,
        "coverage": {
            "viewpoint": slot[len(P4_DISCOVERY_SLOT_PREFIX):],
            "inspected": list(coverage.inspected),
            "checked": list(coverage.checked),
            "evidence_ids": list(coverage.evidence_ids),
            "not_inspected": list(coverage.not_inspected),
        },
    }
    try:
        typed = records.P4Report.from_record(serialize.canonical_data(record), "the discovery report")
        if not serialize.canonical_roundtrips(record):
            raise _report_invalid("it does not read back as itself in canonical form")
    except ValidationError as exc:
        raise _report_invalid(str(exc)) from exc
    return serialize.canonical_data(typed.to_record())


def settled_status(report: Mapping[str, Any]) -> str:
    """A declined discovery report settles its task ``failed``; a completed one ``completed``."""
    return records.TASK_SETTLED_OK if report["status"] == "completed" else records.TASK_SETTLED_FAILED


# --------------------------------------------------------------------------- adjudication (§12.4, §12.5, §27.6-§27.11)

@dataclass(frozen=True)
class PriorCycle:
    """The current-cycle predecessor an adjudication may use (§12.7): its findings, batch and result."""

    review_run_id: str
    adjudication: records.P4Adjudication
    adjudication_digest: str
    repair_batch: records.P4RepairBatch
    repair_result: records.P4RepairResult
    repair_result_digest: str
    #: The B/C surfaces of every earlier adjudication of the cycle, oldest first, this predecessor's last.
    bc_history: tuple[frozenset[str], ...] = ()

    def prior_record(self) -> dict[str, Any]:
        return {
            "predecessor_review_run_id": self.review_run_id,
            "predecessor_adjudication_digest": self.adjudication_digest,
            "repair_batch_id": self.repair_batch.repair_batch_id,
            "repair_result_digest": self.repair_result_digest,
        }


NO_PRIOR = {
    "predecessor_review_run_id": None,
    "predecessor_adjudication_digest": None,
    "repair_batch_id": None,
    "repair_result_digest": None,
}


@dataclass(frozen=True)
class FindingDraft:
    """One normalized Finding before its ID is reserved: the canonical, deterministic grouping of claims."""

    category: str
    severity: str
    statement: str
    semantic_surface: str
    repair_identity: str
    sources: tuple[tuple[str, str, int], ...]
    disposition: str
    blocking: bool
    relation: str
    linked_finding_ids: tuple[str, ...]
    linked_repair_batch_ids: tuple[str, ...]
    causal_evidence_digest: str | None

    def order_key(self) -> tuple[Any, ...]:
        """§27.7: surface, repair identity, category, then the canonical ordered source claims."""
        return (self.semantic_surface, self.repair_identity, self.category, self.sources)


@dataclass(frozen=True)
class Normalized:
    """A validated adjudication return: one entry per raw claim, the Finding drafts in canonical order."""

    objective_holds: bool
    entries: tuple[dict[str, Any], ...]
    drafts: tuple[FindingDraft, ...]
    gaps: tuple[dict[str, Any], ...]
    repair_purpose: str | None
    strategy_change_class: str | None
    strategy_change_required: bool


def _adjudication_invalid(message: str) -> StopError:
    return stop(CODE_ADJUDICATION_INVALID, f"the adjudication return is not valid: {message}; nothing is settled")


def expected_outcome(supported: bool, requirement_decision_required: bool, fails_requirement: bool,
                     better_alternative: bool) -> str:
    """§12.4 in order: the one outcome the decision answers yield."""
    if not supported:
        return OUTCOME_UNSUPPORTED
    if requirement_decision_required:
        return OUTCOME_HUMAN
    if fails_requirement:
        return OUTCOME_PROBLEM
    if better_alternative:
        return OUTCOME_IMPROVEMENT
    return OUTCOME_DISMISSED


def is_blocking(category: str, severity: str, relation: str) -> bool:
    """H-4: Problem HIGH/MID blocks; a repair-induced Problem blocks; LOW and Improvement do not."""
    if category != OUTCOME_PROBLEM:
        return False
    return severity in ("HIGH", "MID") or relation == RELATION_C_REPAIR_INDUCED


def strategy_change_required(bc_history: Sequence[frozenset[str]], current: frozenset[str]) -> bool:
    """§12.17: two consecutive supported B/C failures on the same semantic surface (BB, CC, BC, CB).

    ``bc_history`` holds the B/C surfaces of the cycle's earlier adjudications,
    oldest first; ``current`` the surfaces of this one. Only the immediately
    preceding adjudication is consecutive; a different surface never counts, and
    an operational failure never reaches an adjudication at all.
    """
    if not bc_history:
        return False
    return bool(set(bc_history[-1]) & set(current))


def normalize_adjudication(
    returned: object,
    descriptor: Mapping[str, Any],
    reports: Sequence[tuple[str, str, Mapping[str, Any]]],
    prior: PriorCycle | None,
) -> Normalized:
    """Validate an adjudicator's return against the bound reports, and normalize it deterministically.

    ``reports`` is ``[(task_id, result_digest, canonical report record)]`` in
    the order G3 bound them. Every refusal of §27.11 is a STOP that settles
    nothing: an unsupported claim as a Finding, HUMAN uncertainty as a
    Problem/Improvement, a non-blocking LOW Problem while the objective fails,
    B/C without positive causal linkage, an omitted claim, an invented source,
    and contradictory duplicate Finding identities.
    """
    if type(returned) is not P4AdjudicationReturn:
        raise _adjudication_invalid(f"the adjudicator returned {type(returned).__name__}, not a P4AdjudicationReturn")
    if returned.task_id != descriptor["task_id"]:
        raise _adjudication_invalid(f"it answers task {returned.task_id!r}, not {descriptor['task_id']}")
    if (returned.adjudicator_identity, returned.adjudicator_version) != (
        descriptor["reviewer_identity"], descriptor["reviewer_version"]
    ):
        raise StopError(
            f"adjudication task {descriptor['task_id']} was accepted for {descriptor['reviewer_identity']} "
            f"{descriptor['reviewer_version']}, and the return comes from {returned.adjudicator_identity!r} "
            f"{returned.adjudicator_version!r}; nothing is settled",
            code="review_reviewer_mismatch",
        )
    if type(returned.objective_holds) is not bool:
        raise _adjudication_invalid("objective_holds is not a boolean")
    if not isinstance(returned.dispositions, tuple) or not isinstance(returned.coverage_gaps, tuple):
        raise _adjudication_invalid("dispositions and coverage_gaps are tuples")
    claims: dict[tuple[str, int], tuple[str, Mapping[str, Any]]] = {}
    not_inspected: set[tuple[str, str]] = set()
    for task_id, result_digest, report in reports:
        for index, claim in enumerate(report.get("claims") or []):
            claims[(task_id, index)] = (result_digest, claim)
        for surface in (report.get("coverage") or {}).get("not_inspected") or []:
            not_inspected.add((task_id, str(surface)))
    prior_findings = {} if prior is None else {str(item["finding_id"]): item for item in prior.adjudication.findings}
    entries: list[dict[str, Any]] = []
    groups: dict[tuple[str, str, str], list[tuple[tuple[str, str, int], P4ClaimDisposition]]] = {}
    seen: set[tuple[str, int]] = set()
    for item in returned.dispositions:
        if type(item) is not P4ClaimDisposition:
            raise _adjudication_invalid(f"a disposition is {type(item).__name__}, not a P4ClaimDisposition")
        key = (item.task_id, item.claim_index)
        if key not in claims:
            raise _adjudication_invalid(f"it adjudicates claim {item.claim_index} of {item.task_id!r}, which G3 never bound")
        if key in seen:
            raise _adjudication_invalid(f"it adjudicates claim {item.claim_index} of {item.task_id} twice")
        seen.add(key)
        for flag in ("supported", "requirement_decision_required", "fails_requirement", "better_alternative"):
            if type(getattr(item, flag)) is not bool:
                raise _adjudication_invalid(f"{flag} of claim {item.claim_index} of {item.task_id} is not a boolean")
        expected = expected_outcome(
            item.supported, item.requirement_decision_required, item.fails_requirement, item.better_alternative
        )
        if item.outcome not in P4_OUTCOMES:
            raise _adjudication_invalid(f"outcome {item.outcome!r} is not a P4 outcome")
        if item.outcome != expected:
            raise _adjudication_invalid(
                f"claim {item.claim_index} of {item.task_id} is {item.outcome}, and the §12.4 order yields {expected}"
            )
        problem = public_safe_problem(item.reason)
        if problem is not None:
            raise _adjudication_invalid(f"the reason of claim {item.claim_index} of {item.task_id}: {problem}")
        result_digest, _ = claims[key]
        source = (item.task_id, result_digest, item.claim_index)
        finding_fields = (item.severity, item.statement, item.semantic_surface, item.repair_identity, item.disposition)
        if item.outcome in P4_CATEGORIES:
            _check_finding_fields(item, returned.objective_holds, prior, prior_findings)
            groups.setdefault((item.outcome, str(item.semantic_surface), str(item.repair_identity)), []).append((source, item))
        else:
            if any(value is not None for value in finding_fields) or item.relation != RELATION_A_NEW \
                    or item.linked_finding_ids or item.linked_repair_batch_ids or item.causal_evidence_digest is not None:
                raise _adjudication_invalid(
                    f"claim {item.claim_index} of {item.task_id} is {item.outcome} and carries Finding material; "
                    "only Problem and Improvement create Findings"
                )
        entries.append({
            "task_id": item.task_id, "result_digest": result_digest, "claim_index": item.claim_index,
            "outcome": item.outcome, "supported": item.supported,
            "requirement_decision_required": item.requirement_decision_required,
            "fails_requirement": item.fails_requirement, "better_alternative": item.better_alternative,
            "finding_id": None, "reason": item.reason,
        })
    omitted = sorted(set(claims) - seen)
    if omitted:
        raise _adjudication_invalid(
            "it omits claim(s) " + ", ".join(f"{index} of {task_id}" for task_id, index in omitted)
        )
    by_repair: dict[str, tuple[str, str]] = {}
    drafts: list[FindingDraft] = []
    for (category, surface, repair_identity), members in groups.items():
        owner = by_repair.setdefault(repair_identity, (category, surface))
        if owner != (category, surface):
            raise _adjudication_invalid(
                f"repair identity {repair_identity!r} names two Findings of different category or responsibility"
            )
        members.sort(key=lambda pair: pair[0])
        first = members[0][1]
        for _, other in members[1:]:
            if (other.disposition, other.relation, other.linked_finding_ids, other.linked_repair_batch_ids,
                    other.causal_evidence_digest) != (first.disposition, first.relation, first.linked_finding_ids,
                                                       first.linked_repair_batch_ids, first.causal_evidence_digest):
                raise _adjudication_invalid(
                    f"the claims merged under repair identity {repair_identity!r} disagree on disposition or linkage; "
                    "one Finding has one disposition and one causal linkage"
                )
        severity = max((str(member.severity) for _, member in members), key=lambda value: P4_SEVERITY_RANK[value])
        blocking = is_blocking(category, severity, first.relation)
        disposition = str(first.disposition)
        if blocking and disposition != DISPOSITION_REPAIR_REQUIRED:
            raise _adjudication_invalid(
                f"the {category} {severity} Finding {repair_identity!r} blocks and is disposed {disposition}; a blocking "
                f"Problem is {DISPOSITION_REPAIR_REQUIRED}"
            )
        if not blocking and disposition == DISPOSITION_REPAIR_REQUIRED:
            raise _adjudication_invalid(
                f"the {category} {severity} Finding {repair_identity!r} does not block and is disposed "
                f"{DISPOSITION_REPAIR_REQUIRED}; a deliberate current-cycle repair is {DISPOSITION_REPAIRED_CURRENT_CYCLE}"
            )
        drafts.append(FindingDraft(
            category=category, severity=severity, statement=str(first.statement), semantic_surface=surface,
            repair_identity=repair_identity, sources=tuple(source for source, _ in members), disposition=disposition,
            blocking=blocking, relation=first.relation, linked_finding_ids=tuple(first.linked_finding_ids),
            linked_repair_batch_ids=tuple(first.linked_repair_batch_ids),
            causal_evidence_digest=first.causal_evidence_digest,
        ))
    drafts.sort(key=FindingDraft.order_key)
    gaps: list[dict[str, Any]] = []
    gap_keys: set[tuple[str, str]] = set()
    bound_tasks = {task_id for task_id, _, _ in reports}
    for gap in returned.coverage_gaps:
        if type(gap) is not P4CoverageGap:
            raise _adjudication_invalid(f"a coverage gap is {type(gap).__name__}, not a P4CoverageGap")
        if gap.task_id not in bound_tasks:
            raise _adjudication_invalid(f"a coverage gap names task {gap.task_id!r}, which G3 never bound")
        if gap.resolution not in P4_GAP_RESOLUTIONS:
            raise _adjudication_invalid(f"coverage gap resolution {gap.resolution!r} is not one of {P4_GAP_RESOLUTIONS}")
        if not isinstance(gap.evidence_ids, tuple) or (gap.resolution == GAP_COVERED and not gap.evidence_ids):
            raise _adjudication_invalid(f"coverage gap {gap.surface!r} is resolved covered without valid Evidence")
        key = (gap.task_id, gap.surface)
        if key in gap_keys:
            raise _adjudication_invalid(f"coverage gap {gap.surface!r} of {gap.task_id} is resolved twice")
        gap_keys.add(key)
        gaps.append({"task_id": gap.task_id, "surface": gap.surface, "resolution": gap.resolution,
                     "evidence_ids": list(gap.evidence_ids)})
    if gap_keys != not_inspected:
        missing = sorted(not_inspected - gap_keys)
        extra = sorted(gap_keys - not_inspected)
        raise _adjudication_invalid(
            f"the coverage gaps are not exactly the declared not-inspected surfaces (unresolved {missing}, "
            f"undeclared {extra})"
        )
    gaps.sort(key=lambda item: (item["task_id"], item["surface"]))
    current_bc = frozenset(d.semantic_surface for d in drafts if d.relation in (RELATION_B_RECURRENCE, RELATION_C_REPAIR_INDUCED))
    change_required = strategy_change_required(() if prior is None else prior.bc_history, current_bc)
    repairing = any(d.blocking or d.disposition == DISPOSITION_REPAIRED_CURRENT_CYCLE for d in drafts)
    if returned.repair_purpose is not None and public_safe_problem(returned.repair_purpose) is not None:
        raise _adjudication_invalid("the repair purpose is not public-safe text")
    if returned.strategy_change_class is not None and returned.strategy_change_class not in P4_STRATEGY_CHANGE_CLASSES:
        raise _adjudication_invalid(f"strategy change class {returned.strategy_change_class!r} is not a P4 class")
    human = _human_count(entries, gaps)
    if not returned.objective_holds and not human and not any(d.blocking for d in drafts):
        raise _adjudication_invalid(
            "the current completion objective does not hold, and no blocking Problem or HUMAN outcome says why; a "
            "Candidate that fails its objective is never authorization-ready"
        )
    if repairing and not human:
        if returned.repair_purpose is None:
            raise _adjudication_invalid("a repair follows and the return names no repair purpose")
        if change_required and returned.strategy_change_class is None:
            raise stop(
                CODE_STRATEGY_CHANGE_REQUIRED,
                "two consecutive supported B/C repair failures share a semantic surface, so the next repair must be a "
                "STRATEGY_CHANGE, and the adjudication return selects no strategy-change class; nothing is settled",
            )
    return Normalized(
        objective_holds=returned.objective_holds,
        entries=tuple(entries),
        drafts=tuple(drafts),
        gaps=tuple(gaps),
        repair_purpose=returned.repair_purpose,
        strategy_change_class=returned.strategy_change_class,
        strategy_change_required=change_required,
    )


def _check_finding_fields(item: P4ClaimDisposition, objective_holds: bool, prior: PriorCycle | None,
                          prior_findings: Mapping[str, Mapping[str, Any]]) -> None:
    where = f"claim {item.claim_index} of {item.task_id}"
    if item.severity not in P4_SEVERITIES:
        raise _adjudication_invalid(f"{where} is a Finding with severity {item.severity!r}")
    for name, limit in (("statement", records.P4_MAX_TEXT), ("semantic_surface", records.P4_MAX_LABEL),
                        ("repair_identity", records.P4_MAX_LABEL)):
        problem = public_safe_problem(getattr(item, name), limit=limit)
        if problem is not None:
            raise _adjudication_invalid(f"{where} {name}: {problem}")
    if item.disposition not in P4_DISPOSITIONS:
        raise _adjudication_invalid(f"{where} disposition {item.disposition!r} is not a P4 disposition")
    if item.outcome == OUTCOME_IMPROVEMENT:
        if item.disposition not in (DISPOSITION_RETAINED_HISTORY_ONLY, DISPOSITION_FUTURE_WORK_CANDIDATE,
                                    DISPOSITION_NO_ACTION):
            raise _adjudication_invalid(
                f"{where} is an Improvement disposed {item.disposition}; an Improvement is never inserted into a "
                "mandatory Repair Batch"
            )
        if item.relation != RELATION_A_NEW:
            raise _adjudication_invalid(f"{where} is an Improvement with relation {item.relation}; B/C name Problems")
    if item.outcome == OUTCOME_PROBLEM and item.severity == "LOW" and item.relation != RELATION_C_REPAIR_INDUCED \
            and not objective_holds:
        raise _adjudication_invalid(
            f"{where} is a LOW Problem while the current completion objective does not hold; it is a blocking "
            "Problem MID/HIGH, or HUMAN when the requirement itself is unclear"
        )
    if item.relation not in P4_RELATIONS:
        raise _adjudication_invalid(f"{where} relation {item.relation!r} is not A_NEW, B_RECURRENCE or C_REPAIR_INDUCED")
    if not isinstance(item.linked_finding_ids, tuple) or not isinstance(item.linked_repair_batch_ids, tuple):
        raise _adjudication_invalid(f"{where} links are not tuples")
    problems = relation_problems(
        item.relation, item.semantic_surface, item.linked_finding_ids, item.linked_repair_batch_ids,
        item.causal_evidence_digest, prior, prior_findings,
    )
    if problems:
        raise _adjudication_invalid(f"{where}: " + "; ".join(problems))


def relation_problems(
    relation: str,
    semantic_surface: object,
    linked_finding_ids: Sequence[str],
    linked_repair_batch_ids: Sequence[str],
    causal_evidence_digest: object,
    prior: PriorCycle | None,
    prior_findings: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """§12.16 / §27.23: A/B/C from explicit current-cycle linkage only - timing alone is never causality."""
    problems: list[str] = []
    if relation == RELATION_A_NEW:
        if linked_finding_ids or linked_repair_batch_ids or causal_evidence_digest is not None:
            problems.append("A_NEW asserts no causal linkage; a link names B or C")
        return problems
    if prior is None:
        return [f"{relation} needs a prior repair in this cycle, and there is none"]
    if not isinstance(causal_evidence_digest, str) or records.DIGEST_RE.match(causal_evidence_digest) is None:
        problems.append(f"{relation} carries no causal evidence digest")
    if list(linked_repair_batch_ids) != [prior.repair_batch.repair_batch_id]:
        problems.append(f"{relation} does not name the cycle's prior Repair Batch {prior.repair_batch.repair_batch_id}")
    if relation == RELATION_B_RECURRENCE:
        if not linked_finding_ids:
            problems.append("B_RECURRENCE names no prior Finding it recurs from")
        for finding_id in linked_finding_ids:
            found = prior_findings.get(finding_id)
            if found is None:
                problems.append(f"B_RECURRENCE links {finding_id}, which the prior adjudication does not hold")
            elif finding_id not in prior.repair_batch.finding_ids:
                problems.append(f"B_RECURRENCE links {finding_id}, which the prior repair did not attempt")
            elif found["semantic_surface"] != semantic_surface:
                problems.append(f"B_RECURRENCE links {finding_id} on another semantic responsibility")
    else:
        for finding_id in linked_finding_ids:
            if finding_id not in prior_findings:
                problems.append(f"C_REPAIR_INDUCED links {finding_id}, which the prior adjudication does not hold")
    return problems


def _human_count(entries: Sequence[Mapping[str, Any]], gaps: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for entry in entries if entry["outcome"] == OUTCOME_HUMAN) + sum(
        1 for gap in gaps if gap["resolution"] in (GAP_HUMAN, GAP_TARGETED_CHECK)
    )


def obligations(normalized: Normalized) -> dict[str, Any]:
    """The obligation summary of a normalized adjudication (§12.18)."""
    drafts = normalized.drafts
    return {
        "unadjudicated": 0,
        "problem_high": sum(1 for d in drafts if d.blocking and d.severity == "HIGH"),
        "problem_mid": sum(1 for d in drafts if d.blocking and d.severity != "HIGH"),
        "problem_low": sum(1 for d in drafts if d.category == OUTCOME_PROBLEM and not d.blocking),
        "improvement": sum(1 for d in drafts if d.category == OUTCOME_IMPROVEMENT),
        "human": _human_count(normalized.entries, normalized.gaps),
        "coverage_unresolved": sum(1 for gap in normalized.gaps if gap["resolution"] in (GAP_HUMAN, GAP_TARGETED_CHECK)),
        "strategy_change_required": normalized.strategy_change_required,
    }


def derive_outcome(normalized: Normalized) -> str:
    """§27.11: exactly one of AUTHORIZATION_READY, REPAIR_REQUIRED, HUMAN_WAIT.

    HUMAN first: a missing requirement decision is never repaired by guessing
    it. Then any blocking Problem (or a deliberately repaired LOW) is a repair.
    Otherwise the obligations are zero and the Candidate may authorize, subject
    to the owner's own currency and Evidence checks before the seal.
    """
    found = obligations(normalized)
    if found["human"]:
        return HUMAN_WAIT
    if any(d.blocking or d.disposition == DISPOSITION_REPAIRED_CURRENT_CYCLE for d in normalized.drafts):
        return REPAIR_REQUIRED
    return AUTHORIZATION_READY


def adjudication(
    normalized: Normalized,
    finding_ids: Sequence[str],
    *,
    review_run_id: str,
    gate_record: records.GateGeneration,
    candidate_generation: int,
    review_contract: str,
    descriptor: Mapping[str, Any],
    reports: Sequence[tuple[str, str, Mapping[str, Any]]],
    prior: PriorCycle | None,
) -> records.P4Adjudication:
    """The canonical adjudication record, with the reserved Finding IDs in canonical Finding order."""
    if len(finding_ids) != len(normalized.drafts):
        raise ValidationError("one reserved Finding ID per normalized Finding", code="review_record_invalid")
    by_source: dict[tuple[str, str, int], str] = {}
    findings: list[dict[str, Any]] = []
    for draft, finding_id in zip(normalized.drafts, finding_ids):
        for source in draft.sources:
            by_source[source] = finding_id
        findings.append({
            "finding_id": finding_id, "category": draft.category, "severity": draft.severity,
            "statement": draft.statement, "semantic_surface": draft.semantic_surface,
            "repair_identity": draft.repair_identity,
            "sources": [{"task_id": t, "result_digest": d, "claim_index": i} for t, d, i in draft.sources],
            "disposition": draft.disposition, "blocking": draft.blocking, "relation": draft.relation,
            "linked_finding_ids": list(draft.linked_finding_ids),
            "linked_repair_batch_ids": list(draft.linked_repair_batch_ids),
            "causal_evidence_digest": draft.causal_evidence_digest,
        })
    entries = []
    for entry in normalized.entries:
        source = (entry["task_id"], entry["result_digest"], entry["claim_index"])
        entries.append({**entry, "finding_id": by_source.get(source)})
    entries.sort(key=lambda item: (item["task_id"], item["result_digest"], item["claim_index"]))
    record = {
        serialize.SCHEMA_KEY: records.SCHEMA_P4_ADJUDICATION, serialize.VERSION_KEY: records.VERSION,
        "review_run_id": review_run_id, "review_kind": gate_record.review_kind,
        "target_identity": gate_record.target_identity, "operation_identity": gate_record.operation_identity,
        "candidate_hash": gate_record.candidate_hash, "candidate_generation": candidate_generation,
        "review_context_hash": gate_record.review_context_hash,
        "effective_policy_hash": gate_record.effective_policy_hash,
        "review_contract": review_contract, "adjudication_contract": ADJUDICATION_CONTRACT,
        "instruction": ADJUDICATION_INSTRUCTION, "task_id": str(descriptor["task_id"]),
        "adjudicator_identity": str(descriptor["reviewer_identity"]),
        "adjudicator_version": str(descriptor["reviewer_version"]),
        "reports": [{"task_id": t, "result_digest": d} for t, d, _ in reports],
        "objective_holds": normalized.objective_holds,
        "entries": entries, "findings": findings, "coverage_gaps": [dict(gap) for gap in normalized.gaps],
        "prior": NO_PRIOR if prior is None else prior.prior_record(),
        "outcome": derive_outcome(normalized),
        "obligations": obligations(normalized),
        "repair_purpose": normalized.repair_purpose if derive_outcome(normalized) == REPAIR_REQUIRED else None,
        "strategy_change_class": (
            normalized.strategy_change_class if derive_outcome(normalized) == REPAIR_REQUIRED else None
        ),
    }
    found = records.P4Adjudication.from_record(serialize.canonical_data(record), "the P4 adjudication")
    problems = adjudication_problems(found)
    if problems:
        raise ValidationError("the P4 adjudication is inconsistent: " + "; ".join(problems), code="review_record_invalid")
    return found


def adjudication_problems(found: records.P4Adjudication) -> list[str]:
    """Cross-field consistency a stored adjudication must hold, whether referenced or orphaned."""
    problems: list[str] = []
    bound = {(item["task_id"], item["result_digest"]) for item in found.reports}
    findings = {str(item["finding_id"]): item for item in found.findings}
    named: dict[str, list[tuple[str, str, int]]] = {}
    for entry in found.entries:
        if (entry["task_id"], entry["result_digest"]) not in bound:
            problems.append(f"entry names report {entry['result_digest']} of {entry['task_id']}, which is not bound")
        expected = expected_outcome(entry["supported"], entry["requirement_decision_required"],
                                    entry["fails_requirement"], entry["better_alternative"])
        if entry["outcome"] != expected:
            problems.append(f"entry {entry['claim_index']} of {entry['task_id']} is {entry['outcome']}, not {expected}")
        finding_id = entry["finding_id"]
        if entry["outcome"] in P4_CATEGORIES:
            if finding_id is None or finding_id not in findings:
                problems.append(f"entry {entry['claim_index']} of {entry['task_id']} names no Finding of this record")
            else:
                named.setdefault(finding_id, []).append(
                    (entry["task_id"], entry["result_digest"], entry["claim_index"])
                )
                if findings[finding_id]["category"] != entry["outcome"]:
                    problems.append(f"entry {entry['claim_index']} of {entry['task_id']} and its Finding disagree")
        elif finding_id is not None:
            problems.append(f"a {entry['outcome']} entry names Finding {finding_id}")
    for finding_id, finding in findings.items():
        sources = [(s["task_id"], s["result_digest"], s["claim_index"]) for s in finding["sources"]]
        if sorted(named.get(finding_id, [])) != sources:
            problems.append(f"Finding {finding_id}'s sources are not exactly the entries that name it")
        if finding["blocking"] != is_blocking(finding["category"], finding["severity"], finding["relation"]):
            problems.append(f"Finding {finding_id} says blocking {finding['blocking']} against H-4")
        if finding["blocking"] != (finding["disposition"] == DISPOSITION_REPAIR_REQUIRED):
            problems.append(f"Finding {finding_id}'s disposition does not match its blocking")
    order = [
        (f["semantic_surface"], f["repair_identity"], f["category"],
         tuple((s["task_id"], s["result_digest"], s["claim_index"]) for s in f["sources"]))
        for f in found.findings
    ]
    if order != sorted(order):
        problems.append("the Findings are not in canonical order")
    repair_owner: dict[str, tuple[str, str]] = {}
    for finding in found.findings:
        owner = repair_owner.setdefault(finding["repair_identity"], (finding["category"], finding["semantic_surface"]))
        if owner != (finding["category"], finding["semantic_surface"]):
            problems.append(f"repair identity {finding['repair_identity']} names two Findings")
        elif sum(1 for f in found.findings if f["repair_identity"] == finding["repair_identity"]) > 1:
            problems.append(f"repair identity {finding['repair_identity']} is two Findings")
            break
    entries_view = tuple(found.entries)
    gaps_view = tuple(found.coverage_gaps)
    human = _human_count(entries_view, gaps_view)
    drafts_blocking = [f for f in found.findings if f["blocking"]]
    repairing = drafts_blocking or any(f["disposition"] == DISPOSITION_REPAIRED_CURRENT_CYCLE for f in found.findings)
    expected_outcome_value = HUMAN_WAIT if human else (REPAIR_REQUIRED if repairing else AUTHORIZATION_READY)
    if found.outcome != expected_outcome_value:
        problems.append(f"outcome {found.outcome} is not the obligations' {expected_outcome_value}")
    summary = found.obligations
    if summary["unadjudicated"] != 0:
        problems.append("a stored adjudication leaves a claim unadjudicated")
    if summary["human"] != human:
        problems.append("the HUMAN obligation count is not the entries'")
    if summary["problem_high"] != sum(1 for f in drafts_blocking if f["severity"] == "HIGH"):
        problems.append("the HIGH obligation count is not the Findings'")
    if summary["problem_mid"] != sum(1 for f in drafts_blocking if f["severity"] != "HIGH"):
        problems.append("the MID obligation count is not the Findings'")
    if not found.objective_holds and any(
        f["category"] == OUTCOME_PROBLEM and not f["blocking"] and f["relation"] != RELATION_C_REPAIR_INDUCED
        for f in found.findings
    ):
        problems.append("a LOW Problem is non-blocking while the objective does not hold")
    if not found.objective_holds and found.outcome == AUTHORIZATION_READY:
        problems.append("the objective does not hold and the outcome is authorization-ready")
    return problems


def repair_finding_ids(found: records.P4Adjudication) -> tuple[list[str], list[str]]:
    """The Findings one Repair Batch holds: every blocking Problem, and LOWs deliberately chosen (§27.14)."""
    included: list[str] = []
    deliberate: list[str] = []
    for finding in found.findings:
        if finding["category"] != OUTCOME_PROBLEM:
            continue  # Improvement is never inserted into a mandatory batch
        if finding["blocking"]:
            included.append(str(finding["finding_id"]))
        elif finding["disposition"] == DISPOSITION_REPAIRED_CURRENT_CYCLE:
            included.append(str(finding["finding_id"]))
            deliberate.append(str(finding["finding_id"]))
    return included, deliberate


def repair_batch(
    found: records.P4Adjudication,
    adjudication_digest: str,
    *,
    repair_batch_id: str,
    allowed_result_surface: Sequence[str],
    repair_purpose: str | None = None,
    strategy_change_class: str | None = None,
) -> records.P4RepairBatch:
    """The one Repair Batch of a REPAIR_REQUIRED adjudication (§12.8 / §27.14).

    HUMAN, unsupported, dismissed and Improvement entries are never in it, and
    every decidable blocking Problem is. When the cycle requires STRATEGY_CHANGE
    an ordinary strategy is not representable.
    """
    if found.outcome != REPAIR_REQUIRED:
        raise ValidationError(f"a Repair Batch follows only REPAIR_REQUIRED, not {found.outcome}",
                              code="review_record_invalid")
    included, deliberate = repair_finding_ids(found)
    findings = {str(item["finding_id"]): item for item in found.findings}
    required = bool(found.obligations["strategy_change_required"])
    # The adjudication record is the authority; an explicit argument may only restate it.
    repair_purpose = found.repair_purpose if repair_purpose is None else repair_purpose
    if strategy_change_class is None:
        strategy_change_class = found.strategy_change_class
    strategy = STRATEGY_CHANGE if required or strategy_change_class is not None else STRATEGY_ORDINARY
    record = {
        serialize.SCHEMA_KEY: records.SCHEMA_P4_REPAIR_BATCH, serialize.VERSION_KEY: records.VERSION,
        "repair_batch_id": repair_batch_id, "review_kind": found.review_kind,
        "target_identity": found.target_identity, "operation_identity": found.operation_identity,
        "review_contract": found.review_contract, "source_review_run_id": found.review_run_id,
        "source_candidate_hash": found.candidate_hash, "candidate_generation": found.candidate_generation,
        "adjudication_digest": adjudication_digest, "finding_ids": included,
        "deliberate_low_finding_ids": deliberate,
        "semantic_surfaces": sorted({str(findings[i]["semantic_surface"]) for i in included}),
        "repair_purpose": repair_purpose, "strategy": strategy, "strategy_change_required": required,
        "strategy_change_class": strategy_change_class if strategy == STRATEGY_CHANGE else None,
        "allowed_result_surface": sorted(set(allowed_result_surface)),
        "prior_relations": [
            {
                "finding_id": i, "relation": findings[i]["relation"],
                "linked_finding_ids": list(findings[i]["linked_finding_ids"]),
                "linked_repair_batch_ids": list(findings[i]["linked_repair_batch_ids"]),
            }
            for i in included
        ],
    }
    return records.P4RepairBatch.from_record(serialize.canonical_data(record), "the P4 Repair Batch")


def bc_surfaces(found: records.P4Adjudication) -> frozenset[str]:
    """The semantic surfaces of an adjudication's supported B/C Findings (§12.17)."""
    return frozenset(
        str(item["semantic_surface"]) for item in found.findings
        if item["relation"] in (RELATION_B_RECURRENCE, RELATION_C_REPAIR_INDUCED)
    )


# --------------------------------------------------------------------------- repair settlement (§12.9-§12.15, §27.16-§27.20)

def repair_coverage_problems(check: object) -> list[tuple[str, str]]:
    """``(code, message)`` for a Repair Coverage Check that cannot PASS (§12.15 / §27.17).

    Unknown is never PASS: an unresolved gap, an affected set that is not
    positively enumerable, or one the repair does not cover. A local patch on a
    positively shared responsibility with other sites is the widen-first refusal.
    """
    if type(check) is not P4CoverageCheck:
        return [(CODE_REPAIR_COVERAGE_UNKNOWN, "the repair carries no structured Repair Coverage Check")]
    problems: list[tuple[str, str]] = []
    for name in ("shared_responsibility", "enumerable", "covers_affected_set"):
        if type(getattr(check, name)) is not bool:
            problems.append((CODE_REPAIR_COVERAGE_UNKNOWN, f"the coverage check's {name} is not a boolean"))
    if problems:
        return problems
    if check.repair_scope not in P4_REPAIR_SCOPES:
        problems.append((CODE_REPAIR_COVERAGE_UNKNOWN, f"repair scope {check.repair_scope!r} is not local or widened"))
    for name in ("semantic_behavior_changed", "semantic_responsibility"):
        problem = public_safe_problem(getattr(check, name))
        if problem is not None:
            problems.append((CODE_REPAIR_COVERAGE_UNKNOWN, f"the coverage check's {name}: {problem}"))
    for name in ("other_sites", "affected_set"):
        value = getattr(check, name)
        if not isinstance(value, tuple) or any(public_safe_problem(item) is not None for item in value):
            problems.append((CODE_REPAIR_COVERAGE_UNKNOWN, f"the coverage check's {name} is not public-safe text"))
    if check.unresolved_gap is not None:
        problems.append((CODE_REPAIR_COVERAGE_UNKNOWN, f"the repair leaves a coverage gap: {check.unresolved_gap}"))
    if not check.enumerable:
        problems.append((CODE_REPAIR_COVERAGE_UNKNOWN, "the affected set is not positively enumerable"))
    if not check.covers_affected_set:
        problems.append((CODE_REPAIR_COVERAGE_UNKNOWN, "the repair does not cover the affected set"))
    if check.shared_responsibility and check.repair_scope == "local" and check.other_sites:
        problems.append((
            CODE_REPAIR_WIDEN_REQUIRED,
            "a local patch is presented for a positively shared responsibility with other sites; widen the repair "
            "before another Formal Review round rediscovers the omission",
        ))
    return problems


@dataclass(frozen=True)
class EvidenceReuse:
    evidence_id: str
    reusable: bool
    state: str  # reusable | unknown | invalidated
    reasons: tuple[str, ...]

    def to_record(self) -> dict[str, Any]:
        return {"evidence_id": self.evidence_id, "reusable": self.reusable, "state": self.state,
                "reasons": list(self.reasons)}


def evidence_reuse(
    evidence_id: str,
    prior: closure.EvidenceDeclaration | None,
    new: closure.EvidenceDeclaration | None,
    *,
    prior_identities: Sequence[str],
    new_identities: Sequence[str],
    assumption_invalidated: bool,
) -> EvidenceReuse:
    """§12.13 / §27.18: whether one Evidence may be reused from Candidate N to N+1 - positive proof only.

    Never :func:`closure.may_reuse`, which binds Review provenance including the
    Candidate: a repaired Candidate never inherits Review authorization. Any
    unknown is ``unknown`` (reacquire); any proven change is ``invalidated``.
    """
    if prior is None or new is None:
        return EvidenceReuse(evidence_id, False, "unknown", ("no typed dependency declaration; fresh-use-only",))
    unknown: list[str] = []
    if not prior.complete():
        unknown.append("the prior declaration is incomplete: " + ", ".join(prior.unaccounted()))
    if not new.complete():
        unknown.append("the new declaration is incomplete: " + ", ".join(new.unaccounted()))
    if unknown:
        return EvidenceReuse(evidence_id, False, "unknown", tuple(unknown))
    invalid: list[str] = []
    if (prior.adapter_identity, prior.implementation_version) != (new.adapter_identity, new.implementation_version):
        invalid.append("the adapter identity or version changed")
    if set(prior.required) != set(new.required):
        invalid.append("the required dependency classes changed")
    prior_proofs = {entry.dependency_class: (entry.mode, None if entry.proof is None else entry.proof.to_record())
                    for entry in prior.coverage}
    new_proofs = {entry.dependency_class: (entry.mode, None if entry.proof is None else entry.proof.to_record())
                  for entry in new.coverage}
    if prior_proofs != new_proofs:
        invalid.append("a proof mechanism identity or version changed")
    prior_bound = {entry.dependency_class: tuple(entry.identities) for entry in prior.coverage}
    new_bound = {entry.dependency_class: tuple(entry.identities) for entry in new.coverage}
    if prior_bound != new_bound or tuple(prior_identities) != tuple(new_identities):
        invalid.append("a concrete Evidence-bound identity changed")
    if assumption_invalidated:
        invalid.append("the repair impact invalidates a semantic assumption the Evidence proved")
    if invalid:
        return EvidenceReuse(evidence_id, False, "invalidated", tuple(invalid))
    return EvidenceReuse(evidence_id, True, "reusable", ("every dependency positively proven unchanged",))


def reverification_record(required: Sequence[str], completed: Sequence[P4Verification]) -> dict[str, Any]:
    done = sorted({(item.verification_id, item.result) for item in completed})
    passed = {identifier for identifier, result in done if result == "pass"}
    return {
        "required": sorted(set(required)),
        "completed": [{"id": identifier, "result": result} for identifier, result in done],
        "residual": len(set(required) - passed),
    }


def repair_return_problems(returned: object, descriptor: Mapping[str, Any]) -> list[tuple[str, str]]:
    """The structural refusals of a repair return; an explicit failure is :data:`CODE_REPAIR_FAILED`."""
    if type(returned) is not P4RepairReturn:
        return [(CODE_REPAIR_INVALID, f"the repair actor returned {type(returned).__name__}, not a P4RepairReturn")]
    if returned.task_id != descriptor["task_id"]:
        return [(CODE_REPAIR_INVALID, f"it answers task {returned.task_id!r}, not {descriptor['task_id']}")]
    if (returned.repair_identity, returned.repair_version) != (descriptor["reviewer_identity"], descriptor["reviewer_version"]):
        return [("review_reviewer_mismatch",
                 f"repair task {descriptor['task_id']} was accepted for {descriptor['reviewer_identity']} "
                 f"{descriptor['reviewer_version']}, and the return comes from {returned.repair_identity!r} "
                 f"{returned.repair_version!r}")]
    if returned.status in ("failed", "declined"):
        return [(CODE_REPAIR_FAILED, f"the repair actor {returned.status} the repair; the old Candidate is not authorized")]
    if returned.status != "completed":
        return [(CODE_REPAIR_INVALID, f"repair status {returned.status!r} is not completed, failed or declined")]
    problems: list[tuple[str, str]] = []
    if returned.impact_class not in P4_IMPACT_CLASSES:
        problems.append((CODE_REPAIR_INVALID, f"impact class {returned.impact_class!r} is not one of {P4_IMPACT_CLASSES}"))
    if not isinstance(returned.repaired_surface, tuple) or not returned.repaired_surface \
            or any(public_safe_problem(item) is not None for item in returned.repaired_surface):
        problems.append((CODE_REPAIR_INVALID, "the repaired surface is not a non-empty tuple of public-safe text"))
    if returned.causal_summary is None or public_safe_problem(returned.causal_summary) is not None:
        problems.append((CODE_REPAIR_INVALID, "the causal summary is not public-safe text"))
    if not isinstance(returned.verification, tuple) or any(
        type(item) is not P4Verification or item.result not in records.P4_VERIFICATION_RESULTS
        or public_safe_problem(item.verification_id, limit=records.P4_MAX_LABEL) is not None
        for item in returned.verification
    ):
        problems.append((CODE_REPAIR_INVALID, "the verification results are not P4Verification pass/fail entries"))
    problems.extend(repair_coverage_problems(returned.coverage_check))
    return problems


def repair_result(
    *,
    batch: records.P4RepairBatch,
    source_candidate_generation: int,
    result_candidate_hash: str,
    result_candidate_material_digest: str,
    repair_task_id: str,
    returned: P4RepairReturn,
    evidence: Sequence[EvidenceReuse],
    kind_checks: Sequence[P4Verification],
) -> records.P4RepairResult:
    """The immutable Repair Result of a successful repair (§27.20); STOPs when it cannot be ready.

    Readiness is positive: complete coverage (checked by the caller with
    :func:`repair_return_problems`) and zero residual required verification.
    """
    assert returned.coverage_check is not None and returned.impact_class is not None
    required = reverification_plan(returned.impact_class, [item.verification_id for item in kind_checks])
    reverification = reverification_record(required, tuple(returned.verification) + tuple(kind_checks))
    if reverification["residual"]:
        missing = sorted(set(required) - {item["id"] for item in reverification["completed"] if item["result"] == "pass"})
        raise stop(
            CODE_REVERIFICATION_INCOMPLETE,
            f"the {returned.impact_class} repair leaves required reverification not passed ({', '.join(missing)}); "
            "it cannot be ready for a successor Run, and nothing is settled",
        )
    check = returned.coverage_check.to_record()
    record = {
        serialize.SCHEMA_KEY: records.SCHEMA_P4_REPAIR_RESULT, serialize.VERSION_KEY: records.VERSION,
        "repair_batch_id": batch.repair_batch_id, "review_kind": batch.review_kind,
        "target_identity": batch.target_identity, "operation_identity": batch.operation_identity,
        "review_contract": batch.review_contract, "source_review_run_id": batch.source_review_run_id,
        "source_candidate_hash": batch.source_candidate_hash,
        "source_candidate_generation": source_candidate_generation,
        "result_candidate_hash": result_candidate_hash,
        "result_candidate_generation": source_candidate_generation + 1,
        "result_candidate_material_digest": result_candidate_material_digest,
        "repair_task_id": repair_task_id, "repair_identity": returned.repair_identity,
        "repair_version": returned.repair_version,
        "repaired_surface": sorted(set(returned.repaired_surface)),
        "impact_class": returned.impact_class, "coverage_check": check,
        "coverage_check_digest": serialize.digest(check),
        "evidence_decisions": [item.to_record() for item in sorted(evidence, key=lambda e: e.evidence_id)],
        "reverification": reverification, "reverification_digest": serialize.digest(reverification),
        "causal_summary": returned.causal_summary, "successor_eligible": True,
    }
    return records.P4RepairResult.from_record(serialize.canonical_data(record), "the P4 Repair Result")


def linkage_problems(
    batch: records.P4RepairBatch,
    result: records.P4RepairResult,
    *,
    source_run_id: str,
    source_candidate_hash: str,
    source_candidate_generation: int,
    snapshot_hash: str | None,
    successor_envelope: Mapping[str, Any] | None = None,
    repair_result_digest: str | None = None,
) -> list[str]:
    """G-1 items 1-4 / §27.20-§27.21: the Repair Result, Candidate N+1 and the successor request agree exactly."""
    problems: list[str] = []
    if result.repair_batch_id != batch.repair_batch_id:
        problems.append("the Repair Result names another Repair Batch")
    for name, wanted in (
        ("source_review_run_id", source_run_id), ("source_candidate_hash", source_candidate_hash),
        ("review_kind", batch.review_kind), ("target_identity", batch.target_identity),
        ("operation_identity", batch.operation_identity), ("review_contract", batch.review_contract),
    ):
        if getattr(result, name) != wanted:
            problems.append(f"the Repair Result's {name} is not the source's")
    if batch.source_review_run_id != source_run_id or batch.source_candidate_hash != source_candidate_hash:
        problems.append("the Repair Batch does not name the source Run and Candidate")
    if result.source_candidate_generation != source_candidate_generation or batch.candidate_generation != source_candidate_generation:
        problems.append("the source candidate generation does not agree")
    if result.result_candidate_generation != source_candidate_generation + 1:
        problems.append("the result candidate generation is not the source generation + 1")
    if snapshot_hash != result.result_candidate_hash:
        problems.append("no stored Candidate snapshot hashes to the Repair Result's result candidate")
    if not result.successor_eligible:
        problems.append("the Repair Result is not eligible for a successor Run")
    if successor_envelope is not None:
        succession = successor_envelope.get("succession")
        expected = succession_record(source_run_id, source_candidate_hash, batch.repair_batch_id,
                                     str(repair_result_digest))
        if succession != expected:
            problems.append("the successor request's succession is not exactly the Repair Result linkage")
        if successor_envelope.get("candidate_generation") != result.result_candidate_generation:
            problems.append("the successor request's candidate generation is not the result generation")
        if successor_envelope.get("review_contract") != batch.review_contract:
            problems.append("the successor request names another contract")
        named = [item for item in successor_envelope.get("set_aside_runs") or []
                 if item.get("review_run_id") == source_run_id]
        if named != [{"review_run_id": source_run_id, "reason": SET_ASIDE_REPAIRED}]:
            problems.append("the successor request does not name its predecessor set aside as repaired")
    return problems


# --------------------------------------------------------------------------- convergence (§12.18, §27.12)

@dataclass(frozen=True)
class ConvergenceInput:
    """Every §12.18 condition, each a positive fact the owner established."""

    discovery_settled: bool
    coverage_resolved: bool
    reports_durable: bool
    adjudication_complete: bool
    unadjudicated: int
    problem_high: int
    problem_mid: int
    low_traceable_objective_holds: bool
    improvements_traceable: bool
    human: int
    reverification_complete: bool
    repair_coverage_complete: bool
    repair_induced_unresolved: int
    strategy_change_pending: bool
    evidence_current: bool


def convergence_problems(state: ConvergenceInput) -> list[str]:
    """The unmet §12.18 conditions; empty only when the Candidate may authorize. New findings = 0 is not one."""
    unmet: list[str] = []
    checks = (
        (state.discovery_settled, "a required discovery task is not settled successfully"),
        (state.coverage_resolved, "required coverage is not satisfied or explicitly resolved"),
        (state.reports_durable, "a raw report is not durably present"),
        (state.adjudication_complete, "adjudication is not complete"),
        (state.unadjudicated == 0, "a raw claim is unadjudicated"),
        (state.problem_high == 0, "an unresolved Problem HIGH remains"),
        (state.problem_mid == 0, "an unresolved Problem MID remains"),
        (state.low_traceable_objective_holds, "a Problem LOW is untraceable or the objective does not hold"),
        (state.improvements_traceable, "an Improvement has no traceable disposition"),
        (state.human == 0, "an unresolved HUMAN decision remains"),
        (state.reverification_complete, "required post-repair reverification is incomplete"),
        (state.repair_coverage_complete, "the latest Repair Coverage Check is incomplete"),
        (state.repair_induced_unresolved == 0, "an unresolved repair-induced Problem remains"),
        (not state.strategy_change_pending, "a required STRATEGY_CHANGE is unperformed"),
        (state.evidence_current, "Evidence used for authorization is not current"),
    )
    for held, message in checks:
        if not held:
            unmet.append(message)
    return unmet


def convergence_of(found: records.P4Adjudication, prior_result: records.P4RepairResult | None, *,
                   reports_durable: bool, evidence_current: bool) -> ConvergenceInput:
    """The §12.18 facts of a stored adjudication plus the cycle's latest Repair Result."""
    summary = found.obligations
    return ConvergenceInput(
        discovery_settled=True,
        coverage_resolved=summary["coverage_unresolved"] == 0,
        reports_durable=reports_durable,
        adjudication_complete=True,
        unadjudicated=summary["unadjudicated"],
        problem_high=summary["problem_high"],
        problem_mid=summary["problem_mid"],
        low_traceable_objective_holds=found.objective_holds or summary["problem_low"] == 0,
        improvements_traceable=all(
            f["disposition"] in P4_NONBLOCKING_DISPOSITIONS for f in found.findings if f["category"] == OUTCOME_IMPROVEMENT
        ),
        human=summary["human"],
        reverification_complete=prior_result is None or prior_result.reverification["residual"] == 0,
        repair_coverage_complete=prior_result is None or (
            prior_result.coverage_check["unresolved_gap"] is None and prior_result.coverage_check["enumerable"]
            and prior_result.coverage_check["covers_affected_set"]
        ),
        repair_induced_unresolved=sum(
            1 for f in found.findings if f["relation"] == RELATION_C_REPAIR_INDUCED and f["blocking"]
        ),
        strategy_change_pending=bool(summary["strategy_change_required"]) and found.outcome != AUTHORIZATION_READY,
        evidence_current=evidence_current,
    )


# --------------------------------------------------------------------------- verification-only Integration (§12.20, §27.25)

@dataclass(frozen=True)
class IntegrationDeclaration:
    """An Integration Evidence adapter's declared side-effect contract."""

    adapter_identity: str
    allowed_project_state: tuple[str, ...]
    allowed_external_state: tuple[str, ...]
    allowed_nested_state: tuple[str, ...]
    isolation_mechanism: closure.MechanismProof | None
    disposal_proven: bool


@dataclass(frozen=True)
class IntegrationObservation:
    """What a verification actually mutated persistently."""

    project_mutations: tuple[str, ...] = ()
    external_mutations: tuple[str, ...] = ()
    nested_mutations: tuple[str, ...] = ()
    #: Nested mutations whose only authorization is a gitlink identity.
    gitlink_only_nested: tuple[str, ...] = ()


INTEGRATION_FIX_ROUTE = "normal_fix_work"


def integration_problems(declaration: IntegrationDeclaration, observed: IntegrationObservation) -> list[str]:
    """Why an Integration result cannot PASS as verification-only; empty when it may (§12.20).

    Verification-only = no persistent mutation of Project domain state and none
    of undeclared external or nested state. Disposable or rolled-back effects
    support PASS only when the isolation mechanism is declared, typed, and the
    disposal was positively proven. A gitlink identity never authorizes
    mutating a nested working tree.
    """
    problems: list[str] = []
    if declaration.allowed_project_state:
        problems.append("a verification-only adapter allows no persistent Project state")
    if observed.project_mutations:
        problems.append("verification mutated Project domain state: " + ", ".join(observed.project_mutations))
    isolated = (
        declaration.isolation_mechanism is not None and declaration.isolation_mechanism.well_formed
        and declaration.disposal_proven
    )
    undeclared_external = [item for item in observed.external_mutations if item not in declaration.allowed_external_state]
    if undeclared_external:
        problems.append("verification mutated undeclared external state: " + ", ".join(undeclared_external))
    elif observed.external_mutations and not isolated:
        problems.append("declared external mutation has no proven isolation or disposal")
    if observed.gitlink_only_nested:
        problems.append("a gitlink identity does not authorize nested working-tree mutation: "
                        + ", ".join(observed.gitlink_only_nested))
    undeclared_nested = [item for item in observed.nested_mutations if item not in declaration.allowed_nested_state]
    if undeclared_nested:
        problems.append("verification mutated an undeclared nested repository: " + ", ".join(undeclared_nested))
    elif observed.nested_mutations and not isolated:
        problems.append("declared nested mutation has no proven isolation or disposal")
    return problems


def integration_repair_route(problems_found: Sequence[str]) -> str:
    """Integration that reveals a required domain repair routes to a normal fix Work - never to Review (§12.20)."""
    return INTEGRATION_FIX_ROUTE


# --------------------------------------------------------------------------- the P4 chain shape and state (§27.22, G-3)

SHAPE_SEAL = "seal"
SHAPE_REPAIR = "repair"

STATE_G1 = "g1_discovery_accepted"
STATE_G2 = "g2_discovery_settled"
STATE_G3 = "g3_adjudication_accepted"
STATE_G4_READY = "g4_authorization_ready"
STATE_G4_HUMAN = "g4_human_wait"
STATE_G4_REPAIR = "g4_repair_required"
STATE_G5_SEALED = "g5_sealed"
STATE_G5_REPAIR = "g5_repair_accepted"
STATE_G6_SETTLED = "g6_repair_settled"
STATE_G6_INVALIDATED = "g6_invalidated"
RUN_STATES = (
    STATE_G1, STATE_G2, STATE_G3, STATE_G4_READY, STATE_G4_HUMAN, STATE_G4_REPAIR, STATE_G5_SEALED, STATE_G5_REPAIR,
    STATE_G6_SETTLED, STATE_G6_INVALIDATED,
)
#: Cycle-level states (§27.22): a successor reserved and not yet at G1, a successor active, and malformed.
STATE_SUCCESSOR_RESERVED = "successor_reserved"
STATE_SUCCESSOR_ACTIVE = "successor_active"
STATE_MALFORMED = "malformed_linkage"


def _tasks_of_kind(tasks: Sequence[Mapping[str, Any]], task_kind: str) -> list[Mapping[str, Any]]:
    return [task for task in tasks if task["task_kind"] == task_kind]


def chain_problems(chain: Any) -> list[str]:
    """Every way a validated gate chain is not one of the P4 shapes (§12.6, §27.31, G-3).

    Read from canonical records: the task kinds of the accepted descriptors,
    the seal status and the settlements. Generation 5 is a seal exactly when
    it is sealed with no new task, and an accepted repair exactly when it is
    open and accepts one repair task; generation 6 settles that repair, or is
    the open invalidation of the generation-5 seal. There is no generation 7.
    """
    gens = list(chain.generations)
    problems: list[str] = []
    if len(gens) > LAST_GENERATION:
        return [f"{len(gens)} generations; a P4 Run has at most {LAST_GENERATION} and no generation 7"]
    first = gens[0]
    for found in gens[1:]:
        for name in ("candidate_hash", "operation_identity", "review_context_hash", "effective_policy_hash"):
            if getattr(found, name) != getattr(first, name):
                problems.append(f"generation {found.generation} changes {name}; a Run is bound to one Candidate")
    discovery = _tasks_of_kind(first.accepted_tasks, TASK_KIND_DISCOVERY)
    if first.status != records.GATE_STATUS_OPEN or not discovery or len(discovery) != len(first.accepted_tasks) \
            or first.settled_tasks:
        problems.append("generation 1 is not the open acceptance of discovery task(s) only")
    if any(not str(task["task_slot"]).startswith(P4_DISCOVERY_SLOT_PREFIX) for task in discovery):
        problems.append("generation 1 accepts a discovery task outside a P4 discovery slot")
    if len(gens) >= 2:
        second = gens[1]
        if second.status != records.GATE_STATUS_OPEN or second.accepted_tasks != first.accepted_tasks \
                or sorted(second.settled_task_ids()) != sorted(first.accepted_task_ids()):
            problems.append("generation 2 is not the open settlement of exactly the discovery tasks")
    if len(gens) >= 3:
        third = gens[2]
        added = [task for task in third.accepted_tasks if task not in gens[1].accepted_tasks]
        if third.status != records.GATE_STATUS_OPEN or third.settled_tasks != gens[1].settled_tasks \
                or len(added) != 1 or added[0]["task_kind"] != TASK_KIND_ADJUDICATION \
                or added[0]["task_slot"] != SLOT_ADJUDICATOR:
            problems.append("generation 3 is not the open acceptance of one adjudication task")
    if len(gens) >= 4:
        fourth = gens[3]
        newly = [task for task in fourth.settled_tasks if task not in gens[2].settled_tasks]
        adjudication_ids = {str(task["task_id"]) for task in _tasks_of_kind(gens[2].accepted_tasks, TASK_KIND_ADJUDICATION)}
        if fourth.status != records.GATE_STATUS_OPEN or fourth.accepted_tasks != gens[2].accepted_tasks \
                or len(newly) != 1 or str(newly[0]["task_id"]) not in adjudication_ids:
            problems.append("generation 4 is not the open settlement of the adjudication task")
    shape = None
    if len(gens) >= 5:
        fifth = gens[4]
        added = [task for task in fifth.accepted_tasks if task not in gens[3].accepted_tasks]
        if fifth.sealed and not added and fifth.settled_tasks == gens[3].settled_tasks and fifth.receipt_id:
            shape = SHAPE_SEAL
        elif fifth.status == records.GATE_STATUS_OPEN and len(added) == 1 \
                and added[0]["task_kind"] == TASK_KIND_REPAIR and added[0]["task_slot"] == SLOT_REPAIR \
                and fifth.settled_tasks == gens[3].settled_tasks and fifth.receipt_id is None:
            shape = SHAPE_REPAIR
        else:
            problems.append("generation 5 is neither the seal issuing a Receipt nor the acceptance of one repair task")
    if len(gens) >= 6 and shape is not None:
        sixth = gens[5]
        fifth = gens[4]
        if shape == SHAPE_SEAL:
            if sixth.status != records.GATE_STATUS_OPEN or sixth.accepted_tasks != fifth.accepted_tasks \
                    or sixth.settled_tasks != fifth.settled_tasks or sixth.receipt_id is not None:
                problems.append("generation 6 after a seal is not the open invalidation of it")
        else:
            newly = [task for task in sixth.settled_tasks if task not in fifth.settled_tasks]
            repair_ids = {str(task["task_id"]) for task in _tasks_of_kind(fifth.accepted_tasks, TASK_KIND_REPAIR)}
            if sixth.status != records.GATE_STATUS_OPEN or sixth.accepted_tasks != fifth.accepted_tasks \
                    or len(newly) != 1 or str(newly[0]["task_id"]) not in repair_ids:
                problems.append("generation 6 after a repair acceptance is not the open settlement of the repair")
    return problems


def shape_of(chain: Any) -> str | None:
    """``seal`` or ``repair`` once generation 5 exists (read from its records); ``None`` before."""
    if len(chain.generations) < 5:
        return None
    return SHAPE_SEAL if chain.generations[4].sealed else SHAPE_REPAIR


def run_state(chain: Any, adjudication_outcome: str | None) -> str:
    """The P4 per-Run state of a chain that passed :func:`chain_problems` (§27.22)."""
    latest = chain.latest.generation
    if latest == 1:
        return STATE_G1
    if latest == 2:
        return STATE_G2
    if latest == 3:
        return STATE_G3
    if latest == 4:
        return {AUTHORIZATION_READY: STATE_G4_READY, HUMAN_WAIT: STATE_G4_HUMAN,
                REPAIR_REQUIRED: STATE_G4_REPAIR}.get(str(adjudication_outcome), STATE_MALFORMED)
    if latest == 5:
        return STATE_G5_SEALED if shape_of(chain) == SHAPE_SEAL else STATE_G5_REPAIR
    return STATE_G6_INVALIDATED if shape_of(chain) == SHAPE_SEAL else STATE_G6_SETTLED


def discovery_tasks(chain: Any) -> list[Mapping[str, Any]]:
    return _tasks_of_kind(chain.generations[0].accepted_tasks, TASK_KIND_DISCOVERY)


def adjudication_task(chain: Any) -> Mapping[str, Any] | None:
    found = _tasks_of_kind(chain.latest.accepted_tasks, TASK_KIND_ADJUDICATION)
    return found[0] if found else None


def repair_task(chain: Any) -> Mapping[str, Any] | None:
    found = _tasks_of_kind(chain.latest.accepted_tasks, TASK_KIND_REPAIR)
    return found[0] if found else None


def settled_of(chain: Any, task_id: str) -> Mapping[str, Any] | None:
    for task in chain.latest.settled_tasks:
        if str(task["task_id"]) == task_id:
            return task
    return None


# --------------------------------------------------------------------------- set aside by a proven successor (G-2)

def _successor_envelope(reader: Any, chain: Any) -> dict[str, Any] | None:
    first = chain.generations[0]
    if not first.accepted_tasks:
        return None
    found = reader.read_task_input(str(first.accepted_tasks[0]["task_id"]))
    return found.request_envelope if contract_of_task_input(found) is not None else None


def named_by_successor(reader: Any, predecessor_id: str) -> bool:
    """Whether any Run's P4 discovery request names ``predecessor_id`` as its repaired predecessor."""
    try:
        for run_id in reader.run_ids():
            chain = reader.gate_chain(run_id)
            envelope = None if chain is None else _successor_envelope(reader, chain)
            if envelope is not None and (envelope.get("succession") or {}).get("predecessor_review_run_id") == predecessor_id:
                return True
    except (ValidationError, KeyError, TypeError):
        return True  # what cannot be read cannot be shown not to name it
    return False


def proven_successor(reader: Any, predecessor_id: str, chain: Any) -> str | None:
    """The one successor Run that positively replaces a P4 predecessor, or ``None`` (G-2, §27.21).

    ``reader`` is any read-only Review reader (the working tree's, or one
    commit's committed records). All five conditions are positive proof:

    1. the predecessor is a P4 Run whose generation 6 settled its repair;
    2. its committed successful Repair Result links to exactly one successor;
    3. that successor's request names the predecessor set aside as repaired;
    4. the predecessor has no Receipt, so no registration Consumption or
       registration commit of its own, and no Consumption names it;
    5. candidate, Run, batch and successor identities round-trip and agree.

    Anything missing, unreadable, ambiguous or contradictory is ``None``: the
    predecessor is then never treated as set aside.
    """
    try:
        contracts = {contract_of_task_input(reader.read_task_input(str(task["task_id"])))
                     for task in chain.generations[0].accepted_tasks}
        if len(contracts) != 1 or None in contracts or chain_problems(chain):
            return None
        if shape_of(chain) != SHAPE_REPAIR or len(chain.generations) != REPAIR_SETTLE_GENERATION:
            return None
        if any(generation.receipt_id for generation in chain.generations):
            return None
        repair = repair_task(chain)
        settled = None if repair is None else settled_of(chain, str(repair["task_id"]))
        if settled is None or settled["status"] != records.TASK_SETTLED_OK:
            return None
        batch_id = str(reader.read_task_input(str(repair["task_id"])).request_envelope.get("repair_batch_id"))
        batch = reader.read_repair_batch(batch_id)
        result = reader.read_repair_result(batch_id)
        result_digest = reader.repair_result_digest(batch_id)
        if settled["result_digest"] != result_digest:
            return None
        predecessor_envelope = _successor_envelope(reader, chain) or {}
        first = chain.generations[0]
        found: list[str] = []
        for run_id in reader.run_ids():
            if run_id == predecessor_id:
                continue
            other = reader.gate_chain(run_id)
            envelope = None if other is None else _successor_envelope(reader, other)
            if envelope is None or (envelope.get("succession") or {}).get("predecessor_review_run_id") != predecessor_id:
                continue
            successor_first = other.generations[0]
            problems = linkage_problems(
                batch, result, source_run_id=predecessor_id, source_candidate_hash=first.candidate_hash,
                source_candidate_generation=int(predecessor_envelope.get("candidate_generation") or 0),
                snapshot_hash=successor_first.candidate_hash if reader.candidate_snapshot_exists(successor_first.candidate_hash) else None,
                successor_envelope=envelope, repair_result_digest=result_digest,
            )
            if problems or run_contracts(reader, other) != contracts or (
                successor_first.operation_identity, successor_first.target_identity, successor_first.review_kind
            ) != (first.operation_identity, first.target_identity, first.review_kind):
                return None  # a contradictory successor: never a proof
            found.append(run_id)
        if len(found) != 1:
            return None
        if any(consumption.review_run_id == predecessor_id for consumption in reader.consumptions()):
            return None
        return found[0]
    except (ValidationError, KeyError, TypeError, ValueError):
        return None


def run_contracts(reader: Any, chain: Any) -> set[str | None]:
    return {contract_of_task_input(reader.read_task_input(str(task["task_id"])))
            for task in chain.generations[0].accepted_tasks}
