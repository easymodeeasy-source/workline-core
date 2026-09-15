# Review System — Learning Loop and Phase Design Review Notes

> Status: design memo / non-normative
>
> Date: 2026-09-15
>
> Companion to `REVIEW_SYSTEM_DESIGN_NOTES.md`. This file records later design decisions around self-evolving review policy and Phase Design Review. It does **not** replace `registry.md` or registry-routed canonical Skills. Production behavior must only change when canonical Workline specifications/Skills are updated explicitly.

## 1. Review System must learn from operation

The Review System should not remain static. It should improve from accumulated operational evidence.

Two directions are required:

- strengthen weak review/test areas when repeated misses or escapes are observed
- lighten low-value review/test activity when repeated evidence shows low yield, low escape risk, and adequate replacement coverage

The system must not only get stricter over time; it must also be able to become cheaper where evidence supports that.

## 2. Self-Evolving Review Policy

The intended model is automatic policy evolution within an explicitly allowed scope.

```text
Review / Test / Repair operation
  -> learning logs
  -> repeated-pattern analysis
  -> policy/test change
  -> focused validation
  -> Git commit
  -> human-readable Patch Notes
  -> new policy version
  -> post-change observation
```

This is not merely a recommendation engine. Within the allowed adaptive surface, Workline may automatically modify its own review/test policy.

## 3. Absolute rule: do not evolve from a single event

A single Finding, one successful run, or one no-finding run must never cause a permanent policy evolution.

```text
single observation
  -> record only
  -> no permanent policy change

repeated independent evidence
  -> policy-change candidate

sufficient relevant opportunities
+ persistent trend
+ validation possible
+ rollback possible
  -> automatic evolution may proceed
```

A serious one-off incident may justify an immediate temporary guard, but not a permanent learned rule without repeated evidence.

## 4. Evolution itself is reviewed

Every automatic policy change is itself an experiment whose downstream effect must be observed.

Example:

```text
policy v12
  -> test A is lightened
  -> policy v13
  -> observe subsequent runs
  -> compare escape / severity / recurrence / cost

if quality degrades
  -> rollback or strengthen again

if quality holds or improves
  -> retain v13
```

This is mandatory.

A policy change is not considered successful merely because its own validation passed at change time. It must survive later operational evidence.

## 5. Git and Patch Notes

All automatic policy changes must be Git-managed and individually reversible.

Each policy evolution should preserve at least:

- what changed
- why it changed
- which observations supported the change
- expected effect
- what became lighter or stronger
- which regressions/escapes will be monitored afterward
- policy version before / after
- Git commit
- rollback point

A human-readable Patch Note must explain the change in plain language.

Example shape:

```text
Review System v18

State/lifecycle changes had repeated reader-side escapes, so reader verification is now required for this change type.
Local text-only changes had a long low-yield history for broad regression execution, so they now use focused checks by default.
The change is monitored for later HIGH/MID escapes and can be reverted to commit <...>.
```

## 6. Allowed automatic evolution surface

Automatic evolution is allowed for review/test execution policy, including:

- which tests/checks are selected
- check/test frequency
- focused / targeted / broad verification selection
- change-type to required-check mapping
- specialist reviewer selection conditions
- Pre-Review questions and emphasis
- review coverage emphasis
- representative-case selection
- reviewer emphasis
- strengthening or lightening adaptive checks

The concept is: **how Workline verifies correctness may evolve automatically**.

## 7. Automatic-change prohibition surface

Operational learning must not silently redefine **what correctness means**.

Do not automatically change based only on learning statistics:

- Work / Phase / Roadmap semantics
- completion semantics
- Problem / Improvement meaning
- HIGH / MID / LOW meaning
- HUMAN decision boundary
- product requirements or user-decided specification
- canonical authority rules
- core lifecycle semantics
- non-negotiable security/destructive-operation principles

For example:

```text
HIGH findings are inconvenient -> weaken the HIGH definition
```

is forbidden.

But:

```text
HIGH findings repeatedly escape in state-reader behavior -> strengthen reader verification
```

is allowed.

## 8. Policy strength classes

Global review policy should conceptually distinguish at least:

```text
mandatory
  -> project policy cannot disable it

default
  -> global standard; project evidence may strengthen or carefully lighten it

adaptive
  -> actively optimized by learning
```

Weakening a global default should require stronger evidence than strengthening it.

## 9. Relevant opportunity, not raw run count

Learning denominators must use **relevant opportunities**, not mere execution count.

For each check/reviewer, preserve at least:

```text
applicable: yes / no
executed: yes / no
result: finding / no-finding / inconclusive
```

Thirty no-finding runs do not justify lightening a check if only two runs actually exercised the surface the check is intended to protect.

## 10. Initial direction for evolution thresholds

Do not encode a simplistic fixed universal count as semantic truth.

Working direction:

- strengthening may react after repeated independent same-pattern evidence, potentially in the rough range of 3–5 meaningful cases
- lightening requires substantially more evidence, such as a long run of relevant opportunities, low useful Finding yield, low downstream escape, and a replacement/alternative check
- serious HIGH escape may add a temporary immediate guard, while permanent policy change still requires repeated evidence

Counts are initial operating parameters, not definitions of truth.

## 11. Learning dimensions

The system should learn at least:

- **Coverage learning** — where review repeatedly misses relevant surfaces
- **Cost learning** — where checks cost substantial time but repeatedly add little information
- **Failure-pattern learning** — which design/repair/change types repeatedly produce findings, escapes, B recurrence, or C repair-induced defects

Useful generated measures can include:

- Finding yield over relevant opportunities
- downstream escape rate
- B recurrence rate
- C repair-induced rate
- redundant-review overlap
- review/test cost

Generated metrics are not the raw source of truth; they must remain traceable to underlying runs/findings.

## 12. Learning record granularity

Preserve three connected record layers:

### 12.1 Review Run

Records what was actually checked under a particular policy version:

- target: Work / Phase Design / Phase Integration
- change/risk type
- policy version
- reviewer/check/test selection
- applicability
- coverage
- result
- cost/time where available

### 12.2 Finding / Repair

Records:

- Problem / Improvement
- HIGH / MID / LOW
- discovery source
- A / B / C relationship where applicable
- repair scope
- recurrence or repair-induced outcome
- later downstream escape

### 12.3 Policy Change

Records:

- before / after policy version
- exact change
- supporting Review Runs / Findings
- expected effect
- validation
- Git commit / rollback target
- Patch Notes
- later post-change evaluation

Do not keep only aggregate statistics. Preserve raw evidence sufficiently to recalculate/reconsider the learning decision later.

## 13. Global and Project-local learning

Use a layered model rather than only one global store or only per-project stores.

```text
Global Review Policy
  +
Project-local Review Profile
  +
current Work/Phase change context
  -> Effective Review Policy for this run
```

### Project-local

Project-local learning is the first home for project-specific evidence and tendencies.

Examples:

- a particular project repeatedly misses serializer/migration interactions
- a project-specific UI check has low information value for a certain change type

### Global

Global policy carries cross-project reusable knowledge.

Examples:

- state/lifecycle changes commonly need both writer and reader verification
- a generic failure pattern repeats across unrelated projects

## 14. Promotion from Project-local to Global

A local pattern should not become global merely because it occurs many times in one project.

Promotion requires cross-project evidence such as:

- recurrence in multiple independent projects
- same underlying change/failure type
- sufficient relevant opportunities
- meaningful relationship to severity, escape, B, or C
- evidence that the rule is general rather than project-structure-specific
- post-promotion monitoring is possible
- Git rollback is possible

Preferred shape:

```text
Project A pattern
  -> local adaptation

Project B repeats pattern
  -> cross-project candidate

additional independent evidence
  -> global promotion candidate

Global policy change
  -> Git + Patch Notes
  -> observe effects across projects
  -> retain / rollback / downgrade
```

