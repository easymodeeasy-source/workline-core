# Review System P1 — R3 Gate Generation Mutation Contract Freeze

Status: CONTRACT FROZEN / ROUND 4 REPAIRED / IMPLEMENTATION NOT STARTED

This checkpoint freezes how Candidate 7's minimum durable Review Gate generations enter canonical Project state. It is non-normative until implemented and routed through canonical authority.

## 1. Ownership rule

Canonical Review gate state is written by the top-level operation using the gate:

```text
Roadmap planning Review -> Roadmap mutation owner
Phase-entry Review      -> Roadmap mutation owner
Work Formal Review      -> START mutation owner
future Policy Review    -> corresponding Policy operation owner
```

There is no standalone Review progression controller.

## 2. Crash-safe same-run generation serialization

Project execution lock serializes only the live process. Pending mutation state carries exclusivity across crash.

For every new generation transition:

```text
hold Project lock
-> inspect pending generation mutations for review_run_id
-> if one exists: resume/reconcile it before calculating any new generation
-> if conflicting/multiple: reconcile_required
-> otherwise validate full immutable chain
-> calculate exact N+1 path
-> open mutation with BOTH exact generation path and stable same-run token in initial WriteScope.files
-> only then reserve IDs / record effects
```

Initial scope:

```text
.workline/review/gates/<review_run_id>/<generation:06d>.yaml
.workline/review/gates/<review_run_id>/.generation-serialization
```

`.generation-serialization` is scope-only: never physically created or committed. It guarantees that unfinished N+1 and a hypothetical N+2 for the same run overlap mechanically.

Therefore this window is closed:

```text
G(N+1) physical immutable create succeeds
-> crash before effect.applied save
-> new invocation sees N+1 in canonical chain
```

The new invocation must discover/resume the pending same-run mutation and cannot open N+2 while it remains pending.

## 3. Async callback rule

External reviewer/shadow callbacks do not mutate Project state directly.

Durable sequence:

```text
1. create clone-safe Candidate/task input provenance
2. compute canonical provenance identities
3. parent operation writes accepted task descriptor in new Gate generation
4. provenance + accepted generation reach required local Git persistence boundary
5. only then launch/retrieve external task
6. result returns to an operation holding Project lock
7. identity/result is validated against canonical task input
8. settlement/adjudication is written as next generation
9. only then may sealing/consumption proceed
```

Runtime/provider result arrival alone does not settle anything.

## 4. Clone-safe Candidate/request reconstruction

An accepted task descriptor must reference exact canonical reconstruction material, not only hashes.

### Candidate material

Canonical source:

```text
.workline/review/candidate-snapshots/<candidate_hash>.yaml
```

or deterministic `builder_v1` data whose builder identity/version and every required input are clone-safe and sufficient to regenerate the exact ReviewedArtifactProjection.

Snapshot/builder material must bind exact path/object-kind/mode/deletion/symlink/gitlink/content identity semantics and the Git persistence identity required by R6. Binary data is represented canonically and exactly.

### Task input

Canonical source:

```text
.workline/review/task-inputs/<review_task_id>.yaml
```

Minimum binding:

```text
task_id
task_slot
task_kind
reviewer_or_adapter_identity + version
exact versioned request envelope
request_digest
candidate_hash
candidate reconstruction reference/mode
review_context_hash
effective_policy_hash
accepted_generation
```

Fresh clone/runtime loss may retrieve/rerun **the same task_id** only after reconstructing exact Candidate/request and recomputing matching digests/identities. Missing snapshot/builder input, unavailable adapter version, incomplete reconstruction, or digest mismatch is fail closed/reconcile; never allocate a substitute task ID silently.

Provider job handles remain runtime-only and non-authoritative.

## 5. Canonical provenance identities

Round 4 adds explicit identities for the immutable provenance records themselves so Review-validity reuse cannot depend only on `candidate_hash` or `request_digest`.

Frozen definitions:

```text
candidate_material_digest
= SHA-256(versioned canonical bytes of the exact candidate snapshot record)
```

For deterministic builder mode, `candidate_material_digest` instead hashes the versioned canonical builder envelope containing:

```text
builder identity
builder version
ordered complete clone-safe input identities
candidate_hash
projection semantics version
```

The exact task-input record has:

```text
task_input_digest
= SHA-256(versioned canonical bytes of the exact task-input record)
```

An accepted Gate task descriptor binds both:

```text
candidate_material_digest
task_input_digest
```

along with `candidate_hash`, `request_digest`, adapter/reviewer identity and the existing Context/Policy identities.

These provenance digests identify **how the accepted task and Candidate are reconstructed**, not only the resulting artifact/request identity. Therefore a well-formed replacement of snapshot/task-input/builder provenance that happens to reconstruct the same `candidate_hash` or `request_digest` is still a Review-validity material change unless an explicit irrelevance proof exists.

## 6. Immutable generation snapshot

Each generation is a full minimum immutable snapshot and uses R1 create-only writer.

Minimum fields include:

```text
review_run_id
generation
previous_generation / previous_digest
review_kind / target_identity / operation_identity
candidate_hash / review_context_hash / effective_policy_hash
evidence / coverage / raw-report / adjudication / obligation digests
accepted task descriptors/references
  including candidate_material_digest + task_input_digest
settled task bindings
status = open | sealed_authorized
receipt_id nullable
```

Predecessor digest uses R1 canonical-byte SHA-256 contract.

## 7. Seal + Receipt

A seal that first issues R1 records both immutable creates in one Mutation stage. All effects are durable intent before physical application. A partial stage resumes exact remaining effects; no consumer may rely on the seal until exact ReviewStore reread validates both.

## 8. Invalidation / supersession

A newly supported invalidating fact creates a later `open` generation and supersession record before old Receipt may proceed. The same-run serialization rule applies to every settlement, seal and invalidation generation.

## 9. Mutation invocation binding

The owning mutation binds at least:

```text
review_run_id
review_generation
candidate_hash
review_context_hash
effective_policy_hash
obligation_digest
receipt_id when issued
proof_phase
```

Existing Roadmap/Work request identity is augmented, never replaced.

## 10. Git persistence boundary

Any gate/provenance fact relied on after clone/process loss must reach canonical tracked local Git state before dependent external launch/terminal boundary. Remote-less Projects remain valid.

## 11. No second state machine authority

Gate/provenance records are authorization evidence only. `state.py` never reads them to derive Work/Phase/Roadmap lifecycle or next selection.

## 12. Round-4 repair disposition

P1R-01 remains closed by same-run pending discovery + stable scope-only serialization token.

P1R-02 clone reconstruction remains closed by immutable Candidate snapshot/task-input provenance and exact reconstruction-before-rerun semantics.

The later independent review's provenance-reuse seam is closed by binding `candidate_material_digest` and `task_input_digest` into accepted Gate task descriptors and requiring R6/R11 to treat them as material dependencies.

Architecture blocker: `None`.

HUMAN decision: `None`.
