# Review System P1 — Contract Repair After Independent External Review

Status: REPAIRED CONTRACT FREEZE / IMPLEMENTATION NOT STARTED

This non-normative checkpoint records the accepted independent review of the P1 Integration Contract Reconnaissance and freezes the repairs that supersede the conflicting clauses in R1-R5, R9 and R12. Candidate 7 architecture is retained. Candidate 8 is not created.

Runtime authority remains `registry.md`, registry-routed canonical Skills, and live code until implementation and authority activation.

## 1. Review disposition

Independent review result accepted:

```text
Candidate 7 architecture: RETAIN
Architecture blockers: 0
HUMAN decisions: 0
P1 Integration Contract Reconnaissance: REPAIR REQUIRED
Implementation: DO NOT START until these repairs are frozen
```

The nine accepted repair items are:

1. recover exact K1 identity across `git commit` success -> mutation `commit_id` durable-save interruption;
2. generation serialization must survive process-lock loss through initial pending-mutation conflict scope;
3. canonical Review writes need write-time no-follow/reparse safety, not validation alone;
4. accepted async task identity/request must be clone-safe, not only runtime-reservation state;
5. immutable Review records require create-only semantics, not generic overwrite-capable `write_file` convention;
6. Work terminal Review-v1 binding requires eventual `exactly one` Consumption, not only 0-or-1 uniqueness;
7. PhaseEntry self-selection is a Roadmap-owned review-v1 planning precondition, not an adapter-owned semantic override;
8. first Review write requires Git committability preflight before canonical effects;
9. generation predecessor digest and recovery tests require exact byte/digest/crash contracts.

## 2. R1 repaired contract — safe immutable canonical Review writer

The R1 lazy canonical layout remains valid and unchanged:

```text
.workline/review/
  gates/<review_run_id>/<generation:06d>.yaml
  receipts/<receipt_id>.yaml
  consumptions/<consumption_id>.yaml
  supersessions/<superseded_receipt_id>.yaml
```

Empty Review directories are still not created or committed during Project Start. Absence of `.workline/review/` is not legacy/review-v1 activation evidence.

### 2.1 Write-time containment and no-follow proof

Structural validation is not enough. Every canonical Review create operation must perform a write-time safety proof immediately before the physical create/replace boundary.

For the path from Project root through `.workline/review` to the target parent, implementation must prove each existing component is the expected in-Project plain directory using lstat/no-follow semantics. Symlink, junction, reparse point, gitlink-like indirection or unprovable identity is refused before writing.

The writer must recheck the parent directory identity at the final replace/create boundary. Project execution lock only serializes Workline writers and is not treated as protection from external filesystem actors.

Failure outcome: STOP/reconcile as appropriate, and no bytes may be written outside the Project canonical Review namespace.

### 2.2 Immutable create-only primitive

Gate generation, Receipt, Consumption and supersession records are create-only immutable records.

Frozen behavior:

```text
target absent
-> create exact canonical bytes

target exists with exact expected bytes
-> idempotent MATCHING replay

target exists with different bytes/content/type
-> reconcile_required

base/update semantics for an existing immutable Review object
-> forbidden
```

Implementation should expose a Review-safe immutable create effect/validation mode rather than relying on callers never to pass a generic `write_file(base=...)`. At minimum, Mutation validation must mechanically reject update semantics for canonical immutable Review paths.

The same create-only validation is applied before replaying a previously recorded Review effect on resume.

### 2.3 Git committability preflight

Before the first canonical Review effect of a mutation is recorded/applied, every canonical Review path that the operation expects to commit must be checked through Git's own ignore/exclude evaluation.

Ignored or unanswerable committability is a pre-effect STOP. Workline does not modify `.gitignore`, `.git/info/exclude`, global excludes or user configuration to make the path committable.

This follows the existing bootstrap discipline: do not write canonical state first and discover only at finalization that Git cannot carry it clone-safely.

### 2.4 Generation byte/digest contract

Gate generation predecessor digest is frozen as:

```text
SHA-256(versioned canonical UTF-8 serialization bytes)
```

Canonical serialization uses the Review record renderer's versioned exact bytes, UTF-8 and LF line endings. The digest is over those canonical bytes, not an in-memory mapping and not post-clean-filter Git blob bytes.

Commit proof separately proves that the committed path reconstructs the exact canonical bytes under the Git persistence semantics bound by R6. A clone must therefore reproduce bytes whose canonical digest matches the chain.

## 3. R2/R3 repaired contract — crash-safe generation serialization

The statement "Project execution lock is the serialization mechanism" is superseded.

