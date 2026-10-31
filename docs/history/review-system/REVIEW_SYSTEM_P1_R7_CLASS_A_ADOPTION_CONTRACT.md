# Review System P1 — R7 Class A `adopt_existing_local_commit` Contract Freeze

Status: CONTRACT FROZEN / LIVE-BASELINE RECONCILED (`e32a74192e70d3ce8aec09f1921f175ac72b2d1d`) / IMPLEMENTATION NOT STARTED

This checkpoint freezes the recovery contract for an operation-owned local commit that already exists but does not match the previously authorized Candidate. It is non-normative until implemented and activated through canonical authority.

## 1. Live facts inspected

Re-verified at baseline `e32a741` in `src/workline/gitcmd.py` and `src/workline/mutation.py`.

The current Mutation Controller records the exact commit object ID it made when it can prove that the new HEAD is a one-parent child of the pre-commit HEAD. Later resume recognizes that commit by object ID/history rather than message.

Current Git helpers can already prove:

- current branch/full ref;
- HEAD commit;
- commit parents (`commit_parents`);
- ancestry (`descends_from`);
- the commit a local full-name branch ref points at (`branch_commit`);
- paths touched between commits (`commit_touches`, against a preselected list);
- the complete changed-path set of a commit against its first parent, without rename detection (`commit_changes`) — **paths only**, see §10;
- pinned push destination;
- that Git reads a locator as itself rather than rewriting it (`reads_itself`, via `git ls-remote --get-url`; resolves locally, contacts nothing);
- what a real push of an exact refspec would do (`push_dry_run`, via `git push --dry-run --porcelain`);
- the commit a branch points at in the pinned destination (`destination_branch`, via `git ls-remote --refs`);
- the history behind a destination branch, fetched into the object database alone (`fetch_destination_branch`).

Live push semantics are exact-commit, never branch-tip: `push` and `push_dry_run` route through `_exact_refspec`, which rejects any refspec that is not `<full commit ID>:refs/heads/<name>`, and never force.

No amend/reset/rebase/force-push recovery is allowed by canonical Git rules.

## 2. Class A eligibility

A mismatching local commit K1 is eligible for Class A adoption only if **all** of the following are positively proven:

```text
1. K1 is the exact commit object made by the current operation/mutation path.
2. K1 has exactly the expected one parent.
3. The complete parent->K1 delta is operation-owned.
4. No non-owned/unexpected path or tree entry is present.
5. Current branch is the expected recorded branch and its lineage still contains K1.
6. K1 has not already been published to the configured destination as an unauthorized reviewed result.
7. The mismatch is a transform of operation-owned content, not evidence of unrelated interference.
```

If any item is not provable, this is not Class A. Reconcile rather than adopting by guess.

Item 1 is an ownership precondition and carries the same frozen rule as R5 §3.1: a commit this operation cannot positively show it created is never adopted, however exactly its content, tree, parent, branch or message match. Items 2-7 are checked against an already-owned commit; they never confer ownership. Class A is not a route around R5 §3.

## 3. Freeze K1 as new Candidate C2

Once eligible:

```text
old Candidate C1 / old Receipt R1
-> durable Class-A checkpoint naming exact K1 and mismatch reason
-> freeze K1's complete owned persisted projection as Candidate C2
-> run required Evidence/Review against exact C2
```

C2 is the commit tree/object reality, not a reconstruction from the current working tree.

The Review-validity closure and Context/Policy identities are recomputed/bound as required. R1 cannot authorize K1 after mismatch; it is superseded/ineligible for consumption.

## 4. Remote-publication check — reconciled to live publication classification

The check must occur **while the local branch HEAD is still exactly K1 and before metadata-only K2 is created**.

Use the pinned destination, confirmed against the Project pin and current Git configuration *before* anything is contacted, and the exact refspec a real push would use:

```text
<exact K1 commit ID>:refs/heads/<full branch name>
```

Branch-tip and pattern refspecs are rejected by the live primitive and are not a permitted fallback here.

### 4.1 Dry-run classification

