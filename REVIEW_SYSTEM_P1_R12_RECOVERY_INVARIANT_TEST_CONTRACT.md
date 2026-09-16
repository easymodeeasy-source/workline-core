# Review System P1 — R12 Recovery / Invariant Test Contract Freeze

Status: CONTRACT FROZEN / ROUND 4 REPAIRED / IMPLEMENTATION NOT STARTED

This checkpoint freezes the minimum interruption/invariant test matrix required before Review contracts may activate.

## 1. Test philosophy

Every critical boundary needs:

```text
A. happy path
B. crash after each durable boundary
C. conflicting external/local change before resume
```

Assertions cover both what happened exactly once and what must not have happened yet, especially push/publication, terminal lifecycle, duplicate Review records, task/generation forks and executor rerun.

## 2. R1 immutable writer / layout / committability

Required:

- no `.workline/review/` Project validates;
- first Review write lazily creates exact records;
- runtime Review data never satisfies canonical lookup;
- malformed path/record/reparse fails;
- exact immutable bytes replay -> MATCHING;
- different bytes same immutable path -> reconcile;
- update/base semantics -> mechanically rejected;
- ignored/excluded Review path -> STOP before canonical effect;
- validation-pass then parent replaced by symlink/junction/reparse -> STOP/reconcile and no outside write;
- canonical UTF-8/LF renderer has stable SHA-256 predecessor digest;
- clone reproduces canonical bytes/digest.

## 3. R2/R3 same-run generation recovery

Mandatory cases:

### Zero-effect crash

```text
latest N
-> open N+1 mutation with exact path + same-run serialization token in initial scope
-> intent durable
-> no effect applied
-> crash
-> second invocation
```

Expected: first pending mutation resumes/refuses; no second N+1/fork.

### Physical-create / flag-save crash

```text
G(N+1) immutable physical create succeeds
-> crash before effect.applied save
-> chain visibly includes N+1
-> second invocation would otherwise calculate N+2
```

Expected:

- pending same-run mutation discovered before new generation calculation;
- stable serialization token overlaps hypothetical later generation scope;
- first mutation resumes/classifies N+1 MATCHING;
- no N+2 mutation intent/file until first mutation settles.

Also test multiple/conflicting pending same-run generation mutations -> reconcile.

## 4. Clone-safe accepted task material

Before launch, canonical Candidate snapshot/builder data + task-input + accepted Gate generation must be committed as required.

Test fresh clone/runtime deletion reconstructs exact Candidate + request, recomputes matching hashes and reruns/retrieves same `task_id`.

Negative cases include snapshot missing/digest mismatch, builder unavailable/version drift, required input missing, adapter/reviewer version unavailable and request digest mismatch. All fail closed and never silently allocate a new task ID.

### Review-provenance reuse identity

Mandatory Round-4 HEAD-advancement cases:

```text
A. candidate_hash unchanged
   candidate snapshot canonical bytes changed
   -> candidate_material_digest changes
   -> prior Evidence/Review reuse rejected

B. request_digest unchanged
   task-input canonical bytes changed in other bound provenance
   -> task_input_digest changes
   -> prior Evidence/Review reuse rejected

C. deterministic builder output unchanged
   builder version changes
   -> provenance identity changes
   -> prior Evidence/Review reuse rejected

D. deterministic builder output unchanged
   one clone-safe builder input reference/identity changes
   -> provenance identity changes
   -> prior Evidence/Review reuse rejected
```

Positive control:

```text
candidate_hash/request_digest/provenance digests/builder identities all unchanged
AND complete R6/R11 closure proves all other material surfaces unchanged
-> provenance alone does not force reacquisition
```

No test may treat equal `candidate_hash` as sufficient when `candidate_material_digest` or `task_input_digest` differs.

## 5. Gate settlement / seal / invalidation

Cover accepted task unsettled after crash, result arrival before canonical settlement, G2 partial write/flag save, seal+Receipt partial stage, and invalidating G5+supersession partial stage. No seal/consumption relies on runtime-only success.

## 6. R4 terminal uniqueness / totality / activation

P3 tests include:

```text
review-v1 E1 + matching C1 -> valid
review-v1 E1 only + matching pending terminal stage -> recoverable transient
review-v1 E1 only + no matching pending stage -> invalid/reconcile
C1 only without matching pending transition -> invalid/reconcile
conflicting second C -> fail closed
```

### Activation classification / digest-v1

Mandatory representation-stability cases:

1. Create valid legacy `events.jsonl` using CRLF and inserted blank physical lines.
2. Parse through canonical Event reader.
3. Create activation record using `work-terminal-activation-digest-v1`.
4. Append first post-activation review-v1 event through normal event append/rewrite path.
5. Re-read after representation normalization.
6. Expected: first-N canonical parsed Event digest remains identical and activation stays valid.

Mutation-detection cases:

```text
change one historical Event field
reorder historical Event records
delete/insert historical Event record
change allowed historical metadata field
```

Expected: activation prefix digest mismatch -> reconcile.

Blank-line placement and CRLF-vs-LF changes alone must not change activation digest.

