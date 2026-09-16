# Review System P1 — R12 Recovery / Invariant Test Contract Freeze

Status: CONTRACT FROZEN / REPAIRED AFTER EXTERNAL REVIEW / IMPLEMENTATION NOT STARTED

This checkpoint freezes the minimum interruption and invariant test matrix required before P1/P2/P3 Review contracts may be considered implemented. It is non-normative until implementation and authority activation.

## 1. Live recovery foundation

Existing tests already cover mutation staging, branch binding, declared write scopes, lifecycle resume, bootstrap resume, cancellation decisions, finalized-effect branch behavior and end-to-end flows.

Review tests extend the same durable-intent/replay model. They must exercise real persisted mutation/canonical/Git state rather than mocks that skip recovery semantics.

## 2. Test philosophy

Critical boundaries are tested across:

```text
A. uninterrupted happy path
B. crash/interruption after each durable boundary
C. conflicting external/local change before resume
```

Assertions cover both what happened exactly once and what must not have happened yet, especially push, lifecycle terminalization, duplicate Review records, executor re-run, generation fork and ID reallocation.

## 3. R1/R2 layout, immutable writer, IDs and committability

Required tests:

- Project without `.workline/review/` validates;
- first Review fact lazily creates exact directories/files;
- runtime Review data never satisfies canonical lookup;
- malformed/unknown Review path fails validation;
- Gate filename/run/generation mismatch rejected;
- non-contiguous generation chain rejected;
- predecessor digest mismatch rejected;
- central Review ID prefixes round-trip;
- retry reuses Review reservations;
- reservation key with another kind refuses/reconciles;
- generation numbering cannot skip/duplicate;
- immutable Review path exact bytes -> MATCHING;
- immutable Review path different bytes -> reconcile;
- generic update/base semantics on immutable Review path -> mechanically rejected;
- first Review write to a Git-ignored/excluded Review path STOPs before any canonical Review effect is recorded/applied;
- Workline does not edit ignore/exclude configuration.

### Write-time TOCTOU test

```text
Review validation passes
-> before effect apply, target parent under `.workline/review/` is replaced by symlink/junction/reparse pointing outside Project
-> immutable create is attempted
```

Expected: STOP/reconcile, and no outside-Project bytes are created/modified.

### Predecessor digest tests

- versioned canonical renderer uses UTF-8/LF and stable SHA-256;
- semantic-equivalent but non-canonical bytes are normalized/rejected before persistence, not treated as another valid digest form;
- predecessor canonical bytes changed -> chain failure;
- fresh clone reproduces canonical bytes/digest.

## 4. R3 generation interruption / fork matrix

### Accepted task durability

```text
G1 with clone-safe accepted task descriptor committed
-> process exits before task result
-> runtime removed or clone fresh
-> task identity/request binding reconstructs from canonical G1
-> task remains unsettled and seal forbidden
```

### Result before settlement generation

Runtime/provider result exists but crash occurs before canonical G2. Clone/resume has only G1, so T1 remains unsettled and authorization cannot seal.

### Settlement generation partial state

Test:

```text
G2 stage/intent recorded, effect unapplied
G2 file written, mutation applied flag unsaved
G2 locally committed, later stage not recorded
```

Resume must not duplicate generation/task ID or lose obligation.

### Generation fork after lock loss

Mandatory case:

```text
latest generation N validated
-> exact G(N+1) path included in initial WriteScope when mutation opens
-> pending intent durable
-> no generation effect applied
-> process crashes / OS lock disappears
-> second invocation attempts same Review run next generation
```

Expected: it resumes/refuses against first pending mutation; no second N+1/fork exists.

### Seal + Receipt partial stage

Interrupt before/after each physical effect and before local commit. Consumption must remain impossible until exact Gate+Receipt pair validates.

### New report invalidation

Sealed G4/R1 then G5 open + R1 supersession, with crash after either effect. Resume cannot consume R1.

## 5. R4 terminal event + Consumption matrix

Interrupt after:

```text
terminal stage intent durable / no effects
work_target_removed applied
work_completed E1 applied
Consumption C1 written
stage flags partially unsaved
terminal K2 locally committed
K2 proof passed
terminal push fails/succeeds
```

Required:

- no duplicate E1;
- no second Consumption ID;
- exact R1/E1/K1/operation tuple reused;
- receipt/event uniqueness remains 0-or-1;
- conflicting C1 path -> reconcile, never overwrite;
- conflicting second Consumption -> validation fail closed.

### P3 totality states

Test all:

```text
review-v1 E1 + matching C1
-> valid

review-v1 E1 only + matching pending terminal stage proving C1 remaining
-> recoverable transient

review-v1 E1 only + no matching pending stage
-> invalid / reconcile
```

Test symmetric Consumption-only corruption/recovery state where ordering permits.

Review metadata alone must not change `ProjectView` lifecycle.

## 6. R5 result commit / proof / push matrix

Required cases:

```text
K1 effect not recorded
K1 effect recorded / commit not made
K1 made / commit_id+applied durable save interrupted
K1 made + durable ID / post-commit proof not run
proof fails
proof passes / push not recorded
push recorded / network failure
push succeeds / terminal stage not begun
```

### Exact K1 reconstruction after save interruption

