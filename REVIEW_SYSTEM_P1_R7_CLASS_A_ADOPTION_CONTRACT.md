# Review System P1 — R7 Class A `adopt_existing_local_commit` Contract Freeze

Status: CONTRACT FROZEN / IMPLEMENTATION NOT STARTED

This checkpoint freezes the recovery contract for an operation-owned local commit that already exists but does not match the previously authorized Candidate. It is non-normative until implemented and activated through canonical authority.

## 1. Live facts inspected

The current Mutation Controller records the exact commit object ID it made when it can prove that the new HEAD is a one-parent child of the pre-commit HEAD. Later resume recognizes that commit by object ID/history rather than message.

Current Git helpers can already prove:

- current branch/full ref;
- HEAD commit;
- commit parents;
- ancestry;
- paths touched between commits;
- pinned push destination;
- what a real push would do via `git push --dry-run --porcelain`.

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

## 4. Remote-publication check — frozen conservative mechanism

The check must occur **while the local branch HEAD is still exactly K1 and before metadata-only K2 is created**.

Use the configured/pinned destination and the same branch/refspec as a real push. Existing `push_dry_run()` semantics provide the safe classification boundary:

```text
preview "="
-> destination is already exactly at K1
-> K1 is already published
-> NOT normal Class A adoption
-> record/report unauthorized publication or historical escape as applicable
-> reconcile/recovery path

preview "*" or fast-forward " "
-> Git says pushing current exact K1 would create/advance the destination
-> positive evidence that the configured branch tip is not already K1 and normal publication has not yet happened through this branch
-> Class A may continue

preview "!" or unknown/unanswerable
-> cannot prove safe unpublished state
-> reconcile required
```

P1 does not add a fetch/reset or remote-tracking-ref heuristic. A stale local remote-tracking ref is not publication evidence.

If future Git support can positively prove a stronger remote ancestry fact without weakening safety, that can extend this check; P1's minimum contract is the conservative dry-run classification above.

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
push branch containing K1 + K2
```

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

Implementation therefore needs Git plumbing that enumerates every parent->commit tree entry change including path/mode/object identity. If complete enumeration cannot be obtained, Class A is unavailable and the operation reconciles rather than falling back to partial path evidence.

## 11. Relation to normal flow

Normal Review-v1 flow should not deliberately manufacture Class A. It freezes Candidate before commit and expects K1 to match. Class A exists for operation-owned transformation/mismatch that is discovered only after actual local persistence.

If the mismatch is known before commit, make a new Candidate before committing instead.

## 12. Architecture blocker / HUMAN

Architecture blocker: `None`.

HUMAN decision: `None`.

The live commit-ID recording and push dry-run machinery provides the necessary foundation. P1/P3 need complete-delta plumbing and the explicit adoption stages, not a new recovery philosophy.