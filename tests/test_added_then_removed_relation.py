"""A relation a mutation added and a later stage of its own removed is not added again (BL-040).

START's Derive registers the Works it derives, and the relations it gives them, in a stage of the START's own
mutation. When a cancel later in the same START removes one of those relations (R), the record holds R's add,
applied, and after it R's removal, naming exactly the relation the add wrote. The Mutation Controller classified
every effect against the Project on its own, and an added relation its file does not hold reads as one not added
yet. From the moment R's removal was written, every replay of the record added R again and removed it once more -
the apply of the cancel's own commit stage included, with no interruption at all - and a retry of a START
interrupted from then on refused its own record: R's add looked unapplied while later effects were applied
(``reconcile_required``), for every such window and every retry. A push preview failing between the second add and
the second removal left R back in its file and the record in that same refusal, with no interruption either.

The record shows why R is missing: the same mutation holds R's add as applied, and recorded the removal of exactly
that relation - the same file, ID and snapshot - in a later stage. The Mutation Controller now classifies such an add
as applied, in the one rule ``Mutation.apply``, ``unapplied_effects`` and the proof of an interrupted cancel share,
whether or not the removal's own applied flag was saved. Nothing else stands for that removal: a relation of the
same shape under another ID, a removal with another snapshot, an add the record does not hold as applied, a removal
recorded before the add or in its stage, and a person's edit the record does not explain keep the classification -
and the refusal - they always had.
"""

from __future__ import annotations

from contextlib import contextmanager
import re
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git
from test_cancel_decision_resume import DECISION, CancelCase, Interrupted
from workline import gitcmd
from workline import start as st
from workline.create import RelationSpec, WorkSpec, create_standalone_work
from workline.errors import GitError, StopError
from workline.ids import new_id
from workline.mutation import MATCHING, Effect, Mutation, MutationController, WriteScope, unapplied_effects
from workline.oplock import project_operation
from workline.ops import Replan
from workline.state import ProjectView
from workline.store import Event, Relation, render_relations
from workline.validate import validate_project

ROADMAP = ".workline/relations/roadmap.yaml"
EVENT_LOG = ".workline/events/events.jsonl"
CANCEL_SUBJECT = "chore(workline): cancel "
#: What the cancel's proof says when an effect it holds as applied follows one it does not (``ops._recorded_progress``).
OUT_OF_ORDER = "applied while an earlier one is not"


def _parts(effect) -> tuple[str, dict]:
    return (effect["kind"], effect["payload"]) if isinstance(effect, dict) else (effect.kind, effect.payload)


def _cancels(effects) -> bool:
    return any(kind == "append_event" and payload["record"]["type"] == "work_cancelled" for kind, payload in map(_parts, effects))


def _carries_cancel(effects) -> bool:
    return any(kind == "git_commit" and payload["message"].startswith(CANCEL_SUBJECT) for kind, payload in map(_parts, effects))


def _cancel_removals(stage: object) -> bool:
    return re.search(r":cancel:\d+:remove$", str(stage)) is not None


# --------------------------------------------------------------------------- interruption windows (effect state)
def after_recording(predicate):
    """Stop right after a stage for which ``predicate(stage, effects)`` holds is durably recorded, none of it applied."""
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        real(mutation, stage, effects)
        if predicate(stage, effects):
            raise Interrupted(f"recorded {stage}")

    return mock.patch.object(Mutation, "add_effects", fire)


def after_applying(predicate):
    """Stop right after the apply that newly applied an effect of a stage for which ``predicate(stage, effects)`` holds."""
    real = Mutation.apply

    def fire(mutation):
        before = {e["seq"] for e in mutation.record["effects"] if e.get("applied")}
        outcome = real(mutation)
        for effect in mutation.record["effects"]:
            stage_effects = [e for e in mutation.record["effects"] if e["stage"] == effect["stage"]]
            if effect.get("applied") and effect["seq"] not in before and predicate(effect["stage"], stage_effects):
                raise Interrupted(f"applied {effect['stage']}")
        return outcome

    return mock.patch.object(Mutation, "apply", fire)


