"""A lifecycle operation carries its own interrupted mutation to the end (BL-025).

Holding, resuming or cancelling a Roadmap or a Phase, and recording a Roadmap's
achievement, each append one lifecycle event and then commit and push it. When
one is interrupted its recovery record stays pending, and running the same
operation again continues that mutation: what it recorded is classified, what
already happened is skipped, and only the rest is done (``rules/git``).

That stopped working as soon as the event itself had been applied. Each of these
operations checks its precondition - a Phase to hold must be active, a Roadmap to
resume must be held - and it read that off the current state before the
unfinished mutation was looked at. The current state already held the
operation's own event, so the retry of an interrupted hold was refused because
the Phase "is held". Nothing could finish that mutation: its commit or push was
never made, and every other operation that writes the event log stopped behind
the record.

The precondition is still decided on the state as it is. Only when it refuses is
it decided again, without the one event this operation's own unfinished mutation
has provably applied - the same operation on the same entity, an event that is
exactly the one this operation records, and an event log that holds it exactly
as recorded. Whatever that proof does not cover goes the way it always went: a
state reached any other way is refused as before, another request never takes
the record over, and operations that were independent of it stay independent.
What would have to be taken on trust - several unfinished records, an event log
that disagrees with its record - is left untouched for a human to reconcile.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git
from workline import yamlish
from workline import roadmap as rm
from workline import start as st
from workline.create import RelatedSpec, WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, SpecViolation, StopError
from workline.ids import new_id
from workline.mutation import Mutation, MutationController, WriteScope
from workline.oplock import project_operation
from workline.phase_create import PhaseSpec
from workline.push_pin import pin_push_destination
from workline.state import ProjectView
from workline.store import WORKLINE_DIR
from workline.validate import validate_project

EVENT_LOG = f"{WORKLINE_DIR}/events/events.jsonl"
LEDGERS = sorted((f"{WORKLINE_DIR}/relations/roadmap.yaml", f"{WORKLINE_DIR}/relations/related.yaml", EVENT_LOG))


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone."""


# --------------------------------------------------------------------------- interruption windows
def after_recording(stage: str):
    """Stop with ``stage`` durably recorded and none of its effects applied."""
    real = Mutation.add_effects

    def fire(mutation, name, effects):
        real(mutation, name, effects)
        if name == stage:
            raise Interrupted(f"after add_effects({stage})")

    return mock.patch.object(Mutation, "add_effects", fire)


def before_applying(kind: str):
    """Stop just before the first effect of ``kind`` runs."""
    real = MutationController.apply_effect

    def fire(controller, record):
        if record["kind"] == kind:
            raise Interrupted(f"before {kind}")
        return real(controller, record)

    return mock.patch.object(MutationController, "apply_effect", fire)


def before(target, attr: str):
    def fire(*args, **kwargs):
        raise Interrupted(attr)

    return mock.patch.object(target, attr, fire)


WINDOWS = {
    "event recorded": lambda: after_recording("event"),  # recorded, not in the event log yet
    "event applied": lambda: before(rm, "_finalize"),  # in the event log, nothing committed
    "commit recorded": lambda: after_recording("finalize"),  # the commit decided, not made
    "committed": lambda: before_applying("git_push"),  # committed, not pushed
    "pushed": lambda: before(Mutation, "complete"),  # everything done but closing the mutation
}

# What a resume still has to do from each window - and so everything it must not do again.
STILL_TO_RUN = {
    "event recorded": ["append_event", "git_commit", "git_push"],
    "event applied": ["git_commit", "git_push"],
    "commit recorded": ["git_commit", "git_push"],
    "committed": ["git_push"],
    "pushed": [],
}

# The lifecycle each operation leaves its entity in.
LEAVES = {
    "phase-hold": "held",
    "phase-resume": "active",
    "phase-cancel": "cancelled",
    "roadmap-hold": "held",
    "roadmap-resume": "active",
    "roadmap-cancel": "cancelled",
    "roadmap-achievement": "achieved",
}


