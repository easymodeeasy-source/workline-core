"""A Work-terminal Consumption says which artifact it consumed (P3 F1 §11.3, Gate 2 / F3 IP-5).

A review-v1 Work may complete correctly with no result-path change and no deleted path, and START
then makes no result commit at all: ordinary and correct, not a degenerate case (F1 §11.1, and the
frozen Option B of §11.2). No empty commit is ever synthesized to stand in for one.

At the landed baseline that Work had no valid Consumption. The record applied an all-or-none rule
over the Work-terminal triple - ``terminal_event_id``, ``terminal_event_type``,
``authorized_result_commit_sha`` - so binding the terminal event demanded a result commit the Work
does not have, and the empty-artifact Consumption was unrepresentable. The record could not even
carry the field that would say so: ``_require_exact_fields`` refused ``artifact_kind`` as unknown.

F1 §11.3 replaces that rule. The terminal event is the Work-kind discriminator, and
``artifact_kind`` states which of the two authorized shapes the Consumption binds:

```text
Work-kind        terminal_event_id is not None    "result_commit" | "empty"    required
any other kind   terminal_event_id is None        null                         required
```

The field is always emitted, present-as-null, never omitted, so "absent" and "null" are never the
same question.

This is Gate 2 alone. The Candidate side of the F3 §14 agreement does not exist yet, and the
comparison of the two is read and proven by the F3 terminal-stage and C-2(K2) proofs, not here.
Gate 3 (the activation producer) is not implemented, and the tests below pin that it is absent.
"""

from __future__ import annotations

import unittest

from helpers import WorklineTestCase
from workline.errors import ValidationError
from workline.review import paths, records, serialize
from workline.review.records import CONSUMPTION_ARTIFACT_KINDS, CONSUMPTION_FIELDS, Consumption
from workline.review.store import ReviewStore

from test_review_authorization import CONSUMPTION_ID, consumption_record

#: The Work-terminal triple the old all-or-none rule ranged over, and the field F1 §11.3 adds.
NON_WORK_NULLS = ("terminal_event_id", "terminal_event_type", "authorized_result_commit_sha", "artifact_kind")

EMPTY_ARTIFACT = {"artifact_kind": "empty", "authorized_result_commit_sha": None}
NON_WORK = dict.fromkeys(NON_WORK_NULLS)


def read(record: dict) -> Consumption:
    return Consumption.from_record(record, "consumption")


def refusal(case: unittest.TestCase, record: dict) -> ValidationError:
    with case.assertRaises(ValidationError) as caught:
        read(record)
    case.assertEqual(caught.exception.code, "review_record_invalid")
    return caught.exception


class SchemaTests(unittest.TestCase):
    """The field set gains exactly one entry, and the record always emits it."""

    def test_the_field_set_gains_exactly_one_entry_and_it_is_last(self) -> None:
        self.assertEqual(CONSUMPTION_FIELDS[-1], "artifact_kind")
        self.assertEqual(CONSUMPTION_FIELDS.count("artifact_kind"), 1)

    def test_the_allowed_values_are_exactly_the_two_frozen_ones(self) -> None:
        self.assertEqual(CONSUMPTION_ARTIFACT_KINDS, ("result_commit", "empty"))

    def test_a_record_that_omits_the_key_is_invalid(self) -> None:
        """Present-as-null, never omitted: a reader never has to tell absent from null."""
        record = consumption_record()
        del record["artifact_kind"]
        self.assertIn("artifact_kind", str(refusal(self, record)))

    def test_a_non_work_consumption_emits_the_key_as_null(self) -> None:
        emitted = read(consumption_record(**NON_WORK)).to_record()
        self.assertIn("artifact_kind", emitted)
        self.assertIsNone(emitted["artifact_kind"])

    def test_the_field_is_declared_last_so_positional_construction_still_builds(self) -> None:
        """F1 §11.3's implementation note: existing positional non-Work constructions keep working."""
        positional = Consumption(
            "rcs_01ARZ3NDEKTSV4RRFFQ69G5FAV", "rcp_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "rr_01ARZ3NDEKTSV4RRFFQ69G5FAV", 3, "roadmap_planning", "b" * 64, "start",
            "mut_01ARZ3NDEKTSV4RRFFQ69G5FAV", None, None, "rm_01ARZ3NDEKTSV4RRFFQ69G5FAV", None,
        )
        self.assertIsNone(positional.artifact_kind)
        self.assertFalse(positional.work_kind)


