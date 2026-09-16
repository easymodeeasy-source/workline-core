# Review System P1 — Integration Contract Reconnaissance Checkpoint

Status: R1-R12 CONTRACTS REPAIRED AFTER INDEPENDENT REVIEW / IMPLEMENTATION NOT STARTED / RE-REVIEW REQUIRED

This checkpoint records the Candidate 7 P1 Integration Contract Reconnaissance and the accepted independent-review repairs.

It is non-normative design/implementation-contract history until corresponding implementation and canonical authority updates are activated. Runtime authority remains `registry.md`, registry-routed canonical Skills, and live code.

## 1. Baseline

Candidate 7 readiness established:

```text
Architecture blockers: 0
HUMAN decisions: 0
Verdict: READY_FOR_P1
```

P1 reconnaissance then froze R1-R12 against live store/layout, Project Start/bootstrap, Mutation Controller, Project lock, Git helpers/finalization, IDs, validation, Roadmap/Phase planning identities, `ProjectView/state.py`, START completion/finalization and tests.

An independent review then found no Candidate 7 architecture blocker and no HUMAN decision, but identified nine implementation-contract seams. Those findings were accepted.

## 2. Independent review disposition

```text
Candidate 7 architecture: RETAIN
Architecture blockers: 0
HUMAN decisions: 0
Candidate 8 required: No
P1 contract before repair: REPAIR REQUIRED
Implementation during repair: DO NOT START
```

Accepted repair themes:

1. exact K1 recovery after commit succeeds but mutation `commit_id` save is interrupted;
2. generation serialization must survive process-lock loss through pending mutation conflict scope;
3. Review canonical writes need write-time no-follow/reparse/TOCTOU safety;
4. accepted async task descriptors must be clone-safe;
5. immutable Review records need create-only semantics;
6. P3 review-v1 terminal event requires exactly one Consumption;
7. PhaseEntry canonical self-selection must be Roadmap-owned, not adapter-owned;
8. first Review write needs Git committability preflight;
9. predecessor digest/test matrix needed exact byte/crash contracts.

The umbrella repair is recorded in:

`REVIEW_SYSTEM_P1_CONTRACT_REPAIR_AFTER_EXTERNAL_REVIEW.md`

## 3. Current R1-R12 status

### R1 — Durable layout / loader / bootstrap

`REVIEW_SYSTEM_P1_R1_DURABLE_LAYOUT_CONTRACT.md`

Repaired/frozen:

- lazy canonical `.workline/review/` layout retained;
- runtime Review area remains non-authoritative;
- immutable Review records use create-only semantics;
- write-time lstat/no-follow containment and parent identity recheck required;
- symlink/junction/reparse/TOCTOU redirection outside Project is refused;
- first Review write requires Git committability preflight;
- predecessor digest = SHA-256 of versioned canonical UTF-8/LF bytes;
- `ReviewStore` remains separate from `ProjectView/state.py`.

### R2 — IDs / reservation

`REVIEW_SYSTEM_P1_R2_ID_RESERVATION_CONTRACT.md`

Stable kinds remain:

```text
review_run         -> rr
review_receipt     -> rcp
review_consumption -> rcs
review_task        -> rtk
```

Repair:

- Project execution lock alone is not generation serialization;
- exact next-generation path must be present in the mutation's initial `WriteScope.files` before effects/reservations;
- late `extend_scope()` is not accepted as the cross-crash generation lock;
- clone-safe task identity is completed by R3 canonical descriptors.

### R3 — Gate Generation mutation contract

`REVIEW_SYSTEM_P1_R3_GATE_GENERATION_MUTATION_CONTRACT.md`

Repaired/frozen:

- top-level owner remains Roadmap/START/future Policy owner;
- no Review progression controller;
- every N+1 generation is allocated only after validating chain and opening/resuming a pending mutation whose initial WriteScope already contains exact N+1 path;
- pending mutation provides cross-crash serialization after OS lock disappears;
- accepted tasks carry clone-safe canonical descriptors: task ID/slot/kind, reviewer-or-adapter identity/version, request digest, Candidate/Context/Policy binding, accepted generation;
- seal+Receipt remains one mutation decision/stage;
- invalidation uses later open generation + supersession;
- clone-safe gate facts reach tracked local Git state before dependent external/terminal boundaries.

### R4 — Consumption logical uniqueness / totality

`REVIEW_SYSTEM_P1_R4_CONSUMPTION_UNIQUENESS_CONTRACT.md`

P1 common foundation:

```text
Receipt -> 0 or 1 valid Consumption
terminal_event_id -> 0 or 1 valid Consumption
```

P3 review-v1 activation additionally requires:

```text
review-v1 terminal event -> exactly one matching valid Consumption
```

Only a matching pending terminal mutation may justify the transient state where E1 exists but C1 is not yet applied. Without matching pending recovery, the state is invalid/reconcile. `state.py` still derives lifecycle only from events.

### R5 — START result commit / proof / push split

