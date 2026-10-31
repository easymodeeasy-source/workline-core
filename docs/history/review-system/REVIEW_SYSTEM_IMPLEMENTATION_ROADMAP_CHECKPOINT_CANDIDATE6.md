# Review System Implementation Roadmap Checkpoint — Candidate 6

Status: DESIGN REPAIRED AFTER FOURTH EXTERNAL REVIEW / IMPLEMENTATION NOT STARTED

This file is a design checkpoint, not normative authority. Runtime authority remains `registry.md` plus registry-routed canonical Skills. It supersedes `REVIEW_SYSTEM_IMPLEMENTATION_ROADMAP_CHECKPOINT_CANDIDATE5.md` as the latest implementation-roadmap design checkpoint while preserving Candidate 5 and earlier checkpoints as history.

Candidate 5 received an independent review with verdict `REPAIR`. All eight Findings (C5-01 through C5-08) are accepted. Candidate 6 below incorporates the adjudicated repairs while preserving the central architecture: Review remains a quality gate and does not become a second lifecycle/progression controller.

## 1. Candidate 5 external review adjudication

| ID | Category | Severity | Adjudication | Candidate 6 repair |
| --- | --- | --- | --- | --- |
| C5-01 | Problem | HIGH | ACCEPT | Git-write compatibility and Review-validity compatibility are separated; HEAD advancement requires positive proof or new Candidate generation |
| C5-02 | Problem | HIGH | ACCEPT | ReviewedArtifactProjection and OperationMetadataProjection are separated to eliminate Candidate/Receipt self-reference |
| C5-03 | Problem | HIGH | ACCEPT | terminal event and Consumption Record are reserved/applied in one mutation decision/stage with cardinality invariants |
| C5-04 | Problem | MID | ACCEPT | Class A gains an explicit `adopt_existing_local_commit` authorization/consumption path |
| C5-05 | Problem | MID | ACCEPT | Evidence dependency completeness requires a proof basis, not adapter self-assertion |
| C5-06 | Problem | HIGH | ACCEPT | Review generation and operation pending mutation gain a cross-layer consistency invariant preventing stale authorization |
| C5-07 | Problem | MID | ACCEPT | Policy experiment overlap becomes three-state with fail-safe serialization for unresolved overlap |
| C5-08 | Problem | HIGH | ACCEPT | Common authorization core is separated from kind-specific consumption/persistence bindings for Work, Planning, and Policy Change |

No Candidate 5 Finding requires a HUMAN decision. The external verdict `REPAIR` is accepted.

## 2. Core architecture retained

Review remains subordinate to existing operation ownership.

```text
Roadmap / START / Policy Change operation owners
  -> progression, mutation ownership, Git finalization, lifecycle/registration effects

Review System
  -> freeze Candidate / Context / Policy
  -> obtain Evidence / independent reviewer coverage
  -> adjudicate Findings
  -> issue authorization only when obligations are zero
```

Review never directly advances lifecycle state. `state.py` remains derived from canonical events/entities/relations only. Review durable records prove authorization/provenance but are not a second lifecycle ledger.

## 3. Two compatibility layers: Git-safe is not Review-safe

Candidate 6 separates two questions that Candidate 5 still mixed.

### 3.1 Git-write compatibility

Existing mutation/Git logic may determine that an intervening commit does not collide with the operation-owned paths and therefore writing a result commit is Git-safe.

### 3.2 Review-validity compatibility

Review-v1 additionally requires that the semantic base used for Candidate verification remains valid.

Default invariant:

```text
actual result-commit parent
=
base commit against which the Candidate was verified
```

If HEAD advances after verification, the operation may continue without a new Candidate only if the intervening commits are positively proven irrelevant to:

- ReviewedArtifactProjection semantics
- Review Context
- Evidence dependencies
- tool/runtime/dependency identities that materially affect verification

Path non-conflict alone is never sufficient.

If such proof is unavailable:

```text
new HEAD
-> new Candidate generation
-> required Evidence reacquisition / Review
-> only then result commit
```

Normal review-v1 result commits are one-parent commits. Merge/multiple-parent result commits are not silently generalized; unless a future explicit contract exists they STOP/reconcile.

Commit delta comparison uses exact parent-tree to commit-tree path/entry differences, not rename heuristics.

## 4. Reviewed artifact and operation metadata are separate projections

Candidate 6 removes Candidate/Receipt self-reference by defining two independent projections.

### 4.1 ReviewedArtifactProjection

This is the artifact whose correctness Review authorizes.

`candidate_hash` is computed only from this projection plus its declared base/context identity.

For a Work this normally contains the Work-owned domain/result delta with Git-persist-equivalent entry semantics.

### 4.2 OperationMetadataProjection

This contains canonical Workline-owned durable metadata that must accompany or prove the operation but is not itself part of the reviewed artifact hash.

Examples may include:

- Authorization Receipt
- approved durable Review metadata required by the operation contract

The expected metadata projection is fixed before the commit that persists it:

```text
canonical namespace/path set
+ deterministic expected content/hash
```

It may not grow opportunistically after Candidate/authorization freeze.

`.workline/runtime/` and pending mutation metadata are never committed as OperationMetadataProjection.

### 4.3 Post-commit proof now has three checks

```text
A. ReviewedArtifactProjection equality
B. OperationMetadataProjection equality
C. complete commit-delta scope equality
```

Thus an expected metadata path with wrong content cannot pass merely because its path was allowed.

Authorization Receipt does not contain the SHA of the commit that contains that Receipt, avoiding Git self-reference.

## 5. Common Authorization core

All Review kinds reuse a common authorization meaning but do not share a Work-shaped completion schema.

Common Authorization Receipt concept:

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

The Receipt is immutable / append-only.

Common rule:

```text
Receipt exists
!=
operation successfully consumed that authorization
```

Consumption is a separate immutable fact with kind-specific persisted-result identity.

## 6. Work completion consumption — atomic terminal binding

For Work completion, once the local result commit K1 is known and all post-commit proofs have passed, the operation reserves the terminal event identity before final terminalization.

Conceptually:

```text
terminal_event_id E1 reserved
Consumption C1 prepared:
  receipt_id = R1
  operation_id = M1
  authorized_result_commit_sha = K1
  terminal_event_id = E1
```

Then:

```text
append work_completed E1
+
write immutable Consumption C1
```

are one mutation decision/stage and are finalized durably together under the same terminal recovery contract.

The Consumption Record refers to the already-existing authorized result commit SHA K1; it does not attempt to include the SHA of the terminal metadata commit that contains itself.

Cardinality invariants:

```text
one Authorization Receipt -> at most one valid Consumption
one review-v1 terminal event -> exactly one matching valid Consumption
same R1 + same E1 + same K1 -> idempotent replay
same R1 with a different Consumption -> reconcile required
same E1 with a different Receipt -> reconcile required
```

Lifecycle truth remains `work_completed` event/state. Consumption proves which Review authorization permitted that terminal transition; it is not the lifecycle truth itself.

## 7. Planning Review uses kind-specific consumption binding

Roadmap and Phase Design Review reuse the common Authorization core but do not invent terminal events that do not exist in live authority.

### 7.1 Roadmap creation

Consumption binds authorization to facts such as:

```text
roadmap_request_identity
create-roadmap mutation/stage identity
created roadmap/phase IDs as applicable
registration commit identity
```

No fake `terminal_event_id` is introduced.

### 7.2 Phase entry/design

Consumption binds to:

```text
design_identity
phase-entry mutation/stage identity
created Work/integration IDs
registration commit identity
```

Again, no Work-shaped completion event is required.

The common abstraction is authorization + exact consuming operation/stage; persisted result identity is kind-specific.

