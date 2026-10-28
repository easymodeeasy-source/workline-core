"""Parallel START, independent review of r3 (8193d98): the seven reproductions P-01 to P-07 as negative cases.

Same conventions as ``test_parallel_repair``: one Project, real child processes or threads where a second process,
a second thread or a crash is the point, a real remote where a push refusal is. Every case states what must NOT
happen (a second executor run, a result taken for another, a Work in progress without its run, a lost result, a
tree removed while in use, a path cut apart, an unproven commit finished over).
"""

from __future__ import annotations

from pathlib import Path
import threading
from unittest import mock

import subprocess

from helpers import WorklineTestCase, git
import test_parallel_repair as repair
from workline import parallel as par
from workline import run_deps
from workline import start as st
from workline import status
from workline.errors import ProjectOperationBusy, StopError, ValidationError
from workline.state import ProjectView

_HELPERS = ("_reap", "standalone", "spawn", "result", "wait_signal", "release", "events", "lifecycle",
            "assert_events_sound", "assert_released", "hold_lock", "hook")


class ParallelReviewR3Tests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.signals = self.new_dir("signals")
        self.ws_root = self.tmp / "runs"
        self.children: list[subprocess.Popen] = []
        self.addCleanup(self._reap)

    def head(self) -> str:
        return git(self.store.root, "rev-parse", "HEAD").strip()

    def state(self, work_id: str) -> str:
        return ProjectView.load(self.store).work_state(work_id).state

    # P-01 same-Work ownership -------------------------------------------------------------------------------
    def test_p01_a_second_thread_of_the_same_process_never_runs_the_work(self) -> None:
        (a,) = self.standalone("A")
        spec = par.WorkspaceSpec(root=self.ws_root)
        entered, go = threading.Event(), threading.Event()
        ran, out = [], {}

        def slow(ctx):
            ran.append(threading.get_ident())
            entered.set()
            go.wait(120)
            (ctx.workspace / "a.txt").write_text("A\n", encoding="utf-8")
            return st.Completed(("a.txt",))

        first = threading.Thread(target=lambda: out.setdefault(
            "first", st.start(self.store, a, "single-work", slow, parallel=True, workspace=spec)))
        first.start()
        try:
            self.assertTrue(entered.wait(120))
            refused = []

            def again(call):
                try:
                    refused.append(call())
                except StopError as exc:
                    refused.append(exc)

            # the same START from another thread, and - below the invocation guard - the record's own owner check
            for call in (lambda: st.start(self.store, a, "single-work", slow, parallel=True, workspace=spec),
                         lambda: par._run(self.store, a, slow, spec, 5.0)):
                other = threading.Thread(target=again, args=(call,))
                other.start()
                other.join(120)
            self.assertEqual([getattr(r, "code", r) for r in refused], ["work_run_active", "work_run_active"])
            self.assertIn("another thread of this process", str(refused[0]))
            self.assertEqual(par.owner_state(par.read_run(self.store, a)), par.ALIVE)
            with self.assertRaises(StopError) as raised:  # nor an ordinary START, from this thread
                st.start(self.store, a, "single-work", lambda ctx: st.Completed())
            self.assertEqual(raised.exception.code, "work_run_active")
        finally:
            go.set()
            first.join(180)
        self.assertEqual(out["first"].status, "completed")
        self.assertEqual(len(ran), 1)  # one executor run, in the first thread
        self.assertEqual(self.lifecycle(a).count("work_started"), 1)
        self.assert_released(a)
        self.assert_events_sound()

    def test_p01_a_run_entered_again_from_its_own_executor_is_refused(self) -> None:
        (a,) = self.standalone("A")
        spec = par.WorkspaceSpec(root=self.ws_root)
        inner = []

        def reenter(ctx):
            for parallel in (True, False):
                try:
                    st.start(self.store, a, "single-work", lambda c: st.Completed(), parallel=parallel,
                             workspace=spec if parallel else None)
                    inner.append((parallel, "ran", ""))
                except StopError as exc:
                    inner.append((parallel, exc.code, str(exc)))
            (ctx.workspace / "a.txt").write_text("A\n", encoding="utf-8")
            return st.Completed(("a.txt",))

        done = st.start(self.store, a, "single-work", reenter, parallel=True, workspace=spec)
        self.assertEqual(done.status, "completed", done.detail)
        self.assertEqual([code for _, code, _ in inner], ["work_run_active", "work_run_active"])
        self.assertIn("from inside its own run", inner[0][2])
        self.assertEqual(self.lifecycle(a).count("work_started"), 1)
        self.assert_events_sound()

    def test_p01_an_ended_invocation_is_resumed_by_another_process_while_its_own_lives(self) -> None:
        (a,) = self.standalone("A")
        holder = []

        def then_hold_the_lock(ctx):
            (ctx.workspace / "a.txt").write_text("A\n", encoding="utf-8")
            holder.append(self.hold_lock("H"))  # the finish of this invocation will find the lock taken
            return st.Completed(("a.txt",))

        with self.assertRaises(ProjectOperationBusy):
            par.run(self.store, a, then_hold_the_lock, par.WorkspaceSpec(root=self.ws_root), lock_wait=1.0)
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.EXECUTED)
        self.release("H")
        holder[0].communicate(timeout=60)
        # this process lives on; another process resumes the run without waiting for it to exit
        out = self.result(self.spawn("A2", a, writes={"a.txt": "not run\n"}))
        self.assertEqual(out["status"], "completed", out)
        self.assertTrue(record["owner"].get("ended_at"))  # because its invocation said it ended
        self.assertFalse(list(self.signals.glob("entered-A2-*.json")))  # finished from the record, not run again
        final = self.assert_released(a)
        self.assertEqual(git(self.store.root, "show", f"{final['result_commit']}:a.txt").replace("\r\n", "\n"), "A\n")

    # P-02 RETURNED result identity --------------------------------------------------------------------------
    def test_p02_a_result_changed_or_replaced_after_the_return_is_never_taken_for_it(self) -> None:
        a, b = self.standalone("A", "B")
        for work, name in ((a, "A"), (b, "B")):
            dead = self.spawn(name, work, writes={"r.txt": "returned\n"}, crash_after_return=True)
            dead.communicate(timeout=120)
            self.assertEqual(dead.returncode, 29)
        ws_a = Path(par.read_run(self.store, a)["workspace"]["path"])
        (ws_a / "r.txt").write_text("changed after the return\n", encoding="utf-8")  # same path, other bytes
        ws_b = Path(par.read_run(self.store, b)["workspace"]["path"])
        (ws_b / "r.txt").unlink()
        (ws_b / "r.txt").mkdir()  # replaced by a directory of the same name
        (ws_b / "r.txt" / "inner.txt").write_text("returned\n", encoding="utf-8")
        head, ran = self.head(), []
        for work in (a, b):
            for _ in range(2):  # and it stays stopped
                with self.assertRaises(StopError) as raised:
                    st.start(self.store, work, "single-work", lambda ctx: ran.append(1) or st.Completed(),
                             parallel=True, workspace=par.WorkspaceSpec(root=self.ws_root))
                self.assertEqual(raised.exception.code, "run_outcome_unknown")
            record = par.read_run(self.store, work)
            self.assertEqual((record["state"], record["next_actor"]), (par.OUTCOME_UNKNOWN, "human"))
            self.assertIn("is not what the executor returned", record["unknown"][0])
            self.assertIsNone(record.get("result_commit"))
            self.assertEqual(self.state(work), "in_progress")
            self.assertTrue(record["outcome"]["identity"]["r.txt"].startswith("file:"))  # recorded at the return
        self.assertEqual(ran, [])
        self.assertEqual(self.head(), head)

    def test_p02_an_executed_result_changed_before_its_finish_is_not_integrated(self) -> None:
        (a,) = self.standalone("A")
        holder = []

        def then_hold_the_lock(ctx):
            (ctx.workspace / "a.txt").write_text("returned\n", encoding="utf-8")
            holder.append(self.hold_lock("H"))
            return st.Completed(("a.txt",))

        with self.assertRaises(ProjectOperationBusy):
            par.run(self.store, a, then_hold_the_lock, par.WorkspaceSpec(root=self.ws_root), lock_wait=1.0)
        self.release("H")
        holder[0].communicate(timeout=60)
        ws = Path(par.read_run(self.store, a)["workspace"]["path"])
        (ws / "a.txt").write_text("edited before the finish\n", encoding="utf-8")
        head = self.head()
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", lambda ctx: st.Completed(), parallel=True,
                     workspace=par.WorkspaceSpec(root=self.ws_root))
        self.assertEqual(raised.exception.code, "run_outcome_unknown")
        self.assertEqual(self.head(), head)
        self.assertFalse((self.store.root / "a.txt").exists())  # nothing copied into the Project
        self.assertEqual(par.read_run(self.store, a)["state"], par.OUTCOME_UNKNOWN)

    # P-03 claim record preservation -------------------------------------------------------------------------
    def test_p03_a_claim_whose_push_the_remote_refuses_keeps_its_run_record(self) -> None:
        (a,) = self.standalone("A")
        spec = par.WorkspaceSpec(root=self.ws_root)
        before = self.head()
        refuse = self.hook(self.remote_path(), "pre-receive", "echo rejected-for-test; exit 1")
        ran = []

        def work(ctx):
            ran.append(ctx.attempt)
            (ctx.workspace / "a.txt").write_text("A\n", encoding="utf-8")
            return st.Completed(("a.txt",))

        with self.assertRaises(Exception) as raised:
            st.start(self.store, a, "single-work", work, parallel=True, workspace=spec)
        self.assertIn("rejected-for-test", str(raised.exception))
        self.assertEqual(ran, [])
        self.assertNotEqual(self.head(), before)  # the claim's commit was made; its push was refused
        self.assertEqual(self.state(a), "in_progress")
        record = par.read_run(self.store, a)
        self.assertIsNotNone(record, "a Work in progress lost the run record that holds it")
        self.assertEqual((record["state"], record["next_actor"]), (par.CLAIMING, "start"))
        self.assertTrue(any(item.startswith("HEAD moved") for item in record["claim_error"]["left"]))
        self.assertEqual(status.build_status(self.store.root).data["parallel_runs"]["runs"][0]["state"], par.CLAIMING)
        with self.assertRaises(Exception):  # nothing else runs the Work meanwhile
            st.start(self.store, a, "single-work", lambda ctx: ran.append("ordinary") or st.Completed())
        self.assertEqual(ran, [])
        self.assertEqual(par.read_run(self.store, a)["run_id"], record["run_id"])
        refuse.unlink()
        done = st.start(self.store, a, "single-work", work, parallel=True, workspace=spec)
        self.assertEqual(done.status, "completed", done.detail)
        self.assertEqual(ran, [1])
        self.assertEqual(self.lifecycle(a).count("work_started"), 1)
        self.assertEqual(self.lifecycle(a).count("work_completed"), 1)
        self.assertEqual(git(self.remote_path(), "rev-parse", "main").strip(), self.head())
        self.assertEqual(par.read_run(self.store, a)["previous_runs"][-1]["run_id"], record["run_id"])
        self.assert_released(a)
        self.assert_events_sound()

    # (a claim refused before it writes anything still leaves no record: test_parallel_start's
    # test_a_work_dependency_is_not_ignored)

    # P-04 in-place isolation --------------------------------------------------------------------------------
    def test_p04_two_in_place_works_writing_one_file_never_both_complete(self) -> None:
        a, b = self.standalone("A", "B")
        head, codes = self.head(), []

        def write(text):
            def executor(ctx):
                (ctx.workspace / "shared.txt").write_text(text, encoding="utf-8")
                return st.Completed(("shared.txt",))
            return executor

        def a_writes_while_b_writes(ctx):
            try:  # B runs and finishes inside A's run: two in-place Works on one Project folder at once
                st.start(self.store, b, "single-work", write("from B\n"), parallel=True,
                         workspace=par.WorkspaceSpec(kind="in_place"))
            except ValidationError as exc:
                codes.append(exc.code)
            return write("from A\n")(ctx)

        with self.assertRaises(ValidationError) as raised:
            st.start(self.store, a, "single-work", a_writes_while_b_writes, parallel=True,
                     workspace=par.WorkspaceSpec(kind="in_place"))
        codes.append(raised.exception.code)
        self.assertEqual(codes, ["parallel_in_place_read_only", "parallel_in_place_read_only"])
        for work in (a, b):
            self.assertEqual(par.read_run(self.store, work)["state"], par.FAILED)
            self.assertEqual(self.state(work), "in_progress")
            self.assertNotIn("work_completed", self.lifecycle(work))
        self.assertNotIn("shared.txt", git(self.store.root, "ls-tree", "--name-only", "HEAD"))
        self.assertEqual(git(self.store.root, "rev-list", "--count", f"{head}..HEAD").strip(), "2")  # the claims only

    def test_p04_an_in_place_work_that_writes_without_saying_so_is_not_finished(self) -> None:
        a, b = self.standalone("A", "B")
        (self.store.root / "kept.txt").write_text("a Human's draft\n", encoding="utf-8")  # untracked before the run

        def reads(ctx):
            return st.Completed()

        done = st.start(self.store, a, "single-work", lambda ctx: (ctx.workspace / "kept.txt").read_text() and reads(ctx),
                        parallel=True, workspace=par.WorkspaceSpec(kind="in_place"))
        self.assertEqual(done.status, "completed", done.detail)  # a reading Work runs in place

        def stray(ctx):
            (ctx.workspace / "stray.txt").write_text("written in place\n", encoding="utf-8")
            (ctx.workspace / "kept.txt").write_text("overwritten\n", encoding="utf-8")
            return st.Completed()

        with self.assertRaises(StopError) as raised:
            st.start(self.store, b, "single-work", stray, parallel=True, workspace=par.WorkspaceSpec(kind="in_place"))
        self.assertEqual(raised.exception.code, "run_project_written")
        written = par.read_run(self.store, b)["project_written"]
        self.assertIn("folder:stray.txt", written)
        self.assertIn("folder:kept.txt", written)
        self.assertEqual(self.state(b), "in_progress")

    # P-05 shared deps ---------------------------------------------------------------------------------------
    def deps_entry(self) -> tuple[Path, dict, str]:
        store_dir, source = self.new_dir("deps-store"), self.new_dir("deps-src")
        (source / "core.h").write_text("int core;\n", encoding="utf-8")
        identity = {"ocgcore": "abc123", "lua": "5.4.6"}
        run_deps.adopt(store_dir, identity, source, run_deps.manifest(source)[0])
        return store_dir, identity, run_deps.key_of(identity)

    def test_p05_a_removal_never_comes_between_a_use_check_and_its_record(self) -> None:
        store_dir, identity, key = self.deps_entry()
        checked, go, got, removed = threading.Event(), threading.Event(), [], []
        manifest = run_deps.manifest

        def checked_then_wait(tree, exclude=()):
            found = manifest(tree, exclude)
            checked.set()  # the acquire has checked the tree; its use is not recorded yet
            go.wait(60)
            return found

        def remove():
            try:
                run_deps.remove(store_dir, key)
                removed.append("removed")
            except StopError as exc:
                removed.append(exc.code)

        with mock.patch.object(run_deps, "manifest", checked_then_wait):
            user = threading.Thread(target=lambda: got.append(run_deps.acquire(store_dir, identity, "run_X")))
            user.start()
            self.assertTrue(checked.wait(60))
            remover = threading.Thread(target=remove)
            remover.start()
            remover.join(1.5)
            self.assertTrue(remover.is_alive(), "the removal did not wait for the use being registered")
            go.set()
            user.join(60)
            remover.join(60)
        self.assertEqual(removed, ["deps_in_use"])
        self.assertEqual((got[0] / "core.h").read_text(encoding="utf-8"), "int core;\n")
        self.assertEqual(run_deps.users(store_dir, key), ["run_X"])

    def test_p05_an_acquire_never_returns_a_tree_a_removal_is_deleting(self) -> None:
        store_dir, identity, key = self.deps_entry()
        checked, go, got = threading.Event(), threading.Event(), []
        users = run_deps.users

        def none_yet_then_wait(store, k):
            found = users(store, k)
            checked.set()  # the removal has seen no user; the entry is not deleted yet
            go.wait(60)
            return found

        def acquire():
            try:
                got.append(run_deps.acquire(store_dir, identity, "run_Y"))
            except StopError as exc:
                got.append(exc.code)

        with mock.patch.object(run_deps, "users", none_yet_then_wait):
            remover = threading.Thread(target=lambda: run_deps.remove(store_dir, key))
            remover.start()
            self.assertTrue(checked.wait(60))
            user = threading.Thread(target=acquire)
            user.start()
            user.join(1.5)
            self.assertTrue(user.is_alive(), "the acquire did not wait for the removal")
            go.set()
            remover.join(60)
            user.join(60)
        self.assertEqual(got, ["deps_missing"])  # never a tree that is being deleted
        self.assertFalse((store_dir / key).exists())
        run_deps.adopt(store_dir, identity, self.tmp / "deps-src", run_deps.manifest(self.tmp / "deps-src")[0])
        self.assertTrue(run_deps.acquire(store_dir, identity, "run_Z").is_dir())  # adopted again, used again

    # P-06 base drift paths ----------------------------------------------------------------------------------
    def test_p06_base_drift_keeps_paths_with_spaces_and_non_ascii_exactly(self) -> None:
        a, b = self.standalone("A", "B")
        names = ["dir/x y.txt", "spaced  dir/z.txt", "日本語 ファイル.txt"]
        child_a = self.spawn("A", a, writes={"dir/y.txt": "A\n"}, block=True)
        self.wait_signal("entered-A-1.json")
        out_b = self.result(self.spawn("B", b, writes={n: "B\n" for n in names}))
        self.assertEqual(out_b["status"], "completed", out_b)
        self.release("A")
        out = self.result(child_a)
        self.assertEqual((out["status"], out["code"]), ("completed", "integrated_with_base_drift"), out)
        integration = par.read_run(self.store, a)["integration"]
        self.assertEqual(integration["base_drift"], sorted(names))
        self.assertEqual(integration["drift"]["near_result"], ["dir/x y.txt"])
        self.assertEqual(integration["drift"]["eligibility"], "reverify_near_result")
        messages = git(self.store.root, "log", "-n", "4", "--format=%B")
        self.assertIn("Workline-Base-Drift: " + ", ".join(sorted(names)), messages)
        self.assert_events_sound()

    # P-07 canonical write provenance ------------------------------------------------------------------------
    def test_p07_an_executor_committing_canonical_files_is_not_finished(self) -> None:
        a, b = self.standalone("A", "B")
        work_file = next((self.store.root / ".workline" / "works").glob("*.md"))
        rel = work_file.relative_to(self.store.root).as_posix()
        made = []

        def trespass(ctx):
            # another Work completes meanwhile through Workline: a legitimate change, never refused
            st.start(self.store, b, "single-work",
                     lambda c: ((self.store.root / "b.txt").write_text("B\n", encoding="utf-8"),
                                st.Completed(("b.txt",)))[1])
            with open(work_file, "a", encoding="utf-8") as f:
                f.write("\nwritten and committed by an executor without the lock\n")
            git(self.store.root, "commit", "-q", "-m", "executor commit", "--", rel)
            made.append(self.head())
            (ctx.workspace / "a.txt").write_text("A\n", encoding="utf-8")
            return st.Completed(("a.txt",))

        spec = par.WorkspaceSpec(root=self.ws_root)
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", trespass, parallel=True, workspace=spec)
        self.assertEqual(raised.exception.code, "run_project_written")
        self.assertEqual(git(self.store.root, "status", "--porcelain", "--", ".workline/works").strip(), "")  # clean
        record = par.read_run(self.store, a)
        written = record["project_written"]
        self.assertEqual([w.split(" ")[0] for w in written], [f"commit:{made[0]}"])  # B's commits are proven
        self.assertEqual(record["next_actor"], "human")
        self.assertEqual(self.state(a), "in_progress")
        self.assertEqual(self.state(b), "completed")
        self.assertEqual(self.head(), made[0])  # nothing finished over it
        with self.assertRaises(StopError):  # and it stays stopped
            st.start(self.store, a, "single-work", trespass, parallel=True, workspace=spec)
        with self.assertRaises(StopError) as unknown:  # only an unproven commit, named exactly, can be accepted
            par.accept_project_writes(self.store, a, [record["claim"]["head"]], "test")
        self.assertEqual(unknown.exception.code, "run_accept_unknown_commit")
        par.accept_project_writes(self.store, a, [made[0]], "test: a Human checked the executor commit")
        done = st.start(self.store, a, "single-work", trespass, parallel=True, workspace=spec)
        self.assertEqual(done.status, "completed", done.detail)
        self.assertEqual(len(made), 1)  # the executor was not run again
        self.assert_released(a)

    def test_p07_an_executor_moving_the_project_history_is_not_finished(self) -> None:
        (a,) = self.standalone("A")

        def rewind(ctx):
            git(self.store.root, "reset", "-q", "--soft", "HEAD~1")  # the claim's own commit leaves HEAD's history
            git(self.store.root, "commit", "-q", "-m", "the claim, rewritten")
            (ctx.workspace / "a.txt").write_text("A\n", encoding="utf-8")
            return st.Completed(("a.txt",))

        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", rewind, parallel=True, workspace=par.WorkspaceSpec(root=self.ws_root))
        self.assertEqual(raised.exception.code, "run_project_written")
        self.assertTrue(any(w.startswith("history:") for w in par.read_run(self.store, a)["project_written"]))

    def test_p07_a_project_without_parallel_runs_notes_nothing(self) -> None:
        (a,) = self.standalone("A")
        done = st.start(self.store, a, "single-work",
                        lambda ctx: ((self.store.root / "a.txt").write_text("A\n", encoding="utf-8"),
                                     st.Completed(("a.txt",)))[1])
        self.assertEqual(done.status, "completed")
        self.assertFalse((self.store.root / par.JOURNAL_DIR).exists())
        self.assertFalse((self.store.root / par.RUNS_DIR).exists())


# the repair suite's helpers, borrowed without a module-level alias of its class (which pytest would collect again)
for _name in _HELPERS:
    setattr(ParallelReviewR3Tests, _name, getattr(repair.ParallelRepairTests, _name))

if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
