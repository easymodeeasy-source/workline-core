"""START (``skills/start``): execute a registered Work to the requested boundary.

START is the operation owner for Work execution: dependency checks,
target / lifecycle events, derived / fix Work creation through CREATE,
integration and human_confirmation handling, cancel with replan, Git
persistence and terminal finalization, and same-Phase continuation in
``outer`` mode. START never crosses into the next Phase.

The actual domain work (and every domain judgement: what to derive, whether
the result is acceptable, ...) is supplied by an ``executor`` callable that
receives an ``ExecutionContext`` and returns an outcome object. START owns
the mechanics: it does not invent Works, relations or integrations beyond
the structural rules the live specification assigns to it.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import os
import stat
from typing import Any, Callable

from . import gitcmd, gitops, yamlish
from .create import RelatedSpec, RelationSpec, WorkSpec, register_works, resolve_ref
from .errors import ReconcileRequired, SpecViolation, StopError, ValidationError
from .ids import is_valid_id
from .mutation import FILE_EFFECT_KINDS, Effect, Mutation, MutationController, WriteScope, _decides, abandon_on_stop
from .oplock import project_operation
from .ops import (
    Replan,
    _as_recorded,
    _own_effects_free_view,
    _owned_paths,
    _plan_exclusion_ledgers,
    _plan_exclusion_request,
    _ProvenRecord,
    _recorded_progress,
    _recorded_stages,
    _refuse_before_replay,
    _registration_matches,
    _resume_plan_exclusion,
    apply_replan,
    event_effects,
    owned_canonical_paths,
    plan_replan,
    problems_text,
    projected_view,
    stage_name,
    validate_projection,
)
from .registry import validate_registry
from .state import (
    ACTIVE,
    AMBIGUOUS_CANDIDATES,
    COMPLETED,
    HELD,
    IN_PROGRESS,
    UNSTARTED,
    ProjectView,
    WorkState,
)
from .store import WORK_TERMINAL_EVENTS, WORKLINE_DIR, Entity, ProjectStore, Relation
from .validate import condition_applies, validate_structure

OWNER = "start"
MODES = ("single-work", "outer")
# What a Work refused for a result path of its own carries until it is run again
# (``skills/start``: Work result). One refused Work's own result, kept so that the
# retry after the person resolves their change does not run the executor over
# their file a second time - not a store of executor results: nothing else is
# kept, and it is dropped as soon as that result is past the refusal.
_REFUSED_RESULT = "refused_result"
_REFUSED_RESULT_VERSION = 1
# Above this much, the result is not kept and the retry asks the executor again,
# exactly as it does today. A recovery record is rewritten whole on every save.
_REFUSED_RESULT_LIMIT = 1 << 20
LEDGER_FILES = (
    f"{WORKLINE_DIR}/relations/roadmap.yaml",
    f"{WORKLINE_DIR}/relations/related.yaml",
    f"{WORKLINE_DIR}/events/events.jsonl",
)


# --------------------------------------------------------------------------- outcomes

@dataclass(frozen=True)
class Completed:
    """A finished Work and the changes it owns.

    ``result_paths`` are the files the Work created or modified; they must
    exist when it completes. ``deleted_paths`` are tracked files the Work
    deliberately removed; they must be absent and must have been tracked.
    The two are declared separately on purpose — a result path that has gone
    missing is a failed Work, never an inferred deletion.

    ``deleted_paths`` is last so the existing positional form
    ``Completed(paths, message)`` keeps working.
    """

    result_paths: tuple[str, ...] = ()
    message: str | None = None
    deleted_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuestionWait:
    question: str = ""


@dataclass(frozen=True)
class Hold:
    reason: str = ""


@dataclass(frozen=True)
class Cancel:
    replan: Replan = Replan()
    reason: str = ""


@dataclass(frozen=True)
class DerivedWork:
    name: str
    desired_state: str
    related: tuple[RelatedSpec, ...] = ()
    before_integration: bool = True
    work_kind: str | None = None
    confirmation_target: str | list[str] | None = None
    derivation_detail: str | None = None
    return_to: bool = False


@dataclass(frozen=True)
class Derive:
    """START decided new Works (and optionally a re-integration) while executing."""

    works: dict[str, DerivedWork]
    integration: DerivedWork | None = None
    relations: tuple[RelationSpec, ...] = ()
    move: bool = False


@dataclass(frozen=True)
class HumanNG:
    """human_confirmation judged NG: fix Works + new integration, then return to the same confirmation."""

    fix_works: dict[str, DerivedWork]
    integration: DerivedWork
    relations: tuple[RelationSpec, ...] = ()


Outcome = Completed | QuestionWait | Hold | Cancel | Derive | HumanNG


@dataclass
class ExecutionContext:
    store: ProjectStore
    view: ProjectView
    work: Entity
    state: WorkState
    phase: Entity | None
    roadmap: Entity | None
    reading_plan: list[str]
    mutation_id: str
    mode: str
    attempt: int


Executor = Callable[[ExecutionContext], Outcome]


@dataclass(frozen=True)
class StartResult:
    status: str  # completed | phase_complete | question_wait | held | cancelled | moved | stopped
    work_id: str
    mutation_id: str
    completed_work_ids: tuple[str, ...] = ()
    phase_id: str | None = None
    detail: str = ""
    head: str | None = None


# --------------------------------------------------------------------------- helpers

def _structure_or_stop(store: ProjectStore, context: str) -> ProjectView:
    view = ProjectView.load(store)
    problems = validate_structure(view)
    if problems:
        raise ValidationError(f"{context}: {problems_text(problems)}", code="structure_invalid")
    return view


def _tracked_files(store: ProjectStore) -> list[str]:
    result = gitcmd.run_git(store.root, "ls-files", "-z", check=False)
    return [p.replace("\\", "/") for p in result.stdout.split("\0") if p] if result.ok else []


def read_obligations(
    store: ProjectStore, view: ProjectView, work_id: str, *, tracked: list[str] | None = None
) -> list[Relation]:
    """The Related edges a Work has to read, in the canonical reading order.

    ``must_read``, every ``conditional_must_read`` whose condition currently
    applies, then the ``obey`` chain (``rules/information-tracing``). They are
    *current* obligations only while the Work can still run: the same edges on
    a terminal Work are historical evidence of what that Work had to read when
    it ran, and are never revived as a present duty.
    """
    obligations = list(view.related_from(work_id, "must_read"))
    conditional = view.related_from(work_id, "conditional_must_read")
    if conditional:
        if tracked is None:
            tracked = _tracked_files(store)
        obligations += [r for r in conditional if condition_applies(r.extra.get("condition") or {}, tracked)]
    obligations += view.related_from(work_id, "obey")
    return obligations


def require_read_targets(store: ProjectStore, view: ProjectView, work: Entity) -> None:
    """STOP unless every current read obligation of ``work`` resolves.

    A Work about to run must be able to read what it was told to read. A
    target that is gone is never worked around: no filename, directory, mtime
    or similarity fallback, and no assumption that an old target no longer
    matters (``rules/information-tracing``).
    """
    missing = [r for r in read_obligations(store, view, work.id) if not _ref_resolves(store, r.to)]
    if missing:
        detail = ", ".join(f"{r.type} {r.to} (relation {r.id})" for r in missing)
        raise StopError(f"Work {work.id} cannot resolve what it must read: {detail}", code="related_target_missing")


def reading_plan(store: ProjectStore, view: ProjectView, work: Entity) -> list[str]:
    """Work → Phase → Roadmap → must_read → applicable conditional_must_read → obey chain."""
    plan = [work.path]
    phase = view.phases.get(work.phase_id) if work.phase_id else None
    if phase is not None:
        plan.append(phase.path)
        roadmap = view.roadmaps.get(phase.roadmap_id or "")
        if roadmap is not None:
            plan.append(roadmap.path)
    return plan + [relation.to for relation in read_obligations(store, view, work.id)]


def _ref_resolves(store: ProjectStore, target: str) -> bool:
    if target.startswith("workline://"):
        root = store.workline_root()
        return validate_registry(root).ok and target[len("workline://"):] in _registry_ids(root)
    return (store.root / target).exists()


def _registry_ids(root) -> set[str]:
    from .registry import _extract_id_blocks

    try:
        return set(_extract_id_blocks((root / "registry.md").read_text(encoding="utf-8")))
    except OSError:
        return set()


def _result_message(message: str | None, work: Entity) -> str:
    """The message a Work's result commit carries.

    An executor that has something to say says it, and that string is committed
    exactly as given - not stripped, prefixed, retyped or checked against any
    commit convention. Saying nothing is the same however it is spelled: no
    message, an empty one, or only whitespace all fall back to the neutral
    default, because none of them tells a reader anything the default does not.
    The emptiness test is the only thing that strips; it never reaches the
    message that gets committed.

    Blank strings are the only thing this adds to the truthiness test it
    replaces, and nothing else changes meaning. A falsy value still falls back
    to the default as it always did. A truthy value that is not a string is
    still handed on unchanged, so the commit effect's own validation refuses it
    exactly as before - it is neither promoted to a valid message here nor
    refused by a new check of its own.
    """
    if not message:
        return f"chore(workline): {work.display} {work.name}"
    if isinstance(message, str) and not message.strip():
        return f"chore(workline): {work.display} {work.name}"
    return message


def completion_precheck(
    store: ProjectStore,
    view: ProjectView,
    work: Entity,
    result_paths: tuple[str, ...],
    deleted_paths: tuple[str, ...] = (),
) -> None:
    """Work completion precheck (mechanically checkable part of the spec list).

    The Work's changed set is ``result_paths | deleted_paths``, so deleting a
    ``must_update`` target counts as having updated it. ``realizes`` keeps its
    meaning untouched: it asks whether the target exists, so a deletion can
    never satisfy it.
    """
    problems: list[str] = []
    paths = set(result_paths) | set(deleted_paths)
    for relation in view.related_from(work.id, "must_update"):
        if relation.to not in paths:
            problems.append(f"must_update not satisfied: {relation.to}")
    for relation in view.related_from(work.id, "conditional_must_update"):
        condition = relation.extra.get("condition") or {}
        if condition_applies(condition, sorted(paths)) and relation.to not in paths:
            problems.append(f"conditional_must_update not satisfied: {relation.to}")
    for relation in view.related_from(work.id, "realizes"):
        if not _ref_resolves(store, relation.to):
            problems.append(f"realizes target does not exist: {relation.to}")
    unsatisfied = view.unsatisfied_dependencies(work.id)
    if unsatisfied:
        problems.append("unresolved required dependency: " + ", ".join(r.from_id for r, _ in unsatisfied))
    for path in result_paths:
        if not (store.root / path).exists():
            problems.append(f"result path missing: {path}")
    overlap = sorted(set(result_paths) & set(deleted_paths))
    if overlap:
        problems.append("declared both as a result and as a deletion: " + ", ".join(overlap))
    for path in deleted_paths:
        if (store.root / path).exists():
            problems.append(f"deleted path still exists: {path}")
        if not gitcmd.tracked_file(store.root, path):
            # never tracked, or a directory standing in for the files under it
            problems.append(f"deleted path is not a tracked file: {path}")
    # The session refuses such a removal right after the executor returns, where it can
    # still put the file back; this keeps the condition true for a direct caller too.
    problems.extend(_deletion_blocked_by_readers(store, view, work.id, deleted_paths))
    structural = validate_structure(view)
    if structural:
        problems.append("structure invalid: " + problems_text(structural))
    if problems:
        raise StopError("completion precheck failed: " + "; ".join(problems), code="completion_precheck_failed")


def _deletion_blocked_by_readers(
    store: ProjectStore, view: ProjectView, work_id: str, deleted_paths: tuple[str, ...]
) -> list[str]:
    """Started Works, other than this one, that currently must read a path this Work deletes.

    Workline does not create the state its own rule then refuses to run in: a
    Work that entered execution and has not finished still needs what it was
    told to read. The deleting Work itself is not one of them, since it started
    while the target was there. Unstarted Works are future plan, maintained
    through the Roadmap route, and a terminal Work's edges are historical
    evidence, which a later deletion never invalidates.
    """
    if not deleted_paths:
        return []
    targets = set(deleted_paths)
    tracked = _tracked_files(store)
    problems: list[str] = []
    for other_id in sorted(view.works):
        if other_id == work_id:
            continue
        state = view.work_state(other_id)
        if state.terminal or state.state == UNSTARTED:
            continue
        for relation in read_obligations(store, view, other_id, tracked=tracked):
            if relation.to in targets:
                problems.append(
                    f"deleted path {relation.to} is a current read target of {other_id} "
                    f"({relation.type}, relation {relation.id})"
                )
    return problems


def standalone_scope(view: ProjectView, work_id: str) -> list[Entity]:
    """Standalone Works connected to ``work_id`` through roadmap relations."""
    seen = {work_id}
    queue = [work_id]
    while queue:
        current = queue.pop()
        for relation in view.roadmap_relations:
            for other in (relation.from_id, relation.to):
                if other in seen or other not in view.works or view.works[other].phase_id is not None:
                    continue
                if current in (relation.from_id, relation.to):
                    seen.add(other)
                    queue.append(other)
    return [view.works[w] for w in sorted(seen)]


# --------------------------------------------------------------------------- START

class _Session:
    def __init__(
        self,
        store: ProjectStore,
        mutation: Mutation,
        destination: gitops.PushDestination | None,
        mode: str,
        executor: Executor,
    ) -> None:
        self.store = store
        self.mutation = mutation
        # The push destination START verified at its entry; every commit this
        # session finalizes pushes there or nowhere.
        self.destination = destination
        self.mode = mode
        self.executor = executor
        self.completed: list[str] = []
        # What the paths already changed when this operation began held, read once
        # before any executor of this session runs (:meth:`_protect_preexisting`).
        self._preexisting: dict[str, tuple[bytes, int] | None] | None = None

    # git ---------------------------------------------------------------
    def _commit(self, prefix: str, message: str, paths: list[str], *, include_canonical: bool = True) -> None:
        stage = stage_name(self.mutation, prefix)
        owned = sorted(set(paths) | (set(owned_canonical_paths(self.mutation)) if include_canonical else set()))
        dirty = gitcmd.changed_against_head(self.store.root, owned)
        to_commit = sorted(p for p in owned if p in dirty)
        if not to_commit:
            return
        gitops.finalize(self.mutation, stage, message, to_commit, destination=self.destination)

    def _lifecycle(self, work: Entity, types: list[str]) -> None:
        if not types:
            return
        stage = stage_name(self.mutation, f"{work.id}:lifecycle")
        self.mutation.add_effects(stage, event_effects(self.mutation, stage, work.id, types))
        self.mutation.apply()

    # single Work cycle -------------------------------------------------------
    def run_work(self, work_id: str) -> StartResult:
        view = _structure_or_stop(self.store, "start precheck")
        work = view.works.get(work_id)
        if work is None:
            raise ValidationError(f"Work unresolvable: {work_id}", code="entity_unresolvable")
        state = view.work_state(work_id)
        if state.state == COMPLETED:
            # Only a resumed START gets here, once replaying its recorded finalization has
            # committed and pushed the completion; one whose finalization was never
            # recorded is finished before any Work is run (:func:`_completion_to_finish`).
            return StartResult("completed", work_id, self.mutation.id, phase_id=work.phase_id)
        if state.terminal:
            raise SpecViolation(f"Work {work_id} is {state.state}; terminal Works are not started")
        phase = view.phases.get(work.phase_id) if work.phase_id else None
        if phase is not None:
            if view.phase_lifecycle(phase.id) != ACTIVE:
                raise StopError(f"Phase {phase.id} is {view.phase_lifecycle(phase.id)}", code="phase_inactive")
            if view.roadmap_lifecycle(phase.roadmap_id or "") != ACTIVE:
                raise StopError(f"Roadmap {phase.roadmap_id} is {view.roadmap_lifecycle(phase.roadmap_id or '')}", code="roadmap_inactive")
        unsatisfied = view.unsatisfied_dependencies(work_id)
        if unsatisfied:
            raise StopError(
                f"Work {work_id} has unresolved requires_completion: " + ", ".join(f"{r.from_id} ({label})" for r, label in unsatisfied),
                code="dependency_unsatisfied",
            )
        require_read_targets(self.store, view, work)
        # Refuse here, before this Work writes anything, when a target another started
        # Work must read could not be put back if this execution removed it.
        self._protected_read_targets(view, work_id)
        plan = reading_plan(self.store, view, work)
        # Whatever the executor returns, START does not end well without committing the
        # event log - a question wait only defers that commit - so a change to it from
        # before START is refused before any event is appended or the executor runs.
        gitops.ensure_separable_before_effects(self.mutation, [_EVENT_LOG])
        # Before anything of this run is written: the paths already changed when this
        # operation began that are still changed now (``rules/git``: Commit / push), and
        # what they hold, so a result path among them can be refused without the
        # executor's write over the person's file being what is left behind.
        gitops.narrow_preexisting_dirty(self.mutation, self.store.root)
        self._protect_preexisting()
        self.mutation.extend_scope(entities=[work_id])

        # target / lifecycle ---------------------------------------------------
        if state.state == UNSTARTED:
            self._lifecycle(work, ["work_started", "work_target_added"])
        elif state.state == HELD:
            self._lifecycle(work, ["work_resumed", "work_target_added"])
        elif state.state == IN_PROGRESS and not state.has_target:
            self._lifecycle(work, ["work_target_added"])

        attempt = 0
        while True:
            attempt += 1
            view = ProjectView.load(self.store)
            work = view.works[work_id]
            roadmap = view.roadmaps.get(phase.roadmap_id or "") if phase else None
            context = ExecutionContext(self.store, view, work, view.work_state(work_id), phase, roadmap, plan, self.mutation.id, self.mode, attempt)
            protected = self._protected_read_targets(view, work_id)
            try:
                kept = self._refused_result(work_id)
                outcome = self.executor(context) if kept is None else self._reuse_refused_result(kept)
            except BaseException as failure:
                self._put_back_after_failure(protected, failure)
                raise
            self._keep_protected_read_targets(view, work_id, protected)
            if isinstance(outcome, Completed):
                return self._complete(view, work, outcome)
            if isinstance(outcome, QuestionWait):
                return StartResult("question_wait", work_id, self.mutation.id, phase_id=work.phase_id, detail=outcome.question)
            if isinstance(outcome, Hold):
                self._record_hold(work, outcome)
                self._commit("commit", f"chore(workline): hold {work.display}", [])
                return StartResult("held", work_id, self.mutation.id, phase_id=work.phase_id, detail=outcome.reason, head=gitcmd.head_commit(self.store.root))
            if isinstance(outcome, Cancel):
                return self._cancel(view, work, outcome)
            if isinstance(outcome, Derive):
                self._derive(view, work, outcome)
                if outcome.move:
                    self._lifecycle(work, ["work_target_removed"])
                    self._commit("commit", f"chore(workline): branch from {work.display}", [])
                    return StartResult("moved", work_id, self.mutation.id, phase_id=work.phase_id, head=gitcmd.head_commit(self.store.root))
                self._commit("commit", f"chore(workline): derive from {work.display}", [])
                continue
            if isinstance(outcome, HumanNG):
                self._human_ng(view, work, outcome)
                self._lifecycle(work, ["work_target_removed"])
                self._commit("commit", f"chore(workline): {work.display} NG; fix planned", [])
                return StartResult("moved", work_id, self.mutation.id, phase_id=work.phase_id, head=gitcmd.head_commit(self.store.root))
            raise ValidationError(f"executor returned an unknown outcome: {outcome!r}")

    # protected read targets -------------------------------------------------
    def _protected_read_targets(self, view: ProjectView, work_id: str) -> dict[str, tuple[bytes, int]]:
        """What other started Works must currently read, as it stands before the executor runs.

        Only what this rule protects: the current read obligations of Works that
        entered execution and have not finished. The content comes from the
        working tree, not from Git, so uncommitted local content is what would
        be put back. A ``workline://`` target is not a file this execution can
        delete, and a target that is already gone is the reader's own STOP
        rather than this Work's doing; neither is carried here.

        A target that exists but could not be put back the same way — a
        directory, a link, a file that cannot be read — STOPs the Work here,
        before it writes or runs anything, instead of after an executor has
        destroyed it.
        """
        snapshot: dict[str, tuple[bytes, int]] = {}
        tracked = _tracked_files(self.store)
        for other_id in sorted(view.works):
            if other_id == work_id:
                continue
            state = view.work_state(other_id)
            if state.terminal or state.state == UNSTARTED:
                continue
            for relation in read_obligations(self.store, view, other_id, tracked=tracked):
                if relation.to in snapshot or relation.to.startswith("workline://"):
                    continue
                target = self.store.root / relation.to
                if not target.exists():
                    continue
                if target.is_symlink():
                    reason = "it is a link"
                elif target.is_dir():
                    reason = "it is a directory"
                else:
                    try:
                        snapshot[relation.to] = (target.read_bytes(), target.stat().st_mode)
                        continue
                    except OSError as exc:
                        reason = f"it cannot be read ({exc.strerror or exc})"
                raise StopError(
                    f"Work {work_id} cannot run while {other_id} must read {relation.to} "
                    f"(relation {relation.id}): {reason}, so Workline could not put it back "
                    "if this execution removed it",
                    code="related_target_unprotectable",
                )
        return snapshot

    def _put_back_protected(self, snapshot: dict[str, tuple[bytes, int]]) -> tuple[list[str], list[str]]:
        """Write back the protected targets that are gone; return what was and was not put back.

        Exactly the protected paths that disappeared are written, byte for byte
        as they stood when the executor started. Nothing else in the working
        tree is read, restored or reverted, and Git is not asked to check
        anything out.
        """
        restored: list[str] = []
        unrestored: list[str] = []
        for path in sorted(snapshot):
            target = self.store.root / path
            if target.exists():
                continue
            content, mode = snapshot[path]
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                os.chmod(target, stat.S_IMODE(mode))
                restored.append(path)
            except OSError:
                unrestored.append(path)
        return restored, unrestored

    def _keep_protected_read_targets(
        self, view: ProjectView, work_id: str, snapshot: dict[str, tuple[bytes, int]]
    ) -> None:
        """Put back what this execution removed from another started Work, then STOP.

        Refusing the Work is not enough: the Project must not be left without a
        file another started Work still has to read.
        """
        restored, unrestored = self._put_back_protected(snapshot)
        lost = sorted(restored + unrestored)
        if not lost:
            return
        detail = "; ".join(_deletion_blocked_by_readers(self.store, view, work_id, tuple(lost)))
        message = f"Work {work_id} removed what another started Work must read: {detail}"
        if restored:
            message += "; put back as it stood before this execution: " + ", ".join(restored)
        if unrestored:
            message += "; could not be put back: " + ", ".join(unrestored)
        raise StopError(message, code="related_target_removed")

    # changes that were there before this operation ---------------------------
    def _protect_preexisting(self) -> None:
        """Read, once per session and before any executor runs, what the already-changed paths hold.

        These are the paths the operation recorded as changed when it began
        (``rules/git``: Commit / push). What the executor goes on to return as a
        result is not known until it returns, so the only moment their content
        can still be read is this one. ``None`` stands for a path that is not
        there - a deletion the person has not committed - which is put back by
        removing what was created in its place.

        A directory or a link is not carried: putting one back is not writing
        bytes, and this never writes over one. A path that cannot be read is not
        carried either. Either way the refusal says so rather than claiming the
        person's work was kept.
        """
        if self._preexisting is not None:
            return
        held: dict[str, tuple[bytes, int] | None] = {}
        for path in gitops.record_preexisting_dirty(self.mutation, self.store.root):
            target = self.store.root / path
            if target.is_symlink() or target.is_dir():
                continue
            if not target.exists():
                held[path] = None
                continue
            try:
                held[path] = (target.read_bytes(), target.stat().st_mode)
            except OSError:
                continue
        self._preexisting = held

    def _put_back_preexisting(self, paths: list[str]) -> tuple[list[str], list[str]]:
        """Put ``paths`` back to what they held when this operation began; report what could not be.

        Exactly those paths, byte for byte, and nothing else in the working tree:
        the operation is refusing its own result, not reverting the Project.
        """
        restored: list[str] = []
        unrestored: list[str] = []
        for path in sorted(set(paths)):
            held = (self._preexisting or {}).get(path, _UNPROTECTED)
            target = self.store.root / path
            if held is _UNPROTECTED or target.is_symlink():
                unrestored.append(path)
                continue
            try:
                if held is None:
                    if target.exists():
                        target.unlink()
                else:
                    content, mode = held
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                    os.chmod(target, stat.S_IMODE(mode))
                restored.append(path)
            except OSError:
                unrestored.append(path)
        return restored, unrestored

    def _refuse_overlapping_result(self, work: Entity, outcome: object, overlap: list[str], contested: list[str]) -> None:
        """Refuse a result whose paths carry a change from before this operation, leaving that change as it was.

        The executor has run, and at ``contested`` it has written over what the
        person had not committed. The two cannot be separated (``rules/git``:
        Commit / push), so the operation stops - but not on top of their work:
        what they had is put back exactly as it was, and what the executor
        produced is kept in this mutation's record, so that the retry after they
        commit or discard their change finishes the same Work without running the
        executor over their file again.
        """
        self._keep_refused_result(work, outcome, overlap, contested)
        restored, unrestored = self._put_back_preexisting(contested)
        message = gitops.OVERLAP_MESSAGE + ", ".join(overlap)
        if restored:
            message += "; put back as it stood before this operation: " + ", ".join(restored)
        if unrestored:
            message += "; could not be put back: " + ", ".join(unrestored)
        raise StopError(message, code="dirty_overlap")

    # the result a refusal keeps ---------------------------------------------
    def _keep_refused_result(self, work: Entity, outcome: object, overlap: list[str], contested: list[str]) -> None:
        """Keep what the executor returned, and what it left at ``contested``, for the retry.

        Only for this refusal: the executor finished normally and returned a
        result, and the operation stops because a change that was already there
        when it began is at a path that result owns. Anything this record cannot
        keep exactly - a result too large to sit in a record rewritten on every
        save, an outcome a resume would not read back as the same one - is simply
        not kept, and the retry asks the executor again exactly as it does today.
        """
        recorded = _recorded_outcome(outcome)
        held = self._contested_content(contested)
        if recorded is None or held is None:
            return
        note = {
            "version": _REFUSED_RESULT_VERSION,
            "work_id": work.id,
            "overlap": sorted(overlap),
            "outcome": recorded,
            "contested": held,
        }
        if _read_back(note) is _UNKEPT:
            return
        self.mutation.set_note(_REFUSED_RESULT, note)

    def _contested_content(self, contested: list[str]) -> list[dict[str, Any]] | None:
        """What the executor left at ``contested``, or ``None`` when this record would not hold it.

        Bytes as they are: what a Work produces is not always text, and a result
        put back differently is not the result. ``None`` content stands for a path
        the executor removed, which is put back by removing it again.
        """
        held: list[dict[str, Any]] = []
        total = 0
        for path in sorted(set(contested)):
            target = self.store.root / path
            if target.is_symlink() or target.is_dir():
                return None
            if not target.exists():
                held.append({"path": path, "content": None, "mode": None})
                continue
            try:
                raw = target.read_bytes()
                mode = stat.S_IMODE(target.stat().st_mode)
            except OSError:
                return None
            total += len(raw)
            if total > _REFUSED_RESULT_LIMIT:
                return None
            held.append({"path": path, "content": base64.b64encode(raw).decode("ascii"), "mode": mode})
        return held

    def _refused_result(self, work_id: str) -> dict[str, Any] | None:
        """The result this mutation kept for ``work_id`` when it refused it, or ``None``.

        A note that is there but is not one this reads back is not guessed at:
        nothing of it is used, replayed or written, and the operation stops.
        """
        note = self.mutation.note(_REFUSED_RESULT)
        if note is None:
            return None
        if not _reusable_result(note):
            raise ReconcileRequired(
                f"mutation {self.mutation.id} holds a refused result this START does not read back; nothing is "
                "replayed and the record is left as it is: reconcile required"
            )
        return note if note["work_id"] == work_id else None

    def _reuse_refused_result(self, kept: dict[str, Any]) -> object:
        """Finish the Work from the result its refusal kept, without asking the executor again.

        The refusal is made again first, on the paths it was made for: while any
        of them still carries the change that was there before this operation,
        nothing is put back over it and the operation stops exactly as it did,
        having written nothing at all.
        """
        still = sorted(set(gitops.record_preexisting_dirty(self.mutation, self.store.root)) & set(kept["overlap"]))
        if still:
            raise StopError(gitops.OVERLAP_MESSAGE + ", ".join(still), code="dirty_overlap")
        for entry in kept["contested"]:
            target = self.store.root / entry["path"]
            if target.is_symlink():
                raise ReconcileRequired(
                    f"the result kept for {kept['work_id']} names {entry['path']}, which is now a link; nothing is "
                    "written and the record is left as it is: reconcile required"
                )
            if entry["content"] is None:
                if target.exists():
                    target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(entry["content"]))
            if entry["mode"] is not None:
                os.chmod(target, stat.S_IMODE(entry["mode"]))
        return _outcome_from_record(kept["outcome"])

    def _drop_refused_result(self, work_id: str) -> None:
        """Forget the kept result once what it holds is past the refusal that kept it."""
        note = self.mutation.note(_REFUSED_RESULT)
        if isinstance(note, dict) and note.get("work_id") == work_id:
            self.mutation.set_note(_REFUSED_RESULT, None)

    def _put_back_after_failure(self, snapshot: dict[str, tuple[bytes, int]], failure: BaseException) -> None:
        """Put back what a failed execution removed, without taking over its failure.

        The executor failing is its own outcome and keeps its own meaning, so a
        successful put-back says nothing and lets that failure travel on. Only
        when the Project cannot be put back does it become a STOP of its own,
        raised from the original failure so that neither is hidden.
        """
        _, unrestored = self._put_back_protected(snapshot)
        if unrestored:
            raise StopError(
                "the Work failed and Workline could not put back what another started Work must read: "
                + ", ".join(unrestored),
                code="related_target_unrestored",
            ) from failure

    # completion ------------------------------------------------------------
    def _complete(self, view: ProjectView, work: Entity, outcome: Completed) -> StartResult:
        result_paths = tuple(p.replace("\\", "/") for p in outcome.result_paths)
        deleted_paths = tuple(p.replace("\\", "/") for p in outcome.deleted_paths)
        completion_precheck(self.store, view, work, result_paths, deleted_paths)
        # Created, modified and deleted results are one owned set: they are
        # protected from pre-existing changes together and finalized in the
        # same commit, by exact path.
        owned = sorted(set(result_paths) | set(deleted_paths))
        if owned:
            preexisting = gitops.record_preexisting_dirty(self.mutation, self.store.root)
            overlap = sorted(set(preexisting) & set(owned))
            if overlap:
                self._refuse_overlapping_result(work, outcome, overlap, overlap)
            # Without an executor-supplied message the default stays neutral:
            # whether a result is a feature, a fix or documentation is the
            # executor's product judgement, and Workline never infers it from
            # the Work name or kind. A blank message says nothing, so it means
            # the same as supplying none - whitespace alone is not a message a
            # commit could carry, and refusing it would strand the finished Work
            # rather than describe it. Only that emptiness test strips: a
            # message with anything in it is committed exactly as given.
            self._commit(f"{work.id}:results", _result_message(outcome.message, work), owned, include_canonical=False)
            self._drop_refused_result(work.id)
        self._lifecycle(work, ["work_target_removed", "work_completed"])
        return self._finalize_completion(work)

    def _finalize_completion(self, work: Entity) -> StartResult:
        """The Git stage of a completion: the commit carrying its events, the push, the postcheck."""
        self._commit(f"{work.id}:finalize", f"chore(workline): complete {work.display}", [])
        after = ProjectView.load(self.store)
        if after.work_state(work.id).state != COMPLETED:
            raise StopError(f"{work.id} is not completed after finalization", code="postcheck_failed")
        self.completed.append(work.id)
        return StartResult("completed", work.id, self.mutation.id, tuple(self.completed), work.phase_id, head=gitcmd.head_commit(self.store.root))

    def finish_completion(self, work_id: str) -> StartResult:
        """Finalize a completion this mutation recorded and applied, doing none of it again.

        The Work's result is committed and its ``work_target_removed`` /
        ``work_completed`` events are in the event log, but the commit that
        carries them was never recorded. What is left is exactly the Git stage
        (``skills/start``: Terminal finalization): the executor is not asked
        again, no event is added, and nothing else is chosen or run first.
        """
        work = ProjectView.load(self.store).works.get(work_id)
        if work is None:
            raise ValidationError(f"Work unresolvable: {work_id}", code="entity_unresolvable")
        return self._finalize_completion(work)

    # hold ------------------------------------------------------------------
    def _record_hold(self, work: Entity, outcome: Hold) -> None:
        """Record the hold's lifecycle events together with the reason it was held for, then apply them.

        The reason rides on the ``work_held`` effect, so it is durable in exactly
        the save that records the hold's events - the save in which the Mutation
        Controller also records the branch they are decided on (``rules/git``:
        Commit / push). A retry then reports the hold the uninterrupted run would
        have reported, without asking the executor again. A reason the record
        cannot keep exactly (:func:`_hold_decision`) is not recorded and never
        refuses the hold: it is the executor's word to START's caller, not
        Project content, and the hold is finished from the events either way.
        """
        stage = stage_name(self.mutation, f"{work.id}:lifecycle")
        effects = event_effects(self.mutation, stage, work.id, list(_HOLD_EVENTS))
        decision = _hold_decision(outcome.reason)
        if decision is not None:
            effects[-1] = Effect(effects[-1].kind, {**effects[-1].payload, _HOLD_DECISION: decision})
        self.mutation.add_effects(stage, effects)
        self.mutation.apply()

    def finish_hold(self, hold: "_ProvenHold") -> StartResult:
        """Finish a hold this mutation recorded, deciding none of it again.

        The record was shown to hold this START's own hold of that Work
        (:func:`_hold_to_finish`), and replaying it applied every effect already
        recorded. What is left is the Git stage: the commit carrying its events
        and the push, or nothing at all when that commit is recorded too and
        replaying it finished it. The executor is not asked, no event is added,
        no lifecycle is chosen from the state this mutation's own events made,
        and nothing is chosen or run after it - a hold ends the START in
        ``outer`` mode as it does in ``single-work``.
        """
        work = ProjectView.load(self.store).works.get(hold.work_id)
        if work is None:
            raise ValidationError(f"Work unresolvable: {hold.work_id}", code="entity_unresolvable")
        if not hold.committed:
            self._commit("commit", f"chore(workline): hold {work.display}", [])
        after = ProjectView.load(self.store)
        if after.work_state(work.id).state != HELD:
            raise StopError(f"{work.id} is not held after finalization", code="postcheck_failed")
        return StartResult(
            "held", work.id, self.mutation.id, tuple(self.completed), work.phase_id, hold.reason,
            gitcmd.head_commit(self.store.root),
        )

    # cancel ----------------------------------------------------------------
    def _cancel(self, view: ProjectView, work: Entity, outcome: Cancel) -> StartResult:
        state = view.work_state(work.id)
        prefix = stage_name(self.mutation, f"{work.id}:cancel")
        work_ids, removals, additions = plan_replan(self.mutation, prefix, view, outcome.replan)
        events = [(work.id, "work_target_removed")] if state.has_target else []
        events.append((work.id, "work_cancelled"))
        projection = projected_view(
            view,
            add_events=events,
            remove_relation_ids=tuple(r.id for r in removals),
            add_relations=additions,
            add_works={work_ids[k]: spec for k, spec in outcome.replan.new_works.items()},
        )
        validate_projection(projection, "cancel replan")
        decision = _cancel_decision(work.id, prefix, outcome, removals)
        self._record_cancel(work, [t for _, t in events], decision)
        return self._carry_cancel(work, prefix, outcome.replan, removals, additions, work_ids, outcome.reason)

    def _record_cancel(self, work: Entity, types: list[str], decision: dict[str, Any]) -> None:
        """Record the cancel's lifecycle events together with the decision that made them, then apply them.

        The decision rides on the ``work_cancelled`` effect, so it is durable in
        exactly the save that records the terminal events - the save in which the
        Mutation Controller also records the branch they are decided on
        (``rules/git``: Commit / push). No record holds the events without their
        decision, and once they exist nothing a resume needs is left with the
        executor.
        """
        stage = stage_name(self.mutation, f"{work.id}:lifecycle")
        effects = event_effects(self.mutation, stage, work.id, types)
        effects[-1] = Effect(effects[-1].kind, {**effects[-1].payload, _CANCEL_DECISION: decision})
        self.mutation.add_effects(stage, effects)
        self.mutation.apply()

    def _carry_cancel(
        self,
        work: Entity,
        prefix: str,
        replan: Replan,
        removals: list[Relation],
        additions: list[Relation],
        work_ids: dict[str, str],
        reason: object,
    ) -> StartResult:
        """Everything of a cancel after its lifecycle events: the replan, the structural validation, the commit."""
        apply_replan(self.mutation, prefix, replan, removals, additions, work_ids)
        _structure_or_stop(self.store, "cancel structural validation")
        self._commit("commit", f"chore(workline): cancel {work.display}", [])
        return StartResult("cancelled", work.id, self.mutation.id, tuple(self.completed), work.phase_id, reason, gitcmd.head_commit(self.store.root))

    def finish_cancel(self, cancel: "_ProvenCancel") -> StartResult:
        """Carry a cancel this mutation recorded through what is left of it, deciding none of it again.

        The record was shown to hold the cancel's decision and only effects that
        decision makes, and replaying it applied every effect already recorded
        (:func:`_cancel_to_finish`). The executor is not asked; the prefix, the
        IDs, the removals and a recorded registration come from the record; and
        the rest is recorded from the decision exactly as the uninterrupted cancel
        records it. A commit recorded already is done once replayed. The outcome
        is the cancel's own: ``cancelled``, with the reason it was decided for,
        and nothing is chosen or run after it.
        """
        work = ProjectView.load(self.store).works[cancel.work_id]
        if cancel.committed:
            return StartResult(
                "cancelled", work.id, self.mutation.id, tuple(self.completed), work.phase_id, cancel.reason,
                gitcmd.head_commit(self.store.root),
            )
        return self._carry_cancel(
            work, cancel.prefix, cancel.replan, cancel.removals, cancel.additions, cancel.work_ids, cancel.reason
        )

    # derived / fix Works -----------------------------------------------------
    def _derive(self, view: ProjectView, work: Entity, outcome: Derive) -> dict[str, str]:
        if not outcome.works and outcome.integration is None:
            raise ValidationError("Derive without Works")
        for key in outcome.works:
            if key == "integration":
                raise ValidationError("reserved Work key: integration")
        phase_id = work.phase_id
        roadmap_id = view.phases[phase_id].roadmap_id if phase_id else None
        specs: dict[str, WorkSpec] = {}
        relations: list[RelationSpec] = []
        for key, derived in outcome.works.items():
            specs[key] = WorkSpec(
                derived.name,
                derived.desired_state,
                phase_id=phase_id,
                roadmap_id=roadmap_id,
                work_kind=derived.work_kind,
                confirmation_target=derived.confirmation_target,
                related=tuple(derived.related),
                derivation_detail=derived.derivation_detail,
            )
            relations.append(RelationSpec("derived", work.id, key))
            if derived.return_to:
                relations.append(RelationSpec("return_to", key, work.id))
        normal_keys = [k for k, d in outcome.works.items() if d.work_kind is None]
        if phase_id is not None:
            unfinished = view.unfinished_integrations(phase_id)
            if len(unfinished) >= 2:
                raise SpecViolation(f"Phase {phase_id} has {len(unfinished)} unfinished integrations: structural anomaly, STOP")
            if outcome.integration is not None:
                if unfinished:
                    raise SpecViolation("an unfinished integration already exists; START must not create another")
                specs["integration"] = WorkSpec(
                    outcome.integration.name,
                    outcome.integration.desired_state,
                    phase_id=phase_id,
                    roadmap_id=roadmap_id,
                    work_kind="phase_integration_check",
                    related=tuple(outcome.integration.related),
                    derivation_detail=outcome.integration.derivation_detail,
                )
                relations.append(RelationSpec("derived", work.id, "integration"))
                for key in normal_keys:
                    if outcome.works[key].before_integration:
                        relations.append(RelationSpec("requires_completion", key, "integration"))
            elif normal_keys:
                if len(unfinished) == 1:
                    for key in normal_keys:
                        if outcome.works[key].before_integration:
                            relations.append(RelationSpec("requires_completion", key, unfinished[0].id))
                else:
                    raise StopError(
                        f"Phase {phase_id} has no unfinished integration; START must design a re-integration for the new Work(s)",
                        code="reintegration_required",
                    )
        elif outcome.integration is not None:
            raise SpecViolation("standalone Works have no phase integration")
        relations += list(outcome.relations)
        # The registration writes relation files, and which ones is known only now,
        # from what the executor returned. A change that was there before this
        # operation in one of them is refused here, before a Work, a derivation
        # detail or a relation of this derivation is recorded or applied: recording
        # them first left every retry adding another set over the same change.
        ledgers = _derive_ledgers(specs, relations)
        overlap = sorted(set(gitops.record_preexisting_dirty(self.mutation, self.store.root)) & set(ledgers))
        if overlap:
            self._refuse_overlapping_result(work, outcome, overlap, [])
        stage = stage_name(self.mutation, f"{work.id}:derive")
        result = register_works(self.mutation, stage, specs, relations)
        self._drop_refused_result(work.id)
        return result.work_ids

    def _human_ng(self, view: ProjectView, work: Entity, outcome: HumanNG) -> dict[str, str]:
        if work.work_kind != "human_confirmation":
            raise SpecViolation("HumanNG applies to human_confirmation Works only")
        if not outcome.fix_works:
            raise ValidationError("HumanNG needs at least one fix Work")
        relations = [RelationSpec("requires_completion", "integration", work.id)]
        relations += list(outcome.relations)
        derive = Derive(dict(outcome.fix_works), outcome.integration, tuple(relations), move=True)
        return self._derive(view, work, derive)

    # continuation ------------------------------------------------------------
    def next_work(self, view: ProjectView, phase_id: str | None, entry: Entity, just_completed: str | None) -> Entity | None:
        works = view.effective_works(phase_id) if phase_id else standalone_scope(view, entry.id)
        inflight = [w for w in works if view.work_state(w.id).state == IN_PROGRESS and view.work_state(w.id).has_target]
        if len(inflight) > 1:
            raise StopError("multiple Works carry a target: " + ", ".join(w.id for w in inflight), code="multiple_targets")
        if inflight:
            return inflight[0]
        startable = view.startable_works(phase_id, works if phase_id is None else None)
        # a Work that a still-active branch plans to return to waits for that branch
        pending_returns = {
            r.to for r in view.roadmap_relations
            if r.type == "return_to" and r.from_id in view.works and not view.work_state(r.from_id).terminal
        }
        startable = [w for w in startable if w.id not in pending_returns] or startable
        # The plan decides which Work comes next. When it leaves several equally
        # planned, the continuation STOPs instead of separating them by the order
        # they were read in.
        return view.choose_startable(startable, "Work")


def _next_or_ambiguous(
    session: "_Session", view: ProjectView, phase_id: str | None, entry: Entity, just_completed: str | None
) -> tuple[Entity | None, str | None]:
    """The next Work, or the reason the continuation cannot choose one.

    An ambiguous continuation is a STOP, but the Work that just finished was
    committed legitimately and its finalization mutation still has to close. So
    the ambiguity comes back as a stop reason to return, not as an exception
    that would leave the mutation pending behind a decision nobody made.
    """
    try:
        return session.next_work(view, phase_id, entry, just_completed), None
    except StopError as exc:
        if exc.code != AMBIGUOUS_CANDIDATES:
            raise
        return None, exc.message


_EVENT_LOG = f"{WORKLINE_DIR}/events/events.jsonl"
_COMPLETION_EVENTS = ("work_target_removed", "work_completed")


def _completion_to_finish(mutation: Mutation, work_id: str, mode: str) -> str | None:
    """The Work whose recorded completion a resumed START finalizes before anything else, or ``None``.

    A terminal lifecycle stage this START records is finalized by the Git stage
    recorded after it: ``<Work>:finalize:<n>`` for a completion, ``commit:<n>``
    for a cancel. While that stage is missing, the terminal events are in the
    event log, or about to be replayed into it, with nothing committed or
    pushed. Current state already shows the Work completed or cancelled, so a
    retry that read only the state would report success, choose the next Work
    or fold those events into another Work's commit - and close the mutation
    that was the only way left to finalize them.

    So the record is read first, before anything is replayed:

    * no terminal stage without its Git stage - ``None``, and START goes on as
      it always did (a recorded Git stage is replayed like any other effect);
    * an unfinished completion that is provably this START's own - its stage
      holds exactly the two events a completion records for that Work, under
      the IDs reserved for them, it is the last stage recorded, in single-work
      mode it is the invoked Work, and HEAD's event log does not hold those
      events yet - that Work: only its Git stage is left, and it is done
      before anything else;
    * anything else unfinished - more than one unfinished terminal Work, a
      completion recorded in a form this START does not write, or completion
      events HEAD's event log already holds through a commit this mutation did
      not record, which leaves its own finalization commit and push unshown -
      STOP, with the record left exactly as it is.

    A cancel is never finished here. A record holding one is read before the
    mutation is even opened (:func:`_cancel_to_finish`): the cancel is carried on
    from its recorded decision, or START stops there. An unfinished cancel that
    reaches this point was not seen there, and is not taken on trust.
    """
    stages: list[str] = []
    for effect in mutation.effects:
        if effect.get("stage") not in stages:
            stages.append(effect.get("stage"))
    unfinished: list[tuple[int, str, dict]] = []
    for position, stage in enumerate(stages):
        terminal = [
            event for event in _stage_events(mutation, stage)
            if event.get("type") in WORK_TERMINAL_EVENTS and isinstance(event.get("entity"), str)
        ]
        if not terminal:
            continue
        subject, event_type = terminal[0]["entity"], terminal[0]["type"]
        closing = f"{subject}:finalize:" if event_type == "work_completed" else "commit:"
        if not any(str(later).startswith(closing) for later in stages[position + 1:]):
            unfinished.append((position, stage, terminal[0]))
    if not unfinished:
        return None
    if len(unfinished) > 1:
        raise ReconcileRequired(
            f"START mutation {mutation.id} recorded terminal lifecycle events for "
            + ", ".join(sorted({event["entity"] for _, _, event in unfinished}))
            + " that no commit finalizes; START finalizes one Work before it runs another, so this is not a "
            "record it can continue, and it is left pending, exactly as it is: reconcile required"
        )
    position, stage, event = unfinished[0]
    subject, event_type = event["entity"], event["type"]
    if event_type == "work_completed":
        if not (position == len(stages) - 1 and (mode == "outer" or subject == work_id) and _recorded_completion(mutation, stage, subject)):
            raise ReconcileRequired(
                f"START mutation {mutation.id} recorded work_completed for {subject} without the commit that finalizes "
                "it, but not as this START records a completion of that Work, so it cannot show that finalizing it "
                "is its own to do; it is left pending, exactly as it is: reconcile required"
            )
        if _in_head_event_log(mutation.store, [recorded.get("id") for recorded in _stage_events(mutation, stage)]):
            raise ReconcileRequired(
                f"START mutation {mutation.id} recorded the completion of {subject}, but a commit it did not record "
                "already holds those events, so its own finalization commit and push cannot be shown; it is left "
                "pending, exactly as it is: reconcile required"
            )
        return subject
    raise ReconcileRequired(
        f"START mutation {mutation.id} recorded {event_type} for {subject} without the commit that finalizes it, "
        "and not as a cancel this START has shown from its record, so it can neither finish it nor go on past it "
        "to report another outcome; it is left pending, exactly as it is: reconcile required"
    )


def _stage_events(mutation: Mutation, stage: str) -> list[dict]:
    """The event records of ``stage``'s ``append_event`` effects, in recorded order."""
    events: list[dict] = []
    for effect in mutation.stage_effects(stage):
        payload = effect.get("payload")
        record = payload.get("record") if effect.get("kind") == "append_event" and isinstance(payload, dict) else None
        if isinstance(record, dict):
            events.append(record)
    return events


