"""Candidate 7 §4 / R8-R10: the three projections and the adapter round trip.

Evidence and Review-validity completeness live in test_review_completeness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import unittest

from workline.errors import ValidationError
from workline.review import projections
from workline.review.adapter import (
    PersistedProjectionAdapter,
    ReservedIds,
    prove_expected_scope,
    prove_round_trip,
)

class ProjectionTests(unittest.TestCase):
    def test_the_three_kinds_are_distinct(self) -> None:
        self.assertEqual(
            ("reviewed_artifact", "authorized_transition", "operation_metadata"), projections.PROJECTION_KINDS
        )
        artifact = projections.reviewed_artifact("v1", {"a": 1})
        transition = projections.authorized_transition("v1", {"a": 1})
        metadata = projections.operation_metadata("v1", {"a": 1})
        identities = {artifact.identity(), transition.identity(), metadata.identity()}
        self.assertEqual(3, len(identities), "same content, different kinds must not share an identity")

    def test_operation_metadata_is_never_normative(self) -> None:
        """Candidate 7 §4.3's absolute rule, as one mechanical statement."""
        self.assertFalse(projections.normative(projections.OPERATION_METADATA))
        self.assertFalse(projections.operation_metadata("v1", {}).normative)
        self.assertTrue(projections.normative(projections.REVIEWED_ARTIFACT))
        self.assertTrue(projections.normative(projections.AUTHORIZED_TRANSITION))

    def test_normative_projections_exclude_metadata(self) -> None:
        found = projections.ProjectionSet(
            reviewed_artifact=projections.reviewed_artifact("v1", {"a": 1}),
            authorized_transition=projections.authorized_transition("v1", {"b": 2}),
            operation_metadata=projections.operation_metadata("v1", {"c": 3}),
        )
        kinds = {p.kind for p in found.normative_projections()}
        self.assertEqual({projections.REVIEWED_ARTIFACT, projections.AUTHORIZED_TRANSITION}, kinds)

    def test_a_slot_refuses_a_projection_of_another_kind(self) -> None:
        with self.assertRaises(ValidationError):
            projections.ProjectionSet(reviewed_artifact=projections.operation_metadata("v1", {}))

    def test_identity_does_not_depend_on_key_order(self) -> None:
        first = projections.reviewed_artifact("v1", {"a": 1, "b": 2})
        second = projections.reviewed_artifact("v1", {"b": 2, "a": 1})
        self.assertTrue(first.same_as(second))

    def test_a_projection_refuses_content_the_canonical_form_cannot_carry(self) -> None:
        with self.assertRaises(ValidationError):
            projections.reviewed_artifact("v1", {"a": 1.5})

    def test_a_missing_projection_is_not_equal_to_a_present_one(self) -> None:
        with_metadata = projections.ProjectionSet(
            reviewed_artifact=projections.reviewed_artifact("v1", {"a": 1}),
            operation_metadata=projections.operation_metadata("v1", {}),
        )
        without = projections.ProjectionSet(reviewed_artifact=projections.reviewed_artifact("v1", {"a": 1}))
        self.assertFalse(with_metadata.same_as(without))


# --------------------------------------------------------------------------- a synthetic adapter

@dataclass
class _Plan:
    """A tiny reviewed candidate: a name and phases named by caller key."""

    name: str
    phases: tuple[tuple[str, str], ...]


