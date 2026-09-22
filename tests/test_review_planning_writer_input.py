"""P2 §28 N: the canonical writer input W - the Candidate, never the caller's mapping order, feeds the writer."""

from __future__ import annotations

from dataclasses import replace
import unittest
from unittest import mock

from planning_helpers import (
    Crash, PlanningTestCase, Reviewer, blob_at, condition, crash_at, design, deterministic_ids, plan, registered, rr,
    run_ids, snapshot_material,
)
from workline import roadmap as rm
from workline.errors import ReconcileRequired, ValidationError
from workline.review import planning, publication, serialize
from workline.review.store import ReviewStore
from workline.store import ProjectStore

RELATED_YAML = ".workline/relations/related.yaml"
CONDITIONAL = "conditional_must_read"


def conditional(cond) -> dict:
    return {"w1": (rr.RelatedSpec(CONDITIONAL, "src/x.py", cond),)}


class _WriterCase(PlanningTestCase):
    def registered_entry(self, name: str, the_design, *, recover: bool = False) -> dict:
        """A review-v1 Phase entry on a fresh, deterministically built Project, and everything W and E are."""
        with deterministic_ids():
            store = self.planning_project(name)
            phase_id = rm.create_roadmap(store, plan()).phase_ids["a"]
            if recover:
                with crash_at(rr, "_use_check"):
                    with self.assertRaises(Crash):
                        self.reviewed_entry(store, phase_id, Reviewer(), the_design)
                self.runtime_gone(store)
            result = self.reviewed_entry(store, phase_id, Reviewer(), the_design)
        return self.facts(store, result)

    def facts(self, store, result) -> dict:
        found = registered(store, result)
        first = self.chain(store, result.review_run_id).generations[0]
        task_input = ReviewStore(store).read_task_input(first.accepted_tasks[0]["task_id"])
        context = task_input.request_envelope["context"]
        expected = rr.expected_projection(store, found.material, context, found.parent)
        (run,) = [r for r in publication.registered_runs(store.root, found.km)
                  if r.candidate_hash == planning.candidate_hash(found.material)]
        return {
            "store": store, "found": found, "context": context,
            "candidate": found.material, "candidate_hash": first.candidate_hash,
            "operation_identity": first.operation_identity, "task_request_digest": task_input.request_digest,
            "w": repr(rr.writer_input(found.material)),  # repr keeps every mapping's key order
            "e": [(e.path, e.status, e.old_mode, e.new_mode, e.old_blob, e.new_blob, e.content) for e in expected.entries],
            "bytes": found.registration_blobs(store),
            "proof": publication.committed_planning_proof(store.root, found.km, run),
        }

    def assert_one_writer_input(self, one: dict, other: dict) -> None:
        for key in ("candidate", "candidate_hash", "operation_identity", "task_request_digest", "w", "e", "bytes"):
            self.assertEqual(one[key], other[key], key)
        self.assertIsNone(one["proof"])
        self.assertIsNone(other["proof"])


class KeyOrderTests(_WriterCase):
    def test_a_condition_key_order_gives_one_candidate_one_w_one_e_and_one_set_of_bytes(self) -> None:
        pattern_first = self.registered_entry("pattern", design(related=conditional(condition("pattern"))))
        kind_first = self.registered_entry("kind", design(related=conditional(condition("kind"))))
        self.assert_one_writer_input(pattern_first, kind_first)
        related = pattern_first["bytes"][RELATED_YAML].decode("utf-8")
        self.assertLess(related.index("kind: path_glob"), related.index("pattern: "), "the canonical order: kind first")

    def test_b_nested_mappings_in_two_insertion_orders_at_two_depths(self) -> None:
        one = {"kind": "path_glob", "pattern": "src/*.py", "scope": {"b": 1, "a": {"y": 2, "x": 3}}}
        two = {"scope": {"a": {"x": 3, "y": 2}, "b": 1}, "pattern": "src/*.py", "kind": "path_glob"}
        first = self.registered_entry("one", design(related=conditional(one)))
        second = self.registered_entry("two", design(related=conditional(two)))
        self.assert_one_writer_input(first, second)
        related = first["bytes"][RELATED_YAML].decode("utf-8")
        for kept in ("x: 3", "y: 2", "b: 1"):
            self.assertIn(kept, related, "every entry kept")

    def test_c_extra_scalar_list_and_mapping_entries(self) -> None:
        one = {"kind": "path_glob", "pattern": "src/*.py", "note": "text", "tags": ["b", "a"], "meta": {"z": 1, "a": 2}}
        two = {"meta": {"a": 2, "z": 1}, "tags": ["b", "a"], "note": "text", "pattern": "src/*.py", "kind": "path_glob"}
        first = self.registered_entry("one", design(related=conditional(one)))
        second = self.registered_entry("two", design(related=conditional(two)))
        self.assert_one_writer_input(first, second)
        related = first["bytes"][RELATED_YAML].decode("utf-8")
        for kept in ("note: text", "z: 1", "a: 2"):
            self.assertIn(kept, related)
        self.assertLess(related.index("- b"), related.index("- a"), "a sequence keeps its order")


