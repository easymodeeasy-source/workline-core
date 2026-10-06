"""P7 materialization of the Global policy (``WORKLINE_COMPLETION_SPRINT`` §16.2 / §31.2 / §31.3 / §31.22 / §31.49).

The Global policy record ``review-policy/global-policy.yaml`` is defined ONCE in
the P6 loader module (:mod:`workline.review.policy`): its strict form, its exact
bytes, its successor rule and the baseline it loads as. The initial
materialization is the derived baseline restated - version 1, no parent, the two
code defaults - and its policy-semantic projection is the derived baseline's
exactly (R6-2), so materializing it changes no Effective Policy.

RB7-F foundation rows. The loader's materialized mode (the file read and the
``source_mode`` switch, RB7C-8) and the tracked v1 file land with RB7 step 4 and
add their rows here.
"""

from __future__ import annotations

import unittest

from helpers import WORKLINE_ROOT
from workline.errors import ValidationError
from workline.review import policy, serialize

#: The exact bytes of Global policy version 1: the derived baseline's two Global settings, nothing else.
V1_TEXT = (
    "fixed_meta_rules_identity: review-v1-p6-meta-rules-v1\n"
    "global_policy_version: 1\n"
    "loader_semantics_identity: review-v1-p6-policy-loader-v1\n"
    "parent_global_policy_digest: null\n"
    "schema: review-p7-global-policy\n"
    "settings:\n"
    "  - global_setting: 1\n"
    "    policy_surface_id: review.discovery.required_slots\n"
    "  - global_setting: 0\n"
    "    policy_surface_id: review.reverification.extra_scope_steps\n"
    "version: 1\n"
)
V1_DIGEST = "fa83abb1bf1710e8dbfaa2b76131b93f0010969da70595c2cd3ca07ef184170b"
SLOTS = policy.SURFACE_REQUIRED_SLOTS
STEPS = policy.SURFACE_EXTRA_SCOPE_STEPS


def derived() -> policy.GlobalPolicyBaseline:
    """The P6 derived baseline of this root, from the derived builder itself (whatever mode the loader reads)."""
    record = policy.baseline_record(policy.baseline_authority_digests(WORKLINE_ROOT), policy.source_policy_identities())
    return policy.parse_baseline(record, "the derived Global policy baseline")


def v1() -> dict:
    return policy.global_policy_from_baseline(derived())


def with_settings(record: dict, settings: list) -> dict:
    return {**record, "settings": settings}


class InitialMaterializationTests(unittest.TestCase):
    def test_version_1_restates_the_derived_baseline_in_exact_bytes(self) -> None:
        record = v1()
        self.assertEqual(V1_TEXT.encode("utf-8"), policy.global_policy_bytes(record))
        self.assertEqual(V1_DIGEST, policy.global_policy_digest(record))
        self.assertEqual({SLOTS: 1, STEPS: 0}, policy.global_policy_settings(record))
        self.assertEqual((1, None), (record["global_policy_version"], record["parent_global_policy_digest"]))
        self.assertEqual(set(policy.GLOBAL_POLICY_FIELDS), set(record))
        self.assertEqual("review-policy/global-policy.yaml", policy.GLOBAL_POLICY_REL)

    def test_the_semantic_projection_is_the_derived_baselines(self) -> None:
        baseline = derived()
        self.assertEqual(policy.SOURCE_MODE_DERIVED, baseline.source_mode)
        self.assertEqual(baseline.semantic_projection, policy.global_policy_projection(v1()))
        self.assertEqual(baseline.semantic_digest, serialize.digest(policy.global_policy_projection(v1())))

    def test_the_baseline_it_loads_as_differs_from_the_derived_one_in_provenance_only(self) -> None:
        baseline = derived()
        loaded = policy.materialized_baseline_record(v1(), baseline.record["root_authority_digests"],
                                                     baseline.record["source_policy_identities"])
        self.assertEqual([], policy.baseline_record_problems(loaded, "the materialized baseline"))
        self.assertEqual(set(policy.BASELINE_FIELDS), set(loaded))
        self.assertEqual({"source_mode", "global_policy_identity"},
                         {key for key in loaded if loaded[key] != baseline.record[key]})
        self.assertEqual(policy.SOURCE_MODE_MATERIALIZED, loaded["source_mode"])
        self.assertEqual(V1_DIGEST, loaded["global_policy_identity"])
        self.assertEqual(policy.semantic_projection(baseline.record), policy.semantic_projection(loaded))

    def test_only_version_1_is_materialized_from_a_baseline(self) -> None:
        later = policy.GlobalPolicyBaseline({**derived().record, "baseline_version": 2})
        with self.assertRaises(ValidationError):
            policy.global_policy_from_baseline(later)


