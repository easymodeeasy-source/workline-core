"""P5 §28.26 (with §28.17 / §28.18 / §28.20 / §28.21): history against its immutable sources, as pure functions.

* the builders recompute every summary from its P1-P4 source records;
* ``history_problems``: a summary that disagrees with its source is a validation failure, never "latest wins";
* unsupported / HUMAN / dismissed claims never become Finding summaries;
* Repair summary <-> Repair Batch + Repair Result linkage; causal status supported / unresolved / insufficient;
* relation endpoints and duplicate logical identity; Human Decision Evidence points at a real HUMAN part;
* the versioned readiness gates, dispatched by an explicit history contract (no inference, no backfill);
* the RB5 reference projection; and every function here reads only - nothing is written.
"""

from __future__ import annotations

from dataclasses import replace
import os
import unittest

from helpers import rmtree
from workline.errors import StopError, ValidationError
from workline.review import history, p4, paths, records, serialize

from test_review_history_records import (
    CALLER_DECISION, CANDIDATE, CONSUMPTION, DECISION, OTHER_RELATION, OTHER_RUN, RECEIPT, RELATION, RUN, TASK_A,
    WORK, HistoryCase, chain, consumption, generation, human_adjudication, human_decision_fixture, human_reports,
    ready_adjudication, ready_reports, receipt, repair_reports, snapshot,
)
from test_review_p4_adjudication import BATCH, adjudicate, bound, disposition, report, returned
from test_review_p4_records import adjudication_fixture, batch_fixture, result_fixture

RUNS = paths.HISTORY_RUNS
FINDINGS = paths.HISTORY_FINDINGS
REPAIRS = paths.HISTORY_REPAIRS
RELATIONS = paths.HISTORY_RELATIONS
DECISIONS = paths.HISTORY_HUMAN_DECISIONS
OTHER_CONSUMPTION = "rcs_01ARZ3NDEKTSV4RRFFQ69G5FAW"
OTHER_DECISION = "rhd_01ARZ3NDEKTSV4RRFFQ69G5FAW"


def discovery_chain(status: str) -> list[records.GateGeneration]:
    """G1 accepts one discovery task and G2 settles it with ``status`` (GAP-E: the G2 settlement is the fact)."""
    task = {
        "task_id": TASK_A, "task_slot": p4.discovery_slot("correctness"), "task_kind": p4.TASK_KIND_DISCOVERY,
        "reviewer_identity": "reviewer", "reviewer_version": "v1", "candidate_hash": CANDIDATE,
        "candidate_material_digest": "8" * 64, "reconstruction_mode": records.RECONSTRUCTION_SNAPSHOT,
        "request_digest": "8" * 64, "task_input_digest": "8" * 64, "review_context_hash": "b" * 64,
        "effective_policy_hash": p4.policy_hash(),
    }
    first = replace(generation(1, None), accepted_tasks=(task,))
    settled = {"task_id": TASK_A, "status": status, "result_digest": "7" * 64, "settled_generation": 2}
    second = replace(generation(2, serialize.digest(first.to_record())), accepted_tasks=(task,),
                     settled_tasks=(settled,))
    return [first, second]


class World(HistoryCase):
    """Complete P1-P4 source worlds for one P4 Run, each with exactly the history its final transition writes."""

    def human_world(self) -> tuple[records.P4Adjudication, list[records.GateGeneration], history.RunSummary]:
        found = human_adjudication()
        self.put_reports(human_reports())
        self.put_adjudication(found)
        generations = chain(4, adjudication=found)
        self.put_chain(generations)
        summary = history.run_summary(generations[-1], durable_disposition=history.DISPOSITION_HUMAN_WAIT,
                                      candidate_generation=1, adjudication=found)
        self.put_history(RUNS, summary)
        return found, generations, summary

    def consumed_world(self) -> tuple[records.P4Adjudication, list[records.GateGeneration], history.RunSummary]:
        found = ready_adjudication()
        self.put_reports(ready_reports())
        digest = self.put_adjudication(found)
        generations = chain(5, adjudication=found, seal_at=5)
        self.put_chain(generations)
        issued = receipt(digest)
        self.put(paths.receipt_rel(RECEIPT), issued.to_record())
        summary = history.consumed_run_summary(generations[-1], issued, CONSUMPTION, candidate_generation=1,
                                               adjudication=found)
        self.put(paths.consumption_rel(CONSUMPTION), consumption().to_record())
        self.put_history(RUNS, summary)
        for item in history.finding_summaries(found):
            self.put_history(FINDINGS, item)
        return found, generations, summary

    def repaired_world(self) -> tuple[records.P4Adjudication, records.P4RepairBatch, records.P4RepairResult,
                                      history.RunSummary, history.RepairSummary]:
        found = adjudication_fixture()
        self.put_reports(repair_reports())
        digest = self.put_adjudication(found)
        batch = batch_fixture(found, digest)
        result = result_fixture(batch)
        self.put(paths.repair_batch_rel(BATCH), batch.to_record())
        self.put(paths.repair_result_rel(BATCH), result.to_record())
        self.put(paths.candidate_snapshot_rel(CANDIDATE), snapshot().to_record())
        generations = chain(6, adjudication=found)
        self.put_chain(generations)
        summary = history.run_summary(generations[-1], durable_disposition=history.DISPOSITION_REPAIRED,
                                      candidate_generation=1, adjudication=found, repair_batch_id=BATCH)
        repair = history.repair_summary(found, batch, result,
                                        source_candidate_material_digest=self.review.candidate_material_digest(CANDIDATE))
        self.put_history(RUNS, summary)
        self.put_history(REPAIRS, repair)
        for item in history.finding_summaries(found):
            self.put_history(FINDINGS, item)
        return found, batch, result, summary, repair

    def invalidated_world(self) -> history.RunSummary:
        found = ready_adjudication()
        self.put_reports(ready_reports())
        digest = self.put_adjudication(found)
        generations = chain(6, adjudication=found, seal_at=5)
        self.put_chain(generations)
        self.put(paths.receipt_rel(RECEIPT), receipt(digest).to_record())
        self.put(paths.supersession_rel(RECEIPT),
                 records.Supersession(RECEIPT, RUN, 6, p4.INVALIDATION_STALE_RECEIPT).to_record())
        summary = history.run_summary(generations[-1], durable_disposition=history.DISPOSITION_INVALIDATED,
                                      candidate_generation=1, adjudication=found, receipt_id=RECEIPT)
        self.put_history(RUNS, summary)
        for item in history.finding_summaries(found):
            self.put_history(FINDINGS, item)
        return summary

    def reset(self) -> None:
        """Remove every record, so one test can lay down another world."""
        rmtree(self.root / ".workline")

    def problems(self, work_ids=None) -> list[tuple[str, str]]:
        return history.history_problems(self.review, work_ids=work_ids)

    def codes(self, work_ids=None) -> list[str]:  # type: ignore[override]
        return [code for code, _ in self.problems(work_ids)]

    def tree(self) -> dict[str, bytes]:
        found: dict[str, bytes] = {}
        for folder, _, files in os.walk(self.root):
            for name in files:
                path = os.path.join(folder, name)
                with open(path, "rb") as handle:
                    found[os.path.relpath(path, self.root)] = handle.read()
        return found


