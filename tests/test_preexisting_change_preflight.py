"""An operation refuses a change from before it that its commit could not separate before its first effect (BL-041).

START, a Roadmap lifecycle decision and a plan exclusion note which paths were already changed when they began, and
their Git stage refuses a commit that overlaps those paths (``dirty_overlap``). That was the first place the overlap
was looked at. With a change to the event log from before the operation - a person's appended event, a blank line -
START appended its opening events, ran its executor, committed and pushed the result and appended the completion
before it stopped; a Phase hold appended its event, and a plan exclusion its event and its replan. The note names
paths and is recorded once, so no retry, restore or separate commit of the person's change finished that mutation,
and every operation writing the same ledgers stopped behind it.

The same refusal now comes first: on the very snapshot the Git stage reads, against what the operation commits
whatever else it goes on to do - the event log for START and a lifecycle decision, the event log and the relation
files its replan writes for a plan exclusion. The mutation is abandoned, nothing is appended, run, written, committed
or pushed, and the operation goes on normally once the person's change is committed or discarded. The person's change
is never separated from the operation's own writes. Changes outside those paths are left alone as before, and a
record that already holds effects is not refused this way: it keeps stopping at its Git stage - and, since BL-044
reads a recorded hold back instead of deciding it again, a retry of one adds nothing while it does.
"""

from __future__ import annotations

import json
import re
import unittest
from unittest import mock

from helpers import WorklineTestCase, completing_executor, git
from workline import gitops
from workline import roadmap as rm
from workline import start as st
from workline.create import RelatedSpec, RelationSpec, WorkSpec, create_standalone_work
from workline.errors import StopError
from workline.ids import new_id
from workline.mutation import Mutation, MutationController
from workline.ops import Replan
from workline.state import ACTIVE, ProjectView
from workline.store import WORKLINE_DIR
from workline.validate import validate_project

EVENT_LOG = f"{WORKLINE_DIR}/events/events.jsonl"
ROADMAP_YAML = f"{WORKLINE_DIR}/relations/roadmap.yaml"
RELATED_YAML = f"{WORKLINE_DIR}/relations/related.yaml"
OVERLAP = "pre-existing changes overlap operation-owned paths and cannot be separated safely: "


class Interrupted(RuntimeError):
    """A deterministic interruption, injected by the test alone."""


def before_bl041():
    """The implementation before this change, which left the overlap to the Git stage alone."""
    return mock.patch.object(gitops, "ensure_separable_before_effects", lambda mutation, paths: None)


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


def before_pushing(pattern: str):
    """Stop with the commit of a stage matching ``pattern`` made, and its push not made."""
    real = MutationController.apply_effect

    def fire(controller, record):
        if record["kind"] == "git_push" and re.search(pattern, record["stage"]):
            raise Interrupted("committed, not pushed")
        return real(controller, record)

    return mock.patch.object(MutationController, "apply_effect", fire)


def after_noting():
    """Stop right after the snapshot of pre-existing changes is saved, before anything else is recorded."""
    real = Mutation.set_note

    def fire(mutation, key, value):
        real(mutation, key, value)
        if key == "preexisting_dirty":
            raise Interrupted("noted")

    return mock.patch.object(Mutation, "set_note", fire)


class PreflightCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.root = self.store.root
        self.ran: list[str] = []

    # fixtures ---------------------------------------------------------------
    def phases(self) -> None:
        """Phase A entered (W1, its integration I1); Phases B and C not entered."""
        roadmap = self.simple_roadmap(self.store, {"a": ("Phase A", "A"), "b": ("Phase B", "B"), "c": ("Phase C", "C")})
        self.rid = roadmap.roadmap_id
        self.pa, self.pb, self.pc = (roadmap.phase_ids[key] for key in "abc")
        entry = self.simple_entry(self.store, self.pa)
        self.w1, self.i1 = entry.work_ids["w1"], entry.integration_id

    def standalone(self, *names: str) -> list[str]:
        return [create_standalone_work(self.store, WorkSpec(name, name.lower())).work_id for name in names]

    def executor(self, outcome=None):
        """Completes each Work with a result file, or returns ``outcome``."""
        done = completing_executor(self.store, self.ran)

        def execute(ctx: st.ExecutionContext):
            if outcome is None:
                return done(ctx)
            self.ran.append(ctx.work.id)
            return outcome

        return execute

    def start(self, work_id: str, mode: str = "single-work", outcome=None):
        return lambda: st.start(self.store, work_id, mode, self.executor(outcome))

    # a person's changes -----------------------------------------------------------
    def person_event(self) -> str:
        """A legal event a person appends to the event log and does not commit: Phase B held."""
        line = json.dumps({"id": new_id("event"), "type": "phase_held", "entity": self.pb, "at": "2026-09-15T00:00:00+00:00"},
                          separators=(",", ":")) + "\n"
        self.append(EVENT_LOG, line)
        return line

    def append(self, path: str, text: str) -> None:
        with open(self.root / path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(text)

    def commit_person_change(self, *paths: str) -> None:
        git(self.root, "add", "--", *paths)
        git(self.root, "commit", "-q", "-m", "person: my own change", "--", *paths)
        git(self.root, "push", "-q", "origin", "main")

    # observation --------------------------------------------------------------
    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return git(self.remote_path(), "rev-parse", "main").strip()

    def dirty(self) -> list[str]:
        status = git(self.root, "status", "--porcelain", "--untracked-files=all").splitlines()
        return [line for line in status if ".workline/runtime/" not in line]

    def records(self) -> list[dict]:
        return MutationController(self.store).list_records()

    def pending_ids(self) -> list[str]:
        return sorted(r["mutation_id"] for r in self.records() if r["status"] == "pending")

    def project(self) -> dict:
        """The Project files and Git, byte for byte, apart from the recovery area."""
        files = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in sorted(self.root.rglob("*"))
                 if p.is_file() and ".git" not in p.relative_to(self.root).parts
                 and "runtime" not in p.relative_to(self.root).parts}
        return {"files": files, "head": self.head(), "remote": self.remote_head(), "dirty": self.dirty()}

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

    def assertRefusedBeforeAnything(self, call, *overlap: str, resumed: dict | None = None) -> StopError:
        """Refused as the Git stage refuses, with no effect, no executor, no change and no pending record left.

        The mutation the refusal closes is a new one, or ``resumed`` when the call picks up that effect-less record.
        """
        before, ran, executed, stages = self.project(), list(self.ran), [], []
        statuses = {r["mutation_id"]: r["status"] for r in self.records()}
        with self.assertRaises(StopError) as refused:
            self.watching(call, executed, stages)
        self.assertEqual((refused.exception.code, refused.exception.message), ("dirty_overlap", OVERLAP + ", ".join(overlap)))
        self.assertEqual((stages, executed), ([], []))  # nothing recorded, appended, written, committed or pushed
        self.assertEqual(self.ran, ran)  # no executor
        self.assertEqual(self.project(), before)  # the person's change exactly as it was, and nothing else
        (closed,) = [r for r in self.records() if statuses.get(r["mutation_id"]) != r["status"]]
        self.assertEqual((closed["status"], closed["effects"]), ("abandoned", []))
        self.assertTrue(set(overlap) <= set(closed["notes"]["preexisting_dirty"]))
        if resumed is None:
            self.assertNotIn(closed["mutation_id"], statuses)
        else:
            self.assertEqual(closed["mutation_id"], resumed["mutation_id"])
        pending = sorted(mid for mid, status in statuses.items() if status == "pending" and mid != closed["mutation_id"])
        self.assertEqual(self.pending_ids(), pending)  # no record left for a retry to be stopped by
        return refused.exception

    def assertLeftAsItWas(self, before: dict, *paths: str) -> None:
        """The operation committed and pushed, and the person's changes are still there, uncommitted, as they were."""
        after = self.project()
        self.assertEqual(self.head(), self.remote_head())
        self.assertEqual(after["dirty"], before["dirty"])
        for path in paths:
            self.assertEqual(after["files"].get(path), before["files"].get(path))
        self.assertEqual(MutationController(self.store).list_pending(), [])


