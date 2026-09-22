"""P2 §28 P: the committed R9 basis - the declared base and the R9 selection come from HEAD's committed view."""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import completing_executor, git
from planning_helpers import (
    Crash, PlanningTestCase, Reviewer, blob_at, crash_at, deterministic_ids, design, plan, plumb_commit, registered, rr, run_ids,
    snapshot_material, state_entries,
)
from workline import roadmap as rm
from workline import start as st
from workline import yamlish
from workline.create import WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, SpecViolation, StopError, ValidationError
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.review import planning, publication, serialize
from workline.review.store import ReviewStore

EVENT_LOG = ".workline/events/events.jsonl"
ROADMAP_YAML = ".workline/relations/roadmap.yaml"


class _BasisCase(PlanningTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()
        created = rm.create_roadmap(self.store, plan())
        self.roadmap_id, self.phase_id = created.roadmap_id, created.phase_ids["a"]
        self.external = create_standalone_work(self.store, WorkSpec("External", "外部の前提が成立する")).work_id

    def the_design(self, **kwargs):
        """w1 waits for the external Work, w2 does not: R9 selects w2 now, and w1 once the external Work completes."""
        return design(requires_completion=((self.external, "w1"),), **kwargs)

    def entry(self, the_design=None, reviewer: Reviewer | None = None):
        return self.reviewed_entry(self.store, self.phase_id, reviewer or Reviewer(), the_design or self.the_design())

    def captured(self, operation) -> bytes:
        """The event-log lines a real operation appends, with the history then put back where it was."""
        before, log = self.head(self.store), (self.store.root / EVENT_LOG).read_bytes()
        operation()
        lines = (self.store.root / EVENT_LOG).read_bytes()[len(log):]
        git(self.store.root, "reset", "-q", "--hard", before)
        self.assertTrue(lines)
        return lines

    def completion_lines(self) -> bytes:
        return self.captured(lambda: st.start(self.store, self.external, "single-work", completing_executor(self.store)))

    def append_uncommitted(self, lines: bytes) -> None:
        path = self.store.root / EVENT_LOG
        path.write_bytes(path.read_bytes() + lines)

    def persons_commit(self, lines: bytes) -> str:
        self.append_uncommitted(lines)
        return self.commit_all(self.store, "a person commits a lifecycle change", EVENT_LOG)

    def canonical_first(self, material: dict) -> str | None:
        first = planning.candidate_content(material)["canonical_first_work"]
        return None if first is None else first["id"]


class EqualBasesTests(_BasisCase):
    def test_a_the_frozen_selection_is_the_selection_of_every_later_reader(self) -> None:
        result = self.entry()
        found = registered(self.store, result)
        frozen = self.canonical_first(found.material)
        self.assertEqual(result.registration.work_ids["w2"], frozen)
        on_parent = rr.r9_selection(rr.project_on(self.store, found.material, found.parent).view, self.phase_id)
        self.assertEqual(frozen, on_parent.work_id, "the pre-Kp proof's selection on P")
        self.assertEqual(frozen, rr.selected_first_work_id(found.material, rr.committed_view(self.store, found.kp)), "P9")
        clone = self.fresh_clone(self.store.root, "clone")
        self.assertEqual(frozen, rr.selected_first_work_id(found.material, rr.committed_view(clone, found.kp)))
        (run,) = [r for r in publication.registered_runs(clone.root, found.km)
                  if r.candidate_hash == planning.candidate_hash(found.material)]
        self.assertIsNone(publication.committed_planning_proof(clone.root, found.km, run), "CP6 in a fresh clone")


class UncommittedTests(_BasisCase):
    def assert_refused_uncommitted(self) -> None:
        before = {k: v for k, v in state_entries(self.store).items() if "/runtime/" not in k}
        reviewer = Reviewer()
        with self.assertRaises(ValidationError) as raised:
            self.entry(reviewer=reviewer)
        self.assertEqual("review_base_uncommitted", raised.exception.code)
        self.assertEqual((), run_ids(self.store), "before any Review record")
        self.assertEqual([], [r for r in self.pending(self.store) if r["invocation"].get("operation") == "phase-entry"],
                         "the planning mutation abandoned")
        self.assertEqual(before, {k: v for k, v in state_entries(self.store).items() if "/runtime/" not in k}, "nothing written")
        self.assertEqual([], reviewer.tasks)

    def test_b_an_uncommitted_resume_of_the_held_phase(self) -> None:
        rm.hold_phase(self.store, self.phase_id)
        self.append_uncommitted(self.captured(lambda: rm.resume_phase(self.store, self.phase_id)))
        self.assert_refused_uncommitted()

    def test_b_an_uncommitted_completion_of_a_predecessor_work(self) -> None:
        self.append_uncommitted(self.completion_lines())
        self.assert_refused_uncommitted()

    def test_the_r9_step_comes_before_the_working_tree_compatibility_check(self) -> None:
        # §14.4 step 2: the R9 selection on HEAD's committed basis, then the working-tree compatibility check. With an
        # uncommitted completion of the predecessor, the working tree lets w1 start and HEAD does not: the explicit
        # entry w1 passes the live startability check (working tree) and is not HEAD's canonical w2 - that refusal first
        self.append_uncommitted(self.completion_lines())
        with self.assertRaises(StopError) as raised:
            self.entry(self.the_design(entry="w1"))
        self.assertEqual("review_entry_not_canonical", raised.exception.code)
        self.assertEqual((), run_ids(self.store), "before any Review record")
        self.assertEqual([], [r for r in self.pending(self.store) if r["invocation"].get("operation") == "phase-entry"],
                         "the planning mutation abandoned")

    def test_c_an_uncommitted_relation_change_of_a_compared_fact(self) -> None:
        store = self.planning_project("gated")
        created = rm.create_roadmap(store, rm.RoadmapPlan(
            "Gated", "背景", "状態", {"a": PhaseSpec("A", "A"), "b": PhaseSpec("B", "B")},
            (PhaseRelationSpec("requires_completion", "a", "b"),),
        ))
        ledger = store.root / ROADMAP_YAML
        data = yamlish.load(ledger.read_text(encoding="utf-8"))
        data["relations"] = [r for r in data["relations"] if r.get("type") != "requires_completion"]
        ledger.write_text(yamlish.dump(data), encoding="utf-8", newline="\n")  # b no longer waits for a, uncommitted
        # the change is the Phase's incoming requires_completion from an unfinished Phase: on HEAD's basis no Work of
        # the design can start (R9 none), in the working tree one could - a relation that changes the R9 selection
        phase_a, phase_b = created.phase_ids["a"], created.phase_ids["b"]
        committed = rr.committed_view(store, self.head(store))
        working = rr.ProjectView.load(store)
        into_b = [r.id for r in committed.roadmap_relations if r.type == "requires_completion" and r.to == phase_b]
        self.assertEqual(1, len(into_b))
        self.assertNotIn(into_b[0], [r.id for r in working.roadmap_relations])
        self.assertNotIn(committed.phase_state(phase_a), ("complete", "cancelled", "plan_excluded"), "a is unfinished")
        with self.assertRaises(ValidationError) as raised:
            self.reviewed_entry(store, phase_b, Reviewer(), design())
        self.assertEqual("review_base_uncommitted", raised.exception.code)
        self.assertEqual((), run_ids(store))

    def test_c_a_ledger_change_of_no_compared_fact_is_the_dirty_overlap(self) -> None:
        ledger = self.store.root / ROADMAP_YAML
        ledger.write_bytes(ledger.read_bytes() + b"\n")
        with self.assertRaises(StopError) as raised:
            self.entry()
        self.assertEqual("dirty_overlap", raised.exception.code)
        self.assertEqual((), run_ids(self.store))

    def test_d_the_whole_candidate_is_the_one_head_gives(self) -> None:
        materials = []
        for name, irrelevant in (("clean", False), ("irrelevant", True)):
            with deterministic_ids():
                store = self.planning_project(name)
                phase_id = rm.create_roadmap(store, plan()).phase_ids["a"]
                other = rm.create_roadmap(store, plan("Other Roadmap")).roadmap_id
                before, log = self.head(store), (store.root / EVENT_LOG).read_bytes()
                rm.hold_roadmap(store, other)
                lines = (store.root / EVENT_LOG).read_bytes()[len(log):]
                git(store.root, "reset", "-q", "--hard", before)
                if irrelevant:  # another Roadmap's event and an unrelated file, uncommitted
                    (store.root / EVENT_LOG).write_bytes(log + lines)
                    (store.root / "notes.txt").write_text("unrelated\n", encoding="utf-8")
                result = self.reviewed_entry(store, phase_id, Reviewer(), design())
            self.assertEqual("registered", result.status)
            materials.append(snapshot_material(store, result.review_run_id))
        self.assertEqual(serialize.canonical_data(materials[0]), serialize.canonical_data(materials[1]))
        self.assertEqual(planning.candidate_hash(materials[0]), planning.candidate_hash(materials[1]))

    def test_d_an_irrelevant_uncommitted_change_is_not_refused(self) -> None:
        other = rm.create_roadmap(self.store, plan("Other Roadmap")).roadmap_id
        self.append_uncommitted(self.captured(lambda: rm.hold_roadmap(self.store, other)))
        (self.store.root / "notes.txt").write_text("unrelated\n", encoding="utf-8")
        result = self.entry()
        self.assertEqual("registered", result.status)
        material = snapshot_material(self.store, result.review_run_id)
        on_head = rr.declared_base(rr.committed_view(self.store, registered(self.store, result).parent),
                                   planning.candidate_content(material))
        self.assertEqual(material["declared_base"], planning.serialize.canonical_data(on_head))


class DeclaredBaseFirstTests(_BasisCase):
    """E: a committed predecessor completion is a declared-base change, never an R9 or Candidate mismatch."""

    def test_e_stale_before_a_receipt(self) -> None:
        lines = self.completion_lines()
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.entry()
        self.persons_commit(lines)
        result = self.entry()
        self.assertEqual(("stale", planning.STALE_DECLARED_BASE, None), (result.status, result.detail, result.receipt_id))

    def test_e_stale_before_a_receipt_after_generation_2(self) -> None:
        lines = self.completion_lines()
        with crash_at(rr, "_seal"):
            with self.assertRaises(Crash):
                self.entry()
        self.persons_commit(lines)
        result = self.entry()
        self.assertEqual(("stale", planning.STALE_DECLARED_BASE, None), (result.status, result.detail, result.receipt_id))
        self.assertEqual(2, self.chain(self.store, result.review_run_id).latest.generation)

    def test_e_generation_4_at_the_use_check(self) -> None:
        lines = self.completion_lines()
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.entry()
        self.persons_commit(lines)
        result = self.entry()
        self.assertEqual(("stale", planning.STALE_DECLARED_BASE), (result.status, result.detail))
        self.assertEqual(4, self.chain(self.store, result.review_run_id).latest.generation)

    def test_e_the_pre_kp_proof(self) -> None:
        lines = self.completion_lines()
        with crash_at(rm, "register_works", when=lambda n, mutation, stage, specs, relations: stage == "integration"):
            with self.assertRaises(Crash):
                self.entry()
        self.persons_commit(lines)
        with self.assertRaises(ReconcileRequired) as raised:
            self.entry()
        self.assertEqual("review_registration_currency_changed", raised.exception.reason)

    def test_e_p12_in_c2_kp(self) -> None:
        lines = self.completion_lines()
        with crash_at(rm, "register_works", when=lambda n, mutation, stage, specs, relations: stage == "integration"):
            with self.assertRaises(Crash):
                self.entry()
        self.persons_commit(lines)
        with mock.patch.object(rr, "_pre_kp_proof", lambda *args, **kwargs: None):
            with self.assertRaises(ReconcileRequired) as raised:
                self.entry()
        self.assertEqual("review_persisted_proof_failed", raised.exception.reason)
        self.assertIn("C-2(Kp) P12", str(raised.exception))

    def test_e_cp7_in_the_committed_planning_proof(self) -> None:
        lines = self.completion_lines()
        result = self.entry()
        found = registered(self.store, result)
        parent = plumb_commit(self.store, found.parent, {EVENT_LOG: blob_at(self.store, found.parent, EVENT_LOG) + lines})
        kp = plumb_commit(self.store, parent, found.registration_blobs(self.store))
        km = plumb_commit(self.store, kp, {found.consumption_path: blob_at(self.store, found.km, found.consumption_path)})
        (run,) = [r for r in publication.registered_runs(self.store.root, km)
                  if r.candidate_hash == planning.candidate_hash(found.material)]
        failed = publication.committed_planning_proof(self.store.root, km, run)
        self.assertEqual("CP7", failed[0], failed)


class PhaseHeldTests(_BasisCase):
    """P-E's other example, "the Phase held", for the kind that has an R9 selection: a review-v1 Phase entry. No
    Workline operation can hold the Phase while its entry is pending (the scopes overlap: the live reconcile), so the
    hold arrives as a person's commit; the frozen entry order then runs the live Phase-state check first on every call
    (§5.6 step 2), before any currency evaluation, and the planning mutation stays pending. Once the Phase is resumed
    the Run is current again and the flow goes on."""

    def setUp(self) -> None:
        super().setUp()
        before, log = self.head(self.store), (self.store.root / EVENT_LOG).read_bytes()
        rm.hold_phase(self.store, self.phase_id)
        held = (self.store.root / EVENT_LOG).read_bytes()
        rm.resume_phase(self.store, self.phase_id)
        resumed = (self.store.root / EVENT_LOG).read_bytes()
        git(self.store.root, "reset", "-q", "--hard", before)
        self.hold_lines, self.resume_lines = held[len(log):], resumed[len(held):]

    def held_then_refused(self) -> None:
        (before,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "phase-entry"]
        with self.assertRaises(ReconcileRequired) as overlap:
            rm.hold_phase(self.store, self.phase_id)
        self.assertIsNone(overlap.exception.reason, "the live scope overlap: no Workline hold while the entry is pending")
        self.persons_commit(self.hold_lines)
        with self.assertRaises(SpecViolation) as raised:
            self.entry()
        self.assertIn("is held", str(raised.exception))
        (after,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "phase-entry"]
        self.assertEqual(before, after, "the planning mutation stays pending, untouched")
        self.persons_commit(self.resume_lines)

    def assert_registered(self) -> None:
        result = self.entry()
        self.assertEqual("registered", result.status)
        self.assertEqual(3, self.chain(self.store, result.review_run_id).latest.generation)

    def test_after_generation_1(self) -> None:
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.entry()
        self.held_then_refused()
        self.assert_registered()

    def test_after_generation_2(self) -> None:
        with crash_at(rr, "_seal"):
            with self.assertRaises(Crash):
                self.entry()
        self.held_then_refused()
        self.assert_registered()

    def test_after_generation_3(self) -> None:
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.entry()
        self.held_then_refused()
        self.assert_registered()

    def test_after_the_registration_began(self) -> None:
        with crash_at(rm, "register_works", when=lambda n, mutation, stage, specs, relations: stage == "integration"):
            with self.assertRaises(Crash):
                self.entry()
        self.held_then_refused()
        self.assert_registered()  # P descends from use_check_head through event-log commits, the base current again


class MismatchWithAnEqualBaseTests(_BasisCase):
    """F: the declared base equal, the R9 reconstruction made to differ by a patched selection."""

    def other_first(self):
        real = rr.first_work_of

        def other(selection, content, entry_key):
            found = real(selection, content, entry_key)
            others = [w for w in content["works"] if found is None or w["id"] != found["id"]]
            return {"key": others[0]["key"], "id": others[0]["id"]}

        return mock.patch.object(rr, "first_work_of", other)

    def test_f_the_use_check(self) -> None:
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.entry()
        with self.other_first():
            with self.assertRaises(ReconcileRequired) as raised:
                self.entry()
        self.assertEqual("review_candidate_mismatch", raised.exception.reason)

    def test_f_the_pre_kp_proof(self) -> None:
        with crash_at(rm, "register_works", when=lambda n, mutation, stage, specs, relations: stage == "integration"):
            with self.assertRaises(Crash):
                self.entry()
        with self.other_first():
            with self.assertRaises(ReconcileRequired) as raised:
                self.entry()
        self.assertEqual("review_candidate_mismatch", raised.exception.reason)

    def test_f_discovery(self) -> None:
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.entry()
        self.runtime_gone(self.store)
        with self.other_first():
            with self.assertRaises(ReconcileRequired) as raised:
                self.entry()
        self.assertEqual("review_recovery_incomplete", raised.exception.reason)

    def test_f_p8_p9_in_c2_kp_and_cp6_at_the_barrier(self) -> None:
        with crash_at(rr, "_c2_kp"):
            with self.assertRaises(Crash):
                self.entry()
        wrong = mock.patch.object(rr, "selected_first_work_id", lambda material, view: "w_01ARZ3NDEKTSV4RRFFQ69G5FAV")
        with wrong:
            with self.assertRaises(ReconcileRequired) as raised:
                self.entry()
        self.assertEqual("review_persisted_proof_failed", raised.exception.reason)
        self.assertIn("C-2(Kp) P9 fails", str(raised.exception))
        result = self.entry()
        found = registered(self.store, result)
        with wrong:
            self.assertIn("CP6 fails", publication.barrier_problem(self.store.root, found.km))

    def test_f_p8_when_the_projection_identity_carries_another_selection(self) -> None:
        with crash_at(rr, "_c2_kp"):
            with self.assertRaises(Crash):
                self.entry()
        real = rr.semantic_projection

        def other_selection(material, view, selection_view=None):
            found = real(material, view, selection_view)
            content = dict(found.content)
            content["canonical_first_work"] = {"key": "other", "id": "w_01ARZ3NDEKTSV4RRFFQ69G5FAV"}
            return type(found)(found.kind, found.semantics_version, content)

        with mock.patch.object(rr, "semantic_projection", other_selection):
            with self.assertRaises(ReconcileRequired) as raised:
                self.entry()
        self.assertEqual("review_persisted_proof_failed", raised.exception.reason)
        self.assertIn("C-2(Kp) P8 fails", str(raised.exception))
        self.assertFalse(ReviewStore(self.store).consumption_ids())


class RoundTripBasisTests(_BasisCase):
    def test_an_uncommitted_lifecycle_event_after_the_freeze_does_not_change_the_round_trip(self) -> None:
        lines = self.completion_lines()
        with crash_at(rm, "register_works", when=lambda n, mutation, stage, specs, relations: stage == "integration"):
            with self.assertRaises(Crash):
                self.entry()
        self.append_uncommitted(lines)  # read from the working tree, R9 would now select w1
        result = self.entry()
        self.assertEqual("registered", result.status)
        self.assertEqual(result.registration.work_ids["w2"], result.registration.entry_work_id)


if __name__ == "__main__":
    unittest.main()
