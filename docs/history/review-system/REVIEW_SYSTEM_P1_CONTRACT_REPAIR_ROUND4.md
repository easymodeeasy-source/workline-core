# Review System P1 — Contract Repair Round 4

Status: ROUND 4 REPAIR FROZEN / IMPLEMENTATION NOT STARTED

This non-normative checkpoint records the latest independent review and distinguishes stale findings against the old review HEAD from the one remaining contract seam that was still material on current `main`.

Runtime authority remains `registry.md`, registry-routed canonical Skills and live code until implementation/activation.

## 1. Review baseline distinction

The supplied review explicitly fixed its evidence to old commit:

```text
d38f02c282a0f8ae575418aa94b26c638583c4c9
```

while live `main` had already advanced beyond it.

Therefore findings were adjudicated against current contracts, not blindly replayed from the old snapshot.

Disposition:

```text
P1R-01 same-run generation recovery      RESOLVED
P1R-02 clone-safe exact task material    RESOLVED for clone reconstruction
P1R-03 terminal classification digest    ALREADY REPAIRED in Round 3 current main
P1R-04 external process/signing guard     ALREADY REPAIRED in Round 3 current main

new remaining seam:
Review provenance identity not explicitly bound into R6/R11 reuse
-> ACCEPTED / REPAIRED in Round 4
```

Candidate 7 architecture remains retained. Candidate 8 is not required.

## 2. Provenance reuse repair

Round 4 freezes two canonical provenance identities:

```text
candidate_material_digest
task_input_digest
```

### Candidate material

Snapshot mode:

```text
candidate_material_digest
= SHA-256(versioned canonical Candidate snapshot bytes)
```

Builder mode:

```text
candidate_material_digest
= SHA-256(versioned canonical builder envelope)
```

where the builder envelope binds:

```text
builder identity
builder version
ordered complete clone-safe input identities
candidate_hash
projection semantics version
```

### Task input

```text
task_input_digest
= SHA-256(versioned canonical task-input bytes)
```

Accepted Gate task descriptors bind these digests directly in addition to result identities such as `candidate_hash` and `request_digest`.

## 3. R6 Review-validity change

`ReviewValidityClosure` now has explicit `review_provenance_dependencies`.

Automatic HEAD-advancement reuse requires all bound provenance identities to remain unchanged.

Therefore:

```text
same candidate_hash
+ changed snapshot bytes
-> no automatic reuse

same request_digest
+ changed task-input provenance bytes
-> no automatic reuse

same builder output
+ changed builder version/input identity
-> no automatic reuse
```

unless an explicit irrelevance proof exists.

## 4. R11 Evidence change

`review_provenance` is now a first-class dependency class for reusable Evidence.

Reusable Evidence binds at least:

```text
candidate_hash
candidate_material_digest
task_input_digest
request_digest
review_context_hash
effective_policy_hash
adapter/check identity
```

and builder identity/version/input identities where builder mode is used.

Unknown/missing provenance completeness prevents cross-Candidate Evidence reuse.

## 5. R12 tests

Round 4 adds explicit negative tests where result hashes remain unchanged but provenance changes:

- snapshot canonical bytes changed;
- task-input canonical bytes changed;
- builder version changed;
- builder input identity changed.

All must invalidate prior Evidence/Review reuse.

Round-3 activation digest tests and commit-signing/external-process tests remain mandatory and unchanged.

## 6. Architecture / HUMAN

```text
Candidate 7 architecture: RETAIN
Architecture blockers: 0
HUMAN decisions: 0
Candidate 8 required: No
```

## 7. Current state

```text
Round 1 findings: REPAIRED/FROZEN
Round 2 findings: REPAIRED/FROZEN
Round 3 findings: REPAIRED/FROZEN
Round 4 provenance reuse seam: REPAIRED/FROZEN

P1 implementation: NOT STARTED
Implementation activation: BLOCKED pending one current-HEAD final focused re-review
```

The next review must use the live current `main` HEAD, not the old `d38f02c...` snapshot, and should not reopen Round-3 findings unless it demonstrates a failure that still exists in the current contracts.
