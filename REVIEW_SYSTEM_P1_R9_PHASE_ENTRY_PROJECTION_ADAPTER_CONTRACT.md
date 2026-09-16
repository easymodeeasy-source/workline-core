# Review System P1 — R9 Phase Entry `PersistedProjectionAdapter` Contract Freeze

Status: CONTRACT FROZEN / REPAIRED AFTER EXTERNAL REVIEW / IMPLEMENTATION NOT STARTED

This checkpoint freezes the P1/P2 adapter contract that proves a reviewed `PhaseEntryDesign` is what canonical Project state contains after expansion. It is non-normative until implementation and authority activation.

## 1. Live facts inspected

The live Roadmap-owned Phase-entry path already provides:

- `PhaseEntryDesign` as the pre-write semantic object;
- `design_identity(design)` embedded in the Roadmap mutation invocation;
- stable reserved Work/relation IDs;
- separate normal Work / integration / optional human-confirmation stages;
- canonical `planned_next` and `requires_completion` relations;
- canonical integration/human-confirmation kinds;
- structural validation before commit;
- fresh `ProjectView.load()` after persistence;
- an `entry` field that influences immediate selection/return but is not persisted as canonical progression state.

That last point is the relevant live seam.

## 2. Adapter responsibility

The Phase specialization of `PersistedProjectionAdapter` conceptually owns:

```text
normalize_candidate(PhaseEntryDesign)
project_expected(normalized_candidate, reserved_ids, base_view)
load_persisted(phase_id, created_ids, ProjectView)
normalize_persisted(loaded_result)
```

It verifies persisted semantic round-trip. It does **not** own Roadmap planning meaning.

## 3. Persisted semantic component

Frozen persisted semantics include:

```text
normal Works in declared order:
- design key
- name
- desired_state
- Related specifications

integration Work:
- name
- desired_state
- Related specifications
- work_kind = phase_integration_check

optional human confirmation:
- name
- desired_state
- Related specifications
- work_kind = human_confirmation
- confirmation_target = created integration Work

relations:
- reviewed planned_next
- reviewed requires_completion
- generated requires_completion normal Work -> integration
- generated requires_completion integration -> confirmation when present

origin/affiliation:
- phase_id
- roadmap_id
```

Generated IDs/display values are persistence identities, not user-authored semantics, but enter exact expected physical proof once reserved.

## 4. `entry` finding: authority ownership repaired

Current live Roadmap behavior allows explicit `entry` to disambiguate several otherwise equally planned Works. Because `entry` itself is not persisted as canonical plan state, a fresh clone cannot reconstruct that explicit one-shot choice from entities/relations/events alone.

Candidate 7 forbids Review metadata from becoming progression authority.

The previous R9 wording reached the right safety outcome but assigned too much semantic ownership to the adapter. This is repaired as follows.

### 4.1 Roadmap-owned review-v1 planning precondition

At P2 activation, the canonical Roadmap authority must explicitly own this stronger precondition for review-v1 planning:

```text
A reviewed PhaseEntryDesign must be canonically self-selecting.
```

Meaning:

- evaluate the design without relying on ephemeral `entry` as persisted plan meaning;
- the canonical graph/state produced by the design must leave zero or one unique first Work as appropriate;
- if several equally planned startable Works remain, the design is not valid for review-v1 even if `entry` names one;
- if `entry` is supplied, it must equal the unique Work the canonical graph itself selects.

### 4.2 Adapter role

`PersistedProjectionAdapter` only verifies that the Roadmap-owned precondition and semantic round-trip hold. It may not invent, weaken or strengthen Roadmap planning semantics on its own.

Legacy Phase-entry behavior remains unchanged until explicit review-v1 planning activation.

This is an authority refinement/migration inside the existing Roadmap owner, not Candidate 8 and not a second progression controller.

## 5. Stable reservation map

Adapter consumes exact reservations for normal design keys, integration, optional confirmation, and relation slots.

No reconstruction uses names/display numbers as identity fallback.

## 6. Expected canonical effects

`project_expected()` reuses canonical WorkSpec/render/registration helpers or shared pure functions extracted from them. A second hand-coded renderer is not acceptable.

Expected effects cover Work entity files, Related additions, Roadmap relation additions, integration dependencies and optional confirmation dependency.

Projected structure must pass the same registration/structure validation used by live Roadmap registration.

## 7. Persisted reconstruction

After local registration commit:

- reload fresh `ProjectView`;
- select created Works by exact reserved IDs;
- verify Phase/Roadmap affiliation and Work kinds;
- reconstruct Related/Roadmap relations using exact expected IDs/records;
- reconstruct canonical first-Work selection from normal ProjectView semantics;
- compare normalized persisted semantics against reviewed semantics;
- verify the Roadmap-owned review-v1 self-selecting precondition.

Declaration order is recovered from the reviewed reservation map where needed; filesystem/ID order is not silently treated as semantic order.

## 8. Equality conditions

PASS requires:

```text
all expected Works exactly once
all expected relations exactly once
no unexpected operation-owned Work/relation
kinds/targets/origin/affiliation match
normalized persisted semantics == reviewed persisted semantic component
Roadmap-owned review-v1 self-selecting precondition holds
canonical plan uniquely identifies the same first Work when one is expected
structure validation passes
exact physical commit-delta proof passes
```

`design_identity` alone is insufficient.

## 9. Planning Consumption binding

P2 Phase-entry Consumption binds at least:

```text
PhaseEntryDesign identity digest
persisted semantic projection digest
phase_id
created normal Work IDs
integration Work ID
confirmation Work ID/null
created relation IDs
canonical first Work ID/null
registration commit SHA
adapter/loader identity
```

`canonical first Work ID` is evidence of canonical plan semantics, not a separate progression source.

## 10. Recovery

A pending expansion resumes only when live `design_identity()` matches exactly. Reserved IDs/effects are reused.

After replay/finalization, semantic round-trip and Roadmap-owned self-selection validation run again. If canonical graph no longer reconstructs reviewed meaning, stop/reconcile.

A completed expansion is never re-expanded merely to recover an ephemeral `entry`.

## 11. Review-v1 entry cases

Frozen cases:

```text
canonical graph uniquely selects A, entry=A -> valid
canonical graph uniquely selects A, entry=B -> invalid
canonical graph leaves A/B ambiguous, entry=A -> invalid for review-v1
no explicit entry, canonical graph uniquely selects A -> valid
```

These cases are owned by Roadmap authority at P2 activation and verified by the adapter/tests.

## 12. External-review repair disposition

Accepted and repaired here:

- canonical self-selection remains required for review-v1;
- semantic ownership moves explicitly to Roadmap authority;
- adapter is verification/projection only and does not become a planning authority.

Architecture blocker: `None`.

HUMAN decision: `None`.
