# Review System P2 — Planning Review Gates: Integration Contract Reconnaissance

Status: `RECONNAISSANCE / REPAIRED AFTER INDEPENDENT REVIEW (P2-RECON-001, P2-RECON-002) / NON-NORMATIVE / P2 CONTRACT NOT FROZEN / P2 IMPLEMENTATION NOT STARTED / READY_FOR_P2_RECONNAISSANCE_REVIEW`

Runtime authority is unchanged: `registry.md`, the registry-routed canonical Skills, and the live implementation and tests. This document is not authority. It records what the live repository at the baseline says about connecting the landed P1 Review Core to Roadmap creation and Phase entry, keeps live facts apart from contract choices that are still open, exposes two P2 contract issues the contract freeze has to resolve (C-3, C-4), and names the one decision that needs a human.

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

How to read it: statements are marked

- **Live** — what the baseline code or authority does, with `file:line`;
- **Measured** — what a throw-away probe observed on real Projects (§18), valid only for the flow that probe ran;
- **Frozen P1** — wording of the frozen P1 contract files: not runtime authority, but the constraint a P2 contract must satisfy or explicitly repair;
- **Open P2 contract issue** — a conflict the P2 contract freeze must resolve; the directions listed are not choices made here (C-1..C-6 in §14.2, with C-3 and C-4 the two unresolved ones);
- **Open** — an implementation question with a default the live code or frozen contracts already point to (Q1..Q18 in §14.1);
- **HUMAN** — a decision reserved for a person (§16).

Nothing marked Open is frozen here.

## Repair history

The first revision (`f2df83e`) was reviewed independently. Two HIGH findings were accepted and are repaired in this revision; nothing else was reopened.

- **P2-RECON-001** — the first revision called P1 same-run generation serialization reusable as-is inside one long-lived planning mutation, adding the gate paths and the serialization token with `extend_scope()` after the mutation opened and writing generations 1 → 2 → 3 in that mutation. That contradicts the frozen R2 §4 / R3 §2 procedure and the live helper: `next_generation_scope()` refuses the very mutation that holds the token (`review_generation_pending`). Repaired as open P2 contract issue **C-4**, with two contract directions (§14.2). Affected: §5, §6, §7.5, §8, §12, §14, §15, §18, §19.
- **P2-RECON-002** — the first revision closed the frozen R8/R9 persisted proof by moving the semantic proof before the commit and keeping the combined commit + push. A working-tree proof does not show that the committed and pushed Git objects carry the reviewed semantics, and the Consumption ordering against the registration commit was not examined. Repaired as open P2 contract issue **C-3**, with two contract directions, and an exposed Consumption / publication ordering problem (§9.3, §10.3, §11.3, §14.2). Affected: §8, §9, §10, §11, §12, §14, §15, §19.

One focused probe was added for P2-RECON-001 (probe 8, §18). P2-RECON-002 was repaired from code and frozen text alone. §13.2 and §16 each gained one consistency note; the Roadmap and Phase-entry flows (§3, §4), the mutation owners, the lifecycle separation proof, R9, HUMAN-1 and the incidental findings are unchanged.

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
| repair revision | made against live main `f2df83e` (the first revision; code unchanged since `b78be1c`) in a fresh GitHub clone; this file only |

P1 as it stands at the baseline: Review Core implemented (`ef77aa3`), repaired (`d6723b6`), finally repaired (`fedd0f3`, `b78be1c`). Work-terminal gating is not activated and no activation record exists. `state.py`, `roadmap.py`, `start.py`, `create.py`, `phase_create.py`, `ops.py` do not import `workline.review`.

## 2. Live authority consulted

Authority, read in full:

- `registry.md`: `rules/git` (Operation Owner, Project context, Unsupported self-hosting, Workline implementation, Project execution lock, Mutation Controller, Multi-write mutation, Cleanup, Commit / push, Push destination), `rules/ai-decision`, `rules/human-confirmation`, `rules/information-tracing`, and the seven routed Skills including `skills/review`.
- `.claude/skills/roadmap/SKILL.md`, `phase-create/SKILL.md`, `create/SKILL.md`, `review/SKILL.md`, `project-router/SKILL.md`; `start/SKILL.md` for the handoff, outer continuation and terminal sections.

Implementation: `roadmap.py`, `phase_create.py`, `create.py`, `mutation.py`, `state.py`, `store.py`, `validate.py`, `gitops.py`, `oplock.py`, `yamlish.py`, `errors.py`, and `review/{__init__,paths,serialize,records,store,gate,projections,adapter,closure,validate}.py` in full; `ops.py` (shared helpers; the plan-exclusion resume skimmed), `start.py` (outcomes, `start`, `_start_locked`, plan exclusion), `gitcmd.py` (the primitives the Git stage uses), `cli.py` (subcommands), `implementation.py` (what implementation identity covers), `review/fsafe.py` (platform support).

Tests, for behaviour and for pins a P2 change must keep: `helpers.py`, `test_phase_entry_contract.py`, `test_phase_expansion_resume.py`, `test_declared_write_scope.py`, `test_project_start_recovery.py`, `test_decision_branch_binding.py`, `test_cancel_decision_resume.py`, `test_decided_content_binding.py`, `test_review_gate_generation.py`.

Non-authority documents, read and checked against the above, never used as the source of a live fact: Candidate 7 checkpoint (§2, §4, §8, §11, §15) and readiness note; P1 R1, R2, R3, R4, R5 §12, R8, R9, R10, R11, R12 §11-§14; the P1 contract repair after external review §6; the Learning and Phase Design notes §17-§25; BACKLOG (search only, BL-041 read for its residuals). Where they disagree with the live code or with each other, §14 names the seam.

Re-read for the repair: R2 §3-§4, R3 §2, §3, §7, §8, §10, R4 §7, R8 §5-§9, R9 §7-§10, Candidate 7 §4.4 and §11; and live `review/gate.py`, `review/adapter.py`, `gitops.py`, `gitcmd.py`, `mutation.py` (`Mutation.apply`, `_make_commit`, `_classify_commit`, `_recorded_publication`, `_publish`, `MutationController.open`, `require_execution_lock`), `state.py`, `store.py`.

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

**Measured (probes 2, 5).** One `roadmap`-owned mutation carried every Review record — Candidate snapshot, task input, three gate generations, Receipt, Consumption — as `create_file` effects, and then the unchanged live registration (`_create_roadmap` / `_expand_phase`) and Git finalization, under one mutation ID from the first reservation to `complete()`. No Review-owned mutation, no second lock and no new effect kind were needed. **Not a conforming design:** those probes fixed the generation numbers in advance, added the gate paths and the serialization token to the scope with `extend_scope()` after the mutation opened, and never let the P1 helper compute a generation — when asked, `next_generation_scope()` refused the planning mutation itself. They show what the Mutation Controller does with Review records, not a flow that satisfies R2/R3 (C-4).

**Measured (probe 8).** The alternative also runs on the live lock and mutation model: the Roadmap operation's planning mutation stays pending while each generation transition is its own `roadmap`-owned mutation, opened under the same `project_operation` lock with the initial scope exactly `[gate path, token]` returned by the unchanged `next_generation_scope()`. Whether that shape is the P2 contract is C-4's question.

Which items the owner holds, and where the contract is still open:

