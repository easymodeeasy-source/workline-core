# Review System P1 — Contract Repair Round 2

Status: SECOND REPAIR FROZEN / IMPLEMENTATION NOT STARTED

This non-normative checkpoint records the second independent Implementation Readiness review after the first P1 contract repair. Candidate 7 architecture remains retained; Candidate 8 is not created.

Runtime authority remains `registry.md`, registry-routed canonical Skills and live code until implementation/activation.

## 1. Review disposition

The second independent review found:

```text
F1 K1 identity crash recovery       RESOLVED
F2 generation serialization         PARTIAL -> P1R-01
F3 write-time no-follow safety      RESOLVED
F4 clone-safe async task            PARTIAL -> P1R-02
F5 immutable create-only            RESOLVED
F6 Consumption totality             PARTIAL -> P1R-03
F7 Roadmap authority ownership      RESOLVED
F8 Git committability preflight     RESOLVED
F9 predecessor digest exactness     RESOLVED

Architecture blockers: None
HUMAN decisions: None
Verdict: REPAIR
```

The three MID findings are accepted. The LOW improvement P1R-04 is also accepted now so it cannot become an avoidable implementation ambiguity later.

## 2. P1R-01 — same-run generation recovery after physical create / flag-save crash

The previous exact-next-generation-path conflict rule is insufficient once `G(N+1)` physically exists but its mutation still remains pending.

Frozen repair:

Every mutation that may create/settle/seal/invalidate a generation for one `review_run_id` declares **both** of these in its initial `WriteScope.files` before effects are recorded:

```text
1. exact generation file path
   .workline/review/gates/<review_run_id>/<generation:06d>.yaml

2. stable same-run serialization scope token
   .workline/review/gates/<review_run_id>/.generation-serialization
```

The serialization token is scope-only. It is never physically created, committed or treated as Review data. Its only purpose is to make all pending generation mutations of the same run overlap mechanically even when one invocation sees N+1 already present and would otherwise calculate N+2.

Additionally, before calculating a new generation number, the owning operation must inspect pending Review mutations for that `review_run_id`:

```text
one matching pending generation mutation
-> resume/reconcile it before allocating another generation

multiple/conflicting pending same-run generation mutations
-> reconcile_required

none
-> validate chain and allocate next generation
```

Therefore:

```text
G(N+1) physical create succeeds
-> crash before effect.applied save
-> next invocation sees file G(N+1)
```

cannot open G(N+2): the stable same-run scope token conflicts with the pending first mutation, and pending-run discovery requires the first mutation to settle first.

The scope-only token is not an authority record and does not survive by itself; cross-crash authority is still the pending Mutation record containing it.

## 3. P1R-02 — exact clone-safe task input / Candidate reconstruction material

A task ID plus hashes is identity evidence, not reconstruction material. An accepted task may not launch until the exact request/Candidate material needed to retrieve or rerun it is clone-safe.

P1 adds immutable provenance records:

```text
.workline/review/candidate-snapshots/<candidate_hash>.yaml
.workline/review/task-inputs/<review_task_id>.yaml
```

Both use R1 immutable create-only/no-follow/Git-committability rules and are Review provenance only, never lifecycle/progression truth.

### Candidate snapshot v1

For an arbitrary Work Candidate that cannot be deterministically regenerated solely from already-clone-safe canonical inputs, the snapshot records the exact `ReviewedArtifactProjection` sufficient to reconstruct it. The versioned manifest binds at least:

```text
candidate_hash
candidate_base_commit
projection_version
ordered normalized entries
  path
  object kind: blob | symlink | gitlink | deletion
  Git mode
  content SHA-256
  exact content bytes encoded canonically when needed
  gitlink object id when applicable
Git persistence semantics identity required by R6
```

Binary content is represented by versioned canonical base64 bytes or an equivalently exact content-addressed representation whose complete bytes are canonical and clone-safe.

Where a Candidate is fully reproducible from a deterministic builder instead of snapshot bytes, the task input may use `builder_v1` only when it binds the exact builder identity/version and **all** clone-safe inputs needed to regenerate the identical projection. Unknown/missing input forces fail closed; hashes alone are not a builder.

### Task input v1

Before accepted-task generation is committed and before the external task launches, immutable task input binds:

```text
task_id
task_slot
task_kind
reviewer_or_adapter_identity + version
exact versioned request envelope
request_digest
candidate_hash
candidate material reference/reconstruction mode
review_context_hash
effective_policy_hash
accepted_generation
```

Fresh clone/runtime-loss behavior:

```text
load canonical task input
-> reconstruct exact Candidate/request
-> recompute candidate_hash/request_digest
-> identities match
-> retrieve or rerun the same logical task using the same task_id
```

If snapshot/builder material is missing, adapter version is unavailable, reconstruction is incomplete, or any digest differs: reconcile/fail closed. Never silently allocate a new task ID as a substitute for the lost accepted task.

## 4. P1R-03 — durable legacy/review-v1 Work-terminal classification

P3 terminal totality needs a clone-safe classification boundary. "Review files exist" is not sufficient.

Before the first review-v1 Work terminalization, P3 creates one immutable activation record:

```text
.workline/review/activation/work-terminal-v1.yaml
```

Minimum activation record:

```yaml
workline: workline-review-work-terminal-activation
version: 1
operation_contract: review-v1
legacy_event_count: <N>
legacy_event_prefix_sha256: <SHA-256 of exact canonical first N events.jsonl bytes>
activation_base_head: <commit immediately preceding activation-record commit>
```

The activation record is committed/proven before any review-v1 `work_completed` event is permitted. It does not contain the SHA of its own containing commit.

Classification after clone:

```text
activation record absent
-> only positively legacy project state is allowed; any explicit review-v1 terminal marker is contradictory

activation record present and event-log prefix count+digest matches
-> first N historical events are pre-activation legacy
-> every work_completed appended after N must carry explicit operation_contract = review-v1

post-activation work_completed missing marker
unknown marker
contradictory activation/prefix
-> reconcile_required; never legacy fallback
```

P3 extends canonical Event record parsing/rendering so review-v1 terminal events may carry versioned non-lifecycle metadata including at minimum:

```text
operation_contract: review-v1
review_receipt_id
review_run_id
review_generation
```

`state.py` and lifecycle derivation ignore these fields. They are read only by Review/operation consistency validation.

Totality remains:

```text
post-activation review-v1 work_completed
-> exactly one matching valid Consumption
```

The pending-terminal-stage exception remains the only recoverable one-sided transient.

## 5. P1R-04 — commit-local external side-effect test/guard

R5 already requires `commit_local()` to make no network contact, but live `git commit` may execute hooks and applicable filters/processes.

Frozen improvement:

Before Review-v1 `commit_local`, implementation must classify active hook/filter execution relevant to that commit. A hook/filter path that can produce an external side effect and is not mechanically sandboxed/denied is fail closed for Review-v1 commit. Workline must not assume that "no git_push effect" means no network publication occurred.

The implementation may mechanically disable applicable hooks only if doing so is itself part of the frozen Git persistence semantics for the Review-v1 commit. Filters that materially define committed bytes cannot simply be disabled; they must be either proven/contained sufficiently for the no-network contract or the commit must STOP.

R6/R11 dependency identity continues to bind effective hooks/filters/tooling. This repair adds the missing external-side-effect guard/test, not a second Git semantics model.

## 6. Required Round-2 tests

R12 is extended with at least:

1. `G(N+1)` physical create succeeds, applied flag save interrupted, crash, second invocation -> first pending mutation resumes; no N+2 intent/file.
2. same-run serialization token makes N+1 and hypothetical N+2 scopes overlap while first mutation pending.
3. accepted task -> runtime removed/fresh clone -> exact Candidate + request reconstruct from immutable provenance -> same task_id rerun/retrieve.
4. candidate snapshot missing/digest mismatch/builder unavailable -> fail closed; no new task ID.
5. activation marker with valid legacy event prefix -> pre-cutoff work_completed accepted as legacy.
6. post-activation review-v1 event + Consumption -> valid.
7. post-activation work_completed missing/unknown/contradictory operation-contract marker -> reconcile, never legacy fallback.
8. activation prefix digest/count mismatch -> reconcile.
9. `state.py` lifecycle result is unchanged by event Review metadata.
10. post-commit hook attempts push/network side effect before proof -> Review-v1 commit_local must block/sandbox so remote ref does not move.
11. applicable external clean/process filter with uncontained network side effect -> fail closed before reviewed publication boundary.

## 7. Revised readiness state

```text
Candidate 7 architecture: RETAIN
Architecture blockers: 0
HUMAN decisions: 0
P1R-01: REPAIRED/FROZEN
P1R-02: REPAIRED/FROZEN
P1R-03: REPAIRED/FROZEN
P1R-04: ACCEPTED/FROZEN LOW improvement
P1 implementation: NOT STARTED
Implementation activation: BLOCKED pending independent re-review
Candidate 8: NOT REQUIRED
```
