# Review System Implementation Roadmap Checkpoint — Candidate 3

Status: DESIGN REPAIRED AFTER EXTERNAL REVIEW / IMPLEMENTATION NOT STARTED

This file is a design checkpoint, not normative authority. Runtime authority remains `registry.md` plus registry-routed canonical Skills. It supersedes `REVIEW_SYSTEM_IMPLEMENTATION_ROADMAP_CHECKPOINT.md` as the latest implementation-roadmap design checkpoint, while preserving the earlier checkpoint as history.

Candidate 2 received an independent external review with verdict `REPAIR`. All ten reported Findings (ER-01 through ER-10) were adjudicated as accepted. Candidate 3 below incorporates their required repairs without changing the central architecture: Review remains a quality gate and does not become a second lifecycle/progression controller.

## 1. External review adjudication

| ID | Category | Severity | Adjudication | Candidate 3 repair |
| --- | --- | --- | --- | --- |
| ER-01 | Problem | HIGH | ACCEPT | Minimum durable Review Receipt moves before Review-aware completion activation |
| ER-02 | Problem | HIGH | ACCEPT | Work Candidate becomes persist-equivalent; pre-existing dirty becomes Ambient Workspace Context |
| ER-03 | Problem | HIGH | ACCEPT | Evidence, Attestation, and final Git content are bound to the same immutable Candidate |
| ER-04 | Problem | HIGH | ACCEPT | Candidate Builder gets canonical path/object/symlink/external-artifact contract |
| ER-05 | Problem | HIGH | ACCEPT | `phase_integration_check` becomes verification-only; domain repair occurs in normal fix Work |
| ER-06 | Problem | MID | ACCEPT | Deferred Review LOW Works form one Project-wide queue/chain, not per-review independent chains |
| ER-07 | Problem | MID | ACCEPT | Durable causality snapshots preserve repair-relevant before/after material for B/C audit |
| ER-08 | Problem | HIGH | ACCEPT | Project Policy Change and Global Policy Change receive explicit operation ownership/recovery contracts |
| ER-09 | Improvement | MID | ACCEPT | Lightening requires frozen independent measurement via shadow/holdout verification |
| ER-10 | Problem | MID | ACCEPT | Global promotion counts independent evidence sources, not raw Project count |

No external Finding requires a HUMAN decision. The external verdict `REPAIR` is accepted.

## 2. Repair grouping

The ten external Findings collapse into five repair batches.

### Batch A — authorization durability and Candidate identity

Covers ER-01, ER-02, ER-03, ER-04, ER-07.

The repaired invariant is:

```text
Reviewed Candidate
= Verified Candidate
= Attested Candidate
= Persisted Candidate
```

A Work may not terminally complete if those identities cannot be proven equal.

### Batch B — Phase Integration responsibility

Covers ER-05.

`phase_integration_check` is verification/evidence-only. It does not own domain artifact repair. If integration discovers a defect requiring mutation, START/CREATE create/execute a normal fix Work, that Work receives normal Work Formal Review, and integration is run again.

### Batch C — Deferred LOW selection

Covers ER-06.

All Review-origin deferred LOW Works in one Project belong to one Project-wide ordered `planned_next` chain. Review does not become scheduler/selector. Existing progression ownership chooses the unique queue head only at a legitimate idle boundary.

### Batch D — Policy Change operation ownership

Covers ER-08.

Project-local policy writes and Workline-root Global policy writes are explicit state-changing operations with their own owner/recovery contract. Review only evaluates Policy Change Candidates and emits authorization; it does not physically own policy mutation or Git finalization.

### Batch E — learning measurement quality

Covers ER-09 and ER-10.

Lightening cannot remove its own measurement channel, and Global promotion counts independent causal evidence rather than nominal Project count.

## 3. Core architecture retained

Review System remains a quality gate around existing lifecycle boundaries.

```text
Roadmap / START / state.py
  -> progression, registration, lifecycle, completion, generated state

Review System
  -> determine whether a frozen Candidate satisfies the current requirement/context under a frozen Effective Policy
```

Review does not add `review_passed`, `review_status`, or another lifecycle state to `state.py`. Existing events/entities/relations remain lifecycle truth.

Primary review kinds remain:

1. Roadmap Review
2. Phase Design Review
3. Work Formal Review
4. Phase Integration Check

Policy Change Review remains a separate meta-review kind/operation, not ordinary Work Review Repair.

## 4. Candidate / Context / Policy / Evidence — Candidate 3 model

Keep these distinct:

```text
Candidate          = exact artifact/state that Review may authorize for persistence/progression
Review Context     = what defines correctness for this Review
Effective Policy   = how this Review must verify correctness
Evidence           = verification result explicitly bound to a Candidate/context where required
Ambient Context    = non-owned workspace/environment facts visible during execution but not part of persisted Work result
```

Each Review Run freezes at least:

```text
candidate_hash
review_context_hash
effective_policy_hash
```

### 4.1 Persist-equivalent Work Candidate

Candidate 2 used:

```text
Base HEAD + Baseline Overlay + Work-owned Delta
```

Candidate 3 replaces this with:

```text
Persisted Candidate
= Base HEAD
+ effective Work-owned Delta
- Work-owned deletions
```

Pre-existing tracked dirty state is not part of the Persisted Candidate merely because it is present in the working tree.

Instead:

```text
Ambient Workspace Context
= pre-existing tracked dirty content
+ other explicitly relevant non-owned local state
```

The reviewer may be informed that ambient state exists, but Review authorization cannot depend on ambient bytes that START will not persist.

If verification/review discovers that the Work result is semantically dependent on an Ambient Workspace change, Attestation is blocked until that dependency is formalized by an appropriate owning operation/commit. START must not steal ownership of another change to make Review pass.

### 4.2 Candidate generations

Repair never mutates a reviewed Candidate in place.

```text
C1 -> Repair R1 -> C2 -> Repair R2 -> C3
```

Each generation has its own identity/hash. Selective evidence/review reuse is allowed only where unchanged assumptions and candidate-bound evidence prove reuse safe.

### 4.3 Candidate filesystem/object contract

Before Candidate Builder reads/hashes an artifact, paths and object semantics must be canonical and safe.

Minimum contract:

```text
- Project-relative normalized paths only
- reject absolute paths
- reject drive-qualified paths
- reject `.` / `..` escape forms
- path resolution may not escape Project root
- object type determined without blindly dereferencing links
- symlink identity follows Git-persisted semantics, not target-file bytes
- directory traversal does not follow symlink/junction/reparse escape outside Project
- arbitrary external artifact bytes are not imported as Candidate files
```

Project-external artifacts are modeled as explicit Review Context/Evidence with their own identity/fingerprint and provenance.

This contract must be validated before Candidate freeze, not only later by mutation/Git code.

## 5. Candidate-bound Evidence and final persistence invariant

Candidate 2 allowed Pre-Review evidence generation before Candidate freeze. Candidate 3 changes the ordering.

Normal Work flow becomes:

```text
execution result
-> Review Entry Safety
-> freeze immutable Candidate Cn
-> acquire/reacquire candidate-bound verification Evidence
-> Repair Coverage Check
-> Pre-Review Quality Pass / Evidence map
-> Formal Review
```

Evidence used for Attestation must identify the Candidate it verifies. At minimum, candidate-sensitive Evidence records `candidate_hash`; where environment/context materially affects the result, it also records the required environment/context fingerprint.

Evidence produced before Candidate freeze may remain diagnostic input, but it cannot independently satisfy final Review obligations unless it is revalidated against the frozen Candidate.

### 5.1 Pre-persistence reproof

After CONVERGED and before Git persistence/final terminalization, START must re-prove that the exact Work-owned additions/modifications/deletions to be persisted equal the Attested Candidate.

```text
Attested Candidate Cn
-> existing completion precheck
-> final owned-tree equality proof
   match    -> Git persistence may proceed
   mismatch -> freeze Cn+1 -> impacted verification/review
```

This is required on uninterrupted normal execution as well as crash/resume paths.

Project execution lock serializes Workline operations; it is not a filesystem security sandbox. External/local processes may still mutate files, so final equality cannot be assumed from lock ownership alone.

## 6. Minimum Durable Review Receipt

A Review-aware completion gate may not activate before there is a compact durable authorization record whose lifetime exceeds runtime mutation cleanup.

Full Review History remains a later capability, but a Minimum Durable Review Receipt is introduced with the first gated operation.

