"""P7 materialization of the Global policy (``WORKLINE_COMPLETION_SPRINT`` §16.2 / §31.2 / §31.3 / §31.22 / §31.49).

The Global policy record ``review-policy/global-policy.yaml`` is defined ONCE in
the P6 loader module (:mod:`workline.review.policy`): its strict form, its exact
bytes, its successor rule and the baseline it loads as. The initial
materialization is the derived baseline restated - version 1, no parent, the two
code defaults - and its policy-semantic projection is the derived baseline's
exactly (R6-2), so materializing it changes no Effective Policy.

Rows: the record and its bytes (foundation); the tracked version 1 file and the
reader side of the loader transition (RB7C-8: both source modes, the runtime
Global policy version rule, the fixed registry facts in both modes, Effective
Policies frozen under a later version); and the loader's switch to the tracked
file (§31.3: source_mode and provenance only, the file required, no-follow).
"""

from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest import mock

from helpers import WORKLINE_ROOT, WorklineTestCase, copy_workline_root, rmtree
from workline.errors import StopError, ValidationError
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
    return policy.derived_global_baseline(WORKLINE_ROOT)


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

    def test_the_p7_loader_identities_are_declared_once_and_distinct(self) -> None:
        self.assertEqual("materialized-global-policy", policy.SOURCE_MODE_MATERIALIZED)
        self.assertNotEqual(policy.SOURCE_MODE_DERIVED, policy.SOURCE_MODE_MATERIALIZED)
        self.assertEqual("review-v1-p7-total-adapter-v1", policy.COMPATIBILITY_TOTAL_ADAPTER_V1)
        self.assertNotEqual(policy.COMPATIBILITY_EXACT_DERIVED_SEMANTIC, policy.COMPATIBILITY_TOTAL_ADAPTER_V1)
        self.assertEqual(("global", "review_global_policy_change"), (policy.ORIGIN_GLOBAL, policy.GLOBAL_EXPERIMENT_KIND))
        self.assertNotEqual(policy.ORIGIN_PROJECT, policy.ORIGIN_GLOBAL)
        self.assertNotEqual(policy.SCHEMA_BASELINE, policy.SCHEMA_GLOBAL_POLICY)

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

    def test_version_1_is_exactly_the_derived_defaults(self) -> None:
        """§31.2: version 1 is the zero-semantic-change materialization; any other setting is a later version."""
        record = v1()
        slots, steps = record["settings"]
        for settings in ([{**slots, "global_setting": 2}, steps], [slots, {**steps, "global_setting": 1}]):
            with self.subTest(settings=settings):
                self.refused(with_settings(record, settings))
        with self.assertRaises(ValidationError):
            policy.global_policy_record(1, None, {SLOTS: 2, STEPS: 0})

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