def _recorded_completion(mutation: Mutation, stage: str, work_id: str) -> bool:
    """Whether ``stage`` is exactly the lifecycle stage a completion of ``work_id`` records."""
    effects = mutation.stage_effects(stage)
    events = _stage_events(mutation, stage)
    return (
        isinstance(stage, str)
        and stage.rsplit(":", 1)[0] == f"{work_id}:lifecycle"
        and [effect.get("kind") for effect in effects] == ["append_event"] * len(_COMPLETION_EVENTS)
        and [(event.get("type"), event.get("entity")) for event in events] == [(t, work_id) for t in _COMPLETION_EVENTS]
        and all(mutation.reserved(f"{stage}:event:{index}") == event.get("id") for index, event in enumerate(events))
    )


def _in_head_event_log(store: ProjectStore, event_ids: list[str]) -> bool:
    """Whether the event log committed in HEAD holds any of ``event_ids``; a question Git cannot answer counts as yes."""
    patterns = [arg for event_id in event_ids for arg in ("-e", str(event_id))]
    found = gitcmd.run_git(store.root, "grep", "-q", "-F", *patterns, "HEAD", "--", _EVENT_LOG, check=False)
    return found.returncode != 1


# --------------------------------------------------------------------------- cancel decision
#
# A cancel is decided by the executor, not by START's caller: which new Works
# replace the cancelled one, which relations are added and removed, and why, all
# come back as its outcome. START records that decision on the ``work_cancelled``
# effect, in the save that records the cancel's lifecycle events, and a retry of
# the same START carries the cancel on from the record alone - never by asking
# the executor again, and never by reading the decision back out of the Project.
# Where the retry may replay and record is not decided here: the Mutation
# Controller allows it only on the branch the cancel was decided on, and the
# recorded commit's own branch rules from its Git stage on (``rules/git``:
# Commit / push).

