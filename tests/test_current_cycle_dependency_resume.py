"""START continues its own cycle past the requires_completion that cycle registered into its Work (BL-051).

A derivation may register, with the Works it decides, a ``requires_completion``
from one of them into the deriving Work itself: the executor decides that the
Work waits for its fix. That dependency is checked where the Work is next
entered and where it completes, never between the attempts of the cycle that
registered it - uninterrupted, a derivation that keeps the target goes straight
on to the next attempt of the same cycle.

A resume of that cycle - the answer to a question its next attempt asked, as
much as a retry after an interruption - continues it from the record (BL-046),
but it entered the cycle through the precheck that guards running a Work. That
precheck counted the cycle's own dependency as an unfinished one and stopped with
``dependency_unsatisfied`` on every retry, before the executor was asked, while
the pending record held off every operation that could satisfy it. BL-049 left
out only what a move registered itself, so a move decided after such a
derivation met the earlier dependency the same way.

That precheck now leaves out exactly the relations the cycle's own proven
registrations added into the Work - whether a registration kept the target or
moved it - and only once the record shows that cycle going on: this mutation
resumed, the Work still carrying the cycle's target, its derivations proven, the
record holding nothing in that cycle but its registrations and their Git stages,
each registration exactly the one its decision makes, each relation under the ID
reserved for it and held by the Project exactly so. The relation itself stays:
the Work completes only once it is satisfied, and once the cycle has ended every
entry into the Work checks it as before. A dependency the Project held before,
one a person added, one a record cannot show, and every dependency of a cycle
opened here are checked exactly as before; a stage that is not the registration
its decision makes is ``reconcile required`` and nothing of the cycle runs.
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone
import json
import re
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git
from test_recorded_move_dependency import (
    Interrupted,
    MoveCase,
    after_applying,
    after_recording,
    after_writing_one,
    before_keeping,
    before_pushing,
    before_recording,
    by_attempt,
)
from workline import start as st
from workline.create import RelationSpec
from workline.errors import ReconcileRequired, StopError
from workline.ids import new_id
from workline.mutation import Mutation
from workline.state import ProjectView
from workline.store import WORKLINE_DIR
from workline.validate import validate_project

ROADMAP_YAML = f"{WORKLINE_DIR}/relations/roadmap.yaml"
EVENT_LOG = f"{WORKLINE_DIR}/events/events.jsonl"
STARTED = ["work_started", "work_target_added"]
MOVED = STARTED + ["work_target_removed"]
HELD = STARTED + ["work_target_removed", "work_held"]


def interrupted_executor(real, name: str, attempt: int):
    """``real``, except that asking ``name`` for ``attempt`` the first time dies like the process running it."""
    seen = {"n": 0}

    def execute(ctx: st.ExecutionContext):
        outcome = real(ctx)
        if (ctx.work.name, ctx.attempt) == (name, attempt) and not seen["n"]:
            seen["n"] += 1
            raise Interrupted(f"{name} attempt {attempt} interrupted")
        return outcome

    return execute


# --------------------------------------------------------------------------- the Project, and what it can show
class CycleCase(MoveCase):
    """A Phase with W1 (and W2, when the case needs another Work) and its integration."""

    remote = True
    works = {"w1": "W1 done"}
    entry_options: dict = {}

    def setUp(self) -> None:
        WorklineTestCase.setUp(self)
        self.store = self.new_project(remote=self.remote)
        self.root = self.store.root
        self.ran: list[str] = []
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A")})
        self.pa = roadmap.phase_ids["a"]
        entry = self.simple_entry(self.store, self.pa, dict(self.works), **dict(self.entry_options))
        self.w1, self.i1, self.h1 = entry.work_ids["w1"], entry.integration_id, entry.confirmation_id
        self.w2 = entry.work_ids.get("w2")

    def remote_head(self) -> str | None:
        return super().remote_head() if self.remote else None

    # the derivations -------------------------------------------------------------
    def waits(self, *keys: str, others: tuple[str, ...] = (), move: bool = False, into: str | None = None) -> st.Derive:
        """A derivation of a Work per key (named after it) that the deriving Work waits for - and of ``others``,
        which it does not wait for - keeping the target, or moving it away with ``move``."""
        works = {key: st.DerivedWork(key.capitalize(), f"{key.capitalize()} done", derivation_detail=f"why {key}")
                 for key in (*keys, *others)}
        relations = tuple(RelationSpec("requires_completion", key, into or self.w1) for key in keys)
        return st.Derive(works, relations=relations, move=move)

    def starting(self, script: dict, *, mode: str = "single-work", work_id: str | None = None, executor=None):
        """A START of W1 (or ``work_id``) whose executor answers from ``script`` by Work name and attempt."""
        answer = executor or by_attempt(self.ran, dict(script), default=completing_executor(self.store))
        return lambda: st.start(self.store, work_id or self.w1, mode, answer)

    def ask(self, first=None) -> str:
        """The question wait BL-051 starts from: W1 derives Fix, decides to wait for it and keeps its target, and
        its next attempt asks a question. The mutation is left pending; its ID is returned."""
        asked = self.starting({("W1", 1): first or self.waits("fix"), ("W1", 2): st.QuestionWait("which way?")})()
        self.assertEqual((asked.status, self.ran[-2:]), ("question_wait", ["W1#1", "W1#2"]))
        (pending,) = self.pending()
        self.assertEqual(pending["mutation_id"], asked.mutation_id)
        return asked.mutation_id

    # observation ---------------------------------------------------------------
    def outcome(self) -> dict:
        """What a run leaves, by name: Works, relations, lifecycle events, derivation details, commits, loose ends."""
        view = ProjectView.load(self.store)
        return {
            "works": sorted(w.name for w in view.works.values()),
            "relations": self.relations(),
            "events": {w.name: self.events(w.id) for w in view.works.values()},
            "details": self.derivation_files(),
            "subjects": self.subjects(),
            "pending": self.pending(),
            "dirty": self.dirty(),
            "published": self.head() == self.remote_head() if self.remote else None,
            "problems": validate_project(self.store),
        }

    @staticmethod
    def settled(outcome: dict) -> dict:
        """``outcome`` without the commit subjects: what the Project holds, published or not, and what is left pending."""
        return {key: value for key, value in outcome.items() if key != "subjects"}

    def twin(self, script) -> dict:
        """What the same START leaves uninterrupted, on a Project set up the same way.

        ``script`` is called once that Project exists: a derivation names the Work it waits for by its ID.
        """
        self.setUp()
        self.starting(script())()
        return self.outcome()

    def state(self, work_id: str | None = None) -> tuple[str, bool]:
        state = ProjectView.load(self.store).work_state(work_id or self.w1)
        return state.state, state.has_target

    def relation_id(self, from_name: str, to_id: str | None = None) -> str:
        view = ProjectView.load(self.store)
        (relation,) = [r for r in view.roadmap_relations
                       if r.type == "requires_completion" and r.to == (to_id or self.w1)
                       and view.works[r.from_id].name == from_name]
        return relation.id

    def hand_add(self, from_id: str, to_id: str | None = None) -> str:
        """A person's own relation line, making W1 (or ``to_id``) wait for ``from_id``."""
        relation = new_id("relation")
        path = self.root / ROADMAP_YAML
        path.write_bytes(path.read_bytes().rstrip(b"\n") + (
            f"\n  - id: {relation}\n    type: requires_completion\n    from: {from_id}\n    to: {to_id or self.w1}\n"
        ).encode("utf-8"))
        return relation


