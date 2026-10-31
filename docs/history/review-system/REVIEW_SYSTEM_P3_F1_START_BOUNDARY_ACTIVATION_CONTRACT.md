# Review System P3 — F1 Review-v1 START Boundary and Activation Contract Freeze

Status: CONTRACT FROZEN / IMPLEMENTATION NOT STARTED / LIVE BASELINE `68085d6570b2d31d9ee5fac52c2b1a5579c234e2`

P3 implementation remains NOT STARTED. Nothing in this document is activated by writing it.

## 1. Status, baseline and authority

### 1.1 Baseline

This contract is frozen against live `main` at `68085d6570b2d31d9ee5fac52c2b1a5579c234e2`, with P1 Review Core,
P2 Planning Review, BL-056 and BL-057 landed. Every "measured at baseline" note below refers to that commit. If a
later implementation runs against a different baseline, the live facts must be re-verified before this contract is
applied; the decisions themselves are not rebased onto another baseline silently.

### 1.2 Authority relationship

Runtime authority is, and remains:

```text
1. registry.md
2. registry-routed canonical Skills
3. live implementation / tests
```

This document is a **frozen implementation contract**. It is not runtime authority and changes no behaviour until
the corresponding implementation lands and the canonical authority statements of §13 are activated.

The P1 and P2 freeze documents remain historical frozen contracts and are **not edited**. Where this contract
controls a P3 question differently from an earlier frozen text, it says so explicitly as a **forward amendment**
(§10.3, §11.3, §14), and the earlier document keeps its own text unchanged as the historical record.

Forward amendments made here, and only these:

```text
P1 R4 §2     amended for P3 Work-terminal Consumption: artifact_kind (§11.3)

P1 R4 §4.2   amended for P3 post-activation classification (§10.3): because activation is
             Project capability × per-invocation selection, a post-activation work_completed
             with no operation-contract marker is a legacy completion; a review-v1 marker
             selects review-v1; unknown or contradictory markers still fail closed.

P1 R5 §8     clarified for P3: an empty-artifact Candidate has no physical K1 commit (§11.3)
```

### 1.3 Scope of the freeze

F1 freezes the boundary that decides **which START contract is running** and **whether Work-terminal Review
applies**. It freezes no commit topology, no proof, and no Review content.

---

## 2. F1 scope and non-scope

### 2.1 In scope — frozen here

```text
A  caller opt-in to review-v1 START                                     §3
B  durable mutation identity for legacy vs review-v1 START              §4
C  resume / refusal rules on invocation-vs-pending mismatch             §5
D  Work-terminal Review activation semantics                            §6
E  the activation record and its producer authority                     §7, §8
F  work-terminal-activation-digest-v1                                   §9
G  activation totality, absence semantics, upgrade compatibility        §10
H  result-less Work, insofar as activation / Candidate applicability
   must already decide it                                               §11
I  ordered implementation prerequisites for activation                   §12
J  canonical authority activation plan                                   §13
```

### 2.2 Out of scope — deferred, named in §15

F1 does not freeze the Work Candidate schema, the Review-validity closure, K1/K2 proof checkpoints, the split
publication validator, the Consumption terminal stage mechanics, Class A/B/C, stale-generation handling, isolated
verification, or the full interruption matrix. Where F1 creates a dependency on one of those, it names the
dependency without solving it.

### 2.3 Live START behaviour F1 does not redesign

Measured at baseline: START already makes a result commit `<Work>:results:<n>`, then the terminal lifecycle
(`work_target_removed`, `work_completed`), then a finalization commit `<Work>:finalize:<n>`; both Git stages are
`git_commit + git_push` recorded as one stage and applied in one uninterrupted pass; the result commit can be pushed
while the Work is still `in_progress`; an interruption after the result push but before the terminal events re-runs
the executor; and a Work with no owned result paths legitimately produces no result commit at all.

F1 changes none of this. It decides only which contract is active.

---

## 3. Review-v1 START caller contract (F1-D1)

### 3.1 Frozen selection

```text
legacy      start(store, work_id, mode, executor)
review-v1   start(store, work_id, mode, executor, *, review=<Review selector>)
```

1. **Explicit caller opt-in, keyword-only, defaulting to absent.** Every existing call site is source-compatible and
   behaves exactly as it does today. There is no second entry point: START remains one operation with one owner.
2. **The selector carries a versioned Review contract identity, never a boolean.** The frozen contract string is:

```text
review contract identity = "review-v1-work-v1"
```

3. **The selector carries the reviewer identity and version as persistable single-line text**, validated for
   canonical representability at the same moment as the contract string, so a value that could not later be
   recorded is refused before anything is written. What the reviewer is *for* is F2.
4. **Validation happens before the Project execution lock and before any Project state is read.** An invalid
   selector — wrong type, unsupported contract string, non-representable identity text — raises
   `ValidationError` with the existing code `review_contract_invalid`. No lock is taken, no mutation record exists,
   no Review record is read, nothing is written.
5. **An unsupported contract version fails closed.** Only the exact frozen string is accepted by a given build.
   Any other value — newer, older, malformed, or not a string — is `review_contract_invalid`. There is no forward
   tolerance, no downgrade, and no "best effort" acceptance.
6. **The START contract mode is known before execution, necessarily**, because the selector is an argument. The
   mode is fixed at the API boundary, while the executor runs later, under the lock, inside the Work cycle.
