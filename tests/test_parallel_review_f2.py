"""Parallel START, the formal review PARSTARTF2 (candidate 410ce179): N-01 (after reopen(), a Hold kept the old result
commit on the parked ref), N-02 (a rewritten pre-existing ignored file stopped an in-place finish with no way out), N-03
(a stale conflict-check map turned a Hold into a spurious conflict), N-05 (an unreadable worktree read as clean), N-07
(a runs folder inside the Project stopped every in-place finish), N-08 (a relative gitdir), N-09 (an outer START and a
parallel run waiting on each other). Real Git and real child processes; refs, files, run records and results are read
directly."""

from __future__ import annotations

from pathlib import Path
import subprocess

from helpers import WorklineTestCase, completing_executor, git
import test_parallel_start as ps
from workline import parallel as par
from workline import start as st
from workline.errors import StopError

_HELPERS = ("_reap", "standalone", "spawn", "result", "wait_signal", "release", "events", "lifecycle")


class ReviewF2Tests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.signals = self.new_dir("signals")
        self.ws_root = self.tmp / "runs"
        self.children: list[subprocess.Popen] = []
        self.addCleanup(self._reap)

    def ref(self, name: str) -> str:
        out = subprocess.run(["git", "-C", str(self.store.root), "rev-parse", "--verify", "--quiet", name],
                             capture_output=True, text=True)
        return out.stdout.strip()

    def conflicted(self, also: dict[str, str] | None = None) -> str:
        """Work A parked in a conflict (Work B integrated shared.txt while A ran), then reopened. ``also``: more files
        A returns that do not conflict (the conflict check records what it saw at them)."""
        (self.store.root / "shared.txt").write_text("base\n", encoding="utf-8")
        git(self.store.root, "add", "shared.txt")
        git(self.store.root, "commit", "-q", "-m", "shared")
        git(self.store.root, "push", "-q", "origin", "HEAD:main")
        a, b = self.standalone("A", "B")
        child_a = self.spawn("A", a, writes={"shared.txt": "A\n", **(also or {})}, block=True)
        self.wait_signal("entered-A-1.json")
        self.assertEqual(self.result(self.spawn("B", b, writes={"shared.txt": "B\n"}))["status"], "completed")
        self.release("A")
        self.assertEqual(self.result(child_a)["status"], "conflict")
        par.reopen(self.store, a)
        return a

    @staticmethod
    def holds_wip(ctx):
        (ctx.workspace / "shared.txt").write_text("work in progress\n", encoding="utf-8")
        return st.Hold("later")

    # N-01 --------------------------------------------------------------------------------------------------------
    def test_n01_a_hold_after_reopen_keeps_its_own_work_on_the_parked_ref(self) -> None:
        a = self.conflicted()
        done = st.start(self.store, a, "single-work", self.holds_wip, parallel=True,
                        workspace=par.WorkspaceSpec(root=self.ws_root))
        self.assertEqual(done.status, "held", done.detail)
        record = par.read_run(self.store, a)
        tip = self.ref(f"refs/heads/{record['workspace']['branch']}")
        self.assertEqual(self.ref(record["refs"]["parked"]), tip)  # the work in progress, not the old result
        self.assertEqual(git(self.store.root, "show", f"{tip}:shared.txt").replace("\r\n", "\n"), "work in progress\n")
        self.assertIsNone(record.get("result_commit"))

    # N-03 --------------------------------------------------------------------------------------------------------
    def test_n03_a_hold_after_reopen_is_not_turned_into_a_conflict(self) -> None:
        a = self.conflicted({"other.txt": "A's other\n"})
        (self.store.root / "other.txt").write_text("the Human's edit\n", encoding="utf-8")  # after the conflict
        done = st.start(self.store, a, "single-work", self.holds_wip, parallel=True,
                        workspace=par.WorkspaceSpec(root=self.ws_root))
        self.assertEqual(done.status, "held", done.detail)
        self.assertEqual((self.store.root / "other.txt").read_text(encoding="utf-8"), "the Human's edit\n")

    # N-02 / N-07 ---------------------------------------------------------------------------------------------------
    def ignore_build(self) -> None:
        (self.store.root / ".gitignore").write_text("build/\n", encoding="utf-8")
        git(self.store.root, "add", ".gitignore")
        git(self.store.root, "commit", "-q", "-m", "ignore build output")
        git(self.store.root, "push", "-q", "origin", "HEAD:main")

    def test_n02_a_rewritten_existing_ignored_file_does_not_stop_and_a_created_one_is_cleared_by_removing_it(self) -> None:
        self.ignore_build()
        out = self.store.root / "build" / "out.bin"
        out.parent.mkdir(parents=True)
        out.write_bytes(b"old build")
        a, b = self.standalone("A", "B")
        spec = par.WorkspaceSpec(kind="in_place", root=self.ws_root)

        def rebuilds(ctx):
            out.write_bytes(b"a newer build, as the Human's own build would")
            return st.Completed()

        self.assertEqual(st.start(self.store, a, "single-work", rebuilds, parallel=True, workspace=spec).status,
                         "completed")
        created = self.store.root / "build" / "new.bin"

        def creates(ctx):
            created.write_bytes(b"made by the executor")
            return st.Completed()

        with self.assertRaises(StopError) as raised:
            st.start(self.store, b, "single-work", creates, parallel=True, workspace=spec)
        self.assertEqual(raised.exception.code, "run_project_written")
        self.assertIn("folder:build/new.bin", par.read_run(self.store, b)["project_written"])
        created.unlink()  # the documented way out
        done = st.start(self.store, b, "single-work", creates, parallel=True, workspace=spec)
        self.assertEqual(done.status, "completed", done.detail)

    def test_n07_a_runs_folder_inside_the_project_does_not_stop_the_finish(self) -> None:
        self.ignore_build()
        (a,) = self.standalone("A")
        done = st.start(self.store, a, "single-work", lambda ctx: st.Completed(), parallel=True,
                        workspace=par.WorkspaceSpec(kind="in_place", root=self.store.root / "build" / "runs"))
        self.assertEqual(done.status, "completed", done.detail)

    # N-05 --------------------------------------------------------------------------------------------------------
    def test_n05_an_unreadable_worktree_is_not_clean(self) -> None:
        with self.assertRaises(StopError) as raised:
            par._ignored_and_dirty(self.tmp / "not-a-worktree")
        self.assertEqual(raised.exception.code, "run_git_unknown")

    # N-08 --------------------------------------------------------------------------------------------------------
    def test_n08_a_relative_gitdir_is_matched(self) -> None:
        repo = self.new_dir("rel-repo")
        git(repo, "init", "-q")
        admin = repo / ".git" / "worktrees" / "snap"
        admin.mkdir(parents=True)
        gone = self.tmp / "snap-gone"
        relative = Path("..", "..", "..", "..", gone.name, ".git")  # from admin: worktrees/snap -> .git -> repo -> tmp
        (admin / "gitdir").write_text(str(relative) + "\n", encoding="utf-8")
        self.assertEqual((admin / relative).resolve(), (gone / ".git").resolve())
        par._drop_worktree_admin(repo, gone)
        self.assertFalse(admin.exists())

    # N-09 --------------------------------------------------------------------------------------------------------
    def test_n09_an_outer_start_stops_before_a_work_a_parallel_run_holds(self) -> None:
        roadmap = self.simple_roadmap(self.store)
        entry = self.simple_entry(self.store, roadmap.phase_ids["a"], {"w1": "W1 done", "w2": "W2 done"})
        w1, w2 = entry.work_ids["w1"], entry.work_ids["w2"]
        child = self.spawn("B", w2, writes={"w2.txt": "W2\n"}, block=True)
        self.wait_signal("entered-B-1.json")
        try:
            outer = st.start(self.store, w1, "outer", completing_executor(self.store))
            outcome = (outer.status, outer.code)
        except StopError as exc:
            outcome = ("raised", exc.code)
        self.assertEqual(outcome, ("stopped", "work_run_active"))
        self.release("B")
        self.assertEqual(self.result(child)["status"], "completed")  # its finish is not refused by a pending outer


for _name in _HELPERS:
    setattr(ReviewF2Tests, _name, getattr(ps.ParallelStartTests, _name))

if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
