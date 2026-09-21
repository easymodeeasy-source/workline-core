"""The common semantic round-trip proof: what was reviewed is what the Project now holds.

A byte or hash match is not enough (``R8`` §2, ``R10`` §3). Defaults, omitted
fields, schema interpretation and loader behaviour can all change what a
persisted record *means* without changing what it looks like. So the proof runs
the meaning all the way around:

```text
reviewed semantic candidate
+ stable/reserved IDs
+ schema/base/version identity
        ↓  project_expected
expected canonical projection
        ↓  persist            (the owning operation, not the adapter)
        ↓  load_persisted     (the canonical loader, not a cached copy)
        ↓  normalize_persisted
normalized persisted semantics
        ==
normalized reviewed candidate resolved through the reserved ID map
```

Two things make this honest. The reload goes through the canonical loader, so
what is compared is what the Project will actually read back, not what the
writer believed it wrote. And identity comes from the reservation map, never
from matching on display number or name after the write - a lookup by
resemblance would make the proof agree with itself.

P1 freezes the protocol and proves it against synthetic adapters. The Roadmap
specialization is P2 (``R8``), Phase entry is P2 (``R9``), Work START is P3,
and Policy is later (``R10``); none of them is anticipated here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ..errors import ValidationError
from .projections import Projection, ProjectionSet


@dataclass(frozen=True)
class ReservedIds:
    """The exact identities the owning mutation reserved, keyed by the candidate's own keys.

    The adapter resolves a reviewed candidate's internal reference - "the Phase
    I called ``design``" - through this map. An endpoint that legitimately names
    an already-canonical entity stays that exact ID.

    Resolution is total: an unknown key is a STOP, never a guess and never a
    lookup by name similarity (``R8`` §4).
    """

    mapping: dict[str, str]

    def resolve(self, key: str) -> str:
        if key not in self.mapping:
            raise ValidationError(
                f"the reviewed candidate names {key!r}, which the owning mutation reserved no identity for; "
                "identity is never recovered by name or display similarity after the write",
                code="review_adapter_unresolved",
            )
        return self.mapping[key]

    def resolve_existing(self, reference: str, canonical: set[str]) -> str:
        """``reference`` as either a reserved key or an existing canonical ID.

        An endpoint may legitimately name an entity that already exists. It may
        not name nothing at all.
        """
        if reference in self.mapping:
            return self.mapping[reference]
        if reference in canonical:
            return reference
        raise ValidationError(
            f"the reviewed candidate names {reference!r}, which is neither a reserved key nor an "
            "existing canonical identity",
            code="review_adapter_unresolved",
        )


@runtime_checkable
class PersistedProjectionAdapter(Protocol):
    """What a Review kind must provide before it may persist a reviewed candidate.

    Exact Python names are an implementation detail; these responsibilities are
    not (``R8`` §2). An adapter that cannot answer all five cannot be activated.
    """

    def adapter_identity(self) -> str:
        """Stable identity of this adapter, bound into Evidence and closure identity."""

    def loader_identity(self) -> str:
        """Identity/version of the canonical loader the reload goes through.

        Bound because a loader change can alter effective meaning without
        altering a single stored byte.
        """

    def normalize_candidate(self, candidate: Any, reserved: ReservedIds) -> Projection:
        """The reviewed candidate as normalized semantics, with references resolved."""

    def project_expected(self, candidate: Any, reserved: ReservedIds, base: Any) -> ProjectionSet:
        """The exact canonical projection persisting that candidate should produce."""

    def load_persisted(self, result_identity: Any, view: Any) -> Any:
        """Reread the persisted result through the canonical loader."""

    def normalize_persisted(self, loaded: Any) -> Projection:
        """The persisted result as normalized semantics, comparable with the candidate."""


@dataclass(frozen=True)
class RoundTrip:
    """The outcome of one semantic round-trip proof."""

    matched: bool
    reason: str
    reviewed: Projection
    persisted: Projection

    def require(self) -> None:
        """Raise unless the round trip matched.

        A mismatch is ``reconcile_required`` territory rather than a repair:
        what the Project holds is not what was reviewed, and no automatic
        rewrite of either side can make the authorization true again.
        """
        if not self.matched:
            raise ValidationError(
                f"what the Project holds is not what Review authorized: {self.reason}",
                code="review_roundtrip_mismatch",
            )


def prove_round_trip(
    adapter: PersistedProjectionAdapter,
    candidate: Any,
    reserved: ReservedIds,
    result_identity: Any,
    view: Any,
) -> RoundTrip:
    """Run the semantic round trip for ``candidate`` and report whether it holds.

    The reload goes through ``adapter.load_persisted`` - the canonical loader -
    so the comparison is against what the Project reads back, not against what
    the writer thought it wrote.
    """
    reviewed = adapter.normalize_candidate(candidate, reserved)
    persisted = adapter.normalize_persisted(adapter.load_persisted(result_identity, view))
    if reviewed.kind != persisted.kind:
        return RoundTrip(
            False,
            f"the reviewed semantics are a {reviewed.kind} projection and the persisted semantics a {persisted.kind} one",
            reviewed,
            persisted,
        )
    if reviewed.semantics_version != persisted.semantics_version:
        return RoundTrip(
            False,
            f"semantics version {reviewed.semantics_version} was reviewed and "
            f"{persisted.semantics_version} was persisted",
            reviewed,
            persisted,
        )
    if not reviewed.same_as(persisted):
        return RoundTrip(
            False,
            f"reviewed semantics {reviewed.identity()[:12]} != persisted semantics {persisted.identity()[:12]}",
            reviewed,
            persisted,
        )
    return RoundTrip(True, "reviewed and persisted semantics are identical", reviewed, persisted)


def prove_expected_scope(expected: ProjectionSet, actual: ProjectionSet) -> RoundTrip:
    """Whether what was actually persisted is exactly the projection that was expected.

    Scope equality, alongside semantic equality: an operation that also wrote
    something nobody projected has not persisted the reviewed candidate, even
    if the reviewed part of it round-trips perfectly.
    """
    reviewed = expected.reviewed_artifact or expected.authorized_transition or expected.operation_metadata
    found = actual.reviewed_artifact or actual.authorized_transition or actual.operation_metadata
    if reviewed is None or found is None:
        raise ValidationError("a projection scope comparison needs a projection on both sides", code="review_projection_invalid")
    if expected.same_as(actual):
        return RoundTrip(True, "the persisted projection is exactly the expected one", reviewed, found)
    return RoundTrip(False, "the persisted projection is not the expected one", reviewed, found)
