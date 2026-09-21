# Review System P1 — Final Baseline Repair Checkpoint (P1-FLBR-01)

Status: P1-FLBR-01 RESOLVED (D1 REPAIRED / FROZEN) / IMPLEMENTATION NOT STARTED / FINAL READINESS CHECK REQUIRED

This checkpoint records the repair of the single Finding left by the final focused live-baseline review. It is non-normative until implementation and canonical authority activation.

Runtime authority remains `registry.md`, registry-routed canonical Skills, and the live implementation and tests.

## 1. Baselines

```text
live implementation baseline (unchanged): e32a74192e70d3ce8aec09f1921f175ac72b2d1d
contract baseline repaired from:          a09338682d2ecba7a15d36fd71d5b5b6bfedabed
```

This repair changes contract text only. It does not move the live implementation baseline, and no source, test or canonical authority file was touched.

## 2. The Finding

```text
P1-FLBR-01
current/legacy combined publication path and future Review-v1 split
publication path had colliding validation rules in contract text
```

Round 5 required, for Review-v1:

```text
commit-only boundary -> durable exact-K proof -> push-only boundary
```

while R12 case C stated, without qualification, that a recorded push whose Git stage is not the same-stage `git_commit` -> `git_push` exact pair is malformed and fails closed.

A Review-v1 split push has no `git_commit` beside it in its own stage. Read literally, the section that introduced the split also condemned every push the split produces. The two validation rules could not both be satisfied.

The Finding was in the contract text, not in live behaviour: live code at `e32a741` implements only the combined path, correctly.

## 3. Repair — two named publication contracts

R5 §12 is restructured from one shape description into two separately validated contracts.

### 3.1 `current-combined` publication (R5 §12.1)

The live shape, preserved in substance and explicitly not narrowed:

```text
one Git stage
  git_commit
  git_push
exact ordered pair
seq-consecutive
nothing else carries the stage
existing _recorded_publication() semantics
malformed pair -> fail closed / reconcile
```

Plus the commit-ID, branch, single-parent, base-descent, recorded-paths and branch-containment proofs already frozen. This governs every existing/current operation and is unchanged by this repair.

### 3.2 `review-v1-split` publication (R5 §12.2)

Review-v1 only. Conceptual durable order:

```text
S-c   commit exact K
C-2   durable proof checkpoint for exact K
S-p   authorized push of exact K
```

Frozen in both directions:

```text
Review-v1 does not require a same-stage commit+push pair
  as its well-formed shape, and an S-p with no git_commit beside
  it is not malformed under this contract;

Review-v1 may not use the current combined stage to reach the
  destination, because that places the push in the same
  uninterrupted apply pass as the commit - a push before proof.
```

### 3.3 Discriminator (R5 §12.3)

A validator never infers the contract from observed shape. The contract is read from durable operation metadata the Review-v1 path already binds — review operation identity, review contract/version, and the Review-v1 binding (`review_run_id` / generation as applicable) — surfaced as implementation requirement **R5-IMPL-2**:

```text
publication_contract = review-v1-split-v1
```

Non-lifecycle operation metadata for mutation/recovery validation only. Not a lifecycle authority, absent from `ProjectView/state.py` derivation, and it never changes Work/Phase/Roadmap state.

Selection precedence, as repaired by P1-FLBR-01-D1 (§9 below), is the cases A-E of R5 §12.3.1. An absent identity is not by itself an answer: it defaults to current-combined only on the positive showing that the mutation carries no durable Review-v1 operation metadata.

No mutation is promoted into Review-v1 by shape, content, presence or absence of Review files, Candidate existence, or presence or absence of a combined pair — and none is demoted out of it by them either (R5 §12.3.2).

## 4. Review-v1 split bindings (R5 §12.4)

Each is proven from its own record; none is reconstructed from a later one.

```text
S-c   exact commit ID K
      expected branch (full ref name)
      expected parent / recorded base
      operation identity

C-2   exact K
      Review Candidate / applicable projection identity
      ReviewValidity identity
      current authorization / generation identity
      proof result
      proof contract / version

S-p   the same exact K as C-2
      exact pinned destination
      exact destination branch / ref
      latest valid authorization generation
      review-v1 split publication contract identity
```

```text
C-2 is never reconstructed from the existence of a push.
```

C-2 is re-checked as durably complete and still current both before S-p is recorded and before it is applied; passing once at record time does not carry to apply time.

## 5. Fail-closed matrix (R5 §12.5)

```text
S-c exists, C-2 missing                       -> no push
C-2 binds a different K                       -> fail closed
C-2 stale / superseded authorization          -> fail closed
S-p binds a different K than C-2              -> fail closed
S-p binds a different destination             -> fail closed
S-p exists, C-2 not positively validated      -> reconcile / STOP
push occurred, C-2 absent or unprovable       -> NEVER infer proof
                                                 from push; historical
                                                 escape / reconcile
Review-v1 mutation contains a combined pair   -> does not bypass C-2;
                                                 validation refuses it
```