Mandatory fault injection:

```text
record commit effect
-> real git commit succeeds producing K1
-> crash before mutation records commit_id/applied
-> resume
```

PASS only when the repaired R5 positive proof establishes exact branch, exact one-parent relation to recorded base, complete expected parent->tree delta, no extra post-commit commit, complete Git inspection and current Review identities. Then the same K1 ID is durably backfilled before Review proof/push proceeds.

Negative fixtures:

- matching message but wrong tree;
- extra commit after K1;
- wrong parent;
- changed branch;
- unexpected mode/blob/deletion/link/gitlink entry;
- unanswerable Git query;
- conflicting existing durable commit ID.

All negative cases reconcile. Message match alone never identifies K1.

General assertions:

- executor not rerun merely to finish a positively recovered K1 path;
- no push before proof pass/binding;
- failed proof creates no push effect;
- push retry rechecks exact destination/branch/commit/latest authorization;
- authorized K1 may be remotely present while Work remains non-terminal until K2;
- no-result Work gets metadata-only K1;
- legacy semantics unchanged before review-v1 activation.

## 7. R6 Review-validity HEAD advancement

Cases include:

- unrelated intervening commit + complete proven closure -> reuse allowed;
- Review Context/evidence/tool/Git semantic dependency touched -> no reuse as appropriate;
- `.gitattributes`/filter/config/hook semantics changed -> no fast path;
- closure completeness unknown -> new Candidate;
- rewritten/rebased base -> reconcile;
- merge material dependency touched in parent -> detected;
- changed then reverted still counts;
- non-repo material identity change invalidates reuse.

No test passes reuse only because result paths were untouched.

## 8. R7 Class A

Required:

- positively identified operation-owned transformed K1 -> exact C2/R2/K2 path;
- K1 lacking durable made ID may enter only after R5 positive reconstruction proves its identity;
- unexpected/non-owned path -> reconcile;
- multiple parent -> refused;
- branch/lineage change -> adoption invalid;
- destination already contains K1 (`=` while HEAD K1) -> historical escape/reconcile path, not normal adoption;
- new/fast-forward may continue;
- rejection/unknown -> reconcile;
- K2 exact metadata-only -> accepted;
- hook adds domain/transition delta -> reconcile;
- no recursive Receipt chain;
- crash after K2 before push resumes exact K2 proof/push.

## 9. R8 Roadmap semantic round-trip

Cover multiple Phases/order, optional sections, relations, stable IDs and canonical normalization. Fault inject changed relation/desired-state/section/ID/extra-missing entity or loader interpretation. Request identity alone must not make semantic proof pass.

## 10. R9 Phase-entry semantic round-trip / authority

Cover normal Works, integration, confirmation, Related, planned/requires edges, stable reservations/resume and origin.

Roadmap-owned review-v1 precondition cases:

```text
canonical graph uniquely selects A, entry=A -> PASS
canonical graph uniquely selects A, entry=B -> reject
canonical graph ambiguous A/B, entry=A -> reject for review-v1
no explicit entry, canonical graph uniquely selects A -> PASS
```

Tests must demonstrate the rule is enforced by the Roadmap review-v1 planning path and merely verified by the adapter. Adapter-only semantic override is not accepted.

After clone/reload, first Work remains derivable without Review metadata.

## 11. R10 Policy adapter harness

P1 tests only generic protocol/harness. Unimplemented Project/Global adapters fail explicitly; no fallback generic policy store is invented.

## 12. R11 Evidence completeness

Synthetic adapters cover required/observed/pinned/denied/unknown dependencies; dynamic/subprocess/network/env/cache/tool/runtime cases; unknown means no cross-Candidate reuse; prompt-only claims never count as mechanical denial/coverage.

## 13. Clone/runtime-cleanup

For open/sealed canonical Review state:

```text
remove `.workline/runtime/**` or clone fresh
-> Gate/Receipt/Consumption/accepted-task descriptors reconstruct from canonical files
-> `ProjectView` lifecycle remains entities/relations/events only
```

A sealed authorization may never depend on runtime-only task identity.

## 14. Authority boundary

Mechanical tests prove:

- Review metadata cannot directly change Work/Phase/Roadmap lifecycle;
- Roadmap/START remain transition owners;
- R9 self-selection semantic is Roadmap-owned at review-v1 activation;
- Review writes use the same Project lock/mutation authority;
- foreign Project context cannot mutate Review state;
- concurrent active writer gets ordinary Project-lock refusal;
- cross-crash generation conflict is still caught through pending initial WriteScope.

## 15. Activation gates

P1 common infrastructure is not implementation-complete until repaired R1-R7/R10/R11 tests pass.

P2 Planning activation additionally requires R8/R9 tests.

P3 START activation additionally requires full R4/R5/R7 terminal/commit/proof/push interruption and totality tests.

Happy path alone is insufficient.

## 16. External-review repair disposition

This revision adds explicit tests for every accepted independent-review seam: K1 identity save interruption, generation fork after lock loss, write-time path TOCTOU, immutable create-only enforcement, clone-safe async task descriptor, terminal totality, first-write committability and canonical predecessor digest.

Architecture blocker: `None`.

HUMAN decision: `None`.
