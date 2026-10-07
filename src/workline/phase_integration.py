"""Phase integration structure (``WORKLINE_COMPLETION_SPRINT`` §14 / §32.6-§32.13): pure, over canonical truth.

What a Phase's integration covers is read from canonical Work metadata, events
and ``requires_completion`` relations only - a :class:`~workline.state.ProjectView`
and nothing else. Nothing here reads a Review record, opens a mutation, takes a
lock, writes a file or decides that an operation should proceed; the lifecycle
owners (START, Roadmap) and the generated-state reader call it.

```text
marker          phase_review_contract: phase-integration-review-v1, on a
                phase_integration_check Work only (§14.2 / §32.2)
mode            legacy | phase-integration-review-v1, per Phase (§32.7)
classification  the five coverage classes of one candidate integration (§14.6 / §32.8;
                downstream confirmation by the direct edge alone - ruling R5-1)
covering        any completed reviewed integration whose direct predecessors
                cover the current required set - never "the latest" (§32.10)
closure         the required predecessors a fresh / reintegration must get
                as direct edges (§32.11 - §32.13)
late work       where a newly added Work's coverage goes (§14.9)
facts           the structural basis material achievement / the Candidate
                digest, without reading Review history (§32.6, §32.33)
```

The marker is read through the frozen read-only interface ``Entity.phase_review_contract``
(§32.2). Whether a stored marker is *valid* is decided by structural validation
and by CREATE, never here: this module only asks whether an integration carries
exactly the supported contract.

Classification is mechanical. No timestamp, ID order, file order or "newest"
rule ever selects an integration or decides a class; lists come back in ID
order only so that they read and digest deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .errors import ValidationError
from .state import COMPLETE, COMPLETED, ProjectView
from .store import WORK_TERMINAL_EVENTS, Entity

# --------------------------------------------------------------------------- the marker (§14.2, §32.2)

#: The Work frontmatter key that carries the caller-decided Phase Review contract.
PHASE_REVIEW_CONTRACT_KEY = "phase_review_contract"
#: The one supported contract value.
PHASE_INTEGRATION_REVIEW_V1 = "phase-integration-review-v1"
#: Every value the marker may hold. Anything else fails validation (§14.2).
SUPPORTED_PHASE_REVIEW_CONTRACTS = (PHASE_INTEGRATION_REVIEW_V1,)

INTEGRATION_KIND = "phase_integration_check"
CONFIRMATION_KIND = "human_confirmation"
DEPENDENCY = "requires_completion"

# --------------------------------------------------------------------------- completion mode (§32.7)

MODE_LEGACY = "legacy"
MODE_REVIEWED = PHASE_INTEGRATION_REVIEW_V1
COMPLETION_MODES = (MODE_LEGACY, MODE_REVIEWED)

# --------------------------------------------------------------------------- coverage classes (§14.6, §32.8)

PRE_INTEGRATION = "pre_integration"
CURRENT_INTEGRATION = "current_integration"
POST_INTEGRATION_CONFIRMATION = "post_integration_confirmation"
HISTORICAL_INTEGRATION = "historical_integration"
INVALID_UNCOVERED = "invalid_uncovered"
COVERAGE_CLASSES = (
    PRE_INTEGRATION, CURRENT_INTEGRATION, POST_INTEGRATION_CONFIRMATION, HISTORICAL_INTEGRATION, INVALID_UNCOVERED,
)
#: The versioned identity of the classification rules above (§14.5 "versioned integration-coverage classification").
COVERAGE_CLASSIFICATION_VERSION = "phase-integration-coverage-v1"

# --------------------------------------------------------------------------- coverage status (§14.28, §32.51)

COVERAGE_NOT_APPLICABLE = "not_applicable"  # a legacy Phase
COVERAGE_COVERED = "covered"
COVERAGE_MISSING = "missing"  # no completed reviewed integration
COVERAGE_STALE = "stale"  # completed reviewed integration(s), none covers the current plan
COVERAGE_STATUSES = (COVERAGE_NOT_APPLICABLE, COVERAGE_COVERED, COVERAGE_MISSING, COVERAGE_STALE)

# --------------------------------------------------------------------------- late Work routes (§14.9, §32.12 - §32.13)

ROUTE_ADD_TO_UNFINISHED = "add_to_unfinished_integration"
ROUTE_REINTEGRATION_REQUIRED = "reintegration_required"
ROUTE_STRUCTURAL_STOP = "structural_stop"
#: A reviewed-mode Phase whose one unfinished integration carries no marker (structural STOP / reconcile).
ROUTE_UNMARKED_UNFINISHED = "unmarked_unfinished_integration"

# --------------------------------------------------------------------------- the CPQ-01 code (ruling CPQ-01)

#: The one code of the CPQ-01 predicate wherever it refuses or reports: structural validation's Problem
#: (:func:`coverage_order_problems`) and the owners' refusal (CREATE, the replan owners) - defined here only.
CODE_COVERAGE_ORDER = "integration_coverage_order"


# --------------------------------------------------------------------------- detection

def is_integration(work: Entity) -> bool:
    return work.work_kind == INTEGRATION_KIND


def is_reviewed_integration(work: Entity) -> bool:
    """An integration Work carrying exactly the supported Phase Review contract (§32.7)."""
    return work.work_kind == INTEGRATION_KIND and work.phase_review_contract == PHASE_INTEGRATION_REVIEW_V1


def reviewed_integrations(view: ProjectView, phase_id: str) -> list[Entity]:
    """The effective current-plan reviewed integrations of ``phase_id``, in ID order."""
    return sorted((w for w in view.effective_works(phase_id) if is_reviewed_integration(w)), key=lambda w: w.id)


def completion_mode(view: ProjectView, phase_id: str) -> str:
    """``phase-integration-review-v1`` when the effective current plan holds a reviewed integration, else ``legacy``.

    A Phase transitions to reviewed semantics only through a canonical
    effective integration that carries the marker (§32.5); an excluded marked
    integration leaves the Phase as its effective plan says.
    """
    return MODE_REVIEWED if reviewed_integrations(view, phase_id) else MODE_LEGACY


def confirmation_targets(work: Entity) -> tuple[str, ...]:
    """The Work IDs a ``human_confirmation`` names as ``confirmation_target`` (one or a list), as stored."""
    target = work.meta.get("confirmation_target")
    if target is None:
        return ()
    if isinstance(target, list):
        return tuple(str(item) for item in target)
    return (str(target),)


def is_downstream_confirmation(view: ProjectView, work: Entity, integration_id: str) -> bool:
    """A ``human_confirmation`` with the direct canonical ``requires_completion`` I -> confirmation edge.

    Orchestrator ruling R5-1 (§14.6 lines 2950 / 2954 and §14.7 line 2960 over
    the §32.8 wording at line 12975, by the precedence clause at line 12817):
    downstream-ness is decided by the canonical relation alone.
    ``confirmation_target`` is Work metadata, not a canonical relation, and is
    not a classification condition - so the confirmation a Human NG returns to
    (``start._human_ng`` adds ``new integration -> confirmation`` and keeps the
    old target) is downstream of the new integration. The edge must be direct;
    nothing is decided by order or time.
    """
    return work.work_kind == CONFIRMATION_KIND and any(
        relation.from_id == integration_id for relation in view.relations_to(work.id, DEPENDENCY)
    )


def downstream_confirmations(view: ProjectView, phase_id: str, integration_id: str) -> list[Entity]:
    """The effective structural confirmations downstream of ``integration_id``, in ID order."""
    return sorted(
        (w for w in view.effective_works(phase_id) if is_downstream_confirmation(view, w, integration_id)),
        key=lambda w: w.id,
    )


# --------------------------------------------------------------------------- direct coverage

def direct_predecessor_ids(view: ProjectView, integration_id: str) -> tuple[str, ...]:
    """Every ``from`` of a direct ``requires_completion`` -> ``integration_id`` edge, sorted and unique."""
    return tuple(sorted({relation.from_id for relation in view.relations_to(integration_id, DEPENDENCY)}))


def required_pre_integration_ids(
    view: ProjectView, phase_id: str, integration_id: str | None = None, *, planned_downstream: Iterable[str] = ()
) -> tuple[str, ...]:
    """§14.7 / §32.11: every effective non-integration Work that must directly precede the integration.

    That is every effective Work of the Phase except integrations (current or
    historical - historical integrations are never required predecessors) and
    except a structural ``human_confirmation`` downstream of the integration.
    Already-completed current-plan Works are included.

    ``integration_id=None`` asks for a fresh integration not registered yet.
    Its downstream confirmations cannot be read from ``view`` - a Human NG
    reintegration adds ``new integration -> confirmation`` in the very stage that
    registers the integration - so the caller names them in
    ``planned_downstream`` (existing ``human_confirmation`` Works the same
    registration makes downstream of the new integration by a direct edge).
    Only ``human_confirmation`` Works can be excluded that way (§32.11: a
    downstream structural human_confirmation is never a pre-integration
    predecessor); naming any other Work is refused.
    """
    planned = set(planned_downstream)
    for work_id in sorted(planned):
        work = view.works.get(work_id)
        if work is None or work.work_kind != CONFIRMATION_KIND or work.phase_id != phase_id:
            raise ValidationError(
                f"{work_id} is not a human_confirmation of Phase {phase_id}; only a confirmation can be planned "
                "downstream of an integration",
                code="validation_failed",
            )
    required = []
    for work in view.effective_works(phase_id):
        if work.id == integration_id or is_integration(work) or work.id in planned:
            continue
        if integration_id is not None and is_downstream_confirmation(view, work, integration_id):
            continue
        required.append(work.id)
    return tuple(sorted(required))


def missing_predecessor_ids(view: ProjectView, phase_id: str, integration_id: str) -> tuple[str, ...]:
    """The required pre-integration Works that lack their direct edge to ``integration_id``, sorted.

    An edge gap only. For a completed integration the ``invalid_uncovered``
    Works are these plus the Works whose edge exists but whose completion did
    not precede the integration's (CPQ-01) and any unfinished other integration
    (CPQ-02); see :func:`classify_coverage`.
    """
    direct = set(direct_predecessor_ids(view, integration_id))
    return tuple(work_id for work_id in required_pre_integration_ids(view, phase_id, integration_id)
                 if work_id not in direct)


def _require_phase_integration(view: ProjectView, phase_id: str, integration_id: str) -> Entity:
    work = view.works.get(integration_id)
    if work is None or work.phase_id != phase_id or not is_integration(work) \
            or view.work_state(integration_id).excluded:
        raise ValidationError(
            f"{integration_id} is not an effective phase_integration_check of Phase {phase_id}",
            code="validation_failed",
        )
    return work


def completion_ranks(view: ProjectView, work_ids: Iterable[str]) -> dict[str, int | None]:
    """Each Work's position in the canonical event log of its ``work_completed`` event, or ``None`` when it has none.

    The canonical event order is the order of ``view.events`` - the event log
    as the store reads it, and as a projection appends to it. It is lifecycle
    truth, not a timestamp: the ``at`` field is never read, and no ID order is
    involved.
    """
    wanted = set(work_ids)
    ranks: dict[str, int | None] = {work_id: None for work_id in wanted}
    for position, event in enumerate(view.events):
        if event.type == "work_completed" and event.entity in wanted and ranks[event.entity] is None:
            ranks[event.entity] = position
    return ranks


def completed_before(ranks: Mapping[str, int | None], work_id: str, integration_id: str) -> bool:
    """CPQ-01: whether ``work_id``'s ``work_completed`` precedes ``integration_id``'s in canonical event order.

    The deny-only validity condition for pre-integration coverage of an
    already-completed integration. A Work that has not completed, or completed
    after the integration, never counts - so no relation added later can
    launder late Work into an old covering integration. It never selects an
    integration; it only refuses coverage.
    """
    work_rank, integration_rank = ranks.get(work_id), ranks.get(integration_id)
    return work_rank is not None and integration_rank is not None and work_rank < integration_rank


def classify_from_edges(
    integration_id: str,
    work_kinds: Mapping[str, str | None],
    edges: Iterable[tuple[str, str]],
    ranks: Mapping[str, int | None],
) -> dict[str, str]:
    """The one classification rule, over plain data: effective Work kinds, ``requires_completion`` edges and
    canonical completion order (``ranks``, see :func:`completion_ranks`).

    ```text
    I itself                                              current_integration
    another integration that has COMPLETED                historical_integration
    another integration that has NOT completed            invalid_uncovered   (CPQ-02)
    human_confirmation with a direct I -> c edge          post_integration_confirmation   (R5-1)
    any other Work with a direct work -> I edge, and -
      when I has completed - whose own completion
      precedes I's in canonical event order               pre_integration     (CPQ-01, deny-only)
    otherwise                                             invalid_uncovered
    ```

    Control Plane rulings: R5-1 (the direct edge alone decides a downstream
    confirmation); CPQ-02 (``historical_integration`` is an older COMPLETED
    integration - an unfinished other integration fits no permitted role and is
    structurally invalid; the two-unfinished-integrations STOP stays);
    CPQ-01 (pre-integration coverage of an already-completed integration needs
    the Work's ``work_completed`` to precede the integration's - a deny-only
    validity condition, never a selection). A completed other integration is
    historical whatever its order relative to I, so no rule here ever selects
    "the latest" integration (§32.10). :func:`classify_coverage` and the
    Candidate's internal consistency check both use this function.
    Returned in Work ID order.
    """
    pairs = {(from_id, to) for from_id, to in edges}
    integration_completed = ranks.get(integration_id) is not None
    classes: dict[str, str] = {}
    for work_id in sorted(work_kinds):
        kind = work_kinds[work_id]
        if work_id == integration_id:
            classes[work_id] = CURRENT_INTEGRATION
        elif kind == INTEGRATION_KIND:
            classes[work_id] = HISTORICAL_INTEGRATION if ranks.get(work_id) is not None else INVALID_UNCOVERED
        elif kind == CONFIRMATION_KIND and (integration_id, work_id) in pairs:
            classes[work_id] = POST_INTEGRATION_CONFIRMATION
        elif (work_id, integration_id) in pairs and (
            not integration_completed or completed_before(ranks, work_id, integration_id)
        ):
            classes[work_id] = PRE_INTEGRATION
        else:
            classes[work_id] = INVALID_UNCOVERED
    return classes


def classify_coverage(view: ProjectView, phase_id: str, integration_id: str) -> dict[str, str]:
    """§32.8 with rulings R5-1 / CPQ-01 / CPQ-02: every effective Work of ``phase_id`` classified for the integration.

    Keyed by Work ID in ID order. ``integration_id`` must be an effective
    integration of the Phase. See :func:`classify_from_edges` for the rule.
    """
    _require_phase_integration(view, phase_id, integration_id)
    effective = sorted(view.effective_works(phase_id), key=lambda w: w.id)
    edges = [(r.from_id, r.to) for r in view.roadmap_relations if r.type == DEPENDENCY]
    ranks = completion_ranks(view, [w.id for w in effective])
    return classify_from_edges(integration_id, {w.id: w.work_kind for w in effective}, edges, ranks)


def invalid_uncovered_ids(view: ProjectView, phase_id: str, integration_id: str) -> tuple[str, ...]:
    classes = classify_coverage(view, phase_id, integration_id)
    return tuple(work_id for work_id, found in classes.items() if found == INVALID_UNCOVERED)


# --------------------------------------------------------------------------- covering integrations (§32.10)

def covering_integration_ids(view: ProjectView, phase_id: str) -> tuple[str, ...]:
    """Every completed reviewed integration with zero ``invalid_uncovered`` Works under :func:`classify_coverage`.

    That is: every required Work has its direct edge into the integration AND
    completed before it in canonical event order (CPQ-01), and no other
    integration is unfinished (CPQ-02). Any of them satisfies the structural
    predicate; none is "the latest". An older integration that no longer covers
    stays historical. ID order is a listing order, never a selection.
    """
    return tuple(
        work.id for work in reviewed_integrations(view, phase_id)
        if view.work_state(work.id).state == COMPLETED and not invalid_uncovered_ids(view, phase_id, work.id)
    )


@dataclass(frozen=True)
class CoverageStatus:
    """The reviewed-integration coverage of one Phase, read-only (§14.28, §32.51)."""

    phase_id: str
    mode: str
    status: str
    covering_integration_ids: tuple[str, ...] = ()
    unfinished_reviewed_integration_ids: tuple[str, ...] = ()
    #: Each completed reviewed integration that no longer covers, with the Works it does not cover.
    stale: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def reasons(self) -> tuple[str, ...]:
        """Why reviewed completion does not hold structurally; empty for a legacy or covered Phase."""
        if self.status == COVERAGE_MISSING:
            waiting = (f" (reviewed integration {', '.join(self.unfinished_reviewed_integration_ids)} is not completed)"
                       if self.unfinished_reviewed_integration_ids else "")
            return (f"no completed {PHASE_INTEGRATION_REVIEW_V1} integration covers the current effective plan: "
                    f"coverage missing{waiting}",)
        if self.status == COVERAGE_STALE:
            then = (f"coverage stale; awaiting reintegration {', '.join(self.unfinished_reviewed_integration_ids)}"
                    if self.unfinished_reviewed_integration_ids else "coverage stale; reintegration required")
            return tuple(
                f"{integration_id} no longer covers the current effective plan: uncovered {', '.join(uncovered)} "
                f"({then})"
                for integration_id, uncovered in self.stale
            )
        return ()


def coverage_status(view: ProjectView, phase_id: str) -> CoverageStatus:
    """Covered / missing / stale for a reviewed Phase; ``not_applicable`` for a legacy one."""
    reviewed = reviewed_integrations(view, phase_id)
    if not reviewed:
        return CoverageStatus(phase_id, MODE_LEGACY, COVERAGE_NOT_APPLICABLE)
    unfinished = tuple(w.id for w in reviewed if view.work_state(w.id).state != COMPLETED)
    covering = covering_integration_ids(view, phase_id)
    if covering:
        return CoverageStatus(phase_id, MODE_REVIEWED, COVERAGE_COVERED, covering, unfinished)
    stale = tuple(
        (w.id, invalid_uncovered_ids(view, phase_id, w.id))
        for w in reviewed if view.work_state(w.id).state == COMPLETED
    )
    if stale:
        return CoverageStatus(phase_id, MODE_REVIEWED, COVERAGE_STALE, (), unfinished, stale)
    return CoverageStatus(phase_id, MODE_REVIEWED, COVERAGE_MISSING, (), unfinished)


def completion_reasons(view: ProjectView, phase_id: str) -> tuple[str, ...]:
    """§32.9: the reasons reviewed completion adds to the legacy predicate; always empty for a legacy Phase.

    The structural part of the reviewed predicate: at least one completed
    reviewed integration, at least one of them covering the current required
    set (so zero ``invalid_uncovered`` for it). Every effective Work being
    completed - downstream confirmations included - and the integration
    invariant stay the legacy checks; structural validation stays the owners'
    pre/postcheck. Only entity / event / relation truth is read.
    """
    return coverage_status(view, phase_id).reasons


def phase_generated_complete(view: ProjectView, phase_id: str) -> bool:
    """Generated Phase completion including the reviewed predicate.

    ``view.phase_state(phase_id) == COMPLETE`` plus :func:`completion_reasons`
    empty. Once the generated-state reader applies :func:`completion_reasons`
    itself this is exactly ``phase_state == COMPLETE``; until then it is the
    reviewed-aware reading for the owners that need it.
    """
    return view.phase_state(phase_id) == COMPLETE and not completion_reasons(view, phase_id)


# --------------------------------------------------------------------------- late Work (§14.9, §32.12 - §32.13)

def late_work_route(view: ProjectView, phase_id: str) -> tuple[str, str | None]:
    """Where coverage for a Work added to ``phase_id`` now goes, and the unfinished integration when there is one.

    One unfinished integration -> the new Work and the integration's complete
    required closure are wired to it; none -> reintegration is required (a
    caller with no reintegration design STOPs ``reintegration_required`` before
    writing); two or more -> the existing structural STOP. Legitimate late Work
    is never refused to preserve an old completion.

    A reviewed-mode Phase whose one unfinished integration is unmarked gets its
    own structural route (:data:`ROUTE_UNMARKED_UNFINISHED`): wiring late Work to
    a legacy integration would leave the reviewed Phase uncoverable (it can
    never become the reviewed cover, and no reviewed reintegration can be
    created while it is unfinished). A legacy Phase keeps exactly the routes it
    always had.
    """
    unfinished = sorted(view.unfinished_integrations(phase_id), key=lambda w: w.id)
    if len(unfinished) >= 2:
        return ROUTE_STRUCTURAL_STOP, None
    if len(unfinished) == 1:
        if completion_mode(view, phase_id) == MODE_REVIEWED and not is_reviewed_integration(unfinished[0]):
            return ROUTE_UNMARKED_UNFINISHED, unfinished[0].id
        return ROUTE_ADD_TO_UNFINISHED, unfinished[0].id
    return ROUTE_REINTEGRATION_REQUIRED, None


def completed_integration_edge_problems(view: ProjectView, edges: Iterable[tuple[str, str, str]]) -> list[str]:
    """Why proposed relations would launder Work into an already-completed reviewed integration (RB5A-02, CPQ-01).

    ``edges`` are ``(type, from_id, to_id)`` a Workline owner is about to add.
    A new ``requires_completion`` edge whose successor is an effective reviewed
    integration that has already completed is refused unless the predecessor's
    ``work_completed`` precedes the integration's in canonical event order -
    the same predicate covering eligibility uses (:func:`completed_before`). A
    Work registered by the same operation has no completion yet and is always
    refused. Pure and deny-only: the owners (CREATE's projection check, the
    Roadmap / START replan relation paths) call it - that wiring is deferred
    integration. A legacy integration is never refused here.
    """
    problems = []
    for relation_type, from_id, to_id in edges:
        if relation_type != DEPENDENCY:
            continue
        target = view.works.get(to_id)
        if target is None or not is_reviewed_integration(target) or view.work_state(to_id).state != COMPLETED:
            continue
        if completed_before(completion_ranks(view, (from_id, to_id)), from_id, to_id):
            continue
        problems.append(
            f"requires_completion {from_id} -> {to_id}: {to_id} is a completed {PHASE_INTEGRATION_REVIEW_V1} "
            f"integration and {from_id} did not complete before it; late Work is covered by a reintegration, never by "
            "an edge onto a completed integration"
        )
    return problems


def coverage_order_problems(view: ProjectView) -> list[tuple[str, str]]:
    """CPQ-01 structural-validation helper: existing edges that try to launder late Work; empty when none.

    For every effective completed reviewed integration, each direct
    ``requires_completion`` predecessor that did not complete before the
    integration in canonical event order is reported as ``(code, message)`` -
    the shape ``validate.Problem`` takes - whatever that predecessor is: a Work
    of the Phase, a Work of another Phase, an excluded Work or another
    integration. That is exactly the scope the owners refuse
    (:func:`completed_integration_edge_problems`), so a structure an owner would
    refuse to create never stands unreported when it was written by hand
    (§14.9: "validation reports it"; post-RB6 integration finding RB5I-3).
    Reported, never repaired; no coverage changes with it (a predecessor that
    is not a required Work of the Phase is never classified). Wired into
    ``validate.validate_structure``.
    """
    problems: list[tuple[str, str]] = []
    for phase_id in sorted(view.phases):
        for integration in reviewed_integrations(view, phase_id):
            if view.work_state(integration.id).state != COMPLETED:
                continue
            predecessors = list(direct_predecessor_ids(view, integration.id))
            ranks = completion_ranks(view, [*predecessors, integration.id])
            for work_id in predecessors:
                if not completed_before(ranks, work_id, integration.id):
                    problems.append((
                        CODE_COVERAGE_ORDER,
                        f"requires_completion {work_id} -> {integration.id}: {work_id} did not complete before the "
                        f"completed {PHASE_INTEGRATION_REVIEW_V1} integration {integration.id}",
                    ))
    return problems


# --------------------------------------------------------------------------- structural facts (§32.6, §32.18, §32.33)

def terminal_event_id(view: ProjectView, work_id: str) -> str | None:
    """The ID of the Work's terminal lifecycle event (``work_completed`` / ``work_cancelled`` / ``plan_excluded``)."""
    found = [event.id for event in view.events_for(work_id) if event.type in WORK_TERMINAL_EVENTS]
    return found[-1] if found else None


