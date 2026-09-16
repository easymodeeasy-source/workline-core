# Review System P1 — R4 Consumption Logical Uniqueness Contract Freeze

Status: CONTRACT FROZEN / ROUND 3 REPAIRED / IMPLEMENTATION NOT STARTED

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

### 4.1 `work-terminal-activation-digest-v1`

The activation prefix digest is **not** a hash of raw physical `events.jsonl` bytes. Valid historical Projects may contain CRLF and blank physical lines, and ordinary event-log rewriting may normalize representation without changing historical Event meaning.

The frozen digest algorithm is:

```text
1. Read the pre-activation event log through the canonical Event parser.
2. Ignore blank physical lines exactly as the live Event reader does.
3. Parse and validate every nonblank JSON object as one complete Event record.
4. `legacy_event_count` = number of parsed Event records before activation.
5. For the first N parsed records, produce canonical activation-digest JSON bytes:
   - preserve every schema-allowed field, including non-lifecycle metadata;
   - object keys sorted lexicographically by Unicode code point;
   - JSON separators exactly `,` and `:` with no insignificant whitespace;
   - strings encoded as UTF-8 JSON with `ensure_ascii=false` semantics;
   - no NaN/Infinity/non-JSON numeric values;
   - append exactly one LF byte after each canonical JSON object.
6. Concatenate those N canonical record lines in event order.
7. `legacy_event_prefix_sha256` = SHA-256 of the concatenated canonical bytes.
```

The digest therefore binds **Event record identity/order/content**, not incidental CRLF/blank-line representation.

If the Event schema later adds an allowed metadata field, the activation digest serializer preserves that field. Unknown/unparseable fields under the active schema are not silently dropped; validation fails closed.

A changed, reordered, deleted, inserted or metadata-mutated pre-activation Event changes the canonical prefix digest. Merely rewriting CRLF to LF or removing blank physical lines does not.

### 4.2 Classification after clone

```text
activation record present
+ first N parsed canonical Event records reproduce the stored activation digest
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

## 8. Round-3 repair disposition

P1R2-NF-01 is closed by freezing `work-terminal-activation-digest-v1` as a canonical parsed-Event serialization rather than raw event-log bytes. This preserves exact classification across valid CRLF/blank-line legacy representations while still detecting semantic historical mutation.

Architecture blocker: `None`.

HUMAN decision: `None`.
