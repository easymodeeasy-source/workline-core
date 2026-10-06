"""RB1 §29.26: ``status`` runs through the canonical launcher from anywhere, and is the launcher's only exception.

Every other command - every mutation-capable one included - keeps the original
binding to the configured Workline root of the Project the process works in,
and ``activate()`` is unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

from helpers import WORKLINE_ROOT, copy_workline_root, git, launcher_command, run_python
from status_helpers import StatusCase, tree_snapshot
from workline import cli
from workline.store import render_project_yaml


class LauncherStatusTests(StatusCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project("target")
        self.simple_roadmap(self.store)
        # another established Project, configured to another Workline root: the launcher of this root may not run
        # any command bound to it
        self.other_root = copy_workline_root(self.tmp / "other-root")
        self.other = self.new_project("other")
        self.other.project_yaml.write_text(render_project_yaml(self.other_root), encoding="utf-8")
        git(self.other.root, "add", ".workline/project.yaml")
        git(self.other.root, "commit", "-q", "-m", "configure another Workline root")
        self.neutral = self.new_dir("neutral")

    def status_from(self, where: Path) -> str:
        result = run_python(launcher_command(WORKLINE_ROOT, "status", self.store.root, "--json"), cwd=where)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_the_same_model_bytes_from_the_target_a_neutral_folder_and_another_project(self) -> None:
        before = {root: tree_snapshot(root) for root in (self.store.root, self.other.root)}

        inside = self.status_from(self.store.root)
        neutral = self.status_from(self.neutral)
        elsewhere = self.status_from(self.other.root)

        self.assertEqual(inside, neutral)
        self.assertEqual(inside, elsewhere)
        data = json.loads(inside)
        self.assertEqual(data["project"]["root"], str(self.store.root))
        self.assertEqual(data["authority"]["implementation"]["status"], "match")
        for root, snapshot in before.items():
            self.assertEqual(tree_snapshot(root), snapshot, f"status wrote under {root}")

    def test_the_human_rendering_runs_from_anywhere_too(self) -> None:
        result = run_python(launcher_command(WORKLINE_ROOT, "status", self.store.root), cwd=self.other.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Workline status (workline-status v1)", result.stdout)

    def test_a_relative_target_names_the_same_project(self) -> None:
        relative = run_python(launcher_command(WORKLINE_ROOT, "status", ".", "--json"), cwd=self.store.root)
        self.assertEqual(relative.returncode, 0, relative.stderr)
        self.assertEqual(relative.stdout, self.status_from(self.neutral))

    def test_every_other_command_keeps_the_working_directory_binding(self) -> None:
        commands = (
            ("validate-project", "."),
            ("validate-registry", WORKLINE_ROOT),
            ("create-work", ".", "--name", "Other", "--desired-state", "never registered"),
            ("backfill-bootstrap", "."),
            ("pin-push-destination", ".", "--url", str(self.tmp / "nowhere.git")),
            ("activate-work-terminal-review", ".", "--confirm"),
            ("project-start", str(self.tmp / "fresh"), "--workline-root", WORKLINE_ROOT),
            ("--", "status", self.store.root),  # status not in the command position stays bound
            ("bogus-command",),
        )
        before = tree_snapshot(self.other.root)
        for args in commands:
            with self.subTest(command=args[0]):
                result = run_python(launcher_command(WORKLINE_ROOT, *args), cwd=self.other.root)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("STOP [workline_implementation_mismatch]", result.stdout)
        self.assertEqual(tree_snapshot(self.other.root), before)
        self.assertFalse((self.tmp / "fresh").exists())

    def test_the_exception_is_status_alone(self) -> None:
        self.assertFalse(cli.binds_invocation_project(["status", "x"]))
        self.assertFalse(cli.binds_invocation_project(["status", "x", "--json"]))
        for argv in (["validate-project"], ["create-work", "status"], ["--", "status"], [], ["Status", "x"],
                     ["status-x", "y"], ["-h", "status"]):
            with self.subTest(argv=argv):
                self.assertTrue(cli.binds_invocation_project(argv))

    def test_api_activate_is_unchanged(self) -> None:
        driver = (
            "import runpy\n"
            f'activate = runpy.run_path(r"{WORKLINE_ROOT / "run-workline.py"}")["activate"]\n'
            "activate()\n"
            "print('ACTIVATED')\n"
        )
        bound = run_python([sys.executable, "-I", "-B", "-"], cwd=self.other.root, stdin=driver)
        self.assertEqual(bound.returncode, 1, bound.stdout + bound.stderr)
        self.assertIn("STOP [workline_implementation_mismatch]", bound.stdout)
        self.assertNotIn("ACTIVATED", bound.stdout)
        free = run_python([sys.executable, "-I", "-B", "-"], cwd=self.store.root, stdin=driver)
        self.assertEqual(free.returncode, 0, free.stdout + free.stderr)
        self.assertIn("ACTIVATED", free.stdout)

    def test_the_isolated_mode_check_still_applies_to_status(self) -> None:
        result = run_python(launcher_command(WORKLINE_ROOT, "status", self.store.root, flags=("-B",)), cwd=self.neutral)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("STOP [workline_invocation_not_isolated]", result.stdout)

    def test_another_roots_launcher_reports_the_mismatch_as_a_fact(self) -> None:
        result = run_python(launcher_command(self.other_root, "status", self.store.root, "--json"), cwd=self.store.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["authority"]["running_workline_root"]["path"], str(self.other_root))
        self.assertEqual(data["authority"]["implementation"]["status"], "mismatch")
        self.assertNotEqual(data["validation"]["status"], "pass")


if __name__ == "__main__":
    unittest.main()
