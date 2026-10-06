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


def p7_root_copy(dest: Path) -> Path:
    """A copied Workline root carrying its tracked Global policy (P7 §31.2, RB7C-7): the loader requires the file.

    ``copy_workline_root`` gains the file itself with RB7's shared helper change; until then the copy is completed
    here, and afterwards this adds nothing.
    """
    root = copy_workline_root(dest)
    target = root.joinpath(*policy.GLOBAL_POLICY_REL.split("/"))
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(WORKLINE_ROOT.joinpath(*policy.GLOBAL_POLICY_REL.split("/")).read_bytes())
    return root


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


class ChangeReader:
    """The two change-record readers compatibility recovery uses, over in-memory records (R6-2 item 3)."""

    def __init__(self, *changes: dict) -> None:
        self.changes = {item["policy_change_id"]: item for item in changes}

    def policy_change_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.changes))

    def read_policy_change(self, change_id: str) -> dict:
        return self.changes[change_id]

    def policy_change_exists(self, change_id: str) -> bool:
        return change_id in self.changes


def change_with_baseline(change_id: str, after: policy.ProjectProfile, record: dict, *, digest: str | None = None,
                         surface: str = policy.SURFACE_REQUIRED_SLOTS, setting: int = 2) -> dict:
    return {"policy_change_id": change_id, "after_profile_digest": after.digest, "global_baseline": record,
            "global_baseline_digest": digest or serialize.digest(record), "affected_policy_surface": surface,
            "after_setting": setting}