class LoaderReadsBothModesTests(unittest.TestCase):
    """RB7C-8: ``parse_baseline`` and the Effective Policy reader admit materialized Global versions as runtime data."""

    def loaded(self, global_policy: dict) -> dict:
        baseline = derived()
        return policy.materialized_baseline_record(global_policy, baseline.record["root_authority_digests"],
                                                   baseline.record["source_policy_identities"])

    def v2(self, slots: int = 2, steps: int = 0) -> dict:
        return policy.global_policy_record(2, V1_DIGEST, {SLOTS: slots, STEPS: steps})

    def test_the_modes_and_the_runtime_version_rule(self) -> None:
        self.assertEqual((policy.SOURCE_MODE_DERIVED, policy.SOURCE_MODE_MATERIALIZED), policy.SOURCE_MODES)
        self.assertEqual((1,), policy.BASELINE_VERSIONS)
        # a list, not a dict: True == 1 would collapse the boolean rows onto the integer ones
        cases = [
            (1, policy.SOURCE_MODE_DERIVED, True), (2, policy.SOURCE_MODE_DERIVED, False),
            (1, policy.SOURCE_MODE_MATERIALIZED, True), (2, policy.SOURCE_MODE_MATERIALIZED, True),
            (97, policy.SOURCE_MODE_MATERIALIZED, True), (0, policy.SOURCE_MODE_MATERIALIZED, False),
            (True, policy.SOURCE_MODE_DERIVED, False), (True, policy.SOURCE_MODE_MATERIALIZED, False),
            ("2", policy.SOURCE_MODE_MATERIALIZED, False), (1, "another-mode", False),
        ]
        for version, mode, admitted in cases:
            with self.subTest(version=version, mode=mode):
                self.assertIs(admitted, policy.baseline_version_admitted(version, mode))

    def test_a_materialized_baseline_of_any_version_parses(self) -> None:
        for record in (v1(), self.v2(), self.v2(4, 3), policy.global_policy_record(9, V1_DIGEST, {SLOTS: 1, STEPS: 0})):
            with self.subTest(version=record["global_policy_version"], settings=record["settings"]):
                parsed = policy.parse_baseline(self.loaded(record), "a materialized baseline")
                self.assertEqual(policy.SOURCE_MODE_MATERIALIZED, parsed.source_mode)
                self.assertEqual(record["global_policy_version"], parsed.version)
                self.assertEqual(policy.global_policy_settings(record),
                                 {surface.policy_surface_id: parsed.global_setting(surface.policy_surface_id)
                                  for surface in policy.SURFACES})

    def test_an_effective_policy_frozen_under_a_later_version_reads_back(self) -> None:
        baseline = policy.parse_baseline(self.loaded(self.v2()), "a materialized baseline")
        record = policy.effective_policy_record(baseline, None, ())
        self.assertEqual({"contract": policy.BASELINE_CONTRACT, "baseline_version": 2, "digest": baseline.digest,
                          "source_mode": policy.SOURCE_MODE_MATERIALIZED}, record["global_baseline"])
        self.assertEqual(record, policy.parse_effective_policy(record, "the frozen Effective Policy"))
        self.assertEqual({SLOTS: 2, STEPS: 0}, record["settings"])
        # every stored derived (version 1) envelope keeps reading exactly as before (FC-RB7-2)
        stored = policy.effective_policy_record(derived(), None, ())
        self.assertEqual(stored, policy.parse_effective_policy(stored, "a stored derived Effective Policy"))
        for name, baseline_identity in (
            ("a derived baseline at version 2", {**stored["global_baseline"], "baseline_version": 2}),
            ("a materialized baseline at version 0", {**record["global_baseline"], "baseline_version": 0}),
            ("an unknown source mode", {**record["global_baseline"], "source_mode": "guessed"}),
        ):
            with self.subTest(name), self.assertRaises(ValidationError):
                policy.parse_effective_policy({**record, "global_baseline": baseline_identity}, "a frozen policy")

    def test_the_registry_facts_stay_fixed_in_both_modes(self) -> None:
        derived_record = derived().record
        materialized = self.loaded(self.v2())
        surfaces = materialized["surfaces"]
        cases = {
            "a derived baseline with a non-default setting": {
                **derived_record, "surfaces": [{**derived_record["surfaces"][0], "global_setting": 2},
                                               derived_record["surfaces"][1]]},
            "a truncated derived surface list": {**derived_record, "surfaces": derived_record["surfaces"][:1]},
            "a truncated materialized surface list": {**materialized, "surfaces": surfaces[:1]},
            "an extended materialized surface list": {**materialized, "surfaces": surfaces + surfaces[:1]},
            "reordered surfaces": {**materialized, "surfaces": list(reversed(surfaces))},
            "a reclassified surface": {**materialized, "surfaces": [{**surfaces[0], "strength_class": "adaptive"},
                                                                    surfaces[1]]},
            "a widened range": {**materialized, "surfaces": [{**surfaces[0], "allowed_range": {"minimum": 0,
                                                                                               "maximum": 9}},
                                                             surfaces[1]]},
            "an out-of-range Global setting": {**materialized, "surfaces": [{**surfaces[0], "global_setting": 5},
                                                                           surfaces[1]]},
            "a boolean Global setting": {**materialized, "surfaces": [surfaces[0], {**surfaces[1],
                                                                                     "global_setting": False}]},
            "a materialized identity that is no digest": {**materialized, "global_policy_identity": "v2"},
            "a materialized version 0": {**materialized, "baseline_version": 0},
            "a derived version 2": {**derived_record, "baseline_version": 2},
            "an unknown source mode": {**materialized, "source_mode": "guessed"},
            "other meta-rules": {**materialized, "meta_rules_digest": "0" * 64},
        }
        for name, record in cases.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                policy.parse_baseline(record, "a baseline")

    def test_the_tracked_version_1_file_is_the_materialization(self) -> None:
        """The candidate's ``review-policy/global-policy.yaml`` (a checkout may turn its LF line ends into CRLF)."""
        raw = WORKLINE_ROOT.joinpath(*policy.GLOBAL_POLICY_REL.split("/")).read_bytes()
        self.assertEqual(V1_TEXT.encode("utf-8"), raw.replace(b"\r\n", b"\n"))
        self.assertEqual(v1(), policy.parse_global_policy_bytes(raw.replace(b"\r\n", b"\n"), "the tracked file"))
        tracked = sorted(path.relative_to(WORKLINE_ROOT).as_posix()
                         for path in WORKLINE_ROOT.joinpath("review-policy").rglob("*"))
        self.assertEqual(["review-policy/global-policy.yaml"], tracked,
                         "no Promotion Packet, change, evaluation or Patch Note is fabricated for it (§31.2)")