# --------------------------------------------------------------------------- Run summaries


class RunSummaryTests(World):
    def test_each_final_disposition_validates_against_its_sources(self) -> None:
        worlds = {
            "human_wait": self.human_world,
            "consumed": self.consumed_world,
            "repaired": self.repaired_world,
            "invalidated": self.invalidated_world,
        }
        for name, build in worlds.items():
            with self.subTest(name):
                self.reset()
                build()
                self.assertEqual([], self.problems())

    def test_a_set_aside_run_before_its_adjudication(self) -> None:
        generations = chain(2)
        self.put_chain(generations)
        summary = history.set_aside_run_summary(generations[-1], candidate_generation=None)
        self.put_history(RUNS, summary)
        self.assertEqual([], self.problems())
        self.assertEqual(serialize.digest(generations[-1].to_record()), summary.gate_digest)
        self.assertEqual((), summary.finding_ids)

    def test_the_summary_copies_the_chain_and_the_adjudication(self) -> None:
        found, generations, summary = self.human_world()
        terminal = generations[-1]
        self.assertEqual((4, serialize.digest(terminal.to_record())), (summary.gate_generation, summary.gate_digest))
        self.assertEqual(self.review.gate_chain(RUN).latest_digest, summary.gate_digest)
        self.assertEqual(self.review.adjudication_digest(RUN), summary.adjudication_digest)
        for name in ("review_kind", "target_identity", "operation_identity", "candidate_hash", "review_context_hash",
                     "effective_policy_hash", "evidence_digest", "coverage_digest"):
            self.assertEqual(getattr(terminal, name), getattr(summary, name))

    def test_a_later_generation_than_the_summary_binds_is_a_failure_not_latest_wins(self) -> None:
        found, _, _ = self.human_world()
        self.put_chain(chain(5, adjudication=found))
        self.assertIn(history.PROBLEM_CONFLICT, self.codes())

    def test_a_gate_digest_or_identity_mismatch_fails(self) -> None:
        _, _, summary = self.human_world()
        for change in ({"gate_digest": "d" * 64}, {"evidence_digest": "9" * 64}, {"target_identity": WORK},
                       {"candidate_generation": 2}, {"review_kind": "roadmap-plan-v1"}):
            with self.subTest(change=change):
                self.put_history(RUNS, replace(summary, **change))
                self.assertIn(history.PROBLEM_CONFLICT, self.codes())
        self.put_history(RUNS, summary)
        self.assertEqual([], self.problems())

    def test_the_summary_must_bind_the_adjudication_and_findings_the_chain_settled(self) -> None:
        found, generations, summary = self.consumed_world()
        for change in ({"finding_ids": ()}, {"adjudication_digest": "9" * 64}):
            with self.subTest(change=change):
                self.put_history(RUNS, replace(summary, **change))
                self.assertIn(history.PROBLEM_CONFLICT, self.codes())
        omitted = replace(summary, adjudication_digest=None, finding_ids=())
        self.put_history(RUNS, omitted)
        self.assertIn(history.PROBLEM_CONFLICT, self.codes())

    def test_a_receipt_or_consumption_mismatch_fails(self) -> None:
        _, _, summary = self.consumed_world()
        self.put_history(RUNS, replace(summary, consumption_id=OTHER_CONSUMPTION))
        self.assertIn(history.PROBLEM_CONFLICT, self.codes())
        self.assertIn(history.PROBLEM_MISSING, self.codes())
        self.put_history(RUNS, replace(summary, durable_disposition=history.DISPOSITION_SET_ASIDE, consumption_id=None))
        self.assertIn(history.PROBLEM_CONFLICT, self.codes(), "a consumed Receipt is never set aside")
        self.put_history(RUNS, replace(summary, durable_disposition=history.DISPOSITION_SET_ASIDE, consumption_id=None,
                                       receipt_id=None))
        self.assertIn(history.PROBLEM_CONFLICT, self.codes(), "the chain issued a Receipt the summary omits")

    def test_a_consumed_summary_whose_consumption_is_not_stored_fails(self) -> None:
        self.consumed_world()
        (self.root / paths.consumption_rel(CONSUMPTION)).unlink()
        self.assertIn(history.PROBLEM_MISSING, self.codes())

    def test_an_invalidated_summary_needs_the_supersession(self) -> None:
        self.invalidated_world()
        (self.root / paths.supersession_rel(RECEIPT)).unlink()
        self.assertIn(history.PROBLEM_MISSING, self.codes())

    def test_a_human_wait_summary_of_an_adjudication_that_is_not_human_wait_fails(self) -> None:
        found = ready_adjudication()
        self.put_reports(ready_reports())
        self.put_adjudication(found)
        generations = chain(4, adjudication=found)
        self.put_chain(generations)
        summary = history.run_summary(generations[-1], durable_disposition=history.DISPOSITION_HUMAN_WAIT,
                                      candidate_generation=1, adjudication=found)
        self.put_history(RUNS, summary)
        self.assertIn(history.PROBLEM_CONFLICT, self.codes())

    def test_a_missing_source_run_fails(self) -> None:
        _, _, summary = self.human_world()
        self.put_history(RUNS, replace(summary, review_run_id=OTHER_RUN))
        self.assertIn(history.PROBLEM_MISSING, self.codes())

    def test_the_consumption_bound_builder_refuses_another_receipt_or_run(self) -> None:
        found = ready_adjudication()
        generations = chain(5, adjudication=found, seal_at=5)
        sealed = generations[-1]
        issued = receipt(serialize.digest(found.to_record()))
        self.assertEqual(history.DISPOSITION_CONSUMED, history.consumed_run_summary(
            sealed, issued, CONSUMPTION, candidate_generation=1, adjudication=found).durable_disposition)
        for name, call in {
            "unsealed": lambda: history.consumed_run_summary(generations[3], issued, CONSUMPTION, candidate_generation=1),
            "other receipt": lambda: history.consumed_run_summary(
                sealed, replace(issued, receipt_id="rcp_01ARZ3NDEKTSV4RRFFQ69G5FAW"), CONSUMPTION,
                candidate_generation=1),
            "other run": lambda: history.consumed_run_summary(sealed, replace(issued, review_run_id=OTHER_RUN),
                                                              CONSUMPTION, candidate_generation=1),
            "bad consumption id": lambda: history.consumed_run_summary(sealed, issued, RECEIPT, candidate_generation=1),
            "other generation": lambda: history.consumed_run_summary(sealed, issued, CONSUMPTION,
                                                                     candidate_generation=2, adjudication=found),
        }.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                call()

    def test_the_run_builder_refuses_an_adjudication_of_another_run(self) -> None:
        found = ready_adjudication()
        other = chain(4, adjudication=found, run=OTHER_RUN)[-1]
        with self.assertRaises(ValidationError):
            history.run_summary(other, durable_disposition=history.DISPOSITION_HUMAN_WAIT, candidate_generation=1,
                                adjudication=found)

    def test_a_summary_binding_an_adjudication_its_chain_never_settled_fails(self) -> None:
        found = human_adjudication()
        self.put_reports(human_reports())
        self.put_adjudication(found)
        generations = chain(4)  # the stored adjudication is an orphan: no generation settles it
        self.put_chain(generations)
        self.put_history(RUNS, history.run_summary(generations[-1], durable_disposition=history.DISPOSITION_HUMAN_WAIT,
                                                   candidate_generation=1, adjudication=found))
        self.assertIn(history.PROBLEM_MISSING, self.codes())

    def test_gap_f_a_stored_reserved_disposition_is_refused_by_source_validation(self) -> None:
        _, _, summary = self.consumed_world()
        for value in history.DISPOSITIONS_WITHOUT_TRANSITION:
            with self.subTest(value):
                self.put_history(RUNS, replace(summary, durable_disposition=value, consumption_id=None))
                self.assertIn(history.CODE_DISPOSITION_UNSUPPORTED, self.codes())
                with self.assertRaises(StopError) as raised:
                    history.require_history_ready(self.review, RUN, history.BOUNDARY_CONSUMPTION,
                                                  history_contract=history.HISTORY_CONTRACT)
                self.assertEqual(history.CODE_HISTORY_INVALID, raised.exception.code)
        self.put_history(RUNS, summary)
        self.assertEqual([], self.problems())

    def test_gap_e_not_authorized_is_proven_by_its_failed_discovery_settlement(self) -> None:
        for status, expected in ((records.TASK_SETTLED_FAILED, []), (records.TASK_SETTLED_OK, [history.PROBLEM_CONFLICT])):
            with self.subTest(status=status):
                self.reset()
                generations = discovery_chain(status)
                self.put_chain(generations)
                summary = history.run_summary(generations[-1], durable_disposition=history.DISPOSITION_NOT_AUTHORIZED,
                                              candidate_generation=None)
                self.put_history(RUNS, summary)
                self.assertEqual((2, None, ()), (summary.gate_generation, summary.adjudication_digest,
                                                 summary.finding_ids))
                self.assertEqual(expected, self.codes())