class StrictFormTests(unittest.TestCase):
    def refused(self, record: object) -> None:
        with self.assertRaises(ValidationError):
            policy.parse_global_policy(record, "a Global policy")

    def test_the_v1_record_reads_back_as_itself(self) -> None:
        record = v1()
        self.assertEqual(record, policy.parse_global_policy(record, "the Global policy"))
        self.assertEqual(record, policy.parse_global_policy_bytes(V1_TEXT.encode("utf-8"), "the Global policy file"))

    def test_fields_schema_and_identities_are_exact(self) -> None:
        record = v1()
        cases = {
            "an unknown field": {**record, "comment": "x"},
            "a missing field": {key: value for key, value in record.items() if key != "settings"},
            "another schema": {**record, "schema": "review-p6-global-baseline"},
            "another record version": {**record, "version": 2},
            "another loader semantics identity": {**record, "loader_semantics_identity": "review-v1-p6-policy-loader-v2"},
            "other meta-rules": {**record, "fixed_meta_rules_identity": "review-v1-p6-meta-rules-v2"},
            "not a mapping": [record],
        }
        for name, case in cases.items():
            with self.subTest(name):
                self.refused(case)

    def test_the_version_and_parent_agree(self) -> None:
        record = v1()
        parent = policy.global_policy_digest(record)
        for name, version, named in (
            ("version 0", 0, None), ("a text version", "1", None), ("a boolean version", True, None),
            ("version 1 with a parent", 1, parent), ("version 2 without a parent", 2, None),
            ("version 2 with a short parent", 2, parent[:40]), ("version 2 with an upper-case parent", 2, parent.upper()),
        ):
            with self.subTest(name):
                self.refused({**record, "global_policy_version": version, "parent_global_policy_digest": named})
        self.assertEqual(2, policy.parse_global_policy({**record, "global_policy_version": 2,
                                                         "parent_global_policy_digest": parent}, "v2")
                         ["global_policy_version"])

    def test_each_fixed_surface_once_sorted_and_in_range(self) -> None:
        record = v1()
        slots, steps = record["settings"]
        cases = {
            "unsorted": [steps, slots],
            "a surface twice": [slots, slots],
            "a surface missing": [slots],
            "an extra surface": [slots, steps, {"policy_surface_id": "review.discovery.extra", "global_setting": 1}],
            "an unknown surface": [slots, {"policy_surface_id": "review.severity.blocking", "global_setting": 0}],
            "required_slots below its range": [{**slots, "global_setting": 0}, steps],
            "required_slots above its range": [{**slots, "global_setting": 5}, steps],
            "extra_scope_steps below its range": [slots, {**steps, "global_setting": -1}],
            "extra_scope_steps above its range": [slots, {**steps, "global_setting": 4}],
            "a boolean setting": [{**slots, "global_setting": True}, steps],
            "a text setting": [{**slots, "global_setting": "1"}, steps],
            "a setting with an extra field": [{**slots, "strength_class": "default"}, steps],
            "a setting that is not a mapping": [[SLOTS, 1], steps],
        }
        for name, settings in cases.items():
            with self.subTest(name):
                self.refused(with_settings(record, settings))
        self.refused({**record, "settings": {SLOTS: 1, STEPS: 0}})

    def test_every_in_range_pair_is_a_valid_policy(self) -> None:
        for slots in range(1, 5):
            for steps in range(0, 4):
                with self.subTest(slots=slots, steps=steps):
                    record = policy.global_policy_record(2, V1_DIGEST, {SLOTS: slots, STEPS: steps})
                    self.assertEqual({SLOTS: slots, STEPS: steps}, policy.global_policy_settings(record))

    def test_the_builder_refuses_a_setting_set_other_than_the_fixed_surfaces(self) -> None:
        for settings in ({SLOTS: 1}, {SLOTS: 1, STEPS: 0, "review.discovery.extra": 1}, [(SLOTS, 1), (STEPS, 0)]):
            with self.subTest(settings=settings), self.assertRaises(ValidationError):
                policy.global_policy_record(1, None, settings)

    def test_only_the_canonical_bytes_are_read(self) -> None:
        for name, raw in (
            ("CRLF line ends", V1_TEXT.replace("\n", "\r\n").encode("utf-8")),
            ("no final line end", V1_TEXT.rstrip("\n").encode("utf-8")),
            ("reordered keys", ("version: 1\n" + V1_TEXT[:-len("version: 1\n")]).encode("utf-8")),
            ("a comment", ("# note\n" + V1_TEXT).encode("utf-8")),
        ):
            with self.subTest(name), self.assertRaises(ValidationError):
                policy.parse_global_policy_bytes(raw, "the Global policy file")


class SuccessorTests(unittest.TestCase):
    def test_a_successor_is_exactly_the_next_version_naming_its_exact_parent(self) -> None:
        first = v1()
        second = policy.global_policy_record(2, policy.global_policy_digest(first), {SLOTS: 2, STEPS: 0})
        self.assertIsNone(policy.global_policy_successor_problem(first, second))
        # a rollback is a new, higher version like any other change (§31.22)
        third = policy.global_policy_record(3, policy.global_policy_digest(second), {SLOTS: 1, STEPS: 0})
        self.assertIsNone(policy.global_policy_successor_problem(second, third))
        self.assertEqual(policy.global_policy_settings(first), policy.global_policy_settings(third))
        self.assertNotEqual(policy.global_policy_digest(first), policy.global_policy_digest(third))

    def test_a_skipped_repeated_or_reparented_version_is_not_a_successor(self) -> None:
        first = v1()
        second = policy.global_policy_record(2, policy.global_policy_digest(first), {SLOTS: 2, STEPS: 0})
        for name, before, after in (
            ("a skipped version", first, policy.global_policy_record(3, policy.global_policy_digest(first),
                                                                     {SLOTS: 2, STEPS: 0})),
            ("the same version", first, first),
            ("backwards", second, first),
            ("another parent", second, policy.global_policy_record(3, "0" * 64, {SLOTS: 1, STEPS: 0})),
            ("a malformed after", first, {**second, "settings": []}),
        ):
            with self.subTest(name):
                self.assertIsNotNone(policy.global_policy_successor_problem(before, after))

    def test_a_changed_setting_changes_the_projection(self) -> None:
        first = v1()
        second = policy.global_policy_record(2, policy.global_policy_digest(first), {SLOTS: 2, STEPS: 0})
        projection = policy.global_policy_projection(second)
        self.assertNotEqual(policy.global_policy_projection(first), projection)
        self.assertEqual(2, projection["baseline_version"])
        self.assertEqual([2, 0], [item["global_setting"] for item in projection["surfaces"]])


if __name__ == "__main__":
    unittest.main()
