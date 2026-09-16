# Review System P1 — R5 START Result Commit / Proof / Push Split Contract Freeze

Status: CONTRACT FROZEN / ROUND 2 REPAIRED / IMPLEMENTATION NOT STARTED

This checkpoint freezes the Git transaction shape required by Candidate 7 for Review-v1 Work completion. It is non-normative until implementation and canonical authority activation.

## 1. Required topology

Review-v1 Work completion uses:

```text
local K1
-> exact K1 identity
-> post-commit artifact/metadata/scope/Review-validity proof
-> authorized push K1
-> terminal event + Consumption stage
-> local K2
-> exact K2 proof
-> authorized push K2
-> postcheck / mutation complete
```

No push before exact proof. Receipt/Consumption remain non-self-referential.

## 2. `commit_local(...)`

Commit-only primitive must:

- preserve pre-existing dirty/separability checks;
- record/apply only commit, never Workline push;
- expose exact commit identity only if durable or positively reconstructed;
- never use message as identity;
- make **no uncontrolled external/network side effect** before proof.

## 3. Missing commit-id recovery

If Git commit succeeds but crash occurs before `commit_id`/applied save, K may be backfilled only after positive proof of:

```text
current branch == recorded branch
HEAD = exact K
parents(K) == recorded base
complete base->K tree delta == expected projection
no extra post-commit commit
all required Git inspection complete
Candidate/Context/Policy/authorization identities current
```

Tree proof includes content/object identity, mode, deletion, symlink/gitlink and applicable path/case semantics.

If proven, durable backfill occurs before Review proof/push. Otherwise reconcile, except separately proven R7 Class A.

## 4. Commit hooks / filters and external side effects

Live `git commit` may execute hooks and applicable clean/process filters. Therefore "no `git_push` Mutation effect" is not by itself proof that no publication/network side effect happened.

Before Review-v1 `commit_local`, implementation must classify applicable hook/filter execution for that commit.

Frozen rule:

```text
applicable hook/filter can produce external side effect
AND that side effect is not mechanically denied/contained
-> STOP before commit_local
```

A Review-v1 commit path may mechanically suppress hooks only if the suppression itself is part of the frozen Review-v1 Git persistence semantics and does not change the semantic bytes Review expects Git to persist.

Filters that materially define committed bytes cannot simply be disabled to obtain safety. They must either:

- execute within a mechanism that mechanically satisfies the no-uncontrolled-network/external-side-effect requirement and whose identity is bound by R6/R11; or
- cause Review-v1 commit to fail closed.

R6 continues to bind effective attributes/filter/config/hook/tool identity as material Review-validity/Git persistence dependencies.

## 5. `push_committed(...)`

Push-only primitive runs only after proof checkpoint. It requires exact branch/lineage, authorized K1/K2, current pinned destination, allowed dry-run classification and latest authorization recheck. No implicit commit.

## 6. K1/K2 semantics

K1 contains ReviewedArtifact plus required pre-consumption Review metadata, or metadata-only authorization for an empty artifact Candidate. K2 contains deterministic terminal transition + Consumption metadata only. K2 needs proof but no new Receipt; Class A does not recursively apply to terminal K2.

A remote may validly contain authorized K1 while Work remains non-terminal until K2.

## 7. Legacy/review-v1 activation

P3 uses R4's durable activation marker and event operation-contract metadata to distinguish pre-activation legacy completion from review-v1 completion. Unknown/contradictory classification reconciles. Absence of arbitrary Review files is not legacy proof.

## 8. No forceful recovery

No amend/reset/rebase/force-push/clean recovery is introduced.

## 9. Round-2 repair disposition

P1R-04 LOW improvement is accepted now: R5's existing `commit_local()` no-network requirement is made mechanically testable against active hooks/filters rather than assuming Workline's own push effect is the only publication path.

Architecture blocker: `None`.

HUMAN decision: `None`.
