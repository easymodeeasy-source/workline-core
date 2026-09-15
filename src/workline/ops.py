"""Helpers shared by operation owners (Roadmap / START / CREATE direct).

* event effect construction with mutation-stable IDs;
* replan payloads (relation removal / addition / new Works) with projected
  structural validation before any physical write;
* owned canonical path computation from recorded effects;
* the resume of an interrupted plan exclusion, which Roadmap (Phase / Work) and
  START (standalone Work) share, and whose record checks a resumed START cancel
  reuses.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
from typing import Any, Callable, Iterable

from . import gitops
from .create import RelationSpec, WorkSpec, _check_registration, _registration_effects, register_works, resolve_ref
from .errors import ReconcileRequired, SpecViolation, StopError, ValidationError
from .ids import is_valid_id, new_id
from .mutation import (
    FILE_EFFECT_KINDS,
    MISMATCH,
    UNAPPLIED,
    Effect,
    Mutation,
    MutationController,
    pending_for_slot,
    require_same_request,
    utc_now,
)
from .state import ProjectView
from .store import WORK_DESIRED_HEADING, WORKLINE_DIR, Entity, Event, ProjectStore, Relation, render_body
from .validate import Problem, validate_structure


def new_event(mutation: Mutation, key: str, event_type: str, entity_id: str) -> Event:
    return Event(mutation.reserve_id(key, "event"), event_type, entity_id, utc_now())


def event_effects(mutation: Mutation, stage: str, entity_id: str, types: list[str]) -> list[Effect]:
    return [Effect.append_event(new_event(mutation, f"{stage}:event:{index}", t, entity_id)) for index, t in enumerate(types)]


def stage_name(mutation: Mutation, prefix: str) -> str:
    """Unique stage name ``<prefix>:<n>`` based on stages already recorded."""
    count = len({e["stage"] for e in mutation.effects if str(e["stage"]).startswith(prefix + ":")})
    return f"{prefix}:{count}"


def owned_canonical_paths(mutation: Mutation) -> list[str]:
    """Canonical paths touched by the mutation's recorded effects."""
    return _owned_paths(mutation.effects)


def _owned_paths(effects: Iterable[dict[str, Any] | Effect]) -> list[str]:
    """Canonical paths the effects - recorded, or about to be - write."""
    paths: set[str] = set()
    for effect in effects:
        kind, payload = (effect["kind"], effect["payload"]) if isinstance(effect, dict) else (effect.kind, effect.payload)
        if kind == "write_file":
            paths.add(payload["path"])
        elif kind in ("add_relation", "remove_relation"):
            paths.add(f"{WORKLINE_DIR}/relations/{payload['file']}.yaml")
        elif kind == "append_event":
            paths.add(f"{WORKLINE_DIR}/events/events.jsonl")
    return sorted(paths)


# --------------------------------------------------------------------------- replan

@dataclass(frozen=True)
class Replan:
    """Operation-owner decided future-plan changes accompanying cancel / plan exclusion."""

    remove_relation_ids: tuple[str, ...] = ()
    add_relations: tuple[RelationSpec, ...] = ()
    new_works: dict[str, WorkSpec] = field(default_factory=dict)


def projected_view(
    view: ProjectView,
    *,
    add_events: list[tuple[str, str]] = (),
    remove_relation_ids: tuple[str, ...] = (),
    add_relations: list[Relation] = (),
    add_works: dict[str, WorkSpec] | None = None,
    remove_related_ids: tuple[str, ...] = (),
    add_related: list[Relation] = (),
) -> ProjectView:
    """In-memory projection of ``view`` after the planned changes."""
    projected = ProjectView(view.store)
    projected.works = dict(view.works)
    projected.phases = dict(view.phases)
    projected.roadmaps = dict(view.roadmaps)
    projected.related = [r for r in view.related if r.id not in remove_related_ids] + list(add_related)
    projected.roadmap_relations = [r for r in view.roadmap_relations if r.id not in remove_relation_ids] + list(add_relations)
    projected.events = list(view.events) + [Event(f"evt_{'0' * 26}", t, e, utc_now()) for e, t in add_events]
    for work_id, spec in (add_works or {}).items():
        meta: dict[str, Any] = {"id": work_id, "display": "W-??", "type": "work"}
        if spec.phase_id is not None:
            meta["phase_id"] = spec.phase_id
            meta["origin"] = {"type": "roadmap", "roadmap_id": spec.roadmap_id, "phase_id": spec.phase_id}
        else:
            meta["origin"] = {"type": "standalone"}
        if spec.work_kind is not None:
            meta["work_kind"] = spec.work_kind
        body = render_body(spec.name, [(WORK_DESIRED_HEADING, spec.desired_state)])
        projected.works[work_id] = Entity(work_id, "work", meta, body, ProjectStore.entity_rel_path("work", work_id))
    return projected


