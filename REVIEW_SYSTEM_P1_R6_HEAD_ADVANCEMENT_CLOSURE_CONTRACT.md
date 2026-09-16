# Review System P1 — R6 HEAD Advancement / Review-Validity Closure Contract Freeze

Status: CONTRACT FROZEN / IMPLEMENTATION NOT STARTED

This checkpoint freezes the positive-proof contract for allowing an intervening HEAD advance without creating a new Review Candidate. It is non-normative until implemented and activated through canonical authority.

## 1. Live behavior confirmed

The current Mutation Controller already has a Git-write compatibility fast path for a recorded commit whose base HEAD has advanced. `_head_advanced_independently()` allows the commit to remain UNAPPLIED when:

- recorded base is a valid ancestor of current HEAD;
- current HEAD is still on the recorded branch;
- `commits_touching(base, head, recorded_paths)` reports no intervening commit touching those paths.

This is intentionally path/Git-write compatibility. It does not prove that Review Context, Evidence, toolchain, Git filters, tests, or semantic dependencies stayed unchanged.

Candidate 7 therefore keeps that mechanism for write safety but requires an additional Review-validity proof before a reviewed Candidate/evidence may be reused across the HEAD advance.

## 2. Frozen closure object

Every frozen Review Candidate carries a versioned `ReviewValidityClosure` identity with at least these sections:

```yaml
version: 1
base_commit_sha: ...
repo_dependencies: [...]
git_semantics: {...}
review_context_dependencies: [...]
evidence_dependencies: [...]
policy_dependencies: [...]
tool_runtime_dependencies: [...]
completeness: complete | unknown
completeness_basis: ...
digest: ...
```

The closure is not just a list of changed paths. It is the positively justified set of material dependencies whose invariance is required to reuse Review/Evidence after HEAD moves.

If any required section cannot prove completeness, the whole HEAD-advance fast path is `unknown` and a new Candidate is required.

## 3. Repository dependency entries

A repo-backed dependency records exact identity from the verified base tree, not merely worktree filename existence.

For each material path, capture enough Git tree identity to distinguish at least:

```text
normalized repo-relative path
Git entry mode
git object type
object ID / canonical tree entry identity
absence/deletion
```

This covers regular executable/non-executable files, symlinks, gitlinks/submodules, and deletion. Case/path collision handling follows the Candidate Builder's normalized-path contract; inability to establish an unambiguous path identity makes completeness unknown.

Actual implementation may use `git ls-tree`/plumbing helpers added to `gitcmd.py`; the proof source must be the commit tree, not mtime or a best-effort working-tree scan.

## 4. Closure classes

At minimum, the Review-validity closure distinguishes:

### A. ReviewedArtifact semantic dependencies

Files/configuration whose semantics affect the reviewed artifact even when they are not Work-owned output paths.

### B. Review Context provenance

Canonical Requirement/Work/Phase/Roadmap/registry/Skill/spec inputs and any source used to build the Review Context.

### C. Evidence dependencies

Tests, fixtures, helper code, build scripts, generated-input definitions, dependency manifests/lockfiles and other inputs declared by the Evidence adapter.

### D. Effective Policy / verifier inputs

Policy/profile/check/reviewer configuration and version identities that determine which obligations were run or how they were judged.

### E. Git persistence semantics

Material Git settings/files that can transform or reinterpret persisted content.

### F. Tool/runtime/dependency identities

Interpreter/tool/compiler/runtime/library/external identities whose change can invalidate Evidence or Candidate semantics.

R11 defines dependency-class completeness for Evidence; the same completeness discipline is reused here.

## 5. Git persistence semantics that must be considered

The live repository currently exposes no first-class helper for all Git attribute/filter/hook identity, so P1 implementation must add positive inspection where supported and use `unknown` otherwise.

Material surface includes, when applicable:

- tracked `.gitattributes` affecting Candidate/metadata paths;
- repository-local `.git/info/attributes`;
- configured global/system attributes source if it affects the repository;
- `filter.*` clean/smudge/process definitions for applicable attributes;
- line-ending/text settings materially affecting index/tree conversion (`core.autocrlf`, `core.eol`, related effective attributes);
- symlink/filemode behavior where relevant;
- `core.hooksPath` and the effective hooks that can mutate/refuse commit behavior;
- repository-local hooks under the effective hook path when relevant;
- submodule/gitlink identity for dependencies represented as gitlinks.

The implementation must not pretend completeness merely because these files/settings were not found by one path scan. It either establishes their effective identity or marks the relevant closure class unknown.

## 6. Uncommitted ambient state

HEAD advancement compatibility concerns intervening commits, but Evidence/Review may also depend on uncommitted ambient state. Candidate 7's isolated verification rule remains:

```text
final Evidence runs against Frozen Candidate in an isolated verification workspace
+ declared Context inputs
```

Therefore final Evidence must not silently inherit arbitrary dirty worktree/index/env inputs.

If an adapter intentionally declares a non-commit Context input, that input receives its own stable identity in the closure. Hidden ambient dependency makes completeness unknown.

## 7. Positive fast-path decision

Given verified base B and current HEAD H, Review/Evidence may be reused only if **both** layers pass:

### Layer 1 — Git-write compatibility

Existing rules prove branch/lineage and operation-owned commit paths remain safely committable.

### Layer 2 — Review-validity compatibility

```text
closure.completeness == complete
AND
B is ancestor of H
AND
for every intervening changed dependency surface:
    it is proven outside the complete material closure
AND
non-repo material identities bound by the closure are unchanged
```

Equivalent shorthand:

```text
intervening changed surfaces
INTERSECT
complete proven material closure
=
empty
```

The set operation is conceptual: non-path identities (runtime/policy/external/tool identities) are compared by their own identity proof, not coerced into fake paths.

## 8. Unknown is not false

Frozen fail-closed rule:

```text
cannot enumerate changed surface
OR closure completeness unknown
OR dependency identity cannot be compared
OR Git semantic source cannot be resolved
OR tool/external identity unavailable
=> Review-validity unknown
=> new Candidate generation
```

No fallback of the form:

```text
"we did not find a changed dependency, therefore unchanged"
```

is permitted.

## 9. New Candidate behavior

When Review-validity is unknown/invalid after HEAD advancement:

```text
new HEAD H
-> freeze new Candidate generation against H
-> recompute Candidate/Context identities
-> reuse only Evidence whose own R11 completeness/invariance proof succeeds
-> reacquire everything else
```

This is normal conservative behavior, not HUMAN and not reconcile by itself.

Reconcile is reserved for Git/ref/mutation facts that conflict or cannot safely resume; a semantically changed but otherwise valid HEAD simply creates a new Review Candidate.

## 10. Merge/multiple-parent result commit boundary

Intervening history may contain merges if the closure traversal can positively establish changed surfaces through all parents; current `commits_touching --full-history` already follows all parents for path checks.

The **Review-v1 result commit itself** remains one-parent unless a future explicit contract adds merge-result semantics. If commit proof sees multiple parents for K1/K2 where one-parent is required, reconcile/stop; do not infer equivalence from tree equality.

## 11. Closure digest and Review binding

The closure's canonical serialization/digest is part of the Candidate/Review Context evidence identity and is bound into the Gate Generation/Receipt proof material.

Changing the closure definition/version or discovering a previously unknown required dependency invalidates prior fast-path reuse; it does not retroactively rewrite historical completed operations.

## 12. Architecture blocker / HUMAN

Architecture blocker: `None`.

HUMAN decision: `None`.

The live Git layer needs additional inspection primitives, but Candidate 7 already defines the safe fallback: if completeness cannot be mechanically proven, create a new Candidate rather than weakening the gate.