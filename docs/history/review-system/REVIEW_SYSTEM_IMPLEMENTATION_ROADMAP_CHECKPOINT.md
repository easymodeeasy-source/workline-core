# Review System Implementation Roadmap Checkpoint

Status: DESIGN READY / IMPLEMENTATION NOT STARTED

This file is a design checkpoint, not normative authority. Runtime authority remains `registry.md` plus registry-routed canonical Skills. The purpose of this checkpoint is to preserve the current Review System design and implementation roadmap so it can be independently reviewed before implementation.

## 1. Core principle

Review System does not replace Roadmap / START / `state.py` lifecycle responsibilities.

```text
Roadmap / START / state.py
  -> progression, registration, lifecycle, completion, generated state

Review System
  -> judge whether a frozen candidate may proceed to the next existing lifecycle boundary
```

No `review_passed` / `review_status` field is added to generated Work / Phase / Roadmap state. Review convergence is a quality obligation and recovery checkpoint, not a second domain lifecycle.

## 2. Review kinds

Four primary review kinds:

1. Roadmap Review
2. Phase Design Review
3. Work Formal Review
4. Phase Integration Check

Common flow:

```text
freeze Candidate
-> freeze Review Context
-> freeze Effective Policy
-> independent discovery
-> Coverage records
-> freeze Raw Reports
-> Adjudication
-> REPAIR / HUMAN / ACCEPTED
```

Accepted display verdicts:

- Roadmap Review: READY
- Phase Design Review: READY
- Work Formal Review: CONVERGED
- Phase Integration Check: PASS

## 3. Candidate / Context / Policy / Evidence

Keep these distinct:

```text
Candidate      = what was reviewed
Review Context = what defines correctness for this review
Effective Policy = how it was reviewed
Evidence       = what has already been verified
```

Bind each Review Run with:

```text
candidate_hash
review_context_hash
effective_policy_hash
```

Tests are Evidence, not Candidate.

### Roadmap candidate

Use the existing `RoadmapPlan` semantics and reuse the existing recovery identity (`roadmap_request_identity(plan)`) rather than inventing a second normalization.

### Phase Design candidate

Use the existing `PhaseEntryDesign` semantics and reuse `design_identity(design)`.

### Work candidate

Conceptual model:

```text
Base HEAD
+ Baseline Overlay (pre-existing tracked dirty state, not Work-owned)
+ Work-owned Delta (execution + Review Repair changes)
```

Reviewer must inspect a frozen read-only Candidate Tree, not the mutable live workspace.

Candidate manifest conceptually contains:

```text
candidate_id
base_head
baseline_overlay
owned_delta
ownership
candidate_hash
```

Do not auto-import arbitrary untracked files. Include explicit Work result artifacts and explicit Review Context inputs only. Pre-existing dirty ownership protections are never weakened by Review.

Repair never mutates an old Candidate. It produces a new immutable generation:

```text
Candidate C1 -> Repair -> Candidate C2
```

## 4. Reviewer model

Discovery is fresh; adjudication is history-aware.

A reviewer receives:

- fixed Candidate
- current requirement/spec/desired state
- required evidence
- assigned viewpoint
- Effective Policy

Normally it does not receive prior Findings, Repair history, or other reviewers' Findings.

Reviewer result conceptually contains:

```text
reviewer
viewpoint
candidate_id
candidate_hash
coverage:
  inspected
  questions_checked
  evidence_used
  not_inspected
  undecidable
raw_reports
counterexample_check
status: completed | failed
```

Reviewer does not finalize Problem/Improvement, severity, A/B/C, or HUMAN. Adjudication does.

Reviewer execution is abstracted behind a Reviewer Executor Protocol. Required properties are fixed Candidate, independent context, read-only behavior, and structured output. Parallelism and any specific Claude Code subagent implementation are adapters/optimizations, not Review semantics.

## 5. Finding classification and severity

Adjudication:

```text
review statement
-> is claim supported?
   NO -> dismiss
   YES
   -> does artifact satisfy currently decided requirement/goal?
      NO -> Problem
      YES
      -> genuinely better alternative?
         YES -> Improvement
         NO -> dismiss
```

