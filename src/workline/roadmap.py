"""Roadmap (``skills/roadmap``).

Roadmap is the operation owner for Roadmap meaning, Phase meaning and
relations, startable Phase selection, Phase entry (Work structure, first
integration, structural human_confirmation), future-plan maintenance
(hold / resume / cancel / plan exclusion with replan), Phase addition to an
existing Roadmap, and the explicit Roadmap achievement judgement.
Registration goes through Phase CREATE / CREATE and the Mutation Controller;
Roadmap never executes Works and never lets START cross into the next Phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from . import gitcmd, gitops
from .create import (
    RegistrationResult,
    RelatedSpec,
    RelationSpec,
    WorkSpec,
    register_works,
    related_edge_key,
    validate_related_specs,
)
from .errors import ReconcileRequired, SpecViolation, StopError, ValidationError
from .mutation import (
    Effect,
    Mutation,
    MutationController,
    WriteScope,
    abandon_on_stop,
    pending_for_slot,
    require_same_request,
    same_request,
)
from .oplock import project_operation
from .ops import (
    Replan,
    apply_replan,
    event_effects,
    owned_canonical_paths,
    plan_replan,
    problems_text,
    projected_view,
    validate_projection,
)
from .phase_create import PhaseRelationSpec, PhaseSpec, register_phases
from .state import (
    ACHIEVED,
    ACTIVE,
    AMBIGUOUS_CANDIDATES,
    CANCELLED,
    COMPLETE,
    COMPLETED,
    FINISHED_STATES,
    HELD,
    PLAN_EXCLUDED,
    TERMINAL_STATES,
    UNSTARTED,
    ProjectView,
)
from .store import (
    ROADMAP_BACKGROUND_HEADING,
    ROADMAP_DESIRED_HEADING,
    ROADMAP_OUT_OF_SCOPE_HEADING,
    ROADMAP_SCOPE_HEADING,
    WORKLINE_DIR,
    Entity,
    ProjectStore,
    Relation,
    render_body,
    render_entity,
)
from .validate import validate_structure

OWNER = "roadmap"

ROADMAP_RELATIONS = f"{WORKLINE_DIR}/relations/roadmap.yaml"
RELATED_RELATIONS = f"{WORKLINE_DIR}/relations/related.yaml"
EVENT_LOG = f"{WORKLINE_DIR}/events/events.jsonl"
#: Every canonical ledger a Roadmap operation can write; the fallback for one
#: whose own set is not written down.
LEDGER_FILES = (ROADMAP_RELATIONS, RELATED_RELATIONS, EVENT_LOG)

#: Which of those each operation can write, on any path it has.
#:
#: A declared write scope is what says whether an interrupted operation and a
#: new one are independent (``rules/git``: a pending mutation not provably
#: independent of the planned scope is ``reconcile required``). Declaring every
#: ledger for every operation therefore made two operations that never touch the
#: same file look like a conflict - a Phase put on hold writes only the event
#: log, yet an unfinished one stopped a Related correction that writes only
#: ``related.yaml``.
#:
#: These are the files each operation *can* write, not the ones a particular
#: call did: a conditional write still belongs here, because scope is declared
#: before the operation knows which path it takes. A shared ledger is rewritten
#: whole, so two operations that can both write one are never independent, and
#: both keep it here.
OPERATION_LEDGERS: dict[str, tuple[str, ...]] = {
    # Roadmap and Phase registration write Roadmap-decided Phase relations.
    # They record no event and no Related.
    "roadmap-create": (ROADMAP_RELATIONS,),
    "roadmap-add-phases": (ROADMAP_RELATIONS,),
    # Phase expansion registers Works with their relations and Related data.
    # Expansion is not a lifecycle event, so it never writes the event log.
    "phase-entry": (ROADMAP_RELATIONS, RELATED_RELATIONS),
    # A lifecycle decision is one appended event and nothing else.
    "phase-hold": (EVENT_LOG,),
    "phase-resume": (EVENT_LOG,),
    "phase-cancel": (EVENT_LOG,),
    "roadmap-hold": (EVENT_LOG,),
    "roadmap-resume": (EVENT_LOG,),
    "roadmap-cancel": (EVENT_LOG,),
    "roadmap-achievement": (EVENT_LOG,),
    # Plan exclusion records its event and then applies the replan, which can
    # register Works (Related) and add or remove Roadmap relations.
    "phase-plan-exclude": LEDGER_FILES,
    "work-plan-exclude": LEDGER_FILES,
    # Related maintenance is a plan correction, never a lifecycle event.
    "work-related-maintenance": (RELATED_RELATIONS,),
}


def _ledgers(operation: str) -> tuple[str, ...]:
    """The canonical ledgers ``operation`` can write.

    An operation whose set is not written down declares all of them, so a new
    one added without a decision here is over-declared - stopping more than it
    must - rather than wrongly declared independent of everything it touches.
    """
    return OPERATION_LEDGERS.get(operation, LEDGER_FILES)


# --------------------------------------------------------------------------- payloads

@dataclass(frozen=True)
class RoadmapPlan:
    name: str
    background: str
    desired_state: str
    phases: dict[str, PhaseSpec]
    relations: tuple[PhaseRelationSpec, ...] = ()
    scope: str | None = None
    out_of_scope: str | None = None


@dataclass(frozen=True)
class RoadmapResult:
    roadmap_id: str
    phase_ids: dict[str, str]
    mutation_id: str
    head: str | None
    resumed: bool


@dataclass(frozen=True)
class PhaseAdditionResult:
    roadmap_id: str
    phase_ids: dict[str, str]
    relation_ids: dict[int, str]
    mutation_id: str
    head: str | None
    resumed: bool


@dataclass(frozen=True)
class WorkDesign:
    name: str
    desired_state: str
    related: tuple[RelatedSpec, ...] = ()


@dataclass(frozen=True)
class PhaseEntryDesign:
    works: dict[str, WorkDesign]
    integration: WorkDesign
    human_confirmation: WorkDesign | None = None
    planned_next: tuple[tuple[str, str], ...] = ()
    requires_completion: tuple[tuple[str, str], ...] = ()
    entry: str | None = None


@dataclass(frozen=True)
class PhaseEntryResult:
    phase_id: str
    work_ids: dict[str, str]
    integration_id: str | None
    confirmation_id: str | None
    entry_work_id: str | None
    expanded: bool
    mutation_id: str | None
    head: str | None


@dataclass(frozen=True)
class OperationResult:
    status: str
    entity_id: str
    mutation_id: str | None
    head: str | None
    detail: str = ""


# --------------------------------------------------------------------------- helpers

def _stop_on_structure(store: ProjectStore, context: str) -> ProjectView:
    view = ProjectView.load(store)
    problems = validate_structure(view)
    if problems:
        raise ValidationError(f"{context}: {problems_text(problems)}", code="structure_invalid")
    return view


def _open(
    store: ProjectStore, operation: str, identity: dict[str, Any], entities: list[str] = ()
) -> tuple[Mutation, gitops.PushDestination | None]:
    """Open (or resume) the operation's mutation with a verified push destination.

    The destination is checked before the mutation exists, so an unpinned or
    drifted remote STOPs with no intent record, no domain write and no network
    contact.
    """
    destination = gitops.ensure_push_destination(store)
    controller = MutationController(store)
    invocation = {"operation": operation, **identity}
    mutation = controller.open(OWNER, invocation, WriteScope(entities=tuple(entities), files=_ledgers(operation)))
    gitops.ensure_git_ready(store.root)
    gitops.record_preexisting_dirty(mutation, store.root)
    mutation.apply()
    return mutation, destination


def _finalize(
    mutation: Mutation, destination: gitops.PushDestination | None, message: str, extra_paths: list[str] = ()
) -> str | None:
    paths = sorted(set(owned_canonical_paths(mutation)) | set(extra_paths))
    gitops.finalize(mutation, "finalize", message, paths, destination=destination)
    _stop_on_structure(mutation.store, "postcheck")
    mutation.complete()
    return gitcmd.head_commit(mutation.store.root)


def _require_active_roadmap(view: ProjectView, roadmap_id: str) -> None:
    if roadmap_id not in view.roadmaps:
        raise ValidationError(f"Roadmap unresolvable: {roadmap_id}")
    lifecycle = view.roadmap_lifecycle(roadmap_id)
    if lifecycle in (CANCELLED, ACHIEVED):
        raise SpecViolation(f"Roadmap {roadmap_id} is {lifecycle}")
    if lifecycle == HELD:
        raise StopError(f"Roadmap {roadmap_id} is held; resume it first", code="roadmap_held")


# --------------------------------------------------------------------------- decided request

ROADMAP_REQUEST_VERSION = 1


def _related_records(specs: tuple[RelatedSpec, ...]) -> list[dict[str, Any]]:
    return [{"type": r.type, "to": r.to, "condition": r.condition} for r in specs]


def _phase_records(phases: dict[str, PhaseSpec]) -> list[dict[str, Any]]:
    """The Phases as decided, in declared order: that order sets their display numbers.

    The desired state is stripped because rendering strips it
    (``store.render_body``); the name is kept verbatim because rendering writes
    it as given.
    """
    return [
        {"key": key, "name": spec.name, "desired_state": spec.desired_state.strip()}
        for key, spec in phases.items()
    ]


def _phase_relation_records(relations: tuple[PhaseRelationSpec, ...]) -> list[dict[str, str]]:
    """Declared order is kept: it decides which reservation each relation gets.

    Endpoints are recorded as the caller wrote them. An endpoint naming a spec
    key and one naming the Phase ID that key was reserved as resolve to the same
    relation, yet they are two requests here, because this identity is fixed
    before any ID is reserved and so cannot resolve one into the other. Treating
    them as one would mean trusting a caller that read this run's reservations
    out of the recovery record and rewrote its request around them.
    """
    return [{"type": r.type, "from": r.from_ref, "to": r.to_ref} for r in relations]


def _optional_section(text: str | None) -> str | None:
    """An optional section as the writer sees it: present and stripped, or absent.

    ``None`` and ``""`` leave the section out of the body entirely while a
    blank string puts an empty one in, so presence is recorded separately from
    content instead of being collapsed by stripping.
    """
    return text.strip() if text else None


def roadmap_request_identity(plan: RoadmapPlan) -> dict[str, Any]:
    """What a Roadmap creation decided, in the form its mutation records.

    A Roadmap's name does not say what the Roadmap is, and its creation writes
    the Roadmap *and* its Phases; resuming one plan's half-written creation with
    another leaves a Roadmap that is partly one plan and partly another. The
    plan therefore travels in the invocation, durable before any ID is reserved.
    """
    return {
        "version": ROADMAP_REQUEST_VERSION,
        "name": plan.name,
        "background": plan.background.strip(),
        "desired_state": plan.desired_state.strip(),
        "scope": _optional_section(plan.scope),
        "out_of_scope": _optional_section(plan.out_of_scope),
        "phases": _phase_records(plan.phases),
        "relations": _phase_relation_records(plan.relations),
    }


def phase_addition_request_identity(
    phases: dict[str, PhaseSpec], relations: tuple[PhaseRelationSpec, ...]
) -> dict[str, Any]:
    """What a Phase addition decided.

    ``future_plan_change`` is deliberately not part of it: it decides whether a
    held Roadmap accepts the addition at all and never reaches an effect, so two
    requests differing only there register exactly the same Phases. It is
    checked before the mutation is opened instead, so a request refused for it
    leaves no record behind either.
    """
    return {
        "version": ROADMAP_REQUEST_VERSION,
        "phases": _phase_records(phases),
        "relations": _phase_relation_records(relations),
    }


def related_request_identity(add: tuple[RelatedSpec, ...], remove_relation_ids: tuple[str, ...]) -> dict[str, Any]:
    """What a related maintenance request decided.

    Structural rather than the printable key of :func:`_related_request_key`:
    that key joins caller text with separators it does not escape, so two
    different requests can spell the same key. Order is kept because it decides
    which reservation each addition gets.
    """
    return {
        "version": ROADMAP_REQUEST_VERSION,
        "add": _related_records(add),
        "remove": list(remove_relation_ids),
    }


def _collapse_related_request(
    work_id: str, add: tuple[RelatedSpec, ...], remove_relation_ids: tuple[str, ...]
) -> tuple[tuple[RelatedSpec, ...], tuple[str, ...]]:
    """The request with its own repeats folded away, keeping the first of each.

    :func:`_resolve_related_changes` already treats a repeated edge or a
    repeated removal ID as one, so ``(E, E)`` and ``(E,)`` decide the same
    thing. They are folded here, before the identity is built *and* before the
    request is resolved, so the two spellings are one request that also reserves
    the same relation IDs - the reservation key is the position in the request,
    and a retry must keep the IDs its first attempt issued.

    Only the request's own repeats are folded. What the Project already holds is
    left to resolution, so the identity says what was asked for, independently
    of the state it meets.
    """
    seen_edges: set[tuple] = set()
    adds: list[RelatedSpec] = []
    for spec in add:
        key = related_edge_key(spec.type, work_id, spec.to, spec.condition)
        if key not in seen_edges:
            seen_edges.add(key)
            adds.append(spec)
    seen_ids: set[str] = set()
    removals: list[str] = []
    for relation_id in remove_relation_ids:
        if relation_id not in seen_ids:
            seen_ids.add(relation_id)
            removals.append(relation_id)
    return tuple(adds), tuple(removals)


# --------------------------------------------------------------------------- new Roadmap

def create_roadmap(store: ProjectStore, plan: RoadmapPlan) -> RoadmapResult:
    if not plan.name.strip() or not plan.background.strip() or not plan.desired_state.strip():
        raise ValidationError("Roadmap needs name, background and desired state")
    if not plan.phases:
        raise ValidationError("a new Roadmap registers all of its Phases; none were decided")
    with project_operation(store, "roadmap-create", {"name": plan.name}):
        _stop_on_structure(store, "precheck")
        request = roadmap_request_identity(plan)
        require_same_request(
            pending_for_slot(store, OWNER, {"operation": "roadmap-create", "name": plan.name}),
            request,
            f"Roadmap creation of {plan.name!r}",
        )
        mutation, destination = _open(store, "roadmap-create", {"name": plan.name, "request": request})
        with abandon_on_stop(mutation):
            return _create_roadmap(store, mutation, destination, plan)


def _create_roadmap(
    store: ProjectStore, mutation: Mutation, destination: gitops.PushDestination | None, plan: RoadmapPlan
) -> RoadmapResult:
    roadmap_id = mutation.reserve_id("roadmap", "roadmap")
    mutation.extend_scope(entities=[roadmap_id])

    if not mutation.has_stage("roadmap"):
        sections = [(ROADMAP_BACKGROUND_HEADING, plan.background), (ROADMAP_DESIRED_HEADING, plan.desired_state)]
        if plan.scope:
            sections.append((ROADMAP_SCOPE_HEADING, plan.scope))
        if plan.out_of_scope:
            sections.append((ROADMAP_OUT_OF_SCOPE_HEADING, plan.out_of_scope))
        meta = {"id": roadmap_id, "display": f"R-{store.count_entities('roadmap') + 1:02d}", "type": "roadmap"}
        content = render_entity(meta, render_body(plan.name, sections))
        mutation.add_effects("roadmap", [Effect.write_file(ProjectStore.entity_rel_path("roadmap", roadmap_id), content)])
    mutation.apply()

    phases = register_phases(mutation, "phases", roadmap_id, plan.phases, list(plan.relations))
    head = _finalize(
        mutation, destination, f"chore(workline): create roadmap {ProjectView.load(store).roadmaps[roadmap_id].display}"
    )
    return RoadmapResult(roadmap_id, phases.phase_ids, mutation.id, head, mutation.resumed)


# --------------------------------------------------------------------------- Phase addition

def add_phases(
    store: ProjectStore,
    roadmap_id: str,
    phases: dict[str, PhaseSpec],
    relations: tuple[PhaseRelationSpec, ...] = (),
    *,
    future_plan_change: bool = False,
    invocation_key: str | None = None,
) -> PhaseAdditionResult:
    """Add already-decided Phases to an existing Roadmap (Roadmap operation).

    This is the formal recovery / replan path the achievement check requires
    (``not_achieved`` → add Phases / replan *without* changing the desired
    state). Roadmap owns the mutation, the structural check and the Git
    finalization; Phase CREATE participates as the child registration. The
    Roadmap body is never rewritten and existing Phases / relations are never
    touched: only new Phases and Roadmap-decided Phase relations are added.

    ``relations`` endpoints are spec keys of ``phases`` or existing Phase IDs.
    A cancelled / achieved Roadmap takes no normal Phase addition; a held
    Roadmap follows the existing lifecycle rule and needs a decided
    ``future_plan_change``.
    """
    if not phases:
        raise ValidationError("Phase addition needs at least one decided Phase")
    with project_operation(store, "roadmap-add-phases", {"roadmap_id": roadmap_id}):
        return _add_phases_locked(store, roadmap_id, phases, relations, future_plan_change, invocation_key)


def _add_phases_locked(
    store: ProjectStore,
    roadmap_id: str,
    phases: dict[str, PhaseSpec],
    relations: tuple[PhaseRelationSpec, ...],
    future_plan_change: bool,
    invocation_key: str | None,
) -> PhaseAdditionResult:
    view = _stop_on_structure(store, "precheck")
    if roadmap_id not in view.roadmaps:
        raise ValidationError(f"Roadmap unresolvable: {roadmap_id}")
    lifecycle = view.roadmap_lifecycle(roadmap_id)
    if lifecycle in (CANCELLED, ACHIEVED):
        raise SpecViolation(f"Roadmap {roadmap_id} is {lifecycle}; no Phase addition")
    display = view.roadmaps[roadmap_id].display

    identity = {
        "roadmap_id": roadmap_id,
        "key": invocation_key or " | ".join(spec.name for spec in phases.values()),
    }
    request = phase_addition_request_identity(phases, relations)
    # First, so that an unfinished addition this request cannot continue is
    # reported as what it is. The held-Roadmap rule below would otherwise hide
    # it behind a lifecycle fact that says nothing about the stranded record.
    require_same_request(
        pending_for_slot(store, OWNER, {"operation": "roadmap-add-phases", **identity}),
        request,
        f"Phase addition to {roadmap_id}",
    )
    if lifecycle == HELD and not future_plan_change:
        # Still decided before the mutation exists, so two requests differing
        # only in this flag are one request as far as resume is concerned, and a
        # request refused for it leaves no record behind. Phase CREATE keeps the
        # same precheck as part of its own contract.
        raise SpecViolation(f"Roadmap {roadmap_id} is held; Phase addition needs a decided future-plan change")
    mutation, destination = _open(store, "roadmap-add-phases", {**identity, "request": request}, [roadmap_id])
    with abandon_on_stop(mutation):
        registered = register_phases(
            mutation, "phases", roadmap_id, phases, list(relations), future_plan_change=future_plan_change
        )
        head = _finalize(mutation, destination, f"chore(workline): add phases to roadmap {display}")
    return PhaseAdditionResult(
        roadmap_id, registered.phase_ids, registered.relation_ids, mutation.id, head, mutation.resumed
    )


# --------------------------------------------------------------------------- startable Phase

def startable_phases(store: ProjectStore, roadmap_id: str) -> list[Entity]:
    view = _stop_on_structure(store, "precheck")
    _require_active_roadmap(view, roadmap_id)
    return view.startable_phases(roadmap_id)


def select_phase(store: ProjectStore, roadmap_id: str, explicit: str | None = None) -> Entity | None:
    """Select the Phase to enter.

    Returns None only when nothing was explicitly asked for and there is no
    startable candidate (the achievement-check / diagnosis path).
    """
    view = _stop_on_structure(store, "precheck")
    _require_active_roadmap(view, roadmap_id)
    candidates = view.startable_phases(roadmap_id)
    # An explicit Phase is validated first: an invalid explicit choice means the
    # same thing whether or not other candidates exist.
    if explicit is not None:
        for phase in candidates:
            if phase.id == explicit:
                return phase
        raise SpecViolation(f"{explicit} is not a startable Phase")
    # The plan decides, or nothing does: several equally planned Phases STOP
    # here rather than being separated by the order they were read in.
    return view.choose_startable(candidates, "Phase")


def diagnose_no_candidate(store: ProjectStore, roadmap_id: str) -> str:
    view = ProjectView.load(store)
    if view.all_active_phases_complete(roadmap_id):
        return "all active Phases complete: run the Roadmap achievement check"
    reasons = []
    for phase in view.active_phases(roadmap_id):
        state = view.phase_state(phase.id)
        if state == COMPLETE:
            continue
        if state == HELD:
            reasons.append(f"{phase.id} held")
        unsatisfied = view.unsatisfied_dependencies(phase.id)
        if unsatisfied:
            reasons.append(f"{phase.id} blocked by " + ", ".join(f"{r.from_id} ({label})" for r, label in unsatisfied))
    return "; ".join(reasons) or "no startable Phase"


# --------------------------------------------------------------------------- Phase entry

# The shape of the Phase-entry design as the mutation records it. Bumped only
# when the recorded shape changes meaning; it is operation-local to Phase entry
# and is not the intent record's own version.
DESIGN_IDENTITY_VERSION = 1


def design_identity(design: PhaseEntryDesign) -> dict[str, Any]:
    """What this Phase expansion is expanding, in the form the mutation records.

    An interrupted expansion can only be continued if it is provable that the
    continuation is expanding the same plan. Nothing in the Project's own files
    says which design a half-finished expansion belonged to - the design's keys
    are never persisted, and a stage that was never recorded left no trace at
    all - so the plan is written into the mutation's invocation, which
    ``MutationController.begin`` makes durable before a single ID is reserved.

    It holds the design itself rather than a digest of it, so a record can be
    read and understood by a human reconciling it. The declared order of the
    normal Works is kept: it decides their display numbers, so reordering them
    is a different plan, not the same one written differently. Sequences are
    lists of mappings because the recovery record's format does not nest
    sequences.
    """

    def related(specs: "tuple[RelatedSpec, ...]") -> list[dict[str, Any]]:
        return [{"type": r.type, "to": r.to, "condition": r.condition} for r in specs]

    def work(w: WorkDesign) -> dict[str, Any]:
        # The desired state is stripped because that is what rendering keeps
        # (``store.render_body``), so two designs whose desired states differ
        # only in surrounding whitespace really are the same plan. The name is
        # kept verbatim: rendering writes it as given, so its whitespace does
        # reach the Project's files.
        return {"name": w.name, "desired_state": w.desired_state.strip(), "related": related(w.related)}

    def pairs(items: "tuple[tuple[str, str], ...]") -> list[dict[str, str]]:
        return [{"from": a, "to": b} for a, b in items]

    return {
        "version": DESIGN_IDENTITY_VERSION,
        "works": [{"key": key, **work(w)} for key, w in design.works.items()],
        "integration": work(design.integration),
        "confirmation": work(design.human_confirmation) if design.human_confirmation is not None else None,
        "planned_next": pairs(design.planned_next),
        "requires_completion": pairs(design.requires_completion),
        "entry": design.entry,
    }


def _pending_phase_entry(store: ProjectStore, phase_id: str) -> list[dict[str, Any]]:
    """This Phase's own unfinished Phase entries, whatever design they carry."""
    return [
        record
        for record in MutationController(store).list_pending()
        if record["owner"] == OWNER
        and record["invocation"].get("operation") == "phase-entry"
        and record["invocation"].get("phase_id") == phase_id
    ]