`unknown` is never `proven` anywhere in this matrix.

## 6. Test contract repair (R12)

```text
C -> C-current   scoped to current-combined mutations, i.e. those
                 carrying no Review-v1 split publication contract
                 identity; failure conditions unchanged, and a
                 current-combined mutation is never rescued by being
                 re-read as a Review-v1 split
§10.2            new mandatory Review-v1 split cases:
                 V1 well-formed split publication
                 V2 crash before proof            -> no push
                 V3 crash before push             -> revalidate, then push
                 V4 C-2/S-p bind different K      -> fail closed
                 V5 push without provable proof   -> never infer proof
                 V6 superseded authorization      -> no push
                 V7 destination pin changed       -> no push until current
                 V8 combined pair in Review-v1    -> refuse, no bypass
                 V9 discriminator integrity
```

`C-current` was scoped, not relaxed: every condition it failed closed on before, it still fails closed on.

## 7. Safety regression check

Nothing below was weakened by this repair:

```text
NO PUSH BEFORE EXACT PROOF
operation-owned K identity
foreign commit not adopted
exact commit refspec
pinned destination
latest authorization
unknown != proof
Class A rules
K2 recursion cutoff
no reset / no amend / no rebase / no force-push
Review is not lifecycle authority
state.py remains independent of Review metadata
```

R1-R4, R6, R7, R8-R11 are untouched. Candidate 7 architecture is unchanged.

## 8. P1-FLBR-01 closure condition

Closure condition, as required by the Finding: the current-combined publication validator and the Review-v1 split publication validator are now distinct contracts in text (R5 §12.1 vs §12.2), selected by a shape-independent discriminator (§12.3), with the Review-v1 `S-c -> durable C-2 -> S-p` binding (§12.4) and failure matrix (§12.5) frozen, and with the test contract split correspondingly (R12 `C-current` and §10.2).

## 9. P1-FLBR-01-D1 — discriminator precedence

The closure review of the above returned one Finding, severity MID.

### 9.1 The defect

§12.3 as first written said `absent -> current-combined, unconditionally` and `a mutation without the identity is current-combined, full stop`. That collapsed two unlike states into one answer:

```text
a mutation that was never under the Review-v1 contract
a Review-v1 mutation whose identity is missing
```

The second is reachable. R5-IMPL-2 requires `publication_contract` to be durable before the first Git stage, but a mutation can bind Review-v1 operation metadata and then be interrupted before that save. The old default routed it to §12.1, where a same-stage commit+push pair is well-formed — so it could publish without C-2. The hole was in the default, not in either shape rule.

### 9.2 Repaired precedence (R5 §12.3.1)

```text
A. publication_contract absent
   AND no durable Review-v1 operation metadata
   -> current-combined

B. publication_contract absent
   AND any durable Review-v1 operation metadata present
   -> contradictory -> fail closed
      (never current-combined, never review-v1-split)

C. publication_contract = review-v1-split-v1
   AND matching Review-v1 durable metadata
   -> review-v1-split

D. publication_contract present but unknown / unreadable
   / unsupported version, or metadata whose presence cannot
   itself be determined
   -> fail closed

E. publication_contract present but contradicted by the
   mutation's durable operation metadata
   -> fail closed
```

Case A's default is available **only** on the positive showing that no durable Review-v1 operation metadata exists. Absence that cannot be established is case D. A contradiction is never resolved by preferring the weaker contract.

`Review-v1 durable operation metadata` means review operation identity, review contract/version, `review_run_id` / generation, or any other durable Review-v1 binding on the mutation.

### 9.3 Test repair (R12 V9)

```text
V9-A  true legacy/current absence   -> current-combined
V9-B  contradictory absence         -> fail closed   [MANDATORY]
V9-C  explicit Review-v1            -> split validator
V9-D  unknown / undeterminable      -> fail closed
V9-E  explicit value contradicted   -> fail closed
V9-F  shape and content are never selectors
```

V9-B is the mandatory negative regression test for this Finding: a Review-v1 mutation interrupted after binding Review-v1 metadata and before `publication_contract` was saved must not reach the current-combined validator, and no same-stage pair in it may publish without C-2.

### 9.4 Scope of the change

§12.1's current-combined rule, §12.2's split rule, §12.4's bindings, §12.5's matrix (one row added), R12 `C-current` and V1-V8 are all unchanged. Only the selection between contracts was corrected, and strictly in the narrowing direction: case B moves a state that previously reached §12.1 into fail-closed. Nothing became newly acceptable.

## 10. Current checkpoint

```text
P1-FLBR-01-D1: REPAIRED / FROZEN
P1-FLBR-01:    RESOLVED

Architecture: RETAIN
Architecture reopen: No
Candidate 8: No
HUMAN: None

Live implementation baseline:
e32a74192e70d3ce8aec09f1921f175ac72b2d1d

Implementation:
NOT STARTED

Next:
final P1 implementation readiness check
```