| item | held as | identity |
| --- | --- | --- |
| gate generation | a `create_file`; **which mutation records it, and how the R2/R3 same-run procedure is satisfied, is open (C-4)** | Run ID reserved under `review-run:<kind>:<target>` |
| CandidateSnapshot | `create_file`, committed before the reviewer launch (R3 §3); by the mutation that commits it (a mutation cannot commit a path another pending mutation wrote, §14.2 C-4) | content address (`candidate_hash`) |
| TaskInput | as the CandidateSnapshot | `review-task:<run>:<slot>` |
| Receipt | `create_file` in the same stage as the sealed generation (R3 §7) | `review-receipt:<run>:<generation>` |
| Consumption | `create_file` in the planning mutation; **its position against the registration commit is open (§9.3)** | `review-consumption:<receipt_id>` |
| planning mutation | the live `write_file` / `add_relation` stages | the live reservation keys |
| Git | a commit-only stage at the launch boundary; **the registration commit's proof and publication boundary is open (C-3)** | recorded commit IDs |

Every one of them is opened, recorded, applied and committed by the Roadmap operation inside its own `project_operation` lock. The Review package contributes record shapes, validation, read-back and the generation-scope helper; it takes no lock, opens no mutation, writes no lifecycle event and decides no progression.

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
| Review ID kinds and reservation keys | `ids.py`, `gate.py:40-78`, `Mutation.reserve_id` | as-is | reservations are per mutation: a Run reserved by one mutation cannot be reached by another; a Run ID reserved inside the planning mutation is unknown when that mutation opens, so its token cannot be in that mutation's initial scope (C-4) |
| Same-Run serialization | `gate.py:102-157` | **not as-is for one long-lived planning mutation (C-4)**; as-is when every generation transition is its own mutation (C-4 Direction A) | `pending_generation_mutations()` finds any pending mutation whose scope holds the Run's token, the caller's own included, and `next_generation_scope()` then refuses (`review_generation_pending`). Measured: probe 2's planning mutation, holding the token, was refused by the helper; probe 8's separate generation mutations were given generations 1, 2, 3 with the initial scope R2/R3 require |
| Persistence preflight | `gate.require_committable` (`:162`), `gate.require_persisted` (`:196`) | as-is | Measured |
| Settlement check | `gate.validate_settlement` (`:239-312`) | as-is | Measured |
| `create_file` effect (immutable, no-follow, exclusive) | `mutation.py:231-259`, `:1775-1788`, `:2061-2140`, `fsafe.py` | as-is on Windows | POSIX: refused at record time, `review_create_unsupported` (`fsafe.py:130`, `:523-537`) |
| Projection kinds, `normative()` | `projections.py` | as-is container, planning binding for content | registration effects are `AuthorizedTransitionProjection`; Receipt and Consumption are `OperationMetadataProjection` |
| `PersistedProjectionAdapter`, `ReservedIds`, `prove_round_trip`, `prove_expected_scope` | `adapter.py` | planning binding | two adapters: Roadmap and Phase entry. `load_persisted` rereads "through the canonical loader", and the live canonical loader reads the working tree only; loading from a commit is not provided (C-3) |
| Review Context | only `review_context_hash` fields | planning binding | P1 has no builder |
| Effective Policy | only `effective_policy_hash` fields | planning binding | no Policy subsystem exists (R10) |
| Evidence foundation (`EvidenceDeclaration`, `ClassCoverage`, `MechanismProof`) | `closure.py:54-327` | not in P2 for completeness and reuse; `evidence_digest` content is a planning binding | unknown completeness is fresh-use only, and P2 reuses nothing across Candidates |
| ReviewValidity foundation (`ReviewValidityClosure`, `may_reuse`) | `closure.py:330-559` | not in P2 | HEAD-advancement reuse is P3 |
| `WorkTerminalActivation` | `records.py:877-931` | not in P2 | P3 |
| `validate_review` inside `validate_project` | `review/validate.py`, `validate.py:302-332` | as-is | Measured: gated runs validate clean, tampering is reported |
| Mutation Controller rules (branch binding, own bytes, commit ID, exact publication, projection before replay) | `mutation.py` | as-is | Measured over every interruption window of §12. Their scope is one mutation: nothing in them binds one mutation's commit to another's decisions (C-4 Direction A), and the combined Git stage leaves no point between a commit and its push (C-3) |

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

This check decides which Candidates may be reviewed at all. It is a prediction of the working tree, not the persisted proof R8/R9 require after the registration commit (C-3).

### 7.5 What the freeze point does not settle

The freeze point is the same whichever way C-3 and C-4 are resolved. What it leaves open: which mutation reserves the Review Run, task and Receipt IDs (the Run ID has to exist before generation 1; under C-4 Direction A the planning mutation can reserve it and each generation mutation reserves the Receipt key of its own generation, as probe 8 did), and which mutation writes and commits the Candidate snapshot and task input before the reviewer is launched.

## 8. Review insertion points

### 8.1 The eight points on the live flow

| # | point | RoadmapPlan | PhaseEntryDesign | durable as |
| --- | --- | --- | --- | --- |
| 1 | Candidate freeze | between `roadmap.py:496` and `:497` | in `_expand_phase` after `:990`, before `:997` | recomputable from the invocation and reserved IDs |
| 2 | Review task acceptance | snapshot, task input and generation 1 (`open`, accepted task descriptor) recorded; **the generation transition's mutation shape is open (C-4)** | same | recorded `create_file` effects, then the working tree |
| 3 | external reviewer launch boundary | after the point-2 records are committed and `gate.require_persisted` passes (R3 §3, §10) | same | local Git |
| 4 | settlement | `gate.validate_settlement`, then the next generation carrying the settled task; **how that generation is computed and written under R2/R3 is open (C-4)** | same | `create_file` |
| 5 | seal and Receipt | the sealed generation (`receipt_id`, `authorized_operation_stage`) and the Receipt in one stage (R3 §7); read back through `ReviewStore` before any use; **generation mutation shape open (C-4)** | same | `create_file` |
| 6 | Receipt consumption | re-validate the Receipt against the Candidate, Context and stage; record the Consumption; **its position against the registration commit is open (§9.3)** | same | `create_file` |
| 7 | actual planning mutation | the live stages `roadmap` (`:497`) and `phases` (`:500`), then a working-tree round-trip check | the live stages `works`, `integration`, `confirmation`, the live phase structure check (`:1020`), then a working-tree round-trip check | `write_file`, `add_relation` |
| 8 | planning commit, persisted proof and publication | today's live `finalize` stage commits and pushes in one pass (`:271`); **the R8/R9 post-commit proof and the publication boundary are open (C-3)**; then postcheck and `complete()` | same (`:1021`) | Git and the destination |

Authorization (points 4-5) and the planning mutation (7-8) are separate steps; the Consumption (6) is what binds them. A Receipt registers nothing by itself — a not-authorized run in probe 2 registered nothing and left an open, unconsumed chain.

**Measured shape (probe 2, uninterrupted).** Commits `initialize project` → `probe review accept` (local only) → `create roadmap R-01` (commit and push; destination equals local HEAD); 7 Review files; `validate_project` → no problem; Roadmap `active` and both Phases `unstarted`, exactly as in a legacy run. Probe 5 shows the same for Phase entry. What this shape does not show: an R2/R3-conforming generation procedure (it bypassed the P1 helper, C-4) or an R8/R9 persisted proof (its round trip read the working tree before the commit, C-3). **Measured (probe 8):** with one mutation per generation transition, three generation commits precede the registration commit, and the end state is again lifecycle-neutral with `validate_project` clean.

### 8.2 Sequence

