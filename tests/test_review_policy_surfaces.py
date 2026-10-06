"""P6 §30.34: the fixed two-surface adaptive registry (WORKLINE_COMPLETION_SPRINT §30.2-§30.3, §15.10-§15.11).

* exactly two v1 surfaces, with their fixed strength class, Global setting and allowed range;
* an unknown surface and the absolute non-adaptive surface are rejected mechanically;
* the strength order (higher is stronger) and the P4 floor: a Profile only ever adds verification;
* a Profile can neither reclassify a surface nor invent one;
* the semantic core is inert: no lock, mutation, filesystem write, Git or lifecycle import.
"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from helpers import WORKLINE_ROOT  # noqa: F401  (puts this worktree's src first)
from workline.review import p4, policy, records

RPC = "rpc_01ARZ3NDEKTSV4RRFFQ69G5FAV"


def override(surface: str = policy.SURFACE_REQUIRED_SLOTS, setting: int = 2, **changes: object) -> dict:
    found = policy.SURFACE_BY_ID.get(surface)
    item = {
        "policy_surface_id": surface,
        "strength_class": found.strength_class if found else policy.CLASS_DEFAULT,
        "setting": setting,
        "direction": policy.DIRECTION_STRENGTHEN,
        "supporting_policy_change_id": RPC,
    }
    item.update(changes)
    return item


def profile_record(*overrides: dict, refs: tuple[str, ...] = (RPC,)) -> dict:
    return {
        "schema": policy.SCHEMA_PROFILE, "version": 1, "profile_version": 1, "parent_profile_digest": None,
        "global_baseline_digest": "a" * 64, "global_baseline_version": 1,
        "loader_semantics_identity": policy.LOADER_SEMANTICS_IDENTITY,
        "overrides": list(overrides), "active_experiment_refs": list(refs),
    }


class RegistryTests(unittest.TestCase):
    def test_exactly_two_v1_surfaces(self) -> None:
        self.assertEqual((policy.SURFACE_REQUIRED_SLOTS, policy.SURFACE_EXTRA_SCOPE_STEPS),
                         tuple(surface.policy_surface_id for surface in policy.SURFACES))
        self.assertEqual("review.discovery.required_slots", policy.SURFACE_REQUIRED_SLOTS)
        self.assertEqual("review.reverification.extra_scope_steps", policy.SURFACE_EXTRA_SCOPE_STEPS)
        self.assertEqual(2, len(policy.SURFACE_BY_ID))

    def test_required_slots_is_default_class_global_one_range_one_to_four(self) -> None:
        surface = policy.SURFACE_BY_ID[policy.SURFACE_REQUIRED_SLOTS]
        self.assertEqual((policy.CLASS_DEFAULT, 1, 1, 4),
                         (surface.strength_class, surface.global_setting, surface.minimum, surface.maximum))
        for value in (1, 2, 3, 4):
            self.assertTrue(surface.in_range(value))
        for value in (0, 5, -1, True, "2", 2.0, None):
            with self.subTest(value=value):
                self.assertFalse(surface.in_range(value))

    def test_extra_scope_steps_is_adaptive_class_global_zero_range_zero_to_three(self) -> None:
        surface = policy.SURFACE_BY_ID[policy.SURFACE_EXTRA_SCOPE_STEPS]
        self.assertEqual((policy.CLASS_ADAPTIVE, 0, 0, 3),
                         (surface.strength_class, surface.global_setting, surface.minimum, surface.maximum))
        for value in (0, 1, 2, 3):
            self.assertTrue(surface.in_range(value))
        for value in (-1, 4, False, "1"):
            with self.subTest(value=value):
                self.assertFalse(surface.in_range(value))

    def test_no_surface_is_mandatory_and_none_is_learned(self) -> None:
        self.assertNotIn(policy.CLASS_MANDATORY, {surface.strength_class for surface in policy.SURFACES})
        self.assertEqual(policy.STRENGTH_ORDER_HIGHER, policy.SURFACES[0].to_record()["strength_order"])


class RejectionTests(unittest.TestCase):
    def test_an_unknown_surface_is_rejected(self) -> None:
        for surface in ("review.discovery.extra", "review.discovery.required_slot", "x.y", "", None, 3):
            with self.subTest(surface=surface):
                code, _ = policy.surface_problem(surface)
                self.assertEqual(policy.CODE_SURFACE_UNKNOWN, code)
                with self.assertRaises(Exception) as raised:
                    policy.require_surface(surface)
                self.assertEqual(policy.CODE_SURFACE_UNKNOWN, raised.exception.code)

    def test_the_absolute_non_adaptive_surface_is_rejected_mechanically(self) -> None:
        for surface in ("review.severity.blocking", "lifecycle.completion", "review.human_boundary",
                        "review.requirement.meaning", "routing.owner", "review.authorization.consumption",
                        "mutation.git_safety", "review.finding.category", "local.capability_approval",
                        "security.destructive_operations", "work.completion"):
            with self.subTest(surface=surface):
                code, message = policy.surface_problem(surface)
                self.assertEqual(policy.CODE_SURFACE_NON_ADAPTIVE, code)
                self.assertIn("never what correctness means", message)

    def test_the_registered_surfaces_are_adaptable(self) -> None:
        for surface in policy.SURFACES:
            self.assertIsNone(policy.surface_problem(surface.policy_surface_id))


class StrengthTests(unittest.TestCase):
    def test_higher_is_stronger_and_widening_is_capped_at_foundation(self) -> None:
        self.assertEqual(("LOCAL",), policy.widened_impact_levels("LOCAL", 0))
        self.assertEqual(("LOCAL", "SHARED"), policy.widened_impact_levels("LOCAL", 1))
        self.assertEqual(("LOCAL", "SHARED", "CONTRACT", "FOUNDATION"), policy.widened_impact_levels("LOCAL", 3))
        self.assertEqual(("CONTRACT", "FOUNDATION"), policy.widened_impact_levels("CONTRACT", 3))
        self.assertEqual(("FOUNDATION",), policy.widened_impact_levels("FOUNDATION", 2))

    def test_the_p4_minimum_is_never_verified_less(self) -> None:
        for impact in policy.IMPACT_ORDER:
            for steps in range(0, 4):
                with self.subTest(impact=impact, steps=steps):
                    levels = policy.widened_impact_levels(impact, steps)
                    self.assertEqual(impact, levels[0])
                    required = set().union(*(p4.REVERIFICATION_MINIMUMS[level] for level in levels))
                    self.assertTrue(set(p4.reverification_plan(impact)) <= required)

    def test_a_negative_or_unknown_widening_is_refused(self) -> None:
        for impact, steps in (("LOCAL", -1), ("LOCAL", True), ("NONE", 0)):
            with self.subTest(impact=impact, steps=steps), self.assertRaises(Exception):
                policy.widened_impact_levels(impact, steps)


class ProfileSurfaceTests(unittest.TestCase):
    def test_a_profile_cannot_reclassify_a_surface(self) -> None:
        found = policy.profile_problems(profile_record(override(strength_class=policy.CLASS_ADAPTIVE)), "p")
        self.assertIn(policy.CODE_RECLASSIFIED, [code for code, _ in found])
        found = policy.profile_problems(profile_record(override(strength_class=policy.CLASS_MANDATORY)), "p")
        self.assertIn(policy.CODE_RECLASSIFIED, [code for code, _ in found])

    def test_a_profile_cannot_invent_a_surface(self) -> None:
        found = policy.profile_problems(profile_record(override("review.discovery.extra_reviewers")), "p")
        self.assertEqual(policy.CODE_SURFACE_UNKNOWN, found[0][0])
        found = policy.profile_problems(profile_record(override("review.severity.blocking")), "p")
        self.assertEqual(policy.CODE_SURFACE_NON_ADAPTIVE, found[0][0])

    def test_a_profile_setting_stays_inside_the_allowed_range(self) -> None:
        for setting in (0, 5):
            with self.subTest(setting=setting):
                found = policy.profile_problems(profile_record(override(setting=setting)), "p")
                self.assertIn(policy.CODE_SETTING_INVALID, [code for code, _ in found])
        found = policy.profile_problems(profile_record(override(policy.SURFACE_EXTRA_SCOPE_STEPS, 4)), "p")
        self.assertIn(policy.CODE_SETTING_INVALID, [code for code, _ in found])

    def test_the_baseline_carries_exactly_the_fixed_registry(self) -> None:
        baseline = policy.load_global_baseline(WORKLINE_ROOT)
        self.assertEqual([surface.to_record() for surface in policy.SURFACES], baseline.record["surfaces"])
        tampered = dict(baseline.record)
        tampered["surfaces"] = baseline.record["surfaces"][:1]
        with self.assertRaises(Exception):
            policy.parse_baseline(tampered, "a tampered baseline")


class CatalogueTests(unittest.TestCase):
    def test_p6_names_are_its_own(self) -> None:
        names = set(policy.STOP_CODES) | set(policy.RECONCILE_REASONS)
        self.assertEqual(len(names), len(policy.STOP_CODES) + len(policy.RECONCILE_REASONS))
        self.assertTrue(all(name.startswith("review_p6_") for name in names))
        self.assertEqual(set(), names & (set(p4.STOP_CODES) | set(p4.RECONCILE_REASONS)))

    def test_every_review_p6_literal_in_the_implementation_is_declared(self) -> None:
        import re

        declared = set(policy.STOP_CODES) | set(policy.RECONCILE_REASONS)
        found: set[str] = set()
        for path in Path(policy.__file__).resolve().parents[1].rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                        and re.fullmatch(r"review_p6_[a-z_]+", node.value):
                    found.add(node.value)
        self.assertEqual(set(), found - declared)

    def test_the_policy_contract_is_p4_family_and_never_repairs(self) -> None:
        self.assertIn(policy.POLICY_CHANGE_CONTRACT, records.P4_CONTRACTS)
        self.assertNotIn(policy.POLICY_CHANGE_CONTRACT, records.P4_REPAIR_CONTRACTS)
        self.assertEqual((records.P4_PLANNING_CONTRACT, records.P4_WORK_CONTRACT), records.P4_REPAIR_CONTRACTS)


class InertCoreTests(unittest.TestCase):
    def test_the_policy_core_imports_nothing_that_locks_mutates_writes_or_finalizes(self) -> None:
        tree = ast.parse(Path(policy.__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.add(("." * node.level) + (node.module or ""))
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        for forbidden in ("mutation", "oplock", "gitops", "gitcmd", "durable", "state", "fsafe", "hermetic",
                          "project_policy"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, {name.rsplit(".", 1)[-1] for name in imported})
        calls = {node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                 for node in ast.walk(tree) if isinstance(node, ast.Call)}
        for forbidden in ("open", "write_text", "write_bytes", "mkdir", "unlink", "rename"):
            with self.subTest(call=forbidden):
                self.assertNotIn(forbidden, calls)


if __name__ == "__main__":
    unittest.main()
