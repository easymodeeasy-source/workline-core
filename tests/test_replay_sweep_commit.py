"""START finishes a recorded move whose registration a replay's own commit already carries (BL-052).

A cycle that decides a derivation which keeps the target and then one which
removes it records, in order: the first registration, the commit that carries it,
the move's registration, the removal of the target, and the commit that carries
the move. Interrupted with the move's registration recorded and its removal not,
the resume replays the cycle (BL-046) - and the replay of the first derivation
commits every owned path it finds uncommitted, the move's registration among
them, under its own ``derive from`` message. That Git stage lands between the
move's registration and the removal the next attempt records (BL-051 residual
(a), which this change leaves exactly as it is).

``_derive_move_to_finish`` read the removal as the stage immediately after the
registration, so from then on it could not show the move at all. It returned
"not a move of mine", and the next resume treated the Work as one to open: with a
dependency the cycle had registered into it, ``dependency_unsatisfied`` on every
retry with the record pending and the removal left uncommitted; without one, the
Work was opened again - a second ``work_target_added``, the executor asked again,
and another set of Works, relations and derivation details on every retry; in
``outer`` mode the mutation completed with no commit carrying the move at all,
leaving the removal event uncommitted so that every later operation refused it.

A Git stage decides nothing, so the proof now passes over at most the one commit
of its own a cycle can hold there (:func:`workline.start._own_git_stage`) and
looks for the removal after it. What shows the move is unchanged: the
registration this START decided (BL-046), the removal of that Work's target under
the ID reserved for it, and the commit carrying the move with the message that
move was decided on (BL-048). Nothing else is passed over - a lifecycle stage, a
result, a registration, a stage holding a file effect beside its commit, one
whose commit names a path no effect of this mutation writes, or more than the one
commit - and a record that cannot show its move is left exactly as it was.

The windows here are named by what the record holds, never by a stage number: the
same window is a different stage number under a different fix, which is how this
shape went unpinned.
"""

from __future__ import annotations

import re
import unittest
from unittest import mock

from helpers import git
from test_current_cycle_dependency_resume import CycleCase
from test_recorded_move_dependency import Interrupted
from workline import start as st
from workline.errors import ReconcileRequired, StopError
from workline.ids import new_id
from workline.mutation import Mutation, MutationController, effect_path
from workline.ops import finalization_proven
from workline.state import ProjectView
from workline.store import WORKLINE_DIR

STARTED = ["work_started", "work_target_added"]
MOVED = STARTED + ["work_target_removed"]


# --------------------------------------------------------------------------- what the record holds
def _derivations(mutation: Mutation) -> list[dict]:
    note = mutation.note(st._DERIVATIONS)
    entries = note.get("derivations") if isinstance(note, dict) else None
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def _move_registration(mutation: Mutation) -> str | None:
    """The stage the move this record keeps decides, by that kept decision - not by its number."""
    for entry in _derivations(mutation):
        outcome = entry.get("outcome")
        if isinstance(outcome, dict) and outcome.get("move"):
            return entry.get("stage")
    return None


def _removes_target(effect) -> bool:
    record = effect.payload.get("record") if effect.kind == "append_event" else None
    return isinstance(record, dict) and record.get("type") == "work_target_removed"


def _removal_recorded(mutation: Mutation) -> bool:
    return any(
        e["kind"] == "append_event"
        and isinstance(e["payload"].get("record"), dict)
        and e["payload"]["record"].get("type") == "work_target_removed"
        for e in mutation.effects
    )


def _git_only(effects) -> bool:
    return bool(effects) and all(e.kind in ("git_commit", "git_push") for e in effects)


def _finalizes_a_move(message: object) -> bool:
    return any(finalization_proven(kind, None, message) for kind in st._MOVE_FINALIZATIONS.values())


def _carries_a_move(effects) -> bool:
    return any(e.kind == "git_commit" and _finalizes_a_move(e.payload.get("message")) for e in effects)


