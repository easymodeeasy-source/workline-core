# Review System P2 — Planning Review Gates: Integration Contract

Status: `CONTRACT FROZEN / IMPLEMENTATION NOT STARTED / PENDING INDEPENDENT CONTRACT REVIEW`

Runtime authority is unchanged by this document: `registry.md`, the registry-routed canonical Skills, and the live implementation and tests. This is a non-normative contract checkpoint. It freezes how P2 connects RoadmapPlan Review and PhaseEntryDesign Review to the landed P1 Review Core and to the live Roadmap operation, so that the P2 implementation is left with no choice to make. It starts no implementation and edits no authority; §26 states the authority text the implementation changes under the approval of this contract.

```text
Candidate 7:            RETAIN
Architecture reopen:    No
Architecture blocker:   None
HUMAN:                  None   (HUMAN-1 resolved: A, per-invocation opt-in)
P2 scope:               1. RoadmapPlan Review
                        2. PhaseEntryDesign Review
                        3. semantic round-trip integration
C-1 .. C-6:             CLOSED BY P2 CONTRACT (§23)
P3:                     NOT STARTED, and nothing here activates it
```

How to read it. Each rule is marked:

- **Frozen** — a P2 contract rule: the P2 implementation does exactly this;
- **Live** — what the baseline code or authority does, with `file:line` at the baseline;
- **Measured** — what a throw-away probe observed on real Projects (§31);
- **Frozen P1** — wording of the frozen P1 contracts or Candidate 7: not runtime authority, but a constraint this contract satisfies (§24).

Where the accepted reconnaissance listed contract directions, this document names the one chosen and says why. Nothing in it is left to the implementation to decide.

## 1. Baseline and inputs

| item | value |
| --- | --- |
| repository | `easymodeeasy-source/workline-core` |
| branch | `main` |
| contract baseline = live main at start | `cdb152312006f6ac25533962d942ed77e2d98bd4` — local `main`, `origin/main` and GitHub `refs/heads/main` verified equal, working tree clean |
| accepted P2 reconnaissance checkpoint | `cdb152312006f6ac25533962d942ed77e2d98bd4` (`REVIEW_SYSTEM_P2_INTEGRATION_CONTRACT_RECONNAISSANCE.md`) |
| P1 accepted checkpoint | `b78be1ccd778ceb2ecd97b90e2f71744bd1b3bc5` |
| code at the baseline | `src/`, `tests/`, Skills and `registry.md` are byte-identical to `b78be1c`; the two commits since touch only the reconnaissance document |
| investigation tree | a fresh GitHub clone at `cdb1523`; the canonical worktree was only read |

Accepted inputs, not reopened here:

```text
Candidate 7:            RETAIN            Architecture reopen:   No
P1:                     ACCEPTED (b78be1c)
P2 reconnaissance:      ACCEPTED (cdb1523)
Review                  = subordinate authorization / quality gate
Review                  != lifecycle / progression controller
Roadmap operation       = the top-level semantic and mutation owner
state.py / ProjectView  never read Review metadata as lifecycle truth
P3                      NOT STARTED
```

**HUMAN-1 = A (per-invocation opt-in)** is a frozen input: a legacy invocation runs the live path unchanged; an explicitly opted-in invocation runs the P2 gate and registers nothing without valid authorization; there is no Project-wide planning activation record, no global mandatory Review, no activation inferred from Review records, and no cross-operation rule such as "Phase entry requires its Roadmap to have been reviewed". POSIX with the opt-in fails closed before planning registration; POSIX without it keeps planning.

## 2. Scope and non-goals

In scope: the review-v1 path of `roadmap.create_roadmap` (RoadmapPlan Review) and of `roadmap.enter_phase` (PhaseEntryDesign Review), the semantic round trip both require, and the P2 planning commit / proof / publication boundary those two paths need to satisfy Frozen P1 R8/R9.

Not implemented or activated by P2: START Review Gate; Work Formal Review runtime; Work completion Review; review-v1 `work_completed`; Work-terminal activation (`activation/work-terminal-v1.yaml` stays absent); Work-terminal Consumption totality; the P3 result-commit publication contract (`review-v1-split-v1`); P3 Class A / B / C; P3 Review-validity closure; P3 HEAD-advancement reuse; P3 stale-generation Work blocking; P3 Work commit / proof / push; P4+ learning, repair and policy systems. The planning publication contract of §18 is P2-native and activates none of them.

Ungated planning writers stay ungated (reconnaissance §3.7 / Q18): `add_phases`, Related maintenance, plan exclusion with replan, START derivations, direct CREATE.

## 3. Terms

| term | meaning |
| --- | --- |
| planning operation | one call of `create_roadmap` (lock operation `roadmap-create`) or `enter_phase` (lock operation `phase-entry`) made with `review=` (§5) |
| planning mutation | the mutation that operation resumes or begins at its entry: owner `"roadmap"`, invocation = the live invocation plus the two markers of §5.2 |
| generation mutation | a mutation the planning operation starts, under its own lock and owner, to write exactly one gate generation transition of its Review Run (§11) |
| Run | the Review Run the planning mutation reserved (§6) |
| Run records | the Run's candidate snapshot, task input, gate generations 1–3 and Receipt |
| registration stages | the live stages that register the plan: `roadmap`, `phases` (RoadmapPlan); `works`, `integration`, `confirmation` when the design declares one (PhaseEntryDesign) |
| registration paths | exactly the canonical paths the registration stages write: the new entity files and the ledgers they re-render (§14.1) |
| Kp | the registration commit: a commit-only stage of the planning mutation carrying exactly the registration paths |
| Km | the metadata commit: a commit-only stage of the planning mutation carrying exactly the planning Consumption |
| C-2(K) | the durable proof checkpoint for commit K (the term of Frozen P1 R5 §1.1) |
| planning-owned paths | registration paths + Run record paths + the planning Consumption path |
| freeze | the step of the planning operation that fixes the Candidate and every identity before the first Review record is written (§7, §14) |
| use check | the re-validation of the Receipt right before the first registration stage is recorded (§13, §17) |

## 4. Decision summary

| issue | frozen decision | section |
| --- | --- | --- |
| HUMAN-1 = A | keyword `review=PlanningReview(...)`; invocation markers `review_contract` / `publication_contract` | §5 |
| C-4 generation serialization | **Direction A**: every generation transition is its own `roadmap`-owned generation mutation, R2/R3 and the live helper unchanged | §11 |
| abandonment gap | the planning mutation is abandonable only before its first generation mutation starts; afterwards pending until a terminal outcome | §12 |
| C-3 persisted proof | **Direction A**: Kp commit-only → exact proof → canonical reload from the committed result → equality → Consumption → Km commit-only → exact proof → push-only publication of exact Km | §15, §18 |
| C-2 planning Consumption binding | `review-consumption` **version 2** (Planning Consumption) with a `persisted_result` binding; v1 unchanged | §16 |
| ordering | Receipt → use check → registration → Kp → C-2(Kp) → Consumption → Km → C-2(Km) → publication | §17 |
| C-1 publication discriminator | durable invocation markers select `review-v1-planning-publication-v1`; legacy is the unchanged current-combined rule | §18.5 |
| C-5 invocation binding | markers augment, never replace, the request identity; Run / task / Receipt / Consumption IDs are planning reservations; generation invocations bind run, generation, transition and every hash | §5.2, §11.2 |
| C-6 runtime-loss rerun | never: runtime loss requires a fresh Candidate and a new Run; the old Run is a legal orphan | §12, §23 |
| staleness before Consumption | terminal `stale` outcome; no re-review inside the operation | §13 |
| not authorized | terminal `not_authorized` outcome, nothing registered, planning mutation completed | §19 |
| reviewer | synchronous callback inside the lock; one required slot; static policy v1 | §9, §10 |

## 5. Per-invocation opt-in (HUMAN-1 = A)

### 5.1 API

**Frozen.**

```python
# workline.review.planning   (new, Review-owned; reads, validates and renders, writes nothing)
PLANNING_CONTRACT = "review-v1-planning-v1"

@dataclass(frozen=True)
class PlanningReview:
    reviewer: Callable[[PlanningReviewTask], PlanningReviewReport]   # §10
    reviewer_identity: str
    reviewer_version: str
    contract: str = PLANNING_CONTRACT

# workline.roadmap
def create_roadmap(store: ProjectStore, plan: RoadmapPlan, *,
                   review: PlanningReview | None = None) -> RoadmapResult | ReviewedPlanningResult
def enter_phase(store: ProjectStore, phase_id: str, design: PhaseEntryDesign, *,
                review: PlanningReview | None = None) -> PhaseEntryResult | ReviewedPlanningResult
```

- `review` is keyword-only with default `None`. Every existing caller passes two or three positional arguments and needs no change.
- `review is None` → the legacy path: the live function body as at the baseline, plus the marker check of §5.3 (which fires only for a pending record that carries a marker); it returns `RoadmapResult` / `PhaseEntryResult`. No Review module is consulted.
- `review` given → validated before the lock, before any read of Project state: `type(review) is PlanningReview`; `review.contract == "review-v1-planning-v1"` exactly; `callable(review.reviewer)`; `reviewer_identity` and `reviewer_version` are non-empty `str`, equal to their own `strip()`, and contain no character `str.splitlines` breaks on. Anything else → `ValidationError` code `review_contract_invalid`; nothing is read or written.
- The return value on the review-v1 path is always `ReviewedPlanningResult` (§19.3); the legacy result types are unchanged and nested inside it on success.

A versioned contract string, not a boolean, is the opt-in: it is recorded verbatim in the durable invocation, it is the selector of the publication contract (§18.5), and a future planning contract is a new string that this build refuses (fail closed) instead of a flag whose meaning drifts.

### 5.2 The durable marker

**Frozen.** The planning mutation's invocation is the live invocation plus exactly two keys:

```text
RoadmapPlan       {"operation": "roadmap-create", "name": <plan.name>, "request": <roadmap_request_identity(plan)>,
                   "review_contract": "review-v1-planning-v1",
                   "publication_contract": "review-v1-planning-publication-v1"}

PhaseEntryDesign  {"operation": "phase-entry", "phase_id": <phase_id>, "design": <design_identity(design)>,
                   "review_contract": "review-v1-planning-v1",
                   "publication_contract": "review-v1-planning-publication-v1"}
```

The request and design identities, `ROADMAP_REQUEST_VERSION` and `DESIGN_IDENTITY_VERSION` are unchanged: the markers sit beside the request, never inside it (Frozen P1 R3 §9: "Existing Roadmap/Work request identity is augmented, never replaced"). `MutationController.begin` makes both durable before any ID is reserved, so the publication contract is durable before any Git stage (Frozen P1 R5-IMPL-2).

### 5.3 Resume compatibility

**Frozen.** At the entry, right after the live same-request check (`require_same_request` for Roadmap creation, `_require_resumable` for Phase entry) and before `_open`, every pending planning record of the slot is compared with the invocation:

| pending record | invocation | outcome |
| --- | --- | --- |
| no `review_contract` (legacy) | legacy | live behaviour, unchanged |
| no `review_contract` (legacy) | review-v1 | `ReconcileRequired` — no silent upgrade; record untouched |
| the frozen marker pair | legacy | `ReconcileRequired` — no silent downgrade; record untouched |
| the frozen marker pair | review-v1 | continue (resume by exact invocation) |
| any other `review_contract` / `publication_contract` presence or value | any | `ReconcileRequired` — unknown contract, fail closed |

The check is added to the legacy entry too. It fires only for a pending record that carries a marker, which no baseline or legacy run writes, so every legacy outcome is unchanged; where it fires, the baseline would already stop the same call with `reconcile_required` through the scope overlap in `MutationController.open` (reconnaissance Q15, Measured), and now stops earlier with the same class and a precise reason.

### 5.4 Platform and fail-closed

**Frozen.** `review` given and `workline.review.fsafe.immutable_create_supported()` false (POSIX at the baseline) → `StopError` code `review_create_unsupported` before `project_operation`: no lock, no mutation record, no write. Legacy invocations on POSIX are unchanged.

An opted-in invocation never falls back to the legacy path: every inability of the gate — platform, Git persistence preflight, Context unavailable, reviewer failure, proof failure — is a STOP or a terminal review outcome, never an ungated registration.

### 5.5 What is never read to decide applicability

No Project-global activation state, no Review record, no `project.yaml` key and no prior Run decides whether a call is gated. Only the `review` argument does, and, for resume compatibility, the markers of the slot's own pending records.

## 6. Identities

### 6.1 Static contract identifiers

| identifier | meaning |
| --- | --- |
| `review-v1-planning-v1` | the planning operation contract (opt-in marker) |
| `review-v1-planning-publication-v1` | the planning publication contract (§18) |
| `review-v1-planning-local-v1` | the planning commit primitive / Git persistence semantics (§15.2) |
| `review-v1-planning-persisted-result-v1` | the `persisted_result` binding inside a Planning Consumption (§16) |
| `review-v1-planning-proof-v1` | the C-2 proof contract for Kp and Km (§15.3, §18.2) |
| `review-v1-planning-policy-v1` | the static Effective Policy (§9) |
| `review-v1-planning-adjudication-v1` | the adjudication rule (§10.6) |
| `review-v1-planning-instruction-v1` | the reviewer instruction identity carried in every request envelope (§10.2) |
| `planning-review-v1` | the task kind of both slots |

### 6.2 Per-kind identities

**Frozen.**

