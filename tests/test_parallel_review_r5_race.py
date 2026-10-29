"""Parallel START, r5 F-02 remaining race: a Human acts on the gitlink checkout INSIDE the move, at fixed points.

The Human's action is injected deterministically just before the move's first write ("read-tree", the working
tree / index update) or just before its ref write ("update-ref"), by wrapping the one function every Git call of
Workline goes through. The Human's commands are plain ``git`` processes, as from a terminal or a GUI. Real Git,
real files; nothing is mocked but the timing.

What must never happen: a Human branch moved, the Human's checkout (HEAD, branch, index, tracked files) changed
under a branch it does not belong to, a Human edit lost, a half-moved checkout reported as success, the executor
run again.
"""

from __future__ import annotations

import subprocess

from helpers import WorklineTestCase, git
import test_parallel_repair as repair
from workline import gitcmd
from workline import parallel as par
from workline import start as st
from workline.errors import StopError
from workline.state import ProjectView

_HELPERS = ("_reap", "standalone", "spawn", "result", "wait_signal", "release", "events", "lifecycle",
            "assert_events_sound", "assert_released", "hold_lock", "hook", "solver_project", "solver_spec", "pointer")


def human(repo, *args: str) -> subprocess.CompletedProcess:
    """A Human's own git command (not Workline's), its outcome returned as is."""
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")


class RaceTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.signals = self.new_dir("signals")
        self.ws_root = self.tmp / "runs"
        self.children: list[subprocess.Popen] = []
        self.addCleanup(self._reap)
        self.done: list[subprocess.CompletedProcess] = []

    # setup ------------------------------------------------------------------------------------------------
    def setup_solver(self, *, on_main: bool, new_file: bool = False):
        fork_remote, base = self.solver_project()
        solver = self.store.root / "solver"
        if on_main:
            git(solver, "checkout", "-q", "-B", "main", base)
        git(solver, "branch", "feature/human", base)
        (a,) = self.standalone("A")

        def change(ctx):
            (ctx.workspace / "engine.cpp").write_text("int v = 2;\n", encoding="utf-8")
            paths = ["engine.cpp"]
            if new_file:
                (ctx.workspace / "new.txt").write_text("from the Work\n", encoding="utf-8")
                paths.append("new.txt")
            return st.Completed(tuple(paths), "feat(solver): v = 2")

        return fork_remote, base, solver, a, change

    def inject(self, op: str, action) -> None:
        """Run ``action`` once, just before Workline's first git call whose arguments contain ``op`` in the checkout."""
        original = gitcmd.run_git
        fired = []

        def wrapped(repo, *args, **kwargs):
            if not fired and op in args and repo is not None and str(repo).replace("\\", "/").endswith("/solver"):
                fired.append(op)
                self.done.append(action())
            return original(repo, *args, **kwargs)

        gitcmd.run_git = wrapped
        self.addCleanup(setattr, gitcmd, "run_git", original)
        self.fired = fired

    def human_state(self, solver):
        return {"branch": human(solver, "symbolic-ref", "--quiet", "HEAD").stdout.strip(),
                "head": git(solver, "rev-parse", "HEAD").strip(),
                "feature": git(solver, "rev-parse", "refs/heads/feature/human").strip(),
                "index_engine": git(solver, "rev-parse", ":engine.cpp").strip(),
                "engine": (solver / "engine.cpp").read_text(encoding="utf-8"),
                "status": git(solver, "status", "--porcelain")}

    def start(self, a, change):
        return st.start(self.store, a, "single-work", change, parallel=True, workspace=self.solver_spec())

    def resume_after(self, a, solver, base):
        """G: the Human's checkout is back on main and clean; the next START finishes without the executor."""
        ran = []
        done = st.start(self.store, a, "single-work", lambda ctx: ran.append(1) or st.Completed(), parallel=True,
                        workspace=self.solver_spec())
        self.assertEqual(done.status, "completed", done.detail)
        self.assertEqual(ran, [])
        result = par.read_run(self.store, a)["result_commit"]
        self.assertEqual(self.pointer(), result)
        self.assertEqual(git(solver, "rev-parse", "refs/heads/feature/human").strip(), base)
        return result

    # A / B: a branch switch by the Human ------------------------------------------------------------------
    def check_switch(self, op: str, *, on_main: bool) -> None:
        _fork, base, solver, a, change = self.setup_solver(on_main=on_main)
        self.inject(op, lambda: human(solver, "checkout", "-q", "feature/human"))
        try:
            done = self.start(a, change)
        except StopError as exc:
            done = exc
        self.assertEqual(self.fired, [op])
        switched = self.done[0].returncode == 0
        print(f"RACE window={op} on_main={on_main} human_switch_rc={self.done[0].returncode} "
              f"human_stderr={self.done[0].stderr.strip()[:120]!r} workline={getattr(done, 'status', getattr(done, 'code', None))}")
        state = self.human_state(solver)
        result = par.read_run(self.store, a)["result_commit"]
        # the Human's branch is never moved
        self.assertEqual(state["feature"], base)
        if switched:
            # the Human did switch: then nothing of the result may be in their checkout
            self.assertEqual(state["branch"], "refs/heads/feature/human")
            self.assertEqual(state["head"], base)
            self.assertEqual(state["index_engine"], git(solver, "rev-parse", f"{base}:engine.cpp").strip())
            self.assertEqual(state["engine"].replace("\r\n", "\n"), "int v = 1;\n")
            self.assertEqual(state["status"], "")
            self.assertIsInstance(done, StopError)
            self.assertEqual(self.pointer(), base)
            human(solver, "checkout", "-q", "main" if on_main else base)
            self.resume_after(a, solver, base)
        else:
            # the Human's switch was refused by Git itself (the checkout's index is locked by the move)
            self.assertIn("index.lock", self.done[0].stderr)
            self.assertNotIsInstance(done, StopError)
            self.assertEqual(done.status, "completed", done.detail)
            self.assertEqual(state["head"], result)
            self.assertEqual(state["status"], "")
            self.assertEqual(self.pointer(), result)

    def test_a_switch_before_the_first_write_on_main(self) -> None:
        self.check_switch("read-tree", on_main=True)

    def test_b_switch_between_the_writes_on_main(self) -> None:
        self.check_switch("update-ref", on_main=True)

    def test_e_switch_before_the_first_write_detached(self) -> None:
        self.check_switch("read-tree", on_main=False)

    def test_e_switch_between_the_writes_detached(self) -> None:
        self.check_switch("update-ref", on_main=False)

    # C: a tracked file edited by the Human (no Git lock is involved) ---------------------------------------
    def test_c_a_human_edit_before_the_first_write_is_kept(self) -> None:
        _fork, base, solver, a, change = self.setup_solver(on_main=True)
        self.inject("read-tree", lambda: (solver / "engine.cpp").write_text("int v = 99; // mine\n", encoding="utf-8"))
        with self.assertRaises(StopError):
            self.start(a, change)
        state = self.human_state(solver)
        self.assertEqual(state["engine"], "int v = 99; // mine\n")  # the edit is kept
        self.assertEqual(state["branch"], "refs/heads/main")
        self.assertEqual(state["head"], base)  # nothing moved
        self.assertEqual(state["index_engine"], git(solver, "rev-parse", f"{base}:engine.cpp").strip())
        self.assertEqual(self.pointer(), base)
        self.assertEqual(ProjectView.load(self.store).work_state(a).state, "in_progress")
        (solver / "engine.cpp").write_text("int v = 1;\n", encoding="utf-8")  # the Human puts it back
        self.resume_after(a, solver, base)

    # D: the working tree update itself fails ---------------------------------------------------------------
    def test_d_a_failed_working_tree_update_leaves_everything_as_it_was(self) -> None:
        _fork, base, solver, a, change = self.setup_solver(on_main=True, new_file=True)
        self.inject("read-tree", lambda: (solver / "new.txt").write_text("the Human's own new file\n", encoding="utf-8"))
        with self.assertRaises(StopError):
            self.start(a, change)
        state = self.human_state(solver)
        self.assertEqual((solver / "new.txt").read_text(encoding="utf-8"), "the Human's own new file\n")
        self.assertEqual((state["branch"], state["head"]), ("refs/heads/main", base))
        self.assertEqual(git(solver, "rev-parse", "refs/heads/main").strip(), base)
        self.assertEqual(state["engine"].replace("\r\n", "\n"), "int v = 1;\n")
        self.assertEqual(state["index_engine"], git(solver, "rev-parse", f"{base}:engine.cpp").strip())
        self.assertFalse((git_dir(solver) / "index.lock").exists())
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.EXECUTED)  # the result commit is kept
        self.assertEqual(git(solver, "cat-file", "-t", record["result_commit"]).strip(), "commit")
        (solver / "new.txt").unlink()
        self.resume_after(a, solver, base)

    # F: the target branch checked out in another worktree in the window --------------------------------------
    def test_f_the_target_branch_taken_by_another_worktree_is_not_moved_under_it(self) -> None:
        _fork, base, solver, a, change = self.setup_solver(on_main=False)
        other = self.tmp / "other-wt"
        self.inject("update-ref", lambda: human(solver, "worktree", "add", "-q", str(other), "main"))
        try:
            done = self.start(a, change)
        except StopError as exc:
            done = exc
        self.assertEqual(self.done[0].returncode, 0, self.done[0].stderr)
        # the other worktree has main out: main must still be where that worktree's files are
        self.assertEqual(git(other, "rev-parse", "HEAD").strip(), git(solver, "rev-parse", "refs/heads/main").strip())
        self.assertEqual(git(other, "status", "--porcelain"), "")
        self.assertIsInstance(done, StopError)
        self.assertEqual(self.pointer(), base)
        self.assertEqual(git(solver, "rev-parse", "HEAD").strip(), base)
        self.assertEqual(git(solver, "status", "--porcelain"), "")
        human(solver, "worktree", "remove", str(other))
        self.resume_after(a, solver, base)


def git_dir(repo):
    from pathlib import Path

    return Path(git(repo, "rev-parse", "--absolute-git-dir").strip())


for _name in _HELPERS:
    setattr(RaceTests, _name, getattr(repair.ParallelRepairTests, _name))

if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
