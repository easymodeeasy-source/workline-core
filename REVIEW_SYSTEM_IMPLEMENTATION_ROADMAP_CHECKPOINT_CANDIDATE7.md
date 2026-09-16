# Review System Implementation Roadmap Checkpoint — Candidate 7

Status: DESIGN REPAIRED AFTER FIFTH EXTERNAL REVIEW / IMPLEMENTATION NOT STARTED

This file is a non-normative design checkpoint. Runtime authority remains `registry.md` plus registry-routed canonical Skills. It supersedes `REVIEW_SYSTEM_IMPLEMENTATION_ROADMAP_CHECKPOINT_CANDIDATE6.md` as the latest design checkpoint while preserving Candidate 6 and earlier checkpoints as history.

Candidate 6 received an independent external review with verdict `REPAIR`. All seven Findings (C6-01 through C6-07) are accepted. No HUMAN decision was required. Candidate 7 incorporates those repairs while retaining the core architecture: Review is an authorization/quality gate, never a second lifecycle/progression controller.

## 1. Candidate 6 external review adjudication

| ID | Category | Severity | Adjudication | Candidate 7 repair |
| --- | --- | --- | --- | --- |
| C6-01 | Problem | HIGH | ACCEPT | HEAD advancement Review-validity proof is tied to a complete proven dependency/provenance closure; unknown completeness forces new Candidate generation |
| C6-02 | Problem | MID | ACCEPT | Add `AuthorizedTransitionProjection` between reviewed artifact and non-normative operation metadata |
| C6-03 | Problem | MID | ACCEPT | Consumption gets stable reserved identity plus logical uniqueness/cardinality enforcement |
| C6-04 | Problem | HIGH | ACCEPT | Add a minimum clone-safe `Review Gate Generation Record` in P1/P3 with durable async task settlement and sealed authorization semantics |
| C6-05 | Problem | MID | ACCEPT | `adopt_existing_local_commit` gains remote-publication checks and a metadata-only K2 recursion cutoff |
| C6-06 | Problem | HIGH | ACCEPT | Planning/Policy gain kind-specific semantic round-trip `PersistedProjectionAdapter` proof from reviewed semantics through canonical loader |
| C6-07 | Problem | MID | ACCEPT | Evidence completeness becomes dependency-class coverage proof, not merely a named basis |

External verdict: `REPAIR` — accepted.

HUMAN decisions: `0`.

## 2. Architecture retained

```text
Roadmap / START / Policy Change operation owner
  = progression / mutation / Git / lifecycle or registration transition owner

Review System
  = Candidate freeze / Evidence / reviewers / adjudication / authorization gate
```

Review durable records do not become lifecycle truth. `state.py` remains derived only from canonical domain events/entities/relations. The operation owner consumes Review authorization; Review does not advance lifecycle by itself.

## 3. HEAD advancement — Git-safe and Review-safe remain distinct

Candidate 7 keeps the Candidate 6 split:

```text
Git-write compatibility
!=
Review-validity compatibility
```

Default Review-v1 invariant:

```text
actual result-commit parent
=
verified Candidate base
```

An intervening HEAD advance may be accepted only through a fast path backed by positive proof.

### 3.1 Complete Review-validity dependency/provenance closure

At Review generation freeze, record a closure covering at least:

- ReviewedArtifact semantic dependencies
- Review Context provenance/dependencies
- Evidence dependencies
- Effective Policy / verifier-input dependencies
- Git attributes/filter/config dependencies that can affect persisted objects or verification meaning
- declared tool/runtime/dependency identities where material

The closure itself carries completeness status/evidence.

HEAD advancement is Review-valid only if:

```text
intervening changed surfaces
INTERSECT
complete proven dependency/provenance closure
=
empty
```

If closure completeness is `unknown` or cannot be proven sufficient:

```text
Review-validity = unknown
-> freeze new Candidate against new HEAD
-> reacquire invalidated Evidence / Review
```

