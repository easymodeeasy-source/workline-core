# Review System P1 — R5 START Result Commit / Proof / Push Split Contract Freeze

Status: CONTRACT FROZEN / REPAIRED AFTER EXTERNAL REVIEW / IMPLEMENTATION NOT STARTED

This checkpoint freezes the Git transaction shape required by Candidate 7 for Review-v1 Work completion. It is non-normative until implementation and canonical authority activation.

## 1. Live behavior confirmed

Today `gitops.finalize()` records `git_commit` and optional `git_push` in one mutation stage and applies both before caller control returns. START `_Session._commit()` therefore cannot currently insert Review proof between local commit and push.

Current Work completion is conceptually:

```text
executor Completed
-> completion_precheck
-> result commit + push
-> terminal lifecycle events
-> terminal canonical commit + push
-> postcheck
```

Review-v1 requires:

```text
local result commit K1
-> exact post-commit proof
-> only then push K1
```

The current Mutation model already has separately classifiable commit and push effects, so the split remains an API/flow change rather than a new Git engine.

## 2. Frozen helper split

### `commit_local(...)`

Records/applies only an exact `git_commit` effect.

Required properties:

- preserve pre-existing dirty/separability checks;
- stable stage on retry;
- no network contact;
- expose an exact operation-made commit identity only when that identity is durably recorded or positively reconstructed under section 3;
- never use commit message as commit identity.

### `push_committed(...)`

Records/applies only an authorized `git_push` effect after required post-commit proof.

Required properties:

- verified Project destination/pin;
- exact branch/lineage still contains authorized commit/chain;
- existing dry-run classification/destination recheck preserved;
- stable stage on retry;
- no implicit commit.

Legacy operations may retain a compatibility wrapper equivalent to current finalize until explicitly migrated. Review-v1 paths use the split boundary.

## 3. Mandatory recovery: commit succeeded, commit ID not durably saved

Live Mutation has this interruption window:

```text
recorded git_commit effect
-> git commit succeeds
-> HEAD = K
-> process crashes before effect.applied / commit_id durable save
```

A later clean-looking tree or matching commit message is not proof that K is the mutation's commit.

When a recorded Review-v1 commit effect has no durable made-commit ID, the implementation may backfill K only if all of these are positively proven:

```text
1. current branch ref == recorded commit branch
2. current HEAD is one exact commit K
3. parents(K) == [recorded base_head]
   (or explicitly valid root-parent shape)
4. complete recorded-base -> K tree delta equals the exact expected commit projection
5. no extra post-commit commit exists between recorded base and K
6. every Git/tree query required by the proof succeeded completely
7. current Candidate/Context/Policy/authorization identities required at this proof phase still match
```

The complete tree proof includes path entry identity, content/blob identity, mode, deletion, symlink/gitlink semantics, and case/path semantics applicable to the repository. It is not merely `changed_against_head()==empty` or recorded-path non-conflict.

If every predicate passes:

```text
K is positively reconstructed as this recorded mutation's exact K1
-> durably backfill K into the mutation commit effect record
-> persist applied/commit identity under the normal recovery record durability rule
-> only then may post-commit Review proof continue
```

If any predicate is false or unprovable: `reconcile_required`, except where the separately proven R7 Class A entry conditions apply. Never create/push a proof checkpoint first and infer commit identity later.

Backfill is idempotent only for the same exact K. A conflicting durable ID or changed branch/HEAD/parent/tree is reconcile required.

## 4. Normal Review-v1 Work completion topology

For non-empty ReviewedArtifactProjection:

```text
B = verified Candidate base

working tree Candidate + sealed Gate + Receipt R1
↓
local K1 commit
↓
resolve exact K1 identity
  - from durable made-commit ID
  - or section 3 positive reconstruction/backfill
↓
POST-COMMIT PROOF K1
  A. ReviewedArtifactProjection equality
  B. OperationMetadataProjection equality
  C. complete parent->tree delta scope equality
  D. verified base / Review-validity check
  E. Receipt/Gate current
↓
AUTHORIZED PUSH K1
↓
terminal stage
  AuthorizedTransitionProjection: work_target_removed as applicable + work_completed E1
  OperationMetadataProjection: Consumption C1 binding R1 + K1 + E1
↓
local K2 terminal commit
↓
resolve exact K2 identity by the same commit identity discipline
↓
POST-COMMIT PROOF K2
  exact transition/metadata projection
  complete K1->K2 delta
  no ReviewedArtifact/domain result delta
↓
AUTHORIZED PUSH K2
↓
postcheck lifecycle + ReviewStore invariants
↓
mutation complete
```

The remote may temporarily contain authorized K1 while the Work remains non-terminal until K2. Retry resumes the pending terminal mutation.

## 5. No-result Work

An empty ReviewedArtifactProjection still requires clone-safe authorization:

```text
sealed Gate + Receipt R1
-> metadata-only local K1
-> exact commit identity resolution
-> metadata/scope proof
-> authorized push K1 if configured
-> terminal stage/K2
```

## 6. Receipt self-reference boundary

Receipt does not contain the SHA of the commit containing itself. It binds Candidate/Context/Policy/generation/obligation identities. Consumption later binds exact proven K1.

This avoids self-referential commit bytes.

## 7. K1 proof before push

After `commit_local`, caller code regains control before any push effect is recorded.

Proof inspects actual commit object/tree/parent and relevant Git persistence semantics. Hooks, filters, line endings, modes, symlinks/gitlinks and attributes are reasons to inspect actual Git result rather than assume the expected worktree became the commit.

A failed/unproven K1 never receives a normal push effect.

## 8. Push binding

Before recording/replaying push:

```text
current branch ref == expected branch
HEAD/history contains exact authorized K1/K2
configured destination == pinned destination
push dry-run is an allowed new/fast-forward/up-to-date state
latest durable Review authorization still validates
```

History rewrite/reset/rebase or unprovable lineage is reconcile, not automatic recomputation.

## 9. Terminal K2

K2 finalizes exact terminal transition + Consumption metadata. It needs exact post-commit proof but no new Receipt.

If a hook/transformation changes K2 outside deterministic expected projection, reconcile. Do not recursively enter Class A for terminal K2.

## 10. Mutation/Git capabilities required

Implementation needs:

- commit-only mutation stage;
- push-only mutation stage;
- durable access to a recorded made commit ID;
- positive reconstruction/backfill of a missing commit ID under section 3;
- exact branch/parent/lineage inspection;
- complete actual parent->commit tree delta inspection;
- Review proof checkpoint binding before any Review-v1 push effect;
- latest authorization recheck on resume.

Proof checkpoint binds at least:

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

## 11. Legacy activation

Explicit operation-contract identity distinguishes:

```text
legacy -> existing completion Git semantics
review-v1 -> split commit/proof/push semantics
unknown/contradictory -> reconcile
```

Absence of Review files alone is not legacy evidence. Finished legacy Work is not retroactively reviewed.

## 12. No forceful Git repair

No amend/reset/rebase/force push/clean recovery is introduced.

Mismatch handling remains:

```text
fully operation-owned transformed K1 -> possible Class A only under R7
unexpected/non-owned delta           -> reconcile
lineage/ref/unproven identity         -> reconcile
```

## 13. External-review repair disposition

Accepted and repaired here:

- exact K1/K2 identity recovery for commit-success/save-crash window;
- durable positive-proof backfill before any Review proof/push;
- Class A cannot rely on a merely plausible unrecorded commit identity.

Architecture blocker: `None`.

HUMAN decision: `None`.
