"""Shared test fixtures: temporary Git repositories, Projects, executors."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from workline import roadmap as rm  # noqa: E402
from workline import start as st  # noqa: E402
from workline.phase_create import PhaseRelationSpec, PhaseSpec  # noqa: E402
from workline.project_start import project_start  # noqa: E402
from workline.store import ProjectStore  # noqa: E402

WORKLINE_ROOT = Path(__file__).resolve().parents[1]

GIT_ENV = {
    "GIT_AUTHOR_NAME": "workline-test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "workline-test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _force_remove(function, path, _exc_info):
    os.chmod(path, stat.S_IWRITE)
    function(path)


def rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onerror=_force_remove)


def git(repo: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    if check and completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {completed.stderr}")
    return completed.stdout


class WorklineTestCase(unittest.TestCase):
    """Base class with an isolated temp dir and git identity."""

    def setUp(self) -> None:
        super().setUp()
        self._env_backup = {key: os.environ.get(key) for key in GIT_ENV}
        os.environ.update(GIT_ENV)
        self.tmp = Path(tempfile.mkdtemp(prefix="workline-test-"))
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        rmtree(self.tmp)
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # repositories ----------------------------------------------------------
    def new_dir(self, name: str = "proj") -> Path:
        path = self.tmp / name
        path.mkdir(parents=True)
        return path

    def new_project(self, name: str = "proj", *, remote: bool = False, pin: bool = True) -> ProjectStore:
        """A Workline Project; with ``remote`` its push destination is pinned.

        ``pin=False`` produces the state an existing Project is in before the
        one-time pin backfill: a remote with no approved destination.
        """
        root = self.new_dir(name)
        expected = None
        if remote:
            bare = self.remote_path(name)
            git(self.tmp, "init", "--bare", "-b", "main", str(bare))
            git(root, "init", "-b", "main")
            git(root, "remote", "add", "origin", str(bare))
            expected = str(bare) if pin else None
        project_start(root, WORKLINE_ROOT, expected_push_url=expected)
        return ProjectStore(root)

    def remote_path(self, name: str = "proj") -> Path:
        return self.tmp / f"{name}-remote.git"

    def remote_url(self, name: str = "proj") -> str:
        """This Project's approved push locator, exactly as Git holds it."""
        return str(self.remote_path(name))

    # roadmap helpers ---------------------------------------------------------
    def simple_roadmap(self, store: ProjectStore, phases: dict[str, tuple[str, str]] | None = None, relations=()) -> rm.RoadmapResult:
        phases = phases or {"a": ("Phase A", "A が成立する")}
        plan = rm.RoadmapPlan(
            "Test Roadmap",
            "テスト用の背景",
            "テスト用の達成したい状態",
            {key: PhaseSpec(name, desired) for key, (name, desired) in phases.items()},
            tuple(PhaseRelationSpec(t, a, b) for t, a, b in relations),
        )
        return rm.create_roadmap(store, plan)

    def simple_entry(self, store: ProjectStore, phase_id: str, works: dict[str, str] | None = None, *, confirmation: bool = False, **kwargs) -> rm.PhaseEntryResult:
        works = works or {"w1": "W1 done"}
        design = rm.PhaseEntryDesign(
            {key: rm.WorkDesign(key.upper(), desired) for key, desired in works.items()},
            rm.WorkDesign("Integration", "全Workの統合確認が取れている"),
            rm.WorkDesign("Confirmation", "人間が成果を確認した") if confirmation else None,
            **kwargs,
        )
        return rm.enter_phase(store, phase_id, design)


def completing_executor(store: ProjectStore, log: list[str] | None = None, *, with_files: bool = True):
    """Executor that writes one result file per Work and reports completion."""

    def execute(ctx: st.ExecutionContext):
        if log is not None:
            log.append(ctx.work.id)
        if not with_files:
            return st.Completed()
        name = f"result_{ctx.work.display}.txt"
        (store.root / name).write_text(f"{ctx.work.name}\n", encoding="utf-8")
        return st.Completed((name,))

    return execute


def scripted_executor(outcomes: dict[str, list]):
    """Executor returning scripted outcomes per Work ID (last outcome repeats)."""

    def execute(ctx: st.ExecutionContext):
        queue = outcomes.get(ctx.work.id) or outcomes.get(ctx.work.name) or outcomes.get("*")
        if not queue:
            raise AssertionError(f"no scripted outcome for {ctx.work.id} ({ctx.work.name})")
        outcome = queue.pop(0) if len(queue) > 1 else queue[0]
        return outcome(ctx) if callable(outcome) else outcome

    return execute
