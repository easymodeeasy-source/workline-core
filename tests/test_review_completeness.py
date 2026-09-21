"""P1-REV-006: completeness is a typed, positive proof - a description never makes anything complete."""

from __future__ import annotations

import dataclasses
from typing import Any
import unittest

from workline.errors import ValidationError
from workline.review import closure as c
from workline.review.closure import (
    COMPLETE,
    DENIED,
    DEPENDENCY_CLASSES,
    GIT_STATE,
    INVALIDATED,
    NETWORK,
    NOT_REQUIRED,
    OBSERVED,
    PINNED,
    REPOSITORY_FILES,
    REQUIRED_SURFACES,
    REUSABLE,
    REVIEW_PROVENANCE,
    RUNTIME_TOOLCHAIN,
    SUBPROCESS,
    SURFACE_COVERED,
    SURFACE_EVIDENCE,
    SURFACE_NOT_REQUIRED,
    SURFACE_TOOL_RUNTIME,
    SURFACE_UNKNOWN,
    UNKNOWN,
    ClassCoverage,
    EvidenceDeclaration,
    ReviewProvenance,
    ReviewValidityClosure,
    SurfaceClosure,
    may_reuse,
)

SANDBOX = c.denial("sandbox-net-deny", "2.1")
TRACER = c.observation("process-tracer", "4.0")
CLOSED = c.exclusion("closed-exec-contract", "1.0")
LISTER = c.enumeration("surface-enumerator", "1.3")


def declaration(covered: dict[str, ClassCoverage] | None = None, **fields: Any) -> EvidenceDeclaration:
    """A declaration accounting for every class: the given ones covered, all others excluded by proof."""
    covered = covered if covered is not None else {
        REPOSITORY_FILES: ClassCoverage(REPOSITORY_FILES, OBSERVED, proof=TRACER, identities=("a" * 64,)),
        SUBPROCESS: ClassCoverage(SUBPROCESS, PINNED, identities=("python-3.14.4",)),
        NETWORK: ClassCoverage(NETWORK, DENIED, proof=SANDBOX),
    }
    coverage = list(covered.values()) + [
        ClassCoverage(name, NOT_REQUIRED, proof=CLOSED) for name in DEPENDENCY_CLASSES if name not in covered
    ]
    defaults: dict[str, Any] = {
        "adapter_identity": "tests-adapter",
        "implementation_version": "1.0",
        "required": tuple(covered),
        "coverage": tuple(coverage),
    }
    defaults.update(fields)
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


def surfaces(**overrides: SurfaceClosure) -> tuple[SurfaceClosure, ...]:
    """Every required surface positively closed, each by a complete enumeration."""
    found = {
        name: SurfaceClosure(name, SURFACE_COVERED, identities=(f"{name}-identity",), proof=LISTER)
        for name in REQUIRED_SURFACES
    }
    found.update(overrides)
    return tuple(found.values())


def closure(**fields: Any) -> ReviewValidityClosure:
    defaults: dict[str, Any] = {
        "version": 1,
        "base_commit_sha": "0" * 40,
        "provenance": PROVENANCE,
        "surfaces": surfaces(),
        "evidence_dependencies": (declaration(),),
        "git_semantics": {"commit_signing": "disabled"},
    }
    defaults.update(fields)
    return ReviewValidityClosure(**defaults)


