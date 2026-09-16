# Review System P1 — R1 Durable Layout / Loader / Bootstrap Contract Freeze

Status: CONTRACT FROZEN / IMPLEMENTATION NOT STARTED

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
   └─ supersessions/
      └─ <superseded_receipt_id>.yaml
```

P1 does **not** create or require empty `.workline/review/` directories during Project開始. They appear through ordinary mutation `write_file` effects when the first canonical Review record is persisted.

This avoids meaningless empty-directory bootstrap/backfill work and matches the existing Project layout convention that only files, not empty directories, are clone-safe state.

## 3. Runtime layout remains separate

The following is allowed for ephemeral execution material only:

```text
.workline/runtime/review/
```

Subdirectories may hold candidate scratch data, raw reviewer reports, temporary adapter output, or learning scratch material, but:

```text
runtime Review data
!= canonical Review gate truth
!= evidence by itself
!= authorization
```

A clone or runtime cleanup may remove it. Anything required to decide whether an authorization is currently consumable must be reconstructible from `.workline/review/` canonical records plus canonical Project/Git state.

Open Review work may need to re-run an adapter/reviewer after clone if only its scratch/raw body was runtime-resident. That is acceptable and fail-closed. A sealed authorization may never depend on an unavailable runtime-only fact.

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

Candidate 7's conceptual `superseded` generation state is represented by the existence of a later valid generation in the chain rather than rewriting an immutable older generation. Stored generation terminal state is therefore `open` or `sealed_authorized`; supersession is derived from the validated chain.

## 5. Receipt files

```text
.workline/review/receipts/<receipt_id>.yaml
```

Each Receipt is immutable, one file per stable Receipt ID. Filename and in-record ID must match exactly. A Receipt binds one `sealed_authorized` generation and its Candidate/Context/Policy/Coverage/Adjudication/obligation identities.

Receipt existence alone is never lifecycle truth and never equals consumption.

## 6. Consumption files

```text
.workline/review/consumptions/<consumption_id>.yaml
```

Each Consumption is immutable and references one Receipt plus kind-specific persisted-result/transition identity. Its logical uniqueness is validated separately; path uniqueness alone is insufficient. R4 freezes those cardinality rules.

## 7. Supersession files

```text
.workline/review/supersessions/<superseded_receipt_id>.yaml
```

A supersession record is immutable and keyed by the Receipt it invalidates. The record contains at minimum:

```yaml
superseded_receipt_id: ...
superseded_by_receipt_id: ...   # nullable only where the replacement is not yet issued but invalidation is durable
review_run_id: ...
from_generation: ...
to_generation: ...
reason_code: ...
```

Only one canonical supersession file may exist for a Receipt. Exact matching replay is idempotent; different content at the same path is reconcile required.

This file is Review authorization metadata, not a lifecycle event.

## 8. Loader boundary

P1 adds a dedicated `ReviewStore` (module location may be chosen during implementation, but responsibility is frozen) rather than teaching `ProjectView` to load Review state.

`ReviewStore` owns:

- canonical Review paths;
- YAML record parsing/version checks;
- filename/ID/generation consistency;
- immutable-record shape validation;
- gate-chain validation and latest-generation lookup;
- Receipt lookup;
- Consumption lookup/cardinality indexes;
- supersession lookup;
- canonical rendering for expected write effects.

`ProjectView` / `state.py` MUST NOT read Review files to derive Work/Phase/Roadmap lifecycle or progression.

## 9. Project validation boundary

`validate_project()` gains a Review structural validation pass **outside** `ProjectView`:

```text
validate_project_yaml
+ self-hosting validation
+ ProjectView / domain structure validation
+ ReviewStore structural validation (when review namespace exists)
```

Legacy/P1-not-yet-used Projects with no `.workline/review/` remain structurally valid. Absence of Review records does not itself mean `legacy` or `review-v1`; operation-contract identity is handled in P3.

If `.workline/review/` exists, unknown entries, symlink/reparse indirection where a plain canonical file/directory is required, malformed records, non-contiguous generation chains, duplicate logical IDs, or conflicting immutable facts fail validation.

Review validation reports problems; it never repairs.

## 10. Project開始 / bootstrap contract

Frozen decision:

- do **not** add a placeholder/manifest solely to track an empty Review directory;
- do **not** require Project開始 to backfill `.workline/review/`;
- do **not** treat `.workline/runtime/review/` as canonical state;
- preserve Project開始's existing pre-effect residue rule: any pre-existing `.workline/review/` in a not-yet-established target is partial/unknown canonical state and is not adopted by guess;
- existing established Projects become Review-capable lazily when the first Review operation writes canonical Review records under the normal Project lock/mutation contract.

## 11. Git contract

Every canonical Review write path is explicit in `WriteScope.files` and in the exact Git commit path list. Existing Mutation validation already forbids committing `.workline/runtime/**`; that rule remains.

Review directories/files are not managed through `.gitignore` mutation. Workline continues not to edit Project ignore configuration.

## 12. Future extension boundary

P5 may add full history under additional `.workline/review/` subtrees (runs/findings/repairs/causality/evidence/patch notes). Those future records must not change the P1 meaning of gates, Receipts, Consumptions, or supersessions and must not become lifecycle truth.

P6/P7 may add policy records. They use the same canonical-vs-runtime boundary but are not pre-invented in P1.

## 13. Architecture blocker / HUMAN

Architecture blocker: `None`.

HUMAN decision: `None`.

The live store, durable writer, Mutation write boundary, Project-start layout, and validation architecture support this contract without changing Candidate 7 authority/lifecycle boundaries.
