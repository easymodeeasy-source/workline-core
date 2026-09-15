# Review System / BL-004 Design Notes

> Status: design memo / non-normative
>
> Date: 2026-09-15
>
> This file records design decisions and working agreements from Review System discussions. It does **not** replace `registry.md` or registry-routed canonical Skills. `BACKLOG.md` remains non-normative. Production behavior must only change when the canonical Workline specifications/Skills are updated explicitly.

## 1. Scope

This memo covers the Review System design lane around BL-002 / BL-003 / BL-004, especially:

- Work completion review semantics
- Phase completion review semantics
- review finding classification
- repair/convergence behavior
- review-before-completion quality gates
- LOW finding deferral without blocking the current Roadmap/Phase
- lessons carried from P-0752 ReviewLoopLab research

It does **not** define a new progression controller, scheduler, mutation system, schema, API, or production implementation.

## 2. Review principle

Formal Review is not the place where quality is created from scratch.

The intended separation is:

```text
implementation / design
  -> pre-review quality work
  -> Review Ready
  -> Formal Review
  -> adjudication / repair if needed
```

The pre-review stage should remove obvious defects and weak evidence before Formal Review. Formal Review should independently challenge a candidate that is already claimed to be complete.

## 3. Finding validity and primary classification

A review statement is evaluated in this order:

```text
Is the claim actually supported?
  NO  -> dismiss
  YES -> continue

Does the current artifact satisfy the currently decided requirement / goal?
  NO  -> Problem
  YES -> continue

Is there a genuinely better alternative?
  YES -> Improvement
  NO  -> dismiss
```

If deciding this requires a product/spec/requirement decision, route to HUMAN instead of silently redefining the requirement.

The primary content categories are:

- `Problem`
- `Improvement`

Do not encode “false positive” or “human judgment required” as content categories. Those are adjudication outcomes.

## 4. Importance level

Both Problems and Improvements receive one of:

- HIGH
- MID
- LOW

These are guidelines, not a mathematically rigid scorecard.

### 4.1 Problem

**HIGH**
- Leaving it unfixed creates clear risk to correctness, safety, later implementation, durable state, or trustworthy completion.
- Continuing work on top of it can spread damage or make later repair harder.

**MID**
- Clearly wrong or undesirable, but not as broadly dangerous as HIGH.
- The current Roadmap/Phase/Work should not be considered clean enough to proceed without repairing it.

**LOW**
- Worth fixing, but current progress does not need to stop.
- Operational workarounds are acceptable, later repair is safe, and the current Work/Phase objective can still be achieved.

### 4.2 Improvement

**HIGH**
- The current design technically works, but is clearly taking a detour while a substantially simpler/clearer/higher-quality alternative is available.
- Fixing it now strongly improves later work.

**MID**
- The current design works, but has meaningful awkwardness, unnecessary complexity, or maintainability cost.
- Improvement value is clear, though not overwhelming.

**LOW**
- The current approach is acceptable and the alternative is only moderately better.
- Rough intuition: about a 40:60 quality choice rather than an obvious defect.

A practical question for HIGH/MID/LOW is:

> Knowing this finding exists, should Workline allow the current review cycle to finish without fixing it?

## 5. Repair policy

The default policy is intentionally uniform across Problem and Improvement:

```text
Problem HIGH       -> repair in the current review cycle
Problem MID        -> repair in the current review cycle
Problem LOW        -> create an independent Work

Improvement HIGH   -> repair in the current review cycle
Improvement MID    -> repair in the current review cycle
Improvement LOW    -> create an independent Work
```

Therefore MID is part of the repair boundary, not only HIGH.

### 5.1 LOW Work rule

A LOW finding becomes a real independent Work, not a loose TODO.

The derived Work must at minimum preserve:

- what should be fixed/improved
- where the finding came from
- what “done” means for that Work

Traceability only needs to go **from the derived Work back to the discovery origin**. Do not make that derived Work part of the originating Roadmap/Phase completion set by reverse-link semantics.

The originating Roadmap/Phase may complete while that LOW Work remains pending.

Once the LOW Work is selected later, it is a normal Work and must itself be completed properly. “Deferred” does not mean “optional forever.”

Exact schema/field names are not decided here.

## 6. Duplicate findings

Merge findings based on repair identity, not wording alone.

Treat multiple reports as the same Finding when:

- the central problem/improvement is the same
- the effective repair location or repair strategy is the same
- one repair would resolve all of them

Keep them separate when:

- root cause is different
- repair strategy is different
- fixing one would leave the other unresolved

If unsure, keep them separate. Incorrect merging is more dangerous than temporary duplication.

If merged reports disagree on importance, keep the strongest supported level and retain the reasoning/provenance of the underlying reports.

Do not discard the raw reviewer reports after normalization.

## 7. Discovery time and repair causality

Whether a finding:

- existed before the current repair
- was created by the current repair
- cannot be causally determined

is provenance, not the normal priority axis.

A pre-existing HIGH is still HIGH. A newly discovered MID is still MID.

However, a `Problem LOW` demonstrably created by the current repair is an exception: prefer repairing it in the current cycle instead of externalizing degradation that the current cycle itself introduced.

Do not infer causality merely because a finding appeared in a later review round.

## 8. P-0752 as the baseline failure case

P-0752 ReviewLoopLab is treated as research evidence for the kind of review loop Workline must expect, not as a production design to preserve.

Key observations carried forward:

- later review output is not equivalent to “new problem”
- raw report count, normalized claim count, and finding identity may differ
- previous review completeness may be unprovable
- “same problem” can differ depending on claim/mechanism/scope/evidence granularity
- raw finding counts are not a safe convergence metric
- repair causality may be unknowable without explicit repair-before/after evidence
- reviewers can repeatedly expose different valid surfaces even after earlier PASS results

Therefore the target is **not** “guarantee convergence in N review rounds.”

The target is:

> make it possible to know why the review is still running, preserve enough evidence to distinguish recurrence/repair impact where possible, and change repair strategy when local repair is unstable.

## 9. Formal Review batching

Do not mutate the candidate while a Formal Review pass is still discovering findings.

Preferred shape:

```text
candidate N
  -> complete review pass
  -> freeze discovered reports for that candidate
  -> normalize / deduplicate / adjudicate
  -> repair current-cycle HIGH/MID
  -> candidate N+1
  -> review again
```

This avoids mixing “what existed in candidate N” with “what was introduced while reviewing candidate N.”

New findings in later rounds are still classified normally. They are not automatically deferred just because they were discovered later.

## 10. Repair instability / non-convergence

The dangerous pattern is not simply “many review rounds.” It is a chain where repairs keep generating new problems around the same semantic surface.

Conceptually:

```text
repair A -> problem B
repair B -> problem C
repair C -> problem D
```

When this pattern is supported by evidence around the same responsibility/mechanism, stop adding local patches blindly.

Switch from local repair to a higher-level repair strategy, such as:

- reconsider the underlying state model
- replace the local patch with a coherent redesign
- rollback an unstable repair direction
- widen the repair scope deliberately

If the higher-level repair requires a product/spec decision, route to HUMAN.

A hard review-cycle cap may exist as an emergency fuse, but round count alone is not semantic convergence.

## 11. Convergence direction

Working convergence direction for a Formal Review cycle:

- unresolved HIGH/MID = 0
- every LOW finding has been converted to a traceable independent Work
- unadjudicated review reports = 0
- no unresolved Problem introduced by the current repair remains

Final completion also requires that the required review scope for the candidate has actually been covered. A PASS with unknown/unrecorded coverage should not be treated as strong evidence.

Exact production convergence rules remain to be designed and are not canonicalized by this memo.

## 12. Pre-Review Quality Pass

Historical investigation showed that Workline/dev-os already performed substantial self-review before external review. Examples included fixed review viewpoints, PASS/DEFECT decisions, focused tests, full suites, regression checks, and reproductions. Those steps still allowed later MAJOR/BLOCKER findings.

Therefore Pre-Review Quality Pass must **not** be merely “run another checklist.”

Its distinguishing goals are:

1. enumerate the actual verification surface rather than only naming review viewpoints
2. map evidence to the specific surface it proves
3. expose what remains unverified
4. re-evaluate evidence invalidated by subsequent repair
5. avoid using Pre-Review PASS as a substitute for independent Formal Review

## 13. Pre-Review viewpoints

Useful viewpoints include:

- Requirement: does the artifact actually satisfy the desired state?
- Correctness: success, failure, retry, partial/interrupted states
- Impact: what else reads/depends on the changed state?
- Integration: consistency with existing mechanisms and surrounding design
- Simplicity: unnecessary detours, duplicated mechanisms, avoidable complexity
- Evidence: what test/diff/observation actually supports each claim?