```text
create_roadmap(plan)                                 enter_phase(phase_id, design)
  L1-L5 unchanged                                      E1-E6 unchanged
  L6 reserve roadmap / phase / relation IDs            E7 reserve every stage's IDs (register_works keys)
     decide_phases + refuse_invalid_phase_writes          validate_work_specs (all stages); R9 (review-v1)
  -- (1) Candidate freeze -----------------------------------------------------------
     review-v1: projected round-trip check (7.4) - refusal only, not the persisted proof
     reserve the Review Run ID (which mutation: C-4, 7.5); gate.require_committable
  -- (2)-(5) every generation transition follows R2/R3: pending same-run mutation first,
         then chain validation, then N+1 with [gate path, token] as INITIAL scope
         OPEN C-4:  Direction A - one owner-owned mutation per transition (probe 8)
                    Direction B - a repaired R2/R3 contract for one long-lived mutation
     (2) snapshot + task input + generation 1 (open, accepted)
     (3) committed; gate.require_persisted; reviewer(task input)
     (4) gate.validate_settlement; generation 2 (settled); adjudication -> obligations
     (5) sealed generation 3 + Receipt in one stage; ReviewStore read-back
  -- (6) re-validate; Consumption - position against the registration commit OPEN (9.3)
  -- (7) live registration stages; working-tree round-trip check (ProjectView.load)
  -- (8) OPEN C-3:  Direction A - registration commit (local) -> exact commit / tree /
                                   delta proof -> canonical reload from the committed
                                   result -> semantic equality -> only then publication
                    Direction B - combined finalize, only with a positive proof before
                                   publication of the exact Git objects to be committed
         postcheck; complete()
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
| Consumption bound to | the planning mutation of that `roadmap-create` operation (`operation_mutation_id`), target the reserved Roadmap ID, the authorized Candidate. **Frozen P1** R8 §8 additionally binds the registration commit SHA, and R8 §9 re-runs the round trip "after persistence ... before Consumption/authorization is considered successfully used"; whether the Consumption is recorded before the registration or after its commit is open (§9.3, C-2, C-3) |
| no invented Work terminal event | the live schema already enforces it: the three Work-binding fields are all null for a planning kind, and uniqueness is by Receipt (§9) |
| supersession / stale generation | a changed plan is a different request: never the same mutation (`require_same_request`), so always a new Candidate and a new Run. Within one planning operation only a changed base or Context can make a sealed Receipt stale (Q10). What can change while the mutation is pending is limited by scope: other Roadmap creations, Phase additions and Phase entries are blocked and lifecycle operations on other entities are not (Measured, §12); plan exclusion and START are blocked by their declared scopes (every ledger) |
| exact Candidate and task after a crash | runtime record intact: invocation + reserved IDs rebuild the Candidate; the task is `task-inputs/<task>.yaml` for the ID reserved under `review-task:<run>:<slot>` — in whichever mutation C-4 assigns it to; once that mutation has completed, the committed generation's accepted descriptor still names it — checked by `provenance_problems`. Runtime record lost: nothing links a new mutation to the old Run (Q11) |

### 8.4 PhaseEntryDesign contract questions

| question | answer from the live repository |
| --- | --- |
| exact semantic identity | the design identity (names verbatim, desired states stripped, declared order kept, `design_identity`) with `phase_id` and the reserved IDs; as reviewed semantics: the normal Works in declared order (name, desired state, Related type / to / condition), the integration Work, the optional confirmation Work (its target = the reserved integration ID), the design's `planned_next` / `requires_completion` and the generated `requires_completion` edges, affiliation (`phase_id`, `roadmap_id`), and the canonical first Work |
| Candidate freeze point | 7.2 |
| which operation stage is authorized | the Phase-entry registration of that mutation: `works`, `integration`, `confirmation` and their `finalize`. Not a Phase lifecycle transition (Phase entry writes none, 4.5) and not the START handoff |
| what the Receipt allows | "this exact design, with these reserved IDs, may be registered into this Phase by this Phase-entry request" |
| what the Consumption binds | the `phase-entry` mutation, target `phase_id`, the authorized Candidate |
| keeping Review out of Phase lifecycle truth | §13; the canonical first Work is computed from `ProjectView`, and neither the handoff nor START reads a Review record |
| design changes | a changed design is a different request: `_require_resumable` refuses it and leaves the record untouched; once the expansion finished a new design meets `phase_already_expanded`; once a not-authorized run completed, a new design is a new mutation and a new Run. A sealed Receipt can go stale within one planning operation only through Context or base changes (Q10) |
| retry / recovery / replay | §12; Measured for Phase entry in probe 5 (with the same non-conforming generation handling as probe 2) |
| order against the canonical planning mutation | the Receipt is re-validated before the Consumption is recorded; the live registration stays unchanged; a working-tree round-trip check follows the last registration stage and the live phase structure check. **Frozen P1** R9 §7-§8 require, after the local registration commit, a fresh canonical reload, the semantic comparison and an exact physical commit-delta proof, and R9 §9 binds the registration commit SHA into the Consumption: the proof and publication boundary is open (C-3), and so is the Consumption's position against the registration commit (§9.3) |
| `entry` under review-v1 | the P1 contract repair (§6, externally adjudicated) freezes that a reviewed design must be canonically self-selecting: unique selection A with `entry = A` or no entry is valid; `entry = B` against A, or `entry = A` among equals, is not. Live `enter_phase` accepts both rejected rows (4.4), so the review-v1 path adds a refusal the legacy path does not have, and `skills/roadmap` has to state it (Q13) |

## 9. Receipt / Consumption integration points

### 9.1 Receipt values for a planning kind

| field | value |
| --- | --- |
| `review_run_id` | reserved under `review-run:<kind>:<target>`, in the planning mutation or wherever C-4 places it |
| `review_generation` | the sealing generation |
| `review_kind` | a planning kind string without `:` (Q8) |
| `target_identity` | reserved Roadmap ID, or `phase_id` |
| `operation_identity` | operation plus request- or design-identity digest |
| `authorized_candidate_hash`, `review_context_hash`, `effective_policy_hash`, `coverage_hash`, `adjudication_hash`, `obligation_digest`, `authorized_operation_stage` | copied from the sealing generation; `review/validate.py:49-63` checks every pair |

### 9.2 Consumption for a planning kind

**Live.** `consumption_id` reserved under `review-consumption:<receipt_id>` in the planning mutation; `receipt_id`, `review_run_id`, `review_generation`, `review_kind`, `target_identity`, `operation_identity`, `authorized_candidate_hash` repeated from the Receipt (`review/validate.py:67-75`); `operation_mutation_id` = the planning mutation; `terminal_event_id`, `terminal_event_type`, `authorized_result_commit_sha` all null — the reader refuses a partial Work binding (`records.py:607-613`). Uniqueness is the Receipt index; planning Consumptions are absent from the terminal-event index by construction (`review/store.py:466-484`). A Consumption of a superseded Receipt is a validation problem (`review/validate.py:348-355`).

What the live schema cannot hold, although **Frozen P1** R8 §8 and R9 §9 list it: the registration commit SHA, the created IDs, a semantic projection digest, the adapter or loader identity. The unknown-field rule refuses any extra field (`records.py:143-161`). Seam C-2 in §14.

### 9.3 Placement: what is settled and what is open

Settled by live code and frozen text:

1. The sealed generation and the Receipt are recorded in one stage and read back through `ReviewStore` before any use (R3 §7).
2. Before a Consumption is recorded: the Receipt still binds the Candidate recomputed now, the Context computed now, and the registration about to be applied; the Receipt is not superseded; no Consumption exists for it (Q10).
3. `Authorization != Consumption`: a Receipt can stand unconsumed (a crash before point 6; runtime loss, Q11), and a Consumption exists only in the planning mutation that registers.

**Open P2 contract issue — the Consumption / registration commit / publication ordering.** Three things pull in different directions:

- **Frozen P1.** R8 §8 and R9 §9 bind the registration commit SHA, with the created IDs, the persisted semantic projection digest and the adapter / loader identity, into the planning Consumption. R8 §9: "after persistence, the same semantic round-trip is run again before Consumption/authorization is considered successfully used". R9 §10: "After replay/finalization, semantic round-trip and Roadmap-owned self-selection validation run again." R4 §7: planning uniqueness is "Receipt-based plus kind-specific semantic persisted-result binding". Read together, the Consumption follows a persisted registration commit and its proof.
- **Live.** A record cannot name the commit that stores it, so a Consumption that names the registration commit has to be committed after it, in a later commit. Consumption v1 has no place for that binding: `authorized_result_commit_sha` exists only together with a Work terminal event (`records.py:600-635`), and extra fields are refused (C-2). A later commit that carries only the Consumption is not itself covered by any Receipt; Candidate 7 §10.1 defines a metadata-only cutoff of that kind (K2) for Class A Work results only. `review-consumption:<receipt_id>` is reserved per mutation.
- **The first revision's proposal and probes 2 / 5** recorded the Consumption before the registration and committed both in one combined commit and push. That cannot bind the registration commit SHA, and it records the Consumption before any persisted proof.

What each ordering leaves the contract freeze to define:

| ordering | what the contract must still define |
| --- | --- |
| Consumption before the registration, in the registration commit | what "authorization considered successfully used" (R8 §9) means for a Consumption recorded before the persisted proof; how the registration commit is bound without being named in the record (C-2); what a recorded Consumption means when the registration is then refused on resume (`postcheck_failed`) and the mutation stays pending |
| Consumption after the registration commit | where the commit binding lives (C-2); the second commit and its publication (it pairs with C-3 Direction A, §14.2); the window in which the registration is committed — and, depending on C-3, published — while its Receipt is still unconsumed; what, if anything, covers the Consumption commit itself (a recursion cutoff) |

**Measured (probes 2, 5):** with the first ordering every window between the Consumption, the registration stages and the combined commit resumes (§12). That is mechanics; it does not settle the ordering.

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
- **Canonical semantic projection equality**: `normalize_candidate(reviewed semantics with reserved IDs)` equals `normalize_persisted(the created entities and records read through the canonical loader — Entity.name, Entity.section, relation and Related records — selected by reserved ID and ordered by the Candidate's declared order)`. It is needed at three points, and each proves something different:
  1. **at the freeze point, on the projection** — a Candidate that does not equal its own projected reading is refused before any Review record exists (review-v1 path only). Proves the Candidate can be represented at all.
  2. **after the last registration stage is applied, on `ProjectView.load`, before any Git stage for it is recorded** — a mismatch stops before the commit. Proves the working tree reads as the reviewed semantics.
  3. **the persisted proof Frozen P1 requires** — R8 §6: "After the local registration commit, load a fresh `ProjectView` and reconstruct only the result owned by this reviewed Roadmap creation using the exact created IDs ... The adapter compares normalized semantic meaning, while the separate exact commit/tree proof compares physical bytes/modes/path scope"; R8 §7 makes "exact commit-delta projection proof passes" and R9 §8 "exact physical commit-delta proof passes" a PASS condition; R9 §7 repeats the post-commit reload for Phase entry; Candidate 7 §11 orders it "local commit → exact artifact / transition / metadata / scope proof → canonical loader / ProjectView re-read". The fresh reload is tied to what Git stored only through the exact commit / tree proof. **Open (C-3).** Live code provides no part of that exact-content proof: `gitcmd` has no helper that reads a committed, staged or to-be-staged blob or its mode — `commit_changes`, `commit_touches` and `head_paths` return path names only (`gitcmd.py:93-104`, `:374-387`); `ProjectStore` / `ProjectView` read only the working tree (`store.py:421-427`, `state.py:139-147`); the own-bytes checks compare the working-tree bytes with the recorded `wrote` digest before `git add` (`mutation.py:1232-1299`), not the blob Git stores; and the combined stage makes the commit and the push in one `Mutation.apply` pass with no point between them (`mutation.py:527-553`), so there is no "after the local registration commit" before publication.
- Alongside all three:
  - scope — the created entity, relation and Related sets equal the reserved sets exactly (`prove_expected_scope`), in the working-tree check and again in the persisted proof;
  - what live code already proves physically — every committed path held, *in the working tree*, exactly the bytes the mutation wrote there (`_require_own_bytes_committed`), and a pushed commit changes only its recorded paths (`_recorded_publication` through `commit_changes`, path names only);
  - for Phase entry — the canonical first Work computed from the canonical reader equals the reviewed entry, or the entry is absent and the canonical selection is unique (R9).

Checks 1 and 2 prevent authorizing A when the working tree would read B. They do not show that the committed and pushed Git objects read A: between the working tree and the object store sit Git's content transformations — attributes, clean filters, line-ending conversion, any other object-writing transformation. Nothing here says such a transformation occurs; the point is that no live check excludes one. Closing "A was reviewed and authorized, B was stored" at the level Frozen P1 R8/R9 require is C-3, and it is open.

## 11. Persistence / Git boundaries

### 11.1 P1 invariants on the gated path

| invariant | how the gated path keeps it |
| --- | --- |
| unknown != proof | `require_committable` and `require_persisted` stop when Git cannot answer; a round-trip mismatch stops; P2 reuses nothing across Candidates. Whether the committed objects carry the reviewed semantics is currently *not proven* — it is not taken as proven either (C-3) |
| foreign commit != operation-owned commit | live commit-ID identity and exact-commit publication unchanged; P2 adopts no commit. If someone else commits the accepted records first, `require_persisted` still holds (they are committed) and nothing is claimed as the mutation's own |
| Git-write compatibility != Review-validity compatibility | path non-overlap is never read as Review validity; a Context or base change means a new generation or a new Candidate (Q10) |
| Authorization != Consumption | separate records in separate stages; unconsumed Receipts are valid |
| Review metadata != lifecycle truth | §13 |
| no reset, rebase recovery, amend recovery, force push, branch-tip fallback | the probed flows added no Git primitive: commit-only `gitops.finalize(..., destination=None)` stages and the live combined stage. Neither C-3 direction may add one |

### 11.2 What must be persisted before the external reviewer is launched

**Live (R3 §3-§4, `gate.require_persisted`).** The CandidateSnapshot, the TaskInput and the gate generation that accepted the task, committed in local Git with no working-tree or index difference. P1 does not require a push; remote-less Projects are valid. At that moment the runtime record (request, reserved IDs, recorded stages) is not clone-safe, and no planning registration may exist yet. **Measured:** the probes cross this boundary with a commit-only stage (probe 2 inside the planning mutation; probe 8 inside each generation mutation).

### 11.3 Git stage shapes

**Measured.** Commit-only Git stages followed by the live combined `finalize` stage (commit, then push of exactly that commit) pass `_recorded_publication`, the branch-binding rules and the own-bytes rules; the destination ends equal to local HEAD. The R5 §12.2 split publication is not used (seam C-1). `rules/git` allows several commits and pushes per operation.

**Live — what these shapes do not provide.** The facts that bound C-3:

- In the combined stage the commit and its push are applied in successive iterations of one `Mutation.apply` loop, with nothing in between (`mutation.py:527-553`): no proof can sit between the registration commit and its publication.
- A push is publishable only as the second and last effect of its own stage, right after that stage's single commit — adjacent in the record and by `seq` (`_recorded_publication`, `mutation.py:1461-1471`). A push-only stage after a proof is refused before anything is pushed.
- A commit with nothing left to commit is classified applied without a commit ID (`_classify_commit`, `mutation.py:2009-2011`; `_make_commit` runs only for an unapplied commit), and a push whose commit carries no ID is refused (`mutation.py:1472-1474`).

So with live shapes a proof between the registration commit and its publication exists only when the registration commit is made in a commit-only stage and reaches the destination later, as history of a subsequent stage's own new commit and push — which has to carry content of its own. Otherwise a planning publication shape the live rules do not have is needed. Either is C-3's question.

### 11.4 Publication side effects of a local-only accept commit

**Live.** While the accept commit is local and the lock is released (an asynchronous reviewer wait), any other operation allowed to run (a Phase hold, Measured allowed) publishes it as part of its own base history. Commits someone else makes before the final Git stage is recorded are published by the final push as base history; only commits after the recorded commit are excluded (`rules/git` Push destination).

### 11.5 Pre-existing dirty ledgers

**Live.** Roadmap creation and Phase entry have no `ensure_separable_before_effects` (it is called only by START, lifecycle decisions and plan exclusion: `roadmap.py:1053`, `:1251`, `start.py:509`, `:3298`); BL-041 lists them as residual (4). The Git stage refuses on the snapshot recorded at `_open`, and Roadmap owners never narrow that snapshot (`narrow_preexisting_dirty` is START-only, `start.py:514`). **Measured (probe 7):** with a person's line already in `roadmap.yaml` and a plan with a Phase relation, the run applied every registration effect — the ledger re-render dropped the person's line — then stopped with `dirty_overlap`; after the person discarded their change the retry stopped with `reconcile_required`. A gated run would reach the same stop after the reviewer ran (Q14).

### 11.6 Platform

**Live.** On POSIX the immutable create is refused before anything is written (`review_create_unsupported`, checked in `validate_effect` and at the create boundary), so a gated planning run stops before any Review effect is recorded and its mutation is abandoned. Review-gated planning is available only where `fsafe.immutable_create_supported()` is true, i.e. Windows at this baseline (HUMAN-1).

## 12. Recovery matrix

Terms: **resume** — the same pending mutation continues from its record; **replay** — recorded effects are classified again and only unapplied ones are applied; **retry** — an external action is repeated under the same identity (the same review task ID, the same push); **reconcile required** — STOP with the record untouched; **fresh Candidate required** — a new mutation and a new Review Run.

Baseline conditions for the table: the runtime record is intact, HEAD is on the decided branch, nobody changed a written path. Measured windows are from probe 2 (Roadmap, 13 windows) and probe 5 (Phase entry, 4 windows); in every measured window the second run resumed the same mutation and ended in the same state as an uninterrupted run.

**Scope of these measurements.** Probes 2 and 5 wrote every generation inside the planning mutation with generation numbers fixed in advance and the token added by `extend_scope()` after the mutation opened — not the R2/R3 procedure (C-4) — and ended in today's combined commit and push with a working-tree-only round trip (C-3). The rows therefore show how the Mutation Controller replays recorded Review and registration effects. They do not show that a conforming P2 flow recovers this way: rows 2-5 and 7-8 depend on C-4, rows 9-13 on C-3 and §9.3.

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

**Measured (probe 8) — generation transitions as separate owner mutations (C-4 Direction A).** Each window left two mutations pending, the planning mutation and one generation mutation; the next run resumed the planning mutation (the two scopes do not overlap), found exactly the interrupted generation mutation through `pending_generation_mutations()`, resumed it by its recorded invocation and finished it — apply, commit, `require_persisted`, `complete()` — before `next_generation_scope()` computed the next generation, as R3 §2 orders. Every run ended with nothing pending, `validate_project` clean, and the same lifecycle as a legacy run.

| window | pending after the interruption | next run |
| --- | --- | --- |
| generation 1 recorded, not applied | planning + generation 1 | resume generation 1 → generations 2, 3 → registration |
| generation 2 committed, not completed | planning + generation 2 | resume generation 2 → generation 3 → registration |
| generation 3 (with Receipt) recorded, not applied | planning + generation 3 | resume generation 3 → registration |

Windows the open issues add, which the contract freeze has to classify (not measured):

| issue | windows |
| --- | --- |
| C-4 Direction A | a generation mutation completed (its runtime record dropped) while the planning mutation is still pending; the planning mutation abandoned while its Run already holds committed generations — if it records no effect before the Consumption (as in probe 8), `abandon_on_stop` (`mutation.py:798-805`) abandons it on any STOP during the Review, and a retry reserves a new Run; a branch switch between a generation mutation's commit and the planning decisions (per-mutation branch rules do not span two mutations) |
| C-4 Direction B | whatever states the repaired R2/R3 contract introduces for one mutation that holds several generations |
| C-3 Direction A | registration commit made, proof not yet run; proof failed after the local commit (what happens to the unpublished commit, without reset or amend); proof passed, not yet published; a publishing commit made, not pushed |
| C-3 Direction B | the pre-publication proof passed but the committed objects then differ (hooks, filters, concurrent writers between proof and commit) |
| §9.3 ordering | registration committed while its Receipt is unconsumed; Consumption recorded while the registration is refused on resume |

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
| Review Context changed between seal and consumption | Open: supersede and re-review within the planning operation (the new generations written as C-4 settles), or STOP | Q10 |
| Review not authorized | Review records committed (and pushed), mutation completed, nothing registered; a repaired plan is a fresh Candidate | probe 2 |
| POSIX | STOP `review_create_unsupported` before any Review effect; the mutation is abandoned | `fsafe` |
| a pre-existing dirty ledger the registration commits | `dirty_overlap` at the final Git stage after the registration was applied, then stuck | probe 7, Q14 |

Operations a pending gated planning mutation blocks (**Measured**, probe 2, mutation left pending after the reviewer returned): `create_roadmap` (any plan), `add_phases`, `enter_phase` → `reconcile_required` (scope overlap on `roadmap.yaml`); Phase hold and resume on another Roadmap's Phase, direct CREATE → proceed. START declares every ledger (`start.py:109-113`) and is therefore blocked as well. With a synchronous reviewer the whole Project answers `project_operation_busy` for the reviewer's duration instead.

Nothing in this matrix is the P3 Work-terminal recovery contract: no Work terminal event, no Work result commit K1, no Work-result proof checkpoint. The commit → proof → publication windows that C-3 Direction A would add belong to a P2 planning publication boundary, not to P3.

## 13. Lifecycle separation proof

### 13.1 Static

- `state.py` imports only `.errors` and `.store` (`state.py:16-17`). `ProjectView.load` reads the entity directories, the two relation files and the event log (`:139-147`); `list_entities` globs `.workline/<roadmaps|phases|works>/*.md` (`store.py:440-445`), which never reaches `.workline/review/*.yaml`.
- `ProjectView.with_effects` handles `write_file` on entity paths, `add_relation`, `remove_relation` and `append_event`, and ignores `create_file` (`state.py:170-185`), so a projection that includes Review effects projects no lifecycle change.
- Lifecycle is derived from events only (`derive_work_state`, `derive_phase_lifecycle`, `derive_roadmap_lifecycle`, `state.py:65-117`); neither Roadmap creation nor Phase entry writes an event.
- `normative(OPERATION_METADATA)` is false (`projections.py:50-62`).
- `validate_structure`, which operations use as precheck and postcheck, does not read Review; `validate_project` reports Review problems in a separate pass (`validate.py:302-332`).
- `roadmap.py`, `phase_create.py`, `create.py`, `ops.py`, `start.py` do not import `workline.review`; `mutation.py` imports only `fsafe` and `paths` to guard `create_file`.

### 13.2 Measured

- Gated and legacy creation leave identical lifecycle: Roadmap `active`, Phases `unstarted`; after a gated Phase entry the Phase is `unstarted` with four `unstarted` Works (probes 2, 5). The same holds when every generation transition is its own mutation (probe 8).
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

Every Q item has a default that live code or frozen contracts already point to. The C items are seams with frozen P1 text; C-3 and C-4 have no default here — they are open P2 contract issues whose directions are listed, not chosen. None needs a human except where §16 says so.

### 14.1 Open questions

**Q1 Reviewer invocation.** P1 has no launch mechanism. Live precedents: START's executor, a callback run inside the lock (`start.py:187-201`), and START's `question_wait`, which returns with the mutation pending and its scope held. Measured consequences are in §12. Default: a synchronous reviewer callback, mirroring the executor; an asynchronous wait only if a human reviewer is ever required.

**Q2 Not-authorized outcome.** A mutation with a recorded effect cannot be abandoned (`mutation.py:620-627`), and a pending one blocks every Roadmap-structure operation. So a mutation that holds Review records has to finalize them (commit, and push when a destination exists) and `complete()` without registering, and the operation returns a distinct status. Measured in probe 2 (records held by the planning mutation); under C-4 Direction A the generation mutations have already committed and completed their own records, and what closes the planning mutation follows C-4. Either way a repaired plan then runs as a new request.

**Q3 Candidate and `candidate_hash`.** Content: semantics version, operation, the normalized semantics as the canonical reader reads them, the reserved IDs, the declared base. The snapshot bytes must be a pure function of that content (one snapshot per hash, §6).

**Q4 Review Context.** What can change a plan's meaning or validity without changing the plan: the declared base (RoadmapPlan: existing Phases named by relations and their states; Phase entry: `phase_id`, Phase and Roadmap lifecycle, predecessor states, the Phase's Works); a loader / renderer identity — live implementation identity is its origin only, not its content (`implementation.py`, `rules/git` Workline implementation), so a content digest of the modules that render and read would be new; authority digests (`registry.md`, `skills/roadmap`, `phase-create`, `create`, `review`); projection semantics version; review kind. Nothing runtime-only or unstable.