# --------------------------------------------------------------------------- START
class StartTests(PreflightCase):
    def test_a_change_to_the_event_log_from_before_start_is_refused_before_anything_runs(self) -> None:
        self.phases()
        call = self.start(self.w1)
        self.person_event()

        self.assertRefusedBeforeAnything(call, EVENT_LOG)
        self.assertRefusedBeforeAnything(call, EVENT_LOG)  # a retry leaves no stuck record either

        self.commit_person_change(EVENT_LOG)
        result = call()
        self.assertEqual((result.status, self.ran), ("completed", [self.w1]))
        self.assertEqual((self.dirty(), self.head(), self.pending_ids()), ([], self.remote_head(), []))
        self.assertEqual(validate_project(self.store), [])

    def test_a_blank_line_is_refused_the_same_way_and_discarding_it_lets_start_run(self) -> None:
        self.phases()
        call = self.start(self.w1)
        self.append(EVENT_LOG, "\n")

        self.assertRefusedBeforeAnything(call, EVENT_LOG)

        git(self.root, "checkout", "--", EVENT_LOG)
        self.assertEqual(call().status, "completed")
        self.assertEqual((self.dirty(), self.pending_ids()), ([], []))

    def test_no_outcome_is_asked_for_first(self) -> None:
        """Hold, cancel, a question wait and an outer run all end in the event log's commit, so none is asked first."""
        self.phases()
        self.person_event()
        for label, call in (
            ("hold", self.start(self.w1, outcome=st.Hold("later"))),
            ("question wait", self.start(self.w1, outcome=st.QuestionWait("which one?"))),
            ("cancel", self.start(self.w1, outcome=st.Cancel(Replan(), "not needed"))),
            ("outer", self.start(self.w1, "outer")),
        ):
            with self.subTest(outcome=label):
                self.assertRefusedBeforeAnything(call, EVENT_LOG)

    def test_what_start_refuses_first_keeps_its_own_refusal(self) -> None:
        self.phases()
        s1, s2, s3, helper = self.standalone("S1", "S2", "S3", "Helper")
        st.start(self.store, s1, "single-work", completing_executor(self.store))
        st.plan_exclude_standalone_work(self.store, helper, Replan(add_relations=(RelationSpec("requires_completion", s2, s3),)))
        rm.hold_phase(self.store, self.pa)
        self.person_event()
        for label, call, code in (
            ("a completed Work", self.start(s1), "spec_violation"),
            ("a held Phase", self.start(self.w1), "phase_inactive"),
            ("an unfinished dependency", self.start(s3), "dependency_unsatisfied"),
        ):
            with self.subTest(refused=label):
                before = self.project()
                with self.assertRaises(StopError) as refused:
                    call()
                self.assertEqual(refused.exception.code, code)
                self.assertEqual((self.project(), self.pending_ids(), self.ran), (before, [], []))

    def test_changes_start_does_not_commit_are_left_alone(self) -> None:
        self.phases()
        (self.root / "notes.txt").write_text("a person's draft\n", encoding="utf-8")
        self.append(ROADMAP_YAML, "\n")
        self.append(RELATED_YAML, "\n")
        before = self.project()

        result = self.start(self.w1)()

        self.assertEqual((result.status, self.ran), ("completed", [self.w1]))
        self.assertLeftAsItWas(before, "notes.txt", ROADMAP_YAML, RELATED_YAML)

    def test_a_clean_start_is_unchanged(self) -> None:
        self.phases()
        executed, stages = [], []

        result = self.watching(self.start(self.w1), executed, stages)

        self.assertEqual(result.status, "completed")
        self.assertEqual(executed, ["append_event", "append_event", "git_commit", "git_push",
                                    "append_event", "append_event", "git_commit", "git_push"])
        self.assertEqual((self.dirty(), self.pending_ids(), self.head()), ([], [], self.remote_head()))


