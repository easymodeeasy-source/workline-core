"""Evidence dependency completeness, and the closure that decides whether a Review still holds.

Two connected models live here, and in both the rule is the same: completeness
is a *proof*, never a description.

**Evidence dependency classes** (``R11``). Every materially possible
dependency class must be positively accounted for - mechanically observed,
pinned, mechanically denied, or proven not required by a closed execution
contract. Anything unaccounted for makes completeness ``unknown`` (``R11`` §1).

A class that an adapter simply did not list is *not* thereby "not required".
Not required is its own positive claim, carried by an exclusion proof, and is
never inferred from absence.

Each coverage mode has a typed proof shape, and a free-form ``basis`` string is
a description that proves nothing:

```text
pinned        one or more concrete recorded identities - the pin itself
observed      an observation mechanism (identity + version) that records all
              material instances; zero instances is then a proven "none"
denied        a denial mechanism (identity + version) that prevents the use
not_required  an exclusion contract (identity + version) that rules it out
unknown       no proof - never coverage
```

An entry whose proof is missing or of the wrong kind stays ``unknown``: it is
held, reported, and never counted.

**ReviewValidityClosure** (``R6``). Git-write compatibility is not Review
validity. The closure positively closes each material surface a Review depends
on - the reviewed artifact, the Review Context, the Evidence, the Policy and
verifier inputs, the Git persistence semantics, the tool/runtime, and the
Review provenance - as either covered by a complete enumeration or proven not
required. An empty surface is a proof only when a mechanism enumerated it and
found nothing; "nothing happened to be listed" is ``unknown``.

Reuse across an intervening HEAD advance requires both closures complete and
every bound identity unchanged. Any ``unknown`` is not reuse, and the decision
keeps ``unknown`` as its state rather than collapsing it into a plain no.

P1 builds the model, its completeness rule and its comparison. Wiring it into a
live HEAD-advancement fast path is P3 and is not done here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..errors import ValidationError
from . import serialize

# --------------------------------------------------------------------------- vocabulary

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

#: The modes that make a class a covered, controlled dependency.
COVERING_MODES = (OBSERVED, PINNED, DENIED)

COMPLETE = "complete"

# --------------------------------------------------------------------------- typed proofs

PROOF_OBSERVATION = "observation"
PROOF_DENIAL = "denial"
PROOF_EXCLUSION = "exclusion"
PROOF_ENUMERATION = "enumeration"

PROOF_KINDS = (PROOF_OBSERVATION, PROOF_DENIAL, PROOF_EXCLUSION, PROOF_ENUMERATION)

#: The proof kind each coverage mode requires. ``pinned`` is absent on purpose:
#: its proof is its concrete identities, not a mechanism.
_MODE_PROOF = {OBSERVED: PROOF_OBSERVATION, DENIED: PROOF_DENIAL, NOT_REQUIRED: PROOF_EXCLUSION}


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


@dataclass(frozen=True)
class MechanismProof:
    """A machine-identified mechanism that establishes a coverage fact.

    Typed rather than descriptive: a proof is *which* mechanism, at *which*
    version, established *which kind* of fact. Its identity and version are part
    of what an Evidence identity binds, so a changed mechanism is a changed
    proof, and it cannot self-certify completeness by emitting a flag (``R11``
    §14).
    """

    kind: str
    identity: str
    version: str

    def __post_init__(self) -> None:
        if self.kind not in PROOF_KINDS:
            raise ValidationError(f"unknown proof kind: {self.kind!r}", code="review_dependency_invalid")

    @property
    def well_formed(self) -> bool:
        return _nonempty_text(self.identity) and _nonempty_text(self.version)

    def to_record(self) -> dict[str, Any]:
        return {"kind": self.kind, "identity": self.identity, "version": self.version}


def observation(identity: str, version: str) -> MechanismProof:
    return MechanismProof(PROOF_OBSERVATION, identity, version)


def denial(identity: str, version: str) -> MechanismProof:
    return MechanismProof(PROOF_DENIAL, identity, version)


def exclusion(identity: str, version: str) -> MechanismProof:
    return MechanismProof(PROOF_EXCLUSION, identity, version)


def enumeration(identity: str, version: str) -> MechanismProof:
    return MechanismProof(PROOF_ENUMERATION, identity, version)


# --------------------------------------------------------------------------- dependency classes

@dataclass(frozen=True)
class ClassCoverage:
    """How one dependency class is accounted for, with the proof that accounts for it.

    ``basis`` is a human description and is never read as proof. Whether the
    entry accounts for its class is :attr:`proven`, computed from the typed
    proof its mode requires; an entry that states a mode it cannot prove is kept
    as it is and counts as ``unknown``.
    """

    dependency_class: str
    mode: str
    proof: MechanismProof | None = None
    identities: tuple[str, ...] = ()
    basis: str = ""

    def __post_init__(self) -> None:
        if self.dependency_class not in DEPENDENCY_CLASSES:
            raise ValidationError(
                f"unknown dependency class: {self.dependency_class!r} (vocabulary {VOCABULARY})",
                code="review_dependency_invalid",
            )
        if self.mode not in COVERAGE_MODES:
            raise ValidationError(f"unknown coverage mode: {self.mode!r}", code="review_dependency_invalid")
        if not all(_nonempty_text(identity) for identity in self.identities):
            raise ValidationError(
                f"{self.dependency_class} lists an empty or padded identity", code="review_dependency_invalid"
            )

    @property
    def proven(self) -> bool:
        """Whether the mode's typed proof is present, well formed and of the right kind."""
        if self.mode == PINNED:
            return bool(self.identities)
        required = _MODE_PROOF.get(self.mode)
        if required is None:
            return False  # unknown
        return self.proof is not None and self.proof.kind == required and self.proof.well_formed

    @property
    def covers(self) -> bool:
        """A proven, controlled dependency: observed, pinned or denied."""
        return self.proven and self.mode in COVERING_MODES

    @property
    def excludes(self) -> bool:
        """A proven exclusion: not required, by a closed execution contract."""
        return self.proven and self.mode == NOT_REQUIRED

    def to_record(self) -> dict[str, Any]:
        return {
            "dependency_class": self.dependency_class,
            "mode": self.mode,
            "proof": None if self.proof is None else self.proof.to_record(),
            "identities": list(self.identities),
            "basis": self.basis,
        }


