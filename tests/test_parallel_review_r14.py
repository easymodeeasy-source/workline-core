"""Parallel START, the r14 review: R14-01 (the Human moved the Work branch to a new commit between the release's checks
and its ``git branch -D``: the Human's commit lost its ref) and R14-02 (the Human deleted and made the branch again at
the same commit in that window: the Human's new branch was deleted). The release now never deletes the Work branch.
The Human acts at the last moment before the r14 release would delete it; the refs, the worktrees, the Human's HEAD,
index and dirty files, the run record and the result commit are read from real Git afterwards."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from helpers import WorklineTestCase, git
import test_parallel_repair as repair
from workline import gitcmd
from workline import parallel as par
from workline import start as st

CHILD = Path(__file__).resolve().parent / "parallel_branch_child.py"
OWNED = "refs/workline/owned/"
BRANCH = "feature/approved"
_HELPERS = ("_reap", "standalone", "events", "lifecycle")


class ReviewR14Tests(WorklineTestCase):
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

    def holding(self, commit: str) -> list[str]:
        """Every ref (branches and Workline's own) that has ``commit``."""
        return self.run_git("for-each-ref", "--contains", commit, "--format=%(refname)").stdout.split()

    @staticmethod
    def writes(ctx):
        (ctx.workspace / "a.txt").write_text("A\n", encoding="utf-8")
        return st.Completed(("a.txt",))

    def human_in_the_window(self, act):
        """``act`` runs once, after the release removed the run's worktree and right before the branch would be
        deleted - r14's ``git branch -D`` (after its proof checks), or the first look at the branch after that."""
        run_git = gitcmd.run_git
        seen = {"pruned": False, "hit": 0}

        def git_(repo, *args, **kwargs):
            if args[:2] == ("worktree", "remove"):
                seen["pruned"] = True
            elif seen["pruned"] and not seen["hit"] and (
                    (args[:2] == ("branch", "-D") and args[-1] == BRANCH)
                    or args[-1:] == (f"refs/heads/{BRANCH}",) and args[:1] == ("rev-parse",)):
                seen["hit"] = 1
                act()
            return run_git(repo, *args, **kwargs)

        gitcmd.run_git = git_
        self.addCleanup(setattr, gitcmd, "run_git", run_git)
        return seen

    def assert_released_and_kept(self, a: str, tip: str) -> dict:
        record = par.read_run(self.store, a)
        self.assertEqual((record["state"], record["cleanup"]["state"]), (par.RELEASED, "released"))
        kept = record["cleanup"]["retained_branch"]
        self.assertEqual((kept["branch"], kept["tip"]), (BRANCH, tip))  # recorded exactly as Git has it
        self.assertEqual(self.ref(f"refs/heads/{BRANCH}"), tip)
        self.assertFalse(Path(record["workspace"]["path"]).exists())  # its worktree is gone
        self.assertEqual(self.refs("refs/workline/parked/"), [])
        self.assertEqual(self.refs("refs/workline/runs/"), [record["refs"]["saved"]])
        self.assertEqual(git(self.store.root, "show", "HEAD~1:a.txt").replace("\r\n", "\n"), "A\n")  # the result
        self.assertEqual(self.lifecycle(a)[-1], "work_completed")
        return record

    # R14-01 ------------------------------------------------------------------------------------------------------
    def test_r14_01_a_branch_the_human_moves_during_the_release_keeps_the_human_commit(self) -> None:
        (a,) = self.standalone("A")
        made = {}

        def human():
            tree = git(self.store.root, "rev-parse", f"refs/heads/{BRANCH}^{{tree}}").strip()
            made["commit"] = git(self.store.root, "commit-tree", tree, "-p", f"refs/heads/{BRANCH}", "-m", "human").strip()
            git(self.store.root, "update-ref", f"refs/heads/{BRANCH}", made["commit"])

        seen = self.human_in_the_window(human)
        done = st.start(self.store, a, "single-work", self.writes, parallel=True, workspace=self.spec(BRANCH))
        self.assertEqual((done.status, seen["hit"]), ("completed", 1), done.detail)
        self.assertIn(f"refs/heads/{BRANCH}", self.holding(made["commit"]))  # the Human's commit still has its branch
        record = self.assert_released_and_kept(a, made["commit"])
        self.assertNotEqual(self.ref(record["refs"]["saved"]), made["commit"])  # Workline's own tip, on its saved ref

    # R14-02 ------------------------------------------------------------------------------------------------------
    def test_r14_02_a_branch_the_human_makes_again_during_the_release_is_kept(self) -> None:
        (a,) = self.standalone("A")
        made = {}

        def human():
            made["commit"] = self.ref(f"refs/heads/{BRANCH}")
            git(self.store.root, "update-ref", "-d", f"refs/heads/{BRANCH}")
            git(self.store.root, "branch", BRANCH, made["commit"])  # the Human's own, same name, same commit

        seen = self.human_in_the_window(human)
        done = st.start(self.store, a, "single-work", self.writes, parallel=True, workspace=self.spec(BRANCH))
        self.assertEqual((done.status, seen["hit"]), ("completed", 1), done.detail)
        self.assertEqual(self.ref(f"refs/heads/{BRANCH}"), made["commit"])
        self.assertEqual(self.run_git("reflog", "show", "--format=%gs", f"refs/heads/{BRANCH}").stdout.strip(),
                         f"branch: Created from {made['commit']}")  # still the Human's own branch
        self.assert_released_and_kept(a, made["commit"])

    # R13-02 under r15: a Human checkout in the same window -------------------------------------------------------
    def test_r14_a_branch_the_human_checks_out_during_the_release_is_kept_with_the_human_worktree(self) -> None:
        (a,) = self.standalone("A")
        other = self.tmp / "human-wt"

        def human():
            git(self.store.root, "worktree", "add", str(other), BRANCH)
            (other / "human.txt").write_text("the Human's own, uncommitted\n", encoding="utf-8")

        seen = self.human_in_the_window(human)
        done = st.start(self.store, a, "single-work", self.writes, parallel=True, workspace=self.spec(BRANCH))
        self.assertEqual((done.status, seen["hit"]), ("completed", 1), done.detail)
        tip = self.ref(f"refs/heads/{BRANCH}")
        self.assertEqual(git(other, "symbolic-ref", "HEAD").strip(), f"refs/heads/{BRANCH}")
        self.assertEqual(git(other, "rev-parse", "HEAD").strip(), tip)
        self.assertEqual(self.run_git("diff", "--cached", "--name-only", cwd=other).stdout, "")
        self.assertEqual(self.run_git("status", "--porcelain", cwd=other).stdout.strip(), "?? human.txt")
        record = self.assert_released_and_kept(a, tip)
        self.assertEqual(self.ref(record["refs"]["saved"]), tip)
        self.assertEqual(self.refs(OWNED), [OWNED + record["run_id"]])

    # a release cut short is finished by the next one ----------------------------------------------------------------
    def test_r14_death_during_the_release_is_finished_and_keeps_the_branch(self) -> None:
        (a,) = self.standalone("A")
        spec = {"root": str(self.store.root), "work_id": a, "ws_root": str(self.ws_root), "die": "after_worktree_remove",
                "branch": BRANCH}
        path = self.signals / "kill.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        died = subprocess.run([sys.executable, str(CHILD), str(path)], cwd=str(self.store.root),
                              capture_output=True, text=True, encoding="utf-8", timeout=300)
        self.assertEqual(died.returncode, 23, died.stderr[-2000:])
        self.assertEqual(par.read_run(self.store, a)["state"], par.RELEASING)
        released = par.release(self.store, a)
        self.assertEqual(released["state"], par.RELEASED)
        record = self.assert_released_and_kept(a, self.ref(f"refs/heads/{BRANCH}"))
        self.assertEqual(self.ref(record["refs"]["saved"]), self.ref(f"refs/heads/{BRANCH}"))
        self.assertEqual(len(self.worktrees()), 1)


for _name in _HELPERS:
    setattr(ReviewR14Tests, _name, getattr(repair.ParallelRepairTests, _name))

if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
