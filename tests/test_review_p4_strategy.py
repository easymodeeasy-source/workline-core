"""P4 §27.34: A/B/C from explicit linkage only, and the STRATEGY_CHANGE trigger."""

from __future__ import annotations

import unittest

from workline.errors import StopError
from workline.review import p4, records, serialize

from test_review_p4_adjudication import (
    BATCH, PRED, TASK_A, TASK_B, adjudicate, bound, disposition, report, returned,
)

PRIOR_FINDING = "rfd_01ARZ3NDEKTSV4RRFFQ69G5F10"
CAUSAL = "7" * 64


def prior_cycle(bc_history=(), surface: str = "parser") -> p4.PriorCycle:
    """A predecessor Run whose one blocking Finding on ``surface`` was repaired by :data:`BATCH`."""
    reports = bound(report(TASK_A, "correctness", [("HIGH", "x", "earlier claim")]))
    found = adjudicate(reports, returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity="HIGH",
                                                     semantic_surface=surface)))
    record = found.to_record()
    record["review_run_id"] = PRED
    found = records.P4Adjudication.from_record(serialize.canonical_data(record), "prior")
    batch = p4.repair_batch(found, "9" * 64, repair_batch_id=BATCH, allowed_result_surface=["src/a.py"],
                            repair_purpose="fix it", strategy_change_class=None)
    result = records.P4RepairResult(
        repair_batch_id=BATCH, review_kind=found.review_kind, target_identity=found.target_identity,
        operation_identity=found.operation_identity, review_contract=found.review_contract,
        source_review_run_id=PRED, source_candidate_hash=found.candidate_hash, source_candidate_generation=1,
        result_candidate_hash="b" * 64, result_candidate_generation=2, result_candidate_material_digest="c" * 64,
        repair_task_id="rtk_01ARZ3NDEKTSV4RRFFQ69G5FA7", repair_identity="repairer", repair_version="v1",
        repaired_surface=("src/a.py",), impact_class=p4.IMPACT_LOCAL,
        coverage_check={}, coverage_check_digest="0" * 64, evidence_decisions=(),
        reverification={"required": [], "completed": [], "residual": 0}, reverification_digest="0" * 64,
        causal_summary="changed the parser", successor_eligible=True,
    )
    history = tuple(bc_history) + (p4.bc_surfaces(found),)
    return p4.PriorCycle(PRED, found, "8" * 64, batch, result, "6" * 64, history)


class RelationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reports = bound(report(TASK_B, "security", [("HIGH", "y", "after repair")]))

    def test_after_repair_timing_alone_is_a_new(self) -> None:
        found = adjudicate(self.reports, returned(disposition(TASK_B, 0, p4.OUTCOME_PROBLEM)), prior=prior_cycle(),
                           generation=2)
        self.assertEqual(p4.RELATION_A_NEW, found.findings[0]["relation"])
        self.assertEqual(PRED, found.prior["predecessor_review_run_id"])

    def test_supported_recurrence_is_b_with_links(self) -> None:
        found = adjudicate(self.reports, returned(disposition(
            TASK_B, 0, p4.OUTCOME_PROBLEM, relation=p4.RELATION_B_RECURRENCE, linked_finding_ids=(PRIOR_FINDING,),
            linked_repair_batch_ids=(BATCH,), causal_evidence_digest=CAUSAL,
        )), prior=prior_cycle(), generation=2)
        finding = found.findings[0]
        self.assertEqual(p4.RELATION_B_RECURRENCE, finding["relation"])
        self.assertEqual([PRIOR_FINDING], finding["linked_finding_ids"])
        self.assertEqual([BATCH], finding["linked_repair_batch_ids"])

    def test_b_without_positive_linkage_is_refused(self) -> None:
        for fields in (
            dict(linked_finding_ids=(), linked_repair_batch_ids=(BATCH,), causal_evidence_digest=CAUSAL),
            dict(linked_finding_ids=(PRIOR_FINDING,), linked_repair_batch_ids=(), causal_evidence_digest=CAUSAL),
            dict(linked_finding_ids=(PRIOR_FINDING,), linked_repair_batch_ids=(BATCH,), causal_evidence_digest=None),
            dict(linked_finding_ids=("rfd_01ARZ3NDEKTSV4RRFFQ69G5F99",), linked_repair_batch_ids=(BATCH,),
                 causal_evidence_digest=CAUSAL),
        ):
            with self.subTest(fields=fields), self.assertRaises(StopError):
                adjudicate(self.reports, returned(disposition(
                    TASK_B, 0, p4.OUTCOME_PROBLEM, relation=p4.RELATION_B_RECURRENCE, **fields,
                )), prior=prior_cycle(), generation=2)

    def test_b_on_another_responsibility_is_refused(self) -> None:
        with self.assertRaises(StopError):
            adjudicate(self.reports, returned(disposition(
                TASK_B, 0, p4.OUTCOME_PROBLEM, relation=p4.RELATION_B_RECURRENCE, semantic_surface="writer",
                linked_finding_ids=(PRIOR_FINDING,), linked_repair_batch_ids=(BATCH,), causal_evidence_digest=CAUSAL,
            )), prior=prior_cycle(), generation=2)

    def test_supported_repair_induced_is_c_with_causal_digest(self) -> None:
        found = adjudicate(self.reports, returned(disposition(
            TASK_B, 0, p4.OUTCOME_PROBLEM, severity="LOW", relation=p4.RELATION_C_REPAIR_INDUCED,
            linked_repair_batch_ids=(BATCH,), causal_evidence_digest=CAUSAL,
        )), prior=prior_cycle(), generation=2)
        finding = found.findings[0]
        self.assertEqual(p4.RELATION_C_REPAIR_INDUCED, finding["relation"])
        self.assertEqual(CAUSAL, finding["causal_evidence_digest"])
        self.assertTrue(finding["blocking"], "an unresolved repair-induced Problem blocks convergence")

    def test_c_without_causal_digest_or_without_a_prior_repair_is_refused(self) -> None:
        with self.assertRaises(StopError):
            adjudicate(self.reports, returned(disposition(
                TASK_B, 0, p4.OUTCOME_PROBLEM, relation=p4.RELATION_C_REPAIR_INDUCED, linked_repair_batch_ids=(BATCH,),
            )), prior=prior_cycle(), generation=2)
        with self.assertRaises(StopError):
            adjudicate(self.reports, returned(disposition(
                TASK_B, 0, p4.OUTCOME_PROBLEM, relation=p4.RELATION_C_REPAIR_INDUCED, linked_repair_batch_ids=(BATCH,),
                causal_evidence_digest=CAUSAL,
            )))

    def test_unknown_causality_stays_a_new(self) -> None:
        with self.assertRaises(StopError):
            adjudicate(self.reports, returned(disposition(
                TASK_B, 0, p4.OUTCOME_PROBLEM, linked_repair_batch_ids=(BATCH,),
            )), prior=prior_cycle(), generation=2)


