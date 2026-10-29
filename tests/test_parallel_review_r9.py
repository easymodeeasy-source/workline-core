"""Parallel START, the r9 review: R9-01 (the in-process windows of taking and releasing a checkout index.lock) and
R9-02 (malformed owner fields read as dead).

R9-01 is driven deterministically: a second thread is started exactly inside the first thread's window (right after
the nonce is written / right before the lock is removed) and given a second to act; what is checked is whether the
second thread got the lock while the first still had it, whether the lock file still exists while a holder lives, and
whether a Human ``git checkout`` is refused for as long as any holder lives. Real Git, real files, real threads.
"""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import threading

from helpers import WorklineTestCase, git
from workline import parallel as par
from workline.errors import StopError

ULID_A = "01M6300000000000000000PROC"
ULID_B = "01M630000000000000000LOCK0"


def human(repo, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")


class ReviewR9Tests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.repo = self.new_dir("checkout")
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "f.txt").write_text("1\n", encoding="utf-8")
        git(self.repo, "add", "f.txt")
        git(self.repo, "commit", "-q", "-m", "base")
        git(self.repo, "branch", "other")
        self.gitdir = self.repo / ".git"
        self.lock = self.gitdir / "index.lock"
        self.children: list[subprocess.Popen] = []
        self.addCleanup(lambda: [c.kill() for c in self.children if c.poll() is None])

    def record_with(self, nonce: str) -> dict:
        return {"run_id": "run_test", "integration": {"checkout_move": {"lock_nonce": nonce}}}

    def second_holder(self, nonce_of) -> tuple[threading.Thread, dict, threading.Event]:
        """A thread that tries to take the lock with the nonce the first holder wrote and, if it gets it, holds it."""
        out, release = {}, threading.Event()

        def run():
            try:
                with par._index_lock(self.gitdir, self.record_with(nonce_of())):
                    out["got"] = True
                    out["checkout_while_second_holds"] = None
                    release.wait(30)
            except StopError as exc:
                out["refused"] = exc.code

        return threading.Thread(target=run, daemon=True), out, release

    # R9-01: the window between writing the nonce and registering the holder -----------------------------------
    def test_r9_01_a_second_thread_in_the_take_window_never_gets_the_lock(self) -> None:
        write = os.write
        state = {}

        def write_then_race(fd, data):
            n = write(fd, data)
            if b"workline-run" in data and "thread" not in state:
                thread, out, release = self.second_holder(lambda: self.lock.read_bytes().decode("utf-8"))
                state.update(thread=thread, out=out, release=release)
                thread.start()
                thread.join(1.0)  # the second thread acts inside the first thread's window
            return n

        os.write = write_then_race
        try:
            with par._index_lock(self.gitdir, {"run_id": "run_test"}):
                state["thread"].join(5.0)
                self.assertNotIn("got", state["out"], "a second thread took the lock its owner still holds")
                self.assertTrue(self.lock.exists())
                self.assertNotEqual(human(self.repo, "checkout", "-q", "other").returncode, 0)
        finally:
            os.write = write
            if "release" in state:
                state["release"].set()
        state["thread"].join(5.0)
        self.assertEqual(state["out"].get("refused"), "run_checkout_busy")
        self.assertFalse(self.lock.exists())

    # R9-01: the window between unregistering the holder and removing the lock -----------------------------------
    def test_r9_01_a_lock_is_never_removed_from_under_a_second_holder(self) -> None:
        unlink = Path.unlink
        state = {}
        holder_nonce = {}

        def race_then_unlink(path, *args, **kwargs):
            if path.name == "index.lock" and "thread" not in state:
                thread, out, release = self.second_holder(lambda: holder_nonce["n"])
                state.update(thread=thread, out=out, release=release)
                thread.start()
                thread.join(1.0)  # the second thread acts inside the first thread's release
            return unlink(path, *args, **kwargs)

        Path.unlink = race_then_unlink
        try:
            with par._index_lock(self.gitdir, {"run_id": "run_test"}) as lock:
                holder_nonce["n"] = lock.read_bytes().decode("utf-8")
            Path.unlink = unlink
            state["thread"].join(2.0)
            if state["out"].get("got"):
                # whoever holds the lock now, it must exist and keep Git writers out while held
                self.assertTrue(self.lock.exists(), "the lock was removed from under its live holder")
                self.assertNotEqual(human(self.repo, "checkout", "-q", "other").returncode, 0)
        finally:
            Path.unlink = unlink
            state["release"].set()
        state["thread"].join(5.0)
        self.assertFalse(self.lock.exists())

    # R9-02: malformed owner fields are unknown, never dead ---------------------------------------------------------
    def nonce(self, pid: str, started: str, *, process: str = ULID_A, lock_id: str = ULID_B) -> str:
        return f"workline-run run_test pid {pid} host {socket.gethostname()} started {started} process {process} id {lock_id}"

    def assert_refused_untouched(self, nonce: str) -> None:
        self.lock.write_bytes(nonce.encode("utf-8"))
        with self.assertRaises(StopError) as raised:
            with par._index_lock(self.gitdir, self.record_with(nonce)):
                self.fail("taken over")
        self.assertEqual(raised.exception.code, "run_checkout_busy")
        self.assertEqual(self.lock.read_bytes(), nonce.encode("utf-8"))
        self.assertNotEqual(human(self.repo, "checkout", "-q", "other").returncode, 0)
        self.lock.unlink()

    def test_r9_02_malformed_owner_fields_are_never_dead(self) -> None:
        cases = {
            "pid zero": self.nonce("0", "1"),
            "pid with a sign": self.nonce("+12", "1"),
            "pid with leading zeros": self.nonce("0012", "1"),
            "pid far out of range": self.nonce("99999999999", "1"),
            "start time zero": self.nonce("4242", "0"),
            "start time not a number": self.nonce("4242", "abc"),
            "start time negative": self.nonce("4242", "-5"),
            "process id malformed": self.nonce("4242", "1", process="x"),
            "lock id malformed": self.nonce("4242", "1", lock_id="y"),
        }
        for name, nonce in cases.items():
            with self.subTest(name):
                self.assertEqual(par._lock_owner_state(nonce), par.UNKNOWN, nonce)
                self.assert_refused_untouched(nonce)

    def test_r9_02_a_live_pid_with_a_later_recorded_start_is_unknown(self) -> None:
        alive = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self.children.append(alive)
        started = par._process_started(alive.pid)
        self.assertEqual(par._lock_owner_state(self.nonce(str(alive.pid), started)), par.ALIVE)
        later = str(int(started) + 10_000_000)  # a start after the running process's own: inconsistent
        self.assertEqual(par._lock_owner_state(self.nonce(str(alive.pid), later)), par.UNKNOWN)
        self.assert_refused_untouched(self.nonce(str(alive.pid), later))
        earlier = str(int(started) - 10_000_000)  # the pid was reused after the writer: the writer is gone
        self.assertEqual(par._lock_owner_state(self.nonce(str(alive.pid), earlier)), par.DEAD)

    def test_r9_02_a_dead_owner_is_still_taken_over(self) -> None:
        gone = subprocess.Popen([sys.executable, "-c", "pass"])
        started = par._process_started(gone.pid)
        gone.wait()
        nonce = self.nonce(str(gone.pid), started)
        self.lock.write_bytes(nonce.encode("utf-8"))
        with par._index_lock(self.gitdir, self.record_with(nonce)):
            self.assertNotEqual(human(self.repo, "checkout", "-q", "other").returncode, 0)
        self.assertFalse(self.lock.exists())


if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