# --------------------------------------------------------------------------- Finding summaries


class FindingSummaryTests(World):
    def test_one_summary_per_normalized_finding_copied_exactly(self) -> None:
        reports = bound(report(TASK_A, "correctness", [("HIGH", "x", "one"), ("LOW", "y", "two"), ("MID", "z", "three"),
                                                       ("LOW", "w", "four")]))
        found = adjudicate(reports, returned(
            disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity="HIGH", semantic_surface="a", repair_identity="a"),
            disposition(TASK_A, 1, p4.OUTCOME_IMPROVEMENT, severity="LOW", semantic_surface="b", repair_identity="b"),
            disposition(TASK_A, 2, p4.OUTCOME_UNSUPPORTED),
            disposition(TASK_A, 3, p4.OUTCOME_DISMISSED),
        ))
        summaries = history.finding_summaries(found)
        self.assertEqual([str(item["finding_id"]) for item in found.findings], [item.finding_id for item in summaries])
        self.assertEqual(2, len(summaries), "unsupported and dismissed claims never become Finding summaries")
        for item, finding in zip(summaries, found.findings):
            self.assertEqual((finding["category"], finding["severity"], finding["semantic_surface"],
                              finding["disposition"], finding["statement"], finding["relation"]),
                             (item.category, item.severity, item.semantic_surface, item.disposition, item.summary,
                              item.relation))
            self.assertEqual(serialize.digest(found.to_record()), item.adjudication_digest)
            self.assertEqual((reports[0][1],), item.source_report_digests)

    def test_unsupported_human_and_dismissed_claims_cannot_become_finding_summaries(self) -> None:
        found = human_adjudication()
        self.assertEqual((), history.finding_summaries(found))
        self.assertIsNone(found.entries[0]["finding_id"])
        with self.assertRaises(ValidationError):
            history.finding_summary(found, "rfd_01ARZ3NDEKTSV4RRFFQ69G5F10")

    def test_a_finding_summary_validates_exactly_against_its_adjudication(self) -> None:
        found, _, _ = self.consumed_world()
        self.assertEqual([], self.problems())
        (finding,) = history.finding_summaries(found)
        for change in ({"severity": "HIGH"}, {"category": "Problem"}, {"disposition": "no_action_after_adjudication"},
                       {"semantic_surface": "another"}, {"summary": "a different claim"},
                       {"relation": "B_RECURRENCE"}, {"adjudication_digest": "9" * 64},
                       {"candidate_hash": "9" * 64}, {"source_report_digests": ("9" * 64,)}):
            with self.subTest(change=change):
                self.put_history(FINDINGS, replace(finding, **change))
                self.assertIn(history.PROBLEM_CONFLICT, self.codes())
        self.put_history(FINDINGS, finding)
        self.assertEqual([], self.problems())

    def test_a_summary_of_no_finding_or_of_an_unsettled_adjudication_fails(self) -> None:
        found, _, _ = self.consumed_world()
        (finding,) = history.finding_summaries(found)
        stray = "rfd_01ARZ3NDEKTSV4RRFFQ69G5F99"
        self.put_history(FINDINGS, replace(finding, finding_id=stray))
        self.assertTrue(any(stray in message for _, message in self.problems()))
        self.put_chain(chain(3))  # a fresh Run chain that never settled the adjudication
        for relative in (paths.gate_rel(RUN, 4), paths.gate_rel(RUN, 5)):
            (self.root / relative).unlink()
        self.assertIn(history.PROBLEM_MISSING, self.codes())

    def test_a_missing_source_report_fails(self) -> None:
        self.consumed_world()
        (_, digest, _), = ready_reports()
        (self.root / paths.report_rel(digest)).unlink()
        self.assertIn(history.PROBLEM_MISSING, self.codes())


