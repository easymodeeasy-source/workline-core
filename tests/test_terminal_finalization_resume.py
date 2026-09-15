"""START finishes the terminal finalization it recorded before it reports anything else (BL-031).

A Work's completion is finalized inside one START mutation: the result commit,
the ``work_target_removed`` / ``work_completed`` events, the commit that carries
those events, and the push (``skills/start``: Terminal finalization). A cancel is
finalized the same way, by the commit that carries its events and its replan.

When START was interrupted after the terminal events were recorded but before
the commit that carries them was recorded, running the same START again read
only the current state. That state already showed the Work completed or
cancelled, so a single-work retry reported ``completed``, and an outer retry
chose the next Work - or found none and reported ``stopped`` or
``phase_complete``. Either way the mutation was closed: the events stayed
uncommitted and unpushed, or were folded into the next Work's commit, the only
record that could have finished them was gone, and the next START that had to
commit the event log stopped on it as a pre-existing change.

A resumed START now reads its record first. A completion it recorded and applied
is carried through exactly its Git stage - the executor is not asked again, no
event is added, no other Work runs first - and only then does START report, or
go on in outer mode. A cancel is carried on from the decision it recorded with
its events (BL-030, ``test_cancel_decision_resume``) and ends the START as it
would have uninterrupted: ``cancelled``, with nothing chosen or run after it.
"""

from __future__ import annotations

import re
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git
from workline import start as st
from workline import yamlish
from workline.create import RelationSpec, WorkSpec, create_standalone_work
from workline.errors import StopError
from workline.ids import new_id
from workline.mutation import Mutation, MutationController, utc_now
from workline.ops import Replan
from workline.state import ProjectView
from workline.validate import validate_project

EVENT_LOG = ".workline/events/events.jsonl"


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


def around_push(pattern: str, *, pushed: bool):
    """Stop just before (``pushed=False``) or just after the push of a stage matching ``pattern``."""
    real = MutationController.apply_effect

    def fire(controller, record):
        ours = record["kind"] == "git_push" and re.search(pattern, record["stage"])
        if ours and not pushed:
            raise Interrupted("committed, not pushed")
        result = real(controller, record)
        if ours and pushed:
            raise Interrupted("pushed")
        return result

    return mock.patch.object(MutationController, "apply_effect", fire)


def completion_windows(work_id: str) -> dict:
    """The windows of one Work's terminal finalization, from its completion events on."""
    lifecycle, finalize = rf"^{work_id}:lifecycle:1$", rf"^{work_id}:finalize:0$"
    return {
        "completion recorded": lambda: after_recording(lifecycle),
        "completion applied": lambda: after_applying(lifecycle),
        "finalize recorded": lambda: after_recording(finalize),
        "committed": lambda: around_push(finalize, pushed=False),
        "pushed": lambda: around_push(finalize, pushed=True),
    }


# What a single-work retry still has to do from each window - and so everything it must not do again.
STILL_TO_RUN = {
    "completion recorded": ["append_event", "append_event", "git_commit", "git_push"],
    "completion applied": ["git_commit", "git_push"],
    "finalize recorded": ["git_commit", "git_push"],
    "committed": ["git_push"],
    "pushed": [],
}

# The windows in which the commit carrying the terminal events has not been recorded yet.
UNFINISHED = ("completion recorded", "completion applied")


def cancel_windows(work_id: str) -> dict:
    lifecycle = rf"^{work_id}:lifecycle:1$"
    return {
        "cancel recorded": lambda: after_recording(lifecycle),
        "cancel applied": lambda: after_applying(lifecycle),
        "commit recorded": lambda: after_recording(r"^commit:\d+$"),
    }


