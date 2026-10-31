# Review System Implementation Roadmap Checkpoint — Candidate 5

Status: DESIGN REPAIRED AFTER THIRD EXTERNAL REVIEW / IMPLEMENTATION NOT STARTED

This file is a design checkpoint, not normative authority. Runtime authority remains `registry.md` plus registry-routed canonical Skills. It supersedes `REVIEW_SYSTEM_IMPLEMENTATION_ROADMAP_CHECKPOINT_CANDIDATE4.md` as the latest implementation-roadmap design checkpoint while preserving Candidate 4 and earlier checkpoints as history.

Candidate 4 received an independent review with verdict `REPAIR`. All seven Findings (C4-01 through C4-07) are accepted. Candidate 5 below incorporates the adjudicated repairs without changing the central architecture: Review remains a quality gate and does not become a second lifecycle/progression controller.

## 1. Candidate 4 external review adjudication

| ID | Category | Severity | Adjudication | Candidate 5 repair |
| --- | --- | --- | --- | --- |
| C4-01 | Problem | HIGH | ACCEPT | Post-commit proof now verifies both authorized entry equality and complete commit-delta scope equality |
| C4-02 | Problem | MID | ACCEPT | Immutable Authorization Receipt and immutable Consumption Record are split into separate append-only records |
| C4-03 | Problem | HIGH | ACCEPT | Post-commit mismatch recovery is classified canonically; no push before proof; unexpected/non-owned commit content forces reconcile |
| C4-04 | Problem | MID | ACCEPT | Evidence reuse becomes positive-proof only; unknown dependency completeness forces conservative invalidation |
| C4-05 | Problem | HIGH | ACCEPT | Integration verification-only now covers persistent external/nested side effects via an explicit side-effect contract |
| C4-06 | Problem | MID | ACCEPT | Deferred LOW chain gains fail-closed structural integrity validation before head selection |
| C4-07 | Problem | MID | ACCEPT | Policy experiments gain overlap/attribution rules and rollback units by affected policy surface |

No Candidate 4 Finding requires a HUMAN decision. The external verdict `REPAIR` is accepted.

## 2. Core architecture retained

Review remains a gate around existing operation owners.

```text
Roadmap / START / existing progression
  -> registration, execution, mutation ownership, Git finalization, lifecycle, completion

Review System
  -> freeze Candidate / Context / Policy
  -> discover and adjudicate Findings
  -> require Repair / HUMAN / reverification
  -> emit authorization only when obligations are zero
```

No Review lifecycle field is added to `state.py`. Canonical events/entities/relations remain lifecycle truth. Review durable records are authorization/provenance evidence, not a second lifecycle ledger.

## 3. Candidate identity — base lineage + owned projection

Candidate 5 resolves the ambiguity between whole-repository tree identity and Work-owned artifact identity.

A Work Candidate is defined by:

```text
base lineage identity
+ authorized Work-owned projection
+ Git-persist-equivalent semantics for that projection
```

The projection includes the exact entry set the operation is allowed to persist, with relevant Git semantics:

- repository-relative path
- blob identity/content after applicable Git clean/filter normalization
- file mode / executable bit
- deletion
- symlink blob semantics
- gitlink/submodule entry identity
- case-collision rules where relevant
- relevant attributes/filter configuration identity where it can change persisted objects

Independent HEAD advancement outside the operation-owned projection is not automatically a Candidate mismatch if existing mutation/Git authority can prove it is compatible. The Candidate therefore does not require unrelated repository entries to remain byte-identical forever.

## 4. Commit proof — two independent invariants

After the operation creates its local commit and before push or terminal lifecycle finalization, prove both:

### 4.1 Authorized projection equality

```text
Every expected Work-owned / explicitly expected Workline-owned entry
in the actual commit
=
the Attested Candidate entry with the same Git semantics
```

### 4.2 Complete commit-delta scope equality

Compute the actual diff from the commit's actual parent to the actual commit tree.

```text
actual changed-entry set
=
authorized Work-owned delta
+ explicitly expected Workline-owned metadata/authorization entries
```

No extra changed path is allowed merely because all expected paths match.

This closes hook/index cases that inject an unreviewed path into the commit.

### 4.3 Push gate

```text
post-commit Candidate proof not complete
-> push forbidden
-> terminalization forbidden
```

Only after both proofs pass may the owning operation continue to push/final lifecycle work under existing Git safety rules.

## 5. Canonical post-commit mismatch recovery