Path non-conflict alone never proves Review validity.

Normal review-v1 result commits remain one-parent commits. Merge/multiple-parent result commits require an explicit future contract; otherwise STOP/reconcile.

## 4. Three projection model

Candidate 7 defines three distinct projections.

### 4.1 `ReviewedArtifactProjection`

The artifact whose correctness Review authorizes.

Examples:
- Work result domain/result delta
- reviewed semantic plan/policy projected into exact expected durable artifact identity for the applicable Review kind

`candidate_hash` is derived from this reviewed artifact identity plus declared base/context identity, not from Receipt/Consumption metadata.

### 4.2 `AuthorizedTransitionProjection`

Canonical transition effects that consume the authorization under the owning operation.

Examples:
- exact `work_completed` / `work_target_removed` event effects
- Roadmap/Phase registration entity/relation effects
- Project/Global Policy transition/version effects

These are not Review metadata. They are canonical lifecycle/registration/policy-transition effects owned by the domain operation.

### 4.3 `OperationMetadataProjection`

Non-normative durable Review/operation metadata, such as:
- Authorization Receipt
- Consumption Record
- supersession/provenance records required by the Review contract

Absolute rule:

```text
OperationMetadataProjection MUST NOT be a normative source for
state.py / progression / correctness definitions.
```

If a file later determines normative runtime behavior, it is not metadata and must be modeled as Context/Policy/canonical transition state under the appropriate authority.

### 4.4 Exact persistence proof

A persisted operation commit proves the exact union required for its kind:

```text
ReviewedArtifactProjection equality
+ AuthorizedTransitionProjection equality when applicable
+ OperationMetadataProjection equality when applicable
+ complete commit-delta scope equality
```

No allowed path bypasses content/semantic verification merely because its path is expected.

## 5. Common Authorization core remains immutable

Common immutable Authorization Receipt:

```yaml
receipt_id: ...
review_run_id: ...
review_kind: ...
target_identity: ...
operation_identity: ...
authorized_candidate_hash: ...
review_context_hash: ...
effective_policy_hash: ...
coverage_hash: ...
adjudication_hash: ...
review_generation: ...
obligation_digest: ...
unresolved_obligations: 0
authorized_operation_stage: ...
```

Receipt existence never equals operation completion.

Receipt does not contain the SHA of the commit that contains the Receipt itself.

## 6. Minimum durable `Review Gate Generation Record`

P1 introduces a clone/runtime-cleanup-safe minimum Review gate record before P3 activates Review-v1 terminal gating. This is intentionally smaller than the P5 full durable Review history.

Each immutable generation record conceptually includes:

```yaml
review_run_id: ...
generation: ...
candidate_hash: ...
review_context_hash: ...
effective_policy_hash: ...
evidence_digest: ...
coverage_digest: ...
raw_report_set_digest: ...
adjudication_digest: ...
obligation_digest: ...
accepted_async_task_ids: [...]
settled_async_task_ids: [...]
status: open | sealed_authorized | superseded
```

Only `sealed_authorized` generations may issue/retain consumable Authorization Receipts.

A fact that may invalidate an old authorization is durably reflected through a newer generation/invalidation record before the old authorization may continue toward push/transition consumption.

## 7. Async/shadow ordering is logical and durable, not wall-clock based

For a Review generation:

```text
accepted task
= task identity/request durably recorded in the gate generation

settled task
= terminal task result/status + digest durably recorded
```

Authorization seal requires all required accepted tasks to be settled under Effective Policy.

If a raw report arrives, the prior seal cannot remain consumable while that report is pending adjudication. The task is not considered settled for authorization purposes until its supported disposition is durably represented, for example:

- dismissed with durable adjudication
- LOW with required LOW handling/workization obligation satisfied
- HIGH/MID with repair/reverification obligation satisfied
- timeout/cancel/failure disposition explicitly permitted by Effective Policy

