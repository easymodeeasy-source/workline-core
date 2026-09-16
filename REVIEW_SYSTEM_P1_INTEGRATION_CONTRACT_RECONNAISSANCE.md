# Review System P1 — Integration Contract Reconnaissance Checkpoint

Status: ROUND 4 CONTRACT REPAIRS FROZEN / IMPLEMENTATION NOT STARTED / CURRENT-HEAD FINAL RE-REVIEW REQUIRED

Runtime authority remains `registry.md`, registry-routed canonical Skills, and live code until implementation/activation.

## Architecture baseline

```text
Candidate 7 architecture: RETAIN
Architecture blockers: 0
HUMAN decisions: 0
Candidate 8 required: No
```

Review remains a subordinate authorization/quality gate. `ProjectView/state.py` remains lifecycle/progression authority from canonical entities/relations/events. Review metadata never becomes lifecycle truth.

## Repair history

Round 1: `REVIEW_SYSTEM_P1_CONTRACT_REPAIR_AFTER_EXTERNAL_REVIEW.md`

Round 2: `REVIEW_SYSTEM_P1_CONTRACT_REPAIR_ROUND2.md`

Round 3: `REVIEW_SYSTEM_P1_CONTRACT_REPAIR_ROUND3.md`

Round 4: `REVIEW_SYSTEM_P1_CONTRACT_REPAIR_ROUND4.md`

## Round-3 repairs already frozen before the latest supplied review

The latest supplied review explicitly fixed its judgment to old commit `d38f02c282a0f8ae575418aa94b26c638583c4c9`. Live `main` had already advanced beyond that point.

Therefore two findings in that review were already closed on current `main` before Round 4:

### Activation digest

`work-terminal-activation-digest-v1` hashes canonical parsed Event records, not raw `events.jsonl` bytes. It preserves all schema-allowed fields, uses sorted compact JSON, UTF-8 and one LF per canonical Event line. Valid CRLF/LF and blank-line representation changes do not alter the digest; semantic Event mutation/order/metadata changes do.

### Commit-local external processes / signing

Review-v1 `commit_local-v1` classifies the full external executable/process surface reachable by the exact staging/local-commit path. Commit signing is explicitly disabled (`--no-gpg-sign` equivalent) for this contract version, and signing-disabled mode plus applicable hook/filter/helper semantics are bound into R6/R11 identity. Unclassified reachable external process => fail closed.

These remain mandatory; they were not reopened merely because the old-head review repeated them.

## Round-4 accepted seam — Review provenance reuse

The one newly material seam from the supplied review was that exact clone-safe Candidate/task reconstruction existed, but R6/R11 did not yet explicitly bind the provenance records themselves into cross-HEAD Evidence reuse.

Round 4 freezes:

```text
candidate_material_digest
task_input_digest
```

Accepted Gate task descriptors bind both.

### Snapshot mode

```text
candidate_material_digest
= SHA-256(versioned canonical Candidate snapshot bytes)
```

### Builder mode

The digest covers a canonical builder envelope containing builder identity/version, ordered complete clone-safe input identities, Candidate hash and projection-semantics version.

### Task input

```text
task_input_digest
= SHA-256(versioned canonical task-input bytes)
```

## R6 change

`ReviewValidityClosure` now includes explicit Review-provenance dependencies. Automatic HEAD-advance reuse requires provenance identities unchanged.

Therefore equal result hashes do not hide changed reconstruction provenance:

```text
same candidate_hash + changed snapshot bytes -> no automatic reuse
same request_digest + changed task-input bytes -> no automatic reuse
same builder output + changed builder version/input identity -> no automatic reuse
```

unless an explicit irrelevance proof exists.

## R11 change

`review_provenance` is a first-class Evidence dependency class. Reusable Evidence binds Candidate material digest, task-input digest and builder identities/inputs as applicable. Missing/uncomparable provenance => completeness unknown => no cross-Candidate reuse.

## R12 change

Mandatory tests now include negative HEAD-advance cases where Candidate/request result hashes stay equal while snapshot bytes, task-input bytes, builder version, or builder-input identities change. All must invalidate prior Review/Evidence reuse.

Round-3 activation serializer and signing/external-process tests remain mandatory.

## Current checkpoint

```text
Round 1 findings: REPAIRED/FROZEN
Round 2 findings: REPAIRED/FROZEN
Round 3 findings: REPAIRED/FROZEN
Round 4 provenance reuse seam: REPAIRED/FROZEN

P1 implementation: NOT STARTED
Implementation activation: BLOCKED pending one current-HEAD final focused independent re-review
```

## Next stage

Run one final focused readiness review against the **current live main HEAD**, not the old `d38f02c...` snapshot.

Final verdict must be one of:

```text
REPAIR
HUMAN
READY_FOR_P1_IMPLEMENTATION
```

If no concrete HIGH/MID seam and no HUMAN decision remains, stop the contract-review loop and begin P1 implementation.