def change(change_id: str, before_version: int | None, before_digest: str | None, after: policy.ProjectProfile,
           *, surface: str | None = None, setting: int | None = None) -> dict:
    """The lineage fields of a change record; its surface / after setting are those of the override it supports in
    ``after`` (RB6FR1-3), unless given."""
    supported = next((item for item in after.overrides if item["supporting_policy_change_id"] == change_id), None)
    return {"policy_change_id": change_id, "before_profile_version": before_version,
            "before_profile_digest": before_digest, "after_profile_version": after.profile_version,
            "after_profile_digest": after.digest,
            "affected_policy_surface": surface or (supported or {}).get("policy_surface_id"),
            "after_setting": setting if setting is not None else (supported or {}).get("setting")}


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

    def test_overrides_are_sorted_and_unique(self) -> None:
        # the structural reader keeps the §30.5 rules only (FC-RB7-9 b): surface / class / range / id / sort / uniqueness
        record = profile().to_record()
        a = dict(record["overrides"][0])
        b = {"policy_surface_id": policy.SURFACE_EXTRA_SCOPE_STEPS, "strength_class": policy.CLASS_ADAPTIVE,
             "setting": 1, "direction": "strengthen", "supporting_policy_change_id": RPC}
        self.assertEqual([], policy.profile_problems({**record, "overrides": [a, b]}, "p"))
        self.assertIn(policy.CODE_PROFILE_INVALID, codes(policy.profile_problems({**record, "overrides": [b, a]}, "p")))
        self.assertIn(policy.CODE_PROFILE_INVALID, codes(policy.profile_problems({**record, "overrides": [a, dict(a)]}, "p")))
        self.assertIn(policy.CODE_PROFILE_INVALID,
                      codes(policy.profile_problems({**record, "overrides": [dict(a, direction="sideways")]}, "p")))
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

    def test_an_override_is_exactly_what_its_supporting_change_decided(self) -> None:
        """RB6FR1-3: an override's surface and setting are those of the change it names (affected_policy_surface,
        after_setting) - checked by lineage itself, not only by the compatibility decision."""
        first = profile()
        good = {RPC: change(RPC, None, None, first)}
        self.assertEqual([], policy.lineage_problems(first, good))
        for name, forged in (("another setting", change(RPC, None, None, first, setting=4)),
                             ("another surface", change(RPC, None, None, first, surface=policy.SURFACE_EXTRA_SCOPE_STEPS)),
                             ("no surface or setting recorded", {key: value for key, value in good[RPC].items()
                                                                 if key not in ("affected_policy_surface",
                                                                                "after_setting")})):
            with self.subTest(name):
                found = policy.lineage_problems(first, {RPC: forged})
                self.assertIn(policy.CODE_LINEAGE_INVALID, codes(found))
                self.assertIn("is not the surface and setting its supporting policy change", found[-1][1])

    def test_genuine_carried_rollback_and_experiment_shapes_keep_their_lineage(self) -> None:
        """RB6FR1-3 pins the genuine shapes (``policy.expected_after_profile``): an override carried across a change
        on the other surface keeps the change that set it; a rollback away from the Global supports the restored
        setting; a rollback to the Global removes the override; experiment refs are not overrides."""
        surface_b = policy.SURFACE_BY_ID[policy.SURFACE_EXTRA_SCOPE_STEPS]
        first = profile(setting=3)  # RPC: required_slots 1 -> 3
        carried_override = dict(first.overrides[0])
        second = policy.ProjectProfile(  # RPC2: extra_scope_steps 0 -> 1, RPC's override carried unchanged
            2, first.digest, baseline().digest, 1, policy.LOADER_SEMANTICS_IDENTITY,
            (carried_override, {"policy_surface_id": surface_b.policy_surface_id, "strength_class": surface_b.strength_class,
                                "setting": 1, "direction": "strengthen", "supporting_policy_change_id": RPC2}),
            (RPC, RPC2))
        changes = {RPC: change(RPC, None, None, first), RPC2: change(RPC2, 1, first.digest, second)}
        self.assertEqual([], policy.lineage_problems(second, changes), "a carried override keeps its own change")
        rpc3 = "rpc_01ARZ3NDEKTSV4RRFFQ69G5FB1"
        rolled_back = policy.ProjectProfile(  # RPC3 rolls RPC back to 2 (not the Global): it supports setting 2
            3, second.digest, baseline().digest, 1, policy.LOADER_SEMANTICS_IDENTITY,
            (dict(carried_override, setting=2, supporting_policy_change_id=rpc3), second.overrides[1]), (RPC2, rpc3))
        rollback = change(rpc3, 2, second.digest, rolled_back)
        self.assertEqual((policy.SURFACE_REQUIRED_SLOTS, 2), (rollback["affected_policy_surface"], rollback["after_setting"]))
        self.assertEqual([], policy.lineage_problems(rolled_back, dict(changes, **{rpc3: rollback})))
        to_global = policy.ProjectProfile(  # RPC3 rolls RPC back to the Global 1: the override is gone
            3, second.digest, baseline().digest, 1, policy.LOADER_SEMANTICS_IDENTITY, (second.overrides[1],), (RPC2, rpc3))
        self.assertEqual([], policy.lineage_problems(to_global, dict(changes, **{rpc3: change(
            rpc3, 2, second.digest, to_global, surface=policy.SURFACE_REQUIRED_SLOTS, setting=1)})))


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
        # RB6B-M3: a Profile no stored change produced fails the new-Run lineage gate first; validation names both
        # the broken lineage and the incompatibility (its written-under baseline cannot be recovered)
        self.write_profile(profile(digest="a" * 64))
        with self.assertRaises(StopError) as raised:
            policy.resolve_policy_state(self.review, self.store.workline_root())
        self.assertEqual(policy.CODE_LINEAGE_INVALID, raised.exception.code)
        self.assertIn("policy maintenance / reconcile", str(raised.exception))
        found = [problem.code for problem in validate_project(self.store)]
        self.assertIn(policy.CODE_PROFILE_INCOMPATIBLE, found)
        self.assertIn(policy.CODE_LINEAGE_INVALID, found)

    def test_a_malformed_profile_fails_closed_and_is_a_validation_problem(self) -> None:
        target = self.store.root / paths.POLICY_PROFILE_REL
        target.parent.mkdir(parents=True)
        target.write_text("schema: review-p6-project-profile\nversion: 1\n", encoding="utf-8", newline="")
        with self.assertRaises(StopError) as raised:
            policy.resolve_policy_state(self.review, self.store.workline_root())
        self.assertEqual(policy.CODE_PROFILE_INVALID, raised.exception.code)
        self.assertIn(policy.CODE_PROFILE_INVALID, [problem.code for problem in validate_project(self.store)])

    def test_a_text_only_root_edit_keeps_the_profile_compatible(self) -> None:
        # R6-2 item 4: the canonical digest moves, the policy-semantic projection does not
        other = p7_root_copy(self.tmp / "root2")
        skill = other / ".claude" / "skills" / "review" / "SKILL.md"
        skill.write_bytes(skill.read_bytes() + b"\n")
        edited = policy.load_global_baseline(other)
        self.assertNotEqual(baseline().digest, edited.digest)
        self.assertEqual(baseline().semantic_projection, edited.semantic_projection)
        found = profile()
        reader = ChangeReader(change_with_baseline(RPC, found, baseline().record))
        self.assertIsNone(policy.compatibility_problem(found, baseline(), reader))
        self.assertIsNone(policy.compatibility_problem(found, edited, reader))

    def test_a_semantic_baseline_change_makes_the_profile_incompatible(self) -> None:
        found = profile()
        changed = serialize.canonical_data(baseline().record)
        changed["surfaces"][0]["global_setting"] = 2
        reader = ChangeReader(change_with_baseline(RPC, found, changed, digest=found.global_baseline_digest))
        self.assertIn("cannot be recovered", policy.compatibility_problem(found, baseline(), reader))
        other = dict(baseline().record, meta_rules_id="review-v1-p6-meta-rules-v9")
        found = profile(digest=serialize.digest(other))
        reader = ChangeReader(change_with_baseline(RPC, found, other))
        self.assertIn("policy semantics", policy.compatibility_problem(found, baseline(), reader))

    def test_each_override_is_judged_against_the_global_it_was_decided_under(self) -> None:
        # FC-RB7-8 / -9: the restate / direction checks run in the evidence-backed compatibility decision, against the
        # baseline record the override's supporting change binds - never in the structural reader, never skipped
        for setting, direction, expected in ((1, "lighten", "restates"), (2, "lighten", "other side"),
                                             (2, "strengthen", None)):
            with self.subTest(setting=setting, direction=direction):
                found = policy.ProjectProfile(
                    1, None, baseline().digest, 1, policy.LOADER_SEMANTICS_IDENTITY,
                    ({"policy_surface_id": policy.SURFACE_REQUIRED_SLOTS, "strength_class": policy.CLASS_DEFAULT,
                      "setting": setting, "direction": direction, "supporting_policy_change_id": RPC},), (RPC,))
                self.assertEqual([], policy.profile_problems(found.to_record(), "p"))
                reader = ChangeReader(change_with_baseline(RPC, found, baseline().record, setting=setting))
                problem = policy.compatibility_problem(found, baseline(), reader)
                if expected is None:
                    self.assertIsNone(problem)
                else:
                    self.assertIn(expected, problem)

    def test_a_carried_override_keeps_its_own_global(self) -> None:
        # FC-RB7-9 (c): a later Global default may differ; the override decided under its own Global stays valid
        later = serialize.canonical_data(baseline().record)
        later["surfaces"][0]["global_setting"] = 2  # what a later Global would say; this change predates it
        found = profile()
        reader = ChangeReader(change_with_baseline(RPC, found, baseline().record))
        self.assertEqual([], policy.override_global_problems(found, reader))
        reader_later = ChangeReader(change_with_baseline(RPC, found, later, digest=found.global_baseline_digest))
        self.assertIn("restates", policy.override_global_problems(found, reader_later)[0])

    def test_the_written_under_baseline_must_be_recovered_positively(self) -> None:
        found = profile()
        self.assertIn("0 applied", policy.compatibility_problem(found, baseline(), ChangeReader()))
        twice = ChangeReader(change_with_baseline(RPC, found, baseline().record),
                             change_with_baseline(RPC2, found, baseline().record))
        self.assertIn("2 applied", policy.compatibility_problem(found, baseline(), twice))
        foreign = profile(digest="a" * 64)
        reader = ChangeReader(change_with_baseline(RPC, foreign, baseline().record))
        self.assertIn("cannot be recovered", policy.compatibility_problem(foreign, baseline(), reader))

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