class EmptyArtifactTests(unittest.TestCase):
    """The baseline defect: the Consumption of a result-less Work is now representable."""

    def test_an_empty_artifact_work_consumption_is_valid(self) -> None:
        found = read(consumption_record(**EMPTY_ARTIFACT))
        self.assertTrue(found.work_kind)
        self.assertEqual(found.artifact_kind, "empty")
        self.assertIsNone(found.authorized_result_commit_sha)

    def test_it_still_binds_its_terminal_event_and_its_work(self) -> None:
        """Nothing is invented and nothing is lost: the binding is the record's other fields."""
        found = read(consumption_record(**EMPTY_ARTIFACT))
        self.assertEqual(found.terminal_event_id, consumption_record()["terminal_event_id"])
        self.assertEqual(found.terminal_event_type, "work_completed")
        self.assertEqual(found.work_id, consumption_record()["target_identity"])

    def test_no_placeholder_commit_is_ever_written(self) -> None:
        self.assertIsNone(read(consumption_record(**EMPTY_ARTIFACT)).to_record()["authorized_result_commit_sha"])


class ResultCommitTests(unittest.TestCase):
    """The result-bearing shape is unchanged, and now says so explicitly."""

    def test_a_result_commit_consumption_is_valid(self) -> None:
        found = read(consumption_record())
        self.assertEqual(found.artifact_kind, "result_commit")
        self.assertEqual(found.authorized_result_commit_sha, "a" * 40)

    def test_a_sha256_object_id_is_still_accepted(self) -> None:
        found = read(consumption_record(authorized_result_commit_sha="a" * 64))
        self.assertEqual(found.authorized_result_commit_sha, "a" * 64)

    def test_a_short_commit_id_is_still_refused(self) -> None:
        self.assertIn("full commit id", str(refusal(self, consumption_record(authorized_result_commit_sha="a" * 7))))


class ContradictionTests(unittest.TestCase):
    """The kind and the commit say the same thing, or the record is not one."""

    def test_empty_with_a_result_commit_is_refused(self) -> None:
        record = consumption_record(artifact_kind="empty", authorized_result_commit_sha="a" * 40)
        self.assertIn("binds no result commit", str(refusal(self, record)))

    def test_result_commit_with_no_commit_is_refused(self) -> None:
        record = consumption_record(artifact_kind="result_commit", authorized_result_commit_sha=None)
        self.assertIn("full commit id", str(refusal(self, record)))

    def test_neither_field_is_ever_derived_from_the_other(self) -> None:
        """F3 §14: neither is computed, defaulted or filled in from the other - both are read."""
        for kind, commit in (("empty", "a" * 40), ("result_commit", None)):
            with self.subTest(artifact_kind=kind):
                refusal(self, consumption_record(artifact_kind=kind, authorized_result_commit_sha=commit))


class WorkKindValueTests(unittest.TestCase):
    """A Work-kind Consumption carries one of the two values, and nothing else."""

    def test_an_unknown_value_is_refused(self) -> None:
        self.assertIn("artifact_kind", str(refusal(self, consumption_record(artifact_kind="deleted_path"))))

    def test_null_on_a_work_kind_is_refused(self) -> None:
        self.assertIn("artifact_kind", str(refusal(self, consumption_record(artifact_kind=None))))

    def test_a_non_string_value_is_refused(self) -> None:
        for value in (True, 1, ["empty"], {"kind": "empty"}):
            with self.subTest(value=value):
                refusal(self, consumption_record(artifact_kind=value))

    def test_a_near_miss_spelling_is_refused(self) -> None:
        for value in ("Empty", "EMPTY", "result-commit", "resultcommit", "", " empty"):
            with self.subTest(value=value):
                refusal(self, consumption_record(artifact_kind=value))

    def test_the_terminal_event_type_rule_is_unchanged(self) -> None:
        record = consumption_record(terminal_event_type="work_cancelled")
        self.assertIn("work_completed", str(refusal(self, record)))

    def test_the_work_target_rule_is_unchanged(self) -> None:
        record = consumption_record(target_identity="rm_01ARZ3NDEKTSV4RRFFQ69G5FAV")
        self.assertIn("target_identity", str(refusal(self, record)))


class NonWorkKindTests(unittest.TestCase):
    """A Consumption that is not Work-kind carries all four as null."""

    def test_all_four_null_is_valid(self) -> None:
        found = read(consumption_record(review_kind="roadmap_planning", **NON_WORK))
        self.assertFalse(found.work_kind)
        self.assertIsNone(found.artifact_kind)
        self.assertIsNone(found.work_id)

    def test_an_artifact_kind_without_a_terminal_event_is_refused(self) -> None:
        record = consumption_record(**{**NON_WORK, "artifact_kind": "empty"})
        message = str(refusal(self, record))
        self.assertIn("artifact_kind", message)
        self.assertIn("without a terminal_event_id", message)

    def test_each_other_bound_field_without_a_terminal_event_is_still_refused(self) -> None:
        """The protection the old all-or-none rule gave this side is kept, and now covers four fields."""
        for name, value in (
            ("terminal_event_type", "work_completed"),
            ("authorized_result_commit_sha", "a" * 40),
            ("artifact_kind", "result_commit"),
        ):
            with self.subTest(field=name):
                self.assertIn(name, str(refusal(self, consumption_record(**{**NON_WORK, name: value}))))