# --------------------------------------------------------------------------- Repair summaries and causal material


class RepairSummaryTests(World):
    def test_the_repair_summary_binds_exactly_its_batch_and_result(self) -> None:
        found, batch, result, _, repair = self.repaired_world()
        self.assertEqual([], self.problems())
        self.assertEqual((batch.repair_batch_id, batch.source_review_run_id, batch.source_candidate_hash,
                          result.result_candidate_hash, batch.finding_ids, batch.semantic_surfaces, batch.strategy,
                          result.impact_class, result.coverage_check_digest, result.repair_identity,
                          result.repair_version),
                         (repair.repair_batch_id, repair.source_review_run_id, repair.source_candidate_hash,
                          repair.result_candidate_hash, repair.finding_ids, repair.semantic_surfaces, repair.strategy,
                          repair.impact_class, repair.coverage_check_digest, repair.repair_identity,
                          repair.repair_version))
        self.assertEqual((self.review.repair_batch_digest(BATCH), self.review.repair_result_digest(BATCH)),
                         (repair.batch_digest, repair.result_digest))
        material = repair.causal_material
        self.assertEqual(self.review.candidate_material_digest(CANDIDATE), material.source_candidate_material_digest)
        self.assertEqual(result.result_candidate_material_digest, material.result_candidate_material_digest)
        self.assertEqual(tuple(result.coverage_check["affected_set"]), material.affected_surfaces)
        self.assertEqual((found.review_context_hash, found.effective_policy_hash),
                         (material.review_context_hash, material.effective_policy_hash))
        self.assertEqual(history.REPAIR_RESULT_SUCCESSOR_ELIGIBLE, repair.durable_result)

    def test_a_repair_summary_mismatch_fails(self) -> None:
        _, _, _, _, repair = self.repaired_world()
        for change in ({"impact_class": "SHARED"}, {"result_candidate_hash": "9" * 64}, {"batch_digest": "9" * 64},
                       {"finding_ids": ("rfd_01ARZ3NDEKTSV4RRFFQ69G5F99",)}, {"coverage_covers_affected_set": False},
                       {"causal_material": replace(repair.causal_material, reverification_digest="9" * 64)}):
            with self.subTest(change=str(change)[:40]):
                self.put_history(REPAIRS, replace(repair, **change))
                self.assertIn(history.PROBLEM_CONFLICT, self.codes())

    def test_a_repaired_run_needs_its_repair_result(self) -> None:
        self.repaired_world()
        (self.root / paths.repair_result_rel(BATCH)).unlink()
        self.assertIn(history.PROBLEM_MISSING, self.codes())

    def test_the_builder_refuses_a_batch_result_or_adjudication_of_another_linkage(self) -> None:
        found = adjudication_fixture()
        digest = serialize.digest(found.to_record())
        batch = batch_fixture(found, digest)
        result = result_fixture(batch)
        other = ready_adjudication()
        for name, call in {
            "another adjudication": lambda: history.repair_summary(other, batch, result,
                                                                   source_candidate_material_digest="9" * 64),
            "another batch": lambda: history.repair_summary(
                found, replace(batch, repair_batch_id="rrb_01ARZ3NDEKTSV4RRFFQ69G5FAC"), result,
                source_candidate_material_digest="9" * 64),
            "not successor eligible": lambda: history.repair_summary(
                found, batch, replace(result, successor_eligible=False), source_candidate_material_digest="9" * 64),
        }.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                call()


