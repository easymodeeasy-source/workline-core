"""START registers a derivation it decided instead of deciding it again (BL-046).

A derivation is the executor's decision: START records it as a registration stage
- the fix Work's file, its derivation detail and its relations - carrying the
branch it was decided on, and the commit that finalizes it. But a resumed START
read only the current state, fell back into the cycle that had decided it, asked
the executor again and recorded whatever came back as *another* derivation. The
stage is named from the stages already recorded and every reserved ID hangs off
that name, so the second registration produced another Work, another derivation
detail and another pair of relations, and the only duplicate guard there is (a
stage recorded twice) never fired.

No interruption was needed. A question wait right after a derivation ends the
START with the record pending, and the invocation that answers it starts the
Work's cycles from the first one again - so the supported derive → ask → answer
flow registered the fix Work twice, committed and pushed both, and returned
``completed`` with nothing to see. An interrupted one grew another fix Work on
every retry, without bound, and ``validate_project`` reported none of it.

A resumed START now reads its record for the derivations it decided, as it
already reads it for a completion (BL-031), a cancel (BL-030) and a hold
(BL-044). The outcome the executor returned is kept before the stage that
registers it exists, so no recorded registration is ever without the decision
that made it. Cycles whose derivation the record holds register that same one -
the recorded stage is shown to be the registration that decision makes
(``ops._registration_matches``, BL-045, so a Work another owner registered
meanwhile cannot renumber it out of recognition) and is read back rather than
registered again, exactly as a replayed replan's registration is. A derivation
that removed its Work's target ends that Work's cycle, so it is finished from the
record through its Git stage alone - otherwise the resume re-opens the Work and
doubles its lifecycle events too. Anything the record cannot show is
``reconcile required`` with the record, the Project and Git left exactly as they
are, and a record written before START kept its derivations asks the executor
again exactly as it always did.
"""

from __future__ import annotations

import json
import re
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git
from workline import start as st
from workline import yamlish
from workline.create import WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.ids import new_id
from workline.mutation import Mutation, MutationController
from workline.state import ProjectView
from workline.store import WORK_DESIRED_HEADING, WORKLINE_DIR, ProjectStore
from workline.validate import validate_project

EVENT_LOG = f"{WORKLINE_DIR}/events/events.jsonl"
ROADMAP_YAML = f"{WORKLINE_DIR}/relations/roadmap.yaml"


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone."""


# --------------------------------------------------------------------------- interruption windows
def before_keeping():
    """Stop after the executor returned the derivation and before the record keeps it."""
    real = Mutation.set_note

    def fire(mutation, key, value):
        if key == st._DERIVATIONS:
            raise Interrupted("before keeping the derivation")
        return real(mutation, key, value)

    return mock.patch.object(Mutation, "set_note", fire)


def before_recording(pattern: str):
    """Stop with a stage matching ``pattern`` about to be recorded."""
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        if re.search(pattern, stage):
            raise Interrupted(f"about to record {stage}")
        return real(mutation, stage, effects)

    return mock.patch.object(Mutation, "add_effects", fire)


def after_recording(pattern: str):
    """Stop right after a stage matching ``pattern`` is recorded, none of it applied."""
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        real(mutation, stage, effects)
        if re.search(pattern, stage):
            raise Interrupted(f"recorded {stage}")

    return mock.patch.object(Mutation, "add_effects", fire)


def after_writing_one(pattern: str):
    """Stop once exactly one effect of a stage matching ``pattern`` is applied and flagged."""
    real = MutationController.apply_effect
    seen = {"n": 0}

    def fire(controller, record):
        if re.search(pattern, record["stage"]):
            if seen["n"] >= 1:
                raise Interrupted(f"applied one effect of {record['stage']}")
            seen["n"] += 1
        return real(controller, record)

    return mock.patch.object(MutationController, "apply_effect", fire)


def after_applying(pattern: str):
    """Stop right after the call that applied a stage matching ``pattern``."""
    real = Mutation.apply

    def fire(mutation):
        before = {e["seq"] for e in mutation.record.get("effects") or [] if e.get("applied")}
        outcome = real(mutation)
        if any(e.get("applied") and e["seq"] not in before and re.search(pattern, e["stage"])
               for e in mutation.record.get("effects") or []):
            raise Interrupted(f"applied {pattern}")
        return outcome

    return mock.patch.object(Mutation, "apply", fire)


def before_pushing():
    """Stop with the derivation's commit made and its push not made."""
    real = MutationController.apply_effect

    def fire(controller, record):
        if record["kind"] == "git_push":
            raise Interrupted("committed, not pushed")
        return real(controller, record)

    return mock.patch.object(MutationController, "apply_effect", fire)


# Every window from the moment the derivation is decided, and what is left to do from each.
# "decision kept" is not a window a raised exception can reach: the registration that would
# record the stage is what raises, and a refused registration deliberately forgets the
# decision with it. It is built instead (:meth:`DerivationCase.keep_without_recording`) from
# the state a process killed there leaves: the decision kept, its IDs reserved, no stage.
WINDOWS = {
    "registration recorded": lambda: after_recording(r":derive:0$"),
    "one effect applied": lambda: after_writing_one(r":derive:0$"),
    "registration applied": lambda: after_applying(r":derive:0$"),
    "commit recorded": lambda: after_recording(r"^commit:0$"),
    "committed": before_pushing,
}