**Q5 Effective Policy.** No Policy subsystem exists (R10). A versioned planning policy declared in canonical authority (`skills/review`) and hashed: reviewer slots and roles (the four roles of the Phase Design notes are non-authority), the authorization rule (no unresolved HIGH / MID), LOW handling, failure and timeout disposition, adjudication rule version.

**Q6 Evidence.** What `evidence_digest` covers for planning: mechanical results (projected structure validation, round-trip check, R9 check) and reviewer report digests. R11 completeness is not needed, because P2 reuses nothing.

**Q7 Adjudication and obligations.** P1 stores only digests (`adjudication_digest`, `obligation_digest`, `raw_report_set_digest`); raw reports are runtime-only material (R1 §3). P2 defines the canonical input of those digests and the zero-obligation seal; full history is P5.

**Q8 Identity strings.** `review_kind` values (no `:`, `gate._require_key_part`), `target_identity` (reserved Roadmap ID / `phase_id`), `operation_identity` (operation plus request digest), `authorized_operation_stage` (one name per registration unit).

**Q9 Stage layout.** Stage names must not collide with the live ones (`roadmap`, `phases`, `works`, `integration`, `confirmation`, `finalize`); seal and Receipt in one stage (R3 §7); which Review records are committed at the launch boundary. The rest of the layout follows the open issues: which mutation records each generation (C-4), where the Consumption sits against the registration commit (§9.3), and the registration commit's proof and publication stages (C-3).