class _Store:
    """The canonical loader stand-in: what persistence put there, read back."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}


class _Adapter:
    """A synthetic ``PersistedProjectionAdapter``, complete enough to prove the protocol."""

    SEMANTICS = "synthetic-plan-v1"

    def adapter_identity(self) -> str:
        return "synthetic-plan-adapter"

    def loader_identity(self) -> str:
        return "synthetic-loader-v1"

    def normalize_candidate(self, candidate: _Plan, reserved: ReservedIds) -> projections.Projection:
        return projections.reviewed_artifact(
            self.SEMANTICS,
            {
                "name": candidate.name,
                "phases": [{"id": reserved.resolve(key), "desired": desired} for key, desired in candidate.phases],
            },
        )

    def project_expected(self, candidate: _Plan, reserved: ReservedIds, base: Any) -> projections.ProjectionSet:
        return projections.ProjectionSet(
            reviewed_artifact=self.normalize_candidate(candidate, reserved),
            authorized_transition=projections.authorized_transition(
                self.SEMANTICS, {"registers": [reserved.resolve(key) for key, _ in candidate.phases]}
            ),
        )

    def persist(self, candidate: _Plan, reserved: ReservedIds, store: _Store) -> None:
        store.rows[candidate.name] = {
            "name": candidate.name,
            "phases": [{"id": reserved.resolve(key), "desired": desired} for key, desired in candidate.phases],
        }

    def load_persisted(self, result_identity: str, view: _Store) -> dict[str, Any]:
        if result_identity not in view.rows:
            raise ValidationError(f"nothing persisted under {result_identity!r}", code="review_adapter_unresolved")
        return view.rows[result_identity]

    def normalize_persisted(self, loaded: dict[str, Any]) -> projections.Projection:
        return projections.reviewed_artifact(self.SEMANTICS, dict(loaded))


PLAN = _Plan("plan-a", (("design", "designed"), ("build", "built")))
RESERVED = ReservedIds({"design": "p_01ARZ3NDEKTSV4RRFFQ69G5FAV", "build": "p_01ARZ3NDEKTSV4RRFFQ69G5FAW"})


class AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = _Adapter()
        self.store = _Store()

    def test_the_synthetic_adapter_satisfies_the_protocol(self) -> None:
        self.assertIsInstance(self.adapter, PersistedProjectionAdapter)

    def test_a_faithful_round_trip_holds(self) -> None:
        self.adapter.persist(PLAN, RESERVED, self.store)
        result = prove_round_trip(self.adapter, PLAN, RESERVED, PLAN.name, self.store)
        self.assertTrue(result.matched, result.reason)
        result.require()

    def test_a_semantic_mismatch_fails(self) -> None:
        self.adapter.persist(PLAN, RESERVED, self.store)
        self.store.rows[PLAN.name]["phases"][0]["desired"] = "something else"
        result = prove_round_trip(self.adapter, PLAN, RESERVED, PLAN.name, self.store)
        self.assertFalse(result.matched)
        with self.assertRaises(ValidationError) as caught:
            result.require()
        self.assertEqual("review_roundtrip_mismatch", caught.exception.code)

    def test_a_byte_identical_but_semantically_different_reload_fails(self) -> None:
        """Equality is over normalized meaning, not over what the writer believed."""
        self.adapter.persist(PLAN, RESERVED, self.store)
        self.store.rows[PLAN.name]["phases"].append({"id": "p_01ARZ3NDEKTSV4RRFFQ69G5FAX", "desired": "extra"})
        self.assertFalse(prove_round_trip(self.adapter, PLAN, RESERVED, PLAN.name, self.store).matched)

    def test_a_semantics_version_change_fails(self) -> None:
        self.adapter.persist(PLAN, RESERVED, self.store)

        class _Newer(_Adapter):
            def normalize_persisted(self, loaded):
                return projections.reviewed_artifact("synthetic-plan-v2", dict(loaded))

        result = prove_round_trip(_Newer(), PLAN, RESERVED, PLAN.name, self.store)
        self.assertFalse(result.matched)
        self.assertIn("semantics version", result.reason)

    def test_identity_is_never_recovered_by_resemblance(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            self.adapter.normalize_candidate(_Plan("p", (("unreserved", "x"),)), RESERVED)
        self.assertEqual("review_adapter_unresolved", caught.exception.code)

    def test_an_existing_canonical_endpoint_resolves_to_itself(self) -> None:
        existing = "p_01ARZ3NDEKTSV4RRFFQ69G5FAZ"
        self.assertEqual(existing, RESERVED.resolve_existing(existing, {existing}))
        with self.assertRaises(ValidationError):
            RESERVED.resolve_existing("p_nothing", set())

    def test_scope_equality_is_separate_from_semantic_equality(self) -> None:
        expected = self.adapter.project_expected(PLAN, RESERVED, None)
        extra = projections.ProjectionSet(
            reviewed_artifact=expected.reviewed_artifact,
            authorized_transition=expected.authorized_transition,
            operation_metadata=projections.operation_metadata(_Adapter.SEMANTICS, {"unplanned": True}),
        )
        self.assertTrue(prove_expected_scope(expected, expected).matched)
        self.assertFalse(prove_expected_scope(expected, extra).matched)


if __name__ == "__main__":
    unittest.main()
