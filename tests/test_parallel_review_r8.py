"""Parallel START, the r8 review finding R8-F02-02: an existing checkout index.lock is taken over only when its owner is
proven gone - never when it is alive, unknown, of another host, of a malformed nonce, or held by an outer frame of
this very process.

Real Git and real files. The state that is checked directly: the lock file's bytes, whether a Human ``git checkout``
is refused, the journal, the branch / HEAD / index / file, and - for a real takeover - the result commit and that the
executor is not run again.
"""

from __future__ import annotations

import json
from pathlib import Path
import socket
import subprocess
import sys
from unittest import mock

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


class ReviewR8Tests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.signals = self.new_dir("signals")
        self.ws_root = self.tmp / "runs"
        self.children: list[subprocess.Popen] = []
        self.addCleanup(self._reap)
        self.repo = self.new_dir("checkout")
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "f.txt").write_text("1\n", encoding="utf-8")
        git(self.repo, "add", "f.txt")
        git(self.repo, "commit", "-q", "-m", "base")
        git(self.repo, "branch", "other")
        self.gitdir = self.repo / ".git"
        self.lock = self.gitdir / "index.lock"

    def record_with(self, nonce: str) -> dict:
        return {"run_id": "run_test", "integration": {"checkout_move": {"lock_nonce": nonce}}}

    def assert_refused_untouched(self, nonce: str) -> None:
        self.lock.write_bytes(nonce.encode("utf-8"))
        with self.assertRaises(StopError) as raised:
            with par._index_lock(self.gitdir, self.record_with(nonce)):
                self.fail("the lock was taken over")
        self.assertEqual(raised.exception.code, "run_checkout_busy")
        self.assertEqual(self.lock.read_bytes(), nonce.encode("utf-8"))  # never removed or rewritten
        self.assertNotEqual(human(self.repo, "checkout", "-q", "other").returncode, 0)  # Git writers stay out
        self.assertEqual(human(self.repo, "symbolic-ref", "HEAD").stdout.strip(), "refs/heads/main")

    def nonce(self, pid: int, *, host: str | None = None, started: str | None = None,
              process: str = "01M6300000000000000000PROC", lock_id: str = "01M630000000000000000LOCK0") -> str:
        return (f"workline-run run_test pid {pid} host {host or socket.gethostname()} started {started or '-'} "
                f"process {process} id {lock_id}")

    # A: an outer frame of this same process holds it --------------------------------------------------------
    def test_a_same_process_outer_holder_keeps_its_lock(self) -> None:
        with par._index_lock(self.gitdir, {"run_id": "run_test"}) as lock:
            held = lock.read_bytes().decode("utf-8")
            self.assertNotEqual(human(self.repo, "checkout", "-q", "other").returncode, 0)
            with self.assertRaises(StopError) as raised:
                with par._index_lock(self.gitdir, self.record_with(held)):
                    self.fail("an inner frame took the outer frame's lock")
            self.assertEqual(raised.exception.code, "run_checkout_busy")
            self.assertEqual(lock.read_bytes().decode("utf-8"), held)  # the outer lock is still there
            self.assertNotEqual(human(self.repo, "checkout", "-q", "other").returncode, 0)  # still protecting
        self.assertFalse(self.lock.exists())  # released by its own holder only
        self.assertEqual(human(self.repo, "checkout", "-q", "other").returncode, 0)

    # B: another host ----------------------------------------------------------------------------------------
    def test_b_another_hosts_owner_is_unknown(self) -> None:
        self.assert_refused_untouched(self.nonce(4242, host="another-host", started="1"))

    # C: the owner's state cannot be established ----------------------------------------------------------------
    def test_c_an_unknown_owner_is_never_taken_for_gone(self) -> None:
        nonce = self.nonce(4243, started="1")
        with mock.patch.object(par, "pid_state", return_value=par.UNKNOWN):
            self.assert_refused_untouched(nonce)

    # D: the owner is alive ------------------------------------------------------------------------------------
    def test_d_a_live_owner_keeps_its_lock(self) -> None:
        alive = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self.children.append(alive)
        self.assert_refused_untouched(self.nonce(alive.pid, started=par._process_started(alive.pid)))

    # E: the owner is proven dead: taken over, and released by the new holder ------------------------------------
    def test_e_a_dead_owner_is_taken_over(self) -> None:
        gone = subprocess.Popen([sys.executable, "-c", "pass"])
        started = par._process_started(gone.pid)
        gone.wait()
        nonce = self.nonce(gone.pid, started=started)
        self.lock.write_bytes(nonce.encode("utf-8"))
        with par._index_lock(self.gitdir, self.record_with(nonce)) as lock:
            self.assertEqual(lock.read_bytes().decode("utf-8"), nonce)
            self.assertNotEqual(human(self.repo, "checkout", "-q", "other").returncode, 0)
        self.assertFalse(self.lock.exists())

    # F: malformed nonces ---------------------------------------------------------------------------------------
    def test_f_malformed_nonces_are_never_taken_over(self) -> None:
        for nonce in ("workline-run run_test pid 1 host x id y",  # the r8 form: no start time, no process id
                      "workline-run garbage",
                      self.nonce(0, started="1").replace("pid 0", "pid zero"),
                      self.nonce(4244) + " extra"):
            with self.subTest(nonce=nonce):
                self.assert_refused_untouched(nonce)
        self.assert_refused_untouched(self.nonce(4245))  # no start time: a reused pid could not be told apart

    # H: the real START path - a dead owner's half move is recovered; the executor is not run again ----------------
    def test_h_a_killed_start_is_recovered_through_start(self) -> None:
        _fork, base = self.solver_project()
        solver = self.store.root / "solver"
        git(solver, "checkout", "-q", "-B", "main", base)
        (a,) = self.standalone("A")
        spec = {"root": str(self.store.root), "work_id": a, "ws_root": str(self.ws_root), "signals": str(self.signals),
                "die": "before_index_replace"}
        path = self.signals / "kill.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        died = subprocess.run([sys.executable, str(KILL_CHILD), str(path)], cwd=str(self.store.root),
                              capture_output=True, text=True, encoding="utf-8", timeout=300)
        self.assertEqual(died.returncode, 23, died.stderr[-2000:])
        held = (solver / ".git" / "index.lock").read_text(encoding="utf-8")
        self.assertEqual(par._lock_owner_state(held), par.DEAD)
        (self.signals / "executor-ran").unlink(missing_ok=True)
        done = st.start(self.store, a, "single-work", lambda ctx: st.Completed(), parallel=True,
                        workspace=self.solver_spec())
        self.assertEqual(done.status, "completed", done.detail)
        self.assertFalse((self.signals / "executor-ran").exists())
        result = par.read_run(self.store, a)["result_commit"]
        self.assertEqual(git(solver, "rev-parse", "HEAD").strip(), result)
        self.assertEqual(git(solver, "status", "--porcelain"), "")
        self.assertEqual(self.pointer(), result)
        self.assertFalse((solver / ".git" / "index.lock").exists())


for _name in _HELPERS:
    setattr(ReviewR8Tests, _name, getattr(repair.ParallelRepairTests, _name))

if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