# --------------------------------------------------------------------------- Roadmap lifecycle
class LifecycleTests(PreflightCase):
    def test_a_change_to_the_event_log_stops_a_lifecycle_decision_before_its_event(self) -> None:
        self.phases()
        call = lambda: rm.hold_phase(self.store, self.pa)  # noqa: E731
        self.person_event()

        self.assertRefusedBeforeAnything(call, EVENT_LOG)
        self.assertRefusedBeforeAnything(call, EVENT_LOG)

        self.assertEqual(ProjectView.load(self.store).phase_lifecycle(self.pa), ACTIVE)
        self.commit_person_change(EVENT_LOG)
        self.assertEqual(call().status, "phase_held")
        self.assertEqual((self.dirty(), self.pending_ids(), self.head()), ([], [], self.remote_head()))

    def test_a_change_outside_the_event_log_does_not_stop_it(self) -> None:
        self.phases()
        self.append(ROADMAP_YAML, "\n")
        self.append(RELATED_YAML, "\n")
        before = self.project()

        self.assertEqual(rm.hold_phase(self.store, self.pa).status, "phase_held")

        self.assertLeftAsItWas(before, ROADMAP_YAML, RELATED_YAML)


# --------------------------------------------------------------------------- plan exclusion
class PlanExclusionTests(PreflightCase):
    def replacement(self) -> tuple[str, Replan]:
        """Phase A with W1 and W2; W2's exclusion replaces it by W3, which must read a document."""
        (self.root / "doc.md").write_text("doc\n", encoding="utf-8")
        self.commit_person_change("doc.md")
        roadmap = self.simple_roadmap(self.store)
        self.rid, self.pa = roadmap.roadmap_id, roadmap.phase_ids["a"]
        entry = self.simple_entry(self.store, self.pa, {"w1": "W1", "w2": "W2"})
        w2, i1 = entry.work_ids["w2"], entry.integration_id
        (removed,) = [r.id for r in ProjectView.load(self.store).roadmap_relations
                      if (r.type, r.from_id, r.to) == ("requires_completion", w2, i1)]
        return w2, Replan(
            remove_relation_ids=(removed,),
            add_relations=(RelationSpec("requires_completion", "w3", i1),),
            new_works={"w3": WorkSpec("W3", "w3", phase_id=self.pa, roadmap_id=self.rid,
                                      related=(RelatedSpec("must_read", "doc.md"),))},
        )

    def test_a_change_to_the_event_log_is_refused_before_a_phase_is_excluded(self) -> None:
        self.phases()
        call = lambda: rm.plan_exclude_phase(self.store, self.pc, Replan())  # noqa: E731
        self.person_event()

        self.assertRefusedBeforeAnything(call, EVENT_LOG)

        self.commit_person_change(EVENT_LOG)
        self.assertEqual(call().status, "plan_excluded")
        self.assertEqual((self.dirty(), self.pending_ids()), ([], []))

    def test_a_change_to_the_relations_a_replan_writes_is_refused_before_its_event(self) -> None:
        s1, s2 = self.standalone("S1", "S2")
        replan = Replan(new_works={"k": WorkSpec("K", "k")}, add_relations=(RelationSpec("planned_next", s1, "k"),))
        call = lambda: st.plan_exclude_standalone_work(self.store, s2, replan)  # noqa: E731
        self.append(ROADMAP_YAML, "\n")

        self.assertRefusedBeforeAnything(call, ROADMAP_YAML)

        git(self.root, "checkout", "--", ROADMAP_YAML)
        self.assertEqual(call().status, "plan_excluded")
        self.assertEqual((self.dirty(), self.pending_ids()), ([], []))

    def test_a_change_to_the_related_a_replacement_carries_is_refused_before_its_event(self) -> None:
        w2, replan = self.replacement()
        call = lambda: rm.plan_exclude_work(self.store, w2, replan)  # noqa: E731
        self.append(RELATED_YAML, "\n")

        self.assertRefusedBeforeAnything(call, RELATED_YAML)
        self.append(ROADMAP_YAML, "\n")
        self.assertRefusedBeforeAnything(call, RELATED_YAML, ROADMAP_YAML)

        git(self.root, "checkout", "--", RELATED_YAML, ROADMAP_YAML)
        self.assertEqual(call().status, "plan_excluded")
        self.assertEqual((self.dirty(), self.pending_ids()), ([], []))

    def test_a_ledger_the_exclusion_does_not_write_is_left_alone(self) -> None:
        self.phases()
        s1, s2 = self.standalone("S1", "S2")
        self.append(ROADMAP_YAML, "\n")
        self.append(RELATED_YAML, "\n")
        before = self.project()
        for label, call in (
            ("roadmap, no replan", lambda: rm.plan_exclude_phase(self.store, self.pb, Replan())),
            ("start, a new Work without relations or Related",
             lambda: st.plan_exclude_standalone_work(self.store, s2, Replan(new_works={"k": WorkSpec("K", "k")}))),
        ):
            with self.subTest(exclusion=label):
                self.assertEqual(call().status, "plan_excluded")
                self.assertLeftAsItWas(before, ROADMAP_YAML, RELATED_YAML)


