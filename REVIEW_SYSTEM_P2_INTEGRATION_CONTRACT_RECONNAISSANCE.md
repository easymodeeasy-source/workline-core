# Review System P2 — Planning Review Gates: Integration Contract Reconnaissance

Status: `RECONNAISSANCE COMPLETE / NON-NORMATIVE / P2 IMPLEMENTATION NOT STARTED / READY_FOR_P2_RECONNAISSANCE_REVIEW`

Runtime authority is unchanged: `registry.md`, the registry-routed canonical Skills, and the live implementation and tests. This document is not authority. It records what the live repository at the baseline says about connecting the landed P1 Review Core to Roadmap creation and Phase entry, keeps live facts apart from contract choices that are still open, and names the one decision that needs a human.

```text
Candidate 7:           RETAIN
Architecture reopen:   No
P2 scope:              Planning Review Gates
                       1. RoadmapPlan Review
                       2. PhaseEntryDesign Review
                       3. semantic round-trip integration
Not touched:           START Review Gate, Work completion Review, review-v1 work_completed,
                       Work-terminal activation and Consumption totality, commit/proof/push split,
                       P3 Review-validity closure runtime, P3 stale-generation blocking runtime,
                       Class A, Work terminal event metadata, P3 publication_contract
```

How to read it: statements are marked **Live** (what the baseline code or authority does, with `file:line`), **Measured** (what a throw-away probe observed on real Projects, §18), or **Open** (what the P2 contract still has to decide). Nothing marked Open is frozen here.

## 1. Exact baseline

| item | value |
| --- | --- |
| repository | `easymodeeasy-source/workline-core` |
| branch | `main` |
| baseline = P1 accepted checkpoint | `b78be1ccd778ceb2ecd97b90e2f71744bd1b3bc5` |
| verified before any reading | local `main`, local `origin/main` and GitHub `ls-remote refs/heads/main` all `b78be1c`; HEAD on `main`; canonical worktree clean (`status --porcelain --untracked-files=all` empty) |
| investigation tree | fresh `git clone --no-local` from GitHub at `b78be1c`; the canonical worktree was only read |
| probe environment | Windows 11, Python 3.14.4, Git 2.54.0.windows.1; every probe asserted that `workline` was imported from the investigation tree's own `src` |
| repository changes | this file only; no code, test, Skill, registry or BACKLOG change |

P1 as it stands at the baseline: Review Core implemented (`ef77aa3`), repaired (`d6723b6`), finally repaired (`fedd0f3`, `b78be1c`). Work-terminal gating is not activated and no activation record exists. `state.py`, `roadmap.py`, `start.py`, `create.py`, `phase_create.py`, `ops.py` do not import `workline.review`.

## 2. Live authority consulted

Authority, read in full:

- `registry.md`: `rules/git` (Operation Owner, Project context, Unsupported self-hosting, Workline implementation, Project execution lock, Mutation Controller, Multi-write mutation, Cleanup, Commit / push, Push destination), `rules/ai-decision`, `rules/human-confirmation`, `rules/information-tracing`, and the seven routed Skills including `skills/review`.
- `.claude/skills/roadmap/SKILL.md`, `phase-create/SKILL.md`, `create/SKILL.md`, `review/SKILL.md`, `project-router/SKILL.md`; `start/SKILL.md` for the handoff, outer continuation and terminal sections.

Implementation: `roadmap.py`, `phase_create.py`, `create.py`, `mutation.py`, `state.py`, `store.py`, `validate.py`, `gitops.py`, `oplock.py`, `yamlish.py`, `errors.py`, and `review/{__init__,paths,serialize,records,store,gate,projections,adapter,closure,validate}.py` in full; `ops.py` (shared helpers; the plan-exclusion resume skimmed), `start.py` (outcomes, `start`, `_start_locked`, plan exclusion), `gitcmd.py` (the primitives the Git stage uses), `cli.py` (subcommands), `implementation.py` (what implementation identity covers), `review/fsafe.py` (platform support).

Tests, for behaviour and for pins a P2 change must keep: `helpers.py`, `test_phase_entry_contract.py`, `test_phase_expansion_resume.py`, `test_declared_write_scope.py`, `test_project_start_recovery.py`, `test_decision_branch_binding.py`, `test_cancel_decision_resume.py`, `test_decided_content_binding.py`, `test_review_gate_generation.py`.

Non-authority documents, read and checked against the above, never used as the source of a live fact: Candidate 7 checkpoint (§2, §4, §8, §11, §15) and readiness note; P1 R1, R2, R3, R4, R5 §12, R8, R9, R10, R11, R12 §11-§14; the P1 contract repair after external review §6; the Learning and Phase Design notes §17-§25; BACKLOG (search only, BL-041 read for its residuals). Where they disagree with the live code or with each other, §14 names the seam.

## 3. Current Roadmap planning flow — `RoadmapPlan`

### 3.1 Live names

**Live.** The design name is the live name. `RoadmapPlan` (`roadmap.py:155-163`: `name`, `background`, `desired_state`, `phases: dict[str, PhaseSpec]`, `relations: tuple[PhaseRelationSpec, ...]`, `scope`, `out_of_scope`) with `PhaseSpec` / `PhaseRelationSpec` from `phase_create.py:26-38`. No production code constructs one (`src/` holds no `RoadmapPlan(` call): the caller is the AI running `skills/roadmap`, through the Python API after `activate()` — Roadmap has no CLI (`cli.py` offers validate-registry, project-start, push destination pin, validate-project, backfill and create-work only).

### 3.2 Meaning versus mutation

| role | live owner |
| --- | --- |
| semantic owner (what the plan means) | `skills/roadmap`: Roadmap意味決定 → 全Phase意味決定 → Phase間relation意味決定 |
| top-level operation and mutation owner | `roadmap.create_roadmap`; lock operation `roadmap-create`; mutation owner `"roadmap"` (`roadmap.py:94`) |
| registration core (no lock, no Git) | Phase CREATE: `phase_create.decide_phases` / `register_phases` |
| physical writer | Mutation Controller |
| Git finalizer | `roadmap._finalize` → `gitops.finalize` |

### 3.3 Exact current order

```text
L0  the caller decides a RoadmapPlan                          nothing persisted
L1  non-blank name / background / desired state, >= 1 Phase   roadmap.py:452-456
L2  project_operation: Project context -> self-hosting ->
    implementation -> execution lock                          :457, oplock.py:211-295
L3  _stop_on_structure("precheck") (validate_structure)       :458
L4  request = roadmap_request_identity(plan);
    require_same_request(pending_for_slot(roadmap, {operation, name}))   :459-464
L5  _open: ensure_push_destination -> MutationController.open
    (invocation {operation, name, request}; scope roadmap.yaml)
    -> ensure_git_ready -> record_preexisting_dirty
    -> [resumed] refuse_invalid_phase_writes -> apply()       :233-264
L6  _create_roadmap: reserve "roadmap"; extend scope           :475-476
    stage "roadmap" not recorded yet:
      render the Roadmap file (display R-<count+1>)            :479-486
      projected = ProjectView.load().with_effects([file])      :494
      decide_phases: reserves phases:phase:<key> and
        phases:rel:<i>; Phase CREATE precheck and payload rules  :495, phase_create.py:88-157
      refuse_invalid_phase_writes(projected)                   :496
      add_effects("roadmap", [write Roadmap file])  <- first domain effect  :497
    apply()                                                    :498
L7  register_phases: same IDs; refuse; add_effects("phases",
    Phase files + Roadmap relations); apply; postcheck         :500, phase_create.py:160-204
L8  _finalize: Git stage "finalize" = git_commit + git_push;
    _stop_on_structure("postcheck"); complete()                :501-503, :267-274
L9  RoadmapResult
```

Validation today: Phase CREATE precheck and payload rules, the projected structure check before each registration stage is recorded, the registration postcheck after apply (which does compare each Phase relation with its decided record, `phase_create.py:196-199`), and the structure postcheck after the commit. **No step compares the persisted Roadmap or Phase text with the request** — the Roadmap Skill says so itself (postcheck "今回のrequestが決めた本文内容と正本を突き合わせない").

### 3.4 Durable and commit boundaries