The Project lock serializes active writers only while the process lives. Crash releases it; pending mutation records must carry the cross-process conflict.

### 3.1 Initial WriteScope requirement

For generation N+1:

```text
hold Project execution lock
-> validate current gate chain and determine exact N+1 path
-> open/resume owning Mutation with that exact N+1 path already present in initial WriteScope.files
-> only then reserve/record/apply generation effects
```

The N+1 path must not be added only later through `extend_scope()`.

If a Review resource cannot be represented by an exact physical path at mutation-open time, the implementation must add an explicit logical conflict-resource facility with equivalent pending-mutation overlap semantics. It must not rely on late scope extension.

This guarantees that after:

```text
G(N+1) pending intent durable
process crash
lock released
```

a second invocation cannot independently create another N+1/fork while the first pending mutation exists.

### 3.2 Async accepted task descriptor is canonical

A canonical Gate generation that says a task is accepted must carry enough descriptor data to reconstruct/re-run the task after clone/runtime loss.

Minimum per accepted task:

```text
task_id
task_slot
task_kind
reviewer_or_adapter_identity
reviewer_or_adapter_version
request_digest
candidate_hash
review_context_hash
effective_policy_hash
accepted_generation
```

Provider-specific job handles may remain runtime-only. If lost, canonical task descriptor data must be sufficient to safely retrieve or rerun according to policy. `rtk_*` alone is insufficient.

Settlement must bind the same canonical task identity and terminal disposition. A task cannot be treated as settled because a runtime callback/body exists without a canonical matching generation.

### 3.3 Seal / invalidation ordering

Existing R3 rules remain: seal+Receipt are one mutation decision/stage; invalidation creates a later open generation and supersession before old authorization may proceed; only latest valid `sealed_authorized` generation may support a consumable Receipt.

The repaired generation serialization rule applies to every next-generation transition including settlement, seal-related snapshot change and invalidation.

## 4. R4 repaired contract — uniqueness plus terminal totality

P1 common infrastructure freezes 0-or-1 uniqueness:

```text
receipt_id -> 0 or 1 valid Consumption
terminal_event_id -> 0 or 1 valid Consumption
```

P3 Review-v1 Work activation additionally freezes totality:

```text
review-v1 terminal event
-> exactly one matching valid Consumption
```

A durable operation-contract marker must make it mechanically decidable after clone whether a terminal event belongs to `review-v1`; absence of Review files alone is not that marker.

Transient recovery exception:

```text
review-v1 terminal event exists
Consumption missing
matching pending mutation proves both were one recorded terminal stage
-> recoverable transient; resume must fill Consumption before publication/final completion
```

Invalid canonical state:

```text
review-v1 terminal event exists
Consumption missing
no matching pending recovery intent
-> fail closed / reconcile required
```

The inverse partial state is treated symmetrically where effect ordering or corruption permits it: Consumption without its exact required transition is not a valid completed consumption.

`state.py` still derives lifecycle from events only. The totality validator is an operation/Review consistency invariant, not a second lifecycle authority.

## 5. R5 repaired contract — exact K1 recovery after commit/save crash

R5's commit-only / proof / push-only topology is retained, with one mandatory recovery addition.

Live Mutation has the crash window:

```text
git commit succeeds
HEAD = K1
process crashes before effect.applied / commit_id durable save
```

Review-v1 must never continue to proof/push using message heuristics or an unproven HEAD.

### 5.1 Positive reconstruction of operation-made K1

When a recorded commit effect has no durable made-commit ID, implementation may backfill K1 only if all are positively proven:

```text
1. current branch ref == recorded commit branch
2. current HEAD is one exact commit K
3. parents(K) == [recorded base_head]
   (or root-parent shape where explicitly valid)
4. complete base_head -> K tree delta equals the exact commit effect's expected authorized path/tree-entry projection
5. no extra post-commit commit exists between recorded base and K
6. commit/tree inspection itself is complete and error-free
7. Review-validity identities required at this checkpoint still match
```

The proof compares actual Git tree entries/content/modes/deletions/symlink/gitlink semantics, not commit message and not merely a clean worktree.

If all pass:

```text
K is positively identified as this recorded mutation's exact K1
-> durably backfill the commit ID into the mutation record
-> only after that may post-commit Review proof continue
```

If any item is false or unprovable: `reconcile_required` (or Class A only where the separate R7 prerequisites positively apply). Never push first and infer later.

### 5.2 Backfill durability/idempotence

The backfill write is itself recovery metadata and must be durable before any proof checkpoint or push effect records K as authorized. Retry with the same exact K is idempotent. A different durable commit ID or changed HEAD/lineage is reconcile.