If the commit already exists locally but does not match the Attested Candidate, classify the mismatch.

### Class A — transformed but still entirely operation-owned

Conditions:

- actual commit delta contains only entries the operation owns/was explicitly allowed to write;
- mismatch is caused by Git semantics/hook/filter transformation or equivalent operation-owned transformation;
- commit/ref lineage remains provable.

Then:

```text
local commit K1
-> freeze K1's owned projection as new Candidate C2
-> no push
-> acquire/reacquire candidate-bound Evidence
-> impacted Review
-> if accepted, create new authorization/consumption records and continue
-> if rejected, create only operation-owned corrective work/commit under the existing mutation owner
```

Do not pretend K1 was reviewed under the old Attestation.

### Class B — unexpected/non-owned commit entry

If the commit contains any changed entry not owned/authorized by the operation:

```text
reconcile required
no automatic repair
no push
no terminalization
```

The operation must not silently revert or claim ownership of the unexpected entry.

### Class C — ref/lineage cannot be proven

If branch/ref identity or mutation commit lineage cannot be proven:

```text
reconcile required
```

Candidate 5 does not use reset, amend, rebase, force push, or hidden history rewrite as automatic recovery.

## 6. Authorization Receipt and Consumption Record are separate immutable facts

Candidate 5 removes mutable consumption status from the Receipt itself.

### 6.1 Authorization Receipt

Immutable / append-only concept:

```yaml
receipt_id: ...
review_run_id: ...
review_kind: ...
target: ...
operation_contract: review-v1
authorized_candidate_hash: ...
review_context_hash: ...
effective_policy_hash: ...
coverage_hash: ...
adjudication_hash: ...
unresolved_obligations: 0
authorized_transition:
  type: ...
  operation_id: ...
  stage_id: ...
```

### 6.2 Consumption Record

Separate immutable / append-only fact:

```yaml
consumption_id: ...
receipt_id: ...
operation_id: ...
commit_sha: ...
terminal_event_id: ...
```

Receipt existence does not mean Work completion. Consumption Record existence does not replace lifecycle truth. Canonical lifecycle completion remains derived from existing events/state.

Supersession is represented by a new immutable supersession/successor fact, not by editing an old Receipt.

## 7. Receipt / Git / lifecycle ordering

Target Work completion sequence:

```text
Review CONVERGED
-> Attestation
-> completion precheck
-> final pre-persistence Candidate proof
-> immutable Authorization Receipt staged by the owning operation
-> local authorized Git commit
-> post-commit authorized-projection proof
-> post-commit complete-delta-scope proof
-> if mismatch: Class A/B/C recovery; no push
-> if match: existing push policy may proceed
-> terminal lifecycle finalization
-> immutable Consumption Record bound to receipt + commit + terminal event under the same recovery contract
```

Implementation must make every interruption resumable without treating Review records as lifecycle truth.

## 8. Isolated Evidence retained; reuse becomes positive-proof only

Final Evidence remains acquired against a frozen Candidate in an isolated verification workspace whenever technically possible.

Candidate 5 strengthens Evidence reuse:

```text
Evidence reuse across Candidate generations is allowed
iff
all material dependencies represented by that Evidence adapter
are positively proven unchanged.
```

The rule is not:

```text
no dependency change was noticed -> reuse
```

If dependency completeness is unknown, reuse across Candidate generations is forbidden.

Conservative invalidation applies when the adapter cannot prove unchanged identity for relevant inputs such as:

- test helper
- fixture
- generated artifact
- schema/config
- toolchain/runtime
- transitive dependency
- lock/dependency state
- Review Context
- Effective Policy rules that affect the verification
- external service/version where material
- cache/input provenance where material

Semantic-impact analysis may narrow rerun scope only where dependency identity proves the narrowing safe. It is an optimization, not the correctness proof itself.

## 9. Mechanically verification-only Phase Integration includes external side effects

Candidate 5 defines:

```text
verification-only
=
no persistent mutation to Project domain state
AND
no persistent mutation to undeclared external/nested state
```

Integration Evidence adapters declare a side-effect contract.

Preferred execution uses disposable/isolated resources, for example:

- read-only/frozen Candidate filesystem
- disposable DB/schema
- temp build directory
- isolated container/worktree
- disposable service fixture
- explicitly allowed Review runtime/evidence output area

Persistent external state may not be mutated by a final-PASS verifier unless isolation/rollback/disposability is mechanically guaranteed by the adapter contract.