| boundary | where | clone-safe |
| --- | --- | --- |
| request durable | `MutationController.begin` writes the runtime record (`mutation.py:1693-1711`) | no — `.workline/runtime/`, never committed |
| first canonical write | `apply()` of stage `roadmap` | no — working tree |
| commit and push | Git stage `finalize` | yes |
| record removed | `complete()` → `_drop_own_record`, only when the run was not a resume (`mutation.py:563-618`) | — |

### 3.5 Source of truth after a crash; replay; idempotency

**Live.**

- An interrupted creation is continued only through its pending runtime record — `request`, `reserved_ids`, the recorded effects with `held_before` / `wrote` / `decided_on`, the `preexisting_dirty` note — read together with the canonical files and Git. The record is found only by `MutationController.open` on an identical owner and invocation (`mutation.py:1655-1691`).
- Replay: every recorded effect is classified unapplied / applied_matching / applied_mismatch before anything else happens (`Mutation.apply`, `mutation.py:500-554`); a different request for the same slot is refused before the mutation opens, with the record untouched (`require_same_request`, `:723-756`); the branch rules (`_require_decided_branch`, `_require_finalized_branch`), the own-bytes rules, commit-ID identity and exact-commit publication apply unchanged.
- Idempotency covers interruption only. **Measured (probe 6):** after `complete()` no record is left, and the same `RoadmapPlan` again creates a second Roadmap.

### 3.6 Lifecycle and progression

**Live.** Roadmap creation records no event (`OPERATION_LEDGERS["roadmap-create"]`, `roadmap.py:121`). A Roadmap is `active` because no event says otherwise (`state.derive_roadmap_lifecycle`, `state.py:106-117`); a Phase likewise. Startable Phases, selection and achievement are computed by `ProjectView`, `select_phase` and `evaluate_achievement` from entities, relations and events only.

### 3.7 Other live planning writers — the P2 scope edge

**Live.** By its live name, `RoadmapPlan` is the input of `create_roadmap` alone. These also change planning content but take other inputs: `add_phases` (a `PhaseSpec` dict with its own request identity), `maintain_work_related`, plan exclusion with `Replan` (new Works and relations), START's `Derive` / `HumanNG` registrations, and direct CREATE. P2 as scoped leaves them ungated, so a reviewed plan can later be changed through them. Recorded as a scope fact (§14 Q18), not a blocker.

## 4. Current Phase-entry planning flow — `PhaseEntryDesign`

### 4.1 Live names, and one naming correction

**Live.** `PhaseEntryDesign` (`roadmap.py:192-199`: `works: dict[str, WorkDesign]`, `integration`, `human_confirmation`, `planned_next`, `requires_completion`, `entry`) and `WorkDesign` (`:185-189`: `name`, `desired_state`, `related`). Entry point `enter_phase` (`:757`) → `_enter_phase_locked` (`:762`) → `_expand_phase` (`:949`).

The Phase Design notes place "Phase Design Review ... before Phase CREATE/registration". In live code Phase CREATE registers *Phases* (Roadmap creation and `add_phases`), while a `PhaseEntryDesign` is registered as *Works* by the CREATE registration core when the Phase is entered. The P2 object is `enter_phase`'s design; Phase CREATE belongs to the RoadmapPlan registration.

### 4.2 Owners

As in 3.2, except: operation `enter_phase`, lock operation `phase-entry`, owner `"roadmap"`, declared ledgers `roadmap.yaml` and `related.yaml` with entity `phase_id` (`roadmap.py:125`, `:819-822`), registration core CREATE `register_works` in up to three stages.

### 4.3 Exact current order

```text
E0  the caller designs the Works (skills/roadmap, Phase entry)
E1  project_operation(..., "phase-entry")                           roadmap.py:758
E2  precheck structure; Phase resolvable; Roadmap active;
    Phase not complete / held / cancelled / plan_excluded;
    _require_settled_lifecycle(roadmap, phase);
    dependencies satisfied (phase_blocked)                        :763-784
E3  identity = design_identity(design); unfinished expansions of
    this Phase -> _require_resumable (legacy, several, other design
    -> reconcile_required, record untouched)                      :786-792
E4  Works exist and nothing unfinished -> phase_already_expanded   :793-805
E5  design shape; _require_startable_entry;
    _require_unique_entry (new expansions only)                   :806-817
E6  _open(invocation {operation, phase_id, design}; scope
    roadmap.yaml + related.yaml; entity phase_id;
    refuse_recorded=refuse_invalid_work_writes)                   :819-822
E7  _expand_phase: WorkSpecs; validate_work_specs for every stage
    not recorded yet                                              :950-990
      stage "works"        register_works -> add_effects -> apply   :997, create.py:212-303
      stage "integration"  normal Works -> integration              :999-1004
      stage "confirmation" optional; integration -> confirmation    :1006-1015
E8  _stop_on_structure("phase structure check"); _finalize        :1020-1021
E9  entry: an explicit entry must be startable; otherwise the Work
    the plan points to, or None                                   :1023-1037
```

### 4.4 `entry` is not persisted

**Live.** `entry` is recorded only in the runtime invocation (`design_identity`, `:641-681`) and returned as `PhaseEntryResult.entry_work_id`; no canonical file holds it. The handoff recomputes the Work through `ProjectView.choose_startable` unless the caller passes one (`:1632-1643`). An explicit entry skips `_require_unique_entry` (`:897-908`) and is checked only for startability (`:833-866`).

**Measured (probes 1, 1b):**

| design | live outcome | the canonical reread selects |
| --- | --- | --- |
| two Works, no `planned_next`, `entry = w1` | accepted, returns w1 | nothing (both equally planned) |
| `planned_next w1 -> w2`, `entry = w2` | accepted, returns w2 | w1 |
| `planned_next w1 -> w2`, `entry = w1` | accepted, returns w1 | w1 |
| `planned_next w1 -> w2`, no entry | accepted, returns w1 | w1 |

`tests/helpers.simple_entry` relies on the first row: it sets `entry` for multi-Work designs without `planned_next`.

### 4.5 Where lifecycle stops and planning begins

**Live.** Phase entry writes no event (`OPERATION_LEDGERS["phase-entry"]`). Phase lifecycle (`active` / `held` / `cancelled` / `plan_excluded`) comes only from Phase events, which Roadmap lifecycle operations write. Phase *state* (`unstarted` / `in_progress` / `complete`) is derived from the Works' events, which START writes; right after an expansion the Phase is still `unstarted` (**Measured**, probe 5). The START handoff is a separate top-level operation that runs after the Roadmap operation returned and released the lock. Phase entry is therefore a structural registration and not a lifecycle transition, and its authorization cannot be an authorization of anything START does.

### 4.6 Durable boundaries and recovery

**Live.** The boundaries of 3.4 apply unchanged. Only the identical design resumes an unfinished expansion (BL-023); a recorded stage is read back from its record (`_recorded_registration`, `:728-754`) rather than decided again; an expansion with an effect is never abandoned (`:823-828`). **Measured (probe 6):** an expansion that finished is refused on retry as `phase_already_expanded`.

## 5. Current mutation owners

| operation | function | lock operation | owner | resume key (invocation) | declared ledgers | registration core |
| --- | --- | --- | --- | --- | --- | --- |
| Roadmap creation | `create_roadmap` | `roadmap-create` | `roadmap` | `{operation, name, request}` | `roadmap.yaml` | Phase CREATE |
| Phase entry | `enter_phase` | `phase-entry` | `roadmap` | `{operation, phase_id, design}` | `roadmap.yaml`, `related.yaml` | CREATE |

**Live.** `skills/review`: "Roadmap planning Review -> Roadmap mutation owner / Phase entry Review -> Roadmap mutation owner"; Review takes no lock, opens no mutation and commits nothing, and the canonical Review records are written by the mutation of the operation that uses the gate. The code agrees: nothing in `workline.review` writes (`review/__init__.py:8-12`), `ReviewStore` only reads, and records reach disk only as the Mutation Controller's `create_file` effect.

**Measured (probes 2, 5).** One `roadmap`-owned mutation carried every Review record — Candidate snapshot, task input, three gate generations, Receipt, Consumption — as `create_file` effects, and then the unchanged live registration (`_create_roadmap` / `_expand_phase`) and Git finalization, under one mutation ID from the first reservation to `complete()`. No Review-owned mutation, no second lock and no new effect kind were needed.

