"""P7 Profile compatibility adapter v1 (``WORKLINE_COMPLETION_SPRINT`` §31.21, §31.52; §16.11 / §16.28 rows), RB7-C.

Exhaustive and pure over the finite Profile v1 domain of the two fixed integer surfaces:

* absence, each valid single override and both overrides, at every valid old / new Global setting pair (required
  slots 1..4 x 1..4, extra scope steps 0..3 x 0..3): the overlay keeps every absolute local override and takes the
  new Global setting elsewhere - the same normalized local override semantics, every value in its fixed range;
* no Profile field is dropped, renamed or rewritten (no backfill); an unsupported Profile schema, another loader or
  a structurally invalid Profile is refused, never guessed; a stronger mandatory Global is never weakened by an old
  local override (vacuous for v1 - both surfaces are default / adaptive - and still asserted);
* the proof is total and binds both Global identities; an unprovable case blocks automatic promotion;
* R6-2 / CP RB7-PREP item 4: equal policy-semantic projections (the initial materialization, a text-only root edit)
  keep the exact derived-semantic interpretation; only a real changed Global projection uses the total adapter v1.

The RB7C-8 loader rows (materialized v2 parses, a v2-frozen Effective Policy reads, ...) are RB7-F's, in
``test_global_policy_materialization.py``.
"""

from __future__ import annotations

from dataclasses import replace
from itertools import product
from typing import Any
import unittest
from unittest import mock

from workline.errors import StopError
from workline.review import global_policy as gp
from workline.review import policy

from test_global_policy_promotion import (
    CHANGE_ID, SLOTS, STEPS, V1, change_request, digest_of, root_policy_hash_stub, successor, two_independent,
)

SURFACES = {SLOTS: range(1, 5), STEPS: range(0, 4)}
SUPPORTING = "rpc_" + "3" * 26


def profile(overrides: dict[str, int], *, refs: tuple[str, ...] = ()) -> policy.ProjectProfile:
    found = []
    for surface_id, value in sorted(overrides.items()):
        surface = policy.SURFACE_BY_ID[surface_id]
        found.append({"policy_surface_id": surface_id, "strength_class": surface.strength_class, "setting": value,
                      "direction": "strengthen" if value > surface.global_setting else "lighten",
                      "supporting_policy_change_id": SUPPORTING})
    return policy.ProjectProfile(
        profile_version=2, parent_profile_digest=digest_of("parent"), global_baseline_digest=digest_of("baseline"),
        global_baseline_version=1, loader_semantics_identity=policy.LOADER_SEMANTICS_IDENTITY,
        overrides=tuple(found), active_experiment_refs=refs)


def settings(slots: int, steps: int) -> dict[str, int]:
    return {SLOTS: slots, STEPS: steps}


def baseline_record(global_policy: dict[str, Any], authority: tuple[dict[str, str], ...] = ()) -> dict[str, Any]:
    return policy.materialized_baseline_record(global_policy, authority, ())


class ExhaustiveAdapterTests(unittest.TestCase):
    def test_every_override_presence_and_every_old_new_pair_keeps_the_local_semantics(self) -> None:
        cases = 0
        presences = [{}, *({surface: value} for surface, values in SURFACES.items() for value in values),
                     *({SLOTS: a, STEPS: b} for a, b in product(SURFACES[SLOTS], SURFACES[STEPS]))]
        for overrides in presences:
            found = profile(overrides)
            before_record = found.to_record()
            for old_slots, new_slots, old_steps, new_steps in product(SURFACES[SLOTS], SURFACES[SLOTS],
                                                                      SURFACES[STEPS], SURFACES[STEPS]):
                old, new = settings(old_slots, old_steps), settings(new_slots, new_steps)
                self.assertIsNone(gp.adapter_v1_problem(found, old, new))
                overlay = gp.adapt_profile_v1(found, old, new)
                for surface_id in SURFACES:
                    expected = overrides.get(surface_id, new[surface_id])
                    if overlay[surface_id] != expected:
                        self.fail(f"{overrides} {old}->{new}: {surface_id} is {overlay[surface_id]}, not {expected}")
                    self.assertTrue(policy.SURFACE_BY_ID[surface_id].in_range(overlay[surface_id]))
                cases += 1
            self.assertEqual(before_record, found.to_record(), "no Profile field is dropped, renamed or rewritten")
        self.assertEqual((1 + 4 + 4 + 16) * 4 * 4 * 4 * 4, cases)

    def test_absence_follows_the_new_global_exactly(self) -> None:
        for old, new in product(product(SURFACES[SLOTS], SURFACES[STEPS]), repeat=2):
            with self.subTest(old=old, new=new):
                self.assertEqual(settings(*new), gp.adapt_profile_v1(None, settings(*old), settings(*new)))

    def test_a_project_may_stay_stricter_or_lighter_than_a_later_global_default(self) -> None:
        stricter = profile({SLOTS: 2})
        self.assertEqual(2, gp.adapt_profile_v1(stricter, settings(1, 0), settings(3, 0))[SLOTS],
                         "an absolute local override is kept, even below a strengthened default surface")
        self.assertEqual(2, gp.adapt_profile_v1(stricter, settings(1, 0), settings(2, 0))[SLOTS])


