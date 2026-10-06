# RB2 benchmark - BL-007 cold-start recovery

Completion Sprint tooling and evidence for RB2 (`WORKLINE_COMPLETION_SPRINT.md` §10, §36). It is **not**
Workline runtime authority: no runtime code, status, validation or routing reads anything here, and it never
edits the measured Workline root. The public-safe result lives in `WORKLINE_RB2_PERFORMANCE_MEASUREMENT.md`.

## What it measures, and what it does not

It measures deterministic local Workline recovery mechanics of one measured Workline root `R`:

| target | invocation |
|---|---|
| primary (RB1 status, cold) | `py -3 -I -B <R>/run-workline.py status <project-root> --json` |
| secondary (cold) | `py -3 -I -B <R>/run-workline.py validate-project <project-root>` |
| warm (diagnostic) | `runpy.run_path(<R>/run-workline.py)["activate"]()`, then `workline.status.render_json(workline.status.build_status(<project-root>))` repeated in one process |
| mechanical recovery sequence | `validate-registry <R>`, router resolution (`registry.resolve_skill` / `router_candidates` after `activate()`), `status --json`, `validate-project` - each a fresh process |

POSIX uses `python3 -I -B`. Every measured process runs from `<project-root>` as its working directory.

It does not benchmark LLM reasoning latency, token generation or model context loading, human reading time,
editor/IDE startup, or network latency (§36.3). Cold samples are cold-process, not cold-disk: the OS file cache
is not purged (§36.10).

## Files

- `generate.py` - the deterministic fixture generator (§36.5-§36.9). Contract `workline-rb2-fixture` v1, default
  seed 7007. Scales: `T` (12 Works, test only), `S` (30), `M` (300), `L` (3,000); ten Events per Work as target.
  Every canonical file comes from the measured root's own renderers and Review record constructors; IDs are valid
  Workline IDs derived from the seed (never `new_id()`), timestamps are synthetic. Each fixture is one local commit
  with no remote, plus exactly one uncommitted pending recovery record. It writes only under its target and refuses
  a non-empty target, a target overlapping the Workline root, or one outside `--allowed-base`.
- `run.py` - the runner. `admit` generates (when missing) and admits fixtures; `series` runs the protocol;
  `render` re-renders a `results.json`. The `_child` modes run inside measured processes and import nothing but
  `os`/`sys`/`time` before the measurement starts.

## Protocol (one `series`)

1. Environment and identity: harness SHA, measured Workline SHA (the runtime surfaces `src/`, `run-workline.py`,
   `registry.md`, `.claude/` must equal it), Python/Git/OS/CPU facts, compiled-bytecode count under `<R>/src`.
2. Quiet window (Windows): CPU / disk counters and the count of running `pytest` processes before, after and at
   every batch boundary; an `OFFICIAL` series refuses to start, and is discarded, when any test process runs.
3. Admission (§36.9): HEAD/tree match the manifest, the landed `validate-project` PASSes, status reads the fixture
   `stable_read` with validation `pass`; the exact status bytes become the reference every later sample must match.
4. Cold (§36.10): `--reps` fresh processes of status and validate-project per scale, scales round-robin with a
   rotating start, operations alternating first. Uninstrumented wall time is the headline.
5. Warm (§36.11): `--warm-calls` calls of the status API in one process per scale (diagnostic only).
6. Component (§36.12-§36.13): the launcher's own `main` in a benchmark-only child whose landed boundaries are
   wrapped at runtime with `perf_counter_ns` spans (inclusive and exclusive; nesting deduplicated; unassigned time
   reported). The instrumented status JSON must be byte-identical to the uninstrumented one. `--derivation-samples`
   adds samples that also wrap the per-entity scans (`ProjectView.events_for`, `relations_to`, `relations_from`,
   `phase_works`) - never headline, only Trigger A attribution.
7. Mechanical recovery sequence (§36.12), `--sequence-reps` times.
8. Git counts (§36.14): a wrapper of `gitcmd.run_git` / `run_git_bytes` in the component run, cross-checked with
   `GIT_TRACE2_EVENT` (temporary directory outside the Project, aggregated, then deleted). Any network family or
   socket stops the series.
9. Profile: one `cProfile` run per scale and operation - supporting evidence only.
10. Before/after every batch: worktree bytes (including the runtime record), the whole `.git`, HEAD, tree and
    porcelain status of every fixture must be unchanged.
11. Analysis: Trigger A (§36.17) on the uninstrumented cold M median, Trigger B (§36.18) per operation and A-I stage
    for S->M and M->L, and the frozen decision (§36.19).

Trigger B's noise rule: the excess is outside run-to-run noise when the conservative ratio Q1(larger) / Q3(smaller)
also exceeds 12x; a median ratio above 12x that fails it is `non_robust` and stops the decision (§36.32).

## Running it

```text
py -3 -B benchmarks/rb2/run.py admit  --workline-root <R> --fixtures <dir> --scales S M L
py -3 -B benchmarks/rb2/run.py series --workline-root <R> --fixtures <dir> --logs <dir> \
    --label OFFICIAL --measured-sha <sha> --scales S M L --reps 15 --warm-calls 30 \
    --component-samples 5 --derivation-samples 3 --sequence-reps 5 --suites-dir <suite dir>
py -3 -B benchmarks/rb2/run.py render --results <logs>/<run>/results.json --out WORKLINE_RB2_PERFORMANCE_MEASUREMENT.md
```

`--label SMOKE` runs are harness debugging only and never evidence. Fixtures and logs are disposable and belong
outside every worktree. Focused tests: `tests/test_rb2_benchmark.py` (reduced `T` and `S` scales only; set
`RB2_FIXTURE_BASE` to choose where their disposable fixtures go).
