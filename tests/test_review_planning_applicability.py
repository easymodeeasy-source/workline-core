"""P2 §28 A: applicability - per-invocation opt-in, no fallback to legacy, markers, the review argument, POSIX."""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import git
from planning_helpers import CANONICAL_RULE, Crash, PlanningTestCase, Reviewer, crash_at, design, plan, rr
from workline import roadmap as rm
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.mutation import MutationController
from workline.review import checkout, fsafe, planning
from workline.review import paths as review_paths
from workline.review.store import ReviewStore
from workline.store import ProjectStore, render_body, render_entity


class LegacyUnchangedTests(PlanningTestCase):
    """``review=None`` is the live path: no Review module is consulted, and it writes what it always wrote."""

    def _forbid_review(self):
        forbidden = [
            mock.patch.object(rr, name, side_effect=AssertionError(f"legacy consulted roadmap_review.{name}"))
            for name in ("require_entry_gate", "preflight_roadmap_request", "preflight_phase_entry_request",
                         "create_roadmap_reviewed", "enter_phase_reviewed")
        ]
        for patcher in forbidden:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_legacy_roadmap_creation_and_phase_entry_are_the_live_path(self) -> None:
        store = self.planning_project()
        self._forbid_review()
        before = self.head(store)
        result = rm.create_roadmap(store, plan())
        self.assertIsInstance(result, rm.RoadmapResult)
        self.assertEqual(["chore(workline): create roadmap R-01", "attributes"], self.subjects(store)[:2])
        self.assertEqual([before], git(store.root, "rev-list", "--parents", "-n", "1", "HEAD").split()[1:])
        # the Roadmap file is exactly the canonical writer's rendering
        roadmap_file = store.root / ProjectStore.entity_rel_path("roadmap", result.roadmap_id)
        expected = render_entity(
            {"id": result.roadmap_id, "display": "R-01", "type": "roadmap"},
            render_body("Planned Roadmap", [("背景", "計画の背景"), ("達成したい状態", "達成したい状態")]),
        )
        self.assertEqual(expected.encode("utf-8"), roadmap_file.read_bytes())
        entry = rm.enter_phase(store, result.phase_ids["a"], design())
        self.assertIsInstance(entry, rm.PhaseEntryResult)
        self.assertEqual("chore(workline): expand phase P-01", self.subjects(store)[0])
        self.assertFalse((store.root / review_paths.REVIEW_DIR).exists(), "legacy writes no Review record")
        self.assertEqual([], self.pending(store))

    def test_legacy_invocation_carries_no_marker_and_records_the_live_stages(self) -> None:
        store = self.planning_project()
        with crash_at(rm, "_finalize"):
            with self.assertRaises(Crash):
                rm.create_roadmap(store, plan())
        (record,) = self.pending(store)
        self.assertEqual({"operation", "name", "request"}, set(record["invocation"]))
        self.assertEqual(["phases", "roadmap"], sorted({effect["stage"] for effect in record["effects"]}))
        self.assertNotIn("mode", str(record["effects"]))
        rm.create_roadmap(store, plan())  # resumes, live
        self.assertEqual([], self.pending(store))

    def test_legacy_works_without_the_review_rule_and_on_posix(self) -> None:
        store = self.new_project()  # no .gitattributes at all
        with mock.patch.object(fsafe, "immutable_create_supported", return_value=False):
            result = rm.create_roadmap(store, plan())
            rm.enter_phase(store, result.phase_ids["a"], design())
        self.assertEqual("chore(workline): expand phase P-01", self.subjects(store)[0])


class GatedTests(PlanningTestCase):
    def test_review_v1_roadmap_creation_is_gated(self) -> None:
        store = self.planning_project()
        reviewer = Reviewer()
        result = self.reviewed_roadmap(store, reviewer)
        self.assertIsInstance(result, rr.ReviewedPlanningResult)
        self.assertEqual(("registered", "roadmap-create"), (result.status, result.operation))
        self.assertEqual(1, len(reviewer.tasks))
        chain = self.chain(store, result.review_run_id)
        self.assertEqual([1, 2, 3], [generation.generation for generation in chain.generations])
        self.assertIsNotNone(result.consumption_id)
        self.assertEqual(result.registration.head, self.head(store))
        self.assertTrue(self.subjects(store)[0].startswith("chore(workline): record review consumption"))

    def test_review_v1_phase_entry_is_gated(self) -> None:
        store = self.planning_project()
        _, phase_id = self.roadmap_and_phase(store)
        reviewer = Reviewer()
        result = self.reviewed_entry(store, phase_id, reviewer)
        self.assertEqual(("registered", "phase-entry"), (result.status, result.operation))
        self.assertIsInstance(result.registration, rm.PhaseEntryResult)
        self.assertEqual("phase-entry-design-v1", reviewer.tasks[0].review_kind)
        self.assertEqual(result.registration.work_ids["w1"], result.registration.entry_work_id)