Nested repositories/submodules are treated explicitly: gitlink identity in the Candidate does not authorize mutation of the nested working tree.

If the verifier performs unauthorized Project/external mutation, Integration cannot PASS. A required domain repair remains a normal fix Work followed by normal Work Formal Review and reintegration.

## 10. Deferred Review LOW queue — fail-closed structural integrity

Review LOW Works remain phase-less standalone Works in one Project-wide logical chain. `planned_next` may record order/provenance but is not itself treated as strict queue enforcement.

Before existing progression ownership considers LOW maintenance, run a read-only structural validation of the Review LOW chain/provenance.

Required invariants include:

```text
exactly one head for the active queue
no cycle
each Review LOW member appears exactly once
no duplicate predecessor
no duplicate successor
provenance membership is consistent with the relation projection
terminal members are handled consistently
```

Result:

```text
valid linear chain
-> resolve first nonterminal member
-> apply strict head eligibility

broken / cyclic / multiple-head / missing-member / contradictory provenance
-> reconcile required
```

Invalid queue structure is never interpreted as idle and never permits skipping to an arbitrary startable LOW Work.

Queue mutation/repair, when required, occurs under an existing canonical Project mutation owner + execution lock, not inside Review and not through a new scheduler.

## 11. Durable causality model retained

Candidate 4's causality repair is retained as resolved.

Durable causal material includes at least:

- source/result Candidate hashes
- full Work-owned touched delta before/after
- impact-analysis affected surfaces
- generated artifacts needed for causal re-evaluation where practical
- external-state Evidence/fingerprints where reconstructible
- supporting Evidence refs

Causality state supports:

```text
supported
unresolved
insufficient_evidence
```

Only supported strong causality becomes finalized C for learning/counting.

## 12. Project-local Policy Change experiments — overlap and attribution

Each Policy Change Candidate/experiment identifies:

```text
affected_policy_surface
measurement_contract
observation_window
base Project Profile version
relevant Global Policy version
environment/dependency identity needed for attribution
rollback unit
```

Observation concurrency rule:

```text
non-overlapping affected_policy_surface
-> concurrent observation allowed

overlapping affected_policy_surface
-> next change waits until prior experiment is retained, rolled back, or explicitly superseded
```

If multiple coupled changes are intentionally tested together, they are one compound Policy Change Candidate and share one measurement/rollback unit.

An overlapping experiment is not silently stacked on top of another and later attributed independently.

Rollback creates a new version; history is never rewritten.

Shadow/holdout semantics from Candidate 4 remain:

- not selected -> no direct completion effect
- executed/no Finding -> measurement only
- executed pre-terminal/supported LOW -> normal LOW handling
- executed pre-terminal/supported HIGH/MID -> normal Review obligation, completion blocked
- first known after terminal completion -> historical escape, no retroactive lifecycle rewrite, trigger fix/guard/rollback evaluation

## 13. Global evidence independence retained

Candidate 4's three-state relationship remains:

```text
proven_independent
known_correlated
independence_unresolved
```

Only proven-independent sources count independently toward promotion thresholds. Unresolved evidence is neither silently counted as independent nor automatically escalated to HUMAN.

## 14. Seven-phase implementation Roadmap — Candidate 5

### P1 — Review Core + Authority + Runtime + immutable authorization foundation + Git Candidate semantics

Desired state: Review semantics and recovery primitives exist without changing domain lifecycle; Candidate identity is Git-persist-equivalent; authorization facts are immutable.

Works:

- canonical Review Skill / registry routing / Review Constitution
- Review domain model
- Candidate / Context / Effective Policy identities
- base-lineage + owned-projection Candidate identity
- Git entry/filter/mode/symlink/gitlink contract
- Reviewer Executor Protocol/adapters
- Coverage + Adjudication
- runtime Review storage/recovery compatibility
- immutable Authorization Receipt model
- immutable Consumption Record model
- Project durable Review layout/init/residue/recovery prerequisites
- synthetic recovery/invariant tests

P1 does not activate terminal Work review gating.

### P2 — Planning Review Gates

Desired state: RoadmapPlan and PhaseEntryDesign are reviewed before existing mutation/registration, with immutable authorization/consumption evidence bound to the consuming operation.

Works:

- RoadmapPlan Candidate adapter / Roadmap Review / repair continuation
- READY -> existing Roadmap mutation
- PhaseEntryDesign Candidate adapter / Phase Design Review / repair continuation
- READY -> existing Phase entry/registration
- planning Authorization Receipt / Consumption Record recovery tests

