# Review System P1 — R11 Evidence Dependency-Class Adapter Contract Freeze

Status: CONTRACT FROZEN / ROUND 3 REPAIRED / IMPLEMENTATION NOT STARTED

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
```

Future vocabulary changes do not inherit completeness automatically.

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

## 6. Environment / subprocess / dynamic libraries

Ambient inherited environment, untraced child processes, or unbound runtime libraries make corresponding classes unknown. Process-tree coverage must include child filesystem/network/dynamic-library activity.

## 7. Nondeterministic classes

Clock/randomness/hardware/cache and similar surfaces require mechanical pin/freeze, denial/non-use guarantee, or a contract proving observed variation immaterial. Otherwise no cross-Candidate reuse.

## 8. Network / external service

Network transport and external-service semantic identity are separate dependencies. Network access with unpinned remote semantics is not complete external-service coverage.

## 9. Git-state class

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

## 10. External-process versus subprocess/network classes

Git-configured external helpers are represented in `git_state` for Git semantic reachability and identity, while their execution-side effects also implicate `subprocess`, `network`, `filesystem_external`, or `external_service` as appropriate.

Completeness therefore requires both:

```text
Git semantic reachability/identity accounted for
AND
side-effect dependency classes mechanically covered/denied/pinned
```

This prevents `git_state=complete` from hiding an uncontrolled signer/filter/hook network dependency.

## 11. Evidence identity

Reusable Evidence binds at least Candidate/Context/Policy, adapter/check identity, class vocabulary, required-class declaration digest, coverage-basis digest, concrete dependency identities, tool/runtime identity, result digest and flakiness/repetition contract where relevant.

Any material bound identity change requires explicit irrelevance proof or reacquisition.

## 12. Interaction with R6

HEAD advancement may reuse Evidence only when Evidence completeness is complete and all repo/non-repo material identities remain valid. Unknown completeness cannot establish the R6 fast path.

## 13. Adapter trust

Trace/sandbox/basis implementations have their own identity/version and cannot self-certify completeness by outputting a boolean. Unsupported platforms/configurations fall to unknown.

## 14. Round-3 repair disposition

P1R2-NF-02 is closed at the Evidence boundary by binding Review-v1's signing-disabled commit mode and the reachable external Git-process surface into `git_state`, while also requiring the relevant subprocess/network/external dependency classes to be mechanically covered.

Architecture blocker: `None`.

HUMAN decision: `None`.
