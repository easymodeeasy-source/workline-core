"""P2 §28 A: applicability - per-invocation opt-in, no fallback to legacy, markers, the review argument, POSIX."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from helpers import git
from planning_helpers import (
    CANONICAL_RULE, Crash, PlanningTestCase, Reviewer, crash_at, design, plan, rr, state_entries,
)
from workline import roadmap as rm
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.mutation import MutationController
from workline.review import checkout, fsafe, planning, serialize
from workline.review import paths as review_paths
from workline.review.store import ReviewStore
from workline.store import ProjectStore, render_body, render_entity


HIGH_SURROGATE = "\ud800"
LOW_SURROGATE = "\udfff"

#: Reviewer identity / version pairs that pass the single-line shape rule and that the canonical Review form
#: cannot carry (BL-057). Before the rule of the entry gate each of these was first encoded in generation-1
#: acceptance, after the lock, the planning mutation and its reservations.
UNREPRESENTABLE_REVIEWERS = {
    "the identity is a lone high surrogate": (HIGH_SURROGATE, "1"),
    "the identity is a lone low surrogate": (LOW_SURROGATE, "1"),
    "the version is a lone high surrogate": ("id", HIGH_SURROGATE),
    "the version is a lone low surrogate": ("id", LOW_SURROGATE),
    "a surrogate inside the identity": (f"reviewer-{HIGH_SURROGATE}-x", "1"),
    "a surrogate inside the version": ("id", f"v-{LOW_SURROGATE}-1"),
}


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


class LegacyBaselineTests(PlanningTestCase):
    """§28 A and N item G: the legacy path byte for byte as at the implementation baseline.

    ``p2_legacy_scenario.run_scenario`` records a legacy Roadmap creation and Phase entry - the pending records
    (invocation, stages, every recorded effect), every commit (subject, parents, every file's bytes), every push, and
    the results - with deterministic IDs; ``p2_legacy_baseline.json`` is that record made on ``de3681c``.
    """

    def test_a_legacy_roadmap_creation_and_phase_entry_are_the_baselines_byte_for_byte(self) -> None:
        import json

        from p2_legacy_scenario import run_scenario

        golden = json.loads((Path(__file__).parent / "p2_legacy_baseline.json").read_text(encoding="utf-8"))
        self.assertEqual("de3681c94d9a0c8bf1ac8263513b5793c495a02e", golden["baseline"])
        forbidden = [mock.patch.object(serialize, "canonical_data", side_effect=AssertionError("canonicalized")),
                     mock.patch.object(rr, "writer_input", side_effect=AssertionError("W computed"))]
        forbidden += [mock.patch.object(rr, name, side_effect=AssertionError(f"roadmap_review.{name}"))
                      for name in ("require_entry_gate", "preflight_roadmap_request", "preflight_phase_entry_request",
                                   "create_roadmap_reviewed", "enter_phase_reviewed")]
        for patcher in forbidden:
            patcher.start()
            self.addCleanup(patcher.stop)
        record = run_scenario(self)
        for key in golden["record"]:
            with self.subTest(key):
                self.assertEqual(golden["record"][key], record[key])
        self.assertEqual(set(golden["record"]), set(record))
        related = record["entry:commit"]["files"][".workline/relations/related.yaml"][1]
        self.assertLess(related.index("pattern: "), related.index("kind: path_glob"), "the caller's key order")
        self.assertEqual(record["create:commit"]["head"], record["create:commit"]["published"], "pushed")
        self.assertEqual(record["entry:commit"]["head"], record["entry:commit"]["published"], "pushed")


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

        def pending_entry() -> Path:
            (record,) = [r for r in self.pending(store) if r["invocation"].get("operation") == "phase-entry"]
            return store.mutations / f"{record['mutation_id']}.yaml"

        # a legacy record against a review-v1 invocation
        with crash_at(rm, "_finalize"):
            with self.assertRaises(Crash):
                rm.enter_phase(store, phase_id, design())
        path = pending_entry()
        before = path.read_bytes()
        with self.assertRaises(ReconcileRequired) as raised:
            self.reviewed_entry(store, phase_id)
        self.assertEqual(("reconcile_required", "review_marker_mismatch"), (raised.exception.code, raised.exception.reason))
        self.assertEqual(before, path.read_bytes(), "no silent upgrade; the record untouched")
        rm.enter_phase(store, phase_id, design())  # the legacy entry resumes and completes
        # a review-v1 record against a legacy invocation
        other_phase = rm.create_roadmap(store, plan("Second Roadmap")).phase_ids["a"]
        with crash_at(rr, "_accept"):
            with self.assertRaises(Crash):
                self.reviewed_entry(store, other_phase)
        path = pending_entry()
        before = path.read_bytes()
        with self.assertRaises(ReconcileRequired) as raised:
            rm.enter_phase(store, other_phase, design())
        self.assertEqual(("reconcile_required", "review_marker_mismatch"), (raised.exception.code, raised.exception.reason))
        self.assertEqual(before, path.read_bytes(), "no silent downgrade; the record untouched")

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
        _, phase_id = self.roadmap_and_phase(store)
        before = self.snapshot_state(store)
        reviewer = Reviewer()
        invalid = [
            "not a review",
            planning.PlanningReview(reviewer, "id", "1", contract="review-v1-planning-v2"),
            planning.PlanningReview("not callable", "id", "1"),  # type: ignore[arg-type]
            planning.PlanningReview(reviewer, " id", "1"),
            planning.PlanningReview(reviewer, "id", ""),
            planning.PlanningReview(reviewer, "id x", "1"),
            *(planning.PlanningReview(reviewer, identity, version)
              for identity, version in UNREPRESENTABLE_REVIEWERS.values()),
        ]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError) as raised:
                    rm.create_roadmap(store, plan(), review=value)
                self.assertEqual("review_contract_invalid", raised.exception.code)
                with self.assertRaises(ValidationError) as entry:
                    rm.enter_phase(store, phase_id, design(), review=value)
                self.assertEqual("review_contract_invalid", entry.exception.code)
        self.assertEqual(before, self.snapshot_state(store))
        self.assertEqual([], self.pending(store))


class ReviewerTextTests(PlanningTestCase):
    """BL-057: the reviewer identity and version are text a Review record carries, proven at the entry gate.

    Generation 1 makes both durable in the TaskInput and in the accepted
    descriptor, so a value the canonical form cannot carry has to be refused
    before the lock; the alternative, measured at the baseline, is a raw
    ``UnicodeEncodeError`` from :func:`planning.accepted_descriptor` with the
    planning mutation and its reservations already recorded.
    """

    def _call(self, store, phase_id: str, entry: str, reviewer: Reviewer):
        if entry == "roadmap creation":
            return self.reviewed_roadmap(store, reviewer)
        return self.reviewed_entry(store, phase_id, reviewer)

    def test_unrepresentable_reviewer_text_is_refused_before_the_lock(self) -> None:
        store = self.planning_project()
        _, phase_id = self.roadmap_and_phase(store)
        before, head = state_entries(store), self.head(store)
        for described, (identity, version) in UNREPRESENTABLE_REVIEWERS.items():
            for entry in ("roadmap creation", "Phase entry"):
                with self.subTest(described=described, entry=entry):
                    reviewer = Reviewer(identity=identity, version=version)
                    with mock.patch.object(rm, "project_operation", side_effect=AssertionError("lock taken")):
                        with self.assertRaises(ValidationError) as raised:
                            self._call(store, phase_id, entry, reviewer)
                    self.assertEqual("review_contract_invalid", raised.exception.code)
                    self.assertIn("the canonical Review form cannot carry", str(raised.exception))
                    self.assertEqual([], reviewer.tasks, "the reviewer is not called")
        self.assertEqual(before, state_entries(store),
                         "no planning mutation, reservation, Review record, domain effect or runtime file")
        self.assertEqual([], self.pending(store))
        self.assertEqual(head, self.head(store))
        self.assertFalse((store.root / ".workline" / "review").exists())
        self.assertEqual([], sorted(store.tmp.rglob("*")) if store.tmp.exists() else [])

    def test_representable_unicode_reviewer_text_still_registers(self) -> None:
        cases = {
            "japanese": ("\u30ec\u30d3\u30e5\u30a2\u30fc", "\u7b2c1\u7248"),
            "accented": ("revi\u00e9wer", "v1.2-rc.3"),
            "astral": ("reviewer " + chr(0x1F600), "v" + chr(0x20000)),
            "spaced": ("Review Bot A (build #7)", "1.2.3+build.7"),
        }
        for name, (identity, version) in cases.items():
            with self.subTest(name=name):
                store = self.planning_project(name)
                result = self.reviewed_roadmap(store, Reviewer(identity=identity, version=version))
                self.assertEqual("registered", result.status)
                if name == "japanese":
                    entry = self.reviewed_entry(store, result.registration.phase_ids["a"],
                                                Reviewer(identity=identity, version=version))
                    self.assertEqual("registered", entry.status)
                self.assertEqual([], self.pending(store))

    def test_the_rule_is_the_canonical_bytes_and_the_round_trip_together(self) -> None:
        """The round trip never encodes, so on its own it accepts text no Review file could hold."""
        for described, value in {
            "a lone high surrogate": HIGH_SURROGATE,
            "a lone low surrogate": LOW_SURROGATE,
            "a surrogate inside ordinary text": f"reviewer-{HIGH_SURROGATE}-x",
        }.items():
            with self.subTest(described=described):
                holder = {"reviewer_text": value}
                self.assertTrue(serialize.canonical_roundtrips(holder), "the round trip alone accepts it")
                with self.assertRaises(UnicodeEncodeError):
                    serialize.canonical_bytes(holder)
                self.assertTrue(planning._single_line_text(value), "the shape rule alone accepts it")
                self.assertFalse(planning._persistable_reviewer_text(value), "only the two together refuse it")

    def test_the_shape_rule_and_everything_it_already_decided_are_unchanged(self) -> None:
        refused = {
            "empty": "", "whitespace only": " ", "a leading space": " id", "a trailing space": "id ",
            "LF": "a\nb", "CR": "a\rb", "CRLF": "a\r\nb", "VT": "a\vb", "FF": "a\fb",
            "FS": "a\x1cb", "GS": "a\x1db", "RS": "a\x1eb", "NEL": "a\x85b",
            "LINE SEPARATOR": "a\u2028b", "PARAGRAPH SEPARATOR": "a\u2029b",
        }
        for described, value in refused.items():
            with self.subTest(refused=described):
                self.assertFalse(planning._persistable_reviewer_text(value))
                with self.assertRaises(ValidationError) as raised:
                    planning.validate_planning_review(planning.PlanningReview(Reviewer(), value, "1"))
                self.assertEqual("review_contract_invalid", raised.exception.code)
                self.assertIn("non-empty single-line text without surrounding whitespace", str(raised.exception),
                              "a shape refusal keeps its own detail")
        accepted = {
            "ASCII": "reviewer-a",
            "internal spaces": "Review Bot A",
            "punctuation": "r@e.com/v1 (b#7) [x] {y} <z> |t| ~u",
            "a backslash": "a\\b",
            "a tab": "rev\ter",
            "a no-break space": "rev\u00a0er",
            "a byte order mark": "a\ufeffb",
            "a noncharacter": "a\uffffb",
            "a private use character": "a\ue000b",
            "combining marks": "e\u0301 reviewer",
            "right to left": "\u05d1\u05d5\u05d3",
            "a joined emoji": chr(0x1F468) + "\u200d" + chr(0x1F4BB),
            "text a reader could take for a number": "1",
            "text a reader could take for a boolean": "true",
            "text a reader could take for null": "null",
            "text that looks like YAML": "- reviewer: {a: b}",
            "long text": "r" * 5000,
        }
        for described, value in accepted.items():
            with self.subTest(accepted=described):
                self.assertTrue(planning._persistable_reviewer_text(value))
                planning.validate_planning_review(planning.PlanningReview(Reviewer(), value, value))

    def test_a_pending_planning_mutation_survives_an_unrepresentable_retry(self) -> None:
        """The refusal is before the lock, so a planning mutation the Project already holds is left as it is."""
        for operation, entry in (("roadmap-create", "roadmap creation"), ("phase-entry", "Phase entry")):
            with self.subTest(operation=operation):
                store = self.planning_project(operation)
                phase_id = "" if entry == "roadmap creation" else self.roadmap_and_phase(store)[1]
                with crash_at(rr, "_accept"):
                    with self.assertRaises(Crash):
                        self._call(store, phase_id, entry, Reviewer())
                (record,) = [r for r in self.pending(store) if r["invocation"].get("operation") == operation]
                path = store.mutations / f"{record['mutation_id']}.yaml"
                before_record, before_state = path.read_bytes(), state_entries(store)

                reviewer = Reviewer(identity=HIGH_SURROGATE)
                with mock.patch.object(rm, "project_operation", side_effect=AssertionError("lock taken")):
                    with self.assertRaises(ValidationError) as raised:
                        self._call(store, phase_id, entry, reviewer)
                self.assertEqual("review_contract_invalid", raised.exception.code)
                self.assertEqual(before_record, path.read_bytes(), "the pending planning mutation is untouched")
                self.assertEqual(before_state, state_entries(store))
                self.assertEqual([], reviewer.tasks)

                resumed = self._call(store, phase_id, entry, Reviewer())
                self.assertEqual("registered", resumed.status)
                self.assertEqual(record["mutation_id"], resumed.mutation_id, "the same planning mutation resumed")
                self.assertEqual([], self.pending(store))

    def test_the_rule_is_never_reached_on_the_legacy_path(self) -> None:
        store = self.planning_project()
        with mock.patch.object(planning, "_persistable_reviewer_text",
                               side_effect=AssertionError("legacy consulted the reviewer-text rule")):
            roadmap = rm.create_roadmap(store, plan())
            rm.enter_phase(store, roadmap.phase_ids["a"], design())
        self.assertEqual([], self.pending(store))

    def test_a_report_keeps_its_own_representability_boundary(self) -> None:
        """BL-057 moves nothing on the report path: a finding's shape rule is still ``_single_line_text``."""
        descriptor = {"task_id": "rtk_1", "reviewer_identity": "id", "reviewer_version": "1"}
        for described, finding in {
            "a finding code": planning.PlanningReviewFinding("LOW", HIGH_SURROGATE, "m"),
            "a finding message": planning.PlanningReviewFinding("LOW", "c", f"m {HIGH_SURROGATE}"),
        }.items():
            with self.subTest(described=described):
                report = planning.PlanningReviewReport("rtk_1", "id", "1", "completed", (finding,))
                with self.assertRaises(StopError) as raised:
                    planning.report_record(report, descriptor)
                self.assertEqual("review_report_invalid", raised.exception.code)
                self.assertIn("cannot be recorded canonically", str(raised.exception),
                              "refused where the report is canonicalized, not by the shape rule")
        self.assertTrue(planning._single_line_text(HIGH_SURROGATE), "the shared shape rule itself is unchanged")


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