**Q10 Staleness at consumption.** Planning-native and exact: recompute the Candidate and Context at point 6; any difference either supersedes (new open generation plus supersession record, fresh tasks) within the planning operation — the generation written the way C-4 settles — or stops. No P3 reuse fast path.

**Q11 Runtime loss.** The committed records survive, the owner's record does not, and reservations are per mutation. Default: a fresh Candidate; the old Run stays a valid orphan. The alternative, an exact canonical rule for adopting an in-flight Run, is new recovery surface. Seam C-6.

**Q12 Round-trip refusal set.** Defined mechanically as "the projected reading differs from the Candidate" (7.4), not as a list of forbidden characters. The Candidate must not normalize a lone CR away, or the §17 classifier defect strands the mutation after the Review.

**Q13 R9 self-selection.** Place it in `roadmap.py`'s review-v1 path and in `skills/roadmap`; the legacy path, and `tests/helpers.simple_entry` which depends on it, stay as they are.

**Q14 Early dirty-overlap check.** On the review-v1 path, call `ensure_separable_before_effects` for every path the registration will commit before the first Review effect. A new refusal on the new path only.

**Q15 Invocation marker.** A review-v1 run needs a marker in its invocation (the probes used an extra key). Measured consequence: a legacy retry of the same plan while a gated one is pending meets `reconcile_required` through scope, because slot lookup finds the gated record and the exact invocation does not match.

