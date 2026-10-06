"""P6 §30.33: the canonical runtime authority (Skills, rules/git) carries P6 - and the identities it binds are pinned.

* the P6 Review Policy block in ``skills/review`` equals ``p4.P6_POLICY_RECORD`` byte for byte, after the P5 block;
* the review Skill names every P6 code and reason; the roadmap / start Skills state the P6 owner duties inside their
  Review-v1 sections; the project-router states the BL-055 wording outcomes; rules/git states the exact Profile CAS
  and publication contract; no Skill or routing entry is added;
* RB6B-M5: the meta-rules, the P6 family policy record and the loader semantics identity are pinned as literals, so
  any change to them forces a new identity rather than a silent reclassification of stored P6 Runs.
"""

from __future__ import annotations

import re
import unittest

from helpers import WORKLINE_ROOT
from workline.review import p4, policy, serialize

#: RB6B-M5 literal pins. Changing any of these changes what every stored P6 Run binds: a new identity is due.
META_RULES_DIGEST = "01fb30c824b82a2dbb8aebd20943815d78dd2546f8610dba57e66517255e20a5"
P6_FAMILY_POLICY_HASH = "38f548c24aa086d18ee37b9229a38f19a53893d23349be6caf7479ca14c63e6b"
LOADER_SEMANTICS_IDENTITY = "review-v1-p6-policy-loader-v1"


def read(*parts: str) -> str:
    return WORKLINE_ROOT.joinpath(*parts).read_text(encoding="utf-8").replace("\r\n", "\n")


def section(text: str, start: str, end: str | None) -> str:
    begin = text.index(start)
    return text[begin:] if end is None else text[begin:text.index(end, begin)]


class IdentityPinTests(unittest.TestCase):
    def test_the_p6_identities_are_pinned_literals(self) -> None:
        self.assertEqual(META_RULES_DIGEST, policy.meta_rules_digest())
        self.assertEqual(P6_FAMILY_POLICY_HASH, p4.family_policy_hash(p4.P6_POLICY_ID))
        self.assertEqual(LOADER_SEMANTICS_IDENTITY, policy.LOADER_SEMANTICS_IDENTITY)


class ReviewSkillTests(unittest.TestCase):
    def test_the_p6_policy_block_equals_the_code_constant_and_follows_the_p5_block(self) -> None:
        text = read(".claude", "skills", "review", "SKILL.md")
        heading = text.index("## P6 Review Policy")
        self.assertLess(text.index("## P5 Review Policy"), text.index("## P6 Project-local Adaptive Policy"))
        self.assertLess(text.index("## P6 Project-local Adaptive Policy"), heading)
        block = re.search(r"```yaml\n(.*?)```", text[heading:], re.S)
        self.assertIsNotNone(block)
        self.assertEqual(serialize.canonical_text(p4.P6_POLICY_RECORD), block.group(1))
        p5 = re.search(r"```yaml\n(.*?)```", text[text.index("## P5 Review Policy"):], re.S)
        self.assertEqual(serialize.canonical_text(p4.P5_POLICY_RECORD), p5.group(1), "the P5 block is unchanged")

    def test_the_review_skill_names_every_p6_code_reason_and_rule(self) -> None:
        text = section(read(".claude", "skills", "review", "SKILL.md"), "## P6 Project-local Adaptive Policy",
                       "## P6 Review Policy")
        for name in policy.STOP_CODES + policy.RECONCILE_REASONS + policy.VALIDATION_CODES:
            with self.subTest(name=name):
                self.assertIn(f"`{name}`", text)
        for phrase in (policy.SURFACE_REQUIRED_SLOTS, policy.SURFACE_EXTRA_SCOPE_STEPS, "`replace_review_profile`",
                       "`.workline/review/policy/project-profile.yaml`", "`project-policy-change`", policy.REVIEW_KIND,
                       policy.TARGET_IDENTITY, policy.AUTHORIZED_OPERATION_STAGE, policy.POLICY_CHANGE_CONTRACT,
                       p4.P6_POLICY_ID, "R6-1", "R6-2", "derived-baseline", "holdout", "`retain`", "`inconclusive`",
                       "temporary_guard", "`proven_disjoint`", "backfill"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


class OwnerSkillTests(unittest.TestCase):
    PHRASES = ("R6-1", p4.P6_POLICY_ID, "`holdout_discovery`", "`review_p6_discovery_slots_unmet`",
               "`review_p6_holdout_unbound`", "`review_p6_holdout_unsettled`", "`review_p6_holdout_failed`",
               "`review_p6_profile_incompatible`", "`review_p6_lineage_invalid`", "`review.reverification.extra_scope_steps`",
               "open Runは途中でpolicyを変えない")

    def test_the_roadmap_skill_states_p6_inside_its_review_v1_section(self) -> None:
        planning = section(read(".claude", "skills", "roadmap", "SKILL.md"), "## Review-v1 planning", "## Mutation / Git")
        for phrase in self.PHRASES:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, planning)

    def test_the_start_skill_states_p6_inside_its_review_v1_section(self) -> None:
        work = section(read(".claude", "skills", "start", "SKILL.md"), "## Review-v1 Work", "## outer continuation")
        for phrase in self.PHRASES:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, work)


class RulesAndRouterTests(unittest.TestCase):
    def test_rules_git_states_the_exact_profile_cas_and_publication_contract(self) -> None:
        registry = read("registry.md")
        rules = section(registry, "<!-- workline-id: rules/git -->", "<!-- workline-id: rules/ai-decision -->")
        for phrase in ("`project-policy-change`", "`replace_review_profile`", "`.workline/review/policy/project-profile.yaml`",
                       policy.POLICY_PUBLICATION_CONTRACT, "`base_exact`", "`rules/human-confirmation`"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rules)
        self.assertNotIn("skills/project-policy", registry, "no new routing entry")

    def test_the_router_resolves_noncanonical_wording_by_meaning(self) -> None:
        router = read(".claude", "skills", "project-router", "SKILL.md")
        self.assertLess(router.index("## 選択の失敗"), router.index("## 非canonicalな言い回し"))
        self.assertLess(router.index("## 非canonicalな言い回し"), router.index("## canonical implementation first"))


if __name__ == "__main__":
    unittest.main()