# --------------------------------------------------------------------------- the windows, by what they hold
def after_the_move_is_registered():
    """Stop once the stage the move decides is applied, with the removal of the target not recorded yet."""
    real = Mutation.apply

    def fire(mutation):
        before = {e["seq"] for e in mutation.record.get("effects") or [] if e.get("applied")}
        outcome = real(mutation)
        stage = _move_registration(mutation)
        if stage is not None and not _removal_recorded(mutation) and any(
            e.get("applied") and e["seq"] not in before and e["stage"] == stage
            for e in mutation.record.get("effects") or []
        ):
            raise Interrupted("the move's registration is applied")
        return outcome

    return mock.patch.object(Mutation, "apply", fire)


def after_the_replay_commits_the_registration():
    """Stop once a Git stage of this mutation's own is recorded over the move's registration.

    The record holds that registration, no removal of the target yet, and the
    commit being recorded is not the one that carries the move: it is the commit
    the replay of an earlier derivation of the same cycle makes.
    """
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        real(mutation, stage, effects)
        if (
            _move_registration(mutation) is not None
            and not _removal_recorded(mutation)
            and _git_only(effects)
            and not _carries_a_move(effects)
        ):
            raise Interrupted("the replay's commit over the move's registration is recorded")

    return mock.patch.object(Mutation, "add_effects", fire)


def after_the_target_removal_is_recorded():
    """Stop once the stage holding the removal of the moving Work's target is recorded, none of it applied."""
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        real(mutation, stage, effects)
        if any(_removes_target(effect) for effect in effects):
            raise Interrupted("the removal of the target is recorded")

    return mock.patch.object(Mutation, "add_effects", fire)


def after_the_target_removal_is_applied():
    """Stop once the removal of the moving Work's target is applied."""
    real = Mutation.apply

    def fire(mutation):
        before = {e["seq"] for e in mutation.record.get("effects") or [] if e.get("applied")}
        outcome = real(mutation)
        if any(
            e.get("applied") and e["seq"] not in before and e["kind"] == "append_event"
            and isinstance(e["payload"].get("record"), dict)
            and e["payload"]["record"].get("type") == "work_target_removed"
            for e in mutation.record.get("effects") or []
        ):
            raise Interrupted("the removal of the target is applied")
        return outcome

    return mock.patch.object(Mutation, "apply", fire)


def after_the_move_commit_is_recorded():
    """Stop once the Git stage whose commit message finalizes the move is recorded, none of it applied."""
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        real(mutation, stage, effects)
        if _carries_a_move(effects):
            raise Interrupted("the commit carrying the move is recorded")

    return mock.patch.object(Mutation, "add_effects", fire)


def before_the_move_commit_is_pushed():
    """Stop with the commit that carries the move made and its push not made."""
    real = MutationController.apply_effect
    carrying = {"stage": None}

    def fire(controller, record):
        if record["kind"] == "git_commit" and _finalizes_a_move(record["payload"].get("message")):
            carrying["stage"] = record["stage"]
        if record["kind"] == "git_push" and record["stage"] == carrying["stage"]:
            raise Interrupted("the commit carrying the move is made, its push is not")
        return real(controller, record)

    return mock.patch.object(MutationController, "apply_effect", fire)