#: The key of the ``work_cancelled`` effect's payload under which a cancel's decision is recorded.
_CANCEL_DECISION = "cancel"
_CANCEL_DECISION_VERSION = 1
_DECISION_FIELDS = frozenset({"version", "work_id", "prefix", "reason", "new_works", "add_relations", "remove_relations"})
_NEW_WORK_FIELDS = frozenset({
    "key", "name", "desired_state", "phase_id", "roadmap_id", "work_kind", "confirmation_target", "related",
    "derivation_detail",
})
_RELATED_FIELDS = frozenset({"type", "to", "condition"})
_ADDITION_FIELDS = frozenset({"type", "from", "to"})
_EVENT_FIELDS = frozenset({"id", "type", "entity", "at"})
#: The lifecycle events a cancel records, in the order it records them.
_CANCEL_EVENTS = (["work_cancelled"], ["work_target_removed", "work_cancelled"])


# --------------------------------------------------------------------------- the result a refusal keeps

_UNPROTECTED = object()

_DERIVED_FIELDS = {
    "name", "desired_state", "related", "before_integration", "work_kind",
    "confirmation_target", "derivation_detail", "return_to",
}
_CONTESTED_FIELDS = {"path", "content", "mode"}
_REFUSED_FIELDS = {"version", "work_id", "overlap", "outcome", "contested"}


