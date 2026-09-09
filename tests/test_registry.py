from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from workline.registry import REQUIRED_RULE_IDS, REQUIRED_SKILL_IDS, validate_registry


class RegistryValidationTests(unittest.TestCase):
    def _root(self) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return Path(temp.name)

    def _write_valid_registry(self, root: Path) -> None:
        lines = ["# registry", "", "## Rules"]
        for rule_id in REQUIRED_RULE_IDS:
            lines.extend([f"- id: `{rule_id}`", "  owner: registry", ""])
        lines.append("## Skills")
        for skill_id in REQUIRED_SKILL_IDS:
            target = f"{skill_id}/SKILL.md"
            lines.extend([f"- id: `{skill_id}`", f"  target: `{target}`", ""])
            path = root / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {skill_id}\n", encoding="utf-8")
        (root / "registry.md").write_text("\n".join(lines), encoding="utf-8")

    def test_valid_registry_passes(self) -> None:
        root = self._root()
        self._write_valid_registry(root)
        self.assertTrue(validate_registry(root).ok)

    def test_missing_required_rule_fails(self) -> None:
        root = self._root()
        self._write_valid_registry(root)
        registry = root / "registry.md"
        registry.write_text(registry.read_text(encoding="utf-8").replace("- id: `rules/git`", "- id: `rules/other`"), encoding="utf-8")
        codes = {problem.code for problem in validate_registry(root).problems}
        self.assertIn("required_rule_missing", codes)

    def test_duplicate_required_skill_fails(self) -> None:
        root = self._root()
        self._write_valid_registry(root)
        registry = root / "registry.md"
        registry.write_text(registry.read_text(encoding="utf-8") + "\n- id: `skills/start`\n  target: `skills/start/SKILL.md`\n", encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
