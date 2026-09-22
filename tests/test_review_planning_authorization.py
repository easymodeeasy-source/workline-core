"""P2 §28 C: authorization - the chain, the Receipt at the use check, not-authorized outcomes, policy, reviewer failures."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from helpers import git
from planning_helpers import Crash, PlanningTestCase, Reviewer, crash_at, plan, rr, run_ids
from workline import roadmap as rm
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.review import gate, planning, publication, serialize
from workline.review import paths as review_paths
from workline.review import records
from workline.review.planning import PlanningReviewFinding, PlanningReviewReport
from workline.review.store import ReviewStore
from workline.validate import validate_project

WORKLINE_ROOT = Path(__file__).resolve().parents[1]


class ChainTests(PlanningTestCase):
    def test_accepted_settled_sealed_chain_validates(self) -> None:
        store = self.planning_project()
        result = self.reviewed_roadmap(store)
        chain = self.chain(store, result.review_run_id)
        first, second, third = chain.generations
        self.assertEqual((1, 0), (len(first.accepted_tasks), len(first.settled_tasks)))
        self.assertEqual("completed", second.settled_tasks[0]["status"])
        self.assertTrue(third.sealed)
        self.assertEqual("roadmap-create:registration", third.authorized_operation_stage)
        self.assertEqual([], validate_project(store))

    def test_a_seal_with_an_unsettled_task_is_refused(self) -> None:
        store = self.planning_project()
        with crash_at(rr, "_launch_and_settle"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(store)
        (run_id,) = run_ids(store)
        first = self.chain(store, run_id).generations[0]
        from dataclasses import replace

        sealed = replace(first, generation=2, previous_generation=1, previous_digest=self.chain(store, run_id).latest_digest,
                         status="sealed_authorized", receipt_id="rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                         authorized_operation_stage="roadmap-create:registration")
        target = store.root / review_paths.gate_rel(run_id, 2)
        target.write_text(serialize.canonical_text(sealed.to_record()), encoding="utf-8", newline="\n")
        with self.assertRaises(ValidationError) as raised:
            ReviewStore(store).gate_chain(run_id)
        self.assertEqual("review_gate_chain", raised.exception.code)
        self.assertIn("sealed with unsettled accepted task", str(raised.exception))


class ReceiptAtTheUseCheckTests(PlanningTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()
        with crash_at(rr, "_use_check"):
            with self.assertRaises(Crash):
                self.reviewed_roadmap(self.store)
        (self.run_id,) = run_ids(self.store)
        self.receipt_id = self.chain(self.store, self.run_id).latest.receipt_id

    def test_a_tampered_unbound_receipt_is_refused(self) -> None:
        review = ReviewStore(self.store)
        receipt = review.read_receipt(self.receipt_id)
        from dataclasses import replace

        tampered = replace(receipt, coverage_hash="0" * 64)
        (self.store.root / review_paths.receipt_rel(self.receipt_id)).write_text(
            serialize.canonical_text(tampered.to_record()), encoding="utf-8", newline="\n"
        )
        with self.assertRaises(ReconcileRequired) as raised:
            self.reviewed_roadmap(self.store)
        self.assertEqual("review_receipt_invalid", raised.exception.reason)
        self.assertFalse(any((self.store.root / ".workline" / "roadmaps").glob("*.md")))

    def test_a_superseded_receipt_fixture_is_refused(self) -> None:
        supersession = records.Supersession(self.receipt_id, self.run_id, 4, "fixture")
        target = self.store.root / review_paths.supersession_rel(self.receipt_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialize.canonical_text(supersession.to_record()), encoding="utf-8", newline="\n")
        with self.assertRaises(ReconcileRequired) as raised:
            self.reviewed_roadmap(self.store)
        self.assertEqual("review_receipt_invalid", raised.exception.reason)


class NotAuthorizedTests(PlanningTestCase):
    def _not_authorized(self, reviewer: Reviewer, *, remote: bool = False, name: str = "proj"):
        store = self.planning_project(name, remote=remote)
        result = self.reviewed_roadmap(store, reviewer)
        self.assertEqual(("not_authorized", None, None, None),
                         (result.status, result.receipt_id, result.consumption_id, result.registration))
        self.assertFalse(any((store.root / ".workline" / "roadmaps").glob("*.md")), "nothing is registered")
        self.assertEqual([], self.pending(store))
        chain = self.chain(store, result.review_run_id)
        self.assertEqual([1, 2], [generation.generation for generation in chain.generations])
        return store, result

    def test_high_finding(self) -> None:
        finding = PlanningReviewFinding("HIGH", "phase-scope", "Phase B has no measurable state")
        _, result = self._not_authorized(Reviewer(findings=(finding,)))
        self.assertEqual((finding,), result.findings)

    def test_mid_finding(self) -> None:
        finding = PlanningReviewFinding("MID", "ordering", "the order is unclear")
        self._not_authorized(Reviewer(findings=(finding,)))

    def test_declined_is_a_failed_task(self) -> None:
        store, result = self._not_authorized(Reviewer(status="declined"))
        settled = self.chain(store, result.review_run_id).latest.settled_tasks[0]
        self.assertEqual("failed", settled["status"])
        self.assertNotEqual(planning.empty_obligation_digest(), self.chain(store, result.review_run_id).latest.obligation_digest)

    def test_no_publication_barrier_results_and_a_legacy_push_proceeds(self) -> None:
        for name, reviewer in (
            ("declined", Reviewer(status="declined")),
            ("high", Reviewer(findings=(PlanningReviewFinding("HIGH", "phase-scope", "no measurable state"),))),
            ("mid", Reviewer(findings=(PlanningReviewFinding("MID", "ordering", "the order is unclear"),))),
        ):
            with self.subTest(name):
                store, _ = self._not_authorized(reviewer, remote=True, name=name)
                self.assertIsNone(publication.barrier_problem(store.root, self.head(store)))
                legacy = rm.create_roadmap(store, plan("Legacy after refusal"))
                self.assertEqual(legacy.head, self.remote_head(name))


class LowFindingTests(PlanningTestCase):
    def test_low_findings_do_not_block_and_are_returned(self) -> None:
        store = self.planning_project()
        finding = PlanningReviewFinding("LOW", "wording", "consider a clearer name")
        result = self.reviewed_roadmap(store, Reviewer(findings=(finding,)))
        self.assertEqual("registered", result.status)
        self.assertEqual((finding,), result.findings)


class PolicyAuthorityTests(unittest.TestCase):
    def test_the_skill_policy_block_equals_the_code_constant(self) -> None:
        text = (WORKLINE_ROOT / ".claude" / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8")
        heading = text.index("Planning Review Policy")
        block = re.search(r"```yaml\n(.*?)```", text[heading:], re.S)
        self.assertIsNotNone(block, "the Review Skill declares the policy record in a yaml block")
        declared = serialize.parse(block.group(1), "the Planning Review Policy")
        self.assertEqual(serialize.canonical_data(planning.POLICY_RECORD), serialize.canonical_data(declared))
        self.assertEqual(serialize.canonical_text(planning.POLICY_RECORD), block.group(1))


class ReviewerFailureTests(PlanningTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()

    def _fails(self, reviewer: Reviewer, code: str) -> None:
        with self.assertRaises(StopError) as raised:
            self.reviewed_roadmap(self.store, reviewer)
        self.assertEqual(code, raised.exception.code)
        (run_id,) = run_ids(self.store)
        self.assertEqual(1, self.chain(self.store, run_id).latest.generation, "nothing is settled")

    def test_a_raised_exception(self) -> None:
        self._fails(Reviewer(raises=RuntimeError("boom")), "review_reviewer_failed")

    def test_invalid_reports(self) -> None:
        cases = [
            lambda task: "not a report",
            lambda task: PlanningReviewReport("rtk_01ARZ3NDEKTSV4RRFFQ69G5FAV", "test-reviewer", "1", "completed", ()),
            lambda task: PlanningReviewReport(task.task_id, "test-reviewer", "1", "approved", ()),
            lambda task: PlanningReviewReport(task.task_id, "test-reviewer", "1", "completed", (PlanningReviewFinding("CRITICAL", "c", "m"),)),
            lambda task: PlanningReviewReport(task.task_id, "test-reviewer", "1", "completed", (PlanningReviewFinding("LOW", " c", "m"),)),
            lambda task: PlanningReviewReport(task.task_id, "test-reviewer", "1", "completed", [PlanningReviewFinding("LOW", "c", "m")]),
        ]
        for index, returns in enumerate(cases):
            with self.subTest(case=index):
                with self.assertRaises(StopError) as raised:
                    self.reviewed_roadmap(self.store, Reviewer(returns=returns))
                self.assertEqual("review_report_invalid", raised.exception.code)
        (run_id,) = run_ids(self.store)
        self.assertEqual(1, self.chain(self.store, run_id).latest.generation)

    def test_a_report_from_another_identity(self) -> None:
        self._fails(
            Reviewer(returns=lambda task: PlanningReviewReport(task.task_id, "someone-else", "1", "completed", ())),
            "review_reviewer_mismatch",
        )

    def test_a_relaunch_for_another_reviewer_identity_is_refused(self) -> None:
        self._fails(Reviewer(raises=RuntimeError("down")), "review_reviewer_failed")
        other = Reviewer(identity="another-reviewer")
        with self.assertRaises(StopError) as raised:
            self.reviewed_roadmap(self.store, other)
        self.assertEqual("review_reviewer_mismatch", raised.exception.code)
        self.assertEqual([], other.tasks, "the reviewer is not called")


class ProcessDeath(BaseException):
    """The process ends inside the reviewer call: no handler of the operation sees it (not an Exception)."""


class RelaunchTests(PlanningTestCase):
    def test_the_same_task_id_is_relaunched_after_the_process_died_in_the_reviewer_call(self) -> None:
        store = self.planning_project()
        first = Reviewer(raises=ProcessDeath())
        with self.assertRaises(ProcessDeath):
            self.reviewed_roadmap(store, first)
        (run_id,) = run_ids(store)
        self.assertEqual(1, self.chain(store, run_id).latest.generation, "nothing was settled")
        self.assertEqual(1, len([r for r in self.pending(store) if r["invocation"].get("operation") == "roadmap-create"]))
        second = Reviewer()
        result = self.reviewed_roadmap(store, second)
        self.assertEqual("registered", result.status)
        self.assertEqual(run_id, result.review_run_id)
        self.assertEqual(first.tasks, second.tasks, "the relaunched task is exactly the stored one, by the same task ID")

    def test_the_same_task_id_is_relaunched_after_a_crash(self) -> None:
        store = self.planning_project()
        first = Reviewer(raises=RuntimeError("process died"))
        with self.assertRaises(StopError):
            self.reviewed_roadmap(store, first)
        second = Reviewer()
        result = self.reviewed_roadmap(store, second)
        self.assertEqual("registered", result.status)
        self.assertEqual(first.tasks[0].task_id, second.tasks[0].task_id)
        self.assertEqual(first.tasks[0], second.tasks[0], "the relaunched task is exactly the stored one")

    def test_a_duplicate_settlement_is_idempotent(self) -> None:
        store = self.planning_project()
        result = self.reviewed_roadmap(store)
        chain = self.chain(store, result.review_run_id)
        settled = chain.latest.settled_tasks[0]
        descriptor = chain.generations[0].accepted_tasks[0]
        for _ in range(2):
            found = gate.validate_settlement(store, result.review_run_id, settled["task_id"], settled["result_digest"],
                                             descriptor["reviewer_identity"])
            self.assertEqual(descriptor, found)


if __name__ == "__main__":
    unittest.main()