def _require_resumable(pending: list[dict[str, Any]], phase_id: str, identity: dict[str, Any]) -> None:
    """STOP unless this interrupted expansion is provably the one now being asked for.

    Continuing one plan's half-applied expansion with another plan would leave a
    Phase that is partly one design and partly another, which no later reader
    could untangle. Where that cannot be ruled out the expansion is left exactly
    as it is, for a human to reconcile: nothing is abandoned, removed, replaced
    or rolled back.
    """
    legacy = [record for record in pending if record["invocation"].get("design") is None]
    if legacy:
        raise ReconcileRequired(
            "legacy pending Phase entry "
            + ", ".join(sorted(record["mutation_id"] for record in legacy))
            + f" of Phase {phase_id}: the record is still pending but was written before Phase entry "
            "wrote down which design it was expanding, so the design identity needed to resume it "
            "automatically is missing and no continuation can be shown to be the same plan; it is "
            "left untouched: reconcile required"
        )
    if len(pending) > 1:
        raise ReconcileRequired(
            f"Phase {phase_id} has {len(pending)} unfinished Phase entries "
            f"({', '.join(sorted(record['mutation_id'] for record in pending))}): reconcile required"
        )
    record = pending[0]
    if not same_request(record["invocation"].get("design"), identity):
        raise ReconcileRequired(
            f"the unfinished Phase entry {record['mutation_id']} of Phase {phase_id} is expanding a "
            "different design from the one now given; an interrupted expansion is never continued "
            "with another plan, and it is left untouched: reconcile required"
        )