def _derive_ledgers(specs: dict[str, WorkSpec], relations: list[RelationSpec]) -> list[str]:
    """The relation files a registration of ``specs`` and ``relations`` writes.

    The Work files and derivation details it writes carry IDs this mutation
    reserves for them, so no change from before the operation can be at those
    paths; only the relation files can be (``create.register_works``).
    """
    ledgers = []
    if relations:
        ledgers.append(f"{WORKLINE_DIR}/relations/roadmap.yaml")
    if any(spec.related for spec in specs.values()):
        ledgers.append(f"{WORKLINE_DIR}/relations/related.yaml")
    return ledgers


def _recorded_derived(work: DerivedWork) -> dict[str, Any]:
    """One derived Work exactly as the executor declared it."""
    return {
        "name": work.name,
        "desired_state": work.desired_state,
        "related": [{"type": r.type, "to": r.to, "condition": r.condition} for r in work.related],
        "before_integration": work.before_integration,
        "work_kind": work.work_kind,
        "confirmation_target": work.confirmation_target,
        "derivation_detail": work.derivation_detail,
        "return_to": work.return_to,
    }


def _recorded_outcome(outcome: object) -> dict[str, Any] | None:
    """``outcome`` in the form its record keeps, or ``None`` when this refusal does not keep it.

    Only the two outcomes a result path or a derivation's relation files can
    refuse. Nothing is normalised: a retry rebuilds from this the outcome the
    uninterrupted run carried on with, endpoints and order as given.
    """
    try:
        if isinstance(outcome, Completed):
            return {
                "kind": "completed",
                "result_paths": [p.replace("\\", "/") for p in outcome.result_paths],
                "deleted_paths": [p.replace("\\", "/") for p in outcome.deleted_paths],
                "message": outcome.message,
            }
        if isinstance(outcome, Derive):
            return {
                "kind": "derive",
                "works": [{"key": key, "work": _recorded_derived(derived)} for key, derived in outcome.works.items()],
                "integration": _recorded_derived(outcome.integration) if outcome.integration is not None else None,
                "relations": [{"type": r.type, "from": r.from_ref, "to": r.to_ref} for r in outcome.relations],
                "move": outcome.move,
            }
    except (AttributeError, TypeError):
        return None
    return None


