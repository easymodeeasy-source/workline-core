# WORKLINE RB2 performance measurement - BL-007 cold-start recovery (OFFICIAL)

Completion Sprint evidence only (`WORKLINE_COMPLETION_SPRINT.md` §36). No Workline runtime code, status, validation or routing reads this file.

**What this does not claim (§36.3).** It measures deterministic local Workline recovery mechanics only. It does not benchmark LLM reasoning latency, token generation or model context loading, human reading time, editor/IDE startup, or network latency. `Cold-start recovery` here is not total agent wall-clock experience. Samples are cold-process, not cold-disk: the OS file cache is not purged.

## Identity

- Reviewed/Measured Workline SHA: `0c7b2690f71e860210096a3a8d6879bdfd2c65f4` (runtime surfaces at the harness commit are byte-identical to it: `src/`, `run-workline.py`, `registry.md`, `.claude/`)
- Measured Workline status: landed production main (RB1 landed; RB4/P5 landed)
- Benchmark harness SHA: `fa1efce323a11187a0131a5ed2c7c1f48abd8b29`
- Harness contract: `workline-rb2-harness` v1
- RB1 status command binding: `py -3 -I -B <workline-root>/run-workline.py status <project-root> --json`
- validate-project binding: `py -3 -I -B <workline-root>/run-workline.py validate-project <project-root>`
- RB1 status API binding (warm): `runpy.run_path(<workline-root>/run-workline.py)["activate"]()`, then `workline.status.render_json(workline.status.build_status(<project-root>))`
- Generator contract/seed: `workline-rb2-fixture` v1, seed `7007`
- Compiled bytecode under `<workline-root>/src` at measurement: 0 file(s)

## Environment

- Python: 3.14.4 (CPython, 64bit), invoked as `py -3 -I -B`
- Git: git version 2.54.0.windows.1; global config: core.autocrlf=true, core.fsmonitor=unset, core.untrackedCache=unset, core.preloadIndex=unset, feature.manyFiles=unset
- OS: Windows 11 (10.0.26300), AMD64
- CPU: Intel64 Family 6 Model 183 Stepping 1, GenuineIntel; logical CPUs: 32
- Page cache: not purged (cold-process, not cold-disk)
- Quiet window: granted by the Orchestrator (`MEASURE_SLOT_GRANTED`)
  - before: CPU% [13, 11, 4, 7, 12], disk idle% [100, 100, 100, 99, 99], disk queue [0, 0, 0, 0, 0], pytest processes 0, live sharded suites 0
  - after: CPU% [2, 6, 12, 20, 7], disk idle% [100, 100, 100, 99, 100], disk queue [0, 0, 0, 0, 0], pytest processes 0, live sharded suites 0
  - batch boundaries checked: 6; pytest processes seen at any boundary: 0

## Fixtures (S/M/L actual counts + digests)

| scale | Works | Phases | Roadmaps | completed / in progress / unstarted | roadmap relations | Related | Events | event-log bytes | entity bytes | Review records (bytes) | pending records (bytes) | logical digest |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S | 30 | 3 | 2 | 14 / 1 / 15 | 53 | 36 | 299 | 40,946 | 10,078 | 3 (2,987) | 1 (527) | `917ef05f289443ed` |
| M | 300 | 30 | 2 | 214 / 1 / 85 | 566 | 360 | 2999 | 410,866 | 97,351 | 3 (2,987) | 1 (527) | `3ca2ac43322ead8e` |
| L | 3000 | 300 | 2 | 2104 / 1 / 895 | 5696 | 3600 | 29999 | 4,112,026 | 978,757 | 3 (2,987) | 1 (527) | `eecf29f2106d5a2f` |

Each fixture: one local commit of the canonical files, no remote; only the intentional runtime pending record uncommitted; admitted only after the landed `validate-project` PASSed and status read it `stable_read` (§36.9).

- Pending fixture (§36.8): one pending `push-destination-pin` record, classified by RB1 as `unknown_or_invalid` (`push_destination_remote_missing`), affects_progression=False. A structurally valid record of a real owner whose read-only probe runs; a positive resumability proof would need a remote, which §36.9 excludes.
- Review fixture (§36.8): one Review Run (`work_formal`, generations 1 open -> 2 sealed) with its Receipt: state `sealed`, receipt `issued`, obligations `not_available_by_contract`; Work-terminal activation `absent`.
- Selection (every scale): current roadmap=selected, phase=selected, work=selected; next phase=selected, work=selected; blockers none; the current Work is the fixture's one in-flight Work: True.

## Cold process (headline, uninstrumented)

| scale | operation | n | first | median | q1 | q3 | p95 | max |
|---|---|---|---|---|---|---|---|---|
| S | status | 15 | 699.5 | **668.2** | 657.9 | 675.3 | n/a | 713.0 |
| S | validate | 15 | 445.4 | **433.4** | 427.0 | 443.8 | n/a | 463.3 |
| M | status | 15 | 1,493.9 | **1,463.2** | 1,452.2 | 1,488.1 | n/a | 1,546.5 |
| M | validate | 15 | 740.9 | **705.6** | 694.6 | 731.0 | n/a | 765.0 |
| L | status | 15 | 66,998.3 | **63,406.6** | 63,122.9 | 65,337.9 | n/a | 67,554.6 |
| L | validate | 15 | 22,404.2 | **21,290.8** | 21,073.3 | 21,598.9 | n/a | 22,617.3 |

Milliseconds. p95 is nearest-rank and reported only for n >= 20. Scales ran round-robin with a rotating start, and status / validate-project alternated first (§36.10).

## Warm process (diagnostic only)

| scale | calls | first | median | q3 | p95 | max |
|---|---|---|---|---|---|---|
| S | 30 | 351.6 | 251.8 | 253.6 | 265.3 | 351.6 |
| M | 30 | 1,159.9 | 1,056.3 | 1,062.9 | 1,072.0 | 1,159.9 |
| L | 30 | 62,163.2 | 62,466.9 | 66,871.0 | 68,184.9 | 68,367.5 |

## A-I stage table (component run, instrumented, exclusive time)

### status

| stage | S median ms | M median ms | L median ms |
|---|---|---|---|
| A bootstrap/root resolution | 301.9 | 302.6 | 299.5 |
| B implementation identity verification | 18.6 | 18.7 | 19.1 |
| C registry parse/validation | 11.5 | 11.9 | 12.3 |
| D router/Skill authority inventory | 2.5 | 2.5 | 2.7 |
| E canonical Project load | 21.3 | 185.6 | 1,956.9 |
| F validate-project | 13.4 | 378.2 | 40,126.5 |
| G RB1 status derivation | 30.1 | 291.2 | 21,819.0 |
| H local Git diagnostics (all Git subprocesses) | 194.6 | 192.9 | 208.6 |
| I final JSON/render serialization and CLI output | 4.5 | 4.8 | 7.0 |
| unassigned in-process (outside every span) | 0.0 | 0.0 | 0.0 |
| harness only (runpy load of the launcher, span installation; not A-I) | 10.0 | 9.5 | 10.0 |
| in-process total | 615.8 | 1,404.7 | 64,451.9 |
| interpreter start/exit + pipes (wall - in-process) | 63.4 | 61.9 | 65.5 |
| instrumented wall | 671.0 | 1,467.8 | 64,523.0 |

Span detail at M (status): label, stage, calls, inclusive ms, exclusive ms.

| span | stage | calls | inclusive | exclusive |
|---|---|---|---|---|
| `launcher.import_workline` | A | 6 | 293.8 | 293.8 |
| `launcher._load_helper` | A | 1 | 8.5 | 8.5 |
| `status._project` | A | 1 | 0.3 | 0.3 |
| `launcher._activate` | A | 1 | 309.5 | 0.2 |
| `launcher._binds_invocation_project` | A | 1 | 0.0 | 0.0 |
| `launcher._require_supported_python` | A | 1 | 0.0 | 0.0 |
| `launcher._require_isolated_mode` | A | 1 | 0.0 | 0.0 |
| `implementation.loaded_implementation_problem` | B | 3 | 13.9 | 13.9 |
| `launcher.loaded_implementation_problem` | B | 2 | 4.7 | 4.7 |
| `implementation.running_workline_root` | B | 1 | 4.6 | 0.1 |
| `implementation.configured_implementation_problem` | B | 2 | 9.2 | 0.0 |
| `registry.validate_registry` | C | 4 | 11.9 | 11.9 |
| `registry.authority_inventory` | D | 1 | 5.3 | 2.3 |
| `status._authority` | D | 1 | 15.0 | 0.1 |
| `state.ProjectView.load` | E | 2 | 185.6 | 185.6 |
| `validate.validate_structure` | F | 2 | 359.7 | 359.7 |
| `review.validate.validate_review` | F | 1 | 43.3 | 17.7 |
| `validate.validate_project_yaml` | F | 2 | 6.7 | 0.7 |
| `validate.validate_project` | F | 1 | 320.6 | 0.4 |
| `self_hosting.self_hosting_problem` | F | 1 | 0.1 | 0.1 |
| `status._validation` | F | 1 | 325.3 | 0.0 |
| `status._lifecycle` | G | 1 | 470.0 | 201.5 |
| `status.read_witnesses` | G | 2 | 106.7 | 59.8 |
| `status._review` | G | 1 | 41.4 | 15.2 |
| `status._pending` | G | 1 | 52.4 | 13.9 |
| `mutation.inspect_records` | G | 3 | 0.9 | 0.9 |
| `status.build_status` | G | 1 | 1,079.6 | 0.4 |
| `gitcmd.run_git` | H | 12 | 138.3 | 138.3 |
| `gitcmd.run_git_bytes` | H | 4 | 52.3 | 52.3 |
| `status._git_section` | H | 1 | 58.7 | 0.5 |
| `cli.main` | I | 1 | 1,083.9 | 4.2 |
| `status._assemble` | I | 1 | 0.5 | 0.5 |
| `status.render_json` | I | 1 | 0.1 | 0.1 |
| `harness.install_spans` | harness | 1 | 2.6 | 2.6 |

