"""P4 §27.29: the four P4 record kinds - strict schema, canonical round-trip, digest naming, orphans, namespace."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from helpers import WorklineTestCase, rmtree
from workline.errors import ReconcileRequired, StopError, ValidationError
from workline.mutation import MATCHING, Effect, MutationController, WriteScope
from workline.oplock import project_operation
from workline.review import ReviewStore, checkout, fsafe, p4, paths, records, serialize, validate
from workline.store import ProjectStore

from test_review_p4_adjudication import (
    ADJ_TASK, BATCH, RUN, TASK_A, adjudicate, bound, disposition, report, returned,
)
from test_review_p4_evidence import REPAIR_TASK, coverage

CREATE_ONLY = unittest.skipUnless(fsafe.immutable_create_supported(), "the immutable Review create is fail-closed here")


def adjudication_fixture() -> records.P4Adjudication:
    reports = bound(report(TASK_A, "correctness", [("HIGH", "x", "the claim")]))
    return adjudicate(reports, returned(disposition(TASK_A, 0, p4.OUTCOME_PROBLEM, severity="HIGH")))


def batch_fixture(found: records.P4Adjudication, digest: str) -> records.P4RepairBatch:
    return p4.repair_batch(found, digest, repair_batch_id=BATCH, allowed_result_surface=["src/a.py"],
                           repair_purpose="fix it", strategy_change_class=None)


def result_fixture(batch: records.P4RepairBatch, result_hash: str = "b" * 64, material: str = "c" * 64) -> records.P4RepairResult:
    returned_value = p4.P4RepairReturn(
        task_id=REPAIR_TASK, repair_identity="repairer", repair_version="v1", status="completed", proposal={},
        repaired_surface=("src/a.py",), impact_class=p4.IMPACT_LOCAL, coverage_check=coverage(),
        verification=(p4.P4Verification("focused_tests", "pass"), p4.P4Verification("direct_consumers", "pass")),
        causal_summary="changed the parser",
    )
    return p4.repair_result(batch=batch, source_candidate_generation=1, result_candidate_hash=result_hash,
                            result_candidate_material_digest=material, repair_task_id=REPAIR_TASK,
                            returned=returned_value, evidence=(), kind_checks=())


class NamespaceCase(unittest.TestCase):
    """A bare directory read through ``ReviewStore``: records laid down as their exact canonical bytes."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="workline-p4-records-"))
        self.addCleanup(rmtree, self.root)
        self.store = ProjectStore(self.root)
        self.review = ReviewStore(self.store)

    def put(self, relative: str, record: dict | None = None, raw: bytes | None = None) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw if raw is not None else serialize.canonical_bytes(record))

    def problems(self) -> list[str]:
        return [problem.code for problem in validate.review_problems(self.review)]


class PathTests(unittest.TestCase):
    def test_paths_are_the_frozen_shapes(self) -> None:
        self.assertEqual(f".workline/review/reports/{'a' * 64}.yaml", paths.report_rel("a" * 64))
        self.assertEqual(f".workline/review/adjudications/{RUN}.yaml", paths.adjudication_rel(RUN))
        self.assertEqual(f".workline/review/repair-batches/{BATCH}.yaml", paths.repair_batch_rel(BATCH))
        self.assertEqual(f".workline/review/repair-results/{BATCH}.yaml", paths.repair_result_rel(BATCH))

    def test_path_helpers_refuse_other_identities(self) -> None:
        for call, value in ((paths.report_rel, "A" * 64), (paths.report_rel, "a" * 63), (paths.adjudication_rel, BATCH),
                            (paths.repair_batch_rel, RUN), (paths.repair_result_rel, RUN)):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                call(value)

    def test_the_four_areas_are_inside_the_closed_namespace(self) -> None:
        for area in ("reports", "adjudications", "repair-batches", "repair-results"):
            self.assertIn(area, paths.REVIEW_SUBDIRS)
        for relative in (paths.report_rel("a" * 64), paths.adjudication_rel(RUN), paths.repair_batch_rel(BATCH),
                         paths.repair_result_rel(BATCH)):
            paths.require_review_record_path(relative)
            with self.assertRaises(ValidationError):
                paths.require_review_record_path(relative.replace(".yaml", "/x.yaml"))