def validate_projection(view: ProjectView, context: str, *, ignore_placeholder_events: bool = True) -> None:
    problems = [
        p for p in validate_structure(view)
        if not (ignore_placeholder_events and p.code == "event_invalid" and "duplicate event id: evt_0" in p.message)
    ]
    if problems:
        raise SpecViolation(f"{context}: structure would be invalid: " + "; ".join(p.message for p in problems))


def plan_replan(
    mutation: Mutation,
    prefix: str,
    view: ProjectView,
    replan: Replan,
) -> tuple[dict[str, str], list[Relation], list[Relation]]:
    """Reserve IDs and resolve a replan into (new work ids, removals, additions)."""
    removals = _resolve_removals(view, replan)
    work_ids = {key: mutation.reserve_id(f"{prefix}:works:work:{key}", "work") for key in replan.new_works}
    additions: list[Relation] = []
    relation_stage = f"{prefix}:works" if replan.new_works else f"{prefix}:relations"
    for index, spec in enumerate(replan.add_relations):
        relation_id = mutation.reserve_id(f"{relation_stage}:rel:{index}", "relation")
        additions.append(Relation(relation_id, spec.type, resolve_ref(spec.from_ref, work_ids), resolve_ref(spec.to_ref, work_ids)))
    return work_ids, removals, additions


def _resolve_removals(view: ProjectView, replan: Replan) -> list[Relation]:
    """The Roadmap relations a replan removes, as ``view`` holds them, or the refusal."""
    removals: list[Relation] = []
    existing = {r.id: r for r in view.roadmap_relations}
    for relation_id in replan.remove_relation_ids:
        relation = existing.get(relation_id)
        if relation is None:
            raise ValidationError(f"replan: relation {relation_id} unresolvable")
        if relation.type == "derived":
            raise SpecViolation("replan: derived relations are historical facts and cannot be removed")
        removals.append(relation)
    return removals


def apply_replan(
    mutation: Mutation,
    prefix: str,
    replan: Replan,
    removals: list[Relation],
    additions: list[Relation],
    work_ids: dict[str, str],
) -> list[str]:
    """Record and apply replan effects. Returns touched canonical paths."""
    touched: list[str] = []
    works = f"{prefix}:works"
    if replan.new_works and mutation.has_stage(works):
        # Only a resumed plan exclusion (:func:`_resume_plan_exclusion`) or START
        # cancel (``start._cancel_to_finish``) gets here: its resume showed the
        # recorded stage is the registration its request or its recorded decision
        # makes, and has replayed it. Registering it again would validate Works that
        # now exist and count a recorded integration twice, so the stage is read
        # back instead: its reservations give the Work IDs, its effects the paths.
        if {key: mutation.reserved(f"{works}:work:{key}") for key in replan.new_works} != work_ids:
            raise ValidationError("replan: reserved Work IDs diverged")
        touched.extend(_owned_paths(mutation.stage_effects(works)))
    elif replan.new_works:
        # The owner projected the whole replan - its event, removals, additions
        # and new Works - before recording any of it. Registration here is one
        # step of applying that, so the registration keeps its apply-then-
        # postcheck order on this path. It is taken before the removals, which
        # are already decided and are recorded and applied only after it: its
        # structure checks leave them out, so they judge the structure this
        # replan leaves instead of refusing the moment in between, while a
        # registration refused for anything else never leaves a removal applied.
        result = register_works(
            mutation,
            works,
            replan.new_works,
            list(replan.add_relations),
            refuse_before_apply=False,
            removed_after=tuple(r.id for r in removals),
        )
        touched.extend(result.paths)
        if result.work_ids != work_ids:
            raise ValidationError("replan: reserved Work IDs diverged")
    elif additions:
        stage = f"{prefix}:relations"
        if not mutation.has_stage(stage):
            mutation.add_effects(stage, [Effect.add_relation("roadmap", r) for r in additions])
        mutation.apply()
        touched.append(f"{WORKLINE_DIR}/relations/roadmap.yaml")
    if removals:
        stage = f"{prefix}:remove"
        if not mutation.has_stage(stage):
            mutation.add_effects(stage, [Effect.remove_relation("roadmap", r) for r in removals])
        mutation.apply()
        touched.append(f"{WORKLINE_DIR}/relations/roadmap.yaml")
    return touched