7. **The contract mode is never inferred.** Not from Project state, Review files, Work kind, Work content, Work
   history, branch state, or the executor's outcome.
8. **The Project execution lock holder description names only the static contract marker**, never a caller value,
   so an unrepresentable caller value can never strand the lock.
9. **Review remains a subordinate authorization gate.** Selecting review-v1 does not make Review the operation
   owner. START owns the operation, the mutation, the lock and Git finalization, exactly as it does today.

### 3.2 Not frozen

The Python spelling of the selector type and its field names is implementation detail and is deliberately left
open. Only the semantics above, and the contract string, are frozen.

---

## 4. Durable START contract identity (F1-D2)

### 4.1 Frozen durable invocation

START's durable mutation invocation gains exactly two keys on the review-v1 path, and nothing on the legacy path:

```text
legacy      {"operation": "start", "work_id": <W>, "mode": <M>}

review-v1   {"operation": "start", "work_id": <W>, "mode": <M>,
             "review_contract":      "review-v1-work-v1",
             "publication_contract": "review-v1-split-v1"}
```

### 4.2 Frozen rules

* **Identity versus metadata.** `operation`, `work_id` and `mode` remain the **slot identity** used for
  same-request matching. The two markers are **compatibility metadata and are not part of the slot identity.**
  Making them identity would let a legacy and a review-v1 START on the same Work and mode resolve to different
  slots and both open — two concurrent mutations on one Work.
* **Written at mutation open**, in the intent's first durable write, before any effect and before any Git stage of
  that mutation. This satisfies the R5 implementation requirement that the publication contract be durable before
  the first Git stage.
* **Both markers are written together, in F1, and the publication marker is not deferred to F3.** R5 §12.3.1
  case B makes a mutation that carries Review-v1 durable metadata but lacks its publication discriminator
  contradictory and fail-closed. Freezing only the review contract would put every review-v1 START mutation into
  case B from its first durable write, unable to publish anything ever. F3 owns the *validator* that gives
  `review-v1-split-v1` behaviour; F1 owns the fact that the marker is present and what it names. Until F3 lands, a
  review-v1 START mutation is correctly unable to record a push. That is the fail-closed state, not a defect.
* **Contract selection reads durable operation metadata and nothing else.** It is frozen that the contract is
  never inferred from:

```text
stage shape
the presence or absence of a git_commit + git_push pair
the presence or absence of Review files
Candidate or activation file existence
any content pattern
branch state, HEAD position or history shape
```

* **Activation identity is not copied into the invocation.** The invocation binds the *operation's* contract.
  Activation is Project state and is verified against the Project at entry (§6.4). A copy inside the invocation
  would be a second source of truth that would have to be re-verified anyway.
* **A pending mutation's contract never changes because a retry caller passed different arguments.** The record's
  markers decide what that mutation is; the retry's arguments decide only whether the retry may continue it (§5).

---

## 5. Legacy / review-v1 resume mismatch contract (F1-D3)

### 5.1 Where it is evaluated

At START's entry, from the **durable invocation alone**, after the live same-request check and **before** the
mutation is opened. The pending record is read and never written.

### 5.2 Frozen matrix

| # | pending record | retry invocation | outcome |
| --- | --- | --- | --- |
| 1 | legacy (no marker key) | legacy | **resume**, exactly as today, unchanged in every respect |
| 2 | legacy (no marker key) | review-v1 | **refuse** |
| 3 | review-v1 (frozen pair) | review-v1, same contract | **resume** |
| 4 | review-v1 (frozen pair) | legacy | **refuse** |
| 5 | review-v1 (frozen pair) | review-v1, **different** `review_contract` value | **refuse** — a different version is not this invocation's contract |
| 6 | partial, unknown, or extra marker keys, on either side | either | **refuse** — never read as legacy, never read as review-v1 |

### 5.3 Frozen refusal semantics

```text
category            ReconcileRequired      code   reconcile_required
                                           reason review_marker_mismatch
owner of refusal    START, the operation owner, at its entry
mutation record     left exactly as it is: no upgrade, no downgrade,
                    no field added, changed or removed
effects             none recorded, none applied
executor            never run
Review namespace    never read — the decision uses the durable invocation only
Git                 no stage, no commit, no push, no network contact
```

The existing semantic category is reused rather than a new code introduced: the pending record exists and is
well-formed, and what failed is an expectation match against durable recovery state, which is exactly what
`ReconcileRequired` means. The identical situation in review-v1 planning already raises precisely this, with
precisely this reason.

### 5.4 Reviewer configuration is not bound here

Reviewer identity and version are **not** part of the mutation invocation. They are bound where the Review gate
binds them — in the accepted task record — and a mismatch there is the gate's refusal, not a mutation contract
mismatch. Binding them into the invocation would turn a harmless reviewer-version change into an unrecoverable
mutation mismatch. Deferred to F2.

---

## 6. Work-terminal activation semantics (F1-D4)

### 6.1 Frozen meaning

```text
Work-terminal Review activation is a Project-scoped capability and classification boundary.

It states:      from activation_base_head, with the first legacy_event_count canonical Event
                records behind it fixed by legacy_event_prefix_sha256, this Project MAY
                terminalize Works under the review-v1 operation contract.

It does NOT state:
                that any particular Work must be reviewed;
                that Review owns, derives or gates any lifecycle state;
                that any existing Work, event or record changes meaning.
```

The model is, exactly:

```text
Project capability (the activation record)  ×  per-invocation selection (the durable marker)
```

### 6.2 Frozen scope answers