@dataclass(frozen=True)
class EvidenceDeclaration:
    """One Evidence adapter's declaration of what its check materially depends on.

    Completeness is computed (:meth:`completeness`), never declared. Every class
    of the vocabulary must be accounted for - covered with proof if it is
    required, or excluded with proof if it is not - and a class that is simply
    absent is unaccounted, whatever the ``required`` list says.
    """

    adapter_identity: str
    implementation_version: str
    required: tuple[str, ...]
    coverage: tuple[ClassCoverage, ...]
    vocabulary: str = VOCABULARY

    def __post_init__(self) -> None:
        if not _nonempty_text(self.adapter_identity) or not _nonempty_text(self.implementation_version):
            raise ValidationError(
                "an Evidence declaration names its adapter identity and implementation version",
                code="review_dependency_invalid",
            )
        if self.vocabulary != VOCABULARY:
            raise ValidationError(
                f"Evidence declared under vocabulary {self.vocabulary!r}, which this build does not read",
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
        contradictory = sorted(
            entry.dependency_class for entry in self.coverage
            if entry.mode == NOT_REQUIRED and entry.dependency_class in self.required
        )
        if contradictory:
            raise ValidationError(
                f"class(es) both required and declared not required: {', '.join(contradictory)}",
                code="review_dependency_invalid",
            )

    def _entry(self, dependency_class: str) -> ClassCoverage | None:
        for entry in self.coverage:
            if entry.dependency_class == dependency_class:
                return entry
        return None

    def unaccounted(self) -> tuple[str, ...]:
        """Every class not positively accounted for - exactly what makes completeness unknown.

        A required class needs covering proof; any other class needs covering or
        exclusion proof. A missing entry, an ``unknown`` entry, and an entry
        whose typed proof is absent or of the wrong kind are all unaccounted.
        """
        missing: list[str] = []
        for dependency_class in DEPENDENCY_CLASSES:
            entry = self._entry(dependency_class)
            if entry is None:
                missing.append(dependency_class)
            elif dependency_class in self.required:
                if not entry.covers:
                    missing.append(dependency_class)
            elif not (entry.covers or entry.excludes):
                missing.append(dependency_class)
        return tuple(missing)

    def completeness(self) -> str:
        """``complete`` only when every class is positively accounted for; else ``unknown``."""
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

SURFACE_REVIEWED_ARTIFACT = "reviewed_artifact"
SURFACE_REVIEW_CONTEXT = "review_context"
SURFACE_EVIDENCE = "evidence"
SURFACE_POLICY = "policy"
SURFACE_GIT_SEMANTICS = "git_semantics"
SURFACE_TOOL_RUNTIME = "tool_runtime"
SURFACE_REVIEW_PROVENANCE = "review_provenance"

#: The material surfaces a Review-validity closure must positively close
#: (``R6`` §5: artifact, provenance, Context, Evidence, Policy, Git semantics,
#: tool/runtime).
REQUIRED_SURFACES = (
    SURFACE_REVIEWED_ARTIFACT,
    SURFACE_REVIEW_CONTEXT,
    SURFACE_EVIDENCE,
    SURFACE_POLICY,
    SURFACE_GIT_SEMANTICS,
    SURFACE_TOOL_RUNTIME,
    SURFACE_REVIEW_PROVENANCE,
)

SURFACE_COVERED = "covered"
SURFACE_NOT_REQUIRED = "not_required"
SURFACE_UNKNOWN = "unknown"
SURFACE_STATES = (SURFACE_COVERED, SURFACE_NOT_REQUIRED, SURFACE_UNKNOWN)


@dataclass(frozen=True)
class SurfaceClosure:
    """One material surface, positively closed or not.

    ``covered`` is proven by an *enumeration* proof: a mechanism that listed
    the surface's material identities completely. With it, an empty identity
    list is a proven "no dependency"; without it, a list - empty or not - is
    only what happened to be written down. ``not_required`` is proven by an
    exclusion proof.
    """

    surface: str
    state: str
    identities: tuple[str, ...] = ()
    proof: MechanismProof | None = None

    def __post_init__(self) -> None:
        if self.surface not in REQUIRED_SURFACES:
            raise ValidationError(f"unknown closure surface: {self.surface!r}", code="review_dependency_invalid")
        if self.state not in SURFACE_STATES:
            raise ValidationError(f"unknown surface state: {self.state!r}", code="review_dependency_invalid")
        if not all(_nonempty_text(identity) for identity in self.identities):
            raise ValidationError(f"{self.surface} lists an empty or padded identity", code="review_dependency_invalid")

    @property
    def proven(self) -> bool:
        if self.proof is None or not self.proof.well_formed:
            return False
        if self.state == SURFACE_COVERED:
            return self.proof.kind == PROOF_ENUMERATION
        if self.state == SURFACE_NOT_REQUIRED:
            return self.proof.kind == PROOF_EXCLUSION
        return False

    def to_record(self) -> dict[str, Any]:
        return {
            "surface": self.surface,
            "state": self.state,
            "identities": list(self.identities),
            "proof": None if self.proof is None else self.proof.to_record(),
        }


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

    ``completeness_basis`` is a description for people and has no effect on
    completeness whatsoever.
    """

    version: int
    base_commit_sha: str
    provenance: ReviewProvenance | None
    surfaces: tuple[SurfaceClosure, ...] = ()
    evidence_dependencies: tuple[EvidenceDeclaration, ...] = ()
    git_semantics: dict[str, Any] = field(default_factory=dict)
    completeness_basis: str = ""

    def surface(self, name: str) -> SurfaceClosure | None:
        found = [entry for entry in self.surfaces if entry.surface == name]
        return found[0] if len(found) == 1 else None

    def unproven_surfaces(self) -> tuple[str, ...]:
        """The required surfaces not positively closed - absent, duplicated, unknown or unproven."""
        return tuple(name for name in REQUIRED_SURFACES if (self.surface(name) is None or not self.surface(name).proven))

    def completeness(self) -> str:
        """``complete`` only when every surface is positively closed and every Evidence declaration is complete.

        There is no partial credit, because the fast path this feeds is
        all-or-nothing: either prior Review and Evidence may be reused without
        re-proving, or a new Candidate is required.
        """
        if self.provenance is None:
            return UNKNOWN
        if self.unproven_surfaces():
            return UNKNOWN
        # A Review always has provenance (R6 section 4); it is covered, never excluded.
        if self.surface(SURFACE_REVIEW_PROVENANCE).state != SURFACE_COVERED:
            return UNKNOWN
        evidence = self.surface(SURFACE_EVIDENCE)
        if evidence.state == SURFACE_COVERED and any(not declaration.complete() for declaration in self.evidence_dependencies):
            return UNKNOWN
        if evidence.state == SURFACE_NOT_REQUIRED and self.evidence_dependencies:
            return UNKNOWN  # Evidence declared while the surface claims none is needed: contradictory
        return COMPLETE

    def complete(self) -> bool:
        return self.completeness() == COMPLETE

    def to_record(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "base_commit_sha": self.base_commit_sha,
            "review_provenance_dependencies": None if self.provenance is None else self.provenance.to_record(),
            "surfaces": [entry.to_record() for entry in sorted(self.surfaces, key=lambda item: item.surface)],
            "evidence_dependencies": [declaration.to_record() for declaration in self.evidence_dependencies],
            "git_semantics": dict(self.git_semantics),
            "completeness": self.completeness(),
        }

    def digest(self) -> str:
        return serialize.digest(self.to_record())


REUSABLE = "reusable"
INVALIDATED = "invalidated"


@dataclass(frozen=True)
class ReuseDecision:
    """Whether prior Review/Evidence may be reused, the semantic state, and why.

    ``state`` keeps ``unknown`` distinct from a proven change: unknown means
    completeness could not be shown, not that something was shown to differ.
    """

    reusable: bool
    state: str
    reason: str


def may_reuse(before: ReviewValidityClosure, after: ReviewValidityClosure) -> ReuseDecision:
    """Whether the Review described by ``before`` survives into the state ``after`` describes.

    Every answer other than an explicit yes is a no. Unknown completeness on
    either side is ``unknown``; a changed provenance, surface, Evidence or Git
    semantics identity is ``invalidated`` (``R6`` §9, §10). Absence of
    discovered change is never proof of invariance, which is why this compares
    declared, proven identities rather than looking for evidence of a
    difference.
    """
    if not before.complete():
        return ReuseDecision(False, UNKNOWN, f"the prior closure's completeness is {before.completeness()}")
    if not after.complete():
        return ReuseDecision(False, UNKNOWN, f"the current closure's completeness is {after.completeness()}")
    if not before.provenance.same_as(after.provenance):
        return ReuseDecision(False, INVALIDATED, "the Review provenance changed; equal result hashes do not make equal reconstruction")
    for name in REQUIRED_SURFACES:
        mine, theirs = before.surface(name), after.surface(name)
        if (mine.state, mine.identities) != (theirs.state, theirs.identities):
            return ReuseDecision(False, INVALIDATED, f"the {name} surface changed")
        if mine.proof != theirs.proof:
            return ReuseDecision(False, INVALIDATED, f"the {name} surface is proven by a different mechanism")
    if before.git_semantics != after.git_semantics:
        return ReuseDecision(False, INVALIDATED, "the Git persistence semantics identity changed")
    if tuple(d.identity() for d in before.evidence_dependencies) != tuple(d.identity() for d in after.evidence_dependencies):
        return ReuseDecision(False, INVALIDATED, "an Evidence declaration identity changed")
    return ReuseDecision(True, REUSABLE, "every bound identity is unchanged and both closures are complete")
