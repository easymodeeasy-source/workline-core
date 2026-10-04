"""P4 §27.28 / §27.2: the canonical runtime authority (Skills, registry) and the inert common core.

* the P4 Review Policy block in ``skills/review`` equals ``p4.POLICY_RECORD`` byte for byte;
* the review / roadmap / start Skills carry the P4 responsibilities and the canonical wording of the
  Control Plane rulings G-1 ... G-5; registry rules/git names the P4 markers and the G-2 barrier sentence;
* the P4 catalogue: every ``review_p4_*`` name in the implementation is one p4 declares, none is a P2
  catalogue name, and every one is named by the Skills;
* ``review/p4.py`` is inert: no lock, mutation, filesystem write, Git or lifecycle import.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest

from helpers import WORKLINE_ROOT
from workline.review import p4, serialize

SRC = Path(p4.__file__).resolve().parents[1]

G1 = ("P4 planning Candidate N+1 currency is proven from its immutable Repair Result, complete stored CandidateSnapshot, "
      "successor linkage, current declared base, Context, Policy and decided requirement/desired-state authority. A "
      "repaired Candidate is never reconstructed from the original Candidate-N caller request merely to test equality.")
G2 = ("The planning publication barrier proves actual registration Runs. A P4 predecessor Candidate snapshot whose Run "
      "is positively proven replaced/set aside by its committed Repair Result and deterministic successor, and which "
      "itself has no registration Consumption/registration commit, is not treated as a registration Run merely because "
      "its reserved entity paths are later registered by the successor. Missing or contradictory replacement proof "
      "fails closed.")
G3 = ("A stale P4 authorization Receipt is invalidated by a P4 G6 invalidate transition that atomically Supersedes the "
      "G5 Receipt. Repair G6 and invalidation G6 are distinct transition shapes. No G7 exists. P4 Work does not reuse "
      "F4 Class A for a G5-sealed P4 Run.")
G4 = ("A HUMAN_WAIT Run remains non-authorizing at G4. A later Human decision is supplied through the owning operation "
      "boundary as an explicit decision identity and disposition. The decision does not create a separate requirement "
      "store. A requirement change must already be reflected in its normal authority; a confirmation may leave "
      "requirement bytes unchanged. The owner binds the decision, sets the prior HUMAN_WAIT Run aside as "
      "`human_decision`, freezes a new Candidate/Context as needed, and starts a new P4 Run.")
G5 = ("The Work repair actor returns a complete repaired Candidate proposal/material and never directly mutates the "
      "canonical working tree as Review authority. After G6, the owning START alone adopts the exact proposal onto the "
      "allowed result surface using the existing ownership, overlap, witness, resulting-tree and verification "
      "machinery. The adopted Candidate must equal the persisted Candidate N+1 exactly before successor Review or Git "
      "persistence.")


def read(*parts: str) -> str:
    return (WORKLINE_ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def section(text: str, start: str, end: str | None) -> str:
    begin = text.index(start)
    return text[begin:] if end is None else text[begin:text.index(end, begin)]


class PolicyAuthorityTests(unittest.TestCase):
    def test_the_p4_policy_block_equals_the_code_constant(self) -> None:
        text = read(".claude", "skills", "review", "SKILL.md")
        heading = text.index("## P4 Review Policy")
        block = re.search(r"```yaml\n(.*?)```", text[heading:], re.S)
        self.assertIsNotNone(block, "the Review Skill declares the P4 policy record in a yaml block")
        self.assertEqual(serialize.canonical_text(p4.POLICY_RECORD), block.group(1))
        self.assertEqual(p4.POLICY_ID, serialize.parse(block.group(1), "the P4 Review Policy")["policy_id"])

    def test_the_v1_policy_blocks_stay_first_under_their_own_headings(self) -> None:
        text = read(".claude", "skills", "review", "SKILL.md")
        self.assertLess(text.index("Planning Review Policy"), text.index("## P4 Review Policy"))
        self.assertLess(text.index("**Work Review Policy**"), text.index("## P4 Review Policy"))


class SkillTests(unittest.TestCase):
    def test_the_review_skill_states_the_p4_semantics(self) -> None:
        skill = read(".claude", "skills", "review", "SKILL.md")
        p4_text = section(skill, "## P4 Repair Loop", "## P4 Review Policy")
        for phrase in (
            "discovery != adjudication", "discoveryはfreshである", "`.workline/review/reports/<result_digest>.yaml`",
            "`unsupported`", "`HUMAN`", "`Problem`", "`Improvement`", "`dismissed_non_actionable`",
            "Problem HIGH / MIDはblocking", "ImprovementはHIGH / MID / LOWのどれでも非blocking",
            "one Repair Batch per Candidate generation", "G1-G6、G7は無い", "new Candidate / new Run after repair",
            "Evidence-only positive-proof reuse", "`closure.may_reuse` を使わない", "`STRATEGY_CHANGE`", "`A_NEW`",
            "`B_RECURRENCE`", "`C_REPAIR_INDUCED`", "自動でWorkを作らない", "Reviewはlifecycle・top-level Project mutation・Git finalizationを所有しない",
            G1, G3, G4, G5,
        ):
            with self.subTest(phrase=phrase[:60]):
                self.assertIn(phrase, p4_text)

    def test_the_roadmap_skill_states_the_planning_owner_responsibilities(self) -> None:
        skill = read(".claude", "skills", "roadmap", "SKILL.md")
        planning = section(skill, "## Review-v1 planning", "## Mutation / Git")
        for phrase in (
            "review=PlanningReviewP4(", "`review-v1-planning-p4-v1`", "Candidate N+1", "後継Run", "`human_wait`",
            "最終Receiptの消費", "v1を読み替えない", "`review_marker_mismatch`", G1, G2, G4,
        ):
            with self.subTest(phrase=phrase[:60]):
                self.assertIn(phrase, planning)

    def test_the_start_skill_states_the_work_owner_responsibilities(self) -> None:
        skill = read(".claude", "skills", "start", "SKILL.md")
        work = section(skill, "## Review-v1 Work", "## outer continuation")
        for phrase in (
            "review=WorkReviewP4(", "`review-v1-work-p4-v1`", "Candidate N+1の採用（START所有）", "後継Run", "HUMAN_WAIT",
            "最終Receiptの消費とClass A", "v1を読み替えない", "operation identityは変えない", G3, G4, G5,
        ):
            with self.subTest(phrase=phrase[:60]):
                self.assertIn(phrase, work)

    def test_every_p4_code_and_reason_is_named_by_the_skills(self) -> None:
        review = section(read(".claude", "skills", "review", "SKILL.md"), "## P4 Repair Loop", "## P4 Review Policy")
        start = section(read(".claude", "skills", "start", "SKILL.md"), "## Review-v1 Work", "## outer continuation")
        roadmap = section(read(".claude", "skills", "roadmap", "SKILL.md"), "## Review-v1 planning", "## Mutation / Git")
        for name in p4.STOP_CODES + p4.RECONCILE_REASONS:
            with self.subTest(name=name):
                self.assertIn(f"`{name}`", review)
                self.assertTrue(f"`{name}`" in start or f"`{name}`" in roadmap, name)

    def test_registry_names_the_p4_markers_and_the_barrier_sentence_and_routing_is_unchanged(self) -> None:
        registry = read("registry.md")
        rules_git = registry[registry.index("<!-- workline-id: rules/git -->"):registry.index("## AI Decision")]
        for phrase in ("`review-v1-planning-p4-v1`", "`review-v1-work-p4-v1`", G2):
            with self.subTest(phrase=phrase[:60]):
                self.assertIn(phrase, rules_git)
        self.assertNotIn("skills/p4", registry, "P4 adds no Skill and changes no routing")


class CatalogueTests(unittest.TestCase):
    def test_p4_names_are_its_own_and_never_p2_catalogue_names(self) -> None:
        from test_review_planning_fold_ins import CATALOGUE_CODES, CATALOGUE_REASONS

        names = set(p4.STOP_CODES) | set(p4.RECONCILE_REASONS)
        self.assertEqual(len(names), len(p4.STOP_CODES) + len(p4.RECONCILE_REASONS))
        self.assertEqual(set(), names & (CATALOGUE_CODES | CATALOGUE_REASONS))
        self.assertTrue(all(name.startswith("review_p4_") for name in names))

    def test_every_review_p4_literal_in_the_implementation_is_declared(self) -> None:
        declared = set(p4.STOP_CODES) | set(p4.RECONCILE_REASONS) | {"review_p4_requirement_changed"}
        found: set[str] = set()
        for path in SRC.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.fullmatch(r"review_p4_[a-z_]+", node.value):
                    found.add(node.value)
        self.assertEqual(set(), found - declared)


class InertCoreTests(unittest.TestCase):
    def test_p4_imports_nothing_that_locks_mutates_writes_or_finalizes(self) -> None:
        tree = ast.parse(Path(p4.__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.add(("." * node.level) + (node.module or ""))
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        for forbidden in ("mutation", "oplock", "gitops", "gitcmd", "durable", "state", "store", "fsafe", "hermetic"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, {name.rsplit(".", 1)[-1] for name in imported})
        calls = {node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                 for node in ast.walk(tree) if isinstance(node, ast.Call)}
        for forbidden in ("open", "write_text", "write_bytes", "mkdir", "unlink", "replace", "rename"):
            with self.subTest(call=forbidden):
                self.assertNotIn(forbidden, calls)


if __name__ == "__main__":
    unittest.main()
