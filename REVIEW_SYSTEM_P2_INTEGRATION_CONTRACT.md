# Review System P2 — Planning Review Gates: Integration Contract

Status: `CONTRACT FROZEN / ROUND 1 REPAIRED (P2-CONTRACT-001..004) / IMPLEMENTATION NOT STARTED / PENDING INDEPENDENT CONTRACT RE-REVIEW`

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
P2-CONTRACT-001 .. 004: CLOSED BY ROUND-1 REPAIR (§33); cross-finding pass §34
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
| round-1 repair baseline = contract under repair | `2f8771ae91df580453a0ebc026febe5c5a562cc0` — local `main`, `origin/main` and GitHub `refs/heads/main` verified equal, working tree clean; `src/`, `tests/`, Skills and `registry.md` still byte-identical to `b78be1c`; repaired in a fresh GitHub clone at `2f8771a`, and the repair changes this document only |

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

Not implemented or activated by P2: START Review Gate; Work Formal Review runtime; Work completion Review; review-v1 `work_completed`; Work-terminal activation (`activation/work-terminal-v1.yaml` stays absent); Work-terminal Consumption totality; the P3 result-commit publication contract (`review-v1-split-v1`); P3 Class A / B / C; P3 Review-validity closure; P3 HEAD-advancement reuse; P3 stale-generation Work blocking; P3 Work commit / proof / push; P4+ learning, repair and policy systems. The planning publication contract of §18 is P2-native and activates none of them. Its publication barrier (§18.7) applies to every Workline push, legacy ones included, and refuses nothing in a history that holds no review-v1 planning registration commit: it asks nothing of the operation that pushes, only that what it publishes carries no unproven review-v1 registration.

Ungated planning writers stay ungated (reconnaissance §3.7 / Q18): `add_phases`, Related maintenance, plan exclusion with replan, START derivations, direct CREATE.

## 3. Terms

| term | meaning |
| --- | --- |
| planning operation | one call of `create_roadmap` (lock operation `roadmap-create`) or `enter_phase` (lock operation `phase-entry`) made with `review=` (§5) |
| planning mutation | the mutation that operation resumes or begins at its entry: owner `"roadmap"`, invocation = the live invocation plus the two markers of §5.2 |
| generation mutation | a mutation the planning operation starts, under its own lock and owner, to write exactly one gate generation transition of its Review Run (§11) |
| Run | the Review Run the planning mutation reserved (§6) |
| Run records | the Run's candidate snapshot, task input, gate generations 1–3 and Receipt, and — when the Run is invalidated (§13.3) — gate generation 4 and the Supersession of its Receipt |
| registration stages | the live stages that register the plan: `roadmap`, `phases` (RoadmapPlan); `works`, `integration`, `confirmation` when the design declares one (PhaseEntryDesign) |
| registration paths | exactly the canonical paths the registration stages write: the new entity files and the ledgers they re-render (§14.1) |
| Kp | the registration commit: a commit-only stage of the planning mutation carrying exactly the registration paths |
| Km | the metadata commit: a commit-only stage of the planning mutation carrying exactly the planning Consumption |
| C-2(K) | the durable proof checkpoint for commit K (the term of Frozen P1 R5 §1.1) |
| planning-owned paths | registration paths + Run record paths + the planning Consumption path |
| freeze | the step of the planning operation that fixes the Candidate and every identity before the first Review record is written (§7, §14) |
| use check | the re-validation of the Receipt right before the first registration stage is recorded (§13, §17) |
| committed view of B | `ProjectView.load` over commit B's canonical Project files, materialized from raw blobs by the committed-result loader (§15.4) — never the working tree |
| `use_check_head` | the note recording HEAD's full commit ID at the last passing use check before the first registration stage (§17) |
| P | Kp's one parent: the `base_head` recorded in the Kp effect, on which Kp is made and nowhere else (§15.2, §15.6) |
| pre-Kp currency proof | the full currency re-proof on P right before Kp is recorded and right before a recorded Kp is replayed (§15.6) |
| registration commit | a commit that adds registration paths of a planning Run: Kp, or anyone's commit of those files (§18.7) |
| publication barrier | the rule that no Workline push publishes a history holding a registration commit without its proven Planning Consumption (§18.7) |
| checkout capability | the positive proof that Git reproduces canonical Review bytes in this repository and in a fresh clone (§14.5) |

## 4. Decision summary

| issue | frozen decision | section |
| --- | --- | --- |
| HUMAN-1 = A | keyword `review=PlanningReview(...)`; invocation markers `review_contract` / `publication_contract` | §5 |
| C-4 generation serialization | **Direction A**: every generation transition is its own `roadmap`-owned generation mutation, R2/R3 and the live helper unchanged | §11 |
| abandonment gap | the planning mutation is abandonable only before its first generation mutation starts; afterwards pending until a terminal outcome | §12 |
| C-3 persisted proof | **Direction A**: Kp commit-only → exact proof → canonical reload from the committed result → equality → Consumption → Km commit-only → exact proof → push-only publication of exact Km | §15, §18 |
| C-2 planning Consumption binding | `review-consumption` **version 2** (Planning Consumption) with a `persisted_result` binding; v1 unchanged | §16 |
| ordering | Receipt → use check (`use_check_head`) → registration → pre-Kp currency proof → Kp → C-2(Kp) → Consumption → Km → C-2(Km) → publication barrier → publication | §17 |
| C-1 publication discriminator | durable invocation markers select `review-v1-planning-publication-v1`; legacy is the unchanged current-combined rule | §18.5 |
| C-5 invocation binding | markers augment, never replace, the request identity; Run / task / Receipt / Consumption IDs are planning reservations; generation invocations bind run, generation, transition and every hash | §5.2, §11.2 |
| C-6 runtime-loss rerun | never: runtime loss requires a fresh Candidate and a new Run; the old Run is a legal orphan — and an unproven registration commit it left keeps the publication barrier until a person reconciles | §12, §21, §23 |
| staleness | before a Receipt: terminal `stale`, nothing written; after the Receipt and before the registration: generation 4 (`open`) + Supersession in one stage, then terminal `stale`; after the registration began: `ReconcileRequired`, never `stale`; no re-review inside the operation | §13 |
| publication barrier (P2-CONTRACT-001) | no Workline push of any operation publishes a history holding a planning registration commit that no proven Planning Consumption binds; computed from committed Git objects alone | §18.7 |
| registration base (P2-CONTRACT-003) | `use_check_head` noted at the use check; Kp made on exactly its recorded parent P (`base_exact`); P = `use_check_head`, or a descendant through commits that touch no planning-owned path, with full currency on P; C-2(Kp) proves full currency on P's committed view | §13, §15.2, §15.3, §15.6, §17 |
| checkout capability (P2-CONTRACT-004) | committed and effective attributes of Review paths must be exactly form L or form B; every existing Review record must read canonically; fail closed before the first Review record; P1 reader unchanged; legacy unchanged | §14.5, §14.6 |
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

The checkout capability (§14.5) and the readability of the existing Review namespace (§14.6) are the second applicability condition of an opted-in invocation. They read the repository's attributes and records, so they are checked under the lock at the freeze, before the first Review record: a failure is `review_checkout_unsafe`, `review_checkout_unknown` or `review_namespace_unreadable`, and the planning mutation is abandoned with nothing written. Legacy invocations check none of this and are unchanged.

An opted-in invocation never falls back to the legacy path: every inability of the gate — platform, checkout capability, Review namespace, Git persistence preflight, Context unavailable, reviewer failure, proof failure — is a STOP or a terminal review outcome, never an ungated registration.

### 5.5 What is never read to decide applicability

No Project-global activation state, no Review record, no `project.yaml` key and no prior Run decides whether a call is gated. Only the `review` argument does, and, for resume compatibility, the markers of the slot's own pending records. The publication barrier (§18.7) reads Review records in the published history, but it gates no call: it decides only whether a push may publish that history.

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
| `review-v1-planning-checkout-v1` | the checkout capability contract for Review paths (§14.5) |
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

**Frozen.** All four in the planning mutation, at the freeze (§14.4), in this order: Run, task, Receipt (`review-receipt:<run_id>:3` — generation 3 is the only generation of a P2 Run that seals; generation 4, when written, is an invalidation generation with status `open` that issues nothing, §11.6), Consumption (`review-consumption:<receipt_id>`). The Supersession path of an invalidation is keyed by the reserved Receipt ID (`.workline/review/supersessions/<receipt_id>.yaml`), so it too is known at the freeze. Generation mutations reserve nothing; their invocations carry the IDs they use. Reservations are per mutation (live `Mutation.reserve_id`), so a Run reserved by one planning mutation is unreachable from any other.

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
- Reconstruction on resume: from the planning invocation (`request` / `design`), the planning mutation's reserved IDs and the declared base recomputed under the lock on the committed view of the base commit that currency is evaluated on (§7.4, §13). The rebuilt record must digest to the Run's `candidate_hash` and equal the stored snapshot's `material`. A different declared base is staleness or, once the registration began, reconciliation (§13); any other difference is `ReconcileRequired`.
- After runtime loss the reservations are gone: a fresh Candidate is required (new planning mutation, new reserved IDs, new `candidate_hash`, new Run); the old Run is a legal orphan and its task is never rerun (§12, §23 C-6). A registration commit the old Run left unproven is not lifted by a fresh Candidate: the publication barrier keeps it unpublished (§18.7, §21).

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

**Frozen.** Computed under the lock on the committed view of HEAD (§3, §15.4) — at the freeze HEAD is `review_binding.head` — never on the working tree: the registration is committed on a commit, and the currency that authorizes it is that commit's (§13). Part of the Candidate and so of `candidate_hash` (Candidate 7 §4.1: "reviewed artifact identity plus declared base/context identity"). An entity the declared base names that the committed view does not hold (a Phase or Work present only in the working tree) → at the freeze `ValidationError` code `review_base_uncommitted`, before any Review record, planning abandoned; at any subsequent evaluation, a declared-base difference (§13). The live preconditions keep reading the working tree, unchanged; a working-tree-only change of a declared-base fact is not part of the base until it is committed.

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
checkout_capability: review-v1-planning-checkout-v1
```

`<R>` is the configured Workline root (`project.yaml` `workline.root`); Skills resolve through `workline.registry.resolve_skill(R, id)`. Unresolvable or unreadable → `StopError` code `review_context_unavailable` at the freeze, before any Review record. `review_context_hash = serialize.digest(context record)`. Recomputed at the freeze, before each reviewer launch, before each generation mutation after the first, at the use check, at the pre-Kp currency proof (§15.6) and in C-2(Kp) (§15.3 P12). Unavailable at one of those points, it is the same `review_context_unavailable` STOP with the planning mutation pending — never a stale difference, so a transient read failure never invalidates a Receipt.

Decisions on each candidate input (task §18):

| input | decision |
| --- | --- |
| base Git identity (HEAD / commit) | **not bound in the Context.** The Run's own generation commits advance HEAD, so a HEAD-bound Context would invalidate itself. Branch and lineage are bound by the operation binding (§11.5); the exact pre-registration commit by `use_check_head` and Kp's recorded parent P (§15.2, §15.6, §17); the semantic base by the Candidate's declared base, evaluated on the committed view of that commit (§7.4, §13) |
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
| checkout semantics of Review paths (attributes, line endings) | `checkout_capability`: the capability contract of §14.5 (Frozen P1 R6 §6 / R11 §10 name attributes and line-ending conversion as bound Git semantics). Which of its two forms a repository uses is not bound: both reproduce the canonical bytes exactly |
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
                        {check: checkout-capability, result: pass},
                        {check: review-namespace, result: pass},
                        {check: dirty-separability, result: pass},
                        {check: publication-barrier, result: pass | not-applicable}]}   # not-applicable: remote-less
```

Gate fields: `evidence_digest`, `coverage_digest`, `raw_report_set_digest`, `adjudication_digest`, `obligation_digest` are `serialize.digest` of these records. Generation 1 uses the evidence of the freeze and the empty forms (`settled: []`, `reports: []`, `tasks: []`, `obligations: []`). Generation 2 and 3 use the settled forms. Generation 4 carries generation 3's digests and its own invalidation evidence (§11.6.1). `unresolved_obligations = len(obligations)`. Authorized iff every required task settled `completed` and `unresolved_obligations == 0`. Evidence completeness (R11) is `unknown` by definition and is never reused: P2 reuses nothing across Candidates.

## 11. Generation mutations (C-4)

**Chosen: Direction A** — every generation transition is its own generation mutation, owned by the Roadmap operation, with Frozen P1 R2 §4 / R3 §2 and the live helpers `gate.pending_generation_mutations` / `gate.next_generation_scope` unchanged.

Why: it satisfies the frozen procedure as written and uses the helper as landed (**Measured**, reconnaissance probe 8: initial scope exactly `[gate path, token]`, generations from the unchanged helper, interrupted generation mutation resumed first, every window clean). Direction B would change frozen R2/R3 text and the live helper and needs a new mechanism to tell the current owner, a stale predecessor and a second owner apart inside one long-lived mutation; no P2 requirement needs it. Every defect the reconnaissance found in Direction A is closed below: the missing snapshot (§11.4), cross-mutation branch binding (§11.5), the abandonment gap (§12), the one-mutation wording of `rules/git` (§11.12, §26.1).

### 11.1 Ownership

**Frozen.** Top-level operation: the planning operation (`create_roadmap` under lock operation `roadmap-create`, `enter_phase` under `phase-entry`). Owner string: `"roadmap"`. A generation mutation is started, applied, committed and completed by Roadmap-owned code (`workline.roadmap_review`) inside that operation's `project_operation` lock (`MutationController.require_execution_lock` accepts it: `mutation.py:1626-1652`). It has no lock operation, entry point, CLI or API of its own; it is never a top-level operation. Review takes no lock, starts no mutation, commits nothing and finalizes no Roadmap or Phase state; it contributes record shapes, validation, read-back and the generation-scope helper.

```text
Roadmap top-level operation (lock roadmap-create | phase-entry, owner "roadmap")
  owns:  planning mutation          request + markers; registration; Consumption; Kp; Km; push
         generation mutation 1      accept      (snapshot, task input, gate 1)
         generation mutation 2      settle      (gate 2)
         generation mutation 3      seal        (gate 3 + Receipt)
         generation mutation 4      invalidate  (gate 4 + Supersession) — only when the Run is stale after the seal (§13.3)
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
 "transition": "accept" | "settle" | "seal" | "invalidate",
 "candidate_hash": <the Run's>, "review_context_hash": <the Run's>, "effective_policy_hash": <the Run's>,
 "obligation_digest": <the obligation_digest generation N records>,
 "receipt_id": <the reserved Receipt ID for "seal", the superseded Receipt ID for "invalidate", null otherwise>,
 "invalidation_reason": <the reason code of §13 for "invalidate", null otherwise>}
```

It binds the parent (`planning_mutation_id`), the Run, the exact generation and transition, the Candidate / Context / Policy identities and, for an invalidation, the Receipt it supersedes and why (Frozen P1 R3 §9). A resumed generation mutation is re-entered through `MutationController.open` with its recorded owner, invocation and scope (reconnaissance probe 8), so its invocation never has to be recomputed.

### 11.3 Initial write scope

**Frozen.** `WriteScope(files = GenerationScope.files + extra, entities = ())`, created by `MutationController.open("roadmap", invocation, scope)` directly — not through `_open` (no push destination, no `_ledgers`):

| transition | `files` |
| --- | --- |
| accept (N = 1) | gate path 1, token, candidate snapshot path, task input path |
| settle (N = 2) | gate path 2, token |
| seal (N = 3) | gate path 3, token, Receipt path |
| invalidate (N = 4) | gate path 4, token, Supersession path (`.workline/review/supersessions/<receipt_id>.yaml`) |

Every path is known before the mutation begins (§6.3), so no generation mutation calls `extend_scope` (Frozen P1 R2 §4: "extend_scope() is not the safety mechanism"). The planning mutation's scope never holds a token, so the helper never refuses the planning mutation itself.

### 11.4 Dirty snapshot

**Frozen.** Right after the generation mutation begins, before any effect: `gitops.record_preexisting_dirty(gen, root)`, then `gitops.ensure_separable_before_effects(gen, <its record paths>)`. A resumed generation mutation reuses its noted snapshot. **Measured** (reconnaissance probe 8, first run): without the snapshot taken when the mutation begins, the mutation took its own generation file for a person's change and stopped with `dirty_overlap`.

### 11.5 Operation binding (branch and base across mutations)

**Frozen.** At the end of the freeze the planning mutation records the note `review_binding = {branch: <full ref of HEAD's branch>, head: <HEAD commit>}`. "The binding holds" means: HEAD is on exactly that branch (full ref) and HEAD's history holds `head` (`gitcmd.descends_from`). It is checked before each generation mutation starts, before each reviewer launch, at the use check, and before the planning mutation records each of its post-Review stages (registration, Kp, Consumption, Km, publication). Not holding → `ReconcileRequired`, nothing replayed, recorded, committed or pushed; returning to the branch continues. Inside each mutation the live rules apply unchanged: a generation mutation's `create_file` stage carries `decided_on`, and its commit names that branch (`_bind_decision`).