**Q16 Pins to keep.** Public method sets of `Mutation` and `MutationController` (`test_project_start_recovery.py:978-991`: add module-level functions, not methods); `EFFECT_KINDS` (`test_decision_branch_binding.py:676`, `test_cancel_decision_resume.py:367`); `rm.register_works` called as `(mutation, stage, specs, relations)` with stage names `works` / `integration` / `confirmation` (`test_phase_entry_contract.py`); the `rm.validate_structure` call order in Phase entry (1 = precheck, 2 = phase structure check, `test_phase_entry_contract.py:529-555`), so a new check belongs in another module; `OPERATION_LEDGERS` (`test_declared_write_scope.py:162-191`), so Review paths are added dynamically like entity IDs; `ROADMAP_REQUEST_VERSION`, `DESIGN_IDENTITY_VERSION` and their shapes.

**Q17 Authority text.** P2 changes canonical Skills (`skills/roadmap`: the gated flows, R9, the not-authorized outcome; `skills/review`: planning kinds, policy, adjudication). `rules/human-confirmation` treats that as a Workline common-rule change, which the P2 contract approval covers.

**Q18 Ungated planning writers.** `add_phases`, Related maintenance, plan exclusion with replan, START derivations and direct CREATE remain ungated under P2 as scoped (3.7).

### 14.2 Seams with frozen P1 contract text

These are conflicts between frozen P1 contract text and the live code or the P2 scope. C-1, C-2, C-5 and C-6 have a suggested resolution inside Candidate 7. **C-3 and C-4 are open P2 contract issues**: the contract freeze must choose, and nothing here chooses. None of them needs Candidate 7's architecture to change.

