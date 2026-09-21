# Review System P1 — R11 Evidence Dependency-Class Adapter Contract Freeze

Status: CONTRACT FROZEN / ROUND 4 REPAIRED / IMPLEMENTATION NOT STARTED

This checkpoint freezes how Evidence adapters prove dependency completeness for Candidate 7 reuse and HEAD-advancement fast paths. It is non-normative until implementation and authority activation.

## 1. Problem boundary

Candidate 7 rejects bare completeness flags and best-effort dependency lists. Every materially possible dependency class must be mechanically observed, pinned, denied, or explicitly proven not required. Anything unaccounted for makes completeness `unknown`.

## 2. Versioned dependency-class vocabulary

P1 uses `review-dependency-classes-v1` with minimum classes:

```text
repository_files
filesystem_external
environment
subprocess
network
clock
randomness
locale
dynamic_libraries
runtime_toolchain
hardware
external_service
cache_state
git_state
review_provenance
```

`review_provenance` identifies the canonical reconstruction material used by accepted Review tasks. Future vocabulary changes do not inherit completeness automatically.

## 3. Adapter declaration

Every Evidence adapter declares required classes, coverage mode/basis/identities and closed `not_required` classes in canonical machine-readable form.

Coverage modes:

```text
observed | pinned | denied | unknown
```

Completeness requires that every materially possible class is mechanically covered/pinned/denied or positively excluded by a closed execution contract.

## 4. Coverage semantics

### observed
Mechanically records all material instances under a stated guarantee. Best-effort traces do not count as complete where children/native loads/other surfaces escape.

### pinned
Dependency constrained to stable recorded identity.

### denied
Execution environment mechanically prevents use of that class.

### unknown
Anything not positively accounted for. Unknown Evidence may be fresh-use-only but not cross-Candidate reusable on completeness grounds.

## 5. Repository-file identities

Use the same commit-tree path/mode/object identity discipline as R6. Dynamic discovery requires tracing/denial sufficient to make repository-file dependency coverage complete.

## 6. Review provenance identities

Evidence produced for an accepted Review task binds the exact canonical provenance used to reconstruct the Candidate/request, not only their result hashes.

Minimum reusable Evidence identity includes:

```text
candidate_hash
candidate_material_digest
task_input_digest
request_digest
reviewer_or_adapter_identity + version
review_context_hash
effective_policy_hash
```

For deterministic builder mode, provenance identity additionally binds:

```text
builder identity
builder version
ordered complete clone-safe input identities
projection semantics version
```

Changing snapshot bytes, task-input bytes, builder version, or any bound builder input identity invalidates automatic Evidence reuse even when reconstructed `candidate_hash` or `request_digest` remains unchanged, unless an explicit irrelevance proof is available.

A complete `review_provenance` claim therefore requires every reconstruction input to be pinned/observed by canonical identity. Missing or incomparable provenance identity => `unknown` => no cross-Candidate reuse.

## 7. Environment / subprocess / dynamic libraries

Ambient inherited environment, untraced child processes, or unbound runtime libraries make corresponding classes unknown. Process-tree coverage must include child filesystem/network/dynamic-library activity.

## 8. Nondeterministic classes

Clock/randomness/hardware/cache and similar surfaces require mechanical pin/freeze, denial/non-use guarantee, or a contract proving observed variation immaterial. Otherwise no cross-Candidate reuse.

## 9. Network / external service

Network transport and external-service semantic identity are separate dependencies. Network access with unpinned remote semantics is not complete external-service coverage.

## 10. Git-state class

Checks/operations that invoke Git or depend on repository Git behavior declare `git_state` required unless an isolated exported-tree contract positively excludes it.

For Review-v1 staging/local-commit related evidence, `git_state` coverage includes as materially applicable:

```text
branch/base/tree/index identity
attributes and line-ending conversion semantics
applicable clean/process/LFS filters
core.hooksPath and effective commit hooks
hook suppression/containment mode
effective commit-signing configuration/program surface
Review-v1 commit-local-v1 signing mode = explicitly disabled
reachable Git-configured external helpers for the exact path
```