# --------------------------------------------------------------------------- the Project, and the record under test
class SweepCase(CycleCase):
    """W1 derives once keeping its target, then moves - the smallest cycle that records the shape.

    No question wait is needed: one process decides both derivations, and two
    interruptions of it are enough.
    """

    def script(self, *, waits: bool = True) -> dict:
        """Attempt 1 derives and keeps the target, attempt 2 derives and moves it away.

        With ``waits`` each derivation also makes W1 wait for what it derived, which is what turned
        this shape into a deadlock; without it the resume opened the Work again instead.
        """
        if waits:
            return {("W1", 1): self.waits("mid"), ("W1", 2): self.waits("other", move=True)}
        return {("W1", 1): self.waits(others=("mid",)), ("W1", 2): self.waits(others=("other",), move=True)}

    def outer_twin(self, script) -> dict:
        self.setUp()
        self.starting(script(), mode="outer")()
        return self.outcome()

    # the record ------------------------------------------------------------------
    def swept(self, *, waits: bool = True, mode: str = "single-work", then=None) -> str:
        """Drive the Project to the record BL-052 is about, and return the pending mutation's ID.

        Interrupted once with the move's registration applied and its removal not
        recorded; the resume's replay of the first derivation commits that
        registration, and ``then`` - the removal recorded, by default - stops it
        again. The shape is asserted by what the record holds.
        """
        run = lambda: self.starting(self.script(waits=waits), mode=mode)  # noqa: E731
        self.interrupt(after_the_move_is_registered, run())
        self.interrupt(then or after_the_target_removal_is_recorded, run())
        (pending,) = self.pending()
        self.assertSwept()
        return pending["mutation_id"]

    def shape(self) -> tuple[str, list[str], str]:
        """From the pending record: the move's registration stage, the stages between it and the removal, the removal."""
        (pending,) = self.pending()
        entries = pending["notes"][st._DERIVATIONS]["derivations"]
        registration = next(e["stage"] for e in entries if e["outcome"]["move"])
        effects = pending["effects"]
        stages: list[str] = []
        for effect in effects:
            if effect["stage"] not in stages:
                stages.append(effect["stage"])
        removal = next(
            effect["stage"] for effect in effects
            if effect["kind"] == "append_event" and effect["payload"]["record"]["type"] == "work_target_removed"
        )
        return registration, stages[stages.index(registration) + 1: stages.index(removal)], removal

    def assertSwept(self) -> str:
        """Exactly one stage sits between the move's registration and the removal, and it is a Git stage of this
        mutation: one ``git_commit``, with the ``git_push`` that publishes it, over paths its own effects write."""
        (pending,) = self.pending()
        registration, between, removal = self.shape()
        self.assertEqual(len(between), 1, f"{registration} .. {removal} holds {between}")
        (stage,) = between
        effects = [e for e in pending["effects"] if e["stage"] == stage]
        self.assertEqual([e["kind"] for e in effects], ["git_commit", "git_push"])
        self.assertFalse(_finalizes_a_move(effects[0]["payload"]["message"]))
        written = {effect_path(e) for e in pending["effects"]} - {None}
        self.assertTrue(set(effects[0]["payload"]["paths"]) <= written, effects[0]["payload"]["paths"])
        return stage

    def assertShowsNoMove(self, call, code: str) -> None:
        """The record is not read as a move: nothing of the cycle is registered again, the executor is not asked, the
        record is left pending and START stops with ``code``.

        Either the Work is entered as one to open and stops on the dependency the
        cycle registered into it (``dependency_unsatisfied``), or the record is
        refused outright (``reconcile_required``). What must never happen is a
        move being taken from a record that cannot show one.
        """
        ran, derived = list(self.ran), []
        real = st._Session._derive
        with mock.patch.object(st._Session, "_derive", lambda *a, **k: derived.append("x") or real(*a, **k)), \
                self.assertRaises(StopError) as refused:
            call()
        self.assertEqual(refused.exception.code, code)
        self.assertEqual((self.ran, derived), (ran, []))
        self.assertTrue(self.pending())

    def tamper(self, stage: str, change) -> None:
        def edit(record: dict) -> None:
            for effect in list(record["effects"]):
                if effect["stage"] == stage:
                    change(record, effect)

        self.edit_record(edit)