class UninterruptedAndRecoveredTests(_WriterCase):
    def test_d_the_same_w_e_and_domain_bytes(self) -> None:
        the_design = design(related=conditional(condition("pattern")))
        uninterrupted = self.registered_entry("straight", the_design)
        recovered = self.registered_entry("recovered", the_design, recover=True)
        for key in ("candidate", "w", "e", "bytes"):
            self.assertEqual(uninterrupted[key], recovered[key], key)
        self.assertIsNone(recovered["proof"])

    def test_e_a_fresh_clone_computes_the_same_w_and_e(self) -> None:
        original = self.registered_entry("original", design(related=conditional(condition("kind"))))
        clone = self.fresh_clone(original["store"].root, "clone")
        material = ReviewStore(clone).read_candidate_snapshot(original["candidate_hash"]).material
        self.assertEqual(original["w"], repr(rr.writer_input(material)))
        expected = rr.expected_projection(clone, material, original["context"], original["found"].parent)
        self.assertEqual(original["e"], [(e.path, e.status, e.old_mode, e.new_mode, e.old_blob, e.new_blob, e.content)
                                         for e in expected.entries])


class CallerObjectTests(_WriterCase):
    def test_f_a_resumed_request_with_another_insertion_order_writes_the_candidates_bytes(self) -> None:
        store = self.planning_project()
        phase_id = rm.create_roadmap(store, plan()).phase_ids["a"]
        first_design = design(related=conditional(condition("kind")))
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.reviewed_entry(store, phase_id, Reviewer(), first_design)
        caller_condition = condition("pattern")
        resumed = self.reviewed_entry(store, phase_id, Reviewer(), design(related=conditional(caller_condition)))
        self.assertEqual(["pattern", "kind"], list(caller_condition), "the caller's object is not mutated")
        found = registered(store, resumed)
        related = blob_at(store, found.kp, RELATED_YAML).decode("utf-8")
        self.assertLess(related.index("kind: path_glob"), related.index("pattern: "), "the Candidate's bytes")
        # W is the Candidate's: its condition mapping is in the Candidate's (canonical) key order, never the caller's
        w = rr.writer_input(snapshot_material(store, resumed.review_run_id))
        (spec,) = [spec for spec in w.stages.normal_specs.values() if spec.related]
        self.assertEqual(["kind", "pattern"], list(spec.related[0].condition))
        self.assertNotEqual(list(caller_condition), list(spec.related[0].condition))
        self.assertEqual(serialize.canonical_data(caller_condition), spec.related[0].condition, "equal as a value")

    def test_g_legacy_keeps_the_callers_order(self) -> None:
        store = self.planning_project()
        phase_id = rm.create_roadmap(store, plan()).phase_ids["a"]
        rm.enter_phase(store, phase_id, design(related=conditional(condition("pattern"))))
        related = (store.root / RELATED_YAML).read_text(encoding="utf-8")
        self.assertLess(related.index("pattern: "), related.index("kind: path_glob"), "byte for byte as at the baseline")


class SequenceOrderTests(_WriterCase):
    def _frozen(self, name: str, the_design) -> tuple[str, str, bytes]:
        with deterministic_ids():
            store = self.planning_project(name)
            phase_id = rm.create_roadmap(store, plan()).phase_ids["a"]
            with crash_at(rr, "_launch_and_settle"):
                with self.assertRaises(Crash):
                    self.reviewed_entry(store, phase_id, Reviewer(), the_design)
        (run_id,) = run_ids(store)
        material = snapshot_material(store, run_id)
        projected = rr.project_on(store, material, self.head(store))
        return planning.candidate_hash(material), repr(rr.writer_input(material)), \
            {e.path.rsplit("/", 1)[-1]: e.content for e in projected.expected.entries}

    def test_h_reordered_related_entries_or_works_are_another_candidate(self) -> None:
        a, b = rr.RelatedSpec("must_read", "docs/a.md"), rr.RelatedSpec("must_read", "docs/b.md")
        variants = {
            "related": (design(related={"w1": (a, b)}), design(related={"w1": (b, a)})),
            "works": (design(works={"w1": "W1", "w2": "W2"}), design(works={"w2": "W2", "w1": "W1"})),
        }
        for described, (one, two) in variants.items():
            with self.subTest(described):
                first = self._frozen(f"{described}-1", one)
                second = self._frozen(f"{described}-2", two)
                self.assertNotEqual(first[0], second[0], "candidate_hash")
                self.assertNotEqual(first[1], second[1], "W")
                self.assertNotEqual(first[2], second[2], "bytes")


