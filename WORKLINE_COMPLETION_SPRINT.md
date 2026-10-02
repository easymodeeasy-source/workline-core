# Workline Completion Sprint

Status: CONTROL CONTRACT / ACTIVE COMPLETION PROGRAM
Date: 2026-10-03

---

## 0. Authority scope

This document is the single completion-work control authority for taking Workline from the current production baseline to completion.

It is not the normative runtime specification.

Runtime authority remains:

~~~
registry.md
+ registry-routed canonical Skills
+ live implementation / tests
~~~

This document owns:

- completion scope
- Review Block topology
- dependency and collision rules
- frozen Human decisions
- implementation sequencing
- completion acceptance
- the mapping from completion decisions into runtime authority

A runtime rule written only here is not implemented merely because it is frozen here. When a Review Block lands, every runtime rule it introduces must also be activated in the canonical runtime authority that owns that responsibility.

Historical REVIEW_SYSTEM_* design/checkpoint/contract files remain rationale and frozen implementation history; they are not runtime authority.

BACKLOG.md is non-normative and is not the Completion Sprint execution tracker.

---

## 1. Starting baseline

Repository:

~~~
easymodeeasy-source/workline-core
~~~

Completion-program starting baseline:

~~~
main: 8fee664ad7bb6d4e8f9318de2dca64f410555d8d
tree: 48031a47d932193905f6a97ea96465540330406a
~~~

Remote GitHub main matched that baseline when this control contract was created.

Known local-only artifact from earlier execution context:

~~~
P3_F3_IMPLEMENTATION_PROGRAM.md
~~~

It is not present on remote main. Until inspected locally it is not authority, must not be deleted by assumption, and must not be promoted automatically.

---

## 2. Operating model

### 2.1 Control Plane

The Control Plane owns:

- read-only repository reconnaissance
- requirement and authority analysis
- Human-decision freeze
- contract design
- dependency/collision design
- implementation briefs
- candidate review
- completion judgment

Current Control Plane: ChatGPT.

### 2.2 Canonical-document write permission

Human authorization on 2026-10-03 permits the Control Plane to edit and commit Workline canonical documentation directly through GitHub in order to conserve coding-agent capacity.

This permission includes completion-control and normative documentation surfaces when the change is documentation/contract text.

It does not by itself authorize the Control Plane to modify production source code or tests.

### 2.3 Execution Writer

An Execution Writer owns work that requires an executable/local development environment:

- local repository inspection
- production code changes
- tests
- performance measurement
- OS/Git/filesystem probes
- candidate commits
- real-Project acceptance

Work, Claude Code, or another coding environment is an execution surface, not Workline runtime authority.

### 2.4 Coding-agent conservation

Do not delegate to a coding agent what the Control Plane can close from:

- live repository reads
- existing contracts
- static implementation inspection
- Human decisions already frozen

Before using a coding agent, freeze as much as possible of:

- exact objective
- semantic contract
- authority owner
- affected static surface
- non-scope
- acceptance criteria
- test matrix
- known edge cases
- stop conditions

Open-ended "investigate and design" tasks are a last resort.

---

## 3. Schedule policy

The former objective to complete the sprint by the 2026-10-03 14:00 tool reset is withdrawn.

Completion correctness must not be weakened to meet a tool-reset clock.

Priority is:

~~~
correctness
authority clarity
recoverability
testability
evidence
~~~

---

## 4. Frozen Human policies

### H-1 — LOW and non-blocking findings

LOW/non-blocking findings remain traceable in Review history but do not automatically create Work.

A future Work is created only when it is clearly valuable.

A change required for the current desired state is a Problem, not an Improvement.

### H-2 — automatic achievement

Phase/Roadmap achievement may be decided automatically when all are true:

- objective is clear
- evidence exists
- required checks pass
- no blocking obligation remains
- no unresolved HUMAN decision remains
- no new meaning is invented

Human confirmation is reserved for genuinely Human-owned judgment.

### H-3 — durable Review history

Durable Review history stores only structured, sanitized, public-safe facts required for:

- recovery
- audit
- recurrence detection
- repair causality
- achievement

Do not persist:

- chain-of-thought
- raw reasoning
- raw transcript
- secrets
- unnecessary private/local information

This does not authorize deletion of P1-P3 operational reconstruction/provenance material required by the existing contracts.

### H-4 — completion scope versus runtime Improvement

Current completion scope and post-completion runtime Improvement are separate.

P4-P7, named BL items, runtime hardening and final acceptance already in this Completion Sprint may not be deferred merely by calling them Improvements.

Runtime classification:

~~~
Problem HIGH -> blocking
Problem MID  -> blocking
Problem LOW  -> non-blocking only if the completion objective still holds
Improvement HIGH/MID/LOW -> non-blocking
desired requirement change -> HUMAN
~~~

H-1 through H-4 are frozen and are not reopened without an explicit Human change.

---

## 5. Frozen Human decisions

### HD-1 — malformed semantic-changing input

Decision: REJECT BEFORE EFFECT / RESERVATION.

Inputs that currently succeed while persisting a different semantic value, including newline truncation/heading injection classes, are rejected before reservation/effect.

This is an intentional success-to-refusal compatibility change.

### HD-3 — RB9 real Project

Decision: DEFER UNTIL RB9.

At RB9, present 2-3 candidate real Projects and their risks to the Human once.

Do not use:

- PokéTool
- retained P3 acceptance Projects
- an unapproved Project

### HD-2W — Execution Writer landing

Unresolved until first actual implementation landing is ready.

Question: after Control Plane review PASS, exact candidate identity, required tests and race gate, may the Execution Writer fast-forward main without per-landing Human confirmation?

This does not block design.

---

## 6. Completion topology

The Completion Sprint has ten Review Blocks.

~~~
RB1   BL-006 read-only status/context
RB2   BL-007 cold-start performance
RB3   P3-F4 + P4 + BL-004
RB4   P5 + BL-005 front / durable Review history
RB5   BL-003 + BL-005 back / Phase Review and achievement
RB6   BL-055 + P6 / Project-local policy
RB7   P7 / Global promotion
RB8   BL-011 + BL-013 + BL-020
RB9   final audit + BL-100 + acceptance
RB10  runtime hardening
~~~

The old nine-block topology is obsolete.

---

## 7. Dependency graph

Hard dependency:

~~~
RB1 -> RB2

RB3-K0
-> RB3-C1
-> RB3 remaining / P4 / BL-004
-> RB4

RB4 -> RB5
RB4 -> RB6 -> RB7
RB5 + RB7 -> RB8

RB3-C1 design -> RB10-N4 design
RB3-C1 landed semantics + RB1 status -> RB10-N4 integration

RB1 + RB2 + RB3 + RB4 + RB5 + RB6 + RB7 + RB8 + RB10
-> RB9
~~~

Structural critical path:

~~~
RB3 -> RB4 -> RB6 -> RB7 -> RB8 -> RB9
~~~

RB10 N2/N3/N6 may advance earlier when collision-free.

---

## 8. Collision rules

Separate branches do not by themselves prove safe parallelism.

One semantic surface has one writer.

Collision-sensitive pairs:

~~~
RB3-C1 <-> RB10-N4
RB1    <-> RB5 status
RB1    <-> RB10-N4 status
RB3    <-> RB4 Review semantics/history
RB4    <-> RB5 achievement evidence
RB6    <-> RB7 policy authority
RB10 N2 <-> N3 legacy registration owners
RB10 N6 <-> N2/N3 when they share an implementation invariant
README/canonical-doc writers <-> same files
RB9 <-> all production writers
~~~

Landing is serialized.

---

## 9. RB1 — BL-006 read-only status/context

Goal: canonical read-only status/context interface.

Machine- and human-readable output includes at least:

- Project
- Roadmap
- Phase
- Work
- current
- next
- pending mutation
- validation
- authority
- Git state
- approved push destination
- Review activation/status

Hard constraints:

- no Project mutation
- no durable state write
- no repository write
- no network write

Later RB5/RB6/RB10 additions are additive to the RB1 base contract.

---

## 10. RB2 — BL-007 cold-start performance

Measure first.

Representative scale:

~~~
~300 Works
~3,000 events
~~~

Optimization is justified only if either:

1. indexing/removal of derivation can eliminate more than 50% of status/validate-project wall time; or
2. approximately 10x input produces clear super-linear growth, operationally about >12x median wall time beyond measurement noise.

If neither threshold is met:

~~~
measurement evidence
+ no-optimization disposition
+ BL-007 closeout
~~~

Do not change bootstrap/registry authority layout for performance by default.

Actual measurement requires an Execution Writer.

---

# 11. RB3 — P3-F4 + P4 + BL-004

RB3 begins by closing P3-F4 residue before P4.

P3 F3 explicitly defers:

- Class A/B/C mismatch handling
- adopt_existing_local_commit
- replacement Candidate/Receipt
- supersession
- remote-publication precondition
- stale-generation mechanics
- repair action matrix
- interruption matrix
- permanent set-aside/recovery disposition

## 11.1 RB3-C1 — inherited invariants

F4 does not weaken:

- exact commit identity
- no push before complete proof
- exact-SHA publication
- no force
- no reset/rebase/amend recovery
- no branch-tip substitution
- complete tree-entry delta proof
- Candidate/Context/Policy/Evidence binding
- Receipt existence != completion
- Authorization != Consumption
- Review record != lifecycle truth
- legacy START unchanged
- START remains operation owner
- Review remains subordinate authorization gate
- canonical Review records are immutable create-only

Unknown is never proof.

## 11.2 Pre-commit drift

If a mismatch is known before the result commit exists:

~~~
do not commit known mismatch
-> freeze new Candidate
-> perform required verification / Review
~~~

Class A/B/C is post-commit recovery, not a normal-flow strategy.

## 11.3 Post-commit classification

### Class A — adoptable existing local result

Available only when all are positively proven:

1. exact K1 was created by the current operation/mutation;
2. K1 has exactly the expected one parent;
3. complete parent->K1 delta is known with path, modes, object types and object IDs;
4. every changed entry is operation-owned;
5. no unexpected/non-owned entry exists;
6. expected branch and raw lineage remain intact;
7. K1 is not already published to the approved destination in an unauthorized state;
8. K1 can be frozen exactly as a replacement Candidate from committed objects;
9. no history rewrite is required;
10. ownership/provenance are unambiguous.

Permitted Class-A entry causes:

~~~
A1: old Candidate != actual K1 due to an operation-owned persistence transform

A2: exact operation-owned K1 still exists locally, but its prior authorization
    became stale before publication/terminalization and requires fresh authorization
~~~

A2 is fresh Review, not generic Review reuse.

### Class B — unexpected/non-owned commit content

~~~
reconcile required
no automatic repair
no revert
no claiming ownership
no push
no terminalization
~~~

### Class C — ownership/ref/lineage unprovable

~~~
reconcile required
no adoption
no push
no terminalization
~~~

Examples include unknown K1 ownership, unavailable raw parent, wrong parent count, ref rewrite, complete-delta unavailability or contradictory durable recovery state.

## 11.4 Already-published K1

If K1 already exists at the approved destination before replacement authorization:

~~~
unauthorized / historical publication escape
-> no history rewrite
-> no retroactive authorization
-> no normal Class-A publication
-> reconcile / historical-escape handling
~~~

Use the pinned destination and positive destination-read semantics. A stale remote-tracking ref is not publication evidence.

## 11.5 Replacement Candidate C2

For Class A:

~~~
exact K1
-> read persisted projection from K1 and parent(K1)
-> freeze replacement Candidate C2
-> fresh Context / Policy / Evidence / reviewer binding
-> fresh Review
~~~

C2 is reconstructed from immutable committed objects, never the mutable working tree.

Old authorization is not reused.

## 11.6 Work set-aside linkage

Work replacement adopts the existing planning principle that a new Run names older matching Runs it intentionally does not resume.

A versioned Work request contract gains:

~~~yaml
set_aside_runs:
  - review_run_id: ...
    reason: ...
~~~

Existing in-flight v1 Work request bytes keep their existing semantics.

Set-aside:

- never deletes or edits the older Run
- prevents automatic recovery selection of that exact older Run
- is never inferred by age or ID order

The explicit no-replacement Human disposition operation is RB10-N4.

## 11.7 Class-A physical topology amendment

Earlier R7/F3 text required:

~~~
parent(K2-A) == K1
~~~

That is incompatible with the later F3 invariant requiring Candidate/TaskInput and generation commits to be persisted on the same branch before reviewer launch/seal.

F4 therefore forward-amends only the Class-A topology:

~~~
K1
-> replacement G1
-> replacement G2
-> replacement G3 + replacement Receipt R2
-> K_adopt
-> K_terminal
~~~

The raw range K1..parent(K_adopt) contains only that replacement Run's canonical Review-generation commits.

No domain/result/lifecycle transition is allowed in that range.

This is a narrow own-Review range exception, not generic HEAD reuse.

## 11.8 K_adopt

K_adopt is the metadata-only Class-A adoption carrier.

Its parent is the exact latest replacement-Review generation commit.

Its complete delta contains only the immutable supersession of the old Receipt and any F4 Class-A metadata explicitly required by the final record contract.

It contains no:

- ReviewedArtifact delta
- domain-result delta
- lifecycle event
- AuthorizedTransitionProjection
- Consumption

R2 and replacement Review records are inherited from the replacement seal.

K_adopt receives no additional Review.

This is the recursion cutoff.

Any mismatch:

~~~
reconcile required
no recursive Class A
no R3
no push
~~~

## 11.9 Class-A publication topology

For a remote Project:

1. publish exact K_adopt, never K1 alone and never branch tip;
2. create normal terminal transition K_terminal consuming R2;
3. prove K_terminal;
4. publish exact K_terminal.

The first publication carries K1 + replacement Review + R2 + supersession in one fast-forward lineage, so K1 is never first exposed remotely without the replacement authorization material in the published history.

Result-bearing remote Class A therefore retains two publication points:

~~~
1. adopted result publication
2. terminal publication
~~~

Remote-less Projects omit publication but keep local proof and terminal semantics.

## 11.10 Sealed authorization invalidation

A sealed Work Receipt that becomes stale before consumption is made durably non-consumable.

Use the already-established planning invalidation pattern for Work:

~~~
generation 3 sealed / R1
-> generation 4 open invalidation
   + Supersession(R1)
~~~

Generation 4:

- names generation 3 and its digest
- carries no Receipt
- carries no authorized stage
- carries invalidation evidence with stable reason identity
- is the final generation of that Run

Supersession and generation 4 are created by one generation mutation.

## 11.11 Unsealed/unsealable Run disposition

A Run without a Receipt cannot use Receipt supersession.

When an automatic replacement Run is created, permanent replacement disposition is represented through that replacement Run's set_aside_runs.

No old record is deleted or rewritten.

If no replacement Run is created, F4 does not invent a tombstone. RB10-N4 owns the explicit Human-invoked no-replacement disposition operation.

## 11.12 Recovery selection

For one Work Review invocation, prove and classify every matching Run as one of:

~~~
consumed
superseded/invalidated
set_aside
not-authorized terminal
recoverable
stale
incomplete/contradictory
~~~

Rules:

- exactly one recoverable -> resume it
- zero recoverable -> a new Run may begin if normal preconditions allow
- multiple recoverable -> reconcile
- incomplete/contradictory matching Run -> reconcile
- consumed/invalidated/superseded/set-aside -> never resume

Never select by recency.

## 11.13 Stale-generation blocking

Current authorization is re-derived at every irreversible boundary, at least:

- before result-publication effect record
- immediately before result publication
- before terminal stage record
- before terminal commit
- before terminal-publication effect record
- immediately before terminal publication
- before returning completed

Material stale surfaces include:

- Candidate
- base lineage
- owned result identity
- Context
- Effective Policy
- Evidence
- reviewer binding
- activation
- Receipt currentness
- Supersession
- Consumption
- raw commit lineage
- approved push destination

A prior proof is not timeless validity.

## 11.14 Async/shadow cutoff