Conceptual minimum:

```yaml
review_run_id: ...
review_kind: work_formal | roadmap | phase_design | phase_integration
target: ...
candidate_hash: ...
review_context_hash: ...
effective_policy_hash: ...
coverage_hash: ...
final_adjudication_hash: ...
unresolved_obligations: 0
verdict: CONVERGED | READY | PASS
```

Properties:

- durable and Git-managed
- non-lifecycle history; never an input to `state.py`
- written by the owning domain operation as part of the same durable operation that consumes the authorization
- cannot be represented only by `.workline/runtime/` or a pending mutation record that may later be deleted
- enough to prove after clone/runtime cleanup which fixed Candidate/context/policy authorized the gated transition

Full Finding/Repair/learning history is still introduced later.

## 7. Reviewer / Coverage / Adjudication model retained

Discovery remains fresh; adjudication remains history-aware.

Reviewer receives the frozen Candidate, current requirement/spec/desired state, candidate-bound Evidence, assigned viewpoint, and Effective Policy. Normally it does not receive prior Findings/Repair history or other reviewer Findings.

Coverage records continue to distinguish:

```text
zero Findings because Candidate is good
!=
zero Findings because relevant surface was not inspected
```

A reviewer failure is not a zero-Finding result. Mandatory viewpoints cannot silently disappear because the executor failed or policy adapted.

Adjudication still owns:

- supported vs unsupported claim
- Problem / Improvement
- HIGH / MID / LOW
- duplicate merge
- HUMAN
- A/B/C classification
- repair obligation identity

## 8. Finding / Repair / recurrence retained and strengthened

Definitions remain:

- A: newly discovered issue; may have existed before
- B: substantially same previously repaired issue reappears
- C: prior Repair caused a genuinely new issue absent before

C requires strong causality, not mere temporal ordering.

Repair instability remains:

```text
Two supported repair failures in the same semantic surface
-> stop assuming another local patch is correct
-> strategy change
```

### 8.1 Durable causality snapshots

Candidate hashes alone are insufficient to audit B/C later if intermediate Candidates were never Git commits.

For a B/C judgment that depends on an intermediate Candidate/Repair transition, durable history preserves the minimum repair-relevant material required to re-evaluate causality.

Conceptually:

```text
source_candidate_hash
repair_id
result_candidate_hash
repair_relevant_surfaces:
  - path / logical surface
  - before content-addressed ref/hash
  - after content-addressed ref/hash
  - supporting evidence refs
causality_claim
causality_confidence
```

This is a causality snapshot, not a permanent full Candidate Tree archive.

Goal:

```text
Candidate hash
-> reconstructible relevant before/after material
-> Repair
-> next Candidate hash
```

Full runtime Candidate materialization may still be deleted after recovery is no longer needed.

## 9. Work Formal Review lifecycle — Candidate 3

```text
START
-> Work execution
-> Completed-like reviewable result
-> Review Entry Safety
-> freeze Candidate C1
-> candidate-bound verification Evidence
-> Repair Coverage Check
-> Pre-Review Quality Pass
-> Work Formal Review
-> Adjudication
   HIGH/MID -> ReviewRepairRequest -> same domain executor -> Candidate C2 -> impacted verification/review
   LOW      -> repair now or deferred LOW Work
   HUMAN    -> wait only where repair truly depends on HUMAN
   obligations=0 -> CONVERGED
-> Review Attestation
-> owning START mutation records Attestation checkpoint
-> Minimum Durable Review Receipt prepared/persisted under owning operation
-> existing completion precheck
-> final Attested Candidate == to-be-persisted owned tree proof
   mismatch -> Candidate next generation and re-review
   match    -> Git persistence
-> terminal finalization / work_completed
```

`Completed` from the executor remains a reviewable implementation result, not immediate terminal completion.

Review states what must become true. START/domain executor changes the workspace. Review verifies whether it became true.

## 10. Phase Integration Check — verification-only

Candidate 2 allowed a special integration Work to mutate domain artifacts while receiving only a lightweight integration review. Candidate 3 closes that bypass.

Canonical design direction:

```text
phase_integration_check
= verification/evidence-only integration Work
```