# --------------------------------------------------------------------------- records written before this refusal
class LegacyRecordTests(PreflightCase):
    def stuck(self, call) -> dict:
        """What the implementation before this change left: effects applied, then stopped at the Git stage."""
        with before_bl041(), self.assertRaises(StopError) as stopped:
            call()
        self.assertEqual(stopped.exception.code, "dirty_overlap")
        (pending,) = [r for r in self.records() if r["status"] == "pending"]
        self.assertTrue(pending["effects"])
        return pending

    def assertStillStoppedAtTheGitStage(self, call, pending: dict) -> None:
        path = MutationController(self.store).intent_path(pending["mutation_id"])
        before, record, ran, executed, stages = self.project(), path.read_bytes(), list(self.ran), [], []
        with self.assertRaises(StopError) as stopped:
            self.watching(call, executed, stages)
        self.assertEqual(stopped.exception.code, "dirty_overlap")
        self.assertEqual((stages, executed, self.ran), ([], [], ran))
        self.assertEqual((self.project(), path.read_bytes(), self.pending_ids()), (before, record, [pending["mutation_id"]]))

    def withdraw(self, line: str) -> None:
        """The person takes exactly their own line back out of the event log."""
        raw = self.store.events_jsonl.read_bytes()
        self.assertIn(line.encode("utf-8"), raw)
        self.store.events_jsonl.write_bytes(raw.replace(line.encode("utf-8"), b"", 1))

    def test_a_stuck_start_keeps_stopping_at_its_git_stage(self) -> None:
        self.phases()
        line = self.person_event()
        call = self.start(self.w1)
        pending = self.stuck(call)
        self.assertEqual(self.ran, [self.w1])

        self.assertStillStoppedAtTheGitStage(call, pending)
        self.withdraw(line)
        self.assertStillStoppedAtTheGitStage(call, pending)  # nothing is guessed from what the change was

    def test_a_stuck_hold_keeps_stopping_at_its_git_stage_and_grows_nothing(self) -> None:
        """BL-044 reads the recorded hold back, so no retry decides it again (``test_recorded_hold_resume``)."""
        self.phases()
        line = self.person_event()
        call = self.start(self.w1, outcome=st.Hold("later"))
        pending = self.stuck(call)
        self.assertEqual((self.ran, len(pending["effects"])), ([self.w1], 4))

        self.assertStillStoppedAtTheGitStage(call, pending)
        self.withdraw(line)
        self.assertStillStoppedAtTheGitStage(call, pending)  # nothing is guessed from what the change was

    def test_a_stuck_lifecycle_decision_keeps_stopping_at_its_git_stage(self) -> None:
        self.phases()
        line = self.person_event()
        call = lambda: rm.hold_phase(self.store, self.pa)  # noqa: E731
        pending = self.stuck(call)

        self.assertStillStoppedAtTheGitStage(call, pending)
        self.withdraw(line)
        self.assertStillStoppedAtTheGitStage(call, pending)

    def test_a_record_that_noted_the_change_and_recorded_nothing_else_is_abandoned(self) -> None:
        """Interrupted between the snapshot and the refusal, the retry refuses on that snapshot and leaves nothing."""
        self.phases()
        call = self.start(self.w1)
        self.person_event()
        with after_noting(), self.assertRaises(Interrupted):
            call()
        (noted,) = [r for r in self.records() if r["status"] == "pending"]
        self.assertEqual((noted["effects"], noted["notes"]), ([], {"preexisting_dirty": [EVENT_LOG]}))

        self.assertRefusedBeforeAnything(call, EVENT_LOG, resumed=noted)

        self.commit_person_change(EVENT_LOG)
        self.assertEqual(call().status, "completed")
        self.assertEqual((self.dirty(), self.pending_ids()), ([], []))