def by_attempt(log: list[str], script: dict, default=None):
    """Executor scripted by Work name and ``ctx.attempt``.

    A double scripted by how many times it has been called answers a resumed run
    with the *next* outcome, which is what hid this defect: the retry's first
    cycle asked again and was handed the completion the second cycle should have
    got. Keyed on the attempt, a resumed run is asked exactly what an
    uninterrupted one is asked.
    """

    def execute(ctx: st.ExecutionContext):
        log.append(f"{ctx.work.name}#{ctx.attempt}")
        outcome = script.get((ctx.work.name, ctx.attempt), script.get(ctx.work.name))
        if outcome is None:
            if default is None:
                raise AssertionError(f"no outcome scripted for {ctx.work.name} attempt {ctx.attempt}")
            return default(ctx)
        return outcome(ctx) if callable(outcome) else outcome

    return execute


class DerivationCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.root = self.store.root
        self.ran: list[str] = []
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A")})
        self.pa = roadmap.phase_ids["a"]
        entry = self.simple_entry(self.store, self.pa, {"w1": "W1 done"})
        self.w1, self.i1 = entry.work_ids["w1"], entry.integration_id

    # the calls under test ----------------------------------------------------
    def fix(self, name: str = "Fix", **kwargs) -> st.DerivedWork:
        return st.DerivedWork(name, f"{name} done", derivation_detail=f"why {name}", **kwargs)

    def deriving(self, script: dict | None = None, *, mode: str = "single-work", work_id: str | None = None):
        """W1 derives one fix Work on its first attempt and completes on its second."""
        script = script or {("W1", 1): st.Derive({"fix": self.fix()})}
        executor = by_attempt(self.ran, script, default=completing_executor(self.store))
        return lambda: st.start(self.store, work_id or self.w1, mode, executor)

    def interrupt(self, window, call) -> dict:
        with window(), self.assertRaises(Interrupted):
            call()
        (pending,) = MutationController(self.store).list_pending()
        return pending

    def keep_without_recording(self, call) -> dict:
        """The state a process killed between keeping the decision and recording its stage leaves.

        The kill is not an exception: it is between the save that keeps the decision and the
        save that records the stage, so the record holds the decision and the IDs reserved
        for that stage, and no effect of it. Reached here by taking the stage back out of a
        record that has it, which is the same record byte for byte.
        """
        pending = self.interrupt(WINDOWS["registration recorded"], call)
        stage = f"{self.w1}:derive:0"
        self.edit_record(pending, lambda record: record.update(
            {"effects": [e for e in record["effects"] if e["stage"] != stage]}))
        return MutationController(self.store).list_pending()[0]

    def watching(self, call, executed: list[str], stages: list[str]):
        real_apply, real_add = MutationController.apply_effect, Mutation.add_effects

        def apply(controller, record):
            executed.append(record["kind"])
            return real_apply(controller, record)

        def add(mutation, stage, effects):
            stages.append(stage)
            return real_add(mutation, stage, effects)

        with mock.patch.object(MutationController, "apply_effect", apply), mock.patch.object(Mutation, "add_effects", add):
            return call()

    # observation ------------------------------------------------------------
    def works_named(self, name: str) -> list[str]:
        return sorted(w.id for w in ProjectView.load(self.store).works.values() if w.name == name)

    def display(self, work_id: str) -> str:
        return ProjectView.load(self.store).works[work_id].display

    def events(self, work_id: str) -> list[str]:
        return [e.type for e in ProjectView.load(self.store).events if e.entity == work_id]

    def committed_events(self, work_id: str) -> list[str]:
        text = git(self.root, "show", f"HEAD:{EVENT_LOG}", check=False)
        return [json.loads(line)["type"] for line in text.splitlines()
                if line.strip() and json.loads(line)["entity"] == work_id]

    def relations(self) -> list[tuple[str, str, str]]:
        return sorted((r.type, r.from_id, r.to) for r in ProjectView.load(self.store).roadmap_relations)

    def derivation_files(self) -> list[str]:
        area = self.root / f"{WORKLINE_DIR}/derivations"
        return sorted(p.name for p in area.glob("*.md")) if area.is_dir() else []

    def subjects(self) -> list[str]:
        return git(self.root, "log", "--format=%s").splitlines()

    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return git(self.remote_path(), "rev-parse", "main").strip()

    def dirty(self) -> list[str]:
        status = git(self.root, "status", "--porcelain", "--untracked-files=all").splitlines()
        return [line for line in status if ".workline/runtime/" not in line]

    def record_of(self, mutation_id: str) -> dict:
        (record,) = [r for r in MutationController(self.store).list_records() if r["mutation_id"] == mutation_id]
        return record

    def stage_names(self, record: dict) -> list[str]:
        names: list[str] = []
        for effect in record.get("effects") or []:
            if effect["stage"] not in names:
                names.append(effect["stage"])
        return names

    def snapshot(self) -> dict:
        """Everything a refused resume must leave exactly as it was: the records byte for byte, the Project, Git."""
        return {
            "records": {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))},
            "files": {p.relative_to(self.root).as_posix(): p.read_bytes()
                      for p in sorted((self.root / ".workline").rglob("*"))
                      if p.is_file() and "runtime" not in p.relative_to(self.root).parts},
            "head": self.head(),
            "remote": self.remote_head(),
            "dirty": self.dirty(),
        }

    def edit_record(self, pending: dict, change) -> None:
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        change(record)
        path.write_text(yamlish.dump(record), encoding="utf-8")

    # assertions -------------------------------------------------------------
    def assertDerivedOnce(self, name: str = "Fix") -> str:
        """Exactly what one uninterrupted derivation of ``name`` leaves: one Work, one detail, one relation pair."""
        (fix,) = self.works_named(name)
        self.assertEqual(len(self.derivation_files()), len(self.works_named(name)))
        self.assertIn(("derived", self.w1, fix), self.relations())
        self.assertEqual([r for r in self.relations() if r[2] == fix], [("derived", self.w1, fix)])
        self.assertEqual(sum(1 for r in self.relations() if r[1] == fix), 1)
        self.assertEqual(validate_project(self.store), [])
        return fix

    def assertConverged(self, result, *, ran: list[str], status: str = "completed") -> str:
        """The resume ends as the uninterrupted run does: one fix Work, one derive commit, pushed, nothing pending."""
        self.assertEqual((result.status, result.work_id), (status, self.w1))
        fix = self.assertDerivedOnce()
        self.assertEqual(self.subjects().count(f"chore(workline): derive from {self.display(self.w1)}"), 1)
        self.assertEqual(self.ran, ran)
        self.assertEqual((self.head(), self.dirty()), (self.remote_head(), []))
        self.assertEqual(MutationController(self.store).list_pending(), [])
        return fix

    def assertUntouched(self, call, before: dict) -> ReconcileRequired:
        """Refused before anything is replayed, recorded or run, with the record and the Project as they were."""
        ran, executed, stages = list(self.ran), [], []
        with self.assertRaises(ReconcileRequired) as refused:
            self.watching(call, executed, stages)
        self.assertEqual((executed, stages, self.ran), ([], [], ran))
        self.assertEqual(self.snapshot(), before)
        return refused.exception


