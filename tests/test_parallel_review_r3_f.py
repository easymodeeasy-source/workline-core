"""Parallel START, r3 findings F-02 and F-06 as negative cases (on top of the P-01..P-07 repair).

F-02: the gitlink checkout is changed (another branch checked out) between the integration check and the move; no
branch but the target may move, nothing moves at all, and the run resumes once the checkout is back.
F-06: the lock waits of an invocation are kept on its run on every way out - a question wait and a failure included.
Real Git, a real lock-holding child process.
"""

from __future__ import annotations

import subprocess
import threading

from helpers import WorklineTestCase, git
import test_parallel_repair as repair
from workline import parallel as par
from workline import start as st
from workline.errors import StopError
from workline.state import ProjectView

_HELPERS = ("_reap", "standalone", "spawn", "result", "wait_signal", "release", "events", "lifecycle",
            "assert_events_sound", "assert_released", "hold_lock", "hook", "solver_project", "solver_spec", "pointer")


class ParallelReviewR3FTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.signals = self.new_dir("signals")
        self.ws_root = self.tmp / "runs"
        self.children: list[subprocess.Popen] = []
        self.addCleanup(self._reap)

    def state(self, work_id: str) -> str:
        return ProjectView.load(self.store).work_state(work_id).state

    # F-02 ---------------------------------------------------------------------------------------------------
    def test_f02_a_branch_switched_in_after_the_check_is_never_moved(self) -> None:
        fork_remote, base = self.solver_project()
        solver = self.store.root / "solver"
        # the integration checkout is on the target branch (the J3 form); the Human also has a feature branch there
        git(solver, "checkout", "-q", "-B", "main", base)
        git(solver, "branch", "feature/human", base)
        (a,) = self.standalone("A")

        def change(ctx):
            (ctx.workspace / "engine.cpp").write_text("int v = 2;\n", encoding="utf-8")
            return st.Completed(("engine.cpp",), "feat(solver): v = 2")

        checked = par._integrate_repository

        def check_then_the_human_switches(store, record):
            refused = checked(store, record)
            git(solver, "checkout", "-q", "feature/human")  # between the check and the move
            return refused

        par._integrate_repository = check_then_the_human_switches
        try:
            with self.assertRaises(StopError) as raised:
                st.start(self.store, a, "single-work", change, parallel=True, workspace=self.solver_spec())
        finally:
            par._integrate_repository = checked
        self.assertEqual(raised.exception.code, "run_checkout_changed")
        # nothing moved: the Human's branch, the checkout, the local target branch, the Project's pointer
        self.assertEqual(git(solver, "rev-parse", "refs/heads/feature/human").strip(), base)
        self.assertEqual(git(solver, "branch", "--show-current").strip(), "feature/human")
        self.assertEqual(git(solver, "rev-parse", "HEAD").strip(), base)
        self.assertEqual(git(solver, "rev-parse", "refs/heads/main").strip(), base)
        self.assertEqual(self.pointer(), base)
        self.assertEqual(git(solver, "status", "--porcelain", "--untracked-files=no").strip(), "")
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.EXECUTED)
        self.assertEqual(record["integration"]["checkout_changed"]["now"]["symbolic"], "refs/heads/feature/human")
        self.assertEqual(self.state(a), "in_progress")
        result = record["result_commit"]
        self.assertEqual(git(fork_remote, "rev-parse", "main").strip(), result)  # the remote was reached first
        # the Human goes back; the next START checks again and moves only main, executor not run again
        git(solver, "checkout", "-q", "main")
        ran = []
        done = st.start(self.store, a, "single-work", lambda ctx: ran.append(1) or st.Completed(), parallel=True,
                        workspace=self.solver_spec())
        self.assertEqual(done.status, "completed", done.detail)
        self.assertEqual(ran, [])
        self.assertEqual(git(solver, "rev-parse", "refs/heads/main").strip(), result)
        self.assertEqual(git(solver, "branch", "--show-current").strip(), "main")
        self.assertEqual(git(solver, "rev-parse", "HEAD").strip(), result)
        self.assertEqual(git(solver, "status", "--porcelain", "--untracked-files=no").strip(), "")
        self.assertEqual(git(solver, "rev-parse", "refs/heads/feature/human").strip(), base)  # never moved
        self.assertEqual(self.pointer(), result)
        self.assertEqual(self.lifecycle(a).count("work_completed"), 1)

    def test_f02_a_detached_checkout_moved_after_the_check_is_never_moved_further(self) -> None:
        _fork_remote, base = self.solver_project()
        solver = self.store.root / "solver"
        git(solver, "branch", "feature/human", base)
        (a,) = self.standalone("A")

        def change(ctx):
            (ctx.workspace / "engine.cpp").write_text("int v = 3;\n", encoding="utf-8")
            return st.Completed(("engine.cpp",))

        checked = par._integrate_repository

        def check_then_the_human_switches(store, record):
            refused = checked(store, record)
            git(solver, "checkout", "-q", "feature/human")
            return refused

        par._integrate_repository = check_then_the_human_switches
        try:
            with self.assertRaises(StopError) as raised:
                st.start(self.store, a, "single-work", change, parallel=True, workspace=self.solver_spec())
        finally:
            par._integrate_repository = checked
        self.assertEqual(raised.exception.code, "run_checkout_changed")
        self.assertEqual(git(solver, "rev-parse", "refs/heads/feature/human").strip(), base)
        self.assertEqual(git(solver, "branch", "--show-current").strip(), "feature/human")
        self.assertEqual(self.pointer(), base)

    # F-06 ---------------------------------------------------------------------------------------------------
    def test_f06_a_question_wait_keeps_its_lock_wait_on_the_run(self) -> None:
        (a,) = self.standalone("A")
        holder = self.hold_lock("L")
        threading.Timer(1.5, self.release, args=("L",)).start()
        asked = st.start(self.store, a, "single-work", lambda ctx: st.QuestionWait("which colour?"), parallel=True,
                         workspace=par.WorkspaceSpec(root=self.ws_root))
        holder.communicate(timeout=60)
        self.assertEqual(asked.status, "question_wait")
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.QUESTION_WAIT)
        timings = record["timings"]
        self.assertGreaterEqual(timings["claim_lock_wait_s"], 1.0)  # waited for the lock, recorded as a wait
        self.assertIn("claim_s", timings)
        self.assertIn("run_s", timings)
        self.assertLess(timings["run_s"], timings["claim_lock_wait_s"])  # waiting and running are kept apart
        self.assertEqual(record["timings_history"][-1]["state"], par.QUESTION_WAIT)

    def test_f06_a_failed_executor_keeps_its_lock_wait_on_the_run(self) -> None:
        (a,) = self.standalone("A")

        def fails(ctx):
            raise RuntimeError("executor broke")

        with self.assertRaises(RuntimeError):
            st.start(self.store, a, "single-work", fails, parallel=True, workspace=par.WorkspaceSpec(root=self.ws_root))
        record = par.read_run(self.store, a)
        self.assertIn("claim_lock_wait_s", record["timings"])
        self.assertIn("claim_s", record["timings"])
        self.assertNotIn("run_s", record["timings"])  # the run never returned


for _name in _HELPERS:
    setattr(ParallelReviewR3FTests, _name, getattr(repair.ParallelRepairTests, _name))

if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