Serializer-specific tests freeze:

- parsed nonblank Event record count semantics;
- canonical JSON key ordering;
- no insignificant JSON whitespace;
- UTF-8 / non-ASCII preservation;
- exactly one LF per canonical Event line;
- preservation of every schema-allowed field;
- unknown/unparseable field fails closed rather than being dropped.

Classification cases:

- valid activation + valid prefix -> first N legacy;
- post-activation review-v1 marker + matching C1 -> valid;
- post-activation marker missing -> reconcile;
- unknown marker -> reconcile;
- contradictory marker/run/Receipt -> reconcile;
- activation prefix mismatch -> reconcile;
- explicit review-v1 event without valid activation -> reconcile;
- Review Event metadata does not change `ProjectView/state.py` lifecycle.

## 7. R5 K1/K2 identity / proof / push

Cover commit effect not made, made+ID save interrupted, positive reconstruction/backfill, wrong message/tree/parent/mode/link/gitlink, extra commit, unanswerable Git query, proof fail/pass, push failure/resume, K1 remote while Work non-terminal, and K2 terminal proof.

No push/publication before exact proof.

## 8. Complete commit-local external-process guard

Mandatory Review-v1 tests cover all reachable external process classes for the exact staging/local-commit path, not only hooks/filters.

### Hooks

- active `pre-commit`, `prepare-commit-msg`, `commit-msg`, `post-commit` attempting network/push/file side effect;
- non-default `core.hooksPath`;
- hook identity change between Candidate proof and commit.

Expected: uncontained side effect -> STOP/fail closed before commit. If mechanically suppressed, suppression mode is bound in Git semantics identity.

### Filters/process/LFS

- applicable clean/process filter attempts external service/network access;
- LFS clean/process path where selected by attributes;
- content-defining filter cannot be safely contained.

Expected: contained with bound identity or fail closed; content-defining filter is never silently disabled merely for safety.

### Commit signing

Mandatory case:

```text
git config commit.gpgSign true
configure custom signing program/helper that would create external/network side effect
invoke Review-v1 commit_local-v1
```

Expected:

```text
commit_local explicitly disables signing (`--no-gpg-sign` equivalent)
-> signer is not invoked
-> no signer-visible external/network side effect occurs
-> resulting commit enters normal exact K proof
```

Also test that `Review-v1 signing-disabled` is present in bound R6/R11 Git semantics identity. If a test fixture removes/changes that contract mode, reuse/proof identity must change/fail as specified.

### Reachability discrimination

Prove that configuration for helpers not reachable by the exact add/commit path does not cause false execution, while a configuration that makes an external helper reachable enters the classified surface.

## 9. R6 HEAD advancement / evidence closure

Cover unrelated proven-disjoint advancement, material context/evidence/Git/tool changes, merges, changed-then-reverted dependencies, unknown completeness, rewritten base and non-repo identity drift. Path non-conflict alone never proves Review validity.

Include changes to:

```text
candidate_material_digest
task_input_digest
builder identity/version/input identities
commit signing mode
reachable signing/helper configuration
hook suppression/containment mode
applicable filter execution identity
```

Expected: changed material Review provenance or Git semantics invalidates reuse unless explicitly proven irrelevant under the versioned contract.

## 10. R7 Class A

Cover positive operation-owned transformed K1, non-owned/unexpected delta, multi-parent, lineage drift, already-published remote K1, metadata-only K2 mismatch, no recursive Receipt chain and failure after K2 before push.

## 11. R8/R9 semantic round-trip

Roadmap and Phase-entry tests cover exact reserved IDs, canonical reload, generated integration/confirmation edges and fault injection. R9 review-v1 self-selection is enforced by Roadmap-owned planning precondition, not adapter-only override.

## 12. R10/R11

Policy adapter harness remains generic only. Evidence tests cover observed/pinned/denied/unknown dependency classes, dynamic/subprocess/network/env/cache/tool/runtime cases, with unknown preventing cross-Candidate reuse.

Review-provenance tests bind Candidate snapshot/task-input/builder identities separately from result hashes. Git-state evidence binds signing-disabled mode and any reachable external commit helper together with relevant subprocess/network/external-service dependency coverage.

## 13. Authority boundary

Mechanical tests prove:

- Review metadata cannot change Work/Phase/Roadmap lifecycle;
- Roadmap/START remain transition owners;
- same-run generation pending conflict survives process crash;
- foreign Project context cannot mutate Review state;
- active writer receives ordinary Project lock refusal;
- activation/event metadata is used only by Review/operation consistency validation.

## 14. Activation gates

P1 common infrastructure is not complete until repaired common tests pass. P2 additionally requires R8/R9. P3 additionally requires full R4/R5/R7 terminal/activation/commit/proof/push matrix.

Happy path alone is insufficient.

## 15. Round-4 repair disposition

This revision adds explicit tests for the remaining provenance-reuse seam while retaining the already-frozen Round-3 activation serializer and commit-signing/external-process tests.

Architecture blocker: `None`.

HUMAN decision: `None`.