Unknown/duplicate callbacks cannot silently rewrite an old sealed generation.

Historical escape remains only for results whose relevant task/result did not belong to the pre-terminal durable authorization set under the cutoff contract.

## 8. Work Consumption identity and uniqueness

Consumption remains a separate immutable fact, but Candidate 7 makes identity reservation mechanical.

Before the mutation stage that creates terminal effects is recorded, reserve a stable Consumption identity from that same mutation, conceptually keyed by the authorization, e.g.:

```text
review-consumption:<receipt_id>
```

For Work completion, logical uniqueness invariants are:

```text
receipt_id -> 0 or 1 valid Consumption
terminal_event_id -> 0 or 1 valid Consumption
```

Exact existing tuple:

```text
(receipt_id, terminal_event_id, authorized_result_commit_sha, operation_id)
```

is idempotently reused on resume.

Conflicts fail closed:

```text
same receipt + different event/commit/operation -> reconcile required
same terminal event + different receipt -> reconcile required
superseded receipt -> may not create a new Consumption
```

## 9. Atomic Work terminal transition remains one mutation stage

Once result commit K1 exists locally and all post-commit Review proofs pass:

1. reserve terminal event ID E1;
2. reserve stable Consumption ID C1;
3. record one mutation stage containing the exact `AuthorizedTransitionProjection` and `OperationMetadataProjection` effects;
4. apply/recover effects under normal Mutation Controller expected-before/after classification;
5. final terminal commit/push may proceed only once all required stage effects are matching/applied.

Conceptually:

```text
AuthorizedTransitionProjection:
  work_completed E1 (+ other exact canonical terminal effects if required)

OperationMetadataProjection:
  Consumption C1 binding R1 + K1 + E1
```

Physical writes need not be atomic because the Mutation Controller can recover individual effects; the durable intent/stage and exact effect identities must make partial application replay-safe.

Lifecycle truth remains the canonical event/state, not Consumption metadata.

## 10. Class A `adopt_existing_local_commit` — stricter preconditions

Class A remains a special authorization type for an exact local unpushed commit K1 that is entirely operation-owned but differs from the old Candidate due to operation-owned/Git transformation.

Preconditions include:

```text
exact K1 object ID
expected one-parent lineage
operation-owned commit delta only
configured local branch lineage unchanged
new Receipt R2 authorizes exact K1
configured push destination does NOT already contain/publish K1 as an unauthorized result
```

If the configured destination already contains K1 before Review authorization/push proof:

```text
not normal Class A adoption
-> record unauthorized publication / historical escape as applicable
-> reconcile/recovery path
```

### 10.1 Metadata-only K2 recursion cutoff

R2 also authorizes the deterministic OperationMetadataProjection needed to record R2 and the old-Receipt supersession fact.

K2:

```text
must contain no ReviewedArtifact/domain delta
must contain no AuthorizedTransition delta
must match exact deterministic metadata projection
must pass complete scope proof
```

K2 does **not** require another Review Receipt.

If K2 mismatches its deterministic metadata projection or contains any extra domain/transition delta:

```text
reconcile required
no recursive Class-A re-review loop
no push
```

This terminates metadata authorization recursion.

## 11. `PersistedProjectionAdapter` — semantic round-trip proof

Each Review kind that authorizes persisted canonical state defines a `PersistedProjectionAdapter`.

Common invariant:

```text
Reviewed semantic Candidate
+ stable/reserved IDs
+ base/version/schema-loader identity
↓
deterministic expected canonical effects
↓
local commit
↓
exact artifact / transition / metadata / scope proof
↓
canonical loader / ProjectView re-read
↓
normalized persisted semantics
=
Reviewed semantic Candidate
```

Byte/hash equality is required for artifact integrity where applicable but does not replace semantic equality.

### 11.1 Roadmap Review