def first_removal_applied():
    """Stop inside the cancel's removal stage: its first removal applied and saved, before the second is applied."""
    real = MutationController.apply_effect
    seen: list[str] = []

    def fire(controller, record):
        if record["kind"] == "remove_relation" and _cancel_removals(record["stage"]):
            if seen:
                raise Interrupted("before the second removal")
            seen.append(record["payload"]["record"]["id"])
        return real(controller, record)

    return mock.patch.object(MutationController, "apply_effect", fire)


@contextmanager
def removal_flag_unsaved():
    """Stop right after the cancel's first removal is written, before the save that records it applied."""
    real_apply, real_save = MutationController.apply_effect, Mutation._save
    state = {"armed": False, "fired": False}

    def apply_effect(controller, record):
        result = real_apply(controller, record)
        if record["kind"] == "remove_relation" and _cancel_removals(record["stage"]) and not state["fired"]:
            state["armed"] = True
        return result

    def save(mutation):
        if state["armed"]:
            state["armed"], state["fired"] = False, True
            raise Interrupted("removal written, its applied flag not saved")
        return real_save(mutation)

    with mock.patch.object(MutationController, "apply_effect", apply_effect), mock.patch.object(Mutation, "_save", save):
        yield


@contextmanager
def around_cancel_push(*, pushed: bool):
    """Stop just before (``pushed=False``) or just after the push of the stage whose commit carries the cancel."""
    real_add, real_apply = Mutation.add_effects, MutationController.apply_effect
    noted: dict[str, str] = {}

    def add_effects(mutation, stage, effects):
        real_add(mutation, stage, effects)
        if _carries_cancel(effects):
            noted["stage"] = stage

    def apply_effect(controller, record):
        ours = record["kind"] == "git_push" and record["stage"] == noted.get("stage")
        if ours and not pushed:
            raise Interrupted("committed, not pushed")
        result = real_apply(controller, record)
        if ours and pushed:
            raise Interrupted("pushed, its applied flag not saved")
        return result

    with mock.patch.object(Mutation, "add_effects", add_effects), mock.patch.object(MutationController, "apply_effect", apply_effect):
        yield


def before_completion():
    def fire(mutation):
        raise Interrupted("every effect applied, the mutation not completed")

    return mock.patch.object(Mutation, "complete", fire)


WINDOWS = {
    "cancel applied": lambda: after_applying(lambda stage, effects: _cancels(effects)),  # W2b
    "removals recorded": lambda: after_recording(lambda stage, effects: _cancel_removals(stage)),  # W2c
    "first removal applied": first_removal_applied,  # W2d
    "removal written, its flag not saved": removal_flag_unsaved,  # W2e
    "removals applied": lambda: after_applying(lambda stage, effects: _cancel_removals(stage)),  # W3
    "commit recorded": lambda: after_recording(lambda stage, effects: _carries_cancel(effects)),  # W4
    "committed": lambda: around_cancel_push(pushed=False),  # W5
    "pushed": lambda: around_cancel_push(pushed=True),  # W6
    "before completion": before_completion,  # W6b
}

# What a retry of S1 still executes from each window once R's removal has been written - never R again.
LEFT = {
    "first removal applied": ["remove_relation", "git_commit", "git_push"],
    "removal written, its flag not saved": ["remove_relation", "git_commit", "git_push"],
    "removals applied": ["git_commit", "git_push"],
    "commit recorded": ["git_commit", "git_push"],
    "committed": ["git_push"],
    "pushed": [],
    "before completion": [],
}


@contextmanager
def relation_writes():
    """Every relation effect written inside the block, as (kind, relation ID), in the order written."""
    written: list[tuple[str, str]] = []
    real = MutationController.apply_effect

    def watch(controller, record):
        result = real(controller, record)
        if record["kind"] in ("add_relation", "remove_relation"):
            written.append((record["kind"], record["payload"]["record"]["id"]))
        return result

    with mock.patch.object(MutationController, "apply_effect", watch):
        yield written