Every task durably accepted as required before authorization cutoff must settle under the Effective Policy before authorization is consumable.

A result first becoming known only after durable terminal completion is a historical escape:

~~~
do not rewrite completed lifecycle
do not pretend it participated in prior authorization
hand off to later Review/Repair/History policy
~~~

## 11.15 F4 action matrix

~~~
pre-commit drift
-> new Candidate

post-commit exact normal match
-> normal F3 path

strict Class A
-> C2 -> replacement Review -> R2 -> K_adopt -> terminal Consumption

Class B
-> reconcile

Class C
-> reconcile

already remotely published K1 before valid replacement authorization
-> historical/unauthorized publication escape -> reconcile

sealed Receipt becomes stale before consumption
-> invalidate/supersede -> new Candidate if current state can be positively reconstructed

K_adopt mismatch
-> reconcile, no recursive Review

terminal commit mismatch
-> reconcile, no push, no completed return
~~~

## 11.16 Interruption matrix requirement

Regression coverage must include interruption at least around:

- mismatch discovery / Class-A checkpoint
- C2 freeze
- replacement G1/G2/G3
- reviewer launch/settlement
- R2 issue
- K_adopt record/commit/proof/publication
- terminal stage partial application
- K_terminal commit/proof/publication
- final completion proof before mutation cleanup

No interruption may create duplicate:

- publication
- Receipt
- Supersession
- Consumption
- terminal event
- replacement Candidate

and may never fall back to legacy START.

## 11.17 P4 boundary

F4 ends when recovery can safely choose among:

~~~
continue current authorization
freeze replacement Candidate
Class-A adopt exact local result
invalidate/supersede
set aside
reconcile
historical escape
~~~

P4, not F4, owns:

- Problem/Improvement/HUMAN adjudication v2
- Repair Batch
- repair execution
- new Candidate after repair
- selective reverification
- recurrence and convergence

---

## 12. RB3 remaining — P4 / BL-004

P4 closes the current-cycle Repair Loop and BL-004 finding classification/convergence problem without turning Review into a second lifecycle controller.

P4 is common Review infrastructure for the already-existing review-v1 planning kinds and review-v1 Work kind. It does not make Review mandatory for every Work and does not change legacy operation behavior.

### 12.1 P4 boundary and precedence

P4 owns:

- durable raw-report material needed to resume the current Review cycle
- separate discovery and adjudication tasks
- supported/unsupported/HUMAN adjudication
- Problem / Improvement classification
- authoritative severity after adjudication
- Finding identity and deduplication
- one Repair Batch per repaired Candidate generation
- ReviewRepairRequest and repair-task recovery
- Candidate generations inside one owning operation
- Repair Coverage Check
- positive-proof Evidence reuse
- conservative invalidation
- A/B/C repair relationship
- strategy-change trigger
- impact-scaled reverification
- verification-only Integration side-effect contract
- normal fix Work + reintegration
- policy/contract versioning and in-flight compatibility
- convergence by unresolved obligations

P4 does not own:

- long-lived cross-run Review history beyond the minimum records needed to resume/prove the current cycle (RB4/P5)
- Project-local adaptive Policy (RB6/P6)
- Global promotion (RB7/P7)
- Phase completion/achievement integration (RB5)
- lifecycle/progression truth
- Git finalization

Where old non-normative design notes conflict with frozen H-1/H-4, this Completion Sprint contract wins.

In particular, the old directions:

~~~
Improvement HIGH/MID -> mandatory current-cycle repair
every LOW -> automatically create independent Work
convergence requires every LOW to become a Work
~~~

are withdrawn.

The frozen rule is:

~~~
Problem HIGH/MID -> blocking current-cycle obligation
Problem LOW      -> non-blocking only when the current completion objective still holds
Improvement any severity -> non-blocking
desired requirement change -> HUMAN
LOW/Improvement -> no automatic Work creation
~~~

### 12.2 Discovery and adjudication are separate

Use:

> discovery is fresh; adjudication is history-aware.

A discovery reviewer receives the fixed Candidate, current requirements/desired state, Context/Policy and the Evidence it needs.

By default it does not receive prior Finding/Repair history.

Discovery reports claims. They do not authoritatively decide Problem/Improvement/HUMAN and do not repair the Candidate.

After all required discovery reports for the fixed Candidate are frozen, a separate adjudication task receives:

- the exact Candidate identity
- exact raw report records
- current decided requirement/desired state
- relevant Review Context and Effective Policy
- prior Finding/Repair relationships within this current Review cycle
- relevant Evidence/coverage identities

The adjudicator does not modify the Candidate.

### 12.3 Raw report durability

P2/P3 currently retain settled report identity by digest while Work P3 intentionally does not preserve LOW text canonically.

P4 current-cycle repair cannot recover correctly from only a digest.

Therefore every settled discovery report used by P4 is written canonically before or with the generation that first records its settlement.

Add a content-addressed Review record:

~~~
.workline/review/reports/<result_digest>.yaml
~~~

The filename digest equals the canonical report-record digest.

The raw report remains immutable.

It preserves the reviewer's original:

- task identity
- reviewer identity/version
- status
- claimed severity
- code
- message
- versioned coverage declaration where the P4 reviewer contract provides it

Reviewer severity is input to adjudication, not final authority.

P4 never rewrites a raw report to reflect later adjudication.

Here "raw report" means **unadjudicated discovery report**, not unsanitized model output.

Before canonical persistence, the report must already satisfy H-3:

- no chain-of-thought or hidden reasoning
- no raw chat/session transcript
- no secrets/credentials
- no unnecessary absolute/local path
- no unnecessary private/local identifiers
- only the structured public-safe claim needed for audit/recovery

The reviewer instruction requires public-safe structured output. If an external return cannot be made H-3-safe without changing the substantive claim, it is not persisted or settled as that report; the task remains/re-enters the versioned reviewer path for a safe report. Unsanitized external output is ephemeral and never settlement authority.

### 12.4 Adjudication classification

Each raw claim is handled in this order:

~~~
1. Is the claim supported by the Candidate/requirement/evidence?
   NO
   -> unsupported / dismissed
   -> no Finding obligation

2. Does deciding the claim require changing or choosing
   product/spec/requirement meaning?
   YES
   -> HUMAN
   -> do not silently define the requirement

3. Does the Candidate fail the currently decided requirement/objective?
   YES
   -> Problem

4. Otherwise, is there a genuinely better actionable alternative?
   YES
   -> Improvement

5. Otherwise
   -> dismissed_non_actionable
~~~

"false positive" is not a content category. It is an unsupported adjudication outcome.

"HUMAN" is not a content category. It is an adjudication outcome saying Review cannot decide the requirement boundary.

Normalized content categories are only:

~~~
Problem
Improvement
~~~

Both may retain HIGH/MID/LOW as importance metadata, but blocking behavior is H-4, not the old uniform Problem/Improvement rule.

A Problem classified LOW is valid as non-blocking only if the current completion objective still holds. If the objective does not hold, the adjudicator must classify it as blocking Problem MID/HIGH, or HUMAN if the requirement itself is unclear.

### 12.5 Normalized Finding identity and deduplication

One adjudication record is canonical for one Candidate/Review Run:

~~~
.workline/review/adjudications/<review_run_id>.yaml
~~~

It contains stable reserved Finding IDs and the complete normalized disposition of the frozen raw reports.

A normalized Finding contains at least:

- finding_id
- review_run_id
- candidate_hash
- category: Problem | Improvement
- severity: HIGH | MID | LOW
- statement
- semantic_surface
- source claims as (task_id, result_digest, finding index)
- disposition
- A/B/C relationship where supported
- linked prior finding/repair IDs where applicable
- causal evidence digest where B/C is asserted

Unsupported, HUMAN and dismissed_non_actionable raw claims remain explicit adjudication entries even though they are not accepted Problem/Improvement Findings.

Deduplicate by repair identity, not wording alone.

Merge only when all are true:

- the substantive problem/improvement is the same
- the semantic responsibility is the same
- one repair/disposition would close all source claims

Keep separate if root cause or repair strategy differs.

If uncertain, keep separate.

When merged source claims disagree on severity, use the strongest severity the adjudication can support and retain every source reference.

### 12.6 P4 Review Run state machine

A P1 Review Run remains bound to exactly one Candidate.

P4 does not mutate a Run to point at a repaired Candidate.

P1 GateGeneration already permits later generations to accept additional immutable tasks, so P4 uses the existing chain rather than adding a second controller.

For a new P4 Review Run:

~~~
G1  accept discovery task(s)
    CandidateSnapshot + discovery TaskInput(s) + open gate

G2  settle required discovery task(s)
    persist raw report record(s)
    open gate

G3  accept adjudication task
    adjudication TaskInput is reconstructed from canonical material
    open gate

G4  settle adjudication
    persist adjudication record
    derive obligations
    open gate

if obligations permit authorization:

G5  seal
    issue Receipt
    -> normal owning-operation persistence/Consumption path

if blocking Problem repair is required:

G5  accept one Repair task
    persist one Repair Batch + Repair TaskInput
    no Receipt

G6  settle Repair task
    persist Repair Result
    freeze CandidateSnapshot N+1
    no Receipt

then:
    new Review Run for Candidate N+1
    previous Run is explicitly set aside/replaced
~~~

Exact generation count is therefore versioned P4 semantics, not a reinterpretation of P2/P3 v1's fixed three-generation Work/planning flow.

A HUMAN adjudication does not launch a repair that guesses the missing requirement. The current Run remains non-authorizing/HUMAN_WAIT. After the Human decision changes or confirms the requirement, the owning operation freezes a new Candidate/Context as needed and starts a new versioned Run, explicitly setting the old Run aside.

### 12.7 Adjudication task durability

Adjudication is an external task when an external model/agent performs it.

Therefore P1's launch rule applies:

~~~
no external adjudicator launch
until its exact TaskInput and accepted descriptor
are durably persisted in a committed gate generation
~~~

The adjudication TaskInput binds:

- Candidate hash/material identity
- Context hash
- Effective Policy hash
- ordered raw-report identities
- prior current-cycle Finding/Repair references it is allowed to use
- adjudicator identity/version
- adjudication instruction/version

A crash relaunches the same accepted adjudication task only to the bound adjudicator identity/version.

No in-memory raw report or chat transcript is recovery authority.

### 12.8 One Repair Batch per Candidate generation

After adjudication, all currently decidable blocking Problem HIGH/MID Findings of that Candidate are grouped into one Repair Batch.

Do not repair one blocking Finding while leaving another known blocking Finding from the same frozen Candidate for a later ordinary patch round.

The Repair Batch is immutable and stored as:

~~~
.workline/review/repair-batches/<repair_batch_id>.yaml
~~~

It binds at least:

- repair_batch_id
- operation_identity
- source review_run_id
- source candidate_hash
- ordered blocking finding_ids
- semantic surfaces
- repair purpose
- selected repair strategy
- allowed repair/result surface
- strategy-change requirement, if any

Improvement Findings are not inserted into a mandatory Repair Batch.

Problem LOW is not inserted automatically unless a deliberate current-cycle repair is chosen. Its non-blocking disposition remains traceable.

HUMAN claims are never converted into repair instructions.

### 12.9 ReviewRepairRequest and repair ownership

The repair executor receives a versioned ReviewRepairRequest reconstructed only from canonical material.

It contains:

- exact source Candidate reconstruction material
- exact Repair Batch
- current decided requirement/desired state
- repair purpose
- allowed result surface
- relevant Evidence/coverage constraints

The repair executor may propose/create the repaired artifact, but Review still does not own lifecycle, top-level Project mutation or Git finalization.

The owning Roadmap/START operation remains the operation owner and is the only component that may adopt the repair result into its Candidate flow.

The repair task itself is accepted durably before external launch under the same P1 task rules.

An exception/invalid return does not settle the task.

An explicit failed/declined repair never authorizes the old Candidate and never becomes a successful repair by inference.

### 12.10 Repair Result and Candidate N+1

A successful repair produces an immutable Repair Result:

~~~
.workline/review/repair-results/<repair_batch_id>.yaml
~~~

It binds:

- repair_batch_id
- source candidate_hash
- result candidate_hash
- repair executor identity/version
- exact repaired semantic surface
- change-impact class
- Repair Coverage Check result
- Evidence reuse/invalidation result
- causal material needed to judge B/C in the next adjudication

Candidate N+1 is a complete new Candidate, not a patch object.

Its CandidateSnapshot is frozen before the next reviewer launch.

The next Run is a new immutable Review Run with the same owning operation identity and a higher current-cycle Candidate generation.

The old Run is explicitly named in the new request's set-aside/replacement material.

No Review Run changes candidate_hash in place.

### 12.11 Current Review cycle identity

One owning operation may contain several Candidate-specific Review Runs.

The stable current-cycle identity is the owning operation_identity plus its target/review kind.

Candidate generation is an explicit positive integer carried in the P4 request/repair linkage.

The chain is proven from explicit:

- source review_run_id
- source candidate_hash
- repair_batch_id
- result candidate_hash
- next review_run_id/set-aside linkage

Do not derive generation by file ordering, timestamp or newest ID.

### 12.12 Reviewer coverage

P4 reviewer contracts make coverage explicit.

Each required discovery report states:

- assigned viewpoint/task slot
- surface actually inspected
- concrete behavior/questions checked
- Evidence used
- relevant surface not inspected or not decidable

A candidate with zero Findings but unknown required coverage is not converged.

Coverage gaps are classified:

~~~
unrelated to Candidate
-> explicitly not applicable

relevant and already positively covered
-> attach valid Evidence

relevant and not sufficiently covered
-> targeted reviewer/check required

requires requirement/product judgment
-> HUMAN
~~~

Do not rerun every base reviewer merely because one targeted coverage gap exists.

### 12.13 Evidence dependency completeness and reuse

Reuse the existing P1/P3 dependency-class vocabulary and typed proof model in review/closure.py.

Evidence is reusable across repaired Candidates only when all are positively proven:

1. the Evidence declaration is complete under the versioned dependency vocabulary;
2. every required dependency class is covered by a valid observed/pinned/denied proof;
3. every non-required class is positively excluded or otherwise completely accounted for;
4. every concrete bound identity relevant to the Evidence is unchanged;
5. adapter identity/version and proof mechanism identity/version are unchanged;
6. the repair impact does not change a semantic assumption the Evidence proved.

If any required class is unknown, unaccounted or contradictory:

~~~
completeness = unknown
-> Evidence is fresh-use-only
-> reacquire after repair
~~~

Absence of observed change is not proof of reuse.

A reviewer report/adjudication from Candidate N is never reused as authorization for Candidate N+1. Formal discovery is against the new fixed Candidate. Only Evidence with the positive-proof reuse contract may be reused.

### 12.14 Impact-scaled reverification

Every successful repair records one change-impact class:

~~~
LOCAL
  localized behavior/condition/input-output rule

SHARED
  shared helper/validator/serializer/common transform

CONTRACT
  state/event/schema/lifecycle/recovery/authority semantics

FOUNDATION
  broad infrastructure or assumption used across many operations
~~~

Minimum reverification follows semantic impact, not file count.

LOCAL:
- focused tests
- direct callers/consumers where semantics reach them

SHARED:
- focused tests
- representative callers
- relevant integration checks

CONTRACT:
- writers and readers
- failure/interruption/retry/resume
- adjacent eligibility/progression effects
- schema/event/contract round-trip where relevant

FOUNDATION:
- broad targeted integration
- full suite when whole-system evidence is materially required

For every repair answer:

1. what semantic behavior changed?
2. who writes it?
3. who reads/depends on it?
4. which operations change eligibility/outcome?
5. what failure/interruption/retry/resume behavior changed?
6. did schema/event/contract meaning change?
7. is shared code/authority affected?
8. which previous Evidence assumptions became invalid?

The Repair Coverage Check occurs before claiming Review Ready.

### 12.15 Repair Coverage Check

The Repair Coverage Check is not exhaustive testing.

It proves that the repair is not merely suppressing the observed site when responsibility is broader.