def problems_text(problems: list[Problem]) -> str:
    return "; ".join(f"{p.code}: {p.message}" for p in problems)


# --------------------------------------------------------------------------- plan exclusion resume
#
# A plan exclusion - Roadmap's of a Phase or a Phase Work, START's of a
# standalone Work - records its ``plan_excluded`` event and then applies its
# replan: the new Works with the relations they carry, the removals, the commit
# and the push. Once that event was applied, a retry read the Project with the
# exclusion (and whatever of the replan followed it) already in it and refused
# itself, so nothing could finish the mutation.
#
# The request - the target and its replan - is bound to the mutation before the
# first ID is reserved. An unfinished mutation of the slot is continued only by
# that same request, and only when its record shows it is that request's own; the
# request is then decided on the Project without the effects the mutation already
# applied, and everything still to come is checked before anything recorded is
# replayed. Where the retry may replay and record is not decided here: the
# Mutation Controller allows it only where the recorded decision was made, and
# the recorded commit's own branch rules from its Git stage on (``rules/git``:
# Commit / push). START's own resume of a Work it finalizes or cancelled
# (``start._completion_to_finish``, ``start._cancel_to_finish``) reads only
# START's invocation, which a plan exclusion never shares.

_PLAN_EXCLUSION_REQUEST_VERSION = 1

# The stages a plan exclusion records, as its owners name them.
_EVENT_STAGE = "event"
_REPLAN = "replan"
_FINALIZE_STAGE = "finalize"


def _plan_exclusion_request(target: str, replan: Replan) -> dict[str, Any]:
    """What a plan exclusion decided, in the form its mutation records.

    Operation and target say what is excluded, not how the plan is changed around
    it, so a mutation identified by them alone can be continued by a retry that
    decided another replan - and then report success while the Project keeps the
    first replan, or a mix of both. The replan therefore travels in the
    invocation, which ``MutationController.begin`` makes durable before a single
    ID is reserved.

    Normalised to what is written, by the rules the other request identities use:
    a Work's desired state and derivation detail are stripped because rendering
    strips them, and an absent derivation detail stays distinct from an empty one;
    names, IDs, kinds, confirmation targets, Related edges and relation endpoints
    are kept exactly as the caller wrote them - an endpoint naming a new Work's key
    and one naming the ID that key was reserved as are two requests, because this
    identity is fixed before any ID exists. Declared order is kept everywhere: it
    decides the Works' display numbers and which reservation each Work and
    relation gets.

    It says what was decided, not where: the branch a decision is finalized on is
    recorded by the Mutation Controller with the decided effects themselves.
    """
    return {
        "version": _PLAN_EXCLUSION_REQUEST_VERSION,
        "target": target,
        "new_works": [
            {
                "key": key,
                "name": spec.name,
                "desired_state": _stripped(spec.desired_state),
                "phase_id": spec.phase_id,
                "roadmap_id": spec.roadmap_id,
                "work_kind": spec.work_kind,
                "confirmation_target": spec.confirmation_target,
                "related": [{"type": r.type, "to": r.to, "condition": r.condition} for r in spec.related],
                "derivation_detail": None if spec.derivation_detail is None else _stripped(spec.derivation_detail),
            }
            for key, spec in replan.new_works.items()
        ],
        "add_relations": [{"type": r.type, "from": r.from_ref, "to": r.to_ref} for r in replan.add_relations],
        "remove_relation_ids": list(replan.remove_relation_ids),
    }


