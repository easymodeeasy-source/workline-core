"""Review-v1 planning (P2): the RoadmapPlan and PhaseEntryDesign Review gates of the Roadmap operation.

Roadmap-owned (``skills/roadmap``). An explicit ``review=PlanningReview(...)``
opts one ``create_roadmap`` / ``enter_phase`` invocation into this path; with
``review=None`` nothing here is reached and the live Roadmap path runs
unchanged. Review stays a subordinate gate: it contributes record shapes,
validation and proofs (``workline.review``), while the Roadmap operation owns
the planning mutation, the generation mutations it starts, the registration, the
commits and the push.

```text
entry      argument / platform / Git version -> live checks -> request identity
           -> canonical-input preflight -> same request and markers -> remaining
           live checks -> recovery discovery (no pending mutation only) -> _open
setup      recovered binding | freeze on the committed basis of HEAD
generations G1 accept -> G2 settle -> G3 seal [-> G4 invalidate + Supersession]
use check  Receipt valid and current on HEAD; use_check_head noted
registration  the live stages, fed from W (the canonical Candidate), display base check before each
Kp         pre-Kp currency proof, base-exact registration commit, C-2(Kp)
Km         Planning Consumption v2, metadata commit, C-2(Km)
publish    publication barrier, push of exact Km
```

Nothing here derives lifecycle: the Candidate, W, the expected physical
projection and every committed view are read by the gate and its proofs only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
from pathlib import Path
from typing import Any, Callable

from . import gitcmd, gitops
from .committed_view import CommittedReadError, committed_view, materialized
from .create import RelatedSpec, WorkSpec, _allocated_displays, _registration_effects, _resolve_roadmap_relations
from .durable import durable_write_text
from .errors import ReconcileRequired, StopError, ValidationError
from .ids import is_valid_id
from .mutation import (
    MATCHING,
    MISMATCH,
    UNAPPLIED,
    Effect,
    Mutation,
    MutationController,
    WriteScope,
    abandon_on_stop,
    effect_path,
    planned_write,
)
from .phase_create import PhaseRelationSpec, PhaseSpec, phase_registration_effects, resolve_phase_relations
from .review import checkout, committed, gate, paths as review_paths, planning, records, serialize
from .review import fsafe
from .review.planning import (
    PlanningReview,
    PlanningReviewFinding,
    PlanningReviewReport,
    PlanningReviewTask,
)
from .review.projections import Projection, reviewed_artifact
from .review.store import ReviewStore
from .state import ProjectView
from .store import (
    CONDITIONAL_RELATED_TYPES,
    PHASE_DESIRED_HEADING,
    ROADMAP_BACKGROUND_HEADING,
    ROADMAP_DESIRED_HEADING,
    ROADMAP_OUT_OF_SCOPE_HEADING,
    ROADMAP_SCOPE_HEADING,
    WORK_DESIRED_HEADING,
    WORKLINE_DIR,
    ProjectStore,
)
from .validate import validate_condition, validate_structure

__all__ = [
    "PlanningReview",
    "PlanningReviewFinding",
    "PlanningReviewReport",
    "PlanningReviewTask",
    "ReviewedPlanningResult",
]

OWNER = "roadmap"

ROADMAP_RELATIONS = f"{WORKLINE_DIR}/relations/roadmap.yaml"
RELATED_RELATIONS = f"{WORKLINE_DIR}/relations/related.yaml"

#: The planning mutation's own stages after the live registration stages.
STAGE_KP = "review-registration-commit"
STAGE_CONSUMPTION = "review-consumption"
STAGE_KM = "review-consumption-commit"
STAGE_PUBLICATION = "review-publication"
#: A generation mutation's stages.
STAGE_GENERATION = "review-generation"
STAGE_GENERATION_COMMIT = "review-generation-commit"

ROADMAP_STAGES = ("roadmap", "phases")
PHASE_ENTRY_STAGES = ("works", "integration", "confirmation")

NOTE_DISCOVERY = "recovery_discovery"
NOTE_RECOVERY_BINDING = "recovery_binding"
NOTE_BINDING = "review_binding"
NOTE_USE_CHECK_HEAD = "use_check_head"
NOTE_PUBLICATION_PROOF = "publication_proof"

STATUS_REGISTERED = "registered"
STATUS_NOT_AUTHORIZED = "not_authorized"
STATUS_STALE = "stale"


# --------------------------------------------------------------------------- result

@dataclass(frozen=True)
class ReviewedPlanningResult:
    """What a review-v1 planning invocation ended in (``skills/roadmap``: terminal outcomes)."""

    status: str
    operation: str
    mutation_id: str
    review_run_id: str
    receipt_id: str | None
    consumption_id: str | None
    registration: Any
    findings: tuple[PlanningReviewFinding, ...]
    detail: str


def _reconcile(message: str, reason: str) -> ReconcileRequired:
    return ReconcileRequired(f"{message}: reconcile required", reason=reason)


# --------------------------------------------------------------------------- entry gate (before the lock)

def require_entry_gate(review: object) -> PlanningReview:
    """The opt-in's own applicability, before the lock and before any Project state is read.

    ``review_contract_invalid`` for an invalid argument; ``review_create_unsupported``
    where an immutable Review create cannot be kept inside the Project;
    ``review_git_unsupported`` on a Git older than ``P2_REVIEW_GIT_MIN`` or of
    unknown version. Nothing is read or written, and a pending planning mutation
    is left exactly as it is.
    """
    checked = planning.validate_planning_review(review)
    if not fsafe.immutable_create_supported():
        raise StopError(
            "review-v1 planning writes immutable Review records, which this platform cannot keep inside the "
            "Project; nothing was begun (the legacy path is unaffected)",
            code="review_create_unsupported",
        )
    version = gitcmd.running_git_version()
    if not gitcmd.version_meets(version, gitcmd.P2_REVIEW_GIT_MIN):
        found = "of unknown version" if version is None else gitcmd.version_text(version)
        raise StopError(
            f"the running Git is {found}; review-v1 planning needs P2_REVIEW_GIT_MIN "
            f"({gitcmd.version_text(gitcmd.P2_REVIEW_GIT_MIN)}) or newer; nothing was begun",
            code="review_git_unsupported",
        )
    return checked


# --------------------------------------------------------------------------- canonical-input preflight

def _unrepresentable(described: str, detail: str) -> ValidationError:
    return ValidationError(
        f"{described} cannot be canonicalized ({detail}): the caller input cannot be carried by the canonical "
        "form, so nothing was begun",
        code="review_candidate_unrepresentable",
    )


def _first_noncanonical(value: Any, where: str) -> str | None:
    """Where in ``value`` the canonical form would change or refuse something, for the refusal's detail."""
    if isinstance(value, tuple):
        return f"{where} is a tuple, which the canonical form would make a list"
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                return f"{where} has a {type(key).__name__} mapping key {key!r}"
            found = _first_noncanonical(item, f"{where}.{key}")
            if found:
                return found
        return None
    if isinstance(value, list):
        for index, item in enumerate(value):
            found = _first_noncanonical(item, f"{where}[{index}]")
            if found:
                return found
        return None
    if value is None or isinstance(value, (str, bool, int)):
        return None
    return f"{where} is a {type(value).__name__}: {value!r}"


def require_canonical_input(identity: dict[str, Any], described: str) -> None:
    """The request identity ``identity`` is exact P1 canonical data apart from mapping key order.

    Uses the P1 serializer alone: ``canonical_data`` succeeds and equals the
    value under Python equality, the canonical bytes of a record holding it
    render, and they read back as the same data. Any failure is
    ``review_candidate_unrepresentable``, never a serializer exception.
    """
    try:
        data = serialize.canonical_data(identity)
    except ValidationError as exc:
        raise _unrepresentable(described, str(exc)) from exc
    if data != identity:
        raise _unrepresentable(described, _first_noncanonical(identity, "request") or "canonicalization changes it")
    holder = {"request": identity}
    try:
        serialize.canonical_bytes(holder)
        roundtrips = serialize.canonical_roundtrips(holder)
    except Exception as exc:  # the P1 renderer refuses: empty key, nested sequence, unencodable text
        raise _unrepresentable(described, f"{type(exc).__name__}: {exc}") from exc
    if not roundtrips:
        raise _unrepresentable(described, "its canonical text does not read back as the same data")


def preflight_roadmap_request(request: dict[str, Any]) -> None:
    """The canonical-input preflight of a review-v1 Roadmap creation (before ``_open``)."""
    require_canonical_input(request, "the RoadmapPlan request")


def phase_entry_continuation(store: ProjectStore, phase_id: str, pending: list[dict[str, Any]]) -> bool:
    """Whether a review-v1 Phase entry of this slot continues a Run the Project already accepted (§5.8).

    The boundary of §5.8, read from canonical state and from nothing a caller
    supplies: the slot holds a pending review-v1 Phase-entry planning mutation,
    and the Run that mutation holds - its reservation under the Run key, or the
    Run its ``recovery_binding`` note names - has a canonical generation 1.

    It is a read-only predicate. It reserves nothing, writes nothing, evaluates
    no caller value, begins, repairs or classifies no Run, and runs no recovery
    discovery. Anything it cannot prove is no continuation, and the live
    admission checks of §5.6 branch A then decide the call.
    """
    from . import roadmap as rm

    key = gate.review_run_key(planning.KIND_PHASE_ENTRY, phase_id)
    for record in pending:
        invocation = record.get("invocation") or {}
        if rm.planning_marker(invocation, planning.OPERATION_PHASE_ENTRY) not in ("review", "recovery"):
            continue
        run_id = (record.get("reserved_ids") or {}).get(key)
        if not run_id:
            binding = (record.get("notes") or {}).get(NOTE_RECOVERY_BINDING)
            run_id = binding.get("review_run_id") if isinstance(binding, dict) else None
        if isinstance(run_id, str) and run_id and _canonical_generation_1(store, run_id):
            return True
    return False


def _canonical_generation_1(store: ProjectStore, review_run_id: str) -> bool:
    """Whether the Run's generation 1 is canonical: committed at HEAD and reading back with its own material.

    "Reading back" is the P1 reader's, and "committed" is the persistence proof
    the rest of P2 uses (``gate.require_persisted`` and the blob check, §12.3):
    the gate, its Candidate snapshot and its task input are at HEAD as
    ``100644`` blobs of exactly the canonical bytes. A generation 1 that is
    recorded, applied or committed but not readable proves no accepted Run, so
    it is no boundary; nothing here raises.
    """
    try:
        review = ReviewStore(store)
        chain = review.gate_chain(review_run_id)
        if chain is None or not chain.generations or chain.generations[0].generation != 1:
            return False
        first = chain.generations[0]
        task_id = str(first.accepted_tasks[0]["task_id"])
        review.read_task_input(task_id)
        review.read_candidate_snapshot(first.candidate_hash)
        wanted = [
            review_paths.gate_rel(review_run_id, 1),
            review_paths.candidate_snapshot_rel(first.candidate_hash),
            review_paths.task_input_rel(task_id),
        ]
        require_committed_records(store, {relative: (review.read_bytes(relative) or b"") for relative in wanted})
    except (StopError, ValidationError, ReconcileRequired, OSError, LookupError, IndexError, TypeError, ValueError):
        return False
    return True


def preflight_phase_entry_request(design: Any, identity: dict[str, Any]) -> None:
    """The canonical-input preflight of a review-v1 Phase entry (before ``_open``).

    Each condition of a conditional Related type first goes through the live
    ``validate_condition``, with its live refusal unchanged; then the design
    identity through the P1 serializer.
    """
    works: list[tuple[str, Any]] = list(design.works.items()) + [("integration", design.integration)]
    if design.human_confirmation is not None:
        works.append(("confirmation", design.human_confirmation))
    for key, work in works:
        for related in work.related:
            if related.type in CONDITIONAL_RELATED_TYPES:
                message = validate_condition(related.condition)
                if message:
                    raise ValidationError(f"work {key}: {message}")
    require_canonical_input(identity, "the PhaseEntryDesign request")


# --------------------------------------------------------------------------- the Candidate's content

def roadmap_candidate_content(request: dict[str, Any], reserved: dict[str, str]) -> dict[str, Any]:
    """The RoadmapPlan content, from the request identity and the reserved IDs (``skills/review``)."""
    roadmap_id = reserved["roadmap"]
    phase_ids = {phase["key"]: reserved[f"phases:phase:{phase['key']}"] for phase in request["phases"]}
    return {
        "roadmap": {
            "id": roadmap_id,
            "name": request["name"],
            "background": request["background"],
            "desired_state": request["desired_state"],
            # null for a caller's None or "", else the stripped text: the request identity records exactly that,
            # so a blank caller value is "" and the writer keeps its empty section, as legacy does
            "scope": request["scope"],
            "out_of_scope": request["out_of_scope"],
        },
        "phases": [
            {"key": phase["key"], "id": phase_ids[phase["key"]], "name": phase["name"], "desired_state": phase["desired_state"]}
            for phase in request["phases"]
        ],
        "relations": [
            {
                "id": reserved[f"phases:rel:{index}"],
                "type": relation["type"],
                "from": phase_ids.get(relation["from"], relation["from"]),
                "to": phase_ids.get(relation["to"], relation["to"]),
            }
            for index, relation in enumerate(request["relations"])
        ],
    }


def _related_content(related: list[dict[str, Any]], reserved: dict[str, str], prefix: str) -> list[dict[str, Any]]:
    return [
        {
            "id": reserved[f"{prefix}:{index}"],
            "type": item["type"],
            "to": item["to"],
            "condition": None if item.get("condition") is None else serialize.canonical_data(item["condition"]),
        }
        for index, item in enumerate(related)
    ]


def phase_entry_candidate_content(
    design: dict[str, Any], phase_id: str, roadmap_id: str, reserved: dict[str, str]
) -> dict[str, Any]:
    """The PhaseEntryDesign content, from the design identity and the reserved IDs, without ``canonical_first_work``."""
    work_ids = {work["key"]: reserved[f"works:work:{work['key']}"] for work in design["works"]}
    works = [
        {
            "key": work["key"],
            "id": work_ids[work["key"]],
            "name": work["name"],
            "desired_state": work["desired_state"],
            "work_kind": None,
            "related": _related_content(work["related"], reserved, f"works:related:{work['key']}"),
        }
        for work in design["works"]
    ]
    integration_id = reserved["integration:work:integration"]
    integration = {
        "id": integration_id,
        "name": design["integration"]["name"],
        "desired_state": design["integration"]["desired_state"],
        "related": _related_content(design["integration"]["related"], reserved, "integration:related:integration"),
        "work_kind": "phase_integration_check",
    }
    confirmation = None
    if design["confirmation"] is not None:
        confirmation = {
            "id": reserved["confirmation:work:confirmation"],
            "name": design["confirmation"]["name"],
            "desired_state": design["confirmation"]["desired_state"],
            "related": _related_content(design["confirmation"]["related"], reserved, "confirmation:related:confirmation"),
            "work_kind": "human_confirmation",
            "confirmation_target": integration_id,
        }
    relations: list[dict[str, Any]] = []
    declared = [("planned_next", pair) for pair in design["planned_next"]]
    declared += [("requires_completion", pair) for pair in design["requires_completion"]]
    for index, (relation_type, pair) in enumerate(declared):
        relations.append({
            "id": reserved[f"works:rel:{index}"],
            "type": relation_type,
            "from": work_ids.get(pair["from"], pair["from"]),
            "to": work_ids.get(pair["to"], pair["to"]),
        })
    for index, work in enumerate(works):
        relations.append({
            "id": reserved[f"integration:rel:{index}"], "type": "requires_completion",
            "from": work["id"], "to": integration_id,
        })
    if confirmation is not None:
        relations.append({
            "id": reserved["confirmation:rel:0"], "type": "requires_completion",
            "from": integration_id, "to": confirmation["id"],
        })
    return {
        "phase_id": phase_id,
        "roadmap_id": roadmap_id,
        "works": works,
        "integration": integration,
        "confirmation": confirmation,
        "relations": relations,
    }


# --------------------------------------------------------------------------- reservation keys

def roadmap_domain_keys(request: dict[str, Any]) -> list[tuple[str, str]]:
    """``(key, kind)`` of every domain ID a Roadmap creation reserves, in the order the live code reserves them."""
    keys = [("roadmap", "roadmap")]
    keys += [(f"phases:phase:{phase['key']}", "phase") for phase in request["phases"]]
    keys += [(f"phases:rel:{index}", "relation") for index in range(len(request["relations"]))]
    return keys