`git push --dry-run --porcelain` of that exact refspec:

```text
"="
-> the destination branch is exactly K1
-> K1 is already published
-> NOT normal Class A adoption
-> record/report unauthorized publication or historical escape as applicable
-> reconcile/recovery path

"*" (new branch) or " " (fast-forward)
-> the destination branch is absent or strictly behind K1
-> positive evidence that K1 is not yet published through this branch
-> Class A may continue

"!"
-> not decided here; resolve by the destination read of §4.2

anything else / unanswerable / transport or auth failure
-> STOP; never taken for published or unpublished
```

The dry-run is put to the named remote, not to a resolved locator, so Git applies its own rewriting once and answers about the repository the push would actually write to.

### 4.2 `!` — positive destination read

`!` means the destination branch is not an ancestor of K1. That is either a branch that has moved past K1 — so K1 *is* published — or a divergent history. The dry-run cannot tell these apart, so the destination is read.

This is a **positive read of the pinned destination**, not a heuristic:

```text
1. confirm Git reads the recorded locator as itself
   (git ls-remote --get-url; resolves locally, contacts nothing).
   If Git would rewrite it to another repository -> do not read ->
   reconcile required, nothing pushed.
   If Git cannot say -> STOP.

2. read where the destination's branch points
   (git ls-remote --refs, read-only).

3. if this repository cannot yet decide ancestry, bring the
   destination branch's history into the object database only:
   no ref created or moved, no FETCH_HEAD, no tag, no submodule,
   no bundle URI, no automatic maintenance; working tree, index,
   HEAD and every branch unchanged.

4. classify:
   destination holds K1  -> published; nothing is pushed,
                            the branch is left where it is
   destination lacks K1  -> divergent; nothing is pushed or forced;
                            reconcile required
   unreadable / changed while being read / unprovable
                         -> STOP, never taken for published
```

For Class A specifically, "published" at step 4 means K1 is already at the destination, which is the `=` disposition of §4.1: **not** normal Class A adoption.

### 4.3 What remains prohibited

```text
reset
rebase
force push
stale remote-tracking ref as publication evidence
branch-tip / ambiguous whole-branch push
inferring publication from absence of discovered evidence
passing a resolved locator to another Git command without the
  step-1 self-read proof
```

The read in §4.2 is neither a remote-tracking-ref heuristic nor a fetch-and-reset: it creates no ref, writes no `FETCH_HEAD`, and changes nothing locally or remotely. It is the "stronger remote ancestry fact" this section previously anticipated, now present in live canonical authority (`registry.md`, Push destination) and in live code (`workline.mutation._published_under`). Reuse it; do not reimplement a weaker check beside it.

## 5. Replacement Receipt R2

After Review of exact K1/C2 converges:

```text
reserve R2
R2 authorizes exact Candidate C2 / K1 persisted artifact identity
write supersession of R1 as required
```

R2 does not contain the SHA of the commit that will store R2. It may contain exact K1 identity because K1 already exists and is the artifact being adopted.

## 6. Metadata-only K2

Because K1 already exists, R2 cannot be inserted into it without rewriting history. Therefore Class A uses one deterministic child commit K2:

```text
K1
└─ K2 metadata-only
   - R2
   - R1 supersession record if applicable
   - exact Gate-generation metadata needed for R2
```

Frozen K2 invariants:

```text
parent(K2) == K1
K2 delta == exact deterministic OperationMetadataProjection
no ReviewedArtifact/domain result delta
no AuthorizedTransitionProjection
one parent only
```

K2 does **not** require another Review Receipt. R2 itself authorizes the deterministic metadata projection required to record R2/supersession around the already-reviewed K1.

This is the recursion cutoff.

## 7. K2 proof and mismatch

K2 is locally committed before push and receives exact post-commit proof:

```text
parent equality
metadata content/hash equality
complete delta scope equality
no domain/transition delta
branch/lineage still exact
K1 still in history unchanged
```

If K2 differs from the expected deterministic metadata projection because of hooks/filters/interference:

```text
reconcile required
no Class-A-on-K2
no R3 just to authorize K2
no push
```

The adoption path terminates rather than creating metadata authorization recursion.

## 8. Push topology

Only after K2 proof passes:

```text
push exact authorized K2 commit ID
to the pinned destination branch

refspec = <exact K2 commit ID>:refs/heads/<full branch name>
never forced
```

Publication authority names exactly K2. The lineage that reaches the destination includes K1 because K1 is K2's exact parent — proven locally before the push, not asserted by pushing a branch. A branch-tip push is not a permitted expression of this and is rejected by the live primitive.

The push stage binds the exact lineage `... -> K1 -> K2` and the configured destination. Before push, recheck:

- branch ref unchanged;
- HEAD exactly expected K2 or positively allowed descendant under the specific operation contract;
- K1 object and K2 parent relationship unchanged;
- Review generation/R2 still latest valid authorization;
- destination pin unchanged;
- push dry-run safe.

A changed ref/lineage invalidates adoption and reconciles; no amend/reset/rebase is attempted.

## 9. Failure windows

Frozen recovery behavior:

```text
K1 exists / C2 Review incomplete
-> resume Review of exact K1; never push

R2 decided / K2 not committed
-> replay deterministic metadata stage/commit

K2 committed / proof not durable or not passed
-> re-prove exact K2; never push first

K2 proved / push failed
-> resume same push after latest-authorization/lineage/destination recheck

K1 became remote before R2/K2 normal publication
-> no longer normal Class A; reconcile/historical-publication handling

K1 or branch rewritten at any point
-> reconcile
```

## 10. Complete delta proof

Class A eligibility and K2 proof require complete commit delta, not rename heuristics or merely `commit_touches()` on a preselected list.

The frozen requirement is unchanged:

```text
complete parent->commit tree-entry proof required
(path AND mode AND object type/object ID)
```

If complete enumeration cannot be obtained, Class A is unavailable and the operation reconciles rather than falling back to partial path evidence.

### 10.1 Implementation binding at baseline `e32a741`

Live `workline.gitcmd.commit_changes()` (`git diff-tree --no-commit-id --name-only -r -z --no-renames`) supplies complete, rename-free changed-**path** enumeration against the first parent. Re-verified: no live helper supplies mode or object identity — both `commit_changes` and the `ls-tree` helper use `--name-only`.

```text
current commit_changes() is reusable for path enumeration,
but P1 still needs plumbing for mode/object identity
```

Until that plumbing exists, the path list alone does not satisfy this section and Class A is unavailable. The safety condition is not relaxed to match what live code currently provides.

This is an implementation gap, not an architecture blocker.

## 11. Relation to normal flow

Normal Review-v1 flow should not deliberately manufacture Class A. It freezes Candidate before commit and expects K1 to match. Class A exists for operation-owned transformation/mismatch that is discovered only after actual local persistence.

If the mismatch is known before commit, make a new Candidate before committing instead.

## 12. Architecture blocker / HUMAN

Architecture blocker: `None`.

HUMAN decision: `None`.

The live commit-ID recording and exact-commit publication machinery provides the necessary foundation. P1/P3 need mode/object-identity delta plumbing and the explicit adoption stages, not a new recovery philosophy.

## 13. Round-5 live-baseline reconciliation disposition

Reconciled from readiness baseline `19bf5e71da6c7d735666e62cbe5b12ed9fffa5a9` to live baseline `e32a74192e70d3ce8aec09f1921f175ac72b2d1d`.

```text
§1     live helper inventory refreshed; exact-commit push semantics recorded
§2     ownership precondition made explicit (aligned with R5 §3.1)
§4     dry-run table replaced by exact-refspec classification plus the
       positive destination read for "!"
§8     push topology restated as exact authorized K2 commit ID
§10    safety condition retained; implementation binding for commit_changes()
```

Prohibitions unchanged: reset, rebase, force push, stale remote-tracking ref as publication evidence, ambiguous branch-tip push.

Architecture reopen: `No`. Candidate 8: `No`.