How the one owner holds each item as a subordinate effect of its own mutation, inside its own lock:

| item | held as | identity |
| --- | --- | --- |
| gate generation | `create_file` in its own stage; the path and the Run's serialization token added to the scope | Run ID reserved under `review-run:<kind>:<target>` |
| CandidateSnapshot | `create_file` in the acceptance stage | content address (`candidate_hash`) |
| TaskInput | `create_file` in the acceptance stage | `review-task:<run>:<slot>` |
| Receipt | `create_file` in the seal stage, beside the sealed generation | `review-receipt:<run>:<generation>` |
| Consumption | `create_file` in the consumption stage | `review-consumption:<receipt_id>` |
| planning mutation | the live `write_file` / `add_relation` stages | the live reservation keys |
| Git | a commit-only stage at the launch boundary, then the live `finalize` | recorded commit IDs |

The Review package contributes record shapes, validation and read-back; it takes no lock, opens no mutation, writes no lifecycle event and decides no progression.

## 6. P1 primitives available to P2

`as-is`: usable unchanged. `planning binding`: the mechanism is usable, P2 must define planning-specific content or values. `not in P2`: not needed by P2.

| primitive | live location | P2 | constraint or evidence |
| --- | --- | --- | --- |
| `ReviewStore` (canonical read, chain validation, lookups, uniqueness indexes) | `review/store.py` | as-is | Measured: chain and Receipt read back after the seal; the Receipt index holds planning Consumptions |
| Gate generation and chain invariants | `records.py:226-416`, `review/store.py:136-209` | as-is schema, planning binding | `review_kind`, `target_identity`, `operation_identity`, `authorized_operation_stage` and the five digests need planning definitions; kind and target are fixed for the whole Run |
| Receipt | `records.py:421-516`, binding `review/validate.py:49-63` | as-is schema, planning binding | issued only by a seal, `unresolved_obligations == 0` |
| Consumption | `records.py:521-649` | as-is for a planning kind | `terminal_event_id`, `terminal_event_type`, `authorized_result_commit_sha` must be all null for a non-Work kind (`:607-613`); unique by Receipt (`review/store.py:446-464`); no field for created IDs or a commit SHA |
| CandidateSnapshot | `records.py:699-780` | as-is, snapshot mode | stored at `candidate-snapshots/<candidate_hash>.yaml`: one snapshot per hash, so the bytes must be a pure function of the Candidate |
| TaskInput | `records.py:789-874` | as-is schema, planning binding | request envelope is planning-specific |
| Supersession | `records.py:652-694`, `review/validate.py:240-325` | as-is | needed only if a sealed planning Receipt is invalidated before use (Q10) |
| Review ID kinds and reservation keys | `ids.py`, `gate.py:40-78`, `Mutation.reserve_id` | as-is | reservations are per mutation: a Run reserved by one mutation cannot be reached by another |
| Same-Run serialization | `gate.py:102-157` | as-is | Measured: once the planning mutation's scope holds the token, `pending_generation_mutations` finds it and `next_generation_scope` refuses with `review_generation_pending` |
| Persistence preflight | `gate.require_committable` (`:162`), `gate.require_persisted` (`:196`) | as-is | Measured |
| Settlement check | `gate.validate_settlement` (`:239-312`) | as-is | Measured |
| `create_file` effect (immutable, no-follow, exclusive) | `mutation.py:231-259`, `:1775-1788`, `:2061-2140`, `fsafe.py` | as-is on Windows | POSIX: refused at record time, `review_create_unsupported` (`fsafe.py:130`, `:523-537`) |
| Projection kinds, `normative()` | `projections.py` | as-is container, planning binding for content | registration effects are `AuthorizedTransitionProjection`; Receipt and Consumption are `OperationMetadataProjection` |
| `PersistedProjectionAdapter`, `ReservedIds`, `prove_round_trip`, `prove_expected_scope` | `adapter.py` | planning binding | two adapters: Roadmap and Phase entry |
| Review Context | only `review_context_hash` fields | planning binding | P1 has no builder |
| Effective Policy | only `effective_policy_hash` fields | planning binding | no Policy subsystem exists (R10) |
| Evidence foundation (`EvidenceDeclaration`, `ClassCoverage`, `MechanismProof`) | `closure.py:54-327` | not in P2 for completeness and reuse; `evidence_digest` content is a planning binding | unknown completeness is fresh-use only, and P2 reuses nothing across Candidates |
| ReviewValidity foundation (`ReviewValidityClosure`, `may_reuse`) | `closure.py:330-559` | not in P2 | HEAD-advancement reuse is P3 |
| `WorkTerminalActivation` | `records.py:877-931` | not in P2 | P3 |
| `validate_review` inside `validate_project` | `review/validate.py`, `validate.py:302-332` | as-is | Measured: gated runs validate clean, tampering is reported |
| Mutation Controller rules (branch binding, own bytes, commit ID, exact publication, projection before replay) | `mutation.py` | as-is | Measured over every interruption window of §12 |

Minor P1 observation, message only: `gate.py:139` and `:149` list `record.get("id")`, but a pending record carries `mutation_id`, so the diagnostic prints `None`. The refusal and its code are correct.

## 7. Candidate freeze points

**Live.** No draft is persisted. The first durable form of a plan is the runtime request or design identity; the first canonical form is its registration. P2's Candidate would be the first canonical, committed representation of a plan before it is registered.

### 7.1 RoadmapPlan

Freeze after L5 and after the part of L6 that precedes the first domain effect:

- the mutation exists and holds the request in its invocation;
- `roadmap`, `phases:phase:<key>` and `phases:rel:<i>` are reserved — **Measured (probe 2):** reserving them first under these keys gives exactly the IDs the unchanged registration then uses;
- Phase CREATE precheck, relation payload rules and the projected structure check have passed (`roadmap.py:494-496`);
- before `add_effects("roadmap", ...)` (`roadmap.py:497`).

### 7.2 PhaseEntryDesign

Freeze after E6 and after E7's payload check:

- the mutation exists and holds the design in its invocation;
- every identity of every stage is reserved under the keys `register_works` uses (`create.py:251-259`): `works:work:<key>`, `works:rel:<i>` for `planned_next` then `requires_completion`, `works:related:<key>:<i>`, `integration:work:integration`, `integration:rel:<i>` (one per normal Work), `integration:related:integration:<i>`, `confirmation:work:confirmation`, `confirmation:rel:0`, `confirmation:related:confirmation:<i>` — **Measured (probe 5):** the unchanged `_expand_phase` used exactly these Work, relation and Related IDs;
- `validate_work_specs` has passed for every stage (`roadmap.py:984-990`), the entry rules have passed, and for review-v1 the R9 self-selection rule (§8.4);
- before the first `register_works` records stage `works`.

### 7.3 What the Candidate holds

The normalized semantics, the reserved IDs, and the declared base the plan depends on. Not in the Candidate: display numbers (decided when a stage is recorded and read back from it afterwards — BL-045), the commit message (it carries the display), file layout, ledger order, timestamps, the mutation ID.

### 7.4 A round-trip check can run at the freeze point

**Measured (probe 4).** For all 13 inputs tried — 9 Roadmap, 4 Phase entry, covering every kind of loss in §10.2 — `ProjectView.with_effects(<the effects the operation recorded>)` on the pre-write state read exactly what `ProjectView.load` read after the write. `with_effects` reads entity files through the store's own rules (`state.py:149-190`, `store.as_read_back`). A Candidate whose semantics would not survive the canonical reader can therefore be refused at the freeze point, before any Review record or domain effect exists.

## 8. Review insertion points

### 8.1 The eight points on the live flow

