"""P2 §28 Q: the pre-freeze resume setup - an interrupted setup completes on the same mutation, or is abandoned."""

from __future__ import annotations

import contextlib
import unittest
from unittest import mock

from helpers import git
from planning_helpers import (
    CANONICAL_RULE, Crash, PlanningTestCase, Reviewer, crash_at, deterministic_ids, design, plan, rr, run_ids,
)
from workline import roadmap as rm
from workline import yamlish
from workline.errors import ReconcileRequired, StopError
from workline.mutation import Mutation, MutationController
from workline.review import planning, recovery
from workline.review import paths as review_paths

ROADMAP_YAML = ".workline/relations/roadmap.yaml"


def _changed_authority():
    real = planning._read_authority
    return mock.patch.object(
        planning, "_read_authority", lambda path: real(path) + (b"\nchanged\n" if str(path).endswith("registry.md") else b"")
    )


def _begun(operation: str):
    return lambda n, self_, owner, invocation, scope: invocation.get("operation") == operation


class _SetupCase(PlanningTestCase):
    operation = planning.OPERATION_ROADMAP

    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()

    def call(self, reviewer: Reviewer | None = None):
        return self.reviewed_roadmap(self.store, reviewer or Reviewer())

    def crash_after_begin(self, **kwargs) -> dict:
        """The process ends right after MutationController.begin saved the planning mutation."""
        with crash_at(MutationController, "begin", after=True, when=_begun(self.operation)):
            with self.assertRaises(Crash):
                self.call(**kwargs)
        return self.record()

    def record(self) -> dict:
        (found,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == self.operation]
        return found

    def rewrite(self, record: dict) -> None:
        path = self.store.mutations / f"{record['mutation_id']}.yaml"
        path.write_text(yamlish.dump(record), encoding="utf-8", newline="\n")

    def assert_abandoned(self, mutation_id: str) -> None:
        self.assertEqual([], [r for r in self.pending(self.store) if r["mutation_id"] == mutation_id], "abandoned")
        record = MutationController(self.store).intent_path(mutation_id)
        if record.exists():
            self.assertEqual("abandoned", yamlish.load(record.read_text(encoding="utf-8"))["status"])


class CrashAfterBeginTests(_SetupCase):
    def test_a_the_same_mutation_resumes_runs_discovery_records_the_note_and_completes(self) -> None:
        record = self.crash_after_begin()
        self.assertNotIn(rr.NOTE_DISCOVERY, record.get("notes") or {})
        begun: list[str] = []
        real_begin, real_discover = MutationController.begin, rr._discover
        discovered: list[str] = []

        def begin(self_, owner, invocation, scope):
            begun.append(invocation.get("operation"))
            return real_begin(self_, owner, invocation, scope)

        def discover(op):
            discovered.append(op.operation)
            return real_discover(op)

        with mock.patch.object(MutationController, "begin", begin), mock.patch.object(rr, "_discover", discover), \
                crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.call()
        self.assertEqual([], [b for b in begun if b == self.operation], "no second planning mutation")
        self.assertEqual([self.operation], discovered, "discovery ran again, inside the setup")
        resumed = self.record()
        self.assertEqual(record["mutation_id"], resumed["mutation_id"])
        self.assertEqual({"set_aside": []}, resumed["notes"][rr.NOTE_DISCOVERY])
        self.assertEqual(record["mutation_id"], self.call().mutation_id)