### validate

| stage | S median ms | M median ms | L median ms |
|---|---|---|---|
| A bootstrap/root resolution | 299.5 | 306.7 | 308.4 |
| B implementation identity verification | 13.8 | 14.1 | 14.0 |
| C registry parse/validation | 3.0 | 3.0 | 3.2 |
| D router/Skill authority inventory | 0.0 | 0.0 | 0.0 |
| E canonical Project load | 11.2 | 93.7 | 948.4 |
| F validate-project | 11.9 | 200.8 | 19,494.6 |
| G RB1 status derivation | 0.0 | 0.0 | 0.0 |
| H local Git diagnostics (all Git subprocesses) | 31.0 | 33.3 | 28.2 |
| I final JSON/render serialization and CLI output | 4.6 | 4.1 | 4.2 |
| unassigned in-process (outside every span) | 0.0 | 0.0 | 0.0 |
| harness only (runpy load of the launcher, span installation; not A-I) | 9.7 | 10.1 | 10.1 |
| in-process total | 387.6 | 666.0 | 20,805.4 |
| interpreter start/exit + pipes (wall - in-process) | 62.8 | 59.7 | 63.0 |
| instrumented wall | 458.9 | 733.7 | 20,864.0 |

Span detail at M (validate): label, stage, calls, inclusive ms, exclusive ms.

| span | stage | calls | inclusive | exclusive |
|---|---|---|---|---|
| `launcher.import_workline` | A | 6 | 297.6 | 297.6 |
| `launcher._load_helper` | A | 1 | 8.7 | 8.7 |
| `launcher._activate` | A | 1 | 318.1 | 0.3 |
| `launcher._require_project_configured_for_this_root` | A | 1 | 7.7 | 0.2 |
| `context.resolve_invocation_context` | A | 1 | 0.2 | 0.2 |
| `launcher._binds_invocation_project` | A | 1 | 0.0 | 0.0 |
| `launcher._require_supported_python` | A | 1 | 0.0 | 0.0 |
| `launcher._require_isolated_mode` | A | 1 | 0.0 | 0.0 |
| `implementation.loaded_implementation_problem` | B | 2 | 9.4 | 9.4 |
| `launcher.loaded_implementation_problem` | B | 2 | 4.6 | 4.6 |
| `implementation.configured_implementation_problem` | B | 2 | 9.4 | 0.0 |
| `implementation.require_configured_implementation` | B | 2 | 9.4 | 0.0 |
| `registry.validate_registry` | C | 1 | 3.0 | 3.0 |
| `state.ProjectView.load` | E | 1 | 93.7 | 93.7 |
| `validate.validate_structure` | F | 1 | 182.8 | 182.8 |
| `review.validate.validate_review` | F | 1 | 50.8 | 17.6 |
| `validate.validate_project` | F | 1 | 331.1 | 0.3 |
| `validate.validate_project_yaml` | F | 1 | 3.3 | 0.2 |
| `self_hosting.self_hosting_problem` | F | 1 | 0.1 | 0.1 |
| `gitcmd.run_git_bytes` | H | 2 | 33.3 | 33.3 |
| `cli.main` | I | 1 | 340.6 | 4.1 |
| `harness.install_spans` | harness | 2 | 2.6 | 2.6 |

Spans wrap the landed boundaries at runtime in a separate child running the launcher's own `main`; the instrumented status JSON was byte-identical to the uninstrumented one for every sample. Stage H is every Git subprocess wherever it was called from (its time is not also counted in the calling stage). Stage F includes `validate_structure` wherever it runs (also inside status lifecycle). Unassigned time is reported, not forced into a stage.

## Mechanical recovery end-to-end (§36.12)