# --------------------------------------------------------------------------- relations and causal status


class RelationTests(World):
    def finding_endpoint(self) -> tuple[history.FindingSummary, history.Endpoint]:
        found, _, _ = self.consumed_world()
        (finding,) = history.finding_summaries(found)
        return finding, history.endpoint(history.ENDPOINT_FINDING, finding.finding_id, basis=history.BASIS_HISTORY,
                                         digest=serialize.digest(finding.to_record()))

    def test_causal_status_round_trips_and_only_supported_is_confirmed(self) -> None:
        finding, source = self.finding_endpoint()
        target = history.endpoint(history.ENDPOINT_RUN, RUN, basis=history.BASIS_SOURCE,
                                  digest=self.review.gate_chain(RUN).digests[0])
        built = {}
        for status, evidence in ((history.CAUSAL_SUPPORTED, ["3" * 64]), (history.CAUSAL_UNRESOLVED, []),
                                 (history.CAUSAL_INSUFFICIENT_EVIDENCE, [])):
            found = history.relation(RELATION, history.RELATION_DOWNSTREAM_ESCAPE, source, target, status=status,
                                     rationale="found after the prior completion", supporting_evidence_digests=evidence)
            again = history.Relation.from_record(serialize.canonical_data(found.to_record()), status)
            self.assertEqual(status, again.status, "unknown stays unknown")
            built[status] = again
        self.assertEqual((built[history.CAUSAL_SUPPORTED],), history.confirmed_relations(built.values()))
        with self.assertRaises(ValidationError):
            history.relation(RELATION, history.RELATION_REPAIR_INDUCED, source,
                             history.endpoint(history.ENDPOINT_REPAIR, BATCH, basis=history.BASIS_SOURCE,
                                              digest="9" * 64),
                             status=history.CAUSAL_SUPPORTED, rationale="the repair broke it", semantic_surface="parser")

    def test_relation_endpoints_must_exist_as_the_exact_records_they_bind(self) -> None:
        finding, source = self.finding_endpoint()
        run_target = history.endpoint(history.ENDPOINT_RUN, RUN, basis=history.BASIS_HISTORY,
                                      digest=self.review.history_digest(RUNS, RUN))
        found = history.relation(RELATION, history.RELATION_DOWNSTREAM_ESCAPE, source, run_target,
                                 status=history.CAUSAL_UNRESOLVED, rationale="a later defect may trace back here")
        self.put_history(RELATIONS, found)
        self.assertEqual([], self.problems())
        cases = {
            "unknown history run": replace(run_target, id=OTHER_RUN),
            "wrong history digest": replace(run_target, digest="9" * 64),
            "source basis of an unknown run": replace(run_target, id=OTHER_RUN, basis=history.BASIS_SOURCE),
        }
        for name, target in cases.items():
            with self.subTest(name):
                self.put_history(RELATIONS, replace(found, target=target))
                self.assertTrue(self.problems())
        self.put_history(RELATIONS, replace(found, target=replace(run_target, basis=history.BASIS_SOURCE,
                                                                  digest=self.review.gate_chain(RUN).digests[2])))
        self.assertEqual([], self.problems(), "a source-basis Run endpoint names one immutable generation")
        source_finding = replace(source, basis=history.BASIS_SOURCE, digest=self.review.adjudication_digest(RUN))
        self.put_history(RELATIONS, replace(found, source=source_finding))
        self.assertEqual([], self.problems(), "a source-basis Finding is bound by the adjudication holding it")

    def test_one_logical_relation_is_recorded_once(self) -> None:
        finding, source = self.finding_endpoint()
        target = history.endpoint(history.ENDPOINT_RUN, RUN, basis=history.BASIS_HISTORY,
                                  digest=self.review.history_digest(RUNS, RUN))
        first = history.relation(RELATION, history.RELATION_DOWNSTREAM_ESCAPE, source, target,
                                 status=history.CAUSAL_UNRESOLVED, rationale="first")
        self.put_history(RELATIONS, first)
        self.put_history(RELATIONS, replace(first, relation_id=OTHER_RELATION, rationale="second"))
        problems = self.problems()
        self.assertEqual([history.PROBLEM_CONFLICT], [code for code, _ in problems])
        self.assertIn(RELATION, problems[0][1])

    def test_future_work_link_is_provenance_shaped_and_checks_the_work_only_with_a_project_view(self) -> None:
        finding, _ = self.finding_endpoint()
        link = history.future_work_link(RELATION, finding, WORK, status=history.CAUSAL_SUPPORTED,
                                        rationale="a later Work was created for this Improvement",
                                        supporting_evidence_digests=[serialize.digest(finding.to_record())])
        self.assertEqual((history.ENDPOINT_FINDING, history.ENDPOINT_WORK), (link.source.kind, link.target.kind))
        self.put_history(RELATIONS, link)
        self.assertEqual([], self.problems(work_ids=None))
        self.assertEqual([], self.problems(work_ids={WORK}))
        self.assertEqual([history.PROBLEM_MISSING], self.codes(work_ids=set()))
        (self.root / paths.history_finding_rel(finding.finding_id)).unlink()
        self.assertIn(history.PROBLEM_MISSING, self.codes(work_ids={WORK}))

    def test_a_later_relation_never_rewrites_the_finding_it_points_at(self) -> None:
        finding, source = self.finding_endpoint()
        before = (self.root / paths.history_finding_rel(finding.finding_id)).read_bytes()
        self.put_history(RELATIONS, history.future_work_link(
            RELATION, finding, WORK, status=history.CAUSAL_UNRESOLVED, rationale="maybe valuable later"))
        self.assertEqual(before, (self.root / paths.history_finding_rel(finding.finding_id)).read_bytes())
        # RB4-OWNER (GAP-C / P-5): the one relation field binds only the relations the SAME G4 made knowable from
        # this Finding - the canonical record the owner derives that G4's relation paths from. A later relation is
        # never added to it: the file above is unchanged, and its relation_ids stay empty.
        self.assertEqual(["relation_ids"], [name for name in history.FINDING_SUMMARY_FIELDS if name.startswith("relation_")])
        self.assertEqual((), history.FindingSummary.from_record(
            serialize.parse((self.root / paths.history_finding_rel(finding.finding_id)).read_text(encoding="utf-8"),
                            "the Finding summary"), "the Finding summary").relation_ids)