```text
per Project           YES — the record is Project-scoped and names no Work
per Work              NO
per Work kind         NO   (result-ness does not follow from Work kind — §11)
per START invocation  YES, for whether a given completion is review-v1;
                      decided by the durable marker, never by the activation record
canonical authority   YES — a canonical, immutably created, committed, clone-safe Review record
```

### 6.3 No second lifecycle truth

`state.py` remains the sole lifecycle authority, deriving Work, Phase and Roadmap state from canonical entities,
relations and lifecycle events. The activation record is never read by `ProjectView`, by state derivation, by
structural validation, by startability or by progression. Review authorizes; it never progresses.

It is frozen that the existing authority pin — that the lifecycle-deriving module contains no Review dependency —
must continue to hold **after** the Event metadata carrier of §12.1 lands.

### 6.4 Frozen entry behaviour for a review-v1 START

Activation is verified **under the Project execution lock, before the mutation is opened** — the position the push
destination check already occupies: Project state is read after the lock, and the refusal must happen before any
intent record exists.

```text
activation record absent           STOP, code review_not_activated.
                                   No mutation, no write, nothing read further.
activation record malformed        the reader's ValidationError; fail closed
operation_contract unknown         the reader's ValidationError; fail closed
activation prefix unprovable       STOP; never a silent legacy fallback
```

`review_not_activated` is a new code, and the only new code this contract introduces. No existing code states "this
Project has not activated review-v1 Work terminalization": the contract-argument refusal is about the caller's
argument, the namespace refusal is about record health, and the Git-version refusal is about the toolchain. It must
be registered in the error and reason catalogue alongside the review-v1 planning codes.

---

## 7. Activation record (F1-D6)

### 7.1 Reuse — no second record

F1 introduces **no new activation record type**. The existing frozen P1 `WorkTerminalActivation` record is
sufficient and is reused unchanged:

```text
path      .workline/review/activation/work-terminal-v1.yaml
schema    review-work-terminal-activation          version 1
fields    operation_contract          = "review-v1"      (the only accepted value)
          legacy_event_count          = N                (integer >= 0)
          legacy_event_prefix_sha256  = 64 hex           (work-terminal-activation-digest-v1, §9)
          activation_base_head        = 40 hex           (full commit id)
writer    immutable create only
```

No field is added to this record by F1. The one frozen-record repair F1 requires is on the Consumption record
(§11.3), not here.

### 7.2 Frozen uniqueness, immutability and replay

```text
logical uniqueness     one activation per Project
physical uniqueness    one canonical path; the activation directory may hold that one plain file and
                       nothing else — no other entry, no nested directory, no symlink, junction or
                       other reparse point anywhere in it
                       => logical and physical uniqueness coincide; there is no separate logical key

immutability           immutable create-only. The generic update primitive is mechanically kept away
                       from canonical Review paths; the create carries no base.

replay, identical bytes        applied / matching
replay, different bytes        applied / mismatch -> reconcile required
replay, target absent          unapplied -> created
a directory or an indirection
anywhere on the path           mismatch -> reconcile required; never followed

replaceable            NO
deletable by Workline  NO
dangling record        NOT REACHABLE — the record names no Work, so an activation that references an
                       unknown Work cannot arise under this schema
```

### 7.3 Frozen version behaviour

A later Work-terminal contract is a **different record at a different path**, introduced by a deliberate change to
the Review namespace validator. Under this contract, any entry in the activation directory other than the one
frozen filename is a namespace violation. There is no in-place upgrade and no version field to bump.

---

## 8. Activation producer authority (F1-D5)

### 8.1 Frozen producer

```text
authoritative producer   a dedicated Project-level activation maintenance operation:
                         its own top-level operation owner, its own mutation,
                         subject to rules/human-confirmation,
                         following the ownership pattern of the push destination pin

NOT the producer
  START                  activation is canonical INPUT to START. START must never
                         retroactively invent the authority that governs it.
  Review                 Review never opens a mutation, never holds the Project lock
                         and never finalizes Git.
  Roadmap / Phase CREATE they own planning, not the Project-wide terminal contract,
                         and standalone Works have no Roadmap at all.
```

### 8.2 Enforced mechanically

Writing a canonical Review record is owner-agnostic at baseline. It is frozen that the Mutation Controller gains a
**closed owner allowlist for the activation record path**, in the same shape as the existing push-pin guard: any
owner other than the activation maintenance operation that records that create is refused at effect validation,
before the effect is written into the record. This is a mechanical guard, not Skill prose.

### 8.3 Frozen production preconditions

All of the following, under the Project execution lock:

```text
- no pending mutation of any owner exists
    (the event-log prefix is therefore stable, and no pending START is surprised by a new contract)
- no pre-existing uncommitted change overlaps the activation path
- the existing Review namespace reads canonically
- HEAD is on a branch, and activation_base_head is that HEAD
- legacy_event_count and the prefix digest are computed from the committed event log at that HEAD
- the record is committed in the activation operation's own mutation, and pushed where a
  destination is pinned
- human confirmation is obtained: this is a Project-specific rule change
- both ordered prerequisites of §12 are satisfied
```

### 8.4 Frozen prohibitions

```text
no implicit activation during START or any other domain operation
no retroactive inference of activation from Review files, history or Work state
no bulk migration, and none permitted
activation is produced once per Project and never replaced in place
```

---

## 9. `work-terminal-activation-digest-v1` (F1-D7)

