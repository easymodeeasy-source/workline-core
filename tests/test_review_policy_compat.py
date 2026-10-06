"""P6 §30.41: compatibility regression - what P6 must leave exactly as it was, and the frozen-policy property.

* old Runs keep their frozen policies: read through the Run reader after the Profile moved on disk (RB6B-L12);
* existing Projects need no backfill and Profile absence is valid; ProjectSTART and the bootstrap layout are untouched;
* dynamic registry routing, the Skill set and the capability approval boundary (rules/human-confirmation) are
  unchanged: pinned against the base commit 61b0b9dd as literals;
* the P6 modules never clean up or migrate anything (no delete, no rename, no rmtree);
* P4 / P5 semantics are unchanged except the explicit P6-capable resolution (the literal identity pins live in
  tests/test_review_policy_profile.py ``BASE_LITERALS``).
"""

from __future__ import annotations

import ast
import hashlib
import re
import unittest

from helpers import WORKLINE_ROOT, WorklineTestCase
from project_policy_helpers import PolicyCase
from workline.review import p4, paths, policy
from workline.review.store import ReviewStore
from workline.validate import validate_project

#: The routing entries of registry.md at the base commit: (workline-id, workline-target, workline-context).
BASE_ROUTING = (
    ("skills/project-start", ".claude/skills/project-start/SKILL.md", "pre-project"),
    ("skills/project-router", ".claude/skills/project-router/SKILL.md", "router"),
    ("skills/roadmap", ".claude/skills/roadmap/SKILL.md", "project"),
    ("skills/phase-create", ".claude/skills/phase-create/SKILL.md", "project"),
    ("skills/create", ".claude/skills/create/SKILL.md", "project"),
    ("skills/start", ".claude/skills/start/SKILL.md", "project"),
    ("skills/review", ".claude/skills/review/SKILL.md", "project"),
)
BASE_RULE_IDS = ("rules/git", "rules/ai-decision", "rules/human-confirmation", "rules/information-tracing")
BASE_SKILLS = ("create", "phase-create", "project-router", "project-start", "review", "roadmap", "start")
#: SHA-256 of the rules/human-confirmation section (LF) at the base commit: the capability approval boundary.
BASE_HUMAN_CONFIRMATION = "b86cfc6a9d21e1829c6ce46124ae2f189adab3d7b1d16ecea6957033b505bc79"


def registry_text() -> str:
    return (WORKLINE_ROOT / "registry.md").read_text(encoding="utf-8").replace("\r\n", "\n")


class FrozenPolicyTests(PolicyCase):
    """An open or finished Run's policy is what it froze, read back from its own requests - never re-resolved."""

    template = "profiled"

    def test_a_run_reads_the_policy_it_froze_after_the_profile_moved(self) -> None:
        review = self.review_store
        (change_id,) = review.policy_change_ids()
        run_id = review.read_policy_change(change_id)["review_run_id"]
        frozen = p4.run_effective_policy(review, review.gate_chain(run_id))
        self.assertIsNotNone(frozen)
        self.assertIsNone(frozen["profile"], "the Policy Review froze the BEFORE state: no Profile")
        current = self.state()
        self.assertIsNotNone(current.profile, "the Profile moved on disk since")
        self.assertNotEqual(current.effective, frozen)
        self.assertEqual(policy.effective_policy_hash(frozen),
                         review.gate_chain(run_id).generations[0].effective_policy_hash)
        # every evidence Run created before the change still reads the absence it froze
        for evidence_run in review.history_ids(paths.HISTORY_RUNS):
            if evidence_run == run_id:
                continue
            with self.subTest(evidence_run):
                found = p4.run_effective_policy(review, review.gate_chain(evidence_run))
                self.assertIsNotNone(found, "R6-1: a new first P4-capable Run is P6-capable")
                self.assertIsNone(found["profile"])


    def test_status_reads_the_policy_section_and_the_policy_review_run_read_only(self) -> None:
        """§30.30 / N4: the RB1 status reads a Profile-holding Project; nothing is written, review stays available."""
        from workline.status import build_status, render_human

        head, profile = self.commit_of(), self.profile_bytes()
        model = build_status(self.store.root)
        section = model.data["policy"]
        current = self.state()
        self.assertEqual({"status": "present", "version": 1, "digest": current.profile.digest}, section["profile"])
        self.assertEqual(current.effective_hash, section["effective_policy"]["hash"])
        self.assertEqual(current.effective["settings"], section["effective_policy"]["settings"])
        (change_id,) = self.review_store.policy_change_ids()
        self.assertEqual([change_id], [item["policy_change_id"] for item in section["experiments"]["items"]])
        self.assertEqual("active", section["experiments"]["items"][0]["status"])
        self.assertEqual("none", section["maintenance"]["status"])
        self.assertEqual("available", model.data["review"]["status"])
        self.assertEqual("pass", model.data["validation"]["status"])
        self.assertIn("profile: v1 ", render_human(model))
        self.assertEqual((head, profile), (self.commit_of(), self.profile_bytes()), "status writes nothing")
        self.assertEqual([], self.dirty())