class LifecycleCase(WorklineTestCase):
    def build(self, name: str = "proj") -> None:
        self.name = name
        self.store = self.new_project(name, remote=True)
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B")})
        self.rid = roadmap.roadmap_id
        self.pa, self.pb = roadmap.phase_ids["a"], roadmap.phase_ids["b"]

    def operation(self, name: str):
        """One lifecycle operation, made ready to run: (call, entity, event type)."""
        store = self.store
        if name == "phase-resume":
            rm.hold_phase(store, self.pa)
        if name == "roadmap-resume":
            rm.hold_roadmap(store, self.rid)
        if name == "roadmap-achievement":
            entry = self.simple_entry(store, self.pa)
            st.start(store, entry.entry_work_id, "outer", completing_executor(store))
            rm.plan_exclude_phase(store, self.pb)
        return {
            "phase-hold": (lambda: rm.hold_phase(store, self.pa), self.pa, "phase_held"),
            "phase-resume": (lambda: rm.resume_phase(store, self.pa), self.pa, "phase_resumed"),
            "phase-cancel": (lambda: rm.cancel_phase(store, self.pa), self.pa, "phase_cancelled"),
            "roadmap-hold": (lambda: rm.hold_roadmap(store, self.rid), self.rid, "roadmap_held"),
            "roadmap-resume": (lambda: rm.resume_roadmap(store, self.rid), self.rid, "roadmap_resumed"),
            "roadmap-cancel": (lambda: rm.cancel_roadmap(store, self.rid), self.rid, "roadmap_cancelled"),
            "roadmap-achievement": (
                lambda: rm.evaluate_achievement(store, self.rid, "achieved"), self.rid, "roadmap_achieved"),
        }[name]

    # interruption ----------------------------------------------------------
    def interrupt(self, call, window: str) -> dict:
        with WINDOWS[window]():
            with self.assertRaises(Interrupted):
                call()
        (pending,) = MutationController(self.store).list_pending()
        return pending

    def run_counting_effects(self, call):
        """Run ``call``, recording the kind of every effect it actually executes."""
        executed: list[str] = []
        real = MutationController.apply_effect

        def watch(controller, record):
            executed.append(record["kind"])
            return real(controller, record)

        with mock.patch.object(MutationController, "apply_effect", watch):
            result = call()
        return result, executed

    # observation -----------------------------------------------------------
    def events_of(self, entity: str, event_type: str) -> list[str]:
        return [e.id for e in ProjectView.load(self.store).events if e.entity == entity and e.type == event_type]

    def subjects(self) -> list[str]:
        return git(self.store.root, "log", "--format=%s").splitlines()

    def head(self) -> str:
        return git(self.store.root, "rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return git(self.remote_path(self.name), "rev-parse", "main").strip()

    def record_bytes(self) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in sorted(self.store.mutations.glob("*.yaml"))}

    def snapshot(self) -> dict:
        """Everything a refused request must leave exactly as it was."""
        return {
            "records": self.record_bytes(),
            "events": self.store.events_jsonl.read_bytes(),
            "head": self.head(),
            "remote": self.remote_head(),
        }

    def dirty(self) -> list[str]:
        status = git(self.store.root, "status", "--porcelain", "--untracked-files=all").splitlines()
        return [line for line in status if ".workline/runtime/" not in line]

    def edit_record(self, pending: dict, change) -> bytes:
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        record = yamlish.load(path.read_text(encoding="utf-8"))
        change(record)
        path.write_text(yamlish.dump(record), encoding="utf-8")
        return path.read_bytes()

    def edit_event(self, event_id: str, **changes) -> None:
        lines = self.store.events_jsonl.read_text(encoding="utf-8").splitlines()
        edited = []
        for line in lines:
            record = json.loads(line)
            if record["id"] == event_id:
                record.update(changes)
            edited.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        self.store.events_jsonl.write_text("\n".join(edited) + "\n", encoding="utf-8")

    def lifecycle(self, entity: str) -> str:
        view = ProjectView.load(self.store)
        return view.phase_lifecycle(entity) if entity in view.phases else view.roadmap_lifecycle(entity)

    def assertCarriedToTheEnd(self, pending: dict, result, entity: str, event_type: str) -> None:
        subject = f"chore(workline): {event_type} {entity}"
        self.assertEqual(self.lifecycle(entity), LEAVES[pending["invocation"]["operation"]])
        self.assertEqual(result.mutation_id, pending["mutation_id"])  # the same mutation, resumed
        self.assertEqual(len(self.events_of(entity, event_type)), 1)  # the event exactly once
        self.assertEqual(self.subjects().count(subject), 1)  # one commit
        self.assertEqual(self.subjects()[0], subject)  # and it is HEAD
        self.assertEqual(self.head(), self.remote_head())  # pushed
        self.assertEqual(MutationController(self.store).list_pending(), [])
        (record,) = MutationController(self.store).list_records()  # no second record
        self.assertEqual(record["mutation_id"], pending["mutation_id"])
        self.assertEqual(record["status"], "completed")  # a resumed record is kept (BL-019)
        self.assertEqual(record["reserved_ids"], pending["reserved_ids"])  # nothing new reserved
        self.assertEqual(validate_project(self.store), [])
        self.assertEqual(self.dirty(), [])


