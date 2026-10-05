"""RB4 / P5 §28.24: the canonical runtime authority (Skills) carries P5, and the Control Plane GAP-A ... GAP-G wording.

* the P5 Review Policy block in ``skills/review`` equals ``p4.P5_POLICY_RECORD`` byte for byte, after the P4 block
  (which stays the first yaml block under its own heading);
* the review Skill states every §28.24 item; the start / roadmap Skills state the owner responsibilities at the
  exact transition boundaries, inside their Review-v1 sections only;
* every canonical runtime wording of the rulings appears where its owner states it, GAP-D in the create Skill;
* every P5 code / reason is named by the review Skill and by an owner Skill; registry routing is unchanged.
"""

from __future__ import annotations

import re
import unittest

from helpers import WORKLINE_ROOT
from workline.review import history, p4, serialize

GAP_A = ("P5 capability is an explicit per-Run stored Review policy/history-contract property within the P4-capable "
         "owner family. New first Runs use the P5-capable policy after P5 activation; a cycle keeps the policy/history "
         "family of its first Run. Existing P4-only Runs are never upgraded by file presence, current code, or shape "
         "inference.")
GAP_B = ("History namespace structure is validated by the shared Review readers. Cross-source history semantics are "
         "validated separately. A P5 history defect blocks the P5 transition whose stored contract requires that "
         "history; it does not become a new lifecycle gate for unrelated pre-P5 or P4-only operations.")
GAP_C = ("A P5-capable adjudication receives a deterministic validated prior-history reference set for the same "
         "target/review kind and may return structured cross-run relation claims. Accepted relations are immutable new "
         "G4 facts; they never rewrite prior Findings or Runs.")
GAP_E = ("A P5 Run whose canonical G2 settlement makes discovery non-authorizing receives its immutable not_authorized "
         "Run summary in that same G2 transition.")
GAP_F = ("`authorized` and `historical_escape` remain reserved Run-disposition vocabulary values, but P5 writes neither "
         "until a canonical source transition exists that can prove that final disposition. Downstream escape is "
         "represented by an immutable relation, never by rewriting a prior Run verdict.")
GAP_G = ("Human Decision Evidence explicitly identifies the prior HUMAN_WAIT Run and candidate affected by the decision. "
         "The owner validates that exact canonical G4 HUMAN state, sets that Run aside as `human_decision`, persists one "
         "immutable evidence record before the resumed external Review launch, and separately proves the current "
         "canonical requirement/authority. Evidence never substitutes for requirement authority.")
GAP_D = ("Future Work provenance is optional explicit CREATE input. P5 never schedules or creates Work automatically. "
         "When source_finding_id is supplied and valid, CREATE persists one future_work_link relation in the same "
         "canonical owner commit as the Work without changing Work progression or originating completion dependencies.")


def read(*parts: str) -> str:
    return WORKLINE_ROOT.joinpath(*parts).read_text(encoding="utf-8")


def section(text: str, start: str, end: str | None) -> str:
    begin = text.index(start)
    return text[begin:] if end is None else text[begin:text.index(end, begin)]


class PolicyAuthorityTests(unittest.TestCase):
    def test_the_p5_policy_block_equals_the_code_constant_and_follows_the_p4_block(self) -> None:
        text = read(".claude", "skills", "review", "SKILL.md")
        heading = text.index("## P5 Review Policy")
        self.assertLess(text.index("## P4 Review Policy"), text.index("## P5 Review History"))
        self.assertLess(text.index("## P5 Review History"), heading)
        block = re.search(r"```yaml\n(.*?)```", text[heading:], re.S)
        self.assertIsNotNone(block)
        self.assertEqual(serialize.canonical_text(p4.P5_POLICY_RECORD), block.group(1))
        record = serialize.parse(block.group(1), "the P5 Review Policy")
        self.assertEqual((p4.P5_POLICY_ID, p4.P5_ADJUDICATION_INSTRUCTION, history.HISTORY_CONTRACT),
                         (record["policy_id"], record["adjudication"]["instruction"], record["history"]["contract"]))

    def test_the_p5_policy_keeps_every_p4_rule(self) -> None:
        for key, value in p4.POLICY_RECORD.items():
            if key in ("schema", "policy_id", "adjudication"):
                continue
            with self.subTest(key=key):
                self.assertEqual(value, p4.P5_POLICY_RECORD[key])
        for key, value in p4.POLICY_RECORD["adjudication"].items():
            if key != "instruction":
                self.assertEqual(value, p4.P5_POLICY_RECORD["adjudication"][key])


