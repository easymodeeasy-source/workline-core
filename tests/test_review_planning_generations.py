"""P2 §28 B: generation serialization and the transition state machine (G1 accept, G2 settle, G3 seal, G4 invalidate)."""

from __future__ import annotations

import unittest
from unittest import mock

from helpers import git
from planning_helpers import Crash, PlanningTestCase, Reviewer, crash_at, plan, rr, run_ids
from workline import roadmap as rm
from workline import yamlish
from workline.errors import ReconcileRequired
from workline.mutation import Mutation, MutationController
from workline.phase_create import PhaseRelationSpec, PhaseSpec
from workline.review import gate, planning, serialize
from workline.review import paths as review_paths
from workline.review import records
from workline.review.store import ReviewStore
from workline.review.validate import validate_review
from workline.validate import validate_project


def _is_generation(mutation: Mutation, number: int) -> bool:
    invocation = mutation.invocation
    return invocation.get("operation") == "review-generation" and invocation.get("generation") == number


def _changed_authority():
    real = planning._read_authority

    def changed(path):
        data = real(path)
        return data + b"\n<!-- authority changed -->\n" if str(path).endswith("registry.md") else data

    return mock.patch.object(planning, "_read_authority", changed)


def _changed_policy():
    return mock.patch.dict(planning.POLICY_RECORD, {"repair": "a changed repair rule"})


class _GenerationCase(PlanningTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()
        self.reviewer = Reviewer()

    def run_plan(self, the_plan=None):
        return self.reviewed_roadmap(self.store, self.reviewer, the_plan)

    def crash(self, target, name, **kwargs):
        with crash_at(target, name, **kwargs):
            with self.assertRaises(Crash):
                self.run_plan()

    def only_run(self) -> str:
        (run_id,) = run_ids(self.store)
        return run_id

    def generations(self) -> list[int]:
        chain = self.chain(self.store, self.only_run())
        return [generation.generation for generation in chain.generations]


class UninterruptedTests(_GenerationCase):
    def test_three_generation_commits_before_kp_and_no_generation_4(self) -> None:
        result = self.run_plan()
        run_id = result.review_run_id
        subjects = self.subjects(self.store)
        expected = [f"chore(workline): record review generation {n} of {run_id}" for n in (3, 2, 1)]
        self.assertEqual(expected, subjects[2:5])
        self.assertTrue(subjects[1].startswith("chore(workline): create roadmap"))
        self.assertEqual([1, 2, 3], self.generations())
        self.assertFalse(ReviewStore(self.store).supersession_exists(result.receipt_id))
        self.assertEqual([], validate_review(self.store))


class GenerationWindowTests(_GenerationCase):
    """§21.1 rows 3-5, 9 and 11: each interrupted generation is resumed before N+1 is computed."""

    def assert_completes(self) -> None:
        result = self.run_plan()
        self.assertEqual("registered", result.status)
        self.assertEqual([1, 2, 3], self.generations())
        self.assertEqual([], self.pending(self.store))
        self.assertEqual([], validate_review(self.store))

    def test_row_3_generation_1_begun_with_no_effect(self) -> None:
        self.crash(gate, "require_committable", when=lambda n, store, relatives: len(relatives) == 3)
        pending = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "review-generation"]
        self.assertEqual(1, len(pending))
        self.assertEqual([], pending[0]["effects"])
        self.assertEqual((), run_ids(self.store))
        self.assert_completes()

    def test_row_4_generation_1_partly_applied(self) -> None:
        from workline.mutation import MutationController as Controller

        self.crash(Controller, "_create_review_record", after=True,
                   when=lambda n, self_, relative, content: "candidate-snapshots" in relative)
        self.assert_completes()

    def test_row_5_generation_1_committed_not_completed(self) -> None:
        self.crash(Mutation, "complete", when=lambda n, self_: _is_generation(self_, 1))
        self.assertEqual([1], self.generations())
        self.assert_completes()

    def test_row_9_generation_2_recorded_not_applied(self) -> None:
        self.crash(rr, "_finish_generation", when=lambda n, store, gen: gen.invocation.get("generation") == 2)
        self.assertEqual(1, len(self.reviewer.tasks))
        self.assert_completes()
        self.assertEqual(1, len(self.reviewer.tasks), "the reviewer is not called again")

    def test_row_11_seal_written_without_its_receipt(self) -> None:
        self.crash(MutationController, "_create_review_record", after=True,
                   when=lambda n, self_, relative, content: relative.endswith("/000003.yaml"))
        self.assertEqual([1, 2, 3], [g.generation for g in ReviewStore(self.store).gate_chain(self.only_run()).generations])
        self.assert_completes()

    def test_a_created_generation_file_with_its_applied_flag_unsaved_is_matching_and_no_n_plus_2(self) -> None:
        self.crash(MutationController, "_create_review_record", after=True,
                   when=lambda n, self_, relative, content: relative.endswith("/000002.yaml"))
        (gen,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "review-generation"]
        self.assertFalse(gen["effects"][0]["applied"])
        self.assert_completes()
        self.assertNotIn(4, self.generations())


