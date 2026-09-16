# Review System P1 — R1 Durable Layout / Loader / Bootstrap Contract Freeze

Status: CONTRACT FROZEN / REPAIRED AFTER EXTERNAL REVIEW / ROUND 2 REPAIRED / IMPLEMENTATION NOT STARTED

This is a non-normative implementation-contract checkpoint for Candidate 7 P1. Runtime authority remains `registry.md` plus registry-routed canonical Skills and live code until this contract is implemented and routed into authority.

## 1. Live facts inspected

The current Project canonical store is rooted at `.workline/`. `ProjectStore` exposes `project.yaml`, Roadmap/Phase/Work entities, `relations/roadmap.yaml`, `relations/related.yaml`, `events/events.jsonl`, and `derivations/`. `.workline/runtime/` is explicitly non-domain runtime state, not committed and not evidence.

`MutationController.write_file` already permits arbitrary safe text paths under `.workline/` except `.workline/runtime/`, so a canonical `.workline/review/` namespace can use the existing durable file effect/recovery mechanism without adding an escape from the canonical boundary.

`durable_write_text()` creates parent directories lazily, writes through `.workline/runtime/tmp/`, fsyncs the file, atomically replaces the destination, and fsyncs the parent on POSIX. Therefore empty canonical directories do not need to exist at Project initialization.

`Project開始` currently creates only the four central canonical files as mutation effects, then creates the empty entity/derivation directories outside Git and commits only owned files. Empty directories are therefore intentionally not part of clone-safe Project identity.

The pre-project residue check accepts only runtime mutation residue before the first Project-start effect. A pre-existing `.workline/review/` before Project establishment must remain invalid residue rather than being guessed as owned.

Full Project validation currently validates `project.yaml`, supported topology, then `ProjectView` entity/relation/event structure. Review metadata is not part of `ProjectView` and must remain outside lifecycle truth.

## 2. Frozen P1 canonical layout

P1 adds one canonical namespace, created lazily on first Review write:

```text
.workline/
└─ review/
   ├─ gates/
   │  └─ <review_run_id>/
   │     └─ <generation:06d>.yaml
   ├─ receipts/
   │  └─ <receipt_id>.yaml
   ├─ consumptions/
   │  └─ <consumption_id>.yaml
   ├─ supersessions/
   │  └─ <superseded_receipt_id>.yaml
   ├─ candidate-snapshots/
   │  └─ <candidate_hash>.yaml
   ├─ task-inputs/
   │  └─ <review_task_id>.yaml
   └─ activation/
      └─ work-terminal-v1.yaml
```

P1 does **not** create or require empty `.workline/review/` directories during Project開始. They appear through ordinary mutation effects when the first canonical Review record is persisted.

This avoids meaningless empty-directory bootstrap/backfill work and matches the existing Project layout convention that only files, not empty directories, are clone-safe state.

`candidate-snapshots/` and `task-inputs/` are clone-safe Review provenance needed to reconstruct accepted tasks after runtime loss. `activation/work-terminal-v1.yaml` is introduced only at P3 activation and classifies pre-activation legacy terminal history versus post-activation review-v1 terminal events. None is lifecycle truth.

## 3. Runtime layout remains separate

The following is allowed for ephemeral execution material only:

```text
.workline/runtime/review/
```

Subdirectories may hold candidate scratch data, raw reviewer reports, temporary adapter output, provider job handles, or learning scratch material, but:

```text
runtime Review data
!= canonical Review gate truth
!= evidence by itself
!= authorization
!= sole task reconstruction material
```

A clone or runtime cleanup may remove it. Anything required to decide whether an authorization is currently consumable or to reconstruct an accepted task must be reconstructible from `.workline/review/` canonical records plus canonical Project/Git state.

## 4. Gate generation files

A Review Run owns an ordered immutable sequence:

```text
.workline/review/gates/<review_run_id>/000001.yaml
.workline/review/gates/<review_run_id>/000002.yaml
...
```

Rules:

- generation numbers start at 1 and increase exactly by one;
- filename is zero-padded decimal and must equal the record's `generation`;
- every generation after 1 names its exact predecessor generation and predecessor digest;
- a generation file is immutable once committed;
- a later generation is what changes Review gate state; an earlier file is never edited in place;
- the effective latest generation is obtained only after validating the full contiguous chain for that run;
- a missing number, duplicate semantic generation, bad predecessor, unknown field version, unreadable file, or conflicting chain is fail-closed / reconcile required.

Predecessor digest is frozen as:

```text
SHA-256(versioned canonical UTF-8 serialization bytes)
```

Canonical Review rendering uses UTF-8 and LF line endings. The digest is over those canonical bytes, not over an in-memory mapping and not over a post-filter Git blob. Git persistence proof separately proves the committed path reproduces those bytes under the Git semantics bound by R6.

Candidate 7's conceptual `superseded` generation state is represented by the existence of a later valid generation in the chain rather than rewriting immutable old files. Stored generation terminal state is `open` or `sealed_authorized`; supersession is derived from the validated chain.

