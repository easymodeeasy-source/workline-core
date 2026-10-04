"""P4 §27.30: adjudication - the §12.4 order, normalized Findings, merge by repair identity, H-4 blocking."""

from __future__ import annotations

import unittest

from workline.errors import StopError, ValidationError
from workline.review import p4, records, serialize

RUN = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV"
PRED = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAP"
TASK_A = "rtk_01ARZ3NDEKTSV4RRFFQ69G5FA1"
TASK_B = "rtk_01ARZ3NDEKTSV4RRFFQ69G5FA2"
ADJ_TASK = "rtk_01ARZ3NDEKTSV4RRFFQ69G5FA9"
BATCH = "rrb_01ARZ3NDEKTSV4RRFFQ69G5FAB"
CANDIDATE = "a" * 64
DIGEST = "c" * 64


def report(task_id: str, slot: str, claims: list[tuple[str, str, str]], not_inspected: tuple[str, ...] = ()) -> dict:
    return serialize.canonical_data({
        "schema": records.SCHEMA_P4_REPORT, "version": records.VERSION, "review_kind": "work-result-v1",
        "review_contract": p4.WORK_CONTRACT, "task_id": task_id, "task_slot": p4.discovery_slot(slot),
        "reviewer_identity": "reviewer", "reviewer_version": "v1", "status": "completed",
        "claims": [{"severity": s, "code": c, "message": m} for s, c, m in claims],
        "coverage": {"viewpoint": slot, "inspected": ["result"], "checked": ["behaviour"], "evidence_ids": [],
                     "not_inspected": list(not_inspected)},
    })


def bound(*items: dict) -> list[tuple[str, str, dict]]:
    return [(item["task_id"], serialize.digest(item), item) for item in items]


DESCRIPTOR = {"task_id": ADJ_TASK, "reviewer_identity": "adjudicator", "reviewer_version": "v1"}


def disposition(task_id: str, index: int, outcome: str, **fields: object) -> p4.P4ClaimDisposition:
    flags = {
        p4.OUTCOME_UNSUPPORTED: (False, False, False, False),
        p4.OUTCOME_HUMAN: (True, True, False, False),
        p4.OUTCOME_PROBLEM: (True, False, True, False),
        p4.OUTCOME_IMPROVEMENT: (True, False, False, True),
        p4.OUTCOME_DISMISSED: (True, False, False, False),
    }[outcome]
    base: dict = dict(
        task_id=task_id, claim_index=index, supported=flags[0], requirement_decision_required=flags[1],
        fails_requirement=flags[2], better_alternative=flags[3], outcome=outcome, reason="adjudicated",
    )
    if outcome in (p4.OUTCOME_PROBLEM, p4.OUTCOME_IMPROVEMENT):
        base.update(severity="MID", statement="the result is wrong", semantic_surface="parser",
                    repair_identity="fix-parser",
                    disposition=p4.DISPOSITION_REPAIR_REQUIRED if outcome == p4.OUTCOME_PROBLEM
                    else p4.DISPOSITION_RETAINED_HISTORY_ONLY)
    base.update(fields)
    return p4.P4ClaimDisposition(**base)  # type: ignore[arg-type]


def returned(*dispositions: p4.P4ClaimDisposition, objective_holds: bool = True, gaps=(), purpose="repair it",
             strategy_class=None) -> p4.P4AdjudicationReturn:
    return p4.P4AdjudicationReturn(
        task_id=ADJ_TASK, adjudicator_identity="adjudicator", adjudicator_version="v1",
        objective_holds=objective_holds, dispositions=tuple(dispositions), coverage_gaps=tuple(gaps),
        repair_purpose=purpose, strategy_change_class=strategy_class,
    )


def gate(**overrides: object) -> records.GateGeneration:
    values: dict = dict(
        review_run_id=RUN, generation=3, previous_generation=2, previous_digest="d" * 64, review_kind="work-result-v1",
        target_identity="w_01ARZ3NDEKTSV4RRFFQ69G5FAV", operation_identity="start:" + "e" * 64,
        candidate_hash=CANDIDATE, review_context_hash="b" * 64, effective_policy_hash=p4.policy_hash(),
        evidence_digest="f" * 64, coverage_digest="f" * 64, raw_report_set_digest="f" * 64,
        adjudication_digest="f" * 64, obligation_digest="f" * 64, accepted_tasks=(), settled_tasks=(),
        status=records.GATE_STATUS_OPEN, receipt_id=None, authorized_operation_stage=None,
    )
    values.update(overrides)
    return records.GateGeneration(**values)