def _reusable_derived(work: object) -> bool:
    if not isinstance(work, dict) or set(work) != _DERIVED_FIELDS:
        return False
    target = work["confirmation_target"]
    return (
        isinstance(work["name"], str)
        and isinstance(work["desired_state"], str)
        and isinstance(work["before_integration"], bool)
        and isinstance(work["return_to"], bool)
        and all(work[field] is None or isinstance(work[field], str)
                for field in ("work_kind", "derivation_detail"))
        and (_names_one(target) or target is None
             or isinstance(target, list) and all(_names_one(item) for item in target))
        and isinstance(work["related"], list)
        and all(
            isinstance(related, dict)
            and set(related) == _RELATED_FIELDS
            and isinstance(related["type"], str)
            and isinstance(related["to"], str)
            and (related["condition"] is None or isinstance(related["condition"], dict))
            for related in work["related"]
        )
    )


def _reusable_outcome(outcome: object) -> bool:
    if not isinstance(outcome, dict):
        return False
    if outcome.get("kind") == "completed":
        return (
            set(outcome) == {"kind", "result_paths", "deleted_paths", "message"}
            and all(isinstance(outcome[field], list) and all(_names_one(path) for path in outcome[field])
                    for field in ("result_paths", "deleted_paths"))
            and (outcome["message"] is None or isinstance(outcome["message"], str))
        )
    if outcome.get("kind") == "derive":
        return (
            set(outcome) == {"kind", "works", "integration", "relations", "move"}
            and isinstance(outcome["works"], list)
            and outcome["works"]
            and all(isinstance(item, dict) and set(item) == {"key", "work"}
                    and _names_one(item["key"]) and _reusable_derived(item["work"])
                    for item in outcome["works"])
            and (outcome["integration"] is None or _reusable_derived(outcome["integration"]))
            and isinstance(outcome["relations"], list)
            and all(isinstance(rel, dict) and set(rel) == {"type", "from", "to"}
                    and all(_names_one(rel[part]) for part in ("type", "from", "to"))
                    for rel in outcome["relations"])
            and isinstance(outcome["move"], bool)
        )
    return False


def _decodes(content: object) -> bool:
    """Whether kept content is text a result can actually be put back from."""
    if content is None:
        return True
    try:
        base64.b64decode(content, validate=True)
    except (ValueError, TypeError):
        return False
    return True


def _reusable_result(note: object) -> bool:
    """Whether a kept result is one this START reads back as the one it recorded."""
    return (
        isinstance(note, dict)
        and set(note) == _REFUSED_FIELDS
        and note["version"] == _REFUSED_RESULT_VERSION
        and _names_one(note["work_id"])
        and isinstance(note["overlap"], list)
        and note["overlap"]
        and all(_names_one(path) for path in note["overlap"])
        and isinstance(note["contested"], list)
        and all(
            isinstance(entry, dict)
            and set(entry) == _CONTESTED_FIELDS
            and _names_one(entry["path"])
            and (entry["content"] is None or isinstance(entry["content"], str) and _decodes(entry["content"]))
            and (entry["mode"] is None or isinstance(entry["mode"], int) and not isinstance(entry["mode"], bool))
            for entry in note["contested"]
        )
        and _reusable_outcome(note["outcome"])
    )


def _derived_from_record(work: dict[str, Any]) -> DerivedWork:
    return DerivedWork(
        work["name"],
        work["desired_state"],
        related=tuple(RelatedSpec(r["type"], r["to"], r["condition"]) for r in work["related"]),
        before_integration=work["before_integration"],
        work_kind=work["work_kind"],
        confirmation_target=work["confirmation_target"],
        derivation_detail=work["derivation_detail"],
        return_to=work["return_to"],
    )


def _outcome_from_record(outcome: dict[str, Any]) -> object:
    """The outcome a kept result records, rebuilt as the executor returned it."""
    if outcome["kind"] == "completed":
        return Completed(tuple(outcome["result_paths"]), outcome["message"], tuple(outcome["deleted_paths"]))
    return Derive(
        {item["key"]: _derived_from_record(item["work"]) for item in outcome["works"]},
        _derived_from_record(outcome["integration"]) if outcome["integration"] is not None else None,
        tuple(RelationSpec(rel["type"], rel["from"], rel["to"]) for rel in outcome["relations"]),
        outcome["move"],
    )


def _cancel_decision(work_id: str, prefix: str, outcome: Cancel, removals: list[Relation]) -> dict[str, Any]:
    """What a START cancel decided, exactly as its recovery record reads it back - or the refusal.

    Everything a resume needs that no effect recorded with the cancel's events
    holds: the Work, the prefix its replan stages are recorded under, the reason,
    the new Works and the relations to add exactly as the executor gave them
    (declared order, endpoints as written - a key and the ID it is reserved as
    are different decisions), and every relation to remove as the Project held
    it when the cancel was decided. The lifecycle events are not repeated - the
    decision rides on them - and neither are the IDs reserved for the replan,
    which the record keeps under keys this decision determines.

    Nothing is normalised or translated, because a resume rebuilds from it the
    replan the uninterrupted cancel carries on with. The decision is therefore
    recorded only when the record reads every part of it back as the same value
    of the same kind. A part it cannot keep - a float, a tuple, an object, a
    nested list, text holding a lone surrogate UTF-8 cannot write -
    refuses the cancel here, before anything of it is recorded, rather than
    leaving a cancel that could be finished only if nothing interrupted it. So
    does a decision a resume would not read as one (:func:`_decision_problem`),
    such as a new Work whose name is not text, which the registration would
    refuse only after the cancel's events were applied.
    """
    replan = outcome.replan
    try:
        decision = {
            "version": _CANCEL_DECISION_VERSION,
            "work_id": work_id,
            "prefix": prefix,
            "reason": outcome.reason,
            "new_works": [
                {
                    "key": key,
                    "name": spec.name,
                    "desired_state": spec.desired_state,
                    "phase_id": spec.phase_id,
                    "roadmap_id": spec.roadmap_id,
                    "work_kind": spec.work_kind,
                    "confirmation_target": spec.confirmation_target,
                    "related": [{"type": r.type, "to": r.to, "condition": r.condition} for r in spec.related],
                    "derivation_detail": spec.derivation_detail,
                }
                for key, spec in replan.new_works.items()
            ],
            "add_relations": [{"type": r.type, "from": r.from_ref, "to": r.to_ref} for r in replan.add_relations],
            "remove_relations": [relation.to_record() for relation in removals],
        }
    except (AttributeError, TypeError) as exc:
        raise ValidationError(
            f"cancel decision: the replan is not one a cancel decision can record ({exc}); a cancel is recorded only "
            "together with everything it decided, so nothing of it is recorded"
        ) from exc
    kept = _read_back(decision)
    if kept is _UNKEPT:
        where, value = _unkept_part(decision, "cancel")
        raise ValidationError(
            f"cancel decision: {where} ({type(value).__name__}) cannot be kept exactly by the recovery record; a "
            "cancel is recorded only together with everything it decided, so nothing of it is recorded"
        )
    # Only a decision a resume can read back as one is recorded: what the registration would refuse anyway is refused
    # here, before the cancel's events, instead of after them.
    problem = _decision_problem(kept)
    if problem is not None:
        raise ValidationError(
            f"cancel decision: {problem}; a cancel is recorded only together with everything it decided, so nothing "
            "of it is recorded"
        )
    return kept


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


_UNKEPT = object()


def _read_back(value: object) -> object:
    """``value`` as a recovery record reads it back once written, or :data:`_UNKEPT` when that is not exactly ``value``.

    Written and read the way the record itself is (``yamlish``, UTF-8), and
    compared with the kind of every part, keys included (:func:`_typed`).
    """
    try:
        text = yamlish.dump({"value": value})
        text.encode("utf-8")
        kept = yamlish.load(text)["value"]
        if _typed(kept) == _typed(value):
            return kept
    except (yamlish.YamlishError, TypeError, ValueError, KeyError, RecursionError):
        pass
    return _UNKEPT


def _typed(value: object) -> object:
    """``value`` spelled out with the kind of each part, so that ``True`` is not ``1``, nor ``1`` the key ``"1"``."""
    if value is None or isinstance(value, bool):
        return [type(value).__name__, value]
    if isinstance(value, int):
        return ["int", int(value)]
    if isinstance(value, str):
        return ["str", str(value)]
    if isinstance(value, dict):
        return ["dict", [[_typed(key), _typed(item)] for key, item in value.items()]]
    if isinstance(value, list):
        return ["list", [_typed(item) for item in value]]
    raise TypeError(f"{type(value).__name__} is not a value a recovery record keeps")


def _unkept_part(value: object, where: str) -> tuple[str, object]:
    """The innermost part of ``value`` a recovery record does not keep exactly, and where it is."""
    if isinstance(value, dict):
        parts = [(f"{where}.{key}", item) for key, item in value.items()]
    elif isinstance(value, list):
        parts = [(f"{where}[{index}]", item) for index, item in enumerate(value)]
    else:
        parts = []
    for part, item in parts:
        if _read_back(item) is _UNKEPT:
            return _unkept_part(item, part)
    return where, value


@dataclass(frozen=True)
class _ProvenCancel:
    """An interrupted cancel of exactly this START, shown from its record, and what carrying it on still needs."""

    mutation_id: str
    work_id: str
    prefix: str
    reason: object
    replan: Replan
    work_ids: dict[str, str]
    additions: list[Relation]
    removals: list[Relation]
    committed: bool  # the commit carrying the cancel is recorded: replaying the record finishes it
    view: ProjectView  # the Project without the cancel's own applied effects: what the decision was made on