## 5. Receipt / Consumption / supersession files

Receipt:

```text
.workline/review/receipts/<receipt_id>.yaml
```

Consumption:

```text
.workline/review/consumptions/<consumption_id>.yaml
```

Supersession:

```text
.workline/review/supersessions/<superseded_receipt_id>.yaml
```

All are immutable. Receipt existence alone is never lifecycle truth and never equals Consumption. Logical Consumption uniqueness/totality is R4 responsibility.

## 6. Candidate snapshot and task-input provenance

Accepted task launch requires clone-safe reconstruction material.

Canonical snapshot path:

```text
.workline/review/candidate-snapshots/<candidate_hash>.yaml
```

Canonical task-input path:

```text
.workline/review/task-inputs/<review_task_id>.yaml
```

Both use the same immutable create-only/no-follow/Git-committability contract as other Review records.

Candidate snapshot records exact ReviewedArtifactProjection reconstruction material, or a deterministic builder identity plus all clone-safe inputs sufficient to recreate the identical projection. A digest alone is never treated as reconstruction material.

Task-input binds the exact versioned request envelope, request digest, task/reviewer/adapter identity+version, candidate reference/reconstruction mode, Review Context, Effective Policy, and accepted generation.

If clone/runtime loss leaves insufficient material to reconstruct the exact request/Candidate, fail closed; do not silently create a replacement task identity.

## 7. Work-terminal activation record

P3 introduces one immutable activation record:

```text
.workline/review/activation/work-terminal-v1.yaml
```

It binds at minimum:

```text
operation_contract = review-v1
legacy_event_count
legacy_event_prefix_sha256
activation_base_head
```

The prefix digest is over the exact canonical first N bytes/records of `events/events.jsonl` according to the versioned activation serializer contract. The activation record is committed/proven before the first review-v1 `work_completed` event is allowed.

The activation record is Review/operation consistency metadata only. `ProjectView/state.py` must not derive lifecycle or selection from it.

## 8. Immutable create-only writer contract

Gate generation, Receipt, Consumption, supersession, Candidate snapshot, task-input and activation records use a Review-safe immutable create primitive/validation mode.

Frozen behavior:

```text
target absent -> create exact canonical bytes
exact same bytes -> MATCHING / idempotent replay
different bytes/content/type -> reconcile_required
existing immutable Review object + generic update/base semantics -> mechanically forbidden
```

## 9. Write-time containment / no-follow contract

Immediately before a canonical Review create is physically applied, the writer positively proves containment from Project root through `.workline/review` to the target parent using lstat/no-follow semantics. Every existing component must be the expected in-Project plain directory. Symlink, junction, reparse point, unexpected indirection, or unprovable identity is refused.

The target parent identity is rechecked at the final create/replace boundary so TOCTOU cannot redirect Review bytes outside the Project.

## 10. Loader boundary

P1 adds dedicated `ReviewStore` rather than teaching `ProjectView` to load Review state.

`ReviewStore` owns canonical Review paths, record parsing/version checks, filename/ID/generation consistency, immutable shape validation, gate-chain validation, Receipt/Consumption/supersession lookup, candidate/task provenance lookup, activation lookup, canonical rendering and predecessor digest calculation.

`ProjectView` / `state.py` MUST NOT read Review records to derive Work/Phase/Roadmap lifecycle or progression.

## 11. Project validation boundary

`validate_project()` gains a Review structural validation pass outside `ProjectView`.

Projects with no `.workline/review/` remain structurally valid. Absence of Review records alone does not classify a Work terminal event as legacy after review-v1 activation has occurred; P3 activation record + event classification owns that distinction.

Unknown entries, symlink/reparse indirection where a plain file/directory is required, malformed records, non-contiguous generation chains, duplicate logical IDs, conflicting immutable facts, malformed provenance, or contradictory activation state fail closed.

## 12. Project開始 / bootstrap contract

No placeholder/manifest is created solely to track empty Review directories. Existing Projects become Review-capable lazily. Pre-existing `.workline/review/` in a not-yet-established target remains partial/unknown state and is not adopted by guess.

## 13. Git committability preflight

Before the first canonical Review effect of a mutation is recorded/applied, every Review path that operation expects to commit must be checked with Git's own ignore/exclude evaluation. Ignored or unanswerable committability STOPs before canonical Review effects. Workline never edits ignore/exclude configuration to make Review paths committable.

## 14. Future extension boundary

P5 may add further history under `.workline/review/`; P6/P7 may add policy records. Those extensions must preserve this canonical-vs-runtime, immutable-writer, no-hidden-authority boundary.

## 15. Round-2 repair disposition

Round 2 adds:

- clone-safe Candidate snapshot / task-input provenance;
- P3 work-terminal activation marker path/role;
- explicit statement that those records use the same immutable/no-follow/Git preflight rules.

Architecture blocker: `None`.

HUMAN decision: `None`.