def bare_root(dest: Path) -> Path:
    """A copied Workline root WITHOUT its tracked Global policy (copy_workline_root carries it, RB7C-7)."""
    root = copy_workline_root(dest)
    rmtree(root / "review-policy")
    return root


class LoaderSwitchTests(WorklineTestCase):
    """§31.3 / §16.26: the same loader reads the tracked Global policy; the transition is source_mode only."""

    def root_with(self, data: bytes | None) -> Path:
        root = bare_root(self.tmp / "root")
        if data is not None:
            (root / "review-policy").mkdir()
            (root / "review-policy" / "global-policy.yaml").write_bytes(data)
        return root

    def test_the_real_root_loads_its_tracked_version_1(self) -> None:
        loaded = policy.load_global_baseline(WORKLINE_ROOT)
        baseline = derived()
        self.assertEqual((policy.SOURCE_MODE_MATERIALIZED, 1, V1_DIGEST),
                         (loaded.source_mode, loaded.version, loaded.global_policy_identity))
        self.assertEqual(baseline.semantic_projection, loaded.semantic_projection)
        self.assertEqual({"source_mode", "global_policy_identity"},
                         {key for key in loaded.record if loaded.record[key] != baseline.record[key]})
        self.assertEqual(loaded.record, policy.load_global_baseline(WORKLINE_ROOT).record)

    def test_no_effective_policy_semantics_change_at_the_transition(self) -> None:
        """§16.26: a new Run freezes the same settings; a Run frozen before keeps reading; no Profile is touched."""
        before = policy.effective_policy_record(derived(), None, ())
        after = policy.effective_policy_record(policy.load_global_baseline(WORKLINE_ROOT), None, ())
        self.assertEqual(before["settings"], after["settings"])
        self.assertEqual(before["compatibility"], after["compatibility"])
        self.assertEqual(policy.COMPATIBILITY_EXACT_DERIVED_SEMANTIC, after["compatibility"])
        self.assertEqual(before, policy.parse_effective_policy(before, "an Effective Policy frozen before"))

    def test_a_crlf_checkout_reads_as_the_same_policy(self) -> None:
        root = self.root_with(V1_TEXT.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(V1_DIGEST, policy.load_global_baseline(root).global_policy_identity)

    def test_a_later_version_loads_as_runtime_data(self) -> None:
        later = policy.global_policy_record(2, V1_DIGEST, {SLOTS: 3, STEPS: 1})
        loaded = policy.load_global_baseline(self.root_with(policy.global_policy_bytes(later)))
        self.assertEqual((2, 3, 1), (loaded.version, loaded.global_setting(SLOTS), loaded.global_setting(STEPS)))
        self.assertEqual(policy.global_policy_projection(later), loaded.semantic_projection)

    def test_the_file_is_required_and_never_replaced_by_the_derived_baseline(self) -> None:
        root = self.root_with(None)
        with self.assertRaises(StopError) as raised:
            policy.load_global_baseline(root)
        self.assertEqual(policy.CODE_BASELINE_UNAVAILABLE, raised.exception.code)
        self.assertFalse((root / "review-policy").exists(), "the loader writes nothing")

    def test_a_malformed_file_is_an_invalid_record(self) -> None:
        for name, data in (
            ("not canonical", ("# note\n" + V1_TEXT).encode("utf-8")),
            ("version 1 with another setting", V1_TEXT.replace("global_setting: 1", "global_setting: 2").encode("utf-8")),
            ("not yaml", b"\x00\xff"),
        ):
            with self.subTest(name):
                root = bare_root(self.tmp / name.replace(" ", "-"))
                (root / "review-policy").mkdir()
                (root / "review-policy" / "global-policy.yaml").write_bytes(data)
                with self.assertRaises(ValidationError) as raised:
                    policy.load_global_baseline(root)
                self.assertEqual("review_record_invalid", raised.exception.code)

    def test_an_indirected_file_or_directory_is_never_followed(self) -> None:
        outside = self.new_dir("outside")
        (outside / "global-policy.yaml").write_text(V1_TEXT, encoding="utf-8", newline="")
        for name in ("file symlink", "directory symlink", "directory junction"):
            with self.subTest(name):
                root = bare_root(self.tmp / f"root-{name.replace(' ', '-')}")
                try:
                    if name == "file symlink":
                        (root / "review-policy").mkdir()
                        os.symlink(outside / "global-policy.yaml", root / "review-policy" / "global-policy.yaml")
                    elif name == "directory symlink":
                        os.symlink(outside, root / "review-policy", target_is_directory=True)
                    else:
                        if os.name != "nt":
                            self.skipTest("a junction is a Windows reparse point")
                        import _winapi

                        _winapi.CreateJunction(str(outside), str(root / "review-policy"))
                except OSError as exc:
                    self.skipTest(f"this platform cannot create a {name} here ({exc})")
                with self.assertRaises(StopError) as raised:
                    policy.load_global_baseline(root)
                self.assertEqual(policy.CODE_BASELINE_UNAVAILABLE, raised.exception.code)

    def test_the_loader_never_writes_the_root(self) -> None:
        root = self.root_with(V1_TEXT.encode("utf-8"))

        def snapshot() -> dict[str, tuple[bytes, int]]:
            return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
                    for path in sorted(root.rglob("*")) if path.is_file()}

        before = snapshot()
        policy.load_global_baseline(root)
        self.assertEqual(before, snapshot())
        self.assertFalse((root / ".workline").exists())
        self.assertFalse((root / ".workline-root-runtime").exists())