`REVIEW_SYSTEM_P1_R5_START_COMMIT_PROOF_PUSH_CONTRACT.md`

Topology retained:

```text
local K1
-> exact K1 identity
-> post-commit proof
-> authorized push K1
-> terminal event + Consumption
-> local K2
-> exact K2 proof
-> authorized push K2
```

Critical repair:

```text
git commit succeeds
-> process crashes before commit_id/applied save
```

Resume may backfill K only after positive proof of exact branch, one-parent/base relation, complete expected parent->tree delta, no extra post-commit commit, complete Git inspection and current Review identities. Only then is K durably backfilled and allowed to enter Review proof/push. Commit message never identifies K.

R7 Class A depends on this exact commit-identity primitive.

### R6 — HEAD advancement closure

`REVIEW_SYSTEM_P1_R6_HEAD_ADVANCEMENT_CLOSURE_CONTRACT.md`

No repair required. Positive-proof Review-validity closure remains frozen; unknown completeness means new Candidate rather than negative-search reuse.

### R7 — Class A `adopt_existing_local_commit`

`REVIEW_SYSTEM_P1_R7_CLASS_A_ADOPTION_CONTRACT.md`

Architecture retained. Implementation readiness is conditional on repaired R5 exact K1 identity reconstruction/backfill. Class A cannot adopt a merely plausible unrecorded commit identity.

### R8 — Roadmap `PersistedProjectionAdapter`

`REVIEW_SYSTEM_P1_R8_ROADMAP_PROJECTION_ADAPTER_CONTRACT.md`

No repair required. Live `RoadmapPlan`, request identity, stable reservations, registration helpers, projection and canonical reload remain sufficient for semantic round-trip.

### R9 — Phase Entry `PersistedProjectionAdapter`

`REVIEW_SYSTEM_P1_R9_PHASE_ENTRY_PROJECTION_ADAPTER_CONTRACT.md`

Repair:

- canonical self-selection remains required for review-v1 planning;
- the rule is owned by canonical Roadmap authority at P2 activation;
- the adapter only verifies Roadmap-owned semantics and persisted round-trip;
- legacy explicit-entry behavior remains unchanged before review-v1 activation;
- Review metadata never becomes progression truth.

### R10 — Project / Global Policy adapter hook

`REVIEW_SYSTEM_P1_R10_POLICY_ADAPTER_HOOK_CONTRACT.md`

No repair required. P1 freezes only common adapter/loader/version hooks; final Project/Global policy schemas and physical ownership remain P6/P7 reconnaissance work.

### R11 — Evidence dependency-class adapter contract

`REVIEW_SYSTEM_P1_R11_EVIDENCE_DEPENDENCY_CLASS_CONTRACT.md`

No repair required. Unknown/uncovered dependencies remain non-reusable; same completeness discipline feeds R6.

### R12 — Recovery / invariant tests

`REVIEW_SYSTEM_P1_R12_RECOVERY_INVARIANT_TEST_CONTRACT.md`

Expanded to require explicit tests for:

- K1 commit success / commit-ID save interruption and positive reconstruction;
- generation fork attempt after crash/lock release;
- Review-path symlink/junction/reparse TOCTOU;
- immutable create-only overwrite refusal;
- clone-safe async task descriptor after runtime removal/fresh clone;
- review-v1 terminal E1/C1 totality states;
- first-write Git committability STOP-before-effect;
- exact predecessor canonical-byte SHA-256 behavior;
- R9 Roadmap-owned self-selection authority boundary.

## 4. Cross-contract implementation shape after repair

The implementation decomposition remains:

```text
A. ReviewStore + safe immutable canonical Review writer
B. central Review ID extensions/reservation helpers
C. crash-safe Gate generation + clone-safe task descriptors + Receipt orchestration
D. common Consumption uniqueness foundation / P3 terminal totality hook
E. commit-only / exact commit identity reconstruction / proof / push-only Git primitives
F. complete Git tree-delta and Review-validity closure plumbing
G. Class A adoption flow using proven K1 identity
H. PersistedProjectionAdapter protocol
I. Roadmap adapter
J. Phase-entry adapter + Roadmap-owned review-v1 self-selection rule
K. Policy adapter hook
L. Evidence dependency completeness engine
M. expanded interruption/recovery/invariant suite
```

P1 does not yet activate Work terminal Review gating; that remains P3.

## 5. Current checkpoint

```text
Candidate 7 architecture: RETAIN
Architecture blockers: 0
HUMAN decisions: 0
Candidate 8 required: No

Independent review findings: ACCEPTED
P1 contract repairs: FROZEN
R1-R12: REPAIRED/FROZEN where affected
P1 implementation: NOT STARTED
Implementation activation: BLOCKED pending independent re-review
```

## 6. Next stage

Run a focused independent implementation-readiness re-review against the repaired contracts and live repo.

Final verdict must be one of:

```text
REPAIR
HUMAN
READY_FOR_P1_IMPLEMENTATION
```

Only `READY_FOR_P1_IMPLEMENTATION` permits implementation to start.