@dataclass(frozen=True)
class _CancelRecord:
    """The stages of a START record and its one cancel, read with nothing assumed."""

    effects: list[dict[str, Any]]
    stages: list[str]
    by_stage: dict[str, list[dict[str, Any]]]
    stage: str
    position: int
    work_id: str
    events: list[dict[str, Any]]
    reserved: dict[str, Any]
    decision: object

    @property
    def types(self) -> list[str]:
        return [event["type"] for event in self.events]


def _cancel_to_finish(store: ProjectStore, entry: Entity, mode: str) -> _ProvenCancel | None:
    """The cancel an interrupted run of exactly this START recorded and a retry carries on, or ``None``.

    Read before anything is judged on the current Project, before the mutation
    is opened and before any recorded effect is replayed, because a cancel that
    stopped part-way leaves a Project this START would otherwise refuse or
    misread: its own ``work_cancelled`` makes the Work terminal, a relation its
    replan was about to remove can still point at the cancelled Work, and a
    commit already recorded would be replayed before anything else. Every step
    reads only, and whatever refuses leaves the record, the Project and Git
    exactly as they are:

    * no unfinished START of this Work and mode holds a cancel - ``None``, and
      START goes on as it always did (a recovery area that cannot be read proves
      nothing here and is reported where it always was, when the mutation is
      opened);
    * several unfinished STARTs of this Work and mode - ``reconcile required``;
    * a cancel recorded without its decision, as every cancel was before START
      recorded one - ``reconcile required``, whether or not its commit is
      recorded too: what it decided is never read back out of the Project, the
      events, the commit or the reservations;
    * :func:`_prove_cancel` - the decision is in the form START records it, it
      cancels this START's Work under its own prefix and reservations, every
      stage recorded after it is exactly what it makes, and what was applied is
      consistent with the order it was recorded in;
    * :func:`_decide_cancel` - the decision judged again, as START judged it, on
      the Project without the cancel's own applied effects;
    * ``ops._refuse_before_replay`` - what is still to come refused the way
      recording and applying it would refuse, before any of it runs.
    """
    invocation = {"operation": OWNER, "work_id": entry.id, "mode": mode}
    try:
        records = [
            record for record in MutationController(store).list_pending()
            if record["owner"] == OWNER and record["invocation"] == invocation
        ]
    except ReconcileRequired:
        return None
    if not any(_cancel_event(effect) is not None for record in records for effect in _effects_of(record)):
        return None
    if len(records) > 1:
        raise ReconcileRequired(
            f"{len(records)} unfinished START mutations of {entry.id} ({mode}) "
            + ", ".join(sorted(record["mutation_id"] for record in records))
            + ", and one of them recorded a cancel; START carries on exactly one, and they are left as they are: "
            "reconcile required"
        )
    (record,) = records
    refuse = _cancel_refusal(record)
    read = _read_cancel_record(record, refuse)
    proven, cancel = _prove_cancel(store, record, read, entry, mode, refuse)
    view = _decide_cancel(proven, read, cancel, refuse)
    own = {read.stage, *_replan_stages(cancel.prefix, cancel.replan)}
    _refuse_before_replay(
        store, OWNER, record, proven, cancel.replan, cancel.removals,
        prefix=cancel.prefix,
        context="cancel replan",
        committing=[effect for effect in proven.file_effects if effect["stage"] in own],
    )
    return _ProvenCancel(
        record["mutation_id"], read.work_id, cancel.prefix, read.decision["reason"], cancel.replan, cancel.work_ids,
        cancel.additions, cancel.removals, cancel.committed, view,
    )


def _effects_of(record: dict[str, Any]) -> list[Any]:
    effects = record.get("effects")
    return effects if isinstance(effects, list) else []


def _cancel_event(effect: object) -> dict[str, Any] | None:
    """The ``work_cancelled`` event an effect records, or ``None``."""
    payload = effect.get("payload") if isinstance(effect, dict) and effect.get("kind") == "append_event" else None
    event = payload.get("record") if isinstance(payload, dict) else None
    return event if isinstance(event, dict) and event.get("type") == "work_cancelled" else None


def _cancel_refusal(record: dict[str, Any]) -> Callable[[str], ReconcileRequired]:
    def refuse(reason: str) -> ReconcileRequired:
        return ReconcileRequired(
            f"START mutation {record['mutation_id']} recorded a cancel, but its record holds {reason}; nothing shows "
            "that carrying it on does what that cancel decided, and it is left pending, exactly as it is: "
            "reconcile required"
        )

    return refuse


def _read_cancel_record(record: dict[str, Any], refuse) -> _CancelRecord:
    """The record's stages and its one cancel stage with the decision on it, when both are in the form START records them."""
    effects = record.get("effects")
    if not isinstance(effects, list) or not all(
        isinstance(effect, dict)
        and isinstance(effect.get("stage"), str)
        and isinstance(effect.get("kind"), str)
        and isinstance(effect.get("payload"), dict)
        for effect in effects
    ):
        raise refuse("effects that cannot be read")
    stages = _recorded_stages(effects, refuse)
    cancelled = [effect for effect in effects if _cancel_event(effect) is not None]
    if len(cancelled) != 1:
        raise refuse("more than one work_cancelled event; START cancels one Work and then stops")
    (cancel_effect,) = cancelled
    stage = cancel_effect["stage"]
    if _CANCEL_DECISION not in cancel_effect["payload"]:
        raise ReconcileRequired(
            f"START mutation {record['mutation_id']} recorded the cancel of {_cancel_event(cancel_effect).get('entity')} "
            "without the decision that cancel made: it was written before START recorded what a cancel decides, so "
            "neither its replan nor its outcome can be shown, and nothing stands in for them - not the Project, the "
            "events, a recorded commit or the IDs it reserved; it is left pending, exactly as it is: reconcile required"
        )
    by_stage = {name: [effect for effect in effects if effect["stage"] == name] for name in stages}
    lifecycle = by_stage[stage]
    events = [effect["payload"].get("record") for effect in lifecycle]
    if not all(
        effect["kind"] == "append_event"
        and isinstance(event, dict)
        and set(event) == _EVENT_FIELDS
        and all(isinstance(event[field], str) and event[field] for field in _EVENT_FIELDS)
        for effect, event in zip(lifecycle, events)
    ):
        raise refuse(f"a cancel stage {stage!r} holding something other than lifecycle events")
    work_id = events[-1]["entity"]
    if (
        [event["type"] for event in events] not in _CANCEL_EVENTS
        or any(event["entity"] != work_id for event in events)
        or not is_valid_id(work_id, "work")
    ):
        raise refuse(f"a cancel stage {stage!r} holding other events than the cancel of one Work records")
    position = stages.index(stage)
    number = len({name for name in stages[:position] if name.startswith(f"{work_id}:lifecycle:")})
    if stage != f"{work_id}:lifecycle:{number}":
        raise refuse(f"a cancel stage named {stage!r}, where the cancel of {work_id} records it as its next lifecycle stage")
    reserved = record.get("reserved_ids")
    if not isinstance(reserved, dict):
        raise refuse("reservations that are not a mapping")
    if any(reserved.get(f"{stage}:event:{index}") != event["id"] for index, event in enumerate(events)):
        raise refuse("cancel events under IDs the cancel did not reserve for them")
    if any(set(effect["payload"]) != {"record"} for effect in lifecycle[:-1]) or set(lifecycle[-1]["payload"]) != {
        "record", _CANCEL_DECISION
    }:
        raise refuse("cancel events carrying something other than the decision on the work_cancelled event")
    return _CancelRecord(
        effects, stages, by_stage, stage, position, work_id, events, reserved, lifecycle[-1]["payload"][_CANCEL_DECISION]
    )


def _decision_problem(decision: object) -> str | None:
    """What makes ``decision`` other than a cancel decision START records, or ``None``.

    The form is the one :func:`_cancel_decision` records, and it refuses to
    record any other: text where registering a Work or a relation needs text,
    and any value the record keeps where the executor may hand one - a reason,
    and a new Work's key and the endpoints and confirmation targets that name
    one.
    """
    if not isinstance(decision, dict) or set(decision) != _DECISION_FIELDS:
        return "fields other than a cancel decision's"
    if type(decision["version"]) is not int or decision["version"] != _CANCEL_DECISION_VERSION:
        return f"version {decision['version']!r}, which this START does not read"
    if not isinstance(decision["work_id"], str) or not isinstance(decision["prefix"], str):
        return "a Work or a prefix that is not text"
    new_works, additions, removals = decision["new_works"], decision["add_relations"], decision["remove_relations"]
    if not isinstance(new_works, list) or not all(_decided_work(work) for work in new_works):
        return "new Works in another form than a cancel decision records them"
    keys = [work["key"] for work in new_works]
    if len(set(keys)) != len(keys) or len({_canonical(key) for key in keys}) != len(keys):
        return "one new Work key decided twice"
    if not isinstance(additions, list) or not all(
        isinstance(addition, dict)
        and set(addition) == _ADDITION_FIELDS
        and isinstance(addition["type"], str)
        and _names_one(addition["from"])
        and _names_one(addition["to"])
        for addition in additions
    ):
        return "relations to add in another form than a cancel decision records them"
    if not isinstance(removals, list) or not all(_decided_removal(removal) for removal in removals):
        return "relations to remove in another form than a cancel decision records them"
    return None


def _names_one(value: object) -> bool:
    """Whether ``value`` can name a Work - by its ID or by a new Work's key - as a record keeps it."""
    return value is None or isinstance(value, (str, int))


def _decided_work(work: object) -> bool:
    if not isinstance(work, dict) or set(work) != _NEW_WORK_FIELDS:
        return False
    target = work["confirmation_target"]
    return (
        _names_one(work["key"])
        and isinstance(work["name"], str)
        and isinstance(work["desired_state"], str)
        and all(work[field] is None or isinstance(work[field], str) for field in ("phase_id", "roadmap_id", "work_kind", "derivation_detail"))
        and (_names_one(target) or isinstance(target, list) and all(_names_one(item) for item in target))
        and isinstance(work["related"], list)
        and all(
            isinstance(related, dict)
            and set(related) == _RELATED_FIELDS
            and isinstance(related["type"], str)
            and isinstance(related["to"], str)
            and (related["condition"] is None or isinstance(related["condition"], dict))
            for related in work["related"]
        )
    )


def _decided_removal(removal: object) -> bool:
    return (
        isinstance(removal, dict)
        and all(isinstance(removal.get(part), str) and removal[part] for part in ("id", "type", "from", "to"))
        and is_valid_id(removal["id"], "relation")
        and removal["type"] != "derived"
        and Relation.from_record(removal).to_record() == removal
    )


def _decided_replan(decision: dict[str, Any]) -> Replan:
    """The replan a proven decision records, rebuilt as the executor gave it."""
    return Replan(
        remove_relation_ids=tuple(removal["id"] for removal in decision["remove_relations"]),
        add_relations=tuple(RelationSpec(addition["type"], addition["from"], addition["to"]) for addition in decision["add_relations"]),
        new_works={
            work["key"]: WorkSpec(
                work["name"],
                work["desired_state"],
                phase_id=work["phase_id"],
                roadmap_id=work["roadmap_id"],
                work_kind=work["work_kind"],
                confirmation_target=work["confirmation_target"],
                related=tuple(RelatedSpec(related["type"], related["to"], related["condition"]) for related in work["related"]),
                derivation_detail=work["derivation_detail"],
            )
            for work in decision["new_works"]
        },
    )


def _replan_stages(prefix: str, replan: Replan) -> list[str]:
    """The stages a cancel's replan records after its lifecycle stage, in the order it records them (``ops.apply_replan``)."""
    stages = [f"{prefix}:works"] if replan.new_works else [f"{prefix}:relations"] if replan.add_relations else []
    if replan.remove_relation_ids:
        stages.append(f"{prefix}:remove")
    return stages


@dataclass(frozen=True)
class _DecidedCancel:
    prefix: str
    replan: Replan
    work_ids: dict[str, str]
    additions: list[Relation]
    removals: list[Relation]
    committed: bool