class StatusShadowRenderTests(WorklineTestCase):
    """RB6FR3-2: the status human render of the shadow advisory is the detector's own ``render_lines()``, line for line
    (status renders it from the JSON projection, so every evidence line - not only the first - is pinned)."""

    def test_the_status_human_render_is_the_detectors_render_lines(self) -> None:
        from test_shadow_authority import CLAIMING_SKILL
        from workline import shadow_authority as sa
        from workline.status import build_status, render_human

        store = self.new_project("project")
        skill = store.root / ".claude" / "skills" / "tracker" / "SKILL.md"
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text(CLAIMING_SKILL, encoding="utf-8", newline="\n")
        expected = ["  " + line for line in sa.detect_shadow_authority(store.root).render_lines()]
        self.assertGreater(len(expected), 1, "the fixture yields evidence lines beyond the status line")
        rendered = render_human(build_status(store.root)).splitlines()
        start = rendered.index(expected[0])
        self.assertEqual(expected, rendered[start:start + len(expected)])


class NoBackfillTests(WorklineTestCase):
    def test_an_existing_project_needs_no_backfill_and_absence_is_valid(self) -> None:
        store = self.new_project()
        self.assertFalse((store.root / paths.POLICY_DIR).exists())
        self.assertEqual([], [problem.code for problem in validate_project(store)])
        state = policy.resolve_policy_state(ReviewStore(store), store.workline_root())
        self.assertIsNone(state.profile)

    def test_projectstart_and_the_bootstrap_never_name_p6(self) -> None:
        for name in ("project_start.py", "bootstrap.py"):
            text = (WORKLINE_ROOT / "src" / "workline" / name).read_text(encoding="utf-8")
            for needle in ("review.policy", "project_policy", "project-profile", "shadow_authority"):
                with self.subTest(module=name, needle=needle):
                    self.assertNotIn(needle, text)


class RoutingAndBoundaryTests(unittest.TestCase):
    def test_dynamic_registry_routing_and_the_skill_set_are_unchanged(self) -> None:
        text = registry_text()
        routing = tuple(re.findall(r"<!-- workline-id: (skills/[a-z-]+) -->\n<!-- workline-target: ([^ ]+) -->\n"
                                   r"<!-- workline-context: ([a-z-]+) -->", text))
        self.assertEqual(BASE_ROUTING, routing)
        rules = tuple(re.findall(r"<!-- workline-id: (rules/[a-z-]+) -->", text))
        self.assertEqual(BASE_RULE_IDS, rules)
        skills = tuple(sorted(entry.name for entry in (WORKLINE_ROOT / ".claude" / "skills").iterdir()))
        self.assertEqual(BASE_SKILLS, skills, "no new Skill, no Project-facing policy Skill")

    def test_the_capability_approval_boundary_is_unchanged(self) -> None:
        text = registry_text()
        start = text.index("<!-- workline-id: rules/human-confirmation -->")
        end = text.index("<!-- workline-id:", start + 10)
        self.assertEqual(BASE_HUMAN_CONFIRMATION, hashlib.sha256(text[start:end].encode("utf-8")).hexdigest())


class NoCleanupTests(unittest.TestCase):
    def test_the_p6_modules_never_delete_rename_or_migrate(self) -> None:
        forbidden = {"unlink", "rmtree", "remove", "rmdir", "rename", "removedirs"}
        for module in ("review/policy.py", "project_policy.py"):
            tree = ast.parse((WORKLINE_ROOT / "src" / "workline" / module).read_text(encoding="utf-8"))
            calls = {node.func.attr for node in ast.walk(tree)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
            with self.subTest(module):
                self.assertEqual(set(), calls & forbidden)


if __name__ == "__main__":
    unittest.main()