It may collect/read evidence and determine whether the Phase goal and cross-Work integration hold, but it may not own normal domain result delta whose correctness would otherwise need Work Formal Review.

If integration detects a defect requiring mutation:

```text
Phase Integration Check
-> Finding / required outcome
-> create/execute normal fix Work through existing CREATE/START ownership
-> fix Work receives normal Work Formal Review
-> run/re-run Phase Integration Check
-> PASS
-> integration terminalization
-> Phase completion remains derived by existing state machinery
```

If future design deliberately permits integration Work to own domain delta, that delta must receive normal Work Formal Review in addition to the dedicated Phase Integration Check. Lightweight Integration Check alone is never a bypass for mutable domain output.

## 11. LOW-derived Work — one Project-wide deferred chain

LOW not repaired immediately remains a real standalone Work:

```text
phase_id = None
origin.type = standalone
```

Review provenance is separate from existing birth-origin semantics.

Candidate 3 strengthens ordering:

```text
all Review-origin deferred LOW Works in one Project
-> one Project-wide `planned_next` chain
```

Example:

```text
LOW-1 -> LOW-2 -> LOW-3 -> LOW-4
```

A new deferred LOW appends to the current deferred LOW tail. Do not create unrelated per-Review LOW chains whose heads later become ambiguous.

Existing unrelated standalone Works are not silently merged into the Review LOW queue.

Selection priority remains:

```text
explicit human Work selection
-> currently required/in-flight Work / Review / Repair
-> normal current Roadmap/Phase progression
-> Roadmap achievement
-> deferred Review LOW maintenance
```

`blocked != idle`: ambiguity, HUMAN wait, broken dependency, reconcile-required, or other failed mandatory progression is not a reason to switch to LOW.

Review does not select the queue head. Existing progression ownership may start the unique LOW queue head only after mandatory progression legitimately reaches a no-mandatory-plan/idle boundary. Once selected, the LOW Work behaves as a normal Work and receives normal Review/completion requirements.

## 12. Durable Review History — full model

Minimum Durable Review Receipt arrives before gated completion activation. Full durable Review History still arrives later for recurrence, provenance, and learning.

Conceptual layout remains:

```text
.workline/review/
  receipts/
  profile.yaml
  runs/
  findings/
  repairs/
  causality-snapshots/
  policy-changes/
  evidence-snapshots/
  patch-notes/

.workline/runtime/review/
  runs/
  candidates/
  raw-reports/
  learning/
```

Durable data:

- Minimum Review Receipt
- compact Review Run summary
- Finding summary
- Repair summary
- B/C recurrence history
- repair-relevant causality snapshots
- LOW provenance
- policy-change evidence / observation / patch notes

Runtime data:

- reviewer raw output
- in-progress recovery state
- Candidate materializations
- temporary coverage/adjudication state
- high-volume learning observations not promoted to durable evidence

Durable Review History remains non-lifecycle history and is not read by `state.py` to derive Work/Phase/Roadmap lifecycle state.

## 13. Project-local Policy Change operation

Project-local policy evolution is a distinct Project state-changing operation, not Review Repair and not an extension of START/Roadmap ownership.

Review owns:

```text
PolicyChangeCandidate
-> Policy Change Review
-> policy-change Attestation / required outcomes
```

A canonical Project Policy Change operation owner owns:

```text
Project context check
-> self-hosting / implementation checks as applicable
-> Project execution lock
-> pending policy-change mutation open/resume
-> profile / durable policy evidence writes
-> validation/postcheck
-> Git commit / optional push under existing Git safety rules
-> durable completion/recovery cleanup
```

It reuses Project context, Project execution lock, Mutation Controller, and Git primitives rather than inventing a new generic Controller.

Review never becomes physical mutation owner merely because it approved a policy candidate.

## 14. Project-local learning and lightening measurement

Policy evolution remains:

```text
Review Run
-> Learning observation
-> Evaluation Trigger
-> Policy Change Candidate
-> Policy Change Review under pre-change policy + fixed meta rules
-> Project Policy Change operation
-> new Profile version
-> observing
-> retain / adjust / rollback
```

Strengthening may be proposed after a small number of meaningful independent same-pattern opportunities, subject to evidence quality. Lightening requires materially stronger evidence.

### 14.1 Frozen measurement contract for lightening

A lightening proposal must define before activation:

- Relevant Opportunity denominator
- pre-change check being lightened
- replacement verification
- independent observation channel
- observation window
- success criteria
- rollback threshold

During `observing`, the changed policy cannot weaken its own measurement contract.

At a representative sample of Relevant Opportunities, the old/lightened check runs in shadow/holdout mode or an independently justified detector with equal-or-better escape sensitivity remains active.

Shadow/holdout results need not necessarily gate each production completion, but they are durable evidence for retain/rollback evaluation.

Thus:

```text
observed escape = 0
```

cannot be concluded merely because the policy removed the sensor capable of detecting the escape.

## 15. Global Policy Change operation

Global policy mutation targets the Workline-root repository and is not a Workline Project START operation. Current unsupported self-hosting rules must not be bypassed by pretending the Workline root is an ordinary Project.

A canonical Workline-root maintenance operation must define:

```text
root authorization / implementation identity
single-writer serialization
optimistic base version/hash
pending durable intent
write scope
validation
Git commit
push behavior
crash/resume
conflict / reconcile behavior
```

Review owns Global Policy Change evaluation/authorization; the maintenance operation owns physical Workline-root mutation and Git finalization.

Project mutation and Global mutation remain separate operations/repositories. No two-repository transaction is introduced.

## 16. Global promotion — independent evidence sources

Global promotion is based on generalized mechanism and independent evidence sources, not the raw number of Project IDs.

Promotion evidence records enough provenance to identify correlated evidence, including where applicable:

```text
Project/repository identity
repository/template/fork lineage
relevant base provenance
shared upstream dependency/context
Finding/Review Run refs
generalized failure-pattern identity
root-cause identity
incident identity/correlation
local policy-change + observation evidence
```

Evidence from multiple repositories that are copies/forks/templates affected by the same upstream incident may count as one independent source for promotion purposes.

The promotion gate asks:

```text
How many independent evidence sources support the generalized mechanism?
```

not simply:

```text
How many Projects reported it?
```

Project-specific component names/workarounds are not promoted as Global rules. Global policy remains adaptive data interpreted under normative Review Constitution in `registry.md` + canonical Review Skill.

## 17. Legacy activation compatibility retained

```text
operation_contract = legacy
  -> finish under legacy semantics

operation_contract = review-v1
  -> Review obligations + durable Receipt required

unknown / contradictory
  -> reconcile required
```

Absence of an Attestation or Receipt does not itself prove legacy status. Contract/version must be mechanically established.

Review-v1 completion activation occurs only after the Minimum Durable Review Receipt path is available and recoverable.

## 18. Seven-phase implementation Roadmap — Candidate 3

### P1 — Review Core + Authority + Runtime + Minimum Durable Receipt + Candidate safety

Desired state:

Review semantics and recovery foundation exist without creating a second lifecycle, and any future gated authorization can survive runtime cleanup/clone.

Works:

- canonical Review Skill / registry routing / Review Constitution
- Review domain model
- Candidate / Review Context / Effective Policy identities
- Reviewer Executor Protocol and adapters
- Coverage + Adjudication
- runtime Review storage and recovery compatibility
- Minimum Durable Review Receipt schema/storage contract
- Project layout/init/residue/recovery changes required for Receipt storage
- Candidate filesystem/path/object/symlink/external-artifact contract
- synthetic Review recovery integration

P1 does not yet activate Work terminal Review gating.

### P2 — Planning Review Gates

Desired state:

RoadmapPlan and PhaseEntryDesign are reviewed before canonical registration/mutation.

Works:

- RoadmapPlan Candidate adapter using existing request identity
- Roadmap Review A/B/C viewpoints
- Roadmap repair continuation
- READY -> existing Roadmap mutation gate
- PhaseEntryDesign Candidate adapter using existing design identity
- Phase Design Review viewpoints/closure checks
- Phase design repair continuation
- READY -> existing Phase entry/registration gate
- durable Receipt integration for accepted planning Reviews where the subsequent mutation consumes the authorization

### P3 — START Review Gate + persist-equivalent Candidate + activation compatibility

Desired state:

A review-v1 Work cannot terminally complete unless exact persisted output equals the frozen, verified, attested Candidate.

Works:

- review-v1 vs legacy operation contract/version identity
- legacy pending resume compatibility
- persist-equivalent Work Candidate Builder
- Ambient Workspace Context separation
- Review Entry Safety
- immutable Candidate freeze before final verification
- candidate-bound Evidence contract
- Pre-Review evidence mapping
- Work Formal Review A/B/C/D
- Review Attestation checkpoint in START mutation
- Minimum Durable Review Receipt persistence
- final Attested Candidate == Git-to-be-persisted tree proof
- normal-path and crash/resume recovery tests

### P4 — Repair Loop + same-run recurrence + verification-only Phase Integration

Desired state:

HIGH/MID Review Findings are repaired inside the current Work cycle where appropriate, with new Candidate generations and selective reverification; integration cannot bypass Work Formal Review by mutating domain artifacts under a lightweight gate.

Works:

- ReviewRepairRequest contract
- same domain executor `review_repair` purpose
- Repair Batch model
- Repair Coverage Check
- semantic-impact invalidation
- selective candidate-bound reverification/re-review
- same-run A/B/C
- repeated repair-failure strategy change
- verification-only Phase Integration Check
- normal fix Work + reintegration flow

### P5 — Full Durable Review History + causality + cross-run recurrence + Project-wide LOW queue

Desired state:

Clone/runtime-cleanup-safe history is sufficient to justify cross-run recurrence, causality, LOW provenance, and later learning without becoming lifecycle truth.

Works:

- full `.workline/review/` layout and Project compatibility
- durable Run/Finding/Repair summaries
- causality snapshots for intermediate repair-relevant surfaces
- cross-run B/C resolver
- Review provenance on LOW Work
- deferred LOW Workization as phase-less standalone Work
- one Project-wide Review LOW `planned_next` chain
- legitimate idle-boundary handoff to existing progression owner
- tests with unrelated pre-existing standalone Works and multiple Review sources

### P6 — Project-local Adaptive Policy + Project Policy Change operation + shadow observation

Desired state:

Project learning can safely strengthen/lighten verification without changing correctness semantics or losing the ability to detect regressions.

Works:

- Learning observation / Relevant Opportunity metrics
- Evaluation Trigger
- Policy Change Candidate
- fixed meta-review rules under pre-change policy
- canonical Project Policy Change operation owner/recovery/Git contract
- Project Profile versioning
- strengthening automation
- Temporary Guards
- observation / retain / adjust / rollback
- frozen measurement contract
- shadow/holdout verification for lightening
- lightening only after sufficient independent evidence

### P7 — Global Promotion + Workline-root Policy Change operation + independence model

Desired state:

Only independently supported generalized verification improvements can change Global Adaptive Policy, through a recoverable Workline-root maintenance operation that does not use unsupported self-hosting.

Works:

- Global adaptive policy storage/versioning contract
- Promotion Packet with lineage/correlation provenance
- independent evidence-source deduplication
- generalized failure/root-cause identity
- Global Policy Change Review
- canonical Workline-root policy maintenance operation
- single-writer/base-version/conflict/recovery behavior
- Git + Patch Notes
- Project adoption compatibility at next Review Run boundary
- Global observation / retain / rollback

## 19. Candidate 3 acceptance targets before another external review

Candidate 3 design is not declared READY merely by writing this checkpoint. Before implementation, the next independent review should specifically attempt to break these repaired invariants:

```text
1. a completed Review authorization survives pending-mutation/runtime cleanup
2. ambient dirty bytes cannot be silently relied on as persisted Work output
3. final Git bytes cannot drift from the Attested Candidate
4. Candidate Builder cannot review different filesystem meaning than Git persists
5. integration cannot mutate domain output while bypassing Work Formal Review
6. multiple Review LOW sources cannot create an ambiguous autonomous queue head
7. B/C causality remains auditable after intermediate Candidate runtime cleanup
8. policy mutation has an explicit non-Review operation owner and recovery path
9. lightening cannot erase its own regression detector
10. correlated Projects cannot inflate Global evidence independence
```

Current status after adjudication:

```text
External Review Candidate 2 verdict: REPAIR
ER-01..ER-10: ACCEPTED
HUMAN decisions: 0
Candidate 3: CREATED
Implementation: NOT STARTED
Candidate 3 independent re-review: NOT YET RUN
```