class ReportRecordTests(NamespaceCase):
    def test_report_path_digest_is_the_canonical_report_digest(self) -> None:
        record = report(TASK_A, "correctness", [("HIGH", "x", "claim")])
        digest = serialize.digest(record)
        self.put(paths.report_rel(digest), record)
        self.assertEqual(TASK_A, self.review.read_report(digest).task_id)
        self.assertEqual((digest,), self.review.report_digests())
        self.assertEqual([], self.problems())

    def test_a_report_under_another_digest_is_refused(self) -> None:
        record = report(TASK_A, "correctness", [])
        self.put(paths.report_rel("e" * 64), record)
        with self.assertRaises(ValidationError):
            self.review.read_report("e" * 64)
        self.assertIn("review_record_invalid", self.problems())

    def test_report_schema_is_strict(self) -> None:
        base = report(TASK_A, "correctness", [("HIGH", "x", "claim")])
        mutations = {
            "unknown field": lambda r: r.update(extra=1),
            "missing field": lambda r: r.pop("coverage"),
            "bad severity": lambda r: r["claims"][0].update(severity="CRITICAL"),
            "unsafe message": lambda r: r["claims"][0].update(message="read C:\\Users\\me\\secret.txt"),
            "token in message": lambda r: r["claims"][0].update(message="api_key=abcdef123456"),
            "multi-line message": lambda r: r["claims"][0].update(message="one\ntwo"),
            "declined with claims": lambda r: r.update(status="declined"),
            "viewpoint not slot": lambda r: r["coverage"].update(viewpoint="security"),
            "v1 contract": lambda r: r.update(review_contract="review-v1-work-v1"),
            "non-p4 slot": lambda r: r.update(task_slot="work-result-reviewer"),
        }
        for name, mutate in mutations.items():
            record = serialize.canonical_data(base)
            record = {**record, "claims": [dict(c) for c in record["claims"]], "coverage": dict(record["coverage"])}
            mutate(record)
            with self.subTest(name), self.assertRaises(ValidationError):
                records.P4Report.from_record(record, name)

    def test_report_record_builder_refuses_an_unsafe_return_before_persistence(self) -> None:
        descriptor = {"task_id": TASK_A, "task_slot": p4.discovery_slot("correctness"),
                      "reviewer_identity": "reviewer", "reviewer_version": "v1"}
        unsafe = p4.P4DiscoveryReport(TASK_A, "reviewer", "v1", "completed",
                                      (p4.P4Claim("HIGH", "x", "see /home/alice/.ssh/id_rsa"),))
        with self.assertRaises(StopError) as raised:
            p4.report_record(unsafe, descriptor, review_kind="work-result-v1", review_contract=p4.WORK_CONTRACT)
        self.assertEqual("review_report_invalid", raised.exception.code)
        safe = p4.P4DiscoveryReport(TASK_A, "reviewer", "v1", "completed", (p4.P4Claim("HIGH", "x", "the parser drops keys"),))
        record = p4.report_record(safe, descriptor, review_kind="work-result-v1", review_contract=p4.WORK_CONTRACT)
        self.assertEqual(record, serialize.canonical_data(records.P4Report.from_record(record, "x").to_record()))
        other = p4.P4DiscoveryReport(TASK_A, "someone", "v1", "completed")
        with self.assertRaises(StopError) as raised:
            p4.report_record(other, descriptor, review_kind="work-result-v1", review_contract=p4.WORK_CONTRACT)
        self.assertEqual("review_reviewer_mismatch", raised.exception.code)

    def test_an_orphan_report_is_validated_not_condemned(self) -> None:
        record = report(TASK_A, "correctness", [])
        self.put(paths.report_rel(serialize.digest(record)), record)
        self.assertEqual([], self.problems())
        bad = dict(record)
        bad["status"] = "maybe"
        self.put(paths.report_rel(serialize.digest(bad)), bad)
        self.assertIn("review_record_invalid", self.problems())