class SkillTests(unittest.TestCase):
    def test_the_review_skill_states_every_28_24_item_and_the_rulings(self) -> None:
        text = section(read(".claude", "skills", "review", "SKILL.md"), "## P5 Review History", "## P5 Review Policy")
        for phrase in (
            "lifecycleの正本ではない", ".workline/review/history/", "immutable create-only", "backfillはしない",
            "H-3", "自動でWorkを作らない", "端点のrecordを書き換えない", "`supported`・`unresolved`・`insufficient_evidence`",
            "Evidence never substitutes for requirement authority", "`require_history_ready`", "`not_required_by_contract`",
            "`p4.DecisionEvidence`", "P4-onlyのcycleは従来どおり", "`skills/create` のfuture Work provenance",
            GAP_A, GAP_B, GAP_C, GAP_D, GAP_E, GAP_F, GAP_G,
        ):
            with self.subTest(phrase=phrase[:60]):
                self.assertIn(phrase, text)
        self.assertNotIn("WAIT_EXACT", text, "GAP-D is implemented: no WAIT clause is left")

    def test_the_start_skill_states_the_work_owner_duties_inside_its_review_v1_section(self) -> None:
        work = section(read(".claude", "skills", "start", "SKILL.md"), "## Review-v1 Work", "## outer continuation")
        for phrase in (GAP_A, GAP_E, GAP_G, "`decision_evidence=(DecisionEvidence(...),)`", "P4-R7の待っているRunそのもの",
                       "consumed Run summaryのcreateを先頭に", "T4", "T8", "P-6", "P4-onlyのcycleは従来どおり"):
            with self.subTest(phrase=phrase[:60]):
                self.assertIn(phrase, work)

    def test_the_roadmap_skill_states_the_planning_owner_duties_inside_its_review_v1_section(self) -> None:
        skill = read(".claude", "skills", "roadmap", "SKILL.md")
        planning = section(skill, "## Review-v1 planning", "## Mutation / Git")
        for phrase in (GAP_A, GAP_C, GAP_E, GAP_G, "Run summaryとConsumptionの2つだけ", "operation identityが変わる",
                       "P4-onlyのcycleは従来どおり"):
            with self.subTest(phrase=phrase[:60]):
                self.assertIn(phrase, planning)
        scope = skill[skill.index("各Roadmap operationが宣言する予定write scope"):]
        self.assertIn("1つだけ例外", scope)
        self.assertIn("`.workline/review/history/runs/<review_run_id>.yaml`", scope)

    def test_every_p5_code_and_reason_is_named_by_the_review_skill_and_an_owner_skill(self) -> None:
        review = section(read(".claude", "skills", "review", "SKILL.md"), "## P5 Review History", "## P5 Review Policy")
        start = section(read(".claude", "skills", "start", "SKILL.md"), "## Review-v1 Work", "## outer continuation")
        roadmap = section(read(".claude", "skills", "roadmap", "SKILL.md"), "## Review-v1 planning", "## Mutation / Git")
        for name in history.STOP_CODES + history.RECONCILE_REASONS:
            with self.subTest(name=name):
                self.assertIn(f"`{name}`", review)
                self.assertIn(f"`{name}`", start)
                self.assertIn(f"`{name}`", roadmap)

    def test_registry_routing_is_unchanged_and_create_states_the_gap_d_input(self) -> None:
        registry = read("registry.md")
        self.assertNotIn("history_contract", registry)
        self.assertNotIn("skills/p5", registry)
        create = read(".claude", "skills", "create", "SKILL.md")
        # GAP-D (a): the create Skill states the explicit CREATE input, its relation path and the ruling's wording
        for phrase in (GAP_D, "`source_finding_id`", "`--source-finding-id <finding ID>`",
                       "`create_standalone_work(..., source_finding_id=...)`",
                       "`.workline/review/history/relations/<予約したreview_relation ID>.yaml`",
                       "`review_p5_history_missing`", "`review_p5_history_invalid`", "`review_p5_history_conflict`"):
            with self.subTest(phrase=phrase[:60]):
                self.assertIn(phrase, create)
        self.assertNotIn("WAIT_EXACT", create)


if __name__ == "__main__":
    unittest.main()