@contextmanager
def push_preview_fails_once(case: "PairCase"):
    """The first ``git push --dry-run`` once the cancel's commit stage is recorded fails, as an unreachable remote does.

    Yields, for that failure, whether the relation under test was in its file at that moment.
    """
    real_add, real_preview = Mutation.add_effects, gitcmd.push_dry_run
    state = {"armed": any(_carries_cancel(p["effects"]) for p in MutationController(case.store).list_pending()), "fired": False}
    present: list[bool] = []

    def add_effects(mutation, stage, effects):
        real_add(mutation, stage, effects)
        if _carries_cancel(effects):
            state["armed"] = True

    def preview(repo, remote, branch):
        if state["armed"] and not state["fired"]:
            state["fired"] = True
            present.append(case.r["id"] in case.relation_ids())
            raise GitError(f"cannot preview the push to {remote}: Network is unreachable")
        return real_preview(repo, remote, branch)

    with mock.patch.object(Mutation, "add_effects", add_effects), mock.patch.object(gitcmd, "push_dry_run", preview):
        yield present


# --------------------------------------------------------------------------- the Project and the START under test
class PairCase(CancelCase):
    """Phase A (W1 -planned_next-> W2, integration I1) and a START that derives F and then cancels, as ``shape`` says.

    The relation under test (``self.r``) is the one the cancel's decision is about:

    * S1  single-work: W1 derives F with planned_next W1->F (R); W1's cancel removes R and W1->I1.
    * S2  single-work: W1 derives F returning to W1 (R = return_to F->W1, added by the Derive itself, which the
      cancel of W1 must remove); W1's cancel removes R and W1->I1.
    * S6  outer: S1.
    * S7  outer: W1 derives F with requires_completion F->W2 (R) and completes; F, chosen next, is cancelled,
      removing R and F->I1.
    * S3d single-work, no pair: W1 derives F; W1's cancel removes the planned_next W1->W2 the Phase entry made
      (the relation under test) and W1->I1.
    * S4  single-work, no pair: W1 derives F with planned_next W1->F (R); W1's cancel removes W1->I1 only.
    * S8  no pair in one record: W1 derives F with planned_next W1->F (R) in a START that moves on and completes its
      mutation; the START under test cancels W1, removing R and W1->I1.
    """

    CANCELLED = {"S7": "F"}

    def world(self, shape: str, name: str | None = None):
        if name is not None:
            self.build(name)
        roadmap = self.simple_roadmap(self.store)
        self.rid, self.pa = roadmap.roadmap_id, roadmap.phase_ids["a"]
        entry = self.simple_entry(self.store, self.pa, {"w1": "W1 done", "w2": "W2 done"}, planned_next=(("w1", "w2"),))
        self.w1, self.w2, self.i1 = entry.work_ids["w1"], entry.work_ids["w2"], entry.integration_id
        self.r: dict | None = None
        executor = self.deciding(shape)
        mode = "outer" if shape in ("S6", "S7") else "single-work"
        if shape == "S8":
            self.assertEqual(st.start(self.store, self.w1, "single-work", executor).status, "moved")
            self.assertEqual(MutationController(self.store).list_pending(), [])
        return lambda: st.start(self.store, self.w1, mode, executor)

    def deciding(self, shape: str):
        """Decides from the Project alone, so a retry that asked it again would decide exactly the same."""
        done = completing_executor(self.store, self.ran)
        cancelled = self.CANCELLED.get(shape, "W1")

        def relation(rel_type: str, a: str, b: str) -> Relation:
            (found,) = [r for r in ProjectView.load(self.store).roadmap_relations if (r.type, r.from_id, r.to) == (rel_type, a, b)]
            return found

        def execute(ctx: st.ExecutionContext):
            derived = [work.id for work in ctx.view.works.values() if work.name == "F"]
            if ctx.work.id == self.w1 and not derived:
                self.ran.append(ctx.work.id)
                relations = {
                    "S1": (RelationSpec("planned_next", self.w1, "f"),),
                    "S4": (RelationSpec("planned_next", self.w1, "f"),),
                    "S6": (RelationSpec("planned_next", self.w1, "f"),),
                    "S8": (RelationSpec("planned_next", self.w1, "f"),),
                    "S7": (RelationSpec("requires_completion", "f", self.w2),),
                }.get(shape, ())
                derived_work = st.DerivedWork("F", "fixed", return_to=shape == "S2")
                return st.Derive({"f": derived_work}, relations=relations, move=shape == "S8")
            if ctx.work.name != cancelled:
                return done(ctx)
            self.ran.append(ctx.work.id)
            (f,) = derived
            under_test = {
                "S2": ("return_to", f, self.w1),
                "S7": ("requires_completion", f, self.w2),
                "S3d": ("planned_next", self.w1, self.w2),
            }.get(shape, ("planned_next", self.w1, f))
            self.r = relation(*under_test).to_record()
            removals = [] if shape == "S4" else [self.r["id"]]
            removals.append(relation("requires_completion", ctx.work.id, self.i1).id)
            return st.Cancel(Replan(remove_relation_ids=tuple(removals)), "not needed")

        return execute

    # observation --------------------------------------------------------------
    def cancelled_work(self, shape: str) -> str:
        return self.named("F")[0] if shape in self.CANCELLED else self.w1

    def relation_ids(self) -> set[str]:
        return {relation.id for relation in ProjectView.load(self.store).roadmap_relations}

    def of_r(self, written: list[tuple[str, str]]) -> list[str]:
        return [kind for kind, relation_id in written if relation_id == self.r["id"]]

    def effect_of_r(self, record: dict, kind: str) -> dict:
        (effect,) = [e for e in record["effects"] if e["kind"] == kind and e["payload"]["record"]["id"] == self.r["id"]]
        return effect

    # edits between the interruption and the retry ------------------------------
    def write_relations(self, relations: list[Relation]) -> None:
        (self.store.root / ROADMAP).write_text(render_relations(relations), encoding="utf-8", newline="\n")

    def without_r(self) -> None:
        self.write_relations([r for r in ProjectView.load(self.store).roadmap_relations if r.id != self.r["id"]])

    def interrupted(self, shape: str, window: str, name: str | None = None):
        call = self.world(shape, name)
        return call, self.interrupt(WINDOWS[window], call)


