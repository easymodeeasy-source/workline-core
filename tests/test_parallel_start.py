"""Parallel START: a second Work begins and runs while the first one still runs or waits on a Human.

Every scenario uses one Project (one canonical event log) and real separate
processes for the Works, so nothing is proven by two Workline copies.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

from helpers import WorklineTestCase, git
from workline import parallel as par
from workline import roadmap as rm
from workline import start as st
from workline.create import WorkSpec, create_standalone_work
from workline.errors import StopError
from workline.mutation import MutationController
from workline.state import ProjectView
from workline.store import ProjectStore
from workline.validate import validate_project

CHILD = Path(__file__).resolve().parent / "parallel_child.py"


class ParallelStartTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.signals = self.new_dir("signals")
        self.ws_root = self.tmp / "runs"
        self.children: list[subprocess.Popen] = []
        self.addCleanup(self._reap)

    def _reap(self) -> None:
        for child in self.children:
            if child.poll() is None:
                child.kill()
                child.wait()

    # helpers ----------------------------------------------------------------
    def standalone(self, *names: str) -> list[str]:
        return [create_standalone_work(self.store, WorkSpec(n, f"{n} done")).work_id for n in names]

    def spawn(self, name: str, work_id: str, **spec) -> subprocess.Popen:
        spec.update(root=str(self.store.root), signal_dir=str(self.signals), name=name, work_id=work_id,
                    workspace_root=str(self.ws_root))
        path = self.signals / f"spec-{name}.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        child = subprocess.Popen([sys.executable, "-B", str(CHILD), str(path)], cwd=str(self.store.root),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        self.children.append(child)
        return child

    def result(self, child: subprocess.Popen, timeout: float = 180) -> dict:
        out, err = child.communicate(timeout=timeout)
        lines = [line for line in out.splitlines() if line.strip()]
        self.assertTrue(lines, f"child printed nothing (rc {child.returncode}): {err}")
        return json.loads(lines[-1])

    def wait_signal(self, name: str, timeout: float = 120) -> dict:
        path = self.signals / name
        deadline = time.monotonic() + timeout
        while not path.exists():
            self.assertLess(time.monotonic(), deadline, f"no signal {name}")
            time.sleep(0.02)
        time.sleep(0.05)
        return json.loads(path.read_text(encoding="utf-8"))

    def release(self, name: str) -> None:
        (self.signals / f"release-{name}").write_text("go", encoding="utf-8")

    def events(self) -> list[dict]:
        text = (self.store.root / ".workline/events/events.jsonl").read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def lifecycle(self, work_id: str) -> list[str]:
        return [e.get("type") for e in self.events() if e.get("entity") == work_id]

    def assert_events_sound(self) -> None:
        ids = [e.get("id") or e.get("event_id") for e in self.events()]
        self.assertEqual(len(ids), len(set(ids)), "duplicate event ids")
        self.assertEqual(git(self.store.root, "status", "--porcelain", "--untracked-files=no", "--", ".workline").strip(), "")
        self.assertEqual(MutationController(self.store).list_pending(), [])
        self.assertEqual(validate_project(self.store), [])

    def assert_released(self, work_id: str) -> dict:
        record = par.read_run(self.store, work_id)
        self.assertEqual(record["state"], par.RELEASED, record.get("cleanup"))
        ws = record["workspace"]
        self.assertFalse(Path(ws["path"]).exists())
        self.assertNotIn(ws["branch"], git(self.store.root, "branch", "--list"))
        self.assertEqual(git(self.store.root, "rev-parse", record["refs"]["saved"]).strip(), record["result_commit"])
        return record

    # A, C, D, E, F, M -------------------------------------------------------
    def test_work_b_starts_and_finishes_while_work_a_runs(self) -> None:
        roadmap = self.simple_roadmap(self.store)
        entry = self.simple_entry(self.store, roadmap.phase_ids["a"], {"wa": "A done", "wb": "B done"})
        a, b = entry.work_ids["wa"], entry.work_ids["wb"]
        child_a = self.spawn("A", a, writes={"a.txt": "from A\n"}, block=True, message="feat: A result")
        entered_a = self.wait_signal("entered-A-1.json")
        child_b = self.spawn("B", b, writes={"b.txt": "from B\n"}, message="feat: B result")
        entered_b = self.wait_signal("entered-B-1.json")
        out_b = self.result(child_b)
        # B's executor ran and B finished while A's executor still blocks in its own process
        self.assertEqual(out_b["status"], "completed", out_b)
        self.assertIsNone(child_a.poll())
        self.assertEqual(par.read_run(self.store, a)["state"], par.RUNNING)
        self.assertNotEqual(entered_a["pid"], entered_b["pid"])
        self.assertNotEqual(entered_a["run_id"], entered_b["run_id"])
        self.assertNotEqual(entered_a["workspace"], entered_b["workspace"])
        view = ProjectView.load(self.store)
        self.assertEqual(view.work_state(b).state, "completed")
        self.assertEqual(view.work_state(a).state, "in_progress")
        self.assertFalse((self.store.root / "a.txt").exists())  # A's unfinished work is not in the Project
        # D: a second START of A while it runs is refused - ordinary or parallel
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", lambda ctx: st.Completed())
        self.assertEqual(raised.exception.code, "work_run_active")
        dup = self.result(self.spawn("A2", a, writes={"x.txt": "x\n"}))
        self.assertEqual((dup["status"], dup["code"]), ("stop", "work_run_active"))
        self.release("A")
        out_a = self.result(child_a)
        self.assertEqual(out_a["status"], "completed", out_a)
        view = ProjectView.load(self.store)
        self.assertEqual(view.work_state(a).state, "completed")
        # C / E: each result sits in its own commit, tied to its run
        for work_id, path in ((a, "a.txt"), (b, "b.txt")):
            record = self.assert_released(work_id)
            self.assertEqual(git(self.store.root, "show", f"{record['result_commit']}:{path}").replace("\r\n", "\n"),
                             f"from {path[0].upper()}\n")
            self.assertEqual(record["integration"]["state"], "integrated")
            self.assertEqual(self.lifecycle(work_id).count("work_completed"), 1)
            self.assertEqual(self.lifecycle(work_id).count("work_started"), 1)
        log = git(self.store.root, "log", "--format=%s").splitlines()
        self.assertIn("feat: A result", log)
        self.assertIn("feat: B result", log)
        self.assertEqual(git(self.store.root, "rev-parse", "HEAD"), git(self.remote_path(), "rev-parse", "main"))
        self.assert_events_sound()
        self.assertEqual([p for p in self.ws_root.iterdir()], [])  # F

    # B ----------------------------------------------------------------------
    def test_work_b_starts_while_work_a_waits_for_a_human(self) -> None:
        a, b = self.standalone("A", "B")
        asked = st.start(self.store, a, "single-work",
                         lambda ctx: ((ctx.workspace / "a.txt").write_text("draft\n", encoding="utf-8"),
                                      st.QuestionWait("which colour?"))[1], parallel=True,
                         workspace=par.WorkspaceSpec(root=self.ws_root))
        self.assertEqual(asked.status, "question_wait")
        self.assertEqual(MutationController(self.store).list_pending(), [])  # nothing holds the ledgers
        self.assertEqual(par.read_run(self.store, a)["state"], par.QUESTION_WAIT)
        out_b = self.result(self.spawn("B", b, writes={"b.txt": "from B\n"}))
        self.assertEqual(out_b["status"], "completed", out_b)
        self.assertTrue(self.wait_signal("entered-B-1.json"))
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", lambda ctx: st.Completed())
        self.assertEqual(raised.exception.code, "work_run_active")
        seen: list[str] = []

        def answered(ctx):
            seen.append((ctx.workspace / "a.txt").read_text(encoding="utf-8"))  # the same workspace, resumed
            (ctx.workspace / "a.txt").write_text("blue\n", encoding="utf-8")
            return st.Completed(("a.txt",))

        done = st.start(self.store, a, "single-work", answered, parallel=True,
                        workspace=par.WorkspaceSpec(root=self.ws_root))
        self.assertEqual(done.status, "completed")
        self.assertEqual(seen, ["draft\n"])
        self.assertEqual(self.lifecycle(a).count("work_started"), 1)
        self.assert_released(a)
        self.assert_events_sound()

    # G ----------------------------------------------------------------------
    def test_same_file_changed_by_both_is_detected_at_integration(self) -> None:
        (self.store.root / "shared.txt").write_text("base\n", encoding="utf-8")
        git(self.store.root, "add", "shared.txt")
        git(self.store.root, "commit", "-q", "-m", "shared")
        git(self.store.root, "push", "-q", "origin", "HEAD:main")
        a, b = self.standalone("A", "B")
        child_a = self.spawn("A", a, writes={"shared.txt": "A's version\n"}, block=True)
        self.wait_signal("entered-A-1.json")
        out_b = self.result(self.spawn("B", b, writes={"shared.txt": "B's version\n"}))
        self.assertEqual(out_b["status"], "completed", out_b)
        self.release("A")
        out_a = self.result(child_a)
        self.assertEqual((out_a["status"], out_a["code"]), ("conflict", "run_conflict"), out_a)
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.CONFLICT)
        self.assertEqual(record["conflicts"], ["shared.txt"])
        # nothing of A reached the Project; A's result is kept on its branch and a parked ref, its worktree stays
        self.assertEqual((self.store.root / "shared.txt").read_text(encoding="utf-8"), "B's version\n")
        self.assertEqual(git(self.store.root, "rev-parse", record["refs"]["parked"]).strip(), record["result_commit"])
        self.assertTrue(Path(record["workspace"]["path"]).exists())
        self.assertEqual(ProjectView.load(self.store).work_state(a).state, "in_progress")
        self.assert_events_sound()

    # I ----------------------------------------------------------------------
    def test_a_work_dependency_is_not_ignored(self) -> None:
        roadmap = self.simple_roadmap(self.store)
        entry = self.simple_entry(self.store, roadmap.phase_ids["a"], {"wa": "A", "wc": "C"},
                                  requires_completion=(("wa", "wc"),), entry="wa")
        a, c = entry.work_ids["wa"], entry.work_ids["wc"]
        child_a = self.spawn("A", a, writes={"a.txt": "A\n"}, block=True)
        self.wait_signal("entered-A-1.json")
        out_c = self.result(self.spawn("C", c, writes={"c.txt": "C\n"}))
        self.assertEqual((out_c["status"], out_c["code"]), ("stop", "dependency_unsatisfied"), out_c)
        self.assertFalse((self.signals / "entered-C-1.json").exists())
        self.assertIsNone(par.read_run(self.store, c))
        self.release("A")
        self.assertEqual(self.result(child_a)["status"], "completed")
        self.assert_events_sound()

    # H ----------------------------------------------------------------------
    def test_two_finishes_at_once_are_serialized(self) -> None:
        a, b = self.standalone("A", "B")
        child_a = self.spawn("A", a, writes={"a.txt": "A\n"}, block=True)
        child_b = self.spawn("B", b, writes={"b.txt": "B\n"}, block=True)
        self.wait_signal("entered-A-1.json")
        self.wait_signal("entered-B-1.json")
        self.release("A")
        self.release("B")
        self.assertEqual(self.result(child_a)["status"], "completed")
        self.assertEqual(self.result(child_b)["status"], "completed")
        self.assert_released(a)
        self.assert_released(b)
        self.assert_events_sound()

    # J, K, L ----------------------------------------------------------------
    def test_a_crashed_work_neither_harms_the_other_nor_loses_its_files(self) -> None:
        a, b = self.standalone("A", "B")
        crashed = self.spawn("A", a, writes={"a.txt": "half\n"}, crash=True)
        crashed.communicate(timeout=120)
        self.assertEqual(crashed.returncode, 17)
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.RUNNING)
        self.assertFalse(par.pid_alive(record["pid"]))
        out_b = self.result(self.spawn("B", b, writes={"b.txt": "B\n"}))
        self.assertEqual(out_b["status"], "completed", out_b)
        self.assert_released(b)
        # the dead run is resumed in its own workspace; a build output there that is not declared regenerable
        # blocks the release instead of being deleted
        ws = Path(record["workspace"]["path"])
        self.assertEqual((ws / "a.txt").read_text(encoding="utf-8"), "half\n")
        (ws / ".gitignore").write_text("build/\n", encoding="utf-8")
        (ws / "build").mkdir()
        (ws / "build" / "out.bin").write_bytes(b"\0" * 10)

        ran = []

        def finish(ctx):
            ran.append(ctx.attempt)
            (ctx.workspace / "a.txt").write_text("whole\n", encoding="utf-8")
            return st.Completed(("a.txt", ".gitignore"))

        # R5: the owner died inside its executor - not run again until someone accepts that
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", finish, parallel=True, workspace=par.WorkspaceSpec(root=self.ws_root))
        self.assertEqual(raised.exception.code, "run_interrupted")
        self.assertEqual((ran, par.read_run(self.store, a)["state"]), ([], par.INTERRUPTED))
        par.acknowledge_interrupted(self.store, a, "test: the executor only writes its own worktree")
        done = st.start(self.store, a, "single-work", finish, parallel=True,
                        workspace=par.WorkspaceSpec(root=self.ws_root))
        self.assertEqual(ran, [2])  # run again knowingly, as its second attempt
        self.assertEqual((done.status, done.code), ("completed", "run_cleanup_incomplete"))
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.CLEANUP_FAILED)
        self.assertTrue((ws / "build" / "out.bin").exists())  # L: never deleted unasked
        self.assertEqual(ProjectView.load(self.store).work_state(a).state, "completed")
        # K: the interrupted release is found and resumed once the output is declared regenerable
        record["workspace"]["regenerable"] = ["build", "build/*"]
        par._save(self.store, record)
        self.assertEqual(par.release(self.store, a)["state"], par.RELEASED)
        self.assertFalse(ws.exists())
        self.assert_events_sound()

    def test_unintegrated_commit_is_parked_not_deleted(self) -> None:
        (a,) = self.standalone("A")
        held = st.start(self.store, a, "single-work",
                        lambda ctx: ((ctx.workspace / "a.txt").write_text("wip\n", encoding="utf-8"),
                                     st.Hold("waiting for a vendor"))[1],
                        parallel=True, workspace=par.WorkspaceSpec(root=self.ws_root))
        self.assertEqual(held.status, "held")
        record = par.read_run(self.store, a)
        # what the held run left uncommitted is kept as a WIP commit on its branch and parked ref, then released
        self.assertEqual(record["state"], par.PARKED)
        self.assertEqual(git(self.store.root, "rev-parse", record["refs"]["parked"]).strip(), record["wip_commit"])
        self.assertEqual(git(self.store.root, "rev-parse", record["refs"]["parked"]).strip(),
                         git(self.store.root, "rev-parse", record["workspace"]["branch"]).strip())
        self.assertEqual(git(self.store.root, "show", f"{record['wip_commit']}:a.txt").replace("\r\n", "\n"), "wip\n")
        self.assertFalse(Path(record["workspace"]["path"]).exists())

    # in place (a reading Work: read-only since the r3 review, P-04) -------------
    def test_in_place_work_runs_beside_a_worktree_work(self) -> None:
        a, b = self.standalone("A", "B")
        child_a = self.spawn("A", a, writes={"a.txt": "A\n"}, block=True)
        self.wait_signal("entered-A-1.json")
        seen = []

        def read_only(ctx):
            self.assertEqual(Path(ctx.workspace), self.store.root)
            seen.append(sorted(p.name for p in (self.store.root / ".workline" / "works").glob("*.md")))
            return st.Completed()

        done = st.start(self.store, b, "single-work", read_only, parallel=True,
                        workspace=par.WorkspaceSpec(kind="in_place"))
        self.assertEqual(done.status, "completed")
        self.assertEqual(len(seen[0]), 2)
        self.assertEqual(par.read_run(self.store, b)["state"], par.RELEASED)
        self.release("A")
        self.assertEqual(self.result(child_a)["status"], "completed")
        self.assert_events_sound()

    # approach S: a worktree of another repository (a Solver) ----------------------
    def test_solver_repository_worktree_keeps_its_commit_for_integration(self) -> None:
        solver = self.new_dir("solver")
        git(solver, "init", "-q", "-b", "main")
        (solver / "engine.cpp").write_text("int v = 1;\n", encoding="utf-8")
        (solver / ".gitignore").write_text("bin/\nobj/\n", encoding="utf-8")
        git(solver, "add", ".")
        git(solver, "commit", "-q", "-m", "solver base")
        base = git(solver, "rev-parse", "HEAD").strip()
        (a,) = self.standalone("A")

        def change_solver(ctx):
            (ctx.workspace / "engine.cpp").write_text("int v = 2;\n", encoding="utf-8")
            (ctx.workspace / "bin").mkdir()
            (ctx.workspace / "bin" / "solver.exe").write_bytes(b"MZ" + b"\0" * 64)  # a build output
            return st.Completed(("engine.cpp",), "feat(solver): v = 2")

        done = st.start(self.store, a, "single-work", change_solver, parallel=True,
                        workspace=par.WorkspaceSpec(repo=solver, root=self.ws_root, regenerable=("bin", "bin/*", "obj", "obj/*")))
        self.assertEqual(done.status, "completed")
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.PARKED)
        self.assertEqual(record["integration"]["state"], "pending")
        commit = record["result_commit"]
        self.assertEqual(git(solver, "rev-parse", record["refs"]["parked"]).strip(), commit)
        self.assertEqual(git(solver, "rev-parse", record["workspace"]["branch"]).strip(), commit)  # branch kept
        self.assertEqual(git(solver, "rev-parse", "main").strip(), base)  # the Solver's own branch untouched
        self.assertEqual(git(solver, "status", "--porcelain").strip(), "")
        self.assertFalse(Path(record["workspace"]["path"]).exists())
        self.assertEqual(record["integration"]["work_commit"], git(self.store.root, "rev-parse", "HEAD").strip())
        self.assertEqual(ProjectView.load(self.store).work_state(a).state, "completed")
        self.assert_events_sound()

    # B (boundary): two parallel STARTs of the same Work at once ---------------------
    def test_two_parallel_starts_of_one_work_run_its_executor_once(self) -> None:
        (a,) = self.standalone("A")
        first = self.spawn("A1", a, writes={"a.txt": "1\n"}, block=True)
        second = self.spawn("A2", a, writes={"a.txt": "2\n"}, block=True)
        deadline = time.monotonic() + 120
        while not any((self.signals / f"entered-{n}-1.json").exists() for n in ("A1", "A2")):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.05)
        time.sleep(3)  # the other one has had time to claim, be refused, or enter
        entered = [n for n in ("A1", "A2") if (self.signals / f"entered-{n}-1.json").exists()]
        self.assertEqual(len(entered), 1, entered)
        loser = "A2" if entered == ["A1"] else "A1"
        out = self.result(second if loser == "A2" else first)
        self.assertEqual((out["status"], out["code"]), ("stop", "work_run_active"), out)
        self.release(entered[0])
        self.assertEqual(self.result(first if entered == ["A1"] else second)["status"], "completed")
        self.assertEqual(self.lifecycle(a).count("work_started"), 1)
        self.assert_events_sound()

    # D (boundary): the finish dies after copying the results, before committing ----------
    def test_a_finish_that_dies_midway_is_finished_by_the_next_start(self) -> None:
        (a,) = self.standalone("A")
        dead = self.spawn("A", a, writes={"a.txt": "A\n"}, crash_after_copy=True)
        dead.communicate(timeout=120)
        self.assertEqual(dead.returncode, 19)
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.EXECUTED)  # the result is kept, nothing was confirmed
        self.assertEqual(ProjectView.load(self.store).work_state(a).state, "in_progress")
        self.assertEqual(len(MutationController(self.store).list_pending()), 1)  # the interrupted finish
        ran = []
        done = st.start(self.store, a, "single-work", lambda ctx: ran.append(1) or st.Completed(), parallel=True,
                        workspace=par.WorkspaceSpec(root=self.ws_root))
        self.assertEqual(done.status, "completed")
        self.assertEqual(ran, [])  # the executor is not run again: the recorded result is finished
        self.assertEqual(git(self.store.root, "show", "HEAD~1:a.txt").replace("\r\n", "\n"), "A\n")
        self.assertEqual(self.lifecycle(a).count("work_completed"), 1)
        self.assert_released(a)
        self.assert_events_sound()

    # parked: a held run's work is resumed, a conflict is reopened explicitly ---------------
    def test_held_work_resumes_from_its_parked_work(self) -> None:
        (a,) = self.standalone("A")
        spec = par.WorkspaceSpec(root=self.ws_root)
        held = st.start(self.store, a, "single-work",
                        lambda ctx: ((ctx.workspace / "a.txt").write_text("half\n", encoding="utf-8"),
                                     st.Hold("vendor"))[1], parallel=True, workspace=spec)
        self.assertEqual(held.status, "held")
        first = par.read_run(self.store, a)
        self.assertEqual(first["state"], par.PARKED)  # its uncommitted file became a WIP commit on the parked ref
        self.assertEqual(git(self.store.root, "show", f"{first['refs']['parked']}:a.txt").replace("\r\n", "\n"), "half\n")
        seen = []

        def resume(ctx):
            seen.append((ctx.workspace / "a.txt").read_text(encoding="utf-8"))
            (ctx.workspace / "a.txt").write_text("whole\n", encoding="utf-8")
            return st.Completed(("a.txt",))

        done = st.start(self.store, a, "single-work", resume, parallel=True, workspace=spec)
        self.assertEqual(done.status, "completed")
        self.assertEqual(seen, ["half\n"])
        second = par.read_run(self.store, a)
        self.assertEqual(second["resumed_from"]["run_id"], first["run_id"])
        self.assertEqual(second["previous_runs"][-1]["run_id"], first["run_id"])
        self.assert_released(a)
        self.assert_events_sound()

    def test_conflict_is_reopened_explicitly_and_reconciled(self) -> None:
        (self.store.root / "shared.txt").write_text("base\n", encoding="utf-8")
        git(self.store.root, "add", "shared.txt")
        git(self.store.root, "commit", "-q", "-m", "shared")
        git(self.store.root, "push", "-q", "origin", "HEAD:main")
        a, b = self.standalone("A", "B")
        spec = par.WorkspaceSpec(root=self.ws_root)
        child_a = self.spawn("A", a, writes={"shared.txt": "A\n"}, block=True)
        self.wait_signal("entered-A-1.json")
        self.assertEqual(self.result(self.spawn("B", b, writes={"shared.txt": "B\n"}))["status"], "completed")
        self.release("A")
        self.assertEqual(self.result(child_a)["status"], "conflict")
        with self.assertRaises(StopError) as raised:  # never silently re-run
            st.start(self.store, a, "single-work", lambda ctx: st.Completed(), parallel=True, workspace=spec)
        self.assertEqual(raised.exception.code, "run_conflict_parked")
        par.reopen(self.store, a)

        def reconcile(ctx):
            (ctx.workspace / "shared.txt").write_text("A and B\n", encoding="utf-8")
            return st.Completed(("shared.txt",))

        done = st.start(self.store, a, "single-work", reconcile, parallel=True, workspace=spec)
        self.assertEqual(done.status, "completed")
        self.assertEqual((self.store.root / "shared.txt").read_text(encoding="utf-8"), "A and B\n")
        self.assert_released(a)
        self.assert_events_sound()

    # approach S with integration: fork branch fast-forwarded, pushed, then the Project's gitlink ---------
    def test_solver_result_is_integrated_into_the_fork_and_the_gitlink(self) -> None:
        fork_remote = self.tmp / "solver-remote.git"
        seed = self.new_dir("solver-seed")
        git(seed, "init", "-q", "-b", "main")
        (seed / "engine.cpp").write_text("int v = 1;\n", encoding="utf-8")
        (seed / ".gitignore").write_text("bin/\n", encoding="utf-8")
        git(seed, "add", ".")
        git(seed, "commit", "-q", "-m", "solver base")
        git(self.tmp, "clone", "-q", "--bare", str(seed), str(fork_remote))
        git(self.store.root, "clone", "-q", str(fork_remote), "solver")
        base = git(self.store.root / "solver", "rev-parse", "HEAD").strip()
        git(self.store.root / "solver", "checkout", "-q", "--detach", base)
        git(self.store.root, "add", "solver")
        git(self.store.root, "commit", "-q", "-m", "solver gitlink")
        git(self.store.root, "push", "-q", "origin", "HEAD:main")
        (a,) = self.standalone("A")

        def change(ctx):
            (ctx.workspace / "engine.cpp").write_text("int v = 2;\n", encoding="utf-8")
            (ctx.workspace / "bin").mkdir()
            (ctx.workspace / "bin" / "solver.exe").write_bytes(b"MZ")
            return st.Completed(("engine.cpp",), "feat(solver): v = 2")

        spec = par.WorkspaceSpec(repo=self.store.root / "solver", root=self.ws_root, regenerable=("bin", "bin/*"),
                                 branch_prefix="feature/", integrate=par.IntegrateSpec("solver", push_remote="origin"))
        done = st.start(self.store, a, "single-work", change, parallel=True, workspace=spec)
        self.assertEqual(done.status, "completed", done.detail)
        record = par.read_run(self.store, a)
        result = record["result_commit"]
        self.assertEqual(record["state"], par.RELEASED, record.get("cleanup"))
        self.assertTrue(record["workspace"]["branch"].startswith("feature/"))
        self.assertEqual(git(fork_remote, "rev-parse", "main").strip(), result)  # the fork's main, pushed
        self.assertEqual(git(fork_remote, "rev-parse", record["workspace"]["branch"]).strip(), result)
        self.assertEqual(git(self.store.root, "rev-parse", "HEAD:solver").strip(), result)  # the Project's gitlink
        self.assertEqual(git(self.store.root, "rev-parse", "HEAD:solver"),
                         git(self.remote_path(), "rev-parse", "main:solver"))
        self.assertEqual(git(self.store.root / "solver", "rev-parse", "HEAD").strip(), result)
        self.assertEqual(git(self.store.root / "solver", "rev-parse", record["refs"]["saved"]).strip(), result)
        self.assertEqual(self.lifecycle(a).count("work_completed"), 1)
        self.assert_events_sound()

    # deps: a tree per identity, read-only, not removed while used -------------------------
    def test_deps_are_shared_only_between_the_same_identity(self) -> None:
        from workline import run_deps

        store_dir = self.tmp / "deps-store"
        src1, src2 = self.new_dir("deps1"), self.new_dir("deps2")
        (src1 / "a.h").write_text("one\n", encoding="utf-8")
        (src2 / "a.h").write_text("two\n", encoding="utf-8")
        id1 = {"ocgcore": "c1", "lua": "l1", "fetch_script": "f1", "patches": "p1"}
        id2 = dict(id1, patches="p2")  # same commits, another patch: never the same tree
        m1, m2 = run_deps.manifest(src1)[0], run_deps.manifest(src2)[0]
        with self.assertRaises(StopError):
            run_deps.adopt(store_dir, id1, src2, m1)  # the wrong bytes are refused
        run_deps.adopt(store_dir, id1, src1, m1)
        run_deps.adopt(store_dir, id2, src2, m2)
        self.assertNotEqual(run_deps.key_of(id1), run_deps.key_of(id2))
        (a,) = self.standalone("A")
        seen = {}

        def build(ctx):
            tree = par.use_deps(ctx, id1)
            seen["text"] = (tree / "a.h").read_text(encoding="utf-8")
            seen["users"] = run_deps.users(store_dir, run_deps.key_of(id1))
            with self.assertRaises(StopError):
                run_deps.remove(store_dir, run_deps.key_of(id1))  # in use: not removable
            with self.assertRaises(OSError):
                (tree / "a.h").write_text("changed\n", encoding="utf-8")  # read-only
            (ctx.workspace / "a.txt").write_text("built\n", encoding="utf-8")
            return st.Completed(("a.txt",))

        done = st.start(self.store, a, "single-work", build, parallel=True,
                        workspace=par.WorkspaceSpec(root=self.ws_root, deps_store=store_dir))
        self.assertEqual(done.status, "completed")
        self.assertEqual(seen["text"], "one\n")
        self.assertEqual(seen["users"], [par.read_run(self.store, a)["run_id"]])
        self.assertEqual(run_deps.users(store_dir, run_deps.key_of(id1)), [])  # released with the run
        run_deps.remove(store_dir, run_deps.key_of(id1))
