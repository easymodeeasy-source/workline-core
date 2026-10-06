"""P6 §30.35: the GlobalPolicyBaseline, the canonical Project Profile and the Effective Policy (§15.8-§15.13, §30.4-§30.7).

* an absent Profile is valid and is the Global baseline; ProjectSTART creates and backfills nothing;
* the Profile is strict: exact fields, sorted unique overrides and refs, the allowed ranges, the lineage chain;
* an incompatible Profile fails closed - no guess, no merge, no dropped override - and is a validation Problem;
* the Effective Policy is a frozen normalized record: a later Profile change does not alter what an open Run bound;
* pre-P6 static policies stay valid exactly; the loader is canonical, read-only and derived (the RB7 seam).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from helpers import WORKLINE_ROOT, WorklineTestCase, copy_workline_root, git
from workline.errors import StopError, ValidationError
from workline.review import history, p4, paths, policy, serialize
from workline.review.store import ReviewStore
from workline.validate import validate_project

RPC = "rpc_01ARZ3NDEKTSV4RRFFQ69G5FAV"
RPC2 = "rpc_01ARZ3NDEKTSV4RRFFQ69G5FB0"


def baseline() -> policy.GlobalPolicyBaseline:
    return policy.load_global_baseline(WORKLINE_ROOT)


def profile(version: int = 1, parent: str | None = None, *, setting: int = 2, surface: str = policy.SURFACE_REQUIRED_SLOTS,
            supporting: str = RPC, refs: tuple[str, ...] = (RPC,), digest: str | None = None) -> policy.ProjectProfile:
    found = policy.SURFACE_BY_ID[surface]
    return policy.ProjectProfile(
        profile_version=version, parent_profile_digest=parent,
        global_baseline_digest=digest or baseline().digest, global_baseline_version=1,
        loader_semantics_identity=policy.LOADER_SEMANTICS_IDENTITY,
        overrides=({"policy_surface_id": surface, "strength_class": found.strength_class, "setting": setting,
                    "direction": "strengthen" if setting > found.global_setting else "lighten",
                    "supporting_policy_change_id": supporting},),
        active_experiment_refs=refs,
    )


def codes(found: list[tuple[str, str]]) -> list[str]:
    return [code for code, _ in found]


def change(change_id: str, before_version: int | None, before_digest: str | None, after: policy.ProjectProfile) -> dict:
    return {"policy_change_id": change_id, "before_profile_version": before_version,
            "before_profile_digest": before_digest, "after_profile_version": after.profile_version,
            "after_profile_digest": after.digest}


class AbsentProfileTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.review = ReviewStore(self.store)

    def test_absent_profile_is_valid_and_is_the_global_baseline(self) -> None:
        self.assertIsNone(self.review.read_profile())
        self.assertIsNone(self.review.read_profile_bytes())
        state = policy.resolve_policy_state(self.review, self.store.workline_root())
        self.assertIsNone(state.profile)
        self.assertEqual((), state.active)
        self.assertEqual({policy.SURFACE_REQUIRED_SLOTS: 1, policy.SURFACE_EXTRA_SCOPE_STEPS: 0},
                         state.effective["settings"])
        self.assertIsNone(state.effective["profile"])
        self.assertEqual(state.baseline.digest, state.effective["global_baseline"]["digest"])
        self.assertEqual([], [problem.code for problem in validate_project(self.store)])

    def test_project_start_creates_and_backfills_no_policy_state(self) -> None:
        self.assertFalse((self.store.root / paths.POLICY_DIR).exists())
        self.assertFalse((self.store.root / paths.REVIEW_DIR).exists())
        source = (WORKLINE_ROOT / "src" / "workline" / "project_start.py").read_text(encoding="utf-8")
        for needle in ("review.policy", "project-profile", "project_policy", "POLICY_DIR"):
            self.assertNotIn(needle, source)

    def test_an_absent_profile_is_never_a_validation_problem(self) -> None:
        (self.store.root / paths.POLICY_DIR / paths.POLICY_CHANGES).mkdir(parents=True)
        self.assertEqual([], [problem.code for problem in validate_project(self.store)])


class StrictProfileTests(unittest.TestCase):
    def test_the_profile_round_trips_canonically(self) -> None:
        found = profile()
        again, text = policy.parse_profile_bytes(found.text().encode("utf-8"), "p")
        self.assertEqual(found, again)
        self.assertEqual(found.digest, serialize.digest_of_text(text))
        self.assertEqual(found.digest, hashlib.sha256(found.text().encode("utf-8")).hexdigest())

    def test_non_canonical_bytes_are_refused(self) -> None:
        text = profile().text()
        for raw in (text.replace("\n", "\r\n").encode("utf-8"), (text + "\n").encode("utf-8"), b"not: [yaml"):
            with self.subTest(raw=raw[:20]), self.assertRaises(ValidationError) as raised:
                policy.parse_profile_bytes(raw, "p")
            self.assertEqual(policy.CODE_PROFILE_INVALID, raised.exception.code)

    def test_unknown_and_missing_fields_fail_closed(self) -> None:
        record = profile().to_record()
        for mutate in (lambda r: r.update({"script": "rm -rf"}), lambda r: r.pop("active_experiment_refs"),
                       lambda r: r.update({"actor_credential": "x"}), lambda r: r.update({"schema": "other"})):
            broken = dict(record)
            mutate(broken)
            with self.subTest(fields=sorted(broken)):
                self.assertIn(policy.CODE_PROFILE_INVALID, codes(policy.profile_problems(broken, "p")))

    def test_overrides_are_sorted_unique_and_never_restate_the_global_setting(self) -> None:
        record = profile().to_record()
        a = dict(record["overrides"][0])
        b = {"policy_surface_id": policy.SURFACE_EXTRA_SCOPE_STEPS, "strength_class": policy.CLASS_ADAPTIVE,
             "setting": 1, "direction": "strengthen", "supporting_policy_change_id": RPC}
        self.assertEqual([], policy.profile_problems({**record, "overrides": [a, b]}, "p"))
        self.assertIn(policy.CODE_PROFILE_INVALID, codes(policy.profile_problems({**record, "overrides": [b, a]}, "p")))
        self.assertIn(policy.CODE_PROFILE_INVALID, codes(policy.profile_problems({**record, "overrides": [a, dict(a)]}, "p")))
        restated = dict(a, setting=1)
        self.assertIn(policy.CODE_PROFILE_INVALID, codes(policy.profile_problems({**record, "overrides": [restated]}, "p")))
        wrong = dict(a, direction="lighten")
        self.assertIn(policy.CODE_PROFILE_INVALID, codes(policy.profile_problems({**record, "overrides": [wrong]}, "p")))
        unsupported = dict(a, supporting_policy_change_id="rel_01ARZ3NDEKTSV4RRFFQ69G5FAV")
        self.assertIn(policy.CODE_PROFILE_INVALID,
                      codes(policy.profile_problems({**record, "overrides": [unsupported]}, "p")))

    def test_active_experiment_refs_are_sorted_and_unique(self) -> None:
        record = profile().to_record()
        for refs in ([RPC2, RPC], [RPC, RPC], ["r_01ARZ3NDEKTSV4RRFFQ69G5FAV"]):
            with self.subTest(refs=refs):
                self.assertIn(policy.CODE_PROFILE_INVALID,
                              codes(policy.profile_problems({**record, "active_experiment_refs": refs}, "p")))

    def test_version_and_parent_digest_chain(self) -> None:
        first = profile()
        self.assertEqual([], policy.profile_problems(first.to_record(), "p"))
        self.assertIn(policy.CODE_LINEAGE_INVALID,
                      codes(policy.profile_problems({**first.to_record(), "parent_profile_digest": "b" * 64}, "p")))
        self.assertIn(policy.CODE_LINEAGE_INVALID,
                      codes(policy.profile_problems({**first.to_record(), "profile_version": 2}, "p")))
        self.assertIn(policy.CODE_PROFILE_INVALID,
                      codes(policy.profile_problems({**first.to_record(), "profile_version": 0}, "p")))
        second = profile(2, first.digest, setting=3, supporting=RPC2, refs=(RPC, RPC2))
        changes = {RPC: change(RPC, None, None, first), RPC2: change(RPC2, 1, first.digest, second)}
        self.assertEqual([], policy.lineage_problems(second, changes))
        # a skipped version, a fork, a Profile no change produced, a wrong parent
        third = profile(3, second.digest, setting=4, supporting=RPC2, refs=(RPC, RPC2))
        self.assertIn(policy.CODE_LINEAGE_INVALID, codes(policy.lineage_problems(third, changes)))
        forked = dict(changes, rpc_01ARZ3NDEKTSV4RRFFQ69G5FB1=change("rpc_01ARZ3NDEKTSV4RRFFQ69G5FB1", 1, first.digest, second))
        self.assertIn(policy.CODE_LINEAGE_INVALID, codes(policy.lineage_problems(second, forked)))
        self.assertIn(policy.CODE_LINEAGE_INVALID, codes(policy.lineage_problems(second, {RPC: changes[RPC]})))
        wrong_parent = profile(2, "c" * 64, setting=3, supporting=RPC2, refs=(RPC, RPC2))
        self.assertIn(policy.CODE_LINEAGE_INVALID,
                      codes(policy.lineage_problems(wrong_parent, {RPC: changes[RPC], RPC2: change(RPC2, 1, first.digest, wrong_parent)})))
        self.assertIn(policy.CODE_LINEAGE_INVALID, codes(policy.lineage_problems(None, changes)))
        self.assertEqual([], policy.lineage_problems(None, {}))


class CompatibilityTests(WorklineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.review = ReviewStore(self.store)

    def write_profile(self, found: policy.ProjectProfile) -> None:
        target = self.store.root / paths.POLICY_PROFILE_REL
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(found.text().encode("utf-8"))

    def test_an_incompatible_profile_fails_closed_and_is_a_validation_problem(self) -> None:
        self.write_profile(profile(digest="a" * 64))
        with self.assertRaises(StopError) as raised:
            policy.resolve_policy_state(self.review, self.store.workline_root())
        self.assertEqual(policy.CODE_PROFILE_INCOMPATIBLE, raised.exception.code)
        self.assertIn("no override is guessed, merged or dropped", str(raised.exception))
        self.assertIn(policy.CODE_PROFILE_INCOMPATIBLE, [problem.code for problem in validate_project(self.store)])

    def test_a_malformed_profile_fails_closed_and_is_a_validation_problem(self) -> None:
        target = self.store.root / paths.POLICY_PROFILE_REL
        target.parent.mkdir(parents=True)
        target.write_text("schema: review-p6-project-profile\nversion: 1\n", encoding="utf-8", newline="")
        with self.assertRaises(StopError) as raised:
            policy.resolve_policy_state(self.review, self.store.workline_root())
        self.assertEqual(policy.CODE_PROFILE_INVALID, raised.exception.code)
        self.assertIn(policy.CODE_PROFILE_INVALID, [problem.code for problem in validate_project(self.store)])

    def test_a_workline_root_change_makes_the_profile_incompatible(self) -> None:
        other = copy_workline_root(self.tmp / "root2")
        skill = other / ".claude" / "skills" / "review" / "SKILL.md"
        skill.write_bytes(skill.read_bytes() + b"\n")
        found = profile()
        self.assertIsNone(policy.compatibility_problem(found, baseline()))
        self.assertIsNotNone(policy.compatibility_problem(found, policy.load_global_baseline(other)))

    def test_a_profile_entry_that_is_a_directory_or_an_unknown_entry_is_a_namespace_problem(self) -> None:
        (self.store.root / paths.POLICY_PROFILE_REL).mkdir(parents=True)
        (self.store.root / paths.POLICY_DIR / "notes.yaml").write_text("x: 1\n", encoding="utf-8")
        found = [problem.code for problem in validate_project(self.store)]
        self.assertIn("review_namespace_invalid", found)


class EffectivePolicyTests(unittest.TestCase):
    def test_the_effective_policy_binds_baseline_profile_settings_meta_rules_and_loader(self) -> None:
        base = baseline()
        found = policy.effective_policy_record(base, profile(), ())
        self.assertEqual(found, policy.parse_effective_policy(found, "e"))
        self.assertEqual(base.digest, found["global_baseline"]["digest"])
        self.assertEqual({"profile_version": 1, "digest": profile().digest}, found["profile"])
        self.assertEqual(2, policy.setting(found, policy.SURFACE_REQUIRED_SLOTS))
        self.assertEqual(0, policy.setting(found, policy.SURFACE_EXTRA_SCOPE_STEPS))
        self.assertEqual(policy.meta_rules_digest(), found["meta_rules_digest"])
        self.assertEqual(policy.LOADER_SEMANTICS_IDENTITY, found["loader_semantics_identity"])
        self.assertNotEqual(policy.effective_policy_hash(found),
                            policy.effective_policy_hash(policy.effective_policy_record(base, None, ())))

    def test_a_tampered_effective_policy_is_refused(self) -> None:
        found = policy.effective_policy_record(baseline(), None, ())
        for mutate in (lambda r: r["settings"].update({policy.SURFACE_REQUIRED_SLOTS: 9}),
                       lambda r: r.update({"policy_id": p4.P5_POLICY_ID}),
                       lambda r: r["settings"].pop(policy.SURFACE_EXTRA_SCOPE_STEPS),
                       lambda r: r.update({"extra": 1}),
                       lambda r: r.update({"meta_rules_digest": "d" * 64})):
            broken = serialize.canonical_data(found)
            mutate(broken)
            with self.assertRaises(ValidationError):
                policy.parse_effective_policy(broken, "e")

    def test_a_later_profile_change_does_not_alter_what_an_open_run_froze(self) -> None:
        base = baseline()
        frozen = policy.effective_policy_record(base, None, ())
        envelope = p4.discovery_request(
            review_contract=p4.PLANNING_CONTRACT, review_kind="roadmap-plan-v1", viewpoint="correctness",
            candidate={"c": 1}, context={"x": 1}, requirement={"r": 1}, candidate_generation=1, succession=None,
            set_aside_runs=(), human_decision=None, policy_id=p4.P6_POLICY_ID, effective_policy=frozen,
            discovery_role=policy.ROLE_REQUIRED,
        )
        before = p4.envelope_policy_hash(envelope)
        later = policy.effective_policy_record(base, profile(), ())
        self.assertNotEqual(policy.effective_policy_hash(later), before)
        self.assertEqual(before, p4.envelope_policy_hash(envelope))  # the request is the frozen authority
        self.assertEqual(frozen, p4.effective_policy_of_envelope(envelope))

    def test_holdout_and_reverification_levels_follow_the_active_experiments(self) -> None:
        base = baseline()
        lightened = profile(setting=2, refs=(RPC,))
        active = (policy.ActiveExperiment(RPC, policy.SURFACE_REQUIRED_SLOTS, policy.DIRECTION_LIGHTEN, 3),)
        found = policy.effective_policy_record(base, lightened, active)
        self.assertEqual(1, policy.required_holdout_slots(found))
        steps = profile(setting=1, surface=policy.SURFACE_EXTRA_SCOPE_STEPS)
        active = (policy.ActiveExperiment(RPC, policy.SURFACE_EXTRA_SCOPE_STEPS, policy.DIRECTION_LIGHTEN, 2),)
        found = policy.effective_policy_record(base, steps, active)
        self.assertEqual((("LOCAL", "SHARED"), ("CONTRACT",)), policy.reverification_levels(found, "LOCAL"))
        self.assertEqual(0, policy.required_holdout_slots(found))


class PreP6CompatibilityTests(unittest.TestCase):
    def test_the_static_p4_and_p5_policies_are_exactly_what_they_were(self) -> None:
        self.assertEqual((p4.POLICY_ID, history.P5_POLICY_ID), p4.POLICY_IDS)
        self.assertEqual({p4.POLICY_ID, history.P5_POLICY_ID}, set(p4.POLICY_RECORDS))
        for policy_id in p4.POLICY_IDS:
            self.assertEqual(serialize.digest(p4.policy_record(policy_id)), p4.policy_hash(policy_id))
            self.assertEqual(p4.policy_hash(policy_id), p4.family_policy_hash(policy_id))
        with self.assertRaises(ValidationError):
            p4.policy_hash(p4.P6_POLICY_ID)  # a P6 Run has no static Effective Policy
        self.assertIsNone(p4.policy_named(p4.P6_POLICY_ID))

    def test_a_p4_and_a_p5_request_are_read_exactly_as_before(self) -> None:
        common = dict(review_contract=p4.PLANNING_CONTRACT, review_kind="roadmap-plan-v1", viewpoint="correctness",
                      candidate={"c": 1}, context={"x": 1}, requirement={"r": 1}, candidate_generation=1,
                      succession=None, set_aside_runs=(), human_decision=None)
        p4_request = p4.discovery_request(**common, policy_id=p4.POLICY_ID)
        p5_request = p4.discovery_request(**common, policy_id=p4.P5_POLICY_ID)
        self.assertNotIn(policy.EFFECTIVE_POLICY_KEY, p4_request)
        self.assertNotIn(policy.EFFECTIVE_POLICY_KEY, p5_request)
        self.assertNotIn(policy.DISCOVERY_ROLE_KEY, p5_request)
        self.assertEqual(p4.POLICY_ID, p4.policy_of_envelope(p4_request))
        self.assertEqual(p4.P5_POLICY_ID, p4.policy_of_envelope(p5_request))
        self.assertEqual(p4.policy_hash(p4.P5_POLICY_ID), p4.envelope_policy_hash(p5_request))
        with self.assertRaises(ValidationError):
            p4.discovery_request(**common, policy_id=p4.P5_POLICY_ID, effective_policy={"x": 1})


class LoaderSeamTests(WorklineTestCase):
    def test_the_derived_baseline_is_canonical_exact_and_reproducible(self) -> None:
        first, second = baseline(), baseline()
        self.assertEqual(first.record, second.record)
        self.assertEqual(policy.SOURCE_MODE_DERIVED, first.source_mode)
        self.assertEqual(set(policy.BASELINE_FIELDS), set(first.record))
        self.assertEqual(list(policy.BASELINE_AUTHORITY_IDS),
                         [item["id"] for item in first.record["root_authority_digests"]])
        self.assertEqual(["planning", "work", "p4", "p5", "p6"],
                         [item["id"] for item in first.record["source_policy_identities"]])
        self.assertEqual(policy.GlobalPolicyBaseline(first.record).digest, policy.parse_baseline(first.record, "b").digest)

    def test_the_loader_never_mutates_the_workline_root(self) -> None:
        root = copy_workline_root(self.tmp / "root")

        def snapshot() -> dict[str, tuple[bytes, int]]:
            return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
                    for path in sorted(root.rglob("*")) if path.is_file()}

        before = snapshot()
        policy.load_global_baseline(root)
        self.assertEqual(before, snapshot())

    def test_an_unreadable_root_authority_stops_the_loader(self) -> None:
        root = copy_workline_root(self.tmp / "root")
        (root / ".claude" / "skills" / "start" / "SKILL.md").unlink()
        with self.assertRaises(StopError) as raised:
            policy.load_global_baseline(root)
        self.assertEqual(policy.CODE_BASELINE_UNAVAILABLE, raised.exception.code)


if __name__ == "__main__":
    unittest.main()
