"""START-owned Phase Integration Review orchestration (``WORKLINE_COMPLETION_SPRINT`` §32.4 / §32.11 - §32.30): pure parts.

START owns the integration Work's lifecycle, reintegration, the dynamic
confirmation structure and the domain fix Works; Review only verifies and
authorizes. This module holds the parts of START's integration orchestration
that are pure - decided from a :class:`~workline.state.ProjectView`, a Work and
caller-supplied facts, with no lock, no mutation, no reservation, no executor
call and no Git:

```text
semantics      the durable operation-contract note a fresh START records, and how a
               resumed mutation without it stays legacy (§32.4)
entry gate     marker + selectors -> Phase Integration Review / legacy / refusal (§32.14 - §32.15)
marker         the deterministic marker injection into a reintegration WorkSpec (§32.4)
closure        the complete direct predecessor edges of a fresh reviewed integration, and
               the fail-closed gap check of an unfinished one (§32.11 - §32.13, CPQ-03)
confirmation   the deterministic confirmation START registers through CREATE, and
               whether a valid downstream confirmation already exists (§32.23)
Candidate      the Phase Integration Candidate built from committed canonical state,
               and the unowned-structure-difference check before freeze (§32.17 - §32.18)
repair         IntegrationRepairPlan over START's Derive, the STRATEGY_CHANGE reuse
               refusal and which executor answers a domain repair context (§32.25 - §32.26)
terminal gate  the frozen work_completed precondition list over supplied facts (§14.16, §32.30)
```

Every hook into ``start.py`` / ``start_review.py`` - recording the note,
calling the gate under the START lock, registering through CREATE, running the
Review flow, consuming the Receipt - is deferred to the integrated candidate,
as are the ``phase_review`` selector type (it carries P4/P6 actor identities)
and the Effective Policy the Candidate binds.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping

from . import phase_integration as pi
from .create import RelationSpec, WorkSpec
from .errors import ReconcileRequired, SpecViolation, StopError, ValidationError
from .review import integration as ri
from .review import serialize
from .state import ProjectView
from .store import PHASE_DESIRED_HEADING, WORK_DESIRED_HEADING, Entity

# --------------------------------------------------------------------------- the operation-contract note (§32.4)

#: The key of the durable note a fresh RB5-capable START mutation records before any executor call.
OPERATION_NOTE_KEY = "phase_integration_semantics"
SEMANTICS_LEGACY = pi.MODE_LEGACY
SEMANTICS_REVIEWED = pi.PHASE_INTEGRATION_REVIEW_V1

# --------------------------------------------------------------------------- STOP codes

#: A marked integration was reached without the ``phase_review`` selector (``review=`` never substitutes).
CODE_PHASE_REVIEW_REQUIRED = "phase_review_required"
#: A Work carries a Phase Review contract this build does not support, or carries one on a non-integration Work.
CODE_PHASE_REVIEW_CONTRACT_UNSUPPORTED = "phase_review_contract_unsupported"
#: A START mutation records a Phase integration semantics this build does not read.
CODE_SEMANTICS_UNKNOWN = "phase_integration_semantics_unknown"
#: The existing START code for new Work after a completed integration with no reintegration design.
CODE_REINTEGRATION_REQUIRED = "reintegration_required"
#: A reviewed-mode Phase whose one unfinished integration carries no marker: late Work cannot be covered.
CODE_UNMARKED_UNFINISHED = "phase_integration_unmarked_unfinished"
#: A Phase Integration Candidate cannot be frozen over a failing structural validation.
CODE_STRUCTURE_INVALID = "structure_invalid"
#: CPQ-03: the unfinished reviewed integration lacks an edge from a Work this operation did not register.
CODE_COVERAGE_GAP = "phase_integration_coverage_gap"
#: Several incompatible downstream confirmations match one integration (reconcile reason).
REASON_CONFIRMATION_CONFLICT = "phase_confirmation_conflict"

# --------------------------------------------------------------------------- entry routes (§32.14)

ROUTE_NOT_INTEGRATION = "not_an_integration"
ROUTE_LEGACY_INTEGRATION = "legacy_integration"
ROUTE_PHASE_INTEGRATION_REVIEW = "phase_integration_review"


def fresh_operation_note() -> dict[str, str]:
    """The note a fresh RB5-capable START records before any executor call."""
    return {OPERATION_NOTE_KEY: SEMANTICS_REVIEWED}


def mutation_semantics(note_value: object) -> str:
    """The Phase integration semantics a START mutation runs under, read from its own note.

    A resumed legacy mutation that lacks the note stays legacy and is never
    upgraded; a note naming anything else is refused rather than guessed.
    """
    if note_value is None:
        return SEMANTICS_LEGACY
    if note_value == SEMANTICS_REVIEWED:
        return SEMANTICS_REVIEWED
    raise StopError(f"the START mutation records Phase integration semantics {note_value!r}, which this build does "
                    "not read; it is neither upgraded nor downgraded", code=CODE_SEMANTICS_UNKNOWN)


@dataclass(frozen=True)
class EntryGate:
    """How START runs one Work's Review, decided from the Work's own marker and the supplied selectors.

    There is deliberately no activation field: the P3 Work-terminal activation is
    never an input of Phase Integration Review (§32.14 - the canonical marker
    itself makes the gate mandatory), and Work Formal Review keeps its own
    activation semantics unchanged.
    """

    route: str
    #: Whether the Work Formal Review selector (``review=``) applies to this Work.
    work_review_applies: bool
    #: Whether the Phase Integration Review selector (``phase_review=``) applies to this Work.
    phase_review_applies: bool


def entry_gate(work: Entity, *, phase_review_supplied: bool, work_review_supplied: bool) -> EntryGate:
    """§32.14 - §32.15, re-reading the Work's marker:

    * a legacy (unmarked) integration runs without ``phase_review``, exactly as today;
    * a marked integration requires ``phase_review`` and never falls back to Work Formal Review -
      ``review=`` alone is refused;
    * a marker other than the exact supported contract is refused, and so is any
      marker on a Work that is not an integration (RB5B-L7: the gate never relies
      on structural validation having run);
    * with both selectors, each applies only to its own Review kind.
    """
    marker = work.phase_review_contract
    if not pi.is_integration(work):
        if marker is not None:
            raise StopError(f"Work {work.id} is not a phase_integration_check and carries phase_review_contract "
                            f"{marker!r}", code=CODE_PHASE_REVIEW_CONTRACT_UNSUPPORTED)
        return EntryGate(ROUTE_NOT_INTEGRATION, work_review_supplied, False)
    if marker is None:
        return EntryGate(ROUTE_LEGACY_INTEGRATION, work_review_supplied, False)
    if not pi.is_reviewed_integration(work):
        raise StopError(f"integration {work.id} carries phase_review_contract {marker!r}, which is not supported",
                        code=CODE_PHASE_REVIEW_CONTRACT_UNSUPPORTED)
    if not phase_review_supplied:
        also = " (the Work Formal Review selector review= never substitutes for it)" if work_review_supplied else ""
        raise StopError(f"integration {work.id} is a {marker} integration: Phase Integration Review is mandatory and "
                        f"needs the phase_review selector{also}", code=CODE_PHASE_REVIEW_REQUIRED)
    return EntryGate(ROUTE_PHASE_INTEGRATION_REVIEW, False, True)


def require_phase_review_for_registration(*, semantics: str, phase_review_supplied: bool) -> None:
    """§32.15: a fresh START about to register a reviewed integration without ``phase_review`` refuses first.

    Refused before the registration effect, so the operation resumes once the
    runtime capability is supplied.
    """
    if semantics == SEMANTICS_REVIEWED and not phase_review_supplied:
        raise StopError("this START would register a phase-integration-review-v1 integration and holds no "
                        "phase_review selector; nothing was registered", code=CODE_PHASE_REVIEW_REQUIRED)


# --------------------------------------------------------------------------- marker injection (§32.4)

def marked_integration_spec(spec: WorkSpec) -> WorkSpec:
    """The integration WorkSpec with the fixed structural review contract; name / desired state stay the executor's."""
    if spec.work_kind != pi.INTEGRATION_KIND:
        raise ValidationError("only a phase_integration_check WorkSpec carries a phase_review_contract")
    if spec.phase_review_contract not in (None, pi.PHASE_INTEGRATION_REVIEW_V1):
        raise ValidationError(f"unsupported phase_review_contract {spec.phase_review_contract!r}")
    return replace(spec, phase_review_contract=pi.PHASE_INTEGRATION_REVIEW_V1)