MEASUREMENT = {"version": "m1", "metric": "supported escapes per relevant Run", "success_criteria": "no added escape",
               "minimum_opportunities": 3, "minimum_clusters": 2, "continued_observation_permitted": False}
STRENGTHEN_ID = "rgc_" + "1" * 26
LIGHTEN_ID = "rgc_" + "2" * 26
OVERRIDE_CHANGE = "rpc_" + "3" * 26


def global_change(change_id: str, before: dict, after: dict, direction: str, surface: str = SLOTS) -> dict:
    """A stored Global change record of ``before`` -> ``after`` on ``surface`` (RB7-C's strict schema)."""
    from workline.review import global_policy as gp

    before_setting = policy.global_policy_settings(before)[surface]
    record = {
        serialize.SCHEMA_KEY: gp.SCHEMA_CHANGE, serialize.VERSION_KEY: 1, "global_policy_change_id": change_id,
        "promotion_packet_id": "rpp_" + change_id[4:], "promotion_packet_digest": "a" * 64, "candidate_hash": "b" * 64,
        "review_run_id": "rr_" + "7" * 26, "receipt_id": "rcp_" + "7" * 26,
        "before_global_policy_version": before["global_policy_version"],
        "before_global_policy_digest": policy.global_policy_digest(before),
        "after_global_policy_version": after["global_policy_version"],
        "after_global_policy_digest": policy.global_policy_digest(after),
        "policy_surface_id": surface, "before_setting": before_setting,
        "after_setting": policy.global_policy_settings(after)[surface], "direction": direction,
        "generalized_mechanism_id": "contract-drift", "compatibility_adapter_identity": policy.COMPATIBILITY_TOTAL_ADAPTER_V1,
        "compatibility_proof_digest": "c" * 64, "expected_effect": "fewer escapes per relevant Run",
        "measurement_contract": dict(MEASUREMENT),
        "rollback_contract": {"threshold": "one added supported escape",
                              "unit": {"policy_surface_id": surface, "restore_setting": before_setting,
                                       "restore_global_policy_digest": policy.global_policy_digest(before)}},
        "summary": "a generalized contract-drift check",
    }
    return gp.parse_change_record(record, "a Global change record")


class NoProfileReader:
    """A Project with no Profile and no policy record: the Global baseline alone governs it."""

    def read_profile(self) -> None:
        return None

    def policy_change_ids(self) -> tuple[str, ...]:
        return ()

    def policy_evaluation_ids(self) -> tuple[str, ...]:
        return ()


class OverrideReader:
    """The change-record readers the compatibility decision uses, over one Project change (R6-2 item 3)."""

    def __init__(self, change: dict) -> None:
        self.change = change

    def policy_change_ids(self) -> tuple[str, ...]:
        return (self.change["policy_change_id"],)

    def read_policy_change(self, change_id: str) -> dict:
        return self.change

    def policy_change_exists(self, change_id: str) -> bool:
        return change_id == self.change["policy_change_id"]