A complete `git_state` claim must establish for each reachable external process that it is either unreachable under the exact invocation, mechanically suppressed by the frozen contract, or mechanically contained/denied with the relevant identity/basis recorded.

The fact that an external helper was not observed in one run is not enough if the invocation could reach it.

A signing-enabled Git default does not invalidate Review-v1 commit-local-v1 by itself because the frozen Review-v1 primitive explicitly disables signing. The effective fact that signing is disabled for that primitive is itself bound into Evidence/Git-state identity. A future signed Review-v1 contract is a different semantic identity.

### 10.1 Publication-state remote read

Re-verified at baseline `e32a741`: the live publication path reads the pinned destination read-only (`git ls-remote --refs`, plus an isolated history fetch into the object database alone) after proof, to decide whether an exact commit is already published.

This read is not publication and writes nothing, but it is material and is declared, not waived:

```text
network            transport to the pinned destination
external_service   the destination repository's semantic identity
git_state          pinned locator identity, the proof that Git reads that
                   locator as itself rather than rewriting it, and the
                   destination branch/ancestry fact relied upon
runtime_toolchain  the Git implementation performing the read
```

Coverage rules:

```text
destination identity unpinned or rewritten by Git
  -> not covered -> fail closed, the read is not performed
read unanswerable, or the destination changed while being read
  -> unknown -> fail closed
absence of a discovered publication
  -> never coverage, and never proof of non-publication
```

Distinguish this from R6 §7's pre-proof external-process problem: a pre-proof uncontrolled external side effect is fail-closed on reachability grounds, whereas a post-proof publication-state read is permitted and merely has to be completely declared.

## 11. External-process versus subprocess/network classes

Git-configured external helpers are represented in `git_state` for Git semantic reachability and identity, while their execution-side effects also implicate `subprocess`, `network`, `filesystem_external`, or `external_service` as appropriate.

Completeness therefore requires both:

```text
Git semantic reachability/identity accounted for
AND
side-effect dependency classes mechanically covered/denied/pinned
```

This prevents `git_state=complete` from hiding an uncontrolled signer/filter/hook network dependency.

## 12. Evidence identity

Reusable Evidence binds at least:

```text
candidate_hash
candidate_material_digest
task_input_digest
request_digest
review_context_hash
effective_policy_hash
adapter/check identity
class vocabulary
required-class declaration digest
coverage-basis digest
concrete dependency identities
tool/runtime identity
result digest
flakiness/repetition contract where relevant
```

Any material bound identity change requires explicit irrelevance proof or reacquisition.

## 13. Interaction with R6

HEAD advancement may reuse Evidence only when Evidence completeness is complete and all repository, Review-provenance and non-repo material identities remain valid. Unknown completeness cannot establish the R6 fast path.

## 14. Adapter trust

Trace/sandbox/basis implementations have their own identity/version and cannot self-certify completeness by outputting a boolean. Unsupported platforms/configurations fall to unknown.

## 15. Round-4 repair disposition

This revision closes the later independent review's provenance-reuse seam by making Candidate snapshot/task-input/builder reconstruction identities first-class reusable-Evidence dependencies.

Round-3 signing/external-process safeguards remain in force.

Architecture blocker: `None`.

HUMAN decision: `None`.

## 16. Round-5 live-baseline reconciliation disposition

Consequential update only, reconciled to live baseline `e32a74192e70d3ce8aec09f1921f175ac72b2d1d`.

§10.1 declares the post-proof publication-state remote read across `network`, `external_service`, `git_state` and `runtime_toolchain`, with fail-closed handling for unpinned destination identity and unanswerable reads.

The `review-dependency-classes-v1` vocabulary is unchanged — no class added, removed or renamed — so no completeness claim is inherited or invalidated by this revision.

Architecture reopen: `No`. Candidate 8: `No`.