### 9.1 Frozen algorithm

The algorithm is the one frozen by P1 R4 §4.1, confirmed implementable at this baseline:

```text
1. Read the pre-activation event log through the canonical Event reader.
2. Ignore blank physical lines exactly as the live Event reader does.
3. Parse and validate every nonblank line as one complete Event record.
4. legacy_event_count = N = the number of parsed Event records before activation.
5. For each of the first N parsed records, produce canonical activation-digest JSON bytes:
     - preserve every schema-allowed field, including non-lifecycle metadata;
     - object keys sorted lexicographically by Unicode code point;
     - separators exactly "," and ":", with no insignificant whitespace;
     - UTF-8, with ensure_ascii = false semantics;
     - no NaN / Infinity / non-JSON numeric values;
     - exactly one LF byte after each canonical JSON object.
6. Concatenate those N canonical record lines in event order.
7. legacy_event_prefix_sha256 = SHA-256 of the concatenated canonical bytes, lowercase hex.
```

### 9.2 Why this is deliberately not the Review canonical-record form

This is an intentional, frozen distinction, not an ad-hoc serializer:

```text
the Review canonical-record form   renders Review records, and every Review digest is taken
                                   over those bytes
work-terminal-activation-digest-v1 hashes the canonical parsed Event prefix of the event log,
                                   which is not a Review record and is not rendered by the
                                   Review writer
```

The material is the event log. Hashing its raw bytes would bind incidental representation: a valid historical
Project may hold CRLF line ends and blank physical lines, and ordinary event-log handling may normalize
representation without changing any Event's meaning. Hashing canonical *parsed* Events binds what actually matters:

```text
binds        Event record identity, order and content, for the first N records
ignores      CRLF versus LF
ignores      blank physical lines, exactly as the Event reader ignores them
preserves    every schema-allowed field, including non-lifecycle metadata
changes on   a changed, reordered, deleted, inserted or metadata-mutated pre-activation Event
```

The final SHA-256 step may reuse the Review digest helper; the canonicalization above is not replaced by the
Review record renderer.

### 9.3 Frozen inclusion set

```text
included        the first N canonical parsed Event records, in event order

not included    the activation schema and version   — sibling fields of the record, covered by the
                                                      record's own canonical bytes
                any Work ID                         — the record is Project-scoped and names no Work
                the Review contract version         — likewise a sibling field
                activation parameters               — likewise sibling fields
                raw event-log bytes                 — deliberately excluded (§9.2)
```

### 9.4 Frozen digest identity

The digest identity is the pair:

```text
(activation digest algorithm version, Event schema version)
```

"Every schema-allowed field" means allowed at the Event schema version in force. At baseline that is exactly the
four lifecycle fields. When the §12.1 carrier lands the allowed set grows; binding the Event schema version into
the digest identity makes that a digest-identity change rather than a silent re-interpretation of a stored digest.
The stored prefix is pre-activation and therefore never carries review-v1 metadata.

### 9.5 Frozen properties

Deterministic; clone-safe, from committed material only; canonical; derived from no runtime state; stable across
CRLF-to-LF and blank-line normalization; and changing whenever pre-activation Event history is semantically
mutated.

---

## 10. Activation totality and upgrade compatibility (F1-D8, F1-D9)

### 10.1 Frozen absence and contradiction semantics

```text
no activation record              review-v1 Work terminalization is NOT activated.
                                  A valid, ordinary state. Legacy START is unaffected and unchanged.
                                  A review-v1 START refuses at entry (review_not_activated).

activation present and the
prefix digest reproduces          events 0 .. N-1 are positively classified pre-activation legacy.
                                  The Project may terminalize under review-v1.

activation present, prefix
digest does not reproduce         fail closed. Never legacy fallback. Never partial activation.
record malformed
operation_contract unknown
unsupported activation version
```

Absence of arbitrary Review files is never legacy proof. No ambiguous state ever silently selects the weaker
contract.

### 10.2 Frozen totality scope and statement

```text
scope       work_completed events at parsed index >= legacy_event_count.
            Terminal events only: work_started, work_target_added, work_resumed and
            work_target_removed are never in scope, at any index.

below N     never review-v1; never requires a Consumption; never re-classified.

statement   a work_completed in scope that carries the review-v1 operation-contract marker
            has exactly one valid Consumption binding its terminal_event_id.

allowance   a temporary one-sided state is valid only while a matching pending terminal
            Mutation stage proves that the event and the Consumption were one durable stage
            and that the missing effect remains recoverable. Without that matching pending
            intent, an event-only or Consumption-only review-v1 state is invalid and
            reconcile required.
```

### 10.3 Frozen classification of a post-activation `work_completed`

```text
carries the review-v1 operation-contract marker      review-v1; the totality statement applies
carries no marker                                    legacy; no Consumption is required or expected
carries an unknown marker                            reconcile required
carries a marker contradicting the activation
  record, the Run or the Receipt it names            reconcile required
```

**Forward amendment to P1 R4 §4.2.** P1 R4 §4.2 freezes that, once activation is present and its prefix
reproduces, *every* later `work_completed` must carry explicit review-v1 operation-contract metadata, and that a
post-activation event missing the marker is `reconcile_required` and never a legacy fallback. **That
classification rule is superseded for P3 by the table above.**

