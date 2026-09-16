# Review System P1 — R3 Gate Generation Mutation Contract Freeze

Status: CONTRACT FROZEN / IMPLEMENTATION NOT STARTED

This checkpoint freezes how Candidate 7's minimum durable Review Gate generations enter canonical Project state. It is non-normative until implemented and routed through canonical authority.

## 1. Live facts inspected

The live mutation model already gives every established-Project writer one top-level operation owner, one Project execution lock, and one durable mutation intent. Child registration cores join that mutation; they do not open another top-level controller.

The lock serializes Project writers from the point state-changing operations read decisive Project state through mutation effects, validation, commit and push. `MutationController` decides no domain meaning; it records/replays the physical effects the operation owner decided.

Candidate 7 requires Review to remain an authorization gate, not a second progression/lifecycle owner. Therefore P1 must not introduce a parallel Review lifecycle controller just to persist Review state.

## 2. Frozen ownership rule

**Canonical Review gate state is written by the top-level operation that is currently using the gate.**

Examples:

```text
Roadmap planning Review -> Roadmap operation owns the mutation
Phase-entry Review      -> Roadmap operation owns the mutation
Work Formal Review      -> START owns the mutation
Project Policy Review   -> future Project Policy Change owner
Global Policy Review    -> future Global Policy Change owner
```

There is no general `ReviewController` that may advance Roadmap/Phase/Work state.

P1 does not add a standalone `review-gate` progression operation.

## 3. Async reviewer/callback rule

External reviewer/shadow callbacks do **not** directly write the Project while another operation owns the Project lock.

The durable contract is:

```text
1. parent operation durably records task acceptance in a new Gate generation
2. external execution happens
3. result is returned/retrieved by a Project operation holding the lock
4. that operation validates task identity/result identity
5. it durably records settlement/adjudication in a new Gate generation
6. only then may authorization sealing/consumption proceed
```

If the process exits after acceptance but before settlement, the canonical generation still says the task is accepted and unsettled. A later invocation must retrieve/re-run/reconcile the task; it cannot seal the generation by assuming the missing result was harmless.

This is deliberately fail-closed and means a callback service does not need independent Project write authority.

## 4. Immutable generation transition

A gate transition never updates an existing generation file. It creates the next immutable generation file.

Conceptual state transitions:

```text
G1 open: task T accepted
G2 open: T settled, raw-report-set digest changed
G3 open: adjudication/repair obligation changed
G4 sealed_authorized: all authorization obligations resolved
```

Each generation contains the full minimum gate snapshot needed to decide authorization, not merely an event delta. This lets the latest valid generation stand on its own after validating its predecessor chain.

The exact record includes at least:

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
accepted_task_ids: [...]
settled_task_ids: [...]
status: open | sealed_authorized
receipt_id: rcp_... | null
```

Fields not yet meaningful for an early open generation use explicit null/empty canonical values rather than being silently omitted where omission would make two semantic states ambiguous.

## 5. Generation write stage

Within the owning mutation, a generation is persisted as an ordinary canonical `Effect.write_file()` to the exact R1 path:

```text
.workline/review/gates/<review_run_id>/<generation:06d>.yaml
```

The generation stage must be recorded before any later effect whose authority depends on that generation.

Example:

```text
stage review-gate-G4
  write G4 sealed_authorized
  write Receipt R1 (if this seal issues R1)

apply stage
-> exact ReviewStore reread/validation
-> then later authorized operation stages
```

Seal + newly issued Receipt are one mutation decision/stage where both are first created, so a crash cannot durably present a sealed generation that points to an unrecorded Receipt intent without the same mutation knowing the missing Receipt effect.

Physical writes can still be partial; Mutation recovery resumes the exact remaining effect.

## 6. Open generation creation

The first Review generation is written before any accepted async/mandatory task is launched if that task's existence matters to terminal authorization.

Therefore:

```text
reserve rr_X / task IDs
-> write G1 containing accepted task IDs
-> apply/commit canonical G1 as required by the operation's persistence boundary
-> launch/continue tasks
```

An external task that was launched but never durably accepted does not count as a required pre-cutoff task. The orchestration must launch only after acceptance persistence succeeds when terminal-cutoff semantics depend on it.

## 7. Settlement rule

A task is `settled` only when the latest canonical Gate generation records its terminal disposition and the result/adjudication digests needed by that disposition.

Terminal dispositions are versioned values, conceptually:

```text
completed
failed
cancelled
timed_out
```

Whether `failed/cancelled/timed_out` satisfies an authorization obligation is determined by Effective Policy; the status itself does not imply permission to seal.

A raw report that may affect adjudication cannot be represented as settled merely because bytes arrived. The generation that counts the task settled must also bind the report-set/adjudication/obligation digests that reflect its disposition.

## 8. Seal rule

A generation may become `sealed_authorized` only if all of the following hold from canonical inputs:

```text
accepted required tasks == settled required tasks
required reviewers complete
coverage obligations resolved
unadjudicated raw reports = 0
unresolved HIGH/MID = 0
required LOW handling complete
required reverification complete
no unresolved supported repair-induced blocker
HUMAN pending = 0
Candidate/Context/Policy identities current
```

The seal stage reserves/writes the Receipt ID defined by R2. ReviewStore rereads both exact files before any consuming stage relies on them.

No mutable `authorized=true` flag elsewhere exists.

## 9. Invalidation / supersession

If a new supported fact invalidates a previously sealed generation before its Receipt is consumed:

```text
sealed G4 / Receipt R1
-> owning operation opens G5 (open) with new obligations
-> same mutation writes supersession record for R1
-> only after both are canonical may work continue toward a future seal
```

A consumer always rechecks latest Gate chain and supersession immediately before consumption. It never trusts a mutation note saying a Receipt used to be valid.

If a later generation exists, the older generation is derived-superseded even if a separate Receipt supersession file is absent because no Receipt was issued for that older generation.

## 10. Mutation invocation binding

The owning mutation's invocation must bind the Review gate identity sufficiently to prevent a retry of a different Candidate/target from taking over a pending Review mutation.

At minimum the Review-aware operation mutation/checkpoint binds:

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

Where the existing operation already has a durable request/design identity, Review binding augments it; it does not replace Roadmap/Phase/Work operation identity.

A mismatch on resume is reconcile or new Candidate/Review according to the owning operation's contract; never silently overwrite the pending record.

## 11. Git persistence boundary

Open generations that must survive clone/process loss are canonical and therefore committed through the owning operation's exact Git path set. A Review gate must never claim clone-safe accepted/settled/sealed state while its only durable copy is an uncommitted runtime file.

The exact commit/push sequencing differs by operation kind and is frozen further in R5/P2/P6/P7. P1 common rule is:

```text
canonical gate fact relied on after clone
=> included in a proven local commit before the dependent external/terminal boundary
```

Remote-less Projects remain valid; clone-safe means canonical/tracked local Git state, not mandatory existence of a remote.

## 12. No second state machine authority

Review Gate generations form an authorization-state chain, but they do not derive Work/Phase/Roadmap lifecycle.

Forbidden:

```text
state.py sees sealed_authorized -> marks Work completed
Review gate decides next Phase -> advances Roadmap
callback writes work_completed directly
```

Allowed:

```text
START asks ReviewStore whether exact Receipt is currently consumable
-> START, as lifecycle owner, decides/records its canonical terminal transition
```

## 13. Architecture blocker / HUMAN

Architecture blocker: `None`.

HUMAN decision: `None`.

The existing Project lock + parent operation + Mutation recovery model is sufficient. P1 needs a Review orchestration layer and ReviewStore, not a competing progression controller.