class SomeReservationsTests(_SetupCase):
    def crash_after_the_roadmap_reservation(self) -> dict:
        with crash_at(Mutation, "reserve_id", after=True, when=lambda n, self_, key, kind: key == "roadmap"):
            with self.assertRaises(Crash):
                self.call()
        return self.record()

    def test_b_recorded_reservations_are_reused_and_the_missing_ones_reserved_in_order(self) -> None:
        record = self.crash_after_the_roadmap_reservation()
        self.assertEqual(["roadmap"], list(record["reserved_ids"]))
        result = self.call()
        self.assertEqual(record["reserved_ids"]["roadmap"], result.registration.roadmap_id)

    def test_b_the_missing_ones_are_reserved_in_the_frozen_order(self) -> None:
        records = []
        for name, interrupted in (("straight", False), ("resumed", True)):
            with deterministic_ids():
                self.store = self.planning_project(name)
                if interrupted:
                    self.crash_after_the_roadmap_reservation()
                with crash_at(rr, "_launch_and_settle"):
                    with self.assertRaises(Crash):
                        self.call()
            records.append(self.record())
        straight, resumed = records
        self.assertEqual(list(straight["reserved_ids"].items()), list(resumed["reserved_ids"].items()),
                         "every reservation, in the order the frozen freeze makes them")
        self.assertEqual(straight["mutation_id"], resumed["mutation_id"])

    def test_b_a_recorded_key_the_order_does_not_reserve_is_setup_invalid(self) -> None:
        record = self.crash_after_the_roadmap_reservation()
        record["reserved_ids"]["an-unknown-key"] = "r_01ARZ3NDEKTSV4RRFFQ69G5FAV"
        self.rewrite(record)
        with self.assertRaises(ReconcileRequired) as raised:
            self.call()
        self.assertEqual("review_setup_invalid", raised.exception.reason)
        self.assert_abandoned(record["mutation_id"])


class RecoverableMeanwhileTests(_SetupCase):
    def test_c_a_run_that_became_recoverable_is_a_changed_discovery_then_recovered(self) -> None:
        base = self.head(self.store)
        git(self.store.root, "checkout", "-q", "-b", "side")
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.call()
        (run_id,) = run_ids(self.store)
        (self.store.mutations / f"{self.record()['mutation_id']}.yaml").unlink()  # only its runtime record goes
        git(self.store.root, "checkout", "-q", "main")
        self.assertEqual(base, self.head(self.store))
        new_run = self.crash_after_begin()
        self.assertNotIn(planning.MARKER_RECOVERY, new_run["invocation"])
        git(self.store.root, "merge", "-q", "--no-edit", "side")  # the Run is canonical, and recoverable, now
        with self.assertRaises(ReconcileRequired) as raised:
            self.call()
        self.assertEqual("review_discovery_changed", raised.exception.reason)
        self.assert_abandoned(new_run["mutation_id"])
        intent = MutationController(self.store).intent_path(new_run["mutation_id"])
        if intent.exists():
            self.assertEqual(new_run["invocation"], yamlish.load(intent.read_text(encoding="utf-8"))["invocation"],
                             "the invocation is never rewritten into a recovery")
        result = self.call()
        self.assertEqual(("registered", run_id), (result.status, result.review_run_id))


class RecoveryBeforeBindingTests(_SetupCase):
    def setUp(self) -> None:
        super().setUp()
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.call()
        (self.run_id,) = run_ids(self.store)
        self.runtime_gone(self.store)
        self.recovering = self.crash_after_begin()
        self.assertEqual(self.run_id, self.recovering["invocation"][planning.MARKER_RECOVERY])
        self.assertNotIn(rr.NOTE_RECOVERY_BINDING, self.recovering.get("notes") or {})

    def test_d_the_same_mutation_is_bound_by_discovery_and_continues(self) -> None:
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.call()
        bound = self.record()
        self.assertEqual(self.recovering["mutation_id"], bound["mutation_id"])
        self.assertEqual({"review_run_id": self.run_id, "latest_generation": 1}, bound["notes"][rr.NOTE_RECOVERY_BINDING])
        result = self.call()
        self.assertEqual(("registered", self.run_id, self.recovering["mutation_id"]),
                         (result.status, result.review_run_id, result.mutation_id))

    def test_d_a_reservation_without_a_binding_is_a_conflict(self) -> None:
        self.recovering["reserved_ids"] = {"roadmap": "r_01ARZ3NDEKTSV4RRFFQ69G5FAV"}
        self.rewrite(self.recovering)
        with self.assertRaises(ReconcileRequired) as raised:
            self.call()
        self.assertEqual("review_recovery_reservation_conflict", raised.exception.reason)
        self.assert_abandoned(self.recovering["mutation_id"])

    def test_d_the_run_no_longer_the_one_recoverable_run_is_a_changed_discovery(self) -> None:
        with _changed_authority():  # the Run is obsolete now
            with self.assertRaises(ReconcileRequired) as raised:
                self.call()
        self.assertEqual("review_discovery_changed", raised.exception.reason)
        self.assert_abandoned(self.recovering["mutation_id"])