The reason is F1's selection model (F1-D1, F1-D4, F1-D9): activation is a Project **capability**, not a Project-wide
mandate, and review-v1 is chosen **per invocation**. A legacy START therefore remains available and unchanged in an
activated Project (§16 invariant 1), and it necessarily produces a post-activation `work_completed` with no marker.
Under the unamended R4 §4.2 rule that ordinary, correct completion would be invalid — which is precisely the
position-only outcome this section rejects below, and which would break the legacy guarantee this contract freezes.

The amendment is narrow, and it is the **only** relaxation:

```text
amended       a post-activation work_completed with NO operation-contract marker is a legacy
              completion, and requires no Consumption.
              Marker absence is legacy only when the event otherwise belongs to the valid
              post-activation history of an activated Project: the activation record must be
              present, well-formed, of a supported version, and its prefix digest must reproduce.

inherited     R4 §4.2's other statements, unchanged:
                absence of arbitrary Review files is never legacy proof;
                an explicit review-v1 event without matching activation is contradictory and invalid.
              R4 §3 totality, for events positively classified review-v1 (§10.2).
              R4 §5 Event metadata requirements (§12.1).

NOT amended   unknown, malformed or contradictory Review metadata never falls back to legacy.
              Only true absence of the marker means legacy. There is no general
              "metadata problem -> legacy" rule, and none may be introduced.
              Activation-prefix and activation-record failures stay fail-closed (§10.1):
              a malformed record, an unsupported version, an unknown operation_contract or a
              prefix digest that does not reproduce refuse the Project's review-v1 use outright,
              and no event is classified legacy on their account.
```

The discriminator is the marker on the event. Measured at baseline, that marker cannot be carried end-to-end
today, which is why §12.1 makes the carrier an ordered prerequisite of activation and why activation is refused
until it exists. There is no half-activated state.

Two alternatives were evaluated and are closed:

```text
position-only classification   ("every work_completed at index >= N is review-v1")
                               rejected: an activated Project could then never run a legacy START,
                               breaking the legacy guarantee of §16 invariant 1 and trapping any
                               START pending at activation time.

Consumption-anchored           ("review-v1 iff a Consumption binds it")
classification                 rejected: makes the totality statement vacuous and loses exactly the
                               event-only detection the totality rule exists for.
```

### 10.4 Frozen upgrade compatibility — no migration

| existing state at P3 introduction | frozen behaviour |
| --- | --- |
| unstarted Works | legacy by default. Nothing is written to them. They may later be started review-v1, because activation is Project-scoped and selection is per invocation: there is no per-Work activation to backfill. |
| in-progress Works with no pending START mutation | may be started review-v1. Their already-written opening events are out of totality scope (§10.2), so they need no marker and are never reclassified. |
| in-progress Works with a pending legacy START mutation | that mutation stays legacy for its whole life (§5 case 2). Once it is finished or abandoned, a later invocation may be review-v1. |
| pending legacy START mutations | **never converted.** This is why the activation operation requires that no pending mutation exists (§8.3): a pending START is never surprised by a new semantic contract, and activation never reinterprets an already-open mutation. |
| completed Works | irrelevant. Below N they are pre-activation legacy by the prefix digest; above N they carry no marker and are legacy by classification. None is re-opened, re-validated or migrated. |
| bulk migration | **NONE REQUIRED, and none permitted.** No existing record is rewritten, no event is amended, no Work file is touched. |

### 10.5 Activation is explicit, not policy-driven

At P3, activation is caller-driven and explicit: a human-confirmed maintenance operation produces the record. No
project-local or global policy machinery is introduced, assumed or reserved by this contract. A later phase may
make activation policy-driven; nothing frozen here depends on that or forecloses it.

---

## 11. Result-less Work and the empty-artifact Candidate (F1-D10)

### 11.1 The fact

Measured at baseline: a Work can complete correctly with no result-path change and no deleted path, and START then
makes **no result commit at all**. This is not an error state and not a degenerate case; it is ordinary and
correct — a Work whose result is semantic rather than a file change.

### 11.2 Frozen decision — Option B

```text
A review-v1 Work MAY complete with an empty-artifact Candidate and no physical K1 result commit.

No artificial empty commit is ever created merely to make a K1 exist.
Review-v1 is never refused for an otherwise correct result-less Work.
```

**The decisive reason.** Result-ness is known only after the executor returns. A contract that selected review-v1
at entry and then refused every result-less outcome would refuse *after* the executor has produced a semantically
complete Work — and the pending review-v1 mutation could not be retried as legacy (§5 case 4) while a review-v1
retry would re-run the executor, reach the same result-less outcome and refuse again. That is a reachable
retry/reconcile trap for a valid Work, created by the contract itself. Refusing at entry is impossible because
result-ness is not knowable there, and refusing by Work kind is wrong because result-ness does not follow from Work
kind.

The rejected alternatives, closed:

```text
Option A  every review-v1 Work must have a K1, synthesizing an empty commit where needed
          rejected: canonical START already states that a Work with no owned result file makes no
          result commit; nothing in the system creates an empty commit; the artifact proof over an
          empty delta is degenerate; and it manufactures Git history to satisfy a schema field.

Option C  result-less Work cannot use review-v1
          rejected: creates the reachable trap described above.
```

### 11.3 Forward amendment to P1 — Consumption `artifact_kind`

For P3 Work-terminal Consumption, this contract **supersedes the incompatible part of P1 R4 §2** and **clarifies
P1 R5 §8**. Neither historical file is edited.