class GlobalChangeAdoptionTests(WorklineTestCase):
    """§31.45 / §16.12: a Project adopts a later Global version at its next Run boundary through the same loader.

    Lineage here: v1 (slots 1) -> v2 strengthens slots to 2 -> v3 lightens slots back to 1.
    """

    def setUp(self) -> None:
        super().setUp()
        self.v2 = policy.global_policy_record(2, V1_DIGEST, {SLOTS: 2, STEPS: 0})
        self.v3 = policy.global_policy_record(3, policy.global_policy_digest(self.v2), {SLOTS: 1, STEPS: 0})
        self.changes = [global_change(STRENGTHEN_ID, v1(), self.v2, "strengthen"),
                        global_change(LIGHTEN_ID, self.v2, self.v3, "lighten")]
        self.root = self.root_at(self.v3, self.changes)

    def root_at(self, current: dict, changes: list, name: str = "root") -> Path:
        root = copy_workline_root(self.tmp / name)
        (root / "review-policy" / "changes").mkdir(parents=True)
        (root / "review-policy" / "global-policy.yaml").write_bytes(policy.global_policy_bytes(current))
        for change in changes:
            (root / "review-policy" / "changes" / f"{change['global_policy_change_id']}.yaml").write_bytes(
                serialize.canonical_bytes(change))
        return root

    def overriding(self, surface: str, setting: int) -> tuple[policy.ProjectProfile, OverrideReader]:
        """A Profile v1 written under Global v1 with one override, and its supporting Project change record."""
        bound = self.loaded_v1()
        found = policy.SURFACE_BY_ID[surface]
        profile = policy.ProjectProfile(
            profile_version=1, parent_profile_digest=None, global_baseline_digest=serialize.digest(bound),
            global_baseline_version=1, loader_semantics_identity=policy.LOADER_SEMANTICS_IDENTITY,
            overrides=({"policy_surface_id": surface, "strength_class": found.strength_class, "setting": setting,
                        "direction": "strengthen" if setting > found.global_setting else "lighten",
                        "supporting_policy_change_id": OVERRIDE_CHANGE},),
            active_experiment_refs=(),
        )
        change = {"policy_change_id": OVERRIDE_CHANGE, "after_profile_digest": profile.digest, "global_baseline": bound,
                  "global_baseline_digest": serialize.digest(bound), "affected_policy_surface": surface,
                  "after_setting": setting}
        return profile, OverrideReader(change)

    def loaded_v1(self) -> dict:
        return policy.load_global_baseline(WORKLINE_ROOT).record

    def test_the_closed_tables_admit_the_p7_identities(self) -> None:
        self.assertEqual((policy.COMPATIBILITY_EXACT_DERIVED_SEMANTIC, policy.COMPATIBILITY_TOTAL_ADAPTER_V1),
                         policy.COMPATIBILITY_INTERPRETATIONS)
        self.assertEqual({policy.ORIGIN_PROJECT: "review_policy_change",
                          policy.ORIGIN_GLOBAL: policy.GLOBAL_EXPERIMENT_KIND}, dict(policy.EXPERIMENT_ORIGINS))
        baseline = policy.load_global_baseline(self.root)
        with self.assertRaises(ValidationError):  # an absent Profile is the baseline itself: never "adapted"
            policy.effective_policy_record(baseline, None, (), compatibility=policy.COMPATIBILITY_TOTAL_ADAPTER_V1)
        with self.assertRaises(ValidationError):
            policy.effective_policy_record(baseline, None, (), compatibility="review-v1-p7-guessed")

    def test_a_project_following_the_global_setting_freezes_the_lightening_holdout(self) -> None:
        state = policy.resolve_policy_state(NoProfileReader(), self.root)
        self.assertEqual((policy.SOURCE_MODE_MATERIALIZED, 3), (state.baseline.source_mode, state.baseline.version))
        self.assertEqual([(LIGHTEN_ID, SLOTS, "lighten", 2, policy.ORIGIN_GLOBAL)],
                         [(item.policy_change_id, item.policy_surface_id, item.direction, item.holdout_setting,
                           item.origin) for item in state.active],
                         "the later change on the surface supersedes the earlier; the lightening keeps the stronger "
                         "before setting as its holdout")
        self.assertEqual({SLOTS: 1, STEPS: 0}, state.effective["settings"])
        self.assertEqual(policy.COMPATIBILITY_EXACT_DERIVED_SEMANTIC, state.effective["compatibility"])
        self.assertEqual(state.effective, policy.parse_effective_policy(state.effective, "the frozen Effective Policy"))

    def test_an_overridden_surface_is_no_observation_of_the_global_change(self) -> None:
        """FLAG-C3: an override keeps its absolute setting (§31.21), so the Global lightening changes nothing there."""
        baseline = policy.load_global_baseline(self.root)
        profile, _ = self.overriding(SLOTS, 3)
        self.assertEqual((), policy.global_experiments(self.root, baseline, profile))
        lightening = policy.global_experiments(self.root, baseline, None)
        frozen = policy.effective_policy_record(baseline, profile, (),
                                                compatibility=policy.COMPATIBILITY_TOTAL_ADAPTER_V1)
        self.assertEqual({SLOTS: 3, STEPS: 0}, frozen["settings"])
        self.assertEqual(frozen, policy.parse_effective_policy(frozen, "the frozen Effective Policy"))
        # the reader's rule is NOT loosened: that holdout on that override would still be refused
        with self.assertRaises(ValidationError):
            policy.parse_effective_policy(policy.effective_policy_record(
                baseline, profile, lightening, compatibility=policy.COMPATIBILITY_TOTAL_ADAPTER_V1), "a frozen policy")
        # an override on the OTHER surface leaves the Project following the Global slots setting: it observes it
        steps_profile, _ = self.overriding(STEPS, 2)
        self.assertEqual([LIGHTEN_ID], [item.policy_change_id for item in
                                        policy.global_experiments(self.root, baseline, steps_profile)])

    def test_a_profile_written_under_an_earlier_global_is_applied_through_adapter_v1(self) -> None:
        baseline = policy.load_global_baseline(self.root)
        profile, reader = self.overriding(SLOTS, 3)
        self.assertIsNone(policy.compatibility_problem(profile, policy.load_global_baseline(WORKLINE_ROOT), reader))
        self.assertEqual(policy.COMPATIBILITY_EXACT_DERIVED_SEMANTIC,
                         policy.compatibility_interpretation(profile, policy.load_global_baseline(WORKLINE_ROOT), reader))
        self.assertIsNone(policy.compatibility_problem(profile, baseline, reader))
        self.assertEqual(policy.COMPATIBILITY_TOTAL_ADAPTER_V1,
                         policy.compatibility_interpretation(profile, baseline, reader))
        self.assertEqual({SLOTS: 3, STEPS: 0}, policy.profile_overlay(profile, baseline))
        self.assertEqual(policy.COMPATIBILITY_EXACT_DERIVED_SEMANTIC,
                         policy.compatibility_interpretation(None, baseline, reader))

    def test_the_global_lineage_is_read_strictly_from_the_configured_root(self) -> None:
        baseline = policy.load_global_baseline(self.root)
        stray = self.root / "review-policy" / "changes" / "notes.txt"
        stray.write_text("x\n", encoding="utf-8")
        with self.assertRaises(StopError) as raised:
            policy.global_experiments(self.root, baseline, None)
        self.assertEqual(policy.CODE_BASELINE_UNAVAILABLE, raised.exception.code)
        stray.unlink()
        record = self.root / "review-policy" / "changes" / f"{LIGHTEN_ID}.yaml"
        record.write_bytes(b"# note\n" + serialize.canonical_bytes(self.changes[1]))
        with self.assertRaises(ValidationError) as invalid:
            policy.global_experiments(self.root, baseline, None)
        self.assertEqual("review_record_invalid", invalid.exception.code)
        record.write_bytes(serialize.canonical_bytes(self.changes[1]).replace(b"\n", b"\r\n"))
        self.assertEqual([LIGHTEN_ID], [item.policy_change_id
                                        for item in policy.global_experiments(self.root, baseline, None)],
                         "a CRLF checkout of a record reads as the record")
        unrecorded = self.root_at(self.v2, [], "unrecorded")
        with self.assertRaises(ValidationError):
            policy.global_experiments(unrecorded, policy.load_global_baseline(unrecorded), None)
        self.assertEqual((), policy.global_experiments(WORKLINE_ROOT, policy.load_global_baseline(WORKLINE_ROOT), None),
                         "version 1 is no learned change")


