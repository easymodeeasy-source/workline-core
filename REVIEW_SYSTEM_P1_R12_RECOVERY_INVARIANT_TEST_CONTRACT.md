# Review System P1 — R12 Recovery / Invariant Test Contract Freeze

Status: CONTRACT FROZEN / IMPLEMENTATION NOT STARTED

This checkpoint freezes the minimum interruption and invariant test matrix required before P1/P2/P3 Review contracts may be considered implemented. It is non-normative until implementation and authority activation.

## 1. Live test/recovery foundation inspected

The existing repository already has broad recovery-oriented tests for mutation staging, branch binding, declared write scopes, lifecycle resume, bootstrap resume, cancellation decisions, finalized-effect branch behavior and end-to-end operation flows.

The live Mutation Controller is explicitly designed so a stage can be partially applied: all effects are durably recorded first, then each effect is classified against reality as UNAPPLIED / MATCHING / MISMATCH on resume. Review tests must extend this style rather than replacing it with mocks that skip real persisted intent/state.

## 2. Test philosophy

Every critical Review boundary is tested in three dimensions where applicable:

```text
A. uninterrupted happy path
B. crash/interruption after each durable boundary
C. conflicting external/local change before resume
```

Assertions must cover both:

```text
what DID happen exactly once
what MUST NOT have happened yet
```

especially push, lifecycle terminalization, duplicate Receipt/Consumption, executor re-run and ID reallocation.

Tests prefer real temporary Git repositories and real canonical file/mutation records, following existing test conventions. Network-dependent push cases use local bare remotes where possible.

## 3. R1/R2 canonical layout and IDs

Required tests:

- legacy Project with no `.workline/review/` validates;
- first canonical Review write lazily creates exact review directories/files;
- `.workline/runtime/review/` never satisfies canonical ReviewStore lookup;
- malformed/unknown Review path/file causes structural validation failure;
- symlink/reparse substitution at canonical Review paths is refused where applicable;
- Gate filename/run/generation mismatch is rejected;
- non-contiguous generation chain is rejected;
- predecessor digest mismatch is rejected;
- central Review ID prefixes round-trip through `new_id/kind_of/is_valid_id`;
- retry of same mutation reservation reuses Review IDs;
- same reservation key requested with another kind reconciles/refuses;
- generation numbering derives from validated chain and cannot skip/duplicate.

## 4. R3 Gate Generation interruption matrix

At minimum test:

### Accepted task durability

```text
G1 accepted T1 persisted
-> process exits before launching/retrieving result
-> resume sees T1 unsettled
-> authorization cannot seal
```

### Result arrives before settlement generation

```text
external/runtime result exists
-> crash before canonical G2
-> clone/resume has only G1
-> T1 remains unsettled; no seal
```

### Settlement generation partial write/commit

```text
G2 effect recorded, write unapplied
G2 file written, mutation flag unsaved
G2 committed locally, later stage not recorded
```

Each resumes without duplicate generation/task ID or loss of obligation.

### Seal + Receipt same stage

Interrupt:

```text
before either write
Gsealed written / Receipt absent
Receipt written / stage applied flag not saved (if effect order permits)
after both writes / before local commit
after commit / before proof or push
```

Resume must never permit consumption until both exact canonical facts validate.

### New report invalidates seal

```text
sealed G4/R1
-> new supported report requires G5 open + R1 supersession
-> crash after either effect
-> resume cannot consume R1
```

## 5. R4 terminal event + Consumption matrix

Using a Review-v1 Work, interrupt after:

```text
terminal stage durably recorded, no effects applied
work_target_removed applied
work_completed E1 applied
Consumption C1 written
stage flags partially unsaved
terminal K2 committed locally
terminal K2 proof passed
terminal push fails/succeeds
```

Required invariants:

- no duplicate E1;
- no second Consumption ID;
- exact R1/E1/K1/operation tuple reused;
- Receipt cardinality remains 0-or-1;
- E1 cardinality remains 0-or-1;
- if E1 exists and C1 is temporarily absent locally, pending mutation deterministically fills C1 before terminal publication/final completion;
- conflict inserted at C1 path is reconcile, never overwrite;
- conflicting second Consumption for same Receipt/Event makes Review validation fail closed.

## 6. R5 result commit / proof / push matrix

Required Work result cases:

```text
executor returns Completed
-> K1 commit not yet recorded
K1 effect recorded / commit not made
K1 made / mutation commit ID save interrupted
K1 made + identified / post-commit proof not run
proof fails
proof passes / push not recorded
push recorded / network failure
push succeeds / terminal stage not begun
```

Assertions:

- executor is not rerun merely to finish a proven existing K1 path;
- no push occurs before proof pass/binding;
- failed proof never creates push effect;
- push retry uses same destination/branch/commit and rechecks latest authorization;
- result K1 may be remotely published while Work remains non-terminal until K2;
- no-result Work creates/proves authorization metadata K1 before terminal consumption;
- legacy operation behavior remains unchanged until explicit review-v1 activation.

## 7. R6 Review-validity HEAD advancement tests

Cases:

- unrelated intervening commit with complete proven closure -> reuse allowed;
- intervening commit touches Review Context dependency -> new Candidate;
- touches test helper/evidence dependency -> new Candidate or evidence reacquisition as contract dictates;
- `.gitattributes`/filter/tool config material change -> no fast-path reuse;
- closure completeness unknown -> new Candidate even when recorded result paths untouched;
- base rewritten/rebased -> reconcile/Git incompatibility, not semantic fast path;
- merge in intervening history with material dependency touched in a parent -> detected;
- changed-then-reverted dependency still counts as changed for reuse decision;
- non-repo runtime/tool identity change invalidates reuse where bound.

No test may pass fast path solely because `commits_touching(result_paths)==[]`.

## 8. R7 Class A tests

Required cases:

- operation-owned transformed K1 eligible -> exact C2 Review -> R2 -> metadata-only K2 -> proof -> push;
- K1 contains unexpected/non-owned path -> Class A refused/reconcile;
- K1 multiple-parent -> refused;
- branch/lineage changes during C2 Review -> adoption invalid;
- push dry-run says `=` for exact K1 before K2 -> already published/historical escape, no normal adoption;
- dry-run fast-forward/new branch -> unpublished classification may continue;
- dry-run reject/unknown -> reconcile;
- K2 exact metadata-only -> accepted;
- hook adds domain/transition delta to K2 -> reconcile;
- K2 metadata bytes transformed unexpectedly -> reconcile;
- **no recursive R3/K3 Receipt chain is created**;
- failure after K2 commit but before push resumes same K2 proof/push.

## 9. R8 Roadmap semantic round-trip tests

Construct reviewed `RoadmapPlan` cases covering:

- multiple Phases in declared order;
- scope/out-of-scope absent vs present semantics;
- planned/requires Phase relations;
- stable reserved IDs across resume;
- canonical render/loader normalization.

Fault-injection variants deliberately change:

```text
relation type/endpoint
Phase desired state
Roadmap section
created ID
extra/missing entity/relation
serializer/loader interpretation fixture
```

Request identity may remain syntactically present, but semantic round-trip must fail.

Successful case must bind exact registration commit/projection into Planning Consumption.

## 10. R9 Phase-entry semantic round-trip tests

Cover:

- multiple normal Works;
- integration generation/dependencies;
- optional human confirmation + target;
- Related edges;
- planned_next / requires_completion;
- stable reserved IDs/resume;
- exact Phase/Roadmap origin.

Critical `entry` cases:

```text
canonical graph uniquely selects A, entry=A -> PASS
canonical graph uniquely selects A, entry=B -> reject before persistence/Review READY
canonical graph leaves A/B ambiguous, entry=A -> review-v1 reject (ephemeral hint cannot be sole persisted meaning)
no explicit entry, canonical graph uniquely selects A -> PASS
```

After clone/reload, unique first Work must be derivable without Review metadata.

## 11. R10 Policy adapter contract tests

P1 tests only the generic protocol/harness:

- adapter after-state round-trip equality passes for a synthetic deterministic adapter;
- byte-equal but semantic-default-different fixture fails;
- stale before-version fails;
- loader/schema identity change invalidates proof;
- unimplemented Project/Global Policy adapter fails explicitly, never falls back to `project.yaml`/generic dictionary storage.

Actual policy schemas are tested in P6/P7.

## 12. R11 Evidence completeness tests

For synthetic adapters:

- every required class covered/pinned/denied -> complete;
- one required class unknown -> no cross-Candidate reuse;
- undeclared ambient environment -> unknown;
- subprocess child escapes trace -> corresponding classes unknown;
- network denied mechanically -> may count denied;
- prompt-only “no network” -> not denied;
- vocabulary version change invalidates automatic completeness;
- tool/runtime identity change invalidates reuse;
- complete repo dependencies unchanged -> reuse permitted;
- one repo dependency changed/reverted -> invalidated;
- flaky single PASS cannot be promoted to reusable certainty without its repetition contract.

## 13. Clone/runtime-cleanup tests

For a Project with canonical open/sealed Review state:

```text
remove .workline/runtime/** or clone repository fresh
-> ReviewStore reconstructs gate/Receipt/Consumption state from canonical files
-> ProjectView lifecycle remains based only on entities/relations/events
```

Open task scratch may be gone and must be rerun/retrieved; sealed authorization may not depend on missing runtime-only data.

## 14. Authority boundary tests

Mechanical tests must prove:

- Review metadata cannot make `state.py` report a Work/Phase/Roadmap lifecycle transition;
- adding/removing Receipt/Consumption alone does not change `ProjectView` lifecycle;
- Roadmap/START remain owners of their domain transitions;
- Review write stages occur under the same Project execution-lock/mutation authority as the owning top-level operation;
- a foreign Project context cannot mutate Review canonical state;
- concurrent top-level writer sees ordinary Project lock refusal.

## 15. Required test gate before activation

P1 common infrastructure is not considered implementation-complete until all R1-R7/R10/R11 common-contract tests pass.

P2 Planning Review activation additionally requires R8/R9 round-trip/recovery tests.

P3 START Review-v1 activation additionally requires full R4/R5 terminal/commit/push/Class-A interruption matrix and compatibility tests.

A passing happy-path suite without interruption/fault-injection coverage is insufficient for activation.

## 16. Architecture blocker / HUMAN

Architecture blocker: `None`.

HUMAN decision: `None`.

The live test suite already uses the same recovery-oriented style. P1 work is to extend it across every newly introduced durable Review boundary.