# --------------------------------------------------------------------------- no interruption
class UninterruptedTests(PairCase):
    def test_the_relation_is_added_once_and_removed_once(self) -> None:
        for index, shape in enumerate(("S1", "S2", "S6", "S7")):
            with self.subTest(shape=shape):
                call = self.world(shape, f"once-{index}")
                with relation_writes() as written:
                    result = call()

                work = self.cancelled_work(shape)
                self.assertEqual((result.status, result.work_id), ("cancelled", work))
                self.assertEqual(self.of_r(written), ["add_relation", "remove_relation"])  # not added back by the commit stage
                self.assertNotIn(self.r["id"], self.relation_ids())
                self.assertCancelled(work)

    def test_a_push_preview_failing_once_the_cancel_commit_is_recorded_leaves_the_relation_removed(self) -> None:
        call = self.world("S1")
        with relation_writes() as written:
            with push_preview_fails_once(self) as present, self.assertRaises(GitError):
                call()
            self.assertEqual(present, [False])  # R was not back in its file when the preview failed
            (pending,) = MutationController(self.store).list_pending()
            self.assertTrue(any(_carries_cancel([e]) for e in pending["effects"]))
            self.assertNotIn(self.r["id"], self.relation_ids())
            self.assertEqual(validate_project(self.store), [])

            result = call()

        self.assertEqual((result.status, result.mutation_id), ("cancelled", pending["mutation_id"]))
        self.assertEqual(self.ran, [self.w1, self.w1])
        self.assertEqual(self.of_r(written), ["add_relation", "remove_relation"])
        self.assertCancelled(self.w1)