```text
P1 R4 §2 says      Work terminal Consumption binds at least ... authorized_result_commit_sha = K1

F1 amends it to    artifact_kind = result_commit, with authorized_result_commit_sha = K1;
                   or artifact_kind = empty, with authorized_result_commit_sha absent,
                   for an empty-artifact Candidate.

P1 R5 §8 says      K1 contains ReviewedArtifact plus required pre-consumption Review metadata,
                   or metadata-only authorization for an empty artifact Candidate.

F1 clarifies       the empty-artifact case has NO physical K1 commit. R5 §8 permits the case but
                   does not say whether a commit exists; F1 fixes that it does not, and that no
                   commit is synthesized to stand in for one.
```

**The exact frozen repair — Consumption record, version 1.**

```text
1. schema field set
   the Consumption field set gains exactly one entry:  artifact_kind
   the record always emits the key: it is present-as-null, never omitted.
   (Implementation note, not a semantic rule: declaring the field last keeps existing positional
    constructions of non-Work Consumptions working.)

2. allowed values
   Work-kind      (terminal_event_id is not None):   "result_commit" | "empty"    — required
   any other kind (terminal_event_id is None):       null                         — required

3. binding rule, replacing the current all-or-none rule over the Work-terminal triple
   A Work-kind Consumption requires:
       terminal_event_type == "work_completed"
       target_identity is a Work id
       artifact_kind in ("result_commit", "empty")
       authorized_result_commit_sha is a full commit id   IFF artifact_kind == "result_commit"
       authorized_result_commit_sha is null               IFF artifact_kind == "empty"
   A non-Work-kind Consumption requires all four of
       terminal_event_id, terminal_event_type, authorized_result_commit_sha, artifact_kind
   to be null.
```

**What an empty-artifact Consumption binds instead of a commit.** Nothing is invented and no placeholder SHA is
ever written. The authorization binding is already complete through the record's existing fields — the Receipt, the
Review Run and generation, the authorized Candidate hash, the terminal event, the target Work and the owning
mutation. The Candidate itself carries the base lineage. F1 freezes only that `artifact_kind = empty` states the
absence explicitly rather than leaving a null to be guessed at; the empty-artifact Candidate's **content,
base-lineage fields and hash** are F2, and the **proof topology when no K1 exists** is F3.

**Classification.** This is a contract repair, not an implementation detail: it changes a frozen P1 record's exact
field set, which the record validator enforces strictly.

### 11.4 Compatibility statement — narrow and factual

Measured at this baseline: **no production Consumption version 1 is produced anywhere in live `src/`.** The only
Consumption any Project can currently hold is the version 2 Planning Consumption, which this repair does not touch.

Therefore this repair requires:

```text
no production migration
no legacy production record conversion
fixture and test updates during implementation
```

This exception is safe **only** because the version 1 Work-terminal Consumption contract has never been activated
for production Work Consumption. It is not a general licence to change record schemas without versioning; every
record that has reached production keeps its version discipline unchanged.

---

## 12. Ordered implementation prerequisites

Activation is gated. The order below is part of the activation safety contract, not implementation advice.

```text
Gate 1   Event metadata carrier
   then
Gate 2   Consumption version 1 artifact_kind repair, landed and test-pinned
   then
Gate 3   Work-terminal activation producer, and actual P3 activation

The activation producer MUST fail closed and remain unavailable until Gate 1 and Gate 2 are both
satisfied. No Project may be activated before then, and therefore no post-activation review-v1
terminal event may exist before then.
```

### 12.1 Gate 1 — Event metadata carrier

**Measured defect at baseline.** An `append_event` effect whose record carries an additional metadata key is
accepted by effect validation and physically written into the event log with the key intact; but the canonical
Event model and reader drop it, and effect classification then compares the reduced parsed record against the
recorded effect, yielding `applied_mismatch` — after which the next apply of the same mutation raises
`reconcile_required`. Activating before this is fixed would create a half-supported review-v1 event contract in
which every review-v1 terminal event poisons its own mutation.

**Frozen prerequisite capability.** Known, versioned, non-lifecycle Event metadata used by P3 must survive the
whole path without being dropped:

```text
effect record
  -> physical event log
    -> canonical Event reader
      -> Event model and its record form
        -> Mutation effect classification
```

**Frozen minimum carrier content** — inherited from P1 R4 §5, for a review-v1 `work_completed`:

```text
operation_contract = review-v1
review_receipt_id
review_run_id
review_generation
```

No additional field is frozen here; further fields belong to F3/F4.

**Frozen separation of concerns.**

```text
lifecycle fields              id, type, entity, at
                              these, and only these, are lifecycle inputs

Review consistency metadata   operation_contract, review_receipt_id, review_run_id,
                              review_generation
                              non-normative: state derivation ignores them entirely
```

It is frozen that lifecycle derivation continues to read only the lifecycle fields, that legacy lifecycle semantics
are unchanged, and that an Event carrying no metadata renders, parses, classifies and digests exactly as it does at
baseline. Unknown or contradictory operation-contract metadata fails closed wherever Review consistency reads it;
it is never stripped into legacy semantics.

This carrier is **not implemented by this contract.**

### 12.2 Gate 2 — Consumption `artifact_kind` repair

After Gate 1 is proven, the Consumption version 1 repair of §11.3 must land and be test-pinned before the
activation producer may be enabled.

This repair is **not implemented by this contract.**

### 12.3 Why the order matters