# --------------------------------------------------------------------------- A, B, C, P: the answer continues the cycle
class AnswerTests(CycleCase):
    def held_twin(self) -> dict:
        return self.twin(lambda: {("W1", 1): self.waits("fix"), ("W1", 2): st.Hold("waiting for Fix")})

    def test_the_answer_continues_the_same_cycle_at_its_next_attempt(self) -> None:
        """A: the resume asks attempt 2 again, under the same mutation, with nothing recorded or registered again."""
        mutation_id = self.ask()
        fix, relations, details = self.named("Fix"), self.relations(), self.derivation_files()
        result, executed, stages = self.watching(self.starting({("W1", 2): st.QuestionWait("still?")}))
        self.assertEqual((result.status, result.work_id, result.mutation_id), ("question_wait", self.w1, mutation_id))
        self.assertEqual(result.detail, "still?")
        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#2"])  # not W1#1 again: the derivation is not decided again
        self.assertEqual((executed, stages), ([], []))
        self.assertEqual((self.named("Fix"), self.relations(), self.derivation_files()), (fix, relations, details))
        self.assertEqual(self.events(self.w1), STARTED)
        self.assertEqual([p["mutation_id"] for p in self.pending()], [mutation_id])

    def test_a_resumed_cycle_ends_as_the_uninterrupted_one_does(self) -> None:
        """A: answered with a hold, the Project is exactly what the uninterrupted cycle leaves."""
        expected = self.held_twin()
        self.setUp()
        mutation_id = self.ask()
        result = self.starting({("W1", 2): st.Hold("waiting for Fix")})()
        self.assertEqual((result.status, result.mutation_id), ("held", mutation_id))
        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#2"])
        self.assertEqual(self.outcome(), expected)
        self.assertIn(("requires_completion", "Fix", "W1"), self.relations())  # the dependency itself stays

    def test_a_cycle_asked_again_and_again_still_goes_on(self) -> None:
        """B: every question wait resumes the same cycle; nothing grows on any retry."""
        expected = self.held_twin()
        self.setUp()
        mutation_id = self.ask()
        fix, relations, details = self.named("Fix"), self.relations(), self.derivation_files()
        for asked in range(3):
            result, executed, stages = self.watching(self.starting({("W1", 2): st.QuestionWait(f"again {asked}?")}))
            self.assertEqual((result.status, result.mutation_id), ("question_wait", mutation_id))
            self.assertEqual((executed, stages), ([], []))
            self.assertEqual((self.named("Fix"), self.relations(), self.derivation_files()), (fix, relations, details))
        self.assertEqual(self.starting({("W1", 2): st.Hold("waiting for Fix")})().status, "held")
        self.assertEqual(self.ran, ["W1#1"] + ["W1#2"] * 5)
        self.assertEqual(self.outcome(), expected)

    def test_an_answer_that_moves_the_target_ends_the_cycle(self) -> None:
        """C: the answer's move is registered, the target removed and the move committed as uninterrupted."""
        expected = self.twin(lambda: {("W1", 1): self.waits("fix"), ("W1", 2): self.waits("other", move=True)})
        self.setUp()
        mutation_id = self.ask()
        result = self.starting({("W1", 2): self.waits("other", move=True)})()
        self.assertEqual((result.status, result.mutation_id), ("moved", mutation_id))
        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#2"])
        self.assertEqual(self.events(self.w1), MOVED)
        self.assertEqual(self.state(), ("in_progress", False))
        self.assertEqual(self.outcome(), expected)
        self.assertTrue({("requires_completion", "Fix", "W1"), ("requires_completion", "Other", "W1")}
                        <= set(self.relations()))

    def test_a_derivation_that_does_not_wait_is_unchanged(self) -> None:
        """P: a derivation that registers no dependency into its Work goes on after the answer exactly as before."""
        expected = self.twin(lambda: {("W1", 1): self.waits(others=("fix",)), ("W1", 2): st.Hold("later")})
        self.setUp()
        self.ask(self.waits(others=("fix",)))
        self.assertEqual(self.starting({("W1", 2): st.Hold("later")})().status, "held")
        self.assertEqual(self.outcome(), expected)