If deciding requires changing/choosing product/spec/requirement, use HUMAN.

Categories:

- Problem
- Improvement

Severity:

- HIGH
- MID
- LOW

Repair policy:

```text
HIGH -> current review cycle
MID  -> current review cycle
LOW  -> independent Work when not repaired immediately
```

Useful severity question: "Knowing this, may the system proceed to the next Work?"

Duplicate reports merge by repair identity, not wording: same central issue + same repair location/strategy + one repair resolves all. Uncertain -> keep separate. Merged severity is the strongest supported severity; provenance is preserved.

## 6. A / B / C recurrence

- A: newly discovered issue; may have existed before
- B: substantially the same issue reappears after a prior Repair
- C: a prior Repair itself caused a genuinely new issue that did not exist before

C requires strong causality. "Found after repair" is insufficient.

Repair instability rule:

```text
Two supported repair failures in the same semantic surface
-> stop assuming another local patch is correct
-> strategy change
```

Possible strategy changes include shared/common mechanism repair, widening scope, state/lifecycle reconsideration, rollback/replacement of unstable repair, or a simpler invariant. Escalate to HUMAN only when a human-controlled boundary is crossed.

Phase 4 implementation supports same-Review-Run recurrence. Cross-run recurrence is intentionally deferred until durable history exists in Phase 5.

## 7. Repair Coverage Check and Pre-Review Quality Pass

After Repair, before Formal Review:

Repair Coverage Check asks:

1. Are there other paths with the same responsibility/decision?
2. Should a shared mechanism be repaired rather than a local site?
3. Can the applicable path set be enumerated?

Pre-Review Quality Pass:

1. enumerate concrete verification surface
2. map evidence to the surface
3. expose unverified surface
4. after repair, reevaluate invalidated evidence
5. Pre-Review PASS is not Formal Review PASS

Verification depth is proportional to semantic impact. State/contract/lifecycle changes require writers/readers/interruption/failure/retry/resume coverage. Broad shared infrastructure may require broad targeted integration and a full suite only when genuinely necessary.

Evidence reuse:

```text
assumptions unchanged -> reuse allowed
changed               -> reacquire
uncertain              -> reacquire
```

Formal convergence requires all required reviewers complete, coverage resolved, unadjudicated Raw Reports zero, HIGH/MID zero, LOW obligations properly handled, required reverification complete, latest Coverage Check complete, no unresolved repair-induced Problem, and no required HUMAN pending.

## 8. HUMAN semantics

Do not globally stop automation because one HUMAN obligation exists.

```text
repair independent of HUMAN decision
-> proceed now

repair meaning may change after HUMAN decision
-> may proceed, then reevaluate

repair itself depends on HUMAN decision
-> wait
```

Candidate may advance through independent repairs while HUMAN is pending, but no final Attestation may be issued while required HUMAN obligations remain.

HUMAN categories include:

- Product / Requirement
- Security / Permission
- External contract / irreversible action
- Canonical authority
- Capability / policy boundary

Hard implementation questions are not HUMAN by themselves.

A human response is Decision Evidence bound to `decision_context_hash`.

## 9. Work Formal Review lifecycle

Target flow:

```text
START
-> Work execution
-> Completed-like result
-> Review Entry Safety Check
-> Repair Coverage Check
-> Pre-Review Quality Pass
-> freeze Candidate
-> Work Formal Review
-> Adjudication
   HIGH/MID -> Repair -> new Candidate -> impacted re-review
   LOW      -> repair now or independent LOW Work
   HUMAN    -> wait only where dependent
   obligations=0 -> CONVERGED
-> Review Attestation
-> existing completion precheck
-> Git persistence
-> terminal finalization
-> work_completed
```

Important semantic change for Review-aware START: executor `Completed` means "reviewable implementation result exists", not immediately "Work is terminally completed".

Review System owns required outcomes, Findings, Coverage, Adjudication, rerun scope, and Attestation. START/domain executor owns actual mutation/repair and lifecycle.

### Review repair execution

START re-invokes the same domain executor with an explicit repair purpose rather than creating a new Repair Controller.

Conceptually:

```text
ExecutionContext.purpose = execute | review_repair
```

`ReviewRepairRequest` includes review run, source candidate, Finding refs, severity, affected surface, required outcome, repair identity, recurrence class, strategy, and required reverification.

Review tells the executor what outcome must hold; executor decides how to implement it.

Do not union result-path lists and treat that as final delta. START tracks touched/owned paths but recomputes the effective current delta for each new Candidate.

## 10. Phase Integration Check

`phase_integration_check` Work does not receive another full Work Formal Review. It gets a dedicated lightweight integration review before terminalization.

```text
integration Work result exists
-> Phase Integration Check
-> REPAIR / HUMAN / PASS
-> existing completion precheck
-> Git / terminal finalization
-> Phase completion remains derived by existing state machinery
```

Checks Phase goal, cross-Work integration, artifacts/results, boundary/next Phase prerequisites, hidden unresolved issues, and evidence.

If integration discovers an issue in an already-completed Work, do not reopen the completed Work. Create fix Work / re-integration through existing START/CREATE mechanisms.

## 11. Review Attestation and recovery bridge

Review convergence is not a domain event. Review Skill returns an Attestation; operation owner persists a checkpoint in its own pending mutation.

Conceptual Attestation:

```text
review_run_id
review_kind
target
candidate_hash
review_context_hash
effective_policy_hash
coverage_hash
final_adjudication_hash
unresolved_obligations=0
```

Crash cases:

1. crash during Review -> resume Review Run
2. CONVERGED but no operation checkpoint -> reissue Attestation only if same Candidate/Context/Policy is provable
3. checkpoint before completion precheck -> recompute fingerprints; if they match, continue without full re-review
4. after precheck before terminal finalization -> existing operation recovery continues
5. after terminal event/commit boundary -> existing terminal-finalization recovery owns

Runtime Review state alone never proves authorization. Existing lifecycle events remain canonical truth.

## 12. Roadmap and Phase Design reviews

### Roadmap Review

Natural gate:

```text
RoadmapPlan complete
-> freeze
-> Roadmap Review
-> READY
-> existing create_roadmap mutation/registration/Git
```

Review viewpoints:

- purpose/requirements
- decomposition/order/dependencies
- feasibility/simplicity
- specialists as needed

### Phase Design Review

Natural gate:

```text
Phase entry eligibility/prechecks
-> complete PhaseEntryDesign
-> freeze
-> Phase Design Review
-> READY
-> existing Phase CREATE / Work registration
```

Six concerns:

1. Requirement Completeness
2. Interpretation Closure
3. Authority/Responsibility Closure
4. Enforcement Closure
5. Lifecycle/Temporal Closure
6. Evidence Closure

Counterexample question: if implemented exactly as designed, is there a representative case that still breaks?

## 13. LOW-derived Work

Accepted LOW not repaired immediately becomes a real independent Work, not a TODO.

To avoid blocking the origin Phase/Roadmap:

```text
phase_id = None
origin.type = standalone
```

Keep Review provenance separately (conceptually `review_origin`) rather than inventing a third `origin.type`.

Minimum LOW Work meaning:

- what to fix/improve
- origin Finding / Review Run / source Work
- done condition

LOW Works do not become completion members of the source Phase/Roadmap. Once later selected, they are normal Works and pass normal START / Pre-Review / Formal Review.

Deferred LOW ordering uses existing `planned_next`, not a new scheduler/priority state:

```text
LOW-1 -> LOW-2 -> LOW-3
```

Normal Roadmap progression has priority. `blocked != idle`: ambiguity, HUMAN wait, broken dependency, or reconcile-required does not justify silently switching to LOW maintenance. Explicit human selection may start a LOW Work at any time.

## 14. Durable Review History

Runtime-only history is insufficient for cross-run recurrence, LOW provenance, and learning. Durable data should preserve causality, not every raw log.

Conceptual Project layout:

```text
.workline/review/
  profile.yaml
  runs/
  findings/
  repairs/
  policy-changes/
  evidence-snapshots/
  patch-notes/

.workline/runtime/review/
  runs/
  candidates/
  raw-reports/
  learning/
```

Durable:

- compact Review Run summary
- Finding summary
- Repair summary
- B/C history
- LOW provenance
- policy-change evidence snapshots / patch notes

Runtime:

- reviewer raw output
- mutable recovery state
- Candidate materializations
- intermediate Coverage
- high-volume learning observations

Candidate Tree itself is not committed. Durable history stores identities/hashes/base revision and any immutable external evidence necessary for reconstruction.

Review History must not become an input to `state.py` generated lifecycle state.

## 15. Self-evolving Review Policy

Invariant:

```text
what correctness means = fixed by normative authority
how correctness is verified = may evolve within allowed bounds
```

Effective Policy composition:

```text
Global Review Policy
+ Project-local Review Profile
+ Review Kind
+ Candidate / Change Risk
+ Active Temporary Guards
= Effective Review Policy
```

Rules conceptually carry:

```text
rule_id
class: mandatory | default | adaptive
subject
minimum_strength
lightenable
risk_triggers
source
```

Mandatory floor cannot be waived by Project learning. Candidate risk and Temporary Guards only strengthen the current Run. Project lightening applies only when allowed, evidence-backed, no risk/guard conflicts exist, and replacement verification exists.

Effective Policy is frozen per Run. Global changes do not retroactively alter an in-progress Run, except an explicitly defined emergency security rule if later designed.

## 16. Project-local Policy Change

Policy evolution is a separate closed-loop operation, not an ordinary Review Repair:

```text
Review Run
-> Learning observation
-> Evaluation Trigger
-> Policy Change Candidate
-> Policy Change Review
-> apply new Project Profile version
-> Git + Patch Notes
-> observing
-> retain / adjust / rollback
```

Policy Change review uses three meta-viewpoints:

- Evidence validity
- Safety / boundary preservation
- Effectiveness / operability

A proposal cannot weaken/change the rules used to approve itself. It is evaluated using frozen pre-change policy plus fixed meta-review rules.

Autonomous changes may tune reviewer emphasis, specialists, verification scope/frequency, representative cases, coverage emphasis, and adaptive checks. They may not redefine Problem/Improvement, severity meaning, HUMAN boundaries, lifecycle/completion semantics, canonical authority, product requirements, or non-negotiable safety principles.

Evidence asymmetry initial parameters:

- strengthening candidate: about 3-5 independent meaningful same-pattern observations
- lightening candidate: about 20-30 Relevant Opportunities + low yield/escape/B/C + replacement verification

A serious single HIGH escape may create a strengthening-only Temporary Guard with expiry/observation requirements, not a permanent rule.

Rollback creates a new version/commit; history is not rewritten.

## 17. Global Policy promotion

Review Constitution remains in normative authority (`registry.md` + canonical Review Skill). Global Adaptive Policy is versioned data interpreted under that authority, not a new independent authority.

Normal flow:

```text
Project A evidence
Project B evidence
Project C evidence
-> generalized pattern
-> Global Policy Change Candidate
-> Global Policy Change Review
-> Global vN+1
-> observing
-> retain / rollback
```

One Project normally cannot directly promote a permanent Global rule. Promotion should rely on independent Project evidence and a generalized mechanism, not repeated counts of the same local bug.

Project mutation and Global Workline-root mutation are separate operations/repositories. A Project operation never performs a two-repository transaction. Projects adopt new Global versions at the next Review Run boundary after compatibility checks.

## 18. Legacy activation compatibility

New Review gates must not be retrofitted into an already-pending legacy operation merely because new code is now installed.

Conceptual contract:

```text
operation_contract = legacy
  -> finish under legacy semantics

operation_contract = review-v1
  -> Review Attestation required

unknown / contradictory
  -> reconcile required
```

Absence of an Attestation does not itself prove legacy status. The operation contract/version must be mechanically established.

## 19. Seven-phase implementation Roadmap - Candidate 2

### P1 Review Core + Authority + Runtime Foundation

Desired state: Review semantics, execution contract, and runtime recovery foundation exist without changing existing domain lifecycle.

Works:

- Review Constitution / canonical Review Skill / registry routing
- Review domain model
- Candidate / Context identities
- Effective Policy v1
- Reviewer Executor Protocol
- executor adapters
- Coverage + Adjudication
- runtime Review storage
- runtime layout/recovery compatibility
- Review Core recovery
- synthetic integration

### P2 Planning Review Gates

- RoadmapPlan Candidate adapter using existing request identity
- Roadmap Review
- Roadmap repair continuation
- READY -> existing Roadmap mutation gate
- PhaseEntryDesign Candidate adapter using existing design identity
- Phase Design Review
- Phase design repair continuation
- READY -> existing Phase entry gate
- integration validates that unreviewed planning objects cannot write canonical state

### P3 START Review Gate + Activation Compatibility

- operation contract/version identity
- legacy pending compatibility
- Work Candidate ownership
- Candidate Builder
- Review Entry Safety
- Pre-Review Quality Pass
- Work Formal Review gate
- Attestation checkpoint
- completion bridge
- crash/resume seams across Review, checkpoint, result commit, and finalization

Initial P3 may stop on REPAIR/HUMAN; automatic Repair is intentionally deferred to P4.

### P4 Repair Loop + Same-Run Recurrence + Integration Review

- ReviewRepairRequest
- executor repair purpose
- Repair Batch
- Repair Coverage Check
- semantic impact
- selective re-review
- same-run A/B/C
- repair instability / strategy change
- Phase Integration Check
- fix/reintegration flow

### P5 Durable Review History + Cross-Run Recurrence + LOW Work

- canonical `.workline/review/` layout
- Project Start / validation / residue compatibility
- durable Run/Finding/Repair records
- cross-run recurrence resolver
- `review_origin` provenance
- LOW Workization
- Deferred LOW `planned_next` chain
- idle-boundary selection

### P6 Project-local Adaptive Policy

Recommended rollout order:

```text
learning metrics
-> strengthening only
-> Temporary Guards
-> observation / rollback
-> lightening
```

### P7 Global Policy Promotion

- Global Adaptive Policy storage under Workline-root authority
- Promotion Packet
- cross-project evidence aggregation
- generalization check
- Global Policy Change Review
- versioning / Patch Notes
- Project adoption compatibility
- observation / rollback

## 20. Roadmap Review history

Candidate 1 independent review found:

- R1 HIGH Problem: canonical Review authority was missing
- R2 HIGH Problem: runtime Review storage was introduced before runtime layout/recovery compatibility
- R3 MID Problem: cross-run recurrence was planned before durable history existed
- R4 HIGH Problem: no activation boundary for legacy pending operations vs Review-aware operations
- R5 MID Improvement: Review semantics risked coupling to a concrete reviewer executor/subagent mechanism

Candidate 2 repairs:

- R1 resolved in P1 through canonical Review Skill / registry / Constitution
- R2 resolved by moving runtime compatibility to P1 and leaving durable `.workline/review/` layout to P5
- R3 resolved by limiting P4 to same-run recurrence and P5+ to cross-run recurrence
- R4 resolved by explicit operation-contract/version activation semantics in P3
- R5 resolved by Reviewer Executor Protocol + adapters

Latest internal Roadmap Review of Candidate 2:

```text
A Purpose / Requirements: PASS
B Decomposition / Dependency: PASS
C Feasibility / Simplicity: PASS
Unresolved HIGH/MID: 0
HUMAN: 0
Verdict: READY
```

This READY verdict is intentionally not authoritative for external review. An independent reviewer should challenge it from scratch.

## 21. Earlier design checkpoints that must accompany external review

Also review these existing non-normative design-history files:

- `REVIEW_SYSTEM_DESIGN_NOTES.md`
- `REVIEW_SYSTEM_LEARNING_AND_PHASE_DESIGN_NOTES.md`

They contain earlier reasoning and may expose assumptions, omissions, or contradictions hidden by this consolidated checkpoint.

External review must also inspect current live canonical authority and implementation, especially:

- `registry.md`
- relevant canonical Skills under `.claude/skills/`
- current `src/workline/` lifecycle/recovery/Git/mutation implementation

Do not treat this checkpoint as overriding live canonical behavior. Any mismatch with live `main` must be reported explicitly.