### 11.6 Content, commits and the transition state machine

**Frozen.** A P2 Run has at most four generations, each written by its own generation mutation:

| N | transition | stage `review-generation` (`create_file` effects, in this order) | gate `status` | started only when |
| --- | --- | --- | --- | --- |
| 1 | accept | candidate snapshot, task input, gate 1 (accepted task, empty settlement) | `open` | the freeze is complete (§14.4) |
| 2 | settle | gate 2 (settled task, settled digests) | `open` | the latest generation is 1 and a valid report returned (§10.4–§10.5) |
| 3 | seal | gate 3 (`sealed_authorized`, `receipt_id`, `authorized_operation_stage`), then the Receipt — one stage (Frozen P1 R3 §7) | `sealed_authorized` | the latest generation is 2, it authorizes (§10.6), and the Run is current (§13) |
| 4 | invalidate | gate 4 (§11.6.1), then the Supersession of the generation-3 Receipt — one stage (Frozen P1 R3 §8) | `open` | the latest generation is 3, no registration stage is recorded, and the use check finds the Run stale (§13.3) |

The valid chains of a P2 Run are exactly:

```text
G1 accept                                            unsealed: stale before a Receipt, or orphaned
G1 accept -> G2 settle                               unsealed: not authorized, stale before a Receipt, or orphaned
G1 accept -> G2 settle -> G3 seal                    sealed: the Receipt is used by the registration, or orphaned
G1 accept -> G2 settle -> G3 seal -> G4 invalidate   unsealed again: the Receipt superseded; terminal
```

Generation 3 is the only seal, and generation 4 is the last generation a P2 Run ever has: no P2 path writes generation 5, seals again, or starts generation 4 once a registration stage is recorded (§11.10, §13.4). A transition started in any other state, a generation whose number the helper computes differently from this table, or a chain of any other shape is `ReconcileRequired`.

Before recording the stage: `gate.require_committable` and the Git persistence preflight (§14.3, the checkout capability of §14.5 included) on its paths. Then `apply()`, then Git stage `review-generation-commit`: exactly one `git_commit` of the stage's paths with the planning commit primitive (§15.2), message `chore(workline): record review generation <N> of <run_id>`, commit-only, never a push. Then `gate.require_persisted(paths)` and the blob check (HEAD blob == canonical bytes, mode `100644`). Only then `complete()`. Generation commits stay local until a push from that branch carries them as history (they add no registration, so the publication barrier never concerns them, §18.7); the reviewer launch needs only the local Git boundary (Frozen P1 R3 §10: remote-less Projects remain valid).

#### 11.6.1 Generation 4 and the Supersession

**Frozen.** Every field of gate 4 (P1 `GATE_FIELDS`):

| field | value |
| --- | --- |
| `review_run_id` | the Run |
| `generation` / `previous_generation` | `4` / `3` |
| `previous_digest` | SHA-256 of gate 3's canonical bytes (the chain digest `ReviewStore` computes, Frozen P1 R1 §4) |
| `review_kind`, `target_identity`, `operation_identity` | gate 3's: kind and target are immutable facts of a Run, and the operation is unchanged |
| `candidate_hash`, `review_context_hash`, `effective_policy_hash` | gate 3's: the generation withdraws the authorization of that Candidate under that Context and Policy; the values found stale are no identity of the Run and are named only by the reason |
| `evidence_digest` | `serialize.digest({schema: review-planning-invalidation-evidence, version: 1, superseded_receipt_id: <gate 3's receipt_id>, reason: <reason>})` |
| `coverage_digest`, `raw_report_set_digest`, `adjudication_digest`, `obligation_digest` | gate 3's: nothing is re-reviewed, re-settled or re-adjudicated |
| `accepted_tasks`, `settled_tasks` | exactly gate 3's lists: a full snapshot (Frozen P1 R3 §6), no new acceptance, no new settlement |
| `status` | `open` |
| `receipt_id`, `authorized_operation_stage` | `null`, `null`: a generation with status `open` issues and authorizes nothing (P1 `GateGeneration.from_record`) |

`<reason>` is the reason code of the first stale difference the use check found (§13): `review_context_changed`, `review_policy_changed` or `review_declared_base_changed`; it is also the generation invocation's `invalidation_reason`.

The Supersession, at `.workline/review/supersessions/<receipt_id>.yaml`: `{schema: review-supersession, version: 1, superseded_receipt_id: <gate 3's receipt_id>, review_run_id: <the Run>, superseding_generation: 4, reason: <reason>}`.