def _stripped(text: object) -> object:
    """Stripped the way rendering strips it; a value that is not text is left for validation to refuse where it did."""
    return text.strip() if isinstance(text, str) else text


@dataclass(frozen=True)
class _ResumedPlanExclusion:
    """An interrupted plan exclusion shown to be this request's own, and what it decided."""

    view: ProjectView  # the Project without the effects the mutation applied: what the request is decided on
    work_ids: dict[str, str]
    removals: list[Relation]
    additions: list[Relation]


def _resume_plan_exclusion(
    store: ProjectStore,
    owner: str,
    slot: dict[str, Any],
    target: str,
    replan: Replan,
    request: dict[str, Any],
    precheck: Callable[[ProjectView], None],
    message: Callable[[ProjectView], str],
) -> _ResumedPlanExclusion | None:
    """Decide how the unfinished plan exclusion of ``slot`` is continued, writing nothing.

    ``slot`` names the operation and its target, so only a plan exclusion of that
    target is looked at - never another operation of the same owner, such as a
    START of the same Work. ``None`` leaves the request to its owner's first
    attempt: there is no unfinished mutation; or it recorded no stage yet, so it
    applied nothing and the current state is still the one the request is decided
    on - only its reservations have to be this request's; or the recovery area
    cannot be read, which proves nothing and is reported where it always was, when
    the mutation is opened.

    Otherwise every step reads only, and whatever refuses leaves the record, the
    Project and Git exactly as they are:

    1. a record written before plan exclusions recorded their request, several
       records, or the record of another request - ``reconcile required``;
    2. :func:`_prove_plan_exclusion` - the record holds exactly what this request
       records, and what it applied is consistent with the order it records in;
    3. :func:`_decide_plan_exclusion` - the request decided again, as its owner
       decides it, on the Project without the effects the mutation applied;
    4. :func:`_refuse_before_replay` - what is still to come refused the way
       recording and applying it would refuse, before any of it runs.
    """
    described = f"plan exclusion of {target}"
    try:
        pending = pending_for_slot(store, owner, slot)
    except ReconcileRequired:
        return None
    if not pending:
        return None
    require_same_request(pending, request, described)
    (record,) = pending
    refuse = _refusal(record, described)
    if not record.get("effects"):
        _proven_reservations(record, replan, refuse)
        return None
    proven = _prove_plan_exclusion(store, record, target, replan, refuse)
    view, removals = _decide_plan_exclusion(proven, target, replan, precheck, message, refuse)
    _refuse_before_replay(store, owner, record, proven, replan, removals)
    return _ResumedPlanExclusion(view, proven.work_ids, removals, proven.additions)


def _refusal(record: dict[str, Any], described: str) -> Callable[[str], ReconcileRequired]:
    def refuse(reason: str) -> ReconcileRequired:
        return ReconcileRequired(
            f"the unfinished {described} {record['mutation_id']} was recorded for this request, but its record holds "
            f"{reason}; nothing shows that continuing it carries out this request, and it is left untouched: "
            "reconcile required"
        )

    return refuse


def _plan_exclusion_stages(replan: Replan) -> list[str]:
    """The stages this request records, in the order it records them."""
    stages = [_EVENT_STAGE]
    if replan.new_works:
        stages.append(f"{_REPLAN}:works")
    elif replan.add_relations:
        stages.append(f"{_REPLAN}:relations")
    if replan.remove_relation_ids:
        stages.append(f"{_REPLAN}:remove")
    stages.append(_FINALIZE_STAGE)
    return stages


def _plan_exclusion_reservations(replan: Replan) -> tuple[dict[str, str], dict[str, str]]:
    """The reservation keys this request makes, with the kind of ID each holds.

    The first set is reserved before the event is recorded - the replan's Works
    and relations, then the event; the second only by the registration core,
    right before it records its stage - the new Works' Related edges and
    derivation details.
    """
    before_event = {f"{_REPLAN}:works:work:{key}": "work" for key in replan.new_works}
    relation_stage = f"{_REPLAN}:works" if replan.new_works else f"{_REPLAN}:relations"
    before_event.update({f"{relation_stage}:rel:{index}": "relation" for index in range(len(replan.add_relations))})
    before_event[f"{_EVENT_STAGE}:event:0"] = "event"
    registration: dict[str, str] = {}
    for key, spec in replan.new_works.items():
        registration.update({f"{_REPLAN}:works:related:{key}:{index}": "relation" for index in range(len(spec.related))})
        if spec.derivation_detail is not None:
            registration[f"{_REPLAN}:works:der:{key}"] = "derivation"
    return before_event, registration