def _recorded_registration(mutation: Mutation, stage: str, keys: list[str]) -> RegistrationResult:
    """What a stage already recorded, read back instead of decided a second time.

    ``_open`` has already classified and applied every recorded effect, so this
    stage is done. Asking the registration core again would reserve its IDs
    again, validate its specs against a Project that already contains them, and
    project a structure that already exists - which is how a recorded
    integration comes to be counted twice. The stage's own reservations and
    effects say everything the rest of the expansion needs from it.
    """
    work_ids: dict[str, str] = {}
    for key in keys:
        work_id = mutation.reserved(f"{stage}:work:{key}")
        if work_id is None:
            raise ReconcileRequired(
                f"the unfinished Phase entry {mutation.id} recorded stage {stage!r} without "
                f"reserving {key!r}: reconcile required"
            )
        work_ids[key] = work_id
    effects = mutation.stage_effects(stage)
    paths = [effect["payload"]["path"] for effect in effects if effect["kind"] == "write_file"]
    files = {effect["payload"]["file"] for effect in effects if effect["kind"] == "add_relation"}
    if "roadmap" in files:
        paths.append(f"{WORKLINE_DIR}/relations/roadmap.yaml")
    if "related" in files:
        paths.append(f"{WORKLINE_DIR}/relations/related.yaml")
    return RegistrationResult(work_ids, {}, tuple(paths))