def phase_entry_domain_keys(design: dict[str, Any]) -> list[tuple[str, str]]:
    """``(key, kind)`` of every domain ID a Phase entry reserves, under the unchanged ``register_works`` keys."""
    keys = [(f"works:work:{work['key']}", "work") for work in design["works"]]
    relation_count = len(design["planned_next"]) + len(design["requires_completion"])
    keys += [(f"works:rel:{index}", "relation") for index in range(relation_count)]
    for work in design["works"]:
        keys += [(f"works:related:{work['key']}:{index}", "relation") for index in range(len(work["related"]))]
    keys.append(("integration:work:integration", "work"))
    keys += [(f"integration:rel:{index}", "relation") for index in range(len(design["works"]))]
    keys += [
        (f"integration:related:integration:{index}", "relation") for index in range(len(design["integration"]["related"]))
    ]
    if design["confirmation"] is not None:
        keys.append(("confirmation:work:confirmation", "work"))
        keys.append(("confirmation:rel:0", "relation"))
        keys += [
            (f"confirmation:related:confirmation:{index}", "relation")
            for index in range(len(design["confirmation"]["related"]))
        ]
    return keys


def reservations_of(material: dict[str, Any]) -> list[tuple[str, str, str]]:
    """``(key, id, kind)`` of every domain ID a Candidate holds, under the keys the unchanged registration reserves."""
    content = planning.candidate_content(material)
    found: list[tuple[str, str, str]] = []
    if material["review_kind"] == planning.KIND_ROADMAP:
        found.append(("roadmap", content["roadmap"]["id"], "roadmap"))
        found += [(f"phases:phase:{phase['key']}", phase["id"], "phase") for phase in content["phases"]]
        found += [(f"phases:rel:{index}", relation["id"], "relation") for index, relation in enumerate(content["relations"])]
        return found
    works = content["works"]
    confirmation = content["confirmation"]
    generated = len(works) + (1 if confirmation is not None else 0)
    declared = content["relations"][: len(content["relations"]) - generated]
    found += [(f"works:work:{work['key']}", work["id"], "work") for work in works]
    found += [(f"works:rel:{index}", relation["id"], "relation") for index, relation in enumerate(declared)]
    for work in works:
        found += [(f"works:related:{work['key']}:{index}", item["id"], "relation") for index, item in enumerate(work["related"])]
    integration = content["integration"]
    found.append(("integration:work:integration", integration["id"], "work"))
    tail = content["relations"][len(declared):]
    found += [(f"integration:rel:{index}", relation["id"], "relation") for index, relation in enumerate(tail[: len(works)])]
    found += [
        (f"integration:related:integration:{index}", item["id"], "relation") for index, item in enumerate(integration["related"])
    ]
    if confirmation is not None:
        found.append(("confirmation:work:confirmation", confirmation["id"], "work"))
        found.append(("confirmation:rel:0", tail[len(works)]["id"], "relation"))
        found += [
            (f"confirmation:related:confirmation:{index}", item["id"], "relation")
            for index, item in enumerate(confirmation["related"])
        ]
    return found


# --------------------------------------------------------------------------- declared base

class _NotInBase(Exception):
    """An entity the declared base names that this view does not hold."""

    def __init__(self, entity_id: str) -> None:
        super().__init__(entity_id)
        self.entity_id = entity_id


def _candidate_entity_ids(content: dict[str, Any]) -> set[str]:
    if "roadmap" in content:
        return {content["roadmap"]["id"]} | {phase["id"] for phase in content["phases"]}
    ids = {work["id"] for work in content["works"]} | {content["integration"]["id"]}
    if content["confirmation"] is not None:
        ids.add(content["confirmation"]["id"])
    return ids


def declared_base(view: ProjectView, content: dict[str, Any]) -> dict[str, Any]:
    """The declared base of a Candidate's content on ``view``: the facts the reviewed plan rests on.

    Raises :class:`_NotInBase` for an entity it names that ``view`` does not hold.
    """
    own = _candidate_entity_ids(content)
    if "roadmap" in content:
        existing = sorted({
            endpoint for relation in content["relations"] for endpoint in (relation["from"], relation["to"])
            if endpoint not in own
        })
        phases = []
        for phase_id in existing:
            entity = view.phases.get(phase_id)
            if entity is None:
                raise _NotInBase(phase_id)
            phases.append({
                "id": phase_id, "roadmap_id": entity.roadmap_id,
                "lifecycle": view.phase_lifecycle(phase_id), "state": view.phase_state(phase_id),
            })
        return {"existing_phases": phases}
    phase_id, roadmap_id = content["phase_id"], content["roadmap_id"]
    phase = view.phases.get(phase_id)
    if phase is None:
        raise _NotInBase(phase_id)
    if roadmap_id not in view.roadmaps:
        raise _NotInBase(roadmap_id)
    works = content["works"]
    generated = len(works) + (1 if content["confirmation"] is not None else 0)
    declared = content["relations"][: len(content["relations"]) - generated]
    existing = sorted({
        endpoint for relation in declared for endpoint in (relation["from"], relation["to"]) if endpoint not in own
    })
    existing_works = []
    for work_id in existing:
        entity = view.works.get(work_id)
        if entity is None:
            raise _NotInBase(work_id)
        existing_works.append({"id": work_id, "phase_id": entity.phase_id, "state": view.work_state(work_id).state})
    dependencies = sorted(view.relations_to(phase_id, "requires_completion"), key=lambda relation: relation.id)
    return {
        "phase": {
            "id": phase_id, "roadmap_id": phase.roadmap_id,
            "lifecycle": view.phase_lifecycle(phase_id), "state": view.phase_state(phase_id),
        },
        "roadmap": {"id": roadmap_id, "lifecycle": view.roadmap_lifecycle(roadmap_id)},
        "phase_dependencies": [
            {"relation_id": relation.id, "from": relation.from_id, "from_state": view.entity_state_label(relation.from_id)}
            for relation in dependencies
        ],
        "existing_works": existing_works,
    }


# --------------------------------------------------------------------------- R9: the canonical first Work

@dataclass(frozen=True)
class Selection:
    """The R9 selection on a view: ``none``, ``unique`` (``work_id``) or ``ambiguous``."""

    kind: str
    work_id: str | None = None
    ties: tuple[str, ...] = ()


def r9_selection(view: ProjectView, phase_id: str) -> Selection:
    """``startable_works`` + ``planned_next_preference`` of the Phase on ``view`` (Roadmap-owned, ``skills/roadmap``)."""
    startable = view.startable_works(phase_id)
    if not startable:
        return Selection("none")
    preferred = view.planned_next_preference(startable)
    if len(preferred) == 1:
        return Selection("unique", preferred[0].id)
    return Selection("ambiguous", None, tuple(sorted(work.id for work in preferred)))


def first_work_of(selection: Selection, content: dict[str, Any], entry_key: str | None) -> dict[str, str] | None:
    """The canonical first Work the selection gives for a design with ``entry_key``, or the R9 refusal."""
    keys = {work["id"]: work["key"] for work in content["works"]}
    if selection.kind == "unique":
        key = keys.get(selection.work_id)
        if key is None:
            raise StopError(
                f"the canonical selection {selection.work_id} is not a Work of this design", code="review_entry_not_canonical"
            )
        if entry_key is not None and entry_key != key:
            raise StopError(
                f"entry Work {entry_key} is not the canonical first Work: the committed basis selects {key} "
                f"({selection.work_id})",
                code="review_entry_not_canonical",
            )
        return {"key": key, "id": selection.work_id}
    if selection.kind == "ambiguous":
        tied = ", ".join(sorted(keys.get(work_id, work_id) for work_id in selection.ties))
        if entry_key is not None:
            raise StopError(
                f"entry Work {entry_key} is not the canonical first Work: the committed basis leaves {tied} equally "
                "planned, and a review-v1 design must select its first Work canonically",
                code="review_entry_ambiguous",
            )
        raise StopError(
            f"{len(selection.ties)} Works of this design would be equally planned to start: {tied}; the design does "
            "not say which comes first",
            code="ambiguous_startable_candidates",
        )
    return None


# --------------------------------------------------------------------------- W: the canonical planning writer input

class WriterInputUnavailable(ValidationError):
    """A Candidate record that does not give the exact writer inputs W is built from."""

    def __init__(self, message: str) -> None:
        super().__init__(f"the writer input cannot be computed from the Candidate: {message}", code="review_record_invalid")


@dataclass(frozen=True)
class RoadmapWriterInput:
    """W of a RoadmapPlan: the stage inputs and the reserved IDs the unchanged writer receives."""

    roadmap_id: str
    stages: Any  # roadmap.RoadmapStages
    phase_ids: dict[str, str]
    relation_ids: dict[int, str]
    reservations: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class PhaseEntryWriterInput:
    """W of a PhaseEntryDesign: the three stages' inputs and the reserved IDs the unchanged writer receives."""

    phase_id: str
    roadmap_id: str
    stages: Any  # roadmap.PhaseEntryStages
    work_ids: dict[str, str]
    relation_ids: dict[int, str]
    related_ids: dict[tuple[str, int], str]
    integration_id: str
    integration_relation_ids: dict[int, str]
    integration_related_ids: dict[tuple[str, int], str]
    confirmation_id: str | None
    confirmation_relation_ids: dict[int, str]
    confirmation_related_ids: dict[tuple[str, int], str]
    reservations: tuple[tuple[str, str, str], ...]


def writer_input(material: dict[str, Any]) -> RoadmapWriterInput | PhaseEntryWriterInput:
    """W: the exact inputs the live writer helpers receive, computed from the canonical Candidate record alone.

    Mappings stay in the Candidate's (canonical) key order, sequences in the
    Candidate's order, every entry kept; ``canonical_first_work`` is not read.
    The same stage-input derivation the legacy path calls turns the rebuilt plan
    or design into stage inputs. W renders nothing.
    """
    from . import roadmap as rm

    try:
        planning.require_planning_candidate(material, "the Candidate")
        content = planning.candidate_content(material)
        reservations = tuple(reservations_of(material))
        if material["review_kind"] == planning.KIND_ROADMAP:
            roadmap = content["roadmap"]
            phase_ids = {phase["key"]: phase["id"] for phase in content["phases"]}
            key_of = {phase_id: key for key, phase_id in phase_ids.items()}
            stages = rm.RoadmapStages(
                roadmap["name"],
                tuple(rm.roadmap_file_sections(
                    roadmap["background"], roadmap["desired_state"], roadmap["scope"], roadmap["out_of_scope"]
                )),
                {phase["key"]: PhaseSpec(phase["name"], phase["desired_state"]) for phase in content["phases"]},
                tuple(
                    PhaseRelationSpec(relation["type"], key_of.get(relation["from"], relation["from"]),
                                      key_of.get(relation["to"], relation["to"]))
                    for relation in content["relations"]
                ),
            )
            return RoadmapWriterInput(
                roadmap["id"], stages, phase_ids,
                {index: relation["id"] for index, relation in enumerate(content["relations"])}, reservations,
            )
        works = content["works"]
        confirmation = content["confirmation"]
        generated = len(works) + (1 if confirmation is not None else 0)
        if len(content["relations"]) < generated:
            raise WriterInputUnavailable("its relations do not hold the generated integration relations")
        declared = content["relations"][: len(content["relations"]) - generated]
        types = [relation["type"] for relation in declared]
        if not set(types) <= {"planned_next", "requires_completion"} or types != sorted(
            types, key=lambda value: 0 if value == "planned_next" else 1
        ):
            raise WriterInputUnavailable("its declared relations are not planned_next followed by requires_completion")
        work_ids = {work["key"]: work["id"] for work in works}
        key_of = {work_id: key for key, work_id in work_ids.items()}

        def related(items: list[dict[str, Any]]) -> tuple[RelatedSpec, ...]:
            return tuple(RelatedSpec(item["type"], item["to"], item["condition"]) for item in items)

        def pairs(relation_type: str) -> tuple[tuple[str, str], ...]:
            return tuple(
                (key_of.get(relation["from"], relation["from"]), key_of.get(relation["to"], relation["to"]))
                for relation in declared if relation["type"] == relation_type
            )

        design = rm.PhaseEntryDesign(
            {work["key"]: rm.WorkDesign(work["name"], work["desired_state"], related(work["related"])) for work in works},
            rm.WorkDesign(content["integration"]["name"], content["integration"]["desired_state"],
                          related(content["integration"]["related"])),
            None if confirmation is None else rm.WorkDesign(
                confirmation["name"], confirmation["desired_state"], related(confirmation["related"])
            ),
            pairs("planned_next"),
            pairs("requires_completion"),
            None,
        )
        stages = rm.phase_entry_stages(design, content["phase_id"], content["roadmap_id"])
        tail = content["relations"][len(declared):]
        return PhaseEntryWriterInput(
            phase_id=content["phase_id"],
            roadmap_id=content["roadmap_id"],
            stages=stages,
            work_ids=work_ids,
            relation_ids={index: relation["id"] for index, relation in enumerate(declared)},
            related_ids={
                (work["key"], index): item["id"] for work in works for index, item in enumerate(work["related"])
            },
            integration_id=content["integration"]["id"],
            integration_relation_ids={index: relation["id"] for index, relation in enumerate(tail[: len(works)])},
            integration_related_ids={
                ("integration", index): item["id"] for index, item in enumerate(content["integration"]["related"])
            },
            confirmation_id=None if confirmation is None else confirmation["id"],
            confirmation_relation_ids={} if confirmation is None else {0: tail[len(works)]["id"]},
            confirmation_related_ids={} if confirmation is None else {
                ("confirmation", index): item["id"] for index, item in enumerate(confirmation["related"])
            },
            reservations=reservations,
        )
    except WriterInputUnavailable:
        raise
    except (KeyError, TypeError, IndexError, AttributeError, ValidationError) as exc:
        raise WriterInputUnavailable(f"{type(exc).__name__}: {exc}") from exc


# --------------------------------------------------------------------------- E: the expected physical projection

class ExpectedUnavailable(Exception):
    """The expected physical projection cannot be computed; unknown is never proof."""


@dataclass(frozen=True)
class ExpectedEntry:
    path: str
    status: str
    old_mode: str
    old_blob: str
    new_mode: str
    new_blob: str
    content: bytes

    def record(self) -> dict[str, str]:
        return {
            "path": self.path, "status": self.status, "old_mode": self.old_mode, "new_mode": self.new_mode,
            "old_blob": self.old_blob, "new_blob": self.new_blob,
        }


@dataclass(frozen=True)
class ExpectedProjection:
    """E: every path, transition, mode and exact byte a registration commit on ``parent`` may carry."""

    parent: str
    entries: tuple[ExpectedEntry, ...]

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(entry.path for entry in self.entries)

    def by_path(self) -> dict[str, ExpectedEntry]:
        return {entry.path: entry for entry in self.entries}

    def delta_record(self, commit: str) -> dict[str, Any]:
        """The ``review-planning-delta`` record of E with ``commit`` as the registration commit."""
        return planning.delta_record(self.parent, commit, [entry.record() for entry in self.entries])

    def delta_digest(self, commit: str) -> str:
        return serialize.digest(self.delta_record(commit))


@dataclass(frozen=True)
class Projected:
    """E on a base, with the base's committed view after W's effects (its committed basis) and those effects."""

    expected: ExpectedProjection
    view: ProjectView
    effects: tuple[Effect, ...]


def _apply_into(scratch: ProjectStore, effect: Effect, written: list[str]) -> None:
    record = {"kind": effect.kind, "payload": effect.payload}
    planned = planned_write(scratch, record)
    if planned is None:
        return
    path, text = planned
    durable_write_text(path, text, tmp_dir=scratch.tmp)
    relative = effect_path(record)
    if relative is not None and relative not in written:
        written.append(relative)


def _roadmap_stage_effects(scratch: ProjectStore, w: RoadmapWriterInput, written: list[str]) -> list[Effect]:
    from . import roadmap as rm

    effects: list[Effect] = []
    roadmap_effect = rm.roadmap_file_effect(
        w.roadmap_id, f"R-{scratch.count_entities('roadmap') + 1:02d}", w.stages.name, list(w.stages.sections)
    )
    _apply_into(scratch, roadmap_effect, written)
    effects.append(roadmap_effect)
    view = ProjectView.load(scratch)
    resolved = resolve_phase_relations(view, list(w.stages.relations), w.phase_ids, w.relation_ids)
    for effect in phase_registration_effects(
        w.stages.phases, w.phase_ids, resolved, w.roadmap_id, scratch.count_entities("phase")
    ):
        _apply_into(scratch, effect, written)
        effects.append(effect)
    return effects


def _work_stage_effects(
    scratch: ProjectStore,
    specs: dict[str, WorkSpec],
    relations: list[Any],
    work_ids: dict[str, str],
    relation_ids: dict[int, str],
    related_ids: dict[tuple[str, int], str],
    written: list[str],
) -> list[Effect]:
    view = ProjectView.load(scratch)
    resolved = _resolve_roadmap_relations(view, relations, work_ids, relation_ids)
    stage = _registration_effects(
        specs, work_ids, resolved, related_ids, {}, _allocated_displays(specs, scratch.count_entities("work"))
    )
    for effect in stage:
        _apply_into(scratch, effect, written)
    return stage