def effective_work_facts(view: ProjectView, phase_id: str) -> list[dict[str, Any]]:
    """Per effective Work, in ID order: kind, marker, generated state and terminal event identity."""
    return [
        {
            "work_id": work.id,
            "work_kind": work.work_kind,
            PHASE_REVIEW_CONTRACT_KEY: work.phase_review_contract,
            "state": view.work_state(work.id).state,
            "terminal_event_id": terminal_event_id(view, work.id),
        }
        for work in sorted(view.effective_works(phase_id), key=lambda w: w.id)
    ]


def coverage_facts(view: ProjectView, phase_id: str, integration_id: str) -> dict[str, Any]:
    """The exact direct coverage of one integration: its predecessor edges and its downstream confirmations.

    Edges are bound by their endpoints, not by relation ID, so the same coverage
    reads as the same coverage.
    """
    _require_phase_integration(view, phase_id, integration_id)
    return {
        "integration_id": integration_id,
        "predecessor_ids": list(direct_predecessor_ids(view, integration_id)),
        "downstream_confirmation_ids": [w.id for w in downstream_confirmations(view, phase_id, integration_id)],
    }


def dependency_edges(view: ProjectView, phase_id: str) -> list[dict[str, str]]:
    """Every ``requires_completion`` relation touching an effective Work of the Phase, in relation ID order."""
    effective = {work.id for work in view.effective_works(phase_id)}
    return [
        {"relation_id": relation.id, "from": relation.from_id, "to": relation.to}
        for relation in sorted(view.roadmap_relations, key=lambda r: r.id)
        if relation.type == DEPENDENCY and (relation.from_id in effective or relation.to in effective)
    ]


