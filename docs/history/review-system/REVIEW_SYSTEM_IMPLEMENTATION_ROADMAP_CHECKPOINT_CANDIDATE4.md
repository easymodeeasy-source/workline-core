# Review System Implementation Roadmap Checkpoint — Candidate 4

Status: DESIGN REPAIRED AFTER SECOND EXTERNAL REVIEW / IMPLEMENTATION NOT STARTED

This file is a design checkpoint, not normative authority. Runtime authority remains `registry.md` plus registry-routed canonical Skills. It supersedes `REVIEW_SYSTEM_IMPLEMENTATION_ROADMAP_CHECKPOINT_CANDIDATE3.md` as the latest implementation-roadmap design checkpoint, while preserving Candidate 3 and earlier checkpoints as history.

Candidate 3 received a second independent external review with verdict `REPAIR`. All eight reported Findings (C3-01 through C3-08) are accepted. Candidate 4 below incorporates those repairs while preserving the central architecture: Review remains a quality gate and does not become a second lifecycle/progression controller.

## 1. Candidate 3 external review adjudication

| ID | Category | Severity | Adjudication | Candidate 4 repair |
| --- | --- | --- | --- | --- |
| C3-01 | Problem | HIGH | ACCEPT | Candidate identity is extended to Git-persist-equivalent tree semantics and actual commit tree is re-proven before terminal completion |
| C3-02 | Problem | HIGH | ACCEPT | Final authorization Evidence is acquired in an isolated frozen-Candidate verification workspace with declared inputs |
| C3-03 | Problem | MID | ACCEPT | Review Receipt becomes immutable authorization/consumption evidence, bound to the actual transition it authorizes |
| C3-04 | Problem | HIGH | ACCEPT | Phase Integration verification-only becomes mechanically enforced, not just semantic guidance |
| C3-05 | Problem | MID | ACCEPT | Deferred LOW queue gets explicit queue-head eligibility semantics; `planned_next` alone is not relied on for strict ordering |
| C3-06 | Problem | MID | ACCEPT | Durable causal material widens beyond the initially hypothesized surface and allows unresolved causality |
| C3-07 | Problem | HIGH | ACCEPT | Shadow/holdout HIGH/MID found before terminalization escalates to normal Review obligations and blocks completion |
| C3-08 | Problem | MID | ACCEPT | Global evidence independence becomes three-state: proven independent / correlated / unresolved |

No Candidate 3 Finding requires a HUMAN decision. The external verdict `REPAIR` is accepted.

## 2. Repair grouping

The eight Findings reduce to four design repairs.

### Repair A — exact artifact identity from Review through Git

Covers C3-01, C3-02, C3-03.

Candidate 4 strengthens the invariant to:

```text
Reviewed Candidate
= Verified Candidate
= Attested Candidate
= Git-persisted Candidate
= Candidate consumed by the terminal transition
```

The equality must be mechanically proven at the relevant boundaries, not inferred from working-tree similarity.

### Repair B — mechanically enforced verification-only integration and strict LOW head semantics

Covers C3-04, C3-05.

Integration may not mutate domain output under a lightweight gate. Deferred LOW ordering may reuse `planned_next` for provenance, but queue enforcement is a separate selection rule owned by existing progression logic.

### Repair C — causal evidence remains auditable when the initial hypothesis was wrong

Covers C3-06.

Durable causality material must preserve enough of the entire owned repair delta and declared affected surfaces to permit later re-evaluation. C may remain unresolved when strong causality cannot be re-proven.

### Repair D — adaptive policy cannot bypass known correctness evidence or overstate independence

Covers C3-07, C3-08.

Shadow/holdout checks are measurement tools, not permission to ignore a supported defect discovered before terminalization. Global promotion counts only proven-independent evidence, with unresolved independence represented explicitly.

## 3. Core architecture retained

Review remains a gate around existing operation owners.

```text
Roadmap / START / existing progression
  -> registration, execution, mutation ownership, Git finalization, lifecycle, completion

Review System
  -> freeze Candidate/Context/Policy
  -> discover/adjudicate Findings
  -> require Repair/HUMAN/reverification
  -> emit authorization only when obligations are zero
```

No `review_passed`, `review_status`, or Review lifecycle field is added to `state.py`. Existing events/entities/relations remain lifecycle truth. Durable Review records are evidence/provenance, not another domain state machine.

