# Review System P1 — R2 Review IDs / Reservation Contract Freeze

Status: CONTRACT FROZEN / ROUND 2 REPAIRED / IMPLEMENTATION NOT STARTED

This is a non-normative P1 contract checkpoint under Candidate 7. Runtime authority remains `registry.md` plus registry-routed canonical Skills and live code until implementation activates this contract.

## 1. Stable Review ID kinds

P1 adds exactly:

```text
review_run         -> rr
review_receipt     -> rcp
review_consumption -> rcs
review_task        -> rtk
```

All extend central `ids.py` / `Mutation.reserve_id()` semantics. Review does not create a separate generator.

Generation itself is a positive integer scoped to one Review Run. Candidate/Context/Policy/Coverage/Adjudication/obligation identities are digests/content identities rather than allocated ULIDs.

## 2. Reservation ownership

```text
review-run:<review_kind>:<target_identity>
review-receipt:<review_run_id>:<generation>
review-consumption:<receipt_id>
review-task:<review_run_id>:<task-slot>
```

Reservation keys are deterministic and replay-stable. Callback-side random IDs are never adopted later into canonical state.

## 3. Generation numbering

Next generation derives only from the validated immutable chain:

```text
none -> 1
latest N -> N+1
```

Project lock alone is not serialization because a crash releases it.

## 4. Round-2 same-run serialization contract

For every generation mutation, the initial `WriteScope.files` contains both:

```text
.workline/review/gates/<review_run_id>/<generation:06d>.yaml
.workline/review/gates/<review_run_id>/.generation-serialization
```

The second path is a **scope-only conflict token**. No file is created at that path, it is never committed, and it is never Review truth. It exists only inside pending Mutation scope so any unfinished generation mutation for the same Review Run mechanically overlaps any later attempt, even if the physical generation file already appeared before an `applied` flag was saved and a new invocation would otherwise calculate N+2.

Before calculating any new generation, the owner inspects pending generation mutations for the same `review_run_id`:

```text
exactly one -> resume/reconcile it first
more than one/conflicting -> reconcile_required
none -> validate chain and calculate next generation
```

Thus `extend_scope()` is not the safety mechanism, and the next-generation path alone is not treated as sufficient after partial physical application.

## 5. Task ID versus clone-safe task material

`rtk_*` is only stable task identity. R3/R1 require clone-safe canonical task-input/Candidate reconstruction material before launch. A task ID or digest alone does not satisfy rerun/retrieval requirements after `.workline/runtime/**` loss.

A later clone resumes the same logical accepted task only when canonical task input reconstructs an exact request/Candidate whose digests and bound adapter identities match the accepted record. It never silently allocates a replacement task ID for missing accepted material.

## 6. Validation

Central ID functions and `ReviewStore` enforce filename/content kind and identity consistency. Unknown Review prefixes are not mapped by guess. Generation filenames are validated as integers separately from `kind_of()`.

## 7. Architecture/HUMAN

Architecture blocker: `None`.

HUMAN decision: `None`.
