"""START finishes a hold it recorded instead of deciding it again (BL-044).

A hold is the executor's decision, and START records it as two lifecycle events
(``work_target_removed`` / ``work_held``) and the commit that carries them. Those
events are not terminal: a held Work is one a later START legitimately resumes.
So a retry of an interrupted hold read only the current state, saw a held Work,
and resumed the very hold this mutation had just recorded - it appended
``work_resumed`` / ``work_target_added``, asked the executor again, recorded
whatever came back as a new decision, and named every stage afresh, so the only
duplicate guard there is (a stage recorded twice) never fired.

A hold whose push had failed therefore committed and pushed a resume/hold cycle
that never happened, and a record stuck before BL-041 grew four effects, two
stages, four events and one executor call on every retry, without bound, while
blocking every other operation that writes the same ledgers.

A resumed START now reads its record for a hold as it already reads it for a
completion (BL-031) and a cancel (BL-030). One it can show is its own - the next
lifecycle stage of that Work, exactly the two events a hold records, under the
IDs reserved for them, nothing recorded after it but its own commit, and those
events not already in HEAD through a commit it did not record - is carried
through exactly its Git stage: no executor, no event, no new stage, and nothing
chosen or run after it. The reason it was held for rides on the ``work_held``
effect, so the retry reports the same hold; a record written before START kept
one is finished just the same and reports it without a reason. Anything else is
``reconcile required`` with the record left exactly as it is - which is also what
a record stuck before BL-041 now does at its Git stage: the same ``dirty_overlap``
it always made, with nothing added.
"""

from __future__ import annotations

import json
import re
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git, scripted_executor
from workline import gitops
from workline import start as st
from workline import yamlish
from workline.create import WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, StopError
from workline.ids import new_id
from workline.mutation import Mutation, MutationController
from workline.state import ProjectView
from workline.store import WORKLINE_DIR
from workline.validate import validate_project

EVENT_LOG = f"{WORKLINE_DIR}/events/events.jsonl"
HOLD_EVENTS = ["work_started", "work_target_added", "work_target_removed", "work_held"]


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone."""


# --------------------------------------------------------------------------- interruption windows
def after_recording(pattern: str):
    """Stop right after a stage matching ``pattern`` is recorded, none of it applied."""
    real = Mutation.add_effects

    def fire(mutation, stage, effects):
        real(mutation, stage, effects)
        if re.search(pattern, stage):
            raise Interrupted(f"recorded {stage}")

    return mock.patch.object(Mutation, "add_effects", fire)


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
    """Stop with the hold's commit made and its push not made."""
    real = MutationController.apply_effect

    def fire(controller, record):
        if record["kind"] == "git_push":
            raise Interrupted("committed, not pushed")
        return real(controller, record)

    return mock.patch.object(MutationController, "apply_effect", fire)


# What is left to do from each window, and so everything the resume must not do again.
WINDOWS = {
    "hold recorded": lambda: after_recording(r":lifecycle:1$"),
    "hold applied": lambda: after_applying(r":lifecycle:1$"),
    "committed": before_pushing,
}
STILL_TO_RUN = {
    "hold recorded": ["append_event", "append_event", "git_commit", "git_push"],
    "hold applied": ["git_commit", "git_push"],
    "committed": ["git_push"],
}


# --------------------------------------------------------------------------- the implementation before this change
def before_bl041():
    """The implementation before BL-041, which left the pre-existing overlap to the Git stage alone."""
    return mock.patch.object(gitops, "ensure_separable_before_effects", lambda mutation, paths: None)


def before_the_reason_was_kept():
    """The implementation before this change, which recorded a hold's events without a decision at all.

    That is also what a record written before START kept the display the hold's
    commit message renders holds (BL-047), so a hold recorded this way is
    finished by the shape of its own finalization.
    """
    return mock.patch.object(st, "_hold_decision", lambda reason, display: None)


class HoldCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.root = self.store.root
        self.ran: list[str] = []
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B")})
        self.pa, self.pb = roadmap.phase_ids["a"], roadmap.phase_ids["b"]
        entry = self.simple_entry(self.store, self.pa, {"w1": "W1 done", "w2": "W2 done"}, entry="w1")
        self.w1, self.w2, self.i1 = entry.work_ids["w1"], entry.work_ids["w2"], entry.integration_id

    # the call under test ----------------------------------------------------
    def holding(self, reason: object = "later", work_id: str | None = None, mode: str = "single-work"):
        def executor(ctx: st.ExecutionContext):
            self.ran.append(ctx.work.id)
            return st.Hold(reason)

        return lambda: st.start(self.store, work_id or self.w1, mode, executor)

    def interrupt(self, window, call) -> dict:
        with window(), self.assertRaises(Interrupted):
            call()
        (pending,) = MutationController(self.store).list_pending()
        return pending

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
    def display(self, work_id: str) -> str:
        return ProjectView.load(self.store).works[work_id].display

    def events(self, work_id: str) -> list[str]:
        return [e.type for e in ProjectView.load(self.store).events if e.entity == work_id]

    def committed_events(self, work_id: str) -> list[str]:
        text = git(self.root, "show", f"HEAD:{EVENT_LOG}", check=False)
        lines = [json.loads(line) for line in text.splitlines() if line.strip()]
        return [e["type"] for e in lines if e["entity"] == work_id]

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
        """Everything a refused retry must leave exactly as it was: the records byte for byte, the Project, Git."""
        return {
            "records": {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))},
            "files": {p.relative_to(self.root).as_posix(): p.read_bytes()
                      for p in sorted((self.root / ".workline").rglob("*"))
                      if p.is_file() and "runtime" not in p.relative_to(self.root).parts},
            "head": self.head(),
            "remote": self.remote_head(),
            "dirty": self.dirty(),
        }

    def closing(self, call) -> tuple[object, list[dict]]:
        """Run ``call`` and keep each mutation's stages as it closes; a completed mutation drops its own record."""
        closed: list[dict] = []
        real = Mutation.complete

        def keep(mutation):
            closed.append({"stages": self.stage_names(mutation.record), "effects": len(mutation.effects)})
            return real(mutation)

        with mock.patch.object(Mutation, "complete", keep):
            return call(), closed

    def edit_record(self, pending: dict, change) -> None:
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        change(record)
        path.write_text(yamlish.dump(record), encoding="utf-8")

    @staticmethod
    def held_effect(record: dict) -> dict:
        (effect,) = [e for e in record["effects"] if e["kind"] == "append_event"
                     and e["payload"]["record"]["type"] == "work_held"]
        return effect

    # assertions -------------------------------------------------------------
    def assertHeldOnce(self, result, work_id: str, reason: object, *, ran: list[str]) -> None:
        """The hold as an uninterrupted one leaves it: its events once, its commit once, pushed, nothing pending."""
        self.assertEqual((result.status, result.work_id, result.detail), ("held", work_id, reason))
        self.assertEqual(self.events(work_id), HOLD_EVENTS)
        self.assertEqual(self.committed_events(work_id), HOLD_EVENTS)
        self.assertEqual(self.subjects().count(f"chore(workline): hold {self.display(work_id)}"), 1)
        self.assertEqual(self.ran, ran)
        self.assertEqual((self.head(), self.dirty()), (self.remote_head(), []))
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(validate_project(self.store), [])

    def assertUntouched(self, call, before: dict) -> ReconcileRequired:
        """Refused before anything is replayed, recorded or run, with the record and the Project as they were."""
        ran, executed, stages = list(self.ran), [], []
        with self.assertRaises(ReconcileRequired) as refused:
            self.watching(call, executed, stages)
        self.assertEqual((executed, stages, self.ran), ([], [], ran))
        self.assertEqual(self.snapshot(), before)
        return refused.exception


