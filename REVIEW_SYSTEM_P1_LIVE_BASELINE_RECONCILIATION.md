# Review System P1 — Live Baseline Reconciliation Checkpoint

Status: CONTRACT RECONCILED TO LIVE BASELINE / P1-FLBR-01 RESOLVED (D1 REPAIRED) / IMPLEMENTATION NOT STARTED / FINAL READINESS CHECK REQUIRED

The focused review of this reconciliation returned one Finding, `P1-FLBR-01`, now repaired and frozen: see `REVIEW_SYSTEM_P1_FINAL_BASELINE_REPAIR.md`. §4.1 below is amended by it — the same-stage `git_commit` -> `git_push` pair is the current/legacy combined publication shape (R5 §12.1), not the Review-v1 split shape (R5 §12.2).

This checkpoint records the reconciliation of the frozen P1 Integration Contract to the current live baseline. It is non-normative until implementation and canonical authority activation.

Runtime authority remains `registry.md`, registry-routed canonical Skills, and the live implementation and tests. `BACKLOG.md` is non-normative.

## 1. Baselines

```text
old readiness baseline: 19bf5e71da6c7d735666e62cbe5b12ed9fffa5a9
new live baseline:      e32a74192e70d3ce8aec09f1921f175ac72b2d1d
```

`19bf5e71` is a strict ancestor of `e32a741`; the window is 11 forward commits with no divergence.

## 2. Disposition

```text
Candidate 7 architecture: RETAIN
Architecture reopen:      No
Candidate 8:              No
New architecture document: None
HUMAN decision:           None

contract reconciliation:
  R5   updated
  R7   updated
  R6   consequential update
  R11  consequential update
  R12  updated
  Integration Contract Reconnaissance  status/next-stage updated

implementation: NOT STARTED
```

This was a reconciliation of frozen contract text to confirmed live drift. It was not an architecture review, and no architecture-level decision was revisited.

## 3. Architecture seam confirmed intact

Verified at `e32a741`:

```text
src/workline/state.py   5073c8994cc706a5e1a1c9aef28b1beee78f5e3d   unchanged
src/workline/ids.py     4bac3fb61908428da02b870889bcafaa2e4c27d5   unchanged
src/workline/gitops.py  415d61bf28b951c2123f6a75e74d016c5288aa93   unchanged
src/workline/destination.py 500ecb75fdac85d7c8166c314eaae472f8389653 unchanged
```

`bootstrap.py`, `store.py`, `durable.py`, `validate.py`, `push_pin.py` and `pushurl.py` are likewise untouched across the window, and `_head_advanced_independently()` is byte-identical.

Therefore: lifecycle/progression authority, Review's subordinate-gate role, the R1 durable-layout and bootstrap seam, the R2 ID-reservation seam, and the R6 §1 fast-path premise all carried over unchanged. Only R5 and R7 held text that live authority had moved past.

## 4. Live drift reflected into the contracts

Each item was re-verified against live code at `e32a741` before being written into a contract.

### 4.1 Git publication stage shape — R5 §1.1, §1.2, §12

`workline.mutation._recorded_publication` proves a recorded push only when its Git stage is an exact ordered pair — `git_commit` then `git_push`, adjacent in the record, consecutive by `seq`, with no third effect carrying that stage — plus commit-ID, branch, single-parent, base-descent, recorded-paths and branch-containment proofs. `Mutation.apply` applies the recorded effects in one ordered pass with no interposition point between them.

R5 now states the topology as an ordering of durable checkpoints (C-1 commit, C-2 proof, C-3 push) rather than as effect adjacency, and records implementation requirement **R5-IMPL-1**: the Review-v1 path must explicitly split the combined commit+push finalization stage so the proof checkpoint sits durably between a commit-only stage and a push stage.

`NO PUSH BEFORE EXACT PROOF` was not weakened to fit the current combined stage. If the split cannot be implemented, Review-v1 result push is unavailable and the operation fails closed.

### 4.2 Operation-owned K1 identity — R5 §3, R7 §2

`registry.md` (Commit / push) refuses to adopt a commit the mutation did not make, declines branch-tip, message and content-identity fallback, does not run the recorded push, and stops at `reconcile required` as a publication safety boundary.

R5 §3 now scopes missing commit-id recovery to exactly one situation — this operation's Git commit actually succeeded and the record save was lost — and makes ownership a precondition rather than a conclusion:

```text
operation-owned K1 identity must be positively proven
a commit this operation cannot show it created is never adopted,
however exactly its content, tree, parent, branch or message match
```

Where ownership cannot be proven: reconcile, or a new Candidate against the actual committed state, or the applicable fail-closed path. Never silent adoption, never a push. R7 §2 item 1 carries the same precondition, so Class A is not a route around it.

R5 §3.4 scopes out the live BL-054 path (`stage_writes_already_committed`, used by `start._registration_already_committed`): it applies to registration stages only (`write_file`, `add_relation`), names no commit, writes no commit ID, publishes nothing, and proves only that the written state was reached. It is not K1 adoption. R5 §3.5 freezes what happens when a Review-v1 result reaches committed state without an owned commit: no K1, no proof, no push, reconcile or new Candidate.