# --------------------------------------------------------------------------- D: the answer's move, interrupted
class AnswerMoveTests(CycleCase):
    def moving(self):
        return self.starting({("W1", 2): self.waits("other", move=True)})

    def windows(self) -> dict:
        """The windows of the answer's move, W1's second derivation, read when each opens."""
        stage = lambda: rf"^{self.w1}:derive:1$"  # noqa: E731
        return {
            "registration recorded": lambda: after_recording(stage()),
            "one effect of it applied": lambda: after_writing_one(stage()),
            "registration applied": lambda: after_applying(stage()),
            "removal about to be recorded": lambda: before_recording(rf"^{self.w1}:lifecycle:1$"),
            "removal recorded": lambda: after_recording(rf"^{self.w1}:lifecycle:1$"),
            "commit recorded": lambda: after_recording(r"^commit:1$"),
            "committed, not pushed": lambda: before_pushing("commit:1"),
        }

    def test_a_move_after_the_cycle_s_own_dependency_finishes_from_its_record(self) -> None:
        """D: whatever window the move stopped in, the earlier derivation's dependency does not stop its resume.

        Stopped before its removal is recorded, the move's registration is written but not committed, and the
        replay of the earlier derivation commits what it finds under its own message before the move commit is
        made - the replay's own way, unchanged here - so only the grouping of those commits can differ.
        """
        expected = self.twin(lambda: {("W1", 1): self.waits("fix"), ("W1", 2): self.waits("other", move=True)})
        for window, make in self.windows().items():
            with self.subTest(window=window):
                self.setUp()
                mutation_id = self.ask()
                decided = self.display(self.w1)
                self.interrupt(make, self.moving())
                self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#2"])
                result = self.starting({})()  # nothing is asked: the move is the record's
                self.assertEqual((result.status, result.mutation_id), ("moved", mutation_id))
                self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#2"])
                self.assertEqual(self.settled(self.outcome()), self.settled(expected))
                self.assertEqual(self.subjects()[0], f"chore(workline): branch from {decided}")
                self.assertEqual(self.subjects().count(f"chore(workline): branch from {decided}"), 1)
                if window not in ("registration recorded", "one effect of it applied", "registration applied",
                                  "removal about to be recorded"):
                    self.assertEqual(self.outcome(), expected)

    def test_a_move_stopped_again_after_the_replay_s_commit_still_finishes(self) -> None:
        """D: the resume that commits the move's registration stops once more before recording the removal; the
        Git stage it recorded after the move's registration decides nothing, and the next resume finishes the move."""
        expected = self.twin(lambda: {("W1", 1): self.waits("fix"), ("W1", 2): self.waits("other", move=True)})
        self.setUp()
        mutation_id = self.ask()
        self.interrupt(lambda: after_applying(rf"^{self.w1}:derive:1$"), self.moving())
        self.interrupt(lambda: after_recording(r"^commit:1$"), self.starting({}))
        self.assertEqual(self.stage_names()[-2:], [f"{self.w1}:derive:1", "commit:1"])
        self.assertEqual(self.state(), ("in_progress", True))
        result = self.starting({})()
        self.assertEqual((result.status, result.mutation_id), ("moved", mutation_id))
        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#2"])
        self.assertEqual(self.settled(self.outcome()), self.settled(expected))

    def test_a_move_kept_before_its_stage_was_recorded_is_registered_from_the_record(self) -> None:
        """D: decision kept, stage not recorded - the resume registers that move, not another."""
        expected = self.twin(lambda: {("W1", 1): self.waits("fix"), ("W1", 2): self.waits("other", move=True)})
        self.setUp()
        self.ask()
        self.keep_without_recording(lambda: after_recording(rf"^{self.w1}:derive:1$"), self.moving(), f"{self.w1}:derive:1")
        self.assertEqual(self.starting({})().status, "moved")
        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#2"])
        self.assertEqual(self.outcome(), expected)

    def test_a_move_stopped_before_its_decision_was_kept_is_asked_again(self) -> None:
        """D: before the decision is kept nothing was decided, so attempt 2 is asked once more - as before."""
        expected = self.twin(lambda: {("W1", 1): self.waits("fix"), ("W1", 2): self.waits("other", move=True)})
        self.setUp()
        self.ask()
        self.interrupt(before_keeping, self.moving())
        self.assertEqual(self.moving()().status, "moved")
        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#2", "W1#2"])
        self.assertEqual(self.outcome(), expected)

    def test_the_move_commit_carries_the_display_the_move_was_decided_on(self) -> None:
        """BL-048: W1's display changed after the move's registration; the move commit keeps the decided one."""
        self.ask()
        self.interrupt(lambda: after_applying(rf"^{self.w1}:derive:1$"), self.moving())
        decided = self.display(self.w1)
        path = self.root / ProjectView.load(self.store).works[self.w1].path
        path.write_text(re.sub(r"(?m)^display: .*$", "display: W-99", path.read_text(encoding="utf-8"), count=1),
                        encoding="utf-8")
        git(self.root, "add", path.relative_to(self.root).as_posix())
        git(self.root, "-c", "core.hooksPath=/dev/null", "commit", "-m", "person: renumber W1")
        self.assertEqual(self.starting({})().status, "moved")
        self.assertEqual(self.subjects()[0], f"chore(workline): branch from {decided}")
        self.assertEqual(self.subjects().count(f"chore(workline): derive from {decided}"), 1)
        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#2"])