### P3 — START Review Gate + isolated Evidence + full commit-delta proof + mismatch recovery

Desired state: a review-v1 Work cannot terminally complete unless actual committed content and scope exactly match authorization and any mismatch is handled fail-closed.

Works:

- review-v1 vs legacy contract identity
- persist-equivalent Candidate Builder
- Ambient Workspace separation
- isolated Candidate verification workspace
- declared Evidence dependency contract
- positive-proof Evidence identity support
- Pre-Review / Work Formal Review
- Attestation checkpoint
- pre-persistence proof
- Authorization Receipt staging
- local result commit
- authorized projection equality
- complete commit-delta scope equality
- no-push-before-proof
- Class A/B/C post-commit mismatch recovery
- terminal finalization
- Consumption Record binding
- interruption/recovery tests for every boundary

### P4 — Repair Loop + same-run recurrence + positive-proof reuse + external-side-effect-safe Integration

Desired state: HIGH/MID repair stays in the current Review cycle where appropriate, while selective reverification cannot reuse unproven Evidence and Integration cannot persist undeclared side effects.

Works:

- ReviewRepairRequest / executor repair purpose
- Repair Batch / Coverage Check
- Candidate generations
- positive-proof Evidence reuse/invalidation
- same-run A/B/C and strategy-change trigger
- Integration side-effect contract
- disposable DB/service/build/container adapters where needed
- nested repo/submodule side-effect checks
- normal fix Work + reintegration flow

### P5 — Full Durable Review History + causality + strict LOW structural validation

Desired state: clone/runtime-cleanup-safe history supports recurrence/causality/LOW provenance without becoming lifecycle truth, and LOW maintenance fails closed on queue corruption.

Works:

- full `.workline/review/` durable history
- Run/Finding/Repair summaries
- durable causal material
- cross-run recurrence
- LOW provenance/workization
- one Project-wide Review LOW chain
- structural chain validator
- strict first-nonterminal head eligibility
- reconcile behavior for cycle/multi-head/missing-member corruption
- coexistence tests with unrelated standalone Works

### P6 — Project-local Adaptive Policy + Policy Change operation + overlap-aware experiments

Desired state: Project learning can strengthen/lighten verification without changing correctness semantics, hiding known defects, or destroying experiment attribution.

Works:

- Relevant Opportunity / Learning metrics
- Policy Change Candidate/meta-review
- Project Policy Change operation owner/recovery/Git contract
- Profile versioning
- strengthening / Temporary Guards
- frozen measurement contract
- shadow/holdout escalation semantics
- affected-policy-surface identity
- overlap detection
- concurrent non-overlap observation
- wait/supersede rules for overlap
- compound experiment rollback unit
- retain / adjust / rollback

### P7 — Global Promotion + Workline-root Policy Change + evidence independence

Desired state: Global Adaptive Policy changes only from sufficiently supported generalized evidence through a recoverable root maintenance operation.

Works:

- Global policy storage/versioning
- Promotion Packet provenance
- correlation clustering
- proven-independent / correlated / unresolved evidence relationship
- Global Policy Change Review
- Workline-root maintenance operation
- single-writer/base-version/conflict/recovery behavior
- Git + Patch Notes
- Project adoption at next Review Run boundary
- Global observation / retain / rollback

## 15. Candidate 5 acceptance targets for the next independent review

The next review should specifically try to break these repaired invariants:

```text
1. Actual commit delta cannot contain an unreviewed extra entry while authorized entries still match.
2. Post-commit mismatch cannot be auto-hidden by reset/amend/rebase/force-push semantics.
3. Unexpected/non-owned committed content cannot be auto-repaired or pushed.
4. Authorization Receipt remains immutable; consumption/supersession are separate immutable facts.
5. Evidence cannot be reused across Candidate generations unless material dependencies are positively proven unchanged.
6. Integration verification cannot persist undeclared Project, nested-repo, DB, service, cache, or other external side effects.
7. Broken/cyclic/multiple-head LOW queue structure fails closed to reconcile-required rather than being treated as idle.
8. Overlapping Policy Change experiments cannot silently contaminate each other's attribution/rollback windows.
```

Current status:

```text
Candidate 4 external review verdict: REPAIR
C4-01..C4-07: ACCEPTED
HUMAN decisions: 0
Candidate 5: CREATED
Implementation: NOT STARTED
Candidate 5 independent re-review: NOT YET RUN
```