# --------------------------------------------------------------------------- Human Decision Evidence


class HumanDecisionTests(World):
    def test_evidence_points_only_at_a_real_human_part_of_a_settled_adjudication(self) -> None:
        found, _, _ = self.human_world()
        evidence = human_decision_fixture(found, changed=False)
        self.put_history(DECISIONS, evidence)
        self.assertEqual([], self.problems())
        self.assertEqual((found.review_run_id, found.candidate_hash),
                         (evidence.affected_review_run_id, evidence.affected_candidate_hash))
        for change in ({"affected_candidate_hash": "9" * 64}, {"affected_adjudication_digest": "9" * 64},
                       {"affected_entries": ({**evidence.affected_entries[0], "claim_index": 5},)},
                       {"affected_coverage_gaps": ({"task_id": TASK_A, "surface": "nothing"},)}):
            with self.subTest(change=str(change)[:40]):
                self.put_history(DECISIONS, replace(evidence, **change))
                self.assertIn(history.PROBLEM_CONFLICT, self.codes())
        self.put_history(DECISIONS, replace(evidence, affected_review_run_id=OTHER_RUN))
        self.assertIn(history.PROBLEM_MISSING, self.codes())

    def test_the_builder_refuses_a_reference_that_is_not_human(self) -> None:
        human = human_adjudication()
        ready = ready_adjudication()
        common = dict(decision_id=CALLER_DECISION, decision_disposition=history.DECISION_REQUIREMENT_CONFIRMED,
                      question_summary="q?", decision_summary="d.", authority_identity="registry.md#rules/limits",
                      action_class=history.ACTION_RESUME_CONFIRMED, source_digests=["4" * 64])
        for name, call in {
            "an Improvement entry of an authorization-ready adjudication": lambda: history.human_decision_evidence(
                DECISION, ready, affected_entries=[ready.entries[0]], **common),
            "no reference": lambda: history.human_decision_evidence(DECISION, human, affected_entries=[], **common),
            "an unknown gap": lambda: history.human_decision_evidence(
                DECISION, human, affected_entries=[], affected_coverage_gaps=[{"task_id": TASK_A, "surface": "x"}],
                **common),
        }.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                call()

    def test_one_evidence_record_per_affected_run_named_by_its_reserved_identity(self) -> None:
        found, _, _ = self.human_world()
        first = human_decision_fixture(found, changed=False)
        self.put_history(DECISIONS, first)
        self.assertEqual([], self.problems())
        self.assertEqual(paths.history_decision_rel(DECISION), paths.history_rel(DECISIONS, first.review_decision_id))
        self.assertNotEqual(first.review_decision_id, first.decision_id, "the caller's decision_id is only a field")
        self.assertEqual(f"review-decision:{RUN}", history.review_decision_key(first.affected_review_run_id))
        self.put_history(DECISIONS, human_decision_fixture(found, changed=False, review_decision_id=OTHER_DECISION))
        problems = self.problems()
        self.assertEqual([history.PROBLEM_CONFLICT], [code for code, _ in problems])
        self.assertIn(RUN, problems[0][1])

    def test_evidence_is_not_requirement_authority(self) -> None:
        names = set(history.HUMAN_DECISION_FIELDS)
        self.assertNotIn("requirement", names)
        self.assertIn("authority_identity", names, "it names the authority it affected, never carries it")
        self.assertFalse(hasattr(history, "requirement_of"))