# --------------------------------------------------------------------------- E: several derivations of one cycle
class SeveralDerivationsTests(CycleCase):
    def script(self, third) -> dict:
        return {("W1", 1): self.waits("fix1"), ("W1", 2): self.waits("fix2"), ("W1", 3): third}

    def test_every_derivation_of_the_cycle_is_its_own(self) -> None:
        """E: two derivations that each made W1 wait, then a question; the answer goes on to attempt 3."""
        expected = self.twin(lambda: self.script(st.Hold("waiting for both")))
        self.setUp()
        asked = self.starting(self.script(st.QuestionWait("which way?")))()
        self.assertEqual(asked.status, "question_wait")
        result, executed, stages = self.watching(self.starting({("W1", 3): st.Hold("waiting for both")}))
        self.assertEqual((result.status, result.mutation_id), ("held", asked.mutation_id))
        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#3", "W1#3"])
        self.assertEqual(stages, [f"{self.w1}:lifecycle:1", "commit:2"])  # only the hold: nothing registered again
        self.assertEqual(executed, ["append_event", "append_event", "git_commit", "git_push"])
        self.assertEqual(self.outcome(), expected)
        self.assertEqual((len(self.named("Fix1")), len(self.named("Fix2")), self.derivation_files()), (1, 1, 2))

    def test_an_interrupted_second_derivation_goes_on_with_both(self) -> None:
        """E: the second derivation stopped in its registration or its commit; the resume continues the cycle."""
        expected = self.twin(lambda: self.script(st.Hold("waiting for both")))
        for window, make in {
            "registration applied": lambda: after_applying(rf"^{self.w1}:derive:1$"),
            "commit recorded": lambda: after_recording(r"^commit:1$"),
            "committed, not pushed": lambda: before_pushing("commit:1"),
        }.items():
            with self.subTest(window=window):
                self.setUp()
                pending = self.interrupt(make, self.starting(self.script(st.Hold("waiting for both"))))
                self.assertEqual(self.ran, ["W1#1", "W1#2"])
                result = self.starting(self.script(st.Hold("waiting for both")))()
                self.assertEqual((result.status, result.mutation_id), ("held", pending["mutation_id"]))
                self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#3"])
                self.assertEqual(self.outcome(), expected)


# --------------------------------------------------------------------------- the windows of the derivation itself
class DerivationWindowTests(CycleCase):
    def script(self) -> dict:
        return {("W1", 1): self.waits("fix"), ("W1", 2): st.Hold("waiting for Fix")}

    def test_every_window_of_a_derivation_that_keeps_its_target_resumes_as_uninterrupted(self) -> None:
        """Interrupted anywhere from keeping the decision to its push, the resume leaves what one run leaves."""
        expected = self.twin(self.script)
        stage = lambda: rf"^{self.w1}:derive:0$"  # noqa: E731
        windows = {
            "decision kept, stage not recorded": None,
            "registration recorded": lambda: after_recording(stage()),
            "one effect of it applied": lambda: after_writing_one(stage()),
            "registration applied": lambda: after_applying(stage()),
            "commit recorded": lambda: after_recording(r"^commit:0$"),
            "committed, not pushed": lambda: before_pushing("commit:0"),
        }
        for window, make in windows.items():
            with self.subTest(window=window):
                self.setUp()
                if make is None:
                    self.keep_without_recording(lambda: after_recording(stage()), self.starting(self.script()),
                                                f"{self.w1}:derive:0")
                else:
                    self.interrupt(make, self.starting(self.script()))
                self.assertEqual(self.ran, ["W1#1"])
                result = self.starting(self.script())()
                self.assertEqual(result.status, "held")
                self.assertEqual(self.ran, ["W1#1", "W1#2"])  # the derivation is not decided again
                self.assertEqual(self.outcome(), expected)

    def test_a_cycle_stopped_while_its_next_attempt_ran_resumes_at_that_attempt(self) -> None:
        """Committed and pushed, the process died while attempt 2 ran: the resume asks attempt 2."""
        expected = self.twin(self.script)
        self.setUp()
        real = by_attempt(self.ran, self.script(), default=completing_executor(self.store))
        call = self.starting({}, executor=interrupted_executor(real, "W1", 2))
        pending = self.interrupt(nullcontext, call)
        self.assertEqual(self.head(), self.remote_head())
        result = call()
        self.assertEqual((result.status, result.mutation_id), ("held", pending["mutation_id"]))
        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#2"])
        self.assertEqual(self.outcome(), expected)