```text
Before Gate 1   review-v1 terminal event metadata is not replay- and classification-safe.
                Activation could therefore create post-activation review-v1 terminal events that
                cannot be replayed or classified, and the totality discriminator would not exist.

Before Gate 2   a result-less review-v1 Work has no complete Consumption representation.
                Activation would therefore make an ordinary, reachable START outcome impossible to
                consume correctly.

Only after both are true may the activation producer make a Project subject to the totality
contract of §10.2.
```

---

## 13. Canonical authority activation plan (F1-D11)

No canonical authority is edited by this contract. The statements below are what will need authority activation
when the corresponding implementation lands, with their owners fixed.

> Label note: the `R1`–`R6` labels below identify **`skills/review` statements of this F1 contract**. They are not
> the P1 freeze documents `R4`, `R5` and so on, which are cited in this document by their full names.

### 13.1 `skills/start` — START remains the operation owner

```text
S1  the per-invocation review-v1 opt-in and its versioned contract string; no selector means legacy
S2  the durable invocation markers START writes, and that they are written before any Git stage
S3  the resume mismatch rule: a pending START is never upgraded or downgraded; reconcile required
S4  the entry precondition: a review-v1 START requires a valid activation record, after the lock,
    before the mutation is opened, with no silent legacy fallback
S5  that the contract mode is fixed at the API boundary and never inferred from Project state,
    Review files, Work kind, Work content or the executor's outcome
S6  that a result-less Work is supported under review-v1 as an empty-artifact Candidate
S7  the unchanged-legacy statement of §16 invariant 1
```

### 13.2 `skills/review` — Review owns record meaning and progresses nothing

```text
R1  what Work-terminal activation means and does not mean, including that it is not lifecycle authority
R2  the activation record: path, uniqueness, immutability, absence semantics
R3  work-terminal-activation-digest-v1 and why its canonical form is parsed-Event JSON
R4  the totality statement and its scope (terminal events at index >= N)
R5  that an Event's operation-contract metadata is non-normative and never enters state derivation
R6  the empty-artifact Consumption binding (artifact_kind), once the §11.3 repair lands
```

### 13.3 `rules/git`

```text
G1  the new top-level operation owner for activation maintenance, in the Operation Owner section
G2  the owner allowlist for writing the activation record path (the push-pin guard's sibling)
G3  that appending an event may carry non-normative metadata, and that this changes no commit rule
```

### 13.4 `registry.md` routing

```text
no change required. Activation is an operation OWNER, not a Skill — the same status as the push
destination pin maintenance operation, which is not registry-routed either. No new Skill, no new
routing entry, and no routing change merely because activation exists.
```

### 13.5 Statements that must not move into `skills/review`

The opt-in API, the durable mutation markers, the resume refusal, the activation entry precondition, and all
commit, push and executor ordering. START remains the operation owner; Review never opens a mutation, never holds
the Project lock, never finalizes Git, and never decides that an operation should proceed.

---

## 14. F1 decision table

A compact index to the normative sections above. The prose sections are the contract; this table does not replace
them.

| Decision | Frozen rule | Primary live evidence | Amends / inherits | Downstream dependency |
| --- | --- | --- | --- | --- |
| **F1-D1** caller opt-in | explicit keyword-only selector carrying the versioned contract `review-v1-work-v1`; no boolean; validated before the lock and the executor with `review_contract_invalid`; unsupported version fails closed (§3) | START has no CLI, so the Python API is the sole caller surface; review-v1 planning's keyword-only versioned opt-in is validated before the lock | inherits the P2 opt-in pattern | F2 defines the reviewer's use; F3 the publication behaviour |
| **F1-D2** durable markers | `review_contract` + `publication_contract` = `review-v1-work-v1` / `review-v1-split-v1`, written together at mutation open, before any Git stage; compatibility metadata, **not** slot identity; contract never inferred from shape or content (§4) | START's durable invocation carries no marker today; the publication-contract selector already reads the durable invocation only | inherits P1 R5 §12.3 and R5-IMPL-2; R5 §12.3.1 case B is why the publication marker cannot wait for F3 | F3 implements the `review-v1-split-v1` validator; until then a review-v1 push cannot be recorded, which is fail-closed and correct |
| **F1-D3** resume mismatch | four-way matrix of §5.2; mismatch is `ReconcileRequired` with reason `review_marker_mismatch`; record untouched, executor never runs, Review never read | review-v1 planning already raises exactly this, with this reason, for the identical situation; `ReconcileRequired` is defined as a recovery/expectation mismatch | inherits the existing semantic category; introduces no new code | F2 adds the reviewer-identity check at the gate, not in the invocation |
| **F1-D4** activation meaning | Project capability × per-invocation selection; never lifecycle truth, never a state-derivation input, never inferred from Review files (§6) | the activation record is Project-scoped and names no Work | inherits P1 R4 §4's activation record and R5 §9; R4 §4.2's post-activation classification is forward-amended (§10.3) | F2 binds the activation record's canonical digest into Review Context / Candidate |
| **F1-D5** activation producer | a dedicated human-confirmed maintenance operation with its own owner and mutation; mechanical owner allowlist; no pending mutation at production time; never START, never Review, never Roadmap; no implicit or retroactive activation (§8) | writing a canonical Review record is owner-agnostic today; the push destination pin already uses a closed owner allowlist enforced in effect validation | inherits the push-pin ownership pattern and the Review authority boundary | authority statements G1 and G2 |
| **F1-D6** record uniqueness / immutability | one per Project at one canonical path; logical uniqueness equals physical uniqueness; immutable create-only; identical bytes replay as applied, different bytes reconcile; never replaced or deleted; dangling-Work case not reachable (§7) | the Review namespace validator already admits only that one filename, as a plain file, with no indirection anywhere | inherits P1 immutable-record semantics unchanged | a future contract is a different path and a deliberate validator change |
| **F1-D7** activation digest | P1 R4 §4.1's algorithm over canonical parsed Events, deliberately not the Review record renderer; digest identity is (algorithm version, Event schema version) (§9) | the Event reader already ignores blank lines and normalizes CRLF; the event log is appended textually, so historical lines are never re-rendered | inherits P1 R4 §4.1 unchanged; adds the digest-identity pairing | F2 binds the record's canonical digest into Review Context / Candidate |
| **F1-D8** totality / absence | absence means not activated and is valid; malformed, unknown or contradictory fails closed; scope is `work_completed` at index ≥ N; the discriminator is the event marker; **no carrier ⇒ not activatable** (§10, §12.1) | measured: a metadata-carrying event is written but classified `applied_mismatch`, and the next apply raises `reconcile_required` | **forward-amends the post-activation classification portion of P1 R4 §4.2** (§10.3); inherits R4 §3 totality for events positively classified review-v1, R4 §4.2's remaining statements, and R4 §5 Event metadata requirements | Gate 1 of §12; the marker's full field set beyond R4 §5 is F3/F4 |
| **F1-D9** upgrade compatibility | no migration and none permitted; unstarted and in-progress Works may later be started review-v1; a pending legacy START is never converted; completed Works are untouched (§10.4) | activation is Project-scoped, so there is no per-Work state to backfill | — | none |
| **F1-D10** result-less Work | Option B: an empty-artifact Candidate with no physical K1; no synthesized empty commit; review-v1 never refused for a correct result-less Work (§11) | measured: a Work with no owned result path produces no result commit; the Work-kind Consumption currently demands a commit id whenever a terminal event is present | **amends P1 R4 §2**; **clarifies P1 R5 §8**; neither file edited | F2 defines the empty-artifact Candidate content; F3 the proof topology without a K1; Gate 2 of §12 |
| **F1-D11** authority surfaces | S1–S7 to `skills/start`, R1–R6 to `skills/review`, G1–G3 to `rules/git`; **no registry routing change** (§13) | the push destination pin maintenance operation is an owner and is not registry-routed | inherits the Review authority boundary | each statement activates with the contract that implements it |