These viewpoints alone are insufficient. The important part is the mapping between the concrete surface and the evidence.

For example, “interruption behavior checked” should ideally identify which interruption windows were actually exercised, rather than treating one exercised window as proof of all interruption behavior.

## 14. Avoiding redundant self-review

Pre-Review must not become “run everything after every small change.”

Core rule:

> verification effort should scale with the semantic impact of the change.

Preferred execution shape:

```text
change
  -> classify semantic impact
  -> identify which existing evidence was invalidated
  -> rerun only the necessary focused/targeted checks
  -> expand only when the change surface requires it
  -> Review Ready
```

Full-suite execution is not an anxiety ritual. It should be used where whole-system evidence is actually needed.

## 15. Change-impact levels for re-verification

### 15.1 Local logic change

Examples:
- one conditional
- localized validation rule
- direct input/output behavior

Typical re-verification:
- focused tests
- direct callers/consumers only when semantics affect them

### 15.2 Shared utility / common processing change

Examples:
- shared helper
- validator
- serializer
- common transform

Typical re-verification:
- focused tests
- representative callers
- relevant integration checks

### 15.3 State / contract / lifecycle change

Examples:
- event meaning
- state derivation
- schema
- completion condition
- recovery/resume behavior
- read/write dependency

Typical re-verification:
- writers
- readers
- interruption/failure paths
- retry/resume
- adjacent operations whose eligibility/meaning depends on the changed state

This category should be treated more aggressively because historical misses often came from only checking the write side or only one interruption window.

### 15.4 Shared infrastructure / broad foundation change

Examples:
- cross-cutting Workline infrastructure
- broadly shared lifecycle mechanism
- behavior that invalidates assumptions across many Works

Typical re-verification:
- broad targeted integration
- full suite when whole-system evidence is genuinely required

## 16. Re-verification questions

For each repair/change, answer briefly:

1. What semantic behavior changed?
2. Who writes the changed state/value?
3. Who reads/depends on it?
4. Which operations have different eligibility or outcomes because of it?
5. Does it affect failure/interruption/retry/resume?
6. Does it alter schema/event/contract meaning?
7. Is the changed code shared?
8. Which prior evidence became invalid because its assumptions changed?

Then rerun the invalidated evidence rather than blindly repeating all previous checks.

## 17. Evidence reuse

Evidence may be reused when the change did not invalidate the assumptions under which that evidence was collected.

```text
assumptions unchanged -> evidence may be reused
assumptions changed   -> evidence must be reacquired
uncertain             -> reacquire
```

This is intended to reduce repeated full-suite runs while still making repair impact explicit.

## 18. Review Ready direction

Working direction for Review Ready:

- required Pre-Review checks for the actual change surface are complete
- known HIGH/MID concerns = 0
- LOW concerns are either repaired or formalized as independent Works
- remaining unverified areas are explicitly identified rather than silently assumed covered
- evidence used to claim readiness is still valid after the latest repair

This is a gate for entering Formal Review, not proof that Formal Review will find zero findings.

## 19. Open design work

Still to decide before production implementation:

- exact data model for raw reports, normalized findings, recurrence identity, causality, and evidence
- exact HUMAN escalation rules
- exact trigger for “repair instability” and how much can be automated without becoming a rigid counter
- how Formal Review scope/completeness is recorded
- exact Work creation semantics for LOW-derived Works
- how deferred LOW Works are later selected without inventing a new scheduler/controller
- BL-002 Work review integration point
- BL-003 Phase review integration point
- exact production convergence rule

## 20. Non-goals

Do not infer from this memo that Workline should:

- recreate ReviewLoopLab
- add a separate progression Controller
- replace existing Phase integration semantics with parallel completion machinery
- run a full test suite after every change
- treat review count as convergence
- treat every later-round finding as newly created by repair
- make LOW-derived Works block the originating Roadmap/Phase

## 21. A / B / C relationship to previous repair

A finding discovered after a repair should not be classified by timing alone. Use the relationship to the previous repair.

### A. New discovery

The finding was observed later, but may already have existed before the previous repair.

Typical example:

```text
Finding A: failure incorrectly becomes completed
Repair A: fix completed handling
Finding B: failure leaves a lock unreleased
```