### 5.3 R7 dependency

R7 Class A is only implementation-ready once this exact commit-identity recovery primitive exists. Class A may not treat a commit lacking durable/proven identity as K1 merely because current paths/message look compatible.

## 6. R9 repaired contract — Roadmap owns the self-selecting requirement

The technical finding remains: `PhaseEntryDesign.entry` is not persisted as canonical Project progression state.

The previous wording that made the adapter itself reject `ambiguous graph + explicit entry` is superseded in ownership, not outcome.

Frozen authority boundary:

```text
Roadmap canonical authority
owns the review-v1 Phase planning precondition:
"a reviewed PhaseEntryDesign must be canonically self-selecting"

PersistedProjectionAdapter
only verifies that Roadmap-owned rule and round-trip equality
```

At P2 activation the Roadmap Skill/implementation must explicitly own this stronger review-v1 planning rule. The adapter must not invent a new planning semantic or silently override legacy Roadmap behavior.

Review-v1 rule remains:

```text
canonical graph uniquely selects A, entry=A -> valid
canonical graph uniquely selects A, entry=B -> invalid
canonical graph ambiguous A/B, entry=A -> invalid for review-v1
no explicit entry, canonical graph uniquely selects A -> valid
```

Legacy Phase-entry behavior remains unchanged until explicit review-v1 planning activation.

This is an authority migration/refinement, not Candidate 8 and not a second progression controller.

## 7. R12 repaired test additions

In addition to the existing matrix, activation requires these cases.

### 7.1 K1 identity save interruption

```text
record commit effect
-> git commit succeeds producing K1
-> crash before `commit_id`/applied save
-> resume
```

PASS only if exact branch/parent/complete tree-delta positive proof reconstructs K1, durably backfills the same ID, then proof may continue. Any extra commit, changed parent, unexpected tree entry, unanswerable Git query or lineage change => reconcile. Commit message match alone must never pass.

### 7.2 Generation fork after lock loss

```text
validated latest generation N
-> mutation for exact G(N+1) opened with N+1 path in initial WriteScope
-> pending intent durable
-> no generation effect applied
-> process crash / lock released
-> second invocation attempts same run next generation
```

It must resume/refuse behind the first pending mutation and must not create a second N+1 or fork.

### 7.3 Review-path TOCTOU

```text
ReviewStore validation passes
-> before effect apply, gates/<run> parent replaced by symlink/junction/reparse pointing outside Project
-> immutable create attempt
```

Must STOP/reconcile; no outside-Project file may be created/modified.

### 7.4 Immutable overwrite

For Gate/Receipt/Consumption/supersession:

```text
same path + exact bytes -> MATCHING/idempotent
same path + different bytes -> reconcile
attempt generic update/base semantics -> mechanically rejected
```

### 7.5 Clone-safe async task

After accepted task generation is committed:

```text
remove `.workline/runtime/**` or clone fresh
```

ReviewStore must recover task slot/kind/adapter identity/version/request digest and Candidate/Context/Policy binding from canonical state. Authorization remains blocked until settlement; provider runtime handle is not required for authority.

### 7.6 Terminal totality

Test all three states:

```text
E1 + C1 -> valid
E1 only + matching pending terminal stage -> recoverable transient
E1 only + no matching pending stage -> invalid/reconcile
```

and symmetric corrupted Consumption-only state as applicable.

### 7.7 First-write Git committability

Project Git rules ignore `.workline/review/**` through repository/global/exclude mechanisms. First Review write must STOP before any canonical Review effect is recorded/applied. Workline must not edit ignore configuration.

### 7.8 Predecessor digest exactness

Fixtures must show:

- canonical LF/UTF-8/versioned renderer produces stable SHA-256;
- semantic-equivalent but byte-different non-canonical encoding is rejected/normalized before persistence, not accepted as another digest form;
- predecessor bytes changed => chain failure;
- clone reproduces canonical bytes/digest.

## 8. Revised implementation readiness gate

The independent review did not reopen architecture. These repairs close implementation-contract seams only.

After this checkpoint and the affected R1-R5/R9/R12 documents are treated with these clauses as higher-precedence repaired contract, the next action is an independent implementation-readiness re-review.

Until that re-review returns READY:

```text
Candidate 7 architecture: RETAIN
Architecture blockers: 0
HUMAN decisions: 0
P1 contract: REPAIRED/FROZEN by this checkpoint
P1 implementation: NOT STARTED
Implementation activation: BLOCKED pending re-review
Candidate 8: NOT REQUIRED
```
