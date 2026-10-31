# Review System P1 — R8 Roadmap `PersistedProjectionAdapter` Contract Freeze

Status: CONTRACT FROZEN / IMPLEMENTATION NOT STARTED

This checkpoint freezes the P1/P2 adapter contract that proves a reviewed `RoadmapPlan` is exactly what canonical Project state receives. It is non-normative until implementation and authority activation.

## 1. Live facts inspected

The live Roadmap operation already has the important semantic/recovery pieces:

- `RoadmapPlan` is the pre-write semantic object;
- `roadmap_request_identity(plan)` normalizes and durably records the plan before any ID is reserved;
- the Roadmap mutation reserves the Roadmap ID and Phase/relation IDs through the existing mutation reservation mechanism;
- `decide_phases()`/`register_phases()` build deterministic entity/relation effects from those reservations;
- `ProjectView.with_effects()` can project decided entity/relation/event effects without writing;
- `ProjectView.load()` rereads canonical entity/relation/event state after persistence;
- structural validation already checks affiliation, relation integrity, cycles and other canonical invariants.

The missing contract is a first-class semantic round-trip equality proof between the reviewed plan and the canonical state after registration.

## 2. Adapter responsibility

P1 defines a common `PersistedProjectionAdapter` protocol. The Roadmap specialization owns four operations conceptually:

```text
normalize_candidate(RoadmapPlan)
project_expected(normalized_candidate, reserved_ids, base_view)
load_persisted(result_identity, ProjectView)
normalize_persisted(loaded_result)
```

and one invariant:

```text
normalize_persisted(load_persisted(...))
==
normalize_candidate(reviewed RoadmapPlan) resolved through the reserved ID map
```

Exact Python names may differ; these responsibilities may not.

## 3. Reviewed semantic normalization

The Review semantic identity starts from the same normalization already used by `roadmap_request_identity()` rather than inventing a parallel interpretation.

Frozen semantic fields:

```text
Roadmap:
- name (verbatim as rendering persists it)
- background (trimmed as rendering persists it)
- desired_state (trimmed)
- optional scope presence/content using existing optional-section semantics
- optional out_of_scope presence/content

Phases in declared order:
- caller key
- name
- desired_state normalized exactly as existing request identity

Phase relations in declared order:
- type
- from endpoint reference
- to endpoint reference
```

Display numbers and allocated IDs are not user-authored semantics, but once reserved they are part of the exact expected persisted projection and must match it.

## 4. Stable ID resolution map

Before persistence proof, the adapter receives the exact reservations made by the owning Roadmap mutation:

```text
roadmap key -> r_...
phase key -> p_...
relation ordinal -> rel_...
```

A relation endpoint that names a reviewed Phase key is resolved through this map. An endpoint that legitimately names an existing canonical Phase ID remains that exact ID where the operation kind permits it.

The adapter never discovers identity by display number/name similarity after the write.

## 5. Expected canonical projection

`project_expected()` produces an exact expected set of canonical effects/tree entries for the creation:

```text
Roadmap entity file
Phase entity files
Roadmap relation additions
```

The expected Roadmap/Phase bytes use the same canonical rendering functions as the live writer. Expected relation records use the exact reserved relation IDs/endpoints/types.

The projection also captures which existing canonical ledgers are rewritten as whole files by the physical mutation, so post-commit delta proof can distinguish:

```text
semantic additions
vs
physical whole-ledger byte result
```

The adapter does not independently reimplement Phase CREATE rendering rules; it calls/reuses the canonical projection/registration helpers or a shared pure renderer extracted from them.

## 6. Persisted semantic reconstruction

After the local registration commit, load a fresh `ProjectView` and reconstruct only the result owned by this reviewed Roadmap creation using the exact created IDs.

Reconstructed semantic object includes:

```text
Roadmap body/name/sections
ordered created Phase semantic records
relations created by this operation, resolved to the exact created/existing endpoints
```

Order that is semantically meaningful is recovered from the reviewed reservation/result map, not filesystem enumeration order. The canonical store lists entities by ID, which is not the reviewed declaration order.

The adapter compares normalized semantic meaning, while the separate exact commit/tree proof compares physical bytes/modes/path scope.

## 7. Equality rules

Round-trip PASS requires all of:

```text
reviewed normalized Roadmap semantics == reconstructed persisted semantics
created IDs == reserved IDs
all expected created entities exist exactly once
all expected created relations exist exactly once
no operation-owned semantic entity/relation is missing
no extra operation-owned semantic entity/relation appears
canonical structure validation passes
exact commit-delta projection proof passes
```

A matching request identity alone is not sufficient.

A matching set of files with different relation meaning is not sufficient.

A byte-perfect persisted projection whose canonical loader interprets a different meaning is not sufficient.

## 8. Registration commit / Consumption binding

P2 Roadmap Review Consumption binds:

```text
reviewed Roadmap candidate hash
roadmap_request_identity digest
reserved/created Roadmap ID
reserved/created Phase IDs
reserved/created relation IDs
semantic projection digest
registration commit SHA
canonical loader/adapter identity
```

This is Planning-native Consumption. It does not fabricate a Work terminal event.

## 9. Recovery behavior

On resume:

- pending mutation request identity must still equal the reviewed plan identity;
- reservations are reused from the mutation record;
- recorded registration effects are projected/reread rather than regenerated with new IDs;
- if canonical state partially contains the exact expected effects, Mutation recovery completes them;
- after persistence, the same semantic round-trip is run again before Consumption/authorization is considered successfully used;
- mismatch is reconcile/new Review according to whether persistence or Candidate semantics changed; never infer equality from names/display numbers.

## 10. Loader/adapter identity

The Review Context binds an adapter/loader identity sufficient to invalidate Review if the canonical interpretation changes between Review and persistence.

At minimum P1 can bind:

```text
adapter contract version
configured Workline implementation identity/commit/tree identity as available
schema/rendering version identities used by the adapter
```

P1 must not use Python object identity or process memory as a durable loader identity.

## 11. Existing display-number behavior

Current Roadmap/Phase rendering derives display numbers from current entity counts while holding the Project lock. The expected projection must use the exact values decided by the live canonical writer under that lock and then prove them after write.

Display is persistence metadata/UX identity, not a substitute for semantic Roadmap/Phase ID.

## 12. Architecture blocker / HUMAN

Architecture blocker: `None`.

HUMAN decision: `None`.

The live `RoadmapPlan`, durable request identity, ID reservations, pure projection support and canonical reload already provide the necessary foundation. P2 implementation needs to expose/reuse those helpers through the adapter rather than inventing a second Roadmap semantics engine.