class FinalizationCase(WorklineTestCase):
    def build(self, name: str = "proj") -> None:
        self.name = name
        self.store = self.new_project(name, remote=True)
        self.ran: list[str] = []

    def setUp(self) -> None:
        super().setUp()
        self.build()

    # fixtures ---------------------------------------------------------------
    def phase(self, works=None, **kwargs):
        roadmap = self.simple_roadmap(self.store)
        return self.simple_entry(self.store, roadmap.phase_ids["a"], works, **kwargs)

    def standalone_chain(self, *names: str) -> list[str]:
        """Standalone Works, each ``planned_next`` after the one before it."""
        ids = [create_standalone_work(self.store, WorkSpec(name, name.lower())).work_id for name in names]
        if len(ids) > 1:
            helper = create_standalone_work(self.store, WorkSpec("Helper", "helper")).work_id
            relations = tuple(RelationSpec("planned_next", a, b) for a, b in zip(ids, ids[1:]))
            st.plan_exclude_standalone_work(self.store, helper, Replan(add_relations=relations))
        return ids

    def executor(self, outcomes: dict | None = None):
        """Completes every Work with a result file, except the Works given another outcome."""
        done = completing_executor(self.store, self.ran)
        outcomes = outcomes or {}

        def execute(ctx: st.ExecutionContext):
            if ctx.work.id not in outcomes:
                return done(ctx)
            self.ran.append(ctx.work.id)
            return outcomes[ctx.work.id]

        return execute

    # running ------------------------------------------------------------------
    def interrupt(self, window, call) -> dict:
        with window(), self.assertRaises(Interrupted):
            call()
        (pending,) = MutationController(self.store).list_pending()
        return pending

    def watching(self, call, executed: list[str]):
        """Run ``call``, recording the kind of every effect it actually executes."""
        real = MutationController.apply_effect

        def watch(controller, record):
            executed.append(record["kind"])
            return real(controller, record)

        with mock.patch.object(MutationController, "apply_effect", watch):
            return call()

    # observation --------------------------------------------------------------
    def display(self, work_id: str) -> str:
        return ProjectView.load(self.store).works[work_id].display

    def subjects(self) -> list[str]:
        return git(self.store.root, "log", "--format=%s").splitlines()

    def head(self) -> str:
        return git(self.store.root, "rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return git(self.remote_path(self.name), "rev-parse", "main").strip()

    def dirty(self) -> list[str]:
        status = git(self.store.root, "status", "--porcelain", "--untracked-files=all").splitlines()
        return [line for line in status if ".workline/runtime/" not in line]

    def record_bytes(self) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))}

    def snapshot(self) -> dict:
        """Everything a refused retry must leave exactly as it was."""
        return {
            "records": self.record_bytes(),
            "events": self.store.events_jsonl.read_bytes(),
            "head": self.head(),
            "remote": self.remote_head(),
        }

    def events(self, work_id: str, event_type: str) -> list[str]:
        return [e.id for e in ProjectView.load(self.store).events if e.entity == work_id and e.type == event_type]

    def introduced_by(self, work_id: str, event_type: str) -> list[str]:
        """For each such event in the log, the subject of the commit that brought it into the event log."""
        found = []
        for event_id in self.events(work_id, event_type):
            subjects = git(self.store.root, "log", "--format=%s", "-S", event_id, "--", EVENT_LOG).splitlines()
            found.append(subjects[-1] if subjects else "uncommitted")
        return found

    def edit_record(self, pending: dict, change) -> None:
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        change(record)
        path.write_text(yamlish.dump(record), encoding="utf-8")

    def assertFinalized(self, work_id: str) -> None:
        """The completion was carried by the Work's own finalization commit, once, and it was pushed."""
        subject = f"chore(workline): complete {self.display(work_id)}"
        self.assertEqual(self.introduced_by(work_id, "work_completed"), [subject])
        self.assertEqual(self.subjects().count(subject), 1)
        self.assertEqual(self.head(), self.remote_head())

    def assertNothingLeftOver(self) -> None:
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(self.dirty(), [])
        self.assertEqual(validate_project(self.store), [])

    def assertStoppedUntouched(self, pending: dict, call) -> StopError:
        """The retry STOPs having executed nothing, run no executor and changed nothing at all."""
        before, ran, executed = self.snapshot(), list(self.ran), []
        with self.assertRaises(StopError) as stopped:
            self.watching(call, executed)
        self.assertEqual(stopped.exception.code, "reconcile_required")
        self.assertEqual(executed, [])
        self.assertEqual(self.ran, ran)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual([p["mutation_id"] for p in MutationController(self.store).list_pending()], [pending["mutation_id"]])
        return stopped.exception