| | RoadmapPlan | PhaseEntryDesign |
| --- | --- | --- |
| `review_kind` | `roadmap-plan-v1` | `phase-entry-design-v1` |
| `target_identity` | the reserved Roadmap ID (live key `roadmap`) | `phase_id` |
| `operation_identity` | `roadmap-create:<request_digest>` | `phase-entry:<request_digest>` |
| `authorized_operation_stage` | `roadmap-create:registration` | `phase-entry:registration` |
| task slot | `roadmap-plan-reviewer` | `phase-entry-design-reviewer` |
| projection semantics version | `roadmap-plan-projection-v1` | `phase-entry-design-projection-v1` |
| adapter identity | `roadmap-plan-adapter-v1` | `phase-entry-design-adapter-v1` |
| Run key | `review-run:roadmap-plan-v1:<roadmap_id>` | `review-run:phase-entry-design-v1:<phase_id>` |
| task key | `review-task:<run_id>:roadmap-plan-reviewer` | `review-task:<run_id>:phase-entry-design-reviewer` |
| Receipt key | `review-receipt:<run_id>:3` | `review-receipt:<run_id>:3` |
| Consumption key | `review-consumption:<receipt_id>` | `review-consumption:<receipt_id>` |

`request_digest` is `serialize.digest` (SHA-256 over canonical bytes) of:

```text
RoadmapPlan       {schema: review-planning-request-identity, version: 1,
                   operation: roadmap-create, request: <roadmap_request_identity(plan)>}
PhaseEntryDesign  {schema: review-planning-request-identity, version: 1,
                   operation: phase-entry, phase_id: <phase_id>, design: <design_identity(design)>}
```

Properties, each by construction: every key part is colon-free and stripped (`gate._require_key_part`); every value is stable across retry (the request identity is durable before any reservation; the target is a planning reservation for RoadmapPlan and the given, existing Phase ID for PhaseEntryDesign); none uses a display number, a timestamp or a process identity; `operation_identity` binds the exact request / design semantics; the kind names carry the planned object and a version, and this contract reserves the `roadmap-` and `phase-entry-` prefixes for planning kinds, so a Work review kind cannot collide; `authorized_operation_stage` names exactly the registration stages of the planning mutation that holds the Consumption, committed as Kp (§15.1) — nothing else is authorized by the Receipt.

### 6.3 Where each Review ID is reserved

**Frozen.** All four in the planning mutation, at the freeze (§14.4), in this order: Run, task, Receipt (`review-receipt:<run_id>:3` — the P2 transition sequence seals at generation 3, §11.6), Consumption (`review-consumption:<receipt_id>`). Generation mutations reserve nothing; their invocations carry the IDs they use. Reservations are per mutation (live `Mutation.reserve_id`), so a Run reserved by one planning mutation is unreachable from any other.

## 7. Candidate contract

### 7.1 Common

**Frozen.** The Candidate record is canonical data:

```text
schema: review-planning-candidate
version: 1
review_kind: <kind>
projection:                       # ReviewedArtifactProjection.to_record()
  projection_kind: reviewed_artifact
  semantics_version: <projection semantics version>
  content: <kind-specific content: §7.2 / §7.3>
declared_base: <kind-specific: §7.4>
```

- `candidate_hash = serialize.digest(candidate record)`.
- CandidateSnapshot (P1 schema, snapshot mode) at `.workline/review/candidate-snapshots/<candidate_hash>.yaml`: `{candidate_hash, reconstruction_mode: snapshot, projection_semantics_version, material: <candidate record>, builder: null}`.
- `candidate_material_digest` = SHA-256 of the snapshot record's canonical bytes (`ReviewStore.candidate_material_digest`).
- Reconstruction mode: `snapshot`. `builder_v1` is not used: its inputs (the request and the reserved IDs) live only in the runtime record, which is not clone-safe.
- Reconstruction on resume: from the planning invocation (`request` / `design`), the planning mutation's reserved IDs and the declared base recomputed on `ProjectView.load(store)` under the lock. The rebuilt record must digest to the Run's `candidate_hash` and equal the stored snapshot's `material`. A different declared base is staleness (§13); any other difference is `ReconcileRequired`.
- After runtime loss the reservations are gone: a fresh Candidate is required (new planning mutation, new reserved IDs, new `candidate_hash`, new Run); the old Run is a legal orphan and its task is never rerun (§12, §23 C-6).

### 7.2 RoadmapPlan content (`normalize_candidate`)

**Frozen.**

```text
roadmap:
  id:            <reserved Roadmap ID>
  name:          <plan.name, verbatim>
  background:    <plan.background.strip()>
  desired_state: <plan.desired_state.strip()>
  scope:         <null when plan.scope is None or "", else plan.scope.strip()>
  out_of_scope:  <same rule on plan.out_of_scope>
phases:                            # declared order of plan.phases
  - key:           <caller key>
    id:            <reserved under phases:phase:<key>>
    name:          <spec.name, verbatim>
    desired_state: <spec.desired_state.strip()>
relations:                         # declared order of plan.relations
  - id:   <reserved under phases:rel:<index>>
    type: <relation type>
    from: <reserved Phase ID of a spec key, or the existing Phase ID as written>
    to:   <same rule>
```

The only normalization is the stripping the live writer itself performs (`store.render_body` strips section text; `roadmap_request_identity` records the same). Names stay verbatim. Frozen P1 R8 §3 fields are all present; the caller keys are reviewed semantics carried through the reservation map (Frozen P1 R8 §4, §6).

### 7.3 PhaseEntryDesign content (`normalize_candidate`)

**Frozen.**

```text
phase_id:   <phase_id>
roadmap_id: <the Phase's roadmap_id>
works:                             # declared order of design.works
  - key:           <design key>
    id:            <reserved under works:work:<key>>
    name:          <verbatim>
    desired_state: <strip()>
    work_kind:     null
    related:                       # declared order
      - id:        <reserved under works:related:<key>:<i>>
        type:      <type>
        to:        <verbatim>
        condition: <mapping, or null>
integration:
  id:            <reserved under integration:work:integration>
  name / desired_state / related   (related IDs under integration:related:integration:<i>)
  work_kind:     phase_integration_check
confirmation:                      # null when the design declares none
  id:            <reserved under confirmation:work:confirmation>
  name / desired_state / related   (related IDs under confirmation:related:confirmation:<i>)
  work_kind:     human_confirmation
  confirmation_target: <the integration ID>
relations:                         # registration order
  - {id, type, from, to}   works:rel:<i> — design planned_next in declared order, then design
                           requires_completion in declared order; a design key resolves to its
                           reserved Work ID, an existing Work ID stays as written
  - {id, type, from, to}   integration:rel:<i> — requires_completion <normal Work i> -> integration,
                           normal Works in declared order
  - {id, type, from, to}   confirmation:rel:0 — requires_completion integration -> confirmation,
                           only with a confirmation
canonical_first_work:              # §7.7
  null, or {key: <design key>, id: <reserved Work ID>}
```

These are exactly the reservation keys and orders the unchanged `register_works` uses (`create.py:251-259`); **Measured** (reconnaissance probe 5): the unchanged `_expand_phase` used exactly the pre-reserved IDs.

### 7.4 Declared base

**Frozen.** Computed from `ProjectView.load(store)` under the lock; part of the Candidate and so of `candidate_hash` (Candidate 7 §4.1: "reviewed artifact identity plus declared base/context identity").

```text
RoadmapPlan:
  existing_phases:        # every existing Phase ID a relation endpoint names, once, sorted by ID
    - {id, roadmap_id, lifecycle: <phase_lifecycle>, state: <phase_state>}

PhaseEntryDesign:
  phase:   {id, roadmap_id, lifecycle, state}      # live preconditions: active, not complete, no Work
  roadmap: {id, lifecycle}                         # live precondition: active
  phase_dependencies:     # incoming requires_completion of the Phase, sorted by relation ID
    - {relation_id, from, from_state}
  existing_works:         # every existing Work ID a design relation endpoint names, once, sorted by ID
    - {id, phase_id, state}
```

### 7.5 Excluded as presentation or runtime material

Display numbers (`R-xx`, `P-xx`, `W-xx`), commit messages, frontmatter layout and key order, ledger file order and whole-file rendering, timestamps, mutation IDs, lock holder, Git commits and branch, the `entry` field as such (the canonical first Work stands for its meaning, §7.7), filesystem enumeration order. The bytes that carry display and layout are proven physically by the persisted proof (§15.3 P4); they are never reviewed as meaning.

### 7.6 Representability check (pre-Review)

**Frozen.** At the freeze, after every reservation and the live payload and structure refusals, before any Review record:

1. the expected effects — RoadmapPlan: the Roadmap `write_file` effect exactly as `_create_roadmap` builds it now (`roadmap.py:478-486`) plus the `decide_phases` effects; PhaseEntryDesign: the three stages' effects built by the registration core's own effect builder (`create._registration_effects` with `_allocated_displays`, counts accumulating across stages, the reserved relation and Related IDs) — reused, or extracted as a pure function with no behaviour change;
2. `projected = ProjectView.load(store).with_effects(expected effects)`;
3. `validate_structure(projected) == []`;
4. `adapter.normalize_persisted(adapter.load_persisted(result identity, projected))` equals `adapter.normalize_candidate(...)` exactly (projection identity);
5. PhaseEntryDesign: R9 (§7.7) evaluated on `projected`.

Failure of 3 → the live refusal (`ValidationError` code `postcheck_failed`); of 4 → `ValidationError` code `review_candidate_unrepresentable`; of 5 → the R9 codes of §7.7. Every one happens before any Review record or domain effect, and the planning mutation is abandoned (§12). Nothing is normalized away to make it pass: a Roadmap name with a trailing space, a `## heading` line injected into a section, a CR or CRLF in any text, U+2028 in a name — every loss the reconnaissance measured (§10.2 there) — is refused here, and a lone CR can therefore never strand a review-v1 run (reconnaissance §17 item 1).

This check predicts the working tree. It is not the persisted proof, which is over the committed result (§15.3).

### 7.7 R9 canonical self-selection

**Frozen P1** R9 §4, §11 as repaired: the rule belongs to Roadmap authority, the adapter only verifies it, legacy is unchanged.

**Frozen.** Roadmap-owned code evaluates, on the projected canonical view of §7.6 (all new Works are in the Phase, which held no Work before):

```text
startable = projected.startable_works(phase_id)
preferred = projected.planned_next_preference(startable)
selection = none        when startable is empty
          = unique A    when len(preferred) == 1
          = ambiguous   when len(preferred) > 1
```

| `design.entry` | canonical selection | outcome |
| --- | --- | --- |
| A | unique A | valid; `canonical_first_work = A` |
| B | unique A (B ≠ A) | `StopError` code `review_entry_not_canonical` |
| A | ambiguous, A among the ties | `StopError` code `review_entry_ambiguous` |
| none | unique A | valid; `canonical_first_work = A` |
| none | ambiguous | `StopError` code `ambiguous_startable_candidates` (the live code of `_require_unique_entry`) |
| none | none startable | valid; `canonical_first_work = null` |
| A | none startable | refused by the live `_require_startable_entry` before `_open`, as today |

The rule applies to review-v1 invocations only; `tests/helpers.simple_entry`, which relies on the legacy acceptance of an explicit entry among equals, is unaffected. The adapter recomputes the selection on the committed view (§15.3 P9) and never decides it.

## 8. Review Context

**Frozen.**

```text
schema: review-planning-context
version: 1
review_kind: <kind>
contract: review-v1-planning-v1
projection_semantics_version: <per kind>
adapter_identity: <per kind>
loader_identity: <§8.1>
authority:                               # in this order
  - {id: registry,            digest: <SHA-256 of <R>/registry.md, CRLF -> LF>}
  - {id: skills/roadmap,      digest: <same, for its resolved SKILL.md>}
  - {id: skills/phase-create, digest: ...}
  - {id: skills/create,       digest: ...}
  - {id: skills/review,       digest: ...}
git_persistence: review-v1-planning-local-v1
```

`<R>` is the configured Workline root (`project.yaml` `workline.root`); Skills resolve through `workline.registry.resolve_skill(R, id)`. Unresolvable or unreadable → `StopError` code `review_context_unavailable` at the freeze, before any Review record. `review_context_hash = serialize.digest(context record)`. Recomputed at the freeze, before each reviewer launch, before each generation mutation after the first, at the use check, and (its `loader_identity`) before the persisted proof.

Decisions on each candidate input (task §18):

| input | decision |
| --- | --- |
| base Git identity (HEAD / commit) | **not bound in the Context.** The Run's own generation commits advance HEAD, so a HEAD-bound Context would invalidate itself. Branch and lineage are bound by the operation binding (§11.5); the semantic base is bound by the Candidate's declared base (§7.4) |
| target Roadmap / Phase identity | bound by the Candidate content and the gate's `target_identity` |
| existing relation endpoints relied on | declared base (Candidate) |
| relevant lifecycle / state facts | declared base (Candidate) |
| predecessor / dependency states | declared base (Candidate) |
| canonical loader identity | `loader_identity` |
| renderer / projection identity | `loader_identity` + `projection_semantics_version` + `adapter_identity` |
| Workline implementation identity | `loader_identity` (content, not location) |
| authority identities / digests | `authority` |
| projection schema / version | `projection_semantics_version` |
| review kind | `review_kind` |
| Git persistence semantics | `git_persistence` |
| timestamps, lock IDs, provider job handles, mutation `updated_at`, runtime material | never |

### 8.1 Loader identity

