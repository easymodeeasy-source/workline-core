# Review System P1 — R9 Phase Entry `PersistedProjectionAdapter` Contract Freeze

Status: CONTRACT FROZEN / IMPLEMENTATION NOT STARTED

This checkpoint freezes the P1/P2 adapter contract that proves a reviewed `PhaseEntryDesign` is what canonical Project state contains after expansion. It is non-normative until implementation and authority activation.

## 1. Live facts inspected

The live Roadmap-owned Phase-entry path already provides:

- `PhaseEntryDesign` as the pre-write semantic object;
- `design_identity(design)` durably embedded in the Roadmap mutation invocation before IDs are reserved;
- stable reserved Work/relation IDs through registration helpers;
- separate normal Work / integration / optional human-confirmation registration stages;
- canonical `planned_next` and `requires_completion` relations;
- canonical `work_kind=phase_integration_check` and optional `human_confirmation` with confirmation target;
- structural validation before final commit;
- fresh `ProjectView.load()` after persistence;
- an `entry` field that currently influences the immediate return/selection but is **not itself persisted as canonical Phase/Work/Relation state**.

The last point matters for semantic round-trip and is frozen explicitly below rather than hidden.

## 2. Adapter responsibility

The Phase specialization of `PersistedProjectionAdapter` conceptually owns:

```text
normalize_candidate(PhaseEntryDesign)
project_expected(normalized_candidate, reserved_ids, base_view)
load_persisted(phase_id, created_ids, ProjectView)
normalize_persisted(loaded_result)
```

Round-trip equality applies to the **persisted semantic component** of the reviewed design. Operation-only continuation hints must be proven not to carry unique plan meaning that disappears after the operation.

## 3. Persisted semantic component

Frozen persisted semantics are:

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
- generated requires_completion from every normal Work to integration
- generated requires_completion from integration to confirmation when present

origin/affiliation:
- phase_id
- roadmap_id
```

Allocated entity/relation IDs and display values are generated persistence identities, not user-authored semantics, but they are part of the exact expected physical projection once reserved.

## 4. `entry` live-contract finding and frozen Review-v1 rule

Current `PhaseEntryDesign.entry` is not persisted. The live code can accept an explicit `entry` specifically to disambiguate several Works that the persisted `planned_next` graph itself does not uniquely order. After a successful expansion commit, only the returned `entry_work_id` carries that immediate choice; a fresh clone/ProjectView cannot reconstruct the fact that the caller explicitly chose it.

Candidate 7 forbids Review metadata from becoming a normative progression source, so P1/P2 must **not** solve this by reading a Receipt/Consumption later to decide which Work starts.

Frozen Review-v1 contract:

```text
A reviewed PhaseEntryDesign MUST be canonically self-selecting.
```

Meaning:

- remove the ephemeral `entry` hint from the persisted comparison;
- evaluate the resulting canonical design graph with the same startable/planned-next rules used by `ProjectView`;
- it must leave zero or one unique first Work as appropriate for the design;
- if several equally planned startable Works remain, Review-v1 Phase entry is not READY even if `design.entry` names one;
- an explicit `entry`, when present, must equal the unique Work the canonical persisted plan itself selects.

Thus `entry` remains an immediate operation convenience/check, not hidden persisted meaning. A crash/clone can recover the intended next Work from canonical relations/state without consulting Review metadata.

Legacy Phase entry behavior is unchanged until P2 activation; the stronger rule applies to `review-v1` planning contracts.

This is a contract refinement discovered by live reconnaissance, not a new progression authority or architecture loop.

## 5. Stable reservation map

The adapter consumes the exact mutation reservations for:

```text
each normal design key -> Work ID
integration             -> Work ID
confirmation            -> Work ID if present
relation reservation slots -> relation IDs
```

References in reviewed relations are resolved through these stable keys/IDs exactly as canonical registration resolves them.

No semantic reconstruction uses Work names/display numbers as identity fallback.

## 6. Expected canonical effects

`project_expected()` generates/reuses the same canonical effects as registration:

```text
Work entity files
Related relation additions
Roadmap relation additions
```

for normal Works, integration, optional confirmation and all generated dependency edges.

It must reuse canonical WorkSpec/render/registration helpers or shared pure functions extracted from them. A second hand-coded renderer is not acceptable because the proof would merely compare one implementation against a different interpretation.

Before persistence, the projected view must pass the same registration/structure validation the live operation requires.

## 7. Persisted reconstruction

After the local registration commit:

- reload fresh `ProjectView`;
- select created Works by exact reserved IDs;
- verify Phase/Roadmap affiliation and Work kinds;
- reconstruct reviewed Related and Roadmap relations for those IDs;
- distinguish reviewed edges from generated integration/confirmation edges using exact expected relation IDs/records;
- reconstruct the canonical first-Work selection from ProjectView startability/planned-next semantics;
- compare to the normalized reviewed persisted semantics and the Review-v1 self-selecting rule.

Filesystem/ID order is not semantic declared Work order. Where declaration order matters for rendering/display, recover it from the reviewed reservation map and prove expected persisted display/effect separately.

## 8. Equality conditions

PASS requires:

```text
all expected Works exist exactly once
all expected Related/Roadmap relations exist exactly once
no unexpected operation-owned Work/relation exists
normal/integration/confirmation kinds and targets match
origin/phase/roadmap affiliation matches
normalized persisted design semantics == reviewed persisted semantic component
canonical plan uniquely identifies the same first Work when one is expected
structure validation passes
exact physical commit-delta proof passes
```

A matching `design_identity` alone is insufficient.

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

The `canonical first Work ID` is evidence of what canonical plan semantics select after write. It does not become a separate progression authority; START/Roadmap still derive selection from Project state on future invocations.

## 10. Recovery

A pending expansion only resumes when the live `design_identity()` matches exactly, as today. Reserved IDs/effects are reused.

After replay/finalization, semantic round-trip runs again. If the canonical graph no longer reconstructs the reviewed design or unique first Work, stop/reconcile rather than accepting the historical invocation identity as proof of current meaning.

A completed expansion with no pending mutation is not re-expanded to recover an ephemeral `entry`; Review-v1 prevents that information loss by requiring the persisted graph itself to determine the same choice.

## 11. Architecture blocker / HUMAN

Architecture blocker: `None`.

HUMAN decision: `None`.

Live reconnaissance found one concrete Phase-entry seam (`entry` is not persisted). It is closed at the P1/P2 contract level by forbidding Review-v1 plans from relying on that ephemeral hint to resolve canonical ambiguity, preserving Candidate 7's rule that Review metadata is not progression truth.