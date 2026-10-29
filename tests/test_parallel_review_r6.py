"""Parallel START, the r6 independent review (F-01 BLOCKER, F-02 BLOCKER, F-03 HIGH) as negative cases.

Real Git, real files, a real process killed with os._exit. What is checked is the Human's work and what was actually
committed - never only a return code: the Human's file bytes, the checkout's branch / HEAD / index / files, the
Project's commit content, the run record, and that the executor is not run again.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from helpers import WorklineTestCase, git
import test_parallel_repair as repair
from workline import gitcmd
from workline import parallel as par
from workline import start as st
from workline.errors import StopError
from workline.state import ProjectView

_HELPERS = ("_reap", "standalone", "spawn", "result", "wait_signal", "release", "events", "lifecycle",
            "assert_events_sound", "assert_released", "hold_lock", "hook", "solver_project", "solver_spec", "pointer")
KILL_CHILD = Path(__file__).resolve().parent / "parallel_kill_child.py"


def human(repo, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")


class ReviewR6Tests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.signals = self.new_dir("signals")
        self.ws_root = self.tmp / "runs"
        self.children: list[subprocess.Popen] = []
        self.addCleanup(self._reap)

    def state(self, work_id: str) -> str:
        return ProjectView.load(self.store).work_state(work_id).state

    def checkout_state(self, solver: Path) -> dict:
        return {"branch": human(solver, "symbolic-ref", "--quiet", "HEAD").stdout.strip(),
                "head": git(solver, "rev-parse", "HEAD").strip(),
                "main": git(solver, "rev-parse", "refs/heads/main").strip(),
                "index_engine": git(solver, "rev-parse", ":engine.cpp").strip(),
                "engine": (solver / "engine.cpp").read_text(encoding="utf-8").replace("\r\n", "\n"),
                "status": git(solver, "status", "--porcelain")}

    # F-01 -------------------------------------------------------------------------------------------------
    def test_f01_a_reading_work_cannot_take_the_humans_uncommitted_work(self) -> None:
        (self.store.root / "kept.txt").write_text("the Human's own work\n", encoding="utf-8")
        tracked = self.store.root / ".gitignore"
        before_tracked = tracked.read_bytes() if tracked.exists() else None
        (a,) = self.standalone("A")
        seen = {}

        def reader_that_writes(ctx):
            seen["read"] = (ctx.workspace / "kept.txt").read_text(encoding="utf-8")  # it can read the Human's state
            seen["workspace_is_project"] = Path(ctx.workspace).resolve() == self.store.root.resolve()
            try:
                (ctx.workspace / "kept.txt").write_text("overwritten by the run\n", encoding="utf-8")
                seen["write"] = "succeeded"
            except OSError as exc:
                seen["write"] = f"refused: {type(exc).__name__}"
            return st.Completed((), "read only")

        try:
            st.start(self.store, a, "single-work", reader_that_writes, parallel=True,
                     workspace=par.WorkspaceSpec(kind="in_place", root=self.ws_root))
        except StopError:
            pass
        # the Human's file is exactly what it was; nothing of the run reached the Project
        self.assertEqual((self.store.root / "kept.txt").read_text(encoding="utf-8"), "the Human's own work\n")
        if before_tracked is not None:
            self.assertEqual(tracked.read_bytes(), before_tracked)
        self.assertEqual(seen["read"], "the Human's own work\n")
        self.assertFalse(seen["workspace_is_project"])
        self.assertTrue(seen["write"].startswith("refused"), seen)
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.RELEASED, record.get("cleanup"))
        self.assertFalse(Path(record["workspace"]["path"]).exists())  # the snapshot is gone
        self.assertNotIn(record["workspace"]["path"], git(self.store.root, "worktree", "list"))

    # F-02 -------------------------------------------------------------------------------------------------
    def solver_on_main(self):
        fork_remote, base = self.solver_project()
        solver = self.store.root / "solver"
        git(solver, "checkout", "-q", "-B", "main", base)
        (a,) = self.standalone("A")

        def change(ctx):
            (ctx.workspace / "engine.cpp").write_text("int v = 2;\n", encoding="utf-8")
            return st.Completed(("engine.cpp",), "feat(solver): v = 2")

        return fork_remote, base, solver, a, change

    def assert_back_at_base(self, solver: Path, base: str) -> None:
        state = self.checkout_state(solver)
        self.assertEqual(state["branch"], "refs/heads/main")
        self.assertEqual((state["head"], state["main"]), (base, base))
        self.assertEqual(state["index_engine"], git(solver, "rev-parse", f"{base}:engine.cpp").strip())
        self.assertEqual(state["engine"], "int v = 1;\n")
        self.assertEqual(state["status"], "")
        self.assertEqual(self.pointer(), base)

    def resume(self, a: str, solver: Path, base: str) -> None:
        ran = []
        done = st.start(self.store, a, "single-work", lambda ctx: ran.append(1) or st.Completed(), parallel=True,
                        workspace=self.solver_spec())
        self.assertEqual(done.status, "completed", done.detail)
        self.assertEqual(ran, [])
        result = par.read_run(self.store, a)["result_commit"]
        state = self.checkout_state(solver)
        self.assertEqual((state["branch"], state["head"], state["main"]), ("refs/heads/main", result, result))
        self.assertEqual(state["engine"], "int v = 2;\n")
        self.assertEqual(state["status"], "")
        self.assertEqual(self.pointer(), result)
        self.assertEqual(self.lifecycle(a).count("work_completed"), 1)

    def test_f02_a_failed_index_commit_after_the_ref_moved_is_undone(self) -> None:
        _fork, base, solver, a, change = self.solver_on_main()
        original = os.replace

        def failing(src, dst, *rest):
            if str(dst).replace("\\", "/").endswith("/.git/index") and "/solver/" in str(dst).replace("\\", "/"):
                raise OSError("injected: the index cannot be written")
            return original(src, dst, *rest)

        os.replace = failing
        try:
            with self.assertRaises(BaseException):
                st.start(self.store, a, "single-work", change, parallel=True, workspace=self.solver_spec())
        finally:
            os.replace = original
        self.assert_back_at_base(solver, base)
        self.assertFalse((solver / ".git" / "index.lock").exists())
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.EXECUTED)
        self.assertNotIn("checkout_move", record["integration"])
        self.resume(a, solver, base)

    def test_f02_a_failed_check_after_the_ref_moved_is_undone(self) -> None:
        _fork, base, solver, a, change = self.solver_on_main()
        original = gitcmd.run_git
        moved = []

        def failing(repo, *args, **kwargs):
            on_solver = repo is not None and str(repo).replace("\\", "/").endswith("/solver")
            if on_solver and moved and args[:2] == ("rev-parse", "HEAD") and len(moved) == 1:
                moved.append("failed")
                return gitcmd.GitResult(128, "", "injected: HEAD cannot be read")
            out = original(repo, *args, **kwargs)
            if on_solver and args[:2] == ("update-ref", "refs/heads/main") and not moved:
                moved.append("ref")
            return out

        gitcmd.run_git = failing
        try:
            with self.assertRaises(StopError):
                st.start(self.store, a, "single-work", change, parallel=True, workspace=self.solver_spec())
        finally:
            gitcmd.run_git = original
        self.assertEqual(moved, ["ref", "failed"])
        self.assert_back_at_base(solver, base)
        self.resume(a, solver, base)

    def test_f02_a_process_killed_after_the_ref_moved_is_recovered_by_the_next_start(self) -> None:
        _fork, base, solver, a, _change = self.solver_on_main()
        spec = {"root": str(self.store.root), "work_id": a, "ws_root": str(self.ws_root), "signals": str(self.signals)}
        path = self.signals / "kill.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        died = subprocess.run([sys.executable, str(KILL_CHILD), str(path)], cwd=str(self.store.root),
                              capture_output=True, text=True, encoding="utf-8", timeout=300)
        self.assertEqual(died.returncode, 23, died.stderr)
        # what the death left: the ref moved, the working tree moved, the index not, the lock left behind
        self.assertNotEqual(git(solver, "rev-parse", "refs/heads/main").strip(), base)
        self.assertTrue((solver / ".git" / "index.lock").exists())
        refused = human(solver, "checkout", "-q", "-b", "feature/human")
        self.assertNotEqual(refused.returncode, 0)  # Git itself keeps the Human out of the half-moved checkout
        record = par.read_run(self.store, a)
        self.assertIn(record["integration"]["checkout_move"]["phase"], ("worktree", "ref"))  # the last durable step
        (self.signals / "executor-ran").unlink()
        self.resume(a, solver, base)  # the next START undoes the half move, then moves it whole
        self.assertFalse((self.signals / "executor-ran").exists())
        self.assertFalse((solver / ".git" / "index.lock").exists())
        undone = par.read_run(self.store, a)["integration"]["checkout_undone"]
        self.assertEqual(len(undone), 1)

    def test_f02_a_human_edit_during_a_half_move_is_never_overwritten_by_the_undo(self) -> None:
        _fork, base, solver, a, _change = self.solver_on_main()
        spec = {"root": str(self.store.root), "work_id": a, "ws_root": str(self.ws_root), "signals": str(self.signals)}
        path = self.signals / "kill.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        subprocess.run([sys.executable, str(KILL_CHILD), str(path)], cwd=str(self.store.root), capture_output=True,
                       timeout=300)
        (solver / "engine.cpp").write_text("int v = 77; // the Human's\n", encoding="utf-8")  # an editor needs no lock
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", lambda ctx: st.Completed(), parallel=True, workspace=self.solver_spec())
        self.assertEqual(raised.exception.code, "run_checkout_unrecovered")
        self.assertEqual((solver / "engine.cpp").read_text(encoding="utf-8"), "int v = 77; // the Human's\n")
        record = par.read_run(self.store, a)
        self.assertIn("checkout_move", record["integration"])  # kept for the reconcile
        self.assertEqual(record["integration"]["checkout_unrecovered_paths"], ["engine.cpp"])
        self.assertEqual(self.pointer(), base)

    # F-03 -------------------------------------------------------------------------------------------------
    def test_f03_a_result_replaced_after_its_check_is_never_committed(self) -> None:
        (a,) = self.standalone("A")
        checked = par._conflicts
        swapped = []

        def then_swap(store, record, *args, **kwargs):
            out = checked(store, record, *args, **kwargs)
            (par.workspace_path(record) / "a.txt").write_text("B - swapped after the check\n", encoding="utf-8")
            swapped.append(1)
            return out

        par._conflicts = then_swap
        try:
            done = st.start(self.store, a, "single-work",
                            lambda ctx: ((ctx.workspace / "a.txt").write_text("A - what was returned\n", encoding="utf-8"),
                                         st.Completed(("a.txt",)))[1],
                            parallel=True, workspace=par.WorkspaceSpec(root=self.ws_root))
        except StopError as exc:
            done = exc
        finally:
            par._conflicts = checked
        self.assertEqual(swapped, [1])
        committed = human(self.store.root, "show", "HEAD:a.txt")
        if committed.returncode == 0:
            # whatever was committed is exactly what the executor returned
            self.assertEqual(committed.stdout.replace("\r\n", "\n"), "A - what was returned\n")
        record = par.read_run(self.store, a)
        self.assertEqual(git(self.store.root, "show", f"{record['result_commit']}:a.txt").replace("\r\n", "\n"),
                         "A - what was returned\n")

    def test_f03_a_result_replaced_before_its_check_is_never_integrated(self) -> None:
        (a,) = self.standalone("A")
        proven = par._unproven_result

        def swap_then_check(record, root):
            (Path(root) / "a.txt").write_text("B\n", encoding="utf-8")
            return proven(record, root)

        par._unproven_result = swap_then_check
        try:
            with self.assertRaises(StopError) as raised:
                st.start(self.store, a, "single-work",
                         lambda ctx: ((ctx.workspace / "a.txt").write_text("A\n", encoding="utf-8"),
                                      st.Completed(("a.txt",)))[1],
                         parallel=True, workspace=par.WorkspaceSpec(root=self.ws_root))
        finally:
            par._unproven_result = proven
        self.assertEqual(raised.exception.code, "run_outcome_unknown")
        self.assertNotEqual(human(self.store.root, "show", "HEAD:a.txt").returncode, 0)  # nothing committed
        self.assertEqual(self.state(a), "in_progress")


for _name in _HELPERS:
    setattr(ReviewR6Tests, _name, getattr(repair.ParallelRepairTests, _name))

if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
