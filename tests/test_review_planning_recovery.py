"""P2 §28 L: runtime-loss recovery - the same Run continued from its committed records, never replaced."""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import git
from planning_helpers import (
    Crash, PlanningTestCase, Reviewer, crash_at, design, plan, raw_git, rr, run_ids, snapshot_material,
)
from workline import ids
from workline import mutation as mutation_module
from workline import roadmap as rm
from workline import yamlish
from workline.errors import ReconcileRequired, StopError
from workline.mutation import MutationController, WriteScope
from workline.oplock import project_operation
from workline.review import gate, planning, recovery
from workline.review import paths as review_paths
from workline.review.store import ReviewStore
from workline.store import ProjectStore

DOMAIN_KINDS = ("roadmap", "phase", "work", "relation")


def _changed_authority():
    real = planning._read_authority
    return mock.patch.object(
        planning, "_read_authority", lambda path: real(path) + (b"\nchanged\n" if str(path).endswith("registry.md") else b"")
    )


def _generation_commit(number: int):
    return lambda n, store, payload, paths: f"record review generation {number} of" in payload.get("message", "")


class _RecoveryCase(PlanningTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()

    def run_plan(self, reviewer: Reviewer | None = None):
        return self.reviewed_roadmap(self.store, reviewer or Reviewer())

    def crash(self, target, name, reviewer: Reviewer | None = None, **kwargs) -> None:
        with crash_at(target, name, **kwargs):
            with self.assertRaises(Crash):
                self.run_plan(reviewer)

    def planning_records(self) -> list[dict]:
        return [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-create"]

    def lost(self) -> dict:
        """The planning mutation's record, read just before the runtime is lost."""
        (record,) = self.planning_records()
        return record

    def only_run(self) -> str:
        (run_id,) = run_ids(self.store)
        return run_id

    def recovered_invocation_spy(self):
        seen: list[dict] = []
        real = MutationController.begin

        def begin(self_, owner, invocation, scope):
            seen.append(dict(invocation))
            return real(self_, owner, invocation, scope)

        return seen, mock.patch.object(MutationController, "begin", begin)


class Generation1Tests(_RecoveryCase):
    def test_the_same_run_and_task_are_recovered_and_settled_by_the_recovery_mutation(self) -> None:
        self.crash(rr, "_launch_and_settle")
        lost = self.lost()
        run_id = self.only_run()
        chain = self.chain(self.store, run_id)
        task_id = chain.generations[0].accepted_tasks[0]["task_id"]
        stored = ReviewStore(self.store).read_task_input(task_id)
        lost_receipt = lost["reserved_ids"][gate.review_receipt_key(run_id, planning.SEAL_GENERATION)]
        lost_consumption = lost["reserved_ids"][gate.review_consumption_key(lost_receipt)]
        self.runtime_gone(self.store)
        reviewer = Reviewer()
        with crash_at(rr, "_finish_generation", when=lambda n, store, gen: gen.invocation.get("generation") == 2):
            with self.assertRaises(Crash):
                self.run_plan(reviewer)
        (recovering,) = self.planning_records()
        self.assertEqual(run_id, recovering["invocation"][planning.MARKER_RECOVERY])
        self.assertNotEqual(lost["mutation_id"], recovering["mutation_id"])
        self.assertEqual([task_id], [task.task_id for task in reviewer.tasks])
        self.assertEqual(planning.task_from_input(stored, planning.KIND_ROADMAP), reviewer.tasks[0], "exactly the original task")
        (gen,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == planning.OPERATION_GENERATION]
        self.assertEqual(recovering["mutation_id"], gen["invocation"]["planning_mutation_id"])
        self.assertEqual(2, gen["invocation"]["generation"])
        result = self.run_plan(reviewer)
        self.assertEqual(("registered", run_id), (result.status, result.review_run_id))
        self.assertEqual(recovering["mutation_id"], result.mutation_id)
        # the lost runtime-only reservations are never reused; the canonical ones (Run, task, domain) are bound
        self.assertNotIn(result.receipt_id, (lost_receipt, lost_consumption))
        self.assertNotIn(result.consumption_id, (lost_receipt, lost_consumption))
        self.assertEqual(lost["reserved_ids"]["roadmap"], result.registration.roadmap_id)

    def test_from_a_fresh_clone(self) -> None:
        self.crash(rr, "_launch_and_settle")
        run_id = self.only_run()
        task_id = self.chain(self.store, run_id).generations[0].accepted_tasks[0]["task_id"]
        clone = self.fresh_clone(self.store.root, "clone")
        git(clone.root, "remote", "remove", "origin")
        self.enter(clone.root)
        reviewer = Reviewer()
        result = self.reviewed_roadmap(clone, reviewer)
        self.assertEqual("registered", result.status)
        self.assertEqual(run_id, result.review_run_id)
        self.assertEqual([task_id], [task.task_id for task in reviewer.tasks])

    def test_a_missing_task_input_is_incomplete(self) -> None:
        self.crash(rr, "_launch_and_settle")
        run_id = self.only_run()
        task_id = self.chain(self.store, run_id).generations[0].accepted_tasks[0]["task_id"]
        self.runtime_gone(self.store)
        git(self.store.root, "rm", "-q", review_paths.task_input_rel(task_id))
        git(self.store.root, "commit", "-q", "-m", "a person deletes the task input")
        self.assert_incomplete()

    def test_a_task_input_digest_mismatch_is_incomplete(self) -> None:
        self.crash(rr, "_launch_and_settle")
        run_id = self.only_run()
        task_id = self.chain(self.store, run_id).generations[0].accepted_tasks[0]["task_id"]
        self.runtime_gone(self.store)
        path = self.store.root / review_paths.task_input_rel(task_id)
        path.write_text(path.read_text(encoding="utf-8").replace("request_digest: ", "request_digest: 0", 1),
                        encoding="utf-8", newline="\n")
        self.assert_incomplete(reasons=("review_recovery_incomplete",), stop_codes=("review_namespace_unreadable",))

    def test_a_candidate_snapshot_mismatch_fails_closed(self) -> None:
        self.crash(rr, "_launch_and_settle")
        run_id = self.only_run()
        candidate_hash = self.chain(self.store, run_id).generations[0].candidate_hash
        self.runtime_gone(self.store)
        path = self.store.root / review_paths.candidate_snapshot_rel(candidate_hash)
        path.write_text(path.read_text(encoding="utf-8").replace("Phase A", "Phase Z"), encoding="utf-8", newline="\n")
        self.assert_incomplete(reasons=("review_recovery_incomplete",), stop_codes=("review_namespace_unreadable",))

    def assert_incomplete(self, reasons=("review_recovery_incomplete",), stop_codes=()) -> None:
        before = run_ids(self.store)
        reviewer = Reviewer()
        try:
            self.run_plan(reviewer)
        except ReconcileRequired as exc:
            self.assertIn(exc.reason, reasons)
        except StopError as exc:
            self.assertIn(exc.code, stop_codes)
        else:
            self.fail("recovered or replaced a Run that is not whole")
        self.assertEqual(before, run_ids(self.store), "no new Run")
        self.assertEqual([], reviewer.tasks, "no new task")
        self.assertEqual([], self.planning_records(), "nothing begun")


class AmbiguousTests(_RecoveryCase):
    def test_two_recoverable_runs_merged_into_one_history_are_ambiguous(self) -> None:
        base = self.head(self.store)
        git(self.store.root, "checkout", "-q", "-b", "first")
        self.crash(rr, "_launch_and_settle")
        self.runtime_gone(self.store)
        git(self.store.root, "checkout", "-q", "-b", "second", base)
        self.crash(rr, "_launch_and_settle")
        self.runtime_gone(self.store)
        git(self.store.root, "merge", "-q", "--no-edit", "first")
        self.assertEqual(2, len(run_ids(self.store)))
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_recovery_ambiguous", raised.exception.reason)
        self.assertEqual([], self.planning_records())


class Generation2Tests(_RecoveryCase):
    def test_authorizing_and_current_resumes_without_a_reviewer_and_reserves_the_receipt_anew(self) -> None:
        self.crash(rr, "_seal")
        lost = self.lost()
        run_id = self.only_run()
        lost_receipt = lost["reserved_ids"][gate.review_receipt_key(run_id, planning.SEAL_GENERATION)]
        self.runtime_gone(self.store)
        result = self.run_plan(Reviewer(raises=AssertionError("the settled task was launched again")))
        self.assertEqual("registered", result.status)
        self.assertEqual(run_id, result.review_run_id)
        self.assertNotEqual(lost_receipt, result.receipt_id)

    def test_not_authorizing_is_set_aside_and_a_new_run_names_it(self) -> None:
        declined = Reviewer(status="declined")
        self.crash(rr, "_finish", reviewer=declined,
                   when=lambda n, op, mutation, run, status, **kw: status == rr.STATUS_NOT_AUTHORIZED)
        first = self.only_run()
        settled_task = self.chain(self.store, first).generations[0].accepted_tasks[0]["task_id"]
        self.runtime_gone(self.store)
        reviewer = Reviewer()
        result = self.run_plan(reviewer)
        self.assertEqual("registered", result.status)
        self.assertNotEqual(first, result.review_run_id)
        self.assertNotIn(settled_task, [task.task_id for task in reviewer.tasks], "never launched again")
        envelope = reviewer.tasks[0].request_envelope
        self.assertEqual([{"review_run_id": first, "reason": planning.SET_ASIDE_NOT_AUTHORIZED}], envelope["set_aside_runs"])


class Generation3Tests(_RecoveryCase):
    def test_current_registers_under_the_same_receipt(self) -> None:
        self.crash(rr, "_use_check")
        run_id = self.only_run()
        receipt = self.chain(self.store, run_id).latest.receipt_id
        self.runtime_gone(self.store)
        result = self.run_plan(Reviewer(raises=AssertionError("no reviewer call")))
        self.assertEqual(("registered", run_id, receipt), (result.status, result.review_run_id, result.receipt_id))
        self.assertEqual(receipt, ReviewStore(self.store).read_consumption(result.consumption_id).receipt_id)

    def test_stale_invalidates_and_ends_stale(self) -> None:
        self.crash(rr, "_use_check")
        run_id = self.only_run()
        self.runtime_gone(self.store)
        with _changed_authority():
            result = self.run_plan()
        self.assertEqual(("stale", run_id), (result.status, result.review_run_id))
        self.assertEqual(4, self.chain(self.store, run_id).latest.generation)
        self.assertTrue(ReviewStore(self.store).supersession_exists(result.receipt_id))

    def test_the_sealed_receipt_is_bound_and_the_consumption_reserved_anew(self) -> None:
        self.crash(rr, "_use_check")
        lost = self.lost()
        run_id = self.only_run()
        receipt = self.chain(self.store, run_id).latest.receipt_id
        lost_consumption = lost["reserved_ids"][gate.review_consumption_key(receipt)]
        self.runtime_gone(self.store)
        self.crash(rr, "_use_check")
        (recovering,) = self.planning_records()
        reserved = recovering["reserved_ids"]
        self.assertEqual(receipt, reserved[gate.review_receipt_key(run_id, planning.SEAL_GENERATION)])
        self.assertNotEqual(lost_consumption, reserved[gate.review_consumption_key(receipt)])
        self.assertEqual({"review_run_id": run_id, "latest_generation": 3}, recovering["notes"][rr.NOTE_RECOVERY_BINDING])


class Generation4Tests(_RecoveryCase):
    def test_an_invalidated_run_is_set_aside_and_a_new_run_begun(self) -> None:
        self.crash(rr, "_use_check")
        first = self.only_run()
        with _changed_authority():
            self.assertEqual("stale", self.run_plan().status)
        self.runtime_gone(self.store)
        reviewer = Reviewer()
        result = self.run_plan(reviewer)
        self.assertEqual("registered", result.status)
        self.assertNotEqual(first, result.review_run_id)
        self.assertEqual([{"review_run_id": first, "reason": planning.SET_ASIDE_INVALIDATED}],
                         reviewer.tasks[0].request_envelope["set_aside_runs"])


class DomainReservationTests(_RecoveryCase):
    def _no_domain_id_generated(self):
        generated: list[str] = []
        real = ids.new_id

        def spy(kind):
            generated.append(kind)
            return real(kind)

        return generated, mock.patch.object(ids, "new_id", spy), mock.patch.object(mutation_module, "new_id", spy)

    def test_a_recovered_roadmap_registration_writes_exactly_the_snapshots_ids(self) -> None:
        self.crash(rr, "_use_check")
        material = snapshot_material(self.store, self.only_run())
        self.runtime_gone(self.store)
        generated, spy_ids, spy_mutation = self._no_domain_id_generated()
        with spy_ids, spy_mutation:
            result = self.run_plan()
        self.assertFalse([kind for kind in generated if kind in DOMAIN_KINDS], generated)
        content = planning.candidate_content(material)
        self.assertEqual(content["roadmap"]["id"], result.registration.roadmap_id)
        self.assertEqual({p["key"]: p["id"] for p in content["phases"]}, result.registration.phase_ids)
        ledger = [r.id for r in ProjectStore(self.store.root).read_roadmap_relations()]
        self.assertTrue(set(r["id"] for r in content["relations"]) <= set(ledger))

    def test_a_recovered_phase_entry_registration_writes_exactly_the_snapshots_ids(self) -> None:
        phase_id = rm.create_roadmap(self.store, plan()).phase_ids["a"]
        the_design = design(related={"w1": (rr.RelatedSpec("must_read", "docs/a.md"),)})
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.reviewed_entry(self.store, phase_id, Reviewer(), the_design)
        material = snapshot_material(self.store, self.only_run())
        self.runtime_gone(self.store)
        generated, spy_ids, spy_mutation = self._no_domain_id_generated()
        with spy_ids, spy_mutation:
            result = self.reviewed_entry(self.store, phase_id, Reviewer(), the_design)
        self.assertFalse([kind for kind in generated if kind in DOMAIN_KINDS], generated)
        content = planning.candidate_content(material)
        self.assertEqual({w["key"]: w["id"] for w in content["works"]}, result.registration.work_ids)
        self.assertEqual(content["integration"]["id"], result.registration.integration_id)
        related = [r.id for r in ProjectStore(self.store.root).read_related()]
        self.assertEqual([item["id"] for item in content["works"][0]["related"]], related)

    def _recovery_mutation(self, run_id: str):
        invocation = {"operation": planning.OPERATION_ROADMAP, "name": "n", "request": {}, **planning.invocation_markers(),
                      planning.MARKER_RECOVERY: run_id}
        return MutationController(self.store).begin(rr.OWNER, invocation, WriteScope(entities=(), files=()))

    def test_the_helper_refuses_conflicting_wrong_kind_and_used_ids(self) -> None:
        with project_operation(self.store, planning.OPERATION_ROADMAP, {"name": "n"}):
            self._helper_refusals()

    def _helper_refusals(self) -> None:
        roadmap_id = "r_01ARZ3NDEKTSV4RRFFQ69G5FAV"
        other_roadmap = "r_01ARZ3NDEKTSV4RRFFQ69G5FAW"
        cases = {
            "a key bound to two IDs": ([("roadmap", roadmap_id, "roadmap"), ("roadmap", other_roadmap, "roadmap")], set()),
            "an ID of the wrong kind": ([("roadmap", "p_01ARZ3NDEKTSV4RRFFQ69G5FAV", "roadmap")], set()),
            "an ID already used": ([("roadmap", roadmap_id, "roadmap")], {roadmap_id}),
        }
        for described, (bindings, used) in cases.items():
            with self.subTest(described):
                mutation = self._recovery_mutation("rr_01ARZ3NDEKTSV4RRFFQ69G5FAV")
                before = mutation.path.read_bytes()
                with self.assertRaises(ReconcileRequired) as raised:
                    mutation_module._bind_recovered_reservations(mutation, bindings, used, ("recovery_binding", {"x": 1}))
                self.assertEqual("review_recovery_reservation_conflict", raised.exception.reason)
                self.assertEqual(before, mutation.path.read_bytes(), "nothing recorded")
                mutation.abandon()
        mutation = self._recovery_mutation("rr_01ARZ3NDEKTSV4RRFFQ69G5FAV")
        mutation.reserve_id("roadmap", "roadmap")
        with self.assertRaises(ReconcileRequired) as raised:
            mutation_module._bind_recovered_reservations(mutation, [("roadmap", roadmap_id, "roadmap")], set(),
                                                        ("recovery_binding", {"x": 1}))
        self.assertEqual("review_recovery_reservation_conflict", raised.exception.reason)


class HalfWrittenTests(_RecoveryCase):
    """A half-written canonical generation, or one applied and never committed, with no runtime record."""

    def _refused(self) -> None:
        before = run_ids(self.store)
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_recovery_incomplete", raised.exception.reason)
        self.assertEqual(before, run_ids(self.store), "a new Run never hides it")
        self.assertEqual([], self.planning_records())

    def test_gate_1_without_its_task_input(self) -> None:
        self.crash(mutation_module, "_make_planning_commit", when=_generation_commit(1))
        self.runtime_gone(self.store)
        (task_input,) = (self.store.root / ".workline" / "review" / "task-inputs").glob("*.yaml")
        task_input.unlink()
        self._refused()

    def test_an_applied_but_uncommitted_gate_2(self) -> None:
        self.crash(mutation_module, "_make_planning_commit", when=_generation_commit(2))
        self.runtime_gone(self.store)
        self._refused()

    def test_gate_3_without_its_receipt(self) -> None:
        self.crash(mutation_module, "_make_planning_commit", when=_generation_commit(3))
        self.runtime_gone(self.store)
        (receipt,) = (self.store.root / ".workline" / "review" / "receipts").glob("*.yaml")
        receipt.unlink()
        self._refused()

    def test_generation_4_without_its_supersession(self) -> None:
        self.crash(rr, "_use_check")
        with _changed_authority(), crash_at(mutation_module, "_make_planning_commit", when=_generation_commit(4)):
            with self.assertRaises(Crash):
                self.run_plan()
        self.runtime_gone(self.store)
        (supersession,) = (self.store.root / ".workline" / "review" / "supersessions").glob("*.yaml")
        supersession.unlink()
        self._refused()

    def test_a_generation_mutation_left_pending_by_a_lost_planning_mutation(self) -> None:
        self.crash(rr, "_finish_generation", when=lambda n, store, gen: gen.invocation.get("generation") == 2)
        (planning_record,) = self.planning_records()
        (self.store.mutations / f"{planning_record['mutation_id']}.yaml").unlink()
        self._refused()


class NewRunEligibilityTests(_RecoveryCase):
    def test_an_obsolete_generation_1_is_set_aside_and_never_recovered_even_when_current_again(self) -> None:
        self.crash(rr, "_launch_and_settle")
        first = self.only_run()
        self.runtime_gone(self.store)
        with _changed_authority():
            with crash_at(rr, "_launch_and_settle"):
                with self.assertRaises(Crash):
                    self.run_plan()
        second = [run for run in run_ids(self.store) if run != first][0]
        self.runtime_gone(self.store)
        reviewer = Reviewer()
        with _changed_authority():
            result = self.run_plan(reviewer)
        self.assertEqual(second, result.review_run_id)
        self.assertEqual([{"review_run_id": first, "reason": planning.STALE_CONTEXT}],
                         reviewer.tasks[0].request_envelope["set_aside_runs"])
        self.assertEqual({first, second}, set(run_ids(self.store)), "the obsolete Run is never recovered")

    def test_the_obsolete_run_stays_set_aside_when_its_currency_returns(self) -> None:
        self.crash(rr, "_launch_and_settle")
        first = self.only_run()
        self.runtime_gone(self.store)
        with _changed_authority():
            with crash_at(rr, "_launch_and_settle"):
                with self.assertRaises(Crash):
                    self.run_plan()
        second = [run for run in run_ids(self.store) if run != first][0]
        self.runtime_gone(self.store)
        # the authority text is back: the first Run would be current again, and the second one no longer is
        reviewer = Reviewer()
        result = self.run_plan(reviewer)
        self.assertNotIn(result.review_run_id, (first, second), "a set-aside Run is never recovered afterwards")
        self.assertEqual(
            sorted([{"review_run_id": first, "reason": planning.SET_ASIDE_SET_ASIDE},
                    {"review_run_id": second, "reason": planning.STALE_CONTEXT}], key=lambda item: item["review_run_id"]),
            reviewer.tasks[0].request_envelope["set_aside_runs"],
        )


class StaleBeforeReceiptCompletionTests(_RecoveryCase):
    def test_current_again_recovers_the_old_run(self) -> None:
        self.crash(rr, "_launch_and_settle")
        first = self.only_run()
        with _changed_authority():
            ended = self.run_plan()  # stale before a Receipt: completed with the runtime intact, nothing written
        self.assertEqual(("stale", None), (ended.status, ended.receipt_id))
        self.assertEqual([], self.planning_records())
        result = self.run_plan()  # the authority text is back
        self.assertEqual(("registered", first), (result.status, result.review_run_id))

    def test_still_stale_sets_it_aside_and_begins_a_new_run(self) -> None:
        self.crash(rr, "_launch_and_settle")
        first = self.only_run()
        with _changed_authority():
            ended = self.run_plan()
        self.assertEqual(("stale", None), (ended.status, ended.receipt_id))
        reviewer = Reviewer()
        with _changed_authority():
            result = self.run_plan(reviewer)
        self.assertEqual("registered", result.status)
        self.assertNotEqual(first, result.review_run_id)
        self.assertEqual([{"review_run_id": first, "reason": planning.STALE_CONTEXT}],
                         reviewer.tasks[0].request_envelope["set_aside_runs"])


class WorkingTreeRegistrationTests(_RecoveryCase):
    def test_roadmap_creation_stops_at_the_binding_until_the_files_are_discarded(self) -> None:
        self.crash(rr, "_pre_kp_proof")
        run_id = self.only_run()
        self.runtime_gone(self.store)
        before = self.snapshot_state(self.store)
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_recovery_reservation_conflict", raised.exception.reason)
        self.assertEqual({k: v for k, v in before.items() if "/runtime/" not in k},
                         {k: v for k, v in self.snapshot_state(self.store).items() if "/runtime/" not in k}, "nothing written")
        git(self.store.root, "checkout", "--", ".workline/relations/roadmap.yaml")
        raw_git(self.store.root, "clean", "-q", "-f", "--", ".workline/roadmaps", ".workline/phases")
        result = self.run_plan(Reviewer(raises=AssertionError("no reviewer call")))
        self.assertEqual(("registered", run_id), (result.status, result.review_run_id))

    def test_phase_entry_stops_at_the_live_precheck_until_the_files_are_discarded(self) -> None:
        phase_id = rm.create_roadmap(self.store, plan()).phase_ids["a"]
        with crash_at(rr, "_pre_kp_proof"):
            with self.assertRaises(Crash):
                self.reviewed_entry(self.store, phase_id)
        run_id = self.only_run()
        self.runtime_gone(self.store)
        with self.assertRaises(StopError) as raised:
            self.reviewed_entry(self.store, phase_id)
        self.assertEqual("phase_already_expanded", raised.exception.code)
        git(self.store.root, "checkout", "--", ".workline/relations/roadmap.yaml")
        raw_git(self.store.root, "clean", "-q", "-f", "--", ".workline/works")
        result = self.reviewed_entry(self.store, phase_id, Reviewer(raises=AssertionError("no reviewer call")))
        self.assertEqual(("registered", run_id), (result.status, result.review_run_id))


class AfterKpTests(_RecoveryCase):
    def test_roadmap_creation_is_incomplete_and_no_new_run(self) -> None:
        self.crash(rr, "_c2_kp")
        self.runtime_gone(self.store)
        before = run_ids(self.store)
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_recovery_incomplete", raised.exception.reason)
        self.assertEqual(before, run_ids(self.store))
        from workline.review import publication

        self.assertIsNotNone(publication.barrier_problem(self.store.root, self.head(self.store)))

    def test_phase_entry_is_already_expanded_before_discovery(self) -> None:
        phase_id = rm.create_roadmap(self.store, plan()).phase_ids["a"]
        with crash_at(rr, "_c2_kp"):
            with self.assertRaises(Crash):
                self.reviewed_entry(self.store, phase_id)
        self.runtime_gone(self.store)
        before = run_ids(self.store)
        with mock.patch.object(recovery, "discover", side_effect=AssertionError("discovery ran")):
            with self.assertRaises(StopError) as raised:
                self.reviewed_entry(self.store, phase_id)
        self.assertEqual("phase_already_expanded", raised.exception.code)
        self.assertEqual(before, run_ids(self.store))


class NormalRetryTests(_RecoveryCase):
    def test_a_present_record_is_resumed_without_discovery(self) -> None:
        self.crash(rr, "_use_check")
        (lost,) = self.planning_records()
        with mock.patch.object(recovery, "discover", side_effect=AssertionError("discovery ran")):
            result = self.run_plan()
        self.assertEqual(lost["mutation_id"], result.mutation_id)

    def test_a_pending_recovery_mutation_is_resumed_by_its_exact_invocation(self) -> None:
        self.crash(rr, "_launch_and_settle")
        self.runtime_gone(self.store)
        self.crash(rr, "_launch_and_settle")
        (recovering,) = self.planning_records()
        self.assertIn(planning.MARKER_RECOVERY, recovering["invocation"])
        with mock.patch.object(recovery, "discover", side_effect=AssertionError("discovery ran")):
            result = self.run_plan()
        self.assertEqual(recovering["mutation_id"], result.mutation_id)

    def test_a_legacy_invocation_never_runs_discovery(self) -> None:
        self.crash(rr, "_launch_and_settle")
        self.runtime_gone(self.store)
        with mock.patch.object(recovery, "discover", side_effect=AssertionError("discovery ran")):
            created = rm.create_roadmap(self.store, plan())
        self.assertTrue(created.roadmap_id)


class RecoveryMarkerTests(_RecoveryCase):
    def setUp(self) -> None:
        super().setUp()
        self.crash(rr, "_launch_and_settle")
        self.runtime_gone(self.store)
        self.crash(rr, "_launch_and_settle")
        (self.recovering,) = self.planning_records()
        self.path = self.store.mutations / f"{self.recovering['mutation_id']}.yaml"

    def _rewritten(self, invocation: dict) -> bytes:
        record = dict(self.recovering)
        record["invocation"] = invocation
        self.path.write_text(yamlish.dump(record), encoding="utf-8", newline="\n")
        return self.path.read_bytes()

    def test_a_pending_recovery_record_against_a_legacy_invocation(self) -> None:
        before = self.path.read_bytes()
        with self.assertRaises(ReconcileRequired) as raised:
            rm.create_roadmap(self.store, plan())
        self.assertEqual("review_marker_mismatch", raised.exception.reason)
        self.assertEqual(before, self.path.read_bytes())

    def test_the_recovery_key_without_the_marker_pair(self) -> None:
        invocation = {k: v for k, v in self.recovering["invocation"].items()
                      if k not in (planning.MARKER_REVIEW, planning.MARKER_PUBLICATION)}
        before = self._rewritten(invocation)
        for call in (self.run_plan, lambda: rm.create_roadmap(self.store, plan())):
            with self.assertRaises(ReconcileRequired):
                call()
            self.assertEqual(before, self.path.read_bytes())

    def test_any_other_extra_key(self) -> None:
        before = self._rewritten({**self.recovering["invocation"], "extra": "x"})
        with self.assertRaises(ReconcileRequired):
            self.run_plan()
        self.assertEqual(before, self.path.read_bytes())


if __name__ == "__main__":
    unittest.main()
