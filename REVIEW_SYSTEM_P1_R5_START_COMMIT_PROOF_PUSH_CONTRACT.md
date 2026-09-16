# Review System P1 — R5 START Result Commit / Proof / Push Split Contract Freeze

Status: CONTRACT FROZEN / ROUND 3 REPAIRED / IMPLEMENTATION NOT STARTED

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

## 4. External executable/process surface before proof

The prior hook/filter-only wording is superseded. Review-v1 must classify **every external executable or process that Git can invoke on the exact staging + local-commit path** before `commit_local()`.

Minimum surface includes, when effective/applicable:

```text
pre-commit
prepare-commit-msg
commit-msg
post-commit
core.hooksPath / effective hook path
clean filters
process filters
LFS clean/process filters
commit signing helpers/programs
GPG signing programs
SSH signing programs/default-key commands
other configured commit-time external helpers that the exact Git invocation can execute
```

Surfaces not invoked by the exact staging/commit path, such as smudge-only filters, textconv/external diff drivers, or credential helpers in an otherwise local commit, are not automatically material merely because Git supports them. If configuration causes them to become reachable, they enter the classified surface.

Frozen rule:

```text
applicable external process can produce uncontrolled filesystem/network/external-service side effect
AND that side effect is not mechanically denied/contained
-> STOP before commit_local
```

Classification itself must be positive and complete. "No known hook" or "Workline did not call push" is insufficient.

## 5. Commit signing behavior

For Review-v1 `commit_local`, the default P1/P3 contract is:

```text
invoke Git with signing explicitly disabled for that commit
(equivalent to `--no-gpg-sign`)
```

This prevents repository/user/global `commit.gpgSign=true` from silently launching an external signing program before Review proof.

`Review-v1 commit signing = disabled by commit_local-v1` is part of the frozen Git persistence semantics identity and is bound into R6/R11 Review-validity/Evidence identity.

If a future operation requires signed Review-v1 commits, that is a later explicit contract version. It must positively bind signing format/program/agent/key/helper identity and mechanically contain external side effects before activation. P1 does not infer such safety.

## 6. Hooks / filters and semantic bytes

A Review-v1 commit path may mechanically suppress hooks only if the suppression itself is part of the frozen Review-v1 Git persistence semantics and does not change semantic bytes Review expects Git to persist.

Filters that materially define committed bytes cannot simply be disabled to obtain safety. They must either:

- execute within a mechanism that mechanically satisfies the no-uncontrolled-network/external-side-effect requirement and whose identity is bound by R6/R11; or
- cause Review-v1 commit to fail closed.

Effective attributes/filter/config/hook/tool identity and the explicit signing-disabled commit mode are material Review-validity/Git persistence dependencies.

## 7. `push_committed(...)`

Push-only primitive runs only after proof checkpoint. It requires exact branch/lineage, authorized K1/K2, current pinned destination, allowed dry-run classification and latest authorization recheck. No implicit commit.

## 8. K1/K2 semantics

K1 contains ReviewedArtifact plus required pre-consumption Review metadata, or metadata-only authorization for an empty artifact Candidate. K2 contains deterministic terminal transition + Consumption metadata only. K2 needs proof but no new Receipt; Class A does not recursively apply to terminal K2.

A remote may validly contain authorized K1 while Work remains non-terminal until K2.

## 9. Legacy/review-v1 activation

P3 uses R4's durable activation marker and event operation-contract metadata to distinguish pre-activation legacy completion from review-v1 completion. Unknown/contradictory classification reconciles. Absence of arbitrary Review files is not legacy proof.

## 10. No forceful recovery

No amend/reset/rebase/force-push/clean recovery is introduced.

## 11. Round-3 repair disposition

P1R2-NF-02 is closed by broadening `commit_local()` safety from hooks/filters to the complete reachable external-process surface and freezing P1 Review-v1 commits as explicitly unsigned via signing-disabled Git invocation. Signing-disabled identity is part of Git persistence semantics and test/review closure.

Architecture blocker: `None`.

HUMAN decision: `None`.
