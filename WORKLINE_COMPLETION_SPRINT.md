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

RB1 creates the canonical read-only interface for recovering and inspecting one established Workline Project without re-deriving status logic from source code.

### 9.1 Canonical interface

Add one canonical CLI surface:

~~~
run-workline.py status <project-root>
run-workline.py status <project-root> --json
~~~

The human-readable form and JSON form are two renderings of the same status model.

The JSON form is versioned and machine-readable.

The command is allowed from outside the target Project because BL-001 permits cross-Project read-only inspection.

It never grants state-changing authority.

### 9.2 Hard read-only boundary

status must perform no write of any kind.

Prohibited:

- MutationController.open
- Project execution lock acquisition
- lock/holder creation
- canonical Project write
- runtime note/cache write
- Git index/ref/config write
- fetch/pull/push/ls-remote or any other network access
- reviewer/external-service launch
- activation/backfill/pin maintenance
- automatic repair/cleanup

status may use only local read operations.

It may read an existing holder.json as a diagnostic hint, but holder.json is never ownership proof and a stale holder must not be reported as an active lock fact.

### 9.3 Snapshot consistency

A read-only command cannot acquire the Project execution lock because taking that lock may create/update runtime lock artifacts.

Therefore status does not pretend its multi-file read is atomic.

It performs a bounded local consistency check:

~~~
B0:
  local HEAD identity
  current branch identity
  pending mutation identity set
  canonical status-surface fingerprint

read/derive status model

B1:
  re-read the same four identities
~~~

If B0 == B1:

~~~
snapshot_consistency = stable_read
~~~

and current/next derived fields may be presented normally.

If any identity changes:

~~~
snapshot_consistency = changing
~~~

The command still returns the facts it safely observed but must not claim one authoritative current/next selection from the mixed snapshot.

In JSON, fields whose answer depends on one stable Project snapshot are null/unknown with an explicit reason such as project_changed_during_status.

No retry loop that could wait indefinitely is required. One optional immediate re-read/rebuild is permitted as a bounded convenience, still with zero writes/network.

### 9.4 Canonical status model

Version 1 includes at least:

~~~
schema / version

project:
  root
  project identity/readability
  configured Workline root

authority:
  running implementation identity
  configured implementation identity
  registry validation
  canonical authority digests/identities needed to explain the active rules

git:
  repository top-level
  branch/full ref or detached
  HEAD
  dirty paths/status summary
  approved push destination pin
  locally resolved active push locator consistency
  no network-derived remote state

lifecycle:
  Roadmap(s) and lifecycle state
  current active Roadmap when mechanically unique
  active/current Phase when mechanically unique
  current/in-flight Work when mechanically unique
  next startable Work candidate(s)
  ambiguity/block reason instead of an invented winner

pending:
  pending mutation IDs
  owner
  invocation identity safe for diagnostics
  recorded write scope
  whether normal automatic resume is possible / reconcile-required / disposed
  matching Review generation mutation state where relevant

validation:
  validate-project problem list/result

review:
  Work-terminal activation state
  active review-v1 Run summary where mechanically present
  pending Review obligation summary
  no raw reviewer output

completion:
  Phase/Roadmap achievement readiness/evidence summary once RB5 is active

policy:
  Project-local Profile / effective policy / observation summary once RB6 is active
~~~

Later RB5/RB6/RB10 fields are additive to this versioned model and must not redefine the meaning of existing RB1 fields.

### 9.5 Current and next semantics

RB1 introduces no new progression algorithm.

It reuses the same canonical state/selection semantics already owned by state.py, skills/roadmap and skills/start.

Rules:

- do not select by filename, mtime or newest ID;
- do not invent a current Roadmap/Phase/Work when canonical state permits several;
- explicit in-flight/pending state is shown before a hypothetical new start;
- unresolved dependency/HUMAN/reconcile state is a blocker, not idle;
- deferred LOW maintenance is not reported as next while mandatory normal progression is blocked;
- if several startable candidates remain without a canonical winner, return the full candidate set plus ambiguity.

status is diagnostic. It never starts the reported next Work.

### 9.6 Pending mutation status

Use MutationController's durable records read-only.

At minimum distinguish:

~~~
none
pending_resumable
pending_reconcile_required
disposed_by_human
unknown_or_invalid
~~~

Do not call a pending mutation completed merely because its domain effects appear applied.

Do not hide a pending mutation merely because current lifecycle state has advanced.

For a structurally unreadable pending record, report the exact validation/reconcile reason and do not guess its owner/intent.

### 9.7 Review status

RB1 reads canonical Review records only.

At minimum expose:

- activation absent/present/invalid;
- Review Run ID/kind/target;
- latest generation;
- open/sealed/invalidated/set-aside/consumed state where mechanically derivable;
- Receipt/Consumption presence and validity summary;
- current blocking-obligation count once P4 is active.

It does not expose chain-of-thought/raw report text.

A Review record is not lifecycle truth; lifecycle and review sections remain separate.

### 9.8 Git status and push destination

Git reads are strictly local.

Allowed examples:

- rev-parse/toplevel
- symbolic-ref/current branch
- HEAD/object reads
- status/diff
- local config needed to compare configured push locator with the Project pin

Do not contact a remote merely to make status more current.

Report separately:

~~~
approved_destination
active_local_push_locator
local_locator_matches_pin
remote_publication_state = not_checked
~~~

unless a future explicitly networked read-only command owns remote inspection.

### 9.9 Validation behavior

status does not fail to produce a diagnostic model merely because validate-project has Problems.

Where enough structure can still be read safely, include:

~~~
validation = failed
problems = [...]
~~~

and continue with independent diagnostic fields.

A field whose source cannot be read reports unavailable with its exact reason rather than turning the entire Project into not_a_project.

This aligns with RB10 N6-3.

### 9.10 Authority diagnostics

The command identifies the rules/implementation being used without forcing a caller to inspect source.

At minimum:

- configured Workline root;
- current running implementation origin/identity result;
- registry validation;
- registry/canonical Skill identities relevant to Project routing;
- Review activation contract identity when active.

It does not copy canonical Skill prose into status output.

### 9.11 Human-readable output

The default rendering prioritizes recovery:

~~~
Project
Authority
Current
Next
Blocked/Waiting
Pending mutation
Review
Validation
Git / push destination
Achievement
Policy
~~~

Sections with no applicable data may be concise but must not silently erase an error state.

### 9.12 JSON stability

JSON:

- has explicit schema/version;
- uses stable enum-like status values;
- keeps display strings separate from stable IDs;
- never requires parsing human prose to recover IDs/status;
- orders lists deterministically;
- represents unknown/not-applicable explicitly;
- does not include secrets or credential-bearing URLs.

A push locator that contains credentials is redacted/fails safe consistently with current push-destination rules.

### 9.13 RB1 tests

Required tests include:

- zero writes to canonical and runtime Project surfaces;
- no lock/holder creation;
- no network command invocation;
- same status from Project cwd and external read-only caller;
- stable current/next recovery on a normal Project;
- ambiguity reported rather than guessed;
- pending mutation reported;
- malformed pending record reported without mutation;
- invalid canonical ledger still yields diagnostic validation reason;
- detached HEAD;
- unpinned/pinned push destination;
- activation absent/present/invalid;
- snapshot changes during read -> changing, no authoritative current/next claim;
- JSON deterministic and schema-valid;
- later RB5/RB6/N4 additive fields do not change base-field meaning.

### 9.14 RB1 HUMAN status

No new Human decision is required.

RB1 is read-only and expands neither mutation authority nor external connectivity.

RB1 is DESIGN_READY. Implementation/execution tests require a coding environment.


## 10. RB2 — BL-007 cold-start recovery performance

RB2 is measurement-first.

It does not assume cold-start recovery is too slow, nor that indexing/caching is automatically desirable.

### 10.1 Performance path under measurement

Measure the supported recovery path as separate stages:

~~~
A bootstrap/root resolution
B implementation identity verification
C registry parse/validation
D project-router/Skill inventory resolution
E canonical Project load
F validate-project
G RB1 status derivation
H local Git diagnostics
I final rendering/JSON serialization
~~~

Where A-D are outside one Python process in the real supported invocation, record both end-to-end and component timings rather than constructing an artificial single-process benchmark only.

No network operation belongs to the cold-start path.

### 10.2 Workloads

Use generated/disposable benchmark Projects, not a private real Project as the only evidence.

At minimum define three scales:

~~~
S:
  ~30 Works
  ~300 events

M:
  ~300 Works
  ~3,000 events

L:
  ~3,000 Works
  ~30,000 events
~~~

Keep representative:

- Roadmaps/Phases;
- roadmap and Related relations;
- completed and unstarted Works;
- some pending/review records for status/recovery readers;
- Git history sufficient for ordinary local diagnostics.

The existing originally proposed ~300 Works/~3,000 events is the primary representative M workload.

L is used to expose scaling shape, not as an assumed normal Project size.

### 10.3 Cold versus warm

Record separately:

~~~
cold-process
  new Python process
  no Workline in-process caches

warm-process
  repeated call in one process where supported
~~~

Primary BL-007 decision uses cold-process performance because the problem is fresh-session recovery.

OS filesystem cache is not artificially purged unless a portable, safe measurement method exists; if it is not controlled, record that limitation rather than calling the run cold disk.

### 10.4 Measurement protocol

For every scale:

- perform enough repeated runs to expose noise;
- report median and a tail statistic such as p95/max;
- record Python version, Git version, OS and Workline commit SHA;
- record exact benchmark Project generator/version/seed identity;
- record per-stage elapsed time;
- record local Git subprocess count by command family;
- record canonical file/entity/event counts;
- record bytes read where practical without instrumenting production semantics.

Measurement instrumentation must not mutate the benchmark Project's canonical state.

Generated temporary benchmark data may be created outside the measured status invocation.

### 10.5 Optimization trigger

Production optimization is justified only when at least one is shown:

#### Trigger A — dominant removable derivation

~~~
a concrete indexable/cachable/repeated derivation
accounts for >50% of representative M status or validate-project wall time
~~~

and there is a semantics-preserving design to remove/reuse it.

#### Trigger B — clear super-linear scaling

Approximately 10x logical input causes roughly:

~~~
>12x median wall time
~~~

for the same operation/stage beyond run-to-run noise.

The 12x value is a Completion Sprint operational threshold, not a timeless Workline semantic rule.

If neither trigger is met:

~~~
NO_OPTIMIZATION
~~~

is a valid and preferred BL-007 result.

Close BL-007 with measurements instead of adding infrastructure without evidence.

### 10.6 Allowed optimizations

When a trigger is met, prefer in this order:

1. remove duplicate load/validation inside one command;
2. reuse one immutable in-process Project snapshot within the status operation;
3. batch equivalent local Git reads;
4. add an index/cache only if the preceding approaches cannot meet the measured need.

Any cache/index must have an exact invalidation authority.

Unknown/stale cache validity falls back to canonical reconstruction, never returns a guessed current state.

### 10.7 Prohibited shortcuts

RB2 may not improve benchmark numbers by:

- skipping required validation;
- weakening registry validation;
- omitting pending mutation/review recovery;
- using stale remote-tracking refs as truth;
- keeping hidden cross-session mutable authority;
- changing lifecycle semantics;
- changing bootstrap/routing authority;
- requiring Project-side copies of canonical Skills;
- contacting a remote in status;
- persisting private/session-specific AI state as a cache.

### 10.8 Bootstrap/routing change threshold

BL-007 alone does not authorize bootstrap text/registry routing changes.

If measurement proves the bottleneck is the semantic bootstrap/routing shape rather than implementation duplication, trigger the frozen conditional HUMAN decision before changing that authority boundary.

Ordinary implementation optimization that preserves routing meaning needs no Human decision.

### 10.9 RB1 integration

RB1 status is the canonical end-to-end recovery measurement target.

Do not benchmark a private helper and call BL-007 complete if the supported status invocation remains slow.

Also measure validate-project separately because BL-007 explicitly names repeated structure validation as a candidate cost.

### 10.10 Measurement artifact

Store a public-safe Completion Sprint measurement summary containing at least:

- measured Workline SHA;
- benchmark generator/workload identities;
- environment versions;
- per-scale medians/tails;
- stage timing;
- Git command counts;
- trigger A/B evaluation;
- optimization decision;
- limitations.

Do not commit machine-specific absolute paths or private Project names.

Raw profiler/tracing output need not become permanent canonical history if the summary is sufficient to reproduce the conclusion.

### 10.11 If optimization is performed

Optimization is a separate candidate after the measurement result.

Required:

~~~
baseline measurement
-> frozen optimization hypothesis
-> implementation
-> same benchmark protocol
-> semantic regression suite
-> before/after report
~~~

The optimized version must produce the same RB1 JSON semantic model for the same stable Project snapshot, except for explicitly versioned additive fields unrelated to the optimization.

### 10.12 RB2 closeout

RB2 DONE requires either:

~~~
MEASURED_NO_OPT
  measurement complete
  Trigger A false
  Trigger B false
  no production optimization

or

MEASURED_OPTIMIZED
  trigger positively shown
  optimization landed
  semantic equivalence/regression PASS
  repeated measurement shows the intended improvement
~~~

A vague seems-faster result is insufficient.

### 10.13 RB2 HUMAN status

No Human decision is required for measurement or semantics-preserving optimization.

A bootstrap/routing meaning change triggers the conditional Human boundary.

RB2 is DESIGN_READY.

Actual measurement and any optimization require an execution-capable coding environment.


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

## 11.18 RB3-C1 implementation reconciliation amendment

This section is a narrow forward correction discovered by reconciling the frozen F4 design with the landed F3 generation and Supersession validators.

Where this section conflicts with 11.3 A2 or 11.7-11.10, this section wins.

### 11.18.1 Reuse same-Run invalidation before the successor Run

The current Supersession schema/validator intentionally means:

~~~
a Receipt is superseded by a later open generation
of the SAME Review Run
~~~

Do not broaden that schema merely for Class A.

For an old sealed Work Run/R1 that must be replaced, first use the existing invalidation shape:

~~~
old Run G3 sealed / R1
-> old Run G4 open invalidation
   + Supersession(R1)
~~~

The G4 generation mutation creates the gate and Supersession together.

Only after that exact invalidation is committed may the successor Review Run begin.

This preserves the existing Review validator and makes old R1 mechanically non-consumable before R2 can exist.

### 11.18.2 Replacement seal commit is the adoption carrier

After old-run invalidation, the replacement topology is:

~~~
K1
-> old Run G4 + Supersession(R1)
-> replacement G1
-> replacement G2
-> replacement G3 + R2
   = K_adopt
-> adopted-result publication of exact K_adopt
-> terminal transition/Consumption of R2
-> K_terminal
-> terminal publication
~~~

Do not create an extra metadata-only commit after the replacement Review seals.

K_adopt is the exact commit that persists replacement generation 3 and R2.

Its own delta contains only the replacement Run's generation-3 gate, R2 and any other record explicitly required by that generation-3 contract.

It contains no ReviewedArtifact/domain-result delta, lifecycle transition or Consumption.

The lineage from K1 through K_adopt may contain only:

- old Run's exact G4 invalidation commit;
- replacement Run's exact G1/G2/G3 commits.

No other commit is permitted in that adoption range.

### 11.18.3 Durable Class-A checkpoint before old G4

Before recording old Run G4, the owning START mutation records a durable Class-A checkpoint containing at least:

- exact K1 commit ID;
- exact old Review Run ID;
- exact old Receipt ID;
- old Candidate hash;
- mismatch/staleness classification reason;
- exact result-stage/commit ownership binding;
- predecessor Run ID for successor reservation;
- Class-A contract/version identity;
- proof that no incompatible result-publication/terminal effect is already durable.

The checkpoint is recovery/runtime material, not lifecycle truth and not a canonical Review record.

On resume it is validated against immutable committed state before any invalidation/replacement action.

It is never reconstructed from a commit message, newest commit, branch tip, path similarity or the mere existence of K1.

### 11.18.4 Old-run G4 invalidation

Class-A replacement uses a Work-specific invalidation reason/evidence identity but the same structural generation-4 mechanics as planning.

Required before G4:

- old chain is exactly G1/G2/G3 sealed;
- R1 is current and unconsumed;
- no Supersession already exists;
- K1 and raw lineage remain the exact Class-A checkpoint;
- K1 is not published;
- no incompatible publication/terminal stage is durable.

G4:

- generation = 4;
- previous_generation = 3;
- previous_digest = exact G3 digest;
- status = open;
- receipt_id = null;
- authorized_operation_stage = null;
- carries forward the immutable accepted/settled snapshot required by GateChain rules;
- evidence_digest binds a stable Work invalidation evidence record/reason;
- creates Supersession(R1) in the same generation mutation.

After G4, old R1 is never consumable and the old Run is never resumed as current authorization.

No generation 5 is permitted.

### 11.18.5 Successor Review Run reservation

One START mutation must be able to hold more than its initial Work Review Run.

Keep the existing first-Run reservation key unchanged for in-flight compatibility.

Add one deterministic successor reservation relation keyed by the exact predecessor Review Run, conceptually:

~~~
review-successor-run:<predecessor_review_run_id>
~~~

A replay of the same replacement reserves the same successor Run ID.

The successor Run still carries:

~~~
review_kind = work-result-v1
target_identity = the same Work ID
operation_identity = the same Work operation identity
~~~

The reservation key is recovery mechanics only; it does not alter semantic target identity.

A predecessor may have at most one direct successor under this F4 adoption path.

Conflicting successor IDs are reconcile-required.

P4 should reuse/generalize this same successor relation for repaired Candidate generations rather than inventing another replacement-run identity system.

### 11.18.6 Work request v2

New Work Review Runs created after F4 activation use a versioned request shape that includes sorted set_aside_runs.

Existing committed v1 TaskInput/request bytes remain valid and are read without mutation.

The request-version change is scoped to the Work request envelope; it does not require a gratuitous version bump of Candidate, Receipt or unrelated Review records.

The Work request reader supports:

~~~
v1 -> no set_aside_runs field, in-flight compatibility
v2 -> exact validated set_aside_runs list
~~~

New successor Runs use v2 and name the predecessor old Run with its invalidated/Class-A replacement reason.

The request digest continues to cover the whole exact envelope.

### 11.18.7 Automatic A2 eligibility boundary

A2 reauthorization is automatic only while all are true:

- exact operation-owned K1 exists locally;
- K1 is not published;
- no result-publication effect for old K1 has been durably recorded;
- no terminal lifecycle/Consumption stage has been durably recorded;
- no terminal commit/publication stage has been durably recorded;
- old R1 is still exactly consumable before the planned G4 invalidation;
- all ordinary Class-A ownership/lineage/delta proof succeeds.

If an incompatible old-K1 publication effect is already durable but unapplied, F4 does not rewrite/delete that effect or append a replacement publication behind an effect that can no longer be validly applied.

That state is:

~~~
reconcile required
~~~

until an explicit later disposition contract safely retires the old pending state.

Likewise, once terminal effects are durable, Class A is not a route to reinterpret them.

This preserves Mutation Controller immutability.

### 11.18.8 Replacement Candidate C2

C2 is reconstructed from committed K1 and its exact parent, never from the working tree.

Use the predecessor Candidate's declared artifact path set as the closed declaration set, then read old identities from parent(K1) and new identities/material from K1.

The complete parent(K1)->K1 delta must contain no path outside that operation-owned declaration set.

C2 therefore preserves inert declared entries while updating every persisted identity to the exact K1 reality.

The Candidate message is the exact persisted K1 message under the adopted-result contract.

Current activation/Context/Policy/Evidence are recomputed fresh.

C2's resulting-tree identity is the exact K1 tree.

### 11.18.9 Publication identity of K_adopt

After replacement G3 commits, derive K_adopt only by positive proof of the exact commit that added the expected replacement G3/R2 on the proven adoption lineage.

