# Review System P1 — Integration Contract Reconnaissance Checkpoint

Status: ROUND 2 CONTRACT REPAIRS FROZEN / IMPLEMENTATION NOT STARTED / RE-REVIEW REQUIRED

This checkpoint records Candidate 7 P1 Integration Contract Reconnaissance, first independent-review repair, and second independent-readiness repair.

Runtime authority remains `registry.md`, registry-routed canonical Skills and live code until implementation/activation.

## 1. Architecture baseline

```text
Candidate 7 architecture: RETAIN
Architecture blockers: 0
HUMAN decisions: 0
Candidate 8 required: No
```

Review remains a subordinate authorization/quality gate. `ProjectView/state.py` remains lifecycle/progression authority only from canonical entities/relations/events. Review metadata never becomes lifecycle truth.

## 2. First independent review

Nine contract seams were accepted and repaired: K1 commit-ID crash recovery, generation serialization, no-follow writer safety, clone-safe task descriptor, immutable create-only records, terminal Consumption totality, Roadmap ownership of Phase-entry self-selection, Git committability preflight and canonical predecessor digest/test coverage.

Umbrella checkpoint:

`REVIEW_SYSTEM_P1_CONTRACT_REPAIR_AFTER_EXTERNAL_REVIEW.md`

## 3. Second independent readiness review

Second review result:

```text
F1 K1 identity crash recovery       RESOLVED
F2 generation serialization         PARTIAL -> P1R-01
F3 write-time no-follow safety      RESOLVED
F4 clone-safe async task            PARTIAL -> P1R-02
F5 immutable create-only            RESOLVED
F6 Consumption totality             PARTIAL -> P1R-03
F7 Roadmap authority ownership      RESOLVED
F8 Git committability preflight     RESOLVED
F9 predecessor digest exactness     RESOLVED

P1R-04 LOW improvement: accepted
Verdict: REPAIR
```

Round-2 umbrella checkpoint:

`REVIEW_SYSTEM_P1_CONTRACT_REPAIR_ROUND2.md`

## 4. Round-2 frozen repairs

### P1R-01 — same-run generation recovery

Every generation mutation declares in initial `WriteScope.files`:

```text
exact generation file path
+ .workline/review/gates/<review_run_id>/.generation-serialization
```

The latter is scope-only, never a physical/canonical file. Before calculating a new generation, pending same-run generation mutations must be discovered and resumed/reconciled. Thus physical G(N+1) creation followed by crash before `applied` save cannot let a second invocation open G(N+2).

Affected contracts: R2, R3, R12.

### P1R-02 — exact clone-safe task reconstruction

P1 adds immutable provenance:

```text
.workline/review/candidate-snapshots/<candidate_hash>.yaml
.workline/review/task-inputs/<review_task_id>.yaml
```

Accepted task launch requires exact Candidate/request reconstruction material, not merely IDs/digests. Fresh clone must reconstruct exact Candidate/request, recompute matching digests and reuse the same task ID. Missing/incomplete material fails closed.

Affected contracts: R1, R3, R12.

### P1R-03 — durable legacy/review-v1 terminal classification

P3 adds immutable activation:

```text
.workline/review/activation/work-terminal-v1.yaml
```

It binds the exact pre-activation legacy event prefix using count + SHA-256 and activation base. Post-activation review-v1 `work_completed` events carry explicit non-lifecycle operation-contract metadata. Missing/unknown/contradictory marker after activation reconciles; never legacy fallback. `state.py` ignores Review event metadata.

Affected contracts: R1, R4, R5, R12.

### P1R-04 — hook/filter external side-effect guard

Review-v1 `commit_local()` must make no uncontrolled external/network side effect before proof. Applicable hooks/filters capable of external side effects must be mechanically denied/contained or commit fails closed. Content-defining filters cannot simply be disabled if doing so changes Git persistence semantics.

Affected contracts: R5, R12; R6/R11 continue to bind Git/tool dependency identity.

## 5. Current contract documents

Round-2 changes are directly reflected in:

- `REVIEW_SYSTEM_P1_R1_DURABLE_LAYOUT_CONTRACT.md`
- `REVIEW_SYSTEM_P1_R2_ID_RESERVATION_CONTRACT.md`
- `REVIEW_SYSTEM_P1_R3_GATE_GENERATION_MUTATION_CONTRACT.md`
- `REVIEW_SYSTEM_P1_R4_CONSUMPTION_UNIQUENESS_CONTRACT.md`
- `REVIEW_SYSTEM_P1_R5_START_COMMIT_PROOF_PUSH_CONTRACT.md`
- `REVIEW_SYSTEM_P1_R12_RECOVERY_INVARIANT_TEST_CONTRACT.md`

R6/R7/R8/R9/R10/R11 retain their previous repaired/frozen meaning unless explicitly referenced by the Round-2 checkpoint.

## 6. Current state

```text
Candidate 7 architecture: RETAIN
Architecture blockers: 0
HUMAN decisions: 0
Candidate 8 required: No

P1R-01: REPAIRED/FROZEN
P1R-02: REPAIRED/FROZEN
P1R-03: REPAIRED/FROZEN
P1R-04: ACCEPTED/FROZEN

P1 implementation: NOT STARTED
Implementation activation: BLOCKED pending independent re-review
```

## 7. Next stage

Run another focused independent Implementation Readiness re-review against live `main` and the Round-2 repaired contracts.

Allowed final verdicts:

```text
REPAIR
HUMAN
READY_FOR_P1_IMPLEMENTATION
```

Only `READY_FOR_P1_IMPLEMENTATION` permits P1 implementation to start.