# --------------------------------------------------------------------------- readiness, no backfill, RB5


class ReadinessTests(World):
    CONTRACT = history.HISTORY_CONTRACT

    def test_a_pre_p5_run_crosses_every_boundary_with_no_history(self) -> None:
        self.put_chain(chain(4))
        for boundary in history.BOUNDARIES:
            with self.subTest(boundary=boundary):
                self.assertEqual([], history.readiness_problems(self.review, RUN, boundary, history_contract=None))
                history.require_history_ready(self.review, RUN, boundary, history_contract=None)
        self.assertEqual(history.HISTORY_NOT_REQUIRED, history.history_status([], history_contract=None))

    def test_a_history_directory_never_makes_a_run_p5(self) -> None:
        _, _, summary = self.human_world()
        self.put_history(RUNS, replace(summary, gate_digest="9" * 64))
        for boundary in history.BOUNDARIES:
            history.require_history_ready(self.review, RUN, boundary, history_contract=None)

    def test_missing_required_history_blocks_the_p5_transition(self) -> None:
        self.put_chain(chain(4))
        found = human_adjudication()
        self.put_adjudication(found)
        cases = {
            history.BOUNDARY_HUMAN_WAIT: {},
            history.BOUNDARY_REPAIRED: {},
            history.BOUNDARY_CONSUMPTION: {},
            history.BOUNDARY_SUCCESSOR_LAUNCH: {"review_decision_ids": (DECISION,)},
        }
        for boundary, extra in cases.items():
            with self.subTest(boundary=boundary):
                with self.assertRaises(StopError) as raised:
                    history.require_history_ready(self.review, RUN, boundary, history_contract=self.CONTRACT, **extra)
                self.assertEqual(history.CODE_HISTORY_MISSING, raised.exception.code)
        with self.assertRaises(StopError) as raised:
            history.require_history_ready(self.review, RUN, history.BOUNDARY_SUCCESSOR_LAUNCH,
                                          history_contract=self.CONTRACT)
        self.assertEqual(history.CODE_HISTORY_MISSING, raised.exception.code)

    def test_g4_needs_every_finding_summary(self) -> None:
        found, _, _ = self.consumed_world()
        history.require_history_ready(self.review, RUN, history.BOUNDARY_FINDINGS, history_contract=self.CONTRACT)
        (self.root / paths.history_finding_rel(str(found.findings[0]["finding_id"]))).unlink()
        with self.assertRaises(StopError) as raised:
            history.require_history_ready(self.review, RUN, history.BOUNDARY_FINDINGS, history_contract=self.CONTRACT)
        self.assertEqual(history.CODE_HISTORY_MISSING, raised.exception.code)

    def test_each_complete_boundary_passes_and_an_invalid_one_is_refused(self) -> None:
        _, _, summary = self.human_world()
        history.require_history_ready(self.review, RUN, history.BOUNDARY_HUMAN_WAIT, history_contract=self.CONTRACT)
        self.assertEqual(history.HISTORY_COMPLETE, history.history_status(
            history.readiness_problems(self.review, RUN, history.BOUNDARY_HUMAN_WAIT, history_contract=self.CONTRACT),
            history_contract=self.CONTRACT))
        self.put_history(RUNS, replace(summary, evidence_digest="9" * 64))
        with self.assertRaises(StopError) as raised:
            history.require_history_ready(self.review, RUN, history.BOUNDARY_HUMAN_WAIT, history_contract=self.CONTRACT)
        self.assertEqual(history.CODE_HISTORY_INVALID, raised.exception.code)
        with self.assertRaises(StopError) as raised:
            history.require_history_ready(self.review, RUN, history.BOUNDARY_CONSUMPTION, history_contract=self.CONTRACT)
        self.assertEqual(history.CODE_HISTORY_INVALID, raised.exception.code, "a human_wait summary is not consumed")

    def test_the_consumption_and_repaired_boundaries(self) -> None:
        self.consumed_world()
        history.require_history_ready(self.review, RUN, history.BOUNDARY_CONSUMPTION, history_contract=self.CONTRACT,
                                      consumption_id=CONSUMPTION)
        with self.assertRaises(StopError):
            history.require_history_ready(self.review, RUN, history.BOUNDARY_CONSUMPTION,
                                          history_contract=self.CONTRACT, consumption_id=OTHER_CONSUMPTION)
        self.reset()
        self.repaired_world()
        history.require_history_ready(self.review, RUN, history.BOUNDARY_REPAIRED, history_contract=self.CONTRACT)
        (self.root / paths.history_repair_rel(BATCH)).unlink()
        with self.assertRaises(StopError) as raised:
            history.require_history_ready(self.review, RUN, history.BOUNDARY_REPAIRED, history_contract=self.CONTRACT)
        self.assertEqual(history.CODE_HISTORY_MISSING, raised.exception.code)

    def test_the_successor_launch_boundary_reads_the_named_evidence(self) -> None:
        found, _, _ = self.human_world()
        evidence = human_decision_fixture(found, changed=False)
        self.put_history(DECISIONS, evidence)
        history.require_history_ready(self.review, OTHER_RUN, history.BOUNDARY_SUCCESSOR_LAUNCH,
                                      history_contract=self.CONTRACT, review_decision_ids=(DECISION,))

    def test_an_unknown_history_contract_is_refused_never_read_as_none(self) -> None:
        self.put_chain(chain(4))
        with self.assertRaises(StopError) as raised:
            history.require_history_ready(self.review, RUN, history.BOUNDARY_HUMAN_WAIT,
                                          history_contract="review-v1-history-v9")
        self.assertEqual(history.CODE_HISTORY_INVALID, raised.exception.code)
        with self.assertRaises(ValueError):
            history.readiness_problems(self.review, RUN, "g7", history_contract=self.CONTRACT)

    def test_the_envelope_binding_is_explicit(self) -> None:
        self.assertIsNone(history.history_contract_of_envelope({"schema": "review-p4-discovery-request"}))
        self.assertIsNone(history.history_contract_of_envelope(None))
        self.assertEqual(history.HISTORY_CONTRACT, history.history_contract_of_envelope(
            {history.HISTORY_CONTRACT_KEY: history.HISTORY_CONTRACT}))
        with self.assertRaises(ValidationError):
            history.history_contract_of_envelope({history.HISTORY_CONTRACT_KEY: "review-v1-history-v2"})