`RoadmapPlan` + reserved entity/relation IDs deterministically projects to expected Roadmap/Phase/relation effects. After commit, canonical ProjectView/loader reconstruction must yield a semantic graph equal to the reviewed plan.

### 11.2 Phase Design Review

`PhaseEntryDesign` + reserved Work/integration/relation IDs projects to exact expected entities/relations. Re-loaded persisted semantics must equal the reviewed design.

### 11.3 Project Policy Change

Normalized reviewed Project Policy after-state must equal:

```text
normalize(canonical_load(committed Project policy/profile))
```

Loader/schema/default semantics version is part of Review Context.

### 11.4 Global Policy Change

Normalized reviewed Global Policy after-state must equal the canonical loader interpretation of the exact committed Workline-root policy artifact, with version/schema/default semantics bound to Review Context.

Project/Global Policy paths retain local commit -> exact proof -> no-push-before-proof discipline.

## 12. Evidence completeness is dependency-class coverage proof

A named basis such as `hermetic sandbox` or `observed trace` is not sufficient by itself.

Each Evidence adapter states a proof claim, conceptually:

```yaml
basis: observed_trace
implementation_version: ...
covered:
  - filesystem_reads
  - environment
  - child_process_filesystem
  - dynamic_libraries
not_covered:
  - network
  - clock
  - randomness
  - hardware
```

The Evidence/check also declares the dependency classes it may materially rely on.

Cross-Candidate reuse is allowed only if:

```text
required dependency classes
SUBSET OF
mechanically covered/pinned/denied dependency classes
```

and all concrete dependency identities within those classes are positively proven unchanged.

If any required class is unknown/uncovered:

```text
completeness = unknown
-> no cross-Candidate reuse
```

The same completeness contract is used by HEAD advancement Review-validity fast paths.

## 13. Policy experiment overlap retained

Three-state overlap remains:

```text
proven_disjoint
known_overlap
overlap_unresolved
```

Only `proven_disjoint` experiments may observe concurrently. Unknown overlap serializes/supersedes rather than requiring HUMAN by default.

## 14. Integration, LOW, causality, global independence retained

The following prior repairs remain in force:

- Integration verification forbids undeclared persistent Project/external/nested side effects.
- Deferred Review LOW uses one Project-wide chain, strict first-nonterminal head eligibility, and fail-closed structural validation.
- Causality supports `supported / unresolved / insufficient_evidence`; only supported strong causality is counted as C.
- Global promotion uses `proven_independent / known_correlated / independence_unresolved`; only proven-independent sources count separately.

## 15. Seven-phase implementation Roadmap — Candidate 7

### P1 — Review Core + Authority + minimum durable gate + three projections + projection adapters

Desired state: core Review semantics/recovery exist before activation, with clone-safe minimum gate state and exact authority boundaries.

Works:
- canonical Review Skill / registry routing / Review Constitution
- Review domain model
- Candidate / Context / Effective Policy identities
- Git-safe vs Review-safe compatibility contract
- complete dependency/provenance closure contract
- `ReviewedArtifactProjection`
- `AuthorizedTransitionProjection`
- `OperationMetadataProjection`
- immutable common Authorization core
- kind-specific Consumption interface
- stable Consumption reservation/uniqueness foundation
- minimum durable `Review Gate Generation Record`
- async task durable accepted/settled contract
- `PersistedProjectionAdapter` common interface
- runtime Review recovery compatibility
- durable layout/bootstrap/residue prerequisites
- synthetic cross-layer recovery/invariant tests

P1 does not activate Work terminal Review gating.

### P2 — Planning Review Gates + semantic round-trip proof

Desired state: reviewed Roadmap/Phase semantics are exactly what canonical Project state contains after registration.

Works:
- RoadmapPlan Candidate / Review / repair continuation
- stable/reserved ID projection
- Roadmap `PersistedProjectionAdapter`
- canonical semantic graph round-trip proof
- PhaseEntryDesign Candidate / Review / repair continuation
- Phase `PersistedProjectionAdapter`
- Works/integration/relation semantic round-trip proof
- planning-native Authorization/Consumption binding
- crash/resume/idempotency tests