def enter_phase(store: ProjectStore, phase_id: str, design: PhaseEntryDesign) -> PhaseEntryResult:
    with project_operation(store, "phase-entry", {"phase_id": phase_id}):
        return _enter_phase_locked(store, phase_id, design)


def _enter_phase_locked(store: ProjectStore, phase_id: str, design: PhaseEntryDesign) -> PhaseEntryResult:
    view = _stop_on_structure(store, "precheck")
    phase = view.phases.get(phase_id)
    if phase is None:
        raise ValidationError(f"Phase unresolvable: {phase_id}")
    roadmap_id = phase.roadmap_id or ""
    _require_active_roadmap(view, roadmap_id)
    state = view.phase_state(phase_id)
    if state == COMPLETE:
        raise SpecViolation(f"Phase {phase_id} is already complete")
    if state in (HELD, CANCELLED, PLAN_EXCLUDED):
        raise SpecViolation(f"Phase {phase_id} is {state}")
    unsatisfied = view.unsatisfied_dependencies(phase_id)
    if unsatisfied:
        raise StopError(
            f"Phase {phase_id} is blocked by " + ", ".join(f"{r.from_id} ({label})" for r, label in unsatisfied),
            code="phase_blocked",
        )

    identity = design_identity(design)
    interrupted = _pending_phase_entry(store, phase_id)
    if interrupted:
        # An expansion of this Phase is unfinished. It is continued only where
        # it is provably the same plan; otherwise it is left for reconciliation
        # rather than hidden behind the already-expanded refusal.
        _require_resumable(interrupted, phase_id, identity)
    if view.phase_works(phase_id):
        if not interrupted:
            # This Phase already holds its Works, so there is nothing for a design
            # to register. Taking the design as read would let a caller believe a
            # different plan had been recorded, so it is refused rather than
            # ignored: what this Phase holds is read through the Project's
            # read-only state, and a formal change to it belongs to the Roadmap's
            # own maintenance (``rules/ai-decision``).
            raise StopError(
                f"Phase {phase_id} is already expanded, so a new entry design is not accepted; "
                "read the current structure instead, and change it through Roadmap maintenance",
                code="phase_already_expanded",
            )
    if not design.works:
        raise ValidationError("Phase entry needs at least one normal Work")
    for key in design.works:
        if key in ("integration", "confirmation"):
            raise ValidationError(f"reserved Work key: {key}")
    _require_startable_entry(view, design)
    if not interrupted:
        # Only a new expansion is refused for being undecided. One already under
        # way is carried to its end (BL-023): the entry Work is a return value,
        # not part of what the expansion registers, so leaving it unchosen is
        # reported afterwards rather than stranding a half-finished expansion.
        _require_unique_entry(view, design)

    mutation, destination = _open(store, "phase-entry", {"phase_id": phase_id, "design": identity}, [phase_id])
    if mutation.resumed:
        # An expansion that already exists is carried forward, never given up:
        # abandoning it would strand the IDs it reserved and the effects it
        # recorded. Only a Phase entry that this run started may be abandoned
        # before its first effect.
        return _expand_phase(store, mutation, destination, phase, phase_id, roadmap_id, design)
    with abandon_on_stop(mutation):
        return _expand_phase(store, mutation, destination, phase, phase_id, roadmap_id, design)