class Rb5ReferenceTests(World):
    def test_a_pre_p5_run_carries_its_p1_references_and_no_history(self) -> None:
        found = ready_adjudication()
        self.put_adjudication(found)
        generations = chain(5, adjudication=found, seal_at=5)
        self.put_chain(generations)
        self.put(paths.receipt_rel(RECEIPT), receipt().to_record())
        self.put(paths.consumption_rel(CONSUMPTION), consumption().to_record())
        before = self.tree()
        reference = history.rb5_reference(self.review, RUN, history_contract=None)
        self.assertEqual(before, self.tree(), "no backfill: nothing is written")
        self.assertEqual((history.HISTORY_NOT_REQUIRED, None, None, RECEIPT, CONSUMPTION, 0, (), ()),
                         (reference.history_status, reference.run_summary_digest, reference.durable_disposition,
                          reference.receipt_id, reference.consumption_id, reference.unresolved_obligations,
                          reference.finding_dispositions, reference.human_decision_evidence_ids))

    def test_a_complete_p5_run_exposes_its_validated_history_references(self) -> None:
        found, _, _ = self.consumed_world()
        reference = history.rb5_reference(self.review, RUN, history_contract=history.HISTORY_CONTRACT)
        self.assertEqual(history.HISTORY_COMPLETE, reference.history_status)
        self.assertEqual(self.review.history_digest(RUNS, RUN), reference.run_summary_digest)
        self.assertEqual(history.DISPOSITION_CONSUMED, reference.durable_disposition)
        self.assertEqual(((str(found.findings[0]["finding_id"]), "retained_history_only"),),
                         reference.finding_dispositions)
        record = reference.to_record()
        self.assertEqual(serialize.canonical_data(record), record)
        self.assertNotIn("achieved", " ".join(record), "RB5 decides achievement, not this projection")

    def test_an_incomplete_p5_run_exposes_no_unvalidated_history(self) -> None:
        found, _, summary = self.consumed_world()
        self.put_history(RUNS, replace(summary, evidence_digest="9" * 64))
        reference = history.rb5_reference(self.review, RUN, history_contract=history.HISTORY_CONTRACT)
        self.assertEqual((history.HISTORY_INCOMPLETE, None, None, ()),
                         (reference.history_status, reference.run_summary_digest, reference.durable_disposition,
                          reference.finding_dispositions))
        self.assertEqual((RECEIPT, CONSUMPTION), (reference.receipt_id, reference.consumption_id))

    def test_the_human_decisions_of_the_run_are_referenced(self) -> None:
        found, _, _ = self.human_world()
        evidence = human_decision_fixture(found, changed=False)
        self.put_history(DECISIONS, evidence)
        reference = history.rb5_reference(self.review, RUN, history_contract=history.HISTORY_CONTRACT)
        self.assertEqual((history.HISTORY_COMPLETE, (DECISION,)),
                         (reference.history_status, reference.human_decision_evidence_ids))


class ReplayStabilityTests(unittest.TestCase):
    """§28.27 (core part): the same immutable sources always build the same history bytes and keys."""

    def build(self) -> list[bytes]:
        found = adjudication_fixture()
        batch = batch_fixture(found, serialize.digest(found.to_record()))
        terminal = chain(6, adjudication=found)[-1]
        built = [
            history.run_summary(terminal, durable_disposition=history.DISPOSITION_REPAIRED, candidate_generation=1,
                                adjudication=found, repair_batch_id=BATCH),
            history.repair_summary(found, batch, result_fixture(batch), source_candidate_material_digest="9" * 64),
            *history.finding_summaries(found),
            human_decision_fixture(),
        ]
        return [serialize.canonical_bytes(item.to_record()) for item in built]

    def test_a_rebuild_is_byte_identical_and_reserves_the_same_keys(self) -> None:
        self.assertEqual(self.build(), self.build())
        self.assertEqual(history.review_relation_key(RUN, 3), history.review_relation_key(RUN, 3))
        self.assertEqual(history.review_decision_key(RUN), history.review_decision_key(RUN))


class PurityTests(World):
    def test_validation_readiness_and_projection_write_nothing(self) -> None:
        self.repaired_world()
        before = self.tree()
        history.history_problems(self.review, work_ids={WORK})
        for boundary in history.BOUNDARIES:
            history.readiness_problems(self.review, RUN, boundary, history_contract=history.HISTORY_CONTRACT,
                                       review_decision_ids=(DECISION,))
        history.rb5_reference(self.review, RUN, history_contract=history.HISTORY_CONTRACT)
        self.assertEqual(before, self.tree())


if __name__ == "__main__":
    unittest.main()