# --------------------------------------------------------------------------- a hold that stopped part-way
class RecordedHoldTests(HoldCase):
    def test_a_recorded_hold_is_finished_from_its_record(self) -> None:
        """From every window: only the Git stage is left, the executor is not asked, nothing is added."""
        for window, still in STILL_TO_RUN.items():
            with self.subTest(window=window):
                self.setUp()
                call = self.holding("later")
                pending = self.interrupt(WINDOWS[window], call)
                executed, stages = [], []

                result = self.watching(call, executed, stages)

                self.assertEqual(result.mutation_id, pending["mutation_id"])
                self.assertEqual(executed, still)  # only what was left; no event recorded twice
                self.assertEqual(stages, [] if window == "committed" else ["commit:0"])
                self.assertHeldOnce(result, self.w1, "later", ran=[self.w1])

    def test_the_record_of_a_finished_hold_holds_one_lifecycle_cycle(self) -> None:
        call = self.holding("later")
        pending = self.interrupt(WINDOWS["hold applied"], call)
        self.assertEqual(self.stage_names(pending), [f"{self.w1}:lifecycle:0", f"{self.w1}:lifecycle:1"])
        _, closed = self.closing(call)

        self.assertEqual(closed, [{
            "stages": [f"{self.w1}:lifecycle:0", f"{self.w1}:lifecycle:1", "commit:0"], "effects": 6,
        }])

    def test_an_outer_hold_ends_the_start_there(self) -> None:
        """A hold ends an outer START as it would have uninterrupted: no other Work is chosen or run after it."""
        call = self.holding("later", mode="outer")
        self.interrupt(WINDOWS["hold applied"], call)

        result = call()

        self.assertHeldOnce(result, self.w1, "later", ran=[self.w1])
        self.assertEqual(self.events(self.w2), [])

    def test_a_hold_recorded_after_a_question_wait_is_finished_from_its_record(self) -> None:
        """The executor asked, then held on the next call: the record's opening stage is not a decision."""
        answers = [st.QuestionWait("which way?"), st.Hold("later")]

        def executor(ctx: st.ExecutionContext):
            self.ran.append(ctx.work.id)
            return answers.pop(0) if len(answers) > 1 else answers[0]

        call = lambda: st.start(self.store, self.w1, "single-work", executor)  # noqa: E731
        self.assertEqual(call().status, "question_wait")
        self.interrupt(WINDOWS["hold applied"], call)

        result = call()

        self.assertHeldOnce(result, self.w1, "later", ran=[self.w1, self.w1])


# --------------------------------------------------------------------------- the reason it was held for
class ReasonTests(HoldCase):
    def test_the_reason_comes_back_from_the_record(self) -> None:
        call = self.holding("waiting for the vendor")
        self.interrupt(WINDOWS["hold recorded"], call)

        self.assertEqual(call().detail, "waiting for the vendor")

    def test_a_hold_recorded_without_a_reason_is_finished_and_reports_none(self) -> None:
        """A record written before START kept the reason: the events are the decision, and they are in the record."""
        call = self.holding("later")
        with before_the_reason_was_kept():
            pending = self.interrupt(WINDOWS["hold applied"], call)
        self.assertEqual(set(self.held_effect(pending)["payload"]), {"record"})

        result = call()

        self.assertHeldOnce(result, self.w1, None, ran=[self.w1])

    def test_a_reason_the_record_cannot_keep_holds_the_work_anyway(self) -> None:
        """The reason is START's word to its caller, not Project content: an unkeepable one is left out, not refused."""
        result = self.holding(3.5)()

        self.assertHeldOnce(result, self.w1, 3.5, ran=[self.w1])

    def test_a_reason_the_record_cannot_keep_is_left_out_and_finished_without_one(self) -> None:
        call = self.holding(3.5)
        pending = self.interrupt(WINDOWS["hold recorded"], call)
        self.assertEqual(set(self.held_effect(pending)["payload"]), {"record"})

        self.assertHeldOnce(call(), self.w1, None, ran=[self.w1])


# --------------------------------------------------------------------------- a push that really failed
class PushFailureTests(HoldCase):
    def test_a_hold_whose_push_failed_pushes_and_adds_nothing(self) -> None:
        """The ordinary way into the window: the approved destination is simply unreachable."""
        away = self.tmp / "proj-remote-away.git"
        call = self.holding("later")
        self.remote_path().rename(away)
        with self.assertRaises(StopError) as failed:
            call()
        self.assertEqual(failed.exception.code, "git_error")
        (pending,) = MutationController(self.store).list_pending()
        self.assertEqual(self.committed_events(self.w1), HOLD_EVENTS)
        away.rename(self.remote_path())  # the approved destination comes back unchanged
        commits = len(self.subjects())
        executed, stages = [], []

        result = self.watching(call, executed, stages)

        self.assertEqual(result.mutation_id, pending["mutation_id"])
        self.assertEqual((executed, stages), (["git_push"], []))  # only the push was left
        self.assertEqual(len(self.subjects()), commits)  # no second commit
        self.assertHeldOnce(result, self.w1, "later", ran=[self.w1])

    def test_the_project_is_no_longer_held_up_behind_the_record(self) -> None:
        away = self.tmp / "proj-remote-away.git"
        call = self.holding("later")
        self.remote_path().rename(away)
        with self.assertRaises(StopError):
            call()
        away.rename(self.remote_path())
        # Another Work of the same Phase shares the event log, so it waits for the hold ...
        with self.assertRaises(ReconcileRequired):
            st.start(self.store, self.w2, "single-work", completing_executor(self.store))

        self.assertEqual(call().status, "held")

        # ... and once the hold is finished it runs, with no cycle of the hold's own in between.
        self.assertEqual(st.start(self.store, self.w2, "single-work", completing_executor(self.store)).status, "completed")
        self.assertEqual(self.events(self.w1), HOLD_EVENTS)
        self.assertEqual(validate_project(self.store), [])