def _require_startable_entry(view: ProjectView, design: PhaseEntryDesign) -> None:
    """Refuse an explicit entry that this expansion could not start, before it writes.

    Whether the named Work can be the one to start is decided by the design and
    the Works that already exist, so it is decided here - before the intent, the
    reserved IDs, the entities and the commit - rather than discovered once the
    expansion is finalized. Every Work this expansion creates is unstarted and in
    the effective set, and the Phase lifecycle has already been checked, so
    startability comes down to the incoming ``requires_completion`` the design
    asks for: a predecessor this same expansion creates cannot be complete yet,
    and an existing one has to be complete already.
    """
    if design.entry is None:
        return
    if design.entry not in design.works:
        raise SpecViolation(f"entry Work {design.entry} is not one of this design's Works")
    blocking: list[str] = []
    for predecessor, successor in design.requires_completion:
        if successor != design.entry:
            continue
        if predecessor in design.works:
            blocking.append(f"{predecessor} (created by this expansion)")
            continue
        label = view.entity_state_label(predecessor)
        if label == "unresolvable":
            continue  # an unresolvable endpoint is refused by the registration core
        if label not in (COMPLETED, COMPLETE):
            blocking.append(f"{predecessor} ({label})")
    if blocking:
        raise SpecViolation(
            f"entry Work {design.entry} cannot be started by this expansion: it requires "
            + ", ".join(blocking)
            + " to complete first"
        )


def _design_startable_keys(view: ProjectView, design: PhaseEntryDesign) -> list[str]:
    """The design's Works this expansion would leave startable, by design key.

    Every Work this expansion creates is unstarted and in the effective set, so
    startability comes down to the incoming ``requires_completion`` the design
    asks for - the same reading :func:`_require_startable_entry` applies to one
    named entry, applied to all of them.
    """
    startable: list[str] = []
    for key in design.works:
        blocked = False
        for predecessor, successor in design.requires_completion:
            if successor != key:
                continue
            if predecessor in design.works:
                blocked = True
                break
            label = view.entity_state_label(predecessor)
            if label == "unresolvable":
                continue  # an unresolvable endpoint is refused by the registration core
            if label not in FINISHED_STATES:
                blocked = True
                break
        if not blocked:
            startable.append(key)
    return startable


def _require_unique_entry(view: ProjectView, design: PhaseEntryDesign) -> None:
    """Refuse a design whose entry Work the plan does not single out, before it writes.

    With no explicit entry the Work to start is read from the design's own
    ``planned_next``, by the rule :meth:`ProjectView.planned_next_preference`
    applies to Works that already exist. The design fixes that answer on its
    own, so an expansion that would leave several equally planned Works STOPs
    here - before the intent, the reserved IDs, the entities and the commit -
    instead of being separated afterwards by the order its Works were read in.
    """
    if design.entry is not None:
        return
    startable = _design_startable_keys(view, design)
    if len(startable) <= 1:
        return
    edges = [(a, b) for a, b in design.planned_next if b in startable]
    # A Work this expansion creates is new, so it has finished nothing and is
    # still outstanding; only an existing endpoint can be in either state.
    recommended = {
        b for a, b in edges if a not in design.works and view.entity_state_label(a) in FINISHED_STATES
    }
    pool = [key for key in startable if key in recommended] or startable
    outstanding = {
        b
        for a, b in edges
        if a in design.works or view.entity_state_label(a) not in TERMINAL_STATES + ("unresolvable",)
    }
    heads = [key for key in pool if key not in outstanding] or pool
    if len(heads) > 1:
        raise StopError(
            f"{len(heads)} Works of this design would be equally planned to start: "
            + ", ".join(sorted(heads))
            + "; the design does not say which comes first, so name the entry Work",
            code=AMBIGUOUS_CANDIDATES,
        )


def _entry_the_plan_points_to(view: ProjectView, startable: list[Entity]) -> str | None:
    """The Work this expansion leaves to start, or ``None`` when the plan is silent.

    A new expansion has already been refused if its design did not single one
    out (:func:`_require_unique_entry`), so this only reports. A resumed one may
    still be undecided, and saying so costs nothing - failing here would fail an
    expansion that is already finalized, which is what an entry decided before
    the first write exists to avoid.
    """
    if not startable:
        return None
    preferred = view.planned_next_preference(startable)
    return preferred[0].id if len(preferred) == 1 else None


def _expand_phase(store: ProjectStore, mutation: Mutation, destination: gitops.PushDestination | None, phase: Entity, phase_id: str, roadmap_id: str, design: PhaseEntryDesign) -> PhaseEntryResult:
    normal_specs = {
        key: WorkSpec(w.name, w.desired_state, phase_id=phase_id, roadmap_id=roadmap_id, related=tuple(w.related))
        for key, w in design.works.items()
    }
    normal_relations = [RelationSpec("planned_next", a, b) for a, b in design.planned_next]
    normal_relations += [RelationSpec("requires_completion", a, b) for a, b in design.requires_completion]
    def registered(stage: str, specs: dict[str, WorkSpec], relations: list[RelationSpec]) -> RegistrationResult:
        if mutation.has_stage(stage):
            return _recorded_registration(mutation, stage, list(specs))
        return register_works(mutation, stage, specs, relations)

    normal = registered("works", normal_specs, normal_relations)

    integration_spec = WorkSpec(
        design.integration.name,
        design.integration.desired_state,
        phase_id=phase_id,
        roadmap_id=roadmap_id,
        work_kind="phase_integration_check",
        related=tuple(design.integration.related),
    )
    integration = registered(
        "integration",
        {"integration": integration_spec},
        [RelationSpec("requires_completion", work_id, "integration") for work_id in normal.work_ids.values()],
    )
    integration_id = integration.work_ids["integration"]

    confirmation_id: str | None = None
    paths = list(normal.paths) + list(integration.paths)
    if design.human_confirmation is not None:
        confirmation_spec = WorkSpec(
            design.human_confirmation.name,
            design.human_confirmation.desired_state,
            phase_id=phase_id,
            roadmap_id=roadmap_id,
            work_kind="human_confirmation",
            confirmation_target=integration_id,
            related=tuple(design.human_confirmation.related),
        )
        confirmation = registered(
            "confirmation",
            {"confirmation": confirmation_spec},
            [RelationSpec("requires_completion", integration_id, "confirmation")],
        )
        confirmation_id = confirmation.work_ids["confirmation"]
        paths += list(confirmation.paths)

    # Called for its refusal, not for its value: this is the last chance to
    # STOP before :func:`_finalize` commits and pushes, so the structure this
    # expansion produced is checked here rather than after it has landed.
    _stop_on_structure(store, "phase structure check")
    head = _finalize(mutation, destination, f"chore(workline): expand phase {phase.display}", paths)

    after = ProjectView.load(store)
    startable = after.startable_works(phase_id)
    if design.entry is not None:
        # Already established before anything was written
        # (:func:`_require_startable_entry`); reaching here with an unstartable
        # entry would mean the expansion did not produce what it projected.
        entry = normal.work_ids[design.entry]
        if entry not in {w.id for w in startable}:
            raise StopError(
                f"postcheck: entry Work {design.entry} is not startable after expansion",
                code="postcheck_failed",
            )
    else:
        entry = _entry_the_plan_points_to(after, startable)
    return PhaseEntryResult(phase_id, normal.work_ids, integration_id, confirmation_id, entry, True, mutation.id, head)