def _prove_cancel(
    store: ProjectStore, record: dict[str, Any], read: _CancelRecord, entry: Entity, mode: str, refuse
) -> tuple[_ProvenRecord, _DecidedCancel]:
    """Show the decision, and every effect recorded with and after it, are what that decision makes for this START."""
    decision = read.decision
    problem = _decision_problem(decision)
    if problem is not None:
        raise refuse(f"a cancel decision with {problem}")
    work_id, stages, reserved, position = read.work_id, read.stages, read.reserved, read.position
    if decision["work_id"] != work_id:
        raise refuse(f"a decision to cancel {decision['work_id']} on the events cancelling {work_id}")
    current = ProjectView.load(store)
    work = current.works.get(work_id)
    if work is None:
        raise refuse(f"the cancel of {work_id}, which does not resolve")
    if mode == "single-work" and work_id != entry.id:
        raise refuse(f"the cancel of {work_id}, where this single-work START runs {entry.id} alone")
    if work.phase_id != entry.phase_id:
        raise refuse(f"the cancel of {work_id}, outside the scope this START runs from {entry.id}")

    # stages: the prefix is the one the cancel recorded its replan under, and only what the decision records follows
    prefix = decision["prefix"]
    expected_prefix = f"{work_id}:cancel:{len({name for name in stages[:position] if name.startswith(f'{work_id}:cancel:')})}"
    if prefix != expected_prefix:
        raise refuse(f"the replan prefix {prefix!r}, where the cancel records its replan under {expected_prefix!r}")
    replan = _decided_replan(decision)
    works_stage, relations_stage, remove_stage = f"{prefix}:works", f"{prefix}:relations", f"{prefix}:remove"
    replanned = _replan_stages(prefix, replan)
    after = stages[position + 1:]
    if after[: len(replanned)] != replanned[: len(after)]:
        raise refuse(f"the stages {after} after the cancel stage, where its decision records {replanned} in that order")
    committed = len(after) > len(replanned)
    commit_stage: str | None = None
    if committed:
        commit_stage = f"commit:{len({name for name in stages[: position + 1 + len(replanned)] if name.startswith('commit:')})}"
        if after[len(replanned):] != [commit_stage]:
            raise refuse(f"the stages {after} after the cancel stage, where its decision records {replanned} and then its commit")
    for index, name in enumerate(stages[:position]):
        for effect in read.by_stage[name]:
            event = effect["payload"].get("record") if effect["kind"] == "append_event" else None
            if not isinstance(event, dict) or event.get("type") not in WORK_TERMINAL_EVENTS:
                continue
            if event.get("type") != "work_completed" or not any(
                later.startswith(f"{event.get('entity')}:finalize:") for later in stages[index + 1: position]
            ):
                raise refuse(f"a terminal lifecycle stage {name!r} no commit finalized before the cancel")

    # reservations: the decision's keys name them, and the IDs are never decided again
    def reserved_id(key: str, kind: str) -> str:
        value = reserved.get(key)
        if not isinstance(value, str) or not is_valid_id(value, kind):
            raise refuse(f"no {kind} ID reserved under {key!r}")
        return value

    work_ids = {key: reserved_id(f"{works_stage}:work:{key}", "work") for key in replan.new_works}
    relation_stage = works_stage if replan.new_works else relations_stage
    relation_ids = [reserved_id(f"{relation_stage}:rel:{index}", "relation") for index in range(len(replan.add_relations))]
    used = list(work_ids.values()) + relation_ids + [event["id"] for event in read.events]
    if len(set(used)) != len(used):
        raise refuse("one reserved ID used for two things the decision makes")
    additions = [
        Relation(relation_ids[index], spec.type, resolve_ref(spec.from_ref, work_ids), resolve_ref(spec.to_ref, work_ids))
        for index, spec in enumerate(replan.add_relations)
    ]
    removals = [Relation.from_record(removal) for removal in decision["remove_relations"]]

    # recorded replan stages: exactly what the decision records, under its reservations
    if works_stage in read.by_stage:
        related_ids = {
            (key, index): reserved_id(f"{works_stage}:related:{key}:{index}", "relation")
            for key, spec in replan.new_works.items()
            for index in range(len(spec.related))
        }
        derivation_ids = {
            key: reserved_id(f"{works_stage}:der:{key}", "derivation")
            for key, spec in replan.new_works.items()
            if spec.derivation_detail is not None
        }
        try:
            matches = _registration_matches(
                read.by_stage[works_stage], replan.new_works, work_ids, additions, related_ids, derivation_ids
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise refuse(f"new Works the registration cannot write ({exc})") from exc
        if not matches:
            raise refuse(f"a {works_stage} stage other than the registration its decision makes")
    if relations_stage in read.by_stage:
        if _as_recorded(read.by_stage[relations_stage]) != _as_recorded(Effect.add_relation("roadmap", r) for r in additions):
            raise refuse(f"a {relations_stage} stage other than the relations its decision adds")
    if remove_stage in read.by_stage:
        if _as_recorded(read.by_stage[remove_stage]) != _as_recorded(Effect.remove_relation("roadmap", r) for r in removals):
            raise refuse(f"a {remove_stage} stage other than the removals its decision makes")
    file_effects = [effect for effect in read.effects if effect["kind"] in FILE_EFFECT_KINDS]
    finalize = read.by_stage[commit_stage] if committed else None
    if finalize is not None:
        try:
            owned = set(_owned_paths(file_effects))
        except (KeyError, TypeError) as exc:
            raise refuse(f"file effects that cannot be read ({exc})") from exc
        commit = finalize[0]["payload"]
        paths = commit.get("paths")
        if (
            [effect["kind"] for effect in finalize] not in (["git_commit"], ["git_commit", "git_push"])
            or commit.get("message") != f"chore(workline): cancel {work.display}"
            or not isinstance(paths, list)
            or not paths
            or not all(isinstance(path, str) for path in paths)
            or not set(paths) <= owned
        ):
            raise refuse(f"a {commit_stage} stage other than the commit carrying the cancel")

    # progress: what was applied is what the record says was done first, and only its last stage can be part-way
    applied, unapplied = _recorded_progress(store, file_effects, stages[-1], committed, refuse)
    if not committed and _in_head_event_log(store, [event["id"] for event in read.events]):
        raise ReconcileRequired(
            f"START mutation {record['mutation_id']} recorded the cancel of {work_id}, but a commit it did not record "
            "already holds those events, so its own commit and push cannot be shown; it is left pending, exactly as "
            "it is: reconcile required"
        )
    proven = _ProvenRecord(
        dict(reserved), read.effects, read.by_stage, current, work_ids, additions,
        removals if remove_stage in read.by_stage else None, finalize, file_effects, applied, unapplied,
    )
    return proven, _DecidedCancel(prefix, replan, work_ids, additions, removals, committed)


def _decide_cancel(proven: _ProvenRecord, read: _CancelRecord, cancel: _DecidedCancel, refuse) -> ProjectView:
    """The decision judged again as START judged it, on the Project without the cancel's own applied effects.

    START's precheck, the Work the cancel found, the relations it removes and
    the owner projection of the whole replan read that Project - the one the
    decision was made on - so the cancel's own events, Works, additions and
    removals are neither held against it nor counted twice. What other stages of
    the same START applied before the cancel stays: the cancel was decided on it.
    """
    own = {read.stage, *_replan_stages(cancel.prefix, cancel.replan)}
    view = _own_effects_free_view(proven.current, [effect for effect in proven.applied if effect["stage"] in own])
    work_id, types = read.work_id, read.types
    state = view.work_state(work_id)
    if state.state != IN_PROGRESS or state.has_target != ("work_target_removed" in types):
        raise refuse(
            f"a cancel of {work_id} as it never stood: without the cancel it is {state.state} "
            f"{'with' if state.has_target else 'without'} a target"
        )
    problems = validate_structure(view)
    if problems:
        raise ValidationError(f"start precheck: {problems_text(problems)}", code="structure_invalid")
    standing = {relation.id: relation for relation in view.roadmap_relations}
    for removal in cancel.removals:
        if removal.id not in standing or standing[removal.id].to_record() != removal.to_record():
            raise refuse(f"relation {removal.id} to remove, which the Project no longer holds as the cancel found it")
    validate_projection(
        projected_view(
            view,
            add_events=[(work_id, event_type) for event_type in types],
            remove_relation_ids=tuple(relation.id for relation in cancel.removals),
            add_relations=cancel.additions,
            add_works={cancel.work_ids[key]: spec for key, spec in cancel.replan.new_works.items()},
        ),
        "cancel replan",
    )
    return view


# --------------------------------------------------------------------------- recorded hold
#
# A hold is decided by the executor, and START records it as two lifecycle
# events and the commit that carries them. Those events are not terminal - the
# Work is held, and a later START runs it again - so a retry that read only the
# current state found a Work it may legitimately resume, and resumed the very
# hold this mutation had just recorded: it appended ``work_resumed`` /
# ``work_target_added``, asked the executor again, recorded whatever came back
# as a new decision, and named every stage afresh, so nothing deduplicated it.
# The record already marks that hold as a decision, with the branch it was
# decided on; what was missing was a resume that reads it.

_HOLD_DECISION = "hold"
_HOLD_DECISION_VERSION = 1
_HOLD_DECISION_FIELDS = frozenset({"version", "reason"})
#: The lifecycle events a hold records, in the order it records them.
_HOLD_EVENTS = ("work_target_removed", "work_held")


def _hold_decision(reason: object) -> dict[str, Any] | None:
    """The reason a hold was decided for, as its record reads it back, or ``None`` when the record cannot keep it.

    Only the reason: everything else a resume needs - the Work, the stage, the
    events and the IDs reserved for them - is in the effects the decision rides
    on. The reason is the executor's word to START's caller and no Project
    content is made from it, so one the record cannot keep exactly (a float, an
    object, text holding a lone surrogate) is left out rather than refusing a
    hold that would otherwise succeed. The retry then finishes the same hold and
    reports it without a reason, exactly as it finishes a record written before
    START kept one.
    """
    kept = _read_back({"version": _HOLD_DECISION_VERSION, "reason": reason})
    return None if kept is _UNKEPT else kept


def _hold_decision_problem(decision: object) -> str | None:
    """What makes ``decision`` other than a hold decision START records, or ``None``."""
    if not isinstance(decision, dict) or set(decision) != _HOLD_DECISION_FIELDS:
        return "fields other than a hold decision's"
    if type(decision["version"]) is not int or decision["version"] != _HOLD_DECISION_VERSION:
        return f"version {decision['version']!r}, which this START does not read"
    return None


def _held_event(effect: object) -> dict[str, Any] | None:
    """The ``work_held`` event an effect records, or ``None``."""
    payload = effect.get("payload") if isinstance(effect, dict) and effect.get("kind") == "append_event" else None
    event = payload.get("record") if isinstance(payload, dict) else None
    return event if isinstance(event, dict) and event.get("type") == "work_held" else None


@dataclass(frozen=True)
class _ProvenHold:
    """A hold exactly this START recorded, shown from its record, and what finishing it still needs."""

    work_id: str
    reason: object  # what it was held for, or ``None`` when the record keeps no reason
    committed: bool  # the commit carrying the hold is recorded: replaying the record finishes it


def _hold_refusal(mutation: Mutation) -> Callable[[str], ReconcileRequired]:
    def refuse(reason: str) -> ReconcileRequired:
        return ReconcileRequired(
            f"START mutation {mutation.id} recorded a hold, but its record holds {reason}; nothing shows that "
            "finishing it does what that hold decided, and it is left pending, exactly as it is: reconcile required"
        )

    return refuse


def _hold_to_finish(mutation: Mutation, work_id: str, mode: str) -> _ProvenHold | None:
    """The hold an interrupted run of exactly this START recorded and a retry finishes, or ``None``.

    Read after the terminal finalization (:func:`_completion_to_finish`) and
    before anything is replayed or chosen, because a hold that stopped part-way
    leaves a Project this START would otherwise read as an invitation to run the
    Work again: its own ``work_held`` makes the Work held, and ``run_work``
    resumes a held Work. Every step reads only, and whatever refuses leaves the
    record, the Project and Git exactly as they are:

    * no ``work_held`` in the record - ``None``, and START goes on as it always
      did; a hold the executor has not returned yet is not in the record at all,
      since its events are recorded together with what they decide;
    * more than one - ``reconcile required``: START holds one Work and stops;
    * a hold that is provably this START's own - its stage is the next lifecycle
      stage of that Work, holding exactly the two events a hold records for it,
      under the IDs reserved for them and carrying nothing but the reason on the
      ``work_held`` effect; in ``single-work`` mode it is the invoked Work; every
      decision recorded before it is finalized by a commit of its own; nothing is
      recorded after it but the commit that carries it; and, while that commit is
      not recorded, HEAD's event log does not hold those events yet - that hold:
      only its Git stage is left, and nothing else is decided, asked or run;
    * anything else - ``reconcile required``, with the record left exactly as it
      is.

    A record written before START kept the reason is finished just the same and
    reports the hold without one: what the hold decided is its two events, and
    they are in the record. Where it may be finished is the Mutation Controller's
    to say: it replays and records only on the branch the hold was decided on,
    and refuses a decision that carries no branch at all (``rules/git``: Commit /
    push).
    """
    effects = mutation.effects
    held = [effect for effect in effects if _held_event(effect) is not None]
    if not held:
        return None
    refuse = _hold_refusal(mutation)
    if len(held) > 1:
        raise refuse("more than one work_held event; START holds one Work and then stops")
    if not all(
        isinstance(effect, dict)
        and isinstance(effect.get("stage"), str)
        and isinstance(effect.get("kind"), str)
        and isinstance(effect.get("payload"), dict)
        for effect in effects
    ):
        raise refuse("effects that cannot be read")
    stages = _recorded_stages(effects, refuse)
    by_stage = {name: [effect for effect in effects if effect["stage"] == name] for name in stages}
    (hold_effect,) = held
    stage, position = hold_effect["stage"], stages.index(hold_effect["stage"])
    subject = _held_event(hold_effect).get("entity")

    # the Work: one this START could have held, and the one it was invoked for when it runs one alone
    if not isinstance(subject, str) or not is_valid_id(subject, "work"):
        raise refuse(f"a work_held event for {subject!r}, which is not a Work")
    if mode != "outer" and subject != work_id:
        raise refuse(f"the hold of {subject}, where this single-work START runs {work_id} alone")

    # the stage: the lifecycle stage a hold of that Work records, holding exactly the events it records
    number = len({name for name in stages[:position] if name.startswith(f"{subject}:lifecycle:")})
    if stage != f"{subject}:lifecycle:{number}":
        raise refuse(f"a hold stage named {stage!r}, where the hold of {subject} records it as its next lifecycle stage")
    lifecycle = by_stage[stage]
    events = [effect["payload"].get("record") for effect in lifecycle]
    if len(lifecycle) != len(_HOLD_EVENTS) or not all(
        effect["kind"] == "append_event"
        and isinstance(event, dict)
        and set(event) == _EVENT_FIELDS
        and all(isinstance(event[field], str) and event[field] for field in _EVENT_FIELDS)
        for effect, event in zip(lifecycle, events)
    ):
        raise refuse(f"a hold stage {stage!r} holding something other than the lifecycle events a hold records")
    if [(event["type"], event["entity"]) for event in events] != [(t, subject) for t in _HOLD_EVENTS]:
        raise refuse(f"a hold stage {stage!r} holding other events than the hold of one Work records")
    if any(mutation.reserved(f"{stage}:event:{index}") != event["id"] for index, event in enumerate(events)):
        raise refuse("hold events under IDs the hold did not reserve for them")
    if set(lifecycle[0]["payload"]) != {"record"} or set(lifecycle[-1]["payload"]) not in (
        {"record"},
        {"record", _HOLD_DECISION},
    ):
        raise refuse("hold events carrying something other than the reason on the work_held event")
    reason: object = None
    if _HOLD_DECISION in lifecycle[-1]["payload"]:
        decision = lifecycle[-1]["payload"][_HOLD_DECISION]
        problem = _hold_decision_problem(decision)
        if problem is not None:
            raise refuse(f"a hold decision with {problem}")
        reason = decision["reason"]

    # around it: every decision before the hold finalized by a commit of its own, and after it only the commit
    # carrying the hold - a hold ends the START, so nothing else is decided or run past it
    finalized = max(
        (index for index, name in enumerate(stages[:position]) if any(e["kind"] == "git_commit" for e in by_stage[name])),
        default=-1,
    )
    undecided = [name for name in stages[finalized + 1:position] if _decides(by_stage[name])]
    if undecided:
        raise refuse(f"the decisions {undecided} before the hold that no commit of their own finalizes")
    after = stages[position + 1:]
    committed = bool(after)
    if committed:
        commit_stage = f"commit:{len([name for name in stages[:position + 1] if name.startswith('commit:')])}"
        if after != [commit_stage]:
            raise refuse(f"the stages {after} after the hold stage, where a hold records only its commit {commit_stage!r}")
        work = ProjectView.load(mutation.store).works.get(subject)
        commit = by_stage[commit_stage][0]["payload"]
        paths = commit.get("paths")
        if (
            work is None
            or [effect["kind"] for effect in by_stage[commit_stage]] not in (["git_commit"], ["git_commit", "git_push"])
            or commit.get("message") != f"chore(workline): hold {work.display}"
            or not isinstance(paths, list)
            or not paths
            or not all(isinstance(path, str) for path in paths)
            or not set(paths) <= set(_owned_paths([e for e in effects if e["kind"] in FILE_EFFECT_KINDS]))
        ):
            raise refuse(f"a {commit_stage} stage other than the commit carrying the hold")
    elif _in_head_event_log(mutation.store, [event["id"] for event in events]):
        raise ReconcileRequired(
            f"START mutation {mutation.id} recorded the hold of {subject}, but a commit it did not record already "
            "holds those events, so its own commit and push cannot be shown; it is left pending, exactly as it is: "
            "reconcile required"
        )
    return _ProvenHold(subject, reason, committed)


def start(store: ProjectStore, work_id: str, mode: str, executor: Executor) -> StartResult:
    if mode not in MODES:
        raise ValidationError(f"mode must be one of {MODES}: {mode!r}")
    # Project execution lock (rules/git): everything that decides a write is read
    # under it, the executor runs inside it, and it is released when START
    # returns. A question wait releases it too; the mutation stays pending for
    # the invocation that resumes it under a fresh lock.
    with project_operation(store, OWNER, {"work_id": work_id, "mode": mode}):
        return _start_locked(store, work_id, mode, executor)


def _start_locked(store: ProjectStore, work_id: str, mode: str, executor: Executor) -> StartResult:
    work = store.read_entity("work", work_id)  # stable resolve; no fallback
    # A cancel an interrupted run of this START recorded is answered from its record first: the current Project
    # shows that cancel part-way, and is judged as it stood when the cancel was decided.
    cancel = _cancel_to_finish(store, work, mode)
    view = cancel.view if cancel is not None else _structure_or_stop(store, "start precheck")
    gitops.ensure_git_ready(store.root)
    # Before the mutation exists: an unpinned or drifted push destination STOPs
    # here, with no intent record, no domain write and no network contact.
    destination = gitops.ensure_push_destination(store)

    controller = MutationController(store)
    # invocation identity = the required START inputs (stable Work ID and mode);
    # a pending START mutation on the same Work with another mode is a conflict → reconcile required
    invocation = {"operation": OWNER, "work_id": work_id, "mode": mode}
    mutation = controller.open(OWNER, invocation, WriteScope(entities=(work_id,), files=LEDGER_FILES))
    with abandon_on_stop(mutation):
        if cancel is not None and mutation.id != cancel.mutation_id:
            raise ReconcileRequired(
                f"START resumed mutation {mutation.id}, not {cancel.mutation_id} whose cancel it had shown; both are "
                "left as they are: reconcile required"
            )
        # A terminal lifecycle this mutation recorded without its finalization is
        # answered from the record before anything is replayed or chosen; so is a
        # hold, which is not terminal but is just as much a decision this START
        # already made and must not make again.
        reading = mutation.resumed and cancel is None
        finishing = _completion_to_finish(mutation, work_id, mode) if reading else None
        holding = _hold_to_finish(mutation, work_id, mode) if reading and finishing is None else None
        gitops.record_preexisting_dirty(mutation, store.root)
        mutation.apply()  # resume: replay every recorded effect before continuing
        state = view.work_state(work_id)
        if state.terminal and not mutation.resumed:
            raise SpecViolation(f"Work {work_id} is {state.state}")

        session = _Session(store, mutation, destination, mode, executor)
        phase_id = work.phase_id
        current: Entity | None = work
        result: StartResult
        just_completed: str | None = None
        if cancel is not None:
            # The cancel ends this START as it would have uninterrupted: no other Work is chosen or run after it.
            result = session.finish_cancel(cancel)
        elif finishing is not None:
            result = session.finish_completion(finishing)
        elif holding is not None:
            # The hold ends this START as it would have uninterrupted: no other Work is chosen or run after it.
            result = session.finish_hold(holding)
        elif mutation.resumed:
            ambiguous: str | None = None
            if mode == "outer":
                current, ambiguous = _next_or_ambiguous(session, ProjectView.load(store), phase_id, work, None)
            if ambiguous is not None:
                result = StartResult("stopped", work_id, mutation.id, phase_id=phase_id, detail=ambiguous)
            elif current is None:
                result = StartResult("completed", work_id, mutation.id, phase_id=phase_id)
            else:
                result = session.run_work(current.id)
        else:
            result = session.run_work(work.id)

    while mode == "outer" and result.status in ("completed", "moved"):
        just_completed = result.work_id if result.status == "completed" else None
        view = ProjectView.load(store)
        if phase_id is not None:
            completion = view.phase_completion(phase_id)
            if completion.complete:
                result = StartResult("phase_complete", work_id, mutation.id, tuple(session.completed), phase_id, head=gitcmd.head_commit(store.root))
                break
        nxt, ambiguous = _next_or_ambiguous(session, view, phase_id, work, just_completed)
        if ambiguous is not None:
            result = StartResult("stopped", work_id, mutation.id, tuple(session.completed), phase_id, ambiguous, gitcmd.head_commit(store.root))
            break
        if nxt is None:
            detail = "; ".join(view.phase_completion(phase_id).reasons) if phase_id else "no startable Work in standalone scope"
            result = StartResult("stopped", work_id, mutation.id, tuple(session.completed), phase_id, detail, gitcmd.head_commit(store.root))
            break
        if result.status == "moved" and nxt.id == result.work_id:
            raise StopError(f"outer continuation makes no progress: {nxt.id} was re-selected right after branching", code="no_progress")
        result = session.run_work(nxt.id)

    if result.status != "question_wait":
        _structure_or_stop(store, "postcheck")
        mutation.complete()
    return StartResult(result.status, result.work_id, mutation.id, tuple(session.completed), phase_id, result.detail, result.head)


# --------------------------------------------------------------------------- standalone plan exclusion

def plan_exclude_standalone_work(store: ProjectStore, work_id: str, replan: Replan = Replan()):
    """START-owned plan exclusion of an unstarted standalone Work."""
    with project_operation(store, "start-plan-exclude", {"work_id": work_id}):
        return _plan_exclude_standalone_locked(store, work_id, replan)


def _plan_exclude_standalone_locked(store: ProjectStore, work_id: str, replan: Replan):
    def precheck(view: ProjectView) -> None:
        work = view.works.get(work_id)
        if work is None:
            raise ValidationError(f"Work unresolvable: {work_id}")
        if work.phase_id is not None:
            raise SpecViolation("Phase Work plan exclusion is owned by Roadmap")
        if view.work_state(work_id).state != UNSTARTED:
            raise SpecViolation(f"plan_excluded is only for unstarted Works; {work_id} is {view.work_state(work_id).state}")

    def message(view: ProjectView) -> str:
        return f"chore(workline): plan_excluded {view.works[work_id].display}"

    # Resumed exactly as Roadmap's plan exclusion is (``roadmap._plan_exclude_locked``). The slot names this
    # operation, not START's own invocation: a START record of the same Work is never taken for one of these, and
    # START's own resume (:func:`_completion_to_finish`) reads only the mutation ``_start_locked`` opens.
    slot = {"operation": "start-plan-exclude", "work_id": work_id}
    request = _plan_exclusion_request(work_id, replan)
    resumed = _resume_plan_exclusion(store, OWNER, slot, work_id, replan, request, precheck, message)
    if resumed is not None:
        view = resumed.view
    else:
        view = _structure_or_stop(store, "precheck")
        precheck(view)
    destination = gitops.ensure_push_destination(store)
    controller = MutationController(store)
    mutation = controller.open(OWNER, {**slot, "request": request}, WriteScope(entities=(work_id,), files=LEDGER_FILES))
    gitops.ensure_git_ready(store.root)
    gitops.record_preexisting_dirty(mutation, store.root)
    mutation.apply()
    if resumed is not None:
        work_ids, removals, additions = resumed.work_ids, resumed.removals, resumed.additions
    else:
        with abandon_on_stop(mutation):
            work_ids, removals, additions = plan_replan(mutation, "replan", view, replan)
            projection = projected_view(
                view,
                add_events=[(work_id, "plan_excluded")],
                remove_relation_ids=tuple(r.id for r in removals),
                add_relations=additions,
                add_works={work_ids[k]: spec for k, spec in replan.new_works.items()},
            )
            validate_projection(projection, "plan exclusion replan")
        gitops.ensure_separable_before_effects(mutation, _plan_exclusion_ledgers(replan))
    if not mutation.has_stage("event"):
        mutation.add_effects("event", event_effects(mutation, "event", work_id, ["plan_excluded"]))
    mutation.apply()
    apply_replan(mutation, "replan", replan, removals, additions, work_ids)
    gitops.finalize(
        mutation,
        "finalize",
        message(view),
        owned_canonical_paths(mutation),
        destination=destination,
    )
    _structure_or_stop(store, "postcheck")
    mutation.complete()
    return StartResult("plan_excluded", work_id, mutation.id, head=gitcmd.head_commit(store.root))


__all__ = [
    "Completed", "QuestionWait", "Hold", "Cancel", "DerivedWork", "Derive", "HumanNG", "ExecutionContext",
    "StartResult", "start", "plan_exclude_standalone_work", "reading_plan", "read_obligations",
    "require_read_targets", "completion_precheck", "standalone_scope",
]