## 4. Candidate 4 Candidate model — Git-persist-equivalent artifact

### 4.1 Logical split

Keep these separate:

```text
Candidate          = exact Git-persist-equivalent artifact/state Review may authorize
Review Context     = correctness meaning for the Review
Effective Policy   = verification method/rules frozen for the Review
Evidence           = verification outputs with declared dependency identity
Ambient Context    = relevant non-owned local/environment state, never silently part of persisted Work output
```

Each Run freezes:

```text
candidate_hash
review_context_hash
effective_policy_hash
```

### 4.2 Work Candidate

The Work Candidate is not defined merely as raw working-tree bytes.

Conceptually:

```text
Git-persist-equivalent Candidate Tree
= base commit tree
+ Work-owned additions/modifications/deletions
normalized through the Git semantics that determine the actual persisted tree
```

Candidate identity must account for the object semantics that matter to the resulting commit, including as applicable:

- repository-relative path identity
- blob content after relevant Git clean/filter normalization
- file mode / executable bit
- deletion
- symlink blob semantics
- gitlink/submodule entry identity
- case-collision rules relevant to supported filesystems
- relevant `.gitattributes` / filter configuration identity where it can alter persisted content

The Candidate contract must not assume that working-tree bytes equal committed blob bytes.

### 4.3 Path/object safety retained

Candidate Builder continues to require:

- Project-relative normalized paths only
- no absolute/drive escape
- no `.` / `..` root escape
- object type identified without blind dereference
- symlink/junction/reparse escape blocked or explicitly modeled
- Project-external artifacts represented as Context/Evidence, not silently imported as Candidate files

## 5. Isolated Candidate-bound verification

Final authorization Evidence is acquired against a frozen Candidate in an isolated verification workspace whenever technically possible.

Normal pattern:

```text
freeze Candidate Cn
-> materialize Cn in isolated verification workspace
-> inject only declared Context inputs
-> run verification
-> record Evidence dependency identity
-> Pre-Review evidence mapping
-> Formal Review
```

A live Project working tree with unrelated dirty/untracked state is not the default final verification environment.

### 5.1 Evidence dependency contract

Evidence used to satisfy final Review obligations records at least:

```text
candidate_hash
review_context_hash when relevant
tool/runtime identity when material
dependency/lock state when material
declared external service/version identity when material
clock/time sensitivity when material
cache provenance when material
```

The exact schema may vary by Evidence type, but the rule is fixed:

```text
If material verification inputs cannot be identified well enough to know what was tested,
that Evidence cannot independently satisfy final authorization.
```

Flaky/nondeterministic checks do not turn one observed PASS into reusable certainty. Effective Policy defines acceptable stabilization/repetition or marks such Evidence as non-final.

### 5.2 Ambient dependency discovery

If a check can only run in a non-isolated environment, its declared input/dependency set is part of the Evidence contract. Discovery that the result depends on non-owned Ambient Workspace content blocks final authorization until that dependency is formalized or the Evidence is replaced by isolated verification.

START never steals ownership of unrelated dirty content to make Review pass.

## 6. Commit-time and post-commit Candidate proof

Candidate 4 uses two relevant equality proofs.

### 6.1 Pre-persistence proof

Before authorized Git persistence, prove that the intended Work-owned delta still corresponds to the Attested Candidate. Drift creates a new Candidate generation and invalidates impacted Evidence/Review.

### 6.2 Actual commit-tree proof

After the commit object is created but before `work_completed`/terminal completion is finalized:

```text
Attested Candidate Tree
-> actual commit tree entries for the authorized Work result
-> exact semantic comparison
```

Only MATCH permits terminal completion.

This closes differences introduced by:

- Git clean filters / normalization
- LFS/filter behavior
- mode changes
- symlink/gitlink encoding
- index state
- hooks that modify staged/committed content

If hooks or Git semantics produce a different committed artifact:

```text
actual commit tree != Attested Candidate
-> do not treat the commit as reviewed completion
-> recover/reconcile according to the owning START mutation
-> construct/review a new Candidate or refuse safely
```

The exact recovery behavior must preserve existing Git/mutation safety and must not silently rewrite unrelated history.

## 7. Immutable Review Receipt bound to authorization consumption

Candidate 4 distinguishes:

```text
Review converged
```

from:

```text
that Review authorization was actually consumed by a concrete domain transition
```