| # | point | RoadmapPlan | PhaseEntryDesign | durable as |
| --- | --- | --- | --- | --- |
| 1 | Candidate freeze | between `roadmap.py:496` and `:497` | in `_expand_phase` after `:990`, before `:997` | recomputable from the invocation and reserved IDs |
| 2 | Review task acceptance | a stage recording snapshot, task input and generation 1 (`open`, accepted task descriptor) | same | recorded `create_file` effects, then the working tree |
| 3 | external reviewer launch boundary | after a commit-only Git stage for point 2 and `gate.require_persisted` | same | local Git |
| 4 | settlement | `gate.validate_settlement`, then generation N+1 carrying the settled task | same | `create_file` |
| 5 | seal and Receipt | one stage: the sealed generation (`receipt_id`, `authorized_operation_stage`) and the Receipt (R3 §7); read back through `ReviewStore` before any use | same | `create_file` |
| 6 | Receipt consumption | re-validate the Receipt against the Candidate, Context and stage; a stage recording the Consumption, before (or together with) the first registration stage | same | `create_file` |
| 7 | actual planning mutation | the live stages `roadmap` (`:497`) and `phases` (`:500`), then the post-apply round-trip proof | the live stages `works`, `integration`, `confirmation`, the live phase structure check (`:1020`), then the round-trip proof | `write_file`, `add_relation` |
| 8 | planning commit and persistence | the live `finalize` Git stage: commit and push (`:271`); postcheck; `complete()` | same (`:1021`) | Git and the destination |

Authorization (points 4-5) and the planning mutation (7-8) are separate stages of one mutation; the Consumption (6) is what binds them. A Receipt registers nothing by itself — a not-authorized run in probe 2 registered nothing and left an open, unconsumed chain.

**Measured shape (probe 2, uninterrupted).** Commits `initialize project` → `probe review accept` (local only) → `create roadmap R-01` (commit and push; destination equals local HEAD); 7 Review files; `validate_project` → no problem; Roadmap `active` and both Phases `unstarted`, exactly as in a legacy run. Probe 5 shows the same for Phase entry.

### 8.2 Sequence

```text
create_roadmap(plan)                                 enter_phase(phase_id, design)
  L1-L5 unchanged                                      E1-E6 unchanged
  L6 reserve roadmap / phase / relation IDs            E7 reserve every stage's IDs (register_works keys)
     decide_phases + refuse_invalid_phase_writes          validate_work_specs (all stages); R9 (review-v1)
  -- (1) Candidate freeze -----------------------------------------------------------
     review-v1: projected round-trip check (7.4)
     reserve Run / task IDs; extend scope with the gate paths and the serialization token
     gate.require_committable
  -- (2) stage: snapshot + task input + generation 1 (open, accepted)
  -- (3) commit-only Git stage; gate.require_persisted; reviewer(task input)
  -- (4) gate.validate_settlement; stage: generation 2 (settled)
         adjudication -> obligations
  -- (5) stage: sealed generation 3 + Receipt; ReviewStore read-back
  -- (6) re-validate; stage: Consumption
  -- (7) live registration stages; round-trip proof on ProjectView.load
  -- (8) live finalize (commit + push); postcheck; complete()
```

### 8.3 RoadmapPlan contract questions

| question | answer from the live repository |
| --- | --- |
| reviewed artifact | the decided plan as the Project will read it once registered, resolved through the reserved IDs: Roadmap name, background, desired state, scope / out-of-scope (present-and-stripped or absent); the Phases in declared order (key → reserved `p_` ID, name, desired state); the Phase relations in declared order (type, endpoints resolved to reserved or existing `p_` IDs, reserved `rel_` ID) |
| semantic fields of the projection | the above, plus the projection semantics version and the declared base (existing Phases any relation names, with the state the plan was judged against) |
| presentation-only, derived or unstable | display `R-xx` / `P-xx` (entity counts at stage-record time, `roadmap.py:484`, `phase_create.py:149`); commit message; frontmatter layout; ledger order and whole-file rendering; timestamps; mutation ID; lock holder; reserved ID *values* (stable inside one mutation, new in another) |
| `candidate_hash` over | the `ReviewedArtifactProjection` of those semantics with the reserved IDs, the semantics version and the declared base — never over Receipt or Consumption metadata (Candidate 7 §4.1) |
| deterministic reconstruction | yes: the request identity and the reserved IDs rebuild the Candidate byte for byte (Measured: every resumed window re-derived it and its `create_file` classified `applied_matching`) |
| snapshot or `builder_v1` | snapshot. `builder_v1` would need clone-safe inputs, and the request and reserved IDs live only in the runtime record |
| Review Context | Open, Q4 |
| Effective Policy | Open, Q5 |
| Receipt `target_identity` | the reserved Roadmap ID recommended: it is the entity the authorized registration creates, and the Run key `review-run:<kind>:<target>` needs a colon-free part known before generation 1 (Q8) |
| `operation_identity` | the operation plus a digest of the request identity (Q8); the mutation itself is already `Consumption.operation_mutation_id` |
| `authorized_operation_stage` | one name for the whole registration (stages `roadmap` and `phases` with their `finalize`), because the field is single-valued and the registration spans several stages (Q8) |
| Consumption bound to | the same `roadmap-create` mutation (`operation_mutation_id`), target the reserved Roadmap ID, the authorized Candidate; recorded before stage `roadmap`; committed in the registration commit |
| no invented Work terminal event | the live schema already enforces it: the three Work-binding fields are all null for a planning kind, and uniqueness is by Receipt (§9) |
| supersession / stale generation | a changed plan is a different request: never the same mutation (`require_same_request`), so always a new Candidate and a new Run. Inside one mutation only a changed base or Context can make a sealed Receipt stale (Q10). What can change while the mutation is pending is limited by scope: other Roadmap creations, Phase additions and Phase entries are blocked and lifecycle operations on other entities are not (Measured, §12); plan exclusion and START are blocked by their declared scopes (every ledger) |
| exact Candidate and task after a crash | runtime record intact: invocation + reserved IDs rebuild the Candidate; the task is `task-inputs/<task>.yaml` for the ID reserved under `review-task:<run>:<slot>`, checked by `provenance_problems`. Runtime record lost: nothing links a new mutation to the old Run (Q11) |

### 8.4 PhaseEntryDesign contract questions

| question | answer from the live repository |
| --- | --- |
| exact semantic identity | the design identity (names verbatim, desired states stripped, declared order kept, `design_identity`) with `phase_id` and the reserved IDs; as reviewed semantics: the normal Works in declared order (name, desired state, Related type / to / condition), the integration Work, the optional confirmation Work (its target = the reserved integration ID), the design's `planned_next` / `requires_completion` and the generated `requires_completion` edges, affiliation (`phase_id`, `roadmap_id`), and the canonical first Work |
| Candidate freeze point | 7.2 |
| which operation stage is authorized | the Phase-entry registration of that mutation: `works`, `integration`, `confirmation` and their `finalize`. Not a Phase lifecycle transition (Phase entry writes none, 4.5) and not the START handoff |
| what the Receipt allows | "this exact design, with these reserved IDs, may be registered into this Phase by this Phase-entry request" |
| what the Consumption binds | the `phase-entry` mutation, target `phase_id`, the authorized Candidate |
| keeping Review out of Phase lifecycle truth | §13; the canonical first Work is computed from `ProjectView`, and neither the handoff nor START reads a Review record |
| design changes | a changed design is a different request: `_require_resumable` refuses it and leaves the record untouched; once the expansion finished a new design meets `phase_already_expanded`; once a not-authorized run completed, a new design is a new mutation and a new Run. A sealed Receipt can go stale inside one mutation only through Context or base changes (Q10) |
| retry / recovery / replay | §12; Measured for Phase entry in probe 5 |
| order against the canonical planning mutation | Consumption before stage `works`; the live registration unchanged; the round-trip proof after the last registration stage and the live phase structure check, before `_finalize` |
| `entry` under review-v1 | the P1 contract repair (§6, externally adjudicated) freezes that a reviewed design must be canonically self-selecting: unique selection A with `entry = A` or no entry is valid; `entry = B` against A, or `entry = A` among equals, is not. Live `enter_phase` accepts both rejected rows (4.4), so the review-v1 path adds a refusal the legacy path does not have, and `skills/roadmap` has to state it (Q13) |

## 9. Receipt / Consumption integration points

### 9.1 Receipt values for a planning kind

