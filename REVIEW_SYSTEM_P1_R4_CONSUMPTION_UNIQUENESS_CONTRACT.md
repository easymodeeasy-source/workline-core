# Review System P1 — R4 Consumption Logical Uniqueness Contract Freeze

Status: CONTRACT FROZEN / REPAIRED AFTER EXTERNAL REVIEW / IMPLEMENTATION NOT STARTED

This checkpoint freezes the common Consumption identity/cardinality contract under Candidate 7. It is non-normative until implemented and routed through canonical authority.

## 1. Live facts inspected

The live Mutation Controller already provides recovery-safe ID reservation, exact replay classification, one Project execution lock, and durable multi-effect stages.

These mechanisms can make a terminal event + Consumption pair replay-safe, but path uniqueness alone does not enforce Candidate 7's logical cardinality or Work-terminal totality. ReviewStore-level validation is required.

## 2. Common Consumption record

Every Consumption is immutable and stored at:

```text
.workline/review/consumptions/<consumption_id>.yaml
```

Common core:

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

The referenced Receipt must exist, be valid, bind the same identities, and be currently consumable when the owning operation records the Consumption stage.

## 3. Stable physical identity

The consuming operation reserves Consumption before recording its effect:

```text
review-consumption:<receipt_id>
```

Same exact canonical bytes at the reserved immutable path are idempotent MATCHING. Different bytes at the same path are reconcile required under R1's immutable create-only writer.

## 4. Global logical uniqueness indexes

`ReviewStore` builds canonical scan/index views:

```text
by_receipt[receipt_id]
by_terminal_event[event_id]
by_kind_persisted_result[key]
```

Any uniqueness-constrained index with conflicting records fails closed. No mutable counter/index file is introduced.

## 5. Common cardinality

Frozen common invariant:

```text
one Authorization Receipt -> at most one valid Consumption
```

Before creating C1:

```text
none for R1 -> create
exact semantic existing C1 -> idempotent reuse
conflicting Consumption for R1 -> reconcile
```

A superseded Receipt cannot receive a new Consumption.

## 6. Work terminal binding

Work terminal `kind_binding` contains at least:

```yaml
kind: work_terminal_v1
authorized_result_commit_sha: <K1>
terminal_event_id: evt_...
terminal_event_type: work_completed
work_id: w_...
```

The non-circular binding remains:

```text
Receipt R1 authorizes Candidate/K1 eligibility
terminal event E1 consumes R1
Consumption C1 binds R1 + exact proven K1 + E1 + operation mutation
```

Receipt/Consumption bytes do not self-reference the commit containing themselves.

P1 uniqueness foundation:

```text
receipt_id        -> 0 or 1 Consumption
terminal_event_id -> 0 or 1 Consumption
```

## 7. P3 Work-terminal totality

Before review-v1 START terminal gating is activated, the stronger invariant is mandatory:

```text
one review-v1 terminal event -> exactly one matching valid Consumption
```

This requires a durable operation-contract identity that makes it mechanically decidable after clone whether a terminal event belongs to `review-v1`. Absence/presence of arbitrary Review files alone is not this marker.

Allowed transient recovery state:

```text
review-v1 terminal event exists
Consumption missing
matching pending mutation proves event + Consumption were one durably recorded terminal stage
-> recoverable transient; resume must complete C1 before terminal publication/final completion
```

Invalid state:

```text
review-v1 terminal event exists
Consumption missing
no matching pending recovery intent
-> fail closed / reconcile required
```

If effect ordering/corruption permits Consumption without its exact required transition, that state is likewise invalid unless a matching pending stage proves the transition is the remaining unapplied effect.

This totality check is a Review/operation consistency invariant only. `state.py` continues deriving lifecycle from canonical events, not Consumption metadata.

## 8. Terminal event reservation/order

START reserves terminal event ID and Consumption ID before the terminal stage.

Deterministic stage order:

```text
1. AuthorizedTransitionProjection effects
2. OperationMetadataProjection Consumption immutable create
```

All effects are durable intent before the first apply. Crash after E1 but before C1 is recovered by classification/replay, not by physical atomicity assumptions.

No terminal commit/push may proceed until the stage rereads complete and uniqueness/totality prerequisites applicable at that point pass.

## 9. Planning and Policy bindings

Planning kinds have no fake terminal event. Their Consumption binds exact semantic projection/result identity and registration commit.

Policy kinds similarly bind reviewed before/after policy semantics and exact persisted proof. Exact schemas remain P6/P7 work; common one-Receipt-at-most-one-Consumption applies.

## 10. Validation timing

Validation runs:

```text
before stage record:
  current Receipt + no conflicting canonical Consumption

after stage apply / before terminal commit:
  exact Consumption exists + indexes valid

after local terminal commit / before push:
  exact persisted transition/metadata proof

after clone/full validation for review-v1 terminal state:
  totality check using durable operation-contract identity and pending-recovery exception only
```

Resume repeats checks from canonical files and mutation intent.

## 11. External-review repair disposition

Accepted and repaired here:

- 0-or-1 uniqueness is explicitly only the P1 common foundation;
- P3 activation requires `review-v1 terminal event -> exactly one Consumption`;
- only a matching pending terminal stage permits temporary one-sided local state;
- no second lifecycle authority is introduced.

Architecture blocker: `None`.

HUMAN decision: `None`.