class ScopeAndSnapshotTests(_GenerationCase):
    def test_initial_scope_is_exact_and_no_extend_scope(self) -> None:
        extended: list[str] = []
        real = Mutation.extend_scope

        def watch(self_, *args, **kwargs):
            if self_.invocation.get("operation") == "review-generation":
                extended.append(self_.id)
            return real(self_, *args, **kwargs)

        with mock.patch.object(Mutation, "extend_scope", watch):
            self.crash(rr, "_finish_generation", when=lambda n, store, gen: True)
        (gen,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "review-generation"]
        run_id = gen["invocation"]["review_run_id"]
        files = set(gen["write_scope"]["files"])
        task_id = gen["effects"][1]["payload"]["path"].rsplit("/", 1)[-1][:-5]
        snapshot = gen["effects"][0]["payload"]["path"]
        self.assertEqual(
            {review_paths.gate_rel(run_id, 1), review_paths.serialization_token_rel(run_id), snapshot,
             review_paths.task_input_rel(task_id)},
            files,
        )
        self.assertEqual([], gen["write_scope"]["entities"])
        self.assertEqual([], extended)
        # the dirty snapshot was noted when the generation mutation began, before its first effect
        self.assertIn("preexisting_dirty", gen["notes"])

    def pending_generation(self) -> dict:
        (gen,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "review-generation"]
        return gen

    def test_seal_and_invalidation_scopes(self) -> None:
        self.crash(rr, "_finish_generation", when=lambda n, store, gen: gen.invocation.get("generation") == 3)
        gen = self.pending_generation()
        run_id = gen["invocation"]["review_run_id"]
        receipt_id = gen["invocation"]["receipt_id"]
        self.assertEqual(
            {review_paths.gate_rel(run_id, 3), review_paths.serialization_token_rel(run_id),
             review_paths.receipt_rel(receipt_id)},
            set(gen["write_scope"]["files"]),
        )
        self.assertEqual("seal", gen["invocation"]["transition"])

    def test_settle_scope(self) -> None:
        self.crash(rr, "_finish_generation", when=lambda n, store, gen: gen.invocation.get("generation") == 2)
        gen = self.pending_generation()
        run_id = gen["invocation"]["review_run_id"]
        self.assertEqual("settle", gen["invocation"]["transition"])
        self.assertEqual({review_paths.gate_rel(run_id, 2), review_paths.serialization_token_rel(run_id)},
                         set(gen["write_scope"]["files"]))
        self.assertEqual([], gen["write_scope"]["entities"])

    def test_invalidation_scope_and_its_one_stage(self) -> None:
        self.crash(rr, "_use_check")
        with _changed_authority():
            self.crash(rr, "_finish_generation", when=lambda n, store, gen: gen.invocation.get("generation") == 4)
        gen = self.pending_generation()
        run_id = gen["invocation"]["review_run_id"]
        receipt_id = gen["invocation"]["receipt_id"]
        self.assertEqual("invalidate", gen["invocation"]["transition"])
        self.assertEqual(
            {review_paths.gate_rel(run_id, 4), review_paths.serialization_token_rel(run_id),
             review_paths.supersession_rel(receipt_id)},
            set(gen["write_scope"]["files"]),
        )
        self.assertEqual([], gen["write_scope"]["entities"])
        # gate 4 and the Supersession are one stage, in this order, then that stage's commit (§11.6)
        files = [e for e in gen["effects"] if e["kind"] == "create_file"]
        self.assertEqual([review_paths.gate_rel(run_id, 4), review_paths.supersession_rel(receipt_id)],
                         [e["payload"]["path"] for e in files])
        self.assertEqual(1, len({e["stage"] for e in files}), "one stage")

    def test_no_generation_mutation_ever_extends_its_scope(self) -> None:
        extended: list[int] = []
        real = Mutation.extend_scope

        def watch(self_, *args, **kwargs):
            if self_.invocation.get("operation") == "review-generation":
                extended.append(self_.invocation.get("generation"))
            return real(self_, *args, **kwargs)

        with mock.patch.object(Mutation, "extend_scope", watch):
            self.crash(rr, "_use_check")  # generations 1 to 3, each applied, committed and completed
            with _changed_authority():
                self.assertEqual("stale", self.run_plan().status)  # generation 4
            self.assertEqual("registered", self.run_plan(plan("Another Roadmap")).status)
        self.assertEqual([], extended)


