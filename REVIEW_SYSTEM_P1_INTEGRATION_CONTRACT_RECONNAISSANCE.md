# Review System P1 — Integration Contract Reconnaissance Checkpoint

Status: ROUND 4 CONTRACT REPAIRS FROZEN / ROUND 5 LIVE-BASELINE RECONCILED (`e32a74192e70d3ce8aec09f1921f175ac72b2d1d`) / IMPLEMENTATION NOT STARTED / FOCUSED RECONCILIATION RE-REVIEW REQUIRED

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

Round 5 (live-baseline reconciliation, not an architecture round): `REVIEW_SYSTEM_P1_LIVE_BASELINE_RECONCILIATION.md`

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

## Round-5 live-baseline reconciliation

The final readiness review reached `READY_FOR_P1_IMPLEMENTATION` against baseline `19bf5e71da6c7d735666e62cbe5b12ed9fffa5a9`. Live `main` then advanced 11 commits to `e32a74192e70d3ce8aec09f1921f175ac72b2d1d`.

A baseline reconciliation confirmed the Candidate 7 architecture seam intact — `state.py` and `ids.py` byte-identical, the R1/R2 layout and ID surfaces untouched, `_head_advanced_independently()` unchanged — while R5 and R7 carried frozen text that live canonical authority had moved past.

Round 5 reflects that live drift into the contracts. It is not an architecture round: no Candidate 8, no architecture document, no change to lifecycle/progression authority or to Review's subordinate-gate role.

```text
R5   updated (§1.1, §1.2, §3, §7, §12, §13)
R7   updated (§1, §2, §4, §8, §10, §13)
R6   consequential (§6.1, §15)
R11  consequential (§10.1, §16)
R12  updated (§10.1, §16)
```

## Current checkpoint

```text
Round 1 findings: REPAIRED/FROZEN
Round 2 findings: REPAIRED/FROZEN
Round 3 findings: REPAIRED/FROZEN
Round 4 provenance reuse seam: REPAIRED/FROZEN
Round 5 live-baseline reconciliation: APPLIED/FROZEN

Candidate 7 architecture: RETAIN
Architecture reopen: No
HUMAN decision: None

P1 implementation: NOT STARTED
Implementation activation: BLOCKED pending one focused independent
re-review of the Round-5 live-baseline reconciliation only
```

## Next stage

Run one focused independent re-review scoped to **the Round-5 live-baseline reconciliation against `e32a74192e70d3ce8aec09f1921f175ac72b2d1d`** — not a re-review of Candidate 7 architecture, and not a re-review of Rounds 1-4, which stay frozen.

Review target: `REVIEW_SYSTEM_P1_LIVE_BASELINE_RECONCILIATION.md` and the R5/R7/R6/R11/R12 changes it records.

Final verdict must be one of:

```text
REPAIR
HUMAN
READY_FOR_P1_IMPLEMENTATION
```

If no concrete HIGH/MID seam and no HUMAN decision remains, stop the contract-review loop and begin P1 implementation.
