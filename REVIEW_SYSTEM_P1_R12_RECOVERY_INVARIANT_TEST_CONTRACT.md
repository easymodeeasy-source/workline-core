# Review System P1 — R12 Recovery / Invariant Test Contract Freeze

Status: CONTRACT FROZEN / ROUND 2 REPAIRED / IMPLEMENTATION NOT STARTED

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
-> chain now visibly includes N+1
-> second invocation would otherwise calculate N+2
```

Expected:

- pending same-run mutation is discovered before new generation calculation;
- stable `.generation-serialization` scope token causes same-run overlap;
- first mutation resumes/classifies N+1 MATCHING;
- no N+2 mutation intent/file is created until first mutation settles.

Also test multiple/conflicting pending same-run generation mutations -> reconcile.

## 4. Clone-safe accepted task material

Before launch, canonical Candidate snapshot/builder data + task-input + accepted Gate generation must be committed as required.

Test:

```text
accepted task committed
-> remove `.workline/runtime/**` or fresh clone
-> load task input
-> reconstruct exact Candidate + request
-> recompute matching candidate_hash/request_digest
-> same task_id is retrieved/rerun
```

Negative cases:

- candidate snapshot missing;
- snapshot content digest mismatch;
- deterministic builder unavailable/version drift;
- required builder input missing;
- adapter/reviewer version unavailable;
- reconstructed request digest differs.

All negatives fail closed/reconcile and MUST NOT silently allocate a new task ID.

Provider job handle loss alone is not authority loss when canonical reconstruction material is complete.

## 5. Gate settlement / seal / invalidation

Cover accepted task unsettled after crash, result arrival before canonical settlement, G2 partial write/flag save, seal+Receipt partial stage, and invalidating G5+supersession partial stage. No seal/consumption can rely on runtime-only success.

## 6. R4 terminal uniqueness / totality / activation

P3 tests include:

```text
review-v1 E1 + matching C1 -> valid
review-v1 E1 only + matching pending terminal stage -> recoverable transient
review-v1 E1 only + no matching pending stage -> invalid/reconcile
C1 only without matching pending transition -> invalid/reconcile
conflicting second C -> fail closed
```

Activation classification tests:

1. valid activation record + exact legacy event prefix count/digest -> first N events accepted as pre-activation legacy;
2. post-activation `work_completed` with explicit `operation_contract=review-v1` + valid C1 -> valid;
3. post-activation `work_completed` missing marker -> reconcile, never legacy fallback;
4. unknown marker -> reconcile;
5. marker contradicts activation/run/Receipt binding -> reconcile;
6. activation prefix count/digest mismatch -> reconcile;
7. explicit review-v1 terminal marker without valid activation record -> contradictory/reconcile;
8. adding Review metadata to Event does not change `ProjectView/state.py` lifecycle result.

## 7. R5 K1/K2 identity / proof / push

Cover commit effect not made, made+ID save interrupted, positive reconstruction/backfill, wrong message/tree/parent/mode/link/gitlink, extra commit, unanswerable Git query, proof fail/pass, push failure/resume, K1 remote while Work non-terminal, and K2 terminal proof.

No push/publication before exact proof.

## 8. Hooks / filters external-side-effect guard

Mandatory Review-v1 tests:

- active post-commit hook attempts `git push`/network side effect before proof;
- applicable clean/process filter attempts external network/service access;
- hook/filter identity changes between Candidate proof and commit.

Expected:

```text
uncontained external side effect
-> STOP/fail closed before reviewed publication boundary
-> remote ref/service-visible state does not change
```

If hooks are mechanically suppressed, test that suppression is part of bound Git persistence semantics. If a content-defining filter cannot be safely contained, commit_local must not silently disable it; it fails closed.

## 9. R6 HEAD advancement / evidence closure

Cover unrelated proven-disjoint advancement, material context/evidence/Git/tool changes, merges, changed-then-reverted dependencies, unknown completeness, rewritten base and non-repo identity drift. Path non-conflict alone never proves Review validity.

## 10. R7 Class A

Cover positive operation-owned transformed K1, non-owned/unexpected delta, multi-parent, lineage drift, already-published remote K1, metadata-only K2 mismatch, no recursive Receipt chain and failure after K2 before push.

## 11. R8/R9 semantic round-trip

Roadmap and Phase-entry tests cover exact reserved IDs, canonical reload, generated integration/confirmation edges and fault injection. R9 review-v1 self-selection must be enforced by Roadmap-owned planning precondition, not adapter-only override.

## 12. R10/R11

Policy adapter harness remains generic only. Evidence tests cover observed/pinned/denied/unknown dependency classes, dynamic/subprocess/network/env/cache/tool/runtime cases, with unknown preventing cross-Candidate reuse.

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

## 15. Round-2 repair disposition

This revision adds explicit coverage for:

- P1R-01 physical-create / flag-save generation fork window;
- P1R-02 fresh-clone exact Candidate/request reconstruction and same-task rerun;
- P1R-03 legacy/review-v1 activation classification and malformed-marker fail-closed;
- P1R-04 hook/filter external-side-effect prevention.

Architecture blocker: `None`.

HUMAN decision: `None`.