---

## 15. Deferred F2 / F3 / F4 responsibilities

F1 names these dependencies without solving them.

### F2

```text
the complete Work Candidate schema, including the empty-artifact Candidate's content
base-lineage identity and its binding
the three projections' Work-kind contents
the Review-validity closure and its durable home
isolated verification and the Evidence execution model
the reviewer identity/version binding and its mismatch refusal at the gate
binding the activation record's canonical digest into Review Context / Candidate identity
```

### F3

```text
the exact K1/K2 durable proof checkpoints and their contracts
the split publication implementation and the review-v1-split-v1 validator
no-push-before-proof validator internals
the review-v1 terminal stage shape and its recorded-completion proof
Consumption terminal stage mechanics and ordering
the K2 metadata-only recursion cutoff's exact delta rule
```

### F4

```text
Class A / B / C mismatch behaviour in full
adopt_existing_local_commit
stale-generation mechanics
the full recovery and interruption matrix
```

---

## 16. Critical invariants

These are the stop conditions of this contract. An implementation that violates any of them is not implementing
this contract.

```text
 1. Legacy START remains legacy, and behaves exactly as it does at the frozen baseline, unless
    review-v1 is explicitly selected by the caller.

 2. A pending mutation's semantic contract never changes on retry. It is never upgraded, never
    downgraded, and never reinterpreted by a later activation.

 3. The review-v1 publication contract is durable operation metadata, written before the first Git
    stage, and is never inferred from stage shape, file presence, content or branch state.

 4. Activation never becomes lifecycle truth. Lifecycle stays derived from canonical entities,
    relations and lifecycle events, and nothing that derives it reads a Review record.

 5. No post-activation review-v1 terminal event may exist until the Event metadata carrier is
    complete end-to-end (Gate 1).

 6. No activation may occur until the empty-artifact Consumption contract is implementable
    (Gate 2). The activation producer fails closed until both gates are satisfied.

 7. A result-less Work is a valid review-v1 case, never a refusal.

 8. An empty artifact never invents a K1: no synthesized commit, no placeholder commit id.

 9. Review remains a subordinate authorization gate. It opens no mutation, holds no lock,
    finalizes no Git, and progresses nothing.

10. No existing pending legacy START is migrated, converted or reinterpreted, and no bulk
    migration of any existing Work, event or record is performed.

11. Unknown, partial or contradictory contract metadata fails closed. No ambiguous state ever
    silently selects the weaker contract, and absence of arbitrary Review files is never proof of
    legacy.
```

---

## 17. Implementation readiness

```text
Contract status              FROZEN
Contract blockers            NONE
Implementation authorized    NO
P3 implementation            NOT STARTED

Implementation order         Gate 1  Event metadata carrier
                             Gate 2  Consumption version 1 artifact_kind repair, test-pinned
                             Gate 3  activation producer and actual activation

Not implemented by this contract:
  the Event metadata carrier
  the Consumption repair
  the activation producer
  any change to src/, tests/, registry.md, canonical Skills, or any P1 / P2 freeze document
```