#: RB6B-L12: computed at the base commit 61b0b9dd (before any P6 code) and pinned as literals, so the pre-P6
#: identities are compared with what the base build said - never with the new code itself.
BASE_LITERALS = {
    "p4_policy_hash": "49abd2457c0affa393f4bb84c9cc6bffbc5cd461ddc3833501b252767343b6e5",
    "p5_policy_hash": "662bea5575a40b91e46758c472fc2a8ec329e659ea0325dac6c24f27120d16e1",
    "planning_policy_hash": "c556c5e68438f8656298c47060d62ad45830a42eae951bb7bb31ec85fbfe80ca",
    "work_policy_hash": "46fde266f96c666101f9ca0e202e8a93048dc50a7cf49764039ca4baed6ef970",
    "p4_request_digest": "e7734e23872d51427832ea1a8fb3eb7d4522e39fd56e9421a63542694317668f",
    "p5_request_digest": "9c8b12fbab3b0de596256f09e2ebee1f2e7c5f37b487b6826afe3cf88a925c5b",
}


class PreP6CompatibilityTests(unittest.TestCase):
    def test_the_pre_p6_identities_are_the_base_commit_literals(self) -> None:
        from workline.review import planning, work_review

        common = dict(review_kind="planning", viewpoint="correctness", candidate={"a": 1}, context={"b": 2},
                      requirement={"c": 3}, candidate_generation=1, succession=None, set_aside_runs=(),
                      human_decision=None, review_contract=p4.PLANNING_CONTRACT)
        self.assertEqual(BASE_LITERALS, {
            "p4_policy_hash": p4.policy_hash(p4.POLICY_ID),
            "p5_policy_hash": p4.policy_hash(p4.P5_POLICY_ID),
            "planning_policy_hash": planning.policy_hash(),
            "work_policy_hash": work_review.policy_hash(),
            "p4_request_digest": serialize.digest(p4.discovery_request(**common, policy_id=p4.POLICY_ID)),
            "p5_request_digest": serialize.digest(p4.discovery_request(**common, policy_id=p4.P5_POLICY_ID)),
        })

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
        # RB7C-10 (pin updated deliberately with the P7 materialization, RB7 step 4): the derived builder is asserted
        # directly - the loader itself now reads the tracked Global policy - and the loaded baseline differs from it
        # in source_mode and provenance identity only (§31.3)
        first, second = policy.derived_global_baseline(WORKLINE_ROOT), policy.derived_global_baseline(WORKLINE_ROOT)
        self.assertEqual(first.record, second.record)
        self.assertEqual(policy.SOURCE_MODE_DERIVED, first.source_mode)
        self.assertEqual(set(policy.BASELINE_FIELDS), set(first.record))
        self.assertEqual(list(policy.BASELINE_AUTHORITY_IDS),
                         [item["id"] for item in first.record["root_authority_digests"]])
        self.assertEqual(["planning", "work", "p4", "p5", "p6"],
                         [item["id"] for item in first.record["source_policy_identities"]])
        self.assertEqual(policy.GlobalPolicyBaseline(first.record).digest, policy.parse_baseline(first.record, "b").digest)
        loaded = baseline()
        self.assertEqual(policy.SOURCE_MODE_MATERIALIZED, loaded.source_mode)
        self.assertEqual(loaded.record, baseline().record)
        self.assertEqual(first.semantic_projection, loaded.semantic_projection)
        self.assertEqual({"source_mode", "global_policy_identity"},
                         {key for key in first.record if first.record[key] != loaded.record[key]})

    def test_the_loader_never_mutates_the_workline_root(self) -> None:
        root = p7_root_copy(self.tmp / "root")

        def snapshot() -> dict[str, tuple[bytes, int]]:
            return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
                    for path in sorted(root.rglob("*")) if path.is_file()}

        before = snapshot()
        policy.load_global_baseline(root)
        self.assertEqual(before, snapshot())

    def test_an_unreadable_root_authority_stops_the_loader(self) -> None:
        root = p7_root_copy(self.tmp / "root")
        (root / ".claude" / "skills" / "start" / "SKILL.md").unlink()
        with self.assertRaises(StopError) as raised:
            policy.load_global_baseline(root)
        self.assertEqual(policy.CODE_BASELINE_UNAVAILABLE, raised.exception.code)


if __name__ == "__main__":
    unittest.main()
