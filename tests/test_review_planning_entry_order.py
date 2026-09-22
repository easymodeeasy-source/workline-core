"""P2 §28 R: the review-v1 Phase-entry order - live admissibility first, then canonical recovery discovery."""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import completing_executor, git
from planning_helpers import Crash, PlanningTestCase, Reviewer, crash_at, design, plan, rr, run_ids
from workline import mutation as mutation_module
from workline import roadmap as rm
from workline import start as st
from workline.create import WorkSpec, create_standalone_work
from workline.errors import ReconcileRequired, SpecViolation, StopError
from workline.mutation import MutationController
from workline.review import planning, recovery

EVENT_LOG = ".workline/events/events.jsonl"


def _generation_commit(number: int):
    return lambda n, store, payload, paths: f"record review generation {number} of" in payload.get("message", "")


class _EntryCase(PlanningTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()
        self.phase_id = rm.create_roadmap(self.store, plan()).phase_ids["a"]

    def entry(self, the_design=None, reviewer: Reviewer | None = None):
        return self.reviewed_entry(self.store, self.phase_id, reviewer or Reviewer(), the_design or design())

    def planning_records(self) -> list[dict]:
        return [r for r in self.pending(self.store) if r["invocation"].get("operation") == planning.OPERATION_PHASE_ENTRY]

    def no_discovery(self):
        return mock.patch.object(recovery, "discover", side_effect=AssertionError("discovery ran"))


class AlreadyExpandedTests(_EntryCase):
    def test_a_a_consumed_run_is_not_read_the_live_refusal_comes_first(self) -> None:
        self.assertEqual("registered", self.entry().status)
        before = run_ids(self.store)
        with self.no_discovery():
            with self.assertRaises(StopError) as raised:
                self.entry()
        self.assertEqual("phase_already_expanded", raised.exception.code)
        self.assertEqual([], self.planning_records(), "no recovery planning mutation")
        self.assertEqual(before, run_ids(self.store))


class DiscoveryForAnAdmissibleEntryTests(_EntryCase):
    def test_b_an_incomplete_run(self) -> None:
        with crash_at(mutation_module, "_make_planning_commit", when=_generation_commit(1)):
            with self.assertRaises(Crash):
                self.entry()
        self.runtime_gone(self.store)
        with self.assertRaises(ReconcileRequired) as raised:
            self.entry()
        self.assertEqual("review_recovery_incomplete", raised.exception.reason)
        self.assertEqual([], self.planning_records())

    def test_c_two_recoverable_runs(self) -> None:
        base = self.head(self.store)
        git(self.store.root, "checkout", "-q", "-b", "first")
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.entry()
        self.runtime_gone(self.store)
        git(self.store.root, "checkout", "-q", "-b", "second", base)
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.entry()
        self.runtime_gone(self.store)
        git(self.store.root, "merge", "-q", "--no-edit", "first")
        with self.assertRaises(ReconcileRequired) as raised:
            self.entry()
        self.assertEqual("review_recovery_ambiguous", raised.exception.reason)
        self.assertEqual([], self.planning_records())


class OwnAppliedStagesTests(_EntryCase):
    def crash_between_stages(self, the_design) -> dict:
        with crash_at(rm, "register_works", when=lambda n, mutation, stage, specs, relations: stage == "integration"):
            with self.assertRaises(Crash):
                self.entry(the_design)
        (record,) = self.planning_records()
        self.assertTrue([e for e in record["effects"] if e["stage"] == "works" and e["applied"]])
        return record

    def test_d_own_applied_stages_are_resumed_never_already_expanded(self) -> None:
        record = self.crash_between_stages(design())
        result = self.entry(design())
        self.assertEqual(("registered", record["mutation_id"]), (result.status, result.mutation_id))

    def test_d_the_unique_entry_check_is_skipped_for_it(self) -> None:
        external = create_standalone_work(self.store, WorkSpec("External", "外部の前提が成立する")).work_id
        before, log = self.head(self.store), (self.store.root / EVENT_LOG).read_bytes()
        st.start(self.store, external, "single-work", completing_executor(self.store))  # the lines it appends, kept
        completion = (self.store.root / EVENT_LOG).read_bytes()[len(log):]
        git(self.store.root, "reset", "-q", "--hard", before)
        the_design = design(planned_next=(), requires_completion=((external, "w1"),))  # only w2 startable: unique
        self.crash_between_stages(the_design)
        path = self.store.root / EVENT_LOG
        path.write_bytes(path.read_bytes() + completion)
        self.commit_all(self.store, "a person commits the predecessor's completion", EVENT_LOG)
        # with w1 and w2 both startable and unordered the live unique-entry check would refuse a new expansion
        # (ambiguous_startable_candidates); the interrupted one is carried on, and the pre-Kp proof decides
        with self.assertRaises(ReconcileRequired) as raised:
            self.entry(the_design)
        self.assertEqual("review_registration_currency_changed", raised.exception.reason)

    def test_d_the_explicit_entrys_startability_is_still_checked(self) -> None:
        external = create_standalone_work(self.store, WorkSpec("External", "外部の前提が成立する")).work_id
        before = self.head(self.store)
        st.start(self.store, external, "single-work", completing_executor(self.store))
        completed = self.head(self.store)
        the_design = design(requires_completion=((external, "w1"),), entry="w1")
        record = self.crash_between_stages(the_design)
        git(self.store.root, "revert", "--no-edit", f"{before}..{completed}")  # a person undoes the completion
        with self.assertRaises(SpecViolation):
            self.entry(the_design)
        (still,) = self.planning_records()
        self.assertEqual(record, still, "the pending record is untouched")


class RoadmapCreationTests(PlanningTestCase):
    def test_e_roadmap_creation_has_no_remaining_live_check_and_discovery_runs(self) -> None:
        store = self.planning_project()
        calls: list[str] = []
        real = recovery.discover

        def spy(*args, **kwargs):
            calls.append("discover")
            return real(*args, **kwargs)

        with mock.patch.object(recovery, "discover", spy):
            self.reviewed_roadmap(store)
        self.assertEqual(["discover"], calls)


class EarlierRefusalsTests(_EntryCase):
    """A different request, a pending legacy record and a marker mismatch are refused at step 5, ahead of step 6."""

    def test_a_different_pending_request_for_the_slot(self) -> None:
        with crash_at(rm, "register_works", when=lambda n, mutation, stage, specs, relations: stage == "integration"):
            with self.assertRaises(Crash):
                self.entry(design())
        (record,) = self.planning_records()
        with self.assertRaises(ReconcileRequired) as raised:
            self.entry(design(works={"w1": "another W1", "w2": "W2 が成立する"}))
        self.assertIsNone(raised.exception.reason, "the live same-request refusal, not phase_already_expanded")
        self.assertEqual(record, self.planning_records()[0])

    def test_a_pending_legacy_record(self) -> None:
        with crash_at(rm, "register_works", when=lambda n, mutation, stage, specs, relations: stage == "integration"):
            with self.assertRaises(Crash):
                rm.enter_phase(self.store, self.phase_id, design())
        with self.assertRaises(ReconcileRequired) as raised:
            self.entry(design())
        self.assertEqual("review_marker_mismatch", raised.exception.reason)

    def test_a_marker_mismatch(self) -> None:
        with crash_at(rm, "register_works", when=lambda n, mutation, stage, specs, relations: stage == "integration"):
            with self.assertRaises(Crash):
                self.entry(design())
        with self.assertRaises(ReconcileRequired) as raised:
            rm.enter_phase(self.store, self.phase_id, design())
        self.assertEqual("review_marker_mismatch", raised.exception.reason)


if __name__ == "__main__":
    unittest.main()