# --------------------------------------------------------------------------- A: the minimal window
class MinimalWindowTests(SweepCase):
    def test_the_move_is_finished_when_the_cycle_made_its_work_wait(self) -> None:
        """A: two interruptions, no question wait. Before: ``dependency_unsatisfied`` on every retry."""
        expected = self.twin(lambda: self.script())
        self.setUp()
        mutation_id = self.swept()
        decided = self.display(self.w1)
        result, executed, stages = self.watching(self.starting(self.script()))
        self.assertEqual((result.status, result.work_id, result.mutation_id), ("moved", self.w1, mutation_id))
        self.assertEqual(self.ran, ["W1#1", "W1#2"])  # neither derivation is decided again
        self.assertEqual([stage for stage in stages if not stage.startswith("commit:")], [])
        # the recorded removal is replayed, then the Git stage carrying the move is made and published: nothing else
        self.assertEqual(executed, ["append_event", "git_commit", "git_push"])
        self.assertEqual(self.subjects()[0], f"chore(workline): branch from {decided}")
        self.assertEqual(self.events(self.w1), MOVED)
        self.assertEqual(self.settled(self.outcome()), self.settled(expected))

    def test_the_move_is_finished_when_the_cycle_made_it_wait_for_nothing(self) -> None:
        """A: before, the Work was opened again, asked again and derived again on every retry."""
        expected = self.twin(lambda: self.script(waits=False))
        self.setUp()
        mutation_id = self.swept(waits=False)
        works, relations, details = self.named("Other"), self.relations(), self.derivation_files()
        result = self.starting(self.script(waits=False))()
        self.assertEqual((result.status, result.mutation_id), ("moved", mutation_id))
        self.assertEqual(self.ran, ["W1#1", "W1#2"])  # the executor is not asked a third time
        self.assertEqual((self.named("Other"), self.relations(), self.derivation_files()), (works, relations, details))
        self.assertEqual((len(self.named("Mid")), len(self.named("Other"))), (1, 1))
        self.assertEqual(self.events(self.w1), MOVED)  # one work_target_added, one work_target_removed
        self.assertEqual(self.settled(self.outcome()), self.settled(expected))

    def test_the_move_is_finished_in_outer_mode(self) -> None:
        """A: before, ``outer`` chose the next Work and completed the mutation with no commit carrying the move,
        leaving the removal event uncommitted so every later operation refused the Project."""
        expected = self.outer_twin(lambda: self.script())
        self.setUp()
        self.swept(mode="outer")
        decided = self.display(self.w1)
        self.starting(self.script(), mode="outer")()
        self.assertEqual(self.subjects().count(f"chore(workline): branch from {decided}"), 1)
        self.assertEqual(self.events(self.w1), MOVED)
        self.assertEqual((self.pending(), self.dirty()), ([], []))
        self.assertEqual(self.settled(self.outcome()), self.settled(expected))

    def test_the_git_stage_the_replay_recorded_is_kept_as_it_is(self) -> None:
        """A: BL-051 residual (a) is not what this closes - that extra commit is still recorded and still made."""
        self.swept()
        self.assertSwept()
        display = self.display(self.w1)
        self.assertEqual(self.starting(self.script())().status, "moved")
        # uninterrupted the cycle makes one 'derive from' commit; the replay's own is the second
        self.assertEqual(self.subjects().count(f"chore(workline): derive from {display}"), 2)
        self.assertEqual(self.subjects().count(f"chore(workline): branch from {display}"), 1)


# --------------------------------------------------------------------------- B: every window after that commit
class WindowTests(SweepCase):
    def windows(self) -> dict:
        """Every window from the replay's commit to the push of the commit carrying the move."""
        return {
            "the replay's commit recorded": after_the_replay_commits_the_registration,
            "the removal recorded": after_the_target_removal_is_recorded,
            "the removal applied": after_the_target_removal_is_applied,
            "the move's commit recorded": after_the_move_commit_is_recorded,
            "the move committed, not pushed": before_the_move_commit_is_pushed,
        }

    def test_every_window_after_the_replay_s_commit_finishes_the_move(self) -> None:
        """B: the record holds that Git stage in each of them; each next resume ends the cycle as uninterrupted."""
        for waits in (True, False):
            expected = self.twin(lambda waits=waits: self.script(waits=waits))
            for label, window in self.windows().items():
                with self.subTest(window=label, waits=waits):
                    self.setUp()
                    run = lambda waits=waits: self.starting(self.script(waits=waits))  # noqa: E731
                    self.interrupt(after_the_move_is_registered, run())
                    self.interrupt(window, run())
                    decided = self.display(self.w1)
                    result = run()()
                    self.assertEqual(result.status, "moved")
                    self.assertEqual(self.ran, ["W1#1", "W1#2"])
                    self.assertEqual(self.subjects().count(f"chore(workline): branch from {decided}"), 1)
                    self.assertEqual(self.events(self.w1), MOVED)
                    self.assertEqual(self.settled(self.outcome()), self.settled(expected))

    def test_a_third_interruption_after_that_commit_still_finishes_the_move(self) -> None:
        """B: stopped at the replay's commit, then at the removal, then finished - three interruptions."""
        expected = self.twin(lambda: self.script())
        self.setUp()
        run = lambda: self.starting(self.script())  # noqa: E731
        self.interrupt(after_the_move_is_registered, run())
        self.interrupt(after_the_replay_commits_the_registration, run())
        self.interrupt(after_the_target_removal_is_recorded, run())
        self.assertSwept()
        self.assertEqual(run()().status, "moved")
        self.assertEqual(self.ran, ["W1#1", "W1#2"])
        self.assertEqual(self.settled(self.outcome()), self.settled(expected))

    def test_the_window_before_the_removal_is_recorded_is_unchanged(self) -> None:
        """B: with that Git stage recorded and no removal, the cycle records the removal itself, exactly as before."""
        expected = self.twin(lambda: self.script())
        self.setUp()
        run = lambda: self.starting(self.script())  # noqa: E731
        self.interrupt(after_the_move_is_registered, run())
        self.interrupt(after_the_replay_commits_the_registration, run())
        result, _, stages = self.watching(run())
        self.assertEqual(result.status, "moved")
        self.assertEqual([s for s in stages if not s.startswith("commit:")], [f"{self.w1}:lifecycle:1"])
        self.assertEqual(self.ran, ["W1#1", "W1#2"])
        self.assertEqual(self.settled(self.outcome()), self.settled(expected))