# --------------------------------------------------------------------------- reviewed reintegration closure (§32.11 - §32.13)

def reviewed_derivation_problems(derived_works: Mapping[str, Any], *, reviewed: bool) -> list[str]:
    """§32.12: under reviewed semantics every normal / fix Work is pre-integration.

    ``derived_works`` are START's derived Works (``DerivedWork``) by key;
    ``before_integration=False`` on a normal one is invalid for a reviewed target.
    """
    if not reviewed:
        return []
    return [
        f"derived Work {key}: before_integration=False is invalid under {pi.PHASE_INTEGRATION_REVIEW_V1} semantics"
        for key, work in derived_works.items() if work.work_kind is None and work.before_integration is not True
    ]


def pre_existing_closure_gaps(view: ProjectView, phase_id: str, integration_id: str) -> tuple[str, ...]:
    """§32.12 with ruling CPQ-03: the existing Works the one unfinished reviewed integration lacks a direct edge from.

    ``view`` is the Project as this START operation meets it, before its own
    registration. The operation adds - and on resume replays - only the edges it
    owns: those of the Works it registers itself (``before_integration``) and,
    for a fresh reintegration, the closure of the integration it creates
    (:func:`reintegration_closure_relations`). A gap in structure it did not
    create is never auto-repaired (§14.9); it is reported and fails closed
    (:func:`require_no_pre_existing_closure_gap`).
    """
    return pi.missing_predecessor_ids(view, phase_id, integration_id)