# --------------------------------------------------------------------------- single-work completion
class SingleWorkCompletionTests(FinalizationCase):
    def test_every_window_resumes_only_what_is_left_of_the_finalization(self) -> None:
        for index, window in enumerate(STILL_TO_RUN):
            with self.subTest(window=window):
                self.build(f"single-{index}")
                w1 = self.phase().work_ids["w1"]
                call = lambda: st.start(self.store, w1, "single-work", self.executor())  # noqa: E731
                pending = self.interrupt(completion_windows(w1)[window], call)
                self.assertEqual(self.ran, [w1])

                executed: list[str] = []
                result = self.watching(call, executed)

                self.assertEqual((result.status, result.mutation_id), ("completed", pending["mutation_id"]))
                self.assertEqual(executed, STILL_TO_RUN[window])  # nothing applied twice
                self.assertEqual(self.ran, [w1])  # the executor was not asked again
                self.assertEqual(len(self.events(w1, "work_completed")), 1)
                self.assertFinalized(w1)
                self.assertNothingLeftOver()
                (record,) = [r for r in MutationController(self.store).list_records() if r["mutation_id"] == pending["mutation_id"]]
                self.assertEqual(record["status"], "completed")
                self.assertEqual(record["reserved_ids"], pending["reserved_ids"])  # nothing new reserved

    def test_the_retry_reports_the_completion_it_finalized(self) -> None:
        w1 = self.phase().work_ids["w1"]
        call = lambda: st.start(self.store, w1, "single-work", self.executor())  # noqa: E731
        self.interrupt(completion_windows(w1)["completion applied"], call)

        result = call()

        self.assertEqual(result.completed_work_ids, (w1,))
        self.assertEqual(result.head, self.head())

    def test_the_next_start_that_commits_the_event_log_is_not_held_up(self) -> None:
        entry = self.phase()
        w1 = entry.work_ids["w1"]
        call = lambda: st.start(self.store, w1, "single-work", self.executor())  # noqa: E731
        self.interrupt(completion_windows(w1)["completion applied"], call)
        call()

        result = st.start(self.store, entry.integration_id, "single-work", self.executor())

        self.assertEqual(result.status, "completed")
        self.assertFinalized(entry.integration_id)
        self.assertNothingLeftOver()

    def test_a_finalization_stopped_before_it_was_recorded_is_not_reported_as_a_completion(self) -> None:
        """No interruption needed: a pre-existing change to the event log stops the finalization commit."""
        w1 = self.phase().work_ids["w1"]
        with open(self.store.events_jsonl, "a", encoding="utf-8", newline="\n") as log:
            log.write("\n")
        call = lambda: st.start(self.store, w1, "single-work", self.executor())  # noqa: E731
        with self.assertRaises(StopError) as first:
            call()
        self.assertEqual(first.exception.code, "dirty_overlap")
        (pending,) = MutationController(self.store).list_pending()
        before = self.snapshot()

        with self.assertRaises(StopError) as retried:
            call()

        self.assertEqual(retried.exception.code, "dirty_overlap")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual([p["mutation_id"] for p in MutationController(self.store).list_pending()], [pending["mutation_id"]])
        self.assertEqual(self.introduced_by(w1, "work_completed"), ["uncommitted"])
        self.assertEqual(self.ran, [w1])