Fresh-session recovery as the supported procedure runs it, one fresh process per step: `validate-registry <workline-root>` (bootstrap: configured root, registry read + validation), the router step (`activate()`, `registry.resolve_skill(skills/project-router)`, the router's call-time `router_candidates`, SKILL.md bytes read - never interpreted), `status --json` (A-I in one process), `validate-project`. A-D also run inside status itself; the status A-I table above is that process's split.

| scale | n | validate-registry | router | status | validate-project | total median | total max |
|---|---|---|---|---|---|---|---|
| S | 5 | 378.7 | 114.4 | 649.7 | 431.2 | **1,579.7** | 1,714.4 |
| M | 5 | 370.0 | 117.0 | 1,458.2 | 704.7 | **2,646.6** | 2,822.3 |
| L | 5 | 372.4 | 114.9 | 65,002.2 | 20,955.5 | **87,135.4** | 90,658.2 |

Router step in-process (median, first scale): activation 48.5 ms, router resolution 9.3 ms, inventory of 5 routable Skills 4.8 ms.

## Git command counts (per invocation)

| scale | operation | total | rev-parse | symbolic-ref | status | diff | ls-files | ls-tree | remote/config | other | hermetic (env-stripped) | Trace2 visible |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S | status | 16 | 7 | 3 | 1 | 0 | 1 | 2 | 2 | 0 | 4 | 12 |
| S | validate | 2 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 2 | 0 |
| M | status | 16 | 7 | 3 | 1 | 0 | 1 | 2 | 2 | 0 | 4 | 12 |
| M | validate | 2 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 2 | 0 |
| L | status | 16 | 7 | 3 | 1 | 0 | 1 | 2 | 2 | 0 | 4 | 12 |
| L | validate | 2 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 2 | 0 |

- M status: families {'ls-files': 1, 'ls-tree': 2, 'remote': 2, 'rev-parse': 7, 'status': 1, 'symbolic-ref': 3}; Git ms by calling span `review.validate.validate_review` 25.6, `status._git_section` 58.3, `status._pending` 32.2, `status._review` 25.8, `status.read_witnesses` 45.9
- M validate: families {'ls-tree': 1, 'rev-parse': 1}; Git ms by calling span `review.validate.validate_review` 33.3

Counted by a benchmark-only wrapper of `gitcmd.run_git` / `run_git_bytes` in the component run (all Git goes through them), cross-checked with Git Trace2 `start` events of an uninstrumented run. Trace2 cannot see the Review hermetic (class A/B) commands: they run with every inherited `GIT_*` variable stripped by design, so the Trace2 total is lower by exactly those. No network family was observed; no socket was opened.

## Trigger A (§36.17)

### status - denominator: uninstrumented cold M median 1,463.2 ms

| candidate | numerator ms | fraction | > 50% | removable without semantic change | support |
|---|---|---|---|---|---|
| repeated canonical Project load (ProjectView.load) within one command | 92.8 | 6.3% | no | the second load reads the same files between the same B0/B1 witnesses; one immutable snapshot can be reused (§36.22 step 2) | component span state.ProjectView.load: 2 call(s), 185.6 ms exclusive |
| repeated structure validation (validate_structure) within one command | 179.9 | 12.3% | no | the same validation over the same snapshot; its result can be reused (§36.22 step 1) | component span validate.validate_structure: 2 call(s), 359.7 ms exclusive |
| repeated registry validation (validate_registry) within one command | 8.9 | 0.6% | no | the same registry bytes validated again within one command (§36.22 step 1) | component span registry.validate_registry: 4 call(s), 11.9 ms exclusive |
| repeated configured-implementation identity check within one command | 4.6 | 0.3% | no | the same question of the same loaded modules (§36.22 step 1) | component span implementation.configured_implementation_problem: 2 call(s), 9.2 ms inclusive |
| identical Git commands repeated within one command (B0/B1 witness re-reads excluded) | 22.1 | 1.5% | no | the same local question asked again; batching equivalent reads keeps the questions (§36.22 step 3) | component Git wrapper: 2 repeated identical command(s) |
| per-entity full Event-log scans (ProjectView.events_for) behind state derivation | 534.2 | 36.5% | no | each call rescans a whole immutable list of the one snapshot; one grouping pass per command replaces the repeats (an in-memory index: §36.22 step 4, after steps 1-3) | derivation-span variant (3 sample(s), median): 12212 calls, 534.2 ms exclusive (per-call wrapper overhead included: an over-estimate) |
| per-entity full roadmap-relation scans (ProjectView.relations_to) | 16.0 | 1.1% | no | each call rescans a whole immutable list of the one snapshot; one grouping pass per command replaces the repeats (an in-memory index: §36.22 step 4, after steps 1-3) | derivation-span variant (3 sample(s), median): 1884 calls, 16.1 ms exclusive (per-call wrapper overhead included: an over-estimate) |
| per-Phase full Work scans (ProjectView.phase_works) | 11.7 | 0.8% | no | each call rescans a whole immutable list of the one snapshot; one grouping pass per command replaces the repeats (an in-memory index: §36.22 step 4, after steps 1-3) | derivation-span variant (3 sample(s), median): 693 calls, 11.7 ms exclusive (per-call wrapper overhead included: an over-estimate) |
| BOUND: every local Git subprocess of the command (stage H) | 192.9 | 13.2% | no | n/a (upper bound, not one derivation) | component stage H median; not one derivation - the B0/B1 witnesses and each distinct question are semantic |
| BOUND: all canonical load + validation + status derivation (stages E+F+G) | 855.1 | 58.4% | yes | n/a (upper bound, not one derivation) | component stage medians E+F+G; not one derivation |
| per-entity full Event-log scans (ProjectView.events_for) behind state derivation | 425.4 | 29.1% | no | one grouping of the immutable Event list per command replaces each O(E) rescan (an in-memory index: §36.22 step 4, after steps 1-3) | cProfile (supporting): 12212 calls, 30.3% of profiled time; estimate = share x component in-process median (profiler overhead inflates call-heavy code) |

Trigger A (status): **false**

### validate - denominator: uninstrumented cold M median 705.6 ms

| candidate | numerator ms | fraction | > 50% | removable without semantic change | support |
|---|---|---|---|---|---|
| repeated canonical Project load (ProjectView.load) within one command | 0.0 | 0.0% | no | n/a (no repeat) | component span state.ProjectView.load: 1 call(s), 93.7 ms exclusive |
| repeated structure validation (validate_structure) within one command | 0.0 | 0.0% | no | n/a (no repeat) | component span validate.validate_structure: 1 call(s), 182.8 ms exclusive |
| repeated registry validation (validate_registry) within one command | 0.0 | 0.0% | no | n/a (no repeat) | component span registry.validate_registry: 1 call(s), 3.0 ms exclusive |
| repeated configured-implementation identity check within one command | 4.7 | 0.7% | no | the same question of the same loaded modules (§36.22 step 1) | component span implementation.configured_implementation_problem: 2 call(s), 9.4 ms inclusive |
| identical Git commands repeated within one command (B0/B1 witness re-reads excluded) | 0.0 | 0.0% | no | n/a (no repeat) | component Git wrapper: 0 repeated identical command(s) |
| per-entity full Event-log scans (ProjectView.events_for) behind state derivation | 171.2 | 24.3% | no | each call rescans a whole immutable list of the one snapshot; one grouping pass per command replaces the repeats (an in-memory index: §36.22 step 4, after steps 1-3) | derivation-span variant (3 sample(s), median): 3934 calls, 171.2 ms exclusive (per-call wrapper overhead included: an over-estimate) |
| per-entity full roadmap-relation scans (ProjectView.relations_to) | 4.7 | 0.7% | no | each call rescans a whole immutable list of the one snapshot; one grouping pass per command replaces the repeats (an in-memory index: §36.22 step 4, after steps 1-3) | derivation-span variant (3 sample(s), median): 560 calls, 4.7 ms exclusive (per-call wrapper overhead included: an over-estimate) |
| per-Phase full Work scans (ProjectView.phase_works) | 3.2 | 0.5% | no | each call rescans a whole immutable list of the one snapshot; one grouping pass per command replaces the repeats (an in-memory index: §36.22 step 4, after steps 1-3) | derivation-span variant (3 sample(s), median): 215 calls, 3.2 ms exclusive (per-call wrapper overhead included: an over-estimate) |
| BOUND: every local Git subprocess of the command (stage H) | 33.3 | 4.7% | no | n/a (upper bound, not one derivation) | component stage H median; not one derivation - the B0/B1 witnesses and each distinct question are semantic |
| BOUND: all canonical load + validation + status derivation (stages E+F+G) | 294.6 | 41.8% | no | n/a (upper bound, not one derivation) | component stage medians E+F+G; not one derivation |
| per-entity full Event-log scans (ProjectView.events_for) behind state derivation | 139.7 | 19.8% | no | one grouping of the immutable Event list per command replaces each O(E) rescan (an in-memory index: §36.22 step 4, after steps 1-3) | cProfile (supporting): 3934 calls, 21.0% of profiled time; estimate = share x component in-process median (profiler overhead inflates call-heavy code) |

Trigger A (validate): **false**

**Trigger A: false**

Rule: one concrete removable derivation, deduplicated for nesting, strictly above 50% of the uninstrumented cold M median; candidates are never added together; BOUND rows only show how far a whole family could reach; profiler rows are supporting estimates (cProfile inflates call-heavy code), never the proof.

## Trigger B (§36.18)

| pair | subject | Works x | Events x | median small | median large | median ratio | conservative Q1(L)/Q3(S) | verdict |
|---|---|---|---|---|---|---|---|---|
| S->M | cold status (wall) | 10.0 | 10.03 | 668.2 | 1,463.2 | 2.19x | 2.15x | false |
| S->M | status stage A | 10.0 | 10.03 | 301.9 | 302.6 | 1.00x | 0.97x | false |
| S->M | status stage B | 10.0 | 10.03 | 18.6 | 18.7 | 1.01x | 0.96x | false |
| S->M | status stage C | 10.0 | 10.03 | 11.5 | 11.9 | 1.03x | 0.96x | false |
| S->M | status stage D | 10.0 | 10.03 | 2.5 | 2.5 | 0.99x | 0.97x | false |
| S->M | status stage E | 10.0 | 10.03 | 21.3 | 185.6 | 8.70x | 8.31x | false |
| S->M | status stage F | 10.0 | 10.03 | 13.4 | 378.2 | 28.23x | 27.63x | true |
| S->M | status stage G | 10.0 | 10.03 | 30.1 | 291.2 | 9.67x | 9.43x | false |
| S->M | status stage H | 10.0 | 10.03 | 194.6 | 192.9 | 0.99x | 0.93x | false |
| S->M | status stage I | 10.0 | 10.03 | 4.5 | 4.8 | 1.07x | 1.05x | false |
| S->M | cold validate (wall) | 10.0 | 10.03 | 433.4 | 705.6 | 1.63x | 1.57x | false |
| S->M | validate stage A | 10.0 | 10.03 | 299.5 | 306.7 | 1.02x | 0.99x | false |
| S->M | validate stage B | 10.0 | 10.03 | 13.8 | 14.1 | 1.02x | 0.96x | false |
| S->M | validate stage C | 10.0 | 10.03 | 3.0 | 3.0 | 1.01x | 0.94x | false |
| S->M | validate stage D | 10.0 | 10.03 | n/a | n/a | n/a | n/a | unmeasurable |
| S->M | validate stage E | 10.0 | 10.03 | 11.2 | 93.7 | 8.35x | 8.01x | false |
| S->M | validate stage F | 10.0 | 10.03 | 11.9 | 200.8 | 16.88x | 16.61x | true |
| S->M | validate stage G | 10.0 | 10.03 | n/a | n/a | n/a | n/a | unmeasurable |
| S->M | validate stage H | 10.0 | 10.03 | 31.0 | 33.3 | 1.07x | 0.86x | false |
| S->M | validate stage I | 10.0 | 10.03 | 4.6 | 4.1 | 0.89x | 0.88x | false |
| S->M | warm status (diagnostic only) | 10.0 | 10.03 | 251.8 | 1,056.3 | 4.20x | 4.14x | false |
| M->L | cold status (wall) | 10.0 | 10.00 | 1,463.2 | 63,406.6 | 43.33x | 42.42x | true |
| M->L | status stage A | 10.0 | 10.00 | 302.6 | 299.5 | 0.99x | 0.97x | false |
| M->L | status stage B | 10.0 | 10.00 | 18.7 | 19.1 | 1.02x | 1.01x | false |
| M->L | status stage C | 10.0 | 10.00 | 11.9 | 12.3 | 1.04x | 1.00x | false |
| M->L | status stage D | 10.0 | 10.00 | 2.5 | 2.7 | 1.08x | 1.04x | false |
| M->L | status stage E | 10.0 | 10.00 | 185.6 | 1,956.9 | 10.54x | 10.28x | false |
| M->L | status stage F | 10.0 | 10.00 | 378.2 | 40,126.5 | 106.09x | 102.70x | true |
| M->L | status stage G | 10.0 | 10.00 | 291.2 | 21,819.0 | 74.92x | 71.17x | true |
| M->L | status stage H | 10.0 | 10.00 | 192.9 | 208.6 | 1.08x | 1.03x | false |
| M->L | status stage I | 10.0 | 10.00 | 4.8 | 7.0 | 1.47x | 1.42x | false |
| M->L | cold validate (wall) | 10.0 | 10.00 | 705.6 | 21,290.8 | 30.17x | 28.83x | true |
| M->L | validate stage A | 10.0 | 10.00 | 306.7 | 308.4 | 1.01x | 1.00x | false |
| M->L | validate stage B | 10.0 | 10.00 | 14.1 | 14.0 | 0.99x | 0.95x | false |
| M->L | validate stage C | 10.0 | 10.00 | 3.0 | 3.2 | 1.06x | 0.93x | false |
| M->L | validate stage D | 10.0 | 10.00 | n/a | n/a | n/a | n/a | unmeasurable |
| M->L | validate stage E | 10.0 | 10.00 | 93.7 | 948.4 | 10.12x | 9.39x | false |
| M->L | validate stage F | 10.0 | 10.00 | 200.8 | 19,494.6 | 97.06x | 96.86x | true |
| M->L | validate stage G | 10.0 | 10.00 | n/a | n/a | n/a | n/a | unmeasurable |
| M->L | validate stage H | 10.0 | 10.00 | 33.3 | 28.2 | 0.85x | 0.76x | false |
| M->L | validate stage I | 10.0 | 10.00 | 4.1 | 4.2 | 1.03x | 0.98x | false |
| M->L | warm status (diagnostic only) | 10.0 | 10.00 | 1,056.3 | 62,466.9 | 59.14x | 58.56x | true |

Frozen condition: median ratio > 12x AND the excess outside observed run-to-run noise; the noise bound is the interquartile spread (conservative ratio Q1 of the larger scale over Q3 of the smaller must also exceed 12x). `non_robust` = median above 12x but inside noise (STOP, §36.32). Warm rows are diagnostic and never decide.

**Trigger B: true**

## Decision

**MEASURED_TRIGGER_B**

## Canonical Project mutation during measurement

none - 18 before/after identity check(s) of every fixture (worktree bytes incl. the runtime record, the whole `.git`, HEAD, tree, porcelain status) were unchanged.

## Limitations

- Cold-process, not cold-disk: the OS file cache is not purged, so repeated samples read warm file data.
- One machine, one OS: absolute times (especially Windows process creation, which every Git subprocess and the py launcher pay) are specific to it; the trigger decisions rest on ratios and shares measured on it.
- The quiet window pauses test processes; other non-test processes of the machine still run and are not controlled beyond the recorded CPU / disk samples.
- The canonical invocation writes no bytecode (-B) and none is present, so every cold sample compiles the imported Workline modules from source; that is the supported path, and it is measured as such (stage A).
- Component spans are instrumented: wrapper overhead is included, and the child preloads `runpy` (with `importlib.util`), so stage A import time is slightly under-stated there; headline numbers are uninstrumented.
- Derivation-span samples wrap very frequently called scans: their numerators over-state the scan cost a little.
- The profiler run is supporting evidence only; cProfile inflates call-heavy code.
- Git Trace2 cannot see the Review hermetic (class A/B) commands, which strip every inherited GIT_* variable by design; the complete count is the component wrapper's.
- Byte and count observations come from the generated fixture files, not from read counters in production readers.
- The pending fixture is a real owner's structurally valid record classified `unknown_or_invalid`: a positively resumable record would need a remote, which the benchmark Project must not have (§36.8-§36.9).
- The Review fixture is one P1-shape Run (no P4 Run, no Work-terminal activation): Review status cost is covered at O(1), not every Review contract path.
- Warm results are diagnostic only and never decide BL-007.

## Commands (portable form)

- cold status: `py -3 -I -B <workline-root>/run-workline.py status <project-root> --json`
- cold validate-project: `py -3 -I -B <workline-root>/run-workline.py validate-project <project-root>`
- working directory: `<project-root>`
- component child: `py -3 -I -B <workline-root>/benchmarks/rb2/run.py _child component <launcher> <out> plain -- status <project-root> --json`
- warm child: `py -3 -I -B <workline-root>/benchmarks/rb2/run.py _child warm <launcher> <out> <project-root> <calls>`
- Git Trace2: `cold command with GIT_TRACE2_EVENT=<temporary directory outside the Project>`

## Raw cold samples (ms)

- S status: 699.5, 668.2, 713.0, 701.7, 663.5, 670.1, 676.9, 657.9, 666.4, 657.9, 673.7, 648.9, 672.3, 649.5, 644.5
- S validate: 445.4, 430.3, 452.3, 463.3, 417.9, 435.8, 422.7, 418.4, 424.4, 433.4, 429.6, 442.1, 429.9, 452.0, 438.4
- M status: 1493.9, 1545.5, 1534.7, 1546.5, 1459.4, 1451.6, 1458.8, 1448.1, 1450.1, 1450.2, 1482.4, 1463.9, 1467.1, 1463.2, 1452.9
- M validate: 740.9, 765.0, 752.3, 751.6, 708.8, 702.5, 692.9, 707.9, 703.4, 696.3, 689.4, 705.6, 689.3, 721.1, 686.3
- L status: 66998.3, 66810.7, 67554.6, 66437.7, 63708.4, 63340.8, 63406.6, 64238.2, 63060.6, 63004.1, 63698.7, 63290.2, 63172.9, 62352.0, 63072.9
- L validate: 22404.2, 22515.6, 21739.7, 22617.3, 21189.4, 21412.7, 20742.1, 21290.8, 21458.2, 21228.9, 20787.1, 21208.3, 20769.7, 20957.2, 21329.4


## Measurement provenance and decision handling (Execution Orchestrator)

This section was added by the Orchestrator. Everything above is the harness's own `summary.md` of the official series, byte for byte. `run.py render` over the same `results.json` reproduces it except for key ordering: that file is saved with sorted keys, so the fixture rows render L/M/S and two config/command lines change place. No value differs.

**Official series used: attempt 3.**

| Item | Value |
|---|---|
| Label | `OFFICIAL` |
| Measured Workline | `0c7b2690f71e860210096a3a8d6879bdfd2c65f4`, landed production main (RB1 and RB4/P5 landed) |
| Harness | `fa1efce323a11187a0131a5ed2c7c1f48abd8b29` (harness `472cf9d` carried byte-identically onto the landed main) |
| Window | 2026-10-06 05:02:51Z → 06:23:47Z |
| `results.json` sha256 | `95ff483b1f86e89377724994f1745122c38cdfcaa9cdb0d6e4579ebbced22860` |
| `analysis.json` sha256 | `30e08b444456ec3340a4cfdb8d8f1eed3679f07fe157be81c3c0039fb54f8755` |

During that window:

- No other test process ran: no N4 test, suite, heavy run or other measurement.
- The harness quiet checks passed before, after and at all 6 batch boundaries.

**Earlier attempts (preserved, not evidence).**

The harness writes `results.json` only when a series ends, so neither interrupted attempt left any timing sample. Both are kept as `INTERRUPTED-NOT-BL007-EVIDENCE` logs with a note:

| Attempt | Started | Interruption | Reached |
|---|---|---|---|
| 1 | 01:27:20Z | host blue screen, bugcheck `0x0000007E`; unexpected restart at 02:33Z | 15/15 cold reps, warm, component 3/5 |
| 2 | 03:37:41Z | host blue screen, bugcheck `0x00020001`; unexpected restart at 04:06Z | 15/15 cold reps, warm |

- A planned operating-system update restart followed attempt 2 at 04:50Z. The OS build in the environment record above is the post-update one.
- The Human approved attempt 3 after being told about both crashes.
- An earlier, pre-RB1-landing series (2026-10-05) was revoked by the Control Plane and is not evidence either.

**Decision handling.** The frozen decision is `MEASURED_TRIGGER_B` (§36.19), which is `OPTIMIZATION_TRIGGERED`:

- **Trigger A is false.** No single removable derivation exceeds 50% of either M median. The largest is the per-entity Event-log scan behind status derivation, at 36.5% of the cold M status median.
- **Trigger B is true and robust:**
  - cold status M→L: 43.33× (conservative 42.42×);
  - cold validate-project M→L: 30.17× (conservative 28.83×);
  - stage F (structure validation) S→M: 28.23× status / 16.88× validate; M→L: 106.09× / 97.06×;
  - stage G (status derivation) M→L: 74.92×.

Per §36.21 and the Control Plane dispatch, the baseline candidate stops here:

- No production file is changed.
- No optimization or §36.21 hypothesis is frozen in this candidate.
- The optimization path, including whether and how to freeze a §36.21 hypothesis under the §36.22 decision tree, is returned to the Control Plane.

BL-007 is not closed. `BACKLOG.md` is not touched.


---

# §36.21 Frozen optimization hypothesis: RB2-H1

This checkpoint freezes the optimization hypothesis **before** any production optimization byte exists in this history (§36.21). The hypothesis was frozen by the Control Plane after it accepted the baseline above (`MEASURED_TRIGGER_B`); it is committed here verbatim in substance. Everything above this line is the accepted baseline exactly as committed in `a626ac75`.

| Item | Frozen value |
|---|---|
| ID | **RB2-H1** |
| Measured bottleneck | `ProjectView.events_for` repeatedly scans the complete already-loaded immutable Event list, once per entity / state derivation. |
| Expected mechanism | One per-ProjectView in-memory entity → Events index, built from the exact already-loaded Event sequence. It preserves Event object identity and log order. |
| Exact intended production surface | `src/workline/state.py`, `ProjectView.events_for`. Nothing else. |
| Expected Git / load effect | None: no Git command and no canonical load is added, removed or changed. |
| Allowed decision-tree step | §36.22 step 4 only. The baseline showed steps 1–3 cannot remove the validate-project Trigger B (see below). |

**Baseline support** (all from the accepted official series above):

- cold status M median 1,463.2 ms; cold validate-project M median 705.6 ms;
- the `events_for` measured candidate is **36.5%** of the M status median and **24.3%** of the M validate median;
- Trigger B is robust in the wall scaling (M→L cold status 43.33×, conservative 42.42×; cold validate 30.17×, conservative 28.83×) and in stages F and G (status F 106.09×, G 74.92×, validate F 97.06× at M→L; F also at S→M).

**Why step 4 now.** For validate-project, the baseline shows:

- repeated `ProjectView.load` within one command: 0;
- repeated `validate_structure`: 0;
- repeated registry validation: 0;
- repeated identical Git commands: 0.

Yet validate-project still scales 30.17× from M to L. Steps 1–3 therefore cannot remove its Trigger B, and the first shared optimization able to explain both validate and status is the Event lookup index.

**Semantic invariants (must hold exactly):**

- `self.events` remains the canonical authority;
- the same Event objects are returned, in the same order;
- each call returns a new list;
- an empty lookup is unchanged (`[]`);
- status, validation and lifecycle semantics are unchanged;
- no persistent state, no network, no cross-session authority.

**Rollback / stop condition.** Do not land H1, and return to the Control Plane, if either holds:

- a smoke run does not materially collapse the Event-scan super-linearity;
- semantic equality fails.

**Not authorized under RB2-H1:**

- persistent cache, disk index, cache file or background indexing;
- new canonical state, or an Event-format change;
- any change to validation, status JSON, lifecycle, Git or B0/B1;
- network;
- `relations_to` / `relations_from` or `phase_works` indexing;
- a broad ProjectView redesign;
- §36.22 step 1–3 micro-optimizations.


---

# RB2-H1 post-optimization evidence (§36.25)

## Provenance: what ran where

| Item | Value |
|---|---|
| Accepted baseline runtime | `0c7b2690f71e860210096a3a8d6879bdfd2c65f4` (series `official-20261006-140251`, baseline commit `a626ac75`) |
| Hypothesis checkpoint (§36.21) | `5aa5c4177fa19369b2b880c087535965e51023d9`, committed before any production byte of H1 |
| **Originally measured H1 runtime** | `29c5a24d5fb2065f63cc51dcfb0168a138645015`. The official post-H1 series **executed on this commit** (preserved on `exec/rb2-measure-20261006`). |
| **Final compliant H1 runtime commit** | `ca008f9d1437c2773cb25d8f0e3d11f78dd051fb` (on the checkpoint) |
| Runtime byte identity | `git diff 29c5a24d ca008f9d -- src run-workline.py registry.md .claude tests benchmarks` is empty. `src/workline/state.py` blob `1603cdc9198f…` is the same in both. The only tree difference is this measurement summary (the §36.21 section). |
| Official post-H1 series | `OFFICIAL`, 2026-10-06 07:04:50Z → 07:15:20Z, exclusive window: 0 pytest at the before/after checks and all 6 boundaries; no host crash |
| Raw files | `results.json` sha256 `b1d56e6385626ce553b94a5c01fb31abc279d8eb9a3e5644abe210d9f08d4c11`; `analysis.json` sha256 `9c5bb26004ab076725db01fce8890d79cc91235155d32c5e6418f5d162722be5` |

**What this says and does not say.**

- The measurement was not rerun for `ca008f9d`, and none is claimed for it.
- It stands as evidence for `ca008f9d` because its measured production runtime bytes are identical to those of `29c5a24d`.

## Before / after (cold-process medians, ms, n=15)

| Scale | Status before | Status after | Validate before | Validate after |
|---|---|---|---|---|
| S | 668.2 | 701.9 | 433.4 | 454.1 |
| M | 1,463.2 | **987.6** | 705.6 | **565.5** |
| L | 63,406.6 | **6,828.5** | 21,290.8 | **2,629.7** |

M improves beyond run-to-run noise: after-Q3 is below before-Q1 (status 999.3 < 1,452.2; validate 577.0 < 694.6).

## Trigger B after H1, frozen §36.18 (operation OR stage, S→M and M→L)

**Wall rows.**

| Pair | Before | After |
|---|---|---|
| M→L cold status | 43.33× (42.42×) | **6.91× (6.77×): false** |
| M→L cold validate | 30.17× (28.83×) | **4.65× (4.49×): false** |
| S→M cold status | — | 1.41×: false |
| S→M cold validate | — | 1.25×: false |

**Stage rows.**

| Pair / stage | Before | After |
|---|---|---|
| M→L status stage F | 106.09× | **43.00× (42.76×): true** |
| M→L status stage G | 74.92× | **17.42× (17.37×): true** |
| M→L validate stage F | 97.06× | **33.11× (32.22×): true** |

S→M stage F was true before (28.23× / 16.88×); every S→M row is now false.

```
GLOBAL_TRIGGER_B_POST_H1    = TRUE   (stage F/G rows remain above the frozen §36.18 threshold)
COLD_WALL_TRIGGER_B_POST_H1 = FALSE  (both status and validate-project)
```

**Trigger A** stays false. `events_for` fell from 36.5% to 0.4% of the cold M status median (534.2 → 3.5 ms exclusive over 12,212 calls).

## §36.24 equivalence on the identical fixtures

On S, M and L, the admission references of the baseline series (runtime `0c7b2690`) and the post-H1 series (runtime `29c5a24d`) are identical:

- status JSON bytes, `status_stdout_sha256` and `status_lf_sha256`;
- validate-project stdout;
- admission facts.

Git command counts are identical (status 16, validate 2). There was no network and no fixture mutation (18 integrity checks), and instrumented status JSON is byte-identical to uninstrumented.

## §36.25 reading and classification

| §36.25 criterion | Result |
|---|---|
| Intended measured bottleneck falls materially | yes (`events_for` 36.5% → 0.4% at M) |
| Representative cold-process M improves beyond noise | yes |
| Trigger B scaling shape improves | yes (wall 43.33× → 6.91× and 30.17× → 4.65×; stage F 106.09× → 43.00×, G 74.92× → 17.42×, validate F 97.06× → 33.11×) |
| No required stage merely skipped | yes (A-I all present) |
| Semantic / full regression gates | focused gates PASS; the Full suite of the final candidate is pending |

```
RB2_H1_SUPPORTED
MEASURED_OPTIMIZED_CANDIDATE
FULL_SUITE_PENDING
GLOBAL_TRIGGER_B_POST_H1 = TRUE
COLD_WALL_TRIGGER_B_POST_H1 = FALSE
```

The residual stage Trigger B does not authorize another optimization (Control Plane). `MEASURED_OPTIMIZED` becomes final only after all four of:

- the exact final candidate's Full regression PASS;
- Control Plane final review PASS;
- landing;
- consistent closeout of BL-007 / BACKLOG.

BL-007 is not resolved here, and `BACKLOG.md` is not touched.

## Post-H1 harness summary (verbatim; headings demoted one level; measured runtime `29c5a24d`)

The harness's own decision line below, `MEASURED_TRIGGER_B`, is computed over every wall and stage row. It is the `GLOBAL_TRIGGER_B_POST_H1 = TRUE` above.

## WORKLINE RB2 performance measurement - BL-007 cold-start recovery (OFFICIAL)

Completion Sprint evidence only (`WORKLINE_COMPLETION_SPRINT.md` §36). No Workline runtime code, status, validation or routing reads this file.

**What this does not claim (§36.3).** It measures deterministic local Workline recovery mechanics only. It does not benchmark LLM reasoning latency, token generation or model context loading, human reading time, editor/IDE startup, or network latency. `Cold-start recovery` here is not total agent wall-clock experience. Samples are cold-process, not cold-disk: the OS file cache is not purged.

### Identity

- Reviewed/Measured Workline SHA: `29c5a24d5fb2065f63cc51dcfb0168a138645015` (runtime surfaces at the harness commit are byte-identical to it: `src/`, `run-workline.py`, `registry.md`, `.claude/`)
- Measured Workline status: RB2-H1 candidate on landed main 0c7b2690 (not landed)
- Benchmark harness SHA: `29c5a24d5fb2065f63cc51dcfb0168a138645015`
- Harness contract: `workline-rb2-harness` v1
- RB1 status command binding: `py -3 -I -B <workline-root>/run-workline.py status <project-root> --json`
- validate-project binding: `py -3 -I -B <workline-root>/run-workline.py validate-project <project-root>`
- RB1 status API binding (warm): `runpy.run_path(<workline-root>/run-workline.py)["activate"]()`, then `workline.status.render_json(workline.status.build_status(<project-root>))`
- Generator contract/seed: `workline-rb2-fixture` v1, seed `7007`
- Compiled bytecode under `<workline-root>/src` at measurement: 0 file(s)

### Environment

- Python: 3.14.4 (CPython, 64bit), invoked as `py -3 -I -B`
- Git: git version 2.54.0.windows.1; global config: core.autocrlf=true, core.fsmonitor=unset, core.untrackedCache=unset, core.preloadIndex=unset, feature.manyFiles=unset
- OS: Windows 11 (10.0.26300), AMD64
- CPU: Intel64 Family 6 Model 183 Stepping 1, GenuineIntel; logical CPUs: 32
- Page cache: not purged (cold-process, not cold-disk)
- Quiet window: granted by the Orchestrator (`MEASURE_SLOT_GRANTED`)
  - before: CPU% [11, 8, 10, 23, 22], disk idle% [99, 99, 99, 98, 97], disk queue [0, 0, 0, 0, 0], pytest processes 0, live sharded suites 0
  - after: CPU% [2, 22, 20, 5, 29], disk idle% [99, 98, 99, 100, 100], disk queue [0, 0, 0, 0, 0], pytest processes 0, live sharded suites 0
  - batch boundaries checked: 6; pytest processes seen at any boundary: 0

### Fixtures (S/M/L actual counts + digests)

| scale | Works | Phases | Roadmaps | completed / in progress / unstarted | roadmap relations | Related | Events | event-log bytes | entity bytes | Review records (bytes) | pending records (bytes) | logical digest |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S | 30 | 3 | 2 | 14 / 1 / 15 | 53 | 36 | 299 | 40,946 | 10,078 | 3 (2,987) | 1 (527) | `917ef05f289443ed` |
| M | 300 | 30 | 2 | 214 / 1 / 85 | 566 | 360 | 2999 | 410,866 | 97,351 | 3 (2,987) | 1 (527) | `3ca2ac43322ead8e` |
| L | 3000 | 300 | 2 | 2104 / 1 / 895 | 5696 | 3600 | 29999 | 4,112,026 | 978,757 | 3 (2,987) | 1 (527) | `eecf29f2106d5a2f` |

Each fixture: one local commit of the canonical files, no remote; only the intentional runtime pending record uncommitted; admitted only after the landed `validate-project` PASSed and status read it `stable_read` (§36.9).

- Pending fixture (§36.8): one pending `push-destination-pin` record, classified by RB1 as `unknown_or_invalid` (`push_destination_remote_missing`), affects_progression=False. A structurally valid record of a real owner whose read-only probe runs; a positive resumability proof would need a remote, which §36.9 excludes.
- Review fixture (§36.8): one Review Run (`work_formal`, generations 1 open -> 2 sealed) with its Receipt: state `sealed`, receipt `issued`, obligations `not_available_by_contract`; Work-terminal activation `absent`.
- Selection (every scale): current roadmap=selected, phase=selected, work=selected; next phase=selected, work=selected; blockers none; the current Work is the fixture's one in-flight Work: True.

### Cold process (headline, uninstrumented)

| scale | operation | n | first | median | q1 | q3 | p95 | max |
|---|---|---|---|---|---|---|---|---|
| S | status | 15 | 713.5 | **701.9** | 687.5 | 711.2 | n/a | 726.3 |
| S | validate | 15 | 463.3 | **454.1** | 452.8 | 462.9 | n/a | 479.1 |
| M | status | 15 | 987.6 | **987.6** | 974.9 | 999.3 | n/a | 1,029.8 |
| M | validate | 15 | 562.6 | **565.5** | 560.4 | 577.0 | n/a | 585.6 |
| L | status | 15 | 6,901.6 | **6,828.5** | 6,763.8 | 6,962.6 | n/a | 7,189.8 |
| L | validate | 15 | 2,669.9 | **2,629.7** | 2,592.9 | 2,669.3 | n/a | 2,694.7 |

Milliseconds. p95 is nearest-rank and reported only for n >= 20. Scales ran round-robin with a rotating start, and status / validate-project alternated first (§36.10).

### Warm process (diagnostic only)

| scale | calls | first | median | q3 | p95 | max |
|---|---|---|---|---|---|---|
| S | 30 | 372.8 | 264.0 | 265.9 | 269.9 | 372.8 |
| M | 30 | 670.8 | 564.3 | 570.4 | 576.1 | 670.8 |
| L | 30 | 6,392.8 | 6,335.9 | 6,392.5 | 6,563.7 | 6,572.8 |

### A-I stage table (component run, instrumented, exclusive time)

#### status

| stage | S median ms | M median ms | L median ms |
|---|---|---|---|
| A bootstrap/root resolution | 302.6 | 306.4 | 308.9 |
| B implementation identity verification | 18.7 | 18.8 | 18.9 |
| C registry parse/validation | 11.7 | 11.8 | 12.2 |
| D router/Skill authority inventory | 2.5 | 2.4 | 2.5 |
| E canonical Project load | 21.2 | 188.4 | 1,915.8 |
| F validate-project | 11.4 | 45.7 | 1,965.5 |
| G RB1 status derivation | 28.3 | 102.8 | 1,789.9 |
| H local Git diagnostics (all Git subprocesses) | 196.2 | 193.9 | 207.0 |
| I final JSON/render serialization and CLI output | 4.7 | 4.7 | 6.8 |
| unassigned in-process (outside every span) | 0.0 | 0.0 | 0.0 |
| harness only (runpy load of the launcher, span installation; not A-I) | 9.9 | 10.2 | 10.1 |
| in-process total | 606.2 | 882.5 | 6,260.0 |
| interpreter start/exit + pipes (wall - in-process) | 60.9 | 66.8 | 66.7 |
| instrumented wall | 674.2 | 949.5 | 6,322.0 |

Span detail at M (status): label, stage, calls, inclusive ms, exclusive ms.

| span | stage | calls | inclusive | exclusive |
|---|---|---|---|---|
| `launcher.import_workline` | A | 6 | 297.0 | 297.0 |
| `launcher._load_helper` | A | 1 | 8.7 | 8.7 |
| `status._project` | A | 1 | 0.3 | 0.3 |
| `launcher._activate` | A | 1 | 313.7 | 0.2 |
| `launcher._binds_invocation_project` | A | 1 | 0.0 | 0.0 |
| `launcher._require_supported_python` | A | 1 | 0.0 | 0.0 |
| `launcher._require_isolated_mode` | A | 1 | 0.0 | 0.0 |
| `implementation.loaded_implementation_problem` | B | 3 | 14.0 | 14.0 |
| `launcher.loaded_implementation_problem` | B | 2 | 4.7 | 4.7 |
| `implementation.running_workline_root` | B | 1 | 4.8 | 0.1 |
| `implementation.configured_implementation_problem` | B | 2 | 9.2 | 0.0 |
| `registry.validate_registry` | C | 4 | 11.8 | 11.8 |
| `registry.authority_inventory` | D | 1 | 5.3 | 2.3 |
| `status._authority` | D | 1 | 14.8 | 0.1 |
| `state.ProjectView.load` | E | 2 | 188.4 | 188.4 |
| `validate.validate_structure` | F | 2 | 26.6 | 26.6 |
| `review.validate.validate_review` | F | 1 | 44.6 | 17.9 |
| `validate.validate_project_yaml` | F | 2 | 6.6 | 0.6 |
| `validate.validate_project` | F | 1 | 156.0 | 0.3 |
| `self_hosting.self_hosting_problem` | F | 1 | 0.1 | 0.1 |
| `status._validation` | F | 1 | 160.7 | 0.0 |
| `status.read_witnesses` | G | 2 | 105.2 | 59.3 |
| `status._review` | G | 1 | 41.6 | 14.9 |
| `status._pending` | G | 1 | 54.0 | 13.9 |
| `status._lifecycle` | G | 1 | 122.2 | 13.8 |
| `mutation.inspect_records` | G | 3 | 0.9 | 0.9 |
| `status.build_status` | G | 1 | 560.0 | 0.4 |
| `gitcmd.run_git` | H | 12 | 140.3 | 140.3 |
| `gitcmd.run_git_bytes` | H | 4 | 53.1 | 53.1 |
| `status._git_section` | H | 1 | 60.5 | 0.4 |
| `cli.main` | I | 1 | 564.1 | 4.1 |
| `status._assemble` | I | 1 | 0.5 | 0.5 |
| `status.render_json` | I | 1 | 0.1 | 0.1 |
| `harness.install_spans` | harness | 1 | 2.7 | 2.7 |

#### validate

| stage | S median ms | M median ms | L median ms |
|---|---|---|---|
| A bootstrap/root resolution | 306.6 | 310.9 | 304.4 |
| B implementation identity verification | 13.9 | 14.0 | 13.7 |
| C registry parse/validation | 3.0 | 3.0 | 3.0 |
| D router/Skill authority inventory | 0.0 | 0.0 | 0.0 |
| E canonical Project load | 10.9 | 95.9 | 943.3 |
| F validate-project | 10.5 | 31.5 | 1,042.4 |
| G RB1 status derivation | 0.0 | 0.0 | 0.0 |
| H local Git diagnostics (all Git subprocesses) | 27.5 | 31.3 | 31.9 |
| I final JSON/render serialization and CLI output | 4.2 | 4.4 | 4.1 |
| unassigned in-process (outside every span) | 0.0 | 0.0 | 0.0 |
| harness only (runpy load of the launcher, span installation; not A-I) | 10.0 | 10.3 | 10.2 |
| in-process total | 383.8 | 498.9 | 2,366.1 |
| interpreter start/exit + pipes (wall - in-process) | 57.4 | 62.7 | 61.0 |
| instrumented wall | 441.2 | 563.4 | 2,427.1 |

Span detail at M (validate): label, stage, calls, inclusive ms, exclusive ms.

| span | stage | calls | inclusive | exclusive |
|---|---|---|---|---|
| `launcher.import_workline` | A | 6 | 301.5 | 301.5 |
| `launcher._load_helper` | A | 1 | 8.7 | 8.7 |
| `launcher._activate` | A | 1 | 323.1 | 0.3 |
| `launcher._require_project_configured_for_this_root` | A | 1 | 7.8 | 0.2 |
| `context.resolve_invocation_context` | A | 1 | 0.2 | 0.2 |
| `launcher._binds_invocation_project` | A | 1 | 0.0 | 0.0 |
| `launcher._require_supported_python` | A | 1 | 0.0 | 0.0 |
| `launcher._require_isolated_mode` | A | 1 | 0.0 | 0.0 |
| `implementation.loaded_implementation_problem` | B | 2 | 9.3 | 9.3 |
| `launcher.loaded_implementation_problem` | B | 2 | 4.8 | 4.8 |
| `implementation.configured_implementation_problem` | B | 2 | 9.3 | 0.0 |
| `implementation.require_configured_implementation` | B | 2 | 9.3 | 0.0 |
| `registry.validate_registry` | C | 1 | 3.0 | 3.0 |
| `state.ProjectView.load` | E | 1 | 95.9 | 95.9 |
| `review.validate.validate_review` | F | 1 | 48.6 | 17.7 |
| `validate.validate_structure` | F | 1 | 13.3 | 13.3 |
| `validate.validate_project` | F | 1 | 162.5 | 0.3 |
| `validate.validate_project_yaml` | F | 1 | 3.3 | 0.2 |
| `self_hosting.self_hosting_problem` | F | 1 | 0.1 | 0.1 |
| `gitcmd.run_git_bytes` | H | 2 | 31.3 | 31.3 |
| `cli.main` | I | 1 | 170.9 | 4.4 |
| `harness.install_spans` | harness | 2 | 2.8 | 2.8 |

Spans wrap the landed boundaries at runtime in a separate child running the launcher's own `main`; the instrumented status JSON was byte-identical to the uninstrumented one for every sample. Stage H is every Git subprocess wherever it was called from (its time is not also counted in the calling stage). Stage F includes `validate_structure` wherever it runs (also inside status lifecycle). Unassigned time is reported, not forced into a stage.

### Mechanical recovery end-to-end (§36.12)

Fresh-session recovery as the supported procedure runs it, one fresh process per step: `validate-registry <workline-root>` (bootstrap: configured root, registry read + validation), the router step (`activate()`, `registry.resolve_skill(skills/project-router)`, the router's call-time `router_candidates`, SKILL.md bytes read - never interpreted), `status --json` (A-I in one process), `validate-project`. A-D also run inside status itself; the status A-I table above is that process's split.

| scale | n | validate-registry | router | status | validate-project | total median | total max |
|---|---|---|---|---|---|---|---|
| S | 5 | 375.0 | 117.2 | 663.1 | 427.3 | **1,586.5** | 1,607.5 |
| M | 5 | 371.2 | 113.3 | 924.9 | 532.4 | **1,940.4** | 1,955.9 |
| L | 5 | 372.6 | 118.1 | 6,328.4 | 2,373.6 | **9,178.5** | 9,241.3 |

Router step in-process (median, first scale): activation 48.3 ms, router resolution 9.0 ms, inventory of 5 routable Skills 4.6 ms.

### Git command counts (per invocation)

| scale | operation | total | rev-parse | symbolic-ref | status | diff | ls-files | ls-tree | remote/config | other | hermetic (env-stripped) | Trace2 visible |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S | status | 16 | 7 | 3 | 1 | 0 | 1 | 2 | 2 | 0 | 4 | 12 |
| S | validate | 2 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 2 | 0 |
| M | status | 16 | 7 | 3 | 1 | 0 | 1 | 2 | 2 | 0 | 4 | 12 |
| M | validate | 2 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 2 | 0 |
| L | status | 16 | 7 | 3 | 1 | 0 | 1 | 2 | 2 | 0 | 4 | 12 |
| L | validate | 2 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 2 | 0 |

- M status: families {'ls-files': 1, 'ls-tree': 2, 'remote': 2, 'rev-parse': 7, 'status': 1, 'symbolic-ref': 3}; Git ms by calling span `review.validate.validate_review` 26.7, `status._git_section` 60.1, `status._pending` 33.2, `status._review` 26.4, `status.read_witnesses` 45.0
- M validate: families {'ls-tree': 1, 'rev-parse': 1}; Git ms by calling span `review.validate.validate_review` 31.3

Counted by a benchmark-only wrapper of `gitcmd.run_git` / `run_git_bytes` in the component run (all Git goes through them), cross-checked with Git Trace2 `start` events of an uninstrumented run. Trace2 cannot see the Review hermetic (class A/B) commands: they run with every inherited `GIT_*` variable stripped by design, so the Trace2 total is lower by exactly those. No network family was observed; no socket was opened.

### Trigger A (§36.17)

#### status - denominator: uninstrumented cold M median 987.6 ms

| candidate | numerator ms | fraction | > 50% | removable without semantic change | support |
|---|---|---|---|---|---|
| repeated canonical Project load (ProjectView.load) within one command | 94.2 | 9.5% | no | the second load reads the same files between the same B0/B1 witnesses; one immutable snapshot can be reused (§36.22 step 2) | component span state.ProjectView.load: 2 call(s), 188.4 ms exclusive |
| repeated structure validation (validate_structure) within one command | 13.3 | 1.3% | no | the same validation over the same snapshot; its result can be reused (§36.22 step 1) | component span validate.validate_structure: 2 call(s), 26.6 ms exclusive |
| repeated registry validation (validate_registry) within one command | 8.8 | 0.9% | no | the same registry bytes validated again within one command (§36.22 step 1) | component span registry.validate_registry: 4 call(s), 11.8 ms exclusive |
| repeated configured-implementation identity check within one command | 4.6 | 0.5% | no | the same question of the same loaded modules (§36.22 step 1) | component span implementation.configured_implementation_problem: 2 call(s), 9.2 ms inclusive |
| identical Git commands repeated within one command (B0/B1 witness re-reads excluded) | 22.8 | 2.3% | no | the same local question asked again; batching equivalent reads keeps the questions (§36.22 step 3) | component Git wrapper: 2 repeated identical command(s) |
| per-entity full Event-log scans (ProjectView.events_for) behind state derivation | 3.5 | 0.4% | no | each call rescans a whole immutable list of the one snapshot; one grouping pass per command replaces the repeats (an in-memory index: §36.22 step 4, after steps 1-3) | derivation-span variant (3 sample(s), median): 12212 calls, 3.5 ms exclusive (per-call wrapper overhead included: an over-estimate) |
| per-entity full roadmap-relation scans (ProjectView.relations_to) | 15.9 | 1.6% | no | each call rescans a whole immutable list of the one snapshot; one grouping pass per command replaces the repeats (an in-memory index: §36.22 step 4, after steps 1-3) | derivation-span variant (3 sample(s), median): 1884 calls, 16.0 ms exclusive (per-call wrapper overhead included: an over-estimate) |
| per-Phase full Work scans (ProjectView.phase_works) | 10.5 | 1.1% | no | each call rescans a whole immutable list of the one snapshot; one grouping pass per command replaces the repeats (an in-memory index: §36.22 step 4, after steps 1-3) | derivation-span variant (3 sample(s), median): 693 calls, 10.6 ms exclusive (per-call wrapper overhead included: an over-estimate) |
| BOUND: every local Git subprocess of the command (stage H) | 193.9 | 19.6% | no | n/a (upper bound, not one derivation) | component stage H median; not one derivation - the B0/B1 witnesses and each distinct question are semantic |
| BOUND: all canonical load + validation + status derivation (stages E+F+G) | 336.8 | 34.1% | no | n/a (upper bound, not one derivation) | component stage medians E+F+G; not one derivation |
| per-entity full Event-log scans (ProjectView.events_for) behind state derivation | 7.2 | 0.7% | no | one grouping of the immutable Event list per command replaces each O(E) rescan (an in-memory index: §36.22 step 4, after steps 1-3) | cProfile (supporting): 12212 calls, 0.8% of profiled time; estimate = share x component in-process median (profiler overhead inflates call-heavy code) |

Trigger A (status): **false**

#### validate - denominator: uninstrumented cold M median 565.5 ms

| candidate | numerator ms | fraction | > 50% | removable without semantic change | support |
|---|---|---|---|---|---|
| repeated canonical Project load (ProjectView.load) within one command | 0.0 | 0.0% | no | n/a (no repeat) | component span state.ProjectView.load: 1 call(s), 95.9 ms exclusive |
| repeated structure validation (validate_structure) within one command | 0.0 | 0.0% | no | n/a (no repeat) | component span validate.validate_structure: 1 call(s), 13.3 ms exclusive |
| repeated registry validation (validate_registry) within one command | 0.0 | 0.0% | no | n/a (no repeat) | component span registry.validate_registry: 1 call(s), 3.0 ms exclusive |
| repeated configured-implementation identity check within one command | 4.6 | 0.8% | no | the same question of the same loaded modules (§36.22 step 1) | component span implementation.configured_implementation_problem: 2 call(s), 9.3 ms inclusive |
| identical Git commands repeated within one command (B0/B1 witness re-reads excluded) | 0.0 | 0.0% | no | n/a (no repeat) | component Git wrapper: 0 repeated identical command(s) |
| per-entity full Event-log scans (ProjectView.events_for) behind state derivation | 1.2 | 0.2% | no | each call rescans a whole immutable list of the one snapshot; one grouping pass per command replaces the repeats (an in-memory index: §36.22 step 4, after steps 1-3) | derivation-span variant (3 sample(s), median): 3934 calls, 1.2 ms exclusive (per-call wrapper overhead included: an over-estimate) |
| per-entity full roadmap-relation scans (ProjectView.relations_to) | 4.9 | 0.9% | no | each call rescans a whole immutable list of the one snapshot; one grouping pass per command replaces the repeats (an in-memory index: §36.22 step 4, after steps 1-3) | derivation-span variant (3 sample(s), median): 560 calls, 4.9 ms exclusive (per-call wrapper overhead included: an over-estimate) |
| per-Phase full Work scans (ProjectView.phase_works) | 3.1 | 0.6% | no | each call rescans a whole immutable list of the one snapshot; one grouping pass per command replaces the repeats (an in-memory index: §36.22 step 4, after steps 1-3) | derivation-span variant (3 sample(s), median): 215 calls, 3.1 ms exclusive (per-call wrapper overhead included: an over-estimate) |
| BOUND: every local Git subprocess of the command (stage H) | 31.3 | 5.5% | no | n/a (upper bound, not one derivation) | component stage H median; not one derivation - the B0/B1 witnesses and each distinct question are semantic |
| BOUND: all canonical load + validation + status derivation (stages E+F+G) | 127.4 | 22.5% | no | n/a (upper bound, not one derivation) | component stage medians E+F+G; not one derivation |
| per-entity full Event-log scans (ProjectView.events_for) behind state derivation | 2.8 | 0.5% | no | one grouping of the immutable Event list per command replaces each O(E) rescan (an in-memory index: §36.22 step 4, after steps 1-3) | cProfile (supporting): 3934 calls, 0.6% of profiled time; estimate = share x component in-process median (profiler overhead inflates call-heavy code) |

Trigger A (validate): **false**

**Trigger A: false**

Rule: one concrete removable derivation, deduplicated for nesting, strictly above 50% of the uninstrumented cold M median; candidates are never added together; BOUND rows only show how far a whole family could reach; profiler rows are supporting estimates (cProfile inflates call-heavy code), never the proof.

### Trigger B (§36.18)

| pair | subject | Works x | Events x | median small | median large | median ratio | conservative Q1(L)/Q3(S) | verdict |
|---|---|---|---|---|---|---|---|---|
| S->M | cold status (wall) | 10.0 | 10.03 | 701.9 | 987.6 | 1.41x | 1.37x | false |
| S->M | status stage A | 10.0 | 10.03 | 302.6 | 306.4 | 1.01x | 0.95x | false |
| S->M | status stage B | 10.0 | 10.03 | 18.7 | 18.8 | 1.01x | 0.99x | false |
| S->M | status stage C | 10.0 | 10.03 | 11.7 | 11.8 | 1.00x | 0.98x | false |
| S->M | status stage D | 10.0 | 10.03 | 2.5 | 2.4 | 0.98x | 0.96x | false |
| S->M | status stage E | 10.0 | 10.03 | 21.2 | 188.4 | 8.90x | 8.69x | false |
| S->M | status stage F | 10.0 | 10.03 | 11.4 | 45.7 | 4.01x | 3.76x | false |
| S->M | status stage G | 10.0 | 10.03 | 28.3 | 102.8 | 3.63x | 3.60x | false |
| S->M | status stage H | 10.0 | 10.03 | 196.2 | 193.9 | 0.99x | 0.94x | false |
| S->M | status stage I | 10.0 | 10.03 | 4.7 | 4.7 | 0.98x | 0.96x | false |
| S->M | cold validate (wall) | 10.0 | 10.03 | 454.1 | 565.5 | 1.25x | 1.21x | false |
| S->M | validate stage A | 10.0 | 10.03 | 306.6 | 310.9 | 1.01x | 0.99x | false |
| S->M | validate stage B | 10.0 | 10.03 | 13.9 | 14.0 | 1.01x | 0.96x | false |
| S->M | validate stage C | 10.0 | 10.03 | 3.0 | 3.0 | 1.03x | 0.98x | false |
| S->M | validate stage D | 10.0 | 10.03 | n/a | n/a | n/a | n/a | unmeasurable |
| S->M | validate stage E | 10.0 | 10.03 | 10.9 | 95.9 | 8.83x | 8.43x | false |
| S->M | validate stage F | 10.0 | 10.03 | 10.5 | 31.5 | 2.99x | 2.81x | false |
| S->M | validate stage G | 10.0 | 10.03 | n/a | n/a | n/a | n/a | unmeasurable |
| S->M | validate stage H | 10.0 | 10.03 | 27.5 | 31.3 | 1.14x | 1.02x | false |
| S->M | validate stage I | 10.0 | 10.03 | 4.2 | 4.4 | 1.07x | 0.99x | false |
| S->M | warm status (diagnostic only) | 10.0 | 10.03 | 264.0 | 564.3 | 2.14x | 2.10x | false |
| M->L | cold status (wall) | 10.0 | 10.00 | 987.6 | 6,828.5 | 6.91x | 6.77x | false |
| M->L | status stage A | 10.0 | 10.00 | 306.4 | 308.9 | 1.01x | 0.98x | false |
| M->L | status stage B | 10.0 | 10.00 | 18.8 | 18.9 | 1.01x | 0.97x | false |
| M->L | status stage C | 10.0 | 10.00 | 11.8 | 12.2 | 1.04x | 1.02x | false |
| M->L | status stage D | 10.0 | 10.00 | 2.4 | 2.5 | 1.01x | 0.96x | false |
| M->L | status stage E | 10.0 | 10.00 | 188.4 | 1,915.8 | 10.17x | 9.82x | false |
| M->L | status stage F | 10.0 | 10.00 | 45.7 | 1,965.5 | 43.00x | 42.76x | true |
| M->L | status stage G | 10.0 | 10.00 | 102.8 | 1,789.9 | 17.42x | 17.37x | true |
| M->L | status stage H | 10.0 | 10.00 | 193.9 | 207.0 | 1.07x | 1.01x | false |
| M->L | status stage I | 10.0 | 10.00 | 4.7 | 6.8 | 1.46x | 1.37x | false |
| M->L | cold validate (wall) | 10.0 | 10.00 | 565.5 | 2,629.7 | 4.65x | 4.49x | false |
| M->L | validate stage A | 10.0 | 10.00 | 310.9 | 304.4 | 0.98x | 0.97x | false |
| M->L | validate stage B | 10.0 | 10.00 | 14.0 | 13.7 | 0.97x | 0.92x | false |
| M->L | validate stage C | 10.0 | 10.00 | 3.0 | 3.0 | 0.99x | 0.96x | false |
| M->L | validate stage D | 10.0 | 10.00 | n/a | n/a | n/a | n/a | unmeasurable |
| M->L | validate stage E | 10.0 | 10.00 | 95.9 | 943.3 | 9.83x | 9.79x | false |
| M->L | validate stage F | 10.0 | 10.00 | 31.5 | 1,042.4 | 33.11x | 32.22x | true |
| M->L | validate stage G | 10.0 | 10.00 | n/a | n/a | n/a | n/a | unmeasurable |
| M->L | validate stage H | 10.0 | 10.00 | 31.3 | 31.9 | 1.02x | 0.76x | false |
| M->L | validate stage I | 10.0 | 10.00 | 4.4 | 4.1 | 0.93x | 0.92x | false |
| M->L | warm status (diagnostic only) | 10.0 | 10.00 | 564.3 | 6,335.9 | 11.23x | 11.02x | false |

Frozen condition: median ratio > 12x AND the excess outside observed run-to-run noise; the noise bound is the interquartile spread (conservative ratio Q1 of the larger scale over Q3 of the smaller must also exceed 12x). `non_robust` = median above 12x but inside noise (STOP, §36.32). Warm rows are diagnostic and never decide.

**Trigger B: true**

### Decision

**MEASURED_TRIGGER_B**

### Canonical Project mutation during measurement

none - 18 before/after identity check(s) of every fixture (worktree bytes incl. the runtime record, the whole `.git`, HEAD, tree, porcelain status) were unchanged.

### Limitations

- Cold-process, not cold-disk: the OS file cache is not purged, so repeated samples read warm file data.
- One machine, one OS: absolute times (especially Windows process creation, which every Git subprocess and the py launcher pay) are specific to it; the trigger decisions rest on ratios and shares measured on it.
- The quiet window pauses test processes; other non-test processes of the machine still run and are not controlled beyond the recorded CPU / disk samples.
- The canonical invocation writes no bytecode (-B) and none is present, so every cold sample compiles the imported Workline modules from source; that is the supported path, and it is measured as such (stage A).
- Component spans are instrumented: wrapper overhead is included, and the child preloads `runpy` (with `importlib.util`), so stage A import time is slightly under-stated there; headline numbers are uninstrumented.
- Derivation-span samples wrap very frequently called scans: their numerators over-state the scan cost a little.
- The profiler run is supporting evidence only; cProfile inflates call-heavy code.
- Git Trace2 cannot see the Review hermetic (class A/B) commands, which strip every inherited GIT_* variable by design; the complete count is the component wrapper's.
- Byte and count observations come from the generated fixture files, not from read counters in production readers.
- The pending fixture is a real owner's structurally valid record classified `unknown_or_invalid`: a positively resumable record would need a remote, which the benchmark Project must not have (§36.8-§36.9).
- The Review fixture is one P1-shape Run (no P4 Run, no Work-terminal activation): Review status cost is covered at O(1), not every Review contract path.
- Warm results are diagnostic only and never decide BL-007.

### Commands (portable form)

- cold status: `py -3 -I -B <workline-root>/run-workline.py status <project-root> --json`
- cold validate-project: `py -3 -I -B <workline-root>/run-workline.py validate-project <project-root>`
- working directory: `<project-root>`
- component child: `py -3 -I -B <workline-root>/benchmarks/rb2/run.py _child component <launcher> <out> plain -- status <project-root> --json`
- warm child: `py -3 -I -B <workline-root>/benchmarks/rb2/run.py _child warm <launcher> <out> <project-root> <calls>`
- Git Trace2: `cold command with GIT_TRACE2_EVENT=<temporary directory outside the Project>`

### Raw cold samples (ms)

- S status: 713.5, 677.2, 681.2, 716.1, 726.3, 680.6, 720.3, 709.0, 703.3, 703.1, 696.6, 698.0, 701.9, 682.3, 692.6
- S validate: 463.3, 452.4, 446.3, 453.1, 464.6, 479.1, 447.7, 476.7, 453.5, 458.0, 453.2, 460.2, 454.1, 450.2, 462.4
- M status: 987.6, 989.9, 954.5, 973.7, 1029.8, 990.2, 1015.9, 1008.2, 998.6, 966.3, 1000.0, 981.6, 980.3, 965.8, 976.2
- M validate: 562.6, 574.8, 557.2, 573.9, 579.1, 585.6, 582.2, 579.7, 562.6, 555.9, 558.2, 564.6, 553.5, 571.8, 565.5
- L status: 6901.6, 6828.5, 6595.7, 6838.7, 6995.5, 7164.0, 6946.7, 6978.5, 7189.8, 6766.2, 6810.8, 6735.6, 6711.4, 6761.4, 6770.9
- L validate: 2669.9, 2651.1, 2556.1, 2581.2, 2629.7, 2625.6, 2679.1, 2668.7, 2694.7, 2632.3, 2688.3, 2604.7, 2607.4, 2542.4, 2566.2

