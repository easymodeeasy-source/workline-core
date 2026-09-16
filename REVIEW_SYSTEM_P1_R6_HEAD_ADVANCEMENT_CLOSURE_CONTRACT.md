# Review System P1 — R6 HEAD Advancement / Review-Validity Closure Contract Freeze

Status: CONTRACT FROZEN / ROUND 4 REPAIRED / IMPLEMENTATION NOT STARTED

This checkpoint freezes the positive-proof contract for allowing an intervening HEAD advance without creating a new Review Candidate. It is non-normative until implemented and activated through canonical authority.

## 1. Live behavior confirmed

The current Mutation Controller already has a Git-write compatibility fast path for a recorded commit whose base HEAD has advanced. `_head_advanced_independently()` allows the commit to remain UNAPPLIED when recorded base is an ancestor of current HEAD, branch matches, and intervening commits do not touch recorded paths.

This proves path/Git-write compatibility only. It does not prove Review Context, Evidence, provenance, toolchain, Git transformation/external-process semantics, tests or semantic dependencies stayed unchanged.

Candidate 7 therefore requires a separate Review-validity closure.

## 2. Frozen closure object

Every frozen Review Candidate carries a versioned `ReviewValidityClosure` identity with at least:

```yaml
version: 1
base_commit_sha: ...
repo_dependencies: [...]
review_provenance_dependencies: [...]
git_semantics: {...}
review_context_dependencies: [...]
evidence_dependencies: [...]
policy_dependencies: [...]
tool_runtime_dependencies: [...]
completeness: complete | unknown
completeness_basis: ...
digest: ...
```

If any required section cannot prove completeness, HEAD-advance reuse is `unknown` and a new Candidate is required.

## 3. Repository dependency entries

Repo-backed material identities come from the verified Git tree and distinguish path, mode, object type/object ID and absence/deletion. Symlink, executable mode and gitlink semantics are preserved. Ambiguous path/case identity makes completeness unknown.

## 4. Review provenance dependencies

Accepted-task provenance is a first-class material dependency.

For every accepted task, the closure binds at least:

```text
candidate_hash
candidate_material_digest
task_input_digest
request_digest
reviewer_or_adapter_identity + version
review_context_hash
effective_policy_hash
```

For snapshot mode, `candidate_material_digest` is the SHA-256 of the versioned canonical Candidate snapshot bytes.

For deterministic builder mode, the bound provenance includes the exact canonical builder envelope digest and the builder identity/version plus every clone-safe input identity needed to reconstruct the exact projection.

For task input, `task_input_digest` is the SHA-256 of the exact versioned canonical task-input bytes.

The important rule is:

```text
same candidate_hash
!= automatically same Review provenance
```

If snapshot bytes, task-input bytes, builder version, or any bound builder input identity changes across HEAD advancement, prior Review/Evidence is not reusable unless an explicit irrelevance proof exists. Otherwise freeze a new Candidate/reacquire Evidence as required.

A well-formed manual/external Git replacement of immutable provenance records is still a material historical change even if it reconstructs the same artifact/request hash.

## 5. Closure classes

At minimum:

### A. ReviewedArtifact semantic dependencies
Material files/configuration affecting reviewed artifact meaning.

### B. Review provenance
Candidate snapshot/task-input/builder envelopes and all identities needed to reconstruct the accepted Candidate/request.

### C. Review Context provenance
Requirement/Work/Phase/Roadmap/registry/Skill/spec and other Context sources.

### D. Evidence dependencies
Tests, fixtures, helpers, build/generated-input definitions, manifests and adapter-declared inputs.

### E. Effective Policy / verifier inputs
Policy/profile/reviewer/check configuration and version identities.

### F. Git persistence / commit execution semantics
Material Git settings/files/process modes that can transform persisted content, change commit behavior, or cause pre-proof external side effects.

### G. Tool/runtime/dependency identities
Interpreter/compiler/runtime/library/external identities.

R11 dependency completeness is reused here.

## 6. Git semantics surface

P1 implementation must positively inspect applicable Git semantics and use `unknown` where completeness cannot be established.

Material surface includes, when applicable:

- tracked `.gitattributes` affecting Candidate/Review paths;
- `.git/info/attributes` and effective global/system attributes sources;
- applicable `filter.*` clean/process definitions and LFS clean/process identity;
- line-ending/text conversion settings (`core.autocrlf`, `core.eol`, effective attributes);
- symlink/filemode behavior;
- `core.hooksPath` and effective commit hooks;
- hook suppression/containment mode used by Review-v1 commit execution;
- commit signing configuration/program surfaces that the normal Git invocation could otherwise reach;
- **Review-v1 commit-local signing mode = explicitly disabled (`--no-gpg-sign` equivalent) for contract version commit-local-v1**;
- submodule/gitlink identity;
- any other effective Git-configured external executable reachable by the exact staging/local-commit path.

Signing-disabled mode is part of the Review-v1 Git persistence/commit-execution identity. A future signed Review-v1 contract is a different semantic version and does not reuse evidence/proof merely because tree bytes match.

Surfaces that Git supports but the exact path cannot invoke need not be declared material unless configuration makes them reachable.

## 7. External-process completeness

For the Review-v1 staging/local-commit boundary, a complete closure must establish either:

```text
external executable/process is not reachable
OR
it is mechanically suppressed by the frozen commit contract
OR
it is mechanically contained/denied and its identity/containment basis is bound
```

An unclassified reachable external process makes Git semantics completeness unknown/fail-closed for commit execution.

This applies before proof; no later tree equality can erase an uncontrolled pre-proof side effect.

## 8. Uncommitted ambient state

Final Evidence runs against the Frozen Candidate in isolated verification workspace + declared Context. Hidden ambient worktree/index/env dependency makes completeness unknown unless explicitly bound.

## 9. Positive fast-path decision

Review/Evidence reuse across B->H requires both:

### Layer 1 — Git-write compatibility
Branch/lineage and operation-owned write safety pass.

### Layer 2 — Review-validity compatibility

```text
closure.completeness == complete
AND B ancestor of H
AND intervening changed material surfaces are proven outside the complete closure
AND all bound Review provenance identities unchanged
AND non-repo bound identities unchanged
```

Non-path identities are compared directly; they are not coerced into fake paths.

## 10. Unknown is not false

```text
cannot enumerate changed surface
OR closure completeness unknown
OR provenance dependency identity uncomparable
OR Git semantic/external-process source unresolved
OR tool/external identity unavailable
=> Review-validity unknown
=> new Candidate / fresh proof as required
```

Absence of discovered change is never proof of invariance.

## 11. New Candidate behavior

If semantic Review validity is unknown/invalid after HEAD advancement, freeze a new Candidate against H and reuse only Evidence whose own R11 completeness/invariance proof succeeds. Git conflicts remain reconcile territory; semantic drift alone normally creates a new Candidate.

## 12. Merge/result commit boundary

Intervening merges may be handled only with complete changed-surface traversal. Review-v1 result/terminal commits themselves remain one-parent unless a future explicit contract changes that.

## 13. Closure digest and Review binding

Canonical closure digest is bound into Candidate/Review Context evidence identity and Gate/Receipt proof material. Definition/version changes invalidate prior automatic reuse.

## 14. Round-4 repair disposition

This revision closes the later independent review's provenance-reuse seam by adding explicit Review-provenance dependencies (`candidate_material_digest`, `task_input_digest`, builder envelope/input identities) to the ReviewValidityClosure and HEAD-advancement decision.

Round-3 signing/external-process closure remains in force.

Architecture blocker: `None`.

HUMAN decision: `None`.