def require_no_pre_existing_closure_gap(view: ProjectView, phase_id: str, integration_id: str) -> None:
    """CPQ-03: STOP ``phase_integration_coverage_gap`` - before any effect - when pre-existing structure has a gap."""
    gaps = pre_existing_closure_gaps(view, phase_id, integration_id)
    if gaps:
        raise StopError(
            f"the unfinished reviewed integration {integration_id} of Phase {phase_id} lacks the direct edge from "
            f"existing Work {', '.join(gaps)}; structure this operation did not create is reported, never repaired",
            code=CODE_COVERAGE_GAP,
        )


def reintegration_closure_relations(view: ProjectView, phase_id: str, integration_ref: str = "integration", *,
                                    planned_downstream: Iterable[str] = ()) -> list[RelationSpec]:
    """§32.11 / §32.13: every existing required pre-integration Work -> the new reviewed integration.

    Already-completed current-plan Works are included; historical integrations
    are not. ``planned_downstream`` names the existing ``human_confirmation``
    Works the same registration makes downstream of the new integration (a
    Human NG returns to its confirmation through ``integration -> confirmation``);
    :func:`workline.phase_integration.required_pre_integration_ids` excludes
    them, so the closure never makes a cycle. New normal Works of the
    registration get their own edges from the derivation.
    """
    return [RelationSpec(pi.DEPENDENCY, work_id, integration_ref)
            for work_id in pi.required_pre_integration_ids(view, phase_id, None, planned_downstream=planned_downstream)]


def require_reintegration_design(view: ProjectView, phase_id: str, *, has_design: bool) -> str | None:
    """§32.13 / §14.9: where late Work goes; STOP ``reintegration_required`` before writing when no design is given.

    Returns the unfinished integration a new Work attaches to, or ``None`` when
    the given reintegration design is to be registered. A reviewed Phase whose
    one unfinished integration is unmarked is a structural STOP
    (``phase_integration_unmarked_unfinished``), never a silent legacy wiring.
    """
    route, unfinished = pi.late_work_route(view, phase_id)
    if route == pi.ROUTE_STRUCTURAL_STOP:
        raise SpecViolation(f"Phase {phase_id} has more than one unfinished integration: structural anomaly, STOP")
    if route == pi.ROUTE_UNMARKED_UNFINISHED:
        raise StopError(f"Phase {phase_id} is under {pi.PHASE_INTEGRATION_REVIEW_V1} semantics but its one unfinished "
                        f"integration {unfinished} carries no marker: late Work cannot be covered; reconcile the "
                        "structure", code=CODE_UNMARKED_UNFINISHED)
    if route == pi.ROUTE_ADD_TO_UNFINISHED:
        return unfinished
    if not has_design:
        raise StopError(f"Phase {phase_id} has no unfinished integration; START must design a re-integration for the "
                        "new Work(s)", code=CODE_REINTEGRATION_REQUIRED)
    return None