class StopBeforeGeneration1Tests(_SetupCase):
    def test_e_dirty_overlap_in_a_resumed_setup_abandons(self) -> None:
        record = self.crash_after_begin()
        self.assertNotIn("preexisting_dirty", record.get("notes") or {})
        ledger = self.store.root / ROADMAP_YAML
        ledger.write_bytes(ledger.read_bytes() + b"\n")
        with self.assertRaises(StopError) as raised:
            self.call()
        self.assertEqual("dirty_overlap", raised.exception.code)
        self.assert_abandoned(record["mutation_id"])

    def test_e_an_unsafe_checkout_in_a_resumed_setup_abandons(self) -> None:
        record = self.crash_after_begin()
        self.commit_attributes(self.store, "* text=auto\n")
        with self.assertRaises(StopError) as raised:
            self.call()
        self.assertEqual("review_checkout_unsafe", raised.exception.code)
        self.assert_abandoned(record["mutation_id"])


class PhaseEntryStopTests(_SetupCase):
    operation = planning.OPERATION_PHASE_ENTRY

    def setUp(self) -> None:
        super().setUp()
        self.phase_id = rm.create_roadmap(self.store, plan()).phase_ids["a"]

    def call(self, reviewer: Reviewer | None = None):
        return self.reviewed_entry(self.store, self.phase_id, reviewer or Reviewer())

    def test_e_a_resumed_review_v1_phase_entry_is_abandoned(self) -> None:
        record = self.crash_after_begin()
        ledger = self.store.root / ROADMAP_YAML
        ledger.write_bytes(ledger.read_bytes() + b"\n")
        with self.assertRaises(StopError) as raised:
            self.call()
        self.assertEqual("dirty_overlap", raised.exception.code)
        self.assert_abandoned(record["mutation_id"])

    def test_e_a_resumed_legacy_phase_entry_keeps_the_live_rule(self) -> None:
        with crash_at(MutationController, "begin", after=True, when=_begun(self.operation)):
            with self.assertRaises(Crash):
                rm.enter_phase(self.store, self.phase_id, design())
        record = self.record()
        with mock.patch.object(rm, "_expand_phase", side_effect=StopError("a STOP", code="fixture")):
            with self.assertRaises(StopError):
                rm.enter_phase(self.store, self.phase_id, design())
        self.assertEqual("pending", self.record()["status"], "a resumed legacy Phase entry is never abandoned")
        self.assertEqual(record["mutation_id"], self.record()["mutation_id"])


class AfterGeneration1Tests(_SetupCase):
    def test_f_nothing_is_run_again_or_rewritten_and_a_stop_leaves_it_pending(self) -> None:
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.call()
        before = self.record()
        with mock.patch.object(recovery, "discover", side_effect=AssertionError("discovery ran")):
            with self.assertRaises(StopError) as raised:
                self.call(Reviewer(raises=RuntimeError("the reviewer failed")))
        self.assertEqual("review_reviewer_failed", raised.exception.code)
        after = self.record()
        self.assertEqual(before["mutation_id"], after["mutation_id"])
        self.assertEqual(before["notes"][rr.NOTE_DISCOVERY], after["notes"][rr.NOTE_DISCOVERY])
        self.assertEqual(before["notes"][rr.NOTE_BINDING], after["notes"][rr.NOTE_BINDING])
        self.assertEqual("pending", after["status"])