class RecordCheckTests(PlanningTestCase):
    def test_i_an_effect_recorded_from_the_callers_mapping_is_refused_before_kp(self) -> None:
        store = self.planning_project()
        phase_id = rm.create_roadmap(store, plan()).phase_ids["a"]
        the_design = design(related=conditional(condition("kind")))
        real = rm._register_phase_expansion

        def callers_order(store_, mutation, stages, **kwargs):
            def reorder(spec):
                return replace(spec, related=tuple(
                    replace(r, condition={"pattern": r.condition["pattern"], "kind": r.condition["kind"]}) if r.condition else r
                    for r in spec.related))
            stages = replace(stages, normal_specs={k: reorder(v) for k, v in stages.normal_specs.items()})
            return real(store_, mutation, stages, **kwargs)

        with mock.patch.object(rm, "_register_phase_expansion", callers_order):
            with self.assertRaises(ReconcileRequired) as raised:
                self.reviewed_entry(store, phase_id, Reviewer(), the_design)
        self.assertEqual("review_registration_projection_mismatch", raised.exception.reason)
        (record,) = [r for r in self.pending(store) if r["invocation"].get("operation") == "phase-entry"]
        self.assertFalse([e for e in record["effects"] if e["stage"] == rr.STAGE_KP], "no Kp")


class RepresentabilityTests(PlanningTestCase):
    def test_j_unrepresentable_conditions_are_refused_and_representable_ones_kept(self) -> None:
        store = self.planning_project()
        phase_id = rm.create_roadmap(store, plan()).phase_ids["a"]
        base = {"kind": "path_glob", "pattern": "src/*.py"}
        refused = {
            "a tuple": {**base, "extra": ("a", "b")},
            "a float": {**base, "extra": 1.5},
            "a non-text key": {**base, 1: "x"},
            "an empty key": {**base, "": "x"},
            "a sequence inside a sequence": {**base, "extra": [["a"]]},
        }
        for described, cond in refused.items():
            with self.subTest(described):
                with self.assertRaises(ValidationError) as raised:
                    self.reviewed_entry(store, phase_id, Reviewer(), design(related=conditional(cond)))
                self.assertEqual("review_candidate_unrepresentable", raised.exception.code)
                self.assertEqual([], self.pending(store), "nothing begun")
        accepted = {**base, "extra": ["a", "b"], "count": 2, "nested": {"k": "v"}}
        result = self.reviewed_entry(store, phase_id, Reviewer(), design(related=conditional(accepted)))
        related = blob_at(store, registered(store, result).kp, RELATED_YAML).decode("utf-8")
        for kept in ("count: 2", "k: v", "- a", "- b"):
            self.assertIn(kept, related)


class OptionalSectionTests(PlanningTestCase):
    """§7.2 / §7.8: scope and out of scope are null for a caller's None or "", else the stripped text; a section
    whose Candidate value is not null is written, so a blank caller value keeps legacy's empty section."""

    CASES = (
        # (scope, out_of_scope) -> the Candidate's (scope, out_of_scope)
        (("   ", ""), ("", None)),
        (("  範囲  ", "   "), ("範囲", "")),
    )

    def body(self, store, roadmap_id: str) -> str:
        text = (store.root / ProjectStore.entity_rel_path("roadmap", roadmap_id)).read_text(encoding="utf-8")
        return text.split("---", 2)[2]

    def test_blank_empty_and_padded_values(self) -> None:
        for index, ((scope, out_of_scope), expected) in enumerate(self.CASES):
            with self.subTest(scope=scope, out_of_scope=out_of_scope):
                the_plan = replace(plan(), scope=scope, out_of_scope=out_of_scope)
                legacy = self.planning_project(f"legacy-{index}")
                legacy_body = self.body(legacy, rm.create_roadmap(legacy, the_plan).roadmap_id)
                store = self.planning_project(f"reviewed-{index}")
                result = self.reviewed_roadmap(store, Reviewer(), the_plan)
                self.assertEqual("registered", result.status)
                roadmap = planning.candidate_content(registered(store, result).material)["roadmap"]
                self.assertEqual(expected, (roadmap["scope"], roadmap["out_of_scope"]))
                self.assertEqual(legacy_body, self.body(store, result.registration.roadmap_id))


if __name__ == "__main__":
    unittest.main()
