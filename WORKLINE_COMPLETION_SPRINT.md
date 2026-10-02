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

P4 must add:

- Finding identity
- Problem / Improvement / unsupported / HUMAN
- Repair Batch identity
- Candidate generation
- current-cycle resume
- dependency completeness
- conservative invalidation
- A/B/C recurrence
- impact-scaled reverification
- isolated Integration
- normal fix Work reintegration
- policy versioning
- in-flight v1 compatibility
- no semantic round fuse

Review-v1 is not made mandatory for every Work.

Semantic convergence tracks at least:

~~~
A               new supported defect
B_RECURRENCE    known semantic surface recurs
C_REPAIR_INDUCED defect introduced by repair
~~~

Two consecutive supported B/C failures on the same semantic surface require STRATEGY_CHANGE.

Agent timeout/rate-limit/crash is operational failure, not semantic recurrence.

---

## 13. RB4 — P5 / durable Review history

Required durable history:

- Run summary
- Finding summary
- Repair summary
- Finding<->Repair causality
- cross-run recurrence
- LOW traceability
- Improvement traceability
- HUMAN Decision Evidence

History is structured/sanitized/public-safe under H-3.

Review history is not lifecycle authority.

Future Work from LOW/Improvement is optional and never automatic.

---

## 14. RB5 — Phase Review / achievement

Phase Review integrates as the integration Work terminal gate.

Do not replace generated Phase completion semantics with a second lifecycle model.

Keep legacy START.

Do not make review-v1 globally mandatory.

Late Work after integration defaults to disclosure, not refusal.

Implement:

- automatic Phase achievement
- automatic Roadmap achievement
- H-3-compliant achievement evidence
- additive RB1 diagnostics

Human only where rules/human-confirmation requires it.

---

## 15. RB6 — BL-055 + P6

Shadow authority is classified by responsibility, not filename.

Ordinary README/spec/domain docs are permitted.

A canonical Project-local P6 Profile is not shadow authority.

Default shadow detection is advisory/non-refusing.

Do not:

- auto-delete
- auto-retire
- auto-backfill existing Projects
- change bootstrap by default

Adaptive policy may not change:

- correctness requirements
- HUMAN ownership
- lifecycle semantics
- product requirements
- canonical authority boundary

Produce the read-only Global baseline representation RB7 consumes.

---

## 16. RB7 — P7 Global promotion

One Project's recurrence alone cannot justify Global promotion.

Require:

- independent/correlated evidence model
- Promotion Packet
- Global Policy Change operation
- root-policy semantic proof
- adoption at next safe Review Run boundary
- observe / retain / rollback

Project mutation and Workline-root Global mutation are separate responsibilities.

Self-hosting is separate and is not a completion requirement.

---

## 17. RB8 — BL-011 + BL-013 + BL-020

### BL-011

Default migration ownership: Roadmap Skill.

ProjectSTART remains unchanged.

Acceptance uses a disposable legacy Project plus fresh-session recovery.

### BL-013

Intentionally non-self-hosting.

Preserve BL-012 guard.

Canonicalize the reason; do not make self-hosting a completion condition.

### BL-020

If no real historical-correction example exists:

- do not invent speculative schema
- retire BL-020
- move the future requirement into its canonical responsibility
- retarget the historical-related regression

If a real case creates a new Human boundary, use HUMAN.

---

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
