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

        def finish(ctx):
            (ctx.workspace / "a.txt").write_text("whole\n", encoding="utf-8")
            return st.Completed(("a.txt", ".gitignore"))

        done = st.start(self.store, a, "single-work", finish, parallel=True,
                        workspace=par.WorkspaceSpec(root=self.ws_root))
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
        # nothing was committed in the workspace, so the uncommitted file blocks the release
        self.assertEqual(record["state"], par.CLEANUP_FAILED)
        self.assertTrue(Path(record["workspace"]["path"], "a.txt").exists())
        ws = Path(record["workspace"]["path"])
        git(ws, "add", "a.txt")
        git(ws, "commit", "-q", "-m", "wip")
        record = par.release(self.store, a)
        self.assertEqual(record["state"], par.PARKED)
        self.assertEqual(git(self.store.root, "rev-parse", record["refs"]["parked"]).strip(),
                         git(self.store.root, "rev-parse", record["workspace"]["branch"]).strip())
        self.assertFalse(ws.exists())

    # in place (a reading / recording Work) ------------------------------------
    def test_in_place_work_runs_beside_a_worktree_work(self) -> None:
        a, b = self.standalone("A", "B")
        child_a = self.spawn("A", a, writes={"a.txt": "A\n"}, block=True)
        self.wait_signal("entered-A-1.json")

        def record_only(ctx):
            self.assertEqual(Path(ctx.workspace), self.store.root)
            (self.store.root / "notes.md").write_text("measured\n", encoding="utf-8")
            return st.Completed(("notes.md",))

        done = st.start(self.store, b, "single-work", record_only, parallel=True,
                        workspace=par.WorkspaceSpec(kind="in_place"))
        self.assertEqual(done.status, "completed")
        self.assertIn("notes.md", git(self.store.root, "show", "--name-only", "--format=", "HEAD~1") +
                      git(self.store.root, "show", "--name-only", "--format=", "HEAD"))
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