class StrategyTests(unittest.TestCase):
    def test_consecutive_same_surface_pairs_require_strategy_change(self) -> None:
        for pair in ("BB", "CC", "BC", "CB"):
            with self.subTest(pair=pair):
                self.assertTrue(p4.strategy_change_required((frozenset({"parser"}),), frozenset({"parser"})))

    def test_a_different_surface_does_not_count(self) -> None:
        self.assertFalse(p4.strategy_change_required((frozenset({"parser"}),), frozenset({"writer"})))

    def test_only_the_immediately_preceding_adjudication_is_consecutive(self) -> None:
        self.assertFalse(p4.strategy_change_required((frozenset({"parser"}), frozenset()), frozenset({"parser"})))
        self.assertFalse(p4.strategy_change_required((), frozenset({"parser"})))

    def _second_failure(self, strategy_class):
        prior = prior_cycle(bc_history=())
        # the predecessor itself carried a supported B on 'parser'
        prior = p4.PriorCycle(prior.review_run_id, prior.adjudication, prior.adjudication_digest, prior.repair_batch,
                              prior.repair_result, prior.repair_result_digest, (frozenset({"parser"}),))
        reports = bound(report(TASK_B, "security", [("HIGH", "y", "still broken")]))
        return adjudicate(reports, returned(disposition(
            TASK_B, 0, p4.OUTCOME_PROBLEM, relation=p4.RELATION_B_RECURRENCE, linked_finding_ids=(PRIOR_FINDING,),
            linked_repair_batch_ids=(BATCH,), causal_evidence_digest=CAUSAL,
        ), strategy_class=strategy_class), prior=prior, generation=3)

    def test_strategy_change_requirement_blocks_an_ordinary_unchanged_repair(self) -> None:
        with self.assertRaises(StopError) as raised:
            self._second_failure(None)
        self.assertEqual(p4.CODE_STRATEGY_CHANGE_REQUIRED, raised.exception.code)
        found = self._second_failure("repair_shared_responsibility")
        self.assertTrue(found.obligations["strategy_change_required"])
        batch = p4.repair_batch(found, "9" * 64, repair_batch_id="rrb_01ARZ3NDEKTSV4RRFFQ69G5FAC",
                                allowed_result_surface=["src/a.py"], repair_purpose="redo",
                                strategy_change_class="repair_shared_responsibility")
        self.assertEqual(p4.STRATEGY_CHANGE, batch.strategy)
        record = batch.to_record()
        record["strategy"] = p4.STRATEGY_ORDINARY
        record["strategy_change_class"] = None
        with self.assertRaises(Exception):
            records.P4RepairBatch.from_record(serialize.canonical_data(record), "tampered")

    def test_operational_failures_never_reach_the_recurrence_count(self) -> None:
        # A timeout / rate limit / crash raises before any settlement: nothing is adjudicated, so the
        # cycle's B/C history is exactly the adjudications that were settled.
        prior = prior_cycle()
        self.assertEqual(1, len(prior.bc_history))
        self.assertEqual(frozenset(), prior.bc_history[0])


if __name__ == "__main__":
    unittest.main()