# --------------------------------------------------------------------------- the same request
class SameRequestResumeTests(LifecycleCase):
    def assertResumesFrom(self, name: str, windows) -> None:
        for index, window in enumerate(windows):
            with self.subTest(operation=name, window=window):
                self.build(f"{name}-{index}")
                call, entity, event_type = self.operation(name)
                pending = self.interrupt(call, window)
                self.assertEqual(pending["invocation"], {"entity": entity, "operation": name})

                result, executed = self.run_counting_effects(call)

                self.assertEqual(executed, STILL_TO_RUN[window])  # nothing applied twice
                self.assertCarriedToTheEnd(pending, result, entity, event_type)

    def test_phase_hold_resumes_from_every_window(self) -> None:
        self.assertResumesFrom("phase-hold", WINDOWS)

    def test_phase_resume_resumes_from_every_window(self) -> None:
        self.assertResumesFrom("phase-resume", WINDOWS)

    def test_phase_cancel_resumes_from_every_window(self) -> None:
        self.assertResumesFrom("phase-cancel", WINDOWS)

    def test_roadmap_hold_resume_and_cancel_resume(self) -> None:
        for name in ("roadmap-hold", "roadmap-resume", "roadmap-cancel"):
            self.assertResumesFrom(name, ("event applied", "committed", "pushed"))

    def test_an_achievement_resumes(self) -> None:
        self.assertResumesFrom("roadmap-achievement", ("event applied", "committed", "pushed"))

    def test_a_push_that_failed_is_pushed_by_the_retry(self) -> None:
        """The ordinary way to land in the window: the remote could not be reached."""
        self.build()
        away = self.tmp / "proj-remote-away.git"
        self.remote_path().rename(away)
        with self.assertRaises(StopError) as failed:
            rm.hold_phase(self.store, self.pa)
        self.assertEqual(failed.exception.code, "git_error")
        (pending,) = MutationController(self.store).list_pending()
        away.rename(self.remote_path())

        result, executed = self.run_counting_effects(lambda: rm.hold_phase(self.store, self.pa))

        self.assertEqual(executed, ["git_push"])
        self.assertCarriedToTheEnd(pending, result, self.pa, "phase_held")

    def test_the_project_is_no_longer_held_up_behind_the_record(self) -> None:
        self.build()
        work = self.simple_entry(self.store, self.pb).work_ids["w1"]
        pending = self.interrupt(lambda: rm.hold_phase(self.store, self.pa), "committed")
        # START shares the event log with the unfinished hold, so it waits for it ...
        with self.assertRaises(ReconcileRequired):
            st.start(self.store, work, "single-work", completing_executor(self.store))

        # ... until the hold itself is run again and finishes.
        self.assertEqual(rm.hold_phase(self.store, self.pa).mutation_id, pending["mutation_id"])
        self.assertEqual(st.start(self.store, work, "single-work", completing_executor(self.store)).status, "completed")
        self.assertEqual(validate_project(self.store), [])