# --------------------------------------------------------------------------- interrupted once the relation is removed
class RemovedTests(PairCase):
    def test_every_window_from_the_removal_on_carries_on_without_adding_the_relation_again(self) -> None:
        cases = [("S1", window) for window in LEFT] + [("S2", "removals applied"), ("S6", "removals applied"),
                                                        ("S7", "removals applied"), ("S6", "committed")]
        for index, (shape, window) in enumerate(cases):
            with self.subTest(shape=shape, window=window):
                with relation_writes() as written:
                    call, pending = self.interrupted(shape, window, f"removed-{index}")
                    self.assertNotIn(self.r["id"], self.relation_ids())
                    self.assertTrue(self.effect_of_r(pending, "add_relation")["applied"])
                    ran, executed = list(self.ran), []

                    result = self.watching(call, executed)

                work = self.cancelled_work(shape)
                self.assertEqual((result.status, result.work_id, result.mutation_id), ("cancelled", work, pending["mutation_id"]))
                self.assertEqual(self.ran, ran)  # the executor was not asked again
                if shape == "S1":
                    self.assertEqual(executed, LEFT[window])
                self.assertEqual(self.of_r(written), ["add_relation", "remove_relation"])
                self.assertCancelled(work)

    def test_a_removal_written_before_its_applied_flag_was_saved_explains_the_missing_relation(self) -> None:
        with relation_writes() as written:
            call, pending = self.interrupted("S1", "removal written, its flag not saved")
            self.assertFalse(self.effect_of_r(pending, "remove_relation")["applied"])  # written, not recorded as applied
            self.assertNotIn(self.r["id"], self.relation_ids())
            executed: list[str] = []

            result = self.watching(call, executed)

        self.assertEqual((result.status, result.mutation_id), ("cancelled", pending["mutation_id"]))
        self.assertEqual(executed, ["remove_relation", "git_commit", "git_push"])  # W1->I1's removal; not R's again
        self.assertEqual(self.of_r(written), ["add_relation", "remove_relation"])
        self.assertTrue(self.effect_of_r(self.record_of(pending["mutation_id"]), "remove_relation")["applied"])
        self.assertCancelled(self.w1)

    def test_a_retry_whose_push_preview_fails_once_converges_on_the_next_retry(self) -> None:
        for index, window in enumerate(("removals applied", "committed")):
            with self.subTest(window=window):
                with relation_writes() as written:
                    call, pending = self.interrupted("S1", window, f"twice-{index}")
                    with push_preview_fails_once(self) as present, self.assertRaises(GitError):
                        call()
                    self.assertEqual(present, [False])
                    self.assertNotIn(self.r["id"], self.relation_ids())

                    result = call()

                self.assertEqual((result.status, result.mutation_id), ("cancelled", pending["mutation_id"]))
                self.assertEqual(self.ran, [self.w1, self.w1])
                self.assertEqual(self.of_r(written), ["add_relation", "remove_relation"])
                self.assertCancelled(self.w1)

    def test_on_a_branch_without_the_cancel_commit_nothing_is_written_and_the_recorded_branch_goes_on(self) -> None:
        call = self.world("S1")
        git(self.store.root, "branch", "side")  # holds none of what the START commits
        pending = self.interrupt(WINDOWS["committed"], call)
        remote = self.remote_head()
        git(self.store.root, "checkout", "-q", "side")

        self.assertStoppedUntouched([pending["mutation_id"]], call)

        self.assertEqual(self.remote_head(), remote)  # nothing pushed
        git(self.store.root, "checkout", "-q", "main")  # Git lets the person go back: nothing was written over
        with relation_writes() as written:
            result = call()
        self.assertEqual((result.status, result.mutation_id), ("cancelled", pending["mutation_id"]))
        self.assertEqual(written, [])
        self.assertCancelled(self.w1)