# --------------------------------------------------------------------------- a derivation that stopped part-way
class RecordedDerivationTests(DerivationCase):
    def test_a_recorded_derivation_is_registered_again_from_its_record(self) -> None:
        """From every window past the decision: one fix Work, and the executor is not asked for that cycle."""
        for window, make in WINDOWS.items():
            with self.subTest(window=window):
                self.setUp()
                self.interrupt(make, self.deriving())
                self.assertEqual(self.ran, ["W1#1"])
                result = self.deriving()()
                # W1#1 is the interrupted cycle; the resume asks only for the cycle after it.
                self.assertConverged(result, ran=["W1#1", "W1#2"])
                self.assertEqual(self.events(self.w1), ["work_started", "work_target_added", "work_target_removed", "work_completed"])

    def test_the_decision_is_kept_before_the_stage_that_registers_it(self) -> None:
        """No record ever holds a registration whose decision is missing: the decision is saved first."""
        order: list[str] = []
        real_note, real_add = Mutation.set_note, Mutation.add_effects

        def note(mutation, key, value):
            if key == st._DERIVATIONS:
                order.append("kept")
            return real_note(mutation, key, value)

        def add(mutation, stage, effects):
            if ":derive:" in stage:
                order.append(f"recorded {stage.split(':', 1)[1]}")
            return real_add(mutation, stage, effects)

        with mock.patch.object(Mutation, "set_note", note), mock.patch.object(Mutation, "add_effects", add):
            self.deriving()()
        self.assertEqual(order, ["kept", "recorded derive:0"])

    def test_a_decision_kept_before_its_stage_was_recorded_is_registered_from_the_record(self) -> None:
        """Killed in that gap, the resume registers that decision - under the IDs reserved for its stage."""
        pending = self.keep_without_recording(self.deriving())
        self.assertEqual(self.stage_names(self.record_of(pending["mutation_id"])), [f"{self.w1}:lifecycle:0"])
        kept = pending["notes"][st._DERIVATIONS]
        self.assertEqual([e["stage"] for e in kept["derivations"]], [f"{self.w1}:derive:0"])
        self.assertEqual(kept["derivations"][0]["outcome"]["works"][0]["work"]["name"], "Fix")
        reserved = self.record_of(pending["mutation_id"])["reserved_ids"][f"{self.w1}:derive:0:work:fix"]
        self.assertConverged(self.deriving()(), ran=["W1#1", "W1#2"])
        self.assertEqual(self.works_named("Fix"), [reserved])

    def test_the_registration_stage_is_read_back_and_not_recorded_again(self) -> None:
        """The resume adds no stage for a registration the record holds, and no effect of it a second time."""
        pending = self.interrupt(WINDOWS["registration applied"], self.deriving())
        before = self.stage_names(self.record_of(pending["mutation_id"]))
        executed, stages = [], []
        result = self.watching(self.deriving(), executed, stages)
        self.assertConverged(result, ran=["W1#1", "W1#2"])
        self.assertEqual(stages, ["commit:0", f"{self.w1}:results:0", f"{self.w1}:lifecycle:1", f"{self.w1}:finalize:0"])
        self.assertNotIn(f"{self.w1}:derive:1", stages)
        self.assertEqual(before, [f"{self.w1}:lifecycle:0", f"{self.w1}:derive:0"])

    def test_a_recorded_derivation_keeps_its_own_ids(self) -> None:
        """The fix Work, its derivation detail and its relations are the ones the record reserved."""
        pending = self.interrupt(WINDOWS["registration recorded"], self.deriving())
        record = self.record_of(pending["mutation_id"])
        reserved = record["reserved_ids"]
        stage = f"{self.w1}:derive:0"
        self.deriving()()
        (fix,) = self.works_named("Fix")
        self.assertEqual(fix, reserved[f"{stage}:work:fix"])
        self.assertEqual(self.derivation_files(), [f"{reserved[f'{stage}:der:fix']}.md"])
        self.assertEqual([r.id for r in ProjectView.load(self.store).roadmap_relations if r.to == fix],
                         [reserved[f"{stage}:rel:0"]])

    def test_a_question_wait_after_a_derivation_registers_it_once(self) -> None:
        """No interruption at all: derive, ask, answer, resume - and the fix Work is registered once."""
        script = {("W1", 1): st.Derive({"fix": self.fix()}), ("W1", 2): st.QuestionWait("which fix?")}
        asked = self.deriving(script)()
        self.assertEqual((asked.status, asked.detail), ("question_wait", "which fix?"))
        self.assertEqual(self.ran, ["W1#1", "W1#2"])
        self.assertDerivedOnce()
        answered = self.deriving({("W1", 1): st.Derive({"fix": self.fix()})})()
        self.assertConverged(answered, ran=["W1#1", "W1#2", "W1#2"])

    def test_the_executor_is_not_asked_for_a_cycle_the_record_decided(self) -> None:
        """The resumed run asks for the cycles after the recorded ones, and an executor asked for them fails the test."""
        self.interrupt(WINDOWS["commit recorded"], self.deriving())
        asked: list[str] = []
        script = {("W1", 1): lambda ctx: asked.append("derive") or st.Derive({"fix": self.fix("Other")})}
        st.start(self.store, self.w1, "single-work", by_attempt(self.ran, script, default=completing_executor(self.store)))
        self.assertEqual(asked, [])
        self.assertEqual(self.works_named("Other"), [])
        self.assertEqual(self.ran, ["W1#1", "W1#2"])
        self.assertDerivedOnce()

    def test_three_interruptions_in_the_same_window_grow_nothing(self) -> None:
        """What grew without bound: every retry added a fix Work, its detail and its relations."""
        for _ in range(3):
            self.interrupt(before_pushing, self.deriving())
            self.assertEqual(len(self.works_named("Fix")), 1)
            self.assertEqual(len(self.derivation_files()), 1)
            self.assertEqual(len([r for r in self.relations() if r[0] == "derived"]), 1)
        # the executor is asked once, by the cycle that decided it - not again by any retry
        self.assertEqual(self.ran, ["W1#1"])
        self.assertConverged(self.deriving()(), ran=["W1#1", "W1#2"])

    def test_a_derivation_whose_executor_answers_differently_keeps_the_one_it_decided(self) -> None:
        """The decision is the one that was made, not the one the executor would make now."""
        self.interrupt(WINDOWS["registration applied"], self.deriving())
        result = self.deriving({("W1", 1): st.Derive({"fix": self.fix("Second thought")})})()
        self.assertConverged(result, ran=["W1#1", "W1#2"])
        self.assertEqual(self.works_named("Second thought"), [])

    def test_two_derivations_in_one_run_stay_two(self) -> None:
        """A run may legitimately derive more than once; both are its decisions and neither is doubled."""
        script = {("W1", 1): st.Derive({"fix": self.fix("Fix1")}), ("W1", 2): st.Derive({"fix": self.fix("Fix2")})}
        self.interrupt(lambda: after_recording(r"^commit:1$"), self.deriving(dict(script)))
        self.assertEqual(self.ran, ["W1#1", "W1#2"])
        result = self.deriving(dict(script))()
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(self.works_named("Fix1")), 1)
        self.assertEqual(len(self.works_named("Fix2")), 1)
        self.assertEqual(len(self.derivation_files()), 2)
        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#3"])
        self.assertEqual(self.subjects().count(f"chore(workline): derive from {self.display(self.w1)}"), 2)
        self.assertEqual(validate_project(self.store), [])

    def test_an_uninterrupted_derivation_is_unchanged(self) -> None:
        """The run that is not interrupted keeps exactly the shape it had."""
        result = self.deriving()()
        self.assertConverged(result, ran=["W1#1", "W1#2"])
        self.assertEqual(self.ran, ["W1#1", "W1#2"])

    def test_the_decision_before_it_is_kept_still_asks_the_executor(self) -> None:
        """Nothing is decided until the record keeps it, so that cycle is asked again - the contract as it was."""
        self.interrupt(before_keeping, self.deriving())
        pending = MutationController(self.store).list_pending()[0]
        self.assertNotIn(st._DERIVATIONS, pending.get("notes") or {})
        self.assertConverged(self.deriving()(), ran=["W1#1", "W1#1", "W1#2"])