# --------------------------------------------------------------------------- records written before BL-041
class LegacyRecordTests(HoldCase):
    """A record stuck at its Git stage before BL-041: it still stops there, and a retry adds nothing."""

    def person_event(self) -> str:
        """A legal event a person appends to the event log and does not commit: Phase B held."""
        line = json.dumps(
            {"id": new_id("event"), "type": "phase_held", "entity": self.pb, "at": "2026-09-15T00:00:00+00:00"},
            separators=(",", ":"),
        ) + "\n"
        with open(self.root / EVENT_LOG, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
        return line

    def stuck(self, call) -> dict:
        """What the implementation before BL-041 left: the hold applied, then stopped at its Git stage."""
        with before_bl041(), before_the_reason_was_kept(), self.assertRaises(StopError) as stopped:
            call()
        self.assertEqual(stopped.exception.code, "dirty_overlap")
        (pending,) = MutationController(self.store).list_pending()
        self.assertEqual(len(pending["effects"]), 4)
        return pending

    def test_a_stuck_hold_stops_where_it_did_and_grows_nothing(self) -> None:
        self.person_event()
        call = self.holding("later")
        pending = self.stuck(call)
        self.assertEqual(self.ran, [self.w1])
        before, message = self.snapshot(), None
        counts = []

        for _ in range(4):
            executed, stages = [], []
            with self.assertRaises(StopError) as stopped:
                self.watching(call, executed, stages)
            self.assertEqual(stopped.exception.code, "dirty_overlap")
            message = message or stopped.exception.message
            self.assertEqual(stopped.exception.message, message)  # the same refusal, every time
            self.assertEqual((executed, stages), ([], []))
            counts.append(len(self.record_of(pending["mutation_id"])["effects"]))

        self.assertEqual(counts, [4, 4, 4, 4])
        self.assertEqual(self.ran, [self.w1])  # the executor is never asked again
        self.assertEqual(self.snapshot(), before)  # record bytes, event log, Git: nothing moved
        self.assertEqual([r["mutation_id"] for r in MutationController(self.store).list_pending()],
                         [pending["mutation_id"]])

    def test_the_stuck_record_is_not_repaired_when_the_person_commits(self) -> None:
        """BL-041's policy is unchanged: nothing about the record is guessed, and it is not repaired.

        Committing the change carries the hold's own events into HEAD with it, so the record can no longer show
        its own commit and push: the retry is ``reconcile required`` where it used to add another cycle and stop
        at ``dirty_overlap``. Either way the record stays exactly as it is, and now nothing grows.
        """
        self.person_event()
        call = self.holding("later")
        self.stuck(call)
        git(self.root, "add", "--", EVENT_LOG)
        git(self.root, "commit", "-q", "-m", "person: my own change", "--", EVENT_LOG)
        before = self.snapshot()

        with self.assertRaises(StopError) as stopped:
            call()

        self.assertEqual(stopped.exception.code, "reconcile_required")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.ran, [self.w1])

    def test_the_stuck_record_still_stops_when_the_person_discards_their_change(self) -> None:
        """Replay puts the hold's own events back, as it always did, and the Git stage stops on the frozen note."""
        line = self.person_event()
        call = self.holding("later")
        pending = self.stuck(call)
        raw = self.store.events_jsonl.read_bytes()
        self.store.events_jsonl.write_bytes(raw.replace(line.encode("utf-8"), b"", 1))

        for _ in range(3):
            with self.assertRaises(StopError) as stopped:
                call()
            self.assertEqual(stopped.exception.code, "dirty_overlap")

        self.assertEqual(len(self.record_of(pending["mutation_id"])["effects"]), 4)
        self.assertEqual(self.events(self.w1), HOLD_EVENTS)
        self.assertEqual(self.ran, [self.w1])