| field | value |
| --- | --- |
| `review_run_id` | reserved in the planning mutation under `review-run:<kind>:<target>` |
| `review_generation` | the sealing generation |
| `review_kind` | a planning kind string without `:` (Q8) |
| `target_identity` | reserved Roadmap ID, or `phase_id` |
| `operation_identity` | operation plus request- or design-identity digest |
| `authorized_candidate_hash`, `review_context_hash`, `effective_policy_hash`, `coverage_hash`, `adjudication_hash`, `obligation_digest`, `authorized_operation_stage` | copied from the sealing generation; `review/validate.py:49-63` checks every pair |

### 9.2 Consumption for a planning kind

**Live.** `consumption_id` reserved under `review-consumption:<receipt_id>` in the same mutation; `receipt_id`, `review_run_id`, `review_generation`, `review_kind`, `target_identity`, `operation_identity`, `authorized_candidate_hash` repeated from the Receipt (`review/validate.py:67-75`); `operation_mutation_id` = the planning mutation; `terminal_event_id`, `terminal_event_type`, `authorized_result_commit_sha` all null — the reader refuses a partial Work binding (`records.py:607-613`). Uniqueness is the Receipt index; planning Consumptions are absent from the terminal-event index by construction (`review/store.py:466-484`). A Consumption of a superseded Receipt is a validation problem (`review/validate.py:348-355`).

What the live schema cannot hold, although R8 §8 and R9 §9 list it: the registration commit SHA, the created IDs, a semantic projection digest, the adapter or loader identity. The unknown-field rule refuses any extra field (`records.py:143-161`). Seam C-2 in §14.

### 9.3 Placement and checks

1. Seal stage applied, then generation and Receipt read back through `ReviewStore` (R3 §7).
2. Before recording the Consumption: the Receipt still binds the Candidate recomputed now, the Context computed now, and the stage about to be applied; the Receipt is not superseded; no Consumption exists for it (Q10).
3. Consumption stage recorded and applied.
4. Registration stages, round-trip proof, Git stage.

**Measured:** the Consumption and the registration arrive in one commit; every window between them resumes (§12).

`Authorization != Consumption` holds throughout: a Receipt can stand unconsumed (a crash before point 6; runtime loss, Q11), and a Consumption exists only in the mutation that registers.

## 10. Semantic round-trip surface

### 10.1 The chain in live code

| step | live code | what it does to the meaning |
| --- | --- | --- |
| reviewed Candidate | (P2) | — |
| operation input | caller-built `RoadmapPlan` / `PhaseEntryDesign` | none |
| request / design identity | `roadmap_request_identity`, `design_identity` | name verbatim; desired state and background stripped; optional sections present-and-stripped or absent; order kept |
| decided effects | `render_body` (`store.py:250-256`: `# name`, `## heading`, `text.strip()`), `render_entity` (YAML frontmatter: IDs, display, affiliation, origin, kind, target), relations through `yamlish` (unsafe strings JSON-quoted) | display from entity counts |
| persisted bytes | `durable_write_text`: UTF-8, no newline translation | CR and CRLF reach the disk as given |
| Mutation Controller classification | `classify` of `write_file` compares `read_text()` (universal newlines) with `_normalize(content)`, which folds CRLF only (`mutation.py:156-157`, `:1910-1923`) | disagrees with the writer for a lone CR |
| canonical reread | `_parse_entity` via `read_text()` (CRLF and CR → LF); `Entity.name` = first line starting `# `, stripped (`store.py:118-122`); `Entity.section` = first matching `## heading` up to the next `## `, stripped (`:240-247`); relations through `yamlish.load` | lossy for some inputs |

### 10.2 Measured divergence

Probe 1; every row was accepted by live code and passed `validate_structure`.

| input (one field varied) | recorded request or design | what the Project reads back |
| --- | --- | --- |
| Roadmap name with a trailing space, a leading space, or a trailing newline | verbatim | `RM` |
| Roadmap name `RM\nsecond line` | verbatim | `RM` |
| Roadmap name with U+2028 inside | verbatim | the part before U+2028 |
| Roadmap name `RM\n## 達成したい状態\nINJECTED` | desired state `DS` | name `RM`, **desired state `INJECTED`** |
| background containing a `## 達成したい状態` line | desired state `DS` | background `BG`, **desired state `INJECTED`** |
| desired state `line1\r\nline2` | CRLF | LF |
| desired state `x\n## other\ny` | full text | `x` |
| Phase name with a trailing space | verbatim | stripped |
| Phase desired state repeating `## 成立させたい状態` | full text | the part before the repeat |
| Work name with a newline, or a trailing space | verbatim | first line / stripped |
| Work desired state with CRLF, or repeating its heading | as given | LF / truncated |
| controls: blank and padded scope, relations between new Phases, a padded Related target, a condition with an extra key, a confirmation Work | — | equal |

**Lone CR (probe 1b).** A lone CR in a Roadmap name, a Roadmap desired state, a Phase desired state or a Work desired state: the first run records and applies the write, its own next classification then reads `applied_mismatch`, the run stops with `reconcile_required`, and every retry stops the same way; HEAD never moves and the pending record stays. Writer (no translation), classifier (CRLF only) and reader (CRLF and CR) normalize differently. A live defect outside P2 (§17).

**Projection equals reload (probe 4)** in 13 of 13 cases, lossy ones included (7.4).

### 10.3 What to compare

- Not the text of the request: the reader is lossy, and a file also carries IDs, display and layout.
- Not bytes alone: the Mutation Controller already proves the bytes (`wrote`, own-bytes checks), and identical bytes still read back as a different meaning in the rows above.
- **Canonical semantic projection equality**: `normalize_candidate(reviewed semantics with reserved IDs)` equals `normalize_persisted(the created entities and records read through ProjectView — Entity.name, Entity.section, relation and Related records — selected by reserved ID and ordered by the Candidate's declared order)`, checked:
  1. at the freeze point, on the projection — a Candidate that does not equal its own projected reading is refused before any Review record exists (review-v1 path only);
  2. after the last registration stage is applied, on `ProjectView.load`, before the Git stage is recorded — a mismatch stops before the commit;
  3. for scope: the created entity, relation and Related sets equal the reserved sets exactly (`prove_expected_scope`);
  4. physically: the commit carries exactly the bytes the mutation wrote (`_require_own_bytes_committed`) and only the recorded paths (`_recorded_publication` checks `commit_changes` against the recorded paths before the push);
  5. for Phase entry: the canonical first Work computed from `ProjectView` equals the reviewed entry, or the entry is absent with a unique canonical selection (R9).

This is what mechanically prevents "A was reviewed and authorized, B was stored": B cannot be stored without failing check 2, and A cannot be authorized if its own reading is not A (check 1).

Residual: Git content filters between the working tree and the commit (clean / smudge, `core.autocrlf`). The loader reads the working tree, and P2 proves before the commit; binding Git persistence semantics is R6 / P3 territory, and a post-commit, pre-push proof would need the split publication that P2 excludes (seam C-3).

## 11. Persistence / Git boundaries

### 11.1 P1 invariants on the gated path

| invariant | how the gated path keeps it |
| --- | --- |
| unknown != proof | `require_committable` and `require_persisted` stop when Git cannot answer; a round-trip mismatch stops; P2 reuses nothing across Candidates |
| foreign commit != operation-owned commit | live commit-ID identity and exact-commit publication unchanged; P2 adopts no commit. If someone else commits the accepted records first, `require_persisted` still holds (they are committed) and nothing is claimed as the mutation's own |
| Git-write compatibility != Review-validity compatibility | path non-overlap is never read as Review validity; a Context or base change means a new generation or a new Candidate (Q10) |
| Authorization != Consumption | separate records in separate stages; unconsumed Receipts are valid |
| Review metadata != lifecycle truth | §13 |
| no reset, rebase recovery, amend recovery, force push, branch-tip fallback | the gated path adds no Git primitive: a commit-only `gitops.finalize(..., destination=None)` and the live combined stage |

### 11.2 What must be persisted before the external reviewer is launched

**Live (R3 §3-§4, `gate.require_persisted`).** The CandidateSnapshot, the TaskInput and the gate generation that accepted the task, committed in local Git with no working-tree or index difference. P1 does not require a push; remote-less Projects are valid. At that moment the runtime record (request, reserved IDs, recorded stages) is not clone-safe, and no planning registration may exist yet. **Measured:** the probes cross this boundary with a commit-only stage.

### 11.3 Git stage shapes

