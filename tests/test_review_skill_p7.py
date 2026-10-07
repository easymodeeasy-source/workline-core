"""The canonical review Skill states P7 (§31.47; IR-RB7-8, written by the shared-surface writer).

* every ``review_p7_*`` code the implementation declares (scanned from ``src/workline``) is named in the Skill's P7
  section, and the section names no ``review_p7_*`` code that does not exist;
* the P7 section states the §31.47 semantics: independence / correlation, the promotion floors, the Global Policy
  Change Review, root durability, no self-hosting, the pre-change meta-policy, the exact rollback exception and the
  evaluation semantics (including Amendment 12's stranded-change gate for both root operations);
* the ``## P7 Root Review Policy`` block is exactly ``serialize.canonical_text(p4.ROOT_POLICY_RECORD)`` (RB7C-1) and
  comes after the P6 block, which - like the P5 block - stays first under its own heading;
* the P6 section keeps ``derived-baseline`` and names both P6 loader source modes.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from workline.review import global_policy, p4, policy, serialize

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "workline"
P7_HEADING = "## P7 Global Promotion / Global Policy Change"
#: Anchored on whole lines: the P7 prose may mention the block's name, never its heading line.
P7_POLICY_HEADING = "\n## P7 Root Review Policy\n"
CODE = re.compile(r"review_p7_[a-z_]*[a-z]")


def skill() -> str:
    return (ROOT / ".claude" / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8")


def section(text: str, start: str, end: str | None) -> str:
    begin = text.index(start)
    return text[begin:] if end is None else text[begin:text.index(end, begin)]


def declared_codes() -> set[str]:
    """Every ``"review_p7_*"`` string literal in the package (the declared P7 catalogue)."""
    found: set[str] = set()
    for path in sorted(SRC.rglob("*.py")):
        found |= set(re.findall(r"[\"'](review_p7_[a-z_]*[a-z])[\"']", path.read_text(encoding="utf-8")))
    return found


class P7CodeTests(unittest.TestCase):
    def test_the_p7_section_names_every_declared_p7_code_and_no_other(self) -> None:
        codes = declared_codes()
        self.assertGreaterEqual(len(codes), 38, "the scan sees the B, C and D catalogues")
        text = section(skill(), P7_HEADING, P7_POLICY_HEADING)
        for code in sorted(codes):
            with self.subTest(code=code):
                self.assertIn(f"`{code}`", text)
        self.assertEqual(set(), set(CODE.findall(skill())) - codes, "the Skill names a P7 code no module declares")

    def test_the_owner_catalogues_are_exactly_the_scanned_codes(self) -> None:
        from workline import global_policy as owner
        from workline import root_maintenance

        catalogues = (root_maintenance.STOP_CODES + root_maintenance.RECONCILE_REASONS + global_policy.STOP_CODES
                      + global_policy.RECONCILE_REASONS + owner.STOP_CODES + owner.RECONCILE_REASONS)
        self.assertEqual(len(catalogues), len(set(catalogues)), "each P7 code is declared once")
        self.assertEqual(declared_codes(), set(catalogues))


class P7SemanticsTests(unittest.TestCase):
    def test_the_p7_section_states_the_31_47_semantics(self) -> None:
        text = section(skill(), P7_HEADING, P7_POLICY_HEADING)
        for phrase in (
            # no self-hosting, the boundary
            "### self-hostingにしない", "Workline rootはWorkline Projectにならない", "`<workline-root>/.workline/`",
            "`global-policy-change`", "`global-policy-evaluation`", "`review-policy/global-policy.yaml`",
            # independence / correlation
            "### 独立性と相関", global_policy.RELATION_INDEPENDENT, global_policy.RELATION_CORRELATED,
            global_policy.RELATION_UNRESOLVED, "modelの推測でunresolvedをindependentに上げない",
            # the floors (RB7-C final semantics)
            "### 昇格の下限", "2つ以上のsource Project / repository lineage", "互いにproven independentな2つ以上のcluster",
            "3つ以上のlineageと、互いにproven independentな3つ以上のcluster", "directionの語ではなく実際の動き",
            "支持しないsourceとして除外する", "代表的なclusterの中からだけ選ぶ", "1つの機会である",
            # the Review
            "### Global Policy Change Review", global_policy.REVIEW_KIND, global_policy.TARGET_IDENTITY,
            global_policy.AUTHORIZED_OPERATION_STAGE, global_policy.CONTRACT, p4.ROOT_POLICY_ID, "`review-policy/review`",
            "Repair Batchの分岐は無い",
            # the pre-change meta-policy
            "### 変更前のmeta-policy", "`max(2, 変更前のGlobal required_slots)`", "`max(3, 変更前のGlobal required_slots)`",
            "外部reviewerの承認は失敗した項目を越えない",
            # the exact rollback exception
            "### 正確なrollbackの例外", "新しいcross-Projectの傾向なしに",
            # root durability
            "### root durability", "`.workline-root-runtime/`", "`run-workline.py root-policy-maintenance-authorize`",
            "Kp", "Km", "C-2(Kp)", "Global Policy Consumption version 4", "rebase / cherry-pick / amend / reset / forceせず",
            "`<sha>:<full ref>`",
            # Profile compatibility
            policy.COMPATIBILITY_TOTAL_ADAPTER_V1,
            # evaluation, Amendment 12
            "### evaluation", "`retain`", "`adjust`", "`rollback`", "`inconclusive`", "成功ではない",
            "時系列だけでは因果のevidenceではない", "stranded changeの入口条件",
            "`global-policy-change` も `global-policy-evaluation` も新しいroot mutationを開かず",
        ):
            with self.subTest(phrase=phrase[:60]):
                self.assertIn(phrase, text)

    def test_the_p6_section_keeps_derived_baseline_and_names_both_source_modes(self) -> None:
        text = section(skill(), "## P6 Project-local Adaptive Policy", "## P6 Review Policy")
        self.assertEqual(("derived-baseline", "materialized-global-policy"), policy.SOURCE_MODES)
        for mode in policy.SOURCE_MODES:
            with self.subTest(mode=mode):
                self.assertIn(f"`source_mode: {mode}`", text)

    def test_amendment_1_the_capability_approval_boundary_is_not_restated_here(self) -> None:
        """AO-1: P7 changes no rules/human-confirmation text; the Skill's P7 section does not route through it."""
        self.assertNotIn("rules/human-confirmation", section(skill(), P7_HEADING, P7_POLICY_HEADING))


class P7PolicyBlockTests(unittest.TestCase):
    def test_the_root_policy_block_equals_the_code_constant_and_follows_the_p6_block(self) -> None:
        text = skill()
        heading = text.index(P7_POLICY_HEADING)
        self.assertLess(text.index("## P6 Review Policy"), text.index(P7_HEADING))
        self.assertLess(text.index(P7_HEADING), heading)
        block = re.search(r"```yaml\n(.*?)```", text[heading:], re.S)
        self.assertIsNotNone(block)
        self.assertEqual(serialize.canonical_text(p4.ROOT_POLICY_RECORD), block.group(1))
        self.assertEqual(p4.ROOT_POLICY_ID, serialize.parse(block.group(1), "the P7 Root Review Policy")["policy_id"])
        p6 = re.search(r"```yaml\n(.*?)```", text[text.index("## P6 Review Policy"):], re.S)
        self.assertEqual(serialize.canonical_text(p4.P6_POLICY_RECORD), p6.group(1), "the P6 block is unchanged")


if __name__ == "__main__":
    unittest.main()