# --------------------------------------------------------------------------- a derivation that moved the target
class MovedTargetTests(DerivationCase):
    def moving(self, name: str = "Fix", *, mode: str = "single-work"):
        script = {("W1", 1): st.Derive({"fix": self.fix(name)}, move=True)}
        return self.deriving(script, mode=mode)

    def test_a_recorded_move_is_finished_from_its_record(self) -> None:
        """A move ends the Work's cycle: the Git stage is all that is left, and the Work is not re-opened."""
        for window in ("registration applied", "commit recorded", "committed"):
            with self.subTest(window=window):
                self.setUp()
                self.interrupt(WINDOWS[window], self.moving())
                result = self.moving()()
                self.assertEqual((result.status, result.work_id), ("moved", self.w1))
                self.assertEqual(self.ran, ["W1#1"])  # the executor is not asked again at all
                self.assertEqual(self.events(self.w1), ["work_started", "work_target_added", "work_target_removed"])
                self.assertEqual(self.committed_events(self.w1), self.events(self.w1))
                self.assertDerivedOnce()
                self.assertEqual(self.subjects().count(f"chore(workline): branch from {self.display(self.w1)}"), 1)
                self.assertEqual((self.head(), self.dirty()), (self.remote_head(), []))
                self.assertEqual(MutationController(self.store).list_pending(), [])

    def test_a_move_interrupted_before_its_removal_is_recorded_is_carried_on(self) -> None:
        """The removal of the target is not in the record: the cycle that decided the move records it, once."""
        for window in ("decision kept", "registration recorded"):
            with self.subTest(window=window):
                self.setUp()
                if window == "decision kept":
                    self.keep_without_recording(self.moving())
                else:
                    self.interrupt(WINDOWS[window], self.moving())
                result = self.moving()()
                self.assertEqual(result.status, "moved")
                self.assertEqual(self.events(self.w1), ["work_started", "work_target_added", "work_target_removed"])
                self.assertDerivedOnce()
                self.assertEqual(self.subjects().count(f"chore(workline): branch from {self.display(self.w1)}"), 1)

    def test_an_uninterrupted_move_is_unchanged(self) -> None:
        result = self.moving()()
        self.assertEqual(result.status, "moved")
        self.assertEqual(self.events(self.w1), ["work_started", "work_target_added", "work_target_removed"])
        self.assertDerivedOnce()

    def test_a_finished_move_is_not_replayed_for_the_next_cycle(self) -> None:
        """A cycle decides its own derivations: the finished move is neither replayed nor registered again."""
        self.interrupt(WINDOWS["committed"], self.moving())
        result = self.moving()()
        self.assertEqual((result.status, self.ran), ("moved", ["W1#1"]))
        # The Work is startable again exactly as an uninterrupted move leaves it, and that
        # cycle asks the executor instead of registering the derivation the first one decided.
        again = st.start(self.store, self.w1, "single-work",
                         by_attempt(self.ran, {}, default=completing_executor(self.store)))
        self.assertEqual(again.status, "completed")
        self.assertEqual(self.ran, ["W1#1", "W1#1"])
        self.assertDerivedOnce()
        self.assertEqual(self.events(self.w1),
                         ["work_started", "work_target_added", "work_target_removed",
                          "work_target_added", "work_target_removed", "work_completed"])