# --------------------------------------------------------------------------- lifecycle

def _lifecycle(store: ProjectStore, operation: str, entity_id: str, event_type: str, precheck) -> OperationResult:
    with project_operation(store, operation, {"entity": entity_id}):
        return _record_lifecycle(store, operation, entity_id, event_type, precheck)


def _record_lifecycle(store: ProjectStore, operation: str, entity_id: str, event_type: str, precheck) -> OperationResult:
    """Record one lifecycle event; the caller holds the Project execution lock."""
    view = _stop_on_structure(store, "precheck")
    precheck(view)
    mutation, destination = _open(store, operation, {"entity": entity_id}, [entity_id])
    if not mutation.has_stage("event"):
        mutation.add_effects("event", event_effects(mutation, "event", entity_id, [event_type]))
    mutation.apply()
    head = _finalize(mutation, destination, f"chore(workline): {event_type} {entity_id}")
    return OperationResult(event_type, entity_id, mutation.id, head)


def hold_phase(store: ProjectStore, phase_id: str) -> OperationResult:
    def precheck(view: ProjectView) -> None:
        if phase_id not in view.phases:
            raise ValidationError(f"Phase unresolvable: {phase_id}")
        if view.phase_lifecycle(phase_id) != ACTIVE:
            raise SpecViolation(f"Phase {phase_id} is {view.phase_lifecycle(phase_id)}")
    return _lifecycle(store, "phase-hold", phase_id, "phase_held", precheck)


def resume_phase(store: ProjectStore, phase_id: str) -> OperationResult:
    def precheck(view: ProjectView) -> None:
        if view.phase_lifecycle(phase_id) != HELD:
            raise SpecViolation(f"Phase {phase_id} is not held")
    return _lifecycle(store, "phase-resume", phase_id, "phase_resumed", precheck)


def cancel_phase(store: ProjectStore, phase_id: str) -> OperationResult:
    def precheck(view: ProjectView) -> None:
        if phase_id not in view.phases:
            raise ValidationError(f"Phase unresolvable: {phase_id}")
        if view.phase_lifecycle(phase_id) in (CANCELLED, PLAN_EXCLUDED):
            raise SpecViolation(f"Phase {phase_id} already terminal")
    return _lifecycle(store, "phase-cancel", phase_id, "phase_cancelled", precheck)


def hold_roadmap(store: ProjectStore, roadmap_id: str) -> OperationResult:
    def precheck(view: ProjectView) -> None:
        if view.roadmap_lifecycle(roadmap_id) != ACTIVE:
            raise SpecViolation(f"Roadmap {roadmap_id} is {view.roadmap_lifecycle(roadmap_id)}")
    return _lifecycle(store, "roadmap-hold", roadmap_id, "roadmap_held", precheck)


def resume_roadmap(store: ProjectStore, roadmap_id: str) -> OperationResult:
    def precheck(view: ProjectView) -> None:
        if view.roadmap_lifecycle(roadmap_id) != HELD:
            raise SpecViolation(f"Roadmap {roadmap_id} is not held")
    return _lifecycle(store, "roadmap-resume", roadmap_id, "roadmap_resumed", precheck)


def cancel_roadmap(store: ProjectStore, roadmap_id: str) -> OperationResult:
    def precheck(view: ProjectView) -> None:
        if view.roadmap_lifecycle(roadmap_id) in (CANCELLED, ACHIEVED):
            raise SpecViolation(f"Roadmap {roadmap_id} already terminal")
    return _lifecycle(store, "roadmap-cancel", roadmap_id, "roadmap_cancelled", precheck)


def _plan_exclude(store: ProjectStore, operation: str, entity_id: str, replan: Replan, precheck) -> OperationResult:
    with project_operation(store, operation, {"entity": entity_id}):
        return _plan_exclude_locked(store, operation, entity_id, replan, precheck)


def _plan_exclude_locked(store: ProjectStore, operation: str, entity_id: str, replan: Replan, precheck) -> OperationResult:
    view = _stop_on_structure(store, "precheck")
    precheck(view)
    mutation, destination = _open(store, operation, {"entity": entity_id}, [entity_id])
    with abandon_on_stop(mutation):
        work_ids, removals, additions = plan_replan(mutation, "replan", view, replan)
        projection = projected_view(
            view,
            add_events=[(entity_id, "plan_excluded")],
            remove_relation_ids=tuple(r.id for r in removals),
            add_relations=additions,
            add_works={work_ids[k]: spec for k, spec in replan.new_works.items()},
        )
        validate_projection(projection, "plan exclusion replan")
    if not mutation.has_stage("event"):
        mutation.add_effects("event", event_effects(mutation, "event", entity_id, ["plan_excluded"]))
    mutation.apply()
    apply_replan(mutation, "replan", replan, removals, additions, work_ids)
    head = _finalize(mutation, destination, f"chore(workline): plan_excluded {entity_id}")
    return OperationResult("plan_excluded", entity_id, mutation.id, head)


def plan_exclude_phase(store: ProjectStore, phase_id: str, replan: Replan = Replan()) -> OperationResult:
    def precheck(view: ProjectView) -> None:
        if phase_id not in view.phases:
            raise ValidationError(f"Phase unresolvable: {phase_id}")
        if view.phase_state(phase_id) != UNSTARTED:
            raise SpecViolation(f"plan_excluded is only for unstarted Phases; {phase_id} is {view.phase_state(phase_id)}")
    return _plan_exclude(store, "phase-plan-exclude", phase_id, replan, precheck)


def plan_exclude_work(store: ProjectStore, work_id: str, replan: Replan = Replan()) -> OperationResult:
    """Exclude an unstarted Phase Work from the future plan (Roadmap-owned)."""
    def precheck(view: ProjectView) -> None:
        work = view.works.get(work_id)
        if work is None:
            raise ValidationError(f"Work unresolvable: {work_id}")
        if work.phase_id is None:
            raise SpecViolation("standalone Work plan exclusion is owned by START (standalone scope)")
        if view.work_state(work_id).state != UNSTARTED:
            raise SpecViolation(f"plan_excluded is only for unstarted Works; {work_id} is {view.work_state(work_id).state}")
    return _plan_exclude(store, "work-plan-exclude", work_id, replan, precheck)


# --------------------------------------------------------------------------- related maintenance

RELATED_FILE = "related"


@dataclass(frozen=True)
class RelatedMaintenanceResult:
    work_id: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    mutation_id: str | None
    head: str | None
    changed: bool
    resumed: bool = False


def _pending_for(store: ProjectStore, operation: str, identity: dict[str, Any]) -> list[dict[str, Any]]:
    invocation = json.loads(json.dumps({"operation": operation, **identity}, sort_keys=True))
    return [p for p in MutationController(store).list_pending() if p["owner"] == OWNER and p["invocation"] == invocation]