The pair satisfies every P1 rule the live reader and validator apply: the Run's kind and target are unchanged; a seal is followed only by a generation with status `open`; accepted tasks and settlements are carried forward exactly (`store._chain_invariants`); the Supersession names a stored Receipt of the same Run and a subsequent generation with status `open` (`validate._supersessions`); and once both are applied the chain has moved past the Receipt and a Supersession says so, so `validate._superseded` finds no half-written invalidation. While only one of the two is applied the stage is resumed by its generation mutation, and no reader relies on the Run until both are persisted.

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
                                                                            its recorded bytes, and its transition the
                                                                            one §11.6 allows there (else
                                                                            ReconcileRequired); then apply, Git stage,
                                                                            persistence proof, complete()
     exactly one bound to anything else            -> ReconcileRequired (conflicting owner)
     more than one                                 -> ReconcileRequired (the helper's review_generation_conflict)
4. the validated chain decides what the planning mutation does next:
     no chain                              -> the freeze (§14.4), then generation mutation 1
     latest 1                              -> the reviewer launch (§10.3; stale -> terminal, §13.2), then
                                              generation mutation 2 with a valid report
     latest 2                              -> not authorized -> terminal (§19.1); else currency: stale -> terminal
                                              (§13.2), current -> generation mutation 3
     latest 3, no registration stage       -> the use check (§17); stale -> generation mutation 4 (§13.3)
     latest 3, a registration stage        -> the registration flow from its record (§15.1)
     latest 4                              -> terminal stale (§13.3), nothing evaluated again; with a registration
                                              stage recorded -> ReconcileRequired
5. only for the generation mutation step 4 names does gate.next_generation_scope compute N+1
```

The planning mutation is resumed first, its pending generation mutation second, and no generation is computed before that one is resolved (Frozen P1 R3 §2).

### 11.9 Conflicts and crashed predecessors

- A second owner holding the Run's token is refused (step 3).
- A crashed predecessor is the pending generation mutation found through the token.
- A crash with no recorded effect leaves nothing physical: effects are durable before they are applied, so abandoning it and computing N again cannot fork the Run.
- A physical create before the `applied` flag was saved is resumed, classified `applied_matching` and completed before N+1 is computed; the token makes a hypothetical N+2 overlap it (Frozen P1 R12 §3).

### 11.10 Generation mutations and the registration never coexist

The planning mutation records no effect before the use check, and generation mutations — generation mutation 4 included — exist only before its first registration stage is recorded. Once a registration stage is recorded, a pending generation mutation of its Run is a conflict (`ReconcileRequired`), and generation mutation 4 is never started (§13.4).

### 11.11 The planning mutation disappears

**Frozen.** Runtime loss or a fresh clone after generations were committed:

- The committed Review records stay. A Run whose last generation mutation completed is a legal orphan — its latest generation `open` (1, 2 or 4) or `sealed_authorized` and unconsumed (3) — and `validate_review` validates it as one.
- A Run whose runtime was lost with a generation stage partially applied holds a half-written stage (a gate without its task input, a seal without its Receipt, generation 4 without its Supersession), which `validate_review` reports as Frozen P1 R3 requires. P2 never repairs it, never refuses a subsequent call because of it (§14.6), and reads it only through the uniqueness indexes (§16.3), which it does not touch.
- An orphaned sealed Receipt is never used: the use check accepts only the Run its own planning mutation reserved (§17 item 4), and no mutation holds that reservation any more. For the same reason it is never superseded: P2 starts a generation mutation only for its own Run. It carries no registration, so the publication barrier never concerns it (§18.7).
- A pending generation mutation left without its planning mutation is inert. Its scope holds only its Run's paths, and no P2 operation resumes it, because a new planning mutation reserves a new Run and never looks at the old token.
- The same request again begins a new planning mutation with new reserved IDs, a fresh Candidate and a new Run. A registration commit the lost planning mutation left unproven is not lifted by it: the publication barrier keeps every history holding it unpublished until a person reconciles (§18.7, §21).

### 11.12 The `rules/git` one-stable-mutation assumption

**Frozen.** `rules/git` Operation Owner says an operation resumes the one pending mutation that corresponds to the invocation and stops on several. The review-v1 planning operation owns one planning mutation and the generation mutations it starts. At the entry, the planning mutation is the one corresponding mutation. A pending generation mutation bound to it by `planning_mutation_id` and the Run's token is its subordinate and is resolved in the order of §11.8. Anything else remains "複数件 / 競合" and is `reconcile required`. The authority text is amended when the implementation lands (§26.1). Until then no review-v1 planning exists and the live rule is unchanged.

## 12. Planning mutation lifecycle

**Frozen.**

| state | condition | behaviour |
| --- | --- | --- |
| may be abandoned | no generation mutation of its Run has started (no gate chain for the Run, no pending generation mutation bound to it), no effect recorded, and the live path would abandon it too: a Roadmap creation begun or resumed, a Phase entry begun by this run (a resumed Phase entry is never abandoned, `skills/roadmap` Phase entry) | a STOP abandons it (live `abandon_on_stop`): every pre-Review refusal (§7.6, §7.7, §14), a Context that cannot be computed, a reservation or note failure |
| must remain pending | from the start of generation mutation 1 until a terminal outcome | any STOP (reviewer failure, invalid report, binding moved, proof failure, reconcile) leaves it pending; the next invocation with the same request resumes it |
| completed without registration | `not_authorized` (§19.1); `stale` before a Receipt exists (§13.2); `stale` after the Receipt, only once generation 4 and the Supersession are committed and proven persisted (§13.3) | `complete()` with no effect recorded; `ReviewedPlanningResult` returned |
| completed with registration | publication done (remote-less: C-2(Km) recorded) and the live structure postcheck passed | `complete()`; `ReviewedPlanningResult(status registered)` |
| never ends `stale` | from the moment its first registration stage is recorded | a currency difference is `ReconcileRequired` (§13.4); the registration is never undone |
| superseded by a fresh Candidate | never while pending | a different request or design for the slot → `reconcile_required` (live); a fresh Candidate exists only after the previous planning mutation was abandoned (pre-Review), completed (terminal) or lost with the runtime — and a lost one that left an unproven registration commit leaves the publication barrier, which a fresh Candidate does not lift (§18.7, §21) |

The way out of an operational failure is to run the same request again with a working reviewer, or to have the reviewer return `declined`, which settles the task `failed` and ends the attempt as `not_authorized` (§19.1). A pending review-v1 planning mutation therefore never needs a human to stop blocking the Project, except where a reconcile rule of `rules/git` applies (history rewritten, foreign change, proof failure) or a registration commit that can no longer be proven holds the publication barrier (§18.7).

## 13. Currency, staleness and invalidation

**Frozen.** *Currency* is evaluated against one exact base commit B and means, in this order, the first difference deciding:

1. the Context recomputed now (§8) digests to the Run's `review_context_hash` — a difference is reason `review_context_changed`;
2. the Policy recomputed now (§9) digests to the Run's `effective_policy_hash` — a difference is reason `review_policy_changed`;
3. the Candidate rebuilt from the planning invocation (`request` / `design`), the planning mutation's reserved IDs and the declared base computed on the committed view of B (§7.4) digests to the Run's `candidate_hash` and equals the stored snapshot's `material` — a different declared base is reason `review_declared_base_changed`; any other difference (reserved IDs or planning invocation not reproducing the Candidate) is `ReconcileRequired`, never staleness.

The declared base is read from the committed view of B, never from the working tree, so the currency that authorizes a registration is the currency of the exact commit the registration is committed on. `review_kind`, `operation_identity`, `target_identity` and `authorized_operation_stage` are compared wherever a Receipt exists (§17 item 4, §15.6, §15.3 P12). No P3 Review-validity fast path exists; P2 never re-reviews inside the same planning operation.

### 13.1 Where currency is evaluated

| point | base B | a difference means |
| --- | --- | --- |
| right before the reviewer launch (§10.3) | HEAD | stale before a Receipt (§13.2) |
| right before generation mutation 2 or 3 starts | HEAD | stale before a Receipt (§13.2) |
| the use check (latest generation 3, no registration stage recorded, §17) | HEAD, recorded as `use_check_head` when the use check passes | stale after the Receipt: invalidation (§13.3) |
| the pre-Kp currency proof (registration stages recorded, Kp not made, §15.6) | P, which HEAD must be | `ReconcileRequired` (§13.4) |
| C-2(Kp) item P12 (§15.3) | Kp's parent P | `ReconcileRequired` (§13.4, §15.5) |

Once C-2(Kp) has passed, the authorization is spent on the proven Kp: the Consumption records it, and Km and the publication are proven by exact metadata proofs (§18.2) and the publication barrier (§18.7), not by currency.

### 13.2 Stale before a Receipt exists

The Run's latest generation is 1 or 2: nothing is sealed and no Receipt exists. Then:

- no generation is written and no Supersession: a Supersession names a Receipt (Frozen P1 R1 §5, R3 §8), and there is none to invalidate;
- the planning mutation completes with no effect recorded, and the result is `ReviewedPlanningResult(status="stale", receipt_id=None, ...)` (§19.2);
- the Run stays a legal orphan whose latest generation has status `open`, its task accepted and unsettled (latest 1) or settled (latest 2). Nothing can ever seal it: only its own planning mutation starts its next generation mutation, and that mutation has completed.

After generation 2 the not-authorized decision is read from the chain first (§19.1); currency is evaluated only for a settlement that authorizes, right before generation mutation 3 starts.

### 13.3 Stale after the Receipt: invalidation generation 4

The Run's latest generation is 3 (`sealed_authorized`, Receipt issued), no registration stage is recorded, and the use check finds a stale difference (§17 item 7). Before the planning mutation may end:

1. generation mutation 4, transition `invalidate`, writes gate 4 — an `open` generation — and the Supersession of the Receipt, in one stage (§11.6, §11.6.1; Frozen P1 R3 §8: "a later `open` generation and supersession record before old Receipt may proceed"; R12 §5 treats them as one partial stage), under the same-run serialization as every generation (§11.3, §11.8);
2. that stage is committed with the planning commit primitive and proven persisted (gate paths and Supersession path, blob check);
3. only then does the planning mutation complete with no effect recorded; the result is `stale` with `receipt_id` = the superseded Receipt (§19.2).

The invalidation is decided when the generation-4 stage is recorded, not earlier. A generation mutation 4 interrupted with no recorded effect is abandoned like every generation mutation (§11.8), and the next run evaluates the use check again: if the Run is current again, its unsuperseded Receipt goes on to the registration; if not, generation mutation 4 starts again. Once the stage is recorded, a resume finishes it, and the planning mutation ends `stale` without evaluating anything again (§11.8 step 4, §21).

Generation 3 and the Receipt are never rewritten. Once gate 4 and the Supersession are committed the Receipt is superseded: the use check refuses it (§17 item 3), the P1 validator refuses any Consumption of it (`validate._consumptions`), and §16.2 keeps that rule for version 2.

Invalidation exists only in this window. The use check is the last currency evaluation that can end in `stale`, and it runs only while no registration stage is recorded, so no Run ever holds both a registration stage and generation 4. The publication barrier (§18.7) never reads a Supersession to clear: a Supersession can only keep a barrier, so invalidation can never make a registration commit publishable.

### 13.4 After the registration began

Once the first registration stage is recorded, the planning mutation never ends `stale` and never starts generation mutation 4: domain registration exists locally, so it ends registered or stays in reconciliation. A currency difference then is:

- at the pre-Kp currency proof: `ReconcileRequired` (reason `review_registration_currency_changed`, or `review_registration_base_moved` for the base rules of §15.6); no Kp is recorded or made, no Consumption is written, nothing is pushed; the planning mutation stays pending with its registration in the working tree, and the same request continues once the difference is gone (the authority text restored, for example);
- at C-2(Kp): `ReconcileRequired` (reason `review_persisted_proof_failed`) with the consequences of §15.5: no Consumption, and the publication barrier holds for every commit whose history holds Kp.

The registration is never undone, and Kp is never reset, rebased or amended.

### 13.5 Changes and outcomes

| change | detected by | before a Receipt | after the Receipt, before the registration | after the registration began |
| --- | --- | --- | --- | --- |
| a different request or design (the caller passes another plan) | live same-request / `_require_resumable` | `reconcile_required`, record untouched | same | same |
| declared base: lifecycle or state of a named existing Phase or Work, the Phase's or Roadmap's lifecycle or state, a Phase dependency's state — as committed | Candidate rebuild on the committed view | terminal `stale` (§13.2) | generation 4 + Supersession, then terminal `stale` (§13.3) | `ReconcileRequired` (§13.4) |
| Workline implementation content | Context (`loader_identity`) | terminal `stale` | generation 4 + Supersession, then `stale` | `ReconcileRequired` |
| authority text (`registry.md`, a listed Skill) | Context (`authority`) | terminal `stale` | generation 4 + Supersession, then `stale` | `ReconcileRequired` |
| Effective Policy | policy hash | terminal `stale` | generation 4 + Supersession, then `stale` | `ReconcileRequired` |
| reserved IDs or planning invocation not reproducing the Run's Candidate | rebuild | `reconcile_required` | `reconcile_required` | `ReconcileRequired` |
| a Run record changed | `ReviewStore` / `create_file` classification / blob check | `reconcile_required` | `reconcile_required` | `ReconcileRequired` |
| HEAD moved after the use check | §15.6, §15.3 P2 | — | the use check runs again on the new HEAD | a commit touching a planning-owned path, or a history not holding `use_check_head`: `ReconcileRequired` (`review_registration_base_moved`); otherwise currency on the new P decides |

What can change, and when:

- **Under the lock** (the whole synchronous run, the reviewer included): only actors outside Workline — a person or tool editing files or Git state, an edit of the Workline root on disk. P2 has no deliberate lock release.
- **Across a crash window** (the lock released by the process ending): Workline operations whose declared write scope does not overlap the pending planning mutation's — Roadmap / Phase hold, resume, cancel and achievement (event log only), push destination pin maintenance, and, for a pending Roadmap creation, Related maintenance and direct CREATE (`related.yaml`). Roadmap creation, Phase addition, Phase entry and plan exclusion (`roadmap.yaml`) and START (every ledger) are refused by scope overlap (**Measured**, reconnaissance §12). Such an operation can commit and push after the registration began; its commit carries only its own paths, it cannot push an unproven Kp (§18.7), and whether its commit changed the authorized base is decided by the pre-Kp currency proof on the commit Kp is made on (§15.6).

## 14. Pre-Review refusals and the freeze

### 14.1 Registration paths

**Frozen.**

- RoadmapPlan: `.workline/roadmaps/<roadmap_id>.md`, `.workline/phases/<phase_id>.md` for every reserved Phase, and `.workline/relations/roadmap.yaml` when the plan declares at least one relation.
- PhaseEntryDesign: `.workline/works/<work_id>.md` for every normal Work, the integration and the confirmation when present, `.workline/relations/roadmap.yaml` (always: integration dependencies exist), and `.workline/relations/related.yaml` when any Work declares Related.

These are exactly the paths the registration stages write (`ops.owned_canonical_paths` restricted to the registration stages).

### 14.2 Dirty overlap

**Frozen** (task §23). At the freeze, `gitops.ensure_separable_before_effects(planning, registration paths + Run record paths + Consumption path)` on the snapshot `_open` recorded; the Run record paths include gates 1–4 and the Supersession path, all known at the freeze (§6.3). A person's pre-existing change overlapping any of them stops the call with `dirty_overlap` before anything is written, and the planning mutation is abandoned, so the person's bytes are untouched and no reviewer runs for a plan that can never be committed. Each generation mutation repeats the check for its own paths (§11.4). The Kp and Km stages keep the live finalize check (`ensure_separable(preexisting, paths)`). The legacy path is unchanged; BL-041 is not fixed globally.

### 14.3 Git persistence preflight

**Frozen.** Two parts, run at the freeze, before every stage that writes a Review record is recorded, and again right before every Git stage P2 records (attributes and configuration can change):

1. *Transform attributes.* For every planning-owned path of the stage, `git check-attr -z filter ident working-tree-encoding -- <paths>` must report `unspecified` (or `unset`) for all three attributes. Anything else → `StopError` code `review_git_transform`. These are the attributes that can make a committed blob differ from the written bytes or run an external process during `git add` (clean and process filters, Git LFS, `$Id$` expansion, re-encoding). Text and eol normalization is the identity on LF-only content, and every file P2 writes is LF-only (canonical renderers; CR refused by §7.6).
2. *Checkout capability.* For every Review record path of the stage — at the freeze every Review path the Run can write and every Review record committed at HEAD — the checkout capability of §14.5.

### 14.4 Freeze order

**Frozen.** After `_open` and the live reservations:

```text
1  RoadmapPlan: reserve `roadmap` (live) and the Phase and relation IDs through `decide_phases` (live; records
   nothing); PhaseEntryDesign: reserve every stage ID under the register_works keys (§7.3); extend the entity scope
2  build the Candidate (declared base on the committed view of HEAD, §7.4); representability check (§7.6); R9 (§7.7)
3  Context (§8), Policy (§9), evidence (§10.6)
4  reserve Run, task, Receipt, Consumption IDs (§6.3); extend the file scope with the Consumption path
5  gate.require_committable (every Review path the Run can write: snapshot, task input, gates 1-4, Receipt,
   Supersession, Consumption); Git persistence preflight with the checkout capability (§14.3, §14.5);
   Review namespace readability (§14.6); dirty overlap (§14.2); with a push destination, the publication
   barrier on HEAD (§18.7)
6  record the note review_binding (§11.5)
7  start generation mutation 1
```

Before generation mutation 1 has started, steps 1–6 are refusals: a STOP anywhere in them abandons the planning mutation (§12), and a resume runs them again deterministically (every reservation returns the recorded ID; the note, once recorded, is kept). Once generation mutation 1 has started, a resume never runs steps 5–6 again and never abandons: steps 1–3 are recomputed only as the currency evaluation of §13, and the recorded `review_binding` is checked, never re-recorded. The checkout capability and the transform attributes are evaluated again before every Review-writing and every Git stage (§14.3).

The publication barrier at step 5 keeps a new registration from being built on a history that no Workline push may publish: when HEAD's history already holds an unproven registration commit (§18.7), the call stops with `review_publication_barrier` before any Review record. A remote-less Project publishes nothing and skips it.

### 14.5 Checkout capability

**Frozen.** Physical Review bytes must equal the canonical render bytes before any use (Frozen P1 R1 §4; P1-REV-007: `serialize.parse_canonical` refuses CR bytes). P2 never weakens or normalizes that. It therefore writes Review records only where Git's checkout semantics for Review paths reproduce the committed LF bytes in this repository and in every fresh clone of the commits that carry them, and proves that positively before writing. A subsequent commit that removes the rule removes the guarantee for clones of that commit; a P2 call there stops before writing (§21 row 45).

**Measured** (§31; Git for Windows 2.54 with system `core.autocrlf=true`):

- with no attribute rule a fresh clone checks out an LF-only Review record as CRLF while `git status` stays clean, and the P1 reader refuses it (`review_record_noncanonical`);
- a committed `.gitattributes` rule `.workline/review/** eol=lf -filter -ident -working-tree-encoding`, or the same with `-text` for `eol=lf`, keeps the fresh clone's bytes LF, also under a global attributes file asking `*.yaml eol=crlf` and under `core.autocrlf=false` with `core.eol=crlf`;
- a rule only in the origin's `.git/info/attributes` is not carried by a clone; a clone-local `.git/info/attributes` rule `eol=crlf` overrides the committed rule; a subsequent commit dropping the rule loses the guarantee for clones of that commit;
- `git check-attr --source=<commit>` alone still reads `.git/info/attributes`; the committed evaluation below reads the committed rule alone; `check-attr` answers for a path that does not exist yet.

The capability holds for a path exactly when each of the two evaluations below reports, for `text eol filter ident working-tree-encoding`, one of these two exact value tuples:

```text
form L   text: unspecified   eol: lf            filter: unset   ident: unset   working-tree-encoding: unset
form B   text: unset         eol: unspecified   filter: unset   ident: unset   working-tree-encoding: unset
```

- **committed evaluation** — the committed `.gitattributes` files of HEAD's commit alone: `git check-attr --source=<HEAD commit>` with `GIT_ATTR_NOSYSTEM=1`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=<an empty file>`, `-c core.attributesFile=<an empty file>` and `--git-dir=<a fresh, empty bare directory under .workline/runtime/review/attr-eval/<nonce>/ whose objects/info/alternates names this repository's object directory>`, removed afterwards; no `info/attributes`, system or global source takes part. It is what a fresh clone of that commit applies whatever its own configuration: a committed `unset` or `eol=lf` outranks every global and system source, and no clone receives another repository's `info/attributes`;
- **effective evaluation** — plain `git check-attr` in this repository, every source included: what the next checkout here applies.

Anything else → `StopError` code `review_checkout_unsafe`: `unspecified` where a form names `unset` or `lf`, `eol: crlf`, `text: auto` or `set`, a set `filter`, `ident` or `working-tree-encoding`. A question Git cannot answer → `StopError` code `review_checkout_unknown`. Unspecified is never safe: the measured failure had every attribute unspecified while the committed blob was LF.

A commit P2 makes carries only its own paths (`git commit --only`), so it carries HEAD's committed `.gitattributes` unchanged: the committed evaluation of HEAD is the evaluation of the commit that stores the record.

Where it is checked: at the freeze (§14.4 step 5) for every Review path the Run can write and every Review record path committed at HEAD (`git ls-tree -r --name-only <HEAD> -- .workline/review/`); and for each stage's own Review paths before that stage is recorded and before its Git stage is recorded (§11.6, §15.1). At the freeze a failure abandons the planning mutation with nothing written; after generation 1, the planning mutation stays pending and continues once the rule is back.

Workline never writes `.gitattributes` or `info/attributes`: making the capability available is the Project's own configuration decision, as its ignore configuration is (`gate.require_committable`). A Project that uses review-v1 planning commits, for example, `.workline/review/** eol=lf -filter -ident -working-tree-encoding`.

The Context binds the capability contract (`checkout_capability: review-v1-planning-checkout-v1`, §8): Frozen P1 R6 §6 and R11 §10 make attributes and line-ending conversion bound Git semantics, and R1 §4 has the Git persistence proof show that the committed path reproduces the canonical bytes under them. Which form a repository uses is not bound: both reproduce the canonical bytes exactly, and every P2 proof and the publication barrier read raw blobs (§15.2, §18.7), never checked-out bytes.

Legacy invocations evaluate nothing here and write no Review record.

### 14.6 Existing Review namespace

**Frozen.** At the freeze, before any Review record, every record already in the Review namespace must read through `ReviewStore` in the working tree: the namespace shape rule of `validate_review` (only the known subdirectories, each a plain directory); `run_ids()` and `gate_chain(id)` for each Run; `receipt_ids()` and `read_receipt`; `consumption_ids()` and `read_consumption`; `superseded_receipt_ids()` and `read_supersession`; `candidate_snapshot_hashes()` and `read_candidate_snapshot`; `task_input_ids()` and `read_task_input`; `read_activation()`. Any failure — a CRLF record checked out before the rule existed (`review_record_noncanonical`), an unknown entry, a malformed record — → `StopError` code `review_namespace_unreadable` with the P1 error chained; the planning mutation is abandoned and nothing is written.

This is the unchanged P1 strict reader applied to every existing record before P2 adds one, so P2 adds Review state only to a namespace whose every physical record is canonical. Cross-record findings of other Runs that `validate_review` also reports — a half-written stage left by a lost runtime (§11.11) — are not refused here: P2 reads other Runs' records only through the uniqueness indexes (§16.3), which fail closed on their own, and refusing them would let one lost runtime disable review-v1 planning for the Project for good.

## 15. Registration, persisted proof and committed reload (C-3)

**Chosen: Direction A**: a planning-specific local commit, then an exact proof, then a canonical reload from the committed result, then equality, and only then publication.

Why: it proves what Git stored rather than predicting it. Direction B would need a positive proof, before the commit, of the exact Git objects through hooks, filters and concurrent writers. Live code has no helper for that, and it is harder to prove correct. The user preference of the task (§8.1) rules it out.

### 15.1 Sequence

**Frozen.** The planning mutation, after the use check passed and noted `use_check_head` (§17):

```text
1  registration stages, live and unchanged — roadmap, phases | works, integration, confirmation —
   with their projected refusals, postchecks and (Phase entry) the live phase structure check
2  working-tree round trip: ProjectView.load(store) -> normalize_persisted == reviewed;
   mismatch -> ValidationError review_roundtrip_mismatch (P1 adapter code), pending
3  pre-Kp currency proof on P = HEAD (§15.6); Git persistence preflight;
   ensure_separable(preexisting, registration paths)
4  stage review-registration-commit: one git_commit (Kp) of exactly the registration paths,
   planning commit primitive, base_head = P, base_exact (§15.2), the live message
   (chore(workline): create roadmap <display> | chore(workline): expand phase <display>); apply
5  persisted proof over Kp (§15.3)                                   -> C-2(Kp)
6  Git persistence preflight on the Consumption path; stage review-consumption: one create_file —
   the Planning Consumption binding Kp (§16); apply
   (the recorded Consumption effect is the durable C-2(Kp) checkpoint)
7  Git persistence preflight; stage review-consumption-commit: one git_commit (Km) of exactly the
   Consumption path, planning commit primitive, message
   chore(workline): record review consumption <consumption_id>; apply
8  metadata proof over Km (§18.2); note publication_proof            -> C-2(Km)
9  destination present: publication barrier clear for Km (§18.7); stage review-publication:
   one git_push of exact Km (§18.4); apply
10 live structure postcheck (_stop_on_structure "postcheck"); complete()
```

Steps 3 and 4 run with nothing in between: the proof of step 3 and the recording and making of Kp are one uninterrupted sequence in one process. A recorded Kp that a resume finds unapplied is replayed only after the pre-Kp currency proof passes again on its recorded P (§15.6).

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
- **Base-exact registration commit.** The Kp `git_commit` payload also carries `"base_exact": true`, with `base_head` = P (a full commit ID) and `branch` = `review_binding.branch`. For such a commit `_classify_commit` never takes the independent-advancement path (`_head_advanced_independently`): it is unapplied only while HEAD is exactly `base_head` on the recorded branch, and otherwise applied with an unexpected result (`ReconcileRequired`). The primitive reads HEAD again immediately before `git commit` and STOPs (`ReconcileRequired`, reason `review_registration_base_moved`) when it is not `base_head`; `_commit_just_made` then shows the new commit's one parent. So the ordinary independent-HEAD-advancement rule can never move Kp onto another base. Generation commits and Km keep the live base rules, independent advancement included: they carry Review records only, their bytes are proven exactly (§11.6, §18.2), and M1 bounds Km's parent (§18.2). A legacy `git_commit` payload and its classification are unchanged.
- The primitive's identity is the Context's `git_persistence` (Frozen P1 R5 §5–§6, R11 §10, R12 §8: a mechanically suppressed hook mode is bound in the Git semantics identity).
- Blob check (used by §10.3, §11.6, §15.3, §18.2): the committed blob of a path is read with `git cat-file blob <oid>` as raw bytes (no text decoding, no filters) and compared byte for byte; its mode comes from `git ls-tree -r -z --full-tree`.
- Kp or Km recorded applied without a commit ID (an interruption between `git commit` and the save) cannot be shown to be the mutation's own. The result is `ReconcileRequired` (reason `review_commit_unowned`), with no backfill in P2, the live treatment of an unidentified commit (`rules/git` Commit / push).

### 15.3 Persisted proof over Kp — C-2(Kp)

**Frozen.** Contract `review-v1-planning-proof-v1`. PASS requires every item; any failure → `ReconcileRequired` (reason `review_persisted_proof_failed`):

| # | condition | how |
| --- | --- | --- |
| P1 | Kp is the planning mutation's own commit | the `review-registration-commit` `git_commit` is recorded `applied` with `commit_id`; Kp = that ID |
| P2 | exact branch, parent and lineage | HEAD on `review_binding.branch`; that branch holds Kp; Kp has exactly one parent P; P == the `base_head` recorded in the Kp effect; P == `use_check_head`, or P descends from `use_check_head` and `gitcmd.commits_touching(use_check_head, P, planning-owned paths) == []` (so P also descends from `review_binding.head`) |
| P3 | exact operation-owned path set | `git diff-tree -r -z --no-renames --no-abbrev --raw P Kp` lists exactly the registration paths: status `A` for each new entity file, `M` for each ledger, new mode `100644` for every entry, nothing else |
| P4 | exact committed bytes | each entity blob == the recorded `write_file` payload content (UTF-8); each ledger blob's SHA-256 == the recorded `wrote` digest of the registration's last write to it |
| P5 | fresh canonical reconstruction | committed-result loader (§15.4) over Kp and over P |
| P6 | exact relation / ledger result | Kp's roadmap relations == P's + exactly the expected new relations, appended in registration order, records identical; the same for Related; Kp's entities == P's + exactly the reserved new entities |
| P7 | structure | `validate_structure(Kp view) == []` |
| P8 | normalized persisted semantics == reviewed Candidate | `normalize_persisted(load_persisted(result identity, Kp view)) == normalize_candidate(reviewed)` (projection identity; kind and semantics version equal); created IDs == reserved IDs; each expected entity and relation exactly once; no extra operation-owned entity or relation (P3 + P6) |
| P9 | R9 canonical first Work (PhaseEntryDesign) | `startable_works` + `planned_next_preference` on the Kp view give exactly the reviewed `canonical_first_work` (unique ID, or none) |
| P10 | interpretation unchanged | `loader_identity` recomputed now == the Context's; `adapter_identity` equal (P12 covers the whole Context) |
| P11 | nothing published before this proof | the planning mutation holds no `git_push` effect; the planning commit primitive runs no hook; and no Workline push of any operation can carry Kp before a Consumption naming it is committed (§18.7) |
| P12 | authorized pre-state | full currency (§13) on P: the declared base computed on the committed view of P (P5's P view), the Candidate rebuilt from it (digest == the Run's `candidate_hash`, record == the snapshot's `material`), the Context and the Policy recomputed now (== `review_context_hash`, `effective_policy_hash`); `review_kind`, `operation_identity`, `target_identity` and `authorized_operation_stage` recomputed == the Receipt's; P's tree holds the Run's snapshot, task input, gates 1–3 and Receipt with the canonical bytes (blob check), and no gate 4, no Supersession of the Receipt and no Consumption for it |

This covers the task's eleven requirements: 1 = P3, 2 = P4, 3 = P3 modes, 4 = P6, 5 = P8 created IDs, 6 = P3 + P6, 7 = P5, 8 = P8, 9 = P9, 10 = P1 + P2, 11 = P11 + §18. Together, P2 + P12 prove the authorized pre-state, P3–P9 the authorized transition and its exact result: authorized pre-state + authorized transition = exact Kp result. Nothing is substituted by a path list, working-tree bytes, the request identity, `ProjectView.with_effects`, or the fact that P descends from `review_binding.head`.

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
- The same loader gives the committed view of a base commit (§3) to every currency evaluation (§13), the pre-Kp currency proof (§15.6) and P12; it is read by nothing that decides lifecycle (§22).

### 15.5 Proof failure after Kp exists

**Frozen.** STOP (`ReconcileRequired`). The planning mutation stays pending; no Consumption is written, and the planning mutation records no push. Kp remains a local, operation-owned commit that no Consumption proves, and the publication barrier (§18.7) refuses every Workline push — of this operation or of any other — whose history holds it. The barrier is computed from committed objects alone, so it survives a crash, the lock's release, another operation, runtime cleanup, runtime-record loss and a fresh clone. Workline never resets, rebases or amends Kp. Every retry runs the same proof over the same Kp. No invalidation follows (§13.4), and a Supersession would not clear the barrier: only a Consumption binding Kp does.

A person can still push Kp with Git by hand; Workline cannot prevent that and never treats it as proof. The Consumption is written only after C-2(Kp) passes over the local objects; the barrier never reads the destination; and a push classification that finds the destination already holding a commit means only that nothing is pushed for it (§18.7). Which history the branch holds from then on is a person's reconciliation.

The preflight (§14.3), the representability check (§7.6), the contained commit primitive (§15.2), the working-tree round trip (§15.1 step 2) and the pre-Kp currency proof (§15.6) exist so that this path is reached only through a concurrent foreign change or a Git fault.

### 15.6 Pre-Kp currency proof

**Frozen.** Run immediately before the Kp stage is recorded (§15.1 step 3), with P = HEAD, and — when a resume finds the Kp stage recorded and its `git_commit` unapplied — immediately before `_open` replays it, with P = the recorded `base_head`, through the `refuse_recorded` hook of `_open` (composed after the live `refuse_invalid_phase_writes` / `refuse_invalid_work_writes`; the hook runs on a resumed mutation before `mutation.apply()`, `roadmap.py:233-264`). PASS requires every item:

1. HEAD is P; the binding holds (§11.5);
2. P == `use_check_head`, or P descends from `use_check_head` and `gitcmd.commits_touching(use_check_head, P, planning-owned paths) == []`;
3. the Run's records are committed at P and unchanged (`gate.require_persisted` + blob check), and read back: latest generation 3, sealed, issuing the reserved Receipt; no Supersession of it; no Consumption for it;
4. `review_kind`, `operation_identity`, `target_identity` and `authorized_operation_stage` recomputed == the Receipt's;
5. currency (§13) on P: Context, Policy, and the Candidate with the declared base on the committed view of P.

It writes nothing. A failure of 1–2 → `ReconcileRequired` (reason `review_registration_base_moved`); of 3–4 → `ReconcileRequired` (reason `review_receipt_invalid`); of 5 → `ReconcileRequired` (reason `review_registration_currency_changed`). In every case no Kp is recorded or made, no Consumption is written and nothing is pushed; the planning mutation stays pending with its registration in the working tree (§13.4).

Why not `P == use_check_head` alone: a Workline operation whose declared scope is disjoint from the pending planning mutation's (Roadmap / Phase hold, resume, cancel and achievement: event log only, §13.5) can commit in a crash window after the registration began. Strict equality would leave a registration that no Workline path can finish or undo. The invariant chosen is as strong for everything the Receipt authorized: the exact parent's committed semantic base, the Context and the Policy are the authorized ones (item 5, and again P12), no commit since the use check touched a planning-owned path, so the recorded registration effects are still the exact change on P (item 2, and again P3/P4/P6), and Kp is made on exactly P (`base_exact`, §15.2). A commit that changed a declared-base fact, touched a planning-owned path or rewrote history stops the registration at this proof.

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

### 16.5 No field added by the round-1 repair

**Frozen.** Every candidate binding named for the repair was re-checked; none is added, and version 2 stays exactly §16.1:

| candidate binding | decision |
| --- | --- |
| `use_check_head` | not bound: an intermediate anchor of the pre-Kp proof. What the Receipt authorized is proven on Kp's exact parent (P2, P12), which the Consumption binds as `registration_parent` |
| exact Kp parent | already bound: `registration_parent` |
| authorization generation | already bound: `review_generation` (3) with `receipt_id` |
| invalidation / supersession status at use | redundant: the use check, §15.6 and P12 require no Supersession, generation 4 never follows a registration stage (§13.3), and P1 refuses any Consumption of a superseded Receipt (§16.2) |
| publication-barrier identity | none exists to bind: the barrier is computed from the Candidate snapshot, the registration commit and this Consumption (§18.7); `persisted_result.registration_commit` is the binding it reads |

## 17. Ordering and authorization states

**Frozen.**

```text
seal generation + Receipt committed      -> ISSUED
use check passes, use_check_head noted   -> VALID (evaluated on every run until the first registration stage is
                                            recorded, never after)
registration applied                     -> (registration in the working tree; Receipt unconsumed; no barrier)
pre-Kp currency proof passes, Kp made    -> (registration commit exists locally; the publication barrier holds for it)
C-2(Kp) passes, Consumption recorded     -> (durable persisted proof checkpoint)
Km committed                             -> CONSUMED (the barrier is clear for Km and its descendants)
C-2(Km) recorded (publication_proof)     -> SUCCESSFULLY USED
destination holds Km                     -> PUBLISHED   (remote-less Projects complete after SUCCESSFULLY USED)

stale at the use check                   -> generation 4 + Supersession committed -> SUPERSEDED (never consumed)
```

```text
Receipt  !=  Consumption  !=  registration commit (Kp)  !=  publication
```

**Use check** (right before the first registration stage is recorded; base B = HEAD), in this order:

1. the Run's chain validates, and its latest generation is generation 3, `sealed_authorized`, issuing exactly the reserved Receipt;
2. the Receipt reads back canonical and bound to that generation (P1 binding);
3. no Supersession names it, and no Consumption exists for it;
4. `operation_identity`, `target_identity`, `review_kind` and `authorized_operation_stage` equal the recomputed ones, and the Run is the planning mutation's reservation;
5. the binding holds (§11.5);
6. the Run's records are committed at HEAD and unchanged (`gate.require_persisted` + blob check), so every history that holds the registration commit holds the Run's Candidate snapshot (§18.7);
7. currency (§13) on HEAD: Context, Policy, and the Candidate with the declared base on the committed view of HEAD;
8. no registration path differs from HEAD (`gitcmd.changed_against_head`): a change made after the freeze would otherwise be taken into the registration's own writes.

Failures of 1–4 → `ReconcileRequired` (reason `review_receipt_invalid`). A failure of 5 → `ReconcileRequired`. A failure of 6 → the P1 `review_not_persisted` STOP, the planning mutation pending. A stale difference in 7 → invalidation (§13.3): generation 4 and the Supersession, then terminal `stale`; any other difference in 7 → `ReconcileRequired` (§13 item 3), and an unavailable Context → the `review_context_unavailable` STOP (§8); these two invalidate nothing. A failure of 8 → `StopError` code `dirty_overlap`; nothing is written, the planning mutation stays pending, and once the person commits or discards the change the same request continues.

On PASS the planning mutation records the note `use_check_head = <HEAD, full commit ID>` and then its first registration stage. Until that stage is recorded, every run evaluates the use check again and records the note again; once it is recorded, the note is never changed and the use check never runs again (§15.6 takes over).

Answers (task §10):

- **Can registration be locally committed before Consumption?** Yes: Kp precedes it.
- **What prevents that commit from being treated as successfully authorized before persisted proof?**
  - "successfully used" exists only as a committed, proven Consumption binding exactly Kp (Km + `publication_proof`);
  - the planning mutation records no push before C-2(Km);
  - the publication barrier (§18.7): no Workline push of any operation publishes a history holding Kp until a committed Consumption binds it;
  - the planning commit primitive runs no hook, so nothing Workline starts publishes Kp;
  - Review metadata is never lifecycle truth (§22), so no reader of lifecycle treats anything as authorized;
  - the operation returns `registered` only after `complete()`.
- **When is Consumption written?** After C-2(Kp) passes, as stage `review-consumption`.
- **Which commit stores it?** Km, a commit-only metadata commit made on top of Kp.
- **Does Consumption refer to an earlier registration commit?** Yes: `persisted_result.registration_commit` = Kp.
- **What authorizes the metadata-only commit?** The P2 metadata-commit rule (§18.3): Km carries exactly one OperationMetadataProjection path, admitted by the exact deterministic metadata proof C-2(Km), not by a Review. The Receipt authorized Kp; Km records that use.
- **How is recursion terminated?** OperationMetadataProjection is never normative (`projections.normative()`, Candidate 7 §4.3), so it is outside what Review authorizes. Km is proven, never reviewed, and a Km mismatch is `reconcile_required`, never a re-review.
- **When does push become permitted?** Once `publication_proof` is recorded, a re-run of C-2(Km) right before recording the push stage passes, and the publication barrier is clear for Km (§18.7). At classification and apply time the mutation-level validator re-checks the binding and the barrier again (§18.4, §18.7).
- **What if persisted proof fails after the local registration commit?** §15.5: no Consumption, and the barrier keeps every history holding Kp unpublished by Workline.
- **What if Consumption write succeeds but its publication does not?** The planning mutation stays pending with Km local. The Receipt counts as consumed locally, and until a push carries Km the destination holds no part of Kp or Km: no Workline push publishes Kp without Km (§18.7). A retry re-runs C-2(Km) when the note is missing, then records or applies the push under the live push classification (`=`, `*`, ` `, `!`) and the barrier. A destination that holds another history is `reconcile_required`, never forced. No second Consumption can be written (reserved ID + §16.3). Another operation's push from Km or a descendant may publish Km as history, since the barrier is clear for it; the retry then classifies Km as already published.
- **What if the registration commit is accidentally published before Consumption?** No Workline push can do that: the barrier refuses every push — this operation's and every other operation's — whose history holds Kp without its Consumption (§18.7). Only a person can push it by hand (manual Git). The resume then continues unchanged — C-2(Kp) if not yet recorded, Consumption, Km, C-2(Km), push of Km — and nothing about Kp being at the destination is read or relied on; the push fast-forwards the destination from Kp or from any subsequent commit (classified as live). If C-2(Kp) fails, §15.5 applies and the barrier stays.
- **Retry / resume in each case:** §21.

No reset, rebase, amend or deletion of a commit occurs anywhere.

## 18. P2 planning publication contract (C-1)

### 18.1 Shape

**Frozen.** `review-v1-planning-publication-v1`:

```text
Kp commit-only  ->  C-2(Kp) = recorded Consumption  ->  Km commit-only  ->  C-2(Km) = publication_proof note
                ->  push-only stage publishing exact Km
```

One push per planning operation. It publishes Km and its history: Kp, the Run's generation commits, and base history. Once Km is committed, any other Workline push from Km or a descendant may publish it as history too; before that, no Workline push publishes Kp (§18.7). This is not the current-combined shape (Frozen P1 R5 §12.1), and it is not the Work-terminal `review-v1-split-v1` contract (R5 §12.2, with its ReviewValidity bindings). It is a separately named P2 contract.

### 18.2 Metadata proof over Km — C-2(Km)

**Frozen.** Contract `review-v1-planning-proof-v1`. Any failure → `ReconcileRequired` (reason `review_metadata_commit_mismatch`), no push, Km stays local:

| # | condition |
| --- | --- |
| M1 | Km is the planning mutation's own commit (recorded `applied` with `commit_id`); Km has exactly one parent Q; Q is Kp or descends from Kp, and `gitcmd.commits_touching(Kp, Q, planning-owned paths) == []` |
| M2 | HEAD on `review_binding.branch`; that branch holds Km |
| M3 | `diff-tree` of Q → Km is exactly one entry: the Consumption path, status `A`, mode `100644`, blob bytes == the recorded `create_file` content |
| M4 | Km's tree holds every Run record (snapshot, task input, gates 1–3, Receipt) and the Consumption with mode `100644` and bytes == their canonical bytes as `ReviewStore` reads them, no gate 4 and no Supersession of the Receipt, and every registration path with the same blob ID as in Kp |
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

**Frozen.** Stage `review-publication`, recorded only when the Project has a verified push destination, after `publication_proof`, after M1–M5 are re-run, and with the publication barrier clear for Km (§18.7). It holds exactly one effect: `git_push` with payload `{remote, branch, locator, commit: <Km full ID>}` (the live three keys plus `commit`).

The mutation-level validator (`_recorded_publication`, planning branch) names the commit only when all hold:

- the discriminator selects the planning contract (§18.5);
- the push is the only effect of its stage and the last effect of the record;
- `payload.commit` is a full commit ID, equal to `publication_proof.metadata_commit`;
- the effect right before the push (by position and `seq`) is a `git_commit` that is the only effect of its own stage, recorded `applied` with `commit_id == payload.commit`, naming `refs/heads/<payload.branch>`;
- `publication_proof.registration_commit` equals the `commit_id` of the recorded, applied `review-registration-commit` effect;
- Km has one parent, and that parent descends from Kp;
- `gitcmd.commit_changes(Km)` ⊆ `{Consumption path}`;
- the branch holds Km.

Otherwise it names nothing, and the push is refused (`reconcile_required`). Classification and push are live and unchanged: a dry run of the exact refspec `<Km>:refs/heads/<branch>`, `=` published, `*` / ` ` unpublished, `!` a read-only destination read; never forced, never a branch tip. The publication barrier is evaluated again for Km whenever the dry run shows the push would write, and right before the push (§18.7).

### 18.5 Discriminator

**Frozen.** Selection is read from the durable invocation only, never from stage shape, content or Review files (Frozen P1 R5 §12.3.2):

| durable invocation | publication rule |
| --- | --- |
| no `review_contract`, no `publication_contract`, operation not `review-generation` | current-combined: the live `_recorded_publication`, unchanged (R5 §12.3.1 case A) |
| `review_contract == review-v1-planning-v1` and `publication_contract == review-v1-planning-publication-v1` and operation in {`roadmap-create`, `phase-entry`} | planning publication (§18.4); a combined commit + push pair in such a mutation is refused |
| operation `review-generation` | publishes nothing: a recorded `git_push` is refused, and P2 never records one there |
| any other presence, value or combination | fail closed (`reconcile_required`), never current-combined |

Legacy mutations carry no marker and get exactly the live rule. R5's `review-v1-split-v1` value is not recognized by P2; P3 adds it for START under R5.

The publication barrier (§18.7) is not a publication contract and is not selected here: it applies to every push, whichever contract names the commit that push publishes.

### 18.6 Authority for the shape

`rules/git` Push destination currently says a push is the last effect of its Git stage, right after that stage's only commit. The planning shape and the publication barrier need the amendments of §26.1. Until the implementation lands, no planning publication exists, and no planning registration commit exists for the barrier to concern.

### 18.7 Publication barrier

**Frozen.** No Workline push — of a review-v1 planning mutation, of a legacy mutation, of any operation — publishes a commit whose history holds a review-v1 planning registration commit that no proven Planning Consumption binds. The barrier is computed from committed Git objects only: no commit message, branch position, runtime note, mutation record, remote state or human convention takes part, so a process crash, the lock's release, another operation, runtime cleanup, runtime-record loss or a fresh clone cannot remove it.

**Durable source.** For a commit C, read entirely from Git objects reachable from C:

1. *planning Runs in C's history*: every Candidate snapshot blob added in C's history under `.workline/review/candidate-snapshots/`, read as raw bytes and parsed by the P1 reader (`serialize.parse_canonical`, `records.CandidateSnapshot`), whose `material` is a `review-planning-candidate` of kind `roadmap-plan-v1` or `phase-entry-design-v1`;
2. *registration paths of each*: from the snapshot's Candidate content (§7.2 / §7.3) — `.workline/roadmaps/<roadmap.id>.md` and `.workline/phases/<id>.md` for every Phase (RoadmapPlan); `.workline/works/<id>.md` for every normal Work, the integration and, when present, the confirmation (PhaseEntryDesign). These are reserved IDs, which no other operation ever uses;
3. *registration commits*: the commits in C's history that add any of those paths. A commit adds a path when its tree holds the path and none of its parents' trees does; every parent of a merge is followed;
4. *proof*: C's own tree.

"Added in C's history" is read with `git log --full-history --no-renames --diff-merges=combined --diff-filter=A --name-only -z <C> -- <directory>` (**Measured**, §31: it lists a side-branch commit that adds a path and a merge that itself adds one, and lists an ordinary merge as adding nothing; without `--diff-merges=combined` the adding merge is missed), and each blob with `git cat-file blob <commit>:<path>`. A path that a subsequent commit deleted or reverted is still found: the barrier reads the history, not only C's tree. The snapshot is always in the history of Workline's own Kp: the Run's records must be committed at the commit Kp is made on (§17 item 6, §15.6 item 3, P12). Only a person who first removes the Run's records from the branch history and then commits the registration files by hand leaves the barrier nothing to read — manual Git, which Workline does not control and never treats as a registration it made.

**Rule.** For every planning Run of step 1 whose registration paths are added in C's history (a *registered Run*), all of these must hold:

- exactly one commit K in C's history adds any of its registration paths (C-2(Kp) proves that Kp adds every one of them at once, §15.3 P3);
- C's tree holds a Planning Consumption (version 2) that reads back through the P1 reader and the v2 reader, whose `authorized_candidate_hash` is the snapshot's `candidate_hash` and whose `persisted_result.registration_commit` is K;
- C's tree holds that Consumption's Receipt, which reads back and binds it (P1 `RECEIPT_CONSUMPTION_BINDING`), and no Supersession of that Receipt.

Otherwise the barrier holds for C: `StopError` code `review_publication_barrier`, naming the Run's `candidate_hash` and K. A second commit adding one of those paths — a cherry-pick of Kp, or a person deleting and re-adding the files — keeps the barrier holding until a person reconciles: which commit is the registration is never guessed from content. A blob that cannot be read or parsed, a planning snapshot whose content does not yield its registration paths, or a Git question that cannot be answered is the barrier holding, never a clear barrier.

**Where it is checked** — every point at which Workline records or makes a push:

| point | commit evaluated | when it holds |
| --- | --- | --- |
| `gitops.finalize`, before recording a Git stage that holds a `git_push` (every current-combined stage with a destination) | HEAD, the parent of the commit the stage will make; that commit adds only its operation's own paths, never a planning Candidate snapshot or reserved registration path | the stage is not recorded; its mutation stays pending with its domain effects applied and continues once the barrier clears |
| before the planning `review-publication` stage is recorded (§18.4) | Km | the stage is not recorded; the planning mutation stays pending |
| the freeze of a review-v1 planning call with a push destination (§14.4 step 5) | HEAD | the call stops before any Review record; the planning mutation is abandoned |
| `MutationController._classify_push`, when the dry run shows the push would write (`*` or ` `) | the commit the record names (`_recorded_publication`, or the planning validator of §18.4) | the push is not classified unapplied: STOP, nothing pushed |
| `apply_effect` `git_push`, right before `gitcmd.push` (after the locator re-resolution) | the same commit | STOP, nothing pushed |

Apart from the freeze row, which stops a review-v1 call before it builds a new registration on a history no Workline push may publish, it refuses publication only. A commit-only stage is never refused: generation commits, Kp, Km, a remote-less finalization and Project start commit as before. A push classified as already published — `=`, or `!` with the destination holding the commit (`_published_under`) — pushes nothing and is not refused: classifying a commit as already at the destination publishes nothing and proves nothing, and it is never read as proof of Kp.

**Begins** when a commit adding a registered Run's paths enters the history of a commit Workline would publish: Kp, or a person's commit of the planning mutation's working-tree registration. Generation commits, a sealed Receipt, generation 4 and a registration held only in the working tree begin nothing: no registration commit exists, and every current-combined commit carries only its own paths (`git commit --only`).

**Ends** only when the commit being published holds the Consumption that binds K: Km, or a descendant that still holds it. Never by a Supersession, a remote state, a commit message, a branch position, a runtime note, the planning mutation's completion or its loss. A commit between Kp and Km never becomes publishable by its own push; it reaches the destination as history of Km or of a descendant of Km, after which its own push is classified as already published.

**Kinds.** The two planning kinds. A snapshot of any other kind concerns no planning registration and is passed over; P3 adds its own rules.

**Remote-less Projects** record and make no push, so the barrier is never evaluated there; C-2(Km) completes the operation (§12).

**Legacy.** In a history that holds no planning Candidate snapshot — every Project that never ran a review-v1 planning invocation — step 1 finds nothing and the barrier refuses nothing: every legacy outcome is unchanged. It is not a Review gate on the legacy operation: it asks nothing of the operation itself (no Review, no Receipt, no activation), only that what it publishes carries no unproven review-v1 registration, so HUMAN-1 = A holds.

| state of a Run | barrier |
| --- | --- |
| generation 1 or 2 only; generation 3 without a registration commit; generation 4 | none: no registration commit |
| not authorized; stale before or after the seal | none |
| registration applied to the working tree, Kp not made | none; a person's commit of those files is a registration commit and begins it |
| Kp made, C-2(Kp) not run | holds |
| C-2(Kp) failed | holds until a person reconciles the branch history |
| Consumption recorded, Km not made | holds: no committed Consumption |
| Km made | clear for Km and its descendants; holds for commits between Kp and Km |
| Km published | clear |
| runtime record lost with Kp unproven | holds for good: Kp can no longer be proven (§15.2), and a person reconciles |
| fresh clone | the same answer from the same objects |
| a person pushes Kp by hand | Workline cannot prevent it; the barrier still holds for every Workline push, and the remote copy is never read as proof |

**No unrecoverable global block.** The barrier concerns only histories that hold an unproven registration commit — exactly the histories that must not be published — and every other history publishes as before. It ends when the Consumption is committed (the planning operation's retry) or when a person takes the unproven commit out of the branch history; a Run that registered nothing (orphaned at any generation, not authorized, stale) never begins it.

**Why not the Receipt alone** (the direction the independent review proposed to investigate): a sealed, unsuperseded, unconsumed planning Receipt is also the state of a Run whose planning mutation was lost after the seal and before any registration. No P2 path can consume or supersede that orphaned Receipt (only its own planning mutation holds the reservation that would), so a Receipt barrier would stop every Workline push from that history for good over a Run that registered nothing. The registration commit is what must not be published unproven; the Candidate snapshot, committed before any registration, names exactly its paths; and the Consumption, committed only after C-2(Kp), is what ends it. `ReviewStore` reads only the working tree, so the barrier reads the same records from committed objects with the same P1 parser (§27).

## 19. Terminal review outcomes

### 19.1 Not authorized

**Frozen.** The Run's latest generation is 2 with settled tasks, and some task is `failed` or there are unresolved obligations.

| question | answer |
| --- | --- |
| durable Review records | candidate snapshot, task input, gates 1 and 2: committed locally by generation mutations 1 and 2 |
| Receipt | none (no seal) |
| Consumption | none |
| registration | none: no Roadmap, Phase, Work or relation is written; the reserved domain IDs are never used |
| Review commits published | not by this operation; they stay local and reach the destination as base history of the next push from that branch (`rules/git` Push destination); they hold no registration commit, so the publication barrier never concerns them (§18.7) |
| planning mutation | `complete()` with no effect recorded (its record follows the live retention rule) |
| result | `ReviewedPlanningResult(status="not_authorized", registration=None, receipt_id=None, consumption_id=None, findings=<the report's findings>)` |
| corrected plan or design | a fresh call: a new planning mutation, new reserved IDs, a fresh Candidate, a new Run. For Phase entry the Phase is still unexpanded, so the call is accepted |
| reserved domain IDs | never reused |
| retry of the identical request | a new Run and a new review; P2 does not remember the refusal |
| crash between the settlement and `complete()` | the next run recomputes "not authorized" from the chain and completes |

The Project is not blocked: the pending planning mutation is gone, and the immutable Review history stays.

### 19.2 Stale

**Frozen.** Detected by §13 only while no registration stage is recorded; two cases:

| question | stale before a Receipt exists (§13.2) | stale after the Receipt (§13.3) |
| --- | --- | --- |
| detected | right before the reviewer launch, or right before generation mutation 2 or 3 starts | at the use check (§17 item 7) |
| Review records written for it | none — no generation, no Supersession (there is no Receipt to supersede) | generation 4 (`open`) and the Supersession of the Receipt, one stage, committed and proven persisted before the planning mutation ends |
| Receipt | none | superseded, never consumed |
| registration | none | none |
| publication barrier | none (no registration commit) | none (no registration commit) |
| planning mutation | `complete()` with no effect recorded | `complete()` with no effect recorded, only after generation 4 is persisted |
| result | `ReviewedPlanningResult(status="stale", receipt_id=None, consumption_id=None, registration=None, findings=<the settled report's findings when a settlement exists, else ()>)` | `ReviewedPlanningResult(status="stale", receipt_id=<the superseded Receipt>, consumption_id=None, registration=None, findings=<the settled report's findings>)` |
| `detail` | the reason code of §13 | the reason code of §13, as the Supersession records it |
| a fresh call | a fresh Candidate and a new Run | a fresh Candidate and a new Run |

A difference found once a registration stage is recorded is never `stale` (§13.4).

### 19.3 Result type

**Frozen.** In `workline.roadmap_review`; `workline.roadmap` imports it inside the review-v1 branch:

```python
@dataclass(frozen=True)
class ReviewedPlanningResult:
    status: str                    # "registered" | "not_authorized" | "stale"
    operation: str                 # "roadmap-create" | "phase-entry"
    mutation_id: str               # the planning mutation
    review_run_id: str
    receipt_id: str | None         # set when a Receipt exists (for "stale" after the seal: the superseded Receipt)
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
| equality | projection identity + P3–P10 and P12 | same + P9 |

The same `normalize_persisted` runs at three points with three names: the representability check (§7.6, on the projection), the working-tree round trip (§15.1 step 2), and the persisted proof (§15.3, over the committed result).

## 21. Crash and recovery matrix

Terms (reconnaissance §12):

- **resume**: the same pending mutation continues from its record;
- **replay**: recorded effects are classified again and only unapplied ones are applied;
- **retry**: an external action is repeated under the same identity (the same task, the same exact push);
- **reconcile**: STOP with the record untouched;
- **fresh Candidate**: a new planning mutation and a new Run;
- **terminal**: not authorized or stale (§19).

Baseline conditions for rows 1–38: the runtime record is intact, HEAD is on the bound branch, and nobody changed a written path. Rows 39–45 are runtime loss and fresh clones, rows 46–51 other conditions at any window; the variants follow the table.

| # | window | behaviour of the next same-request run |
| --- | --- | --- |
| 1 | planning mutation begun, domain IDs reserved, freeze incomplete | resume; freeze recomputed deterministically (same reservations). A STOP here abandons the planning mutation (§12) |
| 2 | Run / task / Receipt / Consumption IDs reserved, `review_binding` noted, no generation mutation yet | resume; generation 1 starts; a STOP here still abandons (no generation mutation has started) |
| 3 | generation 1 begun, no effect recorded | resume planning; the pending generation mutation is abandoned; N = 1 computed again; a new generation 1 starts (no fork: nothing physical exists) |
| 4 | Candidate snapshot / task input / gate 1 recorded, some applied | resume generation 1; replay (`create_file` applied_matching skipped, unapplied created, mismatch → reconcile); commit; persistence proof; complete |
| 5 | generation 1 committed, not completed | resume generation 1: commit matched by its ID; persistence proof; complete |
| 6 | generation 1 complete, reviewer not launched | launch checks (§10.3), currency included: stale → terminal `stale` before a Receipt (§13.2), nothing written; otherwise the task is launched from the stored TaskInput |
| 7 | reviewer launched; process died, callback raised or returned invalid | retry: the same `task_id` launched again; nothing was settled; an in-memory result is lost |
| 8 | reviewer returned, runtime report copy written, generation 2 not begun | retry: the reviewer is launched again (the runtime copy is never settlement material) |
| 9 | generation 2 recorded, not applied / not committed | resume generation 2; replay; the reviewer is not called again |
| 10 | generation 2 complete | not authorized → terminal `not_authorized` (no currency evaluated); authorized → currency: stale → terminal `stale` before a Receipt (§13.2), no generation written; current → generation 3 (seal) starts with the Receipt ID reserved at the freeze |
| 11 | generation 3 + Receipt partially applied | resume generation 3; replay the remaining `create_file`; commit; persistence proof; complete (Frozen P1 R3 §7) |
| 12 | generation 3 sealed and committed, crash, no registration stage recorded | resume planning; no pending generation mutation; the use check runs again (it is not durable until the first registration stage is recorded): pass → `use_check_head` noted, registration (rows 17–19); stale → row 13 |
| 13 | stale detected after generation 3 (use check item 7) | generation mutation 4 (`invalidate`): gate 4 + Supersession recorded in one stage, applied, committed, proven persisted, completed; then the planning mutation completes `stale` with the superseded Receipt (§13.3) |
| 14 | generation 4 begun, no effect recorded | the pending generation mutation is abandoned; the use check runs again: current → the unsuperseded Receipt goes on to the registration; stale → generation mutation 4 starts again |
| 15 | generation 4 stage recorded, partially applied (gate 4 without the Supersession, or the reverse, or both applied and not committed) | resume planning; the pending generation mutation 4 is found through the token and resumed: replay the remaining `create_file` (absent → created, exact bytes → matching, other bytes → reconcile), commit, persistence proof, complete; then latest generation 4 → terminal `stale` |
| 16 | generation 4 committed (completed or not), planning mutation not completed | resume planning; a pending generation mutation 4 is finished first (row 15); the chain ends at generation 4 with its Supersession → terminal `stale` with nothing evaluated again; `complete()` |
| 17 | use check passed and noted, registration stage not recorded | the use check runs again and notes `use_check_head` again; a registration path changed since the freeze stops it with `dirty_overlap`, nothing written |
| 18 | registration effects partially applied | resume; `_open` projects and replays (live `refuse_invalid_phase_writes` / `refuse_invalid_work_writes` first); the subsequent stages continue from their records; the use check never runs again and `stale` is no longer an outcome (§13.4) |
| 19 | registration fully applied, round trip / pre-Kp proof not run, Kp not recorded | resume; the round trip runs; the pre-Kp currency proof on P = HEAD (§15.6): pass → Kp recorded with `base_head` = P and `base_exact`, and made; failure → `ReconcileRequired`, nothing committed, no Consumption, pending |
| 20 | HEAD advanced after the use check (a disjoint-scope operation's commit in a crash window, or a person's) | the pre-Kp currency proof decides on the new HEAD: P descends from `use_check_head`, no commit since touched a planning-owned path, and currency holds on P → Kp is made on P; otherwise `ReconcileRequired` (`review_registration_base_moved` / `review_registration_currency_changed`), nothing committed |
| 21 | Kp recorded, not made | `_open`'s `refuse_recorded` runs the pre-Kp currency proof with P = the recorded `base_head` first: HEAD == P and the proof passes → the replay makes Kp on exactly P; otherwise `ReconcileRequired`, Kp not made (`base_exact`: never the independent-advancement rule) |
| 22 | Kp made, `commit_id` not saved | reconcile (`review_commit_unowned`, §15.2); Kp can never be proven, so the publication barrier holds for every history holding it (row 25) |
| 23 | Kp made, `commit_id` saved, C-2(Kp) not run | the proof runs over the recorded Kp (P1–P12); the barrier holds for Kp until the Consumption is committed in Km |
| 24 | C-2(Kp) failed | reconcile (§15.5); no Consumption; every retry repeats the same proof; no generation 4; the barrier holds for every history holding Kp; no reset, rebase or amend |
| 25 | another Workline operation attempts a push while Kp is unproven (rows 22–24, 26–28) | `review_publication_barrier` (§18.7): its current-combined stage is not recorded (the mutation stays pending with its domain effects applied), or its recorded push is not classified unapplied / not applied; nothing is pushed and the destination never receives Kp; it continues once Km is committed and published (its commit then fast-forwards over Km, or is classified already published) — or, when Kp can no longer be proven, after a person reconciles the branch history |
| 26 | C-2(Kp) passed, Consumption not recorded | the proof runs again (the Consumption record is its durable checkpoint); Consumption recorded |
| 27 | Consumption recorded, not applied (a single immutable create: absent or exact) | `_open` replay creates it; exact bytes already present → matching; anything else → reconcile |
| 28 | Consumption applied, Km not recorded / not made | Km recorded / made (live base rules, M1 bounding its parent); a Km without a saved ID → `review_commit_unowned` |
| 29 | Km made, C-2(Km) not run or failed | proof runs; failure → reconcile, no push |
| 30 | C-2(Km) passed, `publication_proof` not noted | proof runs again; note recorded |
| 31 | Km local, publication pending (note recorded, push stage not recorded) | C-2(Km) re-run; the barrier is evaluated for Km; push stage recorded. The barrier holds only while Km's history holds another Run's unproven registration commit: then `review_publication_barrier`, pending. Another operation's push from Km or a descendant may publish Km meanwhile |
| 32 | push stage recorded, not applied | `_open` replay: planning validator (§18.4), dry run, barrier, exact push |
| 33 | pushed, `applied` not saved | dry run `=` → matching (nothing pushed; not a barrier point) |
| 34 | published, before `complete()` | everything matches; structure postcheck; complete |
| 35 | after `complete()` | record removed per the live rule; the same request again → a new planning mutation, fresh Candidate, new Run (Roadmap: a second Roadmap, as in legacy; Phase entry: `phase_already_expanded`) |
| 36 | a person pushes Kp (or a descendant) by hand before Km | Workline cannot prevent it and never treats it as proof: the planning resume still runs C-2(Kp) over the local objects and writes the Consumption only if it passes; every Workline push of a history holding Kp stays refused until Km is committed; if C-2(Kp) fails, row 24 |
| 37 | not authorized decided | terminal; after a crash before `complete()`, recomputed from the chain |
| 38 | stale before a Receipt decided (rows 6, 10) | terminal; after a crash before `complete()`, recomputed (currency evaluated again: current → the flow goes on; stale → terminal); nothing to finish |
| 39 | runtime record lost with no generation, generation 1 only, or generation 2 | nothing to finish. The Run is a legal orphan whose latest generation has status `open` (or a half-written stage when lost inside one, reported by `validate_review` and inert, §11.11). No Receipt, no registration commit, no barrier. The same request → fresh Candidate |
| 40 | runtime record lost with generation 3 sealed and no registration commit | the orphaned Receipt is never used or superseded (§11.11) and no barrier exists. Registration files applied to the working tree before the loss stay uncommitted: no current-combined commit and no other Kp carries them (`git commit --only`), a new review-v1 call refuses them with `dirty_overlap` where they overlap its own paths (a ledger, §14.2), and discarding them is a person's cleanup, as after a lost legacy registration. The same request → fresh Candidate |
| 41 | runtime record lost with a generation 4 stage recorded | fully applied: a legal orphan with a superseded Receipt; partially applied: a half-written invalidation, reported by `validate_review` and inert (§11.11). No barrier. The same request → fresh Candidate |
| 42 | runtime record lost while Kp is unproven (Kp made, no committed Consumption) | Kp can never be proven (its ID lived only in the lost record; no backfill, §15.2). The barrier holds for good for every history holding Kp: no Workline push of any operation publishes it. The same request does not lift it: a review-v1 call with a push destination stops at its freeze (`review_publication_barrier`, §14.4); a legacy Roadmap creation registers, and its own push is refused by the same barrier; a Phase entry meets `phase_already_expanded`. A person reconciles by taking Kp out of the branch history (a person's Git action; Workline never resets, rebases or amends) — "fresh Candidate" is not an answer here |
| 43 | runtime record lost with Km made (Consumption committed), not published | the registration is proven canonically; the barrier is clear for Km and descendants, so the next Workline push from the branch publishes Km as history. C-2(Km) may never have run, but Km was made by the contained primitive with `--only` of the Consumption path. The same request → a second Roadmap / `phase_already_expanded` |
| 44 | fresh clone, safe checkout semantics (the checked-out commit holds the committed rule, no clone-local override) | every Review record checks out as its canonical LF bytes (**Measured**, §14.5); `ReviewStore` and `validate_review` read them; the clone holds no runtime record, so each Run is in the runtime-loss state of rows 39–43 by its committed records; the barrier gives the same answer from the same objects |
| 45 | fresh clone, unsafe checkout semantics (no committed rule at the checked-out commit, or a clone-local `info/attributes` override) | Review records may check out as CRLF: `ReviewStore` refuses them (`review_record_noncanonical`, P1 unchanged, nothing normalized); a review-v1 planning call there stops at the freeze (`review_checkout_unsafe` / `review_namespace_unreadable`) with nothing written; legacy operations are unaffected; the barrier is unaffected (it reads raw blobs) |
| 46 | branch changed at any window | reconcile (binding §11.5, live `_require_decided_branch` / `_require_finalized_branch`); checking out the bound branch continues |
| 47 | remote moved | live push classification: destination holds Km → matching; another history → reconcile, never forced; a push that would write is also held to the barrier |
| 48 | canonical Review record tampered | reconcile: `create_file` applied_mismatch, `ReviewStore` refusal, or a blob / M4 / P12 mismatch; never re-reviewed or repaired |
| 49 | pre-existing dirty path | refused at the freeze with `dirty_overlap`, planning abandoned, nothing written (§14.2); a change after the freeze on a written path → live own-bytes reconcile |
| 50 | POSIX with review-v1 | `review_create_unsupported` before the lock; nothing exists |
| 51 | checkout capability missing or lost | at the freeze: `review_checkout_unsafe`, planning abandoned, nothing written; after generation 1 (the rule removed while pending): the next Review-writing or Git stage stops, the planning mutation stays pending, and continues once the rule is back |

Variants at any row: a different request or design → `reconcile_required` (live); a legacy invocation against a review-v1 record, or the reverse → `reconcile_required` (§5.3); a pending generation mutation bound to another planning mutation → reconcile (§11.8); structure changed by an independent operation while pending → the live projected refusal (`postcheck_failed`) before replay; the parent Roadmap held while a Phase entry is pending → the live Phase-entry precheck STOP, continued after resume; that hold committed after the use check → the pre-Kp currency proof decides (a declared-base difference is `ReconcileRequired`, §13.4).

Nothing in the matrix is the P3 Work-terminal recovery contract.

## 22. Lifecycle separation

**Frozen** invariants:

1. `state.py`, `ProjectView`, `validate_structure`, Phase selection, Work selection, startability and Roadmap progression never read a Receipt, Consumption, gate generation, Supersession, snapshot or task input. `state.py` stays byte-identical, and the existing pin `test_review_authority` (no "review" in `state.py`) holds.
2. A review-v1 planning operation reads only its own Run's records, as the authorization of its own planning mutation.
3. There is no cross-operation Review precondition. For example, "Phase entry requires the Roadmap to possess Receipt X" is prohibited: a PhaseEntryDesign Review reviews its own design, whatever the Roadmap's history. The publication barrier (§18.7) is not such a precondition: it asks no operation for a Review or a Receipt, and only keeps an unproven review-v1 registration out of what a push publishes.
4. The R9 canonical first Work is computed from `ProjectView`, never from a Review record.
5. A broken Review record stops a review-v1 planning operation that relies on it. It cannot reinterpret lifecycle history, because nothing that derives lifecycle reads it.
6. The committed-result loader (§15.4) feeds only the proofs and the currency evaluations (§13); its `ProjectView` is never used to decide lifecycle or progression.
7. A review-v1 Roadmap creation or Phase entry writes no event, so the lifecycle it leaves is identical to a legacy call's (Measured, reconnaissance probes 2, 5, 8).
8. The publication barrier (§18.7) reads Review records and history only to decide whether a push may publish. It derives no lifecycle and changes no lifecycle fact: a legacy operation it holds back has applied exactly the effects it would have applied, and only its commit and push wait.
9. Generation 4 and the Supersession (§13.3) are authorization records only: invalidating a Receipt changes no Work, Phase or Roadmap state, and nothing that derives lifecycle reads them.

P3 stays inactive: no activation record, no Work-terminal Consumption, no START change.

## 23. P1 seam disposition

| seam | frozen P1 text | disposition |
| --- | --- | --- |
| C-1 publication discriminator scope | R5 §12.3.1: Review-v1 durable metadata without `publication_contract` fails closed; R5 §12 enumerates two shapes for the operations it governs | **CLOSED BY P2 CONTRACT.** The planning mutation's durable invocation carries `publication_contract = review-v1-planning-publication-v1` from `begin` (R5-IMPL-2 satisfied). P2 implements the discriminator's first branches (§18.5): legacy → current-combined unchanged, planning → planning publication, generation mutations never publish, anything else fails closed. R5 §12.1 / §12.2 are unchanged; R5's `review-v1-split-v1` remains P3's |
| C-2 planning Consumption binding | R8 §8, R9 §9 | **CLOSED BY P2 CONTRACT.** Planning Consumption v2 with `persisted_result` (§16), written after C-2(Kp), stored in Km, binding Kp without self-reference |
| C-3 persisted proof / publication ordering | R8 §5–§9, R9 §7–§10, Candidate 7 §4.4 / §11 | **CLOSED BY P2 CONTRACT.** Direction A (§15, §17, §18), with the round-1 repair: the cross-operation publication barrier (§18.7), the use-check head, the base-exact Kp and full currency on Kp's parent (§15.2, §15.3 P12, §15.6) |
| C-4 generation mutation / same-run serialization | R2 §4, R3 §2, §8 | **CLOSED BY P2 CONTRACT.** Direction A (§11), R2/R3 and the helper unchanged; abandonment gap closed (§12); the R3 §8 invalidation generation is generation mutation 4 under the same serialization (§11.6, §13.3) |
| C-5 owning mutation invocation binding | R3 §9 | **CLOSED BY P2 CONTRACT.** The planning invocation keeps the request identity and adds the two static markers (§5.2). Run / task / Receipt / Consumption IDs are planning reservations (§6.3). Each generation invocation binds run, generation, transition, Candidate / Context / Policy, obligation digest, Receipt ID and, for an invalidation, its reason (§11.2). The planning mutation binds the Receipt, Candidate, Context and obligation through its recorded Consumption effect and `persisted_result`. `proof_phase` (Candidate 6 §11) is the planning mutation's recorded stage position plus the `publication_proof` note, re-checked before recording the registration and the push |
| C-6 runtime-loss same-task / Run rerun | R2 §5, R3 §4 | **CLOSED BY P2 CONTRACT.** P2 never continues a Run after runtime loss: a fresh Candidate and a new Run are required (§12, §21 rows 39–43). A task of an orphaned Run is never rerun, and never under a substitute ID, so R2 §5 / R3 §4 hold vacuously. The orphan Run stays valid (a half-written stage is reported and inert, §11.11). A lost Run that left an unproven registration commit is not a fresh-Candidate case: the publication barrier holds until a person reconciles (§18.7, §21 row 42) |

Every seam is closed.

## 24. Consistency with frozen P1 contracts and Candidate 7

| frozen text | how P2 satisfies it |
| --- | --- |
| R1 §2–§8 layout, immutable create | no new directory. Planning Consumption v2 in `consumptions/`, the Supersession in `supersessions/`; runtime material in `.workline/runtime/review/` (proofs, reports, no-hooks, attr-eval), allowed by R1 §3 |
| R1 §3 runtime data is never authorization | the publication barrier, the currency evaluations and every proof read committed objects; nothing in `.workline/runtime/` decides (§13, §18.7) |
| R1 §4 "Git persistence proof separately proves the committed path reproduces those bytes under the Git semantics bound by R6" | blob checks at every generation commit, M4, P4, P12; and the checkout capability (§14.5), which proves positively that the committed path reproduces the canonical bytes in this working tree and in a fresh clone; the strict reader (P1-REV-007) is unchanged |
| R1 §13 committability | `gate.require_committable` at the freeze and per writer |
| R2 §2–§5 | keys §6.2; reservations §6.3; no substitute task ID |
| R3 §1 ownership | Roadmap mutation owner writes every record (§11.1) |
| R3 §2 serialization | §11.3, §11.8, helper unchanged; generation 4 included |
| R3 §3–§4 launch after local persistence | §10.3 |
| R3 §6 full snapshot | every generation, generation 4 included (§11.6.1) |
| R3 §7 seal + Receipt one stage | §11.6 |
| R3 §8 invalidation | a stale sealed Receipt is invalidated before the planning mutation ends: generation 4 (`open`) and the Supersession in one stage, committed and persisted; the old Receipt never proceeds and is never consumed (§13.3). No Supersession without a Receipt (§13.2) |
| R3 §9 invocation binding | C-5 |
| R3 §10 local Git persistence boundary | §11.6; remote-less valid |
| R3 §11, Candidate 7 §2 no second controller | §22 |
| R4 §1, §7 uniqueness | §16.3 |
| R5 §5–§6 signing disabled, hooks suppressed as bound semantics | §15.2, Context `git_persistence` |
| R5 §12 publication shapes | §18: current-combined unchanged; planning shape separately named and selected by durable metadata, never by shape. R5 §12's "exactly two" enumerates the contracts of the operations R5 governs; P2 adds one R5 did not govern and changes none of R5's |
| R5 §12.1 "not weakened, narrowed or made conditional" | every check of `_recorded_publication` stays as it is; the publication barrier (§18.7) is a separate refusal evaluated after the commit is named, never a substitute for any check, and in a history without a planning registration commit it refuses nothing |
| R5 §12.5 "push already occurred but C-2 is absent → NEVER infer proof from push" | the barrier never reads the destination; a destination already holding a commit only means nothing is pushed for it (§18.7); a person's push of Kp is never proof (§15.5) |
| R6 §6, R11 §10 attributes and line-ending semantics as bound Git semantics | the checkout capability contract is bound in the Context (`checkout_capability`, §8, §14.5) |
| R8 §2–§11 | §7.2, §15.3, §16, §20 |
| R9 §2–§11 (as repaired) | §7.3, §7.7, §15.3 P9, §16, §20 |
| R11 git_state, completeness | the primitive identity is bound; Evidence completeness `unknown`, never reused |
| R12 §2 "clone reproduces canonical bytes/digest" | §14.5; tests §28 J |
| R12 §5 invalidation partial stage | §21 rows 13–16; tests §28 B |
| R12 §3, §8, §11, §13, §14 | test contract §28 |
| Candidate 7 §4.4 exact union | Kp proof: ReviewedArtifact + AuthorizedTransition + scope; Km proof: OperationMetadata + scope |
| Candidate 7 §11 local commit → exact proof → re-read | §15 |

No frozen P1 document needs repair for this contract. P2-CONTRACT-004 in particular closes as a P2 capability precondition: the P1 reader keeps refusing non-canonical physical bytes, and R1 §4 with R6 §6 already make the checkout semantics of Review paths part of the Git semantics a persistence proof is under; P2 proves them positively before it writes.

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
| effect payloads | `git_commit` gains the durable `mode` field (§15.2) and, for Kp only, `base_exact: true`; a planning `git_push` gains `commit` (§18.4); `validate_effect` accepts `mode` only as `review-v1-planning-local-v1`, `base_exact` only as `true` together with that `mode`, a full-ID `base_head` and a `branch`, and `commit` only as a full commit ID; legacy payloads are unchanged |
| `gitops.finalize` | unchanged signature and stages; before recording a stage that holds a push it evaluates the publication barrier on HEAD (§18.7), which refuses nothing in a history without a planning registration commit |
| new STOP codes | `review_publication_barrier` (any push, only when the published history holds an unproven planning registration commit); review-v1 only: `review_checkout_unsafe`, `review_checkout_unknown`, `review_namespace_unreadable`, `review_base_uncommitted`; `ReconcileRequired` reasons `review_registration_base_moved`, `review_registration_currency_changed` |
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
5. Success on publication: a review-v1 planning operation succeeds only once its registration is published (remote-less: once C-2(Km) is recorded); one that ends `not_authorized` or `stale` registers nothing, publishes nothing, and leaves its generation commits (for `stale` after the seal, generation 4 and the Supersession too) as local history that the next push from that branch carries.
6. Push destination, for every operation: no push publishes a commit whose history holds a review-v1 planning registration commit that no proven Planning Consumption binds (§18.7). It is evaluated before a stage holding a push is recorded, when a recorded push would write, and right before the push; a push the destination already holds is not refused, and nothing about the destination is read as proof.
7. Commit / push: the review-v1 registration commit is made only on its recorded parent (`base_exact`), never through the independent-advancement rule (§15.2).
8. Review-v1 planning requires the checkout capability for Review paths and a canonically readable Review namespace (§14.5, §14.6); Workline never edits `.gitattributes` or `info/attributes`.

### 26.2 `skills/roadmap`

- the opt-in (§5);
- the review-v1 flows of Roadmap creation and Phase entry (§14.4, §15.1);
- the R9 canonical self-selection rule, owned here (§7.7);
- the terminal outcomes and the fresh-Candidate rule (§12, §19), with stale before and after the seal (§13.2–§13.3);
- the currency rules: the declared base on the committed view, the use check with `use_check_head`, the pre-Kp currency proof and the reconcile-only rule once the registration began (§13, §15.6, §17);
- the operation binding (§11.5).

### 26.3 `skills/review`

- the planning kinds and identities (§6);
- the static policy record, verbatim (§9);
- the reviewer interface (§10);
- adjudication (§10.6);
- Planning Consumption v2 and uniqueness (§16);
- the planning transition state machine and generation 4 with its Supersession (§11.6);
- the planning publication contract (§18), with the publication barrier every Workline push is held to (§18.7);
- the checkout capability and the namespace readability precondition (§14.5, §14.6);
- the P2 scope of "適用範囲". Work terminal gating stays NOT ACTIVATED.

`skills/phase-create` and `skills/create` are unchanged: their registration cores are called exactly as today.

## 27. Implementation surface map

| file | purpose | contract sections | tests (§28) |
| --- | --- | --- | --- |
| `src/workline/review/planning.py` (new) | identifiers; `PlanningReview`, task, report and finding types; record builders (Candidate, Context, policy, request envelope, report, adjudication, obligations, coverage, report set, evidence, invalidation evidence); stale reason codes; report validation; loader identity; authority digests | §5.1, §6, §7.1, §8, §9, §10, §11.6.1 | A, B, C, D |
| `src/workline/review/committed.py` (new) | committed Review reading: paths added in a commit's history (`--full-history --diff-merges=combined --diff-filter=A`), raw blobs at a commit, parsed by the unchanged P1 serializer and record classes (and the v2 Consumption reader) | §15.3 P12, §18.7 | E, G |
| `src/workline/review/publication.py` (new) | the publication barrier: `barrier_problems(repo, commit)` over committed objects | §18.7 | G |
| `src/workline/review/checkout.py` (new) | the checkout capability: committed and effective attribute evaluation, the two forms; namespace readability | §14.5, §14.6 | J |
| `src/workline/review/records.py` | Planning Consumption v2 (reader and builder) beside v1 | §16.1–§16.2 | F |
| `src/workline/review/store.py` | v2 reading; registration-commit and target indexes | §16.3 | F |
| `src/workline/review/validate.py` | v2 validation, planning binding, uniqueness indexes | §16.2–§16.3 | F, H |
| `src/workline/review/paths.py` | runtime subpaths `proofs/`, `reports/`, `no-hooks/`, `attr-eval/` | §10.5, §14.5, §15.2, §15.4 | E, J |
| `src/workline/roadmap_review.py` (new, Roadmap-owned) | the review-v1 flow: freeze, generation mutations 1–4, reviewer call, currency on committed views, use check and `use_check_head`, registration hand-off, pre-Kp currency proof (and its `refuse_recorded` hook), Kp / Km, proofs, Consumption, publication, terminal outcomes; both adapters; `ReviewedPlanningResult` | §7, §11–§21 | A–J |
| `src/workline/committed_view.py` (new) | committed-result loader: materialization from raw blobs and `ProjectView.load`; delta reading | §15.3–§15.4 | E |
| `src/workline/roadmap.py` | `review=` keyword; marker check at the entry (§5.3); the registration of `_create_roadmap` / `_expand_phase` separated from the legacy `_finalize` without changing legacy behaviour; review-v1 branch | §5, §15.1 | A, B, I |
| `src/workline/gitcmd.py` | a bytes runner; `tree_entries`, `read_blob`, `commit_delta`, `check_attributes` (effective, and committed through the isolated evaluation directory), `added_paths`, `blob_at`; contained `add` / `commit` | §14.3, §14.5, §15.2–§15.4, §18.7 | E, G, J |
| `src/workline/gitops.py` | `review_commit_effect`, `review_publication_effect`, attribute preflight helper; the publication barrier in `finalize` before a stage holding a push is recorded | §14.3, §15.2, §18.4, §18.7 | E, G |
| `src/workline/mutation.py` (private functions only) | discriminator + planning publication branch in `_recorded_publication` (invocation threaded through `_classify_recorded` / `_publish`); `mode` in `apply_effect`; `base_exact` in `_classify_commit` and the planning primitive; the publication barrier in `_classify_push` and in `apply_effect` for `git_push`; payload validation | §15.2, §18.4–§18.5, §18.7 | E, G |
| `registry.md`, `.claude/skills/roadmap/SKILL.md`, `.claude/skills/review/SKILL.md` | authority text | §26 | C (policy pin) |
| `tests/test_review_planning_*.py` (new) | the test contract | §28 | — |

Expected not to change: `state.py` (no helper is needed), `store.py`, `validate.py` (`validate_structure`, `validate_project`), `start.py` and every START Work-terminal path, `create.py` and `phase_create.py` behaviour (at most a pure helper extracted with identical output), `ops.py`, `oplock.py`, `ids.py`, `implementation.py`, `cli.py` (Roadmap has no CLI), `review/gate.py`, `review/adapter.py`, `review/projections.py`, `review/closure.py`, `review/fsafe.py`, `review/serialize.py`, the P1 `GateGeneration`, `Receipt` and `Supersession` classes (generation 4 and the Supersession use them as they are), P3 activation code (none exists), and every unrelated operation — whose only new behaviour is the publication barrier on its push, inert without a review-v1 planning registration commit.

## 28. Test contract

Frozen minimum. Every test runs on real Projects through `tests/helpers.py`, through production code paths. A happy path alone is insufficient (Frozen P1 R12 §14). Section J and the round-1 items of B, D, E and G are the tests of the repaired guarantees (§33).

**A. Applicability**

- A legacy Roadmap creation and a legacy Phase entry are byte-for-byte unchanged: invocation, stages, commits, pushes and result. The existing suite passes unchanged.
- An explicit review-v1 Roadmap creation is gated; an explicit review-v1 Phase entry is gated.
- The opt-in cannot fall back to legacy: platform, checkout capability, Review namespace, Git transform, Context unavailable and reviewer failure each STOP, with no ungated registration.
- Both marker mismatch directions → reconcile with the record untouched (§5.3).
- An invalid `review` argument → `review_contract_invalid` with nothing written.
- POSIX, or a patched `immutable_create_supported() == False`, with review-v1 → `review_create_unsupported` before any lock or record. POSIX legacy is unchanged.

**B. Generation serialization and the transition state machine**

- An uninterrupted run leaves three generation commits before Kp, and no generation 4.
- A crash at every generation window (§21 rows 3–5, 9, 11) resumes correctly.
- A pending predecessor is resumed before N+1.
- A conflicting second owner (a pending generation mutation bound to another planning mutation) → reconcile.
- Two pending generation mutations → reconcile.
- A generation file created with its `applied` flag not saved → classified matching, no N+2.
- No fork and no skipped generation.
- The initial scope is exactly as §11.3, with no `extend_scope` on generation mutations.
- The dirty snapshot is taken at the start.
- The binding is enforced across mutations (branch switch between generation commits → reconcile).
- *P2-CONTRACT-002.* Generation 3 sealed → stale at the use check (authority text, the Policy constant, and a committed declared-base fact, one test each) → generation 4 `open` + the Supersession in one stage, committed and persisted, every field as §11.6.1, before the planning mutation completes `stale` with the superseded Receipt; `validate_project` clean afterwards.
- Interruption at every generation-4 window (§21 rows 14–16): no recorded effect (abandoned; the use check runs again — current again → the registration proceeds with the unsuperseded Receipt; still stale → generation 4 again); gate 4 created with its `applied` flag unsaved; gate 4 created and the Supersession not; both created, not committed; committed, not completed; generation mutation completed, planning mutation not.
- The old Receipt cannot be consumed: the use check refuses it, and a fixture Consumption of it is a `validate_review` problem.
- No fake Supersession before a Receipt exists: stale before the reviewer launch, before generation mutation 2 and before generation mutation 3 → no generation and no Supersession written, `validate_review` clean, result `stale` with `receipt_id=None`.
- Chain shape: generation 5 is never started; generation mutation 4 is never started once a registration stage is recorded; a pending generation mutation of the Run while a registration stage is recorded → reconcile; a transition out of order → reconcile.

**C. Authorization**

- The accepted → settled → sealed chain validates (`validate_project` clean).
- A seal with an unsettled task is refused (P1 invariant).
- An invalid Receipt (tampered, unbound) → reconcile at the use check.
- A superseded Receipt is refused, both from the real invalidation flow (B) and from a fixture.
- Not-authorized paths register nothing: HIGH, MID, `declined`, and a failed task; no publication barrier results from them (a subsequent legacy push proceeds).
- LOW findings do not block and are returned.
- The Skill policy block equals the code constant (canonical).
- Reviewer failures: a raised exception, an invalid report, and an identity mismatch.
- The same task ID is relaunched after a crash.
- A duplicate settlement through the P1 helper (the same report twice) is idempotent.

**D. Semantic projection and currency**

- The Roadmap and Phase-entry round trips are exact at all three points.
- Every reader-loss input of reconnaissance §10.2 and a lone CR are refused before Review (`review_candidate_unrepresentable`).
- Every R9 case of §7.7.
- The declared base changes before the seal → stale, nothing written (§13.2).
- *P2-CONTRACT-003.* Each of authority text, the Policy constant (patched), the loader identity (a package file changed) and a declared-base fact (a hold of the Phase's Roadmap committed by a disjoint-scope operation in a crash window) changed at four moments: after the review and before the registration (→ generation 4, stale); after the first registration stage and before Kp is recorded (→ pre-Kp currency proof `ReconcileRequired`, no Kp, no Consumption, no push, no generation 4); after the Kp stage is recorded and before it is made (→ the `refuse_recorded` pre-replay proof refuses, Kp not made); after Kp is made (→ C-2(Kp) P12 refuses, no Consumption, the barrier holds).
- HEAD independently advances after the use check: a disjoint-scope operation's commit that touches no planning-owned path and no declared-base fact → Kp made on the new HEAD, C-2(Kp) passes with P ≠ `use_check_head`; a commit touching a planning-owned path → `review_registration_base_moved`; a commit changing a declared-base fact → `review_registration_currency_changed`; a history that no longer holds `use_check_head` → `review_registration_base_moved`.
- Kp parent mismatch: HEAD moved between the Kp stage's record and its commit (fixture) → the base-exact rule refuses, Kp not made, never the independent-advancement path; a Kp forced onto another parent → P2 refuses.
- Full currency from Kp's parent: the declared base is read from the committed view of P — an uncommitted change of a declared-base fact changes nothing, a committed one is a difference; `review_base_uncommitted` at the freeze for a named entity present only in the working tree.
- A mismatch after the registration began → reconcile, no Consumption, no push, never `stale`.

**E. Persisted proof**

- Exact committed bytes and modes: a fixture changes a mode.
- Scope: an extra path, a missing path, and a ledger with an extra relation are each detected.
- The committed semantic reload uses the §15.4 loader.
- A Git transformation is detected. Two fixtures: an attribute (`filter`, `ident`, `working-tree-encoding`) refused by the preflight; and a transformation forced after the preflight, caught by P3 / P4.
- Proof failure prevents Consumption and publication, and keeps every subsequent Workline publication of Kp refused (G).
- Hooks (`pre-commit`, `commit-msg`, `post-commit` attempting a push or a file change), `commit.gpgSign=true` with a signing program, and a non-default `core.hooksPath` → none runs (Frozen P1 R12 §8).
- Kp without a saved ID → reconcile, and the barrier holds for it.
- P12: a gate 4, a Supersession or a Consumption of the Receipt present in P's tree (fixture) → refused.

**F. Consumption**

- The exact `persisted_result` binding for both kinds.
- One Receipt → at most one valid Consumption.
- A conflicting Consumption is refused (a second Consumption of the Receipt, of the registration commit, or of the target).
- A commit identity mismatch is refused (`registration_commit` ≠ Kp).
- A Candidate mismatch is refused (`authorized_candidate_hash` ≠ Receipt).
- An adapter identity mismatch is refused.
- A v1 Consumption with a P2 kind is invalid.
- v1 records are unchanged; version 2 has exactly the fields of §16.1.

**G. Publication**

- Interruption at every commit, proof and publish boundary (§21 rows 19–34).
- No push before proof: no `git_push` exists in the record before `publication_proof`.
- A foreign commit is not an operation-owned commit: a byte-identical Kp or Km made by another subject is never published as the operation's own.
- Branch switch → reconcile. Rewritten history → reconcile.
- Remote advancement: fast-forward, destination ahead holding Km, and diverged → reconcile.
- The retry publishes exactly Km.
- Discriminator: legacy is unchanged; a combined pair in a planning mutation is refused; a push in a generation mutation is refused; unknown or partial markers fail closed; shape and content are never selectors.
- A remote-less Project completes without a push, and no barrier is evaluated.
- *P2-CONTRACT-001.* A crash after Kp and before C-2(Kp); an unrelated Workline operation (a hold of another Roadmap: event log only) then runs and attempts its own push → `review_publication_barrier` before its stage is recorded; the destination's branch never receives Kp (read from the destination); after the planning retry proves Kp and publishes Km, the other operation completes and its commit is published on top of Km.
- The same with a current-combined stage recorded before Kp existed and its commit made on Kp by the independent-advancement rule → refused at classification (the dry run shows a write) and, with the classification patched, at application; nothing pushed; completed once Km is at the destination (classified already published).
- Retry after proof: once Km is committed, pushes from Km and its descendants pass; a commit between Kp and Km is never pushed by its own push.
- Kp proof failure keeps every subsequent Workline push of a history holding Kp refused — legacy and review-v1 — across a process crash, a deleted `.workline/runtime/`, runtime-record loss and a fresh clone.
- Runtime-record loss with Kp unproven → the barrier holds for good; the same request does not lift or bypass it (a review-v1 Roadmap call stops at its freeze with `review_publication_barrier`; a legacy Roadmap creation registers and its own push is refused; Phase entry: `phase_already_expanded`).
- A manual external push is detected but never accepted as proof: a person pushes Kp before C-2(Kp); the barrier still finds the unproven Kp in the history of every Workline push that would carry it, whatever the destination holds, so a legacy push of a descendant is still refused; the planning resume still runs C-2(Kp) over local objects; with C-2(Kp) made to fail, no Consumption is written although Kp is at the destination; and a push classified as already published writes nothing and is read as nothing more.
- A person's commit of the working-tree registration after a crash begins the barrier; the planning mutation classifies its Kp applied without an ID → `review_commit_unowned`.
- History does not hide Kp: a subsequent commit that deletes the Candidate snapshot or reverts the registration files → the barrier still holds; a merge bringing in a side branch with Kp → found; an evil merge adding a reserved path → found.
- Unparseable planning snapshot in the pushed history (fixture) → the barrier holds (fail closed).
- No barrier where nothing was registered: generation 1 only, generation 2, orphaned generation 3, generation 4, not authorized, stale — a legacy push proceeds in each.
- A legacy-only Project: the barrier finds no planning snapshot and refuses nothing; the existing suite passes unchanged.

**H. Lifecycle**

- Review metadata does not alter lifecycle (gated vs. legacy end states equal), generation 4 and the Supersession included.
- A tampered Review record does not reinterpret lifecycle: it stops only the gated operation relying on it.
- `state.py` is unchanged (pin).
- P3 stays inactive: no activation record, and START completion behaviour is unchanged.
- No cross-operation Review precondition: a legacy Phase entry on a review-v1-created Roadmap proceeds, and a review-v1 Phase entry on a legacy Roadmap proceeds.
- A legacy operation held back by the barrier has applied exactly its usual effects; only its commit and push wait.

**I. Dirty overlap**

- review-v1 refuses before any Review record or reviewer launch when a registration path, a Run record path (gate 4 and Supersession paths included) or the Consumption path is dirty.
- A registration path changed after the freeze stops the use check with `dirty_overlap`, nothing written, the planning mutation pending; a resume after generation 1 never abandons it.
- The person's bytes are untouched.
- The planning mutation is abandoned.
- The legacy late `dirty_overlap` behaviour is unchanged.

**J. Checkout capability (P2-CONTRACT-004)**

- `core.autocrlf=true` with no attribute rule → `review_checkout_unsafe` at the freeze, before any Review record; the planning mutation abandoned; nothing written.
- Positive: a committed form-L rule and a committed form-B rule each give the capability; a review-v1 run completes under `core.autocrlf=true`.
- A fresh clone, made under `core.autocrlf=true` and again under a global attributes file asking `*.yaml eol=crlf`, of a Project whose committed rule is in place keeps every Review record's physical bytes LF; `ReviewStore` reads each; `validate_project` is clean; a new review-v1 call there passes §14.5 and §14.6.
- Existing Review records of earlier Runs remain readable in that clone.
- Unsafe semantics are never silently normalized: a CRLF record (checked out before the rule, or under a clone-local `info/attributes` `eol=crlf`) → the P1 reader refuses it (`review_record_noncanonical`), the freeze stops (`review_namespace_unreadable`), and no byte is rewritten or normalized.
- A rule only in `.git/info/attributes` → the committed evaluation fails → `review_checkout_unsafe`.
- A committed rule overridden by a clone-local `info/attributes` rule → the effective evaluation fails → `review_checkout_unsafe`.
- The rule removed by a commit after generation 1 → the next Review-writing stage stops `review_checkout_unsafe`, the planning mutation stays pending, and continues once the rule is back.
- `check-attr` unanswerable (fixture) → `review_checkout_unknown`.
- The Context carries `checkout_capability: review-v1-planning-checkout-v1`.
- Legacy planning is unaffected: no evaluation and no refusal in a Project without the rule.

## 29. Incidental live findings outside P2

1. **Review records under checkout line-ending conversion (P1 layer).** **Measured** (§31): with this machine's system `core.autocrlf=true` and no attribute rule, a fresh clone checks out an LF-only Review record as CRLF while `git status` stays clean, and `serialize.parse_canonical` refuses it (`review_record_noncanonical`). For every Review record P2 writes, the checkout capability (§14.5) closes this: P2 writes Review records only where the committed attributes make every fresh clone reproduce the canonical bytes, proves it before writing, and refuses otherwise. No other path writes Review records at the baseline (P3 is not active). The P1 reader and the P1 documents are unchanged; this is recorded so that P3 and any subsequent Review writer carry the same precondition.
2. `gate.py:139` / `:149` print `record.get("id")` for pending generation mutations, which yields `None` (reconnaissance §6); message only.
3. The lone-CR stranding of legacy Roadmap creation and Phase entry (reconnaissance §17 item 1) remains in the legacy path; the review-v1 path refuses such input before Review (§7.6).
4. The late `dirty_overlap` of legacy Roadmap creation and Phase entry (BL-041 residual (4)) remains in the legacy path; review-v1 refuses early (§14.2).
5. A runtime lost inside a generation stage leaves a half-written stage that `validate_review` reports (Frozen P1 fail closed). P2 never repairs it and never refuses on it (§14.6); it is inert (§11.11).

## 30. Quality gates applied to this document

Searched, case-insensitively, after the round-1 repair, for `TBD`, `TODO`, `maybe`, `either`, `alternative`, `open`, `later`, `implementation decides`, `could`, `option`:

Outside this section:

- `TBD`, `TODO`, `maybe`, `either`, `alternative`, `implementation decides`, `could`, `option`: no occurrence (substrings included);
- `later`: only inside the verbatim quotation of Frozen P1 R3 §8 in §13.3;
- `open`: only as the P1 gate status literal `` `open` `` (also inside `` `status: open` ``), the live function and method names `_open` / `MutationController.open`, and inside the task's own labels "Architecture reopen" / "not reopened". None marks an unresolved item.

Also verified: no unresolved A/B choice (C-3 and C-4 name Direction A with reasons; §15.6 states why the equally strong invariant is chosen over bare equality with `use_check_head`); no implementation-defined identity (§6); every mutation owner specified (§11.1); Receipt / Consumption ordering specified (§17); commit / proof / push ordering specified (§15.1, §18); every recovery window specified (§21); no hidden HUMAN choice (§32); no P3 activation (§2, §22); no Review-as-lifecycle authority (§22, §34 item 10).

Round-1 search for the superseded statements: no statement that another operation may publish Kp (§15.5, §17, §18.7 say the opposite); no statement that staleness ends without invalidation once a Receipt exists (§13.3, §19.2); no fixed three-generation sequence (the state machine of §11.6); no statement that the declared base is not re-evaluated after the use check (§13.4, §15.6, P12); no statement that a fresh clone does not matter (§14.5, §21 rows 44–45, §29); and the checkpoint line "No push before proof: PASS" is replaced by the cross-operation line of §32.

## 31. Evidence

Probes are plain scripts (no pytest), run outside the repository; those that use Workline code run against the clone's `src` (`PYTHONPATH`) and assert that `workline` was imported from that tree. The round-1 probes build throw-away repositories only. Environment: Windows 11, Git for Windows 2.54.0.windows.1 with system `core.autocrlf=true`.

| probe | question | result |
| --- | --- | --- |
| autocrlf clone | what does a fresh clone do to an LF-only Review record? | blob LF (`git cat-file blob`); clone working tree CRLF; `git status` clean |
| hook suppression | does `-c core.hooksPath=<empty or absent dir>` suppress repository hooks for `git commit --only`? | default: a failing `pre-commit` hook ran and refused the commit; with an empty directory and with an absent directory: no hook ran, the commit was made |
| `committed_reload_probe.py` | does the production `ProjectView` read a commit's canonical files materialized from raw blobs exactly as it reads the working tree? | live Roadmap creation + Phase entry: 9 canonical files, all `100644`, committed reading == working-tree reading, `validate_structure` clean |
| reconnaissance probes 1–8 | accepted evidence (reconnaissance §18) | Direction A mechanics (probe 8), pre-reservation (probes 2, 5), reader loss (probe 1), projection equality (probe 4), lifecycle neutrality (probes 2, 5, 8) |
| checkout probe, part 1 (round 1) | which attribute conditions keep a Review record's bytes through a fresh clone under `core.autocrlf=true`, and can they be read from committed attributes alone, before the file exists? | no rule: clone CRLF, the P1 reader refuses (`review_record_noncanonical`), `git status` clean; committed `eol=lf -filter -ident -working-tree-encoding`: LF, accepted; committed `-text -filter -ident -working-tree-encoding`: LF, accepted; a rule only in the origin's `info/attributes`: clone CRLF, refused; committed `eol=lf` against a global `*.yaml eol=crlf`: LF, accepted; the global rule alone: CRLF, refused; `check-attr --source=HEAD` still reads `info/attributes`; the empty bare evaluation directory with alternates, `GIT_ATTR_NOSYSTEM`, and empty global configuration and attributes reads the committed rule alone (form L, form B, or all unspecified without a rule); `check-attr` answers for a path that does not exist |
| checkout probe, part 2 (round 1) | do clone-local sources or core settings override a committed rule? | a clone-local `info/attributes` `eol=crlf` overrides committed `eol=lf` after a re-checkout: CRLF, refused, `git status` clean, the effective evaluation shows `eol: crlf`; committed `eol=lf` and committed `-text` keep LF under `core.autocrlf=false` with `core.eol=crlf`; a subsequent commit dropping the rule: a fresh clone of it CRLF, refused |
| add-detection probe (round 1) | which `git log` form lists exactly the commits that add a path — present in the commit, absent from every parent — across merges? | the default form misses a merge that itself adds a path; `--full-history --no-renames --diff-merges=combined --diff-filter=A --name-only` lists the side-branch commit adding a path and the adding merge, and lists an ordinary merge as adding nothing |

Kept outside the repository with the reconnaissance evidence: `D:\AIproject\workline-evidence\cases\`.

## 32. HUMAN, architecture, checkpoint

HUMAN: **None.** HUMAN-1 is resolved (A). Every choice made here, the round-1 repair included, is an engineering choice bounded by live code and frozen text, and each has its reason stated in its section.

Architecture: Candidate 7 **RETAIN**; architecture reopen **No**; architecture blocker **None**. C-2, C-3 and C-4 close, and P2-CONTRACT-001..004 are repaired, inside Candidate 7's responsibility split: Review stays a subordinate gate, the Roadmap operation stays the only top-level owner, lifecycle stays event-derived, and the publication barrier is a publication rule over committed objects, not a Review gate on any operation.

```text
Contract baseline:              cdb152312006f6ac25533962d942ed77e2d98bd4
Contract under repair:          2f8771ae91df580453a0ebc026febe5c5a562cc0
P1 accepted checkpoint:         b78be1ccd778ceb2ecd97b90e2f71744bd1b3bc5
HUMAN-1:                        RESOLVED — A, per-invocation opt-in (review=PlanningReview)
C-1 .. C-6:                     CLOSED BY P2 CONTRACT
P2-CONTRACT-001 .. 004:         CLOSED BY ROUND-1 REPAIR (§33)
Generation contract:            Direction A — roadmap-owned generation mutations, R2/R3 unchanged;
                                G1 accept -> G2 settle -> G3 seal [-> G4 invalidate + Supersession]
Persisted-proof contract:       Direction A — Kp -> C-2(Kp) -> Consumption v2 -> Km -> C-2(Km) -> push Km
Registration base:              use_check_head; base-exact Kp on P; full currency on P's committed view
Unproven Kp publication:        refused for every Workline push (publication barrier, §18.7)
Checkout capability:            committed + effective attributes, form L or form B (§14.5)
Lifecycle separation:           PASS
P1 frozen contract repair:      not required
P2 Integration Contract:        FROZEN / ROUND 1 REPAIRED
P2 implementation:              NOT STARTED
P2 accepted for implementation: NO (pending independent contract re-review)
Candidate 7:                    RETAIN
Architecture reopen:            No
Architecture blocker:           None
HUMAN:                          None
P3:                             NOT STARTED
Status:                         READY_FOR_P2_CONTRACT_REVIEW
```

## 33. Round-1 repair disposition

The independent contract review of `2f8771a` raised four HIGH findings. Each was checked against the live code at the baseline and the frozen P1 texts before it was repaired. Only these four are repaired; every other decision of this contract stands, apart from the dependent changes listed below.

| finding | original failure, confirmed against live code and frozen text | repair | sections |
| --- | --- | --- | --- |
| P2-CONTRACT-001 — unproven Kp published by another Workline operation | "No push before proof" held only for the planning mutation's own record. Every Workline push publishes its commit with the history it was made on (`mutation._recorded_publication`), and a disjoint-scope operation (a Roadmap hold: event log only) can run in a crash window after Kp and push a descendant of Kp; the frozen §15.5 named that path itself | the publication barrier: no Workline push of any operation publishes a history holding a planning registration commit that no committed Planning Consumption binds; computed from committed objects; checked before every push stage is recorded, when a recorded push would write, and right before every push; Kp proof failure keeps it; a Supersession never clears it | §18.7, §15.5, §17, §21 rows 22–25, 36, 42 |
| P2-CONTRACT-002 — stale sealed Receipt left valid | staleness after the seal ended the planning mutation with generation 3 and its Receipt canonically sealed, unsuperseded and unconsumed, against Frozen P1 R3 §8 | stale after the Receipt → generation 4 (`open`) + Supersession in one stage under the same serialization, persisted before the planning mutation ends; stale before a Receipt writes nothing (no Supersession without a Receipt); the state machine G1 → G2 → G3 [→ G4] replaces the fixed 1/2/3 sequence; invalidation only while no registration stage is recorded, so it never meets a Kp | §11.2, §11.3, §11.6, §11.6.1, §13.2–§13.3, §19.2, §21 rows 12–16 |
| P2-CONTRACT-003 — full currency not re-proven at the registration boundary | currency was evaluated at the use check on the working tree; afterwards only the loader identity was re-checked; C-2(Kp) required only that P descend from `review_binding.head`; the live independent-advancement rule (`mutation._head_advanced_independently`) let Kp be made on a moved HEAD | the declared base read from the committed view of the exact base commit; `use_check_head` noted at the use check; the pre-Kp currency proof right before Kp is recorded and right before a recorded Kp is replayed; a base-exact Kp on its recorded parent P; C-2(Kp) proves full currency on P (P2, P12); after the registration began a difference is `ReconcileRequired`, never `stale`, with no Consumption and no publication | §7.4, §13, §15.1–§15.3, §15.6, §17, §21 rows 19–24 |
| P2-CONTRACT-004 — checkout conversion makes Review records unreadable | measured: under `core.autocrlf=true` without an attribute rule, a fresh clone checks out Review records as CRLF (`git status` clean) and the P1 reader refuses them; the repository commits no rule; the contract relied on P2 never reading old records, yet P2 reads the namespace through `ReviewStore` indexes | the checkout capability: the committed and the effective attributes of every Review path must be exactly form L or form B (measured), before the first Review record and before every Review-writing and Git stage; every existing record must read canonically; the capability contract bound in the Context; the P1 reader and P1 documents unchanged | §5.4, §8, §14.3, §14.5, §14.6, §21 rows 44–45, 51 |

Dependent changes, each required by one of the four: the Context gains `checkout_capability` (004, §8); the evidence record gains two checks (004, §10.6); the generation invocation gains the `invalidate` transition and `invalidation_reason` (002, §11.2); the declared base is read from the committed view, with `review_base_uncommitted` at the freeze (003, §7.4); the `use_check_head` note, the Kp `base_exact` field and the pre-replay proof (003, §15.2, §15.6, §17); the freeze evaluates the barrier on HEAD with a push destination (001, §14.4); the Run records gain gate 4 and the Supersession (002, §3, §14.2, §18.2 M4); new codes and reasons (§25); authority text, surface map and tests (§26–§28). Planning Consumption v2 is unchanged (§16.5).

Preserved: Candidate 7 RETAIN; architecture reopen No; HUMAN-1 = A, per-invocation opt-in; the legacy default unchanged — a legacy invocation evaluates nothing new, and in a Project that never ran a review-v1 planning invocation the barrier finds no planning snapshot and refuses nothing; Review a subordinate authorization gate, never a lifecycle controller; the Roadmap operation the top-level owner; P3 not started; `state.py` reads no Review record; C-2 Planning Consumption v2, C-3 and C-4 Direction A; R9 canonical self-selection; POSIX opt-in fail-closed; legacy POSIX unchanged. No frozen P1 document was edited or needs repair (§24).

## 34. Cross-finding consistency

1. **When does the cross-operation publication barrier begin?** When a registration commit of a planning Run — Kp, or anyone's commit of that Run's reserved registration paths — enters the history of a commit Workline would publish (§18.7). Nothing earlier begins it: generation commits, the Receipt, generation 4 and a registration held only in the working tree carry no registration commit.
2. **What canonical state makes it observable after a crash?** Committed Git objects only: the Candidate snapshot added in the published history (committed by generation 1, and required at the use check to be committed at the commit the registration builds on, §17 item 6), the commit adding the reserved registration paths, and the absence, in the tree being published, of a valid Planning Consumption binding that commit. No runtime record, message, branch position or remote state takes part.
3. **How does G4 invalidation affect that barrier?** It does not. Generation 4 is written only while no registration stage is recorded (§13.3), so a Run with generation 4 has no registration commit, and the barrier never reads gate generations or Supersessions to clear.
4. **Can G4 ever clear a barrier protecting an already-created unproven Kp?** No, on two independent grounds: generation mutation 4 is never started once a registration stage is recorded (§11.10, §13.4), and only a committed Planning Consumption binding the registration commit clears a barrier — which a superseded Receipt can never have (P1 `validate._consumptions`, §16.2). A Supersession can only keep a barrier.
5. **What happens when C-2(Kp) fails?** `ReconcileRequired`; no Consumption; the planning mutation stays pending and every retry repeats the same proof; no generation 4; the barrier holds for every history holding Kp, for every Workline operation; no reset, rebase or amend; a person reconciles (§15.5, §21 row 24).
6. **What happens after runtime-record loss?**
   - generation 1 only, or generation 2: an orphan Run, no Receipt, no barrier; the same request is a fresh Candidate (§21 row 39);
   - sealed generation 3, no Kp: the orphaned Receipt is never used or superseded, and there is no barrier; registration files left in the working tree are never carried by a current-combined commit or another Kp, and a new review-v1 call refuses them as `dirty_overlap` where they overlap its paths; fresh Candidate (row 40);
   - Kp, no Consumption: Kp can never be proven, the barrier holds for good, and a fresh Candidate does not lift it; a person reconciles the branch history (row 42);
   - Km, not published: the Consumption is committed, the barrier is clear for Km and its descendants, and the next Workline push from the branch publishes Km (row 43).
7. **Can another Workline operation push at each state?** Generation 1 to 4, not authorized, stale, registration only in the working tree: yes, and its commit carries only its own paths. Kp made without a committed Consumption: no — its push stage is not recorded, or its recorded push is not applied (`review_publication_barrier`). Km made: yes, from Km or a descendant; a commit made between Kp and Km reaches the destination only as history of Km or of a descendant of Km. Km published: yes.
8. **Can a fresh clone correctly identify the state?** Yes for publication: the barrier reads the same committed objects in any clone. Yes for the Review records wherever the checkout capability held at the commits P2 wrote them: they check out as canonical bytes and `ReviewStore` reads them. A clone holds no runtime record and never resumes a planning mutation; each Run is in the runtime-loss state its committed records show (rows 39–44). Where a clone's checkout semantics are unsafe, `ReviewStore` refuses and review-v1 planning stops there before writing (row 45); the barrier is unaffected.
9. **What if checkout semantics cannot preserve canonical Review bytes?** Review-v1 planning is unavailable in that repository: `review_checkout_unsafe`, `review_checkout_unknown` or `review_namespace_unreadable` before the first Review record, or before the next Review-writing stage of a pending planning mutation; nothing is normalized, the P1 reader is unchanged, legacy planning is unaffected, and the barrier, which reads raw blobs, is unaffected.
10. **Does any repair make Review lifecycle truth?** **No.** `state.py`, `ProjectView` and every lifecycle derivation read no Review record; generation 4 and the Supersession change no lifecycle fact; the barrier decides only whether a push may publish and derives no state; the committed view feeds only proofs and currency evaluations (§22).