# --------------------------------------------------------------------------- F, G, H: what is not the cycle's own
class NotOwnTests(CycleCase):
    works = {"w1": "W1 done", "w2": "W2 done"}
    entry_options = {"entry": "w1"}

    def test_a_relation_a_person_added_meanwhile_still_stops_the_resume(self) -> None:
        """G: a Work the cycle derived without waiting for it, made W1's predecessor by a person, is counted."""
        self.ask(self.waits("fix", others=("other",)))
        other, fix = self.named("Other")[0], self.named("Fix")[0]
        original = (self.root / ROADMAP_YAML).read_bytes()
        self.hand_add(other)
        refused = self.assertStoppedUntouched(self.starting({("W1", 2): st.Hold("later")}), "dependency_unsatisfied")
        self.assertIn(other, str(refused))
        self.assertNotIn(fix, str(refused))
        (self.root / ROADMAP_YAML).write_bytes(original)
        self.assertEqual(self.starting({("W1", 2): st.Hold("later")})().status, "held")

    def test_a_relation_a_person_added_from_another_work_still_stops_the_resume(self) -> None:
        """G: W2, which the cycle never touched, made W1's predecessor by a person, is counted."""
        self.ask()
        self.hand_add(self.w2)
        refused = self.assertStoppedUntouched(self.starting({("W1", 2): st.Hold("later")}), "dependency_unsatisfied")
        self.assertIn(self.w2, str(refused))
        self.assertNotIn(self.named("Fix")[0], str(refused))

    def test_a_record_that_cannot_show_its_derivations_keeps_the_precheck(self) -> None:
        """H: no kept derivations, or ones that no longer speak for every derivation - nothing is left out."""
        for label, change in (("no derivations kept", lambda notes: notes.pop(st._DERIVATIONS)),
                              ("derivations incomplete", lambda notes: notes[st._DERIVATIONS].update(
                                  {"complete": False, "derivations": []}))):
            with self.subTest(record=label):
                self.setUp()
                self.ask()
                self.edit_record(lambda record: change(record["notes"]))
                refused = self.assertStoppedUntouched(self.starting({("W1", 2): st.Hold("later")}), "dependency_unsatisfied")
                self.assertIn(self.named("Fix")[0], str(refused))


class CycleShapeTests(CycleCase):
    def rename(self, old: str, new: str) -> None:
        def change(record: dict) -> None:
            for effect in record["effects"]:
                if effect["stage"] == old:
                    effect["stage"] = new

        self.edit_record(change)

    def test_a_record_whose_cycle_holds_another_stage_keeps_the_precheck(self) -> None:
        """H: after the stage that opened the cycle, anything but its registrations and Git stages shows no cycle."""
        for label in ("a stage after the registration", "no opening stage before the registration"):
            with self.subTest(record=label):
                self.setUp()
                self.ask()
                if label == "a stage after the registration":
                    self.rename("commit:0", f"{self.w1}:results:0")
                else:
                    self.rename(f"{self.w1}:lifecycle:0", f"{self.w1}:note:0")
                refused = self.assertStoppedUntouched(self.starting({("W1", 2): st.Hold("later")}),
                                                      "dependency_unsatisfied")
                self.assertIn(self.named("Fix")[0], str(refused))


class PreexistingDependencyTests(CycleCase):
    """W1 waits for W2 by the Phase's own plan."""

    works = {"w1": "W1 done", "w2": "W2 done"}
    entry_options = {"entry": "w2", "requires_completion": (("w2", "w1"),)}

    def test_a_dependency_the_project_held_before_still_stops_the_start(self) -> None:
        """F: the plan's own dependency stops W1 where it is opened, and nothing is recorded."""
        with self.assertRaises(StopError) as refused:
            self.starting({("W1", 1): self.waits("fix")})()
        self.assertEqual(refused.exception.code, "dependency_unsatisfied")
        self.assertIn(self.w2, str(refused.exception))
        self.assertEqual((self.ran, self.pending(), self.events(self.w1)), ([], [], []))
        # once it is satisfied, W1's own cycle goes on past the dependency it registered itself
        self.assertEqual(self.starting({}, work_id=self.w2)().status, "completed")
        self.ask()
        self.assertEqual(self.starting({("W1", 2): st.Hold("waiting for Fix")})().status, "held")
        self.assertEqual(self.ran, ["W2#1", "W1#1", "W1#2", "W1#2"])