def _unstarted_roadmap_work(view: ProjectView, work_id: str) -> Entity:
    """The target of related maintenance, or STOP.

    Only an unstarted Work under an operable Roadmap is future plan; anything
    that already entered its lifecycle is not adjusted by this operation.
    """
    work = view.works.get(work_id)
    if work is None:
        raise ValidationError(f"Work unresolvable: {work_id}")
    origin = work.meta.get("origin")
    if not isinstance(origin, dict) or origin.get("type") != "roadmap":
        raise SpecViolation(
            f"{work_id} is not a Roadmap Work; standalone Work related maintenance is outside Roadmap scope"
        )
    if work.phase_id is None or work.phase_id not in view.phases:
        raise ValidationError(f"{work_id}: phase_id unresolvable")
    roadmap_id = origin.get("roadmap_id")
    if not isinstance(roadmap_id, str) or roadmap_id not in view.roadmaps:
        raise ValidationError(f"{work_id}: origin roadmap unresolvable")
    _require_active_roadmap(view, roadmap_id)
    state = view.work_state(work_id).state
    if state != UNSTARTED:
        raise SpecViolation(
            f"related maintenance is future planning and applies to unstarted Works only; {work_id} is {state}"
        )
    return work


def _related_request_key(add: tuple[RelatedSpec, ...], remove_relation_ids: tuple[str, ...]) -> str:
    """Identity of a maintenance request, derived from the request only.

    Deliberately independent of current state so the same retry resolves to
    the same pending mutation after a crash, whatever the effects already did
    to ``related.yaml``.
    """
    adds = [
        f"+{spec.type}:{spec.to}:{json.dumps(spec.condition, sort_keys=True) if spec.condition is not None else ''}"
        for spec in add
    ]
    return " | ".join(adds + [f"-{relation_id}" for relation_id in remove_relation_ids])


def _resolve_related_changes(
    view: ProjectView,
    work_id: str,
    add: tuple[RelatedSpec, ...],
    remove_relation_ids: tuple[str, ...],
) -> tuple[list[Relation], list[tuple[int, RelatedSpec]]]:
    """Resolve a request against current state.

    Only ever called when nothing of this mutation has been applied yet, so
    "the relation is not there" genuinely means the request is wrong rather
    than already done.
    """
    existing = {r.id: r for r in view.related}
    removals: list[Relation] = []
    seen_removals: set[str] = set()
    for relation_id in remove_relation_ids:
        relation = existing.get(relation_id)
        if relation is None:
            raise ValidationError(
                f"related maintenance: relation {relation_id} unresolvable; "
                "no name / target / similarity fallback is attempted"
            )
        if relation.from_id != work_id:
            raise SpecViolation(
                f"related maintenance: relation {relation_id} belongs to {relation.from_id}, not {work_id}"
            )
        if relation_id not in seen_removals:
            seen_removals.add(relation_id)
            removals.append(relation)

    # An edge that already exists (after the requested removals) is not added
    # a second time; duplicates inside one request collapse the same way.
    remaining = {
        related_edge_key(r.type, r.from_id, r.to, r.extra.get("condition"))
        for r in view.related
        if r.id not in seen_removals
    }
    effective_adds: list[tuple[int, RelatedSpec]] = []
    for index, spec in enumerate(add):
        key = related_edge_key(spec.type, work_id, spec.to, spec.condition)
        if key in remaining:
            continue
        remaining.add(key)
        effective_adds.append((index, spec))
    return removals, effective_adds


def _related_snapshot(view: ProjectView, work_id: str) -> dict[str, Any]:
    work = view.works[work_id]
    return {
        "body": work.body,
        "meta": json.dumps(work.meta, sort_keys=True, ensure_ascii=False),
        "state": view.work_state(work_id).state,
        "events": [e.to_record() for e in view.events],
        "roadmap_relations": [r.to_record() for r in view.roadmap_relations],
        "related": {r.id: r.to_record() for r in view.related},
    }


def maintain_work_related(
    store: ProjectStore,
    work_id: str,
    *,
    add: tuple[RelatedSpec, ...] = (),
    remove_relation_ids: tuple[str, ...] = (),
    invocation_key: str | None = None,
) -> RelatedMaintenanceResult:
    """Maintain the related relations of an existing, unstarted Roadmap Work.

    Roadmap already owns the meaning of ``WorkDesign.related`` at Phase entry,
    so it also owns later corrections to that plan. CREATE stays the
    registration core and never becomes the owner of an existing Work's
    meaning. ``roadmap.yaml`` future-plan relations already had a maintenance
    path; this closes the same gap for ``related.yaml``, which previously could
    only be corrected by editing the file by hand or by discarding and
    recreating the Work.

    Adds reuse the CREATE payload type and validation. Removals accept
    relation IDs that actually exist and belong to this Work; anything else
    STOPs rather than being guessed. Requesting an edge that already exists is
    a no-op, and an operation with no effective change makes no commit, no
    push and no relation ID. The Work body, ``origin``, ``phase_id``,
    lifecycle state, events and ``roadmap.yaml`` are never touched: this is a
    plan correction, not a lifecycle event.
    """
    if not add and not remove_relation_ids:
        raise ValidationError("related maintenance needs at least one add or remove")
    with project_operation(store, "work-related-maintenance", {"work_id": work_id}):
        return _maintain_work_related_locked(store, work_id, add, remove_relation_ids, invocation_key)