class HumanConfirmationTests(WorklineTestCase):
    """The NG of a human confirmation is a derivation that moves the target, with a new integration."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.root = self.store.root
        self.ran: list[str] = []
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A")})
        entry = self.simple_entry(self.store, roadmap.phase_ids["a"], {"w1": "W1 done"}, confirmation=True)
        self.w1, self.i1, self.h1 = entry.work_ids["w1"], entry.integration_id, entry.confirmation_id

    def ng_run(self):
        """The confirmation is judged NG once; confirmed again after the fix, it passes.

        Which cycle it is comes from the Project - is there a fix Work yet - and not from
        how many times the executor has been called: a resumed cycle is asked exactly what
        an uninterrupted one is asked.
        """

        def ng(ctx: st.ExecutionContext):
            if self.named("F1"):
                return completing_executor(self.store)(ctx)
            return st.HumanNG({"f1": st.DerivedWork("F1", "defect fixed", derivation_detail="why F1")},
                              st.DerivedWork("I2", "re-integrated"))

        executor = by_attempt(self.ran, {("Confirmation", 1): ng}, default=completing_executor(self.store))
        return lambda: st.start(self.store, self.w1, "outer", executor)

    def named(self, name: str) -> list[str]:
        return [w.id for w in ProjectView.load(self.store).works.values() if w.name == name]

    def ng_windows(self) -> dict:
        """Every window from the NG's target removal on. The windows before it - where the confirmation
        already depends on its own new re-integration - are BL-049's (``test_recorded_move_dependency.py``)."""
        return {
            "removal recorded": lambda: before_recording(r"^commit:0$"),
            "commit recorded": lambda: after_recording(r"^commit:0$"),
            "committed": self.before_pushing_the_ng,
        }

    def before_pushing_the_ng(self):
        """Stop with the NG's own commit made and its push not made, past every earlier Work's."""
        real = MutationController.apply_effect

        def fire(controller, record):
            removed = [e for e in ProjectView.load(self.store).events
                       if e.entity == self.h1 and e.type == "work_target_removed"]
            if record["kind"] == "git_push" and removed:
                raise Interrupted("the NG is committed, not pushed")
            return real(controller, record)

        return mock.patch.object(MutationController, "apply_effect", fire)

    def test_a_recorded_ng_registers_its_fix_and_integration_once(self) -> None:
        """The new integration must not be counted as one that was already there, and the NG is not decided again."""
        for window, make in self.ng_windows().items():
            with self.subTest(window=window):
                self.setUp()
                with make(), self.assertRaises(Interrupted):
                    self.ng_run()()
                self.assertEqual(self.ran, ["W1#1", "Integration#1", "Confirmation#1"])
                result = self.ng_run()()
                self.assertEqual(result.status, "phase_complete")
                self.assertEqual(len(self.named("F1")), 1)
                self.assertEqual(len(self.named("I2")), 1)
                self.assertEqual(len(self.named("Confirmation")), 1)
                view = ProjectView.load(self.store)
                self.assertEqual([e.type for e in view.events if e.entity == self.h1],
                                 ["work_started", "work_target_added", "work_target_removed",
                                  "work_target_added", "work_target_removed", "work_completed"])
                display = view.works[self.h1].display
                subjects = git(self.root, "log", "--format=%s").splitlines()
                # the commit carrying the move is the one the NG makes, not a derivation's
                self.assertEqual(subjects.count(f"chore(workline): {display} NG; fix planned"), 1)
                self.assertEqual(subjects.count(f"chore(workline): branch from {display}"), 0)
                # the NG cycle is not asked again; the confirmation's next cycle is
                self.assertEqual(self.ran, ["W1#1", "Integration#1", "Confirmation#1",
                                            "F1#1", "I2#1", "Confirmation#1"])
                self.assertEqual(validate_project(self.store), [])

    def test_an_uninterrupted_ng_is_unchanged(self) -> None:
        result = self.ng_run()()
        self.assertEqual(result.status, "phase_complete")
        self.assertEqual(self.ran, ["W1#1", "Integration#1", "Confirmation#1", "F1#1", "I2#1", "Confirmation#1"])
        self.assertEqual((len(self.named("F1")), len(self.named("I2"))), (1, 1))
        self.assertEqual(validate_project(self.store), [])