At minimum it records:

- other paths/sites with the same responsibility
- whether the common mechanism should be repaired instead
- whether the affected set is positively enumerable
- whether the implemented repair covers that set
- unresolved coverage gap, if any

If the check shows a local repair against a shared responsibility:

~~~
do not spend another Formal Review round discovering the omission
-> revise/widen repair first
~~~

Unknown repair coverage is not PASS.

### 12.16 A/B/C relationship

Timing alone never establishes causality.

For Findings after a repair:

~~~
A_NEW
  newly discovered; may have existed before the prior repair

B_RECURRENCE
  the prior repair failed to close the same substantive Problem/
  semantic responsibility

C_REPAIR_INDUCED
  the prior repair positively created a Problem that did not exist before it
~~~

B/C require positive support.

A B finding names the prior Finding/Repair it recurs from.

A C finding names the causal Repair Batch and carries evidence that the Problem was introduced by that repair.

"observed after repair" is not C.

If causality is unknown, classify A_NEW until stronger evidence exists.

The A/B/C relationship is separate from Problem/Improvement and HIGH/MID/LOW.

### 12.17 Strategy-change trigger

There is no semantic round cap.

Track supported repair failures by semantic surface.

If two consecutive supported B/C repair failures occur in the same semantic surface, including mixed B/C:

~~~
B -> B
C -> C
B -> C
C -> B
~~~

the next repair must enter:

~~~
STRATEGY_CHANGE
~~~

Do not continue an ordinary local-patch strategy.

Permitted strategy-change classes include:

- repair shared/common responsibility
- deliberately widen scope
- reconsider state/lifecycle/authority model
- replace/rollback unstable prior repair
- restructure around a simpler coherent invariant
- HUMAN when the required change crosses a product/spec/security/capability boundary

After a strategy change, run normal impact analysis, Repair Coverage Check and reverification again.

Operational failures such as model timeout, rate limit, crash or unavailable tool do not count as B/C semantic repair failures.

### 12.18 P4 convergence

Convergence is based on unresolved obligations, not round count or raw Finding count.

A Candidate may authorize only when all applicable conditions hold:

- every required discovery task is settled successfully
- required coverage is satisfied or explicitly resolved
- every raw report is durably present
- adjudication is complete
- unadjudicated raw claims = 0
- unresolved Problem HIGH = 0
- unresolved Problem MID = 0
- every Problem LOW has a traceable disposition and the current completion objective still holds
- every Improvement has a traceable non-blocking disposition
- no unresolved HUMAN decision required for this Candidate
- required post-repair reverification is complete
- latest Repair Coverage Check is complete when a repair occurred
- no unresolved repair-induced Problem remains
- no required STRATEGY_CHANGE remains unperformed
- all Evidence used for authorization is current under its dependency contract

Therefore:

~~~
new findings = 0
~~~

is neither necessary nor sufficient.

The semantic target is:

~~~
unresolved blocking review obligations = 0
and required review coverage/evidence is current
~~~

### 12.19 LOW and Improvement disposition

Under H-1/H-4:

- Problem LOW does not automatically create Work.
- Improvement HIGH/MID/LOW does not automatically create Work.
- none of them block merely because of severity/category if the current objective still holds and no requirement decision is missing.

Allowed dispositions include:

- repaired_current_cycle
- retained_history_only
- future_work_candidate
- no_action_after_adjudication

A future Work is created only when clearly valuable under normal Workline ownership/progression rules.

P4 itself does not invent a LOW scheduler or Project-wide maintenance queue.

P5/RB4 owns durable long-lived trace/history and any later workization provenance.

### 12.20 Verification-only Integration

P4 freezes:

~~~
verification-only
=
no persistent mutation to Project domain state
AND
no persistent mutation to undeclared external/nested state
~~~

Integration Evidence adapters declare a side-effect contract.

Preferred verification uses read-only/frozen or disposable resources, such as:

- frozen Candidate filesystem
- disposable DB/schema
- temporary build directory
- isolated container/worktree
- disposable service fixture
- explicitly allowed Review runtime/evidence area

Persistent external mutation may support PASS only when isolation/rollback/disposability is mechanically guaranteed and verified by the adapter contract.

Nested repositories/submodules are separate state. A gitlink identity does not authorize mutation of the nested working tree.

If Integration performs undeclared persistent mutation:

~~~
Integration cannot PASS
~~~

If Integration reveals a required domain/product repair:

~~~
create/use a normal fix Work under existing progression ownership
-> complete that Work normally
-> Formal Review as required
-> rerun Integration
~~~

Integration does not become a hidden repair executor or lifecycle owner.

### 12.21 Versioning and in-flight compatibility

P4 is a new versioned Review contract/policy.

Do not mutate P2/P3 v1 policy meaning in place.

Requirements:

- new invocations use a versioned P4-capable contract/policy identity;
- already-pending P2/P3 v1 Runs resume under their exact stored v1 contract/policy;
- old Candidate/TaskInput/Gate/Receipt bytes are never rewritten;
- a Receipt remains interpreted by the policy/version it actually binds;
- a v1 Run is never silently upgraded into a P4 repair Run;
- operation_contract/lifecycle markers already defined by P3 are not reinterpreted by policy version alone;
- legacy non-Review operations remain unchanged.

The exact identifier strings may use the existing review-v1 family with a new contract/policy version, but they must be distinct durable identities. Compatibility is by explicit version dispatch, never shape inference.

### 12.22 Minimum P4 canonical additions

P4 may extend the closed canonical Review namespace only through explicitly versioned record kinds.

Minimum new logical records:

~~~
reports/<result_digest>.yaml
adjudications/<review_run_id>.yaml
repair-batches/<repair_batch_id>.yaml
repair-results/<repair_batch_id>.yaml
~~~

Every new record is:

- immutable create-only
- strict-schema
- canonical-byte round-tripped
- clone-safe
- validated whether referenced or orphaned
- included in checkout-capability/path-safety proof
- never lifecycle truth

P5 may add long-lived summaries/indexing/history around these records but must not retroactively change their P4 execution meaning.

### 12.23 P4 implementation/recovery tests

At minimum cover:

- raw report persists before runtime loss and adjudication can resume
- adjudicator launch never occurs before accepted TaskInput persistence
- unsupported claim creates no repair obligation
- requirement ambiguity becomes HUMAN, not guessed Problem/Improvement
- Problem HIGH/MID blocks
- Problem LOW non-blocks only while objective still holds
- Improvement HIGH/MID/LOW remains non-blocking under H-4
- no automatic Work is created for LOW/Improvement
- duplicate raw claims merge only when repair identity matches
- one Candidate generation creates at most one Repair Batch
- all blocking Problems for that Candidate are represented in that batch
- repair launch is durable/replay-safe
- successful repair freezes a new Candidate/new Run
- old Run candidate_hash never changes
- current-cycle recovery survives runtime cleanup
- incomplete/ambiguous run linkage fails closed
- unknown Evidence completeness forces reacquisition
- complete Evidence reuse requires unchanged identities
- A is not inferred as B/C by timing
- B/C requires explicit causal linkage
- second supported same-surface B/C triggers STRATEGY_CHANGE
- operational tool failures do not increment semantic recurrence
- Repair Coverage unknown does not converge
- Integration external/nested side-effect violations cannot PASS
- normal fix Work + reintegration does not let Review own progression
- v1 pending Runs remain resumable under v1
- new P4 Run cannot be mistaken for a v1 fixed-shape Run

### 12.24 P4 HUMAN status

No new Human policy decision is required to freeze P4.

H-1 through H-4 already decide the previously open BL-004 policy questions.

HUMAN remains a runtime adjudication outcome only when a concrete Finding requires a product/spec/requirement decision.

RB3 is DESIGN_READY when RB3-C1 and this P4 contract are both reflected here and their implementation briefs/test matrices are prepared.


## 13. RB4 — P5 / BL-005 front — durable Review history

RB4 provides clone/runtime-cleanup-safe Review history, causality and traceability without making history a second source of lifecycle truth.

It closes the Review-history half of BL-005. Phase/Roadmap achievement evidence is completed in RB5.

### 13.1 Source-of-truth rule

P5 does not copy P1-P4 facts into a second independent truth store.

The authoritative execution facts remain the immutable P1-P4 records:

- Candidate snapshots
- TaskInputs
- Gate generations
- Receipts
- Consumptions
- Supersessions
- P4 discovery reports
- P4 adjudications
- P4 Repair Batches
- P4 Repair Results
- activation and existing operation/lifecycle records

P5 history is an append-only, validated projection/reference layer over those immutable facts plus genuinely new later facts such as cross-run recurrence or downstream escape.

If a P5 summary disagrees with the source record it summarizes:

~~~
validation failure
not "latest value wins"
~~~

Review history never drives ProjectView/state.py progression.

### 13.2 History purpose

Durable history exists only for:

- recovery explanation
- audit
- recurrence detection
- repair causality
- LOW/Improvement traceability
- optional future Work provenance
- HUMAN Decision Evidence
- later P6/P7 learning/promotion evidence
- RB5 achievement evidence references

It is not:

- lifecycle truth
- a scheduler
- a queue
- a second Roadmap
- an automatic Work generator
- raw AI memory

### 13.3 Minimum history layout

P5 adds a versioned history namespace inside canonical Review storage:

~~~
.workline/review/history/
  runs/<review_run_id>.yaml
  findings/<finding_id>.yaml
  repairs/<repair_batch_id>.yaml
  relations/<relation_id>.yaml
  human-decisions/<decision_id>.yaml
~~~

These records are immutable create-only.

P5 does not create a mutable "current history state" file.

Indexes/caches may later be generated for performance, but they are derived/rebuildable and never outrank the immutable facts above.

### 13.4 Run summary

A Run summary exists for each P5-capable Review Run once that Run reaches a durable disposition relevant to the current Review cycle.

It records only compact structured facts, including at least:

- review_run_id
- review_kind
- target_identity
- operation_identity
- candidate_hash
- candidate_generation where P4 applies
- review_context_hash
- effective_policy_hash
- evidence_digest
- coverage_digest
- terminal/latest gate generation and digest
- adjudication reference/digest where P4 applies
- finding_ids
- repair_batch_id if this Run entered repair
- receipt_id if authorized
- Consumption reference if consumed
- durable disposition

Allowed disposition vocabulary must distinguish at least:

~~~
authorized
repaired_to_next_candidate
human_wait
not_authorized
invalidated
set_aside
consumed
historical_escape
~~~

The summary does not reproduce Candidate bytes, report prose or Gate records.

It references them by stable identity/digest.

### 13.5 Finding summary

A Finding summary is generated only from one canonical P4 adjudication Finding.

It contains at least:

- finding_id
- source review_run_id
- candidate_hash
- category: Problem | Improvement
- severity: HIGH | MID | LOW
- semantic_surface
- public-safe short summary
- current-cycle disposition
- A/B/C relationship from P4 when present
- source adjudication digest
- source report digests
- optional related repair_batch_id
- later relation IDs as append-only relation references, not mutable fields

The summary's category/severity/disposition must validate exactly against the source adjudication.

A Finding summary never upgrades a dismissed/unsupported/HUMAN raw claim into a Finding.

HUMAN claims use Human Decision Evidence and their adjudication source; they are not disguised as Problem/Improvement Findings.

### 13.6 Repair summary

A Repair summary is generated from one P4 Repair Batch + Repair Result.

It contains at least:

- repair_batch_id
- source review_run_id
- source candidate_hash
- result candidate_hash
- finding_ids
- semantic surfaces
- selected strategy
- impact class
- Repair Coverage Check digest/result
- Evidence reuse/invalidation summary
- repair executor identity/version
- durable result/disposition
- source Repair Batch digest
- source Repair Result digest

The summary never claims causality merely because a repair and later Finding are adjacent in time.

### 13.7 Durable causal material

For later causal re-evaluation, preserve references/digests sufficient to recover the entire repair-relevant owned delta, not only the initially suspected site.

At minimum retain or reference:

- source/result Candidate hashes
- complete operation-owned touched delta before/after
- impact-analysis affected surfaces
- generated artifacts needed for causal re-evaluation where practical
- external-state Evidence/fingerprints when safely reconstructible
- supporting Evidence references
- Repair Coverage Check
- relevant policy/context identities

Causal status is one of:

~~~
supported
unresolved
insufficient_evidence
~~~

Only supported causality may be counted as a confirmed repair-induced C relationship or used as positive causal evidence for later learning/promotion.

Unknown is preserved as unknown.

Do not force C when evidence is insufficient.

### 13.8 Cross-run relation records

P4 owns same-current-cycle A/B/C.

P5 adds later/cross-run relationships without rewriting old Findings.

A relation record has a stable relation_id and records at least:

- relation type
- source identity
- target identity
- semantic_surface
- causal/relationship status
- supporting evidence digests
- public-safe rationale summary

Minimum relation types:

~~~
cross_run_recurrence
repair_induced
downstream_escape
future_work_link
~~~

For cross_run_recurrence and repair_induced:

- equality of code/message alone is not proof;
- semantic responsibility and evidence are required;
- status may remain unresolved/insufficient_evidence;
- only supported relations feed confirmed recurrence/causality metrics.

A later relation never edits either endpoint record.

### 13.9 Downstream escape

A defect first discovered after the prior lifecycle transition is completed is a downstream/historical escape.

P5 records an immutable relation from the later supported Finding to the prior Run/Finding/Repair evidence when that link is supportable.

It does not:

- reopen completed lifecycle state
- rewrite the prior Receipt/Consumption
- pretend the later Finding participated in the earlier authorization
- retroactively change an old verdict

The later problem is handled through normal current Workline operations.

### 13.10 LOW and Improvement traceability

H-1/H-4 supersede the old automatic LOW queue design.

P5 does not create a Project-wide LOW queue.

P5 does not automatically create Work from:

- Problem LOW
- Improvement HIGH
- Improvement MID
- Improvement LOW

Every non-blocking Finding still has a durable disposition.

Possible dispositions include:

- repaired_current_cycle
- retained_history_only
- future_work_candidate
- no_action_after_adjudication

If a future Work is later created because it is clearly valuable, it is a normal Work under the existing operation/progression owner.

P5 then appends a future_work_link relation:

~~~
finding_id -> work_id
~~~

That provenance link does not add the Work to the originating Phase/Roadmap completion set and does not create reverse completion dependency.

Work selection remains existing Workline progression; P5 invents no maintenance scheduler.

### 13.11 HUMAN Decision Evidence

When a concrete Review outcome reaches HUMAN and the Human actually makes the required decision, preserve a compact Human Decision Evidence record.

It contains at least:

- decision_id
- affected review_run_id / candidate_hash
- affected adjudication entry/finding references
- public-safe decision question summary
- public-safe Human decision summary
- canonical requirement/authority identity affected by the decision, if any
- resulting action class
- source/effect digests needed to prove what changed

Human Decision Evidence is evidence that a Human decision occurred.

It is not itself a substitute for the canonical requirement/specification/authority that the Human changed or confirmed.

Do not persist the conversation transcript, chain-of-thought, private deliberation or unnecessary personal information.

### 13.12 H-3 sanitation boundary

Every P5 history record is structured, sanitized and public-safe.

Never persist in history:

- chain-of-thought
- hidden reasoning
- raw model transcript
- raw chat transcript
- secrets or credentials
- unnecessary personal information
- unnecessary absolute/local filesystem paths
- unnecessary machine/user identifiers
- private/local details that are not required to understand the Review fact

Prefer:

- Workline stable IDs
- repository-relative identities when needed
- schema/version identities
- hashes/digests
- short public-safe semantic summaries
- explicit status vocabularies

P3/P4 reconstruction material required to reproduce an exact Candidate is not deleted or weakened by this rule.

Operational reconstruction records and human/audit history have different responsibilities.

### 13.13 P4 discovery-report sanitation amendment

P4's canonical report record is the **sanitized unadjudicated discovery report**.

The unsanitized external model/tool return is ephemeral and is never durable authority.

If a return contains H-3-prohibited material:

~~~
do not persist it as-is
do not settle its digest as the canonical report
-> obtain/construct a semantically equivalent H-3-safe structured report
   through the versioned reviewer protocol
or
-> leave the task unresolved/failed under that protocol
~~~

Sanitization must not silently change the substantive claim.

### 13.14 Achievement-evidence handoff to RB5

RB4 defines the durable evidence/history substrate but does not decide Phase/Roadmap achievement.

RB5 will bind automatic Phase/Roadmap achievement to evidence that references this durable substrate.

RB4 therefore exposes stable references for RB5 to cite:

- Review Run
- Receipt/Consumption
- relevant Finding dispositions
- unresolved-obligation status
- required Evidence/coverage identity
- HUMAN Decision Evidence where applicable

RB5 decides the exact achievement record/event binding.

### 13.15 Backfill and compatibility

No historical backfill is required.

Existing Projects/Runs created before P5 remain valid under their original contracts.

P5-capable contracts/policies require history for new P5-capable Runs only.

Do not reconstruct old missing rationale by guessing from:

- current code
- later commits
- current status
- memory/chat history

Where old evidence is absent, it remains absent.

### 13.16 History creation boundary

For P5-capable Review flows, required history facts must become durable before the operation passes the boundary that would make their later reconstruction impossible.

Prefer creating a summary in the same recoverable generation/operation transition that makes its source fact durable, or in an immediately bound recoverable history mutation whose identity is fixed before the source transition is considered complete.

At minimum:

- discovery report durability precedes adjudication
- Finding summary durability follows/binds the immutable adjudication
- Repair summary durability follows/binds Repair Result before next-cycle history is considered complete
- authorized Run summary is durable before its authorization is consumed/operation returns terminal success
- Human Decision Evidence is durable before a Human-dependent Review cycle is resumed under that decision

A crash must yield either:

- a recoverable pending history write with exact source identity; or
- no claim that the P5 history obligation was completed

Never infer completion from a later lifecycle event alone.

### 13.17 Validation

Validation checks every P5 history record independently and against its immutable source.

At minimum detect:

- unknown schema/version
- malformed stable ID
- source record missing
- source digest mismatch
- category/severity/disposition disagreement
- repair source/result mismatch
- relation endpoint missing
- relation type/status invalid
- supported causality with missing supporting evidence
- duplicate logical identity
- Human Decision Evidence pointing at no affected Review fact
- future_work_link pointing at a non-existent/nonmatching Work

A broken history relation does not become lifecycle truth.

For a P5-capable Run whose contract requires a history fact before authorization/consumption, missing required history blocks that new transition until recovered.

### 13.18 Learning boundary

RB4/P5 records evidence.

It does not automatically evolve policy.

Generated metrics may later include:

- Finding yield over relevant opportunities
- downstream escape rate
- B recurrence rate
- C repair-induced rate
- redundant-review overlap
- review/test cost where safely available

Aggregates are never the raw source of truth and must remain traceable to Run/Finding/Repair/history records.

RB6/P6 owns Project-local adaptive policy.

RB7/P7 owns Global promotion.

### 13.19 RB4 tests

At minimum cover:

- Run/Finding/Repair summary round-trip and strict schema
- summary/source mismatch fails validation
- runtime cleanup does not remove canonical history
- fresh clone reconstructs P5 history references
- P4 raw/sanitized discovery report distinction
- H-3-prohibited report cannot be persisted as canonical history/report
- no chain-of-thought/transcript field exists in schema
- no automatic Work from LOW/Improvement
- future_work_link can be added later without rewriting Finding
- future Work does not become originating Phase/Roadmap dependency
- supported/unresolved/insufficient causal status round-trip
- unresolved causality is not counted as C
- cross-run recurrence requires explicit relation/evidence
- downstream escape does not reopen prior lifecycle
- Human Decision Evidence does not replace canonical requirement authority
- no backfill is attempted for pre-P5 Runs
- history write interruption is replay-safe
- P5-capable authorization cannot step over a required missing history fact
- old v1/P3/P4-only Runs remain valid without P5 summaries

### 13.20 RB4 HUMAN status

No new Human policy decision is required to freeze RB4.

H-1/H-3/H-4 already resolve the prior LOW/history/privacy choices.

Conditional Human escalation remains only if implementation would require deleting/weaking P1-P4 reconstruction capability, which this design explicitly forbids.

RB4 is DESIGN_READY when this contract and its implementation brief/test matrix are prepared.


## 14. RB5 — BL-003 + BL-005 back — Phase Review and Achievement Evidence

RB5 connects Phase-wide verification to the existing Phase integration Work and makes successful Phase/Roadmap achievement evidence durable.

It preserves existing ownership:

~~~
START
  -> Work execution / integration ownership / Work lifecycle

Roadmap
  -> Phase planning / continuation / Roadmap achievement

state.py
  -> generated Work / Phase / Roadmap state

Review
  -> verification / adjudication / authorization
~~~

Review does not become a second Phase lifecycle controller.

### 14.1 Phase completion remains generated

Phase completion remains generated state, not a lifecycle event.

RB5 does not add:

- phase_completed
- phase_achieved
- review_passed lifecycle state
- mutable Phase status

The existing mechanical shape remains: Phase is active; effective current-plan Works are complete; integration exists; no unfinished effective integration remains; structural human_confirmation is complete when present; relation/integration replanning is complete; and structural validation passes.

RB5 strengthens what a **new review-aware integration Work may count as completed**, and adds a mechanical coverage requirement for review-aware integration. Phase state remains derived from canonical Work metadata, events and relations rather than Review metadata.

### 14.2 Compatibility marker

No historical backfill is required.

Existing phase_integration_check Works without an RB5 marker retain legacy completion semantics.

Every integration Work created by the RB5-capable Roadmap/START path carries:

~~~
phase_review_contract: phase-integration-review-v1
~~~

This metadata is valid only for work_kind=phase_integration_check. Unknown/non-supported values fail validation.

A Phase containing no effective review-aware integration remains legacy-compatible.

An existing Phase may transition naturally to reviewed integration semantics when a later canonical reintegration is created. No existing Work file is edited merely to opt it in.

### 14.3 Registration ownership

Initial integration meaning remains owned by Roadmap.

Runtime reintegration meaning remains owned by START.

CREATE remains registration core only.

Roadmap/START decide that a newly created integration uses phase-integration-review-v1; CREATE persists the already-decided marker.

No new Project-facing Skill is introduced.

### 14.4 Phase Integration Review kind

Add a dedicated Review kind:

~~~
phase-integration-v1
~~~

It is the execution/verification gate for a review-aware phase_integration_check Work.

It is distinct from ordinary Work Formal Review, Phase Design Review, Roadmap Review and human_confirmation.

A review-aware integration Work is verification/evidence-only. It does not own domain-output repair.

### 14.5 Phase Integration Candidate

The Candidate freezes the exact committed Phase basis being integrated.

At minimum it binds:

- Phase ID / Roadmap ID
- Phase desired state
- integration Work ID / desired state / phase_review_contract
- exact committed Git base and branch identity
- exact effective current-plan Work IDs
- each relevant Work's kind, desired-state identity and terminal/lifecycle identity
- exact relevant requires_completion graph
- Related/authority inputs needed for Phase-wide verification
- available Work Review/achievement evidence references
- structural validation identity/result
- Review Context
- Effective Policy
- versioned integration-coverage classification

Candidate material is clone-safe and reconstructible under the P1-P4 rules.

The Candidate is evidence input, never a mutable Phase-status record.

### 14.6 Integration coverage classes

For a candidate integration I, every effective current-plan Work is classified into exactly one of:

~~~
pre_integration
  result/state must be integrated before I may complete

current_integration
  I itself

post_integration_confirmation
  structural human_confirmation explicitly downstream of I by requires_completion

historical_integration
  older completed phase_integration_check superseded by current integration purpose

invalid_uncovered
  anything fitting none of the permitted classes
~~~

Classification is mechanical from Work kinds and canonical relations.

A normal/fix Work is never post_integration merely by timestamp/order.

A human_confirmation is post_integration only when canonical requires_completion structure makes it downstream of I.

invalid_uncovered is a structural defect and prevents authorization.

### 14.7 Complete pre-integration coverage

For phase-integration-review-v1, every effective non-integration Work that is not an explicitly downstream structural human_confirmation must be represented as a pre_integration responsibility.

Use direct requires_completion edges to make the coverage auditable.

Initial Phase expansion already creates each normal Work -> integration.

For a review-aware reintegration, START creates the complete required predecessor set for that integration, not only the newest fix Work.

Older completed integrations need not be predecessors of the new integration. They are historical_integration and may be inspected through evidence/history.

### 14.8 Generated completion for review-aware Phase

For a Phase whose current integration path is review-aware, generated Phase completion additionally requires at least one **completed covering integration** for the current effective plan.

A covering integration satisfies all:

- work_kind=phase_integration_check;
- phase_review_contract=phase-integration-review-v1;
- it has ordinary work_completed lifecycle truth;
- its direct pre_integration coverage covers the current review-relevant effective Work set;
- no invalid_uncovered Work exists;
- any explicitly downstream structural human_confirmation required by the structure is complete before Phase completion;
- structural validation passes.

This is derived from canonical Work metadata/events/relations. state.py does not read a Receipt/history record as lifecycle truth.

Legacy-only Phases keep the legacy predicate.

### 14.9 Late Work / plan change after integration

Do not refuse legitimate Work merely because a prior integration completed.

When a Workline-owned operation adds/reactivates review-relevant Work after the latest covering integration:

~~~
unfinished integration exists
-> add the required dependency/coverage to that integration

no unfinished integration exists and reintegration is required
-> START creates a new review-aware integration
-> create complete predecessor coverage

two or more unfinished integrations would exist
-> existing structural STOP
~~~

For review-aware Phases, adding a new effective normal/fix Work after a completed covering integration deterministically requires reintegration.

Until reintegration completes, the Phase is not current-complete under reviewed semantics and status discloses stale/missing integration coverage.

An external/manual structure mutation is never auto-repaired; validation reports it.

### 14.10 Verification-only execution

Preferred execution:

~~~
freeze Phase Integration Candidate
-> materialize/read frozen Candidate through read-only/disposable verification
-> run integration checks
-> persist only Review/evidence records
~~~

No domain artifact mutation is allowed under this lightweight gate.

If the verifier cannot operate read-only, the P4 side-effect contract applies: isolated/disposable external state or positive before/after proof that no undeclared persistent mutation occurred.

result_paths=() alone is not proof of read-only behavior.

Undeclared Project/external/nested mutation prevents PASS.

### 14.11 Review scope

Phase Integration Review evaluates what individual Work reviews cannot prove alone:

- cross-Work integration/coherence
- Phase desired-state achievement
- current authority/ownership consistency
- lifecycle/relation consistency
- exact integration coverage
- unresolved Phase-wide dependency/verification gaps
- missing responsibility not owned by any effective Work/integration/confirmation
- evidence/verification sufficiency
- whether genuine Human confirmation is part of the Phase success condition

It does not rerun full Work Review merely because the Phase is ending.

Valid P4 Evidence may be reused only under positive completeness/reuse proof.

### 14.12 Phase desired-state outcome

The integration adjudication records one outcome:

~~~
objectively_satisfied
human_confirmation_required
not_satisfied
desired_state_change_required
~~~

objectively_satisfied means the decided Phase objective is positively satisfied and no Human-owned judgment is required.

human_confirmation_required means the already-decided objective genuinely includes a Human-owned judgment.

not_satisfied means the objective is decided and unmet; blocking Problem/repair handling applies.

desired_state_change_required means passing would require changing the objective itself; route HUMAN.

The outcome never creates lifecycle state by itself.

### 14.13 Dynamic human_confirmation discovered at integration

Existing Workline behavior allows integration-time evidence to reveal that structural human_confirmation is needed even when Phase design did not predict it.

If the Review concludes human_confirmation_required and no valid downstream confirmation exists:

~~~
do not seal/consume an integration completion authorization yet
-> START creates the normal human_confirmation Work/relation
   through existing CREATE ownership
-> freeze a new Phase Integration Candidate/Run containing that structure
-> re-evaluate
~~~

Review never creates the Work directly.

Once reviewed structure contains the required downstream confirmation, the integration may complete; Phase remains incomplete until that confirmation completes.

### 14.14 Blocking Phase Integration Finding

Problem HIGH/MID or not_satisfied prevents integration work_completed.

Domain repair follows:

~~~
Integration Finding
-> normal fix Work through START/CREATE
-> fix Work executes under normal Work semantics
-> Work Formal Review where required
-> retry same unfinished integration when it remains the valid target
-> new Phase Integration Candidate / Review Run
~~~

Do not create a second unfinished integration merely because the current one found a defect.

If the old integration already completed and a later confirmation/fix requires reintegration, START follows the normal no-unfinished-integration rule and creates a new integration.

Integration Review never patches domain artifacts itself.

### 14.15 P4 semantics apply

phase-integration-v1 uses P4 for:

- durable H-3-safe discovery reports
- adjudication
- Problem/Improvement/HUMAN
- coverage
- Evidence completeness
- A/B/C causality where repair cycles apply
- strategy-change
- verification-only side-effect contract

However, Phase Integration domain fixes intentionally leave the lightweight Review repair executor and use normal fix Work ownership.

Any domain repair produces a new Phase Integration Candidate/Run.

### 14.16 Integration terminal gate

START may record work_completed for a review-aware integration only when all hold:

- ordinary Work completion precheck passes;
- Phase Integration Candidate is current;
- required Review tasks/adjudication complete;
- no blocking Problem HIGH/MID;
- Problem LOW/Improvement dispositions satisfy H-1/H-4;
- Phase outcome is objectively_satisfied, or an already-modeled downstream human_confirmation is required;
- Review coverage/evidence is current;
- one valid Receipt authorizes this exact Candidate/integration terminal stage;
- no invalidation/Supersession/Consumption conflict exists;
- verification-only side-effect contract passes.

The terminal mutation consumes that exact Receipt while recording the integration Work's ordinary work_completed transition.

Receipt/Consumption never replaces work_completed lifecycle truth.

### 14.17 Integration completion evidence

The integration terminal path makes required P5 history/evidence durable before terminal success returns.

The Run summary/adjudication must be sufficient to explain:

- exact Candidate/basis checked
- Phase-goal outcome
- coverage
- Finding dispositions
- Receipt/Consumption
- Evidence identity

No raw transcript/CoT is stored.

### 14.18 Achievement Evidence namespace

Extend RB4 history with:

~~~
.workline/review/history/achievements/<achievement_evidence_id>.yaml
~~~

A versioned schema supports at least:

~~~
kind: phase_completion
kind: roadmap_achievement
~~~

These records are evidence/audit facts. They are not lifecycle truth.

### 14.19 Phase Achievement Evidence

For a review-aware Phase, whichever canonical operation first makes the Phase generated-complete must make phase_completion evidence durable in the same recoverable logical transition before Roadmap progression may treat that completion as closed.

It binds at least:

- achievement_evidence_id
- kind=phase_completion
- Phase/Roadmap IDs
- Phase desired-state digest
- exact effective current-plan Work set / basis digest
- covering integration Work ID
- Phase Integration Run/Receipt/Consumption refs
- Phase-goal outcome
- completed downstream human_confirmation evidence where applicable
- structural validation digest/result
- relevant Work Review/history refs
- no-blocking-obligation source digests
- evaluator/reviewer identities/versions
- H-3-safe rationale
- operation/mutation identity that caused final generated completion

state.py does not read this record to decide lifecycle state.

### 14.20 Atomic Phase evidence obligation

A review-aware Phase may become complete because of:

- integration work_completed;
- downstream human_confirmation work_completed;
- canonical replan/terminal operation that changes effective structure into a complete reviewed basis.

Whichever owner performs that transition includes/recoverably binds the evidence obligation in that operation.

The evidence binds a projected canonical basis digest rather than the SHA of the commit containing itself, avoiding self-reference.

Before final success/progression:

~~~
reload committed canonical state
-> recompute Phase basis digest
-> require equality with evidence
~~~

A crash may leave a recoverable pending operation, but no caller advances Roadmap from a P5-capable completion whose evidence obligation is unclosed.

No post-loss evidence is fabricated from guess/memory.

### 14.21 Automatic Phase objective decision

H-2 applies.

The Phase outcome may be decided automatically when:

- desired state is clear;
- required integration evidence exists;
- required checks/coverage pass;
- no blocking obligation remains;
- no Human-owned judgment is part of the objective;
- no new requirement meaning is invented.

Then objectively_satisfied needs no extra Human confirmation.

### 14.22 Roadmap achievement keeps existing lifecycle semantics

Roadmap achievement remains:

~~~
all active Phases complete
-> explicitly evaluate Roadmap desired state

objectively satisfied -> roadmap_achieved
Human-owned judgment required -> Human
decided objective unmet -> add Phase/replan without weakening desired state
desired state itself must change -> HUMAN
~~~

No second Roadmap completion state is added.

roadmap_achieved remains lifecycle truth.

### 14.23 Automatic Roadmap achievement under H-2

The semantic evaluation may be autonomous when:

- every active Phase is generated-complete;
- every P5-capable completed Phase has valid achievement evidence;
- structural validation passes;
- Roadmap desired state is clear;
- bound evidence positively supports it;
- no blocking Review/achievement obligation remains;
- no unresolved HUMAN decision remains;
- no new desired-state meaning is invented.

Human is required only where the objective genuinely contains Human-owned judgment or requirement change.

### 14.24 Roadmap Achievement Evidence

Before recording roadmap_achieved, reserve/write roadmap_achievement evidence in the same recoverable Roadmap achievement mutation.

It binds at least:

- achievement_evidence_id
- kind=roadmap_achievement
- Roadmap ID
- Roadmap desired-state digest
- exact active Phase set
- Phase achievement refs where P5-capable
- explicit legacy Phase completion facts where compatibility requires them
- relevant Review/verification refs
- structural validation digest/result
- semantic judgment=achieved
- evaluator identity/version
- H-3-safe rationale
- reserved roadmap_achieved event ID
- mutation/operation identity

Evidence and event are one logical decision.

The existing event schema is unchanged; evidence references the reserved event ID.

### 14.25 Roadmap achievement ordering

For achieved:

~~~
freeze semantic evaluation/evidence basis
-> Project execution lock
-> recheck canonical structural preconditions
-> reserve event + evidence IDs
-> record one recoverable logical stage containing
     achievement evidence
     + roadmap_achieved event
-> apply
-> commit / exact publication under existing Git rules
-> read back event/evidence/basis agreement
-> return achieved
~~~

The lock still does not claim to atomically snapshot arbitrary external/domain evidence.

Evidence identities are frozen; canonical structure is rechecked under lock.

If a material evidence identity changed and the judgement is no longer supported, do not record achieved; re-evaluate.

### 14.26 Non-achieved Roadmap evaluations

Read-only results:

- not_ready
- not_achieved
- human_confirmation_required
- desired_state_change_required

do not create an achievement event merely to persist diagnostics.

If Human actually makes a required decision, RB4 Human Decision Evidence applies.

If replan/additional Phase follows, that normal operation carries its own durable authority/evidence.

### 14.27 Legacy compatibility

No backfill.

Legacy integrations lacking phase_review_contract keep legacy semantics.

Already-completed legacy Phases remain valid.

Already-pending legacy START/integration mutations resume under stored semantics.

New RB5-capable integration cannot silently fall back to legacy completion.

Roadmap achievement may include legacy-complete Phases in its evidence basis, explicitly marked legacy instead of inventing missing Phase Review history.

Review-v1 is not mandated for every ordinary Work.

### 14.28 RB1 status handoff

RB5 adds read-only diagnostics.

Phase:

- completion mode: legacy | phase-integration-review-v1
- generated complete/incomplete
- covering integration ID or missing/stale
- latest Phase Integration Review disposition
- Phase Achievement Evidence ID/status
- downstream human_confirmation status

Roadmap:

- all-active-Phases-complete
- achievement evidence readiness
- achieved event/evidence binding
- HUMAN-required/objective-unmet status where applicable

No diagnostic read mutates state.

### 14.29 Tests

At minimum cover:

**Compatibility/state**
- Phase completion remains generated and no Phase completion event is added
- legacy integration/Phase behavior unchanged
- completed legacy Phase remains valid
- no backfill
- new integration carries supported marker
- unsupported marker fails
- ordinary Works are not globally forced into review-v1

**Coverage/reintegration**
- initial reviewed integration covers all required predecessors
- Work added before unfinished integration gains dependency/coverage
- Work added after completed integration is allowed and creates/requires reintegration
- old integration cannot cover expanded effective plan
- uncovered normal Work prevents reviewed completion
- downstream human_confirmation classified separately
- two unfinished integrations remain invalid

**Integration Review**
- Candidate reconstructs exact Phase/effective Work/relation basis
- verifier is read-only/disposable
- undeclared mutation cannot PASS
- cross-Work/missing-responsibility Finding blocks as required
- not_satisfied does not complete integration
- desired_state_change_required routes HUMAN
- objectively_satisfied may authorize automatically
- newly required human_confirmation causes START structure change + new Candidate/Review
- domain fix uses normal fix Work and reruns integration
- Receipt consumption and work_completed are bound
- Review metadata is not lifecycle truth

**Late/stale**
- late Work is not refused merely to preserve old integration
- canonical plan change creates/requires reintegration
- stale/missing coverage is visible
- old Review cannot authorize expanded plan by timestamp/ID

**Achievement**
- Phase evidence is durable for reviewed completion
- basis digest round-trips against committed canonical state
- crash/resume cannot advance Roadmap without closing evidence obligation
- roadmap_achieved event/evidence are one recoverable decision
- event schema unchanged
- automatic achievement works under H-2
- genuine Human judgement routes HUMAN
- unmet objective replans instead of weakening desired state
- legacy Phase appears as legacy evidence, never fake backfilled review

### 14.30 HUMAN status

No new Human design decision is required.

BL-003 originally left Phase completion judgement unresolved; H-2 now supplies the policy boundary while this design preserves generated Phase state and existing operation ownership.

RB5 does not refuse legitimate late Work, globally mandate ordinary Work review-v1, or backfill existing Phases.

If implementation would require one of those stronger behaviors, trigger the corresponding conditional HUMAN decision before changing that boundary.

RB5 is DESIGN_READY when this contract and its implementation brief/test matrix are prepared.


## 15. RB6 — BL-055 + P6 Project-local Adaptive Policy

RB6 has two connected but distinct responsibilities:

1. preserve Workline authority hygiene in established Projects so that local artifacts cannot silently become a second planning/execution/state authority;
2. allow a canonical Project-local Review Profile to adapt **how correctness is verified** without redefining correctness.

The P6 Profile is canonical by explicit Workline ownership. It is therefore not shadow authority.

### 15.1 Authority boundary retained

Runtime authority remains:

~~~
Workline root:
  registry.md
  + registry-routed canonical Skills
  + implementation/tests

Project:
  canonical .workline schemas/records
  + the exact Project bootstrap entry defined by ProjectSTART
  + Project/domain authorities only for responsibilities Workline does not own
~~~

Project-local documents may define product/domain requirements and may impose stricter Project-specific safety rules.

They do not become Workline operation/lifecycle/progression authority merely because they are newer, more detailed or explicitly named by a user/agent.

### 15.2 Shadow authority definition

A Project-local artifact is shadow authority only when it **claims or is used to replace/duplicate a responsibility already owned by canonical Workline authority**.

Workline-owned responsibility includes at least:

- Roadmap / Phase / Work planning state
- Work/Phase/Roadmap lifecycle or completion state
- current/next Workline progression
- Workline relation semantics
- Workline operation names/meaning
- Workline Review authorization state
- Workline Project routing/bootstrap semantics
- Workline Git/mutation ownership rules
- canonical Review Policy/Profile semantics

Examples of confirmed shadow-authority behavior:

~~~
a local tracker is treated as the authoritative current/next Work instead of .workline state

a local Skill invents "BACKLOG add" as a Workline operation and persists a parallel task state

a local automation decides Work/Phase completion outside the canonical operation owner

the Project bootstrap/router is redirected to a Project-local copy of Workline operation semantics

a document claims that its separate Roadmap/Work status overrides canonical Workline state
~~~

Not shadow authority merely by existence/name:

- README
- BACKLOG.md
- TODO.md
- STATUS.md
- design/spec documents
- product/domain Roadmaps that are clearly not Workline lifecycle authority
- ordinary domain configuration
- stricter Project-specific CONTRACT/safety rules
- a Project-local Skill/automation whose responsibility does not duplicate Workline
- generated reports/dashboards that explicitly remain derived/read-only

Filename and vocabulary alone never establish shadow authority.

### 15.3 Canonical routing prevents shadow operation invention

For an established Workline Project, the Project bootstrap continues to route through the canonical Project router.

When a request uses a noncanonical label such as:

~~~
"BACKLOGに追加"
"TODOを次タスクにする"
"このSTATUSを完了扱いにして"
~~~

the router/owning Skill resolves the **meaning**, not the filename or alleged operation name.

~~~
meaning maps uniquely to an existing canonical Workline responsibility
-> route to that canonical owner

no canonical Workline operation exists, but the request is plainly a domain/document edit
-> it may remain an ordinary Project artifact edit under that artifact's authority

it is ambiguous whether the user intends a Workline state/progression mutation
-> rules/human-confirmation

a tool/agent claims a non-existent Workline operation or attempts to substitute another authority
-> do not invent/fallback to it
-> report/STOP for that Workline operation
~~~

A request saying "add it to BACKLOG" does not make BACKLOG a Workline concept.

### 15.4 Project-local Skill and automation boundary

Existing `rules/human-confirmation` already governs addition of Project-local Skills/agent automation that expands executable capability or exposure.

RB6 does not add a second approval system.

A Project-local Skill/automation is allowed when its responsibility is distinct from Workline or when it calls canonical Workline operations rather than duplicating their semantics.

It is not allowed to become a second Workline owner by:

- persisting parallel Workline planning/execution state;
- copying canonical Workline Skills and then treating the copy as authority;
- bypassing Project router/operation ownership for Workline mutations;
- inventing new Workline lifecycle states/operations;
- treating its own local tracker as current Workline state.

Project-local capability may read canonical Workline state and produce advisory/derived output. Derived output must identify itself as derived and must not be routed as authority.

### 15.5 BL-055 detection classes

Shadow-authority detection is responsibility-based and fail-safe against false positives.

Read-only diagnostics classify evidence as:

~~~
none
  no shadow-authority evidence found

suspected
  an artifact appears to overlap a Workline-owned responsibility,
  but actual authority substitution cannot be proven

confirmed
  explicit routing/write/authority evidence shows a noncanonical artifact
  is being used as Workline authority
~~~

A filename/content keyword match alone can produce at most `suspected`, never `confirmed`.

Positive confirmation requires concrete evidence such as:

- bootstrap/router delegation to a noncanonical owner;
- explicit instruction that a noncanonical artifact overrides Workline state;
- a local Skill/automation whose declared/observed operation writes parallel Workline lifecycle/progression state;
- an actual noncanonical read/write path used to decide a Workline-owned state transition.

Semantic/model-based inspection may help produce an advisory suspicion but is never itself mutation authority.

### 15.6 Detection is advisory by default

RB6 does **not** make established Projects invalid merely because suspected/confirmed shadow authority exists outside canonical state.

Default behavior:

~~~
status/validate diagnostic
-> disclose shadow-authority evidence
-> identify canonical responsibility that owns the meaning
-> suggest canonical routing / manual retirement where appropriate
-> no automatic deletion/edit/migration
~~~

Canonical Workline operations continue to ignore the shadow source as authority and use their normal canonical inputs.

Existing mutation/write guards still block an unauthorized attempt to change canonical Workline state.

A confirmed external shadow artifact does not gain authority merely because Workline reports it.

No new refusal of ordinary Project operation is introduced by BL-055 alone.

If a future design needs an existing Project to become invalid/refused merely because of shadow-authority presence, that triggers the frozen conditional HUMAN boundary.

### 15.7 BL-011 boundary

BL-011 owns initial migration/retirement of legacy authority when converting a legacy Project.

BL-055 owns **post-establishment reintroduction prevention/detection**.

RB6 does not:

- rerun legacy migration automatically;
- delete or rewrite a discovered legacy/shadow artifact;
- change ProjectSTART;
- backfill existing Projects merely to install shadow-detection state.

A later Human-directed cleanup uses the normal owner of the affected artifact/state.

### 15.8 No ProjectSTART/backfill change for P6

The older learning memo anticipated ProjectSTART initialization of a Project-local Profile.

This Completion Sprint intentionally does not require that.

Frozen rule:

~~~
Project Profile absent
-> valid
-> Effective Policy = Global baseline + current change/risk context

first accepted local policy adaptation
-> project-policy-change lazily creates the canonical Profile
~~~

Therefore:

- no existing Project backfill is required;
- no ProjectSTART bootstrap/layout change is required by P6;
- absence of the Profile is not a validation warning/error;
- existing Projects retain current behavior until a P6 policy change is actually applied.

### 15.9 Read-only Global baseline representation

P6 defines one normalized, read-only logical representation of current Global Review policy.

It is produced by a canonical loader from current Workline-root runtime authority; P6 does not mutate Workline root.

Conceptually:

~~~
GlobalPolicyBaseline {
  contract/version
  global_policy_identity
  root_authority_digests
  strength/meta-rules
  policy surfaces and defaults
  allowed adaptive ranges
  loader/schema/default-semantics identity
}
~~~

Its canonical digest is the Global baseline identity used by Review Context and Project Profiles.

Before RB7 introduces any root policy mutation, the baseline may be **derived** from existing canonical Review policy/Skills/registry.

Derived does not mean weak: the canonical loader and source digests make the baseline exact and reproducible.

RB7 must preserve this loader/interface when it later introduces Global Policy Change.

### 15.10 Policy strength classes

The fixed baseline meta-rules classify each adaptable policy surface as:

~~~
mandatory
  Project policy cannot disable or lighten it

default
  Global standard
  Project may strengthen
  Project may lighten only under the stronger lightening contract

adaptive
  Project may strengthen/lighten inside an explicitly bounded allowed range
~~~

Classification and allowed ranges are fixed Global/meta-policy facts.

A Project Profile cannot reclassify a surface.

Unknown/unclassified surface is not adaptable.

### 15.11 Absolute non-adaptive surface

Project learning may change **how Workline verifies correctness**.

It may not change **what correctness means**.

Automatic Project Policy Change must not alter:

- Roadmap/Phase/Work semantics
- lifecycle/completion semantics
- H-1 through H-4 semantics
- Problem/Improvement meaning
- HIGH/MID/LOW meaning or blocking semantics
- HUMAN decision boundary
- product/user requirements
- canonical authority/routing rules
- Mutation/Git safety invariants
- non-negotiable security/destructive-operation rules
- Review-v1 authorization/Consumption correctness
- Project-local capability approval boundary

A candidate crossing this surface is not a Project Policy Change Candidate.

If the desired change itself is legitimate but changes a Human-owned requirement/authority boundary, route to HUMAN/normal canonical requirement change instead of learning it.

### 15.12 Canonical Project Profile

The canonical Project-local profile is:

~~~
.workline/review/policy/project-profile.yaml
~~~

Its absence means no local override.

The file is the current normalized Project-local policy state, not a free-form configuration file.

Minimum logical fields:

~~~
schema / version
profile_version
parent_profile_digest | null
global_baseline_digest
global_baseline_version
loader_semantics_identity
overrides[]
active_experiment_refs[]
~~~

Each override identifies:

- stable policy_surface_id
- Global strength class
- direction/effect within the allowed range
- exact normalized setting
- supporting policy_change_id

The loader rejects unknown fields/surfaces/settings rather than silently ignoring them.