**Measured.** An intermediate commit-only Git stage followed by the live combined `finalize` stage (commit, then push of exactly that commit) passes `_recorded_publication`, the branch-binding rules and the own-bytes rules; the destination ends equal to local HEAD. The R5 §12.2 split publication is not used (seam C-1). `rules/git` allows several commits and pushes per operation.

### 11.4 Publication side effects of a local-only accept commit

**Live.** While the accept commit is local and the lock is released (an asynchronous reviewer wait), any other operation allowed to run (a Phase hold, Measured allowed) publishes it as part of its own base history. Commits someone else makes before the final Git stage is recorded are published by the final push as base history; only commits after the recorded commit are excluded (`rules/git` Push destination).

### 11.5 Pre-existing dirty ledgers

**Live.** Roadmap creation and Phase entry have no `ensure_separable_before_effects` (it is called only by START, lifecycle decisions and plan exclusion: `roadmap.py:1053`, `:1251`, `start.py:509`, `:3298`); BL-041 lists them as residual (4). The Git stage refuses on the snapshot recorded at `_open`, and Roadmap owners never narrow that snapshot (`narrow_preexisting_dirty` is START-only, `start.py:514`). **Measured (probe 7):** with a person's line already in `roadmap.yaml` and a plan with a Phase relation, the run applied every registration effect — the ledger re-render dropped the person's line — then stopped with `dirty_overlap`; after the person discarded their change the retry stopped with `reconcile_required`. A gated run would reach the same stop after the reviewer ran (Q14).

### 11.6 Platform

**Live.** On POSIX the immutable create is refused before anything is written (`review_create_unsupported`, checked in `validate_effect` and at the create boundary), so a gated planning run stops before any Review effect is recorded and its mutation is abandoned. Review-gated planning is available only where `fsafe.immutable_create_supported()` is true, i.e. Windows at this baseline (HUMAN-1).

## 12. Recovery matrix

Terms: **resume** — the same pending mutation continues from its record; **replay** — recorded effects are classified again and only unapplied ones are applied; **retry** — an external action is repeated under the same identity (the same review task ID, the same push); **reconcile required** — STOP with the record untouched; **fresh Candidate required** — a new mutation and a new Review Run.

Baseline conditions for the table: the runtime record is intact, HEAD is on the decided branch, nobody changed a written path. Measured windows are from probe 2 (Roadmap, 13 windows) and probe 5 (Phase entry, 4 windows); in every measured window the second run resumed the same mutation and ended in the same state as an uninterrupted run.

| # | failure point | RoadmapPlan | PhaseEntryDesign | measured |
| --- | --- | --- | --- | --- |
| 1 | before the Candidate snapshot is written (IDs reserved, no Review effect) | resume; the Candidate is recomputed byte for byte | same | R `after_reservations` |
| 2 | after the Candidate snapshot is written (recorded; applied or not) | resume + replay | same | R `accept_recorded`, `accept_applied` |
| 3 | after the TaskInput is written | resume + replay | same | R (same stage as 2) |
| 4 | after the accepted generation is written, not yet committed | resume + replay; the accept Git stage is then recorded and made | same | R `accept_applied` |
| 5 | before the reviewer is launched (accept commit made, persistence proven) | resume; first launch under the same task ID | same | R `accept_committed`; PE `accept_committed` |
| 6 | after the launch, before the result is settled | resume + retry: the same task ID is launched or fetched again from the canonical task input; a result held only in process memory is lost | same | R `reviewer_returned` — reviewer called twice, under the one reserved task ID |
| 7 | after the settlement generation is written | resume + replay; the reviewer is not called again | same | R `settle_recorded`, `settle_applied` |
| 8 | at the sealed generation / Receipt boundary | resume + replay of whichever of the two creates is unapplied (one stage); both are read back before use | same | R `seal_recorded`, `seal_applied`; PE `seal_applied` |
| 9 | Receipt issued, not yet consumed | resume; the Receipt is re-validated, then consumed | same | R and PE `seal_applied` |
| 10 | Consumption written, planning mutation not yet | resume + replay (Consumption `applied_matching`); the registration proceeds | same | R `consume_recorded`, `consume_applied`; PE `consume_applied` |
| 11 | planning mutation applied (part or all), not committed | resume + replay; the live projection check runs before the replay | same; recorded stages are read back | R `registration_roadmap_applied_phases_not`; PE `works_applied_integration_not` |
| 12 | committed, not pushed | resume: the commit matches by its recorded ID; the push is classified by a dry run and made by exact refspec | same | R `final_commit_made_push_not` |
| 13 | committed and pushed, stopped before `complete()` | resume: everything matches; `complete()` | same | live rule |
| 14 | after `complete()` (record removed), same request again | a new mutation: a second Roadmap, a fresh Candidate and a new Run | `phase_already_expanded` | probe 6 (legacy path) |

The one difference after a resume: the closed runtime record of a resumed mutation stays in `.workline/runtime/mutations/` (`Mutation._own_record_removable` never removes a resumed record, `mutation.py:604`) — existing behaviour, not Review-specific.

Variants at any point:

| condition | outcome | source |
| --- | --- | --- |
| a different request or design | reconcile required, record untouched | `require_same_request`; `_require_resumable` |
| runtime record lost (fresh clone, runtime cleanup) | fresh Candidate required: new mutation, new IDs, new Run; the old Run's committed records stay as valid orphans (`review/validate.py` validates orphans) | Q11 |
| HEAD on another branch, or history rewritten | reconcile required | `_require_decided_branch`, `_require_finalized_branch` |
| a written path changed by someone else | reconcile required | own-bytes checks |
| a Review record of the pending Run changed | reconcile required: the `create_file` classifies `applied_mismatch` — even when the changed record is itself canonical and valid, which `validate_project` alone would accept | probe 3 |
| structure changed by an independent operation while pending (e.g. an endpoint Phase cancelled) | STOP `postcheck_failed` before the replay, record untouched | live projection before replay |
| the parent Roadmap held or cancelled while a Phase entry is pending | STOP at the Phase-entry precheck (`roadmap_held` / `spec_violation`); held → continues after the Roadmap is resumed; cancelled → reconcile | live precheck (the Roadmap entity is outside Phase entry's scope) |
| Review Context changed between seal and consumption | Open: supersede and re-review inside the mutation, or STOP | Q10 |
| Review not authorized | Review records committed (and pushed), mutation completed, nothing registered; a repaired plan is a fresh Candidate | probe 2 |
| POSIX | STOP `review_create_unsupported` before any Review effect; the mutation is abandoned | `fsafe` |
| a pre-existing dirty ledger the registration commits | `dirty_overlap` at the final Git stage after the registration was applied, then stuck | probe 7, Q14 |

Operations a pending gated planning mutation blocks (**Measured**, probe 2, mutation left pending after the reviewer returned): `create_roadmap` (any plan), `add_phases`, `enter_phase` → `reconcile_required` (scope overlap on `roadmap.yaml`); Phase hold and resume on another Roadmap's Phase, direct CREATE → proceed. START declares every ledger (`start.py:109-113`) and is therefore blocked as well. With a synchronous reviewer the whole Project answers `project_operation_busy` for the reviewer's duration instead.

Nothing in this matrix is the P3 Work-terminal recovery contract: no Work terminal event, no result commit K1, no proof checkpoint between commit and push.

## 13. Lifecycle separation proof

### 13.1 Static

- `state.py` imports only `.errors` and `.store` (`state.py:16-17`). `ProjectView.load` reads the entity directories, the two relation files and the event log (`:139-147`); `list_entities` globs `.workline/<roadmaps|phases|works>/*.md` (`store.py:440-445`), which never reaches `.workline/review/*.yaml`.
- `ProjectView.with_effects` handles `write_file` on entity paths, `add_relation`, `remove_relation` and `append_event`, and ignores `create_file` (`state.py:170-185`), so a projection that includes Review effects projects no lifecycle change.
- Lifecycle is derived from events only (`derive_work_state`, `derive_phase_lifecycle`, `derive_roadmap_lifecycle`, `state.py:65-117`); neither Roadmap creation nor Phase entry writes an event.
- `normative(OPERATION_METADATA)` is false (`projections.py:50-62`).
- `validate_structure`, which operations use as precheck and postcheck, does not read Review; `validate_project` reports Review problems in a separate pass (`validate.py:302-332`).
- `roadmap.py`, `phase_create.py`, `create.py`, `ops.py`, `start.py` do not import `workline.review`; `mutation.py` imports only `fsafe` and `paths` to guard `create_file`.

### 13.2 Measured

- Gated and legacy creation leave identical lifecycle: Roadmap `active`, Phases `unstarted`; after a gated Phase entry the Phase is `unstarted` with four `unstarted` Works (probes 2, 5).
- A finished gated Run with a tampered generation (probe 3): lifecycle unchanged; `validate_project` reports `review_record_noncanonical` and `review_record_missing`; `ReviewStore.gate_chain` refuses; ungated operations on the planned entities (Phase entry, Roadmap hold) run normally, because nothing they read changed.
- A pending gated Run with its own generation replaced by a *valid* different record (probe 3): the resume stops with `reconcile_required`; lifecycle unchanged; nothing registered.

### 13.3 STOP versus reinterpretation

A broken Review record can stop the planning operation that relies on that Run — correct and fail-closed. It cannot change what any lifecycle history means, because nothing that derives lifecycle reads it. The first is the gate working; the second is structurally impossible as long as P2 keeps the rules below.

### 13.4 What P2 must keep

1. No Review read in `state.py`, `ProjectView`, `validate_structure` or any selection or startability code.
2. A gated operation reads only its own Run's records, as the authorization of its own mutation.
3. No cross-operation Review precondition. For example, "Phase entry requires that its Roadmap was reviewed" would make Receipt / Consumption metadata a normative progression input, which `normative()` forbids.
4. The R9 canonical first Work is computed from `ProjectView`, never from a Review record.

Verdict: **PASS**.

## 14. Open implementation questions and contract seams

Each item has a default that live code or frozen contracts already point to; none needs a human except where §16 says so.

### 14.1 Open questions

**Q1 Reviewer invocation.** P1 has no launch mechanism. Live precedents: START's executor, a callback run inside the lock (`start.py:187-201`), and START's `question_wait`, which returns with the mutation pending and its scope held. Measured consequences are in §12. Default: a synchronous reviewer callback, mirroring the executor; an asynchronous wait only if a human reviewer is ever required.

**Q2 Not-authorized outcome.** A mutation with a recorded effect cannot be abandoned (`mutation.py:620-627`), and a pending one blocks every Roadmap-structure operation. So "not authorized" has to finalize the Review records (commit, and push when a destination exists), `complete()` the mutation without registering, and return a distinct status. Measured in probe 2; a repaired plan then runs as a new request.

**Q3 Candidate and `candidate_hash`.** Content: semantics version, operation, the normalized semantics as the canonical reader reads them, the reserved IDs, the declared base. The snapshot bytes must be a pure function of that content (one snapshot per hash, §6).

**Q4 Review Context.** What can change a plan's meaning or validity without changing the plan: the declared base (RoadmapPlan: existing Phases named by relations and their states; Phase entry: `phase_id`, Phase and Roadmap lifecycle, predecessor states, the Phase's Works); a loader / renderer identity — live implementation identity is its origin only, not its content (`implementation.py`, `rules/git` Workline implementation), so a content digest of the modules that render and read would be new; authority digests (`registry.md`, `skills/roadmap`, `phase-create`, `create`, `review`); projection semantics version; review kind. Nothing runtime-only or unstable.

**Q5 Effective Policy.** No Policy subsystem exists (R10). A versioned planning policy declared in canonical authority (`skills/review`) and hashed: reviewer slots and roles (the four roles of the Phase Design notes are non-authority), the authorization rule (no unresolved HIGH / MID), LOW handling, failure and timeout disposition, adjudication rule version.

**Q6 Evidence.** What `evidence_digest` covers for planning: mechanical results (projected structure validation, round-trip check, R9 check) and reviewer report digests. R11 completeness is not needed, because P2 reuses nothing.

**Q7 Adjudication and obligations.** P1 stores only digests (`adjudication_digest`, `obligation_digest`, `raw_report_set_digest`); raw reports are runtime-only material (R1 §3). P2 defines the canonical input of those digests and the zero-obligation seal; full history is P5.

**Q8 Identity strings.** `review_kind` values (no `:`, `gate._require_key_part`), `target_identity` (reserved Roadmap ID / `phase_id`), `operation_identity` (operation plus request digest), `authorized_operation_stage` (one name per registration unit).

**Q9 Stage layout.** Stage names must not collide with the live ones (`roadmap`, `phases`, `works`, `integration`, `confirmation`, `finalize`); seal and Receipt in one stage (R3 §7); which Review records are committed at the launch boundary and which with the registration; whether the Consumption joins the first registration stage.

**Q10 Staleness at consumption.** Planning-native and exact: recompute the Candidate and Context at point 6; any difference either supersedes (new open generation plus supersession record, fresh tasks) inside the same mutation or stops. No P3 reuse fast path.

**Q11 Runtime loss.** The committed records survive, the owner's record does not, and reservations are per mutation. Default: a fresh Candidate; the old Run stays a valid orphan. The alternative, an exact canonical rule for adopting an in-flight Run, is new recovery surface. Seam C-6.

**Q12 Round-trip refusal set.** Defined mechanically as "the projected reading differs from the Candidate" (7.4), not as a list of forbidden characters. The Candidate must not normalize a lone CR away, or the §17 classifier defect strands the mutation after the Review.

**Q13 R9 self-selection.** Place it in `roadmap.py`'s review-v1 path and in `skills/roadmap`; the legacy path, and `tests/helpers.simple_entry` which depends on it, stay as they are.

**Q14 Early dirty-overlap check.** On the review-v1 path, call `ensure_separable_before_effects` for every path the registration will commit before the first Review effect. A new refusal on the new path only.

**Q15 Invocation marker.** A review-v1 run needs a marker in its invocation (the probes used an extra key). Measured consequence: a legacy retry of the same plan while a gated one is pending meets `reconcile_required` through scope, because slot lookup finds the gated record and the exact invocation does not match.

**Q16 Pins to keep.** Public method sets of `Mutation` and `MutationController` (`test_project_start_recovery.py:978-991`: add module-level functions, not methods); `EFFECT_KINDS` (`test_decision_branch_binding.py:676`, `test_cancel_decision_resume.py:367`); `rm.register_works` called as `(mutation, stage, specs, relations)` with stage names `works` / `integration` / `confirmation` (`test_phase_entry_contract.py`); the `rm.validate_structure` call order in Phase entry (1 = precheck, 2 = phase structure check, `test_phase_entry_contract.py:529-555`), so a new check belongs in another module; `OPERATION_LEDGERS` (`test_declared_write_scope.py:162-191`), so Review paths are added dynamically like entity IDs; `ROADMAP_REQUEST_VERSION`, `DESIGN_IDENTITY_VERSION` and their shapes.

**Q17 Authority text.** P2 changes canonical Skills (`skills/roadmap`: the gated flows, R9, the not-authorized outcome; `skills/review`: planning kinds, policy, adjudication). `rules/human-confirmation` treats that as a Workline common-rule change, which the P2 contract approval covers.

**Q18 Ungated planning writers.** `add_phases`, Related maintenance, plan exclusion with replan, START derivations and direct CREATE remain ungated under P2 as scoped (3.7).

### 14.2 Seams with frozen P1 contract text

These are contract-text conflicts, not live-code conflicts; each has a resolution inside Candidate 7.

**C-1 — R5 §12.3.1 publication discriminator.** Its "Review-v1 durable operation metadata" is any review operation identity, contract, Run or generation binding on a mutation; case B (metadata present, `publication_contract` absent) and case E (`current-combined` against such metadata) fail closed. A P2 planning mutation carries exactly such bindings and publishes through the combined stage, because the split is out of scope. Live code does not implement the discriminator yet (`publication_contract` appears nowhere in `src/`), but P3 will. Resolution: scope R5 §12.3 to Work-terminal review-v1 result publication; planning mutations carry no `publication_contract`.