# --------------------------------------------------------------------------- modes and continuation
class ModeTests(DerivationCase):
    def test_outer_continues_from_the_recorded_derivation(self) -> None:
        """The recorded fix Work is the one the continuation picks up; no second one makes the plan ambiguous."""
        self.interrupt(WINDOWS["commit recorded"], self.deriving(mode="outer"))
        result = self.deriving(mode="outer")()
        self.assertEqual(result.status, "phase_complete")
        (fix,) = self.works_named("Fix")
        view = ProjectView.load(self.store)
        self.assertEqual(view.work_state(fix).state, "completed")
        self.assertEqual(len(self.derivation_files()), 1)
        self.assertEqual(validate_project(self.store), [])

    def test_single_work_refuses_a_record_that_derived_another_work(self) -> None:
        create_standalone_work(self.store, WorkSpec("Other", "other done"))
        other = self.works_named("Other")[0]
        pending = self.interrupt(WINDOWS["registration applied"], self.deriving())
        self.edit_record(pending, lambda record: record["notes"][st._DERIVATIONS]["derivations"][0].update({"work_id": other}))
        before = self.snapshot()
        refused = self.assertUntouched(self.deriving(), before)
        self.assertIn("runs", str(refused))


# --------------------------------------------------------------------------- what the record cannot show
class UnprovableRecordTests(DerivationCase):
    def stuck(self, window: str = "registration applied") -> dict:
        return self.interrupt(WINDOWS[window], self.deriving())

    def test_a_note_this_start_does_not_read_back_is_refused(self) -> None:
        for label, change in {
            "unknown key": lambda note: note.update({"extra": 1}),
            "version": lambda note: note.update({"version": 2}),
            "complete not a flag": lambda note: note.update({"complete": "yes"}),
            "derivations not a list": lambda note: note.update({"derivations": {}}),
            "entry field missing": lambda note: note["derivations"][0].pop("moved_by"),
            "moved_by unknown": lambda note: note["derivations"][0].update({"moved_by": "elsewhere"}),
            "outcome kind": lambda note: note["derivations"][0]["outcome"].update({"kind": "completed"}),
            "outcome unreadable": lambda note: note["derivations"][0].update({"outcome": {"kind": "derive"}}),
            "work_id not a Work": lambda note: note["derivations"][0].update({"work_id": "nope"}),
        }.items():
            with self.subTest(note=label):
                self.setUp()
                pending = self.stuck()
                self.edit_record(pending, lambda record: change(record["notes"][st._DERIVATIONS]))
                before = self.snapshot()
                self.assertUntouched(self.deriving(), before)

    def test_a_stage_named_other_than_the_derivations_in_order_is_refused(self) -> None:
        pending = self.stuck()
        self.edit_record(pending, lambda record: record["notes"][st._DERIVATIONS]["derivations"][0].update(
            {"stage": f"{self.w1}:derive:3"}))
        before = self.snapshot()
        refused = self.assertUntouched(self.deriving(), before)
        self.assertIn("in the order it decided them", str(refused))

    def test_a_registration_recorded_without_its_branch_is_refused(self) -> None:
        pending = self.stuck()

        def drop_branch(record: dict) -> None:
            for effect in record["effects"]:
                effect.pop("decided_on", None)

        self.edit_record(pending, drop_branch)
        before = self.snapshot()
        refused = self.assertUntouched(self.deriving(), before)
        self.assertIn("without the branch it was decided on", str(refused))

    def test_a_reserved_id_the_derivation_did_not_reserve_is_refused(self) -> None:
        pending = self.stuck()
        self.edit_record(pending, lambda record: record["reserved_ids"].pop(f"{self.w1}:derive:0:rel:0"))
        before = self.snapshot()
        with self.assertRaises(ReconcileRequired) as refused:
            self.deriving()()
        self.assertIn("no relation ID reserved", str(refused.exception))
        self.assertEqual(self.works_named("Fix"), [w for w in self.works_named("Fix")])  # nothing registered twice
        self.assertEqual(len(self.works_named("Fix")), 1)
        self.assertEqual(self.snapshot()["files"], before["files"])

    def assertRefusedWithoutRegistering(self, call, pending: dict) -> ReconcileRequired:
        """Refused with nothing registered a second time, nothing recorded, nothing committed or pushed.

        Replaying what the record already holds still happens - that is the Mutation
        Controller finishing its own recorded effects - so what is pinned here is that no
        stage and no effect is added, no second Work, detail or relation appears, and
        neither HEAD nor the remote moves.
        """
        before = self.record_of(pending["mutation_id"])
        head, remote = self.head(), self.remote_head()
        with self.assertRaises(ReconcileRequired) as refused:
            call()
        after = self.record_of(pending["mutation_id"])
        self.assertEqual(self.stage_names(after), self.stage_names(before))
        self.assertEqual(len(after["effects"]), len(before["effects"]))
        self.assertEqual(after["notes"], before["notes"])
        self.assertEqual((self.head(), self.remote_head()), (head, remote))
        self.assertEqual(len(self.works_named("Fix")), 1)
        self.assertEqual(len(self.derivation_files()), 1)
        # the Phase entry's own relation plus the two this one derivation adds, and no more
        self.assertEqual(len(self.relations()), 3)
        return refused.exception

    def test_a_relation_payload_other_than_the_decision_makes_is_refused(self) -> None:
        for window in ("registration recorded", "registration applied"):
            with self.subTest(window=window):
                self.setUp()
                pending = self.stuck(window)

                def retarget(record: dict) -> None:
                    for effect in record["effects"]:
                        if effect["kind"] == "add_relation" and effect["payload"]["record"]["type"] == "derived":
                            effect["payload"]["record"]["type"] = "planned_next"

                self.edit_record(pending, retarget)
                self.assertRefusedWithoutRegistering(self.deriving(), pending)

    def test_a_work_body_other_than_the_decision_makes_is_refused(self) -> None:
        for window in ("registration recorded", "registration applied"):
            with self.subTest(window=window):
                self.setUp()
                pending = self.stuck(window)

                def rewrite(record: dict) -> None:
                    for effect in record["effects"]:
                        if effect["kind"] == "write_file" and "/works/" in effect["payload"]["path"]:
                            effect["payload"]["content"] = effect["payload"]["content"].replace("Fix done", "other")

                self.edit_record(pending, rewrite)
                self.assertRefusedWithoutRegistering(self.deriving(), pending)

    def test_a_derivation_after_one_that_moved_the_target_is_refused(self) -> None:
        script = {("W1", 1): st.Derive({"fix": self.fix("Fix1")}, move=True)}
        pending = self.interrupt(WINDOWS["registration applied"], self.deriving(script))

        def add_another(record: dict) -> None:
            entries = record["notes"][st._DERIVATIONS]["derivations"]
            entries.append({**entries[0], "stage": f"{self.w1}:derive:1"})
            entries[0], entries[1] = entries[1], entries[0]
            entries[0]["stage"], entries[1]["stage"] = f"{self.w1}:derive:0", f"{self.w1}:derive:1"

        self.edit_record(pending, add_another)
        before = self.snapshot()
        refused = self.assertUntouched(self.deriving(script), before)
        self.assertIn("a move ends the cycle", str(refused))

    def test_a_stage_between_two_derivations_other_than_their_commit_is_refused(self) -> None:
        script = {("W1", 1): st.Derive({"fix": self.fix("Fix1")}), ("W1", 2): st.Derive({"fix": self.fix("Fix2")})}
        pending = self.interrupt(lambda: after_recording(r"^commit:1$"), self.deriving(dict(script)))

        def rename(record: dict) -> None:
            for effect in record["effects"]:
                if effect["stage"] == "commit:0":
                    effect["stage"] = f"{self.w1}:lifecycle:9"

        self.edit_record(pending, rename)
        before = self.snapshot()
        refused = self.assertUntouched(self.deriving(dict(script)), before)
        self.assertIn("only the commit that carries it", str(refused))

    def test_a_removal_other_than_the_move_records_is_refused(self) -> None:
        script = {("W1", 1): st.Derive({"fix": self.fix()}, move=True)}
        pending = self.interrupt(WINDOWS["commit recorded"], self.deriving(script))

        def retype(record: dict) -> None:
            for effect in record["effects"]:
                event = effect["payload"].get("record") if effect["kind"] == "append_event" else None
                if isinstance(event, dict) and event["type"] == "work_target_removed":
                    event["id"] = new_id("event")

        self.edit_record(pending, retype)
        before = self.snapshot()
        refused = self.assertUntouched(self.deriving(script), before)
        self.assertIn("other than the removal of the target", str(refused))

    def test_a_move_commit_other_than_the_one_it_records_is_refused(self) -> None:
        script = {("W1", 1): st.Derive({"fix": self.fix()}, move=True)}
        pending = self.interrupt(WINDOWS["commit recorded"], self.deriving(script))

        def reword(record: dict) -> None:
            for effect in record["effects"]:
                if effect["kind"] == "git_commit":
                    effect["payload"]["message"] = "chore(workline): something else"

        self.edit_record(pending, reword)
        before = self.snapshot()
        refused = self.assertUntouched(self.deriving(script), before)
        self.assertIn("other than the commit carrying the move", str(refused))

    def test_a_move_whose_events_a_foreign_commit_already_holds_is_refused(self) -> None:
        """Its own commit and push cannot be shown once HEAD's event log holds those events."""
        script = {("W1", 1): st.Derive({"fix": self.fix()}, move=True)}
        self.interrupt(lambda: before_recording(r"^commit:0$"), self.deriving(script))
        git(self.root, "add", "--all")
        git(self.root, "-c", "core.hooksPath=/dev/null", "commit", "-m", "someone else commits it")
        before = self.snapshot()
        refused = self.assertUntouched(self.deriving(script), before)
        self.assertIn("already holds that event", str(refused))