def _proven_reservations(record: dict[str, Any], replan: Replan, refuse) -> dict[str, str]:
    """The record's reservations, when each is a key this request reserves, holding a distinct ID of its kind."""
    before_event, registration = _plan_exclusion_reservations(replan)
    expected = {**before_event, **registration}
    reserved = record.get("reserved_ids") or {}
    if not isinstance(reserved, dict):
        raise refuse("reservations that are not a mapping")
    for key, value in reserved.items():
        if key not in expected:
            raise refuse(f"a reservation {key!r} this request never makes")
        if not isinstance(value, str) or not is_valid_id(value, expected[key]):
            raise refuse(f"reservation {key!r} holding {value!r}, which is not a {expected[key]} ID")
    if len(set(reserved.values())) != len(reserved):
        raise refuse("one ID reserved under two keys")
    return dict(reserved)


def _as_recorded(effects: Iterable[dict[str, Any] | Effect]) -> str:
    """Effects as a stage records what it decides - kind and payload, in order - in their canonical encoding.

    Where the stage was decided (``decided_on``) is the Mutation Controller's to
    record and to check; it is not part of what the request decided.
    """
    return json.dumps(
        [[e["kind"], e["payload"]] if isinstance(e, dict) else [e.kind, e.payload] for e in effects],
        sort_keys=True,
        ensure_ascii=False,
    )


@dataclass(frozen=True)
class _ProvenRecord:
    """What :func:`_prove_plan_exclusion` read out of a record, for the decision and the check before replay."""

    reserved: dict[str, str]
    effects: list[dict[str, Any]]
    by_stage: dict[str, list[dict[str, Any]]]
    current: ProjectView
    work_ids: dict[str, str]
    additions: list[Relation]
    recorded_removals: list[Relation] | None
    finalize: list[dict[str, Any]] | None
    file_effects: list[dict[str, Any]]
    applied: list[dict[str, Any]]
    unapplied: list[dict[str, Any]]