class OwnershipConflictTests(_GenerationCase):
    def _pending_generation(self) -> dict:
        self.crash(rr, "_finish_generation", when=lambda n, store, gen: gen.invocation.get("generation") == 2)
        (gen,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "review-generation"]
        return gen

    def _rewrite(self, record: dict) -> None:
        path = self.store.mutations / f"{record['mutation_id']}.yaml"
        path.write_text(yamlish.dump(record), encoding="utf-8", newline="\n")

    def test_a_generation_bound_to_another_planning_mutation_is_a_conflict(self) -> None:
        gen = self._pending_generation()
        gen["invocation"]["planning_mutation_id"] = "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV"
        self._rewrite(gen)
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_generation_owner_conflict", raised.exception.reason)

    def test_two_pending_generation_mutations_are_a_conflict(self) -> None:
        gen = self._pending_generation()
        twin = yamlish.load(yamlish.dump(gen))
        twin["mutation_id"] = "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV"
        self._rewrite(twin)
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_generation_owner_conflict", raised.exception.reason)
        self.assertEqual([1], self.generations(), "no fork, no skipped generation")

    def test_a_transition_out_of_order_is_refused(self) -> None:
        gen = self._pending_generation()
        gen["invocation"]["generation"] = 3
        gen["invocation"]["transition"] = "seal"
        self._rewrite(gen)
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_chain_invalid", raised.exception.reason)


class BindingAcrossMutationsTests(_GenerationCase):
    def test_a_branch_switch_between_generation_commits_is_reconciled(self) -> None:
        self.crash(rr, "_launch_and_settle")
        git(self.store.root, "checkout", "-q", "-b", "elsewhere")
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_binding_moved", raised.exception.reason)
        git(self.store.root, "checkout", "-q", "main")
        self.assertEqual("registered", self.run_plan().status)

    def test_a_branch_switch_before_the_seal_is_reconciled(self) -> None:
        self.crash(rr, "_seal")
        git(self.store.root, "checkout", "-q", "-b", "elsewhere")
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_binding_moved", raised.exception.reason)