# --------------------------------------------------------------------------- other requests
class OtherRequestTests(LifecycleCase):
    """Nothing but the same operation on the same entity continues the record."""

    def test_an_unfinished_hold_is_not_continued_by_a_cancel_or_a_resume(self) -> None:
        self.build()
        pending = self.interrupt(lambda: rm.hold_phase(self.store, self.pa), "event applied")
        before_refusal = self.snapshot()

        for other in (rm.cancel_phase, rm.resume_phase):
            with self.subTest(operation=other.__name__):
                with self.assertRaises(ReconcileRequired) as raised:
                    other(self.store, self.pa)
                self.assertIn(pending["mutation_id"], str(raised.exception))
                self.assertEqual(self.snapshot(), before_refusal)

        # The hold is still the hold, and finishes as one.
        self.assertEqual(rm.hold_phase(self.store, self.pa).mutation_id, pending["mutation_id"])
        self.assertEqual(ProjectView.load(self.store).phase_lifecycle(self.pa), "held")

    def test_an_unfinished_cancel_still_refuses_a_hold(self) -> None:
        """The cancel is not this request's own write, so its state is refused as before."""
        self.build()
        pending = self.interrupt(lambda: rm.cancel_phase(self.store, self.pa), "event applied")
        before_refusal = self.snapshot()

        with self.assertRaises(SpecViolation):
            rm.hold_phase(self.store, self.pa)

        self.assertEqual(self.snapshot(), before_refusal)
        self.assertEqual(rm.cancel_phase(self.store, self.pa).mutation_id, pending["mutation_id"])

    def test_the_same_operation_on_another_entity_does_not_take_the_record_over(self) -> None:
        """Both write the event log, so they are not independent (BL-017) - and still not one request."""
        self.build()
        pending = self.interrupt(lambda: rm.hold_phase(self.store, self.pa), "event applied")
        before_refusal = self.snapshot()

        for call in (lambda: rm.hold_phase(self.store, self.pb), lambda: rm.hold_roadmap(self.store, self.rid)):
            with self.assertRaises(ReconcileRequired) as raised:
                call()
            self.assertIn(pending["mutation_id"], str(raised.exception))
            self.assertEqual(self.snapshot(), before_refusal)
        self.assertEqual(ProjectView.load(self.store).phase_lifecycle(self.pb), "active")

    def test_operations_independent_of_the_record_still_proceed(self) -> None:
        """Nothing that did not overlap the unfinished hold is stopped by it now."""
        self.build()
        (self.store.root / "a.md").write_text("a\n", encoding="utf-8")
        work = self.simple_entry(self.store, self.pb, {"w1": "W1", "w2": "W2"}).work_ids["w2"]
        pending = self.interrupt(lambda: rm.hold_phase(self.store, self.pa), "event applied")

        self.assertTrue(rm.maintain_work_related(self.store, work, add=(RelatedSpec("must_read", "a.md"),)).changed)
        added = rm.add_phases(self.store, self.rid, {"c": PhaseSpec("Phase C", "C")})
        self.assertTrue(self.simple_entry(self.store, added.phase_ids["c"]).expanded)
        create_standalone_work(self.store, WorkSpec("Standalone", "done"))
        self.simple_roadmap(self.store, {"z": ("Phase Z", "Z")})
        self.assertEqual([p["mutation_id"] for p in MutationController(self.store).list_pending()],
                         [pending["mutation_id"]])

        self.assertEqual(rm.hold_phase(self.store, self.pa).mutation_id, pending["mutation_id"])
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(validate_project(self.store), [])