Immediately after the seal it should be HEAD under the Project lock, but HEAD alone is not durable recovery identity.

Before recording adopted-result publication, bind exact K_adopt commit ID into the owning START mutation's proof/checkpoint material.

Publication is:

~~~
<exact K_adopt>:refs/heads/<declared branch>
~~~

never K1 alone and never a branch tip.

The publication validator recognizes adopted-result publication as an explicit role.

Stage shape does not infer the role.

### 11.18.10 Terminal binding after adoption

R2 authorizes C2, whose persisted result artifact is exact K1.

Therefore the terminal Consumption continues to bind:

~~~
authorized_result_commit_sha = K1
~~~

not K_adopt.

But the terminal commit's exact parent is K_adopt, because K_adopt is the latest authorized publication anchor on the branch.

Class-A terminal proof must establish both independently:

~~~
artifact result binding:
  R2/C2/Consumption -> exact K1

terminal lineage:
  K1
  -> old G4
  -> replacement G1
  -> replacement G2
  -> replacement G3 = K_adopt
  -> K_terminal
~~~

No domain/result change is allowed between K1 and K_terminal except the terminal AuthorizedTransition/Consumption in K_terminal.

### 11.18.11 No extra Review of adoption metadata

Old G4 and replacement G1/G2/G3 are canonical Review-generation commits and need no Review of their own.

K_adopt is replacement G3 itself, so there is no extra metadata commit requiring authorization.

Any extra path/domain/lifecycle delta in the adoption range is Class B/reconcile, not another Class A loop.

### 11.18.12 Implementation consequence

Reuse the existing Work generation path rather than building a parallel Class-A record writer.

Expected reuse includes:

- gate.next_generation_scope;
- start_review._start_generation;
- roadmap_review._finish_generation dispatch for work-result-v1;
- ReviewStore immutable record readers;
- records.Supersession and current same-Run validator;
- exact Work generation commit persistence proof;
- exact-SHA publication primitive.

New logic is primarily:

- durable Class-A checkpoint/classifier;
- Work G4 invalidation helper;
- successor Run identity/recovery;
- Work request v2/set-aside;
- C2 reconstruction from K1;
- adopted-result lineage/proof/publication role;
- Class-A terminal-parent proof;
- stale/recovery selection.

No new Human decision is introduced by this amendment.


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

RB10 is completion scope. It closes runtime hardening defects that are already concrete enough to design without reopening P1-P7 architecture.

RB10 does not become a general cleanup bucket. Every item receives one of:

~~~
confirmed defect -> repair
contract-consistent residual -> retain with reason
execution-dependent uncertainty -> bounded probe, then classify
~~~

Silent skip is prohibited.

### 18.1 N2 — effect-pre dirty separability

Status:

~~~
CONFIRMED DEFECT
~~~

The live code already has the correct primitive:

~~~
gitops.ensure_separable_before_effects(mutation, paths)
~~~

and uses it on some mutation owners, for example lifecycle and plan-exclusion paths.

But the protection is not universal across legacy registration owners.

The shared Roadmap _open() path currently:

~~~
open mutation
-> ensure_git_ready
-> record_preexisting_dirty
-> mutation.apply()
~~~

without first proving that every path the operation is about to write is separable from the captured pre-existing dirty set.

Direct CREATE similarly records pre-existing dirty state and proceeds into register_works without one common effect-pre separability boundary.

This creates an inconsistent contract: some owners refuse before recording/applying domain effects while other owners may first discover the overlap at later Git/finalization or owner-specific checks.

RB10 freezes the invariant:

~~~
for every state-changing legacy owner,
once the exact first-stage/all-known-owned path set is known,
pre-existing dirty overlap with that set is checked
BEFORE the first domain effect for those paths is recorded or applied.
~~~

Required owners include at least:

- Roadmap creation
- Roadmap Phase addition
- Phase entry / Phase expansion
- direct standalone CREATE
- Related maintenance
- legacy registration helpers shared by those paths

START result/derivation paths that already implement stronger owner-specific refusal/recovery semantics keep those semantics; RB10 does not replace them with a weaker generic check.

Implementation rule:

1. reuse record_preexisting_dirty as the one stable mutation snapshot;
2. use ensure_separable_before_effects or a single equivalent common helper;
3. do not take a second snapshot that could treat this operation's own writes as pre-existing;
4. run the check only once the operation can name the relevant owned path set exactly;
5. if the exact path set is not yet knowable, no effect touching that still-unknown set may be recorded first;
6. resume uses the same durable snapshot and does not adopt a Human's pre-existing bytes as Workline-owned.

Acceptance must show that a Human dirty change in each affected canonical ledger/entity path is refused before the operation changes canonical Project state.

### 18.2 N2 non-goals

N2 does not:

- require a globally clean repository;
- block unrelated dirty paths;
- remove owner-specific keep/refuse/replay behavior in START;
- broaden write scope merely to make conflict detection easier;
- convert dirty_overlap into reconcile_required where current semantics are a clean pre-effect STOP.

The invariant is separability of operation-owned paths, not cleanliness.

### 18.3 N3(a) — semantic-changing text inputs

Status:

~~~
CONFIRMED DEFECT
Human decision HD-1 already frozen
~~~

The live rendering/parser pair demonstrates the defect class:

~~~
render_body(name, ...)
-> writes "# " + name

Entity.name
-> reads the first body line beginning "# "
-> strips only that line
~~~

A caller name containing a newline can therefore be accepted as non-empty while the persisted/read-back name becomes only the first line.

Likewise, caller-controlled text that can introduce canonical heading syntax may change section structure when read back.

Current Roadmap/Phase/Work input validation generally checks only non-empty .strip(); that is not a semantic round-trip proof.

Frozen rule:

~~~
caller text that cannot round-trip through the canonical writer/reader
without changing structural meaning
is rejected before reservation/effect.
~~~

At minimum reject where structurally significant:

- CR/LF/newline in entity names/displays or other single-line identity text;
- injected entity/section heading syntax in fields whose writer embeds them as Markdown structure;
- any control/Unicode form the canonical UTF-8/Yamlish/Markdown writer-reader path cannot preserve as one supported semantic value.

This is the intentional compatibility change already approved by HD-1:

~~~
old: success with mis-stored/mis-read semantic value
new: refusal before effect
~~~

Do not repair this by escaping one writer while leaving other canonical writers/readers inconsistent unless the whole canonical round-trip contract is deliberately changed.

### 18.4 N3(b) — crash/stranding malformed inputs

Status:

~~~
POLICY FROZEN
EXACT INPUT-SURFACE INVENTORY REQUIRES EXECUTION-CAPABLE IMPLEMENTATION PASS
~~~

Malformed caller input that can:

- crash serialization/rendering,
- create an unreadable durable mutation,
- reserve IDs before later deterministic refusal,
- strand a pending mutation that cannot be resumed from its own record,

must be rejected before reservation/effect.

Known candidates include:

- lone surrogate text;
- invalid tuple/record shapes reaching Phase-entry/registration mutation payloads;
- equivalent values that the durable serializer or canonical reader cannot round-trip.

Implementation must first enumerate the exact public caller surfaces and prove the rejection boundary with focused regression tests.

This is bounded reconnaissance, not an architecture question.

No malformed input is accepted merely because Python can temporarily hold it in memory.

### 18.5 N4 — explicit Human-invoked disposition

Status:

~~~
DESIGN READY
depends on RB3-C1 set-aside semantics
~~~

N4 provides the canonical escape hatch for the case:

~~~
a pending mutation / Review state is not automatically resumable
AND
the Human intentionally decides it must no longer be considered for automatic resume
AND
there is no automatic replacement Run whose set_aside_runs can carry that disposition.
~~~

N4 reuses the RB3-C1 meaning of set-aside:

~~~
the old immutable state remains evidence
but automatic recovery selection must not choose it again
~~~

N4 must not invent a second semantic meaning.

Required operation properties:

- explicitly Human-invoked;
- names the exact mutation/Review Run by stable ID;
- requires a non-empty Human disposition reason;
- verifies the target still has exactly the state being disposed;
- writes one canonical immutable disposition record;
- never edits/deletes the old mutation/Review record;
- never deletes canonical domain history;
- never rewrites Git history;
- never marks Work/Phase/Roadmap lifecycle complete;
- never converts unknown ownership into owned state;
- refuses if an automatic safe resume/replacement is currently in progress;
- idempotently returns the same disposition when repeated with the same identity/reason;
- conflicting second disposition fails closed.

The durable disposition becomes an input to:

- recovery discovery;
- RB1 status/pending-mutation diagnostics;
- validation.

A disposed pending state is no longer selected automatically, but remains visible as historical recovery evidence.

### 18.6 N4 physical ownership

The canonical disposition owner is Workline recovery/runtime authority, not Review history and not lifecycle/state.py.

For Review Runs:

- use the RB3-C1 set-aside relation/meaning;
- Receipt supersession remains the mechanism for an already-authorized sealed Receipt;
- N4 is primarily for no-replacement/no-Receipt/non-resumable state.

For generic pending mutation state:

- add the minimum immutable canonical disposition record needed to stop automatic resume;
- do not encode lifecycle semantics into it.

The exact record path/schema is an implementation detail to freeze during the implementation brief, but there must be one canonical owner and one reader path.

### 18.7 N4 status behavior

RB1 must distinguish at least:

~~~
pending_resumable
pending_reconcile_required
disposed_by_human
~~~

A Human disposition is not reported as completed, cleaned up or silently absent.

Validation may PASS a Project containing historical disposed recovery evidence only when no active pending mutation remains and every disposition record validates against an actual immutable target.

### 18.8 N6-1 — Review gate mutation ID diagnostic

Status:

~~~
CONFIRMED DIAGNOSTIC DEFECT
non-semantic
repair
~~~

review/gate.py formats pending generation mutation IDs with:

~~~
record.get("id")
~~~

but durable Mutation records identify themselves as:

~~~
mutation_id
~~~

Therefore conflict/pending diagnostics can print None.

Repair:

~~~
record.get("mutation_id")
~~~

or one canonical mutation-ID accessor.

No recovery decision currently depends on the printed value, so this is not a safety defect.

Regression tests pin both one-pending and multiple-pending diagnostics to real mutation IDs.

### 18.9 N6-2 — duplicate dirty_overlap wording

Status:

~~~
CONTRACT-CONSISTENT RESIDUAL
no semantic repair required
~~~

Live code deliberately uses one shared:

~~~
code = dirty_overlap
OVERLAP_MESSAGE = "pre-existing changes overlap operation-owned paths and cannot be separated safely: "
~~~

from several owners.

START's refused-result recovery extends that shared message with owner-specific restoration details; generic ensure_separable uses the common prefix.

The same error identity across these paths is desirable because the semantic condition is the same.

Do not create different error codes merely because the text originates at multiple call sites.

Allowed cleanup only:

- deduplicate literal construction through the common constant/helper where it improves maintenance;
- keep owner-specific detail where it explains recovery state.

No Completion Sprint obligation remains here unless implementation tests reveal two semantically different conditions being collapsed into dirty_overlap.

### 18.10 N6-3 — unreadable related.yaml reported as not_a_project

Status:

~~~
CONFIRMED CLASSIFICATION DEFECT
repair
~~~

bootstrap.is_established_project() returns only boolean.

It catches any StopError from reading:

- roadmap relations,
- related relations,
- events,

and returns False.

backfill-bootstrap then reports:

~~~
not_a_project
~~~

even when .workline/project.yaml and the Project identity exist and the actual defect is an unreadable/corrupt canonical ledger such as related.yaml.

That loses the cause and incorrectly describes an established-but-invalid Project as absence/non-establishment.

Frozen repair:

~~~
Project identity/existence
!=
Project canonical validity
~~~

Backfill/diagnostic code must preserve the structural validation reason.

Required behavior:

- missing/not-established identity may use not_a_project;
- established Project with malformed/unreadable relation/event canonical state reports the underlying canonical validation code/reason;
- it is never treated as a fresh initialization opportunity;
- no automatic overwrite/repair of the unreadable ledger.

Do not solve this by weakening is_established_project into accepting invalid ledgers as valid.

### 18.11 N6-4 — commit cleanup and "#" messages

Status:

~~~
CONFIRMED ROBUSTNESS DEFECT
repair
~~~

Legacy/local commit paths use Git commit machinery without freezing message-cleanup semantics.

The caller contract accepts any non-empty message string, while Git configuration such as:

~~~
commit.cleanup=strip
~~~

may reinterpret comment-prefixed message text and can turn a caller-supplied message whose meaningful content is only #... into an empty/changed commit message.

Review-v1 Work's hermetic commit-tree -F - path already treats the message as exact bytes and does not have this ambiguity.

Frozen rule for Workline-owned commit creation:

~~~
a message Workline accepted as non-empty
must be committed with deterministic Workline-selected cleanup semantics,
not repository/user cleanup configuration.
~~~

For Git commit-based primitives, pin cleanup behavior explicitly so comment syntax is not interpreted as instruction to discard caller content.

The chosen mode must also preserve the existing documented treatment of line endings/trailing cleanup where another recovery invariant depends on it; implementation must update proof/comparison tests accordingly.

Do not reject #-prefixed messages solely to work around ambient Git configuration.

### 18.12 Canonical Skill-count correction

Status:

~~~
CONFIRMED DOCUMENTATION DEFECT
~~~

Current registry routes seven canonical Skills:

~~~
skills/project-start
skills/project-router
skills/roadmap
skills/phase-create
skills/create
skills/start
skills/review
~~~

ProjectSTART text still contains "5 Skill ID" / "5 common Skills" wording.

Update the canonical text to seven without changing routing/behavior.

Regression should derive/compare against the registry-defined required set rather than introducing another manually-maintained count if practical.

### 18.13 README public hygiene

Status:

~~~
CONFIRMED DOCUMENTATION HYGIENE
~~~

Remove/make portable at least:

- legacy Vault reference that is no longer current authority;
- personal absolute local path examples such as D:\AIproject\workline-core.

README must describe the Workline root/project relationship portably and route authority to current canonical docs.

Do not rewrite historical contract files solely to remove historical machine paths unless BL-100 classifies them as live public-facing surface.

### 18.14 RB10 implementation ordering

Safe order:

~~~
N3 input-boundary validation
-> N2 effect-pre separability
-> N6 small diagnostics/classification/commit robustness
-> canonical text + README hygiene
~~~

N4 implementation waits for:

~~~
RB3-C1 runtime set-aside semantics LANDED
AND
RB1 status surface LANDED
~~~

N4 design may remain frozen earlier.

N2 and N3 should share one writer when they modify the same registration entrypoints.

N6 items that touch the same modules are serialized with N2/N3 rather than placed on nominally separate branches.

### 18.15 RB10 acceptance matrix

N2:

- pre-dirty roadmap.yaml / related.yaml / entity target tests for every affected owner;
- refusal occurs before first canonical domain effect;
- unrelated dirty path remains allowed;
- resolving/discarding Human change permits safe retry;
- resume does not adopt operation-produced bytes as pre-existing.

N3:

- newline name;
- heading injection;
- CR/LF variants;
- lone surrogate;
- invalid durable tuple/shape cases found by implementation inventory;
- refusal before reservation/effect;
- valid Unicode and multiline fields whose schema intentionally allows multiline still round-trip.

N4:

- exact-ID disposition;
- immutable old record remains;
- recovery no longer selects disposed target;
- duplicate same disposition idempotent;
- conflicting disposition fails closed;
- status shows disposed state;
- no lifecycle achievement/completion side effect.

N6:

- real mutation IDs in gate diagnostics;
- dirty_overlap identity unchanged;
- corrupt related.yaml reports structural invalidity rather than not_a_project;
- # only/comment-prefixed valid message commits deterministically despite hostile commit.cleanup config.

Docs:

- ProjectSTART count agrees with seven routed Skills;
- README has no legacy Vault authority claim/personal absolute root path.

### 18.16 RB10 HUMAN status

No new Human design decision is required.

HD-1 already authorizes N3(a)'s success-to-refusal compatibility change.

N4 is Human-invoked at runtime by design, but its existence/semantics do not require a new product decision.

If implementation discovers that one of N3's malformed inputs can only be fixed by changing a currently supported semantic representation rather than rejecting an invalid one, stop and route that specific requirement change to HUMAN.

RB10 is DESIGN_READY except for bounded execution-dependent enumeration/tests for N3(b) and the implementation-only exact N4 record shape after RB3/RB1 land.

---

## 19. RB9 — final audit / BL-100 / acceptance

RB9 is the global completion barrier.

It begins only when RB1-RB8 and RB10 are LANDED/DONE as applicable and no production writer remains active.

RB9 does not add a new feature program. It proves that the implemented Workline is internally complete, that obsolete development surfaces no longer masquerade as Workline concepts, and that the exact final production candidate works from both a fresh session and a real Project.

### 19.1 RB9 entry gate

Before Stage A, prove:

- RB1 through RB8 and RB10 each have an evidence-backed final disposition;
- every runtime rule frozen in this Completion Sprint that was implemented is also present in its canonical runtime owner;
- no required runtime behavior exists only in WORKLINE_COMPLETION_SPRINT.md, BACKLOG.md or a historical REVIEW_SYSTEM_* file;
- no unresolved blocking Problem HIGH/MID remains;
- no Problem LOW invalidates the completion objective;
- no required Human decision remains except HD-2W if the final landing still needs it and HD-3 for E4 Project selection;
- no implementation candidate/write branch is still concurrently changing the semantic surface under audit.

If any runtime requirement still lives only in sprint/history text, RB9 stops and routes it to the owning canonical runtime authority before cleanup.

### 19.2 Stage A — completion-map disposition audit

Build one completion map for every Completion Sprint item and every still-live BACKLOG item.

For each item record:

- stable ID / source;
- current disposition;
- canonical runtime owner, if any;
- implementation/test evidence;
- whether it is complete, intentionally retired, external development tracking, or still unresolved;
- whether any live file still claims the old responsibility.

BACKLOG.md must not be deleted while any still-valid OPEN/VERIFIED/INVESTIGATE/DEFERRED requirement exists only there.

Permitted final item dispositions are exactly:

~~~
canonicalized_and_implemented
integrated_into_existing_responsibility
moved_to_external_development_tracking
intentionally_retired
~~~

"not currently important", "historical", or "probably obsolete" is not enough by itself.

Any item outside these dispositions blocks BL-100 cleanup.

### 19.3 Stage A — canonical-authority closure

For each implemented Review Block, compare the completion contract against live runtime authority.

The audit asks responsibility-by-responsibility:

~~~
Who owns this behavior now?
Where is the canonical rule?
Where is the implementation?
Where is the regression/acceptance proof?
Would a fresh reader need the sprint/history file to know the rule?
~~~

The last answer must be NO for every runtime behavior.

Historical rationale may explain why a rule exists, but it may not be required to discover what the current rule is.

### 19.4 Stage B — BL-100 repository surface inventory

Inventory the entire tracked repository at one exact main SHA.

Do not inventory only root Markdown files.

Classify every operationally meaningful surface by responsibility:

~~~
A CURRENT
  required by current Workline runtime, public user guidance,
  canonical tests or supported development/runtime execution

B HISTORICAL_ONLY
  useful rationale/evidence, but never a current operation,
  runtime authority, lifecycle or development queue

C OBSOLETE
  duplicate, superseded, non-Workline operational surface,
  completed temporary tracking, or unsupported entry/procedure

D UNCERTAIN
  responsibility cannot yet be proven
~~~

The inventory includes at least:

- root documents;
- canonical Skills;
- registry;
- source/runtime entrypoints;
- test-only helpers/data;
- Review design/contracts/prompts;
- development procedures;
- scripts/helpers;
- generated/tracked artifacts;
- references from README and other live guidance;
- local-only/untracked artifacts discovered by the Execution Writer.

Filename alone never decides the class.

No D may remain in the final BL-100 candidate.

### 19.5 Known provisional BL-100 classification