def _phase_entry_stage_effects(scratch: ProjectStore, w: PhaseEntryWriterInput, written: list[str]) -> list[Effect]:
    from . import roadmap as rm

    stages = w.stages
    effects = _work_stage_effects(
        scratch, stages.normal_specs, list(stages.normal_relations), w.work_ids, w.relation_ids, w.related_ids, written
    )
    effects += _work_stage_effects(
        scratch, {"integration": stages.integration_spec}, rm.integration_relations(w.work_ids),
        {"integration": w.integration_id}, w.integration_relation_ids, w.integration_related_ids, written,
    )
    if stages.confirmation_spec is not None and w.confirmation_id is not None:
        effects += _work_stage_effects(
            scratch, {"confirmation": rm.confirmation_stage_spec(stages.confirmation_spec, w.integration_id)},
            rm.confirmation_relations(w.integration_id), {"confirmation": w.confirmation_id},
            w.confirmation_relation_ids, w.confirmation_related_ids, written,
        )
    return effects


def require_adapter(context: object, review_kind: str) -> planning.PlanningKind:
    """The running implementation's adapter for a Run whose Context names it; ``ExpectedUnavailable`` otherwise."""
    found = planning.KINDS.get(review_kind)
    if (
        found is None
        or review_kind not in ADAPTERS
        or not isinstance(context, dict)
        or context.get("adapter_identity") != found.adapter_identity
        or context.get("projection_semantics_version") != found.projection_semantics_version
    ):
        raise ExpectedUnavailable(
            f"the running implementation does not provide the adapter and projection semantics the Run names "
            f"({review_kind})"
        )
    return found


def project_on(store: ProjectStore, material: dict[str, Any], base: str) -> Projected:
    """E of the Candidate ``material`` on commit ``base``: the writer's builders and planned-write, on ``base``'s files.

    Deterministic, from committed inputs alone: ``base``'s canonical files are
    materialized from raw blobs, W's stage inputs go through the writer's own
    effect builders with display numbers allocated on that base, and each
    effect is applied by the writer's own planned-write computation. No
    recorded effect, note or runtime record takes part.
    """
    repo = store.root
    try:
        w = writer_input(material)
        with materialized(store, base) as scratch:
            written: list[str] = []
            if isinstance(w, RoadmapWriterInput):
                effects = _roadmap_stage_effects(scratch, w, written)
            else:
                effects = _phase_entry_stage_effects(scratch, w, written)
            view = ProjectView.load(scratch)
            contents = {path: (scratch.root / path).read_bytes() for path in written}
    except (CommittedReadError, ValidationError, OSError, KeyError) as exc:
        raise ExpectedUnavailable(f"the expected physical projection on {base} cannot be computed: {exc}") from exc
    old = gitcmd.tree_entries(repo, base, list(contents))
    if old is None:
        raise ExpectedUnavailable(f"Git cannot list {base}'s entries at the registration paths")
    old_by_path = {entry.path: entry for entry in old}
    zero = gitcmd.zero_object_id(base)
    entries: list[ExpectedEntry] = []
    for path in sorted(contents, key=lambda value: value.encode("utf-8", "surrogateescape")):
        blob = gitcmd.hash_blob(repo, contents[path])
        if blob is None or len(blob) != len(base):
            raise ExpectedUnavailable(f"Git cannot give the object ID of the expected bytes of {path}")
        before = old_by_path.get(path)
        if before is None:
            entries.append(ExpectedEntry(path, "A", "000000", zero, "100644", blob, contents[path]))
        elif before.type == "blob" and before.mode == "100644":
            entries.append(ExpectedEntry(path, "M", "100644", before.oid, "100644", blob, contents[path]))
        else:
            raise ExpectedUnavailable(f"{base} holds {path} as {before.type} {before.mode}, not a regular file")
    return Projected(ExpectedProjection(base, tuple(entries)), view, tuple(effects))


def expected_projection(store: ProjectStore, material: dict[str, Any], context: object, parent: str) -> ExpectedProjection:
    """E for a Run whose Context is ``context``, on ``parent``: the one computation every proof uses."""
    require_adapter(context, str(material.get("review_kind")))
    return project_on(store, material, parent).expected


def delta_problem(repo: Path, expected: ExpectedProjection, commit: str) -> str | None:
    """The comparison of E with ``commit``'s delta against E's parent; None when they are exactly equal.

    ``git diff-tree -r -z --no-renames --no-abbrev --raw P K`` must list exactly
    E's paths, each with E's status, old mode and blob, new mode ``100644`` and
    E's new blob - so every committed byte, whole ledgers included, is E's.
    """
    delta = gitcmd.commit_delta(repo, expected.parent, commit)
    if delta is None:
        return f"Git cannot list the delta of {commit} against {expected.parent}"
    found = {entry.path: entry for entry in delta}
    wanted = expected.by_path()
    extra = sorted(set(found) - set(wanted))
    missing = sorted(set(wanted) - set(found))
    if extra or missing:
        parts = []
        if extra:
            parts.append("extra path(s) " + ", ".join(extra))
        if missing:
            parts.append("missing path(s) " + ", ".join(missing))
        return f"{commit}'s delta is not the expected physical projection: " + "; ".join(parts)
    for path, entry in wanted.items():
        actual = found[path]
        if (actual.status, actual.old_mode, actual.old_blob, actual.new_mode, actual.new_blob) != (
            entry.status, entry.old_mode, entry.old_blob, entry.new_mode, entry.new_blob
        ):
            return (
                f"{commit} holds {path} as {actual.status} {actual.old_mode}->{actual.new_mode} {actual.new_blob}, "
                f"and the expected physical projection is {entry.status} {entry.old_mode}->{entry.new_mode} "
                f"{entry.new_blob}"
            )
    return None


def record_problem(mutation: Mutation, expected: ExpectedProjection, stages: tuple[str, ...]) -> str | None:
    """The record check: the recorded registration effects write exactly E's paths and E's bytes."""
    effects = [effect for effect in mutation.effects if effect.get("stage") in stages]
    written: dict[str, dict[str, Any]] = {}
    for effect in effects:
        path = effect_path(effect)
        if path is not None:
            written[path] = effect
    wanted = expected.by_path()
    if set(written) != set(wanted):
        return (
            "the recorded registration writes "
            + (", ".join(sorted(written)) or "nothing")
            + "; the expected physical projection is "
            + ", ".join(sorted(wanted))
        )
    for path, effect in written.items():
        entry = wanted[path]
        if effect["kind"] == "write_file":
            if effect["payload"]["content"].encode("utf-8") != entry.content:
                return f"the recorded write of {path} is not the expected physical projection's bytes"
        elif effect.get("wrote") != "sha256:" + hashlib.sha256(entry.content).hexdigest():
            return f"what the registration last wrote to {path} is not the expected physical projection's bytes"
    return None


# --------------------------------------------------------------------------- semantic adapters

@dataclass(frozen=True)
class PersistedResult:
    """Which registration a semantic reading is of: the Candidate's reserved IDs, and the R9 selection's basis."""

    material: dict[str, Any]
    selection_view: ProjectView | None = None


def _mismatch_marker(described: str) -> dict[str, Any]:
    # A value no reviewed Candidate holds, so a projection carrying it is never the reviewed one.
    return {"__persisted_mismatch__": described}


class _PlanningAdapter:
    review_kind = ""

    def adapter_identity(self) -> str:
        return planning.KINDS[self.review_kind].adapter_identity

    def loader_identity(self) -> str:
        return "workline.state.ProjectView.load"

    def normalize_candidate(self, candidate: dict[str, Any], reserved: Any = None) -> Projection:
        return reviewed_artifact(
            planning.KINDS[self.review_kind].projection_semantics_version, planning.candidate_content(candidate)
        )

    def project_expected(self, candidate: dict[str, Any], reserved: Any, base: tuple[ProjectStore, str]):
        """E on ``base`` (a store and a commit), as the reviewed artifact and the authorized transition."""
        from .review.projections import ProjectionSet, authorized_transition

        store, parent = base
        expected = project_on(store, candidate, parent).expected
        return ProjectionSet(
            reviewed_artifact=self.normalize_candidate(candidate),
            authorized_transition=authorized_transition(
                planning.KINDS[self.review_kind].projection_semantics_version,
                {"parent": parent, "entries": [entry.record() for entry in expected.entries]},
            ),
        )

    def load_persisted(self, result_identity: PersistedResult, view: ProjectView) -> tuple[PersistedResult, ProjectView]:
        return result_identity, view


class RoadmapPlanAdapter(_PlanningAdapter):
    """The Roadmap semantic round-trip adapter (``roadmap-plan-adapter-v1``)."""

    review_kind = planning.KIND_ROADMAP

    def normalize_persisted(self, loaded: tuple[PersistedResult, ProjectView]) -> Projection:
        result, view = loaded
        content = planning.candidate_content(result.material)
        reviewed = content["roadmap"]
        entity = view.roadmaps.get(reviewed["id"])
        if entity is None:
            roadmap: dict[str, Any] = _mismatch_marker(f"Roadmap {reviewed['id']} missing")
        else:
            roadmap = {
                "id": entity.id,
                "name": entity.name,
                "background": entity.section(ROADMAP_BACKGROUND_HEADING),
                "desired_state": entity.section(ROADMAP_DESIRED_HEADING),
                "scope": entity.section(ROADMAP_SCOPE_HEADING),
                "out_of_scope": entity.section(ROADMAP_OUT_OF_SCOPE_HEADING),
            }
        phases: list[dict[str, Any]] = []
        for phase in content["phases"]:
            found = view.phases.get(phase["id"])
            if found is None or found.roadmap_id != reviewed["id"]:
                phases.append(_mismatch_marker(f"Phase {phase['id']} missing or not in the Roadmap"))
                continue
            phases.append({
                "key": phase["key"], "id": found.id, "name": found.name,
                "desired_state": found.section(PHASE_DESIRED_HEADING),
            })
        by_id = {relation.id: relation for relation in view.roadmap_relations}
        relations: list[dict[str, Any]] = []
        for relation in content["relations"]:
            found_relation = by_id.get(relation["id"])
            if found_relation is None or found_relation.extra:
                relations.append(_mismatch_marker(f"relation {relation['id']} missing or carrying extra fields"))
                continue
            relations.append({
                "id": found_relation.id, "type": found_relation.type,
                "from": found_relation.from_id, "to": found_relation.to,
            })
        return reviewed_artifact(
            planning.KINDS[self.review_kind].projection_semantics_version,
            {"roadmap": roadmap, "phases": phases, "relations": relations},
        )


class PhaseEntryDesignAdapter(_PlanningAdapter):
    """The Phase-entry semantic round-trip adapter (``phase-entry-design-adapter-v1``)."""

    review_kind = planning.KIND_PHASE_ENTRY

    def _work(self, view: ProjectView, reviewed: dict[str, Any], content: dict[str, Any]) -> dict[str, Any]:
        entity = view.works.get(reviewed["id"])
        expected_origin = {"type": "roadmap", "roadmap_id": content["roadmap_id"], "phase_id": content["phase_id"]}
        if entity is None or entity.phase_id != content["phase_id"] or entity.meta.get("origin") != expected_origin:
            return _mismatch_marker(f"Work {reviewed['id']} missing, or not in the Phase with its origin")
        related_by_id = {relation.id: relation for relation in view.related}
        related: list[dict[str, Any]] = []
        for item in reviewed["related"]:
            found = related_by_id.get(item["id"])
            if found is None or found.from_id != entity.id or set(found.extra) - {"condition"}:
                related.append(_mismatch_marker(f"Related {item['id']} missing, from another Work, or with extra fields"))
                continue
            related.append({"id": found.id, "type": found.type, "to": found.to, "condition": found.extra.get("condition")})
        normalized: dict[str, Any] = {
            "id": entity.id,
            "name": entity.name,
            "desired_state": entity.section(WORK_DESIRED_HEADING),
            "related": related,
            "work_kind": entity.work_kind,
        }
        if "key" in reviewed:
            normalized["key"] = reviewed["key"]
        if "confirmation_target" in reviewed or "confirmation_target" in entity.meta:
            normalized["confirmation_target"] = entity.meta.get("confirmation_target")
        return normalized

    def normalize_persisted(self, loaded: tuple[PersistedResult, ProjectView]) -> Projection:
        result, view = loaded
        content = planning.candidate_content(result.material)
        phase = view.phases.get(content["phase_id"])
        normalized: dict[str, Any] = {
            "phase_id": content["phase_id"],
            "roadmap_id": phase.roadmap_id if phase is not None else _mismatch_marker("Phase missing"),
            "works": [self._work(view, work, content) for work in content["works"]],
            "integration": self._work(view, content["integration"], content),
            "confirmation": None if content["confirmation"] is None else self._work(view, content["confirmation"], content),
        }
        by_id = {relation.id: relation for relation in view.roadmap_relations}
        relations: list[dict[str, Any]] = []
        for relation in content["relations"]:
            found = by_id.get(relation["id"])
            if found is None or found.extra:
                relations.append(_mismatch_marker(f"relation {relation['id']} missing or carrying extra fields"))
                continue
            relations.append({"id": found.id, "type": found.type, "from": found.from_id, "to": found.to})
        normalized["relations"] = relations
        if "canonical_first_work" in content:
            selection = r9_selection(result.selection_view or view, content["phase_id"])
            keys = {work["id"]: work["key"] for work in content["works"]}
            if selection.kind == "none":
                normalized["canonical_first_work"] = None
            elif selection.kind == "unique" and selection.work_id in keys:
                normalized["canonical_first_work"] = {"key": keys[selection.work_id], "id": selection.work_id}
            else:
                normalized["canonical_first_work"] = _mismatch_marker(f"R9 selection {selection.kind} {selection.ties}")
        return reviewed_artifact(planning.KINDS[self.review_kind].projection_semantics_version, normalized)


ADAPTERS = {
    planning.KIND_ROADMAP: RoadmapPlanAdapter(),
    planning.KIND_PHASE_ENTRY: PhaseEntryDesignAdapter(),
}


def adapter_for(review_kind: str) -> _PlanningAdapter:
    found = ADAPTERS.get(review_kind)
    if found is None:
        raise ExpectedUnavailable(f"no planning adapter for {review_kind}")
    return found


def semantic_projection(material: dict[str, Any], view: ProjectView, selection_view: ProjectView | None = None) -> Projection:
    """The persisted semantic projection of the registration ``material`` names, as ``view`` reads it."""
    adapter = adapter_for(material["review_kind"])
    return adapter.normalize_persisted(adapter.load_persisted(PersistedResult(material, selection_view), view))


def reviewed_projection(material: dict[str, Any]) -> Projection:
    return adapter_for(material["review_kind"]).normalize_candidate(material)


# --------------------------------------------------------------------------- the planning operation

@dataclass
class _Op:
    """One review-v1 planning invocation: what it asks for and how its Candidate is identified."""

    store: ProjectStore
    operation: str
    kind: planning.PlanningKind
    request: dict[str, Any]
    review: PlanningReview
    live_identity: dict[str, Any]
    phase_id: str | None = None
    phase_display: str | None = None
    entry_key: str | None = None
    request_digest: str = ""
    operation_identity: str = ""

    def __post_init__(self) -> None:
        self.request_digest = planning.request_digest(self.operation, self.request, self.phase_id)
        self.operation_identity = planning.operation_identity(self.operation, self.request_digest)

    @property
    def roadmap_kind(self) -> bool:
        return self.kind.review_kind == planning.KIND_ROADMAP

    @property
    def registration_stages(self) -> tuple[str, ...]:
        return ROADMAP_STAGES if self.roadmap_kind else PHASE_ENTRY_STAGES

    def domain_keys(self) -> list[tuple[str, str]]:
        return roadmap_domain_keys(self.request) if self.roadmap_kind else phase_entry_domain_keys(self.request)


@dataclass
class _Run:
    """The Review Run a planning mutation reserved or recovered, and the IDs it uses."""

    review_run_id: str
    task_id: str | None = None
    receipt_id: str | None = None
    consumption_id: str | None = None
    #: The freeze's material, present only between a new Run's freeze and its generation 1.
    frozen: dict[str, Any] | None = None


def _root(store: ProjectStore) -> Path:
    return store.root


def _candidate_target(material: dict[str, Any]) -> str:
    content = planning.candidate_content(material)
    return content["roadmap"]["id"] if material["review_kind"] == planning.KIND_ROADMAP else content["phase_id"]


