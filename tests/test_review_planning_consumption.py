"""P2 §28 F: Planning Consumption v2 - the exact persisted_result binding, uniqueness, and the version rules."""

from __future__ import annotations

from dataclasses import replace
import unittest

from helpers import git
from planning_helpers import PlanningTestCase, Reviewer, design, plan, rr
from workline import gitcmd
from workline.errors import ValidationError
from workline.review import planning, publication, records, serialize
from workline.review import paths as review_paths
from workline.review.store import ReviewStore
from workline.review.validate import validate_review
from workline.store import ProjectStore


def forge_commit(store: ProjectStore, base: str, relative: str, text: str, message: str = "a forged commit") -> str:
    """A commit on ``base`` adding ``relative`` with ``text``; the checkout returns to where it was."""
    branch = git(store.root, "symbolic-ref", "--short", "HEAD").strip()
    git(store.root, "checkout", "-q", "--detach", base)
    target = store.root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    git(store.root, "add", "--", relative)
    git(store.root, "commit", "-q", "-m", message)
    forged = git(store.root, "rev-parse", "HEAD").strip()
    git(store.root, "checkout", "-q", "-f", branch)
    return forged


class _RegisteredCase(PlanningTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.planning_project()
        self.result = self.reviewed_roadmap(self.store)
        self.review = ReviewStore(self.store)
        self.consumption = self.review.read_consumption(self.result.consumption_id)

    def write(self, relative: str, record: dict) -> None:
        target = self.store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialize.canonical_text(record), encoding="utf-8", newline="\n")


class BindingTests(_RegisteredCase):
    def test_roadmap_persisted_result_binding(self) -> None:
        consumption = self.consumption
        self.assertIsInstance(consumption, records.PlanningConsumption)
        chain = self.chain(self.store, self.result.review_run_id)
        first = chain.generations[0]
        result = consumption.persisted_result
        kp = git(self.store.root, "rev-parse", "HEAD~1").strip()
        parent = git(self.store.root, "rev-parse", "HEAD~2").strip()
        material = self.review.read_candidate_snapshot(first.candidate_hash).material
        content = planning.candidate_content(material)
        context = self.review.read_task_input(first.accepted_tasks[0]["task_id"]).request_envelope["context"]
        expected = rr.expected_projection(self.store, material, context, parent)
        self.assertEqual(
            {
                "contract": "review-v1-planning-persisted-result-v1",
                "request_digest": planning.request_digest_of(first.operation_identity),
                "registration_commit": kp,
                "registration_parent": parent,
                "branch": "refs/heads/main",
                "registration_delta_digest": expected.delta_digest(kp),
                "semantic_projection_digest": rr.reviewed_projection(material).identity(),
                "adapter_identity": "roadmap-plan-adapter-v1",
                "loader_identity": context["loader_identity"],
                "roadmap_id": content["roadmap"]["id"],
                "phase_ids": [{"key": p["key"], "id": p["id"]} for p in content["phases"]],
                "relation_ids": [r["id"] for r in content["relations"]],
            },
            result,
        )
        self.assertEqual(
            (self.result.receipt_id, self.result.review_run_id, 3, "roadmap-plan-v1", first.candidate_hash,
             first.operation_identity, self.result.mutation_id, content["roadmap"]["id"]),
            (consumption.receipt_id, consumption.review_run_id, consumption.review_generation, consumption.review_kind,
             consumption.authorized_candidate_hash, consumption.operation_identity, consumption.operation_mutation_id,
             consumption.target_identity),
        )

    def test_phase_entry_persisted_result_binding(self) -> None:
        entry = self.reviewed_entry(self.store, self.result.registration.phase_ids["a"],
                                    the_design=design(related={"w1": (rr.RelatedSpec("must_read", "docs/a.md"),)}))
        review = ReviewStore(self.store)
        consumption = review.read_consumption(entry.consumption_id)
        result = consumption.persisted_result
        registration = entry.registration
        chain = self.chain(self.store, entry.review_run_id)
        first = chain.generations[0]
        kp = git(self.store.root, "rev-parse", "HEAD~1").strip()
        parent = git(self.store.root, "rev-parse", "HEAD~2").strip()
        material = review.read_candidate_snapshot(first.candidate_hash).material
        content = planning.candidate_content(material)
        context = review.read_task_input(first.accepted_tasks[0]["task_id"]).request_envelope["context"]
        expected = rr.expected_projection(self.store, material, context, parent)
        items = list(content["works"]) + [content["integration"], content["confirmation"]]
        self.assertEqual(
            {
                "contract": "review-v1-planning-persisted-result-v1",
                "request_digest": planning.request_digest_of(first.operation_identity),
                "registration_commit": kp,
                "registration_parent": parent,
                "branch": "refs/heads/main",
                "registration_delta_digest": expected.delta_digest(kp),
                "semantic_projection_digest": rr.reviewed_projection(material).identity(),
                "adapter_identity": "phase-entry-design-adapter-v1",
                "loader_identity": context["loader_identity"],
                "phase_id": registration.phase_id,
                "roadmap_id": content["roadmap_id"],
                "work_ids": [{"key": k, "id": v} for k, v in registration.work_ids.items()],
                "integration_work_id": registration.integration_id,
                "confirmation_work_id": registration.confirmation_id,
                # planned_next w1 -> w2, then the integration dependencies, then the confirmation dependency
                "roadmap_relation_ids": [relation["id"] for relation in content["relations"]],
                "related_relation_ids": [related["id"] for item in items for related in item["related"]],
                "canonical_first_work_id": registration.entry_work_id,
            },
            result,
        )
        self.assertEqual(4, len(result["roadmap_relation_ids"]))
        self.assertEqual(1, len(result["related_relation_ids"]))
        self.assertEqual(content["canonical_first_work"]["id"], result["canonical_first_work_id"])
        self.assertEqual(
            (entry.receipt_id, entry.review_run_id, 3, "phase-entry-design-v1", first.candidate_hash,
             first.operation_identity, entry.mutation_id, registration.phase_id),
            (consumption.receipt_id, consumption.review_run_id, consumption.review_generation, consumption.review_kind,
             consumption.authorized_candidate_hash, consumption.operation_identity, consumption.operation_mutation_id,
             consumption.target_identity),
        )