# --------------------------------------------------------------------------- dynamic confirmation (§32.23)

#: The fixed desired-state sentence of a Workline-generated Phase confirmation, verbatim from §32.23. It references
#: the canonical Phase objective and adds none; the Phase and integration are bound by ``phase_id`` and
#: ``confirmation_target``.
CONFIRMATION_DESIRED_STATE = (
    "Human has confirmed that this Phase's current canonical desired state is satisfied after the reviewed "
    "integration."
)

CONFIRMATION_EXISTS = "exists"
CONFIRMATION_CREATE = "create"


@dataclass(frozen=True)
class ConfirmationStructure:
    """The deterministic structural confirmation START registers through CREATE when the Review requires one."""

    name: str
    desired_state: str
    confirmation_target: str
    work_kind: str = pi.CONFIRMATION_KIND


def confirmation_structure(phase_id: str, phase_label: str, integration_id: str) -> ConfirmationStructure:
    """§32.23: a stable Workline-generated label and the verbatim sentence; nothing reviewer-written reaches it."""
    from .ids import is_valid_id

    for value, kind in ((phase_id, "phase"), (integration_id, "work")):
        if not is_valid_id(value, kind):
            raise ValidationError(f"{value!r} is not a {kind} ID")
    label = phase_label.strip() if isinstance(phase_label, str) and phase_label.strip() else phase_id
    return ConfirmationStructure(f"Phase confirmation: {label}", CONFIRMATION_DESIRED_STATE, integration_id)


def confirmation_decision(view: ProjectView, phase_id: str, integration_id: str) -> tuple[str, tuple[str, ...]]:
    """Reuse the valid downstream confirmation(s), or create exactly one; refuse only incompatible duplicates.

    Valid = an effective ``human_confirmation`` with the direct
    ``integration -> confirmation`` edge (ruling R5-1, the same predicate the
    coverage classification and the Candidate use). One or several valid ones
    -> create none. Incompatible matching duplicates - the deterministic
    builder's own confirmation present more than once, which only a duplicated
    registration produces - are a reconcile failure (RB5B-L5).
    """
    found = pi.downstream_confirmations(view, phase_id, integration_id)
    phase = view.phases[phase_id]
    built = confirmation_structure(phase_id, phase.display, integration_id)
    generated = [w.id for w in found if w.name == built.name and w.section(WORK_DESIRED_HEADING) == built.desired_state]
    if len(generated) > 1:
        raise ReconcileRequired(
            f"integration {integration_id} has {len(generated)} Workline-generated downstream confirmations "
            f"({', '.join(generated)}): duplicated structure, reconcile required",
            reason=REASON_CONFIRMATION_CONFLICT,
        )
    if found:
        return CONFIRMATION_EXISTS, tuple(w.id for w in found)
    return CONFIRMATION_CREATE, ()


def confirmation_registration(view: ProjectView, phase_id: str, integration_id: str,
                              key: str = "confirmation") -> tuple[dict[str, WorkSpec], list[RelationSpec]]:
    """The one deterministic confirmation Work and its ``integration -> confirmation`` edge, for CREATE."""
    phase = view.phases[phase_id]
    structure = confirmation_structure(phase_id, phase.display, integration_id)
    spec = WorkSpec(structure.name, structure.desired_state, phase_id=phase_id, roadmap_id=phase.roadmap_id,
                    work_kind=structure.work_kind, confirmation_target=structure.confirmation_target)
    return {key: spec}, [RelationSpec(pi.DEPENDENCY, integration_id, key)]


# --------------------------------------------------------------------------- the Candidate (§32.17 - §32.18)

def _text_digest(text: str | None) -> str | None:
    return None if text is None else serialize.digest_of_text(text)