# --------------------------------------------------------------------------- proof, not state
class OwnWriteProofTests(LifecycleCase):
    """A state is taken as the request's own write only when its record proves it."""

    def test_a_finished_operation_asked_again_is_refused_as_before(self) -> None:
        for index, name in enumerate(LEAVES):
            with self.subTest(operation=name):
                self.build(f"done-{index}")
                call, _, _ = self.operation(name)
                result, executed = self.run_counting_effects(call)
                self.assertEqual(executed, ["append_event", "git_commit", "git_push"])
                self.assertEqual(MutationController(self.store).list_records(), [])  # cleaned up (BL-019)
                before_refusal = self.snapshot()

                with self.assertRaises(SpecViolation):
                    call()

                self.assertEqual(self.snapshot(), before_refusal)  # no record, no event, no commit

    def test_a_record_that_wrote_nothing_does_not_explain_the_state(self) -> None:
        """The Phase is held by a finished hold; an unfinished one that wrote nothing is not its author."""
        self.build()
        rm.hold_phase(self.store, self.pa)
        with project_operation(self.store, "test"):
            empty = MutationController(self.store).begin(
                rm.OWNER, {"operation": "phase-hold", "entity": self.pa},
                WriteScope(entities=(self.pa,), files=(EVENT_LOG,)))
        before_refusal = self.snapshot()

        with self.assertRaises(SpecViolation):
            rm.hold_phase(self.store, self.pa)

        self.assertEqual(self.snapshot(), before_refusal)
        self.assertEqual([p["mutation_id"] for p in MutationController(self.store).list_pending()], [empty.id])

    def test_a_recorded_event_that_is_not_in_the_log_does_not_explain_the_state(self) -> None:
        """Its own event was never written, so the held Phase is somebody else's doing."""
        self.build()
        pending = self.interrupt(lambda: rm.hold_phase(self.store, self.pa), "event recorded")
        # The Phase gets held another way while that event is still unwritten.
        foreign = {"id": new_id("event"), "type": "phase_held", "entity": self.pa, "at": "2026-01-01T00:00:00+00:00"}
        with self.store.events_jsonl.open("a", encoding="utf-8", newline="\n") as log:
            log.write(json.dumps(foreign, separators=(",", ":")) + "\n")
        before_refusal = self.snapshot()

        with self.assertRaises(SpecViolation):
            rm.hold_phase(self.store, self.pa)

        self.assertEqual(self.snapshot(), before_refusal)
        self.assertEqual(len(self.events_of(self.pa, "phase_held")), 1)  # no second hold
        self.assertEqual(MutationController(self.store).list_pending()[0]["mutation_id"], pending["mutation_id"])

    def test_an_event_log_that_disagrees_with_the_record_requires_reconcile(self) -> None:
        for index, changes in enumerate(({"at": "2000-01-01T00:00:00+00:00"}, {"type": "phase_resumed"})):
            with self.subTest(changed=sorted(changes)):
                self.build(f"mismatch-{index}")
                pending = self.interrupt(lambda: rm.hold_phase(self.store, self.pa), "event applied")
                (effect,) = [e for e in pending["effects"] if e["kind"] == "append_event"]
                self.edit_event(effect["payload"]["record"]["id"], **changes)
                before_refusal = self.snapshot()

                with self.assertRaises(ReconcileRequired) as raised:
                    rm.hold_phase(self.store, self.pa)

                self.assertIn(pending["mutation_id"], str(raised.exception))
                self.assertEqual(self.snapshot(), before_refusal)

    def test_a_record_holding_another_event_is_not_taken_as_its_own(self) -> None:
        """It cannot be this hold's own write if what it recorded is not a hold, so nothing is left out."""
        self.build()
        pending = self.interrupt(lambda: rm.hold_phase(self.store, self.pa), "event applied")
        (effect,) = [e for e in pending["effects"] if e["kind"] == "append_event"]

        def record_a_cancel(record: dict) -> None:
            for recorded in record["effects"]:
                if recorded["kind"] == "append_event":
                    recorded["payload"]["record"]["type"] = "phase_cancelled"

        self.edit_record(pending, record_a_cancel)
        self.edit_event(effect["payload"]["record"]["id"], type="phase_cancelled")  # and the log agrees with it
        before_refusal = self.snapshot()

        with self.assertRaises(SpecViolation) as raised:
            rm.hold_phase(self.store, self.pa)

        self.assertIn("cancelled", str(raised.exception))  # the state as it is, refused as it always was
        self.assertEqual(self.snapshot(), before_refusal)

    def test_an_unreadable_recovery_area_is_reported_where_it_always_was(self) -> None:
        """It proves no event to be anyone's, so neither a refusal nor its report changes."""
        self.build()
        rm.hold_phase(self.store, self.pa)
        stray = self.store.mutations / f"{new_id('mutation')}.yaml"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text("status: pending\n", encoding="utf-8")
        before_refusal = self.snapshot()

        with self.assertRaises(SpecViolation):  # the precondition refuses first, as before
            rm.hold_phase(self.store, self.pa)
        with self.assertRaises(ReconcileRequired) as raised:  # and opening a mutation reports the area
            rm.hold_phase(self.store, self.pb)

        self.assertIn(stray.name, str(raised.exception))
        self.assertEqual(self.snapshot(), before_refusal)

    def test_several_unfinished_holds_of_one_phase_require_reconcile(self) -> None:
        self.build()
        pending = self.interrupt(lambda: rm.hold_phase(self.store, self.pa), "event applied")
        twin = new_id("mutation")
        record = yamlish.load(MutationController(self.store).intent_path(pending["mutation_id"]).read_text(encoding="utf-8"))
        record["mutation_id"] = twin
        MutationController(self.store).intent_path(twin).write_text(yamlish.dump(record), encoding="utf-8")
        before_refusal = self.snapshot()

        with self.assertRaises(ReconcileRequired) as raised:
            rm.hold_phase(self.store, self.pa)

        self.assertIn(pending["mutation_id"], str(raised.exception))
        self.assertIn(twin, str(raised.exception))
        self.assertEqual(self.snapshot(), before_refusal)

    def test_an_achievement_already_written_is_never_reported_as_not_ready(self) -> None:
        """If the plan stopped being ready meanwhile, the unfinished achievement STOPs instead."""
        self.build()
        call, _, _ = self.operation("roadmap-achievement")
        pending = self.interrupt(call, "event applied")
        before_refusal = self.snapshot()

        with mock.patch.object(ProjectView, "all_active_phases_complete", lambda view, roadmap_id: False):
            with self.assertRaises(StopError) as raised:
                call()

        self.assertEqual(raised.exception.code, "achievement_not_ready")
        self.assertEqual(self.snapshot(), before_refusal)
        self.assertEqual(MutationController(self.store).list_pending()[0]["mutation_id"], pending["mutation_id"])