class RefusalTests(unittest.TestCase):
    def test_an_unsupported_profile_schema_or_loader_is_refused_never_guessed(self) -> None:
        old = new = settings(1, 0)
        valid = profile({SLOTS: 2})
        cases = {
            "a raw record": valid.to_record(),
            "another loader": replace(valid, loader_semantics_identity="review-v2-other-loader"),
            "unsorted overrides": replace(valid, overrides=tuple(reversed(profile({SLOTS: 2, STEPS: 1}).overrides))),
            "out-of-range override": replace(valid, overrides=({**valid.overrides[0], "setting": 9},)),
        }
        for name, found in cases.items():
            with self.subTest(case=name):
                self.assertIsNotNone(gp.adapter_v1_problem(found, old, new))  # type: ignore[arg-type]
                with self.assertRaises(StopError) as raised:
                    gp.adapt_profile_v1(found, old, new)  # type: ignore[arg-type]
                self.assertEqual(gp.CODE_COMPATIBILITY_UNPROVEN, raised.exception.code)

    def test_global_settings_stay_inside_the_fixed_ranges(self) -> None:
        for name, old, new in (("new out of range", settings(1, 0), settings(5, 0)),
                               ("old missing a surface", {SLOTS: 1}, settings(1, 0)),
                               ("new extra surface", settings(1, 0), {**settings(1, 0), "review.extra.surface": 1})):
            with self.subTest(case=name):
                self.assertIsNotNone(gp.adapter_v1_problem(None, old, new))

    def test_a_stronger_mandatory_global_is_never_weakened_by_an_old_override(self) -> None:
        mandatory = replace(policy.SURFACE_BY_ID[SLOTS], strength_class=policy.CLASS_MANDATORY)
        found = profile({SLOTS: 2})
        with mock.patch.dict(policy.SURFACE_BY_ID, {SLOTS: mandatory}):
            self.assertIsNotNone(gp.adapter_v1_problem(found, settings(1, 0), settings(3, 0)),
                                 "vacuous for v1, asserted: a mandatory surface is never weakened")
        self.assertTrue(all(surface.strength_class != policy.CLASS_MANDATORY for surface in policy.SURFACES))


