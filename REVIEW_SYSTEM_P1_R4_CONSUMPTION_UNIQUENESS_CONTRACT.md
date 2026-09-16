# Review System P1 — R4 Consumption Logical Uniqueness Contract Freeze

Status: CONTRACT FROZEN / IMPLEMENTATION NOT STARTED

This checkpoint freezes the common Consumption identity/cardinality contract under Candidate 7. It is non-normative until implemented and routed through canonical authority.

## 1. Live facts inspected

The live Mutation Controller already provides:

- recovery-safe ID reservation;
- exact file-effect replay classification by expected content/base;
- exact event replay classification by event ID + full record;
- one Project execution lock for state-changing operations;
- one durable stage containing multiple effects before any effect is applied.

These mechanisms are sufficient to make a terminal event + Consumption pair replay-safe, but path uniqueness by itself does not enforce Candidate 7's logical cardinality. P1 therefore needs ReviewStore-level logical validation in addition to Mutation effect safety.

## 2. Common Consumption record

Every Consumption is immutable and stored at:

```text
.workline/review/consumptions/<consumption_id>.yaml
```

Common record core:

```yaml
workline: workline-review-consumption
version: 1
consumption_id: rcs_...
receipt_id: rcp_...
review_run_id: rr_...
review_generation: N
review_kind: ...
target_identity: ...
operation_identity: ...
operation_mutation_id: mut_...
authorized_candidate_hash: ...
kind_binding: {...}
```

`kind_binding` is versioned by `review_kind`; the common core does not invent a Work terminal event for Planning/Policy kinds.

The Receipt referenced by the Consumption must exist, be structurally valid, bind the same run/generation/candidate/target/operation identities, and be currently consumable at the time the owning operation records the Consumption stage.

## 3. Stable physical identity

The consuming operation reserves the Consumption ID before recording any Consumption effect:

```text
reservation semantic key = review-consumption:<receipt_id>
```

Retry/resume of the same consumption reuses the same `rcs_...` ID.

A canonical file with that ID and exact expected content is idempotent MATCHING. Same path + different content is reconcile required through ordinary immutable-file classification/validation.

## 4. Global logical uniqueness indexes

`ReviewStore` builds logical indexes from all valid Consumption records:

```text
by_receipt[receipt_id]
by_terminal_event[event_id]          # Work terminal kinds only
by_kind_persisted_result[key]        # kind-specific where a unique persisted transition/result identity exists
```

Structural validation fails closed if an index that must be 0-or-1 contains conflicting records.

This is a canonical scan/index over immutable records, not a mutable counter/index file that could drift.

## 5. Common cardinality

Frozen invariant:

```text
one Authorization Receipt -> at most one valid Consumption
```

Before recording C1:

```text
no existing Consumption for R1
-> may create C1

existing exact semantic Consumption for R1
-> idempotent reuse; no new record

existing Consumption for R1 with different kind_binding/result/operation
-> reconcile required
```

A superseded Receipt may not receive a new Consumption.

A Receipt already consumed remains consumed even if a later Review generation exists; later history does not rewrite the already-finished domain operation. Any post-terminal discovery follows the historical-escape/next-work rules rather than forking Consumption.

## 6. Work terminal binding

Work completion Consumption `kind_binding` contains at minimum:

```yaml
kind: work_terminal_v1
authorized_result_commit_sha: <K1>
terminal_event_id: evt_...
terminal_event_type: work_completed
work_id: w_...
terminal_commit_sha: <known only in post-commit proof record/binding where non-self-referential; see R5>
```

The non-circular binding is:

```text
Receipt R1 authorizes exact result commit K1/Candidate
terminal event E1 consumes R1
Consumption C1 binds R1 + K1 + E1 + operation mutation
```

A Consumption file embedded in the same terminal commit as E1 must not require that containing commit's SHA in its own bytes. If terminal commit identity needs durable proof, it is verified externally/post-commit and may be represented in a later non-recursive proof record only if future phases require it. P1 does not create a self-reference.

Frozen Work cardinality:

```text
receipt_id        -> 0 or 1 Consumption
terminal_event_id -> 0 or 1 Consumption
```

Conflicts:

```text
same R1 + different E/K1/operation -> reconcile
same E1 + different R              -> reconcile
same exact R1/E1/K1/operation      -> idempotent replay
```

## 7. Terminal event reservation/order

For Work terminalization, START reserves the terminal event ID and Consumption ID before recording the terminal stage.

The stage contains, in deterministic order:

```text
1. exact AuthorizedTransitionProjection event effects
2. exact OperationMetadataProjection Consumption write
```

The order is frozen for reproducibility, but correctness does not rely on physical atomicity. If a crash happens after effect 1 and before effect 2, the Mutation record already contains both effects and resume classifies event 1 MATCHING and applies only Consumption 2. If effect ordering is later expanded to include more terminal events, all transition effects precede Consumption.

No terminal Git commit/push may be authorized until the stage rereads as complete and ReviewStore cardinality validation passes.

## 8. Planning bindings

Planning Consumption has no fake terminal event.

Roadmap creation binding conceptually includes:

```yaml
kind: roadmap_creation_v1
roadmap_request_identity_digest: ...
created_roadmap_id: r_...
created_phase_ids: [...]
created_relation_ids: [...]
registration_commit_sha: ...
semantic_projection_digest: ...
```

Phase-entry binding conceptually includes:

```yaml
kind: phase_entry_v1
phase_entry_design_identity_digest: ...
phase_id: p_...
created_work_ids: [...]
integration_id: w_...
confirmation_id: w_... | null
registration_commit_sha: ...
semantic_projection_digest: ...
```

Exact P2 schemas follow R8/R9 adapter contracts. Their uniqueness remains primarily `receipt_id -> 0 or 1`; created entity IDs/registration commit identity are also cross-validated against the persisted semantic projection rather than used as a generic global uniqueness rule.

## 9. Policy bindings

Project/Global Policy Consumption similarly binds the reviewed before/after policy version and exact persisted policy commit/projection without inventing lifecycle events. Exact schema is deferred to P6/P7; P1 common cardinality remains one Receipt to at most one Consumption.

## 10. Validation timing

Consumption validation runs at three points:

```text
before stage record:
  Receipt current + no conflicting canonical Consumption

after stage apply / before terminal commit:
  exact Consumption file exists and indexes are valid

after local terminal commit / before push:
  complete commit-delta projection proof confirms only expected transition/metadata effects
```

On resume, the same checks are repeated from canonical files and mutation intent rather than trusting an in-memory success flag.

## 11. No lifecycle authority in Consumption

`state.py` and `ProjectView` do not derive lifecycle from Consumption. If event E1 exists and Consumption is missing because of an interrupted stage, current lifecycle may temporarily read completed locally, but the pending Mutation is authoritative recovery evidence and no other conflicting writer can enter while the operation holds/reacquires the lock without pending-mutation reconciliation. Resume completes the paired Consumption before terminal Git publication/final completion.

A clone-visible Review-v1 terminal state is valid only once the terminal commit contains the complete expected transition+Consumption projection.

## 12. Architecture blocker / HUMAN

Architecture blocker: `None`.

HUMAN decision: `None`.

Existing Mutation stage recovery supplies physical replay safety; the new `ReviewStore` supplies the missing logical cardinality/identity safety.