class _InvalidationCase(_GenerationCase):
    """P2-CONTRACT-002: a Run stale after its seal is invalidated by generation 4 and a Supersession, then ``stale``."""

    def assert_invalidated(self, result, reason: str) -> None:
        self.assertEqual("stale", result.status)
        self.assertEqual(reason, result.detail)
        run_id = result.review_run_id
        review = ReviewStore(self.store)
        chain = review.gate_chain(run_id)
        self.assertEqual([1, 2, 3, 4], [generation.generation for generation in chain.generations])
        third, fourth = chain.generations[2], chain.generations[3]
        self.assertEqual(third.receipt_id, result.receipt_id)
        self.assertEqual((4, 3, chain.digests[2]), (fourth.generation, fourth.previous_generation, fourth.previous_digest))
        for name in ("review_kind", "target_identity", "operation_identity", "candidate_hash", "review_context_hash",
                     "effective_policy_hash", "coverage_digest", "raw_report_set_digest", "adjudication_digest",
                     "obligation_digest", "accepted_tasks", "settled_tasks"):
            self.assertEqual(getattr(third, name), getattr(fourth, name), name)
        self.assertEqual(
            serialize.digest(planning.invalidation_evidence_record(third.receipt_id, reason)), fourth.evidence_digest
        )
        self.assertEqual(("open", None, None), (fourth.status, fourth.receipt_id, fourth.authorized_operation_stage))
        supersession = review.read_supersession(third.receipt_id)
        self.assertEqual((third.receipt_id, run_id, 4, reason),
                         (supersession.superseded_receipt_id, supersession.review_run_id,
                          supersession.superseding_generation, supersession.reason))
        gate.require_persisted(self.store, [review_paths.gate_rel(run_id, 4), review_paths.supersession_rel(third.receipt_id)])
        self.assertEqual(f"chore(workline): record review generation 4 of {run_id}", self.subjects(self.store)[0])
        self.assertEqual([], self.pending(self.store))
        self.assertEqual([], validate_project(self.store))
        material = ReviewStore(self.store).read_candidate_snapshot(chain.generations[0].candidate_hash).material
        reserved = planning.candidate_content(material)["roadmap"]["id"]
        self.assertFalse((self.store.root / ".workline" / "roadmaps" / f"{reserved}.md").exists(), "nothing registered")