# --------------------------------------------------------------------------- outer continuation
class OuterContinuationTests(FinalizationCase):
    def test_the_interrupted_work_is_finalized_before_the_next_one_runs(self) -> None:
        for index, window in enumerate(UNFINISHED):
            with self.subTest(window=window):
                self.build(f"outer-{index}")
                entry = self.phase({"w1": "one", "w2": "two"}, planned_next=(("w1", "w2"),))
                w1, w2, integration = entry.work_ids["w1"], entry.work_ids["w2"], entry.integration_id
                call = lambda: st.start(self.store, w1, "outer", self.executor())  # noqa: E731
                pending = self.interrupt(completion_windows(w1)[window], call)

                result = call()

                self.assertEqual((result.status, result.mutation_id), ("phase_complete", pending["mutation_id"]))
                self.assertEqual(self.ran, [w1, w2, integration])  # w1 was not run again
                self.assertEqual(result.completed_work_ids, (w1, w2, integration))
                for work_id in (w1, w2, integration):
                    self.assertFinalized(work_id)
                # w1's own finalization is made before anything of w2 is committed
                history = self.subjects()[::-1]
                self.assertLess(history.index(f"chore(workline): complete {self.display(w1)}"),
                                history.index(f"chore(workline): {self.display(w2)} W2"))
                self.assertNothingLeftOver()

    def test_the_second_work_is_finalized_before_the_integration_runs(self) -> None:
        entry = self.phase({"w1": "one", "w2": "two"}, planned_next=(("w1", "w2"),))
        w1, w2, integration = entry.work_ids["w1"], entry.work_ids["w2"], entry.integration_id
        call = lambda: st.start(self.store, w1, "outer", self.executor())  # noqa: E731
        self.interrupt(completion_windows(w2)["completion applied"], call)

        result = call()

        self.assertEqual(result.status, "phase_complete")
        self.assertEqual(self.ran, [w1, w2, integration])
        for work_id in (w1, w2, integration):
            self.assertFinalized(work_id)
        self.assertNothingLeftOver()

    def test_the_last_work_is_finalized_before_the_phase_is_reported_complete(self) -> None:
        entry = self.phase()
        w1, integration = entry.work_ids["w1"], entry.integration_id
        call = lambda: st.start(self.store, w1, "outer", self.executor())  # noqa: E731
        self.interrupt(completion_windows(integration)["completion applied"], call)

        result = call()

        self.assertEqual(result.status, "phase_complete")
        self.assertEqual(self.ran, [w1, integration])
        self.assertFinalized(integration)
        self.assertNothingLeftOver()

    def test_a_standalone_scope_with_nothing_next_stops_only_after_the_finalization(self) -> None:
        (s1,) = self.standalone_chain("S1")
        call = lambda: st.start(self.store, s1, "outer", self.executor())  # noqa: E731
        self.interrupt(completion_windows(s1)["completion applied"], call)

        result = call()

        self.assertEqual((result.status, result.detail), ("stopped", "no startable Work in standalone scope"))
        self.assertEqual(self.ran, [s1])
        self.assertFinalized(s1)
        self.assertNothingLeftOver()

    def test_a_standalone_next_work_runs_only_after_the_finalization(self) -> None:
        s1, s2 = self.standalone_chain("S1", "S2")
        call = lambda: st.start(self.store, s1, "outer", self.executor())  # noqa: E731
        self.interrupt(completion_windows(s1)["completion recorded"], call)

        result = call()

        self.assertEqual(result.status, "stopped")
        self.assertEqual(self.ran, [s1, s2])
        self.assertFinalized(s1)
        self.assertFinalized(s2)
        self.assertNothingLeftOver()

    def test_equally_planned_next_works_stop_only_after_the_finalization(self) -> None:
        entry = self.phase({"w1": "one", "w2": "two", "w3": "three"}, entry="w1")
        w1 = entry.work_ids["w1"]
        call = lambda: st.start(self.store, w1, "outer", self.executor())  # noqa: E731
        self.interrupt(completion_windows(w1)["completion applied"], call)

        result = call()

        self.assertEqual(result.status, "stopped")
        self.assertIn("equally planned", result.detail)
        self.assertEqual(self.ran, [w1])
        self.assertFinalized(w1)
        self.assertNothingLeftOver()