**Frozen.** `loader_identity = serialize.digest({schema: review-planning-implementation, version: 1, files: [...]})`, where `files` lists every `*.py` file under the running implementation's package directory — the directory the Layer-2 implementation check proved to be `<R>/src/workline` — recursively, as `{path: <posix path from the package's parent, e.g. workline/roadmap.py>, digest: <SHA-256 of the bytes with every CRLF replaced by LF>}`, sorted by path.

Live implementation identity proves where the code is, not what it is (`implementation.py` docstring; `rules/git` Workline implementation: "committed revision ... 実行中にsourceが変更されないことは保証しない"). The content digest of the whole package covers the renderers, the reader, the registration cores and the adapters together, conservatively, and is identical for one commit checked out with different line-ending settings.

## 9. Effective Policy

**Frozen.** One static, versioned policy for P2:

```text
schema: review-planning-policy
version: 1
policy_id: review-v1-planning-policy-v1
slots:
  - {review_kind: roadmap-plan-v1,       task_slot: roadmap-plan-reviewer,       task_kind: planning-review-v1, required: true}
  - {review_kind: phase-entry-design-v1, task_slot: phase-entry-design-reviewer, task_kind: planning-review-v1, required: true}
reviewer_identity_rule: caller-declared identity and version, bound at acceptance; a settlement is accepted only from them
report_statuses: [completed, declined]
severities: [HIGH, MID, LOW]
blocking_severities: [HIGH, MID]
low_disposition: recorded in the report digest, returned to the caller, non-blocking
declined_disposition: the task settles failed; the planning attempt is not authorized
error_disposition: no settlement; the same task is launched again by the next run
timeout_disposition: none imposed by Workline; a reviewer that gives up returns declined
adjudication_rule: review-v1-planning-adjudication-v1
obligation_rule: every HIGH or MID finding and every failed task is an unresolved obligation; P2 resolves none
seal_rule: every required task settled completed and zero unresolved obligations
repair: none; a not-authorized planning attempt is terminal
instruction: review-v1-planning-instruction-v1
```

`effective_policy_hash = serialize.digest(policy record)`, identical for both kinds (the kind is bound separately). No adaptive learning, no Project override. When the implementation lands, canonical authority `skills/review` declares this record verbatim in a "Planning Review Policy" section; the implementation's constant must be canonically identical, and a test asserts it (§28 C).

No unresolved HIGH or MID can authorize a registration: they are obligations, and a seal requires zero.

## 10. Reviewer, TaskInput, settlement, adjudication

### 10.1 Interface

**Frozen.** A synchronous callback, run inside the planning operation's lock like START's executor (`start.py:201`, `Executor = Callable[[ExecutionContext], Outcome]`). No requirement needs asynchronous human waiting, so P2 has none: there is no Review question wait, and the lock is never released on purpose during a Review.

```python
@dataclass(frozen=True)
class PlanningReviewTask:
    task_id: str
    task_slot: str
    task_kind: str
    review_kind: str
    request_envelope: dict[str, Any]     # canonical data, a deep copy of the stored TaskInput's envelope
    request_digest: str
    candidate_hash: str
    review_context_hash: str
    effective_policy_hash: str

@dataclass(frozen=True)
class PlanningReviewFinding:
    severity: str        # HIGH | MID | LOW
    code: str            # non-empty, stripped, no line break
    message: str

@dataclass(frozen=True)
class PlanningReviewReport:
    task_id: str
    reviewer_identity: str
    reviewer_version: str
    status: str          # completed | declined
    findings: tuple[PlanningReviewFinding, ...] = ()
```

All four live in `workline.review.planning`. The reviewer is caller code run in-process, like START's executor, and is not contained: a change it makes to a planning-owned path is caught by the own-bytes, dirty-overlap and proof checks, and nothing it writes anywhere else is committed by P2, whose commits carry only their named paths (`git commit --only`).

### 10.2 Request envelope, TaskInput, accepted descriptor

**Frozen.**

```text
request_envelope:
  schema: review-planning-request
  version: 1
  review_kind: <kind>
  policy_id: review-v1-planning-policy-v1
  instruction: review-v1-planning-instruction-v1
  candidate: <the candidate record, §7.1>
  context: <the context record, §8>
request_digest = serialize.digest(request_envelope)
```

The TaskInput (P1 schema) at `.workline/review/task-inputs/<task_id>.yaml`: `task_id`, `task_slot`, `task_kind: planning-review-v1`, `reviewer_identity`, `reviewer_version`, `request_envelope`, `request_digest`, `candidate_hash`, `reconstruction_mode: snapshot`, `candidate_material_digest`, `review_context_hash`, `effective_policy_hash`, `accepted_generation: 1`. `task_input_digest` = SHA-256 of its canonical bytes. The accepted descriptor in generation 1 carries every P1 `ACCEPTED_TASK_FIELDS` value from the same sources.

### 10.3 Launch

**Frozen.** The reviewer is called only when all hold, checked right before the call:

- the Run's latest generation is generation 1 (`status: open`), and the task is accepted there and unsettled;
- `gate.require_persisted` passes for the snapshot, the task input and generation 1, and each of their HEAD blobs holds exactly the canonical bytes with mode `100644` (§15.2 blob check);
- `ReviewStore.provenance_problems(descriptor, 1) == []`;
- the operation binding holds (§11.5); Candidate, Context and Policy are current (§13);
- the `review` argument's `reviewer_identity` and `reviewer_version` equal the accepted descriptor's, else `StopError` code `review_reviewer_mismatch` and no call.

The task object is rebuilt from the stored TaskInput, never from memory. So the external launch happens only after Candidate, TaskInput and the accepted generation are persisted in local Git (Frozen P1 R3 §3, §10).

### 10.4 Return validation, failures, retry

**Frozen.**

| event | outcome |
| --- | --- |
| the callback raises | `StopError` code `review_reviewer_failed` (original chained); nothing settled; the planning mutation stays pending |
| the return is not exactly a `PlanningReviewReport`, `task_id` differs, `status` outside `completed` / `declined`, or a finding is not exactly a `PlanningReviewFinding` with a valid severity and code | `StopError` code `review_report_invalid`; nothing settled |
| identity or version differ from the accepted descriptor | `StopError` code `review_reviewer_mismatch`; nothing settled |
| valid report | settled through generation 2 (§10.5) |
| next run while generation 1 is still the latest | the same `task_id` is launched again from the stored TaskInput; no new task ID is ever reserved (Frozen P1 R2 §5) |
| duplicate: generation 2 already settles the task with the same `result_digest` | `gate.validate_settlement` returns the descriptor; idempotent (P1 behaviour; the P2 launch rule of §10.3 never launches a settled task, so the flow itself cannot produce one) |
| conflict: a different `result_digest` for a settled task | `review_callback_conflict` (P1), reconcile |
| unknown: a task the Run never accepted, or another reviewer | `review_callback_unknown` (P1) |

A result held only in process memory is lost on a crash and the same task is launched again; the runtime copy (§10.5) is never used to skip the reviewer.

### 10.5 Settlement

**Frozen.** The canonical report record:

```text
{schema: review-planning-report, version: 1, task_id, reviewer_identity, reviewer_version, status,
 findings: [{severity, code, message}, ...]}          # report order
result_digest = serialize.digest(report record)
```

Its canonical text is written to `.workline/runtime/review/reports/<task_id>.yaml` (runtime, `durable_write_text`) before generation 2 is recorded. It is never authority and never settlement material; it is read only to return findings after a resume, and only when its digest equals the settled `result_digest`. Then `gate.validate_settlement(store, run, task_id, result_digest, reviewer_identity)`, then generation 2 with `settled_tasks: [{task_id, status: completed | failed, result_digest, settled_generation: 2}]` (`declined` settles as `failed`).

### 10.6 Adjudication and gate digests

**Frozen.** Mechanical; the reviewer's severity is final; no human adjudication in P2.

```text
adjudication  {schema: review-planning-adjudication, version: 1, rule: review-v1-planning-adjudication-v1,
               tasks: [{task_id, status, result_digest, high, mid, low}]}
obligations   {schema: review-planning-obligations, version: 1,
               obligations: [{task_id, kind: finding, severity: HIGH | MID, code, message}   # report order
                             | {task_id, kind: task_failed, severity: FAILED, code: task_failed, message: ""}]}
coverage      {schema: review-planning-coverage, version: 1,
               required: [{task_slot, task_id}], settled: [{task_id, status}]}
report_set    {schema: review-planning-report-set, version: 1, reports: [{task_id, result_digest}]}
evidence      {schema: review-planning-evidence, version: 1,
               checks: [{check: structure-projection, result: pass},
                        {check: representability, result: pass},
                        {check: self-selection, result: pass | not-applicable, canonical_first_work: <id | null>},
                        {check: git-persistence-preflight, result: pass},
                        {check: dirty-separability, result: pass}]}
```

Gate fields: `evidence_digest`, `coverage_digest`, `raw_report_set_digest`, `adjudication_digest`, `obligation_digest` are `serialize.digest` of these records. Generation 1 uses the evidence of the freeze and the empty forms (`settled: []`, `reports: []`, `tasks: []`, `obligations: []`). Generation 2 and 3 use the settled forms. `unresolved_obligations = len(obligations)`. Authorized iff every required task settled `completed` and `unresolved_obligations == 0`. Evidence completeness (R11) is `unknown` by definition and is never reused: P2 reuses nothing across Candidates.

## 11. Generation mutations (C-4)

**Chosen: Direction A** — every generation transition is its own generation mutation, owned by the Roadmap operation, with Frozen P1 R2 §4 / R3 §2 and the live helpers `gate.pending_generation_mutations` / `gate.next_generation_scope` unchanged.

Why: it satisfies the frozen procedure as written and uses the helper as landed (**Measured**, reconnaissance probe 8: initial scope exactly `[gate path, token]`, generations from the unchanged helper, interrupted generation mutation resumed first, every window clean). Direction B would change frozen R2/R3 text and the live helper and needs a new mechanism to tell the current owner, a stale predecessor and a second owner apart inside one long-lived mutation; no P2 requirement needs it. Every defect the reconnaissance found in Direction A is closed below: the missing snapshot (§11.4), cross-mutation branch binding (§11.5), the abandonment gap (§12), the one-mutation wording of `rules/git` (§11.12, §26.1).

### 11.1 Ownership

**Frozen.** Top-level operation: the planning operation (`create_roadmap` under lock operation `roadmap-create`, `enter_phase` under `phase-entry`). Owner string: `"roadmap"`. A generation mutation is started, applied, committed and completed by Roadmap-owned code (`workline.roadmap_review`) inside that operation's `project_operation` lock (`MutationController.require_execution_lock` accepts it: `mutation.py:1626-1652`). It has no lock operation, entry point, CLI or API of its own; it is never a top-level operation. Review takes no lock, starts no mutation, commits nothing and finalizes no Roadmap or Phase state; it contributes record shapes, validation, read-back and the generation-scope helper.

```text
Roadmap top-level operation (lock roadmap-create | phase-entry, owner "roadmap")
  owns:  planning mutation          request + markers; registration; Consumption; Kp; Km; push
         generation mutation 1      accept   (snapshot, task input, gate 1)
         generation mutation 2      settle   (gate 2)
         generation mutation 3      seal     (gate 3 + Receipt)
```

### 11.2 Invocation

**Frozen.** Exactly these keys:

```text
{"operation": "review-generation",
 "review_contract": "review-v1-planning-v1",
 "planning_mutation_id": <the planning mutation ID>,
 "review_kind": <kind>,
 "review_run_id": <run_id>,
 "generation": <N from gate.next_generation_scope>,
 "transition": "accept" | "settle" | "seal",
 "candidate_hash": <the Run's>, "review_context_hash": <the Run's>, "effective_policy_hash": <the Run's>,
 "obligation_digest": <the obligation_digest generation N records>,
 "receipt_id": <the reserved Receipt ID for "seal", null otherwise>}