def registration_paths(material: dict[str, Any]) -> list[str]:
    """The canonical paths the registration stages write (``skills/roadmap``: registration paths)."""
    content = planning.candidate_content(material)
    if material["review_kind"] == planning.KIND_ROADMAP:
        found = [ProjectStore.entity_rel_path("roadmap", content["roadmap"]["id"])]
        found += [ProjectStore.entity_rel_path("phase", phase["id"]) for phase in content["phases"]]
        if content["relations"]:
            found.append(ROADMAP_RELATIONS)
        return found
    works = [work["id"] for work in content["works"]] + [content["integration"]["id"]]
    if content["confirmation"] is not None:
        works.append(content["confirmation"]["id"])
    found = [ProjectStore.entity_rel_path("work", work_id) for work_id in works]
    found.append(ROADMAP_RELATIONS)
    items = [content["integration"]] + list(content["works"]) + ([content["confirmation"]] if content["confirmation"] else [])
    if any(item["related"] for item in items):
        found.append(RELATED_RELATIONS)
    return found


def entity_paths(material: dict[str, Any]) -> list[str]:
    """The registration's reserved entity paths: what a registration commit adds."""
    return [path for path in registration_paths(material) if path not in (ROADMAP_RELATIONS, RELATED_RELATIONS)]


def run_record_paths(review_run_id: str, material: dict[str, Any], task_id: str, receipt_id: str) -> list[str]:
    """The Run's record paths: snapshot, task input, gates 1-4, Receipt and the Supersession path."""
    return [
        review_paths.candidate_snapshot_rel(planning.candidate_hash(material)),
        review_paths.task_input_rel(task_id),
        *(review_paths.gate_rel(review_run_id, number) for number in range(1, planning.INVALIDATION_GENERATION + 1)),
        review_paths.receipt_rel(receipt_id),
        review_paths.supersession_rel(receipt_id),
    ]


def planning_owned_paths(review_run_id: str, material: dict[str, Any], task_id: str, receipt_id: str,
                         consumption_id: str) -> list[str]:
    """Registration paths + Run record paths + the planning Consumption path."""
    return sorted(set(
        registration_paths(material) + run_record_paths(review_run_id, material, task_id, receipt_id)
        + [review_paths.consumption_rel(consumption_id)]
    ))


# --------------------------------------------------------------------------- Git persistence preflight

def git_persistence_preflight(store: ProjectStore, planning_paths: list[str], review_record_paths: list[str]) -> None:
    """The transform attributes of every planning-owned path, and the checkout capability of every Review path.

    A Git stage that carries no Review record (the registration commit) has no
    Review path to prove the capability for.
    """
    gitops.require_no_planning_transform(store.root, planning_paths)
    if review_record_paths:
        checkout.require_checkout_capability(store, review_record_paths)


# --------------------------------------------------------------------------- currency (the declared base first)

@dataclass(frozen=True)
class Currency:
    """``current``, ``stale`` (with its §13 reason) or ``mismatch`` (with what differs)."""

    state: str
    detail: str = ""

    @property
    def current(self) -> bool:
        return self.state == "current"

    @property
    def stale(self) -> bool:
        return self.state == "stale"


def rebuild_content(
    kind: str, request: dict[str, Any], reserved: dict[str, str], view: ProjectView, phase_id: str | None
) -> dict[str, Any]:
    """The Candidate content rebuilt from a request identity, reserved IDs and a (committed) view."""
    if kind == planning.KIND_ROADMAP:
        return roadmap_candidate_content(request, reserved)
    phase = view.phases.get(phase_id or "")
    if phase is None:
        raise _NotInBase(phase_id or "")
    return phase_entry_candidate_content(request, phase_id or "", phase.roadmap_id or "", reserved)


def currency(
    store: ProjectStore,
    material: dict[str, Any],
    request: dict[str, Any],
    reserved: dict[str, str],
    run_context_hash: str,
    run_policy_hash: str,
    base: str,
    entry_key: str | None,
) -> Currency:
    """Currency against the exact base commit ``base``, in order: Context, Policy, declared base, then the rest.

    The declared base is computed on ``base``'s committed view; only with it
    equal is the Candidate rebuilt - from the planning invocation, the reserved
    IDs, that declared base and the R9 selection on ``base``'s committed basis -
    and compared with the stored snapshot. An unavailable Context is the
    ``review_context_unavailable`` STOP, never a stale difference.
    """
    kind = material["review_kind"]
    context = planning.context_record(store.workline_root(), kind)
    if serialize.digest(context) != run_context_hash:
        return Currency("stale", planning.STALE_CONTEXT)
    if planning.policy_hash() != run_policy_hash:
        return Currency("stale", planning.STALE_POLICY)
    try:
        view = committed_view(store, base)
    except (CommittedReadError, ValidationError) as exc:
        return Currency("mismatch", f"the committed view of {base} cannot be read: {exc}")
    content = planning.candidate_content(material)
    try:
        found_base = declared_base(view, content)
    except _NotInBase as exc:
        return Currency("stale", planning.STALE_DECLARED_BASE) if exc.entity_id else Currency("mismatch", str(exc))
    if serialize.canonical_data(found_base) != material["declared_base"]:
        return Currency("stale", planning.STALE_DECLARED_BASE)
    try:
        rebuilt = rebuild_content(kind, request, reserved, view, content.get("phase_id"))
        if kind == planning.KIND_PHASE_ENTRY:
            projected = project_on(store, material, base)
            rebuilt["canonical_first_work"] = first_work_of(
                r9_selection(projected.view, content["phase_id"]), rebuilt, entry_key
            )
        record = planning.candidate_record(kind, rebuilt, found_base)
    except (KeyError, TypeError, ValidationError, StopError, ExpectedUnavailable, _NotInBase) as exc:
        return Currency("mismatch", f"the Candidate cannot be rebuilt: {exc}")
    if planning.candidate_hash(record) != planning.candidate_hash(material) or record != material:
        return Currency("mismatch", "the rebuilt Candidate is not the reviewed one")
    return Currency("current")


# --------------------------------------------------------------------------- blob checks

def require_committed_records(store: ProjectStore, expected: dict[str, bytes]) -> None:
    """``gate.require_persisted`` and the blob check: HEAD holds each path as a ``100644`` blob of exactly these bytes."""
    relatives = sorted(expected)
    gate.require_persisted(store, relatives)
    head = gitcmd.head_commit(store.root)
    entries = None if head is None else gitcmd.tree_entries(store.root, head, relatives)
    if entries is None:
        raise StopError("git cannot list the committed Review records: STOP", code="review_persistence_unknown")
    by_path = {entry.path: entry for entry in entries}
    for relative in relatives:
        entry = by_path.get(relative)
        data = None if entry is None else gitcmd.read_blob(store.root, entry.oid)
        if entry is None or entry.type != "blob" or entry.mode != "100644" or data != expected[relative]:
            raise StopError(
                f"{relative} is not committed at HEAD as a 100644 blob of its canonical bytes, so the committed Review "
                "record is not the material a clone would reconstruct from: STOP",
                code="review_not_persisted",
            )


def _canonical_bytes_of(record: Any) -> bytes:
    return serialize.canonical_bytes(record.to_record() if hasattr(record, "to_record") else record)


# --------------------------------------------------------------------------- the operation binding

def _binding_holds(store: ProjectStore, binding: object) -> bool:
    if not isinstance(binding, dict):
        return False
    branch, head = binding.get("branch"), binding.get("head")
    if not isinstance(branch, str) or not gitcmd.full_commit_id(head):
        return False
    if gitcmd.current_branch_ref(store.root) != branch:
        return False
    current = gitcmd.head_commit(store.root)
    return current is not None and gitcmd.descends_from(store.root, current, head) is True


def require_binding(store: ProjectStore, mutation: Mutation) -> dict[str, str]:
    binding = mutation.note(NOTE_BINDING)
    if not _binding_holds(store, binding):
        raise _reconcile(
            f"the planning mutation {mutation.id} is bound to {binding}, and HEAD is no longer on that branch over a "
            "history holding that commit; nothing is replayed, recorded, committed or pushed (check the branch out "
            "to continue)",
            "review_binding_moved",
        )
    return dict(binding)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- generation mutations

_TRANSITION_OF = {1: "accept", 2: "settle", 3: "seal", 4: "invalidate"}


def _generation_invocation(
    mutation: Mutation, material_kind: str, run: _Run, generation: int, gate_record: records.GateGeneration,
    receipt_id: str | None, reason: str | None,
) -> dict[str, Any]:
    return {
        "operation": planning.OPERATION_GENERATION,
        "review_contract": planning.PLANNING_CONTRACT,
        "planning_mutation_id": mutation.id,
        "review_kind": material_kind,
        "review_run_id": run.review_run_id,
        "generation": generation,
        "transition": _TRANSITION_OF[generation],
        "candidate_hash": gate_record.candidate_hash,
        "review_context_hash": gate_record.review_context_hash,
        "effective_policy_hash": gate_record.effective_policy_hash,
        "obligation_digest": gate_record.obligation_digest,
        "receipt_id": receipt_id,
        "invalidation_reason": reason,
    }


def _generation_commit_message(generation: int, review_run_id: str) -> str:
    return f"chore(workline): record review generation {generation} of {review_run_id}"


def _finish_generation(store: ProjectStore, gen: Mutation) -> None:
    """Apply a generation mutation's stage, commit it with the planning primitive, prove it persisted, complete it."""
    stage = gen.stage_effects(STAGE_GENERATION)
    paths = [effect["payload"]["path"] for effect in stage]
    expected = {effect["payload"]["path"]: effect["payload"]["content"].encode("utf-8") for effect in stage}
    gen.apply()
    if not gen.has_stage(STAGE_GENERATION_COMMIT):
        git_persistence_preflight(store, paths, paths)
        generation = gen.invocation.get("generation")
        gen.add_effects(STAGE_GENERATION_COMMIT, [
            gitops.review_commit_effect(
                store, _generation_commit_message(int(generation), str(gen.invocation.get("review_run_id"))), paths
            )
        ])
        gen.apply()
    require_committed_records(store, expected)
    gen.complete()


def _start_generation(
    store: ProjectStore,
    mutation: Mutation,
    run: _Run,
    review_kind: str,
    generation: int,
    gate_record: records.GateGeneration,
    extra: list[tuple[str, dict[str, Any]]],
    *,
    receipt_id: str | None = None,
    reason: str | None = None,
) -> None:
    """Start, apply, commit and complete the generation mutation writing ``gate_record`` (and ``extra``)."""
    require_binding(store, mutation)
    scope = gate.next_generation_scope(store, run.review_run_id)
    if scope.generation != generation:
        raise _reconcile(
            f"Review Run {run.review_run_id}'s next generation is {scope.generation}, and the planning flow is at "
            f"generation {generation}",
            "review_chain_invalid",
        )
    extra_paths = [path for path, _ in extra]
    writes = [(scope.gate_path, gate_record.to_record())] + list(extra)
    if generation == records.FIRST_GENERATION:
        # accept: the snapshot and the task input are written before gate 1, which names them
        writes = list(extra) + [(scope.gate_path, gate_record.to_record())]
    invocation = _generation_invocation(mutation, review_kind, run, generation, gate_record, receipt_id, reason)
    files = tuple(scope.files) + tuple(extra_paths)
    gen = MutationController(store).open(OWNER, invocation, WriteScope(files=files))
    record_paths = [path for path, _ in writes]
    with abandon_on_stop(gen):
        gitops.record_preexisting_dirty(gen, store.root)
        gitops.ensure_separable_before_effects(gen, record_paths)
        if not gen.has_stage(STAGE_GENERATION):
            gate.require_committable(store, record_paths)
            git_persistence_preflight(store, record_paths, record_paths)
            gen.add_effects(
                STAGE_GENERATION, [Effect.create_file(path, serialize.canonical_text(record)) for path, record in writes]
            )
    _finish_generation(store, gen)


def resolve_pending_generation(store: ProjectStore, mutation: Mutation, run: _Run, registration_started: bool) -> None:
    """§11.8 step 3: a pending generation mutation of this Run is resumed first, and nothing else is."""
    pending = gate.pending_generation_mutations(store, run.review_run_id)
    if not pending:
        return
    if len(pending) > 1:
        raise _reconcile(
            f"Review Run {run.review_run_id} has {len(pending)} pending generation mutations "
            f"({', '.join(sorted(str(record.get('mutation_id')) for record in pending))})",
            "review_generation_owner_conflict",
        )
    record = pending[0]
    invocation = record.get("invocation") or {}
    if (
        record.get("owner") != OWNER
        or invocation.get("operation") != planning.OPERATION_GENERATION
        or invocation.get("planning_mutation_id") != mutation.id
        or invocation.get("review_run_id") != run.review_run_id
        or registration_started
    ):
        raise _reconcile(
            f"the pending generation mutation {record.get('mutation_id')} of Review Run {run.review_run_id} is bound "
            f"to {invocation.get('planning_mutation_id')}, not to this planning mutation {mutation.id} (or the "
            "registration has begun)",
            "review_generation_owner_conflict",
        )
    gen = MutationController(store).open(OWNER, invocation, WriteScope.from_record(record.get("write_scope") or {}))
    if not gen.effects:
        gen.abandon()
        return
    generation = invocation.get("generation")
    try:
        chain = ReviewStore(store).gate_chain(run.review_run_id)
    except ValidationError as exc:
        raise _reconcile(f"Review Run {run.review_run_id}'s chain does not validate: {exc}", "review_chain_invalid") from exc
    recorded = {effect["payload"]["path"]: effect["payload"]["content"] for effect in gen.stage_effects(STAGE_GENERATION)}
    next_number = records.FIRST_GENERATION if chain is None else chain.next_generation
    fits = generation == next_number
    if not fits and chain is not None and generation == chain.latest.generation:
        gate_path = review_paths.gate_rel(run.review_run_id, int(generation))
        stored = ReviewStore(store).read_bytes(gate_path)
        fits = stored is not None and gate_path in recorded and stored == recorded[gate_path].encode("utf-8")
    if not fits or invocation.get("transition") != _TRANSITION_OF.get(generation):
        raise _reconcile(
            f"the pending generation mutation {gen.id} writes generation {generation} ({invocation.get('transition')}) "
            f"of Review Run {run.review_run_id}, which is not the chain's next transition",
            "review_chain_invalid",
        )
    _finish_generation(store, gen)


# --------------------------------------------------------------------------- semantic proof helpers (P6-P9, CP6, CP9)

def candidate_target(material: dict[str, Any]) -> str:
    """A Candidate's target identity: its reserved Roadmap ID, or its ``phase_id``."""
    return _candidate_target(material)


