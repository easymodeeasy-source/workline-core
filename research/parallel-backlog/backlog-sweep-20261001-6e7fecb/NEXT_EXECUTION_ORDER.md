NON-CANONICAL RESEARCH ARTIFACT
DO NOT MERGE INTO MAIN
Research baseline: 6e7fecb784a6ba1f49586761ab1038aa47d1738b

# Next execution order: backlog-sweep-20261001-6e7fecb

## Baseline

- Research baseline: `6e7fecb784a6ba1f49586761ab1038aa47d1738b` (tree `124ee98884bf707218292995a02d07dd659d5268`)
- Observed main at publication: `6e7fecb784a6ba1f49586761ab1038aa47d1738b`
- Baseline: current


## Assumptions

- Batch E / Gate 3 was in progress elsewhere during the run, and its content is unknown here. Nothing below assumes what it contains.
- `BACKLOG.md` is not authority. Normative authority is `registry.md` plus canonical Skills.
- R3's measurements come from synthetic Projects on a loaded machine. Counts and in-process CPU are robust; wall times are noisy. Real Project sizes are unknown.
- Every package below needs a delta refresh against the post-Batch-E main before it starts.

## Candidate implementation packages (detail: SYNTHESIS.md section 10)

| Package | One line | Gate |
|---|---|---|
| PK-0 | Pre-activation conformance: Work Candidate `desired_state` is null vs F2 (G-01); findings result channel (G-03); snapshot payload exposure (G-02) | GPT decision, Gate 3 owner |
| PK-1 | BL-006 v1 read-only status command | G-29..G-36 |
| PK-2 | BL-007 derivation indexing in `ProjectView` (equivalence-proven) | G-38 |
| PK-3 | BL-007 re-measurement after PK-1 | PK-1 |
| PK-4 | BL-007 bootstrap/registry reading-load change | G-37 + H-6 |
| PK-5 | BL-004 slice 1 (shape from R1 D-A / D-B / D-C) | G-04, G-08..G-18, H-1, H-7 |
| PK-6 | BL-003 Phase gate | G-19..G-25; PK-5 for a non-dead-end gate |
| PK-7 | BL-003 characterization tests / read-only diagnostic | none |
| PK-8 | BL-005 Work-slice totality check | Gate 3 active; G-28 |
| PK-9 | BL-005 residue (achievement, Phase evidence, time, content policy) | G-26, G-27, G-07, G-05; H-2, H-3 |

## Safe parallel packages (after Batch E lands and delta refresh)

- PK-1 + PK-2 + PK-7 in parallel with PK-5 (BL-004). There is no dependency edge between them and the file overlap is small (possibly `src/workline/validate.py`). Conditions: the v1 status Review section is limited to validity, counts and activation; BL-007 code work is limited to derivation indexing; BL-004 implementation starts only after its design decisions.
- PK-8 after Gate 3, in parallel with PK-1 and PK-2.
- Not parallel: PK-5 with PK-6, PK-5 with other Review-namespace work, and PK-4 with any other bootstrap change.

## Blockers

- Batch E / Gate 3 landing and a delta refresh (all packages).
- GPT design decisions (section 9 of SYNTHESIS.md) for PK-0, PK-1, PK-2, PK-4, PK-5, PK-6 and PK-9.
- Human-policy decisions H-1..H-7 (SYNTHESIS.md section 8) for PK-4, PK-5, PK-9 and the BL-005 split.
- BL-007 AI-side cost and real Project sizes: insufficient evidence, not measurable in this run.

## GPT review required

- Time-sensitive before Gate 3 activation: G-01, G-02, G-03.
- BL-004 design: G-04, G-08..G-18.
- BL-003: G-19..G-25.
- BL-005: G-04..G-07, G-26..G-28.
- BL-006/007: G-29..G-39.
- Hygiene: G-40.

## After GPT review

1. Route G-01..G-03 verdicts to the Gate 3 / Batch E owner before activation, if they still apply after the delta refresh.
2. Record the human-policy answers (H-1..H-7) with the owner, and apply BACKLOG lifecycle changes (for example, the BL-005 split) in a separate owner-approved BACKLOG change.
3. Delta-refresh this research against the post-Batch-E main and confirm or update each cited fact.
4. Open implementation sessions per package with exact-SHA bases: PK-1/PK-2 and PK-5 can run in separate sessions in parallel; PK-6 follows PK-5.
5. This research ref stays immutable and is never merged into main.