class RoundTripTests(unittest.TestCase):
    """What the record emits reads back as the same Consumption."""

    def test_every_shape_round_trips_through_its_record(self) -> None:
        for label, overrides in (
            ("result_commit", {}),
            ("empty", EMPTY_ARTIFACT),
            ("non-Work", {"review_kind": "roadmap_planning", **NON_WORK}),
        ):
            with self.subTest(shape=label):
                record = consumption_record(**overrides)
                self.assertEqual(read(record).to_record(), record)
                self.assertEqual(read(read(record).to_record()), read(record))

    def test_the_canonical_bytes_carry_the_field(self) -> None:
        text = serialize.canonical_text(read(consumption_record(**EMPTY_ARTIFACT)).to_record())
        self.assertIn("artifact_kind", text)


class PersistenceTests(WorklineTestCase):
    """An empty-artifact Consumption survives the physical Review namespace."""

    def setUp(self) -> None:
        super().setUp()
        self.store = self.new_project()
        self.review = ReviewStore(self.store)

    def put(self, record: dict) -> None:
        target = self.store.root / paths.consumption_rel(CONSUMPTION_ID)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(serialize.canonical_bytes(record))

    def test_it_reads_back_from_the_namespace_unchanged(self) -> None:
        record = consumption_record(**EMPTY_ARTIFACT)
        self.put(record)
        found = self.review.read_consumption(CONSUMPTION_ID)
        self.assertEqual(found.artifact_kind, "empty")
        self.assertEqual(found.to_record(), record)

    def test_it_takes_its_place_in_the_terminal_event_index(self) -> None:
        record = consumption_record(**EMPTY_ARTIFACT)
        self.put(record)
        index = self.review.consumption_by_terminal_event()
        self.assertEqual(index[str(record["terminal_event_id"])].artifact_kind, "empty")

    def test_it_takes_its_place_in_the_receipt_index(self) -> None:
        record = consumption_record(**EMPTY_ARTIFACT)
        self.put(record)
        index = self.review.consumption_by_receipt()
        self.assertEqual(index[str(record["receipt_id"])].artifact_kind, "empty")


class GateBoundaryTests(unittest.TestCase):
    """Gate 2 is the record repair. It does not reach Gate 3, and it does not do F3 §14."""

    def test_the_candidate_side_of_the_f3_agreement_is_not_implemented_here(self) -> None:
        """F3 §14.1: Candidate.content.artifact_kind is F2/F3 body; Gate 2 owns the Consumption side."""
        self.assertFalse(hasattr(records, "Candidate"))
        self.assertNotIn("artifact_kind", records.CandidateSnapshot.__dataclass_fields__)

    def test_the_record_does_not_read_a_candidate_to_decide_its_own_field(self) -> None:
        """A valid Consumption is valid on its own terms; the agreement is proven at §14.3's points."""
        for kind, commit in (("result_commit", "a" * 40), ("empty", None)):
            with self.subTest(artifact_kind=kind):
                found = read(consumption_record(artifact_kind=kind, authorized_result_commit_sha=commit))
                self.assertEqual(found.artifact_kind, kind)

    def test_gate_3_activation_is_still_not_produced(self) -> None:
        """P3 F1 §12.3 / IP-7: the activation record type exists and nothing writes one."""
        self.assertTrue(hasattr(records, "WorkTerminalActivation"))
        self.assertTrue(hasattr(ReviewStore, "read_activation"))
        for writer in ("write_activation", "create_activation", "activate", "produce_activation"):
            with self.subTest(writer=writer):
                self.assertFalse(hasattr(ReviewStore, writer), f"ReviewStore.{writer} exists; Gate 3 stays unproduced")

    def test_the_review_v1_work_persistence_identity_is_still_not_dispatchable(self) -> None:
        """P3 F3 IP-1: git_commit still accepts the planning mode alone."""
        from workline import mutation

        self.assertEqual(mutation.PLANNING_COMMIT_MODE, "review-v1-planning-local-v1")
        self.assertFalse(hasattr(mutation, "WORK_COMMIT_MODE"))
        with self.assertRaises(ValidationError):
            mutation._validate_planning_commit({"mode": "review-v1-work-local-v2", "paths": [], "message": "m"})

    def test_gate_1_is_preserved(self) -> None:
        """The landed Event metadata carrier still carries, and still holds only lifecycle fields as lifecycle."""
        from workline.store import EVENT_LIFECYCLE_FIELDS, Event

        record = {
            "id": "evt_00000000000000000000000001", "type": "work_completed",
            "entity": "wrk_00000000000000000000000001", "at": "2026-09-27T00:00:00Z",
            "operation_contract": "review-v1", "review_generation": 3,
        }
        self.assertEqual(Event.from_record(record).to_record(), record)
        self.assertEqual(EVENT_LIFECYCLE_FIELDS, ("id", "type", "entity", "at"))


if __name__ == "__main__":
    unittest.main()