class NoFallbackTests(PlanningTestCase):
    """Every inability of the gate is a STOP or a terminal review outcome - never an ungated registration."""

    def _nothing_registered(self, store: ProjectStore) -> None:
        self.assertFalse(any((store.root / ".workline" / "roadmaps").glob("*.md")), "a Roadmap was registered")
        self.assertEqual([], self.pending(store))

    def test_platform(self) -> None:
        store = self.planning_project()
        with mock.patch.object(fsafe, "immutable_create_supported", return_value=False):
            with self.assertRaises(StopError) as raised:
                self.reviewed_roadmap(store)
        self.assertEqual("review_create_unsupported", raised.exception.code)
        self._nothing_registered(store)

    def test_checkout_capability(self) -> None:
        store = self.new_project()  # no canonical rule
        with self.assertRaises(StopError) as raised:
            self.reviewed_roadmap(store)
        self.assertEqual("review_checkout_unsafe", raised.exception.code)
        self._nothing_registered(store)
        self.assertFalse((store.root / review_paths.REVIEW_DIR).exists())

    def test_review_namespace(self) -> None:
        store = self.planning_project()
        stray = store.root / review_paths.REVIEW_DIR / "unknown"
        stray.mkdir(parents=True)
        with self.assertRaises(StopError) as raised:
            self.reviewed_roadmap(store)
        self.assertEqual("review_namespace_unreadable", raised.exception.code)
        self._nothing_registered(store)

    def test_git_transform(self) -> None:
        store = self.planning_project(attributes="*.md filter=lfs\n" + CANONICAL_RULE + "\n")
        with self.assertRaises(StopError) as raised:
            self.reviewed_roadmap(store)
        self.assertEqual("review_git_transform", raised.exception.code)
        self._nothing_registered(store)

    def test_context_unavailable(self) -> None:
        store = self.planning_project()
        with mock.patch.object(planning, "_read_authority", side_effect=OSError("gone")):
            with self.assertRaises(StopError) as raised:
                self.reviewed_roadmap(store)
        self.assertEqual("review_context_unavailable", raised.exception.code)
        self._nothing_registered(store)

    def test_reviewer_failure(self) -> None:
        store = self.planning_project()
        with self.assertRaises(StopError) as raised:
            self.reviewed_roadmap(store, Reviewer(raises=RuntimeError("provider down")))
        self.assertEqual("review_reviewer_failed", raised.exception.code)
        self.assertFalse(any((store.root / ".workline" / "roadmaps").glob("*.md")))
        # the planning mutation stays pending after generation 1: the same request resumes it
        self.assertEqual(1, len([r for r in self.pending(store) if r["invocation"].get("operation") == "roadmap-create"]))