# --------------------------------------------------------------------------- C: what is never passed over
class NotAGitStageTests(SweepCase):
    def test_a_stage_that_is_not_this_mutation_s_git_stage_is_not_passed_over(self) -> None:
        """C: only a Git stage of this START - one commit, its push, over paths its own effects write - is passed
        over. Anything else leaves the move unshown, exactly as a record of a shape START does not write always did."""
        def rename(record, effect):
            effect["stage"] = f"{self.w1}:results:0"

        def add_a_file_effect(record, effect):
            """An event this mutation already applied, recorded again under the Git stage."""
            if effect["kind"] != "git_commit":
                return
            event = next(e for e in record["effects"] if e["kind"] == "append_event" and e.get("applied"))
            top = max(e["seq"] for e in record["effects"])
            record["effects"].insert(
                record["effects"].index(effect), {**event, "stage": effect["stage"], "seq": top + 1})

        def drop_the_commit(record, effect):
            if effect["kind"] == "git_commit":
                record["effects"].remove(effect)

        def a_path_no_effect_writes(record, effect):
            if effect["kind"] == "git_commit":
                effect["payload"]["paths"] = ["README.md"]

        def no_paths(record, effect):
            if effect["kind"] == "git_commit":
                effect["payload"]["paths"] = []

        for label, change, code in (
            ("under a name that is not a commit stage", rename, "dependency_unsatisfied"),
            ("holding an effect beside its commit", add_a_file_effect, "reconcile_required"),
            ("holding only the push", drop_the_commit, "reconcile_required"),
            ("committing a path no effect of this mutation writes", a_path_no_effect_writes, "reconcile_required"),
            ("committing no path at all", no_paths, "reconcile_required"),
        ):
            with self.subTest(stage=label):
                self.setUp()
                self.swept()
                self.tamper(self.assertSwept(), change)
                self.assertShowsNoMove(self.starting(self.script()), code)

    def test_a_commit_and_push_recorded_in_the_other_order_is_not_passed_over(self) -> None:
        """C: the shape is the one ``_Session._commit`` records - the commit, then the push that publishes it.

        A stage whose kinds merely look like Git is not one of these. Such a record is refused where a push
        must be shown to publish its own stage's commit (BL-050) rather than at this proof, so what is pinned
        here is that no move is taken from it: nothing is registered again, the executor is not asked, and the
        record is left pending.
        """
        self.swept()
        stage = self.assertSwept()

        def swap(record: dict) -> None:
            mine = [e for e in record["effects"] if e["stage"] == stage]
            at = record["effects"].index(mine[0])
            for effect in mine:
                record["effects"].remove(effect)
            for offset, effect in enumerate(reversed(mine)):
                record["effects"].insert(at + offset, effect)

        self.edit_record(swap)
        self.assertShowsNoMove(self.starting(self.script()), "reconcile_required")

    def test_more_than_the_one_commit_a_cycle_can_hold_is_not_passed_over(self) -> None:
        """C: a cycle records one such commit - once it is made nothing of the registration is left uncommitted for a
        later replay to carry. A record holding two of them there is not that shape and shows no move."""
        self.swept()
        stage = self.assertSwept()
        prefix, number = stage.split(":")
        twin = f"{prefix}:{int(number) + 1}"

        def duplicate(record: dict) -> None:
            mine = [e for e in record["effects"] if e["stage"] == stage]
            at = record["effects"].index(mine[-1]) + 1
            top = max(e["seq"] for e in record["effects"])
            for offset, effect in enumerate(mine, start=1):
                record["effects"].insert(at + offset - 1, {**effect, "stage": twin, "seq": top + offset})

        self.edit_record(duplicate)
        self.assertShowsNoMove(self.starting(self.script()), "dependency_unsatisfied")