# --------------------------------------------------------------------------- cancel
class UnfinishedCancelTests(FinalizationCase):
    """A cancel recorded without its commit is finished from its recorded decision, and nothing runs after it (BL-030)."""

    def assertCancelled(self, work_id: str) -> None:
        """The cancel was carried by its own commit, once, and pushed."""
        subject = f"chore(workline): cancel {self.display(work_id)}"
        self.assertEqual(self.introduced_by(work_id, "work_cancelled"), [subject])
        self.assertEqual(self.subjects().count(subject), 1)
        self.assertEqual(self.head(), self.remote_head())

    def test_an_outer_start_finishes_the_cancel_and_goes_no_further(self) -> None:
        cases = {
            "nothing next": ("S1", "S2"),
            "a next work": ("S1", "S2", "S3"),
        }
        for index, ((label, names), window) in enumerate((c, w) for c in cases.items() for w in ("cancel recorded", "cancel applied")):
            with self.subTest(case=label, window=window):
                self.build(f"cancel-{index}")
                ids = self.standalone_chain(*names)
                s1, s2 = ids[0], ids[1]
                call = lambda: st.start(self.store, s1, "outer", self.executor({s2: st.Cancel(Replan(), "not needed")}))  # noqa: E731,B023
                pending = self.interrupt(cancel_windows(s2)[window], call)

                result = call()

                self.assertEqual((result.status, result.work_id, result.detail, result.mutation_id),
                                 ("cancelled", s2, "not needed", pending["mutation_id"]))
                self.assertEqual(self.ran, [s1, s2])  # S2 was not asked again, and no next Work ran
                self.assertTrue(all(ProjectView.load(self.store).work_state(other).state == "unstarted" for other in ids[2:]))
                self.assertCancelled(s2)
                self.assertNothingLeftOver()

    def test_an_outer_start_finishes_its_own_entry_works_cancel(self) -> None:
        (s1,) = self.standalone_chain("S1")
        call = lambda: st.start(self.store, s1, "outer", self.executor({s1: st.Cancel(Replan(), "not needed")}))  # noqa: E731
        pending = self.interrupt(cancel_windows(s1)["cancel applied"], call)

        result = call()

        self.assertEqual((result.status, result.work_id, result.mutation_id), ("cancelled", s1, pending["mutation_id"]))
        self.assertCancelled(s1)
        self.assertNothingLeftOver()

    def test_an_outer_start_finishes_the_cancel_before_anything_else_once_its_replan_is_applied(self) -> None:
        """The structure is valid again, and a Work is startable - it still does not run after the cancel."""
        entry = self.phase({"w1": "one", "w2": "two"}, planned_next=(("w1", "w2"),))
        w1, w2, integration = entry.work_ids["w1"], entry.work_ids["w2"], entry.integration_id
        (dependency,) = [r.id for r in ProjectView.load(self.store).roadmap_relations
                         if (r.type, r.from_id, r.to) == ("requires_completion", w2, integration)]
        cancel = st.Cancel(Replan(remove_relation_ids=(dependency,)), "not needed")
        call = lambda: st.start(self.store, w1, "outer", self.executor({w2: cancel}))  # noqa: E731
        pending = self.interrupt(lambda: after_applying(rf"^{w2}:cancel:\d+:remove$"), call)
        self.assertEqual(validate_project(self.store), [])

        result = call()

        self.assertEqual((result.status, result.work_id, result.mutation_id), ("cancelled", w2, pending["mutation_id"]))
        self.assertEqual(self.ran, [w1, w2])  # the integration did not run
        self.assertEqual(ProjectView.load(self.store).work_state(integration).state, "unstarted")
        self.assertCancelled(w2)
        self.assertNothingLeftOver()

    def test_a_single_work_start_finishes_the_cancel_of_its_work(self) -> None:
        for index, window in enumerate(("cancel recorded", "cancel applied")):
            with self.subTest(window=window):
                self.build(f"single-cancel-{index}")
                (s1,) = self.standalone_chain("S1")
                call = lambda: st.start(self.store, s1, "single-work", self.executor({s1: st.Cancel(Replan(), "not needed")}))  # noqa: E731,B023
                pending = self.interrupt(cancel_windows(s1)[window], call)

                result = call()

                self.assertEqual((result.status, result.detail, result.mutation_id), ("cancelled", "not needed", pending["mutation_id"]))
                self.assertEqual(self.ran, [s1])
                self.assertCancelled(s1)
                self.assertNothingLeftOver()

    def test_a_cancel_whose_commit_was_recorded_ends_the_start_once_replayed(self) -> None:
        """Not a new STOP: once the commit is recorded, resuming replays it like any other effect, and the START ends there."""
        s1, s2 = self.standalone_chain("S1", "S2")
        call = lambda: st.start(self.store, s1, "outer", self.executor({s2: st.Cancel(Replan(), "not needed")}))  # noqa: E731
        pending = self.interrupt(cancel_windows(s2)["commit recorded"], call)

        executed: list[str] = []
        result = self.watching(call, executed)

        self.assertEqual((result.status, result.work_id, result.detail, result.mutation_id),
                         ("cancelled", s2, "not needed", pending["mutation_id"]))
        self.assertEqual(executed, ["git_commit", "git_push"])
        self.assertCancelled(s2)
        self.assertNothingLeftOver()