# --------------------------------------------------------------------------- what resumes as it did
class ResumeTests(PreflightCase):
    def test_an_interrupted_completion_is_finalized_as_before(self) -> None:
        """BL-031: only the Git stage is left, and the refusal before the first effect does not stand in its way."""
        self.phases()
        call = self.start(self.w1)
        with after_applying(rf"^{self.w1}:lifecycle:1$"), self.assertRaises(Interrupted):
            call()
        executed, stages = [], []

        result = self.watching(call, executed, stages)

        self.assertEqual((result.status, executed, self.ran), ("completed", ["git_commit", "git_push"], [self.w1]))
        self.assertEqual((self.dirty(), self.pending_ids()), ([], []))

    def test_an_interrupted_cancel_is_carried_on_as_before(self) -> None:
        """BL-030: the cancel goes on from the decision it recorded."""
        (s1,) = self.standalone("S1")
        call = self.start(s1, outcome=st.Cancel(Replan(), "not needed"))
        with after_applying(rf"^{s1}:lifecycle:1$"), self.assertRaises(Interrupted):
            call()
        executed, stages = [], []

        result = self.watching(call, executed, stages)

        self.assertEqual((result.status, executed, self.ran), ("cancelled", ["git_commit", "git_push"], [s1]))
        self.assertEqual((self.dirty(), self.pending_ids()), ([], []))

    def test_a_resume_on_a_branch_without_its_commit_stops_where_it_stopped(self) -> None:
        """BL-038: an applied effect is not written again off its commit's branch; nothing here runs before that."""
        self.phases()
        git(self.root, "branch", "side")
        call = lambda: rm.hold_phase(self.store, self.pa)  # noqa: E731
        with before_pushing(r"^finalize$"), self.assertRaises(Interrupted):
            call()
        (pending,) = [r for r in self.records() if r["status"] == "pending"]
        git(self.root, "checkout", "-q", "side")
        before, executed, stages = self.project(), [], []

        with self.assertRaises(StopError) as stopped:
            self.watching(call, executed, stages)

        self.assertEqual(stopped.exception.code, "reconcile_required")
        self.assertIn("whose working tree does not hold that effect", stopped.exception.message)
        self.assertEqual((executed, stages, self.project(), self.pending_ids()), ([], [], before, [pending["mutation_id"]]))
        git(self.root, "checkout", "-q", "main")
        self.assertEqual(call().status, "phase_held")
        self.assertEqual((self.pending_ids(), self.head()), ([], self.remote_head()))


# --------------------------------------------------------------------------- what this refusal does not reach
class KnownResidualTests(PreflightCase):
    def test_a_result_path_is_only_known_once_the_executor_returns(self) -> None:
        """A person's file at a path the executor then writes is refused where the result is known, after the opening events."""
        self.phases()
        display = ProjectView.load(self.store).works[self.w1].display
        (self.root / f"result_{display}.txt").write_text("someone else's draft\n", encoding="utf-8")
        head = self.head()

        with self.assertRaises(StopError) as stopped:
            self.start(self.w1)()

        self.assertEqual((stopped.exception.code, self.ran), ("dirty_overlap", [self.w1]))
        (pending,) = [r for r in self.records() if r["status"] == "pending"]
        self.assertEqual(sorted({e["stage"] for e in pending["effects"]}), [f"{self.w1}:lifecycle:0"])
        self.assertEqual((self.head(), self.remote_head()), (head, head))

    def test_a_change_made_after_start_began_is_still_committed_with_it(self) -> None:
        """A person's event appended while the executor runs is not in the snapshot taken before it."""
        self.phases()
        done = completing_executor(self.store, self.ran)
        appended = {}

        def executor(ctx: st.ExecutionContext):
            appended["line"] = self.person_event()
            return done(ctx)

        self.assertEqual(st.start(self.store, self.w1, "single-work", executor).status, "completed")

        self.assertIn(appended["line"].strip(), git(self.root, "show", f"HEAD:{EVENT_LOG}"))
        self.assertEqual((self.dirty(), self.head()), ([], self.remote_head()))


if __name__ == "__main__":
    unittest.main()