def _structure(view: ProjectView, phase_id: str, integration_id: str) -> dict[str, Any]:
    """The Candidate's own structural projection of ``phase_id`` for ``integration_id`` (everything but base / owner)."""
    effective = {work.id for work in view.effective_works(phase_id)}
    phase = view.phases.get(phase_id)
    works = []
    for fact in pi.effective_work_facts(view, phase_id):
        work = view.works[fact["work_id"]]
        stored_target = work.meta.get("confirmation_target")
        target = list(pi.confirmation_targets(work)) if work.work_kind == pi.CONFIRMATION_KIND or \
            stored_target is not None else None
        works.append({**fact, "confirmation_target": target,
                      "desired_state_digest": _text_digest(work.section(WORK_DESIRED_HEADING))})
    classes = pi.classify_coverage(view, phase_id, integration_id)
    return {
        "roadmap_id": None if phase is None else phase.roadmap_id,
        "phase_desired_state_digest": None if phase is None else _text_digest(phase.section(PHASE_DESIRED_HEADING)),
        "works": works,
        "dependencies": pi.dependency_edges(view, phase_id),
        "coverage": [{"work_id": work_id, "class": found} for work_id, found in classes.items()],
        "downstream_confirmation_ids": [w.id for w in pi.downstream_confirmations(view, phase_id, integration_id)],
        "related_authority_refs": [
            {"relation_id": relation.id, "type": relation.type, "from": relation.from_id, "to": relation.to,
             "condition": relation.extra.get("condition")}
            for relation in sorted(view.related, key=lambda r: r.id) if relation.from_id in effective
        ],
    }


def unowned_structural_difference(committed: ProjectView, working: ProjectView, phase_id: str,
                                  integration_id: str) -> list[str]:
    """§32.17: the Candidate structure the working state (without START's own effects) holds beyond the committed basis.

    Compares the Candidate's own structural projection built from both views -
    Roadmap membership, the Phase objective, every effective Work (kind, marker,
    ``confirmation_target``, objective, state, terminal event), the dependencies,
    the coverage classes, the downstream confirmations and the Related. Any
    difference invalidates the freeze; nothing is repaired.
    """
    before = _structure(committed, phase_id, integration_id)
    try:
        after = _structure(working, phase_id, integration_id)
    except ValidationError as exc:
        return [f"the working state no longer holds the integration the committed basis holds: {exc}"]
    return [f"{key} differs between the committed basis and the working state" for key in before
            if before[key] != after[key]]