# --------------------------------------------------------------------------- the removal recorded, the relation deleted by hand (D-2)
class DeletedByHandTests(PairCase):
    def test_deleting_the_relation_after_its_removal_was_recorded_ends_as_that_removal_would(self) -> None:
        """The state a removal written before its flag was saved leaves, and the one its twin leaves: both go on."""
        for index, shape in enumerate(("S1", "S3d")):
            with self.subTest(shape=shape):
                call, pending = self.interrupted(shape, "removals recorded", f"by-hand-{index}")
                self.assertFalse(self.effect_of_r(pending, "remove_relation")["applied"])
                self.without_r()
                executed: list[str] = []

                result = self.watching(call, executed)

                self.assertEqual((result.status, result.mutation_id), ("cancelled", pending["mutation_id"]))
                self.assertEqual(executed, ["remove_relation", "git_commit", "git_push"])  # W1->I1 only
                self.assertNotIn(self.r["id"], self.relation_ids())
                self.assertCancelled(self.w1)


# --------------------------------------------------------------------------- never taken over
class NotItsOwnTests(PairCase):
    def test_a_relation_of_the_same_shape_under_another_id_is_left_and_stops_the_retry(self) -> None:
        for index, (shape, window) in enumerate((("S1", "removals applied"), ("S1", "committed"), ("S3d", "removals applied"))):
            with self.subTest(shape=shape, window=window):
                call, pending = self.interrupted(shape, window, f"foreign-{index}")
                foreign = Relation(new_id("relation"), self.r["type"], self.r["from"], self.r["to"])
                self.write_relations(ProjectView.load(self.store).roadmap_relations + [foreign])

                refused = self.assertStoppedUntouched([pending["mutation_id"]], call, code="structure_invalid")

                self.assertIn("start precheck", refused.message)
                self.assertIn(foreign.id, self.relation_ids())
                self.assertNotIn(self.r["id"], self.relation_ids())

    def test_the_relation_put_back_under_its_id_as_another_relation_stops_the_retry(self) -> None:
        call, pending = self.interrupted("S1", "removals applied")
        changed = Relation(self.r["id"], "requires_completion", self.r["from"], self.r["to"])
        self.write_relations(ProjectView.load(self.store).roadmap_relations + [changed])

        refused = self.assertStoppedUntouched([pending["mutation_id"]], call)

        self.assertIn("applied with an unexpected result", refused.message)

    def test_an_edit_the_record_does_not_explain_stops_the_retry(self) -> None:
        cases = (
            ("S1", "cancel applied", "R deleted before its removal was recorded", lambda case: case.without_r()),
            ("S4", "removals applied", "a Derive-added R the cancel keeps deleted", lambda case: case.without_r()),
            ("S1", "removals applied", "R put back exactly as it was added",
             lambda case: case.write_relations(ProjectView.load(case.store).roadmap_relations + [Relation.from_record(case.r)])),
            ("S1", "committed", "R put back exactly as it was added",
             lambda case: case.write_relations(ProjectView.load(case.store).roadmap_relations + [Relation.from_record(case.r)])),
        )
        for index, (shape, window, label, edit) in enumerate(cases):
            with self.subTest(shape=shape, window=window, edit=label):
                call, pending = self.interrupted(shape, window, f"edit-{index}")
                edit(self)

                refused = self.assertStoppedUntouched([pending["mutation_id"]], call)

                self.assertIn(OUT_OF_ORDER, refused.message)

    def test_a_record_the_rule_cannot_read_as_its_own_removal_stops_the_retry(self) -> None:
        def unapplied_add(case, record):
            case.effect_of_r(record, "add_relation")["applied"] = False

        def another_snapshot(case, record):
            """The removal, and the decision it is proven against, name the relation with a field the add did not write."""
            case.effect_of_r(record, "remove_relation")["payload"]["record"]["note"] = "changed"
            (decided,) = [r for r in case.cancel_effect(record, case.w1)["payload"][DECISION]["remove_relations"]
                          if r["id"] == case.r["id"]]
            decided["note"] = "changed"

        for index, (label, change) in enumerate((("the add not recorded as applied", unapplied_add),
                                                  ("the removal recorded with another snapshot", another_snapshot))):
            with self.subTest(record=label):
                call, pending = self.interrupted("S1", "removals applied", f"record-{index}")
                self.edit_record(pending, lambda record: change(self, record))  # noqa: B023

                refused = self.assertStoppedUntouched([pending["mutation_id"]], call)

                self.assertIn(OUT_OF_ORDER, refused.message)

    def test_a_cancel_recorded_without_its_decision_still_stops(self) -> None:
        call, pending = self.interrupted("S1", "removals applied")
        self.edit_record(pending, lambda record: self.cancel_effect(record, self.w1)["payload"].pop(DECISION))

        refused = self.assertStoppedUntouched([pending["mutation_id"]], call)

        self.assertIn("without the decision", refused.message)


