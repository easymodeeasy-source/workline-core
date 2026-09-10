from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from workline.errors import StopError
from workline.registry import (
    CONTEXT_PRE_PROJECT,
    CONTEXT_PROJECT,
    CONTEXT_ROUTER,
    PROJECT_ROUTER_SKILL_ID,
    PROJECT_START_SKILL_ID,
    REQUIRED_RULE_IDS,
    REQUIRED_SKILL_IDS,
    owning_workline_root,
    resolve_skill,
    router_candidates,
    skill_inventory,
    validate_registry,
)


class RegistryFixture(unittest.TestCase):
    """Builds throwaway Workline roots; holds no tests of its own."""

    def _root(self) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return Path(temp.name)

    def _context_of(self, skill_id: str) -> str:
        if skill_id == PROJECT_START_SKILL_ID:
            return CONTEXT_PRE_PROJECT
        if skill_id == PROJECT_ROUTER_SKILL_ID:
            return CONTEXT_ROUTER
        return CONTEXT_PROJECT

    def _add_skill(self, root: Path, lines: list[str], skill_id: str, context: str | None) -> None:
        target = f"{skill_id}/SKILL.md"
        lines.extend([f"<!-- workline-id: {skill_id} -->", f"<!-- workline-target: {target} -->"])
        if context is not None:
            lines.append(f"<!-- workline-context: {context} -->")
        lines.append("")
        path = root / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {skill_id}\n", encoding="utf-8")

    def _write_valid_registry(self, root: Path, extra_skills: dict[str, str] | None = None) -> None:
        lines = ["# registry", "", "## Rules"]
        for rule_id in REQUIRED_RULE_IDS:
            lines.extend([f"<!-- workline-id: {rule_id} -->", ""])
        lines.append("## Skills")
        for skill_id in REQUIRED_SKILL_IDS:
            self._add_skill(root, lines, skill_id, self._context_of(skill_id))
        for skill_id, context in (extra_skills or {}).items():
            self._add_skill(root, lines, skill_id, context)
        (root / "registry.md").write_text("\n".join(lines), encoding="utf-8")


