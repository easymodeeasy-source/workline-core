"""Phase Integration Review (``WORKLINE_COMPLETION_SPRINT`` §14.4 - §14.16 / §32.17 - §32.29): the semantic model.

Inert, exactly as :mod:`workline.review.p4` is: no Project lock, no mutation, no
filesystem write, no Git and no lifecycle transition. Review verifies,
adjudicates and authorizes; START owns the integration Work's lifecycle, the
domain fix Works, the confirmation structure and every structure change, and
Roadmap owns achievement. Only Review-side facts live here.

```text
identity     review kind phase-integration-v1, target = the integration Work ID,
             authorized stage phase-integration:terminal (§32.19)
outcome      objectively_satisfied | human_confirmation_required | not_satisfied |
             desired_state_change_required, bound to the canonical Phase objective
             by digest and cross-checked against the P4 adjudication outcome (§14.12, §32.21)
branch       HUMAN_WAIT > DOMAIN_REPAIR_REQUIRED > CONFIRMATION_STRUCTURE_REQUIRED >
             AUTHORIZATION_READY, after G4, never by severity text (§32.22)
Candidate    the strict clone-safe Phase Integration Candidate schema, internal
             consistency and hash (§32.17 - §32.18)
repair facts the blocking obligation context, strategy identity, STRATEGY_CHANGE
             reuse facts and fix provenance (§32.25 - §32.26, §32.50)
side effects verification-only: P4's contract plus a positive proof that is not
             the verifier's self-report (§14.10, §32.29)
```

START's side of repair planning (``IntegrationRepairPlan`` over START's
``Derive``) and the deterministic confirmation builder live in
:mod:`workline.start_integration_review`.

Not here, and deferred to their owners: the review kind / stage / Consumption
registration in the shared Review dispatch, the Integration Consumption
(version 5, allocation A-1), the carriage of the Phase outcome inside the stored
adjudication, the derivation of this kind's P4 G4 state / seal permission / P5
disposition from :func:`integration_branch`, the Effective Policy (the Candidate
binds a policy hash it is given, never one it computes) and every START hook.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

from ..errors import ValidationError
from ..ids import is_valid_id
from ..store import CONDITIONAL_RELATED_TYPES, RELATED_TYPES, WORK_KINDS
from . import p4, records, serialize

# --------------------------------------------------------------------------- identity (§32.19)

REVIEW_KIND = "phase-integration-v1"
#: The one operation stage a Phase Integration Receipt authorizes: START's integration terminal stage.
AUTHORIZED_OPERATION_STAGE = "phase-integration:terminal"
#: What ``target_identity`` names for this kind.
TARGET_IDENTITY_KIND = "work"

# --------------------------------------------------------------------------- Phase outcome (§14.12, §32.21)

OBJECTIVELY_SATISFIED = "objectively_satisfied"
HUMAN_CONFIRMATION_REQUIRED = "human_confirmation_required"
NOT_SATISFIED = "not_satisfied"
DESIRED_STATE_CHANGE_REQUIRED = "desired_state_change_required"
PHASE_OUTCOMES = (OBJECTIVELY_SATISFIED, HUMAN_CONFIRMATION_REQUIRED, NOT_SATISFIED, DESIRED_STATE_CHANGE_REQUIRED)
#: The outcomes under which the integration may complete (the second only with a modeled downstream confirmation).
AUTHORIZING_PHASE_OUTCOMES = (OBJECTIVELY_SATISFIED, HUMAN_CONFIRMATION_REQUIRED)

# --------------------------------------------------------------------------- branches after G4 (§32.20, §32.22)

BRANCH_HUMAN_WAIT = records.HUMAN_WAIT
BRANCH_DOMAIN_REPAIR_REQUIRED = "DOMAIN_REPAIR_REQUIRED"
BRANCH_CONFIRMATION_STRUCTURE_REQUIRED = "CONFIRMATION_STRUCTURE_REQUIRED"
BRANCH_AUTHORIZATION_READY = records.AUTHORIZATION_READY
BRANCHES = (
    BRANCH_HUMAN_WAIT, BRANCH_DOMAIN_REPAIR_REQUIRED, BRANCH_CONFIRMATION_STRUCTURE_REQUIRED, BRANCH_AUTHORIZATION_READY,
)
#: Only this branch seals G5 and issues a Receipt; every other one is a terminal G4 disposition with no Receipt.
RECEIPT_BRANCHES = (BRANCH_AUTHORIZATION_READY,)

# --------------------------------------------------------------------------- codes

#: A settled adjudication whose Phase outcome and P4 outcome / obligations contradict each other.
CODE_ADJUDICATION_INCONSISTENT = "review_record_invalid"
#: An invalid_uncovered Work: a structural Project defect (§14.6 "prevents authorization"), never a corrupt record.
CODE_UNCOVERED = "phase_integration_uncovered"
#: Coverage / Evidence / H-4 convergence does not hold: nothing is authorized, nothing is corrupt.
CODE_NOT_AUTHORIZABLE = "phase_integration_not_authorizable"

_LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/+-]*")
#: A repair strategy identity: structured and public-safe, never prose (§32.26).
STRATEGY_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,127}")
#: The opening lifecycle events START's own uncommitted projection of the integration may hold (§32.17).
OPENING_EVENTS = ("work_started", "work_resumed", "work_target_added")


def _invalid(message: str, code: str = CODE_ADJUDICATION_INCONSISTENT) -> ValidationError:
    return ValidationError(message, code=code)


def _label_problem(value: object, described: str) -> str | None:
    problem = records.public_safe_problem(value, limit=records.P4_MAX_LABEL)
    if problem is not None:
        return f"{described} is not a public-safe label: {problem}"
    if _LABEL_RE.fullmatch(str(value)) is None:
        return f"{described} {value!r} is not a structured identity"
    return None


def _digest_problem(value: object, described: str) -> str | None:
    if not isinstance(value, str) or records.DIGEST_RE.fullmatch(value) is None:
        return f"{described} {value!r} is not a lowercase hex SHA-256"
    return None


def _object_id_problem(value: object, described: str) -> str | None:
    """A full Git object ID exactly as the canonical owner accepts it (SHA-1 or SHA-256: ``records._FULL_COMMIT``)."""
    if not isinstance(value, str) or records._FULL_COMMIT.fullmatch(value) is None:
        return f"{described} {value!r} is not a full object ID"
    return None


def _id_problem(value: object, kind: str, described: str) -> str | None:
    if not isinstance(value, str) or not is_valid_id(value, kind):
        return f"{described} {value!r} is not a {kind} ID"
    return None


def _count_problem(value: object, described: str) -> str | None:
    if type(value) is not int or value < 0:
        return f"{described} {value!r} is not a count"
    return None


def _sorted_unique(items: Sequence[Any]) -> bool:
    try:
        return list(items) == sorted(set(items))
    except TypeError:
        return False


def _member(value: object, members: set[Any]) -> bool:
    """``value in members``; an unhashable ``value`` is not a member (its own check reports it; never a TypeError)."""
    try:
        return value in members
    except TypeError:
        return False


# --------------------------------------------------------------------------- the Phase outcome record

@dataclass(frozen=True)
class PhaseOutcome:
    """The one Phase desired-state outcome an Integration adjudication carries (§32.21).

    It names the canonical Phase objective by its desired-state digest and
    holds no desired-state text: reviewer prose cannot redefine the objective.
    ``unmet_objective_obligations`` are the explicit, structured unmet
    objective obligations a ``not_satisfied`` outcome may rest on.
    """

    outcome: str
    phase_desired_state_digest: str
    rationale: str
    unmet_objective_obligations: tuple[str, ...] = ()

    def to_record(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "phase_desired_state_digest": self.phase_desired_state_digest,
            "rationale": self.rationale,
            "unmet_objective_obligations": list(self.unmet_objective_obligations),
        }

    @property
    def digest(self) -> str:
        return serialize.digest(self.to_record())

    @classmethod
    def from_record(cls, record: object) -> "PhaseOutcome":
        fields = ("outcome", "phase_desired_state_digest", "rationale", "unmet_objective_obligations")
        if not isinstance(record, dict) or set(record) != set(fields):
            raise _invalid("a Phase outcome record holds exactly outcome, phase_desired_state_digest, rationale and "
                           "unmet_objective_obligations")
        obligations = record["unmet_objective_obligations"]
        if not isinstance(obligations, list):
            raise _invalid("a Phase outcome's unmet_objective_obligations is a list")
        return cls(record["outcome"], record["phase_desired_state_digest"], record["rationale"], tuple(obligations))


def phase_outcome_problems(
    outcome: PhaseOutcome,
    *,
    candidate_desired_state_digest: str,
    p4_outcome: str,
    blocking_problems: int,
    human_obligations: int,
) -> list[str]:
    """Why ``outcome`` is not a valid Integration adjudication outcome for this Candidate and P4 adjudication.

    Empty when it is. Checked together, because the Phase outcome and the P4
    outcome of the same settled adjudication must tell one story (RB5B-M1 / M2):

    * exactly one of the four outcomes, bound to the Candidate's canonical Phase
      objective by its desired-state digest; an H-3 public-safe rationale;
    * ``not_satisfied`` rests on at least one blocking Problem HIGH/MID or an
      explicit unmet objective obligation, and only ``not_satisfied`` carries one;
    * the P4 outcome agrees with its own counts: AUTHORIZATION_READY has no
      blocking and no HUMAN obligation, REPAIR_REQUIRED has a blocking one (this
      kind never uses P4's in-Review repair, so a repair obligation without a
      blocking Problem - e.g. a LOW ``repaired_current_cycle`` - is refused),
      HUMAN_WAIT has a HUMAN one, and a HUMAN obligation is always HUMAN_WAIT
      (RB5FB-2: §32.22 step 1 precedes domain repair, so a HUMAN obligation
      under any other P4 outcome derives no branch);
    * ``desired_state_change_required`` stands only on a P4 HUMAN_WAIT with a
      HUMAN obligation (so P4's G4 HUMAN_WAIT machinery recognises the Run);
    * ``objectively_satisfied`` / ``human_confirmation_required`` stand with no
      blocking Problem.
    """
    problems: list[str | None] = [
        None if outcome.outcome in PHASE_OUTCOMES else f"outcome {outcome.outcome!r} is not one of {', '.join(PHASE_OUTCOMES)}",
        None if outcome.phase_desired_state_digest == candidate_desired_state_digest else
        "the outcome is not about the Candidate's canonical Phase desired state (digest differs)",
        None if records.public_safe_problem(outcome.rationale) is None else
        f"the outcome rationale is not public-safe: {records.public_safe_problem(outcome.rationale)}",
        None if p4_outcome in records.P4_ADJUDICATION_OUTCOMES else
        f"P4 outcome {p4_outcome!r} is not one of {', '.join(records.P4_ADJUDICATION_OUTCOMES)}",
        _count_problem(blocking_problems, "blocking_problems"),
        _count_problem(human_obligations, "human_obligations"),
    ]
    obligations = outcome.unmet_objective_obligations
    if not isinstance(obligations, tuple) or not _sorted_unique(obligations):
        problems.append("unmet_objective_obligations is not a sorted unique tuple")
        obligations = ()
    else:
        problems += [_label_problem(item, "unmet objective obligation") for item in obligations]
    if any(problem is not None for problem in problems):
        return [problem for problem in problems if problem is not None]
    if outcome.outcome == NOT_SATISFIED and not obligations and not blocking_problems:
        problems.append("not_satisfied is supported by no blocking Problem HIGH/MID and no explicit unmet objective "
                        "obligation")
    if outcome.outcome != NOT_SATISFIED and obligations:
        problems.append(f"{outcome.outcome} cannot carry an unmet objective obligation")
    if p4_outcome == records.AUTHORIZATION_READY and (blocking_problems or human_obligations):
        problems.append("P4 AUTHORIZATION_READY with an open blocking or HUMAN obligation")
    if p4_outcome == records.REPAIR_REQUIRED and not blocking_problems:
        problems.append("P4 REPAIR_REQUIRED without a blocking Problem: phase-integration-v1 never uses the in-Review "
                        "repair (e.g. repaired_current_cycle); domain repair needs blocking support")
    if p4_outcome == records.HUMAN_WAIT and not human_obligations:
        problems.append("P4 HUMAN_WAIT without a HUMAN obligation")
    if p4_outcome != records.HUMAN_WAIT and human_obligations:
        problems.append(f"P4 {p4_outcome} with {human_obligations} open HUMAN obligation(s): a HUMAN obligation is P4 "
                        "HUMAN_WAIT, and §32.22 step 1 (HUMAN) precedes domain repair")
    if outcome.outcome == DESIRED_STATE_CHANGE_REQUIRED and p4_outcome != records.HUMAN_WAIT:
        problems.append(f"desired_state_change_required over P4 {p4_outcome}: a desired-state change routes HUMAN, so "
                        "the adjudication records a HUMAN obligation (P4 HUMAN_WAIT)")
    if outcome.outcome in AUTHORIZING_PHASE_OUTCOMES and blocking_problems:
        problems.append(f"{outcome.outcome} with {blocking_problems} blocking Problem(s) is self-contradictory")
    return [problem for problem in problems if problem is not None]


# --------------------------------------------------------------------------- branch precedence (§32.22)

def integration_branch(
    *,
    p4_outcome: str,
    phase_outcome: PhaseOutcome,
    candidate_desired_state_digest: str,
    blocking_problems: int,
    human_obligations: int,
    valid_downstream_confirmation: bool,
    invalid_uncovered: Sequence[str],
    evidence_current: bool,
) -> str:
    """The one branch a settled (G4) Integration adjudication derives, in the frozen order.

    1. unresolved requirement / HUMAN or ``desired_state_change_required`` -> HUMAN_WAIT;
    2. blocking Problem HIGH/MID or ``not_satisfied`` -> DOMAIN_REPAIR_REQUIRED;
    3. ``human_confirmation_required`` with no valid downstream confirmation -> CONFIRMATION_STRUCTURE_REQUIRED;
    4. otherwise, when coverage / evidence / H-4 convergence holds -> AUTHORIZATION_READY.

    The adjudication is first checked for consistency
    (:func:`phase_outcome_problems`): an inconsistent one derives nothing. So
    DOMAIN_REPAIR_REQUIRED is reached only with blocking support - a blocking
    Problem or an explicit unmet objective obligation - never from a raw P4
    REPAIR_REQUIRED. At step 4 an ``invalid_uncovered`` Work is a structural
    Project defect (``phase_integration_uncovered``) and missing coverage /
    evidence currency is ``phase_integration_not_authorizable``; neither is
    reported as a corrupt Review record.
    """
    problems = phase_outcome_problems(
        phase_outcome, candidate_desired_state_digest=candidate_desired_state_digest, p4_outcome=p4_outcome,
        blocking_problems=blocking_problems, human_obligations=human_obligations,
    )
    if problems:
        raise _invalid("the Integration adjudication is not consistent in itself: " + "; ".join(problems))
    if p4_outcome == records.HUMAN_WAIT or phase_outcome.outcome == DESIRED_STATE_CHANGE_REQUIRED:
        return BRANCH_HUMAN_WAIT
    if blocking_problems or phase_outcome.outcome == NOT_SATISFIED:
        return BRANCH_DOMAIN_REPAIR_REQUIRED
    if phase_outcome.outcome == HUMAN_CONFIRMATION_REQUIRED and valid_downstream_confirmation is not True:
        return BRANCH_CONFIRMATION_STRUCTURE_REQUIRED
    if invalid_uncovered:
        raise _invalid("invalid_uncovered Work " + ", ".join(sorted(invalid_uncovered))
                       + " is a structural defect: the integration cannot be authorized", CODE_UNCOVERED)
    if evidence_current is not True:
        raise _invalid("the Integration Review's coverage / evidence is not current: nothing is authorized",
                       CODE_NOT_AUTHORIZABLE)
    return BRANCH_AUTHORIZATION_READY


def branch_issues_receipt(branch: str) -> bool:
    """Whether a G4 branch seals G5 and issues a Receipt (only AUTHORIZATION_READY does, §32.20)."""
    if branch not in BRANCHES:
        raise _invalid(f"{branch!r} is not a Phase Integration branch")
    return branch in RECEIPT_BRANCHES


# --------------------------------------------------------------------------- the Phase Integration Candidate (§32.17 - §32.18)

SCHEMA_CANDIDATE = "review-phase-integration-candidate"
RECORD_VERSION = 1

CANDIDATE_FIELDS = (
    serialize.SCHEMA_KEY, serialize.VERSION_KEY, "review_kind", "phase_id", "roadmap_id", "phase_desired_state_digest",
    "integration", "base", "effective_work_ids", "works", "dependencies", "coverage", "downstream_confirmation_ids",
    "related_authority_refs", "work_review_refs", "achievement_evidence_refs", "structural_validation_digest",
    "review_context_digest", "effective_policy_hash", "candidate_generation", "owning_operation",
)
_INTEGRATION_FIELDS = ("work_id", "work_kind", "phase_review_contract", "desired_state_digest")
_BASE_FIELDS = ("commit", "branch")
_WORK_FIELDS = ("work_id", "work_kind", "phase_review_contract", "confirmation_target", "desired_state_digest", "state",
                "terminal_event_id")
_DEPENDENCY_FIELDS = ("relation_id", "from", "to")
_COVERAGE_FIELDS = ("version", "classes")
_CLASS_FIELDS = ("work_id", "class")
_RELATED_FIELDS = ("relation_id", "type", "from", "to", "condition")
_WORK_REVIEW_FIELDS = ("work_id", "review_run_id", "run_summary_digest")
#: One available achievement evidence reference (§14.5), shaped as ``achievement.RoadmapBasis.phase_evidence_refs``.
_ACHIEVEMENT_REF_FIELDS = ("phase_id", "achievement_evidence_id", "evidence_digest")
_OWNING_FIELDS = ("mutation_id", "terminal_stage", "lifecycle_projection")
_LIFECYCLE_FIELDS = ("event_id", "type", "entity")


def _fields_problem(record: object, expected: tuple[str, ...], described: str) -> str | None:
    if not isinstance(record, dict):
        return f"{described} is not a mapping"
    if set(record) != set(expected):
        return f"{described} does not hold exactly {', '.join(expected)}"
    return None


def _list(candidate: Mapping[str, Any], key: str, found: list[str | None]) -> list[Any]:
    value = candidate[key]
    if not isinstance(value, list):
        found.append(f"{key} is not a list")
        return []
    return value


def _work_entry_problems(work: dict[str, Any], v1: str, states: tuple[str, ...]) -> list[str | None]:
    kind, marker, target = work["work_kind"], work["phase_review_contract"], work["confirmation_target"]
    where = f"Candidate Work {work['work_id']!r}"
    found: list[str | None] = [
        _id_problem(work["work_id"], "work", f"{where} work_id"),
        None if kind is None or kind in WORK_KINDS else f"{where} work_kind {kind!r} is not a Work kind",
        None if marker is None or (marker == v1 and kind == "phase_integration_check") else
        f"{where} phase_review_contract {marker!r} is not the supported marker of an integration",
        _digest_problem(work["desired_state_digest"], f"{where} desired_state_digest"),
        None if work["state"] in states else f"{where} state {work['state']!r} is not an effective Work state",
    ]
    if kind == "human_confirmation":
        if not isinstance(target, list) or not all(isinstance(t, str) and (is_valid_id(t, "work") or is_valid_id(t, "phase"))
                                                   for t in target):
            found.append(f"{where} confirmation_target {target!r} is not a list of Work / Phase IDs")
    elif target is not None:
        found.append(f"{where} carries a confirmation_target but is not a human_confirmation")
    terminal = work["terminal_event_id"]
    if work["state"] == "completed":
        found.append(_id_problem(terminal, "event", f"{where} terminal_event_id"))
    elif terminal is not None:
        found.append(f"{where} is {work['state']} and names terminal event {terminal!r}")
    return found


def candidate_problems(candidate: object) -> list[str]:
    """Why ``candidate`` is not a strict, normalized, internally consistent Phase Integration Candidate.

    Empty when it is. Strict: every nested entry holds exactly its fields, every
    ID is of its kind, every digest a SHA-256, every vocabulary closed (Work
    kinds, the marker, effective Work states, Related types, opening lifecycle
    events), the base a full object ID (SHA-1 or SHA-256, as the canonical
    owner accepts it) on a full branch ref, and the owning operation names the
    integration's own START lifecycle stage. Consistent: the coverage classes
    are exactly what the Candidate's own Works and dependencies classify to
    (:func:`workline.phase_integration.classify_from_edges`), the downstream
    confirmations are exactly the post-integration class, the integration is the
    one ``current_integration`` and agrees with its Work entry, and every Work
    Review ref names an effective Work with a summary digest. The Effective
    Policy hash is a value the policy owner supplies; only its shape is checked.

    ``achievement_evidence_refs`` are the available achievement evidence
    references §14.5 lists at minimum (RB5FB-3): ``(phase_id,
    achievement_evidence_id, evidence_digest)`` entries in (phase_id,
    achievement_evidence_id) order, checked for shape only - which records are
    available and valid is the achievement history reader's, which supplies
    them at freeze (deferred). The evidence ID is a structured identity label
    until its ID kind lands with the history owner, exactly as
    :class:`workline.achievement.PhaseCompletionEvidence` checks it.

    Total over any record value: an unhashable or non-string value is reported
    by its own check and never raises (RB5FA-1).
    """
    from ..phase_integration import (
        CONFIRMATION_KIND,
        COVERAGE_CLASSES,
        COVERAGE_CLASSIFICATION_VERSION,
        CURRENT_INTEGRATION,
        PHASE_INTEGRATION_REVIEW_V1,
        POST_INTEGRATION_CONFIRMATION,
        classify_from_edges,
    )
    from ..state import COMPLETED, HELD, IN_PROGRESS, UNSTARTED

    problem = _fields_problem(candidate, CANDIDATE_FIELDS, "the Phase Integration Candidate")
    if problem is not None:
        return [problem]
    assert isinstance(candidate, dict)
    found: list[str | None] = [
        None if candidate[serialize.SCHEMA_KEY] == SCHEMA_CANDIDATE else f"schema {candidate[serialize.SCHEMA_KEY]!r}",
        None if candidate[serialize.VERSION_KEY] == RECORD_VERSION else f"version {candidate[serialize.VERSION_KEY]!r}",
        None if candidate["review_kind"] == REVIEW_KIND else f"review_kind {candidate['review_kind']!r}",
        _id_problem(candidate["phase_id"], "phase", "phase_id"),
        _id_problem(candidate["roadmap_id"], "roadmap", "roadmap_id"),
        _digest_problem(candidate["phase_desired_state_digest"], "phase_desired_state_digest"),
        _digest_problem(candidate["structural_validation_digest"], "structural_validation_digest"),
        _digest_problem(candidate["review_context_digest"], "review_context_digest"),
        _digest_problem(candidate["effective_policy_hash"], "effective_policy_hash"),
    ]
    generation = candidate["candidate_generation"]
    if type(generation) is not int or generation < 1:
        found.append(f"candidate_generation {generation!r} is not a positive integer")
    base = candidate["base"]
    found.append(_fields_problem(base, _BASE_FIELDS, "base"))
    if isinstance(base, dict) and set(base) == set(_BASE_FIELDS):
        found.append(_object_id_problem(base["commit"], "base commit"))
        if not isinstance(base["branch"], str) or records._FULL_BRANCH.fullmatch(base["branch"]) is None:
            found.append(f"base branch {base['branch']!r} is not a full branch ref")

    effective = _list(candidate, "effective_work_ids", found)
    if not _sorted_unique(effective):
        found.append("effective_work_ids is not sorted and unique")
    found += [_id_problem(work_id, "work", "effective_work_ids entry") for work_id in effective]
    works = _list(candidate, "works", found)
    states = (UNSTARTED, IN_PROGRESS, HELD, COMPLETED)
    valid_works: dict[str, dict[str, Any]] = {}
    for work in works:
        problem = _fields_problem(work, _WORK_FIELDS, "a Candidate Work")
        found.append(problem)
        if problem is None:
            found += _work_entry_problems(work, PHASE_INTEGRATION_REVIEW_V1, states)
            valid_works[str(work["work_id"])] = work
    if [work.get("work_id") for work in works if isinstance(work, dict)] != list(effective):
        found.append("works does not list exactly the effective Works in ID order")

    integration = candidate["integration"]
    integration_id = None
    found.append(_fields_problem(integration, _INTEGRATION_FIELDS, "integration"))
    if isinstance(integration, dict) and set(integration) == set(_INTEGRATION_FIELDS):
        integration_id = integration["work_id"]
        found += [
            _id_problem(integration_id, "work", "integration work_id"),
            None if integration["work_kind"] == "phase_integration_check" else
            "the integration is not a phase_integration_check",
            None if integration["phase_review_contract"] == PHASE_INTEGRATION_REVIEW_V1 else
            f"the integration's phase_review_contract {integration['phase_review_contract']!r} is not supported",
            _digest_problem(integration["desired_state_digest"], "integration desired_state_digest"),
        ]
        entry = valid_works.get(str(integration_id))
        if entry is None or (entry["work_kind"], entry["phase_review_contract"], entry["desired_state_digest"]) != (
            integration["work_kind"], integration["phase_review_contract"], integration["desired_state_digest"]
        ):
            found.append("the integration does not agree with its own effective Work entry")
        elif entry["state"] == COMPLETED:
            found.append("a Phase Integration Candidate is frozen for the one unfinished integration, not a completed one")

    dependencies = _list(candidate, "dependencies", found)
    edges: list[tuple[str, str]] = []
    effective_set = set(effective) if _sorted_unique(effective) else set()
    for dependency in dependencies:
        problem = _fields_problem(dependency, _DEPENDENCY_FIELDS, "a dependency")
        found.append(problem)
        if problem is None:
            found += [_id_problem(dependency["relation_id"], "relation", "dependency relation_id"),
                      _id_problem(dependency["from"], "work", "dependency from"),
                      _id_problem(dependency["to"], "work", "dependency to")]
            if not _member(dependency["from"], effective_set) and not _member(dependency["to"], effective_set):
                found.append(f"dependency {dependency['relation_id']!r} touches no effective Work")
            # Classification pairs Work IDs, which are strings; a non-string endpoint is reported just above and could
            # never match one, so leaving it out changes no class and keeps the check total (RB5FA-1).
            if isinstance(dependency["from"], str) and isinstance(dependency["to"], str):
                edges.append((dependency["from"], dependency["to"]))
    if not _sorted_unique([d.get("relation_id") for d in dependencies if isinstance(d, dict)]):
        found.append("dependencies is not in relation ID order")

    coverage = candidate["coverage"]
    found.append(_fields_problem(coverage, _COVERAGE_FIELDS, "coverage"))
    classes: dict[str, str] = {}
    if isinstance(coverage, dict) and set(coverage) == set(_COVERAGE_FIELDS):
        if coverage["version"] != COVERAGE_CLASSIFICATION_VERSION:
            found.append(f"coverage version {coverage['version']!r} is not {COVERAGE_CLASSIFICATION_VERSION}")
        entries = coverage["classes"] if isinstance(coverage["classes"], list) else []
        if not isinstance(coverage["classes"], list):
            found.append("coverage classes is not a list")
        for entry in entries:
            problem = _fields_problem(entry, _CLASS_FIELDS, "a coverage class entry")
            found.append(problem)
            if problem is None:
                if entry["class"] not in COVERAGE_CLASSES:
                    found.append(f"coverage class {entry['class']!r} is not one of the five")
                classes[str(entry["work_id"])] = entry["class"]
        if [entry.get("work_id") for entry in entries if isinstance(entry, dict)] != list(effective):
            found.append("coverage classifies exactly the effective Works, in ID order")
        current = [work_id for work_id, found_class in classes.items() if found_class == CURRENT_INTEGRATION]
        if current != [integration_id]:
            found.append("the integration is not the one current_integration of its coverage")
        if integration_id is not None and len(valid_works) == len(works):
            # The integration is unfinished (checked above), so only which Works have completed matters to the
            # rule here: a completed other integration is historical, an unfinished one is invalid (CPQ-02).
            ranks = {work_id: (0 if work["state"] == COMPLETED else None) for work_id, work in valid_works.items()}
            expected = classify_from_edges(
                str(integration_id), {work_id: work["work_kind"] for work_id, work in valid_works.items()}, edges,
                ranks,
            )
            if expected != classes:
                found.append("coverage does not follow from the Candidate's own Works and dependencies")
    confirmations = _list(candidate, "downstream_confirmation_ids", found)
    post = sorted(work_id for work_id, found_class in classes.items() if found_class == POST_INTEGRATION_CONFIRMATION)
    if confirmations != post:
        found.append("downstream_confirmation_ids is not exactly the post_integration_confirmation Works")
    found += [None if valid_works.get(str(work_id), {}).get("work_kind") == CONFIRMATION_KIND else
              f"downstream confirmation {work_id!r} is not an effective human_confirmation" for work_id in confirmations]

    related = _list(candidate, "related_authority_refs", found)
    for entry in related:
        problem = _fields_problem(entry, _RELATED_FIELDS, "a Related / authority ref")
        found.append(problem)
        if problem is None:
            found += [_id_problem(entry["relation_id"], "relation", "Related relation_id"),
                      None if entry["type"] in RELATED_TYPES else f"Related type {entry['type']!r} is not a Related type",
                      None if _member(entry["from"], effective_set) else
                      f"Related {entry['relation_id']!r} is not from an effective Work",
                      None if isinstance(entry["to"], str) and entry["to"].strip() else
                      f"Related {entry['relation_id']!r} has no target"]
            conditional = entry["type"] in CONDITIONAL_RELATED_TYPES
            if conditional != isinstance(entry["condition"], dict) or (not conditional and entry["condition"] is not None):
                found.append(f"Related {entry['relation_id']!r} condition does not match its type")
    if not _sorted_unique([entry.get("relation_id") for entry in related if isinstance(entry, dict)]):
        found.append("related_authority_refs is not in relation ID order")

    work_refs = _list(candidate, "work_review_refs", found)
    for entry in work_refs:
        problem = _fields_problem(entry, _WORK_REVIEW_FIELDS, "a Work Review ref")
        found.append(problem)
        if problem is None:
            found += [None if _member(entry["work_id"], effective_set) else
                      f"Work Review ref names {entry['work_id']!r}, which is not an effective Work",
                      _id_problem(entry["review_run_id"], "review_run", "Work Review ref review_run_id"),
                      _digest_problem(entry["run_summary_digest"], "Work Review ref run_summary_digest")]
    if not _sorted_unique([(e.get("work_id"), e.get("review_run_id")) for e in work_refs if isinstance(e, dict)]):
        found.append("work_review_refs is not in (work_id, review_run_id) order")

    achievement_refs = _list(candidate, "achievement_evidence_refs", found)
    for entry in achievement_refs:
        problem = _fields_problem(entry, _ACHIEVEMENT_REF_FIELDS, "an achievement evidence ref")
        found.append(problem)
        if problem is None:
            found += [_id_problem(entry["phase_id"], "phase", "achievement evidence ref phase_id"),
                      _label_problem(entry["achievement_evidence_id"], "achievement evidence ref evidence ID"),
                      _digest_problem(entry["evidence_digest"], "achievement evidence ref evidence_digest")]
    if not _sorted_unique([(e.get("phase_id"), e.get("achievement_evidence_id")) for e in achievement_refs
                           if isinstance(e, dict)]):
        found.append("achievement_evidence_refs is not in unique (phase_id, achievement_evidence_id) order")

    owning = candidate["owning_operation"]
    found.append(_fields_problem(owning, _OWNING_FIELDS, "owning_operation"))
    if isinstance(owning, dict) and set(owning) == set(_OWNING_FIELDS):
        found.append(_id_problem(owning["mutation_id"], "mutation", "owning mutation_id"))
        stage = owning["terminal_stage"]
        prefix = f"{integration_id}:lifecycle:"
        if not isinstance(stage, str) or not stage.startswith(prefix) or not stage[len(prefix):].isdigit():
            found.append(f"owning terminal_stage {stage!r} is not the integration's START lifecycle stage "
                         f"({prefix}<n>)")
        projection = owning["lifecycle_projection"]
        if not isinstance(projection, list) or not projection:
            found.append("owning lifecycle_projection is not a non-empty list of the integration's opening events")
        else:
            for entry in projection:
                problem = _fields_problem(entry, _LIFECYCLE_FIELDS, "a lifecycle projection entry")
                found.append(problem)
                if problem is None:
                    found += [_id_problem(entry["event_id"], "event", "lifecycle projection event_id"),
                              None if entry["type"] in OPENING_EVENTS else
                              f"lifecycle projection type {entry['type']!r} is not an opening event",
                              None if entry["entity"] == integration_id else
                              f"lifecycle projection entry is about {entry['entity']!r}, not the integration"]
    return [problem for problem in found if problem is not None]


def candidate_hash(candidate: dict[str, Any]) -> str:
    """The Candidate hash: the digest of its canonical bytes, refused for anything not strict."""
    problems = candidate_problems(candidate)
    if problems:
        raise _invalid("the Phase Integration Candidate is not strict: " + "; ".join(problems))
    return serialize.digest(candidate)


def invalid_uncovered_of(candidate: dict[str, Any]) -> tuple[str, ...]:
    """The Works a strict Candidate classifies ``invalid_uncovered`` (a structural defect).

    Only for a Candidate whose classes follow from its own Works and
    dependencies (:func:`candidate_problems`); stored classes are never trusted.
    """
    from ..phase_integration import INVALID_UNCOVERED

    problems = candidate_problems(candidate)
    if problems:
        raise _invalid("the Phase Integration Candidate is not strict: " + "; ".join(problems))
    return tuple(entry["work_id"] for entry in candidate["coverage"]["classes"] if entry["class"] == INVALID_UNCOVERED)


def downstream_confirmation_ids_of(candidate: dict[str, Any]) -> tuple[str, ...]:
    """The valid downstream confirmations of a strict Candidate - the one predicate behind the branch input."""
    problems = candidate_problems(candidate)
    if problems:
        raise _invalid("the Phase Integration Candidate is not strict: " + "; ".join(problems))
    return tuple(candidate["downstream_confirmation_ids"])


# --------------------------------------------------------------------------- domain repair facts (§32.25 - §32.28, §32.50)

@dataclass(frozen=True)
class PriorRepairLink:
    """One prior supported repair / future-work link of the integration (validated P5 provenance)."""

    semantic_surface: str
    strategy_id: str
    source_finding_id: str
    source_review_run_id: str
    target_work_id: str


@dataclass(frozen=True)
class IntegrationRepairContext:
    """The canonical blocking obligation set START hands its executor after G4 (§32.25 - §32.26).

    ``blocking_findings`` pairs each blocking Finding with its semantic surface,
    so the surfaces always cover every blocking Finding.
    ``unmet_objective_obligations`` carries the explicit unmet objective
    obligations a ``not_satisfied`` outcome may rest on (§32.21), so a domain
    repair is never without support.
    """

    integration_id: str
    review_run_id: str
    blocking_findings: tuple[tuple[str, str], ...]
    unmet_objective_obligations: tuple[str, ...]
    prior_links: tuple[PriorRepairLink, ...]
    strategy_change_required: bool

    @property
    def blocking_finding_ids(self) -> tuple[str, ...]:
        return tuple(finding_id for finding_id, _ in self.blocking_findings)

    @property
    def semantic_surfaces(self) -> tuple[str, ...]:
        return tuple(sorted({surface for _, surface in self.blocking_findings}))

    def problems(self) -> list[str]:
        """Why this context cannot carry a domain repair; empty when it can. Fails closed (RB5B-M3)."""
        found: list[str | None] = [
            _id_problem(self.integration_id, "work", "integration_id"),
            _id_problem(self.review_run_id, "review_run", "review_run_id"),
            None if type(self.strategy_change_required) is bool else "strategy_change_required is not a boolean",
            None if isinstance(self.blocking_findings, tuple) else "blocking_findings is not a tuple",
            None if isinstance(self.unmet_objective_obligations, tuple) else "unmet_objective_obligations is not a tuple",
            None if isinstance(self.prior_links, tuple) else "prior_links is not a tuple",
        ]
        if any(problem is not None for problem in found):
            return [problem for problem in found if problem is not None]
        for item in self.blocking_findings:
            if not isinstance(item, tuple) or len(item) != 2:
                found.append(f"blocking finding {item!r} is not a (finding_id, semantic_surface) pair")
                continue
            found += [_id_problem(item[0], "review_finding", "blocking Finding"),
                      _label_problem(item[1], f"semantic surface of {item[0]!r}")]
        if not _sorted_unique([item[0] for item in self.blocking_findings if isinstance(item, tuple) and item]):
            found.append("blocking_findings is not in unique Finding ID order")
        if not _sorted_unique(self.unmet_objective_obligations):
            found.append("unmet_objective_obligations is not sorted and unique")
        found += [_label_problem(item, "unmet objective obligation") for item in self.unmet_objective_obligations]
        if not self.blocking_findings and not self.unmet_objective_obligations:
            found.append("a domain repair context has at least one blocking Finding or unmet objective obligation")
        for link in self.prior_links:
            if type(link) is not PriorRepairLink:
                found.append(f"a prior link is {type(link).__name__}, not a PriorRepairLink")
                continue
            found += [
                _label_problem(link.semantic_surface, "prior link semantic surface"),
                None if isinstance(link.strategy_id, str) and STRATEGY_ID_PATTERN.fullmatch(link.strategy_id) else
                f"prior link strategy_id {link.strategy_id!r} is not a strategy identity",
                _id_problem(link.source_finding_id, "review_finding", "prior link source Finding"),
                _id_problem(link.source_review_run_id, "review_run", "prior link source Run"),
                _id_problem(link.target_work_id, "work", "prior link target Work"),
            ]
        if self.strategy_change_required:
            if not self.blocking_findings:
                found.append("STRATEGY_CHANGE is required, yet no blocking Finding names a semantic surface")
            elif not self.prior_strategies():
                found.append("STRATEGY_CHANGE is required, yet no prior supported link exists on the context's "
                             "semantic surfaces: the prior strategy cannot be refused, so nothing is accepted")
        return [problem for problem in found if problem is not None]

    def prior_strategies(self) -> frozenset[str]:
        """The strategy identities already linked on this context's semantic surfaces."""
        surfaces = set(self.semantic_surfaces)
        return frozenset(link.strategy_id for link in self.prior_links
                         if type(link) is PriorRepairLink and link.semantic_surface in surfaces)


@dataclass(frozen=True)
class IntegrationFixProvenance:
    """The P5 future_work_link provenance extension of one integration-generated fix Work (§32.26, §32.50).

    Evidence only: it never places the Work in a completion set and never makes
    Review a CREATE owner. Persisting it is the history owner's.
    """

    source_review_run_id: str
    source_finding_id: str
    strategy_id: str
    target_work_id: str

    def to_record(self) -> dict[str, Any]:
        return {
            "source_review_run_id": self.source_review_run_id,
            "source_finding_id": self.source_finding_id,
            "strategy_id": self.strategy_id,
            "target_work_id": self.target_work_id,
        }

    def problems(self) -> list[str]:
        found = [
            _id_problem(self.source_review_run_id, "review_run", "source_review_run_id"),
            _id_problem(self.source_finding_id, "review_finding", "source_finding_id"),
            None if isinstance(self.strategy_id, str) and STRATEGY_ID_PATTERN.fullmatch(self.strategy_id) else
            f"strategy_id {self.strategy_id!r} is not a strategy identity",
            _id_problem(self.target_work_id, "work", "target_work_id"),
        ]
        return [problem for problem in found if problem is not None]


# --------------------------------------------------------------------------- verification-only side effects (§14.10, §32.29)

NO_PROOF = (
    "no positive proof that the verification left persistent state untouched: a self-reported (possibly empty) "
    "observation - like result_paths=() - is never proof of read-only behaviour"
)


@dataclass(frozen=True)
class MaterializationProof:
    """§14.10 preferred path: the verifier ran on a read-only / disposable materialization of the frozen Candidate.

    ``materialized_tree`` is the tree the verifier actually read; it must be the
    Candidate base commit's tree, which the owner supplies separately.
    """

    mechanism_identity: str
    mechanism_version: str
    materialized_tree: str
    disposed: bool


@dataclass(frozen=True)
class OwnerMeasuredProof:
    """§14.10 fallback: an owner-measured before / after digest of the canonical Project state, taken outside the
    verifier, with the external / nested scopes the declaration allowed."""

    measured_by: str
    before_state_digest: str
    after_state_digest: str
    declared_external_scopes: tuple[str, ...]
    declared_nested_scopes: tuple[str, ...]


def verification_only_problems(declaration: object, observation: object, proof: object, *,
                               candidate_base_tree: str) -> list[str]:
    """Why the integration verification cannot PASS as verification-only; empty when it may.

    P4's verification-only contract (:func:`workline.review.p4.integration_problems`)
    over the adapter's declaration and observation, AND a positive proof that is
    not the verifier's own report (RB5B-H1): either a disposed read-only
    materialization of exactly the Candidate base tree, or an owner-measured
    before / after Project-state digest pair that is unchanged, measured by an
    identity other than the verifier's, over exactly the declared scopes.
    """
    if type(proof) not in (MaterializationProof, OwnerMeasuredProof):
        return [NO_PROOF]
    if type(declaration) is not p4.IntegrationDeclaration:
        return [f"the verification declares its side effects as an IntegrationDeclaration, not {type(declaration).__name__}"]
    if type(observation) is not p4.IntegrationObservation:
        return [f"the verification observation is an IntegrationObservation, not {type(observation).__name__}"]
    problems: list[str | None] = [_object_id_problem(candidate_base_tree, "the Candidate base tree")]
    if isinstance(proof, MaterializationProof):
        problems += [
            _label_problem(proof.mechanism_identity, "materialization mechanism identity"),
            _label_problem(proof.mechanism_version, "materialization mechanism version"),
            _object_id_problem(proof.materialized_tree, "the materialized tree"),
            None if proof.materialized_tree == candidate_base_tree else
            "the verifier read a tree other than the Candidate base tree",
            None if proof.disposed is True else "the disposable materialization was not proven disposed",
        ]
    else:
        problems += [
            _label_problem(proof.measured_by, "the measuring owner identity"),
            None if proof.measured_by != declaration.adapter_identity else
            "the before / after proof was measured by the verifier itself, not by the owner",
            _digest_problem(proof.before_state_digest, "the before Project-state digest"),
            _digest_problem(proof.after_state_digest, "the after Project-state digest"),
            None if proof.before_state_digest == proof.after_state_digest else
            "the owner-measured Project state changed across the verification",
            None if tuple(proof.declared_external_scopes) == tuple(sorted(declaration.allowed_external_state)) else
            "the proof does not bind exactly the declared external scopes",
            None if tuple(proof.declared_nested_scopes) == tuple(sorted(declaration.allowed_nested_state)) else
            "the proof does not bind exactly the declared nested scopes",
        ]
    found = [problem for problem in problems if problem is not None]
    return found + p4.integration_problems(declaration, observation)


__all__ = [
    "REVIEW_KIND", "AUTHORIZED_OPERATION_STAGE", "TARGET_IDENTITY_KIND", "PHASE_OUTCOMES", "AUTHORIZING_PHASE_OUTCOMES",
    "BRANCHES", "OBJECTIVELY_SATISFIED", "HUMAN_CONFIRMATION_REQUIRED", "NOT_SATISFIED",
    "DESIRED_STATE_CHANGE_REQUIRED", "BRANCH_HUMAN_WAIT", "BRANCH_DOMAIN_REPAIR_REQUIRED",
    "BRANCH_CONFIRMATION_STRUCTURE_REQUIRED", "BRANCH_AUTHORIZATION_READY", "CODE_UNCOVERED", "CODE_NOT_AUTHORIZABLE",
    "OPENING_EVENTS", "STRATEGY_ID_PATTERN", "PhaseOutcome", "phase_outcome_problems", "integration_branch",
    "branch_issues_receipt", "SCHEMA_CANDIDATE", "candidate_problems", "candidate_hash", "invalid_uncovered_of",
    "downstream_confirmation_ids_of", "PriorRepairLink", "IntegrationRepairContext", "IntegrationFixProvenance",
    "NO_PROOF", "MaterializationProof", "OwnerMeasuredProof", "verification_only_problems",
]