# --------------------------------------------------------------------------- records written before this change
class LegacyRecordTests(DerivationCase):
    def test_a_record_without_the_decision_asks_the_executor_again(self) -> None:
        """Nothing is guessed from a registration stage alone, and nothing is repaired: today's behaviour."""
        pending = self.interrupt(WINDOWS["registration applied"], self.deriving())
        self.edit_record(pending, lambda record: record["notes"].pop(st._DERIVATIONS))
        result = self.deriving()()
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(self.works_named("Fix")), 2)  # the behaviour this change ends, kept for old records
        self.assertEqual(self.ran, ["W1#1", "W1#1", "W1#2"])
        self.assertEqual(validate_project(self.store), [])

    def test_an_outcome_the_record_cannot_keep_asks_the_executor_again(self) -> None:
        """A derivation the record cannot hold exactly is not kept, and never refuses the derivation itself."""
        with mock.patch.object(st, "_recorded_outcome", lambda outcome: None):
            self.interrupt(WINDOWS["registration applied"], self.deriving())
            pending = MutationController(self.store).list_pending()[0]
            self.assertEqual(pending["notes"][st._DERIVATIONS], {"version": 1, "complete": False, "derivations": []})
            self.assertEqual(len(self.works_named("Fix")), 1)
        result = self.deriving()()
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(self.works_named("Fix")), 2)
        self.assertEqual(validate_project(self.store), [])