**C-1 — R5 §12.3.1 publication discriminator.** Its "Review-v1 durable operation metadata" is any review operation identity, contract, Run or generation binding on a mutation; case B (metadata present, `publication_contract` absent) and case E (`current-combined` against such metadata) fail closed. A P2 planning mutation carries exactly such bindings. Live code does not implement the discriminator yet (`publication_contract` appears nowhere in `src/`), but P3 will. Suggested resolution: scope R5 §12.3 to Work-terminal review-v1 result publication. How planning publication is identified follows C-3: under C-3 Direction B planning publishes through the current combined stage and carries no `publication_contract`; under C-3 Direction A a planning publication boundary exists that the discriminator must tell apart from both the current combined shape and the Work-result split.

**C-2 — R8 §8 / R9 §9 Consumption bindings.** They list the registration commit SHA, created IDs, a semantic projection digest and an adapter identity. The live Consumption v1 holds none of them and forbids extra fields, and a record cannot hold the ID of the commit that stores it (the rule the Review Skill states for Receipts). Directions: (a) bind the created IDs and semantics through the Candidate (its hash is already in Receipt and Consumption), the adapter identity through the Context, and the registration commit through Git history (the commit that adds the Consumption file) — coherent only if the Consumption lives in the registration commit, an ordering §9.3 shows R8 §9 does not support as written; (b) a Consumption schema with a planning persisted-result binding — a P1 record change. Coupled to §9.3 and C-3; open with them.

**C-3 — OPEN P2 CONTRACT ISSUE: the persisted proof and the publication boundary (P2-RECON-002).**

*Frozen P1.* R8 §5-§7, R9 §7-§8 and Candidate 7 §4.4 / §11 (quoted in §10.3): after the local registration commit, an exact commit / tree / delta proof of physical bytes, modes and path scope, and a fresh `ProjectView` reload whose normalized persisted semantics equal the reviewed semantics — both PASS conditions. R8 §9 / R9 §10 run the round trip again after persistence, before the authorization counts as used.

*Live.* No helper reads a committed or staged blob or mode; the canonical loader reads only the working tree; the own-bytes checks prove working-tree bytes before `git add`; the combined stage has no point between commit and push; a push must be its commit's stage partner, and a commit with nothing to commit has no ID (§11.3).

*Why the first revision's resolution fails.* It proved semantics on the working tree before the commit and kept the combined stage. That shows reviewed semantics = working-tree reading, not reviewed semantics = what the committed and pushed objects represent, and it does not perform the post-commit exact proof the frozen text makes a PASS condition. Git content transformations (attributes, clean filters, line-ending conversion, other object-writing transformations) are not assumed to occur; nothing excludes them.

*Directions the freeze must choose between (not chosen here):*

- **Direction A — planning-specific local commit → proof → publication boundary.** Registration (and, per §9.3, possibly Consumption) effects → a local planning commit → exact committed tree / delta proof → reload and reconstruct the canonical persisted semantics from the exact committed result → semantic equality → only then publication. This is a **P2 planning publication boundary**, not P3 Work-terminal activation. With live shapes it is expressible only if the registration commit is made in a commit-only stage and reaches the destination as history of a later stage's own new commit and push, which must carry content of its own (§11.3); otherwise it needs a planning publication shape the live rules lack (and C-1 must recognize). It also needs a proof mechanism that reads the committed result, which live code does not have, and a rule for a proof that fails after the local commit without reset, rebase or amend recovery (§12).
- **Direction B — keep the combined finalization, with a positive pre-publication proof.** Allowed only if P2 can prove, before anything is published, the exact Git objects / tree that the commit will record, and that their canonically loaded semantics equal the reviewed Candidate. `ProjectView.with_effects()` and an ordinary working-tree reread are insufficient. Live helpers provide none of this (§10.3 check 3): the contract has to define how the exact objects are determined, how their content is loaded canonically, and how the proof stays exact up to the commit the combined stage then makes (hooks, filters and concurrent writers in between).

The Consumption / registration-commit ordering (§9.3) is part of this decision.

**C-4 — OPEN P2 CONTRACT ISSUE: generation mutations and same-run serialization (P2-RECON-001).**

*Frozen P1.* R3 §2: "hold Project lock -> inspect pending generation mutations for review_run_id -> if one exists: resume/reconcile it before calculating any new generation -> if conflicting/multiple: reconcile_required -> otherwise validate full immutable chain -> calculate exact N+1 path -> open mutation with BOTH exact generation path and stable same-run token in initial WriteScope.files -> only then reserve IDs / record effects"; R3 §8: "The same-run serialization rule applies to every settlement, seal and invalidation generation." R2 §4: "For every generation mutation, the initial `WriteScope.files` contains both ...", and "Thus `extend_scope()` is not the safety mechanism".

*Live.* `pending_generation_mutations(store, run)` returns every pending mutation whose write scope holds the Run's token, with no notion of the caller's own mutation (`gate.py:102-117`); `next_generation_scope` raises `review_generation_conflict` for several and `review_generation_pending` for one, and computes N+1 only when there are none (`gate.py:120-157`). A Run ID reserved inside the planning mutation is not known when that mutation opens, so its token cannot be in that mutation's initial scope.

*Why the first revision's resolution fails.* It added the gate paths and the token with `extend_scope()` after the planning mutation opened and wrote generations 1 → 2 → 3 in that mutation. Measured (probe 2): the unchanged helper then refused the planning mutation itself (`review_generation_pending`), and the probe could only proceed because it fixed the generation numbers in advance and never used the helper. The P1 procedure is therefore not reusable as-is for a single long-lived planning mutation.

*Directions the freeze must choose between (not chosen here):*

- **Direction A — each generation transition is its own operation-owner mutation, R2/R3 unchanged.** Traced and measured (probe 8): inside the Roadmap operation's `project_operation` lock, the planning mutation stays pending while each transition opens a separate `roadmap`-owned mutation with the invocation `{operation: review-generation, review_run_id, generation}` and the initial scope `[gate path, token]` from the unchanged `next_generation_scope()`. `MutationController.open` only needs the lock this process already holds (`mutation.py:1626-1652`) and refuses only overlapping or scope-less pending mutations (`:1655-1691`); the two scopes are disjoint, so both mutations can be pending together and the planning mutation's retry is not blocked. An interrupted generation mutation is found through the token on the next run and finished before the next generation is computed (§12). The Roadmap operation stays the only top-level owner: every generation mutation is opened, applied, committed and completed by the Roadmap operation's own code, under its lock and owner name; Review opens nothing, and no generation mutation is ever a top-level operation. It also stays the semantic owner: the request lives in the planning mutation's invocation, the generation mutations carry only the Review records that authorize it, and only the planning mutation records the Consumption and the registration. What the contract still has to define:
  - `rules/git` describes one operation with one stable mutation (Multi-write mutation; the entry rule "一意対応する1件があれば ... resume"). An operation owning a planning mutation plus sequential generation mutations, and its resume order (pending generation mutation first, as R3 §2 orders), is not described there.
  - Live branch, own-bytes and commit-identity rules act per mutation; nothing binds a completed generation mutation's commit to the planning mutation's later decisions (a branch switch in between is not caught by them).
  - Every generation mutation has to record its pre-existing dirty snapshot at open. Probe 8's first run skipped that, took its own just-written generation file for a person's change at its Git stage and stopped with `dirty_overlap`. For the same reason a mutation cannot commit a path another pending mutation wrote, so the snapshot and task input must be written by the mutation that commits them.
  - A planning mutation that records no effect before the Consumption is abandoned by `abandon_on_stop` on any STOP during the Review, orphaning the Run (§12).
  - One Git commit per generation transition, before the registration commit.