# --------------------------------------------------------------------------- neighbours
class NeighbourContractTests(LifecycleCase):
    def test_a_record_written_with_the_broad_scope_of_before_still_resumes(self) -> None:
        """BL-017: a record keeps the scope it was written with, and is still this operation's own."""
        self.build()
        pending = self.interrupt(lambda: rm.hold_phase(self.store, self.pa), "event applied")
        self.edit_record(pending, lambda record: record["write_scope"].update(files=LEDGERS))

        result = rm.hold_phase(self.store, self.pa)

        self.assertCarriedToTheEnd(pending, result, self.pa, "phase_held")

    def test_a_changed_push_destination_still_stops_the_resume(self) -> None:
        self.build()
        other = self.tmp / "second-destination.git"
        git(self.tmp, "init", "--bare", "-b", "main", str(other))
        pin_push_destination(self.store.root, [self.remote_url(), str(other)])
        pending = self.interrupt(lambda: rm.hold_phase(self.store, self.pa), "committed")

        git(self.store.root, "remote", "set-url", "origin", str(other))
        with self.assertRaises(ReconcileRequired) as raised:
            rm.hold_phase(self.store, self.pa)

        self.assertIn("push destination changed", str(raised.exception))
        self.assertEqual(git(other, "for-each-ref").strip(), "")  # nothing was sent anywhere new
        (still,) = MutationController(self.store).list_pending()
        self.assertEqual(still["mutation_id"], pending["mutation_id"])

    def test_an_unapproved_push_destination_stops_before_the_record_is_touched(self) -> None:
        self.build()
        pending = self.interrupt(lambda: rm.hold_phase(self.store, self.pa), "committed")
        moved = self.tmp / "moved.git"
        git(self.tmp, "init", "--bare", "-b", "main", str(moved))
        git(self.store.root, "remote", "set-url", "origin", str(moved))
        before_refusal = self.record_bytes()

        with self.assertRaises(StopError) as raised:
            rm.hold_phase(self.store, self.pa)

        self.assertEqual(raised.exception.code, "push_destination_mismatch")
        self.assertEqual(self.record_bytes(), before_refusal)
        self.assertEqual(git(moved, "for-each-ref").strip(), "")
        self.assertEqual(MutationController(self.store).list_pending()[0]["mutation_id"], pending["mutation_id"])


if __name__ == "__main__":
    unittest.main()
