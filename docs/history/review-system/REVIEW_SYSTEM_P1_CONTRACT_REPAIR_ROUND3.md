# Review System P1 — Contract Repair Round 3

Status: THIRD REPAIR FROZEN / IMPLEMENTATION NOT STARTED

This non-normative checkpoint records the third independent Implementation Readiness review. Candidate 7 architecture remains retained; Candidate 8 is not created.

Runtime authority remains `registry.md`, registry-routed canonical Skills and live code until implementation/activation.

## 1. Review disposition

The third independent review found:

```text
P1R-01 same-run generation recovery      RESOLVED
P1R-02 clone-safe exact task material    RESOLVED
P1R-03 terminal contract classification  PARTIAL -> P1R2-NF-01
P1R-04 hook/filter side-effect guard     PARTIAL -> P1R2-NF-02

Architecture blockers: None
HUMAN decisions: None
Verdict: REPAIR
```

Both MID findings are accepted and repaired here. No previously closed contract seam is reopened.

## 2. P1R2-NF-01 — exact activation-prefix canonical serializer

Problem: a raw-byte digest of pre-activation `events.jsonl` would be unstable across valid legacy representations because the live reader accepts CRLF/blank lines while later append/rewrite may normalize text.

Frozen repair: R4 defines `work-terminal-activation-digest-v1` over canonical parsed Event records, not physical file bytes.

Algorithm summary:

```text
parse nonblank Event JSON records using canonical Event schema
legacy_event_count = parsed Event count
for first N Events:
  preserve all schema-allowed fields
  sort object keys lexicographically
  canonical compact JSON (`,` / `:` separators)
  UTF-8, non-ASCII preserved
  exactly one LF after each record
SHA-256(concatenated canonical Event lines)
```

CRLF/LF and blank-line-only representation differences do not change the digest. Historical Event mutation/reorder/insert/delete/allowed-metadata mutation does.

Unknown/unparseable fields are never silently dropped to make the digest pass.

R12 now requires representation-stability and mutation-detection fixtures.

## 3. P1R2-NF-02 — complete commit-local external process surface

Problem: hook/filter-only classification did not explicitly cover Git commit signing programs/helpers, which can execute before Review proof and may have uncontrolled external side effects.

Frozen repair:

```text
commit_local-v1 must positively classify every external executable/process reachable by the exact staging + local-commit path
```

Minimum surfaces include effective commit hooks, clean/process/LFS filters and commit-signing helpers/programs.

P1 Review-v1 commits explicitly disable commit signing (`--no-gpg-sign` equivalent). `Review-v1 signing-disabled` is part of the versioned Git persistence/commit-execution semantics and is bound through R6/R11.

Content-defining filters may not simply be disabled if that changes committed semantics; they must be mechanically contained with bound identity or cause fail-closed STOP.

R12 now includes a `commit.gpgSign=true` + custom signer external-side-effect attack and requires proof that the signer is never invoked by `commit_local-v1`.

## 4. Cross-contract updates

Updated contracts:

```text
R4  activation digest canonical serializer/classification
R5  complete reachable external-process surface + signing-disabled commit_local-v1
R6  signing/external-process mode in ReviewValidityClosure Git semantics
R11 signing/external-process coverage in git_state + subprocess/network classes
R12 explicit Round-3 fault/invariant tests
```

No lifecycle authority moved into Review. `state.py` remains event-type driven and Review metadata remains consistency/provenance only.

## 5. Current state

```text
Candidate 7 architecture: RETAIN
Architecture blockers: 0
HUMAN decisions: 0
Candidate 8 required: No

P1R2-NF-01: REPAIRED/FROZEN
P1R2-NF-02: REPAIRED/FROZEN
P1 implementation: NOT STARTED
Implementation activation: BLOCKED pending one focused independent re-review
```

The next review should be a narrow closure check of only these two Round-3 repairs plus cross-contract regressions. If that review returns no HIGH/MID and no HUMAN, the expected verdict is `READY_FOR_P1_IMPLEMENTATION` and contract-review looping should stop.