# --------------------------------------------------------------------------- no pair in the record
class ControlTests(PairCase):
    def test_a_cancel_with_no_relation_its_own_mutation_added_carries_on_as_before(self) -> None:
        for index, (shape, window) in enumerate((("S3d", None), ("S3d", "removals applied"), ("S3d", "committed"),
                                                 ("S4", None), ("S4", "removals applied"), ("S8", "removals applied"))):
            with self.subTest(shape=shape, window=window):
                call = self.world(shape, f"control-{index}")  # S8: R is added by a START of its own, before this one
                with relation_writes() as written:
                    pending = self.interrupt(WINDOWS[window], call) if window else None
                    result = call()

                self.assertEqual(result.status, "cancelled")
                if pending is not None:
                    self.assertEqual(result.mutation_id, pending["mutation_id"])
                if shape == "S4":  # the relation the Derive added and the cancel kept
                    self.assertEqual(self.of_r(written), ["add_relation"])
                    self.assertIn(self.r["id"], self.relation_ids())
                else:  # a relation this START did not add: removed once
                    self.assertEqual(self.of_r(written), ["remove_relation"])
                    self.assertNotIn(self.r["id"], self.relation_ids())
                self.assertCancelled(self.w1)


# --------------------------------------------------------------------------- the rule on the Mutation Controller's own records
class ControllerRuleTests(WorklineTestCase):
    OWNER = "relation-pair-test"

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.a, self.b = (create_standalone_work(self.store, WorkSpec(name, name.lower())).work_id for name in ("A", "B"))
        lock = project_operation(self.store, self.OWNER)
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)
        self.controller = MutationController(self.store)

    def open_mutation(self):
        # One record at a time: an earlier case's record, left pending, would overlap the write scope.
        for record in self.controller.list_pending():
            self.controller.load(record["mutation_id"]).complete()
        return self.controller.open(self.OWNER, {"operation": self.OWNER}, WriteScope(files=(ROADMAP, EVENT_LOG)))

    def recorded_pair(self) -> tuple[Relation, str]:
        """A mutation that added relation R and removed exactly R in a later stage, each stage applied before the next."""
        relation = Relation(new_id("relation"), "planned_next", self.a, self.b)
        mutation = self.open_mutation()
        mutation.add_effects("add", [Effect.add_relation("roadmap", relation)])
        mutation.apply()
        mutation.add_effects("remove", [Effect.remove_relation("roadmap", relation)])
        mutation.apply()
        self.assertNotIn(relation.id, {r.id for r in self.store.read_relation_file("roadmap")})
        return relation, mutation.id

    def replayed(self, mutation_id: str, change=None) -> tuple[list[int], list[tuple[str, object]], str | None]:
        """For the record as ``change`` leaves it in memory: the seqs :func:`unapplied_effects` lists, what
        :meth:`Mutation.apply` then writes, and the code it stops with (``None`` when it goes through)."""
        mutation = self.controller.load(mutation_id)
        if change is not None:
            change(mutation.record)
        unapplied = [e["seq"] for e in unapplied_effects(mutation)]
        written: list[tuple[str, object]] = []
        real = MutationController.apply_effect

        def watch(controller, record):
            written.append((record["kind"], (record["payload"].get("record") or {}).get("id")))
            return real(controller, record)

        with mock.patch.object(MutationController, "apply_effect", watch):
            try:
                mutation.apply()
            except StopError as exc:
                return unapplied, written, exc.code
        return unapplied, written, None

    def test_an_add_its_own_later_stage_removed_exactly_is_applied_whatever_the_removal_flag(self) -> None:
        for label, change in (
            ("as recorded", None),
            ("the removal's applied flag not saved", lambda record: record["effects"][1].update(applied=False)),
        ):
            with self.subTest(record=label):
                _, mutation_id = self.recorded_pair()

                self.assertEqual(self.replayed(mutation_id, change), ([], [], None))

        with self.subTest(record="only the fields every recorded effect has"):
            _, mutation_id = self.recorded_pair()
            mutation = self.controller.load(mutation_id)
            mutation.record["effects"] = [
                {key: effect[key] for key in ("seq", "stage", "kind", "payload", "applied")} for effect in mutation.effects
            ]
            self.assertEqual(unapplied_effects(mutation), [])

    def test_an_add_no_later_stage_of_its_own_removed_exactly_is_classified_as_it_always_was(self) -> None:
        def another_snapshot(record):
            record["effects"][1]["payload"]["record"]["note"] = "changed"

        def another_relation(record):
            record["effects"][1]["payload"]["record"]["id"] = new_id("relation")

        def same_stage(record):
            record["effects"][1]["stage"] = record["effects"][0]["stage"]

        def removal_first(record):
            record["effects"].reverse()

        for label, change in (
            ("the add not recorded as applied", lambda record: record["effects"][0].update(applied=False)),
            ("the removal recorded with another snapshot", another_snapshot),
            ("the removal naming another relation of the same shape", another_relation),
            ("the removal recorded in the add's own stage", same_stage),
            ("the removal recorded before the add", removal_first),
        ):
            with self.subTest(record=label):
                relation, mutation_id = self.recorded_pair()

                unapplied, written, _ = self.replayed(mutation_id, change)

                self.assertEqual(unapplied[:1], [1])  # seq 1, the add: still to write, as ever
                self.assertEqual(written[:1], [("add_relation", relation.id)])

    def test_the_finalized_branch_guard_still_stops_before_writing_anything_else_again(self) -> None:
        """BL-038: off the commit's branch the guard stops on what would be written again - not on the removed relation."""
        repo = self.store.root
        git(repo, "branch", "side")
        relation = Relation(new_id("relation"), "planned_next", self.a, self.b)
        event = Event(new_id("event"), "work_started", self.a, "2026-09-15T00:00:00+00:00")
        mutation = self.open_mutation()
        stages = (
            ("decide", [Effect.add_relation("roadmap", relation), Effect.append_event(event)]),
            ("commit:0", None),
            ("remove", [Effect.remove_relation("roadmap", relation)]),
            ("commit:1", None),
        )
        for stage, effects in stages:
            if effects is None:
                effects = [Effect.git_commit(f"test: {stage}", [ROADMAP, EVENT_LOG], gitcmd.head_commit(repo), gitcmd.current_branch_ref(repo))]
            mutation.add_effects(stage, effects)
            mutation.apply()
        git(repo, "checkout", "-q", "side")
        before = (mutation.path.read_bytes(), (repo / ROADMAP).read_bytes(), (repo / EVENT_LOG).read_bytes(), gitcmd.head_commit(repo))

        with self.assertRaises(StopError) as stopped:
            self.controller.load(mutation.id).apply()

        self.assertEqual(stopped.exception.code, "reconcile_required")
        self.assertIn("applied effect 2 (append_event", stopped.exception.message)  # the event, not the removed relation
        self.assertEqual((mutation.path.read_bytes(), (repo / ROADMAP).read_bytes(), (repo / EVENT_LOG).read_bytes(),
                          gitcmd.head_commit(repo)), before)
        git(repo, "checkout", "-q", "main")
        self.assertEqual(self.replayed(mutation.id), ([], [], None))  # back on main nothing is written again
        self.assertEqual([c for _, c in self.controller.load(mutation.id).apply()], [MATCHING] * 5)


if __name__ == "__main__":
    unittest.main()