# --------------------------------------------------------------------------- I, J: a record or relation that is not the registration
class TamperTests(CycleCase):
    works = {"w1": "W1 done"}

    def tamper_stage(self, stage: str, change) -> None:
        def edit(record: dict) -> None:
            for effect in record["effects"]:
                if effect["stage"] == stage:
                    change(record, effect)

        self.edit_record(edit)

    def is_the_dependency(self, effect: dict) -> bool:
        record = effect["payload"].get("record") if effect["kind"] == "add_relation" else None
        return isinstance(record, dict) and (record["type"], record["to"]) == ("requires_completion", self.w1)

    def test_a_registration_other_than_the_decision_makes_is_refused_before_anything_runs(self) -> None:
        """I: the record's decision and its registration must agree, compared exactly, before anything is left out."""

        def reserved(record: dict, effect: dict) -> None:
            if self.is_the_dependency(effect):
                key = next(k for k, v in record["reserved_ids"].items() if v == effect["payload"]["record"]["id"])
                record["reserved_ids"][key] = new_id("relation")

        def decided_work(record: dict) -> None:
            outcome = record["notes"][st._DERIVATIONS]["derivations"][0]["outcome"]
            outcome["works"][0]["work"]["desired_state"] = "something else"

        def decided_relation(record: dict) -> None:
            outcome = record["notes"][st._DERIVATIONS]["derivations"][0]["outcome"]
            outcome["relations"][0]["to"] = self.i1

        stage = lambda: f"{self.w1}:derive:0"  # noqa: E731
        for label, window, change in (
            ("reserved relation ID", None, lambda: self.tamper_stage(stage(), reserved)),
            ("decided Work", None, lambda: self.edit_record(decided_work)),
            ("decided relation", None, lambda: self.edit_record(decided_relation)),
            ("recorded Work body", "registration recorded", lambda: self.tamper_stage(stage(), lambda record, effect: (
                effect["payload"].update({"content": effect["payload"]["content"].replace("Fix done", "else")})
                if effect["kind"] == "write_file" and "Fix done" in effect["payload"].get("content", "") else None))),
        ):
            with self.subTest(tampered=label):
                self.setUp()
                if window is None:
                    self.ask()
                else:
                    self.interrupt(lambda: after_recording(rf"^{stage()}$"), self.starting({("W1", 1): self.waits("fix")}))
                change()
                records = {p.name: p.read_bytes() for p in self.store.mutations.glob("*.yaml")}
                refused = self.assertNotReplayed(self.starting({("W1", 2): st.Hold("later")}))
                self.assertIn("other than the registration the derivation it decided makes", str(refused))
                self.assertEqual(self.events(self.w1), STARTED)
                if window is None:  # applied and committed: the refusal writes nothing, the record included
                    self.assertEqual({p.name: p.read_bytes() for p in self.store.mutations.glob("*.yaml")}, records)

    def test_a_relation_changed_in_the_project_is_refused_by_the_replay(self) -> None:
        """J: the relation the cycle registered, changed under its ID while the question waited, is not its own."""
        self.ask(self.waits("fix", others=("other",)))
        path = self.root / ROADMAP_YAML
        original = path.read_bytes()
        mine = self.relation_id("Fix")
        other = self.named("Other")[0]
        path.write_bytes(re.sub(
            rf"(- id: {mine}\r?\n    type: requires_completion\r?\n    from: )\S+".encode("utf-8"),
            lambda m: m.group(1) + other.encode("utf-8"), original))
        head, remote = self.head(), self.remote_head()
        with self.assertRaises(ReconcileRequired) as refused:
            self.starting({("W1", 2): st.Hold("later")})()
        self.assertIn("applied with unexpected result", str(refused.exception))
        self.assertEqual((self.head(), self.remote_head(), self.ran), (head, remote, ["W1#1", "W1#2"]))
        path.write_bytes(original)
        self.assertEqual(self.starting({("W1", 2): st.Hold("later")})().status, "held")

    def test_a_relation_that_no_longer_holds_what_was_registered_is_counted(self) -> None:
        """J: under the registered ID, the Project holds another predecessor by the time the precheck reads it."""
        self.ask(self.waits("fix", others=("other",)))
        path = self.root / ROADMAP_YAML
        original = path.read_bytes()
        mine = self.relation_id("Fix")
        other = self.named("Other")[0]
        real = Mutation.apply
        done = {"n": 0}

        def apply(mutation):
            outcome = real(mutation)
            if not done["n"]:  # right after the resume's replay has shown every recorded effect in place
                done["n"] += 1
                path.write_bytes(re.sub(
                    rf"(- id: {mine}\r?\n    type: requires_completion\r?\n    from: )\S+".encode("utf-8"),
                    lambda m: m.group(1) + other.encode("utf-8"), path.read_bytes()))
            return outcome

        head, remote, stages = self.head(), self.remote_head(), self.stage_names()
        with mock.patch.object(Mutation, "apply", apply), self.assertRaises(StopError) as refused:
            self.starting({("W1", 2): st.Hold("later")})()
        self.assertEqual(refused.exception.code, "dependency_unsatisfied")
        self.assertIn(other, str(refused.exception))
        self.assertEqual((self.head(), self.remote_head(), self.stage_names(), self.ran),
                         (head, remote, stages, ["W1#1", "W1#2"]))
        path.write_bytes(original)
        self.assertEqual(self.starting({("W1", 2): st.Hold("later")})().status, "held")