class RecoveryAfterGeneration1Tests(_SetupCase):
    def test_f_a_recovery_mutation_keeps_its_binding_and_a_stop_leaves_it_pending(self) -> None:
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.call()
        self.runtime_gone(self.store)
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.call()  # the recovery planning mutation binds the Run and reaches the reviewer launch
        before = self.record()
        self.assertIn(planning.MARKER_RECOVERY, before["invocation"])
        self.assertIn(rr.NOTE_RECOVERY_BINDING, before["notes"])
        with mock.patch.object(recovery, "discover", side_effect=AssertionError("discovery ran")):
            with self.assertRaises(StopError) as raised:
                self.call(Reviewer(raises=RuntimeError("the reviewer failed")))
        self.assertEqual("review_reviewer_failed", raised.exception.code)
        after = self.record()
        self.assertEqual(before["mutation_id"], after["mutation_id"])
        self.assertEqual(before["invocation"], after["invocation"])
        self.assertEqual(before["notes"][rr.NOTE_RECOVERY_BINDING], after["notes"][rr.NOTE_RECOVERY_BINDING])
        self.assertEqual(before["notes"].get(rr.NOTE_DISCOVERY), after["notes"].get(rr.NOTE_DISCOVERY))
        self.assertEqual(before["reserved_ids"], after["reserved_ids"])
        self.assertEqual("pending", after["status"])


class NoBypassTests(_SetupCase):
    """Every resumed setup runs each check, and a failing one stops it exactly as it stops a begun setup."""

    def both_stop(self, prepare, code: str, patches=()) -> None:
        record = self.crash_after_begin()
        prepare()
        codes = []
        for call in (self.call, lambda: self.reviewed_roadmap(self.store, Reviewer(), plan("A Begun Roadmap"))):
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch())
                with self.assertRaises(StopError) as raised:
                    call()
            codes.append(raised.exception.code)
        self.assertEqual([code, code], codes, "resumed, then begun")
        self.assert_abandoned(record["mutation_id"])
        self.assertEqual([], [r for r in self.pending(self.store) if r["invocation"].get("name") == "A Begun Roadmap"])

    def test_the_checkout_capability(self) -> None:
        self.both_stop(lambda: self.commit_attributes(self.store, "* text=auto\n"), "review_checkout_unsafe")

    def test_the_dirty_overlap(self) -> None:
        ledger = self.store.root / ROADMAP_YAML
        self.both_stop(lambda: ledger.write_bytes(ledger.read_bytes() + b"\n"), "dirty_overlap")

    def test_the_context(self) -> None:
        unavailable = lambda: mock.patch.object(planning, "context_record", side_effect=StopError(
            "the Context cannot be computed", code="review_context_unavailable"))
        self.both_stop(lambda: None, "review_context_unavailable", patches=(unavailable,))

    def test_the_policy(self) -> None:
        unavailable = lambda: mock.patch.object(planning, "policy_hash", side_effect=StopError(
            "the Policy cannot be computed (fixture)", code="review_context_unavailable"))
        self.both_stop(lambda: None, "review_context_unavailable", patches=(unavailable,))

    def test_the_review_namespace_readability(self) -> None:
        def unreadable() -> None:
            other = self.store.root / review_paths.receipt_rel("rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV")
            other.parent.mkdir(parents=True, exist_ok=True)
            other.write_bytes(b"not: canonical\r\n")
        self.both_stop(unreadable, "review_namespace_unreadable")


class NoBypassBarrierTests(PlanningTestCase):
    def test_the_publication_barrier(self) -> None:
        store = self.planning_project(remote=True)
        with crash_at(rr, "_c2_kp"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store, Reviewer(), plan("Unproven"))
        self.runtime_gone(store)  # Kp stays unproven in HEAD's history
        with crash_at(MutationController, "begin", after=True, when=_begun(planning.OPERATION_ROADMAP)):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store, Reviewer(), plan("Resumed"))
        (record,) = [r for r in self.pending(store) if r["invocation"].get("name") == "Resumed"]
        codes = []
        for name in ("Resumed", "Begun"):
            with self.assertRaises(StopError) as raised:
                self.reviewed_roadmap(store, Reviewer(), plan(name))
            codes.append(raised.exception.code)
        self.assertEqual(["review_publication_barrier"] * 2, codes)
        self.assertEqual([], [r for r in self.pending(store) if r["mutation_id"] == record["mutation_id"]])


if __name__ == "__main__":
    unittest.main()
