"""Parallel START: a Work branch named by the Project before the START (the YGO fork guard of W-187/W-189 accepts only a
branch the Work's own record names, bound to the worktree as (Work, branch)). A guard of that shape is installed as
the fork's real pre-commit and pre-push hooks; nothing in it is relaxed."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from helpers import WorklineTestCase, git
import test_parallel_repair as repair
from workline import parallel as par
from workline import start as st
from workline.create import WorkSpec, create_standalone_work
from workline.errors import StopError

_HELPERS = ("_reap", "standalone", "spawn", "result", "wait_signal", "release", "events", "lifecycle",
            "assert_events_sound", "assert_released", "hold_lock", "hook", "solver_project", "solver_spec", "pointer")

GUARD = r'''#!/bin/sh
B="$(git rev-parse --absolute-git-dir)/fork-guard-binding"
[ -f "$B" ] || { echo "REFUSED: no binding" >&2; exit 1; }
py -3 -I -B - "$B" "{works}" "$1" <<'EOF'
import json, subprocess, sys
from pathlib import Path
b = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
record = Path(sys.argv[2]) / (b["work"] + ".md")
if not record.is_file() or b["branch"] not in record.read_text(encoding="utf-8"):
    sys.exit("REFUSED: the Work's record does not name " + b["branch"])
here = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
if here and here != b["branch"]:
    sys.exit("REFUSED: on " + here + ", bound to " + b["branch"])
EOF
'''


class ExplicitBranchTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project(remote=True)
        self.signals = self.new_dir("signals")
        self.ws_root = self.tmp / "runs"
        self.children: list[subprocess.Popen] = []
        self.addCleanup(self._reap)

    def guarded_solver(self):
        fork_remote, base = self.solver_project()
        solver = self.store.root / "solver"
        works = (self.store.root / ".workline" / "works").as_posix()
        for name in ("pre-commit", "pre-push"):
            self.hook(solver / ".git", name, GUARD.replace("{works}", works).split("\n", 1)[1])
        return fork_remote, base, solver

    @staticmethod
    def bind(worktree: Path, record: dict) -> None:
        gitdir = Path(git(worktree, "rev-parse", "--absolute-git-dir").strip())
        (gitdir / "fork-guard-binding").write_text(
            json.dumps({"work": record["work_id"], "branch": record["workspace"]["branch"]}), encoding="utf-8")

    def test_the_projects_branch_passes_a_record_bound_guard(self) -> None:
        fork_remote, base, solver = self.guarded_solver()
        branch = "feature/demo-explicit-branch"
        a = create_standalone_work(self.store, WorkSpec("A", f"changes the solver on {branch}")).work_id

        def change(ctx):
            (ctx.workspace / "engine.cpp").write_text("int v = 2;\n", encoding="utf-8")
            return st.Completed(("engine.cpp",), "feat(solver): v = 2")

        spec = self.solver_spec(branch=branch, prepare=self.bind)
        done = st.start(self.store, a, "single-work", change, parallel=True, workspace=spec)
        self.assertEqual(done.status, "completed", done.detail)
        record = par.read_run(self.store, a)
        self.assertEqual(record["workspace"]["branch"], branch)
        result = record["result_commit"]
        self.assertEqual(git(fork_remote, "rev-parse", branch).strip(), result)
        self.assertEqual(git(fork_remote, "rev-parse", "main").strip(), result)
        self.assertEqual(self.pointer(), result)

    def test_a_branch_the_record_does_not_name_is_refused_by_the_guard(self) -> None:
        _fork, base, solver = self.guarded_solver()
        a = create_standalone_work(self.store, WorkSpec("A", "a record naming no branch")).work_id

        def change(ctx):
            (ctx.workspace / "engine.cpp").write_text("int v = 2;\n", encoding="utf-8")
            return st.Completed(("engine.cpp",))

        with self.assertRaises(StopError):
            st.start(self.store, a, "single-work", change, parallel=True,
                     workspace=self.solver_spec(branch="feature/not-named", prepare=self.bind))
        self.assertEqual(self.pointer(), base)  # the guard's refusal stands; nothing integrated

    def test_an_existing_branch_is_never_reused_by_a_new_run(self) -> None:
        _fork, base, solver = self.guarded_solver()
        git(solver, "branch", "feature/taken", base)
        a = create_standalone_work(self.store, WorkSpec("A", "on feature/taken")).work_id
        with self.assertRaises(StopError) as raised:
            st.start(self.store, a, "single-work", lambda ctx: st.Completed(), parallel=True,
                     workspace=self.solver_spec(branch="feature/taken", prepare=self.bind))
        self.assertEqual(raised.exception.code, "run_branch_exists")
        self.assertEqual(git(solver, "rev-parse", "feature/taken").strip(), base)  # untouched


for _name in _HELPERS:
    setattr(ExplicitBranchTests, _name, getattr(repair.ParallelRepairTests, _name))

if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