```

It binds the parent (`planning_mutation_id`), the Run, the exact generation and the Candidate / Context / Policy identities (Frozen P1 R3 §9). A resumed generation mutation is re-entered through `MutationController.open` with its recorded owner, invocation and scope (reconnaissance probe 8), so its invocation never has to be recomputed.

### 11.3 Initial write scope

**Frozen.** `WriteScope(files = GenerationScope.files + extra, entities = ())`, created by `MutationController.open("roadmap", invocation, scope)` directly — not through `_open` (no push destination, no `_ledgers`):

| transition | `files` |
| --- | --- |
| accept (N = 1) | gate path 1, token, candidate snapshot path, task input path |
| settle (N = 2) | gate path 2, token |
| seal (N = 3) | gate path 3, token, Receipt path |

Every path is known before the mutation begins (§6.3), so no generation mutation calls `extend_scope` (Frozen P1 R2 §4: "extend_scope() is not the safety mechanism"). The planning mutation's scope never holds a token, so the helper never refuses the planning mutation itself.

### 11.4 Dirty snapshot

**Frozen.** Right after the generation mutation begins, before any effect: `gitops.record_preexisting_dirty(gen, root)`, then `gitops.ensure_separable_before_effects(gen, <its record paths>)`. A resumed generation mutation reuses its noted snapshot. **Measured** (reconnaissance probe 8, first run): without the snapshot taken when the mutation begins, the mutation took its own generation file for a person's change and stopped with `dirty_overlap`.

### 11.5 Operation binding (branch and base across mutations)

**Frozen.** At the end of the freeze the planning mutation records the note `review_binding = {branch: <full ref of HEAD's branch>, head: <HEAD commit>}`. "The binding holds" means: HEAD is on exactly that branch (full ref) and HEAD's history holds `head` (`gitcmd.descends_from`). It is checked before each generation mutation starts, before each reviewer launch, at the use check, and before the planning mutation records each of its post-Review stages (registration, Kp, Consumption, Km, publication). Not holding → `ReconcileRequired`, nothing replayed, recorded, committed or pushed; returning to the branch continues. Inside each mutation the live rules apply unchanged: a generation mutation's `create_file` stage carries `decided_on`, and its commit names that branch (`_bind_decision`).

### 11.6 Content and commits

**Frozen.** The P2 transition sequence is fixed:

| N | transition | stage `review-generation` (`create_file` effects) | gate `status` |
| --- | --- | --- | --- |
| 1 | accept | candidate snapshot, task input, gate 1 (accepted task, empty settlement) | `open` |
| 2 | settle | gate 2 (settled task, settled digests) | `open` |
| 3 | seal | gate 3 (`sealed_authorized`, `receipt_id`, `authorized_operation_stage`) and the Receipt — one stage (Frozen P1 R3 §7) | `sealed_authorized` |

Before recording the stage: `gate.require_committable` and the Git persistence preflight (§14.3) on its paths. Then `apply()`, then Git stage `review-generation-commit`: exactly one `git_commit` of the stage's paths with the planning commit primitive (§15.2), message `chore(workline): record review generation <N> of <run_id>`, commit-only, never a push. Then `gate.require_persisted(paths)` and the blob check (HEAD blob == canonical bytes, mode `100644`). Only then `complete()`. Generation commits stay local until the planning publication (§18) carries them as history; the reviewer launch needs only the local Git boundary (Frozen P1 R3 §10: remote-less Projects remain valid).

P2 writes no other generation and no Supersession record: staleness is terminal instead of an invalidation generation (§13). A generation whose number the helper computes differently from this table, or a chain of any other shape, is `ReconcileRequired`.

### 11.7 Completion and record retention

A generation mutation is complete after its commit and persistence proof. Its runtime record follows the live rule: removed when this run created it and it is provably unchanged, kept when it was resumed (`Mutation._own_record_removable`). Nothing reads a completed generation mutation's record; the committed chain is the truth.

### 11.8 Resume discovery order

**Frozen.**

```text
1. live entry checks; same-request and marker checks (§5.3)
2. the planning mutation is resumed by exact invocation, or begun (live `_open`)
3. when the planning mutation has reserved a Run:
     pending = gate.pending_generation_mutations(store, run_id)
     none                                          -> continue
     exactly one, owner "roadmap", operation "review-generation",
       planning_mutation_id == this planning mutation, review_run_id == run_id
                                                   -> resume it by its recorded owner / invocation / scope:
                                                      no recorded effect -> Mutation.abandon()
                                                      otherwise          -> its invocation's generation must be the
                                                                            validated chain's next generation, or its
                                                                            latest when that gate already holds exactly
                                                                            its recorded bytes (else ReconcileRequired);
                                                                            then apply, Git stage, persistence proof,
                                                                            complete()
     exactly one bound to anything else            -> ReconcileRequired (conflicting owner)
     more than one                                 -> ReconcileRequired (the helper's review_generation_conflict)
4. only then gate.next_generation_scope computes N+1
```

The planning mutation is resumed first, its pending generation mutation second, and no generation is computed before that one is resolved (Frozen P1 R3 §2).

### 11.9 Conflicts and crashed predecessors

- A second owner holding the Run's token is refused (step 3).
- A crashed predecessor is the pending generation mutation found through the token.
- A crash with no recorded effect leaves nothing physical: effects are durable before they are applied, so abandoning it and computing N again cannot fork the Run.
- A physical create before the `applied` flag was saved is resumed, classified `applied_matching` and completed before N+1 is computed; the token makes a hypothetical N+2 overlap it (Frozen P1 R12 §3).

### 11.10 Generation mutations and the registration never coexist

The planning mutation records no effect before the use check, and generation mutations exist only before it. Once a registration stage is recorded, a pending generation mutation of its Run is a conflict (`ReconcileRequired`).

### 11.11 The planning mutation disappears

**Frozen.** Runtime loss or a fresh clone after generations were committed:

- The committed Review records stay. The Run is a legal orphan — its latest generation `open`, or sealed and unconsumed — and `validate_review` validates it as one.
- A pending generation mutation left without its planning mutation is inert. Its scope holds only its Run's paths, and no P2 operation resumes it, because a new planning mutation reserves a new Run and never looks at the old token.
- The same request again begins a new planning mutation with new reserved IDs, a fresh Candidate and a new Run.

### 11.12 The `rules/git` one-stable-mutation assumption

**Frozen.** `rules/git` Operation Owner says an operation resumes the one pending mutation that corresponds to the invocation and stops on several. The review-v1 planning operation owns one planning mutation and the generation mutations it starts. At the entry, the planning mutation is the one corresponding mutation. A pending generation mutation bound to it by `planning_mutation_id` and the Run's token is its subordinate and is resolved in the order of §11.8. Anything else remains "複数件 / 競合" and is `reconcile required`. The authority text is amended when the implementation lands (§26.1). Until then no review-v1 planning exists and the live rule is unchanged.

## 12. Planning mutation lifecycle

**Frozen.**

| state | condition | behaviour |
| --- | --- | --- |
| may be abandoned | no generation mutation of its Run has started (no gate chain for the Run, no pending generation mutation bound to it), no effect recorded, and the live path would abandon it too: a Roadmap creation begun or resumed, a Phase entry begun by this run (a resumed Phase entry is never abandoned, `skills/roadmap` Phase entry) | a STOP abandons it (live `abandon_on_stop`): every pre-Review refusal (§7.6, §7.7, §14), a Context that cannot be computed, a reservation or note failure |
| must remain pending | from the start of generation mutation 1 until a terminal outcome | any STOP (reviewer failure, invalid report, binding moved, proof failure, reconcile) leaves it pending; the next invocation with the same request resumes it |
| completed without registration | `not_authorized` (§19.1) or `stale` (§19.2) | `complete()` with no effect recorded; `ReviewedPlanningResult` returned |
| completed with registration | publication done (remote-less: C-2(Km) recorded) and the live structure postcheck passed | `complete()`; `ReviewedPlanningResult(status registered)` |
| superseded by a fresh Candidate | never while pending | a different request or design for the slot → `reconcile_required` (live); a fresh Candidate exists only after the previous planning mutation was abandoned (pre-Review), completed (terminal) or lost with the runtime |

The way out of an operational failure is to run the same request again with a working reviewer, or to have the reviewer return `declined`, which settles the task `failed` and ends the attempt as `not_authorized` (§19.1). A pending review-v1 planning mutation therefore never needs a human to stop blocking the Project, except where a reconcile rule of `rules/git` applies (history rewritten, foreign change, proof failure).

## 13. Staleness before Consumption

**Frozen.** Currency means: the Candidate rebuilt with the current declared base digests to the Run's `candidate_hash`, the Context to its `review_context_hash`, the policy to its `effective_policy_hash`. It is checked before each generation mutation after the first, before each reviewer launch, and at the use check, in this order: Context and Policy first (a difference is `stale`), then the Candidate rebuild (a different declared base is `stale`; any other difference is `reconcile_required`). No P3 Review-validity fast path exists; P2 never re-reviews inside the same planning operation.

| change | detected by | outcome |
| --- | --- | --- |
| a different request or design (the caller passes another plan) | live same-request / `_require_resumable` | `reconcile_required`, record untouched |
| declared base: lifecycle or state of a named existing Phase or Work, the Phase's or Roadmap's lifecycle or state, a Phase dependency's state | Candidate rebuild | terminal `stale` (§19.2) |
| Workline implementation content | Context (`loader_identity`) | terminal `stale` |
| authority text (`registry.md`, a listed Skill) | Context (`authority`) | terminal `stale` |
| Effective Policy | policy hash | terminal `stale` |
| reserved IDs or planning invocation not reproducing the Run's Candidate | rebuild | `reconcile_required` |
| a Run record changed | `ReviewStore` / `create_file` classification | `reconcile_required` |

After the first registration stage is recorded, the declared base is not re-evaluated: the authorized transition has been decided (and the persisted proof, §15.3, is what protects its meaning). The loader identity alone is re-checked before the persisted proof, because the proof's meaning depends on it; a change is `ReconcileRequired` (reason `review_loader_changed`) with the planning mutation pending, never an undo of the registration.

What can change, and when:

- **Under the lock** (the whole synchronous run, the reviewer included): only actors outside Workline — a person or tool editing files or Git state, an edit of the Workline root on disk. P2 has no deliberate lock release.
- **Across a crash window** (the lock released by the process ending): Workline operations whose declared write scope does not overlap the pending planning mutation's — Roadmap / Phase hold, resume, cancel and achievement (event log only), push destination pin maintenance, and, for a pending Roadmap creation, Related maintenance and direct CREATE (`related.yaml`). Roadmap creation, Phase addition, Phase entry and plan exclusion (`roadmap.yaml`) and START (every ledger) are refused by scope overlap (**Measured**, reconnaissance §12).

## 14. Pre-Review refusals and the freeze

### 14.1 Registration paths

**Frozen.**

- RoadmapPlan: `.workline/roadmaps/<roadmap_id>.md`, `.workline/phases/<phase_id>.md` for every reserved Phase, and `.workline/relations/roadmap.yaml` when the plan declares at least one relation.
- PhaseEntryDesign: `.workline/works/<work_id>.md` for every normal Work, the integration and the confirmation when present, `.workline/relations/roadmap.yaml` (always: integration dependencies exist), and `.workline/relations/related.yaml` when any Work declares Related.

These are exactly the paths the registration stages write (`ops.owned_canonical_paths` restricted to the registration stages).

### 14.2 Dirty overlap

**Frozen** (task §23). At the freeze, `gitops.ensure_separable_before_effects(planning, registration paths + Run record paths + Consumption path)` on the snapshot `_open` recorded. A person's pre-existing change overlapping any of them stops the call with `dirty_overlap` before anything is written, and the planning mutation is abandoned, so the person's bytes are untouched and no reviewer runs for a plan that can never be committed. Each generation mutation repeats the check for its own paths (§11.4). The Kp and Km stages keep the live finalize check (`ensure_separable(preexisting, paths)`). The legacy path is unchanged; BL-041 is not fixed globally.

### 14.3 Git persistence preflight

**Frozen.** For every planning-owned path, `git check-attr -z filter ident working-tree-encoding -- <paths>` must report `unspecified` (or `unset` for `filter` / `ident`) for all three attributes. Anything else → `StopError` code `review_git_transform`. These are the attributes that can make a committed blob differ from the written bytes or run an external process during `git add` (clean and process filters, Git LFS, `$Id$` expansion, re-encoding). Text and eol normalization is the identity on LF-only content, and every file P2 writes is LF-only (canonical renderers; CR refused by §7.6). The check runs at the freeze and again right before every Git stage P2 records (attributes can change).

### 14.4 Freeze order

**Frozen.** After `_open` and the live reservations:

```text
1  RoadmapPlan: reserve `roadmap` (live) and the Phase and relation IDs through `decide_phases` (live; records
   nothing); PhaseEntryDesign: reserve every stage ID under the register_works keys (§7.3); extend the entity scope
2  build the Candidate; representability check (§7.6); R9 (§7.7)
3  Context (§8), Policy (§9), evidence (§10.6)
4  reserve Run, task, Receipt, Consumption IDs (§6.3); extend the file scope with the Consumption path
5  gate.require_committable (Review paths); Git persistence preflight (§14.3); dirty overlap (§14.2)
6  record the note review_binding (§11.5)
7  start generation mutation 1
```

Before generation mutation 1 has started, steps 1–6 are refusals: a STOP anywhere in them abandons the planning mutation (§12), and a resume runs them again deterministically (every reservation returns the recorded ID; the note, once recorded, is kept). Once generation mutation 1 has started, a resume never runs steps 5–6 again and never abandons: steps 1–3 are recomputed only as the currency check of §13 (a difference is `stale` or `reconcile_required`), and the recorded `review_binding` is checked, never re-recorded.

## 15. Registration, persisted proof and committed reload (C-3)

**Chosen: Direction A**: a planning-specific local commit, then an exact proof, then a canonical reload from the committed result, then equality, and only then publication.

Why: it proves what Git stored rather than predicting it. Direction B would need a positive proof, before the commit, of the exact Git objects through hooks, filters and concurrent writers. Live code has no helper for that, and it is harder to prove correct. The user preference of the task (§8.1) rules it out.

### 15.1 Sequence

**Frozen.** The planning mutation, after the use check (§17):

```text
1  registration stages, live and unchanged — roadmap, phases | works, integration, confirmation —
   with their projected refusals, postchecks and (Phase entry) the live phase structure check
2  working-tree round trip: ProjectView.load(store) -> normalize_persisted == reviewed;
   mismatch -> ValidationError review_roundtrip_mismatch (P1 adapter code), pending
3  binding holds; Git persistence preflight; ensure_separable(preexisting, registration paths)
4  stage review-registration-commit: one git_commit (Kp) of exactly the registration paths,
   planning commit primitive, the live message (chore(workline): create roadmap <display> |
   chore(workline): expand phase <display>); apply
5  persisted proof over Kp (§15.3)                                   -> C-2(Kp)
6  stage review-consumption: one create_file — the Planning Consumption binding Kp (§16); apply
   (the recorded Consumption effect is the durable C-2(Kp) checkpoint)
7  stage review-consumption-commit: one git_commit (Km) of exactly the Consumption path,
   planning commit primitive, message chore(workline): record review consumption <consumption_id>; apply
8  metadata proof over Km (§18.2); note publication_proof            -> C-2(Km)
9  destination present: stage review-publication: one git_push of exact Km (§18.4); apply
10 live structure postcheck (_stop_on_structure "postcheck"); complete()
```

The legacy combined `finalize` stage is never recorded by a review-v1 planning mutation (Frozen P1 R5 §12.2: Review-v1 may not reach the destination through a combined stage).

### 15.2 The planning commit primitive (`review-v1-planning-local-v1`)

**Frozen.**

- Selected by the `git_commit` payload field `"mode": "review-v1-planning-local-v1"`, recorded with the effect (durable); `apply_effect` uses it for that effect only.
- Staging: `git -c core.hooksPath=<H> -c core.fsmonitor=false add -- <paths>`.
- Commit: `git -c core.hooksPath=<H> -c commit.gpgSign=false -c core.fsmonitor=false -c gc.auto=0 -c maintenance.auto=false commit --only --no-verify --no-gpg-sign -m <message> -- <paths>`.
- `<H>` = the absolute path of `<Project root>/.workline/runtime/review/no-hooks`, a Workline-owned empty directory, created when absent (absolute, so Git never resolves it against another directory). An entry there that is not an empty plain directory → `StopError` code `review_hooks_path_invalid`.
- Consequences: no repository hook runs (**Measured**, §31), no signing program runs, no clean or process filter runs (refused by §14.3), no background maintenance starts.
- Everything else is the live commit: the commit ID is recorded with `applied` in one durable save (`_make_commit`, `_commit_just_made`), and it is never recognized by its message.
- Used for every generation commit, Kp and Km; never for a legacy commit.
- The primitive's identity is the Context's `git_persistence` (Frozen P1 R5 §5–§6, R11 §10, R12 §8: a mechanically suppressed hook mode is bound in the Git semantics identity).
- Blob check (used by §10.3, §11.6, §15.3, §18.2): the committed blob of a path is read with `git cat-file blob <oid>` as raw bytes (no text decoding, no filters) and compared byte for byte; its mode comes from `git ls-tree -r -z --full-tree`.
- Kp or Km recorded applied without a commit ID (an interruption between `git commit` and the save) cannot be shown to be the mutation's own. The result is `ReconcileRequired` (reason `review_commit_unowned`), with no backfill in P2, the live treatment of an unidentified commit (`rules/git` Commit / push).

### 15.3 Persisted proof over Kp — C-2(Kp)

**Frozen.** Contract `review-v1-planning-proof-v1`. PASS requires every item; any failure → `ReconcileRequired` (reason `review_persisted_proof_failed`):

| # | condition | how |
| --- | --- | --- |
| P1 | Kp is the planning mutation's own commit | the `review-registration-commit` `git_commit` is recorded `applied` with `commit_id`; Kp = that ID |
| P2 | exact branch, parent and lineage | HEAD on `review_binding.branch`; that branch holds Kp; Kp has exactly one parent P; P descends from `review_binding.head` |
| P3 | exact operation-owned path set | `git diff-tree -r -z --no-renames --no-abbrev --raw P Kp` lists exactly the registration paths: status `A` for each new entity file, `M` for each ledger, new mode `100644` for every entry, nothing else |
| P4 | exact committed bytes | each entity blob == the recorded `write_file` payload content (UTF-8); each ledger blob's SHA-256 == the recorded `wrote` digest of the registration's last write to it |
| P5 | fresh canonical reconstruction | committed-result loader (§15.4) over Kp and over P |
| P6 | exact relation / ledger result | Kp's roadmap relations == P's + exactly the expected new relations, appended in registration order, records identical; the same for Related; Kp's entities == P's + exactly the reserved new entities |
| P7 | structure | `validate_structure(Kp view) == []` |
| P8 | normalized persisted semantics == reviewed Candidate | `normalize_persisted(load_persisted(result identity, Kp view)) == normalize_candidate(reviewed)` (projection identity; kind and semantics version equal); created IDs == reserved IDs; each expected entity and relation exactly once; no extra operation-owned entity or relation (P3 + P6) |
| P9 | R9 canonical first Work (PhaseEntryDesign) | `startable_works` + `planned_next_preference` on the Kp view give exactly the reviewed `canonical_first_work` (unique ID, or none) |
| P10 | interpretation unchanged | `loader_identity` recomputed now == the Context's; `adapter_identity` equal |
| P11 | nothing published before this proof | the planning mutation holds no `git_push` effect; the planning commit primitive runs no hook |

This covers the task's eleven requirements: 1 = P3, 2 = P4, 3 = P3 modes, 4 = P6, 5 = P8 created IDs, 6 = P3 + P6, 7 = P5, 8 = P8, 9 = P9, 10 = P1 + P2, 11 = P11 + §18. Nothing is substituted by a path list, working-tree bytes, the request identity or `ProjectView.with_effects`.

### 15.4 The committed-result loader

**Frozen.** Its responsibility is limited to this: given a commit C, materialize exactly C's canonical Project files from raw blob bytes (`git ls-tree` + `git cat-file blob`; no checkout, no smudge, no eol conversion):

- `.workline/project.yaml`
- `.workline/roadmaps/*.md`, `.workline/phases/*.md`, `.workline/works/*.md`
- `.workline/relations/roadmap.yaml`, `.workline/relations/related.yaml`
- `.workline/events/events.jsonl`

It writes them into a fresh directory `.workline/runtime/review/proofs/<nonce>/`, then returns `ProjectView.load(ProjectStore(<that directory>))`, the production loader unchanged.

- Limits: every materialized entry is a blob of mode `100644`; a symlink (`120000`), gitlink (`160000`), executable (`100755`) or tree where a file belongs → proof failure. `.workline/review/**`, `.workline/derivations/**`, `.workline/runtime/**` and everything outside `.workline/` are not materialized (`ProjectView` does not read them). The directory is removed after the proof and read by nothing else; a leftover is runtime residue.
- No second parser: the loader parses nothing itself. Tests use this loader and the production readers, never a different parser.
- Why raw blobs: checkout conversion (`core.autocrlf`, eol attributes) changes only line ends, which the production reader normalizes. Content-changing checkout filters are refused on planning-owned paths (§14.3). So a raw-blob reading is what any conforming checkout reads.
- **Measured** (§31): for a live Roadmap creation plus Phase entry, the materialized reading equals the working-tree reading, all 9 canonical files are mode `100644`, and structure validation is clean.

### 15.5 Proof failure after Kp exists

**Frozen.** STOP (`ReconcileRequired`). The planning mutation stays pending; no Consumption is written and nothing is pushed. Kp remains a local, operation-owned, unpublished commit; Workline never resets, rebases or amends it. Every retry runs the same proof over the same Kp.

If Kp reaches the destination through another subject, a person or another operation's push carrying it as base history (`rules/git` Push destination), it is a registration without a Consumption. Structurally that is a legacy registration, and its Receipt stays unconsumed. Workline never presents it as authorized. A human reconciles.

The preflight (§14.3), the representability check (§7.6), the contained commit primitive (§15.2) and the working-tree round trip (§15.1 step 2) exist so that this path is reached only through a concurrent foreign change or a Git fault.

## 16. Planning Consumption (C-2) and planning uniqueness

**Chosen representation:** an explicit new version of the P1 Consumption schema: `schema: review-consumption`, `version: 2`, the *Planning Consumption*.

Why:

- v1 cannot carry the binding: its reader refuses unknown fields (`records.py:143-161`), and its three Work fields bind a Work terminal event only.
- A separate record referenced by convention from a v1 Consumption would give existing v1 bytes a new obligation.
- A new version is explicit, keeps every v1 record readable with exactly its P1 meaning, and keeps one Receipt uniqueness index across both.

### 16.1 Fields

**Frozen.**

```text
schema: review-consumption
version: 2
consumption_id            # reserved under review-consumption:<receipt_id>
receipt_id
review_run_id
review_generation         # 3
review_kind               # roadmap-plan-v1 | phase-entry-design-v1
authorized_candidate_hash
operation_identity
operation_mutation_id     # the planning mutation
target_identity           # the Roadmap ID | phase_id
persisted_result:
  contract: review-v1-planning-persisted-result-v1
  request_digest                # §6.2 (Frozen P1 R8 §8 / R9 §9 request / design identity digest)
  registration_commit           # Kp, full ID
  registration_parent           # P, full ID
  branch                        # full ref
  registration_delta_digest     # serialize.digest({schema: review-planning-delta, version: 1, parent: P, commit: Kp,
                                #   entries: [{path, status, old_mode, new_mode, old_blob, new_blob}] sorted by path})
  semantic_projection_digest    # Projection.identity() of the normalized persisted projection (== the reviewed one)
  adapter_identity
  loader_identity
  # roadmap-plan-v1:
  roadmap_id
  phase_ids:        [{key, id}, ...]          # declared order
  relation_ids:     [id, ...]                 # declared order
  # phase-entry-design-v1:
  phase_id
  roadmap_id
  work_ids:         [{key, id}, ...]          # declared order of normal Works
  integration_work_id
  confirmation_work_id                        # id or null
  roadmap_relation_ids: [id, ...]             # registration order
  related_relation_ids: [id, ...]             # registration order
  canonical_first_work_id                     # id or null
```

Every list holds scalars or mappings: the canonical Review serializer does not nest sequences (`yamlish.py:133`).

### 16.2 Reading and validation

**Frozen.**

- Version 2 is valid only for the two P2 kinds, and a P2 kind is valid only in version 2. Version 1 with a P2 kind is `review_record_invalid`.
- Exact field sets; exact per-kind `persisted_result` fields. IDs, digests, full commit IDs and full branch refs are checked for form.
- `target_identity == roadmap_id` (RoadmapPlan) or `phase_id` (PhaseEntryDesign), and `adapter_identity` is the kind's.
- Lists are free of duplicates.
- The P1 Receipt binding (`RECEIPT_CONSUMPTION_BINDING`) applies unchanged.
- A Consumption of a superseded Receipt is a problem, as in P1.
- The v1 reader, its Work binding rule and every v1 record are unchanged.

### 16.3 Uniqueness (Frozen P1 R4 §1, §7)

**Frozen.** `ReviewStore` indexes, each a refusal (`review_consumption_conflict`):

- Receipt → at most one Consumption: the P1 index, now over v1 and v2.
- `persisted_result.registration_commit` → at most one Planning Consumption.
- `(review_kind, target_identity)` → at most one Planning Consumption.

This is "Receipt-based plus kind-specific semantic persisted-result binding" (R4 §7). No planning Consumption carries or invents a Work terminal event.

### 16.4 No self-reference

The Consumption names Kp (and its parent), which are ancestors of the commit that stores it, never Km itself. Receipts carry no commit SHA (P1 unchanged).

## 17. Ordering and authorization states

**Frozen.**

```text
seal generation + Receipt committed      -> ISSUED
use check passes                         -> VALID (evaluated once, before the first registration stage is recorded)
registration applied, Kp committed       -> (registration exists locally; Receipt still unconsumed)
C-2(Kp) passes, Consumption recorded     -> (durable persisted proof checkpoint)
Km committed                             -> CONSUMED
C-2(Km) recorded (publication_proof)     -> SUCCESSFULLY USED
destination holds Km                     -> PUBLISHED   (remote-less Projects complete after SUCCESSFULLY USED)
```

```text
Receipt  !=  Consumption  !=  registration commit (Kp)  !=  publication
```

**Use check** (right before the first registration stage is recorded):

1. the Run's chain validates, and its latest generation is generation 3, `sealed_authorized`, issuing exactly the reserved Receipt;
2. the Receipt reads back canonical and bound to that generation (P1 binding);
3. no supersession record names it, and no Consumption exists for it;
4. `operation_identity`, `target_identity`, `review_kind` and `authorized_operation_stage` equal the recomputed ones, and the Run is the planning mutation's reservation;
5. Candidate, Context and Policy are current (§13);
6. the binding holds;
7. no registration path differs from HEAD (`gitcmd.changed_against_head`): a change made after the freeze would otherwise be taken into the registration's own writes.

Failures of 1–4 → `ReconcileRequired` (reason `review_receipt_invalid`). A failure of 5 → terminal `stale`. A failure of 6 → `ReconcileRequired`. A failure of 7 → `StopError` code `dirty_overlap`; nothing is written, the planning mutation stays pending, and once the person commits or discards the change the same request continues.

Answers (task §10):

- **Can registration be locally committed before Consumption?** Yes: Kp precedes it.
- **What prevents that commit from being treated as successfully authorized before persisted proof?**
  - "successfully used" exists only as a committed, proven Consumption binding exactly Kp (Km + `publication_proof`);
  - the planning mutation records no push before C-2(Km);
  - the planning commit primitive runs no hook, so nothing Workline starts publishes Kp;
  - Review metadata is never lifecycle truth (§22), so no reader of lifecycle treats anything as authorized;
  - the operation returns `registered` only after `complete()`.
- **When is Consumption written?** After C-2(Kp) passes, as stage `review-consumption`.
- **Which commit stores it?** Km, a commit-only metadata commit made on top of Kp.
- **Does Consumption refer to an earlier registration commit?** Yes: `persisted_result.registration_commit` = Kp.
- **What authorizes the metadata-only commit?** The P2 metadata-commit rule (§18.3): Km carries exactly one OperationMetadataProjection path, admitted by the exact deterministic metadata proof C-2(Km), not by a Review. The Receipt authorized Kp; Km records that use.
- **How is recursion terminated?** OperationMetadataProjection is never normative (`projections.normative()`, Candidate 7 §4.3), so it is outside what Review authorizes. Km is proven, never reviewed, and a Km mismatch is `reconcile_required`, never a re-review.
- **When does push become permitted?** Once `publication_proof` is recorded and a re-run of C-2(Km) right before recording the push stage passes. At apply time the mutation-level validator re-checks the binding (§18.4).
- **What if persisted proof fails after the local registration commit?** §15.5.
- **What if Consumption write succeeds but its publication does not?** The planning mutation stays pending with Km local. The Receipt counts as consumed locally, and the destination holds no part of Kp or Km. A retry re-runs C-2(Km) when the note is missing, then records or applies the push under the live push classification (`=`, `*`, ` `, `!`). A destination that holds another history is `reconcile_required`, never forced. No second Consumption can be written (reserved ID + §16.3).
- **What if the registration commit is accidentally published before Consumption?** Only another subject can do that: Workline records no push before C-2(Km). Kp is then at the destination without Km. The resume continues unchanged — C-2(Kp) if not yet recorded, Consumption, Km, C-2(Km), push of Km — and the push fast-forwards the destination from Kp or from any subsequent commit (classified as live). If C-2(Kp) fails, §15.5 applies.
- **Retry / resume in each case:** §21.

No reset, rebase, amend or deletion of a commit occurs anywhere.

## 18. P2 planning publication contract (C-1)

### 18.1 Shape

**Frozen.** `review-v1-planning-publication-v1`:

```text
Kp commit-only  ->  C-2(Kp) = recorded Consumption  ->  Km commit-only  ->  C-2(Km) = publication_proof note
                ->  push-only stage publishing exact Km
```

One push per planning operation. It publishes Km and its history: Kp, the Run's generation commits, and base history. This is not the current-combined shape (Frozen P1 R5 §12.1), and it is not the Work-terminal `review-v1-split-v1` contract (R5 §12.2, with its ReviewValidity bindings). It is a separately named P2 contract.

### 18.2 Metadata proof over Km — C-2(Km)

**Frozen.** Contract `review-v1-planning-proof-v1`. Any failure → `ReconcileRequired` (reason `review_metadata_commit_mismatch`), no push, Km stays local:

| # | condition |
| --- | --- |
| M1 | Km is the planning mutation's own commit (recorded `applied` with `commit_id`); Km has exactly one parent Q; Q is Kp or descends from Kp, and `gitcmd.commits_touching(Kp, Q, planning-owned paths) == []` |
| M2 | HEAD on `review_binding.branch`; that branch holds Km |
| M3 | `diff-tree` of Q → Km is exactly one entry: the Consumption path, status `A`, mode `100644`, blob bytes == the recorded `create_file` content |
| M4 | Km's tree holds every Run record (snapshot, task input, gates 1–3, Receipt) and the Consumption with mode `100644` and bytes == their canonical bytes as `ReviewStore` reads them, and every registration path with the same blob ID as in Kp |
| M5 | the Consumption reads back (v2 reader), binds the Receipt, and its `registration_commit` == Kp |

On PASS the planning mutation records the note `publication_proof = {contract: review-v1-planning-proof-v1, registration_commit: Kp, metadata_commit: Km, consumption_id}`.

### 18.3 The metadata-commit rule (Km)

**Frozen** (P2-native; not the P3 Class-A K2 rule):

| item | rule |
| --- | --- |
| allowed contents | exactly one added path `.workline/review/consumptions/<consumption_id>.yaml`, mode `100644`, bytes = the canonical bytes of the recorded Planning Consumption |
| prohibited contents | any other path: a domain entity, relation, event, `project.yaml`, derivation, any other Review record, anything outside `.workline/`; any modification or deletion |
| authorization | the recorded Receipt → Consumption binding plus M1–M5; no Review |
| why no recursive Review | Km changes one OperationMetadataProjection path, which is never normative; Km is proven by exact projection, never reviewed |
| deterministic metadata projection | `{added: [(consumption path, 100644, canonical bytes)]}` computed from the recorded effect |
| extra domain change | refused by M3 before any push |
| Kp binding | `persisted_result.registration_commit` + M1 ancestry + `publication_proof` |
| publication proves Kp and Km | the push stage exists only after `publication_proof` binds both, and the validator re-checks them at apply (§18.4) |

### 18.4 The push stage and its validator

**Frozen.** Stage `review-publication`, recorded only when the Project has a verified push destination, after `publication_proof` and after M1–M5 are re-run. It holds exactly one effect: `git_push` with payload `{remote, branch, locator, commit: <Km full ID>}` (the live three keys plus `commit`).

The mutation-level validator (`_recorded_publication`, planning branch) names the commit only when all hold:

- the discriminator selects the planning contract (§18.5);
- the push is the only effect of its stage and the last effect of the record;
- `payload.commit` is a full commit ID, equal to `publication_proof.metadata_commit`;
- the effect right before the push (by position and `seq`) is a `git_commit` that is the only effect of its own stage, recorded `applied` with `commit_id == payload.commit`, naming `refs/heads/<payload.branch>`;
- `publication_proof.registration_commit` equals the `commit_id` of the recorded, applied `review-registration-commit` effect;
- Km has one parent, and that parent descends from Kp;
- `gitcmd.commit_changes(Km)` ⊆ `{Consumption path}`;
- the branch holds Km.

Otherwise it names nothing, and the push is refused (`reconcile_required`). Classification and push are live and unchanged: a dry run of the exact refspec `<Km>:refs/heads/<branch>`, `=` published, `*` / ` ` unpublished, `!` a read-only destination read; never forced, never a branch tip.

### 18.5 Discriminator

**Frozen.** Selection is read from the durable invocation only, never from stage shape, content or Review files (Frozen P1 R5 §12.3.2):

| durable invocation | publication rule |
| --- | --- |
| no `review_contract`, no `publication_contract`, operation not `review-generation` | current-combined: the live `_recorded_publication`, unchanged (R5 §12.3.1 case A) |
| `review_contract == review-v1-planning-v1` and `publication_contract == review-v1-planning-publication-v1` and operation in {`roadmap-create`, `phase-entry`} | planning publication (§18.4); a combined commit + push pair in such a mutation is refused |
| operation `review-generation` | publishes nothing: a recorded `git_push` is refused, and P2 never records one there |
| any other presence, value or combination | fail closed (`reconcile_required`), never current-combined |

Legacy mutations carry no marker and get exactly the live rule. R5's `review-v1-split-v1` value is not recognized by P2; P3 adds it for START under R5.

### 18.6 Authority for the shape

`rules/git` Push destination currently says a push is the last effect of its Git stage, right after that stage's only commit. The planning shape needs the amendment of §26.1. Until the implementation lands, no planning publication exists.

## 19. Terminal review outcomes

### 19.1 Not authorized

**Frozen.** The Run's latest generation is 2 with settled tasks, and some task is `failed` or there are unresolved obligations.

| question | answer |
| --- | --- |
| durable Review records | candidate snapshot, task input, gates 1 and 2: committed locally by generation mutations 1 and 2 |
| Receipt | none (no seal) |
| Consumption | none |
| registration | none: no Roadmap, Phase, Work or relation is written; the reserved domain IDs are never used |
| Review commits published | not by this operation; they stay local and reach the destination as base history of the next push from that branch (`rules/git` Push destination) |
| planning mutation | `complete()` with no effect recorded (its record follows the live retention rule) |
| result | `ReviewedPlanningResult(status="not_authorized", registration=None, receipt_id=None, consumption_id=None, findings=<the report's findings>)` |
| corrected plan or design | a fresh call: a new planning mutation, new reserved IDs, a fresh Candidate, a new Run. For Phase entry the Phase is still unexpanded, so the call is accepted |
| reserved domain IDs | never reused |
| retry of the identical request | a new Run and a new review; P2 does not remember the refusal |
| crash between the settlement and `complete()` | the next run recomputes "not authorized" from the chain and completes |

The Project is not blocked: the pending planning mutation is gone, and the immutable Review history stays.

### 19.2 Stale

**Frozen.** Detected by §13 before the first registration stage is recorded. The planning mutation completes without registration, and no Receipt is consumed or superseded (it can never be consumed, since its Candidate binds this mutation's reservations). The result is `ReviewedPlanningResult(status="stale", ...)`, and a fresh call is a fresh Candidate.

### 19.3 Result type

**Frozen.** In `workline.roadmap_review`; `workline.roadmap` imports it inside the review-v1 branch:

```python
@dataclass(frozen=True)
class ReviewedPlanningResult:
    status: str                    # "registered" | "not_authorized" | "stale"
    operation: str                 # "roadmap-create" | "phase-entry"
    mutation_id: str               # the planning mutation
    review_run_id: str
    receipt_id: str | None         # set when a Receipt exists
    consumption_id: str | None     # set for "registered"
    registration: RoadmapResult | PhaseEntryResult | None   # set for "registered"
    findings: tuple[PlanningReviewFinding, ...]             # the settled report's findings when available
    detail: str
```

On `registered`, `registration.head` is Km. `PhaseEntryResult.entry_work_id` is the reviewed canonical first Work, which equals the explicit entry when one was given.

## 20. Semantic round-trip adapters

**Frozen.** Two implementations of the P1 `PersistedProjectionAdapter` protocol (`review/adapter.py`) live in `workline.roadmap_review` (Roadmap-owned). They reuse the canonical renderers and registration helpers:

- the Roadmap-file rendering of `_create_roadmap`, extracted as a pure function with no behaviour change;
- `phase_create.decide_phases`;
- `create._registration_effects`, `_allocated_displays` and `_resolve_roadmap_relations`, reused, or extracted as pure functions with no behaviour change.

They read only through `ProjectView`, `Entity.name`, `Entity.section`, `Entity.meta` and the `Relation` records. They never reimplement Roadmap or CREATE semantics.

| responsibility | Roadmap adapter (`roadmap-plan-adapter-v1`) | Phase-entry adapter (`phase-entry-design-adapter-v1`) |
| --- | --- | --- |
| `adapter_identity` / `loader_identity` | §6.2 / §8.1 | same |
| `normalize_candidate` | §7.2 content as `Projection(reviewed_artifact, roadmap-plan-projection-v1)` | §7.3 content as `Projection(reviewed_artifact, phase-entry-design-projection-v1)` |
| `project_expected` | the expected effects: at the freeze from the renderers (§7.6), at the proof from the recorded registration effects (the displays decided under the lock, Frozen P1 R8 §11); as a `ProjectionSet` of the reviewed artifact and an authorized transition `{entities: [{path, sha256}], relations: [records], ledgers: [{path, wrote}]}` | same, three stages |
| reserved IDs | `ReservedIds`: roadmap, `key → Phase ID`, `index → relation ID` | `key → Work ID`, integration, confirmation, relation and Related IDs |
| expected scope | the registration paths (§14.1) | same |
| persisted scope | the Kp delta path set (P3) | same |
| `load_persisted` | the Roadmap by ID, Phases by reserved ID in declared order, relations by reserved ID in declared order; a missing one is a mismatch | Works by reserved ID; Related and roadmap relations by reserved ID; each Work's `phase_id`, `origin`, `work_kind` and `confirmation_target` |
| `normalize_persisted` | §7.2 shape from `Entity.name` / `Entity.section`; a relation with extra fields is a mismatch | §7.3 shape; `condition` from `Relation.extra`, any other extra field is a mismatch; `canonical_first_work` from `startable_works` + `planned_next_preference` on the loaded view, mapped back to its key |
| committed result loading | §15.4 | §15.4 |
| equality | projection identity + P3–P10 | same + P9 |

The same `normalize_persisted` runs at three points with three names: the representability check (§7.6, on the projection), the working-tree round trip (§15.1 step 2), and the persisted proof (§15.3, over the committed result).

## 21. Crash and recovery matrix

Terms (reconnaissance §12):

- **resume**: the same pending mutation continues from its record;
- **replay**: recorded effects are classified again and only unapplied ones are applied;
- **retry**: an external action is repeated under the same identity (the same task, the same exact push);
- **reconcile**: STOP with the record untouched;
- **fresh Candidate**: a new planning mutation and a new Run;
- **terminal**: not authorized or stale (§19).

Baseline conditions for the rows: the runtime record is intact, HEAD is on the bound branch, and nobody changed a written path. The variants follow the table.

| # | window | behaviour of the next same-request run |
| --- | --- | --- |
| 1 | planning mutation begun, domain IDs reserved, freeze incomplete | resume; freeze recomputed deterministically (same reservations). A STOP here abandons the planning mutation (§12) |
| 2 | Run / task / Receipt / Consumption IDs reserved, `review_binding` noted, no generation mutation yet | resume; generation 1 starts; a STOP here still abandons (no generation mutation has started) |
| 3 | generation 1 begun, no effect recorded | resume planning; the pending generation mutation is abandoned; N = 1 computed again; a new generation 1 starts (no fork: nothing physical exists) |
| 4 | Candidate snapshot / task input / gate 1 recorded, some applied | resume generation 1; replay (`create_file` applied_matching skipped, unapplied created, mismatch → reconcile); commit; persistence proof; complete |
| 5 | generation 1 committed, not completed | resume generation 1: commit matched by its ID; persistence proof; complete |
| 6 | generation 1 complete, reviewer not launched | launch checks (§10.3); launch the task from the stored TaskInput |
| 7 | reviewer launched; process died, callback raised or returned invalid | retry: the same `task_id` launched again; nothing was settled; an in-memory result is lost |
| 8 | reviewer returned, runtime report copy written, generation 2 not begun | retry: the reviewer is launched again (the runtime copy is never settlement material) |
| 9 | generation 2 recorded, not applied / not committed | resume generation 2; replay; the reviewer is not called again |
| 10 | generation 2 complete | authorized → generation 3 (seal) starts with the Receipt ID reserved at the freeze; not authorized → terminal `not_authorized` |
| 11 | generation 3 + Receipt partially applied | resume generation 3; replay the remaining `create_file`; commit; persistence proof; complete (Frozen P1 R3 §7) |
| 12 | Receipt fully valid, before the use check | use check; then the registration |
| 13 | before Consumption (use check passed), registration stage not recorded | the use check runs again (it is not durable until the first registration stage is recorded); a registration path changed since the freeze stops it with `dirty_overlap`, nothing written |
| 14 | registration effects partially applied | resume; `_open` projects and replays (live `refuse_invalid_phase_writes` / `refuse_invalid_work_writes` first); the subsequent stages continue from their records |
| 15 | registration fully applied, working-tree round trip not run, Kp not recorded | resume; the round trip runs; Kp recorded |
| 16 | Kp recorded, not made | resume; `_open` replay makes Kp with the recorded primitive (live independent-advancement rule applies) |
| 17 | Kp made, `commit_id` saved, C-2(Kp) not run | proof runs over the recorded Kp |
| 18 | Kp made, `commit_id` not saved | reconcile (`review_commit_unowned`, §15.2) |
| 19 | C-2(Kp) failed | reconcile (§15.5); every retry repeats the same proof |
| 20 | C-2(Kp) passed, Consumption not recorded | the proof runs again (the Consumption record is its durable checkpoint); Consumption recorded |
| 21 | Consumption recorded, not applied (a single immutable create: absent or exact) | `_open` replay creates it; exact bytes already present → matching; anything else → reconcile |
| 22 | Consumption applied, Km not recorded / not made | Km recorded / made as rows 16–18 |
| 23 | Km made, C-2(Km) not run or failed | proof runs; failure → reconcile, no push |
| 24 | C-2(Km) passed, `publication_proof` not noted | proof runs again; note recorded |
| 25 | note recorded, push stage not recorded | C-2(Km) re-run; push stage recorded |
| 26 | push stage recorded, not applied | `_open` replay: planning validator (§18.4), dry run, exact push |
| 27 | pushed, `applied` not saved | dry run `=` → matching |
| 28 | published, before `complete()` | everything matches; structure postcheck; complete |
| 29 | after `complete()` | record removed per the live rule; the same request again → a new planning mutation, fresh Candidate, new Run (Roadmap: a second Roadmap, as in legacy; Phase entry: `phase_already_expanded`) |
| 30 | runtime record lost at any window | fresh Candidate; the old Run is a legal orphan. Local commits already made (generation commits, Kp, Km) stay in history, and Workline removes none. A Kp without a published Km is a registration without a Consumption (§15.5). The same request run again: a Roadmap creation registers a second Roadmap (the legacy semantics of a completed creation); a Phase entry meets `phase_already_expanded` |
| 31 | fresh clone | as row 30; the Run's records are in history only if a push carried them |
| 32 | branch changed at any window | reconcile (binding §11.5, live `_require_decided_branch` / `_require_finalized_branch`); checking out the bound branch continues |
| 33 | remote moved | live push classification: destination holds Km → matching; another history → reconcile, never forced |
| 34 | canonical Review record tampered | reconcile: `create_file` applied_mismatch, `ReviewStore` refusal, or a blob / M4 mismatch; never re-reviewed or repaired |
| 35 | pre-existing dirty path | refused at the freeze with `dirty_overlap`, planning abandoned, nothing written (§14.2); a change after the freeze on a written path → live own-bytes reconcile |
| 36 | POSIX with review-v1 | `review_create_unsupported` before the lock; nothing exists |
| 37 | not authorized decided | terminal; after a crash before `complete()`, recomputed from the chain |
| 38 | stale detected | terminal (§19.2) |

Variants at any row: a different request or design → `reconcile_required` (live); a legacy invocation against a review-v1 record, or the reverse → `reconcile_required` (§5.3); a pending generation mutation bound to another planning mutation → reconcile (§11.8); structure changed by an independent operation while pending → the live projected refusal (`postcheck_failed`) before replay; the parent Roadmap held while a Phase entry is pending → the live Phase-entry precheck STOP, continued after resume.

Nothing in the matrix is the P3 Work-terminal recovery contract.

## 22. Lifecycle separation

**Frozen** invariants:

1. `state.py`, `ProjectView`, `validate_structure`, Phase selection, Work selection, startability and Roadmap progression never read a Receipt, Consumption, gate generation, snapshot or task input. `state.py` stays byte-identical, and the existing pin `test_review_authority` (no "review" in `state.py`) holds.
2. A review-v1 planning operation reads only its own Run's records, as the authorization of its own planning mutation.
3. There is no cross-operation Review precondition. For example, "Phase entry requires the Roadmap to possess Receipt X" is prohibited: a PhaseEntryDesign Review reviews its own design, whatever the Roadmap's history.
4. The R9 canonical first Work is computed from `ProjectView`, never from a Review record.
5. A broken Review record stops a review-v1 planning operation that relies on it. It cannot reinterpret lifecycle history, because nothing that derives lifecycle reads it.
6. The committed-result loader (§15.4) feeds only the proofs; its `ProjectView` is never used to decide lifecycle or progression.
7. A review-v1 Roadmap creation or Phase entry writes no event, so the lifecycle it leaves is identical to a legacy call's (Measured, reconnaissance probes 2, 5, 8).

P3 stays inactive: no activation record, no Work-terminal Consumption, no START change.

## 23. P1 seam disposition

| seam | frozen P1 text | disposition |
| --- | --- | --- |
| C-1 publication discriminator scope | R5 §12.3.1: Review-v1 durable metadata without `publication_contract` fails closed; R5 §12 enumerates two shapes for the operations it governs | **CLOSED BY P2 CONTRACT.** The planning mutation's durable invocation carries `publication_contract = review-v1-planning-publication-v1` from `begin` (R5-IMPL-2 satisfied). P2 implements the discriminator's first branches (§18.5): legacy → current-combined unchanged, planning → planning publication, generation mutations never publish, anything else fails closed. R5 §12.1 / §12.2 are unchanged; R5's `review-v1-split-v1` remains P3's |
| C-2 planning Consumption binding | R8 §8, R9 §9 | **CLOSED BY P2 CONTRACT.** Planning Consumption v2 with `persisted_result` (§16), written after C-2(Kp), stored in Km, binding Kp without self-reference |
| C-3 persisted proof / publication ordering | R8 §5–§9, R9 §7–§10, Candidate 7 §4.4 / §11 | **CLOSED BY P2 CONTRACT.** Direction A (§15, §17, §18) |
| C-4 generation mutation / same-run serialization | R2 §4, R3 §2, §8 | **CLOSED BY P2 CONTRACT.** Direction A (§11), R2/R3 and the helper unchanged; abandonment gap closed (§12) |
| C-5 owning mutation invocation binding | R3 §9 | **CLOSED BY P2 CONTRACT.** The planning invocation keeps the request identity and adds the two static markers (§5.2). Run / task / Receipt / Consumption IDs are planning reservations (§6.3). Each generation invocation binds run, generation, transition, Candidate / Context / Policy, obligation digest and Receipt ID (§11.2). The planning mutation binds the Receipt, Candidate, Context and obligation through its recorded Consumption effect and `persisted_result`. `proof_phase` (Candidate 6 §11) is the planning mutation's recorded stage position plus the `publication_proof` note, re-checked before recording the registration and the push |
| C-6 runtime-loss same-task / Run rerun | R2 §5, R3 §4 | **CLOSED BY P2 CONTRACT.** P2 never continues a Run after runtime loss: a fresh Candidate and a new Run are required (§12, §21 rows 30–31). A task of an orphaned Run is never rerun, and never under a substitute ID, so R2 §5 / R3 §4 hold vacuously. The orphan Run stays valid |

Every seam is closed.

## 24. Consistency with frozen P1 contracts and Candidate 7

| frozen text | how P2 satisfies it |
| --- | --- |
| R1 §2–§8 layout, immutable create | no new directory. Planning Consumption v2 in `consumptions/`; runtime material in `.workline/runtime/review/` (proofs, reports, no-hooks), allowed by R1 §3 |
| R1 §4 "Git persistence proof separately proves the committed path reproduces those bytes" | blob checks at every generation commit, M4, P4 |
| R1 §13 committability | `gate.require_committable` at the freeze and per writer |
| R2 §2–§5 | keys §6.2; reservations §6.3; no substitute task ID |
| R3 §1 ownership | Roadmap mutation owner writes every record (§11.1) |
| R3 §2 serialization | §11.3, §11.8, helper unchanged |
| R3 §3–§4 launch after local persistence | §10.3 |
| R3 §7 seal + Receipt one stage | §11.6 |
| R3 §8 invalidation | not used: stale is terminal, so no old Receipt proceeds |
| R3 §9 invocation binding | C-5 |
| R3 §10 local Git persistence boundary | §11.6; remote-less valid |
| R3 §11, Candidate 7 §2 no second controller | §22 |
| R4 §1, §7 uniqueness | §16.3 |
| R5 §5–§6 signing disabled, hooks suppressed as bound semantics | §15.2, Context `git_persistence` |
| R5 §12 publication shapes | §18: current-combined unchanged; planning shape separately named and selected by durable metadata, never by shape. R5 §12's "exactly two" enumerates the contracts of the operations R5 governs; P2 adds one R5 did not govern and changes none of R5's |
| R8 §2–§11 | §7.2, §15.3, §16, §20 |
| R9 §2–§11 (as repaired) | §7.3, §7.7, §15.3 P9, §16, §20 |
| R11 git_state, completeness | the primitive identity is bound; Evidence completeness `unknown`, never reused |
| R12 §3, §8, §11, §13, §14 | test contract §28 |
| Candidate 7 §4.4 exact union | Kp proof: ReviewedArtifact + AuthorizedTransition + scope; Km proof: OperationMetadata + scope |
| Candidate 7 §11 local commit → exact proof → re-read | §15 |

No frozen P1 document needs repair for this contract.

## 25. Public API compatibility

**Frozen.**

| surface | P2 |
| --- | --- |
| `create_roadmap` | new keyword-only `review=None`; legacy unchanged; review-v1 returns `ReviewedPlanningResult` |
| `enter_phase` | same |
| `RoadmapResult`, `PhaseEntryResult`, `OperationResult` | unchanged |
| new result type | `ReviewedPlanningResult` (`workline.roadmap_review`) |
| `Mutation` public methods | unchanged set (pin `test_project_start_recovery.py:978-991`) |
| `MutationController` public methods | unchanged set (same pin) |
| `EFFECT_KINDS`, `INTENT_VERSION` | unchanged (pins `test_decision_branch_binding.py:676`, `test_cancel_decision_resume.py:367`) |
| effect payloads | `git_commit` gains the durable `mode` field (§15.2); a planning `git_push` gains `commit` (§18.4); `validate_effect` accepts `mode` only as `review-v1-planning-local-v1` and `commit` only as a full commit ID; legacy payloads are unchanged |
| `register_phases`, `register_works` | unchanged signatures, stage names and keys; the review-v1 path pre-reserves under their keys |
| `rm.validate_structure` call order in Phase entry | unchanged: the review-v1 checks call `workline.validate` from `workline.roadmap_review`, never through `rm.validate_structure` (pin `test_phase_entry_contract.py:529-555`) |
| `OPERATION_LEDGERS` / `_ledgers` | unchanged: generation mutations build their scope from the helper, never through `_ledgers` (pin `test_declared_write_scope.py:162-191`) |
| `ROADMAP_REQUEST_VERSION`, `DESIGN_IDENTITY_VERSION` | unchanged |
| `project_operation` signature | unchanged (pin `test_self_hosting_guard.py:603`) |
| entry parameters | no parameter name contains `foreign` or `allow` (pin `test_project_context.py:478`) |
| Review P1 record classes | unchanged; Consumption gains version 2 alongside version 1 |

No `Mutation` or `MutationController` method is added. New behaviour lives in module-level helpers (`gitops`, `gitcmd`), the new modules, and private functions of `mutation.py`.

## 26. Authority changes the implementation makes

When the implementation lands, it changes canonical authority as follows. Under `rules/human-confirmation` this is a Workline common-rule change, and the approval of this contract is what it rests on (reconnaissance Q17).

### 26.1 `registry.md` `rules/git`

1. Operation Owner: a review-v1 planning operation owns one planning mutation and the generation mutations it starts; resume order and conflicts as §11.8 and §11.12.
2. Commit / push: review-v1 planning commits use the contained planning commit primitive (§15.2). Review-v1 planning refuses `dirty_overlap` on its planning-owned paths before its first Review record (§14.2).
3. Push destination: for a mutation whose durable invocation names `review-v1-planning-publication-v1`, a push is its own stage publishing the exact commit named in its payload, proven by the recorded planning proof (§18.4). The current-combined rule is unchanged for every other mutation.
4. Scope: a review-v1 planning mutation also declares the Review record path it writes (the Consumption path), beside its static ledger set.
5. Success on publication: a review-v1 planning operation succeeds only once its registration is published (remote-less: once C-2(Km) is recorded); one that ends `not_authorized` or `stale` registers nothing, publishes nothing, and leaves its generation commits as local history that the next push from that branch carries.

### 26.2 `skills/roadmap`

- the opt-in (§5);
- the review-v1 flows of Roadmap creation and Phase entry (§14.4, §15.1);
- the R9 canonical self-selection rule, owned here (§7.7);
- the terminal outcomes and the fresh-Candidate rule (§12, §19);
- the operation binding (§11.5).

### 26.3 `skills/review`

- the planning kinds and identities (§6);
- the static policy record, verbatim (§9);
- the reviewer interface (§10);
- adjudication (§10.6);
- Planning Consumption v2 and uniqueness (§16);
- the planning publication contract (§18);
- the P2 scope of "適用範囲". Work terminal gating stays NOT ACTIVATED.

`skills/phase-create` and `skills/create` are unchanged: their registration cores are called exactly as today.

## 27. Implementation surface map

| file | purpose | contract sections | tests (§28) |
| --- | --- | --- | --- |
| `src/workline/review/planning.py` (new) | identifiers; `PlanningReview`, task, report and finding types; record builders (Candidate, Context, policy, request envelope, report, adjudication, obligations, coverage, report set, evidence); report validation; loader identity; authority digests | §5.1, §6, §7.1, §8, §9, §10 | A, C, D |
| `src/workline/review/records.py` | Planning Consumption v2 (reader and builder) beside v1 | §16.1–§16.2 | F |
| `src/workline/review/store.py` | v2 reading; registration-commit and target indexes | §16.3 | F |
| `src/workline/review/validate.py` | v2 validation, planning binding, uniqueness indexes | §16.2–§16.3 | F, H |
| `src/workline/review/paths.py` | runtime subpaths `proofs/`, `reports/`, `no-hooks/` | §10.5, §15.2, §15.4 | E |
| `src/workline/roadmap_review.py` (new, Roadmap-owned) | the review-v1 flow: freeze, generation mutations, reviewer call, use check, registration hand-off, Kp / Km, proofs, Consumption, publication, terminal outcomes; both adapters; `ReviewedPlanningResult` | §7, §11–§21 | A–I |
| `src/workline/committed_view.py` (new) | committed-result loader: materialization from raw blobs and `ProjectView.load`; delta reading | §15.3–§15.4 | E |
| `src/workline/roadmap.py` | `review=` keyword; marker check at the entry (§5.3); the registration of `_create_roadmap` / `_expand_phase` separated from the legacy `_finalize` without changing legacy behaviour; review-v1 branch | §5, §15.1 | A, B, I |
| `src/workline/gitcmd.py` | a bytes runner; `tree_entries`, `read_blob`, `commit_delta`, `check_attributes`; contained `add` / `commit` | §14.3, §15.2–§15.4 | E, G |
| `src/workline/gitops.py` | `review_commit_effect`, `review_publication_effect`, attribute preflight helper | §14.3, §15.2, §18.4 | E, G |
| `src/workline/mutation.py` (private functions only) | discriminator + planning publication branch in `_recorded_publication` (invocation threaded through `_classify_recorded` / `_publish`); `mode` in `apply_effect`; payload validation | §15.2, §18.4–§18.5 | G |
| `registry.md`, `.claude/skills/roadmap/SKILL.md`, `.claude/skills/review/SKILL.md` | authority text | §26 | C (policy pin) |
| `tests/test_review_planning_*.py` (new) | the test contract | §28 | — |

Expected not to change: `state.py` (no helper is needed), `store.py`, `validate.py` (`validate_structure`, `validate_project`), `start.py` and every START Work-terminal path, `create.py` and `phase_create.py` behaviour (at most a pure helper extracted with identical output), `ops.py`, `oplock.py`, `ids.py`, `implementation.py`, `cli.py` (Roadmap has no CLI), `review/gate.py`, `review/adapter.py`, `review/projections.py`, `review/closure.py`, `review/fsafe.py`, `review/serialize.py`, P3 activation code (none exists), and every unrelated operation.

## 28. Test contract

Frozen minimum. Every test runs on real Projects through `tests/helpers.py`, through production code paths. A happy path alone is insufficient (Frozen P1 R12 §14).

**A. Applicability**

- A legacy Roadmap creation and a legacy Phase entry are byte-for-byte unchanged: invocation, stages, commits, pushes and result. The existing suite passes unchanged.
- An explicit review-v1 Roadmap creation is gated; an explicit review-v1 Phase entry is gated.
- The opt-in cannot fall back to legacy: platform, Git transform, Context unavailable and reviewer failure each STOP, with no ungated registration.
- Both marker mismatch directions → reconcile with the record untouched (§5.3).
- An invalid `review` argument → `review_contract_invalid` with nothing written.
- POSIX, or a patched `immutable_create_supported() == False`, with review-v1 → `review_create_unsupported` before any lock or record. POSIX legacy is unchanged.

**B. Generation serialization**

- An uninterrupted run leaves three generation commits before Kp.
- A crash at every generation window (§21 rows 3–5, 9, 11) resumes correctly.
- A pending predecessor is resumed before N+1.
- A conflicting second owner (a pending generation mutation bound to another planning mutation) → reconcile.
- Two pending generation mutations → reconcile.
- A generation file created with its `applied` flag not saved → classified matching, no N+2.
- No fork and no skipped generation.
- The initial scope is exactly as §11.3, with no `extend_scope` on generation mutations.
- The dirty snapshot is taken at the start.
- The binding is enforced across mutations (branch switch between generation commits → reconcile).

**C. Authorization**

- The accepted → settled → sealed chain validates (`validate_project` clean).
- A seal with an unsettled task is refused (P1 invariant).
- An invalid Receipt (tampered, unbound) → reconcile at the use check.
- A superseded Receipt is refused (fixture).
- Not-authorized paths register nothing: HIGH, MID, `declined`, and a failed task.
- LOW findings do not block and are returned.
- The Skill policy block equals the code constant (canonical).
- Reviewer failures: a raised exception, an invalid report, and an identity mismatch.
- The same task ID is relaunched after a crash.
- A duplicate settlement through the P1 helper (the same report twice) is idempotent.

**D. Semantic projection**

- The Roadmap and Phase-entry round trips are exact at all three points.
- Every reader-loss input of reconnaissance §10.2 and a lone CR are refused before Review (`review_candidate_unrepresentable`).
- Every R9 case of §7.7.
- The declared base changes → stale.

**E. Persisted proof**

- Exact committed bytes and modes: a fixture changes a mode.
- Scope: an extra path, a missing path, and a ledger with an extra relation are each detected.
- The committed semantic reload uses the §15.4 loader.
- A Git transformation is detected. Two fixtures: an attribute (`filter`, `ident`, `working-tree-encoding`) refused by the preflight; and a transformation forced after the preflight, caught by P3 / P4.
- Proof failure prevents Consumption and publication.
- Hooks (`pre-commit`, `commit-msg`, `post-commit` attempting a push or a file change), `commit.gpgSign=true` with a signing program, and a non-default `core.hooksPath` → none runs (Frozen P1 R12 §8).
- Kp without a saved ID → reconcile.

**F. Consumption**

- The exact `persisted_result` binding for both kinds.
- One Receipt → at most one valid Consumption.
- A conflicting Consumption is refused (a second Consumption of the Receipt, of the registration commit, or of the target).
- A commit identity mismatch is refused (`registration_commit` ≠ Kp).
- A Candidate mismatch is refused (`authorized_candidate_hash` ≠ Receipt).
- An adapter identity mismatch is refused.
- A v1 Consumption with a P2 kind is invalid.
- v1 records are unchanged.

**G. Publication**

- Interruption at every commit, proof and publish boundary (§21 rows 16–28).
- No push before proof: no `git_push` exists in the record before `publication_proof`.
- A foreign commit is not an operation-owned commit: a byte-identical Kp or Km made by another subject is never published as the operation's own.
- Branch switch → reconcile. Rewritten history → reconcile.
- Remote advancement: fast-forward, destination ahead holding Km, and diverged → reconcile.
- The retry publishes exactly Km.
- Discriminator: legacy is unchanged; a combined pair in a planning mutation is refused; a push in a generation mutation is refused; unknown or partial markers fail closed; shape and content are never selectors.
- A remote-less Project completes without a push.

**H. Lifecycle**

- Review metadata does not alter lifecycle (gated vs. legacy end states equal).
- A tampered Review record does not reinterpret lifecycle: it stops only the gated operation relying on it.
- `state.py` is unchanged (pin).
- P3 stays inactive: no activation record, and START completion behaviour is unchanged.
- No cross-operation Review precondition: a legacy Phase entry on a review-v1-created Roadmap proceeds, and a review-v1 Phase entry on a legacy Roadmap proceeds.

**I. Dirty overlap**

- review-v1 refuses before any Review record or reviewer launch when a registration path, a Run record path or the Consumption path is dirty.
- A registration path changed after the freeze stops the use check with `dirty_overlap`, nothing written, the planning mutation pending; a resume after generation 1 never abandons it.
- The person's bytes are untouched.
- The planning mutation is abandoned.
- The legacy late `dirty_overlap` behaviour is unchanged.

## 29. Incidental live findings outside P2

1. **Review records under checkout line-ending conversion.** **Measured** (§31): with this machine's system `core.autocrlf=true`, a fresh clone checks out an LF-only Review record as CRLF while `git status` stays clean, and `serialize.parse_canonical` refuses CRLF (`review_record_noncanonical`). So in such a clone `validate_project` reports every committed Review record, and an accepted task cannot be reconstructed there. This is a P1 reader-boundary limitation (R1 §4 working-tree read), and P2 does not rely on it: runtime loss or a fresh clone requires a fresh Candidate (§12), P2 never reads an old Run's records in another clone, and every P2 proof reads committed blobs, not the working tree. It is recorded for a separate P1 decision and is not repaired here.
2. `gate.py:139` / `:149` print `record.get("id")` for pending generation mutations, which yields `None` (reconnaissance §6); message only.
3. The lone-CR stranding of legacy Roadmap creation and Phase entry (reconnaissance §17 item 1) remains in the legacy path; the review-v1 path refuses such input before Review (§7.6).
4. The late `dirty_overlap` of legacy Roadmap creation and Phase entry (BL-041 residual (4)) remains in the legacy path; review-v1 refuses early (§14.2).

## 30. Quality gates applied to this document

Searched, case-insensitively, for `TBD`, `TODO`, `maybe`, `either`, `alternative`, `open`, `later`, `implementation decides`, `could`, `option`:

Outside this section:

- `TBD`, `TODO`, `maybe`, `either`, `alternative`, `later`, `implementation decides`, `could`, `option`: no occurrence (substrings included);
- `open`: only as the P1 gate status literal `` `open` ``, the live function and method names `_open` / `MutationController.open`, and inside the task's own labels "Architecture reopen" / "not reopened". None marks an unresolved item.

Also verified: no unresolved A/B choice (C-3 and C-4 name Direction A with reasons); no implementation-defined identity (§6); every mutation owner specified (§11.1); Receipt / Consumption ordering specified (§17); commit / proof / push ordering specified (§15.1, §18); every recovery window specified (§21); no hidden HUMAN choice (§32); no P3 activation (§2, §22); no Review-as-lifecycle authority (§22).

## 31. Evidence

Probes are plain scripts (no pytest), run outside the repository against the clone's `src` (`PYTHONPATH`), each asserting that `workline` was imported from that tree. Environment: Windows 11, Git for Windows with system `core.autocrlf=true`.

| probe | question | result |
| --- | --- | --- |
| autocrlf clone | what does a fresh clone do to an LF-only Review record? | blob LF (`git cat-file blob`); clone working tree CRLF; `git status` clean |
| hook suppression | does `-c core.hooksPath=<empty or absent dir>` suppress repository hooks for `git commit --only`? | default: a failing `pre-commit` hook ran and refused the commit; with an empty directory and with an absent directory: no hook ran, the commit was made |
| `committed_reload_probe.py` | does the production `ProjectView` read a commit's canonical files materialized from raw blobs exactly as it reads the working tree? | live Roadmap creation + Phase entry: 9 canonical files, all `100644`, committed reading == working-tree reading, `validate_structure` clean |
| reconnaissance probes 1–8 | accepted evidence (reconnaissance §18) | Direction A mechanics (probe 8), pre-reservation (probes 2, 5), reader loss (probe 1), projection equality (probe 4), lifecycle neutrality (probes 2, 5, 8) |

Kept outside the repository with the reconnaissance evidence: `D:\AIproject\workline-evidence\cases\`.

## 32. HUMAN, architecture, checkpoint

HUMAN: **None.** HUMAN-1 is resolved (A). Every choice made here is an engineering choice bounded by live code and frozen text, and each has its reason stated in its section.

Architecture: Candidate 7 **RETAIN**; architecture reopen **No**; architecture blocker **None**. C-2, C-3 and C-4 close inside Candidate 7's responsibility split: Review stays a subordinate gate, the Roadmap operation stays the only top-level owner, and lifecycle stays event-derived.

```text
Contract baseline:              cdb152312006f6ac25533962d942ed77e2d98bd4
P1 accepted checkpoint:         b78be1ccd778ceb2ecd97b90e2f71744bd1b3bc5
HUMAN-1:                        RESOLVED — A, per-invocation opt-in (review=PlanningReview)
C-1 .. C-6:                     CLOSED BY P2 CONTRACT
Generation contract:            Direction A — roadmap-owned generation mutations, R2/R3 unchanged
Persisted-proof contract:       Direction A — Kp -> C-2(Kp) -> Consumption v2 -> Km -> C-2(Km) -> push Km
No push before proof:           PASS
Lifecycle separation:           PASS
P2 Integration Contract:        FROZEN
P2 implementation:              NOT STARTED
P2 accepted for implementation: NO (pending independent contract review)
Candidate 7:                    RETAIN
Architecture reopen:            No
Architecture blocker:           None
HUMAN:                          None
P3:                             NOT STARTED
Status:                         READY_FOR_P2_CONTRACT_REVIEW
```
