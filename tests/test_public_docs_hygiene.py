"""The canonical ProjectSTART text and the README say what the registry and the repository really are (RB10 §18.12-13).

ProjectSTART resolves the registry's required Skill IDs, and the registry requires seven - project-start,
project-router, roadmap, phase-create, create, start and review - where its text still said five. The count is
read here from ``registry.REQUIRED_SKILL_IDS``, the set the implementation checks, not from another hand-kept number.

The README names no personal clone path and no retired design Vault as an authority: it describes the Workline
root and a Project portably and routes authority to ``registry.md`` and the canonical Skills.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from workline.registry import REQUIRED_RULE_IDS, REQUIRED_SKILL_IDS

ROOT = Path(__file__).resolve().parents[1]
PROJECT_START = ROOT / ".claude" / "skills" / "project-start" / "SKILL.md"
README = ROOT / "README.md"
REGISTRY = ROOT / "registry.md"


class ProjectStartSkillCountTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = PROJECT_START.read_text(encoding="utf-8")

    def test_the_stated_counts_are_the_registry_s_required_sets(self) -> None:
        preflight = re.search(r"必須(\d+) rule IDと必須(\d+) Skill IDを一意解決する", self.text)
        self.assertIsNotNone(preflight, "the preflight states both required sets")
        self.assertEqual((int(preflight.group(1)), int(preflight.group(2))), (len(REQUIRED_RULE_IDS), len(REQUIRED_SKILL_IDS)))
        postcheck = re.search(r"^- 必須(\d+) Skill IDが一意解決$", self.text, re.MULTILINE)
        self.assertIsNotNone(postcheck, "the postcheck states the required Skill set")
        self.assertEqual(int(postcheck.group(1)), len(REQUIRED_SKILL_IDS))

    def test_no_stale_skill_count_is_left(self) -> None:
        for stale in ("5 Skill ID", "5 common Skills", "common Skills"):
            self.assertNotIn(stale, self.text)
        for number in re.findall(r"(\d+) (?:common )?Skills?\b", self.text):
            self.assertEqual(int(number), len(REQUIRED_SKILL_IDS))

    def test_every_required_skill_is_routed_by_the_registry(self) -> None:
        routed = set(re.findall(r"<!-- workline-id: (skills/[a-z-]+) -->", REGISTRY.read_text(encoding="utf-8")))
        self.assertLessEqual(set(REQUIRED_SKILL_IDS), routed)
        self.assertEqual(len(REQUIRED_SKILL_IDS), 7)


class ReadmeHygieneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = README.read_text(encoding="utf-8")

    def test_no_personal_absolute_path(self) -> None:
        self.assertIsNone(re.search(r"\b[A-Za-z]:\\", self.text), "no drive-rooted Windows path")
        self.assertNotIn("AIproject", self.text)
        self.assertIsNone(re.search(r"(?m)(^|\s)/(home|Users)/", self.text), "no home-directory path")

    def test_no_retired_vault_authority(self) -> None:
        self.assertNotIn("aiproject-vault", self.text)
        self.assertNotIn("new-dev-os-redesign", self.text)
        self.assertNotRegex(self.text.lower(), r"\bvault\b")

    def test_roots_are_named_portably_and_authority_is_canonical(self) -> None:
        for placeholder in ("<workline-root>", "<project-root>", "<R>"):
            self.assertIn(placeholder, self.text)
        authority = self.text.split("## Authority", 1)[1].split("\n## ", 1)[0]
        self.assertIn("registry.md", authority)
        self.assertIn(".claude/skills/<name>/SKILL.md", authority)


if __name__ == "__main__":
    unittest.main()