A Review Receipt is immutable. Old Receipts are not overwritten into a synthetic latest-state record.

Conceptual fields include:

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
  type: work_completion | roadmap_registration | phase_entry | phase_integration_completion
  operation_id: ...
  result_stage_id: ...
consumption:
  status: consumed | unconsumed | superseded
  commit_sha: ... | null
  terminal_event_id: ... | null
```

Exact on-disk schema remains implementation work, but semantics are fixed:

- Receipt existence does not mean lifecycle completion
- lifecycle truth remains canonical events/state
- an old unconsumed/superseded Receipt remains historical evidence, not active authorization
- the consuming transition can be mechanically paired with the authorization that permitted it

### 7.1 Ordering

For Work completion the target ordering is:

```text
Review Attestation
-> existing completion precheck
-> final pre-persistence Candidate equality
-> prepare immutable Receipt identity for this authorization/operation stage
-> authorized Git persistence, including durable Receipt as part of the owning operation
-> actual commit-tree equality proof
-> terminal lifecycle finalization
-> Receipt consumption binding finalized durably under the same owning recovery contract
```

Implementation must choose a write/commit staging scheme that can recover every interruption point without making Receipt a second lifecycle ledger. Prefer co-persisting the durable authorization record with the commit that first fixes the authorized Candidate when compatible with existing Mutation/Git safety.

## 8. Repair / recurrence retained with stronger durable causal material

A/B/C definitions remain:

- A: newly discovered issue; may have existed before
- B: substantively same previously repaired problem reappears
- C: prior Repair caused a genuinely new problem absent before

C still requires strong causality.

For each Repair whose history may later support B/C or policy learning, durable causal material includes at minimum:

```text
source_candidate_hash
result_candidate_hash
repair_id
full Work-owned touched delta before/after
impact-analysis affected surfaces
generated artifacts necessary for causal re-evaluation where practical
external-state Evidence/fingerprint where reconstructible
supporting Evidence refs
causality status
```

The system does not need to preserve a permanent full Candidate Tree.

Causality status supports at least:

```text
supported
unresolved
insufficient_evidence
```

Only supported strong causality is finalized as C for learning/counting. If later evidence shows the retained causal material is insufficient, the system may downgrade the causal claim to unresolved rather than invent certainty.

## 9. Phase Integration Check — mechanically verification-only

Canonical direction remains:

```text
phase_integration_check = verification/evidence-only
```

Candidate 4 adds mechanical enforcement.

Preferred execution:

```text
frozen/read-only Candidate materialization
-> Integration verifier
-> evidence/report outputs only in allowed Review evidence/runtime locations
```

If a fully read-only materialization is not available, the operation must compare allowed domain tree identity before/after verification and refuse PASS/terminalization if any unauthorized domain mutation occurred.

Allowed writes must be explicitly scoped to Review evidence/runtime or other canonical evidence-only storage. `result_paths=()` is not proof of read-only behavior.

A required domain fix follows:

```text
Integration Finding
-> normal fix Work through existing CREATE/START owner
-> Work Formal Review
-> re-run Phase Integration Check
```

A future design that deliberately permits integration Work to own domain result delta must give that delta normal Work Formal Review in addition to the dedicated Integration Check.

## 10. Deferred Review LOW queue — strict head eligibility

Review-origin deferred LOW Works remain phase-less standalone Works and one Project-wide ordered chain. `planned_next` may record/provide the chain order, but Candidate 4 does not treat existing `planned_next_preference()` as a strict queue barrier.

When existing progression ownership considers deferred LOW maintenance, it resolves:

```text
queue head = first nonterminal Work in the Project-wide Review LOW chain
```

Eligibility contract:

```text
head startable
-> may select head

head held
-> queue waits for explicit resume

head blocked by requires_completion/dependency
-> whole Review LOW queue is blocked

head waiting HUMAN / reconcile required / invalid state
-> whole Review LOW queue is blocked

head terminal
-> advance head to next nonterminal member
```

A later LOW member is never selected merely because the head disappeared from the ordinary `startable_works()` candidate set.

Existing unrelated standalone Works are not silently inserted into the Review LOW chain.

`blocked != idle` remains mandatory. Review itself never chooses the Work; the existing progression owner applies this queue-head eligibility rule only after normal mandatory Roadmap/Phase progression and Roadmap achievement obligations are legitimately exhausted.

## 11. Project-local adaptive policy — shadow/holdout escalation semantics

The measurement contract remains frozen for each lightening observation window.

Shadow/holdout semantics become explicit:

```text
shadow not selected for this Relevant Opportunity
-> no direct completion effect