## 8. Policy Change Review uses exact persisted-policy proof

Project and Global Policy Change operations also use the common Authorization core plus kind-specific Consumption.

### 8.1 Project Policy Change

Consumption binds to:

```text
before Project Profile version
new Project Profile version
exact persisted policy projection/hash
policy commit SHA
policy-change operation/stage identity
```

The Project Policy Change path receives Work-equivalent persistence discipline:

```text
local commit
-> exact reviewed policy projection proof
-> exact metadata/scope proof
-> only then push
```

### 8.2 Global Policy Change

Consumption binds to:

```text
before Global Policy version
after Global Policy version
exact root policy projection/hash
root commit SHA
root maintenance operation/stage identity
```

It also requires local commit -> exact post-commit artifact/scope proof -> push.

Rollback remains a new version/new commit, never history rewrite.

## 9. Class A recovery — `adopt_existing_local_commit`

Candidate 6 formalizes the special case where a local unpushed commit K1 exists, is entirely operation-owned, but differs from the old Attested Candidate due to Git semantics or another operation-owned transformation.

Flow:

```text
K1 mismatch
-> durable mutation checkpoint records K1 / old Candidate / Class-A classification
-> freeze exact K1 owned projection as Candidate C2
-> verify/review C2
-> if accepted, issue new Receipt R2 authorizing exact existing local commit K1
-> record immutable supersession fact for old R1 where applicable
-> persist R2/supersession in a subsequent metadata-only commit K2
-> re-prove K1 object identity and branch lineage are unchanged
-> only then push
-> terminalize through normal kind-specific Consumption
```

This authorization type is conceptually:

```text
adopt_existing_local_commit
```

K1 is not amended/reset/rebased. If K1/ref/lineage changes while C2 is reviewed, the adoption authorization is invalid and the operation stops/reconciles.

Repeated hook/filter transformation loops are subject to existing recurrence/instability rules; another local patch is not assumed safe indefinitely.

## 10. Evidence completeness requires a proof basis

`dependency_complete` is not a self-declared boolean.

Each Evidence adapter records a `completeness_basis` sufficient to justify cross-Candidate reuse.

Recognized conceptual bases include:

```text
hermetic sandbox
  undeclared filesystem/env/network access is mechanically denied

observed dependency trace
  material reads/imports/subprocess inputs are traced and identity-bound under a defined coverage guarantee

closed build graph
  the toolchain itself provides a closed-world dependency graph with stable identities
```

If the adapter cannot provide a defensible completeness basis — for example because of unrestricted dynamic import, reflection, arbitrary shell, opaque compiler plugins, network, DB access, or untracked runtime file reads — then:

```text
completeness = unknown
```

and Evidence cannot be reused across Candidate generations.

Correctness wins over optimization; full rerun is acceptable when completeness cannot be proven.

## 11. Review generation / operation mutation cross-layer consistency

Candidate 6 keeps progression authority with the operation owner while preventing stale Review authorization from being replayed after Review obligations change.

Any mutation checkpoint that has crossed a Review gate binds at least:

```text
review_run_id
review_generation
candidate_hash
review_context_hash
effective_policy_hash
authorization/receipt_id
obligation_digest
proof_phase
```

Before recording push or terminal/registration consumption, the operation owner rechecks:

```text
mutation-bound Review generation / authorization
==
latest durable valid Review generation / authorization for this operation target
```

If a supported HIGH/MID, Candidate invalidation, context change, policy invalidation, or equivalent fact creates a newer Review generation, the old checkpoint is no longer terminal authorization.

Result:

```text
mismatch
-> resume Review / repair as required
or
-> reconcile required if consistency cannot be proven
```

Review Run phase never directly advances lifecycle. The operation owner merely refuses to consume stale authorization.

### 11.1 Async/shadow terminal cutoff

A mechanical cutoff is required.