class EvidenceCoverageTests(unittest.TestCase):
    def test_every_class_accounted_with_typed_proof_is_complete(self) -> None:
        self.assertEqual(COMPLETE, declaration().completeness())
        self.assertTrue(declaration().reusable())

    def test_a_valid_typed_denial_is_complete(self) -> None:
        found = declaration({NETWORK: ClassCoverage(NETWORK, DENIED, proof=SANDBOX)})
        self.assertEqual(COMPLETE, found.completeness())

    def test_valid_pinned_concrete_identities_are_complete(self) -> None:
        found = declaration({SUBPROCESS: ClassCoverage(SUBPROCESS, PINNED, identities=("git-2.54", "python-3.14.4"))})
        self.assertEqual(COMPLETE, found.completeness())

    def test_required_subprocess_with_no_identity_or_proof_is_unknown(self) -> None:
        found = declaration({SUBPROCESS: ClassCoverage(SUBPROCESS, PINNED)})
        self.assertEqual((SUBPROCESS,), found.unaccounted())
        self.assertEqual(UNKNOWN, found.completeness())

    def test_required_network_with_omitted_coverage_is_unknown(self) -> None:
        # Every other class is excluded by proof; network is required and has no entry at all.
        coverage = tuple(ClassCoverage(name, NOT_REQUIRED, proof=CLOSED) for name in DEPENDENCY_CLASSES if name != NETWORK)
        found = EvidenceDeclaration("tests-adapter", "1.0", (NETWORK,), coverage)
        self.assertEqual((NETWORK,), found.unaccounted())
        self.assertEqual(UNKNOWN, found.completeness())

    def test_a_basis_string_alone_proves_nothing(self) -> None:
        for mode in (PINNED, OBSERVED, DENIED, NOT_REQUIRED):
            with self.subTest(mode=mode):
                entry = ClassCoverage(GIT_STATE, mode, basis="checked everything, trust me")
                self.assertFalse(entry.proven)
        found = declaration({GIT_STATE: ClassCoverage(GIT_STATE, PINNED, basis="checked everything")})
        self.assertEqual(UNKNOWN, found.completeness())

    def test_a_proof_of_the_wrong_kind_proves_nothing(self) -> None:
        self.assertFalse(ClassCoverage(NETWORK, DENIED, proof=TRACER).proven)
        self.assertFalse(ClassCoverage(SUBPROCESS, OBSERVED, proof=SANDBOX).proven)
        self.assertFalse(ClassCoverage(NETWORK, NOT_REQUIRED, proof=SANDBOX).proven)

    def test_a_proof_without_a_version_proves_nothing(self) -> None:
        self.assertFalse(ClassCoverage(NETWORK, DENIED, proof=c.denial("sandbox", "")).proven)

    def test_an_observation_mechanism_proves_an_empty_observation(self) -> None:
        """Zero observed instances is a proven "none" only because a mechanism observed them."""
        self.assertTrue(ClassCoverage(REPOSITORY_FILES, OBSERVED, proof=TRACER).proven)
        self.assertFalse(ClassCoverage(REPOSITORY_FILES, OBSERVED).proven)

    def test_a_class_merely_absent_from_required_is_not_thereby_not_required(self) -> None:
        """Not required is its own positive claim; it is never inferred from absence."""
        found = declaration()
        coverage = tuple(e for e in found.coverage if e.dependency_class != GIT_STATE)
        found = EvidenceDeclaration("tests-adapter", "1.0", found.required, coverage)
        self.assertNotIn(GIT_STATE, found.required)
        self.assertEqual((GIT_STATE,), found.unaccounted())
        self.assertEqual(UNKNOWN, found.completeness())

    def test_unknown_coverage_never_accounts_for_a_class(self) -> None:
        found = declaration({NETWORK: ClassCoverage(NETWORK, UNKNOWN)})
        self.assertEqual((NETWORK,), found.unaccounted())

    def test_a_class_both_required_and_excluded_is_contradictory(self) -> None:
        base = declaration()
        coverage = tuple(e for e in base.coverage if e.dependency_class != GIT_STATE) + (
            ClassCoverage(GIT_STATE, NOT_REQUIRED, proof=CLOSED),
        )
        with self.assertRaises(ValidationError):
            EvidenceDeclaration("tests-adapter", "1.0", base.required + (GIT_STATE,), coverage)

    def test_a_class_outside_the_vocabulary_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            ClassCoverage("telepathy", PINNED, identities=("x",))
        with self.assertRaises(ValidationError):
            declaration(required=("telepathy",))

    def test_a_class_covered_twice_is_refused(self) -> None:
        base = declaration()
        with self.assertRaises(ValidationError):
            EvidenceDeclaration("tests-adapter", "1.0", base.required, base.coverage + (ClassCoverage(NETWORK, DENIED, proof=SANDBOX),))

    def test_the_vocabulary_carries_the_classes_the_contracts_name(self) -> None:
        self.assertEqual("review-dependency-classes-v1", c.VOCABULARY)
        for name in (REPOSITORY_FILES, SUBPROCESS, NETWORK, GIT_STATE, RUNTIME_TOOLCHAIN, REVIEW_PROVENANCE):
            self.assertIn(name, DEPENDENCY_CLASSES)