def build_candidate(
    committed: ProjectView,
    phase_id: str,
    integration_id: str,
    *,
    base_commit: str,
    branch: str,
    owning_mutation_id: str,
    terminal_stage: str,
    lifecycle_projection: Iterable[tuple[str, str]],
    work_review_refs: Iterable[tuple[str, str, str]],
    review_context_digest: str,
    effective_policy_hash: str,
    candidate_generation: int,
    achievement_evidence_refs: Iterable[tuple[str, str, str]] = (),
) -> dict[str, Any]:
    """The strict Phase Integration Candidate over the committed canonical view at ``base_commit``.

    ``committed`` must be read from committed objects (never arbitrary
    working-tree text). START's own uncommitted opening lifecycle is bound
    separately as ``lifecycle_projection`` (``(event_id, type)`` of the
    integration's opening events), never as basis. ``effective_policy_hash`` is
    supplied by the policy owner; nothing here computes it.

    ``achievement_evidence_refs`` are the available achievement evidence
    references §14.5 requires the Candidate to bind (RB5FB-3), as ``(phase_id,
    achievement_evidence_id, evidence_digest)`` - the shape of
    ``achievement.RoadmapBasis.phase_evidence_refs``. The achievement history
    reader supplies the validated refs at freeze (deferred integration); here,
    as for ``work_review_refs``, only their shape is checked. Empty when no
    achievement evidence exists - nothing is backfilled.

    Ruling CPQ-04: a Candidate MAY freeze with ``invalid_uncovered`` Works - the
    coverage classes record them, and :func:`workline.review.integration.integration_branch`
    keeps the §32.22 order and never reaches AUTHORIZATION_READY (no Receipt)
    while one exists. The one refusal here (RB5B-L2) is a committed basis whose
    structural validation FAILS (``validate_structure`` Problems: a
    ``requires_completion`` cycle, two unfinished integrations - the §14.9 /
    §32.12 structural STOP - dangling references, and so on). ``invalid_uncovered``
    is not a structural-validation Problem, so it never causes this refusal; it
    mirrors START's existing precheck, which already STOPs any START operation
    on a structurally invalid Project (``start._structure_or_stop``).
    """
    from .achievement import structural_validation

    integration = committed.works.get(integration_id)
    phase = committed.phases.get(phase_id)
    if integration is None or phase is None:
        raise ValidationError(f"{integration_id} / {phase_id} is not in the committed basis", code="validation_failed")
    passed, validation_digest = structural_validation(committed)
    if not passed:
        raise ValidationError(f"the committed basis of Phase {phase_id} does not validate structurally; no Phase "
                              "Integration Candidate is frozen over it", code=CODE_STRUCTURE_INVALID)
    structure = _structure(committed, phase_id, integration_id)
    candidate = serialize.canonical_data({
        serialize.SCHEMA_KEY: ri.SCHEMA_CANDIDATE,
        serialize.VERSION_KEY: ri.RECORD_VERSION,
        "review_kind": ri.REVIEW_KIND,
        "phase_id": phase_id,
        "roadmap_id": structure["roadmap_id"],
        "phase_desired_state_digest": structure["phase_desired_state_digest"],
        "integration": {
            "work_id": integration_id,
            "work_kind": integration.work_kind,
            "phase_review_contract": integration.phase_review_contract,
            "desired_state_digest": _text_digest(integration.section(WORK_DESIRED_HEADING)),
        },
        "base": {"commit": base_commit, "branch": branch},
        "effective_work_ids": [work["work_id"] for work in structure["works"]],
        "works": structure["works"],
        "dependencies": structure["dependencies"],
        "coverage": {"version": pi.COVERAGE_CLASSIFICATION_VERSION, "classes": structure["coverage"]},
        "downstream_confirmation_ids": structure["downstream_confirmation_ids"],
        "related_authority_refs": structure["related_authority_refs"],
        "work_review_refs": [
            {"work_id": work_id, "review_run_id": run_id, "run_summary_digest": digest}
            for work_id, run_id, digest in sorted(work_review_refs, key=lambda item: (item[0], item[1]))
        ],
        "achievement_evidence_refs": [
            {"phase_id": phase_ref, "achievement_evidence_id": evidence_id, "evidence_digest": digest}
            for phase_ref, evidence_id, digest in sorted(achievement_evidence_refs, key=lambda item: (item[0], item[1]))
        ],
        "structural_validation_digest": validation_digest,
        "review_context_digest": review_context_digest,
        "effective_policy_hash": effective_policy_hash,
        "candidate_generation": candidate_generation,
        "owning_operation": {
            "mutation_id": owning_mutation_id,
            "terminal_stage": terminal_stage,
            "lifecycle_projection": [{"event_id": event_id, "type": kind, "entity": integration_id}
                                     for event_id, kind in lifecycle_projection],
        },
    })
    problems = ri.candidate_problems(candidate)
    if problems:
        raise ValidationError("the Phase Integration Candidate cannot be frozen: " + "; ".join(problems),
                              code="review_candidate_unrepresentable")
    return candidate


# --------------------------------------------------------------------------- domain repair (§32.25 - §32.27)

@dataclass(frozen=True)
class IntegrationRepairPlan:
    """The structured executor answer in the integration-repair planning context (§32.25).

    ``derive`` is START's ``Derive`` outcome: it must move the integration's
    target off (``move=True``), create no integration (the current one stays the
    one unfinished integration) and register only normal fix Works that come
    before the integration. Review never authors or creates them.
    """

    strategy_id: str
    derive: Any


