"""The three projections, and the boundary that keeps two of them out of lifecycle truth.

Candidate 7 §4 separates what a persisted operation puts on disk into three
kinds, because collapsing them is how Review would quietly become a second
authority:

```text
ReviewedArtifactProjection      what Review authorizes the correctness of
AuthorizedTransitionProjection  canonical lifecycle/registration effects the
                                owning operation applies with that authorization
OperationMetadataProjection     durable Review bookkeeping - Receipt,
                                Consumption, supersession, provenance
```

The first two are domain facts. The third is not, and the absolute rule is:

```text
OperationMetadataProjection MUST NOT be a normative source for
state.py / progression / correctness definitions.
```

:func:`normative` is that rule as code. Anything that asks "may this projection
決定 runtime behaviour?" asks it here, and a metadata projection answers no -
so the boundary is one function to audit rather than a convention spread across
call sites. If a file ever does determine normative behaviour, it is not
metadata, and modelling it as Context, Policy or canonical transition state
under the proper authority is the answer rather than relaxing this.

P1 builds the common representation, identity and comparison only. The
kind-specific content of each projection - what a Roadmap registration projects,
what a Work terminal projects - is P2/P3 and is deliberately absent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..errors import ValidationError
from . import serialize

REVIEWED_ARTIFACT = "reviewed_artifact"
AUTHORIZED_TRANSITION = "authorized_transition"
OPERATION_METADATA = "operation_metadata"

PROJECTION_KINDS = (REVIEWED_ARTIFACT, AUTHORIZED_TRANSITION, OPERATION_METADATA)

#: The projection kinds that may inform normative runtime behaviour. Metadata is
#: not among them, and that absence is the point.
NORMATIVE_KINDS = (REVIEWED_ARTIFACT, AUTHORIZED_TRANSITION)


def normative(kind: str) -> bool:
    """Whether a projection of ``kind`` may be a normative source.

    The single mechanical statement of Candidate 7 §4.3's absolute rule.
    ``state.py``, progression and correctness definitions read only what this
    says yes to - which is never :data:`OPERATION_METADATA`.
    """
    if kind not in PROJECTION_KINDS:
        raise ValidationError(f"unknown projection kind: {kind!r}", code="review_projection_invalid")
    return kind in NORMATIVE_KINDS


@dataclass(frozen=True)
class Projection:
    """One projection: its kind, its semantics version, and the content it projects.

    ``content`` is canonical data - the same normalization every Review record
    uses - so two projections of the same semantics have the same
    :meth:`identity` regardless of how either was built. That is what makes a
    round-trip comparison (:mod:`workline.review.adapter`) a statement about
    meaning rather than about dictionary order.
    """

    kind: str
    semantics_version: str
    content: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in PROJECTION_KINDS:
            raise ValidationError(f"unknown projection kind: {self.kind!r}", code="review_projection_invalid")
        if not isinstance(self.semantics_version, str) or not self.semantics_version:
            raise ValidationError("a projection declares its semantics version", code="review_projection_invalid")
        if not isinstance(self.content, dict):
            raise ValidationError("a projection's content is a mapping", code="review_projection_invalid")
        # Canonicalizing here refuses a value the canonical form cannot carry
        # exactly, at the point it enters, rather than at the point it is
        # compared or written.
        serialize.canonical_data(self.content)

    @property
    def normative(self) -> bool:
        return normative(self.kind)

    def to_record(self) -> dict[str, Any]:
        return {
            "projection_kind": self.kind,
            "semantics_version": self.semantics_version,
            "content": dict(self.content),
        }

    def identity(self) -> str:
        """The canonical digest of this projection - what equality is decided by."""
        return serialize.digest(self.to_record())

    def same_as(self, other: "Projection") -> bool:
        return self.identity() == other.identity()


def reviewed_artifact(semantics_version: str, content: dict[str, Any]) -> Projection:
    """The artifact whose correctness Review authorizes.

    ``candidate_hash`` is derived from this - the reviewed artifact identity
    plus declared base/context identity - never from Receipt or Consumption
    metadata (Candidate 7 §4.1).
    """
    return Projection(REVIEWED_ARTIFACT, semantics_version, content)


def authorized_transition(semantics_version: str, content: dict[str, Any]) -> Projection:
    """The canonical transition effects that consume the authorization.

    Events, entity and relation registrations, policy transitions: these belong
    to the domain operation, not to Review. Review authorizes them; it does not
    own them and does not apply them.
    """
    return Projection(AUTHORIZED_TRANSITION, semantics_version, content)


def operation_metadata(semantics_version: str, content: dict[str, Any]) -> Projection:
    """Durable Review bookkeeping - and never a normative source.

    :attr:`Projection.normative` is ``False`` for everything built here.
    """
    return Projection(OPERATION_METADATA, semantics_version, content)


@dataclass(frozen=True)
class ProjectionSet:
    """The projections one persisted operation produces, kept apart by kind.

    Kept as three named slots rather than a list so that "this operation has no
    transition projection" is a statement the type can make, and so that no
    caller can quietly hand a metadata projection to something expecting a
    normative one.
    """

    reviewed_artifact: Projection | None = None
    authorized_transition: Projection | None = None
    operation_metadata: Projection | None = None

    def __post_init__(self) -> None:
        for expected, found in (
            (REVIEWED_ARTIFACT, self.reviewed_artifact),
            (AUTHORIZED_TRANSITION, self.authorized_transition),
            (OPERATION_METADATA, self.operation_metadata),
        ):
            if found is not None and found.kind != expected:
                raise ValidationError(
                    f"a {expected} slot holds a {found.kind} projection", code="review_projection_invalid"
                )

    def present(self) -> tuple[Projection, ...]:
        return tuple(
            found
            for found in (self.reviewed_artifact, self.authorized_transition, self.operation_metadata)
            if found is not None
        )

    def normative_projections(self) -> tuple[Projection, ...]:
        """Only the projections a normative reader may consult."""
        return tuple(found for found in self.present() if found.normative)

    def same_as(self, other: "ProjectionSet") -> bool:
        """Exact per-kind equality - the union Candidate 7 §4.4 requires.

        Equality is per slot: a set that matches on the artifact but differs on
        the transition is not equal, and a missing projection is not equal to a
        present one.
        """
        for mine, theirs in (
            (self.reviewed_artifact, other.reviewed_artifact),
            (self.authorized_transition, other.authorized_transition),
            (self.operation_metadata, other.operation_metadata),
        ):
            if (mine is None) != (theirs is None):
                return False
            if mine is not None and theirs is not None and not mine.same_as(theirs):
                return False
        return True
