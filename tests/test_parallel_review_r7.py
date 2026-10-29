"""Parallel START, the r7 review finding R7-F02-01: a process killed at every boundary of the checkout move's last
steps is recovered by the next START - and a lock of anyone else is never taken.

Each case kills a real child process (os._exit) at one point, then reads the real state directly - the branch, HEAD,
the index entry, the tracked file, the Project's gitlink pointer, the run record, the lock file and whose it is -
and then lets the next START recover. The executor must not run again.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from helpers import WorklineTestCase, git
import test_parallel_repair as repair
from workline import parallel as par
from workline import start as st
from workline.errors import StopError

_HELPERS = ("_reap", "standalone", "spawn", "result", "wait_signal", "release", "events", "lifecycle",
            "assert_events_sound", "assert_released", "hold_lock", "hook", "solver_project", "solver_spec", "pointer")
KILL_CHILD = Path(__file__).resolve().parent / "parallel_kill_child.py"


def human(repo, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")


class ReviewR7Tests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.signals = self.new_dir("signals")
        self.ws_root = self.tmp / "runs"
        self.children: list[subprocess.Popen] = []
        self.addCleanup(self._reap)

    def setup_solver(self):
        _fork, base = self.solver_project()
        solver = self.store.root / "solver"
        git(solver, "checkout", "-q", "-B", "main", base)
        (a,) = self.standalone("A")
        return base, solver, a

    def kill_at(self, a: str, die: str) -> subprocess.CompletedProcess:
        spec = {"root": str(self.store.root), "work_id": a, "ws_root": str(self.ws_root), "signals": str(self.signals),
                "die": die}
        path = self.signals / f"kill-{die}.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        died = subprocess.run([sys.executable, str(KILL_CHILD), str(path)], cwd=str(self.store.root),
                              capture_output=True, text=True, encoding="utf-8", timeout=300)
        self.assertEqual(died.returncode, 23, f"{die}: {died.stderr[-2000:]}")
        return died

    def state(self, solver: Path) -> dict:
        lock = solver / ".git" / "index.lock"
        return {"branch": human(solver, "symbolic-ref", "--quiet", "HEAD").stdout.strip(),
                "head": git(solver, "rev-parse", "HEAD").strip(),
                "main": git(solver, "rev-parse", "refs/heads/main").strip(),
                "index_engine": git(solver, "rev-parse", ":engine.cpp").strip(),
                "engine": (solver / "engine.cpp").read_text(encoding="utf-8").replace("\r\n", "\n"),
                "lock": lock.read_bytes()[:40] if lock.exists() else None,
                "pointer": self.pointer()}

    def resume_and_check(self, a: str, solver: Path, base: str) -> dict:
        (self.signals / "executor-ran").unlink(missing_ok=True)
        done = st.start(self.store, a, "single-work", lambda ctx: st.Completed(), parallel=True,
                        workspace=self.solver_spec())
        self.assertEqual(done.status, "completed", done.detail)
        self.assertFalse((self.signals / "executor-ran").exists())  # the executor is not run again
        record = par.read_run(self.store, a)
        result = record["result_commit"]
        after = self.state(solver)
        self.assertEqual(after["branch"], "refs/heads/main")
        self.assertEqual((after["head"], after["main"], after["pointer"]), (result, result, result))
        self.assertEqual(after["index_engine"], git(solver, "rev-parse", f"{result}:engine.cpp").strip())
        self.assertEqual(after["engine"], "int v = 2;\n")
        self.assertIsNone(after["lock"])
        self.assertEqual(git(solver, "status", "--porcelain"), "")
        self.assertNotIn("checkout_move", record["integration"])
        self.assertEqual(self.lifecycle(a).count("work_completed"), 1)
        return record

    def killed_then_recovered(self, die: str) -> dict:
        base, solver, a = self.setup_solver()
        self.kill_at(a, die)
        left = self.state(solver)
        record = par.read_run(self.store, a)
        evidence = {"die": die, "left": {k: (v.hex() if isinstance(v, bytes) else v) for k, v in left.items()},
                    "journal": (record.get("integration") or {}).get("checkout_move")}
        self.assertEqual(left["pointer"], base)  # the Project's pointer never moved before the completion
        if left["lock"] is not None:
            self.assertTrue(left["lock"].startswith(b"workline-run "), left["lock"])  # the lock still says whose it is
            refused = human(solver, "checkout", "-q", "-b", "feature/human")
            self.assertNotEqual(refused.returncode, 0)  # and keeps every Git writer out
        self.assertEqual(git(self.store.root / "solver", "cat-file", "-t", record["result_commit"]).strip(), "commit")
        self.resume_and_check(a, solver, base)
        print("R7KILL " + json.dumps(evidence, default=str))
        return evidence

    def test_killed_after_the_ref_moved(self) -> None:
        self.killed_then_recovered("after_ref")

    def test_killed_before_the_index_is_replaced(self) -> None:
        self.killed_then_recovered("before_index_replace")

    def test_killed_after_the_index_is_replaced(self) -> None:
        self.killed_then_recovered("after_index_replace")

    def test_killed_before_the_lock_is_released(self) -> None:
        self.killed_then_recovered("before_lock_release")

    def test_killed_after_the_lock_is_released(self) -> None:
        self.killed_then_recovered("after_lock_release")

    def test_a_lock_of_another_git_process_is_never_taken(self) -> None:
        base, solver, a = self.setup_solver()
        lock = solver / ".git" / "index.lock"
        lock.write_bytes(b"DIRC another git process is writing")
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work",
                     lambda ctx: ((ctx.workspace / "engine.cpp").write_text("int v = 2;\n", encoding="utf-8"),
                                  st.Completed(("engine.cpp",)))[1], parallel=True, workspace=self.solver_spec())
        self.assertEqual(raised.exception.code, "run_checkout_busy")
        self.assertEqual(lock.read_bytes(), b"DIRC another git process is writing")  # untouched
        left = self.state(solver)
        self.assertEqual((left["head"], left["main"], left["pointer"]), (base, base, base))
        lock.unlink()  # that process finishes
        self.resume_and_check(a, solver, base)

    def test_a_lock_of_a_live_workline_process_is_never_taken(self) -> None:
        base, solver, a = self.setup_solver()
        self.kill_at(a, "after_ref")
        lock = solver / ".git" / "index.lock"
        alive = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self.children.append(alive)
        import socket

        nonce = f"workline-run x pid {alive.pid} host {socket.gethostname()} id live"
        lock.write_bytes(nonce.encode("utf-8"))
        record = par.read_run(self.store, a)
        record["integration"]["checkout_move"]["lock_nonce"] = nonce
        par._save(self.store, record, take=True)
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", lambda ctx: st.Completed(), parallel=True,
                     workspace=self.solver_spec())
        self.assertEqual(raised.exception.code, "run_checkout_busy")
        self.assertEqual(lock.read_bytes(), nonce.encode("utf-8"))  # untouched while its owner lives
        alive.kill()
        alive.wait()
        self.resume_and_check(a, solver, base)


for _name in _HELPERS:
    setattr(ReviewR7Tests, _name, getattr(repair.ParallelRepairTests, _name))

if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