- **Direction B — P2 formally repairs R2/R3 so one long-lived planning mutation can hold several generations.** The repaired contract needs a mechanically safe way to tell apart (1) the current legitimate owner mutation, (2) a stale or crashed predecessor, and (3) a conflicting second owner — and to stay crash-safe for a generation file created before its `applied` flag was saved. "Ignore the current mutation" and "`extend_scope()` after open" are not sufficient. The first removes, for the one mutation that writes the Run, exactly the guard R2/R3 rely on after a generation file appeared before its `applied` flag was saved — unless the next generation number is tied to that mutation's own record rather than to whatever the chain holds — and it says nothing about a second pending mutation holding the same token, stale predecessor or conflicting owner. The second is what R2 §4 rejects as the safety mechanism. This direction changes frozen P1 contract text and the live helper.

**C-5 — R3 §9 "the owning mutation binds review_run_id, generation, candidate_hash, … receipt_id".** The invocation is the resume key and must be computable before the mutation opens, so values decided later cannot live there. Suggested resolution: a static review-v1 marker in the invocation (Q15); Run, task, Receipt and Consumption IDs as reserved IDs — in which mutation each is reserved follows C-4; Candidate, Context and Receipt bindings through the recorded `create_file` effects.

**C-6 — R3 §4 / R2 §5 same-task rerun after runtime loss.** It presupposes an owner that can re-find its Run; the live owner finds its state only through the runtime record. See Q11.

## 15. Architecture blockers

**None.**

- Ownership: the Roadmap operation owner can own every Review record as a subordinate effect — in its planning mutation (probes 2, 5) or in separate owner mutations under its own lock (probe 8); Review opens nothing and locks nothing.
- Lifecycle separation: PASS (§13).
- P1 foundation: records, store, validation, persistence preflight and `create_file` are reusable as landed. Two P1 mechanisms do not carry P2 as proposed in the first revision — the same-run serialization procedure inside one long-lived planning mutation (C-4), and a proof point between a registration commit and its publication (C-3). Both are P2 integration-contract problems inside Candidate 7: Candidate 7 §11 already orders planning persistence as a local commit, then an exact proof, then a canonical re-read, and R2/R3 already define how a generation mutation is opened.
- Semantic round trip: the live reader is lossy, but the loss is predictable before any write (7.4), so the gate can refuse what it cannot represent; the persisted proof itself is C-3.
- Recovery: every measured interruption window resumes through the ordinary Mutation Controller; the windows the open directions add are listed for the contract freeze (§12).

**Open P2 contract issues** (the contract freeze must resolve them; they are not architecture blockers):

- C-4 — generation mutation / same-run serialization ownership (P2-RECON-001);
- C-3 — persisted commit proof / publication ordering, with the Consumption ordering of §9.3 (P2-RECON-002).

If the freeze found that neither direction of one of them can be made to work within Candidate 7, that would be an architecture question to report, not to absorb; nothing found so far points that way.

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

The repair leaves this comparison unchanged. C-3 and C-4 have to be resolved for every option, and whichever directions the freeze picks — including ones that change P1 contract text — apply to A, B and C alike. "No P1 change" in row A means that choosing A adds none of its own.

No other HUMAN decision is raised: C-3 and C-4 are choices for the P2 contract freeze between directions that live code and frozen text already bound, and every Q item has a default.

## 17. Incidental live findings outside P2 scope

1. **Lone CR strands Roadmap creation and Phase entry** (probe 1b). Writer, Mutation Controller classifier and reader normalize line endings differently (§10.2); an accepted input leaves a pending mutation that no retry can finish, and it holds its write scope. Not recorded in BACKLOG (the only lone-CR entry concerns commit messages). Not fixed here.
2. **Pre-existing dirty ledger in Roadmap creation / Phase entry** (probe 7): effects applied and the person's line dropped by the ledger re-render before the Git-stage `dirty_overlap`; the retry then stops with `reconcile_required`. Known as BL-041 residual (4); the dropped line is worth noting beside it.
3. **`gate.py` diagnostic** prints `None` for pending generation mutations (§6).
4. **A completed Roadmap creation is not deduplicated**: the same plan again creates a second Roadmap (probe 6). Existing semantics.
5. **A resumed mutation's closed runtime record is kept** (§12). Existing rule.

## 18. Evidence

Every probe is a plain script (no pytest), run with `PYTHONPATH` pointing at the investigation tree's `src`; each asserts the imported `workline` is that tree's; each builds disposable Projects under `%TEMP%` through `tests/helpers.py` and drives only functions the baseline ships. Probes 1-7 ran against `b78be1c`, probe 8 against `f2df83e`, whose `src/`, `tests/`, Skills and registry are byte-identical to `b78be1c`. Kept outside the repository: `D:\AIproject\workline-evidence\cases\workline-core-p2-recon\evidence\`.

What the probes are evidence for. Probes 2 and 5 are evidence of Mutation Controller behaviour with Review records, of ID pre-reservation, of lifecycle neutrality and of the blocking table. They are not evidence of an R2/R3-conforming generation procedure — they bypassed the helper, which refused their planning mutation (C-4) — nor of the R8/R9 persisted proof, since their round trip read the working tree before a combined commit and push (C-3). Probe 8 was added for the repair and answers one question only: can distinct owner-owned generation mutations satisfy R2/R3 unchanged under the Roadmap operation's lock?

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
| 8 | `generation_mutation_probe.py` | C-4 Direction A: generation transitions as separate `roadmap`-owned mutations with the R2/R3 initial scope, the planning mutation pending under the same lock | uninterrupted and 3 interruption windows: initial scope exactly `[gate path, token]`, generations 1-3 from the unchanged helper, interrupted generation mutation resumed first, nothing pending at the end, `validate_project` clean, lifecycle as legacy. The first run (kept as `probe8_first_run_missing_snapshot.jsonl`) omitted the pre-existing dirty snapshot at open and stopped with `dirty_overlap` on the mutation's own generation file |

Outputs are the `probe*.jsonl` files beside the scripts.

## 19. Checkpoint

```text
Reviewed baseline:            b78be1ccd778ceb2ecd97b90e2f71744bd1b3bc5 (code); repaired on f2df83e
RoadmapPlan mutation owner:   roadmap.create_roadmap (owner "roadmap", operation roadmap-create)
PhaseEntryDesign owner:       roadmap.enter_phase (owner "roadmap", operation phase-entry)
Insertion:                    Candidate freeze before the first registration stage; Review
                              transitions and the Consumption inside the Roadmap operation, under
                              its lock; live registration stages unchanged
Semantic round trip:          canonical semantic projection equality (not text, not bytes alone);
                              refusal on the projection at freeze, working-tree check before commit;
                              the R8/R9 persisted proof after the commit is OPEN (C-3)
P1 same-run serialization:    NOT reusable as-is inside one long-lived planning mutation (C-4)
Open P2 contract issues:      C-4 generation mutation / same-run serialization ownership
                              C-3 persisted commit proof / publication ordering (+ Consumption, 9.3)
P2-RECON-001:                 REPAIRED IN RECONNAISSANCE (C-4 open for the freeze)
P2-RECON-002:                 REPAIRED IN RECONNAISSANCE (C-3 open for the freeze)
Lifecycle boundary:           PASS
Architecture blocker:         None
HUMAN:                        1 (HUMAN-1, applicability / activation of review-v1 planning) - unresolved
P3 accidentally activated:    No
Candidate 7:                  RETAIN
Architecture reopen:          No
P2 contract freeze:           NOT STARTED
Status:                       READY_FOR_P2_RECONNAISSANCE_REVIEW
```