# --------------------------------------------------------------------------- what the record must show
class ProofTests(HoldCase):
    def held(self, window: str = "hold applied"):
        call = self.holding("later")
        return call, self.interrupt(WINDOWS[window], call)

    def test_a_hold_decision_in_another_form_is_refused(self) -> None:
        for change, what in (
            (lambda d: d.update(version=2), "another version"),
            (lambda d: d.update(extra="x"), "another field"),
            (lambda d: d.pop("reason"), "no reason"),
        ):
            with self.subTest(what=what):
                self.setUp()
                call, pending = self.held()
                self.edit_record(pending, lambda record: change(self.held_effect(record)["payload"]["hold"]))
                before = self.snapshot()

                self.assertIn("hold decision", str(self.assertUntouched(call, before)))

    def test_hold_events_under_other_ids_are_refused(self) -> None:
        call, pending = self.held("hold recorded")
        self.edit_record(pending, lambda record: record["reserved_ids"].update(
            {f"{self.w1}:lifecycle:1:event:1": new_id("event")}))
        before = self.snapshot()

        self.assertIn("IDs the hold did not reserve", str(self.assertUntouched(call, before)))

    def test_a_hold_stage_holding_another_event_is_refused(self) -> None:
        call, pending = self.held("hold recorded")

        def add_a_third(record: dict) -> None:
            held = self.held_effect(record)
            record["effects"].append({
                "seq": len(record["effects"]) + 1, "stage": held["stage"], "kind": "append_event", "applied": False,
                "payload": {"record": {"id": new_id("event"), "type": "work_resumed", "entity": self.w1,
                                       "at": "2026-09-15T00:00:00+00:00"}},
            })

        self.edit_record(pending, add_a_third)
        before = self.snapshot()

        self.assertIn("lifecycle events a hold records", str(self.assertUntouched(call, before)))

    def test_a_stage_recorded_after_the_hold_is_refused(self) -> None:
        call, pending = self.held()

        def add_a_stage(record: dict) -> None:
            record["effects"].append({
                "seq": len(record["effects"]) + 1, "stage": f"{self.w1}:lifecycle:2", "kind": "append_event",
                "applied": False,
                "payload": {"record": {"id": new_id("event"), "type": "work_resumed", "entity": self.w1,
                                       "at": "2026-09-15T00:00:00+00:00"}},
            })

        self.edit_record(pending, add_a_stage)
        before = self.snapshot()

        self.assertIn("after the hold stage", str(self.assertUntouched(call, before)))

    def test_two_holds_in_one_record_are_refused(self) -> None:
        call, pending = self.held()

        def hold_again(record: dict) -> None:
            held = self.held_effect(record)
            record["effects"].append({
                "seq": len(record["effects"]) + 1, "stage": f"{self.w2}:lifecycle:0", "kind": "append_event",
                "applied": False, "payload": dict(held["payload"], record=dict(held["payload"]["record"],
                                                                               id=new_id("event"), entity=self.w2)),
            })

        self.edit_record(pending, hold_again)
        before = self.snapshot()

        self.assertIn("more than one work_held", str(self.assertUntouched(call, before)))

    def test_a_hold_of_another_work_is_refused_where_this_start_runs_one_alone(self) -> None:
        call, pending = self.held()
        self.edit_record(pending, lambda record: self.held_effect(record)["payload"]["record"].update(entity=self.w2))
        before = self.snapshot()

        self.assertIn("single-work START runs", str(self.assertUntouched(call, before)))

    def test_a_hold_stage_named_otherwise_is_refused(self) -> None:
        call, pending = self.held("hold recorded")

        def rename(record: dict) -> None:
            stage, renamed = self.held_effect(record)["stage"], f"{self.w1}:lifecycle:7"
            for effect in record["effects"]:
                if effect["stage"] == stage:
                    effect["stage"] = renamed
            record["reserved_ids"] = {k.replace(stage, renamed): v for k, v in record["reserved_ids"].items()}

        self.edit_record(pending, rename)
        before = self.snapshot()

        self.assertIn("next lifecycle stage", str(self.assertUntouched(call, before)))

    def test_events_a_commit_this_mutation_did_not_record_already_holds_are_refused(self) -> None:
        """Its own commit and push could not be shown, so the hold is not finished from the record."""
        call, _ = self.held()
        git(self.root, "add", "--", EVENT_LOG)
        git(self.root, "commit", "-q", "-m", "person: my own change", "--", EVENT_LOG)
        before = self.snapshot()

        self.assertIn("already holds those events", str(self.assertUntouched(call, before)))