def _maintain_work_related_locked(
    store: ProjectStore,
    work_id: str,
    add: tuple[RelatedSpec, ...],
    remove_relation_ids: tuple[str, ...],
    invocation_key: str | None,
) -> RelatedMaintenanceResult:
    # Every read below, the no-op decision included, sees the state current
    # under the Project execution lock.
    view = _stop_on_structure(store, "precheck")
    work = _unstarted_roadmap_work(view, work_id)
    validate_related_specs(add, f"related maintenance {work_id}")

    # What the request asks for, folded to the form the operation acts on, and
    # then its identity - both derived from the request alone, so they are known
    # before any current-state resolution. That ordering is what makes resume
    # correct: a mutation whose effects are already durably recorded must
    # continue from those records, not be re-derived from a state those very
    # effects changed.
    unfolded_key = invocation_key or _related_request_key(add, remove_relation_ids)
    add, remove_relation_ids = _collapse_related_request(work_id, add, remove_relation_ids)
    operation = "work-related-maintenance"
    slot = {"work_id": work_id, "key": invocation_key or _related_request_key(add, remove_relation_ids)}
    request = related_request_identity(add, remove_relation_ids)
    # Before the no-op decision below, which can return without ever opening a
    # mutation: a retry that decided something else must be refused, not
    # reported as nothing to do while the first request stays unfinished.
    #
    # A default label is derived from the request, so folding this request's
    # repeats changes it. A record written before this operation folded - and so
    # before it recorded what it had decided - sits under the unfolded label, and
    # is looked for there as well; otherwise the one retry that would have found
    # it reports a no-op and leaves it pending unnoticed. The two lookups ask for
    # different labels, so no record is caught twice, and nothing this operation
    # writes can sit under the unfolded one.
    pending = pending_for_slot(store, OWNER, {"operation": operation, **slot})
    if unfolded_key != slot["key"]:
        pending += pending_for_slot(store, OWNER, {"operation": operation, "work_id": work_id, "key": unfolded_key})
    require_same_request(pending, request, f"related maintenance of {work_id}")
    identity = {**slot, "request": request}
    before = _related_snapshot(view, work_id)
    no_change = RelatedMaintenanceResult(work_id, (), (), None, gitcmd.head_commit(store.root), changed=False)

    if not _pending_for(store, operation, identity):
        # Fresh request: resolve against current state (this is where an
        # unresolvable or foreign relation ID is refused) and detect a no-op
        # before any mutation exists.
        removals, effective_adds = _resolve_related_changes(view, work_id, add, remove_relation_ids)
        if not removals and not effective_adds:
            return no_change

    mutation, destination = _open(store, operation, identity, [work_id])
    with abandon_on_stop(mutation):
        if not mutation.has_stage("related"):
            # Either a new mutation, or a pending one that crashed before
            # recording its effects; in both cases nothing has been applied yet,
            # so current state is still the right thing to resolve against.
            removals, effective_adds = _resolve_related_changes(view, work_id, add, remove_relation_ids)
            if not removals and not effective_adds:
                mutation.abandon()
                return no_change
            additions = [
                Relation(
                    mutation.reserve_id(f"related:add:{index}", "relation"),
                    spec.type,
                    work_id,
                    spec.to,
                    {"condition": spec.condition} if spec.condition is not None else {},
                )
                for index, spec in effective_adds
            ]
            validate_projection(
                projected_view(
                    view,
                    remove_related_ids=tuple(r.id for r in removals),
                    add_related=additions,
                ),
                "related maintenance",
            )
            mutation.add_effects(
                "related",
                [Effect.remove_relation(RELATED_FILE, relation) for relation in removals]
                + [Effect.add_relation(RELATED_FILE, relation) for relation in additions],
            )
    # Recorded effects are the authority from here on. The Mutation Controller
    # classifies each one as unapplied / applied_matching / applied_mismatch, so
    # an already-removed relation is "matching", never "unresolvable".
    mutation.apply()

    recorded = mutation.stage_effects("related")
    added_ids = tuple(e["payload"]["record"]["id"] for e in recorded if e["kind"] == "add_relation")
    removed_ids = tuple(e["payload"]["record"]["id"] for e in recorded if e["kind"] == "remove_relation")
    _related_postcheck(store, work_id, before, added_ids, removed_ids)

    head = _finalize(mutation, destination, f"chore(workline): update related refs {work.display}")
    return RelatedMaintenanceResult(
        work_id, added_ids, removed_ids, mutation.id, head, changed=True, resumed=mutation.resumed
    )


def _related_postcheck(
    store: ProjectStore,
    work_id: str,
    before: dict[str, Any],
    added_ids: tuple[str, ...],
    removed_ids: tuple[str, ...],
) -> None:
    after_view = _stop_on_structure(store, "postcheck")
    after = _related_snapshot(after_view, work_id)

    for field_name in ("body", "meta", "state", "events", "roadmap_relations"):
        if after[field_name] != before[field_name]:
            raise StopError(
                f"postcheck: related maintenance changed {field_name} of {work_id}", code="postcheck_failed"
            )

    expected = {rid: rec for rid, rec in before["related"].items() if rid not in removed_ids}
    for relation_id in added_ids:
        relation = next((r for r in after_view.related if r.id == relation_id), None)
        if relation is None:
            raise StopError(f"postcheck: added relation {relation_id} missing", code="postcheck_failed")
        if relation.from_id != work_id:
            raise StopError(f"postcheck: added relation {relation_id} is not from {work_id}", code="postcheck_failed")
        expected[relation_id] = relation.to_record()
    if after["related"] != expected:
        raise StopError(
            "postcheck: related.yaml holds changes beyond the requested add / remove", code="postcheck_failed"
        )


# --------------------------------------------------------------------------- achievement

@dataclass(frozen=True)
class AchievementResult:
    status: str  # not_ready | achieved | human_confirmation_required | not_achieved | desired_state_change_required
    roadmap_id: str
    mutation_id: str | None = None
    head: str | None = None
    detail: str = ""


JUDGEMENTS = ("achieved", "human_confirmation", "not_achieved", "desired_state_change")


def evaluate_achievement(store: ProjectStore, roadmap_id: str, judgement: str, detail: str = "") -> AchievementResult:
    """Explicit Roadmap achievement check.

    All active Phases complete is a precondition, never the conclusion. The
    ``judgement`` is the explicit evaluation of the Roadmap's desired state.
    Only ``achieved`` records ``roadmap_achieved``, and recording it is a write:
    its precondition is evaluated on the state current under the Project
    execution lock, never on a read taken before the lock. The other judgements
    only report and take no lock.
    """
    if judgement not in JUDGEMENTS:
        raise ValidationError(f"unknown judgement: {judgement}")
    if judgement != "achieved":
        view = _stop_on_structure(store, "precheck")
        _require_active_roadmap(view, roadmap_id)
        if not view.all_active_phases_complete(roadmap_id):
            return AchievementResult("not_ready", roadmap_id, detail=diagnose_no_candidate(store, roadmap_id))
        if judgement == "human_confirmation":
            return AchievementResult("human_confirmation_required", roadmap_id, detail=detail)
        if judgement == "not_achieved":
            return AchievementResult("not_achieved", roadmap_id, detail=detail or "add Phases / replan without changing the desired state")
        return AchievementResult("desired_state_change_required", roadmap_id, detail=detail)

    with project_operation(store, "roadmap-achievement", {"entity": roadmap_id}):
        view = _stop_on_structure(store, "precheck")
        _require_active_roadmap(view, roadmap_id)
        if not view.all_active_phases_complete(roadmap_id):
            return AchievementResult("not_ready", roadmap_id, detail=diagnose_no_candidate(store, roadmap_id))

        def still_achievable(current: ProjectView) -> None:
            _require_active_roadmap(current, roadmap_id)
            if not current.all_active_phases_complete(roadmap_id):
                raise StopError(f"Roadmap {roadmap_id} is no longer ready for achievement", code="achievement_not_ready")

        result = _record_lifecycle(store, "roadmap-achievement", roadmap_id, "roadmap_achieved", still_achievable)
    return AchievementResult("achieved", roadmap_id, result.mutation_id, result.head, detail)


# --------------------------------------------------------------------------- handoff

def handoff(store: ProjectStore, phase_id: str, executor, entry_work_id: str | None = None):
    """Hand a Phase to START (mode=outer). START returns at Phase completion or stop."""
    from .start import start

    if entry_work_id is None:
        view = _stop_on_structure(store, "handoff")
        startable = view.startable_works(phase_id)
        if not startable:
            raise StopError(f"Phase {phase_id} has no startable Work", code="no_startable_work")
        # Decided before START is called, so an ambiguous Phase hands nothing over.
        entry_work_id = view.choose_startable(startable, "Work").id
    return start(store, entry_work_id, "outer", executor)


__all__ = [
    "RoadmapPlan", "RoadmapResult", "WorkDesign", "PhaseEntryDesign", "PhaseEntryResult", "OperationResult",
    "PhaseAdditionResult", "AchievementResult", "Replan", "create_roadmap", "add_phases", "startable_phases",
    "select_phase", "diagnose_no_candidate",
    "enter_phase", "hold_phase", "resume_phase", "cancel_phase", "hold_roadmap", "resume_roadmap", "cancel_roadmap",
    "plan_exclude_phase", "plan_exclude_work", "evaluate_achievement", "handoff",
]
