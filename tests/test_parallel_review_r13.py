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
from workline import gitcmd
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
        self.assertEqual(par.read_run(self.store, a)["state"], par.RELEASED)
        self.assertEqual((self.ref("refs/heads/feature/approved"), self.refs(OWNED)), ("", []))

    # R13-02 ------------------------------------------------------------------------------------------------------
    def checkout_in_the_window(self, branch: str, other: Path):
        """The Human checks ``branch`` out in a worktree of their own right before Workline deletes the branch."""
        run_git, run_git_bytes = self.originals = gitcmd.run_git, gitcmd.run_git_bytes
        hit = []

        def human():
            if not hit:
                hit.append(1)
                subprocess.run(["git", "-C", str(self.store.root), "worktree", "add", str(other), branch],
                               capture_output=True, check=True)
                (other / "human.txt").write_text("the Human's own, uncommitted\n", encoding="utf-8")

        def git_(repo, *args, **kwargs):
            if args[:2] == ("branch", "-D") and args[-1] == branch:
                human()
            return run_git(repo, *args, **kwargs)

        def git_bytes(repo, *args, **kwargs):
            if args[:1] == ("update-ref",) and "--stdin" in args and f"delete refs/heads/{branch} ".encode() in (kwargs.get("input") or b""):
                human()
            return run_git_bytes(repo, *args, **kwargs)

        gitcmd.run_git, gitcmd.run_git_bytes = git_, git_bytes
        self.addCleanup(setattr, gitcmd, "run_git", run_git)
        self.addCleanup(setattr, gitcmd, "run_git_bytes", run_git_bytes)
        return hit

    def test_r13_02_a_branch_the_human_checks_out_during_the_release_is_never_deleted(self) -> None:
        (a,) = self.standalone("A")
        other = self.tmp / "human-wt"
        hit = self.checkout_in_the_window("feature/approved", other)
        done = st.start(self.store, a, "single-work", self.writes, parallel=True, workspace=self.spec("feature/approved"))
        self.assertEqual(hit, [1])
        self.assertEqual(done.status, "completed", done.detail)
        record = par.read_run(self.store, a)
        tip = self.ref("refs/heads/feature/approved")
        self.assertNotEqual(tip, "")  # the Human's checked-out branch is still there
        self.assertEqual(git(other, "symbolic-ref", "HEAD").strip(), "refs/heads/feature/approved")
        self.assertEqual(git(other, "rev-parse", "HEAD").strip(), tip)
        self.assertEqual(self.run_git("diff", "--cached", "--name-only", cwd=other).stdout, "")  # index matches HEAD
        self.assertEqual(self.run_git("status", "--porcelain", cwd=other).stdout.strip(), "?? human.txt")
        self.assertEqual((other / "human.txt").read_text(encoding="utf-8"), "the Human's own, uncommitted\n")
        # the run: not declared clean; its result and its proof kept
        self.assertEqual((record["state"], record["cleanup"]["state"]), (par.CLEANUP_FAILED, "branch_in_use"))
        self.assertEqual(self.ref(record["refs"]["saved"]), tip)
        self.assertEqual(self.refs(OWNED), [OWNED + record["run_id"]])
        self.assertEqual(git(self.store.root, "show", "HEAD~1:a.txt").replace("\r\n", "\n"), "A\n")
        self.assertEqual(self.lifecycle(a)[-1], "work_completed")
        # once the Human is done with it, the release finishes and leaves nothing of Workline's
        (other / "human.txt").unlink()
        git(self.store.root, "worktree", "remove", str(other))
        gitcmd.run_git, gitcmd.run_git_bytes = self.originals
        released = par.release(self.store, a)
        self.assertEqual(released["state"], par.RELEASED)
        self.assertEqual((self.ref("refs/heads/feature/approved"), self.refs(OWNED)), ("", []))
        self.assertEqual(self.refs("refs/workline/runs/"), [record["refs"]["saved"]])
        self.assertEqual(self.refs("refs/workline/parked/"), [])
        self.assertEqual(len(self.worktrees()), 1)

    def test_r13_02_death_between_branch_delete_and_proof_removal_is_finished(self) -> None:
        (a,) = self.standalone("A")
        record = self.die(a, "after_branch_delete", "feature/approved")
        self.assertEqual(record["state"], par.RELEASING)
        self.assertEqual(self.ref("refs/heads/feature/approved"), "")
        self.assertEqual(self.refs(OWNED), [OWNED + record["run_id"]])  # the proof outlived the branch
        released = par.release(self.store, a)
        self.assertEqual(released["state"], par.RELEASED)
        self.assertEqual(self.refs(OWNED), [])
        self.assertEqual(self.refs("refs/workline/runs/"), [record["refs"]["saved"]])
        self.assertEqual(len(self.worktrees()), 1)
        self.assertEqual(git(self.store.root, "show", "HEAD~1:a.txt").replace("\r\n", "\n"), "A\n")


for _name in _HELPERS:
    setattr(ReviewR13Tests, _name, getattr(repair.ParallelRepairTests, _name))

if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