`profile_version` increases only through the canonical Project Policy Change operation.

A rollback is a new higher version that restores/replaces settings; Git/history is never rewritten.

### 15.13 Effective Policy resolution

At the start of each P6-capable Review Run:

~~~
read exact GlobalPolicyBaseline
+ read exact Project Profile, or absent
+ current change/risk context
-> normalized Effective Policy
-> freeze effective_policy_hash in the Run
~~~

An in-progress Run never changes policy halfway through because the Global baseline or Project Profile later changes.

A later policy version applies only at the next safe Review Run boundary.

Profile/global compatibility is proven by the canonical loader.

If the Profile names a Global baseline it cannot be reconciled with under fixed compatibility rules:

~~~
do not guess/merge
-> no new Review Run under that Profile
-> policy maintenance/reconciliation path
~~~

RB7 owns compatibility/adoption when the Global policy itself changes.

### 15.14 Project Policy Change Candidate

A permanent/temporary local adaptation begins from RB4/P5 evidence, not raw run count.

A PolicyChangeCandidate binds at least:

- Project identity
- before Profile state/digest or explicit absence
- Global baseline identity/digest
- normalized proposed after Profile
- affected_policy_surface
- strength class
- direction: strengthen | lighten | temporary_guard | adjust | rollback
- supporting Run/Finding/Repair/relation IDs
- Relevant Opportunity definition/evidence
- expected effect
- validation plan
- measurement_contract
- observation_window
- success criteria
- rollback threshold
- environment/dependency identity
- overlap classification
- rollback unit

The Candidate contains exact normalized policy semantics, not an imperative patch script.

### 15.15 Single-event rule

One observation, one Finding, one PASS, or one no-finding run never creates a **permanent learned policy change**.

Permanent adaptation requires repeated relevant evidence and a reviewable trend.

There is no universal fixed count that defines truth.

The fixed meta-policy may define operating thresholds, but:

- denominator is Relevant Opportunity, not raw Review count;
- evidence quality/independence/causality matters;
- an unexercised surface does not count as a successful opportunity.

A serious supported escape may create an immediate `temporary_guard` when the guard only strengthens verification inside an already-allowed policy surface.

A temporary guard:

- cannot lighten policy;
- cannot change correctness/authority;
- is versioned and reversible;
- has explicit reevaluation/expiry criteria;
- does not become permanent without the normal repeated-evidence Policy Change path.

### 15.16 Strengthening contract

Permanent strengthening requires enough relevant evidence to support the pattern and exact affected policy surface.

No hard universal 3/5 count is semantic truth.

Strengthening is allowed only within the Global surface's declared adaptive range and still requires:

- PolicyChangeCandidate
- Policy Change Review
- exact persisted-policy proof
- observation after application
- rollback/adjust path

A stronger check that changes product/requirement meaning is not "strengthening" and is outside P6.

### 15.17 Lightening contract

Lightening has a materially stronger burden than strengthening.

Before activation, freeze:

- Relevant Opportunity denominator
- exact pre-change check/behavior being lightened
- replacement verification or reason coverage remains adequate
- independent shadow/holdout observation channel
- observation window
- success criteria
- escape/rollback threshold
- environment/dependency identity
- affected policy surface
- rollback unit

The changed policy cannot disable/weaken the channel used to evaluate whether that lightening was safe.

No-finding evidence counts only when the relevant surface was actually exercised.

If adequate independent measurement cannot remain active:

~~~
lightening is not authorized
~~~

### 15.18 Shadow/holdout execution semantics

Shadow/holdout verification is measurement, not a weaker correctness channel.

Selection itself is policy-driven; an unselected shadow task has no completion effect.

Once a shadow/holdout task is durably accepted before the Review cutoff:

~~~
it must settle before that authorization is consumed
~~~

This preserves P3/P4 stale-authorization ordering.

Disposition of a supported result known before terminal completion:

~~~
Problem HIGH/MID
-> promote to normal current Review blocking obligation

Problem LOW
-> H-1/H-4 non-blocking disposition if objective still holds

Improvement HIGH/MID/LOW
-> non-blocking disposition under H-4

requirement meaning unclear
-> HUMAN
~~~

No Finding:

~~~
measurement evidence only
~~~

A relevant result first becoming known after durable terminal completion:

~~~
historical/downstream escape
-> no retroactive lifecycle rewrite
-> durable RB4 relation/evidence
-> feed current repair / temporary guard / experiment retain-or-rollback evaluation as applicable
~~~

Shadow mode never authorizes ignoring a supported defect merely because the check was "only experimental."

### 15.19 Policy Change Review

Policy Change itself is reviewed under:

- the **pre-change** Effective Policy; and
- fixed non-adaptive policy meta-rules.

The candidate policy cannot weaken the rules used to authorize its own change.

Policy Change Review verifies at least:

- evidence provenance and Relevant Opportunity basis
- affected surface identity
- strength class / allowed adaptive range
- no forbidden correctness/authority change
- lightening measurement contract where applicable
- experiment overlap state
- environment/dependency attribution
- exact rollback unit
- normalized before/after semantics
- semantic persisted-projection adapter availability

Review produces Authorization only.

Review does not write the Project Profile or finalize Git.

### 15.20 Project Policy Change operation owner

Physical Project policy mutation is owned by the distinct canonical internal operation:

~~~
project-policy-change
~~~

No new Project-facing domain Skill is required.

`skills/review` may coordinate Candidate freeze/meta-review and hand an Authorization to this operation, but it does not write the Profile itself.

`project-policy-change` owns:

~~~
Project context validation
-> Project execution lock
-> pending mutation open/resume
-> exact before Profile/global baseline check
-> consume exact Policy Change Authorization
-> write Project Profile and policy evidence
-> local commit
-> PersistedProjectionAdapter proof
-> complete artifact/scope proof
-> optional exact publication under rules/git
-> durable Consumption
-> completion / recovery cleanup
~~~

It reuses the canonical Mutation Controller and Git primitives.

No new generic Controller is introduced.

### 15.21 Project Policy Consumption

Policy Change uses the common Authorization/Consumption architecture but Project-policy-specific persisted identity.

Consumption binds at least:

- receipt/review identity
- operation identity/stage
- before Profile version/digest or explicit absence
- after Profile version/digest
- Global baseline digest used by the Candidate
- exact normalized persisted-policy projection hash
- local policy commit SHA
- policy_change_id

No Work-shaped lifecycle event is invented.

Review history/Consumption is not Project lifecycle truth.

### 15.22 PersistedProjectionAdapter

A Project Policy Change is successful only if:

~~~
normalized reviewed after-state
==
normalize(canonical_load(committed project-profile.yaml))
~~~

The loader/schema/default-semantics identity is bound in Review Context.

Required persistence discipline:

~~~
local commit
-> exact Profile artifact/scope proof
-> canonical loader semantic round-trip proof
-> Review authorization still current
-> only then publication
~~~

No byte-equivalent-but-semantically-different profile is accepted.

No semantic-equivalent-but-unauthorized byte shape bypasses the exact artifact proof.

If the committed profile or scope mismatches the reviewed Candidate:

~~~
no push
no silent rewrite/adoption
-> P3/P4-compatible mismatch/recovery or reconcile as contractually supported
~~~

Rollback is a new PolicyChangeCandidate/new profile version/new commit.

### 15.23 Policy storage and evidence

P6 adds:

~~~
.workline/review/policy/
  project-profile.yaml
  changes/<policy_change_id>.yaml
  evaluations/<evaluation_id>.yaml
~~~

`project-profile.yaml` is the current canonical local Profile.

`changes/*` are immutable evidence/provenance for applied Policy Changes.

`evaluations/*` are immutable observation evaluations such as retain/adjust/rollback decisions.

Every record is H-3 public-safe.

High-volume observations remain represented through RB4/P5 source references/digests; P6 does not copy raw history into policy files.

### 15.24 Observation state and evaluation

After a Policy Change is applied, it is observed under its frozen measurement contract.

An evaluation result is at least:

~~~
retain
adjust
rollback
inconclusive
~~~

`retain`:
- current Profile remains;
- immutable evaluation evidence is added.

`adjust`:
- creates a new PolicyChangeCandidate/version.

`rollback`:
- creates a new PolicyChangeCandidate/version restoring/replacing the affected setting;
- never Git reset/revert-history rewrite as the policy mechanism.

`inconclusive`:
- does not count as success;
- Profile may remain under its explicitly frozen experiment contract only if that contract permits continued observation safely;
- otherwise its rollback threshold/rule applies.

### 15.25 Experiment overlap and attribution

Every experiment declares exact `affected_policy_surface`.

Overlap is classified:

~~~
proven_disjoint
known_overlap
overlap_unresolved
~~~

Only `proven_disjoint` experiments may observe concurrently.

`known_overlap` and `overlap_unresolved` must be:

- serialized; or
- explicitly superseded; or
- combined into one compound PolicyChangeCandidate with one measurement/rollback unit.

`overlap_unresolved` does not by itself require HUMAN.

The overlap classifier/meta-rules are fixed and cannot be weakened by the experiment being measured.

### 15.26 Observation environment identity

Where material, observation binds:

- Global baseline version/digest
- Project Profile base/version
- reviewer/model identity/version
- Review/check adapter identity/version
- toolchain/runtime identity
- measurement-contract version
- relevant dependency/environment identity

If a material identity changes during an observation window:

~~~
split the observation window
or
prove the change irrelevant with positive evidence
otherwise
-> result inconclusive
~~~

Do not attribute post-change results to the old experiment by chronology alone.

### 15.27 BL-055 interaction with the Project Profile

The canonical Profile is **not** shadow authority because all are true:

- Workline explicitly owns its schema/path/loader;
- it only changes allowed Review execution policy;
- its semantic limits are fixed by Global/meta-policy;
- it is mutated only through `project-policy-change`;
- every change is reviewed and exact-persistence-proven;
- it never becomes Roadmap/Phase/Work lifecycle truth.

A free-form Project file claiming to be the "Review Profile" is not accepted by name similarity.

Only the exact canonical path/schema/loader is Project Profile authority.

### 15.28 RB1 status/validation handoff

RB6 adds read-only diagnostics to the RB1 surface when RB1 exists.

At minimum expose:

- Global baseline identity
- Project Profile: absent | version/digest
- Effective Policy identity for an inspected/current Review where applicable
- active policy experiment IDs/status
- shadow authority diagnostic: none | suspected | confirmed
- concise evidence/source for suspected/confirmed shadow authority
- policy maintenance/reconcile need where applicable

These diagnostics are additive.

They do not mutate Project state.

### 15.29 RB7 handoff

RB7 consumes only the P6 read-only Global baseline interface and RB4/P5/P6 durable evidence.

RB6 does not perform Global promotion.

It exposes enough normalized information for RB7 to reason about:

- Global policy identity/version/digest
- fixed strength/meta-rules
- local Profile delta from Global baseline
- supporting Project evidence
- experiment result/evaluation
- affected policy surface
- environment identity
- causal/independence evidence refs

A local Project recurrence count alone is not a Promotion Packet.

### 15.30 Compatibility

Existing Projects with no Profile remain valid and use Global baseline only.

Existing Review Runs continue under their frozen Effective Policy hash.

A new Profile version never alters an in-progress Run.

No automatic profile backfill.

No automatic shadow-artifact deletion/retirement/edit.

No automatic conversion of existing Project-local Skills/docs.

P6 does not change Project bootstrap.

### 15.31 RB6 tests

At minimum cover:

**Authority hygiene**
- README/BACKLOG/TODO/STATUS filename alone is not shadow authority
- ordinary domain spec/Project CONTRACT is not shadow authority
- canonical Project bootstrap still routes only through Project router
- noncanonical Workline-like operation is never invented from user wording
- unique canonical meaning routes to canonical owner
- ambiguous Workline-state intent routes to Human confirmation
- suspected shadow authority is advisory and does not invalidate Project
- confirmed shadow authority is disclosed but does not become authority
- no automatic file deletion/edit/migration
- local Skill that calls canonical Workline owner is allowed
- local Skill that explicitly substitutes parallel Workline state is detected as confirmed/suspected according to available positive evidence

**Profile/effective policy**
- absent Profile = Global baseline only
- no ProjectSTART/backfill requirement
- first authorized Policy Change lazily creates Profile
- unknown field/surface/range fails closed
- mandatory surface cannot be lightened/disabled
- forbidden correctness/authority change cannot become PolicyChangeCandidate
- Effective Policy snapshot remains frozen across later Profile change
- baseline/Profile incompatibility does not guess a merge

**Policy Change operation**
- distinct `project-policy-change` mutation owner
- Review authorization does not itself mutate Profile
- crash/resume at every profile write/commit/proof/push/Consumption boundary
- exact before-state conflict fails closed
- semantic canonical-load round-trip equals reviewed after-state
- no push before proof
- exact commit publication only
- rollback creates a new version/commit

**Learning/experiment**
- one event cannot produce permanent adaptation
- temporary guard is strengthening-only and reevaluated
- Relevant Opportunity, not raw run count, is denominator
- lightening without independent measurement is refused
- lightening cannot disable its own detector
- accepted pre-cutoff shadow task must settle
- pre-terminal shadow Problem HIGH/MID becomes blocking Review obligation
- post-terminal shadow Finding becomes downstream escape without lifecycle rewrite
- only proven_disjoint experiments observe concurrently
- overlap_unresolved is not silently treated as disjoint
- material environment change makes attribution inconclusive absent irrelevance proof

### 15.32 RB6 HUMAN status

No new Human policy decision is required by this frozen design.

That is because RB6:

- does not invalidate/refuse existing Projects due to shadow artifacts;
- does not add a new restriction merely for ordinary Project-local Skills/docs;
- does not auto-edit/delete anything;
- does not change ProjectSTART/backfill;
- does not alter correctness/HUMAN/lifecycle/product meaning;
- reuses the existing human-confirmation boundary for capability-changing local automation.

If implementation proves one of those assumptions impossible and would require a stricter existing-Project or Project-local capability rule, trigger the corresponding conditional HUMAN decision before changing that boundary.

RB6 is DESIGN_READY when this contract and its implementation brief/test matrix are prepared.


## 16. RB7 — P7 Global Promotion + Global Policy Change

RB7 promotes only sufficiently generalized, sufficiently independent Project evidence into Workline-root adaptive Review policy.

It preserves the boundary:

~~~
Review
  -> evaluates Global Policy Change Candidate
  -> emits Authorization

global-policy-change
  -> owns Workline-root policy mutation / Git / recovery
~~~

Workline root is not turned into a Workline Project. P7 does not require or simulate self-hosting.

### 16.1 Global adaptive scope

Global adaptive policy may change only P6-allowed Review execution surfaces.

It remains data interpreted under fixed normative meta-rules owned by registry.md, the canonical Review Skill, and implementation/tests.

Automatic Global Policy Change may not change:

- Work/Phase/Roadmap or lifecycle/completion semantics
- Problem/Improvement or severity meaning/blocking semantics
- H-1 through H-4
- HUMAN boundary
- product/user requirements
- canonical authority/routing
- mutation/Git/security invariants
- policy strength-class semantics themselves
- self-hosting support

A desired change crossing those boundaries is ordinary Workline-root implementation/spec work, not adaptive Global Policy Change.

### 16.2 Materialized Global policy

P6 provides a read-only derived GlobalPolicyBaseline.

P7 implementation materializes that exact baseline as:

~~~
review-policy/global-policy.yaml
~~~

The P7 implementation landing must prove:

~~~
normalize(canonical_load(materialized global-policy.yaml))
==
P6 derived GlobalPolicyBaseline semantics
~~~

at the transition point.

That first materialization is a zero-semantic-change implementation migration. It is not recorded as a learned policy change.

After materialization, the same canonical loader interface reads the tracked Global policy artifact.

### 16.3 Root policy layout

P7 owns:

~~~
review-policy/
  global-policy.yaml
  promotion-packets/<promotion_packet_id>.yaml
  changes/<global_policy_change_id>.yaml
  evaluations/<evaluation_id>.yaml
  patch-notes/<global_policy_change_id>.md
  review/
    ... root-adapted canonical P1-P4 Review records ...