shadow executed and no Finding
-> measurement evidence only

shadow executed before terminalization and finds supported LOW
-> normal LOW handling

shadow executed before terminalization and finds supported HIGH/MID
-> promote to normal Review obligation
-> completion blocked until resolved

Finding becomes known only after terminal completion
-> historical escape
-> do not retroactively rewrite lifecycle
-> trigger fix / Temporary Guard / rollback evaluation as applicable
```

A lightening rule can reduce sampling frequency; it cannot authorize knowingly completing a Candidate with a supported correctness defect that has already been discovered.

Policy observation therefore cannot weaken Problem/Improvement or severity/completion semantics.

## 12. Global evidence independence — three-state relationship

Global promotion evidence-source relationships are at least:

```text
proven_independent
known_correlated
independence_unresolved
```

Only `proven_independent` sources count independently toward a threshold that requires multiple independent sources.

`known_correlated` evidence may still support the qualitative mechanism but is deduplicated within its correlation cluster for independence counting.

`independence_unresolved` does not automatically require HUMAN. Autonomous choices include:

- gather more provenance/evidence
- wait for another source
- conservatively cluster the unresolved sources together
- decline promotion for now

HUMAN is needed only when a genuinely human-owned external/authority fact is required to resolve the decision.

Promotion Packet provenance may include:

- repository/project identity
- fork/template/scaffold lineage
- relevant base provenance
- shared upstream dependency/incident
- CI/runtime/common generator provenance where known
- Finding/Run refs
- generalized mechanism/root-cause identity
- correlation cluster identity and confidence

The system asks:

```text
How many evidence sources are proven independent enough for this promotion claim?
```

not merely how many Projects observed the pattern.

## 13. Policy Change operation ownership retained

Candidate 3 ER-08 was re-reviewed as resolved and remains retained.

Project Policy Change is a separate Project state-changing operation owner using Project context, Project execution lock, Mutation Controller, and Git primitives under existing safety rules.

Global Policy Change is a Workline-root maintenance operation with explicit authorization, single-writer serialization, optimistic base/version, durable intent, write scope, validation, Git/push finalization, resume, and reconcile behavior.

Review evaluates and authorizes Policy Change Candidates. Review does not become physical mutation owner.

## 14. Legacy activation compatibility retained

```text
operation_contract = legacy
-> complete under legacy semantics

operation_contract = review-v1
-> Review obligations and durable authorization/consumption evidence required

