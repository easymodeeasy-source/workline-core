"""Parallel START, the formal review PARSTARTF1 (candidate 491ae41b): F-01 (an unscoped worktree prune), F-02 (the
saved ref taken from the branch instead of the result commit), F-03 (a Hold lost when its finish fails), F-04 (ignored
files written into the Project by an in-place run), F-07 (a Human edit between the conflict check and the write), F-08
(an in-place release error raised out of a finished START), F-09 (Git reads that fail open; an interrupted snapshot).
Real Git; refs, worktree administrative data, files and run records are read directly."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess

from helpers import WorklineTestCase, git
import test_parallel_repair as repair
from workline import parallel as par
from workline import start as st
from workline.errors import StopError

_HELPERS = ("_reap", "standalone", "events", "lifecycle")


class ReviewF1Tests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.ws_root = self.tmp / "runs"
        self.children: list[subprocess.Popen] = []
        self.addCleanup(self._reap)

    def worktree_spec(self, branch=None) -> par.WorkspaceSpec:
        return par.WorkspaceSpec(root=self.ws_root, branch_prefix="feature/", branch=branch)

    def in_place(self) -> par.WorkspaceSpec:
        return par.WorkspaceSpec(kind="in_place", root=self.ws_root)

    def ref(self, name: str) -> str:
        out = subprocess.run(["git", "-C", str(self.store.root), "rev-parse", "--verify", "--quiet", name],
                             capture_output=True, text=True)
        return out.stdout.strip()

    def admin_dirs(self) -> list[str]:
        root = self.store.root / ".git" / "worktrees"
        return sorted(p.name for p in root.iterdir()) if root.is_dir() else []

    def patch(self, owner, name, value) -> None:
        original = getattr(owner, name)
        setattr(owner, name, value)
        self.addCleanup(setattr, owner, name, original)
        return original

    @staticmethod
    def writes(name="a.txt", text="A\n"):
        def executor(ctx):
            (ctx.workspace / name).write_text(text, encoding="utf-8")
            return st.Completed((name,))
        return executor

    def human_worktree_moved_away(self) -> str:
        """A Human's linked worktree whose folder is not where Git recorded it (moved, or on a detached drive)."""
        place = self.tmp / "human-wt"
        git(self.store.root, "worktree", "add", "-b", "human/work", str(place), "HEAD")
        (place / "staged.txt").write_text("the Human's staged change\n", encoding="utf-8")
        git(place, "add", "staged.txt")
        shutil.move(str(place), str(self.tmp / "human-wt-moved"))
        admins = self.admin_dirs()
        self.assertEqual(len(admins), 1)
        return admins[0]

    # F-01 ---------------------------------------------------------------------------------------------------------
    def test_f01_a_release_keeps_a_human_worktree_that_is_only_moved(self) -> None:
        admin = self.human_worktree_moved_away()
        (a,) = self.standalone("A")
        done = st.start(self.store, a, "single-work", self.writes(), parallel=True, workspace=self.worktree_spec())
        self.assertEqual(done.status, "completed", done.detail)
        self.assertEqual(par.read_run(self.store, a)["state"], par.RELEASED)
        self.assertEqual(self.admin_dirs(), [admin])  # the Human's worktree data (HEAD, index) is still there
        self.assertTrue((self.store.root / ".git" / "worktrees" / admin / "index").is_file())

    def test_f01_an_in_place_release_keeps_a_human_worktree_that_is_only_moved(self) -> None:
        admin = self.human_worktree_moved_away()
        (a,) = self.standalone("A")
        done = st.start(self.store, a, "single-work", lambda ctx: st.Completed(), parallel=True,
                        workspace=self.in_place())
        self.assertEqual(done.status, "completed", done.detail)
        self.assertEqual(self.admin_dirs(), [admin])

    # F-02 ---------------------------------------------------------------------------------------------------------
    def branch_changed_at_release(self, change) -> dict:
        (a,) = self.standalone("A")
        original = par._ignored_and_dirty
        fired = []

        def at_release(ws):
            if not fired:
                fired.append(1)
                change(par.read_run(self.store, a)["workspace"]["branch"])
            return original(ws)

        self.patch(par, "_ignored_and_dirty", at_release)
        done = st.start(self.store, a, "single-work", self.writes(), parallel=True, workspace=self.worktree_spec())
        self.assertEqual((done.status, fired), ("completed", [1]), done.detail)
        record = par.read_run(self.store, a)
        # the branch is not what the release checks (it is kept, never deleted): the run's worktree is. Here it no
        # longer matches its HEAD (the branch it names changed under it), so the worktree is not removed and the release
        # stops as cleanup_failed (blocked) - with the result commit already kept on the saved ref
        self.assertEqual((record["state"], record["cleanup"]["state"]), (par.CLEANUP_FAILED, "blocked"))
        self.assertTrue(Path(record["workspace"]["path"]).is_dir())
        return record

    def test_f02_the_saved_ref_is_the_result_commit_when_the_branch_is_gone(self) -> None:
        record = self.branch_changed_at_release(
            lambda branch: git(self.store.root, "update-ref", "-d", f"refs/heads/{branch}"))
        self.assertEqual(self.ref(par.SAVED_REF_PREFIX + record["run_id"]), record["result_commit"])

    def test_f02_the_saved_ref_is_the_result_commit_when_the_branch_moved(self) -> None:
        moved = {}

        def move(branch):
            tree = git(self.store.root, "rev-parse", "HEAD^{tree}").strip()
            moved["to"] = git(self.store.root, "commit-tree", tree, "-p", "HEAD", "-m", "someone else").strip()
            git(self.store.root, "update-ref", f"refs/heads/{branch}", moved["to"])

        record = self.branch_changed_at_release(move)
        self.assertEqual(self.ref(par.SAVED_REF_PREFIX + record["run_id"]), record["result_commit"])
        self.assertEqual(self.ref(f"refs/heads/{record['workspace']['branch']}"), moved["to"])  # left as it is

    # F-03 ---------------------------------------------------------------------------------------------------------
    def finish_fails_once(self) -> None:
        original = par._finish
        failed = []

        def failing(store, record, outcome):
            if not failed:
                failed.append(1)
                raise StopError("injected: the finish's lock wait ran out", code="project_operation_busy")
            return original(store, record, outcome)

        self.patch(par, "_finish", failing)

    def test_f03_a_hold_whose_finish_fails_is_finished_from_the_record(self) -> None:
        (a,) = self.standalone("A")
        calls = []

        def hold(ctx):
            calls.append(1)
            return st.Hold("waiting for the Human")

        self.finish_fails_once()
        with self.assertRaises(StopError):
            st.start(self.store, a, "single-work", hold, parallel=True, workspace=self.worktree_spec())
        self.assertEqual(par.read_run(self.store, a)["state"], par.EXECUTED)
        done = st.start(self.store, a, "single-work", hold, parallel=True, workspace=self.worktree_spec())
        self.assertEqual((done.status, len(calls)), ("held", 1), done.detail)  # the executor was not run again
        self.assertEqual(self.lifecycle(a).count("work_held"), 1)

    def test_f03_a_cancel_whose_finish_fails_is_an_interruption(self) -> None:
        (a,) = self.standalone("A")
        self.finish_fails_once()
        with self.assertRaises(StopError):
            st.start(self.store, a, "single-work", lambda ctx: st.Cancel(reason="not needed"), parallel=True,
                     workspace=self.worktree_spec())
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", lambda ctx: st.Cancel(reason="not needed"), parallel=True,
                     workspace=self.worktree_spec())
        self.assertEqual(raised.exception.code, "run_interrupted")  # as the registry says: not re-run silently

    # F-04 ---------------------------------------------------------------------------------------------------------
    def test_f04_an_ignored_file_written_into_the_project_stops_the_finish(self) -> None:
        (self.store.root / ".gitignore").write_text("build/\n", encoding="utf-8")
        git(self.store.root, "add", ".gitignore")
        git(self.store.root, "commit", "-q", "-m", "ignore build output")
        (a,) = self.standalone("A")

        def bypass(ctx):
            target = ctx.store.root / "build" / "out.bin"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"\x00built")
            return st.Completed()

        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", bypass, parallel=True, workspace=self.in_place())
        self.assertEqual(raised.exception.code, "run_project_written")
        self.assertIn("folder:build/out.bin", par.read_run(self.store, a)["project_written"])

    # F-07 ---------------------------------------------------------------------------------------------------------
    def test_f07_a_human_edit_after_the_conflict_check_is_never_overwritten(self) -> None:
        (a,) = self.standalone("A")
        original = par._conflicts

        def then_the_human_writes(store, record, paths, deleted, snapshot=None):
            found = original(store, record, paths, deleted, snapshot)
            (store.root / "a.txt").write_text("the Human's own\n", encoding="utf-8")
            return found

        self.patch(par, "_conflicts", then_the_human_writes)
        try:
            done = st.start(self.store, a, "single-work", self.writes(), parallel=True, workspace=self.worktree_spec())
            status = done.status
        except StopError as exc:
            status = exc.code
        self.assertEqual((self.store.root / "a.txt").read_text(encoding="utf-8"), "the Human's own\n")
        self.assertNotEqual(status, "completed")

    # F-08 ---------------------------------------------------------------------------------------------------------
    def test_f08_an_in_place_release_error_is_cleanup_failed(self) -> None:
        (a,) = self.standalone("A")
        original = par._remove_snapshot
        failed = []

        def failing(record):
            if not failed:
                failed.append(1)
                raise PermissionError("injected: a snapshot file is still open")
            return original(record)

        self.patch(par, "_remove_snapshot", failing)
        done = st.start(self.store, a, "single-work", lambda ctx: st.Completed(), parallel=True,
                        workspace=self.in_place())
        self.assertEqual(done.status, "completed")
        self.assertEqual(par.read_run(self.store, a)["state"], par.CLEANUP_FAILED)
        self.assertEqual(par.release(self.store, a)["state"], par.RELEASED)

    # F-09 ---------------------------------------------------------------------------------------------------------
    def test_f09_a_worktree_list_git_cannot_give_is_a_stop(self) -> None:
        with self.assertRaises(StopError) as raised:
            par._branch_out(self.tmp / "not-a-repository", "feature/x")
        self.assertEqual(raised.exception.code, "run_git_unknown")

    def test_f09_an_interrupted_snapshot_is_made_again(self) -> None:
        (self.store.root / "draft.txt").write_text("a Human's untracked draft\n", encoding="utf-8")
        (a,) = self.standalone("A")
        original = par._snapshot_overlay
        failed = []

        def interrupted(project, snapshot):
            if not failed:
                failed.append(1)
                raise KeyboardInterrupt("injected: stopped while the snapshot was made")
            return original(project, snapshot)

        self.patch(par, "_snapshot_overlay", interrupted)
        with self.assertRaises(KeyboardInterrupt):
            st.start(self.store, a, "single-work", lambda ctx: st.Completed(), parallel=True, workspace=self.in_place())
        seen = {}

        def reads(ctx):
            draft = ctx.workspace / "draft.txt"
            seen["draft"] = draft.is_file() and not os.access(draft, os.W_OK)
            return st.Completed()

        done = st.start(self.store, a, "single-work", reads, parallel=True, workspace=self.in_place())
        self.assertEqual(done.status, "completed", done.detail)
        self.assertEqual(seen, {"draft": True})  # the whole snapshot, read-only


for _name in _HELPERS:
    setattr(ReviewF1Tests, _name, getattr(repair.ParallelRepairTests, _name))

if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