class ProfileReader(OverrideReader):
    """A Project whose one Profile override was decided under Global v1, as a new Run's resolution reads it."""

    def __init__(self, profile: policy.ProjectProfile, change: dict) -> None:
        super().__init__(change)
        self.profile = profile

    def read_profile(self) -> policy.ProjectProfile:
        return self.profile

    def policy_evaluation_ids(self) -> tuple[str, ...]:
        return ()


def discovery_actors(count: int, prefix: str = "required") -> tuple:
    from workline.review import p4

    return tuple(p4.DiscoveryBinding(f"{prefix}-{index}", lambda task: None, f"{prefix}-reviewer-{index}", "v1")
                 for index in range(count))


class GlobalLighteningOverrideTests(WorklineTestCase):
    """RB7CL-4 / FLAG-C3: a Global lightening 3 -> 2 of required_slots, and Project overrides of that surface.

    Lineage: v1 (slots 1) -> v2 strengthens slots to 3 -> v3 lightens slots to 2 (holdout 3, the before setting).
    An override AT (3) or ABOVE (4) the pre-change Global setting keeps its absolute value (§31.21), so the Global
    lightening is no downward change there and freezes no holdout: the Run starts and its Effective Policy reads.
    The Profile lineage proof (Receipt-backed change records) is P6's and is exercised by the P6 suites; it is held
    constant here so that only the Global experiment decides.
    """

    root_at = GlobalChangeAdoptionTests.root_at
    overriding = GlobalChangeAdoptionTests.overriding
    loaded_v1 = GlobalChangeAdoptionTests.loaded_v1

    def setUp(self) -> None:
        super().setUp()
        self.v2 = policy.global_policy_record(2, V1_DIGEST, {SLOTS: 3, STEPS: 0})
        self.v3 = policy.global_policy_record(3, policy.global_policy_digest(self.v2), {SLOTS: 2, STEPS: 0})
        self.changes = [global_change(STRENGTHEN_ID, v1(), self.v2, "strengthen"),
                        global_change(LIGHTEN_ID, self.v2, self.v3, "lighten")]
        self.root = self.root_at(self.v3, self.changes)
        lineage = mock.patch.object(policy, "require_lineage")
        lineage.start()
        self.addCleanup(lineage.stop)

    def new_run(self, reader, holdout: tuple = ()) -> dict:
        from workline.review import p4

        needed = policy.setting(policy.resolve_policy_state(reader, self.root).effective, SLOTS)
        return policy.new_run_effective_policy(reader, self.root, p4.P6_POLICY_ID, discovery_actors(needed), holdout)

    def test_an_override_at_or_above_the_pre_change_setting_starts_its_run(self) -> None:
        for setting in (3, 4):
            with self.subTest(override=setting):
                profile, reader = self.overriding(SLOTS, setting)
                effective = self.new_run(ProfileReader(profile, reader.change))
                self.assertEqual(effective, policy.parse_effective_policy(effective, "the frozen Effective Policy"))
                self.assertEqual({SLOTS: setting, STEPS: 0}, effective["settings"])
                self.assertEqual([], effective["active_experiments"], "the Global lightening does not govern it")
                self.assertEqual(0, policy.required_holdout_slots(effective))
                self.assertEqual(policy.COMPATIBILITY_TOTAL_ADAPTER_V1, effective["compatibility"])

    def test_a_project_following_the_global_setting_needs_the_lightening_holdout(self) -> None:
        with self.assertRaises(StopError) as raised:
            self.new_run(NoProfileReader())
        self.assertEqual(policy.CODE_HOLDOUT_UNBOUND, raised.exception.code)
        effective = self.new_run(NoProfileReader(), holdout=discovery_actors(1, "holdout"))
        self.assertEqual(effective, policy.parse_effective_policy(effective, "the frozen Effective Policy"))
        self.assertEqual({SLOTS: 2, STEPS: 0}, effective["settings"])
        self.assertEqual([{"origin": policy.ORIGIN_GLOBAL, "policy_change_id": LIGHTEN_ID, "policy_surface_id": SLOTS,
                           "direction": "lighten", "holdout_setting": 3}], effective["active_experiments"])
        self.assertEqual(1, policy.required_holdout_slots(effective))

    # CP ruling RB7 FLAG-C3 (CP_RULINGS_WAVE_20261007_B §8-§11): only Global-origin experiments on an overridden
    # surface are filtered; Project-local P6 experiment state, evidence and Profile state are never dropped.

    def decided_under(self, global_record: dict, surface: str, setting: int, direction: str, *,
                      local_holdout: int | None = None, change_id: str = OVERRIDE_CHANGE) -> ProfileReader:
        """A Profile v1 with ONE override decided under ``global_record``; with ``local_holdout``, that Project change
        is a still-active Project-local P6 lightening experiment holding that holdout. And the reader of both."""
        loaded = self.loaded_v1()
        bound = policy.materialized_baseline_record(global_record, loaded["root_authority_digests"],
                                                    loaded["source_policy_identities"])
        found = policy.SURFACE_BY_ID[surface]
        profile = policy.ProjectProfile(
            profile_version=1, parent_profile_digest=None, global_baseline_digest=serialize.digest(bound),
            global_baseline_version=bound["baseline_version"], loader_semantics_identity=policy.LOADER_SEMANTICS_IDENTITY,
            overrides=({"policy_surface_id": surface, "strength_class": found.strength_class, "setting": setting,
                        "direction": direction, "supporting_policy_change_id": change_id},),
            active_experiment_refs=() if local_holdout is None else (change_id,),
        )
        change = {"policy_change_id": change_id, "after_profile_digest": profile.digest, "global_baseline": bound,
                  "global_baseline_digest": serialize.digest(bound), "affected_policy_surface": surface,
                  "after_setting": setting, "direction": direction,
                  "holdout_plan": None if local_holdout is None else {"holdout_setting": local_holdout}}
        return ProfileReader(profile, change)

    def started(self, reader, root: Path | None = None) -> dict:
        """The Effective Policy a new P6-capable Run freezes, bound to exactly the actors it asks for; read back."""
        from workline.review import p4

        root = self.root if root is None else root
        state = policy.resolve_policy_state(reader, root)
        effective = policy.new_run_effective_policy(
            reader, root, p4.P6_POLICY_ID, discovery_actors(policy.setting(state.effective, SLOTS)),
            discovery_actors(policy.required_holdout_slots(state.effective), "holdout"))
        self.assertEqual(effective, policy.parse_effective_policy(effective, "the frozen Effective Policy"))
        self.assertGreaterEqual(policy.required_holdout_slots(effective), 0)
        return effective

    def test_row_1_a_stronger_override_freezes_no_global_experiment(self) -> None:
        effective = self.started(self.decided_under(v1(), SLOTS, 4, "strengthen"))
        self.assertEqual(({SLOTS: 4, STEPS: 0}, [], 0),
                         (effective["settings"], effective["active_experiments"], policy.required_holdout_slots(effective)))

    def test_row_2_an_override_equal_to_the_pre_change_setting_freezes_no_global_experiment(self) -> None:
        effective = self.started(self.decided_under(v1(), SLOTS, 3, "strengthen"))
        self.assertEqual(({SLOTS: 3, STEPS: 0}, [], 0),
                         (effective["settings"], effective["active_experiments"], policy.required_holdout_slots(effective)))

    def test_row_3_a_lighter_override_keeps_its_local_experiment_and_freezes_no_global_one(self) -> None:
        # decided under v2 (Global slots 3) as a Project-local lightening to 1 whose own holdout (3) is still active
        reader = self.decided_under(self.v2, SLOTS, 1, "lighten", local_holdout=3)
        baseline = policy.load_global_baseline(self.root)
        self.assertEqual((), policy.global_experiments(self.root, baseline, reader.profile))
        effective = self.started(reader)
        self.assertEqual({SLOTS: 1, STEPS: 0}, effective["settings"])
        self.assertEqual([{"origin": policy.ORIGIN_PROJECT, "policy_change_id": OVERRIDE_CHANGE,
                           "policy_surface_id": SLOTS, "direction": "lighten", "holdout_setting": 3}],
                         effective["active_experiments"], "the Project-local P6 experiment stays authoritative")
        self.assertEqual(2, policy.required_holdout_slots(effective))
        self.assertEqual(policy.COMPATIBILITY_TOTAL_ADAPTER_V1, effective["compatibility"])

    def test_row_4_no_override_keeps_the_global_experiment_and_its_holdout(self) -> None:
        effective = self.started(NoProfileReader())
        self.assertEqual([(policy.ORIGIN_GLOBAL, LIGHTEN_ID, 3)],
                         [(item["origin"], item["policy_change_id"], item["holdout_setting"])
                          for item in effective["active_experiments"]])
        self.assertEqual(1, policy.required_holdout_slots(effective))

    def test_row_5_the_filter_is_per_surface(self) -> None:
        steps_id = "rgc_" + "4" * 26
        v4 = policy.global_policy_record(4, policy.global_policy_digest(self.v3), {SLOTS: 2, STEPS: 1})
        root = self.root_at(v4, self.changes + [global_change(steps_id, self.v3, v4, "strengthen", surface=STEPS)],
                            "per-surface")
        both = [(item.policy_change_id, item.policy_surface_id)
                for item in policy.global_experiments(root, policy.load_global_baseline(root), None)]
        self.assertEqual([(LIGHTEN_ID, SLOTS), (steps_id, STEPS)], both)
        for overridden, kept, holdouts in ((STEPS, (LIGHTEN_ID, SLOTS, 3), 1), (SLOTS, (steps_id, STEPS, None), 0)):
            with self.subTest(overridden=overridden):
                reader = self.decided_under(v1(), overridden, 2 if overridden == STEPS else 4, "strengthen")
                effective = self.started(reader, root)
                self.assertEqual([kept], [(item["policy_change_id"], item["policy_surface_id"], item["holdout_setting"])
                                          for item in effective["active_experiments"]],
                                 "the inherited surface keeps its Global experiment; the overridden one has none")
                self.assertEqual(holdouts, policy.required_holdout_slots(effective))

    def test_an_override_removed_later_freezes_the_global_experiment_again(self) -> None:
        first = self.decided_under(v1(), SLOTS, 4, "strengthen")
        baseline = policy.load_global_baseline(self.root)
        self.assertEqual((), policy.global_experiments(self.root, baseline, first.profile))
        # a later Profile version, decided under the current Global, removes the override
        removed = policy.ProjectProfile(
            profile_version=2, parent_profile_digest=first.profile.digest, global_baseline_digest=baseline.digest,
            global_baseline_version=3, loader_semantics_identity=policy.LOADER_SEMANTICS_IDENTITY, overrides=(),
            active_experiment_refs=())
        change = {"policy_change_id": "rpc_" + "5" * 26, "after_profile_digest": removed.digest,
                  "global_baseline": baseline.record, "global_baseline_digest": baseline.digest,
                  "affected_policy_surface": SLOTS, "after_setting": 2, "direction": "lighten", "holdout_plan": None}
        effective = self.started(ProfileReader(removed, change))
        self.assertEqual([(policy.ORIGIN_GLOBAL, LIGHTEN_ID, 3)],
                         [(item["origin"], item["policy_change_id"], item["holdout_setting"])
                          for item in effective["active_experiments"]])
        self.assertEqual(policy.COMPATIBILITY_EXACT_DERIVED_SEMANTIC, effective["compatibility"])


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