def _expected_new_relations(material: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The roadmap relations and the Related a registration appends, in registration order, as records."""
    content = planning.candidate_content(material)
    roadmap = [
        {"id": relation["id"], "type": relation["type"], "from": relation["from"], "to": relation["to"]}
        for relation in content["relations"]
    ]
    related: list[dict[str, Any]] = []
    if material["review_kind"] == planning.KIND_PHASE_ENTRY:
        items = list(content["works"]) + [content["integration"]]
        if content["confirmation"] is not None:
            items.append(content["confirmation"])
        for item in items:
            for entry in item["related"]:
                record = {"id": entry["id"], "type": entry["type"], "from": item["id"], "to": entry["to"]}
                if entry["condition"] is not None:
                    record["condition"] = entry["condition"]
                related.append(record)
    return roadmap, related


def selected_first_work_id(material: dict[str, Any], view: ProjectView) -> str | None:
    """The R9 selection's Work ID on ``view`` (PhaseEntryDesign); None for none, or for a RoadmapPlan."""
    if material["review_kind"] != planning.KIND_PHASE_ENTRY:
        return None
    selection = r9_selection(view, planning.candidate_content(material)["phase_id"])
    return selection.work_id if selection.kind == "unique" else None


def semantic_problem(material: dict[str, Any], before: ProjectView, after: ProjectView) -> tuple[str, str] | None:
    """P6-P9 / CP6: ``after`` is ``before`` plus exactly the Candidate's registration, meaning the reviewed Candidate.

    Returns the first item that fails, in the order P6, P7, P8, P9 (``skills/review``), with its detail; CP6 is all
    four as one item.
    """
    content = planning.candidate_content(material)
    own = _candidate_entity_ids(content)
    for kind_name in ("roadmaps", "phases", "works"):
        new = set(getattr(after, kind_name)) - set(getattr(before, kind_name))
        if not set(getattr(before, kind_name)) <= set(getattr(after, kind_name)):
            return "P6", f"{kind_name} of the parent are missing after the registration"
        expected = {entity_id for entity_id in own if entity_id in _ids_of_kind(content, kind_name)}
        if new != expected:
            return "P6", f"the registration's new {kind_name} are not exactly the Candidate's reserved ones"
    roadmap, related = _expected_new_relations(material)
    for described, found_before, found_after, wanted in (
        ("roadmap relations", before.roadmap_relations, after.roadmap_relations, roadmap),
        ("Related", before.related, after.related, related),
    ):
        records_before = [relation.to_record() for relation in found_before]
        records_after = [relation.to_record() for relation in found_after]
        if records_after != records_before + wanted:
            return "P6", f"the {described} are not the parent's followed by exactly the Candidate's, in registration order"
    if validate_structure(after):
        return "P7", "the registration commit's structure does not validate"
    if semantic_projection(material, after) != reviewed_projection(material):
        return "P8", "the persisted semantic projection is not the reviewed Candidate's"
    if material["review_kind"] == planning.KIND_PHASE_ENTRY:
        first = content.get("canonical_first_work")
        if selected_first_work_id(material, after) != (None if first is None else first["id"]):
            return "P9", "the R9 selection on the registration is not the reviewed canonical first Work"
    return None


def _ids_of_kind(content: dict[str, Any], kind_name: str) -> set[str]:
    if "roadmap" in content:
        if kind_name == "roadmaps":
            return {content["roadmap"]["id"]}
        if kind_name == "phases":
            return {phase["id"] for phase in content["phases"]}
        return set()
    if kind_name != "works":
        return set()
    return _candidate_entity_ids(content)


def persisted_result_claims(
    material: dict[str, Any],
    run_operation_identity: str,
    registration: str,
    parent: str,
    expected: ExpectedProjection,
    selection_id: str | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Every ``persisted_result`` field but ``branch``, as the committed objects prove it (Consumption, CP9)."""
    content = planning.candidate_content(material)
    claims: dict[str, Any] = {
        "contract": planning.PERSISTED_RESULT_CONTRACT,
        "request_digest": planning.request_digest_of(run_operation_identity),
        "registration_commit": registration,
        "registration_parent": parent,
        "registration_delta_digest": expected.delta_digest(registration),
        "semantic_projection_digest": reviewed_projection(material).identity(),
        "adapter_identity": context.get("adapter_identity"),
        "loader_identity": context.get("loader_identity"),
    }
    if material["review_kind"] == planning.KIND_ROADMAP:
        claims.update({
            "roadmap_id": content["roadmap"]["id"],
            "phase_ids": [{"key": phase["key"], "id": phase["id"]} for phase in content["phases"]],
            "relation_ids": [relation["id"] for relation in content["relations"]],
        })
        return claims
    roadmap, related = _expected_new_relations(material)
    claims.update({
        "phase_id": content["phase_id"],
        "roadmap_id": content["roadmap_id"],
        "work_ids": [{"key": work["key"], "id": work["id"]} for work in content["works"]],
        "integration_work_id": content["integration"]["id"],
        "confirmation_work_id": None if content["confirmation"] is None else content["confirmation"]["id"],
        "roadmap_relation_ids": [record["id"] for record in roadmap],
        "related_relation_ids": [record["id"] for record in related],
        "canonical_first_work_id": selection_id,
    })
    return claims


# --------------------------------------------------------------------------- entry

def create_roadmap_reviewed(
    store: ProjectStore, plan: Any, request: dict[str, Any], review: PlanningReview, pending: list[dict[str, Any]]
) -> ReviewedPlanningResult:
    """The review-v1 Roadmap creation, from §5.6 step 7 on (the live checks and the preflight have run)."""
    op = _Op(
        store=store, operation=planning.OPERATION_ROADMAP, kind=planning.KINDS[planning.KIND_ROADMAP],
        request=request, review=review, live_identity={"name": plan.name, "request": request},
    )
    return _enter(op, pending)


def enter_phase_reviewed(
    store: ProjectStore,
    phase_id: str,
    roadmap_id: str,
    phase: Any,
    design: Any,
    identity: dict[str, Any],
    review: PlanningReview,
    interrupted: list[dict[str, Any]],
) -> ReviewedPlanningResult:
    """The review-v1 Phase entry, from §5.6 step 7 on (the live checks and the preflight have run)."""
    op = _Op(
        store=store, operation=planning.OPERATION_PHASE_ENTRY, kind=planning.KINDS[planning.KIND_PHASE_ENTRY],
        request=identity, review=review, live_identity={"phase_id": phase_id, "design": identity},
        phase_id=phase_id, phase_display=phase.display, entry_key=design.entry,
    )
    return _enter(op, interrupted)


def _enter(op: _Op, pending: list[dict[str, Any]]) -> ReviewedPlanningResult:
    from . import roadmap as rm

    discovery = None
    if pending:
        identity = {key: value for key, value in pending[0]["invocation"].items() if key != "operation"}
    else:
        discovery = _discover(op)
        identity = {**op.live_identity, **planning.invocation_markers()}
        if discovery.recoverable is not None:
            identity[planning.MARKER_RECOVERY] = discovery.recoverable.review_run_id
    live_refusal = rm.refuse_invalid_phase_writes if op.roadmap_kind else rm.refuse_invalid_work_writes

    def refuse_recorded(mutation: Mutation) -> None:
        live_refusal(mutation)
        _pre_replay_kp(op, mutation)

    entities = [] if op.roadmap_kind else [op.phase_id or ""]
    mutation, destination = rm._open(op.store, op.operation, identity, entities, refuse_recorded=refuse_recorded)
    return _run(op, mutation, destination, discovery)


def _discover(op: _Op):
    from .review import recovery

    def run_currency(found: Any) -> Currency:
        reserved = {key: identifier for key, identifier, _ in reservations_of(found.material)}
        head = gitcmd.head_commit(op.store.root) or ""
        return currency(
            op.store, found.material, op.request, reserved, found.chain.latest.review_context_hash,
            found.chain.latest.effective_policy_hash, head, op.entry_key,
        )

    return recovery.discover(op.store, op.kind.review_kind, op.operation_identity, currency=run_currency)


def _is_recovery(mutation: Mutation) -> bool:
    return planning.MARKER_RECOVERY in mutation.invocation


def _generation_started(op: _Op, mutation: Mutation) -> bool:
    """Whether the planning mutation has started a generation mutation (the §12 table, per kind)."""
    bound = [
        record for record in MutationController(op.store).list_pending()
        if (record.get("invocation") or {}).get("operation") == planning.OPERATION_GENERATION
        and (record.get("invocation") or {}).get("planning_mutation_id") == mutation.id
    ]
    if bound:
        return True
    review = ReviewStore(op.store)
    if _is_recovery(mutation):
        binding = mutation.note(NOTE_RECOVERY_BINDING)
        if not isinstance(binding, dict):
            return False
        chain = review.gate_chain(str(binding.get("review_run_id")))
        return chain is not None and chain.latest.generation > int(binding.get("latest_generation") or 0)
    run_id = _reserved_run_id(op, mutation)
    return run_id is not None and review.gate_chain(run_id) is not None


def _target_of(op: _Op, mutation: Mutation) -> str | None:
    return mutation.reserved("roadmap") if op.roadmap_kind else op.phase_id


def _reserved_run_id(op: _Op, mutation: Mutation) -> str | None:
    if _is_recovery(mutation):
        return str(mutation.invocation[planning.MARKER_RECOVERY])
    target = _target_of(op, mutation)
    return None if target is None else mutation.reserved(gate.review_run_key(op.kind.review_kind, target))


def _abandon_idle_generation(op: _Op, mutation: Mutation) -> None:
    """§11.8 step 3 for a generation mutation that recorded nothing: it is abandoned, and nothing physical exists.

    Only a pending generation mutation bound to this planning mutation and its
    Run, with no recorded effect, is abandoned here; anything else is left to
    the resolution of :func:`resolve_pending_generation`, which refuses it.
    """
    run_id = _reserved_run_id(op, mutation)
    if run_id is None:
        return
    pending = gate.pending_generation_mutations(op.store, run_id)
    if len(pending) != 1:
        return
    record = pending[0]
    invocation = record.get("invocation") or {}
    if (
        record.get("owner") == OWNER
        and invocation.get("operation") == planning.OPERATION_GENERATION
        and invocation.get("planning_mutation_id") == mutation.id
        and invocation.get("review_run_id") == run_id
        and not record.get("effects")
    ):
        MutationController(op.store).open(OWNER, invocation, WriteScope.from_record(record.get("write_scope") or {})).abandon()


def _run(op: _Op, mutation: Mutation, destination: Any, discovery: Any) -> ReviewedPlanningResult:
    if not mutation.effects:
        _abandon_idle_generation(op, mutation)
    if not mutation.effects and not _generation_started(op, mutation):
        # Before its first generation mutation a review-v1 planning mutation holds nothing canonical:
        # every STOP of its setup abandons it, begun or resumed, a Phase entry included.
        with abandon_on_stop(mutation):
            if _is_recovery(mutation):
                run = _setup_recovery(op, mutation, destination, discovery)
            else:
                run = _setup_new_run(op, mutation, destination, discovery)
    else:
        run = _recorded_run(op, mutation)
    try:
        return _proceed(op, mutation, destination, run)
    except StopError:
        _abandon_if_nothing_started(op, mutation)
        raise


def _abandon_if_nothing_started(op: _Op, mutation: Mutation) -> None:
    """The §12 table after the setup too: a STOP of any class abandons a planning mutation that has recorded no effect
    and started no generation mutation - a recovery planning mutation until its first generation mutation (§12.4)."""
    try:
        idle = mutation.status == "pending" and not mutation.effects and not _generation_started(op, mutation)
    except (StopError, ValidationError, OSError):
        return  # when that cannot be told, the planning mutation is left pending
    if idle:
        mutation.abandon()


def _recorded_run(op: _Op, mutation: Mutation) -> _Run:
    run_id = _reserved_run_id(op, mutation)
    if run_id is None:
        raise _reconcile(f"the planning mutation {mutation.id} recorded no Review Run", "review_chain_invalid")
    task_id = mutation.reserved(gate.review_task_key(run_id, op.kind.task_slot))
    receipt_id = mutation.reserved(gate.review_receipt_key(run_id, planning.SEAL_GENERATION))
    consumption_id = None if receipt_id is None else mutation.reserved(gate.review_consumption_key(receipt_id))
    return _Run(run_id, task_id, receipt_id, consumption_id)


# --------------------------------------------------------------------------- setup: a new Run (the freeze)

def _expected_review_keys(op: _Op, mutation: Mutation) -> set[str]:
    keys = {key for key, _ in op.domain_keys()}
    target = _target_of(op, mutation)
    if target is None:
        return keys
    run_key = gate.review_run_key(op.kind.review_kind, target)
    keys.add(run_key)
    run_id = mutation.reserved(run_key)
    if run_id is not None:
        keys.add(gate.review_task_key(run_id, op.kind.task_slot))
        receipt_key = gate.review_receipt_key(run_id, planning.SEAL_GENERATION)
        keys.add(receipt_key)
        receipt_id = mutation.reserved(receipt_key)
        if receipt_id is not None:
            keys.add(gate.review_consumption_key(receipt_id))
    return keys


def _require_known_reservations(op: _Op, mutation: Mutation) -> None:
    recorded = set((mutation.record.get("reserved_ids") or {}).keys())
    unknown = sorted(recorded - _expected_review_keys(op, mutation))
    if unknown:
        raise _reconcile(
            f"the planning mutation {mutation.id} recorded reservation(s) {', '.join(unknown)}, which its setup does not "
            "reserve",
            "review_setup_invalid",
        )


def _setup_new_run(op: _Op, mutation: Mutation, destination: Any, discovery: Any) -> _Run:
    from . import roadmap as rm

    store = op.store
    if mutation.note(NOTE_DISCOVERY) is None:
        outcome = discovery
        if outcome is None:
            outcome = _discover(op)
            if outcome.recoverable is not None:
                raise _reconcile(
                    f"canonical recovery discovery now finds Review Run {outcome.recoverable.review_run_id} recoverable "
                    f"for this invocation; the planning mutation {mutation.id} names a new Run and is not rewritten",
                    "review_discovery_changed",
                )
        mutation.set_note(NOTE_DISCOVERY, {"set_aside": list(outcome.set_aside)})
    set_aside = list((mutation.note(NOTE_DISCOVERY) or {}).get("set_aside") or [])
    _require_known_reservations(op, mutation)

    # step 1 - the live reservations and payload refusals
    wt_view = ProjectView.load(store)
    if op.roadmap_kind:
        roadmap_id = mutation.reserve_id("roadmap", "roadmap")
        mutation.extend_scope(entities=[roadmap_id])
        plan_stages = _request_roadmap_stages(op.request)
        written = [rm.roadmap_file_effect(roadmap_id, f"R-{store.count_entities('roadmap') + 1:02d}",
                                          plan_stages.name, list(plan_stages.sections))]
        projected_wt = wt_view.with_effects(written)
        decided = rm.decide_phases(
            mutation, "phases", roadmap_id, plan_stages.phases, list(plan_stages.relations), view=projected_wt
        )
        rm.refuse_invalid_phase_writes(mutation, decided.effects, projected_wt)
        reserved = {key: mutation.reserved(key) or "" for key, _ in op.domain_keys()}
    else:
        reserved = {key: mutation.reserve_id(key, kind_name) for key, kind_name in op.domain_keys()}
        mutation.extend_scope(entities=[
            identifier for (key, kind_name) in op.domain_keys() if kind_name == "work"
            for identifier in [reserved[key]]
        ])
        design_stages = _request_phase_stages(op.request, op.phase_id or "", _phase_roadmap(wt_view, op.phase_id))
        for stage_specs in (
            design_stages.normal_specs,
            {"integration": design_stages.integration_spec},
            {} if design_stages.confirmation_spec is None else {"confirmation": design_stages.confirmation_spec},
        ):
            if stage_specs:
                rm.validate_work_specs(stage_specs, wt_view)
        work_ids = {key[len("works:work:"):]: reserved[key] for key in reserved if key.startswith("works:work:")}
        relation_ids = {int(key.rsplit(":", 1)[1]): reserved[key] for key in reserved if key.startswith("works:rel:")}
        _resolve_roadmap_relations(wt_view, list(design_stages.normal_relations), work_ids, relation_ids)

    # step 2 - the Candidate on the committed basis of HEAD
    head = gitcmd.head_commit(store.root)
    if head is None:
        raise StopError("HEAD names no commit, so the Candidate has no committed basis: STOP", code="review_base_uncommitted")
    committed = _committed_or_stop(store, head)
    content = rebuild_content(op.kind.review_kind, op.request, reserved, committed, op.phase_id) \
        if op.roadmap_kind or op.phase_id in committed.phases else None
    if content is None:
        raise ValidationError(
            f"Phase {op.phase_id} is present only in the working tree, so the review would rest on an uncommitted fact",
            code="review_base_uncommitted",
        )
    try:
        base = declared_base(committed, content)
    except _NotInBase as missing:
        raise ValidationError(
            f"{missing.entity_id} is present only in the working tree, so the review would rest on an uncommitted fact",
            code="review_base_uncommitted",
        ) from None
    try:
        base_wt = declared_base(wt_view, content)
    except _NotInBase:
        base_wt = None
    pre = planning.candidate_record(op.kind.review_kind, content, base)
    projected = project_on_strict(store, pre, head)
    problems = validate_structure(projected.view)
    if problems:
        raise ValidationError(
            "postcheck: " + "; ".join(f"{problem.code}: {problem.message}" for problem in problems), code="postcheck_failed"
        )
    first_id: str | None = None
    selection: Selection | None = None
    if not op.roadmap_kind:
        selection = r9_selection(projected.view, op.phase_id or "")
        first = first_work_of(selection, content, op.entry_key)
        content = dict(content)
        content["canonical_first_work"] = first
        first_id = None if first is None else first["id"]
    # the working-tree compatibility check, after the R9 selection (§14.4 step 2): the declared base, then (Phase
    # entry) the Phase's Work set and the R9 selection, each on the working tree and on HEAD's committed view (§7.4)
    if base_wt is None or serialize.canonical_data(base_wt) != serialize.canonical_data(base):
        raise ValidationError(
            "the working tree and HEAD give a different declared base; commit or discard the change first",
            code="review_base_uncommitted",
        )
    if not op.roadmap_kind:
        wt_works = sorted(work.id for work in wt_view.phase_works(op.phase_id or ""))
        committed_works = sorted(work.id for work in committed.phase_works(op.phase_id or ""))
        wt_selection = r9_selection(wt_view.with_effects(list(projected.effects)), op.phase_id or "")
        if wt_works != committed_works or wt_selection != selection:
            raise ValidationError(
                "the working tree and HEAD give a different Work set of the Phase or R9 selection; commit or discard "
                "the change first",
                code="review_base_uncommitted",
            )
    candidate = planning.candidate_record(op.kind.review_kind, content, base)
    if semantic_projection(candidate, projected.view) != reviewed_projection(candidate):
        raise ValidationError(
            "a projected Candidate or persistence mismatch: what the writer would persist does not read back as the "
            "reviewed Candidate",
            code="review_candidate_unrepresentable",
        )
    snapshot = planning.snapshot_for(candidate)
    try:
        serialize.canonical_bytes(snapshot.to_record())
        representable = serialize.canonical_roundtrips(snapshot.to_record())
    except Exception as exc:
        raise ValidationError(
            f"a projected Candidate representability failure: {exc}", code="review_candidate_unrepresentable"
        ) from exc
    if not representable:
        raise ValidationError(
            "a projected Candidate representability failure: its canonical text does not read back",
            code="review_candidate_unrepresentable",
        )

    # step 3 - Context, Policy, evidence, envelope
    context = planning.context_record(store.workline_root(), op.kind.review_kind)
    evidence = planning.evidence_record(first_id, phase_entry=not op.roadmap_kind, remote=destination is not None)
    envelope = planning.request_envelope(op.kind.review_kind, candidate, context, set_aside)

    # step 4 - the Review IDs, in order
    target = candidate_target(candidate)
    run_id = mutation.reserve_id(gate.review_run_key(op.kind.review_kind, target), "review_run")
    task_id = mutation.reserve_id(gate.review_task_key(run_id, op.kind.task_slot), "review_task")
    receipt_id = mutation.reserve_id(gate.review_receipt_key(run_id, planning.SEAL_GENERATION), "review_receipt")
    consumption_id = mutation.reserve_id(gate.review_consumption_key(receipt_id), "review_consumption")
    mutation.extend_scope(files=[review_paths.consumption_rel(consumption_id)])
    _require_known_reservations(op, mutation)

    # step 5 - committability, persistence, capability, namespace, dirty overlap, barrier
    records_paths = run_record_paths(run_id, candidate, task_id, receipt_id) + [review_paths.consumption_rel(consumption_id)]
    gate.require_committable(store, records_paths)
    owned = planning_owned_paths(run_id, candidate, task_id, receipt_id, consumption_id)
    git_persistence_preflight(store, owned, sorted(set(records_paths + checkout.committed_review_paths(store))))
    checkout.require_namespace_readable(store)
    gitops.ensure_separable_before_effects(mutation, owned)
    if destination is not None:
        from .review import publication

        publication.require_barrier_clear(store.root, head)

    # step 6 - the operation binding
    _note_binding(store, mutation)
    task_input = planning.task_input_for(
        task_id=task_id, review_kind=op.kind.review_kind, reviewer_identity=op.review.reviewer_identity,
        reviewer_version=op.review.reviewer_version, envelope=envelope, candidate=candidate,
        review_context_hash=serialize.digest(context), effective_policy_hash=planning.policy_hash(),
    )
    return _Run(run_id, task_id, receipt_id, consumption_id, frozen={
        "candidate": candidate, "snapshot": snapshot, "task_input": task_input, "evidence": evidence,
        "context": context, "target": target,
    })


def _note_binding(store: ProjectStore, mutation: Mutation) -> None:
    recorded = mutation.note(NOTE_BINDING)
    if recorded is not None:
        require_binding(store, mutation)
        return
    branch = gitcmd.current_branch_ref(store.root)
    head = gitcmd.head_commit(store.root)
    if branch is None or head is None:
        raise StopError("HEAD is on no branch, so the operation binding cannot be recorded: STOP", code="detached_head")
    mutation.set_note(NOTE_BINDING, {"branch": branch, "head": head})


def _committed_or_stop(store: ProjectStore, commit: str) -> ProjectView:
    try:
        return committed_view(store, commit)
    except CommittedReadError as exc:
        raise StopError(f"the committed view of {commit} cannot be read: {exc}", code="review_base_uncommitted") from exc


def project_on_strict(store: ProjectStore, material: dict[str, Any], base: str) -> Projected:
    """:func:`project_on` where a live payload refusal keeps its own code (the freeze)."""
    try:
        return project_on(store, material, base)
    except ExpectedUnavailable as exc:
        cause = exc.__cause__
        if isinstance(cause, StopError):
            raise cause
        raise StopError(f"the committed basis of {base} cannot be computed: {exc}", code="review_base_uncommitted") from exc


def _phase_roadmap(view: ProjectView, phase_id: str | None) -> str:
    phase = view.phases.get(phase_id or "")
    return "" if phase is None else (phase.roadmap_id or "")


def _request_roadmap_stages(request: dict[str, Any]):
    """The Roadmap creation's stage inputs from its request identity (for the live payload refusals at the freeze)."""
    from . import roadmap as rm

    return rm.RoadmapStages(
        request["name"],
        tuple(rm.roadmap_file_sections(request["background"], request["desired_state"],
                                       request["scope"], request["out_of_scope"])),
        {phase["key"]: PhaseSpec(phase["name"], phase["desired_state"]) for phase in request["phases"]},
        tuple(PhaseRelationSpec(relation["type"], relation["from"], relation["to"]) for relation in request["relations"]),
    )


def _request_phase_stages(design: dict[str, Any], phase_id: str, roadmap_id: str):
    """The Phase entry's stage inputs from its design identity (for the live payload refusals at the freeze)."""
    from . import roadmap as rm

    def work(item: dict[str, Any]):
        return rm.WorkDesign(
            item["name"], item["desired_state"],
            tuple(RelatedSpec(entry["type"], entry["to"], entry["condition"]) for entry in item["related"]),
        )

    rebuilt = rm.PhaseEntryDesign(
        {item["key"]: work(item) for item in design["works"]},
        work(design["integration"]),
        None if design["confirmation"] is None else work(design["confirmation"]),
        tuple((pair["from"], pair["to"]) for pair in design["planned_next"]),
        tuple((pair["from"], pair["to"]) for pair in design["requires_completion"]),
        design.get("entry"),
    )
    return rm.phase_entry_stages(rebuilt, phase_id, roadmap_id)


# --------------------------------------------------------------------------- setup: a recovery planning mutation

def _setup_recovery(op: _Op, mutation: Mutation, destination: Any, discovery: Any) -> _Run:
    from .committed_view import committed_view as load_committed

    store = op.store
    run_id = str(mutation.invocation[planning.MARKER_RECOVERY])
    review = ReviewStore(store)
    if mutation.note(NOTE_RECOVERY_BINDING) is None:
        if mutation.record.get("reserved_ids"):
            raise _reconcile(
                f"the recovery planning mutation {mutation.id} holds reservations without its recovered binding",
                "review_recovery_reservation_conflict",
            )
        outcome = _discover(op)
        if outcome.recoverable is None or outcome.recoverable.review_run_id != run_id:
            raise _reconcile(
                f"Review Run {run_id} is no longer the one recoverable Run for this invocation",
                "review_discovery_changed",
            )
        bindings = _recovered_bindings(op, outcome.recoverable)
        head = gitcmd.head_commit(store.root) or ""
        used = _used_ids(ProjectView.load(store)) | _used_ids(load_committed(store, head))
        from .mutation import _bind_recovered_reservations

        _bind_recovered_reservations(
            mutation, bindings, used,
            (NOTE_RECOVERY_BINDING, {"review_run_id": run_id, "latest_generation": outcome.recoverable.chain.latest.generation}),
        )
    else:
        chain = review.gate_chain(run_id)
        if chain is None:
            raise _reconcile(f"Review Run {run_id} has no chain", "review_recovery_reservation_conflict")
        material = review.read_candidate_snapshot(chain.generations[0].candidate_hash).material or {}
        found = _RecoverySource(run_id, chain, material)
        wanted = {key: identifier for key, identifier, _ in _recovered_bindings(op, found)}
        recorded = mutation.record.get("reserved_ids") or {}
        if any(recorded.get(key) != identifier for key, identifier in wanted.items()):
            raise _reconcile(
                f"the recovery planning mutation {mutation.id}'s bound reservations are not the canonical ones of "
                f"Review Run {run_id}",
                "review_recovery_reservation_conflict",
            )
    chain = review.gate_chain(run_id)
    if chain is None:
        raise _reconcile(f"Review Run {run_id} has no chain", "review_chain_invalid")
    material = review.read_candidate_snapshot(chain.generations[0].candidate_hash).material or {}
    task_id = str(chain.generations[0].accepted_tasks[0]["task_id"])
    receipt_id = mutation.reserve_id(gate.review_receipt_key(run_id, planning.SEAL_GENERATION), "review_receipt")
    consumption_id = mutation.reserve_id(gate.review_consumption_key(receipt_id), "review_consumption")
    entity_ids = [identifier for _, identifier, kind_name in reservations_of(material) if kind_name != "relation"]
    mutation.extend_scope(entities=entity_ids, files=[review_paths.consumption_rel(consumption_id)])
    records_paths = run_record_paths(run_id, material, task_id, receipt_id) + [review_paths.consumption_rel(consumption_id)]
    gate.require_committable(store, records_paths)
    owned = planning_owned_paths(run_id, material, task_id, receipt_id, consumption_id)
    git_persistence_preflight(store, owned, sorted(set(records_paths + checkout.committed_review_paths(store))))
    checkout.require_namespace_readable(store)
    gitops.ensure_separable_before_effects(mutation, owned)
    if destination is not None:
        from .review import publication

        publication.require_barrier_clear(store.root, gitcmd.head_commit(store.root))
    _note_binding(store, mutation)
    return _Run(run_id, task_id, receipt_id, consumption_id)


@dataclass(frozen=True)
class _RecoverySource:
    review_run_id: str
    chain: Any
    material: dict[str, Any]


def _recovered_bindings(op: _Op, found: Any) -> list[tuple[str, str, str]]:
    """``(key, id, kind)`` a recovery binds: the snapshot's domain IDs, the Run, the task, the sealed Receipt."""
    bindings = list(reservations_of(found.material))
    target = candidate_target(found.material)
    run_id = found.review_run_id
    bindings.append((gate.review_run_key(op.kind.review_kind, target), run_id, "review_run"))
    bindings.append((gate.review_task_key(run_id, op.kind.task_slot), str(found.chain.generations[0].accepted_tasks[0]["task_id"]), "review_task"))
    if len(found.chain.generations) >= planning.SEAL_GENERATION:
        receipt = found.chain.generation(planning.SEAL_GENERATION).receipt_id
        if receipt is not None:
            bindings.append((gate.review_receipt_key(run_id, planning.SEAL_GENERATION), receipt, "review_receipt"))
    return bindings


def _used_ids(view: ProjectView) -> set[str]:
    return (
        set(view.works) | set(view.phases) | set(view.roadmaps)
        | {relation.id for relation in view.roadmap_relations} | {relation.id for relation in view.related}
    )


# --------------------------------------------------------------------------- the flow, by the validated chain

def _registration_started(op: _Op, mutation: Mutation) -> bool:
    return any(mutation.has_stage(stage) for stage in op.registration_stages)


def _chain(op: _Op, run: _Run):
    try:
        return ReviewStore(op.store).gate_chain(run.review_run_id)
    except ValidationError as exc:
        raise _reconcile(f"Review Run {run.review_run_id}'s chain does not validate: {exc}", "review_chain_invalid") from exc


def _require_shape(run: _Run, chain: Any) -> None:
    """The chain is one of the four shapes a P2 Run has (``skills/review``: the planning transition state machine)."""
    generations = chain.generations
    problems: list[str] = []
    if len(generations) > planning.INVALIDATION_GENERATION:
        problems.append("more than four generations")
    first = generations[0]
    if first.status != records.GATE_STATUS_OPEN or len(first.accepted_tasks) != 1 or first.settled_tasks:
        problems.append("generation 1 is not one accepted, unsettled task")
    if run.task_id is not None and first.accepted_tasks and str(first.accepted_tasks[0]["task_id"]) != run.task_id:
        problems.append("generation 1 accepts another task than the reserved one")
    if len(generations) >= 2 and (generations[1].status != records.GATE_STATUS_OPEN or len(generations[1].settled_tasks) != 1):
        problems.append("generation 2 is not an open settlement")
    if len(generations) >= 3 and (not generations[2].sealed or (run.receipt_id and generations[2].receipt_id != run.receipt_id)):
        problems.append("generation 3 is not the seal issuing the reserved Receipt")
    if len(generations) >= 4 and (generations[3].status != records.GATE_STATUS_OPEN or generations[3].settled_tasks != generations[2].settled_tasks):
        problems.append("generation 4 is not an open invalidation")
    if problems:
        raise _reconcile(f"Review Run {run.review_run_id}: " + "; ".join(problems), "review_chain_invalid")


def _proceed(op: _Op, mutation: Mutation, destination: Any, run: _Run) -> ReviewedPlanningResult:
    while True:
        resolve_pending_generation(op.store, mutation, run, _registration_started(op, mutation))
        chain = _chain(op, run)
        started = _registration_started(op, mutation)
        if chain is None:
            if run.frozen is None:
                raise _reconcile(f"Review Run {run.review_run_id} has no chain to continue", "review_chain_invalid")
            _accept(op, mutation, run)
            run.frozen = None
            continue
        _require_shape(run, chain)
        latest = chain.latest.generation
        if latest == 1:
            if started:
                raise _reconcile("a registration stage is recorded while the Run is unsettled", "review_chain_invalid")
            result = _launch_and_settle(op, mutation, run, chain)
            if result is not None:
                return result
            continue
        if latest == 2:
            if started:
                raise _reconcile("a registration stage is recorded while the Run is unsealed", "review_chain_invalid")
            if not planning.authorizes(chain.latest):
                return _finish(op, mutation, run, STATUS_NOT_AUTHORIZED, detail="not_authorized")
            found = _run_currency(op, mutation, run, chain, gitcmd.head_commit(op.store.root) or "")
            if found.stale:
                return _finish(op, mutation, run, STATUS_STALE, detail=found.detail)
            if not found.current:
                raise _reconcile(f"the Candidate does not reproduce: {found.detail}", "review_candidate_mismatch")
            _seal(op, mutation, run, chain)
            continue
        if latest == 3:
            if not started:
                outcome = _use_check(op, mutation, run, chain)
                if outcome.stale:
                    _invalidate(op, mutation, run, chain, outcome.detail)
                    continue
            return _registration_flow(op, mutation, destination, run, chain)
        if started:
            raise _reconcile("generation 4 exists while a registration stage is recorded", "review_chain_invalid")
        supersession = ReviewStore(op.store).read_supersession(str(chain.generation(planning.SEAL_GENERATION).receipt_id))
        return _finish(
            op, mutation, run, STATUS_STALE, detail=supersession.reason,
            receipt_id=str(chain.generation(planning.SEAL_GENERATION).receipt_id),
        )


def _run_material(op: _Op, chain: Any) -> dict[str, Any]:
    return ReviewStore(op.store).read_candidate_snapshot(chain.generations[0].candidate_hash).material or {}


def _reserved_map(op: _Op, mutation: Mutation, material: dict[str, Any]) -> dict[str, str]:
    """The domain reservations the rebuild uses: the planning mutation's own (recorded, or bound from the Run)."""
    recorded = mutation.record.get("reserved_ids") or {}
    return {key: str(recorded[key]) for key, _, _ in reservations_of(material) if key in recorded}


def _run_currency(op: _Op, mutation: Mutation, run: _Run, chain: Any, base: str) -> Currency:
    material = _run_material(op, chain)
    first = chain.generations[0]
    return currency(
        op.store, material, op.request, _reserved_map(op, mutation, material), first.review_context_hash,
        first.effective_policy_hash, base, op.entry_key,
    )


# --------------------------------------------------------------------------- generations 1-4

def _coverage(task_slot: str, task_id: str, settled: list[dict[str, Any]]) -> dict[str, Any]:
    return planning.coverage_record([(task_slot, task_id)], settled)


def _accept(op: _Op, mutation: Mutation, run: _Run) -> None:
    frozen = run.frozen or {}
    task_input = frozen["task_input"]
    descriptor = planning.accepted_descriptor(task_input)
    candidate = frozen["candidate"]
    gate_one = records.GateGeneration(
        review_run_id=run.review_run_id, generation=1, previous_generation=None, previous_digest=None,
        review_kind=op.kind.review_kind, target_identity=frozen["target"], operation_identity=op.operation_identity,
        candidate_hash=planning.candidate_hash(candidate), review_context_hash=serialize.digest(frozen["context"]),
        effective_policy_hash=planning.policy_hash(), evidence_digest=serialize.digest(frozen["evidence"]),
        coverage_digest=serialize.digest(_coverage(op.kind.task_slot, task_input.task_id, [])),
        raw_report_set_digest=serialize.digest(planning.report_set_record([])),
        adjudication_digest=serialize.digest(planning.adjudication_record([])),
        obligation_digest=serialize.digest(planning.obligations_record([])),
        accepted_tasks=(descriptor,), settled_tasks=(), status=records.GATE_STATUS_OPEN, receipt_id=None,
        authorized_operation_stage=None,
    )
    snapshot = frozen["snapshot"]
    _start_generation(
        op.store, mutation, run, op.kind.review_kind, 1, gate_one,
        [
            (review_paths.candidate_snapshot_rel(snapshot.candidate_hash), snapshot.to_record()),
            (review_paths.task_input_rel(task_input.task_id), task_input.to_record()),
        ],
    )


def _report_copy(store: ProjectStore, task_id: str) -> Path:
    return store.root / review_paths.runtime_report_rel(task_id)


def _settled_report(op: _Op, chain: Any) -> dict[str, Any] | None:
    """The runtime report copy of the settled task, only when its digest is the settled ``result_digest``."""
    settled = chain.latest.settled_tasks
    if not settled:
        return None
    task = settled[0]
    path = _report_copy(op.store, str(task["task_id"]))
    try:
        record = serialize.parse(path.read_text(encoding="utf-8"), "the runtime report copy")
    except (OSError, UnicodeError, ValidationError):
        return None
    return record if serialize.digest(record) == task["result_digest"] else None


def _findings(op: _Op, chain: Any) -> tuple[PlanningReviewFinding, ...]:
    report = _settled_report(op, chain)
    return () if report is None else planning.findings_of(report)


def _launch_and_settle(op: _Op, mutation: Mutation, run: _Run, chain: Any) -> ReviewedPlanningResult | None:
    """§10.3-§10.5: the launch checks, the reviewer, the report, and generation 2; or terminal ``stale``."""
    store = op.store
    review = ReviewStore(store)
    first = chain.latest
    if first.generation != 1 or len(first.accepted_tasks) != 1 or first.settled_tasks:
        raise _reconcile("the Run's latest generation is not generation 1 with one unsettled task", "review_chain_invalid")
    descriptor = first.accepted_tasks[0]
    task_id = str(descriptor["task_id"])
    snapshot_path = review_paths.candidate_snapshot_rel(first.candidate_hash)
    task_input_path = review_paths.task_input_rel(task_id)
    gate_path = review_paths.gate_rel(run.review_run_id, 1)
    require_committed_records(store, {
        relative: (review.read_bytes(relative) or b"") for relative in (snapshot_path, task_input_path, gate_path)
    })
    problems = review.provenance_problems(descriptor, 1)
    if problems:
        raise _reconcile("the accepted task's provenance: " + "; ".join(message for _, message in problems), "review_task_invalid")
    task_input = review.read_task_input(task_id)
    material = review.read_candidate_snapshot(first.candidate_hash).material or {}
    envelope_problems = planning.task_input_problems(
        task_input, material, first.candidate_hash, first.review_context_hash, first.effective_policy_hash
    )
    if envelope_problems:
        raise _reconcile("the accepted task's request: " + "; ".join(envelope_problems), "review_task_invalid")
    require_binding(store, mutation)
    found = _run_currency(op, mutation, run, chain, gitcmd.head_commit(store.root) or "")
    if found.stale:
        return _finish(op, mutation, run, STATUS_STALE, detail=found.detail)
    if not found.current:
        raise _reconcile(f"the Candidate does not reproduce: {found.detail}", "review_candidate_mismatch")
    if (op.review.reviewer_identity, op.review.reviewer_version) != (descriptor["reviewer_identity"], descriptor["reviewer_version"]):
        raise StopError(
            f"task {task_id} was accepted for reviewer {descriptor['reviewer_identity']} {descriptor['reviewer_version']}, "
            f"and this invocation names {op.review.reviewer_identity} {op.review.reviewer_version}; the reviewer is not called",
            code="review_reviewer_mismatch",
        )
    task = planning.task_from_input(task_input, first.review_kind)
    try:
        returned = op.review.reviewer(task)
    except Exception as exc:
        raise StopError(f"the reviewer raised for task {task_id}: {exc}; nothing is settled", code="review_reviewer_failed") from exc
    report = planning.report_record(returned, descriptor)
    result_digest = serialize.digest(report)
    durable_write_text(_report_copy(store, task_id), serialize.canonical_text(report), tmp_dir=store.tmp)
    gate.validate_settlement(store, run.review_run_id, task_id, result_digest, str(returned.reviewer_identity))
    found = _run_currency(op, mutation, run, chain, gitcmd.head_commit(store.root) or "")
    if found.stale:
        return _finish(op, mutation, run, STATUS_STALE, detail=found.detail)
    if not found.current:
        raise _reconcile(f"the Candidate does not reproduce: {found.detail}", "review_candidate_mismatch")
    settled = {"task_id": task_id, "status": planning.settled_status(report), "result_digest": result_digest,
               "settled_generation": 2}
    pairs = [(settled, report)]
    gate_two = replace(
        first,
        generation=2,
        previous_generation=1,
        previous_digest=chain.latest_digest,
        coverage_digest=serialize.digest(_coverage(op.kind.task_slot, task_id, [settled])),
        raw_report_set_digest=serialize.digest(planning.report_set_record([settled])),
        adjudication_digest=serialize.digest(planning.adjudication_record(pairs)),
        obligation_digest=serialize.digest(planning.obligations_record(pairs)),
        settled_tasks=(settled,),
    )
    _start_generation(store, mutation, run, first.review_kind, 2, gate_two, [])
    return None


def _seal(op: _Op, mutation: Mutation, run: _Run, chain: Any) -> None:
    second = chain.latest
    receipt_id = run.receipt_id
    if receipt_id is None:
        raise _reconcile("the planning mutation holds no reserved Receipt ID", "review_chain_invalid")
    gate_three = replace(
        second, generation=3, previous_generation=2, previous_digest=chain.latest_digest,
        status=records.GATE_STATUS_SEALED, receipt_id=receipt_id,
        authorized_operation_stage=op.kind.authorized_operation_stage,
    )
    receipt = records.Receipt(
        receipt_id=receipt_id, review_run_id=run.review_run_id, review_generation=3,
        review_kind=second.review_kind, target_identity=second.target_identity,
        operation_identity=second.operation_identity, authorized_candidate_hash=second.candidate_hash,
        review_context_hash=second.review_context_hash, effective_policy_hash=second.effective_policy_hash,
        coverage_hash=second.coverage_digest, adjudication_hash=second.adjudication_digest,
        obligation_digest=second.obligation_digest, unresolved_obligations=0,
        authorized_operation_stage=op.kind.authorized_operation_stage,
    )
    _start_generation(
        op.store, mutation, run, second.review_kind, 3, gate_three,
        [(review_paths.receipt_rel(receipt_id), receipt.to_record())], receipt_id=receipt_id,
    )


def _invalidate(op: _Op, mutation: Mutation, run: _Run, chain: Any, reason: str) -> None:
    third = chain.latest
    receipt_id = str(third.receipt_id)
    planning.context_record(op.store.workline_root(), third.review_kind)  # unavailable -> the STOP, never stale
    gate_four = replace(
        third, generation=4, previous_generation=3, previous_digest=chain.latest_digest,
        evidence_digest=serialize.digest(planning.invalidation_evidence_record(receipt_id, reason)),
        status=records.GATE_STATUS_OPEN, receipt_id=None, authorized_operation_stage=None,
    )
    supersession = records.Supersession(receipt_id, run.review_run_id, 4, reason)
    _start_generation(
        op.store, mutation, run, third.review_kind, 4, gate_four,
        [(review_paths.supersession_rel(receipt_id), supersession.to_record())], receipt_id=receipt_id, reason=reason,
    )


# --------------------------------------------------------------------------- the use check

def _run_record_bytes(op: _Op, run: _Run, chain: Any, *, generations: int = 3) -> dict[str, bytes]:
    review = ReviewStore(op.store)
    first = chain.generations[0]
    task_id = str(first.accepted_tasks[0]["task_id"])
    wanted = [
        review_paths.candidate_snapshot_rel(first.candidate_hash),
        review_paths.task_input_rel(task_id),
        *(review_paths.gate_rel(run.review_run_id, number) for number in range(1, generations + 1)),
    ]
    third = chain.generation(planning.SEAL_GENERATION) if len(chain.generations) >= 3 else None
    if third is not None and third.receipt_id:
        wanted.append(review_paths.receipt_rel(third.receipt_id))
    return {relative: (review.read_bytes(relative) or b"") for relative in wanted}


def _receipt_problems(op: _Op, mutation: Mutation, run: _Run, chain: Any) -> list[str]:
    """Use check items 1-4 (and pre-Kp item 3's read back): a valid, unsuperseded, unconsumed Receipt of this Run."""
    from .review.validate import GATE_RECEIPT_BINDING

    review = ReviewStore(op.store)
    problems: list[str] = []
    third = chain.latest
    if third.generation != 3 or not third.sealed or third.receipt_id != run.receipt_id:
        return ["the latest generation is not the seal issuing the reserved Receipt"]
    try:
        receipt = review.read_receipt(str(run.receipt_id))
    except ValidationError as exc:
        return [f"the Receipt does not read back: {exc}"]
    for gate_field, receipt_field in GATE_RECEIPT_BINDING:
        if getattr(third, gate_field) != getattr(receipt, receipt_field):
            problems.append(f"the Receipt's {receipt_field} is not generation 3's {gate_field}")
    if review.supersession_exists(receipt.receipt_id):
        problems.append("a Supersession names the Receipt")
    try:
        consumed = review.consumption_by_receipt().get(receipt.receipt_id)
    except ValidationError as exc:
        return problems + [f"the Consumptions do not read: {exc}"]
    if consumed is not None:
        problems.append("a Consumption of the Receipt exists")
    target = _target_of(op, mutation) if not _is_recovery(mutation) else candidate_target(_run_material(op, chain))
    for name, wanted in (
        ("operation_identity", op.operation_identity), ("target_identity", target),
        ("review_kind", op.kind.review_kind), ("authorized_operation_stage", op.kind.authorized_operation_stage),
    ):
        if getattr(receipt, name) != wanted:
            problems.append(f"the Receipt's {name} is not the recomputed one")
    if receipt.review_run_id != run.review_run_id:
        problems.append("the Receipt is not of this planning mutation's Run")
    return problems


def _use_check(op: _Op, mutation: Mutation, run: _Run, chain: Any) -> Currency:
    """§17: the Receipt is valid, current on HEAD and usable here; ``use_check_head`` noted on PASS."""
    store = op.store
    problems = _receipt_problems(op, mutation, run, chain)
    if problems:
        raise _reconcile("the use check refuses the Receipt: " + "; ".join(problems), "review_receipt_invalid")
    require_binding(store, mutation)
    require_committed_records(store, _run_record_bytes(op, run, chain))
    head = gitcmd.head_commit(store.root) or ""
    found = _run_currency(op, mutation, run, chain, head)
    if found.stale:
        return found
    if not found.current:
        raise _reconcile(f"the Candidate does not reproduce: {found.detail}", "review_candidate_mismatch")
    material = _run_material(op, chain)
    changed = gitcmd.changed_against_head(store.root, registration_paths(material))
    if changed:
        raise StopError(
            gitops.OVERLAP_MESSAGE + ", ".join(sorted(changed)) + " (changed after the freeze)", code="dirty_overlap"
        )
    _require_display_base(op, mutation, head)
    mutation.set_note(NOTE_USE_CHECK_HEAD, head)
    return found


def _require_display_base(op: _Op, mutation: Mutation, head: str) -> None:
    """The display base check: the display-allocating ``*.md`` entries are HEAD's plus what this mutation wrote there."""
    store = op.store
    directories = ("roadmaps", "phases") if op.roadmap_kind else ("works",)
    written = {effect["payload"]["path"] for effect in mutation.effects if effect.get("kind") == "write_file"}
    for directory in directories:
        prefix = f"{WORKLINE_DIR}/{directory}/"
        listed = gitcmd.tree_entries(store.root, head, [prefix.rstrip("/")], recursive=True, trees=True)
        if listed is None:
            raise StopError(f"git cannot list {prefix} at {head}: STOP", code="dirty_overlap")
        at_head = {
            entry.path for entry in listed
            if entry.path.startswith(prefix) and "/" not in entry.path[len(prefix):] and entry.path.endswith(".md")
        }
        folder = store.root / WORKLINE_DIR / directory
        working = {f"{prefix}{found.name}" for found in folder.glob("*.md")} if folder.is_dir() else set()
        own = {path for path in written if path.startswith(prefix)}
        if working != at_head | own:
            raise StopError(
                gitops.OVERLAP_MESSAGE
                + ", ".join(sorted(working ^ (at_head | own)))
                + f" (the {directory} entries that allocate display numbers are not HEAD's plus this operation's own)",
                code="dirty_overlap",
            )


# --------------------------------------------------------------------------- the registration and its proofs

def _registration_flow(op: _Op, mutation: Mutation, destination: Any, run: _Run, chain: Any) -> ReviewedPlanningResult:
    from . import roadmap as rm

    store = op.store
    material = _run_material(op, chain)
    w = writer_input(material)
    head_now = gitcmd.head_commit(store.root) or ""

    def before_stage(stage: str) -> None:
        require_binding(store, mutation)
        _require_display_base(op, mutation, gitcmd.head_commit(store.root) or "")

    # step 1 - the live registration stages, fed from W
    if not mutation.has_stage(STAGE_KP):
        require_binding(store, mutation)
    if isinstance(w, RoadmapWriterInput):
        roadmap_id, phases = rm._register_roadmap(store, mutation, w.stages, before_stage=before_stage)
        registration: Any = None
    else:
        normal, integration_id, confirmation_id, _ = rm._register_phase_expansion(
            store, mutation, w.stages, before_stage=before_stage
        )
    # step 2 - the working-tree round trip, the R9 selection from HEAD's committed basis. It is compared on the
    # declared base the Candidate states: a committed declared-base change since the use check is the pre-Kp
    # currency proof's to classify (step 3), as a declared-base difference, never as an R9 mismatch (§13, §21.1 row 20).
    if not mutation.has_stage(STAGE_KP):
        if _declared_base_holds(store, material, head_now):
            basis = project_on(store, material, head_now).view if material["review_kind"] == planning.KIND_PHASE_ENTRY else None
            if semantic_projection(material, ProjectView.load(store), basis) != reviewed_projection(material):
                raise ValidationError(
                    "what the Project now holds is not what Review authorized (working-tree round trip)",
                    code="review_roundtrip_mismatch",
                )
        # step 3 - the pre-Kp currency proof on P = HEAD, then Kp with nothing in between
        parent = gitcmd.head_commit(store.root) or ""
        _pre_kp_proof(op, mutation, run, chain, parent)
        paths = registration_paths(material)
        binding = require_binding(store, mutation)
        git_persistence_preflight(store, paths, [])
        gitops.ensure_separable(gitops.record_preexisting_dirty(mutation, store.root), paths)
        # step 4 - Kp: the base-exact registration commit
        mutation.add_effects(STAGE_KP, [
            gitops.review_commit_effect(
                store, _registration_message(op, store, material), paths, base_head=parent,
                branch=binding["branch"], base_exact=True,
            )
        ])
        mutation.apply()
    # step 5 - C-2(Kp); the recorded Consumption effect is its durable checkpoint
    if mutation.has_stage(STAGE_CONSUMPTION):
        kp_record = _kp_effect(mutation) or {}
        kp, parent = str(kp_record.get("commit_id")), str((kp_record.get("payload") or {}).get("base_head"))
    else:
        kp, parent = _c2_kp(op, mutation, run, chain, material)
    # step 6 - the Planning Consumption
    consumption_path = review_paths.consumption_rel(str(run.consumption_id))
    if not mutation.has_stage(STAGE_CONSUMPTION):
        require_binding(store, mutation)
        git_persistence_preflight(store, [consumption_path], [consumption_path])
        gate.require_committable(store, [consumption_path])
        consumption = _consumption_record(op, mutation, run, chain, material, kp, parent)
        mutation.add_effects(STAGE_CONSUMPTION, [
            Effect.create_file(consumption_path, serialize.canonical_text(consumption.to_record()))
        ])
        mutation.apply()
    # step 7 - Km: the metadata commit
    if not mutation.has_stage(STAGE_KM):
        require_binding(store, mutation)
        git_persistence_preflight(store, [consumption_path], [consumption_path])
        gitops.ensure_separable(gitops.record_preexisting_dirty(mutation, store.root), [consumption_path])
        mutation.add_effects(STAGE_KM, [
            gitops.review_commit_effect(
                store, f"chore(workline): record review consumption {run.consumption_id}", [consumption_path]
            )
        ])
        mutation.apply()
    # step 8 - C-2(Km)
    km = None
    if not mutation.has_stage(STAGE_PUBLICATION):
        km = _c2_km(op, mutation, run, chain, material, kp)
        proof = {
            "contract": planning.PROOF_CONTRACT, "registration_commit": kp, "metadata_commit": km,
            "consumption_id": run.consumption_id,
        }
        if mutation.note(NOTE_PUBLICATION_PROOF) != proof:
            mutation.set_note(NOTE_PUBLICATION_PROOF, proof)
        # step 9 - publication of exact Km
        if destination is not None:
            binding = require_binding(store, mutation)
            from .review import publication

            publication.require_barrier_clear(store.root, km)
            mutation.add_effects(STAGE_PUBLICATION, [
                gitops.review_publication_effect(destination, binding["branch"].removeprefix("refs/heads/"), km)
            ])
    mutation.apply()
    if km is None:
        km = str((mutation.note(NOTE_PUBLICATION_PROOF) or {}).get("metadata_commit"))
    # step 10 - the live structure postcheck, then complete
    rm._stop_on_structure(store, "postcheck")
    content = planning.candidate_content(material)
    if isinstance(w, RoadmapWriterInput):
        registration = rm.RoadmapResult(
            content["roadmap"]["id"], {phase["key"]: phase["id"] for phase in content["phases"]},
            mutation.id, km, mutation.resumed,
        )
    else:
        first = content.get("canonical_first_work")
        registration = rm.PhaseEntryResult(
            content["phase_id"], {work["key"]: work["id"] for work in content["works"]}, content["integration"]["id"],
            None if content["confirmation"] is None else content["confirmation"]["id"],
            None if first is None else first["id"], True, mutation.id, km,
        )
    return _finish(
        op, mutation, run, STATUS_REGISTERED, detail="registered", receipt_id=run.receipt_id,
        consumption_id=run.consumption_id, registration=registration, chain=chain,
    )


def _declared_base_holds(store: ProjectStore, material: dict[str, Any], head: str) -> bool:
    """Whether HEAD's committed view gives the Candidate's declared base; anything unreadable gives no."""
    try:
        found = declared_base(committed_view(store, head), planning.candidate_content(material))
    except (_NotInBase, CommittedReadError, ValidationError):
        return False
    return serialize.canonical_data(found) == material["declared_base"]


def _registration_message(op: _Op, store: ProjectStore, material: dict[str, Any]) -> str:
    if op.roadmap_kind:
        roadmap_id = planning.candidate_content(material)["roadmap"]["id"]
        return f"chore(workline): create roadmap {ProjectView.load(store).roadmaps[roadmap_id].display}"
    return f"chore(workline): expand phase {op.phase_display}"


def _kp_effect(mutation: Mutation) -> dict[str, Any] | None:
    found = mutation.stage_effects(STAGE_KP)
    return found[0] if found else None


def _pre_replay_kp(op: _Op, mutation: Mutation) -> None:
    """The ``refuse_recorded`` hook: a recorded Kp is classified first, and replayed only after the pre-Kp proof."""
    kp = _kp_effect(mutation)
    if kp is None:
        return
    classification = mutation.controller.classify(kp)
    if classification == MISMATCH:
        raise _reconcile(
            f"the recorded registration commit of {mutation.id} is neither made nor makeable on its recorded parent "
            f"{kp['payload'].get('base_head')}",
            "review_registration_base_moved",
        )
    if classification == UNAPPLIED:
        run = _recorded_run(op, mutation)
        chain = _chain(op, run)
        if chain is None:
            raise _reconcile("the Run has no chain", "review_chain_invalid")
        _pre_kp_proof(op, mutation, run, chain, str(kp["payload"]["base_head"]))


def _planning_owned(run: _Run, chain: Any, material: dict[str, Any]) -> list[str]:
    task_id = str(chain.generations[0].accepted_tasks[0]["task_id"])
    return planning_owned_paths(run.review_run_id, material, task_id, str(run.receipt_id), str(run.consumption_id))


def _base_moved(message: str) -> ReconcileRequired:
    return _reconcile(message, "review_registration_base_moved")


def _pre_kp_proof(op: _Op, mutation: Mutation, run: _Run, chain: Any, parent: str) -> None:
    """§15.6: the pre-Kp currency proof on P, with the physical projection check of the recorded registration."""
    store = op.store
    material = _run_material(op, chain)
    head = gitcmd.head_commit(store.root)
    if head != parent or not _binding_holds(store, mutation.note(NOTE_BINDING)):
        raise _base_moved(f"HEAD is {head}, not the registration's parent {parent}, or the binding does not hold")
    use_check_head = mutation.note(NOTE_USE_CHECK_HEAD)
    if not isinstance(use_check_head, str) or not (
        parent == use_check_head
        or (
            gitcmd.descends_from(store.root, parent, use_check_head) is True
            and gitcmd.commits_touching(store.root, use_check_head, parent, _planning_owned(run, chain, material)) == []
        )
    ):
        raise _base_moved(f"{parent} is not use_check_head {use_check_head} or a descendant untouched at planning-owned paths")
    try:
        require_committed_records(store, _run_record_bytes(op, run, chain))
    except StopError as exc:
        raise _reconcile(f"the Run's records are not committed at {parent}: {exc}", "review_receipt_invalid") from exc
    problems = _receipt_problems(op, mutation, run, chain)
    if problems:
        raise _reconcile("; ".join(problems), "review_receipt_invalid")
    found = _run_currency(op, mutation, run, chain, parent)
    if found.stale:
        raise _reconcile(f"the authorized base changed ({found.detail}) after the registration began",
                         "review_registration_currency_changed")
    if not found.current:
        raise _reconcile(f"the Candidate does not reproduce on {parent}: {found.detail}", "review_candidate_mismatch")
    context = ReviewStore(store).read_task_input(str(chain.generations[0].accepted_tasks[0]["task_id"])).request_envelope.get("context")
    try:
        expected = expected_projection(store, material, context, parent)
    except ExpectedUnavailable as exc:
        raise _reconcile(f"the expected physical projection is unavailable: {exc}", "review_registration_projection_mismatch") from exc
    problem = record_problem(mutation, expected, op.registration_stages)
    if problem is not None:
        raise _reconcile(problem, "review_registration_projection_mismatch")


def _proof_failed(item: str, detail: str) -> ReconcileRequired:
    return _reconcile(f"C-2(Kp) {item} fails: {detail}", "review_persisted_proof_failed")


def _c2_kp(op: _Op, mutation: Mutation, run: _Run, chain: Any, material: dict[str, Any]) -> tuple[str, str]:
    """C-2(Kp), P1-P12 (``review-v1-planning-proof-v1``): Kp is this mutation's own, exactly E, exactly the Candidate."""
    from .review import committed as review_committed

    store = op.store
    repo = store.root
    kp_record = _kp_effect(mutation)
    if kp_record is None or kp_record.get("applied") is not True:
        raise _proof_failed("P1", "the registration commit is not recorded applied")
    kp = kp_record.get("commit_id")
    if not gitcmd.full_commit_id(kp):
        raise _reconcile(
            "the registration commit is recorded applied without the ID of a commit this mutation made, so it cannot "
            "be shown to be its own",
            "review_commit_unowned",
        )
    binding = mutation.note(NOTE_BINDING) or {}
    parents = gitcmd.commit_parents(repo, kp)
    tip = gitcmd.branch_commit(repo, str(binding.get("branch")))
    parent = parents[0] if parents and len(parents) == 1 else None
    use_check_head = mutation.note(NOTE_USE_CHECK_HEAD)
    if (
        gitcmd.current_branch_ref(repo) != binding.get("branch") or tip is None
        or gitcmd.descends_from(repo, tip, kp) is not True or parent is None
        or parent != kp_record["payload"].get("base_head")
        or not isinstance(use_check_head, str)
        or not (parent == use_check_head or (
            gitcmd.descends_from(repo, parent, use_check_head) is True
            and gitcmd.commits_touching(repo, use_check_head, parent, _planning_owned(run, chain, material)) == []
        ))
    ):
        raise _proof_failed("P2", "the branch, parent or lineage of the registration commit is not the recorded one")
    context = ReviewStore(store).read_task_input(str(chain.generations[0].accepted_tasks[0]["task_id"])).request_envelope.get("context")
    try:
        expected = expected_projection(store, material, context, parent)
    except ExpectedUnavailable as exc:
        raise _proof_failed("P3", f"the expected physical projection is unavailable: {exc}") from exc
    problem = delta_problem(repo, expected, kp)
    if problem is not None:
        raise _proof_failed("P3", problem)
    problem = record_problem(mutation, expected, op.registration_stages)
    if problem is not None:
        raise _proof_failed("P4", problem)
    try:
        view_kp = committed_view(store, kp)
        view_p = committed_view(store, parent)
    except (CommittedReadError, ValidationError) as exc:
        raise _proof_failed("P5", f"the committed-result loader cannot read {kp} and {parent}: {exc}") from exc
    # P12 first among the semantic items: a declared-base difference is never reported as an R9 mismatch.
    found = _run_currency(op, mutation, run, chain, parent)
    if not found.current:
        raise _proof_failed("P12", f"the authorized pre-state does not hold on {parent}: {found.detail}")
    third = chain.generation(planning.SEAL_GENERATION)
    for name, wanted in (
        ("operation_identity", op.operation_identity), ("target_identity", candidate_target(material)),
        ("review_kind", op.kind.review_kind), ("authorized_operation_stage", op.kind.authorized_operation_stage),
    ):
        if getattr(third, name) != wanted:
            raise _proof_failed("P12", f"the Receipt's {name} is not the recomputed one")
    try:
        at_parent = review_committed.CommittedReviewStore(repo, parent)
        wanted = _run_record_bytes(op, run, chain)
        for relative, data in wanted.items():
            if at_parent.read_bytes(relative) != data or at_parent.blob_id(relative) is None:
                raise _proof_failed("P12", f"{parent} does not hold {relative} with its canonical bytes")
        if at_parent.entry(review_paths.gate_rel(run.review_run_id, 4)) is not None or at_parent.supersession_exists(str(run.receipt_id)):
            raise _proof_failed("P12", f"{parent} holds an invalidation of the Receipt")
        if any(found_consumption.receipt_id == run.receipt_id for found_consumption in at_parent.consumptions()):
            raise _proof_failed("P12", f"{parent} holds a Consumption of the Receipt")
    except ValidationError as exc:
        raise _proof_failed("P12", str(exc)) from exc
    failed = semantic_problem(material, view_p, view_kp)
    if failed is not None:
        raise _proof_failed(*failed)
    if not isinstance(context, dict) or context.get("loader_identity") != planning.context_record(
        store.workline_root(), material["review_kind"]
    )["loader_identity"] or context.get("adapter_identity") != planning.KINDS[material["review_kind"]].adapter_identity:
        raise _proof_failed("P10", "the loader or adapter identity is not the Context's")
    if any(effect.get("kind") == "git_push" for effect in mutation.effects):
        raise _proof_failed("P11", "the planning mutation holds a push before its Consumption")
    return kp, parent


def _consumption_record(
    op: _Op, mutation: Mutation, run: _Run, chain: Any, material: dict[str, Any], kp: str, parent: str
) -> records.PlanningConsumption:
    store = op.store
    first = chain.generations[0]
    context = ReviewStore(store).read_task_input(str(first.accepted_tasks[0]["task_id"])).request_envelope.get("context") or {}
    expected = expected_projection(store, material, context, parent)
    view_kp = committed_view(store, kp)
    claims = persisted_result_claims(
        material, first.operation_identity, kp, parent, expected, selected_first_work_id(material, view_kp), context
    )
    claims["branch"] = (mutation.note(NOTE_BINDING) or {}).get("branch")
    return records.PlanningConsumption(
        consumption_id=str(run.consumption_id), receipt_id=str(run.receipt_id), review_run_id=run.review_run_id,
        review_generation=planning.SEAL_GENERATION, review_kind=first.review_kind,
        authorized_candidate_hash=first.candidate_hash, operation_identity=first.operation_identity,
        operation_mutation_id=mutation.id, target_identity=first.target_identity,
        persisted_result=serialize.canonical_data(claims),
    )


def _metadata_failed(item: str, detail: str) -> ReconcileRequired:
    return _reconcile(f"C-2(Km) {item} fails: {detail}", "review_metadata_commit_mismatch")


def _c2_km(op: _Op, mutation: Mutation, run: _Run, chain: Any, material: dict[str, Any], kp: str) -> str:
    """C-2(Km), M1-M6: Km is this mutation's own commit of exactly the Consumption, and CP proves the Run for Km."""
    from .review import committed as review_committed
    from .review import publication

    store = op.store
    repo = store.root
    km_records = mutation.stage_effects(STAGE_KM)
    km_record = km_records[0] if km_records else {}
    if km_record.get("applied") is not True:
        raise _metadata_failed("M1", "the metadata commit is not recorded applied")
    km = km_record.get("commit_id")
    if not gitcmd.full_commit_id(km):
        raise _reconcile(
            "the metadata commit is recorded applied without the ID of a commit this mutation made", "review_commit_unowned"
        )
    parents = gitcmd.commit_parents(repo, km)
    q = parents[0] if parents and len(parents) == 1 else None
    if q is None or not (q == kp or (
        gitcmd.descends_from(repo, q, kp) is True
        and gitcmd.commits_touching(repo, kp, q, _planning_owned(run, chain, material)) == []
    )):
        raise _metadata_failed("M1", "the metadata commit's parent is not the registration commit or its clean descendant")
    binding = mutation.note(NOTE_BINDING) or {}
    tip = gitcmd.branch_commit(repo, str(binding.get("branch")))
    if gitcmd.current_branch_ref(repo) != binding.get("branch") or tip is None or gitcmd.descends_from(repo, tip, km) is not True:
        raise _metadata_failed("M2", "HEAD is not on the bound branch, or the branch does not hold the metadata commit")
    consumption_path = review_paths.consumption_rel(str(run.consumption_id))
    recorded = mutation.stage_effects(STAGE_CONSUMPTION)
    content = recorded[0]["payload"]["content"].encode("utf-8") if recorded else b""
    delta = gitcmd.commit_delta(repo, q, km)
    blob = None if not delta else gitcmd.read_blob(repo, delta[0].new_blob)
    if not delta or len(delta) != 1 or delta[0].path != consumption_path or delta[0].status != "A" \
            or delta[0].new_mode != "100644" or blob != content:
        raise _metadata_failed("M3", "the metadata commit is not exactly the added Consumption with its recorded bytes")
    try:
        at_km = review_committed.CommittedReviewStore(repo, km)
        for relative, data in _run_record_bytes(op, run, chain).items():
            if at_km.read_bytes(relative) != data:
                raise _metadata_failed("M4", f"{km} does not hold {relative} with its canonical bytes")
        if at_km.read_bytes(consumption_path) != content:
            raise _metadata_failed("M4", f"{km} does not hold the Consumption with its canonical bytes")
        if at_km.entry(review_paths.gate_rel(run.review_run_id, 4)) is not None or at_km.supersession_exists(str(run.receipt_id)):
            raise _metadata_failed("M4", f"{km} holds an invalidation of the Receipt")
        kp_entries = gitcmd.tree_entries(repo, kp, registration_paths(material))
        km_entries = gitcmd.tree_entries(repo, km, registration_paths(material))
        if kp_entries is None or km_entries is None or {e.path: e.oid for e in kp_entries} != {e.path: e.oid for e in km_entries}:
            raise _metadata_failed("M4", f"{km}'s registration paths are not the registration commit's")
        consumption = at_km.read_consumption(str(run.consumption_id))
    except ValidationError as exc:
        raise _metadata_failed("M4", str(exc)) from exc
    if not isinstance(consumption, records.PlanningConsumption) or consumption.receipt_id != run.receipt_id \
            or consumption.registration_commit != kp:
        raise _metadata_failed("M5", "the Consumption does not bind the Receipt and the registration commit")
    runs = [found for found in publication.registered_runs(repo, km) if found.candidate_hash == planning.candidate_hash(material)]
    if len(runs) != 1:
        raise _metadata_failed("M6", "the committed objects do not show this Run's registration")
    failed = publication.committed_planning_proof(repo, km, runs[0])
    if failed is not None:
        raise _metadata_failed("M6", f"the committed planning proof fails {failed[0]} ({failed[1]})")
    return str(km)


# --------------------------------------------------------------------------- terminal outcomes

def _finish(
    op: _Op,
    mutation: Mutation,
    run: _Run,
    status: str,
    *,
    detail: str,
    receipt_id: str | None = None,
    consumption_id: str | None = None,
    registration: Any = None,
    chain: Any = None,
) -> ReviewedPlanningResult:
    """Complete the planning mutation and say how the review-v1 invocation ended."""
    if status != STATUS_REGISTERED and mutation.effects:
        raise _reconcile(f"the planning mutation {mutation.id} holds effects and cannot end {status}", "review_chain_invalid")
    mutation.complete()
    try:
        current = chain if chain is not None else ReviewStore(op.store).gate_chain(run.review_run_id)
    except ValidationError:
        current = None
    findings = () if current is None else _findings(op, current)
    if _is_recovery(mutation):
        detail = f"{detail}; recovered Run {run.review_run_id}"
    return ReviewedPlanningResult(
        status=status, operation=op.operation, mutation_id=mutation.id, review_run_id=run.review_run_id,
        receipt_id=receipt_id, consumption_id=consumption_id, registration=registration, findings=findings, detail=detail,
    )
