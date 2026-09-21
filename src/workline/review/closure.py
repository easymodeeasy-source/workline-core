"""Evidence dependency completeness, and the closure that decides whether a Review still holds.

Two connected models live here.

**Evidence dependency classes** (``R11``). An Evidence adapter declares which
dependency classes its check materially has, and how each one is accounted for:

```text
observed | pinned | denied     accounted for
not_required                   positively excluded by a closed execution contract
unknown                        everything else
```

The frozen rule is that completeness is a subset statement, never a feeling:

```text
required classes ⊆ covered ∪ pinned ∪ denied ∪ not_required
```

Anything unaccounted for makes completeness ``unknown``, and unknown is not
false and not true - it is *not proof*. Unknown Evidence may be used fresh; it
may not be reused across Candidates on completeness grounds.

**ReviewValidityClosure** (``R6``). Git-write compatibility is not Review
validity: that recorded paths are untouched says nothing about whether the
Context, the toolchain, the Policy or the provenance that produced the Review
are still what they were. The closure carries those dependency surfaces, and
reuse across an intervening HEAD advance requires every one of them to be
complete and unchanged.

Provenance is first class among them (``R6`` §4). The same ``candidate_hash``
reached through different snapshot bytes is different provenance, and so is the
same ``request_digest`` reached through different task-input bytes, or the same
builder output from a different builder version. Equal results do not make equal
reconstruction.

P1 builds the model, its completeness rule and its comparison. Wiring it into a
live HEAD-advancement fast path is P3 and is not done here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..errors import ValidationError
from . import serialize

# --------------------------------------------------------------------------- dependency classes

#: ``review-dependency-classes-v1`` (``R11`` §2). A later vocabulary does not
#: inherit completeness from this one: the vocabulary identity is part of what a
#: reusable Evidence identity binds.
VOCABULARY = "review-dependency-classes-v1"

REPOSITORY_FILES = "repository_files"
FILESYSTEM_EXTERNAL = "filesystem_external"
ENVIRONMENT = "environment"
SUBPROCESS = "subprocess"
NETWORK = "network"
CLOCK = "clock"
RANDOMNESS = "randomness"
LOCALE = "locale"
DYNAMIC_LIBRARIES = "dynamic_libraries"
RUNTIME_TOOLCHAIN = "runtime_toolchain"
HARDWARE = "hardware"
EXTERNAL_SERVICE = "external_service"
CACHE_STATE = "cache_state"
GIT_STATE = "git_state"
REVIEW_PROVENANCE = "review_provenance"

DEPENDENCY_CLASSES = (
    REPOSITORY_FILES,
    FILESYSTEM_EXTERNAL,
    ENVIRONMENT,
    SUBPROCESS,
    NETWORK,
    CLOCK,
    RANDOMNESS,
    LOCALE,
    DYNAMIC_LIBRARIES,
    RUNTIME_TOOLCHAIN,
    HARDWARE,
    EXTERNAL_SERVICE,
    CACHE_STATE,
    GIT_STATE,
    REVIEW_PROVENANCE,
)

OBSERVED = "observed"
PINNED = "pinned"
DENIED = "denied"
NOT_REQUIRED = "not_required"
UNKNOWN = "unknown"

COVERAGE_MODES = (OBSERVED, PINNED, DENIED, NOT_REQUIRED, UNKNOWN)

#: The modes that account for a class. ``unknown`` is deliberately absent: it is
#: the answer for everything not positively accounted for, and it never counts
#: as coverage.
ACCOUNTED_MODES = (OBSERVED, PINNED, DENIED, NOT_REQUIRED)

COMPLETE = "complete"


@dataclass(frozen=True)
class ClassCoverage:
    """How one dependency class is accounted for, and on what basis.

    ``basis`` is required for every accounted mode, because "covered" with no
    stated basis is a boolean an adapter asserted about itself, which ``R11``
    §14 refuses: a trace or sandbox implementation cannot self-certify
    completeness by outputting a flag.
    """

    dependency_class: str
    mode: str
    basis: str = ""
    identities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.dependency_class not in DEPENDENCY_CLASSES:
            raise ValidationError(
                f"unknown dependency class: {self.dependency_class!r} (vocabulary {VOCABULARY})",
                code="review_dependency_invalid",
            )
        if self.mode not in COVERAGE_MODES:
            raise ValidationError(f"unknown coverage mode: {self.mode!r}", code="review_dependency_invalid")
        if self.mode in ACCOUNTED_MODES and not self.basis:
            raise ValidationError(
                f"{self.dependency_class} is declared {self.mode} with no stated basis; "
                "coverage is shown, not asserted",
                code="review_dependency_invalid",
            )

    @property
    def accounted(self) -> bool:
        return self.mode in ACCOUNTED_MODES

    def to_record(self) -> dict[str, Any]:
        return {
            "dependency_class": self.dependency_class,
            "mode": self.mode,
            "basis": self.basis,
            "identities": list(self.identities),
        }


@dataclass(frozen=True)
class EvidenceDeclaration:
    """One Evidence adapter's declaration of what its check materially depends on.

    Completeness is computed (:meth:`completeness`), never declared. An adapter
    states what it requires and how each class is accounted for; whether that
    adds up is this class's answer, not the adapter's.
    """

    adapter_identity: str
    implementation_version: str
    required: tuple[str, ...]
    coverage: tuple[ClassCoverage, ...]
    vocabulary: str = VOCABULARY

    def __post_init__(self) -> None:
        if not self.adapter_identity or not self.implementation_version:
            raise ValidationError(
                "an Evidence declaration names its adapter identity and implementation version",
                code="review_dependency_invalid",
            )
        unknown = sorted(set(self.required) - set(DEPENDENCY_CLASSES))
        if unknown:
            raise ValidationError(
                f"required dependency class(es) outside {self.vocabulary}: {', '.join(unknown)}",
                code="review_dependency_invalid",
            )
        seen = [entry.dependency_class for entry in self.coverage]
        if len(set(seen)) != len(seen):
            raise ValidationError("a dependency class is covered twice", code="review_dependency_invalid")

    def accounted_classes(self) -> set[str]:
        return {entry.dependency_class for entry in self.coverage if entry.accounted}

    def unaccounted(self) -> tuple[str, ...]:
        """Required classes with no accounting - exactly what makes completeness unknown."""
        return tuple(sorted(set(self.required) - self.accounted_classes()))

    def completeness(self) -> str:
        """``complete`` only when every required class is accounted for; else ``unknown``."""
        return COMPLETE if not self.unaccounted() else UNKNOWN

    def complete(self) -> bool:
        return self.completeness() == COMPLETE

    def reusable(self) -> bool:
        """Whether this Evidence may be reused across Candidates at all.

        Unknown completeness is fresh-use-only (``R11`` §4). It is not a
        weaker yes.
        """
        return self.complete()

    def to_record(self) -> dict[str, Any]:
        return {
            "adapter_identity": self.adapter_identity,
            "implementation_version": self.implementation_version,
            "vocabulary": self.vocabulary,
            "required": list(self.required),
            "coverage": [entry.to_record() for entry in self.coverage],
            "completeness": self.completeness(),
        }

    def identity(self) -> str:
        return serialize.digest(self.to_record())


# --------------------------------------------------------------------------- review validity closure

@dataclass(frozen=True)
class ReviewProvenance:
    """The reconstruction identities a Review's validity depends on (``R6`` §4).

    Bound separately from the artifact and request they produce, because two
    provenances that reconstruct the same ``candidate_hash`` are still two
    provenances. Without this, replacing snapshot bytes or a builder version
    would silently keep a Review valid that was never performed against the new
    material.
    """

    candidate_hash: str
    candidate_material_digest: str
    task_input_digest: str
    request_digest: str
    reviewer_identity: str
    reviewer_version: str
    review_context_hash: str
    effective_policy_hash: str
    builder_identity: str | None = None
    builder_version: str | None = None
    builder_input_identities: tuple[str, ...] = ()

    def to_record(self) -> dict[str, Any]:
        return {
            "candidate_hash": self.candidate_hash,
            "candidate_material_digest": self.candidate_material_digest,
            "task_input_digest": self.task_input_digest,
            "request_digest": self.request_digest,
            "reviewer_identity": self.reviewer_identity,
            "reviewer_version": self.reviewer_version,
            "review_context_hash": self.review_context_hash,
            "effective_policy_hash": self.effective_policy_hash,
            "builder_identity": self.builder_identity,
            "builder_version": self.builder_version,
            "builder_input_identities": list(self.builder_input_identities),
        }

    def identity(self) -> str:
        return serialize.digest(self.to_record())

    def same_as(self, other: "ReviewProvenance") -> bool:
        return self.identity() == other.identity()


@dataclass(frozen=True)
class ReviewValidityClosure:
    """What must be unchanged for a Review to still hold across an intervening HEAD advance.

    Git-write compatibility is a different question and is not answered here
    (``R6`` §1). That the recorded paths were not touched says nothing about the
    Context, Evidence, Policy, toolchain or Git semantics the Review depended
    on, and Candidate 7 requires this separate closure precisely because the
    first was being mistaken for the second.
    """

    version: int
    base_commit_sha: str
    provenance: ReviewProvenance
    repo_dependencies: tuple[str, ...] = ()
    review_context_dependencies: tuple[str, ...] = ()
    evidence_dependencies: tuple[EvidenceDeclaration, ...] = ()
    policy_dependencies: tuple[str, ...] = ()
    tool_runtime_dependencies: tuple[str, ...] = ()
    git_semantics: dict[str, Any] = field(default_factory=dict)
    completeness_basis: str = ""

    def completeness(self) -> str:
        """``complete`` only when every declared Evidence dependency is itself complete.

        One unknown anywhere makes the whole closure unknown. There is no
        partial credit, because the fast path this feeds is all-or-nothing:
        either prior Review and Evidence may be reused without re-proving, or
        a new Candidate is required.
        """
        if not self.completeness_basis:
            return UNKNOWN
        if any(not declaration.complete() for declaration in self.evidence_dependencies):
            return UNKNOWN
        return COMPLETE

    def complete(self) -> bool:
        return self.completeness() == COMPLETE

    def to_record(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "base_commit_sha": self.base_commit_sha,
            "repo_dependencies": list(self.repo_dependencies),
            "review_provenance_dependencies": self.provenance.to_record(),
            "git_semantics": dict(self.git_semantics),
            "review_context_dependencies": list(self.review_context_dependencies),
            "evidence_dependencies": [declaration.to_record() for declaration in self.evidence_dependencies],
            "policy_dependencies": list(self.policy_dependencies),
            "tool_runtime_dependencies": list(self.tool_runtime_dependencies),
            "completeness": self.completeness(),
            "completeness_basis": self.completeness_basis,
        }

    def digest(self) -> str:
        return serialize.digest(self.to_record())


@dataclass(frozen=True)
class ReuseDecision:
    """Whether prior Review/Evidence may be reused, and the reason either way."""

    reusable: bool
    reason: str


def may_reuse(before: ReviewValidityClosure, after: ReviewValidityClosure) -> ReuseDecision:
    """Whether the Review described by ``before`` survives into the state ``after`` describes.

    Every answer other than an explicit yes is a no. Unknown completeness on
    either side is a no, changed provenance is a no, and a changed non-repo
    material identity is a no (``R6`` §9, §10). Absence of discovered change is
    never proof of invariance, which is why this compares declared identities
    rather than looking for evidence of a difference.
    """
    if not before.complete():
        return ReuseDecision(False, f"the prior closure's completeness is {before.completeness()}, not {COMPLETE}")
    if not after.complete():
        return ReuseDecision(False, f"the current closure's completeness is {after.completeness()}, not {COMPLETE}")
    if not before.provenance.same_as(after.provenance):
        return ReuseDecision(
            False,
            "the Review provenance changed; equal result hashes do not make equal reconstruction",
        )
    for name, mine, theirs in (
        ("repository", before.repo_dependencies, after.repo_dependencies),
        ("Review Context", before.review_context_dependencies, after.review_context_dependencies),
        ("Policy", before.policy_dependencies, after.policy_dependencies),
        ("tool/runtime", before.tool_runtime_dependencies, after.tool_runtime_dependencies),
    ):
        if tuple(mine) != tuple(theirs):
            return ReuseDecision(False, f"a {name} dependency identity changed")
    if before.git_semantics != after.git_semantics:
        return ReuseDecision(False, "the Git persistence semantics identity changed")
    if tuple(d.identity() for d in before.evidence_dependencies) != tuple(
        d.identity() for d in after.evidence_dependencies
    ):
        return ReuseDecision(False, "an Evidence declaration identity changed")
    return ReuseDecision(True, "every bound identity is unchanged and both closures are complete")