class ProofTests(unittest.TestCase):
    def test_the_proof_is_total_over_profile_v1_and_binds_both_globals(self) -> None:
        after = successor(V1, slots=3)
        proof = gp.compatibility_proof(V1, after)
        self.assertTrue(proof["total"])
        self.assertEqual(1 + 9 * 9, proof["cases"], "absence plus every presence / setting / direction combination")
        self.assertEqual((policy.global_policy_digest(V1), policy.global_policy_digest(after)),
                         (proof["before_global_policy_digest"], proof["after_global_policy_digest"]))
        self.assertEqual(policy.COMPATIBILITY_TOTAL_ADAPTER_V1, proof["adapter_identity"])
        self.assertEqual([1], proof["supported_profile_schema_versions"])
        self.assertEqual(list(policy.PROFILE_FIELDS), proof["fields_preserved"])
        self.assertEqual(proof, gp.compatibility_proof(V1, after), "deterministic")
        self.assertEqual(64, len(gp.compatibility_proof_digest(proof)))

    def test_an_unprovable_case_blocks_automatic_promotion(self) -> None:
        root_policy_hash_stub(self)
        with mock.patch.object(gp, "adapter_v1_problem", return_value="a future Profile schema has no adapter"):
            with self.assertRaises(StopError) as raised:
                gp.compatibility_proof(V1, successor(V1, slots=2))
            self.assertEqual(gp.CODE_COMPATIBILITY_UNPROVEN, raised.exception.code)
            snapshots = two_independent()
            record = gp.request_record(change_request(snapshots))
            clusters = gp.clustering(snapshots)
            after = gp.after_global_policy(V1, record)
            with self.assertRaises(StopError) as raised:
                gp.promotion_packet(record, promotion_packet_id="rpp_" + "1" * 26, global_policy_change_id=CHANGE_ID,
                                    before_global=V1, after_global=after, snapshots=snapshots, clusters=clusters,
                                    eligibility=gp.eligibility(record, snapshots, clusters), proof={})
            self.assertEqual(gp.CODE_COMPATIBILITY_UNPROVEN, raised.exception.code)


class InterpretationTests(unittest.TestCase):
    """R6-2 semantic projection: the total adapter v1 only for a real changed Global projection."""

    def test_the_initial_materialization_keeps_the_exact_derived_interpretation(self) -> None:
        derived = policy.baseline_record((), policy.source_policy_identities())
        materialized = baseline_record(V1, ({"id": "registry", "digest": digest_of("registry")},))
        self.assertEqual(policy.COMPATIBILITY_EXACT_DERIVED_SEMANTIC,
                         gp.compatibility_interpretation(derived, materialized))
        self.assertIsNone(gp.profile_compatibility_problem(profile({SLOTS: 2}), derived, materialized))

    def test_a_text_only_root_edit_keeps_the_exact_derived_interpretation(self) -> None:
        before = baseline_record(V1, ({"id": "registry", "digest": digest_of("registry v1")},))
        after = baseline_record(V1, ({"id": "registry", "digest": digest_of("registry v2")},))
        self.assertNotEqual(before, after)
        self.assertEqual(policy.COMPATIBILITY_EXACT_DERIVED_SEMANTIC, gp.compatibility_interpretation(before, after))

    def test_a_real_global_change_uses_the_total_adapter(self) -> None:
        old, new = baseline_record(V1), baseline_record(successor(V1, slots=3))
        self.assertEqual(policy.COMPATIBILITY_TOTAL_ADAPTER_V1, gp.compatibility_interpretation(old, new))
        self.assertIsNone(gp.projection_change_problem(old, new))
        self.assertIsNone(gp.profile_compatibility_problem(profile({SLOTS: 2, STEPS: 1}), old, new))
        self.assertIsNone(gp.profile_compatibility_problem(None, old, new))
        self.assertIsNotNone(gp.profile_compatibility_problem(
            replace(profile({SLOTS: 2}), loader_semantics_identity="review-v2-other-loader"), old, new))

    def test_a_change_beyond_the_global_settings_is_not_bridged(self) -> None:
        old, new = baseline_record(V1), baseline_record(successor(V1, slots=3))
        for name, changed in (("meta-rules", {**new, "meta_rules_digest": digest_of("other meta-rules")}),
                              ("range", {**new, "surfaces": [{**new["surfaces"][0], "allowed_range": {
                                  "minimum": 1, "maximum": 9}}] + new["surfaces"][1:]})):
            with self.subTest(case=name):
                self.assertIsNotNone(gp.projection_change_problem(old, changed))
                self.assertIsNotNone(gp.profile_compatibility_problem(None, old, changed))

    def test_the_next_run_boundary_adopts_the_new_global_deterministically(self) -> None:
        old, new = baseline_record(V1), baseline_record(successor(V1, slots=3))
        found = profile({STEPS: 2})
        first = gp.adapt_profile_v1(found, policy.bound_global_settings(old), policy.bound_global_settings(new))
        self.assertEqual({SLOTS: 3, STEPS: 2}, first)
        self.assertEqual(first, gp.adapt_profile_v1(found, policy.bound_global_settings(old),
                                                    policy.bound_global_settings(new)))


if __name__ == "__main__":
    unittest.main()