# --------------------------------------------------------------------------- K: the branch comes first
class BranchTests(CycleCase):
    def test_a_resume_off_the_branch_the_cycle_was_decided_on_is_refused_first(self) -> None:
        """K: BL-036 / BL-038 refuse before the precheck, the replay, the executor, a commit or a push."""
        for label in ("registration not committed yet", "question wait, branch without the commit"):
            with self.subTest(case=label):
                self.setUp()
                script = {("W1", 1): self.waits("fix"), ("W1", 2): st.Hold("waiting for Fix")}
                if label == "registration not committed yet":
                    self.interrupt(lambda: after_applying(rf"^{self.w1}:derive:0$"), self.starting(script))
                    git(self.root, "checkout", "-q", "-b", "elsewhere")
                else:
                    self.ask()
                    git(self.root, "checkout", "-q", "-b", "elsewhere", "HEAD~1")
                ran, head, remote, stages = list(self.ran), self.head(), self.remote_head(), self.stage_names()
                derived: list[str] = []
                real = st._Session._derive
                with mock.patch.object(st._Session, "_derive", lambda *a, **k: derived.append("x") or real(*a, **k)), \
                        self.assertRaises(ReconcileRequired):
                    self.starting(script)()
                self.assertEqual((self.ran, derived, self.stage_names()), (ran, [], stages))
                self.assertEqual((self.head(), self.remote_head()), (head, remote))
                git(self.root, "checkout", "-q", "main")
                self.assertEqual(self.starting(script)().status, "held")
                self.assertEqual(self.outcome()["pending"], [])


