# Review System P1 — R3 Gate Generation Mutation Contract Freeze

Status: CONTRACT FROZEN / REPAIRED AFTER EXTERNAL REVIEW / IMPLEMENTATION NOT STARTED

This checkpoint freezes how Candidate 7's minimum durable Review Gate generations enter canonical Project state. It is non-normative until implemented and routed through canonical authority.

## 1. Live facts inspected

The live mutation model gives every established-Project writer one top-level operation owner, one Project execution lock, and one durable mutation intent. Child registration cores join that mutation; they do not open another progression controller.

The lock serializes active Project writers while the process lives. Crash releases it. Therefore pending mutation scope, not the OS lock alone, must preserve cross-crash generation exclusivity.

Candidate 7 requires Review to remain an authorization gate, not a second progression/lifecycle owner.

## 2. Frozen ownership rule

Canonical Review gate state is written by the top-level operation currently using the gate.

Examples:

```text
Roadmap planning Review -> Roadmap mutation owner
Phase-entry Review      -> Roadmap mutation owner
Work Formal Review      -> START mutation owner
Project Policy Review   -> future Project Policy Change owner
Global Policy Review    -> future Global Policy Change owner
```

There is no standalone Review progression controller.

## 3. Crash-safe generation allocation / pending-mutation conflict

For every new Gate generation N+1, freeze this order:

```text
hold Project execution lock
-> load/validate full immutable Gate chain
-> determine exact N+1 canonical path
-> open/resume the owning Mutation with that exact path already in initial WriteScope.files
-> only then reserve IDs / record generation effects
```

The N+1 path may not be added only later through `extend_scope()`.

If implementation later needs a Review conflict resource that cannot be expressed as an exact path before mutation open, it must introduce a logical conflict-resource primitive whose pending-mutation overlap semantics are equivalent or stricter. It may not rely on Project lock lifetime alone.

This is the cross-process invariant:

```text
pending intent for G(N+1) durable
+ process crash / lock released
-> later invocation sees/resumes/refuses against that pending conflict
-> no second N+1/fork may be created
```

## 4. Async reviewer/callback rule

External reviewer/shadow callbacks do not directly mutate canonical Project state.

Durable sequence:

```text
1. parent operation writes accepted task identity/descriptor in a new Gate generation
2. that generation reaches the required canonical Git persistence boundary
3. external execution happens
4. result is returned/retrieved by a Project operation holding the lock
5. task identity/result identity are validated
6. settlement/adjudication are written in a new Gate generation
7. only then may sealing/consumption proceed
```

A process exiting after acceptance but before settlement leaves canonical task state accepted/unsettled. Authorization cannot infer success from missing runtime data.

## 5. Clone-safe accepted task descriptor

A Gate generation that records a task as accepted must carry, directly or through an immutable canonical task descriptor referenced by the generation, at least:

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

Provider/job handles may remain runtime-only. Losing `.workline/runtime/**` must not erase the task's identity or request binding. Canonical descriptor data must be sufficient to retrieve or rerun the task safely according to Effective Policy.

A bare `rtk_*` ID is not clone-safe task evidence.

Settlement must bind the same canonical task identity plus terminal disposition/result/adjudication digests.

## 6. Immutable generation transition

A gate transition never edits an existing generation file. It creates the next immutable generation file.

Conceptual sequence:

```text
G1 open: T accepted
G2 open: T settled / report-set changed
G3 open: adjudication/repair obligation changed
G4 sealed_authorized: authorization obligations resolved
```

Each generation is a full minimum snapshot, not merely an event delta.

Minimum record includes at least:

```yaml
workline: workline-review-gate
version: 1
review_run_id: rr_...
generation: 4
previous_generation: 3
previous_digest: ...
review_kind: ...
target_identity: ...
operation_identity: ...
candidate_hash: ...
review_context_hash: ...
effective_policy_hash: ...
evidence_digest: ...
coverage_digest: ...
raw_report_set_digest: ...
adjudication_digest: ...
obligation_digest: ...
accepted_tasks: [...canonical descriptors/refs...]
settled_tasks: [...terminal bindings...]
status: open | sealed_authorized
receipt_id: rcp_... | null
```

Generation predecessor digest follows R1's exact canonical-byte SHA-256 contract.

## 7. Generation/Receipt write stage

Within the owning mutation, each generation is persisted at:

```text
.workline/review/gates/<review_run_id>/<generation:06d>.yaml
```

using R1's immutable create-only Review writer.

A seal that first issues Receipt R1 records both immutable creates in one mutation stage:

```text
stage review-gate-G4
  create immutable G4 sealed_authorized
  create immutable Receipt R1
```

All effects are durable intent before any is applied. Physical application may still be partial; resume completes only the missing exact effect.

No consuming stage may rely on the seal until exact ReviewStore reread validates both facts.

## 8. Open generation creation and task launch cutoff

If task existence matters to terminal authorization:

```text
reserve run/task IDs
-> determine G1 path and open mutation with path in initial WriteScope
-> write G1 with clone-safe accepted task descriptor
-> persist/commit canonical G1 as required
-> only then launch/continue external task
```

A task launched before durable canonical acceptance does not count as an accepted pre-cutoff task and must not silently enter the authorization set later.

## 9. Settlement rule

A task is settled only when the latest canonical generation records its terminal disposition and the report/adjudication/obligation digests required by that disposition.

Conceptual dispositions:

```text
completed
failed
cancelled
timed_out
```

Effective Policy decides whether a non-completed disposition satisfies an obligation. Runtime result arrival alone does not settle anything.

## 10. Seal rule

A generation may be `sealed_authorized` only if canonical inputs prove all required tasks/coverage/adjudication/repair/reverification/HUMAN/Candidate/Context/Policy obligations resolved.

The seal stage reserves/writes the Receipt ID defined by R2. No mutable `authorized=true` flag elsewhere exists.

## 11. Invalidation / supersession

A supported fact invalidating a seal before consumption creates a later `open` generation and supersession record before the old Receipt can proceed.

The repaired cross-crash generation serialization rule applies equally to invalidation generations.

Consumer always rechecks latest validated Gate chain and supersession immediately before consumption.

## 12. Mutation invocation binding

The owning mutation binds at least:

```text
review_run_id
review_generation
candidate_hash
review_context_hash
effective_policy_hash
obligation_digest
receipt_id when issued
proof_phase
```

Existing Roadmap/Phase/Work request identity remains authoritative and is augmented, not replaced.

Mismatch on resume is reconcile/new Candidate according to the owning operation contract; never silently overwrite pending Review intent.

## 13. Git persistence boundary

Any gate fact relied on after clone/process loss is canonical and must reach tracked local Git state before the dependent external/terminal boundary.

Remote-less Projects remain valid; clone-safe means canonical/tracked local state, not mandatory remote publication.

R1 committability preflight applies before first Review effect so canonical state is not created only to discover later that Git ignores it.

## 14. No second state machine authority

Gate generations are authorization state only.

Forbidden:

```text
state.py reads sealed_authorized -> Work complete
Review chooses next Phase as lifecycle truth
callback appends work_completed
```

Allowed:

```text
START/Roadmap queries exact current Review authorization
-> operation owner records its own canonical transition
```

## 15. External-review repair disposition

Accepted and repaired here:

- Project lock alone is not generation serialization;
- exact N+1 path belongs in initial pending `WriteScope`;
- accepted async task descriptors are clone-safe canonical facts;
- every generation transition uses the same repaired serialization discipline.

Architecture blocker: `None`.

HUMAN decision: `None`.