class UniquenessTests(_RegisteredCase):
    def _second(self, **changes) -> records.PlanningConsumption:
        return replace(self.consumption, consumption_id="rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV", **changes)

    def test_one_receipt_at_most_one_consumption(self) -> None:
        self.write(review_paths.consumption_rel("rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV"), self._second().to_record())
        with self.assertRaises(ValidationError) as raised:
            self.review.consumption_by_receipt()
        self.assertEqual("review_consumption_conflict", raised.exception.code)
        self.assertIn("review_consumption_conflict", [p.code for p in validate_review(self.store)])

    def test_a_second_consumption_of_the_registration_commit(self) -> None:
        second = self._second(receipt_id="rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                              target_identity=self.consumption.target_identity)
        second = replace(second, persisted_result={**second.persisted_result})
        self.write(review_paths.consumption_rel(second.consumption_id), second.to_record())
        with self.assertRaises(ValidationError) as raised:
            self.review.planning_consumption_by_commit()
        self.assertEqual("review_consumption_conflict", raised.exception.code)

    def test_a_second_consumption_of_the_target(self) -> None:
        second = self._second(receipt_id="rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV")
        result = dict(second.persisted_result)
        result["registration_commit"] = "f" * 40
        second = replace(second, persisted_result=result)
        self.write(review_paths.consumption_rel(second.consumption_id), second.to_record())
        with self.assertRaises(ValidationError) as raised:
            self.review.planning_consumption_by_target()
        self.assertEqual("review_consumption_conflict", raised.exception.code)
        self.assertIn("review_consumption_conflict", [p.code for p in validate_review(self.store)])


class CommittedMismatchTests(_RegisteredCase):
    """What a Consumption claims is re-proven from committed objects: a wrong claim keeps the barrier holding."""

    def _proof_of_forged(self, consumption: records.PlanningConsumption) -> tuple[str, str] | None:
        kp = self.consumption.persisted_result["registration_commit"]
        relative = review_paths.consumption_rel(consumption.consumption_id)
        forged = forge_commit(self.store, kp, relative, serialize.canonical_text(consumption.to_record()))
        (run,) = [found for found in publication.registered_runs(self.store.root, forged)]
        return publication.committed_planning_proof(self.store.root, forged, run)

    def test_a_commit_identity_mismatch_is_refused(self) -> None:
        result = dict(self.consumption.persisted_result)
        result["registration_commit"] = "e" * 40
        failed = self._proof_of_forged(replace(self.consumption, persisted_result=result))
        self.assertEqual("CP9", failed[0])

    def test_a_candidate_mismatch_is_refused(self) -> None:
        forged = replace(self.consumption, authorized_candidate_hash="d" * 64)
        failed = self._proof_of_forged(forged)
        self.assertEqual("CP8", failed[0])
        self.write(review_paths.consumption_rel(self.consumption.consumption_id), forged.to_record())
        self.assertIn("review_record_conflict", [p.code for p in validate_review(self.store)])


class VersionTests(unittest.TestCase):
    def _v2(self) -> dict:
        return {
            "schema": "review-consumption", "version": 2,
            "consumption_id": "rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV", "receipt_id": "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "review_run_id": "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV", "review_generation": 3, "review_kind": "roadmap-plan-v1",
            "authorized_candidate_hash": "a" * 64, "operation_identity": "roadmap-create:" + "b" * 64,
            "operation_mutation_id": "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV", "target_identity": "r_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "persisted_result": {
                "contract": "review-v1-planning-persisted-result-v1", "request_digest": "b" * 64,
                "registration_commit": "c" * 40, "registration_parent": "d" * 40, "branch": "refs/heads/main",
                "registration_delta_digest": "e" * 64, "semantic_projection_digest": "f" * 64,
                "adapter_identity": "roadmap-plan-adapter-v1", "loader_identity": "0" * 64,
                "roadmap_id": "r_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "phase_ids": [{"key": "a", "id": "p_01ARZ3NDEKTSV4RRFFQ69G5FAV"}],
                "relation_ids": ["rel_01ARZ3NDEKTSV4RRFFQ69G5FAV"],
            },
        }

    def test_version_2_reads_and_has_exactly_the_contract_fields(self) -> None:
        record = self._v2()
        found = records.consumption_from_record(record, "v2")
        self.assertIsInstance(found, records.PlanningConsumption)
        self.assertEqual(serialize.canonical_data(record), serialize.canonical_data(found.to_record()))
        self.assertEqual(
            ("schema", "version", "consumption_id", "receipt_id", "review_run_id", "review_generation", "review_kind",
             "authorized_candidate_hash", "operation_identity", "operation_mutation_id", "target_identity",
             "persisted_result"),
            records.PLANNING_CONSUMPTION_FIELDS,
        )
        for key in ("persisted_result",):
            broken = self._v2()
            broken[key] = {**broken[key], "extra": 1}
            with self.assertRaises(ValidationError):
                records.consumption_from_record(broken, "v2")
        missing = self._v2()
        del missing["persisted_result"]["loader_identity"]
        with self.assertRaises(ValidationError):
            records.consumption_from_record(missing, "v2")

    def _v2_phase_entry(self) -> dict:
        record = self._v2()
        record.update({"review_kind": "phase-entry-design-v1", "operation_identity": "phase-entry:" + "b" * 64,
                       "target_identity": "p_01ARZ3NDEKTSV4RRFFQ69G5FAV"})
        record["persisted_result"] = {
            **{key: record["persisted_result"][key] for key in records.PERSISTED_RESULT_COMMON_FIELDS},
            "adapter_identity": "phase-entry-design-adapter-v1",
            "phase_id": "p_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "roadmap_id": "r_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "work_ids": [{"key": "w1", "id": "w_01ARZ3NDEKTSV4RRFFQ69G5FAV"}],
            "integration_work_id": "w_01BX5ZZKBKACTAV9WEVGEMMVRZ",
            "confirmation_work_id": None,
            "roadmap_relation_ids": ["rel_01ARZ3NDEKTSV4RRFFQ69G5FAV"],
            "related_relation_ids": [],
            "canonical_first_work_id": "w_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        }
        return record

    def test_version_2_phase_entry_has_exactly_the_contract_fields(self) -> None:
        contract = {  # §16.1, typed from the contract
            "roadmap-plan-v1": ("roadmap_id", "phase_ids", "relation_ids"),
            "phase-entry-design-v1": ("phase_id", "roadmap_id", "work_ids", "integration_work_id", "confirmation_work_id",
                                      "roadmap_relation_ids", "related_relation_ids", "canonical_first_work_id"),
        }
        self.assertEqual(contract, dict(records.PERSISTED_RESULT_KIND_FIELDS))
        self.assertEqual(("contract", "request_digest", "registration_commit", "registration_parent", "branch",
                          "registration_delta_digest", "semantic_projection_digest", "adapter_identity",
                          "loader_identity"), records.PERSISTED_RESULT_COMMON_FIELDS)
        record = self._v2_phase_entry()
        found = records.consumption_from_record(record, "v2")
        self.assertIsInstance(found, records.PlanningConsumption)
        self.assertEqual(serialize.canonical_data(record), serialize.canonical_data(found.to_record()))
        extra = self._v2_phase_entry()
        extra["persisted_result"]["phase_ids"] = []  # a Roadmap field in a Phase-entry record
        with self.assertRaises(ValidationError):
            records.consumption_from_record(extra, "v2")
        for key in contract["phase-entry-design-v1"]:
            missing = self._v2_phase_entry()
            del missing["persisted_result"][key]
            with self.subTest(missing=key):
                with self.assertRaises(ValidationError):
                    records.consumption_from_record(missing, "v2")

    def test_an_adapter_identity_mismatch_is_refused(self) -> None:
        record = self._v2()
        record["persisted_result"]["adapter_identity"] = "phase-entry-design-adapter-v1"
        with self.assertRaises(ValidationError) as raised:
            records.consumption_from_record(record, "v2")
        self.assertEqual("review_record_invalid", raised.exception.code)

    def test_form_checks(self) -> None:
        for path, value in (
            (("persisted_result", "registration_commit"), "HEAD"),
            (("persisted_result", "branch"), "main"),
            (("persisted_result", "relation_ids"), ["rel_01ARZ3NDEKTSV4RRFFQ69G5FAV", "rel_01ARZ3NDEKTSV4RRFFQ69G5FAV"]),
            (("target_identity",), "r_01BX5ZZKBKACTAV9WEVGEMMVRZ"),
            (("review_kind",), "work-v1"),
        ):
            record = self._v2()
            holder = record
            for key in path[:-1]:
                holder = holder[key]
            holder[path[-1]] = value
            with self.subTest(path=path):
                with self.assertRaises(ValidationError):
                    records.consumption_from_record(record, "v2")

    def test_a_version_1_consumption_of_a_planning_kind_is_invalid(self) -> None:
        for kind, target, operation in (
            ("roadmap-plan-v1", "r_01ARZ3NDEKTSV4RRFFQ69G5FAV", "roadmap-create:x"),
            ("phase-entry-design-v1", "p_01ARZ3NDEKTSV4RRFFQ69G5FAV", "phase-entry:x"),
        ):
            v1 = {
                "schema": "review-consumption", "version": 1, "consumption_id": "rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "receipt_id": "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV", "review_run_id": "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "review_generation": 3, "review_kind": kind, "authorized_candidate_hash": "a" * 64,
                "operation_identity": operation, "operation_mutation_id": "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "terminal_event_id": None, "terminal_event_type": None, "target_identity": target,
                "authorized_result_commit_sha": None,
            }
            with self.subTest(kind):
                with self.assertRaises(ValidationError) as raised:
                    records.consumption_from_record(v1, "v1")
                self.assertEqual("review_record_invalid", raised.exception.code)
                # the P1 reader itself is unchanged: it reads the same record
                self.assertEqual(kind, records.Consumption.from_record(v1, "v1").review_kind)

    def test_version_1_records_are_unchanged(self) -> None:
        v1 = {
            "schema": "review-consumption", "version": 1, "consumption_id": "rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "receipt_id": "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV", "review_run_id": "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "review_generation": 1, "review_kind": "work-completion-v1", "authorized_candidate_hash": "a" * 64,
            "operation_identity": "start:x", "operation_mutation_id": "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "terminal_event_id": "evt_01ARZ3NDEKTSV4RRFFQ69G5FAV", "terminal_event_type": "work_completed",
            "target_identity": "w_01ARZ3NDEKTSV4RRFFQ69G5FAV", "authorized_result_commit_sha": "c" * 40,
        }
        found = records.consumption_from_record(v1, "v1")
        self.assertIsInstance(found, records.Consumption)
        self.assertEqual(v1, found.to_record())
        self.assertEqual(records.CONSUMPTION_FIELDS, tuple(v1))
        with self.assertRaises(ValidationError):
            records.consumption_from_record({**v1, "version": 3}, "v3")


if __name__ == "__main__":
    unittest.main()
