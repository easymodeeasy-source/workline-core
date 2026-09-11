"""BL-021: one active writer per established Workline Project.

The Project execution lock is held by one process at a time. The busy side
STOPs without writing anything, a question wait releases the lock while its
mutation stays pending, a crash releases it with no cleanup of any kind, child
registration joins the running operation, a write-bearing achievement is
decided on the state current under the lock, and initial Project開始 stays
outside it. Several tests hold the lock in a child process (``lock_child.py``)
so that the contention is real: separate processes on the running OS.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from unittest import mock

from helpers import WORKLINE_ROOT, WorklineTestCase, completing_executor, git, scripted_executor

from workline import bootstrap as bs
from workline import oplock
from workline import project_start as ps
from workline import roadmap as rm
from workline import start as st
from workline.create import RelatedSpec, WorkSpec, create_standalone_work
from workline.errors import ProjectOperationBusy, ProjectOperationNested, StopError
from workline.mutation import INTENT_VERSION, MutationController, WriteScope
from workline.phase_create import PhaseSpec
from workline.push_pin import pin_push_destination
from workline.state import ProjectView
from workline.store import LOCK_EXEMPT_OWNERS, ProjectStore
from workline.validate import validate_project

CHILD = Path(__file__).resolve().parent / "lock_child.py"
WAIT_SECONDS = 120
LIFECYCLE = ["work_started", "work_target_added", "work_target_removed", "work_completed"]


def events_of(store: ProjectStore, work_id: str) -> list[str]:
    return [e.type for e in ProjectView.load(store).events if e.entity == work_id]


def snapshot(store: ProjectStore) -> dict:
    """Everything a busy operation must leave exactly as it was."""
    workline = {}
    for path in sorted(store.workline.rglob("*")):
        rel = path.relative_to(store.root).as_posix()
        if path.is_file() and not rel.startswith((".workline/runtime/locks/", ".workline/runtime/tmp/")):
            workline[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "workline": workline,
        "head": git(store.root, "rev-parse", "HEAD").strip(),
        "index": git(store.root, "ls-files", "-s"),
        "status": git(store.root, "status", "--porcelain", "--untracked-files=all"),
    }


class ExecutionLockTestCase(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.signals = self.tmp / "signals"
        self.signals.mkdir()
        self._children = 0

    # child processes -----------------------------------------------------------
    def spawn(self, scenario: str, store: ProjectStore, name: str, **extra) -> subprocess.Popen:
        self._children += 1
        spec = {"scenario": scenario, "root": str(store.root), "name": name, "signal_dir": str(self.signals), **extra}
        spec_path = self.signals / f"spec-{self._children}-{name}.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        child = subprocess.Popen(
            [sys.executable, str(CHILD), str(spec_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.addCleanup(self._reap, child, name)
        return child

    def _reap(self, child: subprocess.Popen, name: str) -> None:
        if child.poll() is None:
            (self.signals / f"release-{name}").write_text("go", encoding="utf-8")
            try:
                child.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate()

    def wait_ready(self, child: subprocess.Popen, name: str) -> None:
        ready = self.signals / f"ready-{name}"
        deadline = time.monotonic() + WAIT_SECONDS
        while not ready.exists():
            if child.poll() is not None:
                out, err = child.communicate()
                self.fail(f"child {name} ended before it was ready: {out}\n{err}")
            if time.monotonic() > deadline:
                self.fail(f"child {name} never became ready")
            time.sleep(0.02)

    def outcome(self, child: subprocess.Popen, name: str) -> dict:
        out, err = child.communicate(timeout=WAIT_SECONDS)
        reports = [line for line in out.splitlines() if line.startswith("{")]
        if not reports:
            self.fail(f"child {name} reported nothing (exit {child.returncode}): {out}\n{err}")
        return json.loads(reports[-1])

    def release(self, child: subprocess.Popen, name: str) -> dict:
        (self.signals / f"release-{name}").write_text("go", encoding="utf-8")
        return self.outcome(child, name)

    def phase_with_two_works(self, **project):
        store = self.new_project(**project)
        roadmap = self.simple_roadmap(store)
        entry = self.simple_entry(store, roadmap.phase_ids["a"], {"w1": "W1 done", "w2": "W2 done"})
        return store, roadmap, entry


class ConcurrentWriterTests(ExecutionLockTestCase):
    def test_two_processes_starting_mutations_one_runs_and_one_is_busy(self) -> None:
        store, _, entry = self.phase_with_two_works()
        go = self.signals / "go"
        children = {
            "a": self.spawn("start_blocking", store, "a", work_id=entry.work_ids["w1"], wait_for=str(go)),
            "b": self.spawn("start_blocking", store, "b", work_id=entry.work_ids["w2"], wait_for=str(go)),
        }
        go.write_text("go", encoding="utf-8")
        deadline = time.monotonic() + WAIT_SECONDS
        while True:
            ready = [name for name in children if (self.signals / f"ready-{name}").exists()]
            ended = [name for name, child in children.items() if child.poll() is not None]
            if ready and ended:
                break
            if time.monotonic() > deadline:
                self.fail(f"no single active writer: ready={ready} ended={ended}")
            time.sleep(0.02)
        winner, loser = ready[0], ended[0]
        self.assertNotEqual(winner, loser)

        self.assertEqual(self.outcome(children[loser], loser)["code"], "project_operation_busy")
        self.assertEqual(self.release(children[winner], winner)["outcome"], "completed")
        works = {"a": entry.work_ids["w1"], "b": entry.work_ids["w2"]}
        self.assertEqual(events_of(store, works[loser]), [])
        self.assertEqual(events_of(store, works[winner]), LIFECYCLE)
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertEqual(validate_project(store), [])

    def test_the_same_start_is_not_resumed_twice_at_once(self) -> None:
        store, _, entry = self.phase_with_two_works()
        w1 = entry.work_ids["w1"]
        waiting = st.start(store, w1, "single-work", scripted_executor({w1: [st.QuestionWait("which colour?")]}))
        self.assertEqual(waiting.status, "question_wait")

        holder = self.spawn("start_blocking", store, "holder", work_id=w1)
        self.wait_ready(holder, "holder")
        before = snapshot(store)
        with self.assertRaises(ProjectOperationBusy) as ctx:
            st.start(store, w1, "single-work", completing_executor(store))
        self.assertEqual(ctx.exception.code, "project_operation_busy")
        self.assertEqual(snapshot(store), before)

        self.assertEqual(self.release(holder, "holder")["outcome"], "completed")
        self.assertEqual(events_of(store, w1), LIFECYCLE)
        self.assertEqual(MutationController(store).list_pending(), [])

    def test_different_starts_exclude_each_other(self) -> None:
        store, _, entry = self.phase_with_two_works()
        holder = self.spawn("start_blocking", store, "holder", work_id=entry.work_ids["w1"])
        self.wait_ready(holder, "holder")
        before = snapshot(store)
        with self.assertRaises(ProjectOperationBusy):
            st.start(store, entry.work_ids["w2"], "single-work", completing_executor(store))
        self.assertEqual(snapshot(store), before)
        self.assertEqual(self.release(holder, "holder")["outcome"], "completed")

        # once the holder has finished, the same request simply runs
        self.assertEqual(st.start(store, entry.work_ids["w2"], "single-work", completing_executor(store)).status, "completed")

    def test_roadmap_and_start_exclude_each_other(self) -> None:
        store, roadmap, entry = self.phase_with_two_works()
        executing = self.spawn("start_blocking", store, "start", work_id=entry.work_ids["w1"])
        self.wait_ready(executing, "start")
        before = snapshot(store)
        with self.assertRaises(ProjectOperationBusy):
            rm.hold_phase(store, roadmap.phase_ids["a"])
        self.assertEqual(snapshot(store), before)
        self.assertEqual(self.release(executing, "start")["outcome"], "completed")

        planning = self.spawn("roadmap_blocking", store, "roadmap")
        self.wait_ready(planning, "roadmap")
        before = snapshot(store)
        with self.assertRaises(ProjectOperationBusy):
            st.start(store, entry.work_ids["w2"], "single-work", completing_executor(store))
        self.assertEqual(snapshot(store), before)
        self.assertEqual(self.release(planning, "roadmap")["outcome"], "created")
        self.assertEqual(len(ProjectView.load(store).roadmaps), 2)
        self.assertEqual(MutationController(store).list_pending(), [])

    def test_a_busy_operation_writes_nothing(self) -> None:
        store, roadmap, entry = self.phase_with_two_works(remote=True)
        w2 = entry.work_ids["w2"]
        holder = self.spawn("hold_lock", store, "holder")
        self.wait_ready(holder, "holder")
        before = snapshot(store)
        remote_before = git(self.remote_path(), "rev-parse", "main").strip()
        attempts = {
            "start": lambda: st.start(store, w2, "single-work", completing_executor(store)),
            "roadmap-create": lambda: self.simple_roadmap(store),
            "phase-hold": lambda: rm.hold_phase(store, roadmap.phase_ids["a"]),
            "work-plan-exclude": lambda: rm.plan_exclude_work(store, w2),
            "related-maintenance": lambda: rm.maintain_work_related(store, w2, add=(RelatedSpec("must_read", "README.md"),)),
            "achievement": lambda: rm.evaluate_achievement(store, roadmap.roadmap_id, "achieved"),
            "create-direct": lambda: create_standalone_work(store, WorkSpec("Standalone", "standalone done")),
            "bootstrap-backfill": lambda: bs.backfill_bootstrap(store.root),
            "push-destination-pin": lambda: pin_push_destination(store.root, [self.remote_url()]),
        }
        for operation, attempt in attempts.items():
            with self.subTest(operation=operation):
                with self.assertRaises(ProjectOperationBusy) as ctx:
                    attempt()
                self.assertEqual(ctx.exception.holder["operation"], "test-holder")
        self.assertEqual(snapshot(store), before)
        self.assertEqual(git(self.remote_path(), "rev-parse", "main").strip(), remote_before)
        self.assertEqual(self.release(holder, "holder")["outcome"], "released")


class QuestionWaitAndCrashTests(ExecutionLockTestCase):
    def test_question_wait_releases_the_lock_and_keeps_the_mutation_pending(self) -> None:
        store, _, entry = self.phase_with_two_works()
        w1 = entry.work_ids["w1"]
        waiting = st.start(store, w1, "single-work", scripted_executor({w1: [st.QuestionWait("which colour?")]}))
        self.assertEqual(waiting.status, "question_wait")
        self.assertIsNone(oplock.held_lock(store))
        self.assertFalse(store.lock_holder.exists())

        # another process can take the lock while the question is open
        probe = self.spawn("hold_lock", store, "probe")
        self.wait_ready(probe, "probe")
        self.assertEqual(self.release(probe, "probe")["outcome"], "released")
        self.assertEqual([p["mutation_id"] for p in MutationController(store).list_pending()], [waiting.mutation_id])

        # an unrelated operation gets the lock and still meets the pending mutation
        with self.assertRaises(StopError) as ctx:
            self.simple_roadmap(store)
        self.assertEqual(ctx.exception.code, "reconcile_required")
        self.assertEqual(len(ProjectView.load(store).roadmaps), 1)

        resumed = st.start(store, w1, "single-work", completing_executor(store))
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(resumed.mutation_id, waiting.mutation_id)
        self.assertEqual(MutationController(store).list_pending(), [])

    def test_a_crash_releases_the_lock_and_the_pending_mutation_resumes(self) -> None:
        store, _, entry = self.phase_with_two_works()
        w1 = entry.work_ids["w1"]
        crasher = self.spawn("start_crash", store, "crasher", work_id=w1)
        out, err = crasher.communicate(timeout=WAIT_SECONDS)
        self.assertEqual(crasher.returncode, 3, out + err)
        pending = MutationController(store).list_pending()
        self.assertEqual([p["owner"] for p in pending], ["start"])
        self.assertEqual(events_of(store, w1), ["work_started", "work_target_added"])

        # no cleanup of any kind: the OS released the lock with the process
        resumed = st.start(store, w1, "single-work", completing_executor(store))
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(resumed.mutation_id, pending[0]["mutation_id"])
        self.assertEqual(events_of(store, w1), LIFECYCLE)
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertEqual(validate_project(store), [])


class OperationBoundaryTests(ExecutionLockTestCase):
    def test_child_registration_joins_the_running_operation(self) -> None:
        store = self.new_project()
        held_during: list[tuple[str, bool]] = []

        def joining(module, name):
            real = getattr(module, name)

            def call(mutation, *args, **kwargs):
                held_during.append((name, oplock.held_lock(mutation.store) is not None))
                return real(mutation, *args, **kwargs)

            return mock.patch.object(module, name, call)

        with joining(rm, "register_phases"), joining(rm, "register_works"), joining(st, "register_works"):
            roadmap = self.simple_roadmap(store)
            entry = self.simple_entry(store, roadmap.phase_ids["a"])
            w1 = entry.work_ids["w1"]
            derive = st.Derive({"fix": st.DerivedWork("Fix", "fixed")})
            outcome = st.start(store, w1, "single-work", scripted_executor({w1: [derive, st.Completed()]}))
        self.assertEqual(outcome.status, "completed")
        self.assertEqual({name for name, _ in held_during}, {"register_phases", "register_works"})
        self.assertTrue(all(held for _, held in held_during), held_during)
        self.assertIsNone(oplock.held_lock(store))

    def test_a_top_level_operation_inside_a_running_one_is_nested(self) -> None:
        store, roadmap, entry = self.phase_with_two_works()
        w1, w2 = entry.work_ids["w1"], entry.work_ids["w2"]
        refused: list[str] = []

        def executor(ctx: st.ExecutionContext):
            inner = (
                lambda: create_standalone_work(store, WorkSpec("Inner", "inner done")),
                lambda: rm.hold_phase(store, roadmap.phase_ids["a"]),
                lambda: st.start(store, w2, "single-work", completing_executor(store)),
            )
            for attempt in inner:
                try:
                    attempt()
                except ProjectOperationNested as exc:
                    refused.append(exc.code)
            (store.root / "outer.txt").write_text("outer\n", encoding="utf-8")
            return st.Completed(("outer.txt",))

        result = st.start(store, w1, "single-work", executor)
        self.assertEqual(result.status, "completed")
        self.assertEqual(refused, ["project_operation_nested"] * 3)
        view = ProjectView.load(store)
        self.assertFalse(any(work.name == "Inner" for work in view.works.values()))
        self.assertEqual(view.phase_lifecycle(roadmap.phase_ids["a"]), "active")
        self.assertEqual(events_of(store, w2), [])
        self.assertIsNone(oplock.held_lock(store))

    def test_the_mutation_controller_refuses_mutations_without_the_lock(self) -> None:
        store = self.new_project()
        controller = MutationController(store)
        invocation = {"operation": "start", "work_id": "w_x"}
        scope = WriteScope(entities=("w_x",))
        with self.assertRaises(StopError) as ctx:
            controller.open("start", invocation, scope)
        self.assertEqual(ctx.exception.code, "operation_lock_required")
        self.assertEqual(controller.list_pending(), [])

        with oplock.project_operation(store, "lock-test"):
            mutation = controller.open("start", invocation, scope)
            self.assertEqual(oplock.read_holder(store)["mutation_id"], mutation.id)
        # once the operation has returned, its mutation can no longer be written
        for write in (lambda: mutation.reserve_id("work:0", "work"), mutation.apply, mutation.complete, mutation.abandon):
            with self.assertRaises(StopError) as ctx:
                write()
            self.assertEqual(ctx.exception.code, "operation_lock_required")
        self.assertEqual([p["mutation_id"] for p in controller.list_pending()], [mutation.id])
        with oplock.project_operation(store, "lock-test"):
            mutation.abandon()
        self.assertEqual(controller.list_pending(), [])

    def test_nothing_is_created_in_a_folder_that_is_not_a_project(self) -> None:
        store = ProjectStore(self.new_dir("plain"))
        with self.assertRaises(StopError) as ctx:
            st.start(store, "w_01ARZ3NDEKTSV4RRFFQ69G5FAV", "single-work", completing_executor(store))
        self.assertEqual(ctx.exception.code, "not_a_project")
        self.assertFalse(store.workline.exists())

    def test_the_holder_description_is_diagnostic_only(self) -> None:
        store, _, entry = self.phase_with_two_works()
        w1 = entry.work_ids["w1"]
        holder = self.spawn("hold_lock", store, "holder")
        self.wait_ready(holder, "holder")
        with self.assertRaises(ProjectOperationBusy) as ctx:
            st.start(store, w1, "single-work", completing_executor(store))
        self.assertIn("test-holder", ctx.exception.message)

        # an unreadable description changes nothing: ownership is the OS lock itself
        store.lock_holder.write_text("not a description\n", encoding="utf-8")
        with self.assertRaises(ProjectOperationBusy) as ctx:
            st.start(store, w1, "single-work", completing_executor(store))
        self.assertIsNone(ctx.exception.holder)
        self.assertEqual(self.release(holder, "holder")["outcome"], "released")

        # and a stale description left behind does not block the next operation
        ghost = {"workline": oplock.HOLDER_MARKER, "version": 1, "operation": "ghost", "pid": 1}
        store.lock_holder.write_text(json.dumps(ghost), encoding="utf-8")
        self.assertEqual(st.start(store, w1, "single-work", completing_executor(store)).status, "completed")


class AchievementLockTests(ExecutionLockTestCase):
    def _completed_single_phase(self):
        store = self.new_project()
        roadmap = self.simple_roadmap(store)
        entry = self.simple_entry(store, roadmap.phase_ids["a"])
        rm.handoff(store, roadmap.phase_ids["a"], completing_executor(store), entry.entry_work_id)
        self.assertTrue(ProjectView.load(store).all_active_phases_complete(roadmap.roadmap_id))
        return store, roadmap

    def test_recording_achievement_reevaluates_the_state_under_the_lock(self) -> None:
        store, roadmap = self._completed_single_phase()
        real = rm.project_operation
        added: dict[str, str] = {}

        def plan_grows_before_the_lock(store_, operation, details=None):
            if operation == "roadmap-achievement" and not added:
                late = rm.add_phases(store, roadmap.roadmap_id, {"late": PhaseSpec("Late", "late done")})
                added.update(late.phase_ids)
            return real(store_, operation, details)

        with mock.patch.object(rm, "project_operation", plan_grows_before_the_lock):
            result = rm.evaluate_achievement(store, roadmap.roadmap_id, "achieved")
        self.assertEqual(result.status, "not_ready")
        self.assertNotIn("roadmap_achieved", [e.type for e in ProjectView.load(store).events])
        self.assertEqual(MutationController(store).list_pending(), [])

        rm.plan_exclude_phase(store, added["late"])
        achieved = rm.evaluate_achievement(store, roadmap.roadmap_id, "achieved", "checked against the desired state")
        self.assertEqual(achieved.status, "achieved")
        self.assertEqual(ProjectView.load(store).roadmap_lifecycle(roadmap.roadmap_id), "achieved")

    def test_judgements_that_record_nothing_take_no_lock(self) -> None:
        store, roadmap = self._completed_single_phase()
        holder = self.spawn("hold_lock", store, "holder")
        self.wait_ready(holder, "holder")
        for judgement, status in (
            ("human_confirmation", "human_confirmation_required"),
            ("not_achieved", "not_achieved"),
            ("desired_state_change", "desired_state_change_required"),
        ):
            with self.subTest(judgement=judgement):
                self.assertEqual(rm.evaluate_achievement(store, roadmap.roadmap_id, judgement).status, status)
        with self.assertRaises(ProjectOperationBusy):
            rm.evaluate_achievement(store, roadmap.roadmap_id, "achieved")
        self.assertEqual(self.release(holder, "holder")["outcome"], "released")


class ProjectStartAndCompatibilityTests(ExecutionLockTestCase):
    def test_project_start_stays_outside_the_execution_lock(self) -> None:
        self.assertEqual(LOCK_EXEMPT_OWNERS, (ps.OWNER,))
        root = self.new_dir()
        self.assertEqual(ps.project_start(root, WORKLINE_ROOT).status, "initialized")
        store = ProjectStore(root)
        self.assertFalse(store.locks.exists())

        # an operation running on the established Project does not make ProjectSTART busy
        holder = self.spawn("hold_lock", store, "holder")
        self.wait_ready(holder, "holder")
        self.assertEqual(ps.project_start(root, WORKLINE_ROOT).status, "already_initialized")
        self.assertEqual(self.release(holder, "holder")["outcome"], "released")

    def test_an_existing_project_works_without_any_backfill(self) -> None:
        store, _, entry = self.phase_with_two_works()
        project_yaml = store.project_yaml.read_text(encoding="utf-8")
        # a Project set up before the execution lock existed has no lock area at all
        shutil.rmtree(store.locks)
        result = st.start(store, entry.work_ids["w1"], "single-work", completing_executor(store))
        self.assertEqual(result.status, "completed")
        self.assertTrue(store.lock_file.is_file())
        self.assertEqual(store.project_yaml.read_text(encoding="utf-8"), project_yaml)
        self.assertEqual(INTENT_VERSION, 1)
        self.assertEqual([p for p in git(store.root, "ls-files").split() if p.startswith(".workline/runtime/")], [])
        for line in store.events_text().splitlines():
            self.assertEqual(set(json.loads(line)), {"id", "type", "entity", "at"})


if __name__ == "__main__":
    unittest.main()
