"""P2 §28 P: the committed R9 basis - the declared base and the R9 selection come from HEAD's committed view."""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import completing_executor, git
from planning_helpers import (
    Crash, PlanningTestCase, Reviewer, blob_at, crash_at, design, plan, plumb_commit, registered, rr, run_ids, snapshot_material,
    state_entries,
)
from workline import roadmap as rm
from workline import start as st
from workline import yamlish
from workline.create import WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.review import planning, publication
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
        with self.assertRaises(ValidationError) as raised:
            self.reviewed_entry(store, created.phase_ids["b"], Reviewer(), design())
        self.assertEqual("review_base_uncommitted", raised.exception.code)
        self.assertEqual((), run_ids(store))

    def test_c_a_ledger_change_of_no_compared_fact_is_the_dirty_overlap(self) -> None:
        ledger = self.store.root / ROADMAP_YAML
        ledger.write_bytes(ledger.read_bytes() + b"\n")
        with self.assertRaises(StopError) as raised:
            self.entry()
        self.assertEqual("dirty_overlap", raised.exception.code)
        self.assertEqual((), run_ids(self.store))

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
        self.assertIn("P6-P9", str(raised.exception))
        result = self.entry()
        found = registered(self.store, result)
        with wrong:
            self.assertIn("CP6 fails", publication.barrier_problem(self.store.root, found.km))


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