~~~

The root review storage adapter reuses common Review record schema/semantics. It does not redefine Gate, TaskInput, Receipt, Supersession or Consumption meaning.

All records are H-3 public-safe.

Global policy is normative adaptive data. Promotion/change/evaluation/review records are evidence/provenance, never lifecycle state.

### 16.4 Evidence-source identity

Global promotion counts independent evidence sources, not raw Project/repository count.

Each source preserves enough provenance to reason about correlation, including where relevant:

- Project/repository identity
- template/fork/repository lineage
- relevant base provenance
- shared upstream dependency/context
- source Review Run/Finding/Repair/relation IDs
- generalized failure-pattern and root-cause/mechanism identity
- incident identity
- Project-local policy change/evaluation evidence
- Relevant Opportunity basis
- material environment/dependency identities

Project IDs alone never prove independence.

### 16.5 Independence relation

Evidence relations are exactly:

~~~
proven_independent
known_correlated
independence_unresolved
~~~

proven_independent requires positive support that observations are distinct causal/opportunity sources for the generalized mechanism.

Supporting facts may include distinct non-copy repository lineage, distinct triggering incident, distinct affected implementation, and positive proof that any shared dependency is not the common cause.

Absence of discovered correlation is not proof of independence.

known_correlated includes copies/forks/templates affected by the same causal implementation, same upstream incident/change, same causal dependency, or duplicate observations of one failure.

independence_unresolved is used when neither independence nor correlation can be positively established. It is not counted as independent and does not by itself require HUMAN.

### 16.6 Correlation clustering

Known-correlated observations form one evidence cluster for promotion counting.

Unresolved observations may provide context but do not create an additional independent cluster.

Only clusters whose mutual relation is proven_independent count separately.

Do not inflate evidence using repeated runs in one Project, repository copies, multiple reviewers of one defect, multiple Findings from one incident, or multiple local reactions to the same causal event.

### 16.7 Minimum promotion eligibility

Repeated evidence in one Project is never enough by itself.

Automatic Global promotion requires at minimum:

- more than one Project/repository lineage;
- at least two evidence-source clusters positively proven independent from each other;
- the same generalized policy mechanism/change;
- sufficient Relevant Opportunities for the direction;
- no unresolved requirement/HUMAN boundary;
- post-change observation and rollback capability.

This is a minimum eligibility floor, not a universal sufficiency count.

Fixed Global meta-policy may require stronger evidence depending on direction, risk, severity/escape consequences and breadth.

Global lightening always requires materially stronger evidence than strengthening.

### 16.8 Generalization requirement

Promotion moves a reusable mechanism, not Project-specific vocabulary or workaround.

Do not promote:

- Project component/file names as generic rules
- one repository's accidental architecture
- one local workaround
- one tool/model quirk without evidence for the relevant scope

The target policy_surface_id must already exist in the fixed P6 adaptive surface.

A proposal requiring a new policy surface/meta-rule is ordinary Workline-root implementation/spec work, not adaptive promotion.

### 16.9 Promotion Packet

Freeze an immutable:

~~~
review-policy/promotion-packets/<promotion_packet_id>.yaml
~~~

binding at least:

- current Global policy version/digest
- target policy surface and strength class
- direction: strengthen | lighten | adjust | rollback
- normalized proposed Global after-state
- generalized mechanism/root-cause identity
- source Project evidence refs
- evidence clusters and independence states
- Relevant Opportunity evidence
- Project-local policy/evaluation outcomes
- escape/recurrence/repair-induced evidence where relevant
- expected effect
- validation/measurement/observation contract
- success and rollback criteria
- supported Project Profile schema versions
- profile compatibility adapter identity/proof
- environment/dependency diversity/provenance

Packet existence is evidence, not authorization.

### 16.10 Strengthening and lightening

Global strengthening still requires cross-Project independent evidence. One severe Project incident may justify a P6 local temporary guard but not a permanent Global change by itself.

Global strengthening must stay inside an existing adaptive range, generalize the mechanism, satisfy independent-source eligibility, preserve/strengthen correctness detection, and include observation/rollback.

Global lightening has the highest adaptive evidence burden.

Before lightening authorization freeze:

- representative independent Projects/opportunities support low useful yield/acceptable escape behavior;
- adequate replacement verification remains;
- independent shadow/holdout measurement remains after activation;
- the change cannot remove/weaken its own evaluation channel;
- observation/success/rollback rules are fixed;
- Project Profile compatibility is proven.

No-finding counts only where the relevant surface was actually exercised.

One Project's successful lightening experiment is never sufficient for Global lightening.

### 16.11 Profile compatibility is a promotion precondition

Global policy change must not silently invalidate existing valid P6 Profiles.

Every changed Global surface provides a fixed versioned compatibility adapter over all valid records of every still-supported Project Profile schema version.

The adapter maps:

~~~
old valid Project Profile
+ old Global policy
+ proposed new Global policy
-> compatible local overlay semantics under the new Global policy
~~~

The proof is total over the valid schema domain, not merely over known Project files.

Requirements:

- stronger/new mandatory Global constraints cannot be weakened by old local override;
- stronger local override remains stronger where fixed policy semantics permit;
- removed/renamed settings have explicit deterministic mapping;
- no field is silently dropped;
- no Project-specific guess is used;
- resulting semantics remain inside the fixed adaptive surface.

If total compatibility cannot be proven:

~~~
automatic Global promotion is not authorized
~~~

Redesign the change or handle it through explicit migration/product work outside automatic P7 promotion.

This avoids automatic Project backfill and avoids making existing Projects invalid merely because Global policy evolved.

### 16.12 Next-safe-boundary adoption

An in-progress Review Run keeps its frozen Effective Policy.

A new Global version applies only when a new Review Run freezes policy.

At that boundary:

~~~
load new Global policy
+ interpret existing Project Profile through compatibility adapter
+ current change/risk context
-> freeze new Effective Policy hash
~~~

The Project Profile file need not be rewritten merely because Global policy changed.

No running Review is upgraded mid-flight.

### 16.13 Global Policy Change Review

Global Policy Change uses a root meta-review.

Review receives:

- exact Promotion Packet
- current Global policy
- proposed normalized Global after-state
- fixed meta-policy/constitution
- compatibility proof
- evidence/correlation material
- measurement/rollback contract

It verifies:

- current attributable evidence;
- supported independence classification;
- minimum/stronger evidence thresholds;
- generalized mechanism;
- adaptive-surface boundary;
- lightening contract where applicable;
- total Profile compatibility;
- exact normalized before/after semantics;
- root PersistedProjectionAdapter availability;
- observation/rollback feasibility.

The proposed policy cannot weaken the meta-rules used to authorize itself.

Review emits Authorization only.

### 16.14 Root Review durability

External root-policy review obeys P1 persistence:

~~~
exact Candidate/Promotion material
+ TaskInput
+ accepted descriptor
must be committed in root Review storage before external launch
~~~

The root adapter reuses common immutable CandidateSnapshot, TaskInput, GateGeneration, Receipt, Supersession and Consumption semantics.

Root Review generation commits publish nothing by themselves.

A crash/runtime cleanup must be recoverable from tracked root Review records plus immutable Git objects where positive proof is possible.

Runtime memory is never authority.

### 16.15 Global Policy Change operation owner

Physical mutation is owned by:

~~~
global-policy-change
~~~

This is a dedicated Workline-root maintenance operation.

It is not ProjectSTART, a Workline Project mutation, self-hosting, or a Work/Phase/Roadmap operation.

Review evaluates/authorizes; root maintenance owns physical mutation/Git.

### 16.16 Root maintenance runtime area

Root maintenance must never create <workline-root>/.workline/project.yaml.

Noncanonical lock/crash-recovery state lives in a dedicated ignored root runtime area:

~~~
.workline-root-runtime/
  global-policy.lock
  mutations/<mutation_id>.yaml
  maintenance-authorization.yaml
  tmp/
~~~

P7 implementation adds this exact area to root ignore/containment rules.

Nothing there is policy authority.

Runtime-state loss never permits adoption by guess. Recover from canonical root Review/Git identity when positively possible; otherwise STOP/reconcile.

### 16.17 Root maintenance activation / publication pin

When Workline root has a remote, automatic Global Policy Change requires explicit Human-approved root maintenance publication identity before mutation starts.

This is operational authorization under fixed semantics, not a new policy-design decision.

Local activation records:

- exact approved push locator(s)
- exact full destination branch ref
- root repository identity needed to bind authorization
- activation contract/version

in the ignored root runtime area.

Do not infer approval from origin/current remote.

Without the required approved pin:

~~~
Global Policy Change does not start
~~~

A remote-less Workline root may use exact local commit semantics.

### 16.18 Root operation safety

global-policy-change freezes:

- exact root branch/full ref
- exact base commit
- current Global policy digest/version
- Promotion Packet
- Authorization/Receipt
- exact write scope
- relevant implementation/meta-policy/loader identity
- publication destination identity

Use single-writer root maintenance serialization.

Do not commit unrelated Workline-root changes.

Unrelated dirt may remain untouched only when exact-scope ownership/separability is positively proven.

Unowned changes inside policy/review write scope fail closed.

No reset/rebase/amend/force recovery.

### 16.19 Global policy persistence

Runtime flow:

~~~
current Global policy
-> Promotion Packet
-> Global Policy Change Review / Receipt
-> root local policy commit
-> exact artifact/scope proof
-> canonical loader semantic round-trip proof
-> current-authorization recheck
-> exact publication when required
-> Global Policy Consumption
~~~

Consumption binds at least:

- Receipt/Review identity
- global-policy-change operation identity/stage
- before/after Global version/digest
- Promotion Packet ID/digest
- exact root policy projection hash
- exact root policy commit SHA
- compatibility adapter identity/digest

No Work-shaped lifecycle event is invented.

### 16.20 Root PersistedProjectionAdapter

Success requires:

~~~
normalized reviewed Global after-state
==
normalize(canonical_load(committed review-policy/global-policy.yaml))
~~~

Loader/schema/default/meta-policy identity is bound in Review Context.

The complete commit delta must equal the authorized root policy/change/evidence projection and no unrelated root file.

Mismatch:

~~~
no push
no silent rewrite/adoption
-> replacement Candidate/re-review only where explicitly supported
or
-> reconcile
~~~

Publication always names the exact proven commit, never a branch tip.

### 16.21 Root publication race

With configured destination:

- exact authorized commit SHA only;
- no force;
- branch/ref/remote pin rechecked immediately before push;
- remote movement/divergence never causes silent rebase/cherry-pick;
- if the reviewed candidate is no longer a safe fast-forward, stop/reconcile and require a new candidate/review unless an explicit positive reuse proof exists.

Root Review generation commits reach remote only as ancestors of the authorized Global policy publication.

### 16.22 Global evidence and Patch Notes

Every applied change writes immutable H-3-safe:

~~~
review-policy/changes/<global_policy_change_id>.yaml
review-policy/patch-notes/<global_policy_change_id>.md
~~~

The change record binds before/after identity, Promotion Packet, Review/Receipt, exact policy commit, affected surface, expected effect and measurement/rollback contract.

Patch Notes explain what changed, why, supporting evidence, what became stronger/lighter, what will be monitored, and rollback condition.

Patch Notes are explanation, not policy authority.

### 16.23 Global observation/evaluation

After publication, observe Relevant Opportunities and independent evidence sources under the frozen measurement contract.

Persist immutable:

~~~
review-policy/evaluations/<evaluation_id>.yaml
~~~

with outcome:

~~~
retain
adjust
rollback
inconclusive
~~~

retain leaves policy unchanged.

adjust creates a new Promotion/Global Policy Change Candidate as required.

rollback is a new Global version/new commit, never history rewrite.

inconclusive is not success and follows frozen experiment safety/rollback rules.

Post-change evidence uses the same independence model; correlated Projects do not become many confirmations.

### 16.24 Project-local policy remains local

Global promotion never deletes Project-local evidence/Profile state.

A Project may remain stricter than later Global default when fixed strength/compatibility rules allow it.

Global policy does not absorb Project-specific names/workarounds.

Project Profile and Global policy remain separate layers combined only by the canonical Effective Policy loader.

### 16.25 No two-repository transaction

Project-local policy mutation and Global policy mutation are separate operations/repositories.

Promotion reads Project evidence and writes only Workline root.

No atomic Project + root mutation is introduced.

Evidence changing after Promotion Packet freeze invalidates/requires re-evaluation according to its bound identity; it does not trigger cross-repository rollback.

### 16.26 Initial materialization compatibility

P7 implementation's initial materialization of P6 derived baseline must not:

- alter Project Effective Policy semantics;
- require Project Profile backfill;
- alter in-progress Review;
- activate self-hosting;
- pretend a learned Global change occurred.

Tests prove derived-before and explicit-after loader semantics are identical.

After that implementation migration, runtime changes use global-policy-change.

### 16.27 RB1 status handoff

RB7 adds read-only diagnostics:

- current Global policy version/digest
- source mode: derived-baseline | materialized-global-policy
- latest Global Policy Change/evaluation
- root maintenance activation/pin readiness without secret exposure
- pending root policy maintenance status where observable
- next-boundary adoption/compatibility identity

No status read mutates Workline root or Project.

### 16.28 RB7 tests

At minimum cover:

**Promotion/correlation**
- many runs in one Project cannot qualify alone
- fork/template/same-incident evidence clusters as correlated
- absence of known correlation does not become independence
- unresolved independence does not count separately or require HUMAN
- eligibility needs >1 Project lineage and >=2 proven-independent clusters
- Project-specific workaround cannot become Global policy
- adaptive promotion cannot create a new meta-policy surface

**Compatibility**
- total adapter over every supported valid Profile schema
- stronger mandatory Global behavior cannot be weakened by old local override
- no old Profile field silently disappears
- inability to prove total compatibility blocks automatic promotion
- no Project backfill required
- in-progress Run retains old policy
- next Run deterministically adopts new Global version

**Root authority/storage**
- initial materialized policy equals P6 derived baseline
- Workline root never gains .workline/project.yaml
- dedicated root runtime is ignored/non-authoritative
- root Review TaskInput durable before external launch
- runtime cleanup recovers only from positive canonical evidence
- Review does not physically mutate Global policy

**Root mutation/Git**
- Human-approved publication pin required when remote exists
- current remote is never inferred as approval
- single-writer root lock
- exact base/policy conflict fails closed
- unrelated bytes never committed
- exact semantic round-trip proof
- no push before proof
- exact-SHA/non-force publication
- remote race never silently rebases/cherry-picks
- crash/resume around Review, commit, proof, push and Consumption

**Observation**
- Patch Note is explanation, not authority
- retain/adjust/rollback/inconclusive are immutable evidence
- rollback is a new version/commit
- correlated Projects do not inflate retention evidence
- Global lightening retains independent measurement

### 16.29 RB7 HUMAN status

No new Human design decision is required.

P7 remains non-self-hosting and changes only the frozen adaptive verification surface.

Human action is required to approve root maintenance publication identity on a concrete machine when remote publication is enabled. This is operational authorization, not a new product-policy decision.

If implementation proves Global mutation requires treating Workline root as an ordinary Workline Project/self-hosting target, trigger the frozen conditional HUMAN decision instead.

RB7 is DESIGN_READY when this contract and implementation brief/test matrix are prepared.


## 17. RB8 — BL-011 + BL-013 + BL-020

RB8 closes three deferred items with three different dispositions.

~~~
BL-011
-> implement reusable migration procedure in canonical Roadmap responsibility

BL-013
-> complete Workline intentionally non-self-hosting
-> preserve BL-012 guard and canonicalize the reason

BL-020
-> no real correction case exists
-> do not invent correction schema
-> move future safety requirements into canonical authority and retire the backlog item
~~~

### 17.1 BL-011 canonical owner

Reusable legacy-to-Workline migration belongs to skills/roadmap as a canonical procedure.