class RegistryValidationTests(RegistryFixture):
    def test_valid_registry_passes(self) -> None:
        root = self._root()
        self._write_valid_registry(root)
        self.assertTrue(validate_registry(root).ok)

    def test_missing_required_rule_fails(self) -> None:
        root = self._root()
        self._write_valid_registry(root)
        registry = root / "registry.md"
        registry.write_text(registry.read_text(encoding="utf-8").replace("<!-- workline-id: rules/git -->", "<!-- workline-id: rules/other -->"), encoding="utf-8")
        codes = {problem.code for problem in validate_registry(root).problems}
        self.assertIn("required_rule_missing", codes)

    def test_duplicate_required_skill_fails(self) -> None:
        root = self._root()
        self._write_valid_registry(root)
        registry = root / "registry.md"
        registry.write_text(registry.read_text(encoding="utf-8") + "\n<!-- workline-id: skills/start -->\n<!-- workline-target: skills/start/SKILL.md -->\n", encoding="utf-8")
        codes = {problem.code for problem in validate_registry(root).problems}
        self.assertIn("duplicate_skill", codes)

    def test_missing_target_file_fails(self) -> None:
        root = self._root()
        self._write_valid_registry(root)
        (root / "skills/start/SKILL.md").unlink()
        codes = {problem.code for problem in validate_registry(root).problems}
        self.assertIn("skill_target_unreadable", codes)

    def test_empty_target_file_fails(self) -> None:
        root = self._root()
        self._write_valid_registry(root)
        (root / "skills/start/SKILL.md").write_text("", encoding="utf-8")
        codes = {problem.code for problem in validate_registry(root).problems}
        self.assertIn("skill_target_empty", codes)

    def test_target_cannot_escape_root(self) -> None:
        root = self._root()
        self._write_valid_registry(root)
        registry = root / "registry.md"
        registry.write_text(registry.read_text(encoding="utf-8").replace("skills/start/SKILL.md", "../outside/SKILL.md"), encoding="utf-8")
        codes = {problem.code for problem in validate_registry(root).problems}
        self.assertIn("skill_target_outside_root", codes)

    def test_missing_target_marker_fails(self) -> None:
        root = self._root()
        self._write_valid_registry(root)
        registry = root / "registry.md"
        registry.write_text(registry.read_text(encoding="utf-8").replace("<!-- workline-target: skills/start/SKILL.md -->", ""), encoding="utf-8")
        codes = {problem.code for problem in validate_registry(root).problems}
        self.assertIn("skill_target_missing", codes)

    def test_duplicate_required_rule_fails(self) -> None:
        root = self._root()
        self._write_valid_registry(root)
        registry = root / "registry.md"
        registry.write_text(registry.read_text(encoding="utf-8") + "\n<!-- workline-id: rules/git -->\n", encoding="utf-8")
        codes = {problem.code for problem in validate_registry(root).problems}
        self.assertIn("duplicate_rule", codes)

    def test_repository_registry_passes(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        result = validate_registry(repo_root)
        self.assertTrue(result.ok, result.problems)


class OwningWorklineRootTests(RegistryFixture):
    """Workline root is read off the executing Skill, never searched for."""

    def _root_with_skill(self, name: str = "root") -> tuple[Path, Path]:
        root = self._root() / name
        root.mkdir(parents=True)
        self._write_valid_registry(root)
        return root, root / "skills" / "project-start" / "SKILL.md"

    def test_resolves_the_root_that_routes_back_to_the_skill(self) -> None:
        root, skill = self._root_with_skill()
        self.assertEqual(owning_workline_root(skill), root.resolve())

    def test_sibling_workline_root_is_never_considered(self) -> None:
        parent = self._root()
        (parent / "a").mkdir()
        self._write_valid_registry(parent / "a")
        root_b = parent / "b"
        root_b.mkdir()
        self._write_valid_registry(root_b)
        # `a` is the older sibling and `b` the newer one; neither fact is consulted
        self.assertEqual(
            owning_workline_root(root_b / "skills" / "project-start" / "SKILL.md"),
            root_b.resolve(),
        )
        self.assertEqual(
            owning_workline_root((parent / "a") / "skills" / "project-start" / "SKILL.md"),
            (parent / "a").resolve(),
        )

    def test_routing_that_does_not_return_to_the_skill_is_a_routing_error(self) -> None:
        root, skill = self._root_with_skill()
        registry = root / "registry.md"
        registry.write_text(
            registry.read_text(encoding="utf-8").replace(
                "<!-- workline-target: skills/project-start/SKILL.md -->",
                "<!-- workline-target: skills/start/SKILL.md -->",
            ),
            encoding="utf-8",
        )
        with self.assertRaises(StopError) as ctx:
            owning_workline_root(skill)
        self.assertEqual(ctx.exception.code, "routing_error")

    def test_invalid_owning_registry_is_a_routing_error(self) -> None:
        root, skill = self._root_with_skill()
        (root / "skills" / "start" / "SKILL.md").unlink()
        with self.assertRaises(StopError) as ctx:
            owning_workline_root(skill)
        self.assertEqual(ctx.exception.code, "routing_error")

    def test_skill_without_an_owning_registry_is_a_routing_error(self) -> None:
        orphan = self._root() / "skills" / "project-start"
        orphan.mkdir(parents=True)
        skill = orphan / "SKILL.md"
        skill.write_text("# orphan\n", encoding="utf-8")
        with self.assertRaises(StopError) as ctx:
            owning_workline_root(skill)
        self.assertEqual(ctx.exception.code, "routing_error")

    def test_missing_skill_file_is_a_routing_error(self) -> None:
        root, _ = self._root_with_skill()
        with self.assertRaises(StopError) as ctx:
            owning_workline_root(root / "skills" / "project-start" / "ABSENT.md")
        self.assertEqual(ctx.exception.code, "routing_error")

    def test_repository_skill_resolves_to_the_repository_root(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        skill = repo_root / ".claude" / "skills" / "project-start" / "SKILL.md"
        self.assertEqual(owning_workline_root(skill), repo_root)


class CanonicalSkillLayoutTests(unittest.TestCase):
    """The canonical Skills live where Claude Code discovers them, exactly once."""

    REPO_ROOT = Path(__file__).resolve().parents[1]
    SKILL_NAMES = ("project-start", "project-router", "roadmap", "phase-create", "create", "start")

    def test_skills_are_under_the_claude_skills_directory(self) -> None:
        for name in self.SKILL_NAMES:
            with self.subTest(skill=name):
                skill = self.REPO_ROOT / ".claude" / "skills" / name / "SKILL.md"
                self.assertTrue(skill.is_file(), skill)
                self.assertTrue(skill.read_text(encoding="utf-8").strip())

    def test_pre_move_skill_location_is_gone(self) -> None:
        self.assertFalse((self.REPO_ROOT / "skills").exists())

    def test_each_canonical_skill_exists_exactly_once(self) -> None:
        for name in self.SKILL_NAMES:
            with self.subTest(skill=name):
                found = [
                    p for p in self.REPO_ROOT.rglob("SKILL.md")
                    if p.parent.name == name and ".git" not in p.parts
                ]
                self.assertEqual(len(found), 1, found)

    def test_registry_routes_every_skill_to_the_claude_skills_directory(self) -> None:
        text = (self.REPO_ROOT / "registry.md").read_text(encoding="utf-8")
        for skill_id in REQUIRED_SKILL_IDS:
            with self.subTest(skill=skill_id):
                name = skill_id.split("/")[-1]
                self.assertIn(f"<!-- workline-target: .claude/skills/{name}/SKILL.md -->", text)
                # identity stays path-independent
                self.assertIn(f"<!-- workline-id: {skill_id} -->", text)

    def test_non_project_start_skills_require_an_established_project(self) -> None:
        for name in self.SKILL_NAMES:
            if name == "project-start":
                continue
            with self.subTest(skill=name):
                text = (self.REPO_ROOT / ".claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
                description = text.split("---")[1]
                self.assertIn(".workline/project.yaml", description)

    def test_project_start_is_the_pre_project_skill(self) -> None:
        text = (self.REPO_ROOT / ".claude" / "skills" / "project-start" / "SKILL.md").read_text(encoding="utf-8")
        description = text.split("---")[1]
        self.assertIn("before a Workline Project exists", description)


if __name__ == "__main__":
    unittest.main()
