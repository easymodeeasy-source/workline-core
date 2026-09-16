# Review System P1 — R5 START Result Commit / Proof / Push Split Contract Freeze

Status: CONTRACT FROZEN / IMPLEMENTATION NOT STARTED

This checkpoint freezes the Git transaction shape required by Candidate 7 for Review-v1 Work completion. It is non-normative until implementation and canonical authority activation.

## 1. Live behavior confirmed

Today `gitops.finalize()` records a `git_commit` and optional `git_push` in the same mutation stage, then calls `mutation.apply()`. Therefore, when a remote exists, a successful local commit is immediately followed by the push before caller code regains control.

START `_Session._commit()` always uses this helper. Current Work completion is:

```text
executor Completed
-> completion_precheck
-> result commit + push (when result paths exist)
-> append work_target_removed + work_completed
-> terminal canonical commit + push
-> postcheck completed
```

This is safe under the current lifecycle contract but cannot satisfy Candidate 7's Review-v1 invariant:

```text
local result commit K1
-> exact post-commit proof
-> only then push K1
```

The current Mutation Controller already supports separate stages and separately classifiable `git_commit` / `git_push` effects, so the needed split is an API/operation-flow change, not a new Git engine.

## 2. Frozen common Git helper split

P1/P3 implementation must split current `gitops.finalize()` responsibility into recoverable primitives with these semantics:

### `commit_local(...)`

Records/applies **only** a `git_commit` effect for an exact path set and returns/exposes the exact commit object ID that the Mutation Controller proved it made.

Required properties:

- same pre-existing dirty/separability checks as current finalize;
- one-parent commit contract where Candidate 7 requires it;
- stable mutation stage on retry;
- exact made commit identity comes from the recorded `_MADE_COMMIT`/equivalent mutation fact, not commit message search;
- no network contact and no `git_push` effect.

### `push_committed(...)`

Records/applies **only** the authorized `git_push` effect after the caller has completed the required post-commit proof.

Required properties:

- use the already verified Project push destination/pin;
- verify current branch/lineage still contains the exact commit/proven commit chain being published;
- preserve existing dry-run classification and destination recheck immediately before push;
- stable stage on retry;
- no implicit new commit.

Legacy operations may keep a compatibility wrapper equivalent to current `finalize(commit+push)` until their operation contract is explicitly migrated. Review-v1 paths use the split primitives.

## 3. Normal Review-v1 Work completion topology

For a Work whose ReviewedArtifactProjection is non-empty, freeze this topology:

```text
B = verified Candidate base commit

working tree Candidate + canonical sealed Gate generation + Receipt R1
↓
local K1 commit
  - ReviewedArtifactProjection
  - required pre-consumption OperationMetadataProjection (R1 and exact gate metadata)
↓
POST-COMMIT PROOF K1
  A. ReviewedArtifactProjection equality
  B. OperationMetadataProjection equality
  C. complete K1 parent->tree delta scope equality
  D. verified base / Review-validity check
  E. Receipt/Gate identity current
↓
AUTHORIZED PUSH K1 (if Project has a configured destination)
↓
record/apply terminal stage
  AuthorizedTransitionProjection:
    work_target_removed as applicable
    work_completed E1
  OperationMetadataProjection:
    Consumption C1 binding R1 + K1 + E1
↓
local K2 terminal commit
↓
POST-COMMIT PROOF K2
  - exact transition projection
  - exact Consumption metadata projection
  - complete K1->K2 delta scope
  - no ReviewedArtifact/domain result delta
↓
AUTHORIZED PUSH K2
↓
postcheck lifecycle + ReviewStore cardinality
↓
mutation complete
```

K1 and K2 are normal one-parent commits.

The remote may temporarily have K1 without K2 if the terminal step later fails. That is intentional: K1 is an authorized reviewed result commit, while Work lifecycle remains non-terminal until K2. Retry resumes the pending mutation and finishes terminalization. Publication of an authorized result is not equivalent to lifecycle completion.

## 4. Work with no result-path delta

A Review-v1 Work with an empty ReviewedArtifactProjection still needs a durable authorization artifact before terminal consumption.

Frozen rule:

```text
sealed Gate + Receipt R1
-> local K1 metadata-only authorization commit
-> exact metadata/scope proof
-> authorized push K1 if remote
-> terminal stage / K2 as above
```

K1 in this case contains no Work result path; it carries only the exact canonical Review gate/Receipt metadata required to establish clone-safe authorization.

This avoids a special in-memory-only authorization path and gives Consumption a concrete authorized result commit identity.

## 5. Why Receipt may be in K1 without self-reference

Receipt contains Candidate/Context/Policy/generation/obligation identities, not the SHA of the commit containing the Receipt. Therefore R1 may be deterministically rendered before K1 and included in K1.

`authorized_result_commit_sha` is stored in the later Consumption, not R1.

Thus normal flow has no metadata-only K2 solely to save R1; Candidate 7's special metadata-only adoption K2 is reserved for Class A where K1 already exists before replacement Receipt R2 can be written.

## 6. K1 proof must happen before push

The proof boundary is a real operation stage, not prose. After `commit_local`, caller code must regain control before any `git_push` is recorded.

The proof must inspect the actual commit object/tree and parent rather than assuming that the worktree/index/expected path list implies what Git committed. Hooks, filters, line-ending conversion, executable mode changes, symlink/gitlink behavior, and other Git transformations are precisely why actual commit proof exists.

If K1 differs but is fully operation-owned and eligible for Candidate 7 Class A, route to R7. Otherwise reconcile; never push the unproven commit.

## 7. Push proof binding

A push stage is authorized against an exact local commit identity/chain. Before recording or replaying push:

```text
current branch ref == recorded expected branch
HEAD/history contains exact authorized K1 (or terminal K2 for terminal push)
configured destination == pinned recorded destination
push dry-run classifies only allowed new/fast-forward/up-to-date state
```

If HEAD advanced after proof, Review-validity/lineage rules must establish whether the exact authorized commit remains valid and whether the intended push is still safe. A branch rewrite/reset/rebase is reconcile, not an automatic recomputation.

## 8. Terminal stage and K2

The event + Consumption effects are one Mutation stage before K2. K2 finalizes exactly those canonical transition/metadata writes.

K2 does not need another Review Receipt because it is a deterministic consumption of R1, not a new ReviewedArtifact Candidate.

It does require exact post-commit proof before push:

```text
actual K2 parent == expected K1/current authorized terminal base
actual K2 delta == expected AuthorizedTransitionProjection + OperationMetadataProjection
no unexpected result/domain paths
```

If a hook/transformation changes K2 outside that deterministic projection, reconcile. Do not invoke Class A recursively for terminal metadata/transition K2.

## 9. Mutation API additions required

Exact Python names can vary, but the following capabilities are frozen:

- read the exact commit ID made by one named mutation stage without message heuristics;
- record/apply commit-only stage;
- record/apply push-only stage;
- assert exact branch/commit lineage before push;
- inspect actual parent->commit tree delta including path entry identity;
- prove that no push effect for a Review-v1 result/terminal commit exists before its required proof checkpoint is durably satisfied/bound in the mutation.

The Review proof checkpoint bound into the mutation includes at least:

```text
review_run_id
review_generation
candidate_hash
review_context_hash
effective_policy_hash
receipt_id
obligation_digest
commit_sha
proof_phase
```

A resumed push may proceed only if this bound proof checkpoint still matches the latest durable valid Review authorization.

## 10. Legacy activation

P3 activation must preserve explicit operation-contract identity:

```text
legacy -> existing completion Git semantics
review-v1 -> split local commit / proof / push semantics
unknown/contradictory -> reconcile
```

Absence of Review files alone is not evidence that an operation is legacy.

No already-finished legacy Work is retroactively reviewed.

## 11. No forceful Git repair

This contract does not introduce amend/reset/rebase/force-push/clean as recovery tools.

Mismatch handling remains:

```text
operation-owned transformed K1 -> possible Class A adoption (R7)
unexpected/non-owned delta      -> reconcile
lineage/ref unprovable          -> reconcile
```

## 12. Architecture blocker / HUMAN

Architecture blocker: `None`.

HUMAN decision: `None`.

The live code confirms the required split is necessary, and the existing Mutation effect model already supplies the primitives needed to implement it safely.