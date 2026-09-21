# Review System P1 — R5 START Result Commit / Proof / Push Split Contract Freeze

Status: CONTRACT FROZEN / ROUND 3 REPAIRED / LIVE-BASELINE RECONCILED (`e32a74192e70d3ce8aec09f1921f175ac72b2d1d`) / P1-FLBR-01 REPAIRED / IMPLEMENTATION NOT STARTED

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

### 1.1 Execution / durable-checkpoint boundary

The topology above is an ordering of **durable checkpoints**, not a prescription that the proof be recorded as a Mutation effect positioned between the commit effect and the push effect.

Live canonical recovery requires a pushed Git stage to be an exact ordered pair (§12). A contract reading that inserts a third effect — a proof effect — into that pair is therefore not implementable and must not be inferred from this document.

The frozen boundary is:

```text
checkpoint C-1  commit recorded + applied, exact K identity durable
checkpoint C-2  exact proof for that K complete and durable
checkpoint C-3  push of that exact K authorized and recorded
```

Frozen rules over those checkpoints:

```text
C-2 must be durably complete before C-3 is recorded or applied
a push effect may exist only for a K whose C-2 is already satisfied
crash at any point resumes at the earliest unsatisfied checkpoint
C-2 is never reconstructed from the presence of C-3
```

Where the proof material physically lives (a Review Gate/Receipt record written by an earlier stage of the same mutation, a durable proof record keyed by exact K, or an equivalent clone-safe durable artifact) is a P1 implementation detail. What is frozen is that it is durable, keyed by exact K identity, and complete before any push effect for that K is recorded.

### 1.2 Implementation requirement — Git-stage split

The live Git-stage abstraction (`workline.gitops.finalize` / `finalize_effects`) builds commit and push as one stage and applies them in one uninterrupted pass. That abstraction cannot express C-2 between C-1 and C-3.

P1 implementation must therefore **explicitly split the Git-stage abstraction** for the Review-v1 path so that the commit stage and the push stage are separate recorded stages with the proof checkpoint durably between them.

```text
P1 implementation requirement R5-IMPL-1

Review-v1 result persistence does not reuse the combined
commit+push finalization stage. It uses:

  stage S-c : git_commit only
  (durable exact-K proof checkpoint, C-2)
  stage S-p : the authorized push of that exact K

Each stage remains individually crash-safe and resumable.
```

This is an implementation requirement created by the reconciliation, not a weakening of any invariant. **`NO PUSH BEFORE EXACT PROOF` is not relaxed to accommodate the current combined stage.** If the split cannot be implemented, Review-v1 result push is unavailable and the operation fails closed; it does not fall back to pushing before proof.

The split shape is a publication contract of its own, separate from the current/legacy combined shape and validated separately: see §12.2 for the boundary, §12.3 for how a validator tells the two apart, §12.4 for the exact S-c / C-2 / S-p bindings and §12.5 for the fail-closed matrix.

## 2. `commit_local(...)`

Commit-only primitive must:

- preserve pre-existing dirty/separability checks;
- record/apply only commit, never Workline push;
- expose exact commit identity only if durable or positively reconstructed;
- never use message as identity;
- make **no uncontrolled external/network side effect** before proof.

## 3. Missing commit-id recovery

This section covers exactly one situation and no other:

```text
the Git commit invoked by THIS operation actually succeeded,
and the process crashed before the commit_id/applied save
```

It is a reconstruction of an operation-owned commit whose record write was lost. It is **not** a mechanism for deciding that some commit now present in the repository may serve as K.

### 3.1 Operation-owned identity is a precondition, not a conclusion

```text
operation-owned K1 identity must be positively proven
```

Ownership is proven first. The conditions in §3.2 are then checked against that owned commit. They are not a definition of ownership and they never confer it.

Frozen rule:

```text
a commit this operation cannot positively show it created
is never backfilled or adopted as K,
however exactly its content, tree, parent, branch or message match
```

A byte-identical commit created by another subject — a person committing a dirty working tree, another tool, another operation, another clone — is a foreign commit. Content equality is not authorship. Silent adoption is prohibited.

This matches live canonical authority: `registry.md` (Commit / push) refuses to adopt a commit the mutation did not make, declines branch-tip fallback, message fallback and content-identity inference, does not run the recorded push, and stops at `reconcile required` — stated there as a publication safety boundary rather than an error, because publication cannot be withdrawn.

### 3.2 Conditions checked against the owned commit

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

If ownership is proven and every condition holds, durable backfill occurs before Review proof/push.

### 3.3 When ownership cannot be proven

```text
reconcile
OR new Candidate against the actual committed state
OR the applicable fail-closed path
```

Never silent adoption, and never a push. Where the mismatch is a genuinely operation-owned transformation, R7 Class A applies — and R7 §2 item 1 carries the same ownership precondition, so Class A is not a way around this section.

### 3.4 Relation to the live registration-stage recovery path

Live code contains a separate recovery path — `workline.mutation.stage_writes_already_committed`, used by `workline.start._registration_already_committed` (BL-054) — which lets a mutation continue when another subject committed its written bytes and the mutation's own Git stage consequently does not exist.