# --------------------------------------------------------------------------- the rules this change must not disturb
class NonRegressionTests(DerivationCase):
    def test_a_work_registered_by_someone_else_meanwhile_does_not_unprove_it(self) -> None:
        """BL-045: the display comes from the stage that recorded it, never from the Works a Project holds now."""
        for window in ("registration recorded", "registration applied"):
            with self.subTest(window=window):
                self.setUp()
                self.interrupt(WINDOWS[window], self.deriving())
                self.write_foreign_work()
                result = self.deriving()()
                self.assertEqual(result.status, "completed")
                (fix,) = self.works_named("Fix")
                self.assertEqual(ProjectView.load(self.store).works[fix].display, "W-03")
                self.assertEqual(len(self.derivation_files()), 1)
                self.assertEqual(self.ran, ["W1#1", "W1#2"])

    def write_foreign_work(self) -> str:
        """A Work another owner registered, appearing between the interruption and the resume."""
        foreign = new_id("work")
        body = "\n".join([
            "---", f"id: {foreign}", "display: W-09", "type: work", "origin:", "  type: standalone", "---",
            "", "# Foreign", "", f"## {WORK_DESIRED_HEADING}", "foreign done", "",
        ])
        (self.root / ProjectStore.entity_rel_path("work", foreign)).write_text(body, encoding="utf-8")
        return foreign

    def test_a_derivation_over_a_dirty_relation_ledger_still_refuses_before_recording_anything(self) -> None:
        """BL-042: nothing of the derivation is kept or recorded when its ledger was changed beforehand."""
        (self.root / ROADMAP_YAML).write_text(
            (self.root / ROADMAP_YAML).read_text(encoding="utf-8") + "\n# someone's line\n", encoding="utf-8")
        with self.assertRaises(StopError) as refused:
            self.deriving()()
        self.assertEqual(refused.exception.code, "dirty_overlap")
        self.assertEqual(self.works_named("Fix"), [])
        pending = MutationController(self.store).list_pending()[0]
        self.assertNotIn(st._DERIVATIONS, pending.get("notes") or {})
        self.assertEqual(self.stage_names(self.record_of(pending["mutation_id"])), [f"{self.w1}:lifecycle:0"])

    def test_the_refused_result_is_still_reused_after_the_change_is_committed(self) -> None:
        """BL-042: the refused derivation is the one that goes on, and the executor is not asked for it again."""
        (self.root / ROADMAP_YAML).write_text(
            (self.root / ROADMAP_YAML).read_text(encoding="utf-8") + "\n# someone's line\n", encoding="utf-8")
        with self.assertRaises(StopError):
            self.deriving()()
        self.assertEqual(self.ran, ["W1#1"])
        git(self.root, "add", ROADMAP_YAML)
        git(self.root, "-c", "core.hooksPath=/dev/null", "commit", "-m", "the person commits their line")
        result = self.deriving()()
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(self.works_named("Fix")), 1)
        self.assertEqual(self.ran, ["W1#1", "W1#2"])
        self.assertEqual(validate_project(self.store), [])

    def test_a_derivation_the_registration_refuses_before_recording_is_not_kept(self) -> None:
        """Nothing of it is written (``skills/create``), so nothing of it was decided: the retry asks again."""
        script = {("W1", 1): st.Derive({"fix": st.DerivedWork("", "fixed")})}
        with self.assertRaises(ValidationError):
            self.deriving(script)()
        pending = MutationController(self.store).list_pending()[0]
        self.assertEqual((pending["notes"].get(st._DERIVATIONS) or {}).get("derivations"), [])
        self.assertEqual(self.stage_names(self.record_of(pending["mutation_id"])), [f"{self.w1}:lifecycle:0"])
        self.assertConverged(self.deriving()(), ran=["W1#1", "W1#1", "W1#2"])

    def test_a_hold_is_still_finished_from_its_record(self) -> None:
        """BL-044: the hold readback runs before this one and is unchanged by it."""
        script = {("W1", 1): st.Hold("later")}
        self.interrupt(lambda: after_recording(r":lifecycle:1$"), self.deriving(script))
        result = self.deriving(script)()
        self.assertEqual((result.status, result.detail), ("held", "later"))
        self.assertEqual(self.ran, ["W1#1"])
        self.assertEqual(self.events(self.w1), ["work_started", "work_target_added", "work_target_removed", "work_held"])
        self.assertEqual(validate_project(self.store), [])

    def test_a_completion_is_still_finalized_from_its_record(self) -> None:
        """BL-031: a recorded completion is finished before a derivation is even looked for."""
        self.interrupt(lambda: before_recording(rf"^{self.w1}:finalize:"), self.deriving())
        result = self.deriving()()
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(self.works_named("Fix")), 1)
        self.assertEqual(self.ran, ["W1#1", "W1#2"])
        self.assertEqual(self.events(self.w1), ["work_started", "work_target_added", "work_target_removed", "work_completed"])
        self.assertEqual(validate_project(self.store), [])

    def test_a_cancel_after_a_derivation_is_still_carried_from_its_decision(self) -> None:
        """BL-030: the cancel readback runs before the mutation is opened and is unchanged by it."""
        standalone = create_standalone_work(self.store, WorkSpec("S", "s done")).work_id
        script = {("S", 1): st.Derive({"fix": self.fix()}), ("S", 2): st.Cancel(reason="not needed")}
        executor = by_attempt(self.ran, script, default=completing_executor(self.store))
        call = lambda: st.start(self.store, standalone, "single-work", executor)  # noqa: E731
        with after_recording(r":lifecycle:1$"), self.assertRaises(Interrupted):
            call()
        result = call()
        self.assertEqual((result.status, result.detail), ("cancelled", "not needed"))
        self.assertEqual(len(self.works_named("Fix")), 1)
        self.assertEqual(self.ran, ["S#1", "S#2"])
        self.assertEqual(validate_project(self.store), [])

    def test_a_question_wait_before_any_derivation_still_asks_the_executor(self) -> None:
        """A record whose stage only opened the Work decides nothing, so the resume asks again."""
        script = {("W1", 1): st.QuestionWait("?")}
        asked = self.deriving(script)()
        self.assertEqual(asked.status, "question_wait")
        result = self.deriving()()
        self.assertConverged(result, ran=["W1#1", "W1#1", "W1#2"])


if __name__ == "__main__":
    unittest.main()