unknown / contradictory
-> reconcile required
```

Absence of Review records alone never proves legacy status.

Review-v1 activation occurs only when the Candidate, Evidence, Receipt, Git proof, and recovery contracts required by that gate are available.

## 15. Seven-phase implementation Roadmap — Candidate 4

### P1 — Review Core + Authority + Runtime + durable authorization foundation + Git Candidate semantics

Desired state:

Review semantics and recovery primitives exist without changing domain lifecycle, and future Review authorization can be represented against Git-persist-equivalent Candidate identity.

Works:

- canonical Review Skill / registry routing / Review Constitution
- Review domain model
- Candidate / Context / Effective Policy identities
- Git-persist-equivalent Candidate tree model
- path/object/symlink/gitlink/filter/mode identity contract
- Reviewer Executor Protocol/adapters
- Coverage + Adjudication
- runtime Review storage/recovery compatibility
- immutable Receipt identity/authorization semantics
- Project layout/init/residue/recovery changes needed for durable Review records
- synthetic recovery/invariant tests

P1 does not activate Work terminal Review gating.

### P2 — Planning Review Gates

Desired state:

RoadmapPlan and PhaseEntryDesign are reviewed before existing canonical registration/mutation, with durable authorization evidence bound to the operation that consumes it.

Works:

- RoadmapPlan Candidate adapter using existing request identity
- Roadmap Review A/B/C viewpoints
- repair continuation
- READY -> existing Roadmap mutation
- PhaseEntryDesign Candidate adapter using existing design identity
- Phase Design Review closure viewpoints
- READY -> existing Phase entry/registration
- planning Receipt/consumption binding and recovery tests

### P3 — START Review Gate + isolated Evidence + commit-tree proof + Receipt consumption

Desired state:

A review-v1 Work cannot terminally complete unless the exact Git-persisted artifact equals the frozen, verified, attested Candidate and the authorization/transition pairing is durable.

Works:

- review-v1 vs legacy contract identity
- persist-equivalent Candidate Builder
- Ambient Workspace separation
- immutable Candidate materialization
- isolated verification workspace
- declared Evidence dependency identity
- Pre-Review Evidence mapping
- Work Formal Review A/B/C/D
- Review Attestation checkpoint
- pre-persistence Candidate equality
- immutable Receipt staging
- authorized Git persistence
- actual commit-tree equality proof
- Receipt consumption binding
- crash/resume tests for every interruption boundary

### P4 — Repair Loop + same-run recurrence + mechanically read-only Phase Integration

Desired state:

HIGH/MID Findings repair safely inside the current Work cycle while Integration verification cannot mutate domain output under a lightweight gate.

Works:

- ReviewRepairRequest
- executor `review_repair` purpose
- Repair Batch / Coverage Check
- semantic impact / Evidence invalidation
- Candidate-bound selective reverification
- same-run A/B/C and strategy-change trigger
- read-only Integration verifier or before/after domain-tree enforcement
- evidence-only output scope
- normal fix Work + reintegration flow

### P5 — Full Durable Review History + broad causal material + cross-run recurrence + strict LOW head eligibility

Desired state:

Clone/runtime-cleanup-safe history supports recurrence/causality/LOW provenance without becoming lifecycle truth, and deferred LOW selection cannot skip a blocked queue head.

Works:

- full `.workline/review/` layout
- durable Run/Finding/Repair summaries
- full Work-owned Repair touched-delta causal material
- affected-surface/external Evidence refs
- supported/unresolved/insufficient causal status
- cross-run B/C resolver
- LOW provenance/workization
- one Project-wide Review LOW chain
- explicit first-nonterminal queue-head eligibility
- coexistence tests with blocked/held/HUMAN/reconcile head and unrelated standalone Works

### P6 — Project-local Adaptive Policy + Project Policy Change operation + shadow escalation

Desired state:

Project learning may strengthen/lighten verification without changing correctness semantics or hiding a known defect.

Works:

- Relevant Opportunity / Learning metrics
- Evaluation Trigger
- Policy Change Candidate/meta-review
- Project Policy Change operation owner/recovery/Git contract
- Profile versioning
- strengthening / Temporary Guards
- frozen measurement contract
- shadow/holdout sampling
- shadow Finding escalation into normal obligations before terminalization
- historical escape handling after terminalization
- observation / retain / adjust / rollback
- lightening only after sufficient independent evidence

### P7 — Global Promotion + Workline-root Policy Change + three-state independence

Desired state:

Only sufficiently supported generalized verification improvements alter Global Adaptive Policy, with correlation uncertainty represented explicitly and mutation handled by a recoverable Workline-root operation.

Works:

- Global policy storage/versioning
- Promotion Packet provenance
- correlation clustering
- proven-independent / correlated / unresolved relation state
- independent-source promotion threshold
- Global Policy Change Review
- Workline-root maintenance operation
- single-writer/base-version/conflict/recovery behavior
- Git + Patch Notes
- Project adoption at next Review Run boundary
- Global observation / retain / rollback

## 16. Candidate 4 acceptance targets before another independent review

The next independent review should attempt to break at least these invariants:

```text
1. Reviewed/Verified/Attested Candidate cannot differ from actual committed Git tree.
2. Hidden ambient/environment inputs cannot silently make final Evidence pass.
3. Receipt existence cannot masquerade as lifecycle completion; consumed authorization is mechanically paired with its transition.
4. Integration verifier cannot mutate domain output and still PASS.
5. A blocked deferred LOW head cannot be skipped by a later startable LOW Work.
6. Causality can remain unresolved instead of being falsely finalized after evidence loss.
7. A shadow-discovered pre-terminal HIGH/MID cannot be ignored by lightening policy.
8. Unknown evidence independence cannot be counted as proven independence or force unnecessary HUMAN by default.
```

Current status:

```text
Candidate 3 second external review verdict: REPAIR
C3-01..C3-08: ACCEPTED
HUMAN decisions: 0
Candidate 4: CREATED
Implementation: NOT STARTED
Candidate 4 independent re-review: NOT YET RUN
```
