"""Candidate 7 §4 / R8-R11: the three projections, the adapter round trip, and Evidence completeness."""

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
from workline.review.closure import (
    COMPLETE,
    DENIED,
    GIT_STATE,
    NETWORK,
    NOT_REQUIRED,
    OBSERVED,
    PINNED,
    REPOSITORY_FILES,
    REVIEW_PROVENANCE,
    RUNTIME_TOOLCHAIN,
    SUBPROCESS,
    UNKNOWN,
    ClassCoverage,
    EvidenceDeclaration,
    ReviewProvenance,
    ReviewValidityClosure,
    may_reuse,
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


# --------------------------------------------------------------------------- evidence / closure

def _declaration(**overrides: Any) -> EvidenceDeclaration:
    defaults: dict[str, Any] = {
        "adapter_identity": "tests-adapter",
        "implementation_version": "1.0",
        "required": (REPOSITORY_FILES, SUBPROCESS, NETWORK),
        "coverage": (
            ClassCoverage(REPOSITORY_FILES, OBSERVED, basis="tree walk", identities=("a" * 64,)),
            ClassCoverage(SUBPROCESS, PINNED, basis="pinned toolchain"),
            ClassCoverage(NETWORK, DENIED, basis="sandbox denies sockets"),
        ),
    }
    defaults.update(overrides)
    return EvidenceDeclaration(**defaults)


PROVENANCE = ReviewProvenance(
    candidate_hash="a" * 64,
    candidate_material_digest="b" * 64,
    task_input_digest="c" * 64,
    request_digest="d" * 64,
    reviewer_identity="reviewer-a",
    reviewer_version="3.1",
    review_context_hash="e" * 64,
    effective_policy_hash="f" * 64,
)


def _closure(**overrides: Any) -> ReviewValidityClosure:
    defaults: dict[str, Any] = {
        "version": 1,
        "base_commit_sha": "0" * 40,
        "provenance": PROVENANCE,
        "evidence_dependencies": (_declaration(),),
        "git_semantics": {"commit_signing": "disabled"},
        "completeness_basis": "every material surface enumerated by the adapter contract",
    }
    defaults.update(overrides)
    return ReviewValidityClosure(**defaults)


class EvidenceTests(unittest.TestCase):
    def test_a_complete_declaration_is_reusable(self) -> None:
        declaration = _declaration()
        self.assertEqual(COMPLETE, declaration.completeness())
        self.assertTrue(declaration.reusable())

    def test_a_required_class_with_no_coverage_is_unknown(self) -> None:
        declaration = _declaration(required=(REPOSITORY_FILES, SUBPROCESS, NETWORK, GIT_STATE))
        self.assertEqual((GIT_STATE,), declaration.unaccounted())
        self.assertEqual(UNKNOWN, declaration.completeness())
        self.assertFalse(declaration.reusable())

    def test_unknown_coverage_does_not_account_for_a_class(self) -> None:
        declaration = _declaration(
            coverage=(
                ClassCoverage(REPOSITORY_FILES, OBSERVED, basis="tree walk"),
                ClassCoverage(SUBPROCESS, PINNED, basis="pinned"),
                ClassCoverage(NETWORK, UNKNOWN),
            )
        )
        self.assertEqual((NETWORK,), declaration.unaccounted())
        self.assertFalse(declaration.reusable())

    def test_not_required_positively_excludes_a_class(self) -> None:
        declaration = _declaration(
            coverage=(
                ClassCoverage(REPOSITORY_FILES, OBSERVED, basis="tree walk"),
                ClassCoverage(SUBPROCESS, NOT_REQUIRED, basis="closed execution contract spawns nothing"),
                ClassCoverage(NETWORK, DENIED, basis="sandbox"),
            )
        )
        self.assertTrue(declaration.complete())

    def test_coverage_must_state_a_basis(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            ClassCoverage(NETWORK, DENIED)
        self.assertIn("shown, not asserted", str(caught.exception))

    def test_a_class_outside_the_vocabulary_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            ClassCoverage("telepathy", OBSERVED, basis="x")
        with self.assertRaises(ValidationError):
            _declaration(required=("telepathy",))

    def test_a_class_covered_twice_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            _declaration(
                coverage=(
                    ClassCoverage(NETWORK, DENIED, basis="a"),
                    ClassCoverage(NETWORK, OBSERVED, basis="b"),
                )
            )


class ClosureTests(unittest.TestCase):
    def test_git_write_compatibility_is_not_review_validity(self) -> None:
        """A closure with no stated basis is unknown however untouched the paths are."""
        self.assertEqual(UNKNOWN, _closure(completeness_basis="").completeness())

    def test_a_complete_closure_with_unchanged_identities_reuses(self) -> None:
        decision = may_reuse(_closure(), _closure())
        self.assertTrue(decision.reusable, decision.reason)

    def test_one_unknown_evidence_dependency_makes_the_closure_unknown(self) -> None:
        closure = _closure(evidence_dependencies=(_declaration(), _declaration(required=(GIT_STATE,), coverage=())))
        self.assertEqual(UNKNOWN, closure.completeness())
        self.assertFalse(may_reuse(closure, closure).reusable)

    def test_changed_candidate_provenance_invalidates_reuse(self) -> None:
        import dataclasses

        changed = dataclasses.replace(PROVENANCE, candidate_material_digest="9" * 64)
        decision = may_reuse(_closure(), _closure(provenance=changed))
        self.assertFalse(decision.reusable)
        self.assertIn("provenance", decision.reason)

    def test_changed_task_provenance_invalidates_reuse(self) -> None:
        import dataclasses

        changed = dataclasses.replace(PROVENANCE, task_input_digest="9" * 64)
        self.assertFalse(may_reuse(_closure(), _closure(provenance=changed)).reusable)

    def test_same_candidate_hash_with_changed_material_still_invalidates(self) -> None:
        """Equal results do not make equal reconstruction (``R6`` §4)."""
        import dataclasses

        changed = dataclasses.replace(PROVENANCE, candidate_material_digest="9" * 64)
        self.assertEqual(PROVENANCE.candidate_hash, changed.candidate_hash)
        self.assertFalse(may_reuse(_closure(), _closure(provenance=changed)).reusable)

    def test_changed_builder_version_invalidates_reuse(self) -> None:
        import dataclasses

        before = dataclasses.replace(PROVENANCE, builder_identity="b", builder_version="1.0")
        after = dataclasses.replace(PROVENANCE, builder_identity="b", builder_version="1.1")
        self.assertFalse(may_reuse(_closure(provenance=before), _closure(provenance=after)).reusable)

    def test_changed_tool_runtime_identity_invalidates_reuse(self) -> None:
        decision = may_reuse(
            _closure(tool_runtime_dependencies=("python-3.14",)),
            _closure(tool_runtime_dependencies=("python-3.15",)),
        )
        self.assertFalse(decision.reusable)
        self.assertIn("tool/runtime", decision.reason)

    def test_changed_git_semantics_invalidates_reuse(self) -> None:
        decision = may_reuse(_closure(), _closure(git_semantics={"commit_signing": "enabled"}))
        self.assertFalse(decision.reusable)

    def test_changed_evidence_declaration_invalidates_reuse(self) -> None:
        other = _declaration(implementation_version="2.0")
        self.assertFalse(may_reuse(_closure(), _closure(evidence_dependencies=(other,))).reusable)

    def test_the_closure_digest_covers_provenance_and_completeness(self) -> None:
        import dataclasses

        changed = dataclasses.replace(PROVENANCE, request_digest="9" * 64)
        self.assertNotEqual(_closure().digest(), _closure(provenance=changed).digest())

    def test_the_vocabulary_carries_the_classes_the_contracts_name(self) -> None:
        from workline.review.closure import DEPENDENCY_CLASSES, VOCABULARY

        self.assertEqual("review-dependency-classes-v1", VOCABULARY)
        for name in (
            REPOSITORY_FILES,
            SUBPROCESS,
            NETWORK,
            GIT_STATE,
            RUNTIME_TOOLCHAIN,
            REVIEW_PROVENANCE,
        ):
            self.assertIn(name, DEPENDENCY_CLASSES)
            ClassCoverage(name, PINNED, basis="declared by the adapter contract")


if __name__ == "__main__":
    unittest.main()