def repair_plan_problems(plan: object, context: ri.IntegrationRepairContext) -> list[str]:
    """Why ``plan`` may not be registered for ``context``; empty when it may.

    Only an :class:`IntegrationRepairPlan` over START's own ``Derive`` answers a
    domain repair context. The context must itself be valid (it fails closed,
    so the STRATEGY_CHANGE refusal is never vacuous). When STRATEGY_CHANGE is
    required, a plan reusing a strategy identity already linked on the same
    semantic surface is refused. Executor relations that touch the integration
    are refused: the fix Works' edges into the integration are START's own
    (``before_integration``), and nothing may be made post-integration.
    """
    from .start import Derive, DerivedWork

    if type(plan) is not IntegrationRepairPlan:
        return [f"a domain repair context is answered by an IntegrationRepairPlan, not {type(plan).__name__}"]
    if type(plan.derive) is not Derive:
        return [f"an IntegrationRepairPlan carries START's Derive, not {type(plan.derive).__name__}"]
    problems = [f"context: {problem}" for problem in context.problems()]
    if not isinstance(plan.strategy_id, str) or ri.STRATEGY_ID_PATTERN.fullmatch(plan.strategy_id) is None:
        problems.append(f"strategy_id {plan.strategy_id!r} is not a structured public-safe identity")
    derive = plan.derive
    if derive.move is not True:
        problems.append("the repair plan must move the integration's target off (derive.move = true)")
    if derive.integration is not None:
        problems.append("the repair plan creates no integration: the current one stays the one unfinished integration")
    if not derive.works:
        problems.append("the repair plan registers at least one fix Work")
    for key, work in derive.works.items():
        if type(work) is not DerivedWork:
            problems.append(f"fix Work {key} is {type(work).__name__}, not a DerivedWork")
            continue
        if work.work_kind is not None:
            problems.append(f"fix Work {key} is a {work.work_kind}: integration repair registers normal Works only")
        if work.before_integration is not True:
            problems.append(f"fix Work {key} must come before the integration (before_integration = true)")
    for relation in derive.relations:
        if context.integration_id in (relation.from_ref, relation.to_ref):
            problems.append(f"executor relation {relation.type} {relation.from_ref} -> {relation.to_ref} touches the "
                            "integration; its edges are START's own")
    if context.strategy_change_required and plan.strategy_id in context.prior_strategies():
        problems.append(
            f"STRATEGY_CHANGE is required on {', '.join(context.semantic_surfaces)}, and strategy {plan.strategy_id} "
            "is the strategy already linked there"
        )
    return problems


def fix_provenance(context: ri.IntegrationRepairContext, plan: IntegrationRepairPlan, source_finding_id: str,
                   target_work_id: str) -> ri.IntegrationFixProvenance:
    """The provenance of one registered fix Work - only for a plan :func:`repair_plan_problems` accepts."""
    refused = repair_plan_problems(plan, context)
    if refused:
        raise ValidationError("no fix provenance for a refused repair plan: " + "; ".join(refused),
                              code="review_record_invalid")
    if source_finding_id not in context.blocking_finding_ids:
        raise ValidationError(f"{source_finding_id} is not a blocking Finding of this repair context",
                              code="review_record_invalid")
    provenance = ri.IntegrationFixProvenance(context.review_run_id, source_finding_id, plan.strategy_id, target_work_id)
    problems = provenance.problems()
    if problems:
        raise ValidationError("integration fix provenance is invalid: " + "; ".join(problems),
                              code="review_record_invalid")
    return provenance


def repair_outcome_problems(outcome: object, context: ri.IntegrationRepairContext) -> list[str]:
    """Which executor answer a domain repair context accepts: an IntegrationRepairPlan, or the existing
    question / hold behaviour - never a ``Completed`` (or any other) outcome that would bypass the blocking
    obligations."""
    from .start import Hold, QuestionWait

    if isinstance(outcome, (QuestionWait, Hold)):
        return []
    return repair_plan_problems(outcome, context)


# --------------------------------------------------------------------------- the terminal gate (§14.16, §32.30)

@dataclass(frozen=True)
class TerminalGateFacts:
    """What START has established, under its lock, before it may record a marked integration's ``work_completed``.

    Every fact is required: none has a default, so an omitted check can never
    pass (RB5B-M7). The problem-list facts take ``None`` for "not established",
    which fails.
    """

    ordinary_precheck_passed: bool
    marker_matches: bool
    candidate_current: bool
    structural_validation_passed: bool
    structural_coverage_current: bool
    phase_basis_invalidated: bool
    review_complete: bool
    review_evidence_current: bool
    branch: str
    phase_outcome: str
    downstream_confirmation_modeled: bool
    blocking_problems: int
    dispositions_valid: bool
    receipt_authorizes_candidate: bool
    history_obligations_valid: bool
    incompatible_pending_successor: bool
    side_effect_problems: tuple[str, ...] | None
    conflicts: tuple[str, ...] | None
    unclosed_obligations: tuple[str, ...] | None