# --------------------------------------------------------------------------- D: the move is still shown exactly
class MoveIdentityTests(SweepCase):
    def test_the_removal_must_be_the_moving_work_s_own(self) -> None:
        """D: the removal is proven as this move's: its Work, its event shape, under the ID reserved for it."""
        def another_work(record, effect):
            effect["payload"]["record"]["entity"] = self.i1

        def another_event_id(record, effect):
            effect["payload"]["record"]["id"] = new_id("event")

        def another_payload_key(record, effect):
            effect["payload"]["extra"] = "something"

        for label, change in (
            ("of another Work", another_work),
            ("under an ID the move did not reserve", another_event_id),
            ("carrying something beside the event", another_payload_key),
        ):
            with self.subTest(removal=label):
                self.setUp()
                self.swept()
                _, _, removal = self.shape()
                self.tamper(removal, change)
                self.assertNotReplayed(self.starting(self.script()))

    def test_the_removal_must_be_the_move_s_own_next_lifecycle_stage(self) -> None:
        """D: the removal is the Work's *next* lifecycle stage after the registration, not any lifecycle stage of it.

        Renamed to a later number - its events and the IDs reserved for them moved with it, so the record is
        consistent and replays - it is no longer the stage this move records, and no move is shown.
        """
        self.swept()
        _, _, removal = self.shape()
        prefix, number = removal.rsplit(":", 1)
        renamed = f"{prefix}:{int(number) + 6}"

        def rename(record: dict) -> None:
            for effect in record["effects"]:
                if effect["stage"] == removal:
                    effect["stage"] = renamed
            reserved = record["reserved_ids"]
            for key in list(reserved):
                if key.startswith(removal + ":"):
                    reserved[renamed + key[len(removal):]] = reserved.pop(key)

        self.edit_record(rename)
        self.assertShowsNoMove(self.starting(self.script()), "dependency_unsatisfied")

    def test_the_commit_carrying_the_move_must_hold_the_message_it_was_decided_on(self) -> None:
        """D: BL-048 - the recorded commit is the move's only with the finalization that move decided."""
        self.swept(then=after_the_move_commit_is_recorded)
        (pending,) = self.pending()
        stage = next(
            e["stage"] for e in pending["effects"]
            if e["kind"] == "git_commit" and _finalizes_a_move(e["payload"].get("message"))
        )
        self.tamper(stage, lambda record, effect: effect["payload"].update({"message": "chore(workline): something"})
                    if effect["kind"] == "git_commit" else None)
        self.assertNotReplayed(self.starting(self.script()))

    def test_the_move_commit_carries_the_display_the_move_was_decided_on(self) -> None:
        """D: BL-048 - a display a person changed after the move was decided is not what the retry commits."""
        self.swept()
        decided = self.display(self.w1)
        path = self.root / ProjectView.load(self.store).works[self.w1].path
        path.write_text(re.sub(r"(?m)^display: .*$", "display: W-99", path.read_text(encoding="utf-8"), count=1),
                        encoding="utf-8")
        git(self.root, "add", path.relative_to(self.root).as_posix())
        git(self.root, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "person: renumber W1")
        self.assertEqual(self.starting(self.script())().status, "moved")
        self.assertEqual(self.subjects()[0], f"chore(workline): branch from {decided}")

    def test_a_record_that_cannot_show_its_derivations_shows_no_move(self) -> None:
        """D: BL-046 comes first - a record that says nothing about its derivations is not read as a move."""
        for label, change in (
            ("no derivations kept", lambda notes: notes.pop(st._DERIVATIONS)),
            ("derivations incomplete", lambda notes: notes[st._DERIVATIONS].update({"complete": False})),
        ):
            with self.subTest(record=label):
                self.setUp()
                self.swept()
                self.edit_record(lambda record: change(record["notes"]))
                run = self.starting(self.script())
                self.assertShowsNoMove(run, "dependency_unsatisfied")
                self.assertShowsNoMove(run, "dependency_unsatisfied")  # and on every retry after it

    def test_a_registration_this_start_cannot_show_as_its_own_shows_no_move(self) -> None:
        """D: BL-046 / BL-036 come first - the registration must be this START's own, carrying the branch it was
        decided on, before the move is read from the record at all."""
        self.swept()
        registration, _, _ = self.shape()
        self.tamper(registration, lambda record, effect: effect.pop(st._DECIDED_ON, None))
        self.assertNotReplayed(self.starting(self.script()))