class ClosureCompletenessTests(unittest.TestCase):
    def test_a_fully_closed_closure_is_complete(self) -> None:
        self.assertEqual(COMPLETE, closure().completeness())

    def test_a_completeness_basis_string_alone_is_unknown(self) -> None:
        found = closure(surfaces=(), completeness_basis="checked everything")
        self.assertEqual(UNKNOWN, found.completeness())
        self.assertEqual(REQUIRED_SURFACES, found.unproven_surfaces())

    def test_git_write_compatibility_is_not_review_validity(self) -> None:
        """No surface closed at all - however untouched the paths - is unknown."""
        self.assertEqual(UNKNOWN, closure(surfaces=()).completeness())

    def test_an_empty_surface_without_positive_proof_is_unknown(self) -> None:
        unproven = SurfaceClosure(SURFACE_TOOL_RUNTIME, SURFACE_COVERED)
        self.assertEqual(UNKNOWN, closure(surfaces=surfaces(tool_runtime=unproven)).completeness())

    def test_an_empty_surface_proven_by_enumeration_is_complete(self) -> None:
        """"Nothing depended on" is complete only when a mechanism enumerated the surface and found nothing."""
        proven_none = SurfaceClosure(SURFACE_TOOL_RUNTIME, SURFACE_COVERED, proof=LISTER)
        self.assertEqual(COMPLETE, closure(surfaces=surfaces(tool_runtime=proven_none)).completeness())

    def test_a_listed_surface_without_enumeration_proof_is_unknown(self) -> None:
        listed = SurfaceClosure(SURFACE_TOOL_RUNTIME, SURFACE_COVERED, identities=("python-3.14",))
        self.assertEqual(UNKNOWN, closure(surfaces=surfaces(tool_runtime=listed)).completeness())

    def test_a_surface_excluded_by_proof_is_closed(self) -> None:
        excluded = SurfaceClosure(SURFACE_EVIDENCE, SURFACE_NOT_REQUIRED, proof=CLOSED)
        self.assertEqual(COMPLETE, closure(surfaces=surfaces(evidence=excluded), evidence_dependencies=()).completeness())

    def test_evidence_declared_while_the_surface_claims_none_is_unknown(self) -> None:
        excluded = SurfaceClosure(SURFACE_EVIDENCE, SURFACE_NOT_REQUIRED, proof=CLOSED)
        self.assertEqual(UNKNOWN, closure(surfaces=surfaces(evidence=excluded)).completeness())

    def test_an_unknown_surface_is_unknown(self) -> None:
        self.assertEqual(UNKNOWN, closure(surfaces=surfaces(policy=SurfaceClosure("policy", SURFACE_UNKNOWN))).completeness())

    def test_a_duplicated_surface_is_unknown(self) -> None:
        doubled = surfaces() + (SurfaceClosure(SURFACE_TOOL_RUNTIME, SURFACE_COVERED, proof=LISTER),)
        self.assertEqual(UNKNOWN, closure(surfaces=doubled).completeness())

    def test_provenance_can_never_be_excluded(self) -> None:
        excluded = SurfaceClosure(REVIEW_PROVENANCE, SURFACE_NOT_REQUIRED, proof=CLOSED)
        self.assertEqual(UNKNOWN, closure(surfaces=surfaces(review_provenance=excluded)).completeness())
        self.assertEqual(UNKNOWN, closure(provenance=None).completeness())

    def test_one_unknown_evidence_declaration_makes_the_closure_unknown(self) -> None:
        weak = declaration({NETWORK: ClassCoverage(NETWORK, DENIED)})
        self.assertEqual(UNKNOWN, closure(evidence_dependencies=(declaration(), weak)).completeness())