Finding B is not repair-induced merely because it became visible after Repair A. The previous incorrect completion behavior may simply have hidden the lock problem.

Treat A as an ordinary finding and apply the normal Problem/Improvement + HIGH/MID/LOW rules.

### B. Recurrence / incomplete repair coverage

The previous repair did not fully close the same substantive problem.

Typical examples:

- only one condition/path was repaired while equivalent paths still fail
- a shared/common decision point should have been repaired instead of one call site
- the set of paths to which the repair must apply was not enumerated completely

B should trigger a check of **why the previous repair coverage was incomplete**, not merely another blind patch.

### C. Repair-induced finding

The previous repair itself created a problem that did not exist before that repair.

C requires strong causality. “Observed after the repair” is not enough.

Typical example:

```text
Finding A: failure incorrectly becomes completed
Repair A: add wording/logic saying “in condition X, do not complete”
Finding C: the new wording/logic is itself ambiguous or semantically wrong in a way that did not exist before Repair A
```

A candidate C may become B after investigation if the supposedly new problem actually existed in another path before the repair.

Therefore A/B/C may begin as a provisional classification and become final only after checking the relationship to the previous repair.

## 22. Repair Coverage Check

Because B-type recurrence is expected to be common, Workline should try to prevent it before Formal Review.

After a repair and before the normal Pre-Review Quality Pass, perform a lightweight **Repair Coverage Check**:

1. Are there other paths with the same responsibility / decision?
2. Should the shared/common mechanism be repaired instead of the observed local site?
3. Can the set of paths to which this repair applies be enumerated?

The goal is not exhaustive retesting. The goal is to detect a repair that only suppresses the observed symptom.

Preferred flow:

```text
implementation / repair
  -> change-impact classification
  -> Repair Coverage Check
  -> Pre-Review Quality Pass
  -> evidence validity check
  -> focused / targeted verification only as needed
  -> Review Ready
  -> Formal Review
```

If the Repair Coverage Check finds that the repair is local but the responsibility is shared, revise the repair before Formal Review rather than spending another Formal Review round discovering the omission.

## 23. Formal Review execution model

Current direction: Formal Review uses **multiple independent reviewers in parallel**, followed by a separate integration/adjudication stage.

All reviewers inspect the **same fixed candidate version**. Do not repair findings while some reviewers are still examining that candidate.

Preferred shape:

```text
candidate N
  -> Reviewer A ┐
  -> Reviewer B ├─ independent / parallel
  -> Reviewer C ┤
  -> Reviewer D ┘
  -> collect raw reports
  -> normalize / deduplicate / validate
  -> classify Problem / Improvement
  -> classify HIGH / MID / LOW
  -> establish A / B / C relationship where relevant
  -> define current repair set
  -> Repair
  -> candidate N+1
```

Reviewers should not see each other’s findings during discovery by default. This reduces anchoring and confirmation effects.

### 23.1 Separation of roles

Keep these responsibilities separate conceptually:

- **Reviewer**: discover and explain potential findings
- **Adjudication / integration**: determine whether claims are supported, merge duplicates, classify importance, and decide repair/defer/HUMAN handling
- **Repair**: change the artifact

A Reviewer should not silently convert discovery into repair while the Formal Review pass is still running.

### 23.2 Base review viewpoints

Working direction is a small set of stable base viewpoints, plus specialist reviewers when the candidate demands them.

Candidate base viewpoints discussed so far:

- requirements / intended outcome
- correctness / failure / intermediate state
- impact / integration / consistency with existing mechanisms
- simplicity / detours / maintainability

The exact number of base reviewers is **not yet fixed**. Current preference is roughly 3–4 base viewpoints rather than one general reviewer, with specialist review added when needed.

## 24. Updated open design work

Still to decide before production implementation:

- exact data model for raw reports, normalized findings, A/B/C relationship, causality, and evidence
- exact HUMAN escalation rules
- exact trigger for repair instability after C-type findings, without reducing it to a rigid round counter
- how Formal Review scope/completeness is recorded
- exact base reviewer viewpoints and count
- when specialist reviewers are added
- how reviewer independence/context should be controlled
- exact Work creation semantics for LOW-derived Works
- how deferred LOW Works are later selected without inventing a new scheduler/controller
- BL-002 Work review integration point
- BL-003 Phase review integration point
- exact production convergence rule