class MarkerTests(PlanningTestCase):
    """§5.3: no silent upgrade, no silent downgrade; the record is left untouched."""

    def test_legacy_record_against_review_v1(self) -> None:
        store = self.planning_project()
        with crash_at(rm, "_finalize"):
            with self.assertRaises(Crash):
                rm.create_roadmap(store, plan())
        (record,) = self.pending(store)
        before = (store.mutations / f"{record['mutation_id']}.yaml").read_bytes()
        with self.assertRaises(ReconcileRequired) as raised:
            self.reviewed_roadmap(store)
        self.assertEqual(("reconcile_required", "review_marker_mismatch"), (raised.exception.code, raised.exception.reason))
        self.assertEqual(before, (store.mutations / f"{record['mutation_id']}.yaml").read_bytes())

    def test_review_v1_record_against_legacy(self) -> None:
        store = self.planning_project()
        with crash_at(rr, "_accept"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store)
        (record,) = [r for r in self.pending(store) if r["invocation"].get("operation") == "roadmap-create"]
        before = (store.mutations / f"{record['mutation_id']}.yaml").read_bytes()
        with self.assertRaises(ReconcileRequired) as raised:
            rm.create_roadmap(store, plan())
        self.assertEqual("review_marker_mismatch", raised.exception.reason)
        self.assertEqual(before, (store.mutations / f"{record['mutation_id']}.yaml").read_bytes())

    def test_phase_entry_markers_both_directions(self) -> None:
        store = self.planning_project()
        _, phase_id = self.roadmap_and_phase(store)
        with crash_at(rm, "_finalize"):
            with self.assertRaises(Crash):
                rm.enter_phase(store, phase_id, design())
        with self.assertRaises(ReconcileRequired) as raised:
            self.reviewed_entry(store, phase_id)
        self.assertEqual("review_marker_mismatch", raised.exception.reason)

    def test_unknown_marker_values_fail_closed(self) -> None:
        records = [
            {"invocation": {"operation": "roadmap-create", "name": "n", "request": {}, "review_contract": "review-v9"}},
            {"invocation": {"operation": "roadmap-create", "name": "n", "request": {}, "recovery_of_review_run_id": "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"}},
            {"invocation": {"operation": "roadmap-create", "name": "n", "request": {}, "review_contract": planning.PLANNING_CONTRACT,
                            "publication_contract": planning.PUBLICATION_CONTRACT, "extra": 1}},
        ]
        for record in records:
            with self.subTest(record=record["invocation"]):
                for review_v1 in (True, False):
                    with self.assertRaises(ReconcileRequired) as raised:
                        rm.require_marker_compatible([{"mutation_id": "m", **record}], "roadmap-create", review_v1=review_v1)
                    self.assertEqual("review_marker_mismatch", raised.exception.reason)

    def test_the_frozen_pair_with_and_without_recovery_is_accepted_by_review_v1(self) -> None:
        base = {"operation": "roadmap-create", "name": "n", "request": {}, **planning.invocation_markers()}
        rm.require_marker_compatible([{"mutation_id": "m", "invocation": base}], "roadmap-create", review_v1=True)
        recovered = {**base, "recovery_of_review_run_id": "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"}
        rm.require_marker_compatible([{"mutation_id": "m", "invocation": recovered}], "roadmap-create", review_v1=True)
        with self.assertRaises(ReconcileRequired) as raised:
            rm.require_marker_compatible([{"mutation_id": "m", "invocation": recovered}], "roadmap-create", review_v1=False)
        self.assertEqual("review_marker_mismatch", raised.exception.reason)


class ReviewArgumentTests(PlanningTestCase):
    def test_invalid_review_arguments_write_nothing(self) -> None:
        store = self.planning_project()
        before = self.snapshot_state(store)
        reviewer = Reviewer()
        invalid = [
            "not a review",
            planning.PlanningReview(reviewer, "id", "1", contract="review-v1-planning-v2"),
            planning.PlanningReview("not callable", "id", "1"),  # type: ignore[arg-type]
            planning.PlanningReview(reviewer, " id", "1"),
            planning.PlanningReview(reviewer, "id", ""),
            planning.PlanningReview(reviewer, "id x", "1"),
        ]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError) as raised:
                    rm.create_roadmap(store, plan(), review=value)
                self.assertEqual("review_contract_invalid", raised.exception.code)
                with self.assertRaises(ValidationError):
                    rm.enter_phase(store, "p_01ARZ3NDEKTSV4RRFFQ69G5FAV", design(), review=value)
        self.assertEqual(before, self.snapshot_state(store))
        self.assertEqual([], self.pending(store))


class PosixTests(PlanningTestCase):
    def test_review_v1_on_a_platform_without_immutable_create_stops_before_the_lock(self) -> None:
        store = self.planning_project()
        before = self.snapshot_state(store)
        with mock.patch.object(fsafe, "immutable_create_supported", return_value=False), \
                mock.patch.object(rm, "project_operation", side_effect=AssertionError("lock taken")):
            with self.assertRaises(StopError) as raised:
                self.reviewed_roadmap(store)
        self.assertEqual("review_create_unsupported", raised.exception.code)
        self.assertEqual(before, self.snapshot_state(store))


if __name__ == "__main__":
    unittest.main()