# --------------------------------------------------------------------------- E: the contracts around it
class ContractTests(SweepCase):
    def test_a_resume_off_the_branch_the_move_was_decided_on_is_refused_first(self) -> None:
        """E: BL-036 / BL-038 - no proof, no replay, no executor, no commit, no push on another branch."""
        self.swept()
        git(self.root, "checkout", "-q", "-b", "elsewhere")
        ran, head, remote, stages = list(self.ran), self.head(), self.remote_head(), self.stage_names()
        with self.assertRaises(ReconcileRequired):
            self.starting(self.script())()
        self.assertEqual((self.ran, self.stage_names()), (ran, stages))
        self.assertEqual((self.head(), self.remote_head()), (head, remote))
        git(self.root, "checkout", "-q", "main")
        self.assertEqual(self.starting(self.script())().status, "moved")
        self.assertEqual(self.outcome()["pending"], [])

    def test_the_recorded_push_publishes_only_the_commit_the_move_made(self) -> None:
        """E: BL-050 - a person's commit stacked on the branch is not what the move's recorded push sends."""
        self.swept(then=before_the_move_commit_is_pushed)
        mine = self.head()
        (self.root / "person.txt").write_text("person\n", encoding="utf-8")
        git(self.root, "add", "person.txt")
        git(self.root, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "person: unrelated")
        self.assertEqual(self.starting(self.script())().status, "moved")
        self.assertEqual(self.remote_head(), mine)
        self.assertNotEqual(self.head(), mine)

    def test_a_person_s_change_to_an_owned_path_is_neither_committed_nor_erased(self) -> None:
        """E: BL-043 - the commit carrying the move refuses the person's bytes; they stay, nothing is published."""
        self.swept()
        path = self.root / f"{WORKLINE_DIR}/relations/roadmap.yaml"
        original = path.read_bytes()
        path.write_bytes(original + b"# person's note\n")
        head, remote = self.head(), self.remote_head()
        with self.assertRaises(ReconcileRequired) as refused:
            self.starting(self.script())()
        self.assertIn("cannot show the change it would commit is its own", str(refused.exception))
        self.assertEqual(path.read_bytes(), original + b"# person's note\n")
        self.assertEqual((self.head(), self.remote_head()), (head, remote))
        path.write_bytes(original)
        self.assertEqual(self.starting(self.script())().status, "moved")
        self.assertEqual(self.outcome()["pending"], [])

    def test_the_work_does_not_complete_while_the_cycle_s_dependency_is_unfinished(self) -> None:
        """E: BL-049 / BL-051 - the relations the cycle registered stay, and the move ending does not satisfy them."""
        self.swept()
        self.assertEqual(self.starting(self.script())().status, "moved")
        self.assertIn(("requires_completion", "Other", "W1"), self.relations())
        self.assertIn(("requires_completion", "Mid", "W1"), self.relations())
        self.assertEqual(self.state(), ("in_progress", False))


if __name__ == "__main__":
    unittest.main()