def _prove_plan_exclusion(
    store: ProjectStore, record: dict[str, Any], target: str, replan: Replan, refuse
) -> _ProvenRecord:
    """Show the record is this request's own: its reservations, stages, event, registration, removals, commit and progress."""
    before_event, registration_keys = _plan_exclusion_reservations(replan)
    reserved = _proven_reservations(record, replan, refuse)

    effects = record.get("effects") or []
    if not isinstance(effects, list) or not all(isinstance(effect, dict) for effect in effects):
        raise refuse("effects that cannot be read")
    stages = _recorded_stages(effects, refuse)
    order = _plan_exclusion_stages(replan)
    if stages != order[: len(stages)]:
        raise refuse(f"the stages {stages}, where this request records {order} in that order")
    if any(key not in reserved for key in before_event):
        raise refuse("a recorded stage without the reservations this request makes before recording one")
    works_stage, relations_stage, remove_stage = f"{_REPLAN}:works", f"{_REPLAN}:relations", f"{_REPLAN}:remove"
    if works_stage in stages and any(key not in reserved for key in registration_keys):
        raise refuse("a recorded registration without the reservations it makes")
    by_stage = {stage: [effect for effect in effects if effect.get("stage") == stage] for stage in stages}

    event_effect, *extra_events = by_stage[_EVENT_STAGE]
    payload = event_effect.get("payload")
    event = payload.get("record") if isinstance(payload, dict) else None
    if (
        extra_events
        or event_effect.get("kind") != "append_event"
        or set(payload or {}) != {"record"}
        or not isinstance(event, dict)
        or set(event) != {"id", "type", "entity", "at"}
        or event["id"] != reserved[f"{_EVENT_STAGE}:event:0"]
        or event["type"] != "plan_excluded"
        or event["entity"] != target
        or not isinstance(event["at"], str)
        or not event["at"]
    ):
        raise refuse(f"an event stage other than the one plan_excluded event of {target}")

    work_ids = {key: reserved[f"{_REPLAN}:works:work:{key}"] for key in replan.new_works}
    relation_stage = works_stage if replan.new_works else relations_stage
    additions = [
        Relation(reserved[f"{relation_stage}:rel:{index}"], spec.type, resolve_ref(spec.from_ref, work_ids), resolve_ref(spec.to_ref, work_ids))
        for index, spec in enumerate(replan.add_relations)
    ]
    current = ProjectView.load(store)
    if works_stage in by_stage:
        related_ids = {
            (key, index): reserved[f"{_REPLAN}:works:related:{key}:{index}"]
            for key, spec in replan.new_works.items()
            for index in range(len(spec.related))
        }
        derivation_ids = {
            key: reserved[f"{_REPLAN}:works:der:{key}"]
            for key, spec in replan.new_works.items()
            if spec.derivation_detail is not None
        }
        # The Works the Project held when the stage was recorded: while this mutation is pending, its new Works are the
        # only ones registered since.
        base_number = len(current.works) - sum(1 for work_id in work_ids.values() if work_id in current.works)
        expected = _registration_effects(replan.new_works, work_ids, additions, related_ids, derivation_ids, base_number)
        if _as_recorded(by_stage[works_stage]) != _as_recorded(expected):
            raise refuse(f"a {works_stage} stage other than the registration this request decides")
    if relations_stage in by_stage:
        if _as_recorded(by_stage[relations_stage]) != _as_recorded(Effect.add_relation("roadmap", r) for r in additions):
            raise refuse(f"a {relations_stage} stage other than the relations this request adds")
    recorded_removals: list[Relation] | None = None
    if remove_stage in by_stage:
        recorded_removals = []
        for effect in by_stage[remove_stage]:
            payload = effect.get("payload")
            relation = payload.get("record") if isinstance(payload, dict) else None
            if (
                effect.get("kind") != "remove_relation"
                or set(payload or {}) != {"file", "record"}
                or payload.get("file") != "roadmap"
                or not isinstance(relation, dict)
                or not all(isinstance(relation.get(part), str) and relation[part] for part in ("id", "type", "from", "to"))
                or relation["type"] == "derived"
            ):
                raise refuse(f"a {remove_stage} stage holding something other than Roadmap relation removals")
            recorded_removals.append(Relation.from_record(relation))
        if [relation.id for relation in recorded_removals] != list(replan.remove_relation_ids):
            raise refuse(f"a {remove_stage} stage removing other relations than this request, or in another order")
    file_effects = [effect for effect in effects if effect.get("kind") in FILE_EFFECT_KINDS]
    finalize = by_stage.get(_FINALIZE_STAGE)
    if finalize is not None:
        # Only the kinds, the paths and (once the target is known to exist, in the decision) the message are this
        # request's; the base, the branch and the push destination are the Mutation Controller's to classify.
        kinds = [effect.get("kind") for effect in finalize]
        commit = finalize[0].get("payload")
        if (
            kinds not in (["git_commit"], ["git_commit", "git_push"])
            or not isinstance(commit, dict)
            or commit.get("paths") != _owned_paths(file_effects)
        ):
            raise refuse("a finalization other than the commit of the paths this mutation writes")

    applied, unapplied = _recorded_progress(store, file_effects, stages[-1], finalize is not None, refuse)
    return _ProvenRecord(
        reserved, effects, by_stage, current, work_ids, additions, recorded_removals, finalize, file_effects, applied,
        unapplied,
    )


def _recorded_stages(effects: list[dict[str, Any]], refuse) -> list[str]:
    """The stages ``effects`` record, in the order they were recorded, when each is recorded in one place."""
    stages: list[str] = []
    for effect in effects:
        stage = effect.get("stage")
        if stages and stages[-1] == stage:
            continue
        if stage in stages:
            raise refuse(f"stage {stage!r} recorded in two places")
        stages.append(stage)
    return stages


