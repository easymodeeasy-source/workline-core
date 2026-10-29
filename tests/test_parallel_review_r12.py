"""Parallel START, the r12 review: R12-01 (a branch the Human made while a run's branch creation was interrupted was
adopted as the run's own and deleted at its release). The run is killed (os._exit) at points of its workspace creation;
the Human's branch, the run's refs, its record and the Work's lifecycle are read from real Git afterwards."""

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
from workline.state import ProjectView

CHILD = Path(__file__).resolve().parent / "parallel_branch_child.py"
OWNED = "refs/workline/owned/"
_HELPERS = ("_reap", "standalone", "events", "lifecycle")


class ReviewR12Tests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.signals = self.new_dir("signals")
        self.ws_root = self.tmp / "runs"
        self.children: list[subprocess.Popen] = []
        self.addCleanup(self._reap)

    def spec(self, branch=None) -> par.WorkspaceSpec:
        return par.WorkspaceSpec(root=self.ws_root, branch_prefix="feature/", branch=branch)

    def run_git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.store.root), *args], capture_output=True, text=True,
                              encoding="utf-8")

    def ref(self, name: str) -> str:
        return self.run_git("rev-parse", "--verify", "--quiet", name).stdout.strip()

    def owned_refs(self) -> list[str]:
        return self.run_git("for-each-ref", "--format=%(refname)", OWNED).stdout.split()

    def worktrees(self) -> list[str]:
        return [line for line in self.run_git("worktree", "list", "--porcelain").stdout.splitlines()
                if line.startswith("worktree ")]

    @staticmethod
    def writes(text="A\n"):
        def executor(ctx):
            (ctx.workspace / "a.txt").write_text(text, encoding="utf-8")
            return st.Completed(("a.txt",))
        return executor

    def kill_at(self, a: str, die: str, branch: str | None) -> dict:
        spec = {"root": str(self.store.root), "work_id": a, "ws_root": str(self.ws_root), "die": die, "branch": branch}
        path = self.signals / f"kill-{die}.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        died = subprocess.run([sys.executable, str(CHILD), str(path)], cwd=str(self.store.root),
                              capture_output=True, text=True, encoding="utf-8", timeout=300)
        self.assertEqual(died.returncode, 23, f"{die}: {died.stderr[-2000:]}")
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.CREATING)
        return record

    def assert_clean_finish(self, a: str, branch: str) -> None:
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.RELEASED)
        self.assertEqual(self.ref(f"refs/heads/{branch}"), "")  # its own branch, deleted with its proof
        self.assertEqual(self.owned_refs(), [])
        self.assertEqual(len(self.worktrees()), 1)  # only the Project's own checkout
        self.assertEqual(self.lifecycle(a).count("work_started"), 1)
        self.assertEqual(git(self.store.root, "show", "HEAD~1:a.txt").replace("\r\n", "\n"), "A\n")

    # 1-3: the reported failure ----------------------------------------------------------------------------------
    def test_r12_01_a_human_branch_made_during_an_interrupted_creation_is_never_taken_or_deleted(self) -> None:
        (a,) = self.standalone("A")
        record = self.kill_at(a, "before_branch", "feature/approved")
        start = record["workspace"].get("start_at") or record["workspace"]["base_commit"]
        self.assertEqual(self.ref("refs/heads/feature/approved"), "")
        git(self.store.root, "branch", "feature/approved", start)  # the Human's own branch, at the very same commit
        try:
            done = st.start(self.store, a, "single-work", self.writes(), parallel=True,
                            workspace=self.spec("feature/approved"))
        except StopError as exc:
            self.assertEqual(exc.code, "run_branch_exists")
        else:
            self.fail(f"the Human's branch was taken as the run's own (status {done.status})")
        self.assertEqual(self.ref("refs/heads/feature/approved"), start)  # name and commit unchanged
        self.assertFalse(Path(record["workspace"]["path"]).exists())  # nothing was checked out on it
        self.assertEqual(self.lifecycle(a).count("work_started"), 1)
        self.assertNotIn("feature/approved", "".join(self.run_git("worktree", "list", "--porcelain").stdout))

    def test_r12_01_the_same_with_an_automatic_branch_name(self) -> None:
        (a,) = self.standalone("A")
        record = self.kill_at(a, "before_branch", None)
        branch, start = record["workspace"]["branch"], record["workspace"]["base_commit"]
        git(self.store.root, "branch", branch, start)
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", self.writes(), parallel=True, workspace=self.spec(None))
        self.assertEqual(raised.exception.code, "run_branch_exists")
        self.assertEqual(self.ref(f"refs/heads/{branch}"), start)

    # 4-6: the run's own interrupted creation is still recovered -----------------------------------------------
    def test_r12_01_death_before_the_branch_is_made_is_recovered(self) -> None:
        (a,) = self.standalone("A")
        self.kill_at(a, "before_branch", "feature/approved")
        done = st.start(self.store, a, "single-work", self.writes(), parallel=True, workspace=self.spec(None))
        self.assertEqual(done.status, "completed", done.detail)
        self.assert_clean_finish(a, "feature/approved")

    def test_r12_01_death_right_after_the_branch_is_made_is_recovered(self) -> None:
        (a,) = self.standalone("A")
        self.kill_at(a, "after_branch", "feature/approved")
        done = st.start(self.store, a, "single-work", self.writes(), parallel=True,
                        workspace=self.spec("feature/approved"))
        self.assertEqual(done.status, "completed", done.detail)
        self.assert_clean_finish(a, "feature/approved")

    def test_r12_01_death_right_after_worktree_add_is_recovered(self) -> None:
        (a,) = self.standalone("A")
        self.kill_at(a, "after_worktree_add", None)
        done = st.start(self.store, a, "single-work", self.writes(), parallel=True, workspace=self.spec(None))
        self.assertEqual(done.status, "completed", done.detail)
        self.assert_clean_finish(a, par.read_run(self.store, a)["workspace"]["branch"])

    # 7-8: the run's own branch, out elsewhere or moved, is not used and not deleted ----------------------------
    def test_r12_01_its_branch_out_in_another_worktree_is_refused(self) -> None:
        (a,) = self.standalone("A")
        record = self.kill_at(a, "after_branch", "feature/approved")
        start = self.ref("refs/heads/feature/approved")
        other = self.tmp / "human-wt"
        git(self.store.root, "worktree", "add", str(other), "feature/approved")  # the Human checks it out
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", self.writes(), parallel=True, workspace=self.spec(None))
        self.assertEqual(raised.exception.code, "run_branch_exists")
        self.assertEqual(self.ref("refs/heads/feature/approved"), start)
        self.assertEqual(git(other, "symbolic-ref", "HEAD").strip(), "refs/heads/feature/approved")
        self.assertFalse(Path(record["workspace"]["path"]).exists())

    def test_r12_01_its_branch_moved_to_another_commit_is_refused(self) -> None:
        (a,) = self.standalone("A")
        self.kill_at(a, "after_branch", "feature/approved")
        tree = git(self.store.root, "rev-parse", "HEAD^{tree}").strip()
        moved = git(self.store.root, "commit-tree", tree, "-p", "HEAD", "-m", "human").strip()
        git(self.store.root, "branch", "-f", "feature/approved", moved)
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", self.writes(), parallel=True, workspace=self.spec(None))
        self.assertEqual(raised.exception.code, "run_branch_exists")
        self.assertEqual(self.ref("refs/heads/feature/approved"), moved)

    # 9: a held run is continued on its own branch; the proof goes with it ---------------------------------------
    def test_r12_01_a_held_run_is_continued_and_its_proof_handed_over(self) -> None:
        (a,) = self.standalone("A")
        held = st.start(self.store, a, "single-work",
                        lambda ctx: ((ctx.workspace / "a.txt").write_text("wip\n", encoding="utf-8"), st.Hold("later"))[1],
                        parallel=True, workspace=self.spec("feature/owned-work"))
        self.assertEqual(held.status, "held")
        first = par.read_run(self.store, a)
        self.assertEqual(self.owned_refs(), [OWNED + first["run_id"]])
        done = st.start(self.store, a, "single-work", self.writes(), parallel=True,
                        workspace=self.spec("feature/owned-work"))
        self.assertEqual(done.status, "completed", done.detail)
        second = par.read_run(self.store, a)
        self.assertEqual(second["workspace"]["branch_owner"], "inherited")
        self.assertEqual(self.ref("refs/heads/feature/owned-work"), "")  # deleted with the handed-over proof
        self.assertEqual(self.owned_refs(), [])

    def test_r12_01_a_held_branch_without_workline_proof_is_not_continued(self) -> None:
        (a,) = self.standalone("A")
        st.start(self.store, a, "single-work",
                 lambda ctx: ((ctx.workspace / "a.txt").write_text("wip\n", encoding="utf-8"), st.Hold("later"))[1],
                 parallel=True, workspace=self.spec("feature/owned-work"))
        first = par.read_run(self.store, a)
        tip = self.ref("refs/heads/feature/owned-work")
        git(self.store.root, "update-ref", "-d", OWNED + first["run_id"])  # the proof is gone: no longer provably ours
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", self.writes(), parallel=True,
                     workspace=self.spec("feature/owned-work"))
        self.assertEqual(raised.exception.code, "run_branch_exists")
        self.assertEqual(self.ref("refs/heads/feature/owned-work"), tip)
        self.assertEqual(ProjectView.load(self.store).work_state(a).state, "held")

    # 14: a release never deletes a branch it has no proof for ---------------------------------------------------
    def test_r12_01_release_keeps_a_branch_without_proof(self) -> None:
        (a,) = self.standalone("A")
        original = par._ref_transaction if hasattr(par, "_ref_transaction") else None
        seen = {}

        def executor(ctx):
            record = par.read_run(self.store, a)
            seen["branch"] = record["workspace"]["branch"]
            git(self.store.root, "update-ref", "-d", OWNED + record["run_id"])  # the proof vanishes mid-run
            (ctx.workspace / "a.txt").write_text("A\n", encoding="utf-8")
            return st.Completed(("a.txt",))

        done = st.start(self.store, a, "single-work", executor, parallel=True, workspace=self.spec("feature/kept"))
        self.assertEqual(done.status, "completed", done.detail)
        self.assertIsNotNone(original)
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.RELEASED)
        self.assertNotEqual(self.ref("refs/heads/feature/kept"), "")  # kept, and said so
        self.assertTrue(any("feature/kept" in note for note in record.get("cleanup_notes", [])))
        self.assertEqual(len(self.worktrees()), 1)


for _name in _HELPERS:
    setattr(ReviewR12Tests, _name, getattr(repair.ParallelRepairTests, _name))

if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
