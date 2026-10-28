"""Parallel START, one-pass safety repair (R1-R10): the negative cases a parallel START must refuse or survive.

Same conventions as ``test_parallel_start``: one Project, real child processes where a crash or a second process
is the point. Every case states what must NOT happen (a second executor run, a moved pointer, a lost file).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest import mock

from helpers import WorklineTestCase, git
import test_parallel_start as base
from workline import mutation
from workline import parallel as par
from workline import start as st
from workline import status
from workline.errors import ProjectOperationBusy, StopError, ValidationError
from workline.state import ProjectView

LOCK_CHILD = Path(__file__).resolve().parent / "lock_child.py"


class ParallelRepairTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.signals = self.new_dir("signals")
        self.ws_root = self.tmp / "runs"
        self.children: list[subprocess.Popen] = []
        self.addCleanup(self._reap)

    _reap = base.ParallelStartTests._reap
    standalone = base.ParallelStartTests.standalone
    spawn = base.ParallelStartTests.spawn
    result = base.ParallelStartTests.result
    wait_signal = base.ParallelStartTests.wait_signal
    release = base.ParallelStartTests.release
    events = base.ParallelStartTests.events
    lifecycle = base.ParallelStartTests.lifecycle
    assert_events_sound = base.ParallelStartTests.assert_events_sound
    assert_released = base.ParallelStartTests.assert_released

    # helpers ----------------------------------------------------------------
    def hold_lock(self, name: str) -> subprocess.Popen:
        spec = {"scenario": "hold_lock", "root": str(self.store.root), "name": name, "signal_dir": str(self.signals)}
        path = self.signals / f"lock-{name}.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        child = subprocess.Popen([sys.executable, str(LOCK_CHILD), str(path)], cwd=str(self.store.root),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        self.children.append(child)
        deadline = time.monotonic() + 60
        while not (self.signals / f"ready-{name}").exists():
            self.assertLess(time.monotonic(), deadline, "the lock holder never got the lock")
            time.sleep(0.02)
        return child

    def solver_project(self) -> tuple[Path, str]:
        """A Solver fork (bare remote + clone) held by the Project as the gitlink ``solver`` at its base commit."""
        fork_remote = self.tmp / "solver-remote.git"
        seed = self.new_dir("solver-seed")
        git(seed, "init", "-q", "-b", "main")
        (seed / "engine.cpp").write_text("int v = 1;\n", encoding="utf-8")
        (seed / ".gitignore").write_text("bin/\n", encoding="utf-8")
        git(seed, "add", ".")
        git(seed, "commit", "-q", "-m", "solver base")
        git(self.tmp, "clone", "-q", "--bare", str(seed), str(fork_remote))
        git(self.store.root, "clone", "-q", str(fork_remote), "solver")
        solver_base = git(self.store.root / "solver", "rev-parse", "HEAD").strip()
        git(self.store.root / "solver", "checkout", "-q", "--detach", solver_base)
        git(self.store.root, "add", "solver")
        git(self.store.root, "commit", "-q", "-m", "solver gitlink")
        git(self.store.root, "push", "-q", "origin", "HEAD:main")
        return fork_remote, solver_base

    def solver_spec(self, **extra) -> par.WorkspaceSpec:
        return par.WorkspaceSpec(repo=self.store.root / "solver", root=self.ws_root, regenerable=("bin", "bin/*"),
                                 branch_prefix="feature/", integrate=par.IntegrateSpec("solver", push_remote="origin"),
                                 **extra)

    def hook(self, git_dir: Path, name: str, body: str) -> Path:
        path = git_dir / "hooks" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("#!/bin/sh\n" + body + "\n").encode("utf-8"))
        os.chmod(path, 0o755)
        return path

    def pointer(self) -> str:
        return git(self.store.root, "rev-parse", "HEAD:solver").strip()

    # R1 -------------------------------------------------------------------
    def test_r1_detach_from_an_ordinary_start_is_an_unknown_outcome(self) -> None:
        (a,) = self.standalone("A")
        head = git(self.store.root, "rev-parse", "HEAD").strip()
        with self.assertRaises(ValidationError) as raised:
            st.start(self.store, a, "single-work", lambda ctx: st.Detach())
        self.assertIn("unknown outcome", str(raised.exception))
        self.assertIsNone(par.read_run(self.store, a))
        self.assertEqual(git(self.store.root, "rev-parse", "HEAD").strip(), head)  # no detached "start" commit

    def test_r1_an_executor_returning_detach_in_a_parallel_run_is_refused(self) -> None:
        (a,) = self.standalone("A")
        calls = []
        with self.assertRaises(ValidationError) as raised:
            st.start(self.store, a, "single-work", lambda ctx: calls.append(1) or st.Detach(), parallel=True,
                     workspace=par.WorkspaceSpec(root=self.ws_root))
        self.assertEqual(raised.exception.code, "parallel_detach_refused")
        self.assertEqual(calls, [1])  # once, not in a loop
        self.assertEqual(par.read_run(self.store, a)["state"], par.FAILED)

    # R2 -------------------------------------------------------------------
    def test_r2_a_nested_repository_is_never_read_as_a_gitlink(self) -> None:
        nested = self.store.root / "nested"
        git(self.store.root, "init", "-q", "-b", "main", "nested")
        (nested / "n.txt").write_text("n\n", encoding="utf-8")
        git(nested, "add", ".")
        git(nested, "commit", "-q", "-m", "nested")
        head = git(nested, "rev-parse", "HEAD").strip()
        self.assertIsNone(mutation._content_digest(nested))  # .git alone proves nothing
        with mutation.allow_gitlink(self.store.root, "nested", head):
            self.assertIsNone(mutation._content_digest(nested))  # not a mode-160000 entry of the index
        (a,) = self.standalone("A")
        # exactly as on the production base 225f278: the Work completes and the nested repository is not committed
        # (candidate 9e0c8fd read it as a gitlink and would have added it as an embedded repository)
        out = st.start(self.store, a, "single-work", lambda ctx: st.Completed(("nested",)))
        self.assertEqual(out.status, "completed")
        self.assertEqual(git(self.store.root, "ls-files", "--stage", "--", "nested").strip(), "")

    def test_r2_r1_an_ordinary_start_still_cannot_carry_a_gitlink(self) -> None:
        self.solver_project()
        checkout = self.store.root / "solver"
        (checkout / "engine.cpp").write_text("int v = 3;\n", encoding="utf-8")
        git(checkout, "commit", "-q", "-am", "moved by hand")
        moved = git(checkout, "rev-parse", "HEAD").strip()
        before = self.pointer()
        self.assertIsNone(mutation._content_digest(checkout))  # CHG-0003: ordinary START reads no gitlink
        with mutation.allow_gitlink(self.store.root, "solver", moved):
            self.assertEqual(mutation._content_digest(checkout), "gitlink:" + moved)  # the parallel finish only
        with mutation.allow_gitlink(self.store.root, "solver", "0" * 40):
            self.assertIsNone(mutation._content_digest(checkout))  # another commit than declared: unreadable
        (a,) = self.standalone("A")
        with self.assertRaises(Exception):
            st.start(self.store, a, "single-work", lambda ctx: st.Completed(("solver",)))
        self.assertEqual(self.pointer(), before)

    def test_r2_integration_into_a_plain_directory_is_refused(self) -> None:
        self.solver_project()
        (self.store.root / "plain").mkdir()
        (self.store.root / "plain" / "f.txt").write_text("f\n", encoding="utf-8")
        git(self.store.root, "add", "plain")
        git(self.store.root, "commit", "-q", "-m", "plain dir")
        (a,) = self.standalone("A")
        spec = par.WorkspaceSpec(repo=self.store.root / "solver", root=self.ws_root, branch_prefix="feature/",
                                 integrate=par.IntegrateSpec("plain", push_remote="origin"))
        done = st.start(self.store, a, "single-work",
                        lambda ctx: ((ctx.workspace / "engine.cpp").write_text("x\n", encoding="utf-8"),
                                     st.Completed(("engine.cpp",)))[1], parallel=True, workspace=spec)
        self.assertEqual((done.status, done.code), ("conflict", "run_conflict"))
        self.assertIn("mode 160000", par.read_run(self.store, a)["conflicts"][0])
        self.assertEqual(ProjectView.load(self.store).work_state(a).state, "in_progress")

    # R3 -------------------------------------------------------------------
    def test_r3_pid_state_never_takes_an_unprovable_owner_for_gone(self) -> None:
        self.assertEqual(par.pid_state(os.getpid()), par.ALIVE)
        self.assertEqual(par.pid_state(os.getpid(), started="another process"), par.DEAD)  # a reused pid
        done = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True)
        self.assertEqual(par.pid_state(int(done.stdout)), par.DEAD)
        if sys.platform == "win32":
            class Kernel32:
                def OpenProcess(self, *args):
                    return 0

            for error, expected in ((5, par.UNKNOWN), (87, par.DEAD), (31, par.UNKNOWN)):
                with mock.patch("ctypes.WinDLL", lambda *a, **k: Kernel32()), \
                        mock.patch("ctypes.get_last_error", lambda: error):
                    self.assertEqual(par.pid_state(999999), expected, error)

    def test_r3_an_owner_on_another_host_blocks_until_a_human_declares_it_gone(self) -> None:
        (a,) = self.standalone("A")
        crashed = self.spawn("A", a, writes={"a.txt": "half\n"}, crash=True)
        crashed.communicate(timeout=120)
        record = par.read_run(self.store, a)
        record["owner"]["host"] = record["host"] = "elsewhere.invalid"
        par._write(self.store, record)
        ran = []

        def finish(ctx):
            ran.append(ctx.attempt)
            return st.Completed(("a.txt",))

        spec = par.WorkspaceSpec(root=self.ws_root)
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", finish, parallel=True, workspace=spec)
        self.assertEqual(raised.exception.code, "run_owner_unknown")
        self.assertEqual(par.status_projection(self.store)[0]["owner"]["state"], par.UNKNOWN)
        par.declare_owner_gone(self.store, a, record["run_id"], "test: that host is a fixture")
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", finish, parallel=True, workspace=spec)
        self.assertEqual(raised.exception.code, "run_interrupted")  # gone, but its executor was mid-run
        self.assertEqual(ran, [])
        par.acknowledge_interrupted(self.store, a, "test: rerun is safe")
        self.assertEqual(st.start(self.store, a, "single-work", finish, parallel=True, workspace=spec).status, "completed")
        self.assertEqual(ran, [2])
        self.assertEqual(self.lifecycle(a).count("work_started"), 1)

    def test_r3_a_claim_interrupted_after_its_commit_is_claimed_again_without_a_second_start(self) -> None:
        (a,) = self.standalone("A")
        dead = self.spawn("A", a, writes={"a.txt": "A\n"}, crash_after_claim=True)
        dead.communicate(timeout=120)
        self.assertEqual(dead.returncode, 23)
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.CLAIMING)
        self.assertEqual(self.lifecycle(a).count("work_started"), 1)  # the claim's commit happened
        out = self.result(self.spawn("A2", a, writes={"a.txt": "A\n"}))
        self.assertEqual(out["status"], "completed", out)
        self.assertEqual(self.lifecycle(a).count("work_started"), 1)
        self.assertEqual(self.lifecycle(a).count("work_completed"), 1)
        final = par.read_run(self.store, a)
        self.assertEqual(final["previous_runs"][-1]["run_id"], record["run_id"])
        self.assert_released(a)
        self.assert_events_sound()

    def test_r3_r9_a_record_taken_over_is_never_overwritten_by_its_old_owner(self) -> None:
        (a,) = self.standalone("A")
        st.start(self.store, a, "single-work", lambda ctx: st.QuestionWait("q"), parallel=True,
                 workspace=par.WorkspaceSpec(root=self.ws_root))
        stale = par.read_run(self.store, a)
        taken = par.read_run(self.store, a)
        taken["owner"] = dict(taken["owner"], nonce="another-owner", pid=1)
        par._write(self.store, taken)
        with self.assertRaises(StopError) as raised:
            par._set(self.store, stale, par.RUNNING)
        self.assertEqual(raised.exception.code, "run_owner_changed")
        self.assertEqual(par.read_run(self.store, a)["owner"]["nonce"], "another-owner")

    # R4 -------------------------------------------------------------------
    def test_r4_a_question_wait_is_visible_to_status_and_to_the_next_start(self) -> None:
        (a,) = self.standalone("A")
        spec = par.WorkspaceSpec(root=self.ws_root)
        st.start(self.store, a, "single-work",
                 lambda ctx: ((ctx.workspace / "a.txt").write_text("draft\n", encoding="utf-8"),
                              st.QuestionWait("which colour?"))[1], parallel=True, workspace=spec)
        model = status.build_status(self.store.root)
        runs = model.data["parallel_runs"]
        self.assertEqual(runs["waiting_for_human"], [a])
        self.assertEqual(runs["runs"][0]["question"], "which colour?")
        self.assertEqual(model.data["pending"]["status"], status.PENDING_NONE)  # not a canonical pending mutation
        self.assertIn("waits for a Human: which colour?", status.render_human(model))
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", lambda ctx: st.Completed())
        self.assertEqual(raised.exception.code, "work_run_active")
        self.assertIn("which colour?", str(raised.exception))
        seen = []

        def answered(ctx):
            seen.append((ctx.workspace / "a.txt").read_text(encoding="utf-8"))
            (ctx.workspace / "a.txt").write_text("blue\n", encoding="utf-8")
            return st.Completed(("a.txt",))

        self.assertEqual(st.start(self.store, a, "single-work", answered, parallel=True, workspace=spec).status, "completed")
        self.assertEqual(seen, ["draft\n"])
        self.assertEqual(self.lifecycle(a).count("work_started"), 1)
        self.assertEqual(status.build_status(self.store.root).data["parallel_runs"]["waiting_for_human"], [])

    def test_r4_status_is_unchanged_for_a_project_without_parallel_runs(self) -> None:
        self.assertNotIn("parallel_runs", status.build_status(self.store.root).data)

    # R5 -------------------------------------------------------------------
    def test_r5_a_crash_after_the_executor_returned_is_finished_without_running_it_again(self) -> None:
        (a,) = self.standalone("A")
        dead = self.spawn("A", a, writes={"a.txt": "from A\n"}, crash_after_return=True)
        dead.communicate(timeout=120)
        self.assertEqual(dead.returncode, 29)
        self.assertEqual(par.read_run(self.store, a)["state"], par.RETURNED)
        ran = []
        done = st.start(self.store, a, "single-work", lambda ctx: ran.append(1) or st.Completed(), parallel=True,
                        workspace=par.WorkspaceSpec(root=self.ws_root))
        self.assertEqual(done.status, "completed")
        self.assertEqual(ran, [])
        record = self.assert_released(a)
        self.assertEqual(record.get("recovered_from"), par.RETURNED)
        self.assertEqual(git(self.store.root, "show", f"{record['result_commit']}:a.txt").replace("\r\n", "\n"), "from A\n")
        self.assert_events_sound()

    def test_r5_one_acknowledgement_allows_one_rerun(self) -> None:
        (a,) = self.standalone("A")
        self.spawn("A", a, writes={"a.txt": "1\n"}, crash=True).communicate(timeout=120)
        with self.assertRaises(StopError):
            par.run(self.store, a, lambda ctx: st.Completed(), par.WorkspaceSpec(root=self.ws_root))
        par.acknowledge_interrupted(self.store, a, "test: first rerun")
        again = self.spawn("A2", a, writes={"a.txt": "2\n"}, crash=True)  # the acknowledged rerun dies too
        again.communicate(timeout=120)
        self.assertEqual(again.returncode, 17)
        ran = []
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", lambda ctx: ran.append(1) or st.Completed(), parallel=True,
                     workspace=par.WorkspaceSpec(root=self.ws_root))
        self.assertEqual(raised.exception.code, "run_interrupted")  # the first acknowledgement was used up
        self.assertEqual(ran, [])
        self.assertEqual(len(par.read_run(self.store, a)["resumed_after_interruption"]), 1)

    def test_r5_a_returned_result_that_cannot_be_proven_stops_for_a_human(self) -> None:
        (a,) = self.standalone("A")
        dead = self.spawn("A", a, writes={"a.txt": "from A\n"}, crash_after_return=True)
        dead.communicate(timeout=120)
        ws = Path(par.read_run(self.store, a)["workspace"]["path"])
        (ws / "a.txt").unlink()
        ran = []
        for _ in range(2):  # and it stays stopped
            with self.assertRaises(StopError) as raised:
                st.start(self.store, a, "single-work", lambda ctx: ran.append(1) or st.Completed(), parallel=True,
                         workspace=par.WorkspaceSpec(root=self.ws_root))
            self.assertEqual(raised.exception.code, "run_outcome_unknown")
        self.assertEqual(ran, [])
        record = par.read_run(self.store, a)
        self.assertEqual((record["state"], record["next_actor"]), (par.OUTCOME_UNKNOWN, "human"))
        self.assertEqual(ProjectView.load(self.store).work_state(a).state, "in_progress")

    # R6 -------------------------------------------------------------------
    def test_r6_base_drift_reaches_the_result_commit_and_status(self) -> None:
        a, b = self.standalone("A", "B")
        child_a = self.spawn("A", a, writes={"dir/y.txt": "A\n"}, block=True)
        self.wait_signal("entered-A-1.json")
        self.assertEqual(self.result(self.spawn("B", b, writes={"dir/x.txt": "B\n", "other.txt": "o\n"}))["status"],
                         "completed")
        self.release("A")
        out = self.result(child_a)
        self.assertEqual((out["status"], out["code"]), ("completed", "integrated_with_base_drift"), out)
        integration = par.read_run(self.store, a)["integration"]
        self.assertEqual(integration["base_drift"], ["dir/x.txt", "other.txt"])
        self.assertEqual(integration["drift"]["near_result"], ["dir/x.txt"])
        self.assertEqual(integration["drift"]["eligibility"], "reverify_near_result")
        self.assertFalse(integration["drift"]["verified_together"])
        messages = git(self.store.root, "log", "-n", "4", "--format=%B")
        self.assertIn("Workline-Base-Drift: dir/x.txt, other.txt", messages)
        self.assertIn("Workline-Base-Drift-Near-Result: dir/x.txt", messages)
        self.assertIn("Workline-Integration: mechanical", messages)
        shown = {r["work_id"]: r for r in status.build_status(self.store.root).data["parallel_runs"]["runs"]}
        self.assertEqual(shown[a]["integration"]["base_drift"], ["dir/x.txt", "other.txt"])
        self.assert_events_sound()

    # R7 -------------------------------------------------------------------
    def test_r7_a_refusing_commit_hook_is_obeyed_and_the_result_kept(self) -> None:
        self.solver_project()
        guard = ('W=$(cat "$(git rev-parse --absolute-git-dir)/guard-work" 2>/dev/null)\n'
                 'if [ -z "$W" ]; then echo "REFUSED: no Work is named for this worktree"; exit 1; fi')
        self.hook(self.store.root / "solver" / ".git", "pre-commit", guard)
        (a,) = self.standalone("A")
        ran = []

        def change(ctx):
            ran.append(ctx.attempt)
            (ctx.workspace / "engine.cpp").write_text("int v = 2;\n", encoding="utf-8")
            return st.Completed(("engine.cpp",), "feat(solver): v = 2")

        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", change, parallel=True, workspace=self.solver_spec())
        self.assertIn("REFUSED", str(raised.exception))  # the hook ran: nothing was bypassed
        record = par.read_run(self.store, a)
        self.assertEqual((record["state"], record["next_actor"]), (par.RETURNED, "human"))
        ws = Path(record["workspace"]["path"])
        self.assertEqual((ws / "engine.cpp").read_text(encoding="utf-8"), "int v = 2;\n")  # the result is kept
        # the Project names the Work for this worktree's guard; the next START commits without running it again
        gitdir = Path(git(ws, "rev-parse", "--absolute-git-dir").strip())
        (gitdir / "guard-work").write_text(a + "\n", encoding="utf-8")
        done = st.start(self.store, a, "single-work", change, parallel=True, workspace=self.solver_spec())
        self.assertEqual(done.status, "completed", done.detail)
        self.assertEqual(ran, [1])
        self.assertEqual(self.pointer(), par.read_run(self.store, a)["result_commit"])

    def test_r7_prepare_names_the_work_before_the_executor_runs(self) -> None:
        self.solver_project()
        guard = ('W=$(cat "$(git rev-parse --absolute-git-dir)/guard-work" 2>/dev/null)\n'
                 'if [ -z "$W" ]; then echo "REFUSED"; exit 1; fi')
        self.hook(self.store.root / "solver" / ".git", "pre-commit", guard)
        self.hook(self.store.root / "solver" / ".git", "pre-push", guard)
        (a,) = self.standalone("A")

        def name_the_work(worktree: Path, record: dict) -> None:
            gitdir = Path(git(worktree, "rev-parse", "--absolute-git-dir").strip())
            (gitdir / "guard-work").write_text(record["work_id"] + "\n", encoding="utf-8")

        done = st.start(self.store, a, "single-work",
                        lambda ctx: ((ctx.workspace / "engine.cpp").write_text("int v = 4;\n", encoding="utf-8"),
                                     st.Completed(("engine.cpp",)))[1], parallel=True,
                        workspace=self.solver_spec(prepare=name_the_work))
        self.assertEqual(done.status, "completed", done.detail)
        record = par.read_run(self.store, a)
        self.assertEqual(record["integration"]["stages"]["pushed"]["from"], record["workspace"]["path"])  # pushed from it

    # R8 -------------------------------------------------------------------
    def test_r8_a_refused_push_leaves_the_pointer_and_resumes(self) -> None:
        fork_remote, solver_base = self.solver_project()
        refuse = self.hook(fork_remote, "pre-receive", "echo rejected-for-test; exit 1")
        (a,) = self.standalone("A")
        ran = []

        def change(ctx):
            ran.append(1)
            (ctx.workspace / "engine.cpp").write_text("int v = 5;\n", encoding="utf-8")
            return st.Completed(("engine.cpp",))

        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", change, parallel=True, workspace=self.solver_spec())
        self.assertEqual(raised.exception.code, "run_push_failed")
        record = par.read_run(self.store, a)
        self.assertEqual((record["state"], record["integration"]["state"]), (par.EXECUTED, "repository_ahead"))
        self.assertEqual(self.pointer(), solver_base)  # the Project never names an unreached commit
        self.assertEqual(git(self.remote_path(), "rev-parse", "main:solver").strip(), solver_base)
        refuse.unlink()
        self.assertEqual(st.start(self.store, a, "single-work", change, parallel=True, workspace=self.solver_spec()).status,
                         "completed")
        self.assertEqual(ran, [1])
        self.assertEqual(self.pointer(), record["result_commit"])

    def test_r8_an_exit_code_is_not_arrival(self) -> None:
        fork_remote, solver_base = self.solver_project()
        # the remote accepts the push, then puts main back: the push "succeeds" and main never reaches the result
        undo = self.hook(fork_remote, "post-receive", f"git update-ref refs/heads/main {solver_base}")
        (a,) = self.standalone("A")
        change = lambda ctx: ((ctx.workspace / "engine.cpp").write_text("int v = 6;\n", encoding="utf-8"),  # noqa: E731
                              st.Completed(("engine.cpp",)))[1]
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", change, parallel=True, workspace=self.solver_spec())
        self.assertEqual(raised.exception.code, "run_remote_unreached")
        record = par.read_run(self.store, a)
        self.assertEqual(record["integration"]["state"], "repository_unreached")
        self.assertEqual(record["integration"]["remote_seen"]["main"], solver_base)
        self.assertEqual(self.pointer(), solver_base)
        undo.unlink()
        self.assertEqual(st.start(self.store, a, "single-work", change, parallel=True, workspace=self.solver_spec()).status,
                         "completed")
        self.assertEqual(git(fork_remote, "rev-parse", "main").strip(), record["result_commit"])
        self.assertEqual(self.pointer(), record["result_commit"])

    # R9 -------------------------------------------------------------------
    def test_r9_the_claim_retry_expires_and_writes_nothing(self) -> None:
        (a,) = self.standalone("A")
        self.hold_lock("H")
        head = git(self.store.root, "rev-parse", "HEAD").strip()
        called = []
        t0 = time.monotonic()
        with self.assertRaises(ProjectOperationBusy):
            par.run(self.store, a, lambda ctx: called.append(1), par.WorkspaceSpec(root=self.ws_root), lock_wait=1.0)
        self.assertGreaterEqual(time.monotonic() - t0, 1.0)
        self.assertEqual(called, [])
        self.assertIsNone(par.read_run(self.store, a))
        self.assertEqual(git(self.store.root, "rev-parse", "HEAD").strip(), head)
        self.assertNotIn("work_started", self.lifecycle(a))

    def test_r9_an_expired_finish_keeps_the_result_and_the_next_start_finishes_it(self) -> None:
        (a,) = self.standalone("A")
        child = self.spawn("A", a, writes={"a.txt": "A\n"}, block=True, lock_wait=1.0)
        self.wait_signal("entered-A-1.json")
        holder = self.hold_lock("H")
        self.release("A")
        out = self.result(child)
        self.assertEqual((out["status"], out["code"]), ("stop", "project_operation_busy"), out)
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.EXECUTED)
        self.assertIn("ProjectOperationBusy", record["finish_error"])
        self.release("H")
        holder.communicate(timeout=60)
        ran = []
        done = st.start(self.store, a, "single-work", lambda ctx: ran.append(1) or st.Completed(), parallel=True,
                        workspace=par.WorkspaceSpec(root=self.ws_root))
        self.assertEqual((done.status, ran), ("completed", []))
        self.assert_released(a)

    # R10 ------------------------------------------------------------------
    def test_r10_a_parking_release_keeps_small_wip_and_stops_on_large_files(self) -> None:
        a, b = self.standalone("A", "B")
        spec = par.WorkspaceSpec(root=self.ws_root, regenerable=("cache", "cache/*"))

        def hold(ctx):
            (ctx.workspace / ".gitignore").write_text("cache/\n", encoding="utf-8")
            (ctx.workspace / "cache").mkdir()
            (ctx.workspace / "cache" / "c.bin").write_bytes(b"c" * 5)  # ignored: never part of the WIP
            (ctx.workspace / "notes.txt").write_text("note\n", encoding="utf-8")
            (ctx.workspace / "big.bin").write_bytes(b"\0" * 64)
            return st.Hold("vendor")

        with mock.patch.object(par, "WIP_FILE_LIMIT", 32):
            held = st.start(self.store, a, "single-work", hold, parallel=True, workspace=spec)
        self.assertEqual((held.status, held.code), ("held", "run_cleanup_incomplete"))
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.CLEANUP_FAILED)
        self.assertIn("big.bin", " ".join(record["cleanup"]["blocked"]))
        ws = Path(record["workspace"]["path"])
        self.assertTrue((ws / "big.bin").exists() and (ws / "notes.txt").exists())  # nothing lost
        # another Work is not affected by A's stopped cleanup
        self.assertEqual(st.start(self.store, b, "single-work",
                                  lambda ctx: ((ctx.workspace / "b.txt").write_text("B\n", encoding="utf-8"),
                                               st.Completed(("b.txt",)))[1], parallel=True, workspace=spec).status,
                         "completed")
        released = par.release(self.store, a)  # within the limits now: kept as WIP and parked
        self.assertEqual(released["state"], par.PARKED, released.get("cleanup"))
        self.assertEqual(sorted(released["wip_untracked"]), [".gitignore", "big.bin", "notes.txt"])
        kept = git(self.store.root, "ls-tree", "-r", "--name-only", released["refs"]["parked"]).split()
        self.assertIn("big.bin", kept)
        self.assertNotIn("cache/c.bin", kept)
        self.assertFalse(ws.exists())