### 4.3 Exact-commit publication — R5 §7, R7 §4, R7 §8

`workline.gitcmd.push` and `push_dry_run` route through `_exact_refspec`, which rejects anything that is not `<full commit ID>:refs/heads/<name>`, and never force. `registry.md` states that the approved destination authorizes where a push may write, not what it may publish.

R5 §7 and R7 §8 now freeze publication as an exact authorized commit ID. R7 §8's former "push branch containing K1 + K2" is restated as pushing the exact authorized K2 commit ID, with K1 reaching the destination as K2's proven exact parent rather than by pushing a branch.

R7 §4's dry-run table is reconciled rather than retained: `=`, `*` and ` ` keep their dispositions against the exact refspec, and `!` is resolved by the positive destination read described in §4.4 below.

### 4.4 Destination read — R7 §4.2, R6 §6.1, R11 §10.1

For `!`, live `workline.mutation._published_under` confirms Git reads the recorded locator as itself (`git ls-remote --get-url`, which resolves locally and contacts nothing), reads where the destination branch points (`git ls-remote --refs`), and where ancestry cannot yet be decided brings that branch's history into the object database alone — no ref created or moved, no `FETCH_HEAD`, no tag, no submodule, no bundle URI, no maintenance. Destination holds the commit: published, nothing pushed. Does not hold it: reconcile, nothing pushed or forced. Unreadable, or changed while being read: STOP.

This is written into R7 §4.2 as a positive proof, explicitly not a remote-tracking-ref heuristic and not a fetch-and-reset. R7 §4.3 keeps reset, rebase, force push, stale remote-tracking refs as publication evidence, and ambiguous branch-tip pushes prohibited.

R6 §6.1 and R11 §10.1 add the read to the material dependency surface as `network`, `external_service`, `git_state` and `runtime_toolchain`, and separate it from the pre-proof external-process rule:

```text
pre-proof uncontrolled external side effect   -> fail closed
post-proof authorized publication-state read  -> permitted, declared
```

Unpinned or rewritten destination identity, an unanswerable read, or a destination that shifts while being read is fail-closed, never resolved as published and never as unpublished.

### 4.5 Complete delta plumbing — R7 §10

Re-verified: `commit_changes()` supplies complete rename-free changed-**path** enumeration against the first parent, and no live helper supplies mode or object identity — both it and the `ls-tree` helper use `--name-only`.

R7 §10 keeps its safety condition unchanged at complete path *and* mode *and* object type/object ID, and records the implementation binding:

```text
current commit_changes() is reusable for path enumeration,
but P1 still needs plumbing for mode/object identity
```

Until that plumbing exists, Class A is unavailable. The condition was not relaxed to match what live code currently provides. This is an implementation gap, not an architecture blocker.

### 4.6 Mandatory tests — R12 §10.1

Cases A-H frozen: owned commit with lost record backfills; foreign byte-identical commit must not be adopted; violated publication stage shape fails closed; exact-commit publication publishes only the authorized commit; destination already holding the exact commit classifies by the positive read; unanswerable or shifting destination fails closed; incomplete delta plumbing makes Class A unavailable; proof-before-push holds across every crash/resume window including the R5 §1.2 split stages.

## 5. BL-055

```text
BL-055 exists as a separate future authority-hygiene concern.
It did not change current runtime authority and is not a blocker
for this P1 baseline reconciliation.
```

`BACKLOG.md` is non-normative, so BL-055's `Human confirmation likely: yes` is not a HUMAN decision for this reconciliation. BL-055 was not implemented here and no P1 architecture was changed on account of it.

## 6. Validation

```text
document/contract change only
no source file modified
no test file modified
no canonical authority file modified (registry.md, .claude/skills/**)
git diff --check clean
baseline ancestry verified before and after
```

The 293 seam tests covering the `19bf5e71..e32a741` window were already green at this baseline during the reconciliation that preceded this checkpoint. No full-suite rerun was required for a contract-only change.

## 7. Current checkpoint

```text
P1-FLBR-01-D1:             REPAIRED / FROZEN
P1-FLBR-01:                RESOLVED

Candidate 7 architecture:  RETAIN
Architecture reopen:       No
Candidate 8:               No
HUMAN decision:            None

Live implementation baseline:
                           e32a74192e70d3ce8aec09f1921f175ac72b2d1d

Implementation:            NOT STARTED

Next: final P1 implementation readiness check

Status: READY_FOR_FINAL_P1_IMPLEMENTATION_READINESS_CHECK
```

The focused review of this reconciliation is complete. It returned exactly one Finding, `P1-FLBR-01`, repaired in `REVIEW_SYSTEM_P1_FINAL_BASELINE_REPAIR.md`. The closure review of that repair returned one further Finding, `P1-FLBR-01-D1` (discriminator precedence, MID), repaired in the same document at its section 9. Both were contract text only; the live implementation baseline did not move.