# --------------------------------------------------------------------------- L, M, N: the dependency itself stays
class DependencyStaysTests(CycleCase):
    def test_the_work_does_not_complete_while_its_own_dependency_is_unfinished(self) -> None:
        """L: the continuation is let in, but completion still requires what the cycle made it wait for."""
        for label in ("uninterrupted", "after the answer"):
            with self.subTest(run=label):
                self.setUp()
                if label == "uninterrupted":
                    call = self.starting({("W1", 1): self.waits("fix")})  # attempt 2 completes (the default)
                else:
                    self.ask()
                    call = self.starting({})
                with self.assertRaises(StopError) as refused:
                    call()
                self.assertEqual(refused.exception.code, "completion_precheck_failed")
                self.assertIn(self.named("Fix")[0], str(refused.exception))
                self.assertEqual(self.state(), ("in_progress", True))
                self.assertNotIn("work_completed", self.events(self.w1))
                self.assertIn(("requires_completion", "Fix", "W1"), self.relations())
                self.assertEqual(len(self.pending()), 1)

    def test_a_cycle_that_ended_leaves_the_dependency_to_every_later_entry(self) -> None:
        """M, N: once the move ended the cycle, W1 is not entered again until Fix is complete - then it is."""
        self.ask()
        self.assertEqual(self.starting({("W1", 2): self.waits(others=("other",), move=True)})().status, "moved")
        fix = self.named("Fix")[0]
        for mode in ("single-work", "outer"):
            with self.subTest(mode=mode):
                with self.assertRaises(StopError) as refused:
                    self.starting({}, mode=mode)()
                self.assertEqual(refused.exception.code, "dependency_unsatisfied")
                self.assertIn(fix, str(refused.exception))
                self.assertEqual((self.pending(), self.events(self.w1)), ([], MOVED))
        self.assertEqual(self.starting({}, work_id=fix)().status, "completed")
        result = self.starting({})()
        self.assertEqual(result.status, "completed")
        self.assertEqual(self.events(self.w1), MOVED + ["work_target_added", "work_target_removed", "work_completed"])
        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#2", "Fix#1", "W1#1"])
        self.assertEqual((self.pending(), validate_project(self.store)), ([], []))

    def test_a_target_removed_outside_start_ends_the_exemption_with_the_cycle(self) -> None:
        """M: the Work no longer carrying its cycle's target, its entry is a new cycle's and counts every dependency."""
        self.ask()
        path = self.root / EVENT_LOG
        original = path.read_bytes()
        at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        event = {"id": new_id("event"), "type": "work_target_removed", "entity": self.w1, "at": at}
        path.write_bytes(original + (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
        self.assertEqual(self.state(), ("in_progress", False))
        refused = self.assertStoppedUntouched(self.starting({("W1", 2): st.Hold("later")}), "dependency_unsatisfied")
        self.assertIn(self.named("Fix")[0], str(refused))
        path.write_bytes(original)
        self.assertEqual(self.starting({("W1", 2): st.Hold("later")})().status, "held")


# --------------------------------------------------------------------------- O: outer mode
class OuterTests(CycleCase):
    works = {"w1": "W1 done", "w2": "W2 done"}
    entry_options = {"entry": "w1"}

    def test_an_outer_start_continues_the_cycle_of_the_work_carrying_the_target(self) -> None:
        """O: W1 completed, W2 derived Fix and waits for it, then asked; the outer resume goes on with W2's cycle."""
        script = {("W2", 1): self.waits("fix", into=self.w2), ("W2", 2): st.QuestionWait("which way?")}
        asked = self.starting(script, mode="outer")()
        self.assertEqual((asked.status, asked.work_id, self.ran), ("question_wait", self.w2, ["W1#1", "W2#1", "W2#2"]))
        result, _, stages = self.watching(self.starting({("W2", 2): st.Hold("waiting for Fix")}, mode="outer"))
        self.assertEqual((result.status, result.work_id, result.mutation_id), ("held", self.w2, asked.mutation_id))
        self.assertEqual(self.ran, ["W1#1", "W2#1", "W2#2", "W2#2"])
        self.assertEqual(stages, [f"{self.w2}:lifecycle:1", "commit:1"])
        self.assertEqual((self.events(self.w2), len(self.named("Fix")), self.derivation_files()), (HELD, 1, 1))
        self.assertEqual((self.pending(), self.dirty(), self.head()), ([], [], self.remote_head()))


# --------------------------------------------------------------------------- contracts it keeps
class ContractTests(CycleCase):
    def test_a_person_s_change_to_the_fix_work_is_still_refused(self) -> None:
        """BL-043: the fix Work file the cycle wrote, changed by a person, is refused by the replay itself."""
        self.ask()
        path = self.root / ProjectView.load(self.store).works[self.named("Fix")[0]].path
        original = path.read_bytes()
        path.write_bytes(original + b"\nperson's note\n")
        head, remote = self.head(), self.remote_head()
        for _ in range(2):
            with self.assertRaises(ReconcileRequired) as refused:
                self.starting({("W1", 2): st.Hold("later")})()
            self.assertIn("applied with unexpected result", str(refused.exception))
        self.assertEqual(path.read_bytes(), original + b"\nperson's note\n")
        self.assertEqual((self.head(), self.remote_head(), self.ran), (head, remote, ["W1#1", "W1#2"]))
        path.write_bytes(original)
        self.assertEqual(self.starting({("W1", 2): st.Hold("later")})().status, "held")

    def test_a_person_s_change_to_the_relation_ledger_is_neither_committed_nor_erased(self) -> None:
        """BL-043: the replay's commit refuses the person's bytes; they stay, nothing is committed or pushed."""
        self.ask()
        path = self.root / ROADMAP_YAML
        original = path.read_bytes()
        path.write_bytes(original + b"# person's note\n")
        head, remote = self.head(), self.remote_head()
        with self.assertRaises(ReconcileRequired) as refused:
            self.starting({("W1", 2): st.Hold("later")})()
        self.assertIn("cannot show the change it would commit is its own", str(refused.exception))
        self.assertEqual(path.read_bytes(), original + b"# person's note\n")
        self.assertEqual((self.head(), self.remote_head(), self.ran), (head, remote, ["W1#1", "W1#2"]))

    def test_a_commit_made_meanwhile_is_not_published_by_the_cycle_s_recorded_push(self) -> None:
        """BL-050: a person's commit on the branch while the question waited is not what the replayed push sends."""
        self.ask()
        published = self.remote_head()
        (self.root / "person.txt").write_text("person\n", encoding="utf-8")
        git(self.root, "add", "person.txt")
        git(self.root, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "person: unrelated")
        mine = self.head()
        for _ in range(2):
            self.assertEqual(self.starting({("W1", 2): st.QuestionWait("still?")})().status, "question_wait")
            self.assertEqual((self.remote_head(), self.head()), (published, mine))
        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#2", "W1#2"])


class RemotelessTests(CycleCase):
    remote = False

    def test_a_commit_its_replay_refused_over_a_persons_change_does_not_end_the_cycle(self) -> None:
        """The replay's commit refused over a person's ledger change; once they undo it the cycle goes on.

        The commit is refused before its Git stage is written into the record
        (BL-053), so what the cycle holds is exactly what it held before the
        refusal. This once pinned that stage as recorded, which is the state
        that then poisoned every later resume.
        """
        expected = self.twin(lambda: {("W1", 1): self.waits("fix"), ("W1", 2): st.Hold("later")})
        self.setUp()
        self.ask()
        path = self.root / ROADMAP_YAML
        original = path.read_bytes()
        stages = self.stage_names()
        path.write_bytes(original + b"# person's note\n")
        with self.assertRaises(ReconcileRequired) as refused:
            self.starting({("W1", 2): st.Hold("later")})()
        self.assertIn("cannot show the change it would commit is its own", str(refused.exception))
        self.assertEqual(path.read_bytes(), original + b"# person's note\n")
        self.assertEqual(self.stage_names(), stages)  # the refused commit is not recorded as a Git stage
        path.write_bytes(original)
        self.assertEqual(self.starting({("W1", 2): st.Hold("later")})().status, "held")
        self.assertEqual(self.ran, ["W1#1", "W1#2", "W1#2"])
        self.assertEqual(self.outcome(), expected)


if __name__ == "__main__":
    unittest.main()
