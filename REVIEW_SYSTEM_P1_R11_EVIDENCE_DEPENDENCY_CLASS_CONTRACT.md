# Review System P1 — R11 Evidence Dependency-Class Adapter Contract Freeze

Status: CONTRACT FROZEN / IMPLEMENTATION NOT STARTED

This checkpoint freezes how Evidence adapters prove dependency completeness for Candidate 7 reuse and HEAD-advancement fast paths. It is non-normative until implementation and authority activation.

## 1. Problem boundary

Candidate 7 rejects a bare `dependency_complete=true` flag and also rejects treating a named basis such as `hermetic` or `observed_trace` as proof by itself.

The adapter must prove that every dependency class the check may materially use is either:

```text
mechanically observed
mechanically pinned
mechanically denied
```

under a defined guarantee. Anything required but unaccounted for makes completeness `unknown`.

## 2. Versioned dependency-class vocabulary

P1 freezes dependency-class vocabulary version `review-dependency-classes-v1` with these minimum classes:

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

An adapter may declare a narrower required subset. It may not silently place an unknown dependency into a nearby class merely to obtain completeness.

A future vocabulary version may add/split classes. Evidence produced under an older vocabulary is not automatically complete under the new vocabulary; reuse needs an explicit compatibility proof.

## 3. Adapter declaration

Every Evidence adapter declares, in canonical machine-readable form:

```yaml
class_vocabulary: review-dependency-classes-v1
adapter_id: ...
adapter_version: ...
required:
  - repository_files
  - runtime_toolchain
coverage:
  repository_files:
    mode: observed | pinned | denied | unknown
    basis: ...
    identities: [...]
  runtime_toolchain:
    mode: pinned
    basis: ...
    identities: [...]
not_required:
  - network
  - clock
...
```

`not_required` is a semantic claim of the adapter/check contract. A class omitted from both `required` and a closed `not_required` declaration makes the adapter's dependency surface incomplete unless its basis mechanically prevents that class from being used.

## 4. Completeness equation

Evidence dependency completeness is `complete` only when:

```text
for every materially possible dependency class:
  class is declared required and coverage mode is observed|pinned|denied
  OR
  class is positively excluded by the adapter's closed execution contract
```

Equivalent practical rule:

```text
required classes
SUBSET OF
mechanically covered/pinned/denied classes
```

plus proof that the required-class declaration itself is complete for that adapter execution mode.

If either side cannot be established:

```text
completeness = unknown
```

There is no `partial but probably enough` reuse state.

## 5. Coverage modes

### `observed`

The basis mechanically records all material instances within that class under a stated guarantee.

Example: a traced filesystem sandbox that records every allowed file open by the process tree.

A best-effort log that is known not to observe native children/dynamic loads is not `observed` for the whole class; split the guarantee or mark unknown.

### `pinned`

The dependency is constrained to a stable identity that is recorded in Evidence identity.

Examples: exact interpreter/tool binary identity, exact lockfile-derived environment image, exact external service snapshot/version where the provider can actually prove it.

A version string alone is sufficient only if the adapter contract establishes that the string uniquely identifies the materially relevant implementation.

### `denied`

The execution environment mechanically prevents access to that dependency class.

Examples: network namespace/firewall policy that denies all network access; sandbox with no undeclared filesystem mount.

A prompt saying “do not use the network” is not mechanical denial.

### `unknown`

Anything not positively covered. Unknown Evidence may still be freshly run and used for the Candidate on which it was produced, subject to its check semantics, but it is not cross-Candidate reusable on the claim of dependency completeness.

## 6. Repository-file identities

For `repository_files`, Evidence identity uses the same path/tree-entry discipline as R6:

```text
repo-relative path
commit/base identity
entry mode/type
object/blob/tree identity
```

Generated files or worktree-only declared Context inputs need explicit identities separate from commit-tree entries.

An adapter that shells out to arbitrary tools which may discover repository files dynamically cannot claim complete repository-file coverage unless the execution basis traces/denies those dynamic reads.

## 7. Environment / subprocess / dynamic libraries

Environment completeness distinguishes:

- variables intentionally passed/pinned;
- variables mechanically cleared/denied;
- ambient inherited variables.

Ambient inheritance with unknown possible semantic use makes the relevant class unknown.

For subprocess coverage, the proof applies to the whole spawned process tree, not merely the parent command line. If child filesystem/network/dynamic-library activity escapes the trace/sandbox, the corresponding class is unknown.

Dynamic linker/runtime library inputs must be pinned/observed where they can materially change results; process executable path alone is not sufficient proof.

## 8. Nondeterministic classes

`clock`, `randomness`, `hardware`, `cache_state`, and similar nondeterministic surfaces require one of:

```text
mechanical pin/freeze
mechanical denial/non-use guarantee
observed identity plus a check contract proving observed variation is immaterial
```

Otherwise cross-Candidate reuse is forbidden.

A flaky check that passes once never becomes reusable certainty merely because its file dependencies are complete.

## 9. Network / external services

Network access and external-service semantics are separate concerns:

```text
network
= transport/access dependency

external_service
= remote data/service semantic identity
```

Allowing a network connection while pinning no remote result/version is not complete external-service coverage.

Where the external service cannot supply a stable identity/snapshot, Evidence can be fresh-use-only or time/window-scoped as Effective Policy allows; it cannot be reused as timeless proof.

## 10. Git-state class

Checks that invoke Git or whose result depends on repository configuration/index/attributes/hooks declare `git_state` required.

Coverage then binds the relevant Git state identified by R6, including branch/base/tree/config/attributes/filter/hook identities as materially applicable.

A check that only reads files from an isolated exported tree and never invokes Git may mechanically exclude this class.

## 11. Evidence identity

A reusable Evidence record binds at least:

```text
candidate_hash
review_context_hash
effective_policy_hash
adapter ID/version
check identity
class vocabulary version
required-class declaration digest
coverage-basis digest
concrete dependency identities digest
tool/runtime identity
result digest
flakiness/repetition contract where applicable
```

If any bound material identity changes, reuse requires an explicit irrelevance proof; otherwise reacquire.

## 12. Interaction with R6 HEAD advancement

R6 consumes the same dependency-class manifest. HEAD advancement can reuse Evidence only if:

```text
Evidence completeness == complete
AND all repo-backed dependency identities unchanged across the intervening commits
AND all non-repo pinned/observed material identities remain valid
```

If Evidence completeness is unknown, HEAD advancement cannot use that Evidence to establish Review-validity fast-path completeness; freeze a new Candidate and rerun as required.

## 13. Adapter trust

The adapter implementation and completeness basis have their own identity/version. A trace tool cannot certify its own completeness merely by emitting `complete=true`; its declared guarantee is part of canonical Review Policy/adapter code and must be reviewable/tested.

Where the basis relies on OS/container/compiler guarantees, the relevant basis implementation/version is bound. Unsupported platforms/configurations fall to unknown rather than inheriting another platform's guarantee.

## 14. Architecture blocker / HUMAN

Architecture blocker: `None`.

HUMAN decision: `None`.

Exact tracer/sandbox integrations remain implementation work, but the fail-closed completeness contract is fully frozen: unproved classes never become reusable by assumption.