def _recorded_progress(
    store: ProjectStore, file_effects: list[dict[str, Any]], last_stage: object, committed: bool, refuse
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The recorded file effects the Project holds and the ones still to apply, when they show the order they were recorded in.

    Each is classified as replaying it would classify it, with nothing written.
    """
    controller = MutationController(store)
    applied: list[dict[str, Any]] = []
    unapplied: list[dict[str, Any]] = []
    for effect in file_effects:
        try:
            classification = controller.classify(effect)
        except (KeyError, TypeError, AttributeError, ValueError, OSError, StopError) as exc:
            raise refuse(f"effect {effect.get('seq')} ({effect.get('kind')}) that cannot be classified ({exc})") from exc
        if classification == MISMATCH:
            raise refuse(f"effect {effect.get('seq')} ({effect['kind']}) applied with an unexpected result")
        if classification == UNAPPLIED:
            unapplied.append(effect)
        elif unapplied:
            raise refuse(f"effect {effect.get('seq')} ({effect['kind']}) applied while an earlier one is not")
        else:
            applied.append(effect)
    # A stage is recorded only once every stage before it is applied, so what is still to apply can only belong to the
    # last stage recorded - never to a stage another one follows, and never once the commit is recorded.
    if unapplied and (committed or {effect.get("stage") for effect in unapplied} != {last_stage}):
        raise refuse(
            f"effect {unapplied[0].get('seq')} ({unapplied[0]['kind']}) of stage {unapplied[0].get('stage')!r} not "
            "applied although a later stage is recorded"
        )
    return applied, unapplied


def _decide_plan_exclusion(
    proven: _ProvenRecord,
    target: str,
    replan: Replan,
    precheck: Callable[[ProjectView], None],
    message: Callable[[ProjectView], str],
    refuse,
) -> tuple[ProjectView, list[Relation]]:
    """The request decided again as its owner decides it, on the Project without this mutation's own applied effects.

    The owner's structure precheck and precondition, the commit message, the
    removals and the projection of the whole replan read that Project - the one
    the request met - so the mutation's own event, Works, additions and removals
    are neither held against it nor counted twice. Removals already recorded are
    taken from their stage: the relations they name are gone from the Project,
    and resolving them again would find nothing.
    """
    view = _own_effects_free_view(proven.current, proven.applied)
    problems = validate_structure(view)
    if problems:
        raise ValidationError(f"precheck: {problems_text(problems)}", code="structure_invalid")
    precheck(view)
    if proven.finalize is not None and proven.finalize[0]["payload"].get("message") != message(view):
        raise refuse("a finalization other than the commit this request makes")
    removals = proven.recorded_removals if proven.recorded_removals is not None else _resolve_removals(view, replan)
    validate_projection(
        projected_view(
            view,
            add_events=[(target, "plan_excluded")],
            remove_relation_ids=tuple(relation.id for relation in removals),
            add_relations=proven.additions,
            add_works={proven.work_ids[key]: spec for key, spec in replan.new_works.items()},
        ),
        "plan exclusion replan",
    )
    return view, removals


def _own_effects_free_view(view: ProjectView, applied: list[dict[str, Any]]) -> ProjectView:
    """``view`` without the file effects one mutation applied, with nothing written.

    Each effect is taken back the way applying it changed what the store reads:
    an appended event is left out by its ID, an added relation by its ID, a newly
    written entity file is left out, and a removed relation is put back from the
    snapshot its removal recorded. The caller has shown that the effects are the
    mutation's own and all it applied.
    """
    events: set[str] = set()
    added: dict[str, set[str]] = {"roadmap": set(), "related": set()}
    removed: dict[str, list[Relation]] = {"roadmap": [], "related": []}
    written: set[str] = set()
    for effect in applied:
        kind, payload = effect["kind"], effect["payload"]
        if kind == "append_event":
            events.add(payload["record"]["id"])
        elif kind == "add_relation":
            added[payload["file"]].add(payload["record"]["id"])
        elif kind == "remove_relation":
            # A request may name one relation twice; the second removal found it gone and wrote nothing.
            if payload["record"]["id"] not in {relation.id for relation in removed[payload["file"]]}:
                removed[payload["file"]].append(Relation.from_record(payload["record"]))
        elif kind == "write_file":
            written.add(payload["path"])
    return replace(
        view,
        works={work_id: work for work_id, work in view.works.items() if work.path not in written},
        phases={phase_id: phase for phase_id, phase in view.phases.items() if phase.path not in written},
        roadmaps={roadmap_id: roadmap for roadmap_id, roadmap in view.roadmaps.items() if roadmap.path not in written},
        roadmap_relations=[r for r in view.roadmap_relations if r.id not in added["roadmap"]] + removed["roadmap"],
        related=[r for r in view.related if r.id not in added["related"]] + removed["related"],
        events=[e for e in view.events if e.id not in events],
    )


def _refuse_before_replay(
    store: ProjectStore,
    owner: str,
    record: dict[str, Any],
    proven: _ProvenRecord,
    replan: Replan,
    removals: list[Relation],
    *,
    prefix: str = _REPLAN,
    context: str = "plan exclusion replan",
    committing: list[dict[str, Any]] | None = None,
) -> None:
    """Refuse, before any recorded effect is replayed, what the rest of the resume would refuse once it had.

    What is still to come is the recorded effects not applied yet and the stages
    not recorded yet. The registration is checked the way the registration core
    checks it before recording, on the Project it would meet; every effect still
    to be recorded is validated the way recording validates it; the Project all
    of them leave is checked by the structure rule the finalization's postcheck
    applies; and, while the commit is not recorded, its separation from changes
    that were there before the operation. Each refusal is the one recording or
    applying would have made, only before anything is written.

    ``prefix`` names the replan's stages, ``context`` the change the structure
    refusal reports, and ``committing`` the recorded effects whose files the
    commit carries - by default every file effect of the record, which a plan
    exclusion's mutation holds alone. A START cancel shares its mutation with
    what START finalized before it (``start._cancel_to_finish``).
    """
    works_stage, relations_stage, remove_stage = f"{prefix}:works", f"{prefix}:relations", f"{prefix}:remove"
    future: list[Effect] = []
    if replan.new_works and works_stage not in proven.by_stage:
        # The registration meets the Project once the recorded effects are applied.
        at_registration = proven.current.with_effects(proven.unapplied)
        relation_ids = {index: relation.id for index, relation in enumerate(proven.additions)}
        resolved = _check_registration(
            at_registration,
            replan.new_works,
            list(replan.add_relations),
            proven.work_ids,
            relation_ids,
            tuple(relation.id for relation in removals),
        )
        # IDs the registration reserves only right before it records: any unused ID of the kind stands in for them.
        related_ids = {
            (key, index): proven.reserved.get(f"{works_stage}:related:{key}:{index}") or new_id("relation")
            for key, spec in replan.new_works.items()
            for index in range(len(spec.related))
        }
        derivation_ids = {
            key: proven.reserved.get(f"{works_stage}:der:{key}") or new_id("derivation")
            for key, spec in replan.new_works.items()
            if spec.derivation_detail is not None
        }
        future += _registration_effects(
            replan.new_works, proven.work_ids, resolved, related_ids, derivation_ids, len(at_registration.works)
        )
    elif proven.additions and not replan.new_works and relations_stage not in proven.by_stage:
        future += [Effect.add_relation("roadmap", relation) for relation in proven.additions]
    if removals and remove_stage not in proven.by_stage:
        future += [Effect.remove_relation("roadmap", relation) for relation in removals]
    controller = MutationController(store)
    previous = list(proven.effects)
    for effect in future:
        candidate = {"seq": 0, "stage": "-", "kind": effect.kind, "payload": effect.payload, "applied": False}
        controller.validate_effect(candidate, previous, owner)
        previous.append(candidate)
    left = proven.current.with_effects(list(proven.unapplied) + future)
    validate_projection(left, context, ignore_placeholder_events=False)
    if proven.finalize is None:
        noted = (record.get("notes") or {}).get("preexisting_dirty")
        preexisting = list(noted) if isinstance(noted, list) else gitops.preexisting_dirty_snapshot(store.root)
        committed = proven.file_effects if committing is None else committing
        gitops.ensure_separable(preexisting, _owned_paths(list(committed) + future))