def terminal_gate_problems(facts: TerminalGateFacts) -> list[str]:
    """Why START may not record the marked integration's terminal stage yet; empty when every condition holds."""
    if type(facts) is not TerminalGateFacts:
        return [f"the terminal gate reads TerminalGateFacts, not {type(facts).__name__}"]
    problems = []
    for held, message in (
        (facts.ordinary_precheck_passed, "the ordinary Work completion precheck does not pass"),
        (facts.marker_matches, "the integration's marker no longer matches its Review"),
        (facts.candidate_current, "the Phase Integration Candidate is not current (base moved)"),
        (facts.structural_validation_passed, "structural validation does not pass"),
        (facts.structural_coverage_current, "the exact structural coverage is not current"),
        (facts.review_complete, "the required Review tasks / adjudication are not complete"),
        (facts.review_evidence_current, "the Review coverage / Evidence is not current"),
        (facts.dispositions_valid, "Problem LOW / Improvement dispositions do not satisfy H-1 / H-4"),
        (facts.receipt_authorizes_candidate,
         "no one valid G5 Receipt authorizes this exact Candidate and integration terminal stage"),
        (facts.history_obligations_valid, "the Run's P5 history obligations are not valid"),
    ):
        if held is not True:
            problems.append(message)
    if facts.phase_basis_invalidated is not False:
        problems.append("a newer Phase basis invalidation exists (or its absence was not established)")
    if facts.incompatible_pending_successor is not False:
        problems.append("an incompatible Review successor is pending (or its absence was not established)")
    if facts.branch != ri.BRANCH_AUTHORIZATION_READY:
        problems.append(f"the Integration Review branch is {facts.branch}, not {ri.BRANCH_AUTHORIZATION_READY}")
    if type(facts.blocking_problems) is not int or facts.blocking_problems:
        problems.append(f"{facts.blocking_problems!r} blocking Problem HIGH/MID remain (or the count is not established)")
    if facts.phase_outcome == ri.HUMAN_CONFIRMATION_REQUIRED and facts.downstream_confirmation_modeled is not True:
        problems.append("human_confirmation_required with no modeled downstream confirmation")
    elif facts.phase_outcome not in ri.AUTHORIZING_PHASE_OUTCOMES:
        problems.append(f"Phase outcome {facts.phase_outcome!r} does not complete the integration")
    for name, items in (("verification side effect", facts.side_effect_problems),
                        ("invalidation / Supersession / Consumption conflict", facts.conflicts),
                        ("unclosed obligation", facts.unclosed_obligations)):
        if items is None:
            problems.append(f"{name}: not established")
        else:
            problems += [f"{name}: {item}" for item in items]
    return problems


__all__ = [
    "OPERATION_NOTE_KEY", "SEMANTICS_LEGACY", "SEMANTICS_REVIEWED", "CODE_PHASE_REVIEW_REQUIRED",
    "CODE_PHASE_REVIEW_CONTRACT_UNSUPPORTED", "CODE_SEMANTICS_UNKNOWN", "CODE_REINTEGRATION_REQUIRED",
    "CODE_UNMARKED_UNFINISHED", "CODE_STRUCTURE_INVALID", "REASON_CONFIRMATION_CONFLICT", "ROUTE_NOT_INTEGRATION",
    "ROUTE_LEGACY_INTEGRATION", "ROUTE_PHASE_INTEGRATION_REVIEW", "fresh_operation_note", "mutation_semantics",
    "EntryGate", "entry_gate", "require_phase_review_for_registration", "marked_integration_spec",
    "reviewed_derivation_problems", "pre_existing_closure_gaps", "require_no_pre_existing_closure_gap",
    "CODE_COVERAGE_GAP", "reintegration_closure_relations",
    "require_reintegration_design", "CONFIRMATION_DESIRED_STATE", "CONFIRMATION_EXISTS", "CONFIRMATION_CREATE",
    "ConfirmationStructure", "confirmation_structure", "confirmation_decision", "confirmation_registration",
    "unowned_structural_difference", "build_candidate", "IntegrationRepairPlan", "repair_plan_problems",
    "fix_provenance", "repair_outcome_problems", "TerminalGateFacts", "terminal_gate_problems",
]
