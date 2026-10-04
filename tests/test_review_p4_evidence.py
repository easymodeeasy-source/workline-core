"""P4 §27.33: positive-proof Evidence reuse, impact-scaled reverification and the Repair Coverage Check."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from workline.errors import StopError
from workline.review import closure, p4, records, serialize

from test_review_p4_adjudication import TASK_A, adjudicate, bound, disposition, report, returned

BATCH = "rrb_01ARZ3NDEKTSV4RRFFQ69G5FAB"
REPAIR_TASK = "rtk_01ARZ3NDEKTSV4RRFFQ69G5FA7"


def declaration(*, adapter: str = "verifier", version: str = "v1", mechanism: str = "observer",
                identities: tuple[str, ...] = ("blob-1",), drop: str | None = None) -> closure.EvidenceDeclaration:
    coverage = []
    for dependency_class in closure.DEPENDENCY_CLASSES:
        if dependency_class == drop:
            continue
        if dependency_class == closure.REPOSITORY_FILES:
            coverage.append(closure.ClassCoverage(dependency_class, closure.PINNED, identities=identities))
        else:
            coverage.append(closure.ClassCoverage(
                dependency_class, closure.NOT_REQUIRED, proof=closure.exclusion(mechanism, "v1"),
            ))
    return closure.EvidenceDeclaration(adapter, version, (closure.REPOSITORY_FILES,), tuple(coverage))


class EvidenceReuseTests(unittest.TestCase):
    def reuse(self, prior, new, *, prior_ids=("a",), new_ids=("a",), invalidated=False) -> p4.EvidenceReuse:
        return p4.evidence_reuse("evidence-1", prior, new, prior_identities=prior_ids, new_identities=new_ids,
                                 assumption_invalidated=invalidated)

    def test_complete_unchanged_dependencies_may_reuse(self) -> None:
        found = self.reuse(declaration(), declaration())
        self.assertEqual((True, "reusable"), (found.reusable, found.state))

    def test_incomplete_declaration_is_unknown_and_reacquired(self) -> None:
        found = self.reuse(declaration(drop=closure.NETWORK), declaration())
        self.assertEqual((False, "unknown"), (found.reusable, found.state))

    def test_missing_declaration_is_fresh_use_only(self) -> None:
        found = self.reuse(None, declaration())
        self.assertEqual((False, "unknown"), (found.reusable, found.state))

    def test_changed_concrete_identity_invalidates(self) -> None:
        self.assertEqual("invalidated", self.reuse(declaration(), declaration(identities=("blob-2",))).state)
        self.assertEqual("invalidated", self.reuse(declaration(), declaration(), new_ids=("b",)).state)

    def test_changed_proof_mechanism_invalidates(self) -> None:
        self.assertEqual("invalidated", self.reuse(declaration(), declaration(mechanism="other")).state)

    def test_changed_adapter_identity_or_version_invalidates(self) -> None:
        self.assertEqual("invalidated", self.reuse(declaration(), declaration(adapter="other")).state)
        self.assertEqual("invalidated", self.reuse(declaration(), declaration(version="v2")).state)

    def test_repair_impact_invalidating_an_assumption_invalidates(self) -> None:
        self.assertEqual("invalidated", self.reuse(declaration(), declaration(), invalidated=True).state)

    def test_p4_never_calls_closure_may_reuse(self) -> None:
        source = Path(p4.__file__).read_text(encoding="utf-8")
        calls = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == "may_reuse"]
        self.assertEqual([], calls)


def coverage(**overrides: object) -> p4.P4CoverageCheck:
    values: dict = dict(
        semantic_behavior_changed="the parser refuses an empty key", semantic_responsibility="key-parsing",
        other_sites=(), shared_responsibility=False, enumerable=True, affected_set=("src/a.py",),
        covers_affected_set=True, repair_scope="local", unresolved_gap=None,
    )
    values.update(overrides)
    return p4.P4CoverageCheck(**values)


class RepairCoverageTests(unittest.TestCase):
    def test_complete_coverage_passes(self) -> None:
        self.assertEqual([], p4.repair_coverage_problems(coverage()))

    def test_unknown_coverage_never_passes(self) -> None:
        for overrides in (dict(unresolved_gap="the writer side"), dict(enumerable=False),
                          dict(covers_affected_set=False)):
            with self.subTest(overrides=overrides):
                codes = {code for code, _ in p4.repair_coverage_problems(coverage(**overrides))}
                self.assertEqual({p4.CODE_REPAIR_COVERAGE_UNKNOWN}, codes)
        self.assertEqual(p4.CODE_REPAIR_COVERAGE_UNKNOWN, p4.repair_coverage_problems(None)[0][0])

    def test_local_patch_on_a_shared_responsibility_is_widen_first(self) -> None:
        found = p4.repair_coverage_problems(coverage(shared_responsibility=True, other_sites=("src/b.py",)))
        self.assertEqual([p4.CODE_REPAIR_WIDEN_REQUIRED], [code for code, _ in found])
        self.assertEqual([], p4.repair_coverage_problems(
            coverage(shared_responsibility=True, other_sites=("src/b.py",), repair_scope="widened")
        ))


class ReverificationTests(unittest.TestCase):
    def test_minimums_follow_semantic_impact(self) -> None:
        self.assertEqual(("direct_consumers", "focused_tests"), p4.reverification_plan(p4.IMPACT_LOCAL))
        self.assertIn("representative_callers", p4.reverification_plan(p4.IMPACT_SHARED))
        contract = p4.reverification_plan(p4.IMPACT_CONTRACT)
        for required in ("writers_readers", "failure_interruption_resume", "adjacent_eligibility", "contract_roundtrip"):
            self.assertIn(required, contract)
        self.assertIn("full_suite", p4.reverification_plan(p4.IMPACT_FOUNDATION))
        self.assertIn("kind-check", p4.reverification_plan(p4.IMPACT_LOCAL, ["kind-check"]))

    def _batch(self) -> records.P4RepairBatch:
        reports = bound(report(TASK_A, "correctness", [("HIGH", "x", "claim")]))
        found = adjudicate(reports, returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity="HIGH")))
        return p4.repair_batch(found, "9" * 64, repair_batch_id=BATCH, allowed_result_surface=["src/a.py"],
                               repair_purpose="fix", strategy_change_class=None)

    def _returned(self, impact: str, verification) -> p4.P4RepairReturn:
        return p4.P4RepairReturn(
            task_id=REPAIR_TASK, repair_identity="repairer", repair_version="v1", status="completed",
            proposal={}, repaired_surface=("src/a.py",), impact_class=impact, coverage_check=coverage(),
            verification=tuple(p4.P4Verification(name, "pass") for name in verification), causal_summary="fixed",
        )

    def test_incomplete_required_reverification_cannot_be_ready(self) -> None:
        with self.assertRaises(StopError) as raised:
            p4.repair_result(batch=self._batch(), source_candidate_generation=1, result_candidate_hash="b" * 64,
                             result_candidate_material_digest="c" * 64, repair_task_id=REPAIR_TASK,
                             returned=self._returned(p4.IMPACT_CONTRACT, ["focused_tests"]), evidence=(), kind_checks=())
        self.assertEqual(p4.CODE_REVERIFICATION_INCOMPLETE, raised.exception.code)

    def test_complete_reverification_yields_a_ready_result(self) -> None:
        result = p4.repair_result(
            batch=self._batch(), source_candidate_generation=1, result_candidate_hash="b" * 64,
            result_candidate_material_digest="c" * 64, repair_task_id=REPAIR_TASK,
            returned=self._returned(p4.IMPACT_LOCAL, ["focused_tests", "direct_consumers"]),
            evidence=(p4.EvidenceReuse("evidence-1", False, "unknown", ("fresh",)),),
            kind_checks=(p4.P4Verification("kind-check", "pass"),),
        )
        self.assertTrue(result.successor_eligible)
        self.assertEqual(0, result.reverification["residual"])
        self.assertEqual(2, result.result_candidate_generation)
        self.assertEqual(result, records.P4RepairResult.from_record(serialize.canonical_data(result.to_record()), "x"))

    def test_a_failed_kind_check_leaves_residual(self) -> None:
        with self.assertRaises(StopError):
            p4.repair_result(
                batch=self._batch(), source_candidate_generation=1, result_candidate_hash="b" * 64,
                result_candidate_material_digest="c" * 64, repair_task_id=REPAIR_TASK,
                returned=self._returned(p4.IMPACT_LOCAL, ["focused_tests", "direct_consumers"]), evidence=(),
                kind_checks=(p4.P4Verification("kind-check", "fail"),),
            )


class RepairReturnTests(unittest.TestCase):
    DESCRIPTOR = {"task_id": REPAIR_TASK, "reviewer_identity": "repairer", "reviewer_version": "v1"}

    def test_explicit_failure_or_decline_is_never_success(self) -> None:
        for status in ("failed", "declined"):
            found = p4.repair_return_problems(p4.P4RepairReturn(REPAIR_TASK, "repairer", "v1", status), self.DESCRIPTOR)
            self.assertEqual([p4.CODE_REPAIR_FAILED], [code for code, _ in found])

    def test_invalid_returns_do_not_settle(self) -> None:
        self.assertEqual(p4.CODE_REPAIR_INVALID, p4.repair_return_problems("text", self.DESCRIPTOR)[0][0])
        self.assertEqual(p4.CODE_REPAIR_INVALID,
                         p4.repair_return_problems(p4.P4RepairReturn(REPAIR_TASK, "repairer", "v1", "odd"),
                                                   self.DESCRIPTOR)[0][0])
        self.assertEqual("review_reviewer_mismatch",
                         p4.repair_return_problems(p4.P4RepairReturn(REPAIR_TASK, "other", "v1", "completed"),
                                                   self.DESCRIPTOR)[0][0])

    def test_unknown_coverage_in_a_return_is_refused(self) -> None:
        returned_value = p4.P4RepairReturn(
            REPAIR_TASK, "repairer", "v1", "completed", proposal={}, repaired_surface=("src/a.py",),
            impact_class=p4.IMPACT_LOCAL, coverage_check=None, causal_summary="fixed",
        )
        self.assertIn(p4.CODE_REPAIR_COVERAGE_UNKNOWN,
                      [code for code, _ in p4.repair_return_problems(returned_value, self.DESCRIPTOR)])


class NeverReusedAsAuthorizationTests(unittest.TestCase):
    def test_candidate_n_report_adjudication_and_receipt_never_authorize_n_plus_1(self) -> None:
        # The successor request binds the result Candidate; the Receipt it may later get binds that Candidate's
        # hash, and its discovery is fresh. Nothing of Run N is a field of a successor's authorization record.
        self.assertNotIn("receipt", " ".join(records.P4_REPAIR_RESULT_FIELDS))
        envelope = p4.discovery_request(
            review_contract=p4.WORK_CONTRACT, review_kind="work-result-v1", viewpoint="correctness",
            candidate={"c": 1}, context={"x": 1}, requirement={"r": 1}, candidate_generation=2,
            succession=p4.succession_record("rr_01ARZ3NDEKTSV4RRFFQ69G5FAV", "a" * 64, BATCH, "6" * 64),
            set_aside_runs=[{"review_run_id": "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV", "reason": p4.SET_ASIDE_REPAIRED}],
            human_decision=None,
        )
        for forbidden in ("findings", "reports", "adjudication", "receipt_id"):
            self.assertNotIn(forbidden, envelope)


if __name__ == "__main__":
    unittest.main()