That path is **not** K1 adoption and does not weaken this section:

```text
it applies to registration stages only
  (live _REGISTRATION_KINDS = write_file, add_relation)
it names no commit and writes no commit_id
it publishes nothing; a recorded push still publishes only
  the commit its own Git stage made
it proves only that the written state was reached:
  recorded bytes present, no path differing from HEAD,
  HEAD still on the branch and history the stage was decided on
```

Review-v1 result K1 is not a registration stage and never uses this path.

### 3.5 Review-v1 when no owned K1 exists

If a Review-v1 result stage's content reaches committed state without this operation having created the commit, there is no K1 and there never will be one for that attempt. Frozen behavior:

```text
no K1 identity
-> no exact K1 proof
-> no authorized push
-> reconcile / new Candidate against the actual committed state
```

The absence of an owned K1 is not completed work. It is not converted into a metadata-only authorization of somebody else's commit.

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

Push-only primitive runs only after the C-2 proof checkpoint (§1.1). It requires exact branch/lineage, authorized K1/K2, current pinned destination, allowed publication classification (R7 §4, as reconciled) and latest authorization recheck. No implicit commit.

What it publishes is frozen as an exact commit, never a branch tip:

```text
refspec = <exact authorized commit ID>:refs/heads/<full branch name>
never forced
never a branch-tip or pattern refspec
```

This matches the live primitive: `workline.gitcmd.push` / `push_dry_run` route through `_exact_refspec`, which rejects anything that is not `<full commit ID>:refs/heads/<name>`, and `registry.md` (Push destination) states that the approved destination authorizes *where* a push may write, not *what* it may publish.

Consequence, frozen: commits another subject placed on the same branch after the authorized commit — during a question wait, an interruption, or concurrent work — are not published by this push, whatever paths they touch. They reach the destination only if a later authorized commit of the same mutation is built on top of them and is itself published as an exact commit.

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

## 12. Publication shapes — two frozen contracts

There are exactly two publication shapes, and they are separate contracts with separate validators. Neither one's rule is evidence about the other.

```text
current-combined publication    §12.1   existing/current operations
review-v1-split publication     §12.2   Review-v1 only
```

A validator selects between them by the discriminator of §12.3, never by looking at the shape it finds.

### 12.1 `current-combined` publication

Re-verified at baseline `e32a741` in `src/workline/mutation.py` (`_recorded_publication`, `Mutation.apply`, `_publish`, `MutationController._classify_push`).

Live canonical recovery proves what a recorded push publishes only when the Git stage has this exact shape:

```text
the stage's effects are exactly two, in this order:
  git_commit   (the stage's only other effect)
  git_push     (second and last effect of the stage)
adjacent in the effect record
consecutive by seq
no third effect carries that stage
```

and, additionally, that the commit is recorded applied with the full ID of a commit this mutation made, names its branch in full, is matched by the push's branch, has exactly one parent descending from the recorded base, changes nothing outside the recorded paths, and is still held by the recorded branch.

Anything short of that names no commit, and the push is refused with `reconcile_required` rather than falling back to the branch tip.

This is the correct and complete recovery invariant for every existing/current operation, and **it is not weakened, narrowed or made conditional by anything in this contract.** A current-combined mutation whose Git stage is not that exact pair fails closed exactly as it does today.

Frozen consequences inside this shape:

```text
no third effect may be added to the pair, so the Review proof
  cannot be an effect inside it (§1.1)
the terminal event + Consumption stage is a separate stage
  from any Git stage (R4 §6), and adding a Consumption effect
  into a Git stage would break publication and fail closed
```

`Mutation.apply` applies the recorded effects in one ordered pass with no interposition point between a commit and its push, which is why §1.2 is an implementation requirement rather than a sequencing note.

### 12.2 `review-v1-split` publication

Frozen boundary:

```text
the same-stage exact git_commit -> git_push pair
is the current/legacy combined publication recovery shape (§12.1).

It is NOT the Review-v1 split publication shape.

Review-v1 uses the §1.2 cross-checkpoint
S-c -> C-2 -> S-p binding.
```

Review-v1 result publication therefore **does not** take the same-stage commit+push pair as its well-formed shape, and a Review-v1 push stage is not malformed merely because no `git_commit` sits beside it in the same stage. Its correctness is established across checkpoints instead, by the bindings of §12.4.

The converse is equally frozen: Review-v1 may **not** reach the destination through the current-combined shape. Using a combined stage would place the push in the same uninterrupted apply pass as the commit, which is precisely a push before proof. §12.5 refuses it.

```text
review-v1-split publication does not require a same-stage pair
review-v1-split publication may not use a combined stage to push
  before proof
neither statement relaxes §12.1 for anyone else
```

### 12.3 Discriminator — how a validator knows which contract applies

A validator must **never** infer the publication contract from the shape it observes. Shape is the thing being validated; using it to choose the rule would let a malformed current-combined stage re-describe itself as a Review-v1 split, and would let a Review-v1 mutation be judged by a rule it was never under.

The contract is read from durable operation metadata that the Review-v1 path already binds to its mutation:

```text
review operation identity
review contract / version
Review-v1 binding (review_run_id / generation as applicable)
```

Implementation requirement **R5-IMPL-2**: the publication contract is recorded as a versioned identity on the mutation, durable before any Git stage of that mutation is recorded.

```text
publication_contract = review-v1-split-v1
```

Frozen rules for that identity:

```text
absent            -> current-combined (§12.1), unconditionally
present and known -> that contract's validator
present, unknown / unreadable / contradictory
                  -> fail closed; never defaulted to either contract
```

It is **non-lifecycle operation metadata**, used only by mutation/recovery validation. It is not a lifecycle authority, it does not appear in `ProjectView/state.py` derivation, and it never changes Work/Phase/Roadmap state. Review remains a subordinate authorization gate.

No existing mutation is promoted to Review-v1 by its shape, its content, the presence of Review files, or the absence of a combined pair. A mutation without the identity is current-combined, full stop. Absence of the identity is a positive answer, not an unknown.

### 12.4 Review-v1 split binding — S-c / C-2 / S-p

Minimum durable bindings. Each is proven from its own record; none is reconstructed from a later one.

**S-c — commit stage.** Identifies the exact operation-owned commit K:

```text
exact commit ID K
expected branch (full ref name)
expected parent / recorded base
operation identity
```

Ownership is the precondition of §3.1: a commit this operation cannot show it created is not K, however exactly its content matches.

**C-2 — durable proof checkpoint.** Binds at least:

```text
exact K
Review Candidate / applicable projection identity
ReviewValidity identity
current authorization / generation identity
proof result
proof contract / version
```

```text
C-2 is never reconstructed from the existence of a push.
```

A push that exists without a provable C-2 is not evidence that a proof happened; it is an escape to be reconciled (§12.5).

**S-p — push stage.** Binds:

```text
the same exact K as C-2
exact pinned destination
exact destination branch / ref
latest valid authorization generation
review-v1 split publication contract identity
```

Before S-p is recorded **and** before it is applied, C-2 is re-checked as durably complete and still current. Passing the check once at record time does not carry to apply time.

### 12.5 Review-v1 split fail-closed matrix

```text
S-c exists, C-2 missing
-> no push

C-2 exists but binds a different K
-> fail closed

C-2 stale / superseded authorization
-> fail closed

S-p binds a different K than C-2
-> fail closed

S-p binds a different destination
-> fail closed

S-p exists but C-2 cannot be positively validated
-> reconcile / STOP

push already occurred but C-2 is absent or unprovable
-> NEVER infer proof from push
-> historical escape / reconcile as appropriate

a Review-v1 mutation contains a current-combined
same-stage git_commit + git_push pair
-> it does not bypass C-2
-> Review-v1 contract validation refuses that path
```

`unknown` is never `proven` anywhere in this matrix.

## 13. Round-5 live-baseline reconciliation disposition

Reconciled from readiness baseline `19bf5e71da6c7d735666e62cbe5b12ed9fffa5a9` to live baseline `e32a74192e70d3ce8aec09f1921f175ac72b2d1d`.

```text
§1.1 / §1.2  execution-vs-checkpoint boundary + Git-stage split requirement
§3           ownership precondition; foreign byte-identical commit never adopted;
             live registration-stage path scoped out; no-owned-K1 behavior frozen
§7           exact-commit refspec publication semantics
§12          live Git publication stage shape recorded
```

Invariants unchanged: `NO PUSH BEFORE EXACT PROOF`, no amend/reset/rebase/force-push/clean recovery, Receipt/Consumption non-self-referential, Review subordinate to `state.py` lifecycle authority.

Architecture reopen: `No`. Candidate 8: `No`.

Architecture blocker: `None`.

HUMAN decision: `None`.

## 14. P1-FLBR-01 repair disposition

Finding P1-FLBR-01 of the final focused live-baseline review: Round 5 recorded the live same-stage `git_commit` -> `git_push` pair as *the* publication shape while also requiring a Review-v1 split, so the two validation rules collided — a Review-v1 split push read as malformed under the very section that introduced the split.

Repair, contract text only:

```text
§12     restructured into two named, separately validated
        publication contracts
§12.1   current-combined - the live shape, preserved verbatim
        in substance and explicitly not narrowed
§12.2   review-v1-split - explicitly not the same-stage pair,
        and explicitly not permitted to push through one
§12.3   discriminator - contract read from durable non-lifecycle
        operation metadata (R5-IMPL-2), never inferred from shape;
        absent identity means current-combined, unconditionally
§12.4   S-c / C-2 / S-p minimum bindings
§12.5   Review-v1 split fail-closed matrix
§1.2    cross-reference to the above
```

Nothing in §12.1 was relaxed: a current-combined mutation whose Git stage is not the exact pair fails closed exactly as before. Nothing in the split path permits publication before proof.

```text
P1-FLBR-01: REPAIRED / FROZEN
```

Live implementation baseline unchanged: `e32a74192e70d3ce8aec09f1921f175ac72b2d1d`.

Architecture: `RETAIN`. Architecture reopen: `No`. Candidate 8: `No`. HUMAN decision: `None`.