class ReuseTests(unittest.TestCase):
    def test_complete_and_unchanged_is_reusable(self) -> None:
        decision = may_reuse(closure(), closure())
        self.assertEqual((True, REUSABLE), (decision.reusable, decision.state))

    def test_unknown_on_either_side_is_no_reuse_and_keeps_unknown(self) -> None:
        for before, after in ((closure(surfaces=()), closure()), (closure(), closure(surfaces=()))):
            decision = may_reuse(before, after)
            self.assertEqual((False, UNKNOWN), (decision.reusable, decision.state))

    def test_a_changed_surface_identity_is_no_reuse(self) -> None:
        changed = SurfaceClosure(SURFACE_TOOL_RUNTIME, SURFACE_COVERED, identities=("python-3.15",), proof=LISTER)
        decision = may_reuse(closure(), closure(surfaces=surfaces(tool_runtime=changed)))
        self.assertEqual((False, INVALIDATED), (decision.reusable, decision.state))

    def test_a_surface_proven_by_a_different_mechanism_is_no_reuse(self) -> None:
        other = SurfaceClosure(SURFACE_TOOL_RUNTIME, SURFACE_COVERED, identities=("tool_runtime-identity",),
                               proof=c.enumeration("surface-enumerator", "2.0"))
        self.assertFalse(may_reuse(closure(), closure(surfaces=surfaces(tool_runtime=other))).reusable)

    def test_changed_candidate_material_digest_is_no_reuse(self) -> None:
        changed = dataclasses.replace(PROVENANCE, candidate_material_digest="9" * 64)
        decision = may_reuse(closure(), closure(provenance=changed))
        self.assertEqual((False, INVALIDATED), (decision.reusable, decision.state))

    def test_changed_task_input_digest_is_no_reuse(self) -> None:
        changed = dataclasses.replace(PROVENANCE, task_input_digest="9" * 64)
        self.assertFalse(may_reuse(closure(), closure(provenance=changed)).reusable)

    def test_same_candidate_hash_with_changed_material_still_invalidates(self) -> None:
        changed = dataclasses.replace(PROVENANCE, candidate_material_digest="9" * 64)
        self.assertEqual(PROVENANCE.candidate_hash, changed.candidate_hash)
        self.assertFalse(may_reuse(closure(), closure(provenance=changed)).reusable)

    def test_changed_builder_version_is_no_reuse(self) -> None:
        before = dataclasses.replace(PROVENANCE, builder_identity="b", builder_version="1.0")
        after = dataclasses.replace(PROVENANCE, builder_identity="b", builder_version="1.1")
        self.assertFalse(may_reuse(closure(provenance=before), closure(provenance=after)).reusable)

    def test_changed_git_semantics_is_no_reuse(self) -> None:
        self.assertFalse(may_reuse(closure(), closure(git_semantics={"commit_signing": "enabled"})).reusable)

    def test_changed_evidence_declaration_is_no_reuse(self) -> None:
        other = declaration(implementation_version="2.0")
        self.assertFalse(may_reuse(closure(), closure(evidence_dependencies=(other,))).reusable)

    def test_changed_evidence_mechanism_version_is_no_reuse(self) -> None:
        upgraded = declaration({NETWORK: ClassCoverage(NETWORK, DENIED, proof=c.denial("sandbox-net-deny", "2.2"))})
        baseline = declaration({NETWORK: ClassCoverage(NETWORK, DENIED, proof=SANDBOX)})
        self.assertFalse(may_reuse(closure(evidence_dependencies=(baseline,)), closure(evidence_dependencies=(upgraded,))).reusable)

    def test_the_closure_digest_covers_provenance(self) -> None:
        changed = dataclasses.replace(PROVENANCE, request_digest="9" * 64)
        self.assertNotEqual(closure().digest(), closure(provenance=changed).digest())


if __name__ == "__main__":
    unittest.main()
