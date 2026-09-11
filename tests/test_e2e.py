"""End-to-end scenario with temporary local Git repositories (no GitHub access)."""

from __future__ import annotations

import subprocess
import unittest

from helpers import WORKLINE_ROOT, WorklineTestCase, git, launcher_command
from workline import roadmap as rm
from workline import start as st
from workline.create import RelatedSpec
from workline.mutation import MutationController
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.project_start import project_start
from workline.state import ProjectView
from workline.store import ProjectStore
from workline.validate import validate_project


class EndToEndTests(WorklineTestCase):
    def _run(self, store: ProjectStore) -> None:
        # Roadmap ----------------------------------------------------------------
        plan = rm.RoadmapPlan(
            "CLI 電卓",
            "計算を CLI から素早く行いたい",
            "四則演算が CLI から実行でき、結果が正しい",
            {"core": PhaseSpec("計算コア", "四則演算関数が正しい"), "cli": PhaseSpec("CLI", "CLI から計算できる")},
            (PhaseRelationSpec("requires_completion", "core", "cli"), PhaseRelationSpec("planned_next", "core", "cli")),
            scope="四則演算のみ",
        )
        roadmap = rm.create_roadmap(store, plan)
        core, cli = roadmap.phase_ids["core"], roadmap.phase_ids["cli"]

        # Phase CREATE happened inside Roadmap; entering the first Phase expands Works
        selected = rm.select_phase(store, roadmap.roadmap_id)
        self.assertEqual(selected.id, core)
        design = rm.PhaseEntryDesign(
            {
                "add": rm.WorkDesign("加算", "add(a, b) が正しい", (RelatedSpec("must_update", "calc.py"),)),
                "mul": rm.WorkDesign("乗算", "mul(a, b) が正しい"),
            },
            rm.WorkDesign("コア統合確認", "全関数のテストが通る"),
            rm.WorkDesign("コア人間確認", "人間が API 形を承認した"),
            planned_next=(("add", "mul"),),
            entry="add",
        )
        entry = rm.enter_phase(store, core, design)

        def executor(ctx: st.ExecutionContext):
            self.assertIn(ctx.work.path, ctx.reading_plan)
            calc = store.root / "calc.py"
            if ctx.work.name == "加算":
                calc.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
                return st.Completed(("calc.py",))
            if ctx.work.name == "乗算":
                calc.write_text(calc.read_text(encoding="utf-8") + "\n\ndef mul(a, b):\n    return a * b\n", encoding="utf-8")
                return st.Completed(("calc.py",))
            if ctx.work.name == "CLI":
                (store.root / "cli.py").write_text("import calc\n", encoding="utf-8")
                return st.Completed(("cli.py",))
            return st.Completed()

        first = rm.handoff(store, core, executor, entry.entry_work_id)
        self.assertEqual(first.status, "phase_complete")
        self.assertEqual(ProjectView.load(store).phase_state(core), "complete")
        self.assertEqual(rm.evaluate_achievement(store, roadmap.roadmap_id, "achieved").status, "not_ready")

        # next Phase is selected by Roadmap, never by START
        nxt = rm.select_phase(store, roadmap.roadmap_id)
        self.assertEqual(nxt.id, cli)
        entry2 = rm.enter_phase(store, cli, rm.PhaseEntryDesign({"cli": rm.WorkDesign("CLI", "cli.py がある")}, rm.WorkDesign("CLI統合確認", "CLI 経由で結果が正しい")))
        second = rm.handoff(store, cli, executor, entry2.entry_work_id)
        self.assertEqual(second.status, "phase_complete")
        self.assertIsNone(rm.select_phase(store, roadmap.roadmap_id))

        achievement = rm.evaluate_achievement(store, roadmap.roadmap_id, "achieved", "四則演算が CLI から実行できることを確認")
        self.assertEqual(achievement.status, "achieved")
        view = ProjectView.load(store)
        self.assertEqual(view.roadmap_lifecycle(roadmap.roadmap_id), "achieved")
        self.assertEqual(validate_project(store), [])
        self.assertEqual(MutationController(store).list_pending(), [])
        for work in view.works.values():
            self.assertEqual(view.work_state(work.id).state, "completed")
            self.assertNotIn("state", work.meta)
        dirty = [line for line in git(store.root, "status", "--porcelain", "--untracked-files=all").splitlines() if ".workline/runtime/" not in line]
        self.assertEqual(dirty, [])
        self.assertEqual(git(store.root, "log", "--format=%s").splitlines()[-1], "chore(workline): initialize project")

    def test_full_scenario_without_remote(self) -> None:
        root = self.new_dir()
        self.assertEqual(project_start(root, WORKLINE_ROOT).status, "initialized")
        self.enter(root)
        self._run(ProjectStore(root))

    def test_full_scenario_with_local_remote(self) -> None:
        store = self.new_project(remote=True)
        self._run(store)
        self.assertEqual(git(store.root, "rev-parse", "HEAD").strip(), git(self.remote_path(), "rev-parse", "main").strip())

    def test_cli_entry_points(self) -> None:
        root = self.new_dir()
        # the canonical invocation: this Workline root's launcher, isolated and without bytecode, no PYTHONPATH
        run = lambda *args, cwd=WORKLINE_ROOT: subprocess.run(launcher_command(WORKLINE_ROOT, *args), capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
        started = run("project-start", str(root), "--workline-root", str(WORKLINE_ROOT))
        self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
        # an established Project is changed from inside it; validation below reads it from the Workline root
        created = run("create-work", str(root), "--name", "Doc", "--desired-state", "docs exist", "--must-read", "README.md", cwd=root)
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        checked = run("validate-project", str(root))
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertIn("PASS", checked.stdout)
        registry = run("validate-registry", str(WORKLINE_ROOT))
        self.assertEqual(registry.returncode, 0)
        self.assertIn("PASS", registry.stdout)


if __name__ == "__main__":
    unittest.main()