# --------------------------------------------------------------------------- what this must not change
class UnchangedTests(HoldCase):
    def test_an_uninterrupted_hold_is_unchanged(self) -> None:
        result, closed = self.closing(self.holding("later"))

        self.assertHeldOnce(result, self.w1, "later", ran=[self.w1])
        self.assertEqual(closed, [{
            "stages": [f"{self.w1}:lifecycle:0", f"{self.w1}:lifecycle:1", "commit:0"], "effects": 6,
        }])

    def test_a_held_work_is_started_again_by_a_later_start(self) -> None:
        """No record is pending, so this is the ordinary resume of a held Work, and it still runs."""
        self.assertEqual(self.holding("later")().status, "held")

        result = st.start(self.store, self.w1, "single-work", completing_executor(self.store, self.ran))

        self.assertEqual(result.status, "completed")
        self.assertEqual(self.events(self.w1), HOLD_EVENTS + [
            "work_resumed", "work_target_added", "work_target_removed", "work_completed"])
        self.assertEqual(self.ran, [self.w1, self.w1])

    def test_a_question_wait_still_re_runs_the_executor_on_its_own_record(self) -> None:
        """The opening lifecycle stage decides nothing, so a record holding only it is resumed as it always was."""
        attempts: list[int] = []

        def asks_then_completes(ctx: st.ExecutionContext):
            attempts.append(ctx.attempt)
            if len(attempts) == 1:
                return st.QuestionWait("which way?")
            return completing_executor(self.store, self.ran)(ctx)

        call = lambda: st.start(self.store, self.w1, "single-work", asks_then_completes)  # noqa: E731
        first = call()
        self.assertEqual(first.status, "question_wait")
        (pending,) = MutationController(self.store).list_pending()
        self.assertEqual(len(pending["effects"]), 2)

        result = call()

        self.assertEqual((result.status, result.mutation_id), ("completed", pending["mutation_id"]))
        self.assertEqual(attempts, [1, 1])

    def test_a_recorded_completion_is_still_finished_from_its_record(self) -> None:
        """BL-031 is untouched: the terminal finalization is read first and the hold readback never sees it."""
        call = lambda: st.start(self.store, self.w1, "single-work", completing_executor(self.store, self.ran))  # noqa: E731
        pending = self.interrupt(lambda: after_applying(r":lifecycle:1$"), call)

        result = call()

        self.assertEqual((result.status, result.mutation_id), ("completed", pending["mutation_id"]))
        self.assertEqual(self.ran, [self.w1])
        self.assertEqual(self.events(self.w1), ["work_started", "work_target_added", "work_target_removed", "work_completed"])

    def test_a_recorded_cancel_is_still_carried_from_its_decision(self) -> None:
        """BL-030 is untouched: a cancel is read before the mutation is opened and never reaches the hold readback."""
        s1 = create_standalone_work(self.store, WorkSpec("S1", "s1")).work_id
        call = lambda: st.start(  # noqa: E731
            self.store, s1, "single-work", scripted_executor({"*": [st.Cancel(reason="not needed")]}))
        pending = self.interrupt(lambda: after_applying(r":lifecycle:1$"), call)

        result = call()

        self.assertEqual((result.status, result.detail, result.mutation_id),
                         ("cancelled", "not needed", pending["mutation_id"]))
        self.assertEqual(self.events(s1), ["work_started", "work_target_added", "work_target_removed", "work_cancelled"])

    def test_a_pre_existing_change_still_refuses_a_hold_before_its_first_effect(self) -> None:
        """BL-041 is untouched: a trap sprung today leaves no record, no effect and no executor call."""
        line = json.dumps(
            {"id": new_id("event"), "type": "phase_held", "entity": self.pb, "at": "2026-09-15T00:00:00+00:00"},
            separators=(",", ":"),
        ) + "\n"
        with open(self.root / EVENT_LOG, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
        call = self.holding("later")

        for _ in range(3):
            with self.assertRaises(StopError) as stopped:
                call()
            self.assertEqual(stopped.exception.code, "dirty_overlap")

        self.assertEqual((self.ran, MutationController(self.store).list_pending()), ([], []))
        self.assertEqual(self.events(self.w1), [])


if __name__ == "__main__":
    unittest.main()