class InvalidationTests(_InvalidationCase):
    def test_authority_text_changed_after_the_seal(self) -> None:
        self.crash(rr, "_use_check")
        with _changed_authority():
            result = self.run_plan()
        self.assert_invalidated(result, planning.STALE_CONTEXT)

    def test_policy_changed_after_the_seal(self) -> None:
        self.crash(rr, "_use_check")
        with _changed_policy():
            result = self.run_plan()
        self.assert_invalidated(result, planning.STALE_POLICY)

    def test_committed_declared_base_fact_changed_after_the_seal(self) -> None:
        other = rm.create_roadmap(self.store, rm.RoadmapPlan("Other", "背景", "状態", {"x": PhaseSpec("X", "X が成立する")}))
        x = other.phase_ids["x"]
        the_plan = rm.RoadmapPlan(
            "Planned", "背景", "状態", {"a": PhaseSpec("A", "A が成立する")}, (PhaseRelationSpec("planned_next", x, "a"),)
        )
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.run_plan(the_plan)
        rm.hold_phase(self.store, x)  # a disjoint-scope operation commits in the crash window
        result = self.run_plan(the_plan)
        self.assert_invalidated(result, planning.STALE_DECLARED_BASE)

    def test_the_superseded_receipt_cannot_be_consumed(self) -> None:
        self.crash(rr, "_use_check")
        with _changed_authority():
            # the real invalidation: generation 4 and the Supersession committed, the planning mutation not completed
            self.crash(Mutation, "complete", when=lambda n, self_: self_.invocation.get("operation") == "roadmap-create")
        (record,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-create"]
        review = ReviewStore(self.store)
        (run_id,) = run_ids(self.store)
        chain = review.gate_chain(run_id)
        receipt_id = chain.generations[2].receipt_id
        self.assertTrue(review.supersession_exists(receipt_id))
        # the use check itself, on the chain as it stood at the seal: the Supersession the flow wrote refuses the Receipt
        from workline.review.store import GateChain

        sealed = GateChain(run_id, chain.generations[:3], chain.digests[:3])
        op = rr._Op(store=self.store, operation="roadmap-create", kind=planning.KINDS[planning.KIND_ROADMAP],
                    request=rm.roadmap_request_identity(plan()), review=self.reviewer.review(), live_identity={})
        run = rr._Run(run_id, None, receipt_id, None)
        mutation = Mutation(MutationController(self.store), record, resumed=True)
        with self.assertRaises(ReconcileRequired) as raised:
            rr._use_check(op, mutation, run, sealed)
        self.assertEqual("review_receipt_invalid", raised.exception.reason)
        self.assertIn("a Supersession names the Receipt", str(raised.exception))
        result = self.run_plan()
        self.assertEqual(("stale", receipt_id), (result.status, result.receipt_id))
        # and a fixture Consumption of it is a validate_review problem
        consumption = records.Consumption(
            "rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV", result.receipt_id, result.review_run_id, 3, "custom-kind",
            chain.generations[0].candidate_hash, chain.generations[0].operation_identity,
            "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV", None, None, chain.generations[0].target_identity, None,
        )
        target = self.store.root / review_paths.consumption_rel(consumption.consumption_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialize.canonical_text(consumption.to_record()), encoding="utf-8", newline="\n")
        superseded = [problem for problem in validate_review(self.store)
                      if problem.code == "review_record_conflict" and "which is superseded" in problem.message]
        self.assertEqual(1, len(superseded), "the supersession rule refuses the Consumption of the superseded Receipt")


class InvalidationWindowTests(_InvalidationCase):
    """§21.1 rows 14-16."""

    def _stale_after_seal(self, **crash) -> None:
        self.crash(rr, "_use_check")
        with _changed_authority():
            with crash_at(**crash):
                with self.assertRaises(Crash):
                    self.run_plan()

    def test_row_14_no_recorded_effect_then_current_again_registers(self) -> None:
        self._stale_after_seal(target=gate, name="require_committable",
                               when=lambda n, store, relatives: len(relatives) == 2 and relatives[0].endswith("/000004.yaml"))
        # the authority is back: the unsuperseded Receipt goes on to the registration
        result = self.run_plan()
        self.assertEqual("registered", result.status)
        self.assertEqual([1, 2, 3], self.generations())

    def test_row_14_no_recorded_effect_still_stale_invalidates_again(self) -> None:
        self._stale_after_seal(target=gate, name="require_committable",
                               when=lambda n, store, relatives: len(relatives) == 2 and relatives[0].endswith("/000004.yaml"))
        with _changed_authority():
            result = self.run_plan()
        self.assert_invalidated(result, planning.STALE_CONTEXT)

    def test_row_15_gate_4_created_applied_flag_unsaved(self) -> None:
        self._stale_after_seal(target=MutationController, name="_create_review_record", after=True,
                               when=lambda n, self_, relative, content: relative.endswith("/000004.yaml"))
        (gen,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "review-generation"]
        gate_4 = gen["effects"][0]
        self.assertTrue(gate_4["payload"]["path"].endswith("/000004.yaml"))
        self.assertFalse(gate_4["applied"], "created, its applied flag not saved")
        self.assertTrue((self.store.root / gate_4["payload"]["path"]).is_file())
        result = self.run_plan()  # nothing is evaluated again: the recorded invalidation is finished
        self.assert_invalidated(result, planning.STALE_CONTEXT)

    def test_row_15_gate_4_created_supersession_not(self) -> None:
        self._stale_after_seal(target=MutationController, name="_create_review_record",
                               when=lambda n, self_, relative, content: "/supersessions/" in relative)
        result = self.run_plan()
        self.assert_invalidated(result, planning.STALE_CONTEXT)

    def test_row_15_both_created_not_committed(self) -> None:
        from workline import gitops

        self._stale_after_seal(target=gitops, name="review_commit_effect",
                               when=lambda n, store, message, paths, **kw: "generation 4" in message)
        result = self.run_plan()
        self.assert_invalidated(result, planning.STALE_CONTEXT)

    def test_row_16_committed_not_completed(self) -> None:
        self._stale_after_seal(target=Mutation, name="complete", when=lambda n, self_: _is_generation(self_, 4))
        result = self.run_plan()
        self.assert_invalidated(result, planning.STALE_CONTEXT)

    def test_row_16_generation_complete_planning_not(self) -> None:
        self._stale_after_seal(target=Mutation, name="complete",
                               when=lambda n, self_: self_.invocation.get("operation") == "roadmap-create")
        result = self.run_plan()
        self.assert_invalidated(result, planning.STALE_CONTEXT)


class StaleBeforeReceiptTests(_GenerationCase):
    """No Supersession without a Receipt: stale before the seal writes no generation and nothing to invalidate."""

    def assert_stale_without_receipt(self, result, generations: list[int]) -> None:
        self.assertEqual(("stale", None), (result.status, result.receipt_id))
        self.assertEqual(generations, self.generations())
        self.assertFalse(ReviewStore(self.store).superseded_receipt_ids())
        self.assertEqual([], validate_review(self.store))
        self.assertEqual([], self.pending(self.store))

    def test_stale_before_the_reviewer_launch(self) -> None:
        self.crash(rr, "_launch_and_settle")
        with _changed_authority():
            result = self.run_plan()
        self.assert_stale_without_receipt(result, [1])
        self.assertEqual(0, len(self.reviewer.tasks))

    def test_stale_before_generation_2(self) -> None:
        patcher = _changed_authority()

        def reviewer_changing_authority(task):
            patcher.start()
            return planning.PlanningReviewReport(task.task_id, "test-reviewer", "1", "completed", ())

        try:
            result = self.reviewed_roadmap(self.store, Reviewer(returns=reviewer_changing_authority))
        finally:
            patcher.stop()
        self.assert_stale_without_receipt(result, [1])
        self.assertEqual((), result.findings)

    def test_stale_before_generation_3(self) -> None:
        self.crash(rr, "_seal")
        with _changed_authority():
            result = self.run_plan()
        self.assert_stale_without_receipt(result, [1, 2])


class ChainShapeTests(_GenerationCase):
    def test_no_generation_5_after_the_invalidation(self) -> None:
        self.crash(rr, "_use_check")
        with _changed_authority():
            result = self.run_plan()
        self.assertEqual("stale", result.status)
        self.assertEqual([1, 2, 3, 4], self.generations())
        self.assertEqual([], self.pending(self.store))

    def test_no_generation_4_once_a_registration_stage_is_recorded(self) -> None:
        self.crash(rm, "register_phases")  # the roadmap stage is recorded and applied
        with _changed_authority():
            with self.assertRaises(ReconcileRequired) as raised:
                self.run_plan()
        self.assertEqual("review_registration_currency_changed", raised.exception.reason)
        self.assertEqual([1, 2, 3], self.generations())

    def test_a_pending_generation_while_a_registration_stage_is_recorded_is_a_conflict(self) -> None:
        self.crash(rm, "register_phases")
        (planning_record,) = [r for r in self.pending(self.store) if r["invocation"].get("operation") == "roadmap-create"]
        run_id = self.only_run()
        fake = {
            "workline": "workline-mutation-intent", "version": 1, "mutation_id": "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "owner": "roadmap", "status": "pending", "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "invocation": {"operation": "review-generation", "planning_mutation_id": planning_record["mutation_id"],
                           "review_run_id": run_id, "generation": 4, "transition": "invalidate"},
            "write_scope": {"entities": [], "files": [review_paths.gate_rel(run_id, 4), review_paths.serialization_token_rel(run_id)]},
            "reserved_ids": {}, "notes": {}, "effects": [],
        }
        (self.store.mutations / f"{fake['mutation_id']}.yaml").write_text(yamlish.dump(fake), encoding="utf-8", newline="\n")
        with self.assertRaises(ReconcileRequired) as raised:
            self.run_plan()
        self.assertEqual("review_generation_owner_conflict", raised.exception.reason)


if __name__ == "__main__":
    unittest.main()
