"""Parallel START, the r13 review: R13-01 (a branch deleted and made again by the Human, at the same commit, while the
run's owned ref stayed, was taken as the run's and deleted) and R13-02 (a branch the Human checked out between the
release's check and its deletion was deleted from under the Human's worktree). Real Git; the refs, the worktrees, the
Human's HEAD, index and dirty files, the run record and the result commit are read directly."""

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

CHILD = Path(__file__).resolve().parent / "parallel_branch_child.py"
OWNED = "refs/workline/owned/"
_HELPERS = ("_reap", "standalone", "events", "lifecycle")


class ReviewR13Tests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.signals = self.new_dir("signals")
        self.ws_root = self.tmp / "runs"
        self.children: list[subprocess.Popen] = []
        self.addCleanup(self._reap)

    def spec(self, branch=None) -> par.WorkspaceSpec:
        return par.WorkspaceSpec(root=self.ws_root, branch_prefix="feature/", branch=branch)

    def run_git(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(cwd or self.store.root), *args], capture_output=True, text=True,
                              encoding="utf-8")

    def ref(self, name: str) -> str:
        return self.run_git("rev-parse", "--verify", "--quiet", name).stdout.strip()

    def refs(self, prefix: str) -> list[str]:
        return self.run_git("for-each-ref", "--format=%(refname)", prefix).stdout.split()

    def worktrees(self) -> list[str]:
        return [line for line in self.run_git("worktree", "list", "--porcelain").stdout.splitlines()
                if line.startswith("worktree ")]

    @staticmethod
    def writes(ctx):
        (ctx.workspace / "a.txt").write_text("A\n", encoding="utf-8")
        return st.Completed(("a.txt",))

    def die(self, a: str, die: str, branch: str | None) -> dict:
        spec = {"root": str(self.store.root), "work_id": a, "ws_root": str(self.ws_root), "die": die, "branch": branch}
        path = self.signals / f"kill-{die}.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        died = subprocess.run([sys.executable, str(CHILD), str(path)], cwd=str(self.store.root),
                              capture_output=True, text=True, encoding="utf-8", timeout=300)
        self.assertEqual(died.returncode, 23, f"{die}: {died.stderr[-2000:]}")
        return par.read_run(self.store, a)

    # R13-01 ------------------------------------------------------------------------------------------------------
    def test_r13_01_a_branch_deleted_and_made_again_by_the_human_is_never_taken(self) -> None:
        (a,) = self.standalone("A")
        record = self.die(a, "after_branch", "feature/approved")
        self.assertEqual(record["state"], par.CREATING)
        start = self.ref("refs/heads/feature/approved")
        owned = self.refs(OWNED)
        self.assertEqual(owned, [OWNED + record["run_id"]])
        git(self.store.root, "update-ref", "-d", "refs/heads/feature/approved")  # only the branch goes
        git(self.store.root, "branch", "feature/approved", start)  # the Human's own, same name, same commit
        try:
            done = st.start(self.store, a, "single-work", self.writes, parallel=True,
                            workspace=self.spec("feature/approved"))
        except StopError as exc:
            self.assertEqual(exc.code, "run_branch_exists")
        else:
            self.fail(f"the Human's branch was taken as the run's own (status {done.status})")
        self.assertEqual(self.ref("refs/heads/feature/approved"), start)  # the Human's branch: there, unmoved
        self.assertEqual(self.run_git("reflog", "show", "--format=%gs", "refs/heads/feature/approved").stdout.split("\n")[0],
                         f"branch: Created from {start}")  # still the Human's own (its reflog is the Human's)
        self.assertEqual(self.refs(OWNED), owned)  # Workline's proof kept, nothing deleted
        self.assertEqual(len(self.worktrees()), 1)
        self.assertFalse(Path(record["workspace"]["path"]).exists())
        self.assertEqual(par.read_run(self.store, a)["state"], par.CREATING)  # the run is kept, not finished

    def test_r13_01_its_own_branch_gone_before_the_worktree_is_made_again(self) -> None:
        # the branch Workline made was deleted (nobody made one again): the run makes its own branch again
        (a,) = self.standalone("A")
        self.die(a, "after_branch", "feature/approved")
        git(self.store.root, "update-ref", "-d", "refs/heads/feature/approved")
        done = st.start(self.store, a, "single-work", self.writes, parallel=True, workspace=self.spec(None))
        self.assertEqual(done.status, "completed", done.detail)
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.RELEASED)
        # its own branch, made again, kept at the release (r15) and recorded with its proof
        self.assertEqual(record["cleanup"]["retained_branch"]["tip"], self.ref("refs/heads/feature/approved"))
        self.assertEqual(self.refs(OWNED), [OWNED + record["run_id"]])

    # R13-02 (the release and a Human checkout) is covered by test_parallel_review_r14: no release deletes a branch


for _name in _HELPERS:
    setattr(ReviewR13Tests, _name, getattr(repair.ParallelRepairTests, _name))

if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