# --------------------------------------------------------------------------- what the record has to prove
class RecordProofTests(FinalizationCase):
    """Only a completion the record shows to be this START's own is finished; nothing else is taken on trust."""

    def interrupted_single_work(self):
        entry = self.phase({"w1": "one", "w2": "two"}, entry="w1")
        w1 = entry.work_ids["w1"]
        call = lambda: st.start(self.store, w1, "single-work", self.executor())  # noqa: E731
        pending = self.interrupt(completion_windows(w1)["completion applied"], call)
        return entry, call, pending

    def test_events_someone_else_committed_are_not_reported_as_finalized(self) -> None:
        entry, call, pending = self.interrupted_single_work()
        git(self.store.root, "add", "--", EVENT_LOG)
        git(self.store.root, "commit", "-m", "someone committed the event log")

        refused = self.assertStoppedUntouched(pending, call)

        self.assertIn("a commit it did not record already holds those events", refused.message)
        self.assertNotEqual(self.head(), self.remote_head())  # nothing was pushed on its behalf

    def test_a_single_work_record_finishes_only_the_invoked_work(self) -> None:
        entry, _, pending = self.interrupted_single_work()
        w2 = entry.work_ids["w2"]
        self.edit_record(pending, lambda record: record["invocation"].update(work_id=w2))
        call = lambda: st.start(self.store, w2, "single-work", self.executor())  # noqa: E731

        self.assertStoppedUntouched(pending, call)

    def test_a_completion_that_is_not_the_last_stage_recorded_is_not_finished(self) -> None:
        entry, call, pending = self.interrupted_single_work()
        w2 = entry.work_ids["w2"]

        def later_stage(record):
            record["effects"].append({
                "seq": len(record["effects"]) + 1, "stage": f"{w2}:lifecycle:0", "kind": "append_event", "applied": False,
                "payload": {"record": {"id": new_id("event"), "type": "work_started", "entity": w2, "at": utc_now()}},
            })

        self.edit_record(pending, later_stage)

        self.assertStoppedUntouched(pending, call)

    def test_a_completion_under_ids_it_did_not_reserve_is_not_finished(self) -> None:
        entry, call, pending = self.interrupted_single_work()
        w1 = entry.work_ids["w1"]
        self.edit_record(pending, lambda record: record["reserved_ids"].update({f"{w1}:lifecycle:1:event:1": new_id("event")}))

        self.assertStoppedUntouched(pending, call)

    def test_two_unfinished_terminal_works_are_not_finished(self) -> None:
        entry = self.phase({"w1": "one", "w2": "two"}, planned_next=(("w1", "w2"),))
        w1, w2 = entry.work_ids["w1"], entry.work_ids["w2"]
        call = lambda: st.start(self.store, w1, "outer", self.executor())  # noqa: E731
        pending = self.interrupt(completion_windows(w2)["completion applied"], call)

        def unfinished_w1(record):
            record["effects"] = [effect for effect in record["effects"] if effect["stage"] != f"{w1}:finalize:0"]

        self.edit_record(pending, unfinished_w1)
        refused = self.assertStoppedUntouched(pending, call)

        self.assertIn(w1, refused.message)
        self.assertIn(w2, refused.message)


# --------------------------------------------------------------------------- unchanged
class UnchangedWindowTests(FinalizationCase):
    def test_a_start_interrupted_before_its_completion_was_recorded_asks_the_executor_again(self) -> None:
        """Before the terminal events are recorded nothing is finalized yet: the Work runs again, as before."""
        w1 = self.phase().work_ids["w1"]
        call = lambda: st.start(self.store, w1, "single-work", self.executor())  # noqa: E731
        pending = self.interrupt(lambda: after_recording(rf"^{w1}:results:0$"), call)

        result = call()

        self.assertEqual((result.status, result.mutation_id), ("completed", pending["mutation_id"]))
        self.assertEqual(self.ran, [w1, w1])
        self.assertFinalized(w1)
        self.assertNothingLeftOver()


if __name__ == "__main__":
    unittest.main()