```text
mandatory/shadow task accepted before cutoff
-> result must settle before terminal authorization can be consumed

result first becomes known only after durable terminal cutoff/completion
-> historical escape
-> no retroactive lifecycle rewrite
```

This prevents a crash from preserving an old `CONVERGED` operation checkpoint while a newer durable Review generation contains an unresolved HIGH/MID.

## 12. Policy experiment overlap becomes three-state

Overlap assessment is itself fail-safe:

```text
proven_disjoint
known_overlap
overlap_unresolved
```

Only `proven_disjoint` experiments may observe concurrently.

`known_overlap` and `overlap_unresolved` are serialized, explicitly superseded, or combined into one compound experiment. `overlap_unresolved` does not require HUMAN by itself.

Observation environment identity includes where relevant:

- Global Policy version
- reviewer model/version
- toolchain/runtime version
- measurement contract version
- Project Profile base version

If these change during an observation window, the window is split or attribution requires positive proof that the change is irrelevant. Otherwise the result is inconclusive.

`affected_policy_surface` semantics are interpreted by fixed meta-rules, not weakened by the experiment being measured.

## 13. Integration, LOW, causality, and global independence retained

Candidate 5 repairs that survived external review remain in force:

- Integration verification forbids undeclared persistent Project/external/nested side effects and requires disposable/isolated resources where writes are needed.
- Deferred Review LOW uses one Project-wide chain, strict first-nonterminal head eligibility, and fail-closed structural validation for cycle/multi-head/missing-member corruption.
- Durable causal material supports `supported / unresolved / insufficient_evidence`; only supported strong causality is counted as C.
- Global evidence-source relationship remains `proven_independent / known_correlated / independence_unresolved`; only proven-independent sources count separately.

## 14. Seven-phase implementation Roadmap — Candidate 6

### P1 — Review Core + Authority + Runtime + common authorization core + projection semantics

Desired state: Review semantics/recovery exist without changing domain lifecycle; common authorization is defined without Work-shaped assumptions; reviewed artifacts and operation metadata have separate exact identities.

Works:

- canonical Review Skill / registry routing / Review Constitution
- Review domain model
- Candidate / Context / Effective Policy identities
- Git-safe vs Review-safe base compatibility contract
- ReviewedArtifactProjection model
- OperationMetadataProjection model
- exact metadata namespace/path/content identity rules
- common immutable Authorization Receipt core
- common immutable Consumption core + kind-specific binding interface
- Review generation / obligation digest model
- Reviewer Executor Protocol/adapters
- Coverage + Adjudication
- runtime Review storage/recovery compatibility
- Project durable Review layout prerequisites
- synthetic cross-layer consistency/recovery tests

P1 does not activate terminal Work review gating.

### P2 — Planning Review Gates + kind-specific planning consumption

Desired state: RoadmapPlan and PhaseEntryDesign are reviewed before existing registration/mutation and their authorization is consumed using planning-native persisted identities.

Works:

- RoadmapPlan Candidate adapter / Roadmap Review / repair continuation
- Roadmap request identity -> create-roadmap authorization/consumption binding
- PhaseEntryDesign Candidate adapter / Phase Design Review / repair continuation
- design identity -> phase-entry authorization/consumption binding
- created entity/relation/registration commit proof
- crash/resume/idempotency tests without fake lifecycle events

### P3 — START Review Gate + base validity + three-part commit proof + atomic terminal consumption

Desired state: a review-v1 Work cannot terminally complete unless the verified semantic base is still valid, committed artifact/metadata/scope match authorization, and terminal event + Consumption are durably paired.

Works:

- review-v1 vs legacy contract identity
- Candidate Builder with base-lineage semantics
- HEAD advancement Review-validity proof or new Candidate generation
- isolated Candidate verification
- Attestation checkpoint
- ReviewedArtifactProjection proof
- OperationMetadataProjection proof
- complete commit-delta scope proof
- no-push-before-proof
- Authorization Receipt persistence
- Class A/B/C mismatch handling
- `adopt_existing_local_commit`
- terminal event ID reservation
- atomic event + Consumption mutation stage
- cardinality/replay/reconcile invariants
- Review generation vs pending mutation consistency checks
- async/shadow terminal cutoff
- interruption tests at every boundary