## 15. Effective Policy snapshot

At the start of each review run, resolve and freeze:

```text
Global policy version
+ Project profile version
+ current change/risk context
= Effective Policy snapshot
```

The policy used by an in-progress run must not change halfway through that review because a global/local policy evolved concurrently.

Each Review Run should be traceable to the effective policy version/hash that governed it.

## 16. Storage and Project initialization implications

The Review Learning domain should be separate in responsibility from normal Work/Phase lifecycle event/state data.

Conceptually:

```text
Project-local
.workline/
  ...
  review-learning/
    runs/
    findings/
    policy-state/
    ...
```

Exact paths/schema are not fixed here.

Project-local raw operational evidence should stay attributable to its Project. Global learning may aggregate/promote reusable patterns without erasing project context.

Policy files that are automatically evolved should be Git-managed. High-volume raw learning data does not necessarily need one Git commit per run; a policy-change commit must retain references/snapshots/hashes sufficient to trace its evidence.

Production rollout therefore requires updates to the canonical Project creation/layout authority, including at least:

- `project-start` initialization behavior
- `registry.md` ownership/routing
- the canonical document/Skill that defines `.workline/` Project structure
- initialization of the Project-local Review Profile
- traceability to the initial Global Review Policy version

## 17. Phase Design Review purpose

Phase Design Review occurs **before Phase CREATE/registration**, against the proposed `PhaseEntryDesign` or equivalent semantic design object.

```text
PhaseEntryDesign
  -> Phase Design Review
  -> repair design if needed
  -> READY
  -> Phase CREATE / registration
```

Its purpose is not to review an already-completed Phase. It prevents a weak Phase design from being handed to Claude Code/implementation with too much room for interpretation or incomplete system coverage.

## 18. Phase Design Review mandatory concerns

The following concerns were identified:

### 18.1 Requirement Completeness

Ask whether necessary concerns are absent entirely, not merely ambiguous.

Typical examples:

- failure
- interruption
- retry/resume
- partial success
- existing data / migration
- multiple entry points
- downstream readers

A perfectly unambiguous requirement can still be incomplete.

### 18.2 Interpretation Closure

Ask whether Claude Code can reasonably implement a different meaning while believing it followed the specification.

Avoid unspecified implementation judgment such as vague “appropriately”, “safely”, or “as needed” behavior where correctness depends on a specific outcome.

### 18.3 Authority / Responsibility Closure

Ask:

- what is canonical
- who writes it
- who decides it
- who reads it
- whether equivalent meaning is independently stored/decided in multiple places

The goal is to prevent split authority and conflicting representations.

### 18.4 Enforcement Closure

A requirement being clear and a guard/helper existing does not prove the requirement holds system-wide.

Ask whether every relevant production path is forced through the intended enforcement point and whether optional arguments, fallback routes, alternate entrypoints, direct calls, or local implementations can bypass it.

### 18.5 Lifecycle / Temporal Closure

Ask whether the design remains correct during:

- failure
- interruption/crash
- retry
- resume
- duplicate execution
- partial writes
- ordering differences
- intermediate state

The final state alone is not enough for lifecycle-sensitive designs.

### 18.6 Evidence Closure

Ask what later evidence will actually prove the requirement was achieved.

Do not allow a unit helper test to stand in for whole-system enforcement when the requirement is system-wide.

Each reviewer should identify the evidence required for the surface they are judging.

## 19. Phase Design Review depth

All Phases receive at least lightweight consideration of all six concerns.

Four concerns are always central:

- Requirement Completeness
- Interpretation Closure
- Authority / Responsibility Closure
- Enforcement Closure

Lifecycle / Temporal Closure and Evidence Closure always exist as questions, but their depth scales with risk/change type.

State, lifecycle, transaction, authority, concurrency, recovery, resume, and migration work should receive deeper treatment.

## 20. Lightweight counterexample question

Do not create an independent exhaustive adversarial-review stage by default.