class AdjudicationBatchResultTests(NamespaceCase):
    def test_round_trip_and_orphan_validation(self) -> None:
        found = adjudication_fixture()
        self.put(paths.adjudication_rel(RUN), found.to_record())
        digest = self.review.adjudication_digest(RUN)
        batch = batch_fixture(found, digest)
        self.put(paths.repair_batch_rel(BATCH), batch.to_record())
        result = result_fixture(batch)
        self.put(paths.repair_result_rel(BATCH), result.to_record())
        self.assertEqual(found, self.review.read_adjudication(RUN))
        self.assertEqual(batch, self.review.read_repair_batch(BATCH))
        self.assertEqual(result, self.review.read_repair_result(BATCH))
        self.assertEqual(([RUN], [BATCH], [BATCH]), (list(self.review.adjudication_run_ids()),
                                                     list(self.review.repair_batch_ids()),
                                                     list(self.review.repair_result_ids())))
        self.assertEqual([], self.problems())

    def test_a_filename_naming_another_identity_is_refused(self) -> None:
        found = adjudication_fixture()
        other = "rr_01ARZ3NDEKTSV4RRFFQ69G5FAZ"
        self.put(paths.adjudication_rel(other), found.to_record())
        with self.assertRaises(ValidationError):
            self.review.read_adjudication(other)
        self.assertIn("review_record_invalid", self.problems())

    def test_a_batch_that_does_not_bind_its_source_adjudication_conflicts(self) -> None:
        found = adjudication_fixture()
        self.put(paths.adjudication_rel(RUN), found.to_record())
        batch = batch_fixture(found, "9" * 64)
        self.put(paths.repair_batch_rel(BATCH), batch.to_record())
        self.assertIn("review_record_conflict", self.problems())

    def test_a_result_with_another_generation_or_digest_is_refused(self) -> None:
        found = adjudication_fixture()
        batch = batch_fixture(found, "9" * 64)
        result = result_fixture(batch).to_record()
        for name, change in (
            ("generation", {"result_candidate_generation": 3}),
            ("same candidate", {"result_candidate_hash": found.candidate_hash}),
            ("coverage digest", {"coverage_check_digest": "0" * 64}),
            ("residual", {"reverification": {**result["reverification"], "residual": 1}}),
            ("eligibility type", {"successor_eligible": "yes"}),
        ):
            with self.subTest(name), self.assertRaises(ValidationError):
                records.P4RepairResult.from_record(serialize.canonical_data({**result, **change}), name)

    def test_a_tampered_stored_adjudication_is_reported(self) -> None:
        record = adjudication_fixture().to_record()
        record["findings"][0]["blocking"] = False
        record["findings"][0]["disposition"] = p4.DISPOSITION_NO_ACTION
        self.put(paths.adjudication_rel(RUN), serialize.canonical_data(record))
        self.assertIn("review_record_invalid", self.problems())

    def test_conflicting_duplicate_identities_fail_closed(self) -> None:
        record = adjudication_fixture().to_record()
        record["findings"] = record["findings"] * 2
        with self.assertRaises(ValidationError):
            records.P4Adjudication.from_record(serialize.canonical_data(record), "duplicate")
        batch = batch_fixture(adjudication_fixture(), "9" * 64).to_record()
        batch["finding_ids"] = batch["finding_ids"] * 2
        with self.assertRaises(ValidationError):
            records.P4RepairBatch.from_record(serialize.canonical_data(batch), "duplicate")


class NamespaceShapeTests(NamespaceCase):
    def test_stray_entries_in_the_p4_areas_fail_closed(self) -> None:
        for area in ("reports", "adjudications", "repair-batches", "repair-results"):
            with self.subTest(area=area):
                stray = self.root / paths.REVIEW_DIR / area / "evil.yaml"
                stray.parent.mkdir(parents=True, exist_ok=True)
                stray.write_bytes(b"schema: x\nversion: 1\n")
                self.assertIn("review_namespace_invalid", self.problems())
                stray.unlink()
                nested = self.root / paths.REVIEW_DIR / area / "nested"
                nested.mkdir()
                self.assertIn("review_namespace_invalid", self.problems())
                nested.rmdir()

    def test_namespace_readability_reads_the_p4_records(self) -> None:
        record = report(TASK_A, "correctness", [])
        record = {**record, "status": "maybe"}
        self.put(paths.report_rel(serialize.digest(record)), record)
        with self.assertRaises(StopError) as raised:
            checkout.require_namespace_readable(self.store)
        self.assertEqual("review_namespace_unreadable", raised.exception.code)

    def test_noncanonical_bytes_are_refused(self) -> None:
        record = report(TASK_A, "correctness", [])
        digest = serialize.digest(record)
        self.put(paths.report_rel(digest), raw=serialize.canonical_bytes(record).replace(b"\n", b"\r\n"))
        with self.assertRaises(ValidationError):
            self.review.read_report(digest)


class CreateOnlyTests(WorklineTestCase):
    @CREATE_ONLY
    def test_p4_records_are_immutable_create_only(self) -> None:
        store = self.new_project()
        lock = project_operation(store, "p4-records-test")
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)
        record = report(TASK_A, "correctness", [])
        relative = paths.report_rel(serialize.digest(record))
        controller = MutationController(store)
        first = controller.open("start", {"operation": "p4-test", "n": 1}, WriteScope(files=(relative,)))
        first.add_effects("review", [Effect.create_file(relative, serialize.canonical_text(record))])
        first.apply()
        self.assertEqual([MATCHING], [classification for _, classification in first.apply()])
        first.complete()
        other = {**record, "status": "declined", "claims": []}
        clash = controller.open("start", {"operation": "p4-test", "n": 2}, WriteScope(files=(relative,)))
        clash.add_effects("review", [Effect.create_file(relative, serialize.canonical_text(other))])
        with self.assertRaises(ReconcileRequired):
            clash.apply()
        self.assertEqual(serialize.canonical_bytes(record), (store.root / relative).read_bytes())


if __name__ == "__main__":
    unittest.main()