### P4 — Repair Loop + same-run recurrence + completeness-basis Evidence reuse + isolated Integration

Desired state: repair/reverification remain safe even with dynamic dependencies; reuse is allowed only from a defensible completeness proof; Integration cannot persist undeclared side effects.

Works:

- ReviewRepairRequest / executor repair purpose
- Repair Batch / Coverage Check
- Candidate generations
- Evidence adapter `completeness_basis`
- hermetic/trace/closed-graph completeness implementations where available
- conservative invalidation for unknown completeness
- same-run A/B/C / instability strategy change
- Integration side-effect contract / disposable adapters
- normal fix Work + reintegration

### P5 — Full Durable History + causality + strict LOW validation

Desired state: clone/runtime-cleanup-safe history supports recurrence/causality/LOW provenance without becoming lifecycle truth.

Works:

- full durable Review history
- Run/Finding/Repair summaries
- durable causal material
- cross-run recurrence
- LOW provenance/workization
- structural chain validator
- strict queue-head eligibility
- reconcile behavior for corrupted queue structures

### P6 — Project-local Adaptive Policy + kind-specific persisted-policy proof + three-state experiment overlap

Desired state: Project policy evolution is recoverable, exactly persisted as reviewed, and experimentally attributable.

Works:

- Policy Change Candidate/meta-review
- Project Policy Change operation owner/recovery/Git contract
- Project policy Authorization/Consumption binding
- exact persisted profile projection proof
- no-push-before-proof
- Relevant Opportunity / learning metrics
- shadow/holdout escalation
- `proven_disjoint / known_overlap / overlap_unresolved`
- observation environment identity
- compound experiment / supersession / rollback unit
- retain / adjust / rollback

### P7 — Global Promotion + root-policy persisted proof + evidence independence

Desired state: Global policy changes only from sufficiently supported independent evidence and the exact reviewed root policy artifact is what is committed/pushed.

Works:

- Global policy storage/versioning
- Promotion Packet provenance/correlation clustering
- proven-independent / correlated / unresolved evidence relationship
- Global Policy Change Review
- Workline-root maintenance operation
- Global policy Authorization/Consumption binding
- exact root policy projection and scope proof
- no-push-before-proof
- root commit identity/recovery
- Project adoption at next Review Run boundary
- Global observation / retain / rollback

## 15. Candidate 6 acceptance targets for the next independent review

The next review should attempt to break at least these invariants:

```text
1. A path-nonconflicting HEAD advance cannot silently invalidate Review/Evidence semantics.
2. candidate_hash cannot depend on Receipt/metadata that itself embeds candidate_hash.
3. Wrong OperationMetadata content cannot pass merely because its path is allowed.
4. A review-v1 terminal Work cannot be durably completed without the matching immutable Consumption binding.
5. Authorization/Consumption cardinality cannot fork under retry/resume.
6. An existing unpushed Class-A commit can be adopted without amend/reset/history rewrite and without reusing stale authorization.
7. Evidence dependency completeness cannot be claimed without a concrete proof basis.
8. New Review obligations/generation cannot leave an old pending mutation authorized to push/terminalize.
9. Planning Review is not forced into Work-only terminal-event semantics.
10. Project/Global Policy Change cannot persist/push a policy artifact different from the reviewed Candidate.
11. Policy experiments cannot run concurrently unless non-overlap is positively proven.
```

Current status:

```text
Candidate 5 external review verdict: REPAIR
C5-01..C5-08: ACCEPTED
HUMAN decisions: 0
Candidate 6: CREATED
Implementation: NOT STARTED
Candidate 6 independent re-review: NOT YET RUN
```