### P3 — START Review Gate + complete Review-validity closure + deterministic Consumption + Class A publication rules

Desired state: a review-v1 Work cannot push/terminalize under stale semantic assumptions or ambiguous authorization.

Works:
- review-v1 vs legacy durable contract identity
- Candidate Builder/base-lineage identity
- Review-validity closure freeze and HEAD advancement fast path
- isolated verification
- Review Gate generations/sealing
- three-projection commit proof
- no-push-before-proof
- Class A/B/C mismatch handling
- `adopt_existing_local_commit`
- remote-publication precondition
- metadata-only K2 recursion cutoff
- terminal event + Consumption stable ID reservation
- one-stage transition/Consumption recovery
- logical uniqueness/cardinality checks
- stale-generation blocking
- durable async/shadow cutoff
- interruption tests at every boundary

### P4 — Repair Loop + dependency-class completeness + isolated Integration

Desired state: Evidence reuse/repair remains safe even when dependency closure cannot be fully proven.

Works:
- ReviewRepairRequest / executor repair purpose
- Repair Batch / Coverage Check
- Candidate generations
- Evidence dependency-class declarations
- completeness proof claims/coverage contracts
- conservative invalidation on unknown coverage
- same-run A/B/C / instability strategy change
- Integration side-effect contract / disposable adapters
- normal fix Work + reintegration

### P5 — Full Durable Review History + causality + LOW validation

Desired state: full long-lived recurrence/causality/history exists without becoming lifecycle truth.

Works:
- full `.workline/review/` history
- Run/Finding/Repair summaries
- durable causal material
- cross-run recurrence
- LOW provenance/workization
- strict structural chain validation/head eligibility

### P6 — Project-local Adaptive Policy + semantic persisted-policy proof

Desired state: Project policy changes are experimentally attributable and the exact canonical semantics loaded after commit equal the reviewed policy Candidate.

Works:
- Project Policy Change operation
- Project Policy `PersistedProjectionAdapter`
- canonical loader semantic round-trip proof
- no-push-before-proof
- shadow/holdout escalation
- three-state experiment overlap
- observation/retain/adjust/rollback

### P7 — Global Promotion + semantic root-policy proof

Desired state: Global policy changes only from sufficiently independent evidence, and exact loaded root-policy semantics equal what was reviewed.

Works:
- Promotion Packet/correlation model
- Global Policy Change operation
- Global Policy `PersistedProjectionAdapter`
- canonical loader semantic round-trip proof
- root artifact/scope proof
- no-push-before-proof
- Project adoption at next safe Review Run boundary
- observation/retain/rollback

## 16. Candidate 7 readiness objective

Candidate 7 is intended to be the final broad architecture-design candidate before switching review mode.

The next review should not require “zero possible new Finding” as the stopping rule. Instead it should determine whether unresolved items are still architecture blockers or have become P1 live-contract/reconnaissance details.

Proposed readiness criterion:

```text
READY_FOR_P1 iff
1. lifecycle / authority / ownership boundaries are fixed;
2. Review is not a second controller;
3. Candidate / Evidence / Authorization / Consumption / Git invariants are fixed;
4. crash/resume is fail-closed at the architecture level;
5. Planning / Work / Integration / Policy Change responsibilities are fixed;
6. remaining uncertainty requires live-code interface/schema reconnaissance rather than a new architecture decision;
7. unresolved HUMAN decisions = 0.
```

Current status:

```text
Candidate 6 external review verdict: REPAIR
C6-01..C6-07: ACCEPTED
HUMAN decisions: 0
Candidate 7: CREATED
Implementation: NOT STARTED
Candidate 7 Implementation Readiness Review: NOT YET RUN
```