__all__ = [
    "PHASE_REVIEW_CONTRACT_KEY", "PHASE_INTEGRATION_REVIEW_V1", "SUPPORTED_PHASE_REVIEW_CONTRACTS",
    "MODE_LEGACY", "MODE_REVIEWED", "COMPLETION_MODES", "COVERAGE_CLASSES", "COVERAGE_CLASSIFICATION_VERSION",
    "PRE_INTEGRATION", "CURRENT_INTEGRATION", "POST_INTEGRATION_CONFIRMATION", "HISTORICAL_INTEGRATION",
    "INVALID_UNCOVERED", "COVERAGE_STATUSES", "CoverageStatus",
    "ROUTE_ADD_TO_UNFINISHED", "ROUTE_REINTEGRATION_REQUIRED", "ROUTE_STRUCTURAL_STOP", "ROUTE_UNMARKED_UNFINISHED",
    "CODE_COVERAGE_ORDER",
    "classify_from_edges", "completed_integration_edge_problems", "completion_ranks", "completed_before",
    "coverage_order_problems",
    "is_integration", "is_reviewed_integration", "reviewed_integrations", "completion_mode", "confirmation_targets",
    "is_downstream_confirmation", "downstream_confirmations", "direct_predecessor_ids", "required_pre_integration_ids",
    "missing_predecessor_ids", "classify_coverage", "invalid_uncovered_ids", "covering_integration_ids",
    "coverage_status", "completion_reasons", "phase_generated_complete", "late_work_route", "terminal_event_id",
    "effective_work_facts", "coverage_facts", "dependency_edges",
]