The following classification is frozen unless later implementation creates a concrete dependency requiring a narrower exception.

#### A — retain as current

After their own cleanup/canonicalization:

- README.md
- registry.md
- registry-routed canonical Skills
- run-workline.py
- pyproject.toml
- src/workline/**
- canonical regression/acceptance tests and required test data

BL IDs may remain in test names/comments where they identify a regression or rationale.

A BL number does not imply the BACKLOG system remains live.

#### B — historical evidence, remove from root operational surface

The existing root-level REVIEW_SYSTEM_* design/checkpoint/contract/prompt family is non-normative historical Review-system evidence.

At BL-100 it must no longer appear as a peer of current root authority.

Default disposition:

~~~
move to docs/history/review-system/
~~~

with one archive README stating mechanically and prominently:

- historical evidence only;
- not runtime authority;
- not an operational entrypoint;
- not a current implementation plan;
- current authority is registry.md + routed canonical Skills + live implementation/tests.

A historical file may instead be deleted from the live tree when Git history alone is sufficient and no maintainability/evidence purpose justifies the archive.

Do not leave a selected subset at repository root merely because it is frequently cited.

If source/test comments rely on a historical section for the actual current rule, make the current invariant self-contained or route it to current canonical authority before the historical file leaves the root.

#### C — obsolete/non-Workline tracking

BACKLOG.md is deleted after Stage A has disposed every item and after its live tests/references are retargeted.

README's Improvement Backlog/BACKLOG references are removed.

BACKLOG is not replaced by another hidden Workline backlog system.

A future user request saying "add this to BACKLOG" therefore has no implied Workline operation; the caller must identify an actual destination or create normal Work/Roadmap state where appropriate.

### 19.6 Completion Sprint self-disposition

WORKLINE_COMPLETION_SPRINT.md is active control authority only while the Completion Sprint is in progress.

Once Stage A proves every runtime rule has migrated to its proper owner, the sprint document itself becomes:

~~~
B HISTORICAL_ONLY
~~~

before the final production candidate is frozen.

Move it to an explicitly historical completion archive, for example:

~~~
docs/history/completion/WORKLINE_COMPLETION_SPRINT_2026-10-03.md
~~~

or an equivalently explicit archive path.

It must not remain at repository root with Status ACTIVE after Workline completion.

The archived document is not provided as an authority package to E3; if a fresh reader discovers it, the archive boundary must make its non-authoritative status unambiguous.

### 19.7 Historical archive is not a new authority

The history archive is inert documentation.

It has no:

- registry routing;
- Skill entry;
- state/mutation reader;
- lifecycle;
- current task queue;
- next pointer;
- automation;
- authority precedence over runtime docs.

No current README flow routes an ordinary operation through it.

Its only purpose is human/audit provenance.

### 19.8 BACKLOG-dependent tests and references

Before BACKLOG.md deletion:

- retarget tests/test_historical_related.py's BL-020 text assertion to the canonical future-correction boundary in rules/ai-decision;
- preserve the existing historical Related behavior tests;
- remove any test whose only purpose is asserting BACKLOG prose after the requirement has a canonical owner;
- remove README BACKLOG operational guidance;
- repo-wide search for BACKLOG.md / Improvement Backlog / "BACKLOG" as a Workline system.

Remaining BACKLOG text is allowed only where it explicitly says that BACKLOG is not a Workline concept, if such a regression is useful; do not require even that wording if the absence of the system is mechanically clear.

### 19.9 Local-only artifact gate

GitHub inventory cannot prove local untracked/unpushed state.

Before BL-100 deletion/archival work is finalized, the Execution Writer must inspect:

- canonical local checkout;
- worktrees;
- local branches;
- untracked files;
- unpushed commits;
- known local-only P3_F3_IMPLEMENTATION_PROGRAM.md.

Do not delete/reset/clean valuable local state.

For every local-only artifact choose:

~~~
valuable/current
-> preserve and integrate or retain explicitly

historical but useful
-> archive/bundle with provenance

obsolete and safe to remove
-> remove only after positive classification

uncertain
-> preserve and report
~~~

An uncertain local artifact does not authorize destructive cleanup.

### 19.10 BL-100 Human removal manifest

Because BL-100 removes/moves repository surfaces, its exact destructive/archive manifest is a batched Human boundary unless the Human has already explicitly approved that exact manifest.

Present once:

- files/directories to retain;
- files to archive/move;
- files to delete;
- any local-only artifacts affected;
- live references/tests being retargeted;
- confirmation that no runtime semantic is being removed.

Human approval is for the exact cleanup manifest, not for reopening already-frozen runtime architecture.

If the inventory reveals genuinely live development tracking that needs a replacement system, trigger H-C11 instead of inventing one.

### 19.11 Stage B completion gate

BL-100 Stage B passes only when:

- every tracked operational surface is A/B/C;
- D count = 0;
- every BACKLOG item has a Stage-A final disposition;
- historical root Review docs are out of the root operational surface;
- Completion Sprint is archived/non-active;
- BACKLOG.md is absent;
- README no longer routes to BACKLOG/legacy Vault/personal absolute root;
- no canonical test depends on BACKLOG prose;
- no obsolete entrypoint/helper is presented as supported;
- local-only valuable state is preserved;
- current runtime authority/tests still validate.

This cleanup occurs before final-candidate freeze so E3 observes the actual final repository surface.

### 19.12 Stage C — freeze final production candidate

After BL-100 cleanup, freeze one exact candidate:

~~~
candidate SHA
parent SHA
tree SHA
complete changed-path set from the previous accepted production base
exact diff/blob identities
runtime authority identities
canonical full-suite command(s)
environment prerequisites
~~~

No "latest main" shorthand is permitted after freeze.

The candidate includes all BL-100 cleanup bytes.

### 19.13 Stage C — required suite

At freeze time re-read current canonical development/test guidance.

At this baseline, the repository's full regression command is:

~~~
py -3 -B -m pytest tests -q
~~~

and registry validation is exposed by:

~~~
run-workline.py validate-registry <workline-root>
~~~

The final candidate must run the then-current canonical equivalents, not a stale command copied from this sprint if README/entrypoints have legitimately changed.

Required final evidence includes:

- registry validation PASS;
- full tests PASS;
- focused completion tests for RB1-RB8/RB10;
- no unexpected tracked working-tree change from the suite;
- canonical docs/runtime cross-check;
- BL-100 absence/archive checks;
- static public-hygiene checks required by RB10.

Do not invent a lint/type-check gate the repository does not actually define unless it is separately added as canonical development policy.

### 19.14 Stage D — independent exact-candidate review

The Control Plane reviews the exact candidate identity, not a branch name.

If the Control Plane cannot read a local-only candidate directly, the Execution Writer supplies a Candidate Review Package containing at least:

- candidate/parent/tree SHA;
- exact diff/changed blobs;
- test/suite results;
- canonical authority changes;
- unresolved residuals.

PASS is valid only for those exact bytes.

Any repair produces a new candidate and new review.

Review specifically checks:

- every Completion Sprint decision is either canonicalized or intentionally non-runtime;
- no historical/obsolete surface still claims current authority;
- no BL-100 cleanup deleted current semantics;
- H-1 through H-4 and Human decisions are respected;
- acceptance preconditions are satisfiable from the live repo alone.

### 19.15 Stage E — landing

Land only the reviewed exact candidate.

All existing landing safety applies:

- fast-forward only;
- no force;
- no silent rebase/cherry-pick;
- serialized landing;
- race gate immediately before update.

If HD-2W is still unresolved, resolve it immediately before this first final implementation landing.

After landing, prove:

~~~
live main == reviewed candidate SHA
live tree == reviewed tree SHA
~~~

E3/E4 use this exact live main.

### 19.16 E3 — fresh-session authority/recovery acceptance

E3 uses a genuinely fresh session/process.

Do not provide:

- this chat;
- Completion Sprint prompt/package;
- private scratch/reasoning;
- prior implementation conversation;
- answer key;
- hidden summary of expected answers.

The session may use only:

- final live repository;
- canonical Workline authority/routing;
- one disposable acceptance Project prepared under the final candidate;
- ordinary supported tooling.

The historical archive remains visible only as ordinary repository content and must identify itself as non-authoritative.

### 19.17 E3 — seven frozen questions

Freeze one disposable acceptance Project state and an answer key before launching the fresh session.

Ask exactly these semantic questions, adapted only with the fixture's stable IDs/display values:

1. **Runtime authority** — What sources define current Workline runtime behavior, and which visible documents are only history?
2. **Project routing** — Starting from this established Project, how is the configured Workline root and the applicable canonical Skill/rule resolved?
3. **Current state** — What are the current Roadmap, Phase and Work, and what is the mechanically valid next Work/action or blocker?
4. **Recovery state** — Is there a pending mutation/reconcile/disposed state? If so, what does it mean and what may happen next?
5. **Review state** — Is review-v1 activated and what Review authorization/obligation state exists? Does a Receipt by itself mean completion?
6. **Achievement/policy boundary** — Is Phase/Roadmap achievement currently mechanically decidable, and what Project/Global policy or Human boundary governs any unresolved decision?
7. **Nonexistent-system check** — A user says "put this in Workline BACKLOG". What canonical Workline operation/authority is that, if any?

The answer key is derived mechanically from the frozen fixture plus current canonical authority.

Question 7 must answer that Workline has no BACKLOG operation/authority/lifecycle. It must not resurrect deleted BACKLOG.md from history as current authority.

### 19.18 E3 evaluation

Classify errors:

~~~
state/value error
-> implementation/status/fixture defect as evidence supports

authority/routing misread
-> authority-clarity candidate

historical archive treated as current authority
-> authority-clarity candidate

unsupported operation invented
-> authority-clarity candidate
~~~

For an authority-clarity candidate, run one second independent fresh session with the same live candidate/fixture/question and no hint about the first answer.

If the same clear authority is materially misread twice:

~~~
AUTHORITY_CLARITY_DEFECT
-> production repair required
~~~

If the second session reads it correctly:

~~~
single-agent error
-> record as acceptance evidence
-> does not by itself require production repair
~~~

A deterministic implementation/status failure does not need two model mistakes to count as a defect.

E3 PASS requires all seven answer-key outcomes to be recoverable without private sprint context and no repeated authority-clarity defect.

### 19.19 E4 — real Project candidate selection

After E3 PASS, present the Human 2-3 permitted real Project candidates.

For each candidate report only what is needed to choose safely:

- Project identity;
- current Roadmap/state;
- Git cleanliness/unpushed risk;
- remote/no-remote status and approved destination readiness;
- review-v1 activation status;
- whether a genuine useful two-Phase acceptance goal is available;
- mutation/cleanup risk;
- any Human activation required.

Forbidden:

- PokéTool;
- retained P3 acceptance Projects;
- an unspecified/unapproved Project.

Human chooses the Project under HD-3.

Do not infer the choice from prior preferences.

### 19.20 E4 — exact implementation identity

E4 must run against the same final live Workline candidate SHA that passed Stage D/E3.

Before acceptance mutations:

- prove the configured Workline root is the intended final implementation;
- prove its tracked HEAD is the final candidate;
- prove no unreviewed source modification changes the running implementation;
- record Python/Git versions required by current runtime authority.

If the selected real Project points at another Workline root/implementation, do not silently retarget it. Treat that as an explicit migration/configuration step under the Project's normal authority/Human boundary.

### 19.21 E4 — activation boundary

If Work-terminal review-v1 is not activated in the selected Project, Human performs/authorizes the existing Project-specific activation operation.

Completion Sprint does not auto-activate a real Project.

Activation remains one-time and does not make review-v1 the default for unrelated Work.

### 19.22 E4 — real useful workflow

Acceptance is not a dummy test Roadmap in a production Project.

Choose a genuine bounded desired state useful to that Project and represent it through at least two Phases.

The path must exercise:

~~~
Project
-> Roadmap
-> Phase 1
-> Work(s)
-> review-v1
-> repair when a supported blocking finding is actually present
-> Phase Integration Review
-> Phase achievement
-> continuation
-> Phase 2
-> Work(s)
-> review-v1
-> Phase Integration Review
-> Phase achievement
-> Roadmap achievement
~~~

All acceptance Works that terminalize through this path use review-v1.

Do not manufacture a defect solely to force a Repair Loop. If no genuine repair is needed, prove the no-repair convergence path and rely on disposable/focused tests for forced repair cases.

### 19.23 E4 evidence

Preserve H-3-compliant evidence for:

- exact Workline candidate SHA;
- Project/Roadmap/Phase/Work stable IDs;
- Review Runs/Findings/Repairs needed to prove the path;
- Phase Integration outcomes;
- Phase/Roadmap Achievement Evidence;
- push/commit identities where applicable;
- validation result;
- final pending/reconcile status.

Do not put private Project content into the public workline-core repository merely to prove E4.

Public completion evidence uses generalized/result-only facts where needed.

### 19.24 E4 fresh-clone reconstruction

After the real workflow reaches its intended terminal state, reconstruct from a fresh clone/copy of committed state using the supported final Workline implementation.

For a remote-backed Project, prefer the approved remote publication as the clone source after required pushes are complete.

For a remote-less Project, use a fresh clone from the committed repository by a method that does not borrow the original working tree/index/runtime area.

In the fresh reconstruction prove:

- validate-project PASS;
- RB1 status reconstructs the same canonical current/terminal state;
- Review/Achievement evidence required for the accepted workflow is present;
- no pending mutation;
- no reconcile_required;
- no private runtime scratch is required for the completed path.

### 19.25 E4 safety

Do not clean/reset/rebase a real Project to make acceptance convenient.

Pre-existing user changes are preserved under normal Workline Git/dirty-overlap rules.

If candidate selection reveals unsafe dirty/unpushed state, present another candidate or obtain the specific Human decision needed; do not normalize it destructively.

Acceptance cleanup may remove only temporary local clone/worktree material positively created for acceptance and proven disposable.

### 19.26 Acceptance-induced repair rule

If E3 or E4 finds a production defect requiring a Workline source/canonical-authority change:

~~~
repair
-> new candidate SHA/tree
-> canonical required suite
-> independent Control Plane review
-> exact landing
-> rerun every acceptance stage whose proof depends on the changed semantics
~~~

At minimum:

- an E3 authority/status repair reruns E3;
- an E4 runtime/review/achievement repair reruns the affected E4 path from the earliest invalidated proof;
- a broad/foundation repair reruns both E3 and E4.

Do not carry PASS across changed bytes without a positive relevance proof.

Documentation-only history-archive metadata that provably does not affect E3's authority surface may use a documented carry proof, but BL-100/README/authority changes are never presumed irrelevant to E3.

### 19.27 RB9 final completion proof

After E3 and E4 PASS, re-read live main and prove:

- main SHA/tree are still the approved candidate;
- canonical runtime authority validates;
- full suite evidence belongs to that candidate;
- no final acceptance action changed workline-core bytes;
- all Completion Sprint Blocks are DONE;
- BL-100 is complete;
- no unresolved completion Human decision remains;
- no blocking Review obligation remains;
- required evidence exists;
- local cleanup did not destroy valuable state.

If main moved, stop completion reporting until the new main is reconciled/reviewed.

### 19.28 Final report

The Completion Sprint final report records at least:

1. final live main SHA;
2. final tree SHA;
3. RB1-RB10 final disposition;
4. capability/landing checkpoint SHAs;
5. formal Control Plane review outcomes;
6. Repair Batch/recurrence/STRATEGY_CHANGE outcomes;
7. final full-suite result and environment;
8. BL-100 A/B/C inventory summary and Human cleanup approval;
9. E3 seven-question result and any second-session authority checks;
10. E4 selected Project generalized identity/result and two-Phase path outcome;
11. fresh-clone reconstruction result;
12. remaining non-blocking Problems/Improvements;
13. evidence locations;
14. retained local branches/worktrees/untracked artifacts and why;
15. confirmation of fast-forward/no-force/no-silent-rewrite landing invariants.

Do not require the final report itself to become a new runtime authority.

### 19.29 RB9 HUMAN status

Expected Human actions are bounded:

- approve the exact BL-100 destructive/archive manifest unless already explicitly approved;
- resolve HD-2W if still unresolved at final landing;
- choose the E4 real Project under HD-3;
- perform/approve review-v1 activation for that Project if required;
- answer only genuinely Human-owned product/requirement decisions discovered by acceptance.

No generic final approval is required merely because a technical proof completed.

RB9 is DESIGN_READY.

Its inventory, cleanup execution, full suite, fresh-session acceptance and real-Project acceptance require execution-capable environments and/or the Human actions above.

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

## 25. Current execution priority

The Control Plane design pass is complete.

All ten Review Blocks now have a frozen completion contract.

The remaining work is implementation planning and execution, not open-ended architecture exploration.

### 25.1 Control Plane tasks before coding-agent use

Prepare implementation briefs in dependency order:

1. RB3-C1 implementation brief and focused recovery/adoption test matrix;
2. RB3/P4 implementation brief and convergence test matrix;
3. RB4/P5 durable-history implementation brief;
4. RB1 status implementation brief;
5. RB6/P6 and RB7/P7 implementation briefs;
6. RB5 Phase Review/achievement implementation brief;
7. RB8 migration/deferred-item implementation brief;
8. RB10 N2/N3/N6 implementation brief;
9. RB10 N4 brief after RB3-C1/RB1 runtime surfaces exist;
10. RB2 measurement package after RB1 status exists;
11. RB9 audit/cleanup/acceptance runbook only after all production blocks land.

Each implementation brief must name:

- exact frozen contract section;
- existing canonical owner;
- known affected code/doc/test surfaces from static inspection;
- required new runtime canonical text;
- explicit non-scope;
- focused tests;
- required broader regression gate;
- candidate report format;
- stop/Human conditions.

Do not ask a coding agent to rediscover the architecture.

### 25.2 First execution target

The first coding execution target is RB3-C1.

Reason:

~~~
RB3-C1
-> unlocks P4
-> unlocks RB4
-> unlocks RB6 -> RB7
-> supplies N4 set-aside semantics
~~~

It is the structural critical-path head and has the highest value per scarce coding-agent run.

Before dispatch, the Control Plane should reduce RB3-C1's remaining implementation-only questions to a bounded file/function/test checklist.

### 25.3 Parallel-safe preparation

While RB3-C1 implementation is unavailable/running, the Control Plane may continue static preparation of later briefs.

This preparation must not create competing production writers.

In particular:

- RB1 can be implemented independently of RB3 semantics but its later N4/achievement/policy fields are additive;
- RB10 N2/N3/N6 may be prepared independently, but N2/N3/N6 sharing registration modules use one writer;
- RB2 waits for an implemented RB1 status surface before measurement;
- RB4 waits for P4 record/causality semantics;
- RB6 waits for RB4 durable-history semantics where its observation/history representation depends on them;
- RB7 waits for RB6;
- RB5 waits for RB4;
- RB8 waits for RB5+RB7;
- RB9 waits for all production blocks.

### 25.4 Work conservation

Work is treated as scarce.

Do not spend its next substantial run on:

- reading historical contracts already reconciled here;
- choosing Review Block topology;
- deciding H-1 through H-4;
- designing Class A/B/C semantics;
- designing P4/P5/P6/P7/RB5/RB8/RB10/RB1/RB2/RB9 from scratch;
- rewriting this Completion Sprint contract.

Use Work only for tasks requiring its executable/local environment, such as:

- bounded live-code implementation reconnaissance that GitHub static reads cannot answer;
- production edits;
- tests/probes;
- performance measurement;
- local-only artifact/worktree inspection;
- candidate commit preparation.

Claude Code or another coding agent can later consume the same briefs without changing the frozen architecture.

### 25.5 Current milestone

Current control-plane milestone:

~~~
DESIGN FREEZE COMPLETE
~~~

Current next milestone:

~~~
RB3-C1 READY_TO_IMPLEMENT brief complete
~~~

Production implementation has not been declared complete merely because the design contracts are committed.


---

## 26. RB3-C1 implementation brief

Status:

~~~
READY_TO_IMPLEMENT
architecture exploration closed
bounded implementation probes closed
~~~

This brief translates RB3-C1 into a production implementation task.

It does not reopen the frozen Class A/B/C, invalidation, successor-Run, publication or set-aside semantics.

### 26.1 Primary implementation surfaces

Expected production surfaces from static inspection:

~~~
src/workline/start.py
src/workline/start_review.py
src/workline/review/work_review.py
src/workline/review/recovery.py
src/workline/review/gate.py
src/workline/review/validate.py
src/workline/review/store.py
src/workline/review/paths.py
src/workline/review/workcommit.py
src/workline/mutation.py           only if the existing publication hook cannot express the new role cleanly
~~~

Expected canonical runtime text surfaces:

~~~
.claude/skills/start/SKILL.md
.claude/skills/review/SKILL.md
registry.md rules/git only where the existing generic exact-publication/recovery wording needs the F4 specialization
~~~

Do not change registry routing or add a new Skill.

No Receipt/Consumption/Supersession schema change is expected under the final same-Run-G4 design.

### 26.2 Existing primitives that must be reused

Reuse rather than duplicate:

- Work generation mutations: start_review._start_generation;
- work-result-v1 generation commit dispatch: roadmap_review._finish_generation;
- pending generation resume: start_review.resolve_pending_generation;
- gate generation allocation/serialization: review.gate;
- immutable CandidateSnapshot/TaskInput/Gate/Receipt/Supersession storage: ReviewStore;
- same-Run generation-4 Supersession validation: review.validate;
- complete stored-object delta/tree/raw-parent readers used by F3 proof;
- Work hermetic commit primitives and C-1 recovery: review.workcommit;
- exact-SHA publication primitive and destination pin/barrier;
- Review namespace containment/checkout proof;
- current Work Context/Policy/Evidence builders;
- Mutation durable notes/reservations and idempotent stage replay.

Do not create a second Review store, second publication subsystem or Class-A-specific Git implementation.

### 26.3 First-Run compatibility and successor reservation

Keep the current initial reservation:

~~~
review_run_key(work-result-v1, work_id)
~~~

unchanged.

Add a deterministic successor reservation key whose identity is the exact predecessor Review Run.

Recommended semantic shape:

~~~
review-successor-run:<predecessor_review_run_id>
~~~

with the usual ID-kind validation.

Add one helper in review.gate rather than constructing the key ad hoc in start_review.

Required invariants:

- same predecessor -> same reserved successor ID on replay;
- predecessor -> at most one successor in F4;
- successor target_identity remains the same Work ID;
- successor operation_identity remains the same Work operation identity;
- conflicting successor reservation -> reconcile_required;
- legacy/initial in-flight mutation bytes are unchanged.

### 26.4 Replace run_in_flight single-Run assumption

Current start_review.run_in_flight rejects more than one Work Run reservation.

Replace that assumption with one recovery selector that can distinguish:

- initial Run before any successor;
- old Run G4 invalidated;
- successor reserved but G1 not yet committed;
- successor G1/G2/G3 in progress;
- successor sealed and ready for adopted-result publication;
- malformed/ambiguous multiple-successor state.

start.py should continue to have one review-v1 resume branch, but that branch calls the new selector/continuation API instead of assuming the first Run is the only Run.

Do not change legacy START dispatch.

### 26.5 Generalize recovery discovery narrowly

review/recovery.py already has reusable common mechanics:

- matching by review_kind + operation_identity;
- committed-history discovery;
- whole-record persistence proof;
- no age/newest selection;
- set_aside_runs harvesting;
- ambiguous-recoverable refusal.

Its classification/reconstruction tail is planning-specific.

Refactor only enough to allow a Work adapter/callback set for:

- chain-shape validation;
- Candidate/TaskInput reconstruction;
- authorization predicate;
- consumed/terminal-effect classification;
- currency/staleness classification.

Planning behavior and its tests must remain byte/semantic compatible.

Do not copy the whole discovery algorithm into a second Work-only module unless a bounded probe proves reuse would materially entangle unrelated planning semantics.

### 26.6 Work request v1/v2 reader

work_review.request_envelope currently emits the v1 shape without set_aside_runs.

Implement the frozen v2 request envelope with:

- explicit request version distinction;
- exact sorted set_aside_runs;
- stable review_run_id + reason fields;
- no duplicate Run ID;
- no self-reference;
- request digest covering the whole envelope.

TaskInput record version remains unchanged unless a concrete parser constraint proves otherwise.

Reader behavior:

~~~
v1
-> existing exact semantics
-> no implicit set-aside list

v2
-> validate exact new shape
-> validate/sort set_aside_runs canonically
~~~

New successor Runs use v2.

Do not rewrite committed v1 TaskInputs.

### 26.7 Durable Class-A checkpoint

Add one versioned START mutation note/record for Class-A recovery state.

The exact note name is implementation-owned, but the payload must bind the frozen 11.18.3 fields.

The checkpoint is written only after strict Class-A eligibility and remote-publication precondition succeed and before old G4 is recorded.

Replay:

- exact same state -> continue;
- contradictory K1/Run/Receipt/stage identity -> reconcile;
- missing immutable K1/object -> reconcile;
- branch/lineage no longer provable -> Class C/reconcile;
- K1 already remotely published -> historical/unauthorized-publication handling, no adoption.

No checkpoint is created for Class B/C.

### 26.8 Class-A classifier

Do not implement Class A by catching every ReconcileRequired from prove_result.

Classification is explicit and fail-closed.

First establish hard safety facts independently:

- exact operation-owned K1 identity;
- raw one-parent identity;
- complete parent->K1 delta;
- closed operation-owned path set;
- no unexpected entry;
- branch/ref/raw-lineage proof;
- old Run/R1 identity and non-consumption;
- no incompatible durable publication/terminal stage;
- remote-publication precondition.

Only then classify:

~~~
A1
persisted artifact/message identity differs from old Candidate
but all actual K1 bytes/tree/message are wholly operation-owned and reconstructible

A2
persisted K1 is still the exact operation-owned result
but current authorization Context/Policy/Evidence currency requires fresh authorization
before any incompatible publication/terminal effect is durable

B
complete K1 delta has unexpected/non-owned content

C
ownership/ref/lineage/complete-delta/remote state cannot be positively proven
~~~

Malformed Review namespace, missing immutable records, contradictory activation, existing Consumption, unknown destination state and foreign lineage are never downgraded into A.

### 26.9 Exact K1 recovery probe

Bounded implementation probe P1:

Determine the exact existing F3 primitive that recovers the operation-owned K1 ID when:

- the result commit object/ref update exists;
- the normal post-commit proof fails or execution is interrupted;
- runtime resumes from the durable START mutation.

Prefer the existing prepared_commit_id / commit_id / workcommit C-1 recovery facts.

Do not identify K1 from:

- HEAD alone;
- commit message;
- newest commit;
- path similarity.

If current helpers do not expose the already-proven exact K1 to F4, add the narrowest accessor/checkpoint needed without changing C-1 ownership semantics.

This is an implementation probe, not a design choice.

### 26.10 Remote-publication precondition probe

Bounded implementation probe P2:

Locate/reuse the existing positive destination-publication classifier used by current mutation/publication safety and P1 R7 semantics.

Before old G4:

- destination pin must still match;
- exact K1 publication state must be positively classifiable;
- already published -> no normal Class A;
- divergent/unknown/unreadable -> reconcile/STOP as frozen;
- no stale remote-tracking heuristic.

Do not add a second weaker remote ancestry algorithm.

### 26.11 C2 reconstruction

Build C2 from committed objects.

Inputs:

- predecessor Candidate declaration set;
- exact parent(K1);
- exact K1;
- old Candidate/Run identity;
- current activation.

For every predecessor declared artifact entry:

- old identity from parent(K1);
- new identity from K1;
- payload from K1 object for file/symlink kinds;
- no payload for absent/gitlink kinds.

The complete parent(K1)->K1 delta must have no path outside the declaration set.

Preserve inert declared entries.

Bind the exact persisted K1 result message.

C2 resulting-tree identity = exact K1 tree.

Then recompute fresh:

- Context;
- Effective Policy;
- Evidence;
- reviewer descriptor/request v2.

No working-tree artifact byte participates in C2 reconstruction.

### 26.12 Old G4 invalidation helper

Add the Work equivalent of planning _invalidate using the existing Work generation path.

Expected shape:

~~~
old G3 sealed / R1
-> old G4 open
   + Work invalidation evidence digest
   + Supersession(R1)
~~~

Reuse records.Supersession unchanged.

Extend start_review._require_shape to accept exactly the frozen fourth-generation invalidation shape and reject generation 5.

The old Run after G4 is not returned as Sealed and is never consumable.

### 26.13 Successor G1-G3

After old G4 commits:

1. reserve/read the deterministic successor Run;
2. create v2 request with old Run in set_aside_runs;
3. G1 persists C2 snapshot + TaskInput + accepted descriptor;
4. launch/settle reviewer exactly through the existing Work reviewer protocol;
5. G2 uses the normal Work settlement/adjudication records;
6. only an authorizing G2 proceeds;
7. normal capability proof applies to the exact K1 resulting tree;
8. G3 issues R2.

P4 later changes blocking-review repair behavior; F4 does not repair a non-authorizing successor Review.

At the F4 checkpoint, a non-authorizing replacement remains non-authorized/reconcile/STOP under the current Work policy rather than inventing the P4 Repair Loop early.

### 26.14 K_adopt exact identity probe

Bounded implementation probe P3:

After successor G3 is persisted, obtain the exact generation-3 commit ID from positive generation persistence/history proof.

The normal uninterrupted path may observe HEAD immediately after G3 under the Project lock, but recovery cannot treat HEAD alone as identity.

If the generation commit ID is not already exposed durably after gen.complete, add/reuse a helper that proves the unique commit introducing the expected G3/R2 paths and exact generation delta.

Bind the proven commit ID into the START Class-A proof/checkpoint before publication.

Do not keep the generation runtime mutation merely to obtain the SHA if normal cleanup semantics remove it.

### 26.15 Adopted-result proof

Add one explicit adopted-result proof role, conceptually:

~~~
review_work_adopted_result_proof
~~~

The proof binds at least:

- exact K1 artifact commit;
- exact parent(K1);
- exact C2 candidate hash;
- old Run/R1;
- old G4/Supersession;
- successor Run/R2;
- exact K_adopt = successor G3 commit;
- closed raw lineage K1 -> old G4 -> successor G1 -> G2 -> G3;
- every intermediate delta restricted to the exact Review records expected at that generation;
- current Context/Policy/Evidence/activation;
- no Consumption/terminal event yet;
- approved destination identity.

The proof is re-derived before publication record and again at publication apply.

A durable proof note is a binding/pointer, never timeless truth.

### 26.16 Publication validator

Extend the Work publication validator with an explicit adopted-result role.

Normal flow remains:

~~~
normal result publication
terminal publication
~~~

Class A result-bearing flow becomes:

~~~
adopted-result publication of exact K_adopt
terminal publication of exact K_terminal
~~~

Both remote result-bearing cases still allow exactly two pushes.

The validator must never allow both normal-result and adopted-result publication roles in one completion.

No-remote remains zero pushes.

Empty-artifact normal flow remains unchanged.

Class A applies only to an existing K1 result and therefore does not synthesize an empty-result adoption path unless a later contract explicitly proves a real need.

### 26.17 Terminal after adoption

Adapt the terminal path without changing Consumption semantics.

For Class A:

~~~
Consumption.authorized_result_commit_sha = K1
parent(K_terminal) = K_adopt
~~~

The terminal proof separately proves:

- R2/C2/Consumption artifact binding to exact K1;
- exact adoption lineage to K_adopt;
- terminal delta exactly AuthorizedTransition + Consumption;
- no domain result delta after K1.

Normal F3 continues to require parent(K2)=K1.

Do not globally weaken the normal terminal parent rule into "some descendant of K1".

Select the Class-A parent rule only from the durable adoption checkpoint/proof role.

### 26.18 Publication-effect immutability boundary

Before automatic A2/G4, prove no old result-publication effect is durably recorded.

If such an incompatible effect already exists:

~~~
reconcile required
no mutation-record rewrite
no stage deletion
no replacement publication appended behind it
~~~

Add a focused regression that interrupts after old publication effect record but before apply, makes authorization stale, and proves automatic Class A is unavailable.

This regression protects the Mutation Controller immutability assumption.

### 26.19 Canonical authority activation

When implementation lands, update canonical runtime text in the same candidate.

skills/review must define at least:

- Class A/B/C;
- same-Run G4 invalidation;
- successor Run/set-aside;
- v1/v2 request compatibility;
- old Receipt supersession/currentness;
- adopted-result authorization/proof distinction;
- no generation 5;
- Review records remain non-lifecycle authority.

skills/start must define at least:

- where Class A is attempted;
- strict eligibility;
- exact K1/C2 recovery;
- K1 -> old G4 -> successor Review -> K_adopt -> terminal topology;
- exact publication points;
- Consumption still binds K1;
- incompatible durable publication/terminal effect -> reconcile;
- interruption/resume rule.

rules/git only needs additive text if the generic exact-SHA/no-force/no-rewrite rules do not already cover the new adopted-result publication role.

Do not leave any of these runtime semantics only in this Completion Sprint file.

### 26.20 Focused test surface

Prefer one dedicated Work recovery/adoption test module plus focused extensions to existing primitive tests.

Expected test surfaces:

~~~
tests/test_work_review_recovery.py              new, if one cohesive module is clearer
tests/test_work_review_runtime.py
tests/test_work_terminal.py
tests/test_work_persistence.py
tests/test_review_gate_generation.py
tests/test_review_planning_recovery.py          regression: planning behavior unchanged
tests/test_review_planning_generations.py       regression: planning invalidation unchanged
~~~

Do not rewrite existing P3 tests merely to fit F4.

### 26.21 Required focused tests — compatibility

- existing v1 Work TaskInput/request reconstructs unchanged;
- new ordinary Work Run can use v2 with empty set_aside_runs;
- successor v2 request names the exact predecessor and sorts canonically;
- duplicate/self/invalid set-aside entry fails closed;
- existing first-Run reservation key unchanged;
- successor reservation is deterministic/idempotent;
- conflicting successor ID fails closed;
- legacy START does not read F4 Review recovery state.

### 26.22 Required focused tests — invalidation

- sealed old Work Run invalidates as exact G4 + Supersession;
- G4 and Supersession are one generation mutation;
- crash before effect, after one create, after commit, before generation completion all resume to one exact G4;
- no generation 5;
- old R1 cannot be consumed after G4;
- planning same-Run invalidation regressions remain unchanged.

### 26.23 Required focused tests — C2/Class A

- A1 exact K1 committed projection becomes C2 without working-tree reads;
- inert declared entry remains in C2;
- file/symlink/gitlink/deletion identities reconstruct correctly;
- extra non-owned K1 delta -> Class B/reconcile;
- unprovable K1 ownership/raw parent/ref -> Class C/reconcile;
- already-published K1 -> historical/unauthorized publication path, no G4/successor;
- unknown/divergent destination -> no adoption;
- changed/tampered Review namespace -> no Class A;
- existing Consumption -> no Class A;
- incompatible durable result-publication effect -> no automatic A2;
- terminal stage already durable -> no Class A.

### 26.24 Required focused tests — successor Review

- crash after old G4 before successor reservation;
- successor reserved but G1 absent;
- G1 partly/fully persisted;
- reviewer crash/result retry;
- G2 persisted;
- G3/R2 persisted;
- every retry selects the same successor;
- old Run is never resumed after G4;
- no duplicate Receipt/Supersession;
- non-authorizing successor does not invent P4 repair behavior.

### 26.25 Required focused tests — adoption publication

Remote case:

- first Class-A push publishes exact K_adopt, never K1 alone;
- published lineage contains K1 + old G4/Supersession + successor G1/G2/G3/R2;
- publication validator accepts exactly one adopted-result role;
- normal-result and adopted-result roles cannot coexist;
- proof note missing/mismatched -> no push;
- destination changes -> no push;
- barrier still applies;
- exact refspec, no force;
- crash before/after publication record/apply resumes without duplicate push.

No-remote case:

- zero pushes;
- same adoption proof/currentness still required;
- K_adopt remains local exact lineage anchor.

### 26.26 Required focused tests — terminal

- Class-A Consumption binds R2 and authorized_result_commit_sha=K1;
- parent(K_terminal)=K_adopt;
- terminal delta has only the authorized events + Consumption;
- no result/domain delta appears after K1;
- normal F3 still requires parent(K2)=K1;
- terminal proof/currentness re-evaluated;
- terminal publication exact K_terminal;
- crash windows create no duplicate events/Consumption;
- recorded completion proof returns completed only after the same final conditions as F3.

### 26.27 Interruption matrix

At minimum inject interruption/failure at:

1. K1 exists before Class-A checkpoint;
2. checkpoint durable before old G4;
3. old G4 effect record before apply;
4. old G4 partial apply;
5. old G4 commit before generation completion;
6. successor reservation before G1;
7. successor G1 effect/commit;
8. reviewer launch/settlement;
9. successor G2 effect/commit;
10. successor G3/R2 effect/commit;
11. K_adopt identity proven before proof note;
12. adopted-result publication recorded before apply;
13. adopted-result publication applied;
14. terminal event/Consumption partial apply;
15. K_terminal commit;
16. terminal proof note;
17. terminal publication record/apply;
18. recorded-completion proof before START mutation cleanup.

Every row must prove:

- same durable identities on retry;
- no new Candidate/Run/Receipt/Supersession/Consumption when one already exists;
- no branch-tip/force/history rewrite;
- no fallback to legacy;
- no duplicate publication.

### 26.28 Bounded implementation probes — CLOSED

All five bounded implementation probes are closed by static inspection of the live implementation.

#### P1 — exact K1 identity

CLOSED.

Use the existing C-1 Work commit effect identity:

- prepared_commit_id is durable before the ref moves;
- commit_id + applied=true records the exact commit C-1 owns after the ref move;
- interrupted recovery re-validates the stored prepared object/ref rather than inferring from HEAD.

F4 may expose the already-proven exact commit ID through the narrowest helper/accessor needed.

Do not infer K1 from HEAD, commit message, newest commit or path similarity.

#### P2 — destination publication classification

CLOSED.

Reuse the existing exact publication/destination primitives:

- _recorded_publication;
- push_dry_run;
- reads_itself;
- destination_branch;
- fetch_destination_branch;
- raw ancestry classification.

The existing semantics already distinguish:

- destination holds exact commit / descendant -> already published / matching;
- destination holds divergent history -> reconcile;
- destination cannot be read/proven -> STOP;
- stale remote-tracking refs have no authority.

F4 may extract the narrowest read-only precondition helper needed before old G4. Do not add a second remote ancestry algorithm.

#### P3 — successor G3 exact commit SHA

CLOSED.

review.workcommit.require_generation_persisted already proves that one exact Work-mode git_commit effect:

- is applied;
- has one full commit_id owned by C-1;
- is held by the recorded branch under raw ancestry;
- contains the expected Review records as exact bytes.

The narrow implementation change is to return/expose that proven commit ID when F4 needs K_adopt.

Do not recover K_adopt from HEAD alone or keep a completed runtime mutation merely to remember the SHA.

#### P4 — recovery shared-core shape

CLOSED.

review/recovery.py already has a reusable generic discovery/persistence core:

- matching Run discovery by review_kind + operation_identity;
- committed-history discovery;
- whole-record persistence proof;
- set_aside_runs harvesting;
- ambiguous recoverable refusal;
- no age/newest selection.

Keep those mechanics shared.

Make only the planning-specific classification/reconstruction tail adapter-driven, including:

- consumed/terminal classification;
- authorization predicate;
- reconstruction validation;
- currency/staleness;
- reason constants.

Planning keeps a planning adapter with unchanged semantics/tests.

Work adds a Work adapter.

No separate duplicated Work recovery engine and no large shared-core extraction is expected.

#### P5 — exact persisted K1 commit object/message

CLOSED.

Reuse review.workcommit._stored_commit or promote the narrowest equivalent internal accessor.

It already reads the exact stored commit object through cat-file and returns:

- tree;
- raw parents;
- exact message bytes.

It does not use HEAD, branch position, git log/show pretty output, replace-view semantics or working-tree state.

C2 reconstruction therefore reads K1's persisted identity/message directly from the exact stored object.

### 26.28.1 Probe closure consequence

RB3-C1 now has:

~~~
architecture exploration open items = 0
bounded implementation probes open = 0
~~~

Coding-agent reconnaissance is limited to ordinary implementation placement/details that do not alter frozen semantics.

If implementation nevertheless proves a physical contradiction with the immutable Mutation/Review model, STOP and report that exact contradiction rather than weakening the contract.

### 26.29 Explicit non-scope

RB3-C1 implementation does not include:

- P4 Repair Batch/recurrence;
- P5 durable Review history;
- generic positive HEAD-reuse;
- adaptive Project/Global policy;
- Phase Integration Review;
- RB10 Human disposition command;
- RB1 status;
- performance optimization;
- self-hosting;
- changing legacy START;
- making review-v1 mandatory.

Do not opportunistically implement those while touching shared modules.

### 26.30 Regression gate

Before candidate review:

1. new RB3-C1 focused tests PASS;
2. all existing Work Review/P3 tests PASS;
3. planning Review recovery/generation suites PASS unchanged;
4. legacy START focused tests PASS;
5. canonical registry/Skill authority tests PASS;
6. full canonical repository regression command PASS.

At the current baseline the full command is:

~~~
py -3 -B -m pytest tests -q
~~~

Use the then-current canonical command if it legitimately changes before execution.

### 26.31 Candidate report

Execution Writer returns:

- starting main SHA/tree;
- exact implementation candidate SHA/tree;
- changed files;
- P1-P5 bounded probe answers with code references;
- canonical authority text updated;
- focused test list/results;
- planning/legacy regression results;
- full suite result;
- any accepted residuals;
- any STOP/HUMAN trigger;
- confirmation no production landing/push occurred unless separately authorized.

Do not summarize a failed probe as an implementation success.

### 26.32 RB3-C1 completion gate

RB3-C1 becomes REVIEW_CANDIDATE only when:

- Class A/B/C classification exists in production;
- old same-Run G4 invalidation works;
- successor Run recovery works;
- C2 reconstructs exact K1 from committed objects;
- request v1 compatibility/v2 set-aside works;
- K_adopt is exact successor G3;
- adopted-result publication is exact and independently validated;
- terminal Consumption binds K1 while K_terminal parents K_adopt;
- interruption matrix is covered;
- current runtime canonical Skills carry the semantics;
- required regressions pass.

Only after independent exact-candidate review PASS and landing does RB3-C1 become LANDED and unblock P4 implementation.

---

## 27. RB3-P4 implementation brief — current-cycle Repair Loop / BL-004

Status:

~~~
DESIGN_FROZEN
IMPLEMENTATION_BRIEF_FROZEN
READY_TO_IMPLEMENT_AFTER_RB3_C1_LANDS
open_architecture_items = 0
new_HUMAN_policy_decisions = 0
~~~

This section is the canonical implementation-control brief for §12.

It does not replace §12. Where wording conflicts, §12 remains the semantic contract and this section fixes the implementation allocation required to realize it in the current live code.

Execution is dependency-gated:

~~~
RB3-C1 implementation + exact-SHA review + landing
-> P4 implementation
~~~

P4 must reuse the RB3-C1 successor-Run relation and Work request versioning rather than introducing a second replacement-run mechanism.

### 27.1 Existing P3 insertion point

The live planning and Work Review owners currently share the same high-level shape:

~~~
G1 accept discovery reviewer task
-> external reviewer
-> G2 settle
-> mechanical v1 adjudication/obligations
-> authorizes?
   YES -> G3 seal + Receipt
   NO  -> terminal not_authorized/refusal
~~~

The P4 insertion point is the decision after durable discovery settlement and before the current v1 seal/refusal branch.

Do not insert P4 after Receipt issuance and do not make Review a lifecycle owner.

For new P4-capable invocations the owner flow becomes:

~~~
G1 discovery accepted
G2 discovery settled + canonical raw reports
G3 adjudication accepted
G4 adjudication settled + canonical adjudication

then exactly one semantic branch:

authorization-ready
-> G5 seal + Receipt
-> existing owner persistence / Consumption

blocking repair required
-> G5 Repair Batch + repair task accepted
-> G6 repair settled + Repair Result + Candidate N+1 snapshot
-> successor Review Run for Candidate N+1

HUMAN_WAIT
-> stop at G4
-> no guessed repair
-> later owner invocation may freeze a new Candidate/Context after the Human decision
~~~

The old P2/P3 fixed-shape v1 Runs keep their existing meaning and generation counts.

### 27.2 Responsibility split

P4 is implemented as common Review infrastructure plus kind-specific adapters plus existing operation owners.

Common semantic core:

~~~
src/workline/review/p4.py
~~~

New common module responsibility:

- P4 contract/policy identity helpers;
- discovery/adjudication/repair role vocabulary;
- normalized adjudication outcomes;
- Problem / Improvement / HUMAN classification validation;
- normalized Finding identity and canonical ordering;
- deduplication-by-repair-identity validation;
- Repair Batch construction;
- candidate-generation linkage validation;
- A_NEW / B_RECURRENCE / C_REPAIR_INDUCED validation;
- STRATEGY_CHANGE trigger;
- convergence calculation;
- impact-class vocabulary;
- Repair Coverage Check validation;
- Evidence-reuse decision over the existing typed dependency vocabulary;
- verification-only Integration side-effect result validation.

This module is inert:

- no Project lock;
- no mutation open;
- no filesystem write;
- no Git finalization;
- no lifecycle transition.

Kind-specific Review material remains owned by:

~~~
src/workline/review/planning.py
src/workline/review/work_review.py
~~~

Operation orchestration remains owned by:

~~~
src/workline/roadmap_review.py
src/workline/start_review.py
~~~

Do not create a second P4 lifecycle controller.

### 27.3 Version dispatch and v1 compatibility

P4 is an explicit new Review contract/policy identity.

The existing v1 selector types and stored v1 records remain valid without reinterpretation.

Do not modify the meaning of:

~~~
review-v1-planning-v1
review-v1-planning-policy-v1
review-v1-work-policy-v1
the current P3 Work Review contract
~~~

New P4-capable invocations use distinct durable contract/policy identities.

The implementation may centralize the exact strings in the existing kind modules plus review/p4.py, but the following invariants are frozen:

- planning P4 contract is distinct from planning v1;
- Work P4 contract is distinct from Work v1/F4;
- P4 Effective Policy identity is distinct from v1 policy;
- discovery/adjudication/repair TaskInputs bind the exact P4 contract/policy/instruction identities;
- dispatch reads explicit persisted identity from canonical TaskInput/request material;
- dispatch must never infer P4 from generation count or record shape;
- already-pending v1 Runs resume through the existing v1 path unchanged;
- a v1 Receipt is interpreted under the exact policy/hash it already binds;
- legacy non-Review operations are untouched.

Prefer new P4 selector objects/types rather than adding ambiguous optional P4 behavior to the existing v1 selector object.

A P4 selector binds separately:

- required discovery actor(s);
- one adjudicator actor;
- one repair actor.

Each actor binding has:

- callable/provider;
- durable identity;
- durable version.

A repair actor may be unused when no repair is required, but its identity/version are part of the P4 invocation contract before repair launch so resume never chooses a different executor implicitly.

### 27.4 Discovery report versioning

Do not reinterpret the existing v1 discovery report schema.

P4 discovery reports are explicit versioned records that preserve the existing structured claim fields and add the §12.12 coverage declaration.

A P4 discovery report contains at least:

- task identity;
- reviewer identity/version;
- completed/declined status;
- structured claims;
- each claim's reviewer-claimed severity;
- code;
- public-safe statement/message;
- assigned viewpoint/task slot;
- surfaces actually inspected;
- concrete behavior/questions checked;
- Evidence identities used;
- relevant surface not inspected / not decidable.

Reviewer severity remains discovery input only.

It is not authoritative P4 severity.

### 27.5 Canonical P4 namespace

Extend review/paths.py with exact path helpers for:

~~~
.workline/review/reports/<result_digest>.yaml
.workline/review/adjudications/<review_run_id>.yaml
.workline/review/repair-batches/<repair_batch_id>.yaml
.workline/review/repair-results/<repair_batch_id>.yaml
~~~

Add those directories to the closed canonical Review namespace and checkout/path-safety validation.

The raw report file stores the already-canonical kind-specific P4 discovery report record.

Its filename MUST equal:

~~~
serialize.digest(report_record)
~~~

No second wrapper record is required around the raw report.

Add common strict-schema records in review/records.py for:

- P4 Adjudication;
- P4 Repair Batch;
- P4 Repair Result.

Add read/list/digest helpers in review/store.py.

Add whole-namespace validation in review/validate.py.

All four new logical record kinds are:

- immutable create-only;
- canonical-byte round-tripped;
- clone-safe;
- validated when referenced;
- also validated when orphaned;
- Review facts, never lifecycle truth.

### 27.6 Adjudication record

One P4 Review Run has at most one canonical adjudication record:

~~~
adjudications/<review_run_id>.yaml
~~~

It binds at least:

- review_run_id;
- review_kind;
- target identity;
- operation identity;
- candidate_hash;
- candidate_generation;
- review_context_hash;
- effective_policy_hash;
- P4 adjudication contract/instruction identity;
- ordered canonical raw-report identities;
- ordered adjudication entries;
- reserved normalized Finding IDs;
- current-cycle predecessor Finding/Repair references used;
- final obligation summary/digest.

Each adjudication entry retains its exact source claim identity and one disposition:

~~~
unsupported
HUMAN
Problem
Improvement
dismissed_non_actionable
~~~

Only Problem and Improvement create normalized Findings.

A normalized Finding contains the §12.5 fields and additionally carries enough canonical repair identity material to make deduplication deterministic.

The implementation must never derive a Finding from reviewer wording alone.

### 27.7 Finding ordering, IDs and deduplication

Finding IDs are stable owner-mutation reservations.

Add a deterministic reservation-key helper in review/gate.py for normalized Findings.

Reservation order must be derived from canonical normalized adjudication material, not external return order, timestamp or dictionary insertion accident.

Recommended normalization order:

1. semantic responsibility / semantic_surface;
2. repair identity;
3. normalized category;
4. canonical ordered source claim identities.

Claims merge only when one repair/disposition closes the same substantive issue under the same semantic responsibility.

If repair identity is uncertain, keep separate.

When merged claims carry different severities, store the strongest severity positively supported by adjudication and retain every source claim reference.

No unsupported/HUMAN/dismissed entry receives a Finding ID.

### 27.8 G1 — discovery acceptance

For a P4 Run, G1 may accept one or more required discovery tasks.

Persist in the same generation:

- CandidateSnapshot;
- every discovery TaskInput;
- accepted descriptors;
- open G1.

Every discovery TaskInput binds:

- P4 review contract;
- candidate_generation;
- exact Candidate/material digest;
- Context;
- Effective Policy;
- actor identity/version;
- task slot/viewpoint;
- discovery instruction/version;
- Evidence identities available to that discovery task.

No discovery actor is launched until G1 is durably committed and reads back canonically.

The Candidate snapshot is written once.

### 27.9 G2 — discovery settlement and raw-report durability

Run the exact accepted discovery tasks.

Invalid/exceptional/unsafe external returns do not settle the task.

A valid return is first canonicalized and H-3 checked.

Unsanitized model output, chain-of-thought, transcript, secrets, unnecessary local paths and unnecessary private identifiers never become canonical report bytes.

G2 is written only when all required discovery tasks for this Candidate have valid settlement material.

G2 persists:

- each content-addressed canonical raw report;
- settled task descriptors;
- raw-report-set digest;
- coverage digest for discovery coverage;
- no authoritative P4 Finding classification yet.

If a crash occurs after an external return but before durable G2:

- the accepted TaskInput remains authority;
- the same task may be relaunched to the same bound actor;
- runtime copies are not recovery authority.

An orphan canonical raw-report file is valid only if its own strict schema/digest validates; it does not count as settled without the Gate settlement link.

### 27.10 G3 — adjudication acceptance

After G2, build one adjudication TaskInput from canonical material only.

The adjudication request binds:

- exact Candidate identity/material;
- ordered canonical raw-report identities;
- current decided requirement/desired-state material supplied by the owner;
- Context and Effective Policy identities;
- relevant current-cycle Finding/Repair linkage;
- Evidence/coverage identities;
- adjudicator identity/version;
- P4 adjudication instruction/version.

Persist G3 accepting that TaskInput before any external adjudicator launch.

A crash/retry launches only the same persisted adjudication task to the same bound adjudicator identity/version.

No runtime report text is adjudication recovery authority.

### 27.11 G4 — adjudication settlement

The adjudicator return is data, not authority until normalized and validated.

Apply §12.4 in order.

Validation must reject any return that:

- classifies an unsupported claim as a Finding;
- converts HUMAN uncertainty into Problem/Improvement;
- marks a LOW Problem non-blocking while the current completion objective does not hold;
- asserts B/C without the required positive causal linkage;
- omits a source claim;
- invents a source report not bound to G3;
- produces contradictory duplicate Finding identities.

G4 persists:

- canonical adjudication record;
- settled adjudication task;
- final coverage/adjudication/obligation digests;
- open Gate.

After G4, derive one of:

~~~
AUTHORIZATION_READY
REPAIR_REQUIRED
HUMAN_WAIT
~~~

No Receipt exists yet.

### 27.12 Authorization-ready branch

Authorization-ready requires the full §12.18 convergence predicate.

At minimum:

- discovery coverage complete/resolved;
- raw reports all durable;
- adjudication complete;
- unadjudicated claims zero;
- unresolved Problem HIGH/MID zero;
- LOW dispositions traceable and objective still holds;
- Improvement dispositions traceable;
- unresolved HUMAN zero;
- required reverification complete;
- latest Repair Coverage Check complete when relevant;
- no unresolved repair-induced Problem;
- no pending STRATEGY_CHANGE requirement;
- Evidence used for authorization current.

Then:

~~~
G5 sealed
+ Receipt
~~~

For P4 the Receipt's review_generation is 5.

Existing Receipt schema may be reused if it already permits the generation value and all binding invariants remain valid.

Do not weaken v1's seal-generation checks globally.

Owner/validator code dispatches seal generation by explicit stored Review contract.

After P4 G5 Receipt issuance, normal owner persistence/Consumption continues.

### 27.13 HUMAN_WAIT branch

If G4 contains an unresolved HUMAN outcome required for this Candidate:

- no Repair Batch;
- no repair task;
- no Receipt;
- no guessed requirement;
- no lifecycle completion.

The Run remains at canonical G4 HUMAN_WAIT.

A later Human decision is supplied through the normal owning operation boundary.

If that decision requires or yields a new Candidate/Context, the owner starts a new P4 Run and explicitly sets the old Run aside.

P4 does not invent a separate requirement store.

Long-lived Human Decision Evidence is RB4/P5 responsibility; P4 stores only the current-cycle adjudication material required to recover this wait.

### 27.14 Repair Batch

When G4 has decidable blocking Problem HIGH/MID Findings, build exactly one immutable Repair Batch for that Candidate generation.

Reserve its ID deterministically from the owning mutation and source Run.

One source Candidate generation may have at most one Repair Batch.

The batch contains every currently decidable blocking Problem HIGH/MID Finding.

It excludes:

- Improvement;
- HUMAN;
- unsupported;
- dismissed_non_actionable.

A LOW Problem is included only when the adjudication/owner deliberately chooses current-cycle repair; it is never inserted merely because it exists.

The batch binds the §12.8 fields plus:

- candidate_generation;
- adjudication digest;
- exact prior repair relationship inputs;
- strategy mode.

If the common P4 recurrence calculation requires STRATEGY_CHANGE, the batch must record that requirement and an ordinary unchanged local-patch strategy is invalid.

### 27.15 G5 repair branch — Repair Batch + repair task acceptance

For REPAIR_REQUIRED, G5 is open, not sealed.

Persist in the same generation:

- one Repair Batch;
- one Repair TaskInput;
- accepted repair-task descriptor;
- no Receipt.

The ReviewRepairRequest is reconstructed from canonical records only:

- exact source Candidate snapshot/material;
- exact Repair Batch;
- current decided requirement/desired state;
- allowed repair/result surface;
- relevant Evidence/coverage constraints;
- required strategy-change mode where applicable;
- repair actor identity/version;
- repair instruction/version.

Do not launch repair before G5 is durably committed and read back.

An exception, invalid return or explicit repair failure does not settle a successful repair by inference.

### 27.16 Repair executor boundary

The repair executor does not own canonical Project mutation, lifecycle progression or Git finalization.

Its output is a proposal for a complete repaired Candidate.

The common P4 layer must not write repaired domain state.

Kind-specific adapters validate/adopt the proposal:

Planning:

- reconstruct a complete planning Candidate using the planning Candidate builder/validator;
- no Roadmap/Phase registration occurs before later authorization.

Work:

- reconstruct a complete Work Candidate/snapshot material including exact payload bytes/object identities;
- the repair actor does not directly mutate the canonical working tree as Review authority;
- candidate bytes remain Review material until the owning START path adopts the authorized repaired Candidate;
- final canonical working-tree/result adoption remains START-owned and must use the existing ownership/overlap/resulting-tree safety machinery.

If an external repair implementation mutates undeclared canonical Project state as a side effect, the repair is invalid and must not be settled as successful.

### 27.17 Repair Coverage Check and impact class

Every successful repair proposal carries exactly one impact class:

~~~
LOCAL
SHARED
CONTRACT
FOUNDATION
~~~

The Repair Coverage Check is strict structured data, not prose-only evidence.

It records at least:

- semantic behavior changed;
- semantic responsibility;
- other sites/paths with the same responsibility;
- whether the responsibility is shared/common;
- whether the affected set is positively enumerable;
- enumerated/identified affected set where available;
- whether the proposed repair covers that set;
- unresolved coverage gap.

Unknown Repair Coverage never PASSes.

If a local patch is presented for a positively shared responsibility:

~~~
reject successful settlement / require widened repair
~~~

before another Formal Review round is spent rediscovering the same omission.

### 27.18 Evidence reuse across Candidate N -> N+1

Do not call closure.may_reuse() to reuse an entire prior Review across a repaired Candidate.

That helper intentionally binds ReviewProvenance including candidate_hash and task/request identities, so a repaired Candidate must not inherit Review authorization.

P4 reuses only Evidence under §12.13.

Reuse the existing typed dependency vocabulary and proof records in review/closure.py:

- EvidenceDeclaration;
- ClassCoverage;
- MechanismProof;
- dependency classes;
- complete/unknown semantics.

Add a narrow P4 Evidence-reuse decision in review/p4.py.

Evidence reuse is YES only when all are positively proven:

- prior declaration complete;
- new declaration complete;
- all required dependency classes positively covered;
- all non-required classes accounted for;
- concrete Evidence-bound identities unchanged;
- adapter identity/version unchanged;
- proof mechanism identity/version unchanged;
- repair impact does not invalidate the semantic assumption proved.

Anything else is:

~~~
reusable = false
state = unknown | invalidated
-> reacquire
~~~

A discovery report, adjudication or Receipt is never reused as authorization for Candidate N+1.

### 27.19 Impact-scaled reverification

The kind adapter converts the Repair Result impact class into the required verification plan.

The plan is semantic, not file-count based.

Minimum rules are exactly §12.14.

The Repair Result stores:

- impact class;
- required reverification identities;
- completed reverification identities/results;
- Evidence reuse/invalidation decision;
- Repair Coverage Check;
- residual required verification count.

G6 cannot mark a successful repair ready for a successor Run while required repair coverage is unknown.

Evidence that must be reacquired may be obtained for Candidate N+1 during the successor Run; it is not silently copied from Candidate N.

### 27.20 G6 — Repair Result and Candidate N+1

A successful repair settles in G6.

Persist atomically in the generation mutation:

- settled repair task;
- immutable Repair Result;
- complete CandidateSnapshot N+1;
- linkage from source candidate/run/batch to result candidate;
- no Receipt.

Repair Result binds at least the §12.10 fields plus:

- source candidate_generation;
- result candidate_generation = source + 1;
- exact result Candidate material digest;
- exact successor eligibility state;
- exact coverage/reverification digests.

Candidate N+1 is a complete Candidate under the existing kind Candidate schema/semantics.

It is never a patch object.

The old Run's candidate_hash never changes.

### 27.21 Successor Run after G6

Reuse/generalize the deterministic successor relation landed by RB3-C1.

The successor reservation remains keyed by predecessor Review Run ID.

Do not introduce another P4-specific replacement-run identity allocator.

The new Run binds:

- same owning operation_identity;
- same target/review kind;
- result candidate_hash from G6;
- candidate_generation + 1;
- predecessor review_run_id;
- source repair_batch_id;
- explicit set-aside/replacement reference to the predecessor.

At most one direct successor may exist for one predecessor.

Conflicting successor identities are reconcile-required.

No newest/timestamp selection.

### 27.22 Current-cycle recovery

Extend review/recovery.py through versioned adapters, not a second recovery engine.

The generic discovery core continues to own:

- matching by review kind / target / operation identity;
- committed-history discovery;
- canonical persistence proof;
- set-aside harvesting;
- ambiguity refusal;
- no newest selection.

Add P4 state classification for:

- G1 discovery accepted;
- G2 discovery settled;
- G3 adjudication accepted;
- G4 adjudicated authorization-ready;
- G4 HUMAN_WAIT;
- G4 repair-required before G5;
- G5 sealed;
- G5 repair accepted;
- G6 repair settled;
- successor reserved / not yet G1;
- successor active;
- malformed/ambiguous linkage.

Runtime report copies are never required for recovery once canonical P4 report records exist.

Incomplete or contradictory candidate-generation / predecessor / batch / successor linkage is reconcile-required.

### 27.23 A/B/C and STRATEGY_CHANGE

A/B/C is computed/validated only from explicit current-cycle linkage.

Never infer causality from "appeared after repair".

Allowed:

~~~
A_NEW
B_RECURRENCE
C_REPAIR_INDUCED
~~~

B_RECURRENCE requires:

- linked prior Finding;
- linked prior Repair Batch/Result as applicable;
- same substantive Problem/semantic responsibility;
- positive support that the prior repair failed to close it.

C_REPAIR_INDUCED requires:

- linked causal Repair Batch/Result;
- causal evidence digest;
- positive support that the Problem did not exist before and was created by that repair.

Unknown causality -> A_NEW.

Track consecutive supported B/C failures by semantic_surface inside the current cycle.

Two consecutive supported B/C failures on the same surface require the next Repair Batch to enter STRATEGY_CHANGE.

Model timeout, provider rate limit, crash, invalid external return and unavailable tool are operational failures and do not increment semantic recurrence.

### 27.24 LOW / Improvement dispositions

P4 never creates an automatic Work from LOW or Improvement.

Canonical current-cycle dispositions include at least:

~~~
repaired_current_cycle
retained_history_only
future_work_candidate
no_action_after_adjudication
~~~

A future Work, if later chosen, is created through normal Workline ownership/progression.

P4 stores only current-cycle disposition/provenance.

RB4/P5 owns durable long-lived history/workization provenance.

### 27.25 Verification-only Integration

P4 common validation recognizes Integration Evidence only through a declared side-effect contract.

The adapter declares:

- allowed persistent Project state: none for verification-only;
- allowed external/nested state;
- isolation/disposal/rollback mechanism identity;
- proof that disposable effects were actually isolated/rolled back.

PASS is invalid if verification performs undeclared persistent mutation of:

- Project domain state;
- external service/state;
- nested repository/submodule working tree.

A gitlink identity does not authorize nested working-tree mutation.

When Integration reveals required product/domain repair:

~~~
normal fix Work under existing progression
-> complete normally
-> Formal Review as required
-> rerun Integration
~~~

P4 does not turn Integration into a hidden repair/lifecycle controller.

No new generic Integration runtime is required merely to satisfy P4; this contract applies when an adapter declares Integration Evidence.

### 27.26 Primary implementation files

Expected common production changes:

~~~
src/workline/review/p4.py                  NEW
src/workline/review/paths.py
src/workline/review/records.py
src/workline/review/store.py
src/workline/review/validate.py
src/workline/review/gate.py
src/workline/review/recovery.py
src/workline/review/closure.py
~~~

Expected kind-semantic changes:

~~~
src/workline/review/planning.py
src/workline/review/work_review.py
~~~

Expected owner orchestration changes:

~~~
src/workline/roadmap_review.py
src/workline/start_review.py
~~~

Other files may be changed only when an exact existing responsibility requires it.

Do not add:

- a second Review store;
- a second mutation controller;
- a second publication subsystem;
- a P4 lifecycle state database;
- a maintenance queue for LOW/Improvement.

### 27.27 Existing primitives to reuse

Reuse instead of reimplement:

- records.TaskInput for accepted discovery/adjudication/repair task persistence;
- GateGeneration accepted_tasks / settled_tasks;
- generation mutation serialization/persistence;
- content-addressed canonical serialization/digest;
- ReviewStore canonical read primitives;
- gate reservation/task key patterns;
- RB3-C1 deterministic successor relation;
- RB3-C1 Work set_aside request version support;
- review/recovery.py generic discovery core;
- review/closure.py dependency classes, EvidenceDeclaration, ClassCoverage and MechanismProof;
- planning Candidate builders/reconstruction;
- Work Candidate snapshot/material reconstruction;
- Work resulting-tree / checkout capability machinery;
- existing owner operation mutation and publication paths.

Do not reuse closure.may_reuse() as whole-Review authorization across repaired Candidates.

### 27.28 Canonical runtime authority activation

The P4 implementation candidate must update runtime canonical text in the same candidate.

At minimum inspect/update:

~~~
.claude/skills/review/SKILL.md
.claude/skills/roadmap/SKILL.md
.claude/skills/start/SKILL.md
~~~

Review Skill must state:

- discovery != adjudication;
- P4 raw reports are canonical current-cycle records;
- Problem/Improvement/HUMAN rules;
- blocking H-4 semantics;
- one Repair Batch per Candidate generation;
- G1-G6 P4 shape;
- new Candidate/new Run after repair;
- Evidence-only positive-proof reuse;
- A/B/C and STRATEGY_CHANGE;
- LOW/Improvement nonblocking/no automatic Work;
- Review does not own lifecycle/Git finalization.

Roadmap and START Skills must state their owner responsibilities for:

- P4 opt-in/version dispatch;
- Candidate N+1 adoption;
- successor Run;
- HUMAN_WAIT;
- final Receipt consumption;
- no v1 reinterpretation.

registry routing does not change.

### 27.29 Focused tests — common records/namespace

Add focused coverage for:

- report path digest == canonical report digest;
- report schema strictness and H-3-safe persistence contract;
- adjudication strict schema;
- Repair Batch strict schema;
- Repair Result strict schema;
- canonical round-trip;
- immutable/create-only behavior;
- orphan validation;
- namespace/path safety;
- duplicate/conflicting IDs fail closed.

Recommended:

~~~
tests/test_review_p4_records.py
~~~

### 27.30 Focused tests — adjudication

Cover at least:

- unsupported -> no Finding/no obligation;
- requirement ambiguity -> HUMAN;
- decided requirement failure -> Problem;
- actionable better alternative without failure -> Improvement;
- otherwise dismissed_non_actionable;
- reviewer severity is not final authority;
- LOW Problem nonblocking only when objective holds;
- HIGH/MID Problem blocks;
- Improvement any severity nonblocking;
- duplicate claims merge only under same repair identity;
- uncertain repair identity remains separate;
- strongest supported severity retained on merge;
- every source claim accounted for;
- stable Finding ordering/ID reservation across retry.

Recommended:

~~~
tests/test_review_p4_adjudication.py
~~~

### 27.31 Focused tests — generation state machine

Planning and Work each cover:

~~~
G1 discovery accepted
G2 discovery settled/raw report durable
G3 adjudication accepted
G4 adjudication settled

authorization branch -> G5 sealed Receipt
repair branch        -> G5 repair accepted -> G6 repair settled
HUMAN branch         -> stays G4
~~~

Also cover:

- v1 P2/P3 exact old shape still valid;
- v1 Run never upgraded by inference;
- explicit contract dispatch;
- P4 G4 never mistaken for v1 invalidation G4;
- P4 G5 seal never mistaken for repair G5;
- Receipt generation binding;
- no Receipt on repair branch;
- no G7 within one Candidate-specific P4 Run.

### 27.32 Focused tests — repair and successor

Cover:

- exactly one Repair Batch per Candidate generation;
- all blocking HIGH/MID Findings in one batch;
- Improvement excluded;
- HUMAN excluded;
- LOW excluded unless deliberately repaired;
- repair task persisted before launch;
- failed/invalid return does not settle success;
- Repair Coverage unknown rejects success/readiness;
- shared responsibility + local-only repair rejected/widened;
- Candidate N+1 complete, not patch;
- old candidate_hash immutable;
- result candidate_generation = source + 1;
- deterministic successor reservation reused from RB3-C1;
- one predecessor -> at most one successor;
- set-aside predecessor recorded;
- conflicting successor reconcile;
- runtime cleanup recovery works.

Recommended:

~~~
tests/test_review_p4_repair.py
tests/test_review_p4_recovery.py
~~~

### 27.33 Focused tests — Evidence / reverification

Cover:

- incomplete dependency declaration -> unknown/reacquire;
- unknown class -> reacquire;
- changed concrete Evidence identity -> invalidate;
- changed proof mechanism -> invalidate;
- changed adapter identity/version -> invalidate;
- repair impact invalidating assumption -> invalidate;
- complete unchanged Evidence dependencies may reuse;
- Candidate N discovery/adjudication/Receipt never reused as N+1 authorization;
- LOCAL/SHARED/CONTRACT/FOUNDATION reverification minimums;
- required reverification incomplete -> no convergence.

### 27.34 Focused tests — recurrence and strategy

Cover:

- after-repair timing alone -> A_NEW;
- supported recurrence -> B_RECURRENCE with links;
- supported repair-induced -> C_REPAIR_INDUCED with causal digest;
- unknown causality -> A_NEW;
- B->B same surface -> STRATEGY_CHANGE;
- C->C same surface -> STRATEGY_CHANGE;
- B->C same surface -> STRATEGY_CHANGE;
- C->B same surface -> STRATEGY_CHANGE;
- different semantic surface does not increment same-surface sequence;
- operational timeout/rate-limit/crash does not increment recurrence;
- STRATEGY_CHANGE requirement blocks ordinary unchanged repair strategy.

### 27.35 Focused tests — convergence and Integration

Cover:

- zero Findings + unknown coverage does not converge;
- unresolved HIGH/MID does not converge;
- traceable LOW with objective holding may converge;
- traceable Improvement may converge;
- unresolved HUMAN does not converge;
- unknown Repair Coverage does not converge;
- stale Evidence does not converge;
- pending STRATEGY_CHANGE does not converge;
- verification-only Integration with undeclared Project mutation cannot PASS;
- undeclared external mutation cannot PASS;
- nested repository mutation cannot PASS from gitlink identity alone;
- disposable/rollback-confirmed adapter may PASS;
- Integration-discovered fix routes through normal Work ownership.

### 27.36 Interruption/recovery matrix

At minimum test interruption at:

1. P4 Run reservation;
2. G1 before effect;
3. G1 commit;
4. after one discovery external return before G2;
5. raw report record creation before G2 completion;
6. G2 commit;
7. G3 adjudication TaskInput accepted;
8. adjudicator external return before G4;
9. G4 adjudication record creation;
10. G4 commit;
11. Repair Batch ID reservation;
12. G5 Repair Batch/TaskInput partial apply;
13. G5 commit;
14. repair external return before G6;
15. Candidate N+1 snapshot/Repair Result partial apply;
16. G6 commit;
17. successor reservation;
18. successor before G1;
19. successor discovery cycle;
20. P4 G5 seal;
21. existing owner persistence/Consumption.

Every retry proves:

- same task IDs;
- same Finding IDs;
- same Repair Batch ID;
- same Candidate generation;
- same successor Run ID;
- no duplicate raw report;
- no duplicate adjudication;
- no duplicate Repair Batch/Result;
- no duplicate Receipt;
- no v1 fallback;
- no newest/timestamp selection.

### 27.37 Non-scope

P4 implementation must not implement:

- RB4/P5 long-lived Review history/indexing;
- cross-operation recurrence history;
- Project-local adaptive Profile/Policy (P6);
- Global promotion (P7);
- Phase achievement (RB5);
- RB1 status;
- RB2 performance optimization;
- RB10 Human disposition;
- automatic LOW/Improvement Work queue;
- general self-hosting;
- replacement lifecycle state machine.

### 27.38 Regression gate

Run in this order:

1. new P4 common record/adjudication tests;
2. new P4 planning owner tests;
3. new P4 Work owner tests;
4. P4 repair/recovery/interruption tests;
5. recurrence/convergence/Integration tests;
6. RB3-C1/F4 focused regression;
7. existing P2 planning Review regression;
8. existing P3 Work Review regression;
9. legacy non-Review Roadmap/START regression;
10. canonical Skill/registry tests;
11. full repository regression.

Canonical full command remains:

~~~
py -3 -B -m pytest tests -q
~~~

unless live canonical test tooling has legitimately changed before implementation.

### 27.39 Implementation completion gate

RB3-P4 is complete only when all are true:

- RB3-C1 landed semantics are reused;
- P4 common core exists without lifecycle ownership;
- canonical report/adjudication/Repair Batch/Repair Result records implemented;
- explicit v1/P4 dispatch implemented;
- planning P4 G1-G6 owner flow implemented;
- Work P4 G1-G6 owner flow implemented;
- HUMAN_WAIT implemented without guessed repair;
- Candidate N+1/new Run linkage implemented;
- Evidence-only positive-proof reuse implemented;
- Repair Coverage/impact reverification implemented;
- A/B/C + STRATEGY_CHANGE implemented;
- convergence is obligation/coverage/evidence based;
- verification-only Integration contract enforced where declared;
- canonical Skills updated;
- focused tests PASS;
- v1 P2/P3 regression PASS;
- legacy operations PASS;
- full suite PASS;
- exact candidate SHA/tree/diff frozen for independent review;
- no push/landing occurs before that independent review.

After P4 landing, RB3 is implementation-complete and RB4/P5 becomes the next critical-path block.

---

## 28. RB4-P5 implementation brief — durable Review history / BL-005 front

Status:

~~~
DESIGN_FROZEN
IMPLEMENTATION_BRIEF_FROZEN
READY_TO_IMPLEMENT_AFTER_RB3_P4_LANDS
open_architecture_items = 0
new_HUMAN_policy_decisions = 0
~~~

This section is the canonical implementation-control brief for §13.

It does not replace §13. Where wording conflicts, §13 remains the semantic contract and this section fixes the implementation allocation required to realize it in the current live code.

Execution is dependency-gated:

~~~
RB3-C1 landed
-> RB3-P4 landed
-> RB4-P5 implementation
~~~

P5 must project/reference immutable P1-P4 facts. It must not create a second truth store, lifecycle state machine, scheduler or repair controller.

### 28.1 Core responsibility split

Add one inert common history module:

~~~
src/workline/review/history.py
~~~

It owns:

- P5 history contract/version vocabulary;
- strict schemas/parsers for Run/Finding/Repair/Relation/Human Decision history records;
- canonical builders from immutable source records;
- public-safe structured-summary validation;
- source-reference/digest validation helpers;
- cross-run relation status/type vocabulary;
- no-backfill compatibility predicates;
- history-readiness calculation for P5-capable Runs;
- RB5 handoff reference construction.

It does NOT:

- open lifecycle transitions;
- decide Project progression;
- create Work;
- schedule maintenance;
- modify a Candidate;
- perform repair;
- finalize/publish Git.

History path ownership remains in review/paths.py.
Canonical record reading remains in review/store.py.
Whole-namespace and source cross-validation remains in review/validate.py.

History writes are performed by the existing operation/generation owner at the transition that makes the source fact durable.

Do not add an autonomous P5 daemon/controller.

### 28.2 Versioning and pre-P5 compatibility

P5 is explicit, not inferred from file presence.

Add a common durable history contract identity, for example:

~~~
review-v1-history-v1
~~~

and a distinct P5-capable Effective Policy identity for new P4-capable invocations.

The exact identifier strings may follow the existing naming family, but the following are frozen:

- pre-P5 v1/P3/P4 Runs remain valid without history summaries;
- new P5-capable Runs bind an explicit history contract/policy identity;
- missing history is blocking only for a Run whose stored contract requires it;
- no Run becomes P5-capable because a history directory happens to exist;
- no historical Run is upgraded by shape inference;
- old Candidate/TaskInput/Gate/Receipt/P4 bytes are never rewritten;
- no guessed backfill is performed.

New P5-capable TaskInputs/request envelopes bind the history contract identity needed for replay-safe history obligations.

### 28.3 Canonical history namespace

Extend the closed Review namespace with:

~~~
.workline/review/history/
  runs/<review_run_id>.yaml
  findings/<finding_id>.yaml
  repairs/<repair_batch_id>.yaml
  relations/<relation_id>.yaml
  human-decisions/<decision_id>.yaml
~~~

Add exact path helpers and strict path-shape validation in review/paths.py.

No mutable current-state/index file is canonical.

If derived caches/indexes are added later, they must be rebuildable and may not outrank immutable source/history records.

### 28.4 Stable history IDs

Run/Finding/Repair summary filenames reuse the stable IDs of their immutable source records:

- review_run_id;
- finding_id;
- repair_batch_id.

P5 allocates new stable IDs only for genuinely new history facts:

- cross/later relation;
- Human Decision Evidence.

Add explicit Review ID kinds in ids.py rather than overloading Project-domain relation/derivation semantics.

Recommended kinds:

~~~
review_relation
review_decision
~~~

with unique prefixes that cannot be confused with review_run / Project relation IDs.

Allocation uses the existing Mutation.reserve_id replay-stable semantics.

No history ID is derived from timestamp, file ordering or newest-record selection.

### 28.5 Run summary immutability rule

A Run summary is written exactly once.

Do NOT write an authorized summary immediately at Receipt issuance if the Run may still be invalidated, superseded, set aside, repaired or consumed.

The immutable summary is created at the first transition where the Run's durable P5 disposition is final for that Run.

Required creation boundaries:

- HUMAN_WAIT -> same durable G4 transition that fixes HUMAN_WAIT;
- repaired_to_next_candidate -> same G6 transition that persists Repair Result/Candidate N+1;
- not_authorized -> same owner transition that makes non-authorization terminal for the Run;
- invalidated -> same transition that persists invalidation/Supersession;
- set_aside -> same bound replacement transition where set-aside becomes canonical, unless a stronger final disposition such as repaired_to_next_candidate already exists;
- historical_escape -> same explicit historical-escape transition;
- consumed -> same owner transition that creates the Consumption.

A summary is never rewritten from authorized to consumed or authorized to invalidated.

If a pre-consumption state is recoverable but not yet final, source Gate/Receipt records remain the authority; no summary is required yet.

### 28.6 Consumption-bound Run summary

For a P5-capable Run that reaches normal successful Consumption, create the Run summary in the SAME recoverable owner transition as the Consumption.

The mutation record must durably bind both writes before apply.

Effect ordering must make the history obligation replay-safe:

~~~
Run summary create
-> existing owner terminal/consumption effects
-> exact owner commit
~~~

The resulting Run summary may bind:

~~~
durable_disposition = consumed
consumption_id = exact reserved Consumption ID
~~~

even though both records are first made canonical by the same transition.

Post-commit validation proves the summary against the exact Consumption.

Planning:

- extend the existing review-consumption transition;
- include Run summary + Planning Consumption in the P5-capable metadata commit;
- update the exact planning metadata proof only for explicit P5-capable contract dispatch;
- pre-P5 exact Consumption-only metadata semantics remain unchanged.

Work:

- extend the P5-capable terminal transition to include Run summary before the existing terminal events/Consumption;
- update terminal exact-delta/proof only for explicit P5-capable contract dispatch;
- pre-P5/P3/P4 terminal shapes remain unchanged.

Do not insert an extra standalone history commit between an authorized result commit and its terminal commit when that would change frozen parent/lineage semantics.

### 28.7 Run summary fields

The strict Run summary contains the §13.4 fields and no Candidate/report prose.

At minimum:

- history contract/version;
- review_run_id;
- review_kind;
- target_identity;
- operation_identity;
- candidate_hash;
- candidate_generation when P4 applies;
- review_context_hash;
- effective_policy_hash;
- evidence_digest;
- coverage_digest;
- terminal/latest gate generation + digest;
- adjudication reference/digest when P4 applies;
- ordered finding_ids;
- optional repair_batch_id;
- optional receipt_id;
- optional consumption_id/reference;
- durable_disposition.

Its values are copied/recomputed from immutable source facts.

A mismatch is validation failure.

The summary is never consulted to decide lifecycle progression.

### 28.8 Finding summaries

For a P5-capable P4 Run, persist one Finding summary for every accepted normalized P4 Finding in the SAME G4 generation that persists the canonical P4 adjudication.

Finding summary creation rules:

- Problem/Improvement only;
- unsupported/HUMAN/dismissed claims never receive Finding summaries;
- category/severity/semantic_surface/disposition copy exactly from P4 adjudication;
- source adjudication digest and source report digests are exact;
- public-safe short summary comes only from the P4 canonical public-safe finding statement/summary, never raw external output;
- optional repair_batch linkage may only name a batch already fixed by canonical P4 linkage;
- later relations do not mutate this file.

Later relationship discovery is represented by separate relation records pointing at the Finding.

Do not backpatch a Finding summary to add reverse relation lists.

### 28.9 Repair summaries

For a successful P5-capable P4 repair, persist the Repair summary in the SAME G6 generation as:

- Repair Result;
- Candidate N+1 snapshot;
- source/result linkage.

It binds exactly:

- repair_batch_id;
- source review_run_id;
- source/result candidate hashes;
- finding_ids;
- semantic surfaces;
- selected strategy;
- impact class;
- Repair Coverage digest/result;
- Evidence reuse/invalidation result;
- repair executor identity/version;
- durable result/disposition;
- source Repair Batch digest;
- source Repair Result digest.

No temporal adjacency is accepted as causality.

The Run summary for the repaired source Run is also created in this G6 transition with:

~~~
durable_disposition = repaired_to_next_candidate
~~~

### 28.10 Durable causal material

P5 does not duplicate Candidate bytes or owned deltas when immutable P1-P4 records already carry them.

History records store stable references/digests sufficient to re-open the exact source material.

The Repair summary/history validation must retain/reference:

- source/result Candidate hashes;
- complete operation-owned touched delta identities;
- impact-analysis affected surfaces;
- Repair Coverage Check;
- Evidence references;
- relevant Context/Policy identities;
- external-state fingerprints only when they are already safe/canonical.

Causal status vocabulary:

~~~
supported
unresolved
insufficient_evidence
~~~

Only supported causality may feed confirmed C / recurrence / later P6/P7 learning.

Unknown remains unknown.

### 28.11 Cross-run relation records

P5 relation records are append-only new facts.

Minimum relation types:

~~~
cross_run_recurrence
repair_induced
downstream_escape
future_work_link
~~~

Each record binds:

- relation_id;
- type;
- source identity;
- target identity;
- semantic_surface where applicable;
- status;
- supporting evidence digests;
- public-safe rationale summary;
- source history/source Review digests needed to validate endpoints.

For cross_run_recurrence / repair_induced:

- code/message equality is insufficient;
- semantic responsibility + evidence required;
- supported/unresolved/insufficient_evidence remain distinct;
- only supported counts as confirmed recurrence/causality.

No relation rewrites either endpoint.

### 28.12 Relation creation boundary

A relation is written by the operation that has just made the relationship knowable.

Preferred boundaries:

- cross-run recurrence / repair-induced discovered during a later P5-capable adjudication:
  create the relation in that current G4 transition alongside the current adjudication/history projections;
- downstream escape:
  create the relation in the later supported Review cycle once the cross-lifecycle link has positive evidence;
- future_work_link:
  create it in the normal Work-creation owner transition that creates the future Work when explicit source Finding provenance is supplied.

Do NOT create an independent history commit in the middle of an active fixed Candidate flow, because moving HEAD may invalidate the Candidate.

If a relation cannot safely share its owner transition, defer it until an owner-declared safe boundary; do not mutate lifecycle to force history storage.

### 28.13 Future Work provenance

P5 never creates the future Work.

Add an explicit optional owner input for normal Work creation that carries:

~~~
source_finding_id
~~~

separately from Work semantic content.

The normal CREATE/Roadmap owner:

1. creates the Work under existing rules;
2. validates the source P5 Finding summary/adjudication;
3. reserves one review_relation ID;
4. persists future_work_link in the SAME canonical owner commit/transition.

Primary owner surfaces to inspect:

~~~
src/workline/create.py
src/workline/roadmap.py
src/workline/roadmap_review.py
~~~

Do not put P5 provenance into Work body semantics unless an existing canonical Work field explicitly owns it.

The relation finding_id -> work_id does not:

- add the Work to the originating completion set;
- create reverse Phase/Roadmap dependency;
- change Work selection/progression;
- schedule maintenance.

### 28.14 Human Decision Evidence

A Human Decision Evidence record is created only after a concrete HUMAN adjudication and an actual Human decision.

It binds the §13.11 fields.

For a P5-capable cycle resumed under that decision:

- the next owner invocation receives an explicit structured Human-decision evidence input;
- reserve one review_decision ID;
- persist Human Decision Evidence before launching the next external Review task;
- preferably include it in the new Run's G1 generation so it is committed before any reviewer launch;
- bind decision_id/source digest in the new request/Context linkage as required.

It is evidence that a decision happened, not the canonical requirement/specification itself.

The owner must separately read the actual canonical requirement/authority that the Human changed/confirmed.

If the canonical authority does not reflect the decision when it should:

~~~
STOP / HUMAN authority mismatch
~~~

Do not infer the requirement from the Human Decision Evidence summary.

### 28.15 H-3 sanitation implementation

History schemas contain no field for:

- chain-of-thought;
- hidden reasoning;
- raw chat/model transcript;
- credentials/secrets;
- arbitrary local-machine dump.

Derived summaries must be built from already-canonical public-safe P4 material.

Human-decision / relation rationale inputs are explicit structured public-safe summary fields, not transcript blobs.

At minimum enforce:

- non-empty canonical text;
- bounded/single-line summary form where prose is allowed;
- no control/newline injection;
- exact schema only;
- no arbitrary extra metadata map.

Do not silently redact/transform an unsafe external return into a different semantic claim.

P4 discovery-report sanitation remains the upstream authority for report content.

P1-P4 exact reconstruction material is not deleted or weakened by P5 sanitation.

### 28.16 ReviewStore integration

Extend ReviewStore with narrow readers/listers:

- run_history(review_run_id);
- finding_history(finding_id);
- repair_history(repair_batch_id);
- relation_history(relation_id);
- human_decision_history(decision_id);
- corresponding ID enumerators.

Parsers live in review/history.py.

Do not create a second filesystem store abstraction.

All reads use the same canonical Review path safety as existing Review records.

### 28.17 Validation model

Extend review/validate.py to validate the entire history namespace independently and cross-check sources.

At minimum validate:

- exact directory/path shape;
- strict schema/version;
- filename ID == record ID;
- source record exists;
- source digest matches;
- Run summary source Gate/Receipt/Consumption binding;
- Finding summary equals P4 adjudication category/severity/disposition;
- Finding source report digests exist/match;
- Repair summary matches Repair Batch + Repair Result;
- source/result Candidate hashes match;
- relation endpoints exist and have matching types;
- supported causality has supporting evidence;
- duplicate logical relation identity rejected;
- Human Decision Evidence points to a real HUMAN adjudication entry;
- future_work_link target Work exists and source Finding exists;
- no duplicate history file for one immutable source identity.

A broken history record never changes lifecycle truth.

For explicit P5-capable transitions, the owner additionally calls a narrow:

~~~
require_history_ready(...)
~~~

before crossing a boundary that requires history.

### 28.18 History-readiness gates

Required history gating is versioned.

P5-capable owner transitions refuse to advance when required history is absent/malformed.

Minimum gates:

- G4 cannot be considered history-complete until all normalized Finding summaries required by its adjudication are canonical;
- repaired G6 cannot be considered history-complete until Repair summary + source Run summary are canonical;
- HUMAN_WAIT cannot be considered history-complete until its Run summary is canonical;
- successor launch under a Human decision cannot occur before Human Decision Evidence is canonical;
- normal authorization Consumption cannot complete without the final Run summary in the same transition;
- relation-dependent learning/metrics may use only validated relation records.

Pre-P5 Runs skip these gates by explicit stored contract dispatch.

### 28.19 Downstream escape

A downstream escape relation is recorded only after a later supported Finding can be positively linked to prior Run/Finding/Repair evidence.

It never:

- reopens completed lifecycle;
- rewrites prior Receipt/Consumption;
- changes prior verdict;
- pretends the later Finding was known during earlier authorization.

The later defect follows normal current Workline operations.

The relation is evidence/history only.

### 28.20 No-backfill rule

Do not scan old commits/chat/memory to synthesize P5 history.

Existing pre-P5 Runs have:

~~~
history_status = not_required_by_contract
~~~

not missing.

If old evidence is absent, it remains absent.

No migration is required merely to enable P5 for future Runs.

### 28.21 RB5 handoff

P5 exposes validated references only.

Provide a narrow history projection for RB5 containing, as applicable:

- review_run_id;
- validated Run summary identity/digest;
- Receipt/Consumption identity;
- relevant Finding disposition references;
- unresolved-obligation result;
- Evidence/coverage identity;
- Human Decision Evidence identity.

This projection does not decide achievement.

RB5 owns the Phase/Roadmap achievement record/event binding.

### 28.22 Learning boundary

P5 may expose traceable queries/aggregates for later P6/P7, but no policy change occurs here.

Every metric result must retain source IDs sufficient to reproduce it from immutable Run/Finding/Repair/Relation history.

Only supported causal/recurrence relations count as confirmed.

No mutable aggregate is canonical source truth.

### 28.23 Primary implementation files

Expected new common file:

~~~
src/workline/review/history.py
~~~

Expected canonical namespace/store/validation changes:

~~~
src/workline/review/paths.py
src/workline/review/store.py
src/workline/review/validate.py
src/workline/ids.py
~~~

Expected P4 integration points after P4 lands:

~~~
src/workline/review/p4.py
src/workline/roadmap_review.py
src/workline/start_review.py
~~~

Expected future-Work provenance owner changes only if required by the final explicit API:

~~~
src/workline/create.py
src/workline/roadmap.py
~~~

No separate history database, scheduler or lifecycle module.

### 28.24 Canonical runtime authority activation

The P5 candidate must update runtime canonical text in the same candidate.

At minimum inspect/update:

~~~
.claude/skills/review/SKILL.md
.claude/skills/roadmap/SKILL.md
.claude/skills/start/SKILL.md
~~~

Update .claude/skills/create/SKILL.md only if explicit future_work_link provenance becomes part of CREATE's public contract.

Review Skill must state:

- P5 history is projection/reference, not lifecycle truth;
- immutable history layout;
- no backfill;
- H-3 sanitation;
- LOW/Improvement no automatic Work;
- relation records do not rewrite endpoints;
- supported/unresolved/insufficient causality;
- Human Decision Evidence is not requirement authority;
- required P5 history gates for P5-capable Runs.

Roadmap/START must state owner responsibility for writing required Run/Finding/Repair/Human history at exact transition boundaries.

registry routing does not change.

### 28.25 Focused tests — records/namespace

Add:

~~~
tests/test_review_history_records.py
~~~

Cover:

- all five history path families;
- strict schemas;
- canonical round-trip;
- filename/ID mismatch;
- immutable create-only collision;
- namespace/path safety;
- orphan record validation;
- no transcript/CoT arbitrary fields;
- pre-P5 namespace absence valid.

### 28.26 Focused tests — source projection

Add:

~~~
tests/test_review_history_projection.py
~~~

Cover:

- Run summary source match;
- Gate digest mismatch fails;
- Receipt/Consumption mismatch fails;
- Finding summary exact adjudication category/severity/disposition;
- unsupported/HUMAN cannot become Finding summary;
- Repair summary exact Batch/Result linkage;
- unresolved causality remains unresolved;
- insufficient evidence remains insufficient;
- supported causality requires evidence;
- source summary disagreement never latest-wins.

### 28.27 Focused tests — creation boundaries

Cover interruption/retry for:

1. G4 adjudication + Finding summaries;
2. G4 HUMAN_WAIT + Run summary;
3. G6 Repair Result + Repair summary + repaired Run summary;
4. invalidation/Supersession + invalidated Run summary;
5. set-aside finalization where applicable;
6. planning Consumption + consumed Run summary;
7. Work terminal Consumption + consumed Run summary;
8. Human-decision evidence in successor G1;
9. future_work_link in normal Work creation.

Every retry proves:

- same summary path/bytes;
- same relation/decision ID;
- no duplicate source summary;
- no overwrite;
- no inferred backfill;
- no lifecycle effect caused by history replay.

### 28.28 Focused tests — runtime cleanup / clone

Cover:

- deleting .workline/runtime/** does not remove required history;
- fresh clone reconstructs/validates all P5 references;
- no runtime report copy is required to validate history;
- P5 history alone cannot reconstruct/replace missing P1-P4 source facts;
- missing source -> validation failure.

### 28.29 Focused tests — LOW / Improvement / future Work

Cover:

- LOW creates no automatic Work;
- Improvement any severity creates no automatic Work;
- retained_history_only/no_action remain valid;
- future_work_candidate itself creates no Work;
- explicit normal Work creation may add future_work_link;
- later relation does not rewrite Finding;
- future Work does not enter originating Phase/Roadmap completion dependency;
- existing Work selection/progression unchanged.

### 28.30 Focused tests — Human Decision Evidence

Cover:

- only a real HUMAN adjudication may be referenced;
- decision evidence requires exact source identity;
- no transcript/freeform metadata;
- decision evidence does not replace canonical authority;
- authority mismatch blocks resume where authority should have changed;
- evidence persisted before successor external launch;
- retry reuses same decision ID/bytes.

### 28.31 Compatibility regression

Must explicitly prove:

- existing P1/P2/P3 Runs valid without P5;
- RB3-C1/F4 regression PASS;
- P4-only Runs valid without P5 summaries;
- P5-capable Runs cannot step over required missing history;
- existing Planning Consumption proof unchanged for pre-P5;
- existing Work terminal proof unchanged for pre-P5;
- legacy non-Review Roadmap/START/CREATE unchanged.

### 28.32 Full regression order

Run:

1. P5 record/namespace tests;
2. P5 source-projection tests;
3. P5 owner-boundary/interruption tests;
4. P5 clone/runtime-cleanup tests;
5. LOW/Improvement/future-Work tests;
6. Human Decision Evidence tests;
7. P4 focused regression;
8. RB3-C1/F4 regression;
9. P2 planning Review regression;
10. P3 Work Review regression;
11. legacy Roadmap/START/CREATE regression;
12. canonical Skill/registry tests;
13. full repository suite.

Canonical full command:

~~~
py -3 -B -m pytest tests -q
~~~

unless canonical test tooling has legitimately changed before implementation.

### 28.33 Explicit non-scope

RB4/P5 must not implement:

- Phase/Roadmap achievement decision (RB5);
- Project-local adaptive policy (RB6/P6);
- Global promotion (RB7/P7);
- automatic LOW/Improvement Work creation;
- maintenance queue/scheduler;
- mutable history index as authority;
- historical rationale backfill;
- lifecycle reopen from downstream escape;
- self-hosting;
- RB1 status semantics beyond later additive exposure;
- RB10 disposition.

### 28.34 Implementation completion gate

RB4/P5 is complete only when:

- RB3/P4 landed semantics are reused;
- history namespace implemented;
- Run/Finding/Repair/Relation/Human Decision records strict and immutable;
- every summary validates against immutable P1-P4 source facts;
- H-3 sanitation boundary enforced structurally;
- final Run summary timing cannot require later rewrite;
- P5-capable Consumption cannot step over required history;
- repair/HUMAN history is replay-safe;
- no backfill;
- no automatic LOW/Improvement Work;
- future_work_link is provenance only;
- downstream escape never rewrites lifecycle;
- RB5 handoff references are available;
- canonical Skills updated;
- focused tests PASS;
- P4/RB3/P2/P3 regressions PASS;
- legacy operations PASS;
- full suite PASS;
- exact candidate SHA/tree/diff frozen for independent review;
- no push/landing before independent exact-candidate review PASS.

After RB4 landing, RB5 and RB6 are both structurally unblocked; the critical-path next block is RB6/P6, while RB5 may proceed in parallel.

---

## 29. RB1 implementation brief — BL-006 read-only status/context

Status:

~~~
DESIGN_FROZEN
IMPLEMENTATION_BRIEF_FROZEN
READY_TO_IMPLEMENT
open_architecture_items = 0
new_HUMAN_policy_decisions = 0
~~~

This section is the canonical implementation-control brief for §9.

It does not replace §9. Where wording conflicts, §9 remains the semantic contract and this section fixes the implementation allocation required to realize it in the current live code.

RB1 is independent of the RB3/RB4 execution chain. Later RB5/RB6/RB10 status fields are additive and must not redefine the v1 base fields frozen here.

### 29.1 Primary implementation shape

Add one inert status model/reader module:

~~~
src/workline/status.py
~~~

It owns:

- B0/B1 snapshot witnesses;
- tolerant read-only field collection;
- the versioned StatusModel;
- lifecycle diagnostic projection;
- pending-mutation diagnostic projection;
- authority diagnostics;
- local Git/push-destination diagnostics;
- Review diagnostics;
- human rendering;
- deterministic JSON rendering.

It does NOT:

- open a Mutation;
- acquire the Project execution lock;
- write canonical/runtime/cache data;
- repair/cleanup anything;
- launch a reviewer/external tool;
- contact a network remote;
- decide lifecycle state independently of existing state/selection semantics.

CLI wiring is owned by:

~~~
src/workline/cli.py
run-workline.py
~~~

Existing semantic owners remain:

~~~
src/workline/state.py
src/workline/roadmap.py
src/workline/start.py
src/workline/validate.py
src/workline/registry.py
src/workline/review/*
~~~

Do not create a second progression model in status.py.

### 29.2 Canonical CLI

Add:

~~~
run-workline.py status <project-root>
run-workline.py status <project-root> --json
~~~

The two forms render the same in-memory StatusModel.

No renderer performs an additional semantic read.

The command never changes cwd to the target Project.

### 29.3 Launcher cross-Project exception

The current launcher binds every CLI invocation to the configured Workline root of the Project containing the caller's current working directory.

That is correct for every mutation-capable command, but it would prevent the §9.1 cross-Project read-only status command.

Refactor the launcher narrowly:

- isolated-mode check remains mandatory;
- loaded-module origin verification against the launcher Workline root remains mandatory;
- normal API activate() behavior remains unchanged;
- every existing CLI command keeps the current CWD Project configured-root check;
- only when the parsed top-level CLI command is exactly status may main() skip the CWD Project configured-root binding.

The target Project's configured Workline root is then read by status as diagnostic data.

A target configured-root mismatch is reported under authority; it is not used to grant mutation authority.

This exception must be impossible to select for any mutation-capable command.

### 29.4 CLI exit behavior

status is a diagnostic command.

When a StatusModel can be rendered, the command exits successfully even when:

- validation failed;
- the Project is changing during the read;
- the configured Workline root is broken/mismatched;
- a pending mutation requires reconcile;
- Review records are invalid.

Those conditions are stable model fields, not command-crash conditions.

Argument parsing failure keeps argparse's ordinary failure behavior.

A fatal implementation defect that prevents construction/rendering of any StatusModel is non-zero.

Do not turn an invalid Project ledger into an early not_a_project exit when independent diagnostics can still be emitted.

### 29.5 StatusModel v1

The machine model always contains these top-level fields:

~~~
schema
version
snapshot_consistency
snapshot_reason

project
authority
git
lifecycle
pending
validation
review
completion
policy
~~~

Freeze:

~~~
schema  = workline-status
version = 1
~~~

All lists are deterministically sorted.

Stable IDs/status enums are separate from display text.

Unknown and not-applicable are explicit states, never omitted-key inference.

completion and policy are present from v1 even before RB5/RB6:

~~~
completion.status = not_available_by_contract
policy.status     = not_available_by_contract
~~~

Later RBs may add fields/change those section status values, but may not redefine existing RB1 fields.

### 29.6 Snapshot witnesses B0/B1

One status attempt records B0:

1. exact local HEAD object ID;
2. exact full branch ref, or detached state;
3. pending mutation identity witness set;
4. canonical status-surface fingerprint.

It then builds the model and re-reads the same four witnesses as B1.

Pending mutation identity witness set is sorted and contains enough immutable observation to detect a same-ID record changing during the read:

~~~
mutation filename / mutation_id
SHA-256 of the exact durable record bytes
parse-state marker
~~~

A malformed mutation filename/record remains an observed witness; it is not skipped.

The canonical status-surface fingerprint is SHA-256 over a deterministic no-follow inventory of the target Project's canonical .workline tree, excluding .workline/runtime/**.

Each inventory entry binds:

- repository-relative path;
- entry kind: regular_file / directory / indirection / other;
- for a regular file: SHA-256 of exact bytes;
- for an indirection/other: a stable structural marker, never followed.

This automatically includes future canonical Review/history/profile records without changing RB1 semantics.

Runtime lock/holder/tmp files are excluded.

Pending mutation durable records are covered separately by witness 3.

No symlink/junction/reparse target is traversed merely to fingerprint status.

### 29.7 Snapshot result

If B0 == B1:

~~~
snapshot_consistency = stable_read
snapshot_reason      = null
~~~

If any witness differs:

~~~
snapshot_consistency = changing
snapshot_reason      = project_changed_during_status
~~~

One immediate rebuild/re-read retry is permitted.

There is no unbounded retry/wait loop.

When final result is changing:

- current selected Roadmap/Phase/Work fields are null;
- next selected fields are null;
- those fields carry reason project_changed_during_status;
- independently observed diagnostic facts may still be returned.

status never claims atomicity it did not obtain.

### 29.8 Read-only enforcement

status may call only local read primitives.

Allowed categories include:

- ProjectStore readers;
- ProjectView.load;
- validate_project;
- MutationController durable-record inspection only;
- ReviewStore/read-only validation;
- registry/implementation readers;
- local git rev-parse/symbolic-ref/status/diff/config/remote-get-url reads.

Explicitly forbidden from the status call graph:

- MutationController.open/begin/load-for-write;
- Mutation.reserve_id/add_effects/apply/complete/abandon;
- project_operation;
- any holder/lock creation;
- durable_write_text;
- Git add/commit/ref/config mutation;
- fetch/pull/push/ls-remote;
- reviewer/provider launch;
- activation/pin/backfill/cleanup.

Tests must make these boundaries mechanical, not only prose expectations.

### 29.9 Project section and tolerant partial reads

project contains at least:

- requested/root path;
- root readability;
- established-project marker/readability;
- configured Workline root when readable;
- exact reason when unavailable.

Field providers are isolated.

A failure reading project.yaml does not suppress local Git diagnostics.

A failure loading ProjectView does not suppress pending mutation diagnostics.

A broken Review namespace does not suppress lifecycle facts that are independently readable.

The target root being absent/not a directory is represented diagnostically when the model itself can still be produced.

No field silently substitutes guessed data after a reader failure.

### 29.10 Validation section

Reuse validate_project(store).

Expose:

~~~
status = pass | failed | unavailable
problems = [{code, message}, ...]
~~~

Problems are deterministically ordered.

Validation failure does not suppress other independent status sections.

Do not call validation PASS merely because some ProjectView fields loaded.

RB10 N6-3 later tightens bootstrap structural-cause preservation; RB1 consumes that result additively without changing this interface.

### 29.11 Authority section

authority contains at least:

- running Workline root;
- configured Workline root when readable;
- running-vs-configured implementation identity result;
- registry validation result;
- registry content digest when readable;
- canonical authority inventory.

Add a public read-only registry authority inventory helper rather than importing registry private parsers from status.py.

The inventory is deterministic and contains stable facts only:

- workline stable authority ID;
- target path as registered;
- declared context where applicable;
- SHA-256 of the exact target bytes when readable.

Include required rules and all registry-routed canonical Skills.

Do not copy Skill/rule prose into status.

If registry validation fails:

- report all validation problems;
- do not invent a partial valid routing inventory;
- registry file digest may still be reported when its bytes are readable.

The running implementation identity helper may be minimally exposed from implementation.py; do not duplicate module-origin verification in status.py.

### 29.12 Git section

Use only local Git reads.

Expose at least:

- repository top-level;
- full branch ref;
- display branch name;
- detached status;
- HEAD;
- deterministic dirty/status entries;
- approved destination pin;
- active local push locator;
- local_locator_matches_pin;
- local diagnostic problem when locator cannot be resolved safely;
- remote_publication_state = not_checked.

The active locator uses the existing destination/gitcmd local configuration resolution.

Never call a remote.

Credential-bearing locators are never emitted raw.

Use the existing pushurl secret check/redaction behavior.

approved pin values remain treated as secret-free by their canonical schema, but renderer still fails safe rather than printing credential material.

### 29.13 Lifecycle section — no new progression algorithm

Lifecycle status uses ProjectView and pure selection helpers shared with Roadmap/START.

Do not copy the selection algorithm into status.py.

Refactor only where necessary so the existing owner and status call the SAME pure calculation.

Phase candidate calculation:

- active Roadmap mechanics remain state.py/roadmap.py;
- startable Phases use ProjectView.startable_phases();
- planned_next preference uses ProjectView.planned_next_preference()/choose_startable semantics;
- ambiguity returns the candidate set, never an invented winner.

Work candidate calculation:

- current in-flight Work uses the same definition as START continuation:
  IN_PROGRESS and has_target within the effective current scope;
- more than one is ambiguity/blocking, not a winner;
- next startable candidates use the same return_to filtering and planned_next preference START uses;
- factor this candidate computation into a pure helper and make START use it too, so status cannot drift.

For standalone Work where no canonical implicit entry/scope exists:

- report observable startable standalone candidates;
- do not invent one implicit START entry;
- selected next remains null unless existing semantics mechanically determine it.

### 29.14 Current Roadmap/Phase/Work projection

current is diagnostic, not lifecycle authority.

Roadmap:

- list lifecycle states for all Roadmaps;
- current_roadmap_id only when the existing lifecycle facts leave exactly one mechanically current active Roadmap;
- otherwise null with ambiguity/no-current reason.

Phase:

- only under a mechanically unique Roadmap context;
- a currently started Phase is derived from existing Phase state;
- exactly one -> current_phase_id;
- several -> ambiguity;
- none -> no current Phase, then next Phase candidates may be reported.

Work:

- only under a mechanically established scope;
- exactly one START-compatible in-flight target Work -> current_work_id;
- several -> multiple-target blocker;
- none -> next candidate projection.

No mtime/filename/newest-ID rule exists.

### 29.15 Pending mutation tolerant inspection

MutationController.list_records() is intentionally strict and one malformed file currently aborts enumeration.

Add a read-only tolerant inspection API in mutation.py that:

- enumerates mutation record files deterministically;
- reads exact bytes without writing;
- applies the existing ownership/parser validation to each record independently;
- returns either the validated record or its exact structural error;
- never constructs a writable/resumable Mutation object;
- never opens/repairs/abandons a mutation.

Existing strict list_records()/list_pending() semantics remain unchanged for operation owners.

status uses only the tolerant inspection API.

### 29.16 Pending mutation model

For each pending/invalid record expose only diagnostic-safe structured fields:

- mutation_id/filename identity;
- owner when proven;
- safe operation/contract/target identity subset;
- recorded write scope;
- durable stage/effect-count summary;
- resume classification;
- exact diagnostic code/reason.

Do NOT dump arbitrary invocation/request payloads.

Do NOT expose secret-bearing values.

Resume classification vocabulary:

~~~
pending_resumable
pending_reconcile_required
disposed_by_human
unknown_or_invalid
~~~

plus top-level none when no pending record exists.

pending_resumable requires a positive read-only owner-specific proof.

A structurally valid pending record is NOT automatically resumable.

Owner-specific status probes must reuse the same durable predicates used by the operation's normal recovery path, but must not call that path if it mutates/opens/closes anything.

If no positive read-only probe exists:

~~~
unknown_or_invalid
~~~

rather than optimistic resume.

RB10 N4 later adds disposed_by_human classification through the same stable field.

### 29.17 Pending state precedence over hypothetical next

If a pending mutation affects current progression and its safe disposition is unresolved:

- report it under pending/Blocked-Waiting;
- do not claim a hypothetical new current/next action as authoritative;
- observed candidate sets may still be shown as observations;
- selected current/next fields are null with the pending-state reason where appropriate.

Do not hide a pending record because canonical lifecycle state appears to have advanced.

Do not call it completed from effects alone.

### 29.18 Review diagnostic projection

Use canonical Review records only.

A narrow inert Review-status helper may live in:

~~~
src/workline/review/status.py
~~~

if keeping this logic out of the generic status module improves responsibility separation.

It reads:

- activation;
- validated Gate chains;
- Receipt;
- Supersession;
- Consumption;
- P4 adjudication/obligation state when available;
- RB3-C1/P4 explicit set-aside/successor linkage when available.

It exposes no raw discovery/reviewer prose.

Per Run expose at least:

- review_run_id;
- review_kind;
- target_identity;
- latest_generation;
- state;
- receipt status;
- consumption status;
- blocking-obligation count when P4 provides it;
- exact diagnostic reason on invalidity.

State is derived only when mechanically proven:

~~~
open
sealed
invalidated
set_aside
consumed
invalid
~~~

Review state is separate from lifecycle state and never overrides ProjectView.

### 29.19 Activation diagnostics

Activation is:

~~~
absent
present
invalid
~~~

present means the canonical activation record reads under its stored contract and the applicable read-only activation validation is satisfied.

A malformed/contradictory activation is invalid with its validation code/reason, never absent.

status does not create, repair or recompute activation.

### 29.20 completion and policy additive slots

RB1 v1 always emits:

~~~
completion:
  status: not_available_by_contract

policy:
  status: not_available_by_contract
~~~

RB5 later fills completion using its validated evidence handoff.

RB6 later fills policy/Profile/observation fields.

RB10 N4 may add Human disposition detail under pending.

Those RBs may add new nested fields/status values only.

They may not change:

- schema/version;
- snapshot semantics;
- lifecycle base meaning;
- pending base meaning;
- Git base meaning;
- authority base meaning.

### 29.21 Human-readable renderer

Default output renders the StatusModel in this order:

~~~
Project
Authority
Current
Next
Blocked/Waiting
Pending mutation
Review
Validation
Git / push destination
Achievement
Policy
~~~

Rendering is presentation only.

No field is recomputed during rendering.

An error section is never hidden merely to make output concise.

### 29.22 JSON determinism/safety

JSON output:

- uses sorted deterministic arrays where order has no semantic meaning;
- preserves semantically ordered arrays only where the model defines order;
- contains stable IDs separately from labels/messages;
- uses null plus explicit reason/status for unavailable selected values;
- never requires prose parsing to recover state;
- never emits credential-bearing URL text;
- never emits raw reviewer output;
- never emits mutation arbitrary request payloads.

Two calls over the same stable snapshot from target cwd and an external cwd produce the same JSON bytes, aside from no field that records caller cwd/time/process identity.

No current timestamp is part of the model.

### 29.23 Expected production files

Primary new files:

~~~
src/workline/status.py
src/workline/review/status.py   optional narrow Review projection
~~~

Expected integration changes:

~~~
run-workline.py
src/workline/cli.py
src/workline/mutation.py
src/workline/registry.py
src/workline/implementation.py  only for narrow read-only identity helper
src/workline/state.py           only for shared pure selection projection
src/workline/roadmap.py         only to reuse shared pure selection
src/workline/start.py           only to reuse shared pure selection
~~~

Review modules are changed only if a narrow read-only status projection cannot be expressed from existing public readers after RB3/P4 lands.

No new persistence/store/database.

### 29.24 Canonical runtime authority activation

The RB1 candidate must update runtime canonical text in the same candidate.

At minimum inspect/update:

~~~
registry.md
rules/git
.claude/skills/project-router/SKILL.md
~~~

Update other Skills only when the public status command belongs in their actual responsibility.

Canonical text must state:

- status is read-only and cross-Project capable;
- no execution lock/mutation/network;
- current/next are diagnostic projections of existing semantics;
- changing snapshot suppresses authoritative current/next selection;
- status does not progress Roadmap/Phase/Work;
- status output is not lifecycle truth independent of canonical records.

No new Skill/routing ID is introduced.

### 29.25 Focused tests — hard read-only boundary

Add:

~~~
tests/test_status_read_only.py
~~~

Mechanically prove:

- canonical Project bytes unchanged;
- .workline/runtime bytes/entries unchanged;
- no lock/holder directory/file created;
- MutationController.open/begin never called;
- project_operation never called;
- no durable writer called;
- no Git write command called;
- no fetch/pull/push/ls-remote called;
- no reviewer/external callable invoked.

Run against:

- valid Project;
- invalid Project;
- pending mutation;
- Review-enabled Project.

### 29.26 Focused tests — launcher/cross-Project

Cover:

- status from target Project cwd;
- status from neutral external cwd;
- status launched while cwd is another established Workline Project;
- all three inspect the explicit target and yield equivalent model bytes;
- every mutation-capable command still enforces the original CWD configured-root binding;
- API activate() behavior unchanged.

### 29.27 Focused tests — snapshot consistency

Cover:

- stable B0/B1 -> stable_read;
- HEAD moves -> changing;
- branch ref changes -> changing;
- canonical file content changes -> changing;
- canonical entry added/removed -> changing;
- indirection structural change -> changing;
- same mutation ID but mutation bytes change -> changing;
- pending mutation added/removed -> changing;
- optional one retry can recover one transient mismatch;
- repeated change never loops indefinitely;
- final changing model has null authoritative current/next with reason.

### 29.28 Focused tests — lifecycle selection

Cover:

- unique active Roadmap;
- multiple active Roadmaps -> ambiguity;
- unique current started Phase;
- multiple current Phases -> ambiguity;
- one in-flight target Work;
- multiple target Works -> blocker;
- startable Phase planned_next preference exactly matches Roadmap;
- Work return_to/planned_next filtering exactly matches START;
- no candidate diagnosis;
- standalone candidates do not invent implicit entry;
- pending progression mutation suppresses authoritative hypothetical next;
- no filename/mtime ordering changes a result.

### 29.29 Focused tests — pending mutations

Cover:

- none;
- one positively resumable known owner;
- owner probe says reconcile;
- structurally valid but unsupported probe -> unknown_or_invalid;
- malformed filename;
- malformed record;
- several records where one malformed does not hide the others;
- scope/invocation diagnostic safety;
- arbitrary invocation payload not emitted;
- later disposed_by_human additive state.

### 29.30 Focused tests — Review

Cover:

- Review namespace absent;
- activation absent;
- activation valid;
- activation malformed/contradictory -> invalid;
- open Run;
- sealed Run;
- superseded/invalidated Run;
- consumed Run;
- set-aside Run once explicit successor semantics are available;
- malformed chain -> invalid reason;
- P4 blocking obligation count when available;
- no raw report text in model.

### 29.31 Focused tests — validation/Git/authority

Cover:

- validate pass;
- invalid project.yaml still emits diagnostics;
- unreadable entity/ledger still emits independent sections;
- detached HEAD;
- dirty paths deterministic;
- no remote;
- unpinned remote;
- pinned matching locator;
- pinned mismatching locator;
- multiple push locators;
- credential-bearing locator redacted/not emitted;
- remote_publication_state always not_checked;
- configured Workline root missing;
- registry invalid;
- implementation mismatch;
- authority inventory stable IDs/target/digests only.

### 29.32 JSON/human renderer tests

Cover:

- schema/version exact;
- deterministic JSON bytes;
- stable enums/IDs do not require prose parsing;
- target cwd vs external cwd JSON equality;
- no caller cwd/time/pid/host field;
- human renderer is derived only from the same StatusModel;
- validation error remains visible in human output;
- completion/policy base slots remain stable when later fields are injected.

### 29.33 Regression gate

Run:

1. RB1 status read-only tests;
2. launcher/cross-Project tests;
3. snapshot tests;
4. lifecycle selection equivalence tests;
5. pending mutation tests;
6. Review status tests;
7. validation/Git/authority tests;
8. JSON/human renderer tests;
9. existing state.py/Roadmap selection regression;
10. existing START continuation regression;
11. existing validate-project regression;
12. Review P1-P4 regression available at implementation time;
13. canonical Skill/registry tests;
14. full repository suite.

Canonical full command:

~~~
py -3 -B -m pytest tests -q
~~~

unless canonical test tooling has legitimately changed before implementation.

### 29.34 Explicit non-scope

RB1 must not implement:

- remote publication inspection;
- networked status;
- automatic resume;
- automatic repair/cleanup;
- status cache/index;
- RB2 optimization;
- RB5 achievement decision;
- RB6 policy adaptation;
- RB10 Human disposition itself;
- lifecycle/progression redesign;
- Review raw-history display;
- a new Skill or routing branch.

### 29.35 Implementation completion gate

RB1 is complete only when:

- canonical status CLI exists;
- one StatusModel feeds human and JSON output;
- launcher cross-Project exception is status-only;
- zero-write/no-lock/no-network boundary is mechanically tested;
- B0/B1 consistency works;
- changing suppresses authoritative current/next;
- state/Roadmap/START selection semantics are shared, not copied;
- malformed Project/mutation/Review records remain diagnostic rather than destructive;
- local Git/push diagnostics are offline;
- authority identities/digests are exposed without copying prose;
- completion/policy additive slots are frozen;
- canonical runtime authority text updated;
- focused tests PASS;
- existing lifecycle/Review/validation regressions PASS;
- full suite PASS;
- exact candidate SHA/tree/diff frozen for independent review;
- no push/landing before independent exact-candidate review PASS.

RB2 may begin measurement only after this RB1 implementation lands, because RB2 measures the supported status/validate recovery path rather than a hypothetical one.
