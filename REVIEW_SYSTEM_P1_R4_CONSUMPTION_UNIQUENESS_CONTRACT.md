# Review System P1 — R4 Consumption Logical Uniqueness Contract Freeze

Status: CONTRACT FROZEN / ROUND 2 REPAIRED / IMPLEMENTATION NOT STARTED

This checkpoint freezes the common Consumption identity/cardinality contract under Candidate 7. It is non-normative until implemented and routed through canonical authority.

## 1. Common Consumption invariant

P1 common foundation:

```text
one Authorization Receipt -> at most one valid Consumption
one terminal_event_id      -> at most one valid Consumption
```

`ReviewStore` builds canonical immutable indexes by Receipt, terminal event and kind-specific persisted result. Exact replay is idempotent; conflicting tuples reconcile.

## 2. Work terminal binding

Work terminal Consumption binds at least:

```text
receipt_id
review_run_id
review_generation
authorized_candidate_hash
authorized_result_commit_sha = K1
terminal_event_id = E1
terminal_event_type = work_completed
work_id
operation_mutation_id
operation_identity
```

Receipt authorizes exact Candidate/K1 eligibility; E1 consumes Receipt; C1 binds R1 + proven K1 + E1 + operation.

## 3. P3 totality

Before review-v1 START gating activates:

```text
one review-v1 work_completed event -> exactly one matching valid Consumption
```

This totality is Review/operation consistency only. `state.py` still derives lifecycle from events and ignores Review metadata.

Allowed temporary one-sided state only when a matching pending terminal Mutation proves both event+Consumption were one durable stage and the missing effect remains recoverable.

Without matching pending intent, E1-only or C1-only review-v1 state is invalid/reconcile.

## 4. Durable legacy/review-v1 classification

P3 creates and proves one immutable activation record before the first review-v1 Work terminalization:

```text
.workline/review/activation/work-terminal-v1.yaml
```

It binds:

```text
operation_contract = review-v1
legacy_event_count = N
legacy_event_prefix_sha256
activation_base_head
```

`legacy_event_prefix_sha256` is the SHA-256 of the exact canonical pre-activation event-log prefix represented by the first N events under the versioned activation digest contract.

Classification after clone:

```text
activation record present + prefix count/digest valid
-> first N events are positively classified pre-activation legacy
-> every later work_completed must carry explicit review-v1 operation-contract metadata

post-activation work_completed missing marker
unknown marker
contradictory marker/activation prefix
-> reconcile_required; never legacy fallback
```

Absence of arbitrary Review files is never legacy proof. Absence of the activation record means review-v1 Work terminalization has not been positively activated; an explicit review-v1 event without matching activation is contradictory and invalid.

## 5. Event metadata carrier

P3 extends canonical event record parsing/rendering so terminal events may carry versioned non-lifecycle metadata. For review-v1 `work_completed`, minimum metadata is:

```text
operation_contract: review-v1
review_receipt_id
review_run_id
review_generation
```

Event identity/type/entity/at remain lifecycle inputs. `ProjectView/state.py` ignores the added operation-contract metadata. Review consistency validation reads it only to classify totality and bind exact Consumption.

Unknown/contradictory operation-contract metadata fails closed; it is not stripped into legacy semantics.

## 6. Terminal stage ordering

START reserves E1 and C1 before the terminal stage. Stage effect order:

```text
1. AuthorizedTransitionProjection events
2. OperationMetadataProjection Consumption immutable create
```

All effects are durable intent before apply. No terminal commit/push proceeds until the stage rereads complete and uniqueness/totality prerequisites applicable to that point pass.

## 7. Planning/Policy kinds

Planning and Policy Consumption never invent fake Work terminal events. Their uniqueness remains Receipt-based plus kind-specific semantic persisted-result binding.

## 8. Round-2 repair disposition

P1R-03 is closed by freezing both:

- durable P3 activation boundary anchored to the exact pre-activation event prefix;
- explicit review-v1 terminal Event metadata carrier that state derivation ignores.

This distinguishes positive legacy history from post-activation malformed/unknown terminal events after clone.

Architecture blocker: `None`.

HUMAN decision: `None`.
