from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from helpers import WORKLINE_ROOT, WorklineTestCase, git
from workline import gitcmd, gitops
from workline.errors import StopError
from workline.mutation import MutationController
from workline.project_start import INITIAL_COMMIT_MESSAGE, project_start
from workline.store import ProjectStore
from workline.validate import validate_project


class ProjectStartTests(WorklineTestCase):
    def test_new_folder_is_initialized(self) -> None:
        root = self.new_dir()
        result = project_start(root, WORKLINE_ROOT)
        self.assertEqual(result.status, "initialized")
        self.assertEqual(git(root, "rev-parse", "--abbrev-ref", "HEAD").strip(), "main")
        self.assertEqual(git(root, "log", "--format=%s").splitlines(), [INITIAL_COMMIT_MESSAGE])
        tracked = set(git(root, "ls-files").splitlines())
        self.assertEqual(tracked, {
            ".workline/project.yaml",
            ".workline/relations/roadmap.yaml",
            ".workline/relations/related.yaml",
            ".workline/events/events.jsonl",
        })
        store = ProjectStore(root)
        self.assertEqual(store.workline_root(), WORKLINE_ROOT)
        self.assertEqual(validate_project(store), [])
        # empty directories exist locally but hold no placeholder
        for name in ("roadmaps", "phases", "works", "derivations"):
            self.assertTrue((store.workline / name).is_dir())
            self.assertEqual(list((store.workline / name).iterdir()), [])
        self.assertFalse(any(p.name == ".gitkeep" for p in store.workline.rglob("*")))
        self.assertEqual(git(root, "remote").strip(), "")
        # runtime metadata is not committed
        status = git(root, "status", "--porcelain", "--untracked-files=all").splitlines()
        self.assertTrue(all(".workline/runtime/" in line for line in status), status)

    def test_existing_repo_is_used(self) -> None:
        root = self.new_dir()
        git(root, "init", "-b", "main")
        (root / "README.md").write_text("hello\n", encoding="utf-8")
        git(root, "add", "README.md")
        git(root, "commit", "-m", "user commit")
        result = project_start(root, WORKLINE_ROOT)
        self.assertEqual(result.status, "initialized")
        self.assertEqual(git(root, "log", "--format=%s").splitlines(), [INITIAL_COMMIT_MESSAGE, "user commit"])
        self.assertEqual(project_start(root, WORKLINE_ROOT).status, "already_initialized")
        self.assertEqual(git(root, "log", "--format=%s").splitlines(), [INITIAL_COMMIT_MESSAGE, "user commit"])

    def test_parent_repo_subdirectory_not_ignored_stops(self) -> None:
        parent = self.new_dir("parent")
        git(parent, "init", "-b", "main")
        child = parent / "child"
        child.mkdir()
        (child / "a.txt").write_text("a\n", encoding="utf-8")
        with self.assertRaises(StopError) as ctx:
            project_start(child, WORKLINE_ROOT)
        self.assertEqual(ctx.exception.code, "parent_repo")
        self.assertFalse((child / ".workline").exists())
        self.assertFalse((child / ".git").exists())

    def _vault_parent(self) -> tuple[Path, Path]:
        """A parent repo that ignores ``child/`` and tracks nothing beneath it."""
        parent = self.new_dir("vault")
        git(parent, "init", "-b", "main")
        (parent / ".gitignore").write_text("child/\n", encoding="utf-8")
        (parent / "note.md").write_text("vault note\n", encoding="utf-8")
        git(parent, "add", ".gitignore", "note.md")
        git(parent, "commit", "-m", "vault")
        child = parent / "child"
        child.mkdir()
        return parent, child

    def _assert_parent_untouched(self, parent: Path) -> None:
        self.assertEqual(git(parent, "log", "--format=%s").splitlines(), ["vault"])
        self.assertEqual(git(parent, "status", "--porcelain", "--untracked-files=all").strip(), "")

    def test_ignored_child_of_parent_repo_auto_initializes(self) -> None:
        parent, child = self._vault_parent()
        (child / "existing.txt").write_text("mine\n", encoding="utf-8")

        result = project_start(child, WORKLINE_ROOT)

        self.assertEqual(result.status, "initialized")
        self.assertEqual(gitcmd.toplevel(child), child.resolve())
        self.assertEqual(git(child, "rev-parse", "--abbrev-ref", "HEAD").strip(), "main")
        self.assertEqual(git(child, "log", "--format=%s").splitlines(), [INITIAL_COMMIT_MESSAGE])
        self.assertEqual(set(git(child, "ls-files").splitlines()), {
            ".workline/project.yaml",
            ".workline/relations/roadmap.yaml",
            ".workline/relations/related.yaml",
            ".workline/events/events.jsonl",
        })
        self.assertEqual(validate_project(ProjectStore(child)), [])
        # a file that was already in the child is neither committed nor changed
        self.assertEqual((child / "existing.txt").read_text(encoding="utf-8"), "mine\n")
        self.assertIn("?? existing.txt", git(child, "status", "--porcelain", "--untracked-files=all"))
        self._assert_parent_untouched(parent)

    def test_ignored_child_tracked_by_parent_stops(self) -> None:
        parent, child = self._vault_parent()
        (child / "keep.txt").write_text("the vault owns this\n", encoding="utf-8")
        git(parent, "add", "-f", "child/keep.txt")
        git(parent, "commit", "-m", "vault tracks the child")

        with self.assertRaises(StopError) as ctx:
            project_start(child, WORKLINE_ROOT)

        self.assertTrue(ctx.exception.code.startswith("parent_repo"), ctx.exception.code)
        self.assertFalse((child / ".git").exists())
        self.assertFalse((child / ".workline").exists())
        self.assertEqual(git(parent, "ls-files").splitlines(), [".gitignore", "child/keep.txt", "note.md"])
        self.assertEqual(git(parent, "status", "--porcelain", "--untracked-files=all").strip(), "")

    def test_undeterminable_git_boundary_stops(self) -> None:
        parent, child = self._vault_parent()
        for name in ("is_ignored", "tracked_under"):
            with self.subTest(observation=name):
                with mock.patch(f"workline.project_start.gitcmd.{name}", return_value=None):
                    with self.assertRaises(StopError) as ctx:
                        project_start(child, WORKLINE_ROOT)
                self.assertEqual(ctx.exception.code, "git_boundary_unclear")
                self.assertFalse((child / ".git").exists())
                self.assertFalse((child / ".workline").exists())
        self._assert_parent_untouched(parent)

    def test_dirty_existing_repo_keeps_user_changes(self) -> None:
        root = self.new_dir()
        git(root, "init", "-b", "main")
        (root / "tracked.txt").write_text("v1\n", encoding="utf-8")
        git(root, "add", "tracked.txt")
        git(root, "commit", "-m", "user commit")
        (root / "tracked.txt").write_text("v2 uncommitted\n", encoding="utf-8")
        (root / "untracked.txt").write_text("mine\n", encoding="utf-8")
        (root / "staged.txt").write_text("staged\n", encoding="utf-8")
        git(root, "add", "staged.txt")
        result = project_start(root, WORKLINE_ROOT)
        self.assertEqual(result.status, "initialized")
        self.assertEqual(git(root, "log", "--format=%s").splitlines(), [INITIAL_COMMIT_MESSAGE, "user commit"])
        committed = set(git(root, "show", "--name-only", "--format=", "HEAD").split())
        self.assertNotIn("tracked.txt", committed)
        self.assertNotIn("untracked.txt", committed)
        self.assertNotIn("staged.txt", committed)
        status = git(root, "status", "--porcelain", "--untracked-files=all")
        self.assertIn(" M tracked.txt", status)
        self.assertIn("?? untracked.txt", status)
        self.assertIn("A  staged.txt", status)

    def test_pre_existing_workline_dirty_overlap_stops(self) -> None:
        root = self.new_dir()
        git(root, "init", "-b", "main")
        (root / ".workline").mkdir()
        (root / ".workline" / "project.yaml").write_text("someone else\n", encoding="utf-8")
        with self.assertRaises(StopError) as ctx:
            project_start(root, WORKLINE_ROOT)
        self.assertEqual(ctx.exception.code, "partial_workline")
        self.assertEqual((root / ".workline" / "project.yaml").read_text(encoding="utf-8"), "someone else\n")

    def test_resume_partial_mutation(self) -> None:
        root = self.new_dir()
        real_finalize = gitops.finalize
        with mock.patch("workline.project_start.gitops.finalize", side_effect=RuntimeError("crash before commit")):
            with self.assertRaises(RuntimeError):
                project_start(root, WORKLINE_ROOT)
        store = ProjectStore(root)
        self.assertTrue(store.project_yaml.is_file())
        self.assertIsNone(__import__("workline.gitcmd", fromlist=["head_commit"]).head_commit(root))
        pending = MutationController(store).list_pending()
        self.assertEqual(len(pending), 1)
        original_text = store.project_yaml.read_text(encoding="utf-8")
        writes: list[str] = []
        real_apply = MutationController.apply_effect

        def spy(self_, record):
            writes.append(record["kind"])
            return real_apply(self_, record)

        with mock.patch.object(MutationController, "apply_effect", spy):
            result = project_start(root, WORKLINE_ROOT)
        self.assertEqual(result.status, "initialized")
        self.assertTrue(result.resumed)
        self.assertEqual(result.mutation_id, pending[0]["mutation_id"])
        self.assertEqual(writes, ["git_commit"])  # matching domain files were not rewritten
        self.assertEqual(store.project_yaml.read_text(encoding="utf-8"), original_text)
        self.assertEqual(git(root, "log", "--format=%s").splitlines(), [INITIAL_COMMIT_MESSAGE])
        self.assertEqual(MutationController(store).list_pending(), [])
        self.assertIs(gitops.finalize, real_finalize)

    def test_registry_failure_stops_before_any_write(self) -> None:
        root = self.new_dir()
        bad_root = self.new_dir("bad-workline")
        with self.assertRaises(StopError) as ctx:
            project_start(root, bad_root)
        self.assertEqual(ctx.exception.code, "registry_invalid")
        self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