It is not a new lifecycle, Controller or Skill.

ProjectSTART remains unchanged and owns only establishment of the canonical Workline Project/bootstrap boundary.

ProjectSTART does not inventory legacy authority, infer old current state, migrate history, retire old automation, or decide migration achievement.

### 17.2 Migration preflight

Before ProjectSTART on a legacy Project, perform a read-only inventory against one frozen repository/state identity.

Inventory at least:

- legacy current-state/task/progression authority
- legacy Roadmap/plan authority
- Project-local CONTRACT/safety
- Project-local Skills/automation/hooks/agents
- current in-progress/future obligations
- domain-specific authorities
- external authorities needed for current operation
- Git state relevant to cutover
- any prior Workline residue

If material authority changes before cutover, refresh/reconcile the inventory rather than migrate a stale snapshot.

### 17.3 Migration classification

Classify by responsibility, never filename.

~~~
A Workline-owned responsibility
  -> migrate current/future meaning into canonical Workline
  -> retire old normative role

B Project/domain authority Workline does not own
  -> preserve as Project-local authority

C stricter Project-specific safety
  -> preserve; never weaken through migration

D derived/read-only view
  -> retain only as derived/non-authoritative if useful

E historical evidence
  -> retain as history/non-authority where useful

F obsolete
  -> retire/delete only through its normal owner and required Human boundary
~~~

ROADMAP, TODO, BACKLOG, STATUS, CLAUDE or similar naming never decides the class.

RB6 shadow-authority rules apply after cutover.

### 17.4 Local safety preservation

Before retiring a legacy authority, identify any still-applicable Project-specific safety/operational rule not already represented by Workline.

Preserve that responsibility in the appropriate Project-local authority.

Do not preserve obsolete tool workflow merely because one safety rule inside it survives.

Capability-changing Project-local Skill/automation changes continue to use rules/human-confirmation.

### 17.5 Current-state migration

After ProjectSTART establishes the Workline Project:

- create a Migration Roadmap;
- represent the current desired state as Roadmap/Phase/Work;
- represent genuinely in-progress/future obligations required to reach it;
- preserve explicit dependencies and Related authority;
- preserve unresolved meaning as HUMAN rather than guessing.

Do not fabricate historical work_started/work_completed events, historical Phases, Review records, Receipts, Evidence or chronology.

Already-finished legacy work need not be lifecycle-backfilled.

### 17.6 Authority cutover

After ProjectSTART, Workline is authoritative for Workline-owned responsibilities.

Legacy planning/task/status artifacts may remain migration evidence/history, but they do not remain an alternative live progression controller.

Project/domain/safety authorities classified B/C retain authority only for their own responsibility.

This prevents a long dual-authority period.

### 17.7 Legacy authority retirement

For every class-A legacy authority, make the post-cutover role unambiguous through one of:

- delete through its normal owner when safe/authorized;
- remove/replace its normative claim;
- mark it historical/non-authoritative;
- disable old automation under required Human authorization;
- redirect human guidance to canonical Workline entry.

Do not automatically delete files merely because they contain old vocabulary.

Do not retire B/C Project/domain/safety authority.

RB6 detects later reintroduction of shadow Workline authority.

### 17.8 Project-local Skills during migration

Inventory every Project-local Skill/automation.

~~~
distinct Project/domain responsibility
-> keep

calls canonical Workline owner without duplicating semantics
-> keep

duplicates/replaces Workline planning/lifecycle/Review/Git ownership
-> retire/refactor

new capability/exposure required
-> rules/human-confirmation
~~~

ProjectSTART still installs only the canonical bootstrap entry.

BL-011 does not distribute Project-local copies of canonical Workline Skills.

### 17.9 Standalone recovery acceptance

Migration is not complete merely because old documents were edited.

A fresh session/process, without migration chat/private scratch state, must open the Project through supported bootstrap/canonical authority and determine:

- configured Workline root
- current Roadmap
- current Phase
- current/next Work
- dependencies/Related obligations
- surviving Project/domain/safety authority

It must not need retired legacy progression authority to recover current Workline state.

If it does, migration is incomplete.

### 17.10 Migration achievement

Migration Roadmap achievement requires:

- canonical current/future Workline state;
- preserved local safety/domain authority;
- retired/non-authoritative overlapping legacy authority;
- no confirmed shadow authority for migrated Workline responsibilities;
- fresh-session standalone recovery PASS;
- normal validation PASS;
- no unresolved migration Human decision.

Achievement then follows RB5 semantics/evidence.

### 17.11 BL-011 acceptance

Use a disposable legacy Project fixture containing representative:

- legacy state tracker
- stricter local safety
- Project-local automation/Skill
- domain authority
- obsolete legacy authority
- current in-progress/future obligation

Acceptance:

~~~
read-only inventory
-> ProjectSTART
-> Migration Roadmap
-> semantic current-state migration
-> preserve local safety/domain authority
-> retire old authority
-> RB6 shadow-authority check
-> fresh-session standalone recovery
-> validation
-> Migration Roadmap achievement
~~~

No existing successfully migrated Project requires backfill.

### 17.12 BL-013 intentionally non-self-hosting

Completion Sprint does not implement Workline self-hosting.

Supported completion state:

~~~
workline-core is Workline root/runtime implementation
workline-core is NOT a Workline Project
~~~

BL-012 guard remains mandatory:

- Project root and Workline root must be positively proven different physical directories;
- same directory or unprovable identity fails closed with workline_self_hosting_unsupported;
- ProjectSTART stops before Git init/.workline/bootstrap;
- established unsupported-self-hosting layout blocks state-changing operations before writes;
- read-only diagnosis remains possible;
- validate-project does not PASS that layout;
- no override or auto-repair exists.

RB7 root maintenance is not self-hosting.

### 17.13 Canonical reason for non-self-hosting

Canonical ProjectSTART/rules/git authority must state why self-hosting is intentionally unsupported.

At minimum:

- development/runtime separation is not a self-hosting contract;
- no release boundary defines which Workline revision governs mutation of itself;
- mutation/recovery formats may evolve with the implementation being edited;
- break-glass/reconcile cannot safely depend on the same broken runtime;
- root operation context and Project context have different routing/authority;
- public/private planning/evidence disclosure is unresolved for a self-hosted public root;
- portable root/version identity is not a self-hosting release model.

Therefore self-hosting is an unsupported capability, not an incomplete normal mode.

README mirrors the supported mode for humans.

### 17.14 Future self-hosting reopening

A later explicit product/spec project may reopen self-hosting only after defining/verifying:

- runtime/development separation
- release/version boundary
- intent/recovery compatibility
- break-glass/reconcile path independent of broken runtime
- root-vs-Project context/routing
- public/private disclosure
- portable root/version handling

P6/P7 adaptive policy cannot enable self-hosting.

Current Workline completion has no self-hosting dependency.

### 17.15 BL-013 tests

Preserve/add tests that:

- ProjectSTART rejects same physical root before writes;
- unprovable identity fails closed;
- unsupported established self-hosting blocks mutation before lock/write;
- read-only validation/status can diagnose;
- no override exists;
- root Global Policy maintenance never creates .workline/project.yaml;
- canonical authority explains intentional unsupported status.

### 17.16 BL-020 measured disposition

Repository search found no concrete historical event, derived relation, origin or Related record that has actually been proven mis-recorded and required formal correction.

The current BL-020-specific regression only checks that BACKLOG.md carries future correction requirements.

Therefore:

~~~
no real correction case
-> no correction event/schema
-> no speculative generated-state behavior
-> retire BL-020 as an implementation item
~~~

### 17.17 Canonical future correction boundary

Move the future safety boundary into rules/ai-decision.

When a historical fact protected as immutable history is later alleged/proven content-wrong, Workline does not silently edit, delete, ignore or reinterpret it through an ad-hoc correction.

Until a concrete case justifies a generic correction contract:

~~~
original historical record
-> remains physically immutable

generic correction/supersession operation
-> not currently defined

a downstream operation that would need the fact treated as corrected
-> do not guess
-> stop and open explicit design/product work for the concrete case
~~~

Any future generic correction mechanism must satisfy:

1. original record is never physically deleted/rewritten;
2. correction itself is a formal canonical record;
3. downstream readers mechanically detect superseded/invalidated historical fact;
4. superseded/invalidated historical fact is not reused as current truth.

These are future constraints, not a schema.

### 17.18 Existing historical Related stays unchanged

BL-009 remains unchanged.

A terminal Work's Related edge remains historical evidence and is not rewritten merely because a target later changes/disappears.

BL-020 applies only when the recorded historical fact itself is proven wrong.

No such concrete case currently exists in repository evidence.

### 17.19 Retarget test_historical_related

The BACKLOG-specific test that checks BL-020 text must not survive BL-100 deletion.

Retarget it to canonical rules/ai-decision.

The replacement regression verifies the four future-correction constraints in canonical authority while existing historical Related behavioral tests remain unchanged.

Do not create a fake correction fixture for a schema that does not exist.

### 17.20 Future real-case trigger

If a real mis-recorded historical fact later occurs:

- preserve exact concrete evidence;
- do not hand-edit the historical record;
- open explicit design/product work;
- design the narrowest correction contract against that case;
- generalize only what evidence supports;
- route HUMAN only if correction changes a Human-owned meaning/requirement boundary.

Completion Sprint does not pre-authorize the future schema.

### 17.21 Expected implementation surfaces

BL-011:
- skills/roadmap gains Legacy Project Migration procedure
- disposable migration/fresh-session recovery tests
- ProjectSTART behavior unchanged

BL-013:
- rules/git and project-start canonicalize intentional non-self-hosting rationale while preserving BL-012
- README mirrors current supported mode
- no self-hosting implementation

BL-020:
- rules/ai-decision gains future correction safety boundary
- tests/test_historical_related.py stops depending on BACKLOG
- no correction record/event/schema

### 17.22 HUMAN status

No new Human design decision is required.

Frozen conditional boundaries are not triggered:

- BL-011 stays in Roadmap responsibility;
- BL-013 remains non-self-hosting;
- BL-020 has no real case requiring a new Human-boundary schema.

Any future deviation triggers the corresponding conditional HUMAN decision before implementation.

RB8 is DESIGN_READY when this contract and implementation brief/test matrix are prepared.


## 18. RB10 — runtime hardening

RB10 is completion scope.

### N2

Apply effect-pre dirty separability and own-bytes protection consistently across legacy registration owners, at least:

- Roadmap creation
- Phase entry/add
- Related maintenance
- direct CREATE

Human pre-existing uncommitted ledger changes must not be lost/adopted before dirty-overlap/reconcile classification can occur.

### N3(b)

Reject strand/crash-capable malformed inputs before reservation/effect, including invalid tuple mutation values, lone surrogates and equivalent boundary inputs.

### N3(a)

Apply HD-1 to newline truncation, heading injection and equivalent semantic-changing accepted inputs.

### N4

Provide an explicit Human-invoked canonical disposition operation for non-resumable pending mutation/Review state.

Required:

- no record deletion
- no manual ledger edit
- explicit disposition
- durable reason
- reuse RB3-C1 set-aside meaning
- RB1 status visibility

N4 must not invent a second set-aside semantic.

### N6

Each of these receives explicit repair or accepted-residual reasoning:

1. Review gate error message with mutation id None
2. duplicate dirty_overlap messages
3. unreadable related.yaml classified as not_a_project
4. commit cleanup=strip rejecting "# only" message

Silent skip is prohibited.

### Canonical text

ProjectSTART currently says 5 required/common Skills while registry routes 7 canonical Skills:

~~~
skills/project-start
skills/project-router
skills/roadmap
skills/phase-create
skills/create
skills/start
skills/review
~~~

Correct the canonical text.

### README hygiene

Remove at least:

- legacy vault reference
- personal absolute local path

---

## 19. RB9 — final audit / BL-100 / acceptance

Start only after RB1-RB8 and RB10 are DONE.

### A — completion-map audit

Every completion item has an evidence-backed disposition.

Do not delete BACKLOG.md yet.

### B — BL-100

Classify remaining repo surfaces:

~~~
A retain
B historical-only
C obsolete
D uncertain
~~~

Resolve D.

Then, and only then:

- delete BACKLOG.md
- delete README BACKLOG reference

Do not mechanically delete BL IDs still useful in tests/history.

### C — final candidate

- exact candidate SHA/tree
- required full suite
- independent Control Plane review
- race gate

### D — fresh-session acceptance

A fresh process/session receives only live Workline authority, not sprint conversation/private scratch reasoning.

Two repeated clear-authority misreads are an authority-clarity defect.

### E — real Project acceptance

Human selects the Project under HD-3.

At least two Phases must traverse:

~~~
Project
-> Roadmap
-> Phase
-> Work
-> Review
-> Repair where applicable
-> Phase achievement
-> continuation
-> Roadmap achievement
~~~

Acceptance Work uses review-v1.

Require:

- achievement evidence
- fresh-clone reconstruction
- H-3 sanitation
- validate-project PASS
- no pending mutation
- no reconcile_required

A production repair creates a new candidate and requires affected acceptance to rerun.

---

## 20. Candidate review and landing safety

A candidate review fixes at least:

- candidate SHA
- parent SHA
- tree SHA
- changed paths
- exact diff/changed blobs
- focused tests
- required suite results

Changing candidate bytes creates a new candidate and new review.

Landing:

~~~
exact candidate
fast-forward only
~~~

Prohibited:

- force push
- silent rebase
- silent cherry-pick
- reviewed-byte regeneration
- hidden candidate identity change

If main moves after Review, carry a positive proof or rebuild/re-review on the new main.

Landing is serialized and race-gated.

---

## 21. Evidence

Preserve at least:

- candidate identities
- formal Review outcomes
- repair causality summaries
- required suite summaries
- RB2 measurement
- acceptance evidence
- final BL dispositions
- final repository-surface classification

Do not preserve H-3-prohibited raw reasoning.

---

## 22. Conditional Human decisions

Ask only if triggered:

- RB2 requires bootstrap/registry authority-layout change
- RB4 requires loss of P3 reconstruction capability
- RB5 would refuse late Work
- RB6 makes existing Projects newly invalid/refused
- RB6 adds new restrictions beyond the frozen boundary
- RB6 auto-edits/deletes Project files
- RB7 proves impossible without self-hosting
- BL-011 must live outside Roadmap
- BL-013 must become self-hosting
- BL-020 real case requires new Human schema boundary
- BL-100 leaves genuinely live development tracking needing replacement

Batch related Human questions and do not block unrelated work.

---

## 23. Block state model

~~~
NOT_READY
RESEARCHING
DESIGN_READY
READY_TO_IMPLEMENT
IMPLEMENTING
CANDIDATE
IN_REVIEW
REPAIRING
REVIEW_PASS
WAITING_FOR_LANDING
LANDED
ACCEPTANCE
DONE
HUMAN_WAIT
~~~

DONE means the whole block contract is satisfied.

---

## 24. Completion condition

The sprint is complete only when:

~~~
RB1 DONE
RB2 DONE
RB3 DONE
RB4 DONE
RB5 DONE
RB6 DONE
RB7 DONE
RB8 DONE
RB10 DONE

RB9 completion-map audit PASS
BL-100 complete
final candidate review PASS
required full suite PASS
fresh-session acceptance PASS
real-Project acceptance PASS

live main == approved final candidate
tracked canonical tree clean
no unresolved pending mutation
no reconcile_required
no blocking Problem HIGH/MID
no Problem LOW that invalidates the completion objective
no unresolved Human decision required for completion
required evidence preserved
~~~

Runtime Improvements alone do not block completion.

---

## 25. Immediate design priority

Before spending coding-agent capacity, close in the Control Plane:

1. P4 / BL-004
2. RB4 durable-history contract
3. RB6/P6 policy contract
4. RB7 promotion contract
5. RB5 Phase Review/achievement contract
6. RB8 dispositions
7. RB10 static-hardening classification
8. per-block implementation briefs and test matrices

RB2 measurement and production implementation remain execution-environment work.