def finding_ids(count: int) -> list[str]:
    return [f"rfd_01ARZ3NDEKTSV4RRFFQ69G5F{index:02d}" for index in range(10, 10 + count)]


def adjudicate(reports, ret, prior=None, generation=1) -> records.P4Adjudication:
    normalized = p4.normalize_adjudication(ret, DESCRIPTOR, reports, prior)
    return p4.adjudication(
        normalized, finding_ids(len(normalized.drafts)), review_run_id=RUN, gate_record=gate(),
        candidate_generation=generation, review_contract=p4.WORK_CONTRACT, descriptor=DESCRIPTOR, reports=reports,
        prior=prior,
    )


class OrderTests(unittest.TestCase):
    """§12.4 steps 1-5 in order, and a return that skips a step is refused."""

    def setUp(self) -> None:
        self.reports = bound(report(TASK_A, "correctness", [("HIGH", "x", "claim one")]))

    def test_unsupported_creates_no_finding_and_no_obligation(self) -> None:
        found = adjudicate(self.reports, returned(disposition(TASK_A, 0, p4.OUTCOME_UNSUPPORTED)))
        self.assertEqual((), found.findings)
        self.assertEqual(p4.AUTHORIZATION_READY, found.outcome)
        self.assertIsNone(found.entries[0]["finding_id"])

    def test_requirement_ambiguity_is_human_not_a_guessed_problem(self) -> None:
        found = adjudicate(self.reports, returned(disposition(TASK_A, 0, p4.OUTCOME_HUMAN)))
        self.assertEqual(p4.HUMAN_WAIT, found.outcome)
        self.assertEqual(1, found.obligations["human"])
        converted = disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, requirement_decision_required=True)
        with self.assertRaises(StopError) as raised:
            adjudicate(self.reports, returned(converted))
        self.assertEqual(p4.CODE_ADJUDICATION_INVALID, raised.exception.code)

    def test_decided_requirement_failure_is_a_problem(self) -> None:
        found = adjudicate(self.reports, returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM)))
        self.assertEqual([p4.OUTCOME_PROBLEM], [f["category"] for f in found.findings])
        self.assertEqual(p4.REPAIR_REQUIRED, found.outcome)

    def test_better_alternative_without_failure_is_an_improvement(self) -> None:
        found = adjudicate(self.reports, returned(disposition(TASK_A, 0, p4.OUTCOME_IMPROVEMENT, severity="HIGH")))
        self.assertEqual([p4.OUTCOME_IMPROVEMENT], [f["category"] for f in found.findings])
        self.assertEqual(p4.AUTHORIZATION_READY, found.outcome)

    def test_otherwise_dismissed_non_actionable(self) -> None:
        found = adjudicate(self.reports, returned(disposition(TASK_A, 0, p4.OUTCOME_DISMISSED)))
        self.assertEqual((), found.findings)
        self.assertEqual(p4.OUTCOME_DISMISSED, found.entries[0]["outcome"])

    def test_unsupported_claim_classified_as_finding_is_refused(self) -> None:
        bad = disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, supported=False)
        with self.assertRaises(StopError) as raised:
            adjudicate(self.reports, returned(bad))
        self.assertEqual(p4.CODE_ADJUDICATION_INVALID, raised.exception.code)

    def test_non_finding_outcome_with_finding_material_is_refused(self) -> None:
        bad = disposition(TASK_A, 0, p4.OUTCOME_DISMISSED, severity="LOW")
        with self.assertRaises(StopError):
            adjudicate(self.reports, returned(bad))


class SeverityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reports = bound(report(TASK_A, "correctness", [("HIGH", "x", "claim one")]))

    def test_reviewer_severity_is_not_final_authority(self) -> None:
        found = adjudicate(self.reports, returned(disposition(
            TASK_A, 0, p4.OUTCOME_PROBLEM, severity="LOW", disposition=p4.DISPOSITION_RETAINED_HISTORY_ONLY,
        )))
        self.assertEqual("LOW", found.findings[0]["severity"])
        self.assertFalse(found.findings[0]["blocking"])
        self.assertEqual(p4.AUTHORIZATION_READY, found.outcome)

    def test_low_problem_nonblocking_only_while_objective_holds(self) -> None:
        low = disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity="LOW", disposition=p4.DISPOSITION_NO_ACTION)
        with self.assertRaises(StopError) as raised:
            adjudicate(self.reports, returned(low, objective_holds=False))
        self.assertEqual(p4.CODE_ADJUDICATION_INVALID, raised.exception.code)

    def test_objective_failing_without_a_blocking_problem_is_refused(self) -> None:
        with self.assertRaises(StopError):
            adjudicate(self.reports, returned(disposition(TASK_A, 0, p4.OUTCOME_DISMISSED), objective_holds=False))

    def test_high_and_mid_problems_block(self) -> None:
        for severity in ("HIGH", "MID"):
            found = adjudicate(self.reports, returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity=severity)))
            self.assertTrue(found.findings[0]["blocking"])
            self.assertEqual(1, found.obligations["problem_high" if severity == "HIGH" else "problem_mid"])

    def test_blocking_problem_must_be_disposed_repair_required(self) -> None:
        bad = disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, disposition=p4.DISPOSITION_NO_ACTION)
        with self.assertRaises(StopError):
            adjudicate(self.reports, returned(bad))

    def test_improvement_of_every_severity_never_blocks(self) -> None:
        for severity in ("HIGH", "MID", "LOW"):
            found = adjudicate(self.reports, returned(disposition(TASK_A, 0, p4.OUTCOME_IMPROVEMENT, severity=severity)))
            self.assertFalse(found.findings[0]["blocking"])
            self.assertEqual(p4.AUTHORIZATION_READY, found.outcome)

    def test_improvement_is_never_inserted_into_a_mandatory_batch(self) -> None:
        for chosen in (p4.DISPOSITION_REPAIR_REQUIRED, p4.DISPOSITION_REPAIRED_CURRENT_CYCLE):
            with self.subTest(chosen=chosen), self.assertRaises(StopError):
                adjudicate(self.reports, returned(disposition(TASK_A, 0, p4.OUTCOME_IMPROVEMENT, disposition=chosen)))

    def test_no_automatic_work_for_low_or_improvement(self) -> None:
        found = adjudicate(self.reports, returned(disposition(
            TASK_A, 0, p4.OUTCOME_PROBLEM, severity="LOW", disposition=p4.DISPOSITION_FUTURE_WORK_CANDIDATE,
        )))
        self.assertEqual(p4.DISPOSITION_FUTURE_WORK_CANDIDATE, found.findings[0]["disposition"])
        self.assertEqual(p4.AUTHORIZATION_READY, found.outcome)  # a candidate is a disposition, never a Work


class MergeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reports = bound(
            report(TASK_A, "correctness", [("LOW", "x", "first wording"), ("MID", "y", "other")]),
            report(TASK_B, "security", [("HIGH", "z", "second wording")]),
        )

    def test_merge_only_under_one_repair_identity_with_strongest_severity(self) -> None:
        found = adjudicate(self.reports, returned(
            disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity="MID"),
            disposition(TASK_A, 1, p4.OUTCOME_PROBLEM, severity="MID", repair_identity="other-fix"),
            disposition(TASK_B, 0, p4.OUTCOME_PROBLEM, severity="HIGH"),
        ))
        self.assertEqual(2, len(found.findings))
        merged = [f for f in found.findings if f["repair_identity"] == "fix-parser"][0]
        self.assertEqual("HIGH", merged["severity"])
        self.assertEqual(2, len(merged["sources"]))
        self.assertEqual({TASK_A, TASK_B}, {s["task_id"] for s in merged["sources"]})

    def test_uncertain_repair_identity_stays_separate(self) -> None:
        found = adjudicate(self.reports, returned(
            disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, repair_identity="fix-a"),
            disposition(TASK_A, 1, p4.OUTCOME_DISMISSED),
            disposition(TASK_B, 0, p4.OUTCOME_PROBLEM, repair_identity="fix-b"),
        ))
        self.assertEqual(2, len(found.findings))

    def test_contradictory_duplicate_finding_identity_is_refused(self) -> None:
        with self.assertRaises(StopError):
            adjudicate(self.reports, returned(
                disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, semantic_surface="parser"),
                disposition(TASK_A, 1, p4.OUTCOME_DISMISSED),
                disposition(TASK_B, 0, p4.OUTCOME_PROBLEM, semantic_surface="writer"),
            ))
        with self.assertRaises(StopError):
            adjudicate(self.reports, returned(
                disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity="LOW", disposition=p4.DISPOSITION_NO_ACTION),
                disposition(TASK_A, 1, p4.OUTCOME_DISMISSED),
                disposition(TASK_B, 0, p4.OUTCOME_PROBLEM, severity="LOW", disposition=p4.DISPOSITION_RETAINED_HISTORY_ONLY),
            ))

    def test_every_source_claim_is_accounted_for(self) -> None:
        with self.assertRaises(StopError) as raised:
            adjudicate(self.reports, returned(disposition(TASK_A, 0, p4.OUTCOME_DISMISSED)))
        self.assertIn("omits", str(raised.exception))

    def test_an_invented_source_is_refused(self) -> None:
        with self.assertRaises(StopError) as raised:
            adjudicate(self.reports, returned(
                disposition(TASK_A, 0, p4.OUTCOME_DISMISSED), disposition(TASK_A, 1, p4.OUTCOME_DISMISSED),
                disposition(TASK_B, 0, p4.OUTCOME_DISMISSED), disposition(TASK_B, 1, p4.OUTCOME_DISMISSED),
            ))
        self.assertIn("never bound", str(raised.exception))

    def test_a_claim_adjudicated_twice_is_refused(self) -> None:
        with self.assertRaises(StopError):
            adjudicate(self.reports, returned(
                disposition(TASK_A, 0, p4.OUTCOME_DISMISSED), disposition(TASK_A, 0, p4.OUTCOME_DISMISSED),
                disposition(TASK_A, 1, p4.OUTCOME_DISMISSED), disposition(TASK_B, 0, p4.OUTCOME_DISMISSED),
            ))

    def test_stable_finding_order_and_ids_across_retry_and_return_order(self) -> None:
        items = [
            disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, repair_identity="b-fix", semantic_surface="zeta"),
            disposition(TASK_A, 1, p4.OUTCOME_PROBLEM, repair_identity="a-fix", semantic_surface="alpha"),
            disposition(TASK_B, 0, p4.OUTCOME_IMPROVEMENT, repair_identity="c-fix", semantic_surface="alpha"),
        ]
        first = adjudicate(self.reports, returned(*items))
        second = adjudicate(self.reports, returned(*reversed(items)))
        self.assertEqual(first.to_record(), second.to_record())
        self.assertEqual(["alpha", "alpha", "zeta"], [f["semantic_surface"] for f in first.findings])
        self.assertEqual(finding_ids(3), [f["finding_id"] for f in first.findings])


class CoverageGapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reports = bound(report(TASK_A, "correctness", [], not_inspected=("the network path",)))

    def test_every_declared_gap_is_resolved_exactly_once(self) -> None:
        with self.assertRaises(StopError):
            adjudicate(self.reports, returned())
        ok = adjudicate(self.reports, returned(gaps=[p4.P4CoverageGap(TASK_A, "the network path", p4.GAP_NOT_APPLICABLE)]))
        self.assertEqual(p4.AUTHORIZATION_READY, ok.outcome)

    def test_covered_needs_evidence(self) -> None:
        with self.assertRaises(StopError):
            adjudicate(self.reports, returned(gaps=[p4.P4CoverageGap(TASK_A, "the network path", p4.GAP_COVERED)]))
        ok = adjudicate(self.reports, returned(gaps=[
            p4.P4CoverageGap(TASK_A, "the network path", p4.GAP_COVERED, ("evidence-1",))
        ]))
        self.assertEqual(p4.AUTHORIZATION_READY, ok.outcome)

    def test_zero_findings_with_unresolved_coverage_does_not_authorize(self) -> None:
        for resolution in (p4.GAP_TARGETED_CHECK, p4.GAP_HUMAN):
            found = adjudicate(self.reports, returned(gaps=[p4.P4CoverageGap(TASK_A, "the network path", resolution)]))
            self.assertEqual((), found.findings)
            self.assertEqual(p4.HUMAN_WAIT, found.outcome)
            self.assertEqual(1, found.obligations["coverage_unresolved"])


class IdentityTests(unittest.TestCase):
    def test_another_adjudicator_is_a_reviewer_mismatch(self) -> None:
        reports = bound(report(TASK_A, "correctness", []))
        other = p4.P4AdjudicationReturn(ADJ_TASK, "someone-else", "v1", True)
        with self.assertRaises(StopError) as raised:
            adjudicate(reports, other)
        self.assertEqual("review_reviewer_mismatch", raised.exception.code)

    def test_stored_adjudication_round_trips_and_is_consistent(self) -> None:
        reports = bound(report(TASK_A, "correctness", [("HIGH", "x", "claim")]))
        found = adjudicate(reports, returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM)))
        again = records.P4Adjudication.from_record(serialize.canonical_data(found.to_record()), "x")
        self.assertEqual(found, again)
        self.assertEqual([], p4.adjudication_problems(again))

    def test_a_tampered_outcome_is_inconsistent(self) -> None:
        reports = bound(report(TASK_A, "correctness", [("HIGH", "x", "claim")]))
        found = adjudicate(reports, returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM)))
        record = found.to_record()
        record["outcome"] = p4.AUTHORIZATION_READY
        tampered = records.P4Adjudication.from_record(serialize.canonical_data(record), "x")
        self.assertTrue(p4.adjudication_problems(tampered))

    def test_reserving_the_wrong_number_of_ids_is_refused(self) -> None:
        reports = bound(report(TASK_A, "correctness", [("HIGH", "x", "claim")]))
        normalized = p4.normalize_adjudication(returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM)), DESCRIPTOR,
                                               reports, None)
        with self.assertRaises(ValidationError):
            p4.adjudication(normalized, [], review_run_id=RUN, gate_record=gate(), candidate_generation=1,
                            review_contract=p4.WORK_CONTRACT, descriptor=DESCRIPTOR, reports=reports, prior=None)


class RepairBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reports = bound(
            report(TASK_A, "correctness", [("HIGH", "a", "one"), ("MID", "b", "two"), ("LOW", "c", "three")]),
            report(TASK_B, "security", [("LOW", "d", "four"), ("LOW", "e", "five"), ("LOW", "f", "six")]),
        )

    def _batch(self, found: records.P4Adjudication) -> records.P4RepairBatch:
        return p4.repair_batch(found, "9" * 64, repair_batch_id=BATCH, allowed_result_surface=["src/a.py"],
                               repair_purpose="fix it", strategy_change_class=None)

    def test_one_batch_holds_every_blocking_problem_and_excludes_the_rest(self) -> None:
        found = adjudicate(self.reports, returned(
            disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity="HIGH", repair_identity="r1"),
            disposition(TASK_A, 1, p4.OUTCOME_PROBLEM, severity="MID", repair_identity="r2"),
            disposition(TASK_A, 2, p4.OUTCOME_PROBLEM, severity="LOW", repair_identity="r3",
                        disposition=p4.DISPOSITION_RETAINED_HISTORY_ONLY),
            disposition(TASK_B, 0, p4.OUTCOME_IMPROVEMENT, repair_identity="r4"),
            disposition(TASK_B, 1, p4.OUTCOME_UNSUPPORTED),
            disposition(TASK_B, 2, p4.OUTCOME_DISMISSED),
        ))
        batch = self._batch(found)
        blocking = [f["finding_id"] for f in found.findings if f["blocking"]]
        self.assertEqual(blocking, list(batch.finding_ids))
        self.assertEqual((), batch.deliberate_low_finding_ids)

    def test_low_is_included_only_when_deliberately_repaired(self) -> None:
        found = adjudicate(self.reports, returned(
            disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity="HIGH", repair_identity="r1"),
            disposition(TASK_A, 1, p4.OUTCOME_DISMISSED),
            disposition(TASK_A, 2, p4.OUTCOME_PROBLEM, severity="LOW", repair_identity="r3",
                        disposition=p4.DISPOSITION_REPAIRED_CURRENT_CYCLE),
            disposition(TASK_B, 0, p4.OUTCOME_DISMISSED), disposition(TASK_B, 1, p4.OUTCOME_DISMISSED),
            disposition(TASK_B, 2, p4.OUTCOME_DISMISSED),
        ))
        batch = self._batch(found)
        self.assertEqual(2, len(batch.finding_ids))
        self.assertEqual(1, len(batch.deliberate_low_finding_ids))

    def test_human_stops_before_any_batch(self) -> None:
        found = adjudicate(self.reports, returned(
            disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity="HIGH", repair_identity="r1"),
            disposition(TASK_A, 1, p4.OUTCOME_HUMAN), disposition(TASK_A, 2, p4.OUTCOME_DISMISSED),
            disposition(TASK_B, 0, p4.OUTCOME_DISMISSED), disposition(TASK_B, 1, p4.OUTCOME_DISMISSED),
            disposition(TASK_B, 2, p4.OUTCOME_DISMISSED),
        ))
        self.assertEqual(p4.HUMAN_WAIT, found.outcome)
        with self.assertRaises(ValidationError):
            self._batch(found)

    def test_a_repair_without_purpose_is_refused(self) -> None:
        with self.assertRaises(StopError):
            adjudicate(self.reports, returned(
                disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity="HIGH"),
                disposition(TASK_A, 1, p4.OUTCOME_DISMISSED), disposition(TASK_A, 2, p4.OUTCOME_DISMISSED),
                disposition(TASK_B, 0, p4.OUTCOME_DISMISSED), disposition(TASK_B, 1, p4.OUTCOME_DISMISSED),
                disposition(TASK_B, 2, p4.OUTCOME_DISMISSED), purpose=None,
            ))


if __name__ == "__main__":
    unittest.main()
