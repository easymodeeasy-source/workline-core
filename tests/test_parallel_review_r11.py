"""Parallel START, the r11 review of WorkspaceSpec.branch: R11-01 (a Human branch taken and deleted because it pointed at
the parked commit), R11-02 (a recorded branch replaced on a later START), R11-03 (a refused branch leaving a run that
cannot be resumed). Real Git; the refs, the run record and the Work's lifecycle are read directly."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from helpers import WorklineTestCase, git
import test_parallel_repair as repair
from workline import gitcmd
from workline import parallel as par
from workline import start as st
from workline.errors import StopError, ValidationError
from workline.state import ProjectView

_HELPERS = ("_reap", "standalone", "spawn", "result", "wait_signal", "release", "events", "lifecycle",
            "assert_events_sound", "assert_released", "hold_lock", "hook", "solver_project", "solver_spec", "pointer")


class ReviewR11Tests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.signals = self.new_dir("signals")
        self.ws_root = self.tmp / "runs"
        self.children: list[subprocess.Popen] = []
        self.addCleanup(self._reap)

    def spec(self, branch=None, **extra) -> par.WorkspaceSpec:
        return par.WorkspaceSpec(root=self.ws_root, branch_prefix="feature/", branch=branch, **extra)

    def head(self) -> str:
        return git(self.store.root, "rev-parse", "HEAD").strip()

    def ref(self, name: str) -> str:
        out = subprocess.run(["git", "-C", str(self.store.root), "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"],
                             capture_output=True, text=True)
        return out.stdout.strip()

    @staticmethod
    def writes(name, text):
        def executor(ctx):
            (ctx.workspace / name).write_text(text, encoding="utf-8")
            return st.Completed((name,))
        return executor

    # R11-01 ------------------------------------------------------------------------------------------------
    def test_r11_01_a_human_branch_at_the_parked_commit_is_never_taken_or_deleted(self) -> None:
        (a,) = self.standalone("A")
        held = st.start(self.store, a, "single-work",
                        lambda ctx: ((ctx.workspace / "a.txt").write_text("wip\n", encoding="utf-8"), st.Hold("later"))[1],
                        parallel=True, workspace=self.spec("feature/owned-work"))
        self.assertEqual(held.status, "held")
        first = par.read_run(self.store, a)
        parked = git(self.store.root, "rev-parse", first["refs"]["parked"]).strip()
        git(self.store.root, "branch", "feature/human", parked)  # the Human's own branch, at the very same commit
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", self.writes("a.txt", "done\n"), parallel=True,
                     workspace=self.spec("feature/human"))
        self.assertEqual(raised.exception.code, "run_branch_exists")
        self.assertEqual(self.ref("feature/human"), parked)  # the Human's branch: still there, unmoved
        self.assertEqual(par.read_run(self.store, a)["run_id"], first["run_id"])  # nothing was begun
        self.assertEqual(ProjectView.load(self.store).work_state(a).state, "held")
        # the held run's OWN branch is still continued
        done = st.start(self.store, a, "single-work", self.writes("a.txt", "done\n"), parallel=True,
                        workspace=self.spec("feature/owned-work"))
        self.assertEqual(done.status, "completed", done.detail)
        second = par.read_run(self.store, a)
        self.assertEqual(second["workspace"]["branch"], "feature/owned-work")
        self.assertEqual(second["workspace"]["branch_owner"], "inherited")
        self.assertEqual(self.ref("feature/human"), parked)
        self.assertEqual(git(self.store.root, "show", "HEAD~1:a.txt").replace("\r\n", "\n"), "done\n")

    # R11-02 ------------------------------------------------------------------------------------------------
    def test_r11_02_a_recorded_branch_never_changes_on_a_later_start(self) -> None:
        (a,) = self.standalone("A")
        original = gitcmd.run_git
        failed = []

        def fail_once(repo, *args, **kwargs):
            if args[:2] == ("worktree", "add") and not failed:
                failed.append(1)
                return gitcmd.GitResult(128, "", "injected: worktree add failed")
            return original(repo, *args, **kwargs)

        gitcmd.run_git = fail_once
        try:
            with self.assertRaises(StopError):
                st.start(self.store, a, "single-work", self.writes("a.txt", "A\n"), parallel=True,
                         workspace=self.spec("feature/approved"))
        finally:
            gitcmd.run_git = original
        record = par.read_run(self.store, a)
        self.assertEqual((record["state"], record["workspace"]["branch"]), (par.CREATING, "feature/approved"))
        self.assertFalse(Path(record["workspace"]["path"]).exists())
        before = json.dumps(record, sort_keys=True)
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", self.writes("a.txt", "A\n"), parallel=True,
                     workspace=self.spec("feature/different"))
        self.assertEqual(raised.exception.code, "run_branch_mismatch")
        self.assertEqual(json.dumps(par.read_run(self.store, a), sort_keys=True), before)  # untouched
        self.assertEqual(self.ref("feature/different"), "")
        # the same branch (or None: no request) finishes the recorded creation
        done = st.start(self.store, a, "single-work", self.writes("a.txt", "A\n"), parallel=True,
                        workspace=self.spec(None))
        self.assertEqual(done.status, "completed", done.detail)
        self.assertEqual(par.read_run(self.store, a)["workspace"]["branch"], "feature/approved")
        self.assertEqual(self.lifecycle(a).count("work_started"), 1)

    # R11-03 ------------------------------------------------------------------------------------------------
    def test_r11_03_an_invalid_branch_is_refused_before_anything_is_written(self) -> None:
        (a,) = self.standalone("A")
        head = self.head()
        with self.assertRaises(ValidationError) as raised:
            st.start(self.store, a, "single-work", self.writes("a.txt", "A\n"), parallel=True,
                     workspace=self.spec("feature/not?valid"))
        self.assertEqual(raised.exception.code, "run_branch_name")
        self.assertEqual(self.head(), head)  # no claim commit
        self.assertIsNone(par.read_run(self.store, a))
        self.assertEqual(ProjectView.load(self.store).work_state(a).state, "unstarted")
        done = st.start(self.store, a, "single-work", self.writes("a.txt", "A\n"), parallel=True,
                        workspace=self.spec("feature/valid"))
        self.assertEqual(done.status, "completed", done.detail)
        self.assertEqual(self.lifecycle(a).count("work_started"), 1)

    def test_r11_03_an_existing_branch_is_refused_before_anything_is_written(self) -> None:
        (a,) = self.standalone("A")
        git(self.store.root, "branch", "feature/taken", "HEAD")
        taken, head = self.ref("feature/taken"), self.head()
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", self.writes("a.txt", "A\n"), parallel=True,
                     workspace=self.spec("feature/taken"))
        self.assertEqual(raised.exception.code, "run_branch_exists")
        self.assertEqual((self.head(), self.ref("feature/taken")), (head, taken))
        self.assertIsNone(par.read_run(self.store, a))
        done = st.start(self.store, a, "single-work", self.writes("a.txt", "A\n"), parallel=True,
                        workspace=self.spec("feature/unused"))
        self.assertEqual(done.status, "completed", done.detail)
        self.assertEqual(self.ref("feature/taken"), taken)

    def test_r11_03_a_claimed_run_without_a_workspace_is_resumed(self) -> None:
        # compatibility: a run left CREATING with no workspace recorded (as an r11 refusal left it)
        (a,) = self.standalone("A")
        original = par._create_workspace

        def refuse_once(*args, **kwargs):
            par._create_workspace = original
            raise StopError("injected: refused after the claim", code="run_branch_exists")

        par._create_workspace = refuse_once
        try:
            with self.assertRaises(StopError):
                st.start(self.store, a, "single-work", self.writes("a.txt", "A\n"), parallel=True,
                         workspace=self.spec("feature/later"))
        finally:
            par._create_workspace = original
        record = par.read_run(self.store, a)
        self.assertEqual(record["state"], par.CREATING)
        self.assertNotIn("workspace", record)
        done = st.start(self.store, a, "single-work", self.writes("a.txt", "A\n"), parallel=True,
                        workspace=self.spec("feature/later"))
        self.assertEqual(done.status, "completed", done.detail)
        self.assertEqual(self.lifecycle(a).count("work_started"), 1)


for _name in _HELPERS:
    setattr(ReviewR11Tests, _name, getattr(repair.ParallelRepairTests, _name))

if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