Instead, each Phase Design reviewer ends with one bounded question:

> If this design were implemented exactly as specified, is there a representative case in which it could still fail?

For ordinary Phases, one or two representative counterexamples are enough. High-risk Phase designs may explore this more deeply.

The objective is not to prove no imaginable counterexample exists or to run an unbounded search.

## 21. Phase Design reviewer mapping

Use the existing four base reviewer roles with Phase-design-specific emphasis.

### Reviewer A — Requirement / intended outcome

Primary focus:

- Requirement Completeness
- Interpretation Closure
- Phase goal / completion intent

### Reviewer B — Correctness / failure / intermediate state

Primary focus:

- Enforcement Closure
- Lifecycle / Temporal Closure
- failure/retry/resume correctness

### Reviewer C — Impact / integration / authority

Primary focus:

- Authority / Responsibility Closure
- Enforcement Closure across surrounding systems
- previous/next Phase and existing mechanism consistency

### Reviewer D — Simplicity / design quality

Primary focus:

- unnecessary Work decomposition
- local patch-like Phase structure
- duplicated mechanisms
- detours / maintainability
- whether shared responsibility should be solved centrally

Evidence Closure is cross-cutting: each reviewer states what later evidence would prove the surface they reviewed.

Each reviewer also performs the bounded counterexample question.

## 22. Phase Design Review output

A compact review result should expose what was actually reviewed rather than only returning PASS.

Conceptual form:

```text
Phase Design Review

Phase:
Candidate version:

A. Requirement / Interpretation
- covered:
- findings:
- evidence / basis:
- unresolved:

B. Correctness / Lifecycle / Enforcement
- covered:
- findings:
- evidence / basis:
- unresolved:

C. Authority / Integration
- covered:
- findings:
- evidence / basis:
- unresolved:

D. Simplicity / Design Quality
- covered:
- findings:
- evidence / basis:
- unresolved:

Evidence Closure
- implementation-time evidence required:

Counterexample check
- representative counterexample found / none found:

Final
- HIGH:
- MID:
- LOW:
- HUMAN:
- verdict: REPAIR / READY
```

`unresolved` is required so that “not checked” cannot be silently represented as “no problem”.

## 23. Phase Design Review decision rule

Working direction:

```text
HIGH or MID
  -> repair Phase design before CREATE

product/spec/requirement decision needed
  -> HUMAN

no HIGH/MID
+ required coverage is satisfied
+ unresolved items are properly resolved
  -> READY
```

## 24. LOW in Phase Design Review

Phase Design Review LOW is not mechanically identical to Work Formal Review LOW because the Phase is not yet registered/executed and design repair is still cheap.

Use:

```text
LOW and cheap to improve now
  -> improve Phase design now

LOW with real future value but not needed for this Phase
  -> preserve as independent future Work candidate

LOW that is effectively preference/no meaningful value
  -> dismiss after adjudication
```

Do not create future Works for every minor design preference.

Raw review evidence should still preserve dismissed LOW observations for later learning. Repeated supposedly-negligible LOW patterns may later prove meaningful through the Review Learning Loop.

## 25. Relationship to Work and Phase-end review

Keep the three roles distinct:

```text
Phase creation time
  -> Phase Design Review

Work terminalization boundary
  -> Work Formal Review

Phase end after integration
  -> lightweight Phase Integration Check
```

Do not rerun full Work Formal Review at Phase end. Phase-end review should focus on cross-Work integration and Phase-goal achievement that cannot be proven by individual Work reviews alone.

## 26. Open implementation design

Still to decide before production rollout:

- exact Global Review Policy representation
- exact Project-local Review Profile representation
- exact Review Learning storage schema and retention
- exact policy version/hash mechanics
- exact automatic evolution job/trigger
- exact post-evolution observation window and rollback trigger
- exact canonical Project layout changes
- exact `project-start` / `registry.md` updates
- exact Work Formal Review output and integration with START
- exact lightweight Phase Integration Check output
