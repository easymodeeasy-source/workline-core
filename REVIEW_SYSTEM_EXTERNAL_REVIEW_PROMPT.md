# External Review Prompt — Review System Design

You are the independent reviewer for the Workline Review System design.

Your job is not to approve the design. Your job is to determine whether the design, if implemented as written, can safely achieve high-quality autonomous review without breaking Workline's existing authority, lifecycle, recovery, Git, mutation, or progression semantics.

## Materials to read first

Read all of the following before forming conclusions:

1. `REVIEW_SYSTEM_IMPLEMENTATION_ROADMAP_CHECKPOINT.md`
   - latest consolidated design checkpoint
   - includes Candidate 2 implementation Roadmap and the latest internal READY verdict

2. `REVIEW_SYSTEM_DESIGN_NOTES.md`
   - earlier non-normative Review System design notes

3. `REVIEW_SYSTEM_LEARNING_AND_PHASE_DESIGN_NOTES.md`
   - earlier non-normative learning / Phase Design notes

4. Current live canonical authority and implementation on `main`, especially:
   - `registry.md`
   - relevant registry-routed canonical Skills under `.claude/skills/`
   - relevant implementation under `src/workline/`
   - current tests where they establish actual behavior

Important: the notes/checkpoint are not normative authority. If they conflict with live canonical behavior, report the mismatch. Do not silently reinterpret the repository to make the design fit.

## Independence requirement

The latest internal review concluded `READY`. Do not trust or inherit that conclusion.

Review the design from scratch. Existing Findings R1-R5 and their claimed resolutions are evidence of prior reasoning, not facts you must accept.

Prioritize concrete failure scenarios over style preferences.

Do not invent defects merely to be critical. Conversely, do not downgrade a real failure because the design is otherwise coherent.

## Review viewpoints

### A. Requirement / Goal

Check whether implementing this design actually produces the intended system:

- high-quality autonomous Review
- reliable convergence rather than raw round-count stopping
- ability to distinguish new findings, recurrence, and repair-induced defects
- autonomous progression without letting Review become a second progression controller
- HUMAN only where the decision genuinely belongs to a human

Look for missing requirements that would make the system appear complete while still failing its purpose.

### B. Lifecycle / Recovery / Git / Mutation

Trace realistic interruption points across:

- Roadmap Review before Roadmap mutation
- Phase Design Review before CREATE / Phase entry
- Work execution -> Candidate -> Formal Review -> Repair -> completion
- Phase Integration Check before integration terminalization
- Review Attestation -> operation checkpoint -> existing completion/finalization
- legacy pending operations crossing the activation boundary
- LOW Work creation
- Project-local Policy Change
- Global Policy Change

Look for:

- crash/resume ambiguity
- partial writes
- replaying the wrong decision
- duplicate effects
- inability to prove the same Candidate/Context/Policy
- Review recovery conflicting with existing Mutation Controller recovery
- unsafe multi-repository coupling
- cases where a result can be completed without the review obligation actually being durable

### C. Authority / State / Ownership

Check for hidden or duplicate sources of truth between:

- `registry.md`
- canonical Skills
- adaptive policy data
- Project profile
- `state.py`
- events
- relations
- durable Review History
- runtime Review state
- operation pending mutation

Ask whether the design accidentally creates a second state machine or allows adaptive configuration to redefine normative correctness.

Check operation ownership carefully: Review must not silently acquire CREATE, START, Git finalization, progression, or domain repair ownership.

### D. Candidate / Context / Evidence

Stress the reproducibility model:

- base revision
- pre-existing tracked dirty content
- owned Work delta
- deleted files
- allowed untracked results
- symlinks / paths leaving Project
- generated files
- external artifacts
- changes made after test execution but before Candidate freeze
- Repair changing a previously verified assumption
- Candidate snapshot loss while the operation checkpoint remains

Check whether `candidate_hash`, `review_context_hash`, and `effective_policy_hash` are sufficient to prevent unsafe evidence reuse.

### E. Finding / Repair / Recurrence

Check:

- duplicate merge by repair identity
- many Findings -> one Repair
- one Finding -> multiple Repair attempts
- A/B/C classification
- strong causality requirement for C
- Repair Batch boundaries
- semantic-impact selective re-review
- strategy-change trigger after repeated supported repair failure

Try to construct false B/C classifications, hidden recurrence, repair-loop deadlocks, or cases where batching destroys causality.

### F. Coverage / Reviewer Independence

Check whether the proposed discovery model can distinguish:

- zero findings because the candidate is good
- zero findings because the reviewer missed relevant surface

Stress:

- reviewer failure
- specialist selection
- uncovered / undecidable surfaces
- history contamination between reviewers
- parallel vs sequential execution
- whether combining viewpoints can erase mandatory coverage

### G. LOW Work

Check whether LOW handling can simultaneously satisfy:

- source Phase/Roadmap completion is not blocked
- LOW findings are not silently lost
- LOW Works do not create ambiguous selection deadlocks
- normal Roadmap progression remains primary
- `blocked != idle`
- explicitly selected LOW Work behaves as a normal Work

Look specifically at whether using existing `planned_next` plus standalone scope is enough when there are multiple unrelated LOW chains or pre-existing standalone Works.

### H. Durable Review History

Check whether the proposed compact durable history is sufficient for:

- cross-run recurrence
- B/C causality
- LOW provenance
- Policy Learning
- audit after clone / runtime cleanup

Look for information that is kept only in runtime but would later be needed for a justified decision.

Also check the opposite risk: accidentally turning Review History into a second canonical lifecycle ledger.

### I. Self-Evolution / Project-local Policy

Stress:

- self-approval
- Goodhart effects
- weak opportunity denominators
- correlated observations being counted as independent
- repeated local bugs being mistaken for general rules
- temporary guards becoming permanent accidentally
- lightening hiding the very escapes used to evaluate it
- attribution: whether a later outcome can actually be attributed to the policy change
- rollback safety

Check the frozen pre-change meta-review rule and whether it truly prevents a proposal from weakening its own approval conditions.

### J. Global Promotion

Check:

- evidence independence across Projects
- generalization identity
- Project-specific details leaking into Global rules
- Workline root authority
- Global version compatibility with Project Profiles
- suppression of outdated local lightening
- Global rollback
- in-progress Runs retaining their frozen policy

### K. Simplicity / Existing Mechanism Reuse

Identify both directions of design error:

1. unnecessary new concepts where existing Workline mechanisms already suffice;
2. concepts that are semantically distinct but have been forced into an existing mechanism in a way that will make recovery or ownership unclear.

Do not recommend a new Controller/Scheduler/state field merely for organizational convenience.

## Required Finding format

For every accepted Finding, output:

```text
ID:
Category: Problem | Improvement
Severity: HIGH | MID | LOW
Affected area:
Concrete failure scenario:
Why the current design does not prevent it:
Minimal repair direction:
Evidence / live-repo references:
```

Severity meaning:

- HIGH: proceeding without repair risks correctness, safety, data, recovery, completion trust, or broad downstream damage
- MID: clearly wrong and should be repaired before implementation, but less broadly/fatally damaging
- LOW: worthwhile improvement that can safely be handled later

Do not use severity as a confidence score.

If a review statement is unsupported, dismiss it rather than turning it into a Finding.

If multiple reports describe the same central issue and one repair resolves all, merge them by repair identity and preserve provenance.

## Final output

End with exactly these sections:

### Unresolved HIGH/MID
List all unresolved HIGH/MID Finding IDs and one-line summaries. If none, say `None`.

### HUMAN decisions required
List only decisions that genuinely require changing/choosing a user-controlled requirement, authority, security/permission boundary, external irreversible contract, or capability/policy boundary. If none, say `None`.

### Must repair before implementation
List the minimum Finding IDs that must be repaired before implementation may begin.

### Verdict
Choose one:

- `REPAIR`
- `HUMAN`
- `READY`

Do not choose READY merely because the design is detailed. Choose READY only if no unresolved HIGH/MID obligation or required HUMAN decision remains.