**C-2 — R8 §8 / R9 §9 Consumption bindings.** They list the registration commit SHA, created IDs, a semantic projection digest and an adapter identity. The live Consumption v1 holds none of them, forbids extra fields, and a record cannot hold the ID of the commit that stores it (the rule the Review Skill states for Receipts). Resolution: bind created IDs and semantics through the Candidate (its hash is already in Receipt and Consumption) and the adapter identity through the Context; the registration commit is the commit that adds the Consumption file, derivable from Git and never stored. A Consumption v2 schema is the alternative and changes P1.

**C-3 — R8 §7 / R9 §8 "exact commit-delta proof" after the local commit.** Live finalization applies commit and push in one pass with nothing between, and P2 excludes the split. Resolution: prove semantics before the commit (§10.3 checks 1-3); keep the physical proofs (own bytes before staging; `_recorded_publication` checks the commit's paths before the push); record the Git-filter residual.

**C-4 — R2 §4 / R3 §2 "initial WriteScope holds the generation path and the token".** A planning Run's ID is reserved inside the planning mutation, after it opened. Resolution: extend the scope with the gate paths and the token before the first generation effect is recorded. Every generation of the Run is written by the one mutation that reserved it, and **Measured** after `extend_scope`, `pending_generation_mutations` finds the mutation and `next_generation_scope` refuses.

**C-5 — R3 §9 "the owning mutation binds review_run_id, generation, candidate_hash, … receipt_id".** The invocation is the resume key and must be computable before the mutation opens, so values decided later cannot live there. Resolution: a static review-v1 marker in the invocation (Q15); Run, task, Receipt and Consumption IDs as reserved IDs; Candidate, Context and Receipt bindings through the recorded `create_file` effects.

**C-6 — R3 §4 / R2 §5 same-task rerun after runtime loss.** It presupposes an owner that can re-find its Run; the live owner finds its state only through the runtime record. See Q11.

## 15. Architecture blockers

**None.**

- Ownership: the existing Roadmap mutation owner can own every Review record as a subordinate effect of its own mutation (Measured); Review opens nothing and locks nothing.
- Lifecycle separation: PASS (§13).
- P1 foundation: sufficient as landed; P2 adds planning bindings (§6), not a redesign.
- Semantic round trip: the live reader is lossy, but the loss is predictable before any write (7.4), so the gate can refuse what it cannot authorize truthfully.
- Recovery: every measured interruption window resumes through the ordinary Mutation Controller.
- The C-1..C-6 seams are contract-text scoping within Candidate 7.

Conditional: POSIX cannot write Review records at this baseline, so a planning Review made mandatory for a POSIX Project would make planning impossible there. That is part of HUMAN-1, not an architecture blocker for an opt-in P2.

## 16. HUMAN decisions

### HUMAN-1 — How does review-v1 planning apply?

Why the repository cannot answer it: authority names the owner (Roadmap) and says P2 wires Review into Roadmap creation and Phase entry, but not whether Review becomes required. The frozen R9 repair keeps legacy Phase-entry behaviour "until explicit review-v1 planning activation" without saying what activates it. P1's only activation record is `activation/work-terminal-v1.yaml`, and the namespace validator refuses any other file there (`review/validate.py:447-489`). Making Review a precondition of planning is a Workline common-rule change under `rules/human-confirmation`.

| option | what it means | gains | costs |
| --- | --- | --- | --- |
| A. per-invocation opt-in | the caller (`skills/roadmap`) asks for review-v1 on a given `create_roadmap` / `enter_phase`; without it the live path runs unchanged | no P1 change; legacy callers and tests unchanged; POSIX fails closed only when opting in | enforced by Skill instruction, not mechanically; ungated plans stay possible |
| B. durable per-Project activation | an immutable activation record per Project; afterwards ungated planning is refused there | mechanical enforcement; mirrors the P3 pattern | P1 namespace and validator extension; a human-confirmed maintenance owner to write the record; classification of Roadmaps planned before activation; POSIX Projects can never activate |
| C. global and mandatory when P2 lands | every planning call needs a reviewer | strongest enforcement | every existing caller and nearly every test (`helpers.simple_roadmap`, `simple_entry`) changes; planning impossible on POSIX; contradicts the frozen "legacy unchanged until explicit activation" |

Recommendation: **A** for P2 — the smallest change consistent with the frozen contracts and with P1's accepted POSIX decision — and B, if mechanical enforcement is wanted, as a separate later decision.

What it changes in the P2 contract: whether P2 adds an activation record and its owner (B), how a review-v1 mutation is recognized (an invocation marker in A, an activation classification in B), and the test strategy.

No other HUMAN decision is raised: the rest of §14 has defaults derived from live code or frozen contracts.

## 17. Incidental live findings outside P2 scope

1. **Lone CR strands Roadmap creation and Phase entry** (probe 1b). Writer, Mutation Controller classifier and reader normalize line endings differently (§10.2); an accepted input leaves a pending mutation that no retry can finish, and it holds its write scope. Not recorded in BACKLOG (the only lone-CR entry concerns commit messages). Not fixed here.
2. **Pre-existing dirty ledger in Roadmap creation / Phase entry** (probe 7): effects applied and the person's line dropped by the ledger re-render before the Git-stage `dirty_overlap`; the retry then stops with `reconcile_required`. Known as BL-041 residual (4); the dropped line is worth noting beside it.
3. **`gate.py` diagnostic** prints `None` for pending generation mutations (§6).
4. **A completed Roadmap creation is not deduplicated**: the same plan again creates a second Roadmap (probe 6). Existing semantics.
5. **A resumed mutation's closed runtime record is kept** (§12). Existing rule.

## 18. Evidence

Every probe is a plain script (no pytest), run with `PYTHONPATH` pointing at the investigation tree's `src`; each asserts the imported `workline` is that tree's; each builds disposable Projects under `%TEMP%` through `tests/helpers.py` and drives only functions the baseline ships. Kept outside the repository: `D:\AIproject\workline-evidence\cases\workline-core-p2-recon\evidence\`.

| probe | script | question | result |
| --- | --- | --- | --- |
| 1 | `roundtrip_probe.py` | request / design identity against the canonical reread | 27 cases: 15 lose text yet are accepted with a valid structure (§10.2), 1 lone CR stuck, 1 explicit `entry` not reconstructible, 10 controls equal |
| 1b | `roundtrip_probe_b.py` | explicit `entry` against the plan; lone CR | entry = B accepted against canonical A; lone CR stuck in 4 of 4 fields |
| 2 | `integration_probe.py` | Review records inside a Roadmap-owned mutation; interruption windows; not authorized; neighbours | clean end state in all 13 windows; not-authorized completion; blocking table |
| 3 | `corruption_probe.py` | broken Review records against lifecycle | lifecycle unchanged; gated resume stops; ungated operations proceed |
| 4 | `projection_probe.py` | pre-write projection against post-write reload | equal in 13 of 13 |
| 5 | `phase_entry_probe.py` | gated Phase entry; pre-reserved IDs; windows | exact IDs used; the uninterrupted run and all 4 interruption windows clean |
| 6 | `retry_after_complete_probe.py` | the same request after completion | second Roadmap; `phase_already_expanded` |
| 7 | `predirty_probe.py` | pre-existing dirty `roadmap.yaml` | `dirty_overlap` after the effects, person's line dropped, retry `reconcile_required` |

Outputs are the `probe*.jsonl` files beside the scripts.

## 19. Checkpoint

```text
Reviewed baseline:            b78be1ccd778ceb2ecd97b90e2f71744bd1b3bc5
RoadmapPlan mutation owner:   roadmap.create_roadmap (owner "roadmap", operation roadmap-create)
PhaseEntryDesign owner:       roadmap.enter_phase (owner "roadmap", operation phase-entry)
Insertion:                    Candidate freeze before the first registration stage;
                              Review stages, then Consumption, inside the same owner mutation;
                              live registration and finalize unchanged
Semantic round trip:          canonical semantic projection equality (not text, not bytes alone),
                              checked on the projection at freeze and on reload before commit
Lifecycle boundary:           PASS
Architecture blocker:         None
HUMAN:                        1 (HUMAN-1, applicability / activation of review-v1 planning)
P3 accidentally activated:    No
Candidate 7:                  RETAIN
Architecture reopen:          No
Status:                       READY_FOR_P2_RECONNAISSANCE_REVIEW
```
